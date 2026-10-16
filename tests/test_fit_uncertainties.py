"""Hardware-free tests for the uncertainties saved with each calibrated quantity (F70).

QubitSpecSliceFF saves ``lorentz_center_err`` / ``lorentz_fwhm_err`` (sqrt(pcov[2, 2]) and
2 sqrt(pcov[3, 3]) of each accepted Lorentzian; NaN, never an exception, for a non-finite
covariance), AmplitudeRabiFF saves ``fit_*_perr`` and ``fit_*_pi_gain_err`` (= dP/2),
AmplitudeRabiFF_N writes its fit results and ``rotation_phase`` into the saved payload (and a
failed fit still saves the record), and CavitySpecFF saves ``hanger_fit_pcov``. See
docs/experiments/two_tone_spec.md, amplitude_rabi.md and transmission_fit.md (Outputs).

    python -m pytest tests/test_fit_uncertainties.py
"""

import os
import warnings

import matplotlib

matplotlib.use("Agg")

import h5py
import numpy as np
import pytest

import qicklab.experiments.qubit_spec as qs
import qicklab.experiments.rabi as rabi
from qicklab.analysis.fitting import fit_rabi_cosine, hanger_model_db
from qicklab.core.experiment import finish
from qicklab.experiments.qubit_spec import QubitSpecSliceFF, lorentz_fit_errors
from qicklab.experiments.rabi import AmplitudeRabiFF, AmplitudeRabiFF_N
from qicklab.experiments.transmission import CavitySpecFF

# --- QubitSpecSliceFF -------------------------------------------------------------------------

F0 = 3000.0
X_SPEC = F0 - 1.0 + (2.0 / 201) * np.arange(201)


def _spec_data(lines, hwhm=0.05, snr=30.0, seed=0):
    y = np.zeros_like(X_SPEC)
    for f in lines:
        y += hwhm**2 / ((X_SPEC - f) ** 2 + hwhm**2)
    rng = np.random.default_rng(seed)
    avgi = 0.3 + y + rng.normal(0, 1 / snr, X_SPEC.size)
    avgq = -0.2 + rng.normal(0, 1 / snr, X_SPEC.size)
    stack = lambda a: np.stack([a, a])[:, None, :]  # (ADC, read, freq)  # noqa: E731
    return {"config": {}, "data": {"x_pts": X_SPEC, "avgi": stack(avgi), "avgq": stack(avgq)}}


def _spec_display(data, tmp_path):
    exp = object.__new__(QubitSpecSliceFF)
    exp.cfg = {"qubit_gain": 500, "Gauss": True, "sigma": 2}
    exp.titlename = "Qubit Spec"
    exp.iname = str(tmp_path / "spec.png")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        exp.display(
            data, plotDisp=False, figNum=2, min_sep=0.2, fit_window_mhz=0.5, prominent_ratio=0.1
        )
    return data["data"]


def _recording_fit(monkeypatch):
    fits = []
    real = qs.fit_lorentzian_near_peak

    def rec(**kw):
        fit = real(**kw)
        if fit is not None:
            fits.append(fit)
        return fit

    monkeypatch.setattr(qs, "fit_lorentzian_near_peak", rec)
    return fits


@pytest.mark.parametrize("lines", [[F0], [F0 - 0.3, F0 + 0.3]], ids=["single", "doublet"])
def test_spec_saves_lorentz_errors_from_the_fit_covariance(monkeypatch, tmp_path, lines):
    fits = _recording_fit(monkeypatch)
    d = _spec_display(_spec_data(lines), tmp_path)
    assert d["lorentz_num_fits"] == len(lines)
    for key in ("lorentz_center_err", "lorentz_fwhm_err"):
        assert d[key].shape == d["lorentz_centers"].shape
    rows = zip(d["lorentz_centers"], d["lorentz_center_err"], d["lorentz_fwhm_err"])
    for c, c_err, w_err in rows:
        fit = next(f for f in fits if f["center"] == c)  # the accepted fit with this centre
        assert c_err == np.sqrt(fit["pcov"][2, 2])
        assert w_err == 2 * np.sqrt(fit["pcov"][3, 3])
        assert 0 < c_err < 0.05 and 0 < w_err < 0.1  # MHz: a 0.1 MHz FWHM line at SNR 30


