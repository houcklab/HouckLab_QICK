"""Offline self-test of the zero-span parity analysis (moved from the legacy
analyze_ZeroSpanParity ``__main__`` block; same assertions, one test per block).

Blocks 1-3 and 5 of the legacy self-test shared one ``default_rng(1)`` stream; the
helpers below replay the earlier blocks' draws so each test sees the same data.
"""

import json
import os
import tempfile

import h5py
import numpy as np
import pytest

from qicklab.analysis.dwell import _fit_exp_dwell, dwell_time_statistics
from qicklab.analysis.zero_span import (
    _bin_iq_time,
    analyze_parity_run,
    classify_parity_trace,
    detect_bursts,
    sliding_window_switch_rate,
)
from qicklab.analysis.zero_span_checks import (
    bin_size_sweep,
    contrast_from_sweeps,
    projected_histogram_snr,
    threshold_stability,
    verify_modulation,
)

pytestmark = pytest.mark.slow


def _classify_clouds():
    """Legacy block 1 data; returns the shared default_rng(1) stream after its draws."""
    rng = np.random.default_rng(1)
    g_center = np.array([0.0, 0.0])
    e_center = np.array([10.0, 0.0])
    sep = {"g_center": g_center, "e_center": e_center}
    I_g = rng.normal(g_center[0], 0.5, 1000)
    Q_g = rng.normal(g_center[1], 0.5, 1000)
    I_e = rng.normal(e_center[0], 0.5, 1000)
    Q_e = rng.normal(e_center[1], 0.5, 1000)
    I = np.concatenate([I_g, I_e])
    Q = np.concatenate([Q_g, Q_e])
    labels_true = np.concatenate([np.zeros(1000, int), np.ones(1000, int)])
    return rng, sep, I, Q, labels_true


def _rng_after_kmeans_block():
    """The shared stream after blocks 1-2 (block 2 draws the Q-separated clouds)."""
    rng = _classify_clouds()[0]
    rng.normal(0.0, 0.5, 1000)
    rng.normal(0.0, 0.5, 1000)  # Ig_q, Qg_q
    rng.normal(0.0, 0.5, 1000)
    rng.normal(10.0, 0.5, 1000)  # Ie_q, Qe_q
    return rng


def _rng_after_sliding_block():
    """The shared stream after blocks 1-3 (block 3 draws the switch flips)."""
    rng = _rng_after_kmeans_block()
    rng.random(100_000)
    return rng


def test_classify_parity_trace_apriori():
    rng = np.random.default_rng(1)

    # --- classify_parity_trace apriori path -----------------------------------
    g_center = np.array([0.0, 0.0])
    e_center = np.array([10.0, 0.0])
    sep = {"g_center": g_center, "e_center": e_center}
    I_g = rng.normal(g_center[0], 0.5, 1000)
    Q_g = rng.normal(g_center[1], 0.5, 1000)
    I_e = rng.normal(e_center[0], 0.5, 1000)
    Q_e = rng.normal(e_center[1], 0.5, 1000)
    I = np.concatenate([I_g, I_e])
    Q = np.concatenate([Q_g, Q_e])
    labels_true = np.concatenate([np.zeros(1000, int), np.ones(1000, int)])

    out = classify_parity_trace(I, Q, separator=sep, method="apriori")
    assert "binary_states" in out and "scores" in out
    assert "method" in out and out["method"] == "apriori"
    assert "separator_used" in out
    accuracy = np.mean(out["binary_states"] == labels_true)
    assert accuracy > 0.99, f"apriori accuracy too low: {accuracy}"


def test_classify_parity_trace_kmeans():
    rng, sep, I, Q, labels_true = _classify_clouds()

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
    Ig_q = rng.normal(0.0, 0.5, 1000)
    Qg_q = rng.normal(0.0, 0.5, 1000)
    Ie_q = rng.normal(0.0, 0.5, 1000)
    Qe_q = rng.normal(10.0, 0.5, 1000)
    I_q = np.concatenate([Ig_q, Ie_q])
    Q_q = np.concatenate([Qg_q, Qe_q])
    out_q = classify_parity_trace(I_q, Q_q, separator=None, method="kmeans")
    label0_mean_Q = np.mean(np.asarray(Q_q)[out_q["binary_states"] == 0])
    label1_mean_Q = np.mean(np.asarray(Q_q)[out_q["binary_states"] == 1])
    assert label0_mean_Q < label1_mean_Q, (
        "kmeans remap not orientation-independent for Q-separated clouds"
    )


