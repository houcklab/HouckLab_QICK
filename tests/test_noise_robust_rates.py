"""F32: threshold-crossing rates beside a readout-error model and noise-robust estimators.

Threshold counting turns every misassigned sample into two spurious switches; the ZSP
analysis (analyze_parity_run) now reports the readout eps, the expected spurious rate,
the ACF / PSD / HMM rates on the analog scores and their agreement, and the Undriven
time-series analysis an HMM rate beside its Markov-ML rate. Synthetic data only.
"""

import json
import os

import h5py
import numpy as np
import pytest

from qicklab.analysis.rates import autocorrelation_rate_us, simulate_telegraph_trace
from qicklab.analysis.undriven import analyze_undriven_cloud, analyze_undriven_timeseries
from qicklab.analysis.zero_span import analyze_parity_run, event_switch_rate
from qicklab.experiments.undriven_single_shot import _TS_KEYS


def _write_zsp_h5(path, I, Q, t_us, gap_indices=(), sample_period_us=20.0):
    with h5py.File(path, "w") as f:
        f.create_dataset("I", data=I)
        f.create_dataset("Q", data=Q)
        f.create_dataset("t_us", data=t_us)
        f.create_dataset("gap_indices", data=np.asarray(gap_indices, dtype=int))
        f.attrs["sample_period_us"] = sample_period_us
        f.attrs["mode"] = "strobe"


def _driven_trace(pe, sigma, n, gamma_hz=(500.0, 500.0), sp_us=20.0, seed=1):
    tr = simulate_telegraph_trace(n, sp_us * 1e-6, *gamma_hz, 0.0, pe, sigma, sigma, seed=seed)
    Q = sigma * np.random.default_rng(seed + 1).standard_normal(n)
    t_us = tr["t_s"] * 1e6
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([1.0, 0.0])}
    true_rate = event_switch_rate(tr["states"], t_us)["rate_Hz"]
    return tr["v"], Q, t_us, sep, true_rate


def test_low_snr_threshold_rate_flagged_and_robust_rates_recover_truth(tmp_path):
    # parity levels 3.5 sigma apart: the threshold is right but noise crossings inflate
    # the counted rate several-fold; the ACF and HMM on the scores do not count crossings
    I, Q, t_us, sep, true_rate = _driven_trace(0.35, 0.1, n=60_000)
    h5_path = os.path.join(str(tmp_path), "ZeroSpanParity_lowsnr.h5")
    _write_zsp_h5(h5_path, I, Q, t_us)
    res = analyze_parity_run(
        h5_path, separator=sep, window_us=1000.0, save_plots=False, out_dir=str(tmp_path)
    )
    assert not res["bits_withheld"]
    thr = res["rate_switch_threshold_Hz"]
    assert thr == pytest.approx(res["threshold_switch_rate_Hz"])
    assert thr > 4 * true_rate, (thr, true_rate)
    # the readout-error model accounts for the excess: 2 eps (1 - eps) / sample period
    assert 0.002 < res["readout_eps"] < 0.05, res["readout_eps"]
    eps = res["readout_eps"]
    assert res["threshold_spurious_rate_Hz_est"] == pytest.approx(
        2 * eps * (1 - eps) / 20e-6, rel=1e-9
    )
    assert 0.5 < res["threshold_spurious_rate_Hz_est"] / (thr - true_rate) < 2.0
    # noise-robust estimators, as switches per second, recover the true rate
    assert res["hmm_identifiable"], res["hmm_unidentifiable_reasons"]
    assert res["hmm_n_samples"] == I.size
    assert res["rate_switch_hmm_Hz"] == pytest.approx(true_rate, rel=0.25)
    assert res["hmm_gamma01_Hz"] == pytest.approx(500.0, rel=0.3)
    assert res["hmm_gamma10_Hz"] == pytest.approx(500.0, rel=0.3)
    assert np.isfinite(res["hmm_gamma01_err_Hz"]) and res["hmm_gamma01_err_Hz"] > 0
    assert res["acf_fit_ok"]
    assert res["rate_switch_acf_Hz"] == pytest.approx(true_rate, rel=0.25)
    # ... and the agreement line flags the inflated threshold count
    assert res["rates_disagree"] is True
    assert res["rate_agreement_max_ratio"] > 4
    assert "DISAGREE" in res["rate_agreement"] and "threshold" in res["rate_agreement"]
    # the existing threshold outputs are unchanged by the new estimators
    assert res["baseline_rate_Hz"] > 4 * true_rate

    with open(os.path.join(str(tmp_path), "ZeroSpanParity_lowsnr_analysis.json")) as f:
        sj = json.load(f)
    for k in ("readout_eps", "acf_gamma_Hz", "psd_gamma_Hz", "hmm_gamma01_Hz", "rate_agreement"):
        assert k in sj, k
    with h5py.File(os.path.join(str(tmp_path), "ZeroSpanParity_lowsnr_analysis.h5"), "r") as f:
        assert f.attrs["hmm_gamma01_Hz"] == pytest.approx(res["hmm_gamma01_Hz"])


