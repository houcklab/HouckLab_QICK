"""
F30: joint fit of the Ramsey mapping probabilities with the parity-switching rate
(fit_two_state_hmm(fit_mapping=True), the default of analyze_modified_ramsey_record).

With the mapping FIXED at an assumed (0.1, 0.9), a record whose real contrast is lower is
mis-modelled and the rate comes out several times fast with a small error bar (or is
withheld by the resolved-rate gate); fitting P(e|state0), P(e|state1) with the rate, the
readout clouds fixed at the calibration, recovers it. The emission-SNR gate
(min_emission_snr = 0.7, unchanged) is evaluated at the fitted mapping.

Hardware-free and seeded. Run from the repo root:
    python -m pytest tests/test_hmm_fit_mapping.py
"""

import math

import numpy as np
import pytest

from qicklab.analysis.hmm import fit_two_state_hmm
from qicklab.analysis.modified_ramsey import analyze_modified_ramsey_record
from qicklab.analysis.rates import simulate_telegraph_trace
from qicklab.analysis.readout import calibrate_readout_from_labeled_shots
from qicklab.experiments.modified_ramsey import (
    MAPPING_SEED_MIN_PREDICTED_CONTRAST,
    plan_parity_mapping,
    predicted_mapping_seed,
)

DT = 262e-6  # the CSTQ03 cadence (250 us relax + readout)
GAMMA = 200.0  # 2.5 ms dwell


def _em(mu_e, p0=0.1, p1=0.9):
    return {
        "model": "ge_mixture",
        "mu_g": 0.0,
        "mu_e": mu_e,
        "sigma_g": 1.0,
        "sigma_e": 1.0,
        "p_e_state0": p0,
        "p_e_state1": p1,
    }


def _record(seed, n, p0, p1, mu_e, g01=GAMMA, g10=GAMMA):
    """Projected g/e shots of a telegraph whose states give P(e) = p0 / p1 (sigma 1)."""
    rng = np.random.default_rng(seed)
    hidden = simulate_telegraph_trace(
        n, DT, g01, g10, mu0=0.0, mu1=1.0, sigma0=1e-9, sigma1=1e-9, seed=seed + 1
    )["states"]
    prepared_e = rng.random(n) < np.where(hidden == 0, p0, p1)
    return rng.normal(np.where(prepared_e, mu_e, 0.0), 1.0)


def test_misspecified_mapping_biased_joint_fit_recovers_rate():
    # True contrast 0.5 (P(e) = 0.25 / 0.75), readout SNR 3, analysed with (0.1, 0.9).
    v = _record(301, 30000, 0.25, 0.75, mu_e=3.0)
    fixed = fit_two_state_hmm(v, DT, _em(3.0), symmetric=True, gamma_init_hz=400.0)
    g_fixed = fixed["gamma01_hz"] if fixed["identifiable"] else float("nan")
    # The fixed fit is several times fast: either reported (and > 3x off, far outside its
    # error bar) or withheld by the resolved-rate gate.
    fixed_mixing = fixed["mixing_per_step"]
    assert (math.isfinite(g_fixed) and g_fixed > 3 * GAMMA) or (
        not fixed["identifiable"] and fixed_mixing > 3 * 2 * GAMMA * DT
    ), (g_fixed, fixed_mixing, fixed["unidentifiable_reasons"])

    joint = fit_two_state_hmm(
        v, DT, _em(3.0), symmetric=True, fit_mapping=True, gamma_init_hz=400.0
    )
    assert joint["identifiable"], joint["unidentifiable_reasons"]
    g, err = joint["gamma01_hz"], joint["gamma01_err_hz"]
    assert math.isfinite(err) and err > 0, err
    assert abs(g - GAMMA) < 3 * err and abs(g - GAMMA) < 0.2 * GAMMA, (g, err)
    assert abs(joint["p_e_state0_fit"] - 0.25) < 0.03, joint["p_e_state0_fit"]
    assert abs(joint["p_e_state1_fit"] - 0.75) < 0.03, joint["p_e_state1_fit"]
    assert 0 < joint["p_e_state0_err"] < 0.03 and 0 < joint["p_e_state1_err"] < 0.03, joint
    assert joint["mapping_fitted"] and joint["emissions_used"]["p_e_state1"] == pytest.approx(
        joint["p_e_state1_fit"]
    )

    # The rate error is marginal over the mapping: at least the error with the mapping
    # fixed at the (here correct) values.
    known = fit_two_state_hmm(v, DT, _em(3.0, 0.25, 0.75), symmetric=True, gamma_init_hz=400.0)
    assert known["identifiable"], known["unidentifiable_reasons"]
    assert err >= 0.99 * known["gamma01_err_hz"], (err, known["gamma01_err_hz"])


