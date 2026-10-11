"""Every visual constant of the viewer, and ``apply_style(app, scale)``.

Tune sizes here, or zoom at runtime with Ctrl+= / Ctrl+- / Ctrl+0 (0.8x to 2.0x, kept in
QSettings). No styling literals live in browser.py or lattice.py. Fonts are resolved from
what is installed (no bundled or downloaded fonts); ``resolved_families()`` reports which.
"""
from __future__ import annotations

import weakref
from typing import Optional

from PyQt5.QtGui import QFont, QFontDatabase

# --- typefaces: first installed family wins --------------------------------------------
UI_FAMILIES = ("Segoe UI", "Calibri", "Arial", "Helvetica", "DejaVu Sans")
MONO_FAMILIES = ("Consolas", "Cascadia Mono", "Courier New", "DejaVu Sans Mono", "Monospace")
BASE_PT = 11.0               # Qt's default is 9 pt
# On Windows the platform theme gives these classes their OWN 9 pt font, which a plain
# QApplication.setFont() does not override (measured: table + header stayed at 9 pt).
UI_FONT_CLASSES = ("QAbstractItemView", "QHeaderView", "QTabBar", "QMenu", "QMenuBar",
                   "QStatusBar", "QToolTip")
MONO_PT = 10.5

# --- click targets (pixels at scale 1.0) ------------------------------------------------
CONTROL_MIN_H = 32           # buttons, combos, line edits, date edits
ROW_H = 28                   # table rows
INDICATOR = 18               # checkbox / radio indicator
TAB_PAD = (6, 14)            # tab padding (vertical, horizontal)
SPLITTER_HANDLE = 8

# --- zoom -------------------------------------------------------------------------------
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, ZOOM_DEFAULT = 0.8, 2.0, 0.1, 1.0
SETTING_ZOOM = "zoom"

# --- colours: the existing lattice palette plus ONE neutral accent ---------------------
ACCENT = "#2f6fb5"
QUBIT = {"face": "white", "face_on": "indianred", "edge": "maroon",
         "text": "maroon", "text_on": "white"}
# Pair markers follow the qubits' convention: white until BOTH adjacent qubits are selected,
# then colour-filled. The rung edge is a darker green than its mint fill, otherwise the
# unfilled (white) triangle would have an almost invisible outline.
COUPLER = {"face": "white", "face_on": "cornflowerblue", "edge": "darkblue"}
RUNG = {"face": "white", "face_on": "#ADEBB3", "edge": "#3f9c55"}
PAIR_MEW, PAIR_MEW_ON = 1.8, 2.2   # marker edge widths, points
EDGE_LINE = "0.65"
HOVER_RING_MEW = 3.0         # points
# Qubit digits are drawn this fraction of the marker DIAMETER below the centre:
# va="center" centres the text's layout box, which includes descender space digits never
# use, so they otherwise sit high by ~5% of the diameter at every size (measured).
DIGIT_DROP_FRAC = 0.05
HOVER_RING_EXTRA = 8.0       # ring diameter beyond the hovered marker, points
HEADER_BG, GRID_LINE, ALT_ROW, HANDLE_BG = "#f1f3f5", "#cfd4da", "#f6f8fa", "#d5dbe1"


def clamp_zoom(scale: float) -> float:
    """Clamp to [ZOOM_MIN, ZOOM_MAX] on the ZOOM_STEP grid."""
    return round(min(ZOOM_MAX, max(ZOOM_MIN, round(scale / ZOOM_STEP) * ZOOM_STEP)), 1)


def resolve_family(candidates, fallback: QFontDatabase.SystemFont = QFontDatabase.GeneralFont) -> str:
    """First installed family from ``candidates``, else the platform's own choice."""
    installed = set(QFontDatabase().families())
    return next((f for f in candidates if f in installed),
                QFontDatabase.systemFont(fallback).family())


def resolved_families() -> dict:
    return {"ui": resolve_family(UI_FAMILIES),
            "mono": resolve_family(MONO_FAMILIES, QFontDatabase.FixedFont)}


def ui_font(scale: float = 1.0) -> QFont:
    font = QFont(resolve_family(UI_FAMILIES))
    font.setPointSizeF(BASE_PT * scale)
    return font


def mono_font(scale: float = 1.0) -> QFont:
    font = QFont(resolve_family(MONO_FAMILIES, QFontDatabase.FixedFont))
    font.setPointSizeF(MONO_PT * scale)
    font.setStyleHint(QFont.Monospace)
    return font


