"""
Hardware-free deterministic tests for the Modified-Ramsey charge-parity
switching analysis (qicklab.analysis: hmm, rates, readout, modified_ramsey)
and the pure planning helpers in qicklab.experiments.modified_ramsey.

Everything here is seeded and offline: no RFSoC, no Pyro4, no instruments.
Timing checks that need real clock domains stay in
tests/hardware/verify_modified_ramsey_timing.py (hardware-in-the-loop companion).

Run from the repo root:
    python -m pytest tests/test_modified_ramsey_offline.py
"""

import math
import os

import numpy as np

from qicklab.analysis.hmm import (
    _iid_gaussian_mixture_refit,
    _iid_mixture_loglik,
    _log_emissions_from_spec,
    fit_two_state_hmm,
    hmm_forward_backward,
    hmm_viterbi,
)
from qicklab.analysis.modified_ramsey import (
    analyze_modified_ramsey_record,
    assess_parity_record,
    compare_parity_controls,
    drift_corrected_lag_sum,
    lagged_autocovariance_sum,
    reset_success_vs_cycle,
)
from qicklab.analysis.rates import (
    autocorrelation_rate_estimate,
    psd_rate_estimate,
    rate_vs_bin_size,
    remove_slow_drift,
    simulate_telegraph_trace,
    transition_matrix_2state,
)
from qicklab.analysis.readout import calibrate_readout_from_labeled_shots


def close(a, b, rel):
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= rel * abs(b)


# ---------------------------------------------------------------------------
# 1. expm(Q*dt) convention
# ---------------------------------------------------------------------------


def test_transition_matrix():
    from scipy.linalg import expm

    for g01, g10, dt in [
        (400.0, 400.0, 20e-6),
        (150.0, 900.0, 5e-6),
        (1e4, 3.0, 1e-3),
        (0.0, 0.0, 1e-3),
        (250.0, 250.0, 2.5e-3),
    ]:
        Q = np.array([[-g01, g01], [g10, -g10]])
        P_ref = expm(Q * dt)
        P = transition_matrix_2state(g01, g10, dt)
        assert np.allclose(P, P_ref, atol=1e-12), (
            f"expm match g01={g01}, g10={g10}, dt={dt}"
            + ": "
            + f"max err {np.max(np.abs(P - P_ref)):.2e}"
        )
        assert np.allclose(P.sum(axis=1), 1.0, atol=1e-12), f"rows sum to 1 (g01={g01}, g10={g10})"


# ---------------------------------------------------------------------------
# 2. Readout calibration: contrast vs assignment fidelity
# ---------------------------------------------------------------------------


def test_calibration():
    rng = np.random.default_rng(7)
    n = 20000
    d = 4.0  # separation in units of sigma=1 -> P(correct) = Phi(2) = 0.97725
    Ig = rng.normal(0.0, 1.0, n)
    Qg = rng.normal(0.0, 1.0, n)
    Ie = rng.normal(d, 1.0, n)
    Qe = rng.normal(0.0, 1.0, n)
    cal = calibrate_readout_from_labeled_shots(Ig, Qg, Ie, Qe)

    from scipy.stats import norm as norm_dist

    p_correct = norm_dist.cdf(d / 2.0)
    contrast_true = 2 * p_correct - 1

    assert abs(cal["contrast"] - contrast_true) < 0.01, (
        "contrast == max|CDF_g - CDF_e| ~= 2*Phi(d/2)-1: "
        + f"got {cal['contrast']:.4f}, analytic {contrast_true:.4f}"
    )
    assert cal["assignment_fidelity"] == 0.5 * (1 + cal["contrast"]), (
        "assignment fidelity == (1 + contrast)/2 EXACTLY"
    )
    assert cal["max_cdf_gap"] == cal["contrast"], (
        "max_cdf_gap is the same quantity as contrast (legacy 'Fidelity = xx%' figure)"
    )
    assert abs(cal["threshold"]) < 0.15, (
        "threshold near the midpoint: " + f"threshold {cal['threshold']:.3f}"
    )
    assert (
        abs(cal["confusion_matrix"][0, 0] - p_correct) < 0.01
        and abs(cal["confusion_matrix"][1, 1] - p_correct) < 0.01
    ), (
        "confusion-matrix diagonal ~= Phi(d/2): " + f"diag {cal['confusion_matrix'][0, 0]:.4f}, "
        f"{cal['confusion_matrix'][1, 1]:.4f}"
    )
    assert close(cal["snr_analog"], d, 0.05), (
        "analog SNR ~= d/sigma: " + f"snr {cal['snr_analog']:.3f}"
    )
    assert cal["axis"][0] > 0.99 and abs(cal["axis"][1]) < 0.1, "axis points g -> e along +I"
    assert np.allclose(cal["cov_g"], np.eye(2), atol=0.05) and np.allclose(
        cal["cov_e"], np.eye(2), atol=0.05
    ), "covariances ~ identity"
    # Ideal prep: no resolvable e-cloud mixture, so the clean clouds are the moments (F38)
    assert cal["clean_cloud_source"] == "moments" and cal["prep_fidelity_e"] == 1.0
    assert cal["proj_e_mean_clean"] == cal["proj_e_mean"]
    assert cal["snr_analog_clean"] == cal["snr_analog"]

    # Zero contrast: overlapping clouds must warn.
    Ie0 = rng.normal(0.0, 1.0, n)
    Qe0 = rng.normal(0.05, 1.0, n)
    cal0 = calibrate_readout_from_labeled_shots(Ig, Qg, Ie0, Qe0)
    assert cal0["contrast"] < 0.1 and len(cal0["warnings"]) > 0, (
        "overlapping clouds -> low contrast + warnings: " + f"contrast {cal0['contrast']:.3f}"
    )


def _make_cal(mu_g, mu_e, sigma, seed=11, n=8000):
    """Calibration object from synthetic labeled clouds along I."""
    rng = np.random.default_rng(seed)
    Ig = rng.normal(mu_g, sigma, n)
    Qg = rng.normal(0, sigma, n)
    Ie = rng.normal(mu_e, sigma, n)
    Qe = rng.normal(0, sigma, n)
    return calibrate_readout_from_labeled_shots(Ig, Qg, Ie, Qe)


# ---------------------------------------------------------------------------
# 3. HMM rate recovery
# ---------------------------------------------------------------------------


def test_hmm_symmetric_strong():
    gamma = 400.0
    dt = 20e-6
    n = 30000
    sim = simulate_telegraph_trace(
        n, dt, gamma, gamma, mu0=0.0, mu1=3.0, sigma0=1.0, sigma1=1.0, seed=1
    )
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=True)
    assert fit["identifiable"], "identifiable: " + "; ".join(fit["unidentifiable_reasons"])
    assert close(fit["gamma01_hz"], gamma, 0.15), (
        "gamma within 15%: " + f"fit {fit['gamma01_hz']:.1f} Hz vs true {gamma} Hz "
        f"(err {fit['gamma01_err_hz']:.1f})"
    )
    assert math.isfinite(fit["gamma01_err_hz"]) and 0 < fit["gamma01_err_hz"] < gamma, (
        "Hessian error is finite and sane: " + f"err {fit['gamma01_err_hz']:.1f} Hz"
    )
    assert abs(fit["occupancy"][1] - 0.5) < 0.1, (
        "occupancy ~ 50/50: " + f"occ1 {fit['occupancy'][1]:.3f}"
    )
    assert fit["posterior_ambiguity"] < 0.15, (
        "posteriors confident: " + f"ambiguity {fit['posterior_ambiguity']:.3f}"
    )
    # Viterbi vs truth
    agree = np.mean(fit["viterbi_path"] == sim["states"])
    assert agree > 0.90, "Viterbi matches true states > 90%: " + f"agreement {agree:.3f}"


def test_hmm_asymmetric():
    g01, g10 = 150.0, 450.0
    dt = 20e-6
    n = 30000
    sim = simulate_telegraph_trace(
        n, dt, g01, g10, mu0=0.0, mu1=3.0, sigma0=1.0, sigma1=1.0, seed=2
    )
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=False)
    assert fit["identifiable"], "identifiable: " + "; ".join(fit["unidentifiable_reasons"])
    assert close(fit["gamma01_hz"], g01, 0.30), (
        "gamma01 within 30%: " + f"fit {fit['gamma01_hz']:.1f} vs {g01}"
    )
    assert close(fit["gamma10_hz"], g10, 0.30), (
        "gamma10 within 30%: " + f"fit {fit['gamma10_hz']:.1f} vs {g10}"
    )
    assert abs(fit["occupancy"][1] - 0.25) < 0.08, (
        "occupancy(state1) ~ g01/(g01+g10) = 0.25: " + f"occ1 {fit['occupancy'][1]:.3f}"
    )


def test_hmm_moderate_contrast():
    gamma = 300.0
    dt = 20e-6
    n = 40000
    sim = simulate_telegraph_trace(
        n, dt, gamma, gamma, mu0=0.0, mu1=1.5, sigma0=1.0, sigma1=1.0, seed=3
    )
    em = {"mu0": 0.0, "mu1": 1.5, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=True)
    assert fit["identifiable"], "identifiable at SNR 1.5: " + "; ".join(
        fit["unidentifiable_reasons"]
    )
    assert close(fit["gamma01_hz"], gamma, 0.35), (
        "gamma within 35%: " + f"fit {fit['gamma01_hz']:.1f} vs {gamma}"
    )
    assert 0.0 <= fit["posterior_ambiguity"] <= 0.5, (
        "ambiguity reported and sane: " + f"ambiguity {fit['posterior_ambiguity']:.3f}"
    )

    # Fast switching (dwell ~2.5 samples) at SNR 1: temporal smoothing cannot
    # disambiguate individual samples, so the posterior-ambiguity warning must
    # fire even though the RATE is still recoverable.
    sim_lo = simulate_telegraph_trace(
        20000, 100e-6, 4000.0, 4000.0, mu0=0.0, mu1=1.0, sigma0=1.0, sigma1=1.0, seed=30
    )
    em_lo = {"mu0": 0.0, "mu1": 1.0, "sigma0": 1.0, "sigma1": 1.0}
    fit_lo = fit_two_state_hmm(sim_lo["v"], 100e-6, em_lo, symmetric=True, min_emission_snr=0.1)
    assert any("posterior ambiguity" in w for w in fit_lo["warnings"]), (
        "posterior-ambiguity warning fires when smoothing cannot disambiguate: "
        + f"ambiguity {fit_lo['posterior_ambiguity']:.3f}"
    )