def test_emission_gate_uses_the_fitted_mapping():
    # Real contrast 0.4 at readout SNR 2: separation at the fitted mapping ~0.6 < 0.7.
    # The seed (0.1, 0.9) would pass the gate (1.37); the joint fit is withheld by it.
    v = _record(311, 30000, 0.3, 0.7, mu_e=2.0)
    fit = fit_two_state_hmm(v, DT, _em(2.0), symmetric=True, fit_mapping=True, gamma_init_hz=400.0)
    assert fit["emission_snr_seed"] > 0.7 > fit["emission_snr"], fit["emission_snr"]
    assert not fit["identifiable"] and math.isnan(fit["gamma01_hz"])
    assert any("at the fitted mapping" in r for r in fit["unidentifiable_reasons"]), fit[
        "unidentifiable_reasons"
    ]
    # the other gates are still evaluated: there IS switching (gain over i.i.d. >> 10)
    assert fit["delta_loglik_iid"] > 100, fit["delta_loglik_iid"]


def test_low_contrast_joint_fit_unidentifiable():
    # |p1 - p0| = 0.1: the joint fit must not return a rate (degenerates toward i.i.d.).
    v = _record(321, 30000, 0.45, 0.55, mu_e=2.0)
    fit = fit_two_state_hmm(v, DT, _em(2.0), symmetric=True, fit_mapping=True, gamma_init_hz=400.0)
    assert not fit["identifiable"] and math.isnan(fit["gamma01_hz"]), fit
    # i.i.d. shots: the free-P(e) null equals the HMM
    w = _record(322, 30000, 0.5, 0.5, mu_e=2.0)
    fit_iid = fit_two_state_hmm(
        w, DT, _em(2.0), symmetric=True, fit_mapping=True, gamma_init_hz=400.0
    )
    assert not fit_iid["identifiable"] and fit_iid["delta_loglik_iid"] < 10, fit_iid
    assert abs(fit_iid["iid_p_e"] - 0.5) < 0.03, fit_iid["iid_p_e"]


def test_label_order_follows_the_seed():
    # Asymmetric telegraph: state0 (P(e) 0.1) occupied 70%. A reversed seed relabels
    # consistently: p's and rates swap together.
    g01, g10 = 120.0, 280.0
    v = _record(331, 20000, 0.1, 0.9, mu_e=3.0, g01=g01, g10=g10)
    fwd = fit_two_state_hmm(
        v, DT, _em(3.0, 0.2, 0.8), symmetric=False, fit_mapping=True, gamma_init_hz=200.0
    )
    rev = fit_two_state_hmm(
        v, DT, _em(3.0, 0.8, 0.2), symmetric=False, fit_mapping=True, gamma_init_hz=200.0
    )
    assert fwd["identifiable"] and rev["identifiable"], (
        fwd["unidentifiable_reasons"],
        rev["unidentifiable_reasons"],
    )
    assert fwd["p_e_state1_fit"] > fwd["p_e_state0_fit"]
    assert rev["p_e_state0_fit"] > rev["p_e_state1_fit"]
    assert fwd["gamma01_hz"] == pytest.approx(rev["gamma10_hz"], rel=0.02)
    assert fwd["gamma10_hz"] == pytest.approx(rev["gamma01_hz"], rel=0.02)
    assert abs(fwd["gamma01_hz"] - g01) < 0.25 * g01, fwd["gamma01_hz"]
    assert fwd["occupancy"][1] == pytest.approx(rev["occupancy"][0], abs=1e-3)


def test_fit_mapping_options():
    v = _record(341, 3000, 0.1, 0.9, mu_e=3.0)
    gauss = {"model": "gaussian", "mu0": 0.0, "mu1": 3.0, "sigma0": 1.0, "sigma1": 1.0}
    with pytest.raises(ValueError, match="fit_mapping"):
        fit_two_state_hmm(v, DT, gauss, fit_mapping=True)
    # p = 0 / 1 seeds are clipped into the logit bounds; the bootstrap refits the mapping
    fit = fit_two_state_hmm(
        v, DT, _em(3.0, 0.0, 1.0), symmetric=True, fit_mapping=True, n_boot=3, seed=1
    )
    assert fit["identifiable"], fit["unidentifiable_reasons"]
    assert fit["gamma_boot_ci"] is not None and fit["gamma_boot_ci"]["n_boot"] == 3
    assert any("refits the mapping" in w for w in fit["warnings"]), fit["warnings"]
    # default (fit_mapping=False) is unchanged: p's fixed, no fitted fields
    fixed = fit_two_state_hmm(v, DT, _em(3.0), symmetric=True)
    assert not fixed["mapping_fitted"] and math.isnan(fixed["p_e_state0_fit"])
    assert fixed["emissions_used"]["p_e_state0"] == 0.1


