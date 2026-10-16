"""Hardware-free tests for the ChiShift dispersive-shift fit (F37).

The old estimate, argmin(|S21| pi trace) - argmin(|S21| g trace), is pulled toward zero whenever
the pi trace is a mixture of |g> and |e> (pi infidelity, decay during the readout) and is
quantised to the grid step. ChiShift.display now fits both traces jointly as
|(1 - p) S(f; fr) + p S(f; fr + delta)| with shared hanger parameters, p = a (thermal) for the
g trace and p = b for the pi trace, saves delta = f_e - f_g (= 2chi) with its error, the two
populations, kappa and fr, falls back to the argmin value on a failed fit, and warns when
b < 0.6. Synthetic complex traces with random per-point phases (every point is a separate
program). See docs/experiments/chi_shift.md#analysis.

    python -m pytest tests/test_chi_shift_fit.py
"""

import matplotlib

matplotlib.use("Agg")

import warnings

import numpy as np
import pytest

from qicklab.analysis.fitting import (
    CHI_FIT_MIN_PI_POPULATION,
    dispersive_mixture_magnitude,
    fit_dispersive_shift,
    hanger_model_db,
    hanger_s21,
)
from qicklab.experiments.chi_shift import ChiShift

# ChiShift grid with the CSTQ03 defaults (TransSpan 1, TransNumPoints 101, half-open), IF axis.
CENTRE = 95.2
FPTS = CENTRE - 1.0 + (2.0 / 101) * np.arange(101)
FR, KAPPA, DEPTH, ASYM = 95.15, 0.43, 0.8, 0.1
NOISE = 0.01  # per quadrature, relative to the off-resonant line


def _traces(delta, a, b, rng, noise=NOISE, amp=3.0):
    """|I + iQ| of the g and pi traces: population mixtures of the two state responses, a
    random phase per point (separately compiled programs) and complex Gaussian noise."""

    def one(p):
        z = (1 - p) * hanger_s21(FPTS, FR, KAPPA, DEPTH, ASYM) + p * hanger_s21(
            FPTS, FR + delta, KAPPA, DEPTH, ASYM
        )
        z = amp * z * np.exp(2j * np.pi * rng.random(FPTS.size))
        z += amp * noise * (rng.standard_normal(FPTS.size) + 1j * rng.standard_normal(FPTS.size))
        return np.abs(z)

    return one(a), one(b)


def _argmin_delta(amp_g, amp_pi):
    return FPTS[np.argmin(amp_pi)] - FPTS[np.argmin(amp_g)]


def _instance(tmp_path):
    inst = object.__new__(ChiShift)
    inst.cfg = {"cavity_LO": 7.0e9}
    inst.iname = str(tmp_path / "chi.png")
    inst.titlename = "chi"
    return inst


def _data(amp_g, amp_pi):
    def res(amp):
        r = np.zeros((1, 1, 2, FPTS.size))
        r[0, 0, 0] = amp  # I = |S21|, Q = 0
        return r

    return {
        "config": {},
        "data": {"results_ground": res(amp_g), "results_01": res(amp_pi), "fpts": FPTS},
    }


def test_hanger_s21_matches_the_db_model_and_kappa_is_the_power_fwhm():
    # Same curve as hanger_model_db (asym_db = asym * pi * kappa), and |S21|^2 sits half-way
    # between the line and the dip floor at fr +- kappa/2.
    f0 = 7095.0
    qtot = f0 / KAPPA
    f = f0 + np.linspace(-2, 2, 401)
    y_db = hanger_model_db(f, f0, qtot, qtot / DEPTH, ASYM * np.pi * KAPPA, 0.0)
    np.testing.assert_allclose(20 * np.log10(np.abs(hanger_s21(f, f0, KAPPA, DEPTH, ASYM))), y_db)
    p_half = (
        np.abs(hanger_s21(np.array([f0 - KAPPA / 2, f0 + KAPPA / 2]), f0, KAPPA, DEPTH, 0.0)) ** 2
    )
    np.testing.assert_allclose(p_half, 0.5 * (1 + (1 - DEPTH) ** 2))
    # p = 0 / 1 are the pure state responses; the mixture is of amplitudes, not magnitudes.
    m0 = dispersive_mixture_magnitude(f, f0, KAPPA, DEPTH, ASYM, -0.3, 0.0, 2.0)
    m1 = dispersive_mixture_magnitude(f, f0, KAPPA, DEPTH, ASYM, -0.3, 1.0, 2.0)
    np.testing.assert_allclose(m0, 2 * np.abs(hanger_s21(f, f0, KAPPA, DEPTH, ASYM)))
    np.testing.assert_allclose(m1, 2 * np.abs(hanger_s21(f, f0 - 0.3, KAPPA, DEPTH, ASYM)))


