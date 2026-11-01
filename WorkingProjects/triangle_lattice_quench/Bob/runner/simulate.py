"""A simulated board: runs a sequence end to end without an RFSoC.

Stands in for BobProgram and returns single shots in the same form the board does (one I and
one Q array per read-out qubit, reps × rounds shots each), so everything after the board is
exercised for real: populations, the readout correction, saving point by point, Stop, the
Data tab and the plots.

What it does NOT check: that QICK can assemble Bob's program. That needs the board's config
(soccfg), and is the next step once one is saved.

The data is made up and clearly so:

    excited probability   0.5 + 0.42 · exp(-1.3 x) · cos(2π · 1.6 x + π y + 0.35 r)
                          x = position along the innermost sweep axis (0 to 1), y = the mean
                          position along the outer axes, r = which read-out qubit
    readout error         a true |g> reads as e with probability ng_contrast, a true |e> as g with
                          probability ne_contrast (the readout group's SingleShot values)
    I/Q                   two Gaussian clouds either side of the SingleShot threshold, rotated by
                          the SingleShot angle the other way, so the lab's analysis undoes it

Runs made this way are labelled simulated everywhere (file, plots, run bar) and saved under
``<save folder>/_simulated`` so they can't be mistaken for measurements.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

SIMULATED_SUBFOLDER = "_simulated"


class SimulatedBoard:
    """What ``connect`` returns, as both the board and its config, for a simulated run. It has
    no ``dump_cfg``: there is no board config to save."""
    simulated = True


def simulated_connect(station):
    board = SimulatedBoard()
    return board, board


def excited_probability(r: int, point: Optional[dict]) -> float:
    """The made-up signal: a decaying oscillation along the innermost axis, shifted by the outer ones."""
    if not point or not point.get("shape"):
        return float(np.clip(0.5 + 0.3 * np.cos(0.35 * r), 0.02, 0.98))
    shape = [max(1, int(n)) for n in point["shape"]]
    idx = np.unravel_index(int(point["index"]), shape)
    frac = [i / (n - 1) if n > 1 else 0.0 for i, n in zip(idx, shape)]
    x = frac[-1]
    y = float(np.mean(frac[:-1])) if len(frac) > 1 else 0.0
    p = 0.5 + 0.42 * np.exp(-1.3 * x) * np.cos(2 * np.pi * 1.6 * x + np.pi * y + 0.35 * r)
    return float(np.clip(p, 0.0, 1.0))


class SimulatedProgram:
    """Same constructor and acquire methods as BobProgram; shots instead of a QICK program."""

    def __init__(self, soccfg, reps, final_delay, cfg, seed: Optional[int] = None):
        self.cfg, self.reps = cfg, int(reps)
        point = cfg.get("bob_point") or {}
        self.rng = np.random.default_rng(seed if seed is not None else cfg.get("bob_simulation_seed"))
        self.point = point

    def _readout(self, k: int):
        cfg = self.cfg
        angle = float((cfg.get("angle") or [0.0] * (k + 1))[k])
        threshold = float((cfg.get("threshold") or [0.0] * (k + 1))[k])
        cm = cfg.get("confusion_matrix")
        ng, ne = (float(cm[k][1][0]), float(cm[k][0][1])) if cm else (0.03, 0.06)
        return angle, threshold, ng, ne

    def acquire_shots(self, soc, rounds: int = 1, progress: bool = False):
        n = self.reps * max(1, int(rounds))
        shots_i, shots_q = [], []
        for k in range(len(self.cfg["ro_chs"])):
            angle, threshold, ng, ne = self._readout(k)
            excited = self.rng.random(n) < excited_probability(k, self.point)
            flip = np.where(excited, self.rng.random(n) < ne, self.rng.random(n) < ng)
            reads_e = excited ^ flip
            scale = max(abs(threshold), 1.0)
            i_rot = threshold + np.where(reads_e, 1.0, -1.0) * scale + self.rng.normal(0, 0.25 * scale, n)
            q_rot = self.rng.normal(0, 0.25 * scale, n)
            # undo the rotation the analysis applies (populations.rotate by +angle)
            shots_i.append(i_rot * np.cos(-angle) - q_rot * np.sin(-angle))
            shots_q.append(i_rot * np.sin(-angle) + q_rot * np.cos(-angle))
        return shots_i, shots_q

    def acquire(self, soc, rounds: int = 1, progress: bool = False):
        """Averaged I/Q per readout, shaped like AveragerProgramV2.acquire: (triggers, 2)."""
        shots_i, shots_q = self.acquire_shots(soc, rounds, progress)
        return [np.array([[np.mean(i), np.mean(q)]]) for i, q in zip(shots_i, shots_q)]
