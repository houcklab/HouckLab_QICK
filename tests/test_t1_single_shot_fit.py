"""Hardware-free tests for the T1_SS analysis (F66): binomial-weighted T1 fit, Exp_err, and the
readout-confusion correction built from the single_shot calibration shots.

Synthetic shots only (a fake program class replaces T1SingleShotProgram).
See docs/experiments/t1_single_shot.md#analysis.

    python -m pytest tests/test_t1_single_shot_fit.py
"""

import types

import h5py
import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import qicklab.experiments.t1_single_shot as t1ss_mod  # noqa: E402
from qicklab.analysis.fitting import fit_exp_decay  # noqa: E402
from qicklab.analysis.iq import rotate_data  # noqa: E402
from qicklab.core.experiment import finish  # noqa: E402

T1_TRUE = 60.0  # us
EPS_G, EPS_E = 0.05, 0.10  # P(e|g), P(g|e) of the synthetic readout
REPS = 4000
STEP, EXPTS = 10.0, 30


# --- helpers --------------------------------------------------------------------------------


def test_readout_assignment_errors_counts_like_t1_ss():
    # Targets in the rotated frame: threshold 2.0, excited = I' > 2.0.
    angle, threshold = 0.7, 2.0
    ig_rot = np.array([-1.0, 0.0, 1.0, 2.5])  # one g shot above threshold -> P(e|g) = 1/4
    ie_rot = np.array([3.0, 4.0, 5.0, 1.5, 6.0])  # one e shot below -> P(g|e) = 1/5
    # Raw shots that rotate_data(., angle) maps onto the targets.
    ig, qg = rotate_data((ig_rot, np.zeros_like(ig_rot)), -angle)
    ie, qe = rotate_data((ie_rot, np.ones_like(ie_rot)), -angle)
    ie_back, _ = rotate_data((ie, qe), angle)
    np.testing.assert_allclose(ie_back, ie_rot, atol=1e-12)

    eps_g, eps_e = t1ss_mod.readout_assignment_errors(ig, qg, ie, qe, angle, threshold)
    assert eps_g == pytest.approx(0.25)
    assert eps_e == pytest.approx(0.20)


def test_readout_assignment_errors_empty_is_nan():
    eps_g, eps_e = t1ss_mod.readout_assignment_errors([], [], [1.0], [0.0], 0.0, 0.5)
    assert np.isnan(eps_g) and eps_e == 0.0


def test_readout_corrected_population_inverts_confusion():
    p_true = np.array([1.0, 0.6, 0.2, 0.0])
    p_meas = EPS_G + (1 - EPS_G - EPS_E) * p_true
    np.testing.assert_allclose(
        t1ss_mod.readout_corrected_population(p_meas, EPS_G, EPS_E), p_true, atol=1e-12
    )


@pytest.mark.parametrize("eps", [(0.6, 0.5), (0.5, 0.5), (np.nan, 0.1)])
def test_readout_corrected_population_undefined_is_nan(eps):
    out = t1ss_mod.readout_corrected_population([0.3, 0.4], *eps)
    assert out.shape == (2,) and np.all(np.isnan(out))


def test_binomial_sigma_and_clip():
    np.testing.assert_allclose(
        t1ss_mod.binomial_sigma([0.0, 0.5, 1.0], 100), [0.0, 0.05, 0.0], atol=1e-15
    )
    clipped = t1ss_mod.binomial_sigma([0.0, 0.5, 1.0], 100, clip=True)
    assert np.all(clipped > 0)
    assert clipped[0] == pytest.approx(np.sqrt(0.005 * 0.995 / 100))
    assert clipped[1] == pytest.approx(0.05)


# --- fit_exp_decay sigma ----------------------------------------------------------------------

X = np.arange(40) * 5.0


def test_constant_sigma_is_the_unweighted_fit():
    rng = np.random.default_rng(3)
    y = 0.8 * np.exp(-X / 50.0) + 0.1 + rng.normal(0, 0.02, X.size)
    plain = fit_exp_decay(X, y)
    weighted = fit_exp_decay(X, y, sigma=np.full(X.size, 0.37))
    assert plain["ok"] and weighted["ok"]
    np.testing.assert_allclose(weighted["popt"], plain["popt"], rtol=1e-6)
    # absolute_sigma=False: the covariance is rescaled by the residuals, not by sigma's size
    np.testing.assert_allclose(weighted["perr"], plain["perr"], rtol=1e-6)


def test_sigma_downweights_noisy_points():
    y = 0.8 * np.exp(-X / 50.0) + 0.1
    y[5:10] += 0.3  # a corrupted stretch
    sigma = np.full(X.size, 0.01)
    sigma[5:10] = 10.0
    plain = fit_exp_decay(X, y)
    weighted = fit_exp_decay(X, y, sigma=sigma)
    assert weighted["ok"]
    assert abs(weighted["T"] - 50.0) < 0.5
    assert abs(weighted["T"] - 50.0) < abs(plain["T"] - 50.0)


