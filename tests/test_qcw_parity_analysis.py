"""Quasi-CW charge-dispersion parity analysis (F72), hardware-free.

The quasi-CW record is a per-shot g/e readout whose P(e) is set by the charge parity
(drive on resonance with one parity branch). The KMeans split is the g/e assignment, not a
parity trace; the parity rate comes from qcw_parity_analysis: readout self-calibrated from
the record, analyze_modified_ramsey_record with the mapping fitted, dt the program's
scheduled rep period, a feasibility warning below 10 samples per expected dwell and the
KMeans blob gate. docs/experiments/charge_dispersion.md#analysis.
"""

import glob
import os
import types

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

import qicklab.runs.charge_dispersion as cd_runs  # noqa: E402
from qicklab.analysis.iq import kmeans_split  # noqa: E402
from qicklab.analysis.readout import calibrate_readout_from_record  # noqa: E402
from qicklab.core.context import Context  # noqa: E402
from qicklab.runs.charge_dispersion import (  # noqa: E402
    MIN_BLOB_SNR,
    MIN_SAMPLES_PER_DWELL,
    qcw_parity_analysis,
)
from tests.regression import capture  # noqa: E402

# raw-accumulator-like scale: blob centres ~ 1e4 apart, sigma ~ 2.5e3
G_CENTER = np.array([12000.0, -3000.0])
E_CENTER = np.array([2000.0, 4000.0])
SIGMA = 2500.0


def _telegraph_record(n, dt_s, gamma_hz, p_off, p_on, seed):
    """Symmetric telegraph (rate gamma each way) sampled every dt; each shot is |e> with
    P(e | parity) = p_off / p_on, then read out as a Gaussian IQ cloud."""
    rng = np.random.default_rng(seed)
    flip = 0.5 * (1.0 - np.exp(-2.0 * gamma_hz * dt_s))  # exact for the sampled telegraph
    flips = rng.random(n) < flip
    parity = np.cumsum(flips) % 2
    excited = rng.random(n) < np.where(parity == 1, p_on, p_off)
    centers = np.where(excited[:, None], E_CENTER, G_CENTER)
    iq = centers + rng.normal(0.0, SIGMA, size=(n, 2))
    return iq[:, 0], iq[:, 1], parity


def test_self_calibration_recovers_the_clouds():
    i, q, _ = _telegraph_record(20000, 1e-4, 400.0, 0.05, 0.6, seed=1)
    cal = calibrate_readout_from_record(i, q)
    assert np.allclose(cal["g_center"], G_CENTER, atol=150)
    assert np.allclose(cal["e_center"], E_CENTER, atol=150)
    assert cal["proj_g_sigma"] == pytest.approx(SIGMA, rel=0.05)
    assert cal["w_e"] == pytest.approx(0.5 * (0.05 + 0.6), abs=0.02)
    assert cal["proj_e_mean"] > cal["proj_g_mean"]
    assert cal["proj_g_mean"] < cal["threshold"] < cal["proj_e_mean"]
    assert 0.9 < cal["contrast"] <= 1.0
    assert cal["clean_cloud_source"] == "record_mixture"


def test_parity_rate_recovered_with_fitted_mapping(tmp_path):
    """Resolved record (25 samples per dwell): the rate and the mapping are recovered, the
    mapping is fitted (not the seed) and there is no feasibility warning."""
    gamma, dt_us = 400.0, 100.0
    i, q, _ = _telegraph_record(20000, dt_us * 1e-6, gamma, 0.05, 0.6, seed=2)
    states, *_, blob_snr = kmeans_split(np.column_stack([i, q]), min_blob_snr=MIN_BLOB_SNR)
    assert blob_snr >= MIN_BLOB_SNR and states.any()
    out = qcw_parity_analysis(i, q, dt_us, blob_snr, {}, str(tmp_path), "rec_parity", "test")
    assert out["analysed"], out["reason"]
    assert out["feasibility_warning"] is None
    assert out["samples_per_expected_dwell"] == pytest.approx(25.0)
    s = out["summary"]
    assert s["identifiable"]
    assert s["mapping_fitted"]
    assert s["mapping_probabilities_calibrated"] is False
    assert s["dt_nominal_s"] == pytest.approx(dt_us * 1e-6)
    assert abs(s["gamma01_hz"] - gamma) < max(3 * s["gamma01_err_hz"], 0.25 * gamma)
    p0, p1 = sorted((s["mapping_p_e_state0_fit"], s["mapping_p_e_state1_fit"]))
    assert p0 == pytest.approx(0.05, abs=0.05)
    assert p1 == pytest.approx(0.6, abs=0.08)
    assert (tmp_path / "rec_parity_analysis.json").exists()
    assert (tmp_path / "rec_parity_hmm.png").exists()


