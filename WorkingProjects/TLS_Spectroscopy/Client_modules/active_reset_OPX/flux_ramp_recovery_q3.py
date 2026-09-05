import csv
from datetime import datetime
import hashlib
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
    dmem_words_from_soccfg,
    run_dmem_block,
    timeout_for_reset_scheme,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    evaluate_inter_shot_recovery_sweep,
    json_safe,
    wilson_interval,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_q3 import (
    OPX_OVERRIDES,
    _git_commit,
    _plot_calibration,
    _worst_case_timeout_s,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import (
    build_t1_point_config,
    q3_benchmark_settings,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
    acquire_calibration,
    save_calibration,
    save_raw_calibration,
    validate_confident_calibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    OPXResetT1Program,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import (
    RECORD_WORDS,
    TerminalStatus,
    max_records,
)


QUBIT = "q3"
CALIBRATION_SHOTS = 2000
ROUNDS = 2
SHOTS_PER_CONDITION_PER_ROUND = 250
EDGE_SHOTS_PER_ROUND = 50
T1_WAIT_US = 1.0
EXCURSION_GAIN = -20000.0
PASSIVE_RELAX_US = 1000.0
ACTIVE_RELAX_US = (50.0, 100.0, 200.0, 400.0, 800.0)
MAX_ABS_POPULATION_DIFFERENCE = 0.12
MAX_ABS_SHOT_DRIFT = 0.10
HOST_WATCHDOG_S = 2.0
MIN_CONFIDENT_STATE_FRACTION = 0.2
RANDOM_SEED = 20260905
Q3_BENCHMARK_SETTINGS = q3_benchmark_settings()
SHOT_FIELDS = (
    "round",
    "method",
    "active_relax_us",
    "shot_index",
    "initial_z_assembly",
    "initial_z_canonical",
    "excited",
    "reset_attempts",
    "pi_pulses",
    "terminal_status",
    "last_z_assembly",
)
SUMMARY_FIELDS = (
    "method",
    "active_relax_us",
    "shots",
    "excited",
    "excited_fraction",
    "excited_ci95_low",
    "excited_ci95_high",
    "early_excited_fraction",
    "late_excited_fraction",
    "shot_drift",
    "mean_reset_attempts",
    "max_reset_attempts",
)


def _write_json(path, values):
    Path(path).write_text(json.dumps(json_safe(values), indent=2, sort_keys=True) + "\n")


def _make_output_dir():
    now = datetime.now()
    day = Path(outerFolder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_flux_ramp_recovery"
    output.mkdir(parents=True, exist_ok=False)
    return output


def _conditions():
    return [("passive", PASSIVE_RELAX_US)] + [
        ("opx_unbounded", delay) for delay in ACTIVE_RELAX_US
    ]


def _schedule():
    rng = np.random.default_rng(RANDOM_SEED)
    conditions = _conditions()
    output = []
    for round_index in range(ROUNDS):
        for condition_index in rng.permutation(len(conditions)):
            method, relax_us = conditions[int(condition_index)]
            output.append((round_index, method, relax_us))
    return output


def _condition_key(method, relax_us):
    return str(method), float(relax_us)


def _write_assembly(program, output_dir, method, relax_us):
    tag = f"{method}_{float(relax_us):g}us"
    path = output_dir / f"{tag}.asm"
    if path.exists():
        return
    path.write_text(program.asm())
    binary = np.asarray(program.compile(), dtype=np.uint64)
    (output_dir / f"{tag}.asm.sha256").write_text(
        hashlib.sha256(binary.tobytes()).hexdigest() + "\n"
    )


def _append_shots(path, records, *, round_index, method, relax_us, bundle):
    path = Path(path)
    exists = path.exists() and path.stat().st_size > 0
    sign = 1 if bundle.payload.assembly_plan()["excited_above"] else -1
    threshold = int(bundle.payload.excited_threshold)
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHOT_FIELDS)
        if not exists:
            writer.writeheader()
        for shot_index, record in enumerate(records):
            canonical = sign * int(record.initial_z)
            writer.writerow({
                "round": int(round_index),
                "method": str(method),
                "active_relax_us": "" if method == "passive" else float(relax_us),
                "shot_index": int(shot_index),
                "initial_z_assembly": int(record.initial_z),
                "initial_z_canonical": int(canonical),
                "excited": int(canonical > threshold),
                "reset_attempts": int(record.reset_attempts),
                "pi_pulses": int(record.pi_pulses),
                "terminal_status": record.terminal_status.name,
                "last_z_assembly": int(record.last_z),
            })


def _fraction(records, sign, threshold):
    values = np.asarray(
        [sign * int(record.initial_z) > threshold for record in records], dtype=bool
    )
    return float(np.mean(values)) if values.size else float("nan")


def _summarize(accumulated, bundle):
    sign = 1 if bundle.payload.assembly_plan()["excited_above"] else -1
    threshold = int(bundle.payload.excited_threshold)
    rows = []
    for method, relax_us in _conditions():
        batches = accumulated.get(_condition_key(method, relax_us), [])
        records = [record for batch in batches for record in batch]
        early = [
            record
            for batch in batches
            for record in batch[:EDGE_SHOTS_PER_ROUND]
        ]
        late = [
            record
            for batch in batches
            for record in batch[-EDGE_SHOTS_PER_ROUND:]
        ]
        excited_fraction = _fraction(records, sign, threshold)
        early_fraction = _fraction(early, sign, threshold)
        late_fraction = _fraction(late, sign, threshold)
        excited_count = int(round(excited_fraction * len(records))) if records else 0
        low, high = wilson_interval(excited_count, len(records))
        attempts = np.asarray([record.reset_attempts for record in records], dtype=float)
        rows.append({
            "method": method,
            "active_relax_us": None if method == "passive" else float(relax_us),
            "shots": int(len(records)),
            "excited": excited_count,
            "excited_fraction": excited_fraction,
            "excited_ci95_low": float(low),
            "excited_ci95_high": float(high),
            "early_excited_fraction": early_fraction,
            "late_excited_fraction": late_fraction,
            "shot_drift": late_fraction - early_fraction,
            "mean_reset_attempts": (
                float(np.mean(attempts)) if attempts.size else float("nan")
            ),
            "max_reset_attempts": int(np.max(attempts)) if attempts.size else 0,
        })
    return rows


def _evaluate(rows, accumulated, bundle):
    passive = next(row for row in rows if row["method"] == "passive")
    passive_batches = accumulated[_condition_key("passive", PASSIVE_RELAX_US)]
    sign = 1 if bundle.payload.assembly_plan()["excited_above"] else -1
    threshold = int(bundle.payload.excited_threshold)
    active = [
        {
            "active_relax_us": row["active_relax_us"],
            "excited_fraction": row["excited_fraction"],
            "shot_drift": row["shot_drift"],
            "round_population_differences": [
                _fraction(active_batch, sign, threshold)
                - _fraction(passive_batch, sign, threshold)
                for active_batch, passive_batch in zip(
                    accumulated[
                        _condition_key("opx_unbounded", row["active_relax_us"])
                    ],
                    passive_batches,
                )
            ],
        }
        for row in rows
        if row["method"] == "opx_unbounded"
    ]
    return evaluate_inter_shot_recovery_sweep(
        passive_excited_fraction=passive["excited_fraction"],
        rows=active,
        max_abs_population_difference=MAX_ABS_POPULATION_DIFFERENCE,
        max_abs_shot_drift=MAX_ABS_SHOT_DRIFT,
    )


def _write_summary_csv(path, rows):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _plot(rows, evaluation, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    passive = next(row for row in rows if row["method"] == "passive")
    active = [row for row in rows if row["method"] == "opx_unbounded"]
    x = np.asarray([row["active_relax_us"] for row in active], dtype=float)
    y = np.asarray([row["excited_fraction"] for row in active], dtype=float)
    low = np.asarray([row["excited_ci95_low"] for row in active], dtype=float)
    high = np.asarray([row["excited_ci95_high"] for row in active], dtype=float)
    drift = np.asarray([row["shot_drift"] for row in active], dtype=float)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.7))
    axes[0].errorbar(x, y, yerr=(y - low, high - y), fmt="o-", capsize=3)
    axes[0].axhline(passive["excited_fraction"], color="C1", label="passive 1000 us")
    axes[0].axhspan(
        passive["excited_fraction"] - MAX_ABS_POPULATION_DIFFERENCE,
        passive["excited_fraction"] + MAX_ABS_POPULATION_DIFFERENCE,
        color="C1",
        alpha=0.12,
    )
    axes[0].set(
        xscale="log",
        xlabel="Active inter-shot recovery [us]",
        ylabel="Excited fraction at 1 us",
        title=f"Population match: {evaluation['status']}",
    )
    axes[0].legend()
    axes[1].plot(x, drift, "o-")
    axes[1].axhspan(
        -MAX_ABS_SHOT_DRIFT,
        MAX_ABS_SHOT_DRIFT,
        color="C2",
        alpha=0.15,
    )
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set(
        xscale="log",
        xlabel="Active inter-shot recovery [us]",
        ylabel="Late minus early excited fraction",
        title="Within-block shot-history drift",
    )
    for axis in axes:
        axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    output_dir = _make_output_dir()
    print(f"\nFlux-ramp recovery sweep | {QUBIT}")
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
    schedule = _schedule()
    capacity = max_records(
        dmem_words_from_soccfg(soccfg), int(cfg["opx_record_base"]), RECORD_WORDS
    )
    if SHOTS_PER_CONDITION_PER_ROUND > capacity:
        raise ValueError(
            f"shots per condition {SHOTS_PER_CONDITION_PER_ROUND} exceed DMem capacity {capacity}"
        )
    metadata = {
        "qubit": QUBIT,
        "created": datetime.now().isoformat(),
        "source_commit": _git_commit(),
        "qick_version": str(qick.__version__),
        "calibration_shots": int(CALIBRATION_SHOTS),
        "rounds": int(ROUNDS),
        "shots_per_condition_per_round": int(SHOTS_PER_CONDITION_PER_ROUND),
        "edge_shots_per_round": int(EDGE_SHOTS_PER_ROUND),
        "t1_wait_us": float(T1_WAIT_US),
        "excursion_gain": float(EXCURSION_GAIN),
        "passive_relax_us": float(PASSIVE_RELAX_US),
        "active_relax_us": ACTIVE_RELAX_US,
        "max_abs_population_difference": float(MAX_ABS_POPULATION_DIFFERENCE),
        "max_abs_shot_drift": float(MAX_ABS_SHOT_DRIFT),
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
    shots_path = output_dir / "shots.csv"
    for run_index, (round_index, method, relax_us) in enumerate(schedule, start=1):
        reset_scheme = "none" if method == "passive" else "opx_unbounded"
        run_cfg = build_t1_point_config(
            cfg,
            reset_scheme=reset_scheme,
            inter_shot_delay_us=relax_us,
            shots=SHOTS_PER_CONDITION_PER_ROUND,
            delay_us=T1_WAIT_US,
            excursion_gain=EXCURSION_GAIN,
        )
        program = OPXResetT1Program(soccfg, run_cfg, bundle.payload, bundle.loop)
        _write_assembly(program, output_dir, method, relax_us)
        print(
            f"[{run_index:02d}/{len(schedule):02d}] round={round_index + 1} "
            f"method={method} recovery={relax_us:g} us",
            flush=True,
        )
        try:
            records = run_dmem_block(
                soc,
                program,
                timeout_s=timeout_for_reset_scheme(
                    reset_scheme,
                    bounded_timeout_s=_worst_case_timeout_s(
                        run_cfg, SHOTS_PER_CONDITION_PER_ROUND
                    ),
                    unbounded_watchdog_s=HOST_WATCHDOG_S,
                ),
                poll_interval_s=float(run_cfg["opx_poll_interval_s"]),
            )
        except AcquisitionTimeout as exc:
            if exc.partial_records:
                _append_shots(
                    shots_path,
                    exc.partial_records,
                    round_index=round_index,
                    method=method,
                    relax_us=relax_us,
                    bundle=bundle,
                )
            _write_json(output_dir / "watchdog_abort.json", {
                "round": int(round_index),
                "method": method,
                "active_relax_us": float(relax_us),
                "completed_shots": int(exc.completed_shots),
                "requested_shots": int(SHOTS_PER_CONDITION_PER_ROUND),
            })
            raise
        _append_shots(
            shots_path,
            records,
            round_index=round_index,
            method=method,
            relax_us=relax_us,
            bundle=bundle,
        )
        if method == "opx_unbounded" and any(
            record.terminal_status is not TerminalStatus.CONFIRMED_GROUND
            for record in records
        ):
            raise RuntimeError("unbounded reset returned a non-ground terminal status")
        accumulated.setdefault(_condition_key(method, relax_us), []).append(records)
        _write_json(
            output_dir / "summary_partial.json", _summarize(accumulated, bundle)
        )

    rows = _summarize(accumulated, bundle)
    evaluation = _evaluate(rows, accumulated, bundle)
    _write_summary_csv(output_dir / "summary.csv", rows)
    _write_json(output_dir / "summary.json", {
        "evaluation": evaluation,
        "conditions": rows,
    })
    _plot(rows, evaluation, output_dir / "flux_ramp_recovery.png")
    print("\nResults:")
    for row in rows:
        recovery = PASSIVE_RELAX_US if row["method"] == "passive" else row["active_relax_us"]
        print(
            f"  {row['method']:<15} recovery={recovery:>6g} us "
            f"P_e={row['excited_fraction']:.3f} drift={row['shot_drift']:+.3f}"
        )
    print(
        f"  status={evaluation['status']} "
        f"selected_active_recovery_us={evaluation['selected_active_relax_us']}"
    )
    print(f"Completed: {output_dir}")


if __name__ == "__main__":
    main()
