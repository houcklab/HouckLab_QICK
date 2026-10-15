"""Hardware-free tests for the resonator carry-over gate (F52).

assess_resonator_fit / assess_resonator_feature decide whether a transmission trace holds a
resonator worth carrying into ctx.config['pulse_freq']: depth >= 6 robust sigma of the
off-resonant baseline, linewidth in [2 steps, span/2) (and, with a fit, the data's own
half-power width >= 2 steps), f0 >= 2 linewidths inside the span. Synthetic hangers must pass
(including a deep dip whose Qtot > Qext, 20-34 dB near-critically-coupled notches, a 2 dB dip
and a dip on a tilted background); fits to resonator-free noise and to a single bad point must
fail, and a clean, well-placed dip must fail below 6 sigma and pass above it. See
docs/experiments/transmission_fit.md#carry-over-gate.

    python -m pytest tests/test_resonator_gate.py
"""

import warnings

import numpy as np
import pytest
from scipy.optimize import brentq

from qicklab.analysis.fitting import (
    assess_resonator_feature,
    assess_resonator_fit,
    fit_hanger_transmission,
    hanger_model_db,
)

FPTS = np.linspace(7090.0, 7100.0, 201)  # +-5 MHz, 0.05 MHz steps (CSTQ03 Transmission_params)
F0, KAPPA = 7095.2, 0.3  # MHz; kappa = |f0|/Qtot


def _display_fit(y_db):
    """The fit CavitySpecFF.display runs (same start point)."""
    i = int(np.argmin(y_db))
    q = max(abs(FPTS[i]) / ((FPTS[-1] - FPTS[0]) / 10), 1e3)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return fit_hanger_transmission(
            FPTS, amp_db=y_db, startpoint=[FPTS[i], q, 1.5 * q, 0.0, 0.0]
        )["popt"]


def _hanger(qtot_over_qext, asym=0.0, noise_db=0.1, seed=0, f0=F0, kappa=KAPPA):
    qtot = f0 / kappa
    popt = [f0, qtot, qtot / qtot_over_qext, asym, -35.0]
    rng = np.random.default_rng(seed)
    return hanger_model_db(FPTS, *popt) + noise_db * rng.standard_normal(FPTS.size), popt


@pytest.mark.parametrize("asym", [0.0, 0.3, -1.0])
def test_deep_dip_with_qtot_above_qext_passes(asym):
    # Qtot/Qext = 1.2: a ~14 dB dip that a Qtot <= Qext gate would wrongly reject.
    y, popt = _hanger(1.2, asym=asym)
    assert popt[1] > popt[2]
    ok, reasons, m = assess_resonator_fit(FPTS, y, popt)
    assert ok, reasons
    assert m["depth_sigmas"] > 50
    ok, reasons, _ = assess_resonator_fit(FPTS, y, _display_fit(y))
    assert ok, reasons


# f0 on a grid point (FPTS[104]), so the notch minimum is sampled: the dB notch is log-shaped
# and only ~1 point wide half-way down in dB, but its half-power width is the linewidth.
F0_ON_GRID = FPTS[104]


@pytest.mark.parametrize("asym", [0.0, 0.95 * np.tan(0.8) * np.pi * KAPPA], ids=["asym0", "phi0.8"])
@pytest.mark.parametrize("ratio", [0.9, 0.95, 0.98, 1.02, 1.05])
@pytest.mark.parametrize("kappa", [0.3, 0.6])
def test_deep_near_critical_notch_passes(ratio, kappa, asym):
    # Qtot/Qext 0.9-1.05: 20-34 dB notches, the best resonators; judged on the true popt, on
    # display()'s own fit and (raw argmin, no fit) on the data's half-power width.
    y, popt = _hanger(ratio, asym=asym, f0=F0_ON_GRID, kappa=kappa)
    ok, reasons, m = assess_resonator_fit(FPTS, y, popt)
    assert ok, reasons
    assert m["depth_db"] > 15
    assert m["data_width_steps"] >= 0.8 * kappa / 0.05
    ok, reasons, _ = assess_resonator_fit(FPTS, y, _display_fit(y))
    assert ok, reasons
    ok, reasons, m = assess_resonator_feature(FPTS, y, FPTS[np.argmin(y)], dip=True)
    assert ok, reasons
    assert m["linewidth_steps"] >= 0.8 * kappa / 0.05


