"""Hardware-free tests: aborted multi-program acquisitions keep their completed points (F48).

UndrivenSingleShot's charge sweep and T1_SS start one program per point and used to write
nothing until every point was done, so an error or Ctrl-C at point k lost points 0..k-1. Now
the completed points are saved (h5 + json) before the error is re-raised, marked with
`sweep_completed` / `points_completed` and `aborted`, and each program start goes through
`acquire_with_retry`. See docs/experiments/undriven_single_shot.md and t1_single_shot.md.

    python -m pytest tests/test_partial_save.py
"""

import json
import types

import h5py
import numpy as np
import pytest

import qicklab.core.acquisition as acquisition
import qicklab.experiments.t1_single_shot as t1ss_mod
import qicklab.experiments.undriven_single_shot as us_mod
import qicklab.hardware.yoko as yoko_mod

STALE = "could not broadcast input array from shape (26,2) into shape (20,2)"
# Start level off the sweep grid (0, 1, 2, 3 mV), so `yoko.level == START_V` holds only if the
# finally ramped the bias back, not because the abort happened to park it at the start level.
START_V = 0.0075


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(yoko_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(acquisition.time, "sleep", lambda s: None)
    monkeypatch.setattr(us_mod.time, "sleep", lambda s: None)


class _FakeYoko:
    def __init__(self, level=0.0):
        self.level = level
        self.levels = []

    def query(self, cmd):
        assert cmd == ":SOUR:LEV?"
        return f"{self.level}"

    def write(self, cmd):
        self.level = float(cmd.split()[1])
        self.levels.append(self.level)


def _fake_soc():
    soc = types.SimpleNamespace(stop_calls=0)

    def stop_tproc():
        soc.stop_calls += 1

    soc.stop_tproc = stop_tproc
    return soc


def _program_factory(plan, shots_fn):
    """Fake program class: the n-th acquire() follows plan[n] ('ok', or an exception to raise)."""
    calls = {"n": 0}

    class _Prog:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True):
            step = plan[calls["n"]] if calls["n"] < len(plan) else "ok"
            calls["n"] += 1
            if step != "ok":
                raise step
            return shots_fn(self.cfg)

        def scheduled_rep_period_us(self):
            return 10.0

    return _Prog, calls


def _undriven_shots(cfg):
    rng = np.random.default_rng(int(1000 * cfg.get("current_voltage", 0.0)) + 1)
    n = 400
    return [[rng.normal(1.0, 0.1, n)]], [[rng.normal(0.0, 0.1, n)]]


def _undriven(tmp_path, yoko):
    cfg = {
        "charge_sweep": True,
        "voltage_start": 0.0,
        "voltage_end": 0.004,
        "voltage_step": 0.001,
        "ts_bin_sizes": (1, 2),
    }
    return us_mod.UndrivenSingleShot(
        path="Undriven", outerFolder=str(tmp_path) + "/", cfg=cfg, soc=_fake_soc(), yoko=yoko
    )


@pytest.mark.parametrize("abort", [ValueError("readout broke"), KeyboardInterrupt()])
def test_undriven_sweep_abort_saves_completed_biases(tmp_path, monkeypatch, abort):
    # bias 0: one stale-counter failure, retried; bias 1 ok; bias 2 aborts
    prog_cls, calls = _program_factory([ValueError(STALE), "ok", "ok", abort], _undriven_shots)
    monkeypatch.setattr(us_mod, "UndrivenSingleShotProgram", prog_cls)
    yoko = _FakeYoko(level=START_V)
    exp = _undriven(tmp_path, yoko)

    with pytest.raises(type(abort)) as excinfo:
        exp.acquire()

    assert excinfo.value is abort
    assert calls["n"] == 4  # 2 tries at bias 0, 1 at bias 1, the abort at bias 2
    assert exp.soc.stop_calls == 1
    assert 0.002 in yoko.levels  # the sweep did reach bias 2
    assert yoko.level == pytest.approx(START_V)  # back at the starting level

    with h5py.File(exp.fname, "r") as f:
        keys = set(f)
        assert f["sweep_completed"][()] == 2
        np.testing.assert_allclose(f["sweep_voltages"][()], [0.0, 0.001])
        assert f["sweep_n_blobs0"].shape == (2,)
        np.testing.assert_array_equal(f["read_indices"][()], [0])
        np.testing.assert_array_equal(f["shots_i"][()], f["V0_shots_i"][()])
        saved_cfg = json.loads(f.attrs["config"])
    assert any(k.startswith("V0_") for k in keys) and any(k.startswith("V1_") for k in keys)
    assert not any(k.startswith("V2_") for k in keys)
    with open(exp.cname) as fid:
        cfg = json.load(fid)
    for c in (cfg, saved_cfg):
        assert c["sweep_completed"] == 2
        assert c["aborted"] == repr(abort)