def test_sparse_record_warns_but_runs(tmp_path):
    """850 us relax with a 50 us drive: rep 926.8 us, 2.7 samples per 2.5 ms dwell: warned."""
    rep_us = 926.81
    i, q, _ = _telegraph_record(1000, rep_us * 1e-6, 400.0, 0.05, 0.6, seed=3)
    *_, blob_snr = kmeans_split(np.column_stack([i, q]), min_blob_snr=MIN_BLOB_SNR)
    out = qcw_parity_analysis(i, q, rep_us, blob_snr, {}, None, "x", "test")
    assert out["samples_per_expected_dwell"] < MIN_SAMPLES_PER_DWELL
    assert "cannot resolve parity dwells" in out["feasibility_warning"]
    assert "failed" not in (out["reason"] or "")


def test_single_blob_is_gated(tmp_path):
    """No drive response: one blob. KMeans would split it ~50/50; the gate assigns every
    shot 0 and the parity analysis is skipped."""
    rng = np.random.default_rng(4)
    iq = G_CENTER + rng.normal(0.0, SIGMA, size=(2000, 2))
    states, *_, blob_snr = kmeans_split(iq, min_blob_snr=MIN_BLOB_SNR)
    assert blob_snr < MIN_BLOB_SNR and not states.any()
    out = qcw_parity_analysis(iq[:, 0], iq[:, 1], 100.0, blob_snr, {}, str(tmp_path), "one", "test")
    assert not out["analysed"]
    assert "not resolved" in out["reason"]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("variant", capture.VARIANTS)
def test_qcw_dt_is_the_program_rep_period(variant):
    """The record's dt is the emitted schedule: 1 + 50 + 0.5 us drive block, tone + 10 us,
    relax; the old cfg formula (1 + 0.5 + readout_length + 10 + relax) omitted the drive."""
    from tests.test_program_timing import QCW_PERIOD, _program

    soccfg = capture.FakeSocCfg(variant)
    prog = _program("ChargeDispersionQuasiCW", soccfg, relax_delay=850, expts=1, step=0)
    assert prog.scheduled_rep_period_cycles() == QCW_PERIOD[variant]
    old = 1.0 + 0.5 + 15.0 + 10 + 850
    assert prog.scheduled_rep_period_us() - old == pytest.approx(50.3, abs=0.05)


# --- run-level: the two call sites save the program-derived dt and gate the KMeans split ---

N_RUN_SHOTS = 600
QCW_RELAX_US = 850


def _two_blob_shots(n, seed):
    rng = np.random.default_rng(seed)
    excited = rng.random(n) < 0.3
    iq = np.where(excited[:, None], E_CENTER, G_CENTER) + rng.normal(0.0, SIGMA, size=(n, 2))
    return iq[:, 0], iq[:, 1]


def _one_blob_shots(n, seed):
    rng = np.random.default_rng(seed)
    iq = G_CENTER + rng.normal(0.0, SIGMA, size=(n, 2))
    return iq[:, 0], iq[:, 1]


class _RunCtx:
    """Minimal Context for the quasi-CW runs: a regime-A cfg and a FakeSocCfg board."""

    working_config = Context.working_config

    def __init__(self, outer, soccfg):
        from qicklab.hardware.board import BaseConfig
        from tests.test_program_timing import REGIME_A_EXTRA, _cfg

        self.config = _cfg(BaseConfig, **REGIME_A_EXTRA)
        self.outerFolder = outer
        self.qubit_frequency_center = 2651.0
        self.yoko = types.SimpleNamespace(query=lambda cmd: "0.1")
        self.soc = None
        self.soccfg = soccfg


@pytest.fixture
def qcw_run(monkeypatch, tmp_path):
    """The real ChargeDispersionQuasiCW (real program on a FakeSocCfg) with acquire replaced
    by synthetic shots; returns (ctx factory, list of the built instances)."""
    instances = []
    shots = {"fn": _two_blob_shots}

    class _QCW(cd_runs.ChargeDispersionQuasiCW):
        def acquire(self, progress=False, debug=False, load_pulses=True, print_time=False):
            instances.append(self)
            i, q = shots["fn"](N_RUN_SHOTS, seed=len(instances))
            return {"data": {"x_pts": [self.cfg["start"]], "raw_i": i, "raw_q": q}}

    monkeypatch.setattr(cd_runs, "ChargeDispersionQuasiCW", _QCW)
    monkeypatch.setattr(cd_runs.plt, "savefig", lambda *a, **k: None)
    monkeypatch.setattr(cd_runs.plt, "show", lambda *a, **k: None)
    outer = str(tmp_path) + os.sep

    def make(variant, shot_fn):
        shots["fn"] = shot_fn
        return _RunCtx(outer, capture.FakeSocCfg(variant))

    return make, instances, tmp_path


