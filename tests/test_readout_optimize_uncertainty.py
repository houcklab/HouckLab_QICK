"""Per-point uncertainty and smoothed optimum of the single-shot optimisation maps (review F60).

Before 2026-10 ReadOpt_wSingleShotFF and QubitPulseOpt_wSingleShotFF saved only the contrast
per point: no uncertainty and no optimum. At 1000 shots per class the per-point scatter
(~0.015-0.02) is as large as the contrast differences near the optimum, so the brightest pixel
is mostly noise. Synthetic data only (a fake SingleShotProgram returns Gaussian clouds).
docs/experiments/readout_optimize.md#analysis

    python -m pytest tests/test_readout_optimize_uncertainty.py
"""

import matplotlib

matplotlib.use("Agg")

import h5py  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

import qicklab.experiments.readout_optimize as ro  # noqa: E402
from qicklab.analysis.readout import hist_process  # noqa: E402

NEW_KEYS = {"fid_err_mat", "Pgg_mat", "Pee_mat", "threshold_mat", "angle_mat"}
SUMMARY_KEYS = {
    "fid_smooth_mat",
    "tied_mask",
    "best_gain",
    "best_freq",
    "best_fid",
    "best_fid_err",
    "best_fid_smooth",
    "median_fid_err",
}


def _pair(rng, n_g, n_e, d):
    """Unit-width g cloud at the origin and e cloud at distance d along a tilted axis."""
    axis = np.array([np.cos(0.7), np.sin(0.7)])
    g = rng.normal(size=(n_g, 2))
    e = rng.normal(size=(n_e, 2)) + d * axis
    return g[:, 0], g[:, 1], e[:, 0], e[:, 1]


# --- contrast_point_stats ---------------------------------------------------------------------


@pytest.mark.parametrize("n_g,n_e,d", [(1000, 1000, 2.0), (700, 1300, 1.0), (50, 80, 4.0)])
def test_pgg_pee_reproduce_contrast_and_fid_err_formula(capsys, n_g, n_e, d):
    ig, qg, ie, qe = _pair(np.random.default_rng(int(10 * d)), n_g, n_e, d)
    fid, thr, ang = hist_process(data=[ig, qg, ie, qe], plot=False, normalize="per_class")
    pgg, pee, err = ro.contrast_point_stats(ig, qg, ie, qe, fid, thr, ang)
    assert pgg + pee - 1 == pytest.approx(fid, abs=1e-12)
    # the actual class sizes, not a common N
    assert err == pytest.approx(np.sqrt(pgg * (1 - pgg) / n_g + pee * (1 - pee) / n_e), rel=1e-14)
    assert "WARNING" not in capsys.readouterr().out


def test_mismatched_threshold_warns(capsys):
    ig, qg, ie, qe = _pair(np.random.default_rng(0), 1000, 1000, 2.0)
    fid, thr, ang = hist_process(data=[ig, qg, ie, qe], plot=False)
    ro.contrast_point_stats(ig, qg, ie, qe, fid, thr + 0.5, ang)
    assert "WARNING: Pgg + Pee - 1" in capsys.readouterr().out


def test_fid_err_matches_the_trial_to_trial_scatter():
    # 1000 shots per class, d = 2: the finding's Monte Carlo gives sd(C) = 0.015.
    rng = np.random.default_rng(5)
    cs, errs = [], []
    for _ in range(200):
        ig, qg, ie, qe = _pair(rng, 1000, 1000, 2.0)
        fid, thr, ang = hist_process(data=[ig, qg, ie, qe], plot=False)
        cs.append(fid)
        errs.append(ro.contrast_point_stats(ig, qg, ie, qe, fid, thr, ang)[2])
    assert np.median(errs) == pytest.approx(0.0155, abs=0.0015)
    assert np.std(cs) == pytest.approx(np.median(errs), rel=0.2)


