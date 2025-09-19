"""
================
CustomMenuBar.py
================
The custom menu bar for the GUI.

Contains platform-specific window controls (macOS traffic lights or Windows-style buttons),
as well as run, stop, load, progress bar.
"""

import platform
from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QSizePolicy,
    QLabel,
    QProgressBar,
    QSpacerItem,
    QPushButton
)
from PyQt5.QtCore import Qt, QSize, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers

class CustomMenuBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(45)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_StyledBackground, True)

        # Store mouse position for dragging
        self.mouse_pos = QPoint()

        menu_layout = QHBoxLayout(self)
        menu_layout.setContentsMargins(10, 5, 10, 0)
        menu_layout.setSpacing(8)

        # Create platform-specific window controls
        self.is_macos = platform.system() == "Darwin"
        
        # Min/Max/Close window controllers
        if self.is_macos:
            # macOS traffic light style
            self.btn_close = Helpers.create_button("", "btn_close", True, self)
            self.btn_close.setFixedSize(QSize(11, 11))
            self.btn_minimize = Helpers.create_button("", "btn_minimize", True, self)
            self.btn_minimize.setFixedSize(QSize(11, 11))
            self.btn_fullscreen = Helpers.create_button("", "btn_fullscreen", True, self)
            self.btn_fullscreen.setFixedSize(QSize(11, 11))
        else:
            # Windows style
            self.btn_minimize = Helpers.create_button("", "win_btn_minimize", True, self)
            self.btn_minimize.setFixedSize(QSize(16, 16))
            self.btn_fullscreen = Helpers.create_button("", "win_btn_fullscreen", True, self)
            self.btn_fullscreen.setFixedSize(QSize(16, 16))
            self.btn_close = Helpers.create_button("", "win_btn_close", True, self)
            self.btn_close.setFixedSize(QSize(16, 16))
        
        # Actual important buttons
        self.start_experiment_button = Helpers.create_button("", "start_experiment", False, self)
        self.start_experiment_button.setToolTip("Run")
        self.start_experiment_button.setFixedWidth(35)
        self.stop_experiment_button = Helpers.create_button("️", "stop_experiment", False, self)
        self.stop_experiment_button.setToolTip("Stop")
        self.stop_experiment_button.setFixedWidth(35)
        self.soc_status_label = QLabel('✖ Soc Disconnected', self)
        self.soc_status_label.setObjectName("soc_status_label")
        self.experiment_progress_bar = QProgressBar(self, value=0)
        self.experiment_progress_bar.setFixedHeight(15)
        self.experiment_progress_bar.setObjectName("experiment_progress_bar")
        self.experiment_progress_bar.setTextVisible(False)
        self.experiment_progress_bar_label = QLabel(self)
        self.experiment_progress_bar_label.setObjectName("experiment_progress_bar_label")
        self.load_data_button = Helpers.create_button("Load Data", "load_data_button", True, self)
        self.load_experiment_button = Helpers.create_button("Extract Experiment", "load_experiment_button", True, self)

        self.documentation_button = Helpers.create_button("", "documentation", True, self)
        self.documentation_button.setToolTip("Documentation")
        self.documentation_button.setObjectName("documentation_button")
        self.settings_button = Helpers.create_button("", "settings_button", True, self, False)
        self.settings_button.setObjectName("settings_button")

        spacerItem = QSpacerItem(30, 40, QSizePolicy.Fixed, QSizePolicy.Fixed)  # spacer

        if self.is_macos:  # macOS buttons appear on left
            menu_layout.addWidget(self.btn_close)
            menu_layout.addWidget(self.btn_minimize)
            menu_layout.addWidget(self.btn_fullscreen)
            menu_layout.addItem(spacerItem)

        menu_layout.addWidget(self.start_experiment_button)
        menu_layout.addWidget(self.stop_experiment_button)
        menu_layout.addWidget(self.soc_status_label)
        menu_layout.addWidget(self.experiment_progress_bar)
        menu_layout.addWidget(self.experiment_progress_bar_label)
        menu_layout.addWidget(self.load_data_button)
        menu_layout.addWidget(self.load_experiment_button)
        menu_layout.addWidget(self.documentation_button)
        menu_layout.addWidget(self.settings_button)

        if not self.is_macos:  # Windows buttons appear on right
            menu_layout.addItem(spacerItem)
            menu_layout.addWidget(self.btn_minimize)
            menu_layout.addWidget(self.btn_fullscreen)
            menu_layout.addWidget(self.btn_close)
        
        self.setup_signals()

    def setup_signals(self):
        # Menu Bar
        self.btn_close.clicked.connect(self.parent.close)
        self.btn_minimize.clicked.connect(self.minimize_window)
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        pass

    def minimize_window(self):
        if self.is_macos:
            self.parent.hide()
        else:
            self.parent.showMinimized()

    def toggle_fullscreen(self):
        if self.is_macos:
            if self.parent.isFullScreen():
                self.parent.showMinimized()
                self.btn_minimize.setEnabled(True)
                self.parent.setAttribute(Qt.WA_TranslucentBackground, True)
                self.parent.setStyleSheet("QMainWindow{background: transparent; border-radius: 10px}")
                self.setStyleSheet("QWidget#custom_menu_bar{border-top-left-radius: 10px; border-top-right-radius: 10px;}")
            else:
                self.parent.showFullScreen()
                self.btn_minimize.setEnabled(False)
                self.setStyleSheet("QWidget#custom_menu_bar{border-top-left-radius: 0px; border-top-right-radius: 0px;}")
        else:
            if self.parent.isMaximized():
                self.parent.showNormal()
            else:
                self.parent.showMaximized()

        self.parent.apply_settings()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.mouse_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            delta = QPoint(event.globalPos() - self.mouse_pos)
            self.parent.move(self.parent.x() + delta.x(), self.parent.y() + delta.y())
            self.mouse_pos = event.globalPos()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw top corners rounded
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 10, 10)
