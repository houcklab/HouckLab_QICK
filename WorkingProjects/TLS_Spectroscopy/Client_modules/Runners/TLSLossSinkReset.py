"""Test whether a fresh q3 loss feature acts as a cold, reusable reset sink.

This first stage measures feature/control cooling and ground-state heating as a
function of hold time. Every hardware shot interleaves both flux sites, both
preparations, and a 0.1-us reference hold. It uses the already verified passive
reset and corrected single-visit pulse path. A second-use test is conditional
on the measured cooling curve; this runner makes no TLS-identity claim.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeWidePassiveScan as wide,
    TLSSwapHoldConfirm as confirm,
    TLSSwapHoldPilot as swap,
)


REFERENCE_HOLD_US = .1
HOLDS_US = (2.0, 5.0, 10.0, 20.0, 40.0, 60.0)
SHOTS = 800
REFERENCE_SHOTS = 400
RETURN_US = 40.0


def _normalized_scout_survival(row, delay, suffix):
    ground = float(row[f"P0{suffix}"])
    excited = float(row[f"P1{suffix}"])
    survival = float(row[f"Ps_{delay}us{suffix}"])
    contrast = excited - ground
    if not all(map(math.isfinite, (ground, excited, survival))) or contrast < .15:
        return math.nan
    return (survival - ground) / contrast


def select_reset_candidate(rows):
    """Qualify an isolated 25-us dip, then prefer its early 10-us sink rate."""
    indexed = {round(float(row["target_frequency_ghz"]), 3): row
               for row in rows}
    expected = {round(3.8 + .002 * index, 3) for index in range(251)}
    if len(rows) != 251 or set(indexed) != expected:
        raise ValueError("reset candidate needs a complete 251-point scout")
    candidates = {}
    for anchor in sorted(indexed):
        if not 3.820 <= anchor <= 4.280:
            continue
        try:
            candidate = confirm.select_crowded_wide_candidate(
                rows, preferred_center=anchor)
        except ValueError:
            continue
        center = candidate["center_ghz"]
        control = candidate["control_ghz"]
        advantages = {}
        for direction, suffix in (("combined", ""),
                                  ("up", "_scan_up"),
                                  ("down", "_scan_down")):
            feature = _normalized_scout_survival(indexed[center], 10, suffix)
            quiet = _normalized_scout_survival(indexed[control], 10, suffix)
            advantages[direction] = quiet - feature
        if (not all(math.isfinite(value) for value in advantages.values()) or
                min(advantages.values()) < .10):
            continue
        candidate = {**candidate, "anchor_ghz": center,
                     "early_advantage": min(advantages.values()),
                     "early_advantage_by_direction": advantages,
                     "selector": "wide_early_reset_candidate"}
        key = (center, control)
        candidates[key] = candidate
    if not candidates:
        raise ValueError("no qualified early-time loss sink with a quiet control")
    return max(candidates.values(), key=lambda item: (
        item["early_advantage"],
        min(item["depth_scan_up"], item["depth_scan_down"]),
        item["control_min_survival"]))


def program_specs(feature_ghz, control_ghz):
    specs = []
    for cycle in (0, 1):
        holds = HOLDS_US if cycle == 0 else tuple(reversed(HOLDS_US))
        for hold in holds:
            conditions = [
                {"name": f"{site}_{dwell}_{state}", "site": site,
                 "flux_ghz": float(frequency), "hold_us": duration,
                 "state": state}
                for site, frequency in (("feature", feature_ghz),
                                        ("control", control_ghz))
                for dwell, duration in (("early", REFERENCE_HOLD_US),
                                        ("late", hold))
                for state in ("g", "e")]
            if cycle:
                conditions.reverse()
            label = f"{hold:g}".replace(".", "p")
            specs.append({"name": f"r{cycle}_t{label}", "cycle": cycle,
                          "hold_us": hold, "shots": SHOTS,
                          "flux_ghz": float(feature_ghz),
                          "order": [condition["name"]
                                    for condition in conditions],
                          "conditions": conditions, "status": "pending"})
    return specs


def score_reset(fractions):
    values = {name: float(value) for name, value in fractions.items()}
    feature = {dwell: {state: values[f"feature_{dwell}_{state}"]
                       for state in ("g", "e")}
               for dwell in ("early", "late")}
    control = {dwell: {state: values[f"control_{dwell}_{state}"]
                       for state in ("g", "e")}
               for dwell in ("early", "late")}
    early_control_contrast = control["early"]["e"] - control["early"]["g"]
    late_control_contrast = control["late"]["e"] - control["late"]["g"]
    extra_cooling = control["late"]["e"] - feature["late"]["e"]
    extra_heating = feature["late"]["g"] - control["late"]["g"]
    early_cooling_offset = control["early"]["e"] - feature["early"]["e"]
    return {
        "feature": feature, "control": control,
        "extra_excited_cooling": extra_cooling,
        "incremental_excited_cooling": extra_cooling - early_cooling_offset,
        "extra_ground_heating": extra_heating,
        "early_control_contrast": early_control_contrast,
        "late_control_contrast": late_control_contrast,
        "cold_sink_candidate": bool(
            early_control_contrast >= .20 and extra_cooling >= .05 and
            extra_heating <= .05),
        "control_usable": bool(
            early_control_contrast >= .20 and
            control["late"]["g"] - control["early"]["g"] <= .08),
    }


def plan():
    return {"hardware_access": False, "reset_mode": "passive",
            "purpose": "test a fresh loss feature as a measurement-free reset sink",
            "scout_range_ghz": [3.8, 4.3],
            "selection": "qualified bidirectional loss with clean ±12–20-MHz control; "
                         "rank by 10-us rather than 25-us loss",
            "reference_hold_us": REFERENCE_HOLD_US,
            "later_holds_us": list(HOLDS_US), "conditions_per_shot": 8,
            "shots_per_program": SHOTS, "programs": 2 * len(HOLDS_US),
            "condition_order": "feature/control, g/e, reference/test; "
                               "all interleaved and reversed in second cycle",
            "full_return_before_readout_us": RETURN_US,
            "inter_shot_delay_us": 500.0,
            "raw_iq_saved": True,
            "interpretation": "report cooling, ground heating, and total reset latency; "
                              "do not infer an absolute fidelity from raw classifier fractions",
            "follow_up": "repeat-use stress test only if cooling is useful and controls pass"}


def _reference_arms(center):
    references = (probe.reference_arms(center, phase="pre") +
                  probe.reference_arms(center, phase="post"))
    for reference in references:
        reference.update(shots=REFERENCE_SHOTS, status="pending")
    return references


def _normalized_iq(records, axis, ground_iq, excited_iq):
    rotation = np.exp(-1j * axis["theta_rad"])
    ground = np.median(np.real(ground_iq * rotation))
    excited = np.median(np.real(excited_iq * rotation))
    if excited - ground <= 0:
        raise RuntimeError("readout IQ reference axis collapsed")
    return float((np.mean(np.real(resident.record_iq(records) * rotation)) -
                  ground) / (excited - ground))


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**wide.parameters(),
                             "output_suffix": "TLS_Loss_Sink_Reset_Scout_pre"})
    selected = select_reset_candidate(swap.read_wide_scout(scout))
    center = float(selected["center_ghz"])
    control = float(selected["control_ghz"])
    print(f"[loss-sink-reset] feature={center:.3f} GHz; "
          f"quiet control={control:.3f} GHz; "
          f"10-us advantage={selected['early_advantage']:.3f}", flush=True)

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
        specs = program_specs(center, control)
        grid = np.asarray([center, control], dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
        compensation = tls._load_correction(str(correction), str(data_root))
        for hold in (REFERENCE_HOLD_US, *HOLDS_US):
            swap.swap_segments(compensation, hold_us=hold)
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": compensation,
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": .5,
                     "flux_predistortion_return_prefix_us": .5,
                     "flux_predistortion_recovery_us": RETURN_US,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.0,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        session_id = ("q3_tls_loss_sink_reset_" +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        references = _reference_arms(center)
        manifest = {
            "schema": "q3.tls-loss-sink-reset.v1", "status": "running",
            "session_id": session_id,
            "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
            "correction_json": str(correction),
            "correction_sha256": localizer.CORRECTION_SHA256,
            "scout_csv": str(scout), "selected": selected,
            "center_ghz": center, "control_ghz": control,
            "dc_lookup": {str(f): g for f, g in dc_lookup.items()},
            "realized_ghz": realized.tolist(), "plan": plan(),
            "references": references, "programs": specs,
        }
        protocol.checkpoint(path, manifest)
        print(f"[loss-sink-reset] manifest={path}", flush=True)
        raw_references = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            programs = {}
            for entry in specs:
                cfgs = confirm._condition_configs(base, entry, dc_lookup)
                programs[entry["name"]] = confirm.EightSiteSwapHoldProgram(
                    soccfg, cfgs, bundle.payload, bundle.loop)
            for reference in references:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, reference, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["preflight_complete"] = True
            protocol.checkpoint(path, manifest)

            def acquire_reference(reference):
                nonlocal axis
                reference["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                cfg = resident.arm_config(base, reference, dc_lookup)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program,
                    max(30.0, _block_timeout_s(cfg, REFERENCE_SHOTS)),
                    cfg, total_shots=REFERENCE_SHOTS)
                if len(records) != REFERENCE_SHOTS:
                    raise RuntimeError(f"{reference['name']}: incomplete reference IQ")
                raw_references[reference["name"]] = records
                raw_path = folder / f"{reference['name']}.npz"
                np.savez_compressed(raw_path, i=[r.i for r in records],
                                    q=[r.q for r in records])
                reference["raw_npz"] = str(raw_path)
                if reference["name"] == "ref_e_pre":
                    axis = resident.fit_axis(
                        resident.record_iq(raw_references["ref_g_pre"]),
                        resident.record_iq(records))
                    manifest["pre_readout_axis"] = axis
                    if not axis["valid"]:
                        raise RuntimeError("pre-run readout reference invalid")
                if axis is not None:
                    reference["excited_fraction_pre_axis"] = resident.classify(
                        records, axis)
                reference["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for reference in references[:4]:
                print(f"[loss-sink-reset] {reference['name']}", flush=True)
                acquire_reference(reference)
            ground_iq = resident.record_iq(raw_references["ref_g_pre"])
            excited_iq = resident.record_iq(raw_references["ref_e_pre"])
            if (resident.classify(raw_references["ref_transfer_e_pre"], axis) -
                    resident.classify(raw_references["ref_transfer_g_pre"], axis)
                    < .15):
                raise RuntimeError("park-prepared state fails transfer control")

            for entry in specs:
                entry["status"] = "acquiring"
                entry["acquisition_started_at_utc"] = (
                    datetime.now(timezone.utc).isoformat())
                protocol.checkpoint(path, manifest)
                print(f"[loss-sink-reset] {entry['name']} "
                      f"{entry['shots']} x 8", flush=True)
                start = time.monotonic()
                records = _run_program(
                    soc, programs[entry["name"]],
                    max(30.0, 8 * _block_timeout_s(base, entry["shots"])),
                    base, total_shots=entry["shots"])
                entry["acquisition_elapsed_s"] = time.monotonic() - start
                entry["acquisition_finished_at_utc"] = (
                    datetime.now(timezone.utc).isoformat())
                split = confirm.split_eight_records(
                    records, entry["order"], shots=entry["shots"])
                for condition in entry["conditions"]:
                    subset = split[condition["name"]]
                    raw_path = folder / f"{entry['name']}_{condition['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    condition["raw_npz"] = str(raw_path)
                    condition["excited_fraction_pre_axis"] = resident.classify(
                        subset, axis)
                    condition["projected_iq_pre_axis"] = _normalized_iq(
                        subset, axis, ground_iq, excited_iq)
                entry["score"] = score_reset({
                    condition["name"]: condition["excited_fraction_pre_axis"]
                    for condition in entry["conditions"]})
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for reference in references[4:]:
                print(f"[loss-sink-reset] {reference['name']}", flush=True)
                acquire_reference(reference)
            manifest["post_readout_score"] = resident.score_axis(
                axis, resident.record_iq(raw_references["ref_g_post"]),
                resident.record_iq(raw_references["ref_e_post"]))
            manifest["transfer_control"] = {
                phase: {"ground": resident.classify(
                            raw_references[f"ref_transfer_g_{phase}"], axis),
                        "excited": resident.classify(
                            raw_references[f"ref_transfer_e_{phase}"], axis)}
                for phase in ("pre", "post")}
            for result in manifest["transfer_control"].values():
                result["usable"] = resident.transfer_usable(
                    result["ground"], result["excited"])

            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**wide.parameters(),
                                     "output_suffix": "TLS_Loss_Sink_Reset_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                post_rows = swap.read_wide_scout(post_scout)
                manifest["post_selected"] = (
                    confirm.select_crowded_wide_candidate(
                        post_rows, preferred_center=center,
                        preferred_control_ghz=control))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            manifest["feature_stable"] = bool(
                "post_selected" in manifest and
                resident.feature_stable(selected, manifest["post_selected"]))
            manifest["control_usable"] = bool(
                manifest["post_readout_score"]["valid"] and
                all(item["usable"] for item in
                    manifest["transfer_control"].values()) and
                all(entry["score"]["control_usable"] for entry in specs))
            manifest["status"] = (
                "complete" if manifest["feature_stable"] and
                manifest["control_usable"] else "complete_controls_unstable")
            protocol.checkpoint(path, manifest)
            print(f"[loss-sink-reset] {manifest['status']}; "
                  f"manifest={path}", flush=True)
            return path
        except Exception as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            protocol.checkpoint(path, manifest)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root", default=str(localizer.DATA_ROOT))
    parser.add_argument("--correction-json")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
        return 0
    run(data_root=args.data_root, correction_json=args.correction_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
