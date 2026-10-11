"""Program Builder Qt tab: structured FFSegment editor + live timeline plot.

Hardware-free editor for ``ProgramBuilder`` programs, laid out as

    +-- segment column --------------------+-- JSON viewer ----------------------+
    | New / Save / Load   <file name>       | qubit_parameters.json (live tree)    |
    | Add / Duplicate / Delete segment,     | preview of what the selected node    |
    | Add / Delete drive                    | would apply, "Use" button            |
    | table: one row per segment (length +  |                                      |
    |   one gain cell per FF channel) and   |                                      |
    |   per drive (freq, gain, phase, ...)  |                                      |
    | Readout group (operating point)       |                                      |
    +---------------------------------------+--------------------------------------+
    | plot: ProgramBuilder.plot_program for the current segments                   |
    +------------------------------------------------------------------------------+

Every number is edited by typing into its cell. Selecting a segment row and then a JSON node that
resolves to an FF array (a group-level FF_* list, any numeric list, or a drive_groups entry via
``QubitParams.drive_ff``, so FF_override applies) and pressing Use (or double-clicking) copies the
gains; with a drive row selected, a drive_groups entry (or its Qubit object) copies
freq / gain / sigma_us. Values are always copied, never aliased to the JSON.

No hardware touch. Reads ``qubit_parameters_json`` from the shared CalibState.
"""
from __future__ import annotations

import os
import copy
import json
import math
import traceback
from typing import Optional, Tuple

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg

from .. import style as st
from ..state import groups_of, readout_group_names
from triangle_lattice_quench.Experimental_Scripts.Program_Templates.ProgramBuilder import (
    DriveObj, FFSegment, ProgramBuilder,
)

# Default save/load location (created lazily). This module lives at
# Run_Experiments/calibration_gui/tabs/, so walk up three levels to Run_Experiments/.
_PROGRAMS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "program_builder_programs",
)

N_FF_CHANNELS = 8  # one FF line per qubit Q1..Q8
NONE_LABEL = "(none)"
MAX_GAIN = 32766   # DAC full scale


def _default_segment() -> FFSegment:
    return FFSegment(IQArray=None, gains=[0] * N_FF_CHANNELS,
                     length_samples=320, drives=[], type="const")


def _default_drive() -> DriveObj:
    return DriveObj(freq=4000.0, gain=10000, phase=0.0, sigma_us=0.03)


# --- hand-editable JSON persistence ---
# A program is an ordered list of const FFSegments (length + gains + drives), saved as flat
# readable JSON. relative_t preserves its "auto"-vs-float meaning; all six DriveObj fields plus
# the segment type survive the round trip. (GUI-internal: ProgramBuilder.py has no converter, and
# IQArray segments are not saved.)
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


# --- cell parsing (typed text -> value; ValueError carries the message shown to the user) ---

def _fmt(v) -> str:
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return "0" if v == 0 else f"{v:.10g}"
    return str(v)


def _to_float(text: str, what: str) -> float:
    try:
        x = float(text)
    except ValueError:
        raise ValueError(f"{what}: '{text}' is not a number") from None
    if not math.isfinite(x):
        raise ValueError(f"{what}: must be finite")
    return x


def _parse_int(text: str, what: str, lo=None, hi=None) -> int:
    x = int(round(_to_float(text, what)))
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        raise ValueError(f"{what}: {x} is outside [{lo}, {hi}]")
    return x


def _parse_number(text: str, what: str, lo=None, hi=None, positive=False):
    x = _to_float(text, what)
    if positive and x <= 0:
        raise ValueError(f"{what}: must be > 0")
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        raise ValueError(f"{what}: {x:g} is outside [{lo}, {hi}]")
    return int(x) if float(x).is_integer() and abs(x) < 1e15 else x


def _parse_relative_t(text: str):
    if text.strip().lower() in ("", "auto"):
        return "auto"
    return _to_float(text, "relative_t")


# column of each drive field in the table (segment rows: 2 = length, 3.. = one gain per FF channel)
_DRIVE_COLS = {2: "freq", 3: "gain", 4: "phase", 5: "sigma_us", 6: "len_sigmas", 7: "relative_t"}
_DRIVE_HEADERS = ["", "", "freq (MHz)", "gain", "phase", "sigma_us", "len_sigmas", "relative_t"]
_GAIN_COL0 = 3


# --- JSON node -> what it can apply to a segment / drive ---

