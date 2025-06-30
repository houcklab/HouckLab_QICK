###
# This file contains commonly-used functions for defining pulses, to avoid repeating the same code all the time.
# Lev, May 11, 2025: create file, add the standard qubit pulse arb/flat_top/const function
###
from qick.asm_v1 import AcquireProgram


def create_qubit_pulse(prog: AcquireProgram, freq: float) -> float:
    """
    This function takes a program prog with a defined configuration dictionary prog.cfg, and sets up pulse registers
    for the qubit pulse, which can be "arb", "flat_top", or "const".

    :param prog: AcquireProgram: the program object
    :param freq: float:          the frequency of the desired qubit drive [MHz]
    :return pulse_length: float: the length of the generated qubit pulse [us]

    The envelopes are defined by prog.cfg["qubit_pulse_style"] as follows:
        "arb" is a Gaussian with standard deviation prog.cfg["sigma"] and total length 4*sigma
        "flat_top" is a Gaussian with standard deviation prog.cfg["sigma"], with a constant of length
            prog.cfg["flat_top_length"] inserted in the middle
        "const" is constant, for length prog.cfg["qubit_length"]
            If prog.cfg["qubit_mode_periodic"] is set to True and "const" is chosen, the qubit tone is always on.

    Note that this function has no side effects on prog.cfg: you must update the pulse_length manually.
    Also note that it uses the given freq argument and does not assume it to be prog.cfg["start"].
    """

    # Variables for convenience
    freq_reg = prog.freq2reg(freq, gen_ch=prog.cfg["qubit_ch"])
    sigma_reg = prog.us2cycles(prog.cfg["sigma"], gen_ch=prog.cfg["qubit_ch"])
    length_reg = prog.us2cycles(prog.cfg["qubit_length"], gen_ch=prog.cfg["qubit_ch"])

    # Add the pulse
    # Gaussian
    if prog.cfg["qubit_pulse_style"] == "arb":
        prog.add_gauss(ch=prog.cfg["qubit_ch"], name="qubit", sigma=sigma_reg, length=sigma_reg * 4)
        prog.set_pulse_registers(ch=prog.cfg["qubit_ch"], style=prog.cfg["qubit_pulse_style"], freq=freq_reg,
                                 phase=prog.deg2reg(0, gen_ch=prog.cfg["qubit_ch"]), gain=prog.cfg["qubit_gain"],
                                 waveform="qubit")
        pulse_length = prog.cfg["sigma"] * 4  # [us]
    # Flat-top
    elif prog.cfg["qubit_pulse_style"] == "flat_top":
        prog.add_gauss(ch=prog.cfg["qubit_ch"], name="qubit", sigma=sigma_reg, length=sigma_reg * 4)
        prog.set_pulse_registers(ch=prog.cfg["qubit_ch"], style=prog.cfg["qubit_pulse_style"], freq=freq_reg,
                                 phase=prog.deg2reg(0, gen_ch=prog.cfg["qubit_ch"]), gain=prog.cfg["qubit_gain"],
                                 waveform="qubit", length=prog.us2cycles(prog.cfg["flat_top_length"]))
        pulse_length = prog.cfg["sigma"] * 4 + prog.cfg["flat_top_length"]  # [us]
    # Constant
    elif prog.cfg["qubit_pulse_style"] == "const":
        mode_setting = "periodic" if prog.cfg["qubit_mode_periodic"] else "oneshot"
        prog.set_pulse_registers(ch=prog.cfg["qubit_ch"], style="const", freq=freq_reg, phase=0,
                                 gain=prog.cfg["qubit_gain"], length=length_reg, mode=mode_setting)
        pulse_length = prog.cfg["qubit_length"]  # [us]
    else:
        raise ValueError("cfg[\"qubit_pulse_style\"] must be one of \"arb\", \"const\", or \"flat_top\"; received \"" +
                         prog.cfg["qubit_pulse_style"] + "\" instead.")

    return pulse_length