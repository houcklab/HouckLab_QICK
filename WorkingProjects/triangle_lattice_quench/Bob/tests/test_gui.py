"""GUI behavior, driven like a user would (pytest-qt, offscreen).

Covers: dropping blocks onto the canvas, moving and reordering them, copy/paste,
undo/redo, inspector edits (values, sources, sweeps, per-channel overrides, dropdowns),
the problems tab and status pill, experiment settings, save/open, and the preview slider.
"""
import json

import numpy as np
import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pytestqt")
pytestmark = pytest.mark.gui

from PyQt5.QtCore import QMimeData, QPointF, Qt  # noqa: E402
from PyQt5.QtGui import QDropEvent  # noqa: E402
from PyQt5.QtWidgets import QComboBox, QPushButton  # noqa: E402

from Bob.core.params import Sweep, Value  # noqa: E402

TEMPLATES = None


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """Answer "Discard" to unsaved-changes prompts and dismiss warnings; record their titles."""
    from PyQt5.QtWidgets import QMessageBox
    asked = []

    def question(parent, title, text, *a, **k):
        asked.append(title)
        return QMessageBox.Discard

    def warning(parent, title, text, *a, **k):
        asked.append(title)
        return QMessageBox.Ok
    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(warning))
    return asked


@pytest.fixture
def win(qtbot, isolated_settings):
    from Bob.Bob_GUI.main_window import MainWindow
    from Bob.library import build_library
    global TEMPLATES
    TEMPLATES = build_library.HERE / "templates"
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1500, 950)
    w.show()
    w.bob.ctl.new_sequence()
    w.bob.ctl.refresh_now()
    yield w
    _dispose(w)


def _dispose(w):
    """Really delete a window; closed-but-alive windows pile up and slow every later test."""
    from PyQt5.QtCore import QCoreApplication, QEvent
    w.close()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _drop(win, mime_type, payload, pos):
    md = QMimeData()
    md.setData(mime_type, payload.encode() if isinstance(payload, str) else json.dumps(payload).encode())
    win.bob.canvas.dropEvent(QDropEvent(QPointF(*pos), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier))
    win.bob.ctl.refresh_now()


def _new(win, type_name, pos):
    from Bob.Bob_GUI.canvas.canvas import MIME_NEW
    _drop(win, MIME_NEW, type_name, pos)


def _cols(win, kind=None, act=None):
    return [c for c in win.bob.canvas.columns if (kind is None or c.kind == kind) and (act is None or c.act == act)]


def _lane_y(q):
    from Bob.Bob_GUI.canvas.canvas import LANE_H, LANE_Y0
    return LANE_Y0 + (q - 1) * LANE_H + LANE_H / 2


def _flux_y():
    from Bob.Bob_GUI.canvas.canvas import FLUX_Y
    return FLUX_Y + 20


def _build(win):
    """FF hold [pi Q3, pi Q5] | Ramp | Dynamics | Measure, built by drops."""
    ph = _cols(win, "placeholder", "prep")[0]
    _new(win, "FFHold", (ph.x + ph.w / 2, _flux_y()))
    ph = _cols(win, "placeholder", "dynamics")[0]
    _new(win, "FFDynamics", (ph.x + ph.w / 2, _flux_y()))
    c0 = _cols(win, "segment")[0]
    _new(win, "FFRamp", (c0.x + c0.w * 0.8, _flux_y()))
    c0 = _cols(win, "segment")[0]
    _new(win, "PiPulse", (c0.x + 20, _lane_y(3)))
    _new(win, "PiPulse", (c0.x + 20, _lane_y(5)))
    _new(win, "Measure", (win.bob.canvas.columns[-1].x + 20, _flux_y()))


# ================================================================== canvas
def test_drops_build_a_sequence(win):
    _build(win)
    seq = win.bob.ctl.seq
    assert [s.TYPE for s in seq.segments] == ["FFHold", "FFRamp", "FFDynamics"]
    assert [s.act for s in seq.segments] == ["prep", "prep", "dynamics"]
    assert [p.fields["qubit"].value for p in seq.pulses] == [3, 5]
    assert all(p.segment_id == seq.segments[0].id for p in seq.pulses)
    assert seq.measure is not None
    assert win.bob.ctl.compiled is not None


def test_pulse_needs_a_segment(win):
    _new(win, "PiPulse", (200, _lane_y(2)))
    assert win.bob.ctl.seq.pulses == []


def test_drag_moves_pulse_and_reorders_segment(win):
    from Bob.Bob_GUI.canvas.canvas import MIME_MOVE
    _build(win)
    ctl = win.bob.ctl
    c0 = _cols(win, "segment")[0]
    _drop(win, MIME_MOVE, {"id": ctl.seq.pulses[1].id, "kind": "pulse"}, (c0.x + 30, _lane_y(6)))
    assert ctl.seq.pulses[1].fields["qubit"].value == 6
    ramp = ctl.seq.segments[1]
    _drop(win, MIME_MOVE, {"id": ramp.id, "kind": "segment"}, (c0.x + 5, _flux_y()))
    assert [s.TYPE for s in ctl.seq.segments] == ["FFRamp", "FFHold", "FFDynamics"]
    assert any(p.field == "start_gains" for p in ctl.problems)       # nothing before the ramp now


def test_delete_key_removes_selected(win, qtbot):
    _build(win)
    ctl = win.bob.ctl
    ctl.select(ctl.seq.segments[0].id)
    qtbot.keyClick(win.bob.canvas, Qt.Key_Delete)
    assert len(ctl.seq.segments) == 2 and ctl.seq.pulses == []


# ================================================================== undo / copy / paste
def test_undo_redo_everything(win):
    _build(win)
    ctl = win.bob.ctl
    n = ctl.undo.count()
    for _ in range(n):
        ctl.undo.undo()
    assert ctl.seq.segments == [] and ctl.seq.measure is None
    for _ in range(n):
        ctl.undo.redo()
    assert [s.TYPE for s in ctl.seq.segments] == ["FFHold", "FFRamp", "FFDynamics"]


