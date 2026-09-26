"""Bracket short-delay measurements with the original q3 localizer protocol.

After the September 26 target check, the loss feature appeared near 4.106 GHz
instead of 4.098 GHz. The eight-delay scan also had nonmonotonic populations
and used references from its first program chunk. This A-B-A diagnostic uses
one reset calibration and one unchunked program per arm, with a shared 25-us
survival condition. It tests reproducibility/protocol dependence before pumping.

Run only after the other q3 acquisition has stopped. All arms retain the
2-us reference, 40-us return, native correction, and park readout. Each result
is checkpointed, including IQ centroids; any acquisition error stops the series.

Use --history-check for the follow-up after the A-B-A result: compare both
protocols at 10 and 500 us of park idle after payload readout AND feedback reset.
The eight arms repeat the four combinations in reverse order, using one shared
calibration. The 40-us pre-readout return stays fixed. This tests dependence on
measurement history/duty cycle; it cannot by itself identify flux memory versus
bath dynamics, and the longer post-reset idle can change preparation fidelity.
Use the saved P0/P1 and IQ references to assess that change.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
)


def arms(*, history_check=False):
    if history_check:
        combinations = [
            ("A", [25.0, 60.0, 100.0], 10.0),
            ("B", [4.0, 8.0, 25.0], 10.0),
            ("A", [25.0, 60.0, 100.0], 500.0),
            ("B", [4.0, 8.0, 25.0], 500.0),
        ]
        return [
            {"name": f"{i + 1:02d}_{name}_idle{idle:g}us",
             "delays_us": list(delays), "inter_shot_delay_us": idle}
            for i, (name, delays, idle) in enumerate(
                combinations + list(reversed(combinations)))
        ]
    return [
        {"name": "A_before", "delays_us": [25.0, 60.0, 100.0]},
        {"name": "B_short", "delays_us": [4.0, 8.0, 25.0]},
        {"name": "A_after", "delays_us": [25.0, 60.0, 100.0]},
    ]


def arm_config(base, entry):
    """Apply park-idle timing after reset calibration defaults, per arm."""
    cfg = dict(base)
    if "inter_shot_delay_us" in entry:
        cfg["opx_inter_shot_delay_us"] = float(entry["inter_shot_delay_us"])
    return cfg


def parameters():
    return {**localizer.parameters(), "freq_min_ghz": 4.080,
            "freq_max_ghz": 4.125, "freq_step_mhz": 0.5,
            "shots_per_condition": 500}


def checkpoint(path, document):
    """Publish atomically, tolerating brief Windows/NAS replacement conflicts.

    Retry only the rename, never acquisition. A persistent denial still stops
    the run and leaves the old manifest plus the new .pending JSON intact.
    """
    path = Path(path)
    pending = path.with_suffix(".pending")
    pending.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    for delay in (0.05, 0.1, 0.2, 0.4, 0.8, 1.0, 1.0, None):
        try:
            os.replace(pending, path)
            return
        except PermissionError:
            if delay is None:
                raise
            print(f"[checkpoint] Access conflict replacing {path.name}; "
                  f"retrying in {delay:g} s", flush=True)
            time.sleep(delay)


def collect_arms(manifest, path, acquire):
    """Save every completed arm; do not continue after failure or interruption."""
    for entry in manifest["arms"]:
        entry.update(status="acquiring", started_at=datetime.now(timezone.utc).isoformat())
        checkpoint(path, manifest)
        try:
            csv_path = acquire(entry)
            entry.update(status="complete", full_csv=str(csv_path),
                         completed_at=datetime.now(timezone.utc).isoformat())
            checkpoint(path, manifest)
        except BaseException as exc:
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            manifest["status"] = "failed"
            checkpoint(path, manifest)
            raise
    manifest["status"] = "complete"
    checkpoint(path, manifest)


def run(*, data_root=localizer.DATA_ROOT, correction_json=None, history_check=False):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    with localizer.scan_environment(correction):
        import numpy as np
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as five, TLSSpectroscopy as tls,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
            _integer_dc_grid, _target_frequency_grid_ghz,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import T15PointVsFlux
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
            PASSIVE_T1_RESET_US, prepare_reset_session,
        )

        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("Park calibration differs from the planned q3 configuration.")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        p = parameters()
        frequencies = _target_frequency_grid_ghz(p)
        dc_vec, realized = _integer_dc_grid(p, frequencies)
        compensation = tls._load_correction(str(correction), str(data_root))
        kind = "history" if history_check else "protocol"
        session_id = f"q3_pump_probe_{kind}_check_" + datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        session_dir = data_root / "q3" / session_id
        session_dir.mkdir(parents=True, exist_ok=False)
        manifest_path = session_dir / "manifest.json"
        manifest = {
            "schema": "q3.pump-probe-protocol-check.v1", "session_id": session_id,
            "history_check": history_check,
            "status": "calibrating", "created_at": datetime.now(timezone.utc).isoformat(),
            "code_commit": os.environ["Q3_CODE_COMMIT"],
            "correction_json": str(correction), "correction_sha256": localizer.CORRECTION_SHA256,
            "parameters": p, "target_frequency_ghz": frequencies.tolist(),
            "realized_frequency_ghz": realized.tolist(), "dc_vec": dc_vec.tolist(),
            "arms": [dict(arm, status="pending") for arm in arms(history_check=history_check)],
        }
        checkpoint(manifest_path, manifest)
        print(f"[protocol-check] manifest={manifest_path}", flush=True)
        try:
            soc, soccfg = tls.makeProxy()
            reset = prepare_reset_session(
                "active", outer_folder=str(data_root), qubit="q3", base_cfg=tls.BaseConfig,
                soc=soc, soccfg=soccfg, purpose="TLSPumpProbeProtocolCheck",
            )
            manifest["reset_calibration_path"] = str(reset.calibration_output)
            base = dict(tls.BaseConfig)
            base.update({
                "shots": p["shots_per_condition"], "ff_gain_vec": dc_vec,
                "apply_flux_tail_compensation": True, "flux_tail_compensation": compensation,
                "flux_fit_params": tls.FLUX_FIT_PARAMS, "relax_delay": PASSIVE_T1_RESET_US,
                "qubit_pulse_style": "arb", "flux_settle_time_us": 0.5,
                "flux_predistortion_return_prefix_us": 0.5,
                "flux_predistortion_recovery_us": 40.0,
                "flux_predistortion_overlap_payload_readout": False,
                "flux_predistortion_round_trip_mode": "stateful",
                "readout_thermalization_us": 10.0, "opx_t1_3pt_gain_lookup": True,
                "opx_reverse_survival_order": False, "opx_t1_compact_delay_loop": False,
                "diagnostic_iq_summary": True,
            })
            base = reset.apply(base)
            five.apply_verified_feedback_timing(base)
            manifest["status"] = "running"
            checkpoint(manifest_path, manifest)

            def acquire(entry):
                cfg = arm_config(base, entry)
                entry["inter_shot_delay_us"] = float(cfg["opx_inter_shot_delay_us"])
                checkpoint(manifest_path, manifest)
                print(f"[protocol-check] {entry['name']} delays={entry['delays_us']} us; "
                      f"post-reset park idle={entry['inter_shot_delay_us']:g} us", flush=True)
                exp = T15PointVsFlux(
                    soc=soc, soccfg=soccfg, path="q3", outerFolder=str(data_root),
                    suffix=f"TLS_PumpProbe_ProtocolCheck_{session_id}_{entry['name']}",
                    cfg=cfg, dc_vec=dc_vec, decay_delays_us=entry["delays_us"],
                    reference_hold_us=2.0, shots=p["shots_per_condition"], calib_params=None,
                    park_voltage=base["ff_park_gain"], min_ref_contrast=0.05,
                    max_relative_error=0.5, max_fit_t1_us=3000.0,
                    reset_mode=base["reset_mode"], flux_tail_compensation=compensation,
                    write_outputs=False,
                )
                exp.data.update(target_frequency_ghz=frequencies, fit_frequency_ghz=realized,
                                correction_mode="distortion-corrected")
                exp.acquire(progress=True)
                full_csv = five.save_execution_test_outputs(exp)
                # Preserve centroids even if the generic CSV exporter omits them.
                iq_path = session_dir / f"{entry['name']}_iq_centroids.npz"
                np.savez_compressed(iq_path, target_frequency_ghz=frequencies, dc_vec=dc_vec,
                                    **{k: v for k, v in exp.data.items() if k.startswith("iq_")})
                entry["iq_centroids_npz"] = str(iq_path)
                print(f"[protocol-check] saved {full_csv}", flush=True)
                return full_csv

            collect_arms(manifest, manifest_path, acquire)
        except BaseException as exc:
            manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            checkpoint(manifest_path, manifest)
            raise
        return manifest_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--history-check", action="store_true",
                        help="compare A/B at 10/500 us post-reset park idle in eight arms")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        p = parameters()
        print(json.dumps({
            "hardware_access": False, "frequency_count": round(
                1000 * (p["freq_max_ghz"] - p["freq_min_ghz"]) / p["freq_step_mhz"]) + 1,
            "frequency_range_ghz": [p["freq_min_ghz"], p["freq_max_ghz"]],
            "shots_per_condition": p["shots_per_condition"], "reset_calibrations": 1,
            "reference_hold_us": 2.0, "return_us": 40.0,
            "programs_per_arm": 1, "history_check": args.history_check,
            "idle_location": "after payload readout and feedback reset, at park",
            "arms": arms(history_check=args.history_check),
        }, indent=2))
    else:
        print(run(data_root=args.data_root, correction_json=args.correction_json,
                  history_check=args.history_check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
