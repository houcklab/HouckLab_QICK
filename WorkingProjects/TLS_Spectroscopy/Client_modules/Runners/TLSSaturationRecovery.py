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
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTLSSaturation import SATURATION_ARMS, TLSSaturationProbe
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, tee_log
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSMemoryAudit as MemoryAudit
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as TLS


P = {
    "tls_nominal_freq_ghz": 2.234178,
    "control_detuning_mhz": 5.0,
    "dc_search_max": 15000.0,
    "pump_gains": [1500, 3000, 6000, 9000, 12000],
    "pump_us": 15.0,
    "probe_us": 5.0,
    "dose_repeats": 5,
    "confirmation_repeats": 8,
    "recovery_us": [0.5, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0],
    "recovery_repeats": 4,
    "shots": 400,
    "park_cal_shots": 1000,
    "reset_probe_shots": 1000,
    "reset_max_iters": 3,
    "reset_thermalization_us": 0.0,
    "passive_reset_us": 1500.0,
    "min_assignment_contrast": 0.50,
    "min_center_effect": 0.03,
    "min_center_excess": 0.04,
    "min_excess_z": 2.5,
    "min_sign_fraction": 0.75,
    "confirmation_min_center_effect": 0.02,
    "confirmation_min_center_excess": 0.03,
    "confirmation_min_excess_z": 2.5,
    "run_confirmation_if_detected": True,
    "run_recovery_if_confirmed": True,
    "order_seed": 20260731,
    "checkpoint_every": 2,
    "progress_every": 12,
}


def hms(seconds):
    return MemoryAudit.hms(seconds)


def json_default(value):
    return MemoryAudit.json_default(value)


def pump_gains(p=P):
    values = np.unique(np.asarray(p["pump_gains"], dtype=int))
    if values.size == 0 or np.any(values <= 0):
        raise ValueError("pump_gains must contain positive integers")
    return values


def recovery_times_us(p=P):
    values = np.unique(np.asarray(p["recovery_us"], dtype=float))
    if values.size == 0 or np.any(~np.isfinite(values)) or np.any(values <= 0.0):
        raise ValueError("recovery_us must contain finite positive values")
    return values


def target_table(p=P, flux_fit_params=None, base_config=BaseConfig):
    return MemoryAudit.target_table(
        p=p, flux_fit_params=flux_fit_params, base_config=base_config)


def stage_schedule(targets, values, repeats, stage, selected_gain=None, p=P):
    if stage not in ("dose_scan", "confirmation", "recovery_sweep"):
        raise ValueError("invalid saturation stage")
    values = np.asarray(values, dtype=float)
    repeats = int(repeats)
    if values.size == 0 or repeats <= 0:
        raise ValueError("stage values and repeats must be positive")
    superblocks = []
    for repeat in range(repeats):
        for value in values:
            superblocks.append({
                "superblock_index": len(superblocks),
                "repeat": repeat,
                "pump_gain": int(round(value)) if stage == "dose_scan" else int(selected_gain),
                "recovery_us": 0.0 if stage != "recovery_sweep" else float(value),
            })
    offsets = {"dose_scan": 0, "confirmation": 1, "recovery_sweep": 2}
    rng = np.random.default_rng(int(p["order_seed"]) + offsets[stage])
    order = rng.permutation(len(superblocks))
    schedule = []
    block_index = 0
    for superblock_visit, source_index in enumerate(order):
        superblock = superblocks[int(source_index)]
        for target_within, target_index in enumerate(rng.permutation(len(targets))):
            arm_order = rng.permutation(len(SATURATION_ARMS))
            for within_block, arm_index in enumerate(arm_order):
                schedule.append({
                    **superblock,
                    "stage": stage,
                    "superblock_visit": int(superblock_visit),
                    "target_within_superblock": int(target_within),
                    "block_index": int(block_index),
                    "within_block": int(within_block),
                    "target_index": int(target_index),
                    "arm": SATURATION_ARMS[int(arm_index)],
                    "visit": len(schedule),
                })
            block_index += 1
    return schedule


