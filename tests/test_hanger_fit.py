"""Hardware-free tests for the hanger fit's parameterisation and error bars (F36).

|S21| of the hanger model depends on a = Qtot/Qext only through (1 - a)^2, so a magnitude fit
in (Qtot, Qext) could land on the unphysical twin a -> 2 - a (Qtot > Qext, same curve), where
Qext and kappa_ext are wrong and the old |1/(1/Qtot - 1/Qext)| hid it. fit_hanger_transmission
now fits (f0, Qint, Qext, asym, offset) with Qint, Qext > 0, so Qtot < Qext always, still
returns popt as [f0, Qtot, Qext, asym, offset], and gives errors from the full covariance under
Gaussian IQ noise (dB noise ~ 1/|S21|). Monte Carlo on synthetic complex data checks the pulls.
See docs/experiments/transmission_fit.md#analysis.

    python -m pytest tests/test_hanger_fit.py
"""

import matplotlib

matplotlib.use("Agg")

import warnings

import numpy as np
import pytest

from qicklab.analysis.fitting import (
    fit_hanger_transmission,
    hanger_model_db,
    hanger_model_db_qint,
    hanger_startpoint,
)
from qicklab.experiments.transmission import CavitySpecFF

FPTS = np.linspace(7090.0, 7100.0, 201)  # +-5 MHz, 201 points (CSTQ03 Transmission_params)
F0 = 7095.2


def _fit(y, startpoint=None, fpts=FPTS):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return fit_hanger_transmission(
            fpts, amp_db=y, startpoint=startpoint or hanger_startpoint(fpts, y)
        )


def _complex_trace(qint, qext, noise, rng, asym=0.0, fpts=FPTS):
    """|S21| in dB of a hanger at F0 on a -35 dB line plus complex Gaussian noise of rms
    ``noise`` per quadrature (relative to the line)."""
    qtot = 1 / (1 / qint + 1 / qext)
    s21 = 1 - (qtot / qext - 2j * qtot * asym / (2 * np.pi * F0)) / (
        1 + 2j * qtot * (fpts - F0) / F0
    )
    z = s21 + noise * (rng.standard_normal(fpts.size) + 1j * rng.standard_normal(fpts.size))
    return 20 * np.log10(np.abs(z)) - 35.0


def test_magnitude_model_is_invariant_under_the_twin_branch():
    # The degeneracy the reparameterisation removes: a = Qtot/Qext and 2 - a give one curve.
    qtot = 1.5e4
    for asym in (0.0, 0.3):
        y_phys = hanger_model_db(FPTS, F0, qtot, qtot / 0.8, asym, -35.0)
        y_twin = hanger_model_db(FPTS, F0, qtot, qtot / 1.2, asym, -35.0)
        np.testing.assert_allclose(y_phys, y_twin, atol=1e-9)
    np.testing.assert_allclose(
        hanger_model_db_qint(FPTS, F0, 3e4, 3e4, 0.0, -35.0),
        hanger_model_db(FPTS, F0, 1.5e4, 3e4, 0.0, -35.0),
    )


@pytest.mark.parametrize("qtot0, qext0", [(1.5e4, 1.0e4), (1.5e4, 1.5e4), (1.0e4, 2.5e4)])
def test_fit_cannot_land_on_the_qtot_above_qext_twin(qtot0, qext0):
    # Qi = Qc = 3e4. A start at Qtot > Qext (where the old fit stayed: Qext ~ 1e4) or at
    # Qtot = Qext must still return the physical Qext ~ 3e4 with Qtot < Qext and Qint > 0.
    y = _complex_trace(3e4, 3e4, 0.005, np.random.default_rng(0))
    r = _fit(y, startpoint=[F0, qtot0, qext0, 0.0, -35.0])
    f0, qtot, qext, _, _ = r["popt"]
    assert qtot < qext
    assert f0 == pytest.approx(F0, abs=0.01)
    assert qext == pytest.approx(3e4, rel=0.05)
    assert r["Qint"] == pytest.approx(3e4, rel=0.05)
    assert r["Qint"] == pytest.approx(1 / (1 / qtot - 1 / qext), rel=1e-9)
    assert r["kappa_ext"] == pytest.approx(F0 / 3e4, rel=0.05)


def test_popt_layout_and_covariance_are_consistent():
    y = _complex_trace(1e5, 2e4, 0.01, np.random.default_rng(1))
    r = _fit(y)
    f0, qtot, qext, asym, offset = r["popt"]
    fq, qint, qext_q, asym_q, offset_q = r["popt_qint"]
    assert (fq, qext_q, asym_q, offset_q) == (f0, qext, asym, offset)
    assert qtot == pytest.approx(1 / (1 / qint + 1 / qext), rel=1e-12)
    assert r["model"] is hanger_model_db
    np.testing.assert_allclose(
        r["model"](FPTS, *r["popt"]), hanger_model_db_qint(FPTS, *r["popt_qint"])
    )
    assert r["perr"] == pytest.approx(np.sqrt(np.diag(r["pcov"])))
    assert r["Qext_err"] == pytest.approx(r["perr"][2])
    assert r["Qtot_err"] == pytest.approx(r["perr"][1])
    assert r["Qint_err"] == pytest.approx(np.sqrt(r["pcov_qint"][1, 1]))
    assert r["kappa_tot"] == pytest.approx(abs(f0) / qtot)
    assert r["kappa_ext"] == pytest.approx(abs(f0) / qext)
    c = r["pcov_qint"]
    g = np.array([1 / qtot, -f0 / qint**2, -f0 / qext**2])
    assert r["kappa_tot_err"] == pytest.approx(np.sqrt(g @ c[:3, :3] @ g))
    # Qtot and Qext are strongly correlated: Qint's error from their diagonal errors alone
    # (what the old Qint = |1/(1/Qtot - 1/Qext)| would have given) overstates it (1.65x here).
    rho = r["pcov"][1, 2] / (r["perr"][1] * r["perr"][2])
    assert rho > 0.5
    naive = np.hypot(qint**2 / qtot**2 * r["perr"][1], qint**2 / qext**2 * r["perr"][2])
    assert naive > 1.4 * r["Qint_err"]


