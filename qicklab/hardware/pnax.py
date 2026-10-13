"""Keysight PNA-X (N52xx SCPI) S21 readout helpers for the TWPA scripts.

Setup and timing notes: docs/hardware.md#pna-x-at-gpib01616instr.
"""

import numpy as np


def measure_s21_band(pnax, n_avg):
    """Trigger a band sweep (n_avg averages) and return the full complex S21 trace."""
    if n_avg and int(n_avg) > 1:
        pnax.write("SENS:AVER:CLE")
        pnax.write(f"SENS:SWE:GRO:COUN {int(n_avg)}")
        pnax.write("SENS:SWE:MODE GRO")  # run n_avg sweeps, then hold
    else:
        pnax.write("SENS:SWE:MODE SING")
    pnax.query("*OPC?")
    raw = pnax.query("CALC:DATA? SDATA")
    vals = np.fromstring(raw, sep=",")
    if vals.size < 2 or vals.size % 2 != 0:
        raise RuntimeError(f"Unexpected SDATA payload from PNA-X: {vals.size} values")
    return vals[0::2] + 1j * vals[1::2]


def band_mean_dB(trace):
    """Mean |S21| in dB across a complex band trace (NaN-safe)."""
    mag = np.abs(trace)
    with np.errstate(divide="ignore"):
        return float(np.nanmean(20.0 * np.log10(mag)))
