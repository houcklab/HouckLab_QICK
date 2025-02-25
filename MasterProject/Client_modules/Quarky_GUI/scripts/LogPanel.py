import os

from PyQt5.QtCore import (QSize, QtMsgType, qInstallMessageHandler,
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

class QLogPanel(QWidget):

    def __init__(self, parent=None):
        super(QLogPanel, self).__init__(parent)

        sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        sizepolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setMinimumSize(QSize(175, 0))
        self.setSizePolicy(sizepolicy)
        self.setObjectName("log_panel")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.logger = QTextEdit()
        self.logger.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;  /* Dark background */
                color: #CCCCCC;  /* Light gray text */
                font-size: 12px;
                border: 1px solid #333333;  /* Subtle border */
                padding: 5px;
            }
        """)
        read_only_message = f'<span style="color:#CCCCCC">(Read Only)</span>'
        self.logger.append(read_only_message)
        self.logger.setReadOnly(True)

        self.main_layout.addWidget(self.logger)
        self.setLayout(self.main_layout)

    def message_handler(self, mode, context, message):
        color_map = {
            QtMsgType.QtDebugMsg: "#8AC6F2",  # Light blue
            QtMsgType.QtWarningMsg: "#E1B12C",  # Yellow
            QtMsgType.QtCriticalMsg: "#FF5C5C",  # Red
            QtMsgType.QtFatalMsg: "#FF0000",  # Bright red
            QtMsgType.QtInfoMsg: "#CCCCCC"
        }

        color = color_map.get(mode, "#CCCCCC")  # Default gray
        formatted_message = f'<span style="color:{color}">{message}</span>'

        self.logger.append(formatted_message)
        # self.logger.ensureCursorVisible()