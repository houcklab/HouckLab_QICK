import csv
from datetime import datetime
import json
from pathlib import Path
import pickle
import sys

import numpy as np


_source = Path(__file__).resolve()
for _parent in _source.parents:
    if (_parent / "WorkingProjects").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.ss_helpers import (
    find_blob_median,
    find_threshold,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    json_safe,
)
QUBIT = "q3"
CHEVRON_SIGMA_US = 0.2
PASSIVE_RESET_US = 1000.0
GRID_SHOTS = 200
VALIDATION_SHOTS = 1000
QUBIT_FREQ_HALF_SPAN_MHZ = 2.0
QUBIT_FREQ_POINTS = 9
QUBIT_GAIN_POINTS = 13
READOUT_FREQ_HALF_SPAN_MHZ = 0.8
READOUT_FREQ_POINTS = 9
READOUT_GAIN_POINTS = 5


def _axis_with_center(low, high, center, points):
    low = int(low)
    high = int(high)
    center = int(center)
    points = int(points)
    if points < 2 or low < 1 or high > 32767 or not low <= center <= high:
        raise ValueError("invalid DAC axis")
    axis = np.rint(np.linspace(low, high, points)).astype(int)
    axis[int(np.argmin(np.abs(axis - center)))] = center
    values = set(int(value) for value in axis)
    if len(values) < points:
        for value in range(low, high + 1):
            values.add(value)
            if len(values) == points:
                break
    return np.asarray(sorted(values), dtype=int)


def build_gain_axis(center_gain, points=13):
    center = int(round(center_gain))
    if center < 1 or center > 32767:
        raise ValueError("center gain must be between 1 and 32767 DAC")
    low = max(1, int(round(0.25 * center)))
    high = min(32767, max(center + int(points) - 1, int(round(2.0 * center))))
    return _axis_with_center(low, high, center, points)


def _readout_gain_axis(center_gain, points=5):
    center = int(round(center_gain))
    if center < 1 or center > 32767:
        raise ValueError("readout gain must be between 1 and 32767 DAC")
    low = max(1, int(round(0.5 * center)))
    high = min(32767, max(center + int(points) - 1, int(round(1.5 * center))))
    return _axis_with_center(low, high, center, points)


def pair_metrics(ground_i, ground_q, excited_i, excited_q):
    ground = np.asarray(ground_i, dtype=float).reshape(-1) + 1j * np.asarray(
        ground_q, dtype=float
    ).reshape(-1)
    excited = np.asarray(excited_i, dtype=float).reshape(-1) + 1j * np.asarray(
        excited_q, dtype=float
    ).reshape(-1)
    ground = ground[np.isfinite(ground.real) & np.isfinite(ground.imag)]
    excited = excited[np.isfinite(excited.real) & np.isfinite(excited.imag)]
    if ground.size == 0 or excited.size == 0 or ground.size != excited.size:
        raise ValueError("ground and excited clouds need equal nonzero finite samples")
    ground_center = find_blob_median(ground)
    excited_center = find_blob_median(excited)
    delta = excited_center - ground_center
    theta = float(np.angle(delta)) if abs(delta) > 0 else 0.0
    ground_projection = np.real(np.exp(-1j * theta) * ground)
    excited_projection = np.real(np.exp(-1j * theta) * excited)
    thresholds, fidelities = find_threshold(ground_projection, excited_projection)
    index = int(np.nanargmax(fidelities))
    ground_width = float(np.std(ground_projection, ddof=1)) if ground.size > 1 else 0.0
    excited_width = float(np.std(excited_projection, ddof=1)) if excited.size > 1 else 0.0
    pooled_width = float(np.sqrt(0.5 * (ground_width ** 2 + excited_width ** 2)))
    center_distance = float(abs(delta))
    separation_sigma = center_distance / pooled_width if pooled_width > 0 else float("inf")
    return {
        "fidelity": float(fidelities[index]),
        "threshold": float(thresholds[index]),
        "theta_rad": theta,
        "ground_center_i": float(ground_center.real),
        "ground_center_q": float(ground_center.imag),
        "excited_center_i": float(excited_center.real),
        "excited_center_q": float(excited_center.imag),
        "center_distance": center_distance,
        "ground_width": ground_width,
        "excited_width": excited_width,
        "separation_sigma": float(separation_sigma),
        "shots_per_state": int(ground.size),
    }


