"""
===============
VoltagePanel.py
===============
Soon to be the home of a voltage controller interface panel [Qbox and Yoko].

    *Coming Soon*
"""

import pyvisa as visa
import json
import traceback
from PyQt5.QtCore import QSize, QRect, Qt, qCritical, qInfo, QTimer
from PyQt5.QtGui import QTextOption
from PyQt5.QtWidgets import (
    QWidget,
    QSizePolicy,
    QComboBox,
    QLabel,
    QVBoxLayout,
    QGroupBox,
    QTextEdit,
    QMessageBox, QHBoxLayout, QLineEdit, QScrollArea, QFrame, QLCDNumber
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
    range_numbers = { 0: [0,4], 2: [-4,4], 4: [-2,2]}
    """
    The qblox_settings. Change this code to set default values.
        range_numbers:
            * 0 to 4 Volt: range_4V_uni (span 0)
            * -4 to 4 Volt: range_4V_bi (span 2) default
            * -2 to 2 Volt: range_2V_bi (span 4)
    """

    def __init__(self, config_tree_panel, current_Tab, parent=None):
        super(QVoltagePanel, self).__init__(parent)

        self.connected = False
        self.voltage_interface = None
        self.range = [0,0]

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
        self.voltage_interface_currtype = "Qblox"

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
        self.voltage_channels_group = QGroupBox("Channels")
        self.voltage_channels_group.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignTop)
        self.voltage_channels_group.setObjectName("voltage_channels_group")
        self.voltage_channels_group.setMinimumHeight(100)

        # Contains all channel components
        self.voltage_channels_layout = QVBoxLayout(self.voltage_channels_group)
        self.voltage_channels_layout.setContentsMargins(0, 5, 0, 0)
        self.voltage_channels_layout.setSpacing(3)
        self.voltage_channels_layout.setObjectName("voltage_channels_layout")

        self.voltage_range_label = QLabel("  Voltage Range: [0,0]")
        self.voltage_range_label.setStyleSheet("font-size: 10pt;")
        self.voltage_channels_layout.addWidget(self.voltage_range_label)

        # Scroll area to contain list of channels
        self.channel_scroll_area = QScrollArea()
        self.channel_scroll_area.setObjectName("channel_scroll_area")
        self.channel_scroll_area.setFrameShape(QFrame.NoFrame)  # Remove the frame
        self.channel_scroll_area.setWidgetResizable(True)
        # Widget + layout to put into the scroll area (one for qblox, one for yoko)
        self.channel_list = QWidget()
        self.channel_list_layout = QVBoxLayout()
        self.channel_list_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_list.setLayout(self.channel_list_layout)

        # The one for QBLOX
        self.qblox_channel_list = QWidget()
        self.qblox_channel_list_layout = QVBoxLayout()
        self.qblox_channel_list_layout.setContentsMargins(5, 0, 10, 0)
        self.qblox_channel_list_layout.setSpacing(0)
        self.qblox_channel_list_layout.setObjectName("qblox_channel_list_layout")
        self.qblox_channel_list.setLayout(self.qblox_channel_list_layout)
        # The one for YOKO
        self.yoko_channel_list = QWidget()
        self.yoko_channel_list_layout = QVBoxLayout()
        self.yoko_channel_list_layout.setContentsMargins(5, 0, 10, 0)
        self.yoko_channel_list_layout.setSpacing(0)
        self.yoko_channel_list_layout.setObjectName("yoko_channel_list_layout")
        self.yoko_channel_list.setLayout(self.yoko_channel_list_layout)
        self.yoko_channel_list.hide()

        self.channel_list_layout.addWidget(self.qblox_channel_list)
        self.channel_list_layout.addWidget(self.yoko_channel_list)

        self.channel_scroll_area.setWidget(self.channel_list)
        # Adding it all to voltage_channels_layout
        self.voltage_channels_layout.addWidget(self.channel_scroll_area)
        self.voltage_channels_group.setLayout(self.voltage_channels_layout)

        self.setup_voltage_channels()

        # Sweeps Section
        self.sweeps_group = QGroupBox("Sweeps")
        self.sweeps_group.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignTop)
        self.sweeps_group.setObjectName("sweeps_group")
        self.sweeps_group.setMinimumHeight(100)
        self.sweeps_layout = QVBoxLayout(self.sweeps_group)
        self.sweeps_layout.setContentsMargins(0, 0, 0, 0)
        self.sweeps_layout.setObjectName("sweeps_layout")

        self.sweeps_edit = QTextEdit(self.sweeps_group)
        self.sweeps_layout.addWidget(self.sweeps_edit)
        self.sweeps_group.setLayout(self.sweeps_layout)

        self.controller_layout.addWidget(self.voltage_channels_group, stretch=2)
        self.controller_layout.addWidget(self.sweeps_group, stretch=1)

        # Adding it all to main layout
        self.main_layout.addLayout(self.interface_connect_layout)
        self.main_layout.addWidget(self.controller_content)

        self.setLayout(self.main_layout)

        self.setup_signals()

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
        self.voltage_interface_currtype = self.voltage_interface_combo.currentText()

        if self.voltage_interface_currtype == "Yoko":
            self.yoko_channel_list.show()
            self.qblox_channel_list.hide()
            self.voltage_channels_group.setMaximumHeight(100)
        else:
            self.yoko_channel_list.hide()
            self.qblox_channel_list.show()
            self.voltage_channels_group.setMaximumHeight(16777215) # basically removes height constraint

        self.setup_voltage_interface_settings()
        # Change which voltage channel is showing

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
                self.voltage_interface_settings.hide()
                self.voltage_channels_group.setEnabled(True)

                self.changed_tabs()
            else:
                QMessageBox.critical(self, "Error", f"Failed to create voltage interface connection.")
        else:
            self.create_connection_button.setText("Create Connection")
            self.voltage_interface_combo.setEnabled(True)
            self.voltage_interface_settings.setEnabled(True)
            self.voltage_interface_settings.show()
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
                self.sweeps_group.setEnabled(True)

        self.update_sweeps()

    def setup_voltage_interface_settings(self):
        """
        Set up the voltage interface settings with the default values depending on whether Yoko or Qblox is selected.
        """
        self.voltage_interface_settings.clear()
        width = self.voltage_interface_settings.width()

        if self.voltage_interface_currtype == "Yoko":
            formatted_json = json.dumps(self.yoko_settings, indent=2)
            self.voltage_interface_settings.setText(str(formatted_json)[2:-2])
        else:
            formatted_json = json.dumps(self.qblox_settings, indent=2)
            self.voltage_interface_settings.setText(str(formatted_json)[2:-2])

        self.voltage_interface_settings.adjustSize()
        self.voltage_interface_settings.resize(width, 60)

        # TODO handle setting change validation

    def create_connection(self):
        """
        Creates a new connection dependent on what the user has selected on the dropdown. Also retrieves the
        specified connection settings.

        :return: Status of connection, True successful, False otherwise.
        :rtype: bool
        """

        # retrieve the textedit settings
        settings = "{" + self.voltage_interface_settings.toPlainText() + "}"
        try:
            if self.voltage_interface_currtype == "Yoko":
                self.yoko_settings = json.loads(settings)
                self.range = [0,1.3] # Manually set max
            else:
                self.qblox_settings = json.loads(settings)
                self.range = self.range_numbers[self.qblox_settings["range_num"]]
            self.voltage_range_label.setText("  Voltage Range " + str(self.range))
        except json.JSONDecodeError as e:
            qCritical("Invalid settings format:" + str(e))
            QMessageBox.critical(self, "Error", f"Invalid settings format.")
            return False

        # self.connected = True # For Testing
        # return True # For Testing

        try:
            if self.voltage_interface_currtype == "Yoko":
                # Create yoko connection
                rm = visa.ResourceManager()
                self.voltage_interface = YOKOGS200(**self.yoko_settings, rm=rm)
            else:
                # Create Qblox connection
                self.voltage_interface = QBLOX(**self.qblox_settings)

            qInfo("Successfully connected to " + self.voltage_interface_currtype + ".")
            self.connected = True

            return True
        except Exception as e:
            qCritical("Failed to connect to Voltage Controller: " + str(e))
            qCritical(traceback.print_exc())
            return False

    def delete_connection(self):
        """
        Deletes the connection to the voltage interface by deleting the voltage_interface variable.
        """

        self.connected = False
        del self.voltage_interface
        self.voltage_interface = None
        qInfo("Successfully disconnected from Voltage Controller")

    def setup_voltage_channels(self):
        """
        Sets up the UI for the voltage channels for both Qblox and Yoko.
        """

        for i in range(1,17):
            single_channel_group = QHBoxLayout()
            single_channel_group.setSpacing(1)
            single_channel_group.setObjectName("single_channel_group")
            channel_label = QLabel(str(i).zfill(2) + " : ")
            channel_label.setStyleSheet("color: #4A90E2;")
            channel_voltage_input = QLineEdit()
            channel_voltage_input.setPlaceholderText("0.0")
            channel_voltage_input.setAlignment(Qt.AlignRight)
            channel_voltage_setbutton = Helpers.create_button("Set", "set_voltage_button", True)
            single_channel_group.addWidget(channel_label)
            single_channel_group.addWidget(channel_voltage_input)
            single_channel_group.addWidget(channel_voltage_setbutton)

            # Use default arguments in the lambda to capture the current loop variables (i and input box)
            # This avoids the late binding issue where all lambdas would otherwise reference the final loop value
            channel_voltage_setbutton.clicked.connect(
                lambda _, ch=i, input_box=channel_voltage_input, set_button=channel_voltage_setbutton:
                    self.set_voltage(ch-1, input_box, set_button)
            )
            self.qblox_channel_list_layout.addLayout(single_channel_group)

        single_channel_group = QHBoxLayout()
        single_channel_group.setSpacing(1)
        single_channel_group.setObjectName("single_channel_group")
        channel_label = QLabel(str(1).zfill(2) + " : ")
        channel_label.setStyleSheet("color: #4A90E2;")
        channel_voltage_input = QLineEdit()
        channel_voltage_input.setPlaceholderText("0.0V")
        channel_voltage_input.setAlignment(Qt.AlignRight)
        channel_voltage_setbutton = Helpers.create_button("Set", "set_voltage_button", True)
        single_channel_group.addWidget(channel_label)
        single_channel_group.addWidget(channel_voltage_input)
        single_channel_group.addWidget(channel_voltage_setbutton)

        channel_voltage_setbutton.clicked.connect(lambda: self.set_voltage(0, channel_voltage_input,
                                                                           channel_voltage_setbutton))
        self.yoko_channel_list_layout.addLayout(single_channel_group)


    def set_voltage(self, channel, voltage_input, set_button):
        """
        Setting voltage of the connected Voltage Interface given the specified channel and voltage.

        :param channel: Voltage channel input QLineEdit.
        :type channel: QLineEdit
        :param voltage: Voltage value
        :type voltage: float
        """
        voltage = float(voltage_input.text())

        if self.connected and self.voltage_interface is not None:
            # Check ranges first
            if self.range[0] > voltage or voltage > self.range[1]:
                qCritical("Voltage Range " + str(voltage) + " is out of range.")
                QMessageBox.critical(self, "Error", f"Voltage range out of range.")
                return

            try:
                self.voltage_interface.set_voltage(voltage, [channel])
                voltage_input.clear()
                voltage_input.setPlaceholderText(str(voltage))

                set_button.setText("Done")
                QTimer.singleShot(2000, lambda: set_button.setText('Set'))
            except Exception as e:
                qCritical("Failed to set voltage: " + str(e))
                QMessageBox.critical(self, "Error", "Faled to set voltage.")
        else:
            qCritical("No connected voltage interface.") # Should never call

    def update_sweeps(self):
        """
        If Experiment offers a Voltage Config (sweeps), we populate the sweep section with editable configs.
        """
        formatted_json = ""
        if self.current_Tab.experiment_obj is not None:
            if self.current_Tab.experiment_obj.experiment_type == ExperimentClassT2:
                if "Voltage Config" in self.config_tree_panel.config:
                    qInfo("Voltage Config found to populate sweeps.")
                    print(self.config_tree_panel.config)
                    formatted_json = json.dumps(self.config_tree_panel.config["Voltage Config"], indent=2)
        self.sweeps_edit.setText(formatted_json)

        # TODO HANDLE EDIT UPDATING