def base_cfg(p, correction, target_dcs, reset_record):
    cfg = dict(BaseConfig)
    cfg.update({
        "shots": int(p["shots"]),
        "reps": int(p["shots"]),
        "relax_delay": float(p["passive_reset_us"]),
        "ff_gain_vec": np.asarray(target_dcs, dtype=float),
        "flux_tail_compensation": correction,
        "flux_fit_params": TLS.FLUX_FIT_PARAMS,
        "randomize_point_order": True,
        "point_order_seed": int(p["order_seed"]),
        "saturation_reset_thermalization_us": float(p["reset_thermalization_us"]),
    })
    cfg.update(active_reset.feedback_runtime_from_probe(
        reset_record, max_iters=int(p["reset_max_iters"]),
        thermalization_us=float(p["reset_thermalization_us"]),
        post_measure_delay_us=0.05))
    cfg["relax_delay"] = float(p["passive_reset_us"])
    return cfg


def output_base(outer_folder):
    now = datetime.datetime.now()
    folder = os.path.join(outer_folder, TLS.QUBIT, f"{TLS.QUBIT}_{now:%Y_%m_%d}")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{TLS.QUBIT}_{now:%H_%M_%S}_TLSSaturationRecovery")


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
        suffix="TLSSaturationRecovery_SS_Park", cfg=cfg, repeats=1,
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


def run_reset_calibration(soc, soccfg, p, outer_folder):
    started = time.time()
    record = active_reset.probe_reset_params(
        soc, soccfg, BaseConfig, path=TLS.QUBIT, outer_folder=outer_folder,
        shots=int(p["reset_probe_shots"]), validate=True,
        reset_max_iters=int(p["reset_max_iters"]))
    if not active_reset.rotated_probe_record(record):
        raise RuntimeError("a validated rotated feedback reset is required")
    plt.close("all")
    return record, time.time() - started


def run_point(soc, soccfg, cfg, p, outer_folder, target, item,
              calib_params, assignment):
    started = time.time()
    exp = TLSSaturationProbe(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outer_folder,
        suffix="TLSSaturationRecovery_Point", cfg=dict(cfg),
        ff_gain=float(target["dc_gain"]),
        target_freq_mhz=float(target["park_anchored_freq_ghz"]) * 1e3,
        pump_gain=int(item["pump_gain"]), pump_us=float(p["pump_us"]),
        probe_us=float(p["probe_us"]), recovery_us=float(item["recovery_us"]),
        arm=item["arm"], shots=int(p["shots"]),
        calib_params=calib_params, assignment_reference=assignment)
    exp.acquire(progress=False, plotDisp=False)
    theta = float(calib_params["read_theta"])
    rotated = np.exp(-1j * theta) * (
        np.asarray(exp.raw["i"]) + 1j * np.asarray(exp.raw["q"]))
    iq = {
        "I_median": float(np.median(exp.raw["i"])),
        "Q_median": float(np.median(exp.raw["q"])),
        "rotated_x_median": float(np.median(rotated.real)),
        "rotated_y_median": float(np.median(rotated.imag)),
        "rotated_x_iqr": float(np.subtract(*np.percentile(rotated.real, [75, 25]))),
        "rotated_y_iqr": float(np.subtract(*np.percentile(rotated.imag, [75, 25]))),
    }
    return exp, iq, time.time() - started


