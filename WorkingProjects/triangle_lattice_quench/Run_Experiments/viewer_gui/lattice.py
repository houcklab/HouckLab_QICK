"""Clickable lattice selector: geometry, hit test, and the Qt widget.

Geometry is a GUI-local copy of ``helper_Triladder_plotting._triladder_positions``
rather than an import, so the viewer's picture (hit radii, spacing, other topologies)
can evolve without perturbing the analysis plots. Topology itself is always read from
the device json -- never hardcoded.

Imports: matplotlib + PyQt5 + DeviceData (json/dataclasses/numpy/dacite/scipy). No qick.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from matplotlib.transforms import ScaledTranslation
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from . import data_index as dx
from . import style as st
from .widgets import MplCanvas


def triladder_positions(n_qubits: int) -> tuple[dict, dict]:
    """Zigzag coords: Qq at column q-1 (odd->top, even->bottom); Ck midway between
    Qk and Q(k+2)."""
    dx_, x0, top_y = 0.25, 0.225, 0.4
    bot_y = top_y - dx_ * 2 ** 0.5
    row_y = lambda idx: top_y if idx % 2 == 1 else bot_y
    qubit_pos = {f"Q{q}": (x0 + (q - 1) * dx_, row_y(q)) for q in range(1, n_qubits + 1)}
    coupler_pos = {f"C{k}": (x0 + k * dx_, row_y(k)) for k in range(1, n_qubits - 1)}
    return qubit_pos, coupler_pos


def device_topology(device: str, json_dir=dx.DEVICE_JSON_DIR) -> dict:
    """n_qubits + qubit-qubit edges read from the device json.

    Returns {'qubits': {...}, 'couplers': {...}, 'edges': [(a, b), ...]}; an empty
    topology if the json is missing or DeviceData cannot be imported.
    """
    path = Path(json_dir) / f"{device}.json"
    if not path.exists():
        return {"qubits": {}, "couplers": {}, "edges": []}
    try:
        # Lazy: keeps dacite/scipy off the import path of the pure-logic modules.
        from triangle_lattice_quench.Device_Calibration.Device_calib.DeviceData import DeviceData
        dev = DeviceData.from_json(str(path))
        qubit_names = [n for n, t in dev.transmons.items() if t.role == "Qubit"]
        couplings = [(c.q1, c.q2) for c in dev.couplings]
    except Exception:
        return {"qubits": {}, "couplers": {}, "edges": []}
    qubit_pos, coupler_pos = triladder_positions(len(qubit_names))
    edges = [(a, b) for a, b in couplings if a in qubit_pos and b in qubit_pos]
    return {"qubits": qubit_pos, "couplers": coupler_pos, "edges": edges,
            "rungs": find_rungs(qubit_pos, coupler_pos, edges)}


def find_rungs(qubit_pos: dict, coupler_pos: dict, edges: list, tol: float = 1e-6) -> dict:
    """{(a, b): midpoint} for qubit-qubit edges with NO coupler at their midpoint.

    Decided from the geometry, not index parity, so other topologies stay correct:
    on the triladder the Qk-Q(k+2) edges carry a coupler and the zig-zag diagonals
    (Q1-Q2, Q2-Q3, ...) do not.
    """
    rungs = {}
    for a, b in edges:
        mid = ((qubit_pos[a][0] + qubit_pos[b][0]) / 2, (qubit_pos[a][1] + qubit_pos[b][1]) / 2)
        if not any(abs(cx - mid[0]) < tol and abs(cy - mid[1]) < tol
                   for cx, cy in coupler_pos.values()):
            rungs[(a, b)] = mid
    return rungs


def _seg_distance(p, a, b) -> float:
    """Distance from point p to segment ab."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    vx, vy = bx - ax, by - ay
    denom = vx * vx + vy * vy
    t = 0.0 if denom == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / denom))
    return ((px - ax - t * vx) ** 2 + (py - ay - t * vy) ** 2) ** 0.5


