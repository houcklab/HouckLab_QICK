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

import numpy as np

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
        the smaller I-coordinate centroid (deterministic remap).

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

        # Remap so label 0 = cluster with the smaller I-coordinate centroid.
        # This gives a stable, deterministic correspondence between cluster
        # index and (g, e) regardless of KMeans' arbitrary internal ordering.
        if centers[0, 0] <= centers[1, 0]:
            g_idx, e_idx = 0, 1
        else:
            g_idx, e_idx = 1, 0
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


def dwell_time_statistics(binary_states, t_us, gap_indices=None):
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
    breakpoints = sorted(set([0, n] + list(gap_indices or [])))
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

    # Deterministic remap: label 0 should be the lower-I cluster.
    label0_mean_I = np.mean(np.asarray(I)[out_km["binary_states"] == 0])
    label1_mean_I = np.mean(np.asarray(I)[out_km["binary_states"] == 1])
    assert label0_mean_I < label1_mean_I, "kmeans label remap not deterministic"

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

    print("dwell_time_statistics: OK")
