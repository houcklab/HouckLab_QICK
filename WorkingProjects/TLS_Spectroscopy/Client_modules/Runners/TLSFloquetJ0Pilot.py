"""Test for a local loss minimum near the first Floquet J0 zero on q3.

This is a bounded amplitude pilot, not a linewidth measurement. A fresh wide
scout selects a locally qualified loss feature. At 5 and 10 MHz, three amplitudes
estimated from the *static* local flux slope bracket beta=2.4048. Every AC
program interleaves off/on, short/long, and park-prepared g/e visits. Static
center/±2-MHz profiles bracket each block and a new scout recenters block 2.
The delivered AC amplitude is not yet calibrated, so no programmed setting
is labeled an observed J0 zero. All raw IQ and compiled waveforms are saved.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse, flux_fit
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSFluxModulatedT1 as modulated,
    TLSFloquetSwitch as switch,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeShotAlternating as alternating,
    TLSPumpProbeWidePassiveScan as wide,
    TLSSwapHoldPilot as swap,
)


J0_ZERO = 2.4048255577
FREQUENCIES_MHZ = (5.0, 10.0)
BETA_TARGETS = (1.8, J0_ZERO, 3.0)
STATIC_OFFSETS_MHZ = (-2.0, 0.0, 2.0)
HOLDS_US = (1.6, 5.6)
PRE_US = 0.05
SHOTS = 4000
REFERENCE_SHOTS = 400
STATIC_RECORDS_PER_SHOT = 12
LABEL = "TLS_Floquet_J0_Pilot"


def plan():
    return {"hardware_access": False, "reset_mode": "passive",
            "purpose": "test a reproducible local loss minimum near an estimated J0 zero",
            "feature": "fresh locally qualified 3.8-4.3-GHz loss; prefer recent 4.106-GHz site",
            "modulation_frequencies_mhz": list(FREQUENCIES_MHZ),
            "beta_targets": list(BETA_TARGETS),
            "amplitude_calibration": "local static slope only; delivered AC transfer unknown",
            "holds_us": list(HOLDS_US), "pre_target_hold_us": PRE_US,
            "static_offsets_mhz": list(STATIC_OFFSETS_MHZ),
            "static_profiles_per_block": 2, "ac_programs_per_block": 6,
            "blocks": 2, "shots_per_program": SHOTS,
            "scouts": "wide pre/mid/post, with block-2 recentering",
            "ac_conditions_per_shot": modulated.RECORDS_PER_SHOT,
            "static_conditions_per_shot": STATIC_RECORDS_PER_SHOT,
            "full_return_before_readout_us": 40.0,
            "raw_iq_and_compiled_waveforms_saved": True,
            "interpretation": "local amplitude minimum is a Floquet pilot, not yet an intrinsic TLS linewidth"}


def local_static_slope_mhz_per_dac(fit_params, center_dac, *, estimator=None):
    """Symmetric static qubit-frequency slope, not AC-line transfer."""
    estimator = flux_fit.estimate_fit_frequency_ghz_array if estimator is None else estimator
    gains = np.asarray([int(center_dac) - 100, int(center_dac) + 100])
    frequencies = np.asarray(estimator(fit_params, gains), dtype=float)
    if frequencies.shape != (2,) or not np.all(np.isfinite(frequencies)):
        raise ValueError("invalid local static flux slope")
    return abs(float(frequencies[1] - frequencies[0])) * 1000.0 / 200.0


def amplitude_settings(slope_mhz_per_dac):
    slope = float(slope_mhz_per_dac)
    if not np.isfinite(slope) or slope <= 0:
        raise ValueError("local static flux slope must be finite and positive")
    settings = []
    for frequency in FREQUENCIES_MHZ:
        for beta in BETA_TARGETS:
            amplitude = int(np.rint(beta * frequency / slope))
            if not 1 <= amplitude <= 1000:
                raise ValueError("estimated J0 bracket outside 1..1000 DAC pilot range")
            settings.append({"modulation_mhz": frequency,
                             "beta_target": beta,
                             "amplitude_dac": amplitude,
                             "beta_estimate_source":
                             "static_flux_slope_unverified_ac_transfer"})
    if len({(item["modulation_mhz"], item["amplitude_dac"])
            for item in settings}) != len(settings):
        raise ValueError("local static flux slope cannot resolve beta targets")
    return settings


def static_conditions(center, *, reverse=False):
    rows = []
    for offset in STATIC_OFFSETS_MHZ:
        frequency = round(float(center) + offset / 1000.0, 3)
        label = ("m2" if offset < 0 else "p2" if offset > 0 else "c")
        for hold_label, hold in zip(("short", "long"), HOLDS_US):
            for state in ("g", "e"):
                rows.append({"name": f"{label}_{hold_label}_{state}",
                             "offset_mhz": offset, "flux_ghz": frequency,
                             "drive_mhz": 1000.0 * frequency, "gain": 0,
                             "preparation_state": state,
                             "reference_state": None,
                             "pre_drive_us": PRE_US,
                             "post_drive_us": hold})
    return list(reversed(rows)) if reverse else rows


def _entry(center, repeat, kind, position, *, setting=None, shots=SHOTS):
    reverse = bool(repeat)
    if kind == "static":
        rows = static_conditions(center, reverse=reverse)
        name = f"r{repeat}_static_{position}"
    else:
        rows = modulated.conditions(
            center, amplitude_dac=setting["amplitude_dac"],
            reverse=reverse, holds_us=HOLDS_US, pre_us=PRE_US)
        name = (f"r{repeat}_f{setting['modulation_mhz']:g}"
                f"_a{setting['amplitude_dac']}")
    return {"name": name, "kind": kind, "repeat": repeat,
            "position": position, "center_ghz": float(center),
            "setting": setting, "amplitude_dac":
            None if setting is None else setting["amplitude_dac"],
            "shots": int(shots), "order": [row["name"] for row in rows],
            "conditions": rows, "status": "pending"}


def program_specs(center, settings, *, shots=SHOTS):
    specs = []
    for repeat in (0, 1):
        specs.append(_entry(center, repeat, "static", "pre", shots=shots))
        ordered = list(reversed(settings)) if repeat else list(settings)
        for position, setting in enumerate(ordered):
            specs.append(_entry(center, repeat, "ac", position,
                                setting=setting, shots=shots))
        specs.append(_entry(center, repeat, "static", "post", shots=shots))
    return specs


def recenter_repeat(specs, *, center, repeat):
    for entry in specs:
        if entry["repeat"] != repeat:
            continue
        if entry["status"] != "pending":
            raise ValueError("cannot recenter an acquired pilot program")
        refreshed = _entry(center, repeat, entry["kind"], entry["position"],
                           setting=entry["setting"], shots=entry["shots"])
        entry.update(refreshed)


def split_records(records, order, *, shots):
    count = len(order)
    if (count not in (modulated.RECORDS_PER_SHOT, STATIC_RECORDS_PER_SHOT) or
            len(set(order)) != count or len(records) != count * int(shots)):
        raise ValueError("incomplete or duplicate J0-pilot IQ stream")
    return {name: records[index::count] for index, name in enumerate(order)}


class StaticProfileProgram(alternating.ShotAlternatingResidentProgram):
    """Twelve passive, corrected static visits at center and ±2 MHz."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration,
                 loop_calibration):
        cfgs = [dict(cfg) for cfg in condition_cfgs]
        if len(cfgs) != STATIC_RECORDS_PER_SHOT:
            raise ValueError("static profile needs twelve conditions")
        observed = {(round(float(cfg["opx_static_offset_mhz"]), 3),
                     float(cfg["opx_resident_post_us"]),
                     cfg["opx_resident_preparation_state"]) for cfg in cfgs}
        expected = {(offset, hold, state) for offset in STATIC_OFFSETS_MHZ
                    for hold in HOLDS_US for state in ("g", "e")}
        if observed != expected or any(int(cfg["opx_resident_gain"]) != 0
                                       for cfg in cfgs):
            raise ValueError("static profile coverage is incomplete")
        self.logical_shots = int(cfgs[0]["shots"])
        if self.logical_shots <= 0 or any(int(cfg["shots"]) != self.logical_shots
                                         for cfg in cfgs):
            raise ValueError("static profile shot counts must agree")
        self.condition_cfgs = cfgs
        run_cfg = dict(cfgs[0], reps=STATIC_RECORDS_PER_SHOT * self.logical_shots)
        resident.ResidentDriveProgram.__init__(
            self, soccfg, run_cfg, payload_calibration, loop_calibration)

    def _resident_excursion(self):
        cfg = self.cfg
        if self._t1_ff_compensation is None:
            raise ValueError("static profile needs the pinned flux correction")
        park = float(cfg["ff_park_gain"])
        target = float(cfg["ff_gain"])
        before, during, recovery = modulated._target_segments(
            self._t1_ff_compensation,
            pre_us=float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us,
            hold_us=float(cfg["opx_resident_post_us"]),
            recovery_us=self._t1_ff_predistortion_recovery_us)
        ff_pulse.play_relative_compensation_segments(self, park, target, before)
        ff_pulse.play_relative_compensation_segments(self, park, target, during)
        self.sync_all(0)
        ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)


