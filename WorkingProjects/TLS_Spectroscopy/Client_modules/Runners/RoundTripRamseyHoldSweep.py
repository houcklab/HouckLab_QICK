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

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig, outerFolder)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRoundTripRamsey import (
    RAMSEY_ARMS, RoundTripRamsey)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
    SingleShot1Q, discriminate_shots)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import tee_log
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as TLS


P = {
    "tls_nominal_freqs_ghz": [2.234178, 2.284178],
    "control_detuning_mhz": 5.0,
    "dc_search_max": 15000.0,
    "hold_dense_min_us": 0.0,
    "hold_dense_max_us": 5.0,
    "hold_dense_step_us": 0.1,
    "hold_long_us": [7.5, 10.0, 15.0, 20.0, 30.0, 40.0, 60.0],
    "repeats": 1,
    "order_seed": 20260731,
    "shots": 500,
    "rounds": 5,
    "park_cal_shots": 1000,
    "passive_reset_us": 1500.0,
    "min_assignment_contrast": 0.50,
    "min_local_reference_contrast": 0.10,
    "min_park_coherence": 0.35,
    "run_t1_checks": True,
    "t1_shots": 500,
    "t1_rounds": 5,
    "t1_Ts_us": 60.0,
    "t1_ref_hold_us": 1.0,
    "checkpoint_every": 5,
    "progress_every": 5,
}

CHANNEL_KEYS = (
    "P_g", "P_e", "P_i", "P_q", "reference_contrast",
    "local_reference_valid", "assignment_P_g", "assignment_P_e",
    "assignment_contrast", "population_g", "population_e", "ramsey_i",
    "ramsey_q", "coherence_magnitude", "coherence_phase_rad", "valid",
    "keep_fraction_g", "keep_fraction_e", "keep_fraction_i", "keep_fraction_q",
)

T1_KEYS = (
    "T1_3pt_us", "T1_3pt_valid_mask", "P0", "P1", "Ps",
    "ref_contrast_3pt",
)


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


def hold_times_us(p=P):
    start = float(p["hold_dense_min_us"])
    stop = float(p["hold_dense_max_us"])
    step = float(p["hold_dense_step_us"])
    if not np.isfinite([start, stop, step]).all() or start < 0.0 or stop < start or step <= 0.0:
        raise ValueError("hold sweep bounds must be finite with 0 <= min <= max and step > 0")
    count = int(np.floor((stop - start) / step + 0.5))
    dense = start + step * np.arange(count + 1, dtype=float)
    dense = dense[dense <= stop + 1e-9]
    long_values = np.asarray(p.get("hold_long_us", []), dtype=float)
    if np.any(~np.isfinite(long_values)) or np.any(long_values < 0.0):
        raise ValueError("hold_long_us must contain finite non-negative values")
    return np.unique(np.round(np.concatenate((dense, long_values)), 9))


def target_table(p=P, flux_fit_params=None, base_config=BaseConfig):
    params = TLS.FLUX_FIT_PARAMS if flux_fit_params is None else flux_fit_params
    if params is None:
        raise RuntimeError("FLUX_FIT_PARAMS is required")
    tls_freqs = np.asarray(p["tls_nominal_freqs_ghz"], dtype=float)
    detuning = float(p["control_detuning_mhz"])
    if tls_freqs.size == 0 or np.any(~np.isfinite(tls_freqs)) or detuning <= 0.0:
        raise ValueError("TLS frequencies must be finite and control_detuning_mhz must be positive")
    search_max = float(p["dc_search_max"])
    f_edges = fx.estimate_fit_frequency_ghz_array(params, np.asarray([0.0, search_max]))
    f_min, f_max = float(np.min(f_edges)), float(np.max(f_edges))
    fit_park = fx.estimate_fit_frequency_ghz(params, 0.0)
    park_ghz = float(base_config["qubit_pi_freq"]) / 1e3
    anchor_shift = park_ghz - fit_park
    result = []
    for tls_index, center in enumerate(tls_freqs):
        for role, offset_mhz in (("minus", -detuning), ("tls", 0.0),
                                 ("plus", detuning)):
            requested = float(center + offset_mhz / 1e3)
            if requested < f_min or requested > f_max:
                raise ValueError(
                    f"target {requested:.9f} GHz is outside the fitted branch "
                    f"{f_min:.9f}..{f_max:.9f} GHz")
            dc = float(fx.frequency_to_local_flux_branch(
                params, np.asarray([requested]), 0.0, search_max)[0])
            predicted = fx.estimate_fit_frequency_ghz(params, dc)
            if abs(predicted - requested) > 1e-6:
                raise RuntimeError(
                    f"could not invert {requested:.9f} GHz on the selected flux branch")
            result.append({
                "target_index": len(result),
                "tls_index": int(tls_index),
                "role": role,
                "label": f"tls_{tls_index + 1}_{role}",
                "detuning_mhz": float(offset_mhz),
                "nominal_freq_ghz": requested,
                "park_anchored_freq_ghz": requested + anchor_shift,
                "dc_gain": dc,
            })
    return result, fit_park, anchor_shift


