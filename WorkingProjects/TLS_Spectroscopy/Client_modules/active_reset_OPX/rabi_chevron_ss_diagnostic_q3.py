from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        _repo_root = parent
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


QUBIT = "q3"
DIAGNOSTIC_SHOTS = 100
SS_CAL_SHOTS = 1000
PASSIVE_RESET_US = 1000.0
MAX_AXIS_POINTS = 11
HOST_WATCHDOG_S = 5.0
MIN_BLOB_CONTRAST = 0.15
MAX_FLAT_CONTRAST = 0.08
MIN_SS_FIDELITY = 0.70


def matrix_metrics(values, frequencies_mhz, gains_dac):
    values = np.asarray(values, dtype=float)
    frequencies = np.asarray(frequencies_mhz, dtype=float).reshape(-1)
    gains = np.asarray(gains_dac, dtype=int).reshape(-1)
    if values.shape != (frequencies.size, gains.size):
        raise ValueError("matrix shape does not match its frequency and gain axes")
    finite = np.isfinite(values)
    if not np.any(finite):
        return {
            "minimum": None,
            "maximum": None,
            "mean": None,
            "contrast": None,
            "peak_frequency_mhz": None,
            "peak_gain_dac": None,
        }
    masked = np.where(finite, values, -np.inf)
    peak = np.unravel_index(int(np.argmax(masked)), values.shape)
    finite_values = values[finite]
    minimum = float(np.min(finite_values))
    maximum = float(np.max(finite_values))
    return {
        "minimum": minimum,
        "maximum": maximum,
        "mean": float(np.mean(finite_values)),
        "contrast": maximum - minimum,
        "peak_frequency_mhz": float(frequencies[peak[0]]),
        "peak_gain_dac": int(gains[peak[1]]),
    }


def matrix_comparison(reference, candidate):
    reference = np.asarray(reference, dtype=float)
    candidate = np.asarray(candidate, dtype=float)
    if reference.shape != candidate.shape:
        raise ValueError("matrix comparison requires equal shapes")
    finite = np.isfinite(reference) & np.isfinite(candidate)
    if not np.any(finite):
        return {"rmse": None, "correlation": None}
    left = reference[finite]
    right = candidate[finite]
    rmse = float(np.sqrt(np.mean((left - right) ** 2)))
    if left.size < 2 or np.std(left) == 0 or np.std(right) == 0:
        correlation = None
    else:
        correlation = float(np.corrcoef(left, right)[0, 1])
    return {"rmse": rmse, "correlation": correlation}


def classify_diagnostic(
    *,
    ss_fidelity,
    contrasts,
    min_blob_contrast=MIN_BLOB_CONTRAST,
    max_flat_contrast=MAX_FLAT_CONTRAST,
    min_ss_fidelity=MIN_SS_FIDELITY,
):
    if not np.isfinite(float(ss_fidelity)) or float(ss_fidelity) < min_ss_fidelity:
        return "single_shot_or_pi_calibration"
    values = {key: float(value) for key, value in dict(contrasts).items()}
    if (
        values["resident_active_grid_axis"] >= min_blob_contrast
        and values["resident_active_grid_threshold"] <= max_flat_contrast
    ):
        return "payload_classifier"
    if values["legacy_passive_axis"] < min_blob_contrast:
        return "qubit_pulse_or_readout_timing"
    if values["resident_passive_axis"] < min_blob_contrast:
        return "resident_grid_or_dmem"
    if (
        values["resident_active_grid_axis"] < min_blob_contrast
        and values["resident_active_rowwise_axis"] >= min_blob_contrast
    ):
        return "nested_grid_programming"
    if values["resident_active_grid_axis"] < min_blob_contrast:
        return "active_reset_lifecycle"
    return "failure_not_reproduced"


