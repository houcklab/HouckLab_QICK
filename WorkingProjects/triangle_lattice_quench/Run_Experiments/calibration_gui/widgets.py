"""Shared Qt primitives used by more than one tab.

Tab-specific dialogs and widgets stay with their tab; this module holds only
the genuinely cross-tab widgets: the embeddable matplotlib canvas, the generic
param form, the drag-paint state machine and the two widgets built on it
(``MuxChipStrip`` on AutoCalib, ``CalibTable`` on AutoCalib + LatticePoint), the
selection-border delegate, and the agent combo-setter shared by the two-qubit
and pi/2-phase tabs.

Imports only Qt / matplotlib (and ``state``/``helpers`` if needed — none are at
present); no tab module is imported here, so widgets sits below the tabs in the
import DAG.
"""
from __future__ import annotations

from typing import Any, Optional

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPen
from PyQt5.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QSpinBox,
    QStyledItemDelegate, QTableWidget, QToolButton, QWidget,
)


class MplCanvas(FigureCanvas):
    """Embeddable matplotlib figure with a single axis."""
    def __init__(self, parent=None, height=4.0):
        self.fig = Figure(figsize=(7.0, height), tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)

    def reset(self):
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.draw()


class ParamForm(QGroupBox):
    """Generic dict<->form editor.

    spec is a list of (key, label, kind, default) where kind is one of
    'int', 'float', 'bool'. Read back with .values().
    """
    def __init__(self, title: str, spec: list[tuple[str, str, str, Any]]):
        super().__init__(title)
        self.spec = spec
        self.widgets: dict[str, QWidget] = {}
        layout = QFormLayout()
        for key, label, kind, default in spec:
            w = self._make_widget(kind, default)
            self.widgets[key] = w
            layout.addRow(label, w)
        self.setLayout(layout)

    def _make_widget(self, kind: str, default: Any) -> QWidget:
        if kind == "int":
            w = QSpinBox()
            w.setRange(-2**31, 2**31 - 1)
            w.setValue(int(default))
            return w
        if kind == "float":
            w = QDoubleSpinBox()
            w.setRange(-1e9, 1e9)
            w.setDecimals(4)
            w.setValue(float(default))
            return w
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(default))
            return w
        raise ValueError(f"unknown widget kind: {kind}")

    def values(self) -> dict:
        out = {}
        for key, _, kind, _ in self.spec:
            w = self.widgets[key]
            if kind == "int":
                out[key] = int(w.value())
            elif kind == "float":
                out[key] = float(w.value())
            elif kind == "bool":
                out[key] = bool(w.isChecked())
        return out

    def apply(self, overrides: dict) -> list[str]:
        """Set widget values from `overrides` (key->value), coercing by widget kind.
        Keys not in this form and None values are ignored. Returns the keys applied
        (used by agent_run to honor sweep params and report what actually changed)."""
        kinds = {key: kind for key, _, kind, _ in self.spec}
        applied = []
        for key, val in (overrides or {}).items():
            if key not in self.widgets or val is None:
                continue
            w = self.widgets[key]
            try:
                if kinds[key] == "int":
                    w.setValue(int(val))
                elif kinds[key] == "float":
                    w.setValue(float(val))
                elif kinds[key] == "bool":
                    w.setChecked(bool(val))
                else:
                    continue
            except (TypeError, ValueError):
                continue
            applied.append(key)
        return applied


# Per-cell "queued for re-run" selection flag. Encoded as a custom Qt
# item-data role + the delegate below, so the two visual layers are orthogonal.
SELECTION_ROLE = Qt.UserRole + 1


class CalibCellDelegate(QStyledItemDelegate):
    """Draw a 2px border around body cells whose SELECTION_ROLE is truthy.

    Status (last-run outcome) is encoded in the cell's QBrush background via
    setBackground; selection (queued for re-run) is encoded only here, so the
    two visual layers compose without one stomping the other.
    """

    BORDER_COLOR = QColor("#1f6feb")
    BORDER_WIDTH = 2

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if not index.data(SELECTION_ROLE):
            return
        painter.save()
        pen = QPen(self.BORDER_COLOR)
        pen.setWidth(self.BORDER_WIDTH)
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        # Inset by half the pen width so the stroke isn't clipped by the cell rect.
        inset = self.BORDER_WIDTH // 2
        rect = option.rect.adjusted(inset, inset, -inset - 1, -inset - 1)
        painter.drawRect(rect)
        painter.restore()


