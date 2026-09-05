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
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    evaluate_attempt_limit_sweep,
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
MAX_RESET_ATTEMPTS = (8, 12, 16, 24)
FEEDBACK_SYNCDELAY_US = 8.0
CALIBRATION_SHOTS = 2000
BLOCKS = 4
SHOTS_PER_CONDITION_PER_BLOCK = 250
MIN_CONFIDENT_STATE_FRACTION = 0.2
MAX_TIMEOUT_FRACTION = 0.01
MAX_VERIFICATION_EXCITED_FRACTION = 0.10
RANDOM_SEED = 20260905
Q3_BENCHMARK_SETTINGS = q3_benchmark_settings()


def _write_json(path, values):
    Path(path).write_text(
        json.dumps(_json_safe(values), indent=2, sort_keys=True) + "\n"
    )


def _make_output_dir():
    now = datetime.now()
    day = Path(outerFolder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_attempt_limit_sweep"
    output.mkdir(parents=True, exist_ok=False)
    return output


def _flatten_row(max_attempts, preparation, summary):
    low, high = summary["verification_excited_ci95"]
    return {
        "max_reset_attempts": int(max_attempts),
        "preparation": int(preparation),
        "shots": int(summary["shots"]),
        "timeouts": int(summary["timeouts"]),
        "timeout_fraction": float(summary["timeout_fraction"]),
        "verification_excited": int(summary["verification_excited"]),
        "verification_excited_fraction": float(
            summary["verification_excited_fraction"]
        ),
        "verification_excited_ci95_low": float(low),
        "verification_excited_ci95_high": float(high),
        "verification_excited_confirmed_fraction": float(
            summary["verification_excited_confirmed_fraction"]
        ),
        "verification_population": float(summary["verification_population"]),
        "mean_reset_attempts": float(summary["mean_reset_attempts"]),
        "p95_reset_attempts": float(summary["p95_reset_attempts"]),
        "mean_pi_pulses": float(summary["mean_pi_pulses"]),
    }


def _write_summary_csv(path, rows):
    rows = list(rows)
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _plot_summary(rows, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    for preparation, label in ((0, "prepared g"), (1, "prepared e")):
        selected = sorted(
            (row for row in rows if int(row["preparation"]) == preparation),
            key=lambda row: row["max_reset_attempts"],
        )
        attempts = [row["max_reset_attempts"] for row in selected]
        residuals = [row["verification_excited_fraction"] for row in selected]
        low = [
            value - row["verification_excited_ci95_low"]
            for value, row in zip(residuals, selected)
        ]
        high = [
            row["verification_excited_ci95_high"] - value
            for value, row in zip(residuals, selected)
        ]
        axes[0].errorbar(
            attempts,
            residuals,
            yerr=(low, high),
            marker="o",
            label=label,
        )
        axes[1].plot(
            attempts,
            [row["timeout_fraction"] for row in selected],
            marker="o",
            label=label,
        )
        axes[2].plot(
            attempts,
            [row["mean_reset_attempts"] for row in selected],
            marker="o",
            label=label,
        )
    axes[0].axhline(MAX_VERIFICATION_EXCITED_FRACTION, color="k", ls="--")
    axes[1].axhline(MAX_TIMEOUT_FRACTION, color="k", ls="--")
    axes[0].set(title="Verification excited fraction", ylabel="fraction")
    axes[1].set(title="Max-iteration fraction", ylabel="fraction")
    axes[2].set(title="Mean executed attempts", ylabel="attempts")
    for axis in axes:
        axis.set_xlabel("maximum reset attempts")
        axis.set_xticks(MAX_RESET_ATTEMPTS)
        axis.grid(alpha=0.25)
        axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    limits = tuple(int(value) for value in MAX_RESET_ATTEMPTS)
    if not limits or len(set(limits)) != len(limits):
        raise ValueError("MAX_RESET_ATTEMPTS must contain unique values")
    output_dir = _make_output_dir()
    print(f"\nOPX-style active-reset attempt-limit sweep | {QUBIT}")
    print(f"Output: {output_dir}\n")

    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(
            f"This prototype is validated for qick 0.2.133, found {qick.__version__}"
        )
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg.update(OPX_OVERRIDES)
    cfg["opx_feedback_syncdelay_us"] = float(FEEDBACK_SYNCDELAY_US)
    cfg.pop("flux_tail_compensation", None)
    rng = np.random.default_rng(RANDOM_SEED)
    conditions = [(limit, preparation) for limit in limits for preparation in (0, 1)]
    schedule = []
    for block in range(int(BLOCKS)):
        for index in rng.permutation(len(conditions)):
            limit, preparation = conditions[int(index)]
            schedule.append((block, limit, preparation))
    metadata = {
        "qubit": QUBIT,
        "created": datetime.now().isoformat(),
        "source_commit": _git_commit(),
        "qick_version": str(qick.__version__),
        "max_reset_attempts": limits,
        "feedback_syncdelay_us": float(FEEDBACK_SYNCDELAY_US),
        "calibration_shots": int(CALIBRATION_SHOTS),
        "blocks": int(BLOCKS),
        "shots_per_condition_per_block": int(SHOTS_PER_CONDITION_PER_BLOCK),
        "max_timeout_fraction": float(MAX_TIMEOUT_FRACTION),
        "max_verification_excited_fraction": float(
            MAX_VERIFICATION_EXCITED_FRACTION
        ),
        "random_seed": int(RANDOM_SEED),
        "schedule": schedule,
        "base_opx_overrides": OPX_OVERRIDES,
    }
    _write_json(output_dir / "run_metadata.json", metadata)

    print("Acquiring shared timing-matched calibration ...", flush=True)
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
    for index, (block, max_attempts, preparation) in enumerate(schedule, start=1):
        print(
            f"[{index:02d}/{len(schedule):02d}] block={block + 1} "
            f"max={max_attempts} prep={'e' if preparation else 'g'}",
            flush=True,
        )
        attempt_dir = output_dir / f"max_{max_attempts:02d}"
        attempt_dir.mkdir(exist_ok=True)
        run_cfg = dict(cfg)
        run_cfg["opx_max_reset_attempts"] = int(max_attempts)
        records = _run_custom_condition(
            soc,
            soccfg,
            run_cfg,
            bundle,
            method="opx",
            preparation=preparation,
            shots=int(SHOTS_PER_CONDITION_PER_BLOCK),
            block=block,
            csv_path=attempt_dir / "shots.csv",
            assembly_path=attempt_dir / "opx_reset.asm",
        )
        accumulated.setdefault((max_attempts, preparation), []).extend(records)
        partial = [
            _flatten_row(
                limit,
                prep,
                summarize_records(values, bundle.reference_axis, bundle.loop),
            )
            for (limit, prep), values in sorted(accumulated.items())
        ]
        _write_json(output_dir / "summary_partial.json", partial)

    rows = [
        _flatten_row(
            limit,
            prep,
            summarize_records(values, bundle.reference_axis, bundle.loop),
        )
        for (limit, prep), values in sorted(accumulated.items())
    ]
    evaluation = evaluate_attempt_limit_sweep(
        rows,
        max_timeout_fraction=MAX_TIMEOUT_FRACTION,
        max_verification_excited_fraction=MAX_VERIFICATION_EXCITED_FRACTION,
    )
    _write_json(output_dir / "summary.json", rows)
    _write_json(output_dir / "evaluation.json", evaluation)
    _write_summary_csv(output_dir / "summary.csv", rows)
    _plot_summary(rows, output_dir / "attempt_limit_sweep.png")
    print("\nResults:")
    for row in rows:
        print(
            f"  max={row['max_reset_attempts']:2d} "
            f"prep={'e' if row['preparation'] else 'g'} "
            f"P(e)={row['verification_excited_fraction']:.4f} "
            f"timeouts={row['timeout_fraction']:.4f} "
            f"attempts={row['mean_reset_attempts']:.3f}"
        )
    selected = evaluation["selected_max_reset_attempts"]
    if selected is None:
        print("\nNo tested attempt limit met both promotion limits.")
    else:
        print(f"\nSelected maximum reset attempts: {selected}")
    print(f"Completed: {output_dir}")


if __name__ == "__main__":
    main()