def test_copy_paste_with_keys(win, qtbot):
    _build(win)
    ctl, cv = win.bob.ctl, win.bob.canvas
    hold = ctl.seq.segments[0]
    ctl.select(hold.id)
    qtbot.keyClick(cv, Qt.Key_C, Qt.ControlModifier)
    qtbot.keyClick(cv, Qt.Key_V, Qt.ControlModifier)
    assert len(ctl.seq.segments) == 4
    pasted = ctl.seq.segments[1]
    assert pasted.id != hold.id and pasted.TYPE == "FFHold" and len(ctl.seq.pulses_in(pasted.id)) == 2
    assert ctl.selected == pasted.id


def test_paste_pulse_into_selected_segment(win):
    _build(win)
    ctl = win.bob.ctl
    ctl.copy(ctl.seq.pulses[0].id)
    ctl.select(ctl.seq.segments[2].id)
    ctl.paste()
    assert len(ctl.seq.pulses_in(ctl.seq.segments[2].id)) == 1


def test_paste_pulse_without_segment_explains(win, qtbot):
    _build(win)
    ctl = win.bob.ctl
    ctl.copy(ctl.seq.pulses[0].id)
    ctl.select(None)
    with qtbot.waitSignal(ctl.message, timeout=1000) as sig:
        ctl.paste()
    assert "Select a segment" in sig.args[0]


def test_duplicate(win):
    _build(win)
    ctl = win.bob.ctl
    ctl.duplicate(ctl.seq.segments[0].id)
    assert len(ctl.seq.segments) == 4 and len(ctl.seq.pulses) == 4


# ================================================================== inspector
def _select(win, block):
    win.bob.ctl.select(block.id)
    win.bob.ctl.refresh_now()
    return win.bob.inspector.rows


def test_inspector_edit_value(win):
    _build(win)
    hold = win.bob.ctl.seq.segments[0]
    row = _select(win, hold)["duration_us"]
    row.focus_widget.setText("0.5")
    row._scalar_edited(row.focus_widget)
    assert hold.fields["duration_us"] == Value(0.5)


def test_inspector_bad_number_is_not_committed(win):
    _build(win)
    hold = win.bob.ctl.seq.segments[0]
    before = hold.fields["duration_us"]
    row = _select(win, hold)["duration_us"]
    row.focus_widget.setText("abc")
    row._scalar_edited(row.focus_widget)
    assert hold.fields["duration_us"] == before and "number" in row.hint.text()


def test_inspector_switch_to_sweep_creates_axis(win):
    _build(win)
    ctl = win.bob.ctl
    dyn = ctl.seq.segments[2]
    row = _select(win, dyn)["duration_us"]
    i = row.source_combo.findData("sweep")
    row.source_combo.setCurrentIndex(i)
    row._source_changed(i)
    src = ctl.seq.get(dyn.id).fields["duration_us"]
    assert isinstance(src, Sweep) and ctl.seq.settings.axis(src.axis) is not None


def test_inspector_per_channel_override(win):
    _build(win)
    ctl = win.bob.ctl
    dyn = ctl.seq.segments[2]
    row = _select(win, dyn)["gains"]
    row.cells[1].setText("1500")
    row._cell_edited(1, row.cells[1], False)
    assert ctl.seq.get(dyn.id).fields["gains"].overrides == {1: 1500.0}
    ctl.refresh_now()
    assert ctl.resolved.segments[2].params["gains"][1] == 1500.0


def test_inspector_dropdowns_list_calibration_entries(win, calib):
    _build(win)
    ctl = win.bob.ctl
    dyn = ctl.seq.segments[2]
    rows = _select(win, dyn)
    combo = rows["dyn_entry"].focus_widget
    assert isinstance(combo, QComboBox)
    expected = {k for k, br, _ in calib.children("ff_groups/dynamics_groups/dynamics_FF_points") if br}
    assert {combo.itemData(i) for i in range(combo.count())} == expected
    i = combo.findData("swap_5_6")
    combo.setCurrentIndex(i)
    combo.activated.emit(i)
    assert ctl.seq.get(dyn.id).fields["dyn_entry"] == Value("swap_5_6")
    ctl.refresh_now()
    assert ctl.resolved.segments[2].params["gains"] == \
        calib.get("ff_groups/dynamics_groups/dynamics_FF_points/swap_5_6/FF_Dynamics")


def test_pulse_entry_dropdown_has_qubit_number_option(win):
    _build(win)
    rows = _select(win, win.bob.ctl.seq.pulses[0])
    combo = rows["entry"].focus_widget
    assert combo.itemText(0) == "(qubit number)" and combo.itemData(0) == ""


def test_every_visible_field_has_an_info_icon(win):
    from Bob.Bob_GUI.widgets import InfoIcon
    _build(win)
    for block in (win.bob.ctl.seq.segments[1], win.bob.ctl.seq.pulses[0], win.bob.ctl.seq.measure):
        rows = _select(win, block)
        for name, row in rows.items():
            assert row.findChildren(InfoIcon), f"{block.TYPE}.{name} has no info icon"


# ================================================================== problems / status / settings
def test_errors_show_in_problems_and_pill(win):
    _build(win)
    ctl = win.bob.ctl
    ctl.set_field(ctl.seq.pulses[0].id, "freq", Value(9999.0))
    ctl.refresh_now()
    assert "error" in win.bob.topbar.status.text()
    tree = win.bob.problems.tree
    msgs = [tree.topLevelItem(i).text(1) for i in range(tree.topLevelItemCount())]
    assert any("mixer band" in m for m in msgs)
    win.bob.topbar.status.mousePressEvent(None)
    assert win.bob.dock.currentWidget() is win.bob.problems


def test_renaming_an_axis_keeps_fields_pointing_at_it(win):
    win.bob.open_path(str(TEMPLATES / "t1.json"), as_template=True)
    ctl, sp = win.bob.ctl, win.bob.settings_panel
    sp.table.item(0, 0).setText("wait")
    assert ctl.seq.settings.sweeps[0].name == "wait"
    assert ctl.seq.segments[1].fields["duration_us"] == Sweep("wait")


