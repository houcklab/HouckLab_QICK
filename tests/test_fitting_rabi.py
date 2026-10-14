"""Hardware-free tests for the amplitude-Rabi cosine fit (docs/experiments/amplitude_rabi.md):
pi gain = P/2 from a two-seed (FFT peak, gain span) fit, quality flags, guarded displays.

    python -m pytest tests/test_fitting_rabi.py
"""

import os
import warnings

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

from qicklab.analysis.fitting import (
    RABI_FLAG_PHASE,
    RABI_FLAG_PI_OUT_OF_RANGE,
    RABI_FLAG_UNDERSAMPLED,
    fit_rabi_cosine,
)
from qicklab.experiments.rabi import AmplitudeRabiFF, AmplitudeRabiFF_N

# run_amplitude_rabi's grid with the defaults: step = int(10000 / 101) = 99, 101 points
X = np.arange(101) * 99.0
SPAN = X[-1] - X[0]


def _rabi(pi_gain, sign=1, noise=0.03, seed=0, x=X, offset=0.3):
    """P_e = (1 - cos(pi x / pi_gain)) / 2 with Gaussian noise (fraction of the contrast)."""
    rng = np.random.default_rng(seed)
    return offset + sign * (1 - np.cos(np.pi * x / pi_gain)) / 2 + noise * rng.normal(size=x.size)


