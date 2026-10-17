"""Hardware-free tests: UndrivenSingleShot's slimmed h5 layout (F74).

Each 1e6-shot pass used to write ~16 full-length float64 arrays (128 MB), most of them copies
or regenerable axes. save_data now writes the raw traces as float32, 0/1 labels as uint8, an
averaged trace equal to its raw twin (shot_average == 1) and the ModifiedRamsey aliases as
h5py SoftLinks, and drops the per-read index/time axes (regenerated from the saved scalars).
The in-memory self.data, which display() reads, is not touched.
See docs/experiments/undriven_single_shot.md#outputs.

    python -m pytest tests/test_undriven_save_layout.py
"""

import os
import types

import h5py
import numpy as np
import pytest

import qicklab.experiments.undriven_single_shot as us_mod
import qicklab.hardware.yoko as yoko_mod

N_SHOTS = 2002  # not a multiple of 4, so shot_average=4 drops trailing shots
PERIOD_US = 10.0
AXES = ("shot_index", "shot_time_us", "ts_index", "ts_time_us")


def _telegraph_shots(cfg):
    rng = np.random.default_rng(7 + int(1000 * cfg.get("current_voltage", 0.0)))
    flips = rng.random(N_SHOTS) < 0.02
    state = np.cumsum(flips) % 2
    i = state * 1.0 + rng.normal(0.0, 0.1, N_SHOTS)
    q = rng.normal(0.0, 0.1, N_SHOTS)
    return [[i], [i + 0.5]], [[q], [q - 0.5]]  # two reads


class _Prog:
    def __init__(self, soccfg, cfg):
        self.cfg = cfg

    def acquire(self, soc, load_pulses=True):
        return _telegraph_shots(self.cfg)

    def scheduled_rep_period_us(self):
        return PERIOD_US


class _FakeYoko:
    def __init__(self):
        self.level = 0.0

    def query(self, cmd):
        return f"{self.level}"

    def write(self, cmd):
        self.level = float(cmd.split()[1])


@pytest.fixture(autouse=True)
def _fakes(monkeypatch):
    monkeypatch.setattr(us_mod, "UndrivenSingleShotProgram", _Prog)
    monkeypatch.setattr(yoko_mod.time, "sleep", lambda s: None)


def _run(tmp_path, **cfg):
    cfg = {"ts_bin_sizes": (1, 2), **cfg}
    exp = us_mod.UndrivenSingleShot(
        path="Undriven",
        outerFolder=str(tmp_path) + "/",
        cfg=cfg,
        soc=types.SimpleNamespace(stop_tproc=lambda: None),
        yoko=_FakeYoko() if cfg.get("charge_sweep") else None,
    )
    data = exp.acquire()
    snapshot = {k: np.array(v, copy=True) for k, v in data["data"].items()}
    exp.save_data()
    return exp, data["data"], snapshot


def _link(f, key):
    link = f.get(key, getlink=True)
    return link.path if isinstance(link, h5py.SoftLink) else None


def _check_in_memory_untouched(d, snapshot):
    assert set(d) == set(snapshot)
    for k, v in snapshot.items():
        assert np.asarray(d[k]).dtype == v.dtype, k
        np.testing.assert_array_equal(np.asarray(d[k]), v, err_msg=k)


