import csv
from datetime import datetime
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


from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    READOUT_THERMALIZATION_US,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    ReferenceAxis,
    fit_spectroscopy_peak,
    json_safe,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_q3 import (
    OPX_OVERRIDES,
    _git_commit,
    _plot_calibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import (
    q3_benchmark_settings,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
    acquire_calibration,
    save_calibration,
    save_raw_calibration,
    validate_confident_calibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
    acquire_frequency_sweep_iq,
)


QUBIT = "q3"
CALIBRATION_SHOTS = 1000
FREQUENCY_MIN_MHZ = 4335.0
FREQUENCY_MAX_MHZ = 4380.0
FREQUENCY_STEP_MHZ = 0.5
ROUNDS = 2
SHOTS_PER_POINT_PER_ROUND = 10
EXCURSION_GAIN = -20000
HISTORY_HOLDS_US = (1.0, 750.0)
PARK_RECOVERY_US = (10.0, 1000.0)
RANDOM_SEED = 20260906


def _conditions():
    return tuple(
        {
            "name": f"history_{int(history)}_recovery_{int(recovery)}",
            "history_hold_us": float(history),
            "park_recovery_us": float(recovery),
        }
        for recovery in PARK_RECOVERY_US
        for history in HISTORY_HOLDS_US
    )


def _output_dir():
    now = datetime.now()
    day = Path(outerFolder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_park_history_spectroscopy"
    output.mkdir(parents=True, exist_ok=False)
    return output


def _write_json(path, values):
    Path(path).write_text(json.dumps(json_safe(values), indent=2, sort_keys=True) + "\n")


def _curves(frequencies, conditions, samples, reference_axis):
    curves = {}
    fits = {}
    fit_errors = {}
    for condition in conditions:
        name = condition["name"]
        i_values = np.concatenate(samples[name]["i"], axis=1)
        q_values = np.concatenate(samples[name]["q"], axis=1)
        populations = reference_axis.population(i_values, q_values)
        mean = np.mean(populations, axis=1)
        sem = np.std(populations, axis=1, ddof=1) / np.sqrt(populations.shape[1])
        curves[name] = {
            "population": mean,
            "sem": sem,
            "shots_per_point": int(populations.shape[1]),
        }
        try:
            fits[name] = fit_spectroscopy_peak(frequencies, mean)
        except Exception as exc:
            fit_errors[name] = f"{type(exc).__name__}: {exc}"
    return curves, fits, fit_errors


def _write_csv(path, frequencies, conditions, curves):
    fields = ["frequency_mhz"]
    for condition in conditions:
        name = condition["name"]
        fields.extend((f"{name}_population", f"{name}_sem"))
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, frequency in enumerate(frequencies):
            row = {"frequency_mhz": float(frequency)}
            for condition in conditions:
                name = condition["name"]
                row[f"{name}_population"] = float(curves[name]["population"][index])
                row[f"{name}_sem"] = float(curves[name]["sem"][index])
            writer.writerow(row)


def _plot(path, frequencies, conditions, curves, fits):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True, constrained_layout=True)
    for axis, condition in zip(axes.ravel(), conditions):
        name = condition["name"]
        axis.errorbar(
            frequencies,
            curves[name]["population"],
            yerr=curves[name]["sem"],
            fmt=".",
            markersize=3,
            linewidth=0.8,
        )
        if name in fits:
            axis.axvline(fits[name]["center_mhz"], color="C3", linewidth=1)
            title = (
                f"history={condition['history_hold_us']:.0f} us, "
                f"recovery={condition['park_recovery_us']:.0f} us\n"
                f"center={fits[name]['center_mhz']:.3f} MHz, "
                f"contrast={fits[name]['contrast']:.3f}"
            )
        else:
            title = (
                f"history={condition['history_hold_us']:.0f} us, "
                f"recovery={condition['park_recovery_us']:.0f} us"
            )
        axis.set_title(title)
        axis.set_ylabel("Projected excited population")
        axis.grid(alpha=0.2)
    for axis in axes[-1]:
        axis.set_xlabel("Qubit drive frequency [MHz]")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(f"This test requires qick 0.2.133, found {qick.__version__}")
    output = _output_dir()
    print(f"output={output}")
    soc, soccfg = makeProxy()
    settings = q3_benchmark_settings()
    cfg = dict(BaseConfig)
    cfg.update(OPX_OVERRIDES)
    cfg.update(settings.opx_overrides())
    cfg.update({
        "ff_gain": int(EXCURSION_GAIN),
        "do_ff": True,
        "opx_unbounded_watchdog_s": 2.0,
    })
    conditions = _conditions()
    frequencies = np.arange(
        FREQUENCY_MIN_MHZ,
        FREQUENCY_MAX_MHZ + FREQUENCY_STEP_MHZ / 2.0,
        FREQUENCY_STEP_MHZ,
    )
    metadata = {
        "created": datetime.now().isoformat(),
        "source_commit": _git_commit(),
        "qick_version": str(qick.__version__),
        "qubit": QUBIT,
        "calibration_shots": int(CALIBRATION_SHOTS),
        "frequency_min_mhz": float(frequencies[0]),
        "frequency_max_mhz": float(frequencies[-1]),
        "frequency_step_mhz": float(FREQUENCY_STEP_MHZ),
        "rounds": int(ROUNDS),
        "shots_per_point_per_round": int(SHOTS_PER_POINT_PER_ROUND),
        "excursion_gain": int(EXCURSION_GAIN),
        "conditions": conditions,
        "park_lifecycle": "persistent_hard_step",
        "payload_order": "history_then_park_recovery_then_pi_then_readout",
        "reset_scheme": "opx_unbounded",
        "config": cfg,
    }
    _write_json(output / "run_metadata.json", metadata)
    calibration_cfg = dict(cfg)
    calibration_cfg.update({
        "opx_persistent_park": False,
        "opx_hard_flux_steps": False,
        "opx_reference_flux_cycle": False,
    })
    bundle, raw = acquire_calibration(
        soc,
        soccfg,
        calibration_cfg,
        shots=CALIBRATION_SHOTS,
        **settings.calibration_options(),
        metadata=metadata,
    )
    save_calibration(output / "calibration.json", bundle)
    save_raw_calibration(output / "calibration_raw.npz", raw)
    _plot_calibration(raw, bundle, output / "calibration.png")
    validate_confident_calibration(bundle, min_confident_fraction=0.2)
    read_cycles = int(soccfg.us2cycles(
        BaseConfig["read_length"], ro_ch=BaseConfig["ro_chs"][0]
    ))
    reference_axis = ReferenceAxis.from_centers(
        np.mean(raw["payload"]["ground"]["i"]) / read_cycles,
        np.mean(raw["payload"]["ground"]["q"]) / read_cycles,
        np.mean(raw["payload"]["excited"]["i"]) / read_cycles,
        np.mean(raw["payload"]["excited"]["q"]) / read_cycles,
    )
    cfg["opx_reset_calibration"] = bundle.to_dict()
    cfg["opx_inter_shot_delay_us"] = float(READOUT_THERMALIZATION_US)
    samples = {
        condition["name"]: {"i": [], "q": []}
        for condition in conditions
    }
    raw_output = {"frequencies_mhz": frequencies}
    rng = np.random.default_rng(RANDOM_SEED)
    started = time.perf_counter()
    try:
        for round_index in range(ROUNDS):
            for condition_index in rng.permutation(len(conditions)):
                condition = conditions[int(condition_index)]
                name = condition["name"]
                sweep = frequencies if round_index % 2 == 0 else frequencies[::-1]
                i_values, q_values, telemetry = acquire_frequency_sweep_iq(
                    soc,
                    soccfg,
                    cfg,
                    frequencies_mhz=sweep,
                    gain=int(BaseConfig["qubit_pi_gain"]),
                    pulses=1,
                    shots=SHOTS_PER_POINT_PER_ROUND,
                    pulse_placement="park_after_excursion",
                    do_excursion=True,
                    excursion_gain=EXCURSION_GAIN,
                    flux_hold_us=condition["history_hold_us"],
                    park_recovery_us=condition["park_recovery_us"],
                    reset_scheme="opx_unbounded",
                )
                order = np.argsort(sweep)
                i_values = i_values[order]
                q_values = q_values[order]
                samples[name]["i"].append(i_values)
                samples[name]["q"].append(q_values)
                raw_output[f"round_{round_index}_{name}_i"] = i_values
                raw_output[f"round_{round_index}_{name}_q"] = q_values
                raw_output[f"round_{round_index}_{name}_telemetry"] = np.asarray([
                    telemetry["blocks"], telemetry["records"]
                ], dtype=int)
                np.savez_compressed(output / "raw_iq_partial.npz", **raw_output)
                print(f"round={round_index + 1}/{ROUNDS} condition={name}")
    finally:
        reset_gens = getattr(soc, "reset_gens", None)
        if callable(reset_gens):
            reset_gens()
    elapsed_s = time.perf_counter() - started
    np.savez_compressed(output / "raw_iq.npz", **raw_output)
    curves, fits, fit_errors = _curves(
        frequencies, conditions, samples, reference_axis
    )
    _write_csv(output / "spectroscopy.csv", frequencies, conditions, curves)
    result = {
        "source_commit": _git_commit(),
        "elapsed_s": float(elapsed_s),
        "conditions": conditions,
        "reference_axis": reference_axis.to_dict(),
        "fits": fits,
        "fit_errors": fit_errors,
    }
    _write_json(output / "result.json", result)
    _plot(output / "park_history_spectroscopy.png", frequencies, conditions, curves, fits)
    for condition in conditions:
        name = condition["name"]
        if name in fits:
            print(
                f"{name} center={fits[name]['center_mhz']:.6f} MHz "
                f"FWHM={fits[name]['fwhm_mhz']:.6f} MHz "
                f"contrast={fits[name]['contrast']:.6f}"
            )
        else:
            print(f"{name} fit_error={fit_errors[name]}")


if __name__ == "__main__":
    main()
