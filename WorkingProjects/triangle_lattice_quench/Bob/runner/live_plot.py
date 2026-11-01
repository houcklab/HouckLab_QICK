"""Plots of a run's results, decided by the sequence, not written per experiment.

The sequence already says what a plot should show: its sweep axes (names, values, units)
are the plot's axes, and its Measure block says which qubits were read out and what was
measured. So one layout covers every experiment:

    no sweep axes     one value per qubit
    1 axis            one line per qubit against that axis (the lab's SweepExperiment1D_lines)
    2 axes            one map per qubit: inner axis across, outer axis down
    3 or more axes    maps of the two innermost axes at the current outer point

    plot_layout(seq)     what to draw
    RunPlot              a matplotlib figure filled in point by point (exported scripts)
    show_saved(path)     the same figure from a saved .h5

The GUI's Data tab draws the same layout with pyqtgraph.

IQ mode shows the lab's "IQ contrast": I/Q rotated so the measured points spread along one
axis, then centred (Helpers/IQ_contrast.py), computed over the points measured so far.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .save import measured_qubits

QUANTITY = {
    "populations_corrected": ("population_corrected", "Excited state population (corrected)"),
    "populations": ("population", "Excited state population"),
    "iq": ("contrast", "IQ contrast (a.u.)"),
}
REDRAW_EVERY_S = 0.5


@dataclass
class Axis:
    name: str
    values: np.ndarray
    unit: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} ({self.unit})" if self.unit else self.name


@dataclass
class PlotLayout:
    kind: str                                  # "points", "lines" or "maps"
    quantity: str                              # data key plotted: population_corrected, population, contrast
    ylabel: str
    qubits: list
    axes: list = field(default_factory=list)   # every sweep axis, outermost first
    title: str = ""

    @property
    def shape(self) -> tuple:
        return tuple(len(a.values) for a in self.axes) or (1,)

    @property
    def x(self) -> Optional[Axis]:
        return self.axes[-1] if self.axes else None

    @property
    def y(self) -> Optional[Axis]:
        return self.axes[-2] if len(self.axes) >= 2 else None

    @property
    def outer(self) -> list:
        return self.axes[:-2]

    def outer_index(self, k: int) -> tuple:
        """Index of the outer axes (all but the two innermost) for flat sweep point ``k``."""
        if not self.outer:
            return ()
        return tuple(int(i) for i in np.unravel_index(int(k), self.shape)[:len(self.outer)])

    def outer_text(self, idx: tuple) -> str:
        return ", ".join(f"{a.name} = {a.values[i]:g}{' ' + a.unit if a.unit else ''}"
                         for a, i in zip(self.outer, idx))


def plot_layout(seq, simulated: bool = False) -> PlotLayout:
    mode = "iq"
    if seq.measure is not None:
        mode = str(getattr(seq.measure.fields.get("mode"), "value", "iq"))
    quantity, ylabel = QUANTITY.get(mode, QUANTITY["iq"])
    axes = [Axis(a.name, a.values(), a.unit) for a in seq.settings.sweeps]
    kind = "points" if not axes else "lines" if len(axes) == 1 else "maps"
    title = f"{seq.name} (simulated data)" if simulated else seq.name
    return PlotLayout(kind, quantity, ylabel, measured_qubits(seq), axes, title)


def iq_contrast(i, q) -> np.ndarray:
    """IQ_contrast from Helpers/IQ_contrast.py over the measured (finite) points; NaN elsewhere."""
    import scipy.optimize
    i, q = np.asarray(i, float), np.asarray(q, float)
    out = np.full(i.shape, np.nan)
    ok = np.isfinite(i) & np.isfinite(q)
    if not ok.any():
        return out
    im, qm = i[ok], q[ok]

    def q_spread(theta):
        new_q = np.sin(theta) * im + np.cos(theta) * qm
        return np.max(new_q) - np.min(new_q)
    theta = scipy.optimize.minimize(q_spread, (np.pi / 4,)).x
    rot_i = np.cos(theta) * im - np.sin(theta) * qm
    out[ok] = rot_i - np.mean(rot_i)
    return out


def values(layout: PlotLayout, data: dict, outer_idx: tuple = ()) -> np.ndarray:
    """What to draw, one row per read-out qubit, shaped like the shown axes."""
    if layout.quantity == "contrast":
        if "I" not in data:
            return np.full((len(layout.qubits), *layout.shape), np.nan)
        z = np.stack([iq_contrast(data["I"][r], data["Q"][r]) for r in range(len(data["I"]))])
    elif layout.quantity in data:
        z = np.asarray(data[layout.quantity], float)
    else:
        return np.full((len(layout.qubits), *layout.shape), np.nan)
    z = z.reshape((z.shape[0], *layout.shape))
    if layout.outer:
        z = z[(slice(None), *outer_idx)]
    return z


class RunPlot:
    """A matplotlib figure for one run. Feed it points with ``add_point`` (a BobExperiment
    listener) or whole arrays with ``set_data``; ``save`` writes a PNG."""

    def __init__(self, layout: PlotLayout, show: bool = True):
        import matplotlib
        if not show:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        self.plt, self.layout, self.show = plt, layout, show
        n = max(1, len(layout.qubits))
        self.data: dict = {}
        self.outer_idx: tuple = layout.outer_index(0)
        self.done = 0
        self._last_draw = 0.0
        if layout.kind == "maps":
            cols = min(n, 3)
            rows = int(np.ceil(n / cols))
            self.fig, axs = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.4 * rows), squeeze=False,
                                         constrained_layout=True)
            self.axes = list(axs.ravel())
            for ax in self.axes[n:]:
                ax.set_visible(False)
        else:
            self.fig, ax = plt.subplots(figsize=(8, 4.8), constrained_layout=True)
            self.axes = [ax]
        self._artists: list = []
        self._draw_empty()
        if show:
            plt.ion()
            self.fig.show()

    # ---------------------------------------------------------------- data in
    def add_point(self, k: int, pt=None, point: Optional[dict] = None) -> None:
        point = point if point is not None else pt
        idx = np.unravel_index(int(k), self.layout.shape)
        for key, vals in point.items():
            vals = np.asarray(vals, float)
            if key not in self.data:
                self.data[key] = np.full((len(vals), *self.layout.shape), np.nan)
            self.data[key][(slice(None), *idx)] = vals
        self.done = max(self.done, int(k) + 1)
        self.outer_idx = self.layout.outer_index(k)
        last = self.done >= int(np.prod(self.layout.shape))
        if last or time.monotonic() - self._last_draw >= REDRAW_EVERY_S:
            self.redraw()

    def set_data(self, data: dict, done: Optional[int] = None) -> None:
        self.data = {k: np.asarray(v, float) for k, v in data.items()
                     if isinstance(v, np.ndarray) and v.ndim >= 1 and v.shape[1:] == self.layout.shape}
        self.done = int(np.prod(self.layout.shape)) if done is None else int(done)
        self.outer_idx = self.layout.outer_index(max(0, self.done - 1))
        self.redraw()

    # ---------------------------------------------------------------- drawing
    def _qubit_label(self, r: int) -> str:
        q = self.layout.qubits
        return f"Read: Q{q[r]}" if r < len(q) else f"Read: {r}"

    def _draw_empty(self):
        L, n = self.layout, max(1, len(self.layout.qubits))
        self.fig.suptitle(L.title)
        if L.kind == "points":
            ax = self.axes[0]
            self._artists = [ax.plot([r], [np.nan], "o", label=self._qubit_label(r))[0] for r in range(n)]
            ax.set_xticks(range(n), [f"Q{q}" for q in L.qubits] or ["0"])
            ax.set_ylabel(L.ylabel)
        elif L.kind == "lines":
            ax = self.axes[0]
            self._artists = [ax.plot(L.x.values, np.full(len(L.x.values), np.nan), marker="o", markersize=3,
                                     label=self._qubit_label(r))[0] for r in range(n)]
            ax.set_xlabel(L.x.label)
            ax.set_ylabel(L.ylabel)
            ax.legend(fontsize=8)
        else:
            x, y = L.x.values, L.y.values
            ext = [*self._edges(x), *self._edges(y)]
            for r in range(n):
                ax = self.axes[r]
                im = ax.imshow(np.full((len(y), len(x)), np.nan), origin="lower", aspect="auto", extent=ext,
                               interpolation="nearest")
                self.fig.colorbar(im, ax=ax, label=L.ylabel if r % 3 == 2 or r == n - 1 else None)
                ax.set_title(self._qubit_label(r).replace("Read: ", ""))
                ax.set_xlabel(L.x.label)
                ax.set_ylabel(L.y.label)
                self._artists.append(im)

    @staticmethod
    def _edges(v):
        v = np.asarray(v, float)
        if len(v) < 2:
            return (v[0] - 0.5, v[0] + 0.5) if len(v) else (0, 1)
        step = (v[-1] - v[0]) / (len(v) - 1)
        return v[0] - step / 2, v[-1] + step / 2

    def redraw(self):
        L = self.layout
        z = values(L, self.data, self.outer_idx)
        for r, art in enumerate(self._artists):
            if r >= len(z):
                break
            if L.kind == "points":
                art.set_ydata([z[r].ravel()[0]])
            elif L.kind == "lines":
                art.set_ydata(z[r])
            else:
                art.set_data(z[r])
                finite = z[r][np.isfinite(z[r])]
                if finite.size:
                    lo, hi = float(finite.min()), float(finite.max())
                    art.set_clim(lo, hi if hi > lo else lo + 1e-9)
        if L.kind != "maps":
            self.axes[0].relim()
            self.axes[0].autoscale_view()
        n = int(np.prod(L.shape))
        progress = f"{self.done} of {n} points"
        outer = f"  ·  {L.outer_text(self.outer_idx)}" if L.outer else ""
        self.fig.suptitle(f"{L.title}\n{progress}{outer}", fontsize=11)
        self._last_draw = time.monotonic()
        if self.show:
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()

    def save(self, path) -> Path:
        self.redraw()
        self.fig.savefig(str(path), dpi=120)
        return Path(path)


def png_path(h5_path) -> Path:
    """The lab's naming: the plot sits next to the data with the same stem (…_data.png)."""
    return Path(h5_path).with_suffix(".png")


def show_saved(path, show: bool = True, save_png: bool = False) -> RunPlot:
    """Plot a saved run (Bob .h5). Unmeasured points of a stopped run are blank."""
    from ..core.sequence import Sequence
    from .save import load_run
    run = load_run(path)
    seq = Sequence.from_dict(run["sequence"])
    plot = RunPlot(plot_layout(seq, simulated=run["simulated"]), show=show)
    plot.set_data(run["data"], done=run["points_done"])
    if run["status"] != "complete":
        plot.fig.suptitle(plot.fig._suptitle.get_text() + f"  ·  {run['status']}", fontsize=11)
    if save_png:
        plot.save(png_path(path))
    if show:
        plot.plt.show(block=True)
    return plot


if __name__ == "__main__":                     # python -m Bob.runner.live_plot <run>_data.h5
    import sys
    if len(sys.argv) != 2:
        sys.exit("usage: python -m Bob.runner.live_plot <run>_data.h5")
    show_saved(sys.argv[1])
