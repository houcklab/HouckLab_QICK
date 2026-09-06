import csv
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import time

import numpy as np


QUBIT = "q5"
SS_SHOTS = 2000
MIN_FIDELITY = 0.60
ROUNDS = 10
SHOTS_PER_BLOCK = 40
RANDOM_SEED = 20260905
T1_DELAYS_US = np.asarray([1.0, 50.0, 200.0, 800.0, 2000.0])
ACTIVE_POST_RESET_US = (25.0, 50.0, 100.0, 400.0, 1000.0)


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def normalize_classifier(calibration):
    scale = float(calibration.get("scale_factor", 1.0))
    if scale not in (-1.0, 1.0):
        raise ValueError("scale_factor must be -1 or 1")
    threshold = float(calibration["threshold"])
    ground_threshold = float(calibration["ground_threshold"])
    if scale < 0:
        ground_threshold = -ground_threshold
    if not np.all(np.isfinite([threshold, ground_threshold])):
        raise ValueError("classifier thresholds must be finite")
    return scale, threshold, ground_threshold


def build_schedule(rounds, methods, delay_count, seed):
    rounds = int(rounds)
    method_names = tuple(methods)
    delay_count = int(delay_count)
    if rounds <= 0 or delay_count <= 0 or not method_names:
        raise ValueError("rounds, methods, and delays must be nonempty")
    if len(set(method_names)) != len(method_names):
        raise ValueError("method names must be unique")
    rng = np.random.default_rng(int(seed))
    schedule = []
    for round_index in range(rounds):
        for delay_index in rng.permutation(delay_count):
            for method_code in rng.permutation(len(method_names)):
                schedule.append((round_index, int(method_code), int(delay_index)))
    return schedule


def build_methods(passive_us, configured_active_us, extra_active_us):
    passive_us = float(passive_us)
    active_values = sorted({float(configured_active_us), *(float(value) for value in extra_active_us)})
    methods = {f"passive_{passive_us:g}": ("passive", passive_us)}
    methods.update({f"active_{value:g}": ("active", value) for value in active_values})
    return methods


def reduced_group(rows, methods, delays_us, include_round=False, include_shot=False):
    first = rows[0]
    states = np.asarray([int(row["state"]) for row in rows], dtype=int)
    attempts = np.asarray([int(row["reset_attempts"]) for row in rows], dtype=int)
    output = {
        "method": tuple(methods)[int(first["method_code"])],
        "method_code": int(first["method_code"]),
        "delay_index": int(first["delay_index"]),
        "delay_us": float(delays_us[int(first["delay_index"])]),
        "shots": int(states.size),
        "excited_count": int(np.sum(states)),
        "excited_fraction": float(np.mean(states)),
        "mean_reset_attempts": float(np.mean(attempts)),
        "max_reset_attempts": int(np.max(attempts)),
    }
    if include_round:
        output["round"] = int(first["round"])
    if include_shot:
        output["shot_index"] = int(first["shot_index"])
    return output


def summarize_records(records, methods, delays_us):
    records = list(records)
    method_names = tuple(methods)
    delays_us = np.asarray(delays_us, dtype=float).ravel()
    if not records:
        raise ValueError("records must not be empty")
    overall_groups = defaultdict(list)
    round_groups = defaultdict(list)
    shot_groups = defaultdict(list)
    for row in records:
        method_code = int(row["method_code"])
        delay_index = int(row["delay_index"])
        if method_code < 0 or method_code >= len(method_names):
            raise ValueError("method_code is out of range")
        if delay_index < 0 or delay_index >= len(delays_us):
            raise ValueError("delay_index is out of range")
        pair = (method_code, delay_index)
        overall_groups[pair].append(row)
        round_groups[(int(row["round"]), *pair)].append(row)
        shot_groups[(*pair, int(row["shot_index"]))].append(row)
    return {
        "overall": [reduced_group(overall_groups[key], methods, delays_us) for key in sorted(overall_groups)],
        "rounds": [reduced_group(round_groups[key], methods, delays_us, include_round=True) for key in sorted(round_groups)],
        "shot_order": [reduced_group(shot_groups[key], methods, delays_us, include_shot=True) for key in sorted(shot_groups)],
    }


