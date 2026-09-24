"""Independent q3 five-point return/readout IQ audit.

The production long scan is never entered.  Each arm gets its own ordinary
five-point CSV and an immediately checkpointed manifest.  ``--plan`` needs no
hardware; ``--run`` requires a stopped-scan acknowledgement and an explicit
correction JSON.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import statistics
import subprocess
import uuid


DELAYS_US = (25.0, 60.0, 100.0)
SHOTS = 300
STEP_MHZ = 1.0
FULL_RETURN_US = 40.0
CONTRAST_WAIT_US = (2.5, 5.0, 10.0, 20.0, 40.0)


@dataclass(frozen=True)
class AuditArm:
    name: str
    recovery_us: float
    prefix_us: float
    overlap_readout: bool
    reset_mode: str = "active"


def validate_arm(arm):
    if not math.isfinite(arm.recovery_us) or not 1 <= arm.recovery_us <= FULL_RETURN_US:
        raise ValueError("recovery must be 1..40 us")
    if not math.isfinite(arm.prefix_us) or not 1 <= arm.prefix_us <= arm.recovery_us:
        raise ValueError("return prefix must be 1 us through recovery")
    if arm.reset_mode != "active":
        raise ValueError("landing audit requires active reset")
    if not arm.overlap_readout and arm.prefix_us != arm.recovery_us:
        raise ValueError("nonoverlap readout requires full return before readout")
    return arm


def landing_arms():
    control = AuditArm("landing_control", 25, 25, False)
    challenge = (
        AuditArm("recovery_1us", 1, 1, False),
        AuditArm("recovery_5us", 5, 5, False),
        AuditArm("recovery_10us", 10, 10, False),
        AuditArm("recovery_15us", 15, 15, False),
        AuditArm("recovery_40us", 40, 40, False),
        AuditArm("continuous_stateful_1us", 40, 1, True),
        AuditArm("continuous_stateful_5us", 40, 5, True),
        AuditArm("continuous_stateful_10us", 40, 10, True),
        AuditArm("continuous_stateful_15us", 40, 15, True),
        AuditArm("continuous_stateful_25us", 40, 25, True),
    )
    arms = [replace(control, name="landing_control_start")]
    for repeat, order in (
        (1, challenge),
        (2, tuple(reversed(challenge))),
        (3, challenge[5:] + challenge[:5]),
    ):
        for index, arm in enumerate(order):
            arms.append(replace(arm, name=f"{arm.name}_l{repeat}"))
            if (index + 1) % 5 == 0:
                arms.append(replace(control, name=f"landing_control_l{repeat}_{index + 1}"))
    arms.append(replace(control, name="landing_control_end"))
    return [validate_arm(arm) for arm in arms]


def contrast_wait_arms():
    """Repeat production-shaped scans while truncating one 40 us return."""
    control = AuditArm("contrast_control", 25.0, 25.0, False)
    arms = [replace(control, name="contrast_control_start")]
    for repeat, waits in ((1, CONTRAST_WAIT_US),
                          (2, tuple(reversed(CONTRAST_WAIT_US))),
                          (3, CONTRAST_WAIT_US)):
        for wait_us in waits:
            label = f"{wait_us:g}".replace(".", "p")
            arms.append(AuditArm(
                f"contrast_stop_{label}us_r{repeat}",
                wait_us, wait_us, False,
            ))
        if repeat < 3:
            arms.append(replace(control, name=f"contrast_control_mid{repeat}"))
    arms.append(replace(control, name="contrast_control_end"))
    return [validate_arm(arm) for arm in arms]


def summarize_contrast_csv(path):
    """Summarize production P0/P1 references without fit-based filtering."""
    with Path(path).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"no reference records in {path}")
    pairs = []
    valid = 0
    for row in rows:
        p0, p1 = float(row["P0"]), float(row["P1"])
        if not (math.isfinite(p0) and math.isfinite(p1)):
            raise ValueError(f"nonfinite reference population in {path}")
        pairs.append((p0, p1))
        valid += (float(row["T1_5pt_valid_mask"]) == 1.0
                  and float(row["T1_5pt_fit_success"]) == 1.0)
    return {
        "frequency_count": len(pairs),
        "median_p0": statistics.median(pair[0] for pair in pairs),
        "median_p1": statistics.median(pair[1] for pair in pairs),
        "median_p1_minus_p0": statistics.median(p1 - p0 for p0, p1 in pairs),
        "valid_fit_fraction": valid / len(pairs),
    }


def write_contrast_outputs(session_dir, manifest):
    """Checkpoint a compact table and headless plot after each finished arm."""
    session_dir = Path(session_dir)
    rows = []
    for arm in manifest["arms"]:
        if arm["status"] != "complete":
            continue
        summary = arm.get("contrast_summary") or summarize_contrast_csv(
            arm["full_csv"]
        )
        rows.append({
            "arm": arm["name"],
            "return_stop_us": float(arm["recovery_us"]),
            "repeat": (arm["name"].rsplit("_r", 1)[-1]
                       if "_r" in arm["name"] else "control"),
            **summary,
        })
    suffix = f"{len(rows):02d}_of_{len(manifest['arms']):02d}"
    csv_path = session_dir / f"contrast_vs_wait_{suffix}.csv"
    pending = csv_path.with_suffix(".pending")
    with pending.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "arm", "return_stop_us", "repeat", "frequency_count",
            "median_p0", "median_p1", "median_p1_minus_p0",
            "valid_fit_fraction",
        ))
        writer.writeheader()
        writer.writerows(rows)
    os.replace(pending, csv_path)

    import matplotlib
    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for repeat in ("1", "2", "3"):
        points = sorted((row for row in rows if row["repeat"] == repeat),
                        key=lambda row: row["return_stop_us"])
        if points:
            ax.plot([row["return_stop_us"] for row in points],
                    [row["median_p1_minus_p0"] for row in points],
                    marker="o", linewidth=1.2, alpha=0.7,
                    label=f"repeat {repeat}")
    controls = [row for row in rows if row["repeat"] == "control"]
    if controls:
        ax.scatter([25.0] * len(controls),
                   [row["median_p1_minus_p0"] for row in controls],
                   color="0.35", marker="x", label="25 µs drift controls")
    ax.set(xlabel="Correction stop and readout time after return starts (µs)",
           ylabel="Median P1 − P0 across 3.9–4.3 GHz",
           title="q3 production-style return/readout contrast")
    ax.grid(alpha=0.25)
    if ax.has_data():
        ax.legend()
    fig.tight_layout()
    png_path = session_dir / f"contrast_vs_wait_{suffix}.png"
    fig.savefig(png_path, dpi=180)
    plt.close(fig)
    return csv_path, png_path


def arm_config(base, arm):
    validate_arm(arm)
    config = dict(base)
    config.update({
        "flux_predistortion_recovery_us": float(arm.recovery_us),
        "flux_predistortion_return_prefix_us": float(arm.prefix_us),
        "flux_predistortion_overlap_payload_readout": bool(arm.overlap_readout),
        "flux_predistortion_round_trip_mode": "stateful",
        "diagnostic_iq_summary": True,
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


def _assert_prefix_matched(compensation, holds_us, prefix_us):
    """Ensure the early command is not changed by extending the later tail."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse

    for hold_us in holds_us:
        _, short = ff_pulse.compensation_round_trip_segments(
            compensation, hold_us, recovery_us=prefix_us,
        )
        _, full = ff_pulse.compensation_round_trip_segments(
            compensation, hold_us, recovery_us=FULL_RETURN_US,
        )
        early, _ = ff_pulse.split_compensation_segments(full, prefix_us)
        def grid(segments):
            # QICK's fabric clock is finer than this 4 ns comparison grid.
            samples = []
            for coefficient, duration in segments:
                samples.extend([float(coefficient)] * int(round(duration * 250)))
            return samples
        a, b = grid(short), grid(early)
        if a != b:
            raise RuntimeError(
                f"short/full return commands differ before {prefix_us:g} us "
                f"for hold {hold_us:g} us"
            )


