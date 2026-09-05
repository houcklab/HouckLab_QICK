import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sys
import time

import numpy as np


_source = Path(__file__).resolve()
for _parent in _source.parents:
    if (_parent / "WorkingProjects").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import json_safe
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.opx_reference_analysis import (
    build_interleaved_schedule,
    fit_method_decays,
    make_comparison,
    normalize_classifier,
    summarize_block_timings,
    summarize_shots,
)


DEFAULT_METHODS = {
    "passive_1000": ("passive", 1000.0),
    "active_25": ("active", 25.0),
    "active_100": ("active", 100.0),
    "active_400": ("active", 400.0),
    "active_1000": ("active", 1000.0),
}
DEFAULT_DELAYS_US = (1.0, 35.0, 100.0, 250.0, 750.0)
DEFAULT_CHIP = "FTTv01"
DEFAULT_QUBIT = "q1"
DEFAULT_ROUNDS = 12
DEFAULT_SHOTS_PER_BLOCK = 40
DEFAULT_SEED = 20260905
DEFAULT_SS_SHOTS = 2000
DEFAULT_MIN_FIDELITY = 0.6


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--qua-repo", type=Path)
    parser.add_argument("--chip", default=DEFAULT_CHIP)
    parser.add_argument("--qubit", default=DEFAULT_QUBIT)
    parser.add_argument("--dc-target-voltage", type=float)
    parser.add_argument("--park-voltage", type=float)
    parser.add_argument("--flux-settle-ns", type=int)
    parser.add_argument("--delays-us", type=float, nargs="+", default=DEFAULT_DELAYS_US)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--shots-per-block", type=int, default=DEFAULT_SHOTS_PER_BLOCK)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--ss-shots", type=int, default=DEFAULT_SS_SHOTS)
    parser.add_argument("--min-fidelity", type=float, default=DEFAULT_MIN_FIDELITY)
    return parser.parse_args(argv)


def find_qua_repo(explicit=None):
    candidates = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    candidates.extend([Path.cwd(), *_source.parents])
    candidates.extend(parent / "Houck-Lab-Qua" for parent in _source.parents)
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "LabCode").is_dir():
            return resolved
    raise FileNotFoundError("Could not locate Houck-Lab-Qua; pass --qua-repo")


def validate_settings(args):
    delays = np.asarray(args.delays_us, dtype=float)
    if args.rounds <= 0 or args.shots_per_block <= 0 or args.ss_shots <= 0:
        raise ValueError("rounds, shots-per-block, and ss-shots must be positive")
    if delays.size < 4 or not np.all(np.isfinite(delays)) or np.any(delays <= 0):
        raise ValueError("delays-us needs at least four finite positive values")
    if np.any(np.diff(delays) <= 0):
        raise ValueError("delays-us must be strictly increasing")
    if args.flux_settle_ns is not None and args.flux_settle_ns < 0:
        raise ValueError("flux-settle-ns must be nonnegative")
    if not 0 <= args.min_fidelity <= 1:
        raise ValueError("min-fidelity must lie between zero and one")
    return delays


def make_output_dir(outer_folder, qubit):
    now = datetime.now()
    output = (
        Path(outer_folder)
        / qubit
        / f"{qubit}_{now:%Y_%m_%d}"
        / f"{qubit}_{now:%H_%M_%S}_OPX_active_reset_reference"
    )
    output.mkdir(parents=True, exist_ok=False)
    return output


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


