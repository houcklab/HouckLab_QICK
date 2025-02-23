from PyQt5.QtCore import QSize, QRect, Qt
from PyQt5.QtWidgets import (
    QWidget,
    QSizePolicy,
    QComboBox,
    QLabel
)

class QVoltagePanel(QWidget):
    def __init__(self, parent=None):
        super(QVoltagePanel, self).__init__(parent)

        # Set size policy
        sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        sizepolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sizepolicy)
        self.setMinimumSize(QSize(175, 0))
        self.setObjectName("voltage_controller_panel")

        # Voltage source combo box
        self.voltage_source_combo = QComboBox(self)
        self.voltage_source_combo.setGeometry(QRect(10, 10, 151, 26))
        self.voltage_source_combo.setObjectName("voltage_source")
        self.voltage_source_combo.addItems(["qblox", "yoko"])

        # Under construction label
        self.under_construction_label = QLabel(self)
        self.under_construction_label.setText('<html><b>Under <br> Construction</b></html>')
        self.under_construction_label.setGeometry(QRect(20, 200, 131, 41))
        self.under_construction_label.setAlignment(Qt.AlignCenter)
        self.under_construction_label.setObjectName("under_construction_label")
