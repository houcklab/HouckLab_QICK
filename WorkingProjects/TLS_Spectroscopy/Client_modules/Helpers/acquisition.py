import os as _os
import sys as _sys
import contextlib as _contextlib

import numpy as np


@_contextlib.contextmanager
def suppress_stdout():
    saved = _sys.stdout
    devnull = open(_os.devnull, "w")
    try:
        _sys.stdout = devnull
        yield
    finally:
        _sys.stdout = saved
        devnull.close()


def split_reps(shots, rounds):
    shots = int(shots)
    rounds = max(1, min(int(rounds), max(shots, 1)))
    base, extra = divmod(shots, rounds)
    return [base + (1 if r < extra else 0) for r in range(rounds)]


def interleaved_average(run_point, n_points, shots, rounds=None, live=None, progress=None):
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


def order_rng(cfg):
    seed = cfg.get("point_order_seed", None) if isinstance(cfg, dict) else None
    return np.random.default_rng(seed)


def visit_order(n, cfg, rng):
    randomize = (bool(cfg.get("randomize_point_order", False))
                 if isinstance(cfg, dict) else False)
    return rng.permutation(int(n)) if randomize else np.arange(int(n))


def resolve_rounds(cfg, shots, default=None):
    r = cfg.get("interleave_rounds", default) if isinstance(cfg, dict) else default
    if r is None:
        r = min(int(shots), 10)
    if isinstance(r, str):
        r = shots if r.strip().lower() in ("full", "shots", "qua") else int(r)
    r = int(r)
    if r <= 0:
        r = int(shots)
    return max(1, min(r, max(int(shots), 1)))
