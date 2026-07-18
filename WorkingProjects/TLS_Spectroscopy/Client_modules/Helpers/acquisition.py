"""
Shot-interleaved averaging for QICK experiments  --  QUA drift-immunity parity.

WHY
---
QUA runs the shot loop OUTERMOST and stream-averages over it, so every sweep point is
revisited on every shot: slow drift (1/f, thermal, flux, TLS-bath) averages uniformly
into all points instead of imprinting as a systematic gradient along the sweep axis.
This is the standard drift-immunization for fitted quantities (T1/T2 decays, step
responses) and it also protects position-vs-flux maps.

QICK hardware-averages ``reps`` per program execution, and our flux/delay sweeps are
Python loops (each sweep point is a different DAC waveform), so the naive port averages
each point FULLY before moving on -- sequential acquisition, which is vulnerable to
drift.  QICK cannot fold the whole map + shot loop into one FPGA program the way QUA
does, so exact single-shot interleaving would cost ``shots`` x more program loads.

``interleaved_average`` restores the QUA structure at the Python level with a tunable
speed/robustness knob:  it runs ``rounds`` passes over the whole sweep, each pass
hardware-averaging ``reps ~= shots/rounds``, and accumulates a running mean.

    rounds = 1       -> fast per-point average (the original sequential behaviour)
    rounds = shots   -> exact single-shot interleaving (QUA-equivalent; slowest)
    rounds = 5..20   -> most of the drift immunity at bounded cost; each point is
                        sampled ``rounds`` times spread across the acquisition

The running mean is EXACTLY the mean over ``shots`` shots (reps-weighted accumulation),
so for a stationary system the result is bit-for-bit what the sequential average would
give -- only the drift robustness (and the live-plot semantics) change.
"""

import numpy as np


def split_reps(shots, rounds):
    """Per-round rep counts summing to ``shots`` (remainder spread over the first rounds)."""
    shots = int(shots)
    rounds = max(1, min(int(rounds), max(shots, 1)))
    base, extra = divmod(shots, rounds)
    return [base + (1 if r < extra else 0) for r in range(rounds)]


def interleaved_average(run_point, n_points, shots, rounds=None, live=None, progress=None):
    """QUA-style shot-interleaved averaging over a Python sweep of ``n_points``.

    Parameters
    ----------
    run_point : callable(point_index, reps) -> np.ndarray
        Build+run the program for one sweep point, hardware-averaged over ``reps`` for
        this pass, and return its value (any shape, but consistent across points).
    n_points : int
        Number of sweep points (the Python sweep that would otherwise be sequential).
    shots : int
        Total shots per point (== QUA ``shots``).
    rounds : int, optional
        Interleave passes.  None -> ``min(shots, 10)``.  Each pass sweeps all points
        with ``reps ~= shots/rounds``; passes accumulate into a running, reps-weighted
        mean, so the final result is the exact mean over ``shots`` shots.
    live : callable(round_index, running_mean) , optional
        Per-round callback for a QUA-like whole-map live plot (fixed-size map that
        sharpens as the shot count climbs), receiving the running mean of shape
        ``(n_points, *point_shape)``.

    Returns
    -------
    np.ndarray of shape ``(n_points, *point_shape)`` -- the interleaved mean.
    """
    if rounds is None:
        rounds = min(int(shots), 10)
    reps_per_round = split_reps(shots, rounds)
    total_units = sum(1 for reps in reps_per_round if reps > 0) * n_points
    acc = None
    done = 0
    done_units = 0
    for r, reps in enumerate(reps_per_round):
        if reps <= 0:
            continue
        for idx in range(n_points):
            val = np.asarray(run_point(idx, reps))
            if acc is None:
                acc = np.zeros((n_points,) + val.shape,
                               dtype=complex if np.iscomplexobj(val) else float)
            acc[idx] = acc[idx] + val * reps          # sum over shots in this pass
            done_units += 1
            if progress is not None:
                progress(done_units, total_units)      # smooth per-point bar (QUA feel)
        done += reps
        if live is not None:
            live(r, acc / done)                        # running mean (partial average)
    if acc is None:
        raise RuntimeError("interleaved_average collected no shots (shots/rounds = 0).")
    return acc / max(done, 1)


def resolve_rounds(cfg, shots, default=None):
    """Pick the interleave-round count: cfg['interleave_rounds'] if set, else default,
    else min(shots, 10).  Clamped to [1, shots].  'full' or <=0 means shots (exact QUA)."""
    r = cfg.get("interleave_rounds", default) if isinstance(cfg, dict) else default
    if r is None:
        r = min(int(shots), 10)
    if isinstance(r, str):
        r = shots if r.strip().lower() in ("full", "shots", "qua") else int(r)
    r = int(r)
    if r <= 0:
        r = int(shots)
    return max(1, min(r, max(int(shots), 1)))
