"""Lattice-point calibration tab.

Runs ``RamseyVsFF`` once per scheduled (drive_entry, readout_qubit) row to map
each qubit's frequency vs. its fast-flux bias, then writes the per-qubit FF
slot into the shared ``base_params``. Holds its own 1D row table
(``_LatticeRowTable``, a sibling of the AutoCalib ``CalibTable`` pattern) and an
off-thread worker.

Depends on state / helpers / widgets only.
"""
from __future__ import annotations

import time
import traceback
from typing import Any, Optional

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..state import CalibState
from ..helpers import build_cfg_for_qubit, _readout_qubit_for_entry
from ..widgets import (
    MplCanvas,
    ParamForm,
    SELECTION_ROLE,
    CalibCellDelegate,
    DragPainter,
)


class LatticePointCalibWorker(QThread):
    """Run ``RamseyVsFF`` once per scheduled (drive_entry, ro_qubit) row.

    Each row's sweep window is snapshotted on the GUI thread (so concurrent
    mutations of ``base_params`` between rows don't drift the start/stop) and
    handed in as part of the schedule. The worker subclasses ``RamseyVsFF``
    locally with a headless Agg ``display()`` to dodge the
    ``SweepExperimentND.acquire`` Qt-from-worker-thread deadlock (same fix as
    ``TwoQubitChevronWorker``); ``analyze()`` is then called to populate
    ``data["data"]["center_gain"]``.
    """

    progress     = pyqtSignal(str, str)                    # row_label, status text
    row_done     = pyqtSignal(str, object, object, float)  # row_label, expt, data, elapsed_s
    row_failed   = pyqtSignal(str, str, object, object, float)  # row_label, err, expt, data, elapsed_s
    log_msg      = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, state: CalibState, schedule: list[dict]):
        super().__init__()
        self.state = state
        # schedule: list of {row_label, ro_q, current_value, sweep_params}
        self.schedule = schedule
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        # Lazy import — RamseyVsFF pulls qick-flavored deps; keep GUI cold-start cheap.
        try:
            from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF import (
                RamseyVsFF,
            )
        except Exception as exc:
            self.log_msg.emit(f"[FATAL] cannot import RamseyVsFF: {exc}")
            self.finished_all.emit()
            return

        from matplotlib.figure import Figure as _BareFigure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        # Headless-display subclass: same workaround the TwoQubit worker uses.
        # SweepExperimentND.acquire()'s plot branch fires regardless of
        # plotDisp/plotSave (parenthesization bug at line 215); routing that
        # through an Agg canvas keeps Qt out of the worker thread.
        class _RamseyVsFFHeadless(RamseyVsFF):
            def display(self, data=None, plotDisp=False, figNum=1,
                        plotSave=False, block=False, fig_axs=None):
                fig = _BareFigure()
                FigureCanvasAgg(fig)
                ax = fig.add_subplot(111)
                return fig, [ax]

            def _update_fig(self, data, fig, axs):
                pass

        for row in self.schedule:
            if self._stop:
                self.log_msg.emit(f"--- aborted before {row['row_label']} ---")
                break
            row_label = row['row_label']
            ro_q = row['ro_q']
            current_value = row['current_value']
            sweep_params = row['sweep_params']
            t0 = time.perf_counter()
            self.progress.emit(row_label, "starting")
            expt = None
            data = None
            try:
                overrides = dict(sweep_params)
                overrides.update({
                    "qubit_FF_index": int(ro_q),
                    "FF_gain_start": int(current_value) - int(sweep_params["__window"]),
                    "FF_gain_stop":  int(current_value) + int(sweep_params["__window"]),
                    "FF_gain_steps": int(sweep_params["__steps"]),
                    "populations": False,
                })
                # Pop GUI-only carry-throughs before they reach cfg.
                overrides.pop("__window", None)
                overrides.pop("__steps", None)

                # build_cfg_for_qubit: drive entry = row_label, readout qubit = ro_q.
                cfg = build_cfg_for_qubit(
                    self.state, str(ro_q),
                    qubit_pulse=[row_label],
                    qubit_readout=[str(ro_q)],
                    overrides=overrides,
                )
                self.progress.emit(row_label, "acquiring")
                expt = _RamseyVsFFHeadless(
                    path="FF_vs_Ramsey",
                    cfg=cfg,
                    soc=self.state.soc, soccfg=self.state.soccfg,
                    outerFolder=self.state.outer_folder,
                )
                # Pass plotDisp/plotSave=False so the base acquire() doesn't
                # try to plt.show()/plt.savefig() from the worker thread; the
                # Agg-display subclass above already handles the inline
                # plot branch at line 215.
                data = None
                for kwargs in ({"progress": False, "plotDisp": False, "plotSave": False},
                               {"progress": False, "plotDisp": False},
                               {"progress": False}):
                    try:
                        data = expt.acquire(**kwargs)
                        break
                    except TypeError:
                        continue
                if data is None:
                    data = expt.acquire()
                # mRamseyVsFF.analyze() writes center_gain into data["data"].
                try:
                    expt.analyze(data)
                except Exception as ana_exc:
                    self.log_msg.emit(
                        f"[warn] analyze() raised for {row_label}: {ana_exc}"
                    )
                elapsed = time.perf_counter() - t0
                center_gain = data.get("data", {}).get("center_gain")
                if center_gain is None:
                    self.row_failed.emit(
                        row_label,
                        "Ramsey fit returned no center_gain",
                        expt, data, elapsed,
                    )
                    continue
                self.row_done.emit(row_label, expt, data, elapsed)
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                self.row_failed.emit(
                    row_label,
                    f"{exc}\n{traceback.format_exc()}",
                    expt, data, elapsed,
                )
        self.finished_all.emit()