def test_hmm_zero_contrast():
    rng = np.random.default_rng(4)
    v = rng.normal(0.0, 1.0, 20000)
    em = {"mu0": 0.0, "mu1": 0.0 + 1e-6, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(v, 20e-6, em, symmetric=True)
    assert not fit["identifiable"], "zero contrast -> identifiable=False"
    assert math.isnan(fit["gamma01_hz"]), "rates withheld (nan)"
    assert any("emission separation" in r for r in fit["unidentifiable_reasons"]), (
        "reason names emission separation: " + str(fit["unidentifiable_reasons"])
    )


_GE_EM_ASSUMED = {
    "model": "ge_mixture",
    "mu_g": 0.0,
    "mu_e": 2.0,
    "sigma_g": 1.0,
    "sigma_e": 1.0,
    "p_e_state0": 0.1,
    "p_e_state1": 0.9,
}


def _iid_reason(fit):
    return any("uncorrelated (i.i.d.)" in r for r in fit["unidentifiable_reasons"])


def test_hmm_iid_shots_unidentifiable():
    # Uncorrelated 50/50 g/e shots (no parity information) at a 262 us rep,
    # readout SNR 2. Before the i.i.d. gate this was "identifiable" at
    # 7-80 kHz: the single-Gaussian null only tests readout bimodality.
    dt = 262e-6
    rng = np.random.default_rng(60)
    v = rng.normal(np.where(rng.random(20000) < 0.5, 2.0, 0.0), 1.0)
    fit = fit_two_state_hmm(v, dt, _GE_EM_ASSUMED, symmetric=True)
    assert fit["delta_loglik"] > 100, (
        "readout is bimodal (single-Gaussian gate passes): " + f"{fit['delta_loglik']:.1f}"
    )
    assert not fit["identifiable"] and math.isnan(fit["gamma01_hz"]), (
        "i.i.d. symmetric shots -> unidentifiable: " + str(fit["unidentifiable_reasons"])
    )
    assert _iid_reason(fit) and fit["delta_loglik_iid"] < 10, (
        "reason names the i.i.d. null: " + f"dLL_iid {fit['delta_loglik_iid']:.2f}"
    )

    # Biased i.i.d. shots, P(e) = 0.3, asymmetric fit: the null must free the
    # mixture weight (w = (0.3 - 0.1)/0.8 = 0.25), or a 50/50 null is beaten
    # by hundreds of log-likelihood units and the record passes.
    v_b = rng.normal(np.where(rng.random(20000) < 0.3, 2.0, 0.0), 1.0)
    fit_b = fit_two_state_hmm(v_b, dt, _GE_EM_ASSUMED, symmetric=False)
    assert abs(fit_b["iid_weight_state1"] - 0.25) < 0.03, (
        "i.i.d. null weight maximised: " + f"w {fit_b['iid_weight_state1']:.3f}"
    )
    assert not fit_b["identifiable"] and _iid_reason(fit_b), (
        "biased i.i.d. shots -> unidentifiable: " + str(fit_b["unidentifiable_reasons"])
    )

    # Biased i.i.d. shots with the DEFAULT symmetric=True fit (runner default
    # hmm_symmetric=True), P(e) = 0.25, readout SNR 4. A null with its weight
    # fixed at 1/2 is misspecified here: the symmetric HMM beat it by ~2000
    # and the record was "identifiable" at ~700 Hz. The free-weight null
    # (w = (0.25 - 0.1)/0.8 = 0.1875) wins outright (gain < 0).
    em4 = dict(_GE_EM_ASSUMED, mu_e=4.0)
    v_s = rng.normal(np.where(rng.random(20000) < 0.25, 4.0, 0.0), 1.0)
    fit_s = fit_two_state_hmm(v_s, dt, em4, symmetric=True)
    assert abs(fit_s["iid_weight_state1"] - 0.1875) < 0.03, (
        "null weight free also for symmetric=True: " + f"w {fit_s['iid_weight_state1']:.3f}"
    )
    assert not fit_s["identifiable"] and _iid_reason(fit_s) and fit_s["delta_loglik_iid"] < 10, (
        "biased i.i.d. shots, symmetric fit -> unidentifiable: "
        + f"dLL_iid {fit_s['delta_loglik_iid']:.1f}, {fit_s['unidentifiable_reasons']}"
    )


def _em_two_gaussian_loglik(v, n_iter=500):
    # Independent reference: EM for an i.i.d. two-Gaussian mixture.
    w, m0, m1 = 0.5, np.percentile(v, 25), np.percentile(v, 75)
    s0 = s1 = np.std(v) / 2
    for _ in range(n_iter):
        l0 = np.log1p(-w) - 0.5 * ((v - m0) / s0) ** 2 - np.log(s0 * np.sqrt(2 * np.pi))
        l1 = np.log(w) - 0.5 * ((v - m1) / s1) ** 2 - np.log(s1 * np.sqrt(2 * np.pi))
        r1 = np.exp(l1 - np.logaddexp(l0, l1))
        w = r1.mean()
        m0, m1 = np.average(v, weights=1 - r1), np.average(v, weights=r1)
        s0 = np.sqrt(np.average((v - m0) ** 2, weights=1 - r1))
        s1 = np.sqrt(np.average((v - m1) ** 2, weights=r1))
    return float(np.sum(np.logaddexp(l0, l1)))


def test_hmm_iid_null_refits_emissions():
    # fit_emissions=True: the i.i.d. null must be maximised over its OWN
    # weight, means and sigmas (a proper likelihood ratio), not evaluated at
    # the HMM's refit emissions, which would understate it.
    dt = 262e-6
    rng = np.random.default_rng(65)
    v = rng.normal(np.where(rng.random(5000) < 0.4, 2.3, -0.2), 1.1)
    em = {"model": "gaussian", "mu0": 0.0, "mu1": 2.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(v, dt, em, symmetric=False, fit_emissions=True)
    ll_ref = _em_two_gaussian_loglik(v)
    assert fit["loglik_iid"] >= ll_ref - 0.05, (
        "null at the i.i.d. mixture MLE: " + f"{fit['loglik_iid']:.3f} vs EM {ll_ref:.3f}"
    )
    assert not fit["identifiable"] and _iid_reason(fit), (
        "i.i.d. shots, free emissions -> unidentifiable: " + str(fit["unidentifiable_reasons"])
    )
    # The null's own emissions are refit even from a poor start (the HMM's
    # emissions): evaluated there it would be understated by tens of units.
    poor = {"mu0": 0.3, "mu1": 1.6, "sigma0": 0.8, "sigma1": 1.4}
    le_poor = _log_emissions_from_spec(v, dict(poor, model="gaussian"))
    ll_fixed, w_fixed = _iid_mixture_loglik(le_poor)
    bounds = [(-10.0, 10.0)] * 2 + [(math.log(1e-3), math.log(1e3))] * 2
    ll_refit, _ = _iid_gaussian_mixture_refit(v, poor, w_fixed, bounds)
    assert ll_fixed < ll_ref - 10 and abs(ll_refit - ll_ref) < 0.05, (
        f"fixed {ll_fixed:.2f}, refit {ll_refit:.2f}, EM {ll_ref:.2f}"
    )


def test_hmm_dephased_record_unidentifiable():
    # A real 200 Hz telegraph whose g/e mapping carries (almost) no parity
    # information (T2 << tau, or df unresolved: p_e_state0 ~ p_e_state1),
    # analysed with the ASSUMED 0.1/0.9 mapping.
    dt = 262e-6
    n = 20000
    hidden = simulate_telegraph_trace(
        n, dt, 200.0, 200.0, mu0=0.0, mu1=1.0, sigma0=1e-9, sigma1=1e-9, seed=61
    )["states"]
    rng = np.random.default_rng(62)
    prepared_e = rng.random(n) < np.where(hidden == 0, 0.49, 0.51)
    v = rng.normal(np.where(prepared_e, 2.0, 0.0), 1.0)
    fit = fit_two_state_hmm(v, dt, _GE_EM_ASSUMED, symmetric=True)
    assert not fit["identifiable"] and _iid_reason(fit), (
        "dephased record -> unidentifiable via the i.i.d. gate: "
        + str(fit["unidentifiable_reasons"])
    )

    # The same cadence with an informative mapping stays identifiable, and
    # the i.i.d. gain is decisive.
    prepared_e = rng.random(n) < np.where(hidden == 0, 0.1, 0.9)
    v_ok = rng.normal(np.where(prepared_e, 2.0, 0.0), 1.0)
    fit_ok = fit_two_state_hmm(v_ok, dt, _GE_EM_ASSUMED, symmetric=True)
    assert fit_ok["identifiable"] and close(fit_ok["gamma01_hz"], 200.0, 0.25), (
        "informative 200 Hz telegraph at 262 us still identifiable: "
        + f"{fit_ok['gamma01_hz']:.1f} Hz, {fit_ok['unidentifiable_reasons']}"
    )
    assert fit_ok["delta_loglik_iid"] > 100 and fit_ok["mixing_per_step"] < 0.3, (
        "decisive i.i.d. gain, resolved rate: "
        + f"dLL_iid {fit_ok['delta_loglik_iid']:.1f}, mix {fit_ok['mixing_per_step']:.2f}"
    )


def test_hmm_unresolved_rate_gate():
    # A genuine telegraph switching faster than the cadence resolves:
    # (g01 + g10) * dt = 2 * 3 kHz * 262 us ~ 1.6, correlation exp(-1.6) per
    # sample. The i.i.d. gate passes (dLL_iid ~ 40), so only the resolved-rate
    # gate withholds the rate; opening it (max_mixing=100) releases it.
    dt = 262e-6
    n = 20000
    hidden = simulate_telegraph_trace(
        n, dt, 3000.0, 3000.0, mu0=0.0, mu1=1.0, sigma0=1e-9, sigma1=1e-9, seed=63
    )["states"]
    rng = np.random.default_rng(64)
    prepared_e = rng.random(n) < np.where(hidden == 0, 0.1, 0.9)
    v = rng.normal(np.where(prepared_e, 2.0, 0.0), 1.0)
    fit = fit_two_state_hmm(v, dt, _GE_EM_ASSUMED, symmetric=True)
    reasons = fit["unidentifiable_reasons"]
    assert (
        not fit["identifiable"] and len(reasons) == 1 and "unresolved at this cadence" in reasons[0]
    ), "only the resolved-rate gate fires: " + str(reasons)
    assert fit["mixing_per_step"] > 1.0 and fit["delta_loglik_iid"] > 10, (
        f"mix {fit['mixing_per_step']:.2f}, dLL_iid {fit['delta_loglik_iid']:.1f}"
    )
    fit_open = fit_two_state_hmm(v, dt, _GE_EM_ASSUMED, symmetric=True, max_mixing=100.0)
    assert fit_open["identifiable"] and close(fit_open["gamma01_hz"], 3000.0, 0.3), (
        "max_mixing opens the gate: " + str(fit_open["unidentifiable_reasons"])
    )


def test_hmm_label_permutation():
    g01, g10 = 200.0, 500.0
    dt = 20e-6
    n = 25000
    sim = simulate_telegraph_trace(
        n, dt, g01, g10, mu0=0.0, mu1=3.0, sigma0=1.0, sigma1=1.0, seed=5
    )
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    em_swap = {"mu0": 3.0, "mu1": 0.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=False)
    fit_s = fit_two_state_hmm(sim["v"], dt, em_swap, symmetric=False)
    assert fit["identifiable"] and fit_s["identifiable"], "both fits identifiable"
    assert close(fit_s["gamma01_hz"], fit["gamma10_hz"], 0.15) and close(
        fit_s["gamma10_hz"], fit["gamma01_hz"], 0.15
    ), (
        "gamma01 <-> gamma10 swap under label permutation: "
        + f"orig ({fit['gamma01_hz']:.0f}, {fit['gamma10_hz']:.0f}) "
        f"swapped ({fit_s['gamma01_hz']:.0f}, {fit_s['gamma10_hz']:.0f})"
    )
    assert np.allclose(fit["posteriors"][:, 0], fit_s["posteriors"][:, 1], atol=0.05), (
        "posteriors swap columns"
    )
    assert abs(fit["occupancy"][1] - fit_s["occupancy"][0]) < 0.05, "occupancies mirror"


def test_hmm_missing_samples():
    gamma = 400.0
    dt0 = 20e-6
    n_full = 30000
    sim = simulate_telegraph_trace(
        n_full, dt0, gamma, gamma, mu0=0.0, mu1=3.0, sigma0=1.0, sigma1=1.0, seed=6
    )
    rng = np.random.default_rng(60)
    keep = np.sort(rng.choice(n_full, size=int(0.9 * n_full), replace=False))
    v = sim["v"][keep]
    t = sim["t_s"][keep]
    dt_steps = np.diff(t)
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(v, dt_steps, em, symmetric=True)
    assert fit["identifiable"], "identifiable with 10% samples missing: " + "; ".join(
        fit["unidentifiable_reasons"]
    )
    assert close(fit["gamma01_hz"], gamma, 0.20), (
        "gamma within 20% despite gaps: " + f"fit {fit['gamma01_hz']:.1f} vs {gamma}"
    )


def test_hmm_few_and_no_switches():
    dt = 20e-6
    n = 20000  # 0.4 s
    sim = simulate_telegraph_trace(
        n, dt, 5.0, 5.0, mu0=0.0, mu1=3.0, sigma0=1.0, sigma1=1.0, seed=8
    )
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=True)
    assert not fit["identifiable"], "few-switch record -> unidentifiable"
    assert any("transitions" in r for r in fit["unidentifiable_reasons"]), (
        "reason names transition count: " + str(fit["unidentifiable_reasons"])
    )

    rng = np.random.default_rng(9)
    v0 = rng.normal(0.0, 1.0, n)  # never leaves state 0
    fit0 = fit_two_state_hmm(v0, dt, em, symmetric=True)
    assert not fit0["identifiable"], "no-switch record -> unidentifiable: " + str(
        fit0["unidentifiable_reasons"]
    )
    assert math.isnan(fit0["gamma01_hz"]), "no-switch rates withheld"


def test_hmm_bootstrap():
    gamma = 500.0
    dt = 20e-6
    sim = simulate_telegraph_trace(
        8000, dt, gamma, gamma, mu0=0.0, mu1=3.0, sigma0=1.0, sigma1=1.0, seed=10
    )
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=True, n_boot=8, seed=42)
    ci = fit["gamma_boot_ci"]
    assert ci is not None and ci["n_boot"] == 8, "bootstrap CI produced"
    if ci:
        p16, p84 = ci["gamma01_hz"]["p16"], ci["gamma01_hz"]["p84"]
        assert (
            p16 < ci["gamma01_hz"]["p50"] < p84
            and p16 < fit["gamma01_hz"] * 1.5
            and p84 > fit["gamma01_hz"] * 0.5
        ), (
            "CI brackets are ordered and near the fit: "
            + f"p16={p16:.0f}, p50={ci['gamma01_hz']['p50']:.0f}, "
            f"p84={p84:.0f}, fit={fit['gamma01_hz']:.0f}"
        )
    # Determinism: same seed, same CI.
    fit2 = fit_two_state_hmm(sim["v"], dt, em, symmetric=True, n_boot=8, seed=42)
    assert fit2["gamma_boot_ci"]["gamma01_hz"]["p50"] == ci["gamma01_hz"]["p50"], (
        "bootstrap deterministic under fixed seed"
    )


