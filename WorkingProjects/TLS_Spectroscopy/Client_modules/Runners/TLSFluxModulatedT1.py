"""Compare q3 loss with and without fast-flux modulation in each QICK shot.

The carrier/sideband pilot showed that a 30-MHz waveform reaches q3. This
follow-up compares 0, 800, and 1600 DAC AC flux at the freshly found loss
feature and a 14-MHz lower flank. Every logical hardware shot interleaves
short/long, modulation off/on, and park-prepared ground/excited visits. The
off visit uses the pinned static correction; the on visit adds a zero-mean
sinusoid to that same correction. Readout occurs after the full corrected
40-us return. This measures a candidate loss response, not TLS identity.
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
    TLSFluxModulationCalibration as calibration,
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeShotAlternating as alternating,
    TLSPumpProbeWidePassiveScan as wide,
)


MODULATION_MHZ = 30.0
AMPLITUDES_DAC = (800, 1600)
HOLDS_US = (0.1, 6.0)
SHOTS = 4000
REFERENCE_SHOTS = 400
PRE_US = 20.0
PARK_RAMP_US = 1.0
RECORDS_PER_SHOT = 8


def compensated_ac_waveform(*, segments, park_gain, target_gain,
                            amplitude_gain, modulation_mhz,
                            sample_rate_mhz, fabric_rate_mhz, cycles, max_gain):
    """Sample the pinned DC correction plus a sinusoid, without clipping."""
    lengths = np.asarray([float(duration) for _, duration in segments], dtype=float)
    levels = np.asarray([float(level) for level, _ in segments], dtype=float)
    if (lengths.size == 0 or not np.all(np.isfinite(lengths)) or
            not np.all(np.isfinite(levels)) or np.any(lengths <= 0)):
        raise ValueError("modulation hold needs finite positive correction segments")
    sine, report = calibration.modulation_waveform(
        sample_rate_mhz=sample_rate_mhz,
        fabric_rate_mhz=fabric_rate_mhz, cycles=cycles,
        baseline_gain=0.0, amplitude_gain=amplitude_gain,
        modulation_mhz=modulation_mhz, max_gain=max_gain)
    times_us = np.arange(len(sine), dtype=float) / float(sample_rate_mhz)
    if times_us[-1] > sum(lengths) + 1e-6:
        raise ValueError("correction segments do not cover the AC hold")
    segment_index = np.searchsorted(np.cumsum(lengths), times_us, side="right")
    segment_index = np.minimum(segment_index, len(levels)-1)
    baseline = float(park_gain) + levels[segment_index] * (
        float(target_gain) - float(park_gain))
    values = np.rint(baseline + sine.astype(float))
    if np.max(np.abs(values)) > min(float(max_gain), 32767.0):
        raise ValueError("AC waveform exceeds the fast-flux DAC range")
    waveform = values.astype(np.int16)
    report.update({"dc_level_count": int(len(levels)),
                   "dc_min": float(np.min(baseline)),
                   "dc_max": float(np.max(baseline)),
                   "waveform_min": int(waveform.min()),
                   "waveform_max": int(waveform.max())})
    return waveform, report


def conditions(flux_ghz, *, amplitude_dac, reverse=False):
    result = []
    for hold_label, hold_us in (("short", HOLDS_US[0]), ("long", HOLDS_US[1])):
        for drive in ("off", "on"):
            for state in ("g", "e"):
                result.append({"name": f"{hold_label}_{drive}_{state}",
                               "flux_ghz": float(flux_ghz),
                               "drive_mhz": float(flux_ghz) * 1000.0,
                               "gain": 0, "preparation_state": state,
                               "reference_state": None,
                               "pre_drive_us": PRE_US,
                               "post_drive_us": hold_us,
                               "modulation_amplitude_dac": (
                                   int(amplitude_dac) if drive == "on" else 0)})
    return list(reversed(result)) if reverse else result


def score_conditions(fractions):
    values = {name: float(value) for name, value in fractions.items()}
    score = {}
    for hold in ("short", "long"):
        for drive in ("off", "on"):
            score[f"{hold}_{drive}_contrast"] = (
                values[f"{hold}_{drive}_e"] - values[f"{hold}_{drive}_g"])
        score[f"{hold}_cold_modulation_change"] = (
            values[f"{hold}_on_g"] - values[f"{hold}_off_g"])
    score["modulation_survival_change"] = (
        score["long_on_contrast"] - score["short_on_contrast"] -
        score["long_off_contrast"] + score["short_off_contrast"])
    return score


def feature_specific_effect(feature, flank):
    return float(feature["modulation_survival_change"] -
                 flank["modulation_survival_change"])


def plan():
    return {"hardware_access": False, "reset_mode": "passive",
            "site": "fresh loss feature and 14-MHz lower flank",
            "modulation_frequency_mhz": MODULATION_MHZ,
            "modulation_amplitudes_dac": list(AMPLITUDES_DAC),
            "holds_us": list(HOLDS_US),
            "pre_target_hold_us": PRE_US,
            "park_ramp_us": PARK_RAMP_US,
            "conditions_per_shot": RECORDS_PER_SHOT,
            "programs": 8, "shots_per_program": SHOTS,
            "full_return_before_readout_us": 40.0,
            "raw_iq_saved": True,
            "measurement": "within-shot hot/cold survival, AC on/off, short/long",
            "note": __doc__}


def _target_segments(compensation, *, pre_us, hold_us, recovery_us):
    target, recovery = ff_pulse.compensation_round_trip_segments(
        compensation, pre_us + hold_us, recovery_us=recovery_us)
    before, during = ff_pulse.split_compensation_segments(target, pre_us)
    if not before or not during:
        raise ValueError("target correction does not cover the modulation hold")
    if sum(duration for _, duration in recovery) < recovery_us - 1e-6:
        raise ValueError("target correction does not cover the full return")
    return before, during, recovery


class ModulatedT1Program(alternating.ShotAlternatingResidentProgram):
    """Eight complete visits/readouts per shot, with one AC level per program."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration, loop_calibration):
        configs = [dict(cfg) for cfg in condition_cfgs]
        if len(configs) != RECORDS_PER_SHOT:
            raise ValueError("modulated T1 requires eight condition configurations")
        common = ("ff_gain", "ff_park_gain", "opx_resident_pre_us", "shots", "reps")
        if any(any(cfg[key] != configs[0][key] for key in common)
               for cfg in configs[1:]):
            raise ValueError("within-shot conditions must share flux, prehold, and shots")
        amplitudes = {int(cfg["opx_modulation_amplitude_dac"]) for cfg in configs}
        if amplitudes != {0, max(amplitudes)} or max(amplitudes) not in AMPLITUDES_DAC:
            raise ValueError("each program needs AC-off and one declared AC-on level")
        observed = {(float(cfg["opx_resident_post_us"]),
                     int(cfg["opx_modulation_amplitude_dac"]),
                     cfg["opx_resident_preparation_state"]) for cfg in configs}
        expected = {(hold, amplitude, state) for hold in HOLDS_US
                    for amplitude in amplitudes for state in ("g", "e")}
        if observed != expected:
            raise ValueError("conditions do not span both holds, AC states, and preparations")
        self.ac_amplitude_dac = max(amplitudes)
        self.logical_shots = int(configs[0]["shots"])
        self.condition_cfgs = configs
        run_cfg = dict(configs[0], reps=RECORDS_PER_SHOT * self.logical_shots)
        resident.ResidentDriveProgram.__init__(
            self, soccfg, run_cfg, payload_calibration, loop_calibration)

    def _declare_experiment(self):
        super()._declare_experiment()
        cfg = self.cfg
        generator = self.soccfg["gens"][int(cfg["ff_ch"])]
        self.ac_reports = {}
        self.ac_waveforms = {}
        for hold in HOLDS_US:
            _, during, _ = _target_segments(
                self._t1_ff_compensation,
                pre_us=PRE_US + self._t1_ff_settle_us,
                hold_us=hold,
                recovery_us=self._t1_ff_predistortion_recovery_us)
            cycles = int(self.us2cycles(hold, gen_ch=cfg["ff_ch"]))
            waveform, report = compensated_ac_waveform(
                segments=during,
                park_gain=cfg["ff_park_gain"], target_gain=cfg["ff_gain"],
                amplitude_gain=self.ac_amplitude_dac,
                modulation_mhz=MODULATION_MHZ,
                sample_rate_mhz=generator["fs"],
                fabric_rate_mhz=generator["f_fabric"],
                cycles=cycles, max_gain=ff_maxv(self, scaled=True))
            self.ac_reports[str(hold)] = report
            self.ac_waveforms[str(hold)] = waveform
        park_samples = sum(
            length for channel, _, _, length in getattr(self, "_ff_ramp_cache", {})
            if channel == int(cfg["ff_ch"]))
        total_samples = park_samples + sum(len(x) for x in self.ac_waveforms.values())
        budget = ff_envelope_samples(self)
        if total_samples > budget:
            raise ValueError(f"AC flux and park envelopes need {total_samples} "
                             f"samples; generator has {budget}")
        self.ff_envelope_report = {"park_samples": park_samples,
                                   "ac_samples": total_samples - park_samples,
                                   "total_samples": total_samples,
                                   "capacity_samples": budget}
        for hold, waveform in self.ac_waveforms.items():
            name = "q3_ac_short" if float(hold) == HOLDS_US[0] else "q3_ac_long"
            self.add_pulse(ch=cfg["ff_ch"], name=name, idata=waveform,
                           qdata=np.zeros_like(waveform))

    def _resident_excursion(self):
        cfg = self.cfg
        if self._t1_ff_compensation is None:
            raise ValueError("modulated T1 requires the pinned flux correction")
        park = float(cfg["ff_park_gain"])
        target = float(cfg["ff_gain"])
        hold = float(cfg["opx_resident_post_us"])
        before, during, recovery = _target_segments(
            self._t1_ff_compensation,
            pre_us=float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us,
            hold_us=hold,
            recovery_us=self._t1_ff_predistortion_recovery_us)
        ff_pulse.play_relative_compensation_segments(self, park, target, before)
        if int(cfg["opx_modulation_amplitude_dac"]) == 0:
            ff_pulse.play_relative_compensation_segments(self, park, target, during)
        else:
            name = "q3_ac_short" if hold == HOLDS_US[0] else "q3_ac_long"
            self.set_pulse_registers(
                ch=cfg["ff_ch"], freq=0, style="arb", phase=0,
                stdysel="last", gain=ff_maxv(self), waveform=name,
                outsel="input")
            self.pulse(ch=cfg["ff_ch"])
        self.sync_all(0)
        ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)


