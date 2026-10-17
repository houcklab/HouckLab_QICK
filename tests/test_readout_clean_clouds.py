"""
F38: the e cloud of the labelled SingleShot calibration is a g/e mixture when the pi pulse is
imperfect (at the parity doublet centre it is detuned df/2 from both branches), so its raw
moments put mu_e toward g, inflate sigma_e and understate the analog SNR.
calibrate_readout_from_labeled_shots keeps those raw moments under their old keys and adds
the clouds of a joint two-Gaussian mixture fit (proj_*_clean, snr_analog_clean) with the
e-cloud purity prep_fidelity_e; analyze_modified_ramsey_record builds its ge_mixture
emissions from the clean clouds when the mapping is fitted or calibrated.

Hardware-free and seeded. Run from the repo root:
    python -m pytest tests/test_readout_clean_clouds.py
"""

import math

import numpy as np

from qicklab.analysis.modified_ramsey import analyze_modified_ramsey_record
from qicklab.analysis.rates import simulate_telegraph_trace
from qicklab.analysis.readout import (
    calibrate_readout_from_labeled_shots,
    single_shot_figures_of_merit,
)

DT = 262e-6
GAMMA = 200.0


def _shots(seed, n, d, e_contamination=0.0, g_thermal=0.0, sigma_e=1.0):
    """Labelled g/e shots along I (g cloud sigma 1, e cloud sigma_e, separation d) with prep
    errors (the unexcited e shots sit in the g cloud, sigma 1)."""
    rng = np.random.default_rng(seed)
    gi = rng.normal(np.where(rng.random(n) < g_thermal, d, 0.0), 1.0)
    in_g = rng.random(n) < e_contamination
    ei = rng.normal(np.where(in_g, 0.0, d), np.where(in_g, 1.0, sigma_e))
    return gi, rng.normal(0.0, 1.0, n), ei, rng.normal(0.0, 1.0, n)


def test_contaminated_e_cloud_is_cleaned():
    # 45% of the pi-prepared shots stay in g, 3% thermal |e> in the g shots, true SNR 2
    cal = calibrate_readout_from_labeled_shots(*_shots(1, 2000, 2.0, 0.45, 0.03))
    assert cal["clean_cloud_source"] == "mixture" and cal["mixture_2dlnl"] >= 9
    assert cal["snr_analog"] < 1.1, cal["snr_analog"]  # the moments understate it
    assert abs(cal["snr_analog_clean"] - 2.0) < 0.3, cal["snr_analog_clean"]
    assert abs(cal["prep_fidelity_e"] - 0.55) < 0.06, cal["prep_fidelity_e"]
    assert 0.0 <= cal["prep_excited_g"] < 0.08, cal["prep_excited_g"]
    sep = cal["proj_e_mean_clean"] - cal["proj_g_mean_clean"]
    assert abs(sep - 2.0) < 0.25 and cal["proj_e_sigma_clean"] < cal["proj_e_sigma"], cal
    # the raw keys keep their meaning: moments of the projected labelled clouds
    _, _, ie, qe = _shots(1, 2000, 2.0, 0.45, 0.03)
    ve = (np.column_stack([ie, qe]) - cal["midpoint"]) @ cal["axis"]
    assert cal["proj_e_mean"] == float(ve.mean())
    assert cal["proj_e_sigma"] == float(ve.std(ddof=1))
    purity = [w for w in cal["warnings"] if "e-cloud purity" in w]
    assert len(purity) == 1 and purity[0] not in cal["readout_gate_warnings"]


def test_clean_labelled_clouds_equal_the_moments():
    cal = calibrate_readout_from_labeled_shots(*_shots(2, 2000, 3.0))
    assert cal["clean_cloud_source"] == "moments", cal["mixture_2dlnl"]
    for k in ("proj_g_mean", "proj_e_mean", "proj_g_sigma", "proj_e_sigma", "snr_analog"):
        assert cal[k + "_clean"] == cal[k], k
    assert cal["prep_fidelity_e"] == 1.0 and cal["prep_excited_g"] == 0.0
    assert cal["warnings"] == cal["readout_gate_warnings"] == []


def test_pure_cloud_outside_sigma_ratio_bounds_is_not_a_mixture():
    # A pure e cloud wider (1.5) or narrower (0.7) than the [0.8, 1.25] sigma-ratio bound of
    # the mixture: the significance baseline is the unbounded pure fit (the fallback moments),
    # so the bounded mixture must not win. Against a bounded pure baseline these read as
    # mixtures with a false purity of ~0.9 and a clean SNR ~25% above the true 1.57 / 2.35.
    for sigma_e, d, n in ((1.5, 2.0, 2000), (1.5, 3.0, 5000), (0.7, 3.0, 5000)):
        for seed in range(30, 35):
            cal = calibrate_readout_from_labeled_shots(*_shots(seed, n, d, sigma_e=sigma_e))
            tag = (sigma_e, d, seed, cal["mixture_2dlnl"])
            assert cal["clean_cloud_source"] == "moments" and cal["mixture_2dlnl"] < 9, tag
            for k in ("proj_g_mean", "proj_e_mean", "proj_g_sigma", "proj_e_sigma", "snr_analog"):
                assert cal[k + "_clean"] == cal[k], (tag, k)
            assert cal["prep_fidelity_e"] == 1.0 and cal["prep_excited_g"] == 0.0, tag
            assert cal["warnings"] == cal["readout_gate_warnings"], tag