def test_high_snr_estimators_agree(tmp_path):
    # 8-sigma split: threshold counting is fine, and every estimator agrees
    I, Q, t_us, sep, true_rate = _driven_trace(0.4, 0.05, n=40_000, seed=3)
    h5_path = os.path.join(str(tmp_path), "ZeroSpanParity_clean.h5")
    _write_zsp_h5(h5_path, I, Q, t_us)
    res = analyze_parity_run(
        h5_path, separator=sep, window_us=1000.0, save_plots=False, out_dir=str(tmp_path)
    )
    assert res["readout_eps"] < 1e-4
    assert res["threshold_spurious_rate_Hz_est"] < 0.05 * true_rate
    assert res["rate_switch_threshold_Hz"] == pytest.approx(true_rate, rel=0.05)
    assert res["rate_switch_hmm_Hz"] == pytest.approx(true_rate, rel=0.2)
    assert res["rates_disagree"] is False and ": agree" in res["rate_agreement"]


def test_unequal_rates_switch_rate_conversion(tmp_path):
    # g01 = 300 Hz, g10 = 1200 Hz: occupancy w0 ~0.8, true switch rate ~460 Hz. The ACF
    # and PSD measure (g01 + g10)/2 ~750 Hz and need the 4 w0 w1 occupancy scale; the HMM
    # switch rate is 2 g01 g10 / (g01 + g10), not the mean ~750 Hz. Dropping the scale or
    # swapping the formula moves these entries ~1.6x off the true rate.
    I, Q, t_us, sep, true_rate = _driven_trace(0.4, 0.1, n=60_000, gamma_hz=(300.0, 1200.0), seed=5)
    h5_path = os.path.join(str(tmp_path), "ZeroSpanParity_asym.h5")
    _write_zsp_h5(h5_path, I, Q, t_us)
    res = analyze_parity_run(
        h5_path, separator=sep, window_us=1000.0, save_plots=False, out_dir=str(tmp_path)
    )
    w0, w1 = res["classifier_weights"]
    assert 0.75 < w0 < 0.88, (w0, w1)
    occ = 4.0 * w0 * w1
    assert res["acf_fit_ok"] and res["psd_fit_ok"]
    assert res["acf_gamma_Hz"] == pytest.approx(750.0, rel=0.2)
    assert res["rate_switch_acf_Hz"] == pytest.approx(occ * res["acf_gamma_Hz"], rel=1e-12)
    assert res["rate_switch_psd_Hz"] == pytest.approx(occ * res["psd_gamma_Hz"], rel=1e-12)
    assert res["hmm_identifiable"], res["hmm_unidentifiable_reasons"]
    g01, g10 = res["hmm_gamma01_Hz"], res["hmm_gamma10_Hz"]
    assert g01 == pytest.approx(300.0, rel=0.25) and g10 == pytest.approx(1200.0, rel=0.25)
    assert res["rate_switch_hmm_Hz"] == pytest.approx(2 * g01 * g10 / (g01 + g10), rel=1e-12)
    for k in ("rate_switch_acf_Hz", "rate_switch_psd_Hz", "rate_switch_hmm_Hz"):
        assert res[k] == pytest.approx(true_rate, rel=0.15), (k, res[k], true_rate)
    # the unscaled ACF and the mean HMM rate are not the switch rate here
    assert res["acf_gamma_Hz"] > 1.4 * true_rate
    assert 0.5 * (g01 + g10) > 1.4 * true_rate
    # threshold counting is inflated by eps; the robust entries flag it
    assert res["rate_switch_threshold_Hz"] > 3 * true_rate and res["rates_disagree"] is True


