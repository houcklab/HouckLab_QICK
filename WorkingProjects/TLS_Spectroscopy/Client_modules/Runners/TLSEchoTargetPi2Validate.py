"""Finish the 4.288-GHz target pi/2 check with high-shot phase cycles.

The preceding target run resolved a drive and Rabi turnover but stopped at a
fixed midpoint threshold smaller than its shot noise. Reuse those measured
drive parameters, refine pi/2 near the crossing, and independently check two
four-phase cycles. No frequency search, five-point scan, or echo map runs.
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSParkPi2Calibration as calibration,
    TLSPumpProbeLocalizer as localizer,
)


CORRECTION_SHA256 = localizer.CORRECTION_SHA256
SHOTS = 1600


def validate_source(source):
    if (source.get("schema") != "q3.target-pi2-calibration.v1" or
            source.get("status") != "complete_pi2_midpoint_unstable" or
            source.get("correction_sha256") != CORRECTION_SHA256):
        raise ValueError("source must be the pinned, finished target Rabi run")
    try:
        target = float(source["site_frequency_ghz"])
        offset = float(source["chosen_frequency"]["offset_mhz"])
        fit = source["rabi_fit"]
        pi_gain = int(fit["pi_gain"])
        pi2_gain = int(fit["pi2_gain"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("source lacks target pulse parameters") from exc
    if (not fit.get("valid") or target != 4.288 or
            not math.isfinite(offset) or abs(offset) > 10. or
            not 0 < pi2_gain < pi_gain <= 30000):
        raise ValueError("source target pulse parameters are invalid")
    return target, offset, pi_gain, pi2_gain


def candidate_gains(source_gain):
    return tuple(sorted({int(source_gain) + delta
                         for delta in (-2000, -1000, 0, 1000, 2000)
                         if 0 < int(source_gain) + delta <= 30000}))


def refine_pi2(rows, *, source_gain):
    points = sorted((int(row["gain"]), float(row["response"]))
                    for row in rows)
    if len(points) < 4 or len({gain for gain, _ in points}) != len(points):
        return {"valid": False, "reason": "incomplete local gain sweep"}
    crossings = []
    for (lo_gain, lo), (hi_gain, hi) in zip(points[:-1], points[1:]):
        if lo <= .5 <= hi and hi - lo >= .04 and hi_gain - lo_gain <= 2000:
            gain = int(round(lo_gain + (.5 - lo) /
                             (hi - lo) * (hi_gain - lo_gain)))
            crossings.append((abs(gain - int(source_gain)), gain,
                              lo_gain, hi_gain))
    if not crossings:
        return {"valid": False, "reason": "no local half-height crossing"}
    _, gain, low, high = min(crossings)
    return {"valid": bool(abs(gain - int(source_gain)) <= 2500),
            "gain": gain, "bracket_gains": [low, high]}


def plan():
    return {"hardware_access": False,
            "purpose": "confirm target-resident pi/2 with improved statistics",
            "target_ghz": 4.288, "shots_per_arm": SHOTS,
            "local_gain_offsets_dac": [-2000, -1000, 0, 1000, 2000],
            "phase_check_deg": [0, 90, 180, 270],
            "phase_blocks": 2, "reset_mode": "passive",
            "frequency_sweep": False, "fresh_t1_scan": False,
            "wide_echo_map": False,
            "terminal": "no custom progress messages"}


def run(*, data_root=None, correction_json=None, source_manifest=None):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as five,
        TLSDualTransitionLoss as dual,
        TLSEchoPulseCalibration as target_cal,
        TLSPumpProbeResidentDrive as resident,
        TLSPumpProbeWidePassiveScan as wide,
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import _integer_dc_grid
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        _block_timeout_s, _run_program, runtime_bundle,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )

    data_root = Path(data_root or localizer.DATA_ROOT)
    correction = localizer.checked_correction(data_root, correction_json)
    if source_manifest is None:
        paths = sorted((data_root / "q3").glob(
            "q3_target_pi2_calibration_*/manifest.json"))
        if not paths:
            raise FileNotFoundError("no target-resident Rabi run on the NAS")
        source_manifest = paths[-1]
    source_manifest = Path(source_manifest)
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    target, offset, pi_gain, source_pi2 = validate_source(source)

    with localizer.scan_environment(correction):
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        if int(base["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        dc, realized = _integer_dc_grid(wide.parameters(),
                                        np.asarray([target]), tls)
        target_gain = int(dc[0])
        if target_gain != int(source["site_gain"]):
            raise ValueError("target DAC differs from source Rabi run")
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": tls._load_correction(
                         str(correction), str(data_root)),
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": .5,
                     "flux_predistortion_return_prefix_us": .5,
                     "flux_predistortion_recovery_us": 40.,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.})

        session_id = ("q3_target_pi2_validation_" +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        manifest_path = folder / "manifest.json"
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[4], text=True,
                stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = "unknown"
        manifest = {"schema": "q3.target-pi2-validation.v1",
                    "status": "running", "session_id": session_id,
                    "code_commit": commit,
                    "source_manifest": str(source_manifest),
                    "target_frequency_ghz": target,
                    "realized_frequency_ghz": float(realized[0]),
                    "target_gain": target_gain,
                    "drive_frequency_mhz": target * 1000 + offset,
                    "source_pi_gain": pi_gain,
                    "source_pi2_gain": source_pi2,
                    "correction_json": str(correction),
                    "correction_sha256": CORRECTION_SHA256,
                    "plan": plan(), "local_gain_sweep": [],
                    "phase_blocks": []}
        dual.checkpoint(manifest_path, manifest)
        double_class = target_cal.make_double_pulse_program(
            resident.ResidentDriveProgram)
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)

            def configuration(gain, phase=None):
                arm = {"flux_ghz": target,
                       "drive_mhz": target * 1000 + offset,
                       "gain": int(gain), "reference_state": None,
                       "preparation_state": "g",
                       "pre_drive_us": 30., "post_drive_us": .1,
                       "shots": SHOTS}
                cfg = resident.arm_config(base, arm, {target: target_gain})
                if phase is not None:
                    cfg["rabi_second_phase_deg"] = int(phase)
                    cfg["ff_hold"] = 30. + .1 + 2 * (
                        4 * float(cfg["sigma"]) + .01)
                return cfg

            def acquire(gain, filename, phase=None):
                cfg = configuration(gain, phase)
                program_type = (resident.ResidentDriveProgram
                                if phase is None else double_class)
                program = program_type(soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30., _block_timeout_s(cfg, SHOTS)),
                    cfg, total_shots=SHOTS)
                if len(records) != SHOTS:
                    raise RuntimeError(f"{filename}: incomplete IQ records")
                iq = resident.record_iq(records)
                np.savez_compressed(folder / filename,
                                    i=[r.i for r in records],
                                    q=[r.q for r in records])
                return iq

            resident.ResidentDriveProgram(
                soccfg, configuration(0), bundle.payload, bundle.loop)
            double_class(soccfg, configuration(source_pi2, 180),
                         bundle.payload, bundle.loop)
            manifest["compiled_pulse_edges"] = True
            dual.checkpoint(manifest_path, manifest)

            zero = acquire(0, "zero_pre.npz")
            pi = acquire(pi_gain, "pi_pre.npz")
            difference = pi.mean() - zero.mean()
            if abs(difference) < 600.:
                manifest["status"] = "complete_weak_reference"
                manifest["pi_iq_displacement"] = abs(difference)
                dual.checkpoint(manifest_path, manifest)
                return manifest_path
            axis = difference / abs(difference)
            scale = abs(difference)
            zero_sem = float(np.std(np.real(zero * np.conj(axis)), ddof=1) /
                             math.sqrt(zero.size) / scale)
            pi_sem = float(np.std(np.real(pi * np.conj(axis)), ddof=1) /
                           math.sqrt(pi.size) / scale)
            manifest["pi_iq_displacement"] = scale
            dual.checkpoint(manifest_path, manifest)

            def response(iq):
                values = np.real((np.asarray(iq) - zero.mean()) *
                                 np.conj(axis)) / scale
                mean = float(np.mean(values))
                shot_sem = float(np.std(values, ddof=1) /
                                 math.sqrt(values.size))
                sem = math.sqrt(shot_sem ** 2 +
                                ((1 - mean) * zero_sem) ** 2 +
                                (mean * pi_sem) ** 2)
                return {"mean": mean, "sem": sem}

            for gain in candidate_gains(source_pi2):
                stats = response(acquire(gain, f"gain_{gain:05d}.npz"))
                manifest["local_gain_sweep"].append({"gain": gain,
                                                     "response": stats["mean"],
                                                     "sem": stats["sem"]})
                dual.checkpoint(manifest_path, manifest)
            refined = refine_pi2(manifest["local_gain_sweep"],
                                 source_gain=source_pi2)
            manifest["refined_pi2"] = refined
            dual.checkpoint(manifest_path, manifest)
            if not refined["valid"]:
                manifest["status"] = "complete_midpoint_unresolved"
                dual.checkpoint(manifest_path, manifest)
                return manifest_path

            chosen = refined["gain"]
            check = response(acquire(chosen, "pi2_independent.npz"))
            manifest["pi2_independent"] = check
            dual.checkpoint(manifest_path, manifest)
            if abs(check["mean"] - .5) > max(.15, 2.5 * check["sem"]):
                manifest["status"] = "complete_midpoint_unstable"
                dual.checkpoint(manifest_path, manifest)
                return manifest_path

            for block, phases in enumerate(((0, 90, 180, 270),
                                            (270, 180, 90, 0))):
                values = {}
                for phase in phases:
                    stats = response(acquire(
                        chosen, f"phase_block_{block}_phase_{phase}.npz",
                        phase=phase))
                    values[phase] = stats["mean"]
                manifest["phase_blocks"].append(values)
                dual.checkpoint(manifest_path, manifest)
            gate = calibration.phase_circle_gate(
                *manifest["phase_blocks"], ground=0., pi=1.)
            manifest["two_pulse_gate"] = gate
            dual.checkpoint(manifest_path, manifest)

            zero_post = response(acquire(0, "zero_post.npz"))
            pi_post = response(acquire(pi_gain, "pi_post.npz"))
            manifest["end_checks"] = {"zero": zero_post, "pi": pi_post}
            stable = (abs(zero_post["mean"]) <= .2 and
                      abs(pi_post["mean"] - 1.) <= .2)
            manifest["status"] = ("complete_calibrated" if gate["valid"] and
                                  stable else "complete_controls_unstable")
            dual.checkpoint(manifest_path, manifest)
            return manifest_path
        except BaseException as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            dual.checkpoint(manifest_path, manifest)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--data-root")
    parser.add_argument("--correction-json")
    parser.add_argument("--source-manifest")
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), indent=2))
        return 0
    run(data_root=args.data_root,
        correction_json=args.correction_json,
        source_manifest=args.source_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
