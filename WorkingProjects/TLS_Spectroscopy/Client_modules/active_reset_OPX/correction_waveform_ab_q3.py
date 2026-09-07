import csv
from datetime import datetime
import json
from pathlib import Path
import sys

import numpy as np


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


QUBIT = "q3"
PARK_GAIN = -25790
TARGET_GAIN = -20000
CORRECTION_GAIN = 0.75
SHOTS = 100
DELAYS_US = np.asarray([
    1.0,
    1.412,
    7.929,
    22.328,
    31.529,
    44.523,
    62.872,
    70.0,
    88.782,
    125.371,
])


def _rmse(left, right):
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    if left.shape != right.shape or left.size == 0:
        raise ValueError("population traces must have the same nonempty shape")
    finite = np.isfinite(left) & np.isfinite(right)
    if not np.any(finite):
        return float("nan")
    return float(np.sqrt(np.mean((left[finite] - right[finite]) ** 2)))


def infer_failure_source(
    *,
    dynamic_corrected,
    isolated_dynamic_corrected,
    static_corrected,
    uncorrected_before,
    uncorrected_after,
    agreement_rmse=0.08,
    effect_rmse=0.15,
    drift_rmse=0.12,
):
    uncorrected_before = np.asarray(uncorrected_before, dtype=float)
    uncorrected_after = np.asarray(uncorrected_after, dtype=float)
    uncorrected_mean = 0.5 * (uncorrected_before + uncorrected_after)
    dynamic_static = _rmse(dynamic_corrected, static_corrected)
    isolated_static = _rmse(isolated_dynamic_corrected, static_corrected)
    dynamic_isolated = _rmse(dynamic_corrected, isolated_dynamic_corrected)
    uncorrected_stability = _rmse(uncorrected_before, uncorrected_after)
    static_uncorrected = _rmse(static_corrected, uncorrected_mean)
    dynamic_uncorrected = _rmse(dynamic_corrected, uncorrected_mean)
    if uncorrected_stability > float(drift_rmse):
        diagnosis = "measurement_drift"
    elif (
        dynamic_isolated >= float(effect_rmse)
        and isolated_static <= float(agreement_rmse)
    ):
        diagnosis = "cross_delay_flux_history"
    elif (
        dynamic_static <= float(agreement_rmse)
        and isolated_static <= float(agreement_rmse)
        and static_uncorrected >= float(effect_rmse)
        and dynamic_uncorrected >= float(effect_rmse)
    ):
        diagnosis = "correction_waveform"
    elif (
        isolated_static >= float(effect_rmse)
        and static_uncorrected <= float(agreement_rmse)
    ):
        diagnosis = "dynamic_assembly"
    else:
        diagnosis = "inconclusive"
    return {
        "diagnosis": diagnosis,
        "corrected_dynamic_vs_static_rmse": dynamic_static,
        "isolated_dynamic_vs_static_rmse": isolated_static,
        "dynamic_vs_isolated_dynamic_rmse": dynamic_isolated,
        "uncorrected_before_vs_after_rmse": uncorrected_stability,
        "static_corrected_vs_uncorrected_rmse": static_uncorrected,
        "corrected_vs_uncorrected_rmse": dynamic_uncorrected,
    }


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def _output_dir(outer_folder):
    now = datetime.now()
    path = (
        Path(outer_folder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_correction_waveform_AB"
    )
    path.mkdir(parents=True, exist_ok=False)
    return path


def _population(cfg, i_values, q_values, read_cycles):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        classify_payload_iq,
    )

    return np.mean(
        classify_payload_iq(cfg, i_values, q_values, read_cycles),
        axis=-1,
    )


def _dynamic_trace(soc, soccfg, cfg, compensation):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        acquire_t1_flux_sweep_iq,
    )

    run_cfg = dict(cfg)
    run_cfg["apply_flux_tail_compensation"] = compensation is not None
    run_cfg["flux_tail_compensation"] = compensation
    i_values, q_values, telemetry = acquire_t1_flux_sweep_iq(
        soc,
        soccfg,
        run_cfg,
        dc_gains=[TARGET_GAIN],
        delays_us=DELAYS_US,
        shots=SHOTS,
        reset_scheme="opx_unbounded",
    )
    read_cycles = int(telemetry["read_length_cycles"])
    return {
        "i": np.asarray(i_values[0], dtype=float),
        "q": np.asarray(q_values[0], dtype=float),
        "population": _population(
            run_cfg,
            i_values[0],
            q_values[0],
            read_cycles,
        ),
        "telemetry": telemetry,
    }


def _static_trace(soc, soccfg, cfg, compensation):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        acquire_t1_iq,
    )

    i_rows = []
    q_rows = []
    telemetry = []
    for delay_us in DELAYS_US:
        run_cfg = dict(cfg)
        run_cfg.update({
            "apply_flux_tail_compensation": True,
            "flux_tail_compensation": compensation,
            "ff_gain": TARGET_GAIN,
            "ff_hold": float(delay_us),
            "t1_wait_us": float(delay_us),
            "do_ff": True,
            "shots": SHOTS,
            "reps": SHOTS,
        })
        i_values, q_values, point_telemetry = acquire_t1_iq(
            soc,
            soccfg,
            run_cfg,
            shots=SHOTS,
        )
        i_rows.append(np.asarray(i_values, dtype=float))
        q_rows.append(np.asarray(q_values, dtype=float))
        telemetry.append(point_telemetry)
    i_values = np.asarray(i_rows, dtype=float)
    q_values = np.asarray(q_rows, dtype=float)
    read_cycles = int(telemetry[0]["read_length_cycles"])
    return {
        "i": i_values,
        "q": q_values,
        "population": _population(cfg, i_values, q_values, read_cycles),
        "telemetry": telemetry,
    }