class _LatticeRowTable(QTableWidget):
    """Whole-row click-toggle + drag-rectangle selection.

    Mirrors ``CalibTable``'s pattern but in 1D (row state only — no column
    structure). Clicking anywhere on a row toggles that row's selection;
    dragging extends the selection to every row between press and current,
    restoring rows that leave the range to their pre-drag state.
    """
    row_toggled = pyqtSignal(int, bool)   # (row, new_state) — emitted per row
    row_clicked = pyqtSignal(int)         # (row) — emitted on press for plot focus

    # Columns whose clicks should NOT toggle selection — they need normal Qt
    # event flow (e.g. double-click to enter an editor). Populated by the tab.
    PASSTHROUGH_COLS: set = set()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self._painter = DragPainter(
            target_at=self._row_at,
            get_state=self._row_state,
            set_state=lambda r, on: self.row_toggled.emit(r, on),
            region=lambda s, c, _: {r for r in range(min(s, c), max(s, c) + 1)
                                   if 0 <= r < self.rowCount()},
        )

    def _row_state(self, row: int) -> bool:
        item = self.item(row, 0)
        return bool(item.data(SELECTION_ROLE)) if item is not None else False

    def _row_at(self, pos) -> Optional[int]:
        r = self.indexAt(pos).row()
        return r if r >= 0 else None

    def mousePressEvent(self, event):
        idx = self.indexAt(event.pos())
        r, c = idx.row(), idx.column()
        if r < 0 or c in self.PASSTHROUGH_COLS:
            super().mousePressEvent(event)
            return
        if self._painter.press(event.pos()):
            self.row_clicked.emit(r)
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._painter.in_progress():
            super().mouseMoveEvent(event)
            return
        self._painter.move(event.pos())

    def mouseReleaseEvent(self, event):
        if not self._painter.release():
            super().mouseReleaseEvent(event)
            return
        event.accept()

    def mouseDoubleClickEvent(self, event):
        # Always let double-click through (enables in-place editing on
        # editable cells regardless of column).
        super().mouseDoubleClickEvent(event)