def _is_number_list(v) -> bool:
    return (isinstance(v, list) and len(v) > 0
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v))


def _json_node(jd, path):
    node = jd
    for k in path:
        node = node[k] if isinstance(node, dict) else node[int(k)]
    return node


def json_candidates(jd: dict, path: tuple) -> dict:
    """What the JSON node at ``path`` can apply: {'gains': (list, description) | None,
    'drive': (dict, description) | None}. Always fresh copies, never views into ``jd``.

    gains: any numeric list node, or a drive_groups entry / its Qubit / its Readout object (FF_Pulses
    for an entry or its Qubit, FF_Readouts for its Readout, of that entry via ``QubitParams.drive_ff``, FF_override included).
    drive: a drive_groups entry or its Qubit object -> freq / gain / sigma_us from Qubit.
    """
    out = {"gains": None, "drive": None}
    try:
        node = _json_node(jd, path)
    except (KeyError, IndexError, TypeError, ValueError):
        return out
    where = "/".join(str(p) for p in path)
    if _is_number_list(node):
        out["gains"] = ([x for x in node], where)
    if len(path) in (4, 5) and path[0] == "drive_groups" and path[2] == "entries" \
            and (len(path) == 4 or path[4] in ("Qubit", "Readout")):
        group, entry = path[1], str(path[3])
        sub = path[4] if len(path) == 5 else None
        name = "FF_Readouts" if sub == "Readout" else "FF_Pulses"
        try:
            from triangle_lattice_quench.build_config import QubitParams
            ff = QubitParams(jd).drive_ff(name, group, entry)
            if _is_number_list(ff):
                out["gains"] = ([x for x in ff], f"{name} of {group}/{entry}")
        except Exception:
            pass
        if sub in (None, "Qubit"):
            q = (node.get("Qubit") if sub is None else node)
            if isinstance(q, dict) and all(k in q for k in ("Frequency", "Gain", "sigma")):
                out["drive"] = ({"freq": q["Frequency"], "gain": q["Gain"], "sigma_us": q["sigma"]},
                                f"Qubit of {group}/{entry}")
    return out


def _fit_gains(values) -> list:
    g = [int(round(float(x))) for x in values][:N_FF_CHANNELS]
    return g + [0] * (N_FF_CHANNELS - len(g))


