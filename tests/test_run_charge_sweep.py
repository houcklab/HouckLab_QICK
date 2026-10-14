"""Hardware-free tests for the yoko_fixed metadata of the charge sweeps (F28).

With ``ctx.yoko_fixed`` the bias is held, so run_charge_sweep / run_charge_transmission_sweep
repeat the slice in time: every slice must record the held (read-back) level as
current_voltage plus repeat_index / acq_time / nominal_voltage, the yoko must not be written,
and the npz must carry the repeat axis instead of voltage_pts. Without yoko_fixed the slices
keep the grid value and the npz keeps voltage_pts. See docs/experiments/charge_sweep.md and
docs/experiments/charge_transmission_sweep.md.

    python -m pytest tests/test_run_charge_sweep.py
"""

import matplotlib

matplotlib.use("Agg")

from datetime import datetime

import numpy as np
import pytest

import qicklab.runs.charge_sweep as cs
from qicklab.core.context import Context

HELD_V = 0.0123
GRID = {"voltage_start": 0.0, "voltage_end": 0.03, "voltage_step": 0.01}  # 3 points


class _Yoko:
    def __init__(self, level):
        self.level = level
        self.log = []

    def write(self, cmd):
        self.log.append(("W", cmd))

    def query(self, cmd):
        self.log.append(("Q", cmd))
        return repr(self.level) if cmd.strip() == ":SOUR:LEV?" else "0"


class _Ctx:
    working_config = Context.working_config

    def __init__(self, yoko_fixed):
        self.config = {"pulse_freq": 7095.0, "reps": 10, "cavity_LO": 0.0, **GRID}
        self.yoko = _Yoko(HELD_V)
        self.yoko_fixed = yoko_fixed
        self.cavity_min = True
        self.outerFolder = "unused/"
        self.soc = self.soccfg = None


def _fake_experiment(tmp_path, data):
    """A stand-in experiment class: records each slice's cfg snapshot, returns `data()`."""

    class _Fake:
        slices = []

        def __init__(self, path=None, cfg=None, soc=None, soccfg=None, outerFolder=None):
            self.cfg = cfg
            n = len(type(self).slices)
            self.fname = str(tmp_path / f"slice{n}.h5")
            self.iname = str(tmp_path / f"slice{n}.png")
            type(self).slices.append(dict(cfg))

        def acquire(self):
            return {"config": self.cfg, "data": data()}

        def display(self, data=None, **kw):
            pass

        def save_data(self, data=None):
            pass

        def save_config(self):
            pass

    return _Fake


def _spec_data():
    x = np.linspace(-1.0, 1.0, 41)
    amp = np.exp(-(x**2) / 0.01)
    return {"x_pts": x, "avgi": [[amp]], "avgq": [[0.1 * amp]]}


def _trans_data():
    f = np.linspace(7090.0, 7100.0, 21)
    s21 = 1 - 0.8 / (1 + 4j * (f - 7095.0))
    return {"fpts": f, "results": [[[s21.real, s21.imag]]]}


SPEC_PARAMS = {
    "reps": 1,
    "rounds": 1,
    "Gauss": False,
    "min_sep_MHz": 0.2,
    "fit_window_mhz": 0.5,
    "prominent_ratio": 0.1,
}


def _run(kind, yoko_fixed, tmp_path, monkeypatch):
    ramps = []
    monkeypatch.setattr(cs, "ramp_to", lambda yoko, v: ramps.append(float(v)))
    monkeypatch.setattr(cs.plt, "pause", lambda *a, **k: None)
    monkeypatch.setattr(cs.plt, "show", lambda *a, **k: None)
    ctx = _Ctx(yoko_fixed)
    if kind == "spec":
        fake = _fake_experiment(tmp_path, _spec_data)
        monkeypatch.setattr(cs, "QubitSpecSliceFF", fake)
        cs.run_charge_sweep(ctx, SPEC_PARAMS)
        npz = np.load(tmp_path / "slice2_ChargeSweepHeatmap.npz")
    else:
        fake = _fake_experiment(tmp_path, _trans_data)
        monkeypatch.setattr(cs, "CavitySpecFF", fake)
        cs.run_charge_transmission_sweep(ctx, {})
        npz = np.load(tmp_path / "slice2_ChargeTransmissionHeatmap.npz")
    return ctx, fake.slices, npz, ramps


@pytest.mark.parametrize("kind", ["spec", "trans"])
def test_yoko_fixed_records_held_bias_and_repeat_axis(kind, tmp_path, monkeypatch):
    ctx, slices, npz, ramps = _run(kind, True, tmp_path, monkeypatch)
    grid = np.arange(GRID["voltage_start"], GRID["voltage_end"], GRID["voltage_step"])

    assert ramps == []  # the bias is never moved (nor restored)
    assert [c for c in ctx.yoko.log if c[0] == "W"] == []
    assert ctx.yoko.log.count(("Q", ":SOUR:LEV?")) == 1  # read back once, before the loop

    assert len(slices) == len(grid)
    for i, cfg in enumerate(slices):
        assert cfg["current_voltage"] == HELD_V  # the held level, not the grid value
        assert cfg["nominal_voltage"] == pytest.approx(grid[i])
        assert cfg["repeat_index"] == i
        datetime.fromisoformat(cfg["acq_time"])  # wall-clock ISO string
    assert "repeat_index" not in ctx.config  # slice cfgs are working copies

    assert "voltage_pts" not in npz.files
    assert bool(npz["yoko_fixed"]) is True
    np.testing.assert_allclose(npz["nominal_voltage_pts"], grid)
    np.testing.assert_array_equal(npz["repeat_index"], np.arange(len(grid)))
    assert list(npz["acq_time"]) == [c["acq_time"] for c in slices]
    assert npz["elapsed_s"][0] == 0.0 and np.all(np.diff(npz["elapsed_s"]) >= 0)
    assert float(npz["held_voltage"]) == HELD_V


@pytest.mark.parametrize("kind", ["spec", "trans"])
def test_swept_bias_keeps_grid_metadata(kind, tmp_path, monkeypatch):
    ctx, slices, npz, ramps = _run(kind, False, tmp_path, monkeypatch)
    grid = np.arange(GRID["voltage_start"], GRID["voltage_end"], GRID["voltage_step"])

    expected_ramps = list(grid) + ([HELD_V] if kind == "trans" else [])  # trans restores
    np.testing.assert_allclose(ramps, expected_ramps)
    for i, cfg in enumerate(slices):
        assert cfg["current_voltage"] == pytest.approx(grid[i])
        for key in ("nominal_voltage", "repeat_index", "acq_time"):
            assert key not in cfg
    # no extra read-back when sweeping (the spec sweep never queries the yoko)
    assert ctx.yoko.log.count(("Q", ":SOUR:LEV?")) == (1 if kind == "trans" else 0)

    np.testing.assert_allclose(npz["voltage_pts"], grid)
    assert bool(npz["yoko_fixed"]) is False
    for key in ("nominal_voltage_pts", "repeat_index", "acq_time", "held_voltage"):
        assert key not in npz.files