def stylesheet(scale: float = 1.0) -> str:
    # min-height is the CONTENT height: total = min-height + 2 * padding + 2 px border,
    # so derive it from the target total rather than guessing.
    px = lambda v: f"{round(v * scale)}px"
    pad_v, pad_h = TAB_PAD
    # Item views and headers must name their font HERE: once a stylesheet rule matches
    # them, Qt resolves their font from the platform class font (9 pt on Windows) and
    # ignores app.setFont -- measured, the table stayed at 9 pt without this.
    font = f'font-family: "{resolve_family(UI_FAMILIES)}"; font-size: {BASE_PT * scale:.1f}pt;'
    return f"""
    QAbstractItemView, QHeaderView {{ {font} }}
    QPushButton, QComboBox, QLineEdit, QDateEdit, QSpinBox, QDoubleSpinBox {{
        min-height: {control_min_height(scale) - 2 * round(3 * scale) - 2}px;
        padding: {px(3)} {px(8)};
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: {px(INDICATOR)}; height: {px(INDICATOR)};
    }}
    QTabBar::tab {{ padding: {px(pad_v)} {px(pad_h)}; }}
    QSplitter::handle {{ background: {HANDLE_BG}; }}
    QSplitter::handle:horizontal {{ width: {px(SPLITTER_HANDLE)}; }}
    QSplitter::handle:vertical {{ height: {px(SPLITTER_HANDLE)}; }}
    QHeaderView::section {{
        font-weight: bold; padding: {px(4)} {px(8)}; border: none;
        border-bottom: 1px solid {GRID_LINE}; background: {HEADER_BG};
    }}
    QTableView {{ alternate-background-color: {ALT_ROW};
                  selection-background-color: {ACCENT}; }}
    """


# Widgets whose font/size is set explicitly, re-applied on every zoom. Keyed by id and
# unregistered from Qt's own `destroyed` signal: a WeakSet is NOT enough, because Qt
# deletes child widgets with their parent while the Python wrapper can live on, and
# touching such a wrapper was an access violation inside apply_style (or a RuntimeError
# once deletion is deterministic).
_MONO: dict = {}
_TABLES: dict = {}


def _register(registry: dict, widget) -> None:
    key = id(widget)
    registry[key] = weakref.ref(widget)
    widget.destroyed.connect(lambda *_a, k=key, r=registry: r.pop(k, None))


def _live(registry: dict) -> list:
    """Registered widgets whose C++ object still exists."""
    from PyQt5 import sip
    out = []
    for key, ref in list(registry.items()):
        widget = ref()
        if widget is None or sip.isdeleted(widget):
            registry.pop(key, None)
        else:
            out.append(widget)
    return out
_STATE = {"scale": ZOOM_DEFAULT}


def current_scale() -> float:
    return _STATE["scale"]


def control_min_height(scale: Optional[float] = None) -> int:
    return round(CONTROL_MIN_H * (current_scale() if scale is None else scale))


def row_height(scale: Optional[float] = None) -> int:
    return round(ROW_H * (current_scale() if scale is None else scale))


def make_mono(widget):
    """Monospace for panes where alignment and copy-paste matter."""
    _register(_MONO, widget)
    widget.setFont(mono_font(current_scale()))
    return widget


def style_table(table):
    """Alternating rows, no grid, full-row single selection, fixed comfortable rows."""
    from PyQt5.QtWidgets import QAbstractItemView, QHeaderView
    _register(_TABLES, table)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.horizontalHeader().setHighlightSections(False)
    rows = table.verticalHeader()
    rows.setSectionResizeMode(QHeaderView.Fixed)
    rows.setDefaultSectionSize(row_height())
    return table


def apply_style(app, scale: float = ZOOM_DEFAULT) -> float:
    """(Re)apply fonts, sizes and colours at ``scale``; returns the clamped scale."""
    scale = clamp_zoom(scale)
    _STATE["scale"] = scale
    font = ui_font(scale)
    app.setFont(font)
    for cls in UI_FONT_CLASSES:
        app.setFont(font, cls)
    app.setStyleSheet(stylesheet(scale))
    for widget in _live(_MONO):
        widget.setFont(mono_font(scale))
    for table in _live(_TABLES):
        table.verticalHeader().setDefaultSectionSize(row_height(scale))
    return scale
