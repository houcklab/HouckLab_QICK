"""Dwell-time statistics for binary parity traces (gap-aware run lengths, debounce, exponential fits)."""

import numpy as np


def _gap_segment_edges(gap_indices, n):
    """Segment boundaries ``[0, ...valid gaps..., n]`` for a length-n trace.

    Keeps only gap indices strictly inside the trace (``0 < g < n``); out-of-range
    entries (negative, 0, or >= n) are dropped as boundary no-ops. Returned edges
    are sorted and unique, so zipping consecutive pairs yields non-overlapping
    ``[a, b)`` segments that never span an acquisition gap.
    """
    valid = sorted({int(g) for g in (gap_indices or []) if 0 < int(g) < n})
    return [0, *valid, n]


def _debounce_bits(bits, min_len):
    """Merge runs shorter than min_len into the neighbouring run (single segment)."""
    bits = np.asarray(bits).astype(int).copy()
    if bits.size == 0 or min_len <= 1:
        return bits
    changed = True
    while changed:
        changed = False
        edges = np.flatnonzero(np.diff(bits)) + 1
        starts = np.concatenate(([0], edges))
        ends = np.concatenate((edges, [bits.size]))
        lengths = ends - starts
        for i in range(starts.size):
            if lengths[i] < min_len:
                if i > 0:
                    bits[starts[i] : ends[i]] = bits[starts[i - 1]]
                elif i + 1 < starts.size:
                    bits[starts[i] : ends[i]] = bits[starts[i + 1]]
                changed = True
                break
    return bits


def _debounce_bits_segmented(bits, gap_indices, min_dwell_bins):
    """Apply _debounce_bits within each gap-delimited segment (never across a gap)."""
    bits = np.asarray(bits).astype(int)
    n = bits.size
    if min_dwell_bins <= 1 or n == 0:
        return bits.copy()
    edges = _gap_segment_edges(gap_indices, n)
    out = bits.copy()
    for a, b in zip(edges[:-1], edges[1:]):
        out[a:b] = _debounce_bits(bits[a:b], min_dwell_bins)
    return out


def dwell_time_statistics(
    binary_states, t_us, gap_indices=None, merge_short_segments=False, min_dwell_bins=1
):
    """
    Lengths of contiguous runs in state 0 and state 1, in microseconds.

    Runs spanning a `gap_indices` boundary are split (not joined across it).

    Returns
    -------
    dict with keys:
      dwell_0_us, dwell_1_us : array of dwell durations (us)
      mean_0, mean_1         : float, mean dwell time per state (nan if no runs)
      n_runs_0, n_runs_1     : int, run counts
      exp_fit_0, exp_fit_1   : dict {"tau_us": float, "A": float}; nans if fit fails
    """
    binary_states = np.asarray(binary_states).astype(int)
    if merge_short_segments and min_dwell_bins > 1:
        binary_states = _debounce_bits_segmented(binary_states, gap_indices, min_dwell_bins)
    bits = np.asarray(binary_states, dtype=int)
    t = np.asarray(t_us, dtype=float)
    n = bits.size
    if n == 0:
        return {
            "dwell_0_us": np.zeros(0),
            "dwell_1_us": np.zeros(0),
            "mean_0": float("nan"),
            "mean_1": float("nan"),
            "n_runs_0": 0,
            "n_runs_1": 0,
            "exp_fit_0": {"tau_us": float("nan"), "A": float("nan")},
            "exp_fit_1": {"tau_us": float("nan"), "A": float("nan")},
        }

    # Break trace into segments at gap_indices, run-length encode each segment.
    # Out-of-range entries (negative, 0, or >= n) are dropped as boundary no-ops
    # to avoid IndexError from numpy slice wraparound.
    breakpoints = _gap_segment_edges(gap_indices, n)
    # Global sample period, recoverable from the whole trace even when an
    # individual segment is a single sample. Used to extrapolate the duration
    # of the last run in each segment.
    global_sp = float(t[1] - t[0]) if n >= 2 else 0.0
    dwells_0, dwells_1 = [], []
    for a, b in zip(breakpoints[:-1], breakpoints[1:]):
        if b <= a:
            continue
        seg = bits[a:b]
        seg_t = t[a:b]
        # Run-length encode
        change_idx = np.where(np.diff(seg) != 0)[0] + 1
        run_starts = np.concatenate(([0], change_idx))
        run_ends = np.concatenate((change_idx, [seg.size]))
        for rs, re in zip(run_starts, run_ends):
            state = int(seg[rs])
            # Duration: time from first sample in run to first sample after run
            if re < seg.size:
                duration = float(seg_t[re] - seg_t[rs])
            else:
                # Last run in segment: extrapolate using the sample period.
                # Prefer the segment's own period; fall back to the global
                # period so a single-sample segment yields ~one period, not 0.
                if seg.size >= 2:
                    sp = float(seg_t[1] - seg_t[0])
                else:
                    sp = global_sp
                duration = float(seg_t[re - 1] - seg_t[rs]) + sp
            if state == 0:
                dwells_0.append(duration)
            else:
                dwells_1.append(duration)

    dwells_0 = np.asarray(dwells_0, dtype=float)
    dwells_1 = np.asarray(dwells_1, dtype=float)

    return {
        "dwell_0_us": dwells_0,
        "dwell_1_us": dwells_1,
        "mean_0": float(np.mean(dwells_0)) if dwells_0.size else float("nan"),
        "mean_1": float(np.mean(dwells_1)) if dwells_1.size else float("nan"),
        "n_runs_0": int(dwells_0.size),
        "n_runs_1": int(dwells_1.size),
        "exp_fit_0": _fit_exp_dwell(dwells_0),
        "exp_fit_1": _fit_exp_dwell(dwells_1),
    }


def _fit_exp_dwell(dwells, bins=None):
    """
    Fit an exponential to a dwell-time histogram via log-linear regression.

    Parameters
    ----------
    dwells : array of dwell durations (us)
    bins   : int or None; histogram bin count. None -> adaptive
             min(30, max(5, size // 10)).

    Returns
    -------
    dict {tau_us, A, bins_used}. tau_us/A are nan if the fit fails. `A` is the
    count-amplitude calibrated to `bins_used` bins so a caller that re-histograms
    `dwells` with `bins_used` can overlay `A * exp(-x / tau_us)` consistently.

    The log-counts are heteroscedastic (var(log N) ~ 1/N), so the regression is
    weighted by sqrt(count) — unweighted OLS overweights the sparse tail bins
    and biases tau high (~10%, failing the spec §6 ±5% criterion).
    """
    dwells = np.asarray(dwells, dtype=float)
    fail = {"tau_us": float("nan"), "A": float("nan"), "bins_used": 0}
    if dwells.size < 5:
        return fail
    try:
        if bins is None:
            bins = min(30, max(5, dwells.size // 10))
        bins = int(bins)
        hist, edges = np.histogram(dwells, bins=bins)
        centers_h = 0.5 * (edges[:-1] + edges[1:])
        mask = hist > 0
        if mask.sum() < 3:
            return fail
        x = centers_h[mask]
        y = np.log(hist[mask])
        w = np.sqrt(hist[mask].astype(float))  # Poisson weighting in log space
        slope, intercept = np.polyfit(x, y, 1, w=w)
        if slope >= 0:
            return fail
        tau = -1.0 / slope
        A = float(np.exp(intercept))
        return {"tau_us": float(tau), "A": A, "bins_used": bins}
    except Exception:
        return fail
