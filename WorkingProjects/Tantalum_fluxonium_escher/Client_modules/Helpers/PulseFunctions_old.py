###
# This file contains commonly-used functions for defining pulses, to avoid repeating the same code all the time.
# Lev, May 11, 2025: create file, add the standard qubit pulse arb/flat_top/const function
###
from qick.asm_v1 import AcquireProgram
import numpy as np


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
        mode_setting = "periodic" if ("qubit_mode_periodic" in prog.cfg.keys() and prog.cfg["qubit_mode_periodic"]) else "oneshot"
        prog.set_pulse_registers(ch=prog.cfg["qubit_ch"], style="const", freq=freq_reg, phase=0,
                                 gain=prog.cfg["qubit_gain"], length=length_reg, mode=mode_setting)
        pulse_length = prog.cfg["qubit_length"]  # [us]
    else:
        raise ValueError("cfg[\"qubit_pulse_style\"] must be one of \"arb\", \"const\", or \"flat_top\"; received \"" +
                         prog.cfg["qubit_pulse_style"] + "\" instead.")

    return pulse_length

def create_ff_ramp(prog: AcquireProgram, ramp_start: int, ramp_stop: int, pulse_name: str):
    """
    This function takes a program prog with a defined configuration dictionary prog.cfg, and sets up creates a fast flux
    ramp pulse. For now, the only type of pulse supported is "linear". The pulse is DC, and goes from
    ramp_start to ramp_stop in ff_ramp_length time.

    :param prog: AcquireProgram: the program object
    :param ramp_start: int: Starting value of ramp, in DAC units
    :param ramp_stop: int: Ending value of ramp, in DAC units
    :param pulse_name: str: name of pulse to use
    """
    # TODO decide whether it's better to pass parameters instead of taking them from the cfg file

    style = prog.cfg["ff_ramp_style"]
    if style != "linear":
        raise ValueError("cfg[\"ff_ramp_style_\"] must be \"linear\"; received \"" + prog.cfg["ff_ramp_style"] + "\" instead.")

    if np.max([np.abs(ramp_start), np.abs(ramp_stop)]) > prog.soccfg['gens'][0]['maxv']:
        raise ValueError("ramp_start and ramp_stop must not exceed max value in magnitude.")

    length = prog.us2cycles(prog.cfg["ff_ramp_length"], gen_ch = prog.cfg["ff_ch"])
    if length < 3: # If we start wanting to make pulses shorter than 3 clock cycles ~7 ns, we can pad with zeros
        raise ValueError("Pulse shorter than 3 clock cycles disallowed!")

    # The 16 comes from the difference between the channel resolution and the fabric clock rate.
    # e.g.: print(soccfg) shows
    # 	6:	axis_signal_gen_v6 - envelope memory 65536 samples (9.524 us)
    # 		fs=6881.280 MHz, fabric=430.080 MHz, 32-bit DDS, range=6881.280 MHz
    # 		DAC tile 3, blk 2 is 2_231, on JHC3
    # fs is around 16x larger than fabric. I do NOT fully understand why it's not EXACTLY 16.
    idata = np.linspace(start = ramp_start, stop = ramp_stop, num = length * 16)
    qdata = np.zeros(length * 16)

    # TODO figure out how does i and q work for DC signals and for arb with gain

    prog.add_pulse(ch=prog.cfg["ff_ch"], name=pulse_name, idata = idata, qdata = qdata)

    #TODO consider getting rid of this, probably bad for defining ramps up and down

    # Gain here is multiplied by the i/q values, so we set the gain to max value (32766) and control it with i/q instead
    prog.set_pulse_registers(ch=prog.cfg["ff_ch"], freq=0, style='arb',
                             phase=0, gain = prog.soccfg['gens'][0]['maxv'],
                             waveform="ramp", outsel="input",
                             # mode = "periodic",
                             )