def test_overlapping_clouds_are_not_inflated():
    # identical clouds: the mixture must not invent a separation
    for seed in range(5):
        cal = calibrate_readout_from_labeled_shots(*_shots(10 + seed, 2000, 0.0))
        assert cal["clean_cloud_source"] in ("moments", "moments_fallback")
        assert cal["snr_analog_clean"] == cal["snr_analog"] < 0.3, cal["snr_analog_clean"]
        assert cal["contrast"] < 0.1 and cal["readout_gate_warnings"]


def test_unresolved_mixture_falls_back_to_the_moments():
    # 85% of the pi-prepared shots stay in g: the mixture is highly significant but its e
    # weight (~0.15) is below the 0.2 floor, so the clean clouds fall back to the moments
    for seed in range(20, 25):
        cal = calibrate_readout_from_labeled_shots(*_shots(seed, 5000, 3.0, 0.85))
        assert cal["clean_cloud_source"] == "moments_fallback", (seed, cal["mixture_2dlnl"])
        assert cal["mixture_2dlnl"] >= 9
        assert math.isnan(cal["prep_fidelity_e"]) and math.isnan(cal["prep_excited_g"])
        for k in ("proj_g_mean", "proj_e_mean", "proj_g_sigma", "proj_e_sigma", "snr_analog"):
            assert cal[k + "_clean"] == cal[k], (seed, k)
        fallback = [w for w in cal["warnings"] if "mixture fit unresolved" in w]
        assert len(fallback) == 1 and fallback[0] not in cal["readout_gate_warnings"]
        assert not any("e-cloud purity" in w for w in cal["warnings"])  # NaN purity: no warning
        assert cal["warnings"] == cal["readout_gate_warnings"] + fallback


def test_single_shot_gate_ignores_purity_warning():
    ig, qg, ie, qe = _shots(3, 2000, 4.0, 0.2)
    cal = calibrate_readout_from_labeled_shots(ig, qg, ie, qe)
    assert cal["readout_gate_warnings"] == [] and cal["warnings"], cal["warnings"]
    fom, warnings = single_shot_figures_of_merit(ig, qg, ie, qe, 0.5, 0.0, 0.0)
    assert fom["readout_gate_pass"] == 1.0 and warnings == cal["warnings"]


def _mr_record(seed, n, p0, p1, d):
    """IQ of a telegraph whose states give P(e) = p0 / p1, true clouds 0 and d (sigma 1)."""
    rng = np.random.default_rng(seed)
    hidden = simulate_telegraph_trace(
        n, DT, GAMMA, GAMMA, mu0=0.0, mu1=1.0, sigma0=1e-9, sigma1=1e-9, seed=seed + 1
    )["states"]
    prepared_e = rng.random(n) < np.where(hidden == 0, p0, p1)
    i = rng.normal(np.where(prepared_e, d, 0.0), 1.0)
    return i, rng.normal(0.0, 1.0, n)


def test_mr_analysis_uses_clean_clouds_with_fitted_mapping():
    d = 3.0
    cal = calibrate_readout_from_labeled_shots(*_shots(4, 2000, d, 0.4))
    assert cal["clean_cloud_source"] == "mixture"
    I, Q = _mr_record(5, 20000, 0.25, 0.75, d)
    kw = dict(expected_dwell_s=1.0 / GAMMA, save_plots=False, save_sidecars=False)
    res = analyze_modified_ramsey_record(I, Q, DT, cal, **kw)
    s, used = res["summary"], res["hmm"]["emissions_used"]
    assert s["readout_clouds"] == "clean" and used["mu_e"] == cal["proj_e_mean_clean"]
    assert used["sigma_e"] == cal["proj_e_sigma_clean"]
    assert s["prep_fidelity_e"] == cal["prep_fidelity_e"] and s["clean_cloud_source"] == "mixture"
    # the fitted mapping is the true one, not one distorted by the contaminated e cloud
    assert s["identifiable"], res["hmm"]["unidentifiable_reasons"]
    assert abs(s["mapping_p_e_state0_fit"] - 0.25) < 0.05, s["mapping_p_e_state0_fit"]
    assert abs(s["mapping_p_e_state1_fit"] - 0.75) < 0.05, s["mapping_p_e_state1_fit"]
    assert abs(s["gamma01_hz"] - GAMMA) < 0.25 * GAMMA, s["gamma01_hz"]
    raw = analyze_modified_ramsey_record(I, Q, DT, cal, clean_readout_clouds=False, **kw)
    assert raw["summary"]["readout_clouds"] == "raw"
    assert raw["hmm"]["emissions_used"]["mu_e"] == cal["proj_e_mean"]
    assert raw["summary"]["mapping_p_e_state1_fit"] > s["mapping_p_e_state1_fit"] + 0.1

    # an assumed FIXED mapping keeps the raw clouds; forcing clean ones warns
    kw_fixed = dict(kw, fit_mapping=False)
    fixed = analyze_modified_ramsey_record(I, Q, DT, cal, **kw_fixed)["summary"]
    assert fixed["readout_clouds"] == "raw"
    forced = analyze_modified_ramsey_record(I, Q, DT, cal, clean_readout_clouds=True, **kw_fixed)
    s_f = forced["summary"]
    assert s_f["readout_clouds"] == "clean"
    assert any("assumed fixed mapping" in w for w in s_f["warnings"]), s_f["warnings"]
    calibrated = analyze_modified_ramsey_record(
        I, Q, DT, cal, mapping_probabilities_calibrated=True, **kw_fixed
    )["summary"]
    assert calibrated["readout_clouds"] == "clean"
    assert not any("assumed fixed mapping" in w for w in calibrated["warnings"])
    assert math.isfinite(s["snr_analog_clean"]) and s["snr_analog_clean"] > s["snr_analog"]