def select_grid_best(frequencies_mhz, gains, fidelity):
    frequencies = np.asarray(frequencies_mhz, dtype=float).reshape(-1)
    gains = np.asarray(gains, dtype=int).reshape(-1)
    values = np.asarray(fidelity, dtype=float)
    expected = (gains.size, frequencies.size)
    if values.shape != expected:
        raise ValueError(f"fidelity grid shape {values.shape} does not match {expected}")
    gain_index, frequency_index = np.unravel_index(np.nanargmax(values), values.shape)
    return {
        "frequency_mhz": float(frequencies[frequency_index]),
        "gain_dac": int(gains[gain_index]),
        "fidelity": float(values[gain_index, frequency_index]),
    }


def classify_result(
    *,
    ground_drift_fidelity,
    current_fidelity,
    chevron_sigma_fidelity,
    qubit_grid_fidelity,
    readout_grid_fidelity,
    final_ge_fidelity,
    final_eg_fidelity,
    chevron_exact_fidelity=None,
):
    ground_drift_fidelity = float(ground_drift_fidelity)
    current_fidelity = float(current_fidelity)
    chevron_sigma_fidelity = float(chevron_sigma_fidelity)
    qubit_grid_fidelity = float(qubit_grid_fidelity)
    readout_grid_fidelity = float(readout_grid_fidelity)
    final_ge_fidelity = float(final_ge_fidelity)
    final_eg_fidelity = float(final_eg_fidelity)
    chevron_exact_fidelity = (
        chevron_sigma_fidelity
        if chevron_exact_fidelity is None
        else float(chevron_exact_fidelity)
    )
    if ground_drift_fidelity >= 0.62 or abs(final_ge_fidelity - final_eg_fidelity) >= 0.15:
        return "state_order_or_slow_drift"
    if min(final_ge_fidelity, final_eg_fidelity) >= 0.75:
        if current_fidelity >= 0.75:
            return "original_failure_not_reproduced"
        if chevron_sigma_fidelity >= 0.75:
            return "pulse_sigma_mismatch"
        if chevron_exact_fidelity >= 0.75 or qubit_grid_fidelity >= 0.75:
            return "qubit_frequency_or_gain_mismatch"
        if readout_grid_fidelity >= 0.75:
            return "readout_frequency_or_gain_mismatch"
        return "combined_qubit_and_readout_mismatch"
    return "no_resolved_qubit_state_separation"


def should_run_optimizer(*, chevron_exact_fidelity, ground_drift_fidelity):
    return bool(
        float(chevron_exact_fidelity) < 0.75
        or float(ground_drift_fidelity) >= 0.62
    )


