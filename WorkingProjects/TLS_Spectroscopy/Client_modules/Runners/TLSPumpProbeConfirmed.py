"""Bounded q3 pump--probe check using the validated diagnostic reset policy.

At 4.110 GHz, compare +8 and -20 MHz pumps with immediately adjacent zero-drive
shams and a zero-drive null. Ground-state probes visit both target and park for
0.1 us. The same required-loop, half-gain feedback reset precedes and follows
every pump; the final probe uses a separately calibrated normal-gain readout.
Eight randomized rounds of 400 shots give 144 pump--probe blocks. The
--transfer-check follow-up keeps the same pump conditions and locations but
uses a 2-us probe with both ground and excited preparations (288 blocks). Fresh
half- and normal-gain references are acquired before and after either stage.
These are matched pump-control experiments, not measurements of TLS identity or
reset fidelity. The optional program and runner do not alter production scans.

--relocalize uses the same reset, readout, and flux-return sequence with the
microwave pump disabled. It screens 3.900..4.300 GHz at 2-MHz spacing, first
forward then backward, comparing nearby-in-time excited 2/10-us probes with a
ground 10-us control at each target. This is a loss-feature localizer; its
model frequency is not an independently measured TLS frequency. A narrow
feature may lie between screening points and needs a denser follow-up.

--fine-localize applies that follow-up to the independent-pass candidate near
4.045 GHz: 4.036..4.054 GHz in 0.5-MHz steps, four alternating-direction
passes, and 400 shots for each of the same three pump-off probe conditions.
This resolves the candidate and both flanks before selecting a pump coordinate.

--secondary-localize checks the other independent-pass broadband candidate
near 4.114..4.118 GHz after the 4.045-GHz peak weakened in the fine scan.
It uses the same pump-off protocol over 4.108..4.122 GHz at 0.5-MHz spacing.

--drift-track revisits 4.094..4.122 GHz at 1-MHz spacing over twelve
alternating-direction passes after the strongest loss shifted below 4.114 GHz.
It establishes the passive position and time variation before a pump test.

--guarded-scout visits the same range in two passes, with paired decision and
probe references after each ten target-frequency trios. A rejected reference
stops the scout and retains all preceding raw IQ; this limits the chance that
intermittent calibration contrast contaminates an entire long drift scan.

--direct-pump makes the small on-target test at the latest 4.110-GHz loss
candidate: an on-model-frequency 15-us microwave pump versus immediately
adjacent same-frequency zero-drive shams. Ground/excited 2/10-us probes and a
zero-drive null help distinguish survival from direct excitation and drift.
Half- and normal-gain references bracket the run and its midpoint.
"""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbePilot as pilot,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResetCheck as reference,
    TLSPumpProbeResetValidation as reset_validation,
)


def parameters(*, transfer_check=False, relocalize=False, fine_localize=False,
               secondary_localize=False, drift_track=False, guarded_scout=False,
               direct_pump=False):
    if sum((transfer_check, relocalize, fine_localize,
            secondary_localize, drift_track, guarded_scout, direct_pump)) > 1:
        raise ValueError("Choose only one pump-probe follow-up stage")
    p = pilot.parameters(location_check=True)
    p.update({
        "repeats": 8,
        "order_seed": 20261003,
        "probe_states": ["g"],
        "probe_holds_us": [0.1],
        "probe_locations": ["target", "park"],
        "inter_shot_delay_us": 500.0,
    })
    if transfer_check:
        p.update(order_seed=20261004, probe_states=["g", "e"],
                 probe_holds_us=[2.0])
    if relocalize:
        p.update(target_frequency_ghz=[round(3.9 + 0.002 * i, 3) for i in range(201)],
                 freq_step_mhz=2.0, shots=250, repeats=2, order_seed=20261005,
                 probe_states=["g", "e"], probe_holds_us=[2.0, 10.0],
                 probe_locations=["target"], pump_detunings_mhz=[0.0],
                 bracket_each=False)
    if fine_localize:
        p.update(target_frequency_ghz=[round(4.036 + 0.0005 * i, 4) for i in range(37)],
                 freq_step_mhz=0.5, shots=400, repeats=4, order_seed=20261006,
                 probe_states=["g", "e"], probe_holds_us=[2.0, 10.0],
                 probe_locations=["target"], pump_detunings_mhz=[0.0],
                 bracket_each=False)
    if secondary_localize:
        p.update(target_frequency_ghz=[round(4.108 + 0.0005 * i, 4) for i in range(29)],
                 freq_step_mhz=0.5, shots=400, repeats=4, order_seed=20261007,
                 probe_states=["g", "e"], probe_holds_us=[2.0, 10.0],
                 probe_locations=["target"], pump_detunings_mhz=[0.0],
                 bracket_each=False)
    if drift_track or guarded_scout:
        p.update(target_frequency_ghz=[round(4.094 + 0.001 * i, 3) for i in range(29)],
                 freq_step_mhz=1.0, shots=250,
                 repeats=2 if guarded_scout else 12,
                 order_seed=20261009 if guarded_scout else 20261008,
                 probe_states=["g", "e"], probe_holds_us=[2.0, 10.0],
                 probe_locations=["target"], pump_detunings_mhz=[0.0],
                 bracket_each=False)
    if direct_pump:
        p.update(target_frequency_ghz=[4.110], shots=400, repeats=4,
                 order_seed=20261010, probe_states=["g", "e"],
                 probe_holds_us=[2.0, 10.0], probe_locations=["target"],
                 pump_detunings_mhz=[0.0], pump_gain=3000, pump_us=15.0,
                 bracket_each=True)
    return p


