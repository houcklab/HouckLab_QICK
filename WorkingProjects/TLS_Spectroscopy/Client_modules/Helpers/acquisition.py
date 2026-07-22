import os as _os
import sys as _sys
import contextlib as _contextlib

import numpy as np


@_contextlib.contextmanager
def suppress_stdout():
    """Silence stdout for the duration of the block.

    qick prints a per-program line whenever it rounds a requested pulse/readout
    frequency or clips a gain (e.g. the per-flux dispersive readout in step 2 triggers
    it on every point).  Those newline-terminated prints break the in-place '\\r'
    progress bar -- the bar "keeps going away".  Wrapping the program build + acquire in
    this keeps the progress bar the ONLY thing on the console, exactly like the QUA
    workflow.  Exceptions still propagate; stderr is untouched.
    """
    saved = _sys.stdout
    devnull = open(_os.devnull, "w")
    try:
        _sys.stdout = devnull
        yield
    finally:
        _sys.stdout = saved
        devnull.close()


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
    nz_rounds = sum(1 for reps in reps_per_round if reps > 0)
    total_units = nz_rounds * n_points
    if progress is not None:
        reps0 = next((reps for reps in reps_per_round if reps > 0), 0)
        print(f"[acquire] shot-interleaved: {n_points} points x {nz_rounds} rounds x "
              f"~{reps0} reps = {shots} shots/point  ->  progress counts the "
              f"{total_units} programs (NOT shots)", flush=True)
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
            acc[idx] = acc[idx] + val * reps
            done_units += 1
            if progress is not None:
                progress(done_units, total_units)
        done += reps
        if live is not None:
            live(r, acc / done)
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
