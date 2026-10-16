"""hist_process / cdf_gap_threshold: exact empirical-CDF single-shot threshold (review F62).

Before 2026-10 the contrast came from a 200-bin histogram: the returned threshold was the
LEFT edge of the peak bin while the counts ran to its right edge, so the saved (fid,
threshold) pair disagreed by ~0.5% in-sample; shots outside the histogram range were
dropped; and the "pooled" / "per_class" variants broke argmax ties differently on float
noise (threshold jitter up to 0.45 sigma at d = 1). Synthetic data only."""

import math

import numpy as np
import pytest

from qicklab.analysis.readout import (
    calibrate_readout_from_labeled_shots,
    cdf_gap_threshold,
    hist_process,
)


def _true_contrast(d):
    """Equal-width unit Gaussians d sigma apart: C = 2 Phi(d/2) - 1 at the midpoint."""
    return math.erf(d / (2 * math.sqrt(2)))


def _clouds(rng, d, n_g=1000, n_e=1000, angle=0.7, origin=(3.0, -2.0)):
    """g at origin, e at origin + d*(cos angle, sin angle); unit isotropic noise."""
    g = rng.normal(size=(n_g, 2)) + origin
    e = rng.normal(size=(n_e, 2)) + origin + d * np.array([np.cos(angle), np.sin(angle)])
    return g[:, 0], g[:, 1], e[:, 0], e[:, 1]


def _rotated_i(i, q, theta):
    return np.asarray(i) * np.cos(theta) - np.asarray(q) * np.sin(theta)


def _rule_contrast(ig, qg, ie, qe, thr, theta):
    """Contrast the rule g := I' <= thr achieves (the rule iq.count_percentage applies)."""
    return np.mean(_rotated_i(ig, qg, theta) <= thr) - np.mean(_rotated_i(ie, qe, theta) <= thr)


@pytest.mark.parametrize("d", [1.0, 3.0, 6.0])
def test_cdf_gap_threshold_converges_to_analytic(d):
    rng = np.random.default_rng(int(10 * d))
    n = 200_000
    v_g = rng.normal(0.0, 1.0, n)
    v_e = rng.normal(d, 1.0, n)
    contrast, thr = cdf_gap_threshold(v_g, v_e)
    assert abs(contrast - _true_contrast(d)) < 5e-3
    assert abs(thr - d / 2) < (0.3 if d < 2 else 0.15)
    assert contrast == np.mean(v_g <= thr) - np.mean(v_e <= thr)


@pytest.mark.parametrize("d", [1.0, 3.0, 6.0])
def test_hist_process_fid_is_the_contrast_of_its_threshold(d):
    rng = np.random.default_rng(int(100 * d))
    ig, qg, ie, qe = _clouds(rng, d)
    fid, thr, theta = hist_process(data=[ig, qg, ie, qe], plot=False)
    # (a) the saved (fid, threshold) pair agrees with itself exactly (failed by ~0.5% before)
    assert fid == _rule_contrast(ig, qg, ie, qe, thr, theta)
    # median-based angle kept: g -> e lies along +I
    assert abs(theta + 0.7) < 0.3
    # (b) both normalize strings give bit-identical numbers
    assert hist_process(data=[ig, qg, ie, qe], plot=False, normalize="per_class") == (
        fid,
        thr,
        theta,
    )
    # (c) deterministic under permutation of the shots
    pg, pe = rng.permutation(ig.size), rng.permutation(ie.size)
    assert hist_process(data=[ig[pg], qg[pg], ie[pe], qe[pe]], plot=False) == (fid, thr, theta)
    # (d) same contrast as the exact-CDF labelled calibration (mean axis instead of medians)
    cal = calibrate_readout_from_labeled_shots(ig, qg, ie, qe, use_lda=False)
    assert abs(fid - cal["contrast"]) < 2e-2
    # threshold near the analytic midpoint (projected onto the rotated I axis)
    mid_i = _rotated_i(3.0 + 0.5 * d * np.cos(0.7), -2.0 + 0.5 * d * np.sin(0.7), theta)
    assert abs(thr - mid_i) < (0.5 if d < 2 else 0.35)
    # out of sample the threshold is within a few 1e-3 of the optimal contrast
    jg, kg, je, ke = _clouds(np.random.default_rng(7), d, n_g=400_000, n_e=400_000)
    assert _rule_contrast(jg, kg, je, ke, thr, theta) > _true_contrast(d) - 1e-2


