"""Offline self-test of the zero-span parity analysis (moved from the legacy
analyze_ZeroSpanParity ``__main__`` block; same assertions, one test per block).

Blocks 1-3 and 5 of the legacy self-test shared one ``default_rng(1)`` stream; the
helpers below replay the earlier blocks' draws so each test sees the same data.
"""

import json
import os
import tempfile
import warnings

import h5py
import numpy as np
import pytest

from qicklab.analysis.dwell import _fit_exp_dwell, dwell_time_statistics
from qicklab.analysis.rates import simulate_telegraph_trace
from qicklab.analysis.zero_span import (
    _bin_iq_time,
    analyze_parity_run,
    baseline_rate_and_bursts,
    classify_parity_trace,
    detect_bursts,
    event_switch_rate,
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

    # --- classify_parity_trace apriori_midpoint path --------------------------
    # SingleShot-like clouds at g and e, where the g/e midpoint is the right threshold
    # (it is not for zero-span data: see test_apriori_gmm_* below).
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

    out = classify_parity_trace(I, Q, separator=sep, method="apriori_midpoint")
    assert "binary_states" in out and "scores" in out
    assert "method" in out and out["method"] == "apriori_midpoint"
    assert "separator_used" in out
    assert out["threshold"] == 0.0 and out["warning"] is None
    accuracy = np.mean(out["binary_states"] == labels_true)
    assert accuracy > 0.99, f"apriori accuracy too low: {accuracy}"
    # the legacy name "apriori" is the GMM-threshold method; same projection, same bits here
    out_alias = classify_parity_trace(I, Q, separator=sep, method="apriori")
    assert out_alias["method"] == "apriori_gmm"
    np.testing.assert_array_equal(out_alias["scores"], out["scores"])
    assert np.mean(out_alias["binary_states"] == labels_true) > 0.99


def _driven_parity_trace(pe, sigma, n=100_000, gamma_hz=(500.0, 500.0), sp_us=20.0, seed=1):
    """Zero-span trace under a CW parity drive: the undriven parity sits at g, the driven
    one at g + pe * (e - g) (pe <= 1/2 for a driven two-level qubit), |e - g| = 1."""
    tr = simulate_telegraph_trace(n, sp_us * 1e-6, *gamma_hz, 0.0, pe, sigma, sigma, seed=seed)
    Q = sigma * np.random.default_rng(seed + 1).standard_normal(n)
    t_us = tr["t_s"] * 1e6
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([1.0, 0.0])}
    true_rate = event_switch_rate(tr["states"], t_us)["rate_Hz"]
    return tr["v"], Q, t_us, tr["states"], sep, true_rate


@pytest.mark.parametrize(
    "pe, sigma, gamma_hz, min_acc, max_rate_factor",
    [
        (0.5, 0.1, (500.0, 500.0), 0.99, 2.5),  # 5-sigma split: 0.6 % per-sample errors
        (0.35, 0.05, (500.0, 500.0), 0.99, 1.25),
        (0.35, 0.05, (300.0, 700.0), 0.99, 1.25),  # unequal occupations
        # 3.5-sigma split: threshold right, accuracy SNR-limited, but the per-sample switch
        # rate is ~8.5x the truth from noise crossings (no threshold avoids that):
        # test_apriori_gmm_rate_needs_snr_or_binning pins it and the binning remedy
        (0.35, 0.1, (500.0, 500.0), 0.95, None),
    ],
)
def test_apriori_gmm_tracks_parity_at_driven_level(pe, sigma, gamma_hz, min_acc, max_rate_factor):
    # F07: the driven parity level sits at g + pe (e - g), at or below the g/e midpoint, so
    # a midpoint threshold follows the qubit noise; the GMM threshold sits between the
    # two parity levels seen in the data.
    I, Q, t_us, states, sep, true_rate = _driven_parity_trace(pe, sigma, gamma_hz=gamma_hz)
    out = classify_parity_trace(I, Q, separator=sep)  # default method
    assert out["method"] == "apriori_gmm" and out["warning"] is None
    assert out["histogram_fit"]["is_bimodal"]
    # scores are the unchanged midpoint projection: g at -0.5, the driven level at pe - 0.5
    assert -0.5 < out["threshold"] < pe - 0.5
    acc = np.mean(out["binary_states"] == states)
    assert acc > min_acc, acc
    mid = classify_parity_trace(I, Q, separator=sep, method="apriori_midpoint")
    np.testing.assert_array_equal(mid["scores"], out["scores"])
    assert np.mean(mid["binary_states"] == states) < 0.8  # the old default
    if max_rate_factor is not None:
        rate = sliding_window_switch_rate(out["binary_states"], t_us, 1000.0)["rate_Hz"].mean()
        assert true_rate / max_rate_factor < rate < true_rate * max_rate_factor, (rate, true_rate)
        if pe == 0.5:
            rate_mid = sliding_window_switch_rate(mid["binary_states"], t_us, 1000.0)
            assert rate_mid["rate_Hz"].mean() > 10 * true_rate  # the bug: ~25x


def _write_zsp_h5(path, I, Q, t_us, sample_period_us=20.0):
    with h5py.File(path, "w") as f:
        f.create_dataset("I", data=I)
        f.create_dataset("Q", data=Q)
        f.create_dataset("t_us", data=t_us)
        f.create_dataset("gap_indices", data=np.array([], dtype=int))
        f.attrs["sample_period_us"] = sample_period_us
        f.attrs["mode"] = "strobe"


