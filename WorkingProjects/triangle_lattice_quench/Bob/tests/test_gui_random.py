"""Random editing sessions in the real window, checking after every step that everything agrees.

Each step does one random thing a user can do (add, delete, move, paste, rename, sweep, undo,
redo, save and reopen, edit in the Experiment tab or the title). After each step the checks
below compare every panel with the sequence itself, and the sequence with its saved form.
Fixed seeds keep it repeatable; a failure names the seed, step and action.
"""
import os
import random
import traceback

import pytest

pytest.importorskip("pytestqt")
pytestmark = pytest.mark.gui

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from Bob.config.settings import ExperimentSettings  # noqa: E402
from Bob.core.params import Sweep, Value  # noqa: E402
from Bob.core.sequence import Sequence  # noqa: E402

SEG_TYPES = ["FFHold", "FFRamp", "FFDynamics", "Beamsplitter"]
PULSE_TYPES = ["PiPulse", "Pi2Pulse", "Drive"]
ACTS = ["prep", "dynamics", "readout"]


def check(w, step, op):
    ctl, bob = w.bob.ctl, w.bob
    ctl.refresh_now()
    QApplication.processEvents()
    seq = ctl.seq
    d = seq.to_dict()
    problems = []
    if Sequence.from_dict(d).to_dict() != d:
        problems.append("save/load round trip changes the sequence")
    ids = [b.id for b in seq.blocks()]
    if len(ids) != len(set(ids)):
        problems.append(f"duplicate block ids {ids}")
    seg_ids = {s.id for s in seq.segments}
    for p in seq.pulses:
        if p.segment_id not in seg_ids:
            problems.append(f"pulse {p.name} points at missing segment")
    if ctl.selected is not None and seq.get(ctl.selected) is None:
        problems.append("selection points at a deleted block")
    sp = bob.settings_panel
    if not sp.name.hasFocus() and sp.name.text() != seq.name:
        problems.append(f"Experiment tab name {sp.name.text()!r} != {seq.name!r}")
    if sp.reps.value() != seq.settings.reps:
        problems.append(f"Experiment tab reps {sp.reps.value()} != {seq.settings.reps}")
    if sp.rounds.value() != seq.settings.rounds:
        problems.append("Experiment tab rounds out of date")
    names = [sp.table.item(r, 0).text() if sp.table.item(r, 0) else None for r in range(sp.table.rowCount())]
    if names != [a.name for a in seq.settings.sweeps]:
        problems.append(f"sweep table {names} != {[a.name for a in seq.settings.sweeps]}")
    if not sp.desc.hasFocus() and sp.desc.text() != seq.description:
        problems.append("Experiment tab description out of date")
    title = bob.topbar.title
    if not title.name == seq.name or not title.label.text().startswith(seq.name):
        problems.append(f"title {title.label.text()!r} vs name {seq.name!r}")
    if title.label.text().endswith("•") != ctl.dirty:
        problems.append(f"dirty dot shows {title.label.text().endswith('•')} but dirty={ctl.dirty}")
    cols = bob.canvas.columns
    if sum(c.kind == "segment" for c in cols) != len(seq.segments):
        problems.append("canvas segment columns != segments")
    mcol = [c for c in cols if c.kind == "measure"]
    if (mcol[0].block_id if mcol else None) != (seq.measure.id if seq.measure else None):
        problems.append("canvas measure column out of date")
    insp = bob.inspector
    if insp._block_id != ctl.selected:
        problems.append(f"inspector shows {insp._block_id} but selection is {ctl.selected}")
    if ctl.selected is not None and seq.get(ctl.selected) is not None:
        b = seq.get(ctl.selected)
        if set(insp.rows) - {f.name for f in b.FIELDS}:
            problems.append("inspector rows belong to another block type")
        if insp._block_snapshot != b.to_dict():
            problems.append("inspector built from an old version of the block")
    if bob.problems.tree.topLevelItemCount() != len(ctl.problems):
        problems.append("problems list out of date")
    n_pts = seq.settings.n_points()
    if bob.preview.slider.maximum() != max(0, n_pts - 1):
        problems.append(f"preview slider max {bob.preview.slider.maximum()} vs {n_pts - 1} points")
    if not 0 <= ctl.preview_index < n_pts:
        problems.append(f"preview index {ctl.preview_index} outside {n_pts} points")
    n_err = sum(p.level == "error" for p in ctl.problems)
    n_warn = sum(p.level == "warning" for p in ctl.problems)
    tab = bob.dock.tabText(bob.dock.indexOf(bob.problems))
    want = f"Problems ({n_err + n_warn})" if n_err + n_warn else "Problems"
    if tab != want:
        problems.append(f"problems tab {tab!r} want {want!r}")
    return [f"step {step} ({op}): {p}" for p in problems]


