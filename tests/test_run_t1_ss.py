"""Hardware-free tests for qicklab.runs.single_shot.run_t1_ss (calibration branch, F11).

The T1_SS calibration must always be one pi pulse at the pi gain, whatever the single_shot
group says, and a thermal-mode or non-finite calibration (or user angle/threshold) must raise
instead of producing a T1 curve that silently reads 0. See docs/experiments/t1_single_shot.md.

    python -m pytest tests/test_run_t1_ss.py
"""

import types

import numpy as np
import pytest

import qicklab.runs.single_shot as ss_runs
from qicklab.core.context import Context

PI_GAIN = 4200
SPEC_GAIN = 900


class _FakeSS:
    """Stands in for SingleShotProgramFFMUX: records the cfg, returns canned calibration data."""

    instances = []
    result = {}
    fid = [0.9]

    def __init__(self, path=None, outerFolder=None, cfg=None, soc=None, soccfg=None):
        self.path, self.cfg = path, cfg
        self.fid = list(type(self).fid)
        type(self).instances.append(self)

    def acquire(self):
        return {"config": self.cfg, "data": dict(type(self).result)}


class _FakeT1:
    instances = []

    def __init__(self, path=None, cfg=None, soc=None, soccfg=None, outerFolder=None):
        self.cfg = cfg
        type(self).instances.append(self)

    def acquire(self, angle=None, threshold=None):
        self.angle, self.threshold = angle, threshold
        return {"config": self.cfg, "data": {}}


class _Ctx:
    """Minimal Context: just the attributes run_t1_ss uses."""

    working_config = Context.working_config

    def __init__(self):
        # regime-A-like: the config's qubit_gain is NOT the pi gain
        self.config = {"qubit_gain": SPEC_GAIN, "reps": 10}
        self.qubit_gain = PI_GAIN
        self.outerFolder = "unused/"
        self.soccfg = None
        self.soc = types.SimpleNamespace(reset_gens=lambda: None)


T1SS = {
    "T1_step": 80,
    "T1_expts": 3,
    "reps": 100,
    "relax_delay": 50,
    "calibrate_SS": True,
    "angle": 0,
    "threshold": 0,
    "repetitions": 1,
}


@pytest.fixture
def fakes(monkeypatch):
    _FakeSS.instances, _FakeT1.instances = [], []
    _FakeSS.result = {"angle": [0.12], "threshold": [1.3], "thermal_mode": False}
    _FakeSS.fid = [0.9]
    monkeypatch.setattr(ss_runs, "SingleShotProgramFFMUX", _FakeSS)
    monkeypatch.setattr(ss_runs, "T1_SS", _FakeT1)
    monkeypatch.setattr(ss_runs, "finish", lambda *a, **k: None)
    monkeypatch.setattr(ss_runs.time, "sleep", lambda s: None)
    return _FakeSS, _FakeT1


@pytest.mark.parametrize(
    "ss_params",
    [
        {"number_of_pulses": 2, "pi2_SS": True},  # left over from a pi/2 check
        {"number_of_pulses": 0, "pi2_SS": False},  # thermal-mode setting
        {"number_of_pulses": 1, "pi2_SS": False},
    ],
)
def test_calibration_is_one_pi_pulse_at_pi_gain(fakes, ss_params):
    fss, ft1 = fakes
    ss_runs.run_t1_ss(_Ctx(), dict(T1SS), ss_params)
    (cal,) = fss.instances
    assert cal.path == "SingleShot"
    assert cal.cfg["number_of_pulses"] == 1
    assert cal.cfg["qubit_gain"] == PI_GAIN
    (t1,) = ft1.instances
    assert (t1.angle, t1.threshold) == (0.12, 1.3)
    # the calibration knobs do not leak into the T1 cfg
    assert "number_of_pulses" not in t1.cfg
    assert t1.cfg["qubit_gain"] == SPEC_GAIN
    assert t1.cfg["pi_gain"] == PI_GAIN


def test_thermal_mode_calibration_raises(fakes):
    fss, ft1 = fakes
    fss.result = {"angle": [0.3], "threshold": [2.0], "thermal_mode": True}
    with pytest.raises(ValueError, match="thermal mode"):
        ss_runs.run_t1_ss(_Ctx(), dict(T1SS), {"number_of_pulses": 1, "pi2_SS": False})
    assert ft1.instances == []


@pytest.mark.parametrize(
    "angle, threshold", [(0.1, np.nan), (np.nan, 1.0), (0.1, np.inf), (0.1, None)]
)
def test_non_finite_calibration_raises(fakes, angle, threshold):
    fss, ft1 = fakes
    fss.result = {"angle": [angle], "threshold": [threshold], "thermal_mode": False}
    with pytest.raises(ValueError, match="not a finite number"):
        ss_runs.run_t1_ss(_Ctx(), dict(T1SS), {"number_of_pulses": 1, "pi2_SS": False})
    assert ft1.instances == []


@pytest.mark.parametrize("angle, threshold", [(0, None), (None, 1.0), (0, float("nan"))])
def test_non_finite_user_discriminator_raises(fakes, angle, threshold):
    fss, ft1 = fakes
    params = dict(T1SS, calibrate_SS=False, angle=angle, threshold=threshold)
    with pytest.raises(ValueError, match="T1SS_params"):
        ss_runs.run_t1_ss(_Ctx(), params, {"number_of_pulses": 1, "pi2_SS": False})
    assert fss.instances == [] and ft1.instances == []


def test_user_discriminator_used_without_calibration(fakes):
    fss, ft1 = fakes
    params = dict(T1SS, calibrate_SS=False, angle=0.25, threshold=-0.5)
    ss_runs.run_t1_ss(_Ctx(), params, {"number_of_pulses": 2, "pi2_SS": True})
    assert fss.instances == []
    (t1,) = ft1.instances
    assert (t1.angle, t1.threshold) == (0.25, -0.5)
    assert "number_of_pulses" not in t1.cfg


def test_low_contrast_warns_but_runs(fakes, capsys):
    fss, ft1 = fakes
    fss.fid = [0.05]
    ss_runs.run_t1_ss(_Ctx(), dict(T1SS), {"number_of_pulses": 1, "pi2_SS": False})
    assert "WARNING calibration contrast 0.050" in capsys.readouterr().out
    assert len(ft1.instances) == 1


def test_good_contrast_no_warning(fakes, capsys):
    ss_runs.run_t1_ss(_Ctx(), dict(T1SS), {"number_of_pulses": 1, "pi2_SS": False})
    assert "WARNING" not in capsys.readouterr().out
