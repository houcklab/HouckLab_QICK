"""Right panel: the selected block's fields.

Every field row has a source picker (Value, Calibration, Sweep, From previous), an editor
for that source, and the value it resolves to (or the problem) underneath. Per-qubit
fields show one cell per channel: with a Value source the cells are the value; with any
other source they show the resolved numbers and typing in a cell overrides that one
entry (shown bold), like FF_override in qubit_parameters.json.
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QToolButton,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ...core.block import ACT_LABELS, ACTS, FieldSpec, SegmentBlock
from ...core.params import FromPrev, Ref, Sweep, Value, VectorSource, format_value, base_source
from ...core.sequence import sweep_users_text
from .. import icons, style
from ..widgets import Dropdown, InfoIcon, restyle as _restyle

SOURCE_LABELS = {"value": "Value", "ref": "Calibration", "sweep": "Sweep", "from_prev": "From previous"}


def _kind(src) -> str:
    return getattr(base_source(src), "kind", "value")


def _fmt_value(v, unit="") -> str:
    if v is None:
        return "—"
    if isinstance(v, list):
        inner = ", ".join("—" if x is None else (f"{x:.0f}" if isinstance(x, float) and abs(x) >= 100
                                                       else format_value(x)) for x in v)
        return f"[{inner}]"
    s = format_value(v)
    return f"{s} {unit}".strip()


# ======================================================================= calibration picker
class CalibrationPicker(QDialog):
    """Browse qubit_parameters.json and pick a value; ``result_path`` is the chosen calib: path."""

    def __init__(self, calib, start_path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick a calibration value")
        self.resize(640, 520)
        self.calib = calib
        self.result_path = None
        lay = QVBoxLayout(self)
        info = QLabel("Choose a value from the calibration file. In the path you can replace an entry name with "
                      "a placeholder such as {qubit} or {readout_group} to follow the block's own fields.")
        info.setWordWrap(True)
        info.setObjectName("muted")
        lay.addWidget(info)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Key", "Value"])
        self.tree.setColumnWidth(0, 300)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemExpanded.connect(self._expand)
        self.tree.itemDoubleClicked.connect(lambda it, _: self._accept_item(it))
        lay.addWidget(self.tree, 1)
        self.path_edit = QLineEdit(start_path)
        lay.addWidget(self.path_edit)
        self.tree.currentItemChanged.connect(
            lambda it, _: it and self.path_edit.setText("calib:" + it.data(0, Qt.UserRole)))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Use this value")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._fill(self.tree.invisibleRootItem(), "")

    def _fill(self, parent, path):
        for key, is_branch, preview in self.calib.children(path):
            full = f"{path}/{key}" if path else key
            it = QTreeWidgetItem([key, "" if is_branch else preview])
            it.setData(0, Qt.UserRole, full)
            if is_branch:
                it.setText(1, preview)
                it.addChild(QTreeWidgetItem(["…"]))         # placeholder; filled when expanded
            parent.addChild(it)

    def _expand(self, it):
        if it.childCount() == 1 and it.child(0).text(0) == "…":
            it.takeChild(0)
            self._fill(it, it.data(0, Qt.UserRole))

    def _accept_item(self, it):
        if it.childCount() == 0:
            self.path_edit.setText("calib:" + it.data(0, Qt.UserRole))
            self._accept()

    def _accept(self):
        self.result_path = self.path_edit.text().strip()
        self.accept()


# ======================================================================= field row
class FieldRow(QFrame):
    """One field: label with help icon, source picker, an editor for that source, and underneath
    the value it resolves to (or the problem). Edits are sent as ``commit(field name, new source)``."""
    commit = pyqtSignal(str, object)        # field name, new source

    def __init__(self, panel: "InspectorPanel", block, spec: FieldSpec):
        super().__init__()
        self.setObjectName("field_card")
        self.panel, self.block, self.spec = panel, block, spec
        self.src = block.fields[spec.name]
        self.focus_widget: Optional[QWidget] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(4)
        label = QLabel(spec.label + (f"  ({spec.unit})" if spec.unit else ""))
        label.setObjectName("field_label")
        head.addWidget(label)
        if spec.doc:
            head.addWidget(InfoIcon(spec.doc))
        head.addStretch(1)
        if len(spec.sources) > 1:
            self.source_combo = Dropdown()
            self.source_combo.setObjectName("source_combo")
            for k in spec.sources:
                self.source_combo.addItem(SOURCE_LABELS[k], k)
            self.source_combo.setCurrentIndex(max(0, list(spec.sources).index(_kind(self.src))
                                                  if _kind(self.src) in spec.sources else 0))
            self.source_combo.setToolTip("Where this value comes from: typed in, read from the calibration file, "
                                         "a sweep axis, or the previous segment.")
            self.source_combo.activated.connect(self._source_changed)
            head.addWidget(self.source_combo)
        lay.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(4)
        lay.addLayout(self.body)
        self.hint = QLabel()
        self.hint.setObjectName("field_hint")
        self.hint.setWordWrap(True)
        self.hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.hint)
        self.cells: list = []
        self._build_editor()

    # ---------------------------------------------------------------- editors
    def _build_editor(self):
        spec, src = self.spec, self.src
        base = base_source(src)
        if isinstance(base, Ref):
            row = QHBoxLayout()
            self.ref_edit = QLineEdit(base.path)
            self.ref_edit.setObjectName("ref_path")
            try:
                filled = base.filled(self.block.template_values()).path
            except KeyError:
                filled = base.path
            self.ref_edit.setToolTip(filled if filled == base.path else f"{base.path}\n\u2192 {filled}")
            self.ref_edit.setCursorPosition(0)
            self.ref_edit.editingFinished.connect(self._ref_edited)
            row.addWidget(self.ref_edit, 1)
            if base.store != "station":
                btn = QToolButton()
                btn.setIcon(icons.icon("database", style.COLORS["text_muted"], 15))
                btn.setToolTip("Browse the calibration file")
                btn.clicked.connect(self._browse)
                row.addWidget(btn)
            if base.scale != 1.0:
                sc = QLabel(f"× {base.scale:g}")
                sc.setObjectName("muted")
                row.addWidget(sc)
            self.body.addLayout(row)
            self.focus_widget = self.ref_edit
        elif isinstance(base, Sweep):
            self._sweep_editor(base.axis)
        elif isinstance(base, FromPrev):
            lbl = QLabel("Starts where the previous segment ends.")
            lbl.setObjectName("muted")
            self.body.addWidget(lbl)
        if spec.is_vector:
            self._vector_cells(isinstance(base, Value))
        elif isinstance(base, Value):
            self._scalar_editor(base.value)

    def _sweep_editor(self, axis_name: str):
        """Which axis the field follows, that axis's range (edited here or in the Experiment tab:
        it is the same axis), and what else moves with it."""
        self.axis_name = axis_name
        self.axis_combo = Dropdown()
        self.axis_combo.setObjectName("axis_combo")
        self.axis_combo.setToolTip("The sweep axis this field follows. Every field on the same axis takes the "
                                   "same value at each sweep point.")
        for a in self.panel.ctl.seq.settings.sweeps:
            self.axis_combo.addItem(a.name, a.name)
        self.axis_combo.addItem("New axis…", "__new__")
        i = self.axis_combo.findData(axis_name)
        self.axis_combo.setCurrentIndex(i if i >= 0 else 0)
        self.axis_combo.activated.connect(lambda _: self._axis_chosen(self.axis_combo.currentData()))
        self.body.addWidget(self.axis_combo)
        self.focus_widget = self.axis_combo
        self.axis_edits = {}
        if self.panel.ctl.seq.settings.axis(axis_name) is None:
            return                              # the resolver reports the missing axis under the field
        row = QHBoxLayout()
        row.setSpacing(4)
        for key, label, width in (("start", "from", 64), ("stop", "to", 64), ("points", None, 52)):
            if label:
                lab = QLabel(label)
                lab.setObjectName("muted")
                row.addWidget(lab)
            e = QLineEdit()
            e.setObjectName("axis_" + key)
            e.setMinimumWidth(width)
            e.setAlignment(Qt.AlignRight)
            e.editingFinished.connect(lambda key=key, e=e: self._axis_edited(key, e))
            row.addWidget(e, 1)
            self.axis_edits[key] = e
            if key == "stop":
                self.axis_unit = QLabel()
                self.axis_unit.setObjectName("muted")
                row.addWidget(self.axis_unit)
        pts = QLabel("points")
        pts.setObjectName("muted")
        row.addWidget(pts)
        self.body.addLayout(row)
        self.axis_note = QLabel()
        self.axis_note.setObjectName("muted")
        self.axis_note.setWordWrap(True)
        self.body.addWidget(self.axis_note)
        link = QPushButton("All sweep axes in the Experiment tab →")
        link.setObjectName("flat")
        link.setCursor(Qt.PointingHandCursor)
        link.clicked.connect(self.panel.request_experiment_tab.emit)
        hl = QHBoxLayout()
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(link)
        hl.addStretch(1)
        self.body.addLayout(hl)
        self.refresh_sweep()

    def refresh_sweep(self) -> None:
        """Show the axis as it is now (after an edit here, in the Experiment tab, or an undo)."""
        edits = getattr(self, "axis_edits", None)
        if not edits:
            return
        seq = self.panel.ctl.seq
        axes = seq.settings.sweeps
        a = seq.settings.axis(self.axis_name)
        if a is None:
            return
        for key, text in (("start", f"{a.start:g}"), ("stop", f"{a.stop:g}"), ("points", str(a.points))):
            if not edits[key].hasFocus():
                edits[key].setText(text)
        self.axis_unit.setText(a.unit)
        others = [(b, s) for b, s in seq.sweep_users().get(a.name, [])
                  if not (b.id == self.block.id and s.name == self.spec.name)]
        k = [x.name for x in axes].index(a.name)
        if len(axes) == 1:
            loop = f"Each of the {a.points} points runs the whole sequence {seq.settings.reps} times."
        else:
            where = "outermost" if k == 0 else "innermost" if k == len(axes) - 1 else "middle"
            loop = (f"Loop {k + 1} of {len(axes)} ({where}); the axes multiply to "
                    f"{seq.settings.n_points():,} points, each run {seq.settings.reps} times.")
        moves = f"Also follows ‹{a.name}›: {sweep_users_text(others)}." if others else ""
        self.axis_note.setText(f"{loop}\n{moves}".strip())

    def _axis_edited(self, key: str, e: QLineEdit):
        text = e.text().strip()
        a = self.panel.ctl.seq.settings.axis(self.axis_name)
        if a is None:
            return
        try:
            value = float(text) if key != "points" else int(float(text))
            if key == "points" and value < 1:
                raise ValueError
        except ValueError:
            self.hint.setObjectName("field_error")
            self.hint.setText("Points must be a whole number of at least 1." if key == "points"
                              else f"{text!r} is not a number. Not applied.")
            self.hint.setVisible(True)
            _restyle(self.hint)
            e.setText(f"{getattr(a, key):g}" if key != "points" else str(a.points))
            return
        if getattr(a, key) != value:
            self.panel.ctl.update_sweep_axis(self.axis_name, **{key: value})

    def _scalar_editor(self, v):
        spec = self.spec
        if spec.ftype == "choice":
            w = Dropdown()
            w.addItems(list(spec.choices))
            w.setCurrentText(str(v))
            w.activated.connect(lambda _: self.commit.emit(spec.name, Value(w.currentText())))
        elif spec.ftype == "qubit":
            w = QSpinBox()
            w.setRange(1, self.panel.ctl.station.n_channels)
            w.setValue(int(v) if v else 1)
            w.setPrefix("Q")
            w.editingFinished.connect(lambda: self.commit.emit(spec.name, Value(w.value())))
        elif spec.ftype == "qubits":
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(3)
            chosen = set(int(x) for x in (v or []))
            buttons = []
            for q in range(1, self.panel.ctl.station.n_channels + 1):
                b = QPushButton(f"Q{q}")
                b.setCheckable(True)
                b.setChecked(q in chosen)
                b.setFixedWidth(36)
                b.setStyleSheet(self._qubit_toggle_css(q))
                buttons.append(b)
                h.addWidget(b)
            h.addStretch(1)

            def emit():
                self.commit.emit(spec.name, Value([q for q, b in enumerate(buttons, 1) if b.isChecked()]))
            for b in buttons:
                b.toggled.connect(lambda _: emit())
        elif spec.options:
            w = Dropdown()
            w.setEditable(True)
            w.setInsertPolicy(QComboBox.NoInsert)
            opts = self.panel.option_list(spec, self.block)
            blank = "(qubit number)" if spec.name == "entry" else None
            if blank:
                w.addItem(blank, "")
            for o in opts:
                w.addItem(o, o)
            cur = "" if v is None else str(v)
            i = w.findData(cur)
            if i < 0 and cur:
                w.addItem(f"{cur}  (not in file)", cur)
                i = w.count() - 1
            w.setCurrentIndex(max(0, i))
            if not opts:
                w.setToolTip("No choices found in the calibration file; type a name.")

            def commit_choice(_=None, w=w):
                # a listed item commits its data ("" for "(qubit number)"); typed text commits as typed
                data = w.currentData()
                text = w.currentText().strip()
                val = data if data is not None and w.itemText(w.currentIndex()) == text else text
                if val == "(qubit number)":
                    val = ""
                if val != cur:
                    self.commit.emit(spec.name, Value(val))
            w.activated.connect(commit_choice)
            w.lineEdit().editingFinished.connect(commit_choice)
        elif spec.ftype == "bool":
            w = QCheckBox()
            w.setChecked(bool(v))
            w.toggled.connect(lambda on: self.commit.emit(spec.name, Value(bool(on))))
        else:
            w = QLineEdit("" if v is None else format_value(v) if not isinstance(v, str) else v)
            w.editingFinished.connect(lambda: self._scalar_edited(w))
        self.body.addWidget(w)
        self.focus_widget = w

    def _qubit_toggle_css(self, q):
        col = style.QUBIT_COLORS[(q - 1) % 8]
        c = style.COLORS
        return (f"QPushButton {{ padding: 2px 0px; border: 1px solid {c['border_dark']}; border-radius: 5px; "
                f"background: {c['bg']}; font-size: 11px; }}"
                f"QPushButton:checked {{ background: {col}; color: white; border: 1px solid {col}; "
                f"font-weight: 600; }}")

    def _vector_cells(self, editable_values: bool):
        n = self.panel.ctl.station.n_channels
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(5, 1)
        grid.setColumnStretch(7, 1)
        grid.setVerticalSpacing(4)
        base = base_source(self.src)
        literal = list(base.value) if isinstance(base, Value) and isinstance(base.value, (list, tuple)) else None
        overrides = self.src.overrides if isinstance(self.src, VectorSource) else {}
        self.cells = []
        for j in range(n):
            lab = QLabel(f"Q{j + 1}")
            lab.setObjectName("muted")
            e = QLineEdit()
            e.setObjectName("vec_cell")
            e.setMinimumWidth(52)
            e.setAlignment(Qt.AlignRight)
            if editable_values and literal is not None and j < len(literal):
                e.setText("" if literal[j] is None else format_value(literal[j]))
            elif j in overrides:
                e.setText(format_value(overrides[j]))
                e.setObjectName("override")
                e.setToolTip("Overrides the referenced value for this channel. Clear to use the reference.")
            e.editingFinished.connect(lambda j=j, e=e: self._cell_edited(j, e, editable_values))
            r, cpos = divmod(j, 4)
            grid.addWidget(lab, r, cpos * 2)
            grid.addWidget(e, r, cpos * 2 + 1)
            self.cells.append(e)
        self.body.addLayout(grid)
        if self.focus_widget is None and self.cells:
            self.focus_widget = self.cells[0]

    # ---------------------------------------------------------------- resolved hint
    def show_resolved(self, value, problem: Optional[str]):
        base = base_source(self.src)
        if problem:
            self.hint.setObjectName("field_error")
            self.hint.setText(problem)
        else:
            self.hint.setObjectName("field_hint")
            if self.spec.is_vector and not isinstance(base, Value):
                txt = ""
                for j, e in enumerate(self.cells):
                    if value is not None and j < len(value) and e.objectName() != "override":
                        e.setPlaceholderText("—" if value[j] is None else f"{value[j]:.0f}")
            elif self.spec.is_vector or (isinstance(base, Value)
                                         and self.spec.ftype in ("choice", "qubit", "qubits", "bool", "str")):
                txt = ""                        # the editor already shows the value
            else:
                txt = "= " + _fmt_value(value, self.spec.unit) if value is not None else ""
                n = self.panel.ctl.seq.settings.n_points()
                if txt and isinstance(base, Sweep) and n > 1:
                    txt += f" at the preview point ({self.panel.ctl.preview_index + 1} of {n:,})"
            self.hint.setText(txt)
        self.hint.setVisible(bool(self.hint.text()))
        _restyle(self.hint)

    # ---------------------------------------------------------------- commits
    def _wrap(self, base):
        if self.spec.is_vector:
            ov = self.src.overrides if isinstance(self.src, VectorSource) and not isinstance(base, Value) else {}
            return VectorSource(base, dict(ov))
        return base

    def _source_changed(self, _):
        kind = self.source_combo.currentData()
        if kind == _kind(self.src):
            return
        resolved = self.panel.resolved_value(self.spec.name)
        if kind == "value":                     # keep the number currently in use, so nothing jumps
            v = resolved
            if v is None:
                d = base_source(self.spec.make_default())
                v = d.value if isinstance(d, Value) else ([0.0] * self.panel.ctl.station.n_channels
                                                          if self.spec.is_vector else 0.0)
            new = Value(v)
        elif kind == "ref":
            d = base_source(self.spec.make_default())
            new = d if isinstance(d, Ref) else Ref("calib:")
        elif kind == "sweep":
            axes = self.panel.ctl.seq.settings.sweeps
            if not axes:
                self._sweep_new_axis()
                return
            new = Sweep(axes[0].name)
        else:
            new = FromPrev()
        self.commit.emit(self.spec.name, self._wrap(new))

    def _ref_edited(self):
        path = self.ref_edit.text().strip()
        base = base_source(self.src)
        if path and path != base.path:
            if ":" not in path:
                path = "calib:" + path
            self.commit.emit(self.spec.name, self._wrap(Ref(path, base.scale)))

    def _browse(self):
        base = base_source(self.src)
        dlg = CalibrationPicker(self.panel.ctl.calib, base.path, self)
        if dlg.exec_() and dlg.result_path:
            self.commit.emit(self.spec.name, self._wrap(Ref(dlg.result_path, base.scale)))

    def _sweep_new_axis(self) -> None:
        """Add a sweep axis named after this field (0 to twice its current value, 21 points) and sweep
        the field over it, as one undo step."""
        cur = self.panel.resolved_value(self.spec.name)
        cur = cur if isinstance(cur, (int, float)) else 1.0
        ctl = self.panel.ctl
        with ctl.undo_group(f"Sweep {self.spec.label}"):
            axis = ctl.add_sweep_axis(self.spec.name.replace("_us", ""), 0.0, float(cur) * 2 or 1.0, 21,
                                      self.spec.unit)
            self.commit.emit(self.spec.name, self._wrap(Sweep(axis)))

    def _axis_chosen(self, axis):
        if axis == "__new__":
            self._sweep_new_axis()               # its range is edited right here, under the axis
            return
        self.commit.emit(self.spec.name, self._wrap(Sweep(axis)))

    def _scalar_edited(self, w: QLineEdit):
        text = w.text().strip()
        spec = self.spec
        try:
            if spec.ftype == "float":
                v = float(text)
            elif spec.ftype == "int":
                v = int(round(float(text)))
            elif spec.name == "relative_t":
                v = "auto" if text.lower() in ("", "auto") else float(text)
            else:
                v = text
        except ValueError:
            w.setObjectName("bad")
            _restyle(w)
            self.hint.setObjectName("field_error")
            self.hint.setText(f"Enter a number{' or auto' if spec.name == 'relative_t' else ''}.")
            self.hint.setVisible(True)
            _restyle(self.hint)
            return
        cur = base_source(self.src)
        if isinstance(cur, Value) and cur.value == v:
            return
        self.commit.emit(spec.name, Value(v))

    def _cell_edited(self, j, e: QLineEdit, editable_values: bool):
        """With a Value source the cells are the list itself. With any other source a typed cell
        is an override for that channel, and clearing the cell removes the override."""
        text = e.text().strip()
        if editable_values:
            base = base_source(self.src)
            vals = list(base.value) if isinstance(base.value, (list, tuple)) else [base.value] * len(self.cells)
            vals = (vals + [0.0] * len(self.cells))[:len(self.cells)]
            if text == "" or text.lower() == "none":
                if not self.spec.nullable:
                    return
                new = None
            else:
                try:
                    new = float(text)
                except ValueError:
                    return
            if vals[j] == new:
                return
            vals[j] = new
            self.commit.emit(self.spec.name, VectorSource(Value(vals)))
        else:
            ov = dict(self.src.overrides) if isinstance(self.src, VectorSource) else {}
            if text == "":
                if j not in ov:
                    return
                ov.pop(j)
            else:
                try:
                    v = float(text)
                except ValueError:
                    return
                if ov.get(j) == v:
                    return
                ov[j] = v
            self.commit.emit(self.spec.name, VectorSource(base_source(self.src), ov))


# ======================================================================= panel
class InspectorPanel(QWidget):
    """The selected block's name, act and fields. Rebuilt whenever the selection changes."""
    request_experiment_tab = pyqtSignal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.ctl = controller
        self._block_id = None
        self._block_snapshot = None
        self._axes_snapshot: list = []
        self.rows: dict = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(6)
        t = QLabel("Inspector")
        t.setObjectName("section_title")
        wrap = QHBoxLayout()
        wrap.setContentsMargins(8, 0, 8, 0)
        wrap.addWidget(t)
        outer.addLayout(wrap)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self.scroll, 1)
        controller.selection_changed.connect(lambda _: self.rebuild())
        controller.changed.connect(self._maybe_rebuild)
        controller.refreshed.connect(self.update_resolved)
        self.rebuild()

    # ---------------------------------------------------------------- data
    def _resolved_params(self) -> dict:
        res = self.ctl.resolved
        if res is None or self._block_id is None:
            return {}
        return res.params_by_block().get(self._block_id, {})

    def option_list(self, spec, block) -> list:
        """Choices for a group/entry field, read from the calibration file."""
        calib = self.ctl.calib
        try:
            if spec.options == "readout_groups":
                return calib.readout_groups()
            if spec.options.startswith("calib:"):
                path = spec.options.split(":", 1)[1]
                vals = block.template_values()
                if spec.name == "entry":
                    vals.pop("entry", None)          # an entry list must not be filtered by its own value
                for k, v in vals.items():
                    path = path.replace("{" + k + "}", str(v))
                if "{" in path:
                    return []
                return [k for k, is_branch, _ in calib.children(path) if is_branch]
        except Exception:
            return []
        return []

    def resolved_value(self, name):
        return self._resolved_params().get(name)

    def _rename_block(self, b, edit: QLineEdit) -> None:
        current = self.ctl.seq.get(b.id)
        if current is None:
            return
        text = edit.text().strip()
        if not text:
            edit.setText(current.name)               # an empty name is not allowed; put the old one back
        elif text != current.name:
            self.ctl.rename(b.id, text)

    def _maybe_rebuild(self):
        """Rebuild only when the selected block itself changed, or the list of sweep axes did (the axis
        dropdowns list them). Other edits, such as an axis's range, refresh the form in place."""
        b = self.ctl.seq.get(self.ctl.selected) if self.ctl.selected else None
        snap = b.to_dict() if b else None
        axes = [a.name for a in self.ctl.seq.settings.sweeps]
        if snap != self._block_snapshot or self.ctl.selected != self._block_id or axes != self._axes_snapshot:
            self.rebuild()
            return
        for row in self.rows.values():
            try:
                row.refresh_sweep()
            except RuntimeError:                 # row deleted during rebuild
                pass

    # ---------------------------------------------------------------- build
    def rebuild(self):
        focused = None
        fw = self.focusWidget()
        for name, row in self.rows.items():
            if fw is not None and row.isAncestorOf(fw):
                focused = name
        b = self.ctl.seq.get(self.ctl.selected) if self.ctl.selected else None
        self._block_id = b.id if b else None
        self._block_snapshot = b.to_dict() if b else None
        self._axes_snapshot = [a.name for a in self.ctl.seq.settings.sweeps]
        body = QWidget()
        body.setObjectName("inspector_body")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 12)
        lay.setSpacing(0)
        self.rows = {}
        if b is None:
            lay.addWidget(self._empty_state())
        else:
            lay.addWidget(self._header(b))
            basic = [f for f in b.FIELDS if not f.advanced]
            adv = [f for f in b.FIELDS if f.advanced]
            for spec in basic:
                lay.addWidget(self._row(b, spec))
            if adv:
                toggle = QPushButton(f"Advanced ({len(adv)})")
                toggle.setObjectName("flat")
                toggle.setCheckable(True)
                box = QWidget()
                bl = QVBoxLayout(box)
                bl.setContentsMargins(0, 0, 0, 0)
                bl.setSpacing(0)
                for spec in adv:
                    bl.addWidget(self._row(b, spec))
                # open the Advanced section when any of its fields is not at its default
                show = any(_kind(b.fields[s.name]) != _kind(s.make_default()) or
                           b.fields[s.name] != s.make_default() for s in adv)
                box.setVisible(show)
                toggle.setChecked(show)
                toggle.toggled.connect(box.setVisible)
                hl = QHBoxLayout()
                hl.setContentsMargins(8, 6, 8, 2)
                hl.addWidget(toggle)
                hl.addStretch(1)
                lay.addLayout(hl)
                lay.addWidget(box)
        lay.addStretch(1)
        old = self.scroll.takeWidget()
        self.scroll.setWidget(body)
        if old is not None:
            old.deleteLater()
        self.update_resolved()
        if focused and focused in self.rows and self.rows[focused].focus_widget is not None:
            QTimer.singleShot(0, self.rows[focused].focus_widget.setFocus)

    def _row(self, b, spec):
        row = FieldRow(self, b, spec)
        row.commit.connect(lambda name, src, bid=b.id: self.ctl.set_field(bid, name, src))
        self.rows[spec.name] = row
        return row

    def _header(self, b) -> QWidget:
        w = QFrame()
        w.setObjectName("field_card")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 6, 12, 10)
        lay.setSpacing(6)
        kind = {"segment": "Flux segment", "pulse": "Pulse", "measure": "Readout"}[b.KIND]
        top = QHBoxLayout()
        tl = QLabel(f"{b.LABEL}  ·  {kind}")
        tl.setObjectName("muted")
        top.addWidget(tl)
        top.addStretch(1)
        muted = style.COLORS["text_muted"]
        if b.KIND != "measure":
            dup = QToolButton()
            dup.setIcon(icons.icon("duplicate", muted, 15))
            dup.setToolTip(f"Duplicate: insert a copy right after this block ({style.shortcut_text('Ctrl+D')})")
            dup.clicked.connect(lambda: self.ctl.duplicate(b.id))
            top.addWidget(dup)
        rm = QToolButton()
        rm.setIcon(icons.icon("trash", muted, 15))
        rm.setToolTip("Delete this block (Del)")
        rm.clicked.connect(lambda: self.ctl.remove(b.id))
        top.addWidget(rm)
        lay.addLayout(top)
        name = QLineEdit(b.name)
        name.setObjectName("block_title")
        name.editingFinished.connect(lambda: self._rename_block(b, name))
        lay.addWidget(name)
        if isinstance(b, SegmentBlock):
            row = QHBoxLayout()
            al = QLabel("Act")
            al.setObjectName("field_label")
            row.addWidget(al)
            row.addWidget(InfoIcon("Which band the segment sits in on the canvas. Acts organize the sequence "
                                   "and must run preparation \u2192 dynamics \u2192 readout; they don't change "
                                   "the compiled program."))
            act = Dropdown()
            for a in ACTS:
                if a in b.ALLOWED_ACTS:
                    act.addItem(ACT_LABELS[a], a)
            act.setCurrentIndex(max(0, act.findData(b.act)))
            act.activated.connect(lambda _: self.ctl.set_act(b.id, act.currentData()))
            row.addWidget(act, 1)
            lay.addLayout(row)
        d = QLabel(b.DESCRIPTION)
        d.setObjectName("muted")
        d.setWordWrap(True)
        lay.addWidget(d)
        self._block_problems = QLabel()
        self._block_problems.setObjectName("field_error")
        self._block_problems.setWordWrap(True)
        self._block_problems.setVisible(False)
        lay.addWidget(self._block_problems)
        return w

    def _empty_state(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 16, 14, 16)
        lay.setSpacing(8)
        h = QLabel("Nothing selected")
        h.setObjectName("block_title")
        lay.addWidget(h)
        seq = self.ctl.seq
        txt = QLabel("Click a block on the canvas to edit its fields, or drag a new one in from the palette.\n\n"
                     f"This sequence: {len(seq.segments)} segment{'s' if len(seq.segments) != 1 else ''}, "
                     f"{len(seq.pulses)} pulse{'s' if len(seq.pulses) != 1 else ''}, "
                     f"{'a Measure block' if seq.measure else 'no Measure block'}, "
                     f"{seq.settings.n_points()} sweep point{'s' if seq.settings.n_points() != 1 else ''}.")
        txt.setObjectName("muted")
        txt.setWordWrap(True)
        lay.addWidget(txt)
        return w

    def update_resolved(self):
        if self._block_id is None:
            return
        params = self._resolved_params()
        probs = self.ctl.problems_for(self._block_id)
        by_field = {}
        for p in probs:
            if p.field:
                by_field.setdefault(p.field, p.message)
        for name, row in self.rows.items():
            try:
                row.show_resolved(params.get(name), by_field.get(name))
            except RuntimeError:  # row deleted during rebuild
                pass
        general = [p.message for p in probs if not p.field and p.level in ("error", "warning")]
        if hasattr(self, "_block_problems"):
            try:
                self._block_problems.setText("\n".join(general))
                self._block_problems.setVisible(bool(general))
            except RuntimeError:
                pass
