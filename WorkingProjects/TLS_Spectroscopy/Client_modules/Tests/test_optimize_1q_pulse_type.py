import os
import sys

import numpy as np
import pytest


REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mOptimize1Q as O


def base_cfg():
    return {
        "qubit_pi_freq": 2534.25,
        "qubit_pi_gain": 5600,
        "qubit_pi2_gain": 2875,
        "read_pulse_freq": 7249.0,
        "read_pulse_gain": 3500,
    }


def optimizer(cls, tmp_path, pulse_type="X180", num_pi=1):
    return cls(
        soc=None, soccfg=None, path="q4", outerFolder=str(tmp_path), cfg=base_cfg(),
        freqs_mhz=np.array([2534.0, 2534.5]), gains=np.array([2700, 2900]),
        shots=25, num_pi=num_pi, pulse_type=pulse_type, save=False)


@pytest.mark.parametrize(
    "pulse_type,num_pi,expected",
    [("X180", 1, 1), ("x180", 3, 3), ("X90", 1, 2), ("x90", 3, 6)],
)
def test_optimizer_drive_pulses_matches_rabi_semantics(pulse_type, num_pi, expected):
    assert O.optimizer_drive_pulses(pulse_type, num_pi) == expected


@pytest.mark.parametrize("pulse_type", ["X45", "", None])
def test_optimizer_rejects_unknown_pulse_type(pulse_type):
    with pytest.raises(ValueError, match="pulse_type"):
        O.optimizer_drive_pulses(pulse_type, 1)


@pytest.mark.parametrize("num_pi", [0, -1, 2, 4])
def test_optimizer_requires_positive_odd_logical_pi_count(num_pi):
    with pytest.raises(ValueError, match="positive odd"):
        O.optimizer_drive_pulses("X180", num_pi)


def test_readout_optimizer_uses_calibrated_x90_gain_and_two_pulses(monkeypatch,
                                                                   tmp_path):
    seen = {}

    class FakeSingleShot:
        def __init__(self, cfg, repeats, **kw):
            seen["cfg"] = dict(cfg)
            seen["repeats"] = repeats
            self.max_F = 0.91

        def acquire(self, progress=False, plotDisp=False):
            seen["acquired"] = True

    monkeypatch.setattr(O, "SingleShot1Q", FakeSingleShot)
    exp = optimizer(O.ReadoutOptimize, tmp_path, pulse_type="X90")
    value = exp._fidelity_at(7249.2, 4100)
    assert value == 0.91
    assert seen["cfg"]["qubit_gain"] == 2875
    assert seen["cfg"]["read_pulse_freq"] == 7249.2
    assert seen["cfg"]["read_pulse_gain"] == 4100
    assert seen["repeats"] == 2
    assert seen["acquired"]


def test_readout_optimizer_uses_x180_gain_and_odd_error_amplification(monkeypatch,
                                                                     tmp_path):
    seen = {}

    class FakeSingleShot:
        def __init__(self, cfg, repeats, **kw):
            seen["cfg"] = dict(cfg)
            seen["repeats"] = repeats
            self.max_F = 0.92

        def acquire(self, progress=False, plotDisp=False):
            pass

    monkeypatch.setattr(O, "SingleShot1Q", FakeSingleShot)
    exp = optimizer(O.ReadoutOptimize, tmp_path, pulse_type="X180", num_pi=3)
    exp._fidelity_at(7249.2, 4100)
    assert seen["cfg"]["qubit_gain"] == 5600
    assert seen["repeats"] == 3


def test_x90_qubit_optimizer_reports_measured_pi2_gain(tmp_path):
    exp = optimizer(O.QubitPulseOptimize, tmp_path, pulse_type="X90")
    exp._sweep = lambda progress=False: np.array([[0.75, 0.81], [0.96, 0.82]])
    out = exp.acquire()
    data = out["data"]
    assert data["best_qubit_pi2_gain"] == 2900
    assert data["best_qubit_pi_freq"] == 2534.0
    assert "best_qubit_pi_gain" not in data
    assert data["number_drive_pulses"] == 2
    assert data["pulse_type"] == "X90"
    assert data["x90_validation"] is None