def population_views(i_values, q_values, bundle, legacy_calibration, read_cycles):
    i_values = np.asarray(i_values, dtype=float)
    q_values = np.asarray(q_values, dtype=float)
    if i_values.shape != q_values.shape or i_values.ndim != 3:
        raise ValueError("diagnostic IQ arrays must have frequency, gain, shot axes")
    raw_i = np.rint(i_values * int(read_cycles)).astype(np.int64)
    raw_q = np.rint(q_values * int(read_cycles)).astype(np.int64)
    projected = bundle.payload.project(raw_i, raw_q)
    threshold_states = projected > int(bundle.payload.excited_threshold)
    axis_values = bundle.reference_axis.population(raw_i, raw_q)
    theta = float(legacy_calibration["read_theta"])
    factor = float(legacy_calibration["scale_factor"])
    threshold = float(legacy_calibration["threshold"])
    rotated = factor * np.real(
        np.exp(-1j * theta) * (i_values + 1j * q_values)
    )
    legacy_states = rotated > threshold
    return {
        "threshold": np.mean(threshold_states, axis=2),
        "legacy": np.mean(legacy_states, axis=2),
        "axis": np.mean(axis_values, axis=2),
        "classifier_disagreement": np.mean(
            threshold_states != legacy_states, axis=2
        ),
        "mean_i": np.mean(i_values, axis=2),
        "mean_q": np.mean(q_values, axis=2),
    }


def _axis_subset(values, maximum):
    values = np.asarray(values)
    if values.size <= int(maximum):
        return values
    stride = int(np.ceil((values.size - 1) / max(int(maximum) - 1, 1)))
    indices = np.arange(0, values.size, stride, dtype=int)
    return values[indices]


def _resolved_rabi_settings(values, base_config):
    resolved = dict(values)
    resolved["sigma_us"] = float(
        resolved.get("sigma_us", base_config["sigma"])
    )
    return resolved


def _write_json(path, values):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import json_safe

    Path(path).write_text(
        json.dumps(json_safe(values), indent=2, sort_keys=True) + "\n"
    )


def _save_raw(path, values):
    np.savez_compressed(path, **values)


def _progress(label):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter

    started = time.time()
    return lambda done, total: progress_counter(
        int(done) - 1,
        int(total),
        start_time=started,
        label=label,
    )


def _legacy_passive_grid(
    soc,
    soccfg,
    cfg,
    frequencies,
    gains,
    pulses,
    shots,
    calib_params,
):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronSS import sweep_gain_populations
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter

    experiment = type("Experiment", (), {"soc": soc, "soccfg": soccfg})()
    i_rows = []
    q_rows = []
    started = time.time()
    for index, frequency in enumerate(frequencies):
        row_cfg = dict(cfg)
        row_cfg.update({
            "rabi_drive_freq": float(frequency),
            "n_pulses": int(pulses),
            "shots": int(shots),
            "reps": int(shots),
            "reset_mode": "passive",
            "relax_delay": float(PASSIVE_RESET_US),
            "qua_shot_order": False,
        })
        _, i_values, q_values = sweep_gain_populations(
            experiment,
            row_cfg,
            gains,
            calib_params,
            progress=False,
            return_iq=True,
        )
        i_rows.append(i_values)
        q_rows.append(q_values)
        progress_counter(
            index,
            len(frequencies),
            start_time=started,
            label="legacy passive rows",
        )
    return np.asarray(i_rows), np.asarray(q_rows)


def _resident_grid(
    soc,
    soccfg,
    cfg,
    frequencies,
    gains,
    pulses,
    shots,
    reset_scheme,
    label,
):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import acquire_pulse_grid_iq

    i_values, q_values, telemetry = acquire_pulse_grid_iq(
        soc,
        soccfg,
        cfg,
        frequencies_mhz=frequencies,
        gains=gains,
        pulses=int(pulses),
        shots=int(shots),
        pulse_placement="excursion",
        do_excursion=False,
        reset_scheme=reset_scheme,
        progress=_progress(label),
    )
    return i_values, q_values, telemetry


def _active_rowwise_grid(
    soc,
    soccfg,
    cfg,
    frequencies,
    gains,
    pulses,
    shots,
):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import acquire_pulse_sweep_iq
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter

    i_rows = []
    q_rows = []
    telemetry = []
    started = time.time()
    for index, frequency in enumerate(frequencies):
        i_values, q_values, row_telemetry = acquire_pulse_sweep_iq(
            soc,
            soccfg,
            cfg,
            gains=gains,
            pulses=int(pulses),
            frequency_mhz=float(frequency),
            shots=int(shots),
            pulse_placement="excursion",
            do_excursion=False,
            reset_scheme="opx_unbounded",
        )
        i_rows.append(i_values)
        q_rows.append(q_values)
        telemetry.append(dict(row_telemetry))
        progress_counter(
            index,
            len(frequencies),
            start_time=started,
            label="active rowwise",
        )
    return np.asarray(i_rows), np.asarray(q_rows), telemetry


