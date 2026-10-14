"""Shared pyplot helpers for the run-level IQ scatter diagnostics."""

import matplotlib.pyplot as plt
import numpy as np


def iq_separator_geometry(raw_i, raw_q, midpoint, normal):
    """5 % padded IQ axis limits and the perpendicular bisector through `midpoint`.

    Returns (xlim, ylim, I_line, Q_line); Q_line is None when the bisector is vertical.
    """
    I_min, I_max = raw_i.min(), raw_i.max()
    Q_min, Q_max = raw_q.min(), raw_q.max()
    I_pad = 0.05 * (I_max - I_min if I_max > I_min else 1.0)
    Q_pad = 0.05 * (Q_max - Q_min if Q_max > Q_min else 1.0)
    I_line = np.linspace(I_min - I_pad, I_max + I_pad, 400)
    Q_line = None
    if not np.abs(normal[1]) < 1e-12:
        Q_line = midpoint[1] - (normal[0] / normal[1]) * (I_line - midpoint[0])
    return (I_min - I_pad, I_max + I_pad), (Q_min - Q_pad, Q_max + Q_pad), I_line, Q_line


def plot_separator(midpoint, I_line, Q_line):
    """Draw the bisector from `iq_separator_geometry` on the current axes."""
    if Q_line is None:
        plt.axvline(midpoint[0], linestyle="--", linewidth=2, label="Separator")
    else:
        plt.plot(I_line, Q_line, "--", linewidth=2, label="Separator")


def set_iq_limits(xlim, ylim):
    """Apply the IQ axis limits on the current axes with an equal aspect."""
    plt.xlim(*xlim)
    plt.ylim(*ylim)
    plt.gca().set_aspect("equal", adjustable="box")
