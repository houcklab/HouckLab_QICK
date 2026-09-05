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


from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
    AcquisitionTimeout,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    build_interleaved_schedule,
    summarize_records,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_q3 import (
    OPX_OVERRIDES,
    _git_commit,
    _json_safe,
    _plot_calibration,
    _run_custom_condition,
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


QUBIT = "q3"
CALIBRATION_SHOTS = 2000
BLOCKS = 4
SHOTS_PER_CONDITION_PER_BLOCK = 250
METHODS = ("none", "opx_unbounded")
MIN_CONFIDENT_STATE_FRACTION = 0.2
HOST_WATCHDOG_S = 2.0
RANDOM_SEED = 20260905
Q3_BENCHMARK_SETTINGS = q3_benchmark_settings()


def _write_json(path, values):
    Path(path).write_text(
        json.dumps(_json_safe(values), indent=2, sort_keys=True) + "\n"
    )


def _make_output_dir():
    now = datetime.now()
    day = Path(outerFolder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_unbounded"
    output.mkdir(parents=True, exist_ok=False)
    return output


def _summary_row(method, preparation, summary):
    low, high = summary["verification_excited_ci95"]
    return {
        "method": str(method),
        "preparation": int(preparation),
        "shots": int(summary["shots"]),
        "verification_excited": int(summary["verification_excited"]),
        "verification_excited_fraction": float(
            summary["verification_excited_fraction"]
        ),
        "verification_excited_ci95_low": float(low),
        "verification_excited_ci95_high": float(high),
        "verification_population": float(summary["verification_population"]),
        "mean_reset_attempts": float(summary["mean_reset_attempts"]),
        "p95_reset_attempts": float(summary["p95_reset_attempts"]),
        "p99_reset_attempts": float(summary["p99_reset_attempts"]),
        "max_reset_attempts": int(summary["max_reset_attempts"]),
        "mean_pi_pulses": float(summary["mean_pi_pulses"]),
    }


def _write_summary_csv(path, rows):
    rows = list(rows)
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _plot_summary(rows, accumulated, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [
        f"{row['method']}\nprep {'e' if row['preparation'] else 'g'}"
        for row in rows
    ]
    residuals = [row["verification_excited_fraction"] for row in rows]
    lower = [
        value - row["verification_excited_ci95_low"]
        for value, row in zip(residuals, rows)
    ]
    upper = [
        row["verification_excited_ci95_high"] - value
        for value, row in zip(residuals, rows)
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    axes[0].bar(labels, residuals, yerr=(lower, upper), capsize=4)
    axes[0].set(title="Verification excited fraction", ylabel="fraction")
    unbounded_rows = [row for row in rows if row["method"] == "opx_unbounded"]
    attempts = np.arange(len(unbounded_rows))
    width = 0.25
    axes[1].bar(
        attempts - width,
        [row["mean_reset_attempts"] for row in unbounded_rows],
        width,
        label="mean",
    )
    axes[1].bar(
        attempts,
        [row["p95_reset_attempts"] for row in unbounded_rows],
        width,
        label="p95",
    )
    axes[1].bar(
        attempts + width,
        [row["p99_reset_attempts"] for row in unbounded_rows],
        width,
        label="p99",
    )
    axes[1].set_xticks(
        attempts,
        [f"prep {'e' if row['preparation'] else 'g'}" for row in unbounded_rows],
    )
    axes[1].set(title="Reset attempts", ylabel="attempts")
    axes[1].legend()
    for preparation, label in ((0, "prepared g"), (1, "prepared e")):
        records = accumulated.get(("opx_unbounded", preparation), [])
        values = np.sort(
            np.asarray([record.reset_attempts for record in records], dtype=float)
        )
        if values.size:
            survival = 1.0 - np.arange(values.size) / values.size
            axes[2].step(values, survival, where="post", label=label)
    axes[2].set(
        title="Attempt-count survival",
        xlabel="executed attempts",
        ylabel="P(attempts ≥ x)",
        yscale="log",
    )
    axes[2].legend()
    for axis in axes:
        axis.grid(alpha=0.25)
    axes[0].tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    output_dir = _make_output_dir()
    print(f"\nUnbounded OPX-style active reset | {QUBIT}")
    print(f"Output: {output_dir}\n")

    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(
            f"This prototype is validated for qick 0.2.133, found {qick.__version__}"
        )
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg.update(OPX_OVERRIDES)
    cfg.update(Q3_BENCHMARK_SETTINGS.opx_overrides())
    cfg["opx_unbounded_watchdog_s"] = float(HOST_WATCHDOG_S)
    cfg.pop("flux_tail_compensation", None)
    schedule = build_interleaved_schedule(
        methods=METHODS,
        blocks=BLOCKS,
        seed=RANDOM_SEED,
    )
    metadata = {
        "qubit": QUBIT,
        "created": datetime.now().isoformat(),
        "source_commit": _git_commit(),
        "qick_version": str(qick.__version__),
        "calibration_shots": int(CALIBRATION_SHOTS),
        "blocks": int(BLOCKS),
        "shots_per_condition_per_block": int(
            SHOTS_PER_CONDITION_PER_BLOCK
        ),
        "methods": METHODS,
        "normal_exit_condition": "confirmed_ground",
        "host_watchdog_s": float(HOST_WATCHDOG_S),
        "random_seed": int(RANDOM_SEED),
        "schedule": schedule,
        "opx_overrides": cfg,
    }
    _write_json(output_dir / "run_metadata.json", metadata)

    print("Acquiring timing-matched calibration ...", flush=True)
    bundle, raw = acquire_calibration(
        soc,
        soccfg,
        cfg,
        shots=int(CALIBRATION_SHOTS),
        **Q3_BENCHMARK_SETTINGS.calibration_options(),
        metadata=metadata,
    )
    validate_confident_calibration(
        bundle,
        min_confident_fraction=MIN_CONFIDENT_STATE_FRACTION,
    )
    save_calibration(output_dir / "calibration.json", bundle)
    save_raw_calibration(output_dir / "calibration_raw.npz", raw)
    _plot_calibration(raw, bundle, output_dir / "calibration.png")

    accumulated = {}
    csv_path = output_dir / "shots.csv"
    assembly_path = output_dir / "opx_unbounded.asm"
    for index, (block, method, preparation) in enumerate(schedule, start=1):
        print(
            f"[{index:02d}/{len(schedule):02d}] block={block + 1} "
            f"method={method} prep={'e' if preparation else 'g'}",
            flush=True,
        )
        try:
            records = _run_custom_condition(
                soc,
                soccfg,
                cfg,
                bundle,
                method=method,
                preparation=preparation,
                shots=int(SHOTS_PER_CONDITION_PER_BLOCK),
                block=block,
                csv_path=csv_path,
                assembly_path=assembly_path,
            )
        except AcquisitionTimeout as exc:
            _write_json(
                output_dir / "watchdog_abort.json",
                {
                    "block": int(block),
                    "method": str(method),
                    "preparation": int(preparation),
                    "completed_shots": int(exc.completed_shots),
                    "requested_shots": int(SHOTS_PER_CONDITION_PER_BLOCK),
                    "watchdog_s": float(HOST_WATCHDOG_S),
                },
            )
            raise
        accumulated.setdefault((method, preparation), []).extend(records)
        partial = {
            f"{key[0]}_prep_{key[1]}": summarize_records(
                values,
                bundle.reference_axis,
                bundle.loop,
            )
            for key, values in accumulated.items()
        }
        _write_json(output_dir / "summary_partial.json", partial)

    rows = [
        _summary_row(
            method,
            preparation,
            summarize_records(
                values,
                bundle.reference_axis,
                bundle.loop,
            ),
        )
        for (method, preparation), values in sorted(accumulated.items())
    ]
    _write_json(output_dir / "summary.json", rows)
    _write_summary_csv(output_dir / "summary.csv", rows)
    _plot_summary(rows, accumulated, output_dir / "unbounded_reset.png")
    print("\nResults:")
    for row in rows:
        print(
            f"  {row['method']:<15} "
            f"prep={'e' if row['preparation'] else 'g'} "
            f"P(e)={row['verification_excited_fraction']:.4f} "
            f"mean={row['mean_reset_attempts']:.3f} "
            f"p95={row['p95_reset_attempts']:.1f} "
            f"p99={row['p99_reset_attempts']:.1f} "
            f"max={row['max_reset_attempts']}"
        )
    print(f"Completed: {output_dir}")


if __name__ == "__main__":
    main()