# Nearly overlapping clouds (300 shots per class). The seeds include ones (15 and 46 at d = 0,
# 8 and 35 at d = 0.1) where the old pooled |CDF_g - CDF_e| picked the reversed side: its
# threshold put more g than e above it (rule contrast -0.053, -0.020, -0.017, -0.043), so t1_ss
# classified
# anti-correlated (the RunT1SS harness calibration 1 case).
@pytest.mark.parametrize(
    "d, seed", [(0.0, 15), (0.0, 46), (0.0, 0), (0.0, 1), (0.1, 8), (0.1, 35), (0.1, 0), (0.1, 2)]
)
def test_overlapping_clouds_keep_the_e_above_orientation(d, seed):
    ig, qg, ie, qe = _clouds(np.random.default_rng(seed), d, n_g=300, n_e=300)
    fid, thr, theta = hist_process(data=[ig, qg, ie, qe], plot=False)
    assert fid >= 0
    # orientation: the threshold puts at least as many e as g shots above it (failed on the
    # reversed seeds before), then the exactness of the saved pair
    p_e_above = np.mean(_rotated_i(ie, qe, theta) > thr)
    p_g_above = np.mean(_rotated_i(ig, qg, theta) > thr)
    assert p_e_above >= p_g_above
    assert fid == _rule_contrast(ig, qg, ie, qe, thr, theta)
    assert hist_process(data=[ig, qg, ie, qe], plot=False, normalize="per_class") == (
        fid,
        thr,
        theta,
    )


def test_unequal_class_sizes_use_per_class_normalisation():
    rng = np.random.default_rng(3)
    ig, qg, ie, qe = _clouds(rng, 2.0, n_g=1000, n_e=300)
    fid, thr, theta = hist_process(data=[ig, qg, ie, qe], plot=False, normalize="pooled")
    assert fid == _rule_contrast(ig, qg, ie, qe, thr, theta)
    assert hist_process(data=[ig, qg, ie, qe], plot=False, normalize="per_class") == (
        fid,
        thr,
        theta,
    )


def test_far_outliers_are_counted():
    # One g shot 1000 sigma on the far side of g and one e shot 1000 sigma beyond e: the old
    # histogram range [xg - 0.6 ptp_g, xe + 0.6 ptp_e] excluded both from the counts.
    rng = np.random.default_rng(11)
    ig, qg, ie, qe = _clouds(rng, 3.0, angle=0.0, origin=(0.0, 0.0))
    ig, qg = np.append(ig, -1000.0), np.append(qg, 0.0)
    ie, qe = np.append(ie, 1003.0), np.append(qe, 0.0)
    fid, thr, theta = hist_process(data=[ig, qg, ie, qe], plot=False)
    i_g, i_e = _rotated_i(ig, qg, theta), _rotated_i(ie, qe, theta)
    assert ig.size == 1001 and ie.size == 1001
    assert fid == np.sum(i_g <= thr) / 1001 - np.sum(i_e <= thr) / 1001


def test_print_fidelities_reports_misassignment_at_the_threshold(capsys):
    rng = np.random.default_rng(5)
    ig, qg, ie, qe = _clouds(rng, 2.0)
    fid, thr, theta = hist_process(
        data=[ig, qg, ie, qe], plot=False, normalize="per_class", print_fidelities=True
    )
    out = capsys.readouterr().out.splitlines()
    p_e_as_g = np.mean(_rotated_i(ie, qe, theta) <= thr)
    p_g_as_e = np.mean(_rotated_i(ig, qg, theta) > thr)
    assert out == [f"ne contrast:  {p_e_as_g}", f"ng contrast:  {p_g_as_e}"] * 2
    assert fid == pytest.approx(1 - p_e_as_g - p_g_as_e, abs=1e-12)


def test_tie_break_is_first_maximal_plateau_midpoint():
    # disjoint equal maxima (k = 0 and k = 2): the first one, midpoint to the next sample
    assert cdf_gap_threshold([0.0, 2.0], [1.0, 3.0]) == (0.5, 0.5)
    # separated clouds: midpoint of the gap between them
    assert cdf_gap_threshold([0.0, 0.5], [2.0, 3.0]) == (1.0, 1.25)
    # plateau over a tie that holds one g and one e shot (gap unchanged across it)
    assert cdf_gap_threshold([0.0, 1.0], [1.0, 3.0]) == (0.5, 1.5)
    # e entirely left of g: no separating threshold; the threshold is the largest sample
    # (every shot classed g), where the rule contrast is exactly the returned 0
    assert cdf_gap_threshold([5.0, 6.0], [0.0, 1.0]) == (0.0, 6.0)
    assert np.mean(np.array([5.0, 6.0]) <= 6.0) - np.mean(np.array([0.0, 1.0]) <= 6.0) == 0.0
    assert cdf_gap_threshold([0.0, 1.0], [0.0, 1.0]) == (0.0, 1.0)
    c, t = cdf_gap_threshold([], [1.0])
    assert np.isnan(c) and np.isnan(t)
