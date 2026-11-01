"""BobWidget: the whole editor as one QWidget, so Desq or the calibration GUI can host it.

    w = BobWidget()
    w.set_calibration_path(".../qubit_parameters.json")
    desq.central_tabs.addTab(w, "Bob")

Signals: ``sequence_changed`` after any edit, ``title_changed`` and ``status_message`` for the host window.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QApplication, QCheckBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                             QScrollArea, QShortcut, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ..runner.experiment import BobExperiment
from . import icons, style
from .canvas.canvas import SequenceCanvas
from .controller import BOB_ROOT, Controller
from .panels.data_panel import DataPanel
from .panels.inspector import InspectorPanel
from .panels.palette import LIB, PalettePanel
from .panels.preview import PreviewPanel
from .panels.problems import ProblemsPanel
from .panels.resolved_view import ResolvedPanel
from .panels.settings_panel import SettingsPanel
from .topbar import TopBar
from .widgets import ElidedLabel, scrollable


class _DryRun(QThread):
    """Compile every sweep point off the GUI thread, on a copy of the sequence."""
    done = pyqtSignal(dict)

    def __init__(self, ctl):
        super().__init__()
        self.exp = BobExperiment(ctl.seq.clone(), ctl.station, ctl.calib)

    def run(self):
        try:
            self.done.emit(self.exp.dry_run())
        except Exception as exc:
            self.done.emit({"error": str(exc)})


class BobWidget(QWidget):
    sequence_changed = pyqtSignal()
    title_changed = pyqtSignal(str)
    status_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bob_root")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.ctl = Controller(self)
        # the RFSoC: replaced in tests by a stand-in board (see tests/test_gui.py)
        from ..hardware.connection import connect_station
        self.connect_rfsoc = connect_station
        self.program_class = None
        self._run = None                       # (RunWorker, RunRecord) while a run is going

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.topbar = TopBar()
        root.addWidget(self.topbar)

        self.palette = PalettePanel()
        self.palette.setMinimumWidth(190)
        self.inspector = InspectorPanel(self.ctl)
        self.inspector.setMinimumWidth(290)

        # center: canvas over the dock
        canvas_box = QWidget()
        canvas_box.setObjectName("panel")
        cl = QVBoxLayout(canvas_box)
        cl.setContentsMargins(8, 8, 8, 0)
        cl.setSpacing(6)
        head = QHBoxLayout()
        title = QLabel("Sequence")
        title.setObjectName("section_title")
        head.addWidget(title)
        self.hint = ElidedLabel("Time runs left to right. Drop segments on the flux track and pulses into a "
                                "qubit's lane.")
        self.hint.setObjectName("muted")
        head.addWidget(self.hint, 1)
        self.legend = self._make_legend()
        head.addWidget(self.legend)
        head.addSpacing(10)
        self.scale_box = QCheckBox("Columns to scale")
        self.scale_box.toggled.connect(self._toggle_scale)
        head.addWidget(self.scale_box)
        cl.addLayout(head)
        self.canvas = SequenceCanvas(self.ctl)
        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setWidget(self.canvas)
        self.canvas_scroll.setWidgetResizable(False)
        self.canvas_scroll.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.canvas_scroll.setMinimumHeight(220)   # scrolls when the window is short
        cl.addWidget(self.canvas_scroll, 1)

        self.dock = QTabWidget()
        self.preview = PreviewPanel(self.ctl)
        self.problems = ProblemsPanel(self.ctl)
        self.resolved = ResolvedPanel(self.ctl)
        self.settings_panel = SettingsPanel(self.ctl)
        self.data_panel = DataPanel(self.ctl)
        self.dock.addTab(self.preview, "Preview")
        self.dock.addTab(self.data_panel, "Data")
        self.dock.addTab(self.problems, "Problems")
        self.dock.addTab(self.resolved, "Resolved")
        self.settings_scroll = scrollable(self.settings_panel)
        self.dock.addTab(self.settings_scroll, "Experiment")

        center = QSplitter(Qt.Vertical)
        center.addWidget(canvas_box)
        center.addWidget(self.dock)
        center.setStretchFactor(0, 3)
        center.setStretchFactor(1, 2)
        center.setChildrenCollapsible(False)
        self.center = center

        main = QSplitter(Qt.Horizontal)
        main.addWidget(self.palette)
        main.addWidget(center)
        main.addWidget(self.inspector)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setStretchFactor(2, 0)
        main.setSizes([250, 900, 360])
        main.setChildrenCollapsible(False)
        root.addWidget(main, 1)

        self._wire()
        self.apply_style()
        self.ctl.refresh_now()
        self._update_title()

    # ================================================================== wiring
    def _wire(self):
        tb, ctl = self.topbar, self.ctl
        tb.new_btn.clicked.connect(self.new)
        tb.open_btn.clicked.connect(self.open_dialog)
        tb.save_btn.clicked.connect(self.save)
        tb.export_btn.clicked.connect(self.export_python)
        tb.undo_btn.clicked.connect(ctl.undo.undo)
        tb.redo_btn.clicked.connect(ctl.undo.redo)
        ctl.undo.canUndoChanged.connect(tb.undo_btn.setEnabled)
        ctl.undo.canRedoChanged.connect(tb.redo_btn.setEnabled)
        tb.undo_btn.setEnabled(False)
        tb.redo_btn.setEnabled(False)
        tb.calib_btn.clicked.connect(self.choose_calibration)
        tb.station.setCurrentText(ctl.station.name)
        tb.station.activated.connect(lambda _: ctl.set_station(tb.station.currentText()))
        tb.dry_btn.clicked.connect(self.dry_run)
        tb.run_btn.clicked.connect(self.run)
        tb.sim_btn.toggled.connect(lambda _: self._update_run_button())
        self.data_panel.stop_requested.connect(self.stop_run)
        ctl.refreshed.connect(self._update_run_button)
        ctl.changed.connect(self._update_run_button)
        # the status pill is a plain QLabel; clicking it opens the Problems tab
        tb.status.mousePressEvent = lambda e: self.dock.setCurrentWidget(self.problems)
        self.problems.count_changed.connect(lambda e, w, i: tb.set_status(e, w))
        self.problems.count_changed.connect(self._update_problems_tab)
        self.palette.open_template.connect(lambda p: self.open_path(p, as_template=True))
        self.inspector.request_experiment_tab.connect(lambda: self.dock.setCurrentWidget(self.settings_scroll))
        ctl.files_changed.connect(self._update_title)
        ctl.changed.connect(self._update_title)          # a rename anywhere shows in the title at once
        tb.title.renamed.connect(ctl.set_name)
        ctl.changed.connect(self.sequence_changed.emit)
        ctl.message.connect(self.status_message.emit)
        self.canvas.request_open_inspector.connect(lambda _: self.inspector.setFocus())
        for keys, fn in [("Ctrl+N", self.new), ("Ctrl+O", self.open_dialog), ("Ctrl+S", self.save),
                         ("Ctrl+Shift+S", self.save_as), ("Ctrl+E", self.export_python), ("Ctrl+Z", ctl.undo.undo),
                         ("Ctrl+Shift+Z", ctl.undo.redo), ("Ctrl+Y", ctl.undo.redo)]:
            QShortcut(QKeySequence(keys), self, activated=fn)

    def _toggle_scale(self, on):
        self.canvas.to_scale = on
        self.canvas._relayout()

    # ================================================================== style
    def apply_style(self):
        """Style the whole app when Bob owns the window; only this widget when embedded (e.g. in Desq)."""
        app = QApplication.instance()
        if app is not None and app.property("bob_look") == "Fusion":
            pass                                         # Bob's own window: the app already has Bob's look
        elif app is not None and self.window() is self:
            app.setStyleSheet(style.stylesheet())
        else:
            self.setStyleSheet(style.stylesheet())
        self.canvas.update()

    # ================================================================== files
    def _update_title(self):
        ctl = self.ctl
        name = ctl.seq.name or "Untitled"
        where = f"  ·  {ctl.doc_path.name}" if ctl.doc_path else ""
        dot = "  •" if ctl.dirty else ""
        self.topbar.title.set_title(name, f"{name}{where}{dot}")
        self.topbar.set_calibration_label(ctl.calib.path, ctl.calib_error is None)
        self.topbar.station.setCurrentText(ctl.station.name)
        self.title_changed.emit(f"{name}{dot} — Bob")

    def _make_legend(self) -> QLabel:
        """Key to the chip markings; hover a marking on the canvas for its fields."""
        c = style.CANVAS
        dot, tri, sq = "\u25CF", "\u25B2", "\u25A2"

        def mark(color, ch, size=13):
            return f"<span style='color:{color}; font-size:{size}px'>{ch}</span>"
        cal, swp = mark(c["badge_ref"], dot), mark(c["badge_sweep"], tri)
        warn, err, sel = mark(c["warning"], sq, 14), mark(c["error"], sq, 14), mark(c["select"], sq, 14)
        lab = QLabel(f"{cal} calibration &nbsp; {swp} swept &nbsp; {warn} warning &nbsp; {err} error")
        lab.setObjectName("muted")
        lab.setToolTip("<b>Chip markings</b><br>"
                       f"{cal} a field reads from the calibration (or station) file<br>"
                       f"{swp} a field is swept over an experiment axis<br>"
                       f"{warn} orange border: the block has a warning<br>"
                       f"{err} red border: the block has an error<br>"
                       f"{sel} blue border: selected<br>"
                       "Hover a dot or triangle on the canvas to see which fields.")
        return lab

    def _update_problems_tab(self, errors: int, warnings: int, infos: int):
        """Problems tab label: count of errors + warnings, icon of the worst level; notes only in the tooltip."""
        from .panels.problems import ICON
        i = self.dock.indexOf(self.problems)
        n = errors + warnings
        self.dock.setTabText(i, f"Problems ({n})" if n else "Problems")
        level = "error" if errors else "warning" if warnings else "info" if infos else None
        if level:
            name, color = ICON[level]
            self.dock.setTabIcon(i, icons.icon(name, color, 14))
        else:
            from PyQt5.QtGui import QIcon
            self.dock.setTabIcon(i, QIcon())
        parts = [f"{k} {lbl}{'s' if k != 1 else ''}" for k, lbl in
                 ((errors, "error"), (warnings, "warning"), (infos, "note")) if k]
        self.dock.setTabToolTip(i, ", ".join(parts) if parts else "No problems")

    def _confirm_discard(self) -> bool:
        if not self.ctl.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save changes to this sequence first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def new(self):
        if self._confirm_discard():
            self.ctl.new_sequence()

    def open_dialog(self):
        if not self._confirm_discard():
            return
        start = str(self.ctl.doc_path.parent) if self.ctl.doc_path else str(LIB / "templates")
        path, _ = QFileDialog.getOpenFileName(self, "Open sequence", start, "Bob sequence (*.json)")
        if path:
            self.open_path(path)

    def open_path(self, path, as_template=False):
        if as_template and not self._confirm_discard():
            return
        try:
            self.ctl.open_sequence(path, as_template=as_template)
        except Exception as exc:
            QMessageBox.warning(self, "Couldn't open", f"{path}\n\n{exc}")
            return
        self.status_message.emit(f"Opened {'template ' if as_template else ''}{Path(path).name}")

    def _attempt(self, what: str, action) -> bool:
        """Run a file operation; on failure show why instead of failing silently. Returns success."""
        try:
            action()
            return True
        except Exception as exc:
            QMessageBox.warning(self, f"Could not {what}", f"{exc}\n\nNothing was lost: the sequence is still "
                                                           "open in Bob.")
            return False

    def save(self) -> bool:
        if self.ctl.doc_path is None:
            return self.save_as()
        if not self._attempt("save", self.ctl.save):
            return False
        self.status_message.emit(f"Saved {self.ctl.doc_path.name}")
        return True

    def save_as(self) -> bool:
        slug = re.sub(r"[^A-Za-z0-9_]+", "_", self.ctl.seq.name.strip().lower()).strip("_") or "sequence"
        folder = self.ctl.doc_path.parent if self.ctl.doc_path else BOB_ROOT.parent
        path, _ = QFileDialog.getSaveFileName(self, "Save sequence", str(folder / f"{slug}.json"),
                                              "Bob sequence (*.json)")
        if not path or not self._attempt("save", lambda: self.ctl.save(path)):
            return False
        self.status_message.emit(f"Saved {Path(path).name}")
        return True

    def export_python(self) -> bool:
        """Ask where to write the experiment as a Python script, then write it."""
        slug = re.sub(r"[^A-Za-z0-9_]+", "_", self.ctl.seq.name.strip().lower()).strip("_") or "experiment"
        start = str((self.ctl.doc_path.parent if self.ctl.doc_path else BOB_ROOT.parent) / f"{slug}.py")
        path, _ = QFileDialog.getSaveFileName(self, "Export as Python", start, "Python script (*.py)")
        return bool(path) and self.export_python_to(path)

    def export_python_to(self, path) -> bool:
        from ..runner.export import ExportError, export_python
        ctl = self.ctl
        try:
            out = export_python(ctl.seq, ctl.station, ctl.calib, path,
                                source=str(ctl.doc_path) if ctl.doc_path else "")
        except ExportError as exc:
            QMessageBox.warning(self, "Cannot export", str(exc))
            return False
        except OSError as exc:
            QMessageBox.warning(self, "Cannot export", f"Could not write {path}:\n{exc}")
            return False
        self.status_message.emit(f"Exported {Path(out).name}. Run it with: python {Path(out).name}")
        return True

    def choose_calibration(self):
        start = self.ctl.calib.path or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choose calibration file", start, "Qubit parameters (*.json)")
        if path:
            self.set_calibration_path(path)

    def set_calibration_path(self, path):
        self.ctl.set_calibration(path)

    def save_preset(self, block_id):
        preset = self.ctl.block_as_preset(block_id)
        if preset is None:
            return
        name, ok = QInputDialog.getText(self, "Save as preset", "Preset name", text=preset["name"])
        if not ok or not name.strip():
            return
        preset["name"] = name.strip()
        slug = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip().lower()).strip("_") or "preset"
        path = LIB / "presets" / f"{slug}.json"
        if path.exists():
            answer = QMessageBox.question(self, "Replace preset?", f"A preset file {path.name} already exists. "
                                          "Replace it?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        if not self._attempt("save the preset",
                             lambda: path.write_text(json.dumps(preset, indent=2), encoding="utf-8")):
            return
        self.palette.reload()
        self.status_message.emit(f"Saved preset {name.strip()}")

    # ================================================================== dry run
    def dry_run(self):
        self.topbar.dry_btn.setEnabled(False)
        self.topbar.dry_btn.setText(" Checking…")
        self._dry = _DryRun(self.ctl)
        self._dry.done.connect(self._dry_done)
        self._dry.start()

    def _dry_done(self, result):
        self.topbar.dry_btn.setEnabled(True)
        self.topbar.dry_btn.setText(" Dry run")
        if "error" in result:
            QMessageBox.warning(self, "Dry run failed", result["error"])
            return
        n, ok = result["n"], result["n_ok"]
        if ok == n:
            longest = max((p["samples"] or 0) for p in result["points"])
            QMessageBox.information(self, "Dry run", f"All {n} sweep point{'s' if n != 1 else ''} compile.\n\n"
                                    f"Longest FF waveform: {longest} samples per channel "
                                    f"({longest / self.ctl.station.samples_per_us:.3g} µs).")
        else:
            bad = [p for p in result["points"] if not p["ok"]][:6]
            lines = "\n".join(f"• point {p['index'] + 1} {p['point']}: {p['errors'][0] if p['errors'] else ''}"
                              for p in bad)
            QMessageBox.warning(self, "Dry run", f"{n - ok} of {n} sweep points don't compile.\n\n{lines}")
            self.ctl.set_preview_index(bad[0]["index"])
            self.dock.setCurrentWidget(self.problems)

    # ================================================================== run on the RFSoC
    def run_blockers(self) -> list:
        """Why Run is off right now; empty when it can run."""
        from ..runner.script import hardware_ready
        if self._run is not None:
            return ["a run is in progress"]
        reasons = [] if self.simulating else list(hardware_ready(self.ctl.station))
        if any(p.level == "error" for p in self.ctl.problems):
            reasons.append("the sequence has errors (see Problems)")
        if self.ctl.seq.measure is None:
            reasons.append("the sequence has no Measure block")
        return reasons

    @property
    def simulating(self) -> bool:
        return self.topbar.sim_btn.isChecked()

    def _update_run_button(self):
        btn = self.topbar.run_btn
        reasons = self.run_blockers()
        btn.setEnabled(not reasons)
        if self._run is None:
            btn.setText(" Run simulated" if self.simulating else " Run")
        if self._run is not None:
            btn.setToolTip("Running. Stop it from the Data tab.")
        elif reasons:
            btn.setToolTip("Run is off:\n• " + "\n• ".join(reasons) +
                           ("" if self.simulating else "\n\nSimulate runs the sequence on a simulated board."))
        elif self.simulating:
            btn.setToolTip("Run on the simulated board: no RFSoC, made-up data in the real format. "
                           "Saved under _simulated/ and drawn in the Data tab.")
        else:
            btn.setToolTip("Run on the RFSoC. Each point is saved as it is measured and drawn in the Data tab.")

    def run(self):
        """Start the sequence on the RFSoC in the background; results stream into the Data tab."""
        from ..runner.save import run_folder_for
        from .run_worker import RunWorker
        if self.run_blockers():
            self._update_run_button()
            return
        self.ctl.refresh_now()
        if any(p.level == "error" for p in self.ctl.problems):
            self._update_run_button()
            return
        sim = self.simulating
        if sim:
            from ..runner.simulate import SimulatedProgram, simulated_connect
            connect, program_class = simulated_connect, SimulatedProgram
        else:
            connect, program_class = self.connect_rfsoc, self.program_class
        rec = self.data_panel.start_run(self.ctl.seq, simulated=sim)
        worker = RunWorker(self.ctl.seq, self.ctl.station, self.ctl.calib,
                           run_folder_for(self.ctl.seq, self.ctl.station, simulated=sim), connect, program_class,
                           simulated=sim)
        worker.board_checked.connect(self._board_checked)
        # bound methods of this widget, so the slots run on the GUI thread (queued from the worker)
        worker.started_run.connect(self._run_started)
        worker.point.connect(self._run_point)
        worker.finished_run.connect(self._run_finished)
        self._run = (worker, rec)
        self.topbar.sim_btn.setEnabled(False)
        self.topbar.run_btn.setText(" Running…")
        self._update_run_button()
        self.dock.setCurrentWidget(self.data_panel)
        worker.start()

    def stop_run(self):
        if self._run is not None:
            self._run[0].stop()

    def _run_started(self, path: str):
        if self._run is not None:
            self.data_panel.run_started(self._run[1], path)

    def _board_checked(self, check: str):
        if self._run is not None and check.startswith("DIFFERS"):
            self.data_panel.set_note(self._run[1], "board config " + check.split(" (")[0].lower())
            self.status_message.emit(f"Board config {check}")

    def _run_point(self, k: int, point):
        if self._run is not None:
            self.data_panel.add_point(self._run[1], k, point)

    def _run_finished(self, status: str, path: str):
        if self._run is None:
            return
        worker, rec = self._run
        self.data_panel.finish_run(rec, status, path)
        self._run = None
        if worker is not None:
            worker.wait(2000)
        self.topbar.sim_btn.setEnabled(True)
        self._update_run_button()
        self.status_message.emit(f"Run {status}" + (f": {path}" if path else ""))

    def shutdown(self, timeout_ms: int = 30000) -> None:
        """Stop a run in progress and wait for its file to be closed (the window is closing)."""
        if self._run is not None:
            worker = self._run[0]
            worker.stop()
            worker.wait(timeout_ms)

