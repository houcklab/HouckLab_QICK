"""
Offline analysis for the zero-span charge-parity measurement.

See docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md for the
canonical reference.

Sequential pipeline (orchestrated end-to-end by analyze_parity_run):

  classify_parity_trace      Project (I,Q) -> parity bits via separator or KMeans
  sliding_window_switch_rate Switch rate vs time
  detect_bursts              Find anomalous high-rate intervals
  dwell_time_statistics      Per-state run-length statistics + exponential fits
  analyze_parity_run         Load saved .h5, run all of the above, save plots/sidecars

Threshold-free rate extraction (no classifier, no threshold, no debounce — the
switching rate straight from the spectrum, robust to the contrast asymmetry and
occupancy imbalance that bias the counted rate):

  segmented_welch_psd        Gap-aware Welch PSD of a projected trace
  parity_psd_rate            Lorentzian fit -> corner freq -> Gamma = 2*pi*f_c
  psd_rate_vs_bin            f_c invariance vs analysis bin size (telegraph vs
                             threshold noise crossings)
  psd_rate_from_h5           One-call entry point for a raw .h5 already on disk;
                             works with no separator via a principal-axis
                             projection

Validation primitives (consumed by validate_ZeroSpanParity.py, NOT part of the
sequential pipeline above):

  verify_modulation          Confirm a recovered trace carries an injected square wave
  contrast_from_sweeps       |Z_on - Z_off|(f), best probe freq, robust contrast SNR
  projected_histogram_snr    Two-Gaussian bimodality test on projected V(t)
  bin_size_sweep             Reprocess raw IQ at several bin sizes
  threshold_stability        Dwell-tau stability across classification thresholds

Most functions are pure (arrays in, dicts out); the exceptions are
analyze_parity_run (file + plot I/O) and the classifiers, which import sklearn
(KMeans / GaussianMixture) on the kmeans / bimodality paths.

Tests live under the `if __name__ == "__main__":` block at the end of this file
and are run with:
    python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
"""

import os
import json
import numpy as np
import h5py
import matplotlib.pyplot as plt

# Do NOT call matplotlib.use() here. This module is pulled in transitively by
# every runner (Runners/<device>.py -> runs/__init__.py -> runs/zero_span.py ->
# here), and since matplotlib 3.5 use() switches the live backend even after
# pyplot has been imported. Forcing "Agg" at import time therefore silently
# disabled EVERY interactive plot in the session -- all the plotDisp=True paths,
# utils.save_two_tone_plot's live figure, and analyze_charge_dispersion's
# plt.show(block=False) -- for experiments that have nothing to do with parity.
# The plot helpers below only ever fig.savefig() + plt.close(fig), which works on
# any backend, so no global switch is needed. The __main__ block selects Agg for
# itself (headless test runs) after this import.

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
    project_iq_onto_separator,
)


# Cap on the number of samples handed to a Gaussian-mixture fit. Two GMMs on a
# multi-million-sample trace cost tens of seconds each and are called once per
# bin size / once per environment point; a uniform subsample of this size pins
# the centers and sigmas to well under a percent, which is far below the
# systematic uncertainty of the measurement itself.
_GMM_MAX_SAMPLES = 200_000

# Cap on histogram bins. numpy's bins="auto" is max(Sturges, Freedman-Diaconis)
# and is unbounded: a long trace with a small IQR plus a handful of outliers can
# ask for millions of bins.
_HIST_MAX_BINS = 512


def _subsample(x, max_n):
    """Uniformly stride `x` down to at most max_n elements (view, not a copy)."""
    x = np.asarray(x)
    if max_n is None or x.size <= max_n:
        return x
    return x[:: int(np.ceil(x.size / max_n))]


def _two_component_centers(scores):
    """Centers of a 2-Gaussian mixture fit to `scores`, sorted ascending.

    Returns None when the fit is not meaningful (too few samples, degenerate
    input, or sklearn unavailable) so callers can fall back.
    """
    s = np.asarray(scores, dtype=float).ravel()
    s = s[np.isfinite(s)]
    if s.size < 10 or np.ptp(s) <= 0:
        return None
    try:
        from sklearn.mixture import GaussianMixture
    except ImportError:
        return None
    try:
        g = GaussianMixture(n_components=2, random_state=0).fit(
            _subsample(s, _GMM_MAX_SAMPLES).reshape(-1, 1)
        )
    except (ValueError, FloatingPointError):
        return None
    centers = np.sort(g.means_.ravel())
    if not np.all(np.isfinite(centers)):
        return None
    return centers


def _data_driven_threshold(scores):
    """Decision threshold taken from the trace itself, not from a calibration.

    Prefers the midpoint between the two components of a 2-Gaussian mixture fit
    (the valley of a bimodal projected distribution). Falls back to the median
    when the fit is unavailable or degenerate — with a unimodal trace the median
    at least splits the samples evenly instead of labelling all of them the same,
    which keeps the downstream switch-rate and dwell statistics interpretable
    (and visibly noise-like) rather than silently empty.
    """
    s = np.asarray(scores, dtype=float).ravel()
    if s.size == 0:
        return 0.0
    centers = _two_component_centers(s)
    if centers is not None:
        return float(0.5 * (centers[0] + centers[1]))
    finite = s[np.isfinite(s)]
    return float(np.median(finite)) if finite.size else 0.0


def classify_parity_trace(I, Q, separator=None, method="apriori_axis"):
    """
    Project (I, Q) samples onto a 2-state axis and return binary parity labels.

    Parameters
    ----------
    I, Q : array_like
        1-D arrays of equal length, the raw in-phase and quadrature samples.
    separator : dict or None
        For method="apriori"/"apriori_axis": must contain "g_center" and
        "e_center", each a length-2 array-like (I, Q) coordinate from a prior
        single-shot calibration. Ignored if method="kmeans".
    method : {"apriori_axis", "apriori", "kmeans"}
        "apriori_axis" (recommended for zero-span strobe traces): project onto
        (e_center - g_center) -- the SNR-optimal direction from the single-shot
        calibration -- but take the DECISION THRESHOLD from the trace's own
        two-component Gaussian fit rather than from the g/e midpoint.

        This is the right choice whenever the trace is a driven steady state.
        The zero-span measurement parks a CW drive on one parity branch, so both
        parity states sit at some small |e> population; both therefore project to
        the *same* side of the g/e midpoint, and plain "apriori" labels every
        sample identically (zero switches, one dwell run, nan tau) while looking
        like it worked. What actually distinguishes the two parity states is a
        small *offset along* the g->e axis, which is what this method thresholds.

        "apriori": project onto (e_center - g_center) and threshold at the g/e
        midpoint. Correct only when the trace really does populate |g> and |e>
        (e.g. a pi-pulse single-shot record), NOT for a driven parity trace.

        "kmeans": fit KMeans(n_clusters=2) on (I, Q); label 0 = cluster with
        the lower projection on the e-g (inter-centroid) axis, with a canonical
        axis sign so the remap is independent of KMeans' arbitrary centroid
        order and of the g/e separation direction (I, Q, or diagonal). Use when
        no separator is available.

    Returns
    -------
    dict with keys:
      binary_states  : int array (N,), values 0 or 1
      scores         : float array (N,), signed projection along separator axis
      separator_used : dict, the separator actually used (synthesized for kmeans)
      method         : echoes the requested method
      threshold      : float, the score threshold applied (0.0 for "apriori" and
                       "kmeans", which threshold at the midpoint by construction)
    """
    if method == "apriori_axis":
        if separator is None:
            raise ValueError("method='apriori_axis' requires a separator dict")
        scores, _ = project_iq_onto_separator(I, Q, separator)
        threshold = _data_driven_threshold(scores)
        bits = (scores > threshold).astype(int)
        return {
            "binary_states": bits,
            "scores": scores,
            "separator_used": {
                "g_center": np.asarray(separator["g_center"], dtype=float),
                "e_center": np.asarray(separator["e_center"], dtype=float),
            },
            "method": "apriori_axis",
            "threshold": float(threshold),
        }
    elif method == "apriori":
        if separator is None:
            raise ValueError("method='apriori' requires a separator dict")
        scores, bits = project_iq_onto_separator(I, Q, separator)
        return {
            "binary_states": bits,
            "scores": scores,
            "threshold": 0.0,
            "separator_used": {
                "g_center": np.asarray(separator["g_center"], dtype=float),
                "e_center": np.asarray(separator["e_center"], dtype=float),
            },
            "method": "apriori",
        }
    elif method == "kmeans":
        from sklearn.cluster import KMeans
        I = np.ravel(np.asarray(I, dtype=float))
        Q = np.ravel(np.asarray(Q, dtype=float))
        if I.size == 0:
            return {
                "binary_states": np.zeros(0, dtype=int),
                "scores": np.zeros(0, dtype=float),
                "separator_used": {
                    "g_center": np.array([0.0, 0.0]),
                    "e_center": np.array([0.0, 0.0]),
                },
                "method": "kmeans",
                "threshold": 0.0,
            }
        iq = np.column_stack([I, Q])
        km = KMeans(n_clusters=2, n_init=10, random_state=0).fit(iq)
        centers = km.cluster_centers_  # shape (2, 2)

        # Remap so label 0 = cluster with the lower projection on the e-g
        # (inter-centroid) axis, per spec §3.1. Ordering by raw I-coordinate
        # (the previous rule) is meaningless when the g/e separation lies along
        # Q (or any non-I direction). Projecting the centroids onto the
        # inter-centroid axis is the right idea, but the raw axis sign depends
        # on KMeans' arbitrary centroid order (proj[1]-proj[0] = |axis|^2 > 0
        # always, so argmin would just echo that order). Canonicalize the axis
        # sign — point it along its dominant +component (I-dominant -> +I,
        # Q-dominant -> +Q) — so the assignment is deterministic and
        # orientation-independent.
        axis = centers[1] - centers[0]
        if abs(axis[0]) >= abs(axis[1]):
            if axis[0] < 0:
                axis = -axis
        else:
            if axis[1] < 0:
                axis = -axis
        proj = centers @ axis
        g_idx = int(np.argmin(proj))
        e_idx = 1 - g_idx
        g_center = centers[g_idx]
        e_center = centers[e_idx]
        synth_sep = {"g_center": g_center, "e_center": e_center}
        scores, bits = project_iq_onto_separator(I, Q, synth_sep)
        return {
            "binary_states": bits,
            "scores": scores,
            "separator_used": synth_sep,
            "method": "kmeans",
            "threshold": 0.0,
        }
    else:
        raise ValueError(f"Unknown method: {method!r}")


def sliding_window_switch_rate(binary_states, t_us, window_us, step_us=None,
                                gap_indices=None):
    """
    Sliding-window switch rate in Hz from a binary parity trace.

    Parameters
    ----------
    binary_states : array_like of int (0 or 1), shape (N,)
    t_us          : array_like of float, shape (N,), monotonically increasing
    window_us     : float, window duration
    step_us       : float or None, window stride; default = window_us / 2 (50% overlap)
    gap_indices   : list[int] or None, indices i where bits[i] is the first sample
                    after an acquisition-gap boundary; the diff bits[i] - bits[i-1]
                    is set to 0 so no spurious switch is counted across a gap.

    Returns
    -------
    dict with keys:
      window_t_us         : array (M,), center time of each window
      rate_Hz             : array (M,), switch rate per window
      switches_per_window : array (M,) of int
      window_us, step_us  : echoed scalars
      covered_us          : array (M,), time actually spanned by each window
                            (equals window_us except for a short-record trace,
                            where the single window covers only t[-1]-t[0])
    """
    bits = np.asarray(binary_states, dtype=int)
    t = np.asarray(t_us, dtype=float)
    if bits.shape != t.shape:
        raise ValueError(f"binary_states shape {bits.shape} != t_us shape {t.shape}")

    window_us = float(window_us)
    if window_us <= 0:
        raise ValueError(f"window_us must be positive, got {window_us}")
    if step_us is None:
        # spec §3.2: 50% overlap. True division, not `//`: floor division on a
        # float silently truncates (1500.5 -> 750.0) and collapses to 0.0 for any
        # window_us < 2, which then makes the np.arange below raise on step=0.
        step_us = window_us / 2.0
    step_us = float(step_us)
    if step_us <= 0:
        raise ValueError(f"step_us must be positive, got {step_us}")

    if bits.size < 2:
        return {
            "window_t_us": np.zeros(0),
            "rate_Hz": np.zeros(0),
            "switches_per_window": np.zeros(0, dtype=int),
            "window_us": window_us,
            "step_us": step_us,
            "covered_us": np.zeros(0),
        }

    diffs = np.abs(np.diff(bits))  # length N-1, value 0 or 1
    if gap_indices is not None and len(gap_indices):
        # len()/iteration rather than a bare truthiness test: `if gap_indices:`
        # raises "truth value of an array is ambiguous" for a numpy array.
        for gi in gap_indices:
            gi = int(gi)
            if 1 <= gi < bits.size:
                diffs[gi - 1] = 0

    # diffs[i] corresponds to a transition that occurred between t[i] and t[i+1];
    # assign that switch event the timestamp t[i+1].
    t_event = t[1:]

    # Build windows
    t_start = t[0]
    t_end = t[-1]
    if t_end - t_start < window_us:
        # Record shorter than one window: a single window covering the whole
        # trace. Divide by the time actually covered, not by the nominal
        # window_us, which would under-report the rate by (covered/window).
        starts = np.array([t_start])
        covered = np.array([max(t_end - t_start, 0.0)])
    else:
        starts = np.arange(t_start, t_end - window_us + step_us, step_us)
        # A trailing window may hang off the end of the record; credit it only
        # with the span it actually covers so its rate is not diluted either.
        covered = np.minimum(starts + window_us, t_end) - starts
    centers = starts + window_us / 2.0

    # Counting is a prefix-sum lookup, not a mask per window. The masked version
    # is O(M*N) -- for a 600k-sample record with a 1 ms window and 0.5 ms stride
    # that is ~1.4e10 element operations, i.e. many minutes per analysis.
    cum = np.concatenate(([0], np.cumsum(diffs)))
    lo = np.searchsorted(t_event, starts, side="left")
    hi = np.searchsorted(t_event, starts + window_us, side="left")
    # Half-open [s, s+window) so overlapping windows never double-count a
    # boundary event. The final window closes its right edge so a switch landing
    # exactly at t_end (possible when the record length is an exact multiple of
    # the window) is counted rather than silently dropped.
    if hi.size:
        hi[-1] = np.searchsorted(t_event, starts[-1] + window_us, side="right")
    counts = (cum[hi] - cum[lo]).astype(int)

    with np.errstate(divide="ignore", invalid="ignore"):
        rate_Hz = np.where(covered > 0, counts / (covered * 1e-6), 0.0)

    return {
        "window_t_us": centers,
        "rate_Hz": rate_Hz,
        "switches_per_window": counts,
        "window_us": window_us,
        "step_us": step_us,
        "covered_us": covered,
    }


def detect_bursts(rate_Hz, window_t_us, baseline_rate=None, k_sigma=5,
                  min_duration_us=None, window_us=None):
    """
    Identify contiguous high-rate windows as bursts above a robust baseline.

    Parameters
    ----------
    rate_Hz       : array (M,) of switch rates per window (output of
                    sliding_window_switch_rate)
    window_t_us   : array (M,) of window center times
    baseline_rate : float or None; defaults to median(rate_Hz) (robust)
    k_sigma       : float; threshold = baseline + k_sigma * sigma
    min_duration_us : float or None; filter bursts shorter than this
    window_us     : float or None; the sliding-window duration used to produce
                    `rate_Hz`. Used to derive the rate quantum (one switch per
                    window) for the Poisson sigma floor. If None it is estimated
                    from the smallest nonzero rate.

    Threshold model
    ---------------
    sigma is the larger of the robust scale `1.4826 * MAD(rate_Hz)` (MAD taken
    about the *median* of rate_Hz, per spec §3.3) and a Poisson counting floor.
    In the normal regime most windows contain zero switches, so >50% of the
    rates are identical and MAD collapses to 0; a bare `baseline + k_sigma*0`
    threshold would then flag every window holding even one switch as a burst.
    The Poisson floor `sigma_floor = q * sqrt(max(baseline_counts, 1))`, where
    `q = 1/(window_us*1e-6)` is the rate per single switch, keeps the threshold
    a statistically meaningful margin above baseline tunneling.

    Returns
    -------
    list of dicts, one per burst, with keys:
      t_start_us, t_end_us, duration_us,
      peak_rate_Hz, mean_rate_Hz, integrated_excess_switches,
      baseline_rate_Hz, threshold_Hz
    """
    rate = np.asarray(rate_Hz, dtype=float)
    centers = np.asarray(window_t_us, dtype=float)
    if rate.shape != centers.shape:
        raise ValueError(f"rate {rate.shape} and centers {centers.shape} differ")
    if rate.size == 0:
        return []

    median_rate = float(np.median(rate))
    if baseline_rate is None:
        baseline_rate = median_rate
    # MAD is a property of the rate distribution: always centered on the median,
    # independent of the (possibly caller-supplied) baseline (spec §3.3).
    mad = float(np.median(np.abs(rate - median_rate)))
    sigma = 1.4826 * mad

    # Rate quantum: the rate corresponding to a single switch in one window.
    if window_us is not None and window_us > 0:
        q = 1.0 / (float(window_us) * 1e-6)
    else:
        positive = rate[rate > 0]
        q = float(np.min(positive)) if positive.size else 0.0
    if q > 0:
        baseline_counts = max(baseline_rate, 0.0) / q
        sigma_floor = q * np.sqrt(max(baseline_counts, 1.0))
        sigma = max(sigma, sigma_floor)

    threshold = baseline_rate + k_sigma * sigma

    above = rate > threshold
    if not np.any(above):
        return []

    # Find contiguous runs of True
    edges = np.diff(above.astype(int))
    starts = list(np.where(edges == 1)[0] + 1)
    ends = list(np.where(edges == -1)[0] + 1)
    if above[0]:
        starts = [0] + starts
    if above[-1]:
        ends = ends + [above.size]

    # Two different lengths are needed here and conflating them was a bug:
    #   stride  -- spacing between window centers (== step_us). Correct weight for
    #              the Riemann sum in integrated_excess_switches, because with
    #              overlapping windows each window "owns" only one stride of time.
    #   span    -- the time each window actually covers (== window_us). Correct
    #              basis for a burst's start/end/duration.
    # Using stride for the extent made a single above-threshold window report
    # window_us/2 of duration under the default 50% overlap, so min_duration_us
    # was silently compared against half the real value.
    if centers.size >= 2:
        stride = float(np.median(np.diff(centers)))
    else:
        stride = float(window_us) if window_us else 0.0
    if window_us is not None and window_us > 0:
        span = float(window_us)
    else:
        # window_us not supplied: the best available proxy for the covered span
        # is the center spacing (exact only for non-overlapping windows).
        span = stride

    bursts = []
    for s, e in zip(starts, ends):
        # Extent spans from the left edge of the first flagged window to the
        # right edge of the last, i.e. +/- half a WINDOW about each center.
        t_start = float(centers[s] - span / 2.0)
        t_end = float(centers[e - 1] + span / 2.0)
        duration = t_end - t_start
        if min_duration_us is not None and duration < min_duration_us:
            continue
        seg = rate[s:e]
        bursts.append({
            "t_start_us": t_start,
            "t_end_us": t_end,
            "duration_us": duration,
            "peak_rate_Hz": float(np.max(seg)),
            "mean_rate_Hz": float(np.mean(seg)),
            "integrated_excess_switches": float(
                np.sum((seg - baseline_rate)) * (stride * 1e-6)
            ),
            "baseline_rate_Hz": baseline_rate,
            "threshold_Hz": threshold,
        })
    return bursts


def _gap_segment_edges(gap_indices, n):
    """Segment boundaries ``[0, ...valid gaps..., n]`` for a length-n trace.

    Keeps only gap indices strictly inside the trace (``0 < g < n``); out-of-range
    entries (negative, 0, or >= n) are dropped as boundary no-ops. Returned edges
    are sorted and unique, so zipping consecutive pairs yields non-overlapping
    ``[a, b)`` segments that never span an acquisition gap.

    Accepts a list, a tuple, a numpy array, or None. The array case matters: the
    acquisition modules hand back ``gap_indices`` as an ndarray, and a bare
    ``gap_indices or []`` raises "truth value of an array is ambiguous" on any
    array (including, under numpy 2, an empty one).
    """
    if gap_indices is None:
        return [0, n]
    valid = sorted({int(g) for g in np.asarray(gap_indices).ravel().tolist()
                    if 0 < int(g) < n})
    return [0, *valid, n]


def _debounce_bits(bits, min_len):
    """Merge runs shorter than min_len into the neighbouring run (single segment).

    A too-short run is absorbed into the run on its left; the leading run, having
    no left neighbour, takes the state of the run on its right. One left-to-right
    sweep suffices and terminates: an absorbed run only ever extends the run being
    built, so nothing needs revisiting.

    The previous implementation re-encoded the whole array after each individual
    merge -- O(short_runs x N), i.e. 10^10+ element ops on a real
    multi-million-sample record with a few percent misclassification -- and, worse,
    **looped forever** on a segment consisting of a single too-short run: with one
    run neither the left nor the right neighbour exists, so it set changed=True
    without modifying anything and the `while changed` loop never exited. That is
    reachable from _bin_iq_time's gap bookkeeping whenever a segment reduces to
    one bin, and from any 1-sample trace.
    """
    bits = np.asarray(bits).astype(int).copy()
    if bits.size == 0 or min_len <= 1:
        return bits

    edges = np.flatnonzero(np.diff(bits)) + 1
    starts = np.concatenate(([0], edges))
    ends = np.concatenate((edges, [bits.size]))
    lengths = ends - starts

    # A single run has nothing to merge into. Return it unchanged instead of
    # spinning; the caller's dwell statistics then honestly report one short run,
    # which is the correct description of a one-bin segment.
    if starts.size == 1:
        return bits

    # Build the merged run list as (state, length) pairs, absorbing every
    # too-short run into the run being accumulated on its left. Adjacent runs that
    # end up in the same state coalesce, which is what lets a recoloured flicker
    # join the runs on both sides of it.
    merged = []  # list of [state, length]
    for i in range(starts.size):
        state_i = int(bits[starts[i]])
        if merged and (lengths[i] < min_len or state_i == merged[-1][0]):
            merged[-1][1] += int(lengths[i])
        else:
            merged.append([state_i, int(lengths[i])])

    # The leading run has no left neighbour, so the sweep above could not absorb
    # it. If it is still short, hand it to the run on its right (and coalesce, in
    # case that leaves two same-state neighbours). Each pass removes one run, so
    # this terminates.
    while len(merged) > 1 and merged[0][1] < min_len:
        merged[1][1] += merged[0][1]
        merged.pop(0)
        if len(merged) > 1 and merged[0][0] == merged[1][0]:
            merged[1][1] += merged[0][1]
            merged.pop(0)

    pos = 0
    for state, length in merged:
        bits[pos:pos + length] = state
        pos += length
    return bits