def _check_saved_record(npz_path, prog, variant, binary_key, gated):
    from tests.test_program_timing import QCW_PERIOD

    rec = np.load(npz_path, allow_pickle=True)
    f_time = capture.FakeSocCfg(variant)["tprocs"][0]["f_time"]
    rep_us = float(rec["rep_period_us"])
    # the time axis is the emitted schedule, not 1 + 0.5 + readout_length + 10 + relax_delay
    assert rep_us == pytest.approx(prog.scheduled_rep_period_us(), rel=1e-12)
    assert rep_us == pytest.approx(QCW_PERIOD[variant] / f_time, rel=1e-12)
    assert rep_us - (1.0 + 0.5 + 15.0 + 10 + QCW_RELAX_US) == pytest.approx(50.3, abs=0.05)
    elapsed = rec["elapsed_s"]
    assert len(elapsed) == N_RUN_SHOTS
    assert elapsed[1] == pytest.approx(rep_us * 1e-6, rel=1e-12)
    assert elapsed[-1] == pytest.approx((N_RUN_SHOTS - 1) * rep_us * 1e-6, rel=1e-12)
    parity = rec["parity_analysis"].item()
    assert parity["rep_period_us"] == pytest.approx(rep_us, rel=1e-12)
    states = rec[binary_key]
    if gated:
        # one blob: the call site's gate assigns every shot 0 (ungated KMeans splits it)
        assert float(rec["blob_snr"]) < MIN_BLOB_SNR
        assert not states.any()
        assert not parity["analysed"] and "not resolved" in parity["reason"]
    else:
        assert float(rec["blob_snr"]) >= MIN_BLOB_SNR
        assert states.any()
        assert "failed" not in (parity["reason"] or "")
    return parity


@pytest.mark.parametrize("variant", capture.VARIANTS)
@pytest.mark.parametrize("gated", [False, True])
def test_run_charge_dispersion_quasicw_saves_program_dt_and_gates(qcw_run, variant, gated):
    make, instances, tmp_path = qcw_run
    ctx = make(variant, _one_blob_shots if gated else _two_blob_shots)
    cd_runs.run_charge_dispersion_quasicw(
        ctx,
        {"repetitions": N_RUN_SHOTS, "relax_delay": QCW_RELAX_US, "probe_freq": 2651.0},
        {"Gauss": False},
    )
    (npz,) = glob.glob(str(tmp_path / "ChargeDispersion" / "ChargeDispersionQuasiCW_*.npz"))
    (inst,) = instances
    parity = _check_saved_record(npz, inst.prog, variant, "binary_amps", gated)
    assert parity["feasibility_warning"]  # 2.7 samples per 2.5 ms dwell


@pytest.mark.parametrize("variant", capture.VARIANTS)
@pytest.mark.parametrize("gated", [False, True])
def test_run_two_tone_quasicw_saves_program_dt_and_gates(qcw_run, monkeypatch, variant, gated):
    make, instances, tmp_path = qcw_run
    ctx = make(variant, _one_blob_shots if gated else _two_blob_shots)
    x_pts = np.linspace(2649.0, 2653.0, 5)

    class _Spec:
        def __init__(self, path=None, cfg=None, soc=None, soccfg=None, outerFolder=None):
            self.cfg = cfg

        def acquire(self):
            amp = np.exp(-((x_pts - 2651.0) ** 2))
            return {"data": {"x_pts": x_pts, "avgi": [[amp]], "avgq": [[0 * amp]]}}

    choice = {
        "peak_info_raw": {"peak_vals": [1.0]},
        "freqs": [2651.0],  # the centred highest peak: the quasi-CW record runs on it
        "peak_sep": None,
        "source": "fake",
    }
    monkeypatch.setattr(cd_runs, "QubitSpecSliceFF", _Spec)
    monkeypatch.setattr(cd_runs, "finish", lambda *a, **k: None)
    monkeypatch.setattr(
        cd_runs, "choose_two_tone_freqs_from_lorentz_or_peaks", lambda *a, **k: choice
    )
    monkeypatch.setattr(
        cd_runs, "save_two_tone_plot", lambda save_dir, **k: os.path.join(save_dir, "attempt")
    )
    params = {
        "df": 0.5,
        "dV": 0.01,
        "voltage_min": 0.0,
        "voltage_max": 0.2,
        "max_voltage_tries": 1,
        "num_cycles": 1,
        "reps": 10,
        "rounds": 1,
        "Gauss": False,
        "relax_delay": 10,
        "qubit_length": 50.0,
        "SpecSpan": 2.0,
        "SpecNumPoints": 5,
        "qcw_repetitions": N_RUN_SHOTS,
        "qcw_relax_delay": QCW_RELAX_US,
        "use_upper_peak": True,
    }
    cd_runs.run_two_tone_charge_dispersion_quasicw(
        ctx,
        params,
        {"Gauss": False, "min_sep_MHz": 0.1, "fit_window_mhz": 1.0, "prominent_ratio": 0.5},
        {},
    )
    (npz,) = glob.glob(str(tmp_path / "TwoToneChargeDispersion" / "Cycle_000_QuasiCW_*.npz"))
    (inst,) = instances
    _check_saved_record(npz, inst.prog, variant, "binary_states", gated)