def program_specs(center):
    flank = round(float(center) + resident.FLANK_OFFSET_GHZ, 3)
    specs = []
    for repeat in (0, 1):
        sites = (("feature", float(center)), ("flank", flank))
        amplitudes = AMPLITUDES_DAC
        if repeat:
            sites, amplitudes = tuple(reversed(sites)), tuple(reversed(amplitudes))
        for site, flux in sites:
            for amplitude in amplitudes:
                conds = conditions(flux, amplitude_dac=amplitude,
                                   reverse=bool(repeat))
                specs.append({"name": f"r{repeat}_{site}_a{amplitude}",
                              "repeat": repeat, "site": site,
                              "flux_ghz": flux,
                              "amplitude_dac": amplitude,
                              "shots": SHOTS,
                              "order": [c["name"] for c in conds],
                              "conditions": conds, "status": "pending"})
    return specs


def split_records(records, order, *, shots):
    records = list(records)
    expected = {x["name"] for x in conditions(4.136, amplitude_dac=AMPLITUDES_DAC[0])}
    if len(order) != RECORDS_PER_SHOT or set(order) != expected:
        raise ValueError("invalid eight-condition stream order")
    if len(records) != int(shots) * RECORDS_PER_SHOT:
        raise ValueError("incomplete eight-condition IQ stream")
    return {name: records[index::RECORDS_PER_SHOT]
            for index, name in enumerate(order)}


