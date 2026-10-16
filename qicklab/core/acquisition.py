"""Acquisition helpers: raw shot buffers, retry on the stale shot counter, chunk stitching.

Background: docs/concepts/averaging.md.
"""

import time

import numpy as np


def raw_shot_buffers(prog):
    """Return ``(di_buf, dq_buf)`` of an acquired program in the pre-0.2.29x flat raw layout.

    See docs/concepts/averaging.md#single-shot-programs-and-raw-buffers.
    """
    acc_buf = getattr(prog, "acc_buf", None)
    if not acc_buf:
        # qick <= ~0.2.28x: di_buf already is the raw stream; return it untouched
        return prog.di_buf, prog.dq_buf

    di_buf = [np.asarray(d)[..., 0].ravel() for d in acc_buf]
    dq_buf = [np.asarray(d)[..., 1].ravel() for d in acc_buf]
    return di_buf, dq_buf


# Stale tProc shot counter only; "Overflowed the averages buffer" is deliberately not retried
# (docs/concepts/averaging.md#overflowed-the-averages-buffer-is-different)
_TRANSIENT_READOUT_MARKERS = ("could not broadcast input array", "got too much data")


def acquire_with_retry(make_prog, soc, n_tries=3, label="", **acquire_kwargs):
    """Run ``make_prog().acquire(soc)``, retrying on the stale-shot-counter error.

    `make_prog` must return a FRESH program; docs/concepts/averaging.md#the-stale-shot-counter-race.
    """
    last_err = None
    for attempt in range(n_tries):
        prog = make_prog()
        try:
            return prog.acquire(soc, **acquire_kwargs)
        except (ValueError, RuntimeError) as err:
            if not any(m in str(err) for m in _TRANSIENT_READOUT_MARKERS):
                raise
            last_err = err
            tag = f" [{label}]" if label else ""
            print(
                f"[acquire_with_retry]{tag} transient readout error on attempt "
                f"{attempt + 1}/{n_tries}: {err}"
            )
            try:
                # tProc v1 full reset + reload clears the residual counts (tens of ms)
                soc.stop_tproc()
            except Exception as cleanup_err:
                print(f"[acquire_with_retry]   stop_tproc() failed: {cleanup_err}")
            time.sleep(0.1)
    raise RuntimeError(
        f"acquire failed {n_tries}x with a transient readout error"
        f"{f' [{label}]' if label else ''}; last error: {last_err}"
    ) from last_err


# Mode/unit keys copied from the first chunk into the stitched record (and so into save_data)
_META_KEYS = (
    "mode",
    "sample_period_us",
    "read_length_us",
    "adc_trig_offset_us",
    "ro_norm_cycles",
    "decimated_fs_MHz",
    "decimated_fs_source",
    "capture_length_us",
    "samples_per_capture",
    "soft_avgs",
    "n_captures",
)


def chunked_acquire(experiment, n_chunks, progress=False):
    """Run ``experiment.acquire()`` n_chunks times and stitch I, Q and a monotonic t_us.

    Also sets ``experiment.data``; contract: docs/concepts/averaging.md#chunked-acquisition-helpers.
    """
    if n_chunks < 1:
        raise ValueError(f"n_chunks must be >= 1, got {n_chunks}")
    I_parts, Q_parts, t_parts = [], [], []
    wall_clocks = []
    wall_clock_ends = []
    gap_indices = []
    cum_offset_us = 0.0
    cum_idx = 0
    first_meta = {}
    iterator = range(n_chunks)
    if progress:
        try:
            from tqdm import tqdm

            iterator = tqdm(iterator, desc="chunked_acquire")
        except ImportError:
            pass
    for ci in iterator:
        out = experiment.acquire(progress=False)
        I_c = np.asarray(out["I"], dtype=float).ravel()
        Q_c = np.asarray(out["Q"], dtype=float).ravel()
        t_c = np.asarray(out["t_us"], dtype=float).ravel()
        if not (I_c.shape == Q_c.shape == t_c.shape):
            raise RuntimeError(
                f"chunk {ci} returned mismatched shapes: I={I_c.shape}, "
                f"Q={Q_c.shape}, t_us={t_c.shape}"
            )
        if ci == 0:
            for k in _META_KEYS:
                if k in out:
                    first_meta[k] = out[k]
        if ci > 0:
            if t_parts and t_parts[-1].size >= 2:
                sp = float(t_parts[-1][1] - t_parts[-1][0])
            else:
                # single-sample chunk: a 0.0 period would duplicate a timestamp (spec §6.2)
                sp = float(
                    first_meta.get("sample_period_us", 0.0)
                    or getattr(experiment, "cfg", {}).get("sample_period_us", 0.0)
                )
            cum_offset_us = t_parts[-1][-1] + sp
            gap_indices.append(cum_idx)
        t_shifted = t_c + cum_offset_us
        I_parts.append(I_c)
        Q_parts.append(Q_c)
        t_parts.append(t_shifted)
        wall_clocks.append(out.get("wall_clock_start", None))
        wall_clock_ends.append(out.get("wall_clock_end", None))
        cum_idx += I_c.size

    stitched = {
        "I": np.concatenate(I_parts),
        "Q": np.concatenate(Q_parts),
        "t_us": np.concatenate(t_parts),
        "gap_indices": gap_indices,
        "chunk_wall_clock_starts": wall_clocks,
        "chunk_wall_clock_ends": wall_clock_ends,
        "n_chunks": int(n_chunks),
        "wall_clock_start": wall_clocks[0] if wall_clocks else None,
        "wall_clock_end": wall_clock_ends[-1] if wall_clock_ends else None,
    }
    stitched.update(first_meta)
    # the inner acquire() left only the last chunk in experiment.data
    try:
        experiment.data = {"data": stitched}
    except AttributeError:
        pass
    return stitched


