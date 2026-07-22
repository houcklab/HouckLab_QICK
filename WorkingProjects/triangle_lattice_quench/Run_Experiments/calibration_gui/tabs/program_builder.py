"""Program Builder Qt tab — structured FFSegment editor + live timeline plot.

First-cut, hardware-free editor for ``ProgramBuilder`` programs:

  * A readout-group selector (seeds the device operating point for the plot).
  * A QTreeWidget of segments; each segment expands to its drives.
  * Buttons: Add/Delete segment, Add/Delete drive, Edit (inline dialog),
    "Grab gains from JSON point", New/Save/Load program.
  * A matplotlib canvas showing ``ProgramBuilder.plot_program`` for the current
    segment list, refreshed on every edit. If the device-calib model can't be
    imported (no qutip / no hardware), the canvas shows an explanatory message
    instead of crashing.

No hardware touch. Reads ``qubit_parameters_json`` from shared CalibState.
"""
from __future__ import annotations

import os
import copy
import json
from typing import Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QTreeWidget, QTreeWidgetItem, QDialog, QFormLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QDialogButtonBox, QMessageBox, QFileDialog, QInputDialog,
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.ProgramBuilder import (
    DriveObj, FFSegment, ProgramBuilder,
)

# Default save/load location (created lazily). This module now lives at
# Run_Experiments/calibration_gui/tabs/, so walk up two extra levels to keep
# program_builder_programs/ rooted at Run_Experiments/.
_PROGRAMS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "program_builder_programs",
)

N_FF_CHANNELS = 8  # one FF line per qubit Q1..Q8
NONE_LABEL = "(none)"


def _default_segment() -> FFSegment:
    return FFSegment(IQArray=None, gains=[0] * N_FF_CHANNELS,
                     length_samples=320, drives=[], type="const")


# --- hand-editable JSON persistence (folded in from program_builder_io) ---
# A program is an ordered list of const FFSegments (length + 8 gains + drives),
# saved as flat readable JSON. relative_t preserves its "auto"-vs-float meaning;
# all six DriveObj fields plus the segment type survive the round trip.
_DRIVE_FIELDS = ("freq", "gain", "phase", "sigma_us", "len_sigmas", "relative_t")


def _drive_to_dict(drv: DriveObj) -> dict:
    return {f: getattr(drv, f) for f in _DRIVE_FIELDS}


def _drive_from_dict(d: dict) -> DriveObj:
    return DriveObj(
        freq=d["freq"], gain=d["gain"], phase=d["phase"], sigma_us=d["sigma_us"],
        len_sigmas=d.get("len_sigmas", 4), relative_t=d.get("relative_t", "auto"),
    )


def _segment_to_dict(seg: FFSegment) -> dict:
    gains = seg.gains
    gains_list = [] if gains is None else [g.item() if hasattr(g, "item") else g for g in list(gains)]
    return {
        "type": getattr(seg, "type", "const"),
        "length_samples": (None if seg.length_samples is None else int(seg.length_samples)),
        "gains": gains_list,
        "drives": [_drive_to_dict(d) for d in (seg.drives or [])],
    }


def _segment_from_dict(d: dict) -> FFSegment:
    gains = d.get("gains")
    return FFSegment(
        IQArray=None, gains=(list(gains) if gains is not None else None),
        length_samples=d.get("length_samples"),
        drives=[_drive_from_dict(x) for x in (d.get("drives") or [])],
        type=d.get("type", "const"),
    )