class ProgramBuilderTab(QWidget):
    """Structured ProgramBuilder editor with a live timeline preview and a JSON viewer."""

    name = "Program Builder"

    def __init__(self, state, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        self._segments: list[FFSegment] = [_default_segment()]
        self._meta: dict = {}
        self._path: Optional[str] = None          # file of the last Save / Load
        self._baseline = ""                       # serialized program at the last New / Save / Load
        self._suppress = False                    # table rebuilds / programmatic cell updates
        self._row_refs: list = []                 # per table row: ("segment", si) | ("drive", si, di) | None

        def _btn(text, slot):
            b = QPushButton(text)
            b.clicked.connect(slot)
            return b

        # --- file row (over the segment table): New / Save / Load + the file name ---
        self.file_label = QLabel()
        self.file_label.setMinimumWidth(1)
        file_row = QHBoxLayout()
        file_row.addWidget(_btn("New", self._new_program))
        file_row.addWidget(_btn("Save", self._save_program))
        file_row.addWidget(_btn("Load", self._load_program))
        file_row.addWidget(self.file_label, 1)

        edit_row = QHBoxLayout()
        edit_row.addWidget(_btn("Add segment", self._add_segment))
        edit_row.addWidget(_btn("Duplicate segment", self._duplicate_segment))
        edit_row.addWidget(_btn("Delete segment", self._delete_segment))
        edit_row.addWidget(_btn("Add drive", self._add_drive))
        edit_row.addWidget(_btn("Delete drive", self._delete_drive))
        edit_row.addStretch(1)

        # --- segment / drive table ---
        self.table = QTableWidget(0, _GAIN_COL0 + N_FF_CHANNELS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.AnyKeyPressed)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.installEventFilter(self)       # Enter / Return also starts an edit
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._update_json_preview)

        # --- readout group (bottom of the segment column: the readout happens last) ---
        self.readout_combo = QComboBox()
        self.readout_combo.currentTextChanged.connect(lambda _t: self._after_change())
        readout_row = QHBoxLayout()
        readout_row.addWidget(QLabel("Readout group (operating point):"))
        readout_row.addWidget(self.readout_combo, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(file_row)
        left_layout.addLayout(edit_row)
        left_layout.addWidget(self.table, 1)
        left_layout.addLayout(readout_row)

        # --- JSON viewer (right half) ---
        self.json_tree = QTreeWidget()
        self.json_tree.setColumnCount(2)
        self.json_tree.setHeaderLabels(["qubit_parameters.json", "value"])
        self.json_tree.setExpandsOnDoubleClick(False)       # double-click applies instead
        self.json_tree.itemSelectionChanged.connect(self._update_json_preview)
        self.json_tree.itemDoubleClicked.connect(lambda *_: self._use_json_selection())
        self.json_preview = QLabel()
        self.json_preview.setWordWrap(True)
        self.use_btn = QPushButton("Use selected")
        self.use_btn.clicked.connect(self._use_json_selection)
        use_row = QHBoxLayout()
        use_row.addWidget(self.json_preview, 1)
        use_row.addWidget(self.use_btn)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.json_tree, 1)
        right_layout.addLayout(use_row)

        top = QSplitter(Qt.Horizontal)
        top.addWidget(left)
        top.addWidget(right)
        top.setStretchFactor(0, 3)
        top.setStretchFactor(1, 2)

        # --- plot ---
        self._fig = Figure(figsize=(8.0, 4.5))
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._ax = self._fig.add_subplot(111)
        self._status = QLabel("Ready. Type into the cells; select a JSON node and press Use to copy its values.")
        self._status.setWordWrap(True)
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self._canvas, 1)
        bottom_layout.addWidget(self._status)
        self._assumptions = QLabel(
            "Assumptions: one FF gen sample = 0.290 ns. Must check timing if firmware changes from 8fullspeed. "
            "On-demand information is usually in soccfg.cycles2us(cycles, gen_ch=ch). "
            "Time per envelope/IQArray index = soccfg.cycles2us(1, gen_ch=ch) / soccfg['gens'][ch]['samps_per_clk']: "
            "samps_per_clk is 16 for full-speed gens (axis_signal_gen_v6, the FF gens: 1/16 of a 215.04 MHz clock = 0.290 ns) "
            "and 1 for interpolated gens (axis_sg_int4_v2, the qubit drive: 1 index = 1 fabric clock, which is 430.08 MHz = 2.33 ns "
            "on this firmware, so it differs from the 215.04 MHz FF clock).")
        self._assumptions.setWordWrap(True)
        self._assumptions.setStyleSheet("color: #666;")
        bottom_layout.addWidget(self._assumptions)

        outer = QSplitter(Qt.Vertical)
        outer.addWidget(top)
        outer.addWidget(bottom)
        outer.setStretchFactor(0, 1)
        outer.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(outer)

        self._refresh_readout_combo(redraw=False)
        self._rebuild_table(select=("segment", 0))
        self.refresh_json()
        self._reset_baseline()
        self._redraw()

    # ----- JSON helpers -----

    def _qubit_json(self) -> dict:
        return getattr(self.state, "qubit_parameters_json", None) or {}

    def _refresh_readout_combo(self, redraw: bool = True):
        groups = readout_group_names(self._qubit_json())
        wanted = [NONE_LABEL] + list(groups)
        have = [self.readout_combo.itemText(i) for i in range(self.readout_combo.count())]
        if wanted == have:
            return
        cur = self.readout_combo.currentText()
        self.readout_combo.blockSignals(True)
        self.readout_combo.clear()
        self.readout_combo.addItems(wanted)
        if cur in groups:
            self.readout_combo.setCurrentText(cur)
        self.readout_combo.blockSignals(False)
        if redraw:
            self._after_change()

    def _selected_readout_group(self) -> Optional[str]:
        t = self.readout_combo.currentText()
        return None if (not t or t == NONE_LABEL) else t

    def refresh_json(self) -> None:
        """Rebuild the JSON viewer (and the readout-group list) from the live state, keeping
        expanded nodes and the selection. Called on tab show and after a Qubit_Parameters load."""
        self._refresh_readout_combo()

        def walk(item):
            yield item
            for i in range(item.childCount()):
                yield from walk(item.child(i))

        def items():
            for i in range(self.json_tree.topLevelItemCount()):
                yield from walk(self.json_tree.topLevelItem(i))

        expanded = {it.data(0, Qt.UserRole) for it in items() if it.isExpanded()}
        cur = self.json_tree.currentItem()
        cur_path = cur.data(0, Qt.UserRole) if cur is not None else None
        first_build = self.json_tree.topLevelItemCount() == 0
        scroll = self.json_tree.verticalScrollBar().value()
        self.json_tree.blockSignals(True)
        self.json_tree.clear()
        jd = self._qubit_json()
        for key, val in jd.items():
            self._add_json_node(self.json_tree.invisibleRootItem(), key, val, (key,))
        target = None
        for it in items():
            p = it.data(0, Qt.UserRole)
            if p in expanded:
                it.setExpanded(True)
            if cur_path is not None and p == cur_path:
                target = it
        if first_build:
            self.json_tree.expandToDepth(0)
        if target is not None:
            self.json_tree.setCurrentItem(target)
        self.json_tree.blockSignals(False)
        self.json_tree.verticalScrollBar().setValue(scroll)
        self._update_json_preview()

    def _add_json_node(self, parent, key, val, path) -> None:
        if isinstance(val, dict):
            item = QTreeWidgetItem([str(key), ""])
            for k, v in val.items():
                self._add_json_node(item, k, v, path + (k,))
        elif isinstance(val, list) and any(isinstance(x, (dict, list)) for x in val):
            item = QTreeWidgetItem([str(key), f"[{len(val)} items]"])
            for i, v in enumerate(val):
                self._add_json_node(item, i, v, path + (i,))
        elif isinstance(val, list):
            text = ", ".join(_fmt(x) for x in val)
            item = QTreeWidgetItem([str(key), f"[{text}]"])
        else:
            item = QTreeWidgetItem([str(key), _fmt(val) if val is not None else "null"])
        item.setData(0, Qt.UserRole, path)
        parent.addChild(item)

    # ----- table rendering -----

    def _n_value_cols(self) -> int:
        longest = max([len(s.gains or []) for s in self._segments] + [N_FF_CHANNELS])
        return max(longest, len(_DRIVE_COLS) - 1)

    def _cell_text(self, ref, col) -> str:
        """Display text of the model value shown in (ref, col); "" when the cell holds none."""
        if ref[0] == "segment":
            seg = self._segments[ref[1]]
            if col == 0:
                return f"seg {ref[1]}"
            if col == 1:
                return getattr(seg, "type", "const")
            if col == 2:
                return _fmt(seg.length_samples)
            gains = list(seg.gains or [])
            return _fmt(gains[col - _GAIN_COL0]) if 0 <= col - _GAIN_COL0 < len(gains) else ""
        drv = self._segments[ref[1]].drives[ref[2]]
        if col == 0:
            return f"  drive {ref[2]}"
        if col == 1:
            return "gauss"
        field = _DRIVE_COLS.get(col)
        return _fmt(getattr(drv, field)) if field else ""

    def _is_editable(self, ref, col) -> bool:
        if ref[0] == "segment":
            if col == 2:
                return True
            return 0 <= col - _GAIN_COL0 < len(self._segments[ref[1]].gains or [])
        return col in _DRIVE_COLS

    def _set_item_text(self, item, text) -> None:
        was = self._suppress
        self._suppress = True
        try:
            item.setText(text)
            item.setData(Qt.UserRole, text)       # what the cell showed: lets us ignore no-op commits
        finally:
            self._suppress = was

    def _rebuild_table(self, select=None) -> None:
        """Repopulate the table from the model; `select` (a row ref) is re-selected afterwards."""
        if select is None:
            select = self._selected_ref()
        self._suppress = True
        try:
            n_vals = self._n_value_cols()
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(_GAIN_COL0 + n_vals)
            self.table.setHorizontalHeaderLabels(
                ["segment / drive", "type", "length_samples"] + [f"Q{i + 1}" for i in range(n_vals)])
            self._row_refs = []
            header_bg = QColor(st.HEADER_BG)
            unused_bg = QColor(240, 240, 240)
            bold = self.table.font()
            bold.setBold(True)
            for si, seg in enumerate(self._segments):
                self._append_row(("segment", si), bold, unused_bg)
                if seg.drives:
                    r = self.table.rowCount()
                    self.table.insertRow(r)
                    self._row_refs.append(None)
                    for c in range(self.table.columnCount()):
                        it = QTableWidgetItem(_DRIVE_HEADERS[c] if c < len(_DRIVE_HEADERS) else "")
                        it.setFlags(Qt.ItemIsEnabled)                 # not selectable
                        it.setBackground(header_bg)
                        self.table.setItem(r, c, it)
                    for di in range(len(seg.drives)):
                        self._append_row(("drive", si, di), None, unused_bg)
            self.table.resizeColumnsToContents()
            for c in range(self.table.columnCount()):
                self.table.setColumnWidth(c, max(self.table.columnWidth(c), 56 if c >= 2 else 0))
        finally:
            self._suppress = False
        self._select_ref(select)
        self._update_json_preview()

    def _append_row(self, ref, bold_font, unused_bg) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._row_refs.append(ref)
        for c in range(self.table.columnCount()):
            text = self._cell_text(ref, c)
            it = QTableWidgetItem(text)
            it.setData(Qt.UserRole, text)
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if self._is_editable(ref, c):
                flags |= Qt.ItemIsEditable
            elif c >= 2:
                it.setBackground(unused_bg)
            it.setFlags(flags)
            if c == 0 and bold_font is not None:
                it.setFont(bold_font)
            self.table.setItem(r, c, it)

    def _selected_ref(self):
        """("segment", si) / ("drive", si, di) of the selected row, else None."""
        rows = {i.row() for i in self.table.selectedIndexes()}
        if len(rows) != 1:
            return None
        r = rows.pop()
        return self._row_refs[r] if r < len(self._row_refs) else None

    def _select_ref(self, ref) -> None:
        if ref is None:
            return
        # a stale ref (e.g. a deleted drive) falls back to its segment
        for candidate in (ref, ("segment", ref[1])):
            if candidate in self._row_refs:
                self.table.selectRow(self._row_refs.index(candidate))
                return

    def _selected_segment_index(self) -> Optional[int]:
        ref = self._selected_ref()
        return None if ref is None else ref[1]

    # ----- typing into cells -----

    def eventFilter(self, obj, event):
        if (obj is self.table and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and self.table.state() != QAbstractItemView.EditingState):
            idx = self.table.currentIndex()
            if idx.isValid() and self.table.model().flags(idx) & Qt.ItemIsEditable:
                self.table.edit(idx)
                return True
        return super().eventFilter(obj, event)

    def _on_item_changed(self, item) -> None:
        if self._suppress:
            return
        row, col = item.row(), item.column()
        ref = self._row_refs[row] if row < len(self._row_refs) else None
        if ref is None or not self._is_editable(ref, col):
            return
        text = item.text().strip()
        shown = item.data(Qt.UserRole) or ""
        if text == shown:                          # committed unchanged: keep the exact stored value
            self._set_item_text(item, shown)
            return
        try:
            self._apply_edit(ref, col, text)
        except ValueError as exc:
            self._status.setText(f"Not changed: {exc}")
            self._set_item_text(item, shown)
            return
        self._set_item_text(item, self._cell_text(ref, col))
        self._after_change()

    def _apply_edit(self, ref, col, text) -> None:
        """Parse `text` and write it into the model cell (ref, col); ValueError when invalid."""
        if ref[0] == "segment":
            seg = self._segments[ref[1]]
            if col == 2:
                seg.length_samples = _parse_int(text, "length_samples", lo=1)
            else:
                seg.gains = list(seg.gains or [])
                seg.gains[col - _GAIN_COL0] = _parse_int(text, "gain", lo=-MAX_GAIN, hi=MAX_GAIN)
            return
        drv = self._segments[ref[1]].drives[ref[2]]
        field = _DRIVE_COLS[col]
        if field == "freq":
            value = _parse_number(text, "freq", lo=0)
        elif field == "gain":
            value = _parse_number(text, "gain", lo=-MAX_GAIN, hi=MAX_GAIN)
        elif field == "phase":
            value = _parse_number(text, "phase")
        elif field == "relative_t":
            value = _parse_relative_t(text)
        else:                                      # sigma_us, len_sigmas
            value = _parse_number(text, field, positive=True)
        setattr(drv, field, value)

    # ----- JSON viewer -> segment / drive -----

    def _json_selection_path(self) -> Optional[tuple]:
        item = self.json_tree.currentItem()
        return item.data(0, Qt.UserRole) if item is not None and item.isSelected() else None

    def _applicable(self):
        """(kind, payload, description, note) for the selected row + JSON node, or (None, None, text, "")."""
        ref, path = self._selected_ref(), self._json_selection_path()
        if ref is None:
            return None, None, "Select a segment or drive row, then a JSON node.", ""
        if path is None:
            return None, None, "Select a JSON node to copy from.", ""
        cand = json_candidates(self._qubit_json(), path)
        if ref[0] == "segment":
            if cand["gains"] is None:
                return None, None, "This node has no FF gains (pick an FF_* array or an entry).", ""
            vals, where = cand["gains"]
            gains = _fit_gains(vals)
            note = "" if len(vals) == N_FF_CHANNELS else f" ({len(vals)} values fitted to {N_FF_CHANNELS})"
            return "gains", gains, f"gains <- {where}: {gains}{note}", note
        if cand["drive"] is None:
            return None, None, "This node has no drive parameters (pick an entry or its Qubit).", ""
        vals, where = cand["drive"]
        return "drive", vals, (f"drive <- {where}: freq {_fmt(vals['freq'])}, gain {_fmt(vals['gain'])}, "
                               f"sigma_us {_fmt(vals['sigma_us'])}"), ""

    def _update_json_preview(self) -> None:
        if not hasattr(self, "use_btn"):
            return
        kind, _payload, text, _note = self._applicable()
        self.json_preview.setText(text)
        self.use_btn.setEnabled(kind is not None)

    def _use_json_selection(self) -> None:
        kind, payload, _text, _note = self._applicable()
        ref = self._selected_ref()
        if kind is None or ref is None:
            return
        if kind == "gains":
            self._segments[ref[1]].gains = list(payload)
            self._status.setText(f"Set segment {ref[1]} gains from the JSON.")
        else:
            drv = self._segments[ref[1]].drives[ref[2]]
            drv.freq, drv.gain, drv.sigma_us = payload["freq"], payload["gain"], payload["sigma_us"]
            self._status.setText(f"Set drive {ref[2]} of segment {ref[1]} (freq, gain, sigma_us) from the JSON.")
        self._rebuild_table(select=ref)
        self._after_change()

    # ----- structure edits -----

    def _after_change(self) -> None:
        self._redraw()
        self._update_file_label()
        self._update_json_preview()

    def _add_segment(self):
        self._segments.append(_default_segment())
        si = len(self._segments) - 1
        self._rebuild_table(select=("segment", si))
        self._after_change()
        self._status.setText(f"Added segment {si}.")

    def _duplicate_segment(self):
        si = self._selected_segment_index()
        if si is None:
            QMessageBox.information(self, "Select", "Select a segment to duplicate.")
            return
        self._segments.insert(si + 1, copy.deepcopy(self._segments[si]))
        self._rebuild_table(select=("segment", si + 1))
        self._after_change()
        self._status.setText(f"Duplicated segment {si} as segment {si + 1}.")

    def _delete_segment(self):
        si = self._selected_segment_index()
        if si is None:
            QMessageBox.information(self, "Select", "Select a segment to delete.")
            return
        if len(self._segments) <= 1:
            QMessageBox.information(self, "Keep one", "A program needs at least one segment.")
            return
        del self._segments[si]
        self._rebuild_table(select=("segment", min(si, len(self._segments) - 1)))
        self._after_change()
        self._status.setText(f"Deleted segment {si}.")

    def _add_drive(self):
        si = self._selected_segment_index()
        if si is None:
            QMessageBox.information(self, "Select", "Select a segment to add a drive to.")
            return
        self._segments[si].drives.append(_default_drive())
        self._rebuild_table(select=("drive", si, len(self._segments[si].drives) - 1))
        self._after_change()
        self._status.setText(f"Added drive to segment {si}; edit its values in the table.")

    def _delete_drive(self):
        ref = self._selected_ref()
        if ref is None or ref[0] != "drive":
            QMessageBox.information(self, "Select", "Select a drive row to delete.")
            return
        _, si, di = ref
        del self._segments[si].drives[di]
        self._rebuild_table(select=("segment", si))
        self._after_change()
        self._status.setText(f"Deleted drive {di} from segment {si}.")

    # ----- file actions -----

    def _payload(self) -> dict:
        meta = dict(self._meta)
        meta["readout_group"] = self._selected_readout_group()
        return {"meta": meta, "segments": [_segment_to_dict(s) for s in self._segments]}

    def _serialized(self) -> str:
        return json.dumps(self._payload(), sort_keys=True, default=str)

    def _reset_baseline(self) -> None:
        self._baseline = self._serialized()
        self._update_file_label()

    def _is_dirty(self) -> bool:
        return self._serialized() != self._baseline

    def _update_file_label(self) -> None:
        if self._path:
            self.file_label.setText(os.path.basename(self._path) + ("  *  (unsaved changes)" if self._is_dirty() else ""))
            self.file_label.setToolTip(self._path)
        else:
            self.file_label.setText("(not saved to a file)")
            self.file_label.setToolTip("")
        bold = self.file_label.font()
        bold.setBold(bool(self._path) and self._is_dirty())
        self.file_label.setFont(bold)

    def _ask_save_changes(self) -> str:
        """'save' | 'discard' | 'cancel' (separate so tests can answer it)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Unsaved changes")
        box.setText(f"{os.path.basename(self._path)} has unsaved changes.")
        save = box.addButton("Save", QMessageBox.AcceptRole)
        discard = box.addButton("Don't Save", QMessageBox.DestructiveRole)
        cancel = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(save)
        box.setEscapeButton(cancel)
        box.exec_()
        clicked = box.clickedButton()
        return "save" if clicked is save else "discard" if clicked is discard else "cancel"

    def _confirm_discard(self) -> bool:
        """True when it is fine to replace the current program: it was not loaded / saved, or has no
        changes since, or the user chose Save (and it succeeded) / Don't Save."""
        if not self._path or not self._is_dirty():
            return True
        answer = self._ask_save_changes()
        if answer == "cancel":
            return False
        return self._save_program() if answer == "save" else True

    def _new_program(self):
        if not self._confirm_discard():
            return
        self._segments = [_default_segment()]
        self._meta = {}
        self._path = None
        self._rebuild_table(select=("segment", 0))
        self._reset_baseline()
        self._redraw()
        self._status.setText("New program.")

    def _save_program(self) -> bool:
        """Save via a file dialog pre-filled with the current file. False if cancelled / failed."""
        os.makedirs(_PROGRAMS_DIR, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save program", self._path or _PROGRAMS_DIR, "JSON (*.json)")
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            save_program(path, self._segments, self._payload()["meta"])
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return False
        self._path = path
        self._reset_baseline()
        self._status.setText(f"Saved {path}.")
        return True

    def _load_program(self):
        if not self._confirm_discard():
            return
        os.makedirs(_PROGRAMS_DIR, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            self, "Load program", os.path.dirname(self._path) if self._path else _PROGRAMS_DIR, "JSON (*.json)")
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
        self._meta = {k: v for k, v in (meta or {}).items() if k != "readout_group"}
        rg = (meta or {}).get("readout_group")
        if rg:
            idx = self.readout_combo.findText(rg)
            if idx >= 0:
                self.readout_combo.blockSignals(True)
                self.readout_combo.setCurrentIndex(idx)
                self.readout_combo.blockSignals(False)
        self._path = path
        self._rebuild_table(select=("segment", 0))
        self._reset_baseline()
        self._redraw()
        self._status.setText(f"Loaded {path} ({len(segments)} segments).")

    # ----- plot -----

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_json()                       # calibration runs edit the JSON without a load hook
        self._redraw()

    def _redraw(self):
        # Guard: combo/refresh wiring can fire before the canvas exists.
        if getattr(self, "_ax", None) is None:
            return
        self._ax.clear()
        jd = self._qubit_json()
        cfg_like = {
            "ProgramBuilderInfo": self._segments,
            "n_ff_channels": N_FF_CHANNELS,
            "readout_groups": {g: groups_of(jd, "drive_groups")[g] for g in readout_group_names(jd)},  # plot_program reads FF_Pulses/entries of readout groups
        }
        try:
            ProgramBuilder.plot_program(
                cfg_like, readout_group=self._selected_readout_group(), ax=self._ax)
            self._ax.set_title("")                # the tab is obviously a program timeline: reclaim the height
        except Exception as e:
            # plot_program is meant to self-contain its errors; this is a final net.
            self._ax.clear(); self._ax.set_axis_off()
            self._ax.text(0.5, 0.5, f"Plot failed:\n{e}\n\n{traceback.format_exc()}",
                          ha="center", va="center", fontsize=7, family="monospace",
                          transform=self._ax.transAxes)
        self._fig.tight_layout()
        self._canvas.draw_idle()