def test_preview_slider_moves_the_sweep_point(win):
    win.bob.open_path(str(TEMPLATES / "t1.json"), as_template=True)
    ctl = win.bob.ctl
    ctl.refresh_now()
    n0 = ctl.compiled.n_samples
    win.bob.preview.slider.setValue(10)
    ctl.refresh_now()
    assert ctl.preview_index == 10 and ctl.compiled.n_samples > n0


# ================================================================== files / look
def test_save_and_reopen(win, tmp_path):
    _build(win)
    ctl = win.bob.ctl
    assert ctl.dirty
    path = tmp_path / "s.json"
    ctl.save(path)
    assert not ctl.dirty
    before = ctl.seq.to_dict()
    win.bob.open_path(str(path))
    assert ctl.seq.to_dict() == before and ctl.doc_path == path


def test_unsaved_changes_prompt_before_new(win, no_modal_dialogs):
    win.bob.new()
    assert no_modal_dialogs == []                                     # nothing to lose yet
    _build(win)
    win.bob.new()
    assert no_modal_dialogs == ["Unsaved changes"] and win.bob.ctl.seq.segments == []


def test_template_opens_as_untitled_copy(win):
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    assert win.bob.ctl.doc_path is None and win.bob.ctl.seq.name == "Mott quench"


def test_no_theme_toggle(win):
    """One look only: the top bar has no light/dark switch."""
    tips = {b.toolTip().lower() for b in win.bob.topbar.findChildren(QPushButton)}
    assert not any("mode" in t or "theme" in t for t in tips)


def test_settings_stay_out_of_the_users_real_ones(win, isolated_settings, tmp_path):
    from Bob.Bob_GUI.app_settings import app_settings
    assert app_settings().fileName() == str(tmp_path / "bob_settings.ini")
    assert win.bob.ctl.settings_store.fileName() == str(tmp_path / "bob_settings.ini")
    win.close()                                                       # writes window geometry
    assert app_settings().value("geometry") is not None


# ================================================================== measure chip / markers / tooltips
def test_qubit_list_text():
    from Bob.Bob_GUI.canvas.describe import qubit_list_text
    assert qubit_list_text([3, 4, 5, 6, 7, 8]) == "Q3–Q8"
    assert qubit_list_text([4, 1, 3]) == "Q1, Q3–Q4"
    assert qubit_list_text([]) == "no qubits"


def test_measure_chip_says_what_is_measured(win):
    from Bob.Bob_GUI.canvas.describe import measure_chip_lines
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    title, group, second = measure_chip_lines(win.bob.ctl.seq)
    assert group == "readout_3800" and second == "Q3–Q8 · P corrected"
    ctl = win.bob.ctl
    ctl.set_field(ctl.seq.measure.id, "mode", Value("iq"))
    assert measure_chip_lines(ctl.seq)[2] == "Q3–Q8 · IQ"


def test_pi2_before_readout_shows_its_phase(win):
    from Bob.Bob_GUI.canvas.describe import readout_rotation
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl = win.bob.ctl
    ctl.refresh_now()
    pulse, text = readout_rotation(ctl.seq, ctl.resolved, 5)
    assert pulse.TYPE == "Pi2Pulse" and text == "0°"
    ctl.set_field(pulse.id, "phase", Value(90.0))
    ctl.refresh_now()
    assert readout_rotation(ctl.seq, ctl.resolved, 5)[1] == "90°"
    ctl.add_sweep_axis("phi", 0, 180, 5, "deg")
    ctl.set_field(pulse.id, "phase", Sweep("phi"))
    ctl.refresh_now()
    assert readout_rotation(ctl.seq, ctl.resolved, 5)[1] == "‹phi›"


def test_no_basis_tag_when_pi_pulses_are_only_in_prep(win):
    from Bob.Bob_GUI.canvas.describe import readout_rotation
    win.bob.open_path(str(TEMPLATES / "bs_correlations.json"), as_template=True)
    ctl = win.bob.ctl
    ctl.refresh_now()
    assert all(readout_rotation(ctl.seq, ctl.resolved, q) is None for q in range(1, 9))


def test_tooltips_show_resolved_values(win, calib):
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl, cv = win.bob.ctl, win.bob.canvas
    ctl.refresh_now()
    cv._relayout()
    pulse, rect = cv.pulse_rects()[0]
    tip = cv.tooltip_at(rect.center())
    q = pulse.fields["qubit"].value
    freq = calib.get(f"drive_groups/readout_3800/entries/{q}/Qubit/Frequency")
    assert pulse.name in tip and f"{freq:.6g} MHz" in tip and "entries/" in tip and "Plays" in tip
    col = cv.column_for(ctl.seq.measure.id)
    lane_tip = cv.tooltip_at(cv.measure_marker_rect(col, 5).center())
    assert lane_tip.startswith("<b>Q5</b>") and "π/2" in lane_tip and "MHz" in lane_tip
    chip_tip = cv.tooltip_at(cv.flux_rect(col).center())
    assert "Readout MHz" in chip_tip and "Q3–Q8" in chip_tip


# ================================================================== problems tab count
def test_problems_tab_counts_errors_and_warnings(win):
    _build(win)
    ctl, dock = win.bob.ctl, win.bob.dock
    i = dock.indexOf(win.bob.problems)
    assert dock.tabText(i) == "Problems"
    ctl.set_field(ctl.seq.pulses[0].id, "freq", Value(9999.0))
    ctl.refresh_now()
    assert dock.tabText(i) == "Problems (1)" and "1 error" in dock.tabToolTip(i)
    ctl.undo.undo()
    ctl.refresh_now()
    assert dock.tabText(i) == "Problems"


