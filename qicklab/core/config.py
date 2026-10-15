"""Config helpers: sanity dump, the drive-gain guard and the single-shot config rebuild."""

import math
import numbers

import numpy as np

from qicklab.hardware.board import BaseConfig, FF_Qubits

# The tProc v1 gain register is signed 16 bit. qick 0.2.334 compiles larger values without
# complaint and the DAC plays them wrapped (40000 -> -25536: phase-flipped, wrong amplitude).
GAIN_MAX = 2**15 - 1

# Drive gains played on res_ch / qubit_ch (0..GAIN_MAX), and the gain-sweep endpoints that
# become one of them per point. Fast-flux gains are not drive gains and are never checked.
DRIVE_GAIN_KEYS = (
    "pulse_gain",
    "qubit_gain",
    "pi_gain",
    "pi2_gain",
    "qubit_gains",
    "gain_start",
    "gain_end",
    "cav_gain_Start",
    "cav_gain_Stop",
    "qubit_gain_Start",
    "qubit_gain_Stop",
)


def check_gain(name, value, limit=GAIN_MAX):
    """Raise ValueError if the drive gain `value` (a number or a sequence of them) lies outside 0..limit.

    None, NaN and non-numbers are left to the code that uses them. See
    docs/concepts/timing_and_units.md#gains.
    """
    if isinstance(value, (list, tuple, np.ndarray)):
        values = np.ravel(np.asarray(value, dtype=object))
    else:
        values = [value]
    for v in values:
        if isinstance(v, bool) or not isinstance(v, numbers.Real) or math.isnan(v):
            continue
        if not 0 <= v <= limit:
            hint = ""
            if math.isfinite(v) and v > limit:
                wrapped = (int(v) + 2**15) % 2**16 - 2**15
                hint = f" (the 16-bit gain register would play it as {wrapped})"
            raise ValueError(
                f"{name} = {v} is outside the DAC gain range 0..{limit}{hint}; "
                f"qick does not check gains, so fix {name}."
            )


def validate_gains(cfg, sweep_keys=None, where="cfg"):
    """Raise ValueError if a drive gain of `cfg` (DRIVE_GAIN_KEYS) or a gain sweep endpoint is out of range.

    `sweep_keys` = (start, step, expts) names a tProc register sweep over the drive gain: its
    first point and its last point start + step * (expts - 1) are checked. Reads a plain copy
    of `cfg`.
    """
    if not isinstance(cfg, dict):
        return
    flat = dict(cfg)
    for key in DRIVE_GAIN_KEYS:
        if key in flat:
            check_gain(f"{where}['{key}']", flat[key])
    if sweep_keys is not None:
        start_key, step_key, expts_key = sweep_keys
        start, step, expts = (flat.get(k) for k in sweep_keys)
        if start is None or step is None or expts is None:
            return
        check_gain(f"{where}['{start_key}'] (first sweep point)", start)
        check_gain(
            f"{where}['{start_key}'] + {where}['{step_key}'] * ({where}['{expts_key}'] - 1) "
            f"(last sweep point)",
            start + step * (int(expts) - 1),
        )


def sanity_dump(cfg, tag=""):
    """Print the spectroscopy/readout keys of `cfg` that are present, headed by `tag`."""
    keys = [
        "pulse_freq",
        "qubit_freq",
        "SpecSpan",
        "SpecNumPoints",
        "step",
        "start",
        "qubit_pulse_style",
        "qubit_length",
        "qubit_gain",
        "pulse_gain",
        "readout_length",
        "cavity_min",
    ]
    print(f"\n--- Sanity {tag} ---")
    for k in keys:
        if k in cfg:
            print(f"{k:>18}: {cfg[k]}")
    for k in ["cavity_LO", "qubit_LO", "cavity_IF", "qubit_IF", "read_lo", "drive_lo"]:
        if k in cfg:
            print(f"{k:>18}: {cfg[k]}")
    print("-------------------\n")


def rebuild_singleshot_config(ctx, SS_params):
    """Replace ctx.config with the regime-B (single-shot) config, built from BaseConfig.

    Drops regime-A carry-overs; see docs/concepts/config_regimes.md#what-changes-at-the-switch-a---b.
    """
    qubit_gains = [
        ctx.Qubit_Parameters[str(Q_R)]["Qubit"]["Gain"] for Q_R in SS_params["Qubit_Pulse"]
    ]
    qubit_frequency_centers = [
        ctx.Qubit_Parameters[str(Q_R)]["Qubit"]["Frequency"] for Q_R in SS_params["Qubit_Pulse"]
    ]

    UpdateConfig = {
        "read_pulse_style": "const",
        # tone starts at t=0, ADC at ADC_Offset: tone covers both (docs/concepts/readout_window.md)
        "length": SS_params["ADC_Offset"] + SS_params["Readout_Time"],
        "readout_length": SS_params["Readout_Time"],  # us (ADC integration window)
        "adc_trig_offset": SS_params["ADC_Offset"],
        "pi2_SS": SS_params["pi2_SS"],
        "pulse_gain": ctx.cavity_gain,  # [DAC units]
        "pulse_freq": ctx.resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
        "qubit_pulse_style": "arb",
        "sigma": ctx.qubit_sigma,  # us
        "qubit_gain": ctx.qubit_gain,
        "f_ge": ctx.qubit_frequency_center,
        "qubit_gains": qubit_gains,
        "f_ges": qubit_frequency_centers,
        "shots": SS_params["Shots"],  # programs set reps = shots
        "relax_delay": SS_params["relax_delay"],  # us
        "flattop_length": ctx.qubit_flattop,
    }

    config = BaseConfig | UpdateConfig
    config["FF_Qubits"] = FF_Qubits
    config["Read_Indeces"] = ctx.Qubit_Readout
    ctx.config = config
