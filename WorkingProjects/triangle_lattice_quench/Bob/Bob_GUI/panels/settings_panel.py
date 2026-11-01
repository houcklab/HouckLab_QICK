"""Experiment: name, description, reps and relax delay, where runs are saved, the sweep axes fields can
use, and the plain-language summary of the sequence."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                             QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...config.settings import ExperimentSettings
from ...core.sequence import sweep_users_text
from .. import icons, style
from ..widgets import ElidedLabel, InfoIcon, label_with_info, restyle as _restyle


class SettingsPanel(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self._loading = False
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(18)
        left = QFormLayout()
        left.setLabelAlignment(Qt.AlignRight)
        self.name = QLineEdit()
        self.desc = QLineEdit()
        self.reps = QSpinBox()
        self.reps.setRange(1, 10_000_000)
        self.reps.setSingleStep(100)
        self.rounds = QSpinBox()
        self.rounds.setRange(1, 100000)
        self.relax = QLineEdit()
        self.save_folder = QLineEdit()
        self.save_folder.setObjectName("save_folder")
        self.save_folder.editingFinished.connect(self._commit_save_folder)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_save_folder)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(4)
        folder_row.addWidget(self.save_folder, 1)
        folder_row.addWidget(browse)
        self.save_hint = QLabel()
        self.save_hint.setObjectName("muted")
        self.save_hint.setWordWrap(True)
        self.save_hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.name.editingFinished.connect(self._rename)     # same undoable rename as the top-bar title
        # each field saves on its own, so a bad entry in one never blocks or drops the others
        self.desc.editingFinished.connect(self._commit_description)
        self.reps.editingFinished.connect(self._commit_counts)
        self.rounds.editingFinished.connect(self._commit_counts)
        self.relax.editingFinished.connect(self._commit_relax)
        left.addRow("Name", self.name)
        left.addRow("Description", self.desc)
        left.addRow(label_with_info("Reps", "Shots averaged at each sweep point.", "plain"), self.reps)
        left.addRow(label_with_info("Rounds", "How many times the whole set of reps is repeated and averaged. "
                                    "Usually 1.", "plain"), self.rounds)
        left.addRow(label_with_info("Relax delay (µs)", "Wait after each shot so the qubits decay back to the "
                                    "ground state. Blank uses the station default.", "plain"), self.relax)
        left.addRow(label_with_info("Save folder", "Where this sequence's runs are saved. Blank uses the station's "
                                    "outer_folder. Each run is written as it is measured, so a crash or Stop keeps "
                                    "what was measured.", "plain"), folder_row)
        left.addRow("", self.save_hint)
        lw = QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(420)
        outer.addWidget(lw)
        right = QVBoxLayout()
        head = QHBoxLayout()
        t = QLabel("Sweep axes")
        t.setObjectName("field_label")
        head.addWidget(t)
        head.addWidget(InfoIcon("A sweep axis is a named list of values (start, stop, number of points). A field "
                                "follows it when its source is Sweep; set that in the inspector, where the "
                                "axis's range can also be edited. At each point the whole sequence runs Reps "
                                "times with the swept fields at that point's value. With several axes, every "
                                "combination runs and the first axis is the outermost loop. Renaming an axis "
                                "here keeps the fields that use it."))
        hint = ElidedLabel("Each point reruns the whole sequence. Outermost loop first.")
        hint.setObjectName("muted")
        head.addWidget(hint, 1)
        add = QPushButton("Add axis")
        add.setIcon(icons.icon("plus", "#6B6B6B", 14))
        add.clicked.connect(lambda: self.ctl.add_sweep_axis("axis", 0.0, 1.0, 11, ""))
        rm = QPushButton("Remove")
        rm.clicked.connect(self._remove)
        head.addWidget(add)
        head.addWidget(rm)
        right.addLayout(head)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Axis", "Start", "Stop", "Points", "Unit", "Swept fields"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._commit_cell)
        self.table.setMaximumHeight(120)
        right.addWidget(self.table)
        self.total = QLabel()
        self.total.setObjectName("muted")
        right.addWidget(self.total)
        self.error = QLabel()                         # why the last entry was not accepted
        self.error.setObjectName("field_error")
        self.error.setWordWrap(True)
        self.error.hide()
        right.addWidget(self.error)
        sh = QHBoxLayout()
        st = QLabel("Summary")
        st.setObjectName("field_label")
        sh.addWidget(st)
        sh.addWidget(InfoIcon("Bob's plain-language description of the sequence, in play order. It is written into "
                              "the sequence file as \"summary\" every time you save (values at the first sweep "
                              "point), so the file explains itself without opening Bob."))
        sh.addStretch(1)
        right.addSpacing(6)
        right.addLayout(sh)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        right.addWidget(self.summary, 1)
        outer.addLayout(right, 1)
        controller.changed.connect(self.load)
        controller.refreshed.connect(self._update_summary)
        self.load()

    def _update_summary(self):
        from ...config.summary import summarize
        try:
            text = summarize(self.ctl.seq, self.ctl.resolved, self.ctl.station.n_channels)
        except Exception as exc:
            text = f"(summary unavailable: {exc})"
        self.summary.setText(text)

    def load(self, force: bool = False):
        if not force and any(w.hasFocus() for w in (self.name, self.desc, self.relax, self.reps, self.rounds,
                                                     self.save_folder)):
            return
        self._loading = True
        s = self.ctl.seq
        self.name.setText(s.name)
        self.desc.setText(s.description)
        self.reps.setValue(int(s.settings.reps))
        self.rounds.setValue(int(s.settings.rounds))
        self.relax.setText("" if s.settings.relax_delay_us is None else f"{s.settings.relax_delay_us:g}")
        self.relax.setPlaceholderText(f"station default {self.ctl.station.data.get('relax_delay', 200)}")
        self.save_folder.setText(s.settings.save_folder)
        self.save_folder.setPlaceholderText(f"station default: {self.ctl.station.data.get('outer_folder', '')}")
        self._update_save_hint()
        self.table.setRowCount(len(s.settings.sweeps))
        users = s.sweep_users()
        for r, a in enumerate(s.settings.sweeps):
            for cidx, v in enumerate([a.name, f"{a.start:g}", f"{a.stop:g}", str(a.points), a.unit]):
                self.table.setItem(r, cidx, QTableWidgetItem(v))
            used = users.get(a.name, [])
            item = QTableWidgetItem(sweep_users_text(used) if used else "none yet")
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)        # read only: set in the inspector
            item.setToolTip(sweep_users_text(used) if used else
                            "No field follows this axis yet. Select a block and set a field's source to Sweep.")
            if not used:
                item.setForeground(QColor(style.COLORS["text_muted"]))
            self.table.setItem(r, 5, item)
        self.total.setText(self._total_text(s.settings))
        self._loading = False

    @staticmethod
    def _total_text(st: ExperimentSettings) -> str:
        reps = f"{st.reps} rep{'s' if st.reps != 1 else ''}"
        if not st.sweeps:
            return f"No sweep: the sequence runs once, {reps}."
        if len(st.sweeps) == 1:
            return f"{st.n_points():,} points, each run {reps}."
        grid = " × ".join(str(a.points) for a in st.sweeps)
        return f"{grid} = {st.n_points():,} points (every combination), each run {reps}."

    # ---------------------------------------------------------------- commits
    def _settings_copy(self) -> ExperimentSettings:
        return ExperimentSettings.from_dict(self.ctl.seq.settings.to_dict())

    def _show_error(self, text: str = "") -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def _commit(self):
        """Save every simple field (description, reps, rounds, relax delay)."""
        self._commit_description()
        self._commit_counts()
        self._commit_relax()

    def _commit_description(self):
        if not self._loading and self.desc.text() != self.ctl.seq.description:
            self.ctl.set_settings(self._settings_copy(), description=self.desc.text())

    def _commit_counts(self):
        if self._loading:
            return
        new = self._settings_copy()
        new.reps, new.rounds = self.reps.value(), self.rounds.value()
        self.ctl.set_settings(new)

    def _commit_relax(self):
        if self._loading:
            return
        text = self.relax.text().strip()
        try:
            value = float(text) if text else None
            if value is not None and value < 0:
                raise ValueError
        except ValueError:
            self.relax.setObjectName("bad")
            _restyle(self.relax)
            self._show_error(f"Relax delay: {text!r} is not a number of µs. Not applied; blank uses the "
                             "station default.")
            return
        self.relax.setObjectName("")
        _restyle(self.relax)
        self._show_error()
        new = self._settings_copy()
        new.relax_delay_us = value
        self.ctl.set_settings(new)

    def _commit_cell(self, item):
        """One edited sweep-axis cell. A bad entry is explained and the cell reverts."""
        if self._loading:
            return
        r, c = item.row(), item.column()
        new = self._settings_copy()
        if r >= len(new.sweeps) or c > 4:
            return
        axis, text = new.sweeps[r], item.text().strip()
        column = ["Axis", "Start", "Stop", "Points", "Unit"][c]
        try:
            if c == 0:
                if not text:
                    raise ValueError("an axis needs a name")
                if any(a.name == text for k, a in enumerate(new.sweeps) if k != r):
                    raise ValueError(f"another axis is already called {text!r}")
                rename = {axis.name: text} if text != axis.name else None
                axis.name = text
            else:
                rename = None
                if c in (1, 2):
                    setattr(axis, "start" if c == 1 else "stop", float(text))
                elif c == 3:
                    points = int(float(text))
                    if points < 1:
                        raise ValueError("needs at least 1 point")
                    axis.points = points
                else:
                    axis.unit = text
        except ValueError as exc:
            msg = str(exc) if c in (0, 3) and "could not convert" not in str(exc) else f"{text!r} is not a number"
            self._show_error(f"Sweep axis {r + 1}, {column}: {msg}. Not applied.")
            self.load(force=True)
            return
        self._show_error()
        self.ctl.set_settings(new, rename_axes=rename)

    def _commit_save_folder(self):
        if self._loading:
            return
        text = self.save_folder.text().strip()
        if text != self.ctl.seq.settings.save_folder:
            new = self._settings_copy()
            new.save_folder = text
            self.ctl.set_settings(new)
        self._update_save_hint()

    def _browse_save_folder(self):
        start = self.save_folder.text().strip() or self.ctl.station.data.get("outer_folder", "")
        folder = QFileDialog.getExistingDirectory(self, "Save runs in", start)
        if folder:
            self.save_folder.setText(folder)
            self._commit_save_folder()

    def _update_save_hint(self):
        from ...runner.save import data_folder, file_name, folder_problem
        name = file_name(self.ctl.seq)
        folder = data_folder(self.ctl.seq, self.ctl.station)
        problem = folder_problem(folder)
        self.save_hint.setObjectName("field_error" if problem else "muted")
        _restyle(self.save_hint)
        if problem:
            self.save_hint.setText(problem + ".")
            return
        sep = "\\" if "\\" in folder else "/"            # show Windows paths (Z:\...) with their own separator
        folder = folder.rstrip("/\\")
        self.save_hint.setText(f"Runs go to {folder}{sep}{name}{sep}{name}_<date>{sep}")

    def _rename(self):
        text = self.name.text().strip()
        if text:
            self.ctl.set_name(text)
        else:
            self.name.setText(self.ctl.seq.name)       # an empty name is not allowed; put the old one back

    def _remove(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.ctl.seq.settings.sweeps):
            return
        self._show_error(self.ctl.remove_sweep_axis(self.ctl.seq.settings.sweeps[r].name) or "")