def _cal(mu_e, seed):
    rng = np.random.default_rng(seed)
    n = 4000
    return calibrate_readout_from_labeled_shots(
        rng.normal(0.0, 1.0, n),
        rng.normal(0.0, 1.0, n),
        rng.normal(mu_e, 1.0, n),
        rng.normal(0.0, 1.0, n),
    )


def test_analysis_fits_mapping_by_default():
    cal = _cal(3.0, 351)
    v = _record(352, 20000, 0.25, 0.75, mu_e=cal["proj_e_mean"] - cal["proj_g_mean"])
    v = v + cal["proj_g_mean"]
    axis, mid = cal["axis"], cal["midpoint"]
    I, Q = mid[0] + v * axis[0], mid[1] + v * axis[1]
    kw = dict(expected_dwell_s=1.0 / GAMMA, save_plots=False, save_sidecars=False)
    res = analyze_modified_ramsey_record(I, Q, DT, cal, **kw)
    s = res["summary"]
    assert s["mapping_fitted"] and s["identifiable"], res["hmm"]["unidentifiable_reasons"]
    assert (s["mapping_p_e_state0"], s["mapping_p_e_state1"]) == (0.1, 0.9)  # the seed
    assert abs(s["mapping_p_e_state0_fit"] - 0.25) < 0.04, s["mapping_p_e_state0_fit"]
    assert abs(s["mapping_p_e_state1_fit"] - 0.75) < 0.04, s["mapping_p_e_state1_fit"]
    assert math.isfinite(s["mapping_p_e_state0_err"]) and s["emission_snr"] > 0.7
    assert abs(s["gamma01_hz"] - GAMMA) < 0.25 * GAMMA, s["gamma01_hz"]
    assert not any("assumed rather than" in w for w in s["warnings"]), s["warnings"]
    # the seed-mapping SNR, the free-P(e) i.i.d. null and the seed source are saved too
    assert s["emission_snr_seed"] == res["hmm"]["emission_snr_seed"] > s["emission_snr"]
    assert 0.0 < s["iid_p_e"] < 1.0 and s["iid_p_e"] == res["hmm"]["iid_p_e"]
    assert s["mapping_seed_source"] is None

    fixed = analyze_modified_ramsey_record(
        I, Q, DT, cal, fit_mapping=False, mapping_seed_source="assumed", **kw
    )["summary"]
    assert not fixed["mapping_fitted"] and math.isnan(fixed["mapping_p_e_state0_fit"])
    assert any("assumed rather than" in w for w in fixed["warnings"]), fixed["warnings"]
    assert fixed["mapping_seed_source"] == "assumed"
    # hmm_kwargs["fit_mapping"] overrides fit_mapping (the run relies on the same precedence)
    over = analyze_modified_ramsey_record(I, Q, DT, cal, hmm_kwargs={"fit_mapping": False}, **kw)
    assert not over["summary"]["mapping_fitted"]


def test_predicted_mapping_seed():
    cfg = {"df": 2.7, "sigma": 0.04, "f_ge": 4186.7, "symmetric_ramsey": False}
    cfg["ramsey_tau_us"] = 3 / (2 * 2.7)
    pred = plan_parity_mapping(2.7, 0.04, tau_us=cfg["ramsey_tau_us"])["predicted_mapping"]
    p0, p1, src = predicted_mapping_seed(cfg)
    assert src == "predicted" and p0 < p1
    assert (p0, p1) == tuple(sorted((pred["p_e_upper"], pred["p_e_lower"])))
    # the flip control predicts the branches the other way round (not an exact swap with
    # finite pulses); its seed is ordered the same way (state1 = the larger P(e)), the label
    # convention of the (0.1, 0.9) default
    f0, f1, f_src = predicted_mapping_seed(dict(cfg, flip_final_pi2=True))
    pred_f = plan_parity_mapping(2.7, 0.04, tau_us=cfg["ramsey_tau_us"], flip_final_pi2=True)[
        "predicted_mapping"
    ]
    assert f_src == "predicted" and f0 < f1
    assert (pred_f["p_e_upper"] > pred_f["p_e_lower"]) != (pred["p_e_upper"] > pred["p_e_lower"])
    # infeasible plan (no gap between the pulses): fallback
    tight = dict(cfg, ramsey_tau_us=0.1)
    assert predicted_mapping_seed(tight, fallback=(0.2, 0.8)) == (
        0.2,
        0.8,
        "fallback: infeasible plan",
    )
    # predicted contrast below the minimum (an even harmonic): fallback
    even = dict(cfg, ramsey_tau_us=4 / (2 * 2.7))
    p_even = plan_parity_mapping(2.7, 0.04, tau_us=even["ramsey_tau_us"])["predicted_mapping"]
    assert p_even["contrast"] < MAPPING_SEED_MIN_PREDICTED_CONTRAST
    q0, q1, src_even = predicted_mapping_seed(even)
    assert (q0, q1) == (0.1, 0.9) and src_even.startswith("fallback: predicted contrast")
