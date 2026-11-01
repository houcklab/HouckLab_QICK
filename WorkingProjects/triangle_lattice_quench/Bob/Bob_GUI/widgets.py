"""Small shared widgets."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QStyledItemDelegate,
                             QToolTip, QWidget)

from . import icons


class InfoIcon(QLabel):
    """A small (i) that shows its help text as soon as the pointer is over it."""

    def __init__(self, text: str, parent=None, size: int = 13):
        super().__init__(parent)
        self.text_ = text
        self.setPixmap(icons.pixmap("info", "#8A8A90", size))
        self.setFixedSize(size + 4, size + 4)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.WhatsThisCursor)
        self.setToolTip(text)

    def enterEvent(self, e):
        QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), self.text_, self)
        super().enterEvent(e)

    def leaveEvent(self, e):
        QToolTip.hideText()
        super().leaveEvent(e)


def label_with_info(text: str, info: str, object_name: str = "field_label") -> QWidget:
    """A right-aligned label followed by an (i) icon, for QFormLayout label columns."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(4)
    lab = QLabel(text)
    lab.setObjectName(object_name)
    h.addStretch(1)
    h.addWidget(lab)
    if info:
        h.addWidget(InfoIcon(info))
    return w


class ElidedLabel(QLabel):
    """A one-line label that ends in "…" when space is short, instead of widening the window.
    The full text stays available as its tooltip."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        p.setFont(self.font())
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.contentsRect().width())
        p.drawText(self.contentsRect(), int(self.alignment() | Qt.AlignVCenter), text)


def scrollable(widget: QWidget) -> QScrollArea:
    """Wrap a panel so it scrolls when the window is small, instead of forcing the window's minimum size."""
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    return area


def restyle(w: QWidget) -> None:
    """Re-apply the stylesheet after changing a widget's objectName (e.g. to "bad")."""
    w.style().unpolish(w)
    w.style().polish(w)


class Dropdown(QComboBox):
    """A combo box that opens as a normal list below itself, showing up to 15 choices at once.

    Together with ``combobox-popup: 0`` in the stylesheet this replaces the macOS-style popup,
    which with a custom stylesheet shrinks to one row with scroll arrows. The standard item
    delegate lets the stylesheet set the row height.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(QStyledItemDelegate(self))
        self.setMaxVisibleItems(15)