def test_startpoint_seeds_offset_and_qext_from_the_trace():
    qtot = F0 / 0.4
    y = hanger_model_db(FPTS, F0, qtot, qtot / 0.8, 0.0, -35.0)  # 14 dB dip
    f0, qtot0, qext0, asym0, offset0 = hanger_startpoint(FPTS, y)
    assert f0 == FPTS[np.argmin(y)]
    assert qtot0 == pytest.approx(abs(f0) / 1.0)  # |f0| / (span/10)
    assert offset0 == pytest.approx(-35.0, abs=0.05)
    assert qtot0 / qext0 == pytest.approx(0.8, abs=0.01)  # 1 - 10^(-depth/20)
    assert asym0 == 0.0
    # no dip (or a peak) -> ratio clipped, still Qtot < Qext
    _, qt, qe, _, _ = hanger_startpoint(FPTS, np.full(FPTS.size, -35.0))
    assert qt / qe == pytest.approx(0.01)


@pytest.mark.parametrize(
    "qint, qext, span",
    [(1e5, 2e4, 10.0), (3e4, 3e4, 10.0), (2e6, 2e6, 0.1)],
    ids=["overcoupled", "critical", "high-Q"],
)
def test_error_bars_match_the_monte_carlo_scatter(qint, qext, span):
    # Gaussian IQ noise of 1% of the line per quadrature. Correct 1-sigma errors give a median
    # |pull| of 0.67 and ~95% of pulls within 2 sigma; the old unweighted-dB pcov gave a median
    # |pull| of ~1.8 on Qtot for (1e5, 2e4) (errors ~2.7x too small). The high-Q case (Qtot 1e6,
    # kappa 7 kHz on a 0.1 MHz span) pins the f0 error: a finite-difference f0 step of 1e-6 |f0|
    # (= Qtot * 1e-6 linewidths) made perr_f0 1.9x too large there (median |pull| 0.31).
    rng = np.random.default_rng(11)
    fpts = np.linspace(F0 - span / 2, F0 + span / 2, 201)
    qtot = 1 / (1 / qint + 1 / qext)
    truth = {
        "f0": F0,
        "Qtot": qtot,
        "Qint": qint,
        "Qext": qext,
        "kappa_tot": F0 / qtot,
        "kappa_ext": F0 / qext,
    }
    pulls = {k: [] for k in truth}
    for _ in range(120):
        r = _fit(_complex_trace(qint, qext, 0.01, rng, fpts=fpts), fpts=fpts)
        assert r["popt"][1] < r["popt"][2]
        value = dict(r, f0=r["popt"][0], Qtot=r["popt"][1], Qext=r["popt"][2])
        r = dict(r, f0_err=r["perr"][0])
        for k, v in truth.items():
            pulls[k].append((value[k] - v) / r[k + "_err"])
    for k, p in pulls.items():
        p = np.abs(np.asarray(p))
        assert 0.5 < np.median(p) < 0.9, (k, np.median(p))
        assert np.mean(p < 2) > 0.88, (k, np.mean(p < 2))


def test_display_saves_the_error_keys(tmp_path):
    rng = np.random.default_rng(2)
    y = _complex_trace(1e5, 2e4, 0.005, rng)
    inst = object.__new__(CavitySpecFF)
    inst.cfg = {"cavity_LO": 0.0, "pulse_freq": F0}
    inst.iname = str(tmp_path / "trans.png")
    results = np.zeros((1, 1, 2, FPTS.size))
    results[0, 0, 0] = 10 ** (y / 20)
    data = {"config": inst.cfg, "data": {"results": results, "fpts": FPTS}}
    inst.display(data=data, plotDisp=False, fit=True)
    d = data["data"]
    r = _fit(y)
    np.testing.assert_allclose(d["hanger_fit_popt"], r["popt"], rtol=1e-4, atol=1e-6)
    np.testing.assert_allclose(d["hanger_fit_perr"], r["perr"], rtol=1e-3)
    assert float(d["hanger_fit_Qtot"]) < float(d["hanger_fit_Qext"])
    for key, rkey in [
        ("hanger_fit_Qtot_err", "Qtot_err"),
        ("hanger_fit_Qext_err", "Qext_err"),
        ("hanger_fit_Qint_err", "Qint_err"),
        ("hanger_fit_kappa_tot_mhz_err", "kappa_tot_err"),
        ("hanger_fit_kappa_ext_mhz_err", "kappa_ext_err"),
    ]:
        assert float(d[key]) == pytest.approx(r[rkey], rel=1e-3)
        assert 0 < float(d[key]) < np.inf
    assert float(d["hanger_fit_Qint"]) == pytest.approx(1e5, rel=0.15)
    assert float(d["hanger_fit_Qext"]) == pytest.approx(2e4, rel=0.05)
