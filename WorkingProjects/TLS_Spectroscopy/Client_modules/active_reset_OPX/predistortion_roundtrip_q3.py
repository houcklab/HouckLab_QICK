import csv
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

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
PARK_GAIN = -25146
TARGET_GAIN = -14750
FREQUENCY_HALF_SPAN_MHZ = 15.0
FREQUENCY_STEP_MHZ = 0.5
SHOTS_PER_POINT = 30
TARGET_HOLD_US = 70.0
RECOVERY_TIMES_US = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0)
PASSIVE_REARM_US = 1000.0
PARK_PREROLL_US = 400.0


def _output_directory(outer_folder):
    now = datetime.now()
    day = Path(outer_folder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_predistortion_roundtrip"
    output.mkdir(parents=True, exist_ok=False)
    return output


def _center(frequencies, i_values, q_values):
    response = np.mean(
        np.asarray(i_values, dtype=float) + 1j * np.asarray(q_values, dtype=float),
        axis=1,
    )
    magnitude = np.abs(response)
    edge_count = max(3, int(np.ceil(0.15 * magnitude.size)))
    baseline = float(np.median(np.r_[magnitude[:edge_count], magnitude[-edge_count:]]))
    contrast = np.abs(magnitude - baseline)
    peak = int(np.argmax(contrast))
    lo = max(0, peak - 2)
    hi = min(frequencies.size, peak + 3)
    center = float(frequencies[peak])
    if hi - lo >= 3:
        coefficients = np.polyfit(frequencies[lo:hi], contrast[lo:hi], 2)
        if coefficients[0] < 0:
            vertex = float(-coefficients[1] / (2.0 * coefficients[0]))
            if frequencies[lo] <= vertex <= frequencies[hi - 1]:
                center = vertex
    return center, float(contrast[peak]), magnitude


def _write_csv(path, frequencies, curves):
    with Path(path).open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("method", "recovery_us", "frequency_mhz", "magnitude"))
        for curve in curves:
            recovery = curve["recovery_us"]
            for frequency, magnitude in zip(frequencies, curve["magnitude"]):
                writer.writerow((curve["method"], recovery, frequency, magnitude))


