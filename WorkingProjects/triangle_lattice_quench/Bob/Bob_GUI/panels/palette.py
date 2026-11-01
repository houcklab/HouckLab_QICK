"""Left panel: blocks and presets to drag onto the canvas, and templates to open."""
from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import QMimeData, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (QAbstractItemView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QStyle,
                             QStyledItemDelegate, QVBoxLayout, QWidget)

from ...blocks.registry import all_block_classes
from ...core.sequence import Sequence
from .. import style
from ..canvas.canvas import MIME_NEW, MIME_PRESET

LIB = Path(__file__).resolve().parents[2] / "library"
ROLE_KIND, ROLE_PAYLOAD, ROLE_TITLE, ROLE_DESC, ROLE_ACT = range(Qt.UserRole, Qt.UserRole + 5)
GROUPS = [("Preparation", "prep"), ("Dynamics", "dynamics"), ("Readout", "readout"), ("Pulses", "pulse")]


class _Card(QStyledItemDelegate):
    """Paints palette items: section headers, and cards with a family color stripe, title and description."""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel

    def sizeHint(self, option, index):
        if index.data(ROLE_KIND) == "header":
            return QSize(10, 30)
        return QSize(10, 54)

    def paint(self, p: QPainter, option, index):
        kind = index.data(ROLE_KIND)
        c, cv = style.COLORS, style.CANVAS
        r = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if kind == "header":
            f = QFont(option.font)
            f.setPixelSize(11)
            f.setWeight(QFont.DemiBold)
            f.setCapitalization(QFont.AllUppercase)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
            p.setFont(f)
            p.setPen(QColor(c["text_muted"]))
            p.drawText(r.adjusted(10, 8, -6, 0), Qt.AlignLeft | Qt.AlignVCenter, index.data(ROLE_TITLE))
            p.restore()
            return
        card = r.adjusted(6, 3, -6, -3)
        path = QPainterPath()
        path.addRoundedRect(card, 6, 6)
        hover = option.state & QStyle.State_MouseOver
        sel = option.state & QStyle.State_Selected
        p.fillPath(path, QColor(c["bg_accent"] if (hover or sel) else c["bg"]))
        p.setPen(QPen(QColor(c["tab_accent"] if sel else (c["button_hover_border"] if hover else c["border_dark"])), 1))
        p.drawPath(path)
        act = index.data(ROLE_ACT)
        bar = QColor(cv["pulse"]["PiPulse"]) if act == "pulse" else QColor(cv["act_text"].get(act, cv["muted"]))
        if kind == "template":
            bar = QColor(c["connect"])
        p.fillRect(QRectF(card.x(), card.y() + 8, 3, card.height() - 16), bar)
        f = QFont(option.font)
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(c["text"]))
        p.drawText(QRectF(card.x() + 12, card.y() + 5, card.width() - 18, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   index.data(ROLE_TITLE))
        f2 = QFont(option.font)
        f2.setPixelSize(11)
        p.setFont(f2)
        p.setPen(QColor(c["text_muted"]))
        desc = QFontMetrics(f2).elidedText(index.data(ROLE_DESC) or "", Qt.ElideRight, int(card.width() - 20))
        p.drawText(QRectF(card.x() + 12, card.y() + 24, card.width() - 18, 18), Qt.AlignLeft | Qt.AlignVCenter, desc)
        p.restore()


class _List(QListWidget):
    """The palette list; dragging an item carries Bob's MIME data to the canvas."""

    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.setObjectName("palette")
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setItemDelegate(_Card(panel))
        self.setSpacing(0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setResizeMode(QListWidget.Adjust)

    def mimeData(self, items):
        it = items[0]
        m = QMimeData()
        kind = it.data(ROLE_KIND)
        if kind == "block":
            m.setData(MIME_NEW, it.data(ROLE_PAYLOAD).encode())
        elif kind == "preset":
            m.setData(MIME_PRESET, json.dumps(it.data(ROLE_PAYLOAD)).encode())
        return m

    def mimeTypes(self):
        return [MIME_NEW, MIME_PRESET]


class PalettePanel(QWidget):
    open_template = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 4, 8)
        lay.setSpacing(6)
        title = QLabel("Blocks")
        title.setObjectName("section_title")
        lay.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter blocks, presets, templates")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = _List(self)
        lay.addWidget(self.list, 1)
        hint = QLabel("Drag a block onto the canvas. Double-click a template to open it.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.list.itemDoubleClicked.connect(self._double)
        self.reload()

    def _add(self, kind, title, desc="", payload=None, act=None):
        it = QListWidgetItem()
        it.setData(ROLE_KIND, kind)
        it.setData(ROLE_TITLE, title)
        it.setData(ROLE_DESC, desc)
        it.setData(ROLE_PAYLOAD, payload)
        it.setData(ROLE_ACT, act)
        it.setToolTip(desc)
        if kind == "header":
            it.setFlags(Qt.NoItemFlags)
        elif kind == "template":
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        else:
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
        self.list.addItem(it)

    def reload(self):
        self.list.clear()
        classes = all_block_classes()
        for group, act in GROUPS:
            members = [c for c in classes if (c.KIND == "pulse" and act == "pulse")
                       or (c.KIND != "pulse" and c.FAMILY == group)]
            if not members:
                continue
            self._add("header", group)
            for c in members:
                self._add("block", c.LABEL, c.DESCRIPTION, c.TYPE, act if act != "pulse" else "pulse")
        presets = sorted((LIB / "presets").glob("*.json"))
        if presets:
            self._add("header", "Presets")
            for p in presets:
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                    b0 = d["blocks"][0]
                    from ...blocks.registry import block_class
                    cls = block_class(b0["type"])
                    act = "pulse" if cls.KIND == "pulse" else b0.get("act", cls.DEFAULT_ACT)
                    self._add("preset", d.get("name", p.stem), f"Preset · {cls.LABEL}", d, act)
                except Exception:
                    continue
        templates = sorted((LIB / "templates").glob("*.json"))
        if templates:
            self._add("header", "Templates")
            for t in templates:
                try:
                    s = Sequence.load(t)
                    self._add("template", s.name, s.description, str(t), "template")
                except Exception:
                    continue
        self._filter(self.search.text())

    def _filter(self, text):
        text = text.strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(ROLE_KIND) == "header":
                it.setHidden(bool(text))
            else:
                hay = f"{it.data(ROLE_TITLE)} {it.data(ROLE_DESC)}".lower()
                it.setHidden(bool(text) and text not in hay)

    def _double(self, it):
        if it.data(ROLE_KIND) == "template":
            self.open_template.emit(it.data(ROLE_PAYLOAD))