# ================================================================== calibration changed since save
def test_calibration_change_since_save_warns_until_saved_again(win, tmp_path):
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures" / "qubit_parameters.json"
    ctl = win.bob.ctl
    old = tmp_path / "old.json"
    old.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["drive_groups"]["readout_3800"]["entries"]["3"]["Qubit"]["Frequency"] += 2.5
    new = tmp_path / "new.json"
    new.write_text(json.dumps(data))

    ctl.set_calibration(str(old))
    _build(win)
    seq_path = tmp_path / "s.json"
    ctl.save(seq_path)
    assert "used" in json.loads(seq_path.read_text(encoding="utf-8"))["calibration"]

    ctl.set_calibration(str(new))                       # Q3's frequency was recalibrated
    ctl.refresh_now()
    drift = [p for p in ctl.problems if p.message.startswith("Calibration changed")]
    assert len(drift) == 1 and drift[0].block_id == ctl.seq.pulses[0].id
    assert "entries/3/Qubit/Frequency: 3695 → 3697.5" in drift[0].message
    assert ctl.worst_level(ctl.seq.pulses[0].id) == "warning"

    ctl.save(seq_path)                                  # saving accepts the new values
    ctl.refresh_now()
    assert not any(p.message.startswith("Calibration changed") for p in ctl.problems)


def test_opening_after_recalibration_says_so(win, tmp_path, qtbot):
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures" / "qubit_parameters.json"
    ctl = win.bob.ctl
    _build(win)
    seq_path = tmp_path / "s.json"
    ctl.save(seq_path)
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["drive_groups"]["readout_3800"]["FF_Readouts"][0] += 50
    new = tmp_path / "new.json"
    new.write_text(json.dumps(data))
    ctl.set_calibration(str(new))
    with qtbot.waitSignal(ctl.message, timeout=1000) as sig:
        win.bob.open_path(str(seq_path))
    assert "Calibration changed" in sig.args[0] and "See Problems" in sig.args[0]
    assert any("FF_Readouts: Q1" in p.message for p in ctl.problems)


def test_templates_and_new_sequences_never_warn(win):
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    win.bob.ctl.refresh_now()
    assert win.bob.ctl.calib_baseline is None
    assert not any(p.message.startswith("Calibration changed") for p in win.bob.ctl.problems)


# ================================================================== chip markings
def test_legend_explains_the_markings(win):
    assert "calibration" in win.bob.legend.text() and "swept" in win.bob.legend.text()
    assert "Hover a dot or triangle" in win.bob.legend.toolTip()


def test_hovering_a_badge_names_its_fields(win):
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl, cv = win.bob.ctl, win.bob.canvas
    ctl.refresh_now()
    cv._relayout()
    quench = next(s for s in ctl.seq.segments if s.name == "Quench")
    badges = dict(cv.badge_rects(cv.column_for(quench.id)))
    assert set(badges) == {"ref", "sweep"}
    sweep_tip = cv.tooltip_at(badges["sweep"].center())
    assert "swept" in sweep_tip and "‹t_dyn›" in sweep_tip and "Duration" in sweep_tip
    ref_tip = cv.tooltip_at(badges["ref"].center())
    assert "calibration" in ref_tip and "FF gains" in ref_tip and "calib:ff_groups/" in ref_tip


def test_hovering_a_swept_pulse_badge(win):
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl, cv = win.bob.ctl, win.bob.canvas
    pulse = ctl.seq.pulses[-1]
    ctl.add_sweep_axis("phi", 0, 180, 5, "deg")
    ctl.set_field(pulse.id, "phase", Sweep("phi"))
    ctl.refresh_now()
    cv._relayout()
    rect = dict((b.id, r) for b, r in cv.pulse_rects())[pulse.id]
    tip = cv.tooltip_at(cv.pulse_sweep_badge_rect(rect).center())
    assert "Phase" in tip and "‹phi›" in tip


# ================================================================== prepared state / summary
def test_state_column_after_preparation(win):
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl, cv = win.bob.ctl, win.bob.canvas
    ctl.refresh_now()
    cv._relayout()
    kinds = [c.kind for c in cv.columns]
    assert kinds.index("state") == kinds.index("segment") + 1          # right after Init
    col = next(c for c in cv.columns if c.kind == "state")
    tip = cv.tooltip_at(cv.state_marker_rect(col, 6).center())
    assert "Q6" in tip and "superposition" in tip and "P(1) = 0.50" in tip


def test_no_state_column_without_prep_pulses(win):
    _build(win)
    ctl, cv = win.bob.ctl, win.bob.canvas
    for p in list(ctl.seq.pulses):
        ctl.remove(p.id)
    ctl.refresh_now()
    cv._relayout()
    assert "state" not in [c.kind for c in cv.columns]


def test_segment_dropped_on_state_column_ends_preparation(win):
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl, cv = win.bob.ctl, win.bob.canvas
    ctl.refresh_now()
    cv._relayout()
    col = next(c for c in cv.columns if c.kind == "state")
    _new(win, "FFHold", (col.x + 5, _flux_y()))
    assert [s.act for s in ctl.seq.segments[:2]] == ["prep", "prep"] and ctl.seq.segments[1].TYPE == "FFHold"


def test_save_writes_the_summary(win, tmp_path):
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl = win.bob.ctl
    path = tmp_path / "m.json"
    ctl.save(path)
    saved = json.loads(path.read_text(encoding="utf-8"))["summary"]
    assert saved.startswith("Mott quench:") and "Prepared state 00111+11" in saved
    ctl.refresh_now()
    assert win.bob.settings_panel.summary.text() == saved


# ================================================================== export as Python
def test_export_button_writes_a_script(win, tmp_path):
    assert "Export" in win.bob.topbar.export_btn.toolTip()
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    path = tmp_path / "mott.py"
    assert win.bob.export_python_to(path)
    text = path.read_text(encoding="utf-8")
    assert "HOW TO RUN" in text and "python mott.py --run" in text and "SEQUENCE = {" in text


def test_export_with_errors_explains_and_writes_nothing(win, tmp_path, no_modal_dialogs):
    _build(win)
    ctl = win.bob.ctl
    ctl.set_field(ctl.seq.pulses[0].id, "freq", Value(9999.0))
    assert not win.bob.export_python_to(tmp_path / "bad.py")
    assert no_modal_dialogs == ["Cannot export"] and not (tmp_path / "bad.py").exists()