def test_spec_without_accepted_fit_saves_empty_errors(tmp_path):
    data = _spec_data([])
    data["data"]["avgi"] = np.full_like(data["data"]["avgi"], 0.3)  # flat: no usable fit
    data["data"]["avgq"] = np.full_like(data["data"]["avgq"], -0.2)
    d = _spec_display(data, tmp_path)
    assert d["lorentz_num_fits"] == 0
    for key in ("lorentz_center_err", "lorentz_fwhm_err"):
        assert d[key].shape == d["lorentz_centers"].shape == (0,)


def test_spec_singular_covariance_gives_nan_without_raising(monkeypatch, tmp_path):
    # curve_fit returns an all-inf pcov when the Jacobian is singular (a parameter on its
    # bound); the display must keep the fit and save NaN errors, not raise
    real = qs.fit_lorentzian_near_peak

    def inf_pcov(**kw):
        fit = real(**kw)
        if fit is not None:
            fit = dict(fit, pcov=np.full((4, 4), np.inf))
        return fit

    monkeypatch.setattr(qs, "fit_lorentzian_near_peak", inf_pcov)
    d = _spec_display(_spec_data([F0]), tmp_path)
    assert d["lorentz_num_fits"] == 1
    assert np.isnan(d["lorentz_center_err"]).all() and np.isnan(d["lorentz_fwhm_err"]).all()
    assert np.isfinite(d["lorentz_centers"]).all()


@pytest.mark.parametrize(
    "pcov",
    [np.full((4, 4), np.inf), np.full((4, 4), np.nan), -np.eye(4), None, np.eye(2)],
    ids=["inf", "nan", "negative", "missing", "too_small"],
)
def test_lorentz_fit_errors_bad_covariance_is_nan(pcov):
    c_err, w_err = lorentz_fit_errors({"pcov": pcov})
    assert np.isnan(c_err) and np.isnan(w_err)


def test_lorentz_fit_errors_reads_centre_and_gamma():
    pcov = np.diag([1.0, 4.0, 0.25, 0.0625])
    assert lorentz_fit_errors({"pcov": pcov}) == (0.5, 0.5)  # (sqrt 0.25, 2 sqrt 0.0625)


# --- AmplitudeRabiFF / AmplitudeRabiFF_N ------------------------------------------------------

X_RABI = np.arange(101) * 99.0
PI_GAIN = 4000.0


def _rabi_trace(seed=1, noise=0.02):
    rng = np.random.default_rng(seed)
    pe = (1 - np.cos(np.pi * X_RABI / PI_GAIN)) / 2
    trace = 30 + 40j + 5 * pe * np.exp(1j * np.deg2rad(120.0))
    return trace + noise * (rng.normal(size=X_RABI.size) + 1j * rng.normal(size=X_RABI.size))


def test_rabi_ff_saves_perr_and_pi_gain_err(tmp_path):
    trace = _rabi_trace()
    trace = trace * np.exp(-1j * rabi.iq_rotation_angle(trace))  # as acquire leaves it
    sig = np.stack([trace, trace])[:, None, :]
    data = {"data": {"x_pts": X_RABI, "avgi": sig.real, "avgq": sig.imag}}
    inst = AmplitudeRabiFF(path="AmplitudeRabi", outerFolder=str(tmp_path) + os.sep, cfg={})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        inst.display(data=data, plotDisp=False, fit=True)
        ref_i = fit_rabi_cosine(X_RABI, trace.real)
    d = data["data"]
    for q in ("i", "q"):
        assert d[f"fit_{q}_perr"].shape == (4,)
        assert d[f"fit_{q}_pi_gain_err"] == pytest.approx(d[f"fit_{q}_perr"][2] / 2, rel=1e-12)
    assert np.array_equal(d["fit_i_perr"], ref_i["perr"])
    assert d["fit_i_pi_gain"] == pytest.approx(PI_GAIN, rel=0.03)
    assert 0 < d["fit_i_pi_gain_err"] < 0.01 * PI_GAIN


