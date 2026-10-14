"""Hardware-free tests for the thermal-mode population of single_shot (number_of_pulses = 0):
the ML mixture weight `fit_thermal_population` against a labelled pi-pulse reference, and its
wiring into SingleShotProgramFFMUX.acquire (docs/concepts/iq_conventions.md section 7).

The old tail fraction (`classify_thermal_tail`) is kept for the scatter labels only; its bias
(about 1 % floor at zero population, low by up to 4x below d ~ 4 sigma) is documented in its
docstring, not asserted here.

    python -m pytest tests/test_thermal_population.py
"""

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

import qicklab.analysis.readout as readout
import qicklab.experiments.single_shot as single_shot
from qicklab.analysis.readout import classify_thermal_tail, fit_thermal_population

G_CENTER = np.array([3.0, -1.0])


def _clouds(rng, d, n, p_e, theta, p_decay=0.0, sigma_e=1.0):
    """Isotropic sigma = 1 shots: g at G_CENTER, e at distance d along angle theta; a fraction
    p_decay of excited shots decays at a uniform time in the window (mean lies on the g-e line);
    undecayed excited shots have width sigma_e."""
    e_center = G_CENTER + d * np.array([np.cos(theta), np.sin(theta)])
    excited = rng.random(n) < p_e
    frac = excited.astype(float)
    decayed = excited & (rng.random(n) < p_decay)
    frac[decayed] = rng.random(decayed.sum())
    noise = rng.standard_normal((n, 2))
    noise[excited & ~decayed] *= sigma_e
    pts = G_CENTER + frac[:, None] * (e_center - G_CENTER) + noise
    return pts[:, 0], pts[:, 1], e_center


def _undetermined(fit):
    """All fitted quantities NaN; the diagnostics that say why are kept."""
    for key in ("population", "population_err", "pi_population", "e_width_ratio"):
        assert np.isnan(fit[key]), key
    for key in ("g_center", "e_center", "cov"):
        assert np.all(np.isnan(fit[key])), key
    assert np.isfinite(fit["separation_sigma"])


GRID = [(d, p) for d in (2.0, 3.0, 5.0) for p in (0.0, 0.01, 0.03, 0.1)]


@pytest.mark.parametrize("d,p", GRID)
def test_ml_population_unbiased_within_3_se(d, p):
    rng = np.random.default_rng(int(1000 * d + 1e4 * p))
    theta = rng.uniform(0, 2 * np.pi)
    i_th, q_th, _ = _clouds(rng, d, 2000, p, theta)
    i_pi, q_pi, e_true = _clouds(rng, d, 2000, 0.9, theta)
    fit = fit_thermal_population(i_th, q_th, i_pi=i_pi, q_pi=q_pi)
    assert fit["source"] == "pi_shots" and fit["converged"]
    assert 0 < fit["population_err"] < 0.02
    assert abs(fit["population"] - p) < 3 * fit["population_err"], fit
    assert abs(fit["pi_population"] - 0.9) < 0.05
    assert np.linalg.norm(fit["e_center"] - e_true) < 0.2
    assert abs(fit["e_width_ratio"] - 1) < 0.05
    assert not any("as wide as" in w for w in fit["warnings"]), fit["warnings"]


def test_se_matches_trial_to_trial_scatter():
    # The docstring's claim: over 30 seeds at d = 1.5 sigma the mean SE is ~0.86-0.93 of the
    # scatter of p. Scoring the weights alone (no centre/covariance columns) gives ~0.55.
    pops, errs = [], []
    for seed in range(30):
        rng = np.random.default_rng(seed)
        theta = rng.uniform(0, 2 * np.pi)
        i_th, q_th, _ = _clouds(rng, 1.5, 2000, 0.1, theta)
        i_pi, q_pi, _ = _clouds(rng, 1.5, 2000, 0.9, theta)
        fit = fit_thermal_population(i_th, q_th, i_pi=i_pi, q_pi=q_pi)
        pops.append(fit["population"])
        errs.append(fit["population_err"])
    ratio = np.mean(errs) / np.std(pops, ddof=1)
    assert 0.7 < ratio < 1.4, ratio


