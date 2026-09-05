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
    fit_t1_decay,
    wilson_interval,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_q3 import (
    OPX_OVERRIDES,
    _git_commit,
    _json_safe,
    _plot_calibration,
    _worst_case_timeout_s,
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
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    OPXResetT1Program,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import (
    RECORD_WORDS,
    max_records,
)


QUBIT = "q3"
CALIBRATION_SHOTS = 2000
ROUNDS = 2
SHOTS_PER_POINT_PER_ROUND = 250
T1_MIN_US = 1.0
T1_MAX_US = 750.0
T1_POINTS = 21
PASSIVE_RELAX_US = 1000.0
ACTIVE_RELAX_US = 25.0
HOST_WATCHDOG_S = 2.0
MIN_CONFIDENT_STATE_FRACTION = 0.2
T1_MATCH_RELATIVE_TOLERANCE = 0.20
RANDOM_SEED = 20260905
METHODS = ("passive", "opx_unbounded")
Q3_BENCHMARK_SETTINGS = q3_benchmark_settings()
SHOT_FIELDS = (
    "round",
    "method",
    "delay_index",
    "delay_us",
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
    "delay_index",
    "delay_us",
    "shots",
    "excited",
    "excited_fraction",
    "excited_ci95_low",
    "excited_ci95_high",
    "mean_reset_attempts",
    "max_reset_attempts",
)


def _write_json(path, values):
    Path(path).write_text(
        json.dumps(_json_safe(values), indent=2, sort_keys=True) + "\n"
    )


def _make_output_dir():
    now = datetime.now()
    day = Path(outerFolder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_T1_equivalence"
    output.mkdir(parents=True, exist_ok=False)
    return output


def _schedule(delays):
    rng = np.random.default_rng(RANDOM_SEED)
    conditions = [(method, index) for method in METHODS for index in range(len(delays))]
    output = []
    for round_index in range(ROUNDS):
        for condition_index in rng.permutation(len(conditions)):
            method, delay_index = conditions[int(condition_index)]
            output.append((round_index, method, delay_index))
    return output


def _method_config(method):
    if method == "passive":
        return "none", PASSIVE_RELAX_US
    if method == "opx_unbounded":
        return "opx_unbounded", ACTIVE_RELAX_US
    raise ValueError(f"unknown T1 reset method {method!r}")


def _write_assembly(program, output_dir, method, delay_us):
    tag = f"{method}_{float(delay_us):g}us"
    assembly_path = output_dir / f"{tag}.asm"
    if assembly_path.exists():
        return
    assembly_path.write_text(program.asm())
    binary = np.asarray(program.compile(), dtype=np.uint64)
    (output_dir / f"{tag}.asm.sha256").write_text(
        hashlib.sha256(binary.tobytes()).hexdigest() + "\n"
    )


def _append_shots(path, records, *, round_index, method, delay_index, delay_us, bundle):
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
                "delay_index": int(delay_index),
                "delay_us": float(delay_us),
                "shot_index": int(shot_index),
                "initial_z_assembly": int(record.initial_z),
                "initial_z_canonical": int(canonical),
                "excited": int(canonical > threshold),
                "reset_attempts": int(record.reset_attempts),
                "pi_pulses": int(record.pi_pulses),
                "terminal_status": record.terminal_status.name,
                "last_z_assembly": int(record.last_z),
            })


def _summarize(accumulated, delays, bundle):
    sign = 1 if bundle.payload.assembly_plan()["excited_above"] else -1
    threshold = int(bundle.payload.excited_threshold)
    rows = []
    for method in METHODS:
        for delay_index, delay_us in enumerate(delays):
            records = accumulated.get((method, delay_index), [])
            canonical = np.asarray(
                [sign * int(record.initial_z) for record in records], dtype=np.int64
            )
            excited = canonical > threshold
            count = int(np.count_nonzero(excited))
            low, high = wilson_interval(count, len(records))
            attempts = np.asarray(
                [record.reset_attempts for record in records], dtype=float
            )
            rows.append({
                "method": method,
                "delay_index": int(delay_index),
                "delay_us": float(delay_us),
                "shots": int(len(records)),
                "excited": count,
                "excited_fraction": (
                    float(np.mean(excited)) if excited.size else float("nan")
                ),
                "excited_ci95_low": float(low),
                "excited_ci95_high": float(high),
                "mean_reset_attempts": (
                    float(np.mean(attempts)) if attempts.size else float("nan")
                ),
                "max_reset_attempts": (
                    int(np.max(attempts)) if attempts.size else 0
                ),
            })
    return rows


def _fit_methods(rows):
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


def _equivalence(fits):
    if set(fits) != set(METHODS):
        return {"status": "fail", "reason": "one or both T1 fits failed"}
    passive = fits["passive"]
    active = fits["opx_unbounded"]
    if not passive["decaying"] or not active["decaying"]:
        return {"status": "fail", "reason": "one or both fitted curves are not decays"}
    difference = float(active["tau_us"] - passive["tau_us"])
    relative = float(difference / passive["tau_us"])
    passed = abs(relative) <= T1_MATCH_RELATIVE_TOLERANCE
    return {
        "status": "pass" if passed else "fail",
        "passive_tau_us": float(passive["tau_us"]),
        "active_tau_us": float(active["tau_us"]),
        "difference_us": difference,
        "relative_difference": relative,
        "relative_tolerance": float(T1_MATCH_RELATIVE_TOLERANCE),
    }