def test_gapped_record_hmm_dt_encodes_gaps(tmp_path):
    # the instrument's format: many short independent captures (shorter than a dwell),
    # t_us stitched contiguously across the dead time, boundaries only in gap_indices.
    # A gap-blind HMM counts every parity change across a boundary as a transition and
    # reports about 2.5x the true rate here (1844 Hz vs 752 Hz); with the gap steps set to
    # HMM_GAP_DT_S each capture is an independent restart and the rate is recovered
    sp, n_cap, n_per, sigma = 1.0, 120, 400, 0.08
    parts, states = [], []
    for k in range(n_cap):
        tr = simulate_telegraph_trace(
            n_per, sp * 1e-6, 1000.0, 1000.0, 0.0, 0.4, sigma, sigma, seed=100 + k
        )
        parts.append(tr["v"])
        states.append(tr["states"])
    I = np.concatenate(parts)
    t_us = np.arange(I.size) * sp
    gaps = [k * n_per for k in range(1, n_cap)]
    true_rate = event_switch_rate(np.concatenate(states), t_us, gap_indices=gaps)["rate_Hz"]
    Q = sigma * np.random.default_rng(0).standard_normal(I.size)
    sep = {"g_center": np.array([0.0, 0.0]), "e_center": np.array([1.0, 0.0])}
    h5_path = os.path.join(str(tmp_path), "ZeroSpanParity_gaps.h5")
    _write_zsp_h5(h5_path, I, Q, t_us, gap_indices=gaps, sample_period_us=sp)
    res = analyze_parity_run(
        h5_path, separator=sep, window_us=100.0, save_plots=False, out_dir=str(tmp_path)
    )
    assert res["hmm_identifiable"], res["hmm_unidentifiable_reasons"]
    assert res["rate_switch_hmm_Hz"] == pytest.approx(true_rate, rel=0.2), true_rate
    assert res["acf_fit_ok"]
    assert res["rate_switch_acf_Hz"] == pytest.approx(true_rate, rel=0.25), true_rate
    # the PSD's Welch windows span the gaps: reported, but left out of the agreement
    assert "Welch windows run across the acquisition gaps" in res["rate_warnings"]
    assert np.isfinite(res["psd_gamma_Hz"]) and np.isnan(res["rate_switch_psd_Hz"])
    assert "psd left out" in res["rate_agreement"]


def test_hmm_forward_pass_nonuniform_dt_matches_forward_backward():
    # the gap steps make the ZSP dt non-uniform; the scalar fast loop for that case must
    # give the same likelihood as the full forward/backward pass
    from qicklab.analysis.hmm import _forward_loglik, hmm_forward_backward

    rng = np.random.default_rng(4)
    n = 3000
    v = rng.normal(size=n) * 0.3 + (rng.random(n) > 0.5)
    dt = np.full(n - 1, 20e-6)
    dt[rng.integers(0, n - 1, size=30)] = 1e3
    dt[::7] = 40e-6
    for g01, g10 in ((500.0, 700.0), (1e-2, 1e6)):
        ll = _forward_loglik(v, dt, g01, g10, 0.0, 1.0, 0.3, 0.35)
        ref = hmm_forward_backward(v, dt, g01, g10, 0.0, 1.0, 0.3, 0.35)["loglik"]
        assert ll == pytest.approx(ref, rel=1e-12, abs=1e-9)


