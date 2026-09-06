import csv
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

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


QUBIT = "q3"
CALIBRATION_SHOTS = 1000
MIN_CONFIDENT_STATE_FRACTION = 0.2
FREQUENCY_HALF_SPAN_MHZ = 20.0
FREQUENCY_STEP_MHZ = 0.5
ROUNDS = 3
SHOTS_PER_POINT_PER_ROUND = 40
EXCURSION_GAIN = -20000.0
EXCURSION_HOLD_US = 1.0
HOST_WATCHDOG_S = 2.0
RANDOM_SEED = 20260905
METHODS = ("passive_1000", "no_reset_25", "active_25", "active_100")


def _method_config(method):
    values = {
        "passive_1000": ("none", 1000.0),
        "no_reset_25": ("none", 25.0),
        "active_25": ("opx_unbounded", 25.0),
        "active_100": ("opx_unbounded", 100.0),
    }
    try:
        return values[str(method)]
    except KeyError as exc:
        raise ValueError(f"unknown flux-cycle spectroscopy method {method!r}") from exc


def _ordered_frequency_axis(frequencies, round_index):
    values = np.asarray(frequencies, dtype=float)
    return values if int(round_index) % 2 == 0 else values[::-1]


def _write_json(path, values):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import json_safe

    Path(path).write_text(json.dumps(json_safe(values), indent=2, sort_keys=True) + "\n")


