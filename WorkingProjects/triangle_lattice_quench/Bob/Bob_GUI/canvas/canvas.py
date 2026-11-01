"""The sequence canvas: time runs left to right in the three act bands, the flux track on
top, one lane per qubit below.

* Flux segments set the columns. Each lane draws that qubit's FF level through the
  segment (flat for holds, curved for ramps, stepped for the beamsplitter).
* Pulse chips sit in a segment's lane cell, laid out left to right in play order, since
  all drives share one generator and play one after another.
* When Preparation has pulses, a narrow column after it shows each qubit's prepared state.
* Measure is always the last column; its lane markers say what each read-out qubit reports.
* Chip badges: a dot when a field reads from calibration, a triangle when one is swept.
* Drag blocks in from the palette; drag chips to move them; Delete removes; Ctrl+C / Ctrl+V
  copy and paste; right-click for duplicate, delete, save as preset and move to another act.
* Hovering a chip, badge or marker shows its resolved values (text comes from describe.py).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PyQt5.QtCore import QMimeData, QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (QColor, QDrag, QFont, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen,
                         QPixmap, QPolygonF)
from PyQt5.QtWidgets import QMenu, QSizePolicy, QToolTip, QWidget

from ...blocks.registry import block_class
from ...config.summary import prepared_states, state_counts, state_string
from ...core.block import ACT_LABELS, ACTS
from ...core.params import Ref, Sweep, base_source
from .. import style
from . import describe

MIME_NEW = "application/x-bob-new-block"       # palette -> canvas: block TYPE
MIME_PRESET = "application/x-bob-preset"       # palette -> canvas: preset JSON
MIME_MOVE = "application/x-bob-move"           # canvas -> canvas: {"id", "kind"}

# Layout, in pixels. Rows from the top: act bands, flux track, one lane per qubit, time axis.
GUTTER = 64                                    # qubit labels on the left
MARGIN_R = 24
ACT_Y, ACT_H = 10, 24
FLUX_Y, FLUX_H = 40, 50
LANE_Y0, LANE_H = 100, 38
AXIS_H = 50
STATE_W = 36                                   # prepared-state column after Preparation
COL_W = 150
PLACEHOLDER_W = 132
MEASURE_W = 172
CHIP_W, CHIP_H = 30, 20
PULSE_SYMBOL = {"PiPulse": "π", "Pi2Pulse": "π/2", "Drive": "D"}
SHORT_ACT_LABELS = {"prep": "Prep", "dynamics": "Dynamics", "readout": "Readout"}


@dataclass
class Column:
    kind: str                      # segment | placeholder | state | measure
    act: str
    x: float
    w: float
    block_id: Optional[str] = None
    seg_index: int = -1            # index in seq.segments (segment columns)
    insert_index: int = 0          # where a segment dropped on a placeholder goes


@dataclass
class DropTarget:
    kind: str                      # gap | cell | measure | none
    index: int = 0
    act: str = "prep"
    segment_id: Optional[str] = None
    qubit: Optional[int] = None
    x: float = 0.0
    rect: Optional[QRectF] = None


class SequenceCanvas(QWidget):
    request_open_inspector = pyqtSignal(str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self.to_scale = False
        self.columns: list = []
        self._hover = None
        self._drop: Optional[DropTarget] = None
        self._press_pos: Optional[QPoint] = None
        self._press_hit = None
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        controller.changed.connect(self._relayout)
        controller.refreshed.connect(self._relayout)
        controller.selection_changed.connect(lambda _: self.update())
        self._relayout()

    # ================================================================== geometry
    @property
    def colors(self) -> dict:
        return style.CANVAS

    @property
    def n_lanes(self) -> int:
        return self.ctl.station.n_channels

    def lanes_bottom(self) -> float:
        return LANE_Y0 + self.n_lanes * LANE_H

    def total_height(self) -> int:
        return int(self.lanes_bottom() + AXIS_H + 8)

    def lane_rect(self, col: Column, q: int) -> QRectF:
        return QRectF(col.x, LANE_Y0 + (q - 1) * LANE_H, col.w, LANE_H)

    def flux_rect(self, col: Column) -> QRectF:
        return QRectF(col.x + 5, FLUX_Y + 3, col.w - 10, FLUX_H - 6)

    def _segment_lengths(self) -> dict:
        res = self.ctl.resolved
        out = {}
        if res is not None:
            for r in res.segments:
                if r.wave is not None:
                    out[r.block.id] = r.wave.length
        return out

    def _relayout(self):
        """Rebuild the columns from the sequence.

        With acts in order, each act gets its segments (or a placeholder when it has none);
        out of order, segments are drawn as they are so the validator's error can be fixed.
        """
        seq = self.ctl.seq
        lengths = self._segment_lengths()
        widths = {}
        if self.to_scale and lengths:
            view_w = self.parent().width() if self.parent() else 900
            avail = max(400, view_w - GUTTER - MARGIN_R - MEASURE_W - 20)
            total = sum(max(1, lengths.get(s.id, 1)) for s in seq.segments) or 1
            for s in seq.segments:
                widths[s.id] = float(np.clip(avail * max(1, lengths.get(s.id, 1)) / total, 84, 900))
        cols, x = [], GUTTER + 6
        ordered = seq.act_order_ok()
        if ordered:
            n_before = 0
            for act in ACTS:
                segs = [(i, s) for i, s in enumerate(seq.segments) if s.act == act]
                if not segs:
                    cols.append(Column("placeholder", act, x, PLACEHOLDER_W, insert_index=n_before))
                    x += PLACEHOLDER_W
                for i, s in segs:
                    w = widths.get(s.id, COL_W)
                    cols.append(Column("segment", act, x, w, s.id, i))
                    x += w
                if act == "prep" and segs and self.prepared():
                    cols.append(Column("state", "prep", x, STATE_W, insert_index=n_before + len(segs)))
                    x += STATE_W
                n_before += len(segs)
        else:
            for i, s in enumerate(seq.segments):
                w = widths.get(s.id, COL_W)
                cols.append(Column("segment", s.act, x, w, s.id, i))
                x += w
        cols.append(Column("measure", "readout", x, MEASURE_W,
                           seq.measure.id if seq.measure is not None else None))
        x += MEASURE_W
        self.columns = cols
        self.setMinimumSize(int(x + MARGIN_R), self.total_height())
        self.resize(max(self.width(), int(x + MARGIN_R)), self.total_height())
        self.updateGeometry()
        self.update()

    def prepared(self) -> dict:
        """{qubit: PreparedState} after Preparation (empty when prep has no pulses)."""
        return prepared_states(self.ctl.seq, self.ctl.resolved, self.n_lanes)

    def sizeHint(self) -> QSize:
        w = int(self.columns[-1].x + self.columns[-1].w + MARGIN_R) if self.columns else 800
        return QSize(w, self.total_height())

    def column_for(self, block_id) -> Optional[Column]:
        for c in self.columns:
            if c.block_id == block_id:
                return c
        return None

    # ================================================================== hit testing
    def pulse_rects(self) -> list:
        """[(block, QRectF)] for every pulse chip."""
        seq = self.ctl.seq
        out = []
        for col in self.columns:
            if col.kind != "segment":
                continue
            pulses = seq.pulses_in(col.block_id)
            n = len(pulses)
            if not n:
                continue
            # chips step left to right in play order; with many pulses the step shrinks and they overlap
            inner = col.w - 16
            step = min(CHIP_W + 6, max(10.0, (inner - CHIP_W) / max(1, n - 1))) if n > 1 else 0
            total = CHIP_W + step * (n - 1)
            x0 = col.x + (col.w - total) / 2 if total < inner else col.x + 8
            for k, p in enumerate(pulses):
                q = p.qubit
                if not 1 <= q <= self.n_lanes:
                    continue
                lr = self.lane_rect(col, q)
                w = CHIP_W + (10 if PULSE_SYMBOL.get(p.TYPE, "") == "π/2" else 0)
                out.append((p, QRectF(x0 + k * step, lr.center().y() - CHIP_H / 2, w, CHIP_H)))
        return out

    def hit(self, pos: QPointF):
        """("pulse" | "segment" | "measure", block id) under pos, or None. Pulses win over segments."""
        for p, r in reversed(self.pulse_rects()):
            if r.contains(pos):
                return ("pulse", p.id)
        for col in self.columns:
            if col.kind == "segment" and self.flux_rect(col).contains(pos):
                return ("segment", col.block_id)
            measure_area = QRectF(col.x, FLUX_Y, col.w, self.lanes_bottom() - FLUX_Y)
            if col.kind == "measure" and col.block_id and measure_area.contains(pos):
                return ("measure", col.block_id)
        return None

    def drop_target(self, pos: QPointF, kind: str) -> DropTarget:
        """Where a dragged block of this kind would land: a gap between segments, a lane cell, or Measure."""
        cols = self.columns
        if kind == "measure":
            m = cols[-1]
            return DropTarget("measure", rect=QRectF(m.x, FLUX_Y, m.w, self.lanes_bottom() - FLUX_Y))
        if kind == "pulse":
            for col in cols:
                if col.kind != "segment" or not (col.x <= pos.x() < col.x + col.w):
                    continue
                q = int((pos.y() - LANE_Y0) // LANE_H) + 1
                if 1 <= q <= self.n_lanes:
                    return DropTarget("cell", segment_id=col.block_id, qubit=q, rect=self.lane_rect(col, q))
            return DropTarget("none")
        # segment: a gap between columns
        n_seg = len(self.ctl.seq.segments)
        for col in cols:
            if not (col.x <= pos.x() < col.x + col.w):
                continue
            if col.kind == "state":
                return DropTarget("gap", col.insert_index, "prep", x=col.x)
            if col.kind == "placeholder":
                return DropTarget("gap", col.insert_index, col.act, x=col.x + col.w / 2,
                                  rect=QRectF(col.x, ACT_Y, col.w, self.lanes_bottom() - ACT_Y))
            if col.kind == "measure":
                last_act = self.ctl.seq.segments[-1].act if self.ctl.seq.segments else "prep"
                return DropTarget("gap", n_seg, last_act if last_act == "readout" else "readout", x=col.x)
            before = pos.x() < col.x + col.w / 2
            return DropTarget("gap", col.seg_index if before else col.seg_index + 1, col.act,
                              x=col.x if before else col.x + col.w)
        if cols and pos.x() < cols[0].x:
            return DropTarget("gap", 0, cols[0].act, x=cols[0].x)
        return DropTarget("gap", n_seg, "readout", x=cols[-1].x if cols else GUTTER)

    # ================================================================== painting
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.colors
        p.fillRect(self.rect(), QColor(c["bg"]))
        self._paint_bands(p, c)
        self._paint_grid(p, c)
        self._paint_gutter(p, c)
        self._paint_traces(p, c)
        for col in self.columns:
            if col.kind == "segment":
                self._paint_segment_chip(p, c, col)
            elif col.kind == "placeholder":
                self._paint_placeholder(p, c, col)
            elif col.kind == "state":
                self._paint_state(p, c, col)
            else:
                self._paint_measure(p, c, col)
        self._paint_pulses(p, c)
        self._paint_axis(p, c)
        self._paint_drop(p, c)
        p.end()

    def _paint_bands(self, p, c):
        runs, cur = [], None
        for col in self.columns:
            if cur and cur[0] == col.act:
                cur[2] = col.x + col.w
            else:
                cur = [col.act, col.x, col.x + col.w]
                runs.append(cur)
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        for act, x0, x1 in runs:
            r = QRectF(x0 + 2, ACT_Y, x1 - x0 - 4, self.lanes_bottom() - ACT_Y + 4)
            path = QPainterPath()
            path.addRoundedRect(r, 8, 8)
            p.fillPath(path, QColor(c["act"][act]))
            p.setPen(QColor(c["act_text"][act]))
            width = x1 - x0
            if width > 175:
                label = ACT_LABELS[act]                    # full name, e.g. "Beamsplitter + measure"
            elif act == "prep" and width > 110:
                label = "Preparation"
            else:
                label = SHORT_ACT_LABELS[act]
            p.drawText(QRectF(x0 + 10, ACT_Y, x1 - x0 - 20, ACT_H), Qt.AlignVCenter | Qt.AlignLeft, label)

    def _paint_grid(self, p, c):
        pen = QPen(QColor(c["grid"]))
        pen.setWidthF(1.0)
        p.setPen(pen)
        x_end = self.columns[-1].x + self.columns[-1].w if self.columns else self.width()
        for q in range(self.n_lanes + 1):
            y = LANE_Y0 + q * LANE_H
            p.drawLine(QPointF(GUTTER, y), QPointF(x_end, y))
        p.drawLine(QPointF(GUTTER, FLUX_Y + FLUX_H + 4), QPointF(x_end, FLUX_Y + FLUX_H + 4))
        for col in self.columns[1:]:
            p.drawLine(QPointF(col.x, FLUX_Y), QPointF(col.x, self.lanes_bottom()))

    def _paint_gutter(self, p, c):
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(8, FLUX_Y, GUTTER - 12, FLUX_H), Qt.AlignVCenter | Qt.AlignLeft, "Flux")
        readout = set(describe.measure_qubits(self.ctl.seq))
        for q in range(1, self.n_lanes + 1):
            y = LANE_Y0 + (q - 1) * LANE_H
            p.setBrush(style.qubit_color(q))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(14, y + LANE_H / 2), 4, 4)
            p.setPen(QColor(c["text"] if q in readout else c["muted"]))
            p.drawText(QRectF(24, y, GUTTER - 26, LANE_H), Qt.AlignVCenter | Qt.AlignLeft, f"Q{q}")

    def _paint_traces(self, p, c):
        res = self.ctl.resolved
        if res is None:
            return
        waves = {r.block.id: r.wave for r in res.segments if r.wave is not None}
        ro = None
        if res.measure is not None and res.measure.ok:
            ro = np.asarray(res.measure.params.get("ff_readout_gains") or [], float)
        # each lane is scaled to its own channel's range, so small moves stay visible
        n = self.n_lanes
        lo = np.full(n, np.inf)
        hi = np.full(n, -np.inf)
        for w in waves.values():
            if w.length:
                lo = np.minimum(lo, w.samples.min(axis=1)[:n])
                hi = np.maximum(hi, w.samples.max(axis=1)[:n])
            lo = np.minimum(lo, w.start_gains[:n])
            hi = np.maximum(hi, w.start_gains[:n])
        if ro is not None and ro.size == n:
            lo, hi = np.minimum(lo, ro), np.maximum(hi, ro)
        finite = np.isfinite(lo) & np.isfinite(hi)
        lo, hi = np.where(finite, lo, 0.0), np.where(finite, hi, 0.0)
        span = np.where(hi - lo > 1, hi - lo, 1.0)
        mid = (hi + lo) / 2
        for q in range(1, n + 1):
            j = q - 1
            pen = QPen(style.qubit_color(q))
            pen.setWidthF(1.6)
            col_ = pen.color()
            col_.setAlpha(170)
            pen.setColor(col_)
            p.setPen(pen)
            y_top = LANE_Y0 + (q - 1) * LANE_H + 7
            h = LANE_H - 14
            ymap = (lambda g: y_top + h * (0.5 - (g - mid[j]) / span[j])) if span[j] > 1 \
                else (lambda g: y_top + h / 2)
            prev_pt = None
            for col in self.columns:
                pts = []
                if col.kind == "segment" and col.block_id in waves:
                    s = waves[col.block_id].samples[j]
                    if s.size == 0:
                        continue
                    m = int(min(s.size, max(2, col.w * 2)))
                    idx = np.linspace(0, s.size - 1, m)
                    vals = s[np.round(idx).astype(int)]
                    xs = col.x + 3 + (col.w - 6) * np.linspace(0, 1, m)
                    pts = [QPointF(x, ymap(v)) for x, v in zip(xs, vals)]
                elif col.kind == "state" and prev_pt is not None:
                    pts = [QPointF(col.x + 1, prev_pt.y()), QPointF(col.x + col.w - 1, prev_pt.y())]
                elif col.kind == "measure" and ro is not None and ro.size == n and self.ctl.seq.measure:
                    yv = ymap(ro[j])
                    pts = [QPointF(col.x + 3, yv), QPointF(col.x + col.w * 0.35, yv)]
                if not pts:
                    prev_pt = None
                    continue
                if prev_pt is not None:
                    p.drawLine(prev_pt, QPointF(pts[0].x(), pts[0].y()))
                p.drawPolyline(QPolygonF(pts))
                prev_pt = pts[-1]

    def _chip_path(self, r: QRectF, radius=6) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)
        return path

    def _border_pen(self, c, block_id, base=None, width=1.0):
        lvl = self.ctl.worst_level(block_id)
        if block_id == self.ctl.selected:
            pen = QPen(QColor(c["select"]), 2.2)
        elif lvl == "error":
            pen = QPen(QColor(c["error"]), 1.8)
        elif lvl == "warning":
            pen = QPen(QColor(c["warning"]), 1.6)
        else:
            pen = QPen(QColor(base or c["chip_border"]), width)
        return pen

    def _paint_segment_chip(self, p, c, col):
        b = self.ctl.seq.get(col.block_id)
        if b is None:
            return
        r = self.flux_rect(col)
        path = self._chip_path(r)
        fill = QColor(c["chip"])
        if self._hover == ("segment", b.id):
            fill = fill.darker(104)
        p.fillPath(path, fill)
        p.setBrush(Qt.NoBrush)
        p.setPen(self._border_pen(c, b.id))
        p.drawPath(path)
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(c["text"]))
        fm = QFontMetrics(f)
        badges = _badges(b)
        badge_w = 14 * len(badges)
        p.drawText(QRectF(r.x() + 9, r.y() + 4, r.width() - 18 - badge_w, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(b.name, Qt.ElideRight, int(r.width() - 18 - badge_w)))
        f2 = QFont(self.font())
        f2.setPixelSize(11)
        p.setFont(f2)
        p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(r.x() + 9, r.y() + 22, r.width() - 14, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f2).elidedText(self._duration_text(b), Qt.ElideRight, int(r.width() - 14)))
        for kind, br in self.badge_rects(col):
            color = QColor(c["badge_ref"] if kind == "ref" else c["badge_sweep"])
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            bx, by = br.center().x(), br.center().y()
            if kind == "ref":
                p.drawEllipse(QPointF(bx, by), 3.6, 3.6)
            else:
                tri = QPolygonF([QPointF(bx - 4, by + 3), QPointF(bx + 4, by + 3), QPointF(bx, by - 4)])
                p.drawPolygon(tri)

    def badge_rects(self, col) -> list:
        """[(kind, QRectF)] for the calibration dot and sweep triangle on a segment chip (hover targets)."""
        b = self.ctl.seq.get(col.block_id) if col.block_id else None
        if b is None:
            return []
        r = self.flux_rect(col)
        out, bx = [], r.right() - 10
        for kind in reversed(_badges(b)):
            out.append((kind, QRectF(bx - 7, r.y() + 5, 14, 14)))
            bx -= 14
        return list(reversed(out))

    def pulse_sweep_badge_rect(self, rect: QRectF) -> QRectF:
        return QRectF(rect.right() - 4, rect.y() - 11, 12, 11)

    def _duration_text(self, b) -> str:
        src = b.fields.get("duration_us")
        if src is None:
            src = b.fields.get("extra_samples")
        res = self.ctl.resolved
        n = None
        if res is not None:
            for r in res.segments:
                if r.block.id == b.id and r.wave is not None:
                    n = r.wave.length
        t = f"{n / self.ctl.station.samples_per_us * 1e3:.0f} ns" if n is not None and n < 3441 \
            else (f"{n / self.ctl.station.samples_per_us:.3g} µs" if n is not None else "—")
        if isinstance(src, Sweep):
            return f"{t} · sweep ‹{src.axis}›"
        return t

    def state_marker_rect(self, col, q: int) -> QRectF:
        cy = self.lane_rect(col, q).center().y()
        return QRectF(col.x + col.w / 2 - 8, cy - 8, 16, 16)

    def _paint_state(self, p, c, col):
        """Prepared state per qubit: ○ ground, ● excited, ◐ superposition, partial pie, ? unknown."""
        states = self.prepared()
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(col.x, FLUX_Y, col.w, FLUX_H), Qt.AlignCenter, "start\nstate")
        fb = QFont(f)
        fb.setWeight(QFont.DemiBold)
        fb.setPixelSize(10)
        for q, st in states.items():
            if q > self.n_lanes:
                continue
            r = self.state_marker_rect(col, q)
            qc = QColor(style.qubit_color(q))
            p.setPen(QPen(qc, 1.6))
            p.setBrush(QColor(c["bg"]))
            p.drawEllipse(r)
            if st.kind == "1":
                p.setBrush(qc)
                p.drawEllipse(r)
            elif st.kind in ("+", "~") and st.p1 is not None:
                p.setPen(Qt.NoPen)
                p.setBrush(qc)
                p.drawPie(r.adjusted(1, 1, -1, -1), 90 * 16, int(round(st.p1 * 360 * 16)))
            elif st.kind == "?":
                p.setFont(fb)
                p.setPen(qc)
                p.drawText(r, Qt.AlignCenter, "?")
        p.setBrush(Qt.NoBrush)

    def _paint_placeholder(self, p, c, col):
        r = self.flux_rect(col)
        pen = QPen(QColor(c["chip_border"]), 1.2, Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(self._chip_path(r))
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(c["muted"]))
        hint = {"prep": "Drop an FF hold\nor a ramp", "dynamics": "Drop a dynamics\nblock",
                "readout": "Drop a\nbeamsplitter"}[col.act]
        p.drawText(r, Qt.AlignCenter, hint)

    def _paint_measure(self, p, c, col):
        r = self.flux_rect(col)
        m = self.ctl.seq.measure
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        if m is None:
            p.setPen(QPen(QColor(c["chip_border"]), 1.2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawPath(self._chip_path(r))
            f.setWeight(QFont.Normal)
            f.setPixelSize(11)
            p.setFont(f)
            p.setPen(QColor(c["muted"]))
            p.drawText(r, Qt.AlignCenter, "Drop\nMeasure")
            return
        path = self._chip_path(r)
        fill = QColor(c["chip"])
        if self._hover == ("measure", m.id):
            fill = fill.darker(104)
        p.fillPath(path, fill)
        p.setBrush(Qt.NoBrush)
        p.setPen(self._border_pen(c, m.id, base=c["measure"], width=1.2))
        p.drawPath(path)
        title, group, second = describe.measure_chip_lines(self.ctl.seq)
        f2 = QFont(self.font())
        f2.setPixelSize(11)
        fm, fm2 = QFontMetrics(f), QFontMetrics(f2)
        title_w = min(fm.horizontalAdvance(title), int(r.width() * 0.55))
        p.setFont(f)
        p.setPen(QColor(c["measure"]))
        p.drawText(QRectF(r.x() + 9, r.y() + 4, title_w + 2, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(title, Qt.ElideRight, title_w + 2))
        p.setFont(f2)
        p.setPen(QColor(c["muted"]))
        gw = int(r.width() - 18 - title_w - 8)
        p.drawText(QRectF(r.right() - 9 - gw, r.y() + 4, gw, 18), Qt.AlignRight | Qt.AlignVCenter,
                   fm2.elidedText(group, Qt.ElideRight, gw))
        p.setPen(QColor(c["text"]))
        p.drawText(QRectF(r.x() + 9, r.y() + 22, r.width() - 18, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   fm2.elidedText(second, Qt.ElideRight, int(r.width() - 18)))
        # lane markers: what each measured qubit reports, and the basis pulse if there is one
        qs = set(describe.measure_qubits(self.ctl.seq))
        tag = describe.MODE_SHORT.get(describe.measure_mode(self.ctl.seq), "M")
        f3 = QFont(self.font())
        f3.setPixelSize(11)
        f3.setWeight(QFont.DemiBold)
        fm3 = QFontMetrics(f3)
        rot_color = QColor(c["pulse"].get("Pi2Pulse", c["measure"]))
        for q in range(1, self.n_lanes + 1):
            lr = self.lane_rect(col, q)
            cy = lr.center().y()
            if q not in qs:
                p.setPen(QPen(QColor(c["chip_border"]), 1.2))
                p.drawLine(QPointF(col.x + col.w - 34, cy), QPointF(col.x + col.w - 22, cy))
                continue
            pr = self.measure_marker_rect(col, q, fm3.horizontalAdvance(tag))
            p.setPen(QPen(QColor(c["measure"]), 1.3))
            p.setBrush(QColor(c["chip"]))
            p.drawRoundedRect(pr, 9, 9)
            p.setFont(f3)
            p.setPen(QColor(c["measure"]))
            p.drawText(pr, Qt.AlignCenter, tag)
            rot = describe.readout_rotation(self.ctl.seq, self.ctl.resolved, q)
            if rot:
                p.setFont(f2)
                p.setPen(rot_color)
                text = f"π/2 · {rot[1]}"
                tw = pr.left() - col.x - 10
                p.drawText(QRectF(col.x + 6, cy - 9, tw, 18), Qt.AlignRight | Qt.AlignVCenter,
                           fm2.elidedText(text, Qt.ElideRight, int(tw)))
        p.setBrush(Qt.NoBrush)

    def measure_marker_rect(self, col, q: int, text_w: float = 10) -> QRectF:
        w = max(22.0, text_w + 14)
        cy = self.lane_rect(col, q).center().y()
        return QRectF(col.x + col.w - 12 - w, cy - 9, w, 18)

    def _paint_pulses(self, p, c):
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        for b, r in self.pulse_rects():
            base = QColor(c["pulse"].get(b.TYPE, c["select"]))
            path = self._chip_path(r, 5)
            fill = QColor(base)
            if self._hover == ("pulse", b.id):
                fill = fill.lighter(112)
            p.fillPath(path, fill)
            lvl = self.ctl.worst_level(b.id)
            p.setBrush(Qt.NoBrush)
            if b.id == self.ctl.selected:
                p.setPen(QPen(QColor(c["select"]), 2.4))
                p.drawPath(self._chip_path(r.adjusted(-2, -2, 2, 2), 6))
            elif lvl in ("error", "warning"):
                p.setPen(QPen(QColor(c[lvl]), 2.0))
                p.drawPath(self._chip_path(r.adjusted(-2, -2, 2, 2), 6))
            p.setPen(QColor("#FFFFFF"))
            p.drawText(r, Qt.AlignCenter, PULSE_SYMBOL.get(b.TYPE, "?"))
            if any(isinstance(s, Sweep) or isinstance(getattr(s, "base", None), Sweep) for s in b.fields.values()):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(c["badge_sweep"]))
                p.drawPolygon(QPolygonF([QPointF(r.right() - 1, r.y() - 3), QPointF(r.right() + 5, r.y() - 3),
                                         QPointF(r.right() + 2, r.y() - 8)]))
                p.setBrush(Qt.NoBrush)

    def _paint_axis(self, p, c):
        y = self.lanes_bottom() + 6
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(c["muted"]))
        lengths = self._segment_lengths()
        spu = self.ctl.station.samples_per_us
        for col in self.columns:
            if col.kind != "segment":
                continue
            n = lengths.get(col.block_id)
            if n is None:
                continue
            t = n / spu
            p.drawText(QRectF(col.x, y, col.w, 16), Qt.AlignCenter,
                       f"{t * 1e3:.0f} ns" if t < 1 else f"{t:.3g} µs")
        total = sum(lengths.values()) / spu if lengths else 0.0
        hold = float(self.ctl.station.data.get("init_hold_us", 5.0))
        p.drawText(QRectF(8, y, GUTTER, 16), Qt.AlignLeft | Qt.AlignVCenter, "Time")
        states = self.prepared()
        if states:
            last = self.columns[-1]
            p.setPen(QColor(c["text"]))
            p.drawText(QRectF(GUTTER + 8, y + 30, last.x + last.w - GUTTER, 16), Qt.AlignLeft | Qt.AlignVCenter,
                       f"Prepared state  {state_string(states)}   (Q1→Q{len(states)}; {state_counts(states)})")
            p.setPen(QColor(c["muted"]))
        if self.columns:
            last = self.columns[-1]
            p.drawText(QRectF(GUTTER, y + 14, last.x + last.w - GUTTER, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f"Body {total:.3g} µs, after a {hold:g} µs settle at the init gains"
                       + ("  ·  columns to scale" if self.to_scale else "  ·  columns not to scale"))

    def _paint_drop(self, p, c):
        d = self._drop
        if d is None or d.kind == "none":
            return
        color = QColor(c["drop"])
        if d.kind == "gap":
            if d.rect is not None:
                fill = QColor(color)
                fill.setAlpha(36)
                p.fillRect(d.rect, fill)
            pen = QPen(color, 3)
            p.setPen(pen)
            p.drawLine(QPointF(d.x, FLUX_Y - 2), QPointF(d.x, self.lanes_bottom()))
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([QPointF(d.x - 6, FLUX_Y - 8), QPointF(d.x + 6, FLUX_Y - 8),
                                     QPointF(d.x, FLUX_Y - 1)]))
        elif d.rect is not None:
            fill = QColor(color)
            fill.setAlpha(48)
            p.fillRect(d.rect.adjusted(2, 2, -2, -2), fill)
            p.setPen(QPen(color, 1.6, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(d.rect.adjusted(2, 2, -2, -2))

    # ================================================================== mouse
    def mousePressEvent(self, e):
        self.setFocus()
        h = self.hit(QPointF(e.pos()))
        if e.button() == Qt.LeftButton:
            self._press_pos, self._press_hit = e.pos(), h
            self.ctl.select(h[1] if h else None)

    def mouseMoveEvent(self, e):
        h = self.hit(QPointF(e.pos()))
        if h != self._hover:
            self._hover = h
            self.setCursor(Qt.PointingHandCursor if h else Qt.ArrowCursor)
            self.update()
        if self._press_pos is not None and self._press_hit and self._press_hit[0] in ("segment", "pulse") and \
                (e.pos() - self._press_pos).manhattanLength() > 8:
            kind, bid = self._press_hit
            self._press_pos = None
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(MIME_MOVE, json.dumps({"id": bid, "kind": kind}).encode())
            drag.setMimeData(mime)
            drag.setPixmap(self._drag_pixmap(bid))
            drag.exec_(Qt.MoveAction)

    def mouseReleaseEvent(self, e):
        self._press_pos = None

    def mouseDoubleClickEvent(self, e):
        h = self.hit(QPointF(e.pos()))
        if h:
            self.request_open_inspector.emit(h[1])

    def leaveEvent(self, _):
        self._hover = None
        self.update()

    def event(self, e):
        if e.type() == e.ToolTip:
            text = self.tooltip_at(QPointF(e.pos()))
            if text:
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def tooltip_at(self, pos: QPointF) -> str:
        """Resolved values for the chip under pos; a Measure lane marker gets that qubit's readout."""
        for col in self.columns:
            if col.kind == "segment":
                for kind, br in self.badge_rects(col):
                    if br.contains(pos):
                        return describe.badge_tooltip(self.ctl.seq.get(col.block_id), kind)
        for col in self.columns:
            if col.kind == "state" and col.x <= pos.x() < col.x + col.w and pos.y() >= LANE_Y0:
                q = int((pos.y() - LANE_Y0) // LANE_H) + 1
                st = self.prepared().get(q)
                if st is not None:
                    return describe.state_tooltip(st)
        for b, r in self.pulse_rects():
            if describe.swept_fields(b) and self.pulse_sweep_badge_rect(r).contains(pos):
                return describe.badge_tooltip(b, "sweep")
        h = self.hit(pos)
        if not h:
            return ""
        if h[0] == "measure":
            col = self.column_for(h[1])
            if col is not None and pos.y() >= LANE_Y0:
                q = int((pos.y() - LANE_Y0) // LANE_H) + 1
                if q in describe.measure_qubits(self.ctl.seq):
                    return describe.measure_lane_tooltip(self.ctl, q)
        return describe.block_tooltip(self.ctl, h[1])

    def _drag_pixmap(self, bid) -> QPixmap:
        b = self.ctl.seq.get(bid)
        pm = QPixmap(140, 30)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.colors
        p.setBrush(QColor(c["chip"]))
        p.setPen(QPen(QColor(c["select"]), 2))
        p.drawRoundedRect(QRectF(1, 1, 138, 28), 6, 6)
        p.setPen(QColor(c["text"]))
        p.drawText(QRectF(8, 0, 124, 30), Qt.AlignVCenter, b.name if b else "")
        p.end()
        return pm

    def contextMenuEvent(self, e):
        h = self.hit(QPointF(e.pos()))
        if not h:
            if self.ctl.can_paste():
                menu = QMenu(self)
                menu.addAction("Paste", self.ctl.paste)
                menu.exec_(e.globalPos())
            return
        kind, bid = h
        self.ctl.select(bid)
        b = self.ctl.seq.get(bid)
        menu = QMenu(self)
        menu.addAction("Copy\t" + style.shortcut_text("Ctrl+C"), lambda: self.ctl.copy(bid))
        paste = menu.addAction("Paste after\t" + style.shortcut_text("Ctrl+V"), self.ctl.paste)
        paste.setEnabled(self.ctl.can_paste())
        if kind != "measure":
            menu.addAction("Duplicate\t" + style.shortcut_text("Ctrl+D"), lambda: self.ctl.duplicate(bid))
        if kind == "segment":
            sub = menu.addMenu("Move to act")
            for act in ACTS:
                a = sub.addAction(ACT_LABELS[act], lambda act=act: self.ctl.set_act(bid, act))
                a.setEnabled(act != b.act and act in b.ALLOWED_ACTS)
        menu.addAction("Save as preset…", lambda: self.window().save_preset(bid)
                       if hasattr(self.window(), "save_preset") else None)
        menu.addSeparator()
        menu.addAction("Delete", lambda: self.ctl.remove(bid))
        menu.exec_(e.globalPos())

    def keyPressEvent(self, e):
        sel = self.ctl.selected
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and sel:
            self.ctl.remove(sel)
        elif e.key() == Qt.Key_D and e.modifiers() & Qt.ControlModifier and sel:
            self.ctl.duplicate(sel)
        elif e.matches(QKeySequence.Copy) and sel:
            self.ctl.copy(sel)
        elif e.matches(QKeySequence.Paste):
            self.ctl.paste()
        elif e.key() in (Qt.Key_Left, Qt.Key_Right):
            segs = [c.block_id for c in self.columns if c.kind == "segment"]
            if segs:
                i = segs.index(sel) if sel in segs else (-1 if e.key() == Qt.Key_Right else len(segs))
                i = max(0, min(len(segs) - 1, i + (1 if e.key() == Qt.Key_Right else -1)))
                self.ctl.select(segs[i])
        elif e.key() == Qt.Key_Escape:
            self.ctl.select(None)
        else:
            super().keyPressEvent(e)

    # ================================================================== drag and drop
    def _drag_kind(self, mime) -> Optional[tuple]:
        if mime.hasFormat(MIME_NEW):
            t = bytes(mime.data(MIME_NEW)).decode()
            return ("new", t, block_class(t).KIND)
        if mime.hasFormat(MIME_PRESET):
            d = json.loads(bytes(mime.data(MIME_PRESET)).decode())
            t = d["blocks"][0]["type"]
            return ("preset", d, block_class(t).KIND)
        if mime.hasFormat(MIME_MOVE):
            d = json.loads(bytes(mime.data(MIME_MOVE)).decode())
            return ("move", d["id"], d["kind"])
        return None

    def dragEnterEvent(self, e):
        if self._drag_kind(e.mimeData()):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        k = self._drag_kind(e.mimeData())
        if not k:
            return
        kind = k[2]
        self._drop = self.drop_target(QPointF(e.pos()), kind)
        if self._drop.kind == "none":
            e.ignore()
        else:
            e.acceptProposedAction()
        self.update()

    def dragLeaveEvent(self, _):
        self._drop = None
        self.update()

    def dropEvent(self, e):
        k = self._drag_kind(e.mimeData())
        d = self.drop_target(QPointF(e.pos()), k[2]) if k else None
        self._drop = None
        self.update()
        if not k or d is None or d.kind == "none":
            return
        src, payload, kind = k
        if src == "new":
            if kind == "segment":
                self.ctl.add_block(payload, index=d.index, act=d.act)
            elif kind == "pulse":
                self.ctl.add_block(payload, segment_id=d.segment_id, qubit=d.qubit)
            else:
                self.ctl.add_block(payload)
        elif src == "preset":
            if kind == "segment":
                self.ctl.add_preset(payload, index=d.index, act=d.act)
            elif kind == "pulse":
                self.ctl.add_preset(payload, segment_id=d.segment_id, qubit=d.qubit)
            else:
                self.ctl.add_preset(payload)
        else:
            if kind == "segment":
                self.ctl.move_segment(payload, d.index, d.act)
            elif kind == "pulse":
                self.ctl.move_pulse(payload, d.segment_id, d.qubit)
        e.acceptProposedAction()
        self.setFocus()


# ---------------------------------------------------------------------- helpers
def _badges(b) -> list:
    has_ref = has_sweep = False
    for s in b.fields.values():
        base = base_source(s)
        has_ref |= isinstance(base, Ref)
        has_sweep |= isinstance(base, Sweep)
    return (["ref"] if has_ref else []) + (["sweep"] if has_sweep else [])