def test_hmm_sample_cap(tmp_path):
    I, Q, t_us, sep, _ = _driven_trace(0.4, 0.05, n=30_000, seed=5)
    h5_path = os.path.join(str(tmp_path), "ZeroSpanParity_cap.h5")
    _write_zsp_h5(h5_path, I, Q, t_us)
    res = analyze_parity_run(
        h5_path,
        separator=sep,
        window_us=1000.0,
        save_plots=False,
        out_dir=str(tmp_path),
        hmm_max_samples=10_000,
    )
    assert res["hmm_n_samples"] == 10_000
    assert "fitted on the first 10000 of 30000 samples" in res["rate_warnings"]


def test_withheld_bits_keep_threshold_free_estimators(tmp_path):
    # 1-sigma split: bits withheld (F07); the threshold entry is NaN and nothing raises.
    # The score fit fails delta BIC, so its components are no emission model: the HMM is
    # withheld too (fitted on them it reports ~3x the true rate). The ACF still runs.
    I, Q, t_us, sep, true_rate = _driven_trace(0.1, 0.1, n=20_000)
    h5_path = os.path.join(str(tmp_path), "ZeroSpanParity_unresolved.h5")
    _write_zsp_h5(h5_path, I, Q, t_us)
    res = analyze_parity_run(
        h5_path, separator=sep, window_us=1000.0, save_plots=False, out_dir=str(tmp_path)
    )
    assert res["bits_withheld"] is True
    for k in (
        "threshold_switch_rate_Hz",
        "rate_switch_threshold_Hz",
        "readout_eps",
        "threshold_spurious_rate_Hz_est",
    ):
        assert np.isnan(res[k]), (k, res[k])
    assert isinstance(res["rate_agreement"], str) and res["rate_agreement"]
    assert res["hmm_identifiable"] is False and res["hmm_n_samples"] == 0
    assert np.isnan(res["rate_switch_hmm_Hz"]) and np.isnan(res["hmm_gamma01_Hz"])
    assert "not bimodal" in res["hmm_unidentifiable_reasons"]
    assert res["acf_fit_ok"] and res["acf_gamma_Hz"] == pytest.approx(true_rate, rel=0.3)
    assert "fewer than two estimators" in res["rate_agreement"]


def test_kmeans_method_gets_estimators(tmp_path):
    I, Q, t_us, _, true_rate = _driven_trace(0.4, 0.05, n=20_000, seed=7)
    h5_path = os.path.join(str(tmp_path), "ZeroSpanParity_km.h5")
    _write_zsp_h5(h5_path, I, Q, t_us)
    res = analyze_parity_run(
        h5_path,
        classifier_method="kmeans",
        window_us=1000.0,
        save_plots=False,
        out_dir=str(tmp_path),
    )
    assert res["readout_eps"] < 1e-3
    assert res["rate_switch_hmm_Hz"] == pytest.approx(true_rate, rel=0.25)


def _acf_loop(v, edges):
    n = v.size
    x = v - v.mean()
    acov = np.zeros(n)
    for k in range(n):
        s = sum(float(np.dot(x[a : b - k], x[a + k : b])) for a, b in edges if b - a > k)
        p = sum(b - a - k for a, b in edges if b - a > k)
        acov[k] = s / p * (n - k) / n if p else 0.0
    return acov


def test_acf_gap_pooling_matches_loop():
    rng = np.random.default_rng(4)
    tr = simulate_telegraph_trace(400, 1e-6, 2e4, 2e4, 0.0, 1.0, 0.3, 0.3, seed=2)
    v = tr["v"] + 0.01 * rng.standard_normal(400)
    gaps = [120, 260]
    out = autocorrelation_rate_us(v, 1.0, gap_indices=gaps)
    ref = _acf_loop(v, [(0, 120), (120, 260), (260, 400)])
    k = out["acf"].size
    np.testing.assert_allclose(out["acf"], ref[:k] / ref[0], rtol=1e-9, atol=1e-12)
    # no gaps (None, [] or out-of-range boundaries) is the single-trace estimator
    base = autocorrelation_rate_us(v, 1.0)
    for g in ([], [0, 400]):
        same = autocorrelation_rate_us(v, 1.0, gap_indices=g)
        np.testing.assert_array_equal(same["acf"], base["acf"])
        assert same["tau_corr_us"] == base["tau_corr_us"]
    np.testing.assert_allclose(
        base["acf"],
        _acf_loop(v, [(0, 400)])[: base["acf"].size] / _acf_loop(v, [(0, 400)])[0],
        rtol=1e-9,
        atol=1e-12,
    )