def point_schedule(targets, holds, p=P):
    repeats = int(p["repeats"])
    if repeats <= 0:
        raise ValueError("repeats must be positive")
    grid = []
    for repeat in range(repeats):
        for target in targets:
            for hold in holds:
                grid.append({
                    "grid_index": len(grid),
                    "repeat": repeat,
                    "target_index": int(target["target_index"]),
                    "hold_us": float(hold),
                })
    rng = np.random.default_rng(int(p["order_seed"]))
    order = rng.permutation(len(grid))
    return [{**grid[int(index)], "visit": visit}
            for visit, index in enumerate(order)]


def base_cfg(p, flux_tail, target_dcs):
    cfg = dict(BaseConfig)
    cfg.update({
        "reset_mode": "passive",
        "relax_delay": float(p["passive_reset_us"]),
        "shots": int(p["shots"]),
        "reps": int(p["shots"]),
        "ff_gain_vec": np.asarray(target_dcs, dtype=float),
        "flux_tail_compensation": flux_tail,
        "flux_fit_params": TLS.FLUX_FIT_PARAMS,
        "randomize_point_order": True,
        "point_order_seed": int(p["order_seed"]),
    })
    return cfg


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
        suffix="RoundTripHoldSweep_SS_Park", cfg=cfg, repeats=1,
        confidence_threshold=0.0)
    ss.acquire(progress=False, plotDisp=False)
    assignment = {
        "P_g": float(np.mean(discriminate_shots(
            ss.I_0, ss.Q_0, ss.calib_params))),
        "P_e": float(np.mean(discriminate_shots(
            ss.I_1, ss.Q_1, ss.calib_params))),
    }
    assignment["contrast"] = assignment["P_e"] - assignment["P_g"]
    if assignment["contrast"] < float(p["min_assignment_contrast"]):
        raise RuntimeError(
            f"park assignment contrast {assignment['contrast']:.3f} is below "
            f"{float(p['min_assignment_contrast']):.3f}")
    plt.close("all")
    return ss, assignment, time.time() - started


def run_channel(soc, soccfg, cfg, p, outer_folder, dc_gain, hold_us,
                calib_params, assignment):
    started = time.time()
    exp = RoundTripRamsey(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outer_folder,
        suffix="RoundTripHoldSweep_Point", cfg=dict(cfg),
        ff_gain=float(dc_gain), flux_hold_us=float(hold_us),
        shots=int(p["shots"]), rounds=int(p["rounds"]),
        calib_params=calib_params, assignment_reference=assignment,
        min_reference_contrast=float(p["min_local_reference_contrast"]),
        save=False)
    exp.acquire(progress=False, plotDisp=False)
    return exp, time.time() - started