# ================================================================== window size
def test_window_fits_a_laptop_screen(win):
    """The minimum size must fit a 13-inch laptop (about 1280 x 720 usable) with room to spare."""
    hint = win.minimumSizeHint()
    assert hint.width() <= 1100 and hint.height() <= 600, (hint.width(), hint.height())


def test_window_opens_within_the_screen(win):
    avail = win.screen().availableGeometry()
    win.resize(5000, 5000)
    win.fit_to_screen()
    assert win.frameGeometry().width() <= max(avail.width(), win.minimumSizeHint().width() + 50)
    assert win.frameGeometry().height() <= avail.height()


def test_long_names_do_not_widen_the_window(win):
    before = win.minimumSizeHint().width()
    win.bob.ctl.set_settings(win.bob.ctl.seq.settings, name="A very long experiment name " * 10)
    win.bob._update_title()
    assert win.minimumSizeHint().width() <= before


# ================================================================== renaming the sequence
def _click_title(win, qtbot):
    title = win.bob.topbar.title
    qtbot.mouseClick(title, Qt.LeftButton, pos=title.label.geometry().center())
    return title


def test_click_title_to_rename(win, qtbot):
    ctl, sp = win.bob.ctl, win.bob.settings_panel
    title = _click_title(win, qtbot)
    assert title.edit.isVisible() and title.edit.text() == ctl.seq.name
    title.edit.setText("Quench run 7")
    qtbot.keyClick(title.edit, Qt.Key_Return)
    assert ctl.seq.name == "Quench run 7" and not title.edit.isVisible()
    assert title.label.text().startswith("Quench run 7") and sp.name.text() == "Quench run 7"
    ctl.undo.undo()                                      # one undo step reverts it everywhere
    assert ctl.seq.name != "Quench run 7" and not title.label.text().startswith("Quench run 7")
    assert sp.name.text() == ctl.seq.name


def test_escape_cancels_the_rename(win, qtbot):
    ctl = win.bob.ctl
    before = ctl.seq.name
    title = _click_title(win, qtbot)
    title.edit.setText("Not this")
    qtbot.keyClick(title.edit, Qt.Key_Escape)
    assert ctl.seq.name == before and not title.edit.isVisible() and ctl.undo.count() == 0


def test_rename_in_experiment_tab_updates_the_title(win):
    sp, title = win.bob.settings_panel, win.bob.topbar.title
    sp.name.setText("From the tab")
    sp._rename()
    assert win.bob.ctl.seq.name == "From the tab" and title.label.text().startswith("From the tab")


def test_empty_name_is_rejected(win, qtbot):
    ctl, sp = win.bob.ctl, win.bob.settings_panel
    before = ctl.seq.name
    title = _click_title(win, qtbot)
    title.edit.setText("   ")
    qtbot.keyClick(title.edit, Qt.Key_Return)
    sp.name.setText("")
    sp._rename()
    assert ctl.seq.name == before and sp.name.text() == before


# ================================================================== regressions from the bug hunt
def test_deleting_a_segment_clears_a_selected_pulse_in_it(win):
    _build(win)
    ctl = win.bob.ctl
    pulse = ctl.seq.pulses[0]
    ctl.select(pulse.id)
    ctl.remove(pulse.segment_id)
    assert ctl.selected is None and win.bob.inspector._block_id is None


def test_failed_save_is_reported_and_nothing_is_lost(win, tmp_path, no_modal_dialogs):
    from pathlib import Path
    _build(win)
    win.bob.ctl.doc_path = Path(tmp_path / "missing_folder" / "seq.json")
    assert win.bob.save() is False
    assert no_modal_dialogs == ["Could not save"] and win.bob.ctl.dirty


def test_closing_keeps_the_window_open_when_saving_fails(win, tmp_path, monkeypatch):
    from pathlib import Path
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Save))
    _build(win)
    win.bob.ctl.doc_path = Path(tmp_path / "missing_folder" / "seq.json")
    win.close()
    assert win.isVisible()


def test_failed_export_is_reported(win, tmp_path, no_modal_dialogs):
    win.bob.open_path(str(TEMPLATES / "t1.json"), as_template=True)
    assert not win.bob.export_python_to(tmp_path / "missing_folder" / "x.py")
    assert no_modal_dialogs == ["Cannot export"]


def test_saving_a_preset_asks_before_replacing_one(win, tmp_path, no_modal_dialogs, monkeypatch):
    from PyQt5.QtWidgets import QInputDialog
    import Bob.Bob_GUI.bob_widget as bw
    (tmp_path / "presets").mkdir()
    existing = tmp_path / "presets" / "pi_q3.json"
    existing.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(bw, "LIB", tmp_path)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("pi Q3", True)))
    _build(win)
    win.bob.save_preset(win.bob.ctl.seq.pulses[0].id)
    assert "Replace preset?" in no_modal_dialogs and existing.read_text(encoding="utf-8") == "{}"


def test_invalid_relax_delay_is_flagged_and_other_fields_still_apply(win):
    win.bob.open_path(str(TEMPLATES / "t1.json"), as_template=True)
    ctl, sp = win.bob.ctl, win.bob.settings_panel
    sp.relax.setText("abc")
    sp._commit_relax()
    assert sp.relax.objectName() == "bad" and sp.error.isVisibleTo(sp) and "Relax delay" in sp.error.text()
    assert ctl.seq.settings.relax_delay_us is None
    sp.desc.setText("still saved")
    sp._commit_description()
    sp.reps.setValue(77)
    sp._commit_counts()
    assert ctl.seq.description == "still saved" and ctl.seq.settings.reps == 77


def test_invalid_sweep_cell_is_explained_and_reverted(win):
    win.bob.open_path(str(TEMPLATES / "t1.json"), as_template=True)
    ctl, sp = win.bob.ctl, win.bob.settings_panel
    sp.table.item(0, 1).setText("zero")
    assert sp.table.item(0, 1).text() == "0" and "not a number" in sp.error.text()
    sp.table.item(0, 3).setText("40")
    assert ctl.seq.settings.sweeps[0].points == 40 and not sp.error.isVisibleTo(sp)