def test_undriven_sweep_abort_at_first_bias_writes_nothing(tmp_path, monkeypatch):
    prog_cls, _ = _program_factory([ValueError("readout broke")], _undriven_shots)
    monkeypatch.setattr(us_mod, "UndrivenSingleShotProgram", prog_cls)
    yoko = _FakeYoko(level=START_V)
    exp = _undriven(tmp_path, yoko)
    with pytest.raises(ValueError, match="readout broke"):
        exp.acquire()
    assert 0.0 in yoko.levels  # moved to bias 0 before the abort
    assert yoko.level == pytest.approx(START_V)
    assert "sweep_completed" not in exp.cfg
    with pytest.raises(FileNotFoundError):
        open(exp.cname)


def test_undriven_sweep_complete_is_unmarked(tmp_path, monkeypatch):
    prog_cls, _ = _program_factory([], _undriven_shots)
    monkeypatch.setattr(us_mod, "UndrivenSingleShotProgram", prog_cls)
    yoko = _FakeYoko(level=START_V)
    exp = _undriven(tmp_path, yoko)
    d = exp.acquire()["data"]
    assert yoko.level == pytest.approx(START_V)
    assert "sweep_completed" not in d and "sweep_completed" not in exp.cfg
    np.testing.assert_allclose(d["sweep_voltages"], [0.0, 0.001, 0.002, 0.003])
    assert d["sweep_n_blobs0"].shape == (4,)
    np.testing.assert_array_equal(d["read_indices"], [0])
    assert "V3_shots_i" in d


class _RaisingLookup(dict):
    def __init__(self, err):
        super().__init__()
        self.err = err

    def __getitem__(self, key):
        raise self.err


def test_undriven_abort_mid_summary_drops_the_unfinished_bias(tmp_path, monkeypatch):
    # The abort comes after bias 2 has written V2_* into `merged` and its cloud scalars into
    # the summary lists, but before its timeseries scalars: the save must still cover only
    # biases 0 and 1 (the n_done filter on merged and the [:n_done] slice on the summary).
    prog_cls, _ = _program_factory([], _undriven_shots)
    monkeypatch.setattr(us_mod, "UndrivenSingleShotProgram", prog_cls)

    full = _undriven(tmp_path / "full", _FakeYoko(level=START_V))
    full_keys = set(full.acquire()["data"])

    abort = KeyboardInterrupt()
    yoko = _FakeYoko(level=START_V)
    exp = _undriven(tmp_path / "partial", yoko)
    orig = exp._acquire_at_bias
    seen = {"n": 0}

    def acquire_at_bias():
        out = orig()
        seen["n"] += 1
        if seen["n"] == 3:  # bias 2: its data is complete, the summary loop then aborts
            exp.timeseries = _RaisingLookup(abort)
        return out

    monkeypatch.setattr(exp, "_acquire_at_bias", acquire_at_bias)
    with pytest.raises(KeyboardInterrupt) as excinfo:
        exp.acquire()
    assert excinfo.value is abort
    assert yoko.level == pytest.approx(START_V)

    expected = {k for k in full_keys if not k.startswith(("V2_", "V3_"))} | {"sweep_completed"}
    assert set(exp.data["data"]) == expected
    with h5py.File(exp.fname, "r") as f:
        assert set(f) == expected
        assert f["sweep_completed"][()] == 2
        for key in (k for k in f if k.startswith("sweep_") and k != "sweep_completed"):
            assert f[key].shape == (2,), key
        np.testing.assert_array_equal(f["read_indices"][()], [0])


