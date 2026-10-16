"""Hardware-free tests for the |g>-reference bracketing in QubitPulseOpt_wSingleShotFF (F33).

The |g> program plays no qubit pulse, so the qubit gain x frequency map takes it once per row
boundary (rows + 1 blocks) instead of at every point. Each point is analysed against the nearer
of the two blocks that bracket its row, and the g drift across each row is measured and flagged.
SingleShotProgram is replaced by a fake that logs every program and returns synthetic clouds.
See docs/experiments/qubit_optimize.md.

    python -m pytest tests/test_qubit_optimize_bracketing.py
"""

import matplotlib

matplotlib.use("Agg")

import h5py  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

import qicklab.experiments.readout_optimize as ro  # noqa: E402
from qicklab.analysis.readout import hist_process, labelled_overlap_error  # noqa: E402

SHOTS = 2000
SIGMA = 0.3  # cloud width (both quadratures)
E_I = 5.0  # e cloud centre on I; g starts at the origin, so the g-e separation is 5
WARNING = "WARNING: |g> reference drifted"


class _FakeProg:
    """Stands in for SingleShotProgram. Logs (Pulse, qubit_gain, f_ge) and the returned shots.

    The g cloud's I centre is ``drift * program_index`` (a linear drift in time, one unit of
    time per program); the e cloud sits at (e_centre, 0).
    """

    log = []
    drift = 0.0
    e_centre = E_I
    rng = None

    def __init__(self, soccfg, cfg):
        self.cfg = cfg

    def acquire(self, soc, load_pulses=True):
        cls = type(self)
        k = len(cls.log)
        centre = cls.e_centre if self.cfg["Pulse"] else cls.drift * k
        i = cls.rng.normal(centre, SIGMA, SHOTS)
        q = cls.rng.normal(0.0, SIGMA, SHOTS)
        cls.log.append(
            {
                "Pulse": self.cfg["Pulse"],
                "qubit_gain": self.cfg["qubit_gain"],
                "f_ge": self.cfg["f_ge"],
                "i": i,
                "q": q,
            }
        )
        return np.array([[i]]), np.array([[q]])


@pytest.fixture
def run(monkeypatch, tmp_path):
    monkeypatch.setattr(ro, "SingleShotProgram", _FakeProg)

    def _run(n_rows=3, n_cols=5, drift=0.0, style="arb", seed=1, e_centre=E_I):
        _FakeProg.log, _FakeProg.drift, _FakeProg.e_centre = [], drift, e_centre
        _FakeProg.rng = np.random.default_rng(seed)
        cfg = {
            "qubit_gain_Start": 1000,
            "qubit_gain_Stop": 3000,
            "qubit_gain_Points": n_rows,
            "qubit_freq_start": 4000.0,
            "qubit_freq_stop": 4004.0,
            "QubitNumPoints": n_cols,
            "qubit_pulse_style": style,
            "qubit_gain": 2000,
            "f_ge": 4002.0,
            "Pulse": True,
        }
        exp = ro.QubitPulseOpt_wSingleShotFF(
            path="SingleShot_OptQubit", outerFolder=str(tmp_path) + "/", cfg=cfg
        )
        data = exp.acquire(plotDisp=False)
        plt.close("all")
        return exp, data, _FakeProg.log

    return _run


def _slots(n_rows, n_cols):
    """Program index of g block b and of e point (r, c) in the bracketed schedule."""
    g_slot = [b * (n_cols + 1) for b in range(n_rows + 1)]
    e_slot = [[r * (n_cols + 1) + 1 + c for c in range(n_cols)] for r in range(n_rows)]
    return g_slot, e_slot


@pytest.mark.parametrize("n_rows,n_cols", [(3, 5), (2, 4), (2, 2)])
def test_program_count_and_order(run, n_rows, n_cols):
    exp, data, log = run(n_rows=n_rows, n_cols=n_cols)
    # rows + 1 g blocks plus one e program per grid point (was 2 x rows x cols)
    assert len(log) == (n_rows + 1) + n_rows * n_cols
    g_slot, e_slot = _slots(n_rows, n_cols)
    assert [k for k, p in enumerate(log) if not p["Pulse"]] == g_slot
    for r in range(n_rows):
        for c in range(n_cols):
            p = log[e_slot[r][c]]
            assert p["Pulse"] is True
            assert p["qubit_gain"] == int(exp.gain_pts[r])
            assert p["f_ge"] == exp.qubit_fpts[c]
    # the saved cfg is the last point's, with Pulse True (as before the change)
    assert exp.cfg["Pulse"] is True
    assert exp.cfg["qubit_gain"] == int(exp.gain_pts[-1])
    assert exp.cfg["f_ge"] == exp.qubit_fpts[-1]
    t = data["data"]["g_block_time"]
    assert t.shape == (n_rows + 1,)
    assert np.all(np.isfinite(t)) and np.all(np.diff(t) >= 0)


@pytest.mark.parametrize("n_cols", [2, 4, 5, 6])
def test_g_ref_index_is_nearer_block(run, n_cols):
    n_rows = 2
    _, data, _ = run(n_rows=n_rows, n_cols=n_cols)
    idx = data["data"]["g_ref_index"]
    g_slot, e_slot = _slots(n_rows, n_cols)
    for r in range(n_rows):
        for c in range(n_cols):
            # never farther in time than the other bracketing block (ties go to the opening one)
            d_open = e_slot[r][c] - g_slot[r]
            d_close = g_slot[r + 1] - e_slot[r][c]
            assert idx[r, c] == (r if d_open <= d_close else r + 1)
    if n_cols == 5:
        np.testing.assert_array_equal(idx, [[0, 0, 0, 1, 1], [1, 1, 1, 2, 2]])