# ----- shared drag-paint state machine: rect / range / path -----------------


class DragPainter:
    """Click-drag-persistent toggle state machine.

    Region flavor is decided by the ``region`` callback the host supplies:
      - rectangle:   ``lambda s, c, _: cells_in_rect(s, c)``
      - linear range: ``lambda s, c, _: cells_in_range(s, c)``
      - path:        ``lambda s, c, prev: prev | {c}``  (no shrink semantics)

    On press, latches ``target = NOT get_state(start)`` and seeds the region.
    On move, recomputes the region; cells leaving revert to their snapshot,
    cells entering get ``target``. release() returns True iff a drag was in
    progress, so the host can emit any "I'm done" signal it owns.

    Host wires three callables: target_at(pos), get_state(key), set_state(key, on).
    """

    def __init__(self, target_at, get_state, set_state, region):
        self._target_at = target_at
        self._get_state = get_state
        self._set_state = set_state
        self._region_fn = region
        self._start = None
        self._target: bool = False
        self._snapshot: dict = {}
        self._region: set = set()

    def in_progress(self) -> bool:
        return self._start is not None

    def press(self, pos) -> bool:
        key = self._target_at(pos)
        if key is None:
            return False
        self._start = key
        self._target = not self._get_state(key)
        self._snapshot = {}
        self._region = set()
        self._update_to(key)
        return True

    def move(self, pos) -> None:
        if self._start is None:
            return
        key = self._target_at(pos)
        if key is None:
            return
        self._update_to(key)

    def release(self) -> bool:
        if self._start is None:
            return False
        self._start = None
        self._snapshot = {}
        self._region = set()
        return True

    def _update_to(self, current_key) -> None:
        new_region = self._region_fn(self._start, current_key, self._region)
        for k in self._region - new_region:
            self._set_state(k, self._snapshot.get(k, False))
        for k in new_region - self._region:
            self._snapshot.setdefault(k, self._get_state(k))
            self._set_state(k, self._target)
        self._region = new_region


# ----- chip strip: click-drag-persistent multi-toggle for MUX-readout pick --


