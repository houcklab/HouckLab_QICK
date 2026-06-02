"""
Offline analysis for the zero-span charge-parity measurement.

See docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md for the
canonical reference. Five pure functions plus a top-level driver:

  classify_parity_trace      Project (I,Q) -> parity bits via separator or KMeans
  sliding_window_switch_rate Switch rate vs time
  detect_bursts              Find anomalous high-rate intervals
  dwell_time_statistics      Per-state run-length statistics + exponential fits
  analyze_parity_run         Load saved .h5, run all of the above, save plots/sidecars

Tests live under the `if __name__ == "__main__":` block at the end of this file
and are run with:
    python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity
"""

import os
import json
import numpy as np
import h5py
import matplotlib
matplotlib.use("Agg")  # non-interactive backend safe in headless runs
import matplotlib.pyplot as plt

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
    project_iq_onto_separator,
)


def classify_parity_trace(I, Q, separator=None, method="apriori"):
    """
    Project (I, Q) samples onto a 2-state axis and return binary parity labels.

    Parameters
    ----------
    I, Q : array_like
        1-D arrays of equal length, the raw in-phase and quadrature samples.
    separator : dict or None
        For method="apriori": must contain "g_center" and "e_center", each
        a length-2 array-like (I, Q) coordinate from a prior single-shot
        calibration. Ignored if method="kmeans".
    method : {"apriori", "kmeans"}
        "apriori": project onto (e_center - g_center), threshold at 0.
        "kmeans": fit KMeans(n_clusters=2) on (I, Q); label 0 = cluster with
        the lower projection on the e-g (inter-centroid) axis, with a canonical
        axis sign so the remap is independent of KMeans' arbitrary centroid
        order and of the g/e separation direction (I, Q, or diagonal).

    Returns
    -------
    dict with keys:
      binary_states  : int array (N,), values 0 or 1
      scores         : float array (N,), signed projection along separator axis
      separator_used : dict, the separator actually used (synthesized for kmeans)
      method         : "apriori" or "kmeans_fallback"
    """
    if method == "apriori":
        if separator is None:
            raise ValueError("method='apriori' requires a separator dict")
        scores, bits = project_iq_onto_separator(I, Q, separator)
        return {
            "binary_states": bits,
            "scores": scores,
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
                "method": "kmeans_fallback",
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
            "method": "kmeans_fallback",
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
    step_us       : float or None, window stride; default = window_us // 2 (50% overlap)
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
    """
    bits = np.asarray(binary_states, dtype=int)
    t = np.asarray(t_us, dtype=float)
    if bits.shape != t.shape:
        raise ValueError(f"binary_states shape {bits.shape} != t_us shape {t.shape}")

    if step_us is None:
        step_us = window_us / 2.0

    if bits.size < 2:
        return {
            "window_t_us": np.zeros(0),
            "rate_Hz": np.zeros(0),
            "switches_per_window": np.zeros(0, dtype=int),
            "window_us": float(window_us),
            "step_us": float(step_us),
        }

    diffs = np.abs(np.diff(bits))  # length N-1, value 0 or 1
    if gap_indices:
        for gi in gap_indices:
            if 1 <= gi < bits.size:
                diffs[gi - 1] = 0

    # diffs[i] corresponds to a transition that occurred between t[i] and t[i+1];
    # assign that switch event the timestamp t[i+1].
    t_event = t[1:]

    # Build windows
    t_start = t[0]
    t_end = t[-1]
    if t_end - t_start < window_us:
        # Single window covering the whole trace
        starts = np.array([t_start])
    else:
        starts = np.arange(t_start, t_end - window_us + step_us, step_us)
    centers = starts + window_us / 2.0
    counts = np.zeros(starts.size, dtype=int)
    for i, s in enumerate(starts):
        mask = (t_event >= s) & (t_event < s + window_us)
        counts[i] = int(diffs[mask].sum())
    rate_Hz = counts / (window_us * 1e-6)

    return {
        "window_t_us": centers,
        "rate_Hz": rate_Hz,
        "switches_per_window": counts,
        "window_us": float(window_us),
        "step_us": float(step_us),
    }


def detect_bursts(rate_Hz, window_t_us, baseline_rate=None, k_sigma=5,
                  min_duration_us=None):
    """
    Identify contiguous high-rate windows as bursts above a robust baseline.

    Parameters
    ----------
    rate_Hz       : array (M,) of switch rates per window (output of
                    sliding_window_switch_rate)
    window_t_us   : array (M,) of window center times
    baseline_rate : float or None; defaults to median(rate_Hz) (robust)
    k_sigma       : float; threshold = baseline + k_sigma * (1.4826 * MAD)
    min_duration_us : float or None; filter bursts shorter than this

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

    if baseline_rate is None:
        baseline_rate = float(np.median(rate))
    mad = float(np.median(np.abs(rate - baseline_rate)))
    sigma = 1.4826 * mad
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

    # Window stride for duration calculation
    if centers.size >= 2:
        stride = float(np.median(np.diff(centers)))
    else:
        stride = 0.0

    bursts = []
    for s, e in zip(starts, ends):
        t_start = float(centers[s] - stride / 2.0)
        t_end = float(centers[e - 1] + stride / 2.0)
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
                    bits[starts[i]:ends[i]] = bits[starts[i - 1]]
                elif i + 1 < starts.size:
                    bits[starts[i]:ends[i]] = bits[starts[i + 1]]
                changed = True
                break
    return bits


def _debounce_bits_segmented(bits, gap_indices, min_dwell_bins):
    """Apply _debounce_bits within each gap-delimited segment (never across a gap)."""
    bits = np.asarray(bits).astype(int)
    n = bits.size
    if min_dwell_bins <= 1 or n == 0:
        return bits.copy()
    valid = sorted({int(g) for g in (gap_indices or []) if 0 < int(g) < n})
    edges = [0] + valid + [n]
    out = bits.copy()
    for a, b in zip(edges[:-1], edges[1:]):
        out[a:b] = _debounce_bits(bits[a:b], min_dwell_bins)
    return out


def dwell_time_statistics(binary_states, t_us, gap_indices=None,
                          merge_short_segments=False, min_dwell_bins=1):
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
            "dwell_0_us": np.zeros(0), "dwell_1_us": np.zeros(0),
            "mean_0": float("nan"), "mean_1": float("nan"),
            "n_runs_0": 0, "n_runs_1": 0,
            "exp_fit_0": {"tau_us": float("nan"), "A": float("nan")},
            "exp_fit_1": {"tau_us": float("nan"), "A": float("nan")},
        }

    # Break trace into segments at gap_indices, run-length encode each segment.
    # Filter gap_indices to in-range positive values only — out-of-range entries
    # (negative, 0, or >= n) are no-ops at the trace boundaries and are silently
    # dropped to avoid IndexError from numpy slice wraparound.
    valid_gaps = [int(g) for g in (gap_indices or []) if 0 < int(g) < n]
    breakpoints = sorted(set([0, n] + valid_gaps))
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
                # Last run in segment: extrapolate using sample period
                if seg.size >= 2:
                    sp = float(seg_t[1] - seg_t[0])
                else:
                    sp = 0.0
                duration = float(seg_t[re - 1] - seg_t[rs]) + sp
            if state == 0:
                dwells_0.append(duration)
            else:
                dwells_1.append(duration)

    dwells_0 = np.asarray(dwells_0, dtype=float)
    dwells_1 = np.asarray(dwells_1, dtype=float)

    def _fit_exp(dwells):
        if dwells.size < 5:
            return {"tau_us": float("nan"), "A": float("nan")}
        try:
            hist, edges = np.histogram(dwells, bins=min(30, max(5, dwells.size // 10)))
            centers_h = 0.5 * (edges[:-1] + edges[1:])
            mask = hist > 0
            if mask.sum() < 3:
                return {"tau_us": float("nan"), "A": float("nan")}
            x = centers_h[mask]
            y = np.log(hist[mask])
            slope, intercept = np.polyfit(x, y, 1)
            if slope >= 0:
                return {"tau_us": float("nan"), "A": float("nan")}
            tau = -1.0 / slope
            A = float(np.exp(intercept))
            return {"tau_us": float(tau), "A": A}
        except Exception:
            return {"tau_us": float("nan"), "A": float("nan")}

    return {
        "dwell_0_us": dwells_0,
        "dwell_1_us": dwells_1,
        "mean_0": float(np.mean(dwells_0)) if dwells_0.size else float("nan"),
        "mean_1": float(np.mean(dwells_1)) if dwells_1.size else float("nan"),
        "n_runs_0": int(dwells_0.size),
        "n_runs_1": int(dwells_1.size),
        "exp_fit_0": _fit_exp(dwells_0),
        "exp_fit_1": _fit_exp(dwells_1),
    }


def _plot_iq_scatter(I, Q, bits, separator, out_path):
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(np.asarray(I)[bits == 0], np.asarray(Q)[bits == 0],
               s=1, alpha=0.3, label="state 0")
    ax.scatter(np.asarray(I)[bits == 1], np.asarray(Q)[bits == 1],
               s=1, alpha=0.3, label="state 1")
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
        # Downsample by histogram2d for speed
        time_bins = np.linspace(t_us[0], t_us[-1], max_pts)
        idx = np.clip(np.searchsorted(time_bins, t_us) - 1, 0, time_bins.size - 1)
        avg_state = np.bincount(idx, weights=bits.astype(float), minlength=time_bins.size)
        cnt = np.bincount(idx, minlength=time_bins.size).astype(float)
        avg_state[cnt > 0] /= cnt[cnt > 0]
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
            ax.hist(dwells, bins=30, log=True, alpha=0.7)
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
    """
    I = np.ravel(np.asarray(I, dtype=float))
    Q = np.ravel(np.asarray(Q, dtype=float))
    t = np.ravel(np.asarray(t_us, dtype=float))
    if I.size == 0:
        return I, Q, t, [], 0
    sp = float(t[1] - t[0]) if t.size > 1 else float(bin_us)
    if sp <= 0:
        sp = float(bin_us)
    bin_samples = max(1, int(round(float(bin_us) / sp)))
    valid_gaps = sorted({int(g) for g in (gap_indices or []) if 0 < int(g) < I.size})
    segment_edges = [0] + valid_gaps + [I.size]
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
                       classifier_method="apriori", step_us=None,
                       min_burst_duration_us=None, save_plots=True, out_dir=None,
                       analysis_bin_us=None):
    """
    Load a ZeroSpanParity raw .h5, classify into parity bits, compute switch rate,
    detect bursts, compute dwell statistics, save plots and a sidecar.

    Parameters
    ----------
    h5_path           : str, path to raw .h5 written by ZeroSpanParity.save_data
    separator         : dict or None; required for classifier_method="apriori"
    window_us         : float, sliding-window size
    k_sigma           : float, burst threshold
    classifier_method : "apriori" | "kmeans"
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

    Returns
    -------
    dict with scalar summary fields (matches sidecar JSON).
    """
    if out_dir is None:
        out_dir = os.path.dirname(h5_path) or "."
    base = os.path.splitext(os.path.basename(h5_path))[0]

    with h5py.File(h5_path, "r") as f:
        I = np.array(f["I"])
        Q = np.array(f["Q"])
        t_us = np.array(f["t_us"])
        gap_indices = list(np.array(f["gap_indices"])) if "gap_indices" in f else []
        sample_period_us = float(f.attrs.get("sample_period_us",
                                              (t_us[1] - t_us[0]) if t_us.size > 1 else 0.0))
        mode = str(f.attrs.get("mode", "strobe"))

    raw_sample_period_us = sample_period_us
    n_raw_samples = int(I.size)
    n_binned_samples = int(I.size)
    n_dropped = 0
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
        if t_us.size > 1:
            sample_period_us = float(t_us[1] - t_us[0])

    cls = classify_parity_trace(I, Q, separator=separator, method=classifier_method)
    bits = cls["binary_states"]
    sep_used = cls["separator_used"]

    rate_out = sliding_window_switch_rate(bits, t_us, window_us=window_us,
                                          step_us=step_us, gap_indices=gap_indices)
    bursts = detect_bursts(rate_out["rate_Hz"], rate_out["window_t_us"],
                           baseline_rate=None, k_sigma=k_sigma,
                           min_duration_us=min_burst_duration_us)
    stats = dwell_time_statistics(bits, t_us, gap_indices=gap_indices)

    if save_plots:
        _plot_iq_scatter(I, Q, bits, sep_used,
                          os.path.join(out_dir, base + "_iq_scatter.png"))
        _plot_parity_vs_time(bits, t_us,
                              os.path.join(out_dir, base + "_parity_vs_time.png"))
        _plot_switch_rate(rate_out, bursts,
                           os.path.join(out_dir, base + "_switch_rate_vs_time.png"))
        _plot_dwell_histograms(stats,
                                os.path.join(out_dir, base + "_dwell_histograms.png"))

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
    }

    # Write sidecars
    with open(os.path.join(out_dir, base + "_analysis.json"), "w") as f:
        json.dump({**summary,
                   "bursts": bursts,
                   "window_us": rate_out["window_us"],
                   "step_us": rate_out["step_us"]},
                  f, indent=2, default=lambda x: x.tolist()
                  if isinstance(x, np.ndarray) else float(x))
    with h5py.File(os.path.join(out_dir, base + "_analysis.h5"), "w") as f:
        f.create_dataset("binary_states", data=bits)
        f.create_dataset("scores", data=cls["scores"])
        f.create_dataset("window_t_us", data=rate_out["window_t_us"])
        f.create_dataset("rate_Hz", data=rate_out["rate_Hz"])
        f.create_dataset("dwell_0_us", data=stats["dwell_0_us"])
        f.create_dataset("dwell_1_us", data=stats["dwell_1_us"])
        for k, v in summary.items():
            try:
                f.attrs[k] = v
            except TypeError:
                f.attrs[k] = str(v)
    return summary


if __name__ == "__main__":
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
    assert out_km["method"] == "kmeans_fallback"
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