def _fit(*args, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # OptimizeWarning on the under-sampled cases
        return fit_rabi_cosine(*args, **kwargs)


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("periods", [1.1, 1.65, 2.5])
def test_pi_gain_recovered_with_a_period_or_more(periods, sign, seed):
    # The single-start fit (P seed = span) failed from ~1.5 periods on (pi=2000 on this grid
    # gave 4346, inside the range); the old grid search returned the 3pi / 5pi extremum.
    pi_gain = SPAN / periods / 2
    f = _fit(X, _rabi(pi_gain, sign, seed=seed))
    assert f["pi_gain"] == pytest.approx(pi_gain, rel=0.03)
    assert f["pi_gain"] == f["P"] / 2 and f["dpi_gain"] == f["dP"] / 2
    assert 0 < f["dpi_gain"] < 0.03 * pi_gain
    assert f["n_periods"] == pytest.approx(periods, rel=0.03)
    assert f["flags"] == [] and f["flag_code"] == 0


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("sign", [1, -1])
def test_pi_gain_recovered_just_under_one_period(sign, seed):
    # 0.75..1 period: the FFT peak is poorly defined; the span seed carries the fit.
    pi_gain = SPAN / 0.8 / 2
    f = _fit(X, _rabi(pi_gain, sign, seed=seed))
    assert f["pi_gain"] == pytest.approx(pi_gain, rel=0.03)
    assert f["flag_code"] == 0


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize(
    "periods, expected",
    [
        (0.7, RABI_FLAG_UNDERSAMPLED),  # pi inside the sweep but less than 3/4 period seen
        (0.4, RABI_FLAG_UNDERSAMPLED | RABI_FLAG_PI_OUT_OF_RANGE),  # pi beyond max gain
    ],
)
def test_undersampled_sweeps_are_flagged(periods, expected, sign, seed):
    f = _fit(X, _rabi(SPAN / periods / 2, sign, seed=seed))
    assert f["flag_code"] & expected == expected
    assert len(f["flags"]) == bin(f["flag_code"]).count("1")


# (points, periods, sign, seed) on linspace(0, 10000, points) that, before P was bounded
# below by 2 grid steps, converged from the (P = span, -A) start onto the sub-Nyquist alias
# f_s - f or f_s + f (P ~ 40..270) with the same residual as the true period, and won.
_ALIASED_BEFORE_THE_NYQUIST_BOUND = [
    (11, 1.5, 1, 11),
    (11, 1.5, -1, 84),
    (11, 2.0, 1, 69),
    (21, 2.5, 1, 8),
    (31, 2.5, 1, 170),
    (31, 2.5, -1, 178),
    (31, 3.5, -1, 87),
]


@pytest.mark.parametrize("points, periods, sign, seed", _ALIASED_BEFORE_THE_NYQUIST_BOUND)
def test_coarse_grid_does_not_return_an_aliased_period(points, periods, sign, seed):
    x = np.linspace(0, 10000, points)
    pi_gain = 10000 / periods / 2
    f = _fit(x, _rabi(pi_gain, sign, seed=seed, x=x))
    assert f["P"] >= 2 * (x[1] - x[0])
    assert f["pi_gain"] == pytest.approx(pi_gain, rel=0.03)
    assert f["flag_code"] == 0


@pytest.mark.parametrize("points", [11, 21, 31, 41])
@pytest.mark.parametrize("sign", [1, -1])
def test_pi_gain_recovered_on_coarse_grids(points, sign):
    # Quick sweeps (expts ~ 11..41) with at least 1.5 periods and >= 4 points per period.
    x = np.linspace(0, 10000, points)
    for periods in (1.5, 2.0, 2.5, 3.5):
        if (points - 1) / periods < 4:
            continue
        pi_gain = 10000 / periods / 2
        for seed in range(10):
            f = _fit(x, _rabi(pi_gain, sign, seed=seed, x=x))
            assert f["pi_gain"] == pytest.approx(pi_gain, rel=0.03), (periods, seed)
            assert f["flag_code"] == 0, (periods, seed)


def test_phase_flag_when_the_trace_does_not_start_at_an_extremum():
    # e.g. a sweep that does not start at zero drive while x is taken as absolute gain
    pi_gain = SPAN / 2.5 / 2
    y = 0.3 + np.cos(np.pi * X / pi_gain + 1.0) / 2
    f = _fit(X, y)
    assert f["pi_gain"] == pytest.approx(pi_gain, rel=1e-6)
    assert f["flag_code"] == RABI_FLAG_PHASE


def test_yfit_follows_the_caller_order_and_skips_nan():
    pi_gain = SPAN / 1.65 / 2
    y = _rabi(pi_gain)
    order = np.random.default_rng(3).permutation(X.size)
    x_s, y_s = X[order], y[order].copy()
    y_s[5] = np.nan
    f = _fit(x_s, y_s)
    assert f["pi_gain"] == pytest.approx(pi_gain, rel=0.03)
    ref = f["popt"][0] + f["popt"][1] * np.cos(2 * np.pi * x_s / f["P"] + f["phi"])
    np.testing.assert_allclose(f["yfit"], ref)


def test_flat_data_raises():
    with pytest.raises(RuntimeError):
        fit_rabi_cosine(X, np.full(X.size, 0.5))


def _data(i, q, x=X):
    return {"data": {"x_pts": x, "avgi": [[i]], "avgq": [[q]]}}


def test_amplitude_rabi_ff_display_stores_pi_gain_and_flag(tmp_path):
    inst = AmplitudeRabiFF(path="AmplitudeRabi", outerFolder=str(tmp_path) + os.sep, cfg={})
    pi_gain = SPAN / 2.5 / 2
    data = _data(_rabi(pi_gain), np.full(X.size, 0.1) + 0.01 * np.sin(X))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        inst.display(data=data, plotDisp=False, fit=True)
    assert float(data["data"]["fit_i_pi_gain"]) == pytest.approx(pi_gain, rel=0.03)
    assert int(data["data"]["fit_i_flag"]) == 0
    assert os.path.exists(inst.iname)


def test_amplitude_rabi_ff_n_display_survives_a_failed_fit(tmp_path):
    # The fit used to be unguarded here: a flat quadrature raised out of the display.
    inst = AmplitudeRabiFF_N(path="AmplitudeRabi", outerFolder=str(tmp_path) + os.sep, cfg={})
    pi_gain = SPAN / 1.65 / 2
    flat = np.full(X.size, 0.1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        inst.display(data=_data(_rabi(pi_gain), flat), fit=True, rotate=False)
    assert inst.fit_q is None
    assert inst.fit_i["pi_gain"] == pytest.approx(pi_gain, rel=0.03)
    assert os.path.exists(inst.iname)