def hit_test(topo: dict, x: float, y: float, node_r: float = 0.05,
             edge_tol: float = 0.03, marker_r: Optional[float] = None) -> Optional[tuple]:
    """Map a click in data coords to ('qubit', 'Q3') | ('pair', ('Q1','Q3')) | None.

    Priority: a qubit under the cursor, then a pair marker -- a coupler square (Ck
    stands for the Qk-Q(k+2) pair and sits at that segment's midpoint) or a rung square,
    on equal footing, nearest wins -- then the nearest qubit-qubit edge. ``node_r`` is
    the qubit pick radius, ``marker_r`` the square one (defaults to node_r); all in data
    units. Pure function -- testable without a canvas.
    """
    marker_r = node_r if marker_r is None else marker_r
    qubits, couplers, edges = topo["qubits"], topo["couplers"], topo["edges"]
    near = lambda pos: ((pos[0] - x) ** 2 + (pos[1] - y) ** 2) ** 0.5
    hits = sorted(((near(p), n) for n, p in qubits.items()), key=lambda t: t[0])
    if hits and hits[0][0] <= node_r:
        return ("qubit", hits[0][1])
    markers = [(near(p), (f"Q{int(n[1:])}", f"Q{int(n[1:]) + 2}")) for n, p in couplers.items()]
    markers += [(near(mid), pair) for pair, mid in topo.get("rungs", {}).items()]
    markers.sort(key=lambda t: t[0])
    if markers and markers[0][0] <= marker_r:
        return ("pair", markers[0][1])
    ehits = sorted(((_seg_distance((x, y), qubits[a], qubits[b]), (a, b)) for a, b in edges),
                   key=lambda t: t[0])
    if ehits and ehits[0][0] <= edge_tol:
        return ("pair", ehits[0][1])
    return None