def test_selection_bias_is_about_two_errors_at_zero_contrast():
    # fid_err leaves out the bias of choosing the threshold on the same shots. For
    # well-separated clouds it is small (d = 2: ~+0.006, under half an error); with no
    # separation at all the maximised contrast reads ~+0.04, about 2 fid_err (documented
    # on docs/experiments/readout_optimize.md#analysis).
    rng = np.random.default_rng(11)
    for d, c_true, lo, hi in [(0.0, 0.0, 1.4, 2.6), (2.0, 0.6827, -0.2, 0.9)]:
        cs, errs = [], []
        for _ in range(150):
            ig, qg, ie, qe = _pair(rng, 1000, 1000, d)
            fid, thr, ang = hist_process(data=[ig, qg, ie, qe], plot=False)
            cs.append(fid)
            errs.append(ro.contrast_point_stats(ig, qg, ie, qe, fid, thr, ang)[2])
        assert lo < (np.mean(cs) - c_true) / np.median(errs) < hi


def test_empty_class_gives_nan_error():
    ig, qg, ie, qe = _pair(np.random.default_rng(0), 100, 100, 2.0)
    pgg, pee, err = ro.contrast_point_stats(ig, qg, ie[:0], qe[:0], np.nan, np.nan, 0.0)
    assert np.isnan(pee) and np.isnan(err)


# --- summarize_contrast_map -------------------------------------------------------------------

GAINS = np.linspace(3000, 3600, 7)
FREQS = np.linspace(7000.0, 7000.1, 21)


def test_flat_noisy_map_is_mostly_tied():
    # No real structure: the raw brightest pixel is ~2.5 sigma of noise; most points are
    # within one standard error of the smoothed maximum.
    rng = np.random.default_rng(2)
    sigma = 0.016
    fid = 0.68 + sigma * rng.normal(size=(7, 21))
    s = ro.summarize_contrast_map(fid, np.full(fid.shape, sigma), GAINS, FREQS)
    assert set(s) == SUMMARY_KEYS
    assert s["tied_mask"].dtype == bool and s["tied_mask"].shape == fid.shape
    assert s["tied_mask"].mean() > 0.5
    assert np.nanmax(fid) - s["best_fid_smooth"] > 1.5 * sigma  # the winner's curse it avoids
    r, c = np.argwhere((GAINS[:, None] == s["best_gain"]) & (FREQS[None, :] == s["best_freq"]))[0]
    assert s["best_fid"] == fid[r, c] and s["best_fid_err"] == sigma
    assert s["median_fid_err"] == sigma


def test_exactly_flat_map_ties_everywhere():
    fid = np.full((7, 21), 0.5)
    s = ro.summarize_contrast_map(fid, np.full(fid.shape, 0.01), GAINS, FREQS)
    assert s["tied_mask"].all()
    assert s["best_fid_smooth"] == 0.5


def test_broad_peak_beats_a_single_bright_pixel():
    g, f = np.meshgrid(np.arange(7), np.arange(21), indexing="ij")
    fid = 0.9 - 0.02 * ((g - 2) ** 2 + 0.05 * (f - 15) ** 2)  # broad maximum at (2, 15)
    fid[6, 2] = 0.95  # one-pixel spike, brighter than the peak
    s = ro.summarize_contrast_map(fid, np.full(fid.shape, 0.01), GAINS, FREQS)
    assert (s["best_gain"], s["best_freq"]) == (GAINS[2], FREQS[15])
    assert s["best_fid"] == pytest.approx(0.9)
    assert s["tied_mask"][2, 15] and not s["tied_mask"][5, 0]
    smooth = s["fid_smooth_mat"]
    # 3x3 mean with edges extended by the nearest value, by hand at a corner
    pad = np.pad(fid, 1, mode="edge")
    assert smooth[0, 0] == pytest.approx(pad[0:3, 0:3].mean(), rel=1e-14)
    assert smooth[4, 9] == pytest.approx(fid[3:6, 8:11].mean(), rel=1e-14)


def test_all_nan_map_does_not_raise():
    fid = np.full((7, 21), np.nan)
    s = ro.summarize_contrast_map(fid, fid.copy(), GAINS, FREQS)
    for k in ("best_gain", "best_freq", "best_fid", "best_fid_err", "best_fid_smooth"):
        assert np.isnan(s[k])
    assert np.isnan(s["median_fid_err"]) and not s["tied_mask"].any()
    assert np.isnan(s["fid_smooth_mat"]).all()
    ro.report_contrast_optimum(s, "readout", GAINS, FREQS)
    assert ro.contrast_optimum_edges(s, GAINS, FREQS) == []
    assert ro.fid_err_title(fid) == ""