def scan_schedule(p, *, reference_interval_targets=None):
    """Keep each loss/reference trio local in time; reverse the second pass."""
    import random

    rng = random.Random(p["order_seed"])
    points = []
    for repeat in range(p["repeats"]):
        targets = range(len(p["target_frequency_ghz"]))
        if repeat % 2:
            targets = reversed(targets)
        for target_count, target in enumerate(targets, start=1):
            probes = [("e", 2.0), ("e", 10.0), ("g", 10.0)]
            rng.shuffle(probes)
            comparison_id = f"pass_{repeat}_target_{target:04d}"
            for state, hold in probes:
                points.append({
                    "name": f"point_{len(points):04d}", "repeat": repeat,
                    "target_index": target, "pump_mode": "sham",
                    "pump_detuning_mhz": 0.0, "probe_state": state,
                    "pump_gain": 0, "probe_us": hold,
                    "additional_recovery_us": 0.0, "probe_location": "target",
                    "control_position": "scan",
                    "test_condition": f"{state}_{hold:g}us",
                    "comparison_id": comparison_id,
                })
            if (reference_interval_targets is not None
                    and (target_count % reference_interval_targets == 0
                         or target_count == len(p["target_frequency_ghz"]))
                    and (repeat, target_count) !=
                    (p["repeats"] - 1, len(p["target_frequency_ghz"]))):
                for role in ("decision", "probe"):
                    points.append({
                        "name": f"checkpoint_{repeat:02d}_{target_count:02d}_{role}_reference",
                        "kind": "reference", "reference_type": role,
                        "repeat": repeat, "after_targets": target_count,
                    })
    return points


def direct_pump_schedule(p):
    """Keep pump/sham trios adjacent and verify both gains at the midpoint."""
    if p["repeats"] < 2 or p["repeats"] % 2:
        raise ValueError("direct pump requires an even number of rounds")
    base = pilot.schedule(p)
    midpoint = p["repeats"] // 2
    points = []
    for index, entry in enumerate(base):
        points.append(entry)
        if (entry["repeat"] == midpoint - 1
                and (index == len(base) - 1 or base[index + 1]["repeat"] == midpoint)):
            for role in ("decision", "probe"):
                points.append({
                    "name": f"checkpoint_direct_pump_{role}_reference",
                    "kind": "reference", "reference_type": role,
                    "after_rounds": midpoint,
                })
    return points


