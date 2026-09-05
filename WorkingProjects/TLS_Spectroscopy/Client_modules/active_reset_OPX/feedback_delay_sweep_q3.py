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
    evaluate_feedback_delay_sweep,
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
FEEDBACK_SYNCDELAYS_US = (8.0, 12.0, 16.0, 24.0, 32.0)
CALIBRATION_SHOTS = 2000
SHOTS_PER_PREPARATION = 1000
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
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_feedback_delay_sweep"
    output.mkdir(parents=True, exist_ok=False)
    return output


def _delay_directory_name(delay_us):
    return f"feedback_{float(delay_us):06.2f}_us".replace(".", "p")


def _flatten_row(delay_us, preparation, summary, bundle):
    low, high = summary["verification_excited_ci95"]
    return {
        "feedback_syncdelay_us": float(delay_us),
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
        "loop_ground_accept": float(bundle.loop.holdout["ground_accept"]),
        "loop_excited_fire": float(bundle.loop.holdout["excited_fire"]),
        "loop_false_ground_accept": float(
            bundle.loop.holdout["false_ground_accept"]
        ),
        "loop_false_pi": float(bundle.loop.holdout["false_pi"]),
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
            key=lambda row: row["feedback_syncdelay_us"],
        )
        delays = [row["feedback_syncdelay_us"] for row in selected]
        residuals = [row["verification_excited_fraction"] for row in selected]
        low = [
            value - row["verification_excited_ci95_low"]
            for value, row in zip(residuals, selected)
        ]
        high = [
            row["verification_excited_ci95_high"] - value
            for value, row in zip(residuals, selected)
        ]
        axes[0].errorbar(delays, residuals, yerr=(low, high), marker="o", label=label)
        axes[1].plot(
            delays,
            [row["timeout_fraction"] for row in selected],
            marker="o",
            label=label,
        )
        axes[2].plot(
            delays,
            [row["mean_reset_attempts"] for row in selected],
            marker="o",
            label=label,
        )
    axes[0].axhline(MAX_VERIFICATION_EXCITED_FRACTION, color="k", ls="--")
    axes[1].axhline(MAX_TIMEOUT_FRACTION, color="k", ls="--")
    axes[0].set(title="Verification excited fraction", ylabel="fraction")
    axes[1].set(title="Max-iteration fraction", ylabel="fraction")
    axes[2].set(title="Mean reset attempts", ylabel="attempts")
    for axis in axes:
        axis.set_xlabel("feedback sync delay (us)")
        axis.grid(alpha=0.25)
        axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    delays = tuple(float(value) for value in FEEDBACK_SYNCDELAYS_US)
    if not delays or len(set(delays)) != len(delays):
        raise ValueError("FEEDBACK_SYNCDELAYS_US must contain unique values")
    output_dir = _make_output_dir()
    print(f"\nOPX-style active-reset feedback-delay sweep | {QUBIT}")
    print(f"Output: {output_dir}\n")

    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(
            f"This prototype is validated for qick 0.2.133, found {qick.__version__}"
        )
    soc, soccfg = makeProxy()
    metadata = {
        "qubit": QUBIT,
        "created": datetime.now().isoformat(),
        "source_commit": _git_commit(),
        "qick_version": str(qick.__version__),
        "feedback_syncdelays_us": delays,
        "calibration_shots": int(CALIBRATION_SHOTS),
        "shots_per_preparation": int(SHOTS_PER_PREPARATION),
        "max_timeout_fraction": float(MAX_TIMEOUT_FRACTION),
        "max_verification_excited_fraction": float(
            MAX_VERIFICATION_EXCITED_FRACTION
        ),
        "random_seed": int(RANDOM_SEED),
        "base_opx_overrides": OPX_OVERRIDES,
    }
    _write_json(output_dir / "run_metadata.json", metadata)

    rng = np.random.default_rng(RANDOM_SEED)
    delay_order = [delays[int(index)] for index in rng.permutation(len(delays))]
    rows = []
    for delay_index, delay_us in enumerate(delay_order, start=1):
        delay_dir = output_dir / _delay_directory_name(delay_us)
        delay_dir.mkdir()
        cfg = dict(BaseConfig)
        cfg.update(OPX_OVERRIDES)
        cfg["opx_feedback_syncdelay_us"] = float(delay_us)
        cfg.pop("flux_tail_compensation", None)
        calibration_metadata = dict(metadata)
        calibration_metadata["feedback_syncdelay_us"] = float(delay_us)
        print(
            f"[{delay_index}/{len(delay_order)}] feedback sync delay={delay_us:g} us",
            flush=True,
        )
        bundle, raw = acquire_calibration(
            soc,
            soccfg,
            cfg,
            shots=int(CALIBRATION_SHOTS),
            **Q3_BENCHMARK_SETTINGS.calibration_options(),
            metadata=calibration_metadata,
        )
        validate_confident_calibration(
            bundle,
            min_confident_fraction=MIN_CONFIDENT_STATE_FRACTION,
        )
        save_calibration(delay_dir / "calibration.json", bundle)
        save_raw_calibration(delay_dir / "calibration_raw.npz", raw)
        _plot_calibration(raw, bundle, delay_dir / "calibration.png")
        preparation_order = [int(value) for value in rng.permutation(2)]
        delay_rows = []
        for preparation in preparation_order:
            print(
                f"  prep={'e' if preparation else 'g'} "
                f"shots={SHOTS_PER_PREPARATION}",
                flush=True,
            )
            records = _run_custom_condition(
                soc,
                soccfg,
                cfg,
                bundle,
                method="opx",
                preparation=preparation,
                shots=int(SHOTS_PER_PREPARATION),
                block=0,
                csv_path=delay_dir / "shots.csv",
                assembly_path=delay_dir / "opx_reset.asm",
            )
            summary = summarize_records(
                records,
                bundle.reference_axis,
                bundle.loop,
            )
            row = _flatten_row(delay_us, preparation, summary, bundle)
            rows.append(row)
            delay_rows.append(row)
            _write_json(output_dir / "summary_partial.json", rows)
            print(
                f"    P(e)={row['verification_excited_fraction']:.4f} "
                f"timeouts={row['timeout_fraction']:.4f} "
                f"attempts={row['mean_reset_attempts']:.3f}",
                flush=True,
            )
        _write_json(delay_dir / "summary.json", delay_rows)

    evaluation = evaluate_feedback_delay_sweep(
        rows,
        max_timeout_fraction=MAX_TIMEOUT_FRACTION,
        max_verification_excited_fraction=MAX_VERIFICATION_EXCITED_FRACTION,
    )
    _write_json(output_dir / "summary.json", rows)
    _write_json(output_dir / "evaluation.json", evaluation)
    _write_summary_csv(output_dir / "summary.csv", rows)
    _plot_summary(rows, output_dir / "feedback_delay_sweep.png")
    selected = evaluation["selected_feedback_syncdelay_us"]
    if selected is None:
        print("\nNo tested feedback delay met both promotion limits.")
    else:
        print(f"\nSelected feedback sync delay: {selected:g} us")
    print(f"Completed: {output_dir}")


if __name__ == "__main__":
    main()
