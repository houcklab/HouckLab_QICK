"""Stop button -> interrupts a running acquisition and stops the board. No hardware: a fake
soc stands in for the Pyro proxy and mimics what matters about QICK's acquire loop
(poll_data blocks, returns nothing, and is called again and again).

    cd WorkingProjects
    QT_QPA_PLATFORM=offscreen python -m pytest triangle_lattice_quench/Run_Experiments/calibration_gui/test_abort.py

NOT covered, because it needs the board: that ``soc.streamer.stop_readout()`` works through
the Pyro proxy, and what the DACs do when the tProc is stopped mid-sequence.
"""
import os
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from triangle_lattice_quench.Run_Experiments.calibration_gui import abortable_soc, state as st
from triangle_lattice_quench.Run_Experiments.calibration_gui.abortable_soc import (
    POLL_TIMEOUT_S, AbortableSoc, AcquisitionAborted)

_app = QApplication.instance() or QApplication(sys.argv)


class FakeStreamer:
    def __init__(self, soc):
        self.soc = soc

    def stop_readout(self):
        self.soc.calls.append(("stop_readout", threading.get_ident()))


class FakeSoc:
    """poll_data blocks for ``timeout`` and returns nothing, like a QICK board that has not
    produced a packet yet."""
    tproc = object()

    def __init__(self, fail_stop_tproc=False):
        self.calls, self.poll_kwargs = [], []
        self.fail_stop_tproc = fail_stop_tproc
        self.streamer = FakeStreamer(self)
        self.data_for_next_poll = []

    def poll_data(self, totaltime=0.1, timeout=None):
        self.poll_kwargs.append({"totaltime": totaltime, "timeout": timeout})
        time.sleep(timeout if timeout is not None else 5.0)
        out, self.data_for_next_poll = self.data_for_next_poll, []
        return out

    def get_tproc_counter(self, addr=1):
        return 7

    def stop_tproc(self, lazy=False):
        self.calls.append(("stop_tproc", lazy, threading.get_ident()))
        if self.fail_stop_tproc:
            raise ConnectionError("board unreachable")


def _names(soc):
    return [c[0] for c in soc.calls]


# ------------------------------------------------------------------ the wrapper

def test_without_a_stop_everything_is_forwarded_and_polls_are_bounded():
    soc = FakeSoc()
    w = AbortableSoc(soc, lambda: False)
    assert w.get_tproc_counter(addr=3) == 7 and w.tproc is soc.tproc          # delegation
    soc.data_for_next_poll = [("packet",)]
    assert w.poll_data() == [("packet",)]                                      # data passes through
    w.poll_data(totaltime=0.1, timeout=0.01)
    w.poll_data(totaltime=0.1, timeout=99)
    # QICK's default timeout=None would block until a packet arrives; it is bounded, and an
    # explicit shorter timeout is respected while a longer one is capped.
    assert [k["timeout"] for k in soc.poll_kwargs] == [POLL_TIMEOUT_S, 0.01, POLL_TIMEOUT_S]
    assert soc.calls == [] and w.interrupt_errors == []
    with pytest.raises(AttributeError):
        w.no_such_attribute


def test_default_stops_the_tproc_and_ends_the_readout():
    assert abortable_soc.STOP_TPROC_ON_ABORT is True
    soc = FakeSoc()
    w = AbortableSoc(soc, lambda: True)
    with pytest.raises(AcquisitionAborted):
        w.poll_data()
    assert _names(soc) == ["stop_tproc", "stop_readout"] and w.tproc_stopped


def test_with_stop_tproc_disabled_the_board_is_left_to_finish_its_sequence(monkeypatch):
    monkeypatch.setattr(abortable_soc, "STOP_TPROC_ON_ABORT", False)
    soc = FakeSoc()
    w = AbortableSoc(soc, lambda: True)
    with pytest.raises(AcquisitionAborted):
        w.poll_data()
    assert _names(soc) == ["stop_readout"] and not w.tproc_stopped


