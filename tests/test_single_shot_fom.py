"""single_shot saves its own readout figures of merit (review F61).

Before 2026-10 the h5 held only the clouds, threshold and angle: the contrast lived in the png
title, so readout quality and drift could not be tracked across calibrations. Synthetic shots
only (a fake program class replaces SingleShotProgram). docs/experiments/single_shot.md#outputs

    python -m pytest tests/test_single_shot_fom.py
"""

import h5py
import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import qicklab.experiments.single_shot as ss_mod  # noqa: E402
from qicklab.analysis.readout import (  # noqa: E402
    hist_process,
    readout_assignment_errors,
    single_shot_figures_of_merit,
)
from qicklab.core.experiment import finish  # noqa: E402
from qicklab.runs.single_shot import _extract_iq_from_singleshot_data  # noqa: E402

FOM_KEYS = {
    "contrast_hist",
    "assignment_fidelity",
    "P_e_given_g",
    "P_g_given_e",
    "g_center_median",
    "e_center_median",
    "g_center_mean",
    "e_center_mean",
    "snr_analog",
    "cal_contrast",
    "cal_threshold",
    "cal_axis",
    "cal_midpoint",
    "readout_gate_pass",
}
G, E = np.array([1.0, -2.0]), np.array([4.0, 2.0])  # 5 sigma apart


def _cloud(rng, n, center, other, n_wrong):
    """n unit-noise shots at ``center``, the first n_wrong of them at ``other`` (prep errors)."""
    pts = rng.normal(size=(n, 2)) + center
    pts[:n_wrong] += other - center
    return pts[:, 0], pts[:, 1]


def _shots(seed=0, n=2000, n_th=60, n_dec=150):
    rng = np.random.default_rng(seed)
    return (*_cloud(rng, n, G, E, n_th), *_cloud(rng, n, E, G, n_dec))


def test_errors_reproduce_injected_prep_errors_and_identities():
    ig, qg, ie, qe = _shots()
    fid, thr, theta = hist_process(data=[ig, qg, ie, qe], plot=False)
    fom, warnings = single_shot_figures_of_merit(ig, qg, ie, qe, fid, thr, theta)
    assert set(fom) == FOM_KEYS and warnings == []
    assert fom["contrast_hist"] == fid
    # 5 sigma apart: the misassigned shots are (to ~0.6% per class) the injected prep errors
    assert fom["P_e_given_g"] == pytest.approx(60 / 2000, abs=8e-3)
    assert fom["P_g_given_e"] == pytest.approx(150 / 2000, abs=8e-3)
    assert fom["assignment_fidelity"] == 1 - 0.5 * (fom["P_e_given_g"] + fom["P_g_given_e"])
    # Exact because hist_process returns the threshold its contrast is counted at
    # (cdf_gap_threshold, rule g := I <= thr; review F62). The pre-F62 histogram version
    # (left bin edge) misses this by ~5e-4 here.
    assert fom["assignment_fidelity"] == pytest.approx(0.5 * (1 + fid), abs=1e-12)
    # medians: robust to the prep-error shots (7.5% of e shots at G pull the median ~0.1 sigma)
    np.testing.assert_allclose(fom["g_center_median"], G, atol=0.1)
    np.testing.assert_allclose(fom["e_center_median"], E, atol=0.2)
    np.testing.assert_allclose(fom["g_center_mean"], [np.mean(ig), np.mean(qg)], rtol=0)
    # the calibration's own discriminator, under distinct names
    np.testing.assert_allclose(fom["cal_axis"], (E - G) / 5.0, atol=0.05)
    assert fom["snr_analog"] > 2 and fom["readout_gate_pass"] == 1.0
    assert abs(fom["cal_contrast"] - fid) < 2e-2


@pytest.mark.parametrize(
    "n, sep, gate",
    [(400, 5.0, "only 400 labeled shots"), (2000, 0.6, "analog SNR"), (2000, 0.2, "contrast")],
)
def test_gate_flag_matches_the_parity_readout_gates(n, sep, gate):
    rng = np.random.default_rng(1)
    g = rng.normal(size=(n, 2))
    e = rng.normal(size=(n, 2)) + [sep, 0.0]
    fid, thr, theta = hist_process(data=[g[:, 0], g[:, 1], e[:, 0], e[:, 1]], plot=False)
    fom, warnings = single_shot_figures_of_merit(
        g[:, 0], g[:, 1], e[:, 0], e[:, 1], fid, thr, theta
    )
    assert fom["readout_gate_pass"] == 0.0
    assert any(gate in w for w in warnings)


