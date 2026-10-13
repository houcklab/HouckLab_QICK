"""Per-shot accumulated I/Q extraction that survives the QICK buffer change.

Up to qick ~0.2.28x, ``AveragerProgram._process_accumulated`` handed back the
raw per-repetition accumulated stream, so ``prog.di_buf[ch]`` / ``prog.dq_buf[ch]``
were flat arrays of length ``reps * reads_per_shot`` (times ``expts`` for
RAveragerProgram) in raw accumulator units. Every single-shot experiment here
reshapes/strides those arrays.

From qick ~0.2.29x on (the BFG board runs 0.2.367), that method first calls
``_average_buf``, which averages over the reps axis and divides by the readout
length. ``di_buf`` therefore holds ONE length-normalized point per read per
channel, and the old reshape fails with e.g.

    ValueError: cannot reshape array of size 1 into shape (1,1000)

The raw stream still exists, as ``prog.acc_buf``: one array per readout channel
shaped ``(*loop_dims, reads_per_shot, 2)`` with the I/Q pair last, in raw
accumulator units (no length normalization, no IQ-offset removal) — i.e. exactly
what the old ``di_buf``/``dq_buf`` held, just not flattened.

``raw_shot_buffers`` flattens it back to the historical layout so call sites keep
their existing reshape/stride/normalization arithmetic unchanged.

Note on rounds: ``acc_buf`` is overwritten every round, so with ``rounds`` > 1 it
holds the last round only. That matches the old behaviour (``di_buf`` was also
re-derived per round), but single-shot programs should still force ``rounds`` = 1.
"""

import time

import numpy as np


def raw_shot_buffers(prog):
    """Return ``(di_buf, dq_buf)`` in the pre-0.2.29x flat per-shot layout.

    Parameters
    ----------
    prog : qick AveragerProgram / RAveragerProgram
        A program on which ``acquire()`` has already been called.

    Returns
    -------
    (list of numpy.ndarray, list of numpy.ndarray)
        One flat float array per declared readout channel (declaration order,
        not absolute channel number), length ``prod(loop_dims) * reads_per_shot``,
        in raw accumulator units.
    """
    acc_buf = getattr(prog, "acc_buf", None)
    if not acc_buf:
        # qick <= ~0.2.28x (or a synthetic prog in a self-test): di_buf is
        # already the raw stream. Hand the containers back untouched so any
        # indexing convention the caller relies on still works.
        return prog.di_buf, prog.dq_buf

    di_buf = [np.asarray(d)[..., 0].ravel() for d in acc_buf]
    dq_buf = [np.asarray(d)[..., 1].ravel() for d in acc_buf]
    return di_buf, dq_buf


# Signatures of a stale tProc shot counter, as opposed to a real config problem.
# "Overflowed the averages buffer" is deliberately NOT here: that one means the
# tProc is outrunning the readout and needs a longer relax_delay, so retrying it
# would just spin.
_TRANSIENT_READOUT_MARKERS = ("could not broadcast input array",
                              "got too much data")