def _joint_loglik(theta, und, pi):
    p, w, g1, g2, e1, e2, s11, s22, s12 = theta
    cov = np.array([[s11, s12], [s12, s22]])
    inv_cov = np.linalg.inv(cov)
    logdet = np.linalg.slogdet(cov)[1]
    total = 0.0
    for pts, q in ((und, p), (pi, w)):
        log_g = readout._gauss_logpdf(pts, np.array([g1, g2]), inv_cov, logdet)
        log_e = readout._gauss_logpdf(pts, np.array([e1, e2]), inv_cov, logdet)
        total += float(np.logaddexp(np.log1p(-q) + log_g, np.log(q) + log_e).sum())
    return total


def test_se_matches_observed_information_over_all_parameters():
    # The SE is from the outer product of scores over (p, w, g, e, cov). Asymptotically it equals
    # the observed-information SE: the inverse numerical Hessian of the joint log likelihood in
    # all 9 parameters at the fit. A small pi run (200 shots) makes the e centre uncertain, so
    # each block of score columns matters: without the e-centre columns the ratio is ~0.83, the
    # covariance columns ~0.89, the g-centre columns ~0.76, all three ~0.60 (full: ~1.06).
    ratios = []
    for seed in range(3):
        rng = np.random.default_rng(seed)
        theta = rng.uniform(0, 2 * np.pi)
        i_th, q_th, _ = _clouds(rng, 2.0, 4000, 0.1, theta)
        i_pi, q_pi, _ = _clouds(rng, 2.0, 200, 0.9, theta)
        fit = fit_thermal_population(i_th, q_th, i_pi=i_pi, q_pi=q_pi)
        und, pi = np.column_stack([i_th, q_th]), np.column_stack([i_pi, q_pi])
        c = fit["cov"]
        x0 = np.array(
            [fit["population"], fit["pi_population"], *fit["g_center"], *fit["e_center"]]
            + [c[0, 0], c[1, 1], c[0, 1]]
        )
        h = np.array([1e-4, 1e-4] + [1e-3] * 7)
        H = np.zeros((9, 9))
        for a in range(9):
            for b in range(a, 9):

                def f(da, db):
                    x = x0.copy()
                    x[a] += da * h[a]
                    x[b] += db * h[b]
                    return _joint_loglik(x, und, pi)

                H[a, b] = H[b, a] = (f(1, 1) - f(1, -1) - f(-1, 1) + f(-1, -1)) / (4 * h[a] * h[b])
        se_hess = np.sqrt(np.linalg.inv(-H)[0, 0])
        ratios.append(fit["population_err"] / se_hess)
    assert 0.95 < np.mean(ratios) < 1.15, ratios


def test_mirrored_em_solution_is_relabelled(monkeypatch):
    # The likelihood is symmetric under g <-> e with q -> 1 - q, so EM may land on the mirrored
    # solution; |e> must be relabelled as the state the pi pulse fills, giving the same fit.
    rng = np.random.default_rng(13)
    i_th, q_th, _ = _clouds(rng, 3.0, 2000, 0.05, 0.4)
    i_pi, q_pi, _ = _clouds(rng, 3.0, 2000, 0.9, 0.4)
    ref = fit_thermal_population(i_th, q_th, i_pi=i_pi, q_pi=q_pi)
    em = readout._em_shared_cov

    def mirrored(*args, **kwargs):
        weights, g, e, cov, ll, n_iter, converged = em(*args, **kwargs)
        return [1.0 - q for q in weights], e, g, cov, ll, n_iter, converged

    monkeypatch.setattr(readout, "_em_shared_cov", mirrored)
    fit = fit_thermal_population(i_th, q_th, i_pi=i_pi, q_pi=q_pi)
    assert fit["population"] == pytest.approx(ref["population"], abs=1e-9)
    assert fit["population_err"] == pytest.approx(ref["population_err"], rel=1e-6)
    assert fit["pi_population"] == pytest.approx(ref["pi_population"], abs=1e-9)
    np.testing.assert_allclose(fit["e_center"], ref["e_center"], atol=1e-9)
    np.testing.assert_allclose(fit["g_center"], ref["g_center"], atol=1e-9)


