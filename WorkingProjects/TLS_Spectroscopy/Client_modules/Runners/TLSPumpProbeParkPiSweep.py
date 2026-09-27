"""Calibration-only q3 park-pi frequency diagnostic after two rejected references.

The pump-probe drift tracker stopped before collecting any loss data because
the prepared-excited IQ cluster approached the stable ground cluster. Sweep
only the park pi-pulse frequency, with the same half-gain decision readout and
official_guard20 timing used by the rejected tracker. Alternate negative and
positive offsets, bracket the sweep with the original frequency, and save raw
ground/excited IQ at every point even when its classifier fails the normal
quality guard. No classifier is installed and no TLS pump or flux scan runs.
This distinguishes frequency detuning from a loss of preparation contrast that
does not recover in the tested frequency window; it does not diagnose T1 alone.

--stability-check holds the original frequency fixed and measures paired
half-gain decision and normal-gain probe references in twelve slots, twenty
seconds apart. It tests whether both exact tracker references remain usable
over time, without starting a drift scan.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
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


PARK_PI_MHZ = 4367.292
SHOTS = 500
OFFSETS_MHZ = [0.0, *(offset for step in range(2, 22, 2)
                       for offset in (-float(step), float(step))), 0.0]


def plan(*, stability_check=False):
    if stability_check:
        points = [dict(name=f"point_{2 * slot + gain_index:04d}", slot=slot,
                       offset_mhz=0.0, pi_frequency_mhz=PARK_PI_MHZ,
                       readout_gain_dac=gain,
                       not_before_offset_s=slot * 20.0)
                  for slot in range(12)
                  for gain_index, gain in enumerate((940, 1880))]
    else:
        points = [dict(name=f"point_{i:04d}", offset_mhz=offset,
                       pi_frequency_mhz=round(PARK_PI_MHZ + offset, 6),
                       readout_gain_dac=940)
                  for i, offset in enumerate(OFFSETS_MHZ)]
    return dict(hardware_access=False, microwave_pump_enabled=False,
                changes_production_settings=False,
                stability_check=bool(stability_check),
                readout_gain_dac=None if stability_check else 940,
                readout_gains_dac=[940, 1880] if stability_check else [940],
                park_gain_dac=-25146,
                shots_per_state_per_context=SHOTS,
                total_reference_shots=len(points) * 4 * SHOTS,
                points=points, note=__doc__)


def reference_config(base, pi_frequency_mhz, *, readout_gain_dac=940):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        build_calibration_config,
    )

    if int(base["ff_park_gain"]) != -25146 or int(base["read_pulse_gain"]) != 1880:
        raise RuntimeError("Park or normal readout gain differs from the rejected q3 run")
    if readout_gain_dac not in (940, 1880):
        raise ValueError("Only the tracker decision and probe readout gains are supported")
    decision_base = dict(base, read_pulse_gain=940)
    decision_cfg = reference.profile_config(
        build_calibration_config(decision_base, pi_frequency_mhz),
        reset_validation.PROFILE,
    )
    return dict(decision_cfg, read_pulse_gain=readout_gain_dac)


def capture_raw_reference(soc, soccfg, cfg):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
        _capture_context,
    )

    # The combined acquire_calibration API fits before returning its raw IQ.
    # A deliberately off-resonant point may have coincident state centroids,
    # so capture first and persist before attempting any fit.
    return {context: _capture_context(soc, soccfg, cfg, context=context, shots=SHOTS)
            for context in ("payload", "loop")}


def fit_saved_reference(out, cfg, raw, options, metadata):
    import numpy as np
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
        ReferenceAxis,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
        CalibrationBundle, save_calibration, save_raw_calibration,
        threshold_policy_metadata,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import (
        fit_classifier,
    )

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    save_raw_calibration(out / "calibration_raw.npz", raw)
    ground = raw["loop"]["ground"]
    excited = raw["loop"]["excited"]
    di = float(np.mean(excited["i"]) - np.mean(ground["i"]))
    dq = float(np.mean(excited["q"]) - np.mean(ground["q"]))
    result = {"output": str(out), "loop_centroid_distance_raw": math.hypot(di, dq)}
    fits = {}
    try:
        for context in ("payload", "loop"):
            data = raw[context]
            fits[context] = fit_classifier(
                data["ground"]["i"], data["ground"]["q"],
                data["excited"]["i"], data["excited"]["q"],
                context=context, **options,
            )
        axis = ReferenceAxis.from_centers(
            np.mean(ground["i"]), np.mean(ground["q"]),
            np.mean(excited["i"]), np.mean(excited["q"]),
        )
    except (ValueError, RuntimeError) as exc:
        failure = {"schema": "q3.park-pi-fit-failure.v1",
                   "reason": f"{type(exc).__name__}: {exc}",
                   "partial_fits": {k: v.to_dict() for k, v in fits.items()},
                   "metadata": dict(metadata)}
        (out / "fit_failure.json").write_text(
            json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        result.update(accepted=False,
                      rejection_reason=f"fit rejected: {failure['reason']}",
                      payload=fits["payload"].holdout if "payload" in fits else {},
                      loop=fits["loop"].holdout if "loop" in fits else {})
        return result
    bundle_metadata = dict(metadata)
    bundle_metadata.update(
        shots_per_state_per_context=len(raw["payload"]["ground"]["i"]),
        config_sha256=hashlib.sha256(
            json.dumps(dict(cfg), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest(),
    )
    bundle_metadata.update(threshold_policy_metadata(
        false_ground_limit=options.get("false_ground_limit", 0.01),
        false_pi_limit=options.get("false_pi_limit", 0.01),
        ground_confidence_fidelity=options.get("ground_confidence_fidelity"),
        qua_threshold_steps=options.get("qua_threshold_steps", 100),
    ))
    bundle = CalibrationBundle(1, fits["payload"], fits["loop"], axis,
                               bundle_metadata)
    save_calibration(out / "calibration.json", bundle)
    result.update(reference.calibration_report(bundle))
    return result


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        stability_check=False):
    run_plan = plan(stability_check=stability_check)
    label = "[park-reference-stability]" if stability_check else "[park-pi-sweep]"
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    with localizer.scan_environment(correction):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as five, TLSSpectroscopy as tls,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import (
            q3_benchmark_settings,
        )

        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("Unexpected q3 park configuration")
        configured_pi = next(float(tls.BaseConfig[key]) for key in
                             ("reset_pi_freq", "qubit_pi_freq", "qubit_freq")
                             if tls.BaseConfig.get(key) is not None)
        if not math.isclose(configured_pi, PARK_PI_MHZ, abs_tol=1e-6):
            raise RuntimeError(f"Configured park pi frequency changed: {configured_pi} MHz")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)

        prefix = ("q3_pump_probe_park_reference_stability_" if stability_check
                  else "q3_pump_probe_park_pi_sweep_")
        session_id = (prefix
                      + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                      + "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        manifest = dict(schema="q3.pump-probe-park-pi-sweep.v1",
                        session_id=session_id,
                        created_at=datetime.now(timezone.utc).isoformat(),
                        status="calibrating", code_commit=os.environ["Q3_CODE_COMMIT"],
                        stability_check=bool(stability_check),
                        correction_json=str(correction),
                        correction_sha256=localizer.CORRECTION_SHA256,
                        parameters=run_plan,
                        points=[dict(point, status="pending")
                                for point in run_plan["points"]])
        protocol.checkpoint(path, manifest)
        print(f"{label} manifest={path}", flush=True)
        try:
            soc, soccfg = tls.makeProxy()
            manifest["status"] = "running"
            protocol.checkpoint(path, manifest)
            schedule_start = time.monotonic()

            def acquire(entry):
                if stability_check:
                    reference.wait_for_reference_slot(
                        schedule_start, entry["not_before_offset_s"])
                entry["acquisition_started_at"] = datetime.now(timezone.utc).isoformat()
                entry["acquisition_start_offset_s"] = time.monotonic() - schedule_start
                cfg = reference_config(
                    tls.BaseConfig, entry["pi_frequency_mhz"],
                    readout_gain_dac=entry["readout_gain_dac"])
                out = folder / entry["name"]
                out.mkdir(exist_ok=False)
                (out / "config.json").write_text(
                    json.dumps(cfg, default=pilot.json_default, indent=2) + "\n",
                    encoding="utf-8")
                raw = capture_raw_reference(soc, soccfg, cfg)
                report = fit_saved_reference(
                    out, cfg, raw, q3_benchmark_settings().calibration_options(),
                    {"purpose": "TLSPumpProbeParkPiSweep",
                     "session_id": session_id, "point": entry["name"],
                     "pi_frequency_mhz": entry["pi_frequency_mhz"],
                     "readout_gain_dac": entry["readout_gain_dac"]},
                )
                print(f"{label} {entry['offset_mhz']:+.0f} MHz "
                      f"gain={entry['readout_gain_dac']} "
                      f"loop_peak={report['loop'].get('peak_fidelity', float('nan')):.4f} "
                      f"payload_peak={report['payload'].get('peak_fidelity', float('nan')):.4f} "
                      f"accepted={report['accepted']}", flush=True)
                return report

            pilot.collect_points(manifest, path, acquire)
        except BaseException as exc:
            manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            protocol.checkpoint(path, manifest)
            raise
        accepted = sum(bool(p["result"]["accepted"]) for p in manifest["points"])
        print(f"{label} diagnostic complete: {accepted}/{len(manifest['points'])} "
              f"fits accepted; no calibration installed. {path}", flush=True)
        return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--stability-check", action="store_true",
                        help="repeat exact decision and probe references at park")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(stability_check=args.stability_check), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            stability_check=args.stability_check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
