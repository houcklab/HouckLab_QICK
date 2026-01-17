"""
===============
VoltagePanel.py
===============
The home of a voltage controller interface panel [Qbox and Yoko].

Allows for an easy space to manually set voltages by channel and perform basic uniform sweeps.
Sweeps functionality and passing a reference of the voltage interface are only supported for ExperimentPlus experiments.
"""

import pyvisa as visa
import json
import ast
import time
import numpy as np
import traceback
from PyQt5.QtCore import QSize, QRect, Qt, qCritical, qInfo, QTimer, qDebug, qWarning, QThread
from PyQt5.QtGui import QTextOption, QDoubleValidator, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QSizePolicy,
    QComboBox,
    QLabel,
    QVBoxLayout,
    QGroupBox,
    QTextEdit,
    QMessageBox,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QFrame,
    QFormLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog,
)

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers
from MasterProject.Client_modules.Desq_GUI.scripts.AuxiliaryThread import AuxiliaryThread

from MasterProject.Client_modules.Desq_GUI.CoreLib.VoltageInterface import VoltageInterface
from MasterProject.Client_modules.Desq_GUI.PythonDrivers.YOKOGS200 import YOKOGS200
from MasterProject.Client_modules.Desq_GUI.PythonDrivers.QBLOX import QBLOX

