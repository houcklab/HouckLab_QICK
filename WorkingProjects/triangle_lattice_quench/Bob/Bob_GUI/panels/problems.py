"""Problems: everything the resolver and validator found. Click a row to select its block."""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from .. import icons

ICON = {"error": ("error", "#CD5C5C"), "warning": ("alert", "#D9902F"), "info": ("info", "#6495ED")}


class ProblemsPanel(QWidget):
    count_changed = pyqtSignal(int, int, int)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        lay.addWidget(self.summary)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "Problem", "Block"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tree.header().resizeSection(0, 28)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.setWordWrap(True)
        self.tree.itemDoubleClicked.connect(self._jump)
        self.tree.itemClicked.connect(self._jump)
        lay.addWidget(self.tree, 1)
        controller.refreshed.connect(self.refresh)

    def refresh(self):
        self.tree.clear()
        order = {"error": 0, "warning": 1, "info": 2}
        probs = sorted(self.ctl.problems, key=lambda p: order.get(p.level, 3))
        for p in probs:
            name, color = ICON.get(p.level, ICON["info"])
            it = QTreeWidgetItem(["", p.message, (p.block_name or "") + (f" · {p.field}" if p.field else "")])
            it.setIcon(0, icons.icon(name, color, 15))
            it.setToolTip(1, p.message)
            it.setData(0, Qt.UserRole, p.block_id)
            self.tree.addTopLevelItem(it)
        n = {lvl: sum(1 for p in probs if p.level == lvl) for lvl in order}
        if not probs:
            self.summary.setText("No problems. The sequence resolves and compiles.")
        else:
            word = {"error": "error", "warning": "warning", "info": "note"}
            parts = [f"{n[k]} {word[k]}{'s' if n[k] != 1 else ''}" for k in ("error", "warning", "info") if n[k]]
            self.summary.setText(", ".join(parts) + " at the previewed sweep point.")
        self.count_changed.emit(n["error"], n["warning"], n["info"])

    def _jump(self, it, _col=0):
        bid = it.data(0, Qt.UserRole)
        if bid:
            self.ctl.select(bid)