def _rabi_n(tmp_path):
    trace = _rabi_trace()
    data = {"data": {"x_pts": X_RABI, "avgi": [[trace.real]], "avgq": [[trace.imag]]}}
    cfg = {"Qubit_number": 1}
    inst = AmplitudeRabiFF_N(path="AmplitudeRabi", outerFolder=str(tmp_path) + os.sep, cfg=cfg)
    return inst, data


def _saved(inst):
    with h5py.File(inst.fname, "r") as f:
        return {k: f[k][()] for k in f.keys()}


def test_rabi_ff_n_saves_its_fit(tmp_path):
    inst, data = _rabi_n(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        finish(AmplitudeRabiFF_N, inst, data, reraise=True, plotDisp=False, fit=True)
    saved = _saved(inst)
    assert saved["rotation_phase"] == inst.rotation_phase
    for q, f in (("i", inst.fit_i), ("q", inst.fit_q)):
        assert np.array_equal(saved[f"fit_{q}_popt"], f["popt"])
        assert np.array_equal(saved[f"fit_{q}_perr"], f["perr"])
        assert saved[f"fit_{q}_pi_gain"] == f["pi_gain"]
        assert saved[f"fit_{q}_pi_gain_err"] == f["dpi_gain"]
        assert saved[f"fit_{q}_flag"] == f["flag_code"]
    assert saved["fit_i_pi_gain"] == pytest.approx(PI_GAIN, rel=0.03)


def test_rabi_ff_n_fit_failure_keeps_the_record(monkeypatch, tmp_path):
    def boom(x, y):
        raise RuntimeError("All Rabi cosine fits failed.")

    monkeypatch.setattr(rabi, "fit_rabi_cosine", boom)
    inst, data = _rabi_n(tmp_path)
    err = finish(AmplitudeRabiFF_N, inst, data, plotDisp=False, fit=True)
    assert err is None  # the fit failure is caught inside display
    saved = _saved(inst)
    assert {"x_pts", "avgi", "avgq", "rotation_phase"} <= set(saved)
    assert not any(k.startswith("fit_") for k in saved)


# --- CavitySpecFF -----------------------------------------------------------------------------


def test_transmission_saves_hanger_pcov(tmp_path):
    fpts = np.linspace(7090.0, 7100.0, 201)
    rng = np.random.default_rng(0)
    amp = 10 ** (hanger_model_db(fpts, 7095.2, 2e4 / 1.2, 2e4, 0.0, -20.0) / 20)
    amp = amp * (1 + 2e-3 * rng.standard_normal(fpts.size))
    inst = object.__new__(CavitySpecFF)
    inst.cfg = {"cavity_LO": 0.0, "pulse_freq": 7095.2}
    inst.iname = str(tmp_path / "trans.png")
    results = np.zeros((1, 1, 2, fpts.size))
    results[0, 0, 0] = amp  # I = |S21|, Q = 0
    data = {"config": inst.cfg, "data": {"results": results, "fpts": fpts}}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        inst.display(data=data, plotDisp=False, fit=True)
    d = data["data"]
    pcov = d["hanger_fit_pcov"]
    assert pcov.shape == (5, 5)
    assert np.allclose(pcov, pcov.T)
    assert np.array_equal(np.sqrt(np.diag(pcov)), d["hanger_fit_perr"])
    assert d["hanger_fit_Qtot_err"] == np.sqrt(pcov[1, 1])