def summarize_timing(records, methods, passive_method):
    method_names = tuple(methods)
    passive_method = str(passive_method)
    if passive_method not in method_names:
        raise ValueError("passive method is missing")
    blocks = defaultdict(list)
    for row in records:
        blocks[int(row["block_index"])].append(row)
    intervals = defaultdict(list)
    for rows in blocks.values():
        method_codes = {int(row["method_code"]) for row in rows}
        if len(method_codes) != 1:
            raise ValueError("a timing block contains multiple methods")
        ordered = sorted(rows, key=lambda row: int(row["shot_index"]))
        timestamps = np.asarray([int(row["timestamp_ns"]) for row in ordered], dtype=np.int64)
        differences = np.diff(timestamps)
        intervals[next(iter(method_codes))].extend(differences[differences > 0].tolist())
    passive_code = method_names.index(passive_method)
    if not intervals[passive_code]:
        raise ValueError("passive timing intervals are missing")
    passive_median = float(np.median(intervals[passive_code]))
    output = []
    for method_code, method in enumerate(method_names):
        values = np.asarray(intervals.get(method_code, ()), dtype=float)
        if values.size == 0:
            continue
        median = float(np.median(values))
        output.append(
            {
                "method": method,
                "intervals": int(values.size),
                "median_ns_per_shot": median,
                "mean_ns_per_shot": float(np.mean(values)),
                "speedup_to_passive": passive_median / median,
            }
        )
    return output


def fit_decay(times_us, populations, shots):
    from scipy.optimize import curve_fit

    times = np.asarray(times_us, dtype=float)
    values = np.asarray(populations, dtype=float)
    counts = np.asarray(shots, dtype=float)
    if times.size < 4 or times.size != values.size or times.size != counts.size:
        raise ValueError("T1 fit needs at least four matching points")
    if np.any(counts <= 0) or not np.all(np.isfinite(times)) or not np.all(np.isfinite(values)):
        raise ValueError("T1 fit inputs are invalid")
    order = np.argsort(times)
    times = times[order]
    values = values[order]
    counts = counts[order]
    p0_seed = float(np.mean(values[-2:]))
    p1_seed = float(values[0])
    target = p0_seed + (p1_seed - p0_seed) / np.e
    tau_seed = max(0.01, float(times[np.argmin(np.abs(values - target))]))
    clipped = np.clip(values, 0.5 / counts, 1.0 - 0.5 / counts)
    sigma = np.sqrt(clipped * (1.0 - clipped) / counts)
    model = lambda t, p0, p1, tau: p0 + (p1 - p0) * np.exp(-t / tau)
    fitted, covariance = curve_fit(
        model,
        times,
        values,
        p0=[p0_seed, p1_seed, tau_seed],
        sigma=sigma,
        absolute_sigma=True,
        bounds=([-0.5, -0.5, 0.01], [1.5, 1.5, 1e7]),
        maxfev=50000,
    )
    errors = np.sqrt(np.diag(covariance))
    predicted = model(times, *fitted)
    return {
        "P0": float(fitted[0]),
        "P1": float(fitted[1]),
        "T1_us": float(fitted[2]),
        "P0_err": float(errors[0]),
        "P1_err": float(errors[1]),
        "T1_err_us": float(errors[2]),
        "rmse": float(np.sqrt(np.mean((values - predicted) ** 2))),
    }


def fit_methods(summary_rows, methods, passive_method):
    fits = {}
    errors = {}
    for method in methods:
        selected = sorted((row for row in summary_rows if row["method"] == method), key=lambda row: row["delay_index"])
        try:
            fits[method] = fit_decay(
                [row["delay_us"] for row in selected],
                [row["excited_fraction"] for row in selected],
                [row["shots"] for row in selected],
            )
        except Exception as exc:
            errors[method] = f"{type(exc).__name__}: {exc}"
    if passive_method not in fits:
        raise RuntimeError("passive T1 fit failed")
    passive = fits[passive_method]
    comparison = []
    for method, fit in fits.items():
        comparison.append(
            {
                "method": method,
                "T1_us": fit["T1_us"],
                "T1_err_us": fit["T1_err_us"],
                "T1_ratio_to_passive": fit["T1_us"] / passive["T1_us"],
                "P0_difference_from_passive": fit["P0"] - passive["P0"],
                "P1_difference_from_passive": fit["P1"] - passive["P1"],
                "rmse": fit["rmse"],
            }
        )
    return {"fits": fits, "errors": errors, "comparison": comparison}


def write_json(path, values):
    Path(path).write_text(json.dumps(json_safe(values), indent=2, sort_keys=True) + "\n")


def write_csv(path, rows):
    rows = list(rows)
    if not rows:
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_output_dir(outer_folder):
    now = datetime.now()
    output = Path(outer_folder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}" / f"{QUBIT}_{now:%H_%M_%S}_OPX_active_passive_reset_reference"
    output.mkdir(parents=True, exist_ok=False)
    return output


