"""Labelled g/e overlap error saved as overlap_mat by the single-shot optimisation maps (F59).

Before 2026-10 overlap_mat came from MixedShots: an unseeded KMeans split of the pooled shots
and an unbounded double-Gaussian fit to the mixed histogram, NaN whenever the fitted overlap
passed 90% of a blob. At the separations CSTQ03 runs (analog SNR ~1-1.5) it was NaN in most
points, biased high and differed between reruns on the same shots. labelled_overlap_error uses
the g/e labels instead: one unbinned fit with shared centres and width, minority weights in
[0, 0.5], kept only when they raise the likelihood by 2 Delta lnL >= 9 over the w = 0 fit,
and reports 2 Phi(-d/2) of the fitted separation. Synthetic clouds only.
docs/experiments/readout_optimize.md#analysis

    python -m pytest tests/test_labelled_overlap.py
"""

import math

import numpy as np
import pytest

from qicklab.analysis.readout import labelled_overlap_error

AXIS = np.array([np.cos(0.7), np.sin(0.7)])


def _clouds(rng, d, n=1000, sigma=250.0, offset=(1200.0, -400.0), p_g=0.0, p_e=0.0):
    """g and e clouds of width sigma, d sigma apart along AXIS; a fraction p_g of the g shots
    sits on the e centre (thermal) and p_e of the e shots on the g centre (prep error)."""
    g = rng.normal(size=(n, 2)) * sigma + offset
    e = rng.normal(size=(n, 2)) * sigma + offset + d * sigma * AXIS
    g[rng.random(n) < p_g] += d * sigma * AXIS
    e[rng.random(n) < p_e] -= d * sigma * AXIS
    return g[:, 0], g[:, 1], e[:, 0], e[:, 1]


def _ideal(d):
    return math.erfc(d / (2 * math.sqrt(2)))  # 2 Phi(-d/2)


@pytest.mark.parametrize("d,tol", [(1.0, 0.05), (2.0, 0.015), (4.0, 0.005)])
def test_tracks_two_phi_of_half_separation(d, tol):
    rng = np.random.default_rng(int(10 * d))
    vals = np.array([labelled_overlap_error(*_clouds(rng, d)) for _ in range(20)])
    assert np.all(np.isfinite(vals))  # MixedShots was NaN in ~2/3 of the points at d = 1
    assert abs(vals.mean() - _ideal(d)) < tol
    assert vals.std() < 0.05


def test_excludes_state_preparation_error():
    # 5% thermal |e> in the g shots, 10% unexcited e shots: the moment SNR and the contrast see
    # the prep error, the fitted overlap does not.
    rng = np.random.default_rng(3)
    vals = [labelled_overlap_error(*_clouds(rng, 3.0, p_g=0.05, p_e=0.10)) for _ in range(10)]
    assert abs(np.mean(vals) - _ideal(3.0)) < 0.01
    i_g, q_g, i_e, q_e = _clouds(rng, 3.0, p_g=0.05, p_e=0.10)
    v_g = np.column_stack([i_g, q_g]) @ AXIS
    v_e = np.column_stack([i_e, q_e]) @ AXIS
    snr = abs(v_e.mean() - v_g.mean()) / math.sqrt(0.5 * (v_g.var() + v_e.var()))
    assert _ideal(snr) > _ideal(3.0) + 0.1


def test_partial_excitation_reads_readout_separation():
    # qubit_optimize: an under-driven pulse leaves a fraction of the e shots in g. Once the
    # excited fraction is resolvable the fit treats the rest as prep error, so the overlap is a
    # readout-separation number (flat in the excitation), not a pulse-quality one; only an
    # almost-unexcited point reads high (docs/experiments/qubit_optimize.md#analysis).
    d = 4.0
    rng = np.random.default_rng(11)
    for excited in (0.3, 0.5, 1.0):
        vals = [labelled_overlap_error(*_clouds(rng, d, p_e=1 - excited)) for _ in range(10)]
        assert abs(np.mean(vals) - _ideal(d)) < 0.015, excited
    vals = [labelled_overlap_error(*_clouds(rng, d, p_e=0.95)) for _ in range(10)]
    assert np.mean(vals) > 0.5


def test_reproducible_and_invariant_to_iq_frame():
    i_g, q_g, i_e, q_e = _clouds(np.random.default_rng(7), 1.2)
    first = labelled_overlap_error(i_g, q_g, i_e, q_e)
    assert labelled_overlap_error(i_g, q_g, i_e, q_e) == first  # deterministic (no KMeans)
    assert labelled_overlap_error(i_g[::-1], q_g[::-1], i_e, q_e) == pytest.approx(first, abs=1e-3)
    c, s = np.cos(1.1), np.sin(1.1)
    rot = [(c * i - s * q) * 3.0 + 50.0 for i, q in ((i_g, q_g), (i_e, q_e))]
    rot_q = [(s * i + c * q) * 3.0 - 7.0 for i, q in ((i_g, q_g), (i_e, q_e))]
    moved = labelled_overlap_error(rot[0], rot_q[0], rot[1], rot_q[1])
    # equal up to the axis: the per-quadrature medians (hist_process's axis) are not exactly
    # rotation-equivariant, and the optimiser converges to ~1e-4
    assert moved == pytest.approx(first, abs=2e-3)


@pytest.mark.parametrize("d", [0.0, 0.25])
def test_weak_separation_does_not_read_falsely_good(d):
    # Without the likelihood-ratio test a single cloud (d = 0: no drive, off resonance) was
    # fitted as a symmetric w_g = w_e = 0.5 mixture with d ~ 1 in ~8% of the trials (down to
    # 0.52), and d = 0.25 read 0.14 low on average (median 0.79). With the test (1000 + 1000
    # shots): at d = 0 ~0.05% of trials (7 in 13600) still keep a spurious mixture and read
    # 0.41-0.48, so a 60-trial run allows one trial below 0.9 (two or more: ~5e-4 per seed;
    # the unguarded fit put ~5 of 60 below 0.8). The fitted |d| > 0 on every trial, so the
    # d = 0 median sits ~0.018 below 1 (sd over seeds ~0.002, range -0.025 to -0.012): its band
    # is one-sided and 0.03 wide. At d = 0.25 0.4% of trials keep a spurious mixture (worst
    # 0.54 low). Every check passed on 60 other seeds of 60 trials; none rests on one seed.
    rng = np.random.default_rng(int(100 + 100 * d))
    vals = np.array([labelled_overlap_error(*_clouds(rng, d)) for _ in range(60)])
    assert np.all(np.isfinite(vals))
    assert np.mean(vals < _ideal(d) - 0.1) <= 0.05
    if d == 0.0:
        assert _ideal(d) - 0.03 < np.median(vals) <= _ideal(d)
        assert np.sum(vals < 0.9) <= 1
    else:
        assert abs(np.median(vals) - _ideal(d)) < 0.02


def test_degenerate_inputs_are_nan():
    i_g, q_g, i_e, q_e = _clouds(np.random.default_rng(1), 0.0)
    assert np.isnan(labelled_overlap_error(i_g[:1], q_g[:1], i_e, q_e))
    assert np.isnan(labelled_overlap_error(i_g, q_g, i_g, q_g))  # coincident medians
    flat = np.ones(50)
    assert np.isnan(labelled_overlap_error(flat, flat, 2 * flat, flat))  # zero width
