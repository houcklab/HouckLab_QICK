"""
Offline analysis for the zero-span charge-parity measurement.

Sequential pipeline (orchestrated end-to-end by analyze_parity_run):

  classify_parity_trace      Project (I,Q) -> parity bits via separator or KMeans
  sliding_window_switch_rate Switch rate vs time
  detect_bursts              Find anomalous high-rate intervals
  dwell_time_statistics      Per-state run-length statistics + exponential fits
  analyze_parity_run         Load saved .h5, run all of the above, save plots/sidecars

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
import matplotlib
matplotlib.use("Agg")  # non-interactive backend safe in headless runs
import matplotlib.pyplot as plt

from qicklab.analysis.dwell import _gap_segment_edges, dwell_time_statistics
from qicklab.analysis.iq import project_iq_onto_separator


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
      method         : "apriori" or "kmeans" (echoes the requested method)
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
                "method": "kmeans",
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
        step_us = window_us // 2  # spec §3.2: 50% overlap, integer floor division

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
    last = starts.size - 1
    for i, s in enumerate(starts):
        # Half-open [s, s+window) so overlapping windows never double-count a
        # boundary event. The final window closes its right edge so a switch
        # landing exactly at t_end (possible when the record length is an exact
        # multiple of the window) is counted rather than silently dropped.
        if i == last:
            mask = (t_event >= s) & (t_event <= s + window_us)
        else:
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
        # Downsample to max_pts time bins (mean state per bin) so PNG generation
        # stays well under ~1 s even for multi-million-sample records.
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
    segment_edges = _gap_segment_edges(gap_indices, I.size)
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
                           min_duration_us=min_burst_duration_us,
                           window_us=rate_out["window_us"])
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
