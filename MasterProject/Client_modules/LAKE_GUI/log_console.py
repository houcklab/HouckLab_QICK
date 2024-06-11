from PyQt5.QtCore import qDebug, qWarning, qCritical, qInstallMessageHandler, QtMsgType, pyqtSlot
from PyQt5.QtWidgets import QWidget, QTextEdit, QVBoxLayout


class LogConsoleWidget(QWidget):

    def __init__(self, parent):
        '''
        Creates the LogConsoleWidget responsible for maintaining a QTextEdit acting as a console. This text box displays
        any error, info, or warning messages. To display an message, use qInfo for info messages, qCritical for error
        messages, qWarning for warning messages, qDebug for debug messages.
        '''
        super().__init__(parent=parent)

        self.console = None

        self.__init_UI()

    def __init_UI(self):

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        self.console = QTextEdit(self)
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: black; color: white;")

        layout.addWidget(self.console)

    def message_handler(self, mode, context, message):

        # color = 'black'
        color = 'white'
        header = ''
        if mode == QtMsgType.QtDebugMsg:
            color = 'purple'
            header = 'Debug:\t'
        elif mode == QtMsgType.QtWarningMsg:
            color = 'yellow'
            header = 'Warning:\t'
        elif mode == QtMsgType.QtCriticalMsg:
            color = 'red'
            header = 'Error:\t'
        elif mode == QtMsgType.QtInfoMsg:
            color = 'white'
            header = ' -\t'

        self.console.append(f"<span style='color:{color}'>{header}{message}</span>")
        self.console.ensureCursorVisible()