# ---------------------------------------------------------------------------
# 4. tau_dwell / tau_corr / f_corner conventions
# ---------------------------------------------------------------------------


def test_rate_conventions():
    gamma = 250.0  # per-state switch rate
    dt = 20e-6
    n = 200000  # 4 s record, ~2000 switches: tight statistics
    sim = simulate_telegraph_trace(
        n, dt, gamma, gamma, mu0=-1.0, mu1=1.0, sigma0=0.05, sigma1=0.05, seed=12
    )

    # tau_dwell = 1/gamma from the true state path
    states = sim["states"]
    edges = np.flatnonzero(np.diff(states)) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [n]])
    dwells = (ends - starts)[1:-1] * dt  # drop censored first/last runs
    assert close(float(np.mean(dwells)), 1.0 / gamma, 0.10), (
        "mean dwell ~= 1/gamma: " + f"mean dwell {np.mean(dwells) * 1e3:.3f} ms vs "
        f"1/gamma = {1e3 / gamma:.3f} ms"
    )

    acf = autocorrelation_rate_estimate(sim["v"], dt)
    assert acf["fit_ok"], "acf fit ok: " + "; ".join(acf["warnings"])
    assert close(acf["tau_corr_s"], 1.0 / (2 * gamma), 0.15), (
        "tau_corr ~= 1/(2*gamma): " + f"tau_corr {acf['tau_corr_s'] * 1e3:.3f} ms vs "
        f"{1e3 / (2 * gamma):.3f} ms"
    )
    assert close(acf["gamma_hz"], gamma, 0.15), (
        "acf gamma ~= gamma: " + f"acf gamma {acf['gamma_hz']:.1f} Hz"
    )

    psd = psd_rate_estimate(sim["v"], dt)
    assert psd["fit_ok"], "psd fit ok: " + "; ".join(psd["warnings"])
    assert close(psd["f_corner_hz"], gamma / math.pi, 0.25), (
        "f_corner ~= gamma/pi: " + f"f_corner {psd['f_corner_hz']:.1f} Hz vs "
        f"gamma/pi = {gamma / math.pi:.1f} Hz"
    )
    assert close(psd["gamma_hz"], gamma, 0.25), (
        "psd gamma ~= gamma: " + f"psd gamma {psd['gamma_hz']:.1f} Hz"
    )


# ---------------------------------------------------------------------------
# 5. Drift removal
# ---------------------------------------------------------------------------


