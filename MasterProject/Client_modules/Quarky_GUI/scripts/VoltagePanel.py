"""
===============
VoltagePanel.py
===============
Soon to be the home of a voltage controller interface panel [Qbox and Yoko].

    *Coming Soon*
"""

from PyQt5.QtCore import QSize, QRect, Qt
from PyQt5.QtWidgets import (
    QWidget,
    QSizePolicy,
    QComboBox,
    QLabel,
    QVBoxLayout
)

import scripts.Helpers as Helpers
from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface
from MasterProject.Client_modules.Quarky_GUI.PythonDrivers.YOKOGS200 import YOKOGS200
from MasterProject.Client_modules.Quarky_GUI.PythonDrivers.QBLOX import QBLOX
from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentT2 import ExperimentClassT2

class QVoltagePanel(QWidget):
    """
    A custom QWidget class for the voltage control panel.

    **Important Attributes:**

        * -----
    """

    def __init__(self, config_tree_panel, current_Tab, parent=None):
        super(QVoltagePanel, self).__init__(parent)

        # Storing the config tree in order to change its config values via the UI
        self.config_tree_panel = config_tree_panel
        self.current_Tab = current_Tab

        # Set size policy
        sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        sizepolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sizepolicy)
        self.setMinimumSize(QSize(175, 0))
        self.setObjectName("voltage_controller_panel")

        # The main layout that will hold all components
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Buttons layout
        self.interface_button_layout = QVBoxLayout()
        self.interface_button_layout.setContentsMargins(5, 5, 5, 0)
        self.interface_button_layout.setSpacing(1)
        self.interface_button_layout.setObjectName("interface_button_layout")

        # Voltage source combo box and connection button
        self.voltage_interface_combo = QComboBox(self)
        self.voltage_interface_combo.setObjectName("voltage_interface_combo")
        self.voltage_interface_combo.addItems(["Qblox", "Yoko"])
        self.create_connection_button = Helpers.create_button("Create Connection","create_connection_button",True,self)

        self.interface_button_layout.addWidget(self.voltage_interface_combo)
        self.interface_button_layout.addWidget(self.create_connection_button)

        # Under construction label
        self.under_construction_label = QLabel(self)
        self.under_construction_label.setText('<html><b>Under <br> Construction</b></html>')
        self.under_construction_label.setGeometry(QRect(20, 200, 131, 41))
        self.under_construction_label.setAlignment(Qt.AlignCenter)
        self.under_construction_label.setObjectName("under_construction_label")

        self.main_layout.addLayout(self.interface_button_layout)
        self.main_layout.addWidget(self.under_construction_label)

        self.setLayout(self.main_layout)

        self.setup_signals()

    def changed_tabs(self, current_tab):
        self.current_Tab = current_tab
        self.setEnabled(False)

        if self.current_Tab.experiment_obj is not None:
            if self.current_Tab.experiment_obj.experiment_type == ExperimentClassT2:
                print(self.current_Tab.experiment_obj.experiment_type)
                self.setEnabled(True)


                # handle loading configs

    def setup_signals(self):
        """
        Sets up all the signals and slots of the Accounts Panel. Including changing voltage interface type, and
        set voltage buttons.
        """
        self.setEnabled(False)
        if self.current_Tab.experiment_obj is not None:
            if self.current_Tab.experiment_obj.experiment_type == ExperimentClassT2:
                self.setEnabled(True)

        # self.voltage_interface_combo.currentIndexChanged.connect(self.handle_voltInterface_change)
        self.create_connection_button.clicked.connect(self.toggle_create_connection)

    def toggle_create_connection(self):
        """
        Toggles the create connection button between create and delete connection. Ensures we are not just
        creating many instances of voltage interfaces.
        """
        current_text = self.create_connection_button.text()

        if current_text == "Create Connection":
            self.create_connection_button.setText("Delete Connection")
            self.voltage_interface_combo.setEnabled(False)
            # self.create_connection()
        else:
            # Change button text to "Create Connection"
            self.create_connection_button.setText("Create Connection")
            self.voltage_interface_combo.setEnabled(True)
            # self.delete_connection()



