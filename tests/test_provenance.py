"""Hardware-free tests for the provenance record of saved files (F46).

Every ExperimentClass.save_config writes `<stem>_provenance.json` and the h5 attribute
`provenance` next to the cfg: qick/board versions, git commit, host, the session (device, data
root, readout and pulse qubit), the last landed yoko level and the start/end time. It never
touches the cfg, the save_data payload or a public attribute (the regression golden diffs all
three), never queries an instrument, never calls datetime.now() (the harness clock), and a
failure in it never blocks a save. See docs/architecture.md#provenance.

    python -m pytest tests/test_provenance.py
"""

import hashlib
import json
import os
import subprocess

import h5py
import numpy as np
import pytest

from qicklab.core import experiment as experiment_mod
from qicklab.core import io
from qicklab.core.experiment import ExperimentClass, finish
from qicklab.hardware import yoko as yoko_mod
from tests.regression.capture import FakeSocCfg

REQUIRED = (
    "provenance_version",
    "qick_version",
    "python_version",
    "hostname",
    "git_commit",
    "git_dirty",
    "soccfg_sha1",
    "soccfg_sw_version",
    "start_time",
    "end_time",
    "qubit_readout",
    "qubit_pulse",
    "device",
    "data_root",
    "bias",
    "experiment_class",
)


@pytest.fixture(autouse=True)
def fresh_provenance(monkeypatch):
    """Empty session, caches and yoko record for each test (module state, restored after)."""
    monkeypatch.setattr(io, "_SESSION", {})
    monkeypatch.setattr(io, "_SESSION_SOCCFG", [None])
    monkeypatch.setattr(io, "_STATIC", {})
    monkeypatch.setattr(io, "_SOCCFG_CACHE", [None, None])
    monkeypatch.setattr(yoko_mod, "_LAST_LEVELS", {})


class _Yoko:
    """GS200 stand-in that logs every SCPI exchange."""

    resource_name = "GPIB1::9::INSTR"

    def __init__(self, level=0.0):
        self.level = level
        self.log = []

    def write(self, cmd):
        self.log.append("W " + cmd)
        if cmd.startswith(":SOUR:LEV "):
            self.level = float(cmd.split()[1])

    def query(self, cmd):
        self.log.append("Q " + cmd)
        return repr(self.level)


def _session(soccfg):
    io.start_session(
        soccfg,
        device="TESTDEV",
        data_root="/data/TESTDEV/Q2//",
        qubit_readout=2,
        qubit_pulse=3,
        rfsoc_host="192.0.2.1",
        rfsoc_port=8888,
        rfsoc_name="myqick",
        rfsoc_timeout_s=30.0,
        yoko_addr="GPIB1::9::INSTR",
        start_voltage=0.25,
        yoko_fixed=False,
    )


def _make(tmp_path, soccfg, cfg=None):
    return ExperimentClass(
        path="Prov", outerFolder=str(tmp_path) + "/", soccfg=soccfg, cfg=cfg or {"reps": 3}
    )


def _stem(inst):
    return os.path.splitext(inst.cname)[0]


def test_save_config_writes_attr_and_sidecar_leaving_cfg_alone(tmp_path):
    soccfg = FakeSocCfg("A")
    _session(soccfg)
    yoko_mod.ramp_to(_Yoko(0.0), 0.002)
    cfg = {"reps": 3, "qubit_freq": 4185.6, "arr": np.arange(3)}
    inst = _make(tmp_path, soccfg, cfg)
    inst.save_data({"x": [1.0, 2.0]})
    public_before = {k: v for k, v in vars(inst).items() if not k.startswith("_")}
    inst.save_config()

    # cfg json and attrs["config"]: exactly the cfg, no provenance key
    with open(inst.cname) as f:
        assert json.load(f) == {"reps": 3, "qubit_freq": 4185.6, "arr": [0, 1, 2]}
    assert "provenance" not in inst.cfg
    assert {k: v for k, v in vars(inst).items() if not k.startswith("_")}.keys() == (
        public_before.keys()
    )

    with h5py.File(inst.fname, "r") as f:
        assert json.loads(f.attrs["config"]) == {"reps": 3, "qubit_freq": 4185.6, "arr": [0, 1, 2]}
        rec = json.loads(f.attrs["provenance"])
        assert sorted(f.keys()) == ["x"]  # nothing added to the data payload
    with open(_stem(inst) + "_provenance.json") as f:
        assert json.load(f) == rec

    for key in REQUIRED:
        assert key in rec, key
    assert rec["qick_version"]
    assert rec["soccfg_sha1"] == hashlib.sha1(soccfg.dump_cfg().encode()).hexdigest()
    assert rec["soccfg_sw_version"] == soccfg["sw_version"]
    assert rec["qubit_readout"] == 2 and rec["qubit_pulse"] == 3
    assert rec["device"] == "TESTDEV" and rec["rfsoc_host"] == "192.0.2.1"
    assert rec["experiment_class"] == "ExperimentClass"
    assert rec["data_file"] == inst.fname
    assert rec["git_commit"] is None or len(rec["git_commit"]) == 40
    # ISO-8601 with UTC offset, start <= end
    for key in ("start_time", "end_time", "session_start_time"):
        assert len(rec[key]) == 25 and rec[key][10] == "T" and rec[key][19] in "+-", rec[key]
    assert rec["start_time"] <= rec["end_time"]
    charge = rec["bias"]["charge_yoko"]
    assert charge["setpoint"] == 0.002 and charge["readback"] == 0.002 and charge["unit"] == "V"
    assert charge["address"] == "GPIB1::9::INSTR"
    assert "program_class" not in rec  # this class keeps no program


