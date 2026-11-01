"""Ramp shapes, from triangle_lattice_quench/Helpers/RampHelpers.py.

Rewritten as one function of the ramp fraction so every shape starts and ends exactly
where asked. Shapes match the originals:

    linear       straight line
    cubic        RampHelpers.generate_cubic_ramp (reverse=False): fast start, flat finish
    exponential  RampHelpers.generate_exp_ramp (tau factor 4)
"""
from __future__ import annotations

import numpy as np

SHAPES = ("linear", "cubic", "exponential")


def ramp_fraction(u: np.ndarray, shape: str) -> np.ndarray:
    u = np.clip(np.asarray(u, float), 0.0, 1.0)
    s = shape.lower()
    if s == "linear":
        return u
    if s == "cubic":
        return 1.0 - (1.0 - u) ** 3
    if s == "exponential":
        k = 4.0
        return (np.exp(-k * u) - 1.0) / (np.exp(-k) - 1.0)
    raise ValueError(f"unknown ramp shape {shape!r}; expected one of {SHAPES}")


def ramp(start: float, end: float, n_samples: int, shape: str = "cubic") -> np.ndarray:
    """n_samples values going from just after ``start`` to exactly ``end``."""
    n = int(n_samples)
    if n <= 0:
        return np.zeros(0)
    u = np.arange(1, n + 1) / n
    return start + (end - start) * ramp_fraction(u, shape)