def run_t1_check(soc, soccfg, cfg, p, outer_folder, targets, calib_params,
                 stage_index):
    dc_vec = np.asarray([target["dc_gain"] for target in targets], dtype=float)
    t1_cfg = dict(cfg)
    t1_cfg.update({
        "shots": int(p["t1_shots"]),
        "reps": int(p["t1_shots"]),
        "interleave_rounds": int(p["t1_rounds"]),
        "randomize_point_order": True,
        "point_order_seed": int(p["order_seed"]) + 1000 + int(stage_index),
        "three_point_ref_hold_us": float(p["t1_ref_hold_us"]),
        "ff_gain_vec": dc_vec,
    })
    started = time.time()
    exp = TLS.T13PointVsFlux(
        soc=soc, soccfg=soccfg, path=TLS.QUBIT, outerFolder=outer_folder,
        suffix=f"RoundTripHoldSweep_T1_{stage_index}", cfg=t1_cfg,
        dc_vec=dc_vec, Ts_ns=int(round(float(p["t1_Ts_us"]) * 1e3)),
        shots=int(p["t1_shots"]), calib_params=calib_params,
        park_voltage=TLS.BASELINE_DC_OFFSET,
        min_ref_contrast=float(p["min_local_reference_contrast"]),
        max_plot_t1_multiple=20.0, reset_mode="passive",
        flux_tail_compensation=cfg.get("flux_tail_compensation"),
        repeat_metadata=None, write_outputs=False)
    exp.acquire(progress=False)
    result = {key: np.asarray(exp.data[key], dtype=float) for key in T1_KEYS}
    result["Ts_effective_ns"] = float(
        exp.data.get("Ts_effective_ns", float(p["t1_Ts_us"]) * 1e3))
    result["elapsed_s"] = time.time() - started
    plt.close("all")
    return result


def create_h5(path, p, cfg, targets, holds, schedule, park_ss, assignment,
              park_channel, park_elapsed, park_cal_elapsed, fit_park,
              anchor_shift, t1_start):
    string = h5py.string_dtype(encoding="utf-8")
    shots = int(p["shots"])
    n = len(schedule)
    with h5py.File(path, "w") as handle:
        handle.attrs["schema"] = "round_trip_ramsey_hold_sweep_v1"
        handle.attrs["settings"] = json.dumps(p, default=json_default)
        handle.attrs["base_config"] = json.dumps(cfg, default=json_default)
        handle.attrs["flux_fit_params"] = json.dumps(
            TLS.FLUX_FIT_PARAMS, default=json_default)
        handle.attrs["fit_park_freq_ghz"] = float(fit_park)
        handle.attrs["configured_park_freq_ghz"] = float(BaseConfig["qubit_pi_freq"]) / 1e3
        handle.attrs["park_anchor_shift_ghz"] = float(anchor_shift)
        handle.attrs["interrupted"] = False
        handle.attrs["completed_points"] = 0
        handle.attrs["total_points"] = n
        park = handle.create_group("park_cal")
        for key in ("I_0", "Q_0", "I_1", "Q_1"):
            park.create_dataset(key, data=np.asarray(getattr(park_ss, key), dtype=float))
        park.attrs["calib_params"] = json.dumps(park_ss.calib_params, default=json_default)
        park.attrs["fidelity"] = float(park_ss.max_F)
        park.attrs["assignment_reference"] = json.dumps(assignment)
        park.attrs["elapsed_s"] = float(park_cal_elapsed)
        reference = handle.create_group("park_channel_reference")
        for arm in RAMSEY_ARMS:
            for source, label in (("herald_i", "herald_I"),
                                  ("herald_q", "herald_Q"),
                                  ("i", "I"), ("q", "Q")):
                reference.create_dataset(
                    f"{label}_{arm}",
                    data=np.asarray(park_channel.raw[arm][source], dtype=float))
        reference.attrs["metrics"] = json.dumps(
            park_channel.metrics, default=json_default)
        reference.attrs["elapsed_s"] = float(park_elapsed)
        tg = handle.create_group("targets")
        tg.create_dataset("label", data=np.asarray([x["label"] for x in targets], dtype=object),
                          dtype=string)
        tg.create_dataset("role", data=np.asarray([x["role"] for x in targets], dtype=object),
                          dtype=string)
        for key in ("target_index", "tls_index", "detuning_mhz",
                    "nominal_freq_ghz", "park_anchored_freq_ghz", "dc_gain"):
            tg.create_dataset(key, data=np.asarray([x[key] for x in targets]))
        handle.create_dataset("hold_times_us", data=np.asarray(holds, dtype=float))
        sg = handle.create_group("schedule")
        for key in ("visit", "grid_index", "repeat", "target_index", "hold_us"):
            sg.create_dataset(key, data=np.asarray([x[key] for x in schedule]))
        channel = handle.create_group("channel")
        channel.create_dataset("completed", shape=(n,), dtype=np.int8, fillvalue=0)
        channel.create_dataset("error", shape=(n,), dtype=string)
        channel.create_dataset("elapsed_s", shape=(n,), dtype=float, fillvalue=np.nan)
        channel.create_dataset("acquired_unix_s", shape=(n,), dtype=float, fillvalue=np.nan)
        for key in CHANNEL_KEYS:
            channel.create_dataset(key, shape=(n,), dtype=float, fillvalue=np.nan)
        for key in ("coherence_relative_to_park", "coherence_phase_relative_rad"):
            channel.create_dataset(key, shape=(n,), dtype=float, fillvalue=np.nan)
        for arm in RAMSEY_ARMS:
            for prefix in ("herald_I", "herald_Q", "I", "Q"):
                channel.create_dataset(
                    f"{prefix}_{arm}", shape=(n, shots), dtype=float,
                    fillvalue=np.nan, chunks=(1, shots), compression="gzip",
                    compression_opts=1)
        if t1_start is not None:
            save_t1_group(handle, "start", t1_start)
        handle.flush()


