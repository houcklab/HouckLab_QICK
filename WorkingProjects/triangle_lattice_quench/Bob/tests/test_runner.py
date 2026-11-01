"""Dry run, saving, and the hardware entry points (without hardware)."""
import json

import numpy as np
import pytest

from Bob.config.settings import SweepAxis
from Bob.config.snapshot import make_snapshot
from Bob.core.params import Sweep
from Bob.runner.experiment import BobExperiment
from Bob.runner.save import save_run


def test_dry_run_compiles_every_point(basic_seq, station, calib):
    basic_seq.segments[0].set_field("duration_us", Sweep("t"))
    basic_seq.settings.sweeps.append(SweepAxis("t", 0.2, 1.0, 5, "us"))
    out = BobExperiment(basic_seq, station, calib).dry_run()
    assert out["n"] == 5 and out["n_ok"] == 5
    assert out["points"][0]["samples"] < out["points"][-1]["samples"]


def test_dry_run_reports_the_points_that_fail(basic_seq, station, calib):
    basic_seq.segments[0].set_field("duration_us", Sweep("t"))
    basic_seq.settings.sweeps.append(SweepAxis("t", 0.05, 1.0, 5, "us"))   # first point too short for the pulse
    out = BobExperiment(basic_seq, station, calib).dry_run()
    bad = [p for p in out["points"] if not p["ok"]]
    assert bad and bad[0]["index"] == 0 and "past the end" in bad[0]["errors"][0]


def test_run_without_hardware_says_so(basic_seq, station, calib):
    with pytest.raises(RuntimeError, match="not connected"):
        BobExperiment(basic_seq, station, calib).run()


def test_save_run_writes_data_snapshot_and_sequence(basic_seq, station, calib, tmp_path):
    h5py = pytest.importorskip("h5py")
    snap = make_snapshot(basic_seq, station, calib)
    path = save_run(tmp_path, "test", {"I": np.zeros((1, 3)), "t": np.arange(3)}, snap, basic_seq.to_dict())
    with h5py.File(path, "r") as f:
        assert f["I"].shape == (1, 3)
        assert json.loads(f.attrs["bob_sequence"])["blocks"]
    stem = str(path)[: -len("_data.h5")]
    assert json.loads(open(stem + "_bob_snapshot.json", encoding="utf-8").read())["calibration"]["sha256"] == calib.sha256
    assert json.loads(open(stem + "_bob_sequence.json", encoding="utf-8").read())["bob_version"] == 1


def test_bob_program_imports_without_hardware():
    pytest.importorskip("qick")
    from Bob.hardware.bob_program import BobProgram
    assert hasattr(BobProgram, "_initialize") and hasattr(BobProgram, "_body")


def test_nothing_connects_or_reads_disk_at_import():
    """Importing any module has no side effects such as connecting or reading lab files."""
    import importlib
    import pkgutil
    import Bob
    for m in pkgutil.walk_packages(Bob.__path__, "Bob."):
        if ".tests" in m.name or ".Bob_GUI" in m.name:
            continue
        importlib.import_module(m.name)
