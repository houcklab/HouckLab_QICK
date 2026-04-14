"""
===============
VoltagePanel.py
===============

The home of a voltage controller interface panel for Qblox and Yoko hardware.

This module provides a GUI panel for manual voltage control across multiple
channels, supporting both Qblox (16-channel DAC) and Yokogawa GS200 (single-channel)
voltage sources. The panel allows users to:

- Select and configure voltage interface hardware
- Connect/disconnect from hardware with visual feedback
- Set voltages on individual channels with range validation
- View current voltage values across all channels

.. note::

    Sweeps functionality and passing a reference of the voltage interface
    are only supported for ExperimentPlus experiments. The sweeps UI code
    is currently commented out. Sweeps should instead be done within experiment
    files

:var visa: PyVISA module for VISA instrument communication (used by Yoko).

.. seealso::

    :class:`VoltageInterface` - Base class for voltage hardware interfaces.
    :class:`YOKOGS200` - Yokogawa GS200 driver.
    :class:`QBLOX` - Qblox DAC driver.
"""

from __future__ import annotations

import pyvisa as visa
import json
import ast
import time
import numpy as np
import traceback
from typing import Any, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

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

    This panel provides a complete interface for connecting to and controlling
    voltage source hardware. It supports both Qblox (16-channel DAC) and
    Yokogawa GS200 (single-channel) instruments.

    :cvar yoko_settings: Default settings for Yokogawa GS200 connection.
    :vartype yoko_settings: Dict[str, str]

    :cvar qblox_settings: Default settings for Qblox connection.
    :vartype qblox_settings: Dict[str, Any]

    :cvar range_numbers: Mapping of Qblox range_num to [min, max] voltage limits.
    :vartype range_numbers: Dict[int, List[float]]

    :ivar connected: Whether a voltage interface is currently connected.
    :vartype connected: bool

    :ivar voltage_interface: The active voltage interface connection, or None.
    :vartype voltage_interface: Optional[VoltageInterface]

    :ivar voltage_hardware: The hardware reference passed to experiments
        (usually same as voltage_interface).
    :vartype voltage_hardware: Optional[VoltageInterface]

    :ivar range: Current voltage range as [min, max] list.
    :vartype range: List[float]

    :ivar parent: Parent widget reference.
    :vartype parent: QWidget

    :ivar config_tree_panel: Reference to the configuration tree panel for
        updating config values via the UI.
    :vartype config_tree_panel: QConfigTreePanel

    :ivar current_tab: Reference to the current experiment tab.
    :vartype current_tab: QQuarkTab

    :ivar main_layout: The main vertical layout containing all components.
    :vartype main_layout: QVBoxLayout

    :ivar interface_connect_layout: Layout for connection controls.
    :vartype interface_connect_layout: QVBoxLayout

    :ivar voltage_interface_combo: Dropdown to select voltage interface type.
    :vartype voltage_interface_combo: QComboBox

    :ivar voltage_interface_currtype: Currently selected interface type string.
    :vartype voltage_interface_currtype: str

    :ivar voltage_interface_settings: Text editor for JSON connection settings.
    :vartype voltage_interface_settings: QTextEdit

    :ivar create_connection_button: Button to create/delete connection.
    :vartype create_connection_button: QPushButton

    :ivar controller_content: Widget containing channel controls.
    :vartype controller_content: QWidget

    :ivar controller_layout: Layout for controller content.
    :vartype controller_layout: QVBoxLayout

    :ivar voltage_channels_group: Group box containing channel controls.
    :vartype voltage_channels_group: QGroupBox

    :ivar voltage_channels_layout: Layout inside the channels group box.
    :vartype voltage_channels_layout: QVBoxLayout

    :ivar voltage_range_label: Label showing current voltage range.
    :vartype voltage_range_label: QLabel

    :ivar channel_scroll_area: Scroll area for channel list.
    :vartype channel_scroll_area: QScrollArea

    :ivar channel_list: Widget containing channel layouts.
    :vartype channel_list: QWidget

    :ivar channel_list_layout: Layout for channel list.
    :vartype channel_list_layout: QVBoxLayout

    :ivar qblox_channel_list: Widget containing Qblox channel controls.
    :vartype qblox_channel_list: QWidget

    :ivar qblox_channel_list_layout: Layout for Qblox channels.
    :vartype qblox_channel_list_layout: QVBoxLayout

    :ivar yoko_channel_list: Widget containing Yoko channel control.
    :vartype yoko_channel_list: QWidget

    :ivar yoko_channel_list_layout: Layout for Yoko channel.
    :vartype yoko_channel_list_layout: QVBoxLayout

    :ivar is_connecting: Flag indicating connection attempt in progress.
    :vartype is_connecting: bool

    :ivar connecting_dot_count: Counter for connection animation dots.
    :vartype connecting_dot_count: int

    :ivar aux_thread: Background thread for connection operations.
    :vartype aux_thread: QThread

    :ivar aux_worker: Worker object running in aux_thread.
    :vartype aux_worker: AuxiliaryThread

    .. note::

        The sweeps functionality (``sweeps_group``, ``sweeps_layout``) is
        currently commented out in the implementation. This appears to be
        planned functionality for voltage sweep operations.
    """

    #: Default Yokogawa GS200 VISA connection settings.
    #: Modify this dictionary to change default values.
    yoko_settings: Dict[str, str] = {
        "VISAaddress": "USB0::0x0B21::0x0039::91S929901::0::INSTR",
    }

    #: Default Qblox connection settings.
    #: Modify this dictionary to change default values.
    #:
    #: .. note::
    #:
    #:     The ``range_num`` parameter determines the voltage range:
    #:
    #:     - 0: 0 to 4V (unipolar)
    #:     - 2: -4 to 4V (bipolar, default)
    #:     - 4: -2 to 2V (bipolar)
    qblox_settings: Dict[str, Any] = {
        "range_num": 2,
        "module": 2,
        "reset_voltages": False,
        "num_dacs": 16,
        "ramp_step": 0.003,
        "ramp_interval": 0.05,
        "COM_speed": 1e6,
        "port": 'COM3',
        "timeout": 1
    }

    #: Mapping of Qblox range_num values to [min, max] voltage ranges.
    #:
    #: - 0: range_4V_uni (span 0) → [0, 4]
    #: - 2: range_4V_bi (span 2) → [-4, 4] (default)
    #: - 4: range_2V_bi (span 4) → [-2, 2]
    range_numbers: Dict[int, List[float]] = {
        0: [0, 4],
        2: [-4, 4],
        4: [-2, 2]
    }

    def __init__(
        self,
        config_tree_panel: Any,
        current_Tab: Any,
        parent: QWidget
    ) -> None:
        """
        Initialize the custom QWidget class that is the Voltage Panel.

        :param config_tree_panel: The configuration tree panel for updating
            config values via the UI.
        :type config_tree_panel: QConfigTreePanel
        :param current_Tab: The current experiment tab widget.
        :type current_Tab: QQuarkTab
        :param parent: The parent widget.
        :type parent: QWidget
        """
        super(QVoltagePanel, self).__init__(parent)

        self.connected: bool = False
        self.voltage_interface: Optional[VoltageInterface] = None  # the interface used to control voltages
        self.voltage_hardware: Optional[VoltageInterface] = None  # the hardware to send to the experiment
        self.range: List[float] = [-4, 4]  # default bipolar range
        self.parent: QWidget = parent

        # Storing the config tree in order to change its config values via the UI
        self.config_tree_panel: Any = config_tree_panel
        self.current_tab: Any = current_Tab

        # Set size policy - allow horizontal expansion, prefer vertical
        sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        sizepolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sizepolicy)
        self.setMinimumSize(QSize(175, 0))
        self.setObjectName("voltage_controller_panel")

        # The main layout that will hold all components
        self.main_layout: QVBoxLayout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 5, 0, 0)
        self.main_layout.setSpacing(2)

        # === Interface connection controls ===
        self.interface_connect_layout: QVBoxLayout = QVBoxLayout()
        self.interface_connect_layout.setContentsMargins(5, 5, 5, 0)
        self.interface_connect_layout.setSpacing(5)
        self.interface_connect_layout.setObjectName("interface_button_layout")

        # Voltage source combo box and connection button
        self.voltage_interface_combo: QComboBox = QComboBox(self)
        self.voltage_interface_combo.setObjectName("voltage_interface_combo")
        self.voltage_interface_combo.addItems(["Qblox", "Yoko"])
        self.voltage_interface_currtype: str = "Qblox"

        # JSON settings text editor
        self.voltage_interface_settings: QTextEdit = QTextEdit(self)
        self.voltage_interface_settings.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.voltage_interface_settings.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.voltage_interface_settings.setMaximumHeight(60)
        self.voltage_interface_settings.setObjectName("voltage_interface_settings")
        self.setup_voltage_interface_settings()

        self.create_connection_button = Helpers.create_button(
            "Create Connection", "create_connection_button", True, self
        )

        self.interface_connect_layout.addWidget(self.voltage_interface_combo)
        self.interface_connect_layout.addWidget(self.voltage_interface_settings)
        self.interface_connect_layout.addWidget(self.create_connection_button)

        # === Controller Content Widget ===
        self.controller_content: QWidget = QWidget(self)
        self.controller_layout: QVBoxLayout = QVBoxLayout(self.controller_content)
        self.controller_layout.setContentsMargins(0, 5, 0, 0)
        self.controller_layout.setSpacing(10)

        # === Voltage Channels Section ===
        self.voltage_channels_group: QGroupBox = QGroupBox("Channels")
        self.voltage_channels_group.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignTop)
        self.voltage_channels_group.setObjectName("voltage_channels_group")
        self.voltage_channels_group.setMinimumHeight(100)

        # Contains all channel components
        self.voltage_channels_layout: QVBoxLayout = QVBoxLayout(self.voltage_channels_group)
        self.voltage_channels_layout.setContentsMargins(0, 5, 0, 0)
        self.voltage_channels_layout.setSpacing(5)
        self.voltage_channels_layout.setObjectName("voltage_channels_layout")

        self.voltage_range_label: QLabel = QLabel("  Voltage Range: [0,0]")
        self.voltage_range_label.setObjectName("voltage_range_label")
        self.voltage_channels_layout.addWidget(self.voltage_range_label)

        # Scroll area to contain list of channels
        self.channel_scroll_area: QScrollArea = QScrollArea()
        self.channel_scroll_area.setObjectName("channel_scroll_area")
        self.channel_scroll_area.setFrameShape(QFrame.NoFrame)
        self.channel_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_scroll_area.setWidgetResizable(True)

        # Widget + layout to put into the scroll area (contains both qblox and yoko)
        self.channel_list: QWidget = QWidget()
        self.channel_list.setObjectName("channel_list")
        self.channel_list_layout: QVBoxLayout = QVBoxLayout()
        self.channel_list_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_list_layout.setSpacing(2)
        self.channel_list.setLayout(self.channel_list_layout)

        # === Qblox channel list (16 channels) ===
        self.qblox_channel_list: QWidget = QWidget()
        self.qblox_channel_list.setObjectName("qblox_channel_list")
        self.qblox_channel_list_layout: QVBoxLayout = QVBoxLayout()
        self.qblox_channel_list_layout.setContentsMargins(5, 0, 10, 0)
        self.qblox_channel_list_layout.setSpacing(5)
        self.qblox_channel_list_layout.setObjectName("qblox_channel_list_layout")
        self.qblox_channel_list.setLayout(self.qblox_channel_list_layout)

        # === Yoko channel list (single channel) ===
        self.yoko_channel_list: QWidget = QWidget()
        self.yoko_channel_list.setObjectName("yoko_channel_list")
        self.yoko_channel_list_layout: QVBoxLayout = QVBoxLayout()
        self.yoko_channel_list_layout.setContentsMargins(5, 0, 10, 0)
        self.yoko_channel_list_layout.setSpacing(5)
        self.yoko_channel_list_layout.setObjectName("yoko_channel_list_layout")
        self.yoko_channel_list.setLayout(self.yoko_channel_list_layout)
        self.yoko_channel_list.hide()  # Hidden by default since Qblox is default

        self.channel_list_layout.addWidget(self.qblox_channel_list)
        self.channel_list_layout.addWidget(self.yoko_channel_list)

        self.channel_scroll_area.setWidget(self.channel_list)
        # Adding it all to voltage_channels_layout
        self.voltage_channels_layout.addWidget(self.channel_scroll_area)
        self.voltage_channels_group.setLayout(self.voltage_channels_layout)

        self.setup_voltage_channels()

        # === Sweeps Section (currently disabled) ===
        # NOTE: The sweeps functionality is commented out. This appears to be
        # planned functionality for voltage sweep operations that would integrate
        # with the experiment system.
        # self.sweeps_group = QGroupBox("Voltage Config (Sweeps)")
        # self.sweeps_group.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignTop)
        # self.sweeps_group.setObjectName("sweeps_group")
        # self.sweeps_group.setFixedHeight(125)
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

    def setup_signals(self) -> None:
        """
        Set up all the signals and slots of the Voltage Panel.

        Connects:

        - voltage_interface_combo.currentIndexChanged → handle_voltInterface_change
        - create_connection_button.clicked → toggle_create_connection

        Also disables the voltage channels group until a connection is made.
        """
        self.voltage_channels_group.setEnabled(False)
        # self.sweeps_group.setEnabled(False)

        self.voltage_interface_combo.currentIndexChanged.connect(self.handle_voltInterface_change)
        self.create_connection_button.clicked.connect(self.toggle_create_connection)

    def handle_voltInterface_change(self, index: int) -> None:
        """
        Handle when the user changes the voltage interface type.

        Switches between Qblox and Yoko channel displays and updates
        the settings text field with appropriate defaults.

        :param index: The index of the selection made in the combo box.
            Not used directly - the current text is read from the combo box.
        :type index: int
        """
        self.voltage_interface_currtype = self.voltage_interface_combo.currentText()

        if self.voltage_interface_currtype == "Yoko":
            self.yoko_channel_list.show()
            self.qblox_channel_list.hide()
            self.voltage_channels_group.setMaximumHeight(100)
        else:
            self.yoko_channel_list.hide()
            self.qblox_channel_list.show()
            # 16777215 is Qt's QWIDGETSIZE_MAX - effectively removes height constraint
            self.voltage_channels_group.setMaximumHeight(16777215)

        self.setup_voltage_interface_settings()

    def toggle_create_connection(self) -> None:
        """
        Toggle the create connection button between create and delete modes.

        Ensures we are not creating multiple instances of voltage interfaces.
        When creating, starts the connection animation and initiates the
        connection in a background thread. When deleting, disconnects and
        re-enables the UI for a new connection.
        """
        current_text: str = self.create_connection_button.text()

        if current_text == "Create Connection":
            # Begin connection animation
            self.is_connecting: bool = True
            self.connecting_dot_count: int = 0
            self.animate_connecting()
            self.create_connection_button.setEnabled(False)

            # Attempt a connection in background thread
            self.create_connection()

        else:
            # Attempt a disconnection - reset UI to initial state
            self.create_connection_button.setText("Create Connection")
            self.voltage_interface_combo.setEnabled(True)
            self.voltage_interface_settings.setEnabled(True)
            self.voltage_interface_settings.show()
            self.voltage_channels_group.setEnabled(False)
            # self.sweeps_group.setEnabled(False)

            self.delete_connection()

    def animate_connecting(self) -> None:
        """
        Animate the connection button to show progress.

        Cycles through "Connecting", "Connecting.", "Connecting..",
        "Connecting..." with a 500ms interval while ``is_connecting``
        is True.
        """
        if self.is_connecting:
            # Update the label with the current number of dots (cycles 0-3)
            self.create_connection_button.setText(f"Connecting{'.' * (self.connecting_dot_count)}")
            self.connecting_dot_count = (self.connecting_dot_count + 1) % 4
            QTimer.singleShot(500, self.animate_connecting)

    def changed_tabs(self, current_tab: Optional[Any] = None) -> None:
        """
        Handle experiment tab changes.

        Called when the experiment tab is changed. Updates the current tab
        reference and could enable/disable sweeps functionality based on
        experiment type.

        :param current_tab: The tab object of the current tab, or None to
            keep the existing reference.
        :type current_tab: Optional[QQuarkTab]
        """
        if current_tab is not None:
            self.current_tab = current_tab
        # self.sweeps_group.setEnabled(False)

    def setup_voltage_interface_settings(self) -> None:
        """
        Set up the voltage interface settings with default values.

        Populates the settings text editor with JSON-formatted default
        settings for either Yoko or Qblox based on current selection.

        .. note::

            The JSON formatting removes the outer braces and adds them back
            when parsing, which allows users to edit just the inner content.
            This is a somewhat fragile approach.
        """
        self.voltage_interface_settings.clear()
        width: int = self.voltage_interface_settings.width()

        if self.voltage_interface_currtype == "Yoko":
            formatted_json: str = json.dumps(self.yoko_settings, indent=2)
            # Remove outer braces for display (they're added back when parsing)
            self.voltage_interface_settings.setText(str(formatted_json)[2:-2])
        else:
            formatted_json = json.dumps(self.qblox_settings, indent=2)
            self.voltage_interface_settings.setText(str(formatted_json)[2:-2])

        self.voltage_interface_settings.adjustSize()
        self.voltage_interface_settings.resize(width, 60)

    def create_connection(self) -> Optional[bool]:
        """
        Create a new connection to the selected voltage interface.

        Parses the settings from the text editor, validates the JSON format,
        and starts a background thread to initialize the hardware connection.

        :returns: False if JSON parsing fails, None otherwise (result comes
            via signal from background thread).
        :rtype: Optional[bool]

        :raises json.JSONDecodeError: Caught internally - shows error dialog.

        .. note::

            The actual connection happens in a background thread via
            :class:`AuxiliaryThread`. Success/failure is communicated via
            signals to :meth:`successful_interface_connection` or
            :meth:`failed_connection_error`.
        """
        # NOTE: Commented code below was used for testing/bypassing connection
        # self.successful_interface_connection(None)
        # return

        self.create_connection_button.setText("Creating...")

        # Retrieve the textedit settings and wrap in braces for valid JSON
        settings: str = "{" + self.voltage_interface_settings.toPlainText() + "}"
        try:
            if self.voltage_interface_currtype == "Yoko":
                self.yoko_settings = json.loads(settings)
                self.range = [0, 1.3]  # Manually set max for Yoko
            else:
                self.qblox_settings = json.loads(settings)
                self.range = self.range_numbers[self.qblox_settings["range_num"]]
            self.voltage_range_label.setText("  Voltage Range " + str(self.range))
        except json.JSONDecodeError as e:
            qCritical("Invalid settings format:" + str(e))
            QMessageBox.critical(self, "Error", f"Invalid settings format.")
            return False

        # Start an auxiliary thread to make the connection
        # This prevents the UI from freezing during potentially slow hardware init
        self.aux_thread: QThread = QThread()
        if self.voltage_interface_currtype == "Yoko":
            temp_yoko_settings: Dict[str, Any] = self.yoko_settings.copy()
            temp_yoko_settings["rm"] = visa.ResourceManager()
            self.aux_worker: AuxiliaryThread = AuxiliaryThread(
                target_func=self.init_yoko,
                func_kwargs=temp_yoko_settings,
                timeout=5
            )
        else:
            self.aux_worker = AuxiliaryThread(
                target_func=self.init_qblox,
                func_kwargs=self.qblox_settings,
                timeout=45  # Qblox has longer timeout due to ramp operations
            )
        self.aux_worker.moveToThread(self.aux_thread)

        # Connecting thread lifecycle signals
        self.aux_thread.started.connect(self.aux_worker.run)
        self.aux_worker.finished.connect(self.aux_thread.quit)
        self.aux_worker.finished.connect(self.aux_worker.deleteLater)
        self.aux_thread.finished.connect(self.aux_thread.deleteLater)

        # Connecting data/result signals
        self.aux_worker.error_signal.connect(
            lambda err: self.failed_connection_error(err, timeout=False)
        )
        self.aux_worker.result_signal.connect(self.successful_interface_connection)
        self.aux_worker.timeout_signal.connect(
            lambda err: self.failed_connection_error(err, timeout=True)
        )

        self.aux_thread.start()

    def failed_connection_error(self, e: str, timeout: bool = False) -> None:
        """
        Handle a failed connection error from the auxiliary thread.

        Shows an error dialog and resets the connection button to allow
        retry attempts.

        :param e: Error message describing the failure.
        :type e: str
        :param timeout: Whether the failure was due to a timeout.
        :type timeout: bool
        """
        if timeout:
            qCritical("Timeout: Connecting to the voltage interface took too long - "
                     "check your connection settings are correct.")
            QMessageBox.critical(
                None,
                "Timeout Error",
                "Connection took too long. Connection attempt will continue "
                "in the background until termination."
            )
        else:
            qCritical("Failed to connect to Voltage Controller " +
                     self.voltage_interface_currtype + ": " + str(e))
            qCritical(traceback.format_exc())
            QMessageBox.critical(None, "Error", "Voltage Interface connection failed (see log).")

        self.connected = False
        # Stop connection animation and re-enable button
        self.is_connecting = False
        self.create_connection_button.setEnabled(True)
        self.create_connection_button.setText("Create Connection")

    def successful_interface_connection(self, voltage_interface: VoltageInterface) -> None:
        """
        Handle a successful voltage interface connection.

        Saves the connected interface, updates the UI to show connection
        status, and refreshes the channel voltage displays.

        :param voltage_interface: The successfully connected voltage interface.
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

        # Update UI to reflect connected state
        self.create_connection_button.setText("Delete Connection")
        self.voltage_interface_combo.setEnabled(False)
        self.voltage_interface_settings.setEnabled(False)
        self.voltage_interface_settings.hide()
        self.voltage_channels_group.setEnabled(True)

        self.changed_tabs()

    def init_qblox(self, **settings: Any) -> QBLOX:
        """
        Initialize a Qblox instance with the given parameters.

        This is called from the auxiliary thread to perform the actual
        hardware initialization.

        :param settings: Dictionary of parameters to initialize the Qblox.
        :type settings: Any

        :returns: The initialized QBLOX instance.
        :rtype: QBLOX
        """
        return QBLOX(**settings)

    def init_yoko(self, **settings: Any) -> YOKOGS200:
        """
        Initialize a Yokogawa GS200 instance with the given parameters.

        This is called from the auxiliary thread to perform the actual
        hardware initialization.

        :param settings: Dictionary of parameters including the ResourceManager.
        :type settings: Any

        :returns: The initialized YOKOGS200 instance.
        :rtype: YOKOGS200
        """
        return YOKOGS200(**settings)

    def delete_connection(self) -> None:
        """
        Delete the connection to the voltage interface.

        Deletes the voltage_interface variable and sets the reference to None.
        This allows Python's garbage collector to clean up the hardware
        connection resources.
        """
        self.connected = False
        del self.voltage_interface
        self.voltage_interface = None
        qInfo("Successfully disconnected from Voltage Controller")

    def setup_voltage_channels(self) -> None:
        """
        Set up the UI for the voltage channels for both Qblox and Yoko.

        Creates 16 channel rows for Qblox (channels 1-16) and 1 channel
        row for Yoko. Each row contains a label, voltage input field,
        and Set button.

        .. note::

            The lambda capture pattern with default arguments
            ``lambda _, ch=i, input_box=channel_voltage_input, ...``
            is used to avoid the late binding issue where all lambdas
            would otherwise reference the final loop value.

        .. note::

            Channel numbers displayed to user are 1-indexed, but the
            internal channel parameter passed to ``set_voltage`` is
            0-indexed (ch-1).
        """
        # === Create Qblox channels (16 channels) ===
        for i in range(1, 17):
            single_channel_group = QHBoxLayout()
            single_channel_group.setSpacing(3)
            single_channel_group.setObjectName("single_channel_group")

            # Channel label with 2-digit zero-padded number
            channel_label = QLabel(str(i).zfill(2) + " : ")
            # TODO: Move this color to QSS stylesheet
            channel_label.setStyleSheet("color: #4A90E2;")

            channel_voltage_input = QLineEdit()
            channel_voltage_input.setPlaceholderText("0.0")
            channel_voltage_input.setAlignment(Qt.AlignRight)

            channel_voltage_setbutton = Helpers.create_button(
                "Set", "set_voltage_button", True, shadow=False
            )

            single_channel_group.addWidget(channel_label)
            single_channel_group.addWidget(channel_voltage_input)
            single_channel_group.addWidget(channel_voltage_setbutton)

            # Use default arguments in the lambda to capture the current loop variables
            # This avoids the late binding issue where all lambdas would otherwise
            # reference the final loop value (i=16)
            channel_voltage_setbutton.clicked.connect(
                lambda _, ch=i, input_box=channel_voltage_input, set_button=channel_voltage_setbutton:
                    self.set_voltage(ch - 1, input_box, set_button)
            )
            self.qblox_channel_list_layout.addLayout(single_channel_group)

        # === Create Yoko channel (single channel) ===
        single_channel_group = QHBoxLayout()
        single_channel_group.setSpacing(3)
        single_channel_group.setObjectName("single_channel_group")

        channel_label = QLabel(str(1).zfill(2) + " : ")
        channel_label.setStyleSheet("color: #4A90E2;")

        channel_voltage_input = QLineEdit()
        channel_voltage_input.setPlaceholderText("0.0V")
        channel_voltage_input.setAlignment(Qt.AlignRight)

        channel_voltage_setbutton = Helpers.create_button(
            "Set", "set_voltage_button", True, shadow=False
        )

        single_channel_group.addWidget(channel_label)
        single_channel_group.addWidget(channel_voltage_input)
        single_channel_group.addWidget(channel_voltage_setbutton)

        channel_voltage_setbutton.clicked.connect(
            lambda: self.set_voltage(0, channel_voltage_input, channel_voltage_setbutton)
        )
        self.yoko_channel_list_layout.addLayout(single_channel_group)

    def update_voltage_channels(self) -> None:
        """
        Update the voltage channel displays with current hardware values.

        Retrieves all current voltages from the connected voltage interface
        and updates the placeholder text of each channel's input field.
        """
        if self.connected and self.voltage_interface is not None:
            if self.voltage_interface_currtype == "Yoko":
                # Yoko has only one channel
                channel_voltage_input = self.yoko_channel_list_layout.itemAt(0).layout().itemAt(1).widget()
                channel_voltage_input.setPlaceholderText(str(self.voltage_interface.GetVoltage()) + "V")
            else:
                # Qblox has 16 channels
                for i in range(16):
                    channel_voltage_input = self.qblox_channel_list_layout.itemAt(i).layout().itemAt(1).widget()
                    channel_voltage_input.setPlaceholderText(str(self.voltage_interface.get_voltage(i)) + "V")

    def set_voltage(
        self,
        channel: int,
        voltage_input: QLineEdit,
        set_button: Any
    ) -> None:
        """
        Set voltage on the specified channel of the connected interface.

        Validates the voltage against the current range before setting.
        Provides visual feedback via the Set button text during operation.

        :param channel: Zero-indexed channel number to set.
        :type channel: int
        :param voltage_input: The QLineEdit containing the voltage value.
        :type voltage_input: QLineEdit
        :param set_button: The Set button to update with status text.
        :type set_button: QPushButton

        :raises ValueError: If voltage_input text cannot be converted to float.
        """
        text = voltage_input.text().strip()
        try:
            voltage: float = float(text)
        except ValueError:
            # handle error: show message, default value, return early, etc.
            QMessageBox.warning(self, "Invalid input", "Voltage must be a number.")
            return

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
                # Reset button text after 2 seconds
                QTimer.singleShot(2000, lambda: set_button.setText('Set'))
            except Exception as e:
                qCritical("Failed to set voltage: " + str(e))
                QMessageBox.critical(self, "Error", "Failed to set voltage.")
        else:
            # This should never be called if UI state is managed correctly
            qCritical("No connected voltage interface.")