def run(*, correction_json, shots=SHOTS, step_mhz=STEP_MHZ,
        acknowledged_scans_stopped=False, contrast_wait=False):
    if not acknowledged_scans_stopped:
        raise RuntimeError("confirm the QICK production scan has stopped")
    if str(os.environ.get("SET_YOKO", "")).strip().lower() in {"1", "true", "yes", "on"}:
        raise RuntimeError("SET_YOKO must be false")
    if str(os.environ.get("Q3_FLUX_TAIL_GAIN", "")).strip():
        raise RuntimeError("unset Q3_FLUX_TAIL_GAIN; use the pinned correction gain")
    if not correction_json or not Path(correction_json).is_file():
        raise FileNotFoundError("pass an existing, explicit --correction-json")
    if not 2 <= shots <= 300 or step_mhz <= 0 or 400 / step_mhz != round(400 / step_mhz):
        raise ValueError("shots must be 2..300 and step must divide 400 MHz")

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
        raise RuntimeError("audit requires effective correction gain 1.0")
    holds_us = (2.5, 27.5, 62.5, 102.5)
    arms = contrast_wait_arms() if contrast_wait else landing_arms()
    for prefix in sorted({arm.prefix_us for arm in arms}):
        _assert_prefix_matched(compensation, holds_us, prefix)

    session_id = ("q3_return_contrast_" if contrast_wait else "q3_readout_landing_") + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    session_dir = Path(tls.outerFolder) / tls.QUBIT / session_id
    session_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = session_dir / "manifest.json"
    manifest = {
        "schema": ("q3.return-contrast.v1" if contrast_wait
                   else "q3.return-readout-landing.v1"),
        "session_id": session_id,
        "status": "calibrating", "created_at": datetime.now(timezone.utc).isoformat(),
        "code_commit": _git_commit(), "correction_json": str(correction_json),
        "correction_sha256": _sha256(correction_json),
        "shots": int(shots), "frequency_grid_ghz": target.tolist(),
        "realized_frequency_ghz": realized.tolist(), "dc_vec": dc_vec.tolist(),
        "delays_us": list(DELAYS_US), "step_mhz": float(step_mhz),
        "return_template_us": FULL_RETURN_US,
        "arms": [{**asdict(arm), "status": "pending"} for arm in arms],
    }
    _checkpoint(manifest_path, manifest)
    print(f"[landing] session={session_id} manifest={manifest_path}", flush=True)
    print(f"[landing] {len(arms)} arms, {len(target)} frequencies, {shots} shots/condition", flush=True)

    soc, soccfg = tls.makeProxy()
    reset_session = prepare_reset_session(
        "active", outer_folder=tls.outerFolder, qubit=tls.QUBIT,
        base_cfg=tls.BaseConfig, soc=soc, soccfg=soccfg,
        purpose="ReturnReadoutLandingAudit",
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
        "qubit_pulse_style": "arb",
        "flux_settle_time_us": 0.5,
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
        print(f"[landing] {index + 1}/{len(arms)} {arm.name}", flush=True)
        try:
            cfg = arm_config(base, arm)
            exp = T15PointVsFlux(
                soc=soc, soccfg=soccfg, path=tls.QUBIT,
                outerFolder=tls.outerFolder, suffix=f"{session_id}_{arm.name}",
                cfg=cfg, dc_vec=dc_vec, decay_delays_us=DELAYS_US,
                reference_hold_us=2.0, shots=int(shots), calib_params=None,
                park_voltage=cfg.get("ff_park_gain", tls._baseline_dc_offset()),
                min_ref_contrast=0.05, max_relative_error=0.5,
                max_fit_t1_us=3000.0, reset_mode=cfg["reset_mode"],
                flux_tail_compensation=compensation, write_outputs=False,
            )
            exp.data.update({
                "target_frequency_ghz": target,
                "fit_frequency_ghz": realized,
                "audit_session": session_id, "audit_arm": arm.name,
                "correction_source_sha256": manifest["correction_sha256"],
            })
            exp.acquire(progress=True)
            full_csv = five.save_execution_test_outputs(exp)
            entry.update(status="complete", full_csv=str(full_csv),
                         pickle=str(exp.pname),
                         completed_at=datetime.now(timezone.utc).isoformat())
            if contrast_wait:
                entry["contrast_summary"] = summarize_contrast_csv(full_csv)
            _checkpoint(manifest_path, manifest)
            if contrast_wait:
                summary_csv, summary_png = write_contrast_outputs(
                    session_dir, manifest
                )
                manifest["contrast_summary_csv"] = str(summary_csv)
                manifest["contrast_plot_png"] = str(summary_png)
                _checkpoint(manifest_path, manifest)
            print(f"[landing] saved {arm.name}: {full_csv}", flush=True)
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
    parser.add_argument("--contrast-wait", action="store_true",
                        help="2.5/5/10/20/40 us return-stop contrast sweep")
    parser.add_argument("--confirm-scans-stopped", action="store_true")
    args = parser.parse_args(argv)
    arms = contrast_wait_arms() if args.contrast_wait else landing_arms()
    if args.plan:
        print(json.dumps({
            "hardware_access": False, "shots": args.shots,
            "step_mhz": args.step_mhz, "frequency_count":
            int(round(400 / args.step_mhz)) + 1,
            "delays_us": DELAYS_US,
            "return_template_us": FULL_RETURN_US,
            "arms": [asdict(arm) for arm in arms],
        }, indent=2))
        return 0
    if not args.confirm_scans_stopped:
        parser.error("--run requires --confirm-scans-stopped")
    if not args.correction_json:
        parser.error("--run requires --correction-json")
    print(run(correction_json=args.correction_json, shots=args.shots,
              step_mhz=args.step_mhz,
              acknowledged_scans_stopped=True,
              contrast_wait=args.contrast_wait))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