@pytest.mark.parametrize("sigma", [np.zeros(40), np.full(39, 0.1), np.r_[np.nan, np.ones(39)]])
def test_bad_sigma_is_not_ok(sigma):
    fit = fit_exp_decay(X, np.exp(-X / 50.0), sigma=sigma)
    assert not fit["ok"] and "sigma" in fit["error"]


# --- T1_SS end to end -------------------------------------------------------------------------


def _p_meas(t):
    """Excited fraction a perfect threshold would read through the (EPS_G, EPS_E) readout."""
    p_true = np.exp(-t / T1_TRUE)
    return EPS_G + (1 - EPS_G - EPS_E) * p_true


def _program_cls(shots_fn):
    class _Prog:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True):
            return shots_fn(self.cfg)

    return _Prog


def _binomial_shots(seed):
    rng = np.random.default_rng(seed)

    def shots(cfg):
        excited = rng.random(cfg["reps"]) < _p_meas(cfg["variable_wait"])
        return np.where(excited, 2.0, 0.0)[None, :], np.zeros((1, cfg["reps"]))

    return shots


def _flat_shots(cfg):
    return np.zeros((1, cfg["reps"])), np.zeros((1, cfg["reps"]))


def _t1ss(tmp_path, monkeypatch, shots_fn):
    monkeypatch.setattr(t1ss_mod, "T1SingleShotProgram", _program_cls(shots_fn))
    cfg = {"start": 0, "step": STEP, "expts": EXPTS, "reps": REPS}
    soc = types.SimpleNamespace(stop_tproc=lambda: None)
    return t1ss_mod.T1_SS(path="T1SS", outerFolder=str(tmp_path) + "/", cfg=cfg, soc=soc)


def test_t1_ss_fits_t1_and_saves_fields(tmp_path, monkeypatch):
    exp = _t1ss(tmp_path, monkeypatch, _binomial_shots(seed=11))
    data = exp.acquire(threshold=1.0, angle=0.0, readout_errors=(EPS_G, EPS_E))
    d = data["data"]
    t = d["wait_times"]
    np.testing.assert_allclose(
        d["Exp_err"], np.sqrt(d["Exp_values"] * (1 - d["Exp_values"]) / REPS)
    )
    # corrected curve ~ exp(-t/T1): 1 at t = 0, 0 on the plateau (binomial noise ~0.01)
    np.testing.assert_allclose(d["Exp_values_readout_corrected"], np.exp(-t / T1_TRUE), atol=0.04)
    assert d["readout_P_e_given_g"] == EPS_G and d["readout_P_g_given_e"] == EPS_E

    assert finish(t1ss_mod.T1_SS, exp, data, plotDisp=False) is None
    fit = exp.fit
    assert fit["ok"], fit["error"]
    assert abs(fit["T"] - T1_TRUE) < 4 * fit["T_err"]
    assert fit["T_err"] < 0.1 * T1_TRUE

    with h5py.File(exp.fname, "r") as f:
        assert bool(f["t1ss_fit_ok"][()])
        assert f["t1ss_fit_us"][()] == pytest.approx(fit["T"])
        assert f["t1ss_fit_err_us"][()] == pytest.approx(fit["T_err"])
        assert f["t1ss_fit_curve"].shape == (EXPTS,)
        np.testing.assert_allclose(f["t1ss_fit_curve"][()], fit["yfit"])
        np.testing.assert_allclose(f["Exp_err"][()], d["Exp_err"])
        np.testing.assert_allclose(
            f["Exp_values_readout_corrected"][()], d["Exp_values_readout_corrected"]
        )
        np.testing.assert_allclose(f["Exp_values"][()], d["Exp_values"])  # raw kept
        assert f["readout_P_e_given_g"][()] == EPS_G


def test_t1_ss_correction_does_not_change_t1(tmp_path, monkeypatch):
    """The correction is affine in p: a fit to the corrected curve gives the same T1."""
    exp = _t1ss(tmp_path, monkeypatch, _binomial_shots(seed=5))
    d = exp.acquire(threshold=1.0, angle=0.0, readout_errors=(EPS_G, EPS_E))["data"]
    raw = fit_exp_decay(d["wait_times"], d["Exp_values"])
    corrected = fit_exp_decay(d["wait_times"], d["Exp_values_readout_corrected"])
    assert raw["ok"] and corrected["ok"]
    assert corrected["T"] == pytest.approx(raw["T"], rel=1e-4)