def _make_output_dir(outer_folder):
    now = datetime.now()
    output = (
        Path(outer_folder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_SSCal_failure_diagnostic"
    )
    output.mkdir(parents=True, exist_ok=False)
    return output


def _latest_chevron(outer_folder):
    root = Path(outer_folder) / QUBIT
    paths = list(root.glob(f"{QUBIT}_*/{QUBIT}_*_Rabi_Chevron_IQ.pkl"))
    if not paths:
        return None
    path = max(paths, key=lambda candidate: candidate.stat().st_mtime)
    with path.open("rb") as handle:
        data = pickle.load(handle)
    config = dict(data.get("config", {}))
    return {
        "path": str(path),
        "frequency_mhz": float(data["best_drive_freq_mhz"]),
        "gain_dac": int(round(data["best_gain"])),
        "sigma_us": float(config.get("sigma", CHEVRON_SIGMA_US)),
    }


def _passive_config(base_config):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import ProductionResetSession

    values = dict(base_config)
    values.update({
        "shots": int(VALIDATION_SHOTS),
        "reps": int(VALIDATION_SHOTS),
        "relax_delay": float(PASSIVE_RESET_US),
        "ff_gain": 0,
        "ff_hold_gain": 0,
        "readout_after_park": True,
        "qubit_pulse_style": "arb",
    })
    cfg = ProductionResetSession.passive().apply(values)
    cfg["relax_delay"] = float(PASSIVE_RESET_US)
    cfg["opx_inter_shot_delay_us"] = float(PASSIVE_RESET_US)
    return cfg


def _pair_config(cfg, frequency_mhz, gain_dac, sigma_us, state_order, shots):
    values = dict(cfg)
    values.update({
        "shots": int(shots),
        "reps": int(shots),
        "qubit_freq": float(frequency_mhz),
        "qubit_pi_freq": float(frequency_mhz),
        "qubit_gain": int(gain_dac),
        "qubit_pi_gain": int(gain_dac),
        "qubit_pi2_gain": int(round(int(gain_dac) / 2.0)),
        "sigma": float(sigma_us),
        "single_shot_state_order": str(state_order),
        "reset_mode": "passive",
    })
    return values


def _acquire_pair(soc, soccfg, cfg, frequency_mhz, gain_dac, sigma_us, repeats, state_order, shots, outer_folder):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout

    run_cfg = _pair_config(
        cfg,
        frequency_mhz,
        gain_dac,
        sigma_us,
        state_order,
        shots,
    )
    experiment = SingleShot1Q(
        soc=soc,
        soccfg=soccfg,
        path=QUBIT,
        outerFolder=outer_folder,
        suffix="SSCal_failure_diagnostic_point",
        cfg=run_cfg,
        plot=False,
        save=False,
        repeats=int(repeats),
        min_F=0.0,
    )
    with suppress_stdout():
        experiment.acquire(progress=False, plotDisp=False)
    raw = {
        "ground_i": np.asarray(experiment.I_0, dtype=float),
        "ground_q": np.asarray(experiment.Q_0, dtype=float),
        "excited_i": np.asarray(experiment.I_1, dtype=float),
        "excited_q": np.asarray(experiment.Q_1, dtype=float),
    }
    return raw, pair_metrics(
        raw["ground_i"],
        raw["ground_q"],
        raw["excited_i"],
        raw["excited_q"],
    )


def _grid_metrics(i_values, q_values):
    i_values = np.asarray(i_values, dtype=float)
    q_values = np.asarray(q_values, dtype=float)
    if i_values.shape != q_values.shape or i_values.ndim != 4 or i_values.shape[-1] != 2:
        raise ValueError("optimizer IQ arrays must have shape [shot, frequency, gain, state]")
    fidelity = np.empty((i_values.shape[2], i_values.shape[1]), dtype=float)
    separation = np.empty_like(fidelity)
    for frequency_index in range(i_values.shape[1]):
        for gain_index in range(i_values.shape[2]):
            metrics = pair_metrics(
                i_values[:, frequency_index, gain_index, 0],
                q_values[:, frequency_index, gain_index, 0],
                i_values[:, frequency_index, gain_index, 1],
                q_values[:, frequency_index, gain_index, 1],
            )
            fidelity[gain_index, frequency_index] = metrics["fidelity"]
            separation[gain_index, frequency_index] = metrics["separation_sigma"]
    return fidelity, separation


def _acquire_grid(soc, soccfg, cfg, frequencies, gains, kind, drive_gain):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order import acquire_passive_optimizer_grid

    i_values, q_values, telemetry = acquire_passive_optimizer_grid(
        soc,
        soccfg,
        {**cfg, "shots": int(GRID_SHOTS), "reps": int(GRID_SHOTS)},
        frequencies_mhz=frequencies,
        gains=gains,
        kind=kind,
        drive_pulses=1,
        drive_gain=int(drive_gain),
        progress=lambda done, total: None,
    )
    fidelity, separation = _grid_metrics(i_values, q_values)
    return i_values, q_values, fidelity, separation, telemetry


def _write_grid(path, frequencies, gains, fidelity, separation):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("frequency_mhz", "gain_dac", "fidelity", "separation_sigma"),
        )
        writer.writeheader()
        for gain_index, gain in enumerate(gains):
            for frequency_index, frequency in enumerate(frequencies):
                writer.writerow({
                    "frequency_mhz": float(frequency),
                    "gain_dac": int(gain),
                    "fidelity": float(fidelity[gain_index, frequency_index]),
                    "separation_sigma": float(separation[gain_index, frequency_index]),
                })


def _save_raw(path, groups):
    arrays = {}
    for group, values in groups.items():
        for key, value in values.items():
            arrays[f"{group}_{key}"] = np.asarray(value)
    np.savez_compressed(path, **arrays)


