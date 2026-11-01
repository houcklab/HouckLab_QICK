"""The dark top bar, styled like Desq's menu bar: file actions, undo, station and
calibration pickers, a status pill, Dry run and Run."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ..config.station import Station
from . import icons, style
from .widgets import Dropdown, ElidedLabel


def _icon_button(name, tip):
    b = QPushButton()
    b.setObjectName("icon_button")
    b.setIcon(icons.icon(name, "#FFFFFF", 16))
    b.setIconSize(QSize(16, 16))
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b


class EditableTitle(QWidget):
    """The sequence name in the top bar. Click it to rename: Enter or clicking away applies,
    Esc cancels. Emits ``renamed(new name)``; the caller applies it (as an undoable edit)."""
    renamed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = ElidedLabel("Untitled")
        self.label.setObjectName("doc_title")
        self.label.setCursor(Qt.IBeamCursor)
        self.edit = QLineEdit()
        self.edit.setObjectName("title_edit")
        self.edit.setMaximumWidth(360)
        self.edit.hide()
        self.edit.returnPressed.connect(self._finish)
        self.edit.editingFinished.connect(self._finish)
        self.edit.installEventFilter(self)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.edit)
        lay.addStretch(0)
        self.name = "Untitled"

    def set_title(self, name: str, display: str) -> None:
        """``name`` is what editing starts from; ``display`` adds the file name and unsaved dot."""
        self.name = name
        self.label.setText(display)
        self.label.setToolTip(f"{display}\nClick to rename")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.label.isVisible():
            self.start_editing()

    def start_editing(self) -> None:
        self.edit.setText(self.name)
        self.label.hide()
        self.edit.show()
        self.edit.setFocus()
        self.edit.selectAll()

    def _finish(self) -> None:
        if not self.edit.isVisible():
            return
        text = self.edit.text().strip()
        self._close()
        if text and text != self.name:
            self.renamed.emit(text)

    def _close(self) -> None:
        self.edit.hide()
        self.label.show()

    def eventFilter(self, obj, e):
        if obj is self.edit and e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
            self._close()                       # cancel: hide before editingFinished can apply it
            return True
        return super().eventFilter(obj, e)


def _sep():
    f = QFrame()
    f.setFixedSize(1, 22)
    f.setStyleSheet("background: #4A4A50;")
    return f


class TopBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topbar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(52)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 12, 6)
        lay.setSpacing(6)

        brand = QVBoxLayout()
        brand.setSpacing(0)
        t = QLabel("Bob")
        t.setObjectName("app_title")
        st = QLabel("the experiment builder")
        st.setObjectName("app_subtitle")
        brand.addWidget(t)
        brand.addWidget(st)
        lay.addLayout(brand)
        lay.addSpacing(10)
        lay.addWidget(_sep())
        lay.addSpacing(4)

        self.new_btn = _icon_button("new", f"New sequence ({style.shortcut_text('Ctrl+N')})")
        self.open_btn = _icon_button("open", f"Open sequence ({style.shortcut_text('Ctrl+O')})")
        self.save_btn = _icon_button("save", f"Save ({style.shortcut_text('Ctrl+S')})")
        self.export_btn = _icon_button("export", f"Export as a Python script ({style.shortcut_text('Ctrl+E')})")
        self.undo_btn = _icon_button("undo", f"Undo ({style.shortcut_text('Ctrl+Z')})")
        self.redo_btn = _icon_button("redo", f"Redo ({style.shortcut_text('Ctrl+Shift+Z')})")
        for b in (self.new_btn, self.open_btn, self.save_btn, self.export_btn):
            lay.addWidget(b)
        lay.addWidget(_sep())
        for b in (self.undo_btn, self.redo_btn):
            lay.addWidget(b)
        lay.addSpacing(8)
        self.title = EditableTitle()
        self.doc_title = self.title.label
        lay.addWidget(self.title, 1)

        st_lab = QLabel("Station")
        st_lab.setObjectName("app_subtitle")
        lay.addWidget(st_lab)
        self.station = Dropdown()
        self.station.addItems(Station.available() or ["8QV1"])
        self.station.setToolTip("Station: channels, mixers, LOs and timing for this setup")
        lay.addWidget(self.station)
        self.calib_btn = QPushButton("Calibration")
        self.calib_btn.setIcon(icons.icon("database", "#FFFFFF", 15))
        self.calib_btn.setToolTip("Choose qubit_parameters.json")
        self.calib_btn.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.calib_btn)
        lay.addSpacing(4)
        self.status = QLabel("Ready")
        self.status.setObjectName("status_pill")
        self.status.setCursor(Qt.PointingHandCursor)
        self.status.setFixedHeight(22)
        lay.addWidget(self.status)
        lay.addSpacing(4)
        lay.addWidget(_sep())
        self.dry_btn = QPushButton(" Dry run")
        self.dry_btn.setObjectName("dry_run_button")
        self.dry_btn.setIcon(icons.icon("eye", "#FFFFFF", 15))
        self.dry_btn.setToolTip("Compile every sweep point without hardware")
        self.dry_btn.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.dry_btn)
        self.sim_btn = QPushButton("Simulate")
        self.sim_btn.setObjectName("simulate_button")
        self.sim_btn.setCheckable(True)
        self.sim_btn.setCursor(Qt.PointingHandCursor)
        self.sim_btn.setToolTip("Run on a simulated board instead of the RFSoC: made-up data in the real format, "
                                "to check saving and plots. Saved under _simulated/ and labelled simulated.")
        lay.addWidget(self.sim_btn)
        self.run_btn = QPushButton(" Run")
        self.run_btn.setObjectName("run_button")
        self.run_btn.setIcon(icons.icon("play", "#FFFFFF", 14))
        self.run_btn.setEnabled(False)                # BobWidget enables it once the station is verified
        self.run_btn.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.run_btn)

    def set_status(self, errors: int, warnings: int):
        if errors:
            text, bg, fg = f"{errors} error{'s' if errors != 1 else ''}", "#CD5C5C", "#FFFFFF"
        elif warnings:
            text, bg, fg = f"{warnings} warning{'s' if warnings != 1 else ''}", "#E0A24A", "#2B2B2F"
        else:
            text, bg, fg = "Ready", "#3CB371", "#FFFFFF"
        self.status.setText(text)
        self.status.setStyleSheet(f"background: {bg}; color: {fg};")
        self.status.setToolTip("Open the Problems tab" if errors or warnings else "Resolves and compiles")

    def set_calibration_label(self, path, ok: bool):
        name = Path(path).name if path else "No calibration"
        self.calib_btn.setText(f" {name}")
        self.calib_btn.setToolTip(str(path) if path else "Choose qubit_parameters.json")
        self.calib_btn.setStyleSheet("" if ok else "background: #8A3B3B;")