def test_drift():
    gamma = 400.0
    dt = 20e-6
    n = 50000  # 1 s
    t = np.arange(n) * dt
    drift_true = 2.5 * (t / t[-1])  # linear ramp comparable to the separation
    sim = simulate_telegraph_trace(
        n, dt, gamma, gamma, mu0=0.0, mu1=3.0, sigma0=1.0, sigma1=1.0, seed=13, drift=drift_true
    )
    out = remove_slow_drift(sim["v"], dt, drift_timescale_s=0.1, expected_dwell_s=1.0 / gamma)
    assert np.array_equal(out["v_original"], sim["v"]), "original trace preserved untouched"
    assert out["safe"], "drift window flagged safe (40x dwell)"
    # The rolling mean carries the ramp plus telegraph occupancy fluctuation
    # (~separation/(2*sqrt(N_dwells)) per window) and boundary effects, so the
    # detected span brackets the 2.5 ramp loosely.
    assert 1.5 < out["drift_span"] < 4.5, (
        "drift span detected ~ ramp amplitude: " + f"span {out['drift_span']:.2f} vs ramp 2.5"
    )

    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    # Center the corrected trace back on the calibrated emission midpoint
    # (drift removal preserves DC = mean of drift, which includes the ramp).
    v_corr = out["v_corrected"] - out["v_corrected"].mean() + 1.5
    fit = fit_two_state_hmm(v_corr, dt, em, symmetric=True)
    assert fit["identifiable"] and close(fit["gamma01_hz"], gamma, 0.25), (
        "rate recovered after drift removal: " + f"fit {fit['gamma01_hz']:.1f} vs {gamma}"
    )

    out_short = remove_slow_drift(sim["v"], dt, drift_timescale_s=0.01, expected_dwell_s=2.5e-3)
    assert not out_short["safe"] and out_short["warnings"], (
        "too-short drift window flagged unsafe with warning"
    )


# ---------------------------------------------------------------------------
# 6. Controls: final-pulse sign reversal and echo null
# ---------------------------------------------------------------------------


def _analyzed(v, dt, em, label, control_type=None):
    fit = fit_two_state_hmm(v, dt, em, symmetric=False)
    acf = autocorrelation_rate_estimate(v, dt)
    occ1 = float(fit["occupancy"][1]) if fit["posteriors"] is not None else float("nan")
    d = {"label": label, "hmm": fit, "acf": acf, "occupancy_state1": occ1}
    if control_type:
        d["control_type"] = control_type
    return d