def _output_directory(outer_folder):
    now = datetime.now()
    day = Path(outer_folder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_flux_cycle_spectroscopy"
    output.mkdir(parents=True, exist_ok=False)
    return output, now


def _fit_curves(frequencies, accumulated, reference_axis, fit_spectroscopy_peak):
    curves = {}
    fits = {}
    for method in METHODS:
        populations = []
        errors = []
        for frequency_index in range(len(frequencies)):
            i_values = np.concatenate(accumulated[method][frequency_index]["i"])
            q_values = np.concatenate(accumulated[method][frequency_index]["q"])
            projected = reference_axis.population(i_values, q_values)
            populations.append(float(np.mean(projected)))
            errors.append(float(np.std(projected, ddof=1) / np.sqrt(projected.size)))
        curves[method] = {
            "population": np.asarray(populations),
            "error": np.asarray(errors),
        }
        fits[method] = fit_spectroscopy_peak(frequencies, populations)
    return curves, fits


def _write_summary_csv(path, frequencies, curves):
    with Path(path).open("w", newline="") as handle:
        fields = ["frequency_mhz"]
        for method in METHODS:
            fields.extend((f"{method}_population", f"{method}_sem"))
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, frequency in enumerate(frequencies):
            row = {"frequency_mhz": float(frequency)}
            for method in METHODS:
                row[f"{method}_population"] = float(curves[method]["population"][index])
                row[f"{method}_sem"] = float(curves[method]["error"][index])
            writer.writerow(row)


def _plot(path, frequencies, curves, fits, evaluation):
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    labels = {
        "passive_1000": "no reset, 1000 us",
        "no_reset_25": "no reset, 25 us",
        "active_25": "active reset, 25 us",
        "active_100": "active reset, 100 us",
    }
    fig, axes = plt.subplots(2, 1, figsize=(10, 9), constrained_layout=True)
    for method in METHODS:
        axes[0].errorbar(
            frequencies,
            curves[method]["population"],
            yerr=curves[method]["error"],
            marker=".",
            markersize=3,
            linewidth=1,
            label=labels[method],
        )
        axes[0].axvline(fits[method]["center_mhz"], linewidth=0.8, alpha=0.5)
    axes[0].set(
        xlabel="Qubit drive frequency [MHz]",
        ylabel="Excited population",
        title="q3 spectroscopy under repeated flux-ramp/reset lifecycle",
    )
    axes[0].legend()
    x = np.arange(len(METHODS))
    centers = [fits[method]["center_mhz"] for method in METHODS]
    widths = [fits[method]["fwhm_mhz"] for method in METHODS]
    center_errors = [fits[method]["center_err_mhz"] for method in METHODS]
    width_errors = [fits[method]["fwhm_err_mhz"] for method in METHODS]
    axes[1].errorbar(x - 0.08, centers, yerr=center_errors, fmt="o", label="center")
    right = axes[1].twinx()
    right.errorbar(x + 0.08, widths, yerr=width_errors, fmt="s", color="tab:red", label="FWHM")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([labels[method] for method in METHODS], rotation=15)
    axes[1].set_ylabel("Center frequency [MHz]")
    right.set_ylabel("FWHM [MHz]", color="tab:red")
    axes[1].set_title(f"diagnosis={evaluation['diagnosis']}")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(f"Expected qick 0.2.133, found {qick.__version__}")

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import ReferenceAxis, evaluate_flux_cycle_spectroscopy, fit_spectroscopy_peak
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import q3_benchmark_settings
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import acquire_calibration, save_calibration, save_raw_calibration, validate_confident_calibration
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import acquire_frequency_sweep_iq

    output_dir, now = _output_directory(outerFolder)
    print(f"output={output_dir}")
    soc, soccfg = makeProxy()
    settings = q3_benchmark_settings()
    calibration_cfg = dict(BaseConfig)
    calibration_cfg.update(settings.opx_overrides())
    calibration_cfg.update({
        "relax_delay": 400.0,
        "opx_inter_shot_delay_us": 100.0,
        "opx_unbounded_watchdog_s": HOST_WATCHDOG_S,
    })
    try:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_repo_root, text=True
        ).strip()
    except Exception:
        source_commit = "unknown"
    bundle, raw = acquire_calibration(
        soc,
        soccfg,
        calibration_cfg,
        shots=CALIBRATION_SHOTS,
        **settings.calibration_options(),
        metadata={
            "qubit": QUBIT,
            "created": now.isoformat(),
            "source_commit": source_commit,
            "purpose": "flux-cycle spectroscopy at short active-reset intervals",
        },
    )
    validate_confident_calibration(
        bundle, min_confident_fraction=MIN_CONFIDENT_STATE_FRACTION
    )
    save_calibration(output_dir / "calibration.json", bundle)
    save_raw_calibration(output_dir / "calibration_raw.npz", raw)
    read_cycles = int(soccfg.us2cycles(
        BaseConfig["read_length"], ro_ch=BaseConfig["ro_chs"][0]
    ))
    reference_axis = ReferenceAxis.from_centers(
        np.mean(raw["payload"]["ground"]["i"]) / read_cycles,
        np.mean(raw["payload"]["ground"]["q"]) / read_cycles,
        np.mean(raw["payload"]["excited"]["i"]) / read_cycles,
        np.mean(raw["payload"]["excited"]["q"]) / read_cycles,
    )
    center = float(BaseConfig["qubit_pi_freq"])
    frequencies = np.arange(
        center - FREQUENCY_HALF_SPAN_MHZ,
        center + FREQUENCY_HALF_SPAN_MHZ + FREQUENCY_STEP_MHZ / 2.0,
        FREQUENCY_STEP_MHZ,
    )
    accumulated = {
        method: [dict(i=[], q=[]) for _ in frequencies] for method in METHODS
    }
    raw_output = {"frequencies_mhz": frequencies}
    rng = np.random.default_rng(RANDOM_SEED)
    started = time.monotonic()
    try:
        for round_index in range(ROUNDS):
            for method_index in rng.permutation(len(METHODS)):
                method = METHODS[int(method_index)]
                reset_scheme, delay_us = _method_config(method)
                sweep_frequencies = _ordered_frequency_axis(frequencies, round_index)
                cfg = dict(BaseConfig)
                cfg.update(settings.opx_overrides())
                cfg.update({
                    "shots": SHOTS_PER_POINT_PER_ROUND,
                    "reps": SHOTS_PER_POINT_PER_ROUND,
                    "relax_delay": delay_us,
                    "opx_inter_shot_delay_us": delay_us,
                    "opx_unbounded_watchdog_s": HOST_WATCHDOG_S,
                    "opx_reset_calibration": bundle.to_dict(),
                    "readout_after_park": True,
                    "reset_pi_freq": float(BaseConfig["qubit_pi_freq"]),
                    "reset_pi_gain": int(BaseConfig["qubit_pi_gain"]),
                })
                i_values, q_values, telemetry = acquire_frequency_sweep_iq(
                    soc,
                    soccfg,
                    cfg,
                    frequencies_mhz=sweep_frequencies,
                    gain=int(BaseConfig["qubit_pi_gain"]),
                    pulses=1,
                    shots=SHOTS_PER_POINT_PER_ROUND,
                    pulse_placement="park",
                    do_excursion=True,
                    excursion_gain=EXCURSION_GAIN,
                    flux_hold_us=EXCURSION_HOLD_US,
                    reset_scheme=reset_scheme,
                )
                order = np.argsort(sweep_frequencies)
                i_values = i_values[order]
                q_values = q_values[order]
                for frequency_index in range(len(frequencies)):
                    accumulated[method][frequency_index]["i"].append(
                        i_values[frequency_index]
                    )
                    accumulated[method][frequency_index]["q"].append(
                        q_values[frequency_index]
                    )
                raw_output[f"round_{round_index}_{method}_i"] = i_values
                raw_output[f"round_{round_index}_{method}_q"] = q_values
                raw_output[f"round_{round_index}_{method}_telemetry"] = np.asarray([
                    telemetry["blocks"], telemetry["records"]
                ], dtype=int)
    finally:
        reset_gens = getattr(soc, "reset_gens", None)
        if callable(reset_gens):
            reset_gens()
    elapsed_s = time.monotonic() - started
    np.savez_compressed(output_dir / "raw_iq.npz", **raw_output)
    curves, fits = _fit_curves(
        frequencies, accumulated, reference_axis, fit_spectroscopy_peak
    )
    evaluation = evaluate_flux_cycle_spectroscopy(fits)
    _write_summary_csv(output_dir / "spectroscopy.csv", frequencies, curves)
    result = {
        "source_commit": source_commit,
        "elapsed_s": elapsed_s,
        "methods": METHODS,
        "rounds": ROUNDS,
        "shots_per_point_per_round": SHOTS_PER_POINT_PER_ROUND,
        "frequency_min_mhz": float(frequencies[0]),
        "frequency_max_mhz": float(frequencies[-1]),
        "frequency_step_mhz": FREQUENCY_STEP_MHZ,
        "excursion_gain": EXCURSION_GAIN,
        "excursion_hold_us": EXCURSION_HOLD_US,
        "reference_axis": reference_axis.to_dict(),
        "fits": fits,
        "evaluation": evaluation,
    }
    _write_json(output_dir / "result.json", result)
    _plot(output_dir / "spectroscopy.png", frequencies, curves, fits, evaluation)
    print(f"diagnosis={evaluation['diagnosis']}")
    for method in METHODS:
        print(
            f"{method} center={fits[method]['center_mhz']:.6f} MHz "
            f"FWHM={fits[method]['fwhm_mhz']:.6f} MHz "
            f"contrast={fits[method]['contrast']:.6f}"
        )


if __name__ == "__main__":
    main()
