"""Viewer main window and entry point.

Standalone: no connection dialog, no soc/soccfg, no CalibState, nothing imported from
calibration_gui. Opening the viewer never touches the RFSoC.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Qt5Agg")

from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QApplication, QMainWindow, QShortcut, QStatusBar

from .browser import SETTINGS_APP, SETTINGS_ORG, BrowserWidget
from . import data_index as dx
from . import style as st


class ViewerWindow(QMainWindow):
    """Window around the browser widget; the status bar mirrors indexing progress."""

    def __init__(self, db_path=None, auto_index: bool = True):
        super().__init__()
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        st.apply_style(QApplication.instance(),
                       self.settings.value(st.SETTING_ZOOM, st.ZOOM_DEFAULT, type=float))
        self.setWindowTitle("Measurement Data Viewer")
        self.resize(1500, 850)
        self.browser = BrowserWidget(db_path=db_path, auto_index=auto_index)
        self.setCentralWidget(self.browser)
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.browser.status_message.connect(lambda m: self.status.showMessage(m))
        self.status.showMessage(f"Data root: {dx.DATA_ROOT}   |   cache: {dx.DEFAULT_DB_PATH}")
        step = st.ZOOM_STEP
        for keys, action in ((("Ctrl+=", "Ctrl++"), lambda: self.set_zoom(st.current_scale() + step)),
                             (("Ctrl+-",), lambda: self.set_zoom(st.current_scale() - step)),
                             (("Ctrl+0",), lambda: self.set_zoom(st.ZOOM_DEFAULT))):
            for key in keys:
                QShortcut(QKeySequence(key), self, activated=action)

    def set_zoom(self, scale: float) -> float:
        """Re-apply the style at ``scale`` (clamped to 0.8-2.0) and remember it."""
        scale = st.apply_style(QApplication.instance(), scale)
        self.settings.setValue(st.SETTING_ZOOM, scale)
        self.browser.restyle()
        self.status.showMessage(f"zoom {scale:.1f}x  (Ctrl+= / Ctrl+- / Ctrl+0)", 3000)
        return scale

    def closeEvent(self, event):
        self.browser._stop_worker()
        super().closeEvent(event)


# view.png (512 px, transparent) is what Qt scales for the window and taskbar; view.ico is a
# single 32 px size, meant for a desktop shortcut's own icon, so it is not used here.
ICON_PATH = Path(__file__).with_name("view.png")
APP_ID = "HouckLab.ViewerGUI"


def _apply_app_identity(app) -> None:
    """Window/taskbar icon for every window and dialog of this app.

    Windows groups pythonw.exe windows under Python's own identity and icon unless the
    process sets an AppUserModelID, so set one (before any window is shown).
    """
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass                                  # not Windows
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))


def main() -> None:
    # pythonw.exe / detached-console launches leave sys.stdout/stderr == None.
    import os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    app = QApplication(sys.argv)              # styled by ViewerWindow (style.py)
    _apply_app_identity(app)
    win = ViewerWindow()
    win.show()
    sys.exit(app.exec_())