def test_stop_during_a_blocked_poll_unwinds_quickly_and_stops_the_board_once():
    soc = FakeSoc()
    flag = threading.Event()
    w = AbortableSoc(soc, flag.is_set)
    threading.Timer(0.3, flag.set).start()

    t0 = time.perf_counter()
    with pytest.raises(AcquisitionAborted):
        while True:                                  # QICK's loop: poll again and again
            w.poll_data()
    elapsed = time.perf_counter() - t0

    assert 0.3 <= elapsed < 0.3 + POLL_TIMEOUT_S + 0.5       # seen within about one poll
    assert _names(soc) == ["stop_tproc", "stop_readout"]
    assert soc.calls[0][1] is True                           # lazy=True: never a v1 reset
    me = threading.get_ident()                                # all board calls on THIS thread
    assert soc.calls[0][2] == me and soc.calls[1][1] == me


def test_data_from_the_poll_during_which_stop_arrived_is_dropped():
    soc = FakeSoc()
    flag = threading.Event()
    w = AbortableSoc(soc, flag.is_set)
    soc.data_for_next_poll = [("late packet",)]
    threading.Timer(0.05, flag.set).start()
    with pytest.raises(AcquisitionAborted):
        w.poll_data()                                        # returns data, but a stop arrived


def test_a_failing_board_call_does_not_stop_the_unwind():
    soc = FakeSoc(fail_stop_tproc=True)
    w = AbortableSoc(soc, lambda: True)
    with pytest.raises(AcquisitionAborted):
        w.poll_data()
    assert _names(soc) == ["stop_tproc", "stop_readout"]     # the second call still happened
    assert len(w.interrupt_errors) == 1 and "board unreachable" in w.interrupt_errors[0]


def test_get_tproc_counter_loops_are_interruptible_too():
    soc = FakeSoc()
    with pytest.raises(AcquisitionAborted):
        AbortableSoc(soc, lambda: True).get_tproc_counter(addr=1)


def test_broad_except_exception_blocks_cannot_swallow_the_abort():
    swallowed = False
    with pytest.raises(AcquisitionAborted):
        try:
            AbortableSoc(FakeSoc(), lambda: True).poll_data()
        except Exception:                                     # what the stages are full of
            swallowed = True
    assert not swallowed


# ------------------------------------------------------------------ the real worker

class FakeExpt:
    def __init__(self, soc, mode):
        self.soc, self.mode = soc, mode

    def acquire(self):
        if self.mode == "boom":
            raise RuntimeError("fit exploded")
        for _ in range(100):                                   # like prog.acquire(): loop on poll_data
            got = self.soc.poll_data()
            if self.mode == "finish" or got:
                return {"data": {}}
        return {"data": {}}


class FakeStage:
    def __init__(self, name, state, mode, entered=None):
        self.name, self.state, self.mode, self.entered = name, state, mode, entered
        self.made = 0

    def make_experiment(self, cfg):
        self.made += 1
        if self.entered:
            self.entered.set()
        return FakeExpt(self.state.soc, self.mode)      # reads state.soc, as the real stages do

    def on_apply(self, expt, data):
        pass

    def on_success(self, expt, data):
        return "ok"


@pytest.fixture
def worker_env(monkeypatch):
    monkeypatch.setattr(st, "SETTINGS_APP", "CalibrationGuiPytestScope")
    st.get_settings().clear()
    from triangle_lattice_quench.Run_Experiments.calibration_gui.main_window import MainWindow
    win = MainWindow()
    yield win
    win.auto_calib_tab._params_timer.stop()
    win.close()
    win.deleteLater()
    _app.processEvents()
    st.get_settings().clear()


def _run_worker(win, soc, jobs, stop_when=None, stop_after_s=0.0, pre_stop=False, timeout_s=10):
    from triangle_lattice_quench.Run_Experiments.calibration_gui.tabs.auto_calib import AutoCalibWorker
    win.state.soc = soc
    stages = {s.name: s for s in jobs["stages"]}
    schedule = [(q, name, {}) for q, name in jobs["order"]]
    w = AutoCalibWorker(win.state, schedule, stages)
    rec = {"progress": [], "done": [], "failed": [], "log": [], "finished": []}
    w.progress.connect(lambda q, s, t: rec["progress"].append((q, s, t)), Qt.DirectConnection)
    w.stage_done.connect(lambda *a: rec["done"].append(a[:2]), Qt.DirectConnection)
    w.stage_failed.connect(lambda *a: rec["failed"].append(a[:3]), Qt.DirectConnection)
    w.log_msg.connect(rec["log"].append, Qt.DirectConnection)
    w.finished_all.connect(lambda: rec["finished"].append(time.perf_counter()), Qt.DirectConnection)
    if pre_stop:
        w.stop()
    w.start()
    t_stop = None
    if stop_when is not None:
        assert stop_when.wait(5), "the acquisition never started"
        time.sleep(stop_after_s)
        t_stop = time.perf_counter()
        w.stop()
    assert w.wait(timeout_s * 1000), "worker did not finish"
    return rec, t_stop


