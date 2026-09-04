from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        _repo_root = parent
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import NpEncoder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.park_stability import (
    build_frequency_axis_mhz,
    build_park_probe_config,
    fit_local_frequency_slope,
    frequency_trace_to_step_response,
    scale_park_compensation,
    summarize_park_trace,
    summarize_target_trace,
)


QUBIT = "q3"
PARK_GAIN = None
CENTER_FREQUENCY_MHZ = None
FREQUENCY_HALF_SPAN_MHZ = 25.0
FREQUENCY_STEP_MHZ = 0.5
DELAY_US = (0.5, 2.0, 5.0, 10.0, 20.0, 40.0, 60.0, 80.0, 120.0, 160.0)
SLOPE_GAIN_OFFSETS_DAC = (-100, 0, 100)
SLOPE_DELAY_US = 5.0
SHOTS = 100
INTERLEAVE_ROUNDS = 4
SPECTROSCOPY_GAIN = 15000
SPECTROSCOPY_LENGTH_US = 0.5
PASSIVE_RESET_US = 400.0
ACTIVE_RESET_WINDOW_US = 120.0
MAX_ALLOWED_DRIFT_MHZ = 0.5
EDGE_GUARD_MHZ = 1.0
MIN_ABS_SLOPE_MHZ_PER_DAC = 0.005
MIN_SLOPE_R_SQUARED = 0.95
REFERENCE_WINDOW_US = 20.0
SEGMENT_EDGES_NS = (0.0, 20000.0, 40000.0, 60000.0, 80000.0, 120000.0)
REGULARIZATION = 0.02
FINAL_WEIGHT = 0.1
MIN_MULTIPLIER = 0.95
MAX_MULTIPLIER = 1.20
CORRECTION_SCALES = (0.5, 0.75, 1.0)


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(f"Expected qick 0.2.133, found {qick.__version__}")

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse import FFStepResponseSpecProgram
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import interleaved_average, suppress_stdout
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.flux_predistortion import calculate_piecewise_dc_correction
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.trace_extraction import extract_trace_from_map

    park_gain = int(BaseConfig["ff_park_gain"] if PARK_GAIN is None else PARK_GAIN)
    center_mhz = float(
        BaseConfig.get("qubit_pi_freq", BaseConfig["qubit_freq"])
        if CENTER_FREQUENCY_MHZ is None
        else CENTER_FREQUENCY_MHZ
    )
    delay_us = np.asarray(DELAY_US, dtype=float)
    if delay_us.size < 8 or not np.all(np.isfinite(delay_us)) or np.any(delay_us <= 0):
        raise ValueError("DELAY_US must contain at least eight positive finite delays")
    if np.any(np.diff(delay_us) <= 0):
        raise ValueError("DELAY_US must be strictly increasing")
    if int(INTERLEAVE_ROUNDS) <= 0 or int(INTERLEAVE_ROUNDS) > int(SHOTS):
        raise ValueError("INTERLEAVE_ROUNDS must be in the range 1..SHOTS")
    frequency_mhz = build_frequency_axis_mhz(center_mhz, FREQUENCY_HALF_SPAN_MHZ, FREQUENCY_STEP_MHZ)
    now = datetime.now()
    output_dir = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_park_compensation"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    soc, soccfg = makeProxy()
    ff_entry = soccfg["gens"][int(BaseConfig["ff_ch"])]
    max_abs_gain = int(ff_entry["maxv"] * float(ff_entry.get("maxv_scale", 1.0)))
    try:
        source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=_repo_root, text=True).strip()
    except Exception:
        source_commit = "unknown"

    metadata = {
        "created": now.isoformat(),
        "source_commit": source_commit,
        "qubit": QUBIT,
        "park_gain_dac": park_gain,
        "center_frequency_mhz": center_mhz,
        "frequency_half_span_mhz": float(FREQUENCY_HALF_SPAN_MHZ),
        "frequency_step_mhz": float(FREQUENCY_STEP_MHZ),
        "delay_us": delay_us,
        "slope_gain_offsets_dac": list(SLOPE_GAIN_OFFSETS_DAC),
        "slope_delay_us": float(SLOPE_DELAY_US),
        "shots": int(SHOTS),
        "interleave_rounds": int(INTERLEAVE_ROUNDS),
        "active_reset_window_us": float(ACTIVE_RESET_WINDOW_US),
        "max_allowed_drift_mhz": float(MAX_ALLOWED_DRIFT_MHZ),
        "max_abs_gain_dac": max_abs_gain,
        "correction_scales": list(CORRECTION_SCALES),
    }
    (output_dir / "run_metadata.json").write_text(json.dumps(metadata, cls=NpEncoder, indent=2, sort_keys=True) + "\n")

    def extract_maps(mean_iq, delays):
        magnitude_db = 20.0 * np.log10(np.abs(mean_iq) + 1e-12)
        phase_rad = np.angle(mean_iq)
        mode = "independent_slices" if len(delays) == 1 else "ridge"
        options = {
            "trace_tracking_mode": mode,
            "trace_polarity": "auto",
            "trace_max_jump_mhz": 8.0,
            "trace_local_fit_half_window_mhz": 8.0,
            "trace_smoothing_window_points": 7,
            "trace_smoothing_polyorder": 2,
            "trace_use_smoothed_frequency": False,
        }
        phase_trace = extract_trace_from_map(
            phase_rad,
            frequency_mhz / 1e3,
            np.asarray(delays) * 1e3,
            center_mhz / 1e3,
            center_mhz / 1e3,
            float(FREQUENCY_HALF_SPAN_MHZ) / 1e3,
            **options,
        )
        magnitude_trace = extract_trace_from_map(
            magnitude_db,
            frequency_mhz / 1e3,
            np.asarray(delays) * 1e3,
            center_mhz / 1e3,
            center_mhz / 1e3,
            float(FREQUENCY_HALF_SPAN_MHZ) / 1e3,
            **options,
        )
        return magnitude_db, phase_rad, magnitude_trace, phase_trace

    def acquire_arm(name, target_gain, delays, compensation=None):
        delays = np.asarray(delays, dtype=float)
        cfg = build_park_probe_config(
            BaseConfig,
            park_gain=int(target_gain),
            frequency_axis_mhz=frequency_mhz,
            shots=SHOTS,
            spectroscopy_gain=SPECTROSCOPY_GAIN,
            spectroscopy_length_us=SPECTROSCOPY_LENGTH_US,
            passive_reset_us=PASSIVE_RESET_US,
        )
        cfg["interleave_rounds"] = int(INTERLEAVE_ROUNDS)
        if compensation is not None:
            cfg["flux_tail_compensation"] = compensation
        (output_dir / f"{name}_config.json").write_text(json.dumps({
            "delay_us": delays,
            "config_template": cfg,
        }, cls=NpEncoder, indent=2, sort_keys=True) + "\n")
        assembly_saved = False

        def run_point(index, reps):
            nonlocal assembly_saved
            run_cfg = dict(cfg)
            run_cfg["ff_hold"] = float(delays[index])
            run_cfg["reps"] = int(reps)
            with suppress_stdout():
                program = FFStepResponseSpecProgram(soccfg, run_cfg)
            if index == len(delays) - 1 and not assembly_saved:
                (output_dir / f"{name}.asm").write_text(program.asm())
                binary = np.asarray(program.compile(), dtype=np.uint64)
                (output_dir / f"{name}.asm.sha256").write_text(hashlib.sha256(binary.tobytes()).hexdigest() + "\n")
                assembly_saved = True
            with suppress_stdout():
                _, avgi, avgq = program.acquire(soc, load_pulses=True, progress=False)
            return np.asarray(avgi[0][0]) + 1j * np.asarray(avgq[0][0])

        mean_iq = interleaved_average(
            run_point,
            len(delays),
            int(SHOTS),
            rounds=int(INTERLEAVE_ROUNDS),
        ).T
        magnitude_db, phase_rad, magnitude_trace, phase_trace = extract_maps(mean_iq, delays)
        magnitude_frequency_mhz = np.asarray(magnitude_trace["selected_frequency_ghz"], dtype=float) * 1e3
        phase_frequency_mhz = np.asarray(phase_trace["selected_frequency_ghz"], dtype=float) * 1e3
        phase_supported = np.asarray(phase_trace["supported"], dtype=bool)
        magnitude_supported = np.asarray(magnitude_trace["supported"], dtype=bool)
        np.savez_compressed(
            output_dir / f"{name}_raw.npz",
            complex_iq=mean_iq,
            magnitude_db=magnitude_db,
            phase_rad=phase_rad,
            frequency_mhz=frequency_mhz,
            delay_us=delays,
            phase_frequency_mhz=phase_frequency_mhz,
            magnitude_frequency_mhz=magnitude_frequency_mhz,
            phase_supported=phase_supported,
            magnitude_supported=magnitude_supported,
        )
        raw_rows = np.column_stack((
            np.broadcast_to(delays[None, :], magnitude_db.shape).ravel(),
            np.broadcast_to(frequency_mhz[:, None], magnitude_db.shape).ravel(),
            magnitude_db.ravel(),
            phase_rad.ravel(),
        ))
        np.savetxt(
            output_dir / f"{name}_raw.csv",
            raw_rows,
            delimiter=",",
            header="delay_us,probe_frequency_mhz,magnitude_db,phase_rad",
            comments="",
        )
        trace_rows = np.column_stack((
            delays,
            phase_frequency_mhz,
            magnitude_frequency_mhz,
            phase_supported.astype(int),
            magnitude_supported.astype(int),
        ))
        np.savetxt(
            output_dir / f"{name}_trace.csv",
            trace_rows,
            delimiter=",",
            header="delay_us,phase_frequency_mhz,magnitude_frequency_mhz,phase_supported,magnitude_supported",
            comments="",
        )
        if len(delays) > 1:
            phase_summary = summarize_park_trace(
                delay_us=delays,
                frequency_mhz=phase_frequency_mhz,
                supported=phase_supported,
                sweep_min_mhz=float(frequency_mhz[0]),
                sweep_max_mhz=float(frequency_mhz[-1]),
                active_reset_window_us=ACTIVE_RESET_WINDOW_US,
                max_allowed_drift_mhz=MAX_ALLOWED_DRIFT_MHZ,
                edge_guard_mhz=max(float(EDGE_GUARD_MHZ), 2.0 * float(FREQUENCY_STEP_MHZ)),
            )
            magnitude_summary = summarize_park_trace(
                delay_us=delays,
                frequency_mhz=magnitude_frequency_mhz,
                supported=magnitude_supported,
                sweep_min_mhz=float(frequency_mhz[0]),
                sweep_max_mhz=float(frequency_mhz[-1]),
                active_reset_window_us=ACTIVE_RESET_WINDOW_US,
                max_allowed_drift_mhz=MAX_ALLOWED_DRIFT_MHZ,
                edge_guard_mhz=max(float(EDGE_GUARD_MHZ), 2.0 * float(FREQUENCY_STEP_MHZ)),
            )
        else:
            phase_summary = None
            magnitude_summary = None
        fig, axes = plt.subplots(3, 1, figsize=(9, 11), constrained_layout=True)
        pcm0 = axes[0].pcolormesh(delays, frequency_mhz, magnitude_db, shading="auto")
        fig.colorbar(pcm0, ax=axes[0], label="Magnitude [dB]")
        axes[0].plot(delays, magnitude_frequency_mhz, "w.-")
        axes[0].set(ylabel="Frequency [MHz]", title="Magnitude")
        pcm1 = axes[1].pcolormesh(delays, frequency_mhz, phase_rad, shading="auto")
        fig.colorbar(pcm1, ax=axes[1], label="Phase [rad]")
        axes[1].plot(delays, phase_frequency_mhz, "w.-")
        axes[1].set(ylabel="Frequency [MHz]", title="Phase")
        phase_reference = float(phase_frequency_mhz[0])
        magnitude_reference = float(magnitude_frequency_mhz[0])
        axes[2].plot(delays, phase_frequency_mhz - phase_reference, "o-", label="phase")
        axes[2].plot(delays, magnitude_frequency_mhz - magnitude_reference, "o-", label="magnitude")
        axes[2].axhspan(-MAX_ALLOWED_DRIFT_MHZ, MAX_ALLOWED_DRIFT_MHZ, color="tab:green", alpha=0.15)
        axes[2].axvline(ACTIVE_RESET_WINDOW_US, color="tab:red", ls="--")
        axes[2].set(xlabel="Time at park [us]", ylabel="Frequency - first point [MHz]", title=name)
        axes[2].grid(alpha=0.25)
        axes[2].legend()
        fig.savefig(output_dir / f"{name}.png", dpi=180)
        plt.close(fig)
        return {
            "name": name,
            "target_gain_dac": int(target_gain),
            "phase_frequency_mhz": phase_frequency_mhz,
            "magnitude_frequency_mhz": magnitude_frequency_mhz,
            "phase_supported": phase_supported,
            "magnitude_supported": magnitude_supported,
            "phase_summary": phase_summary,
            "magnitude_summary": magnitude_summary,
        }

    print("stage=local_gain_slope", flush=True)
    slope_gains = np.asarray([park_gain + int(offset) for offset in SLOPE_GAIN_OFFSETS_DAC], dtype=int)
    if np.any(np.abs(slope_gains) > max_abs_gain):
        raise ValueError("Local gain-slope calibration exceeds DAC range")
    slope_arms = [
        acquire_arm(f"slope_gain_{gain:+d}", int(gain), [SLOPE_DELAY_US])
        for gain in slope_gains
    ]
    slope_phase_frequency = np.asarray([arm["phase_frequency_mhz"][0] for arm in slope_arms], dtype=float)
    slope_magnitude_frequency = np.asarray([arm["magnitude_frequency_mhz"][0] for arm in slope_arms], dtype=float)
    slope_rows = np.column_stack((slope_gains, slope_phase_frequency, slope_magnitude_frequency))
    np.savetxt(
        output_dir / "local_gain_slope.csv",
        slope_rows,
        delimiter=",",
        header="gain_dac,phase_frequency_mhz,magnitude_frequency_mhz",
        comments="",
    )
    slope_fit = fit_local_frequency_slope(
        slope_gains,
        slope_phase_frequency,
        min_abs_slope_mhz_per_dac=MIN_ABS_SLOPE_MHZ_PER_DAC,
        min_r_squared=MIN_SLOPE_R_SQUARED,
    )
    (output_dir / "local_gain_slope.json").write_text(json.dumps(slope_fit, cls=NpEncoder, indent=2, sort_keys=True) + "\n")

    print("stage=uncorrected", flush=True)
    uncorrected = acquire_arm("uncorrected", park_gain, delay_us)
    if not np.all(uncorrected["phase_supported"]):
        raise RuntimeError("Uncorrected phase trace is incomplete")
    response = frequency_trace_to_step_response(
        delay_us=delay_us,
        frequency_mhz=uncorrected["phase_frequency_mhz"],
        park_gain=park_gain,
        slope_mhz_per_dac=slope_fit["slope_mhz_per_dac"],
        reference_window_us=REFERENCE_WINDOW_US,
    )
    target_frequency_mhz = float(response["reference_frequency_mhz"])
    uncorrected_target = summarize_target_trace(
        delay_us=delay_us,
        frequency_mhz=uncorrected["phase_frequency_mhz"],
        supported=uncorrected["phase_supported"],
        target_frequency_mhz=target_frequency_mhz,
        reference_window_us=REFERENCE_WINDOW_US,
        active_reset_window_us=ACTIVE_RESET_WINDOW_US,
        max_allowed_error_mhz=MAX_ALLOWED_DRIFT_MHZ,
    )
    headroom_bound = float(max_abs_gain) / abs(float(park_gain))
    upper_multiplier = min(float(MAX_MULTIPLIER), headroom_bound)
    correction_fit = calculate_piecewise_dc_correction(
        delay_us * 1e3,
        response["step_response"],
        segment_edges_ns=SEGMENT_EDGES_NS,
        regularization=REGULARIZATION,
        final_weight=FINAL_WEIGHT,
        normalize=False,
        min_multiplier=MIN_MULTIPLIER,
        max_multiplier=upper_multiplier,
        desired_response="unity",
        correction_gain=1.0,
    )
    if not correction_fit["success"]:
        raise RuntimeError(f"Piecewise correction solve failed: {correction_fit['error']}")
    correction_fit["method"] = "park_frequency_local_slope_deconvolution"
    correction_fit["metadata"] = {
        "qubit": QUBIT,
        "flux_channel": int(BaseConfig["ff_ch"]),
        "dc_offset": park_gain,
        "baseline_dc_offset": 0,
        "local_slope_mhz_per_dac": slope_fit["slope_mhz_per_dac"],
        "reference_frequency_mhz": response["reference_frequency_mhz"],
        "fit_ff_ramp_length_us": float(BaseConfig["ff_ramp_length"]),
        "fit_dt_pulseplay_us": float(BaseConfig.get("dt_pulseplay", 5.0)),
        "fit_dt_pulsedef_us": float(BaseConfig.get("dt_pulsedef", 0.002)),
    }
    correction_fit["effective_gain_dac"] = response["effective_gain_dac"]
    correction_fit["measured_step_response"] = response["step_response"]
    (output_dir / "correction_fit.json").write_text(json.dumps(correction_fit, cls=NpEncoder, indent=2, sort_keys=True) + "\n")

    print("stage=corrected_validation", flush=True)
    validations = {}
    compensation_paths = {}
    for scale in CORRECTION_SCALES:
        scaled = scale_park_compensation(
            correction_fit,
            scale=float(scale),
            park_gain=park_gain,
            max_abs_gain=max_abs_gain,
        )
        scaled["metadata"] = dict(correction_fit["metadata"])
        scaled["metadata"]["correction_scale"] = float(scale)
        tag = str(float(scale)).replace(".", "p")
        compensation_path = output_dir / f"correction_scale_{tag}.json"
        compensation_path.write_text(json.dumps(scaled, cls=NpEncoder, indent=2, sort_keys=True) + "\n")
        compensation_paths[tag] = str(compensation_path)
        arm = acquire_arm(f"corrected_scale_{tag}", park_gain, delay_us, compensation=scaled)
        arm["phase_target_summary"] = summarize_target_trace(
            delay_us=delay_us,
            frequency_mhz=arm["phase_frequency_mhz"],
            supported=arm["phase_supported"],
            target_frequency_mhz=target_frequency_mhz,
            reference_window_us=REFERENCE_WINDOW_US,
            active_reset_window_us=ACTIVE_RESET_WINDOW_US,
            max_allowed_error_mhz=MAX_ALLOWED_DRIFT_MHZ,
        )
        validations[tag] = arm

    eligible = {
        tag: arm
        for tag, arm in validations.items()
        if arm["phase_target_summary"]["status"] in {"pass", "fail"}
        and arm["phase_target_summary"]["max_abs_target_error_mhz"] is not None
    }
    if not eligible:
        raise RuntimeError("Every corrected validation was inconclusive")
    best_tag, best_arm = min(
        eligible.items(),
        key=lambda item: float(item[1]["phase_target_summary"]["max_abs_target_error_mhz"]),
    )
    best_path = output_dir / "best_compensation.json"
    best_path.write_text(Path(compensation_paths[best_tag]).read_text())
    uncorrected_error = float(uncorrected_target["max_abs_target_error_mhz"])
    best_error = float(best_arm["phase_target_summary"]["max_abs_target_error_mhz"])
    summary = {
        "park_gain_dac": park_gain,
        "local_gain_slope": slope_fit,
        "uncorrected_phase": uncorrected["phase_summary"],
        "uncorrected_magnitude": uncorrected["magnitude_summary"],
        "uncorrected_target": uncorrected_target,
        "corrected": {
            tag: {
                "phase": arm["phase_summary"],
                "magnitude": arm["magnitude_summary"],
                "phase_target": arm["phase_target_summary"],
                "compensation_json": compensation_paths[tag],
            }
            for tag, arm in validations.items()
        },
        "best_scale": float(best_tag.replace("p", ".")),
        "best_phase_status": best_arm["phase_summary"]["status"],
        "best_target_status": best_arm["phase_target_summary"]["status"],
        "best_phase_max_abs_drift_mhz": float(best_arm["phase_summary"]["max_abs_drift_mhz"]),
        "best_phase_max_abs_target_error_mhz": best_error,
        "uncorrected_phase_max_abs_drift_mhz": float(uncorrected["phase_summary"]["max_abs_drift_mhz"]),
        "uncorrected_phase_max_abs_target_error_mhz": uncorrected_error,
        "improvement_fraction": 1.0 - best_error / uncorrected_error if uncorrected_error > 0 else None,
        "best_compensation_json": str(best_path),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, cls=NpEncoder, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "best_scale": summary["best_scale"],
        "best_phase_status": summary["best_phase_status"],
        "best_target_status": summary["best_target_status"],
        "best_phase_max_abs_drift_mhz": summary["best_phase_max_abs_drift_mhz"],
        "best_phase_max_abs_target_error_mhz": summary["best_phase_max_abs_target_error_mhz"],
        "uncorrected_phase_max_abs_drift_mhz": summary["uncorrected_phase_max_abs_drift_mhz"],
        "uncorrected_phase_max_abs_target_error_mhz": summary["uncorrected_phase_max_abs_target_error_mhz"],
        "improvement_fraction": summary["improvement_fraction"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