def save_program(path: str, segments: list, meta: dict) -> None:
    """Write segments + meta to path as hand-editable JSON."""
    payload = {"meta": dict(meta or {}), "segments": [_segment_to_dict(s) for s in segments]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_program(path: str) -> Tuple[list, dict]:
    """Read a program JSON; return (segments, meta)."""
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return ([_segment_from_dict(s) for s in payload.get("segments", [])],
            payload.get("meta", {}))


class _DriveDialog(QDialog):
    """Edit one DriveObj's six fields."""

    def __init__(self, drive: Optional[DriveObj], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Drive")
        d = drive or DriveObj(freq=4000.0, gain=10000, phase=0.0, sigma_us=0.03)
        form = QFormLayout()
        self.freq = QDoubleSpinBox(); self.freq.setRange(0.0, 20000.0); self.freq.setDecimals(3); self.freq.setValue(float(d.freq))
        self.gain = QSpinBox(); self.gain.setRange(-32766, 32766); self.gain.setValue(int(d.gain))
        self.phase = QDoubleSpinBox(); self.phase.setRange(-360.0, 360.0); self.phase.setDecimals(2); self.phase.setValue(float(d.phase))
        self.sigma = QDoubleSpinBox(); self.sigma.setRange(0.0, 100.0); self.sigma.setDecimals(4); self.sigma.setValue(float(d.sigma_us))
        self.len_sigmas = QDoubleSpinBox(); self.len_sigmas.setRange(0.0, 100.0); self.len_sigmas.setDecimals(2); self.len_sigmas.setValue(float(d.len_sigmas))
        # relative_t accepts "auto" or a float; keep as a text field.
        self.rel_t = QLineEdit(str(d.relative_t))
        form.addRow("freq (MHz)", self.freq)
        form.addRow("gain (DAC)", self.gain)
        form.addRow("phase (deg)", self.phase)
        form.addRow("sigma_us", self.sigma)
        form.addRow("len_sigmas", self.len_sigmas)
        form.addRow("relative_t ('auto' or us)", self.rel_t)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)
        self._result: Optional[DriveObj] = None

    def _on_ok(self):
        rt_text = self.rel_t.text().strip()
        if rt_text == "auto" or rt_text == "":
            rel_t = "auto"
        else:
            try:
                rel_t = float(rt_text)
            except ValueError:
                QMessageBox.warning(self, "Bad relative_t", "Use 'auto' or a number.")
                return
        self._result = DriveObj(
            freq=self.freq.value(), gain=self.gain.value(), phase=self.phase.value(),
            sigma_us=self.sigma.value(), len_sigmas=self.len_sigmas.value(),
            relative_t=rel_t,
        )
        self.accept()

    def result_drive(self) -> Optional[DriveObj]:
        return self._result


class _SegmentDialog(QDialog):
    """Edit a const segment's length + 8 gains."""

    def __init__(self, seg: FFSegment, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Segment (const)")
        form = QFormLayout()
        self.length = QSpinBox(); self.length.setRange(1, 10_000_000)
        self.length.setValue(int(seg.length_samples or 320))
        gains = list(seg.gains) if seg.gains is not None else [0] * N_FF_CHANNELS
        self.gain_edit = QLineEdit(",".join(str(int(g)) for g in gains))
        form.addRow("length_samples", self.length)
        form.addRow(f"gains (comma, {N_FF_CHANNELS} ints)", self.gain_edit)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)
        self._result: Optional[FFSegment] = None
        self._orig = seg

    def _on_ok(self):
        try:
            gains = [int(x.strip()) for x in self.gain_edit.text().split(",")]
        except ValueError:
            QMessageBox.warning(self, "Bad gains", "All gains must be integers.")
            return
        if len(gains) != N_FF_CHANNELS:
            QMessageBox.warning(self, "Wrong length",
                                f"Need exactly {N_FF_CHANNELS} gains, got {len(gains)}.")
            return
        self._result = FFSegment(
            IQArray=None, gains=gains, length_samples=self.length.value(),
            drives=list(self._orig.drives), type="const",
        )
        self.accept()

    def result_segment(self) -> Optional[FFSegment]:
        return self._result


class _GrabGainsDialog(QDialog):
    """One-window cascading picker for a JSON FF point.

    Three combos in the same window -- namespace -> group -> entry -- each one
    enables and populates as the level above it is chosen (no popup chain). When
    a selection resolves to an FF gain vector it's shown live in a read-only
    preview, and OK only enables once a valid vector is previewed.
    """

    def __init__(self, jd: dict, resolvers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grab gains from JSON point")
        self._jd = jd
        # (groups_for_kind, entries_for_group, resolve_stage_ff)
        self._groups_for_kind, self._entries_for_group, self._resolve_stage_ff = resolvers
        self._gains: Optional[list] = None

        self.kind = QComboBox(); self.kind.addItem(NONE_LABEL)
        self.kind.addItems(["ramp", "dynamics", "drive", "readout"])
        self.group = QComboBox(); self.group.setEnabled(False)
        self.entry = QComboBox(); self.entry.setEnabled(False)
        self.preview = QLineEdit(); self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("(pick down to an entry to preview its gains)")

        form = QFormLayout()
        form.addRow("Namespace", self.kind)
        form.addRow("Group", self.group)
        form.addRow("Entry", self.entry)
        form.addRow(f"Gains ({N_FF_CHANNELS} ch)", self.preview)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        self._ok = bb.button(QDialogButtonBox.Ok); self._ok.setEnabled(False)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)

        self.kind.currentTextChanged.connect(self._on_kind)
        self.group.currentTextChanged.connect(self._on_group)
        self.entry.currentTextChanged.connect(self._on_entry)

    def _val(self, combo) -> Optional[str]:
        t = combo.currentText()
        return None if (not t or t == NONE_LABEL) else t

    def _on_kind(self, _t=None):
        self.group.blockSignals(True); self.group.clear(); self.group.blockSignals(False)
        self.entry.blockSignals(True); self.entry.clear(); self.entry.setEnabled(False); self.entry.blockSignals(False)
        self._set_preview(None)
        k = self._val(self.kind)
        if k is None:
            self.group.setEnabled(False); return
        groups = list(self._groups_for_kind(self._jd, k) or [])
        self.group.blockSignals(True)
        self.group.addItem(NONE_LABEL); self.group.addItems(groups)
        self.group.blockSignals(False)
        self.group.setEnabled(bool(groups))

    def _on_group(self, _t=None):
        self.entry.blockSignals(True); self.entry.clear(); self.entry.blockSignals(False)
        self._set_preview(None)
        k, g = self._val(self.kind), self._val(self.group)
        if k is None or g is None:
            self.entry.setEnabled(False); return
        entries = list(self._entries_for_group(self._jd, k, g) or [])
        self.entry.blockSignals(True)
        self.entry.addItem("(group-level)")   # resolve the group's own FF (entry="")
        self.entry.addItems(entries)
        self.entry.blockSignals(False)
        self.entry.setEnabled(True)
        self._on_entry()   # preview the default (group-level) immediately

    def _on_entry(self, _t=None):
        k, g = self._val(self.kind), self._val(self.group)
        if k is None or g is None or not self.entry.isEnabled():
            self._set_preview(None); return
        e = self.entry.currentText()
        entry = "" if (e in ("", "(group-level)")) else e
        try:
            ff = self._resolve_stage_ff(self._jd, k, g, entry)
        except Exception as exc:
            self._set_preview(None, err=f"resolve failed: {exc}"); return
        if ff is None:
            self._set_preview(None, err="(no FF array for this selection)"); return
        gains = [int(round(float(x))) for x in ff][:N_FF_CHANNELS]
        gains += [0] * (N_FF_CHANNELS - len(gains))
        self._set_preview(gains)

    def _set_preview(self, gains, err=None):
        self._gains = gains
        self.preview.setText(", ".join(str(g) for g in gains) if gains is not None else (err or ""))
        self._ok.setEnabled(gains is not None)

    def result_gains(self) -> Optional[list]:
        return self._gains


class ProgramBuilderTab(QWidget):
    """Structured ProgramBuilder editor with a live timeline preview."""

    name = "Program Builder"

    def __init__(self, state, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        self._segments: list[FFSegment] = [_default_segment()]
        self._meta: dict = {}

        # --- readout-group selector ---
        self.readout_combo = QComboBox()
        self.readout_combo.currentTextChanged.connect(lambda _t: self._redraw())
        self._refresh_readout_combo()

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Readout group (operating point):"))
        top_row.addWidget(self.readout_combo, 1)
        reload_btn = QPushButton("Reload groups")
        reload_btn.clicked.connect(self._refresh_readout_combo)
        top_row.addWidget(reload_btn)

        # --- segment / drive tree ---
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["index / drive", "type", "length / freq", "gains / drive params"])

        # --- edit buttons ---
        def _btn(text, slot):
            b = QPushButton(text); b.clicked.connect(slot); return b

        edit_row = QHBoxLayout()
        edit_row.addWidget(_btn("Add segment", self._add_segment))
        edit_row.addWidget(_btn("Delete segment", self._delete_segment))
        edit_row.addWidget(_btn("Add drive", self._add_drive))
        edit_row.addWidget(_btn("Delete drive", self._delete_drive))
        edit_row.addWidget(_btn("Edit", self._edit_selected))
        edit_row.addWidget(_btn("Grab gains from JSON point", self._grab_gains))
        edit_row.addStretch(1)

        file_row = QHBoxLayout()
        file_row.addWidget(_btn("New", self._new_program))
        file_row.addWidget(_btn("Save", self._save_program))
        file_row.addWidget(_btn("Load", self._load_program))
        file_row.addStretch(1)

        # --- matplotlib canvas ---
        self._fig = Figure(figsize=(8.0, 4.5))
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._ax = self._fig.add_subplot(111)

        self._status = QLabel("Ready. Build const FF segments; the plot shows dressed frequencies vs samples.")
        self._status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.tree, 2)
        layout.addLayout(edit_row)
        layout.addLayout(file_row)
        layout.addWidget(self._canvas, 3)
        layout.addWidget(self._status)

        self._refresh_tree()
        self._redraw()

    # ----- JSON helpers -----

    def _qubit_json(self) -> dict:
        return getattr(self.state, "qubit_parameters_json", None) or {}

    def _refresh_readout_combo(self):
        jd = self._qubit_json()
        groups = list((jd.get("readout_groups") or {}).keys())
        cur = self.readout_combo.currentText()
        self.readout_combo.blockSignals(True)
        self.readout_combo.clear()
        self.readout_combo.addItem(NONE_LABEL)
        self.readout_combo.addItems(groups)
        if cur in groups:
            self.readout_combo.setCurrentText(cur)
        self.readout_combo.blockSignals(False)
        self._redraw()

    def _selected_readout_group(self) -> Optional[str]:
        t = self.readout_combo.currentText()
        return None if (not t or t == NONE_LABEL) else t

    # ----- tree rendering -----

    def _refresh_tree(self):
        self.tree.clear()
        for si, seg in enumerate(self._segments):
            gains = list(seg.gains) if seg.gains is not None else []
            gains_str = ", ".join(str(int(g)) for g in gains)
            item = QTreeWidgetItem([
                f"seg {si}", getattr(seg, "type", "const"),
                str(seg.length_samples), gains_str,
            ])
            item.setData(0, Qt.UserRole, ("segment", si))
            for di, drv in enumerate(seg.drives or []):
                d_item = QTreeWidgetItem([
                    f"  drive {di}", "gauss", f"{drv.freq:g} MHz",
                    f"gain={drv.gain}, phase={drv.phase:g}, sigma_us={drv.sigma_us:g}, "
                    f"len_sigmas={drv.len_sigmas:g}, t={drv.relative_t}",
                ])
                d_item.setData(0, Qt.UserRole, ("drive", si, di))
                item.addChild(d_item)
            self.tree.addTopLevelItem(item)
        self.tree.expandAll()
        for c in range(4):
            self.tree.resizeColumnToContents(c)

    def _selected_ref(self):
        """Return ('segment', si) or ('drive', si, di) for the selected row, else None."""
        items = self.tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.UserRole)

    def _selected_segment_index(self) -> Optional[int]:
        ref = self._selected_ref()
        if ref is None:
            return None
        return ref[1]

    # ----- edit actions -----

    def _add_segment(self):
        self._segments.append(_default_segment())
        self._refresh_tree(); self._redraw()
        self._status.setText(f"Added segment {len(self._segments) - 1}.")

    def _delete_segment(self):
        si = self._selected_segment_index()
        if si is None:
            QMessageBox.information(self, "Select", "Select a segment to delete.")
            return
        if len(self._segments) <= 1:
            QMessageBox.information(self, "Keep one", "A program needs at least one segment.")
            return
        del self._segments[si]
        self._refresh_tree(); self._redraw()
        self._status.setText(f"Deleted segment {si}.")

    def _add_drive(self):
        si = self._selected_segment_index()
        if si is None:
            QMessageBox.information(self, "Select", "Select a segment to add a drive to.")
            return
        dlg = _DriveDialog(None, self)
        if dlg.exec_() == QDialog.Accepted and dlg.result_drive() is not None:
            self._segments[si].drives.append(dlg.result_drive())
            self._refresh_tree(); self._redraw()
            self._status.setText(f"Added drive to segment {si}.")

    def _delete_drive(self):
        ref = self._selected_ref()
        if ref is None or ref[0] != "drive":
            QMessageBox.information(self, "Select", "Select a drive row to delete.")
            return
        _, si, di = ref
        del self._segments[si].drives[di]
        self._refresh_tree(); self._redraw()
        self._status.setText(f"Deleted drive {di} from segment {si}.")

    def _edit_selected(self):
        ref = self._selected_ref()
        if ref is None:
            QMessageBox.information(self, "Select", "Select a segment or drive to edit.")
            return
        if ref[0] == "segment":
            si = ref[1]
            dlg = _SegmentDialog(self._segments[si], self)
            if dlg.exec_() == QDialog.Accepted and dlg.result_segment() is not None:
                self._segments[si] = dlg.result_segment()
                self._refresh_tree(); self._redraw()
                self._status.setText(f"Edited segment {si}.")
        else:
            _, si, di = ref
            dlg = _DriveDialog(self._segments[si].drives[di], self)
            if dlg.exec_() == QDialog.Accepted and dlg.result_drive() is not None:
                self._segments[si].drives[di] = dlg.result_drive()
                self._refresh_tree(); self._redraw()
                self._status.setText(f"Edited drive {di} of segment {si}.")

    def _grab_gains(self):
        """Resolve an 8-element FF gain vector from a JSON point via one cascading dialog."""
        si = self._selected_segment_index()
        if si is None:
            QMessageBox.information(self, "Select", "Select a segment to set gains on.")
            return
        jd = self._qubit_json()
        if not jd:
            QMessageBox.warning(self, "No JSON", "No qubit_parameters JSON loaded.")
            return
        try:
            from WorkingProjects.triangle_lattice_quench.Run_Experiments.exptui_demo.freq_resolve import (
                groups_for_kind, entries_for_group, resolve_stage_ff,
            )
        except Exception as e:
            QMessageBox.warning(self, "Resolver unavailable", str(e))
            return
        dlg = _GrabGainsDialog(jd, (groups_for_kind, entries_for_group, resolve_stage_ff), self)
        if dlg.exec_() != QDialog.Accepted:
            return
        gains = dlg.result_gains()
        if gains is None:
            return
        self._segments[si] = FFSegment(
            IQArray=None, gains=gains,
            length_samples=self._segments[si].length_samples,
            drives=list(self._segments[si].drives), type="const",
        )
        self._refresh_tree(); self._redraw()
        self._status.setText(f"Set segment {si} gains.")

    # ----- file actions -----

    def _new_program(self):
        self._segments = [_default_segment()]
        self._meta = {}
        self._refresh_tree(); self._redraw()
        self._status.setText("New program.")

    def _save_program(self):
        os.makedirs(_PROGRAMS_DIR, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save program", _PROGRAMS_DIR, "JSON (*.json)")
        if not path:
            return
        meta = dict(self._meta)
        meta["readout_group"] = self._selected_readout_group()
        try:
            save_program(path, self._segments, meta)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return
        self._status.setText(f"Saved {path}.")

    def _load_program(self):
        os.makedirs(_PROGRAMS_DIR, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            self, "Load program", _PROGRAMS_DIR, "JSON (*.json)")
        if not path:
            return
        try:
            segments, meta = load_program(path)
        except Exception as e:
            QMessageBox.warning(self, "Load failed", str(e))
            return
        if not segments:
            QMessageBox.warning(self, "Empty", "No segments in that file.")
            return
        self._segments = segments
        self._meta = meta or {}
        rg = self._meta.get("readout_group")
        if rg:
            idx = self.readout_combo.findText(rg)
            if idx >= 0:
                self.readout_combo.setCurrentIndex(idx)
        self._refresh_tree(); self._redraw()
        self._status.setText(f"Loaded {path} ({len(segments)} segments).")

    # ----- plot -----

    def _redraw(self):
        # Guard: combo/refresh wiring can fire before the canvas exists.
        if getattr(self, "_ax", None) is None:
            return
        self._ax.clear()
        cfg_like = {
            "ProgramBuilderInfo": self._segments,
            "n_ff_channels": N_FF_CHANNELS,
            "readout_groups": self._qubit_json().get("readout_groups", {}),
        }
        try:
            ProgramBuilder.plot_program(
                cfg_like, readout_group=self._selected_readout_group(), ax=self._ax)
        except Exception as e:
            # plot_program is meant to self-contain its errors; this is a final net.
            import traceback
            self._ax.clear(); self._ax.set_axis_off()
            self._ax.text(0.5, 0.5, f"Plot failed:\n{e}\n\n{traceback.format_exc()}",
                          ha="center", va="center", fontsize=7, family="monospace",
                          transform=self._ax.transAxes)
        self._fig.tight_layout()
        self._canvas.draw_idle()