def rand_block(seq, rng, kinds=("segment", "pulse", "measure")):
    pool = [b for b in seq.blocks() if b.KIND in kinds]
    return rng.choice(pool) if pool else None


def one_run(MainWindow, seed, n_steps, tmp):
    rng = random.Random(seed)
    w = MainWindow()
    w.resize(1300, 800)
    w.show()
    ctl = w.bob.ctl
    ctl.new_sequence()
    found = []
    for step in range(n_steps):
        seq = ctl.seq
        op = rng.choice(["add_seg", "add_seg", "add_pulse", "add_pulse", "add_measure", "remove", "duplicate",
                         "move_seg", "move_pulse", "set_duration", "sweep_duration", "set_qubit", "rename_block",
                         "set_name", "set_act", "add_axis", "set_reps", "rename_axis", "remove_axis", "copy_paste",
                         "undo", "undo", "redo", "select", "preview", "save_reopen", "ui_rename_title",
                         "ui_settings_name", "ui_desc", "ui_reps", "ui_scalar_edit", "set_station_calib"])
        try:
            if op == "add_seg":
                ctl.add_block(rng.choice(SEG_TYPES), index=rng.randint(0, len(seq.segments)), act=rng.choice(ACTS))
            elif op == "add_pulse" and seq.segments:
                s = rng.choice(seq.segments)
                ctl.add_block(rng.choice(PULSE_TYPES), segment_id=s.id, qubit=rng.randint(1, 8))
            elif op == "add_measure":
                ctl.add_block("Measure")
            elif op == "remove":
                b = rand_block(seq, rng)
                b and ctl.remove(b.id)
            elif op == "duplicate":
                b = rand_block(seq, rng)
                b and ctl.duplicate(b.id)
            elif op == "move_seg" and seq.segments:
                s = rng.choice(seq.segments)
                ctl.move_segment(s.id, rng.randint(0, len(seq.segments)), rng.choice([None] + ACTS))
            elif op == "move_pulse" and seq.pulses and seq.segments:
                ctl.move_pulse(rng.choice(seq.pulses).id, rng.choice(seq.segments).id, rng.randint(1, 8))
            elif op == "set_duration":
                b = rand_block(seq, rng, ("segment",))
                b and "duration_us" in b.fields and ctl.set_field(b.id, "duration_us", Value(rng.uniform(0, 2)))
            elif op == "sweep_duration":
                b = rand_block(seq, rng, ("segment",))
                if b and "duration_us" in b.fields and len(seq.settings.sweeps) < 3:
                    name = ctl.add_sweep_axis("t", 0.0, 1.0, rng.randint(1, 30), "us")
                    ctl.set_field(b.id, "duration_us", Sweep(name))
            elif op == "set_qubit":
                b = rand_block(seq, rng, ("pulse",))
                b and ctl.set_field(b.id, "qubit", Value(rng.randint(1, 8)))
            elif op == "rename_block":
                b = rand_block(seq, rng)
                b and ctl.rename(b.id, f"blk{step}")
            elif op == "set_name":
                ctl.set_name(f"Seq {step}")
            elif op == "set_act":
                b = rand_block(seq, rng, ("segment",))
                b and ctl.set_act(b.id, rng.choice(ACTS))
            elif op == "add_axis" and len(seq.settings.sweeps) < 3:
                ctl.add_sweep_axis("ax", 0, 1, rng.randint(1, 20))
            elif op == "set_reps":
                st = ExperimentSettings.from_dict(seq.settings.to_dict())
                st.reps = rng.randint(1, 5000)
                ctl.set_settings(st)
            elif op == "rename_axis" and seq.settings.sweeps:
                st = ExperimentSettings.from_dict(seq.settings.to_dict())
                k = rng.randrange(len(st.sweeps))
                old = st.sweeps[k].name
                st.sweeps[k].name = f"r{step}"
                ctl.set_settings(st, rename_axes={old: st.sweeps[k].name})
            elif op == "remove_axis" and seq.settings.sweeps:
                st = ExperimentSettings.from_dict(seq.settings.to_dict())
                st.sweeps.pop(rng.randrange(len(st.sweeps)))
                ctl.set_settings(st)
            elif op == "copy_paste":
                b = rand_block(seq, rng)
                if b:
                    ctl.copy(b.id)
                    t = rand_block(seq, rng)
                    ctl.select(t.id if t else None)
                    ctl.paste()
            elif op == "undo":
                ctl.undo.undo()
            elif op == "redo":
                ctl.undo.redo()
            elif op == "select":
                b = rand_block(seq, rng)
                ctl.select(b.id if b and rng.random() < 0.8 else None)
            elif op == "preview":
                ctl.set_preview_index(rng.randint(0, 50))
            elif op == "save_reopen":
                path = os.path.join(tmp, f"s{step}.json")
                before = ctl.seq.to_dict()
                ctl.save(path)
                after_save = ctl.seq.to_dict()
                w.bob.open_path(path)
                ctl.refresh_now()
                if ctl.seq.to_dict() != after_save:
                    found.append(f"step {step} (save_reopen): reopened file differs from what was saved")
                if ctl.dirty:
                    found.append(f"step {step} (save_reopen): reopened file is marked unsaved")
                b_wo = {k: v for k, v in before.items() if k not in ("calibration", "summary")}
                a_wo = {k: v for k, v in after_save.items() if k not in ("calibration", "summary")}
                if a_wo != b_wo:
                    found.append(f"step {step} (save_reopen): saving changed the sequence itself")
            elif op == "ui_rename_title":
                t = w.bob.topbar.title
                t.start_editing()
                t.edit.setText(f"T{step}")
                t._finish()
            elif op == "ui_settings_name":
                sp = w.bob.settings_panel
                sp.name.setText(f"N{step}")
                sp._rename()
            elif op == "ui_desc":
                sp = w.bob.settings_panel
                sp.desc.setText(f"desc {step}")
                sp._commit()
            elif op == "ui_reps":
                sp = w.bob.settings_panel
                sp.reps.setValue(rng.randint(1, 9000))
                sp._commit()
            elif op == "ui_scalar_edit" and seq.segments:
                b = rand_block(seq, rng, ("segment",))
                ctl.select(b.id)
                ctl.refresh_now()
                QApplication.processEvents()
                row = w.bob.inspector.rows.get("duration_us")
                if row is not None and row.focus_widget is not None and hasattr(row.focus_widget, "setText") \
                        and type(row.focus_widget).__name__ == "QLineEdit":
                    row.focus_widget.setText(f"{rng.uniform(0, 1):.3f}")
                    row._scalar_edited(row.focus_widget)
            elif op == "set_station_calib":
                ctl.set_station("8QV1")
        except Exception:
            found.append(f"step {step} ({op}): exception\n{traceback.format_exc()}")
        found += check(w, step, op)
        if len(found) > 8:
            break
    end = ctl.seq.to_dict()
    n = ctl.undo.index()
    for _ in range(n):
        ctl.undo.undo()
    for _ in range(n):
        ctl.undo.redo()
    if ctl.seq.to_dict() != end:
        found.append("redo all does not reach the last state")
    found += check(w, "end", "undo/redo all")
    w.close()
    w.deleteLater()
    QApplication.processEvents()
    return found


@pytest.mark.parametrize("seed", [10, 23])
def test_random_editing_session(seed, qtbot, isolated_settings, tmp_path, monkeypatch):
    from Bob.Bob_GUI.main_window import MainWindow
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Discard))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    found = one_run(MainWindow, seed, 150, str(tmp_path))
    assert not found, f"seed {seed}:\n" + "\n".join(found[:5])