def create_stage(handle, name, schedule, shots, reset_iters):
    group = handle.create_group(name)
    n = len(schedule)
    group.attrs["total_points"] = n
    group.attrs["completed_points"] = 0
    for key in ("visit", "superblock_index", "superblock_visit", "repeat",
                "target_within_superblock", "block_index", "within_block",
                "target_index", "pump_gain"):
        group.create_dataset(
            key, data=np.asarray([item[key] for item in schedule], dtype=np.int32))
    group.create_dataset(
        "recovery_us", data=np.asarray([item["recovery_us"] for item in schedule], dtype=float))
    string_dtype = h5py.string_dtype("utf-8")
    group.create_dataset(
        "arm", data=np.asarray([item["arm"] for item in schedule], dtype=object),
        dtype=string_dtype)
    group.create_dataset("completed", shape=(n,), dtype=np.int8, fillvalue=0)
    group.create_dataset("error", shape=(n,), dtype=string_dtype)
    for key in ("P_excited", "population_corrected", "reset_last_P_excited",
                "elapsed_s", "acquired_unix_s", "I_median", "Q_median",
                "rotated_x_median", "rotated_y_median", "rotated_x_iqr",
                "rotated_y_iqr"):
        group.create_dataset(key, shape=(n,), dtype=float, fillvalue=np.nan)
    for key in ("I", "Q"):
        group.create_dataset(
            key, shape=(n, int(shots)), dtype=float, fillvalue=np.nan,
            chunks=(1, int(shots)), compression="gzip", compression_opts=1)
    for key in ("reset_I", "reset_Q"):
        group.create_dataset(
            key, shape=(n, int(shots), int(reset_iters)), dtype=float,
            fillvalue=np.nan, chunks=(1, int(shots), int(reset_iters)),
            compression="gzip", compression_opts=1)
    return group


def create_h5(path, p, cfg, targets, park_ss, assignment, reset_record,
              fit_park, anchor_shift, dose_schedule):
    with h5py.File(path, "w") as handle:
        handle.attrs["schema"] = "tls_saturation_recovery_v1"
        handle.attrs["settings"] = json.dumps(p, default=json_default)
        handle.attrs["base_config"] = json.dumps(cfg, default=json_default)
        handle.attrs["fit_park_freq_ghz"] = float(fit_park)
        handle.attrs["configured_park_freq_ghz"] = float(BaseConfig["qubit_pi_freq"]) / 1e3
        handle.attrs["park_anchor_shift_ghz"] = float(anchor_shift)
        handle.attrs["confirmation_stage_run"] = False
        handle.attrs["recovery_stage_run"] = False
        target_group = handle.create_group("targets")
        for key in ("target_index", "detuning_mhz", "nominal_freq_ghz",
                    "park_anchored_freq_ghz", "dc_gain"):
            target_group.create_dataset(
                key, data=np.asarray([target[key] for target in targets]))
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
        reset = handle.create_group("reset_cal")
        reset.attrs["record"] = json.dumps(reset_record, default=json_default)
        create_stage(
            handle, "dose_scan", dose_schedule, int(p["shots"]),
            int(p["reset_max_iters"]))
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
    group["reset_I"][index, :, :] = np.asarray(exp.raw["reset_i"], dtype=float)
    group["reset_Q"][index, :, :] = np.asarray(exp.raw["reset_q"], dtype=float)
    group["completed"][index] = 1


def run_stage(handle, name, schedule, targets, soc, soccfg, cfg, p,
              outer_folder, calib_params, assignment):
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
                  f"{item['arm']:<7}  gain {item['pump_gain']:>5}  "
                  f"recovery {item['recovery_us']:>7.1f} us  P={value:.3f}  "
                  f"[{hms(elapsed_total)} elapsed, ETA {hms(eta)}]", flush=True)
        if index % 50 == 0:
            gc.collect()
    group.attrs["elapsed_s"] = float(time.time() - started)
    group.attrs["interrupted"] = False
    handle.flush()
    return completed


def stage_rows(group):
    completed = np.asarray(group["completed"][:], dtype=bool)
    arms = np.asarray(group["arm"][:]).astype(str)
    keys = ("visit", "superblock_index", "superblock_visit", "repeat",
            "target_within_superblock", "block_index", "within_block",
            "target_index", "pump_gain", "recovery_us", "P_excited",
            "population_corrected", "reset_last_P_excited", "elapsed_s",
            "acquired_unix_s", "I_median", "Q_median", "rotated_x_median",
            "rotated_y_median", "rotated_x_iqr", "rotated_y_iqr")
    values = {key: np.asarray(group[key][:]) for key in keys}
    rows = []
    for index in np.flatnonzero(completed):
        row = {key: values[key][index].item() for key in keys}
        row["arm"] = arms[index]
        rows.append(row)
    return rows


