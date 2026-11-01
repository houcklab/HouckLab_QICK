"""Resolved: every number Bob will use at the previewed sweep point, block by block,
with where each came from. This is what the snapshot records for every run."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from .inspector import _fmt_value


class ResolvedPanel(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        info = QLabel("Every value at the previewed sweep point and its source. The same record is saved with "
                      "each run.")
        info.setObjectName("muted")
        lay.addWidget(info)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Field", "Value", "Source"])
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Interactive)
        self.tree.header().resizeSection(2, 300)
        lay.addWidget(self.tree, 1)
        controller.refreshed.connect(self.refresh)
        self._expanded = set()

    def refresh(self):
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            key = it.data(0, Qt.UserRole)
            if it.isExpanded():
                self._expanded.add(key)
            else:
                self._expanded.discard(key)
        self.tree.clear()
        res = self.ctl.resolved
        if res is None:
            return
        groups = [("segment", r) for r in res.segments] + [("pulse", r) for r in res.pulses]
        if res.measure:
            groups.append(("measure", res.measure))
        for kind, r in groups:
            b = r.block
            top = QTreeWidgetItem([b.name, b.LABEL, ""])
            top.setData(0, Qt.UserRole, b.id)
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            for spec in b.FIELDS:
                src = b.fields.get(spec.name)
                QTreeWidgetItem(top, [spec.label, _fmt_value(r.params.get(spec.name), spec.unit),
                                      src.describe() if src is not None else ""])
            if kind == "measure" and r.readout:
                ro = QTreeWidgetItem(top, ["Readout settings", "", f"drive_groups/{r.params.get('readout_group')}"])
                for k, v in r.readout.items():
                    QTreeWidgetItem(ro, [k, _fmt_value(v), ""])
            self.tree.addTopLevelItem(top)
            top.setExpanded(b.id in self._expanded or b.id == self.ctl.selected)
        cp = self.ctl.compiled
        if cp is not None:
            top = QTreeWidgetItem(["Compiled program", f"{cp.n_samples} samples per channel "
                                                       f"({cp.body_us:.3g} µs)", "TLQ backend"])
            top.setData(0, Qt.UserRole, "__compiled__")
            for k, v in cp.qick_cfg.items():
                if k == "bob":
                    continue
                QTreeWidgetItem(top, [k, _fmt_value(v), "station" if k in self.ctl.station.data else ""])
            QTreeWidgetItem(top, ["IIR compensation", "applied" if cp.compensated else "not applied", ""])
            QTreeWidgetItem(top, ["drives", str(len(cp.drives)), "scheduled on 16-sample cycles"])
            self.tree.addTopLevelItem(top)
            top.setExpanded("__compiled__" in self._expanded)
