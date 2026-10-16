"""
Hardware-free tests for the threshold-crossing rate-vs-bin-size sweep
(qicklab.analysis.rates): the Modified-Ramsey form `rate_vs_bin_size`
(seconds) and the Undriven form `rate_vs_bin_size_us` (microseconds) share
one core and the same rate definition, n_switches / ((n_bins - 1) * b * dt).

Run from the repo root:
    python -m pytest tests/test_rate_vs_bin_size.py
"""

import math

import numpy as np

from qicklab.analysis.rates import rate_vs_bin_size, rate_vs_bin_size_us


def _telegraph(n, p_flip, sigma, mu1=1.0, seed=0):
    """Per-shot telegraph: flip with probability p_flip per shot, Gaussian noise."""
    rng = np.random.default_rng(seed)
    flips = rng.random(n - 1) < p_flip
    states = np.concatenate([[0], np.cumsum(flips) % 2])
    return states * mu1 + sigma * rng.standard_normal(n), int(flips.sum())


def test_si_and_us_forms_agree():
    dt_us = 2.0
    for n, seed in [(1000, 1), (10000, 2), (100000, 3)]:
        v, _ = _telegraph(n, 0.02, 0.4, seed=seed)
        sizes = (1, 2, 4, 8, 16, 32, 64)
        mr = rate_vs_bin_size(v, dt_us * 1e-6, 0.5, bin_sizes=sizes)
        ud = rate_vs_bin_size_us(v, dt_us, 0.5, bin_sizes=sizes)
        assert list(ud["bin_sizes"]) == mr["bin_sizes"] == list(sizes)
        assert list(ud["n_switches"]) == mr["n_switches"]
        np.testing.assert_allclose(ud["bin_dt_us"], mr["bin_us"], rtol=1e-12)
        np.testing.assert_allclose(ud["rate_hz"], mr["rate_hz"], rtol=1e-12, equal_nan=True)


def test_denominator_counts_diff_intervals():
    # 4 blocks of 1 sample, 3 state changes over 3 intervals of 1 s: 1 Hz.
    # (The old Undriven span n_bins*b*dt gave 0.75 Hz, low by n_bins/(n_bins-1).)
    v = np.array([0.0, 1.0, 0.0, 1.0])
    assert rate_vs_bin_size(v, 1.0, 0.5, bin_sizes=(1,))["rate_hz"] == [1.0]
    assert rate_vs_bin_size_us(v, 1e6, 0.5, bin_sizes=(1,))["rate_hz"][0] == 1.0

    v, _ = _telegraph(103, 0.2, 0.0, seed=4)  # noise-free, 103 // 8 = 12 blocks
    dt = 1e-6
    for b in (1, 2, 8, 25):
        nb = v.size // b
        bits = (v[: nb * b].reshape(nb, b).mean(axis=1) > 0.5).astype(int)
        n_sw = int(np.count_nonzero(np.diff(bits)))
        expect = n_sw / ((nb - 1) * b * dt)
        got_s = rate_vs_bin_size(v, dt, 0.5, bin_sizes=(b,))["rate_hz"][0]
        got_us = rate_vs_bin_size_us(v, dt * 1e6, 0.5, bin_sizes=(b,))["rate_hz"][0]
        assert math.isclose(got_s, expect, rel_tol=1e-12)
        assert math.isclose(got_us, expect, rel_tol=1e-12)
        # pins the nb/(nb-1) relation to the span-based rate
        assert math.isclose(got_us * (nb - 1) / nb, n_sw / (nb * b * dt), rel_tol=1e-12)


def test_unbinned_rate_matches_true_flip_rate():
    # Well-separated levels: every flip is one threshold crossing at b = 1.
    n, p, dt_us = 100000, 0.02, 1.0
    v, n_flips = _telegraph(n, p, 0.4, mu1=10.0, seed=5)
    ud = rate_vs_bin_size_us(v, dt_us, 5.0, bin_sizes=(1,))
    assert ud["n_switches"][0] == n_flips
    true_rate = p / (dt_us * 1e-6)
    sigma_rate = math.sqrt(p * (n - 1)) / ((n - 1) * dt_us * 1e-6)
    assert abs(ud["rate_hz"][0] - true_rate) < 4 * sigma_rate


def test_short_bins_bad_sizes_and_bad_threshold():
    v, _ = _telegraph(20, 0.3, 0.1, seed=6)
    ud = rate_vs_bin_size_us(v, 1.0, 0.5, bin_sizes=(0, 1, 8))
    assert list(ud["bin_sizes"]) == [1, 8]  # b < 1 skipped
    assert np.isnan(ud["rate_hz"][1]) and ud["n_switches"][1] == 0  # 2 blocks < 4
    bad = rate_vs_bin_size_us(v, 1.0, float("nan"), bin_sizes=(1, 2))
    assert np.all(np.isnan(bad["rate_hz"])) and list(bad["n_switches"]) == [0, 0]