def test_two_step_widths_are_counted_not_divided():
    # np.linspace steps differ by an ulp (x[98]-x[96] is 1.99999999998 median steps): a two-point
    # dip and a two-step fitted linewidth must count as 2 steps, not fail '>= 2'.
    y = -35 + 0.05 * np.random.default_rng(0).standard_normal(FPTS.size)
    y[[96, 97]] -= 10.0
    lw = FPTS[98] - FPTS[96]
    assert lw / np.median(np.diff(FPTS)) < 2.0
    f0 = 0.5 * (FPTS[96] + FPTS[97])
    ok, reasons, m = assess_resonator_feature(FPTS, y, f0, linewidth=lw)
    assert ok, reasons
    assert m["data_width_steps"] == 2.0
    ok, reasons, m = assess_resonator_feature(FPTS, y, FPTS[96], dip=True)
    assert ok, reasons
    assert m["linewidth_steps"] == pytest.approx(2.0)


@pytest.mark.parametrize("kappa", [1.0, 1.4])
def test_wide_centred_dip_within_the_baseline_limit_passes(kappa):
    # The baseline rule (>= 10 points beyond 3 linewidths) caps a centred linewidth at about
    # (span - 10 steps)/6 = 1.58 MHz here; below it a clean dip passes (test_no_baseline_fails
    # is the other side).
    y, popt = _hanger(0.7, f0=7095.0, kappa=kappa)
    ok, reasons, m = assess_resonator_fit(FPTS, y, popt)
    assert ok, reasons
    assert m["n_baseline"] >= 10


@pytest.mark.parametrize("seed", range(5))
def test_two_db_dip_passes(seed):
    # |1 - Qtot/Qext| = 10^(-2/20): a 2 dB dip under 0.1 dB noise, judged on the display fit.
    y, _ = _hanger(1 - 10 ** (-2 / 20), seed=seed)
    ok, reasons, m = assess_resonator_fit(FPTS, y, _display_fit(y))
    assert ok, reasons
    assert m["linewidth_source"] == "fit"


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 6, 7, 8, 9])
def test_depth_threshold_is_six_sigma(seed):
    # Pins RESONATOR_GATE_MIN_DEPTH_SIGMAS: a 0.6 MHz (12-step) dip centred in the span under
    # 0.1 dB noise, its depth scaled so the gate measures exactly 4.5, 5.5, 6.5 and 7.5 robust
    # sigma. Width, data width, edge and baseline all pass, so below 6 sigma the depth check is
    # the only reason and above it the dip passes: any threshold outside (5.5, 6.5] fails here.
    # Seeds 0 and 5 are left out: at 4.5 sigma their noise leaves a dip 1-2 points wide at half
    # power, which is the data-width check's business.
    def judge(depth_db):
        y, popt = _hanger(1 - 10 ** (-depth_db / 20), seed=seed, kappa=0.6)
        return assess_resonator_fit(FPTS, y, popt)

    for target in (4.5, 5.5, 6.5, 7.5):
        d = brentq(lambda d: judge(d)[2]["depth_sigmas"] - target, 0.05, 3.0, xtol=1e-9)
        ok, reasons, m = judge(d)
        assert m["depth_sigmas"] == pytest.approx(target, abs=1e-3)
        assert m["linewidth_steps"] == pytest.approx(12.0)
        assert m["data_width_steps"] >= 3
        if target < 6:
            assert not ok
            assert len(reasons) == 1 and "x the baseline noise" in reasons[0], reasons
        else:
            assert ok, reasons


