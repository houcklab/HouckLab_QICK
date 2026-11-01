"""Look and feel: Desq's light palette (Desq_GUI/Desq.py apply_settings and assets/style.qss)
applied to Bob's widgets, the canvas colors, and the qubit lane colors."""
from __future__ import annotations

from PyQt5.QtGui import QColor, QFont, QFontDatabase

from ..core.colors import QUBIT_COLORS  # noqa: F401  (re-exported for the panels)

# Values copied from Desq.apply_settings so the two apps look like one family.
COLORS = {
    "bg": "#FFFFFF", "bg_accent": "#F0F1F2", "text": "#000000", "text_muted": "#6B6B6B",
    "border": "#EAEBE9", "border_dark": "#C4C4C3", "menu_bg": "#2B2B2F", "menu_text": "#FFFFFF",
    "tree_base": "#F0F1F2", "tree_alt": "#FFFFFF", "tree_header": "#E0E1E2",
    "button": "#FFFFFF", "button_text": "#000000", "button_hover_border": "#B6B6B6",
    "button_pressed": "#F0F0F0", "button_disabled": "#ECEEF1", "button_disabled_text": "#B6B6B6",
    "connect": "#6495ED", "run": "#3CB371", "run_hover": "#64DB99", "stop": "#CD5C5C",
    "menu_button": "#404044", "menu_button_hover": "#57575A",
    "tab_bg": "#F6F6F6", "tab_bar_bg": "#F7F8FA", "tab_border": "#C4C4C3", "tab_accent": "#8AC6F2",
    "code_label": "#878787", "simulated": "#D9902F",
}

# Canvas colors. Acts get quiet tints; one accent (Desq's tab blue) marks selection.
CANVAS = {
    "bg": "#FFFFFF", "lane_alt": "#FAFAFB", "grid": "#EAEBE9", "text": "#1E1E22", "muted": "#7A7A80",
    "act": {"prep": "#EEF4FB", "dynamics": "#F4F0FA", "readout": "#EEF7F1"},
    "act_text": {"prep": "#2F5D8A", "dynamics": "#5B3F8C", "readout": "#2E6B45"},
    "chip": "#FFFFFF", "chip_border": "#C4C4C3", "select": "#3B8FD9", "error": "#CD5C5C",
    "warning": "#D9902F", "drop": "#3B8FD9", "measure": "#2E6B45", "badge_ref": "#7C6BC4",
    "badge_sweep": "#D9692F", "pulse": {"PiPulse": "#3B6FB6", "Pi2Pulse": "#3A9A8B", "Drive": "#8A6D3B"},
}



def qubit_color(q: int) -> QColor:
    return QColor(QUBIT_COLORS[(int(q) - 1) % len(QUBIT_COLORS)])


def ui_font(size: int = 13) -> QFont:
    fams = set(QFontDatabase().families())
    for fam in ("Inter", ".AppleSystemUIFont", "SF Pro Text", "Segoe UI", "Helvetica Neue"):
        if fam in fams:
            f = QFont(fam)
            break
    else:
        f = QFont()
    f.setPixelSize(size)
    return f


