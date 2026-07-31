import csv
import datetime
import gc
import json
import os
import time

import h5py
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q, discriminate_shots
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTLSMemory import MEMORY_SEQUENCES, TLSMemory
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as TLS


P = {
    "tls_nominal_freq_ghz": 2.234178,
    "control_detuning_mhz": 5.0,
    "dc_search_max": 15000.0,
    "interaction_min_us": 0.0,
    "interaction_max_us": 5.0,
    "interaction_step_us": 0.1,
    "storage_us": [0.0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0,
                   3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0, 50.0, 75.0,
                   100.0, 150.0, 200.0],
    "shots": 400,
    "park_cal_shots": 1000,
    "passive_reset_us": 1500.0,
    "min_assignment_contrast": 0.50,
    "smooth_points": 3,
    "min_center_retrieval": 0.04,
    "min_center_excess_over_controls": 0.06,
    "run_storage_if_detected": True,
    "order_seed": 20260731,
    "checkpoint_every": 3,
    "progress_every": 15,
}


def hms(seconds):
    seconds = float(seconds)
    if seconds < 90.0:
        return f"{seconds:.1f} s"
    if seconds < 5400.0:
        return f"{seconds / 60.0:.1f} min"
    return f"{seconds / 3600.0:.2f} h"


def json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def interaction_times_us(p=P):
    start = float(p["interaction_min_us"])
    stop = float(p["interaction_max_us"])
    step = float(p["interaction_step_us"])
    if not np.isfinite([start, stop, step]).all() or start < 0.0 or stop < start or step <= 0.0:
        raise ValueError("interaction bounds must be finite with 0 <= min <= max and step > 0")
    count = int(np.floor((stop - start) / step + 0.5))
    values = start + step * np.arange(count + 1, dtype=float)
    return np.round(values[values <= stop + 1e-9], 9)


