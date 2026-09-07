from datetime import datetime
import csv
import json
from pathlib import Path
import sys
import time

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
DIAGNOSTIC_SHOTS = 50
MAX_FREQUENCY_POINTS = 81
MIN_DELAY_STEP_US = 20.0


def _correlation(left, right):
    left = np.asarray(left, dtype=float).reshape(-1)
    right = np.asarray(right, dtype=float).reshape(-1)
    if left.size != right.size or left.size < 3:
        raise ValueError("correlation inputs must have the same length of at least three")
    left = left - np.mean(left)
    right = right - np.mean(right)
    scale = float(np.linalg.norm(left) * np.linalg.norm(right))
    if scale <= 0:
        return 0.0
    return float(np.dot(left, right) / scale)


def compare_time_order(forward_time, forward_values, reverse_time, reverse_values):
    forward_time = np.asarray(forward_time, dtype=float).reshape(-1)
    reverse_time = np.asarray(reverse_time, dtype=float).reshape(-1)
    forward_values = np.asarray(forward_values, dtype=float).reshape(-1)
    reverse_values = np.asarray(reverse_values, dtype=float).reshape(-1)
    if not (
        forward_time.size
        == reverse_time.size
        == forward_values.size
        == reverse_values.size
    ):
        raise ValueError("time and value arrays must have matching lengths")
    forward_order = np.argsort(forward_time)
    reverse_order = np.argsort(reverse_time)
    if not np.allclose(
        forward_time[forward_order],
        reverse_time[reverse_order],
        rtol=0,
        atol=1e-9,
    ):
        raise ValueError("forward and reverse runs must use the same physical delays")
    physical = _correlation(
        forward_values[forward_order],
        reverse_values[reverse_order],
    )
    acquisition = _correlation(forward_values, reverse_values)
    if max(physical, acquisition) < 0.4:
        diagnosis = "inconclusive"
    elif physical >= acquisition + 0.15:
        diagnosis = "physical_delay_feature"
    elif acquisition >= physical + 0.15:
        diagnosis = "acquisition_history_feature"
    else:
        diagnosis = "ambiguous"
    return {
        "diagnosis": diagnosis,
        "physical_time_correlation": float(physical),
        "acquisition_order_correlation": float(acquisition),
        "correlation_difference_physical_minus_order": float(physical - acquisition),
    }


def _diagnostic_times(settings):
    start = max(float(settings["t_min_us"]), 0.01)
    stop = float(settings["t_max_us"])
    step = max(float(settings["t_step_us"]), MIN_DELAY_STEP_US)
    values = np.arange(start, stop, step, dtype=float)
    if values.size < 5:
        values = np.linspace(start, stop, 5, endpoint=False, dtype=float)
    return values


def _diagnostic_frequencies(cfg):
    start = float(cfg["qubit_freq_start"])
    stop = float(cfg["qubit_freq_stop"])
    requested = max(int(cfg["qubit_freq_expts"]), 2)
    points = min(requested, MAX_FREQUENCY_POINTS)
    return np.linspace(start, stop, points, dtype=float)


def _column_background(magnitude_db):
    values = np.nanmedian(np.asarray(magnitude_db, dtype=float), axis=0)
    return values - np.nanmedian(values)


def _make_output_dir(outer_folder):
    now = datetime.now()
    output = (
        Path(outer_folder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_P3_time_origin_diagnostic"
    )
    output.mkdir(parents=True, exist_ok=False)
    return output


def _acquire_map(soc, soccfg, cfg, frequencies, times, target, baseline, shots, progress):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order import (
        acquire_passive_flux_spectroscopy_grid,
    )

    run_cfg = dict(cfg)
    run_cfg["reps"] = int(shots)
    i_values, q_values, telemetry = acquire_passive_flux_spectroscopy_grid(
        soc,
        soccfg,
        run_cfg,
        frequencies_mhz=frequencies,
        dc_gains=[float(target)],
        hold_times_us=times,
        read_frequencies_mhz=[float(run_cfg["read_pulse_freq"])],
        order="shot_frequency_dc_time",
        baseline_rearm_us=float(run_cfg["baseline_rearm_us"]),
        post_readout_reset_us=0.0,
        readout_after_park=False,
        progress=progress,
    )
    signal = np.mean(i_values + 1j * q_values, axis=3)[:, 0, :]
    return {
        "times_us": np.asarray(times, dtype=float),
        "magnitude_db": 20.0 * np.log10(np.abs(signal) + 1e-12),
        "phase_rad": np.angle(signal),
        "background_db": _column_background(20.0 * np.log10(np.abs(signal) + 1e-12)),
        "telemetry": dict(telemetry),
        "target_gain_dac": float(target),
        "baseline_gain_dac": float(baseline),
    }


def _save_csv(path, frequencies, runs):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "method",
            "acquisition_time_index",
            "delay_time_us",
            "frequency_mhz",
            "magnitude_db",
            "phase_rad",
            "column_background_db",
        ])
        for name, run in runs.items():
            for time_index, delay in enumerate(run["times_us"]):
                for frequency_index, frequency in enumerate(frequencies):
                    writer.writerow([
                        name,
                        time_index,
                        float(delay),
                        float(frequency),
                        float(run["magnitude_db"][frequency_index, time_index]),
                        float(run["phase_rad"][frequency_index, time_index]),
                        float(run["background_db"][time_index]),
                    ])


