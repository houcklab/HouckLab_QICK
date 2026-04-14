"""
================
CustomMenuBar.py
================

Custom menu bar widget for the Desq GUI application.

This module provides a platform-aware custom menu bar that includes:

- Platform-specific window controls (macOS traffic lights or Windows-style buttons)
- Experiment control buttons (run, stop)
- Progress bar for experiment execution
- Data and experiment loading buttons
- Documentation and settings access

The menu bar also handles window dragging functionality for frameless windows.

.. note::
    This widget is designed to replace the native window title bar in a
    frameless window configuration.

.. seealso::
    :mod:`Helpers` for button creation utilities
"""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from PyQt5.QtGui import QMouseEvent, QPaintEvent
    from PyQt5.QtWidgets import QMainWindow


class CustomMenuBar(QWidget):
    """
    A custom menu bar widget providing window controls and experiment management buttons.

    This widget serves as the title bar for the Desq application, providing
    platform-specific window controls (close, minimize, fullscreen) along with
    experiment-related controls (run, stop, progress, load).

    The menu bar supports window dragging on both macOS and Windows platforms,
    with platform-specific handling for smooth drag operations.

    :param parent: The parent main window widget.
    :type parent: QMainWindow

    :ivar parent: Reference to the parent main window.
    :vartype parent: QMainWindow
    :ivar mouse_pos: Stored mouse position for window dragging operations.
    :vartype mouse_pos: QPoint
    :ivar is_macos: Flag indicating if running on macOS platform.
    :vartype is_macos: bool
    :ivar btn_close: Window close button.
    :vartype btn_close: QPushButton
    :ivar btn_minimize: Window minimize button.
    :vartype btn_minimize: QPushButton
    :ivar btn_fullscreen: Window fullscreen/maximize toggle button.
    :vartype btn_fullscreen: QPushButton
    :ivar start_experiment_button: Button to start experiment execution.
    :vartype start_experiment_button: QPushButton
    :ivar stop_experiment_button: Button to stop running experiment.
    :vartype stop_experiment_button: QPushButton
    :ivar soc_status_label: Label showing SoC connection status.
    :vartype soc_status_label: QLabel
    :ivar experiment_progress_bar: Progress bar for experiment execution.
    :vartype experiment_progress_bar: QProgressBar
    :ivar experiment_progress_bar_label: Label for progress bar details.
    :vartype experiment_progress_bar_label: QLabel
    :ivar load_data_button: Button to load existing data files.
    :vartype load_data_button: QPushButton
    :ivar load_experiment_button: Button to load experiment definitions.
    :vartype load_experiment_button: QPushButton
    :ivar documentation_button: Button to access documentation.
    :vartype documentation_button: QPushButton
    :ivar settings_button: Button to access settings.
    :vartype settings_button: QPushButton

    .. note::
        On macOS, window controls appear on the left side (traffic light style).
        On Windows, they appear on the right side.

    Example
    -------
    ::

        menu_bar = CustomMenuBar(main_window)
        menu_bar.start_experiment_button.clicked.connect(run_experiment)
    """

    def __init__(self, parent: QMainWindow) -> None:
        """
        Initialize the custom menu bar.

        :param parent: The parent main window that this menu bar belongs to.
        :type parent: QMainWindow
        """
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(45)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_StyledBackground, True)

        # Store mouse position for window dragging calculations
        self.mouse_pos: QPoint = QPoint()

        menu_layout = QHBoxLayout(self)
        menu_layout.setContentsMargins(10, 5, 10, 0)
        menu_layout.setSpacing(8)

        # Detect platform for appropriate window control styling
        self.is_macos: bool = platform.system() == "Darwin"

        # Create platform-specific window control buttons (close/minimize/fullscreen)
        if self.is_macos:
            # macOS "traffic light" style - small circular buttons
            self.btn_close: QPushButton = Helpers.create_button("", "btn_close", True, self)
            self.btn_close.setFixedSize(QSize(11, 11))
            self.btn_minimize: QPushButton = Helpers.create_button("", "btn_minimize", True, self)
            self.btn_minimize.setFixedSize(QSize(11, 11))
            self.btn_fullscreen: QPushButton = Helpers.create_button("", "btn_fullscreen", True, self)
            self.btn_fullscreen.setFixedSize(QSize(11, 11))
        else:
            # Windows style - larger rectangular buttons
            self.btn_minimize: QPushButton = Helpers.create_button("", "win_btn_minimize", True, self)
            self.btn_minimize.setFixedSize(QSize(16, 16))
            self.btn_fullscreen: QPushButton = Helpers.create_button("", "win_btn_fullscreen", True, self)
            self.btn_fullscreen.setFixedSize(QSize(16, 16))
            self.btn_close: QPushButton = Helpers.create_button("", "win_btn_close", True, self)
            self.btn_close.setFixedSize(QSize(16, 16))

        # Create experiment control and utility buttons
        self.start_experiment_button: QPushButton = Helpers.create_button("", "start_experiment", False, self)
        self.start_experiment_button.setToolTip("Run")
        self.start_experiment_button.setFixedWidth(35)
        self.stop_experiment_button: QPushButton = Helpers.create_button("", "stop_experiment", False, self)
        self.stop_experiment_button.setToolTip("Stop")
        self.stop_experiment_button.setFixedWidth(35)

        # SoC connection status indicator
        self.soc_status_label: QLabel = QLabel('Soc Disconnected', self)
        self.soc_status_label.setStyleSheet("color: lightgray;")
        self.soc_status_label.setObjectName("soc_status_label")

        # Experiment progress indicators
        self.experiment_progress_bar: QProgressBar = QProgressBar(self, value=0)
        self.experiment_progress_bar.setFixedHeight(15)
        self.experiment_progress_bar.setObjectName("experiment_progress_bar")
        self.experiment_progress_bar.setTextVisible(False)
        self.experiment_progress_bar_label: QLabel = QLabel(self)
        self.experiment_progress_bar_label.setObjectName("experiment_progress_bar_label")

        # Data and experiment loading buttons
        self.load_data_button: QPushButton = Helpers.create_button("Load Data", "load_data_button", True, self)
        self.load_experiment_button: QPushButton = Helpers.create_button("Load Experiment", "load_experiment_button", True, self)

        # Utility buttons
        self.documentation_button: QPushButton = Helpers.create_button("", "documentation", True, self)
        self.documentation_button.setToolTip("Documentation")
        self.documentation_button.setObjectName("documentation_button")
        self.settings_button: QPushButton = Helpers.create_button("", "settings_button", True, self, False)
        self.settings_button.setObjectName("settings_button")

        # Fixed-width spacer between window controls and main buttons
        spacerItem: QSpacerItem = QSpacerItem(30, 40, QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Layout widgets according to platform conventions
        if self.is_macos:
            # macOS: window controls on the left side
            menu_layout.addWidget(self.btn_close)
            menu_layout.addWidget(self.btn_minimize)
            menu_layout.addWidget(self.btn_fullscreen)
            menu_layout.addItem(spacerItem)

        # Main control buttons (same order on both platforms)
        menu_layout.addWidget(self.start_experiment_button)
        menu_layout.addWidget(self.stop_experiment_button)
        menu_layout.addWidget(self.soc_status_label)
        menu_layout.addWidget(self.experiment_progress_bar)
        menu_layout.addWidget(self.experiment_progress_bar_label)
        menu_layout.addWidget(self.load_data_button)
        menu_layout.addWidget(self.load_experiment_button)
        menu_layout.addWidget(self.documentation_button)
        menu_layout.addWidget(self.settings_button)

        if not self.is_macos:
            # Windows: window controls on the right side
            menu_layout.addItem(spacerItem)
            menu_layout.addWidget(self.btn_minimize)
            menu_layout.addWidget(self.btn_fullscreen)
            menu_layout.addWidget(self.btn_close)

        self.setup_signals()

    def setup_signals(self) -> None:
        """
        Connect window control button signals to their handler methods.

        Connects the close, minimize, and fullscreen buttons to their
        respective window management methods.
        """
        self.btn_close.clicked.connect(self.parent.close)
        self.btn_minimize.clicked.connect(self.minimize_window)
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)

    def minimize_window(self) -> None:
        """
        Minimize the parent window.

        Calls showMinimized() on the parent window regardless of platform.
        """
        self.parent.showMinimized()

    def toggle_fullscreen(self) -> None:
        """
        Toggle the parent window between fullscreen/maximized and normal states.

        On macOS, this toggles true fullscreen mode and adjusts styling
        (border radius, translucent background) accordingly. The minimize
        button is disabled in fullscreen mode on macOS.

        On Windows, this toggles between maximized and normal window states.

        After toggling, applies the parent's settings to ensure consistent
        appearance.
        """
        if self.is_macos:
            if self.parent.isFullScreen():
                # Restore from fullscreen to normal windowed mode
                self.parent.showNormal()
                self.btn_minimize.setEnabled(True)
                # Restore rounded corners and translucent background
                self.parent.setStyleSheet("QMainWindow{background: transparent; border-radius: 10px}")
                self.setStyleSheet("QWidget#custom_menu_bar{border-top-left-radius: 10px; border-top-right-radius: 10px;}")
                self.parent.setAttribute(Qt.WA_TranslucentBackground, True)
            else:
                # Enter fullscreen mode
                self.parent.showFullScreen()
                self.btn_minimize.setEnabled(False)
                # Remove corner rounding for fullscreen
                self.setStyleSheet("QWidget#custom_menu_bar{border-top-left-radius: 0px; border-top-right-radius: 0px;}")
        else:
            # Windows: toggle between maximized and normal
            if self.parent.isMaximized():
                self.parent.showNormal()
            else:
                self.parent.showMaximized()

        # Reapply settings after window state change
        self.parent.apply_settings()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse press events for window dragging initiation.

        On left mouse button press, stores the current mouse position.
        On macOS, initiates system-level window dragging for smoother
        movement.

        :param event: The mouse press event.
        :type event: QMouseEvent
        """
        if event.button() == Qt.LeftButton:
            self.mouse_pos = event.globalPos()

            # macOS: delegate dragging to the system for native feel
            if self.is_macos:
                window = self.parent.windowHandle()
                if window is not None:
                    window.startSystemMove()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse move events for window dragging.

        Moves the parent window based on mouse delta when the left button
        is held down. Includes guards for macOS (handled by system),
        fullscreen mode, and window visibility.

        :param event: The mouse move event.
        :type event: QMouseEvent
        """
        if self.is_macos:
            # macOS: dragging is handled by startSystemMove() in mousePressEvent
            return
        if self.parent.isFullScreen():
            return
        if not self.parent.isVisible():
            return

        if event.buttons() & Qt.LeftButton:

            delta = event.globalPos() - self.mouse_pos
            self.parent.move(self.parent.pos() + delta)
            self.mouse_pos = event.globalPos()

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Paint the menu bar background with rounded top corners.

        Draws the widget background with antialiased rounded corners
        to match the frameless window aesthetic.

        :param event: The paint event.
        :type event: QPaintEvent

        .. note::
            The pen is set to NoPen but no brush is set, so the
            drawRoundedRect call may not produce visible output
            depending on the widget's stylesheet configuration.
            The actual background color is typically controlled
            via stylesheets.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw background with rounded top corners (matches frameless window style)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 10, 10)