def test_x90_validation_checks_population_return_and_phase_axes(monkeypatch,
                                                                 tmp_path):
    seen = {}

    class FakeSingleShot:
        def __init__(self, cfg, repeats, **kw):
            seen.setdefault("ss_cfgs", []).append((dict(cfg), repeats))
            self.I_0 = np.full(20, -1.0)
            self.Q_0 = np.zeros(20)
            if cfg["qubit_gain"] == 5600:
                self.I_1 = np.full(20, 1.0)
            elif repeats == 1:
                self.I_1 = np.r_[np.full(10, -1.0), np.full(10, 1.0)]
            else:
                self.I_1 = np.full(20, -1.0)
            self.Q_1 = np.zeros(20)
            self.calib_params = {
                "scale_factor": 1.0, "threshold": 0.0,
                "read_theta": 0.0, "ground_threshold": -0.5,
            }

        def acquire(self, **kw):
            return None

    class FakeRoundTrip:
        def __init__(self, cfg, ff_gain, flux_hold_us, rounds, **kw):
            seen["channel_cfg"] = dict(cfg)
            seen["ff_gain"] = ff_gain
            seen["flux_hold_us"] = flux_hold_us
            seen["rounds"] = rounds
            self.metrics = {
                "reference_contrast": 0.82,
                "coherence_magnitude": 0.91,
                "ramsey_i": 0.90,
                "ramsey_q": 0.08,
            }

        def acquire(self, **kw):
            return None

    monkeypatch.setattr(O, "SingleShot1Q", FakeSingleShot)
    monkeypatch.setattr(O, "RoundTripRamsey", FakeRoundTrip)
    exp = optimizer(O.QubitPulseOptimize, tmp_path, pulse_type="X90")
    exp.soc = object()
    exp.soccfg = object()
    exp.cfg["x90_validation_rounds"] = 3
    result = exp._validate_x90(2534.4, 2810)
    assert result["passed"] is True
    assert seen["ss_cfgs"][0][0]["qubit_gain"] == 5600
    assert np.isclose(result["population_1x"], 0.5)
    assert np.isclose(result["population_4x"], 0.0)
    assert seen["channel_cfg"]["qubit_pi2_gain"] == 2810
    assert seen["channel_cfg"]["qubit_pi_freq"] == 2534.4
    assert all(cfg["qubit_pi_freq"] == 2534.4 for cfg, repeats in seen["ss_cfgs"])
    assert seen["channel_cfg"]["reset_mode"] == "passive"
    assert seen["ff_gain"] == 0.0
    assert seen["flux_hold_us"] == 0.0
    assert seen["rounds"] == 3


def test_x180_qubit_optimizer_keeps_half_gain_as_seed_only(tmp_path):
    exp = optimizer(O.QubitPulseOptimize, tmp_path, pulse_type="X180")
    exp._sweep = lambda progress=False: np.array([[0.75, 0.81], [0.96, 0.82]])
    out = exp.acquire()
    data = out["data"]
    assert data["best_qubit_pi_gain"] == 2900
    assert data["qubit_pi2_gain_seed"] == 1450
    assert "best_qubit_pi2_gain" not in data
    assert data["number_drive_pulses"] == 1
    assert data["pulse_type"] == "X180"


def test_cfg_can_select_pulse_type_and_logical_pi_count(tmp_path):
    cfg = base_cfg()
    cfg["pulse_type"] = "x90"
    cfg["num_pi"] = 3
    exp = O.QubitPulseOptimize(
        soc=None, soccfg=None, path="q4", outerFolder=str(tmp_path), cfg=cfg,
        freqs_mhz=np.array([2534.0]), gains=np.array([2800]),
        pulse_type="X180", num_pi=1, save=False)
    assert exp.pulse_type == "X90"
    assert exp.num_pi_pulses == 3
    assert exp.drive_pulses == 6
    assert exp.cfg["n_pulses"] == 6