class MuxChipStrip(QWidget):
    """Horizontal row of checkable qubit chips with click-drag-persistent toggle.

    Path-mode DragPainter: each chip the cursor visits during a stroke gets
    the latched check/uncheck state; dragging back over a chip does not
    revert it (no snapshot/restore). Emits selection_changed on release.

    Chips are mouse-transparent so all events route through the container —
    the toggle visual is driven by isChecked() only.
    """

    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chips: dict[str, QToolButton] = {}
        self._lo = QHBoxLayout(self)
        self._lo.setContentsMargins(4, 2, 4, 2)
        self._lo.setSpacing(4)
        self._lo.addStretch(1)
        self._painter = DragPainter(
            target_at=self._chip_at,
            get_state=lambda q: self._chips[q].isChecked(),
            set_state=lambda q, on: self._chips[q].setChecked(on),
            region=lambda s, c, prev: prev | {c},
        )

    def set_qubits(self, qubits: list, selected: list) -> None:
        for chip in self._chips.values():
            chip.setParent(None); chip.deleteLater()
        self._chips.clear()
        sel = set(selected)
        for q in qubits:
            chip = QToolButton(self)
            chip.setText(f"Q{q}")
            chip.setCheckable(True)
            chip.setChecked(q in sel)
            chip.setFocusPolicy(Qt.NoFocus)
            chip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._chips[q] = chip
            self._lo.insertWidget(self._lo.count() - 1, chip)

    def selected(self) -> list:
        return [q for q, c in self._chips.items() if c.isChecked()]

    def _chip_at(self, pos) -> Optional[str]:
        for q, c in self._chips.items():
            if c.geometry().contains(pos):
                return q
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or not self._painter.press(event.pos()):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._painter.move(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._painter.release():
            self.selection_changed.emit(self.selected())


# ----- table subclass: persistent per-cell enabled state + drag-paint -------


class CalibTable(QTableWidget):
    """QTableWidget whose body cells carry a persistent enabled/disabled flag.

    Selection is handled by the parent AutoCalibTab via this widget's mouse
    events: press latches a target state (= NOT current), and every body cell
    entered during the drag is set to that target. Header-row (row 0) and
    qubit-label column (col 0) clicks fire ``header_clicked`` / nothing
    respectively — parent decides what to do. We deliberately do NOT call
    super().mousePressEvent() so Qt's own selection model is never engaged
    (the parent sets ``setSelectionMode(NoSelection)``).
    """

    body_toggled = pyqtSignal(int, int, bool)   # (row, col, new_state)
    body_clicked = pyqtSignal(int, int)         # (row, col) — single click on body cell
    header_clicked = pyqtSignal(int)            # column of header row
    label_clicked = pyqtSignal(int)             # row of qubit-label column

    def __init__(self, parent=None):
        super().__init__(parent)
        # Parent populates after construction; defaults are safe placeholders.
        self.body_col_min: int = 1
        self.body_col_max: int = 1
        self.header_row: int = 0
        self._painter = DragPainter(
            target_at=self._body_cell_at,
            get_state=lambda rc: self._cell_state(*rc),
            set_state=lambda rc, on: self.body_toggled.emit(rc[0], rc[1], on),
            region=lambda s, c, _: self._rect_cells(s[0], s[1], c[0], c[1]),
        )

    def _is_body_cell(self, r: int, c: int) -> bool:
        return (r != self.header_row
                and self.body_col_min <= c <= self.body_col_max
                and r >= 0 and c >= 0)

    def _cell_state(self, r: int, c: int) -> bool:
        item = self.item(r, c)
        return bool(item.data(SELECTION_ROLE)) if item is not None else False

    def _body_cell_at(self, pos) -> Optional[tuple]:
        """Map mouse pos -> (r, c) clamped to the body region, or None."""
        idx = self.indexAt(pos)
        r, c = idx.row(), idx.column()
        if r < 0 or c < 0:
            return None
        # Clamp to body so the rectangle never escapes into headers.
        r = max(r, self.header_row + 1)
        c = min(max(c, self.body_col_min), self.body_col_max)
        return (r, c)

    def _rect_cells(self, r0: int, c0: int, r1: int, c1: int) -> set:
        r_lo, r_hi = sorted([r0, r1])
        c_lo, c_hi = sorted([c0, c1])
        return {(r, c)
                for r in range(r_lo, r_hi + 1)
                for c in range(c_lo, c_hi + 1)
                if self._is_body_cell(r, c)}

    def mousePressEvent(self, event):
        idx = self.indexAt(event.pos())
        r, c = idx.row(), idx.column()
        if r < 0 or c < 0:
            return
        if r == self.header_row and self.body_col_min <= c <= self.body_col_max:
            self.header_clicked.emit(c)
            event.accept()
            return
        if c == 0 and r != self.header_row:
            self.label_clicked.emit(r)
            event.accept()
            return
        if not self._is_body_cell(r, c):
            event.accept()
            return
        if self._painter.press(event.pos()):
            self.body_clicked.emit(r, c)
        event.accept()

    def mouseMoveEvent(self, event):
        self._painter.move(event.pos())

    def mouseReleaseEvent(self, event):
        self._painter.release()
        event.accept()


def _agent_set_combo(combo, val) -> bool:
    """Select a combo item by its data, then by str(data), then by text ('Q<val>'
    or '<val>'). Lets the Measurement Agent address controls by chip number even
    when the combo's data is a position. Returns True if a matching item was set."""
    i = combo.findData(val)
    if i < 0:
        i = combo.findData(str(val))
    if i < 0:
        for k in range(combo.count()):
            t = combo.itemText(k)
            if t == f"Q{val}" or t == str(val):
                i = k
                break
    if i >= 0:
        combo.setCurrentIndex(i)
    return i >= 0