@pytest.mark.parametrize("style", ["arb", "const"])
def test_each_point_analysed_against_its_block(run, style):
    n_rows, n_cols = 2, 5
    exp, data, log = run(n_rows=n_rows, n_cols=n_cols, drift=0.02, style=style)
    d = data["data"]
    g_slot, e_slot = _slots(n_rows, n_cols)
    for r in range(n_rows):
        for c in range(n_cols):
            g = log[g_slot[d["g_ref_index"][r, c]]]
            e = log[e_slot[r][c]]
            fid, threshold, angle = hist_process(
                data=[g["i"], g["q"], e["i"], e["q"]], plot=False, normalize="per_class"
            )
            assert d["fid_mat"][r, c] == fid
            # the overlap and the SNR use the same labelled g/e pair for every drive style
            assert d["overlap_mat"][r, c] == labelled_overlap_error(g["i"], g["q"], e["i"], e["q"])
            assert d["snr_mat"][r, c] == ro.analog_snr(g["i"], g["q"], e["i"], e["q"])
    # fid/threshold/angle attributes hold the last grid point's analysis, as before
    assert exp.fid == fid and exp.threshold == threshold and exp.angle == angle


def test_linear_g_drift_is_flagged(run, capsys):
    # 0.1 per program: the closing block of a 5-column row is 6 programs later, so g moves
    # 0.6 toward e across every row = 2 sigma (sigma 0.3). The g-e separation shrinks as g
    # walks toward e: 5 - 0.1 * (opening block's program index) = 5, 4.4, 3.8.
    _, data, _ = run(n_rows=3, n_cols=5, drift=0.1)
    frac, n_sigma = data["data"]["g_drift_frac"], data["data"]["g_drift_sigma"]
    np.testing.assert_allclose(frac, 0.6 / np.array([5.0, 4.4, 3.8]), rtol=0.05)
    assert np.all(frac > ro.G_DRIFT_WARN_FRAC)
    np.testing.assert_allclose(n_sigma, 0.6 / SIGMA, rtol=0.15)
    assert capsys.readouterr().out.count(WARNING) == 3


def test_no_drift_is_not_flagged(run, capsys):
    _, data, _ = run(n_rows=3, n_cols=5, drift=0.0)
    frac = data["data"]["g_drift_frac"]
    assert np.all(np.isfinite(frac))
    assert np.all(np.abs(frac) < 0.01)
    assert np.all(np.abs(data["data"]["g_drift_sigma"]) < 0.2)
    assert WARNING not in capsys.readouterr().out


def test_noise_on_a_small_separation_is_not_flagged(run, capsys):
    # No drift, but a g-e separation of only 0.5 sigma: the median-shift noise (standard
    # error 1.2533 * sqrt(2 / SHOTS) = 0.04 sigma) divided by 0.5 sigma pushes |frac| past
    # 0.05 in many rows. The standard-error gate keeps those rows from warning.
    n_rows = 12
    _, data, _ = run(n_rows=n_rows, n_cols=3, e_centre=0.5 * SIGMA, seed=3)
    frac, n_sigma = data["data"]["g_drift_frac"], data["data"]["g_drift_sigma"]
    assert np.sum(np.abs(frac) > ro.G_DRIFT_WARN_FRAC) >= 3  # a frac-only gate would fire
    gate = ro.G_DRIFT_WARN_NSE * 1.2533 * np.sqrt(2.0 / SHOTS)
    assert np.all(np.abs(n_sigma) < gate)
    assert WARNING not in capsys.readouterr().out


def test_save_data_writes_new_arrays(run):
    exp, data, _ = run(n_rows=2, n_cols=3)
    exp.save_data(data)
    with h5py.File(exp.fname, "r") as f:
        for key in (
            "fid_mat",
            "overlap_mat",
            "snr_mat",
            "g_ref_index",
            "g_block_time",
            "g_drift_sigma",
        ):
            assert key in f
        assert f["g_drift_frac"].shape == (2,)
        np.testing.assert_array_equal(f["g_ref_index"][()], data["data"]["g_ref_index"])


def test_g_reference_drift_sign_and_scale():
    rng = np.random.default_rng(0)
    g0 = (rng.normal(0, 1, 4000), rng.normal(0, 1, 4000))
    e = (rng.normal(0, 1, 4000), rng.normal(10, 1, 4000))  # g-e axis along +Q, separation 10
    g1 = (g0[0] + 3.0, g0[1] + 0.5)  # 3 across the axis (ignored), 0.5 toward e
    frac, n_sigma = ro.g_reference_drift(g0, g1, e)
    assert frac == pytest.approx(0.05, abs=0.005)
    assert n_sigma == pytest.approx(0.5, rel=0.1)
    g2 = (g0[0], g0[1] - 1.0)  # away from e
    assert ro.g_reference_drift(g0, g2, e)[0] == pytest.approx(-0.1, abs=0.005)
    same = ro.g_reference_drift(g0, g0, g0)
    assert np.isnan(same[0]) and np.isnan(same[1])