def test_two_axes_cannot_share_a_name(win):
    win.bob.open_path(str(TEMPLATES / "t1.json"), as_template=True)
    ctl, sp = win.bob.ctl, win.bob.settings_panel
    ctl.add_sweep_axis("other", 0, 1, 3)
    sp.table.item(1, 0).setText("t_wait")
    assert [a.name for a in ctl.seq.settings.sweeps] == ["t_wait", "other"] and "already called" in sp.error.text()


def test_sweep_axis_checks(station, calib, basic_seq):
    from Bob.compiler.tlq_backend import compile_sequence
    from Bob.config.settings import SweepAxis
    basic_seq.settings.sweeps = [SweepAxis("I", 0, 1, 2), SweepAxis("t", 0, 1, 2), SweepAxis("t", 0, 1, 2)]
    _, _, problems = compile_sequence(basic_seq, station, calib)
    errors = " ".join(p.message for p in problems if p.level == "error")
    assert "same name as a saved data set" in errors and "Two sweep axes are called ‹t›" in errors
    basic_seq.settings.sweeps = [SweepAxis(f"a{k}", 0, 1, 100) for k in range(4)]
    _, _, problems = compile_sequence(basic_seq, station, calib)
    assert any("100,000,000 points" in p.message for p in problems)


def test_huge_sweep_does_not_crash_the_preview(win):
    from Bob.config.settings import ExperimentSettings, SweepAxis
    ctl = win.bob.ctl
    ctl.set_settings(ExperimentSettings(sweeps=[SweepAxis(f"a{k}", 0, 1, 1000) for k in range(4)]))
    ctl.refresh_now()                              # 10^12 points: an error, not a crash
    assert any("points" in p.message and p.level == "error" for p in ctl.problems)


def test_switching_to_sweep_is_one_undo_step(win):
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl = win.bob.ctl
    from Bob.config.settings import ExperimentSettings
    ctl.set_settings(ExperimentSettings())
    seg = ctl.seq.segments[0]
    row = _select(win, seg)["duration_us"]
    before = ctl.seq.to_dict()
    i = row.source_combo.findData("sweep")
    row.source_combo.setCurrentIndex(i)
    row._source_changed(i)
    assert isinstance(ctl.seq.get(seg.id).fields["duration_us"], Sweep) and ctl.seq.settings.sweeps
    ctl.undo.undo()
    assert ctl.seq.to_dict() == before


def test_empty_block_name_is_put_back(win):
    from PyQt5.QtWidgets import QLineEdit
    _build(win)
    b = win.bob.ctl.seq.segments[0]
    _select(win, b)
    edit = next(e for e in win.bob.inspector.findChildren(QLineEdit) if e.text() == b.name)
    edit.setText("")
    edit.editingFinished.emit()
    assert edit.text() == b.name == win.bob.ctl.seq.get(b.id).name


def test_unknown_station_in_a_file_is_flagged(win, tmp_path):
    _build(win)
    path = tmp_path / "s.json"
    win.bob.ctl.save(path)
    d = json.loads(path.read_text(encoding="utf-8"))
    d["station"] = "8QV2"
    path.write_text(json.dumps(d))
    win.bob.open_path(str(path))
    win.bob.ctl.refresh_now()
    assert any("made for station '8QV2'" in p.message for p in win.bob.ctl.problems)


def test_export_makes_waveform_file_paths_absolute(win, tmp_path, monkeypatch):
    import numpy as np
    monkeypatch.chdir(tmp_path)
    np.save("wave.npy", np.zeros((8, 3440)))
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl = win.bob.ctl
    dyn = ctl.seq.segments[1]
    ctl.set_field(dyn.id, "mode", Value("file"))
    ctl.set_field(dyn.id, "waveform_file", Value("wave.npy"))
    out = tmp_path / "m.py"
    assert win.bob.export_python_to(out)
    text = out.read_text(encoding="utf-8")
    assert str(tmp_path / "wave.npy") in text and "keep them where they are" in text


def test_unexpected_errors_are_shown_not_fatal(win, monkeypatch):
    import sys
    from PyQt5.QtWidgets import QMessageBox
    from Bob.Bob_GUI.app import install_error_handler
    shown = []
    monkeypatch.setattr(QMessageBox, "exec_", lambda self: shown.append(self.text()) or 0)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    install_error_handler(win)
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
        sys.excepthook(*sys.exc_info())          # the same error again right away is not shown twice
    assert len(shown) == 1 and "RuntimeError: boom" in shown[0] and "still open" in shown[0]


# ================================================================== dropdowns
def test_dropdowns_open_as_a_normal_list(win):
    """Not the macOS menu-style popup, which with a stylesheet shows one row with scroll arrows."""
    from PyQt5.QtWidgets import QStyle, QStyleOptionComboBox
    from Bob.Bob_GUI.widgets import Dropdown
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl = win.bob.ctl
    ctl.select(ctl.seq.segments[1].id)
    ctl.refresh_now()
    combos = win.findChildren(QComboBox)
    assert combos and all(isinstance(c, Dropdown) for c in combos)
    for c in combos:
        opt = QStyleOptionComboBox()
        c.initStyleOption(opt)
        assert c.style().styleHint(QStyle.SH_ComboBox_Popup, opt, c) == 0
        assert c.maxVisibleItems() >= 15


# ================================================================== sweeps: one axis, edited from either place
def _mott(win):
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    ctl = win.bob.ctl
    quench = next(s for s in ctl.seq.segments if s.name == "Quench")
    return ctl, quench