def test_stop_mid_acquisition_stops_the_run_the_board_and_restores_the_soc(worker_env):
    win, soc, entered = worker_env, FakeSoc(), threading.Event()
    a = FakeStage("FakeA", win.state, "hang", entered)
    b = FakeStage("FakeB", win.state, "finish")
    jobs = {"stages": [a, b], "order": [("1", "FakeA"), ("2", "FakeA"), ("3", "FakeB")]}

    rec, t_stop = _run_worker(win, soc, jobs, stop_when=entered, stop_after_s=0.3)

    assert rec["finished"] and rec["finished"][0] - t_stop < POLL_TIMEOUT_S + 1.0   # prompt
    assert rec["failed"] == [] and rec["done"] == []                  # a stop is not a failure
    assert [p for p in rec["progress"] if p[2] in ("stopped", "skipped")] == [
        ("1", "FakeA", "stopped"), ("2", "FakeA", "skipped"), ("3", "FakeB", "skipped")]
    assert a.made == 1 and b.made == 0                                # later jobs never started
    assert _names(soc) == ["stop_tproc", "stop_readout"]              # board stopped, exactly once
    assert win.state.soc is soc                                       # unwrapped again
    assert any("[STOPPED]" in m and "tProc stopped" in m for m in rec["log"])


def test_with_stop_tproc_disabled_the_worker_leaves_the_processor_alone(worker_env, monkeypatch):
    monkeypatch.setattr(abortable_soc, "STOP_TPROC_ON_ABORT", False)
    win, soc, entered = worker_env, FakeSoc(), threading.Event()
    a = FakeStage("FakeA", win.state, "hang", entered)
    jobs = {"stages": [a], "order": [("1", "FakeA")]}
    rec, _ = _run_worker(win, soc, jobs, stop_when=entered, stop_after_s=0.2)
    assert _names(soc) == ["stop_readout"]
    assert any("[STOPPED]" in m and "finishes the sequence" in m for m in rec["log"])
    assert win.state.soc is soc


def test_a_stop_before_the_first_job_just_skips_everything(worker_env):
    win, soc = worker_env, FakeSoc()
    a = FakeStage("FakeA", win.state, "finish")
    jobs = {"stages": [a], "order": [("1", "FakeA"), ("2", "FakeA")]}
    rec, _ = _run_worker(win, soc, jobs, pre_stop=True)
    assert [p[2] for p in rec["progress"]] == ["skipped", "skipped"] and a.made == 0
    assert soc.calls == [] and win.state.soc is soc                   # nothing touched the board


def test_a_failing_stage_is_still_reported_as_a_failure_and_the_soc_restored(worker_env):
    win, soc = worker_env, FakeSoc()
    a = FakeStage("FakeA", win.state, "boom")
    b = FakeStage("FakeB", win.state, "finish")
    jobs = {"stages": [a, b], "order": [("1", "FakeA"), ("1", "FakeB")]}
    rec, _ = _run_worker(win, soc, jobs)
    assert [f[:2] for f in rec["failed"]] == [("1", "FakeA")] and "fit exploded" in rec["failed"][0][2]
    assert rec["done"] == [("1", "FakeB")]                           # the next job still ran
    assert soc.calls == [] and win.state.soc is soc


def test_a_normal_run_is_unaffected(worker_env):
    win, soc = worker_env, FakeSoc()
    a = FakeStage("FakeA", win.state, "finish")
    jobs = {"stages": [a], "order": [("1", "FakeA"), ("2", "FakeA")]}
    rec, _ = _run_worker(win, soc, jobs)
    assert rec["done"] == [("1", "FakeA"), ("2", "FakeA")] and rec["failed"] == []
    assert soc.calls == [] and win.state.soc is soc