def _infer_sample_period(t, breakpoints=None):
    """Sample period of a (possibly chunk-stitched) time axis, in us.

    Uses the first *interior* difference of the first segment that has one. A bare
    ``t[1] - t[0]`` is wrong whenever the leading segment is a single sample: that
    difference then spans an acquisition gap, which is not a sample period, and it
    would propagate into every binning and last-run-duration calculation.
    Returns 0.0 when no interior difference exists anywhere.
    """
    t = np.asarray(t, dtype=float).ravel()
    if t.size < 2:
        return 0.0
    if breakpoints is None:
        breakpoints = [0, t.size]
    for a, b in zip(breakpoints[:-1], breakpoints[1:]):
        if b - a >= 2:
            return float(t[a + 1] - t[a])
    # Every segment is a single sample: no interior spacing is observable.
    return 0.0


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


def dwell_time_statistics(binary_states, t_us, gap_indices=None,
                          merge_short_segments=False, min_dwell_bins=1):
    """
    Lengths of contiguous runs in state 0 and state 1, in microseconds.

    Runs spanning a `gap_indices` boundary are split (not joined across it).

    Parameters
    ----------
    binary_states : array_like of int (0 or 1), shape (N,)
    t_us          : array_like of float, shape (N,), monotonically increasing
    gap_indices   : list[int] or None, acquisition-boundary indices; runs are
                    split at these, never joined across them
    merge_short_segments : bool, enable debouncing (default False, preserving the
                    original behaviour for existing callers)
    min_dwell_bins : int, with merge_short_segments=True, runs shorter than this
                    many samples are absorbed into a neighbouring run before the
                    run-length statistics are computed. A single marginal-SNR
                    threshold flicker otherwise reads as two parity switches and
                    biases tau sharply low.

    Returns
    -------
    dict with keys:
      dwell_0_us, dwell_1_us : array of dwell durations (us)
      mean_0, mean_1         : float, mean dwell time per state (nan if no runs)
      n_runs_0, n_runs_1     : int, run counts
      exp_fit_0, exp_fit_1   : dict {"tau_us", "A", "bins_used"}; nans if the fit
                               fails
    """
    binary_states = np.asarray(binary_states).astype(int)
    t = np.asarray(t_us, dtype=float)
    # Check before debouncing so a caller passing mismatched arrays gets a clear
    # error rather than an IndexError from the seg_t[re] lookup below (or, for a
    # too-long t_us, silently wrong dwell times).
    if binary_states.shape != t.shape:
        raise ValueError(
            f"binary_states shape {binary_states.shape} != t_us shape {t.shape}"
        )
    if merge_short_segments and min_dwell_bins > 1:
        binary_states = _debounce_bits_segmented(binary_states, gap_indices, min_dwell_bins)
    bits = np.asarray(binary_states, dtype=int)
    n = bits.size
    if n == 0:
        return {
            "dwell_0_us": np.zeros(0), "dwell_1_us": np.zeros(0),
            "mean_0": float("nan"), "mean_1": float("nan"),
            "n_runs_0": 0, "n_runs_1": 0,
            "exp_fit_0": {"tau_us": float("nan"), "A": float("nan")},
            "exp_fit_1": {"tau_us": float("nan"), "A": float("nan")},
        }

    # Break trace into segments at gap_indices, run-length encode each segment.
    # Out-of-range entries (negative, 0, or >= n) are dropped as boundary no-ops
    # to avoid IndexError from numpy slice wraparound.
    breakpoints = _gap_segment_edges(gap_indices, n)
    # Global sample period, recoverable from the whole trace even when an
    # individual segment is a single sample. Used to extrapolate the duration of
    # the last run in each segment. Take it from the first segment's interior, not
    # from t[1]-t[0] blindly: if the very first segment is one sample long, that
    # difference straddles an acquisition gap and is not a sample period at all.
    global_sp = _infer_sample_period(t, breakpoints)
    dwells_0, dwells_1 = [], []
    for a, b in zip(breakpoints[:-1], breakpoints[1:]):
        if b <= a:
            continue
        seg = bits[a:b]
        seg_t = t[a:b]
        # Run-length encode. `r_end` rather than `re`: the latter shadows the
        # stdlib module name.
        change_idx = np.where(np.diff(seg) != 0)[0] + 1
        run_starts = np.concatenate(([0], change_idx))
        run_ends = np.concatenate((change_idx, [seg.size]))
        for rs, r_end in zip(run_starts, run_ends):
            state = int(seg[rs])
            # Duration: time from first sample in run to first sample after run
            if r_end < seg.size:
                duration = float(seg_t[r_end] - seg_t[rs])
            else:
                # Last run in segment: extrapolate using the sample period.
                # Prefer the segment's own period; fall back to the global
                # period so a single-sample segment yields ~one period, not 0.
                if seg.size >= 2:
                    sp = float(seg_t[1] - seg_t[0])
                else:
                    sp = global_sp
                duration = float(seg_t[r_end - 1] - seg_t[rs]) + sp
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


_SCATTER_MAX_PTS = 50_000