class LatticePointCalibrationTab(QWidget):
    """Per-qubit Ramsey-vs-FF calibration of a shared ``base_params`` array.

    The selected drive group (e.g. ``ramsey_3800+``) carries a ``_recipe.base``
    pointing at a base_params array key (e.g. ``Expt_3800``). Each enabled
    row runs RamseyVsFF on that drive entry, sweeps FF around the array's
    current slot, and writes the fitted ``center_gain`` back into one slot of
    that shared array. Subsequent rows in the same batch pick up the updated
    array (build_cfg_for_qubit re-resolves the recipe each call).
    """

    name = "Lattice Point Calibration"
    # Column 0 of the row table — selection layer is painted here via
    # SELECTION_ROLE + CalibCellDelegate.
    SEL_COL = 0

    # Δ-magnitude color thresholds. White below the lower bound, amber up to
    # the upper bound, red above. Easy to tweak.
    DELTA_AMBER_MIN = 50
    DELTA_RED_MIN   = 300

    COLOR_WHITE  = QColor("#ffffff")
    COLOR_AMBER  = QColor("#fff1c2")
    COLOR_RED    = QColor("#f8c4c4")
    COLOR_OK     = QColor("#cdf5cd")
    COLOR_FAIL   = QColor("#f8c4c4")
    COLOR_HEADER = QColor("#dcdcdc")

    # (key, label, kind, default) — matches ParamForm spec format.
    SWEEP_FIELDS = [
        ("window",        "FF window (± from current)", "int",   200),
        ("steps",         "FF steps",                   "int",   7),
        ("expts",         "Ramsey expts",               "int",   71),
        ("stop_delay_us", "Stop delay (us)",            "float", 1.0),
        ("reps",          "reps",                       "int",   200),
        ("relax_delay",   "relax_delay",                "float", 100.0),
    ]

    # Presets pre-fill (window, steps). Other fields stay user-controlled.
    PRESETS = {
        "Fine":  (200, 7),
        "Rough": (5000, 11),
    }

    def __init__(self, state: CalibState, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        self.worker: Optional[LatticePointCalibWorker] = None
        # row_label -> bool (enabled for next batch).
        self._row_enabled: dict[str, bool] = {}
        # row_label -> (expt, data) for plot rendering on row-click.
        self._row_results: dict[str, tuple[Any, Any]] = {}
        # row_label -> new center_gain (int) from last successful run.
        self._row_new_ff: dict[str, int] = {}
        # row_label -> "ok"|"fail"|None.
        self._row_status: dict[str, Optional[str]] = {}
        # row_label -> ro_q (cached on rebuild for quick lookup).
        self._row_ro_q: dict[str, str] = {}

        # --- top: selectors / read-only labels ---
        self.drive_group_combo = QComboBox()
        self.drive_group_combo.setMinimumWidth(180)
        self.drive_group_combo.setToolTip(
            "Recipe-driven drive group whose _recipe.base names the target "
            "base_params array."
        )
        self.drive_group_combo.currentIndexChanged.connect(self._on_drive_group_changed)
        self.target_array_lbl = QLabel("Target array: —")
        self.target_freq_lbl = QLabel("Drive frequency: —")
        self.readout_group_lbl = QLabel("Readout group: —")
        for lbl in (self.target_array_lbl, self.target_freq_lbl, self.readout_group_lbl):
            lbl.setStyleSheet("color: #444; font-weight: bold;")
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Drive group:"))
        top_row.addWidget(self.drive_group_combo)
        top_row.addSpacing(20)
        top_row.addWidget(self.target_array_lbl)
        top_row.addSpacing(20)
        top_row.addWidget(self.target_freq_lbl)
        top_row.addSpacing(20)
        top_row.addWidget(self.readout_group_lbl)
        top_row.addStretch(1)
        top_w = QWidget(); top_w.setLayout(top_row)

        # --- per-qubit table ---
        # Columns: sel | Drive entry | Qubit | Current FF | New FF | Δ | Status
        # Column 0 carries the selection layer (SELECTION_ROLE on its item,
        # painted with a border by CalibCellDelegate). Click-drag toggles
        # rows persistently — same gesture as AutoCalib.
        self.table = _LatticeRowTable()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["", "Drive entry", "Qubit", "Current FF", "New FF", "Δ", "Status"]
        )
        self.table.verticalHeader().setVisible(False)
        # Col 3 (Current FF) is editable — double-click or F2 to enter editor.
        # Clicks on col 3 bypass the row-toggle gesture so the editor opens.
        # Current FF == base_params[idx] (sweep center, saved to disk on Save).
        # Edits write through to base_params; clearing reverts to snapshot.
        self.table.PASSTHROUGH_COLS = {3}
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.table.setItemDelegate(CalibCellDelegate(self.table))
        self.table.row_toggled.connect(self._on_row_toggled)
        self.table.row_clicked.connect(self._on_row_clicked)
        # Guard against itemChanged firing during programmatic table rebuilds.
        self._suppress_item_changed = False
        self.table.itemChanged.connect(self._on_item_changed)
        # Per-row flag: True if Current FF was hand-edited (vs fit or snapshot).
        # Drives the italic+bold display on col 3.
        self._row_current_user_edited: set[str] = set()
        # Set by _on_drive_group_changed; consumed by _rebuild_table_unguarded
        # to discard fit results that belong to the prior group.
        self._drive_group_changed: bool = False

        # --- sweep parameter form ---
        self.param_form = ParamForm("Sweep parameters", self.SWEEP_FIELDS)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("(preset)", None)
        for name in self.PRESETS:
            self.preset_combo.addItem(name, name)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        preset_row.addWidget(self.preset_combo)
        preset_row.addStretch(1)
        preset_w = QWidget(); preset_w.setLayout(preset_row)

        # --- run controls ---
        self.run_btn = QPushButton("Run selected")
        self.run_btn.setStyleSheet("font-weight: bold;")
        self.run_btn.clicked.connect(self._on_run)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.clicked.connect(self._select_all)
        self.clear_btn = QPushButton("Clear selection")
        self.clear_btn.clicked.connect(self._clear_all)
        self.progress_lbl = QLabel("Idle.")
        run_row = QHBoxLayout()
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.stop_btn)
        run_row.addSpacing(16)
        run_row.addWidget(self.select_all_btn)
        run_row.addWidget(self.clear_btn)
        run_row.addSpacing(16)
        run_row.addWidget(self.progress_lbl, 1)
        run_w = QWidget(); run_w.setLayout(run_row)

        # --- log area ---
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        f = QFont(); f.setStyleHint(QFont.Monospace); f.setFamily("Consolas")
        self.log.setFont(f)
        self.log.setPlaceholderText("Per-row status appears here.")

        # --- right pane: plot canvas ---
        self.canvas = MplCanvas(self, height=4.5)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.plot_label = QLabel("Plot — click a row to view its last RamseyVsFF.")
        self.plot_label.setStyleSheet("color: #555;")

        # --- layout ---
        left_v = QVBoxLayout()
        left_v.setContentsMargins(0, 0, 0, 0)
        left_v.addWidget(self.table, 3)
        left_v.addWidget(self.param_form)
        left_v.addWidget(preset_w)
        left_v.addWidget(run_w)
        left_v.addWidget(self.log, 1)
        left_w = QWidget(); left_w.setLayout(left_v)

        right_v = QVBoxLayout()
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.addWidget(self.plot_label)
        right_v.addWidget(self.toolbar)
        right_v.addWidget(self.canvas, 1)
        right_w = QWidget(); right_w.setLayout(right_v)

        splitter = QSplitter()
        splitter.addWidget(left_w)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        outer = QVBoxLayout(self)
        outer.addWidget(top_w)
        outer.addWidget(splitter, 1)

        # Initial population (combos will be set by refresh_groups_from_state).
        self._update_run_enable()

    def showEvent(self, event):
        # The readout group is owned by AutoCalibTab; refresh our display
        # label every time we become visible so a switch over there is
        # reflected here. Cheap (just a label set).
        super().showEvent(event)
        self._refresh_readout_label()

    # ---- public hooks ----

    def refresh_groups_from_state(self) -> None:
        """Repopulate drive-group combo from state.qubit_parameters_json.

        Filters to drive groups whose ``_recipe.base`` is a string (i.e. the
        recipe-driven calibration tools — ``ramsey_3800+`` etc.); recipe-less
        groups like ``4Q_readout`` are excluded.
        """
        jd = self.state.qubit_parameters_json or {}
        dg = jd.get("drive_groups") or {}
        names: list[str] = []
        for gname, gbody in dg.items():
            if not isinstance(gbody, dict):
                continue
            recipe = gbody.get("_recipe")
            if not isinstance(recipe, dict):
                continue
            base = recipe.get("base")
            if isinstance(base, str) and base:
                names.append(gname)

        prev = self.drive_group_combo.currentData()
        self.drive_group_combo.blockSignals(True)
        self.drive_group_combo.clear()
        self.drive_group_combo.addItem("(none)", "")
        for n in names:
            self.drive_group_combo.addItem(n, n)
        # Try to restore prior selection so refreshes don't reset the user.
        if prev:
            for i in range(self.drive_group_combo.count()):
                if self.drive_group_combo.itemData(i) == prev:
                    self.drive_group_combo.setCurrentIndex(i)
                    break
            else:
                self.drive_group_combo.setCurrentIndex(0)
        else:
            self.drive_group_combo.setCurrentIndex(0)
        self.drive_group_combo.blockSignals(False)
        self._on_drive_group_changed(self.drive_group_combo.currentIndex())

    # ---- selectors / labels ----

    def _on_drive_group_changed(self, _idx: int) -> None:
        self._drive_group_changed = True
        self._refresh_readout_label()
        self._refresh_target_labels()
        self._rebuild_table()
        self._update_run_enable()

    def _refresh_readout_label(self) -> None:
        rg = self.state.current_readout_group or "—"
        self.readout_group_lbl.setText(f"Readout group: {rg}")

    def _refresh_target_labels(self) -> None:
        gname = self.drive_group_combo.currentData() or ""
        if not gname:
            self.target_array_lbl.setText("Target array: —")
            self.target_freq_lbl.setText("Drive frequency: —")
            return
        jd = self.state.qubit_parameters_json or {}
        gbody = (jd.get("drive_groups") or {}).get(gname, {}) or {}
        recipe = gbody.get("_recipe") or {}
        base = recipe.get("base", "?")
        self.target_array_lbl.setText(f"Target array: {base}")

        entries = gbody.get("entries") or {}
        freqs = []
        for ebody in entries.values():
            if isinstance(ebody, dict):
                q = ebody.get("Qubit", {}) or {}
                f = q.get("Frequency")
                if f is not None:
                    freqs.append(f)
        if not freqs:
            self.target_freq_lbl.setText("Drive frequency: —")
            return
        first = freqs[0]
        # Recipe-filtered groups always share the drive frequency; tolerate
        # disagreement with a ⚠ glyph just in case.
        all_same = all(f == first for f in freqs)
        warn = "" if all_same else " (!)"
        try:
            text = f"Drive frequency: {first:g} MHz{warn}"
        except Exception:
            text = f"Drive frequency: {first} MHz{warn}"
        self.target_freq_lbl.setText(text)

    # ---- table rebuild ----

    def _rebuild_table(self) -> None:
        """Rebuild rows from the selected drive group's entries.

        Preserves per-row enabled state, new-FF, status, and cached results
        for row labels that survive the rebuild.
        """
        self._suppress_item_changed = True
        try:
            self._rebuild_table_unguarded()
        finally:
            self._suppress_item_changed = False

    def _rebuild_table_unguarded(self) -> None:
        # Drive-group changes invalidate fit results and hand-edit flags
        # (those belong to a specific calibration session). Selection state
        # survives across groups when the entry name still exists.
        prev_enabled = dict(self._row_enabled)
        prev_new = dict(self._row_new_ff) if not self._drive_group_changed else {}
        prev_status = dict(self._row_status) if not self._drive_group_changed else {}
        prev_results = dict(self._row_results) if not self._drive_group_changed else {}
        if self._drive_group_changed:
            self._row_current_user_edited.clear()
            self._drive_group_changed = False
        # Re-derive from JSON.
        self._row_enabled = {}
        self._row_new_ff = {}
        self._row_status = {}
        self._row_results = {}
        self._row_ro_q = {}

        gname = self.drive_group_combo.currentData() or ""
        jd = self.state.qubit_parameters_json or {}
        gbody = (jd.get("drive_groups") or {}).get(gname, {}) or {}
        entries = list((gbody.get("entries") or {}).keys())
        base_name = (gbody.get("_recipe") or {}).get("base")
        base_arr = (jd.get("base_params") or {}).get(base_name) if base_name else None

        self.table.setRowCount(len(entries))
        for r, ename in enumerate(entries):
            ro_q = _readout_qubit_for_entry(ename)
            self._row_ro_q[ename] = ro_q
            # Restore prior state where the label survives.
            self._row_enabled[ename] = bool(prev_enabled.get(ename, False))
            if ename in prev_new:
                self._row_new_ff[ename] = prev_new[ename]
            if ename in prev_status:
                self._row_status[ename] = prev_status[ename]
            if ename in prev_results:
                self._row_results[ename] = prev_results[ename]

            # Col 0: selection cell. The visible glyph is intentionally
            # minimal — the selection state is communicated by the delegate-
            # painted border (CalibCellDelegate reads SELECTION_ROLE here).
            sel_item = QTableWidgetItem("")
            sel_item.setFlags(Qt.ItemIsEnabled)
            sel_item.setData(SELECTION_ROLE, self._row_enabled[ename])
            self.table.setItem(r, 0, sel_item)

            # Col 1: drive entry.
            it = QTableWidgetItem(ename)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(r, 1, it)

            # Col 2: ro qubit.
            it = QTableWidgetItem(ro_q)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 2, it)

            # Col 3: current FF (editable). Italic+bold when hand-edited
            # (state.qubit_parameters_json[base_name][idx] differs from the
            # on-disk snapshot due to a user keystroke rather than a fit).
            cur = None
            if isinstance(base_arr, list) and ro_q.isdigit():
                idx = int(ro_q) - 1
                if 0 <= idx < len(base_arr):
                    cur = base_arr[idx]
            cur_txt = "" if cur is None else str(cur)
            it = QTableWidgetItem(cur_txt)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            it.setTextAlignment(Qt.AlignCenter)
            if ename in self._row_current_user_edited:
                f = it.font(); f.setItalic(True); f.setBold(True); it.setFont(f)
            self.table.setItem(r, 3, it)

            # Col 4: New FF — read-only display of the most recent fit
            # result. Bold while a fit value is held; cleared on re-run.
            new_val = self._row_new_ff.get(ename)
            new_txt = "" if new_val is None else str(int(new_val))
            it = QTableWidgetItem(new_txt)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter)
            if new_val is not None:
                f = it.font(); f.setBold(True); it.setFont(f)
            self.table.setItem(r, 4, it)

            # Col 5: Δ = Current FF − Snapshot (the "save preview" — what
            # this row would write to disk on Save). Independent of fit.
            snap_val = self._snapshot_val_for_row(ename)
            delta_txt = ""
            delta_color = self.COLOR_WHITE
            if cur is not None and snap_val is not None:
                try:
                    delta = int(round(float(cur))) - int(snap_val)
                    delta_txt = f"{delta:+d}"
                    delta_color = self._delta_color(delta)
                except (TypeError, ValueError):
                    pass
            it = QTableWidgetItem(delta_txt)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(delta_color)
            self.table.setItem(r, 5, it)

            # Col 6: status.
            status = self._row_status.get(ename)
            stxt = ""
            sbg = self.COLOR_WHITE
            if status == "ok":
                stxt = "OK"; sbg = self.COLOR_OK
            elif status == "fail":
                stxt = "FAIL"; sbg = self.COLOR_FAIL
            it = QTableWidgetItem(stxt)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(sbg)
            self.table.setItem(r, 6, it)

        # Sizing: stretch Drive-entry / Status; narrow checkbox / qubit cols.
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setStretchLastSection(True)

    def _delta_color(self, delta: int) -> QColor:
        a = abs(int(delta))
        if a >= self.DELTA_RED_MIN:
            return self.COLOR_RED
        if a >= self.DELTA_AMBER_MIN:
            return self.COLOR_AMBER
        return self.COLOR_WHITE

    def _current_base_name(self) -> Optional[str]:
        gname = self.drive_group_combo.currentData() or ""
        jd = self.state.qubit_parameters_json or {}
        gbody = (jd.get("drive_groups") or {}).get(gname, {}) or {}
        return (gbody.get("_recipe") or {}).get("base")

    def _snapshot_val_for_row(self, ename: str):
        """Return snapshot.base_params[<base>][idx] for the row's qubit, or None."""
        snap = self.state.qubit_parameters_json_snapshot or {}
        base_name = self._current_base_name()
        if not base_name:
            return None
        snap_arr = (snap.get("base_params") or {}).get(base_name)
        if not isinstance(snap_arr, list):
            return None
        ro_q = self._row_ro_q.get(ename) or _readout_qubit_for_entry(ename)
        if not ro_q.isdigit():
            return None
        idx = int(ro_q) - 1
        if not (0 <= idx < len(snap_arr)):
            return None
        return snap_arr[idx]

    def _refresh_current_ff_column(self) -> None:
        """Re-read base_params[<array>] and rewrite Current FF + Δ for every row.

        Called after a successful row run (and after hand edits) so the
        visible Current FF tracks the in-memory state without rebuilding the
        whole table. Font is left untouched — italic+bold for user-edited
        rows is set by _on_item_changed / cleared by _on_row_done.
        Δ = Current − Snapshot.
        """
        jd = self.state.qubit_parameters_json or {}
        base_name = self._current_base_name()
        base_arr = (jd.get("base_params") or {}).get(base_name) if base_name else None
        if not isinstance(base_arr, list):
            return
        self._suppress_item_changed = True
        try:
            for r in range(self.table.rowCount()):
                ename_item = self.table.item(r, 1)
                if ename_item is None:
                    continue
                ename = ename_item.text()
                ro_q = self._row_ro_q.get(ename, "")
                if not ro_q.isdigit():
                    continue
                idx = int(ro_q) - 1
                if not (0 <= idx < len(base_arr)):
                    continue
                cur = base_arr[idx]
                cur_it = self.table.item(r, 3)
                if cur_it is not None:
                    cur_it.setText(str(cur))
                # Recompute Δ vs snapshot.
                snap_val = self._snapshot_val_for_row(ename)
                d_it = self.table.item(r, 5)
                if d_it is None:
                    continue
                if cur is None or snap_val is None:
                    d_it.setText("")
                    d_it.setBackground(self.COLOR_WHITE)
                    continue
                try:
                    delta = int(round(float(cur))) - int(snap_val)
                    d_it.setText(f"{delta:+d}")
                    d_it.setBackground(self._delta_color(delta))
                except (TypeError, ValueError):
                    d_it.setText("")
                    d_it.setBackground(self.COLOR_WHITE)
        finally:
            self._suppress_item_changed = False

    # ---- selection helpers ----

    def _ename_for_row(self, row: int) -> Optional[str]:
        it = self.table.item(row, 1)
        return it.text() if it is not None else None

    def _set_row_selection(self, row: int, on: bool) -> None:
        """Single source of truth for the selection layer: updates the
        per-row enabled flag AND the col-0 item's SELECTION_ROLE so the
        delegate repaints the border."""
        ename = self._ename_for_row(row)
        if ename is None:
            return
        self._row_enabled[ename] = bool(on)
        sel_item = self.table.item(row, 0)
        if sel_item is not None:
            sel_item.setData(SELECTION_ROLE, bool(on))

    def _on_row_toggled(self, row: int, new_state: bool) -> None:
        self._set_row_selection(row, new_state)
        self._update_run_enable()

    def _on_row_clicked(self, row: int) -> None:
        # Row press also drives the right-pane plot focus (mirrors AutoCalib).
        self._on_row_selected(row)

    def _select_all(self) -> None:
        for r in range(self.table.rowCount()):
            self._set_row_selection(r, True)
        self._update_run_enable()

    def _clear_all(self) -> None:
        for r in range(self.table.rowCount()):
            self._set_row_selection(r, False)
        self._update_run_enable()

    def _base_arr_for_row(self, ename: str):
        """Return (base_arr, idx) for the in-memory base_params slot that
        backs ``ename``, or (None, None) if any link in the chain is missing.
        """
        gname = self.drive_group_combo.currentData() or ""
        jd = self.state.qubit_parameters_json or {}
        gbody = (jd.get("drive_groups") or {}).get(gname, {}) or {}
        base_name = (gbody.get("_recipe") or {}).get("base")
        base_arr = (jd.get("base_params") or {}).get(base_name) if base_name else None
        ro_q = self._row_ro_q.get(ename) or _readout_qubit_for_entry(ename)
        if not (isinstance(base_arr, list) and ro_q.isdigit()):
            return None, None
        idx = int(ro_q) - 1
        if not (0 <= idx < len(base_arr)):
            return None, None
        return base_arr, idx

    def _write_base_arr_slot(self, ename: str, value: int) -> None:
        """Write ``value`` into the live base_params slot for ``ename``."""
        base_arr, idx = self._base_arr_for_row(ename)
        if base_arr is None:
            return
        base_arr[idx] = int(value)
        self._refresh_current_ff_column()

    def _restore_snapshot_slot(self, ename: str) -> None:
        """Revert the live base_params slot for ``ename`` to its on-disk
        snapshot value. Used when the user clears the Current FF cell.
        """
        base_arr, idx = self._base_arr_for_row(ename)
        if base_arr is None:
            return
        snap_val = self._snapshot_val_for_row(ename)
        if snap_val is not None:
            base_arr[idx] = snap_val
            self._refresh_current_ff_column()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Handle in-place edit of the Current FF cell (col 3).

        Current FF *is* the sweep center — base_params[<base>][idx] in the
        held JSON. Empty text reverts the slot to its snapshot value (and
        clears the italic+bold marker). Valid int writes through to the
        slot and italic+bold-marks the cell. Invalid text reverts the cell
        text without touching state.
        """
        if self._suppress_item_changed:
            return
        if item.column() != 3:
            return
        r = item.row()
        ename = self._ename_for_row(r)
        if ename is None:
            return
        text = item.text().strip()
        if text == "":
            new_val = None
        else:
            try:
                new_val = int(round(float(text)))
            except ValueError:
                # Revert to whatever's in state — base_arr[idx] is the
                # authoritative source.
                base_arr, idx = self._base_arr_for_row(ename)
                prev = base_arr[idx] if base_arr is not None else None
                self._suppress_item_changed = True
                try:
                    item.setText("" if prev is None else str(prev))
                finally:
                    self._suppress_item_changed = False
                return
        # Commit to the in-memory JSON's base_params slot.
        if new_val is None:
            self._row_current_user_edited.discard(ename)
            self._restore_snapshot_slot(ename)
        else:
            self._row_current_user_edited.add(ename)
            self._write_base_arr_slot(ename, new_val)
        # Italic+bold flag — under signal-suppress so setFont/setText below
        # doesn't re-enter this handler.
        self._suppress_item_changed = True
        try:
            f = item.font()
            edited = ename in self._row_current_user_edited
            f.setItalic(edited); f.setBold(edited)
            item.setFont(f)
        finally:
            self._suppress_item_changed = False

    def _update_run_enable(self) -> None:
        has_drive = bool(self.drive_group_combo.currentData() or "")
        busy = self.worker is not None and self.worker.isRunning()
        any_checked = any(self._row_enabled.values())
        self.run_btn.setEnabled(has_drive and any_checked and not busy)
        self.stop_btn.setEnabled(busy)
        self.select_all_btn.setEnabled(has_drive and not busy)
        self.clear_btn.setEnabled(has_drive and not busy)
        self.drive_group_combo.setEnabled(not busy)

    # ---- preset form filler ----

    def _on_preset_changed(self, _idx: int) -> None:
        name = self.preset_combo.currentData()
        if name not in self.PRESETS:
            return
        window, steps = self.PRESETS[name]
        # Mutate widget values via ParamForm internals.
        w_window = self.param_form.widgets.get("window")
        w_steps = self.param_form.widgets.get("steps")
        if w_window is not None:
            w_window.setValue(int(window))
        if w_steps is not None:
            w_steps.setValue(int(steps))

    # ---- row click -> render plot ----

    def _on_row_selected(self, row: int) -> None:
        if row < 0 or row >= self.table.rowCount():
            return
        ename_item = self.table.item(row, 1)
        if ename_item is None:
            return
        ename = ename_item.text()
        entry = self._row_results.get(ename)
        self.canvas.reset()
        if entry is None:
            self.canvas.ax.text(
                0.5, 0.5, "(no data yet — run this calibration first)",
                ha="center", va="center",
                transform=self.canvas.ax.transAxes, color="#888",
            )
            self.canvas.ax.set_xticks([]); self.canvas.ax.set_yticks([])
            self.canvas.draw()
            self.plot_label.setText(f"Plot — {ename}: (no data)")
            return
        expt, data = entry
        try:
            # RamseyVsFF inherits SweepExperiment2D_plots whose _display_plot
            # signature is (data, fig_axs=(fig, axs)). Render onto our canvas.
            # The parent's _display_plot calls fig.show(), which matplotlib
            # rejects for non-pyplot figures — temporarily neuter it.
            _show = self.canvas.fig.show
            self.canvas.fig.show = lambda *a, **kw: None
            try:
                expt._display_plot(data, fig_axs=(self.canvas.fig, [self.canvas.ax]))
            finally:
                self.canvas.fig.show = _show
        except Exception as exc:
            self.canvas.ax.text(
                0.5, 0.5, f"render failed:\n{exc}",
                ha="center", va="center",
                transform=self.canvas.ax.transAxes,
            )
            traceback.print_exc()
        self.canvas.draw()
        self.plot_label.setText(f"Plot — {ename}")

    # ---- run / stop ----

    def _on_run(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.state.is_connected():
            QMessageBox.warning(self, "Not connected",
                                "Connect to the RFSoC before running.")
            return
        gname = self.drive_group_combo.currentData() or ""
        if not gname:
            QMessageBox.information(self, "No drive group",
                                    "Select a recipe-driven drive group first.")
            return
        jd = self.state.qubit_parameters_json or {}
        gbody = (jd.get("drive_groups") or {}).get(gname, {}) or {}
        base_name = (gbody.get("_recipe") or {}).get("base")
        if not base_name or base_name not in (jd.get("base_params") or {}):
            QMessageBox.critical(self, "Bad drive group",
                                 f"Drive group {gname!r} has no resolvable _recipe.base.")
            return
        base_arr = jd["base_params"][base_name]
        if not isinstance(base_arr, list):
            QMessageBox.critical(self, "Bad base_params",
                                 f"base_params[{base_name!r}] is not a list.")
            return

        params = self.param_form.values()
        # Snapshot each row's current_value at schedule time so the worker's
        # FF_gain_start/stop bounds don't drift if a prior row mutates the
        # slot before the next row starts.
        schedule: list[dict] = []
        for ename, enabled in self._row_enabled.items():
            if not enabled:
                continue
            ro_q = self._row_ro_q.get(ename) or _readout_qubit_for_entry(ename)
            if not ro_q.isdigit():
                self.log.appendPlainText(
                    f"[skip] {ename}: cannot parse readout qubit index"
                )
                continue
            idx = int(ro_q) - 1
            if not (0 <= idx < len(base_arr)):
                self.log.appendPlainText(
                    f"[skip] {ename}: ro qubit {ro_q} out of bounds for {base_name}"
                )
                continue
            # Sweep center is Current FF == base_arr[idx] in the held JSON.
            # Hand-edits and prior fits both flow through this slot.
            current_value = base_arr[idx]
            if not isinstance(current_value, (int, float)):
                self.log.appendPlainText(
                    f"[skip] {ename}: base_params[{base_name}][{idx}] is "
                    f"non-numeric ({current_value!r})"
                )
                continue
            sweep_params = {
                # Carry-throughs the worker consumes (not forwarded to cfg).
                "__window": int(params["window"]),
                "__steps":  int(params["steps"]),
                # Forwarded to cfg via overrides.
                "expts":         int(params["expts"]),
                "stop_delay_us": float(params["stop_delay_us"]),
                "reps":          int(params["reps"]),
                "relax_delay":   float(params["relax_delay"]),
            }
            schedule.append({
                "row_label":     ename,
                "ro_q":          ro_q,
                "current_value": int(current_value),
                "sweep_params":  sweep_params,
            })
        if not schedule:
            QMessageBox.information(
                self, "Nothing to run",
                "Tick at least one row's checkbox to enable it for the batch."
            )
            return

        # Reset status for queued rows.
        for row in schedule:
            ename = row["row_label"]
            self._row_status[ename] = None
            self._set_row_cell(ename, 6, "queued", self.COLOR_WHITE)
            # Clear stale plot if user re-runs.
            self._row_results.pop(ename, None)

        self.canvas.reset()
        self.plot_label.setText("Plot — running...")
        self.log.clear()
        self.log.appendPlainText(
            f"Running {len(schedule)} row(s) on drive group {gname!r} -> {base_name}."
        )
        self.progress_lbl.setText(f"Running {len(schedule)} row(s)...")
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.drive_group_combo.setEnabled(False)
        self.select_all_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)

        self.worker = LatticePointCalibWorker(self.state, schedule)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.row_done.connect(self._on_row_done)
        self.worker.row_failed.connect(self._on_row_failed)
        self.worker.log_msg.connect(self.log.appendPlainText)
        self.worker.finished_all.connect(self._on_all_finished)
        self.worker.start()

    def _on_stop(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.log.appendPlainText("[STOP] requested — finishing current row...")
            self.stop_btn.setEnabled(False)

    # ---- worker signal handlers ----

    def _on_worker_progress(self, row_label: str, status: str) -> None:
        self._set_row_cell(row_label, 6, status, self.COLOR_WHITE)
        self.progress_lbl.setText(f"{row_label}: {status}")

    def _on_row_done(self, row_label: str, expt, data, elapsed_s: float) -> None:
        center_gain = data.get("data", {}).get("center_gain") if data else None
        if center_gain is None:
            # Defensive: worker shouldn't emit row_done without center_gain.
            self._on_row_failed(row_label, "row_done with no center_gain", expt, data, elapsed_s)
            return
        new_ff = int(round(float(center_gain)))
        ro_q = self._row_ro_q.get(row_label) or _readout_qubit_for_entry(row_label)
        base_name = self._current_base_name()
        jd = self.state.qubit_parameters_json or {}
        base_arr = (jd.get("base_params") or {}).get(base_name) if base_name else None
        old_val = None
        if isinstance(base_arr, list) and ro_q.isdigit():
            idx = int(ro_q) - 1
            if 0 <= idx < len(base_arr):
                old_val = base_arr[idx]
                base_arr[idx] = new_ff

        # Record in caches. A successful fit clears the hand-edit marker
        # (Current FF font drops italic+bold below) — the cell now reflects
        # a fit, not a user keystroke.
        self._row_new_ff[row_label] = new_ff
        self._row_current_user_edited.discard(row_label)
        self._row_status[row_label] = "ok"
        self._row_results[row_label] = (expt, data)

        # New FF cell: text = fit value, bold.
        self._suppress_item_changed = True
        try:
            new_item = self._set_row_cell(row_label, 4, str(new_ff), None)
            if new_item is not None:
                new_item.setTextAlignment(Qt.AlignCenter)
                f = new_item.font(); f.setBold(True); new_item.setFont(f)
            # Current FF cell: text = fit value, no italic+bold (not hand-edited).
            cur_item = self._set_row_cell(row_label, 3, str(new_ff), None)
            if cur_item is not None:
                cur_item.setTextAlignment(Qt.AlignCenter)
                f = cur_item.font(); f.setItalic(False); f.setBold(False); cur_item.setFont(f)
        finally:
            self._suppress_item_changed = False
        self._set_row_cell(row_label, 6, "OK", self.COLOR_OK)
        # Δ + Current FF column refresh for this row and every other row
        # (a fit can shift the shared base_arr; Δ on other rows is unaffected
        # since they own different slots, but the call is idempotent).
        self._refresh_current_ff_column()

        snap_val = self._snapshot_val_for_row(row_label)
        old_txt = old_val if old_val is not None else "—"
        delta_str = (f"Δ {new_ff - int(snap_val):+d} (vs disk)"
                     if isinstance(snap_val, (int, float)) else "")
        self.log.appendPlainText(
            f"[OK]   ({elapsed_s:5.1f} s)  {row_label}  "
            f"{base_name}[{int(ro_q) - 1 if ro_q.isdigit() else '?'}]: "
            f"{old_txt} -> {new_ff}  {delta_str}"
        )
        # Notify the params tab so the tree refreshes.
        try:
            self.get_main().refresh_qubit_summary()
        except Exception:
            pass

    def _on_row_failed(self, row_label: str, err: str, expt, data, elapsed_s: float) -> None:
        self._row_status[row_label] = "fail"
        if expt is not None and data is not None:
            self._row_results[row_label] = (expt, data)
        self._set_row_cell(row_label, 6, "FAIL", self.COLOR_FAIL)
        first, _, rest = err.partition("\n")
        self.log.appendPlainText(
            f"[FAIL] ({elapsed_s:5.1f} s)  {row_label}  {first}"
        )
        for line in rest.rstrip().splitlines():
            self.log.appendPlainText(f"       {line}")

    def _on_all_finished(self) -> None:
        self.progress_lbl.setText("Done.")
        self.worker = None
        self._update_run_enable()
        # Re-enable controls that were locked during the run.
        self.drive_group_combo.setEnabled(True)
        self.select_all_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)

    # ---- helpers ----

    def _row_index_for(self, row_label: str) -> Optional[int]:
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 1)
            if it is not None and it.text() == row_label:
                return r
        return None

    def _set_row_cell(self, row_label: str, col: int, text: str,
                      bg: Optional[QColor]) -> Optional[QTableWidgetItem]:
        r = self._row_index_for(row_label)
        if r is None:
            return None
        it = self.table.item(r, col)
        if it is None:
            it = QTableWidgetItem(text)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, col, it)
        else:
            it.setText(text)
        if bg is not None:
            it.setBackground(bg)
        return it


# ---------------------------------------------------------------------------
# Qblox D5a coupler-bias loader, worker, and dialog
# ---------------------------------------------------------------------------