def stylesheet(font_px: int = 13) -> str:
    c = COLORS
    small, medium, large = font_px - 2, font_px - 1, font_px + 2
    return f"""
QWidget {{ font-size: {font_px}px; color: {c['text']}; }}
QMainWindow, QWidget#bob_root {{ background: {c['bg']}; }}
QWidget#panel {{ background: {c['bg']}; }}
QWidget#topbar {{ background: {c['menu_bg']}; }}
QWidget#topbar QLabel {{ color: {c['menu_text']}; }}
QLabel#app_title {{ font-size: {large + 2}px; font-weight: 600; color: {c['menu_text']}; }}
QLabel#app_subtitle {{ font-size: {small}px; color: #A9A9B2; }}
QLabel#doc_title {{ font-size: {font_px}px; color: #D8D8DE; }}
QWidget#topbar QLineEdit#title_edit {{ background: {c['menu_button']}; color: white; border: 1px solid {c['connect']};
    border-radius: 5px; padding: 2px 6px; selection-background-color: {c['connect']}; }}
QWidget#topbar QPushButton {{ background: {c['menu_button']}; color: white; border: none; border-radius: 5px;
    padding: 4px 10px; }}
QWidget#topbar QPushButton:hover {{ background: {c['menu_button_hover']}; }}
QWidget#topbar QPushButton:disabled {{ background: #34343A; color: #77777E; }}
QWidget#topbar QPushButton#icon_button {{ background: transparent; padding: 4px 6px; }}
QWidget#topbar QPushButton#icon_button:hover {{ background: {c['menu_button_hover']}; }}
QWidget#topbar QPushButton#dry_run_button {{ background: {c['connect']}; }}
QWidget#topbar QPushButton#dry_run_button:hover {{ background: #7FA8F2; }}
QWidget#topbar QPushButton#run_button {{ background: {c['run']}; }}
QWidget#topbar QPushButton#run_button:hover {{ background: {c['run_hover']}; }}
QWidget#topbar QPushButton#run_button:disabled {{ background: #2F5E44; color: #9FC8AF; }}
QWidget#topbar QPushButton#simulate_button:checked {{ background: {c['simulated']}; color: white; }}
QWidget#topbar QPushButton#simulate_button:checked:hover {{ background: #E8A54A; }}
QWidget#topbar QComboBox {{ combobox-popup: 0; background: {c['menu_button']}; color: white; border: none; border-radius: 5px;
    padding: 3px 10px; }}
QWidget#topbar QComboBox QAbstractItemView {{ background: {c['menu_button']}; color: white; }}
QLabel#status_pill {{ border-radius: 9px; padding: 2px 10px; font-size: {small}px; font-weight: 600; }}

QLabel#section_title {{ font-size: {medium}px; background: {c['bg_accent']}; border-radius: 5px; padding: 3px 8px;
    font-weight: 600; }}
QLabel#muted, QLabel#field_hint {{ color: {c['text_muted']}; font-size: {small}px; }}
QLabel#field_error {{ color: {c['stop']}; font-size: {small}px; }}
QLabel#field_label {{ font-weight: 500; }}
QLabel#block_title {{ font-size: {large}px; font-weight: 600; }}

QPushButton {{ background: {c['button']}; color: {c['button_text']}; padding: 3px 12px; border: 1px solid {c['border']};
    border-radius: 5px; }}
QPushButton:hover {{ border: 1px solid {c['button_hover_border']}; }}
QPushButton:pressed {{ background: {c['button_pressed']}; }}
QPushButton:disabled {{ background: {c['button_disabled']}; color: {c['button_disabled_text']}; border: none; }}
QToolButton {{ background: transparent; border: none; border-radius: 4px; padding: 3px; }}
QToolButton:hover {{ background: {c['bg_accent']}; }}
QLineEdit#ref_path {{ font-size: {small}px; }}
QLineEdit#vec_cell, QLineEdit#override {{ font-size: {small}px; padding: 1px 3px; }}
QPushButton#flat {{ border: none; background: transparent; padding: 2px 6px; color: {c['text_muted']}; }}
QPushButton#flat:hover {{ color: {c['text']}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{ background: {c['bg']}; border: 1px solid {c['border_dark']};
    border-radius: 5px; padding: 2px 5px; selection-background-color: {c['tab_accent']}; }}
QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border: 1px solid {c['connect']}; }}
QLineEdit#override {{ font-weight: 600; border: 1px solid {c['connect']}; }}
QLineEdit#bad {{ border: 1px solid {c['stop']}; }}
QComboBox {{ combobox-popup: 0; background: {c['button']}; border: 1px solid {c['border_dark']}; color: {c['button_text']};
    padding: 2px 10px; border-radius: 5px; }}
QComboBox:hover {{ border: 1px solid {c['button_hover_border']}; }}
QComboBox QAbstractItemView {{ background: {c['bg_accent']}; selection-background-color: {c['tab_accent']};
    border: 1px solid {c['border_dark']}; padding: 2px; outline: none; }}
QComboBox QAbstractItemView::item {{ min-height: 22px; padding: 0px 6px; }}
QComboBox#source_combo {{ font-size: {small}px; padding: 1px 8px; background: {c['bg_accent']}; border: none; }}

QTabWidget::pane {{ background: {c['bg']}; border: 1px solid {c['border']}; border-top: none; }}
QTabWidget::tab-bar {{ alignment: left; }}
QTabBar::tab {{ background: {c['tab_bg']}; color: {c['text']}; padding: 4px 14px; border: 1px solid {c['tab_border']};
    border-bottom: none; font-size: {small + 1}px; min-width: 90px; }}
QTabBar::tab:selected {{ background: {c['bg']}; border-bottom: 3px solid {c['tab_accent']}; }}

QTreeWidget, QListWidget, QTableWidget {{ background: {c['tree_base']}; alternate-background-color: {c['tree_alt']};
    border: 1px solid {c['border_dark']}; border-radius: 4px; }}
QTreeWidget::item, QListWidget::item {{ padding: 2px 2px; }}
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{
    background: {c['tab_accent']}; color: {c['text']}; }}
QHeaderView::section {{ background: {c['tree_header']}; border: none; padding: 3px 6px;
    border-bottom: 1px solid {c['border']}; border-right: 1px solid {c['border']}; }}
QListWidget#palette {{ background: {c['bg']}; border: none; }}
QListWidget#palette::item {{ border: 1px solid {c['border']}; border-radius: 6px; margin: 2px 4px; padding: 0px; }}
QListWidget#palette::item:hover {{ border: 1px solid {c['button_hover_border']}; background: {c['bg_accent']}; }}
QListWidget#palette::item:selected {{ background: {c['bg_accent']}; border: 1px solid {c['tab_accent']}; }}

QScrollArea {{ background: {c['bg']}; border: none; }}
QFrame#run_track {{ background: {c['tab_bar_bg']}; border: 1px solid {c['border_dark']}; border-radius: 9px; }}
QScrollArea#run_history, QWidget#run_history_body {{ background: transparent; border: none; }}
QScrollArea#run_history QScrollBar:horizontal {{ height: 6px; background: transparent; margin: 0px 8px 1px 8px; }}
QScrollArea#run_history QScrollBar::handle:horizontal {{ background: {c['border_dark']}; border-radius: 3px;
    min-width: 30px; }}
QScrollArea#run_history QScrollBar::add-line:horizontal, QScrollArea#run_history QScrollBar::sub-line:horizontal {{
    width: 0px; }}
QScrollArea#run_history QScrollBar::add-page:horizontal, QScrollArea#run_history QScrollBar::sub-page:horizontal {{
    background: transparent; }}
QPushButton#run_chip {{ background: {c['bg']}; border: 1px solid {c['border_dark']}; border-radius: 8px;
    padding: 2px 12px; text-align: left; font-size: {small}px; color: {c['text']}; }}
QPushButton#run_chip:hover {{ background: {c['bg_accent']}; border: 1px solid {c['button_hover_border']}; }}
QPushButton#run_chip:checked {{ background: #EAF4FD; border: 1px solid {c['connect']}; }}
QPushButton#stop_button {{ color: {c['stop']}; border: 1px solid {c['stop']}; }}
QPushButton#stop_button:hover {{ background: #FBEDED; }}
QWidget#inspector_body {{ background: {c['bg']}; }}
QFrame#field_card {{ background: {c['bg']}; border-bottom: 1px solid {c['border']}; }}
QFrame#hline {{ background: {c['border']}; max-height: 1px; min-height: 1px; }}
QGroupBox {{ background: {c['bg_accent']}; border: 1px solid {c['border']}; border-radius: 5px;
    margin-top: {font_px}px; padding: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 4px; }}
QSplitter::handle {{ background: {c['border']}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border-radius: 4px; border: 1px solid {c['border_dark']};
    background: {c['bg']}; }}
QCheckBox::indicator:checked {{ background: {c['connect']}; border: 1px solid {c['connect']}; }}
QToolTip {{ background: {c['bg_accent']}; color: {c['text']}; border: 1px solid {c['border_dark']}; padding: 4px; }}
QStatusBar {{ background: {c['bg_accent']}; color: {c['text_muted']}; font-size: {small - 1}px;
    border-top: 1px solid {c['border']}; padding: 0px 6px; }}
QStatusBar::item {{ border: none; }}
QMenu {{ background: {c['bg_accent']}; border: 1px solid {c['border_dark']}; padding: 4px; }}
QMenu::item {{ padding: 4px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['tab_accent']}; color: {c['text']}; }}
QSlider::groove:horizontal {{ height: 4px; background: {c['border_dark']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {c['connect']}; width: 14px; margin: -6px 0; border-radius: 7px; }}
"""