def _undriven_cloud(sigma, n=40_000, gamma=500.0, dt_us=20.0, seed=11):
    tr = simulate_telegraph_trace(n, dt_us * 1e-6, gamma, gamma, -0.5, 0.5, sigma, sigma, seed=seed)
    q = sigma * np.random.default_rng(seed + 1).standard_normal(n)
    return analyze_undriven_cloud(tr["v"], q), tr


def test_undriven_hmm_beside_markov_ml():
    # blobs 1.0 apart at sigma 0.22 (eps ~1 %): the threshold Markov-ML rates are
    # inflated by noise crossings, the HMM rates are not
    cloud, tr = _undriven_cloud(0.22)
    assert cloud["n_blobs"] == 2
    ts = analyze_undriven_timeseries(cloud, 20.0)
    for name in _TS_KEYS:
        assert name in ts, name
    assert ts["gamma01_hz"] > 1.5 * 500 and ts["gamma10_hz"] > 1.5 * 500
    assert ts["hmm_identifiable"]
    assert ts["hmm_gamma01_hz"] == pytest.approx(500.0, rel=0.25)
    assert ts["hmm_gamma10_hz"] == pytest.approx(500.0, rel=0.25)
    assert ts["hmm_gamma_mean_hz"] == pytest.approx(
        0.5 * (ts["hmm_gamma01_hz"] + ts["hmm_gamma10_hz"])
    )
    assert ts["hmm_n_samples"] == tr["v"].size
    assert ts["hmm_gamma01_err_hz"] > 0
    capped = analyze_undriven_timeseries(cloud, 20.0, hmm_max_samples=5_000)
    assert capped["hmm_n_samples"] == 5_000
    # the existing (threshold) fields do not depend on the HMM
    for k in ("gamma01_hz", "gamma10_hz", "n_transitions", "acf_gamma_hz"):
        assert capped[k] == ts[k]


def test_undriven_hmm_withheld_without_two_blobs():
    rng = np.random.default_rng(0)
    cloud = analyze_undriven_cloud(rng.standard_normal(5000), rng.standard_normal(5000))
    assert cloud["n_blobs"] != 2
    ts = analyze_undriven_timeseries(cloud, 20.0)
    for name in _TS_KEYS:
        assert name in ts, name
    assert ts["hmm_identifiable"] is False and ts["hmm_n_samples"] == 0
    assert np.isnan(ts["hmm_gamma01_hz"]) and np.isnan(ts["hmm_gamma_mean_hz"])


def test_undriven_hmm_withholds_rate_and_error_on_uncorrelated_shots():
    # two blobs but i.i.d. shots (no telegraph): the HMM's i.i.d. gate withholds it, and
    # its (finite, internal) Hessian errors are withheld with the rates
    rng = np.random.default_rng(3)
    n = 20_000
    v = np.where(rng.random(n) < 0.3, 0.5, -0.5) + 0.12 * rng.standard_normal(n)
    cloud = analyze_undriven_cloud(v, 0.12 * rng.standard_normal(n))
    assert cloud["n_blobs"] == 2
    ts = analyze_undriven_timeseries(cloud, 20.0)
    assert ts["hmm_identifiable"] is False
    for k in ("hmm_gamma01_hz", "hmm_gamma10_hz", "hmm_gamma01_err_hz", "hmm_gamma10_err_hz"):
        assert np.isnan(ts[k]), (k, ts[k])
    assert any(w.startswith("HMM rate withheld") for w in ts["warnings"])
