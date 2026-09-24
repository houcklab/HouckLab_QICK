"""Separate production-shaped q3 3pt/5pt scans with a 5-us return/readout.

Only the survival-condition list differs between arms. The three-point arm
uses the same matched-reference acquisition and estimator family as the
five-point production scan; it is not the legacy park-reference 3pt runner.
Run only after any existing QICK acquisition has stopped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


CORRECTION_RETURN_US = 40.0
RETURN_TO_READOUT_US = 5.0
REFERENCE_HOLD_US = 2.0
SHOTS = 300
STEP_MHZ = 1.0


@dataclass(frozen=True)
class ProtocolArm:
    name: str
    delays_us: tuple[float, ...]
    reference_hold_us: float = REFERENCE_HOLD_US

    @property
    def point_count(self):
        return 2 + len(self.delays_us)


def protocol_arms():
    return (
        ProtocolArm("three_point_100us", (100.0,)),
        ProtocolArm("five_point_25_60_100us", (25.0, 60.0, 100.0)),
    )


def arm_config(base, arm):
    if arm not in protocol_arms():
        raise ValueError("unknown q3 protocol comparison arm")
    config = dict(base)
    config.update({
        "flux_predistortion_recovery_us": RETURN_TO_READOUT_US,
        "flux_predistortion_return_prefix_us": RETURN_TO_READOUT_US,
        "flux_predistortion_overlap_payload_readout": False,
        "flux_predistortion_round_trip_mode": "stateful",
        "qua_shot_order": True,
    })
    return config


def _checkpoint(path, document):
    pending = Path(path).with_suffix(".pending")
    with pending.open("w", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(pending, path)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_commit():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[4], text=True,
    ).strip()


def write_arm_curve(path, *, frequencies_ghz, data, point_count):
    """Save a small, analysis-ready result immediately after each arm."""
    frequencies = np.asarray(frequencies_ghz, dtype=float).reshape(-1)
    p0 = np.asarray(data["P0"], dtype=float).reshape(-1)
    p1 = np.asarray(data["P1"], dtype=float).reshape(-1)
    gamma = np.asarray(data[f"inv_T1_{point_count}pt_per_us"], dtype=float).reshape(-1)
    valid = np.asarray(data[f"T1_{point_count}pt_valid_mask"], dtype=bool).reshape(-1)
    success = np.asarray(data[f"T1_{point_count}pt_fit_success"], dtype=bool).reshape(-1)
    if not all(axis.size == frequencies.size for axis in (p0, p1, gamma, valid, success)):
        raise ValueError("curve arrays must share the frequency grid")
    path = Path(path)
    pending = path.with_suffix(".pending")
    with pending.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "frequency_ghz", "P0", "P1", "contrast", "gamma_per_us",
            "valid_mask", "fit_success",
        ))
        writer.writeheader()
        for values in zip(frequencies, p0, p1, gamma, valid, success):
            frequency, ground, excited, loss, is_valid, did_fit = values
            usable = bool(is_valid and did_fit and math.isfinite(loss))
            writer.writerow({
                "frequency_ghz": float(frequency),
                "P0": float(ground), "P1": float(excited),
                "contrast": float(excited - ground),
                "gamma_per_us": float(loss) if usable else "",
                "valid_mask": int(is_valid), "fit_success": int(did_fit),
            })
    os.replace(pending, path)
    return path


def plot_completed_curves(session_dir, manifest):
    """Render from the checkpointed curves, including a partial first-arm plot."""
    import matplotlib
    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot as plt

    completed = [arm for arm in manifest["arms"] if arm["status"] == "complete"]
    if not completed:
        raise ValueError("no completed protocol arms to plot")
    fig, (ax_loss, ax_contrast) = plt.subplots(
        2, 1, figsize=(11, 6.5), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]}, constrained_layout=True,
    )
    for arm in completed:
        with Path(arm["curve_csv"]).open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        frequency = np.asarray([float(row["frequency_ghz"]) for row in rows])
        gamma = np.asarray([
            float(row["gamma_per_us"]) if row["gamma_per_us"] else np.nan
            for row in rows
        ])
        contrast = np.asarray([float(row["contrast"]) for row in rows])
        label = "3pt: 100 µs" if arm["name"] == "three_point_100us" else "5pt: 25/60/100 µs"
        ax_loss.plot(frequency, gamma, linewidth=1.1, label=label)
        ax_contrast.plot(frequency, contrast, linewidth=0.9, label=label)
    ax_loss.set(ylabel=r"$\Gamma_1$ ($\mu$s$^{-1}$)",
                title="q3 / AlOx: 5 µs return-to-readout, separate 3pt and 5pt scans")
    ax_contrast.set(xlabel="Qubit frequency (GHz)", ylabel="P1 − P0")
    for axis in (ax_loss, ax_contrast):
        axis.grid(alpha=0.2)
        axis.legend(fontsize=9)
    output = Path(session_dir) / "gamma1_3pt_vs_5pt_return5us.png"
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return output


def run(*, correction_json, shots=SHOTS, step_mhz=STEP_MHZ,
        acknowledged_scans_stopped=False):
    if not acknowledged_scans_stopped:
        raise RuntimeError("confirm that the current QICK scan has stopped")
    if str(os.environ.get("SET_YOKO", "")).strip().lower() in {"1", "true", "yes", "on"}:
        raise RuntimeError("SET_YOKO must be false")
    if str(os.environ.get("Q3_FLUX_TAIL_GAIN", "")).strip():
        raise RuntimeError("unset Q3_FLUX_TAIL_GAIN; use the pinned correction gain")
    if not correction_json or not Path(correction_json).is_file():
        raise FileNotFoundError("pass an existing, explicit --correction-json")
    if not 2 <= shots <= 300 or not math.isfinite(step_mhz) or step_mhz <= 0:
        raise ValueError("shots must be 2..300 and step-mhz finite and positive")
    if not math.isclose(400 / step_mhz, round(400 / step_mhz), abs_tol=1e-8):
        raise ValueError("step-mhz must divide the 400 MHz production band")

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

    five.install_scan_calibration(tls)
    if bool(getattr(tls, "SET_YOKO", False)):
        raise RuntimeError("SET_YOKO must be false")
    params = dict(five.P6_5PT_APPLES_TO_APPLES)
    params.update(freq_step_mhz=float(step_mhz), shots_per_condition=int(shots),
                  sync_enabled=False, reset_mode="active")
    target = _target_frequency_grid_ghz(params)
    dc_vec, realized = _integer_dc_grid(params, target)
    if min(dc_vec) < -32768 or max(dc_vec) > 32767:
        raise ValueError("inverted QICK DC grid exceeds signed DAC range")
    compensation = tls._load_correction(correction_json, tls.outerFolder)
    if float(tls.FLUX_TAIL_COMPENSATION_GAIN) != 1.0:
        raise RuntimeError("comparison requires effective correction gain 1.0")
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ReturnReadoutLandingAudit import (
        _assert_prefix_matched,
    )
    _assert_prefix_matched(compensation, (2.5, 102.5, 27.5, 62.5), RETURN_TO_READOUT_US)

    session_id = "q3_return5us_3pt_5pt_" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    session_dir = Path(tls.outerFolder) / tls.QUBIT / session_id
    session_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = session_dir / "manifest.json"
    arms = protocol_arms()
    manifest = {
        "schema": "q3.return5us-protocol-comparison.v1",
        "session_id": session_id, "status": "calibrating",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "code_commit": _git_commit(), "correction_json": str(correction_json),
        "correction_sha256": _sha256(correction_json),
        "shots_per_condition": int(shots), "frequency_grid_ghz": target.tolist(),
        "realized_frequency_ghz": realized.tolist(), "dc_vec": dc_vec.tolist(),
        "step_mhz": float(step_mhz), "return_template_us": CORRECTION_RETURN_US,
        "return_to_readout_us": RETURN_TO_READOUT_US,
        "arms": [{**asdict(arm), "status": "pending"} for arm in arms],
    }
    _checkpoint(manifest_path, manifest)
    print(f"[compare] session={session_id} manifest={manifest_path}", flush=True)

    soc, soccfg = tls.makeProxy()
    reset_session = prepare_reset_session(
        "active", outer_folder=tls.outerFolder, qubit=tls.QUBIT,
        base_cfg=tls.BaseConfig, soc=soc, soccfg=soccfg,
        purpose="ReturnFiveUsProtocolComparison",
    )
    manifest["reset_calibration_path"] = str(reset_session.calibration_output)
    manifest["status"] = "running"
    _checkpoint(manifest_path, manifest)
    base = dict(tls.BaseConfig)
    base.update({
        "shots": int(shots), "ff_gain_vec": dc_vec,
        "apply_flux_tail_compensation": True,
        "flux_tail_compensation": compensation,
        "flux_fit_params": tls.FLUX_FIT_PARAMS,
        "relax_delay": PASSIVE_T1_RESET_US,
        "qubit_pulse_style": "arb", "flux_settle_time_us": 0.5,
        "readout_thermalization_us": 10.0,
        "opx_t1_3pt_gain_lookup": True,
        "opx_reverse_survival_order": False,
    })
    base = reset_session.apply(base)
    five.apply_verified_feedback_timing(base)

    for index, arm in enumerate(arms):
        entry = manifest["arms"][index]
        entry["status"] = "acquiring"
        _checkpoint(manifest_path, manifest)
        print(f"[compare] {index + 1}/{len(arms)} {arm.name}", flush=True)
        try:
            cfg = arm_config(base, arm)
            exp = T15PointVsFlux(
                soc=soc, soccfg=soccfg, path=tls.QUBIT,
                outerFolder=tls.outerFolder, suffix=f"{session_id}_{arm.name}",
                cfg=cfg, dc_vec=dc_vec, decay_delays_us=arm.delays_us,
                reference_hold_us=arm.reference_hold_us, shots=int(shots),
                calib_params=None,
                park_voltage=cfg.get("ff_park_gain", tls._baseline_dc_offset()),
                min_ref_contrast=0.05, max_relative_error=0.5,
                max_fit_t1_us=3000.0, reset_mode=cfg["reset_mode"],
                flux_tail_compensation=compensation, write_outputs=False,
            )
            exp.data.update({
                "target_frequency_ghz": target,
                "fit_frequency_ghz": realized,
                "comparison_session": session_id, "comparison_arm": arm.name,
                "correction_source_sha256": manifest["correction_sha256"],
            })
            exp.acquire(progress=True)
            full_csv = five.save_execution_test_outputs(exp)
            curve = write_arm_curve(
                session_dir / f"{arm.name}_gamma1_curve.csv",
                frequencies_ghz=realized, data=exp.data,
                point_count=arm.point_count,
            )
            entry.update(status="complete", full_csv=str(full_csv),
                         curve_csv=str(curve),
                         completed_at=datetime.now(timezone.utc).isoformat())
            _checkpoint(manifest_path, manifest)
            plot = plot_completed_curves(session_dir, manifest)
            manifest["comparison_plot_png"] = str(plot)
            _checkpoint(manifest_path, manifest)
            print(f"[compare] saved {arm.name}: {curve}", flush=True)
        except BaseException as exc:
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            manifest["status"] = "failed"
            _checkpoint(manifest_path, manifest)
            raise
    manifest["status"] = "complete"
    _checkpoint(manifest_path, manifest)
    return manifest_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--correction-json")
    parser.add_argument("--shots", type=int, default=SHOTS)
    parser.add_argument("--step-mhz", type=float, default=STEP_MHZ)
    parser.add_argument("--confirm-scans-stopped", action="store_true")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps({
            "hardware_access": False,
            "shots_per_condition": args.shots, "step_mhz": args.step_mhz,
            "frequency_count": int(round(400 / args.step_mhz)) + 1,
            "return_template_us": CORRECTION_RETURN_US,
            "return_to_readout_us": RETURN_TO_READOUT_US,
            "arms": [{**asdict(arm), "point_count": arm.point_count}
                     for arm in protocol_arms()],
        }, indent=2))
        return 0
    if not args.confirm_scans_stopped:
        parser.error("--run requires --confirm-scans-stopped")
    if not args.correction_json:
        parser.error("--run requires --correction-json")
    print(run(correction_json=args.correction_json, shots=args.shots,
              step_mhz=args.step_mhz, acknowledged_scans_stopped=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