def save_t1_group(handle, stage, result):
    root = handle.require_group("t1_checks")
    if stage in root:
        del root[stage]
    group = root.create_group(stage)
    for key in T1_KEYS:
        group.create_dataset(key, data=np.asarray(result[key], dtype=float))
    group.attrs["Ts_effective_ns"] = float(result["Ts_effective_ns"])
    group.attrs["elapsed_s"] = float(result["elapsed_s"])


def write_channel_point(handle, visit, exp, elapsed, park_metrics):
    channel = handle["channel"]
    for key in CHANNEL_KEYS:
        channel[key][visit] = float(exp.metrics[key])
    park_c = float(park_metrics["coherence_magnitude"])
    park_phase = float(park_metrics["coherence_phase_rad"])
    channel["coherence_relative_to_park"][visit] = (
        float(exp.metrics["coherence_magnitude"]) / park_c)
    channel["coherence_phase_relative_rad"][visit] = float(np.angle(np.exp(
        1j * (float(exp.metrics["coherence_phase_rad"]) - park_phase))))
    for arm in RAMSEY_ARMS:
        values = exp.raw[arm]
        channel[f"herald_I_{arm}"][visit] = values["herald_i"]
        channel[f"herald_Q_{arm}"][visit] = values["herald_q"]
        channel[f"I_{arm}"][visit] = values["i"]
        channel[f"Q_{arm}"][visit] = values["q"]
    channel["elapsed_s"][visit] = float(elapsed)
    channel["acquired_unix_s"][visit] = time.time()
    channel["completed"][visit] = 1


