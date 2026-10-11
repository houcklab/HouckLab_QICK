"""Small Qt primitives for the viewer.

``MplCanvas`` is a deliberate copy of the one in ``calibration_gui.widgets``: that
package's import chain reaches build_config -> MUXInitialize -> qick, and the viewer
must open on a machine with no qick and no hardware. Twelve lines of duplication buys
that independence.
"""
from __future__ import annotations

from typing import Optional

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel


class MplCanvas(FigureCanvas):
    """Embeddable matplotlib figure with a single axis."""

    def __init__(self, parent=None, height=4.0, layout="tight"):
        self.layout = layout        # "constrained" makes room for colorbars/suptitles
        self.fig = Figure(figsize=(7.0, height), layout=layout)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)

    def reset(self):
        self.fig.clf()
        self.fig.set_layout_engine(self.layout)
        self.ax = self.fig.add_subplot(111)
        self.draw()


class PixmapLabel(QLabel):
    """QLabel that keeps its pixmap scaled to the widget, preserving aspect."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(1, 1)     # else the pixmap's size hint blocks shrinking

    def set_image(self, pix: Optional[QPixmap], message: str = "") -> None:
        self._pix = pix
        if pix is None:
            self.clear()
            self.setText(message)
        else:
            self._rescale()

    def _rescale(self) -> None:
        if self._pix is not None:
            self.setPixmap(self._pix.scaled(self.size(), Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()


def human_bytes(n: float) -> str:
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024.0
    return f"{n} B"
