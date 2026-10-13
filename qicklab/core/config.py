"""Config helpers: sanity dump and the single-shot config rebuild."""

from qicklab.hardware.board import BaseConfig, FF_Qubits


def sanity_dump(cfg, tag=""):
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
    # If BaseConfig stores LOs/IFs/NCOs, print them too:
    for k in ["cavity_LO", "qubit_LO", "cavity_IF", "qubit_IF", "read_lo", "drive_lo"]:
        if k in cfg:
            print(f"{k:>18}: {cfg[k]}")
    print("-------------------\n")


def rebuild_singleshot_config(ctx, SS_params):
    """Switch ctx.config into the single-shot regime.

    Reproduces the unconditional top-level `config` rebuild the original script
    performed AFTER the RunActiveResetVerify block (old CSTQ03_BFC.py lines
    2834-2835 + 2990-3016). The original ran a second `config = BaseConfig |
    UpdateConfig` here so every block below it (SingleShot, T1SS, readout/qubit
    optimize, AutoCoherence, ZeroSpanParity) executed under this config, not the
    one used by the transmission/spec/Ramsey/coherence blocks above. The client
    calls this once, at that same point in the run order.
    """
    qubit_gains = [
        ctx.Qubit_Parameters[str(Q_R)]["Qubit"]["Gain"] for Q_R in SS_params["Qubit_Pulse"]
    ]
    qubit_frequency_centers = [
        ctx.Qubit_Parameters[str(Q_R)]["Qubit"]["Frequency"] for Q_R in SS_params["Qubit_Pulse"]
    ]

    UpdateConfig = {
        ###### cavity
        # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
        "read_pulse_style": "const",  # --Fixed
        # The resonator tone starts at t=0; ADC integration starts ADC_Offset
        # later, so the tone must cover offset + the full integration window.
        "length": SS_params["ADC_Offset"] + SS_params["Readout_Time"],
        "readout_length": SS_params["Readout_Time"],  # us (ADC integration window)
        "adc_trig_offset": SS_params["ADC_Offset"],
        "pi2_SS": SS_params["pi2_SS"],
        # "pulse_gain": cavity_gain, # [DAC units]
        "pulse_gain": ctx.cavity_gain,  # [DAC units]
        "pulse_freq": ctx.resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
        ##### qubit spec parameters
        "qubit_pulse_style": "arb",
        "sigma": ctx.qubit_sigma,  ### units us, define a 20ns sigma
        "qubit_gain": ctx.qubit_gain,
        "f_ge": ctx.qubit_frequency_center,
        "qubit_gains": qubit_gains,
        "f_ges": qubit_frequency_centers,
        ##### define shots
        "shots": SS_params["Shots"],  ### this gets turned into "reps"
        "relax_delay": SS_params["relax_delay"],  # us
        "flattop_length": ctx.qubit_flattop,
    }

    config = BaseConfig | UpdateConfig
    config["FF_Qubits"] = FF_Qubits
    config["Read_Indeces"] = ctx.Qubit_Readout
    ctx.config = config
