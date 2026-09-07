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
SHOTS = 30
MAX_AXIS_POINTS = 11
SHOT_BLOCK_SIZE = 5


def main():
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronIQ import n_drive_pulses
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import GateCalibration as runner
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
        json_safe,
        rabi_iq_response_map,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import acquire_pulse_grid_iq
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.rabi_chevron_ss_diagnostic_q3 import (
        _axis_subset,
        matrix_comparison,
        matrix_metrics,
    )

    now = datetime.now()
    output_dir = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_Rabi_Chevron_IQ_park_refresh_AB"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    print(f"output={output_dir}")
    try:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_repo_root, text=True
        ).strip()
    except Exception:
        source_commit = "unknown"

    p = dict(runner.P_RABI_CHEVRON_IQ)
    gain_count = int(p["a_points"])
    gain_step = int(round(
        (float(p["a_max"]) - float(p["a_min"]))
        / max(gain_count - 1, 1)
    ))
    production_gains = (
        int(round(float(p["a_min"])))
        + gain_step * np.arange(gain_count)
    ).astype(int)
    gains = _axis_subset(production_gains, MAX_AXIS_POINTS).astype(int)
    center = float(BaseConfig.get("qubit_pi_freq", BaseConfig["qubit_freq"]))
    production_frequencies = np.linspace(
        center - float(p["freq_span_mhz"]) / 2.0,
        center + float(p["freq_span_mhz"]) / 2.0,
        int(p["freq_points"]),
    )
    frequencies = _axis_subset(
        production_frequencies, MAX_AXIS_POINTS
    ).astype(float)
    pulses = n_drive_pulses(str(p["pulse_type"]), int(p["num_pi"]))
    cfg = runner._base_cfg(
        p,
        extra={
            "amp_start": int(production_gains[0]),
            "amp_stop": int(production_gains[-1]),
            "amp_expts": int(production_gains.size),
            "freq_span": float(p["freq_span_mhz"]),
            "freq_points": int(p["freq_points"]),
            "qubit_pulse_style": "arb",
            "sigma": float(p.get("sigma_us", BaseConfig["sigma"])),
            "relax_delay": float(p.get("relax_delay_us", 1000.0)),
            "qua_passive_pre_point_delay_us": float(
                p.get("relax_delay_us", 1000.0)
            ),
        },
        active=False,
    )
    cfg.update({
        "shots": int(SHOTS),
        "reps": int(SHOTS),
        "n_pulses": int(pulses),
        "remeasure_outliers": False,
    })
    do_excursion = bool(cfg.get("ff_hold_gain", 0))
    soc, soccfg = makeProxy()
    modes = (
        ("no_refresh", False),
        ("refresh_each_measurement", True),
    )
    raw = {
        "frequencies_mhz": frequencies,
        "detunings_mhz": frequencies - center,
        "gains_dac": gains,
    }
    telemetry = {}
    started = {}
    reset_gens = getattr(soc, "reset_gens", None)
    try:
        for mode, refresh in modes:
            if callable(reset_gens):
                reset_gens()
            run_cfg = dict(cfg)
            run_cfg["opx_refresh_park_before_shot"] = bool(refresh)
            print(f"stage={mode}")
            started[mode] = time.time()
            progress_started = started[mode]
            i_values, q_values, mode_telemetry = acquire_pulse_grid_iq(
                soc,
                soccfg,
                run_cfg,
                frequencies_mhz=frequencies,
                gains=gains,
                pulses=int(pulses),
                shots=int(SHOTS),
                pulse_placement="excursion",
                do_excursion=do_excursion,
                excursion_gain=(
                    cfg.get("ff_hold_gain") if do_excursion else None
                ),
                reset_scheme="none",
                progress=lambda done, total, label=mode, began=progress_started: progress_counter(
                    int(done) - 1,
                    int(total),
                    start_time=began,
                    label=f"Rabi IQ {label}",
                ),
            )
            raw[f"{mode}_i"] = np.asarray(i_values)
            raw[f"{mode}_q"] = np.asarray(q_values)
            telemetry[mode] = {
                **dict(mode_telemetry),
                "elapsed_s": float(time.time() - started[mode]),
                "opx_refresh_park_before_shot": bool(refresh),
            }
            np.savez_compressed(output_dir / "raw_iq.npz", **raw)
    finally:
        if callable(reset_gens):
            reset_gens()

    maps = {}
    metrics = {}
    block_metrics = {}
    baseline_ngains = max(
        1,
        min(int(cfg.get("baseline_ngains", 4)), max(1, gains.size // 4)),
    )
    for mode, _ in modes:
        i_values = raw[f"{mode}_i"]
        q_values = raw[f"{mode}_q"]
        maps[mode] = {
            "mean_i": np.mean(i_values, axis=2),
            "mean_q": np.mean(q_values, axis=2),
            "response": rabi_iq_response_map(
                i_values,
                q_values,
                baseline_ngains=baseline_ngains,
            ),
        }
        metrics[mode] = matrix_metrics(
            maps[mode]["response"], frequencies, gains
        )
        rows = []
        for first in range(0, int(SHOTS), int(SHOT_BLOCK_SIZE)):
            last = min(first + int(SHOT_BLOCK_SIZE), int(SHOTS))
            response = rabi_iq_response_map(
                i_values[:, :, first:last],
                q_values[:, :, first:last],
                baseline_ngains=baseline_ngains,
            )
            rows.append({
                "shot_first": int(first + 1),
                "shot_last": int(last),
                **matrix_metrics(response, frequencies, gains),
            })
        block_metrics[mode] = rows
        raw[f"{mode}_mean_i"] = maps[mode]["mean_i"]
        raw[f"{mode}_mean_q"] = maps[mode]["mean_q"]
        raw[f"{mode}_response"] = maps[mode]["response"]
    np.savez_compressed(output_dir / "raw_iq.npz", **raw)

    comparison = matrix_comparison(
        maps["no_refresh"]["response"],
        maps["refresh_each_measurement"]["response"],
    )
    no_refresh_contrast = float(metrics["no_refresh"]["contrast"])
    refresh_contrast = float(
        metrics["refresh_each_measurement"]["contrast"]
    )
    contrast_ratio = (
        None
        if no_refresh_contrast == 0.0
        else float(refresh_contrast / no_refresh_contrast)
    )
    result = {
        "source_commit": source_commit,
        "qubit": QUBIT,
        "shots_per_point": int(SHOTS),
        "frequency_points": int(frequencies.size),
        "gain_points": int(gains.size),
        "center_frequency_mhz": float(center),
        "frequencies_mhz": frequencies,
        "detunings_mhz": frequencies - center,
        "gains_dac": gains,
        "pulse_type": str(p["pulse_type"]),
        "num_pi": int(p["num_pi"]),
        "drive_pulses": int(pulses),
        "sigma_us": float(cfg["sigma"]),
        "passive_reset_us": float(cfg["relax_delay"]),
        "park_gain_dac": int(cfg.get("ff_park_gain", 0)),
        "acquisition_order": "shot_frequency_gain",
        "baseline_ngains": int(baseline_ngains),
        "metrics": metrics,
        "shot_block_metrics": block_metrics,
        "comparison": comparison,
        "refresh_to_no_refresh_contrast_ratio": contrast_ratio,
        "telemetry": telemetry,
    }
    (output_dir / "result.json").write_text(
        json.dumps(json_safe(result), indent=2, sort_keys=True) + "\n"
    )

    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    extent = [
        float(gains[0]),
        float(gains[-1]),
        float(frequencies[0] - center),
        float(frequencies[-1] - center),
    ]
    for row, (mode, _) in enumerate(modes):
        for column, key in enumerate(("mean_i", "mean_q", "response")):
            image = axes[row, column].imshow(
                maps[mode][key],
                origin="lower",
                aspect="auto",
                extent=extent,
                interpolation="nearest",
            )
            axes[row, column].set_title(f"{mode}: {key}")
            axes[row, column].set_xlabel("Qubit gain [DAC]")
            axes[row, column].set_ylabel("Detuning [MHz]")
            fig.colorbar(image, ax=axes[row, column], fraction=0.046)
    fig.savefig(output_dir / "park_refresh_ab.png", dpi=180)
    plt.close(fig)

    print(f"no_refresh_contrast={no_refresh_contrast:.6f}")
    print(f"refresh_each_measurement_contrast={refresh_contrast:.6f}")
    print(f"refresh_to_no_refresh_contrast_ratio={contrast_ratio}")
    print(f"map_correlation={comparison['correlation']}")
    print(f"output={output_dir}")


if __name__ == "__main__":
    main()
