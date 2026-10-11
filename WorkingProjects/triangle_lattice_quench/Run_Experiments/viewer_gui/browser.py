"""The viewer's central widget: device + lattice + filters + file table + preview panes.

No qick, no soc/soccfg, no CalibState -- nothing here can reach the RFSoC. The only
code that touches the experiment classes lives in ``replot`` and is imported lazily.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PyQt5.QtCore import Qt, QDate, QEvent, QSettings, QThread, QTimer, pyqtSignal
import numpy as np
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemDelegate, QAbstractItemView, QApplication, QCheckBox, QComboBox, QCompleter, QDateEdit,
    QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import data_index as dx
from . import style as st
from .config_tree import describe, find_paths
from .lattice import LatticeSelector
from .widgets import MplCanvas, PixmapLabel, human_bytes

# Max rows shown in the table; the true match count is reported alongside it.
ROW_CAP = 500
# Clicking a dataset bigger than this asks first (shot-level runs hold 8x100,000).
CONFIRM_LOAD_BYTES = 5 * 1024 ** 2
# Data tab text: numpy summarises ('...') arrays with more values than this, unless
# "Show raw" is on.
DATA_TEXT_THRESHOLD = 2000

# QSettings slot for the last device that actually indexed (own keys: the viewer shares
# nothing with the calibration GUI).
SETTINGS_ORG, SETTINGS_APP = "HouckLab", "TriangleLatticeDataViewer"
SETTING_LAST_DEVICE = "last_device"

# "Add all to list" takes at most this many rows from the top of the filtered table.
ADD_ALL_MAX = 30
# Item role holding a row's ISO timestamp; Qt.UserRole holds its h5 path.
ISO_ROLE = Qt.UserRole + 1


def friendly_timestamp(iso: str) -> str:
    """'2026-10-01T14:10:00' -> '10/1/26 2:10pm'. Built by hand: Windows strftime has
    no %-m / %-d, and the 12-hour clock / lowercase am-pm need custom handling anyway."""
    import datetime
    try:
        t = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    hour = t.hour % 12 or 12
    return (f"{t.month}/{t.day}/{t.year % 100:02d} "
            f"{hour}:{t.minute:02d}{'am' if t.hour < 12 else 'pm'}")


def format_path_list(paths: list[str]) -> str:
    """Paths as a paste-ready Python list literal, one entry per line."""
    def literal(path: str) -> str:
        # A raw string reads naturally with Windows backslashes, but is only valid when
        # the path has no double quote and does not end in a backslash; else repr().
        ok = '"' not in path and not path.endswith("\\")
        return f'r"{path}"' if ok else repr(path)
    return "[\n" + "".join(f"    {literal(p)},\n" for p in paths) + "]"


# Reset-cache confirmation (title / text are user-specified).
RESET_TITLE = "Reset cache"
RESET_TEXT = ("Clearing the cache can be useful when files are reorganized on the disk. "
              "Are you sure you want to clear the cache?")
RESET_INFO = "The next scan takes a few seconds."
# Progressive table refreshes during a lazy qubit pass, at most this often (seconds).
LAZY_REFRESH_S = 1.0


# file-table column -> h5 attr / index column, for the two user-editable fields
EDITABLE_COLUMNS = {3: "group_name", 4: "name"}

class LazyQubitWorker(QThread):
    """Read qubit info for legacy files that would otherwise show, off the GUI thread
    (data_index.lazy_qubit_pass: budgeted, newest first, never under no qubit filter)."""

    kind = "lazy"
    progress = pyqtSignal(object)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, values: dict, device: str, db_path=None):
        super().__init__()
        self.values, self.device, self.db_path = values, device, db_path
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            conn = dx.connect(self.db_path)
            try:
                stats = dx.lazy_qubit_pass(self.values, self.device, conn,
                                           progress_cb=self.progress.emit,
                                           should_abort=lambda: self._stop)
            finally:
                conn.close()
            self.finished_ok.emit(stats)
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


class ValueView(QSplitter):
    """A LAZY Key | Value tree over any JSON-like / numpy value, with plot-on-select.

    Shared by the Config and Data tabs. Only top-level rows exist after set_value; a
    node's children are built when it is expanded (placeholder child, replaced), never
    more than MAX_CHILDREN under one node. Selecting a node with a plottable ``array``
    draws it (1-D line, 2-D up to MAX_PLOT_ROWS rows, decimated past MAX_PLOT_POINTS);
    anything else hides the plot.
    """

    MAX_PLOT_POINTS = 20000           # decimate beyond this before plotting
    MAX_PLOT_ROWS = 16                # rows overlaid for a 2-D array

    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.materialised = 0             # tree items created (tests + the real check)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Key", "Value"])
        self.tree.setUniformRowHeights(True)
        self.tree.itemExpanded.connect(self._expand)
        self.tree.currentItemChanged.connect(lambda cur, _prev: self._plot(cur))
        self.canvas = MplCanvas(self, height=2.2)
        self.canvas.setMinimumHeight(160)      # it starts hidden; never a 0-px sliver
        self.canvas.hide()
        self.addWidget(self.tree)
        self.addWidget(self.canvas)
        self.setStretchFactor(0, 3)
        self.setStretchFactor(1, 2)

    def set_value(self, value, label: Optional[str] = None) -> None:
        """Top-level rows: the value's own children, or -- with ``label`` -- the value
        itself as one row (selected, so an array plots straight away)."""
        self.clear()
        if label is not None:
            item = self._add(self.tree.invisibleRootItem(), label, value, (label,))
            self.tree.setCurrentItem(item)
        else:
            root = describe(value)
            pairs = root.children() if root.children else [("(value)", value)]
            for key, child in pairs:
                self._add(self.tree.invisibleRootItem(), key, child, (str(key),))
        self.tree.resizeColumnToContents(0)

    def clear(self) -> None:
        self.tree.clear()
        self.canvas.hide()
        self.materialised = 0

    def _add(self, parent, key, value, path: tuple) -> QTreeWidgetItem:
        node = describe(value)
        item = QTreeWidgetItem(parent, [str(key), node.summary])
        item.setData(0, Qt.UserRole, (path, value))
        item.setToolTip(1, node.tooltip or node.summary)   # columns elide when narrow
        if node.children is not None:
            QTreeWidgetItem(item, [""]).setData(0, Qt.UserRole, None)   # placeholder
        self.materialised += 1
        return item

    def _expand(self, item: QTreeWidgetItem) -> None:
        if item.childCount() != 1 or item.child(0).data(0, Qt.UserRole) is not None:
            return                                       # already built
        item.removeChild(item.child(0))
        path, value = item.data(0, Qt.UserRole)
        for key, child in describe(value).children():
            self._add(item, key, child, path + (str(key),))

    def expand_one_level(self) -> None:
        """Expand every visible collapsed node at the shallowest such depth."""
        layer, depth = [], None
        stack = [(self.tree.topLevelItem(i), 0) for i in range(self.tree.topLevelItemCount())]
        while stack:
            item, d = stack.pop()
            if item.isHidden() or item.childCount() == 0:
                continue
            if not item.isExpanded():
                if depth is None or d < depth:
                    layer, depth = [item], d
                elif d == depth:
                    layer.append(item)
            else:
                stack.extend((item.child(i), d + 1) for i in range(item.childCount()))
        for item in layer:
            item.setExpanded(True)

    def _plot(self, item) -> None:
        data = item.data(0, Qt.UserRole) if item is not None else None
        a = describe(data[1]).array if data else None
        if a is None:
            self.canvas.hide()
            return
        ax = self.canvas.ax
        ax.clear()
        rows = a[None, :] if a.ndim == 1 else a[:self.MAX_PLOT_ROWS]
        step = max(1, -(-rows.size // self.MAX_PLOT_POINTS))      # ceil division
        x = np.arange(rows.shape[1])[::step]
        for i, row in enumerate(rows):
            ax.plot(x, row[::step], lw=0.8, label=f"row {i}" if a.ndim == 2 else None)
        title = "/".join(data[0])
        if a.ndim == 2:
            title += f"  ({min(len(a), self.MAX_PLOT_ROWS)} of {len(a)} rows)"
            ax.legend(fontsize="small", ncol=4)
        if step > 1:
            title += f"  [decimated 1:{step}]"
        ax.set_title(title, fontsize="small")
        ax.set_xlabel("index")
        if self.canvas.isHidden() or self.canvas.height() < self.canvas.minimumHeight():
            total = max(sum(self.sizes()), 1)
            self.setSizes([int(total * 0.55), total - int(total * 0.55)])
        self.canvas.show()
        self.canvas.draw_idle()


class ConfigPane(QWidget):
    """The Config tab: a ValueView over the run's config, a filter, and the raw JSON
    one checkbox away. Scalars and short lists read inline with no expansion at all."""

    MAX_EXPANDED = 50                 # filter: at most this many matching paths opened
    MAX_PLOT_POINTS = ValueView.MAX_PLOT_POINTS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = None
        self.view = ValueView(self)
        self.tree, self.canvas = self.view.tree, self.view.canvas
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("filter keys / values")
        self.filter_edit.textChanged.connect(lambda _t: self._filter_timer.start())
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self.apply_filter)
        buttons = []
        for label, slot in (("Expand one level", self.expand_one_level),
                            ("Collapse", lambda: self.tree.collapseAll()),
                            ("Copy JSON", self.copy_json)):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            buttons.append(btn)
        self.raw_box = QCheckBox("Raw JSON")
        self.raw_box.toggled.connect(self._show_page)
        self.raw = st.make_mono(QPlainTextEdit())
        self.raw.setReadOnly(True)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.raw)

        bar = QHBoxLayout()                    # filter gets its own row: the right
        for w in (*buttons, self.raw_box):     # column is narrow in the default window
            bar.addWidget(w)
        bar.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.filter_edit)
        layout.addLayout(bar)
        layout.addWidget(self.stack, 1)

    @property
    def materialised(self) -> int:
        return self.view.materialised

    # ---- loading ----

    def set_config(self, cfg) -> None:
        self.cfg = cfg
        self.raw.setPlainText(json.dumps(cfg, indent=2))
        self.view.set_value(cfg)
        self._show_page(self.raw_box.isChecked())

    def show_message(self, text: str) -> None:
        """Busy / unreadable / missing: plain text in the raw view, switched to."""
        self.cfg = None
        self.view.clear()
        self.raw.setPlainText(text)
        self.stack.setCurrentWidget(self.raw)

    def _show_page(self, raw: bool) -> None:
        if self.cfg is not None:
            self.stack.setCurrentIndex(1 if raw else 0)

    def expand_one_level(self) -> None:
        self.view.expand_one_level()

    def copy_json(self) -> None:
        if self.cfg is not None:
            QApplication.clipboard().setText(json.dumps(self.cfg, indent=2))

    # ---- filter ----

    def apply_filter(self) -> None:
        if self.cfg is None:
            return
        text = self.filter_edit.text().strip()
        self.view.set_value(self.cfg)
        if not text:
            return                                       # everything restored
        paths = find_paths(self.cfg, text)
        if not paths:
            self.tree.clear()
            QTreeWidgetItem(self.tree, ["(no match)", ""])
            return
        tops = {p[0] for p in paths}
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setHidden(item.text(0) not in tops)
        for path in paths[:self.MAX_EXPANDED]:
            item = next((self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())
                         if self.tree.topLevelItem(i).text(0) == path[0]), None)
            for key in path[1:]:                          # open the ancestors only
                if item is None:
                    break
                item.setExpanded(True)
                item = next((item.child(i) for i in range(item.childCount())
                             if item.child(i).text(0) == key), None)


class IndexWorker(QThread):
    """Run one indexing request off the GUI thread.

    ``mode`` is 'open' (tier 0 + tier 1, or a warm refresh) or 'all' (tier 2, optionally
    scoped to one experiment / date range by ``scope``).
    """

    kind = "index"
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(object)
    unavailable = pyqtSignal(str)             # expected condition (root not mounted)
    failed = pyqtSignal(str)                  # unexpected: a real traceback

    def __init__(self, root: str, device: str, mode: str = "open",
                 scope: dict | None = None, db_path=None):
        super().__init__()
        self.root, self.device, self.mode, self.scope = root, device, mode, scope or {}
        self.db_path = db_path
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            if not os.path.isdir(self.root):
                # Checked here, not on the GUI thread: a hung mapped drive would
                # otherwise block window construction. Not an error: several device
                # jsons have no folder on the share, and the viewer still works against
                # whatever is cached -- so this reports into the status line, never a
                # modal dialog (which would also be a hard crash under -platform
                # offscreen in headless checks).
                self.unavailable.emit(
                    f"{dx.UNREACHABLE_MESSAGE} ({self.root} not reachable - check the Z: "
                    f"mapping, or pick another device)")
                return
            conn = dx.connect(self.db_path)       # sqlite3 connections are thread-bound
            try:
                emit = lambda d, t, m: self.progress.emit(d, t, m)
                abort = lambda: self._stop
                if self.mode == "all":
                    stats = dx.index_all(self.root, self.device, conn, self.scope,
                                         progress_cb=emit, should_abort=abort)
                else:
                    stats = dx.open_device(self.root, self.device, conn,
                                           progress_cb=emit, should_abort=abort)
            finally:
                conn.close()
            self.finished_ok.emit(stats)
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


class BrowserWidget(QWidget):
    """Browse saved runs: device -> lattice/filters -> file table -> png/replot/data/config.

    ``auto_index=False`` suppresses the background tier-0/tier-1 pass, so tests and
    headless checks never touch the network or leave a QThread running.
    """

    status_message = pyqtSignal(str)

    def __init__(self, parent=None, db_path=None, auto_index: bool = True):
        super().__init__(parent)
        self.db_path = db_path
        self.conn = dx.connect(db_path)           # GUI-thread connection (WAL)
        self.worker: Optional[QThread] = None     # IndexWorker or LazyQubitWorker
        self._queued: Optional[str] = None        # one worker at a time; next request
        self._lazy_key: Optional[str] = None      # filter state the last lazy pass served
        self._last_lazy_refresh = 0.0
        # Injectable so tests never open a real modal (it hard-crashes offscreen).
        self.confirm_reset: Callable[[], bool] = self._ask_reset
        self._path: Optional[str] = None
        self._datasets: dict[str, dict] = {}

        # --- (a) device ---
        # Listed from the local device jsons (no network on construction). Several of
        # them have no folder on the share, so the last working choice is remembered
        # rather than defaulting to whichever sorts first.
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.device_combo = QComboBox()
        self.device_combo.addItems(dx.available_devices())
        last = self.settings.value(SETTING_LAST_DEVICE, "", type=str)
        if last and self.device_combo.findText(last) >= 0:
            self.device_combo.setCurrentText(last)
        self.device_combo.currentTextChanged.connect(self._on_device_changed)

        # --- (b) lattice + presets ---
        self.lattice = LatticeSelector(self)
        self.lattice.selection_changed.connect(self._on_lattice_changed)
        presets = QHBoxLayout()
        for label, count in (("All", None), ("Left 4", 4), ("Left 6", 6), ("Unselect", 0)):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, c=count: self.lattice.preset(c))
            presets.addWidget(btn)

        # --- (c) filters (one widget per FilterSpec) + index controls ---
        self.filter_values: dict[str, Callable[[], Any]] = {}
        self.filter_widgets: dict[str, QWidget] = {}
        form = QFormLayout()
        for spec in dx.FILTERS:
            widget, value_fn = self._build_filter_widget(spec)
            self.filter_values[spec.key] = value_fn
            if widget is not None:
                self.filter_widgets[spec.key] = widget
                form.addRow(spec.label, widget)
        filter_box = QGroupBox("Filters")
        filter_box.setLayout(form)

        self.refresh_btn = QPushButton("Check for new")
        self.refresh_btn.setToolTip(
            "Re-list experiment folders and the last "
            f"{dx.RECENCY_DAYS} days of day-folders (~0.1 s). Does not walk history.")
        self.refresh_btn.clicked.connect(lambda: self._request("open"))
        self.index_all_btn = QPushButton("Index all history")
        self.index_all_btn.clicked.connect(lambda: self._request("all"))
        # "Stop" while any worker runs, "Reset cache" when idle; _set_busy owns the label.
        self.stop_btn = QPushButton("Reset cache")
        self.stop_btn.clicked.connect(self.on_stop_or_reset)
        self.status_label = QLabel("(cache only)")
        self.status_label.setWordWrap(True)

        # --- (d) file table ---
        self.count_label = QLabel("")
        self.count_label.setWordWrap(True)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["timestamp", "experiment", "qubits", "group_name", "name"])
        self.table.horizontalHeaderItem(1).setToolTip(
            "the archive FOLDER name (ExperimentClass.path, e.g. 'T2R') - present for "
            "every file, and what the Experiment filter matches")
        self.table.horizontalHeaderItem(2).setToolTip(
            "'*' = recovered from a Qubit_Readout_List dataset rather than a metadata "
            "attr; hover a cell for the exact source")
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        st.style_table(self.table)                # (sets full-row single selection ...)
        # Only group_name / name cells carry ItemIsEditable. Cells select individually (drag to
        # pick several in one column); the current ROW still decides which file the panes show.
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.AnyKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self._in_selection_fix = False
        self.table.selectionModel().selectionChanged.connect(self._keep_selection_in_column)
        self.table.itemDelegate().commitData.connect(self._on_editor_committed)   # not itemChanged: restyling fires that
        self._busy = False                    # a pane showed BUSY_MESSAGE for this row
        self.table.cellClicked.connect(self._on_cell_clicked)
        self._friendly_ts = True          # natural form by default; header toggles
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._set_timestamp_tooltip()
        # Right-click on a row adds it to the file list directly (no menu); left
        # clicks are untouched and still select + load the row.
        self.table.viewport().installEventFilter(self)

        # --- (e) right pane ---
        self.right = QTabWidget()
        self.png_label = PixmapLabel()
        png_scroll = QScrollArea()
        png_scroll.setWidgetResizable(True)
        png_scroll.setWidget(self.png_label)
        self.right.addTab(self._build_plot_pane(png_scroll), "Plot")
        self.right.addTab(self._build_data_pane(), "Data")
        self.config_pane = ConfigPane(self)
        self.config_text = self.config_pane.raw          # the raw-JSON view (name kept)
        self.right.addTab(self.config_pane, "Config")

        # Lower right: a small, resizable tab widget. One (label, builder) entry per tab,
        # so adding e.g. a "Terminal" later is one line here.
        self.file_list: list[str] = []
        self.lower = QTabWidget()
        for label, build in (("File list", self._build_file_list_pane),):
            self.lower.addTab(build(), label)
        right_col = QSplitter(Qt.Vertical)
        right_col.addWidget(self.right)
        right_col.addWidget(self.lower)
        right_col.setStretchFactor(0, 4)
        right_col.setStretchFactor(1, 1)
        right_col.setSizes([620, 200])

        # --- assemble ---
        left = QVBoxLayout()
        left.addWidget(QLabel("Device:"))
        left.addWidget(self.device_combo)
        left.addWidget(self.lattice)
        left.addLayout(presets)
        left.addWidget(filter_box)
        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_btn)
        buttons.addWidget(self.index_all_btn)
        buttons.addWidget(self.stop_btn)
        left.addLayout(buttons)
        left.addWidget(self.status_label)
        left.addStretch(1)
        left_box = QWidget()
        left_box.setLayout(left)
        # No maximum: the lattice is width-limited (~3:1), so width is what makes it
        # big enough to click. The left column gets the largest stretch.
        left_box.setMinimumWidth(440)

        self.read_more_btn = QPushButton("Read more old runs")
        self.read_more_btn.setToolTip(
            f"Check the next {dx.PASS_BUDGET} older runs (newest first) for qubit info")
        self.read_more_btn.clicked.connect(lambda: self._request("lazy"))
        self.read_more_btn.hide()
        count_row = QHBoxLayout()
        count_row.addWidget(self.count_label, 1)
        count_row.addWidget(self.read_more_btn)
        middle = QVBoxLayout()
        middle.addLayout(count_row)
        middle.addWidget(self.table, 1)
        middle_box = QWidget()
        middle_box.setLayout(middle)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_box)
        splitter.addWidget(middle_box)
        splitter.addWidget(right_col)
        splitter.setSizes([560, 440, 520])
        for i, stretch in enumerate((3, 2, 2)):
            splitter.setStretchFactor(i, stretch)
        layout = QHBoxLayout(self)
        layout.addWidget(splitter)

        # Text filters fire per keystroke; coalesce into one query.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self.refresh_table)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_worker)

        if self.device_combo.count():
            self._on_device_changed(self.device_combo.currentText(), index=False)
        # Populate from the cache first; only then reach for the network, and only
        # after the event loop is running so construction itself never blocks.
        if auto_index:
            QTimer.singleShot(0, self._request_open)          # bound: dropped if deleted

    # ---- filters ----

    def _build_filter_widget(self, spec: dx.FilterSpec) -> tuple[Optional[QWidget], Callable]:
        """One FilterSpec -> (widget or None, value getter). The kind->widget mapping
        lives only here, so adding a filter of an existing kind touches no GUI code."""
        if spec.kind == "lattice":
            # Reads as a sentence: "[Q3, Q5]  =  qubits". The box mirrors the lattice
            # selection; the dropdown carries the match mode (default exact).
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            self.qubit_edit = QLineEdit()
            self.qubit_edit.setReadOnly(True)
            self.qubit_edit.setPlaceholderText("(click the lattice above)")
            self.qubit_mode = QComboBox()
            for i, (symbol, (name, tip, _)) in enumerate(dx.QUBIT_MODES.items()):
                self.qubit_mode.addItem(symbol)
                self.qubit_mode.setItemData(i, f"{name}: {tip}", Qt.ToolTipRole)
            self.qubit_mode.setCurrentText(dx.DEFAULT_QUBIT_MODE)
            self.qubit_mode.setToolTip("\n".join(
                f"{s}  {name}: {tip}" for s, (name, tip, _) in dx.QUBIT_MODES.items()))
            self.qubit_mode.currentTextChanged.connect(self._schedule_refresh)
            row.addWidget(self.qubit_edit, 1)
            row.addWidget(self.qubit_mode)
            row.addWidget(QLabel("qubits"))
            return box, lambda: {"mode": self.qubit_mode.currentText(),
                                 "qubits": self.lattice.selected()}
        if spec.kind == "combo":
            combo = QComboBox()
            combo.addItem(dx.ANY)
            combo.addItems(list(spec.choices))
            combo.currentTextChanged.connect(self._schedule_refresh)   # debounced
            if not spec.editable:
                return combo, combo.currentText
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.NoInsert)    # typing never adds entries
            completer = QCompleter(combo.model(), combo) # follows repopulated items
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            completer.setCompletionMode(QCompleter.PopupCompletion)
            combo.setCompleter(completer)
            combo.lineEdit().returnPressed.connect(lambda: self._accept_completion(combo))
            return combo, lambda: self._resolve_combo(combo)
        if spec.kind == "text":
            edit = QLineEdit()
            edit.setPlaceholderText("(any)")
            edit.textChanged.connect(self._schedule_refresh)
            return edit, edit.text
        if spec.kind == "daterange":
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            enable = QCheckBox()                          # unset by default: a QDateEdit
            lo = QDateEdit(QDate.currentDate().addMonths(-1))  # always holds a value, so
            hi = QDateEdit(QDate.currentDate())           # the checkbox is what makes
            for w in (lo, hi):                            # "no date filter" expressible
                w.setCalendarPopup(True)
                w.setDisplayFormat("yyyy-MM-dd")
                w.dateChanged.connect(self._schedule_refresh)
            enable.toggled.connect(self._schedule_refresh)
            row.addWidget(enable)
            row.addWidget(lo)
            row.addWidget(hi)
            return box, lambda: ((lo.date().toString("yyyy-MM-dd"),
                                  hi.date().toString("yyyy-MM-dd"))
                                 if enable.isChecked() else (None, None))
        raise ValueError(f"unknown filter kind: {spec.kind}")

    def _on_lattice_changed(self, selected: list) -> None:
        edit = getattr(self, "qubit_edit", None)
        if edit is not None:
            edit.setText(", ".join(f"Q{q}" for q in selected))
        self._schedule_refresh()

    @staticmethod
    def _resolve_combo(combo: QComboBox) -> str:
        """Typed text -> the item it names exactly (case-insensitive), else ANY. A partial
        word therefore filters nothing; the completer popup is the feedback."""
        text = combo.currentText().strip().lower()
        for i in range(combo.count()):
            if combo.itemText(i).lower() == text:
                return combo.itemText(i)
        return dx.ANY

    def _accept_completion(self, combo: QComboBox) -> None:
        """Enter on a partial: take the first suggestion, if there is one."""
        if self._resolve_combo(combo) == dx.ANY and combo.currentText().strip():
            completer = combo.completer()
            completer.setCompletionPrefix(combo.currentText())
            if completer.completionCount():
                combo.setCurrentText(completer.currentCompletion())
        self.refresh_table()

    def _schedule_refresh(self, *_args) -> None:
        self._debounce.start()

    def current_filters(self) -> dict:
        return {key: fn() for key, fn in self.filter_values.items()}

    def _repopulate_combos(self) -> None:
        """Refill index-backed combos, keeping the current choice if still present."""
        device = self.device_combo.currentText()
        for spec in dx.FILTERS:
            if spec.choices_column is None or spec.key not in self.filter_widgets:
                continue
            combo = self.filter_widgets[spec.key]
            keep = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(dx.ANY)
            # Experiment names come from day_folders: tier 0 knows all of them long
            # before their files are indexed.
            combo.addItems(dx.distinct(spec.choices_column, device,
                                       table="day_folders", conn=self.conn))
            idx = combo.findText(keep)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    # ---- device / indexing ----

    def _on_device_changed(self, device: str, index: bool = True) -> None:
        self.lattice.set_device(device)               # also emits -> schedule refresh
        self._repopulate_combos()
        self.refresh_table()
        if index:
            self._request("open")

    def _running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def _request(self, mode: str) -> None:
        """Queue a request ('open' | 'all' | 'lazy'); one worker runs at a time.

        A lazy request waits for a running INDEX pass (never cuts it short) but replaces
        a running lazy pass, whose filter is stale. An index request stops whatever runs.
        The next request starts from the finished handler -- never wait() on the GUI
        thread, since a scandir hung on SMB would not see the stop flag.
        """
        device = self.device_combo.currentText()
        if not device:
            return
        if self._running():
            if not (mode == "lazy" and self.worker.kind == "index"):
                self.worker.stop()
            self._queued = mode
            return
        self._queued = None
        if mode == "lazy":
            worker = LazyQubitWorker(self.current_filters(), device, db_path=self.db_path)
            worker.progress.connect(self._on_lazy_progress)
            worker.finished_ok.connect(self._on_lazy_done)
            worker.failed.connect(self._on_index_failed)
        else:
            scope = dx.day_scope(self.current_filters()) if mode == "all" else {}
            worker = IndexWorker(str(dx.DATA_ROOT / device), device, mode, scope,
                                 db_path=self.db_path)
            worker.progress.connect(lambda d, t, m: self._set_status(m))
            worker.finished_ok.connect(self._on_index_done)
            worker.unavailable.connect(self._on_index_unavailable)
            worker.failed.connect(self._on_index_failed)
        # QThread's own finished signal: the button state can never outlive the thread.
        worker.finished.connect(self._on_thread_finished)
        self.worker = worker
        self._set_busy(True)
        self._start_worker(worker)

    def _start_worker(self, worker: QThread) -> None:
        """Hook: tests replace it to run a worker synchronously."""
        worker.start()

    def _on_thread_finished(self) -> None:
        if not self._running():
            self._set_busy(False)

    def _run_queued(self) -> None:
        if self._queued is not None:
            self._pending, self._queued = self._queued, None
            QTimer.singleShot(0, self._start_pending)

    # Timer targets are BOUND methods, never lambdas: Qt drops a bound method's call if
    # the widget has been deleted, whereas a lambda would run against a dead object.
    def _request_open(self) -> None:
        self._request("open")

    def _request_lazy(self) -> None:
        self._request("lazy")

    def _start_pending(self) -> None:
        mode, self._pending = getattr(self, "_pending", None), None
        if mode:
            self._request(mode)

    def on_stop_or_reset(self) -> None:
        """Stop while a worker runs; Reset cache when idle. Decided at click time from
        the thread itself, so Reset can never fire during a run."""
        if self._running():
            self._queued = None
            self.worker.stop()
            self._set_status("stopping...")
        else:
            self.reset_cache()

    def _reset_box(self) -> QMessageBox:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(RESET_TITLE)
        box.setText(RESET_TEXT)
        box.setInformativeText(RESET_INFO)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        return box

    def _ask_reset(self) -> bool:
        return self._reset_box().exec_() == QMessageBox.Yes

    def reset_cache(self) -> bool:
        """Confirm, then forget the index (all devices) and rebuild the current device.
        qubit_memo and QSettings (device, zoom) are kept. Returns True when cleared."""
        if self._running() or not self.confirm_reset():
            return False
        dx.reset_cache(self.conn)
        self._lazy_key = None
        self._set_status("cache cleared - rebuilding...")
        self._repopulate_combos()
        self.refresh_table()
        self._request("open")
        return True

    def _set_busy(self, running: bool) -> None:
        """Single owner of the button state, so a failure can never leave the controls
        disabled forever. The Stop/Reset button is always enabled; only its label (and
        what on_stop_or_reset does) changes."""
        self.refresh_btn.setEnabled(not running)
        self.index_all_btn.setEnabled(not running)
        self.stop_btn.setText("Stop" if running else "Reset cache")
        self.stop_btn.setEnabled(True)
        if running and self.worker is not None and self.worker.kind == "lazy":
            self.read_more_btn.hide()

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_message.emit(message)

    def _on_index_done(self, stats: dict) -> None:
        self._set_busy(False)
        if stats.get("unreachable"):
            self._set_status(dx.UNREACHABLE_MESSAGE)
            self.refresh_table()
            return
        self.settings.setValue(SETTING_LAST_DEVICE, self.device_combo.currentText())
        self._set_status(
            f"indexed {stats['indexed']:,} files in {stats['days_indexed']:,} day-folders "
            f"({stats['skipped']:,} unchanged, {stats['opened']:,} opened"
            + (f", {stats['failed']:,} unreadable" if stats["failed"] else "")
            + (f", {stats['busy']:,} busy, will retry" if stats.get("busy") else "")
            + (f", {stats['relist_failed']:,} folders unreadable, kept cached"
               if stats.get("relist_failed") else "")
            + (", STOPPED" if stats["aborted"] else "") + ")")
        self._repopulate_combos()
        self.refresh_table()
        self._run_queued()

    def _on_index_unavailable(self, message: str) -> None:
        self._set_busy(False)
        self._set_status(message)
        self._queued = None        # a queued lazy pass would only fail on a missing share

    # ---- lazy qubit lookup ----

    def _on_lazy_progress(self, stats: dict) -> None:
        self._set_status(f"checking older runs for qubit info... {stats['opened']:,} read "
                         f"({stats['matched']:,} match)")
        now = time.monotonic()
        if now - self._last_lazy_refresh >= LAZY_REFRESH_S:   # matches appear as found
            self._last_lazy_refresh = now
            self.refresh_table()

    def _on_lazy_done(self, stats: dict) -> None:
        self._set_busy(False)
        if stats.get("active"):
            tail = ("share not reachable - stopped" if stats.get("unreachable") else
                    "complete for this filter" if stats["complete"] else
                    "table is full" if stats["table_full"] else
                    f"{stats['remaining']:,} more candidates unread")
            self._set_status(f"read {stats['opened']:,} older runs "
                             f"({stats['matched']:,} match); {tail}"
                             + (f"; {stats['busy']} busy, will retry" if stats["busy"] else ""))
        self.refresh_table()
        self._run_queued()

    def _on_index_failed(self, message: str) -> None:
        self._set_busy(False)
        self._set_status("indexing failed - see the dialog")
        QMessageBox.critical(self, "Indexing failed", message)

    def _stop_worker(self) -> None:
        """Never let Qt destroy a running QThread."""
        self._queued = None
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)

    def closeEvent(self, event):
        self._stop_worker()
        super().closeEvent(event)

    # ---- table ----

    def refresh_table(self) -> None:
        self._debounce.stop()                 # fold any pending debounced refresh in
        values = self.current_filters()
        device = self.device_combo.currentText()
        rows, total = dx.query(values, device, conn=self.conn, limit=ROW_CAP)
        self.count_label.setText(self._coverage_text(len(rows), total, values, device)
                                 + self._qubit_note(values, device))
        self.index_all_btn.setText(
            f"Index all {values['experiment']}" if dx.is_set(values.get("experiment"))
            else "Index all history")
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            qubits = row.get("qubits") or row.get("qubit_readout") or ""
            source = row.get("qubit_source")
            # '*' marks a list recovered from a dataset rather than a metadata attr,
            # so a real match is distinguishable from a fallback guess at a glance.
            mark = "" if source in (None, "qubits", "Qubit_Readout") else " *"
            cells = [row.get("timestamp") or "", row.get("experiment") or "",
                     (str(json.loads(qubits)) + mark) if qubits else "",
                     row.get("group_name") or "", row.get("name") or ""]
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if c == 0:
                    item.setData(Qt.UserRole, row["path"])
                    item.setData(ISO_ROLE, value)        # the ISO string stays the data;
                    if self._friendly_ts:                # only the display text changes
                        item.setText(friendly_timestamp(value))
                if c == 0:
                    item.setToolTip(value)                # ISO, whichever form is shown
                elif c == 2:
                    item.setToolTip(f"qubits from {dx.QUBIT_SOURCES.get(source, 'nothing')}")
                elif value:
                    item.setToolTip(value)                # full text when elided
                if c == 2:                                # qubits: centred, apart from the experiment name
                    item.setTextAlignment(Qt.AlignCenter)
                if c not in EDITABLE_COLUMNS:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        self._refresh_row_marks()

    def _on_header_clicked(self, section: int) -> None:
        if section != 0:
            return
        self._friendly_ts = not self._friendly_ts
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            iso = item.data(ISO_ROLE) if item else None
            if iso:
                item.setText(friendly_timestamp(iso) if self._friendly_ts else iso)
        self._set_timestamp_tooltip()
        self.table.resizeColumnToContents(0)
        self._refresh_row_marks()

    def _set_timestamp_tooltip(self) -> None:
        shown = ("friendly (10/1/26 2:10pm)" if self._friendly_ts
                 else "ISO (2026-10-01T14:10:00)")
        self.table.horizontalHeaderItem(0).setToolTip(
            f"showing {shown} - click to toggle; selection and lookup always use ISO")

    def eventFilter(self, obj, event):
        if (obj is self.table.viewport() and event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.RightButton):
            item = self.table.itemAt(event.pos())
            if item is not None:
                self.toggle_in_list(self.table.item(item.row(), 0).data(Qt.UserRole))
            return True                          # consume: no selection change
        return super().eventFilter(obj, event)

    # ---- lower right: file list ----

    def _build_file_list_pane(self) -> QWidget:
        self.list_text = st.make_mono(QPlainTextEdit())
        self.list_text.setReadOnly(True)
        self.list_count = QLabel()
        add_all = QPushButton(f"Add all to list (max {ADD_ALL_MAX})")
        add_all.clicked.connect(self.add_all_to_list)
        copy = QPushButton("Copy")
        copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self.list_text.toPlainText()))
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_list)
        buttons = QHBoxLayout()
        for w in (self.list_count, add_all, copy, clear):
            buttons.addWidget(w)
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(buttons)
        layout.addWidget(self.list_text, 1)
        self._render_list()
        return box

    def add_to_list(self, paths) -> int:
        """Append in order, skipping paths already listed. Returns how many were added.

        Entries are FULL absolute h5 paths, not bare filenames: the list is pasted into
        the user's own code, and ExperimentClass.load_data needs a path."""
        added = 0
        for path in paths:
            if path and path not in self.file_list:
                self.file_list.append(path)
                added += 1
        self._render_list()
        self.status_message.emit(f"added {added} - {len(self.file_list)} in list")
        return added

    def toggle_in_list(self, path: str) -> bool:
        """Right-click: add if absent, remove if present (others keep their order; a
        re-add appends at the end). Returns True when the path is now in the list."""
        if path in self.file_list:
            self.file_list.remove(path)
            self._render_list()
            self.status_message.emit(f"removed 1 - {len(self.file_list)} in list")
            return False
        self.add_to_list([path])
        return True

    def add_all_to_list(self) -> int:
        """The first ADD_ALL_MAX rows of the filtered table, as displayed (newest first)."""
        rows = range(min(ADD_ALL_MAX, self.table.rowCount()))
        return self.add_to_list([self.table.item(r, 0).data(Qt.UserRole) for r in rows])

    def clear_list(self) -> None:
        self.file_list.clear()
        self._render_list()

    def _render_list(self) -> None:
        """The text view is read-only and always regenerated from self.file_list."""
        self.list_text.setPlainText(format_path_list(self.file_list))
        self.list_count.setText(f"{len(self.file_list)} in list")
        self._refresh_row_marks()

    def _refresh_row_marks(self) -> None:
        """Bold every cell of rows whose file is in the list. The ONE place bolding is
        decided; keyed on the path, so it survives re-filtering and reformatting."""
        if not hasattr(self, "table"):
            return
        listed = set(self.file_list)
        bold = QFont(self.table.font())         # the table's current (zoomed) font
        bold.setBold(True)
        for r in range(self.table.rowCount()):
            head = self.table.item(r, 0)
            on = head is not None and head.data(Qt.UserRole) in listed
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item is None:
                    continue
                if on:
                    item.setFont(bold)
                else:
                    item.setData(Qt.FontRole, None)   # inherit the table font again

    def restyle(self) -> None:
        """After a zoom: re-derive bold fonts and re-fit the lattice to its new size."""
        self._refresh_row_marks()
        self.table.resizeColumnToContents(0)
        self.lattice.sync_height()
        self.lattice.redraw()

    def _qubit_note(self, values: dict, device: str) -> str:
        """Under a qubit-based filter: say how many runs the filter cannot judge yet, and
        start (once per filter state) a budgeted lazy pass over them. Nothing at all is
        read or counted without a qubit-based filter."""
        if not device or not dx.qubit_filter_active(values):
            self.read_more_btn.hide()
            return ""
        counts = dx.qubit_unknown_counts(values, device, self.conn)
        lazy_running = self._running() and self.worker.kind == "lazy"
        self.read_more_btn.setVisible(bool(counts["unchecked"]) and not lazy_running)
        key = json.dumps([device, values], sort_keys=True, default=str)
        if counts["unchecked"] and key != self._lazy_key:
            self._lazy_key = key
            QTimer.singleShot(0, self._request_lazy)
        parts = []
        if counts["unchecked"]:
            parts.append(f"{counts['unchecked']:,} older runs not yet checked for qubit info")
        if counts["unavailable"]:
            parts.append(f"{counts['unavailable']:,} have no qubit info")
        return ("  -  " + "; ".join(parts) + ".") if parts else ""

    def _coverage_text(self, shown: int, total: int, values: dict, device: str) -> str:
        """Never let a partial index look exhaustive."""
        head = f"showing {shown:,} of {total:,} indexed" + (
            f" (capped at {ROW_CAP})" if total > shown else "")
        hz = dx.horizon(device, values, conn=self.conn)
        if hz["total_days"] == 0:
            return head + "  -  nothing indexed yet for this device"
        if hz["complete"]:
            return head + f"  -  complete for this filter ({hz['total_days']:,} day-folders)"
        scope = ("this experiment" if hz["scope"].get("experiment") else "history")
        undated = hz["undated_unindexed"]
        dated = hz["unindexed_days"] - undated      # unindexed_days already includes undated
        parts = []
        if dated:
            parts.append(f"{dated:,} day-folders back to {hz['newest_unindexed']}")
        if undated:
            parts.append(f"{undated:,} undated")
        return (head + f"  -  NOT complete: {', '.join(parts)} not indexed. "
                f"Press 'Index all' for the rest of {scope}.")

    def _on_cell_clicked(self, row: int, _col: int) -> None:
        """Clicking the already-selected row again retries panes that found it busy
        (a click on a NEW row is handled by the selection change instead)."""
        item = self.table.item(row, 0)
        if self._busy and item is not None and item.data(Qt.UserRole) == self._path:
            self._load_panes(self._path)

    def _keep_selection_in_column(self, *_) -> None:
        """Drag-select stays within the current cell's column."""
        if self._in_selection_fix:
            return
        sm = self.table.selectionModel()
        col = self.table.currentColumn()
        stray = [i for i in sm.selectedIndexes() if i.column() != col]
        if not stray:
            return
        self._in_selection_fix = True
        try:
            for i in stray:
                sm.select(i, sm.Deselect)
        finally:
            self._in_selection_fix = False

    def _on_editor_committed(self, _editor) -> None:
        """Runs right after the view stored the edit, before Enter moves the cursor and collapses
        the selection (closeEditor is too late for that)."""
        if self.table.currentItem() is not None:
            self._on_item_edited(self.table.currentItem())

    def _on_item_edited(self, item) -> None:
        """Write an edited group_name/name to the h5 attrs and the index, for every selected
        cell in that column when the edited cell is one of several selected."""
        col = item.column()
        if col not in EDITABLE_COLUMNS:
            return
        text = item.text()
        selected = self.table.selectedItems()
        targets = [it for it in selected if it.column() == col] if item in selected else [item]
        key = EDITABLE_COLUMNS[col]
        failed = []
        self.table.blockSignals(True)
        try:
            for it in targets:
                path = self.table.item(it.row(), 0).data(Qt.UserRole)
                try:
                    import h5py
                    with h5py.File(path, "r+") as f:
                        f.attrs[key] = text
                    self.conn.execute(f"UPDATE files SET {key}=? WHERE path=?", (text, path))
                    it.setText(text)
                    it.setToolTip(text)
                except Exception as exc:
                    failed.append(f"{os.path.basename(path)}: {exc}")
            self.conn.commit()
        finally:
            self.table.blockSignals(False)
        if failed:
            self.status_label.setText(f"could not write {key} for {len(failed)} file(s): "
                                      + "; ".join(failed[:3]) + " - refresh to restore")
        else:
            self.status_label.setText(f"set {key} = {text!r} on {len(targets)} file(s)")

    def _on_current_cell_changed(self, row: int, _col: int, prev_row: int, _prev_col: int) -> None:
        if row == prev_row or row < 0:
            return
        item = self.table.item(row, 0)
        self._path = item.data(Qt.UserRole) if item else None
        if not self._path:
            return
        self._load_panes(self._path)

    def _load_panes(self, path: str) -> None:
        self._busy = False
        self._load_png(path)
        self._load_datasets(path)
        self._load_config(path)
        self.replot_msg.setText("(press Replot)")

    # ---- right pane: png ----

    def _load_png(self, path: str) -> None:
        # ASSUMPTION (confirmed by the user): the saved figure always shares the h5
        # stem -- ExperimentClass derives fname/iname/cname from one stem. Experiments
        # that write extra figures with suffixes (e.g. '..._IQ.png') are not shown here.
        png = os.path.splitext(path)[0] + ".png"
        pix = QPixmap(png) if os.path.exists(png) else QPixmap()
        self.png_label.set_image(pix if not pix.isNull() else None,
                                 f"no png beside this file:\n{png}")

    # ---- right pane: data ----

    def _build_data_pane(self) -> QWidget:
        """Dataset list (header only) / the clicked dataset as a ValueView (tree + plot)
        / its values as numpy text -- abbreviated with '...' unless Show raw is on."""
        self.data_tree = QTreeWidget()
        self.data_tree.setHeaderLabels(["dataset", "shape", "dtype", "size"])
        self.data_tree.itemClicked.connect(self._on_dataset_clicked)
        self.data_view = ValueView()
        self.data_text = st.make_mono(QPlainTextEdit())
        self.data_text.setReadOnly(True)
        self._data_value = None
        self.show_raw_btn = QPushButton("Show raw")
        self.show_raw_btn.setCheckable(True)     # off by default; reset per selection
        self.show_raw_btn.setEnabled(False)
        self.show_raw_btn.setToolTip("Print every value instead of numpy's '...' summary")
        self.show_raw_btn.toggled.connect(lambda _on: self._render_data_text())
        text_box = QWidget()
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.addWidget(self.show_raw_btn, 0, Qt.AlignLeft)
        text_layout.addWidget(self.data_text, 1)
        split = QSplitter(Qt.Vertical)
        for w in (self.data_tree, self.data_view, text_box):
            split.addWidget(w)
        box = QWidget()
        layout = QVBoxLayout(box)
        hint = QLabel("Header only - click a dataset to load its values.")
        hint.setWordWrap(True)                   # never let a label set the column width
        layout.addWidget(hint)
        layout.addWidget(split, 1)
        return box

    def _show_data_value(self, value, label: Optional[str] = None) -> None:
        """New selection: tree + plot for an array, Show raw reset to off."""
        self._data_value = None if value is None else np.asarray(value)
        self.show_raw_btn.blockSignals(True)
        self.show_raw_btn.setChecked(False)
        self.show_raw_btn.blockSignals(False)
        if self._data_value is None:
            self.data_view.clear()
        else:
            self.data_view.set_value(self._data_value, label=label)
        self._render_data_text()

    def _render_data_text(self) -> None:
        """numpy's own summary ('...' past DATA_TEXT_THRESHOLD values) by default; every
        value with Show raw. The button only enables when the two would differ."""
        a = self._data_value
        if a is None:
            self.show_raw_btn.setEnabled(False)
            return
        abbreviated = a.size > DATA_TEXT_THRESHOLD
        self.show_raw_btn.setEnabled(abbreviated)
        full = self.show_raw_btn.isChecked() and abbreviated
        self.data_text.setPlainText(np.array2string(
            a, threshold=a.size + 1 if full else DATA_TEXT_THRESHOLD))

    def _load_datasets(self, path: str) -> None:
        """List name / shape / dtype / size from the h5 HEADER -- h5py exposes
        .shape/.dtype without reading any data."""
        import h5py
        from triangle_lattice_quench.Experiment import FileBeingSaved, open_for_reading
        self.data_tree.clear()
        self.data_text.clear()
        self._show_data_value(None)               # new file: no stale tree / plot
        self._datasets = {}
        try:
            with open_for_reading(path) as f:
                # Same level ExperimentClass.load_data reads from, so every listed
                # name is loadable; nested subgroups are shown but flagged.
                group = f["data"] if isinstance(f.get("data"), h5py.Group) else f
                for key in group:
                    obj = group[key]
                    if isinstance(obj, h5py.Dataset):
                        nbytes = int(obj.dtype.itemsize) * int(obj.size)
                        self._datasets[key] = {"nbytes": nbytes}
                        QTreeWidgetItem(self.data_tree, [key, str(obj.shape),
                                                         str(obj.dtype), human_bytes(nbytes)])
                    else:
                        QTreeWidgetItem(self.data_tree,
                                        [key, "(group)", "", "not loadable via load_data"])
        except FileBeingSaved:
            self._busy = True
            QTreeWidgetItem(self.data_tree, [dx.BUSY_MESSAGE, "", "", ""])
        except Exception as exc:
            QTreeWidgetItem(self.data_tree, [f"<unreadable: {exc}>", "", "", ""])

    def _on_dataset_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        key = item.text(0)
        info = self._datasets.get(key)
        if self._path is None or info is None:
            return
        if info["nbytes"] > CONFIRM_LOAD_BYTES:
            answer = QMessageBox.question(
                self, "Load dataset",
                f"{key} is {human_bytes(info['nbytes'])}. Load it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        import numpy as np
        from triangle_lattice_quench.Experiment import ExperimentClass, FileBeingSaved
        try:
            value = ExperimentClass.load_data(self._path, keys=[key])["data"][key]
        except FileBeingSaved:
            self._show_data_value(None)
            self.data_text.setPlainText(dx.BUSY_MESSAGE)
            return
        except Exception as exc:
            self._show_data_value(None)
            self.data_text.setPlainText(f"failed to load {key}: {exc}")
            return
        self._show_data_value(value, label=key)

    # ---- right pane: config ----

    def _load_config(self, path: str) -> None:
        """Config into the lazy tree (raw JSON one checkbox away). The one place the
        ~50 ms blob read is fine. Falls back to the sidecar .json."""
        from triangle_lattice_quench.Experiment import FileBeingSaved, open_for_reading
        problem = ""
        try:
            with open_for_reading(path) as f:
                blob = f.attrs.get("config")
            if blob is not None:
                self.config_pane.set_config(json.loads(blob))
                return
        except FileBeingSaved:
            self._busy = True
            self.config_pane.show_message(dx.BUSY_MESSAGE)
            return
        except Exception as exc:
            problem = f"(h5 config attr unreadable: {exc})\n"
        sidecar = os.path.splitext(path)[0] + ".json"
        try:
            with open(sidecar) as fid:
                self.config_pane.set_config(json.load(fid))
        except Exception as exc:
            self.config_pane.show_message(
                problem + f"(no config attr and no readable sidecar json: {exc})")

    # ---- right pane: plot (png + replot) ----

    def _build_plot_pane(self, png_scroll: QWidget) -> QWidget:
        """The archived png, with a Replot button (and its status text) underneath."""
        self.replot_msg = QLabel("(select a file)")
        self.replot_msg.setWordWrap(True)
        self._replot_windows = []                 # keep the windows alive
        btn = QPushButton("Replot")
        btn.setToolTip("Redraw this run from its data in a new window")
        btn.clicked.connect(self.on_replot)
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.addWidget(png_scroll, 1)
        row = QHBoxLayout()
        row.addWidget(btn)
        row.addWidget(self.replot_msg, 1)
        layout.addLayout(row)
        return box

    def on_replot(self) -> None:
        if not self._path:
            return
        from .replot import replot_into          # lazy: this is the only qick-adjacent path
        win = QWidget(None, Qt.Window)
        win.setWindowTitle(f"Replot - {Path(self._path).stem}")
        canvas = MplCanvas(win, height=6.0, layout="constrained")   # fig_axs displays rebuild the figure
        col = QVBoxLayout(win)
        col.addWidget(NavigationToolbar(canvas, win))
        col.addWidget(canvas, 1)
        win.resize(1100, 750)
        win.show()
        self._replot_windows = [w for w in self._replot_windows if w.isVisible()] + [win]
        self.replot_msg.setText(replot_into(self._path, canvas.ax))
        canvas.draw_idle()
