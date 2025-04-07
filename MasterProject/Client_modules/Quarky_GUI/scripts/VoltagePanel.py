"""
===============
VoltagePanel.py
===============
Soon to be the home of a voltage controller interface panel [Qbox and Yoko].

    *Coming Soon*
"""

import pyvisa as visa
import json
from PyQt5.QtCore import QSize, QRect, Qt, qCritical, qInfo
from PyQt5.QtGui import QTextOption
from PyQt5.QtWidgets import (
    QWidget,
    QSizePolicy,
    QComboBox,
    QLabel,
    QVBoxLayout,
    QGroupBox,
    QTextEdit,
    QMessageBox
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

    yoko_settings = {
        "VISAaddress": "USB0::0x0B21::0x0039::91S929901::0::INSTR",
    }
    """
    The yoko_settings. Change this code to set default values.
    """

    qblox_settings = {
        "range_num": 2, "module": 2, "reset_voltages": False, "num_dacs": 16,"ramp_step": 0.003,
        "ramp_interval": 0.05, "COM_speed": 1e6, "port": 'COM3',"timeout": 1
    }
    """
    The qblox_settings. Change this code to set default values.
    """

    def __init__(self, config_tree_panel, current_Tab, parent=None):
        super(QVoltagePanel, self).__init__(parent)

        self.connected = False
        self.voltage_interface = None

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
        self.main_layout.setSpacing(0)

        # Buttons layout
        self.interface_connect_layout = QVBoxLayout()
        self.interface_connect_layout.setContentsMargins(5, 5, 5, 0)
        self.interface_connect_layout.setSpacing(0)
        self.interface_connect_layout.setObjectName("interface_button_layout")

        # Voltage source combo box and connection button
        self.voltage_interface_combo = QComboBox(self)
        self.voltage_interface_combo.setObjectName("voltage_interface_combo")
        self.voltage_interface_combo.addItems(["Qblox", "Yoko"])

        self.voltage_interface_settings = QTextEdit(self)
        self.voltage_interface_settings.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.voltage_interface_settings.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.voltage_interface_settings.setMaximumHeight(60)
        self.voltage_interface_settings.setStyleSheet("font-size: 10pt;")
        self.setup_voltage_interface_settings()

        self.create_connection_button = Helpers.create_button("Create Connection","create_connection_button",True,self)

        self.interface_connect_layout.addWidget(self.voltage_interface_combo)
        self.interface_connect_layout.addWidget(self.voltage_interface_settings)
        self.interface_connect_layout.addWidget(self.create_connection_button)

        # Controller Content Widget
        self.controller_content = QWidget(self)
        self.controller_layout = QVBoxLayout(self.controller_content)
        self.controller_layout.setContentsMargins(0, 0, 0, 0)
        self.controller_layout.setSpacing(0)

        # Voltage Channels Section
        self.voltage_channels_group = QGroupBox("Voltage Channels")
        self.voltage_channels_group.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignTop)
        self.voltage_channels_group.setObjectName("voltage_channels_group")
        self.voltage_channels_layout = QVBoxLayout(self.voltage_channels_group)
        self.voltage_channels_layout.setContentsMargins(0, 0, 0, 0)
        self.voltage_channels_layout.setObjectName("voltage_channels_layout")

        # Sweeps Section
        self.sweeps_group = QGroupBox("Sweeps")
        self.sweeps_group.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignTop)
        self.sweeps_group.setObjectName("sweeps_group")
        self.sweeps_layout = QVBoxLayout(self.sweeps_group)
        self.sweeps_layout.setContentsMargins(0, 0, 0, 0)
        self.sweeps_layout.setObjectName("sweeps_layout")

        self.voltage_channels_group.setLayout(self.voltage_channels_layout)
        self.controller_layout.addWidget(self.voltage_channels_group)
        self.controller_layout.addWidget(self.sweeps_group)

        # Adding it all to main layout
        self.main_layout.addLayout(self.interface_connect_layout)
        self.main_layout.addWidget(self.controller_content)

        self.setLayout(self.main_layout)

        self.setup_signals()

        # TODO: create the set voltage buttons
        # TODO: create the sweep section
        self.update_sweeps()

    def setup_signals(self):
        """
        Sets up all the signals and slots of the Accounts Panel. Including changing voltage interface type, and
        set voltage buttons.
        """

        self.voltage_channels_group.setEnabled(False)
        self.sweeps_group.setEnabled(False)


        self.voltage_interface_combo.currentIndexChanged.connect(self.handle_voltInterface_change)
        self.create_connection_button.clicked.connect(self.toggle_create_connection)

    def handle_voltInterface_change(self, index):
        """
        Handle when the user changes the voltage interface type.
        """

        self.setup_voltage_interface_settings()

    def toggle_create_connection(self):
        """
        Toggles the create connection button between create and delete connection. Ensures we are not just
        creating many instances of voltage interfaces.
        """

        current_text = self.create_connection_button.text()

        if current_text == "Create Connection":
            if self.create_connection():
                self.create_connection_button.setText("Delete Connection")
                self.voltage_interface_combo.setEnabled(False)
                self.voltage_interface_settings.setEnabled(False)
                self.voltage_channels_group.setEnabled(True)

                self.changed_tabs()
            else:
                QMessageBox.critical(self, "Error", f"Failed to create voltage interface connection.")
        else:
            self.create_connection_button.setText("Create Connection")
            self.voltage_interface_combo.setEnabled(True)
            self.voltage_interface_settings.setEnabled(True)
            self.voltage_channels_group.setEnabled(False)
            self.sweeps_group.setEnabled(False)

            self.delete_connection()

    def changed_tabs(self, current_tab=None):
        """
        The function activated when the experiment tab is changed, where then it retrieves the experiment type, and
        whether it not it provides a Voltage Config to perform sweeps.
        """
        if current_tab is not None:
            self.current_Tab = current_tab
        self.sweeps_group.setEnabled(False)

        if self.connected and self.current_Tab.experiment_obj is not None:
            if self.current_Tab.experiment_obj.experiment_type == ExperimentClassT2:
                print(self.current_Tab.experiment_obj.experiment_type)
                self.sweeps_group.setEnabled(True)

                self.update_sweeps()

    def setup_voltage_interface_settings(self):
        """
        Set up the voltage interface settings with the default values depending on whether Yoko or Qblox is selected.
        """
        self.voltage_interface_settings.clear()
        width = self.voltage_interface_settings.width()

        if self.voltage_interface_combo.currentText() == "Yoko":
            formatted_json = json.dumps(self.yoko_settings, indent=2)
            self.voltage_interface_settings.setText(str(formatted_json)[2:-2])
        else:
            formatted_json = json.dumps(self.qblox_settings, indent=2)
            self.voltage_interface_settings.setText(str(formatted_json)[2:-2])

        self.voltage_interface_settings.adjustSize()
        self.voltage_interface_settings.resize(width, 60)

        # TODO handle setting changes

    def create_connection(self):
        """
        Creates a new connection dependent on what the user has selected on the dropdown. Also retrieves the
        specified connection settings.

        :return: Status of connection, True successful, False otherwise.
        :rtype: bool
        """

        voltage_interface_type = self.voltage_interface_combo.currentText()

        # retrieve the textedit settings
        settings = "{" + self.voltage_interface_settings.toPlainText() + "}"
        try:
            if voltage_interface_type == "Yoko":
                self.yoko_settings = json.loads(settings)
            else:
                self.qblox_settings = json.loads(settings)
        except json.JSONDecodeError as e:
            qCritical("Invalid settings format:" + str(e))
            QMessageBox.critical(self, "Error", f"Invalid settings format.")
            return False

        try:
            if voltage_interface_type == "Yoko":
                # Create yoko connection
                rm = visa.ResourceManager()
                self.voltage_interface = YOKOGS200(**self.yoko_settings, rm=rm)
            else:
                # Create Qblox connection
                self.voltage_interface = QBLOX(**self.qblox_settings)

            qInfo("Successfully connected to " + voltage_interface_type + ".")
            self.connected = True

            return True
        except Exception as e:
            qCritical("Failed to connect to Voltage Controller: " + str(e))
            return False

    def delete_connection(self):
        """
        Deletes the connection to the voltage interface by deleting the voltage_interface variable.
        """

        self.connected = False
        del self.voltage_interface
        qInfo("Successfully disconnected from Voltage Controller")

    def update_sweeps(self):
        """
        If Experiment offers a Voltage Config (sweeps), we populate the sweep section with editable configs.
        """
        pass # TODO


