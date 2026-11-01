"""Data: the results of runs, plotted as they are measured.

One tab for every run. The bar at the top lists this session's runs, newest first; click
one to show it again. Every run is also on disk (runner/save.py), and "Open data…" plots
any saved run. What to draw comes from the sequence (runner/live_plot.plot_layout), the
same layout exported scripts draw with matplotlib:

    no sweep axes     one value per qubit
    1 axis            one line per qubit
    2 or more axes    one map per qubit (the two innermost axes, at the current outer point)
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QEvent, QRectF, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QSizePolicy, QStackedLayout, QVBoxLayout, QWidget)

from ...core.sequence import Sequence
from ...runner.live_plot import plot_layout, values
from .. import style
from ..widgets import ElidedLabel, InfoIcon

REDRAW_MS = 250
CONTROL_H = 28                                   # every button in the tab's header shares this height


class RunRecord:
    """One run in the history bar: its layout, the data so far, and where it is saved."""

    def __init__(self, seq: Sequence, status: str = "running", path: str = "", simulated: bool = False):
        self.seq = seq
        self.simulated = simulated
        self.note = ""                                   # e.g. the board config check
        self.layout = plot_layout(seq, simulated=simulated)
        self.started = datetime.datetime.now()
        self.status, self.path = status, path
        self.total = int(np.prod(self.layout.shape))
        self.done = 0
        self.data: dict = {}
        self.outer_idx = self.layout.outer_index(0)

    def add_point(self, k: int, point: dict) -> None:
        idx = np.unravel_index(int(k), self.layout.shape)
        for key, vals in point.items():
            vals = np.asarray(vals, float)
            if key not in self.data:
                self.data[key] = np.full((len(vals), *self.layout.shape), np.nan)
            self.data[key][(slice(None), *idx)] = vals
        self.done = max(self.done, int(k) + 1)
        self.outer_idx = self.layout.outer_index(k)

    @property
    def running(self) -> bool:
        return self.status == "running"

    def chip_text(self) -> str:
        when = self.started.strftime("%H:%M")
        state = ("running" if self.running else "saved" if self.status == "complete"
                 else "opened" if self.status == "opened" else self.status.split(":")[0].split(" after")[0])
        name = f"{self.seq.name} · simulated" if self.simulated else self.seq.name
        return f"{name}\n{when} · {self.done}/{self.total} · {state}"


class HistoryBar(QFrame):
    """This session's runs as chips in one rounded track, newest on the left; the shown run is
    highlighted. When the chips no longer fit, the track scrolls sideways (thin scroll bar,
    mouse wheel or trackpad) and keeps its size, so nothing below it moves."""
    chosen = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("run_track")
        self.setFixedHeight(54)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        self.area = QScrollArea()
        self.area.setObjectName("run_history")
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setWidgetResizable(True)
        self.area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.area.viewport().installEventFilter(self)
        body = QWidget()
        body.setObjectName("run_history_body")
        self.row = QHBoxLayout(body)
        self.row.setContentsMargins(5, 4, 5, 4)
        self.row.setSpacing(6)
        self.empty = QLabel("Runs appear here")
        self.empty.setObjectName("muted")
        self.row.addWidget(self.empty, 0, Qt.AlignVCenter)
        self.row.addStretch(1)
        self.area.setWidget(body)
        outer.addWidget(self.area)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.chips: list = []

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Wheel and obj is self.area.viewport():
            delta = e.angleDelta()
            step = delta.x() if abs(delta.x()) > abs(delta.y()) else delta.y()
            bar = self.area.horizontalScrollBar()
            bar.setValue(bar.value() - step)          # a plain wheel scrolls the row sideways
            return True
        return super().eventFilter(obj, e)

    def insert(self, text: str, tip: str) -> None:
        self.empty.hide()
        chip = QPushButton(text)
        chip.setObjectName("run_chip")
        chip.setCheckable(True)
        chip.setCursor(Qt.PointingHandCursor)
        chip.setFixedHeight(36)
        chip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        chip.setToolTip(tip)
        chip.clicked.connect(lambda _=False, c=chip: self.chosen.emit(self.chips.index(c)))
        self.group.addButton(chip)
        self.chips.insert(0, chip)
        self.row.insertWidget(0, chip, 0, Qt.AlignVCenter)
        chip.setChecked(True)
        self.area.horizontalScrollBar().setValue(0)   # the new run is on the left: show it

    def update_chip(self, i: int, text: str, tip: str) -> None:
        self.chips[i].setText(text)
        self.chips[i].setToolTip(tip)

    def select(self, i: int) -> None:
        self.chips[i].setChecked(True)
        self.area.ensureWidgetVisible(self.chips[i], 8, 0)

    def count(self) -> int:
        return len(self.chips)

    def chip(self, i: int) -> QPushButton:
        return self.chips[i]


class DataPanel(QWidget):
    stop_requested = pyqtSignal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self.records: list = []
        self.current: Optional[RunRecord] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 6)
        lay.setSpacing(6)

        # header: runs on the left, the actions for the shown run on the right, all on one centre line
        bar = QHBoxLayout()
        bar.setSpacing(8)
        lab = QLabel("Runs")
        lab.setObjectName("field_label")
        bar.addWidget(lab, 0, Qt.AlignVCenter)
        bar.addWidget(InfoIcon("This session's runs, newest first. Click one to show it. Every run is saved as it "
                               "is measured, so Open data… brings back any earlier run."), 0, Qt.AlignVCenter)
        self.history = HistoryBar()
        self.history.chosen.connect(self._row_chosen)
        bar.addWidget(self.history, 1, Qt.AlignVCenter)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stop_button")
        self.stop_btn.setToolTip("Finish the current point, save, and stop.")
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.folder_btn = QPushButton("Show folder")
        self.folder_btn.setToolTip("Open the folder the shown run is saved in")
        self.folder_btn.clicked.connect(self._show_folder)
        self.open_btn = QPushButton("Open data…")
        self.open_btn.setToolTip("Plot a saved run (its _data.h5 file)")
        self.open_btn.clicked.connect(self.open_dialog)
        for b in (self.stop_btn, self.folder_btn, self.open_btn):
            b.setFixedHeight(CONTROL_H)
            b.setCursor(Qt.PointingHandCursor)
            bar.addWidget(b, 0, Qt.AlignVCenter)
        lay.addLayout(bar)

        self.status = ElidedLabel()
        self.status.setObjectName("muted")
        lay.addWidget(self.status)

        self.stack = QStackedLayout()
        self.empty = QLabel("No runs yet. When a run starts its results are drawn here point by point.\n"
                            "Open data… plots a saved run.")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        pg.setConfigOptions(antialias=True)
        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setBackground(style.CANVAS["bg"])
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.glw)
        lay.addLayout(self.stack, 1)

        self._items: list = []                   # plot items for the shown record
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.redraw)
        self._update_controls()

    # ---------------------------------------------------------------- records
    def add_record(self, rec: RunRecord) -> RunRecord:
        self.records.insert(0, rec)
        self.history.insert(rec.chip_text(), rec.path or "not saved yet")
        self.show_record(rec)
        return rec

    def start_run(self, seq: Sequence, simulated: bool = False) -> RunRecord:
        return self.add_record(RunRecord(seq.clone(), "running", simulated=simulated))

    def set_note(self, rec: RunRecord, note: str) -> None:
        rec.note = note
        if rec is self.current:
            self._update_controls()

    def run_started(self, rec: RunRecord, path: str) -> None:
        rec.path = path
        self._refresh_chip(rec)

    def add_point(self, rec: RunRecord, k: int, point: dict) -> None:
        rec.add_point(k, point)
        self._refresh_chip(rec)
        if rec is self.current and not self._timer.isActive():
            self._timer.start(REDRAW_MS)

    def finish_run(self, rec: RunRecord, status: str, path: str) -> None:
        rec.status = status
        rec.path = path or rec.path
        self._refresh_chip(rec)
        if rec is self.current:
            self.redraw()
        self._update_controls()

    def open_path(self, path) -> RunRecord:
        from ...runner.save import load_run
        run = load_run(path)
        rec = RunRecord(Sequence.from_dict(run["sequence"]), "opened", str(path), simulated=run["simulated"])
        if run["board_config_check"].startswith("DIFFERS"):
            rec.note = "board config " + run["board_config_check"].split(" (")[0].lower()
        rec.started = datetime.datetime.fromtimestamp(Path(path).stat().st_mtime)
        rec.data = {k: np.asarray(v, float) for k, v in run["data"].items()
                    if isinstance(v, np.ndarray) and v.ndim >= 1 and v.shape[1:] == rec.layout.shape}
        rec.done = run["points_done"]
        rec.outer_idx = rec.layout.outer_index(max(0, rec.done - 1))
        if run["status"] != "complete":
            rec.status = run["status"]
        return self.add_record(rec)

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open a saved run", self._start_folder(),
                                              "Bob run data (*_data.h5);;HDF5 (*.h5)")
        if path:
            try:
                self.open_path(path)
            except Exception as exc:
                self.status.setText(f"Could not open {Path(path).name}: {exc}")

    def _start_folder(self) -> str:
        from ...runner.save import data_folder
        try:
            folder = data_folder(self.ctl.seq, self.ctl.station)
            return folder if Path(folder).exists() else ""
        except Exception:
            return ""

    def _row_chosen(self, row: int) -> None:
        if 0 <= row < len(self.records):
            self.show_record(self.records[row])

    def _refresh_chip(self, rec: RunRecord) -> None:
        if rec in self.records:
            self.history.update_chip(self.records.index(rec), rec.chip_text(), rec.path or "not saved yet")
        if rec is self.current:
            self._update_controls()

    def _show_folder(self) -> None:
        if self.current is not None and self.current.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.current.path).parent)))

    def _update_controls(self) -> None:
        rec = self.current
        running = rec is not None and rec.running
        self.stop_btn.setVisible(running)
        self.folder_btn.setEnabled(rec is not None and bool(rec.path))
        if rec is None:
            self.status.setText("")
            return
        outer = f"  ·  {rec.layout.outer_text(rec.outer_idx)}" if rec.layout.outer else ""
        where = f"  ·  {Path(rec.path).name}" if rec.path else ""
        state = "" if rec.status in ("running", "complete", "opened") else f"  ·  {rec.status}"
        sim = "Simulated data  ·  " if rec.simulated else ""
        note = f"  ·  {rec.note}" if rec.note else ""
        self.status.setText(f"{sim}{rec.done} of {rec.total} points{outer}{state}{note}{where}")
        self.status.setToolTip(rec.path or "")

    # ---------------------------------------------------------------- plot
    def show_record(self, rec: RunRecord) -> None:
        self.current = rec
        self.glw.clear()
        self._items = []
        L = rec.layout
        n = max(1, len(L.qubits))
        if L.kind == "maps":
            cols = min(n, 3)
            for r in range(n):
                p = self.glw.addPlot(row=r // cols, col=r % cols)
                p.setTitle(f"Q{L.qubits[r]}" if r < len(L.qubits) else str(r))
                p.setLabel("bottom", L.x.label)
                p.setLabel("left", L.y.label)
                for ax in ("bottom", "left"):
                    p.getAxis(ax).enableAutoSIPrefix(False)
                img = pg.ImageItem(axisOrder="row-major")
                p.addItem(img)
                bar = pg.ColorBarItem(values=(0, 1), colorMap="viridis", interactive=False, width=12)
                bar.setImageItem(img, insert_in=p)
                self._style_plot(p)
                self._items.append((img, bar))
        else:
            p = self.glw.addPlot(row=0, col=0)
            p.setLabel("left", L.ylabel)
            p.showGrid(x=True, y=True, alpha=0.15)
            p.getAxis("left").enableAutoSIPrefix(False)
            legend = p.addLegend(offset=(-10, 10))
            legend.setLabelTextColor(style.CANVAS["text"])
            self._style_plot(p)
            if L.kind == "lines":
                p.setLabel("bottom", L.x.label)
                p.getAxis("bottom").enableAutoSIPrefix(False)
                xv = np.asarray(L.x.values, float)
                if len(xv) > 1:                         # the whole sweep from the start; the line grows across it
                    p.setXRange(float(xv.min()), float(xv.max()), padding=0.02)
                    p.enableAutoRange(x=False)
            else:
                p.getAxis("bottom").setTicks([[(r, f"Q{q}") for r, q in enumerate(L.qubits)]])
            for r in range(n):
                q = L.qubits[r] if r < len(L.qubits) else r + 1
                color = style.qubit_color(q)
                item = p.plot([], [], pen=pg.mkPen(color, width=1.6), symbol="o", symbolSize=5,
                              symbolBrush=color, symbolPen=None, name=f"Read: Q{q}", connect="finite")
                self._items.append(item)
        self.stack.setCurrentWidget(self.glw)
        self.redraw()
        self._update_controls()

    @staticmethod
    def _style_plot(p):
        for ax in ("left", "bottom"):
            a = p.getAxis(ax)
            a.setPen(pg.mkPen(style.CANVAS["muted"]))
            a.setTextPen(pg.mkPen(style.CANVAS["text"]))
        p.titleLabel.setText(p.titleLabel.text, color=style.CANVAS["text"])

    @staticmethod
    def _edges(v):
        v = np.asarray(v, float)
        if len(v) < 2:
            return (v[0] - 0.5, v[0] + 0.5) if len(v) else (0.0, 1.0)
        step = (v[-1] - v[0]) / (len(v) - 1)
        return float(v[0] - step / 2), float(v[-1] + step / 2)

    def shown_values(self) -> np.ndarray:
        """What the plot shows now, one row per read-out qubit (for tests and export)."""
        rec = self.current
        return values(rec.layout, rec.data, rec.outer_idx) if rec else np.empty(0)

    def redraw(self) -> None:
        rec = self.current
        if rec is None:
            return
        L = rec.layout
        z = self.shown_values()
        for r, item in enumerate(self._items):
            if r >= len(z):
                break
            if L.kind == "lines":
                ok = np.isfinite(z[r])                  # unmeasured points are left out, not drawn as gaps
                item.setData(np.asarray(L.x.values)[ok], z[r][ok])
            elif L.kind == "points":
                v = z[r].ravel()[0]
                item.setData([r] if np.isfinite(v) else [], [v] if np.isfinite(v) else [])
            else:
                img, bar = item
                finite = z[r][np.isfinite(z[r])]
                lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
                hi = hi if hi > lo else lo + 1e-9
                x0, x1 = self._edges(L.x.values)
                y0, y1 = self._edges(L.y.values)
                img.setImage(z[r], autoLevels=False, levels=(lo, hi), rect=QRectF(x0, y0, x1 - x0, y1 - y0))
                bar.setLevels((lo, hi))
        self._update_controls()