@pytest.mark.parametrize("d", [3.0, 5.0])
def test_population_near_half_resolved_or_nan(d):
    # A 95 % pi pulse swaps the populations: w = F(1 - p) + (1 - F)p. At p = 0.45 the contrast
    # w - p is only ~0.1, so the mean-difference EM start (w - p = 0.85) collapsed e onto g; the
    # KMeans start must recover p. At p = 0.5, w = p: which cloud is |e> is undetermined -> NaN.
    F = 0.95
    for p in (0.45, 0.5):
        for seed in range(3):
            rng = np.random.default_rng(seed)
            theta = rng.uniform(0, 2 * np.pi)
            i_th, q_th, _ = _clouds(rng, d, 2000, p, theta)
            i_pi, q_pi, e_true = _clouds(rng, d, 2000, F * (1 - p) + (1 - F) * p, theta)
            fit = fit_thermal_population(i_th, q_th, i_pi=i_pi, q_pi=q_pi)
            assert abs(fit["separation_sigma"] - d) < 0.3, fit
            if p == 0.45:
                assert abs(fit["population"] - p) < 3 * fit["population_err"], fit
                assert np.linalg.norm(fit["e_center"] - e_true) < 0.2
            else:
                _undetermined(fit)
                assert np.isfinite(fit["pi_contrast"]) and np.isfinite(fit["pi_contrast_err"])
                assert any("not driven" in w and "NaN" in w for w in fit["warnings"])


def test_undriven_reference_read_gives_nan():
    # The other reads of a MUX run: the "pi" shots of an undriven qubit are a second undriven
    # cloud, so which cloud is |e> is undetermined.
    for seed in range(5):
        rng = np.random.default_rng(seed)
        i_th, q_th, _ = _clouds(rng, 3.0, 2000, 0.03, 0.3)
        i_pi, q_pi, _ = _clouds(rng, 3.0, 2000, 0.03, 0.3)
        fit = fit_thermal_population(i_th, q_th, i_pi=i_pi, q_pi=q_pi)
        _undetermined(fit)
        assert abs(fit["pi_contrast"]) < 4 * fit["pi_contrast_err"]
        assert any("not driven" in w and "NaN" in w for w in fit["warnings"])


def test_moved_undriven_reference_can_give_finite_population():
    # Documented limitation (single_shot.md Failure modes, iq_conventions section 7): the guard
    # sees any change between the two sets, not the pi pulse. A non-driven read whose cloud moved
    # by 1 sigma between the runs (drift, cross-Kerr/ZZ) mostly yields a finite p with the moved
    # cloud taken as |e>, so only the driven qubit's read may be trusted.
    finite = 0
    for seed in range(10):
        rng = np.random.default_rng(seed)
        i_th, q_th, _ = _clouds(rng, 3.0, 2000, 0.03, 0.3)
        i_pi, q_pi, _ = _clouds(rng, 3.0, 2000, 0.03, 0.3)
        fit = fit_thermal_population(i_th, q_th, i_pi=i_pi + 1.0, q_pi=q_pi)
        finite += np.isfinite(fit["population"])
    assert finite >= 3


def test_unresolved_clouds_give_nan():
    rng = np.random.default_rng(11)
    i_th, q_th, _ = _clouds(rng, 0.3, 2000, 0.03, 0.3)
    e_center = G_CENTER + 0.3 * np.array([np.cos(0.3), np.sin(0.3)])
    fit = fit_thermal_population(i_th, q_th, e_center=e_center)
    assert fit["separation_sigma"] < 1
    _undetermined(fit)
    assert any("separation" in w and "NaN" in w for w in fit["warnings"])


@pytest.mark.parametrize("sigma_e,direction", [(1.5, "low"), (0.8, "high")])
def test_unequal_cloud_widths_flagged(sigma_e, direction):
    # The shared covariance assumes equal g/e widths: a wider e cloud biases p low, a narrower
    # one high (docstring numbers); e_width_ratio must show it and the fit must warn.
    rng = np.random.default_rng(12)
    i_th, q_th, _ = _clouds(rng, 2.0, 4000, 0.03, 0.9, sigma_e=sigma_e)
    i_pi, q_pi, _ = _clouds(rng, 2.0, 4000, 0.9, 0.9, sigma_e=sigma_e)
    fit = fit_thermal_population(i_th, q_th, i_pi=i_pi, q_pi=q_pi)
    if direction == "low":
        assert fit["e_width_ratio"] > 1.15 and fit["population"] < 0.02
    else:
        assert fit["e_width_ratio"] < 0.9 and fit["population"] > 0.05
    assert any("as wide as" in w and f"biased {direction}" in w for w in fit["warnings"])