def paired_effect_rows(group):
    rows = stage_rows(group)
    blocks = {}
    for row in rows:
        blocks.setdefault(int(row["block_index"]), {})[row["arm"]] = row
    result = []
    for block_index, values in blocks.items():
        if not all(arm in values for arm in SATURATION_ARMS):
            continue
        base = values["no_pump"]
        pumped = values["pump"]
        result.append({
            "block_index": block_index,
            "superblock_index": int(base["superblock_index"]),
            "repeat": int(base["repeat"]),
            "target_index": int(base["target_index"]),
            "pump_gain": int(base["pump_gain"]),
            "recovery_us": float(base["recovery_us"]),
            "no_pump": float(base["population_corrected"]),
            "pump": float(pumped["population_corrected"]),
            "effect": float(pumped["population_corrected"]
                            - base["population_corrected"]),
        })
    return result


def aggregate_effects(group, axis_key):
    pairs = paired_effect_rows(group)
    superblocks = {}
    for row in pairs:
        key = int(row["superblock_index"])
        superblocks.setdefault(key, {})[int(row["target_index"])] = row
    samples = []
    for values in superblocks.values():
        if not all(index in values for index in range(3)):
            continue
        center = values[1]
        effects = np.asarray([values[index]["effect"] for index in range(3)], dtype=float)
        samples.append({
            axis_key: center[axis_key],
            "repeat": center["repeat"],
            "minus": float(effects[0]),
            "tls": float(effects[1]),
            "plus": float(effects[2]),
            "excess": float(effects[1] - 0.5 * (effects[0] + effects[2])),
        })
    result = []
    for axis_value in sorted(set(row[axis_key] for row in samples)):
        selected = [row for row in samples if row[axis_key] == axis_value]
        item = {axis_key: axis_value, "n": len(selected), "samples": selected}
        for key in ("minus", "tls", "plus", "excess"):
            values = np.asarray([row[key] for row in selected], dtype=float)
            item[key] = float(np.mean(values))
            item[f"{key}_sem"] = (float(np.std(values, ddof=1) / np.sqrt(values.size))
                                   if values.size > 1 else np.nan)
        signs = np.sign([row["excess"] for row in selected])
        mean_sign = np.sign(item["excess"])
        item["sign_fraction"] = float(np.mean(signs == mean_sign))
        item["excess_z"] = (float(item["excess"] / item["excess_sem"])
                            if np.isfinite(item["excess_sem"])
                            and item["excess_sem"] > 0.0 else np.nan)
        result.append(item)
    return result


def select_dose(group, p=P):
    aggregates = aggregate_effects(group, "pump_gain")
    if not aggregates:
        raise RuntimeError("dose scan has no complete paired superblocks")
    scores = np.asarray([
        abs(item["excess_z"]) if np.isfinite(item["excess_z"]) else -np.inf
        for item in aggregates])
    index = int(np.argmax(scores))
    selected = aggregates[index]
    detected = bool(
        abs(selected["tls"]) >= float(p["min_center_effect"])
        and abs(selected["excess"]) >= float(p["min_center_excess"])
        and abs(selected["excess_z"]) >= float(p["min_excess_z"])
        and selected["sign_fraction"] >= float(p["min_sign_fraction"]))
    return {**selected, "detected": detected, "aggregates": aggregates}


def confirm_dose(group, discovery, p=P):
    aggregates = aggregate_effects(group, "recovery_us")
    if len(aggregates) != 1:
        raise RuntimeError("confirmation stage lacks one complete recovery condition")
    result = aggregates[0]
    same_sign = bool(np.sign(result["excess"]) == np.sign(discovery["excess"]))
    confirmed = bool(
        same_sign
        and abs(result["tls"]) >= float(p["confirmation_min_center_effect"])
        and abs(result["excess"]) >= float(p["confirmation_min_center_excess"])
        and abs(result["excess_z"]) >= float(p["confirmation_min_excess_z"])
        and result["sign_fraction"] >= float(p["min_sign_fraction"]))
    return {**result, "same_sign": same_sign, "confirmed": confirmed,
            "aggregates": aggregates}


