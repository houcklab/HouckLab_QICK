"""
===========
LogPanel.py
===========

Side panel widget for displaying GUI log messages.

This module provides the :class:`QLogPanel` widget, a read-only log display
that captures and color-codes Qt message system output (debug, info, warning,
critical, fatal messages).

The log panel integrates with Qt's message handling system via
``qInstallMessageHandler``, allowing it to capture all ``qDebug()``,
``qInfo()``, ``qWarning()``, ``qCritical()``, and ``qFatal()`` calls
made anywhere in the application.

Message Types and Colors
------------------------
Messages are color-coded for easy identification:

- **Debug** (``QtDebugMsg``): Light blue (#8AC6F2)
- **Info** (``QtInfoMsg``): Gray (#CCCCCC)
- **Warning** (``QtWarningMsg``): Yellow (#E1B12C)
- **Critical** (``QtCriticalMsg``): Red (#FF5C5C)
- **Fatal** (``QtFatalMsg``): Bright red (#FF0000)

Unread Indicator
----------------
When new messages arrive while the Log tab is not active, the tab text
is updated to "Log*" to indicate unread messages.

.. warning::
    The message handler updates a QTextEdit widget. This is **not thread-safe**
    and should only be called from the main GUI thread. Worker threads should
    use ``print()`` for logging instead of ``qDebug()`` etc.

.. seealso::
    - :func:`PyQt5.QtCore.qInstallMessageHandler` for message handler installation
    - :class:`ExperimentThread` for notes on thread-safe logging
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

from PyQt5.QtCore import (
    QSize,
    QtMsgType,
    qInstallMessageHandler,
    qDebug,
    qInfo,
    qWarning,
    qCritical
)
from PyQt5.QtWidgets import (
    QWidget,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout
)

if TYPE_CHECKING:
    from PyQt5.QtCore import QMessageLogContext
    from PyQt5.QtWidgets import QTabWidget


class QLogPanel(QWidget):
    """
    A widget that displays Qt message system output in a color-coded log view.

    The log panel captures messages from Qt's logging system (``qDebug``,
    ``qInfo``, ``qWarning``, ``qCritical``) and displays them in a scrollable
    text area with color coding based on severity.

    The panel is designed to be used as a tab in a ``QTabWidget``. When messages
    arrive while the tab is not active, the tab title is updated to indicate
    unread messages.

    :param parent: The parent widget, typically a QTabWidget containing this panel.
    :type parent: QTabWidget | None

    :ivar parent: Reference to the parent tab widget.
    :vartype parent: QTabWidget | None
    :ivar main_layout: The vertical layout containing the logger widget.
    :vartype main_layout: QVBoxLayout
    :ivar logger: The text edit widget displaying log messages.
    :vartype logger: QTextEdit

    .. note::
        The ``message_handler`` method must be installed via
        ``qInstallMessageHandler(panel.message_handler)`` to receive messages.
        This is typically done by the main application during setup.

    Example
    -------
    ::

        # Create log panel in a tab widget
        log_panel = QLogPanel(parent=tab_widget)
        tab_widget.addTab(log_panel, "Log")

        # Install message handler to capture Qt messages
        qInstallMessageHandler(log_panel.message_handler)

        # Now all qDebug/qInfo/etc. calls will appear in the log
        qInfo("Application started")
    """

    def __init__(self, parent: Optional[QTabWidget] = None) -> None:
        """
        Initialize the log panel widget.

        :param parent: The parent widget, typically a QTabWidget.
        :type parent: QTabWidget | None
        """
        super(QLogPanel, self).__init__(parent)

        # Configure size policy for flexible layout
        sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        sizepolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())

        self.parent: Optional[QTabWidget] = parent
        self.setMinimumSize(QSize(175, 0))
        self.setSizePolicy(sizepolicy)
        self.setObjectName("log_panel_widget")

        # Set up layout with no margins for clean appearance
        self.main_layout: QVBoxLayout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Create the log text display
        self.logger: QTextEdit = QTextEdit()
        self.logger.setObjectName("log_panel")

        # NOTE: Read-only mode is currently disabled (commented out below)
        # This allows users to select/copy text or potentially clear the log
        read_only_message = f'<span style="color:#CCCCCC">(Read Only)</span>'
        # self.logger.append(read_only_message)
        # self.logger.setReadOnly(True)

        self.main_layout.addWidget(self.logger)
        self.setLayout(self.main_layout)

    def message_handler(
        self,
        mode: QtMsgType,
        context: QMessageLogContext,
        message: str
    ) -> None:
        """
        Handle Qt message system signals and display them in the log.

        This method is designed to be installed as the Qt message handler via
        ``qInstallMessageHandler()``. It receives all messages from ``qDebug()``,
        ``qInfo()``, ``qWarning()``, ``qCritical()``, and ``qFatal()`` calls.

        Messages are formatted with HTML color coding based on severity and
        appended to the logger widget.

        :param mode: The message type/severity level.
        :type mode: QtMsgType
        :param context: Context information about where the message originated
            (file, line, function). Currently unused.
        :type context: QMessageLogContext
        :param message: The log message text.
        :type message: str

        .. note::
            The ``context`` parameter provides source location information but
            is not currently displayed. This could be enhanced to show file/line
            info for debugging purposes.

        .. warning::
            This method updates a QTextEdit and must only be called from the
            main GUI thread. Calling from worker threads will cause
            "Cannot queue arguments of type 'QTextCursor'" errors.
        """
        # Map message types to display colors
        color_map = {
            QtMsgType.QtDebugMsg: "#8AC6F2",    # Light blue for debug
            QtMsgType.QtWarningMsg: "#E1B12C",  # Yellow for warnings
            QtMsgType.QtCriticalMsg: "#FF5C5C", # Red for critical
            QtMsgType.QtFatalMsg: "#FF0000",    # Bright red for fatal
            QtMsgType.QtInfoMsg: "#CCCCCC"      # Gray for info
        }

        color = color_map.get(mode, "#CCCCCC")  # Default to gray for unknown types
        formatted_message = (
            f'<span style="color:{color}">> {message}</span>'
        )

        self.logger.append(formatted_message)

        # NOTE: Auto-scroll is disabled (commented out below)
        # This allows users to scroll back through the log without being
        # interrupted by new messages
        # self.logger.ensureCursorVisible()

        # Update tab title to indicate unread messages if this tab is not active
        # BUG: This assumes parent is a QTabWidget and will fail if parent is None
        # or a different widget type. Should add a type/None check here.
        index = self.parent.indexOf(self)
        if index != self.parent.currentIndex():
            self.parent.setTabText(index, "Log*")