def _check_reps_per_block(experiment, reps_per_block):
    """Raise unless 1 <= reps_per_block <= avg_maxlen (one block fits the averages buffer)."""
    if reps_per_block < 1:
        raise ValueError(f"reps_per_block must be >= 1, got {reps_per_block}")
    soccfg = getattr(experiment, "soccfg", None)
    ro_chs = experiment.cfg.get("ro_chs")
    if soccfg is None or not ro_chs:
        return
    avg_maxlen = int(soccfg["readouts"][ro_chs[0]]["avg_maxlen"])
    if reps_per_block > avg_maxlen:
        raise RuntimeError(
            f"[modulated_strobe_acquire] reps_per_block={reps_per_block} > "
            f"avg_maxlen={avg_maxlen} for readout ch {ro_chs[0]}: each block is kept within "
            f"the averages buffer. Shorten the blocks (raise modulation_freq_hz)."
        )


def modulated_strobe_acquire(experiment, gain_schedule, reps_per_block, progress=False):
    """Acquire one strobe block of `reps_per_block` samples per entry of `gain_schedule`
    (set_qubit_gain first) and stitch.

    Contract: docs/concepts/averaging.md#chunked-acquisition-helpers.
    """
    reps_per_block = int(reps_per_block)
    _check_reps_per_block(experiment, reps_per_block)
    cfg = experiment.cfg
    # set_qubit_gain compiles cfg["reps"] (copied from cfg["reps_per_chunk"] when present):
    # point both at reps_per_block for the blocks, restore them afterwards
    saved = {k: cfg[k] for k in ("reps_per_chunk", "reps") if k in cfg}
    cfg["reps"] = reps_per_block
    if "reps_per_chunk" in cfg:
        cfg["reps_per_chunk"] = reps_per_block
    I_parts, Q_parts, t_parts = [], [], []
    ref_parts, gaps, wall_starts, wall_ends = [], [], [], []
    cum_idx = 0
    cum_offset_us = 0.0
    sample_period = float(cfg.get("sample_period_us", 0.0))
    first_meta = {}
    gain_applied = False
    try:
        for bi, gain in enumerate(gain_schedule):
            experiment.set_qubit_gain(gain)
            gain_applied = True
            data = experiment.acquire(progress=False)
            I_c = np.asarray(data["I"]).ravel()
            Q_c = np.asarray(data["Q"]).ravel()
            t_c = np.asarray(data["t_us"], dtype=float).ravel()
            if bi == 0:
                for k in _META_KEYS:
                    if k in data:
                        first_meta[k] = data[k]
                sample_period = float(data.get("sample_period_us", sample_period) or sample_period)
            if bi > 0:
                gaps.append(cum_idx)
            t_parts.append(t_c + cum_offset_us)
            if t_c.size >= 2:
                cum_offset_us = t_parts[-1][-1] + (t_c[1] - t_c[0])
            else:
                cum_offset_us = t_parts[-1][-1] + sample_period
            I_parts.append(I_c)
            Q_parts.append(Q_c)
            ref_parts.append(np.full(I_c.size, 1.0 if gain > 0 else 0.0))
            wall_starts.append(data.get("wall_clock_start"))
            wall_ends.append(data.get("wall_clock_end"))
            cum_idx += I_c.size
    finally:
        cfg.update(saved)
        for k in ("reps_per_chunk", "reps"):
            if k not in saved:
                cfg.pop(k, None)
        if gain_applied:
            # rebuild with the original reps, still at the last gain applied
            experiment.set_qubit_gain(cfg["qubit_gain"])
    stitched = {
        "I": np.concatenate(I_parts),
        "Q": np.concatenate(Q_parts),
        "t_us": np.concatenate(t_parts),
        "modulation_reference": np.concatenate(ref_parts),
        "gap_indices": gaps,
        "block_labels": list(gain_schedule),
        "chunk_wall_clock_starts": wall_starts,
        "chunk_wall_clock_ends": wall_ends,
        "n_chunks": len(gain_schedule),
        "reps_per_block": reps_per_block,
        "sample_period_us": sample_period,
        "modulation_freq_hz": (1.0 / (2.0 * reps_per_block * sample_period * 1e-6))
        if sample_period > 0
        else float("nan"),
    }
    stitched.update(first_meta)
    return stitched
