"""Program Builder tab: typed cells, JSON -> segment/drive, duplicate, file label + unsaved prompt."""
import copy
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog

from triangle_lattice_quench.Run_Experiments.calibration_gui.tabs import program_builder as pb


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    from triangle_lattice_quench.Run_Experiments.calibration_gui.main_window import MainWindow
    w = MainWindow()
    yield w
    qapp.processEvents()
    w.close()


def _cell(tab, ref, col):
    return tab.table.item(tab._row_refs.index(ref), col)


def _type(tab, ref, col, text):
    """What a committed edit does: write the text into the cell, itemChanged fires."""
    _cell(tab, ref, col).setText(text)


def test_tab_order_and_no_ff_tab(win):
    names = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    assert names[:2] == ["Qubit Parameters", "Program Builder"] and "FF Frequencies" not in names
    assert not hasattr(win, "ff_freq_tab")


def test_typed_cells_update_model_and_bad_input_reverts(win):
    t = win.program_builder_tab
    seg = ("segment", 0)
    _type(t, seg, 2, "480")
    _type(t, seg, 3, "-12000")
    assert t._segments[0].length_samples == 480 and t._segments[0].gains[0] == -12000
    _type(t, seg, 4, "abc")                                   # garbage: reverted
    _type(t, seg, 5, "99999")                                 # out of DAC range: reverted
    assert t._segments[0].gains[1:3] == [0, 0] and _cell(t, seg, 4).text() == "0"
    t._add_drive()
    drv = ("drive", 0, 0)
    for col, text in ((2, "3800.5"), (3, "7000"), (4, "90"), (5, "0.05"), (6, "3"), (7, "1.5")):
        _type(t, drv, col, text)
    d = t._segments[0].drives[0]
    assert (d.freq, d.gain, d.phase, d.sigma_us, d.len_sigmas, d.relative_t) == (3800.5, 7000, 90, 0.05, 3, 1.5)
    _type(t, drv, 7, "auto")
    assert d.relative_t == "auto"
    _type(t, drv, 5, "0")                                     # sigma must be > 0
    assert d.sigma_us == 0.05


def test_unchanged_commit_keeps_the_exact_value(win):
    t = win.program_builder_tab
    t._add_drive()
    d = t._segments[0].drives[0]
    d.freq = 3862.999926700593                                # displayed rounded
    t._rebuild_table()
    item = _cell(t, ("drive", 0, 0), 2)
    item.setText(item.text())                                 # open + commit, no change
    assert d.freq == 3862.999926700593


def test_duplicate_segment_goes_below_the_selected_one_as_a_deep_copy(win):
    t = win.program_builder_tab
    t._add_segment()
    t._segments[0].gains[0] = 111
    t._select_ref(("segment", 0))
    t._add_drive()
    t._select_ref(("segment", 0))
    t._duplicate_segment()
    assert len(t._segments) == 3
    assert t._segments[1].gains == t._segments[0].gains and t._segments[1].gains is not t._segments[0].gains
    assert t._segments[1].drives[0] is not t._segments[0].drives[0]
    assert t._selected_ref() == ("segment", 1)


def _select_json(t, path):
    def find(item):
        if item.data(0, Qt.UserRole) == path:
            return item
        for i in range(item.childCount()):
            r = find(item.child(i))
            if r is not None:
                return r
    for i in range(t.json_tree.topLevelItemCount()):
        item = find(t.json_tree.topLevelItem(i))
        if item is not None:
            t.json_tree.setCurrentItem(item)
            item.setSelected(True)
            return item
    raise AssertionError(path)


