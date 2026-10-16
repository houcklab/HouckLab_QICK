"""Dwell-time statistics for binary parity traces (gap-aware run lengths, debounce, dwell-time MLE)."""

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
    Lengths of contiguous runs in state 0 and state 1, in microseconds and samples.

    Runs spanning a `gap_indices` boundary are split (not joined across it). The
    first and last run of each gap segment are censored (cut by the segment edge).

    The dwell time tau_s = 1/gamma_s is the maximum-likelihood estimate for a
    continuous-time two-state telegraph (rate gamma_0 = 1/tau_0 out of 0, gamma_1 out
    of 1) sampled every sp, with the censored runs included. Sampled, the telegraph is
    a two-state Markov chain: each step from a sample in state s to the next sample of
    the same segment is a trial that leaves s with probability
    P_s = (gamma_s/Gamma)(1 - exp(-Gamma sp)), Gamma = gamma_0 + gamma_1 (a switch
    within the step can be undone by a second one, so P_s depends on both rates). The
    MLE is P_s = N_exits / exposure, where N_exits counts the switches out of s and
    exposure the samples in s that have a next sample in the same segment (a run of n
    samples adds n trials, or n - 1 if it is the segment's last run). Inverting,
    lambda = 1 - P_0 - P_1, Gamma = -ln(lambda)/sp and tau_s = (P_0 + P_1)/(P_s Gamma);
    the single-state form -sp/ln(1 - P_s) would read high by about sp/(2 tau_other).
    tau_err is the delta-method error through both P_0 and P_1 (binomial variances),
    ~ tau/sqrt(N_exits) for tau >> sp. Using only the interior runs (P = 1/mean(n))
    would instead be biased low by about tau/T_segment, because long dwells are the
    ones a segment of length T_segment cuts off. sp is the median within-segment
    sample spacing. tau is NaN with fewer than 5 exits from s, or when lambda <= 0
    (P_0 + P_1 >= 1: switching not resolved at this sp, e.g. every run one sample long).
    With debouncing (`merge_short_segments`, `min_dwell_bins` = m > 1) runs shorter
    than m no longer occur and merging lengthens the neighbours, so the first m - 1
    steps of every run whose start is observed are not counted as trials (for the
    interior runs this is P = 1/(mean(n) - (m - 1))); the debounced trace is not a
    sampled telegraph, so this is an approximation there, not exact.

    Returns
    -------
    dict with keys:
      dwell_0_us, dwell_1_us             : array of dwell durations (us), all runs
      dwell_0_samples, dwell_1_samples   : array of run lengths (samples), all runs
      censored_0, censored_1             : bool array, True for a segment's first/last run
      mean_0, mean_1                     : float, mean dwell time per state over all runs
                                           (nan if no runs)
      n_runs_0, n_runs_1                 : int, run counts (all runs)
      sample_period_us                   : float, sp used by the MLE (nan if < 2 samples)
      tau_mle_0_us, tau_mle_1_us         : float, MLE dwell time (us), censored runs included
      tau_err_0_us, tau_err_1_us         : float, its 1-sigma error (us)
      p_exit_0, p_exit_1                 : float, MLE per-sample exit probability P_s
                                           (exits/trials; nan if no trials)
      n_exits_0, n_exits_1               : int, switches out of the state (the MLE's events)
      n_interior_0, n_interior_1         : int, interior (uncensored) runs
      exp_fit_0, exp_fit_1               : dict {"tau_us", "A", "bins_used"}: log-linear
                                           histogram fit, kept for the histogram overlay and
                                           the legacy ``exp_fit_tau_*`` fields; biased high
                                           (~15 %) at 100-300 dwells. nans if the fit fails.
    """
    binary_states = np.asarray(binary_states).astype(int)
    if merge_short_segments and min_dwell_bins > 1:
        binary_states = _debounce_bits_segmented(binary_states, gap_indices, min_dwell_bins)
    bits = np.asarray(binary_states, dtype=int)
    t = np.asarray(t_us, dtype=float)
    n = bits.size
    shift = max(int(min_dwell_bins), 1) - 1 if merge_short_segments else 0
    if n == 0:
        return {
            "dwell_0_us": np.zeros(0),
            "dwell_1_us": np.zeros(0),
            "dwell_0_samples": np.zeros(0, dtype=int),
            "dwell_1_samples": np.zeros(0, dtype=int),
            "censored_0": np.zeros(0, dtype=bool),
            "censored_1": np.zeros(0, dtype=bool),
            "mean_0": float("nan"),
            "mean_1": float("nan"),
            "n_runs_0": 0,
            "n_runs_1": 0,
            "sample_period_us": float("nan"),
            "tau_mle_0_us": float("nan"),
            "tau_mle_1_us": float("nan"),
            "tau_err_0_us": float("nan"),
            "tau_err_1_us": float("nan"),
            "p_exit_0": float("nan"),
            "p_exit_1": float("nan"),
            "n_exits_0": 0,
            "n_exits_1": 0,
            "n_interior_0": 0,
            "n_interior_1": 0,
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
    # MLE sample period: median spacing of consecutive samples in the same segment
    # (binning can leave an irregular t, and a gap spacing is not a sample period).
    steps = np.diff(t)
    within = np.ones(steps.size, dtype=bool)
    within[[g - 1 for g in breakpoints[1:-1]]] = False
    mle_sp = float(np.median(steps[within])) if within.any() else float("nan")
    dwells_0, dwells_1 = [], []
    runs_0, runs_1 = [], []
    first_0, first_1 = [], []
    last_0, last_1 = [], []
    for a, b in zip(breakpoints[:-1], breakpoints[1:]):
        if b <= a:
            continue
        seg = bits[a:b]
        seg_t = t[a:b]
        change_idx = np.where(np.diff(seg) != 0)[0] + 1
        run_starts = np.concatenate(([0], change_idx))
        run_ends = np.concatenate((change_idx, [seg.size]))
        n_seg_runs = run_starts.size
        for i_run, (rs, re) in enumerate(zip(run_starts, run_ends)):
            state = int(seg[rs])
            is_first = i_run == 0
            is_last = i_run == n_seg_runs - 1
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
                runs_0.append(int(re - rs))
                first_0.append(is_first)
                last_0.append(is_last)
            else:
                dwells_1.append(duration)
                runs_1.append(int(re - rs))
                first_1.append(is_first)
                last_1.append(is_last)

    dwells_0 = np.asarray(dwells_0, dtype=float)
    dwells_1 = np.asarray(dwells_1, dtype=float)
    runs_0 = np.asarray(runs_0, dtype=int)
    runs_1 = np.asarray(runs_1, dtype=int)
    first_0 = np.asarray(first_0, dtype=bool)
    first_1 = np.asarray(first_1, dtype=bool)
    last_0 = np.asarray(last_0, dtype=bool)
    last_1 = np.asarray(last_1, dtype=bool)
    cens_0 = first_0 | last_0
    cens_1 = first_1 | last_1
    mle_0, mle_1 = _telegraph_dwell_mle(
        _exit_counts(runs_0, first_0, last_0, shift),
        _exit_counts(runs_1, first_1, last_1, shift),
        mle_sp,
    )

    return {
        "dwell_0_us": dwells_0,
        "dwell_1_us": dwells_1,
        "dwell_0_samples": runs_0,
        "dwell_1_samples": runs_1,
        "censored_0": cens_0,
        "censored_1": cens_1,
        "mean_0": float(np.mean(dwells_0)) if dwells_0.size else float("nan"),
        "mean_1": float(np.mean(dwells_1)) if dwells_1.size else float("nan"),
        "n_runs_0": int(dwells_0.size),
        "n_runs_1": int(dwells_1.size),
        "sample_period_us": mle_sp,
        "tau_mle_0_us": mle_0["tau_us"],
        "tau_mle_1_us": mle_1["tau_us"],
        "tau_err_0_us": mle_0["tau_err_us"],
        "tau_err_1_us": mle_1["tau_err_us"],
        "p_exit_0": mle_0["p_exit"],
        "p_exit_1": mle_1["p_exit"],
        "n_exits_0": mle_0["n_exits"],
        "n_exits_1": mle_1["n_exits"],
        "n_interior_0": int(np.count_nonzero(~cens_0)),
        "n_interior_1": int(np.count_nonzero(~cens_1)),
        "exp_fit_0": _fit_exp_dwell(dwells_0),
        "exp_fit_1": _fit_exp_dwell(dwells_1),
    }


def _exit_counts(n_samples, is_first, is_last, shift=0):
    """(exits, trials) of one state from its runs, censored ones included.

    Each step from a sample in the state to the next sample of the same segment is a
    trial. A run of n samples adds n trials and one exit, or n - 1 trials and no exit
    if it is the segment's last run (`is_last`). With `shift` = m - 1 > 0 (debounced
    at m bins) the first m - 1 steps of each run whose start is observed (not
    `is_first`) are forced and not counted as trials: an approximation.
    """
    n = np.asarray(n_samples, dtype=float)
    is_first = np.asarray(is_first, dtype=bool)
    is_last = np.asarray(is_last, dtype=bool)
    exits = int(np.count_nonzero(~is_last))
    trials = n - is_last
    if shift:
        trials = np.where(is_first, trials, np.maximum(trials - float(shift), 0.0))
    return exits, float(np.sum(trials))


def _telegraph_dwell_mle(counts_0, counts_1, sample_period_us, min_exits=5):
    """MLE dwell times of a continuous-time two-state telegraph sampled every sp.

    `counts_s` = (exits, trials) from ``_exit_counts``. P_s = exits_s/trials_s is the
    MLE of the sampled chain's per-step exit probability
    P_s = (gamma_s/Gamma)(1 - exp(-Gamma sp)), Gamma = gamma_0 + gamma_1. Inverting:
    lambda = 1 - P_0 - P_1, Gamma = -ln(lambda)/sp, tau_s = 1/gamma_s =
    (P_0 + P_1)/(P_s Gamma). tau_err is the delta-method error with the binomial
    variances P_s (1 - P_s)/trials_s of the two (asymptotically independent)
    estimates. A state with no trials contributes P = 0.

    Returns two dicts {tau_us, tau_err_us, n_exits, p_exit}; tau/err are nan with
    fewer than `min_exits` exits from the state, a non-finite or non-positive sp, or
    lambda <= 0 (P_0 + P_1 >= 1: switching faster than the sampling resolves).
    """
    sp = float(sample_period_us)
    out, P, var = [], [], []
    for exits, trials in (counts_0, counts_1):
        p = exits / trials if trials > 0 else float("nan")
        out.append(
            {
                "tau_us": float("nan"),
                "tau_err_us": float("nan"),
                "n_exits": int(exits),
                "p_exit": float(p),
            }
        )
        P.append(p if trials > 0 else 0.0)
        var.append(p * (1.0 - p) / trials if trials > 0 else 0.0)
    S = P[0] + P[1]
    lam = 1.0 - S
    if not (np.isfinite(sp) and sp > 0 and lam > 0 and S > 0):
        return out[0], out[1]
    L = float(-np.log(lam))  # Gamma * sp
    # tau_k = sp S / (P_k L); dL/dS = 1/lambda
    common = 1.0 - S / (lam * L)
    for k in (0, 1):
        if out[k]["n_exits"] < min_exits or P[k] <= 0:
            continue
        base = sp / (P[k] * L)
        d_own = base * (common - S / P[k])
        d_other = base * common
        out[k]["tau_us"] = float(base * S)
        out[k]["tau_err_us"] = float(np.sqrt(d_own**2 * var[k] + d_other**2 * var[1 - k]))
    return out[0], out[1]


def _fit_exp_dwell(dwells, bins=None):
    """
    Fit an exponential to a dwell-time histogram via log-linear regression.

    Not the primary dwell-time estimate (see ``dwell_time_statistics``: the MLE
    ``tau_mle_*_us``); this fit is biased high by ~15 % at 100-300 dwells and is
    kept for the histogram binning of the overlay plot and the legacy
    ``exp_fit_tau_*`` sidecar fields.

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