def make_program(meta_dict, calibration, methods, delays_us, schedule):
    from qm.qua import align, assign, declare, declare_stream, else_, fixed, for_, if_, play, program, save, stream_processing, wait, while_
    from LabCode.Helpers.qua_helpers import measure_1q, measure_1q_with_timestamps

    qubit = meta_dict["q_name"]
    resonator = meta_dict["r_name"]
    scale_factor, threshold, ground_confidence_threshold = normalize_classifier(calibration)
    method_values = tuple(methods.values())
    schedule_round_values = [int(row[0]) for row in schedule]
    schedule_method_values = [int(row[1]) for row in schedule]
    schedule_delay_values = [int(row[2]) for row in schedule]
    delay_clock_values = [int(np.ceil(float(value) * 1000.0 / 4.0)) for value in delays_us]
    post_reset_clock_values = [int(np.ceil(float(value[1]) * 1000.0 / 4.0)) for value in method_values]
    active_reset_values = [int(value[0] == "active") for value in method_values]
    with program() as prog:
        block = declare(int)
        shot = declare(int)
        state = declare(int)
        reset_attempts = declare(int)
        reset_active = declare(int)
        delay_wait = declare(int)
        post_reset_wait = declare(int)
        round_value = declare(int)
        method_value = declare(int)
        delay_value = declare(int)
        schedule_rounds = declare(int, value=schedule_round_values)
        schedule_methods = declare(int, value=schedule_method_values)
        schedule_delays = declare(int, value=schedule_delay_values)
        delay_clocks = declare(int, value=delay_clock_values)
        post_reset_clocks = declare(int, value=post_reset_clock_values)
        active_resets = declare(int, value=active_reset_values)
        I = declare(fixed)
        Q = declare(fixed)
        I_reset_raw = declare(fixed)
        Q_reset = declare(fixed)
        I_reset = declare(fixed)
        state_stream = declare_stream()
        attempts_stream = declare_stream()
        round_stream = declare_stream()
        method_stream = declare_stream()
        delay_stream = declare_stream()
        shot_stream = declare_stream()
        block_stream = declare_stream()
        I_stream = declare_stream()
        Q_stream = declare_stream()
        timestamp_stream = declare_stream()
        with for_(block, 0, block < len(schedule), block + 1):
            assign(round_value, schedule_rounds[block])
            assign(method_value, schedule_methods[block])
            assign(delay_value, schedule_delays[block])
            assign(delay_wait, delay_clocks[delay_value])
            assign(post_reset_wait, post_reset_clocks[method_value])
            assign(reset_active, active_resets[method_value])
            with if_(reset_active == 0):
                wait(post_reset_wait, qubit)
            with else_():
                align(qubit, resonator)
                I_reset_raw, Q_reset = measure_1q(meta_dict, I_reset_raw, Q_reset)
                assign(I_reset, I_reset_raw * scale_factor)
                with while_(I_reset > ground_confidence_threshold):
                    with if_(I_reset > threshold):
                        play("X180", qubit)
                        align(qubit, resonator)
                    I_reset_raw, Q_reset = measure_1q(meta_dict, I_reset_raw, Q_reset)
                    assign(I_reset, I_reset_raw * scale_factor)
                wait(post_reset_wait, qubit)
            with for_(shot, 0, shot < SHOTS_PER_BLOCK, shot + 1):
                play("X180", qubit)
                wait(delay_wait, qubit)
                align(qubit, resonator)
                I, Q = measure_1q_with_timestamps(meta_dict, I, Q, timestamp_stream)
                assign(I_reset, I * scale_factor)
                with if_(I_reset > threshold):
                    assign(state, 1)
                with else_():
                    assign(state, 0)
                assign(reset_attempts, 0)
                save(state, state_stream)
                save(round_value, round_stream)
                save(method_value, method_stream)
                save(delay_value, delay_stream)
                save(shot, shot_stream)
                save(block, block_stream)
                save(I, I_stream)
                save(Q, Q_stream)
                align(qubit, resonator)
                with if_(reset_active == 0):
                    wait(post_reset_wait, qubit)
                with else_():
                    with while_(I_reset > ground_confidence_threshold):
                        with if_(I_reset > threshold):
                            play("X180", qubit)
                            align(qubit, resonator)
                        I_reset_raw, Q_reset = measure_1q(meta_dict, I_reset_raw, Q_reset)
                        assign(I_reset, I_reset_raw * scale_factor)
                        assign(reset_attempts, reset_attempts + 1)
                    wait(post_reset_wait, qubit)
                save(reset_attempts, attempts_stream)
        with stream_processing():
            state_stream.save_all("state")
            attempts_stream.save_all("reset_attempts")
            round_stream.save_all("round")
            method_stream.save_all("method_code")
            delay_stream.save_all("delay_index")
            shot_stream.save_all("shot_index")
            block_stream.save_all("block_index")
            I_stream.save_all("I")
            Q_stream.save_all("Q")
            timestamp_stream.save_all("timestamp_ns")
    return prog