def test_sliding_window_switch_rate():
    rng = _rng_after_kmeans_block()

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
    out_gap = sliding_window_switch_rate(bits2, t2, window_us=60.0, step_us=60.0, gap_indices=[4])
    assert out_gap["switches_per_window"][0] == 1, (
        f"expected 1 switch with gap, got {out_gap['switches_per_window']}"
    )

    # Default step is window_us // 2 (integer floor, spec §3.2/§3.5).
    out_step = sliding_window_switch_rate(
        np.array([0, 1, 0, 1]), np.array([0.0, 1.0, 2.0, 3.0]), window_us=1001.0
    )
    assert out_step["step_us"] == 500.0, (
        f"default step_us={out_step['step_us']} (expected 500.0 = 1001 // 2)"
    )

    # A switch landing exactly at t_end (record length an exact multiple of the
    # window) must be counted by the closed final window, not dropped.
    out_edge = sliding_window_switch_rate(
        np.array([0, 0, 0, 1]), np.array([0.0, 30.0, 60.0, 90.0]), window_us=30.0, step_us=30.0
    )
    assert int(out_edge["switches_per_window"].sum()) == 1, (
        f"boundary switch dropped: {out_edge['switches_per_window']}"
    )


def test_detect_bursts():
    # --- detect_bursts --------------------------------------------------------
    # Baseline rate ~50 Hz over 100 windows; inject one window with 10 kHz.
    rate = np.full(100, 50.0)
    rate[50] = 10_000.0
    centers = np.arange(100) * 100_000.0  # 100 ms per window in us

    bursts = detect_bursts(rate, centers, baseline_rate=None, k_sigma=5, min_duration_us=None)
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
    q_rate = 1.0 / (win_us * 1e-6)  # one switch per window, in Hz
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
    b_mc = detect_bursts(rate_mc, cen_mc, baseline_rate=0.0, k_sigma=5, window_us=win_us)
    assert b_mc and abs(b_mc[0]["threshold_Hz"] - 5000.0) < 1.0, (
        f"MAD not centered on median: threshold {b_mc[0]['threshold_Hz'] if b_mc else None}"
    )


def test_dwell_time_statistics():
    rng = _rng_after_sliding_block()

    # --- dwell_time_statistics ------------------------------------------------
    # Generate a Markov-style binary trace with known mean dwell times
    # tau_0 = 200 samples, tau_1 = 400 samples, at 20 us/sample.
    n = 200_000
    p01 = 1.0 / 200.0  # prob 0 -> 1 per sample
    p10 = 1.0 / 400.0  # prob 1 -> 0 per sample
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
    s_single = dwell_time_statistics(
        np.array([0, 0, 1]), np.array([0.0, 10.0, 20.0]), gap_indices=[2]
    )
    assert abs(s_single["mean_1"] - 10.0) < 1e-9, (
        f"single-sample dwell = {s_single['mean_1']} (expected ~10 us)"
    )

    # Exponential dwell-time fit is unbiased within +/-5% (spec §6 validation),
    # via sqrt(count) Poisson weighting in log space.
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


def test_dwell_time_statistics_debounce():
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
    assert mean_nodb < 0.5 * mean_clean, (
        f"expected flickers to bias mean low, got {mean_nodb} vs {mean_clean}"
    )
    assert abs(mean_db - mean_clean) / mean_clean < 0.30, (
        f"debounced mean {mean_db} far from clean {mean_clean}"
    )
    # Debounce must respect gaps: a gap index must never merge across the boundary
    g = [clean.size // 2]
    _ = dwell_time_statistics(noisy, t, gap_indices=g, merge_short_segments=True, min_dwell_bins=2)


def test_analyze_parity_run_end_to_end():
    # --- analyze_parity_run end-to-end ----------------------------------------

    with tempfile.TemporaryDirectory() as tmpdir:
        # Build a synthetic raw .h5 mimicking what ZeroSpanParity.save_data writes.
        n_syn = 50_000
        sample_period_us_syn = 20.0
        rng_syn = np.random.default_rng(7)
        # Two IQ clouds, parity-modulated
        labels_syn = (np.cumsum(rng_syn.random(n_syn) < 0.005) % 2).astype(int)
        I_syn = np.where(
            labels_syn == 1, rng_syn.normal(10.0, 0.5, n_syn), rng_syn.normal(0.0, 0.5, n_syn)
        )
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

        sep_syn = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([10.0, 0.0])}
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
        for suffix in [
            "_iq_scatter.png",
            "_parity_vs_time.png",
            "_switch_rate_vs_time.png",
            "_dwell_histograms.png",
        ]:
            png = os.path.join(tmpdir, base + suffix)
            assert os.path.exists(png), f"missing plot: {png}"

        sidecar_json = os.path.join(tmpdir, base + "_analysis.json")
        sidecar_h5 = os.path.join(tmpdir, base + "_analysis.h5")
        assert os.path.exists(sidecar_json)
        assert os.path.exists(sidecar_h5)
        with open(sidecar_json) as f:
            sj = json.load(f)
        assert "baseline_rate_Hz" in sj


