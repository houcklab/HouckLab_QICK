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
SHOTS = 6
MAX_AXIS_POINTS = 11


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
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
        one_shot_bank_record_base,
        resident_stream_plan,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.rabi_chevron_ss_diagnostic_q3 import (
        _axis_subset,
        matrix_comparison,
        matrix_metrics,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import PAYLOAD_RECORD_WORDS

    now = datetime.now()
    output_dir = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_resident_stream_bank_reuse"
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
    soc, soccfg = makeProxy()
    dmem_words = int(soccfg["tprocs"][0]["dmem_size"])
    records_per_shot = int(frequencies.size * gains.size)
    forced_record_base = one_shot_bank_record_base(
        dmem_words=dmem_words,
        records_per_shot=records_per_shot,
        record_words=PAYLOAD_RECORD_WORDS,
    )
    modes = (
        ("default_bank", int(cfg.get("opx_record_base", 32)), False),
        ("one_shot_bank", int(forced_record_base), False),
        ("one_shot_bank_refresh", int(forced_record_base), True),
    )
    raw = {
        "frequencies_mhz": frequencies,
        "detunings_mhz": frequencies - center,
        "gains_dac": gains,
    }
    telemetry = {}
    reset_gens = getattr(soc, "reset_gens", None)
    try:
        for mode, record_base, refresh in modes:
            if callable(reset_gens):
                reset_gens()
            run_cfg = dict(cfg)
            run_cfg.update({
                "opx_record_base": int(record_base),
                "opx_refresh_park_before_shot": bool(refresh),
            })
            plan = resident_stream_plan(
                soccfg,
                done_addr=int(run_cfg.get("opx_done_addr", 1)),
                ack_addr=int(run_cfg.get("opx_stream_ack_addr", 2)),
                ready_addr=int(run_cfg.get("opx_stream_ready_addr", 3)),
                record_base=int(record_base),
                record_words=PAYLOAD_RECORD_WORDS,
                records_per_unit=1,
                total_units=int(SHOTS * records_per_shot),
                records_per_shot=int(records_per_shot),
                total_shots=int(SHOTS),
            )
            print(
                f"stage={mode} record_base={record_base} "
                f"bank_units={plan['bank_units']}"
            )
            started = time.time()
            i_values, q_values, mode_telemetry = acquire_pulse_grid_iq(
                soc,
                soccfg,
                run_cfg,
                frequencies_mhz=frequencies,
                gains=gains,
                pulses=int(pulses),
                shots=int(SHOTS),
                pulse_placement="excursion",
                do_excursion=False,
                reset_scheme="none",
                progress=lambda done, total, label=mode, began=started: progress_counter(
                    int(done) - 1,
                    int(total),
                    start_time=began,
                    label=f"stream {label}",
                ),
            )
            raw[f"{mode}_i"] = np.asarray(i_values)
            raw[f"{mode}_q"] = np.asarray(q_values)
            telemetry[mode] = {
                **dict(mode_telemetry),
                "elapsed_s": float(time.time() - started),
                "record_base": int(record_base),
                "stream_plan": plan,
                "opx_refresh_park_before_shot": bool(refresh),
            }
            np.savez_compressed(output_dir / "raw_iq.npz", **raw)
    finally:
        if callable(reset_gens):
            reset_gens()

    baseline_ngains = max(
        1,
        min(int(cfg.get("baseline_ngains", 4)), max(1, gains.size // 4)),
    )
    maps = {}
    metrics = {}
    for mode, _, _ in modes:
        i_values = raw[f"{mode}_i"]
        q_values = raw[f"{mode}_q"]
        all_response = rabi_iq_response_map(
            i_values,
            q_values,
            baseline_ngains=baseline_ngains,
        )
        early_response = rabi_iq_response_map(
            i_values[:, :, :2],
            q_values[:, :, :2],
            baseline_ngains=baseline_ngains,
        )
        late_response = rabi_iq_response_map(
            i_values[:, :, 2:],
            q_values[:, :, 2:],
            baseline_ngains=baseline_ngains,
        )
        maps[mode] = {
            "all": all_response,
            "early": early_response,
            "late": late_response,
        }
        per_shot = []
        for shot in range(int(SHOTS)):
            shot_response = rabi_iq_response_map(
                i_values[:, :, shot:shot + 1],
                q_values[:, :, shot:shot + 1],
                baseline_ngains=baseline_ngains,
            )
            per_shot.append({
                "shot": int(shot + 1),
                "mean_i": float(np.mean(i_values[:, :, shot])),
                "mean_q": float(np.mean(q_values[:, :, shot])),
                **matrix_metrics(shot_response, frequencies, gains),
            })
        early_metrics = matrix_metrics(early_response, frequencies, gains)
        late_metrics = matrix_metrics(late_response, frequencies, gains)
        metrics[mode] = {
            "all": matrix_metrics(all_response, frequencies, gains),
            "early": early_metrics,
            "late": late_metrics,
            "early_vs_late": matrix_comparison(
                early_response,
                late_response,
            ),
            "late_to_early_contrast_ratio": (
                None
                if float(early_metrics["contrast"]) == 0.0
                else float(
                    late_metrics["contrast"] / early_metrics["contrast"]
                )
            ),
            "per_shot": per_shot,
        }
        raw[f"{mode}_all_response"] = all_response
        raw[f"{mode}_early_response"] = early_response
        raw[f"{mode}_late_response"] = late_response
    np.savez_compressed(output_dir / "raw_iq.npz", **raw)

    result = {
        "source_commit": source_commit,
        "qubit": QUBIT,
        "shots_per_point": int(SHOTS),
        "frequency_points": int(frequencies.size),
        "gain_points": int(gains.size),
        "records_per_shot": int(records_per_shot),
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
        "telemetry": telemetry,
    }
    (output_dir / "result.json").write_text(
        json.dumps(json_safe(result), indent=2, sort_keys=True) + "\n"
    )

    extent = [
        float(gains[0]),
        float(gains[-1]),
        float(frequencies[0] - center),
        float(frequencies[-1] - center),
    ]
    fig, axes = plt.subplots(3, 3, figsize=(14, 11), constrained_layout=True)
    for row, (mode, _, _) in enumerate(modes):
        for column, view in enumerate(("all", "early", "late")):
            image = axes[row, column].imshow(
                maps[mode][view],
                origin="lower",
                aspect="auto",
                extent=extent,
                interpolation="nearest",
            )
            axes[row, column].set_title(f"{mode}: {view}")
            axes[row, column].set_xlabel("Qubit gain [DAC]")
            axes[row, column].set_ylabel("Detuning [MHz]")
            fig.colorbar(image, ax=axes[row, column], fraction=0.046)
    fig.savefig(output_dir / "bank_reuse_maps.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    for column, (mode, _, _) in enumerate(modes):
        rows = metrics[mode]["per_shot"]
        axes[column].plot(
            [row["shot"] for row in rows],
            [row["contrast"] for row in rows],
            marker="o",
        )
        axes[column].axvline(2.5, color="red", linestyle="--")
        axes[column].set_title(mode)
        axes[column].set_xlabel("Shot")
        axes[column].set_ylabel("Rabi IQ contrast")
    fig.savefig(output_dir / "bank_reuse_shot_contrast.png", dpi=180)
    plt.close(fig)

    for mode, _, _ in modes:
        values = metrics[mode]
        print(
            f"{mode} early_contrast={values['early']['contrast']:.6f} "
            f"late_contrast={values['late']['contrast']:.6f} "
            f"late_to_early={values['late_to_early_contrast_ratio']}"
        )
    print(f"output={output_dir}")


if __name__ == "__main__":
    main()