def test_ramp_records_level_without_extra_gpib_traffic():
    y = _Yoko(0.0)
    yoko_mod.ramp_to(y, 0.0)
    assert y.log == ["Q :SOUR:LEV?", "W :SOUR:LEV 0.0", "Q :SOUR:LEV?"]  # unchanged traffic
    n = len(y.log)
    rec = io.provenance()
    assert len(y.log) == n  # provenance queries nothing
    assert rec["bias"]["charge_yoko"]["readback"] == 0.0

    twpa = _Yoko(0.0)
    twpa.resource_name = "GPIB1::12::INSTR"
    yoko_mod.ramp_current(twpa, 2e-6, 1.0, dt=1e-4)
    assert io.provenance()["bias"]["twpa_bias"]["setpoint"] == 2e-6
    assert io.provenance()["bias"]["twpa_bias"]["unit"] == "A"


def test_program_hash_when_the_experiment_keeps_its_program(tmp_path):
    class Prog:
        def asm(self):
            return "regwi 0, $1, 5;"

    inst = _make(tmp_path, FakeSocCfg("A"))
    inst.prog = Prog()
    inst.save_data({"x": [1.0]})
    inst.save_config()
    with h5py.File(inst.fname, "r") as f:
        rec = json.loads(f.attrs["provenance"])
    assert rec["program_class"] == "Prog"
    assert rec["program_asm_sha1"] == hashlib.sha1(b"regwi 0, $1, 5;").hexdigest()


