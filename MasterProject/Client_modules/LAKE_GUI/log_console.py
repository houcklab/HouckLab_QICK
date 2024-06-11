from PyQt5.QtCore import qDebug, qWarning, qCritical, qInstallMessageHandler, QtMsgType
from PyQt5.QtWidgets import QWidget, QTextEdit, QVBoxLayout


class LogConsoleWidget(QWidget):

    def __init__(self, parent):
        super().__init__(parent=parent)

        self.console = None

        self.__init_UI()



        self.test_error()

    def __init_UI(self):

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        self.console = QTextEdit(self)
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: black; color: white;")

        layout.addWidget(self.console)

    def test_error(self):
        qDebug('this is a debug message')
        qWarning('this is a warning message')
        qCritical('this is a critical message')

    def message_handler(self, mode, context, message):

        print(mode)
        print(message)
        print(context)

        color = 'black'
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