def test_json_gains_and_drive_apply_as_copies(win):
    t = win.program_builder_tab
    jd = win.state.qubit_parameters_json
    before = json.dumps(jd, sort_keys=True)
    group = next(g for g, b in jd["drive_groups"].items() if "FF_Pulses" in b)
    entry = next(iter(jd["drive_groups"][group]["entries"]))
    from triangle_lattice_quench.build_config import QubitParams
    want = QubitParams(copy.deepcopy(jd)).drive_ff("FF_Pulses", group, entry)

    t._select_ref(("segment", 0))
    _select_json(t, ("drive_groups", group, "entries", entry))
    assert t.use_btn.isEnabled()
    t._use_json_selection()
    assert t._segments[0].gains == [int(round(x)) for x in want]
    _type(t, ("segment", 0), 3, "5")                          # a later edit must not touch the JSON
    assert json.dumps(jd, sort_keys=True) == before

    t._select_ref(("segment", 0))
    t._add_drive()
    q = jd["drive_groups"][group]["entries"][entry]["Qubit"]
    d = t._segments[0].drives[0]
    d.phase, d.len_sigmas, d.relative_t = 33.0, 5, 2.0
    _select_json(t, ("drive_groups", group, "entries", entry, "Qubit"))
    t._use_json_selection()
    assert (d.freq, d.gain, d.sigma_us) == (q["Frequency"], q["Gain"], q["sigma"])
    assert (d.phase, d.len_sigmas, d.relative_t) == (33.0, 5, 2.0)

    t._select_ref(("segment", 0))
    _select_json(t, ("drive_groups", group, "description"))   # nothing to copy from a text node
    assert not t.use_btn.isEnabled()
    assert json.dumps(jd, sort_keys=True) == before


def test_json_override_entry_matches_drive_ff(win):
    jd = win.state.qubit_parameters_json
    from triangle_lattice_quench.build_config import QubitParams
    found = None
    for g, b in jd["drive_groups"].items():
        for e, body in (b.get("entries") or {}).items():
            if "FF_override" in (body.get("Qubit") or {}):
                found = (g, e)
    if found is None:
        pytest.skip("no FF_override entry in this JSON")
    g, e = found
    snap = json.dumps(jd, sort_keys=True)
    cand = pb.json_candidates(jd, ("drive_groups", g, "entries", e))
    assert cand["gains"][0] == QubitParams(copy.deepcopy(jd)).drive_ff("FF_Pulses", g, e)
    assert json.dumps(jd, sort_keys=True) == snap


def test_save_load_roundtrip_file_label_and_unsaved_prompt(win, tmp_path, monkeypatch):
    t = win.program_builder_tab
    path = str(tmp_path / "prog.json")
    assert t.file_label.text() == "(not saved to a file)"
    _type(t, ("segment", 0), 2, "640")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (path, ""))
    assert t._save_program() and t._path == path
    assert t.file_label.text() == "prog.json" and not t._is_dirty()
    assert pb.load_program(path)[0][0].length_samples == 640

    _type(t, ("segment", 0), 2, "700")                         # change after a save
    assert "unsaved" in t.file_label.text()
    answers = iter(["cancel", "discard", "save"])
    monkeypatch.setattr(t, "_ask_save_changes", lambda: next(answers))
    t._new_program()                                           # Cancel: nothing changes
    assert t._segments[0].length_samples == 700 and t._path == path
    t._new_program()                                           # Discard: reset, file untouched
    assert t._segments[0].length_samples == 320 and t._path is None
    assert pb.load_program(path)[0][0].length_samples == 640

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (path, ""))
    t._load_program()
    assert t._path == path and t._segments[0].length_samples == 640 and not t._is_dirty()
    _type(t, ("segment", 0), 2, "800")
    t._new_program()                                           # Save: writes the file first
    assert pb.load_program(path)[0][0].length_samples == 800 and t._path is None

    _type(t, ("segment", 0), 2, "900")                         # scratch program: no prompt
    monkeypatch.setattr(t, "_ask_save_changes", lambda: pytest.fail("must not prompt"))
    t._new_program()
    assert t._segments[0].length_samples == 320


def test_save_cancel_in_the_prompt_cancels_the_new(win, tmp_path, monkeypatch):
    t = win.program_builder_tab
    path = str(tmp_path / "p.json")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (path, ""))
    t._save_program()
    _type(t, ("segment", 0), 2, "999")
    monkeypatch.setattr(t, "_ask_save_changes", lambda: "save")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))   # user cancels the file dialog
    t._new_program()
    assert t._segments[0].length_samples == 999 and t._path == path
