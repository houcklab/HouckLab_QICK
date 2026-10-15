"""Hardware-free tests for the bounded, guarded single-exponential fit (T1 / T2E) and for the
T1FF / T2EMUX displays that save its result (docs/experiments/t1.md, docs/experiments/t2_echo.md).

    python -m pytest tests/test_exp_decay_fit.py
"""

import os
import warnings

import matplotlib

matplotlib.use("Agg")

import h5py
import numpy as np
import pytest
from scipy.optimize import curve_fit

import qicklab.analysis.fitting as fitting_mod
import qicklab.experiments.t1 as t1_mod
import qicklab.experiments.t2_echo as t2e_mod
from qicklab.analysis.fitting import exp_decay, fit_exp_decay
from qicklab.core.experiment import finish
from qicklab.experiments.t1 import T1FF
from qicklab.experiments.t2_echo import T2EMUX

X = np.arange(100) * 5.0  # 0 ... 495 us, the T1 defaults
SPAN = X[-1] - X[0]
FIT_KEYS = ("ok", "us", "err_us", "a", "c", "popt", "perr", "rotation_rad")


def _decay(T, a=1.0, c=0.1, noise=0.02, seed=0, x=X):
    rng = np.random.default_rng(seed)
    return exp_decay(x, a, T, c) + rng.normal(0, noise, x.size)