def _plot_iq_scatter(I, Q, bits, separator, out_path):
    fig, ax = plt.subplots(figsize=(6, 6))
    I = np.asarray(I)
    Q = np.asarray(Q)
    bits = np.asarray(bits)
    for state, label in ((0, "state 0"), (1, "state 1")):
        sel = bits == state
        # Subsample: at a few million points the markers are fully saturated
        # anyway, so plotting them all only costs render time and PNG size.
        ax.scatter(_subsample(I[sel], _SCATTER_MAX_PTS),
                   _subsample(Q[sel], _SCATTER_MAX_PTS),
                   s=1, alpha=0.3, label=label)
    g = np.asarray(separator["g_center"], dtype=float)
    e = np.asarray(separator["e_center"], dtype=float)
    ax.plot([g[0], e[0]], [g[1], e[1]], "k--", lw=1)
    ax.scatter([g[0], e[0]], [g[1], e[1]], c="k", marker="x", s=60, label="separator")
    ax.set_xlabel("I"); ax.set_ylabel("Q"); ax.legend(loc="best", markerscale=4)
    ax.set_title("Parity IQ scatter")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_parity_vs_time(bits, t_us, out_path, max_pts=100_000):
    fig, ax = plt.subplots(figsize=(10, 3))
    n = bits.size
    if n > max_pts:
        # Downsample to max_pts time bins (mean state per bin) so PNG generation
        # stays well under ~1 s even for multi-million-sample records.
        time_bins = np.linspace(t_us[0], t_us[-1], max_pts)
        idx = np.clip(np.searchsorted(time_bins, t_us) - 1, 0, time_bins.size - 1)
        avg_state = np.bincount(idx, weights=bits.astype(float), minlength=time_bins.size)
        cnt = np.bincount(idx, minlength=time_bins.size).astype(float)
        avg_state[cnt > 0] /= cnt[cnt > 0]
        # Mask empty bins instead of leaving them at 0.0. searchsorted(...)-1
        # never assigns anything to the final bin, so the un-masked version always
        # drew a spurious plunge to state 0 at the right-hand edge of the plot
        # (and at any other bin that happened to be empty).
        avg_state = np.where(cnt > 0, avg_state, np.nan)
        ax.plot(time_bins / 1e6, avg_state, lw=0.5)
        ax.set_ylabel("mean state (downsampled)")
    else:
        ax.step(t_us / 1e6, bits, where="post", lw=0.5)
        ax.set_ylabel("parity state")
    ax.set_xlabel("time (s)")
    ax.set_title("Parity vs time")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_switch_rate(rate_out, bursts, out_path):
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(rate_out["window_t_us"] / 1e6, rate_out["rate_Hz"], lw=0.8)
    if bursts:
        baseline = bursts[0]["baseline_rate_Hz"]
        threshold = bursts[0]["threshold_Hz"]
        ax.axhline(baseline, color="gray", ls=":", label=f"baseline {baseline:.1f} Hz")
        ax.axhline(threshold, color="red", ls="--", label=f"threshold {threshold:.1f} Hz")
        for b in bursts:
            ax.axvspan(b["t_start_us"] / 1e6, b["t_end_us"] / 1e6,
                       color="red", alpha=0.15)
        ax.legend(loc="best")
    ax.set_xlabel("time (s)"); ax.set_ylabel("switch rate (Hz)")
    ax.set_title("Sliding-window switch rate")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _plot_dwell_histograms(stats, out_path):
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(10, 4))
    for ax, dwells, fit, title in [
        (ax0, stats["dwell_0_us"], stats["exp_fit_0"], "state 0 dwells"),
        (ax1, stats["dwell_1_us"], stats["exp_fit_1"], "state 1 dwells"),
    ]:
        if dwells.size > 0:
            # Use the same bin count the fit was computed on so the overlaid
            # exponential (whose amplitude A is calibrated to that bin width)
            # lines up with the plotted bars.
            nb = fit.get("bins_used") or min(30, max(5, dwells.size // 10))
            ax.hist(dwells, bins=int(nb), log=True, alpha=0.7)
            if np.isfinite(fit["tau_us"]):
                xs = np.linspace(dwells.min(), dwells.max(), 200)
                ax.plot(xs, fit["A"] * np.exp(-xs / fit["tau_us"]), "r-",
                        label=f"tau={fit['tau_us']:.1f} us")
                ax.legend()
        ax.set_xlabel("dwell (us)")
        ax.set_title(title)
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def _bin_iq_time(I, Q, t_us, bin_us, gap_indices=None):
    """
    Mean-bin (I, Q, t_us) into windows of `bin_us` microseconds.

    Bins are split across `gap_indices` so a bin never spans an acquisition
    boundary. Returns (I_b, Q_b, t_b, gap_indices_b, n_dropped) where
    n_dropped is the total number of raw samples discarded because they
    didn't fill a complete trailing bin in any segment.

    A `bin_us` below one sample period cannot bin anything; that is reported via a
    printed warning rather than silently returning the trace unchanged, because
    the caller records the *requested* bin size in its sidecar and would otherwise
    claim a binning that never happened.
    """
    I = np.ravel(np.asarray(I, dtype=float))
    Q = np.ravel(np.asarray(Q, dtype=float))
    t = np.ravel(np.asarray(t_us, dtype=float))
    if I.size == 0:
        return I, Q, t, [], 0
    segment_edges = _gap_segment_edges(gap_indices, I.size)
    # Interior spacing of the first multi-sample segment, not a bare t[1]-t[0]:
    # if the leading segment is one sample long that difference spans a chunk gap.
    sp = _infer_sample_period(t, segment_edges)
    if sp <= 0:
        sp = float(bin_us)
    bin_samples = max(1, int(round(float(bin_us) / sp)))
    if bin_samples == 1 and float(bin_us) < sp:
        print(f"[analyze_ZeroSpanParity] WARNING: analysis_bin_us={bin_us} us is "
              f"below the raw sample period ({sp} us); no binning applied.")
    I_parts, Q_parts, t_parts = [], [], []
    new_gaps = []
    cum = 0
    n_dropped = 0
    for seg_idx, (a, b) in enumerate(zip(segment_edges[:-1], segment_edges[1:])):
        n_in_seg = b - a
        n_bins = n_in_seg // bin_samples
        n_dropped += n_in_seg - n_bins * bin_samples
        if n_bins == 0:
            continue
        keep = n_bins * bin_samples
        I_seg = I[a:a + keep].reshape(n_bins, bin_samples).mean(axis=1)
        Q_seg = Q[a:a + keep].reshape(n_bins, bin_samples).mean(axis=1)
        t_seg = t[a:a + keep].reshape(n_bins, bin_samples).mean(axis=1)
        I_parts.append(I_seg); Q_parts.append(Q_seg); t_parts.append(t_seg)
        if seg_idx > 0:
            new_gaps.append(cum)
        cum += n_bins
    if not I_parts:
        return (np.zeros(0), np.zeros(0), np.zeros(0), [], int(n_dropped))
    return (np.concatenate(I_parts), np.concatenate(Q_parts),
            np.concatenate(t_parts), new_gaps, int(n_dropped))


def analyze_parity_run(h5_path, separator=None, window_us=1000.0, k_sigma=5.0,
                       classifier_method="apriori_axis", step_us=None,
                       min_burst_duration_us=None, save_plots=True, out_dir=None,
                       analysis_bin_us=None, merge_short_segments=True,
                       min_dwell_bins=2, psd_nperseg=None, psd_bin_list_us=None):
    """
    Load a ZeroSpanParity raw .h5, classify into parity bits, compute switch rate,
    detect bursts, compute dwell statistics, save plots and a sidecar.

    Parameters
    ----------
    h5_path           : str, path to raw .h5 written by ZeroSpanParity.save_data
    separator         : dict or None; required for classifier_method
                        "apriori_axis" / "apriori"
    window_us         : float, sliding-window size
    k_sigma           : float, burst threshold
    classifier_method : "apriori_axis" | "apriori" | "kmeans". Default
                        "apriori_axis": the g->e axis from the single-shot
                        calibration with a threshold taken from the trace itself.
                        Plain "apriori" thresholds at the g/e midpoint, which
                        labels an entire driven parity trace as one state — see
                        classify_parity_trace.
    step_us           : float or None, window stride
    min_burst_duration_us : float or None
    save_plots        : bool
    out_dir           : str or None; defaults to directory of h5_path
    analysis_bin_us   : float or None
        Mean-bin the trace into this many microseconds before classification.
        Default: None (no binning). Per-sample SNR in a decimated trace is
        much lower than a strobe sample; if the apriori separator is in
        single-shot units, pass an explicit `analysis_bin_us` (e.g. equal
        to one read_length, or a fraction of it for finer time resolution).
        Real decimated captures cover a single `read_length` end-to-end,
        so binning by the full read_length collapses the capture to one
        point — choose a fraction.
    merge_short_segments, min_dwell_bins
        Dwell-time debouncing, ON by default. Runs shorter than
        `min_dwell_bins` samples are absorbed into a neighbour before the dwell
        statistics are computed. Without this, a single-sample classification
        flicker reads as two parity switches, which biases the reported tau low
        by more than 2x at only a few percent misclassification (see the
        debounce test in __main__) and inflates the switch rate and hence the
        burst threshold. Pass merge_short_segments=False for the raw,
        un-debounced statistics.
    psd_nperseg : int or None
        Welch window length for the threshold-free PSD rate (parity_psd_rate),
        which is always computed alongside the counted rate. Default None lets
        segmented_welch_psd pick a window giving ~8 averages. Increase it to
        reach a lower corner frequency (at the cost of averaging); decrease it
        for a short record.
    psd_bin_list_us : sequence of float or None
        When given, also run the bin-size invariance check (psd_rate_vs_bin) on
        the RAW un-binned IQ and report `psd_f_c_cv_vs_bin`. A real telegraph
        holds one f_c across bin sizes; threshold noise crossings do not. Off by
        default because it re-processes the whole trace once per bin size.
        Include 0 in the list for the un-binned trace.

    Returns
    -------
    dict with scalar summary fields (matches sidecar JSON).

    The `psd_*` fields are the threshold-free cross-check. When
    `psd_transitions_per_s_symmetric` and `baseline_rate_Hz` disagree by more
    than about 2x, trust the PSD: the counted rate is the one that absorbs
    classification error. `psd_is_lorentzian=False` on a trace with a healthy
    `separation_snr` means there is no resolvable telegraph in the record, which
    is a result about the data and not about the threshold.
    """
    if out_dir is None:
        out_dir = os.path.dirname(h5_path) or "."
    base = os.path.splitext(os.path.basename(h5_path))[0]

    with h5py.File(h5_path, "r") as f:
        I = np.array(f["I"])
        Q = np.array(f["Q"])
        t_us = np.array(f["t_us"])
        gap_indices = [int(g) for g in np.array(f["gap_indices"])] if "gap_indices" in f else []
        sample_period_us = float(f.attrs.get(
            "sample_period_us",
            _infer_sample_period(t_us, _gap_segment_edges(gap_indices, t_us.size))))
        mode = str(f.attrs.get("mode", "strobe"))

    raw_sample_period_us = sample_period_us
    n_raw_samples = int(I.size)
    n_binned_samples = int(I.size)
    n_dropped = 0
    # Hold references to the UN-binned arrays only when the bin-size invariance
    # check is requested — it has to sweep bin sizes from the raw trace, and the
    # rebinding below would otherwise drop them. Conditional because a
    # multi-million-sample record is not free to keep twice.
    raw_for_psd = ((I, Q, t_us, list(gap_indices)) if psd_bin_list_us is not None
                   and len(list(psd_bin_list_us)) > 1 else None)
    # Do NOT auto-bin: the spec's Path B intent is a raw decimated waveform.
    # Binning by the declared `read_length_us` would collapse the whole
    # capture to a single point (decimated mode captures one read_length
    # end-to-end). Callers that need integrated bins must pass
    # `analysis_bin_us` explicitly.
    if analysis_bin_us and float(analysis_bin_us) > 0:
        I, Q, t_us, gap_indices, n_dropped = _bin_iq_time(
            I, Q, t_us, float(analysis_bin_us), gap_indices=gap_indices
        )
        n_binned_samples = int(I.size)
        binned_sp = _infer_sample_period(
            t_us, _gap_segment_edges(gap_indices, t_us.size))
        if binned_sp > 0:
            sample_period_us = binned_sp

    cls = classify_parity_trace(I, Q, separator=separator, method=classifier_method)
    bits = cls["binary_states"]
    sep_used = cls["separator_used"]

    # Debounce BEFORE the switch rate as well as the dwell statistics: a
    # single-sample flicker contributes two switches to every window it lands in,
    # which raises the baseline rate and therefore the burst threshold. Both
    # derived quantities must see the same bit sequence or the reported rate and
    # the reported dwell times describe different traces.
    bits_stats = (_debounce_bits_segmented(bits, gap_indices, min_dwell_bins)
                  if (merge_short_segments and min_dwell_bins > 1) else bits)

    rate_out = sliding_window_switch_rate(bits_stats, t_us, window_us=window_us,
                                          step_us=step_us, gap_indices=gap_indices)
    bursts = detect_bursts(rate_out["rate_Hz"], rate_out["window_t_us"],
                           baseline_rate=None, k_sigma=k_sigma,
                           min_duration_us=min_burst_duration_us,
                           window_us=rate_out["window_us"])
    # Already debounced above; don't do it twice (it is idempotent, but passing
    # the flag again would hide which sequence the statistics were computed on).
    stats = dwell_time_statistics(bits_stats, t_us, gap_indices=gap_indices)

    # Threshold-free cross-check on the SAME projected trace. Deliberately fed
    # cls["scores"], NOT bits or bits_stats: the whole point is that it never sees
    # a threshold or the debounce, so its answer cannot inherit their biases.
    psd_out = parity_psd_rate(cls["scores"], t_us=t_us,
                              sample_period_us=sample_period_us,
                              gap_indices=gap_indices, nperseg=psd_nperseg)
    psd_sweep = None
    if raw_for_psd is not None:
        I_r, Q_r, t_r, g_r = raw_for_psd
        psd_sweep = psd_rate_vs_bin(I_r, Q_r, t_r, separator=separator,
                                    bin_list_us=list(psd_bin_list_us),
                                    gap_indices=g_r, nperseg=psd_nperseg)

    if save_plots:
        _plot_iq_scatter(I, Q, bits_stats, sep_used,
                          os.path.join(out_dir, base + "_iq_scatter.png"))
        _plot_parity_vs_time(bits_stats, t_us,
                              os.path.join(out_dir, base + "_parity_vs_time.png"))
        _plot_switch_rate(rate_out, bursts,
                           os.path.join(out_dir, base + "_switch_rate_vs_time.png"))
        _plot_dwell_histograms(stats,
                                os.path.join(out_dir, base + "_dwell_histograms.png"))
        _plot_psd(psd_out, os.path.join(out_dir, base + "_psd.png"),
                  title=f"Parity PSD — {base}")

    baseline_rate = (bursts[0]["baseline_rate_Hz"] if bursts
                     else float(np.median(rate_out["rate_Hz"])
                                if rate_out["rate_Hz"].size else 0.0))
    summary = {
        "h5_path": h5_path,
        "sample_period_us": sample_period_us,
        "raw_sample_period_us": raw_sample_period_us,
        "n_samples": int(bits.size),
        "n_raw_samples": n_raw_samples,
        "n_binned_samples": n_binned_samples,
        "n_samples_dropped_by_binning": int(n_dropped),
        "analysis_bin_us": float(analysis_bin_us) if analysis_bin_us else 0.0,
        "mode": mode,
        "n_bursts": len(bursts),
        "baseline_rate_Hz": baseline_rate,
        "mean_dwell_0_us": stats["mean_0"],
        "mean_dwell_1_us": stats["mean_1"],
        "n_runs_0": stats["n_runs_0"],
        "n_runs_1": stats["n_runs_1"],
        "exp_fit_tau_0_us": stats["exp_fit_0"]["tau_us"],
        "exp_fit_tau_1_us": stats["exp_fit_1"]["tau_us"],
        "classifier_method": cls["method"],
        # The decision threshold actually applied, in projected-score units. Zero
        # for "apriori"/"kmeans" (midpoint by construction); data-derived for
        # "apriori_axis". Recorded so a re-analysis can reproduce the labels.
        "classifier_threshold": float(cls.get("threshold", 0.0)),
        "merge_short_segments": bool(merge_short_segments),
        "min_dwell_bins": int(min_dwell_bins),
        # --- threshold-free PSD rate (see parity_psd_rate) --------------------
        "psd_f_c_hz": psd_out["f_c_hz"],
        "psd_f_c_err_hz": psd_out["f_c_err_hz"],
        "psd_gamma_total_hz": psd_out["gamma_total_hz"],
        "psd_transitions_per_s_symmetric": psd_out["transitions_per_s_symmetric"],
        "psd_tau_symmetric_us": psd_out["tau_symmetric_us"],
        "psd_lorentzian_snr": psd_out["lorentzian_snr"],
        "psd_s_white": psd_out["s_white"],
        "psd_s_0": psd_out["s_0"],
        "psd_r2": psd_out["r2"],
        "psd_delta_bic": psd_out["delta_bic"],
        "psd_exponent_free": psd_out["exponent_free"],
        "psd_exponent_consistent_with_rts": bool(
            psd_out["exponent_consistent_with_rts"]),
        "psd_is_lorentzian": bool(psd_out["is_lorentzian"]),
        "psd_verdict": psd_out["verdict"],
        "psd_reason": psd_out["reason"],
        "psd_nperseg_used": psd_out["nperseg_used"],
        "psd_f_resolution_hz": psd_out["f_resolution_hz"],
        "psd_f_nyquist_hz": psd_out["f_nyquist_hz"],
        "psd_n_segments_used": psd_out["n_segments_used"],
        "psd_n_segments_skipped": psd_out["n_segments_skipped"],
        "psd_n_averages": psd_out["n_averages"],
        # Ratio of the two independent estimates of the same quantity. Near 1
        # means the counted rate is trustworthy; >> 1 means the counted rate is
        # dominated by classification flicker, << 1 means the counting is
        # saturating (rate approaching 1/(2*sample_period)) or the debounce dead
        # time is swallowing real switches.
        "counted_over_psd_rate": (
            float(baseline_rate / psd_out["transitions_per_s_symmetric"])
            if np.isfinite(psd_out["transitions_per_s_symmetric"])
            and psd_out["transitions_per_s_symmetric"] > 0 else float("nan")),
    }
    if psd_sweep is not None:
        summary["psd_f_c_cv_vs_bin"] = psd_sweep["f_c_cv"]
        summary["psd_f_c_mean_vs_bin_hz"] = psd_sweep["f_c_mean_hz"]
        summary["psd_n_bins_used_for_cv"] = psd_sweep["n_bins_used"]

    # Write sidecars
    with open(os.path.join(out_dir, base + "_analysis.json"), "w") as f:
        json.dump({**summary,
                   "bursts": bursts,
                   "window_us": rate_out["window_us"],
                   "step_us": rate_out["step_us"],
                   **({"psd_bin_sweep": psd_sweep} if psd_sweep is not None else {})},
                  f, indent=2, default=lambda x: x.tolist()
                  if isinstance(x, np.ndarray) else float(x))
    with h5py.File(os.path.join(out_dir, base + "_analysis.h5"), "w") as f:
        # binary_states is the DEBOUNCED sequence the statistics were computed on;
        # binary_states_raw is the direct classifier output, so a reader can see
        # exactly what debouncing changed.
        f.create_dataset("binary_states", data=bits_stats)
        f.create_dataset("binary_states_raw", data=bits)
        f.create_dataset("scores", data=cls["scores"])
        f.create_dataset("window_t_us", data=rate_out["window_t_us"])
        f.create_dataset("rate_Hz", data=rate_out["rate_Hz"])
        f.create_dataset("dwell_0_us", data=stats["dwell_0_us"])
        f.create_dataset("dwell_1_us", data=stats["dwell_1_us"])
        # Full Welch spectrum plus the log-binned points the Lorentzian was
        # actually fitted to, so the fit can be re-examined without re-reading
        # (and re-projecting) the raw trace.
        f.create_dataset("psd_f_hz", data=psd_out["f_hz"])
        f.create_dataset("psd", data=psd_out["psd"])
        f.create_dataset("psd_f_hz_binned", data=psd_out["f_hz_binned"])
        f.create_dataset("psd_binned", data=psd_out["psd_binned"])
        for k, v in summary.items():
            try:
                f.attrs[k] = v
            except TypeError:
                f.attrs[k] = str(v)
    return summary


def verify_modulation(scores, t_us, modulation_reference, gap_indices=None):
    """Confirm a recovered projected trace carries an injected on/off square wave.

    Judge the gate on these, in this order:
      block_tstat / block_snr : significance of the on-vs-off difference of the
          per-block MEANS. This is the figure of merit -- the injected schedule is
          constant within a block, so that is where the signal is. `snr` below is
          the same difference divided by the PER-SAMPLE spread, which understates
          it by sqrt(samples_per_block) (~22x at the default 500) and can read 0.5
          for a modulation that is in fact overwhelming.
      recovered_freq_hz vs injected_freq_hz : independent and very sharp. If the
          FFT of the recovered trace lands on the injected frequency, the
          modulation is in the data and the time axis is right.
      correlation, lag_samples : sign and alignment check, evaluated only within
          |lag| <= 4 samples because the schedule is software-aligned (lag is 0 by
          construction). A negative correlation here is a real failure.
      level_on / level_off / modulation_depth : the raw contrast, in score units.

    `gap_indices` marks acquisition-boundary indices in a stitched trace. It
    matters here: the only caller (validate_ZeroSpanParity.run_modulation_check)
    feeds the output of modulated_strobe_acquire, where every modulation half-
    period is its own block, so the trace has the densest gap structure in the
    codebase and the stitched t_us does not contain the real inter-block dead
    time. The correlation/lag are therefore computed per gap-free segment and
    combined (weighted by segment length) rather than across boundaries, and the
    FFT diagnostic runs on the longest single segment.

    level_on/level_off/modulation_depth/snr are block-mean statistics and are
    unaffected by gaps, so they use the whole trace.
    """
    scores = np.asarray(scores, dtype=float).ravel()
    ref = np.asarray(modulation_reference, dtype=float).ravel()
    t_us = np.asarray(t_us, dtype=float).ravel()
    out = {"level_on": np.nan, "level_off": np.nan, "modulation_depth": np.nan,
           "snr": np.nan, "correlation": np.nan, "lag_samples": 0,
           "recovered_freq_hz": np.nan, "injected_freq_hz": np.nan,
           "n_segments_used": 0, "block_level_on": np.nan,
           "block_level_off": np.nan, "block_snr": np.nan,
           "block_tstat": np.nan, "n_blocks_on": 0, "n_blocks_off": 0,
           "correlation_lag0": np.nan, "block_separation_auc": np.nan,
           "blocks_fully_separated": False}
    n = min(scores.size, ref.size, t_us.size)
    if n < 2:
        return out
    scores, ref, t_us = scores[:n], ref[:n], t_us[:n]
    on = ref > 0.5
    off = ~on
    if on.sum() == 0 or off.sum() == 0:
        return out
    level_on = float(np.mean(scores[on]))
    level_off = float(np.mean(scores[off]))
    pooled = float(np.sqrt(0.5 * (np.var(scores[on]) + np.var(scores[off]))))
    out["level_on"] = level_on
    out["level_off"] = level_off
    out["modulation_depth"] = abs(level_on - level_off)
    # Per-sample significance of the level split. Keep it for continuity, but note
    # it is NOT the figure of merit for a block schedule: the modulation is
    # constant within a block, so its significance grows as sqrt(block length).
    # Judging a block-modulated signal by per-sample SNR understates it by
    # sqrt(samples_per_block) -- a factor of ~22 at the default 500-sample blocks,
    # which is the difference between "0.5, hopeless" and "12, unambiguous".
    out["snr"] = abs(level_on - level_off) / pooled if pooled > 0 else np.inf

    segments = [(a, b) for a, b in
                zip(*(lambda e: (e[:-1], e[1:]))(_gap_segment_edges(gap_indices, n)))
                if b - a >= 2]
    if not segments:
        segments = [(0, n)]
    out["n_segments_used"] = len(segments)

    # --- block-level SNR: the statistic that actually answers the question -----
    # Average each gap-delimited block, then ask how well the per-block means
    # separate into on vs off. This is where an injected block schedule lives.
    blk_on, blk_off = [], []
    for a, b in segments:
        m = float(np.mean(ref[a:b]))
        val = float(np.mean(scores[a:b]))
        (blk_on if m > 0.5 else blk_off).append(val)
    out["n_blocks_on"] = len(blk_on)
    out["n_blocks_off"] = len(blk_off)
    if blk_on and blk_off:
        bon, boff = np.asarray(blk_on), np.asarray(blk_off)
        out["block_level_on"] = float(bon.mean())
        out["block_level_off"] = float(boff.mean())
        d = abs(out["block_level_on"] - out["block_level_off"])
        # Welch, not pooled-variance. The two groups routinely have very different
        # spreads -- a driven block's steady state wanders (Rabi structure, drift,
        # heating) while an undriven block just sits at |g> -- and pooling then lets
        # the noisy group inflate the denominator for BOTH, understating a cleanly
        # separated result.
        von = float(bon.var(ddof=1)) if bon.size > 1 else 0.0
        voff = float(boff.var(ddof=1)) if boff.size > 1 else 0.0
        se = float(np.sqrt(von / max(bon.size, 1) + voff / max(boff.size, 1)))
        out["block_tstat"] = (d / se) if se > 0 else np.inf
        sb = float(np.sqrt(0.5 * (von + voff)))
        out["block_snr"] = (d / sb) if sb > 0 else np.inf
        # Assumption-free separation: what fraction of on/off block pairs are
        # correctly ordered (the Mann-Whitney / AUC statistic). 1.0 means every
        # driven block sits above every undriven one -- the strongest statement
        # available from N blocks, and immune to either group's spread. With 10 vs
        # 10 blocks, a perfect split is p ~ 1e-5 under the null.
        wins = float(np.sum(bon[:, None] > boff[None, :]))
        ties = float(np.sum(bon[:, None] == boff[None, :]))
        out["block_separation_auc"] = (wins + 0.5 * ties) / (bon.size * boff.size)
        out["blocks_fully_separated"] = bool(bon.min() > boff.max()
                                             or boff.min() > bon.max())

    # --- normalised cross-correlation at the KNOWN alignment -------------------
    # The reference is a SOFTWARE schedule: block k had its gain applied during
    # block k, so the true lag is 0 by construction and only a couple of samples of
    # slack are physically possible. Scanning the full +/-N lag range with
    # argmax(|corr|) is actively wrong for a periodic reference: at lag 0 the
    # correlation is +max and at lag half-period it is -max, with nearly equal
    # magnitude, so the argmax picks between them on the strength of finite-window
    # effects and any slow drift in the scores. That is how a perfectly good
    # modulation came back as correlation = -0.27 at a nonsense lag of 2000
    # samples (80 ms). Search only |lag| <= max_lag and report the SIGNED value.
    s = scores - scores.mean()
    r = ref - ref.mean()
    denom = float(np.sqrt(np.sum(s * s) * np.sum(r * r)))
    if denom > 0:
        max_lag = 4
        lags = np.arange(-max_lag, max_lag + 1)
        vals = []
        for L in lags:
            if L >= 0:
                a1, b1 = s[L:], r[:n - L] if L else r
            else:
                a1, b1 = s[:n + L], r[-L:]
            vals.append(float(np.dot(a1, b1) / denom))
        vals = np.asarray(vals)
        # Signed: take the largest correlation, not the largest magnitude. An
        # anti-correlated result is a genuine failure and must be reported as
        # negative, not silently turned into a pass.
        k = int(np.argmax(vals))
        out["correlation"] = float(vals[k])
        out["lag_samples"] = int(lags[k])
        out["correlation_lag0"] = float(vals[int(np.where(lags == 0)[0][0])])

    # Injected freq from the reference. Transitions ACROSS a gap are still real
    # modulation edges -- the schedule alternated -- so count over the whole
    # trace, but measure the duration as the sum of the segment spans, plus one
    # sample period per segment, so the unrecorded inter-block dead time is not
    # billed as signal time.
    #
    # Half-periods = transitions + 1, not transitions: a block schedule starts and
    # ends ON half-period boundaries, so N alternating blocks show N-1 interior
    # transitions while covering N half-periods. Counting transitions alone
    # under-reports the frequency by (N-1)/N (12% at the default 8 periods).
    sp_us = _infer_sample_period(t_us, _gap_segment_edges(gap_indices, n))
    duration_s = float(sum((t_us[b - 1] - t_us[a]) + sp_us
                           for a, b in segments)) * 1e-6
    transitions = int(np.count_nonzero(np.diff((ref > 0.5).astype(int))))
    if duration_s > 0 and transitions > 0:
        out["injected_freq_hz"] = ((transitions + 1) / 2.0) / duration_s
    # Recovered freq from the dominant FFT bin (diagnostic only).
    #
    # It must be computed on the BLOCK-MEAN sequence, not on a single gap-free
    # segment. With the standard schedule of one block per half-period, every
    # segment has a CONSTANT reference -- no segment contains any modulation at all,
    # so an FFT of one segment is an FFT of drift and noise, and the number it
    # returns is meaningless (it happily reported 25 Hz for a 6.25 Hz schedule).
    #
    # The block means are uniformly spaced in block index, so treat one block as one
    # sample of period (samples_per_block * sample_period). That is where the square
    # wave lives, and it makes the diagnostic sharp.
    sp_us = _infer_sample_period(t_us, _gap_segment_edges(gap_indices, n))
    blk_means, blk_len = [], []
    for a, b in segments:
        blk_means.append(float(np.mean(scores[a:b])))
        blk_len.append(b - a)
    blk_means = np.asarray(blk_means, dtype=float)
    if blk_means.size > 4 and sp_us > 0 and len(set(blk_len)) == 1:
        block_us = blk_len[0] * sp_us
        freqs = np.fft.rfftfreq(blk_means.size, d=block_us * 1e-6)
        spec = np.abs(np.fft.rfft(blk_means - blk_means.mean()))
        if spec.size > 1:
            out["recovered_freq_hz"] = float(freqs[1:][int(np.argmax(spec[1:]))])
    elif blk_means.size <= 4:
        # Too few blocks for a block-domain FFT; fall back to the longest segment
        # and flag it, rather than reporting a confident wrong number.
        a, b = max(segments, key=lambda ab: ab[1] - ab[0])
        m = b - a
        dt_us = float(np.median(np.diff(t_us[a:b]))) if m > 1 else 0.0
        if dt_us > 0 and m > 4:
            freqs = np.fft.rfftfreq(m, d=dt_us * 1e-6)
            seg_s = scores[a:b]
            spec = np.abs(np.fft.rfft(seg_s - seg_s.mean()))
            if spec.size > 1:
                out["recovered_freq_hz"] = float(freqs[1:][int(np.argmax(spec[1:]))])
        out["recovered_freq_source"] = "longest_segment_too_few_blocks"
    out.setdefault("recovered_freq_source", "block_means")
    return out


def contrast_from_sweeps(freqs, Z_on, Z_off):
    """|Z_on - Z_off|(f), best probe freq, robust contrast SNR.

    Z_on/Z_off are complex demodulated responses (proportional to S21, NOT
    calibrated S21).
    """
    freqs = np.asarray(freqs, dtype=float).ravel()
    Z_on = np.asarray(Z_on).ravel()
    Z_off = np.asarray(Z_off).ravel()
    out = {"freqs": freqs, "contrast": np.zeros(0), "best_freq": np.nan,
           "max_contrast": np.nan, "contrast_snr": np.nan,
           "Z_on": Z_on, "Z_off": Z_off}
    n = min(freqs.size, Z_on.size, Z_off.size)
    if n == 0:
        return out
    freqs, Z_on, Z_off = freqs[:n], Z_on[:n], Z_off[:n]
    contrast = np.abs(Z_on - Z_off)
    idx = int(np.argmax(contrast))
    med = float(np.median(contrast))
    mad = float(np.median(np.abs(contrast - med)))
    noise_floor = 1.4826 * mad if mad > 0 else (med if med > 0 else 1.0)
    out.update({"freqs": freqs, "contrast": contrast,
                "best_freq": float(freqs[idx]), "max_contrast": float(contrast[idx]),
                "contrast_snr": float(contrast[idx] / noise_floor) if noise_floor > 0 else np.inf,
                "Z_on": Z_on, "Z_off": Z_off})
    return out


def projected_histogram_snr(scores, bins="auto"):
    """Two-Gaussian fit of V(t) with conservative, BIC-based bimodality.

    A 2-component GMM almost always 'finds' two peaks, so is_bimodal requires
    delta_bic>0 AND separation_snr>1.5 AND both weights in (0.1, 0.9).
    """
    scores = np.asarray(scores, dtype=float).ravel()
    out = {"centers": np.array([np.nan, np.nan]), "sigmas": np.array([np.nan, np.nan]),
           "weights": np.array([np.nan, np.nan]), "separation_snr": 0.0, "overlap": np.nan,
           "is_bimodal": False, "bic_1": np.nan, "bic_2": np.nan, "delta_bic": np.nan,
           "hist": np.zeros(0), "bin_edges": np.zeros(0)}
    if scores.size < 10:
        return out
    from sklearn.mixture import GaussianMixture
    # Fit (and score) a uniform subsample. Two GMMs over a multi-million-sample
    # trace cost tens of seconds, and this runs once per bin in bin_size_sweep and
    # once per point in the stage-7 environment sweep. Both BICs are evaluated on
    # the SAME subsample so delta_bic stays a like-for-like model comparison.
    x = _subsample(scores, _GMM_MAX_SAMPLES).reshape(-1, 1)
    g1 = GaussianMixture(n_components=1, random_state=0).fit(x)
    g2 = GaussianMixture(n_components=2, random_state=0).fit(x)
    bic_1 = float(g1.bic(x))
    bic_2 = float(g2.bic(x))
    means = g2.means_.ravel()
    sigmas = np.sqrt(g2.covariances_.ravel())
    weights = g2.weights_.ravel()
    order = np.argsort(means)
    centers, sig, w = means[order], sigmas[order], weights[order]
    denom = np.sqrt(0.5 * (sig[0] ** 2 + sig[1] ** 2))
    sep = float(abs(centers[1] - centers[0]) / denom) if denom > 0 else 0.0
    # Bhattacharyya coefficient (two gaussians) as overlap
    s2 = sig[0] ** 2 + sig[1] ** 2
    bc = float(np.sqrt(2 * sig[0] * sig[1] / s2) * np.exp(-0.25 * (centers[0] - centers[1]) ** 2 / s2)) if s2 > 0 else 1.0
    # numpy's bins="auto" is max(Sturges, Freedman-Diaconis) and is UNBOUNDED: a
    # long trace with a small IQR plus a few outliers can request millions of bins
    # (huge allocation, useless plot). Cap it.
    if isinstance(bins, str):
        edges_auto = np.histogram_bin_edges(_subsample(scores, _GMM_MAX_SAMPLES),
                                            bins=bins)
        n_bins = min(max(int(edges_auto.size) - 1, 1), _HIST_MAX_BINS)
        hist, edges = np.histogram(scores, bins=n_bins)
    else:
        hist, edges = np.histogram(scores, bins=bins)
    is_bimodal = (bic_1 - bic_2 > 0) and (sep > 1.5) and (0.1 < w[0] < 0.9) and (0.1 < w[1] < 0.9)
    out.update({"centers": centers, "sigmas": sig, "weights": w, "separation_snr": sep,
                "overlap": bc, "is_bimodal": bool(is_bimodal), "bic_1": bic_1, "bic_2": bic_2,
                "delta_bic": bic_1 - bic_2, "hist": hist, "bin_edges": edges})
    return out


def bin_size_sweep(I, Q, t_us, separator, bin_list_us, gap_indices=None,
                   method="apriori_axis"):
    """Reprocess the same raw IQ at several bin sizes.

    Returns per-bin separation SNR and dwell tau. best_bin_us maximizes separation
    SNR. NO monotonic-then-degrade assertion: the optimum can occur before T_parity.

    `method` defaults to "apriori_axis" because binning changes the projected
    distribution's spread, and a fixed g/e-midpoint threshold ("apriori") is on the
    wrong side of a driven trace at every bin size (see classify_parity_trace).
    """
    sep_snr, mean_dwell, exp_tau = [], [], []
    for b in bin_list_us:
        Ib, Qb, tb, gb, _ = _bin_iq_time(I, Q, t_us, float(b), gap_indices)
        cls = classify_parity_trace(Ib, Qb, separator=separator, method=method)
        h = projected_histogram_snr(cls["scores"])
        dw = dwell_time_statistics(cls["binary_states"], tb, gap_indices=gb,
                                   merge_short_segments=True, min_dwell_bins=2)
        sep_snr.append(h["separation_snr"])
        mean_dwell.append(0.5 * (dw["mean_0"] + dw["mean_1"]))
        taus = [dw["exp_fit_0"]["tau_us"], dw["exp_fit_1"]["tau_us"]]
        taus = [tt for tt in taus if np.isfinite(tt)]
        exp_tau.append(float(np.mean(taus)) if taus else np.nan)
    snr_arr = np.array(sep_snr, dtype=float)
    best_bin = float(bin_list_us[int(np.nanargmax(snr_arr))]) if np.any(np.isfinite(snr_arr)) else np.nan
    return {"bin_list_us": list(bin_list_us), "separation_snr_per_bin": sep_snr,
            "mean_dwell_per_bin": mean_dwell, "exp_tau_per_bin": exp_tau, "best_bin_us": best_bin}


def _default_threshold_grid(scores, n_thresholds=5, span_sigma=0.6):
    """Threshold grid for threshold_stability: valley-centred when bimodal.

    Returns `n_thresholds` values spanning `midpoint +/- span_sigma * sigma_within`
    where midpoint/sigma come from a 2-Gaussian fit, so every threshold stays
    inside the valley and a genuine telegraph yields a consistent tau. Falls back
    to percentiles 30..70 when no two-component structure is resolvable.
    """
    s = np.asarray(scores, dtype=float).ravel()
    s = s[np.isfinite(s)]
    if s.size == 0:
        return [0.0]
    n_thresholds = max(int(n_thresholds), 1)
    h = projected_histogram_snr(s)
    centers = np.asarray(h["centers"], dtype=float)
    sigmas = np.asarray(h["sigmas"], dtype=float)
    if np.all(np.isfinite(centers)) and np.all(np.isfinite(sigmas)):
        midpoint = float(0.5 * (centers[0] + centers[1]))
        sigma_within = float(np.sqrt(0.5 * (sigmas[0] ** 2 + sigmas[1] ** 2)))
        half_gap = 0.5 * float(abs(centers[1] - centers[0]))
        # Never step past the component centers themselves, however wide sigma is.
        half_span = min(span_sigma * sigma_within, 0.8 * half_gap)
        if half_span > 0:
            if n_thresholds == 1:
                return [midpoint]
            return list(np.linspace(midpoint - half_span, midpoint + half_span,
                                    n_thresholds))
    pct = np.linspace(30.0, 70.0, n_thresholds) if n_thresholds > 1 else [50.0]
    return list(np.percentile(s, pct))


def threshold_stability(scores, t_us, threshold_list=None, gap_indices=None,
                        min_dwell_bins=2, n_thresholds=5, span_sigma=0.6):
    """Vary the classification threshold; report dwell tau stability.

    Low tau_cv (coefficient of variation across thresholds) = robust telegraph;
    high tau_cv = noise crossings.

    The default grid is centred on the VALLEY between the two components of a
    2-Gaussian fit and spans +/- `span_sigma` of the within-component width. It is
    emphatically NOT a percentile grid: for the well-separated balanced telegraph
    this function is supposed to reward, percentiles 30/40 land deep inside the
    lower lobe and 60/70 deep inside the upper one, so only the median lies in the
    valley. Four of five thresholds then chop a clean telegraph into noise, giving
    a LARGE tau_cv for good data and a small one for pure noise -- the metric
    inverted for exactly its intended input.

    Falls back to a percentile grid only when the two-component fit is unavailable
    (unimodal or degenerate scores), where percentiles are the sensible choice.
    """
    scores = np.asarray(scores, dtype=float).ravel()
    if threshold_list is None:
        threshold_list = _default_threshold_grid(scores, n_thresholds, span_sigma)
    tau0, tau1 = [], []
    for th in threshold_list:
        bits = (scores > th).astype(int)
        dw = dwell_time_statistics(bits, t_us, gap_indices=gap_indices,
                                   merge_short_segments=True, min_dwell_bins=min_dwell_bins)
        tau0.append(dw["exp_fit_0"]["tau_us"])
        tau1.append(dw["exp_fit_1"]["tau_us"])
    allt = np.array([x for x in (tau0 + tau1) if np.isfinite(x)], dtype=float)
    tau_cv = float(np.std(allt) / np.mean(allt)) if allt.size >= 2 and np.mean(allt) > 0 else np.inf
    return {"threshold_list": list(threshold_list), "tau0_per_threshold": tau0,
            "tau1_per_threshold": tau1, "tau_cv": tau_cv}


# ---------------------------------------------------------------------------
# Threshold-free switching-rate extraction: gap-aware Welch PSD + Lorentzian fit.
#
# WHY THIS EXISTS ALONGSIDE sliding_window_switch_rate. Counting thresholded
# transitions puts every classification error straight into the answer: one
# misassigned sample is TWO spurious switches, and _debounce_bits can only trade
# that bias for a dead time that pushes tau back the other way. Both failures
# scale with readout SNR, and in the zero-span geometry that SNR is set by a
# driven steady state with P_e <= 0.5 whose lobe is broader than the undriven
# one -- i.e. exactly the regime where a counted rate is least trustworthy.
#
# The autocorrelation of a two-state telegraph has none of that fragility:
#
#     C(tau) = p (1-p) dV^2 exp(-Gamma tau),      Gamma = gamma_01 + gamma_10
#
# so the one-sided power spectrum is a Lorentzian on a white floor
#
#     S(f) = S_white + S_0 / (1 + (f / f_c)^2),   2 pi f_c = Gamma
#
# with four properties that matter here:
#   * ADDITIVE READOUT NOISE lands entirely in S_white. It lowers the visibility
#     ratio S_0/S_white but does NOT move f_c.
#   * OCCUPANCY IMBALANCE enters only the amplitude, via p(1-p). A trace sitting
#     in the lower state 80% of the time still reports the correct Gamma.
#   * THE PROJECTION SCALE cancels: scaling `scores` by k scales S_0 and S_white
#     by k^2 and leaves f_c alone. No calibrated separator is required -- a bare
#     principal-axis projection works (see _pca_scores).
#   * NO THRESHOLD IS APPLIED AT ALL, so lobe-width asymmetry and the
#     _data_driven_threshold placement drop out of the measurement entirely.
#
# What it cannot do: separate gamma_01 from gamma_10. Only their sum appears in
# Gamma. Take the individual directions from the dwell statistics (or a 2-state
# HMM with unequal sigmas) and cross-check that 1/tau_0 + 1/tau_1 == 2 pi f_c.
#
# TWO TRAPS, both checked by the returned fields rather than assumed away:
#   1. 1/f DRIFT (gain wander, TLS, slow charge motion) also rises toward low
#      frequency and a Lorentzian will happily fit it with a spuriously low f_c.
#      The discriminator is the KNEE EXPONENT: a real RTS gives S ~ f^-2 above
#      f_c, 1/f drift gives ~f^-1. `exponent_free` is fitted with the exponent
#      free and `exponent_consistent_with_rts` gates on it near 2.
#   2. BAND PLACEMENT. f_c must sit inside the measured band with room on both
#      sides: above ~2/(nperseg*dt) (below that, Welch's per-window mean removal
#      has eaten the plateau) and well below Nyquist. `is_lorentzian` enforces
#      both, so a "fit" that is really an extrapolation cannot pass.
#
# The fit is done on LOG10(S) over LOG-BINNED frequencies. Both choices are
# deliberate: Welch PSD scatter is multiplicative (constant in dex, ~1/sqrt(n_avg)),
# so log space is where the residuals are homoscedastic; and the raw frequency
# grid is LINEAR, so 90% of its points sit in the top decade and an unbinned fit
# pins S_white beautifully while leaving f_c almost unconstrained.
# ---------------------------------------------------------------------------

_PSD_DEFAULT_NPERSEG = 2 ** 15
_PSD_LOG_BINS = 60


def _lorentzian_psd(f, s_white, s_0, f_c, exponent=2.0):
    """One-sided RTS power spectrum: a white floor plus a Lorentzian knee."""
    return s_white + s_0 / (1.0 + (np.asarray(f, dtype=float) / f_c) ** exponent)


def _pca_scores(I, Q):
    """Project (I, Q) onto its principal axis — a separator-free 1-D trace.

    For a telegraph the direction of maximum variance IS the switching axis, so
    this gives a usable projection with no single-shot calibration at all. Only
    the corner frequency survives the arbitrary scale, which is exactly what the
    PSD path uses; prefer a real separator when one exists, because anisotropic
    amplifier noise can tilt this axis away from the g->e direction.
    """
    iq = np.column_stack([
        np.ravel(np.asarray(I, dtype=float)),
        np.ravel(np.asarray(Q, dtype=float)),
    ])
    if iq.shape[0] < 2:
        return np.zeros(iq.shape[0], dtype=float)
    iq = iq - iq.mean(axis=0)
    cov = np.cov(iq, rowvar=False)
    if not np.all(np.isfinite(cov)):
        return iq[:, 0]
    w, v = np.linalg.eigh(np.atleast_2d(cov))
    axis = np.asarray(v[:, int(np.argmax(w))], dtype=float)
    # Canonical sign so repeated calls on the same data agree (eigh's sign is
    # arbitrary). Irrelevant to the PSD, but it keeps plots comparable.
    if axis[int(np.argmax(np.abs(axis)))] < 0:
        axis = -axis
    return iq @ axis


def _logbin_psd(f, psd, n_bins=_PSD_LOG_BINS):
    """Average `psd` within `n_bins` logarithmically spaced frequency bins.

    Returns (f_centers, psd_means, counts) over the non-empty bins. Averaging is
    done in LINEAR psd space (that is the unbiased estimator of the spectrum);
    the log is taken later, by the fitter.
    """
    f = np.asarray(f, dtype=float)
    p = np.asarray(psd, dtype=float)
    m = (f > 0) & np.isfinite(f) & np.isfinite(p) & (p > 0)
    f, p = f[m], p[m]
    if f.size == 0:
        return f, p, np.zeros(0, dtype=int)
    if f.size <= n_bins:
        return f, p, np.ones(f.size, dtype=int)
    edges = np.geomspace(f[0], f[-1], int(n_bins) + 1)
    idx = np.clip(np.searchsorted(edges, f, side="right") - 1, 0, int(n_bins) - 1)
    cnt = np.bincount(idx, minlength=int(n_bins))
    fsum = np.bincount(idx, weights=f, minlength=int(n_bins))
    psum = np.bincount(idx, weights=p, minlength=int(n_bins))
    keep = cnt > 0
    return fsum[keep] / cnt[keep], psum[keep] / cnt[keep], cnt[keep]


def segmented_welch_psd(x, sample_period_us, gap_indices=None, nperseg=None,
                        detrend="constant"):
    """
    Welch PSD of a 1-D trace, computed WITHIN gap-free segments and averaged.

    Never FFTs across a `gap_indices` boundary: a chunk gap is a discontinuity of
    unknown width, and transforming the stitched array puts its edge structure
    into the spectrum right where the Lorentzian knee is being looked for.

    Parameters
    ----------
    x                : array_like, the projected trace (arbitrary units)
    sample_period_us : float, spacing of consecutive samples WITHIN a segment
    gap_indices      : list[int] | ndarray | None, acquisition-boundary indices
    nperseg          : int | None, Welch window length. Sets both the frequency
                       resolution (fs/nperseg, hence the lowest usable
                       frequency) and how many windows there are to average
                       (~2N/nperseg), which are in direct tension. The default
                       targets ~8 windows from the longest segment — the largest
                       power of two below longest/8, clamped to [256, 2**15] —
                       rather than maximising resolution, because a spectrum
                       built from one or two windows is too noisy for the knee
                       to be fitted at all. Override when you know which side of
                       the trade the record needs.
    detrend          : passed to scipy.signal.welch; "constant" removes each
                       window's mean, which suppresses the two or three lowest
                       bins (parity_psd_rate excludes them from the fit).

    Returns
    -------
    dict with f_hz, psd, nperseg_used, n_segments_used, n_segments_skipped,
    n_samples_used, n_averages, f_resolution_hz, f_nyquist_hz, sample_period_us,
    reason. `psd` is empty and `reason` is set when no spectrum could be formed.

    Segments shorter than `nperseg` cannot share the frequency grid and are
    skipped; `n_segments_skipped` reports how many, so the loss is never silent.
    Because nperseg defaults to the LONGEST segment's length (capped), at least
    one segment always survives. Equal-length chunks -- what chunked_acquire
    produces -- lose nothing.
    """
    fail = {
        "f_hz": np.zeros(0), "psd": np.zeros(0), "nperseg_used": 0,
        "n_segments_used": 0, "n_segments_skipped": 0, "n_samples_used": 0,
        "n_averages": 0, "f_resolution_hz": np.nan, "f_nyquist_hz": np.nan,
        "sample_period_us": float(sample_period_us or 0.0), "reason": "",
    }
    x = np.ravel(np.asarray(x, dtype=float))
    sp = float(sample_period_us or 0.0)
    if sp <= 0:
        fail["reason"] = "sample_period_us <= 0"
        return fail
    if x.size < 8:
        fail["reason"] = f"trace too short ({x.size} samples)"
        return fail
    if not np.all(np.isfinite(x)):
        fail["reason"] = "trace contains non-finite samples"
        return fail
    try:
        from scipy.signal import welch
    except ImportError:
        fail["reason"] = "scipy unavailable"
        return fail

    fs = 1e6 / sp  # Hz
    edges = _gap_segment_edges(gap_indices, x.size)
    segs = [x[a:b] for a, b in zip(edges[:-1], edges[1:]) if b - a >= 8]
    if not segs:
        fail["reason"] = "no gap-free segment of at least 8 samples"
        return fail
    longest = max(s.size for s in segs)
    if nperseg is None:
        # Aim for ~8 averaging windows out of the longest segment instead of the
        # finest possible resolution: at one or two windows the PSD scatter is
        # ~100% per bin and the Lorentzian knee cannot be located, which is a
        # worse failure than a coarser frequency grid.
        target = longest // 8
        if target >= 256:
            nperseg = min(2 ** int(np.floor(np.log2(target))),
                          _PSD_DEFAULT_NPERSEG)
        else:
            nperseg = min(longest, 256)
    nperseg = int(min(int(nperseg), longest))
    if nperseg < 8:
        fail["reason"] = f"nperseg={nperseg} below the 8-sample minimum"
        return fail

    f_grid = None
    acc = None
    wsum = 0.0
    n_avg = 0
    used = 0
    skipped = 0
    n_used_samples = 0
    for s in segs:
        if s.size < nperseg:
            skipped += 1
            continue
        f_seg, p_seg = welch(s, fs=fs, nperseg=nperseg, detrend=detrend)
        w = float(s.size)
        if acc is None:
            f_grid, acc = f_seg, p_seg * w
        else:
            acc = acc + p_seg * w
        wsum += w
        # Welch's default 50% overlap: ~2N/nperseg - 1 windows per segment.
        n_avg += max(1, 2 * (s.size // nperseg) - 1)
        used += 1
        n_used_samples += int(s.size)
    if acc is None or wsum <= 0:
        fail["reason"] = "no segment reached nperseg"
        return fail

    return {
        "f_hz": np.asarray(f_grid, dtype=float),
        "psd": np.asarray(acc / wsum, dtype=float),
        "nperseg_used": int(nperseg),
        "n_segments_used": int(used),
        "n_segments_skipped": int(skipped),
        "n_samples_used": int(n_used_samples),
        "n_averages": int(n_avg),
        "f_resolution_hz": float(fs / nperseg),
        "f_nyquist_hz": float(fs / 2.0),
        "sample_period_us": sp,
        "reason": "",
    }


def _fit_lorentzian_psd(f, psd, fit_exponent=False):
    """Least-squares fit of S_white + S_0/(1+(f/f_c)^a) to `psd`, in log space.

    Fits log10(S) against log-binned frequencies (see the section header for
    why), and parameterises the amplitudes and f_c by their base-10 LOGS so the
    optimiser cannot wander to a negative floor or a negative corner frequency
    and no bounds are needed on them.

    Returns a dict, or None when the fit cannot be attempted or does not
    converge. `delta_bic` compares the model against a flat (white-noise-only)
    spectrum; positive favours the Lorentzian.
    """
    try:
        from scipy.optimize import curve_fit
    except ImportError:
        return None
    f = np.asarray(f, dtype=float)
    p = np.asarray(psd, dtype=float)
    m = (f > 0) & np.isfinite(f) & np.isfinite(p) & (p > 0)
    f, p = f[m], p[m]
    n_par = 4 if fit_exponent else 3
    if f.size < n_par + 2:
        return None
    y = np.log10(p)

    # Initial guesses. The floor from the top half-decade, the plateau from the
    # lowest few points, and f_c from where the spectrum crosses their midpoint.
    hi = f >= 0.5 * f.max()
    s_white0 = float(np.median(p[hi])) if np.any(hi) else float(np.median(p))
    n_lo = max(1, min(4, f.size // 10))
    s_lo = float(np.median(p[:n_lo]))
    s_00 = max(s_lo - s_white0, 1e-3 * max(s_white0, 1e-300))
    if s_white0 <= 0:
        s_white0 = max(1e-3 * s_00, 1e-300)
    cross = s_white0 + 0.5 * s_00
    f_c0 = float(f[int(np.argmin(np.abs(p - cross)))])
    if not (f_c0 > 0):
        f_c0 = float(np.sqrt(f.min() * f.max()))

    if fit_exponent:
        def model(fx, l_sw, l_s0, l_fc, a):
            return np.log10(_lorentzian_psd(fx, 10.0 ** l_sw, 10.0 ** l_s0,
                                            10.0 ** l_fc, a))
        p0 = [np.log10(s_white0), np.log10(s_00), np.log10(f_c0), 2.0]
        bounds = ([-np.inf, -np.inf, -np.inf, 0.2], [np.inf, np.inf, np.inf, 6.0])
    else:
        def model(fx, l_sw, l_s0, l_fc):
            return np.log10(_lorentzian_psd(fx, 10.0 ** l_sw, 10.0 ** l_s0,
                                            10.0 ** l_fc, 2.0))
        p0 = [np.log10(s_white0), np.log10(s_00), np.log10(f_c0)]
        bounds = (-np.inf, np.inf)
    try:
        # An unfittable spectrum (white noise, a 6-point record) makes curve_fit
        # emit OptimizeWarning because it cannot estimate the covariance. That is
        # an expected outcome here, already handled by reporting nan errors
        # below, so don't let it print a scary traceback-looking block over every
        # legitimate null result.
        import warnings
        from scipy.optimize import OptimizeWarning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", OptimizeWarning)
            popt, pcov = curve_fit(model, f, y, p0=p0, bounds=bounds, maxfev=20000)
    except (RuntimeError, ValueError, TypeError, FloatingPointError):
        return None
    perr = (np.sqrt(np.diag(pcov)) if pcov is not None
            and np.all(np.isfinite(pcov)) else np.full(len(popt), np.nan))

    resid = y - model(f, *popt)
    ssr = float(np.sum(resid ** 2))
    ss0 = float(np.sum((y - np.mean(y)) ** 2))
    n = int(f.size)
    r2 = float(1.0 - ssr / ss0) if ss0 > 0 else np.nan
    # BIC against a flat spectrum (one free parameter: the constant floor).
    def _bic(ss, k):
        if ss <= 0:
            return -np.inf
        return n * np.log(ss / n) + k * np.log(n)
    delta_bic = float(_bic(ss0, 1) - _bic(ssr, n_par))

    l_sw, l_s0, l_fc = popt[0], popt[1], popt[2]
    f_c = float(10.0 ** l_fc)
    # d(10^u)/du = ln(10) * 10^u, so a log-parameter sigma maps to a linear one.
    f_c_err = float(np.log(10.0) * f_c * perr[2]) if np.isfinite(perr[2]) else np.nan
    out = {
        "s_white": float(10.0 ** l_sw),
        "s_0": float(10.0 ** l_s0),
        "f_c_hz": f_c,
        "f_c_err_hz": f_c_err,
        "exponent": float(popt[3]) if fit_exponent else 2.0,
        "exponent_err": (float(perr[3]) if fit_exponent
                         and np.isfinite(perr[3]) else np.nan),
        "r2": r2,
        "delta_bic": delta_bic,
        "n_points": n,
    }
    out["lorentzian_snr"] = (out["s_0"] / out["s_white"]
                             if out["s_white"] > 0 else np.inf)
    return out


def parity_psd_rate(scores, t_us=None, sample_period_us=None, gap_indices=None,
                    nperseg=None, f_min_hz=None, f_max_hz=None,
                    min_lorentzian_snr=0.5, min_delta_bic=10.0,
                    n_log_bins=_PSD_LOG_BINS):
    """
    Switching rate from the Lorentzian corner of a projected trace's PSD.

    No threshold, no classifier, no debouncing — see the section header for why
    that makes the result robust to the contrast asymmetry and occupancy
    imbalance that bias `sliding_window_switch_rate`.

    Parameters
    ----------
    scores           : array_like, the projected 1-D trace (any scale; the
                       corner frequency is scale-invariant)
    t_us             : array_like | None, time axis; used only to infer the
                       sample period when `sample_period_us` is not given
    sample_period_us : float | None, preferred over inferring from t_us
    gap_indices      : list[int] | ndarray | None, acquisition boundaries
    nperseg          : int | None, Welch window length (see segmented_welch_psd)
    f_min_hz         : float | None, low edge of the fit range. Default
                       2 * f_resolution — below that, Welch's per-window mean
                       removal has already eaten the plateau.
    f_max_hz         : float | None, high edge. Default 0.4 * Nyquist.
    min_lorentzian_snr : float, S_0/S_white required for `is_lorentzian`
    min_delta_bic    : float, BIC improvement over a flat spectrum required
    n_log_bins       : int, log-frequency bins the fit is performed on

    Returns
    -------
    dict. Rate fields (nan when no fit):
      f_c_hz, f_c_err_hz     corner frequency
      gamma_total_hz         2*pi*f_c == gamma_01 + gamma_10 == 1/tau_0 + 1/tau_1
      transitions_per_s      2/(tau_0+tau_1); equals gamma_total/2 only for the
                             SYMMETRIC case, so it is reported as
                             transitions_per_s_symmetric to keep that explicit
      tau_symmetric_us       1e6/(pi*f_c), the per-state dwell IF the two rates
                             are equal. Compare against the measured tau_0/tau_1
                             rather than substituting for them.
    Quality fields: s_white, s_0, lorentzian_snr, r2, delta_bic, exponent_free,
    exponent_free_err, exponent_consistent_with_rts, is_lorentzian, verdict,
    reason, plus the PSD arrays (f_hz, psd, f_hz_binned, psd_binned) and the
    acquisition metadata from segmented_welch_psd.

    `is_lorentzian` False with a large s_white and no knee is a real result: it
    says the record contains no resolvable telegraph, which no choice of
    threshold can fix.
    """
    out = {
        "f_c_hz": np.nan, "f_c_err_hz": np.nan, "gamma_total_hz": np.nan,
        "gamma_total_err_hz": np.nan, "transitions_per_s_symmetric": np.nan,
        "tau_symmetric_us": np.nan, "s_white": np.nan, "s_0": np.nan,
        "lorentzian_snr": np.nan, "r2": np.nan, "delta_bic": np.nan,
        "exponent_free": np.nan, "exponent_free_err": np.nan,
        "exponent_consistent_with_rts": False, "is_lorentzian": False,
        "verdict": "NO FIT", "reason": "", "f_min_hz": np.nan, "f_max_hz": np.nan,
        "n_fit_points": 0,
        "f_hz": np.zeros(0), "psd": np.zeros(0),
        "f_hz_binned": np.zeros(0), "psd_binned": np.zeros(0),
    }

    if sample_period_us is None:
        if t_us is None:
            out["reason"] = "need sample_period_us or t_us"
            return out
        t_arr = np.ravel(np.asarray(t_us, dtype=float))
        sample_period_us = _infer_sample_period(
            t_arr, _gap_segment_edges(gap_indices, t_arr.size))
    spec = segmented_welch_psd(scores, sample_period_us,
                               gap_indices=gap_indices, nperseg=nperseg)
    for k in ("nperseg_used", "n_segments_used", "n_segments_skipped",
              "n_samples_used", "n_averages", "f_resolution_hz",
              "f_nyquist_hz", "sample_period_us"):
        out[k] = spec[k]
    out["f_hz"] = spec["f_hz"]
    out["psd"] = spec["psd"]
    if spec["psd"].size == 0:
        out["reason"] = spec["reason"] or "no spectrum"
        out["verdict"] = f"NO SPECTRUM ({out['reason']})"
        return out

    f_res = float(spec["f_resolution_hz"])
    f_nyq = float(spec["f_nyquist_hz"])
    lo = 2.0 * f_res if f_min_hz is None else float(f_min_hz)
    hi = 0.4 * f_nyq if f_max_hz is None else float(f_max_hz)
    out["f_min_hz"], out["f_max_hz"] = lo, hi
    f_all, p_all = spec["f_hz"], spec["psd"]
    mask = (f_all >= lo) & (f_all <= hi) & np.isfinite(p_all) & (p_all > 0)
    if mask.sum() < 6:
        out["reason"] = (f"only {int(mask.sum())} usable PSD bins in "
                         f"[{lo:.3g}, {hi:.3g}] Hz")
        out["verdict"] = f"NO FIT ({out['reason']})"
        return out
    fb, pb, _ = _logbin_psd(f_all[mask], p_all[mask], n_bins=n_log_bins)
    out["f_hz_binned"], out["psd_binned"] = fb, pb
    out["n_fit_points"] = int(fb.size)

    fit = _fit_lorentzian_psd(fb, pb, fit_exponent=False)
    if fit is None:
        out["reason"] = "Lorentzian fit did not converge"
        out["verdict"] = f"NO FIT ({out['reason']})"
        return out
    for k in ("s_white", "s_0", "f_c_hz", "f_c_err_hz", "lorentzian_snr",
              "r2", "delta_bic"):
        out[k] = fit[k]
    f_c = float(fit["f_c_hz"])
    out["gamma_total_hz"] = 2.0 * np.pi * f_c
    if np.isfinite(fit["f_c_err_hz"]):
        out["gamma_total_err_hz"] = 2.0 * np.pi * float(fit["f_c_err_hz"])
    # Symmetric-case conveniences. Gamma = 1/tau_0 + 1/tau_1 always; with
    # tau_0 == tau_1 == tau that is 2/tau, so tau = 1/(pi f_c) and the number of
    # transitions per second is Gamma/2 = pi f_c.
    out["transitions_per_s_symmetric"] = np.pi * f_c
    out["tau_symmetric_us"] = 1e6 / (np.pi * f_c) if f_c > 0 else np.nan

    # Free-exponent refit: the 1/f discriminator. ~2 is an RTS knee, ~1 is drift.
    # Free-exponent refit: the 1/f discriminator. An RTS knee falls as f^-2; 1/f
    # drift fitted with this model comes out near 1.
    #
    # The accepted window is deliberately lopsided ([1.5, 3.5], not [1.5, 2.5]).
    # Only the LOWER bound carries physics -- it is what separates a telegraph
    # from drift. The upper bound is loose because the exponent is only
    # well-constrained when there is a decade of knee to measure it on: the
    # spectrum falls from S_0 to the floor within about sqrt(S_0/S_white) in
    # frequency, so at the low visibility typical of a driven zero-span trace
    # (S_0/S_white of a few) barely one octave of slope exists and the fitted
    # exponent scatters upward by 0.5 or more with no physical meaning. Treat
    # this field as informative only when lorentzian_snr is comfortably above
    # ~10; a value BELOW 1.5 is the finding worth acting on.
    fit_a = _fit_lorentzian_psd(fb, pb, fit_exponent=True)
    if fit_a is not None:
        out["exponent_free"] = fit_a["exponent"]
        out["exponent_free_err"] = fit_a["exponent_err"]
        out["exponent_consistent_with_rts"] = bool(
            1.5 <= float(fit_a["exponent"]) <= 3.5)

    reasons = []
    if not (float(fit["delta_bic"]) > float(min_delta_bic)):
        reasons.append(f"delta_bic={fit['delta_bic']:.1f} <= {min_delta_bic}")
    if not (float(fit["lorentzian_snr"]) > float(min_lorentzian_snr)):
        reasons.append(f"S_0/S_white={fit['lorentzian_snr']:.2g} <= "
                       f"{min_lorentzian_snr}")
    if not (f_c > 3.0 * f_res):
        reasons.append(f"f_c={f_c:.3g} Hz not above 3x resolution "
                       f"({3.0 * f_res:.3g} Hz) — lengthen the record or nperseg")
    if not (f_c < 0.3 * f_nyq):
        reasons.append(f"f_c={f_c:.3g} Hz not below 0.3x Nyquist "
                       f"({0.3 * f_nyq:.3g} Hz) — shorten sample_period_us")
    # The knee exponent gates too. Without it a pure 1/f drift spectrum passes
    # every other check -- it has a plateau, a knee, a floor, and a huge BIC
    # improvement over flat -- and reports is_lorentzian=True with a corner
    # frequency that is really just the low edge of the fit range. The verified
    # behaviour on synthetic 1/f is exponent_free = 1.00, nowhere near the 1.5
    # floor, so this rejects drift without endangering a real telegraph (whose
    # low-visibility scatter pushes the exponent UP, not down).
    if fit_a is not None and not out["exponent_consistent_with_rts"]:
        reasons.append(
            f"knee exponent={out['exponent_free']:.2f} outside [1.5, 3.5] "
            f"(2 = RTS, 1 = 1/f drift) — the low-frequency rise is not a "
            f"telegraph knee")
    out["is_lorentzian"] = not reasons
    out["reason"] = "; ".join(reasons)
    if out["is_lorentzian"]:
        out["verdict"] = (
            f"LORENTZIAN: f_c={f_c:.3g} Hz -> Gamma={out['gamma_total_hz']:.3g} /s "
            f"(tau_sym={out['tau_symmetric_us']:.3g} us), "
            f"S_0/S_white={out['lorentzian_snr']:.2g}, "
            f"knee exponent={out['exponent_free']:.2f}"
        )
    else:
        out["verdict"] = f"NO RESOLVABLE CORNER ({out['reason']})"
    return out


def psd_rate_vs_bin(I, Q, t_us, separator=None, bin_list_us=(0,), gap_indices=None,
                    nperseg=None, max_bin_fc_product=0.1):
    """
    Corner-frequency invariance check across analysis bin sizes.

    A real telegraph has ONE corner frequency; mean-binning the trace low-passes
    it but does not move f_c, so f_c must come out the same at every bin size
    short compared with 1/f_c. Threshold noise crossings have no corner at all,
    and any apparent rate tracks the bin size. This is the cheap way to tell
    those two apart, and unlike bin_size_sweep it involves no classifier.

    A `bin_list_us` entry of 0 (or None) means "no binning" — the raw trace.

    Bins failing `bin_us * f_c <= max_bin_fc_product` are excluded from
    `f_c_cv`: once the boxcar width approaches 1/f_c the binning really is
    attenuating the knee, so a shift there is expected physics, not evidence
    against the telegraph. They are still reported per bin.

    Returns
    -------
    dict with bin_list_us, f_c_per_bin, gamma_total_per_bin,
    lorentzian_snr_per_bin, is_lorentzian_per_bin, used_for_cv, f_c_cv,
    f_c_mean_hz, n_bins_used.
    """
    if separator is None:
        base_scores = _pca_scores(I, Q)
        # Feed the projection back through the binner as a degenerate (I, Q) so
        # every bin size sees the SAME axis. Re-running PCA per bin size would
        # let the axis move with the bin, which is not the invariance being
        # tested.
        I_use, Q_use = base_scores, np.zeros_like(base_scores)
        sep_use = {"g_center": np.array([0.0, 0.0]),
                   "e_center": np.array([1.0, 0.0])}
    else:
        I_use, Q_use, sep_use = I, Q, separator

    bins_out, fc_out, gam_out, snr_out, ok_out = [], [], [], [], []
    for b in bin_list_us:
        bv = 0.0 if not b else float(b)
        if bv > 0:
            Ib, Qb, tb, gb, _ = _bin_iq_time(I_use, Q_use, t_us, bv,
                                             gap_indices=gap_indices)
        else:
            Ib, Qb, tb, gb = (np.asarray(I_use), np.asarray(Q_use),
                              np.asarray(t_us), gap_indices)
        if np.asarray(Ib).size < 8:
            bins_out.append(bv); fc_out.append(np.nan); gam_out.append(np.nan)
            snr_out.append(np.nan); ok_out.append(False)
            continue
        scores, _ = project_iq_onto_separator(Ib, Qb, sep_use)
        r = parity_psd_rate(scores, t_us=tb, gap_indices=gb, nperseg=nperseg)
        bins_out.append(bv)
        fc_out.append(r["f_c_hz"])
        gam_out.append(r["gamma_total_hz"])
        snr_out.append(r["lorentzian_snr"])
        ok_out.append(bool(r["is_lorentzian"]))

    fc = np.asarray(fc_out, dtype=float)
    bw = np.asarray([b if b else 0.0 for b in bins_out], dtype=float)
    # us * Hz -> dimensionless via 1e-6
    prod = bw * 1e-6 * np.where(np.isfinite(fc), fc, 0.0)
    used = (np.asarray(ok_out, dtype=bool) & np.isfinite(fc)
            & (prod <= float(max_bin_fc_product)))
    if used.sum() >= 2:
        mean_fc = float(np.mean(fc[used]))
        cv = float(np.std(fc[used]) / mean_fc) if mean_fc > 0 else np.inf
    elif used.sum() == 1:
        mean_fc = float(fc[used][0])
        cv = 0.0
    else:
        mean_fc, cv = np.nan, np.inf
    return {
        "bin_list_us": [float(b) for b in bins_out],
        "f_c_per_bin": fc_out,
        "gamma_total_per_bin": gam_out,
        "lorentzian_snr_per_bin": snr_out,
        "is_lorentzian_per_bin": ok_out,
        "used_for_cv": used.tolist(),
        "f_c_cv": cv,
        "f_c_mean_hz": mean_fc,
        "n_bins_used": int(used.sum()),
    }


def _plot_psd(psd_out, out_path, title="Parity PSD"):
    """Log-log PSD with the fitted Lorentzian, floor, and corner marked."""
    f = np.asarray(psd_out.get("f_hz", []), dtype=float)
    p = np.asarray(psd_out.get("psd", []), dtype=float)
    fig, ax = plt.subplots(figsize=(7, 5))
    m = (f > 0) & np.isfinite(p) & (p > 0)
    if np.any(m):
        ax.loglog(f[m], p[m], color="0.75", lw=0.6, label="Welch PSD")
    fb = np.asarray(psd_out.get("f_hz_binned", []), dtype=float)
    pb = np.asarray(psd_out.get("psd_binned", []), dtype=float)
    if fb.size:
        ax.loglog(fb, pb, "o", ms=3, color="C0", label="log-binned (fit input)")
    f_c = psd_out.get("f_c_hz", np.nan)
    if np.isfinite(f_c) and fb.size:
        xs = np.geomspace(fb.min(), fb.max(), 400)
        ax.loglog(xs, _lorentzian_psd(xs, psd_out["s_white"], psd_out["s_0"], f_c),
                  "r-", lw=1.5,
                  label=(f"fit: f_c={f_c:.3g} Hz\n"
                         f"$\\Gamma$={psd_out['gamma_total_hz']:.3g} /s"))
        ax.axvline(f_c, color="r", ls="--", lw=0.8)
        ax.axhline(psd_out["s_white"], color="k", ls=":", lw=0.8,
                   label=f"floor={psd_out['s_white']:.3g}")
    lo, hi = psd_out.get("f_min_hz", np.nan), psd_out.get("f_max_hz", np.nan)
    if np.isfinite(lo) and np.isfinite(hi):
        ax.axvspan(lo, hi, color="C2", alpha=0.06, label="fit range")
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("PSD (score$^2$/Hz)")
    ax.set_title(f"{title}\n{psd_out.get('verdict', '')}", fontsize=9)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)


def psd_rate_from_h5(h5_path, separator=None, bin_list_us=(0,), nperseg=None,
                     save_plots=True, out_dir=None, verbose=True):
    """
    One-call threshold-free rate extraction on a saved ZeroSpanParity raw .h5.

    Runs parity_psd_rate on the projected trace and, when `bin_list_us` holds
    more than one entry, the bin-size invariance check as well. Writes
    `<base>_psd.png` and `<base>_psd.json` next to the input unless told
    otherwise, and prints the verdict.

    `separator=None` projects onto the principal axis (_pca_scores) instead of a
    calibrated g->e axis, so this runs on any trace on disk with no calibration
    to hand. The corner frequency does not depend on the projection scale; it
    does depend on the axis being the switching axis, so pass a separator when
    one is available.
    """
    if out_dir is None:
        out_dir = os.path.dirname(h5_path) or "."
    base = os.path.splitext(os.path.basename(h5_path))[0]
    with h5py.File(h5_path, "r") as f:
        I = np.array(f["I"])
        Q = np.array(f["Q"])
        t_us = np.array(f["t_us"])
        gap_indices = ([int(g) for g in np.array(f["gap_indices"])]
                       if "gap_indices" in f else [])
        sample_period_us = float(f.attrs.get(
            "sample_period_us",
            _infer_sample_period(t_us, _gap_segment_edges(gap_indices, t_us.size))))

    if separator is None:
        scores = _pca_scores(I, Q)
        axis_source = "pca"
    else:
        scores, _ = project_iq_onto_separator(I, Q, separator)
        axis_source = "separator"
    res = parity_psd_rate(scores, t_us=t_us, sample_period_us=sample_period_us,
                          gap_indices=gap_indices, nperseg=nperseg)
    res["h5_path"] = h5_path
    res["projection_axis"] = axis_source

    sweep = None
    if bin_list_us is not None and len(list(bin_list_us)) > 1:
        sweep = psd_rate_vs_bin(I, Q, t_us, separator=separator,
                                bin_list_us=bin_list_us,
                                gap_indices=gap_indices, nperseg=nperseg)
        res["f_c_cv_vs_bin"] = sweep["f_c_cv"]
        res["n_bins_used_for_cv"] = sweep["n_bins_used"]

    if save_plots:
        _plot_psd(res, os.path.join(out_dir, base + "_psd.png"),
                  title=f"Parity PSD — {base} ({axis_source} axis)")
    with open(os.path.join(out_dir, base + "_psd.json"), "w") as fh:
        json.dump({k: v for k, v in res.items()
                   if k not in ("f_hz", "psd", "f_hz_binned", "psd_binned")},
                  fh, indent=2,
                  default=lambda x: x.tolist() if isinstance(x, np.ndarray)
                  else float(x))
    if verbose:
        print(f"[psd_rate_from_h5] {base}: {res['verdict']}")
        print(f"    axis={axis_source}  sample_period={sample_period_us} us  "
              f"nperseg={res['nperseg_used']}  segments={res['n_segments_used']}"
              f"(+{res['n_segments_skipped']} skipped)  "
              f"f_res={res['f_resolution_hz']:.3g} Hz  "
              f"f_nyq={res['f_nyquist_hz']:.3g} Hz  n_avg={res['n_averages']}")
        if np.isfinite(res["f_c_hz"]):
            print(f"    Gamma={res['gamma_total_hz']:.4g} /s   "
                  f"transitions/s (if symmetric)="
                  f"{res['transitions_per_s_symmetric']:.4g}   "
                  f"tau_sym={res['tau_symmetric_us']:.4g} us   "
                  f"free exponent={res['exponent_free']:.2f}")
        if sweep is not None:
            print(f"    bin-size invariance: f_c_cv={sweep['f_c_cv']:.3g} over "
                  f"{sweep['n_bins_used']} bins")
            for b, fc, ok, u in zip(sweep["bin_list_us"], sweep["f_c_per_bin"],
                                    sweep["is_lorentzian_per_bin"],
                                    sweep["used_for_cv"]):
                fcs = f"{fc:.4g}" if np.isfinite(fc) else "nan"
                print(f"      bin={b:>8.1f} us  f_c={fcs:>10} Hz  "
                      f"lorentzian={ok}  in_cv={u}")
    return res


if __name__ == "__main__":
    # Headless test run: select a non-interactive backend HERE, not at module
    # import, so importing this module from a runner leaves the session's
    # interactive backend alone (see the note at the top of the file).
    import matplotlib
    matplotlib.use("Agg")

    rng = np.random.default_rng(1)

    # --- classify_parity_trace apriori path -----------------------------------
    g_center = np.array([0.0, 0.0])
    e_center = np.array([10.0, 0.0])
    sep = {"g_center": g_center, "e_center": e_center}
    I_g = rng.normal(g_center[0], 0.5, 1000); Q_g = rng.normal(g_center[1], 0.5, 1000)
    I_e = rng.normal(e_center[0], 0.5, 1000); Q_e = rng.normal(e_center[1], 0.5, 1000)
    I = np.concatenate([I_g, I_e]); Q = np.concatenate([Q_g, Q_e])
    labels_true = np.concatenate([np.zeros(1000, int), np.ones(1000, int)])

    out = classify_parity_trace(I, Q, separator=sep, method="apriori")
    assert "binary_states" in out and "scores" in out
    assert "method" in out and out["method"] == "apriori"
    assert "separator_used" in out
    accuracy = np.mean(out["binary_states"] == labels_true)
    assert accuracy > 0.99, f"apriori accuracy too low: {accuracy}"

    print("classify_parity_trace apriori: OK")

    # --- classify_parity_trace kmeans fallback --------------------------------
    out_km = classify_parity_trace(I, Q, separator=None, method="kmeans")
    assert out_km["method"] == "kmeans"
    assert "separator_used" in out_km
    accuracy_km = np.mean(out_km["binary_states"] == labels_true)
    assert accuracy_km > 0.99, f"kmeans accuracy too low: {accuracy_km}"

    # Deterministic remap: label 0 should be the lower-projection cluster. For
    # these I-axis-separated clouds that is the lower-I cluster.
    label0_mean_I = np.mean(np.asarray(I)[out_km["binary_states"] == 0])
    label1_mean_I = np.mean(np.asarray(I)[out_km["binary_states"] == 1])
    assert label0_mean_I < label1_mean_I, "kmeans label remap not deterministic"

    # Q-axis-separated clouds: the remap must be orientation-independent (the
    # old I-coordinate rule was arbitrary when the g/e split lies along Q).
    # label 0 should be the lower-Q cluster.
    Ig_q = rng.normal(0.0, 0.5, 1000); Qg_q = rng.normal(0.0, 0.5, 1000)
    Ie_q = rng.normal(0.0, 0.5, 1000); Qe_q = rng.normal(10.0, 0.5, 1000)
    I_q = np.concatenate([Ig_q, Ie_q]); Q_q = np.concatenate([Qg_q, Qe_q])
    out_q = classify_parity_trace(I_q, Q_q, separator=None, method="kmeans")
    label0_mean_Q = np.mean(np.asarray(Q_q)[out_q["binary_states"] == 0])
    label1_mean_Q = np.mean(np.asarray(Q_q)[out_q["binary_states"] == 1])
    assert label0_mean_Q < label1_mean_Q, (
        "kmeans remap not orientation-independent for Q-separated clouds"
    )

    print("classify_parity_trace kmeans: OK")

    # --- sliding_window_switch_rate -------------------------------------------
    # Build a 100 000-sample trace at 20 us/sample (record length 2 s).
    # Inject a known switch probability per sample so we can check recovered rate.
    n_samp = 100_000
    sample_period_us = 20.0
    t_us = np.arange(n_samp) * sample_period_us
    p_switch = 0.001  # 0.1% per sample = 50 Hz at 20 us cadence
    flips = rng.random(n_samp) < p_switch
    bits = np.cumsum(flips) % 2

    out_rate = sliding_window_switch_rate(bits, t_us, window_us=100_000, step_us=100_000)
    # Non-overlapping 100 ms windows; expected rate ~ p_switch / (sample_period_us * 1e-6)
    expected_rate_Hz = p_switch / (sample_period_us * 1e-6)
    mean_rate = float(np.mean(out_rate["rate_Hz"]))
    rel_err = abs(mean_rate - expected_rate_Hz) / expected_rate_Hz
    assert rel_err < 0.1, f"sliding rate off: expected {expected_rate_Hz:.1f}, got {mean_rate:.1f}"

    # Gap indices should zero the cross-gap diff.
    # bits2 = [0, 0, 1, 1, 0, 0], diffs = [0, 1, 0, 1, 0]
    # gap_indices=[4] means bits[4] is the first sample after a gap, so the
    # transition from bits[3] to bits[4] (= diffs[3] = 1) is zeroed.
    # Remaining sum: |0| + |1| + |0| + 0 (zeroed) + |0| = 1.
    bits2 = np.array([0, 0, 1, 1, 0, 0])
    t2 = np.array([0.0, 10.0, 20.0, 30.0, 40.0, 50.0])
    out_gap = sliding_window_switch_rate(bits2, t2, window_us=60.0, step_us=60.0,
                                          gap_indices=[4])
    assert out_gap["switches_per_window"][0] == 1, (
        f"expected 1 switch with gap, got {out_gap['switches_per_window']}"
    )

    # Default step is window_us / 2 -- TRUE division (spec §3.2: 50% overlap).
    # Floor division was silently truncating a fractional window (1001 -> 500
    # instead of 500.5), and collapsed to 0.0 for any window_us < 2, which then
    # made the np.arange window construction raise on a zero step.
    out_step = sliding_window_switch_rate(np.array([0, 1, 0, 1]),
                                          np.array([0.0, 1.0, 2.0, 3.0]),
                                          window_us=1001.0)
    assert out_step["step_us"] == 500.5, (
        f"default step_us={out_step['step_us']} (expected 500.5 = 1001 / 2)"
    )
    # Sub-2 us window: used to raise ZeroDivisionError/ValueError from step=0.
    out_tiny = sliding_window_switch_rate(np.array([0, 1, 0, 1, 1]),
                                          np.array([0.0, 0.1, 0.2, 0.3, 0.4]),
                                          window_us=0.2)
    assert out_tiny["step_us"] == 0.1, out_tiny["step_us"]
    assert out_tiny["rate_Hz"].size == out_tiny["window_t_us"].size > 0

    # A switch landing exactly at t_end (record length an exact multiple of the
    # window) must be counted by the closed final window, not dropped.
    out_edge = sliding_window_switch_rate(np.array([0, 0, 0, 1]),
                                          np.array([0.0, 30.0, 60.0, 90.0]),
                                          window_us=30.0, step_us=30.0)
    assert int(out_edge["switches_per_window"].sum()) == 1, (
        f"boundary switch dropped: {out_edge['switches_per_window']}"
    )

    print("sliding_window_switch_rate: OK")

    # --- detect_bursts --------------------------------------------------------
    # Baseline rate ~50 Hz over 100 windows; inject one window with 10 kHz.
    rate = np.full(100, 50.0)
    rate[50] = 10_000.0
    centers = np.arange(100) * 100_000.0  # 100 ms per window in us

    bursts = detect_bursts(rate, centers, baseline_rate=None, k_sigma=5,
                           min_duration_us=None)
    assert len(bursts) == 1, f"expected 1 burst, got {len(bursts)}"
    b = bursts[0]
    assert b["t_start_us"] <= centers[50] <= b["t_end_us"], (
        f"burst window does not contain injection: {b}"
    )
    assert b["peak_rate_Hz"] == 10_000.0
    assert b["baseline_rate_Hz"] == 50.0  # median is robust to one outlier

    # No bursts when everything is at baseline
    bursts0 = detect_bursts(np.full(100, 50.0), centers, k_sigma=5)
    assert bursts0 == [], f"expected no bursts, got {bursts0}"

    # Sparse-baseline regime (the normal operating point): most windows have
    # 0 switches, a minority have exactly one. The MAD collapses to 0, so the
    # Poisson sigma floor must prevent every single-switch window from being
    # flagged as a burst.
    rng_b = np.random.default_rng(0)
    win_us = 1000.0
    q_rate = 1.0 / (win_us * 1e-6)        # one switch per window, in Hz
    sparse = np.zeros(400)
    sparse[rng_b.random(400) < 0.10] = q_rate
    sparse_cen = np.arange(400) * (win_us / 2.0)
    assert detect_bursts(sparse, sparse_cen, k_sigma=5, window_us=win_us) == [], (
        "sparse baseline produced false bursts (sigma floor regression)"
    )
    # A genuine impact burst (many switches in one window) is still detected.
    sparse[200] = 60 * q_rate
    b_impact = detect_bursts(sparse, sparse_cen, k_sigma=5, window_us=win_us)
    assert len(b_impact) == 1, f"real burst missed: {len(b_impact)}"

    # MAD is centered on the median, independent of an explicit baseline_rate.
    # Here median-centered MAD is 0, so the threshold is set by the Poisson
    # floor (q*k_sigma = 5000 Hz), NOT by a baseline-0-centered MAD (~74132 Hz).
    rate_mc = np.array([10000.0] * 8 + [30000.0, 200000.0])
    cen_mc = np.arange(rate_mc.size) * 500.0
    b_mc = detect_bursts(rate_mc, cen_mc, baseline_rate=0.0, k_sigma=5,
                         window_us=win_us)
    assert b_mc and abs(b_mc[0]["threshold_Hz"] - 5000.0) < 1.0, (
        f"MAD not centered on median: threshold {b_mc[0]['threshold_Hz'] if b_mc else None}"
    )

    print("detect_bursts: OK")

    # --- dwell_time_statistics ------------------------------------------------
    # Generate a Markov-style binary trace with known mean dwell times
    # tau_0 = 200 samples, tau_1 = 400 samples, at 20 us/sample.
    n = 200_000
    p01 = 1.0 / 200.0   # prob 0 -> 1 per sample
    p10 = 1.0 / 400.0   # prob 1 -> 0 per sample
    bits_mc = np.zeros(n, dtype=int)
    state = 0
    for i in range(n):
        bits_mc[i] = state
        if state == 0:
            if rng.random() < p01:
                state = 1
        else:
            if rng.random() < p10:
                state = 0
    t_mc = np.arange(n) * 20.0  # us
    stats = dwell_time_statistics(bits_mc, t_mc)
    # Expected mean dwell times in microseconds:
    expected_tau_0_us = 200 * 20.0
    expected_tau_1_us = 400 * 20.0
    assert abs(stats["mean_0"] - expected_tau_0_us) / expected_tau_0_us < 0.15, (
        f"mean_0 off: got {stats['mean_0']:.1f}, expected ~{expected_tau_0_us}"
    )
    assert abs(stats["mean_1"] - expected_tau_1_us) / expected_tau_1_us < 0.15, (
        f"mean_1 off: got {stats['mean_1']:.1f}, expected ~{expected_tau_1_us}"
    )
    assert stats["n_runs_0"] > 0 and stats["n_runs_1"] > 0

    # gap_indices splits runs across acquisition boundaries
    bits_short = np.array([0, 0, 0, 0, 0, 0])
    t_short = np.arange(6, dtype=float) * 10.0
    stats_gap = dwell_time_statistics(bits_short, t_short, gap_indices=[3])
    # Without gap: one run of length 6 in state 0; with gap: two runs of length 3
    assert stats_gap["n_runs_0"] == 2

    # Out-of-range gap_indices are silently filtered (no IndexError).
    stats_oor = dwell_time_statistics(bits_short, t_short, gap_indices=[100, -1, 0, 6])
    # All four entries are out of valid range (0 < g < 6), so they're dropped;
    # the trace is treated as one continuous segment with one run of length 6.
    assert stats_oor["n_runs_0"] == 1, (
        f"out-of-range gap_indices should yield 1 run, got {stats_oor['n_runs_0']}"
    )

    # A single-sample segment (e.g. split off by a gap) yields ~one sample
    # period of dwell, not 0.0 (which would bias mean dwell times down).
    s_single = dwell_time_statistics(np.array([0, 0, 1]),
                                     np.array([0.0, 10.0, 20.0]),
                                     gap_indices=[2])
    assert abs(s_single["mean_1"] - 10.0) < 1e-9, (
        f"single-sample dwell = {s_single['mean_1']} (expected ~10 us)"
    )

    # Exponential dwell-time fit is unbiased within +/-5% (spec §6 validation),
    # via sqrt(count) Poisson weighting in log space.
    rng_fit = np.random.default_rng(0)
    fitted = [
        _fit_exp_dwell(np.random.default_rng(s).exponential(200.0, 5000))["tau_us"]
        for s in range(20)
    ]
    mean_fit_tau = float(np.mean(fitted))
    assert abs(mean_fit_tau - 200.0) / 200.0 < 0.05, (
        f"fitted tau biased: mean {mean_fit_tau:.1f} vs 200"
    )

    # The fit amplitude A is calibrated to bins_used so the plotted overlay
    # (which re-histograms with bins_used) lines up with the bars.
    dwells_cal = np.random.default_rng(3).exponential(150.0, 240)  # <300 -> <30 bins
    fit_cal = _fit_exp_dwell(dwells_cal)
    assert fit_cal["bins_used"] > 0
    hist_cal, edges_cal = np.histogram(dwells_cal, bins=fit_cal["bins_used"])
    cen_cal = 0.5 * (edges_cal[:-1] + edges_cal[1:])
    m_cal = hist_cal > 0
    pred_cal = fit_cal["A"] * np.exp(-cen_cal[m_cal] / fit_cal["tau_us"])
    assert 0.5 < float(np.median(pred_cal / hist_cal[m_cal])) < 2.0, (
        "dwell-histogram overlay mis-scaled relative to its own bins"
    )

    print("dwell_time_statistics: OK")

    # --- Task 1: dwell debounce ---
    rng = np.random.default_rng(0)
    # Clean telegraph: 50 us sample period, runs of ~40 samples (2 ms) per state
    sp_us = 50.0
    runs = []
    state = 0
    for _ in range(400):
        L = max(2, int(rng.exponential(40)))
        runs.append(np.full(L, state))
        state ^= 1
    clean = np.concatenate(runs).astype(int)
    t = np.arange(clean.size) * sp_us
    # Inject single-sample flickers (flip 3% of samples) -> fake fast switches
    noisy = clean.copy()
    flip = rng.random(noisy.size) < 0.03
    noisy[flip] ^= 1

    stats_clean = dwell_time_statistics(clean, t)
    stats_nodb = dwell_time_statistics(noisy, t)
    stats_db = dwell_time_statistics(noisy, t, merge_short_segments=True, min_dwell_bins=2)

    mean_clean = 0.5 * (stats_clean["mean_0"] + stats_clean["mean_1"])
    mean_nodb = 0.5 * (stats_nodb["mean_0"] + stats_nodb["mean_1"])
    mean_db = 0.5 * (stats_db["mean_0"] + stats_db["mean_1"])
    assert mean_nodb < 0.5 * mean_clean, f"expected flickers to bias mean low, got {mean_nodb} vs {mean_clean}"
    assert abs(mean_db - mean_clean) / mean_clean < 0.30, f"debounced mean {mean_db} far from clean {mean_clean}"
    # Debounce must respect gaps: a gap index must never merge across the boundary
    g = [clean.size // 2]
    _ = dwell_time_statistics(noisy, t, gap_indices=g, merge_short_segments=True, min_dwell_bins=2)
    print("dwell_time_statistics debounce: OK")

    # --- analyze_parity_run end-to-end ----------------------------------------
    import os, tempfile, h5py, json

    with tempfile.TemporaryDirectory() as tmpdir:
        # Build a synthetic raw .h5 mimicking what ZeroSpanParity.save_data writes.
        n_syn = 50_000
        sample_period_us_syn = 20.0
        rng_syn = np.random.default_rng(7)
        # Two IQ clouds, parity-modulated
        labels_syn = (np.cumsum(rng_syn.random(n_syn) < 0.005) % 2).astype(int)
        I_syn = np.where(labels_syn == 1,
                         rng_syn.normal(10.0, 0.5, n_syn),
                         rng_syn.normal(0.0, 0.5, n_syn))
        Q_syn = rng_syn.normal(0.0, 0.5, n_syn)
        t_syn = np.arange(n_syn) * sample_period_us_syn

        h5_path = os.path.join(tmpdir, "ZeroSpanParity_synthetic.h5")
        with h5py.File(h5_path, "w") as f:
            f.create_dataset("I", data=I_syn)
            f.create_dataset("Q", data=Q_syn)
            f.create_dataset("t_us", data=t_syn)
            f.create_dataset("gap_indices", data=np.array([], dtype=int))
            f.attrs["sample_period_us"] = sample_period_us_syn
            f.attrs["mode"] = "strobe"

        sep_syn = {"g_center": np.array([0.0, 0.0]),
                   "e_center": np.array([10.0, 0.0])}
        results = analyze_parity_run(
            h5_path=h5_path,
            separator=sep_syn,
            window_us=100_000.0,
            k_sigma=5.0,
            save_plots=True,
            out_dir=tmpdir,
        )
        assert "n_bursts" in results
        assert "baseline_rate_Hz" in results
        assert "mean_dwell_0_us" in results and "mean_dwell_1_us" in results

        base = os.path.splitext(os.path.basename(h5_path))[0]
        for suffix in ["_iq_scatter.png", "_parity_vs_time.png",
                       "_switch_rate_vs_time.png", "_dwell_histograms.png"]:
            png = os.path.join(tmpdir, base + suffix)
            assert os.path.exists(png), f"missing plot: {png}"

        sidecar_json = os.path.join(tmpdir, base + "_analysis.json")
        sidecar_h5   = os.path.join(tmpdir, base + "_analysis.h5")
        assert os.path.exists(sidecar_json)
        assert os.path.exists(sidecar_h5)
        with open(sidecar_json) as f:
            sj = json.load(f)
        assert "baseline_rate_Hz" in sj

    print("analyze_parity_run: OK")

    # --- Markov-trace dwell recovery at two cadences -------------------------
    # Same continuous-time Markov chain sampled at 20 us and 100 us must yield
    # consistent recovered dwell times (within statistical noise). This guards
    # against accidental scaling errors (Hz <-> MHz, us <-> samples) in the
    # sliding-rate or dwell-statistics code.
    def _markov_trace(n, p01, p10, rng_):
        bits_ = np.zeros(n, dtype=int)
        st = 0
        for k in range(n):
            bits_[k] = st
            if st == 0 and rng_.random() < p01: st = 1
            elif st == 1 and rng_.random() < p10: st = 0
        return bits_

    rng_mc = np.random.default_rng(42)
    # Continuous-time rates: lambda01 = 1/2ms, lambda10 = 1/4ms.
    # At 20 us cadence: p01 = 20e-6/2e-3 = 0.01; at 100 us cadence: p01 = 0.05.
    for sample_us, n in [(20.0, 200_000), (100.0, 40_000)]:
        p01 = sample_us * 1e-6 / 2e-3
        p10 = sample_us * 1e-6 / 4e-3
        bits_mc = _markov_trace(n, p01, p10, rng_mc)
        t_mc = np.arange(n) * sample_us
        st = dwell_time_statistics(bits_mc, t_mc)
        # Expected mean dwells: 2 ms (state 0), 4 ms (state 1).
        assert abs(st["mean_0"] - 2000.0) / 2000.0 < 0.2, (
            f"sample_us={sample_us}: mean_0={st['mean_0']:.1f} vs 2000")
        assert abs(st["mean_1"] - 4000.0) / 4000.0 < 0.2, (
            f"sample_us={sample_us}: mean_1={st['mean_1']:.1f} vs 4000")
    print("markov dwell at 20us and 100us cadence: OK")

    # --- _bin_iq_time correctness --------------------------------------------
    # Mean-binning a known ramp by 5x should give the per-bin means.
    I_ramp = np.arange(100, dtype=float)
    Q_ramp = np.zeros(100)
    t_ramp = np.arange(100, dtype=float) * 1.0  # 1 us per sample
    I_b, Q_b, t_b, gaps_b, n_drop = _bin_iq_time(I_ramp, Q_ramp, t_ramp, bin_us=5.0)
    assert I_b.size == 20, f"expected 20 bins, got {I_b.size}"
    assert n_drop == 0, f"expected 0 dropped, got {n_drop}"
    # Bin 0 contains samples 0..4 mean = 2.0; last bin samples 95..99 mean = 97.0.
    assert abs(I_b[0] - 2.0) < 1e-9
    assert abs(I_b[-1] - 97.0) < 1e-9
    # Bins must not cross gap boundaries.
    I_b2, Q_b2, t_b2, gaps_b2, n_drop2 = _bin_iq_time(
        I_ramp, Q_ramp, t_ramp, bin_us=5.0, gap_indices=[50]
    )
    assert 50 // 5 == 10
    assert gaps_b2 == [10], f"expected gap at bin 10, got {gaps_b2}"
    assert n_drop2 == 0
    # Bin straddling the gap must not exist; bin 9 ends at sample 49, bin 10 starts at 50.
    assert abs(I_b2[9] - np.mean(I_ramp[45:50])) < 1e-9
    assert abs(I_b2[10] - np.mean(I_ramp[50:55])) < 1e-9
    # Trailing samples that don't fill a full bin are dropped and counted.
    I_short = np.arange(13, dtype=float)
    Q_short = np.zeros(13)
    t_short_b = np.arange(13, dtype=float) * 1.0
    _, _, _, _, n_drop3 = _bin_iq_time(I_short, Q_short, t_short_b, bin_us=5.0)
    assert n_drop3 == 3, f"expected 3 dropped trailing samples, got {n_drop3}"
    print("_bin_iq_time: OK")

    # --- decimated analysis with explicit analysis_bin_us --------------------
    # Synthesize a decimated-style trace: very high sample rate, per-sample
    # noise so loud the apriori separator can't classify per-sample, but
    # binning at the integration window resolves parity bits reliably.
    # NOTE: the prior implementation auto-binned by `read_length_us`; that's
    # been removed because in a real decimated capture the entire trace IS one
    # read_length, so auto-binning collapsed every capture to a single point.
    # Callers must now pass `analysis_bin_us` when they want integrated bins.
    with tempfile.TemporaryDirectory() as tmpdir:
        rng_dec = np.random.default_rng(11)
        # 500 parity samples, 200 raw decimated samples per integration window
        n_bins = 500
        bin_size = 200
        n_raw = n_bins * bin_size
        # Underlying parity (one bit per bin)
        labels_bins = (np.cumsum(rng_dec.random(n_bins) < 0.01) % 2).astype(int)
        labels_raw = np.repeat(labels_bins, bin_size)
        # Loud per-raw-sample noise; mean per integration window resolves it.
        I_dec = np.where(labels_raw == 1, 10.0, 0.0) + rng_dec.normal(0, 8.0, n_raw)
        Q_dec = rng_dec.normal(0.0, 8.0, n_raw)
        sp_dec = 0.01  # us per raw sample (nominal)
        t_dec = np.arange(n_raw, dtype=float) * sp_dec
        bin_us = bin_size * sp_dec  # 2.0 us — synthetic "integration window"

        h5_dec = os.path.join(tmpdir, "ZeroSpanParity_dec_synth.h5")
        with h5py.File(h5_dec, "w") as f:
            f.create_dataset("I", data=I_dec)
            f.create_dataset("Q", data=Q_dec)
            f.create_dataset("t_us", data=t_dec)
            f.create_dataset("gap_indices", data=np.array([], dtype=int))
            f.attrs["sample_period_us"] = sp_dec
            f.attrs["mode"] = "decimated"
            f.attrs["read_length_us"] = bin_us

        sep_dec = {"g_center": np.array([0.0, 0.0]),
                   "e_center": np.array([10.0, 0.0])}
        # Caller-supplied analysis_bin_us recovers parity bits at >95% accuracy.
        res_dec = analyze_parity_run(
            h5_path=h5_dec, separator=sep_dec,
            window_us=100.0, k_sigma=5.0, save_plots=False, out_dir=tmpdir,
            analysis_bin_us=bin_us,
        )
        # Sidecar records the binning provenance so post-hoc readers can
        # tell raw rate from analysis rate apart.
        assert res_dec["analysis_bin_us"] == bin_us, res_dec
        assert res_dec["n_raw_samples"] == n_raw, res_dec
        assert res_dec["n_binned_samples"] == n_bins, res_dec
        assert res_dec["raw_sample_period_us"] == sp_dec
        assert res_dec["mode"] == "decimated"
        # Read back the binned bits from sidecar and check accuracy
        with h5py.File(os.path.join(tmpdir, "ZeroSpanParity_dec_synth_analysis.h5"), "r") as f:
            bits_out = np.array(f["binary_states"])
        # Bins are aligned to the underlying labels_bins
        assert bits_out.size == n_bins, (
            f"expected {n_bins} binned bits, got {bits_out.size}"
        )
        acc = np.mean(bits_out == labels_bins)
        assert acc > 0.95, f"decimated bin accuracy too low: {acc}"
    print("analyze_parity_run decimated with explicit analysis_bin_us: OK")

    # --- strobe-vs-decimated equivalence (synthetic) -------------------------
    # Build the same underlying parity trace, integrate it two ways:
    #   (a) one integrated sample per "rep" at sample_period_us (strobe-like)
    #   (b) raw decimated waveform at much higher rate, then bin by read_length
    # Recovered binary bits should agree where the cadences align.
    with tempfile.TemporaryDirectory() as tmpdir:
        rng_eq = np.random.default_rng(99)
        n_samples = 2000
        sample_period_us_eq = 5.0  # strobe cadence
        labels_eq = (np.cumsum(rng_eq.random(n_samples) < 0.01) % 2).astype(int)
        # Strobe: one integrated sample per rep with small noise
        I_strobe = np.where(labels_eq == 1, 10.0, 0.0) + rng_eq.normal(0, 0.3, n_samples)
        Q_strobe = rng_eq.normal(0.0, 0.3, n_samples)
        t_strobe = np.arange(n_samples) * sample_period_us_eq
        h5_strobe = os.path.join(tmpdir, "eq_strobe.h5")
        with h5py.File(h5_strobe, "w") as f:
            f.create_dataset("I", data=I_strobe)
            f.create_dataset("Q", data=Q_strobe)
            f.create_dataset("t_us", data=t_strobe)
            f.create_dataset("gap_indices", data=np.array([], dtype=int))
            f.attrs["sample_period_us"] = sample_period_us_eq
            f.attrs["mode"] = "strobe"

        # Decimated: 50 raw samples per cadence period (per "sample window"),
        # noisy per-raw-sample but mean-equivalent to strobe.
        raw_per_period = 50
        raw_sp = sample_period_us_eq / raw_per_period
        n_raw = n_samples * raw_per_period
        labels_raw = np.repeat(labels_eq, raw_per_period)
        I_dec = np.where(labels_raw == 1, 10.0, 0.0) + rng_eq.normal(
            0, 0.3 * np.sqrt(raw_per_period), n_raw)
        Q_dec = rng_eq.normal(0.0, 0.3 * np.sqrt(raw_per_period), n_raw)
        t_dec = np.arange(n_raw, dtype=float) * raw_sp
        h5_dec = os.path.join(tmpdir, "eq_dec.h5")
        with h5py.File(h5_dec, "w") as f:
            f.create_dataset("I", data=I_dec)
            f.create_dataset("Q", data=Q_dec)
            f.create_dataset("t_us", data=t_dec)
            f.create_dataset("gap_indices", data=np.array([], dtype=int))
            f.attrs["sample_period_us"] = raw_sp
            f.attrs["mode"] = "decimated"
            # No read_length_us attr: analyze_parity_run does not auto-bin by it
            # (binning is opt-in via the explicit analysis_bin_us arg below).

        sep_eq = {"g_center": np.array([0.0, 0.0]),
                  "e_center": np.array([10.0, 0.0])}
        analyze_parity_run(h5_path=h5_strobe, separator=sep_eq, window_us=100.0,
                           save_plots=False, out_dir=tmpdir)
        # Caller asks for explicit binning at sample_period_us_eq to match the
        # strobe cadence; without it, raw decimated noise dominates per sample.
        analyze_parity_run(h5_path=h5_dec, separator=sep_eq, window_us=100.0,
                           save_plots=False, out_dir=tmpdir,
                           analysis_bin_us=sample_period_us_eq)
        with h5py.File(os.path.join(tmpdir, "eq_strobe_analysis.h5"), "r") as f:
            bits_s = np.array(f["binary_states"])
        with h5py.File(os.path.join(tmpdir, "eq_dec_analysis.h5"), "r") as f:
            bits_d = np.array(f["binary_states"])
        assert bits_s.size == bits_d.size == n_samples, (
            f"strobe vs dec lengths differ: {bits_s.size} vs {bits_d.size} vs {n_samples}"
        )
        agreement = float(np.mean(bits_s == bits_d))
        assert agreement > 0.95, f"strobe-vs-decimated agreement too low: {agreement}"
    print("strobe-vs-decimated equivalence on synthetic data: OK")

    # --- decimated analysis preserves rate-provenance metadata ---------------
    # The previous t_us[-1] check was tautological: it wrote t_us=arange*sp
    # then verified the same relation after reload, exercising neither the
    # acquisition path nor the binning logic. The real concern surfaced in
    # review is that the *nominal* decimated rate from soccfg may not be the
    # true firmware rate; consumers must therefore be able to reconstruct
    # the time axis from saved metadata after a post-hoc rate calibration.
    # Verify that analyze_parity_run preserves raw_sample_period_us,
    # n_raw_samples, n_binned_samples, analysis_bin_us, and mode in the
    # sidecar — those are exactly the fields needed for that reconstruction.
    with tempfile.TemporaryDirectory() as tmpdir:
        N = 1024
        sp_attr = 1.0 / 307.2  # nominal QICK decimated period
        t_dec = np.arange(N) * sp_attr
        rng_meta = np.random.default_rng(13)
        I_meta = rng_meta.normal(5.0, 0.5, N)
        Q_meta = rng_meta.normal(0.0, 0.5, N)
        h5_t = os.path.join(tmpdir, "t_axis.h5")
        with h5py.File(h5_t, "w") as f:
            f.create_dataset("I", data=I_meta)
            f.create_dataset("Q", data=Q_meta)
            f.create_dataset("t_us", data=t_dec)
            f.create_dataset("gap_indices", data=np.array([], dtype=int))
            f.attrs["sample_period_us"] = sp_attr
            f.attrs["mode"] = "decimated"
            f.attrs["read_length_us"] = N * sp_attr
            f.attrs["decimated_fs_source"] = "soccfg.f_output_unverified"

        sep_meta = {"g_center": np.array([0.0, 0.0]),
                    "e_center": np.array([10.0, 0.0])}
        bin_us_meta = 32 * sp_attr  # bin 32 raw samples together
        summary = analyze_parity_run(
            h5_path=h5_t, separator=sep_meta, window_us=10.0,
            save_plots=False, out_dir=tmpdir,
            analysis_bin_us=bin_us_meta,
        )
        assert summary["mode"] == "decimated"
        assert summary["raw_sample_period_us"] == sp_attr
        assert summary["n_raw_samples"] == N
        assert summary["n_binned_samples"] == N // 32
        assert summary["analysis_bin_us"] == bin_us_meta
        assert summary["n_samples_dropped_by_binning"] == 0
        # Sidecar JSON carries the same fields
        with open(os.path.join(tmpdir, "t_axis_analysis.json")) as f:
            sj = json.load(f)
        for k in ("raw_sample_period_us", "n_raw_samples", "n_binned_samples",
                  "analysis_bin_us", "mode"):
            assert k in sj, f"sidecar missing {k}: {sj.keys()}"
    print("analyze_parity_run preserves rate-provenance metadata: OK")

    # --- Task 2: verify_modulation ---
    rng = np.random.default_rng(0)
    nblk, reps = 10, 500
    sp_us = 20.0
    ref = np.tile(np.concatenate([np.ones(reps), np.zeros(reps)]), nblk)
    t = np.arange(ref.size) * sp_us
    scores = np.where(ref > 0.5, 5.0, 0.0) + rng.normal(0, 1.0, ref.size)
    vm = verify_modulation(scores, t, ref)
    assert vm["correlation"] > 0.9, f"correlation too low: {vm['correlation']}"
    assert vm["modulation_depth"] > 3.0, f"depth too low: {vm['modulation_depth']}"
    assert abs(vm["lag_samples"]) <= 1, f"unexpected lag: {vm['lag_samples']}"
    # Null case: no modulation -> no false positive
    flat = rng.normal(0, 1.0, ref.size)
    vm0 = verify_modulation(flat, t, ref)
    assert abs(vm0["correlation"]) < 0.2, f"false positive correlation: {vm0['correlation']}"
    assert vm0["modulation_depth"] < 0.5, f"false positive depth: {vm0['modulation_depth']}"
    print("verify_modulation: OK")

    # --- Task 5: contrast_from_sweeps ---
    f = np.linspace(99.0, 101.0, 201)
    # Two slightly shifted Lorentzian complex responses
    def _lor(f0):
        return 1.0 / (1 + 1j * (f - f0) / 0.05)
    Z_off = _lor(100.0)
    Z_on = _lor(100.05)
    c = contrast_from_sweeps(f, Z_on, Z_off)
    assert np.isfinite(c["best_freq"]), c
    assert 99.5 < c["best_freq"] < 100.5, c["best_freq"]
    assert c["max_contrast"] > 0, c["max_contrast"]
    assert c["contrast_snr"] > 3.0, c["contrast_snr"]
    # empty input
    ce = contrast_from_sweeps(np.array([]), np.array([]), np.array([]))
    assert not np.isfinite(ce["best_freq"]), ce
    print("contrast_from_sweeps: OK")

    # --- Task 8: projected_histogram_snr ---
    rng = np.random.default_rng(0)
    bim = np.concatenate([rng.normal(-3, 1, 5000), rng.normal(3, 1, 5000)])
    h = projected_histogram_snr(bim)
    assert h["is_bimodal"], h
    assert h["delta_bic"] > 0, h["delta_bic"]
    assert h["separation_snr"] > 2.0, h["separation_snr"]
    uni = rng.normal(0, 1, 10000)
    hu = projected_histogram_snr(uni)
    assert not hu["is_bimodal"], hu
    assert hu["delta_bic"] <= 0, hu["delta_bic"]
    print("projected_histogram_snr: OK")

    # --- Task 9: bin_size_sweep ---
    rng = np.random.default_rng(1)
    # Markov telegraph at 10 us raw sample period, mean dwell ~2 ms, heavy per-sample noise
    sp_raw = 10.0
    n = 200_000
    p = sp_raw / 2000.0  # switch prob per sample for ~2 ms dwell
    state = 0
    bits = np.empty(n, dtype=int)
    for i in range(n):
        if rng.random() < p:
            state ^= 1
        bits[i] = state
    centers = np.array([[0.0, 0.0], [4.0, 0.0]])
    I = centers[bits, 0] + rng.normal(0, 3.0, n)   # noisy: small bins won't separate
    Q = centers[bits, 1] + rng.normal(0, 3.0, n)
    t = np.arange(n) * sp_raw
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([4.0, 0.0])}
    res = bin_size_sweep(I, Q, t, sep, bin_list_us=[100, 200, 500, 1000])
    assert np.isfinite(res["best_bin_us"]), res
    snr = np.array(res["separation_snr_per_bin"], dtype=float)
    assert snr[-1] >= snr[0], f"separation should not be worse at large bins: {snr}"
    print("bin_size_sweep: OK")

    # --- Task 10: threshold_stability ---
    rng = np.random.default_rng(2)
    sp = 50.0
    n = 100_000
    p = sp / 2000.0
    state = 0
    bits = np.empty(n, dtype=int)
    for i in range(n):
        if rng.random() < p:
            state ^= 1
        bits[i] = state
    t = np.arange(n) * sp
    clean_scores = np.where(bits == 1, 4.0, -4.0) + rng.normal(0, 1.0, n)  # well separated
    noise_scores = rng.normal(0, 1.0, n)  # pure noise
    ts_clean = threshold_stability(clean_scores, t)
    ts_noise = threshold_stability(noise_scores, t)
    assert ts_clean["tau_cv"] < ts_noise["tau_cv"], (ts_clean["tau_cv"], ts_noise["tau_cv"])
    # The clean grid must sit in the VALLEY, i.e. between the two lobes at +/-4,
    # not inside them. A percentile grid (the old default) put 4 of 5 thresholds
    # roughly 3 sigma deep into a lobe, which chopped a clean telegraph into noise
    # and inverted the metric this test checks.
    _grid = np.asarray(ts_clean["threshold_list"], dtype=float)
    assert np.all(np.abs(_grid) < 3.0), f"threshold grid left the valley: {_grid}"
    # Unimodal scores have no valley: fall back to percentiles without raising.
    _uni_grid = _default_threshold_grid(rng.normal(0, 1.0, 5000))
    assert len(_uni_grid) == 5 and np.all(np.isfinite(_uni_grid)), _uni_grid
    print("threshold_stability: OK")

    # =====================================================================
    # Regression guards for the fixed-2026-07-28 defect set. Each of these
    # reproduces a bug the suite above could not see.
    # =====================================================================

    # --- apriori_axis vs apriori on a DRIVEN steady state --------------------
    # The zero-span measurement parks a CW drive, so both parity states sit at
    # small |e> population -- i.e. both clouds land on the SAME side of the g/e
    # midpoint. Plain "apriori" thresholds at that midpoint and therefore labels
    # the whole trace one state: zero switches, one dwell run, nan tau, and a
    # sidecar that looks like a successful run. "apriori_axis" keeps the g->e
    # projection axis but takes the threshold from the trace itself.
    rng = np.random.default_rng(7)
    _sp = 40.0
    _n = 60_000
    _p_sw = _sp / 3000.0                      # ~3 ms parity lifetime
    _state = 0
    _true = np.empty(_n, dtype=int)
    for i in range(_n):
        if rng.random() < _p_sw:
            _state ^= 1
        _true[i] = _state
    # g at (0,0), e at (10,0) from the pi-pulse calibration; the DRIVEN steady
    # states sit at only 8% and 14% excited population -- both far below the
    # midpoint at I = 5.
    _g = np.array([0.0, 0.0]); _e = np.array([10.0, 0.0])
    # Level split 0.6 with sigma 0.12 -> 5 sigma of separation, i.e. a resolvable
    # (but far from noiseless) per-sample discrimination.
    _lvl = np.where(_true == 1, 1.4, 0.8)
    _I = _lvl + rng.normal(0, 0.12, _n)
    _Q = rng.normal(0, 0.12, _n)
    _t = np.arange(_n) * _sp
    _sep_drv = {"g_center": _g, "e_center": _e}

    _old = classify_parity_trace(_I, _Q, separator=_sep_drv, method="apriori")
    assert _old["binary_states"].sum() == 0, (
        "test setup wrong: the driven clouds should both be below the g/e "
        f"midpoint, got {_old['binary_states'].sum()} samples above it")
    _old_rate = sliding_window_switch_rate(_old["binary_states"], _t, 5000.0)
    assert _old_rate["switches_per_window"].sum() == 0, (
        "midpoint thresholding should find NO switches on a driven trace")

    _new = classify_parity_trace(_I, _Q, separator=_sep_drv, method="apriori_axis")
    _acc = max(np.mean(_new["binary_states"] == _true),
               np.mean(_new["binary_states"] != _true))   # label sign is arbitrary
    assert _acc > 0.98, f"apriori_axis accuracy on a driven trace: {_acc}"
    # Threshold must land between the two driven levels (projected onto e-g, the
    # axis has |e-g| = 10, and the midpoint offset makes scores negative here).
    assert np.isfinite(_new["threshold"]), _new["threshold"]
    _stats_new = dwell_time_statistics(_new["binary_states"], _t,
                                       merge_short_segments=True, min_dwell_bins=2)
    assert _stats_new["n_runs_0"] > 5 and _stats_new["n_runs_1"] > 5, _stats_new
    for _tau in (_stats_new["exp_fit_0"]["tau_us"], _stats_new["exp_fit_1"]["tau_us"]):
        assert np.isfinite(_tau) and 1000.0 < _tau < 9000.0, (
            f"recovered tau {_tau} us off the injected 3000 us")
    # And the failure mode it replaces: midpoint thresholding yields a single run.
    _stats_old = dwell_time_statistics(_old["binary_states"], _t)
    assert _stats_old["n_runs_0"] == 1 and _stats_old["n_runs_1"] == 0, _stats_old
    print("classify_parity_trace apriori_axis recovers a driven telegraph: OK")

    # --- vectorized switch rate == the old masked loop -----------------------
    def _rate_reference(bits_, t_, window_us_, step_us_, gaps_):
        """Literal transcription of the pre-vectorization masked loop."""
        d = np.abs(np.diff(np.asarray(bits_, dtype=int)))
        for gi in (gaps_ or []):
            if 1 <= int(gi) < len(bits_):
                d[int(gi) - 1] = 0
        te = np.asarray(t_, dtype=float)[1:]
        t0, t1 = t_[0], t_[-1]
        if t1 - t0 < window_us_:
            st = np.array([t0])
        else:
            st = np.arange(t0, t1 - window_us_ + step_us_, step_us_)
        cnt = np.zeros(st.size, dtype=int)
        for i, s in enumerate(st):
            if i == st.size - 1:
                m = (te >= s) & (te <= s + window_us_)
            else:
                m = (te >= s) & (te < s + window_us_)
            cnt[i] = int(d[m].sum())
        return cnt

    rng = np.random.default_rng(11)
    for _gaps in ([], [977], [301, 602, 903]):
        _b = (rng.random(2000) < 0.15).astype(int)
        _tt = np.arange(2000) * 20.0
        _got = sliding_window_switch_rate(_b, _tt, 1000.0, step_us=500.0,
                                          gap_indices=_gaps)
        _exp = _rate_reference(_b, _tt, 1000.0, 500.0, _gaps)
        assert np.array_equal(_got["switches_per_window"], _exp), (
            f"vectorized window counts differ from the masked loop (gaps={_gaps}):\n"
            f"{_got['switches_per_window']}\n{_exp}")
    # ... and it must be fast enough to actually use. The masked loop is O(M*N):
    # ~1.4e10 element ops for this size, i.e. minutes.
    import time as _time
    _bigb = (rng.random(1_000_000) < 0.02).astype(int)
    _bigt = np.arange(_bigb.size) * 40.0
    _t0 = _time.perf_counter()
    _big = sliding_window_switch_rate(_bigb, _bigt, 1000.0)
    _elapsed = _time.perf_counter() - _t0
    assert _big["rate_Hz"].size > 10_000, _big["rate_Hz"].size
    assert _elapsed < 5.0, f"switch rate took {_elapsed:.1f} s on 1e6 samples"
    print(f"sliding_window_switch_rate vectorized (1e6 samples in {_elapsed:.2f} s): OK")

    # --- debounce: terminates, and matches the old semantics -----------------
    # The old implementation spun forever whenever a gap-delimited segment held a
    # single too-short run: with one run there is no left OR right neighbour, so it
    # flagged "changed" without changing anything.
    assert np.array_equal(_debounce_bits(np.array([1]), 2), np.array([1]))
    assert np.array_equal(_debounce_bits(np.array([0]), 3), np.array([0]))
    # Reachable in practice through consecutive gap indices -> a length-1 segment.
    _hb = np.array([0, 1, 0, 1, 1, 0, 0, 1])
    _out_seg = _debounce_bits_segmented(_hb, [1, 2], 2)
    assert _out_seg.size == _hb.size, _out_seg
    # Flicker removal on a plain trace.
    assert np.array_equal(_debounce_bits(np.array([0, 0, 1, 0, 0]), 2),
                          np.zeros(5, dtype=int))
    assert np.array_equal(_debounce_bits(np.array([0, 0, 1, 1, 0, 1, 1, 1]), 2),
                          np.array([0, 0, 1, 1, 1, 1, 1, 1]))
    # A short LEADING run has no left neighbour: it joins the run on its right.
    assert np.array_equal(_debounce_bits(np.array([1, 0, 0, 0]), 2),
                          np.zeros(4, dtype=int))
    # Idempotent, and every surviving run is at least min_len long.
    rng = np.random.default_rng(13)
    _noisy = (rng.random(20000) < 0.35).astype(int)
    _d1 = _debounce_bits(_noisy, 3)
    assert np.array_equal(_debounce_bits(_d1, 3), _d1), "debounce is not idempotent"
    _edges = np.flatnonzero(np.diff(_d1)) + 1
    _runs = np.diff(np.concatenate(([0], _edges, [_d1.size])))
    assert _runs.min() >= 3 or _runs.size == 1, f"short run survived: {_runs.min()}"
    # Worst case for the old O(short_runs x N) version: alternating bits.
    _alt = np.arange(200_000) % 2
    _t0 = _time.perf_counter()
    _da = _debounce_bits(_alt, 2)
    _elapsed = _time.perf_counter() - _t0
    assert _elapsed < 5.0, f"debounce took {_elapsed:.1f} s on alternating 2e5 bits"
    assert len(set(_da.tolist())) == 1, "alternating bits should collapse to one state"
    print(f"_debounce_bits vectorized + terminating ({_elapsed:.2f} s worst case): OK")

    # --- burst duration is the window span, not the stride -------------------
    # With the default 50% overlap a single flagged window covers window_us of
    # time; measuring it in strides reported half that, so min_duration_us was
    # compared against a value off by the overlap factor.
    _centers = np.arange(10) * 500.0 + 500.0      # window 1000, step 500
    _rate = np.zeros(10); _rate[4] = 10_000.0
    _b1 = detect_bursts(_rate, _centers, baseline_rate=0.0, k_sigma=1.0,
                        window_us=1000.0)
    assert len(_b1) == 1, _b1
    assert abs(_b1[0]["duration_us"] - 1000.0) < 1e-9, _b1[0]["duration_us"]
    # A min_duration_us equal to one window must therefore KEEP that burst.
    _b2 = detect_bursts(_rate, _centers, baseline_rate=0.0, k_sigma=1.0,
                        window_us=1000.0, min_duration_us=1000.0)
    assert len(_b2) == 1, "one full window was rejected by min_duration_us=window"
    print("detect_bursts duration uses the window span: OK")

    # --- verify_modulation honours gap_indices -------------------------------
    # modulated_strobe_acquire emits one block per modulation half-period, so every
    # block boundary is a gap and the stitched t_us omits the inter-block dead
    # time. gap_indices was accepted and then ignored.
    _npb = 400
    _blocks = [1.0, 0.0] * 6
    _ref = np.concatenate([np.full(_npb, g) for g in _blocks])
    _gaps_mod = [_npb * k for k in range(1, len(_blocks))]
    rng = np.random.default_rng(17)
    _sc = 5.0 * _ref + rng.normal(0, 0.4, _ref.size)
    _tm = np.arange(_ref.size) * 20.0
    _vm = verify_modulation(_sc, _tm, _ref, gap_indices=_gaps_mod)
    assert _vm["correlation"] > 0.9, _vm["correlation"]
    assert _vm["modulation_depth"] > 4.0, _vm["modulation_depth"]
    assert abs(_vm["lag_samples"]) <= 2, _vm["lag_samples"]
    assert _vm["n_segments_used"] == len(_blocks), _vm["n_segments_used"]
    # 400 samples x 20 us = 8 ms half-period -> 62.5 Hz. Counting half-periods as
    # (transitions + 1) is what makes this exact rather than 12% low.
    assert abs(_vm["injected_freq_hz"] - 62.5) / 62.5 < 0.05, _vm["injected_freq_hz"]
    # Null case: no modulation must not produce a false positive.
    _vm0 = verify_modulation(rng.normal(0, 1.0, _ref.size), _tm, _ref,
                             gap_indices=_gaps_mod)
    assert abs(_vm0["correlation"]) < 0.3, _vm0["correlation"]
    assert _vm0["modulation_depth"] < 0.5, _vm0["modulation_depth"]
    print("verify_modulation respects gap_indices: OK")

    # --- the gate must be judged at the BLOCK level, not per sample -----------
    # Found on hardware 2026-07-29: a modulation where every driven block sat above
    # every undriven block scored snr=0.55 and correlation=-0.27, i.e. "FAIL",
    # because (a) snr used the per-sample spread and (b) the correlation lag scan
    # ran over the whole record and, for a periodic reference, picked the
    # anti-correlated peak half a period away.
    _npb = 500
    _nblk = 20
    _sched_on = np.array([k % 2 == 0 for k in range(_nblk)])
    _ref_b = np.concatenate([np.full(_npb, 1.0 if o else 0.0) for o in _sched_on])
    _gaps_b = [_npb * k for k in range(1, _nblk)]
    _tb = np.arange(_ref_b.size) * 40.0
    rng = np.random.default_rng(31)
    # Per-sample SNR deliberately well BELOW 1 (0.5), as on the real device, and the
    # driven blocks deliberately much more variable than the undriven ones.
    _depth = 1.5
    _lvl = np.concatenate([
        np.full(_npb, (_depth + rng.normal(0, 0.35)) if o else 0.0)
        for o in _sched_on])
    _sc_b = _lvl + rng.normal(0, 3.0, _ref_b.size)
    _vm_b = verify_modulation(_sc_b, _tb, _ref_b, gap_indices=_gaps_b)
    assert _vm_b["snr"] < 1.0, (
        f"test setup: per-sample snr should be <1, got {_vm_b['snr']}")
    assert _vm_b["block_separation_auc"] > 0.95, _vm_b["block_separation_auc"]
    assert _vm_b["block_tstat"] > 5.0, _vm_b["block_tstat"]
    assert _vm_b["correlation"] > 0, (
        f"correlation must be POSITIVE for an in-phase reference, got "
        f"{_vm_b['correlation']}")
    assert abs(_vm_b["lag_samples"]) <= 4, _vm_b["lag_samples"]
    # recovered_freq must come from the block means: every segment here has a
    # CONSTANT reference, so a single-segment FFT sees no modulation at all.
    # 500 samples x 40 us = 20 ms half-period -> 25 Hz.
    assert _vm_b["recovered_freq_source"] == "block_means", _vm_b
    assert abs(_vm_b["recovered_freq_hz"] - 25.0) < 2.0, _vm_b["recovered_freq_hz"]
    assert abs(_vm_b["injected_freq_hz"] - 25.0) < 2.0, _vm_b["injected_freq_hz"]
    # Anti-phase reference must come back NEGATIVE, not silently made positive by
    # an argmax over |correlation|.
    _vm_anti = verify_modulation(_sc_b, _tb, 1.0 - _ref_b, gap_indices=_gaps_b)
    assert _vm_anti["correlation"] < 0, (
        f"anti-phase reference must score negative, got {_vm_anti['correlation']}")
    # A truly unmodulated trace must not pass.
    _vm_null = verify_modulation(rng.normal(0, 3.0, _ref_b.size), _tb, _ref_b,
                                 gap_indices=_gaps_b)
    assert _vm_null["block_separation_auc"] < 0.95, _vm_null["block_separation_auc"]
    assert _vm_null["block_tstat"] < 5.0, _vm_null["block_tstat"]
    print("verify_modulation judges the gate at the block level: OK")

    # --- analyze_parity_run exposes the debounce knobs -----------------------
    # The main pipeline used to report UN-debounced dwell times with no way to
    # turn debouncing on, i.e. exactly the values the debounce test above shows
    # are biased low by >2x under a few percent misclassification.
    with tempfile.TemporaryDirectory() as tmpdir:
        rng = np.random.default_rng(23)
        _n = 40_000
        _sp = 40.0
        _p = _sp / 4000.0
        _st = 0
        _bt = np.empty(_n, dtype=int)
        for i in range(_n):
            if rng.random() < _p:
                _st ^= 1
            _bt[i] = _st
        _flick = rng.random(_n) < 0.03          # 3% single-sample misclassification
        _obs = np.where(_flick, 1 - _bt, _bt)
        _Iw = np.where(_obs == 1, 1.0, 0.0)
        _Qw = np.zeros(_n)
        _h5 = os.path.join(tmpdir, "dbtest_data.h5")
        with h5py.File(_h5, "w") as f:
            f.create_dataset("I", data=_Iw)
            f.create_dataset("Q", data=_Qw)
            f.create_dataset("t_us", data=np.arange(_n) * _sp)
            f.create_dataset("gap_indices", data=np.array([], dtype=int))
            f.attrs["sample_period_us"] = _sp
            f.attrs["mode"] = "strobe"
        _sep_w = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([1.0, 0.0])}
        _on = analyze_parity_run(_h5, separator=_sep_w, window_us=4000.0,
                                 classifier_method="apriori_axis", save_plots=False,
                                 out_dir=tmpdir, merge_short_segments=True,
                                 min_dwell_bins=2)
        _off = analyze_parity_run(_h5, separator=_sep_w, window_us=4000.0,
                                  classifier_method="apriori_axis", save_plots=False,
                                  out_dir=tmpdir, merge_short_segments=False)
        assert _on["merge_short_segments"] is True and _on["min_dwell_bins"] == 2, _on
        assert _off["merge_short_segments"] is False, _off
        # Debounced tau lands near the injected 4000 us; un-debounced is biased low.
        _tau_on = _on["mean_dwell_0_us"]
        _tau_off = _off["mean_dwell_0_us"]
        assert _tau_on > 2.0 * _tau_off, (
            f"debounce made no difference: on={_tau_on}, off={_tau_off}")
        assert 2000.0 < _tau_on < 8000.0, f"debounced dwell {_tau_on} us"
        # Switch rate must use the SAME bit sequence as the dwell statistics.
        assert _on["baseline_rate_Hz"] < _off["baseline_rate_Hz"], (
            _on["baseline_rate_Hz"], _off["baseline_rate_Hz"])
        assert "classifier_threshold" in _on
    print("analyze_parity_run debounce knobs: OK")

    # --- sample period is not read across a gap ------------------------------
    # A leading 1-sample segment makes t[1]-t[0] a GAP width, not a sample period.
    _tg = np.array([0.0, 1000.0, 1020.0, 1040.0, 1060.0])
    assert _infer_sample_period(_tg, _gap_segment_edges([1], _tg.size)) == 20.0
    assert _infer_sample_period(np.array([0.0, 20.0, 40.0])) == 20.0
    assert _infer_sample_period(np.array([5.0])) == 0.0
    print("_infer_sample_period skips gap-straddling differences: OK")

    # =========================================================================
    # Threshold-free PSD rate (parity_psd_rate and friends)
    #
    # The claims under test are the ones that motivate the whole approach:
    #   (a) f_c recovers the injected Gamma,
    #   (b) additive readout noise moves the FLOOR, not f_c,
    #   (c) a 3:1 occupancy imbalance does not move f_c either,
    #   (d) the projection scale cancels,
    #   (e) gaps are respected and never FFT'd across,
    #   (f) f_c is invariant under analysis binning, while
    #   (g) pure noise yields no corner at all.
    # =========================================================================

    def _make_rts(n, p01, p10, rng):
        """Discrete-time two-state telegraph, mean dwells 1/p01 and 1/p10 samples.

        Built from geometric dwell lengths rather than a per-sample coin flip:
        same process, but O(n_runs) instead of O(n) Python-level iterations.
        """
        parts, st, total = [], 0, 0
        while total < n:
            p = p01 if st == 0 else p10
            L = int(rng.geometric(p))
            parts.append(np.full(L, float(st)))
            total += L
            st ^= 1
        return np.concatenate(parts)[:n]

    # Exact corner frequency of the DISCRETE chain: the correlation decays as
    # (1 - p01 - p10)^k per sample, so Gamma = -ln(1-p01-p10)/dt. For the small
    # p used here that is within 0.5% of the continuous-time (p01+p10)/dt, but
    # asserting against the exact value keeps the tolerances about the ESTIMATOR
    # rather than about a discretisation the test itself introduced.
    def _fc_expected(p01, p10, dt_us):
        gamma_per_us = -np.log(1.0 - p01 - p10) / dt_us
        return gamma_per_us * 1e6 / (2.0 * np.pi)

    _dt = 20.0
    _n = 200_000
    _p = 1.0 / 200.0                       # 200 samples = 4000 us mean dwell
    _fc_true = _fc_expected(_p, _p, _dt)   # ~80 Hz
    _t_rts = np.arange(_n) * _dt
    rng = np.random.default_rng(7)
    _state = _make_rts(_n, _p, _p, rng)

    # (a) + (b): same underlying telegraph, three very different noise levels.
    _fcs = {}
    for _sigma in (0.1, 1.0, 3.0):
        _tr = _state + rng.normal(0.0, _sigma, _n)
        _r = parity_psd_rate(_tr, t_us=_t_rts)
        assert _r["is_lorentzian"], (_sigma, _r["verdict"])
        assert abs(_r["f_c_hz"] - _fc_true) / _fc_true < 0.15, (
            f"sigma={_sigma}: f_c={_r['f_c_hz']:.3g} Hz vs expected "
            f"{_fc_true:.3g} Hz")
        assert _r["exponent_consistent_with_rts"], (_sigma, _r["exponent_free"])
        # With a decade of visible knee the exponent really does pin to 2; at
        # sigma=3 (S_0/S_white of a few) only ~an octave of slope exists and it
        # scatters upward, which is why the accepted window is loose above 2.
        if _r["lorentzian_snr"] > 10.0:
            assert abs(_r["exponent_free"] - 2.0) < 0.35, (
                _sigma, _r["exponent_free"], _r["lorentzian_snr"])
        _fcs[_sigma] = _r["f_c_hz"]
        # Gamma/f_c and tau bookkeeping must be self-consistent.
        assert abs(_r["gamma_total_hz"] - 2 * np.pi * _r["f_c_hz"]) < 1e-6
        assert abs(_r["tau_symmetric_us"] - 1e6 / (np.pi * _r["f_c_hz"])) < 1e-3
    # The floor must rise ~sigma^2 while f_c stays put -- that is the whole claim.
    _r_lo = parity_psd_rate(_state + rng.normal(0, 0.1, _n), t_us=_t_rts)
    _r_hi = parity_psd_rate(_state + rng.normal(0, 3.0, _n), t_us=_t_rts)
    assert _r_hi["s_white"] > 100.0 * _r_lo["s_white"], (
        f"floor did not scale with noise power: {_r_lo['s_white']:.3g} -> "
        f"{_r_hi['s_white']:.3g}")
    assert _r_lo["lorentzian_snr"] > _r_hi["lorentzian_snr"]
    _spread = (max(_fcs.values()) - min(_fcs.values())) / _fc_true
    assert _spread < 0.15, f"f_c moved {_spread:.1%} across a 30x noise range"
    print(f"parity_psd_rate recovers f_c={_fc_true:.1f} Hz across a 30x noise "
          f"range (spread {_spread:.1%}): OK")

    # (g) Pure white noise must NOT produce a corner. This is the null that makes
    # a positive result meaningful, and the case the counted rate cannot reject.
    _r_null = parity_psd_rate(rng.normal(0, 1.0, _n), t_us=_t_rts)
    assert not _r_null["is_lorentzian"], _r_null["verdict"]
    print(f"parity_psd_rate rejects white noise: {_r_null['verdict'][:70]}: OK")

    # Trap 1 from the section header: 1/f drift (gain wander, TLS, slow charge
    # motion) also rises toward low frequency. It must NOT be sold as a
    # telegraph. Either the corner lands outside the usable band (rejected) or
    # the free exponent comes out near 1 -- both are honest outcomes, and the
    # test asserts one of them rather than pretending to know which.
    _wn = rng.normal(0, 1.0, _n)
    _F = np.fft.rfft(_wn)
    _fk = np.fft.rfftfreq(_n, d=1.0)
    _F[1:] /= np.sqrt(_fk[1:])          # white -> 1/f power
    _F[0] = 0.0
    _pink = np.fft.irfft(_F, n=_n)
    _pink = _pink / np.std(_pink)
    _r_pink = parity_psd_rate(_pink, t_us=_t_rts)
    assert not _r_pink["is_lorentzian"], (
        f"1/f drift passed as a telegraph: {_r_pink['verdict']}")
    assert _r_pink["exponent_free"] < 1.5, _r_pink["exponent_free"]
    assert "exponent" in _r_pink["reason"], _r_pink["reason"]
    print(f"parity_psd_rate rejects 1/f drift on the knee exponent "
          f"({_r_pink['exponent_free']:.2f}): OK")
    # ... and a telegraph sitting ON TOP of drift still yields its own corner,
    # which is the realistic case: assert f_c survives added 1/f at equal power.
    _r_mix = parity_psd_rate(_state + 1.0 * _pink + rng.normal(0, 0.5, _n),
                             t_us=_t_rts)
    assert abs(_r_mix["f_c_hz"] - _fc_true) / _fc_true < 0.25, (
        f"f_c={_r_mix['f_c_hz']:.3g} Hz under 1/f contamination vs "
        f"{_fc_true:.3g} Hz")
    print(f"parity_psd_rate holds f_c under equal-power 1/f contamination "
          f"({_r_mix['f_c_hz']:.1f} vs {_fc_true:.1f} Hz): OK")

    # (c) Asymmetric rates: 3:1 occupancy imbalance, exactly the pathology that
    # biases the thresholded rate. Gamma = 1/tau_0 + 1/tau_1 must still come out.
    _p01, _p10 = 1.0 / 100.0, 1.0 / 300.0
    _fc_asym = _fc_expected(_p01, _p10, _dt)
    _state_a = _make_rts(_n, _p01, _p10, rng)
    _occ = float(np.mean(_state_a))
    assert 0.70 < _occ < 0.80, f"test setup: occupancy {_occ:.2f}, wanted ~0.75"
    _r_a = parity_psd_rate(_state_a + rng.normal(0, 1.0, _n), t_us=_t_rts)
    assert _r_a["is_lorentzian"], _r_a["verdict"]
    assert abs(_r_a["f_c_hz"] - _fc_asym) / _fc_asym < 0.15, (
        f"asymmetric: f_c={_r_a['f_c_hz']:.3g} vs expected {_fc_asym:.3g}")
    # Gamma is the SUM of the two directional rates, not either one.
    _gamma_true = (1.0 / 2000.0 + 1.0 / 6000.0) * 1e6
    assert abs(_r_a["gamma_total_hz"] - _gamma_true) / _gamma_true < 0.15
    print(f"parity_psd_rate is unbiased at {_occ:.0%}/{1 - _occ:.0%} occupancy "
          f"(f_c={_r_a['f_c_hz']:.1f} vs {_fc_asym:.1f} Hz): OK")

    # (d) Projection scale cancels: the separator's arbitrary units must not
    # reach the answer.
    _tr_ref = _state + rng.normal(0, 1.0, _n)
    _r1 = parity_psd_rate(_tr_ref, t_us=_t_rts)
    _r2 = parity_psd_rate(_tr_ref * 1234.5, t_us=_t_rts)
    assert abs(_r1["f_c_hz"] - _r2["f_c_hz"]) / _r1["f_c_hz"] < 1e-6, (
        _r1["f_c_hz"], _r2["f_c_hz"])
    assert abs(_r1["lorentzian_snr"] - _r2["lorentzian_snr"]) / \
           _r1["lorentzian_snr"] < 1e-3
    assert _r2["s_white"] > 1e5 * _r1["s_white"]
    print("parity_psd_rate is invariant under projection rescaling: OK")

    # (e) Gaps: four declared segments must be transformed separately and
    # averaged, and a segment too short for nperseg must be reported as skipped
    # rather than silently dropped.
    _gaps_psd = [50_000, 100_000, 150_000, 199_990]
    _r_gap = parity_psd_rate(_tr_ref, t_us=_t_rts, gap_indices=_gaps_psd,
                             nperseg=8192)
    assert _r_gap["n_segments_used"] == 4, _r_gap["n_segments_used"]
    assert _r_gap["n_segments_skipped"] == 1, _r_gap["n_segments_skipped"]
    assert _r_gap["is_lorentzian"], _r_gap["verdict"]
    assert abs(_r_gap["f_c_hz"] - _fc_true) / _fc_true < 0.15, _r_gap["f_c_hz"]
    # nperseg can never exceed the longest segment, whatever the caller asks for.
    _r_cap = parity_psd_rate(_tr_ref, t_us=_t_rts, gap_indices=[100],
                             nperseg=10 ** 7)
    assert _r_cap["nperseg_used"] <= _n, _r_cap["nperseg_used"]
    print("parity_psd_rate segments at gaps and reports skipped segments: OK")

    # A record with no usable spectrum reports a reason instead of raising.
    _r_short = parity_psd_rate(np.zeros(3), sample_period_us=20.0)
    assert not _r_short["is_lorentzian"] and _r_short["reason"], _r_short
    assert np.isnan(_r_short["f_c_hz"])
    _r_nan = parity_psd_rate(np.array([1.0, np.nan] * 100), sample_period_us=20.0)
    assert "non-finite" in _r_nan["reason"], _r_nan["reason"]
    print("parity_psd_rate degrades gracefully on unusable input: OK")

    # (f) Bin-size invariance. A real telegraph holds one f_c across bin sizes
    # short compared with 1/f_c; threshold noise crossings do not.
    _sep_psd = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([1.0, 0.0])}
    _sw = psd_rate_vs_bin(_tr_ref, np.zeros(_n), _t_rts, separator=_sep_psd,
                          bin_list_us=(0, 40, 100, 200))
    assert _sw["n_bins_used"] == 4, (_sw["n_bins_used"], _sw["is_lorentzian_per_bin"])
    assert _sw["f_c_cv"] < 0.15, (_sw["f_c_cv"], _sw["f_c_per_bin"])
    assert abs(_sw["f_c_mean_hz"] - _fc_true) / _fc_true < 0.15, _sw["f_c_mean_hz"]
    # Same sweep on noise: no bin size may produce a corner.
    _sw_null = psd_rate_vs_bin(rng.normal(0, 1.0, _n), np.zeros(_n), _t_rts,
                               separator=_sep_psd, bin_list_us=(0, 40, 100, 200))
    assert not any(_sw_null["is_lorentzian_per_bin"]), _sw_null
    print(f"psd_rate_vs_bin: f_c stable to {_sw['f_c_cv']:.1%} over 4 bin sizes, "
          f"and finds nothing in noise: OK")

    # The separator-free path (principal axis) must land on the same f_c, since
    # that is what makes psd_rate_from_h5 usable with no calibration.
    _theta = 0.6
    _Ir = _tr_ref * np.cos(_theta) + rng.normal(0, 0.05, _n)
    _Qr = _tr_ref * np.sin(_theta) + rng.normal(0, 0.05, _n)
    _r_pca = parity_psd_rate(_pca_scores(_Ir, _Qr), t_us=_t_rts)
    assert _r_pca["is_lorentzian"], _r_pca["verdict"]
    assert abs(_r_pca["f_c_hz"] - _fc_true) / _fc_true < 0.15, _r_pca["f_c_hz"]
    print("_pca_scores recovers f_c with no separator: OK")

    # --- integration: the PSD rate survives what the counted rate does not ----
    # Same synthetic device as the debounce test above (tau = 4000 us both ways,
    # so 250 transitions/s) but with 8% single-sample misclassification. The
    # counted rate inflates badly; the PSD sees that flicker as floor and keeps
    # the corner where it belongs.
    with tempfile.TemporaryDirectory() as tmpdir:
        rng = np.random.default_rng(11)
        _n2 = 200_000
        _sp2 = 20.0
        _st2 = _make_rts(_n2, 1.0 / 200.0, 1.0 / 200.0, rng)
        _true_trans_per_s = 2.0 / (2.0 * 200.0 * _sp2 * 1e-6)   # 250 /s
        _flick2 = rng.random(_n2) < 0.08
        _obs2 = np.where(_flick2, 1.0 - _st2, _st2)
        _h5b = os.path.join(tmpdir, "psdtest_data.h5")
        with h5py.File(_h5b, "w") as f:
            f.create_dataset("I", data=_obs2)
            f.create_dataset("Q", data=np.zeros(_n2))
            f.create_dataset("t_us", data=np.arange(_n2) * _sp2)
            f.create_dataset("gap_indices", data=np.array([], dtype=int))
            f.attrs["sample_period_us"] = _sp2
            f.attrs["mode"] = "strobe"
        _res = analyze_parity_run(_h5b, separator=_sep_psd, window_us=4000.0,
                                  classifier_method="apriori_axis",
                                  save_plots=False, out_dir=tmpdir,
                                  merge_short_segments=False)
        assert _res["psd_is_lorentzian"], _res["psd_verdict"]
        _psd_rate = _res["psd_transitions_per_s_symmetric"]
        _counted = _res["baseline_rate_Hz"]
        assert abs(_psd_rate - _true_trans_per_s) / _true_trans_per_s < 0.2, (
            f"PSD rate {_psd_rate:.1f}/s vs true {_true_trans_per_s:.1f}/s")
        assert _counted > 2.0 * _psd_rate, (
            f"test setup: counted rate {_counted:.1f}/s should be inflated by "
            f"the injected flicker, PSD says {_psd_rate:.1f}/s")
        assert _res["counted_over_psd_rate"] > 2.0, _res["counted_over_psd_rate"]
        # Spectrum is persisted for re-examination without re-projecting.
        with h5py.File(os.path.join(tmpdir, "psdtest_data_analysis.h5"), "r") as f:
            assert f["psd_f_hz"].size > 0 and f["psd"].size == f["psd_f_hz"].size
            assert f["psd_binned"].size == f["psd_f_hz_binned"].size > 0
            assert f.attrs["psd_f_c_hz"] > 0
        with open(os.path.join(tmpdir, "psdtest_data_analysis.json")) as f:
            _side = json.load(f)
        assert "psd_verdict" in _side and "psd_gamma_total_hz" in _side

        # The bin sweep is opt-in and, when asked for, reports its own CV.
        _res_sw = analyze_parity_run(_h5b, separator=_sep_psd, window_us=4000.0,
                                     save_plots=True, out_dir=tmpdir,
                                     psd_bin_list_us=(0, 40, 100))
        assert "psd_f_c_cv_vs_bin" in _res_sw, _res_sw.keys()
        assert _res_sw["psd_n_bins_used_for_cv"] >= 2, _res_sw
        assert _res_sw["psd_f_c_cv_vs_bin"] < 0.2, _res_sw["psd_f_c_cv_vs_bin"]
        assert os.path.exists(os.path.join(tmpdir, "psdtest_data_psd.png"))

        # psd_rate_from_h5 works with NO separator at all (principal axis).
        _r_h5 = psd_rate_from_h5(_h5b, separator=None, bin_list_us=(0, 40, 100),
                                 out_dir=tmpdir, verbose=False)
        assert _r_h5["is_lorentzian"], _r_h5["verdict"]
        assert abs(_r_h5["transitions_per_s_symmetric"] - _true_trans_per_s) / \
               _true_trans_per_s < 0.2, _r_h5["transitions_per_s_symmetric"]
        assert _r_h5["projection_axis"] == "pca"
        assert os.path.exists(os.path.join(tmpdir, "psdtest_data_psd.json"))
    print(f"PSD rate survives 8% flicker that inflates the counted rate "
          f"({_psd_rate:.0f}/s vs counted {_counted:.0f}/s, true "
          f"{_true_trans_per_s:.0f}/s): OK")