@pytest.mark.parametrize("delta", [-0.1, -0.3])
@pytest.mark.parametrize("a", [0.0, 0.1])
@pytest.mark.parametrize("b", [0.5, 0.7, 0.9])
def test_joint_fit_recovers_delta_where_the_argmin_is_biased(delta, a, b):
    rng = np.random.default_rng(int(1000 * (b + a) - 100 * delta))
    pulls, argmins, fits = [], [], []
    for _ in range(8):
        amp_g, amp_pi = _traces(delta, a, b, rng)
        fit = fit_dispersive_shift(FPTS, amp_g, amp_pi)
        assert fit["ok"], fit["error"]
        pulls.append((fit["delta"] - delta) / fit["delta_err"])
        fits.append(fit)
        argmins.append(_argmin_delta(amp_g, amp_pi))
    # Each fit within 3.5 standard errors; the mean pull consistent with no bias.
    assert np.max(np.abs(pulls)) < 3.5
    assert abs(np.mean(pulls)) < 3 / np.sqrt(len(pulls)) + 0.5
    # The fitted populations and linewidth follow the truth.
    assert np.mean([f["b"] for f in fits]) == pytest.approx(b, abs=0.08)
    assert np.mean([f["kappa"] for f in fits]) == pytest.approx(KAPPA, rel=0.1)
    assert np.mean([f["fr"] for f in fits]) == pytest.approx(FR, abs=0.01)
    for f in fits:
        # Only delta (= 2chi) is reported, so "_err" cannot mean two different quantities.
        assert "chi" not in f and "chi_err" not in f
    if b <= 0.7:
        # The argmin is pulled toward zero (by 20-35 % at b = 0.5); the fit is not.
        bias_argmin = abs(np.mean(argmins) - delta) / abs(delta)
        bias_fit = abs(np.mean([f["delta"] for f in fits]) - delta) / abs(delta)
        assert bias_fit < 0.5 * bias_argmin
        if b == 0.5:
            assert bias_argmin > 0.2


def test_fit_on_noise_is_not_ok_and_display_falls_back_to_the_argmin(tmp_path):
    rng = np.random.default_rng(5)
    amp_g = np.hypot(*rng.normal(0, 2, (2, FPTS.size)))
    amp_pi = np.hypot(*rng.normal(0, 2, (2, FPTS.size)))
    fit = fit_dispersive_shift(FPTS, amp_g, amp_pi)
    assert not fit["ok"] and fit["error"]

    inst = _instance(tmp_path)
    data = _data(amp_g, amp_pi)
    inst.display(data=data, plotDisp=False)
    d = data["data"]
    assert not d["chi_fit_ok"]
    assert d["chi_argmin"] == pytest.approx(_argmin_delta(amp_g, amp_pi))
    assert d["chi_fit"] == d["chi_argmin"]
    for key in ("chi_err", "p_g_exc", "p_pi_exc", "kappa_fit", "fr_fit"):
        assert np.isnan(d[key]), key
    assert np.all(np.isnan(d["fit_ground"])) and d["fit_ground"].shape == FPTS.shape


def test_fit_rejects_unusable_input_without_raising():
    assert not fit_dispersive_shift(FPTS, np.ones(5), np.ones(FPTS.size))["ok"]
    bad = np.ones(FPTS.size)
    bad[3] = np.nan
    assert not fit_dispersive_shift(FPTS, bad, np.ones(FPTS.size))["ok"]
    assert not fit_dispersive_shift(FPTS, np.zeros(FPTS.size), np.zeros(FPTS.size))["ok"]


def test_display_saves_the_fit_and_warns_on_a_bad_pi_pulse(tmp_path):
    rng = np.random.default_rng(7)
    amp_g, amp_pi = _traces(-0.3, 0.05, 0.9, rng)
    data = _data(amp_g, amp_pi)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)  # a good pi pulse must not warn
        _instance(tmp_path).display(data=data, plotDisp=False)
    d = data["data"]
    assert d["chi_fit_ok"]
    assert d["chi_fit"] == pytest.approx(-0.3, abs=4 * d["chi_err"])
    assert 0 < d["chi_err"] < 0.02
    assert d["p_pi_exc"] == pytest.approx(0.9, abs=0.05)
    assert 0 <= d["p_g_exc"] <= 0.5
    assert d["kappa_fit"] == pytest.approx(KAPPA, rel=0.1)
    assert d["fr_fit"] == pytest.approx(FR, abs=0.01)
    assert d["chi_argmin"] == pytest.approx(_argmin_delta(amp_g, amp_pi))
    assert d["fit_01"].shape == FPTS.shape and np.all(np.isfinite(d["fit_01"]))

    amp_g, amp_pi = _traces(-0.3, 0.05, 0.55, rng)
    data = _data(amp_g, amp_pi)
    with pytest.warns(UserWarning, match="bad pi pulse"):
        _instance(tmp_path).display(data=data, plotDisp=False)
    assert data["data"]["chi_fit_ok"]
    assert data["data"]["p_pi_exc"] < CHI_FIT_MIN_PI_POPULATION