def test_inspector_shows_and_edits_the_swept_axis(win):
    ctl, quench = _mott(win)
    row = _select(win, quench)["duration_us"]
    assert row.axis_combo.currentData() == "t_dyn"
    assert [row.axis_edits[k].text() for k in ("start", "stop", "points")] == ["0", "2.3251", "401"]
    assert "401 points runs the whole sequence 500 times" in row.axis_note.text()
    row.axis_edits["stop"].setText("3")
    row._axis_edited("stop", row.axis_edits["stop"])
    assert ctl.seq.settings.axis("t_dyn").stop == 3.0
    assert win.bob.settings_panel.table.item(0, 2).text() == "3"          # same axis in the Experiment tab
    ctl.undo.undo()
    row = win.bob.inspector.rows["duration_us"]
    assert ctl.seq.settings.axis("t_dyn").stop == 2.3251 and row.axis_edits["stop"].text() == "2.3251"


def test_experiment_tab_edits_show_in_the_inspector(win):
    ctl, quench = _mott(win)
    _select(win, quench)
    win.bob.settings_panel.table.item(0, 3).setText("51")
    row = win.bob.inspector.rows["duration_us"]
    assert row.axis_edits["points"].text() == "51" and "51 points" in row.axis_note.text()


def test_inspector_rejects_a_bad_axis_entry(win):
    ctl, quench = _mott(win)
    row = _select(win, quench)["duration_us"]
    row.axis_edits["points"].setText("0")
    row._axis_edited("points", row.axis_edits["points"])
    assert ctl.seq.settings.axis("t_dyn").points == 401 and "at least 1" in row.hint.text()
    assert row.axis_edits["points"].text() == "401"


def test_inspector_lists_other_fields_on_the_same_axis(win):
    ctl, quench = _mott(win)
    init = next(s for s in ctl.seq.segments if s.name == "Init")
    ctl.set_field(init.id, "duration_us", Sweep("t_dyn"))
    row = _select(win, quench)["duration_us"]
    assert "Also follows ‹t_dyn›: Init › Duration" in row.axis_note.text()


def test_two_axes_explain_the_loop_order(win):
    ctl, quench = _mott(win)
    ctl.add_sweep_axis("phi", 0, 180, 5, "deg")
    row = _select(win, quench)["duration_us"]
    assert "Loop 1 of 2 (outermost)" in row.axis_note.text() and "2,005 points" in row.axis_note.text()
    assert win.bob.settings_panel.total.text().startswith("401 × 5 = 2,005 points")


def test_new_axis_stays_in_the_inspector(win):
    ctl, quench = _mott(win)
    win.bob.dock.setCurrentIndex(0)
    row = _select(win, quench)["duration_us"]
    row._axis_chosen("__new__")
    assert win.bob.dock.currentIndex() == 0
    row = win.bob.inspector.rows["duration_us"]
    assert row.axis_combo.currentData() == "duration" and row.axis_edits["points"].text() == "21"


def test_experiment_tab_shows_swept_fields_and_guards_removal(win):
    ctl, quench = _mott(win)
    sp = win.bob.settings_panel
    assert sp.table.item(0, 5).text() == "Quench › Duration"
    sp.table.setCurrentCell(0, 0)
    sp._remove()
    assert ctl.seq.settings.axis("t_dyn") is not None and "still swept by Quench › Duration" in sp.error.text()
    ctl.add_sweep_axis("spare", 0, 1, 3)
    assert sp.table.item(1, 5).text() == "none yet"
    sp.table.setCurrentCell(1, 0)
    sp._remove()
    assert ctl.seq.settings.axis("spare") is None and not sp.error.isVisibleTo(sp)


# ================================================================== runs and the Data tab (stand-in board)
@pytest.fixture
def board(win, monkeypatch, tmp_path):
    """Pretend the station is verified and plug in the stand-in board; runs save under tmp_path."""
    from Bob.runner import script
    from Bob.tests.test_runs import Oscillating
    monkeypatch.setattr(script, "hardware_ready", lambda station: [])
    calls = []
    win.bob.connect_rfsoc = lambda station: (calls.append(1), (object(), object()))[1]
    win.bob.program_class = Oscillating
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    from Bob.config.settings import SweepAxis
    st = win.bob.ctl.seq.settings
    new = type(st).from_dict(st.to_dict())
    new.sweeps = [SweepAxis("t_dyn", 0.0, 2.3251, 9, "µs")]
    new.reps, new.save_folder = 50, str(tmp_path)
    win.bob.ctl.set_settings(new)
    win.bob.ctl.refresh_now()
    win.bob._update_run_button()
    return calls


def _run_and_wait(win, qtbot):
    win.bob.run()
    qtbot.waitUntil(lambda: win.bob._run is None, timeout=20000)


def test_run_button_explains_why_it_is_off(win):
    win.bob.open_path(str(TEMPLATES / "t1.json"), as_template=True)
    win.bob.ctl.refresh_now()
    btn = win.bob.topbar.run_btn
    assert not btn.isEnabled() and "hardware_verified" in btn.toolTip()


def test_run_streams_into_the_data_tab_and_saves(win, qtbot, board, tmp_path):
    from Bob.runner.save import load_run
    assert win.bob.topbar.run_btn.isEnabled()
    _run_and_wait(win, qtbot)
    dp = win.bob.data_panel
    assert win.bob.dock.currentWidget() is dp and len(dp.records) == 1
    rec = dp.records[0]
    assert rec.status == "complete" and rec.done == 9 and rec.path.endswith("_data.h5")
    assert rec.path.startswith(str(tmp_path))
    saved = load_run(rec.path)["data"]["population_corrected"]
    assert np.allclose(dp.shown_values(), saved)
    xs, ys = dp._items[2].getData()
    assert np.allclose(ys, saved[2])
    assert "9 of 9 points" in dp.status.text() and "saved" in dp.history.chip(0).text()
    assert win.bob.topbar.run_btn.isEnabled() and win.bob.topbar.run_btn.text() == " Run"


def test_reruns_go_into_the_history_bar(win, qtbot, board):
    dp = win.bob.data_panel
    _run_and_wait(win, qtbot)
    first = dp.records[0]
    st = win.bob.ctl.seq.settings
    new = type(st).from_dict(st.to_dict())
    new.sweeps[0].points = 5
    win.bob.ctl.set_settings(new)
    win.bob.ctl.refresh_now()
    _run_and_wait(win, qtbot)
    assert [r.total for r in dp.records] == [5, 9] and dp.history.count() == 2
    assert dp.current is dp.records[0]
    dp.history.chip(1).click()                        # click the older run
    assert dp.history.chip(1).isChecked() and not dp.history.chip(0).isChecked()
    assert dp.current is first and dp.shown_values().shape == (6, 9)