def _min_dist(points_a, points_b) -> float:
    return min((((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
                for ax, ay in points_a for bx, by in points_b), default=0.0)


# --- sizing: everything scales with the PIXEL spacing of the drawn lattice ----------
QUBIT_FRAC = 0.57            # qubit diameter / smallest qubit-qubit edge length
QUBIT_MS_RANGE = (22, 60)    # clamp, points
MARKER_FRAC = 0.6            # coupler / rung marker size / qubit size
GAP_PT = 3                   # minimum drawn gap between a qubit and a pair marker
PAD_PX = 4                   # breathing room past the outermost marker edge
MIN_TARGET_PX = 30           # pair markers are clickable over at least this diameter
QUBIT_SLACK_PX = 3           # a click this far outside a qubit's edge still counts


def lattice_sizes(topo: dict, scale: float, dpi: float) -> dict:
    """Marker sizes (points) and pick radii (pixels) at ``scale`` pixels per data unit.

    The qubit is ~57% of the shortest qubit-qubit edge. Pair markers (couplers and rungs
    are both squares) are 60% of that, but capped so a square -- whose worst-case extent
    along the diagonal toward a qubit is its half-diagonal, edge included -- keeps GAP_PT
    clear of the nearest qubit; on the triladder the rung squares sit only ~0.22 units
    from two qubits, and that cap is what binds.
    """
    ppt = dpi / 72.0
    qubits = list(topo["qubits"].values())
    markers = list(topo["couplers"].values()) + list(topo.get("rungs", {}).values())
    pairs = topo["edges"] or [(a, b) for a in topo["qubits"] for b in topo["qubits"] if a < b]
    spacing = min((_min_dist([topo["qubits"][a]], [topo["qubits"][b]]) for a, b in pairs),
                  default=1.0)
    zoom = st.current_scale()
    lo, hi = QUBIT_MS_RANGE[0] * zoom, QUBIT_MS_RANGE[1] * zoom
    qubit_ms = max(lo, min(hi, QUBIT_FRAC * spacing * scale / ppt))
    qubit_r_pt = qubit_ms / 2 + 1.0                       # + half the selected edge width
    if markers:
        free_pt = _min_dist(qubits, markers) * scale / ppt - qubit_r_pt - GAP_PT
        edge_pt = max(st.PAIR_MEW, st.PAIR_MEW_ON)         # drawn edge, selected or not
        marker_ms = max(6.0, min(MARKER_FRAC * qubit_ms, 2 * free_pt / 2 ** 0.5 - edge_pt))
    else:
        marker_ms = MARKER_FRAC * qubit_ms
    lw = max(2.5, qubit_ms / 6)
    return {
        "qubit_ms": qubit_ms, "marker_ms": marker_ms, "lw": lw,
        "font": max(9.0 * zoom, 0.45 * qubit_ms),
        # outermost drawn thing is the hover ring around an edge qubit
        "margin_px": (qubit_ms + st.HOVER_RING_EXTRA + st.HOVER_RING_MEW) / 2 * ppt + PAD_PX,
        "qubit_hit_px": qubit_r_pt * ppt + QUBIT_SLACK_PX,
        "marker_hit_px": max(marker_ms / 2 * 2 ** 0.5 * ppt, MIN_TARGET_PX / 2),
        "edge_hit_px": lw * ppt / 2 + 6,
    }


def fit_scale(topo: dict, width: float, height: Optional[float], dpi: float) -> tuple:
    """(scale px/unit, sizes) that fit the lattice into width x height pixels, markers
    included. Sizes depend on scale and the padding on sizes, so iterate; the final
    scale is always computed with the padding of the sizes that get drawn, so the fit
    is exact for what is on screen. ``height=None`` fits to the width alone."""
    pos = list(topo["qubits"].values())
    xs, ys = [p[0] for p in pos], [p[1] for p in pos]
    span_x, span_y = max(max(xs) - min(xs), 1e-9), max(max(ys) - min(ys), 1e-9)
    scale = 1.0
    sizes = lattice_sizes(topo, scale, dpi)
    for _ in range(6):
        m = sizes["margin_px"]
        sx = (width - 2 * m) / span_x
        scale = max(min(sx, (height - 2 * m) / span_y) if height else sx, 1e-6)
        new = lattice_sizes(topo, scale, dpi)
        if abs(new["margin_px"] - m) < 0.25:
            break
        sizes = new
    # one last pass with the drawn sizes' own margin -> clip-safe by construction
    m = sizes["margin_px"]
    sx = (width - 2 * m) / span_x
    scale = max(min(sx, (height - 2 * m) / span_y) if height else sx, 1e-6)
    return scale, sizes


def height_for_width(topo: dict, width: float, dpi: float) -> int:
    """Pixel height that holds the lattice at full width, no empty bands."""
    if not topo["qubits"]:
        return 120
    scale, sizes = fit_scale(topo, width, None, dpi)
    ys = [p[1] for p in topo["qubits"].values()]
    return int((max(ys) - min(ys)) * scale + 2 * sizes["margin_px"] + 1)


class LatticeSelector(QWidget):
    """Clickable lattice: click a qubit to toggle it; click a coupler square, a rung
    square, or an edge to toggle that pair. The two kinds of square differ only by colour.

    Markers scale with the width the widget gets (see lattice_sizes), and the widget's
    height follows its width, so a wider left column means a bigger, easier diagram.
    """

    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.topo: dict = {"qubits": {}, "couplers": {}, "edges": [], "rungs": {}}
        self._selected: set[str] = set()
        self.sizes: dict = {}
        self.scale = 1.0
        self.canvas = MplCanvas(self, height=1.5)
        self.canvas.fig.set_tight_layout(False)
        self.canvas.fig.subplots_adjust(0, 0, 1, 1)   # axes == figure: limits own the fit
        self.canvas.mpl_connect("button_press_event", self._on_click)
        self.canvas.mpl_connect("resize_event", lambda _e: self.redraw())
        # Hover: pointing hand + one ring artist on whatever a click would select.
        self._hover = None
        self._ring = None
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("figure_leave_event", lambda _e: self._set_hover(None))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

    # Height follows width (the diagram is ~3:1), freeing vertical room for the filters.
    # Qt's own height-for-width is NOT honoured for a widget nested in a QSplitter column
    # (measured: the layout squeezed the canvas to 0 px), so the height is pinned
    # explicitly -- deferred to after the current resize, because resizing yourself from
    # inside resizeEvent left the inner canvas at its old size.
    def heightForWidth(self, width: int) -> int:
        return height_for_width(self.topo, width, self.canvas.fig.dpi)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            QTimer.singleShot(0, self.sync_height)

    def sync_height(self) -> None:
        want = self.heightForWidth(self.width())
        if abs(self.height() - want) > 1:
            self.setFixedHeight(want)

    def set_device(self, device: str) -> None:
        self.topo = device_topology(device)
        self._selected &= set(self.topo["qubits"])
        self.sync_height()                        # new topology -> new height
        self.redraw()
        self.selection_changed.emit(self.selected())

    def selected(self) -> list[int]:
        """Selected qubits as chip numbers, via the index's shared normalizer."""
        return sorted(n for n in (dx.qubit_label(q) for q in self._selected) if n is not None)

    def set_selected(self, names) -> None:
        self._selected = set(names) & set(self.topo["qubits"])
        self.redraw()
        self.selection_changed.emit(self.selected())

    def preset(self, count: Optional[int]) -> None:
        """'All' (count=None), 'Left N' (count=N) or 'Unselect' (count=0)."""
        names = sorted(self.topo["qubits"], key=lambda n: int(n[1:]))
        self.set_selected(names if count is None else names[:count])

    def fit_limits(self) -> float:
        """Recompute scale + marker sizes for the current canvas, set equal-scale limits
        so every marker sits inside the axes; returns pixels per data unit."""
        ax, pos = self.canvas.ax, list(self.topo["qubits"].values())
        bbox = ax.get_window_extent()
        w, h = max(bbox.width, 1.0), max(bbox.height, 1.0)
        self.scale, self.sizes = fit_scale(self.topo, w, h, self.canvas.fig.dpi)
        xs, ys = [p[0] for p in pos], [p[1] for p in pos]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        ax.set_xlim(cx - w / (2 * self.scale), cx + w / (2 * self.scale))
        ax.set_ylim(cy - h / (2 * self.scale), cy + h / (2 * self.scale))
        return self.scale

    def pick(self, x: float, y: float) -> Optional[tuple]:
        """hit_test with pick radii that track the DRAWN marker sizes (pixels -> data)."""
        s, z = self.scale, self.sizes
        return hit_test(self.topo, x, y, node_r=z["qubit_hit_px"] / s,
                        edge_tol=z["edge_hit_px"] / s, marker_r=z["marker_hit_px"] / s)

    def _on_motion(self, event) -> None:
        if event.xdata is None or event.ydata is None or not self.sizes:
            self._set_hover(None)
            return
        self._set_hover(self.pick(event.xdata, event.ydata))

    def _set_hover(self, hit) -> None:
        """Move the single overlay ring; only redraws when the target changes."""
        if hit == self._hover:
            return
        self._hover = hit
        if hit is None:
            self.canvas.unsetCursor()
        else:
            self.canvas.setCursor(Qt.PointingHandCursor)
        self._place_ring()
        self.canvas.draw_idle()

    def _place_ring(self) -> None:
        ring, hit, z = self._ring, self._hover, self.sizes
        if ring is None:
            return
        if hit is None:
            ring.set_visible(False)
            return
        kind, target = hit
        q = self.topo["qubits"]
        if kind == "qubit":
            (x, y), ms = q[target], z["qubit_ms"]
        else:
            (x1, y1), (x2, y2) = q[target[0]], q[target[1]]
            x, y, ms = (x1 + x2) / 2, (y1 + y2) / 2, z["marker_ms"] * 2 ** 0.5
        ring.set_data([x], [y])
        ring.set_markersize(ms + st.HOVER_RING_EXTRA)
        ring.set_visible(True)

    def _on_click(self, event) -> None:
        if event.xdata is None or event.ydata is None or not self.topo["qubits"]:
            return
        self.fit_limits()
        hit = self.pick(event.xdata, event.ydata)
        if hit is None:
            return
        kind, target = hit
        names = {target} if kind == "qubit" else set(target)
        # A pair toggles as a unit: deselect only when both ends are already on.
        if names <= self._selected:
            self._selected -= names
        else:
            self._selected |= names
        self.redraw()
        self.selection_changed.emit(self.selected())

    def redraw(self) -> None:
        ax = self.canvas.ax
        ax.clear()
        ax.axis("off")
        self._ring = None
        qubits, couplers = self.topo["qubits"], self.topo["couplers"]
        if not qubits:
            self.canvas.draw_idle()
            return
        self.fit_limits()                         # sizes first: they depend on the width
        z, sel = self.sizes, self._selected
        # z-order: lines (1) < coupler / rung squares (5) < qubits (10) < labels (11);
        # a pair marker is colour-filled only when BOTH adjacent qubits are selected;
        # clip_on=False everywhere so nothing is cut at the axes edge.
        for a, b in self.topo["edges"]:
            (x1, y1), (x2, y2) = qubits[a], qubits[b]
            ax.plot([x1, x2], [y1, y2], color=st.EDGE_LINE, lw=z["lw"], zorder=1,
                    solid_capstyle="round", clip_on=False)
        for name, (px, py) in couplers.items():
            k = int(name[1:])
            on = {f"Q{k}", f"Q{k + 2}"} <= sel
            ax.plot([px], [py], marker="s", ms=z["marker_ms"], zorder=5, clip_on=False,
                    mfc=st.COUPLER["face_on" if on else "face"], mec=st.COUPLER["edge"],
                    mew=st.PAIR_MEW_ON if on else st.PAIR_MEW)
        for (a, b), (px, py) in self.topo.get("rungs", {}).items():
            on = {a, b} <= sel
            ax.plot([px], [py], marker="s", ms=z["marker_ms"], zorder=5, clip_on=False,
                    mfc=st.RUNG["face_on" if on else "face"], mec=st.RUNG["edge"],
                    mew=st.PAIR_MEW_ON if on else st.PAIR_MEW)
        # Digits drop by a fraction of the marker diameter (points -> inches), so the
        # correction scales with the marker instead of being a fixed pixel count.
        drop = ScaledTranslation(0, -st.DIGIT_DROP_FRAC * z["qubit_ms"] / 72,
                                 self.canvas.fig.dpi_scale_trans)
        for name, (px, py) in qubits.items():
            on = name in sel
            ax.plot([px], [py], marker="o", ms=z["qubit_ms"], zorder=10, clip_on=False,
                    mfc=st.QUBIT["face_on" if on else "face"],
                    mec=st.QUBIT["edge"], mew=2.0 if on else 1.0)
            ax.text(px, py, name[1:], ha="center", va="center", fontsize=z["font"],
                    zorder=11, color=st.QUBIT["text_on" if on else "text"], clip_on=False,
                    transform=ax.transData + drop)
        (self._ring,) = ax.plot([], [], marker="o", mfc="none", mec=st.ACCENT,
                                mew=st.HOVER_RING_MEW, zorder=12, clip_on=False,
                                visible=False, linestyle="none")
        self._place_ring()
        self.canvas.draw_idle()