def test_apriori_gmm_rate_needs_snr_or_binning(tmp_path):
    # F07 review: at p_e = 0.35, sigma = 0.1 (parity levels 3.5 sigma apart) the GMM
    # threshold is in the right place (96 % accuracy), yet every noise crossing of it
    # counts as two switches, so the unbinned rate is several times the truth. Mean-binning
    # 4 samples (80 us, 7 sigma, still << the 2 ms dwells) removes the crossings.
    I, Q, t_us, _, sep, true_rate = _driven_parity_trace(0.35, 0.1)
    h5_path = os.path.join(str(tmp_path), "ZeroSpanParity_lowsnr.h5")
    _write_zsp_h5(h5_path, I, Q, t_us)
    kw = dict(separator=sep, window_us=1000.0, save_plots=False, out_dir=str(tmp_path))
    raw = analyze_parity_run(h5_path, **kw)
    assert not raw["bits_withheld"]
    assert raw["baseline_rate_Hz"] > 4 * true_rate, (raw["baseline_rate_Hz"], true_rate)
    # the summary carries the documented trust criterion (separation_snr >~ 5 per sample)
    assert 3.0 < raw["classifier_separation_snr"] < 4.0, raw["classifier_separation_snr"]
    binned = analyze_parity_run(h5_path, analysis_bin_us=80.0, **kw)
    assert not binned["bits_withheld"]
    assert true_rate / 1.25 < binned["baseline_rate_Hz"] < 1.25 * true_rate, (
        binned["baseline_rate_Hz"],
        true_rate,
    )
    assert binned["classifier_separation_snr"] > 5.0, binned["classifier_separation_snr"]
    # GMM centers in score units: g at -0.5, the driven level at pe - 0.5 = -0.15, both
    # below the g/e midpoint (0), so no resolved-jump signature
    c = binned["classifier_centers"]
    assert c[0] == pytest.approx(-0.5, abs=0.02) and c[1] == pytest.approx(-0.15, abs=0.02), c
    assert binned["classifier_threshold"] == pytest.approx(-0.325, abs=0.03)
    assert len(binned["classifier_sigmas"]) == 2 and len(binned["classifier_weights"]) == 2
    assert binned["classifier_delta_bic"] > 0
    base = os.path.join(str(tmp_path), "ZeroSpanParity_lowsnr")
    with open(base + "_analysis.json") as f:
        sj = json.load(f)
    assert sj["classifier_centers"] == pytest.approx(c)
    assert sj["classifier_separation_snr"] == pytest.approx(binned["classifier_separation_snr"])
    # F46: the record of this analysis run (code version, host, time)
    assert sj["provenance"]["end_time"] and "qick_version" in sj["provenance"]
    with h5py.File(base + "_analysis.h5", "r") as f:
        np.testing.assert_allclose(f.attrs["classifier_centers"], c)
        assert f.attrs["classifier_separation_snr"] == pytest.approx(
            binned["classifier_separation_snr"]
        )


def test_apriori_gmm_resolved_jump_signature_in_summary(tmp_path):
    # F07 review: when the qubit jumps are resolved within a sample, the driven parity sits
    # at g or at e (here at e with probability 0.4), the histogram has two clean lobes at
    # the SingleShot g and e, it passes the gate and the bits follow the qubit. The summary
    # must expose the documented signature: the upper GMM center at the e score (+0.5),
    # i.e. at or above the g/e midpoint (0).
    n, sigma = 100_000, 0.1
    tr = simulate_telegraph_trace(n, 20e-6, 500.0, 500.0, 0.0, 0.0, sigma, sigma, seed=3)
    rng = np.random.default_rng(4)
    I = tr["v"] + (tr["states"] == 1) * (rng.random(n) < 0.4)
    Q = sigma * rng.standard_normal(n)
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([1.0, 0.0])}
    h5_path = os.path.join(str(tmp_path), "ZeroSpanParity_jumps.h5")
    _write_zsp_h5(h5_path, I, Q, tr["t_s"] * 1e6)
    res = analyze_parity_run(h5_path, separator=sep, window_us=1000.0, save_plots=False)
    assert not res["bits_withheld"] and res["classifier_warning"] == ""  # the gate passes
    c = res["classifier_centers"]
    assert c[0] == pytest.approx(-0.5, abs=0.02) and c[1] == pytest.approx(0.5, abs=0.02), c
    assert c[1] >= 0.0 and res["classifier_separation_snr"] > 5.0
    # the methods without a histogram fit report NaN for these fields
    mid = analyze_parity_run(
        h5_path,
        separator=sep,
        window_us=1000.0,
        save_plots=False,
        classifier_method="apriori_midpoint",
    )
    assert np.isnan(mid["classifier_separation_snr"]) and np.isnan(mid["classifier_delta_bic"])
    assert all(np.isnan(mid[k]).all() for k in ("classifier_centers", "classifier_weights"))


def test_apriori_gmm_withholds_bits_when_not_bimodal(tmp_path):
    # pe = 0.1 at sigma 0.1: the parity levels are 1 sigma apart, the histogram fails the
    # bimodality gate, so no bits, and analyze_parity_run writes NaN instead of a rate
    I, Q, t_us, _, sep, _ = _driven_parity_trace(0.1, 0.1, n=20_000)
    out = classify_parity_trace(I, Q, separator=sep)
    assert out["binary_states"] is None
    assert not out["histogram_fit"]["is_bimodal"]
    assert "withheld" in out["warning"]

    h5_path = os.path.join(str(tmp_path), "ZeroSpanParity_unresolved.h5")
    _write_zsp_h5(h5_path, I, Q, t_us)
    res = analyze_parity_run(h5_path, separator=sep, window_us=1000.0, out_dir=str(tmp_path))
    assert res["bits_withheld"] is True and "withheld" in res["classifier_warning"]
    assert res["classifier_method"] == "apriori_gmm"
    assert res["n_samples"] == I.size
    for k in (
        "baseline_rate_Hz",
        "baseline_rate_err_Hz",
        "median_window_rate_Hz",
        "n_bursts",
        "mean_dwell_0_us",
        "mean_dwell_1_us",
        "exp_fit_tau_0_us",
        "exp_fit_tau_1_us",
        "tau_mle_0_us",
        "tau_mle_1_us",
        "tau_err_0_us",
        "tau_err_1_us",
        "n_exits_0",
        "n_exits_1",
        "n_interior_0",
        "n_interior_1",
    ):
        assert np.isnan(res[k]), (k, res[k])
    base = os.path.join(str(tmp_path), "ZeroSpanParity_unresolved")
    assert os.path.exists(base + "_iq_scatter.png")
    assert not os.path.exists(base + "_switch_rate_vs_time.png")
    with open(base + "_analysis.json") as f:
        sj = json.load(f)
    assert sj["bits_withheld"] is True and np.isnan(sj["baseline_rate_Hz"])
    # the fit that failed the gate is still reported (1-sigma split: separation SNR < 1.5
    # or a lopsided weight)
    assert np.isfinite(res["classifier_separation_snr"]) and len(res["classifier_centers"]) == 2
    assert sj["classifier_separation_snr"] == pytest.approx(res["classifier_separation_snr"])
    with h5py.File(base + "_analysis.h5", "r") as f:
        assert f["binary_states"].size == 0 and f["scores"].size == I.size


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