def test_stop_keeps_what_was_measured(win, qtbot, board):
    import time
    from Bob.runner.save import load_run
    from Bob.tests.test_runs import Oscillating

    class Slow(Oscillating):
        def acquire_shots(self, soc, rounds=1, progress=False):
            time.sleep(0.15)
            return super().acquire_shots(soc, rounds, progress)
    win.bob.program_class = Slow
    win.bob.run()
    dp = win.bob.data_panel
    qtbot.waitUntil(lambda: dp.records[0].done >= 2, timeout=10000)
    assert dp.stop_btn.isVisibleTo(dp) and not win.bob.topbar.run_btn.isEnabled()
    dp.stop_btn.click()
    qtbot.waitUntil(lambda: win.bob._run is None, timeout=10000)
    rec = dp.records[0]
    assert rec.status.startswith("stopped after") and rec.done < 9
    run = load_run(rec.path)
    assert run["status"] == rec.status and run["points_done"] == rec.done
    assert np.isnan(run["data"]["population_corrected"][:, rec.done:]).all()


def test_open_data_shows_a_saved_run(win, qtbot, board):
    dp = win.bob.data_panel
    _run_and_wait(win, qtbot)
    path = dp.records[0].path
    rec = dp.open_path(path)
    assert dp.history.count() == 2 and dp.current is rec and "opened" in dp.history.chip(0).text()
    assert np.allclose(dp.shown_values(), dp.records[1].data["population_corrected"])


def test_unwritable_save_folder_stops_before_connecting(win, qtbot, board, tmp_path):
    blocker = tmp_path / "a_file"
    blocker.write_text("not a folder", encoding="utf-8")
    st = win.bob.ctl.seq.settings
    new = type(st).from_dict(st.to_dict())
    new.save_folder = str(blocker)
    win.bob.ctl.set_settings(new)
    _run_and_wait(win, qtbot)
    rec = win.bob.data_panel.records[0]
    assert rec.status.startswith("not started: cannot save") and board == []


def test_save_folder_field(win, tmp_path):
    sp = win.bob.settings_panel
    sp.save_folder.setText(str(tmp_path))
    sp._commit_save_folder()
    ctl = win.bob.ctl
    assert ctl.seq.settings.save_folder == str(tmp_path) and str(tmp_path) in sp.save_hint.text()
    ctl.undo.undo()
    assert ctl.seq.settings.save_folder == "" and sp.save_folder.text() == ""
    assert ctl.station["outer_folder"].rstrip("\\") in sp.save_hint.text()


def test_history_bar_scrolls_when_full_and_keeps_its_size(win, qtbot, board):
    from PyQt5.QtCore import QPoint, QPointF
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtWidgets import QApplication
    dp = win.bob.data_panel
    win.bob.dock.setCurrentWidget(dp)
    _run_and_wait(win, qtbot)
    height = dp.history.height()
    for _ in range(14):
        dp.open_path(dp.records[-1].path)
    bar = dp.history.area.horizontalScrollBar()
    qtbot.waitUntil(lambda: bar.maximum() > 0, timeout=3000)     # 15 chips don't fit: it scrolls
    assert dp.history.count() == 15 and bar.value() == 0
    assert dp.history.height() == height                        # the track never grows; it scrolls
    vp = dp.history.area.viewport()
    wheel = QWheelEvent(QPointF(10, 10), QPointF(vp.mapToGlobal(QPoint(10, 10))), QPoint(0, 0), QPoint(0, -240),
                        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(vp, wheel)
    assert bar.value() > 0                                       # a plain mouse wheel scrolls sideways
    dp.history.chip(14).click()
    assert dp.current is dp.records[14]


def test_simulate_runs_without_a_verified_station(win, qtbot, tmp_path):
    from Bob.config.settings import SweepAxis
    from Bob.runner.save import load_run
    win.bob.open_path(str(TEMPLATES / "mott_quench.json"), as_template=True)
    st = win.bob.ctl.seq.settings
    new = type(st).from_dict(st.to_dict())
    new.sweeps = [SweepAxis("t_dyn", 0.0, 2.3251, 7, "µs")]
    new.reps, new.save_folder = 50, str(tmp_path)
    win.bob.ctl.set_settings(new)
    win.bob.ctl.refresh_now()
    tb = win.bob.topbar
    assert not tb.run_btn.isEnabled()                              # the real station is not verified
    tb.sim_btn.setChecked(True)
    assert tb.run_btn.isEnabled() and tb.run_btn.text() == " Run simulated"
    win.bob.connect_rfsoc = lambda st: pytest.fail("a simulated run must not connect to the RFSoC")
    win.bob.run()
    assert not tb.sim_btn.isEnabled()                              # can't switch mode mid-run
    qtbot.waitUntil(lambda: win.bob._run is None, timeout=20000)
    rec = win.bob.data_panel.records[0]
    assert rec.simulated and rec.status == "complete" and "/_simulated/" in rec.path.replace("\\", "/")
    assert "simulated" in win.bob.data_panel.history.chip(0).text()
    assert win.bob.data_panel.status.text().startswith("Simulated data")
    assert load_run(rec.path)["simulated"] and tb.sim_btn.isEnabled()
    tb.sim_btn.setChecked(False)
    assert not tb.run_btn.isEnabled() and tb.run_btn.text() == " Run"


def test_a_changed_board_config_is_flagged(win, qtbot, board, monkeypatch):
    from Bob.Bob_GUI import run_worker
    monkeypatch.setattr(run_worker, "check_board_config",
                        lambda station, text: "DIFFERS from the station's saved board config (x): firmware?")
    _run_and_wait(win, qtbot)
    dp = win.bob.data_panel
    assert dp.records[0].note == "board config differs from the station's saved board config"
    assert "board config differs" in dp.status.text()
