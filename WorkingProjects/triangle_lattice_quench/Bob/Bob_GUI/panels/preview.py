"""Preview: the compiled FF waveform on every channel and the drive pulses at the previewed sweep point."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from .. import style
from ..widgets import InfoIcon


class PreviewPanel(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.point_label = QLabel()
        self.point_label.setObjectName("muted")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximumWidth(260)
        self.slider.valueChanged.connect(self.ctl.set_preview_index)
        self.comp = QCheckBox("IIR compensation")
        self.comp.setChecked(True)
        self.comp.toggled.connect(self.ctl.set_compensate)
        self.raw = QCheckBox("Overlay uncompensated")
        self.raw.toggled.connect(lambda _: self.redraw())
        lab = QLabel("Sweep point")
        lab.setObjectName("field_label")
        bar.addWidget(lab)
        bar.addWidget(InfoIcon("Which point of the sweep the canvas, preview, problems and resolved values "
                               "show. Everything is recompiled for that point."))
        bar.addWidget(self.slider)
        bar.addWidget(self.point_label, 1)
        bar.addWidget(self.comp)
        bar.addWidget(self.raw)
        bar.addWidget(InfoIcon("Top: the flux waveform uploaded for each channel (colors match the qubit lanes). "
                               "IIR compensation pre-distorts it to cancel line filtering; it needs the station's "
                               "coefficient files. Bottom: each drive pulse, at the time it plays."))
        lay.addLayout(bar)
        pg.setConfigOptions(antialias=True)
        self.glw = pg.GraphicsLayoutWidget()
        lay.addWidget(self.glw, 1)
        self.ff_plot = self.glw.addPlot(row=0, col=0)
        self.ff_plot.setLabel("left", "FF gain (DAC)")
        self.ff_plot.getAxis("left").enableAutoSIPrefix(False)
        self.ff_plot.showGrid(x=True, y=True, alpha=0.15)
        self.drive_plot = self.glw.addPlot(row=1, col=0)
        self.drive_plot.setLabel("left", "Drives")
        self.drive_plot.getAxis("left").setStyle(showValues=False)
        self.drive_plot.setLabel("bottom", "Time from start of FF body (µs)")
        self.drive_plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.ff_plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.drive_plot.setXLink(self.ff_plot)
        self.drive_plot.showGrid(x=True, y=False, alpha=0.15)
        self.glw.ci.layout.setRowStretchFactor(0, 5)
        self.glw.ci.layout.setRowStretchFactor(1, 3)
        self.drive_plot.getAxis("left").setWidth(self.ff_plot.getAxis("left").width())
        controller.refreshed.connect(self.redraw)
        self._style_plots()

    def _style_plots(self):
        c = style.CANVAS
        self.glw.setBackground(c["bg"])
        for plot in (self.ff_plot, self.drive_plot):
            for ax in ("left", "bottom"):
                a = plot.getAxis(ax)
                a.setPen(pg.mkPen(c["muted"]))
                a.setTextPen(pg.mkPen(c["text"]))
        self.redraw()

    def redraw(self):
        ctl = self.ctl
        n_pts = ctl.seq.settings.n_points()
        self.slider.blockSignals(True)
        self.slider.setMaximum(max(0, min(n_pts - 1, 2**31 - 1)))     # a Qt slider holds a 32-bit int
        self.slider.setValue(min(ctl.preview_index, n_pts - 1, 2**31 - 1))
        self.slider.setEnabled(n_pts > 1)
        self.slider.blockSignals(False)
        pt = ctl.seq.settings.point(ctl.preview_index)
        self.point_label.setText(f"{ctl.preview_index + 1} of {n_pts}" +
                                 ("   " + ",  ".join(f"{k} = {v:.4g}" for k, v in pt.items()) if pt else ""))
        comp_ok = ctl.compiled is not None and ctl.compiled.compensated
        self.comp.setToolTip("" if comp_ok or not ctl.compensate else
                             "IIR coefficient files are not in the station folder, so the waveform is shown "
                             "uncompensated.")
        self.ff_plot.clear()
        self.drive_plot.clear()
        c = style.CANVAS
        cp = ctl.compiled
        if cp is None:
            empty = not ctl.seq.segments
            msg = pg.TextItem("Add blocks to the canvas to see the compiled waveform." if empty else
                              "Fix the errors in Problems to see the compiled waveform.", color=c["muted"],
                              anchor=(0.5, 0.5))
            msg.setPos(0.5, 0)
            self.ff_plot.addItem(msg)
            self.ff_plot.setXRange(0, 1, padding=0)
            self.ff_plot.setYRange(-1, 1, padding=0)
            self.drive_plot.setYRange(0, 1, padding=0)
            return
        t = cp.time_axis_us()
        for j in range(cp.ff.shape[0]):
            color = style.QUBIT_COLORS[j % 8]
            if self.raw.isChecked() and cp.compensated:
                self.ff_plot.plot(t, cp.ff_raw[j], pen=pg.mkPen(color, width=1, style=Qt.DashLine))
            self.ff_plot.plot(t, cp.ff[j], pen=pg.mkPen(color, width=1.6))
        spu = cp.samples_per_us
        head = int(cp.channel_delays.max()) if cp.channel_delays.size else 0
        top = float(np.nanmax(cp.ff)) if cp.ff.size else 0.0
        for k, b in enumerate(cp.segment_bounds[:-1]):
            if cp.segment_bounds[k + 1] == b:          # zero-length at this point: no line, no label
                continue
            x = (b + head) / spu
            self.ff_plot.addItem(pg.InfiniteLine(pos=x, angle=90,
                                                 pen=pg.mkPen(c["muted"], width=1, style=Qt.DashLine)))
            near_end = x > 0.8 * (t[-1] if t.size else 1)
            lab = pg.TextItem(cp.segment_names[k], color=c["act_text"].get(cp.segment_acts[k], c["muted"]),
                              anchor=(1, 1) if near_end else (0, 1))
            lab.setPos(x, top)
            self.ff_plot.addItem(lab)
        n_q = ctl.station.n_channels
        for d in cp.drives:
            n = max(8, int(d.length_us * spu))
            xs = d.t_us + np.linspace(0, d.length_us, n)
            mu, sig = d.t_us + d.length_us / 2, max(d.sigma_us, 1e-6)
            env = np.exp(-((xs - mu) ** 2) / (2 * sig ** 2))
            y0 = n_q - d.qubit
            color = style.QUBIT_COLORS[(d.qubit - 1) % 8]
            curve = self.drive_plot.plot(xs, y0 + 0.8 * env, pen=pg.mkPen(color, width=1.4))
            base = self.drive_plot.plot(xs, np.full_like(xs, y0), pen=pg.mkPen(color, width=0.5))
            fill = pg.FillBetweenItem(curve, base, brush=pg.mkBrush(color + "55"))
            self.drive_plot.addItem(fill)
        self.drive_plot.setYRange(-0.3, n_q - 0.1, padding=0)
        self.ff_plot.setXRange(0, max(t[-1] if t.size else 1, 1e-3), padding=0.01)
        if cp.ff.size:
            lo, hi = float(np.nanmin(cp.ff)), float(np.nanmax(cp.ff))
            pad = max(500.0, 0.12 * (hi - lo))
            self.ff_plot.setYRange(lo - pad, hi + pad * 1.6, padding=0)