@pytest.mark.parametrize("shape", [(1, 21), (7, 1), (1, 1)])
def test_single_row_or_column_grid(shape):
    rng = np.random.default_rng(3)
    fid = 0.5 + 0.01 * rng.normal(size=shape)
    fid.flat[shape[0] * shape[1] // 2] = 0.9
    s = ro.summarize_contrast_map(fid, np.full(shape, 0.01), GAINS[: shape[0]], FREQS[: shape[1]])
    assert s["fid_smooth_mat"].shape == shape
    assert s["best_fid"] == 0.9
    assert s["tied_mask"].shape == shape and s["tied_mask"].sum() >= 1


def test_border_recommendation_is_flagged(capsys):
    # Smoothing with edge replication leaves border points noisier, so on a flat noisy map the
    # argmax lands on the border far more often than its share of the grid (review of F60).
    # The printout must say so; an interior optimum must not be flagged.
    rng = np.random.default_rng(11)
    n_border = 0
    for _ in range(200):
        fid = 0.68 + 0.016 * rng.normal(size=(7, 21))
        s = ro.summarize_contrast_map(fid, np.full(fid.shape, 0.016), GAINS, FREQS)
        n_border += bool(ro.contrast_optimum_edges(s, GAINS, FREQS))
    assert n_border / 200 > 0.6  # border cells are 35% of a 7x21 grid
    corner = np.full((7, 21), 0.5)
    corner[0, -1] = 0.9
    s = ro.summarize_contrast_map(corner, np.full(corner.shape, 0.01), GAINS, FREQS)
    assert ro.contrast_optimum_edges(s, GAINS, FREQS) == ["gain", "frequency"]
    ro.report_contrast_optimum(s, "readout", GAINS, FREQS)
    out = capsys.readouterr().out
    assert "WARNING: the recommended readout point is on the edge of the gain and frequency" in out
    g, f = np.meshgrid(np.arange(7), np.arange(21), indexing="ij")
    interior = 0.9 - 0.02 * ((g - 3) ** 2 + 0.05 * (f - 10) ** 2)
    s = ro.summarize_contrast_map(interior, np.full(interior.shape, 0.01), GAINS, FREQS)
    assert ro.contrast_optimum_edges(s, GAINS, FREQS) == []
    ro.report_contrast_optimum(s, "qubit", GAINS, FREQS)
    assert "WARNING" not in capsys.readouterr().out
    # axes shorter than 3 points have no meaningful border: a 1-row map flags only frequency
    row = np.full((1, 21), 0.5)
    row[0, 0] = 0.9
    s = ro.summarize_contrast_map(row, np.full(row.shape, 0.01), GAINS[:1], FREQS)
    assert ro.contrast_optimum_edges(s, GAINS[:1], FREQS) == ["frequency"]


def test_partial_map_picks_only_measured_points():
    # an interrupted sweep: the smoothed map is finite next to measured points, but the
    # recommendation must be a measured one
    fid = np.full((7, 21), np.nan)
    fid[0, :] = 0.4
    fid[1, :3] = 0.8
    s = ro.summarize_contrast_map(fid, np.full(fid.shape, 0.01), GAINS, FREQS)
    assert np.isfinite(s["fid_smooth_mat"][2, 0])
    assert s["best_gain"] == GAINS[1] and s["best_freq"] in FREQS[:3]
    assert not s["tied_mask"][np.isnan(fid)].any()


# --- the experiments end to end ---------------------------------------------------------------


class _FakeProg:
    """SingleShotProgram stand-in: unit-width g cloud at the origin, e cloud at I = 2."""

    rng = None
    shots = 600

    def __init__(self, soccfg, cfg):
        self.cfg = cfg

    def acquire(self, soc, load_pulses=True):
        cls = type(self)
        d = 2.0 if self.cfg["Pulse"] else 0.0
        i = cls.rng.normal(d, 1.0, cls.shots)
        q = cls.rng.normal(0.0, 1.0, cls.shots)
        return np.array([[i]]), np.array([[q]])


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(ro, "SingleShotProgram", _FakeProg)
    _FakeProg.rng = np.random.default_rng(11)


def _check(data, n_rows, n_cols, gain_pts, freq_pts, capsys):
    d = data["data"]
    assert NEW_KEYS | SUMMARY_KEYS <= set(d)
    for k in NEW_KEYS | {"fid_smooth_mat", "tied_mask"}:
        assert d[k].shape == (n_rows, n_cols)
        if k != "tied_mask":
            assert np.all(np.isfinite(d[k]))
    np.testing.assert_allclose(d["Pgg_mat"] + d["Pee_mat"] - 1, d["fid_mat"], rtol=0, atol=1e-12)
    # labelled overlap and analog SNR (F59): finite at every point of these d = 2 clouds
    assert np.all(np.isfinite(d["overlap_mat"])) and np.all(np.isfinite(d["snr_mat"]))
    np.testing.assert_allclose(
        d["fid_err_mat"],
        np.sqrt((d["Pgg_mat"] * (1 - d["Pgg_mat"]) + d["Pee_mat"] * (1 - d["Pee_mat"])) / 600),
        rtol=1e-12,
    )
    assert d["best_gain"] in gain_pts and d["best_freq"] in freq_pts
    assert d["tied_mask"].any()
    out = capsys.readouterr().out
    assert "Recommended" in out and "NOT written back" in out
    assert "WARNING: Pgg" not in out


def test_readout_optimize_saves_uncertainty_and_optimum(fake, tmp_path, capsys):
    cfg = {
        "cav_gain_Start": 3000,
        "cav_gain_Stop": 3600,
        "cav_gain_Points": 3,
        "trans_freq_start": 7000.0,
        "trans_freq_stop": 7000.1,
        "TransNumPoints": 4,
        "qubit_pulse_style": "arb",
        "pulse_gain": 3300,
        "pulse_freq": 7000.05,
    }
    exp = ro.ReadOpt_wSingleShotFF(
        path="SingleShot_OptReadout", outerFolder=str(tmp_path) + "/", cfg=cfg
    )
    data = exp.acquire(plotDisp=False)
    _check(data, 3, 4, exp.gain_pts, exp.trans_fpts, capsys)
    # the last point's pulse_gain/pulse_freq stay in the cfg: the optimum is not written back
    assert exp.cfg["pulse_gain"] == 3600 and exp.cfg["pulse_freq"] == exp.trans_fpts[-1]
    assert plt.gcf().axes[2].get_title().startswith("median 1 s.e. ")  # fidelity colorbar
    plt.close("all")
    exp.save_data(data)
    with h5py.File(exp.fname, "r") as f:
        for k in NEW_KEYS | SUMMARY_KEYS:
            assert k in f
        np.testing.assert_array_equal(f["tied_mask"][()], data["data"]["tied_mask"])
        assert f["best_fid"][()] == data["data"]["best_fid"]


def test_qubit_optimize_saves_uncertainty_and_optimum(fake, tmp_path, capsys):
    cfg = {
        "qubit_gain_Start": 1000,
        "qubit_gain_Stop": 3000,
        "qubit_gain_Points": 3,
        "qubit_freq_start": 4000.0,
        "qubit_freq_stop": 4004.0,
        "QubitNumPoints": 5,
        "qubit_pulse_style": "arb",
        "qubit_gain": 2000,
        "f_ge": 4002.0,
        "Pulse": True,
    }
    exp = ro.QubitPulseOpt_wSingleShotFF(
        path="SingleShot_OptQubit", outerFolder=str(tmp_path) + "/", cfg=cfg
    )
    data = exp.acquire(plotDisp=False)
    _check(data, 3, 5, exp.gain_pts, exp.qubit_fpts, capsys)
    assert exp.cfg["qubit_gain"] == 3000 and exp.cfg["f_ge"] == exp.qubit_fpts[-1]
    # the last point analysed sets threshold/angle attributes; the maps hold every point's
    d = data["data"]
    assert d["threshold_mat"][-1, -1] == exp.threshold and d["angle_mat"][-1, -1] == exp.angle
    plt.close("all")