def make_program(meta_dict, calibration, methods, delays_us, schedule, shots_per_block, target_voltage, park_voltage, settle_ns):
    from qm.qua import align, assign, declare, declare_stream, else_, fixed, for_, if_, play, program, save, set_dc_offset, stream_processing, wait, while_
    from LabCode.Helpers.qua_helpers import measure_1q, measure_1q_with_timestamps

    qubit = meta_dict["q_name"]
    resonator = meta_dict["r_name"]
    flux_line = meta_dict["flux_name"]
    classifier = normalize_classifier(calibration)
    threshold = classifier["threshold"]
    ground_confidence_threshold = classifier["ground_threshold"]
    scale_factor = classifier["scale_factor"]
    method_values = tuple(methods.values())
    schedule_round_values = [int(row[0]) for row in schedule]
    schedule_method_values = [int(row[1]) for row in schedule]
    schedule_delay_values = [int(row[2]) for row in schedule]
    delay_clock_values = [int(np.ceil(float(value) * 1000.0 / 4.0)) for value in delays_us]
    post_reset_clock_values = [int(np.ceil(float(value[1]) * 1000.0 / 4.0)) for value in method_values]
    active_reset_values = [int(value[0] == "active") for value in method_values]
    settle_clocks = int(np.ceil(float(settle_ns) / 4.0))
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
            with for_(shot, 0, shot < int(shots_per_block), shot + 1):
                play("X180", qubit)
                if target_voltage is None:
                    wait(delay_wait, qubit)
                else:
                    align(qubit, resonator, flux_line)
                    set_dc_offset(flux_line, "single", float(target_voltage))
                    if settle_clocks > 0:
                        wait(settle_clocks, qubit, resonator, flux_line)
                    wait(delay_wait, qubit, resonator, flux_line)
                    set_dc_offset(flux_line, "single", float(park_voltage))
                    if settle_clocks > 0:
                        wait(settle_clocks, qubit, resonator, flux_line)
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
        raise RuntimeError(f"missing OPX result handle {name}")
    handle.wait_for_all_values()
    fetched = handle.fetch_all()
    if isinstance(fetched, dict) and "value" in fetched:
        fetched = fetched["value"]
    return np.asarray(fetched).ravel()


def make_records(job, methods, delays_us, expected_count):
    names = (
        "round",
        "method_code",
        "delay_index",
        "shot_index",
        "block_index",
        "state",
        "reset_attempts",
        "I",
        "Q",
        "timestamp_ns",
    )
    values = {name: fetch_values(job, name) for name in names}
    lengths = {name: len(value) for name, value in values.items()}
    if set(lengths.values()) != {int(expected_count)}:
        raise RuntimeError(f"unexpected OPX result lengths: expected={expected_count}, observed={lengths}")
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


