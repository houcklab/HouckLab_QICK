###
# This file contains commonly-used functions for defining pulses, to avoid repeating the same code all the time.
# Lev, May 11, 2025: create file, add the standard qubit pulse arb/flat_top/const function
###
from qick.asm_v1 import AcquireProgram
import numpy as np
from dataclasses import dataclass
import matplotlib.pyplot as plt
from typing import List, Tuple, Optional, Sequence

def _ensure_1d(a: Sequence[float]) -> np.ndarray:
    a = np.asarray(a, dtype=float).ravel()
    return a

# --------------- Pulse primitives -----------------

@dataclass
class Trapezoid:
    """A single trapezoid pulse.
    start:   start time (s)
    rise:    rise time (s)
    flat:    flat top duration (s)
    fall:    fall time (s)
    amp:     amplitude (arb)
    offset:  vertical offset added to the pulse (arb), default 0
    """
    start: float
    rise: float
    flat: float
    fall: float
    amp: float
    offset: float = 0.0

    def sample(self, t: np.ndarray) -> np.ndarray:
        """Sample the trapezoid at times t (seconds)."""
        y = np.zeros_like(t, dtype=float) + self.offset
        t0 = self.start
        t1 = t0 + self.rise
        t2 = t1 + self.flat
        t3 = t2 + self.fall

        # Rising edge
        m_rise = self.amp / max(self.rise, 1e-30)
        mask = (t >= t0) & (t < t1)
        y[mask] += m_rise * (t[mask] - t0)

        # Flat
        mask = (t >= t1) & (t < t2)
        y[mask] += self.amp

        # Falling edge
        m_fall = -self.amp / max(self.fall, 1e-30)
        mask = (t >= t2) & (t < t3)
        y[mask] += self.amp + m_fall * (t[mask] - t2)

        # After
        mask = (t >= t3)
        y[mask] += 0.0
        return y


class PulseBuilder:
    """Build and visualize arbitrary sums of trapezoid pulses."""
    def __init__(self, dt: float, T: float):
        """
        dt: sample period (s)
        T:  total record length (s)
        """
        self.dt = float(dt)
        self.T = float(T)
        self.t = np.arange(0.0, T, dt)
        self._pulses: List[Trapezoid] = []

    def add_trapezoid(self, start: float, rise: float, flat: float, fall: float, amp: float, offset: float = 0.0):
        self._pulses.append(Trapezoid(start, rise, flat, fall, amp, offset))

    def add_train(self, start: float, rise: float, flat: float, fall: float, amp: float, period: float, count: int, offset: float = 0.0):
        t0 = start
        for _ in range(count):
            self.add_trapezoid(t0, rise, flat, fall, amp, offset)
            t0 += period

    def waveform(self) -> np.ndarray:
        """Sum all pulses to produce the total waveform."""
        y = np.zeros_like(self.t, dtype=float)
        for p in self._pulses:
            y += p.sample(self.t)
        return y

    def plot(self, y: Optional[np.ndarray] = None, title: str = "Ideal waveform"):
        if y is None:
            y = self.waveform()
        plt.figure()
        plt.plot(self.t * 1e6, y, label="waveform")
        plt.xlabel("Time [µs]")
        plt.ylabel("Amplitude [arb]")
        plt.title(title)
        plt.legend()
        plt.show()


@dataclass
class TwoTailParams:
    A1: float
    tau1: float
    A2: float
    tau2: float
class SimpleTwoTailDistortion:
    """Two-tail line model using a single parameter set."""
    def __init__(self, A1: float, tau1: float, A2: float, tau2: float, x_val: float):
        self.params = TwoTailParams(A1=A1, tau1=tau1, A2=A2, tau2=tau2)
        self.dt = float(x_val)

    def simulate(self, x: np.ndarray) -> np.ndarray:
        """Apply two-tail distortion using the configured parameters."""
        p = self.params
        y = self._single_tail_forward(self._single_tail_forward(x, p.A1, p.tau1),
                                      p.A2, p.tau2)
        return y

    def _single_tail_forward(self, x: np.ndarray, A: float, tau: float) -> np.ndarray:
        alpha = tau / self.dt
        y = np.zeros_like(x, dtype=float)
        y[0] = x[0]
        for k in range(1, len(x)):
            num = x[k] + (1.0 + A)*alpha*(x[k] - x[k-1]) + alpha*y[k-1]
            den = alpha + 1.0
            y[k] = num / den
        return y

    def predistort(self, d: np.ndarray) -> np.ndarray:
        """Compute predistorted drive using the configured parameter set."""
        p = self.params
        x1 = self._single_tail_inverse(d, p.A2, p.tau2)
        x = self._single_tail_inverse(x1, p.A1, p.tau1)
        return x

    def _single_tail_inverse(self, d: np.ndarray, A: float, tau: float) -> np.ndarray:
        alpha = tau / self.dt
        x = np.zeros_like(d, dtype=float)
        x[0] = d[0]
        den = (1.0 + A)*alpha + 1.0
        for k in range(1, len(d)):
            num = (1.0 + A)*alpha*x[k-1] + d[k] + alpha*(d[k] - d[k-1])
            x[k] = num / den
        return x


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