def fetch_values(job, name):
    handle = job.result_handles.get(name)
    if handle is None:
        raise RuntimeError(f"missing result handle {name}")
    handle.wait_for_all_values()
    fetched = handle.fetch_all()
    if isinstance(fetched, dict) and "value" in fetched:
        fetched = fetched["value"]
    return np.asarray(fetched).ravel()


def make_records(job, methods, delays_us, expected_count):
    names = ("round", "method_code", "delay_index", "shot_index", "block_index", "state", "reset_attempts", "I", "Q", "timestamp_ns")
    values = {name: fetch_values(job, name) for name in names}
    lengths = {name: len(value) for name, value in values.items()}
    if set(lengths.values()) != {int(expected_count)}:
        raise RuntimeError(f"unexpected result lengths: expected={expected_count}, observed={lengths}")
    method_names = tuple(methods)
    records = []
    for index in range(expected_count):
        method_code = int(values["method_code"][index])
        delay_index = int(values["delay_index"][index])
        records.append(
            {
                "round": int(values["round"][index]),
                "method": method_names[method_code],
                "method_code": method_code,
                "delay_index": delay_index,
                "delay_us": float(delays_us[delay_index]),
                "shot_index": int(values["shot_index"][index]),
                "block_index": int(values["block_index"][index]),
                "state": int(values["state"][index]),
                "reset_attempts": int(values["reset_attempts"][index]),
                "I": float(values["I"][index]),
                "Q": float(values["Q"][index]),
                "timestamp_ns": int(values["timestamp_ns"][index]),
            }
        )
    return records


