"""Background RFSoC connection: controller semantics and the in-place state update (no Pyro, no board)."""
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

from triangle_lattice_quench.Run_Experiments.calibration_gui.tabs.connection import ConnectionController


class _Cfg:
    def description(self):
        return "fake soccfg"


def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Never write the user's real saved connection / channel map."""
    from PyQt5.QtCore import QSettings
    from triangle_lattice_quench.Run_Experiments.calibration_gui.tabs import connection
    ini = str(tmp_path / "s.ini")
    monkeypatch.setattr(connection, "get_settings", lambda: QSettings(ini, QSettings.IniFormat))


def _controller(connector):
    return ConnectionController(connector=connector)


def test_success_emits_once_with_params(qapp):
    ctrl = _controller(lambda h, p, n: (f"soc-{n}", _Cfg(), {"gens": []}))
    got = []
    ctrl.succeeded.connect(lambda soc, cfg, d, params: got.append((soc, params)))
    ctrl.connect_to("h", 1, "a")
    assert _wait(lambda: got) and got == [("soc-a", {"host": "h", "port": 1, "name": "a"})]
    assert not ctrl.pending


def test_abort_drops_the_late_result(qapp):
    release = threading.Event()
    def slow(h, p, n):
        release.wait(5)
        return "soc", _Cfg(), {}
    ctrl = _controller(slow)
    got, aborted = [], []
    ctrl.succeeded.connect(lambda *a: got.append(a))
    ctrl.aborted.connect(lambda: aborted.append(1))
    ctrl.connect_to("h", 1, "a")
    assert ctrl.pending
    ctrl.abort()
    assert aborted and not ctrl.pending
    release.set()
    time.sleep(0.2); QApplication.processEvents()
    assert got == []


def test_second_connect_supersedes_the_first(qapp):
    gate = {"a": threading.Event()}
    def conn(h, p, n):
        if n == "a":
            gate["a"].wait(5)
        return f"soc-{n}", _Cfg(), {}
    ctrl = _controller(conn)
    got, failed = [], []
    ctrl.succeeded.connect(lambda soc, cfg, d, params: got.append(soc))
    ctrl.failed.connect(failed.append)
    ctrl.connect_to("h", 1, "a")
    ctrl.connect_to("h", 1, "b")
    assert _wait(lambda: got) and got == ["soc-b"]
    gate["a"].set()
    time.sleep(0.2); QApplication.processEvents()
    assert got == ["soc-b"] and not failed


def test_failure_is_reported_not_raised(qapp):
    def bad(h, p, n):
        raise TimeoutError("no route")
    ctrl = _controller(bad)
    msgs = []
    ctrl.failed.connect(msgs.append)
    ctrl.connect_to("h", 1, "a")
    assert _wait(lambda: msgs) and "TimeoutError" in msgs[0] and not ctrl.pending


def test_window_opens_offline_and_connect_updates_state_in_place(qapp):
    from triangle_lattice_quench.Run_Experiments.calibration_gui.main_window import MainWindow
    win = MainWindow()
    try:
        assert not win.state.is_connected() and win.conn_dialog is not None
        state_obj = win.state
        win.state.outer_folder = "X:/keep/"
        win.conn_ctrl._connector = lambda h, p, n: ("SOC", _Cfg(), {"gens": [{"type": "x", "fs": 1}] * 12})
        win.conn_ctrl.connect_to("h", 9, "nm")
        assert _wait(lambda: win.state.is_connected())
        assert win.state is state_obj and win.state.soc == "SOC" and win.state.server_name == "nm"
        assert win.state.outer_folder == "X:/keep/"
        assert "connected" in win.conn_label.text()
        win.conn_dialog.on_disconnect()
        assert not win.state.is_connected() and "not connected" in win.conn_label.text()
    finally:
        win.close()


def test_duplicate_group_copies_in_place_and_selects_the_copy(qapp):
    import copy
    from PyQt5.QtCore import Qt
    from triangle_lattice_quench.Run_Experiments.calibration_gui.main_window import MainWindow
    win = MainWindow()
    try:
        tab = win.params_tab
        jd = tab._jd
        names = list(jd["drive_groups"])
        src = names[0]
        tab.duplicate_group("drive_groups", src, "my_copy")
        groups = jd["drive_groups"]
        assert win.state.qubit_parameters_json is jd                      # same live dict
        assert list(groups)[:2] == [src, "my_copy"] and len(groups) == len(names) + 1
        assert groups["my_copy"] == groups[src] and groups["my_copy"] is not groups[src]
        assert groups["my_copy"]["entries"] is not groups[src]["entries"]  # deep copy
        assert tab.tree.currentItem().data(0, Qt.UserRole) == ("group", "drive_groups", "my_copy")
        for bad in ("", src, "my_copy"):
            with pytest.raises(ValueError):
                tab.duplicate_group("drive_groups", src, bad)
        from triangle_lattice_quench.Run_Experiments.calibration_gui.helpers import _diff_entries
        added = [r for r in _diff_entries(win.state.qubit_parameters_json_snapshot, jd) if r["status"] == "added"]
        assert added and {r["group"] for r in added} == {"my_copy"}        # Save will write the copy
    finally:
        qapp.processEvents()                 # the view-restoring QTimer must fire before the window dies
        win.close()
