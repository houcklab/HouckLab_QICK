from datetime import datetime
import json
from pathlib import Path
import sys
import time

import numpy as np


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


QUBIT = "q3"
SHOTS = 300
FREQUENCY_HALF_SPAN_MHZ = 1.5
FREQUENCY_STEP_MHZ = 0.1
SPEC_GAIN = 15000
SPEC_LENGTH_US = 1.0
METHODS = (
    "passive_1000",
    "compact_1000",
    "compact_10",
    "active_10",
)


def _method_config(method):
    values = {
        "passive_1000": ("passive", "none", 1000.0),
        "compact_1000": ("compact", "none", 1000.0),
        "compact_10": ("compact", "none", 10.0),
        "active_10": ("compact", "opx_unbounded", 10.0),
    }
    try:
        return values[str(method)]
    except KeyError as exc:
        raise ValueError(f"unknown qubit spectroscopy method {method!r}") from exc


def _output_directory(outer_folder):
    now = datetime.now()
    output = (
        Path(outer_folder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_qubit_spec_lifecycle"
    )
    output.mkdir(parents=True, exist_ok=False)
    return output


def _normalized(values):
    array = np.asarray(values, dtype=float)
    scale = float(np.std(array))
    if not np.isfinite(scale) or scale == 0.0:
        return np.zeros_like(array)
    return (array - float(np.mean(array))) / scale


def _metrics(frequencies, signal, feature_frequency, elapsed_s, telemetry):
    magnitude = np.abs(signal)
    phase = np.unwrap(np.angle(signal))
    return {
        "feature_frequency_mhz": float(feature_frequency),
        "magnitude_max_frequency_mhz": float(frequencies[np.argmax(magnitude)]),
        "magnitude_min_frequency_mhz": float(frequencies[np.argmin(magnitude)]),
        "magnitude_span": float(np.ptp(magnitude)),
        "phase_span_rad": float(np.ptp(phase)),
        "elapsed_s": float(elapsed_s),
        "telemetry": telemetry,
    }


def main():
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
        BaseConfig,
        outerFolder,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitSpec import (
        _feature_freq,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
        json_safe,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        acquire_pulse_grid_iq,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
        prepare_reset_session,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order import (
        acquire_passive_pulse_grid,
    )

    output_dir = _output_directory(outerFolder)
    print(f"output={output_dir}")
    soc, soccfg = makeProxy()
    active_session = prepare_reset_session(
        "active",
        outer_folder=outerFolder,
        qubit=QUBIT,
        base_cfg=BaseConfig,
        soc=soc,
        soccfg=soccfg,
        purpose="qubit_spec_lifecycle",
    )
    center = float(BaseConfig["qubit_pi_freq"])
    frequencies = np.arange(
        center - FREQUENCY_HALF_SPAN_MHZ,
        center + FREQUENCY_HALF_SPAN_MHZ + FREQUENCY_STEP_MHZ / 2.0,
        FREQUENCY_STEP_MHZ,
    )
    common = dict(BaseConfig)
    common.update({
        "shots": int(SHOTS),
        "reps": int(SHOTS),
        "qubit_pulse_style": "const",
        "qubit_gain": int(SPEC_GAIN),
        "qubit_length": float(SPEC_LENGTH_US),
        "ff_hold_gain": 0,
        "readout_after_park": True,
    })
    signals = {}
    metrics = {}
    raw = {"frequencies_mhz": frequencies}
    for method in METHODS:
        engine, reset_scheme, delay_us = _method_config(method)
        if engine == "passive":
            cfg = ProductionResetSession.passive().apply(common)
            cfg["relax_delay"] = float(delay_us)
            started = time.perf_counter()
            i_values, q_values, telemetry = acquire_passive_pulse_grid(
                soc,
                soccfg,
                cfg,
                frequencies_mhz=frequencies,
                gains=[SPEC_GAIN],
                pulses=1,
                progress=True,
            )
        else:
            cfg = active_session.apply(common)
            cfg["relax_delay"] = float(delay_us)
            cfg["opx_inter_shot_delay_us"] = float(delay_us)
            started = time.perf_counter()
            i_values, q_values, telemetry = acquire_pulse_grid_iq(
                soc,
                soccfg,
                cfg,
                frequencies_mhz=frequencies,
                gains=[SPEC_GAIN],
                pulses=1,
                shots=SHOTS,
                pulse_placement="park",
                reset_scheme=reset_scheme,
            )
        elapsed_s = time.perf_counter() - started
        signal = np.mean(i_values[:, 0, :] + 1j * q_values[:, 0, :], axis=1)
        feature = _feature_freq(frequencies, np.abs(signal))
        signals[method] = signal
        metrics[method] = _metrics(
            frequencies,
            signal,
            feature,
            elapsed_s,
            telemetry,
        )
        raw[f"{method}_i"] = i_values
        raw[f"{method}_q"] = q_values
    reference = _normalized(np.abs(signals["passive_1000"]))
    for method in METHODS:
        metrics[method]["magnitude_correlation_to_passive"] = float(
            np.corrcoef(reference, _normalized(np.abs(signals[method])))[0, 1]
        )
        metrics[method]["feature_delta_from_passive_mhz"] = float(
            metrics[method]["feature_frequency_mhz"]
            - metrics["passive_1000"]["feature_frequency_mhz"]
        )
    summary = {
        "qubit": QUBIT,
        "shots": int(SHOTS),
        "frequency_points": int(frequencies.size),
        "frequency_step_mhz": float(FREQUENCY_STEP_MHZ),
        "spec_gain": int(SPEC_GAIN),
        "spec_length_us": float(SPEC_LENGTH_US),
        "park_gain_dac": int(BaseConfig.get("ff_park_gain", 0)),
        "calibration_output": str(active_session.calibration_output),
        "methods": metrics,
    }
    (output_dir / "result.json").write_text(
        json.dumps(json_safe(summary), indent=2, sort_keys=True) + "\n"
    )
    np.savez_compressed(output_dir / "raw.npz", **raw)
    fig, axes = plt.subplots(2, 1, figsize=(9, 8), sharex=True)
    for method in METHODS:
        signal = signals[method]
        axes[0].plot(frequencies, _normalized(np.abs(signal)), ".-", label=method)
        axes[1].plot(frequencies, np.unwrap(np.angle(signal)), ".-", label=method)
    axes[0].set_ylabel("Normalized |IQ|")
    axes[0].legend()
    axes[1].set_xlabel("Qubit frequency [MHz]")
    axes[1].set_ylabel("Phase [rad]")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(output_dir / "comparison.png", dpi=180)
    plt.close(fig)
    print(json.dumps(json_safe(summary), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
