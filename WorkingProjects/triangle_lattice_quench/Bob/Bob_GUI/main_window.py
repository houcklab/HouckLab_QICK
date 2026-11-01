"""Standalone window around BobWidget."""
from __future__ import annotations

from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QStatusBar

from . import style
from .app_settings import app_settings
from .bob_widget import BobWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bob = BobWidget()
        self.setCentralWidget(self.bob)
        bar = QStatusBar()
        bar.setSizeGripEnabled(False)
        bar.setFixedHeight(18)                    # a thin strip for short messages ("Saved …")
        self.setStatusBar(bar)
        self.bob.status_message.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self.bob.title_changed.connect(self.setWindowTitle)
        self.setWindowTitle("Bob")
        self.resize(1480, 920)
        geo = app_settings().value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.fit_to_screen()
        style.apply_app_look(QApplication.instance())   # Bob owns this window: same look on every OS
        self.bob.apply_style()

    def fit_to_screen(self):
        """Shrink and move the window so all of it is on the screen it opens on."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        frame = self.frameGeometry().size() - self.geometry().size()   # title bar and borders
        w = min(self.width(), avail.width() - frame.width())
        h = min(self.height(), avail.height() - frame.height())
        self.resize(max(w, self.minimumSizeHint().width()), max(h, self.minimumSizeHint().height()))
        x = min(max(self.x(), avail.left()), avail.right() - self.frameGeometry().width() + 1)
        y = min(max(self.y(), avail.top()), avail.bottom() - self.frameGeometry().height() + 1)
        self.move(max(x, avail.left()), max(y, avail.top()))

    def save_preset(self, block_id):
        self.bob.save_preset(block_id)

    def closeEvent(self, e):
        if self.bob._run is not None:
            r = QMessageBox.question(self, "Run in progress", "A run is in progress. Stop it after the current "
                                     "point, save it, and close?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                e.ignore()
                return
        try:
            ok = self.bob._confirm_discard()
        except Exception:
            ok = False                     # never close with unsaved work because something went wrong
        if not ok:
            e.ignore()
            return
        self.bob.shutdown()                    # a run in progress stops after its current point and saves
        app_settings().setValue("geometry", self.saveGeometry())
        e.accept()