def light_palette():
    """Bob's light colours for everything a stylesheet doesn't reach (native dialogs aside), so macOS
    dark mode or a Windows high-contrast theme can't leave white text on a white panel."""
    from PyQt5.QtGui import QPalette
    c = COLORS
    pal = QPalette()
    for role, color in ((QPalette.Window, c["bg"]), (QPalette.WindowText, c["text"]), (QPalette.Base, c["bg"]),
                        (QPalette.AlternateBase, c["bg_accent"]), (QPalette.Text, c["text"]),
                        (QPalette.Button, c["button"]), (QPalette.ButtonText, c["button_text"]),
                        (QPalette.ToolTipBase, c["bg_accent"]), (QPalette.ToolTipText, c["text"]),
                        (QPalette.Highlight, c["tab_accent"]), (QPalette.HighlightedText, c["text"]),
                        (QPalette.Link, c["connect"]), (QPalette.PlaceholderText, c["text_muted"]),
                        (QPalette.BrightText, c["stop"])):
        pal.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(c["button_disabled_text"]))
    return pal


def apply_app_look(app) -> None:
    """The same look on macOS, Windows and Linux: Qt's Fusion style (the native macOS and Windows
    styles ignore parts of a stylesheet), Bob's light palette, and the stylesheet. Only for Bob's
    own window; when Bob is embedded (Desq), the host's application look is left alone."""
    if app.property("bob_look") == "Fusion":
        return                                   # already done for this application
    from PyQt5.QtWidgets import QStyleFactory
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setProperty("bob_look", "Fusion")      # app.style() reports the stylesheet wrapper, not Fusion
    app.setPalette(light_palette())
    app.setStyleSheet(stylesheet())


def shortcut_text(keys: str) -> str:
    """A shortcut as this platform writes it: "Ctrl+D" on Windows and Linux, "⌘D" on macOS."""
    from PyQt5.QtGui import QKeySequence
    return QKeySequence(keys).toString(QKeySequence.NativeText)

