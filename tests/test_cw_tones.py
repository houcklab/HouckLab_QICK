"""CW tones (F69): one periodic program, held, then always stopped with soc.reset_gens().

A periodic generator output keeps playing after the tProc `end` and after Python returns, so
every exit path of ConstantTwoTone / SingleTone (Enter, hold_s, Ctrl-C, no stdin) must call
reset_gens. Hardware-free: a recording soc and the synthetic board A.
"""

import builtins
import glob
import json
import os
import time

import pytest

from tests.regression import capture


class RecordingSoc:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: self.calls.append(name)


def _cfg():
    from qicklab.hardware.board import BaseConfig

    cfg = dict(BaseConfig)
    cfg.update(
        mixer_freq=0.0,
        pulse_freq=7095.4,
        pulse_gain=1500,
        qubit_freq=2651.0,
        qubit_gain=1000,
        tone_length=151,
        length=15.3,
        reps=1000,
        rounds=1,
    )
    return cfg


def _experiment(cls_name, tmp_path, soc):
    import qicklab.experiments.cw_tones as cw

    return getattr(cw, cls_name)(
        soc=soc,
        soccfg=capture.FakeSocCfg("A"),
        path="CW",
        outerFolder=str(tmp_path) + os.sep,
        cfg=_cfg(),
    )


@pytest.mark.parametrize("cls_name", ["ConstantTwoTone", "SingleTone"])
def test_hold_then_stop(tmp_path, monkeypatch, cls_name):
    soc = RecordingSoc()
    slept = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append((s, list(soc.calls))))
    inst = _experiment(cls_name, tmp_path, soc)
    cfg_before = dict(inst.cfg)
    inst.acquire(hold_s=2.5)
    # Started once (no 1e6 / 100 x acquire loop, no readout), held while on, then stopped.
    assert soc.calls.count("load_bin_program") == 1 and soc.calls.count("start_tproc") == 1
    assert "start_readout" not in soc.calls
    ((held_s, calls_while_held),) = slept
    assert held_s == 2.5 and "reset_gens" not in calls_while_held
    assert calls_while_held[-1] == "start_tproc"
    assert soc.calls[-1] == "reset_gens" and soc.calls.count("reset_gens") == 1
    assert inst.cfg == cfg_before  # SingleTone used to write reps/rounds


@pytest.mark.parametrize("cls_name", ["ConstantTwoTone", "SingleTone"])
def test_ctrl_c_still_stops_the_tones(tmp_path, monkeypatch, cls_name):
    soc = RecordingSoc()

    def interrupt(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", interrupt)
    inst = _experiment(cls_name, tmp_path, soc)
    with pytest.raises(KeyboardInterrupt):
        inst.acquire()
    assert soc.calls[-1] == "reset_gens"


def test_enter_stops_the_tones(tmp_path, monkeypatch):
    soc = RecordingSoc()
    seen = []
    monkeypatch.setattr(builtins, "input", lambda *_: seen.append(list(soc.calls)) or "")
    _experiment("ConstantTwoTone", tmp_path, soc).acquire()
    assert len(seen) == 1 and "reset_gens" not in seen[0] and seen[0][-1] == "start_tproc"
    assert soc.calls[-1] == "reset_gens"


@pytest.mark.parametrize("exc", [EOFError, OSError])
def test_no_stdin_stops_at_once(tmp_path, monkeypatch, capsys, exc):
    """No usable stdin (closed, or captured as under pytest / the golden harness): no hang."""
    soc = RecordingSoc()

    def no_stdin(*_):
        raise exc

    monkeypatch.setattr(builtins, "input", no_stdin)
    _experiment("SingleTone", tmp_path, soc).acquire()
    assert soc.calls[-1] == "reset_gens"
    assert "no interactive stdin" in capsys.readouterr().out


def test_start_failure_still_stops(tmp_path):
    class FailingSoc(RecordingSoc):
        def start_tproc(self):
            raise RuntimeError("board gone")

    soc = FailingSoc()
    with pytest.raises(RuntimeError, match="board gone"):
        _experiment("ConstantTwoTone", tmp_path, soc).acquire(hold_s=0)
    assert soc.calls[-1] == "reset_gens"


@pytest.mark.parametrize("run", ["run_constant_two_tone", "run_constant_tone"])
def test_run_makes_one_folder_and_saves_the_settings(tmp_path, monkeypatch, run):
    import qicklab.runs.resonator as resonator

    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)

    def no_operator(prompt=""):
        raise AssertionError("params['hold_s'] was ignored: the step waited on input()")

    monkeypatch.setattr("builtins.input", no_operator)

    class Ctx:
        soc = RecordingSoc()
        soccfg = capture.FakeSocCfg("A")
        outerFolder = str(tmp_path) + os.sep

        def working_config(self):
            return _cfg()

    ctx = Ctx()
    getattr(resonator, run)(ctx, {"hold_s": 1.5})
    assert slept == [1.5]  # params['hold_s'] reaches the hold
    assert ctx.soc.calls.count("start_tproc") == 1 and ctx.soc.calls[-1] == "reset_gens"
    (saved,) = glob.glob(str(tmp_path / "*" / "*" / "*.json"))
    with open(saved) as fid:
        assert json.load(fid)["pulse_freq"] == 7095.4
    assert len(glob.glob(str(tmp_path / "*" / "*"))) == 1
