"""
===============
VoltagePanel.py
===============
The home of a voltage controller interface panel [Qbox and Yoko].

Allows for an easy space to manually set voltages by channel and perform basic uniform sweeps.
Sweeps functionality and passing a reference of the voltage interface are only supported for ExperimentT2 experiments.
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
    QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog
)

import scripts.Helpers as Helpers
from scripts.AuxiliaryThread import AuxiliaryThread

from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface
from MasterProject.Client_modules.Quarky_GUI.PythonDrivers.YOKOGS200 import YOKOGS200
from MasterProject.Client_modules.Quarky_GUI.PythonDrivers.QBLOX import QBLOX
from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentT2 import ExperimentClassT2

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
        self.channel_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_scroll_area.setWidgetResizable(True)
        # Widget + layout to put into the scroll area (one for qblox, one for yoko)
        self.channel_list = QWidget()
        self.channel_list_layout = QVBoxLayout()
        self.channel_list_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_list_layout.setSpacing(0)
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
        self.sweeps_group = QGroupBox("Voltage Config (Sweeps)")
        self.sweeps_group.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignTop)
        self.sweeps_group.setObjectName("sweeps_group")
        # self.sweeps_group.setMinimumHeight(200)
        self.sweeps_group.setFixedHeight(125)

        self.sweeps_layout = VoltageSweepBox(self.config_tree_panel, self.voltage_interface_combo, self)
        self.sweeps_group.setLayout(self.sweeps_layout)

        # Adding to controller
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
            self.sweeps_group.setEnabled(False)

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
        self.sweeps_group.setEnabled(False)

        if self.connected and self.current_tab.experiment_obj is not None:
            if self.current_tab.experiment_obj.experiment_type == ExperimentClassT2:
                hardware_req = self.current_tab.experiment_obj.experiment_hardware_req
                if any(issubclass(cls, VoltageInterface) for cls in hardware_req):
                    self.sweeps_group.setEnabled(True)
                    # self.config_tree_panel.populate_tree(False)

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
        self.sweeps_layout.populate_channel_dropdown()

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
        self.config_tree_panel.populate_tree()
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

    def update_sweeps(self):
        """
        If Experiment offers a Voltage Config (sweeps), we populate the sweep section with editable configs.
        """
        self.sweeps_layout.populate_form()

class VoltageSweepBox(QVBoxLayout):
    """
    A custom QVBoxLayout layout that contains the form for voltage sweep functionality.

    This part of the GUI is still relatively experimental. It is recommended for now to just create regular ExperimentClass
    experiments that perform a connection themselves and sweep.
    """

    def __init__(self, config_tree_panel, voltage_interface_combo, parent):
        super().__init__()
        self.config_tree_panel = config_tree_panel
        self.voltage_interface_combo = voltage_interface_combo
        self.parent = parent

        self.setContentsMargins(0, 5, 0, 5)
        self.setSpacing(1)
        self.setObjectName("sweeps_layout")

        # Voltage Sweep Form
        self.sweep_form_layout = QFormLayout()
        self.sweep_form_layout.setContentsMargins(0, 0, 0, 0)
        self.sweep_form_layout.setVerticalSpacing(2)
        self.sweep_form_layout.setObjectName("form_layout")

        # self.channel_dropdown_label = QLabel()
        # self.channel_dropdown_label.setText("Channel: ")
        # self.channel_dropdown_label.setObjectName("channel_dropdown_label")
        # self.sweep_form_layout.setWidget(0, QFormLayout.LabelRole, self.channel_dropdown_label)
        # self.channel_dropdown = QComboBox()
        # self.channel_dropdown.setFixedWidth(70)
        # self.sweep_form_layout.setWidget(0, QFormLayout.FieldRole, self.channel_dropdown)

        self.dacs_label = QLabel()
        self.dacs_label.setText("DACs: ")
        self.dacs_label.setObjectName("dacs_label")
        self.sweep_form_layout.setWidget(1, QFormLayout.LabelRole, self.dacs_label)
        self.dacs_edit = QLineEdit()
        self.dacs_edit.setObjectName("dacs_edit")
        self.sweep_form_layout.setWidget(1, QFormLayout.FieldRole, self.dacs_edit)

        self.start_label = QLabel()
        self.start_label.setText("Start: ")
        self.start_label.setObjectName("start_label")
        self.sweep_form_layout.setWidget(2, QFormLayout.LabelRole, self.start_label)
        self.start_edit = QLineEdit()
        self.start_edit.setObjectName("start_edit")
        self.sweep_form_layout.setWidget(2, QFormLayout.FieldRole, self.start_edit)

        self.stop_label = QLabel()
        self.stop_label.setText("Stop: ")
        self.stop_label.setObjectName("stop_label")
        self.sweep_form_layout.setWidget(3, QFormLayout.LabelRole, self.stop_label)
        self.stop_edit = QLineEdit()
        self.stop_edit.setObjectName("stop_edit")
        self.sweep_form_layout.setWidget(3, QFormLayout.FieldRole, self.stop_edit)

        self.numPoints_label = QLabel()
        self.numPoints_label.setText("#Points: ")
        self.numPoints_label.setObjectName("numPoints_label")
        self.sweep_form_layout.setWidget(4, QFormLayout.LabelRole, self.numPoints_label)
        self.numPoints_edit = QLineEdit()
        self.numPoints_edit.setObjectName("numPoints_edit")
        self.sweep_form_layout.setWidget(4, QFormLayout.FieldRole, self.numPoints_edit)

        self.addLayout(self.sweep_form_layout)

        self.setup_signals()

    def setup_signals(self):
        self.populate_form()
        # self.channel_dropdown.currentIndexChanged.connect(self.on_channel_edited)
        self.dacs_edit.editingFinished.connect(self.on_dacs_edited)
        self.start_edit.editingFinished.connect(self.on_start_edited)
        self.stop_edit.editingFinished.connect(self.on_stop_edited)
        self.numPoints_edit.editingFinished.connect(self.on_num_points_edited)

    # def populate_channel_dropdown(self):
    #     self.voltage_interface_currtype = self.voltage_interface_combo.currentText()
    #     self.channel_dropdown.clear()
    #     self.channel_dropdown.addItem(str("None"))
    #
    #     if self.voltage_interface_currtype == "Yoko":
    #         self.channel_dropdown.addItem(str("Yoko"))
    #     else:
    #         num_channels = 16
    #         for i in range(num_channels):
    #             self.channel_dropdown.addItem(str(i+1))

    def populate_form(self):
        # self.populate_channel_dropdown()
        if "DACs" in self.config_tree_panel.config["Experiment Config"]:
            self.start_edit.setText(str(self.config_tree_panel.config["Experiment Config"]["DACs"])[1:-1])
        else:
            self.start_edit.setText("")

        if "VoltageStart" in self.config_tree_panel.config["Experiment Config"]:
            self.start_edit.setText(str(self.config_tree_panel.config["Experiment Config"]["VoltageStart"]))
        else:
            self.start_edit.setText(str(0.0))

        if "VoltageStop" in self.config_tree_panel.config["Experiment Config"]:
            self.stop_edit.setText(str(self.config_tree_panel.config["Experiment Config"]["VoltageStop"]))
        else:
            self.stop_edit.setText(str(0.0))

        if "VoltageNumPoints" in self.config_tree_panel.config["Experiment Config"]:
            self.numPoints_edit.setText(str(self.config_tree_panel.config["Experiment Config"]["VoltageNumPoints"]))
        else:
            self.numPoints_edit.setText(str(0))

    # def on_channel_edited(self):
    #     try:
    #         channel = self.channel_dropdown.currentText()
    #         if channel == "None" or channel == "Yoko" or not channel:
    #             self.parent.voltage_hardware = self.parent.voltage_interface
    #         else:
    #             value = int(channel)
    #             self.parent.voltage_hardware = self.parent.voltage_interface
    #             # try:
    #             #     self.parent.voltage_hardware = self.parent.voltage_interface.channels[(value-1)]
    #             # except:
    #             #     raise ValueError
    #     except ValueError:
    #         QMessageBox.critical(self.parent, "Error", "Something went wrong when setting channel.")
    #         qDebug(f"Something went wrong when setting the voltage channel to sweep.")
    #         self.channel_dropdown.setCurrentIndex(0)

    def on_dacs_edited(self):
        try:
            # Get the string of numbers from the text edit field
            dacs = self.dacs_edit.text()
            dacs_list = [int(x.strip()) for x in dacs.split(',')]

            if self.voltage_interface_currtype == "Yoko":
                if dacs in dacs_list:
                    if not (dacs != 1):
                        raise ValueError
            else:
                for dac in dacs_list:
                    if not (1 <= dac <= 16):
                        raise ValueError

            self.config_tree_panel.config["Experiment Config"]["DACs"] = dacs_list
            self.config_tree_panel.populate_tree()
        except ValueError:
            # If there's any issue (e.g., a non-number value), raise an error
            qDebug(f"The input is not in the correct format. Please enter a comma-separated list of integers within the channel range. Resetting.")
            self.start_edit.setText(str(self.config_tree_panel.config["Experiment Config"]["DACs"])[1:-1])

    def on_start_edited(self):
        try:
            value = float(self.start_edit.text())
            if value < self.parent.range[0] or value > self.parent.range[1]:
                raise ValueError
            self.config_tree_panel.config["Experiment Config"]["VoltageStart"] = value
            self.config_tree_panel.populate_tree()
        except ValueError:
            qDebug(f"Invalid voltage start value (check range). Resetting.")
            self.start_edit.setText(str(self.config_tree_panel.config["Experiment Config"]["VoltageStart"]))

    def on_stop_edited(self):
        try:
            value = float(self.stop_edit.text())
            if value < self.parent.range[0] or value > self.parent.range[1]:
                raise ValueError
            self.config_tree_panel.config["Experiment Config"]["VoltageStop"] = value
            self.config_tree_panel.populate_tree()
        except ValueError:
            qDebug(f"Invalid voltage stop value. Resetting.")
            self.stop_edit.setText(str(self.config_tree_panel.config["Experiment Config"]["VoltageStop"]))

    def on_num_points_edited(self):
        try:
            value = int(self.numPoints_edit.text())
            self.config_tree_panel.config["Experiment Config"]["VoltageNumPoints"] = value
            self.config_tree_panel.populate_tree()
        except ValueError:
            qDebug(f"Invalid voltage stop value. Resetting.")
            self.numPoints_edit.setText(str(self.config_tree_panel.config["Experiment Config"]["VoltageNumPoints"]))


### CURRENTLY NOT USED
class VoltageSweepTable(QVBoxLayout):
    """
    Prototype sweep table currently not used.
    """
    def __init__(self, config_tree_panel, voltage_interface_combo, parent):
        super().__init__()
        self.config_tree_panel = config_tree_panel
        self.voltage_interface_combo = voltage_interface_combo
        self.parent = parent

        if "Voltage Config" in self.config_tree_panel.config:
            if "Channels" not in self.config_tree_panel.config["Voltage Config"]:
                qCritical("No Channels field found to Voltage Config.")
            elif "VoltageMatrix" not in self.config_tree_panel.config["Voltage Config"]:
                qCritical("No VoltageMatrix field found to Voltage Config.")

        # the channel list is self.config_tree_panel.config["Voltage Config"]["Channels"]
        # the voltage matrix is at self.config_tree_panel.config["Voltage Config"]["VoltageMatrix"]

        self.retrieve_references()

        ### Creating the UI
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(1)
        self.setObjectName("sweeps_layout")

        # Buttons
        self.load_matrix_button = Helpers.create_button("Load", "load_matrix_button", True)
        self.copy_matrix_button = Helpers.create_button("Copy", "copy_matrix_button", True)

        self.toolbar = QHBoxLayout()
        self.toolbar.setContentsMargins(0, 0, 0, 0)
        self.toolbar.setSpacing(0)
        self.toolbar.addWidget(self.load_matrix_button)
        self.toolbar.addWidget(self.copy_matrix_button)

        # Table
        self.table_layout = QHBoxLayout()
        self.table_layout.setContentsMargins(0, 0, 0, 0)
        self.table_layout.setSpacing(0)

        self.channel_table = QTableWidget(self.num_rows, 1)
        self.channel_table.setAlternatingRowColors(True)
        self.channel_table.setColumnWidth(0, 30)
        self.channel_table.horizontalHeader().setStretchLastSection(True)
        self.channel_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_table.setFixedWidth(30)
        self.channel_table.verticalHeader().setVisible(False)
        self.channel_table.setHorizontalHeaderLabels(["Ch"])

        self.voltage_table = QTableWidget(self.num_rows, self.num_cols)
        self.voltage_table.setAlternatingRowColors(True)
        self.voltage_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.voltage_table.setEditTriggers(QTableWidget.AllEditTriggers)
        self.voltage_table.verticalHeader().setVisible(False)
        # self.voltage_table.setVerticalHeaderLabels([f"Ch {channel}" for channel in self.channels])

        self.table_layout.addWidget(self.channel_table)
        self.table_layout.addWidget(self.voltage_table)

        # Adding it all together
        self.addLayout(self.toolbar)
        self.addLayout(self.table_layout)

        self.setup_signals()

    def setup_signals(self):
        self.voltage_table.itemChanged.connect(self.table_edited)
        self.channel_table.itemChanged.connect(self.channel_edited)

        # Sync Scroll
        self.voltage_table.verticalScrollBar().valueChanged.connect(
            self.channel_table.verticalScrollBar().setValue
        )
        self.channel_table.verticalScrollBar().valueChanged.connect(
            self.voltage_table.verticalScrollBar().setValue
        )

        self.load_matrix_button.clicked.connect(self.load_matrix)
        self.copy_matrix_button.clicked.connect(self.copy_matrix)
        pass

    def retrieve_references(self):
        voltage_config = self.config_tree_panel.config.get("Voltage Config")
        if voltage_config:
            self.channels = voltage_config.get("Channels")
            self.matrix = voltage_config.get("VoltageMatrix")
            self.num_rows = len(self.matrix)
            self.num_cols = len(self.matrix[0])
            if self.num_rows != len(self.channels):
                qCritical("Number of rows and channels do not match.")
        else:
            self.channels = []
            self.matrix = [[]]
            self.num_rows = 0
            self.num_cols = 0

    def _set_item(self, row, col, text):
        # Verification
        item = QTableWidgetItem(f"{float(text):.3f}")
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)

        lower, upper = self.parent.range[0], self.parent.range[1]
        if lower != 0 and upper != 0:
            if float(text) < lower or float(text) > upper:
                item.setBackground(QColor("lightcoral"))

        self.voltage_table.setItem(row, col, item)

    def populate_table(self, matrix=None):
        """Populate the table to match the shape of the given matrix."""
        self.retrieve_references()

        # Channel Table
        self.channel_table.clear()
        self.channel_table.setRowCount(self.num_rows)
        self.channel_table.setColumnCount(1)
        self.channel_table.setHorizontalHeaderLabels(["Ch"])
        for i, channel in enumerate(self.channels):
            item = QTableWidgetItem(str(channel))
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
            self.channel_table.setItem(i, 0, item)

        # Voltage Table
        if matrix is not None:
            if (len(matrix) != len(self.matrix) or
                    any(len(self.matrix[0]) != len(self.matrix[i]) for i in range(len(matrix)))):
                qCritical("Error: Matrix dimensions do not match - load aborted.")
                return

            # Truncate extra columns in matrix
            self.num_cols = len(matrix[0])
            for i in range(len(self.matrix)):
                # Truncate or extend each row
                if len(self.matrix[i]) < self.num_cols:
                    self.matrix[i].extend([0.0] * (self.num_cols - len(self.matrix[i])))
                elif len(self.matrix[i]) > self.num_cols:
                    self.matrix[i] = self.matrix[i][:self.num_cols]

            # copy entires over (copying so to preserve the self.matrix reference
            for i in range(len(matrix)):
                for j in range(len(matrix[i])):
                    self.matrix[i][j] = matrix[i][j]

        self.voltage_table.clear()
        self.voltage_table.setRowCount(self.num_rows)
        self.voltage_table.setColumnCount(self.num_cols)

        for row in range(self.num_rows):
            for col in range(self.num_cols):
                value = self.matrix[row][col]
                self._set_item(row, col, value)

        if self.channels and len(self.channels) == self.num_rows:
            self.voltage_table.setVerticalHeaderLabels([f"Ch {channel}" for channel in self.channels])
        self.voltage_table.setEditTriggers(QTableWidget.AllEditTriggers)

    def table_edited(self, item):
        self.voltage_table.blockSignals(True)

        row = item.row()
        col = item.column()

        try:
            value = float(item.text())
            if value < self.parent.range[0] or value > self.parent.range[1]:
                raise ValueError
            self.matrix[row][col] = value
            self._set_item(row, col, value)
        except ValueError:
            # If the conversion fails, reset to a default value
            qDebug(f"Invalid value at row {row}, col {col}, must be in range and a float. Resetting.")
            self._set_item(row, col, self.matrix[row][col])

        self.voltage_table.blockSignals(False)

    def channel_edited(self, item):
        row = item.row()

        try:
            value = int(item.text())
            self.channels[row] = value
        except ValueError:
            # If the conversion fails, reset to a default value
            qDebug(f"Invalid channel at row {row} - resetting.")
            item.setText(str(self.channels[row]))

        # TODO do some verification

    def load_matrix(self):
        self.retrieve_references()

        text, ok = QInputDialog.getMultiLineText(
            self.parent,
            "Load Matrix",
            "Paste matrix in Python syntax (numpy supported): \n e.g., [[1, 2], [3, 4], np.linspace(1,2,2)] :"
        )
        if not ok or not text.strip():
            return

        try:
            safe_globals = {"np": np}
            data = self.convert_to_list_matrix(eval(text.strip(), {"__builtins__": {}}, safe_globals))

            if not isinstance(data, (list, np.ndarray)) or any(not isinstance(row, (list, np.ndarray)) for row in data):
                raise ValueError("Input is not a 2D list.")
            elif len(data) != self.num_rows or any(len(row) != len(data[0]) for row in data):
                QMessageBox.critical(self.parent, f"Matrix must have {self.num_rows} rows and consistent column lengths.")
                return

            self.populate_table(data)
        except Exception as e:
            QMessageBox.critical(self.parent, "Invalid Input", f"Error parsing matrix: {e}")

    def convert_to_list_matrix(self, matrix):
        """
        Recursively converts any numpy arrays in a matrix to lists.
        :param matrix: A list or numpy array that may contain nested lists/arrays.
        :return: A matrix (list of lists) with all numpy arrays converted to lists.
        """
        if isinstance(matrix, np.ndarray):
            matrix = matrix.tolist()

        return [
            row.tolist() if isinstance(row, np.ndarray) else row
            for row in matrix
        ]

    def copy_matrix(self):
        clipboard = QApplication.clipboard()
        temp_matrix = self.convert_to_list_matrix(self.matrix.copy())

        clipboard.setText(str(temp_matrix))
        qInfo("Current voltage matrix copied to clipboard!")

        self.copy_matrix_button.setText('Done!')
        QTimer.singleShot(3000, lambda: self.copy_matrix_button.setText('Copy'))