"""Auto-Calibration tab state: parameters persist across restarts, and results of stages
that are not re-run stay valid. Headless; QSettings is redirected to a throwaway scope so
the user's real saved parameters are never read or written.

    cd WorkingProjects
    QT_QPA_PLATFORM=offscreen python -m pytest triangle_lattice_quench/Run_Experiments/calibration_gui/test_autocalib_state.py
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

import pytest
from PyQt5.QtWidgets import QApplication

from triangle_lattice_quench.Run_Experiments.calibration_gui import state as st

_app = QApplication.instance() or QApplication(sys.argv)


_windows = []


@pytest.fixture(autouse=True)
def scratch_settings(monkeypatch):
    monkeypatch.setattr(st, "SETTINGS_APP", "CalibrationGuiPytestScope")
    st.get_settings().clear()
    yield
    # A window left alive would fire its pending debounced save into a LATER test's
    # settings scope, so stop and delete every window before clearing.
    for w in _windows:
        w.auto_calib_tab._params_timer.stop()
        w.close()
        w.deleteLater()
    _windows.clear()
    _app.processEvents()
    st.get_settings().clear()


def _window():
    from triangle_lattice_quench.Run_Experiments.calibration_gui.main_window import MainWindow
    w = MainWindow()
    _windows.append(w)
    return w


def _form(win, stage):
    return next(s for s in win.stages if s.name == stage).param_form


def _pump(sec):
    end = time.time() + sec
    while time.time() < end:
        _app.processEvents()


def test_changed_values_survive_a_restart_and_untouched_ones_stay_default():
    a = _window()
    _form(a, "T1").widgets["expts"].setValue(77)
    _form(a, "T2R").widgets["phase_shift_cycles"].setValue(9)
    a.auto_calib_tab._save_params()

    b = _window()                                         # "restart"
    assert _form(b, "T1").values()["expts"] == 77
    assert _form(b, "T2R").values()["phase_shift_cycles"] == 9
    assert _form(b, "T1").values()["reps"] == st.STAGE_DEFAULTS["t1"]["reps"]
    assert "restored 2 saved parameter value(s)" in b.auto_calib_tab.log.toPlainText()


def test_only_non_default_values_are_stored():
    w = _window()
    form = _form(w, "T1")
    form.widgets["expts"].setValue(77)
    w.auto_calib_tab._save_params()
    assert st.get_autocalib_params() == {"T1": {"expts": 77}}

    form.widgets["expts"].setValue(st.STAGE_DEFAULTS["t1"]["expts"])      # back to default
    w.auto_calib_tab._save_params()
    assert st.get_autocalib_params() == {}


def test_untouched_fields_follow_a_changed_code_default(monkeypatch):
    a = _window()
    _form(a, "T1").widgets["expts"].setValue(77)
    a.auto_calib_tab._save_params()

    monkeypatch.setitem(st.STAGE_DEFAULTS["t1"], "reps", 999)             # the code default moves
    b = _window()
    assert _form(b, "T1").values()["reps"] == 999                         # never edited: follows
    assert _form(b, "T1").values()["expts"] == 77                         # edited: kept


def test_stale_corrupt_and_wrongly_typed_saved_values_are_ignored():
    st.get_settings().setValue(st.SETTING_AUTOCALIB_PARAMS, "{ this is not json")
    assert st.get_autocalib_params() == {}
    assert _form(_window(), "T1").values()["expts"] == st.STAGE_DEFAULTS["t1"]["expts"]

    st.set_autocalib_params({"NoSuchStage": {"x": 1}, "T1": {"no_such_key": 5, "expts": "abc", "reps": 123}})
    w = _window()                                         # must not raise
    v = _form(w, "T1").values()
    assert v["reps"] == 123                               # the valid one still applied
    assert v["expts"] == st.STAGE_DEFAULTS["t1"]["expts"]  # unparseable value ignored


def test_edits_are_saved_after_a_short_pause_and_restoring_is_not_an_edit():
    st.set_autocalib_params({"T1": {"expts": 61}})
    w = _window()
    assert not w.auto_calib_tab._params_timer.isActive()  # restoring did not schedule a save

    _form(w, "T1").widgets["reps"].setValue(321)
    assert w.auto_calib_tab._params_timer.isActive()
    _pump(0.8)
    assert st.get_autocalib_params() == {"T1": {"expts": 61, "reps": 321}}


def test_rerunning_one_stage_keeps_the_other_stages_results_and_view_button():
    w = _window()
    tab = w.auto_calib_tab
    q = tab._row_qubit[0]
    other = tab._row_qubit[1]
    tab.results[q] = {"T1": ("expt-t1", "data-t1"), "T2R": ("expt-t2", "data-t2")}
    tab.results[other] = {"T1": ("e", "d")}
    for k in [(q, "T1"), (q, "T2R"), (other, "T1")]:
        tab._cell_outcome[k] = "ok"
    btn = tab._result_buttons[q]
    btn.setText("View"); btn.setEnabled(True)

    tab._reset_for_run({(q, "T1")})                       # run T1 again on this qubit only

    assert tab.results[q] == {"T2R": ("expt-t2", "data-t2")}             # T2R plot still valid
    assert tab._cell_outcome[(q, "T2R")] == "ok" and tab._cell_outcome[(q, "T1")] is None
    assert tab.results[other] == {"T1": ("e", "d")}                      # other qubit untouched
    assert btn.isEnabled() and btn.text() == "View"


def test_view_button_clears_only_when_a_qubit_has_no_results_left():
    w = _window()
    tab = w.auto_calib_tab
    q = tab._row_qubit[0]
    tab.results[q] = {"T1": ("e", "d")}
    btn = tab._result_buttons[q]
    btn.setText("View"); btn.setEnabled(True)

    tab._reset_for_run({(q, "T1")})                       # the only cached stage is re-run

    assert q not in tab.results
    assert btn.text() == "-" and not btn.isEnabled()