def _old_unbounded(x, y):
    """The pre-2026-10-14 fit: unbounded curve_fit from the same start values, |T| reported."""
    a = y[0] - y[-1]
    c = y[-1]
    i = np.argmin(np.abs(y - (a / 2.6 + c)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        popt, pcov = curve_fit(exp_decay, x, y, p0=[a, x[i], c])
    return abs(popt[1]), np.sqrt(np.diag(pcov))[1]


@pytest.mark.parametrize("T_true", [20.0, 80.0, 150.0])
@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_recovers_T_within_3_percent(T_true, sign):
    fit = fit_exp_decay(X, _decay(T_true, a=sign))
    assert fit["ok"], fit["error"]
    assert fit["error"] is None
    assert fit["T"] == pytest.approx(T_true, rel=0.03)
    assert np.sign(fit["a"]) == sign
    assert fit["popt"][1] == fit["T"] and fit["perr"][1] == fit["T_err"]
    assert fit["yfit"].shape == X.shape
    assert fit["T_bounds"] == (2.5, 20 * SPAN)


@pytest.mark.parametrize("T_true", [30.0, 80.0, 150.0])
def test_same_value_as_old_unbounded_fit_on_well_behaved_data(T_true):
    y = _decay(T_true, seed=1)
    T_old, err_old = _old_unbounded(X, y)
    fit = fit_exp_decay(X, y)
    assert fit["ok"]
    assert fit["T"] == pytest.approx(T_old, rel=1e-5)
    assert fit["T_err"] == pytest.approx(err_old, rel=1e-3)


@pytest.mark.parametrize("seed", range(20))
def test_noise_only_does_not_raise_and_is_not_ok(seed):
    y = np.random.default_rng(seed).normal(0, 1, X.size)
    fit = fit_exp_decay(X, y)
    assert fit["ok"] is False
    assert isinstance(fit["error"], str) and fit["error"]


@pytest.mark.parametrize("seed", [2, 10, 42])
def test_runaway_is_bounded(seed):
    # On these noise traces the old unbounded fit ran away to T ~ 1e6 us (2000 x the sweep).
    y = np.random.default_rng(seed).normal(0, 1, X.size)
    assert _old_unbounded(X, y)[0] > 1e5
    fit = fit_exp_decay(X, y)
    assert fit["ok"] is False
    assert "bound" in fit["error"]  # the upper-bound rule decides, not another check
    assert fit["T"] == pytest.approx(20 * SPAN, rel=1e-3)


def test_decay_much_longer_than_sweep_is_not_ok():
    fit = fit_exp_decay(X, _decay(1e5))
    assert fit["ok"] is False
    assert "bound" in fit["error"]
    assert fit["T"] == pytest.approx(20 * SPAN, rel=1e-3)


def test_decay_faster_than_sampling_hits_lower_bound():
    fit = fit_exp_decay(X, _decay(0.5))
    assert fit["ok"] is False
    assert "bound" in fit["error"]
    assert fit["T"] == pytest.approx(2.5, rel=1e-3)


def _patch_pcov(monkeypatch, make_pcov):
    """Run the real bounded fit but replace its covariance, to pin one ok rule at a time."""
    real = fitting_mod.curve_fit

    def fake(*args, **kwargs):
        popt, pcov = real(*args, **kwargs)
        return popt, make_pcov(popt)

    monkeypatch.setattr(fitting_mod, "curve_fit", fake)


def test_patched_small_covariance_is_ok(monkeypatch):
    # Control for the two tests below: the patch itself does not make a good fit fail.
    _patch_pcov(monkeypatch, lambda p: np.diag([1e-6, (0.01 * p[1]) ** 2, 1e-6]))
    fit = fit_exp_decay(X, _decay(80.0))
    assert fit["ok"], fit["error"]
    assert fit["T_err"] == pytest.approx(0.01 * fit["T"])


def test_T_err_not_below_T_is_not_ok_and_keeps_values(monkeypatch):
    # a is many sigmas and T is inside the bounds, so only the T_err >= T rule can reject it.
    _patch_pcov(monkeypatch, lambda p: np.diag([1e-6, (2.0 * p[1]) ** 2, 1e-6]))
    fit = fit_exp_decay(X, _decay(80.0))
    assert fit["ok"] is False
    assert fit["error"].startswith("T_err")
    assert fit["T"] == pytest.approx(80.0, rel=0.03)  # value kept for a not-ok fit
    assert fit["T_err"] == pytest.approx(2.0 * fit["T"])
    assert fit["popt"][1] == fit["T"]


@pytest.mark.parametrize("bad", [np.inf, np.nan])
def test_non_finite_covariance_is_not_ok(monkeypatch, bad):
    _patch_pcov(monkeypatch, lambda p: np.full((3, 3), bad))
    fit = fit_exp_decay(X, _decay(80.0))
    assert fit["ok"] is False
    assert "covariance" in fit["error"]
    assert fit["T"] == pytest.approx(80.0, rel=0.03)


@pytest.mark.parametrize(
    "x, y",
    [
        (X, np.full(X.size, 0.3)),  # constant
        (X[:3], np.array([1.0, 0.5, 0.2])),  # too short
        (X, np.where(np.arange(X.size) == 5, np.nan, _decay(50.0))),  # NaN
        (np.zeros(10), np.arange(10.0)),  # no x spread
        (X, _decay(50.0)[:-1]),  # length mismatch
    ],
)
def test_degenerate_inputs_do_not_raise(x, y):
    fit = fit_exp_decay(x, y)
    assert fit["ok"] is False
    assert np.isnan(fit["T"]) and np.isnan(fit["T_err"])
    assert fit["popt"].shape == (3,) and fit["perr"].shape == (3,)


# ---------------------------------------------------------------- displays


def _data(avgi, x=X):
    avgi = np.asarray(avgi, dtype=float)
    return {
        "data": {
            "x_pts": x,
            "avgi": avgi[None, None, :],
            "avgq": np.zeros((1, 1, x.size)),
            "qfreq": 4000.0,
        }
    }


EXPTS = {
    # class, prefix, cfg (rotation 0 keeps I as given), h5 suffix
    "T1FF": (T1FF, "t1", {"Qubit_number": 1, "rotation_angle": 0.0}, "_Q1.h5"),
    "T2EMUX": (T2EMUX, "t2e", {"num_pi_pulses": 1, "rotation_angle": 0.0}, "_n1.h5"),
}


def _run(tmp_path, name, avgi):
    cls, prefix, cfg, suffix = EXPTS[name]
    inst = cls(path=name, outerFolder=str(tmp_path) + os.sep, cfg=dict(cfg))
    data = _data(avgi)
    err = finish(cls, inst, data, plotDisp=False)
    assert err is None  # the display itself never raises
    assert inst.fname.endswith(suffix)
    for png in ("I_Data.png", "Q_Data.png"):
        assert os.path.exists(inst.iname[:-4] + png)
    with h5py.File(inst.fname, "r") as f:
        saved = {k: f[k][()] for k in f}
    return inst, prefix, saved


@pytest.mark.parametrize("name", sorted(EXPTS))
def test_display_saves_fit_fields(tmp_path, name):
    inst, prefix, saved = _run(tmp_path, name, _decay(80.0))
    assert inst.fit["ok"]
    for k in FIT_KEYS:
        assert f"{prefix}_fit_{k}" in saved
    assert saved[f"{prefix}_fit_ok"] == 1.0
    assert saved[f"{prefix}_fit_us"] == pytest.approx(80.0, rel=0.03)
    assert saved[f"{prefix}_fit_us"] == pytest.approx(inst.fit["T"], rel=1e-12)
    assert saved[f"{prefix}_fit_err_us"] == pytest.approx(inst.fit["T_err"], rel=1e-12)
    np.testing.assert_allclose(saved[f"{prefix}_fit_popt"], inst.fit["popt"])
    np.testing.assert_allclose(saved[f"{prefix}_fit_perr"], inst.fit["perr"])
    assert saved[f"{prefix}_fit_rotation_rad"] == 0.0
    assert "x_pts" in saved and "avgi" in saved  # the raw record is still there


@pytest.mark.parametrize("name", sorted(EXPTS))
def test_display_on_noise_saves_not_ok(tmp_path, name):
    inst, prefix, saved = _run(tmp_path, name, np.random.default_rng(3).normal(0, 1, X.size))
    assert inst.fit["ok"] is False
    assert saved[f"{prefix}_fit_ok"] == 0.0
    assert saved[f"{prefix}_fit_us"] <= 20 * SPAN * (1 + 1e-9) or np.isnan(
        saved[f"{prefix}_fit_us"]
    )


@pytest.mark.parametrize("name", sorted(EXPTS))
def test_display_survives_a_fit_exception(tmp_path, name, monkeypatch):
    mod = t1_mod if name == "T1FF" else t2e_mod

    def boom(x, y):
        raise RuntimeError("Optimal parameters not found")

    monkeypatch.setattr(mod, "fit_exp_decay", boom)
    inst, prefix, saved = _run(tmp_path, name, _decay(80.0))
    assert inst.fit == {"ok": False, "error": "RuntimeError('Optimal parameters not found')"}
    assert saved[f"{prefix}_fit_ok"] == 0.0
    for k in ("us", "err_us", "a", "c"):
        assert np.isnan(saved[f"{prefix}_fit_{k}"])
    assert np.all(np.isnan(saved[f"{prefix}_fit_popt"]))