def save_csv(h5_path, csv_path, targets):
    target_map = {int(target["target_index"]): target for target in targets}
    fieldnames = [
        "stage", "visit", "superblock_index", "superblock_visit", "repeat",
        "target_within_superblock", "block_index", "within_block", "target_index",
        "role", "label", "detuning_mhz", "nominal_freq_ghz",
        "park_anchored_freq_ghz", "dc_gain", "arm", "pump_gain", "pump_us",
        "probe_us", "recovery_us", "P_excited", "population_corrected",
        "reset_last_P_excited", "elapsed_s", "acquired_unix_s", "I_median",
        "Q_median", "rotated_x_median", "rotated_y_median", "rotated_x_iqr",
        "rotated_y_iqr",
    ]
    with h5py.File(h5_path, "r") as handle, open(csv_path, "w", newline="") as stream:
        settings = json.loads(handle.attrs["settings"])
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for stage in ("dose_scan", "confirmation", "recovery_sweep"):
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
                    "pump_us": settings["pump_us"],
                    "probe_us": settings["probe_us"],
                })


def save_plot(h5_path, plot_path, targets, discovery, confirmation):
    with h5py.File(h5_path, "r") as handle:
        dose = aggregate_effects(handle["dose_scan"], "pump_gain")
        recovery = (aggregate_effects(handle["recovery_sweep"], "recovery_us")
                    if "recovery_sweep" in handle else [])
        confirmation_points = (aggregate_effects(handle["confirmation"], "recovery_us")
                               if "confirmation" in handle else [])
        all_points = []
        for stage in ("dose_scan", "confirmation", "recovery_sweep"):
            if stage in handle:
                all_points.extend(stage_rows(handle[stage]))
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    colors = ("tab:blue", "tab:red", "tab:green")
    gains = np.asarray([row["pump_gain"] for row in dose], dtype=float)
    for index, (target, color) in enumerate(zip(targets, colors)):
        key = ("minus", "tls", "plus")[index]
        axes[0, 0].errorbar(
            gains, [row[key] for row in dose],
            yerr=[row[f"{key}_sem"] for row in dose], marker="o", color=color,
            label=target["role"])
    axes[0, 0].axhline(0.0, color="black", linewidth=0.8)
    axes[0, 0].axvline(discovery["pump_gain"], color="black", linestyle=":")
    axes[0, 0].set_xlabel("Saturation tone gain [DAC]")
    axes[0, 0].set_ylabel("Pump minus no-pump population")
    axes[0, 0].set_title("Dose response")
    axes[0, 0].legend()
    axes[0, 1].errorbar(
        gains, [row["excess"] for row in dose],
        yerr=[row["excess_sem"] for row in dose], marker="o", color="tab:purple")
    axes[0, 1].axhline(0.0, color="black", linewidth=0.8)
    axes[0, 1].axvline(discovery["pump_gain"], color="black", linestyle=":")
    axes[0, 1].set_xlabel("Saturation tone gain [DAC]")
    axes[0, 1].set_ylabel("TLS effect minus mean controls")
    axes[0, 1].set_title("Center-specific pump effect")
    combined = confirmation_points + recovery
    if combined:
        combined = sorted(combined, key=lambda row: row["recovery_us"])
        delays = np.asarray([row["recovery_us"] for row in combined], dtype=float)
        for key, color in zip(("minus", "tls", "plus"), colors):
            axes[1, 0].errorbar(
                delays, [row[key] for row in combined],
                yerr=[row[f"{key}_sem"] for row in combined], marker="o",
                color=color, label=key)
        axes[1, 0].errorbar(
            delays, [row["excess"] for row in combined],
            yerr=[row["excess_sem"] for row in combined], marker="s",
            color="tab:purple", label="center excess")
        axes[1, 0].set_xscale("symlog", linthresh=0.5)
        axes[1, 0].legend()
    axes[1, 0].axhline(0.0, color="black", linewidth=0.8)
    axes[1, 0].set_xlabel("Additional recovery after reset [us]")
    axes[1, 0].set_ylabel("Pump effect")
    axes[1, 0].set_title("Independent confirmation and recovery")
    points = sorted(all_points, key=lambda row: row["acquired_unix_s"])
    axes[1, 1].plot([row["rotated_y_median"] for row in points],
                    label="rotated y median")
    axes[1, 1].plot([row["rotated_y_iqr"] for row in points],
                    label="rotated y IQR")
    axes[1, 1].set_xlabel("Acquisition visit")
    axes[1, 1].set_ylabel("Rotated IQ coordinate")
    axes[1, 1].set_title("Readout orthogonal-axis monitor")
    axes[1, 1].legend()
    discovery_status = "detected" if discovery["detected"] else "not detected"
    confirmation_status = (
        "confirmed" if confirmation and confirmation["confirmed"]
        else "not confirmed" if confirmation else "not run")
    fig.suptitle(
        f"TLS saturation recovery: {discovery_status}, {confirmation_status}, "
        f"gain {discovery['pump_gain']}, discovery excess "
        f"{discovery['excess']:+.3f} ({discovery['excess_z']:+.2f} sigma)")
    fig.savefig(plot_path, dpi=180)
    plt.close(fig)