def _condition_configs(base, entry, dc_lookup):
    if entry["kind"] == "ac":
        return modulated._condition_configs(base, entry, dc_lookup)
    cfgs = []
    for condition in entry["conditions"]:
        arm = dict(condition, shots=entry["shots"])
        cfg = resident.arm_config(base, arm, dc_lookup)
        cfg["opx_static_offset_mhz"] = condition["offset_mhz"]
        cfgs.append(cfg)
    return cfgs


def _score_entry(entry):
    fractions = {condition["name"]: condition["excited_fraction_pre_axis"]
                 for condition in entry["conditions"]}
    if entry["kind"] == "ac":
        return modulated.score_conditions(fractions)
    return {label: {hold: (
        fractions[f"{label}_{hold}_e"] - fractions[f"{label}_{hold}_g"])
        for hold in ("short", "long")}
        for label in ("m2", "c", "p2")}


def _score_usable(entry, score):
    if entry["kind"] == "static":
        return bool(score["c"]["short"] >= 0.08 and
                    all(score[label]["short"] >= 0.08
                        for label in ("m2", "p2")))
    return bool(
        min(score["short_off_contrast"], score["short_on_contrast"]) >= 0.08
        and score["long_off_contrast"] >= 0.03
        and max(abs(score["short_cold_modulation_change"]),
                abs(score["long_cold_modulation_change"])) <= 0.10)


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
                             "output_suffix": f"{LABEL}_Scout_pre"})
    selected = switch.select_switch_candidate(
        swap.read_wide_scout(scout), preferred_center=4.106)
    center = round(float(selected["center_ghz"]), 3)
    print(f"[j0-pilot] fresh feature={center:.3f} GHz", flush=True)

    with localizer.scan_environment(correction):
        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        grid = np.asarray([round(center + x / 1000.0, 3)
                           for x in STATIC_OFFSETS_MHZ])
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
        slope = local_static_slope_mhz_per_dac(
            tls.FLUX_FIT_PARAMS, dc_lookup[center])
        settings = amplitude_settings(slope)
        print(f"[j0-pilot] static slope={slope:.5f} MHz/DAC; "
              f"estimated settings={[(x['modulation_mhz'], x['amplitude_dac']) for x in settings]}",
              flush=True)
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
                     "ff_ramp_length": modulated.PARK_RAMP_US,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        for hold in HOLDS_US:
            modulated._target_segments(
                compensation, pre_us=PRE_US + 0.5, hold_us=hold,
                recovery_us=40.0)

        session_id = ("q3_floquet_j0_pilot_" +
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
        manifest = {"schema": "q3.floquet-j0-pilot.v1", "status": "running",
                    "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "dc_lookup": dc_lookup,
                    "realized_ghz": realized.tolist(),
                    "local_static_slope_mhz_per_dac": slope,
                    "amplitude_settings": settings,
                    "plan": plan(), "references": refs,
                    "programs": program_specs(center, settings)}
        protocol.checkpoint(path, manifest)
        print(f"[j0-pilot] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            programs = {}

            def compile_entry(entry):
                cfgs = _condition_configs(base, entry, dc_lookup)
                if entry["kind"] == "ac":
                    program = modulated.ModulatedT1Program(
                        soccfg, cfgs, bundle.payload, bundle.loop,
                        holds_us=HOLDS_US, pre_us=PRE_US,
                        allowed_amplitudes=tuple(
                            x["amplitude_dac"] for x in settings),
                        modulation_mhz=entry["setting"]["modulation_mhz"])
                    entry["waveform_reports"] = program.ac_reports
                    entry["ff_envelope_report"] = program.ff_envelope_report
                    for hold, samples in program.ac_waveforms.items():
                        wave_path = folder / f"{entry['name']}_waveform_{hold}.npz"
                        np.savez_compressed(wave_path, idata=samples)
                        entry.setdefault("waveform_npz", {})[hold] = str(wave_path)
                else:
                    program = StaticProfileProgram(
                        soccfg, cfgs, bundle.payload, bundle.loop)
                programs[entry["name"]] = program

            for entry in manifest["programs"][:8]:
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
                    ref["excited_fraction_pre_axis"] = resident.classify(
                        records, axis)
                ref["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for ref in refs[:4]:
                print(f"[j0-pilot] {ref['name']}", flush=True)
                acquire_ref(ref)
            for entry in manifest["programs"]:
                if entry["repeat"] == 1 and "mid_selected" not in manifest:
                    mid_scout = localizer.run(
                        data_root=data_root, correction_json=correction,
                        parameter_overrides={**wide.parameters(),
                                             "output_suffix": f"{LABEL}_Scout_mid"})
                    mid_selected = switch.select_switch_candidate(
                        swap.read_wide_scout(mid_scout),
                        preferred_center=center)
                    mid_center = round(float(mid_selected["center_ghz"]), 3)
                    recenter_repeat(manifest["programs"], center=mid_center,
                                    repeat=1)
                    mid_grid = np.asarray([
                        round(mid_center + x / 1000.0, 3)
                        for x in STATIC_OFFSETS_MHZ])
                    mid_dc, mid_realized = _integer_dc_grid(
                        wide.parameters(), mid_grid, tls)
                    dc_lookup.update({float(f): int(g)
                                      for f, g in zip(mid_grid, mid_dc)})
                    mid_slope = local_static_slope_mhz_per_dac(
                        tls.FLUX_FIT_PARAMS, dc_lookup[mid_center])
                    manifest.update({"mid_scout_csv": str(mid_scout),
                                     "mid_selected": mid_selected,
                                     "mid_center_ghz": mid_center,
                                     "mid_realized_ghz": mid_realized.tolist(),
                                     "mid_local_static_slope_mhz_per_dac": mid_slope})
                    for ref in refs[4:]:
                        ref["flux_ghz"] = mid_center
                        ref["drive_mhz"] = round(1000.0 * mid_center + 5.0, 3)
                        resident.ResidentDriveProgram(
                            soccfg, resident.arm_config(base, ref, dc_lookup),
                            bundle.payload, bundle.loop)
                    for future in manifest["programs"][8:]:
                        compile_entry(future)
                    manifest["preflight_complete"] = True
                    protocol.checkpoint(path, manifest)
                    print(f"[j0-pilot] midpoint feature={mid_center:.3f} GHz",
                          flush=True)
                records_per_shot = len(entry["order"])
                print(f"[j0-pilot] {entry['name']} {entry['shots']} x "
                      f"{records_per_shot}", flush=True)
                entry["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                records = _run_program(
                    soc, programs[entry["name"]],
                    max(30.0, records_per_shot *
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
                entry["score"] = _score_entry(entry)
                entry["controls_usable"] = _score_usable(entry, entry["score"])
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)
                if entry["kind"] == "ac":
                    print(f"[j0-pilot] {entry['name']} protection="
                          f"{entry['score']['modulation_survival_change']:+.4f} "
                          f"controls={entry['controls_usable']}", flush=True)
                else:
                    center_score = entry["score"]["c"]
                    print(f"[j0-pilot] {entry['name']} static-center "
                          f"short={center_score['short']:.3f} "
                          f"long={center_score['long']:.3f} "
                          f"controls={entry['controls_usable']}", flush=True)

            for ref in refs[4:]:
                print(f"[j0-pilot] {ref['name']}", flush=True)
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
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**wide.parameters(),
                                     "output_suffix": f"{LABEL}_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = switch.select_switch_candidate(
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
                     and all(x["controls_usable"] for x in manifest["programs"])
                     and manifest["feature_stable"])
            manifest["status"] = "complete" if valid else "complete_controls_unstable"
            protocol.checkpoint(path, manifest)
            print(f"[j0-pilot] {manifest['status']}: {path}", flush=True)
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
