"""Bounded q3 pump--probe check using the validated diagnostic reset policy.

At 4.110 GHz, compare +8 and -20 MHz pumps with immediately adjacent zero-drive
shams and a zero-drive null. Ground-state probes visit both target and park for
0.1 us. The same required-loop, half-gain feedback reset precedes and follows
every pump; the final probe uses a separately calibrated normal-gain readout.
Eight randomized rounds of 400 shots give 144 pump--probe blocks. Fresh half-
and normal-gain references are acquired before and after the blocks. This is a
matched pump-control experiment, not a measurement of TLS identity or reset
fidelity. Its optional program and runner do not alter production scan defaults.
"""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbePilot as pilot,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResetCheck as reference,
    TLSPumpProbeResetValidation as reset_validation,
)


def parameters():
    p = pilot.parameters(location_check=True)
    p.update({
        "repeats": 8,
        "order_seed": 20261003,
        "probe_states": ["g"],
        "probe_holds_us": [0.1],
        "probe_locations": ["target", "park"],
        "inter_shot_delay_us": 500.0,
    })
    return p


def plan():
    p = parameters()
    points = pilot.schedule(p)
    return {
        "hardware_access": False,
        "parameters": p,
        "acquisition_blocks": len(points),
        "pump_probe_shots": len(points) * p["shots"],
        "reference_shots": 4 * 4 * reference.SHOTS,
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


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
    import numpy as np

    p = parameters()
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
        full_grid = np.linspace(4.094, 4.110, 9)
        all_dc, all_realized = _integer_dc_grid(p, full_grid)
        dc_gain, realized_ghz = int(all_dc[-1]), float(all_realized[-1])
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

        session_id = "q3_pump_probe_confirmed_" + datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        points = [dict(entry, status="pending") for entry in pilot.schedule(p)]
        points += [dict(name="final_decision_reference", kind="reference", status="pending"),
                   dict(name="final_probe_reference", kind="reference", status="pending")]
        manifest = {
            "schema": "q3.pump-probe-confirmed.v1", "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "calibrating", "code_commit": os.environ["Q3_CODE_COMMIT"],
            "parameters": plan(), "points": points,
            "correction_json": str(correction),
            "correction_sha256": localizer.CORRECTION_SHA256,
            "realized_frequency_ghz": realized_ghz, "dc_gain": dc_gain,
            "classifier_sources": {"decision": "initial_decision_reference/calibration.json",
                                   "probe": "initial_probe_reference/calibration.json"},
        }
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
                        cal_cfg = (decision_cal_cfg if entry["name"] == "final_decision_reference"
                                   else verification_cal_cfg)
                        _, report = acquire_reference(entry["name"], cal_cfg)
                        if not report["accepted"]:
                            entry["result"] = report
                            manifest["final_references_accepted"] = False
                            raise RuntimeError("Final calibration reference rejected; "
                                               f"raw pump-probe data saved in {folder}")
                        return report
                    target = entry["target_index"]
                    if target != 0:
                        raise RuntimeError("Unexpected target index in confirmed pilot")
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
                    print(f"[pump-probe-confirmed] {entry['name']} {entry['pump_mode']} "
                          f"{entry['pump_detuning_mhz']:+g} MHz {entry['probe_location']} "
                          f"P={result['P_excited']:.3f}", flush=True)
                    return result

                pilot.collect_points(manifest, path, acquire)
        except BaseException as exc:
            manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            protocol.checkpoint(path, manifest)
            raise
        manifest["final_references_accepted"] = all(
            entry["result"]["accepted"] for entry in manifest["points"]
            if entry.get("kind") == "reference")
        protocol.checkpoint(path, manifest)
        print(f"[pump-probe-confirmed] complete; final references accepted="
              f"{manifest['final_references_accepted']}; summary={summary_path}", flush=True)
        return path


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