def test_git_unavailable_still_saves(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    inst = _make(tmp_path, FakeSocCfg("A"))
    inst.save_data({"x": [1.0]})
    inst.save_config()
    with h5py.File(inst.fname, "r") as f:
        rec = json.loads(f.attrs["provenance"])
    assert rec["git_commit"] is None and rec["git_dirty"] is None
    assert rec["qick_version"]  # the rest is still recorded


@pytest.mark.parametrize(
    "exc", [FileNotFoundError("git"), subprocess.TimeoutExpired("git", 5.0), OSError("x")]
)
def test_git_failure_modes_give_none(monkeypatch, exc):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(io.subprocess, "run", boom)
    rec = io.provenance()
    assert rec["git_commit"] is None and rec["git_dirty"] is None


def test_static_facts_are_computed_once(monkeypatch):
    calls = []
    real = io._git

    def counting(*args):
        calls.append(args)
        return real(*args)

    monkeypatch.setattr(io, "_git", counting)
    for _ in range(5):
        io.provenance()
    assert len(calls) <= 2  # rev-parse (+ status) once per process, not per save


def test_provenance_failure_never_blocks_a_save(tmp_path, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("provenance broke")

    monkeypatch.setattr(experiment_mod, "provenance_json", boom)
    inst = _make(tmp_path, FakeSocCfg("A"))
    inst.save_data({"x": [1.0]})
    inst.save_config()
    with h5py.File(inst.fname, "r") as f:
        assert json.loads(f.attrs["config"]) == {"reps": 3}
        assert "provenance" not in f.attrs
    assert not os.path.exists(_stem(inst) + "_provenance.json")

    # finish() too
    inst2 = _make(tmp_path, FakeSocCfg("A"))
    assert finish(ExperimentClass, inst2, {"x": [2.0]}) is None
    with open(inst2.cname) as f:
        assert json.load(f) == {"reps": 3}

    # a failing piece inside provenance() is reported in the record, not raised
    monkeypatch.setattr(io, "_static", lambda: 1 / 0)
    rec = io.provenance()
    assert "ZeroDivisionError" in rec["provenance_error"]


def test_unwritable_sidecar_does_not_fail_the_save(tmp_path, monkeypatch, capsys):
    inst = _make(tmp_path, FakeSocCfg("A"))
    os.makedirs(_stem(inst) + "_provenance.json")  # a directory: the sidecar open() fails
    inst.save_data({"x": [1.0]})
    inst.save_config()
    assert "[provenance] could not write" in capsys.readouterr().out
    with open(inst.cname) as f:
        assert json.load(f) == {"reps": 3}
    with h5py.File(inst.fname, "r") as f:  # the h5 attribute is still written
        assert json.loads(f.attrs["provenance"])["experiment_class"] == "ExperimentClass"


def test_provenance_never_reads_the_datetime_clock(monkeypatch):
    class NoClock:
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("provenance must not call datetime.now()")

    monkeypatch.setattr(io, "datetime", NoClock)
    rec = io.provenance(t_start=0.0)
    assert "provenance_error" not in rec and rec["end_time"]


def test_save_record_writes_a_provenance_sidecar(tmp_path):
    _session(None)
    base = str(tmp_path / "Cycle_000_MR")
    io.save_record(base, {"reps": 1}, a=np.arange(2))
    with open(base + "_config.json") as f:
        assert json.load(f) == {"reps": 1}
    with open(base + "_provenance.json") as f:
        rec = json.load(f)
    assert rec["qubit_readout"] == 2 and rec["data_root"] == "/data/TESTDEV/Q2//"
    with np.load(base + ".npz") as z:
        assert sorted(z.files) == ["a"]


def test_write_provenance_reports_and_returns_none_on_failure(tmp_path, capsys):
    assert io.write_provenance(str(tmp_path / "missing_dir" / "x")) is None
    assert "[provenance] could not write" in capsys.readouterr().out


def test_save_record_with_its_experiment_carries_class_file_and_program_hash(tmp_path):
    class Prog:
        def asm(self):
            return "regwi 0, $2, 7;"

    inst = _make(tmp_path, FakeSocCfg("A"))
    inst.prog = Prog()
    base = str(tmp_path / "ChargeDispersionQuasiCW_x")
    io.save_record(base, {"reps": 1}, inst, a=np.arange(2))
    with open(base + "_provenance.json") as f:
        rec = json.load(f)
    assert rec["program_asm_sha1"] == hashlib.sha1(b"regwi 0, $2, 7;").hexdigest()
    assert rec["experiment_class"] == "ExperimentClass" and rec["data_file"] == inst.fname
    assert rec["start_time"] and rec["start_time"] <= rec["end_time"]
    with np.load(base + ".npz") as z:  # the experiment is not an array
        assert sorted(z.files) == ["a"]
    with open(base + "_config.json") as f:
        assert json.load(f) == {"reps": 1}


# --- the other write sites ---------------------------------------------------------------------


def test_build_context_registers_the_session(monkeypatch):
    import qicklab.core.context as context_mod

    class _Stop(Exception):
        pass

    def _no_visa():
        raise _Stop  # build_context stops right after the session is registered

    soccfg = FakeSocCfg("A")
    monkeypatch.setattr(context_mod, "makeProxy", lambda **kw: (None, soccfg))
    monkeypatch.setattr(context_mod.pyvisa, "ResourceManager", _no_visa)
    qp = {
        "2": {"Readout": {"Gain": 1000, "Frequency": 7000.0}, "outerfoldername": "/data/D/Q2//"},
        "3": {"Qubit": {"Gain": 1000, "pi2_Gain": 500, "Frequency": 3000.0}},
    }
    with pytest.raises(_Stop):
        context_mod.build_context(
            qp,
            2,
            3,
            0.125,
            Transmission_params={},
            Spec_relevant_params={"qubit_gain": 800},
            tl={},
            ts={},
            charge_params={},
            yoko_fixed=True,
            rfsoc_host="192.0.2.7",
            rfsoc_port=9000,
            rfsoc_name="board",
            rfsoc_timeout_s=12.0,
            device="DEV1",
        )
    s = io.session()
    assert {k: s[k] for k in s if k != "session_start_time"} == {
        "device": "DEV1",
        "data_root": "/data/D/Q2//",
        "qubit_readout": 2,
        "qubit_pulse": 3,
        "rfsoc_host": "192.0.2.7",
        "rfsoc_port": 9000,
        "rfsoc_name": "board",
        "rfsoc_timeout_s": 12.0,
        "yoko_addr": "GPIB1::9::INSTR",  # the build_context default
        "start_voltage": 0.125,
        "yoko_fixed": True,
    }
    rec = io.provenance()
    assert rec["soccfg_sha1"] == hashlib.sha1(soccfg.dump_cfg().encode()).hexdigest()
    assert rec["device"] == "DEV1" and rec["qubit_pulse"] == 3


def test_undriven_partial_save_writes_the_attribute_from_save_data(tmp_path, monkeypatch):
    import qicklab.core.acquisition as acquisition
    import qicklab.experiments.undriven_single_shot as us_mod
    from tests.test_partial_save import (
        START_V,
        _FakeYoko,
        _program_factory,
        _undriven,
        _undriven_shots,
    )

    for mod in (yoko_mod, acquisition, us_mod):
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    abort = ValueError("readout broke")
    prog_cls, _ = _program_factory(["ok", "ok", abort], _undriven_shots)
    monkeypatch.setattr(us_mod, "UndrivenSingleShotProgram", prog_cls)
    exp = _undriven(tmp_path, _FakeYoko(level=START_V))
    monkeypatch.setattr(exp, "save_config", lambda: None)  # only save_data can write it

    with pytest.raises(ValueError):
        exp.acquire()
    with h5py.File(exp.fname, "r") as f:
        assert f["sweep_completed"][()] == 2  # the partial-sweep save
        rec = json.loads(f.attrs["provenance"])
    assert rec["experiment_class"] == "UndrivenSingleShot" and rec["data_file"] == exp.fname
    assert rec["bias"]["charge_yoko"]["unit"] == "V"  # the sweep's ramps were recorded
    assert not os.path.exists(_stem(exp) + "_provenance.json")  # the sidecar is save_config's


def test_active_reset_verify_overlay_gets_a_sidecar(tmp_path, monkeypatch):
    import types

    import qicklab.runs.active_reset as ar

    class _ARV:
        def __init__(self, path, cfg, soc, soccfg, outerFolder):
            self.cfg = cfg

        def acquire(self):
            return {"data": {"p_ground": np.full(2, 0.9)}}

    monkeypatch.setattr(ar, "ActiveResetVerify", _ARV)
    monkeypatch.setattr(ar, "finish", lambda *a, **k: None)
    monkeypatch.setattr(ar.plt, "savefig", lambda *a, **k: None)
    monkeypatch.setattr(
        ar,
        "calibrate_active_reset_readout",
        lambda ctx: {
            "res_phase": 0,
            "readout_threshold": 0.5,
            "reset_ground_below_threshold": True,
            "g_center": np.zeros(2),
            "e_center": np.ones(2),
        },
    )
    soccfg = FakeSocCfg("A")
    ctx = types.SimpleNamespace(
        outerFolder=str(tmp_path),
        qubit_frequency_center=3000.0,
        qubit_gain=1000,
        qubit_sigma=0.05,
        qubit_flattop=0.0,
        Qubit_Readout=2,
        soc=None,
        soccfg=soccfg,
        working_config=lambda: {},
    )
    params = {
        "reps": 10,
        "relax_delay": 10,
        "n_verify_reads": 2,
        "verify_relax_delay": 1,
        "reset_cycles": 1,
        "reset_readout_relax_delay": 1,
        "post_reset_wait": 0,
    }
    ar.run_active_reset_verify(ctx, params)
    (npz,) = (tmp_path / "ActiveResetVerify").glob("ActiveResetVerify_*.npz")
    rec = json.loads((npz.parent / (npz.stem + "_provenance.json")).read_text())
    assert rec["soccfg_sha1"] == hashlib.sha1(soccfg.dump_cfg().encode()).hexdigest()


def test_twpa_flux_sweep_npz_gets_a_sidecar_with_the_bias_ramp(tmp_path, monkeypatch):
    from qicklab.twpa import flux_sweep
    from tests.test_yoko_safety import ScriptedYoko, _patch_script

    dev = ScriptedYoko(output=False, func="CURR", rang=1e-3, level=0.0)
    _patch_script(monkeypatch, flux_sweep, dev)
    monkeypatch.setattr(flux_sweep, "SAVE_DIR", str(tmp_path))
    monkeypatch.setattr(flux_sweep, "N_BIAS_POINTS", 2)
    monkeypatch.setattr(flux_sweep, "I_START_uA", 0.0)
    monkeypatch.setattr(flux_sweep, "I_STOP_uA", 0.5)
    monkeypatch.setattr(flux_sweep, "PNAX_N_FREQ_POINTS", 3)
    monkeypatch.setattr(flux_sweep, "configure_pnax", lambda *a, **k: None)
    monkeypatch.setattr(flux_sweep, "measure_s21_band", lambda pnax, n: np.ones(3, dtype=complex))
    monkeypatch.setattr(flux_sweep.plt, "show", lambda *a, **k: None)
    flux_sweep.main()
    flux_sweep.plt.close("all")
    (npz,) = tmp_path.glob("*.npz")
    rec = json.loads((tmp_path / (npz.stem + "_provenance.json")).read_text())
    assert rec["start_time"] and rec["start_time"] <= rec["end_time"]
    twpa = rec["bias"]["twpa_bias"]  # the last ramp before the last save: 0.5 uA
    assert twpa["unit"] == "A" and twpa["setpoint"] == pytest.approx(0.5e-6)