def run(soc, soccfg, outer_folder=outerFolder, settings=None):
    p = dict(P if settings is None else settings)
    gains = pump_gains(p)
    recoveries = recovery_times_us(p)
    targets, fit_park, anchor_shift = target_table(p)
    correction = TLS._load_correction(None, outer_folder)
    dose_schedule = stage_schedule(
        targets, gains, int(p["dose_repeats"]), "dose_scan", p=p)
    confirmation_points = len(targets) * int(p["confirmation_repeats"]) * len(SATURATION_ARMS)
    recovery_points = (len(targets) * len(recoveries) * int(p["recovery_repeats"])
                       * len(SATURATION_ARMS))
    base_path = output_base(outer_folder)
    h5_path = f"{base_path}_raw.h5"
    csv_path = f"{base_path}.csv"
    plot_path = f"{base_path}.png"
    floor_scale = int(p["shots"]) * float(p["passive_reset_us"]) * 1e-6
    print("=" * 96)
    print("TLS SATURATION AND RECOVERY PUMP-PROBE")
    print(f"dose discovery: {len(targets)} targets x {len(gains)} gains x "
          f"{int(p['dose_repeats'])} repeats x {len(SATURATION_ARMS)} arms = "
          f"{len(dose_schedule)} points")
    print(f"independent confirmation if detected: {confirmation_points} points")
    print(f"recovery sweep if confirmed: {recovery_points} points")
    print(f"park X180 only; target-frequency tone is uncalibrated saturation drive")
    print(f"pump {float(p['pump_us']):g} us, probe hold {float(p['probe_us']):g} us, "
          f"passive reset {float(p['passive_reset_us']):g} us, {int(p['shots'])} shots")
    print(f"pulse-time lower bounds: discovery {hms(len(dose_schedule) * floor_scale)}, "
          f"confirmation {hms(confirmation_points * floor_scale)}, "
          f"recovery {hms(recovery_points * floor_scale)}")
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
    reset_record, reset_elapsed = run_reset_calibration(
        soc, soccfg, p, outer_folder)
    print(f"rotated reset validated, threshold {int(reset_record['threshold_raw'])}, "
          f"{hms(reset_elapsed)}")
    cfg = base_cfg(
        p, correction, [target["dc_gain"] for target in targets], reset_record)
    create_h5(
        h5_path, p, cfg, targets, park_ss, assignment, reset_record,
        fit_park, anchor_shift, dose_schedule)
    confirmation = None
    with h5py.File(h5_path, "r+") as handle:
        run_stage(
            handle, "dose_scan", dose_schedule, targets, soc, soccfg, cfg, p,
            outer_folder, park_ss.calib_params, assignment)
        discovery = select_dose(handle["dose_scan"], p)
        handle.attrs["selected_pump_gain"] = int(discovery["pump_gain"])
        handle.attrs["discovery_center_effect"] = float(discovery["tls"])
        handle.attrs["discovery_center_excess"] = float(discovery["excess"])
        handle.attrs["discovery_excess_z"] = float(discovery["excess_z"])
        handle.attrs["dose_detected"] = bool(discovery["detected"])
        print("=" * 96)
        print(f"selected pump gain {int(discovery['pump_gain'])}")
        print(f"center pump effect {discovery['tls']:+.3f}")
        print(f"center excess {discovery['excess']:+.3f} "
              f"({discovery['excess_z']:+.2f} sigma, "
              f"sign fraction {discovery['sign_fraction']:.2f})")
        print(f"dose response {'DETECTED' if discovery['detected'] else 'NOT DETECTED'}")
        if bool(p["run_confirmation_if_detected"]) and discovery["detected"]:
            confirmation_schedule = stage_schedule(
                targets, [0.0], int(p["confirmation_repeats"]), "confirmation",
                selected_gain=int(discovery["pump_gain"]), p=p)
            create_stage(
                handle, "confirmation", confirmation_schedule, int(p["shots"]),
                int(p["reset_max_iters"]))
            handle.attrs["confirmation_stage_run"] = True
            handle.flush()
            run_stage(
                handle, "confirmation", confirmation_schedule, targets,
                soc, soccfg, cfg, p, outer_folder, park_ss.calib_params, assignment)
            confirmation = confirm_dose(handle["confirmation"], discovery, p)
            handle.attrs["confirmation_center_effect"] = float(confirmation["tls"])
            handle.attrs["confirmation_center_excess"] = float(confirmation["excess"])
            handle.attrs["confirmation_excess_z"] = float(confirmation["excess_z"])
            handle.attrs["dose_confirmed"] = bool(confirmation["confirmed"])
            print(f"confirmation center effect {confirmation['tls']:+.3f}")
            print(f"confirmation center excess {confirmation['excess']:+.3f} "
                  f"({confirmation['excess_z']:+.2f} sigma, "
                  f"sign fraction {confirmation['sign_fraction']:.2f})")
            print(f"dose response {'CONFIRMED' if confirmation['confirmed'] else 'NOT CONFIRMED'}")
            if bool(p["run_recovery_if_confirmed"]) and confirmation["confirmed"]:
                recovery_schedule = stage_schedule(
                    targets, recoveries, int(p["recovery_repeats"]),
                    "recovery_sweep", selected_gain=int(discovery["pump_gain"]), p=p)
                create_stage(
                    handle, "recovery_sweep", recovery_schedule, int(p["shots"]),
                    int(p["reset_max_iters"]))
                handle.attrs["recovery_stage_run"] = True
                handle.flush()
                run_stage(
                    handle, "recovery_sweep", recovery_schedule, targets,
                    soc, soccfg, cfg, p, outer_folder,
                    park_ss.calib_params, assignment)
            else:
                print("recovery sweep skipped; independent confirmation remains saved")
        else:
            print("confirmation skipped; complete dose scan remains saved")
        handle.attrs["completed"] = True
        handle.flush()
    save_csv(h5_path, csv_path, targets)
    save_plot(h5_path, plot_path, targets, discovery, confirmation)
    print("=" * 96)
    print(f"raw H5: {h5_path}")
    print(f"CSV:    {csv_path}")
    print(f"plot:   {plot_path}")
    print("=" * 96)
    return {
        "h5": h5_path, "csv": csv_path, "plot": plot_path,
        "discovery": discovery, "confirmation": confirmation,
    }


def main():
    with tee_log.tee(outerFolder, "TLSSaturationRecovery"):
        soc, soccfg = makeProxy()
        run(soc, soccfg)


if __name__ == "__main__":
    main()