def _isolated_dynamic_trace(soc, soccfg, cfg, compensation):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        acquire_t1_flux_sweep_iq,
    )

    run_cfg = dict(cfg)
    run_cfg["apply_flux_tail_compensation"] = True
    run_cfg["flux_tail_compensation"] = compensation
    i_rows = []
    q_rows = []
    telemetry = []
    for delay_us in DELAYS_US:
        i_values, q_values, point_telemetry = acquire_t1_flux_sweep_iq(
            soc,
            soccfg,
            run_cfg,
            dc_gains=[TARGET_GAIN],
            delays_us=[float(delay_us)],
            shots=SHOTS,
            reset_scheme="opx_unbounded",
        )
        i_rows.append(np.asarray(i_values[0, 0], dtype=float))
        q_rows.append(np.asarray(q_values[0, 0], dtype=float))
        telemetry.append(point_telemetry)
    i_values = np.asarray(i_rows, dtype=float)
    q_values = np.asarray(q_rows, dtype=float)
    read_cycles = int(telemetry[0]["read_length_cycles"])
    return {
        "i": i_values,
        "q": q_values,
        "population": _population(run_cfg, i_values, q_values, read_cycles),
        "telemetry": telemetry,
    }


def _write_outputs(output, traces, diagnosis, metadata):
    fields = [
        "method",
        "delay_us",
        "shots",
        "population_pe",
        "mean_i",
        "mean_q",
        "std_i",
        "std_q",
    ]
    with (output / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method, trace in traces.items():
            for index, delay_us in enumerate(DELAYS_US):
                writer.writerow({
                    "method": method,
                    "delay_us": float(delay_us),
                    "shots": int(trace["i"].shape[1]),
                    "population_pe": float(trace["population"][index]),
                    "mean_i": float(np.mean(trace["i"][index])),
                    "mean_q": float(np.mean(trace["q"][index])),
                    "std_i": float(np.std(trace["i"][index])),
                    "std_q": float(np.std(trace["q"][index])),
                })
    np.savez_compressed(
        output / "raw_iq.npz",
        delays_us=DELAYS_US,
        **{
            f"{method}_{quadrature}": trace[quadrature]
            for method, trace in traces.items()
            for quadrature in ("i", "q")
        },
    )
    payload = dict(metadata)
    payload["diagnosis"] = diagnosis
    payload["telemetry"] = {
        method: trace["telemetry"] for method, trace in traces.items()
    }
    (output / "result.json").write_text(
        json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n"
    )


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
        BaseConfig,
        outerFolder,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        prepare_reset_session,
    )

    output = _output_dir(outerFolder)
    correction_path = fpd.find_latest_compensation_json(
        outerFolder,
        QUBIT,
        baseline_dc_offset=PARK_GAIN,
    )
    if correction_path is None:
        raise FileNotFoundError("no matching flux-tail compensation JSON was found")
    compensation = fpd.scale_compensation_gain(
        fpd.load_compensation_json(correction_path),
        CORRECTION_GAIN,
    )
    soc, soccfg = makeProxy()
    base_cfg = dict(BaseConfig)
    base_cfg.update({
        "ff_park_gain": PARK_GAIN,
        "ff_gain": TARGET_GAIN,
        "do_ff": True,
        "shots": SHOTS,
        "reps": SHOTS,
    })
    session = prepare_reset_session(
        "active",
        outer_folder=outerFolder,
        qubit=QUBIT,
        base_cfg=base_cfg,
        soc=soc,
        soccfg=soccfg,
        purpose="correction_waveform_AB",
    )
    cfg = session.apply(base_cfg)
    traces = {}
    print("stage=uncorrected_before")
    traces["uncorrected_before"] = _dynamic_trace(soc, soccfg, cfg, None)
    print("stage=dynamic_corrected")
    traces["dynamic_corrected"] = _dynamic_trace(
        soc, soccfg, cfg, compensation
    )
    print("stage=isolated_dynamic_corrected")
    traces["isolated_dynamic_corrected"] = _isolated_dynamic_trace(
        soc, soccfg, cfg, compensation
    )
    print("stage=static_corrected")
    traces["static_corrected"] = _static_trace(
        soc, soccfg, cfg, compensation
    )
    print("stage=uncorrected_after")
    traces["uncorrected_after"] = _dynamic_trace(soc, soccfg, cfg, None)
    diagnosis = infer_failure_source(
        dynamic_corrected=traces["dynamic_corrected"]["population"],
        isolated_dynamic_corrected=traces["isolated_dynamic_corrected"]["population"],
        static_corrected=traces["static_corrected"]["population"],
        uncorrected_before=traces["uncorrected_before"]["population"],
        uncorrected_after=traces["uncorrected_after"]["population"],
    )
    metadata = {
        "qubit": QUBIT,
        "park_gain_dac": PARK_GAIN,
        "target_gain_dac": TARGET_GAIN,
        "correction_gain": CORRECTION_GAIN,
        "correction_source": correction_path,
        "shots_per_delay": SHOTS,
        "delays_us": DELAYS_US,
        "reset_calibration_output": session.calibration_output,
        "population_traces": {
            method: trace["population"] for method, trace in traces.items()
        },
    }
    _write_outputs(output, traces, diagnosis, metadata)
    print(json.dumps(_json_safe({
        **diagnosis,
        "population_traces": metadata["population_traces"],
        "output": output,
    }), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