def _plot(path, frequencies, curves, reference_center):
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(10, 9), constrained_layout=True)
    for curve in curves:
        label = curve["method"]
        if curve["recovery_us"] is not None:
            label += f" {curve['recovery_us']:g} us"
        axes[0].plot(frequencies, curve["magnitude"], linewidth=1, label=label)
    for mode in ("raw", "predistorted"):
        selected = [curve for curve in curves if curve["method"] == mode]
        axes[1].plot(
            [curve["recovery_us"] for curve in selected],
            [curve["center_mhz"] - reference_center for curve in selected],
            marker="o",
            label=mode,
        )
    axes[0].set(xlabel="Qubit drive frequency [MHz]", ylabel="Mean |IQ|")
    axes[0].legend(ncol=2, fontsize=8)
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set(
        xscale="log",
        xlabel="Target-to-park recovery [us]",
        ylabel="Park-frequency error [MHz]",
    )
    axes[1].legend()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(f"Expected qick 0.2.133, found {qick.__version__}")

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import json_safe
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import q3_benchmark_settings
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import acquire_frequency_sweep_iq

    correction_path = fpd.find_latest_compensation_json(
        outerFolder,
        QUBIT,
        dc_offset=TARGET_GAIN,
        baseline_dc_offset=PARK_GAIN,
    )
    if correction_path is None:
        raise FileNotFoundError(
            "No matching q3 flux-tail compensation was found for the selected park and target gains"
        )
    compensation = fpd.load_compensation_json(correction_path)
    output = _output_directory(outerFolder)
    print(f"output={output}")
    print(f"correction={correction_path}")
    soc, soccfg = makeProxy()
    cfg_base = dict(BaseConfig)
    cfg_base.update(q3_benchmark_settings().opx_overrides())
    cfg_base.update({
        "ff_park_gain": PARK_GAIN,
        "opx_park_preroll_us": PARK_PREROLL_US,
        "reset_mode": "passive",
        "relax_delay": PASSIVE_REARM_US,
        "qua_passive_pre_point_delay_us": PASSIVE_REARM_US,
        "shots": SHOTS_PER_POINT,
        "reps": SHOTS_PER_POINT,
        "readout_after_park": True,
    })
    frequencies = np.arange(
        float(cfg_base["qubit_pi_freq"]) - FREQUENCY_HALF_SPAN_MHZ,
        float(cfg_base["qubit_pi_freq"]) + FREQUENCY_HALF_SPAN_MHZ
        + FREQUENCY_STEP_MHZ / 2.0,
        FREQUENCY_STEP_MHZ,
    )
    curves = []

    def acquire_curve(method, recovery_us, applied, do_excursion):
        cfg = dict(cfg_base)
        cfg["flux_tail_compensation"] = applied
        i_values, q_values, telemetry = acquire_frequency_sweep_iq(
            soc,
            soccfg,
            cfg,
            frequencies_mhz=frequencies,
            gain=int(cfg["qubit_pi_gain"]),
            pulses=1,
            shots=SHOTS_PER_POINT,
            pulse_placement=("park_after_excursion" if do_excursion else "park"),
            do_excursion=do_excursion,
            excursion_gain=(TARGET_GAIN if do_excursion else None),
            flux_hold_us=TARGET_HOLD_US,
            park_recovery_us=(0.0 if recovery_us is None else recovery_us),
            reset_scheme="none",
        )
        center, contrast, magnitude = _center(frequencies, i_values, q_values)
        curve = {
            "method": method,
            "recovery_us": recovery_us,
            "center_mhz": center,
            "contrast": contrast,
            "magnitude": magnitude,
            "telemetry": telemetry,
        }
        curves.append(curve)
        print(
            f"{method} recovery_us={recovery_us} center_mhz={center:.6f} "
            f"contrast={contrast:.6g}"
        )

    acquire_curve("park_raw", None, None, False)
    acquire_curve("park_predistorted", None, compensation, False)
    for recovery_us in RECOVERY_TIMES_US:
        acquire_curve("raw", recovery_us, None, True)
        acquire_curve("predistorted", recovery_us, compensation, True)

    reference_center = float(np.mean([
        curve["center_mhz"]
        for curve in curves
        if curve["method"].startswith("park_")
    ]))
    result = {
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_repo_root, text=True
        ).strip(),
        "correction_path": correction_path,
        "park_gain": PARK_GAIN,
        "target_gain": TARGET_GAIN,
        "target_hold_us": TARGET_HOLD_US,
        "park_preroll_us": PARK_PREROLL_US,
        "passive_rearm_us": PASSIVE_REARM_US,
        "shots_per_point": SHOTS_PER_POINT,
        "frequency_step_mhz": FREQUENCY_STEP_MHZ,
        "reference_center_mhz": reference_center,
        "curves": [
            {key: value for key, value in curve.items() if key != "magnitude"}
            for curve in curves
        ],
    }
    (output / "result.json").write_text(
        json.dumps(json_safe(result), indent=2, sort_keys=True) + "\n"
    )
    _write_csv(output / "spectroscopy.csv", frequencies, curves)
    _plot(output / "spectroscopy.png", frequencies, curves, reference_center)
    print(f"reference_center_mhz={reference_center:.6f}")
    for recovery_us in RECOVERY_TIMES_US:
        raw = next(
            curve for curve in curves
            if curve["method"] == "raw" and curve["recovery_us"] == recovery_us
        )
        corrected = next(
            curve for curve in curves
            if curve["method"] == "predistorted"
            and curve["recovery_us"] == recovery_us
        )
        print(
            f"recovery_us={recovery_us:g} "
            f"raw_error_mhz={raw['center_mhz'] - reference_center:+.6f} "
            f"predistorted_error_mhz={corrected['center_mhz'] - reference_center:+.6f}"
        )


if __name__ == "__main__":
    main()