def storage_times_us(p=P):
    values = np.unique(np.asarray(p["storage_us"], dtype=float))
    if values.size == 0 or np.any(~np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError("storage_us must contain finite non-negative values")
    return values


def target_table(p=P, flux_fit_params=None, base_config=BaseConfig):
    params = TLS.FLUX_FIT_PARAMS if flux_fit_params is None else flux_fit_params
    if params is None:
        raise RuntimeError("FLUX_FIT_PARAMS is required")
    center = float(p["tls_nominal_freq_ghz"])
    detuning = float(p["control_detuning_mhz"])
    search_max = float(p["dc_search_max"])
    if not np.isfinite(center) or not np.isfinite(detuning) or detuning <= 0.0:
        raise ValueError("TLS frequency and control detuning must be finite and positive")
    f_edges = fx.estimate_fit_frequency_ghz_array(params, np.asarray([0.0, search_max]))
    f_min, f_max = float(np.min(f_edges)), float(np.max(f_edges))
    fit_park = fx.estimate_fit_frequency_ghz(params, 0.0)
    configured_park = float(base_config["qubit_pi_freq"]) / 1e3
    anchor_shift = configured_park - fit_park
    targets = []
    for role, offset in (("minus", -detuning), ("tls", 0.0), ("plus", detuning)):
        requested = center + offset / 1e3
        if requested < f_min or requested > f_max:
            raise ValueError(f"target {requested:.9f} GHz is outside {f_min:.9f}..{f_max:.9f} GHz")
        dc = float(fx.frequency_to_local_flux_branch(
            params, np.asarray([requested]), 0.0, search_max)[0])
        predicted = fx.estimate_fit_frequency_ghz(params, dc)
        if abs(predicted - requested) > 1e-6:
            raise RuntimeError(f"could not invert {requested:.9f} GHz")
        targets.append({
            "target_index": len(targets),
            "role": role,
            "label": f"tls_1_{role}",
            "detuning_mhz": float(offset),
            "nominal_freq_ghz": float(requested),
            "park_anchored_freq_ghz": float(requested + anchor_shift),
            "dc_gain": dc,
        })
    return targets, fit_park, anchor_shift


def block_schedule(targets, axis_values, stage, interaction_us, p=P):
    blocks = []
    for target in targets:
        for value in np.asarray(axis_values, dtype=float):
            blocks.append({
                "block_index": len(blocks),
                "target_index": int(target["target_index"]),
                "interaction_us": float(value if stage == "interaction_scan" else interaction_us),
                "storage_us": float(0.0 if stage == "interaction_scan" else value),
            })
    rng = np.random.default_rng(int(p["order_seed"]) + (0 if stage == "interaction_scan" else 1))
    block_order = rng.permutation(len(blocks))
    schedule = []
    for block_visit, block_index in enumerate(block_order):
        block = blocks[int(block_index)]
        sequence_order = rng.permutation(len(MEMORY_SEQUENCES))
        for within_block, sequence_index in enumerate(sequence_order):
            schedule.append({
                **block,
                "stage": stage,
                "block_visit": int(block_visit),
                "within_block": int(within_block),
                "sequence": MEMORY_SEQUENCES[int(sequence_index)],
                "visit": len(schedule),
            })
    return schedule


def base_cfg(p, correction, target_dcs):
    cfg = dict(BaseConfig)
    cfg.update({
        "reset_mode": "passive",
        "relax_delay": float(p["passive_reset_us"]),
        "shots": int(p["shots"]),
        "reps": int(p["shots"]),
        "ff_gain_vec": np.asarray(target_dcs, dtype=float),
        "flux_tail_compensation": correction,
        "flux_fit_params": TLS.FLUX_FIT_PARAMS,
        "randomize_point_order": True,
        "point_order_seed": int(p["order_seed"]),
    })
    return cfg


def output_base(outer_folder):
    now = datetime.datetime.now()
    folder = os.path.join(outer_folder, TLS.QUBIT, f"{TLS.QUBIT}_{now:%Y_%m_%d}")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{TLS.QUBIT}_{now:%H_%M_%S}_TLSMemoryAudit")


def run_park_calibration(soc, soccfg, p, outer_folder):
    cfg = dict(BaseConfig)
    cfg.update({
        "reset_mode": "passive",
        "relax_delay": float(p["passive_reset_us"]),
        "shots": int(p["park_cal_shots"]),
        "reps": int(p["park_cal_shots"]),
    })
    started = time.time()
    ss = SingleShot1Q(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outer_folder,
        suffix="TLSMemoryAudit_SS_Park", cfg=cfg, repeats=1,
        confidence_threshold=0.0)
    ss.acquire(progress=False, plotDisp=False)
    assignment = {
        "P_g": float(np.mean(discriminate_shots(ss.I_0, ss.Q_0, ss.calib_params))),
        "P_e": float(np.mean(discriminate_shots(ss.I_1, ss.Q_1, ss.calib_params))),
    }
    assignment["contrast"] = assignment["P_e"] - assignment["P_g"]
    if assignment["contrast"] < float(p["min_assignment_contrast"]):
        raise RuntimeError(
            f"park assignment contrast {assignment['contrast']:.3f} is below "
            f"{float(p['min_assignment_contrast']):.3f}")
    plt.close("all")
    return ss, assignment, time.time() - started


def run_point(soc, soccfg, cfg, p, outer_folder, target, item, calib_params, assignment):
    started = time.time()
    exp = TLSMemory(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outer_folder,
        suffix="TLSMemoryAudit_Point", cfg=dict(cfg),
        ff_gain=float(target["dc_gain"]),
        interaction_us=float(item["interaction_us"]),
        storage_us=float(item["storage_us"]),
        sequence=item["sequence"], shots=int(p["shots"]),
        calib_params=calib_params, assignment_reference=assignment)
    exp.acquire(progress=False, plotDisp=False)
    theta = float(calib_params["read_theta"])
    rotated = np.exp(-1j * theta) * (np.asarray(exp.raw["i"]) + 1j * np.asarray(exp.raw["q"]))
    iq = {
        "I_median": float(np.median(exp.raw["i"])),
        "Q_median": float(np.median(exp.raw["q"])),
        "rotated_x_median": float(np.median(rotated.real)),
        "rotated_y_median": float(np.median(rotated.imag)),
        "rotated_x_iqr": float(np.subtract(*np.percentile(rotated.real, [75, 25]))),
        "rotated_y_iqr": float(np.subtract(*np.percentile(rotated.imag, [75, 25]))),
    }
    return exp, iq, time.time() - started


def create_stage(handle, name, schedule, shots):
    group = handle.create_group(name)
    n = len(schedule)
    group.attrs["total_points"] = n
    group.attrs["completed_points"] = 0
    for key in ("visit", "block_index", "block_visit", "within_block", "target_index"):
        group.create_dataset(key, data=np.asarray([item[key] for item in schedule], dtype=np.int32))
    for key in ("interaction_us", "storage_us"):
        group.create_dataset(key, data=np.asarray([item[key] for item in schedule], dtype=float))
    string_dtype = h5py.string_dtype("utf-8")
    group.create_dataset("sequence", data=np.asarray([item["sequence"] for item in schedule], dtype=object), dtype=string_dtype)
    group.create_dataset("completed", shape=(n,), dtype=np.int8, fillvalue=0)
    group.create_dataset("error", shape=(n,), dtype=string_dtype)
    for key in ("P_excited", "population_corrected", "keep_fraction", "elapsed_s",
                "acquired_unix_s", "I_median", "Q_median", "rotated_x_median",
                "rotated_y_median", "rotated_x_iqr", "rotated_y_iqr"):
        group.create_dataset(key, shape=(n,), dtype=float, fillvalue=np.nan)
    for key in ("I", "Q", "herald_I", "herald_Q"):
        group.create_dataset(
            key, shape=(n, int(shots)), dtype=float, fillvalue=np.nan,
            chunks=(1, int(shots)), compression="gzip", compression_opts=1)
    return group


def create_h5(path, p, cfg, targets, park_ss, assignment, fit_park, anchor_shift,
              schedule):
    with h5py.File(path, "w") as handle:
        handle.attrs["schema"] = "tls_population_memory_audit_v1"
        handle.attrs["settings"] = json.dumps(p, default=json_default)
        handle.attrs["base_config"] = json.dumps(cfg, default=json_default)
        handle.attrs["fit_park_freq_ghz"] = float(fit_park)
        handle.attrs["configured_park_freq_ghz"] = float(BaseConfig["qubit_pi_freq"]) / 1e3
        handle.attrs["park_anchor_shift_ghz"] = float(anchor_shift)
        handle.attrs["storage_stage_run"] = False
        target_group = handle.create_group("targets")
        for key in ("target_index", "detuning_mhz", "nominal_freq_ghz",
                    "park_anchored_freq_ghz", "dc_gain"):
            target_group.create_dataset(key, data=np.asarray([target[key] for target in targets]))
        string_dtype = h5py.string_dtype("utf-8")
        for key in ("role", "label"):
            target_group.create_dataset(
                key, data=np.asarray([target[key] for target in targets], dtype=object),
                dtype=string_dtype)
        park = handle.create_group("park_cal")
        park.attrs["fidelity"] = float(park_ss.max_F)
        park.attrs["calib_params"] = json.dumps(park_ss.calib_params, default=json_default)
        park.attrs["assignment_reference"] = json.dumps(assignment, default=json_default)
        for key, values in (("I_0", park_ss.I_0), ("Q_0", park_ss.Q_0),
                            ("I_1", park_ss.I_1), ("Q_1", park_ss.Q_1)):
            park.create_dataset(key, data=np.asarray(values, dtype=float), compression="gzip")
        create_stage(handle, "interaction_scan", schedule, int(p["shots"]))
        handle.flush()


def write_point(group, item, exp, iq, elapsed):
    index = int(item["visit"])
    for key, value in exp.metrics.items():
        group[key][index] = float(value)
    for key, value in iq.items():
        group[key][index] = float(value)
    group["elapsed_s"][index] = float(elapsed)
    group["acquired_unix_s"][index] = time.time()
    group["I"][index, :] = np.asarray(exp.raw["i"], dtype=float)
    group["Q"][index, :] = np.asarray(exp.raw["q"], dtype=float)
    group["herald_I"][index, :] = np.asarray(exp.raw["herald_i"], dtype=float)
    group["herald_Q"][index, :] = np.asarray(exp.raw["herald_q"], dtype=float)
    group["completed"][index] = 1


def run_stage(handle, name, schedule, targets, soc, soccfg, cfg, p, outer_folder,
              calib_params, assignment):
    group = handle[name]
    started = time.time()
    completed = 0
    for item in schedule:
        index = int(item["visit"])
        target = targets[int(item["target_index"])]
        try:
            exp, iq, elapsed = run_point(
                soc, soccfg, cfg, p, outer_folder, target, item,
                calib_params, assignment)
            write_point(group, item, exp, iq, elapsed)
            completed += 1
        except KeyboardInterrupt:
            group.attrs["interrupted"] = True
            group.attrs["completed_points"] = completed
            handle.flush()
            raise
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            group["error"][index] = message
            print(f"{name} point {index + 1}/{len(schedule)} failed: {message}")
        group.attrs["completed_points"] = completed
        if ((index + 1) % int(p["checkpoint_every"]) == 0
                or index + 1 == len(schedule)):
            handle.flush()
        if ((index + 1) % int(p["progress_every"]) == 0
                or index + 1 == len(schedule)):
            elapsed_total = time.time() - started
            eta = elapsed_total / max(index + 1, 1) * (len(schedule) - index - 1)
            value = group["population_corrected"][index]
            print(f"{name} {index + 1:>4}/{len(schedule)}  {target['label']:<12}  "
                  f"{item['sequence']:<13}  interaction {item['interaction_us']:>4.1f} us  "
                  f"storage {item['storage_us']:>5.1f} us  P={value:.3f}  "
                  f"[{hms(elapsed_total)} elapsed, ETA {hms(eta)}]", flush=True)
        if index % 50 == 0:
            gc.collect()
    group.attrs["elapsed_s"] = float(time.time() - started)
    group.attrs["interrupted"] = False
    handle.flush()
    return completed


def stage_rows(group):
    completed = np.asarray(group["completed"][:], dtype=bool)
    sequences = np.asarray(group["sequence"][:]).astype(str)
    rows = []
    keys = ("visit", "block_index", "block_visit", "within_block", "target_index",
            "interaction_us", "storage_us", "P_excited", "population_corrected",
            "keep_fraction", "elapsed_s", "acquired_unix_s", "I_median", "Q_median",
            "rotated_x_median", "rotated_y_median", "rotated_x_iqr", "rotated_y_iqr")
    values = {key: np.asarray(group[key][:]) for key in keys}
    for index in np.flatnonzero(completed):
        row = {key: values[key][index].item() for key in keys}
        row["sequence"] = sequences[index]
        rows.append(row)
    return rows


def retrieval_rows(group):
    rows = stage_rows(group)
    blocks = {}
    for row in rows:
        key = (int(row["target_index"]), float(row["interaction_us"]),
               float(row["storage_us"]))
        blocks.setdefault(key, {})[row["sequence"]] = row
    result = []
    for key, values in blocks.items():
        if not all(sequence in values for sequence in MEMORY_SEQUENCES):
            continue
        result.append({
            "target_index": key[0],
            "interaction_us": key[1],
            "storage_us": key[2],
            "single": float(values["single"]["population_corrected"]),
            "double": float(values["double"]["population_corrected"]),
            "ground_double": float(values["ground_double"]["population_corrected"]),
            "retrieval": float(values["double"]["population_corrected"]
                               - values["single"]["population_corrected"]),
        })
    return result


def smooth(values, points):
    values = np.asarray(values, dtype=float)
    width = max(int(points), 1)
    if width % 2 == 0:
        width += 1
    if width == 1 or values.size < width:
        return values.copy()
    half = width // 2
    padded = np.pad(values, (half, half), mode="edge")
    return np.convolve(padded, np.ones(width) / width, mode="valid")


def select_interaction(group, p=P):
    rows = retrieval_rows(group)
    curves = {}
    for target_index in range(3):
        selected = sorted(
            [row for row in rows if row["target_index"] == target_index],
            key=lambda row: row["interaction_us"])
        curves[target_index] = selected
    if any(len(curves[index]) == 0 for index in range(3)):
        raise RuntimeError("interaction scan lacks a complete target curve")
    times = np.asarray([row["interaction_us"] for row in curves[1]], dtype=float)
    if any(not np.allclose(times, [row["interaction_us"] for row in curves[index]])
           for index in range(3)):
        raise RuntimeError("interaction scan target grids do not match")
    scores = {
        index: np.asarray([row["retrieval"] for row in curves[index]], dtype=float)
        for index in range(3)
    }
    smoothed = {index: smooth(scores[index], p["smooth_points"]) for index in range(3)}
    excess = smoothed[1] - 0.5 * (smoothed[0] + smoothed[2])
    index = int(np.nanargmax(excess))
    center = float(smoothed[1][index])
    center_excess = float(excess[index])
    detected = bool(
        center >= float(p["min_center_retrieval"])
        and center_excess >= float(p["min_center_excess_over_controls"]))
    return {
        "interaction_us": float(times[index]),
        "center_retrieval": center,
        "center_excess_over_controls": center_excess,
        "detected": detected,
        "times": times,
        "scores": scores,
        "smoothed": smoothed,
        "excess": excess,
    }


def save_csv(h5_path, csv_path, targets):
    target_map = {int(target["target_index"]): target for target in targets}
    fieldnames = [
        "stage", "visit", "block_index", "block_visit", "within_block",
        "target_index", "role", "label", "detuning_mhz", "nominal_freq_ghz",
        "park_anchored_freq_ghz", "dc_gain", "sequence", "interaction_us",
        "storage_us", "P_excited", "population_corrected", "keep_fraction",
        "elapsed_s", "acquired_unix_s", "I_median", "Q_median",
        "rotated_x_median", "rotated_y_median", "rotated_x_iqr", "rotated_y_iqr",
    ]
    with h5py.File(h5_path, "r") as handle, open(csv_path, "w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for stage in ("interaction_scan", "storage_sweep"):
            if stage not in handle:
                continue
            for row in stage_rows(handle[stage]):
                target = target_map[int(row["target_index"])]
                writer.writerow({
                    "stage": stage,
                    **row,
                    "role": target["role"],
                    "label": target["label"],
                    "detuning_mhz": target["detuning_mhz"],
                    "nominal_freq_ghz": target["nominal_freq_ghz"],
                    "park_anchored_freq_ghz": target["park_anchored_freq_ghz"],
                    "dc_gain": target["dc_gain"],
                })


def save_plot(h5_path, plot_path, targets, selected):
    with h5py.File(h5_path, "r") as handle:
        interaction = retrieval_rows(handle["interaction_scan"])
        storage = retrieval_rows(handle["storage_sweep"]) if "storage_sweep" in handle else []
        all_points = stage_rows(handle["interaction_scan"])
        if "storage_sweep" in handle:
            all_points.extend(stage_rows(handle["storage_sweep"]))
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    colors = ("tab:blue", "tab:red", "tab:green")
    for target, color in zip(targets, colors):
        index = int(target["target_index"])
        rows = sorted([row for row in interaction if row["target_index"] == index],
                      key=lambda row: row["interaction_us"])
        t = np.asarray([row["interaction_us"] for row in rows])
        axes[0, 0].plot(t, [row["single"] for row in rows], color=color, linestyle="--",
                          label=f"{target['role']} single")
        axes[0, 0].plot(t, [row["double"] for row in rows], color=color,
                          label=f"{target['role']} double")
        axes[0, 1].plot(t, [row["retrieval"] for row in rows], color=color,
                          marker=".", label=target["role"])
        storage_rows = sorted([row for row in storage if row["target_index"] == index],
                              key=lambda row: row["storage_us"])
        if storage_rows:
            s = np.asarray([row["storage_us"] for row in storage_rows])
            axes[1, 0].plot(s, [row["retrieval"] for row in storage_rows],
                              color=color, marker="o", label=target["role"])
            axes[1, 0].plot(s, [row["ground_double"] for row in storage_rows],
                              color=color, linestyle=":", alpha=0.7)
    axes[0, 0].set_xlabel("Interaction hold [us]")
    axes[0, 0].set_ylabel("Corrected excited population")
    axes[0, 0].set_title("Single pass and double pass")
    axes[0, 0].legend(ncol=2)
    axes[0, 1].axhline(0.0, color="black", linewidth=0.8)
    axes[0, 1].axvline(float(selected["interaction_us"]), color="black", linestyle=":")
    axes[0, 1].set_xlabel("Interaction hold [us]")
    axes[0, 1].set_ylabel("Double minus single")
    axes[0, 1].set_title("Population retrieval score")
    axes[0, 1].legend()
    axes[1, 0].axhline(0.0, color="black", linewidth=0.8)
    axes[1, 0].set_xscale("symlog", linthresh=0.1)
    axes[1, 0].set_xlabel("Storage at park [us]")
    axes[1, 0].set_ylabel("Retrieval score")
    axes[1, 0].set_title("Storage and retrieval" if storage else "Storage stage not run")
    if storage:
        axes[1, 0].legend()
    points = sorted(all_points, key=lambda row: row["acquired_unix_s"])
    axes[1, 1].plot([row["rotated_y_median"] for row in points], label="rotated y median")
    axes[1, 1].plot([row["rotated_y_iqr"] for row in points], label="rotated y IQR")
    axes[1, 1].set_xlabel("Acquisition visit")
    axes[1, 1].set_ylabel("Rotated IQ coordinate")
    axes[1, 1].set_title("Readout orthogonal-axis monitor")
    axes[1, 1].legend()
    status = "detected" if selected["detected"] else "not detected"
    fig.suptitle(
        f"TLS population memory audit: {status}, interaction "
        f"{selected['interaction_us']:.3f} us, center retrieval "
        f"{selected['center_retrieval']:.3f}, excess "
        f"{selected['center_excess_over_controls']:.3f}")
    fig.savefig(plot_path, dpi=180)
    plt.close(fig)


def run(soc, soccfg, outer_folder=outerFolder, settings=None):
    p = dict(P if settings is None else settings)
    interactions = interaction_times_us(p)
    storages = storage_times_us(p)
    targets, fit_park, anchor_shift = target_table(p)
    correction = TLS._load_correction(None, outer_folder)
    cfg = base_cfg(p, correction, [target["dc_gain"] for target in targets])
    interaction_schedule = block_schedule(
        targets, interactions, "interaction_scan", 0.0, p)
    base_path = output_base(outer_folder)
    h5_path = f"{base_path}_raw.h5"
    csv_path = f"{base_path}.csv"
    plot_path = f"{base_path}.png"
    stage1_floor = len(interaction_schedule) * int(p["shots"]) * float(
        p["passive_reset_us"]) * 1e-6
    stage2_points = len(targets) * len(storages) * len(MEMORY_SEQUENCES)
    stage2_floor = stage2_points * int(p["shots"]) * float(p["passive_reset_us"]) * 1e-6
    print("=" * 96)
    print("TLS POPULATION STORAGE AND RETRIEVAL AUDIT")
    print(f"stage 1: {len(targets)} targets x {len(interactions)} interactions x "
          f"{len(MEMORY_SEQUENCES)} arms = {len(interaction_schedule)} points")
    print(f"stage 2 if retrieval is detected: {len(targets)} targets x {len(storages)} "
          f"storage delays x {len(MEMORY_SEQUENCES)} arms = {stage2_points} points")
    print(f"passive reset {float(p['passive_reset_us']):g} us, {int(p['shots'])} shots")
    print(f"pulse-time lower bounds: stage 1 {hms(stage1_floor)}, stage 2 {hms(stage2_floor)}")
    print(f"checkpoint H5: {h5_path}")
    print(f"fit park {fit_park:.9f} GHz, configured park "
          f"{float(BaseConfig['qubit_pi_freq']) / 1e3:.9f} GHz, "
          f"anchor shift {anchor_shift * 1e3:+.3f} MHz")
    for target in targets:
        print(f"{target['label']:<12} nominal {target['nominal_freq_ghz']:.6f} GHz  "
              f"dc {target['dc_gain']:.3f}  "
              f"park-anchored {target['park_anchored_freq_ghz']:.6f} GHz")
    print("=" * 96)
    park_ss, assignment, park_elapsed = run_park_calibration(
        soc, soccfg, p, outer_folder)
    print(f"park SS fidelity {park_ss.max_F:.3f}, assignment contrast "
          f"{assignment['contrast']:.3f}, {hms(park_elapsed)}")
    create_h5(
        h5_path, p, cfg, targets, park_ss, assignment, fit_park,
        anchor_shift, interaction_schedule)
    with h5py.File(h5_path, "r+") as handle:
        run_stage(
            handle, "interaction_scan", interaction_schedule, targets,
            soc, soccfg, cfg, p, outer_folder, park_ss.calib_params, assignment)
        selected = select_interaction(handle["interaction_scan"], p)
        handle.attrs["selected_interaction_us"] = selected["interaction_us"]
        handle.attrs["center_retrieval"] = selected["center_retrieval"]
        handle.attrs["center_excess_over_controls"] = selected["center_excess_over_controls"]
        handle.attrs["retrieval_detected"] = selected["detected"]
        print("=" * 96)
        print(f"selected interaction {selected['interaction_us']:.3f} us")
        print(f"center retrieval {selected['center_retrieval']:+.3f}")
        print(f"center excess over controls {selected['center_excess_over_controls']:+.3f}")
        print(f"retrieval {'DETECTED' if selected['detected'] else 'NOT DETECTED'}")
        if bool(p["run_storage_if_detected"]) and selected["detected"]:
            storage_schedule = block_schedule(
                targets, storages, "storage_sweep", selected["interaction_us"], p)
            create_stage(handle, "storage_sweep", storage_schedule, int(p["shots"]))
            handle.attrs["storage_stage_run"] = True
            handle.flush()
            run_stage(
                handle, "storage_sweep", storage_schedule, targets,
                soc, soccfg, cfg, p, outer_folder, park_ss.calib_params, assignment)
        else:
            print("storage sweep skipped; the complete interaction scan remains saved")
        handle.attrs["completed"] = True
        handle.flush()
    save_csv(h5_path, csv_path, targets)
    save_plot(h5_path, plot_path, targets, selected)
    print("=" * 96)
    print(f"raw H5: {h5_path}")
    print(f"CSV:    {csv_path}")
    print(f"plot:   {plot_path}")
    print("=" * 96)
    return {"h5": h5_path, "csv": csv_path, "plot": plot_path, "selected": selected}


def main():
    with tee_log.tee(outerFolder, "TLSMemoryAudit"):
        soc, soccfg = makeProxy()
        run(soc, soccfg)


if __name__ == "__main__":
    main()