def plot_results(summary, fits, comparison, timing, methods, output_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(methods)))
    color_map = dict(zip(methods, colors))
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    curve_ax, ratio_ax, attempts_ax, order_ax = axes.ravel()
    for method in methods:
        rows = sorted((row for row in summary["overall"] if row["method"] == method), key=lambda row: row["delay_us"])
        times = np.asarray([row["delay_us"] for row in rows])
        values = np.asarray([row["excited_fraction"] for row in rows])
        curve_ax.plot(times, values, "o", color=color_map[method], label=method)
        if method in fits:
            fit = fits[method]
            grid = np.logspace(np.log10(np.min(times)), np.log10(np.max(times)), 300)
            predicted = fit["P0"] + (fit["P1"] - fit["P0"]) * np.exp(-grid / fit["tau_us"])
            curve_ax.plot(grid, predicted, "-", color=color_map[method])
        attempts_ax.plot(times, [row["reset_attempt_mean"] for row in rows], "o-", color=color_map[method], label=method)
    curve_ax.set_xscale("log")
    curve_ax.set_xlabel("T1 delay (us)")
    curve_ax.set_ylabel("Excited fraction")
    curve_ax.legend(fontsize=8)
    ratio_ax.axhline(1.0, color="black", linewidth=1)
    ratio_ax.bar([row["method"] for row in comparison], [row["tau_ratio_to_passive"] for row in comparison], color=[color_map[row["method"]] for row in comparison])
    ratio_ax.set_ylabel("T1 / passive T1")
    ratio_ax.tick_params(axis="x", rotation=35)
    attempts_ax.set_xscale("log")
    attempts_ax.set_xlabel("T1 delay (us)")
    attempts_ax.set_ylabel("Mean reset attempts")
    shortest = min(row["delay_index"] for row in summary["shot_order"])
    for method in methods:
        rows = sorted((row for row in summary["shot_order"] if row["method"] == method and row["delay_index"] == shortest), key=lambda row: row["shot_index"])
        order_ax.plot([row["shot_index"] for row in rows], [row["excited_fraction"] for row in rows], "o-", color=color_map[method], label=method)
    order_ax.set_xlabel("Shot index within block")
    order_ax.set_ylabel("Excited fraction at shortest delay")
    timing_text = "\n".join(f"{row['method']}: {row['speedup_to_passive']:.2f}x" for row in timing)
    order_ax.text(1.02, 1.0, timing_text, transform=order_ax.transAxes, va="top")
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(argv=None):
    args = parse_args(argv)
    delays_us = validate_settings(args)
    qua_repo = find_qua_repo(args.qua_repo)
    if str(qua_repo) not in sys.path:
        sys.path.insert(0, str(qua_repo))
    from LabCode.Config.config_helpers import meta_dict_to_config_1Q_ft
    from LabCode.Config.make_meta_dict_flux_tunable import make_meta_dict
    from LabCode.CoreLib.experiment import qmm
    from LabCode.Experiments.Readout_Cal.m_single_shot_1Q import SingleShot1Q
    from LabCode.PythonDrivers.control_8257 import set_LO_parameters

    meta_dict = make_meta_dict(args.qubit, chip=args.chip)[args.qubit]
    if args.park_voltage is not None:
        meta_dict["flux_dc_offset"] = float(args.park_voltage)
    park_voltage = float(meta_dict["flux_dc_offset"])
    settle_ns = int(meta_dict.get("flux_settle_time", 0) if args.flux_settle_ns is None else args.flux_settle_ns)
    outer_folder = meta_dict["global_params"]["outer_folder"]
    set_LO_parameters([meta_dict["q_LO"], meta_dict["r_LO"]])
    config = meta_dict_to_config_1Q_ft(meta_dict)
    calibration_run = SingleShot1Q(
        args.qubit,
        args.ss_shots,
        meta_dict=meta_dict,
        outer_folder=outer_folder,
        path=args.qubit,
        suffix="OPX_active_reset_reference_SS",
        config=config,
        save=True,
        plot=True,
    )
    if calibration_run.max_F < args.min_fidelity:
        raise RuntimeError(f"single-shot fidelity {calibration_run.max_F:.4f} is below {args.min_fidelity:.4f}")
    calibration = dict(calibration_run.calib_params)
    meta_dict["read_theta"] = calibration["read_theta"]
    config = meta_dict_to_config_1Q_ft(meta_dict)
    methods = dict(DEFAULT_METHODS)
    schedule = build_interleaved_schedule(args.rounds, tuple(methods), len(delays_us), args.seed)
    prog = make_program(
        meta_dict,
        calibration,
        methods,
        delays_us,
        schedule,
        args.shots_per_block,
        args.dc_target_voltage,
        park_voltage,
        settle_ns,
    )
    output_dir = make_output_dir(outer_folder, args.qubit)
    metadata = {
        "created": datetime.now().isoformat(),
        "qua_repo": str(qua_repo),
        "chip": args.chip,
        "qubit": args.qubit,
        "methods": methods,
        "delays_us": delays_us,
        "rounds": args.rounds,
        "shots_per_block": args.shots_per_block,
        "seed": args.seed,
        "ss_shots": args.ss_shots,
        "ss_fidelity": float(calibration_run.max_F),
        "calibration": calibration,
        "dc_target_voltage": args.dc_target_voltage,
        "park_voltage": park_voltage,
        "flux_settle_ns": settle_ns,
        "schedule": [(round_index, tuple(methods)[method_code], delay_index) for round_index, method_code, delay_index in schedule],
    }
    write_json(output_dir / "metadata.json", metadata)
    qm = qmm.open_qm(config)
    qmm.clear_all_job_results()
    started = time.perf_counter()
    job = qm.execute(prog, duration_limit=0, data_limit=0)
    expected_count = len(schedule) * args.shots_per_block
    records = make_records(job, methods, delays_us, expected_count)
    host_elapsed_s = time.perf_counter() - started
    summary = summarize_shots(records, tuple(methods), delays_us)
    fitted = fit_method_decays(summary["overall"], tuple(methods))
    comparison = make_comparison(fitted["fits"], "passive_1000")
    timing = summarize_block_timings(records, tuple(methods), "passive_1000")
    results = {
        "fits": fitted["fits"],
        "fit_errors": fitted["errors"],
        "comparison": comparison,
        "timing": timing,
        "host_elapsed_s": host_elapsed_s,
    }
    write_csv(output_dir / "raw_shots.csv", records)
    write_csv(output_dir / "summary.csv", summary["overall"])
    write_csv(output_dir / "round_summary.csv", summary["rounds"])
    write_csv(output_dir / "shot_order.csv", summary["shot_order"])
    write_json(output_dir / "results.json", results)
    plot_results(summary, fitted["fits"], comparison, timing, tuple(methods), output_dir / "comparison.png")
    print(f"output={output_dir}")
    for row in comparison:
        timing_row = next((value for value in timing if value["method"] == row["method"]), None)
        speedup = float("nan") if timing_row is None else timing_row["speedup_to_passive"]
        print(f"{row['method']} T1={row['tau_us']:.3f} us ratio={row['tau_ratio_to_passive']:.3f} speedup={speedup:.3f}")


if __name__ == "__main__":
    main()
