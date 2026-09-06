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
    evaluate_t1_equivalence,
    fit_t1_decay,
    json_safe,
    wilson_interval,
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
    acquire_t1_sweep_iq,
)


QUBIT = "q3"
CALIBRATION_SHOTS = 1000
ROUNDS = 4
SHOTS_PER_METHOD_PER_ROUND = 125
T1_DELAYS_US = np.asarray([1.0, 35.0, 100.0, 250.0, 750.0])
EXCURSION_GAIN = -20000
PASSIVE_THERMALIZATION_US = 1000.0
ACTIVE_THERMALIZATION_US = READOUT_THERMALIZATION_US
METHODS = ("passive", "opx_unbounded")
RANDOM_SEED = 20260905
T1_MATCH_RELATIVE_TOLERANCE = 0.20
ENDPOINT_TOLERANCE = 0.12


def _output_dir():
    now = datetime.now()
    day = Path(outerFolder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_QUA_order_T1"
    output.mkdir(parents=True, exist_ok=False)
    return output


def _write_json(path, values):
    Path(path).write_text(json.dumps(json_safe(values), indent=2, sort_keys=True) + "\n")


def _method_delay(method):
    if method == "passive":
        return PASSIVE_THERMALIZATION_US
    if method == "opx_unbounded":
        return ACTIVE_THERMALIZATION_US
    raise ValueError(f"unknown method {method!r}")


def _method_scheme(method):
    if method == "passive":
        return "none"
    if method == "opx_unbounded":
        return "opx_unbounded"
    raise ValueError(f"unknown method {method!r}")


def _classify(bundle, i_values, q_values, read_cycles):
    raw_i = np.rint(np.asarray(i_values, dtype=float) * int(read_cycles)).astype(np.int64)
    raw_q = np.rint(np.asarray(q_values, dtype=float) * int(read_cycles)).astype(np.int64)
    projected = bundle.payload.project(raw_i, raw_q)
    excited = projected > int(bundle.payload.excited_threshold)
    return raw_i, raw_q, projected, excited


def _rows_from_runs(runs):
    rows = []
    for method in METHODS:
        for delay_index, delay_us in enumerate(T1_DELAYS_US):
            selected = [run for run in runs if run["method"] == method]
            excited = np.concatenate([
                run["excited"][delay_index].astype(bool) for run in selected
            ])
            count = int(np.count_nonzero(excited))
            low, high = wilson_interval(count, excited.size)
            rows.append({
                "method": method,
                "delay_index": int(delay_index),
                "delay_us": float(delay_us),
                "shots": int(excited.size),
                "excited": count,
                "excited_fraction": float(np.mean(excited)),
                "excited_ci95_low": float(low),
                "excited_ci95_high": float(high),
            })
    return rows


def _fits(rows):
    fits = {}
    errors = {}
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        try:
            fits[method] = fit_t1_decay(
                [row["delay_us"] for row in selected],
                [row["excited_fraction"] for row in selected],
                shots=[row["shots"] for row in selected],
            )
        except Exception as exc:
            errors[method] = f"{type(exc).__name__}: {exc}"
    return fits, errors


def _write_shots(path, runs):
    fields = (
        "round",
        "method",
        "delay_index",
        "delay_us",
        "shot_index",
        "i_raw",
        "q_raw",
        "projected",
        "excited",
    )
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for run in runs:
            for delay_index, delay_us in enumerate(T1_DELAYS_US):
                for shot_index in range(run["excited"].shape[1]):
                    writer.writerow({
                        "round": int(run["round"]),
                        "method": run["method"],
                        "delay_index": int(delay_index),
                        "delay_us": float(delay_us),
                        "shot_index": int(shot_index),
                        "i_raw": int(run["i_raw"][delay_index, shot_index]),
                        "q_raw": int(run["q_raw"][delay_index, shot_index]),
                        "projected": int(run["projected"][delay_index, shot_index]),
                        "excited": int(run["excited"][delay_index, shot_index]),
                    })


def _write_summary_csv(path, rows):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _plot(path, rows, fits, equivalence, runs):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    colors = {"passive": "C0", "opx_unbounded": "C1"}
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        x = np.asarray([row["delay_us"] for row in selected], dtype=float)
        y = np.asarray([row["excited_fraction"] for row in selected], dtype=float)
        low = np.asarray([row["excited_ci95_low"] for row in selected], dtype=float)
        high = np.asarray([row["excited_ci95_high"] for row in selected], dtype=float)
        axes[0].errorbar(
            x,
            y,
            yerr=(y - low, high - y),
            fmt="o",
            capsize=2,
            color=colors[method],
            label=method,
        )
        if method in fits:
            fit = fits[method]
            dense = np.logspace(np.log10(x.min()), np.log10(x.max()), 400)
            curve = fit["P0"] + (fit["P1"] - fit["P0"]) * np.exp(
                -dense / fit["tau_us"]
            )
            axes[0].plot(
                dense,
                curve,
                color=colors[method],
                label=f"{method} T1={fit['tau_us']:.1f} us",
            )
    elapsed = {
        method: sum(run["elapsed_s"] for run in runs if run["method"] == method)
        for method in METHODS
    }
    axes[1].bar(METHODS, [elapsed[method] for method in METHODS], color=["C0", "C1"])
    axes[0].set(
        xscale="log",
        xlabel="T1 delay [us]",
        ylabel="Excited fraction",
        title=f"QUA-order equivalence: {equivalence['status']}",
    )
    axes[1].set(ylabel="Acquisition time [s]", title="Matched shots and points")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
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
        "ff_hold": float(np.max(T1_DELAYS_US)),
        "t1_wait_us": float(np.max(T1_DELAYS_US)),
        "do_ff": True,
        "do_pi": True,
        "opx_max_payload_records_per_block": 480,
    })
    metadata = {
        "created": datetime.now().isoformat(),
        "source_commit": _git_commit(),
        "qick_version": str(qick.__version__),
        "qubit": QUBIT,
        "calibration_shots": int(CALIBRATION_SHOTS),
        "rounds": int(ROUNDS),
        "shots_per_method_per_round": int(SHOTS_PER_METHOD_PER_ROUND),
        "delays_us": T1_DELAYS_US,
        "excursion_gain": int(EXCURSION_GAIN),
        "park_gain": int(cfg["ff_park_gain"]),
        "passive_thermalization_us": float(PASSIVE_THERMALIZATION_US),
        "active_thermalization_us": float(ACTIVE_THERMALIZATION_US),
        "order": "shot_major",
        "park_lifecycle": "persistent_hard_step",
        "config": cfg,
    }
    _write_json(output / "run_metadata.json", metadata)
    bundle, raw = acquire_calibration(
        soc,
        soccfg,
        cfg,
        shots=CALIBRATION_SHOTS,
        **settings.calibration_options(),
        metadata=metadata,
    )
    validate_confident_calibration(bundle, min_confident_fraction=0.2)
    save_calibration(output / "calibration.json", bundle)
    save_raw_calibration(output / "calibration_raw.npz", raw)
    _plot_calibration(raw, bundle, output / "calibration.png")
    cfg["opx_reset_calibration"] = bundle.to_dict()
    rng = np.random.default_rng(RANDOM_SEED)
    runs = []
    for round_index in range(ROUNDS):
        for method_index in rng.permutation(len(METHODS)):
            method = METHODS[int(method_index)]
            run_cfg = dict(cfg)
            run_cfg["opx_inter_shot_delay_us"] = float(_method_delay(method))
            started = time.perf_counter()
            i_values, q_values, telemetry = acquire_t1_sweep_iq(
                soc,
                soccfg,
                run_cfg,
                delays_us=T1_DELAYS_US,
                shots=SHOTS_PER_METHOD_PER_ROUND,
                reset_scheme=_method_scheme(method),
            )
            elapsed_s = time.perf_counter() - started
            i_raw, q_raw, projected, excited = _classify(
                bundle,
                i_values,
                q_values,
                telemetry["read_length_cycles"],
            )
            runs.append({
                "round": int(round_index),
                "method": method,
                "elapsed_s": float(elapsed_s),
                "telemetry": telemetry,
                "i_raw": i_raw,
                "q_raw": q_raw,
                "projected": projected,
                "excited": excited,
            })
            print(
                f"round={round_index + 1}/{ROUNDS} method={method} "
                f"elapsed_s={elapsed_s:.3f}"
            )
    rows = _rows_from_runs(runs)
    fits, fit_errors = _fits(rows)
    if set(fits) == set(METHODS):
        equivalence = evaluate_t1_equivalence(
            fits["passive"],
            fits["opx_unbounded"],
            max_relative_tau_difference=T1_MATCH_RELATIVE_TOLERANCE,
            max_abs_p0_difference=ENDPOINT_TOLERANCE,
            max_abs_p1_difference=ENDPOINT_TOLERANCE,
        )
    else:
        equivalence = {"status": "fail", "reason": "one or both fits failed"}
    elapsed = {
        method: float(sum(run["elapsed_s"] for run in runs if run["method"] == method))
        for method in METHODS
    }
    speedup = elapsed["passive"] / elapsed["opx_unbounded"]
    _write_shots(output / "shots.csv", runs)
    _write_summary_csv(output / "summary.csv", rows)
    _write_json(output / "summary.json", {
        "equivalence": equivalence,
        "fits": fits,
        "fit_errors": fit_errors,
        "elapsed_s": elapsed,
        "speedup": float(speedup),
        "points": rows,
        "runs": [
            {
                "round": run["round"],
                "method": run["method"],
                "elapsed_s": run["elapsed_s"],
                "telemetry": run["telemetry"],
            }
            for run in runs
        ],
    })
    _plot(output / "qua_order_t1_equivalence.png", rows, fits, equivalence, runs)
    print(f"status={equivalence['status']}")
    for method in METHODS:
        if method in fits:
            print(f"{method} T1={fits[method]['tau_us']:.3f} us")
    print(f"speedup={speedup:.3f}")


if __name__ == "__main__":
    main()
