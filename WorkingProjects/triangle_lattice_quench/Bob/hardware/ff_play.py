"""FF play helpers, from triangle_lattice_quench/Helpers/FF_utils.py.

Changed: channels and per-channel delays are passed in (``prog.ff_channels``,
``prog.ff_t0``), not read from module globals or a crosstalk module that loads at import.
Waveforms are expected to be a whole number of clock cycles already (the backend pads
them at the end), so nothing here shifts timing by padding the front.
"""
from __future__ import annotations

import numpy as np

MIN_ARB_SAMPLES = 48  # QICK arb envelopes need at least 3 clock cycles


def add_ff_const(prog, label: str, gains, length_us: float, sign: float = 1.0) -> None:
    for j, ch in enumerate(prog.ff_channels):
        prog.add_pulse(ch=ch, name=f"{label}_{ch}", style="const", length=length_us,
                       freq=0, phase=0, gain=sign * float(gains[j]) / prog.ff_maxv)


def add_ff_arb(prog, label: str, waveforms) -> None:
    for j, ch in enumerate(prog.ff_channels):
        w = np.asarray(waveforms[j], float)
        if len(w) < MIN_ARB_SAMPLES:
            # only for very short waveforms: front-pad at the first level to meet the QICK minimum
            w = np.concatenate([np.full(MIN_ARB_SAMPLES - len(w), w[0] if len(w) else 0.0), w])
        if len(w) % 16:
            raise ValueError(f"FF waveform for channel {ch} is {len(w)} samples, not a multiple of 16")
        prog.add_envelope(ch=ch, name=f"{label}_{ch}", idata=np.clip(w, -prog.ff_maxv, prog.ff_maxv))
        prog.add_pulse(ch=ch, name=f"{label}_{ch}", style="arb", envelope=f"{label}_{ch}",
                       freq=0, phase=0, gain=1.0, outsel="input")


def play_ff(prog, label: str, t="auto") -> None:
    for j, ch in enumerate(prog.ff_channels):
        t_ = t if t == "auto" else t + prog.ff_t0[j]
        prog.pulse(ch=ch, name=f"{label}_{ch}", t=t_)


def play_ff_inverted(prog, label: str, t="auto") -> None:
    """Play an arb FF pulse with its gain negated, reusing the same waveform memory
    (FF_utils.FFInvertWaveforms). Used to DC-balance the flux lines after each shot."""
    for j, ch in enumerate(prog.ff_channels):
        name = f"{label}_{ch}"
        maxv = prog.soccfg["gens"][ch]["maxv"]
        for wname in prog.list_pulse_waveforms(name):
            prog.read_wmem(name=wname)
            prog.write_reg(dst="w_gain", src=-maxv)
            prog.write_wmem(name=wname)
            t_ = t if t == "auto" else t + prog.ff_t0[j]
            prog.pulse(ch=ch, name=name, t=t_)
            prog.read_wmem(name=wname)
            prog.write_reg(dst="w_gain", src=+maxv)
            prog.write_wmem(name=wname)