def _sliding_counts_loop(bits, t, window_us, step_us, gap_indices=None):
    """The pre-F75 per-window mask loop (test oracle for the switch counts)."""
    bits = np.asarray(bits, dtype=int)
    t = np.asarray(t, dtype=float)
    diffs = np.abs(np.diff(bits))
    for gi in gap_indices or ():
        if 1 <= gi < bits.size:
            diffs[gi - 1] = 0
    t_event = t[1:]
    if t[-1] - t[0] < window_us:
        starts = np.array([t[0]])
    else:
        starts = np.arange(t[0], t[-1] - window_us + step_us, step_us)
    counts = np.zeros(starts.size, dtype=int)
    for i, s in enumerate(starts):
        if i == starts.size - 1:
            mask = (t_event >= s) & (t_event <= s + window_us)
        else:
            mask = (t_event >= s) & (t_event < s + window_us)
        counts[i] = int(diffs[mask].sum())
    return starts, counts


@pytest.mark.parametrize(
    "n, dt_us, window_us, step_us",
    [
        (60_000, 20.0, 1000.0, 500.0),  # window edges land exactly on sample times
        (60_001, 20.0, 1000.0, 1000.0),  # record an exact multiple: switch at t_end
        (20_000, 7.3, 333.0, 111.0),  # incommensurate spacing, 2/3 overlap
        (5_000, 20.0, 1e6, None),  # record shorter than one window
    ],
)
def test_sliding_window_counts_match_loop(n, dt_us, window_us, step_us):
    # F75: the cumsum + searchsorted counts are bit-identical to the old mask loop
    # (same half-open windows, closed last window, gap zeroing) on a telegraph with gaps.
    rng = np.random.default_rng(n)
    bits = (np.cumsum(rng.random(n) < 0.02) % 2).astype(int)
    bits[-1] = 1 - bits[-2]  # a switch exactly at t_end
    t = np.arange(n) * dt_us
    gaps = [0, 1, 17, n // 3, n // 2, n - 1, n]  # incl. the guarded out-of-range ones
    out = sliding_window_switch_rate(bits, t, window_us, step_us=step_us, gap_indices=gaps)
    step = window_us // 2 if step_us is None else step_us
    starts, counts = _sliding_counts_loop(bits, t, window_us, step, gap_indices=gaps)
    assert out["switches_per_window"].dtype.kind == "i"
    assert np.array_equal(out["switches_per_window"], counts)
    assert np.array_equal(out["window_t_us"], starts + window_us / 2.0)
    # Full windows are still divided by window_us exactly; only the last can be partial.
    full = out["covered_us"] == window_us
    assert full[:-1].all()
    assert np.array_equal(out["rate_Hz"][full], counts[full] / (window_us * 1e-6))


def test_sliding_window_partial_last_window():
    # F75: t = 0..1020 us, W = 100, step 50 -> the last window [950, 1050) holds only the
    # samples 950..1020, i.e. 71 us of observed time; its rate is n/71 us, not n/100 us,
    # so a uniform 1 MHz switching trace reads 1 MHz there too (was 0.71 MHz).
    t = np.arange(0, 1021, dtype=float)
    bits = np.arange(t.size) % 2  # a switch on every sample interval
    out = sliding_window_switch_rate(bits, t, window_us=100.0, step_us=50.0)
    assert out["window_t_us"][-1] == 1000.0
    assert out["covered_us"][-1] == 71.0
    assert np.all(out["covered_us"][:-1] == 100.0)
    assert out["switches_per_window"][-1] == 71  # events (t[i+1]) at t = 950..1020
    assert out["rate_Hz"][-1] == pytest.approx(1e6)
    # 100 switches per full 100 us window (the first holds events at t = 1..99 only)
    assert out["switches_per_window"][0] == 99
    assert np.allclose(out["rate_Hz"][1:-1], 1e6)
    # A record shorter than one window is normalised to its own length (+ one sample).
    short = sliding_window_switch_rate(bits[:51], t[:51], window_us=100.0)
    assert short["covered_us"].tolist() == [51.0]
    assert short["rate_Hz"][0] == pytest.approx(50 / 51e-6)


def test_sliding_window_step_wider_than_window_drops_empty_tail():
    # F75 review: with step_us > window_us the last arange start (1200) lies past
    # t_end = 1100 and would get covered_us = -99 (rate -0.0, NaN burst threshold).
    # It holds no sample, so it is dropped; the kept windows match the old loop.
    t = np.arange(0, 1101, dtype=float)
    bits = np.arange(t.size) % 2
    out = sliding_window_switch_rate(bits, t, window_us=100.0, step_us=300.0)
    starts, counts = _sliding_counts_loop(bits, t, 100.0, 300.0)
    assert starts.tolist() == [0.0, 300.0, 600.0, 900.0, 1200.0]
    assert counts[-1] == 0
    assert np.array_equal(out["window_t_us"], starts[:-1] + 50.0)
    assert np.array_equal(out["switches_per_window"], counts[:-1])
    assert out["covered_us"].tolist() == [100.0] * 4
    assert np.all(out["rate_Hz"] >= 0)
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # the old -99 us window raised in sqrt
        base, bursts = baseline_rate_and_bursts(bits, t, out, k_sigma=3.0)
    assert np.isfinite(base["baseline_rate_Hz"])
    assert bursts == []


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

    # A caller-supplied, non-integer (event-based) baseline: the Poisson floor is
    # q*sqrt(max(baseline/q, 1)), so a sub-one-switch-per-window baseline keeps the
    # one-switch floor and a larger one scales as sqrt(counts) (F17).
    rate_nb = np.zeros(400)
    rate_nb[rng_b.random(400) < 0.3] = q_rate
    rate_nb[200] = 60 * q_rate
    for base, sig in [(400.0, q_rate), (2500.0, q_rate * np.sqrt(2.5))]:
        b_nb = detect_bursts(rate_nb, sparse_cen, baseline_rate=base, k_sigma=5, window_us=win_us)
        assert len(b_nb) == 1, f"baseline {base}: {len(b_nb)} bursts"
        assert b_nb[0]["baseline_rate_Hz"] == base
        assert abs(b_nb[0]["threshold_Hz"] - (base + 5 * sig)) < 1e-6, b_nb[0]["threshold_Hz"]


def _telegraph(rate_Hz, dt_us, n, seed, burst=None):
    """Binary telegraph sampled every dt_us: each interval switches with probability
    rate_Hz*dt (so the expected switch count is exactly rate_Hz * (n-1)*dt). `burst` =
    (i0, i1, p) raises the per-interval probability to p on intervals i0..i1-1."""
    rng = np.random.default_rng(seed)
    p = np.full(n - 1, rate_Hz * dt_us * 1e-6)
    if burst is not None:
        p[burst[0] : burst[1]] = burst[2]
    flips = rng.random(n - 1) < p
    bits = np.concatenate([[0], np.cumsum(flips) % 2]).astype(int)
    return bits, np.arange(n) * float(dt_us)


@pytest.mark.parametrize("true_rate", [95.0, 222.0, 452.0, 933.0])
def test_event_baseline_rate_recovers_telegraph(true_rate):
    # F17: the median of per-window counts is 0 Hz below ~0.7 switches per window and
    # quantised to 1/window above it; the event-based baseline n/T is unbiased, with a
    # sqrt(n)/T standard error (Gaussian approximation; n is in the hundreds here).
    bits, t = _telegraph(true_rate, 50.0, 40_001, seed=int(true_rate))  # 2 s record
    rate_out = sliding_window_switch_rate(bits, t, window_us=1000.0, step_us=500.0)
    base, _ = baseline_rate_and_bursts(bits, t, rate_out, k_sigma=5)
    err = base["baseline_rate_err_Hz"]
    assert abs(base["baseline_rate_Hz"] - true_rate) < 3 * err, (true_rate, base)
    assert err == pytest.approx(np.sqrt(base["n_switches_baseline"]) / base["T_baseline_s"])
    assert base["T_baseline_s"] <= 2.0
    if true_rate < 500:
        assert base["median_window_rate_Hz"] == 0.0  # the old estimator's failure


def test_event_baseline_excludes_bursts():
    # 400 Hz telegraph over 2 s with a 20 ms, ~10 kHz burst at t = 1 s. The provisional
    # (whole-record) rate is biased by the burst; one exclusion pass recovers 400 Hz.
    dt = 50.0
    i0, i1 = 20_000, 20_400
    bits, t = _telegraph(400.0, dt, 40_001, seed=3, burst=(i0, i1, 0.5))
    rate_out = sliding_window_switch_rate(bits, t, window_us=1000.0, step_us=500.0)
    whole = event_switch_rate(bits, t)
    base, bursts = baseline_rate_and_bursts(bits, t, rate_out, k_sigma=5)
    assert abs(whole["rate_Hz"] - 400.0) > 3 * whole["rate_err_Hz"]
    assert abs(base["baseline_rate_Hz"] - 400.0) < 3 * base["baseline_rate_err_Hz"], base
    assert bursts and all(b["t_end_us"] >= t[i0] and b["t_start_us"] <= t[i1] for b in bursts)
    assert all(b["baseline_rate_Hz"] == base["baseline_rate_Hz"] for b in bursts)
    excluded_s = whole["T_s"] - base["T_baseline_s"]
    assert 0.02 <= excluded_s < 0.1, excluded_s
    assert base["n_switches_baseline"] < whole["n_switches"]


@pytest.mark.parametrize("n_bursts, p_burst", [(200, 0.9), (100, 0.5)])
def test_event_baseline_masks_full_flagged_windows(n_bursts, p_burst):
    # Many 1 ms bursts (18 kHz / 10 kHz) on a 400 Hz quiet telegraph, 2 s at 50 us. A
    # burst is reported as centers[s] - stride/2 .. centers[e-1] + stride/2, but its
    # flagged windows reach window_us/2 past the end centres; masking only the reported
    # span leaks window_us/4 of burst edge per side into the baseline. The exclusion is
    # padded by (window_us - stride)/2, which recovers the quiet rate.
    dt, n, blen = 50.0, 40_001, 20
    rng = np.random.default_rng(0)
    p = np.full(n - 1, 400.0 * dt * 1e-6)
    quiet = np.ones(n - 1, dtype=bool)
    for s0 in rng.choice(np.arange(200, n - 1 - 200, 60), n_bursts, replace=False):
        p[s0 : s0 + blen] = p_burst
        quiet[s0 : s0 + blen] = False
    flips = rng.random(n - 1) < p
    bits = np.concatenate([[0], np.cumsum(flips) % 2]).astype(int)
    t = np.arange(n) * dt
    quiet_rate = flips[quiet].sum() / (quiet.sum() * dt * 1e-6)
    rate_out = sliding_window_switch_rate(bits, t, window_us=1000.0, step_us=500.0)
    base, _ = baseline_rate_and_bursts(bits, t, rate_out, k_sigma=5)
    err = base["baseline_rate_err_Hz"]
    assert abs(base["baseline_rate_Hz"] - 400.0) < 3 * err, base
    assert abs(base["baseline_rate_Hz"] - quiet_rate) < 3 * err, (quiet_rate, base)
    # The unpadded mask (the reported burst spans) is biased high by > 3 sigma here.
    flagged = detect_bursts(
        rate_out["rate_Hz"],
        rate_out["window_t_us"],
        baseline_rate=event_switch_rate(bits, t)["rate_Hz"],
        k_sigma=5,
        window_us=1000.0,
    )
    narrow = event_switch_rate(
        bits, t, exclude_us=[(b["t_start_us"], b["t_end_us"]) for b in flagged]
    )
    assert narrow["rate_Hz"] - 400.0 > 3 * narrow["rate_err_Hz"], narrow


def _tail_trace(n, tail_flips, seed=7, dt=10.0, rate_Hz=200.0):
    """200 Hz telegraph at 10 us/sample whose last len(tail_flips) intervals are set."""
    rng = np.random.default_rng(seed)
    flips = rng.random(n - 1) < rate_Hz * dt * 1e-6
    flips[-len(tail_flips) :] = tail_flips
    bits = np.concatenate([[0], np.cumsum(flips) % 2]).astype(int)
    return bits, np.arange(n) * dt


@pytest.mark.parametrize("step_us", [1000.0, 500.0])
def test_partial_tail_window_single_switch_is_not_a_burst(step_us):
    # F75: the record is 100 windows + 2 samples, so with step = window the last window
    # covers 30 us; one switch there reads 33 kHz. At the full-window Poisson floor
    # (q = 1 kHz) that is a 5-sigma burst, and it would then be cut from the baseline.
    # The partial window is held to its own floor (q_c = 1/30 us): no burst, baseline =
    # the whole-record event rate.
    bits, t = _tail_trace(10_003, [False, True, False])
    rate_out = sliding_window_switch_rate(bits, t, window_us=1000.0, step_us=step_us)
    cov = rate_out["covered_us"]
    assert cov[-1] == (30.0 if step_us == 1000.0 else 530.0) and np.all(cov[:-1] == 1000.0)
    assert rate_out["switches_per_window"][-1] == 1
    base, bursts = baseline_rate_and_bursts(bits, t, rate_out, k_sigma=5)
    assert bursts == []
    whole = event_switch_rate(bits, t)
    assert base["baseline_rate_Hz"] == whole["rate_Hz"]
    assert base["T_baseline_s"] == whole["T_s"]
    if step_us == 1000.0:
        # without covered_us (one floor for every window) the tail switch is flagged
        flagged = detect_bursts(
            rate_out["rate_Hz"],
            rate_out["window_t_us"],
            baseline_rate=whole["rate_Hz"],
            k_sigma=5,
            window_us=1000.0,
        )
        assert [b["t_start_us"] for b in flagged] == [100_000.0]


def test_partial_tail_window_real_burst_is_detected():
    # F75: a switch on every one of the last 29 intervals (a 97 kHz burst in a 300 us
    # tail window) still crosses the partial window's own threshold; its integrated
    # excess is the excess switches it holds, (rate - baseline) * covered_us.
    bits, t = _tail_trace(10_030, np.ones(29, dtype=bool))
    rate_out = sliding_window_switch_rate(bits, t, window_us=1000.0, step_us=1000.0)
    assert rate_out["covered_us"][-1] == 300.0
    base, bursts = baseline_rate_and_bursts(bits, t, rate_out, k_sigma=5)
    assert len(bursts) == 1
    (b,) = bursts
    assert (b["t_start_us"], b["t_end_us"]) == (100_000.0, 101_000.0)
    assert b["peak_rate_Hz"] == pytest.approx(29 / 300e-6)
    expected = 29 - base["baseline_rate_Hz"] * 300e-6
    assert b["integrated_excess_switches"] == pytest.approx(expected)
    # the tail's 29 switches are excluded from the baseline
    assert base["n_switches_baseline"] == event_switch_rate(bits, t)["n_switches"] - 29


def test_detect_bursts_covered_us_full_windows_unchanged():
    # F75: covered_us of only full windows gives the old detection exactly; covered_us
    # needs window_us (it sets the per-window quantum) and the rate's shape.
    rng = np.random.default_rng(11)
    rate = rng.poisson(0.4, 400) * 1000.0
    rate[200:204] = 20_000.0
    cen = np.arange(400) * 500.0 + 500.0
    ref = detect_bursts(rate, cen, baseline_rate=400.0, k_sigma=5, window_us=1000.0)
    got = detect_bursts(
        rate, cen, baseline_rate=400.0, k_sigma=5, window_us=1000.0, covered_us=np.full(400, 1e3)
    )
    assert ref and got == ref
    with pytest.raises(ValueError, match="requires window_us"):
        detect_bursts(rate, cen, covered_us=np.full(400, 1e3))
    with pytest.raises(ValueError, match="differ"):
        detect_bursts(rate, cen, window_us=1000.0, covered_us=np.full(399, 1e3))


def test_event_switch_rate_edge_cases():
    # Gap-aware: the switch across the gap and the 970 us gap interval are not counted;
    # T is the sum of the in-record intervals, not (N-1)*dt.
    bits = np.array([0, 0, 1, 1, 0, 0])
    t = np.array([0.0, 10.0, 20.0, 30.0, 1000.0, 1010.0])
    r = event_switch_rate(bits, t, gap_indices=[4])
    assert r["n_switches"] == 1 and r["T_s"] == pytest.approx(40e-6)
    assert r["rate_Hz"] == pytest.approx(25_000.0)
    assert r["rate_err_Hz"] == pytest.approx(25_000.0)
    # Zero events: rate 0, error 0 (the sqrt(n) approximation, as specified), T > 0.
    r0 = event_switch_rate(np.zeros(101, int), np.arange(101) * 10.0)
    assert r0["rate_Hz"] == 0.0 and r0["rate_err_Hz"] == 0.0 and r0["T_s"] == pytest.approx(1e-3)
    # Fewer than two samples, or everything excluded: no observed time -> nan, T = 0.
    for rn in (
        event_switch_rate(np.array([1]), np.array([0.0])),
        event_switch_rate(np.array([], int), np.array([])),
        event_switch_rate(bits, t, exclude_us=[(-1.0, 2000.0)]),
    ):
        assert np.isnan(rn["rate_Hz"]) and np.isnan(rn["rate_err_Hz"]) and rn["T_s"] == 0.0
    b_short, bursts_short = baseline_rate_and_bursts(
        np.array([1]), np.array([0.0]), sliding_window_switch_rate([1], [0.0], 1000.0)
    )
    assert np.isnan(b_short["baseline_rate_Hz"]) and bursts_short == []
    assert b_short["median_window_rate_Hz"] == 0.0
    # All-burst record: exclusion would leave T = 0, so the provisional (whole-record)
    # baseline is kept. 10 switches in 10 ms -> 1000 Hz; every window far above it.
    bits_ab = (np.arange(1001) // 95) % 2  # switches at samples 95, 190, ..., 950
    t_ab = np.arange(1001) * 10.0
    n_ab = 10
    fake = {
        "rate_Hz": np.full(21, 1e6),
        "window_t_us": np.arange(21) * 500.0,
        "window_us": 1000.0,
    }
    b_ab, bursts_ab = baseline_rate_and_bursts(bits_ab, t_ab, fake, k_sigma=5)
    assert len(bursts_ab) == 1
    assert b_ab["T_baseline_s"] == pytest.approx(0.01)
    assert b_ab["n_switches_baseline"] == n_ab
    assert b_ab["baseline_rate_Hz"] == pytest.approx(n_ab / 0.01)


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


def _sampled_exit_p(sp_us, tau_own_us, tau_other_us):
    """Per-sample exit probability of a continuous-time telegraph sampled every sp:
    P_s = (gamma_s/Gamma)(1 - exp(-Gamma sp)), Gamma = gamma_0 + gamma_1."""
    g_own, g_other = 1.0 / tau_own_us, 1.0 / tau_other_us
    gam = g_own + g_other
    return g_own / gam * -np.expm1(-gam * sp_us)


def _geometric_telegraph(rng, n_dwells, tau_us, sp_us):
    """Alternating 0/1 runs with the exact run-length law of a symmetric continuous-time
    telegraph (dwell tau) sampled every sp: Geometric(P), P = (1 - exp(-2 sp/tau))/2."""
    p = _sampled_exit_p(sp_us, tau_us, tau_us)
    lengths = rng.geometric(p, n_dwells)
    bits = np.repeat(np.arange(lengths.size) % 2, lengths)
    return bits, np.arange(bits.size) * sp_us


def test_dwell_mle_unbiased_at_small_n():
    # F73: at the 100-300 dwells of a stage-7 / threshold-stability record the
    # log-linear histogram fit reads tau ~15 % high; the dwell-time MLE is unbiased
    # to ~1 % and its tau_err matches the replicate scatter. The runs follow the exact
    # run-length law of a sampled symmetric telegraph.
    sp, tau = 20.0, 2000.0
    rng = np.random.default_rng(11)
    mle, err, hist, n_int, n_exits = [], [], [], [], []
    for _ in range(200):
        bits, t = _geometric_telegraph(rng, 2 * 150 + 2, tau, sp)
        st = dwell_time_statistics(bits, t)
        mle.append(st["tau_mle_0_us"])
        err.append(st["tau_err_0_us"])
        hist.append(st["exp_fit_0"]["tau_us"])
        n_int.append(st["n_interior_0"])
        n_exits.append(st["n_exits_0"])
    mle, err, hist = (np.asarray(x, dtype=float) for x in (mle, err, hist))
    assert set(n_int) == {150}  # 151 state-0 runs, the first one censored
    assert set(n_exits) == {151}  # ... but it still ends in a switch: 151 exits
    assert abs(np.mean(mle) / tau - 1) < 0.02, np.mean(mle)
    assert np.nanmean(hist) / tau - 1 > 0.08, np.nanmean(hist)  # the bias being replaced
    assert np.std(mle) < np.nanstd(hist)
    # delta-method error ~ tau/sqrt(N_exits), and it matches the scatter of the estimate
    assert np.mean(err) == pytest.approx(tau / np.sqrt(151), rel=0.05)
    assert np.mean(err) == pytest.approx(np.std(mle), rel=0.15)


def _symmetric_markov(rng, n, tau_us, sp_us):
    """A symmetric continuous-time telegraph (dwell tau) sampled n times every sp.

    Sampled, it is a Markov chain switching with P = (1 - exp(-2 sp/tau))/2 per step
    in either state, so the switch events are i.i.d. Bernoulli(P) and the chain is a
    cumsum.
    """
    p = _sampled_exit_p(sp_us, tau_us, tau_us)
    return (rng.integers(2) + np.cumsum(rng.random(n) < p)) % 2


def _ct_telegraph(rng, T_us, tau0_us, tau1_us, sp_us):
    """Event-driven continuous-time telegraph: exponential dwells (tau0 in 0, tau1 in 1),
    sampled every sp for T_us with a random sampling phase. Returns (bits, t_us)."""
    s0 = int(rng.integers(2))
    n_ev = int(3 * T_us / min(tau0_us, tau1_us)) + 50
    states = (s0 + np.arange(n_ev)) % 2
    edges = np.concatenate(([0.0], np.cumsum(rng.exponential(np.where(states, tau1_us, tau0_us)))))
    assert edges[-1] > T_us
    ts = rng.random() * sp_us + np.arange(int(T_us / sp_us)) * sp_us
    return states[np.searchsorted(edges, ts, side="right") - 1], ts - ts[0]


def _telegraph_tau(sp, p_own, p_other):
    """Independent inversion of the sampled-telegraph exit probabilities."""
    gam = -np.log(1.0 - p_own - p_other) / sp
    return (p_own + p_other) / (p_own * gam)


def _transition_counts(bits, gap_indices, k):
    """Brute-force (exits, trials) from state k: steps i -> i+1 within a segment."""
    edges = [0, *sorted(gap_indices), bits.size]
    exits = trials = 0
    for a, b in zip(edges[:-1], edges[1:]):
        for i in range(a, b - 1):
            if bits[i] == k:
                trials += 1
                exits += int(bits[i + 1] != k)
    return exits, trials


def test_dwell_mle_censoring_and_edge_cases():
    # Run lengths in samples with a censored flag for each segment's first/last run;
    # the MLE counts every within-segment step from a state as a trial and every
    # switch out of it as an exit, censored runs included.
    bits = np.array([0, 0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 1])
    t = np.arange(bits.size) * 10.0
    st = dwell_time_statistics(bits, t, gap_indices=[9])
    # segment [0, 9): 00 111 0000 ; segment [9, 14): 11 00 1
    np.testing.assert_array_equal(st["dwell_0_samples"], [2, 4, 2])
    np.testing.assert_array_equal(st["censored_0"], [True, True, False])
    np.testing.assert_array_equal(st["dwell_1_samples"], [3, 2, 1])
    np.testing.assert_array_equal(st["censored_1"], [False, True, True])
    assert st["n_interior_0"] == 1 and st["n_interior_1"] == 1
    assert st["n_exits_0"] == 2 and st["n_exits_1"] == 2  # a segment's last run has no exit
    assert st["sample_period_us"] == 10.0
    assert np.isnan(st["tau_mle_0_us"]) and np.isnan(st["tau_err_0_us"])  # < 5 exits

    # Exact value: P_s = exits/trials, tau_s from the two-state telegraph inversion,
    # against a brute-force count of the transitions, in one segment and split by a
    # gap; the error against a finite-difference delta method.
    runs = [7] + [2, 4, 3, 5, 6] * 4 + [9]  # alternating states, the last run in state 1
    bits2 = np.repeat(np.arange(len(runs)) % 2, runs)
    t2 = np.arange(bits2.size) * 20.0
    t3 = t2.copy()
    t3[1:] += 5.0  # irregular first step
    t3[60:] += 1000.0  # acquisition gap
    for tt, gaps in ((t2, []), (t3, [60])):
        st2 = dwell_time_statistics(bits2, tt, gap_indices=gaps)
        # The sample period is the median within-segment spacing, not t[1] - t[0]
        # and not the spacing across a gap.
        assert st2["sample_period_us"] == 20.0
        counts = [_transition_counts(bits2, gaps, k) for k in (0, 1)]
        P = [e / n for e, n in counts]
        for k in (0, 1):
            exits, trials = counts[k]
            assert st2[f"n_exits_{k}"] == exits
            assert st2[f"p_exit_{k}"] == pytest.approx(P[k], rel=1e-12)
            assert st2[f"tau_mle_{k}_us"] == pytest.approx(
                _telegraph_tau(20.0, P[k], P[1 - k]), rel=1e-12
            )
            var = 0.0
            for j in (0, 1):
                h = 1e-7
                dp = [0.0, 0.0]
                dp[j] = h
                d = (
                    _telegraph_tau(20.0, P[k] + dp[k], P[1 - k] + dp[1 - k])
                    - _telegraph_tau(20.0, P[k] - dp[k], P[1 - k] - dp[1 - k])
                ) / (2 * h)
                var += d**2 * P[j] * (1 - P[j]) / counts[j][1]
            assert st2[f"tau_err_{k}_us"] == pytest.approx(np.sqrt(var), rel=1e-5)
    # one segment: state 1 holds the last run (9 samples, 8 trials, no exit)
    assert _transition_counts(bits2, [], 1) == (10, sum(runs[1::2]) - 1)

    # Every run at the minimum length (P_0 + P_1 = 2 >= 1): tau not resolved (nan, not 0).
    flicker = np.arange(40) % 2
    st4 = dwell_time_statistics(flicker, np.arange(40) * 20.0)
    assert st4["n_exits_0"] == 20 and np.isnan(st4["tau_mle_0_us"])
    # Empty trace
    st5 = dwell_time_statistics(np.zeros(0), np.zeros(0))
    assert st5["n_interior_0"] == 0 and st5["n_exits_0"] == 0 and np.isnan(st5["tau_mle_1_us"])


def test_dwell_mle_short_segments():
    # A sampled Markov chain cut into gap segments only 5 tau long: the censored
    # likelihood stays unbiased, while the mean of the interior runs alone is biased
    # low by ~tau/T_segment (long dwells are the ones a segment cuts off).
    sp, tau = 20.0, 2000.0
    seg_len, n_seg = 500, 80  # 5 tau per segment
    gaps = list(range(seg_len, seg_len * n_seg, seg_len))
    rng = np.random.default_rng(21)
    mle, err, interior_only = [], [], []
    for _ in range(40):
        bits = _symmetric_markov(rng, seg_len * n_seg, tau, sp)
        t = np.arange(bits.size) * sp + np.repeat(np.arange(n_seg) * 5e4, seg_len)
        st = dwell_time_statistics(bits, t, gap_indices=gaps)
        assert st["sample_period_us"] == sp
        mle.append(st["tau_mle_0_us"])
        err.append(st["tau_err_0_us"])
        n_int = st["dwell_0_samples"][~st["censored_0"]]
        interior_only.append(sp * n_int.mean())
    assert abs(np.mean(mle) / tau - 1) < 0.02, np.mean(mle)
    assert np.mean(interior_only) / tau - 1 < -0.15, np.mean(interior_only)
    assert np.mean(err) == pytest.approx(np.std(mle), rel=0.25)


def test_dwell_mle_continuous_telegraph():
    # An event-driven continuous-time telegraph (exponential dwells, random sampling
    # phase), asymmetric, at sp/tau = 0.33 / 0.17 / 0.1: the MLE recovers the true
    # 1/gamma_s. The single-state inversion -sp/ln(1 - P_s) of the same exit
    # probability would read high by ~sp/(2 tau_other) (+8 % for tau0 = 60 us).
    rng = np.random.default_rng(31)
    sp = 20.0
    for tau0, tau1 in ((60.0, 120.0), (200.0, 400.0)):
        est = {0: [], 1: []}
        err = {0: [], 1: []}
        single = {0: [], 1: []}
        for _ in range(40):
            bits, t = _ct_telegraph(rng, 2000 * tau1, tau0, tau1, sp)
            st = dwell_time_statistics(bits, t)
            assert st["sample_period_us"] == pytest.approx(sp)
            for k in (0, 1):
                est[k].append(st[f"tau_mle_{k}_us"])
                err[k].append(st[f"tau_err_{k}_us"])
                single[k].append(-sp / np.log1p(-st[f"p_exit_{k}"]))
        for k, tau in ((0, tau0), (1, tau1)):
            m, e = np.mean(est[k]), np.mean(err[k])
            # mean of 40 replicates: its error is e/sqrt(40)
            assert abs(m - tau) < 4 * e / np.sqrt(40), (tau0, tau1, k, m, tau, e)
            assert e == pytest.approx(np.std(est[k]), rel=0.35)
            # the single-state inversion's model bias, -sp/ln(1 - P_s)/tau - 1 at the
            # true P_s (+9.5 % / +18.5 % at 60 / 120 us, +2.6 % / +5.3 % at 200 / 400 us)
            other = tau1 if k == 0 else tau0
            bias = -sp / np.log1p(-_sampled_exit_p(sp, tau, other)) / tau - 1
            assert bias > 0.7 * sp / (2 * other)
            ratio = np.mean(np.asarray(single[k]) / np.asarray(est[k])) - 1
            assert ratio == pytest.approx(bias, rel=0.1), (tau0, tau1, k, ratio, bias)


def test_dwell_mle_debounce_on_noisy_markov():
    # Debouncing at m = 2 bins on a sampled Markov chain with isolated one-sample
    # readout flips: merging (prev + flip + next) restores the true dwells, and the
    # shifted censored MLE recovers tau; without debouncing the flips read as fast
    # switching. The shift is an approximation: debouncing also merges the real
    # one-sample dwells, so at tau = 10 sp the estimate reads high by ~11 %.
    sp = 20.0
    seg_len, n_seg = 2000, 40
    gaps = list(range(seg_len, seg_len * n_seg, seg_len))
    rng = np.random.default_rng(8)
    for tau, tol in ((2000.0, None), (200.0, 0.2)):
        tau_exact = tau
        bits = _symmetric_markov(rng, seg_len * n_seg, tau, sp)
        flips = rng.random(bits.size) < 0.01
        bits = np.where(flips, 1 - bits, bits)
        t = np.arange(bits.size) * sp
        st = dwell_time_statistics(
            bits, t, gap_indices=gaps, merge_short_segments=True, min_dwell_bins=2
        )
        st_raw = dwell_time_statistics(bits, t, gap_indices=gaps)
        for k in (0, 1):
            tau_hat, e = st[f"tau_mle_{k}_us"], st[f"tau_err_{k}_us"]
            if tol is None:
                assert abs(tau_hat - tau_exact) < 4 * e, (k, tau_hat, tau_exact, e)
            else:
                assert tau_exact < tau_hat < (1 + tol) * tau_exact, (k, tau_hat, tau_exact)
            assert st_raw[f"tau_mle_{k}_us"] < 0.9 * tau_exact


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
        # F17: event-based baseline with its Poisson error and exposure, plus the old median
        for key in (
            "baseline_rate_err_Hz",
            "n_switches_baseline",
            "T_baseline_s",
            "median_window_rate_Hz",
        ):
            assert key in results, key
        assert results["T_baseline_s"] > 0
        assert results["baseline_rate_Hz"] == pytest.approx(
            results["n_switches_baseline"] / results["T_baseline_s"]
        )
        assert "mean_dwell_0_us" in results and "mean_dwell_1_us" in results
        # F73: dwell-time MLE with its error; the labels flip with P = 0.005 per sample,
        # i.e. a symmetric telegraph sampled every sp with tau = -2 sp/ln(1 - 2P)
        tau_syn = -2 * sample_period_us_syn / np.log1p(-2 * 0.005)
        for k in (0, 1):
            assert results[f"n_interior_{k}"] >= 50
            assert results[f"n_exits_{k}"] >= results[f"n_interior_{k}"]
            assert abs(results[f"tau_mle_{k}_us"] - tau_syn) < 4 * results[f"tau_err_{k}_us"], (
                k,
                results[f"tau_mle_{k}_us"],
                tau_syn,
            )

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
        assert sj["baseline_rate_err_Hz"] == pytest.approx(results["baseline_rate_err_Hz"])
        assert sj["tau_mle_0_us"] == pytest.approx(results["tau_mle_0_us"])
        assert sj["tau_err_1_us"] == pytest.approx(results["tau_err_1_us"])


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
    # Continuous-time rates: lambda01 = 1/2ms, lambda10 = 1/4ms, sampled exactly:
    # p01 = (2/3)(1 - exp(-sp * 3/4ms)) (~0.01 at 20 us cadence, ~0.048 at 100 us).
    for sample_us, n in [(20.0, 200_000), (100.0, 40_000)]:
        p01 = _sampled_exit_p(sample_us, 2000.0, 4000.0)
        p10 = _sampled_exit_p(sample_us, 4000.0, 2000.0)
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
        # F73: the dwell-time MLE recovers the continuous-time tau (2 ms / 4 ms) at both
        # cadences within 4 of its own error bars, which are tau/sqrt(N_exits) to a few %.
        for k, tau_k in ((0, 2000.0), (1, 4000.0)):
            tau_hat, err = st[f"tau_mle_{k}_us"], st[f"tau_err_{k}_us"]
            assert abs(tau_hat - tau_k) < 4 * err, (sample_us, k, tau_hat, tau_k, err)
            assert err == pytest.approx(tau_hat / np.sqrt(st[f"n_exits_{k}"]), rel=0.05)


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
    # Thresholds in the gap between the clouds (>= 2.5 sigma from both centres). The
    # default 30-70th percentiles of a balanced telegraph sit inside a cloud, where the
    # clean trace also has noise crossings (tau_cv ~0.6 for both traces at the defaults).
    thr = [-1.5, -0.75, 0.0, 0.75, 1.5]
    ts_clean = threshold_stability(clean_scores, t, threshold_list=thr)
    ts_noise = threshold_stability(noise_scores, t, threshold_list=thr)
    assert ts_clean["tau_cv"] < 0.1 < ts_noise["tau_cv"], (ts_clean["tau_cv"], ts_noise["tau_cv"])
    # Default threshold_list: the 30-70th score percentiles. It runs and returns finite
    # per-threshold MLEs, but it is not a telegraph-vs-noise discriminator (see docstring).
    ts_def = threshold_stability(clean_scores, t)
    np.testing.assert_allclose(
        ts_def["threshold_list"], np.percentile(clean_scores, [30, 40, 50, 60, 70])
    )
    assert len(ts_def["tau0_per_threshold"]) == len(ts_def["tau1_per_threshold"]) == 5
    assert np.all(np.isfinite(ts_def["tau0_per_threshold"] + ts_def["tau1_per_threshold"]))
    assert np.isfinite(ts_def["tau_cv"])
