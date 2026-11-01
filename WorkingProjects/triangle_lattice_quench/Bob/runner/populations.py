"""Single-shot readout to excited-state populations, with the lab's conventions.

The same steps as AveragerProgramFF.acquire_populations and Helpers/rotate_SS_data.py:

    1. rotate each shot's (I, Q) by the readout group's SingleShot ``angle`` (radians)
    2. a shot is excited when its rotated I is above ``threshold``
    3. the excited fraction is the raw population
    4. corrected population = row 1 of inv(confusion matrix) applied to (1 - P, P)

Pure numpy, so it can be checked without hardware (tests/test_populations.py compares it
against verbatim copies of the lab helpers).
"""
from __future__ import annotations

import numpy as np


def rotate(i, q, theta: float):
    """Rotate shots by ``theta`` radians (rotate_SS_data.rotate_data)."""
    i, q = np.asarray(i, float), np.asarray(q, float)
    return i * np.cos(theta) - q * np.sin(theta), i * np.sin(theta) + q * np.cos(theta)


def excited_fraction(i, q, angle: float, threshold: float) -> float:
    """Fraction of shots above threshold after rotation (rotate_SS_data.count_percentage)."""
    i_rot, _ = rotate(i, q, angle)
    return float(np.mean(i_rot > threshold))


def correct_population(p, confusion_matrix):
    """Remove readout error (rotate_SS_data.correct_occ). Works on a scalar or an array of P."""
    p = np.asarray(p, float)
    vec = np.vstack([1.0 - p.ravel(), p.ravel()])
    return (np.linalg.inv(np.asarray(confusion_matrix, float))[1, :] @ vec).reshape(p.shape)


def populations(shots_i: list, shots_q: list, cfg: dict) -> dict:
    """Per read-out qubit: raw population, and corrected population when the cfg has a confusion matrix.

    ``shots_i[k]``, ``shots_q[k]`` are the single shots of readout channel k; ``cfg`` holds the
    readout group's ``angle``, ``threshold`` and (optionally) ``confusion_matrix`` lists.
    """
    raw = np.array([excited_fraction(si, sq, cfg["angle"][k], cfg["threshold"][k])
                    for k, (si, sq) in enumerate(zip(shots_i, shots_q))])
    out = {"population": raw}
    if cfg.get("confusion_matrix") is not None:
        out["population_corrected"] = np.array([float(correct_population(raw[k], cfg["confusion_matrix"][k]))
                                                for k in range(len(raw))])
    return out