def _save_plot(path, frequencies, runs, comparison):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    maps = ["forward_step", "reverse_step", "no_step"]
    all_values = np.concatenate([runs[name]["magnitude_db"].reshape(-1) for name in maps])
    vmin, vmax = np.nanpercentile(all_values, [2, 98])
    for axis, name in zip(axes.reshape(-1)[:3], maps):
        run = runs[name]
        order = np.argsort(run["times_us"])
        image = axis.pcolormesh(
            run["times_us"][order],
            frequencies,
            run["magnitude_db"][:, order],
            shading="auto",
            vmin=vmin,
            vmax=vmax,
        )
        axis.set_title(name)
        axis.set_xlabel("Physical delay after target step [us]")
        axis.set_ylabel("Qubit frequency [MHz]")
        fig.colorbar(image, ax=axis, label="Magnitude [dB]")
    axis = axes.reshape(-1)[3]
    for name, run in runs.items():
        order = np.argsort(run["times_us"])
        axis.plot(
            run["times_us"][order],
            run["background_db"][order],
            marker="o",
            ms=3,
            label=name,
        )
    axis.set_xlabel("Physical delay after target step [us]")
    axis.set_ylabel("Frequency-median background [dB]")
    axis.set_title(comparison["diagnosis"])
    axis.legend()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import outerFolder
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as runner

    settings = dict(runner.P3_STEP_RESPONSE)
    cfg = runner._step3_common_cfg(settings)
    baseline = float(runner._baseline_dc_offset())
    target = float(runner.TARGET_DC_OFFSET)
    if not bool(cfg.get("opx_hard_flux_steps", False)):
        raise RuntimeError("P3 production configuration is not using hard flux steps")
    times = _diagnostic_times(settings)
    frequencies = _diagnostic_frequencies(cfg)
    shots = min(int(settings["shots"]), DIAGNOSTIC_SHOTS)
    output = _make_output_dir(outerFolder)
    print(f"output={output}")
    soc, soccfg = makeProxy()
    methods = (
        ("forward_step", times, target),
        ("reverse_step", times[::-1], target),
        ("no_step", times, baseline),
    )
    runs = {}
    for name, run_times, run_target in methods:
        started = time.time()
        print(f"stage={name}")

        def report(done, total, start=started):
            progress_counter(
                done - 1,
                total,
                progress_bar=True,
                percent=True,
                start_time=start,
            )

        runs[name] = _acquire_map(
            soc,
            soccfg,
            cfg,
            frequencies,
            run_times,
            run_target,
            baseline,
            shots,
            report,
        )
    comparison = compare_time_order(
        runs["forward_step"]["times_us"],
        runs["forward_step"]["background_db"],
        runs["reverse_step"]["times_us"],
        runs["reverse_step"]["background_db"],
    )
    comparison["no_step_background_peak_to_peak_db"] = float(
        np.ptp(runs["no_step"]["background_db"])
    )
    comparison["forward_step_background_peak_to_peak_db"] = float(
        np.ptp(runs["forward_step"]["background_db"])
    )
    summary = {
        "platform": "QICK",
        "qubit": QUBIT,
        "shots": int(shots),
        "frequency_points": int(frequencies.size),
        "frequency_min_mhz": float(frequencies[0]),
        "frequency_max_mhz": float(frequencies[-1]),
        "delay_points": int(times.size),
        "delay_min_us": float(np.min(times)),
        "delay_max_us": float(np.max(times)),
        "baseline_rearm_us": float(cfg["baseline_rearm_us"]),
        "baseline_gain_dac": baseline,
        "target_gain_dac": target,
        "hard_flux_step": True,
        "qick_hard_step_duration_ns": float(3.0 / 430.08e6 * 1e9),
        "qick_sequence": "baseline, baseline_rearm, target_step, plotted_delay, qubit_probe, readout",
        "qua_sequence": "baseline, baseline_rearm, target_step, plotted_delay, qubit_probe, readout",
        **comparison,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    np.savez_compressed(
        output / "maps.npz",
        frequencies_mhz=frequencies,
        forward_times_us=runs["forward_step"]["times_us"],
        forward_magnitude_db=runs["forward_step"]["magnitude_db"],
        forward_phase_rad=runs["forward_step"]["phase_rad"],
        reverse_times_us=runs["reverse_step"]["times_us"],
        reverse_magnitude_db=runs["reverse_step"]["magnitude_db"],
        reverse_phase_rad=runs["reverse_step"]["phase_rad"],
        no_step_times_us=runs["no_step"]["times_us"],
        no_step_magnitude_db=runs["no_step"]["magnitude_db"],
        no_step_phase_rad=runs["no_step"]["phase_rad"],
    )
    _save_csv(output / "raw_maps.csv", frequencies, runs)
    _save_plot(output / "comparison.png", frequencies, runs, comparison)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
