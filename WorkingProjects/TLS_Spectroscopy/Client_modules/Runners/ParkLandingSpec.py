"""Probe q3's qubit frequency after the exact production flux round trip.

This is a standalone diagnostic, never a production-scan setting.  The full
40 us stateful return is retained while a 500 ns spectroscopy pulse starts
1, 5, or 25 us after return begins.  Each point is saved independently.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def _numbers(value):
    return [float(item.strip()) for item in str(value).split(",") if item.strip()]


def plan(environ=None):
    environ = os.environ if environ is None else environ
    timings = _numbers(environ.get("Q3_PARK_LANDING_TIMINGS_US", "1,5,25"))
    holds = _numbers(environ.get("Q3_PARK_LANDING_HOLDS_US", "2,100"))
    span = float(environ.get("Q3_PARK_LANDING_SPAN_MHZ", "30"))
    step = float(environ.get("Q3_PARK_LANDING_STEP_MHZ", "1.5"))
    shots = int(environ.get("Q3_PARK_LANDING_SHOTS", "150"))
    pulse_us = float(environ.get("Q3_PARK_LANDING_PULSE_US", "0.5"))
    gain = int(environ.get("Q3_PARK_LANDING_SPEC_GAIN", "7000"))
    recovery = 40.0
    if (not timings or len(timings) != len(set(timings))
            or any(not np.isfinite(x) or x < 1 or x > recovery for x in timings)):
        raise ValueError("return timings must be unique and within the 40 us recovery")
    if len(holds) != 2 or any(not np.isfinite(x) or x <= 0 for x in holds):
        raise ValueError("exactly two positive target holds are required")
    if not np.isfinite(span) or span <= 0 or not np.isfinite(step) or step <= 0:
        raise ValueError("spectroscopy span and step must be positive")
    count = int(round(2 * span / step))
    if count < 2 or count > 200 or not np.isclose(count * step, 2 * span):
        raise ValueError("spectroscopy grid must have 2..200 exact steps")
    if shots < 2 or not np.isfinite(pulse_us) or pulse_us < 0.1 or not 0 < gain < 32768:
        raise ValueError("shots, spectroscopy length, and gain are invalid")
    return {
        "return_prefix_us": timings,
        "target_holds_us": holds,
        "recovery_us": recovery,
        "probe_offsets_mhz": np.linspace(-span, span, count + 1).tolist(),
        "shots": shots,
        "pulse_us": pulse_us,
        "spec_gain": gain,
        "target_frequency_ghz": float(environ.get("Q3_PARK_LANDING_TARGET_GHZ", "4.055")),
    }


def result_rows(states, iq_i, iq_q, *, probe_frequency_ghz, return_prefix_us,
                park_frequency_ghz, target_frequency_ghz, holds_us, shots):
    states = np.asarray(states, dtype=float)
    iq_i = np.asarray(iq_i, dtype=float)
    iq_q = np.asarray(iq_q, dtype=float)
    if any(value.shape != (2 * len(holds_us), 2, shots)
           for value in (states, iq_i, iq_q)):
        raise ValueError("expected P0/P1 per hold, park/target, and all shots")
    rows = []
    for dc_index, (kind, frequency) in enumerate((
        ("park", park_frequency_ghz), ("target", target_frequency_ghz),
    )):
        for hold_index, hold in enumerate(holds_us):
            zero, one = 2 * hold_index, 2 * hold_index + 1
            p0 = float(np.mean(states[zero, dc_index]))
            p1 = float(np.mean(states[one, dc_index]))
            rows.append({
                "controller": "QICK", "qubit": "q3", "target_kind": kind,
                "target_frequency_ghz": float(frequency),
                "hold_us": float(hold), "return_prefix_us": float(return_prefix_us),
                "probe_frequency_ghz": float(probe_frequency_ghz),
                "shots": int(shots), "P0": p0, "P1": p1,
                "response": p1 - p0,
                "iq_I_P0": float(np.mean(iq_i[zero, dc_index])),
                "iq_Q_P0": float(np.mean(iq_q[zero, dc_index])),
                "iq_I_P1": float(np.mean(iq_i[one, dc_index])),
                "iq_Q_P1": float(np.mean(iq_q[one, dc_index])),
            })
    return rows


def _checkpoint(path, document):
    pending = path.with_suffix(".pending")
    pending.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.replace(pending, path)


def _write_rows(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(settings, *, correction_json, acknowledged_scans_stopped=False):
    if not acknowledged_scans_stopped:
        raise RuntimeError("confirm the QICK production scan has stopped")
    if str(os.environ.get("SET_YOKO", "")).strip().lower() in {"1", "true", "yes", "on"}:
        raise RuntimeError("SET_YOKO must be false")
    if str(os.environ.get("Q3_FLUX_TAIL_GAIN", "")).strip():
        raise RuntimeError("unset Q3_FLUX_TAIL_GAIN; use the pinned gain")
    correction_path = Path(correction_json)
    if not correction_path.is_file():
        raise FileNotFoundError("pass an existing explicit correction JSON")

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as five, TLSSpectroscopy as tls, Test as diagnostic,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import _integer_dc_grid
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import classify_payload_iq
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        PASSIVE_T1_RESET_US, prepare_reset_session,
    )

    five.install_scan_calibration(tls)
    if bool(getattr(tls, "SET_YOKO", False)):
        raise RuntimeError("SET_YOKO must be false")
    params = dict(five.P6_5PT_APPLES_TO_APPLES)
    dc_target, realized = _integer_dc_grid(
        params, np.asarray([settings["target_frequency_ghz"]], dtype=float),
    )
    park_gain = int(round(tls._baseline_dc_offset()))
    dc_vec = np.asarray([park_gain, int(dc_target[0])], dtype=np.int64)
    if np.any(np.abs(dc_vec) > 32767):
        raise ValueError("park or target exceeds signed DAC range")
    park_ghz = float(tls.BaseConfig["qubit_pi_freq"]) / 1000.0
    probe_ghz = park_ghz + np.asarray(settings["probe_offsets_mhz"]) / 1000.0
    correction = tls._load_correction(str(correction_path), tls.outerFolder)
    if float(tls.FLUX_TAIL_COMPENSATION_GAIN) != 1.0:
        raise RuntimeError("diagnostic requires effective correction gain 1.0")

    soc, soccfg = tls.makeProxy()
    if bool(soc.streamer.readout_running()):
        raise RuntimeError("QICK streamer is already running; stop the other acquisition")
    session = prepare_reset_session(
        "active", outer_folder=tls.outerFolder, qubit=tls.QUBIT,
        base_cfg=tls.BaseConfig, soc=soc, soccfg=soccfg,
        purpose="ParkLandingSpec",
    )
    session_id = "q3_park_landing_spec_" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    output_dir = Path(tls.outerFolder) / tls.QUBIT / session_id
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = output_dir / "manifest.json"
    manifest = {
        "schema": "q3.park-landing-spec.v1", "status": "running",
        "settings": settings, "correction_json": str(correction_path),
        "correction_sha256": hashlib.sha256(correction_path.read_bytes()).hexdigest(),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[4],
            text=True,
        ).strip(),
        "park_frequency_ghz": park_ghz,
        "target_frequency_ghz_realized": float(realized[0]),
        "park_dac": park_gain, "target_dac": int(dc_target[0]),
        "reset_calibration_path": str(session.calibration_output),
        "completed": [],
    }
    _checkpoint(manifest_path, manifest)
    base = dict(tls.BaseConfig)
    base.update({
        "shots": settings["shots"], "ff_gain_vec": dc_vec,
        "apply_flux_tail_compensation": True,
        "flux_tail_compensation": correction,
        "flux_fit_params": tls.FLUX_FIT_PARAMS,
        "relax_delay": PASSIVE_T1_RESET_US,
        "qubit_pulse_style": "arb",
        "flux_settle_time_us": 0.5,
        "readout_thermalization_us": 10.0,
        "opx_t1_3pt_gain_lookup": True,
        "opx_reverse_survival_order": False,
        "opx_diagnostic_condition_tags": True,
        "flux_predistortion_recovery_us": settings["recovery_us"],
        "flux_predistortion_overlap_payload_readout": True,
        "flux_predistortion_round_trip_mode": "stateful",
        "opx_t1_post_return_spec_gain": settings["spec_gain"],
        "opx_t1_post_return_spec_length_us": settings["pulse_us"],
    })
    base = session.apply(base)
    five.apply_verified_feedback_timing(base)
    try:
        for prefix in settings["return_prefix_us"]:
            for index, frequency in enumerate(probe_ghz):
                label = f"t{prefix:g}_f{index:03d}"
                print(f"[landing-spec] acquiring {label}", flush=True)
                cfg = dict(base)
                cfg["flux_predistortion_return_prefix_us"] = float(prefix)
                cfg["opx_t1_post_return_spec_freq_mhz"] = float(frequency) * 1000.0
                i_values, q_values, telemetry = diagnostic.acquire_t1_npoint_iq(
                    soc, soccfg, cfg, dc_gains=dc_vec,
                    delays_us=(10.0, 50.0, 200.0),
                    reference_hold_us=settings["target_holds_us"][0],
                    shots=settings["shots"], reset_scheme="opx_unbounded",
                    condition_holds_us=[
                        settings["target_holds_us"][0],
                        settings["target_holds_us"][0],
                        settings["target_holds_us"][1],
                        settings["target_holds_us"][1],
                    ],
                    condition_excitation_flags=[0, 1, 0, 1],
                    condition_names=["short_P0", "short_P1", "long_P0", "long_P1"],
                    prepare_excited_after_return=True,
                )
                if telemetry.get("condition_tag_mismatches", 0):
                    raise RuntimeError("QICK condition tags did not match decoded conditions")
                states = classify_payload_iq(
                    cfg, i_values, q_values, telemetry["read_length_cycles"],
                )
                rows = result_rows(
                    states, i_values, q_values,
                    probe_frequency_ghz=frequency, return_prefix_us=prefix,
                    park_frequency_ghz=park_ghz,
                    target_frequency_ghz=float(realized[0]),
                    holds_us=settings["target_holds_us"], shots=settings["shots"],
                )
                csv_path = output_dir / f"{label}.csv"
                raw_path = output_dir / f"{label}_raw.npz"
                _write_rows(csv_path, rows)
                np.savez_compressed(raw_path, states=states, iq_i=i_values, iq_q=q_values)
                manifest["completed"].append({
                    "label": label, "csv": str(csv_path), "raw_npz": str(raw_path),
                    "records": telemetry["records"],
                })
                _checkpoint(manifest_path, manifest)
                print(f"[landing-spec] saved {label} "
                      f"({len(manifest['completed'])}/{len(probe_ghz) * len(settings['return_prefix_us'])})",
                      flush=True)
        manifest["status"] = "complete"
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _checkpoint(manifest_path, manifest)
    return manifest_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--correction-json")
    parser.add_argument("--confirm-scans-stopped", action="store_true")
    args = parser.parse_args(argv)
    settings = plan()
    if args.plan:
        print(json.dumps({"hardware_access": False, **settings}, indent=2))
        return 0
    if not args.confirm_scans_stopped:
        parser.error("--run requires --confirm-scans-stopped")
    if not args.correction_json:
        parser.error("--run requires --correction-json")
    print(run(settings, correction_json=args.correction_json,
              acknowledged_scans_stopped=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
