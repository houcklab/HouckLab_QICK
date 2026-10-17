"""Hardware-free tests for the base h5/json writers in qicklab.core.experiment (F77).

save_data converts every key before writing (one bad key writes nothing), keeps numeric and
bool data float64, stores complex as complex128 and str as UTF-8 strings, and replaces a key
on re-save; NumpyJSONEncoder handles np.bool_ and complex without truncating the .json;
experiments started in the same second get "_1", "_2" file names instead of sharing a file.
See docs/architecture.md#h5-and-json-writing.

    python -m pytest tests/test_save_formats.py
"""

import datetime as _dt
import json
import os
import types

import h5py
import numpy as np
import pytest

from qicklab.core import experiment as experiment_mod
from qicklab.core.experiment import ExperimentClass, NumpyJSONEncoder, data_paths

_NOW = _dt.datetime(2026, 1, 1, 12, 0, 0)


class _FrozenDateTime(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return _NOW


@pytest.fixture
def frozen_clock(monkeypatch):
    """Every ExperimentClass built in the test starts in the same second."""
    fake = types.ModuleType("datetime")
    fake.__dict__.update(vars(_dt))
    fake.datetime = _FrozenDateTime
    monkeypatch.setattr(experiment_mod, "datetime", fake)
    monkeypatch.setattr(experiment_mod, "_CLAIMED_PATHS", set())


def _make(tmp_path, cfg=None, path="Fmt"):
    return ExperimentClass(path=path, outerFolder=str(tmp_path) + "/", cfg=cfg or {"reps": 3})


def test_numeric_bool_complex_and_str_round_trip(tmp_path):
    inst = _make(tmp_path)
    inst.save_data(
        {
            "f": [0.5, 1.5],
            "i": np.arange(3),
            "b": np.array([True, False]),
            "scalar": 7,
            "c": np.array([1 + 2j, -3j]),
            "s": "Q1",
            "s_arr": ["a", "bc"],
        }
    )
    with h5py.File(inst.fname, "r") as f:
        for key in ("f", "i", "b", "scalar"):
            assert f[key].dtype == np.float64, key  # on-disk type of every existing record
        assert f["b"][()].tolist() == [1.0, 0.0]
        assert f["scalar"][()] == 7.0
        assert f["c"].dtype == np.complex128
        np.testing.assert_array_equal(f["c"][()], [1 + 2j, -3j])
        assert f["s"].asstr()[()] == "Q1"
        assert f["s_arr"].asstr()[()].tolist() == ["a", "bc"]
        assert f["f"].maxshape == (None,)


@pytest.mark.parametrize(
    "bad", [None, np.array([1.0, None], dtype=object), b"raw", [[1.0], [1.0, 2.0]]]
)
def test_one_bad_key_writes_nothing(tmp_path, bad):
    inst = _make(tmp_path)
    with pytest.raises(TypeError, match="'bad'"):
        inst.save_data({"good": [1.0, 2.0], "bad": bad, "later": [3.0]})
    # no zero-filled half-file: the h5 was never opened
    assert not os.path.exists(inst.fname)

    with h5py.File(inst.fname, "w"):
        pass
    with pytest.raises(TypeError, match="'bad'"):
        inst.save_data({"good": [1.0, 2.0], "bad": bad})
    with h5py.File(inst.fname, "r") as f:
        assert list(f.keys()) == []


def test_resave_replaces_key(tmp_path):
    """A partial save followed by the final save (F48 abort paths) overwrites, not raises."""
    inst = _make(tmp_path)
    inst.save_data({"x": [1.0, 2.0], "partial": [1.0]})
    inst.save_data({"x": [3.0, 4.0, 5.0]})
    with h5py.File(inst.fname, "r") as f:
        assert f["x"][()].tolist() == [3.0, 4.0, 5.0]
        assert f["partial"][()].tolist() == [1.0]
    with experiment_mod.H5File(inst.fname, "a") as f:
        f.add("x", "now a string")
        assert f["x"].asstr()[()] == "now a string"


def test_encoder_handles_numpy_bool_and_complex():
    obj = {
        "k": 0,
        "flag": np.bool_(True),
        "z": np.complex128(1 + 2j),
        "z64": np.complex64(0.5 - 1j),
        "pz": 3j,
        "zarr": np.array([1 + 1j, 2 - 2j]),
        "barr": np.array([True, False]),
        "n": np.int64(4),
        "x": np.float32(0.25),
    }
    assert json.loads(json.dumps(obj, cls=NumpyJSONEncoder)) == {
        "k": 0,
        "flag": True,
        "z": [1.0, 2.0],
        "z64": [0.5, -1.0],
        "pz": [0.0, 3.0],
        "zarr": [[1.0, 1.0], [2.0, -2.0]],
        "barr": [True, False],
        "n": 4,
        "x": 0.25,
    }
    # plain float cfgs encode exactly as before (byte-identical json)
    plain = {"a": 1.5, "b": [1, 2], "c": "s", "d": np.float64(0.1)}
    assert json.dumps(plain, cls=NumpyJSONEncoder) == json.dumps({**plain, "d": 0.1})


def test_save_config_round_trips_and_never_truncates(tmp_path):
    cfg = {"reps": 3, "active": np.bool_(True), "z": np.complex128(1j)}
    inst = _make(tmp_path, cfg=cfg)
    inst.save_config()
    with open(inst.cname) as fh:
        on_disk = fh.read()
    assert json.loads(on_disk) == {"reps": 3, "active": True, "z": [0.0, 1.0]}
    with h5py.File(inst.fname, "r") as f:
        assert f.attrs["config"] == on_disk
    assert not os.path.exists(inst.cname + ".tmp")

    inst.cfg["broken"] = object()
    with pytest.raises(TypeError):
        inst.save_config()
    with open(inst.cname) as fh:
        assert fh.read() == on_disk  # previous json intact, not a truncated prefix


def test_save_config_survives_a_locked_json_and_leaves_no_tmp(tmp_path, monkeypatch):
    """A reader holding the .json open makes os.replace fail on Windows (WinError 5)."""
    monkeypatch.setattr(experiment_mod, "_REPLACE_BACKOFF_S", 0.0)
    inst = _make(tmp_path)
    inst.save_config()
    inst.cfg["reps"] = 7
    with open(inst.cname) as reader:  # held open across the re-save (partial-save paths)
        inst.save_config()
        reader.read()
    with open(inst.cname) as fh:
        assert json.loads(fh.read()) == {"reps": 7}
    assert not os.path.exists(inst.cname + ".tmp")

    # replace refused every time (any OS): retried, then written in place, .tmp removed
    calls = []

    def refuse(src, dst):
        calls.append((src, dst))
        raise PermissionError(13, "locked", dst)

    monkeypatch.setattr(experiment_mod.os, "replace", refuse)
    inst.cfg["reps"] = 9
    inst.save_config()
    assert len(calls) == experiment_mod._REPLACE_RETRIES
    with open(inst.cname) as fh:
        assert json.loads(fh.read()) == {"reps": 9}
    with h5py.File(inst.fname, "r") as f:
        assert json.loads(f.attrs["config"]) == {"reps": 9}
    assert not os.path.exists(inst.cname + ".tmp")


def test_failed_json_write_removes_the_tmp(tmp_path, monkeypatch):
    inst = _make(tmp_path)
    inst.save_config()

    def boom(src, dst):
        raise OSError(28, "No space left on device", dst)

    monkeypatch.setattr(experiment_mod.os, "replace", boom)
    with pytest.raises(OSError):
        inst.save_config()
    assert not os.path.exists(inst.cname + ".tmp")
    with open(inst.cname) as fh:
        assert json.loads(fh.read()) == {"reps": 3}  # previous json intact


def test_same_second_runs_get_distinct_files(tmp_path, frozen_clock):
    expected = data_paths(str(tmp_path) + "/", "Fmt", "data", _NOW)
    first = _make(tmp_path)
    # no collision: byte-identical to data_paths
    assert (first.fname, first.iname, first.cname, first.titlename) == expected

    # built before `first` saved anything: still distinct (claimed in this process)
    second = _make(tmp_path)
    assert second.fname == expected[0][: -len(".h5")] + "_1.h5"
    assert second.iname == expected[1][: -len(".png")] + "_1.png"
    assert second.cname == expected[2][: -len(".json")] + "_1.json"
    assert second.titlename == first.titlename

    for i, inst in enumerate((first, second)):
        inst.save_data({"x": [float(i)]})
        inst.save_config()
    with h5py.File(first.fname, "r") as f:
        assert f["x"][()].tolist() == [0.0]
    with h5py.File(second.fname, "r") as f:
        assert f["x"][()].tolist() == [1.0]

    third = _make(tmp_path)
    assert third.fname.endswith("_data_2.h5")
    # a different path in the same second is not a collision
    assert _make(tmp_path, path="Other").fname.endswith("_data.h5")


def test_files_from_another_process_are_not_overwritten(tmp_path, frozen_clock, monkeypatch):
    """T1-style runs rename fname to *_Q1.h5; their .json keeps the stem and marks it taken."""
    first = _make(tmp_path)
    first.fname = first.fname[:-3] + "_Q1.h5"
    first.save_data({"x": [1.0]})
    first.save_config()
    monkeypatch.setattr(experiment_mod, "_CLAIMED_PATHS", set())  # a fresh process
    second = _make(tmp_path)
    assert second.cname.endswith("_data_1.json")
    assert second.fname[:-3] + "_Q1.h5" != first.fname