def test_fixed_e_center_from_cfg():
    rng = np.random.default_rng(7)
    i_th, q_th, e_true = _clouds(rng, 3.0, 2000, 0.03, 1.1)
    fit = fit_thermal_population(i_th, q_th, e_center=e_true)
    assert fit["source"] == "cfg_e_center"
    assert np.array_equal(fit["e_center"], e_true)
    assert np.isnan(fit["pi_population"])
    assert abs(fit["population"] - 0.03) < 3 * fit["population_err"]
    assert np.isnan(fit["e_width_ratio"])


def test_no_reference_gives_nan_and_warning():
    rng = np.random.default_rng(8)
    i_th, q_th, _ = _clouds(rng, 3.0, 500, 0.03, 0.0)
    fit = fit_thermal_population(i_th, q_th)
    assert fit["source"] == "none"
    assert np.isnan(fit["population"]) and np.isnan(fit["population_err"])
    assert any("not a population" in w for w in fit["warnings"])


def test_t1_decay_smear_biases_low_as_documented():
    # 20 % of excited shots decay during the window (both runs): the docstring states p is low by
    # about 11-17 % relative at d = 3-5 sigma; large N so the bias dominates the noise.
    rng = np.random.default_rng(9)
    i_th, q_th, _ = _clouds(rng, 3.0, 20000, 0.1, 0.4, p_decay=0.2)
    i_pi, q_pi, _ = _clouds(rng, 3.0, 20000, 0.9, 0.4, p_decay=0.2)
    fit = fit_thermal_population(i_th, q_th, i_pi=i_pi, q_pi=q_pi)
    ratio = fit["population"] / 0.1
    assert 0.75 < ratio < 0.97, ratio
    assert fit["pi_population"] < 0.9
    # The smear is not a width mismatch: the width diagnostic stays quiet (docstring).
    assert not any("as wide as" in w for w in fit["warnings"]), fit["warnings"]


def test_tail_classifier_reports_tail_fraction_not_population():
    rng = np.random.default_rng(10)
    i_th, q_th, _ = _clouds(rng, 3.0, 2000, 0.03, 0.0)
    tail = classify_thermal_tail(i_th, q_th, {}, 0)
    assert "population" not in tail
    assert tail["tail_fraction"] == pytest.approx(np.mean(tail["labels"]))


# --- SingleShotProgramFFMUX thermal branch -------------------------------------------------------


class _FakeProgram:
    """Stands in for SingleShotProgram: shots from the synthetic clouds, excited fraction 0.9 for
    a pi run (Pulse and number_of_pulses > 0), else P_THERMAL."""

    P_THERMAL = 0.05
    calls = []

    def __init__(self, soccfg, cfg):
        self.cfg = cfg

    def acquire(self, soc, load_pulses=True):
        pulsed = bool(self.cfg["Pulse"]) and self.cfg["number_of_pulses"] > 0
        _FakeProgram.calls.append((self.cfg["Pulse"], self.cfg["number_of_pulses"]))
        rng = np.random.default_rng(len(_FakeProgram.calls))
        i, q, _ = _clouds(rng, 4.0, 3000, 0.9 if pulsed else self.P_THERMAL, 0.7)
        return [i[None, :]], [q[None, :]]


def _run(tmp_path, monkeypatch, **cfg_extra):
    monkeypatch.setattr(single_shot, "SingleShotProgram", _FakeProgram)
    _FakeProgram.calls = []
    cfg = {"number_of_pulses": 0, "readout_length": 15, **cfg_extra}
    inst = single_shot.SingleShotProgramFFMUX(
        path="SingleShot", outerFolder=str(tmp_path) + "/", cfg=cfg
    )
    data = inst.acquire()
    return inst, data["data"]


def test_acquire_thermal_runs_pi_reference_and_saves_population(tmp_path, monkeypatch):
    inst, d = _run(tmp_path, monkeypatch)
    assert _FakeProgram.calls == [(False, 0), (True, 1)]
    assert inst.cfg["number_of_pulses"] == 0  # the pi run uses a copy of cfg
    assert "thermal_population_tail0" not in d
    for key in (
        "thermal_population0",
        "thermal_population_err0",
        "thermal_tail_fraction0",
        "thermal_pi_population0",
        "thermal_fit_e_width_ratio0",
        "thermal_fit_g_center0",
        "thermal_fit_e_center0",
        "thermal_fit_cov0",
        "i_pi0",
        "q_pi0",
    ):
        assert key in d, key
    assert abs(d["thermal_population0"] - _FakeProgram.P_THERMAL) < 3 * d["thermal_population_err0"]
    assert d["thermal_mode"] is True
    inst.display({"data": d}, plotDisp=False)