def acquire_accepted_reference_pair(acquire, decision_cfg, probe_cfg, *,
                                    attempts, wait_for_attempt, record_attempt):
    """Save every attempt and return only a pair passing the unchanged guard."""
    if attempts < 1:
        raise ValueError("at least one calibration attempt is required")
    for index in range(attempts):
        wait_for_attempt(index)
        name = f"initial_decision_attempt_{index + 1:02d}"
        decision_bundle, decision_report = acquire(name, decision_cfg)
        record = {"attempt": index + 1, "decision": decision_report}
        if decision_report["accepted"]:
            name = f"initial_probe_attempt_{index + 1:02d}"
            probe_bundle, probe_report = acquire(name, probe_cfg)
            record["probe"] = probe_report
        record_attempt(record)
        if decision_report["accepted"] and record.get("probe", {}).get("accepted"):
            return decision_bundle, probe_bundle, decision_report, probe_report
    raise RuntimeError("No accepted decision/probe reference pair after "
                       f"{attempts} attempts")


def plan(*, transfer_check=False, relocalize=False, fine_localize=False,
         secondary_localize=False, drift_track=False, guarded_scout=False,
         direct_pump=False):
    p = parameters(transfer_check=transfer_check, relocalize=relocalize,
                   fine_localize=fine_localize,
                   secondary_localize=secondary_localize,
                   drift_track=drift_track, guarded_scout=guarded_scout,
                   direct_pump=direct_pump)
    scan_mode = relocalize or fine_localize or secondary_localize or drift_track or guarded_scout
    points = (scan_schedule(p, reference_interval_targets=10 if guarded_scout else None)
              if scan_mode else direct_pump_schedule(p) if direct_pump else pilot.schedule(p))
    checkpoint_refs = sum(x.get("kind") == "reference" for x in points)
    data_blocks = len(points) - checkpoint_refs
    return {
        "hardware_access": False,
        "transfer_check": bool(transfer_check),
        "relocalize": bool(relocalize),
        "fine_localize": bool(fine_localize),
        "secondary_localize": bool(secondary_localize),
        "drift_track": bool(drift_track),
        "guarded_scout": bool(guarded_scout),
        "direct_pump": bool(direct_pump),
        "microwave_pump_enabled": not scan_mode,
        "parameters": p,
        "acquisition_blocks": data_blocks,
        "pump_probe_shots": data_blocks * p["shots"],
        "checkpoint_references": checkpoint_refs,
        "reference_shots": (4 + checkpoint_refs) * 4 * reference.SHOTS,
        "reference_shots_excludes_retries": bool(direct_pump),
        "initial_reference_attempts_max": 12 if direct_pump else 1,
        "initial_reference_spacing_s": 20.0 if direct_pump else None,
        "decision_readout_fraction": 0.5,
        "probe_readout_fraction": 1.0,
        "reset_policy": "required_loop_before_and_after_pump",
        "timing_profile": reset_validation.PROFILE,
        "note": __doc__,
    }


def point_config(cfg, *, ff_gain, pump_frequency_mhz, pump_gain, pump_us,
                 probe_us, arm, recovery_us, shots):
    """Reproduce the native saturation API's validated run fields locally."""
    import numpy as np
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        quantize_signed_dac_gain,
    )

    arm = str(arm).strip().lower()
    if arm not in ("pump", "no_pump"):
        raise ValueError("TLS saturation arm must be 'pump' or 'no_pump'")
    values = np.asarray([pump_frequency_mhz, pump_gain, pump_us, probe_us, recovery_us], dtype=float)
    if (not np.all(np.isfinite(values)) or pump_gain <= 0 or pump_us <= 0
            or probe_us <= 0 or recovery_us < 0 or int(shots) <= 0):
        raise ValueError("invalid saturation drive, hold, recovery or shot count")
    run_cfg = dict(cfg)
    run_cfg.update({
        "opx_reset_scheme": "opx_unbounded",
        "opx_saturation_shots": int(shots),
        "opx_saturation_arm": arm,
        "opx_saturation_pump_freq_mhz": float(pump_frequency_mhz),
        "opx_saturation_pump_gain": int(round(float(pump_gain))),
        "opx_saturation_pump_us": float(pump_us),
        "opx_saturation_probe_us": float(probe_us),
        "opx_saturation_recovery_us": float(recovery_us),
        "ff_gain": quantize_signed_dac_gain(ff_gain),
        "ff_hold": max(float(pump_us), float(probe_us)),
        "do_ff": True,
        "opx_resident_dmem_stream": True,
    })
    return run_cfg