def save_csv(h5_path, csv_path):
    with h5py.File(h5_path, "r") as handle, open(csv_path, "w", newline="") as output:
        fields = [
            "visit", "grid_index", "repeat", "target_index", "tls_index", "role",
            "label", "detuning_mhz", "nominal_freq_ghz",
            "park_anchored_freq_ghz", "dc_gain", "hold_us", "completed", "error",
            "elapsed_s", "acquired_unix_s",
        ] + list(CHANNEL_KEYS) + [
            "coherence_relative_to_park", "coherence_phase_relative_rad"
        ]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        targets = handle["targets"]
        schedule = handle["schedule"]
        channel = handle["channel"]
        for visit in range(len(schedule["visit"])):
            target_index = int(schedule["target_index"][visit])
            row = {
                key: schedule[key][visit].item()
                for key in ("visit", "grid_index", "repeat", "target_index", "hold_us")
            }
            row.update({
                "tls_index": int(targets["tls_index"][target_index]),
                "role": targets["role"][target_index].decode(),
                "label": targets["label"][target_index].decode(),
                "detuning_mhz": float(targets["detuning_mhz"][target_index]),
                "nominal_freq_ghz": float(targets["nominal_freq_ghz"][target_index]),
                "park_anchored_freq_ghz": float(
                    targets["park_anchored_freq_ghz"][target_index]),
                "dc_gain": float(targets["dc_gain"][target_index]),
                "completed": int(channel["completed"][visit]),
                "error": channel["error"][visit].decode(),
                "elapsed_s": float(channel["elapsed_s"][visit]),
                "acquired_unix_s": float(channel["acquired_unix_s"][visit]),
            })
            for key in CHANNEL_KEYS + (
                    "coherence_relative_to_park", "coherence_phase_relative_rad"):
                row[key] = float(channel[key][visit])
            writer.writerow(row)


def save_t1_csv(h5_path, csv_path):
    with h5py.File(h5_path, "r") as handle, open(csv_path, "w", newline="") as output:
        fields = [
            "stage", "target_index", "tls_index", "role", "label",
            "detuning_mhz", "nominal_freq_ghz", "park_anchored_freq_ghz",
            "dc_gain",
        ] + list(T1_KEYS)
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        if "t1_checks" not in handle:
            return
        targets = handle["targets"]
        for stage in ("start", "end"):
            if stage not in handle["t1_checks"]:
                continue
            group = handle[f"t1_checks/{stage}"]
            for index in range(len(targets["target_index"])):
                row = {
                    "stage": stage,
                    "target_index": index,
                    "tls_index": int(targets["tls_index"][index]),
                    "role": targets["role"][index].decode(),
                    "label": targets["label"][index].decode(),
                    "detuning_mhz": float(targets["detuning_mhz"][index]),
                    "nominal_freq_ghz": float(targets["nominal_freq_ghz"][index]),
                    "park_anchored_freq_ghz": float(
                        targets["park_anchored_freq_ghz"][index]),
                    "dc_gain": float(targets["dc_gain"][index]),
                }
                for key in T1_KEYS:
                    row[key] = float(group[key][index])
                writer.writerow(row)


def save_plot(h5_path, plot_path):
    with h5py.File(h5_path, "r") as handle:
        targets = handle["targets"]
        schedule = handle["schedule"]
        channel = handle["channel"]
        completed = np.asarray(channel["completed"], dtype=bool)
        tls_indices = np.asarray(targets["tls_index"], dtype=int)
        n_tls = int(np.max(tls_indices)) + 1
        fig, axes = plt.subplots(2, n_tls, figsize=(7 * n_tls, 9),
                                 squeeze=False, constrained_layout=True)
        colors = {"minus": "#2563eb", "tls": "#dc2626", "plus": "#16a34a"}
        for tls_index in range(n_tls):
            for target_index in np.where(tls_indices == tls_index)[0]:
                role = targets["role"][target_index].decode()
                nominal = float(targets["nominal_freq_ghz"][target_index])
                mask = completed & (np.asarray(schedule["target_index"]) == target_index)
                if not np.any(mask):
                    continue
                hold = np.asarray(schedule["hold_us"])[mask]
                order = np.argsort(hold)
                hold = hold[order]
                coherence = np.asarray(channel["coherence_relative_to_park"])[mask][order]
                phase = np.asarray(channel["coherence_phase_relative_rad"])[mask][order]
                label = f"{role} {nominal:.6f} GHz"
                axes[0, tls_index].plot(
                    hold, coherence, ".-", lw=0.9, ms=4,
                    color=colors[role], label=label)
                axes[1, tls_index].plot(
                    hold, np.unwrap(phase), ".-", lw=0.9, ms=4,
                    color=colors[role], label=label)
            center = float(targets["nominal_freq_ghz"][np.where(
                (tls_indices == tls_index)
                & (np.asarray(targets["detuning_mhz"]) == 0.0))[0][0]])
            axes[0, tls_index].set(
                title=f"TLS {tls_index + 1}: nominal {center:.6f} GHz",
                ylabel="|C| / |C park|")
            axes[1, tls_index].set(
                xlabel="Target hold [us]", ylabel="Unwrapped phase from park [rad]")
            for ax in axes[:, tls_index]:
                ax.axhline(0.0 if ax is axes[1, tls_index] else 1.0,
                           color="black", lw=0.7, alpha=0.5)
                ax.grid(True, alpha=0.2)
                ax.legend(fontsize=8)
        fig.suptitle("Targeted round-trip Ramsey hold sweep")
        fig.savefig(plot_path, dpi=180, bbox_inches="tight")
        plt.close(fig)