@pytest.mark.parametrize("seed", range(12))
def test_noise_only_fit_fails(seed):
    y = -35 + 0.3 * np.random.default_rng(seed).standard_normal(FPTS.size)
    ok, reasons, m = assess_resonator_fit(FPTS, y, _display_fit(y))
    assert not ok and reasons
    # No single check is relied on: a broad fit to noise can come out deeper than 6 sigma and
    # is then caught by the baseline count, the edge or the data's half-power width (see docs).


@pytest.mark.parametrize("depth_db", [1.0, 10.0, 20.0])
@pytest.mark.parametrize("seed", range(6))
def test_single_bad_point_fails_on_the_fit_path(depth_db, seed):
    # One point pulled down on a flat line: the display fit settles on it with a linewidth just
    # above 2 steps, so only the data's own half-power width (1 step) rejects it.
    y = -35 + 0.1 * np.random.default_rng(seed).standard_normal(FPTS.size)
    y[100] -= depth_db
    ok, reasons, m = assess_resonator_fit(FPTS, y, _display_fit(y))
    assert not ok
    assert m["data_width_steps"] == pytest.approx(1.0)
    assert any("single-point dip" in r for r in reasons), reasons


def test_single_bad_point_with_a_two_step_fit_fails_only_on_data_width():
    # The case the fit-linewidth check alone let through: popt with a 2.2-step linewidth
    # centred on the bad point (depth ~100 sigma, far from the edges).
    y = -35 + 0.1 * np.random.default_rng(0).standard_normal(FPTS.size)
    y[100] -= 10.0
    popt = [FPTS[100], FPTS[100] / 0.11, 1e9, 0.0, -35.0]
    ok, reasons, m = assess_resonator_fit(FPTS, y, popt)
    assert not ok
    assert len(reasons) == 1 and "single-point dip" in reasons[0], reasons
    assert "raise num_points or narrow span" in reasons[0], reasons
    assert m["linewidth_steps"] == pytest.approx(2.2, abs=0.01)


@pytest.mark.parametrize("kappa", [0.03, 0.05])
@pytest.mark.parametrize("ratio", [0.5, 0.95])
def test_resonance_narrower_than_the_grid_fails_with_the_remedy(kappa, ratio):
    # A real, deep resonance under 2 steps wide (0.6-1 step on the default grid) cannot be told
    # from a spike, so it is rejected; the reason must say how to fix it (finer step), not call
    # it noise, and must not suggest widening the span.
    y, _ = _hanger(ratio, f0=F0_ON_GRID, kappa=kappa)
    ok, reasons, m = assess_resonator_fit(FPTS, y, _display_fit(y))
    assert not ok
    assert m["depth_db"] > 5
    hints = [r for r in reasons if "too narrow for the grid" in r]
    assert hints, reasons
    assert all("raise num_points or narrow span" in r for r in hints), hints
    ok, reasons, _ = assess_resonator_feature(FPTS, y, FPTS[np.argmin(y)], dip=True)
    assert not ok
    assert any("too narrow for the grid" in r for r in reasons), reasons
    # The remedy works: the same resonance on a 0.01 MHz grid (+-2 MHz, 401 points) passes.
    fine = np.linspace(F0_ON_GRID - 2.0, F0_ON_GRID + 2.0, 401)
    popt = [F0_ON_GRID, F0_ON_GRID / kappa, F0_ON_GRID / kappa / ratio, 0.0, -35.0]
    y_fine = hanger_model_db(fine, *popt) + 0.1 * np.random.default_rng(0).standard_normal(401)
    ok, reasons, _ = assess_resonator_fit(fine, y_fine, popt)
    assert ok, reasons


