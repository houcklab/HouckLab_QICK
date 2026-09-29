"""Switch q3's modulation-protected loss within one feature visit.

At a freshly located loss feature, compare equal-length corrected target
visits with AC off, AC throughout, AC in the first half, or AC in the second
half. Each four-condition QICK shot pairs two flux patterns with ground and
excited preparations. The pair and condition orders reverse in a second
block after a fresh scout. This tests dynamic loss control and possible
within-visit memory; it does not establish a microscopic TLS identity.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.PulseFunctions import (
    ff_envelope_samples, ff_maxv,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeShotAlternating as alternating,
    TLSPumpProbeWidePassiveScan as wide,
    TLSSwapHoldPilot as swap,
    TLSFluxModulatedT1 as modulated,
)


PATTERNS = ("off", "on", "early", "late")
HOLD_US = 3.6
SWITCH_US = 1.8
PRE_US = 0.05
PARK_RAMP_US = 1.0
MODULATION_MHZ = 30.0
AMPLITUDE_DAC = 1000
SHOTS = 8000
REFERENCE_SHOTS = 400
RECORDS_PER_SHOT = 4


def plan():
    return {"hardware_access": False, "reset_mode": "passive",
            "site": "fresh 3.992-GHz loss feature",
            "patterns": list(PATTERNS),
            "modulation_frequency_mhz": MODULATION_MHZ,
            "amplitude_dac": AMPLITUDE_DAC,
            "hold_us": HOLD_US, "switch_us": SWITCH_US,
            "pre_target_hold_us": PRE_US,
            "park_ramp_us": PARK_RAMP_US,
            "programs": 4, "conditions_per_shot": RECORDS_PER_SHOT,
            "shots_per_program": SHOTS,
            "midpoint_feature_scout": True,
            "full_return_before_readout_us": 40.0,
            "raw_iq_saved": True,
            "measurement": "equal-duration AC off/on and early/late loss at a fresh feature",
            "interpretation": "early-versus-late probes temporal response; "
                              "DC correction and transients remain alternatives "
                              "to TLS memory"}


def switch_waveform(*, pattern, segments, park_gain, target_gain,
                    amplitude_dac, modulation_mhz, sample_rate_mhz,
                    fabric_rate_mhz, cycles, max_gain):
    """Compile a correction-matched AC pattern with a zero-crossing switch."""
    if pattern not in PATTERNS:
        raise ValueError(f"unknown AC switch pattern {pattern!r}")
    kwargs = dict(segments=segments, park_gain=park_gain,
                  target_gain=target_gain, modulation_mhz=modulation_mhz,
                  sample_rate_mhz=sample_rate_mhz,
                  fabric_rate_mhz=fabric_rate_mhz, cycles=cycles,
                  max_gain=max_gain)
    dc, dc_report = modulated.compensated_ac_waveform(
        amplitude_gain=0, **kwargs)
    ac, ac_report = modulated.compensated_ac_waveform(
        amplitude_gain=amplitude_dac, **kwargs)
    if len(dc) % 2 or ac_report["cycles_per_waveform"] % 2:
        raise ValueError("switch boundary must divide an even-cycle AC waveform")
    midpoint = len(dc) // 2
    if abs(int(ac[midpoint]) - int(dc[midpoint])) > 1:
        raise ValueError("AC switch is not at a zero crossing")
    result = {"off": dc, "on": ac,
              "early": np.concatenate((ac[:midpoint], dc[midpoint:])),
              "late": np.concatenate((dc[:midpoint], ac[midpoint:]))}[pattern]
    report = dict(ac_report, pattern=pattern, switch_sample=midpoint,
                  on_samples=(0 if pattern == "off" else len(dc)
                              if pattern == "on" else midpoint),
                  dc_waveform_min=dc_report["waveform_min"],
                  dc_waveform_max=dc_report["waveform_max"])
    return result, report


def conditions(center, patterns, *, reverse=False):
    if len(patterns) != 2 or any(pattern not in PATTERNS for pattern in patterns):
        raise ValueError("each switch program needs two declared patterns")
    rows = [
        {"name": f"{pattern}_{state}", "flux_ghz": float(center),
         "drive_mhz": float(center) * 1000.0, "gain": 0,
         "preparation_state": state, "reference_state": None,
         "pre_drive_us": PRE_US, "post_drive_us": HOLD_US,
         "switch_pattern": pattern}
        for pattern in patterns for state in ("g", "e")]
    return list(reversed(rows)) if reverse else rows


def program_specs(center, *, shots=SHOTS):
    specs = []
    for repeat, pairs in ((0, (("reference", ("off", "on")),
                               ("switch", ("early", "late")))),
                          (1, (("switch", ("early", "late")),
                               ("reference", ("off", "on"))))):
        for pair, patterns in pairs:
            rows = conditions(center, patterns, reverse=bool(repeat))
            specs.append({"name": f"r{repeat}_{pair}", "repeat": repeat,
                          "pair": pair, "patterns": list(patterns),
                          "flux_ghz": float(center), "shots": int(shots),
                          "order": [row["name"] for row in rows],
                          "conditions": rows, "status": "pending"})
    return specs


def recenter_repeat(specs, *, center, repeat):
    for spec in specs:
        if spec["repeat"] != repeat:
            continue
        if spec["status"] != "pending":
            raise ValueError("cannot retarget an acquired switch program")
        spec["flux_ghz"] = float(center)
        spec["conditions"] = conditions(
            center, spec["patterns"], reverse=bool(repeat))
        spec["order"] = [row["name"] for row in spec["conditions"]]


def split_records(records, order, *, shots):
    records = list(records)
    if (len(order) != RECORDS_PER_SHOT or len(set(order)) != RECORDS_PER_SHOT or
            len(records) != int(shots) * RECORDS_PER_SHOT):
        raise ValueError("incomplete or duplicate switch IQ stream")
    return {name: records[index::RECORDS_PER_SHOT]
            for index, name in enumerate(order)}


def score_patterns(fractions):
    x = {pattern: {
        state: float(fractions[f"{pattern}_{state}"])
        for state in ("g", "e")}
        for pattern in PATTERNS}
    contrasts = {pattern: x[pattern]["e"] - x[pattern]["g"]
                 for pattern in PATTERNS}
    grounds = [x[pattern]["g"] for pattern in PATTERNS]
    spread = max(grounds) - min(grounds)
    return {"contrasts": contrasts,
            "on_minus_off_contrast": contrasts["on"] - contrasts["off"],
            "late_minus_early_contrast": contrasts["late"] - contrasts["early"],
            "ground_spread": spread,
            "usable": bool(min(contrasts.values()) >= 0.05 and spread <= 0.10)}


class SwitchProgram(alternating.ShotAlternatingResidentProgram):
    """Four complete target visits per shot, with two sampled AC patterns."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration,
                 loop_calibration):
        cfgs = [dict(cfg) for cfg in condition_cfgs]
        if len(cfgs) != RECORDS_PER_SHOT:
            raise ValueError("switch program requires four conditions")
        common = ("ff_gain", "ff_park_gain", "opx_resident_pre_us",
                  "opx_resident_post_us", "shots", "reps")
        if any(any(cfg[key] != cfgs[0][key] for key in common)
               for cfg in cfgs[1:]):
            raise ValueError("switch conditions must share target and timing")
        patterns = tuple(dict.fromkeys(cfg["opx_switch_pattern"] for cfg in cfgs))
        observed = {(cfg["opx_switch_pattern"],
                     cfg["opx_resident_preparation_state"]) for cfg in cfgs}
        if (len(patterns) != 2 or set(patterns) not in
                ({"off", "on"}, {"early", "late"}) or
                observed != {(pattern, state) for pattern in patterns
                             for state in ("g", "e")} or
                any(int(cfg["opx_resident_gain"]) != 0 for cfg in cfgs) or
                float(cfgs[0]["opx_resident_pre_us"]) != PRE_US or
                float(cfgs[0]["opx_resident_post_us"]) != HOLD_US):
            raise ValueError("invalid switch pattern/preparation coverage")
        self.patterns = patterns
        self.logical_shots = int(cfgs[0]["shots"])
        if self.logical_shots <= 0:
            raise ValueError("switch shot count must be positive")
        self.condition_cfgs = cfgs
        run_cfg = dict(cfgs[0], reps=RECORDS_PER_SHOT * self.logical_shots)
        resident.ResidentDriveProgram.__init__(
            self, soccfg, run_cfg, payload_calibration, loop_calibration)

    def _declare_experiment(self):
        super()._declare_experiment()
        cfg = self.cfg
        generator = self.soccfg["gens"][int(cfg["ff_ch"])]
        _, during, _ = modulated._target_segments(
            self._t1_ff_compensation,
            pre_us=PRE_US + self._t1_ff_settle_us,
            hold_us=HOLD_US,
            recovery_us=self._t1_ff_predistortion_recovery_us)
        cycles = int(self.us2cycles(HOLD_US, gen_ch=cfg["ff_ch"]))
        self.waveforms = {}
        self.waveform_reports = {}
        for pattern in self.patterns:
            wave, report = switch_waveform(
                pattern=pattern, segments=during,
                park_gain=cfg["ff_park_gain"], target_gain=cfg["ff_gain"],
                amplitude_dac=AMPLITUDE_DAC, modulation_mhz=MODULATION_MHZ,
                sample_rate_mhz=generator["fs"],
                fabric_rate_mhz=generator["f_fabric"],
                cycles=cycles, max_gain=ff_maxv(self, scaled=True))
            self.waveforms[pattern] = wave
            self.waveform_reports[pattern] = report
        park_samples = sum(
            length for channel, _, _, length in getattr(self, "_ff_ramp_cache", {})
            if channel == int(cfg["ff_ch"]))
        total_samples = park_samples + sum(len(w) for w in self.waveforms.values())
        capacity = ff_envelope_samples(self)
        if total_samples > capacity:
            raise ValueError(f"switch envelopes need {total_samples} samples; "
                             f"generator has {capacity}")
        self.ff_envelope_report = {"park_samples": park_samples,
                                   "switch_samples": total_samples - park_samples,
                                   "total_samples": total_samples,
                                   "capacity_samples": capacity}
        for pattern, wave in self.waveforms.items():
            self.add_pulse(ch=cfg["ff_ch"], name=f"q3_switch_{pattern}",
                           idata=wave, qdata=np.zeros_like(wave))

    def _resident_excursion(self):
        cfg = self.cfg
        if self._t1_ff_compensation is None:
            raise ValueError("switch experiment requires pinned correction")
        park = float(cfg["ff_park_gain"])
        target = float(cfg["ff_gain"])
        before, _, recovery = modulated._target_segments(
            self._t1_ff_compensation,
            pre_us=float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us,
            hold_us=HOLD_US,
            recovery_us=self._t1_ff_predistortion_recovery_us)
        ff_pulse.play_relative_compensation_segments(self, park, target, before)
        self.set_pulse_registers(
            ch=cfg["ff_ch"], freq=0, style="arb", phase=0,
            stdysel="last", gain=ff_maxv(self),
            waveform=f"q3_switch_{cfg['opx_switch_pattern']}",
            outsel="input")
        self.pulse(ch=cfg["ff_ch"])
        self.sync_all(0)
        ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)