def test_controls():
    g01, g10 = 150.0, 450.0  # asymmetric so the mapping inversion is visible
    dt = 20e-6
    n = 30000
    sim = simulate_telegraph_trace(
        n, dt, g01, g10, mu0=0.0, mu1=3.0, sigma0=1.0, sigma1=1.0, seed=14
    )
    em = {"mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}

    # flip_final_pi2 swaps which parity branch maps to which readout cloud:
    # the SAME parity trajectory now emits with the means exchanged.
    rng = np.random.default_rng(15)
    mu_flip = np.where(sim["states"] == 0, 3.0, 0.0)
    v_flip = mu_flip + rng.standard_normal(n)

    main = _analyzed(sim["v"], dt, em, "parity")
    flip = _analyzed(v_flip, dt, em, "flip", control_type="flip_final_pi2")

    # echo null: parity contrast destroyed -> emission collapses to one level.
    rng2 = np.random.default_rng(16)
    v_echo = 1.5 + rng2.standard_normal(n)
    echo = _analyzed(v_echo, dt, em, "echo", control_type="use_pi_pulse")
    echo["control_type"] = "echo_null"

    cmp_out = compare_parity_controls(main, [flip, echo])
    by_type = {c["control_type"]: c for c in cmp_out["controls"]}
    assert by_type["flip_final_pi2"]["checked"] is True, (
        "flip control: telegraph survives with inverted mapping: "
        + by_type["flip_final_pi2"]["note"]
    )
    assert abs(main["occupancy_state1"] + flip["occupancy_state1"] - 1.0) < 0.1, (
        "occupancy actually inverted: " + f"main occ1 {main['occupancy_state1']:.2f}, "
        f"flip occ1 {flip['occupancy_state1']:.2f}"
    )
    assert by_type["echo_null"]["checked"] is True, (
        "echo null: parity contrast suppressed: " + by_type["echo_null"]["note"]
    )
    assert cmp_out["all_expected"], "all controls behave as expected"
    assert not echo["hmm"]["identifiable"], "echo-null HMM is itself unidentifiable: " + str(
        echo["hmm"]["unidentifiable_reasons"]
    )


# ---------------------------------------------------------------------------
# 7. Pure planning helpers (tau + mapping conventions, control variants)
# ---------------------------------------------------------------------------


def test_planning_helpers():
    from qicklab.experiments.modified_ramsey import (
        MR_CONTROL_TYPE_CODES,
        build_control_variants,
        plan_parity_mapping,
    )

    p = plan_parity_mapping(0.5, 0.1)
    assert p["tau_us"] == 1.0, "tau = 1/(2*df): " + f"tau {p['tau_us']}"
    assert abs(p["gap_us"] - (1.0 - 0.4)) < 1e-12, (
        "gap = tau - 4*sigma (no pi): " + f"gap {p['gap_us']}"
    )
    assert p["final_pi2_phase_deg"] == 180, "standard final pi/2 phase 180 deg"
    assert p["feasible"], "feasible at df=0.5, sigma=0.1: " + str(p["errors"])

    p_echo = plan_parity_mapping(0.5, 0.1, use_pi_pulse=True)
    assert abs(p_echo["gap_us"] - (1.0 - 0.8) / 2) < 1e-12, (
        "echo gap = (tau - 8*sigma)/2: " + f"gap {p_echo['gap_us']}"
    )
    assert any("null" in w.lower() for w in p_echo["warnings"]), "echo warns it is a null control"

    p_flip = plan_parity_mapping(0.5, 0.1, flip_final_pi2=True)
    assert p_flip["final_pi2_phase_deg"] == 0, "flip final pi/2 phase 0 deg"
    p_sym = plan_parity_mapping(0.5, 0.1, symmetric_ramsey=True)
    assert p_sym["final_pi2_phase_deg"] == 90, "symmetric final pi/2 phase 90 deg"
    p_symflip = plan_parity_mapping(0.5, 0.1, symmetric_ramsey=True, flip_final_pi2=True)
    assert p_symflip["final_pi2_phase_deg"] == 270, "symmetric+flip phase 270 deg"
    assert p_sym["drive_freq_offset_mhz"] == -0.25, "symmetric drive offset = -df/2"
    assert p_sym["branch_detuning_mhz"] == 0.25 and p["branch_detuning_mhz"] == 0.5, (
        "symmetric halves the branch detuning"
    )

    p_bad = plan_parity_mapping(2.0, 0.1)  # tau=0.25 us < 4*sigma=0.4 us
    assert not p_bad["feasible"] and p_bad["errors"], (
        "unreachable df -> infeasible with error: "
        + (p_bad["errors"][0][:90] if p_bad["errors"] else "")
    )
    assert abs(p_bad["df_max_mhz"] - 1.0 / 0.8) < 1e-12, "df_max = 1/(8*sigma) (no pi)"

    # Bandwidth-marginal standard scheme recommends symmetric.
    p_marg = plan_parity_mapping(0.5, 0.5)  # rabi ~0.2 MHz, ratio ~2.5 > 1
    assert (
        not p_marg["feasible"]
        and p_marg["recommend_symmetric"]
        and any("symmetric" in e for e in p_marg["errors"])
    ), "bandwidth-infeasible standard scheme fails and suggests symmetric"

    base = {"f_ge": 3055.2, "df": 0.5, "sigma": 0.1, "pi2_gain": 2375, "pi_gain": 4600}
    variants = build_control_variants(base)
    by = {v["control_type"]: v for v in variants}
    assert set(by) == set(MR_CONTROL_TYPE_CODES), "all six variants built"
    assert by["parity"]["cfg"]["df"] == 0.5 and not by["parity"]["cfg"].get(
        "flip_final_pi2", False
    ), "parity variant unmodified"
    assert by["flip_final_pi2"]["cfg"]["flip_final_pi2"] is True, "flip variant sets flip_final_pi2"
    assert by["echo_null"]["cfg"]["use_pi_pulse"] is True, "echo variant sets use_pi_pulse"
    assert (
        by["tau_offset"]["cfg"]["df"] == 0.5
        and abs(by["tau_offset"]["cfg"]["ramsey_tau_us"] - 2.0) < 1e-12
    ), "tau_offset changes programmed tau (default: the even harmonic 2/(2 df)), not physical df"
    assert (
        by["drive_detuned"]["cfg"]["f_ge"] == 3055.2
        and abs(by["drive_detuned"]["cfg"]["ramsey_drive_freq_mhz"] - 3055.7) < 1e-9
    ), "detuned variant changes drive, not physical f_ge"
    assert by["drive_off"]["cfg"]["pi2_gain"] == 0, "drive_off variant zeroes pi2_gain"
    assert all(
        v["cfg"] is None or v["cfg"]["mr_control_type"] == v["control_type"] for v in variants
    ), "every variant stamps mr_control_type"
    assert base.get("flip_final_pi2") is None and base["df"] == 0.5, "base cfg not mutated"

    # Echo infeasible at large df: returned as skipped, not raised.
    base_tight = dict(base, df=1.0)  # tau=0.5 us, echo needs > 0.8 us
    v_tight = build_control_variants(base_tight, include=("echo_null",))
    assert v_tight[0]["cfg"] is None and v_tight[0]["skip_reason"], (
        "infeasible echo variant skipped with reason"
    )


# ---------------------------------------------------------------------------
# 8. Reset validation + bin-size stability + end-to-end record
# ---------------------------------------------------------------------------


def test_reset_and_binsize():
    cal = _make_cal(0.0, 4.0, 1.0, seed=17)
    rng = np.random.default_rng(18)
    n_shots = 4000

    def cloud(p_excited):
        exc = rng.random(n_shots) < p_excited
        I = np.where(exc, rng.normal(4.0, 1.0, n_shots), rng.normal(0.0, 1.0, n_shots))
        Q = rng.normal(0.0, 1.0, n_shots)
        return I, Q

    # Readout k measures the state before flip k: 40% excited thermally,
    # then 5%, then 1% after successive resets.
    rows = [cloud(0.40), cloud(0.05), cloud(0.01)]
    reset_I = np.stack([r[0] for r in rows])
    reset_Q = np.stack([r[1] for r in rows])
    out = reset_success_vs_cycle(reset_I, reset_Q, cal)
    assert np.all(np.diff(out["g_fraction"]) > 0), (
        "g-fraction increases with reset cycle: " + f"fractions {np.round(out['g_fraction'], 3)}"
    )
    assert out["converged"] is None and out["n_resets_observed"] == 2 and out["warnings"], (
        "saved rows do not claim final reset convergence: " + str(out["warnings"])
    )
    assert np.allclose(
        out["validated_after_reset_g_fraction"], out["pre_correction_g_fraction"][1:]
    ), "row k validates only preceding corrections"

    post_I, post_Q = cloud(0.01)
    verified = reset_success_vs_cycle(
        reset_I, reset_Q, cal, post_reset_I=post_I, post_reset_Q=post_Q
    )
    assert verified["converged"] is True and verified["final_ground_fraction"] > 0.9, (
        "explicit post-reset readout can establish convergence"
    )

    bad = reset_success_vs_cycle(reset_I[:1], reset_Q[:1], cal)
    assert bad["converged"] is None and bad["n_resets_observed"] == 0 and bad["warnings"], (
        "single pre-correction row cannot validate reset: "
        + (bad["warnings"][0][:80] if bad["warnings"] else "")
    )

    sim = simulate_telegraph_trace(
        60000, 20e-6, 300.0, 300.0, mu0=0.0, mu1=3.0, sigma0=1.0, sigma1=1.0, seed=19
    )
    rvb = rate_vs_bin_size(sim["v"], 20e-6, threshold=1.5, bin_sizes=(1, 2, 4, 8, 16))
    rates = np.array(rvb["rate_hz"])
    assert np.all(np.isfinite(rates)), "bin-size sweep produced finite rates: " + str(
        np.round(rates, 1)
    )
    # Raw single-shot threshold crossings include noise flips; after modest
    # binning the rate should settle toward the true total switch rate.
    assert abs(rates[2] - 300.0) / 300.0 < 0.5, (
        "binned rate settles near true rate (300 Hz total): " + f"rate at bin=4: {rates[2]:.1f} Hz"
    )


def test_end_to_end():
    cal = _make_cal(0.0, 4.0, 1.0, seed=20)
    gamma = 200.0  # 2.5 ms dwell: the documented BFC operating point
    dt = 20e-6
    n = 60000  # 1.2 s
    mu0p, mu1p = cal["proj_g_mean"], cal["proj_e_mean"]
    sim = simulate_telegraph_trace(
        n,
        dt,
        gamma,
        gamma,
        mu0=mu0p,
        mu1=mu1p,
        sigma0=cal["proj_g_sigma"],
        sigma1=cal["proj_e_sigma"],
        seed=21,
    )
    # Rebuild I/Q from the projected trace so the projection round-trips:
    # v = ((IQ - midpoint) @ axis), place samples along the axis.
    axis = cal["axis"]
    mid = cal["midpoint"]
    I = mid[0] + sim["v"] * axis[0]
    Q = mid[1] + sim["v"] * axis[1]

    res = analyze_modified_ramsey_record(
        I,
        Q,
        dt,
        cal,
        drift_timescale_s=0.2,
        expected_dwell_s=1.0 / gamma,
        symmetric_hmm=True,
        mapping_probabilities=(0.0, 1.0),
        out_dir=None,
        save_plots=False,
        save_sidecars=False,
    )
    s = res["summary"]
    assert s["identifiable"], "identifiable end-to-end: " + str(
        res["hmm"]["unidentifiable_reasons"]
    )
    assert close(s["gamma01_hz"], gamma, 0.25), (
        "gamma within 25% of 200 Hz (2.5 ms dwell): "
        + f"HMM {s['gamma01_hz']:.1f} Hz, ACF {s['acf_gamma_hz']:.1f}, "
        f"PSD {s['psd_gamma_hz']:.1f}"
    )
    assert not any("disagree" in w for w in s["warnings"]), (
        "estimators agree (no disagreement warning): " + str(s["warnings"])
    )
    assert close(res["hmm"]["dwell_mean_s"]["state0"], 1 / gamma, 0.3) or close(
        res["hmm"]["dwell_mean_s"]["state1"], 1 / gamma, 0.3
    ), "dwell ~2.5 ms recovered from Viterbi: " + f"dwells {res['hmm']['dwell_mean_s']}"

    # Zero-contrast end-to-end must come out unidentifiable, not with a rate.
    rng = np.random.default_rng(22)
    I0 = mid[0] + rng.normal(0, 1.0, 30000) * axis[0]
    Q0 = mid[1] + rng.normal(0, 1.0, 30000) * axis[1]
    cal0 = _make_cal(0.0, 0.02, 1.0, seed=23)  # overlapping calibration
    res0 = analyze_modified_ramsey_record(
        I0,
        Q0,
        dt,
        cal0,
        mapping_probabilities=(0.0, 1.0),
        out_dir=None,
        save_plots=False,
        save_sidecars=False,
    )
    assert not res0["summary"]["identifiable"] and math.isnan(res0["summary"]["gamma01_hz"]), (
        "zero-contrast record -> unidentifiable end-to-end"
    )

    gate = assess_parity_record(
        calibration=cal0, hmm=res0["hmm"], acf=res0["acf"], psd=res0["psd"], drift=res0["drift"]
    )
    assert not gate["clean"], "quality gates carry the warnings"


def test_imperfect_mapping_and_bad_samples():
    rng = np.random.default_rng(24)
    gamma = 250.0
    dt = 20e-6
    n = 50000
    hidden = simulate_telegraph_trace(
        n, dt, gamma, gamma, mu0=0.0, mu1=1.0, sigma0=1e-9, sigma1=1e-9, seed=25
    )["states"]
    p0, p1 = 0.15, 0.85
    prepared_e = rng.random(n) < np.where(hidden == 0, p0, p1)
    v = rng.normal(np.where(prepared_e, 4.0, 0.0), 1.0)
    emissions = {
        "model": "ge_mixture",
        "mu_g": 0.0,
        "mu_e": 4.0,
        "sigma_g": 1.0,
        "sigma_e": 1.0,
        "p_e_state0": p0,
        "p_e_state1": p1,
    }
    fit = fit_two_state_hmm(v, dt, emissions, symmetric=True)
    assert fit["identifiable"], "imperfect-mapping mixture is identifiable: " + str(
        fit["unidentifiable_reasons"]
    )
    assert close(fit["gamma01_hz"], gamma, 0.25), (
        "mixture model recovers switching rate: " + f"fit {fit['gamma01_hz']:.1f} vs {gamma}"
    )

    v_bad = v.copy()
    v_bad[10] = np.nan
    try:
        fit_two_state_hmm(v_bad, dt, emissions, symmetric=True)
        rejected = False
    except ValueError:
        rejected = True
    assert rejected, "direct HMM rejects non-finite samples"

    cal = _make_cal(0.0, 4.0, 1.0, seed=26)
    axis, mid = cal["axis"], cal["midpoint"]
    I = mid[0] + v * axis[0]
    Q = mid[1] + v * axis[1]
    I[100] = np.nan
    analyzed = analyze_modified_ramsey_record(
        I,
        Q,
        dt,
        cal,
        mapping_probabilities=(p0, p1),
        out_dir=None,
        save_plots=False,
        save_sidecars=False,
    )
    assert analyzed["summary"]["n_samples_removed_nonfinite"] == 1, (
        "end-to-end analysis jointly filters bad IQ"
    )
    assert (
        not analyzed["summary"]["uniform_timing"]
        and not analyzed["acf"]["fit_ok"]
        and not analyzed["psd"]["fit_ok"]
        and any("nonuniform" in w for w in analyzed["summary"]["warnings"])
    ), "gap forces exact-time HMM and skips uniform estimators"


def test_plot_and_sidecar_paths():
    """Exercise save_plots=True end to end.

    Every other end-to-end test passes save_plots=False, so the plotting
    helpers were never run against the "ge_mixture" emission spec that
    analyze_modified_ramsey_record ALWAYS builds. _plot_hmm indexed em["mu0"],
    which only exists on the plain-Gaussian spec, so every real run that saved
    plots died with KeyError: 'mu0' after acquisition.
    """
    import tempfile

    cal = _make_cal(0.0, 4.0, 1.0, seed=31)
    gamma, dt, n = 200.0, 20e-6, 30000
    sim = simulate_telegraph_trace(
        n,
        dt,
        gamma,
        gamma,
        mu0=cal["proj_g_mean"],
        mu1=cal["proj_e_mean"],
        sigma0=cal["proj_g_sigma"],
        sigma1=cal["proj_e_sigma"],
        seed=32,
    )
    axis, mid = cal["axis"], cal["midpoint"]
    I = mid[0] + sim["v"] * axis[0]
    Q = mid[1] + sim["v"] * axis[1]

    with tempfile.TemporaryDirectory() as td:
        # identifiable record, plots + sidecars ON (the production call shape)
        res = analyze_modified_ramsey_record(
            I,
            Q,
            dt,
            cal,
            expected_dwell_s=1.0 / gamma,
            mapping_probabilities=(0.1, 0.9),
            out_dir=td,
            base_name="plt",
            save_plots=True,
            save_sidecars=True,
        )
        assert res["hmm"]["emissions_used"]["model"] == "ge_mixture", (
            "ge_mixture record renders plots without KeyError"
        )
        written = sorted(os.listdir(td))
        for suffix in (
            "_hmm.png",
            "_calibration.png",
            "_projected_trace.png",
            "_acf_psd.png",
            "_rate_vs_bin.png",
            "_dwells.png",
            "_analysis.json",
        ):
            assert f"plt{suffix}" in written, f"wrote plt{suffix}" + ": " + str(written)
        assert all(os.path.getsize(os.path.join(td, f)) > 0 for f in written), (
            "every written plot is non-empty: " + str(written)
        )

    # an UNIDENTIFIABLE record must also render (rates withheld -> nan title)
    with tempfile.TemporaryDirectory() as td:
        rng = np.random.default_rng(33)
        cal0 = _make_cal(0.0, 0.02, 1.0, seed=34)
        I0 = cal0["midpoint"][0] + rng.normal(0, 1.0, 20000) * cal0["axis"][0]
        Q0 = cal0["midpoint"][1] + rng.normal(0, 1.0, 20000) * cal0["axis"][1]
        res0 = analyze_modified_ramsey_record(
            I0,
            Q0,
            dt,
            cal0,
            mapping_probabilities=(0.1, 0.9),
            out_dir=td,
            base_name="unid",
            save_plots=True,
            save_sidecars=True,
        )
        assert not res0["summary"]["identifiable"] and "unid_hmm.png" in os.listdir(td), (
            "unidentifiable record still renders plots"
        )

    # the plain-Gaussian emission spec must keep working through _plot_hmm
    with tempfile.TemporaryDirectory() as td:
        em = {
            "mu0": cal["proj_g_mean"],
            "mu1": cal["proj_e_mean"],
            "sigma0": cal["proj_g_sigma"],
            "sigma1": cal["proj_e_sigma"],
        }
        fit = fit_two_state_hmm(sim["v"], dt, em, symmetric=True)
        from qicklab.analysis.modified_ramsey import _plot_hmm

        path = os.path.join(td, "gauss_hmm.png")
        _plot_hmm(sim["t_s"], sim["v"], fit, path)
        assert (
            fit["emissions_used"].get("model", "gaussian") == "gaussian"
            and os.path.getsize(path) > 0
        ), "plain-Gaussian emission spec still plots"


def test_controls_require_evidence():
    main = {
        "label": "parity",
        "hmm": {"identifiable": True},
        "acf": {"amplitude": 1.0},
        "occupancy_state1": 0.3,
    }
    missing_flip = {
        "control_type": "flip_final_pi2",
        "hmm": {"identifiable": True},
        "acf": {"amplitude": 0.9},
    }
    missing_echo = {
        "control_type": "echo_null",
        "hmm": {"identifiable": True},
        "acf": {"amplitude": float("nan")},
    }
    result = compare_parity_controls(main, [missing_flip, missing_echo])
    assert result["controls"][0]["checked"] is False, "missing flip occupancy fails"
    assert result["controls"][1]["checked"] is False, "missing echo suppression evidence fails"
    assert result["all_expected"] is False, "missing evidence cannot produce all-expected verdict"
    assert compare_parity_controls(main, [])["all_expected"] is False, (
        "no controls cannot produce all-expected verdict"
    )


# ---------------------------------------------------------------------------
# 9. Acquisition-side buffer striding and schedule ledger (mocked program)
# ---------------------------------------------------------------------------


def test_program_buffer_and_ledger():
    from qicklab.experiments.modified_ramsey import (
        ModifiedRamseyProgram,
    )

    reps, n_reset = 5, 2
    reads_per_rep = n_reset + 1
    prog = ModifiedRamseyProgram.__new__(ModifiedRamseyProgram)
    prog.cfg = {"ro_chs": [0], "readout_length": 1.0, "reps": reps}
    prog.reset_cycles = n_reset
    prog.reads_per_rep = reads_per_rep
    prog.us2cycles = lambda *a, **k: 10  # norm = 10

    # Buffer layout: rep r contributes [reset0, reset1, final] sequentially.
    # Encode readout k of rep r as 100*r + k so the striding is checkable.
    raw = np.array([100 * r + k for r in range(reps) for k in range(reads_per_rep)], dtype=float)
    prog.di_buf = [raw]
    prog.dq_buf = [raw + 0.5]

    si, sq = prog.collect_shots()
    assert np.array_equal(si.ravel() * 10, np.array([2.0, 102.0, 202.0, 302.0, 402.0])), (
        "collect_shots keeps only the FINAL readout of each rep"
    )
    ri, rq = prog.collect_reset_shots()
    assert ri.shape == (n_reset, reps) and rq.shape == (n_reset, reps), (
        "reset shots shape (reset_cycles, reps)"
    )
    assert np.array_equal(
        ri[0] * 10, np.array([0.0, 100.0, 200.0, 300.0, 400.0])
    ) and np.array_equal(ri[1] * 10, np.array([1.0, 101.0, 201.0, 301.0, 401.0])), (
        "reset row k holds readout k of every rep"
    )

    # No reset: empty (0, reps) arrays.
    prog.reset_cycles = 0
    ri0, _ = prog.collect_reset_shots()
    assert ri0.shape == (0, reps), "no-reset reset_shots empty with stable shape"

    # Schedule ledger: synci immediates plus one r_wait sync per Ramsey gap.
    prog.wait_cycles = 37
    prog.prog_list = [
        {"name": "regwi", "args": [0, 3, 37]},
        {"label": "LOOP_J", "name": "synci", "args": [100]},
        {"name": "set", "args": [1, 0, 0, 0, 0, 0, 0, 7]},
        {"name": "sync", "args": [0, 3]},
        {"name": "synci", "args": [250]},
        {"name": "seti", "args": [0, 0, 0, 0]},
        {"name": "synci", "args": [13]},
        {"name": "loopnz", "args": [0, 15, "LOOP_J"]},
        {"name": "synci", "args": [999]},  # outside the rep loop: ignored
    ]
    assert prog.scheduled_rep_period_cycles() == 100 + 37 + 250 + 13, (
        "ledger sums synci + r_wait syncs inside LOOP_J only: "
        + f"got {prog.scheduled_rep_period_cycles()}"
    )


def test_forward_backward_consistency():
    sim = simulate_telegraph_trace(
        3000, 20e-6, 400.0, 400.0, mu0=0.0, mu1=3.0, sigma0=1.0, sigma1=1.0, seed=24
    )
    fb = hmm_forward_backward(sim["v"], np.full(2999, 20e-6), 400.0, 400.0, 0.0, 3.0, 1.0, 1.0)
    assert np.allclose(fb["posteriors"].sum(axis=1), 1.0, atol=1e-9), "posteriors normalized"
    # Likelihood must be invariant to which end the recursion starts from:
    # logsumexp(alpha_t + beta_t) is constant in t.
    lse = np.logaddexp(
        fb["log_alpha"][:, 0] + fb["log_beta"][:, 0], fb["log_alpha"][:, 1] + fb["log_beta"][:, 1]
    )
    assert np.allclose(lse, fb["loglik"], atol=1e-6), (
        "alpha*beta constant across t (stable log-space recursion): "
        + f"max dev {np.max(np.abs(lse - fb['loglik'])):.2e}"
    )
    vit = hmm_viterbi(sim["v"], np.full(2999, 20e-6), 400.0, 400.0, 0.0, 3.0, 1.0, 1.0)
    agree = np.mean(vit == sim["states"])
    assert agree > 0.9, "Viterbi ~ truth on clean data: " + f"agreement {agree:.3f}"


# ---------------------------------------------------------------------------
# 10. Control verdicts on realistic records (F16): echo null, flip inversion,
#     drive_off carryover. Records go through analyze_modified_ramsey_record,
#     so the model-free lag-covariance statistic is the one the runner sees.
# ---------------------------------------------------------------------------

_CTL_DT = 262e-6  # 250 us relax + readout: the CSTQ03 cadence after the T1 fix
_CTL_N = 20000  # 5.2 s
_CTL_CAL = _make_cal(0.0, 2.0, 1.0, seed=70)  # readout SNR 2


def _ctl_record(seed, prob_e, label, control_type=None, mapping=(0.1, 0.9), symmetric=True):
    """Analyse g/e shots with per-shot P(e) = prob_e through the full pipeline."""
    return _ctl_record_v(_ctl_shots(seed, prob_e), label, control_type, mapping, symmetric)


def _ctl_shots(seed, prob_e):
    """Projected g/e shots (readout SNR 2) with per-shot P(e) = prob_e."""
    rng = np.random.default_rng(seed)
    prepared_e = rng.random(_CTL_N) < prob_e
    return rng.normal(np.where(prepared_e, _CTL_CAL["proj_e_mean"], _CTL_CAL["proj_g_mean"]), 1.0)


def _ctl_record_v(v, label, control_type=None, mapping=(0.1, 0.9), symmetric=True):
    """Analyse the projected trace v through the full pipeline."""
    axis, mid = _CTL_CAL["axis"], _CTL_CAL["midpoint"]
    res = analyze_modified_ramsey_record(
        mid[0] + v * axis[0],
        mid[1] + v * axis[1],
        _CTL_DT,
        _CTL_CAL,
        symmetric_hmm=symmetric,
        mapping_probabilities=mapping,
        save_plots=False,
        save_sidecars=False,
    )
    d = {
        "label": label,
        "hmm": res["hmm"],
        "acf": res["acf"],
        "occupancy_state1": res["summary"]["occupancy_state1"],
    }
    if control_type:
        d["control_type"] = control_type
    return d


def _telegraph_prob_e(seed, g01, g10, p_state0, p_state1):
    hidden = simulate_telegraph_trace(
        _CTL_N, _CTL_DT, g01, g10, mu0=0.0, mu1=1.0, sigma0=1e-9, sigma1=1e-9, seed=seed
    )["states"]
    return np.where(hidden == 0, p_state0, p_state1)


def _verdict(main, control):
    out = compare_parity_controls(main, [control])
    return out["controls"][0], out["all_expected"]


def _lag_stat(value, sd, n_boot=1000, seed=0):
    """A lagged_autocovariance_sum result with Gaussian bootstrap replicates."""
    boot = np.random.default_rng(seed).normal(value, sd, n_boot)
    return {"available": True, "value": value, "boot": boot, "max_lag": 10, "reason": ""}


def _dict_record(lag_value, lag_sd, seed, control_type=None, amplitude=0.5, hmm=None, occ1=0.5):
    d = {
        "label": control_type or "parity",
        "hmm": hmm if hmm is not None else {"identifiable": True},
        "acf": {
            "amplitude": amplitude,
            "lag_covariance_sum": _lag_stat(lag_value, lag_sd, seed=seed),
        },
        "occupancy_state1": occ1,
    }
    if control_type:
        d["control_type"] = control_type
    return d


def test_lagged_autocovariance_sum():
    rng = np.random.default_rng(71)
    white = rng.standard_normal(40000)
    st = lagged_autocovariance_sum
    out = st(white, 10)
    assert out["available"] and out["n_blocks"] >= 20 and out["block_len"] == 100, out
    lo, hi = np.percentile(out["boot"], [2.5, 97.5])
    assert lo < 0 < hi, f"white noise: CI [{lo:.3f}, {hi:.3f}] covers 0"
    # AR(1) with phi = 0.5, unit innovations: C(k) = phi^k / (1 - phi^2).
    ar = np.zeros(40000)
    for i in range(1, ar.size):
        ar[i] = 0.5 * ar[i - 1] + white[i]
    expected = sum(0.5**k for k in range(1, 11)) / 0.75
    got = st(ar, 10)["value"]
    assert close(got, expected, 0.1), f"AR(1) lag sum {got:.3f} vs {expected:.3f}"
    short = st(white[:300], 10)
    assert not short["available"] and "too short" in short["reason"], short


def test_control_verdicts_echo_null():
    main = _ctl_record(72, _telegraph_prob_e(73, 200.0, 200.0, 0.1, 0.9), "parity")
    assert main["hmm"]["identifiable"], main["hmm"]["unidentifiable_reasons"]
    # Ideal echo null: i.i.d. shots, any P(e). P(e) = 0.5 was FAILED before F06/F16
    # (ACF fit failure -> amplitude ratio nan).
    for k, p_e in enumerate((0.5, 0.0, 0.03, 0.1, 0.2)):
        echo = _ctl_record(80 + k, p_e, f"echo{p_e}", "echo_null")
        entry, all_expected = _verdict(main, echo)
        assert entry["checked"] is True and all_expected, f"P(e)={p_e}: " + entry["note"]
        assert entry["lag_cov_ratio_upper95"] < 0.25, entry
    # An echo that did NOT refocus (the telegraph survives) fails.
    leaky = _ctl_record(90, _telegraph_prob_e(91, 200.0, 200.0, 0.1, 0.9), "leaky", "echo_null")
    entry, all_expected = _verdict(main, leaky)
    assert entry["checked"] is False and not all_expected, entry["note"]
    # A partially refocused echo (mapping 0.29/0.71, lag ratio ~0.3): with the mapping fixed
    # at the parity record's, the HMM locked onto a fast rate ("switching unresolved"); with
    # the fitted mapping (F30) the emission gate withholds it. Neither gate is null evidence;
    # the lag statistic (upper bound > 0.25) fails it.
    for s in (200, 202):
        partial = _ctl_record(
            s, _telegraph_prob_e(s + 1, 200.0, 200.0, 0.29, 0.71), "partial", "echo_null"
        )
        entry, _ = _verdict(main, partial)
        assert entry["checked"] is False, entry["note"]
        assert entry["lag_cov_ratio_upper95"] > 0.25, entry

    # A 400 Hz parity record stays identifiable and still validates the echo.
    main400 = _ctl_record(92, _telegraph_prob_e(93, 400.0, 400.0, 0.1, 0.9), "parity400")
    assert main400["hmm"]["identifiable"], main400["hmm"]["unidentifiable_reasons"]
    entry, _ = _verdict(main400, _ctl_record(94, 0.5, "echo", "echo_null"))
    assert entry["checked"] is True, entry["note"]

    # An ACF fit failure by itself (e.g. non-uniform timing) is not null evidence.
    no_evidence = {
        "control_type": "echo_null",
        "hmm": {"identifiable": False, "unidentifiable_reasons": ["HMM optimization failed"]},
        "acf": {"amplitude": float("nan"), "fit_ok": False},
    }
    entry, _ = _verdict(main, no_evidence)
    assert entry["checked"] is False, entry["note"]

    # The model-free statistic vetoes the HMM's i.i.d. verdict when the surviving
    # correlation is significantly above the threshold (5% lower bound >= 0.25).
    iid = {"identifiable": False, "unidentifiable_reasons": ["uncorrelated (i.i.d.) shots"]}
    dmain = _dict_record(1.0, 0.05, seed=1)
    entry, _ = _verdict(dmain, _dict_record(0.5, 0.05, 2, "echo_null", hmm=iid))
    assert entry["checked"] is False and "survived" in entry["note"], entry["note"]
    # ... but a noisy, inconclusive lag statistic leaves the i.i.d. verdict standing.
    entry, _ = _verdict(dmain, _dict_record(0.3, 0.3, 3, "echo_null", hmm=iid))
    assert entry["checked"] is True, entry["note"]
    # Without the i.i.d. verdict, the echo passes on the lag statistic only when its
    # 95% UPPER bound is below 0.25, not merely its point estimate: lag ratio
    # 0.2 +- 0.05 is neither bounded below nor significantly above the threshold.
    not_iid = {"identifiable": True}
    entry, all_expected = _verdict(dmain, _dict_record(0.2, 0.05, 5, "echo_null", hmm=not_iid))
    assert entry["lag_cov_ratio"] < 0.25 < entry["lag_cov_ratio_upper95"], entry
    assert "survived" not in entry["note"], entry["note"]
    assert entry["checked"] is False and not all_expected, entry["note"]
    entry, _ = _verdict(dmain, _dict_record(0.05, 0.02, 6, "echo_null", hmm=not_iid))
    assert entry["checked"] is True, entry["note"]


def test_control_verdicts_flip():
    # Balanced parity occupancy (the expected symmetric case): a flip record whose
    # mapping did NOT invert was PASSED before F16 (0.50 vs 1 - 0.49).
    main = _ctl_record(100, _telegraph_prob_e(101, 200.0, 200.0, 0.1, 0.9), "parity")
    noflip = _ctl_record(
        102, _telegraph_prob_e(103, 200.0, 200.0, 0.1, 0.9), "noflip", "flip_final_pi2"
    )
    assert abs(main["occupancy_state1"] - 0.5) < 0.15, main["occupancy_state1"]
    entry, all_expected = _verdict(main, noflip)
    assert entry["checked"] is not True and not all_expected, entry
    assert entry["verdict"] == "inversion uninformative", entry["note"]
    # Same, but the "flip" telegraph runs at 3x the rate: the rate check fails it.
    fast = _ctl_record(
        104, _telegraph_prob_e(105, 600.0, 600.0, 0.1, 0.9), "fast", "flip_final_pi2"
    )
    entry, _ = _verdict(main, fast)
    assert entry["checked"] is False, entry["note"]

    # Imbalanced parity occupancy 0.3: the inversion is informative.
    g01, g10 = 120.0, 280.0  # occ1 = 120 / 400 = 0.3
    main3 = _ctl_record(106, _telegraph_prob_e(107, g01, g10, 0.1, 0.9), "parity", symmetric=False)
    assert abs(main3["occupancy_state1"] - 0.3) < 0.1, main3["occupancy_state1"]
    inverted = _ctl_record(
        108,
        _telegraph_prob_e(109, g01, g10, 0.9, 0.1),  # closing pi/2 flipped: mapping swapped
        "flip",
        "flip_final_pi2",
        symmetric=False,
    )
    entry, all_expected = _verdict(main3, inverted)
    assert entry["checked"] is True and all_expected, entry["note"]
    not_inverted = _ctl_record(
        110, _telegraph_prob_e(111, g01, g10, 0.1, 0.9), "flip", "flip_final_pi2", symmetric=False
    )
    entry, _ = _verdict(main3, not_inverted)
    assert entry["checked"] is False, entry["note"]

    # Rate drift between the parity and flip records (100k-shot statistical errors):
    # 15% is many sigma but within FLIP_RATE_MAX_RATIO = 2, so an inverted flip
    # still passes; a 3x rate is a different process and fails.
    def hmm(g, err=2.5):
        return {
            "identifiable": True,
            "symmetric": True,
            "gamma01_hz": g,
            "gamma10_hz": g,
            "gamma01_err_hz": err,
            "gamma10_err_hz": err,
        }

    rmain = {"hmm": hmm(200.0), "acf": {"amplitude": 0.5}, "occupancy_state1": 0.3}
    for g_flip, expect in ((230.0, True), (170.0, True), (600.0, False), (90.0, False)):
        flip = {
            "control_type": "flip_final_pi2",
            "hmm": hmm(g_flip),
            "acf": {"amplitude": 0.5},
            "occupancy_state1": 0.7,
        }
        entry, _ = _verdict(rmain, flip)
        assert entry["checked"] is expect, f"{g_flip} Hz: " + entry["note"]

    # hmm.py can return identifiable rates with NaN errors (singular Hessian): the
    # factor-of-2 rule then decides alone, so equal rates still pass.
    nan = float("nan")
    for g_flip, expect in ((200.0, True), (300.0, True), (600.0, False)):
        flip = {
            "control_type": "flip_final_pi2",
            "hmm": hmm(g_flip, err=nan),
            "acf": {"amplitude": 0.5},
            "occupancy_state1": 0.7,
        }
        entry, all_expected = _verdict(rmain, flip)
        assert entry["checked"] is expect and all_expected is expect, (
            f"{g_flip} Hz, NaN errors: " + entry["note"]
        )
        assert "rate errors unavailable" in entry["note"], entry["note"]


def test_control_verdicts_drive_off():
    main = {
        "label": "parity",
        "hmm": {"identifiable": True},
        "acf": {"amplitude": 0.004582},
        "occupancy_state1": 0.5,
    }
    # CSTQ03 Q2 2026-08-04: drive_off showed 2.4x the parity ACF amplitude.
    carry = {"control_type": "drive_off", "hmm": {}, "acf": {"amplitude": 0.011050}}
    entry, all_expected = _verdict(main, carry)
    assert entry["checked"] is False and not all_expected, entry["note"]
    assert "carryover" in entry["note"], entry["note"]
    clean = {"control_type": "drive_off", "hmm": {}, "acf": {"amplitude": 0.05 * 0.004582}}
    entry, all_expected = _verdict(main, clean)
    assert entry["checked"] is True and all_expected, entry["note"]

    # Full pipeline: a clean drive_off (i.i.d., P(e) = 0.02, ACF fit typically fails)
    # passes on the lag statistic; T1 carryover (79% of the previous shot's
    # excitation survives) is flagged.
    parity = _ctl_record(112, _telegraph_prob_e(113, 200.0, 200.0, 0.1, 0.9), "parity")
    entry, _ = _verdict(parity, _ctl_record(114, 0.02, "off", "drive_off"))
    assert entry["checked"] is True, entry["note"]
    rng = np.random.default_rng(115)
    p_e = np.empty(_CTL_N)
    excited = False
    for i in range(_CTL_N):
        p_e[i] = 0.79 if excited else 0.02
        excited = rng.random() < p_e[i]
    entry, _ = _verdict(parity, _ctl_record(116, p_e, "carry", "drive_off"))
    assert entry["checked"] is False and "carryover" in entry["note"], entry["note"]

    # Lag statistic, symmetric three-way rule: 95% upper bound < 0.1 -> passed;
    # 5% lower bound >= 0.1 -> failed; an interval straddling 0.1 (short or noisy
    # record) -> inconclusive, not decisive, whichever side the point estimate is on.
    dmain = _dict_record(1.0, 0.05, seed=1)
    for value, sd, expect, verdict in (
        (0.03, 0.02, True, "passed"),
        (0.25, 0.02, False, "failed"),
        (0.05, 0.10, None, "inconclusive"),
        (0.12, 0.10, None, "inconclusive"),
    ):
        entry, all_expected = _verdict(dmain, _dict_record(value, sd, 4, "drive_off"))
        assert entry["checked"] is expect and entry["verdict"] == verdict, entry
        assert all_expected is (expect is True), entry

    # No correlation evidence at all (lag statistic unavailable, ACF amplitude nan):
    # inconclusive, not failed.
    blind = {
        "control_type": "drive_off",
        "hmm": {},
        "acf": {
            "amplitude": float("nan"),
            "lag_covariance_sum": {"available": False, "reason": "record too short"},
        },
    }
    entry, all_expected = _verdict(dmain, blind)
    assert entry["checked"] is None and entry["verdict"] == "inconclusive", entry
    assert "no correlation evidence" in entry["note"] and not all_expected, entry["note"]


def test_lag_statistic_ignores_drift_window_edges():
    # remove_slow_drift's rolling mean (mode="nearest") repeats the end samples over
    # half a window, leaking a common ramp into the first/last ~W/2 shots. A clean
    # drive_off whose first and last shots read high (5.0, 2.5 sigma above the e
    # mean) must still pass: the lag statistic uses the interior only.
    v = _ctl_shots(117, 0.02)
    v[0] = v[-1] = 5.0
    off = _ctl_record_v(v, "off", "drive_off")
    lag = off["acf"]["lag_covariance_sum"]
    drift = remove_slow_drift(v, _CTL_DT, 0.2, expected_dwell_s=2.5e-3)
    assert lag["edge_trim_samples"] == drift["window_samples"] // 2 > 0, lag
    parity = _ctl_record(118, _telegraph_prob_e(119, 200.0, 200.0, 0.25, 0.75), "parity")
    main_value = parity["acf"]["lag_covariance_sum"]["value"]
    # On the full corrected trace the edge ramp alone exceeds the drive_off budget.
    full = lagged_autocovariance_sum(drift["v_corrected"], lag["max_lag"])["value"]
    assert full > 0.3 * main_value, f"edge bias {full:.3f} vs parity {main_value:.3f}"
    assert abs(lag["value"]) < 0.05 * main_value, f"interior lag sum {lag['value']:.3f}"
    entry, all_expected = _verdict(parity, off)
    assert entry["checked"] is True and all_expected, entry["note"]


def _weak_lag_record(seed, n, a, control_type=None, hmm=None):
    """Unit-variance noise plus a 400 Hz symmetric telegraph of step a (normalised ACF
    amplitude A = (a/2)^2 / (1 + (a/2)^2)), drift-corrected and reduced to the lag
    statistic exactly as analyze_modified_ramsey_record does (the 100k-shot HMM fit
    is skipped: these records are compared on the lag statistic only)."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(n)
    if a:
        tel = simulate_telegraph_trace(
            n, _CTL_DT, 400.0, 400.0, 0.0, 1.0, 1e-9, 1e-9, seed=seed + 10_000
        )["states"]
        v = v + a * tel
    drift = remove_slow_drift(v, _CTL_DT, 0.2, expected_dwell_s=2.5e-3)
    lag = drift_corrected_lag_sum(drift["v_corrected"], drift["window_samples"], 10, seed=seed)
    d = {
        "label": control_type or "parity",
        "hmm": hmm if hmm is not None else {"identifiable": True},
        "acf": {"amplitude": 0.5, "lag_covariance_sum": lag},
        "occupancy_state1": 0.5,
    }
    if control_type:
        d["control_type"] = control_type
    return d


def test_lag_statistic_removes_drift_window_offset():
    # Subtracting a centred rolling mean of W samples puts a flat offset of about
    # -var/W on every lag: -var*K/W summed over lags 1..K (-0.013 at K = 10, W = 763),
    # comparable to a weak parity record's own lag sum. The baseline band (lags
    # 4K..8K) measures and removes it.
    k = 10
    raw, corrected = [], []
    for seed in range(16):
        lag = _weak_lag_record(400 + seed, 100_000, 0.0)["acf"]["lag_covariance_sum"]
        assert lag["baseline_lags"] == [40, 80] and lag["edge_trim_samples"] == 381, lag
        raw.append(lag["uncorrected_value"])
        corrected.append(lag["value"])
    w = remove_slow_drift(np.zeros(100), _CTL_DT, 0.2)["window_samples"]
    assert w == 763
    assert -1.5 * k / w < np.mean(raw) < -0.5 * k / w, f"uncorrected {np.mean(raw):.4f}"
    assert abs(np.mean(corrected)) < 0.3 * k / w, f"corrected {np.mean(corrected):.4f}"
    # The band is linear in the offset: an AR(1) process (decayed by lag 40) keeps its sum.
    ar = np.zeros(40000)
    white = np.random.default_rng(71).standard_normal(ar.size)
    for i in range(1, ar.size):
        ar[i] = 0.5 * ar[i - 1] + white[i]
    expected = sum(0.5**j for j in range(1, 11)) / 0.75
    got = lagged_autocovariance_sum(ar, 10, baseline_lags=(40, 80), drift_window=763)
    assert close(got["value"], expected, 0.1), f"AR(1) baseline-corrected {got['value']:.3f}"


def test_control_verdicts_weak_parity_contrast():
    # Weak parity contrast (normalised ACF amplitude A ~ 0.02, 100k shots): without the
    # baseline correction the drift-window offset pulled every control's lag ratio
    # down (a drive_off at true ratio 0.2 averaged ~ -0.06 over these records and
    # could pass). Per-record ratios scatter by ~0.15 at this contrast.
    a = 2 * math.sqrt(0.02 / 0.98)
    n = 100_000
    off_ratios = []
    for seed in range(8):
        main = _weak_lag_record(500 + 10 * seed, n, a)
        assert main["acf"]["lag_covariance_sum"]["available"]
        off = _weak_lag_record(501 + 10 * seed, n, a * math.sqrt(0.2), "drive_off")
        entry, all_expected = _verdict(main, off)
        assert entry["verdict"] != "passed" and not all_expected, entry
        off_ratios.append(entry["lag_cov_ratio"])
        echo = _weak_lag_record(502 + 10 * seed, n, a * math.sqrt(0.45), "echo_null")
        entry, _ = _verdict(main, echo)
        assert entry["checked"] is not True, entry
    assert 0.08 < np.mean(off_ratios) < 0.35, off_ratios

    # CSTQ03 Q2 2026-08-04 contrast (A ~ 0.0046) on 20k shots: the parity lag sum is
    # not significant, so no ratio can be formed. drive_off is then inconclusive; its
    # ACF amplitude (fitted noise on such a record, 0.47x the parity's here) no longer
    # decides.
    a = 2 * math.sqrt(0.0046 / 0.9954)
    main = _weak_lag_record(600, 20_000, a)
    off = _weak_lag_record(601, 20_000, 0.0, "drive_off")
    off["acf"]["amplitude"] = 0.47 * main["acf"]["amplitude"]
    entry, all_expected = _verdict(main, off)
    assert entry["checked"] is None and entry["verdict"] == "inconclusive", entry
    assert "no significant lag covariance" in entry["note"] and not all_expected, entry