def _plot(path, frequencies, gains, views, diagnosis):
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    mode_names = (
        "legacy_passive",
        "resident_passive",
        "resident_active_grid",
        "resident_active_rowwise",
    )
    view_names = ("threshold", "legacy", "axis")
    titles = {
        "threshold": "production threshold",
        "legacy": "standalone SS threshold",
        "axis": "continuous reference axis",
    }
    fig, axes = plt.subplots(
        len(mode_names),
        len(view_names),
        figsize=(13, 13),
        constrained_layout=True,
        sharex=True,
        sharey=True,
    )
    extent = [
        float(gains[0]),
        float(gains[-1]),
        float(frequencies[0]),
        float(frequencies[-1]),
    ]
    for row, mode in enumerate(mode_names):
        for column, view in enumerate(view_names):
            values = np.asarray(views[mode][view], dtype=float)
            image = axes[row, column].imshow(
                values,
                origin="lower",
                aspect="auto",
                extent=extent,
                vmin=0.0,
                vmax=1.0,
                interpolation="nearest",
            )
            axes[row, column].set_title(f"{mode}\n{titles[view]}")
            axes[row, column].set_ylabel("Drive frequency [MHz]")
            axes[row, column].set_xlabel("Qubit gain [DAC]")
            fig.colorbar(image, ax=axes[row, column], fraction=0.046)
    fig.suptitle(f"q3 Rabi Chevron SS diagnostic: {diagnosis}")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(f"Expected qick 0.2.133, found {qick.__version__}")

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronIQ import n_drive_pulses
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.GateCalibration import P_RABI_CHEVRON_SS
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import CalibrationBundle, save_calibration
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import prepare_reset_session

    now = datetime.now()
    output_dir = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_Rabi_Chevron_SS_diagnostic"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    print(f"output={output_dir}")
    try:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_repo_root, text=True
        ).strip()
    except Exception:
        source_commit = "unknown"
    p = _resolved_rabi_settings(P_RABI_CHEVRON_SS, BaseConfig)
    original_gain_count = int(p["a_points"])
    original_gain_step = int(round(
        (float(p["a_max"]) - float(p["a_min"]))
        / max(original_gain_count - 1, 1)
    ))
    original_gains = (
        int(round(float(p["a_min"])))
        + original_gain_step * np.arange(original_gain_count)
    ).astype(int)
    gains = _axis_subset(original_gains, MAX_AXIS_POINTS).astype(int)
    soc, soccfg = makeProxy()
    reset_session = prepare_reset_session(
        "active",
        outer_folder=outerFolder,
        qubit=QUBIT,
        base_cfg=BaseConfig,
        soc=soc,
        soccfg=soccfg,
        purpose="Rabi Chevron SS diagnostic",
        now=now.strftime("%Y_%m_%d_%H_%M_%S"),
    )
    active_cfg = reset_session.apply(dict(BaseConfig))
    active_cfg.update({
        "shots": int(DIAGNOSTIC_SHOTS),
        "reps": int(DIAGNOSTIC_SHOTS),
        "sigma": float(p["sigma_us"]),
        "ff_hold_gain": 0,
        "readout_after_park": True,
        "opx_unbounded_watchdog_s": float(HOST_WATCHDOG_S),
    })
    center = float(active_cfg["qubit_pi_freq"])
    original_frequencies = np.linspace(
        center - float(p["freq_span_mhz"]) / 2.0,
        center + float(p["freq_span_mhz"]) / 2.0,
        int(p["freq_points"]),
    )
    frequencies = _axis_subset(
        original_frequencies, MAX_AXIS_POINTS
    ).astype(float)
    pulses = n_drive_pulses(str(p["pulse_type"]), int(p["num_pi"]))
    bundle = CalibrationBundle.from_dict(reset_session.calibration)
    save_calibration(output_dir / "active_reset_calibration.json", bundle)
    ss_cfg = dict(active_cfg)
    ss_cfg.update({
        "reset_mode": "passive",
        "shots": int(SS_CAL_SHOTS),
        "reps": int(SS_CAL_SHOTS),
        "relax_delay": float(PASSIVE_RESET_US),
        "qubit_gain": int(BaseConfig["qubit_pi_gain"]),
        "qubit_pi_freq": float(center),
        "single_shot_state_order": "ge",
    })
    ss_cfg.pop("opx_reset_calibration", None)
    print("stage=standalone_single_shot")
    ss = SingleShot1Q(
        soc=soc,
        soccfg=soccfg,
        path=QUBIT,
        outerFolder=str(output_dir),
        suffix="diagnostic_SS",
        cfg=ss_cfg,
        repeats=1,
        plot=False,
        save=False,
    )
    ss.acquire(progress=True, plotDisp=False)
    raw = {
        "frequencies_mhz": frequencies,
        "gains_dac": gains,
        "ss_ground_i": np.asarray(ss.I_0),
        "ss_ground_q": np.asarray(ss.Q_0),
        "ss_excited_i": np.asarray(ss.I_1),
        "ss_excited_q": np.asarray(ss.Q_1),
    }
    _save_raw(output_dir / "raw_iq.npz", raw)
    passive_cfg = dict(active_cfg)
    passive_cfg.update({
        "reset_mode": "passive",
        "relax_delay": float(PASSIVE_RESET_US),
        "qua_passive_pre_point_delay_us": float(PASSIVE_RESET_US),
        "opx_inter_shot_delay_us": float(PASSIVE_RESET_US),
    })
    print("stage=legacy_passive")
    legacy_i, legacy_q = _legacy_passive_grid(
        soc,
        soccfg,
        passive_cfg,
        frequencies,
        gains,
        pulses,
        DIAGNOSTIC_SHOTS,
        ss.calib_params,
    )
    raw.update({"legacy_passive_i": legacy_i, "legacy_passive_q": legacy_q})
    _save_raw(output_dir / "raw_iq.npz", raw)
    print("stage=resident_passive")
    resident_passive_i, resident_passive_q, resident_passive_telemetry = _resident_grid(
        soc,
        soccfg,
        passive_cfg,
        frequencies,
        gains,
        pulses,
        DIAGNOSTIC_SHOTS,
        "none",
        "resident passive",
    )
    raw.update({
        "resident_passive_i": resident_passive_i,
        "resident_passive_q": resident_passive_q,
    })
    _save_raw(output_dir / "raw_iq.npz", raw)
    print("stage=resident_active_grid")
    active_i, active_q, active_telemetry = _resident_grid(
        soc,
        soccfg,
        active_cfg,
        frequencies,
        gains,
        pulses,
        DIAGNOSTIC_SHOTS,
        "opx_unbounded",
        "resident active grid",
    )
    raw.update({"resident_active_grid_i": active_i, "resident_active_grid_q": active_q})
    _save_raw(output_dir / "raw_iq.npz", raw)
    print("stage=resident_active_rowwise")
    try:
        row_i, row_q, row_telemetry = _active_rowwise_grid(
            soc,
            soccfg,
            active_cfg,
            frequencies,
            gains,
            pulses,
            DIAGNOSTIC_SHOTS,
        )
        control_frequencies = _axis_subset(frequencies, 3)
        control_gains = _axis_subset(gains, 3)
        print("stage=no_drive_control")
        control_i, control_q, control_telemetry = _resident_grid(
            soc,
            soccfg,
            active_cfg,
            control_frequencies,
            control_gains,
            0,
            DIAGNOSTIC_SHOTS,
            "opx_unbounded",
            "no-drive control",
        )
    finally:
        reset_gens = getattr(soc, "reset_gens", None)
        if callable(reset_gens):
            reset_gens()
    raw.update({
        "resident_active_rowwise_i": row_i,
        "resident_active_rowwise_q": row_q,
        "no_drive_i": control_i,
        "no_drive_q": control_q,
    })
    read_cycles = int(soccfg.us2cycles(
        active_cfg["read_length"], ro_ch=active_cfg["ro_chs"][0]
    ))
    mode_iq = {
        "legacy_passive": (legacy_i, legacy_q),
        "resident_passive": (resident_passive_i, resident_passive_q),
        "resident_active_grid": (active_i, active_q),
        "resident_active_rowwise": (row_i, row_q),
    }
    views = {
        mode: population_views(
            i_values,
            q_values,
            bundle,
            ss.calib_params,
            read_cycles,
        )
        for mode, (i_values, q_values) in mode_iq.items()
    }
    control_views = population_views(
        control_i,
        control_q,
        bundle,
        ss.calib_params,
        read_cycles,
    )
    for mode, mode_views in views.items():
        for view, values in mode_views.items():
            raw[f"{mode}_{view}"] = values
    for view, values in control_views.items():
        raw[f"no_drive_{view}"] = values
    _save_raw(output_dir / "raw_iq.npz", raw)
    metrics = {
        mode: {
            view: matrix_metrics(values, frequencies, gains)
            for view, values in mode_views.items()
        }
        for mode, mode_views in views.items()
    }
    contrasts = {
        "legacy_passive_axis": metrics["legacy_passive"]["axis"]["contrast"],
        "resident_passive_axis": metrics["resident_passive"]["axis"]["contrast"],
        "resident_active_grid_axis": metrics["resident_active_grid"]["axis"]["contrast"],
        "resident_active_grid_threshold": metrics["resident_active_grid"]["threshold"]["contrast"],
        "resident_active_rowwise_axis": metrics["resident_active_rowwise"]["axis"]["contrast"],
    }
    diagnosis = classify_diagnostic(
        ss_fidelity=float(ss.max_F),
        contrasts=contrasts,
    )
    transposed_rowwise = views["resident_active_rowwise"]["axis"].T
    transposed_comparison = (
        matrix_comparison(
            views["resident_active_grid"]["axis"],
            transposed_rowwise,
        )
        if views["resident_active_grid"]["axis"].shape == transposed_rowwise.shape
        else {"rmse": None, "correlation": None}
    )
    comparisons = {
        "legacy_vs_resident_passive_axis": matrix_comparison(
            views["legacy_passive"]["axis"],
            views["resident_passive"]["axis"],
        ),
        "resident_passive_vs_active_grid_axis": matrix_comparison(
            views["resident_passive"]["axis"],
            views["resident_active_grid"]["axis"],
        ),
        "active_grid_vs_rowwise_axis": matrix_comparison(
            views["resident_active_grid"]["axis"],
            views["resident_active_rowwise"]["axis"],
        ),
        "active_grid_vs_rowwise_axis_transposed": transposed_comparison,
    }
    result = {
        "diagnosis": diagnosis,
        "source_commit": source_commit,
        "qubit": QUBIT,
        "shots_per_point": int(DIAGNOSTIC_SHOTS),
        "frequency_points": int(len(frequencies)),
        "gain_points": int(len(gains)),
        "frequency_center_mhz": center,
        "frequencies_mhz": frequencies,
        "gains_dac": gains,
        "pulse_type": str(p["pulse_type"]),
        "num_pi": int(p["num_pi"]),
        "drive_pulses": int(pulses),
        "sigma_us": float(p["sigma_us"]),
        "passive_reset_us": float(PASSIVE_RESET_US),
        "standalone_ss_fidelity": float(ss.max_F),
        "standalone_ss_calibration": dict(ss.calib_params),
        "active_reset_calibration_output": str(reset_session.calibration_output),
        "metrics": metrics,
        "contrasts": contrasts,
        "comparisons": comparisons,
        "no_drive": {
            view: matrix_metrics(values, control_frequencies, control_gains)
            for view, values in control_views.items()
        },
        "telemetry": {
            "resident_passive": resident_passive_telemetry,
            "resident_active_grid": active_telemetry,
            "resident_active_rowwise": row_telemetry,
            "no_drive": control_telemetry,
        },
    }
    _write_json(output_dir / "result.json", result)
    _plot(
        output_dir / "diagnostic.png",
        frequencies,
        gains,
        views,
        diagnosis,
    )
    print(f"diagnosis={diagnosis}")
    print(f"standalone_ss_fidelity={ss.max_F:.4f}")
    for mode in mode_iq:
        print(
            f"{mode} "
            f"threshold_contrast={metrics[mode]['threshold']['contrast']:.4f} "
            f"axis_contrast={metrics[mode]['axis']['contrast']:.4f} "
            f"legacy_contrast={metrics[mode]['legacy']['contrast']:.4f}"
        )
    print(
        "active_grid_vs_rowwise_axis_rmse="
        f"{comparisons['active_grid_vs_rowwise_axis']['rmse']:.6f}"
    )
    print(f"output={output_dir}")


if __name__ == "__main__":
    main()