def acquire_with_retry(make_prog, soc, n_tries=3, label="", **acquire_kwargs):
    """Run a QICK program, retrying a transient streaming-readout failure.

    When programs run back to back, the tProc shot counter occasionally reports
    more shots than the program actually ran: the streamer zeroes the counter and
    starts the next program while the previous one is still retiring its last
    reps, so those leftover counts land on top of the fresh run. qick_asm.acquire()
    then tries to write more accumulated points than it allocated and dies with

        ValueError: could not broadcast input array from shape (26,2) into shape (20,2)

    (the second number is reps, the first is reps + leftovers). It is intermittent
    and gets likelier the more programs a routine starts, so a long sweep can lose
    hours of acquisition to it. The condition does not persist: resetting the tProc
    and re-arming the readout clears the counter, so retrying the point recovers.

    `make_prog` is a zero-argument callable returning a FRESH program object — the
    failed one has a half-written accumulation buffer and must not be reused.
    Raises the underlying error unchanged if it is not one of the transient ones,
    or if every attempt fails.
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
            print(f"[acquire_with_retry]{tag} transient readout error on attempt "
                  f"{attempt + 1}/{n_tries}: {err}")
            try:
                # tProc v1: full reset + program reload, which is what actually
                # clears the residual counts. Tens of ms, and only on a failure.
                soc.stop_tproc()
            except Exception as cleanup_err:
                print(f"[acquire_with_retry]   stop_tproc() failed: {cleanup_err}")
            time.sleep(0.1)
    raise RuntimeError(
        f"acquire failed {n_tries}x with a transient readout error"
        f"{f' [{label}]' if label else ''}; last error: {last_err}"
    ) from last_err


# Keys that describe the acquisition mode/units, propagated from the first chunk
# to the stitched output so save_data persists them verbatim. Module-level so both
# chunked_acquire and modulated_strobe_acquire share the same set.
_META_KEYS = (
    "mode", "sample_period_us",
    "read_length_us", "adc_trig_offset_us", "ro_norm_cycles",
    "decimated_fs_MHz", "decimated_fs_source",
    "capture_length_us", "samples_per_capture",
    "soft_avgs", "n_captures",
)


def chunked_acquire(experiment, n_chunks, progress=False):
    """
    Run experiment.acquire() n_chunks times back-to-back and stitch results.

    Each acquire() must return a dict with keys "I", "Q", "t_us" (1-D arrays of
    equal length per chunk) and optionally "wall_clock_start" (str).

    The stitched time axis is monotonic: each subsequent chunk's t_us is shifted
    by (previous_chunk_t_us[-1] + sample_period). Inter-chunk Python+tProc gaps
    are NOT modeled in the stitched t_us; gap_indices marks where boundaries
    occur so the analysis module can avoid counting switches across them.

    Parameters
    ----------
    experiment : object with .acquire(progress=False) -> dict {I, Q, t_us, ...}
    n_chunks   : int >= 1
    progress   : bool

    Returns
    -------
    dict:
      I, Q, t_us               : concatenated arrays
      gap_indices              : list of ints, first index of each chunk after the
                                  first (length n_chunks - 1)
      chunk_wall_clock_starts  : list of str (or None) per chunk
      n_chunks                 : echoed int

    Side effect: sets ``experiment.data = {"data": stitched}`` before returning
    so a subsequent ``experiment.save_data()`` persists the full stitched record.
    Without this the inner ``acquire()`` calls leave only the final chunk in
    ``experiment.data``, and a bare ``save_data()`` would silently write just
    that last chunk. Callers may still pass the returned dict explicitly.
    """
    if n_chunks < 1:
        raise ValueError(f"n_chunks must be >= 1, got {n_chunks}")
    I_parts, Q_parts, t_parts = [], [], []
    wall_clocks = []
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
            # Stitch time: previous chunk's last + estimated sample period.
            if t_parts and t_parts[-1].size >= 2:
                sp = float(t_parts[-1][1] - t_parts[-1][0])
            else:
                # Degenerate single-sample chunk: the intra-chunk diff is
                # unavailable, so fall back to a real sample period (from chunk
                # metadata or the experiment cfg) instead of 0.0 — otherwise the
                # next chunk's first timestamp would duplicate this one and
                # break the strictly-increasing t_us guarantee (spec §6.2).
                sp = float(first_meta.get("sample_period_us", 0.0)
                           or getattr(experiment, "cfg", {}).get("sample_period_us", 0.0))
            cum_offset_us = t_parts[-1][-1] + sp
            gap_indices.append(cum_idx)
        t_shifted = t_c + cum_offset_us
        I_parts.append(I_c); Q_parts.append(Q_c); t_parts.append(t_shifted)
        wall_clocks.append(out.get("wall_clock_start", None))
        cum_idx += I_c.size

    stitched = {
        "I": np.concatenate(I_parts),
        "Q": np.concatenate(Q_parts),
        "t_us": np.concatenate(t_parts),
        "gap_indices": gap_indices,
        "chunk_wall_clock_starts": wall_clocks,
        "n_chunks": int(n_chunks),
        "wall_clock_start": wall_clocks[0] if wall_clocks else None,
    }
    stitched.update(first_meta)
    # Wire the stitched record into experiment.data so save_data() persists the
    # full trace, not the last chunk the inner acquire() left behind.
    try:
        experiment.data = {"data": stitched}
    except AttributeError:
        pass
    return stitched


def modulated_strobe_acquire(experiment, gain_schedule, reps_per_block, progress=False):
    """Run strobe acquisition in blocks, setting qubit_gain per block, and stitch.

    gain_schedule : list of gain values, one per block (e.g. [G_on, 0, G_on, 0, ...]).
    reps_per_block : reps (= time samples) per block; must satisfy avg_maxlen (rule 4).

    Returns the chunked_acquire contract plus:
      modulation_reference : per-sample 1.0 where the block gain > 0 else 0.0
      block_labels         : the gains actually applied, per block
      reps_per_block, sample_period_us, modulation_freq_hz
    """
    I_parts, Q_parts, t_parts = [], [], []
    ref_parts, gaps, wall_starts = [], [], []
    cum_idx = 0
    cum_offset_us = 0.0
    sample_period = float(experiment.cfg.get("sample_period_us", 0.0))
    first_meta = {}
    for bi, gain in enumerate(gain_schedule):
        experiment.set_qubit_gain(gain)
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
        cum_idx += I_c.size
    stitched = {
        "I": np.concatenate(I_parts),
        "Q": np.concatenate(Q_parts),
        "t_us": np.concatenate(t_parts),
        "modulation_reference": np.concatenate(ref_parts),
        "gap_indices": gaps,
        "block_labels": list(gain_schedule),
        "chunk_wall_clock_starts": wall_starts,
        "n_chunks": len(gain_schedule),
        "reps_per_block": int(reps_per_block),
        "sample_period_us": sample_period,
        "modulation_freq_hz": (1.0 / (2.0 * reps_per_block * sample_period * 1e-6))
                              if reps_per_block > 0 and sample_period > 0 else float("nan"),
    }
    stitched.update(first_meta)
    return stitched