def output_base(outer_folder):
    now = datetime.datetime.now()
    folder = os.path.join(outer_folder, TLS.QUBIT, f"{TLS.QUBIT}_{now:%Y_%m_%d}")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(
        folder, f"{TLS.QUBIT}_{now:%H_%M_%S}_RoundTripRamseyHoldSweep")


def run(soc, soccfg, outer_folder=outerFolder, settings=None):
    p = dict(P if settings is None else settings)
    holds = hold_times_us(p)
    targets, fit_park, anchor_shift = target_table(p)
    schedule = point_schedule(targets, holds, p)
    target_dcs = [target["dc_gain"] for target in targets]
    flux_tail = TLS._load_correction(None, outer_folder)
    cfg = base_cfg(p, flux_tail, target_dcs)
    base_path = output_base(outer_folder)
    h5_path = f"{base_path}_raw.h5"
    csv_path = f"{base_path}.csv"
    t1_csv_path = f"{base_path}_T1_checks.csv"
    plot_path = f"{base_path}.png"
    n = len(schedule)
    passive_floor = n * 4 * int(p["shots"]) * float(p["passive_reset_us"]) * 1e-6
    if p.get("run_t1_checks"):
        passive_floor += 2 * len(targets) * 3 * int(p["t1_shots"]) * float(
            p["passive_reset_us"]) * 1e-6
    print("=" * 96)
    print("TARGETED ROUND-TRIP RAMSEY HOLD SWEEP")
    print(f"{len(targets)} frequencies x {len(holds)} holds x {int(p['repeats'])} repeats "
          f"= {n} finite channel points")
    print(f"passive reset {float(p['passive_reset_us']):g} us, "
          f"{int(p['shots'])} shots per arm, randomized seed {int(p['order_seed'])}")
    print(f"pulse-time lower bound {hms(passive_floor)}; live ETA includes hardware overhead")
    print(f"checkpoint H5: {h5_path}")
    print(f"fit park {fit_park:.9f} GHz, configured park "
          f"{float(BaseConfig['qubit_pi_freq']) / 1e3:.9f} GHz, "
          f"saved anchor shift {anchor_shift * 1e3:+.3f} MHz")
    for target in targets:
        print(f"{target['label']:<12} nominal {target['nominal_freq_ghz']:.6f} GHz  "
              f"dc {target['dc_gain']:.3f}  "
              f"park-anchored {target['park_anchored_freq_ghz']:.6f} GHz")
    print("=" * 96)
    park_ss, assignment, park_cal_elapsed = run_park_calibration(
        soc, soccfg, p, outer_folder)
    print(f"park SS fidelity {park_ss.max_F:.3f}, assignment contrast "
          f"{assignment['contrast']:.3f}, {hms(park_cal_elapsed)}")
    park_channel, park_elapsed = run_channel(
        soc, soccfg, cfg, p, outer_folder, TLS.BASELINE_DC_OFFSET, 0.0,
        park_ss.calib_params, assignment)
    park_metrics = park_channel.metrics
    print(f"park channel P_g={park_metrics['P_g']:.3f}, "
          f"P_e={park_metrics['P_e']:.3f}, "
          f"|C|={park_metrics['coherence_magnitude']:.3f}, "
          f"contrast={park_metrics['reference_contrast']:.3f}, {hms(park_elapsed)}")
    if not park_metrics["valid"]:
        raise RuntimeError("park assignment reference is invalid")
    if not park_metrics["local_reference_valid"]:
        raise RuntimeError("park channel reference contrast is invalid")
    if float(park_metrics["coherence_magnitude"]) < float(p["min_park_coherence"]):
        raise RuntimeError(
            f"park coherence {park_metrics['coherence_magnitude']:.3f} is below "
            f"{float(p['min_park_coherence']):.3f}")
    t1_start = None
    if p.get("run_t1_checks"):
        print("running randomized start T1 check")
        t1_start = run_t1_check(
            soc, soccfg, cfg, p, outer_folder, targets, park_ss.calib_params, 0)
        print(f"start T1 check complete in {hms(t1_start['elapsed_s'])}")
    create_h5(
        h5_path, p, cfg, targets, holds, schedule, park_ss, assignment,
        park_channel, park_elapsed, park_cal_elapsed, fit_park, anchor_shift,
        t1_start)
    started = time.time()
    interrupted = False
    completed = 0
    with h5py.File(h5_path, "r+") as handle:
        for item in schedule:
            visit = int(item["visit"])
            target = targets[int(item["target_index"])]
            try:
                exp, elapsed = run_channel(
                    soc, soccfg, cfg, p, outer_folder, target["dc_gain"],
                    item["hold_us"], park_ss.calib_params, assignment)
                write_channel_point(handle, visit, exp, elapsed, park_metrics)
                completed += 1
            except KeyboardInterrupt:
                interrupted = True
                print("interrupt received; preserving completed points")
                break
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                handle["channel/error"][visit] = message
                print(f"point {visit + 1}/{n} failed: {message}")
            handle.attrs["completed_points"] = completed
            if ((visit + 1) % int(p["checkpoint_every"]) == 0
                    or completed == n):
                handle.flush()
            if ((visit + 1) % int(p["progress_every"]) == 0
                    or visit + 1 == n):
                elapsed_total = time.time() - started
                eta = elapsed_total / max(visit + 1, 1) * (n - visit - 1)
                coherence = handle["channel/coherence_magnitude"][visit]
                phase = handle["channel/coherence_phase_relative_rad"][visit]
                print(f"{visit + 1:>4}/{n}  {target['label']:<12}  "
                      f"hold {float(item['hold_us']):>5.1f} us  "
                      f"|C| {coherence:.3f}  phase {phase:+.2f}  "
                      f"[{hms(elapsed_total)} elapsed, ETA {hms(eta)}]", flush=True)
            if visit % 50 == 0:
                gc.collect()
        handle.attrs["interrupted"] = bool(interrupted)
        handle.attrs["completed_points"] = completed
        handle.attrs["channel_elapsed_s"] = float(time.time() - started)
        if p.get("run_t1_checks") and not interrupted:
            print("running randomized end T1 check")
            t1_end = run_t1_check(
                soc, soccfg, cfg, p, outer_folder, targets,
                park_ss.calib_params, 1)
            save_t1_group(handle, "end", t1_end)
            print(f"end T1 check complete in {hms(t1_end['elapsed_s'])}")
        handle.flush()
    save_csv(h5_path, csv_path)
    save_t1_csv(h5_path, t1_csv_path)
    save_plot(h5_path, plot_path)
    print(f"CSV: {csv_path}")
    print(f"T1 CSV: {t1_csv_path}")
    print(f"raw H5: {h5_path}")
    print(f"overview: {plot_path}")
    print(f"completed {completed}/{n} channel points in {hms(time.time() - started)}")
    return {
        "csv": csv_path,
        "t1_csv": t1_csv_path,
        "h5": h5_path,
        "plot": plot_path,
        "completed": completed,
        "total": n,
        "interrupted": interrupted,
    }


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with tee_log.tee(f"RoundTripRamseyHoldSweep_{stamp}", outerFolder):
        soc, soccfg = makeProxy()
        run(soc, soccfg)


if __name__ == "__main__":
    main()