def test_acquire_thermal_with_cfg_e_center(tmp_path, monkeypatch):
    e_center = G_CENTER + 4.0 * np.array([np.cos(0.7), np.sin(0.7)])
    _, d = _run(tmp_path, monkeypatch, thermal_pi_calibration=False, thermal_e_center=e_center)
    assert _FakeProgram.calls == [(False, 0)]
    assert "i_pi0" not in d and np.isnan(d["thermal_pi_population0"])
    np.testing.assert_array_equal(d["thermal_fit_e_center0"], e_center)
    assert abs(d["thermal_population0"] - _FakeProgram.P_THERMAL) < 3 * d["thermal_population_err0"]


def test_acquire_thermal_without_reference_reports_nan(tmp_path, monkeypatch, capsys):
    _, d = _run(tmp_path, monkeypatch, thermal_pi_calibration=False)
    assert np.isnan(d["thermal_population0"])
    assert np.isfinite(d["thermal_tail_fraction0"])
    assert "WARNING" in capsys.readouterr().out


class _FakeProgramTwoReads(_FakeProgram):
    """Two reads; the pi pulse drives only read 0's qubit (read 1 stays thermal in both runs)."""

    def acquire(self, soc, load_pulses=True):
        pulsed = bool(self.cfg["Pulse"]) and self.cfg["number_of_pulses"] > 0
        _FakeProgram.calls.append((self.cfg["Pulse"], self.cfg["number_of_pulses"]))
        rng = np.random.default_rng(len(_FakeProgram.calls))
        i0, q0, _ = _clouds(rng, 4.0, 3000, 0.9 if pulsed else self.P_THERMAL, 0.7)
        i1, q1, _ = _clouds(rng, 4.0, 3000, self.P_THERMAL, 2.0)
        return [i0[None, :], i1[None, :]], [q0[None, :], q1[None, :]]


def test_acquire_thermal_mux_only_driven_read_calibrated(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(single_shot, "SingleShotProgram", _FakeProgramTwoReads)
    _FakeProgram.calls = []
    cfg = {"number_of_pulses": 0, "readout_length": 15, "Read_Indeces": [0, 1]}
    inst = single_shot.SingleShotProgramFFMUX(
        path="SingleShot", outerFolder=str(tmp_path) + "/", cfg=cfg
    )
    d = inst.acquire()["data"]
    assert abs(d["thermal_population0"] - _FakeProgram.P_THERMAL) < 3 * d["thermal_population_err0"]
    assert np.isnan(d["thermal_population1"]) and np.isnan(d["thermal_population_err1"])
    # Nothing from the undetermined fit may look like a working pi pulse.
    assert np.isnan(d["thermal_pi_population1"]) and np.isnan(d["thermal_fit_e_width_ratio1"])
    for key in ("thermal_fit_g_center1", "thermal_fit_e_center1", "thermal_fit_cov1"):
        assert np.all(np.isnan(d[key])), key
    assert np.isfinite(d["thermal_pi_population0"])
    assert np.isfinite(d["thermal_tail_fraction1"])
    out = capsys.readouterr().out
    assert "Read 1: WARNING" in out
    assert "only that qubit's read is a population" in out
    read1 = [line for line in out.splitlines() if "Read 1: p =" in line]
    assert read1 and "NaN" in read1[0] and "pi-run excited" not in read1[0], read1


def test_acquire_thermal_nonzero_read_index_titles_png(tmp_path, monkeypatch):
    # The device reads index 5 (Qubit_Readout); display() plots suffix 0, so the keys its title
    # uses must be mirrored under the enumeration index.
    titles = []
    monkeypatch.setattr(single_shot.plt, "title", lambda t, *a, **k: titles.append(t))
    inst, d = _run(tmp_path, monkeypatch, Read_Indeces=5)
    for key in (
        "thermal_population",
        "thermal_population_err",
        "thermal_tail_fraction",
        "thermal_center_g",
        "thermal_center_e",
    ):
        np.testing.assert_array_equal(d[key + "0"], d[key + "5"])
    assert np.isfinite(d["thermal_population0"])
    inst.display({"data": d}, plotDisp=False)
    assert titles and "nan" not in titles[-1].lower(), titles
    assert f"{100 * d['thermal_population5']:.2f}" in titles[-1]