@pytest.mark.parametrize("tilt", [0.3, 0.6, 1.0])  # dB/MHz: 3-10 dB across the 10 MHz span
def test_tilted_background_does_not_count_as_noise(tilt):
    # A clean 3 dB dip judged on its own hanger curve: the tilt the hanger model cannot follow
    # is removed from the baseline residuals before the MAD, so the dip is not "too shallow".
    y, popt = _hanger(1 - 10 ** (-3 / 20))
    y = y + tilt * (FPTS - 7095.0)
    ok, reasons, m = assess_resonator_fit(FPTS, y, popt)
    assert ok, reasons
    assert m["depth_sigmas"] > 15


@pytest.mark.parametrize("seed", range(5))
def test_tilted_background_peak_passes(seed):
    # The no-fit path (raw peak): the residuals are the trace itself, so the tilt is all there.
    rng = np.random.default_rng(seed)
    y = -35 + 3 / (1 + ((FPTS - F0) / 0.15) ** 2) + 0.1 * rng.standard_normal(FPTS.size)
    y = y + 0.3 * (FPTS - 7095.0)
    ok, reasons, _ = assess_resonator_feature(FPTS, y, FPTS[np.argmax(y)], dip=False)
    assert ok, reasons


@pytest.mark.parametrize(
    "kappa, words",
    [(0.05, "frequency steps"), (6.0, "not below 0.5 x the span"), (0.002, "frequency steps")],
    ids=["one_step", "wider_than_half_span", "sub_step"],
)
def test_linewidth_bounds(kappa, words):
    y, popt = _hanger(0.5, kappa=max(kappa, 0.3))
    popt[1] = popt[0] / kappa
    ok, reasons, _ = assess_resonator_fit(FPTS, y, popt)
    assert not ok
    assert any(words in r for r in reasons), reasons


def test_dip_at_the_sweep_edge_fails():
    y, popt = _hanger(0.5, f0=7090.4)  # 1.3 linewidths inside the span
    ok, reasons, m = assess_resonator_fit(FPTS, y, popt)
    assert not ok
    assert any("sweep edge" in r for r in reasons), reasons
    assert m["edge_linewidths"] == pytest.approx(0.4 / KAPPA)


def test_no_baseline_fails():
    # f0 central, kappa = 2 MHz: nothing lies more than 3 linewidths (6 MHz) from f0.
    y, popt = _hanger(0.5, f0=7095.0, kappa=2.0)
    ok, reasons, m = assess_resonator_fit(FPTS, y, popt)
    assert not ok and m["n_baseline"] < 10
    assert len(reasons) == 1 and "no baseline" in reasons[0], reasons


def test_peak_feature_passes_and_noise_peak_fails():
    rng = np.random.default_rng(3)
    y = -35 + 6 / (1 + ((FPTS - F0) / 0.15) ** 2) + 0.05 * rng.standard_normal(FPTS.size)
    ok, reasons, m = assess_resonator_feature(FPTS, y, FPTS[np.argmax(y)], dip=False)
    assert ok, reasons
    assert m["linewidth_source"] == "half-power width"
    assert m["linewidth"] == pytest.approx(0.3, abs=0.1)
    # the same trace judged as a dip at its maximum is rejected (sign matters)
    assert not assess_resonator_feature(FPTS, y, FPTS[np.argmax(y)], dip=True)[0]
    for seed in range(8):
        y = -35 + 0.3 * np.random.default_rng(seed).standard_normal(FPTS.size)
        assert not assess_resonator_feature(FPTS, y, FPTS[np.argmax(y)], dip=False)[0]
        assert not assess_resonator_feature(FPTS, y, FPTS[np.argmin(y)], dip=True)[0]


def test_single_point_spike_fails_on_width():
    y = -35 + 0.05 * np.random.default_rng(0).standard_normal(FPTS.size)
    y[100] += 5.0
    ok, reasons, m = assess_resonator_feature(FPTS, y, FPTS[100], dip=False)
    assert not ok
    assert m["linewidth_steps"] == pytest.approx(1.0)
    assert any("frequency steps" in r for r in reasons), reasons