def plot_results(summary, fit_result, timing, methods, output_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    method_names = tuple(methods)
    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(method_names)))
    color_map = dict(zip(method_names, colors))
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    curve_ax, ratio_ax, attempts_ax, order_ax = axes.ravel()
    for method in method_names:
        rows = sorted((row for row in summary["overall"] if row["method"] == method), key=lambda row: row["delay_us"])
        times = np.asarray([row["delay_us"] for row in rows])
        populations = np.asarray([row["excited_fraction"] for row in rows])
        curve_ax.plot(times, populations, "o", color=color_map[method], label=method)
        if method in fit_result["fits"]:
            fit = fit_result["fits"][method]
            grid = np.logspace(np.log10(np.min(times)), np.log10(np.max(times)), 300)
            predicted = fit["P0"] + (fit["P1"] - fit["P0"]) * np.exp(-grid / fit["T1_us"])
            curve_ax.plot(grid, predicted, "-", color=color_map[method])
        attempts_ax.plot(times, [row["mean_reset_attempts"] for row in rows], "o-", color=color_map[method])
    curve_ax.set_xscale("log")
    curve_ax.set_xlabel("T1 delay (us)")
    curve_ax.set_ylabel("Excited fraction")
    curve_ax.legend(fontsize=8)
    ratio_ax.axhline(1.0, color="black", linewidth=1)
    ratio_ax.bar(
        [row["method"] for row in fit_result["comparison"]],
        [row["T1_ratio_to_passive"] for row in fit_result["comparison"]],
        color=[color_map[row["method"]] for row in fit_result["comparison"]],
    )
    ratio_ax.set_ylabel("T1 / passive T1")
    ratio_ax.tick_params(axis="x", rotation=35)
    attempts_ax.set_xscale("log")
    attempts_ax.set_xlabel("T1 delay (us)")
    attempts_ax.set_ylabel("Mean reset attempts")
    shortest = int(np.argmin(T1_DELAYS_US))
    for method in method_names:
        rows = sorted((row for row in summary["shot_order"] if row["method"] == method and row["delay_index"] == shortest), key=lambda row: row["shot_index"])
        order_ax.plot([row["shot_index"] for row in rows], [row["excited_fraction"] for row in rows], "o-", color=color_map[method], label=method)
    order_ax.set_xlabel("Shot index within block")
    order_ax.set_ylabel("Excited fraction at 1 us")
    timing_text = "\n".join(f"{row['method']}: {row['speedup_to_passive']:.2f}x" for row in timing)
    order_ax.text(1.02, 1.0, timing_text, transform=order_ax.transAxes, va="top")
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main():
    from qualang_tools.units import unit
    from LabCode.Config.config_helpers import meta_dict_to_config_1Q
    from LabCode.Config.make_meta_dict import make_meta_dict
    from LabCode.CoreLib.experiment import qmm
    from LabCode.Experiments.Readout_Cal.m_single_shot_1Q import SingleShot1Q
    from LabCode.PythonDrivers.control_8257 import set_LO_parameters

    u = unit(coerce_to_integer=True)
    meta_dict = make_meta_dict(QUBIT)[QUBIT]
    outer_folder = meta_dict["global_params"]["outer_folder"]
    config = meta_dict_to_config_1Q(meta_dict)
    set_LO_parameters([meta_dict["q_LO"], meta_dict["r_LO"]])
    calibration_run = SingleShot1Q(
        QUBIT,
        SS_SHOTS,
        meta_dict=meta_dict,
        outer_folder=outer_folder,
        path=QUBIT,
        suffix="OPX_active_passive_reset_reference_SS",
        config=config,
        save=True,
        plot=True,
    )
    if calibration_run.max_F < MIN_FIDELITY:
        raise RuntimeError(f"single-shot fidelity {calibration_run.max_F:.4f} is below {MIN_FIDELITY:.4f}")
    calibration = dict(calibration_run.calib_params)
    meta_dict["read_theta"] = calibration["read_theta"]
    config = meta_dict_to_config_1Q(meta_dict)
    passive_us = float(meta_dict["reset_time"] / u.us)
    configured_active_us = float(meta_dict["thermalization_time"] / u.us)
    passive_method = f"passive_{passive_us:g}"
    methods = build_methods(passive_us, configured_active_us, ACTIVE_POST_RESET_US)
    schedule = build_schedule(ROUNDS, methods, len(T1_DELAYS_US), RANDOM_SEED)
    prog = make_program(meta_dict, calibration, methods, T1_DELAYS_US, schedule)
    output_dir = make_output_dir(outer_folder)
    metadata = {
        "created": datetime.now().isoformat(),
        "qubit": QUBIT,
        "ss_shots": SS_SHOTS,
        "ss_fidelity": float(calibration_run.max_F),
        "calibration": calibration,
        "methods": methods,
        "delays_us": T1_DELAYS_US,
        "rounds": ROUNDS,
        "shots_per_block": SHOTS_PER_BLOCK,
        "random_seed": RANDOM_SEED,
        "schedule": [(round_index, tuple(methods)[method_code], delay_index) for round_index, method_code, delay_index in schedule],
        "q_LO": meta_dict["q_LO"],
        "q_IF": meta_dict["q_IF"],
        "r_LO": meta_dict["r_LO"],
        "r_IF": meta_dict["r_IF"],
        "pi_amp": meta_dict["pi_amp"],
        "read_amp": meta_dict["read_amp"],
        "read_len": meta_dict["read_len"],
    }
    write_json(output_dir / "metadata.json", metadata)
    qm = qmm.open_qm(config)
    qmm.clear_all_job_results()
    started = time.perf_counter()
    job = qm.execute(prog, duration_limit=0, data_limit=0)
    expected_count = len(schedule) * SHOTS_PER_BLOCK
    records = make_records(job, methods, T1_DELAYS_US, expected_count)
    elapsed_s = time.perf_counter() - started
    summary = summarize_records(records, methods, T1_DELAYS_US)
    fit_result = fit_methods(summary["overall"], methods, passive_method)
    timing = summarize_timing(records, methods, passive_method)
    results = {
        "host_elapsed_s": elapsed_s,
        "fits": fit_result["fits"],
        "fit_errors": fit_result["errors"],
        "comparison": fit_result["comparison"],
        "timing": timing,
    }
    write_csv(output_dir / "raw_shots.csv", records)
    write_csv(output_dir / "summary.csv", summary["overall"])
    write_csv(output_dir / "round_summary.csv", summary["rounds"])
    write_csv(output_dir / "shot_order.csv", summary["shot_order"])
    write_json(output_dir / "results.json", results)
    plot_results(summary, fit_result, timing, methods, output_dir / "comparison.png")
    print(f"output={output_dir}")
    for row in fit_result["comparison"]:
        timing_row = next((value for value in timing if value["method"] == row["method"]), None)
        speedup = float("nan") if timing_row is None else timing_row["speedup_to_passive"]
        print(f"{row['method']} T1={row['T1_us']:.3f} us ratio={row['T1_ratio_to_passive']:.3f} delta_P1={row['P1_difference_from_passive']:+.4f} speedup={speedup:.3f}")


if __name__ == "__main__":
    main()
