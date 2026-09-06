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
GAIN_START_DAC = 0
GAIN_STOP_DAC = 22200
GAIN_STEP_DAC = 925
ROUNDS = 3
SHOTS_PER_POINT_PER_ROUND = 40
EXCURSION_GAIN = -20000.0
EXCURSION_HOLD_US = 1.0
HOST_WATCHDOG_S = 2.0
RANDOM_SEED = 20260905
MAX_ABS_PEAK_POPULATION_DIFFERENCE = 0.12
METHODS = ("passive_1000", "no_reset_25", "active_25", "active_100")


def _method_config(method):
    values = {
        "passive_1000": ("none", 1000.0, "passive"),
        "no_reset_25": ("none", 25.0, "active"),
        "active_25": ("opx_unbounded", 25.0, "active"),
        "active_100": ("opx_unbounded", 100.0, "active_100"),
    }
    try:
        return values[str(method)]
    except KeyError as exc:
        raise ValueError(f"unknown flux-cycle Rabi method {method!r}") from exc


def _write_json(path, values):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import json_safe

    Path(path).write_text(json.dumps(json_safe(values), indent=2, sort_keys=True) + "\n")


def _output_directory(outer_folder):
    now = datetime.now()
    day = Path(outer_folder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_flux_cycle_Rabi"
    output.mkdir(parents=True, exist_ok=False)
    return output, now


def _load_method_frequencies(path):
    values = json.loads(Path(path).read_text())
    fits = values["fits"]
    frequencies = {
        "passive": float(fits["passive_1000"]["center_mhz"]),
        "active": float(fits["active_25"]["center_mhz"]),
        "active_100": float(fits["active_100"]["center_mhz"]),
    }
    if not np.all(np.isfinite(list(frequencies.values()))):
        raise ValueError("spectroscopy centers must be finite")
    return frequencies


def _curves(accumulated, bundle, read_cycles):
    curves = {}
    errors = {}
    threshold = int(bundle.payload.excited_threshold)
    for method in METHODS:
        i_values = np.concatenate(accumulated[method]["i"], axis=1)
        q_values = np.concatenate(accumulated[method]["q"], axis=1)
        raw_i = np.rint(i_values * int(read_cycles)).astype(np.int64)
        raw_q = np.rint(q_values * int(read_cycles)).astype(np.int64)
        projected = bundle.payload.project(raw_i, raw_q)
        excited = projected > threshold
        population = np.mean(excited, axis=1)
        shots = excited.shape[1]
        curves[method] = population
        errors[method] = np.sqrt(population * (1.0 - population) / shots)
    return curves, errors


def _write_csv(path, gains, curves, errors):
    fields = ["gain_dac"]
    for method in METHODS:
        fields.extend((f"{method}_population", f"{method}_sem"))
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, gain in enumerate(gains):
            row = {"gain_dac": int(gain)}
            for method in METHODS:
                row[f"{method}_population"] = float(curves[method][index])
                row[f"{method}_sem"] = float(errors[method][index])
            writer.writerow(row)


def _plot(path, gains, curves, errors, evaluation):
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    labels = {
        "passive_1000": "no reset, 1000 us",
        "no_reset_25": "no reset, 25 us",
        "active_25": "active reset, 25 us",
        "active_100": "active reset, 100 us",
    }
    fig, axis = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
    for method in METHODS:
        axis.errorbar(
            gains,
            curves[method],
            yerr=errors[method],
            marker="o",
            markersize=3,
            linewidth=1,
            capsize=2,
            label=labels[method],
        )
        axis.axvline(
            evaluation["metrics"][method]["peak_gain"],
            linewidth=0.8,
            alpha=0.35,
        )
    axis.set(
        xlabel="Qubit gain [DAC]",
        ylabel="Excited fraction",
        title=f"q3 exact flux-cycle Rabi: {evaluation['diagnosis']}",
    )
    axis.grid(alpha=0.25)
    axis.legend()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(f"Expected qick 0.2.133, found {qick.__version__}")

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import evaluate_flux_cycle_rabi
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import q3_benchmark_settings
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import acquire_calibration, save_calibration, save_raw_calibration, validate_confident_calibration
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import acquire_pulse_sweep_iq
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.t1_flux_ramp_frequency_retune_q3 import _latest_result

    output_dir, now = _output_directory(outerFolder)
    print(f"output={output_dir}")
    diagnostic_path = _latest_result(outerFolder)
    frequencies = _load_method_frequencies(diagnostic_path)
    gains = np.arange(
        GAIN_START_DAC,
        GAIN_STOP_DAC + GAIN_STEP_DAC,
        GAIN_STEP_DAC,
        dtype=int,
    )
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
            "purpose": "exact flux-cycle Rabi at short active-reset intervals",
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
    accumulated = {method: {"i": [], "q": []} for method in METHODS}
    raw_output = {"gains_dac": gains}
    rng = np.random.default_rng(RANDOM_SEED)
    started = time.monotonic()
    try:
        for round_index in range(ROUNDS):
            for method_index in rng.permutation(len(METHODS)):
                method = METHODS[int(method_index)]
                reset_scheme, delay_us, frequency_key = _method_config(method)
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
                    "reset_pi_freq": frequencies[frequency_key],
                    "reset_pi_gain": int(BaseConfig["qubit_pi_gain"]),
                })
                i_values, q_values, telemetry = acquire_pulse_sweep_iq(
                    soc,
                    soccfg,
                    cfg,
                    gains=gains,
                    pulses=1,
                    frequency_mhz=frequencies[frequency_key],
                    shots=SHOTS_PER_POINT_PER_ROUND,
                    pulse_placement="park",
                    do_excursion=True,
                    excursion_gain=EXCURSION_GAIN,
                    flux_hold_us=EXCURSION_HOLD_US,
                    reset_scheme=reset_scheme,
                )
                accumulated[method]["i"].append(i_values)
                accumulated[method]["q"].append(q_values)
                raw_output[f"round_{round_index}_{method}_i"] = i_values
                raw_output[f"round_{round_index}_{method}_q"] = q_values
                raw_output[f"round_{round_index}_{method}_telemetry"] = np.asarray(
                    [telemetry["blocks"], telemetry["records"]], dtype=np.int32
                )
    finally:
        reset_gens = getattr(soc, "reset_gens", None)
        if callable(reset_gens):
            reset_gens()
    elapsed_s = time.monotonic() - started
    curves, errors = _curves(accumulated, bundle, read_cycles)
    evaluation = evaluate_flux_cycle_rabi(
        gains,
        curves,
        max_abs_peak_population_difference=MAX_ABS_PEAK_POPULATION_DIFFERENCE,
    )
    result = {
        "source_commit": source_commit,
        "diagnostic_result": str(diagnostic_path),
        "elapsed_s": elapsed_s,
        "frequencies_mhz": frequencies,
        "gains_dac": gains,
        "rounds": ROUNDS,
        "shots_per_point_per_round": SHOTS_PER_POINT_PER_ROUND,
        "excursion_gain": EXCURSION_GAIN,
        "excursion_hold_us": EXCURSION_HOLD_US,
        "curves": curves,
        "errors": errors,
        "evaluation": evaluation,
    }
    np.savez_compressed(output_dir / "raw_iq.npz", **raw_output)
    _write_json(output_dir / "result.json", result)
    _write_csv(output_dir / "rabi.csv", gains, curves, errors)
    _plot(output_dir / "rabi.png", gains, curves, errors, evaluation)
    print(f"status={evaluation['status']}")
    print(f"diagnosis={evaluation['diagnosis']}")
    for method in METHODS:
        metric = evaluation["metrics"][method]
        print(
            f"{method} peak_gain={metric['peak_gain']} "
            f"peak_population={metric['peak_population']:.4f}"
        )


if __name__ == "__main__":
    main()