def _disk_full(*args, **kwargs):
    raise OSError("disk full")


@pytest.mark.parametrize("abort", [ValueError("readout broke"), KeyboardInterrupt()])
@pytest.mark.parametrize("broken", ["save_data", "save_config"])
def test_undriven_partial_save_failure_keeps_original_error(tmp_path, monkeypatch, abort, broken):
    # a failure while saving the completed biases must not replace the abort that triggered
    # the save, nor skip the ramp back to the starting level
    prog_cls, _ = _program_factory(["ok", "ok", abort], _undriven_shots)
    monkeypatch.setattr(us_mod, "UndrivenSingleShotProgram", prog_cls)
    yoko = _FakeYoko(level=START_V)
    exp = _undriven(tmp_path, yoko)
    monkeypatch.setattr(exp, broken, _disk_full)

    with pytest.raises(type(abort)) as excinfo:
        exp.acquire()

    assert excinfo.value is abort
    assert yoko.level == pytest.approx(START_V)


def _t1_shots(cfg):
    n = cfg["reps"]
    i = np.full((1, n), 2.0 if cfg["variable_wait"] < 25 else 0.0)
    return i, np.zeros((1, n))


def _t1(tmp_path):
    cfg = {"start": 0, "step": 10, "expts": 6, "reps": 20}
    return t1ss_mod.T1_SS(path="T1SS", outerFolder=str(tmp_path) + "/", cfg=cfg, soc=_fake_soc())


@pytest.mark.parametrize("abort", [ValueError("readout broke"), KeyboardInterrupt()])
def test_t1ss_abort_saves_completed_points(tmp_path, monkeypatch, abort):
    # wait 1: one stale-counter failure, retried; abort at wait index 4
    plan = ["ok", ValueError(STALE), "ok", "ok", "ok", abort]
    prog_cls, calls = _program_factory(plan, _t1_shots)
    monkeypatch.setattr(t1ss_mod, "T1SingleShotProgram", prog_cls)
    exp = _t1(tmp_path)

    with pytest.raises(type(abort)) as excinfo:
        exp.acquire(threshold=1.0, angle=0.0)

    assert excinfo.value is abort
    assert calls["n"] == 6
    assert exp.soc.stop_calls == 1
    with h5py.File(exp.fname, "r") as f:
        assert f["points_completed"][()] == 4
        np.testing.assert_allclose(f["wait_times"][()], [0, 10, 20, 30])
        np.testing.assert_allclose(f["Exp_values"][()], [1.0, 1.0, 1.0, 0.0])
        assert f["RotatedIQ"].shape[0] == 4
        assert f["threshold"][()] == 1.0
    with open(exp.cname) as fid:
        cfg = json.load(fid)
    assert cfg["points_completed"] == 4
    assert cfg["aborted"] == repr(abort)


def test_t1ss_complete_is_unmarked(tmp_path, monkeypatch):
    prog_cls, _ = _program_factory([], _t1_shots)
    monkeypatch.setattr(t1ss_mod, "T1SingleShotProgram", prog_cls)
    exp = _t1(tmp_path)
    d = exp.acquire(threshold=1.0, angle=0.0)["data"]
    assert "points_completed" not in d and "points_completed" not in exp.cfg
    np.testing.assert_allclose(d["Exp_values"], [1, 1, 1, 0, 0, 0])


@pytest.mark.parametrize("abort", [ValueError("readout broke"), KeyboardInterrupt()])
@pytest.mark.parametrize("broken", ["save_data", "save_config"])
def test_t1ss_partial_save_failure_keeps_original_error(tmp_path, monkeypatch, abort, broken):
    prog_cls, calls = _program_factory(["ok", "ok", abort], _t1_shots)
    monkeypatch.setattr(t1ss_mod, "T1SingleShotProgram", prog_cls)
    exp = _t1(tmp_path)
    monkeypatch.setattr(exp, broken, _disk_full)

    with pytest.raises(type(abort)) as excinfo:
        exp.acquire(threshold=1.0, angle=0.0)

    assert excinfo.value is abort
    assert calls["n"] == 3
