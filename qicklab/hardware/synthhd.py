"""Windfreak SynthHD (dual-channel) TWPA pump helpers; needs the optional ``pywindfreak``.

Connect/close side effects: docs/hardware.md#pump-windfreak-synthhd-on-com5.
"""

from pywindfreak import SynthHD

__all__ = ["SynthHD", "set_pump_channels"]


def set_pump_channels(channels, freq_hz, power_dbm, rf_enable):
    """Program every pump channel identically (freq, power, RF on/off)."""
    for ch in channels:
        ch.frequency = float(freq_hz)
        ch.power = float(power_dbm)
        ch.rf_enable = bool(rf_enable)