def _plot(path, qubit_scan, readout_scan, final_raw, pulse_counts, diagnosis):
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    if qubit_scan["fidelity"].size == 1:
        qpcm = axes[0, 0].scatter(
            qubit_scan["frequencies"],
            qubit_scan["gains"],
            c=100.0 * qubit_scan["fidelity"].reshape(-1),
            vmin=50.0,
            vmax=100.0,
            s=120,
        )
    else:
        qpcm = axes[0, 0].pcolormesh(
            qubit_scan["frequencies"],
            qubit_scan["gains"],
            100.0 * qubit_scan["fidelity"],
            shading="nearest",
        )
    fig.colorbar(qpcm, ax=axes[0, 0], label="Fidelity [%]")
    axes[0, 0].plot(
        qubit_scan["selected"]["frequency_mhz"],
        qubit_scan["selected"]["gain_dac"],
        "wx",
        ms=10,
        mew=2,
    )
    axes[0, 0].set_xlabel("Qubit frequency [MHz]")
    axes[0, 0].set_ylabel("Qubit gain [DAC]")
    axes[0, 0].set_title("Direct SS qubit grid")
    if readout_scan["fidelity"].size == 1:
        rpcm = axes[0, 1].scatter(
            readout_scan["frequencies"],
            readout_scan["gains"],
            c=100.0 * readout_scan["fidelity"].reshape(-1),
            vmin=50.0,
            vmax=100.0,
            s=120,
        )
    else:
        rpcm = axes[0, 1].pcolormesh(
            readout_scan["frequencies"],
            readout_scan["gains"],
            100.0 * readout_scan["fidelity"],
            shading="nearest",
        )
    fig.colorbar(rpcm, ax=axes[0, 1], label="Fidelity [%]")
    axes[0, 1].plot(
        readout_scan["selected"]["frequency_mhz"],
        readout_scan["selected"]["gain_dac"],
        "wx",
        ms=10,
        mew=2,
    )
    axes[0, 1].set_xlabel("Readout frequency [MHz]")
    axes[0, 1].set_ylabel("Readout gain [DAC]")
    axes[0, 1].set_title("Direct SS readout grid")
    axes[1, 0].scatter(
        final_raw["ground_i"],
        final_raw["ground_q"],
        s=7,
        alpha=0.35,
        label="ground",
    )
    axes[1, 0].scatter(
        final_raw["excited_i"],
        final_raw["excited_q"],
        s=7,
        alpha=0.35,
        label="one pulse",
    )
    axes[1, 0].set_xlabel("I")
    axes[1, 0].set_ylabel("Q")
    axes[1, 0].set_title("Final validation IQ")
    axes[1, 0].legend()
    counts = np.asarray(sorted(pulse_counts), dtype=int)
    fidelities = np.asarray([pulse_counts[int(count)]["fidelity"] for count in counts])
    axes[1, 1].plot(counts, fidelities, "o-")
    axes[1, 1].axhline(0.75, color="black", linestyle="--", linewidth=1)
    axes[1, 1].set_ylim(0.45, 1.01)
    axes[1, 1].set_xticks(counts)
    axes[1, 1].set_xlabel("Repeated candidate pulses")
    axes[1, 1].set_ylabel("Ground-reference separation fidelity")
    axes[1, 1].set_title("Odd/even pulse check")
    fig.suptitle(f"{QUBIT} SSCal diagnostic: {diagnosis}")
    fig.savefig(path, dpi=170)
    plt.close(fig)


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy

    output = _make_output_dir(outerFolder)
    base_cfg = _passive_config(BaseConfig)
    current = {
        "frequency_mhz": float(base_cfg["qubit_pi_freq"]),
        "gain_dac": int(base_cfg["qubit_pi_gain"]),
        "sigma_us": float(base_cfg["sigma"]),
        "readout_frequency_mhz": float(base_cfg["read_pulse_freq"]),
        "readout_gain_dac": int(base_cfg["read_pulse_gain"]),
    }
    chevron = _latest_chevron(outerFolder)
    if chevron is None:
        chevron = {
            "path": None,
            "frequency_mhz": current["frequency_mhz"],
            "gain_dac": current["gain_dac"],
            "sigma_us": float(CHEVRON_SIGMA_US),
        }
    audit = {
        "current_ss": current,
        "base_qubit_freq_mhz": float(base_cfg["qubit_freq"]),
        "base_qubit_gain_dac": int(base_cfg["qubit_gain"]),
        "latest_chevron": chevron,
        "passive_reset_us": float(PASSIVE_RESET_US),
        "grid_shots": int(GRID_SHOTS),
        "validation_shots": int(VALIDATION_SHOTS),
        "reset_mode": "passive",
    }
    (output / "run_metadata.json").write_text(
        json.dumps(json_safe(audit), indent=2, sort_keys=True) + "\n"
    )
    print(f"output={output}")
    print(json.dumps(json_safe(audit), indent=2, sort_keys=True))
    soc, soccfg = makeProxy()
    raw_groups = {}
    metrics = {}
    print("stage=ground_drift")
    raw_groups["ground_drift"], metrics["ground_drift"] = _acquire_pair(
        soc,
        soccfg,
        base_cfg,
        current["frequency_mhz"],
        current["gain_dac"],
        current["sigma_us"],
        0,
        "ge",
        VALIDATION_SHOTS,
        outerFolder,
    )
    print("stage=current_ss_ge")
    raw_groups["current_ge"], metrics["current_ge"] = _acquire_pair(
        soc,
        soccfg,
        base_cfg,
        current["frequency_mhz"],
        current["gain_dac"],
        current["sigma_us"],
        1,
        "ge",
        VALIDATION_SHOTS,
        outerFolder,
    )
    print("stage=current_ss_eg")
    raw_groups["current_eg"], metrics["current_eg"] = _acquire_pair(
        soc,
        soccfg,
        base_cfg,
        current["frequency_mhz"],
        current["gain_dac"],
        current["sigma_us"],
        1,
        "eg",
        VALIDATION_SHOTS,
        outerFolder,
    )
    print("stage=chevron_sigma_only")
    raw_groups["chevron_sigma"], metrics["chevron_sigma"] = _acquire_pair(
        soc,
        soccfg,
        base_cfg,
        current["frequency_mhz"],
        current["gain_dac"],
        chevron["sigma_us"],
        1,
        "ge",
        VALIDATION_SHOTS,
        outerFolder,
    )
    print("stage=chevron_exact")
    raw_groups["chevron_exact"], metrics["chevron_exact"] = _acquire_pair(
        soc,
        soccfg,
        base_cfg,
        chevron["frequency_mhz"],
        chevron["gain_dac"],
        chevron["sigma_us"],
        1,
        "ge",
        VALIDATION_SHOTS,
        outerFolder,
    )
    run_optimizer = should_run_optimizer(
        chevron_exact_fidelity=metrics["chevron_exact"]["fidelity"],
        ground_drift_fidelity=metrics["ground_drift"]["fidelity"],
    )
    repeated_qubit_scan = None
    if run_optimizer:
        qubit_frequencies = np.linspace(
            chevron["frequency_mhz"] - QUBIT_FREQ_HALF_SPAN_MHZ,
            chevron["frequency_mhz"] + QUBIT_FREQ_HALF_SPAN_MHZ,
            QUBIT_FREQ_POINTS,
        )
        qubit_gains = build_gain_axis(chevron["gain_dac"], QUBIT_GAIN_POINTS)
        qubit_cfg = _pair_config(
            base_cfg,
            chevron["frequency_mhz"],
            chevron["gain_dac"],
            chevron["sigma_us"],
            "ge",
            GRID_SHOTS,
        )
        print("stage=qubit_fidelity_grid")
        q_i, q_q, q_fidelity, q_separation, q_telemetry = _acquire_grid(
            soc,
            soccfg,
            qubit_cfg,
            qubit_frequencies,
            qubit_gains,
            "qubit",
            chevron["gain_dac"],
        )
        raw_groups["qubit_grid"] = {"i": q_i, "q": q_q}
        q_selected = select_grid_best(qubit_frequencies, qubit_gains, q_fidelity)
        readout_frequencies = np.linspace(
            current["readout_frequency_mhz"] - READOUT_FREQ_HALF_SPAN_MHZ,
            current["readout_frequency_mhz"] + READOUT_FREQ_HALF_SPAN_MHZ,
            READOUT_FREQ_POINTS,
        )
        readout_gains = _readout_gain_axis(
            current["readout_gain_dac"], READOUT_GAIN_POINTS
        )
        readout_cfg = _pair_config(
            base_cfg,
            q_selected["frequency_mhz"],
            q_selected["gain_dac"],
            chevron["sigma_us"],
            "ge",
            GRID_SHOTS,
        )
        print("stage=readout_fidelity_grid")
        r_i, r_q, r_fidelity, r_separation, r_telemetry = _acquire_grid(
            soc,
            soccfg,
            readout_cfg,
            readout_frequencies,
            readout_gains,
            "readout",
            q_selected["gain_dac"],
        )
        raw_groups["readout_grid"] = {"i": r_i, "q": r_q}
        r_selected = select_grid_best(readout_frequencies, readout_gains, r_fidelity)
        final_q_selected = dict(q_selected)
        if r_selected["fidelity"] >= q_selected["fidelity"] + 0.08:
            repeated_cfg = dict(qubit_cfg)
            repeated_cfg["read_pulse_freq"] = float(r_selected["frequency_mhz"])
            repeated_cfg["read_pulse_gain"] = int(r_selected["gain_dac"])
            print("stage=qubit_fidelity_grid_after_readout_retune")
            q2_i, q2_q, q2_fidelity, q2_separation, q2_telemetry = _acquire_grid(
                soc,
                soccfg,
                repeated_cfg,
                qubit_frequencies,
                qubit_gains,
                "qubit",
                chevron["gain_dac"],
            )
            raw_groups["qubit_grid_after_readout"] = {"i": q2_i, "q": q2_q}
            final_q_selected = select_grid_best(
                qubit_frequencies, qubit_gains, q2_fidelity
            )
            repeated_qubit_scan = {
                "fidelity": q2_fidelity,
                "separation": q2_separation,
                "selected": final_q_selected,
                "telemetry": q2_telemetry,
            }
    else:
        qubit_frequencies = np.asarray([chevron["frequency_mhz"]], dtype=float)
        qubit_gains = np.asarray([chevron["gain_dac"]], dtype=int)
        q_fidelity = np.asarray([[metrics["chevron_exact"]["fidelity"]]], dtype=float)
        q_separation = np.asarray(
            [[metrics["chevron_exact"]["separation_sigma"]]], dtype=float
        )
        q_telemetry = {"skipped": True, "reason": "exact_chevron_validated"}
        q_selected = select_grid_best(qubit_frequencies, qubit_gains, q_fidelity)
        final_q_selected = dict(q_selected)
        readout_frequencies = np.asarray([current["readout_frequency_mhz"]], dtype=float)
        readout_gains = np.asarray([current["readout_gain_dac"]], dtype=int)
        r_fidelity = q_fidelity.copy()
        r_separation = q_separation.copy()
        r_telemetry = {"skipped": True, "reason": "exact_chevron_validated"}
        r_selected = select_grid_best(readout_frequencies, readout_gains, r_fidelity)
        print("stage=optimizer_skipped_exact_chevron_validated")
    final_cfg = _pair_config(
        base_cfg,
        final_q_selected["frequency_mhz"],
        final_q_selected["gain_dac"],
        chevron["sigma_us"],
        "ge",
        VALIDATION_SHOTS,
    )
    final_cfg["read_pulse_freq"] = float(r_selected["frequency_mhz"])
    final_cfg["read_pulse_gain"] = int(r_selected["gain_dac"])
    print("stage=final_ss_ge")
    raw_groups["final_ge"], metrics["final_ge"] = _acquire_pair(
        soc,
        soccfg,
        final_cfg,
        final_q_selected["frequency_mhz"],
        final_q_selected["gain_dac"],
        chevron["sigma_us"],
        1,
        "ge",
        VALIDATION_SHOTS,
        outerFolder,
    )
    print("stage=final_ss_eg")
    raw_groups["final_eg"], metrics["final_eg"] = _acquire_pair(
        soc,
        soccfg,
        final_cfg,
        final_q_selected["frequency_mhz"],
        final_q_selected["gain_dac"],
        chevron["sigma_us"],
        1,
        "eg",
        VALIDATION_SHOTS,
        outerFolder,
    )
    pulse_counts = {1: metrics["final_ge"]}
    for count in (0, 2, 3):
        print(f"stage=pulse_count_{count}")
        raw, count_metrics = _acquire_pair(
            soc,
            soccfg,
            final_cfg,
            final_q_selected["frequency_mhz"],
            final_q_selected["gain_dac"],
            chevron["sigma_us"],
            count,
            "ge",
            VALIDATION_SHOTS,
            outerFolder,
        )
        raw_groups[f"pulse_count_{count}"] = raw
        pulse_counts[count] = count_metrics
    diagnosis = classify_result(
        ground_drift_fidelity=metrics["ground_drift"]["fidelity"],
        current_fidelity=min(
            metrics["current_ge"]["fidelity"], metrics["current_eg"]["fidelity"]
        ),
        chevron_sigma_fidelity=metrics["chevron_sigma"]["fidelity"],
        chevron_exact_fidelity=metrics["chevron_exact"]["fidelity"],
        qubit_grid_fidelity=q_selected["fidelity"],
        readout_grid_fidelity=r_selected["fidelity"],
        final_ge_fidelity=metrics["final_ge"]["fidelity"],
        final_eg_fidelity=metrics["final_eg"]["fidelity"],
    )
    qubit_scan = {
        "frequencies": qubit_frequencies,
        "gains": qubit_gains,
        "fidelity": q_fidelity,
        "separation": q_separation,
        "selected": q_selected,
        "telemetry": q_telemetry,
    }
    readout_scan = {
        "frequencies": readout_frequencies,
        "gains": readout_gains,
        "fidelity": r_fidelity,
        "separation": r_separation,
        "selected": r_selected,
        "telemetry": r_telemetry,
    }
    result = {
        "diagnosis": diagnosis,
        "audit": audit,
        "metrics": metrics,
        "qubit_scan": qubit_scan,
        "readout_scan": readout_scan,
        "repeated_qubit_scan": repeated_qubit_scan,
        "pulse_counts": pulse_counts,
        "recommended_config": {
            "qubit_pi_freq": float(final_q_selected["frequency_mhz"]),
            "qubit_freq": float(final_q_selected["frequency_mhz"]),
            "qubit_pi_gain": int(final_q_selected["gain_dac"]),
            "qubit_gain": int(final_q_selected["gain_dac"]),
            "qubit_pi2_gain": int(round(final_q_selected["gain_dac"] / 2.0)),
            "sigma": float(chevron["sigma_us"]),
            "read_pulse_freq": float(r_selected["frequency_mhz"]),
            "read_pulse_gain": int(r_selected["gain_dac"]),
        },
    }
    (output / "result.json").write_text(
        json.dumps(json_safe(result), indent=2, sort_keys=True) + "\n"
    )
    _save_raw(output / "raw_iq.npz", raw_groups)
    _write_grid(
        output / "qubit_grid.csv",
        qubit_frequencies,
        qubit_gains,
        q_fidelity,
        q_separation,
    )
    _write_grid(
        output / "readout_grid.csv",
        readout_frequencies,
        readout_gains,
        r_fidelity,
        r_separation,
    )
    _plot(
        output / "diagnostic.png",
        qubit_scan if repeated_qubit_scan is None else {
            **qubit_scan,
            "fidelity": repeated_qubit_scan["fidelity"],
            "separation": repeated_qubit_scan["separation"],
            "selected": repeated_qubit_scan["selected"],
        },
        readout_scan,
        raw_groups["final_ge"],
        pulse_counts,
        diagnosis,
    )
    print(f"diagnosis={diagnosis}")
    print(f"current_ge_fidelity={metrics['current_ge']['fidelity']:.4f}")
    print(f"current_eg_fidelity={metrics['current_eg']['fidelity']:.4f}")
    print(f"chevron_sigma_fidelity={metrics['chevron_sigma']['fidelity']:.4f}")
    print(f"chevron_exact_fidelity={metrics['chevron_exact']['fidelity']:.4f}")
    print(f"qubit_grid_best_fidelity={q_selected['fidelity']:.4f}")
    print(f"readout_grid_best_fidelity={r_selected['fidelity']:.4f}")
    print(f"final_ge_fidelity={metrics['final_ge']['fidelity']:.4f}")
    print(f"final_eg_fidelity={metrics['final_eg']['fidelity']:.4f}")
    print("recommended_config=" + json.dumps(result["recommended_config"], sort_keys=True))
    print(f"output={output}")


if __name__ == "__main__":
    main()