def create_ff_ramp(prog: AcquireProgram, reversed: bool, name = None ) -> None:
    """
    This function takes a program prog with a defined configuration dictionary prog.cfg, and sets up creates a fast flux
    ramp pulse. For now, the only type of pulse supported is "linear". The pulse is DC, and goes from
    ff_ramp_start to ff_ramp_stop in ff_ramp_length time.

    :param prog: AcquireProgram: the program object
    :param reversed: bool: Make a reversed version of the ramp instead
    :param name: str: Name of the pulse. If None, use "ramp" or "ramp_reversed"
    """
    # TODO decide whether it's better to pass parameters instead of taking them from the cfg file

    style = prog.cfg["ff_ramp_style"]
    if style != "linear":
        raise ValueError("cfg[\"ff_ramp_style_\"] must be \"linear\"; received \"" + prog.cfg["ff_ramp_style"] + "\" instead.")

    if "ff_ramp_start" in prog.cfg or 'ff_ramp_stop' in prog.cfg :
        if np.max([np.abs(prog.cfg["ff_ramp_start"]), np.abs(prog.cfg["ff_ramp_stop"])]) > prog.soccfg['gens'][0]['maxv']:
            raise ValueError("cfg[\"ffr_ramp_start\"] and cfg[\"ff_ramp_stop\"] must not exceed max value in magnitude.")

    length = prog.us2cycles(prog.cfg["ff_ramp_length"], gen_ch = prog.cfg["ff_ch"])
    if length < 3: # If we start wanting to make pulses shorter than 3 clock cycles ~7 ns, we can pad with zeros
        raise ValueError("Pulse shorter than 3 clock cycles disallowed! Current length: " + str(length) + " cycles.")

    # The 16 comes from the difference between the channel resolution and the fabric clock rate.
    # e.g.: print(soccfg) shows
    # 	6:	axis_signal_gen_v6 - envelope memory 65536 samples (9.524 us)
    # 		fs=6881.280 MHz, fabric=430.080 MHz, 32-bit DDS, range=6881.280 MHz
    # 		DAC tile 3, blk 2 is 2_231, on JHC3
    # fs is around 16x larger than fabric. I do NOT fully understand why it's not EXACTLY 16.
    if reversed:
        idata = np.linspace(start=prog.cfg["ff_ramp_stop"], stop=prog.cfg["ff_ramp_start"], num=length * 16)
    else:
        idata = np.linspace(start = prog.cfg["ff_ramp_start"], stop = prog.cfg["ff_ramp_stop"], num = length * 16)
    qdata = np.zeros(length * 16)
    # print(f"idata = {idata}")
    # TODO figure out how does i and q work for DC signals and for arb with gain

    if reversed:
        if name is None:
            name = "ramp_reversed"

        prog.add_pulse(ch=prog.cfg["ff_ch"], name=name, idata=idata, qdata=qdata)

        # Gain here is multiplied by the i/q values, so we set the gain to max value (32766) and control it with i/q instead
        prog.set_pulse_registers(ch=prog.cfg["ff_ch"], freq=0, style='arb',
                                 phase=0, gain = prog.soccfg['gens'][0]['maxv'],
                                 waveform=name, outsel="input",
                                 # mode = "periodic",
                                 )
    else:
        if name is None:
            name = "ramp"
        prog.add_pulse(ch=prog.cfg["ff_ch"], name=name, idata = idata, qdata = qdata)

        # Gain here is multiplied by the i/q values, so we set the gain to max value (32766) and control it with i/q instead
        prog.set_pulse_registers(ch=prog.cfg["ff_ch"], freq=0, style='arb',
                                 phase=0, gain = prog.soccfg['gens'][0]['maxv'],
                                 waveform=name, outsel="input",
                                 # mode = "periodic",
                                 )