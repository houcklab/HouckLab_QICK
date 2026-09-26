"""Bracket short-delay measurements with the original q3 localizer protocol.

After the September 26 target check, the loss feature appeared near 4.106 GHz
instead of 4.098 GHz. The eight-delay scan also had nonmonotonic populations
and used references from its first program chunk. This A-B-A diagnostic uses
one reset calibration and one unchunked program per arm, with a shared 25-us
survival condition. It tests reproducibility/protocol dependence before pumping.

Run only after the other q3 acquisition has stopped. All arms retain the
2-us reference, 40-us return, native correction, and park readout. Each result
is checkpointed, including IQ centroids; any acquisition error stops the series.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
)


def arms():
    return [
        {"name": "A_before", "delays_us": [25.0, 60.0, 100.0]},
        {"name": "B_short", "delays_us": [4.0, 8.0, 25.0]},
        {"name": "A_after", "delays_us": [25.0, 60.0, 100.0]},
    ]


def parameters():
    return {**localizer.parameters(), "freq_min_ghz": 4.080,
            "freq_max_ghz": 4.125, "freq_step_mhz": 0.5,
            "shots_per_condition": 500}


def checkpoint(path, document):
    path = Path(path)
    pending = path.with_suffix(".pending")
    pending.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(pending, path)


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


def run(*, data_root=localizer.DATA_ROOT, correction_json=None):
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
        session_id = "q3_pump_probe_protocol_check_" + datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        session_dir = data_root / "q3" / session_id
        session_dir.mkdir(parents=True, exist_ok=False)
        manifest_path = session_dir / "manifest.json"
        manifest = {
            "schema": "q3.pump-probe-protocol-check.v1", "session_id": session_id,
            "status": "calibrating", "created_at": datetime.now(timezone.utc).isoformat(),
            "code_commit": os.environ["Q3_CODE_COMMIT"],
            "correction_json": str(correction), "correction_sha256": localizer.CORRECTION_SHA256,
            "parameters": p, "target_frequency_ghz": frequencies.tolist(),
            "realized_frequency_ghz": realized.tolist(), "dc_vec": dc_vec.tolist(),
            "arms": [dict(arm, status="pending") for arm in arms()],
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
                print(f"[protocol-check] {entry['name']} delays={entry['delays_us']} us", flush=True)
                exp = T15PointVsFlux(
                    soc=soc, soccfg=soccfg, path="q3", outerFolder=str(data_root),
                    suffix=f"TLS_PumpProbe_ProtocolCheck_{session_id}_{entry['name']}",
                    cfg=dict(base), dc_vec=dc_vec, decay_delays_us=entry["delays_us"],
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
            "programs_per_arm": 1, "arms": arms(),
        }, indent=2))
    else:
        print(run(data_root=args.data_root, correction_json=args.correction_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