def _condition_configs(base, spec, dc_lookup):
    cfgs = []
    for cond in spec["conditions"]:
        arm = dict(cond, shots=spec["shots"])
        cfg = resident.arm_config(base, arm, dc_lookup)
        cfg["opx_modulation_amplitude_dac"] = cond["modulation_amplitude_dac"]
        cfgs.append(cfg)
    return cfgs


def _controls(scores):
    reports = {}
    for name, score in scores.items():
        site = "feature" if "_feature_" in name else "flank"
        short_floor = 0.08 if site == "feature" else 0.20
        long_floor = 0.03 if site == "feature" else 0.10
        reports[name] = {
            "usable": bool(
                min(score["short_off_contrast"], score["short_on_contrast"])
                >= short_floor and
                score["long_off_contrast"] >= long_floor and
                max(abs(score["short_cold_modulation_change"]),
                    abs(score["long_cold_modulation_change"])) <= 0.10),
            "short_hot_floor": short_floor, "long_off_hot_floor": long_floor}
    return {"programs": reports,
            "usable": all(x["usable"] for x in reports.values())}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**adaptive.scout_parameters(phase="pre"),
                             "output_suffix": "TLS_FluxModulated_T1_Scout_pre"})
    selected = adaptive.select_loss_feature(adaptive.read_scout(scout))
    center = round(float(selected["center_ghz"]), 3)
    flank = round(center + resident.FLANK_OFFSET_GHZ, 3)
    print(f"[mod-T1] feature={center:.3f} GHz; flank={flank:.3f} GHz",
          flush=True)

    with localizer.scan_environment(correction):
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

        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        grid = np.asarray([center, flank], dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
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
        for hold in HOLDS_US:
            _target_segments(compensation, pre_us=PRE_US + 0.5,
                             hold_us=hold, recovery_us=40.0)
        session_id = ("q3_flux_modulated_t1_" +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = probe.reference_arms(center, phase="pre") + \
            probe.reference_arms(center, phase="post")
        for ref in refs:
            ref["shots"] = REFERENCE_SHOTS
            ref["status"] = "pending"
        manifest = {"schema": "q3.flux-modulated-t1.v1",
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "flank_ghz": flank,
                    "dc_lookup": dc_lookup,
                    "realized_ghz": realized.tolist(),
                    "plan": plan(), "references": refs,
                    "programs": program_specs(center)}
        protocol.checkpoint(path, manifest)
        print(f"[mod-T1] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            programs = {}
            for entry in manifest["programs"]:
                cfgs = _condition_configs(base, entry, dc_lookup)
                program = ModulatedT1Program(
                    soccfg, cfgs, bundle.payload, bundle.loop)
                programs[entry["name"]] = program
                entry["waveform_reports"] = program.ac_reports
                entry["ff_envelope_report"] = program.ff_envelope_report
                for hold, samples in program.ac_waveforms.items():
                    wave_path = folder / f"{entry['name']}_waveform_{hold}.npz"
                    np.savez_compressed(wave_path, idata=samples)
                    entry.setdefault("waveform_npz", {})[hold] = str(wave_path)
            for ref in refs:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, ref, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["preflight_complete"] = True
            protocol.checkpoint(path, manifest)

            def acquire_ref(ref):
                nonlocal axis
                cfg = resident.arm_config(base, ref, dc_lookup)
                ref["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, REFERENCE_SHOTS)),
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
                print(f"[mod-T1] {ref['name']}", flush=True)
                acquire_ref(ref)
            for entry in manifest["programs"]:
                print(f"[mod-T1] {entry['name']} {SHOTS} x 8", flush=True)
                entry["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                records = _run_program(
                    soc, programs[entry["name"]],
                    max(30.0, RECORDS_PER_SHOT * _block_timeout_s(base, SHOTS)),
                    base, total_shots=SHOTS)
                split = split_records(records, entry["order"], shots=SHOTS)
                for cond in entry["conditions"]:
                    subset = split[cond["name"]]
                    raw_path = folder / f"{entry['name']}_{cond['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    cond["raw_npz"] = str(raw_path)
                    cond["excited_fraction_pre_axis"] = resident.classify(subset, axis)
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)
            for ref in refs[4:]:
                print(f"[mod-T1] {ref['name']}", flush=True)
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
                item["usable"] = resident.transfer_usable(item["ground"],
                                                           item["excited"])
            scores = {}
            for entry in manifest["programs"]:
                fractions = {c["name"]: c["excited_fraction_pre_axis"]
                             for c in entry["conditions"]}
                scores[entry["name"]] = score_conditions(fractions)
            manifest["program_scores"] = scores
            manifest["control_report"] = _controls(scores)
            effects = {}
            for repeat in (0, 1):
                for amplitude in AMPLITUDES_DAC:
                    f = scores[f"r{repeat}_feature_a{amplitude}"]
                    b = scores[f"r{repeat}_flank_a{amplitude}"]
                    effects[f"r{repeat}_a{amplitude}"] = {
                        "feature_modulation_survival_change":
                            f["modulation_survival_change"],
                        "flank_modulation_survival_change":
                            b["modulation_survival_change"],
                        "feature_specific_effect": feature_specific_effect(f, b)}
            manifest["effect_report"] = effects
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**adaptive.scout_parameters(phase="post"),
                                     "output_suffix": "TLS_FluxModulated_T1_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = adaptive.select_loss_feature(
                    adaptive.read_scout(post_scout))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = (
                resident.feature_stable(selected, manifest["post_selected"])
                if "post_selected" in manifest else False)
            valid = (manifest["post_readout_score"]["valid"] and
                     all(x["usable"] for x in manifest["transfer_control"].values()) and
                     manifest["control_report"]["usable"] and
                     manifest["feature_stable"])
            manifest["status"] = "complete" if valid else "complete_controls_unstable"
            protocol.checkpoint(path, manifest)
            print(f"[mod-T1] {manifest['status']}: {path}", flush=True)
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