def _condition_configs(base, spec, dc_lookup):
    cfgs = []
    for condition in spec["conditions"]:
        arm = dict(condition, shots=spec["shots"])
        cfg = resident.arm_config(base, arm, dc_lookup)
        cfg["opx_switch_pattern"] = condition["switch_pattern"]
        cfgs.append(cfg)
    return cfgs


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as five, TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
        _integer_dc_grid,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        _block_timeout_s, _run_program, runtime_bundle,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )

    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**wide.parameters(),
                             "output_suffix": "TLS_Floquet_Switch_Scout_pre"})
    selected = swap.select_wide_candidate(
        swap.read_wide_scout(scout), preferred_center=3.992)
    center = round(float(selected["center_ghz"]), 3)
    print(f"[floquet-switch] feature={center:.3f} GHz", flush=True)

    with localizer.scan_environment(correction):
        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        dc, realized = _integer_dc_grid(wide.parameters(),
                                        np.asarray([center]), tls)
        dc_lookup = {center: int(dc[0])}
        compensation = tls._load_correction(str(correction), str(data_root))
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": compensation,
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": 0.5,
                     "flux_predistortion_return_prefix_us": 0.5,
                     "flux_predistortion_recovery_us": 40.0,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.0,
                     "ff_ramp_length": PARK_RAMP_US,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        modulated._target_segments(
            compensation, pre_us=PRE_US + 0.5,
            hold_us=HOLD_US, recovery_us=40.0)
        session_id = ("q3_floquet_switch_" +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = (probe.reference_arms(center, phase="pre") +
                probe.reference_arms(center, phase="post"))
        for ref in refs:
            ref["shots"] = REFERENCE_SHOTS
            ref["status"] = "pending"
        manifest = {"schema": "q3.floquet-switch.v1", "status": "running",
                    "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "dc_lookup": dc_lookup,
                    "realized_ghz": realized.tolist(),
                    "plan": plan(), "references": refs,
                    "programs": program_specs(center)}
        protocol.checkpoint(path, manifest)
        print(f"[floquet-switch] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            programs = {}

            def compile_entry(entry):
                cfgs = _condition_configs(base, entry, dc_lookup)
                program = SwitchProgram(soccfg, cfgs, bundle.payload,
                                        bundle.loop)
                programs[entry["name"]] = program
                entry["waveform_reports"] = program.waveform_reports
                entry["ff_envelope_report"] = program.ff_envelope_report
                for pattern, samples in program.waveforms.items():
                    wave_path = folder / f"{entry['name']}_{pattern}_waveform.npz"
                    np.savez_compressed(wave_path, idata=samples)
                    entry.setdefault("waveform_npz", {})[pattern] = str(wave_path)

            for entry in manifest["programs"][:2]:
                compile_entry(entry)
            for ref in refs[:4]:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, ref, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["first_block_preflight_complete"] = True
            protocol.checkpoint(path, manifest)

            def acquire_ref(ref):
                nonlocal axis
                cfg = resident.arm_config(base, ref, dc_lookup)
                ref["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program,
                    max(30.0, _block_timeout_s(cfg, REFERENCE_SHOTS)),
                    cfg, total_shots=REFERENCE_SHOTS)
                if len(records) != REFERENCE_SHOTS:
                    raise RuntimeError(f"{ref['name']}: incomplete reference IQ")
                raw_refs[ref["name"]] = records
                raw_path = folder / f"{ref['name']}.npz"
                np.savez_compressed(raw_path, i=[r.i for r in records],
                                    q=[r.q for r in records])
                ref["raw_npz"] = str(raw_path)
                if ref["name"] == "ref_e_pre":
                    axis = resident.fit_axis(
                        resident.record_iq(raw_refs["ref_g_pre"]),
                        resident.record_iq(records))
                    manifest["pre_readout_axis"] = axis
                    if not axis["valid"]:
                        raise RuntimeError("pre-run readout reference invalid")
                if axis is not None:
                    ref["excited_fraction_pre_axis"] = resident.classify(records, axis)
                ref["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for ref in refs[:4]:
                print(f"[floquet-switch] {ref['name']}", flush=True)
                acquire_ref(ref)
            for entry in manifest["programs"]:
                if entry["repeat"] == 1 and "mid_selected" not in manifest:
                    mid_scout = localizer.run(
                        data_root=data_root, correction_json=correction,
                        parameter_overrides={**wide.parameters(),
                                             "output_suffix": "TLS_Floquet_Switch_Scout_mid"})
                    mid_selected = swap.select_wide_candidate(
                        swap.read_wide_scout(mid_scout),
                        preferred_center=center)
                    mid_center = round(float(mid_selected["center_ghz"]), 3)
                    recenter_repeat(manifest["programs"], center=mid_center,
                                    repeat=1)
                    mid_dc, mid_realized = _integer_dc_grid(
                        wide.parameters(), np.asarray([mid_center]), tls)
                    dc_lookup[mid_center] = int(mid_dc[0])
                    manifest.update({"mid_scout_csv": str(mid_scout),
                                     "mid_selected": mid_selected,
                                     "mid_center_ghz": mid_center,
                                     "mid_realized_ghz": mid_realized.tolist()})
                    for ref in refs[4:]:
                        ref["flux_ghz"] = mid_center
                        ref["drive_mhz"] = round(1000.0 * mid_center + 5.0, 3)
                        resident.ResidentDriveProgram(
                            soccfg, resident.arm_config(base, ref, dc_lookup),
                            bundle.payload, bundle.loop)
                    for future in manifest["programs"][2:]:
                        compile_entry(future)
                    manifest["preflight_complete"] = True
                    protocol.checkpoint(path, manifest)
                    print(f"[floquet-switch] midpoint feature={mid_center:.3f} GHz",
                          flush=True)
                print(f"[floquet-switch] {entry['name']} {entry['shots']} x 4",
                      flush=True)
                entry["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                records = _run_program(
                    soc, programs[entry["name"]],
                    max(30.0, RECORDS_PER_SHOT *
                        _block_timeout_s(base, entry["shots"])),
                    base, total_shots=entry["shots"])
                split = split_records(records, entry["order"],
                                      shots=entry["shots"])
                for condition in entry["conditions"]:
                    subset = split[condition["name"]]
                    raw_path = folder / f"{entry['name']}_{condition['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    condition["raw_npz"] = str(raw_path)
                    condition["excited_fraction_pre_axis"] = resident.classify(
                        subset, axis)
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)
            for ref in refs[4:]:
                print(f"[floquet-switch] {ref['name']}", flush=True)
                acquire_ref(ref)
            manifest["post_readout_score"] = resident.score_axis(
                axis, resident.record_iq(raw_refs["ref_g_post"]),
                resident.record_iq(raw_refs["ref_e_post"]))
            manifest["transfer_control"] = {
                phase: {"ground": resident.classify(
                            raw_refs[f"ref_transfer_g_{phase}"], axis),
                        "excited": resident.classify(
                            raw_refs[f"ref_transfer_e_{phase}"], axis)}
                for phase in ("pre", "post")}
            for item in manifest["transfer_control"].values():
                item["usable"] = resident.transfer_usable(
                    item["ground"], item["excited"])
            block_scores = {}
            for repeat in (0, 1):
                fractions = {}
                for entry in manifest["programs"]:
                    if entry["repeat"] == repeat:
                        fractions.update({
                            c["name"]: c["excited_fraction_pre_axis"]
                            for c in entry["conditions"]})
                block_scores[f"r{repeat}"] = score_patterns(fractions)
            manifest["effect_report"] = block_scores
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**wide.parameters(),
                                     "output_suffix": "TLS_Floquet_Switch_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = swap.select_wide_candidate(
                    swap.read_wide_scout(post_scout),
                    preferred_center=manifest["mid_center_ghz"])
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            if "post_selected" in manifest:
                manifest["block_stability"] = modulated.block_stability(
                    selected, manifest["mid_selected"],
                    manifest["post_selected"])
                manifest["feature_stable"] = all(
                    manifest["block_stability"].values())
            else:
                manifest["feature_stable"] = False
            valid = (manifest["post_readout_score"]["valid"] and
                     all(x["usable"] for x in manifest["transfer_control"].values())
                     and all(x["usable"] for x in block_scores.values()) and
                     manifest["feature_stable"])
            manifest["status"] = "complete" if valid else "complete_controls_unstable"
            protocol.checkpoint(path, manifest)
            print(f"[floquet-switch] {manifest['status']}: {path}", flush=True)
            return path
        except BaseException as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            protocol.checkpoint(path, manifest)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