def acquire_records(soc, soccfg, run_cfg):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeConfirmedProgram import (
        ConfirmedPumpProbeProgram,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        _block_timeout_s, _run_program, flux_predistortion_telemetry, runtime_bundle,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
        AcquisitionTimeout,
    )

    bundle = runtime_bundle(run_cfg)
    shots = int(run_cfg["opx_saturation_shots"])
    program = ConfirmedPumpProbeProgram(soccfg, run_cfg, bundle.payload, bundle.loop)
    read_cycles = int(program.us2cycles(run_cfg["read_length"], ro_ch=run_cfg["ro_chs"][0]))
    try:
        records = _run_program(soc, program, _block_timeout_s(run_cfg, shots), run_cfg,
                               total_shots=shots)
    except AcquisitionTimeout as exc:
        exc.read_length_cycles = read_cycles
        raise
    telemetry = {
        "shots": shots, "records": len(records), "resident_stream": True,
        "order": "shot_arm", "read_length_cycles": read_cycles,
        "reset_reference_guard_us": float(program._saturation_reset_guard_us),
        **flux_predistortion_telemetry(program),
    }
    return records, telemetry


def save_probe_iq(path, records, read_cycles, verification_bundle):
    """Persist raw IQ before evaluating shot count or either classifier axis."""
    import numpy as np

    i_raw = np.asarray([r.final_i for r in records], dtype=np.int64)
    q_raw = np.asarray([r.final_q for r in records], dtype=np.int64)
    np.savez_compressed(path, i_raw=i_raw, q_raw=q_raw,
                        i=i_raw / read_cycles, q=q_raw / read_cycles,
                        read_length_cycles=int(read_cycles))
    result = {"raw_npz": str(path), "shots": len(records),
              "I_mean": float(np.mean(i_raw / read_cycles)) if len(records) else float("nan"),
              "Q_mean": float(np.mean(q_raw / read_cycles)) if len(records) else float("nan")}
    for context in ("payload", "loop"):
        fit = getattr(verification_bundle, context)
        excited = fit.project(i_raw, q_raw) > fit.excited_threshold
        result[f"P_excited_{context}"] = float(np.mean(excited)) if len(records) else float("nan")
        result[f"excited_count_{context}"] = int(np.sum(excited))
    # Keep the pilot's payload classifier as the primary population observable.
    result["P_excited"] = result["P_excited_payload"]
    return result


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        transfer_check=False, relocalize=False, fine_localize=False,
        secondary_localize=False, drift_track=False, guarded_scout=False,
        direct_pump=False):
    import numpy as np

    p = parameters(transfer_check=transfer_check, relocalize=relocalize,
                   fine_localize=fine_localize,
                   secondary_localize=secondary_localize,
                   drift_track=drift_track, guarded_scout=guarded_scout,
                   direct_pump=direct_pump)
    scan_mode = relocalize or fine_localize or secondary_localize or drift_track or guarded_scout
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    with localizer.scan_environment(correction):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as five, TLSSpectroscopy as tls,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
            _integer_dc_grid,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
            AcquisitionTimeout,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import (
            q3_benchmark_settings,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
            acquire_calibration, save_calibration, save_raw_calibration,
            validate_confident_calibration,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
            build_calibration_config,
        )

        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("Park calibration differs from the planned q3 configuration")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        if scan_mode:
            dc_vec, realized_vec = _integer_dc_grid(p, np.asarray(p["target_frequency_ghz"]))
        else:
            full_grid = np.linspace(4.094, 4.110, 9)
            all_dc, all_realized = _integer_dc_grid(p, full_grid)
            dc_vec, realized_vec = all_dc[-1:], all_realized[-1:]
        compensation = tls._load_correction(str(correction), str(data_root))
        frequency = next(float(tls.BaseConfig[key]) for key in
                         ("reset_pi_freq", "qubit_pi_freq", "qubit_freq")
                         if tls.BaseConfig.get(key) is not None)
        normal_gain = int(tls.BaseConfig["read_pulse_gain"])
        if normal_gain != 1880:
            raise RuntimeError(f"Expected q3 normal readout gain 1880; got {normal_gain}")
        decision_base = dict(tls.BaseConfig, read_pulse_gain=normal_gain // 2)
        decision_cal_cfg = reference.profile_config(
            build_calibration_config(decision_base, frequency), reset_validation.PROFILE)
        verification_cal_cfg = dict(decision_cal_cfg, read_pulse_gain=normal_gain)

        prefix = ("q3_pump_probe_direct_pump_" if direct_pump else
                  "q3_pump_probe_guarded_scout_" if guarded_scout else
                  "q3_pump_probe_drift_track_" if drift_track else
                  "q3_pump_probe_secondary_localize_" if secondary_localize else
                  "q3_pump_probe_fine_localize_" if fine_localize else
                  "q3_pump_probe_relocalize_" if relocalize else
                  "q3_pump_probe_transfer_check_" if transfer_check else
                  "q3_pump_probe_confirmed_")
        session_id = prefix + datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        schedule = (scan_schedule(p, reference_interval_targets=10 if guarded_scout else None)
                    if scan_mode else direct_pump_schedule(p) if direct_pump else pilot.schedule(p))
        points = [dict(entry, status="pending") for entry in schedule]
        points += [dict(name="final_decision_reference", kind="reference",
                        reference_type="decision", status="pending"),
                   dict(name="final_probe_reference", kind="reference",
                        reference_type="probe", status="pending")]
        manifest = {
            "schema": "q3.pump-probe-confirmed.v1", "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "calibrating", "code_commit": os.environ["Q3_CODE_COMMIT"],
            "transfer_check": bool(transfer_check),
            "relocalize": bool(relocalize),
            "fine_localize": bool(fine_localize),
            "secondary_localize": bool(secondary_localize),
            "drift_track": bool(drift_track),
            "guarded_scout": bool(guarded_scout),
            "direct_pump": bool(direct_pump),
            "parameters": plan(transfer_check=transfer_check, relocalize=relocalize,
                               fine_localize=fine_localize,
                               secondary_localize=secondary_localize,
                               drift_track=drift_track,
                               guarded_scout=guarded_scout,
                               direct_pump=direct_pump),
            "points": points,
            "correction_json": str(correction),
            "correction_sha256": localizer.CORRECTION_SHA256,
            "realized_frequency_ghz": (realized_vec.tolist() if scan_mode
                                       else float(realized_vec[0])),
            "dc_gain": dc_vec.tolist() if scan_mode else int(dc_vec[0]),
            "classifier_sources": ({"decision": None, "probe": None} if direct_pump else
                                   {"decision": "initial_decision_reference/calibration.json",
                                    "probe": "initial_probe_reference/calibration.json"}),
        }
        if direct_pump:
            manifest["initial_reference_attempts"] = []
        protocol.checkpoint(path, manifest)
        print(f"[pump-probe-confirmed] manifest={path}", flush=True)
        try:
            soc, soccfg = tls.makeProxy()

            def acquire_reference(name, cal_cfg):
                out = folder / name
                out.mkdir(exist_ok=False)
                (out / "config.json").write_text(
                    json.dumps(cal_cfg, default=pilot.json_default, indent=2) + "\n", encoding="utf-8")
                bundle, raw = acquire_calibration(
                    soc, soccfg, cal_cfg, shots=reference.SHOTS,
                    **q3_benchmark_settings().calibration_options(),
                    metadata={"purpose": "TLSPumpProbeConfirmed", "stage": name,
                              "session_id": session_id},
                )
                save_calibration(out / "calibration.json", bundle)
                save_raw_calibration(out / "calibration_raw.npz", raw)
                return bundle, dict(reference.calibration_report(bundle), output=str(out))

            if direct_pump:
                retry_start = time.monotonic()

                def record_attempt(record):
                    manifest["initial_reference_attempts"].append(record)
                    protocol.checkpoint(path, manifest)
                    print("[pump-probe-confirmed] initial reference attempt "
                          f"{record['attempt']}: decision="
                          f"{record['decision']['accepted']} probe="
                          f"{record.get('probe', {}).get('accepted', 'skipped')}", flush=True)

                decision_bundle, probe_bundle, decision_report, probe_report = (
                    acquire_accepted_reference_pair(
                        acquire_reference, decision_cal_cfg, verification_cal_cfg,
                        attempts=12,
                        wait_for_attempt=lambda index: reference.wait_for_reference_slot(
                            retry_start, index * 20.0),
                        record_attempt=record_attempt,
                    ))
                manifest["classifier_sources"] = {
                    "decision": Path(decision_report["output"]).name + "/calibration.json",
                    "probe": Path(probe_report["output"]).name + "/calibration.json",
                }
                manifest["initial_decision_reference"] = decision_report
                manifest["initial_probe_reference"] = probe_report
                protocol.checkpoint(path, manifest)
                validate_confident_calibration(decision_bundle)
                validate_confident_calibration(probe_bundle)
            else:
                decision_bundle, decision_report = acquire_reference(
                    "initial_decision_reference", decision_cal_cfg)
                manifest["initial_decision_reference"] = decision_report
                protocol.checkpoint(path, manifest)
                validate_confident_calibration(decision_bundle)
                probe_bundle, probe_report = acquire_reference(
                    "initial_probe_reference", verification_cal_cfg)
                manifest["initial_probe_reference"] = probe_report
                protocol.checkpoint(path, manifest)
                validate_confident_calibration(probe_bundle)

            cfg = reset_validation.runtime_config(decision_base, decision_bundle.to_dict(), frequency)
            cfg.update({
                "shots": p["shots"], "opx_inter_shot_delay_us": p["inter_shot_delay_us"],
                "opx_saturation_reset_before_pump": True,
                "opx_diagnostic_probe_readout_gain": normal_gain,
                "apply_flux_tail_compensation": True,
                "flux_tail_compensation": compensation,
                "flux_fit_params": tls.FLUX_FIT_PARAMS,
                "qubit_pulse_style": "arb", "flux_settle_time_us": 0.5,
                "flux_predistortion_return_prefix_us": 0.5,
                "flux_predistortion_recovery_us": p["return_us"],
                "flux_predistortion_overlap_payload_readout": False,
                "flux_predistortion_round_trip_mode": "stateful",
                "readout_thermalization_us": 10.0,
            })
            (folder / "config.json").write_text(
                json.dumps(cfg, default=pilot.json_default, indent=2) + "\n", encoding="utf-8")
            manifest["status"] = "running"
            protocol.checkpoint(path, manifest)
            summary_path = folder / "summary.csv"
            with summary_path.open("w", newline="", encoding="utf-8") as stream:
                writer = None

                def acquire(entry):
                    nonlocal writer
                    if entry.get("kind") == "reference":
                        cal_cfg = (decision_cal_cfg if entry["reference_type"] == "decision"
                                   else verification_cal_cfg)
                        _, report = acquire_reference(entry["name"], cal_cfg)
                        if not report["accepted"]:
                            entry["result"] = report
                            final = entry["name"].startswith("final_")
                            manifest["final_references_accepted" if final else
                                     "checkpoint_references_accepted"] = False
                            raise RuntimeError(f"{'Final' if final else 'Checkpoint'} "
                                               "calibration reference rejected; "
                                               f"raw pump-probe data saved in {folder}")
                        return report
                    target = entry["target_index"]
                    if not scan_mode and target != 0:
                        raise RuntimeError("Unexpected target index in confirmed pilot")
                    dc_gain = int(dc_vec[target])
                    realized_ghz = float(realized_vec[target])
                    pump_frequency_mhz = realized_ghz * 1000 + entry["pump_detuning_mhz"]
                    drive = pilot.drive_settings(entry, p)
                    point_cfg = point_config(
                        {**cfg, "opx_saturation_probe_state": entry["probe_state"],
                         "opx_saturation_probe_location": entry["probe_location"]},
                        ff_gain=dc_gain, pump_frequency_mhz=pump_frequency_mhz,
                        pump_gain=drive["pump_gain"], pump_us=p["pump_us"],
                        probe_us=entry["probe_us"], arm=drive["arm"],
                        recovery_us=drive["recovery_us"], shots=p["shots"],
                    )
                    raw_path = folder / f"{entry['name']}.npz"
                    try:
                        records, telemetry = acquire_records(soc, soccfg, point_cfg)
                    except AcquisitionTimeout as exc:
                        save_probe_iq(folder / f"{entry['name']}_partial.npz",
                                      exc.partial_records, exc.read_length_cycles, probe_bundle)
                        entry["partial_acquisition"] = {
                            "raw_npz": str(folder / f"{entry['name']}_partial.npz"),
                            "completed_shots": exc.completed_shots,
                            "recovered_records": len(exc.partial_records),
                        }
                        raise
                    result = save_probe_iq(raw_path, records,
                                           telemetry["read_length_cycles"], probe_bundle)
                    if len(records) != p["shots"]:
                        raise RuntimeError(f"Incomplete IQ block saved to {raw_path}")
                    result.update({
                        "target_frequency_ghz": p["target_frequency_ghz"][target],
                        "realized_frequency_ghz": realized_ghz,
                        "dc_gain": dc_gain, "pump_frequency_mhz": pump_frequency_mhz,
                        "effective_pump_gain": entry["pump_gain"],
                        "probe_dc_gain": (int(cfg["ff_park_gain"])
                                          if entry["probe_location"] == "park" else dc_gain),
                    })
                    row = {key: entry[key] for key in (
                        "name", "repeat", "target_index", "pump_mode",
                        "pump_detuning_mhz", "probe_state", "probe_us",
                        "additional_recovery_us", "probe_location", "control_position",
                        "test_condition", "comparison_id", "started_at")}
                    row.update(result)
                    if writer is None:
                        writer = csv.DictWriter(stream, fieldnames=list(row))
                        writer.writeheader()
                    writer.writerow(row)
                    stream.flush()
                    result["telemetry"] = telemetry
                    print(f"[pump-probe-confirmed] {entry['name']} "
                          f"{result['target_frequency_ghz']:.3f} GHz {entry['pump_mode']} "
                          f"{entry['pump_detuning_mhz']:+g} MHz {entry['probe_location']} "
                          f"{entry['probe_state']} {entry['probe_us']:g} us "
                          f"P={result['P_excited']:.3f}", flush=True)
                    return result

                pilot.collect_points(manifest, path, acquire)
        except BaseException as exc:
            manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            protocol.checkpoint(path, manifest)
            raise
        manifest["final_references_accepted"] = all(
            entry["result"]["accepted"] for entry in manifest["points"]
            if entry["name"].startswith("final_") and entry.get("kind") == "reference")
        if guarded_scout or direct_pump:
            manifest["checkpoint_references_accepted"] = all(
                entry["result"]["accepted"] for entry in manifest["points"]
                if entry.get("kind") == "reference" and
                not entry["name"].startswith("final_"))
        protocol.checkpoint(path, manifest)
        print(f"[pump-probe-confirmed] complete; final references accepted="
              f"{manifest['final_references_accepted']}; summary={summary_path}", flush=True)
        return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument("--transfer-check", action="store_true",
                       help="compare ground and excited 2-us target/park probes")
    stage.add_argument("--relocalize", action="store_true",
                       help="screen 3.9..4.3 GHz for a current loss feature without microwave pumping")
    stage.add_argument("--fine-localize", action="store_true",
                       help="resolve the 4.045-GHz candidate at 0.5-MHz spacing without pumping")
    stage.add_argument("--secondary-localize", action="store_true",
                       help="check the 4.114..4.118-GHz candidate at 0.5-MHz spacing without pumping")
    stage.add_argument("--drift-track", action="store_true",
                       help="track pump-off loss over 4.094..4.122 GHz across twelve passes")
    stage.add_argument("--guarded-scout", action="store_true",
                       help="two-pass pump-off scout with periodic calibration references")
    stage.add_argument("--direct-pump", action="store_true",
                       help="compare on-target 4.110-GHz pump with adjacent zero-drive shams")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(transfer_check=args.transfer_check,
                              relocalize=args.relocalize,
                              fine_localize=args.fine_localize,
                              secondary_localize=args.secondary_localize,
                              drift_track=args.drift_track,
                              guarded_scout=args.guarded_scout,
                              direct_pump=args.direct_pump), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            transfer_check=args.transfer_check, relocalize=args.relocalize,
            fine_localize=args.fine_localize,
            secondary_localize=args.secondary_localize,
            drift_track=args.drift_track,
            guarded_scout=args.guarded_scout,
            direct_pump=args.direct_pump)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