def test_calibration_failure_is_nan_not_an_exception():
    ig, qg, ie, qe = (x[:5] for x in _shots())  # < 10 shots per class: calibrate raises
    fid, thr, theta = hist_process(data=[ig, qg, ie, qe], plot=False)
    fom, warnings = single_shot_figures_of_merit(ig, qg, ie, qe, fid, thr, theta)
    assert len(warnings) == 1 and "calibration failed" in warnings[0]
    for key in ("snr_analog", "cal_contrast", "cal_threshold", "readout_gate_pass"):
        assert np.isnan(fom[key])
    assert np.all(np.isnan(fom["cal_axis"])) and np.all(np.isnan(fom["cal_midpoint"]))
    assert np.isfinite(fom["P_e_given_g"]) and fom["contrast_hist"] == fid


# --- SingleShotProgramFFMUX end to end --------------------------------------------------------


def _program_cls(n_reads, seed=0):
    shots = [_shots(seed + r) for r in range(n_reads)]

    class _Prog:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True):
            k = 2 if self.cfg["Pulse"] else 0
            return (
                [s[k][None, :] for s in shots],
                [s[k + 1][None, :] for s in shots],
            )

    return _Prog


def _experiment(tmp_path, monkeypatch, n_reads=1, **cfg):
    monkeypatch.setattr(ss_mod, "SingleShotProgram", _program_cls(n_reads))
    cfg = {"number_of_pulses": 1, "readout_length": 3.0, "qubit_ch": 1, **cfg}
    return ss_mod.SingleShotProgramFFMUX(
        path="SingleShot", outerFolder=str(tmp_path) + "/", cfg=cfg, soc=None
    )


def test_acquire_saves_fom_per_read_and_h5(tmp_path, monkeypatch, capsys):
    exp = _experiment(tmp_path, monkeypatch, n_reads=2, Read_Indeces=[0, 3])
    data = exp.acquire()
    d = data["data"]
    for r in ("0", "3", "1"):  # read 3 is enumeration index 1: mirrored like i_g<i>
        assert {k + r for k in FOM_KEYS} <= set(d)
    for k in FOM_KEYS:
        np.testing.assert_array_equal(d[k + "3"], d[k + "1"])
    assert [d["contrast_hist0"], d["contrast_hist3"]] == exp.fid
    assert d["threshold"] == exp.threshold and d["angle"] == exp.angle  # unchanged keys

    # run_t1_ss counts its readout_errors with the same helper on the same shots: bit for bit
    errs = readout_assignment_errors(
        *_extract_iq_from_singleshot_data(data, "g"),
        *_extract_iq_from_singleshot_data(data, "e"),
        d["angle"][0],
        d["threshold"][0],
    )
    assert errs == (d["P_e_given_g0"], d["P_g_given_e0"])

    finish(ss_mod.SingleShotProgramFFMUX, exp, data, plotDisp=False)
    assert exp.fid == d["contrast_hist0"]  # display keeps fid = contrast (the png number)
    with h5py.File(exp.fname, "r") as f:
        assert f["contrast_hist0"][()] == d["contrast_hist0"]
        np.testing.assert_array_equal(f["cal_axis3"][()], d["cal_axis3"])
        assert f["readout_gate_pass0"][()] == 1.0


def test_thermal_mode_saves_no_fom(tmp_path, monkeypatch):
    exp = _experiment(tmp_path, monkeypatch, number_of_pulses=0, thermal_pi_calibration=False)
    d = exp.acquire()["data"]
    assert d["thermal_mode"] is True
    assert not any(k.startswith(tuple(FOM_KEYS)) for k in d)


def test_pooled_png_title_names_the_contrast():
    matplotlib.pyplot.close("all")
    ig, qg, ie, qe = _shots()
    fid, _, _ = hist_process(data=[ig, qg, ie, qe], plot=True, normalize="pooled")
    title = matplotlib.pyplot.gcf().axes[2].get_title()
    assert title == f"Contrast C = {fid * 100:.2f}% (F_assign = {50 * (1 + fid):.2f}%)"
    matplotlib.pyplot.close("all")
    hist_process(data=[ig, qg, ie, qe], plot=True, normalize="per_class")
    assert matplotlib.pyplot.gcf().axes[2].get_title().startswith("Fi: ")
    matplotlib.pyplot.close("all")