def _write_summary_csv(path, rows):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _plot(rows, fits, equivalence, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    colors = {"passive": "C0", "opx_unbounded": "C1"}
    labels = {
        "passive": f"passive ({PASSIVE_RELAX_US:g} us)",
        "opx_unbounded": f"unbounded ({ACTIVE_RELAX_US:g} us)",
    }
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
            ms=4,
            capsize=2,
            color=colors[method],
            label=labels[method],
        )
        if method in fits:
            fit = fits[method]
            dense = np.logspace(np.log10(x.min()), np.log10(x.max()), 400)
            fitted = fit["P0"] + (fit["P1"] - fit["P0"]) * np.exp(
                -dense / fit["tau_us"]
            )
            axes[0].plot(
                dense,
                fitted,
                color=colors[method],
                label=f"{method} T1={fit['tau_us']:.1f}±{fit['tau_err_us']:.1f} us",
            )
        attempts = np.asarray(
            [row["mean_reset_attempts"] for row in selected], dtype=float
        )
        axes[1].plot(x, attempts, "o-", ms=4, color=colors[method], label=labels[method])
    axes[0].set(
        xscale="log",
        xlabel="T1 delay [us]",
        ylabel="Excited fraction",
        title=f"T1 reset equivalence: {equivalence['status']}",
    )
    axes[1].set(
        xscale="log",
        xlabel="T1 delay [us]",
        ylabel="Mean post-readout reset attempts",
        title="Reset work after each T1 readout",
    )
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    output_dir = _make_output_dir()
    print(f"\nT1 equivalence | {QUBIT} | passive vs true-unbounded reset")
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
    delays = np.logspace(
        np.log10(T1_MIN_US), np.log10(T1_MAX_US), T1_POINTS
    )
    schedule = _schedule(delays)
    capacity = max_records(
        dmem_words_from_soccfg(soccfg), int(cfg["opx_record_base"]), RECORD_WORDS
    )
    if SHOTS_PER_POINT_PER_ROUND > capacity:
        raise ValueError(
            f"shots per point {SHOTS_PER_POINT_PER_ROUND} exceed DMem capacity {capacity}"
        )
    metadata = {
        "qubit": QUBIT,
        "created": datetime.now().isoformat(),
        "source_commit": _git_commit(),
        "qick_version": str(qick.__version__),
        "calibration_shots": int(CALIBRATION_SHOTS),
        "rounds": int(ROUNDS),
        "shots_per_point_per_round": int(SHOTS_PER_POINT_PER_ROUND),
        "delays_us": delays,
        "passive_relax_us": float(PASSIVE_RELAX_US),
        "active_relax_us": float(ACTIVE_RELAX_US),
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
    assembly_saved = set()
    for run_index, (round_index, method, delay_index) in enumerate(schedule, start=1):
        delay_us = float(delays[delay_index])
        reset_scheme, inter_shot_delay_us = _method_config(method)
        run_cfg = dict(cfg)
        run_cfg.update({
            "shots": int(SHOTS_PER_POINT_PER_ROUND),
            "reps": int(SHOTS_PER_POINT_PER_ROUND),
            "t1_wait_us": delay_us,
            "opx_reset_scheme": reset_scheme,
            "opx_inter_shot_delay_us": float(inter_shot_delay_us),
        })
        program = OPXResetT1Program(
            soccfg, run_cfg, bundle.payload, bundle.loop
        )
        if method not in assembly_saved:
            _write_assembly(program, output_dir, method, delay_us)
            assembly_saved.add(method)
        print(
            f"[{run_index:02d}/{len(schedule):02d}] round={round_index + 1} "
            f"method={method} delay={delay_us:.3f} us",
            flush=True,
        )
        try:
            records = run_dmem_block(
                soc,
                program,
                timeout_s=timeout_for_reset_scheme(
                    reset_scheme,
                    bounded_timeout_s=_worst_case_timeout_s(
                        run_cfg, SHOTS_PER_POINT_PER_ROUND
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
                    delay_index=delay_index,
                    delay_us=delay_us,
                    bundle=bundle,
                )
            _write_json(output_dir / "watchdog_abort.json", {
                "round": int(round_index),
                "method": method,
                "delay_index": int(delay_index),
                "delay_us": delay_us,
                "completed_shots": int(exc.completed_shots),
                "requested_shots": int(SHOTS_PER_POINT_PER_ROUND),
            })
            raise
        _append_shots(
            shots_path,
            records,
            round_index=round_index,
            method=method,
            delay_index=delay_index,
            delay_us=delay_us,
            bundle=bundle,
        )
        accumulated.setdefault((method, delay_index), []).extend(records)
        partial_rows = _summarize(accumulated, delays, bundle)
        _write_json(output_dir / "summary_partial.json", partial_rows)

    rows = _summarize(accumulated, delays, bundle)
    fits, fit_errors = _fit_methods(rows)
    equivalence = _equivalence(fits)
    _write_summary_csv(output_dir / "summary.csv", rows)
    _write_json(output_dir / "summary.json", {
        "equivalence": equivalence,
        "fits": fits,
        "fit_errors": fit_errors,
        "points": rows,
    })
    _plot(rows, fits, equivalence, output_dir / "t1_equivalence.png")
    print("\nResults:")
    for method in METHODS:
        if method in fits:
            fit = fits[method]
            print(
                f"  {method:<15} T1={fit['tau_us']:.2f} ± "
                f"{fit['tau_err_us']:.2f} us"
            )
        else:
            print(f"  {method:<15} fit failed: {fit_errors.get(method)}")
    print(
        f"  equivalence={equivalence['status']} "
        f"tolerance={100 * T1_MATCH_RELATIVE_TOLERANCE:.0f}%"
    )
    print(f"Completed: {output_dir}")


if __name__ == "__main__":
    main()