class QVoltagePanel(QWidget):
    """
    A custom QWidget class for the voltage control panel.

    **Important Attributes:**
        * voltage_interface (VoltageInterface): The actual connection to the specified voltage interface.
        * voltage_hardware (VoltageInterface): The hardware that is passed to the experiment, usually the same as voltage_interface.
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

    def __init__(self, config_tree_panel, current_Tab, parent):
        """
        Initialise the custom QWidget class that is the Voltage Panel.

        :param config_tree_panel: The configuration tree panel.
        :type config_tree_panel: QConfigTreePanel
        :param current_Tab: The current tab widget.
        :type current_Tab: QQuarkTab
        :param parent: The parent widget.
        :type parent: QWidget
        """

        super(QVoltagePanel, self).__init__(parent)

        self.connected = False
        self.voltage_interface = None # the interface used to control voltages
        self.voltage_hardware = None # the hardware to send to the experiment
        self.range = [-4,4] # default
        self.parent = parent

        # Storing the config tree in order to change its config values via the UI
        self.config_tree_panel = config_tree_panel
        self.current_tab = current_Tab

        # Set size policy
        sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        sizepolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sizepolicy)
        self.setMinimumSize(QSize(175, 0))
        self.setObjectName("voltage_controller_panel")

        # The main layout that will hold all components
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 5, 0, 0)
        self.main_layout.setSpacing(2)

        # Buttons layout
        self.interface_connect_layout = QVBoxLayout()
        self.interface_connect_layout.setContentsMargins(5, 5, 5, 0)
        self.interface_connect_layout.setSpacing(5)
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
        self.voltage_interface_settings.setObjectName("voltage_interface_settings")
        self.setup_voltage_interface_settings()

        self.create_connection_button = Helpers.create_button("Create Connection","create_connection_button",True,self)

        self.interface_connect_layout.addWidget(self.voltage_interface_combo)
        self.interface_connect_layout.addWidget(self.voltage_interface_settings)
        self.interface_connect_layout.addWidget(self.create_connection_button)

        # Controller Content Widget
        self.controller_content = QWidget(self)
        self.controller_layout = QVBoxLayout(self.controller_content)
        self.controller_layout.setContentsMargins(0, 5, 0, 0)
        self.controller_layout.setSpacing(10)

        # Voltage Channels Section
        self.voltage_channels_group = QGroupBox("Channels")
        self.voltage_channels_group.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignTop)
        self.voltage_channels_group.setObjectName("voltage_channels_group")
        self.voltage_channels_group.setMinimumHeight(100)

        # Contains all channel components
        self.voltage_channels_layout = QVBoxLayout(self.voltage_channels_group)
        self.voltage_channels_layout.setContentsMargins(0, 5, 0, 0)
        self.voltage_channels_layout.setSpacing(5)
        self.voltage_channels_layout.setObjectName("voltage_channels_layout")

        self.voltage_range_label = QLabel("  Voltage Range: [0,0]")
        self.voltage_range_label.setObjectName("voltage_range_label")
        self.voltage_channels_layout.addWidget(self.voltage_range_label)

        # Scroll area to contain list of channels
        self.channel_scroll_area = QScrollArea()
        self.channel_scroll_area.setObjectName("channel_scroll_area")
        self.channel_scroll_area.setFrameShape(QFrame.NoFrame)  # Remove the frame
        self.channel_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_scroll_area.setWidgetResizable(True)
        # Widget + layout to put into the scroll area (one for qblox, one for yoko)
        self.channel_list = QWidget()
        self.channel_list.setObjectName("channel_list")
        self.channel_list_layout = QVBoxLayout()
        self.channel_list_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_list_layout.setSpacing(2)
        self.channel_list.setLayout(self.channel_list_layout)

        # The one for QBLOX
        self.qblox_channel_list = QWidget()
        self.qblox_channel_list.setObjectName("qblox_channel_list")
        self.qblox_channel_list_layout = QVBoxLayout()
        self.qblox_channel_list_layout.setContentsMargins(5, 0, 10, 0)
        self.qblox_channel_list_layout.setSpacing(5)
        self.qblox_channel_list_layout.setObjectName("qblox_channel_list_layout")
        self.qblox_channel_list.setLayout(self.qblox_channel_list_layout)
        # The one for YOKO
        self.yoko_channel_list = QWidget()
        self.yoko_channel_list.setObjectName("yoko_channel_list")
        self.yoko_channel_list_layout = QVBoxLayout()
        self.yoko_channel_list_layout.setContentsMargins(5, 0, 10, 0)
        self.yoko_channel_list_layout.setSpacing(5)
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
        # self.sweeps_group = QGroupBox("Voltage Config (Sweeps)")
        # self.sweeps_group.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignTop)
        # self.sweeps_group.setObjectName("sweeps_group")
        # # self.sweeps_group.setMinimumHeight(200)
        # self.sweeps_group.setFixedHeight(125)
        #
        # self.sweeps_layout = VoltageSweepBox(self.global_config_panel, self.voltage_interface_combo, self)
        # self.sweeps_group.setLayout(self.sweeps_layout)

        # Adding to controller
        self.controller_layout.addWidget(self.voltage_channels_group, stretch=2)
        # self.controller_layout.addWidget(self.sweeps_group, stretch=1)

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
        # self.sweeps_group.setEnabled(False)

        self.voltage_interface_combo.currentIndexChanged.connect(self.handle_voltInterface_change)
        self.create_connection_button.clicked.connect(self.toggle_create_connection)

    def handle_voltInterface_change(self, index):
        """
        Handle when the user changes the voltage interface type.

        :param index: The index of the selection made in the combo box (not used).
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
            # Begin connection animation
            self.is_connecting = True
            self.connecting_dot_count = 0
            self.animate_connecting()
            self.create_connection_button.setEnabled(False)

            # Attempt a connection
            self.create_connection()

        else:
            # Attempt a disconnection
            self.create_connection_button.setText("Create Connection")
            self.voltage_interface_combo.setEnabled(True)
            self.voltage_interface_settings.setEnabled(True)
            self.voltage_interface_settings.show()
            self.voltage_channels_group.setEnabled(False)
            # self.sweeps_group.setEnabled(False)

            self.delete_connection()

    def animate_connecting(self):
        """
        Small function to animate connecting to let the user know whatever connection is actively being attempted.
        """
        if self.is_connecting:
            # Update the label with the current number of dots
            self.create_connection_button.setText(f"Connecting{'.' * (self.connecting_dot_count)}")
            self.connecting_dot_count = (self.connecting_dot_count + 1) % 4  # Cycle through 0, 1, 2
            QTimer.singleShot(500, self.animate_connecting)  # Repeat every 500 ms

    def changed_tabs(self, current_tab=None):
        """
        The function activated when the experiment tab is changed, where then it retrieves the experiment type, and
        whether it not it provides a Voltage Config to perform sweeps.

        :param current_tab: The tab object of the current tab.
        :type current_tab: QQuarkTab
        """
        if current_tab is not None:
            self.current_tab = current_tab
        # self.sweeps_group.setEnabled(False)

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

        # TODO: comment out, used for testing purposes (bypassing connection)
        # self.successful_interface_connection(None)
        # return


        self.create_connection_button.setText("Creating...")

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

        # Start an auxiliary thread to make the connection
        self.aux_thread = QThread()
        if self.voltage_interface_currtype == "Yoko":
            temp_yoko_settings = self.yoko_settings.copy()
            temp_yoko_settings["rm"] = visa.ResourceManager()
            self.aux_worker = AuxiliaryThread(target_func=self.init_yoko, func_kwargs=temp_yoko_settings, timeout=5)
        else:
            self.aux_worker = AuxiliaryThread(target_func=self.init_qblox, func_kwargs=self.qblox_settings, timeout=45)
        self.aux_worker.moveToThread(self.aux_thread)

        # Connecting started and finished signals
        self.aux_thread.started.connect(self.aux_worker.run)  # run function
        self.aux_worker.finished.connect(self.aux_thread.quit)  # stop thread
        self.aux_worker.finished.connect(self.aux_worker.deleteLater)  # delete worker
        self.aux_thread.finished.connect(self.aux_thread.deleteLater)  # delete thread

        # Connecting data related slots
        self.aux_worker.error_signal.connect(lambda err: self.failed_connection_error(err, timeout=False))
        self.aux_worker.result_signal.connect(self.successful_interface_connection)
        self.aux_worker.timeout_signal.connect(lambda err: self.failed_connection_error(err, timeout=True))

        self.aux_thread.start()

    def failed_connection_error(self, e, timeout=False):
        """
        Function to handle a failed connection error (used by aux thread).

        :param e: Error message
        :type e: str
        :param timeout: Whether there was a timeout error
        :type timeout: bool
        """

        if timeout:
            qCritical("Timeout: Connecting to the voltage interface took too long - check your connection settings are correct.")
            QMessageBox.critical(None, "Timeout Error", "Connection took too long. " +
                                            "Connection attempt will continue in the background until termination.")
        else:
            qCritical("Failed to connect to Voltage Controller " + self.voltage_interface_currtype + ": " + str(e))
            qCritical(traceback.print_exc())
            QMessageBox.critical(None, "Error", "Voltage Interface connection failed (see log).")

        self.connected = False
        # Stop connection animation
        self.is_connecting = False
        self.create_connection_button.setEnabled(True)
        self.create_connection_button.setText("Create Connection")

    def successful_interface_connection(self, voltage_interface):
        """
        Function to save a passed voltage interface object (used in aux thread).

        :param voltage_interface: The voltage interface object to save.
        :type voltage_interface: VoltageInterface
        """
        self.voltage_interface = voltage_interface
        self.voltage_hardware = self.voltage_interface
        self.update_voltage_channels()
        # self.sweeps_layout.populate_form()

        qInfo("Successfully connected to " + self.voltage_interface_currtype + ".")
        self.connected = True

        # Stop connection animation
        self.is_connecting = False
        self.create_connection_button.setEnabled(True)

        # Handle UI
        self.create_connection_button.setText("Delete Connection")
        self.voltage_interface_combo.setEnabled(False)
        self.voltage_interface_settings.setEnabled(False)
        self.voltage_interface_settings.hide()
        self.voltage_channels_group.setEnabled(True)

        self.changed_tabs()

    def init_qblox(self, **settings):
        """
        Helper function to initialize a qblox instance given the dictionary of parameters (used in aux thread).

        :param settings: Dictionary of parameters to initialize the qblox instance.
        :type settings: dict
        """
        return QBLOX(**settings)

    def init_yoko(self, **settings):
        """
        Helper function to initialize a yoko instance given the dictionary of parameters (used in aux thread).

        :param settings: Dictionary of parameters to initialize the yoko instance.
        :type settings: dict
        """
        return YOKOGS200(**settings)

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
            single_channel_group.setSpacing(3)
            single_channel_group.setObjectName("single_channel_group")
            channel_label = QLabel(str(i).zfill(2) + " : ")
            channel_label.setStyleSheet("color: #4A90E2;") # TODO: CHANGE TO QSS
            channel_voltage_input = QLineEdit()
            channel_voltage_input.setPlaceholderText("0.0")
            channel_voltage_input.setAlignment(Qt.AlignRight)
            channel_voltage_setbutton = Helpers.create_button("Set", "set_voltage_button", True, shadow=False)
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
        single_channel_group.setSpacing(3)
        single_channel_group.setObjectName("single_channel_group")
        channel_label = QLabel(str(1).zfill(2) + " : ")
        channel_label.setStyleSheet("color: #4A90E2;")
        channel_voltage_input = QLineEdit()
        channel_voltage_input.setPlaceholderText("0.0V")
        channel_voltage_input.setAlignment(Qt.AlignRight)
        channel_voltage_setbutton = Helpers.create_button("Set", "set_voltage_button", True, shadow=False)
        single_channel_group.addWidget(channel_label)
        single_channel_group.addWidget(channel_voltage_input)
        single_channel_group.addWidget(channel_voltage_setbutton)

        channel_voltage_setbutton.clicked.connect(lambda: self.set_voltage(0, channel_voltage_input,
                                                                           channel_voltage_setbutton))
        self.yoko_channel_list_layout.addLayout(single_channel_group)

    def update_voltage_channels(self):
        """
        With the voltage interface connection, it retrieves all the current voltages of all channels to display.
        """

        if self.connected and self.voltage_interface is not None:
            if self.voltage_interface_currtype == "Yoko":
                channel_voltage_input = self.yoko_channel_list_layout.itemAt(0).layout().itemAt(1).widget()
                channel_voltage_input.setPlaceholderText(str(self.voltage_interface.GetVoltage()) + "V")
            else:
                for i in range(16):
                    channel_voltage_input = self.qblox_channel_list_layout.itemAt(i).layout().itemAt(1).widget()
                    channel_voltage_input.setPlaceholderText(str(self.voltage_interface.get_voltage(i)) + "V")

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
                set_button.setText("Setting")
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