def test_t1_ss_without_calibration_has_no_corrected_curve(tmp_path, monkeypatch):
    exp = _t1ss(tmp_path, monkeypatch, _binomial_shots(seed=2))
    d = exp.acquire(threshold=1.0, angle=0.0)["data"]
    assert "Exp_values_readout_corrected" not in d and "readout_P_e_given_g" not in d
    assert "Exp_err" in d


def test_t1_ss_flat_data_does_not_raise(tmp_path, monkeypatch, capsys):
    """All-g shots (the harness's flat fake data): no fit, NaN fields, the record is saved."""
    exp = _t1ss(tmp_path, monkeypatch, _flat_shots)
    data = exp.acquire(threshold=1.0, angle=0.0, readout_errors=(0.6, 0.5))
    assert np.all(np.isnan(data["data"]["Exp_values_readout_corrected"]))
    assert finish(t1ss_mod.T1_SS, exp, data, plotDisp=False) is None
    assert not exp.fit["ok"]
    assert "T1_SS fit not reliable" in capsys.readouterr().out
    with h5py.File(exp.fname, "r") as f:
        assert not bool(f["t1ss_fit_ok"][()])
        assert np.isnan(f["t1ss_fit_us"][()])
        assert np.all(np.isnan(f["t1ss_fit_curve"][()]))


def _deterministic_shots(cfg):
    """round(reps * 0.9 exp(-t/30)) excited shots: the late points have none (p = 0 exactly)."""
    n_e = int(round(cfg["reps"] * 0.9 * np.exp(-cfg["variable_wait"] / 30.0)))
    i = np.zeros(cfg["reps"])
    i[:n_e] = 2.0
    return i[None, :], np.zeros((1, cfg["reps"]))


def test_t1_ss_display_weights_by_clipped_model_sigma(tmp_path, monkeypatch):
    """display fits twice (fit_t1ss_decay): unweighted, then weighted with
    binomial_sigma(yfit_1, reps, clip=True) of the first model curve, not of the observed p.
    The clip keeps a model plateau at 0 at a finite, positive sigma and the fit succeeds."""
    calls = []
    real_fit = t1ss_mod.fit_exp_decay

    def recording_fit(x, y, *args, **kwargs):
        out = real_fit(x, y, *args, **kwargs)
        calls.append((kwargs.get("sigma"), out))
        return out

    monkeypatch.setattr(t1ss_mod, "fit_exp_decay", recording_fit)
    exp = _t1ss(tmp_path, monkeypatch, _deterministic_shots)
    data = exp.acquire(threshold=1.0, angle=0.0)
    p = data["data"]["Exp_values"]
    assert np.any(p == 0.0)  # observed zeros: observed-p weights would be clipped here

    assert finish(t1ss_mod.T1_SS, exp, data, plotDisp=False) is None
    assert len(calls) == 2
    assert calls[0][0] is None  # pass 1 unweighted
    sigma = np.asarray(calls[1][0])
    np.testing.assert_allclose(sigma, t1ss_mod.binomial_sigma(calls[0][1]["yfit"], REPS, clip=True))
    assert not np.allclose(sigma, t1ss_mod.binomial_sigma(p, REPS, clip=True))
    assert np.all(np.isfinite(sigma)) and np.all(sigma > 0)
    assert sigma.min() >= np.sqrt(0.5 / REPS * (1 - 0.5 / REPS) / REPS) * (1 - 1e-12)
    assert exp.fit is calls[1][1]
    assert exp.fit["ok"], exp.fit["error"]
    assert exp.fit["T"] == pytest.approx(30.0, rel=0.02)


def test_fit_t1ss_decay_falls_back_to_pass_1_without_a_model_curve():
    fit = t1ss_mod.fit_t1ss_decay(X, np.zeros(X.size), REPS)
    assert not fit["ok"] and fit["error"] == "y is constant"


@pytest.mark.parametrize("eps_g, reps", [(0.0, 200), (0.003, 200), (0.03, 200)])
def test_fit_t1ss_decay_is_unbiased_at_a_low_count_plateau(eps_g, reps):
    """Monte Carlo, T1 = 60 us, 100 points at 5 us. Observed-p weights (Neyman chi-square)
    biased T1 low by ~2 us (1.5-2 sigma) at eps_g = 0, reps = 200, where the plateau holds
    < 1 excited shot per point; model weights must not. Mean of 150 trials, sd ~0.1 us."""
    rng = np.random.default_rng(7)
    x = np.arange(100) * 5.0
    p_true = eps_g + (1 - eps_g) * 0.95 * np.exp(-x / 60.0)
    ts = []
    for _ in range(150):
        y = rng.binomial(reps, p_true) / reps
        fit = t1ss_mod.fit_t1ss_decay(x, y, reps)
        assert fit["ok"], fit["error"]
        ts.append(fit["T"])
    assert np.mean(ts) == pytest.approx(60.0, abs=0.5)