def test_markov_dwell_at_two_cadences():
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
            if st == 0 and rng_.random() < p01:
                st = 1
            elif st == 1 and rng_.random() < p10:
                st = 0
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
            f"sample_us={sample_us}: mean_0={st['mean_0']:.1f} vs 2000"
        )
        assert abs(st["mean_1"] - 4000.0) / 4000.0 < 0.2, (
            f"sample_us={sample_us}: mean_1={st['mean_1']:.1f} vs 4000"
        )


def test_bin_iq_time():
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


def test_analyze_parity_run_decimated_explicit_bin():
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

        sep_dec = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([10.0, 0.0])}
        # Caller-supplied analysis_bin_us recovers parity bits at >95% accuracy.
        res_dec = analyze_parity_run(
            h5_path=h5_dec,
            separator=sep_dec,
            window_us=100.0,
            k_sigma=5.0,
            save_plots=False,
            out_dir=tmpdir,
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
        assert bits_out.size == n_bins, f"expected {n_bins} binned bits, got {bits_out.size}"
        acc = np.mean(bits_out == labels_bins)
        assert acc > 0.95, f"decimated bin accuracy too low: {acc}"


def test_strobe_vs_decimated_equivalence():
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
            0, 0.3 * np.sqrt(raw_per_period), n_raw
        )
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

        sep_eq = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([10.0, 0.0])}
        analyze_parity_run(
            h5_path=h5_strobe, separator=sep_eq, window_us=100.0, save_plots=False, out_dir=tmpdir
        )
        # Caller asks for explicit binning at sample_period_us_eq to match the
        # strobe cadence; without it, raw decimated noise dominates per sample.
        analyze_parity_run(
            h5_path=h5_dec,
            separator=sep_eq,
            window_us=100.0,
            save_plots=False,
            out_dir=tmpdir,
            analysis_bin_us=sample_period_us_eq,
        )
        with h5py.File(os.path.join(tmpdir, "eq_strobe_analysis.h5"), "r") as f:
            bits_s = np.array(f["binary_states"])
        with h5py.File(os.path.join(tmpdir, "eq_dec_analysis.h5"), "r") as f:
            bits_d = np.array(f["binary_states"])
        assert bits_s.size == bits_d.size == n_samples, (
            f"strobe vs dec lengths differ: {bits_s.size} vs {bits_d.size} vs {n_samples}"
        )
        agreement = float(np.mean(bits_s == bits_d))
        assert agreement > 0.95, f"strobe-vs-decimated agreement too low: {agreement}"


def test_analyze_parity_run_preserves_rate_provenance():
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

        sep_meta = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([10.0, 0.0])}
        bin_us_meta = 32 * sp_attr  # bin 32 raw samples together
        summary = analyze_parity_run(
            h5_path=h5_t,
            separator=sep_meta,
            window_us=10.0,
            save_plots=False,
            out_dir=tmpdir,
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
        for k in (
            "raw_sample_period_us",
            "n_raw_samples",
            "n_binned_samples",
            "analysis_bin_us",
            "mode",
        ):
            assert k in sj, f"sidecar missing {k}: {sj.keys()}"


def test_verify_modulation():
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


def test_contrast_from_sweeps():
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


def test_projected_histogram_snr():
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


def test_bin_size_sweep():
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
    I = centers[bits, 0] + rng.normal(0, 3.0, n)  # noisy: small bins won't separate
    Q = centers[bits, 1] + rng.normal(0, 3.0, n)
    t = np.arange(n) * sp_raw
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([4.0, 0.0])}
    res = bin_size_sweep(I, Q, t, sep, bin_list_us=[100, 200, 500, 1000])
    assert np.isfinite(res["best_bin_us"]), res
    snr = np.array(res["separation_snr_per_bin"], dtype=float)
    assert snr[-1] >= snr[0], f"separation should not be worse at large bins: {snr}"


def test_threshold_stability():
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