@pytest.mark.parametrize("delta, b", [(-0.03, 0.9), (-0.05, 0.5)])
def test_a_small_shift_keeps_the_fit_and_is_only_flagged_unresolved(tmp_path, delta, b):
    # Below ~kappa/4 the shift is often within 2 errors of zero. Such a fit stays ok (resolved
    # False) and its delta is saved: gating chi_fit on |delta| >= 2 err would keep only the fits
    # that scattered away from zero and swap the rest for the argmin (biased toward zero).
    a = 0.05
    rng = np.random.default_rng(int(1000 * b - 1000 * delta) + 11)
    fits = [fit_dispersive_shift(FPTS, *_traces(delta, a, b, rng)) for _ in range(24)]
    for fit in fits:
        assert fit["ok"], fit["error"]
        assert fit["resolved"] == (abs(fit["delta"]) >= 2 * fit["delta_err"])
    deltas = np.array([f["delta"] for f in fits])
    resolved = np.array([f["resolved"] for f in fits])
    assert 0 < resolved.sum() < len(fits)  # the regime the gate used to discard
    # The unconditional mean is closer to the truth than the mean of the resolved fits.
    assert abs(np.mean(deltas) - delta) < abs(np.mean(deltas[resolved]) - delta)
    # Here only the product (b - a) * delta is constrained: the populations are pulled
    # together and delta outward, but the product is recovered (docs: chi_shift.md#analysis).
    prod = np.array([(f["b"] - f["a"]) * f["delta"] for f in fits])
    assert np.mean(prod) == pytest.approx((b - a) * delta, abs=3 * np.std(prod) / np.sqrt(24))
    # display keeps an unresolved fit's value in chi_fit (not the argmin).
    while True:
        amp_g, amp_pi = _traces(delta, a, b, rng)
        fit = fit_dispersive_shift(FPTS, amp_g, amp_pi)
        if fit["ok"] and not fit["resolved"]:
            break
    data = _data(amp_g, amp_pi)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # b is pulled toward 0.5 here
        _instance(tmp_path).display(data=data, plotDisp=False)
    d = data["data"]
    assert d["chi_fit_ok"]
    assert d["chi_fit"] == pytest.approx(fit["delta"]) and np.isfinite(d["chi_err"])
    assert abs(d["chi_fit"]) < 2 * d["chi_err"]


def test_no_shift_is_fitted_ok_and_centred_on_zero():
    # delta = 0: the populations drop out and the linearised error is unreliable (some fits
    # report a tiny one), so 'resolved' is not a calibrated 2-sigma test here; the fitted
    # values still scatter about zero and are kept.
    rng = np.random.default_rng(17)
    deltas = []
    for _ in range(24):
        fit = fit_dispersive_shift(FPTS, *_traces(0.0, 0.05, 0.9, rng))
        assert fit["ok"], fit["error"]
        deltas.append(fit["delta"])
    assert abs(np.mean(deltas)) < 3 * np.std(deltas) / np.sqrt(len(deltas))


def test_display_falls_back_to_the_argmin_when_the_fit_raises(tmp_path, monkeypatch, capsys):
    # The try/except in display: a fitter exception must cost neither the plot nor the record.
    import qicklab.experiments.chi_shift as chi_shift

    def boom(*args, **kwargs):
        raise RuntimeError("fitter exploded")

    monkeypatch.setattr(chi_shift, "fit_dispersive_shift", boom)
    amp_g, amp_pi = _traces(-0.3, 0.05, 0.9, np.random.default_rng(3))
    data = _data(amp_g, amp_pi)
    inst = _instance(tmp_path)
    inst.display(data=data, plotDisp=False)
    d = data["data"]
    assert not d["chi_fit_ok"]
    assert d["chi_fit"] == d["chi_argmin"] == pytest.approx(_argmin_delta(amp_g, amp_pi))
    for key in ("chi_err", "p_g_exc", "p_pi_exc", "kappa_fit", "fr_fit"):
        assert np.isnan(d[key]), key
    assert np.all(np.isnan(d["fit_01"])) and d["fit_01"].shape == FPTS.shape
    assert "fitter exploded" in capsys.readouterr().out
    assert (tmp_path / "chi.png").exists()
