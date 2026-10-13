"""Config helpers: sanity dump and the single-shot config rebuild."""

from qicklab.hardware.board import BaseConfig, FF_Qubits


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