def _check_read(f, d, prefix, tag, n_avg):
    p = prefix
    for name in ("i_raw", "q_raw", "projection_raw"):
        ds = f[p + name + tag]
        assert ds.dtype == np.float32 and _link(f, p + name + tag) is None
        np.testing.assert_allclose(ds[()], d[p + name + tag], rtol=1e-6, atol=1e-6)
    for name in ("labels", "ts_states"):
        assert f[p + name + tag].dtype == np.uint8
        np.testing.assert_array_equal(f[p + name + tag][()], d[p + name + tag])
    for avg, raw in (("i", "i_raw"), ("q", "q_raw"), ("projection", "projection_raw")):
        if n_avg == 1:
            assert _link(f, p + avg + tag) == "/" + p + raw + tag
        else:
            assert _link(f, p + avg + tag) is None and f[p + avg + tag].dtype == np.float32
        np.testing.assert_allclose(f[p + avg + tag][()], d[p + avg + tag], rtol=1e-6, atol=1e-6)
    for name in AXES:
        assert p + name + tag not in f
    # the dropped axes regenerate exactly from the saved scalars
    period = f[p + "scheduled_rep_period_us"][()]
    n = int(f[p + "shot_average"][()])
    n_raw = f[p + "i_raw" + tag].shape[0]
    shot_index = np.arange(n_raw, dtype=float)
    ts_index = np.arange(n_raw // n) * n + (n - 1) / 2.0
    np.testing.assert_array_equal(shot_index, d[p + "shot_index" + tag])
    np.testing.assert_array_equal(shot_index * period, d[p + "shot_time_us" + tag])
    np.testing.assert_array_equal(ts_index, d[p + "ts_index" + tag])
    np.testing.assert_array_equal(ts_index * period, d[p + "ts_time_us" + tag])
    assert f[p + "timeseries_dt_us"][()] == pytest.approx(period * n)


def _expected_narrow(prefixes, n_avg):
    """The exact set of real (non-link) datasets save_data may store narrower than float64."""
    names = ["i_raw", "q_raw", "projection_raw", "labels", "ts_states"]
    if n_avg > 1:
        names += ["i", "q", "projection"]
    narrow = {p + name + tag for p in prefixes for name in names for tag in ("0", "1")}
    return narrow | {p + "shot_index" for p in prefixes}


def _check_rest_float64(f, d, expected_narrow):
    real = [k for k in f if _link(f, k) is None]
    narrow = {k for k in real if f[k].dtype != np.float64}
    assert narrow == expected_narrow
    for key in real:
        if key in narrow:
            continue
        np.testing.assert_array_equal(f[key][()], np.asarray(d[key], dtype=float), err_msg=key)


@pytest.mark.parametrize("n_avg", [1, 4])
def test_single_bias_layout(tmp_path, n_avg):
    exp, d, snapshot = _run(tmp_path, shot_average=n_avg)
    _check_in_memory_untouched(d, snapshot)
    with h5py.File(exp.fname, "r") as f:
        for tag in ("0", "1"):
            _check_read(f, d, "", tag, n_avg)
        # ModifiedRamsey aliases: links to the first read, one real index/time copy
        assert _link(f, "shots_i") == "/i_raw0" and _link(f, "shots_q") == "/q_raw0"
        np.testing.assert_allclose(f["shots_i"][()], d["shots_i"], rtol=1e-6, atol=1e-6)
        assert f["shot_index"].dtype == np.uint32
        np.testing.assert_array_equal(f["shot_index"][()], np.arange(N_SHOTS))
        assert f["shot_time_us"].dtype == np.float64
        np.testing.assert_array_equal(f["shot_time_us"][()], d["shot_time_us"])
        _check_rest_float64(f, d, _expected_narrow([""], n_avg))
        # every in-memory key is on disk except the regenerable per-read axes
        dropped = {name + tag for name in AXES for tag in ("0", "1")}
        assert set(f) == set(d) - dropped
        stored = sum(f[k].id.get_storage_size() for k in f if _link(f, k) is None)
    in_memory = sum(np.asarray(v, dtype=float).nbytes for v in d.values())
    assert stored < (0.25 if n_avg == 1 else 0.35) * in_memory


def test_charge_sweep_layout(tmp_path):
    cfg = dict(charge_sweep=True, voltage_start=0.0, voltage_end=0.002, voltage_step=0.001)
    exp, d, snapshot = _run(tmp_path, **cfg)
    _check_in_memory_untouched(d, snapshot)
    with h5py.File(exp.fname, "r") as f:
        for k in (0, 1):
            p = f"V{k}_"
            for tag in ("0", "1"):
                _check_read(f, d, p, tag, 1)
            assert _link(f, p + "shots_i") == f"/{p}i_raw0"
            assert _link(f, p + "shots_q") == f"/{p}q_raw0"
            assert f[p + "shot_index"].dtype == np.uint32
        for alias, target in (
            ("shots_i", "/V0_i_raw0"),
            ("shots_q", "/V0_q_raw0"),
            ("shot_index", "/V0_shot_index"),
            ("shot_time_us", "/V0_shot_time_us"),
        ):
            assert _link(f, alias) == target, alias
        np.testing.assert_array_equal(f["shot_time_us"][()], d["shot_time_us"])
        np.testing.assert_allclose(f["sweep_voltages"][()], [0.0, 0.001])
        _check_rest_float64(f, d, _expected_narrow(["V0_", "V1_"], 1))


@pytest.mark.parametrize("bad", [None, [1, [2, 3]], np.array([object()], dtype=object)])
def test_bad_key_writes_nothing(tmp_path, bad):
    """F77: the override converts every key before opening the file, like the base save_data.

    A bad key in the middle of the payload used to leave the keys before it written and drop
    the keys after it; now save_data raises TypeError naming the key and the h5 is not touched.
    """
    exp, d, _ = _run(tmp_path)
    with h5py.File(exp.fname, "r") as f:
        before = {k: f[k].dtype for k in f if _link(f, k) is None}
    keys = list(d)
    mid = len(keys) // 2
    payload = {k: d[k] for k in keys[:mid]}
    payload["bad_key"] = bad
    payload.update({k: d[k] for k in keys[mid:]})
    payload["late_key"] = np.arange(3.0)  # would be written last if the loop kept going
    with pytest.raises(TypeError, match="bad_key"):
        exp.save_data({"data": payload})
    with h5py.File(exp.fname, "r") as f:
        assert "bad_key" not in f and "late_key" not in f
        assert {k: f[k].dtype for k in f if _link(f, k) is None} == before
    # a fresh experiment whose first save fails creates no h5 at all
    exp2 = us_mod.UndrivenSingleShot(
        path="Undriven2",
        outerFolder=str(tmp_path) + "/",
        cfg={"ts_bin_sizes": (1, 2)},
        soc=types.SimpleNamespace(stop_tproc=lambda: None),
    )
    with pytest.raises(TypeError, match="bad_key"):
        exp2.save_data({"data": payload})
    assert not os.path.exists(exp2.fname)
