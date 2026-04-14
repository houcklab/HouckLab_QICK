"""
=======
Desq.py
=======

Main entry point for the Desq GUI application.

This module initializes the GUI, handles application-level logic, and manages interactions between
different components. Desq is a PyQt5-based GUI application for managing superconducting qubit
experiments on RFSoC hardware.

:var BACKEND_MODULE: The matplotlib backend module path for custom plot interception.
:vartype BACKEND_MODULE: str
:var TESTING: Global flag for testing mode. When True, RFSoC connection is not required
    to run experiments. Should be used with mock experiments only.
:vartype TESTING: bool

.. note::
    This module sets up the matplotlib backend before any other matplotlib imports
    to ensure proper plot interception via the custom BackendDesq module.
"""

from __future__ import annotations

import os
import sys
from typing import Optional, List, Any, Dict

# Ensure our custom backend modules are importable
script_directory = os.path.dirname(os.path.realpath(__file__))
if script_directory not in sys.path:
    sys.path.insert(0, script_directory)

# Set the backend via environment variable (takes effect on first matplotlib import)
BACKEND_MODULE = 'module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq'
os.environ["MPLBACKEND"] = BACKEND_MODULE

import matplotlib

matplotlib.use(BACKEND_MODULE, force=True)
import matplotlib.pyplot as plt

import ast
import math
import traceback
from pathlib import Path
from PyQt5.QtGui import QIcon, QDesktopServices
from PyQt5.QtCore import (
    qInstallMessageHandler, qDebug, qInfo, qWarning, qCritical,
    Qt,
    QSize,
    QThread,
    pyqtSignal,
    QUrl,
    QTimer,
    QEvent,
    QCoreApplication,
    QObject
)
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QSplitter,
    QMessageBox,
    QTabWidget,
    QSizePolicy,
    QSizeGrip,
    QMenu
)

from MasterProject.Client_modules.Desq_GUI.CoreLib.socProxy import makeProxy

from MasterProject.Client_modules.Desq_GUI.scripts.CheckboxDialogs import MultiCheckboxDialog
from MasterProject.Client_modules.Desq_GUI.scripts.CustomMenuBar import CustomMenuBar
from MasterProject.Client_modules.Desq_GUI.scripts.ExperimentThread import ExperimentThread
from MasterProject.Client_modules.Desq_GUI.scripts.DesqTab import QDesqTab
from MasterProject.Client_modules.Desq_GUI.scripts.VoltagePanel import QVoltagePanel
from MasterProject.Client_modules.Desq_GUI.scripts.AccountsPanel import QAccountPanel
from MasterProject.Client_modules.Desq_GUI.scripts.LogPanel import QLogPanel
from MasterProject.Client_modules.Desq_GUI.scripts.ConfigTreePanel import QConfigTreePanel

from MasterProject.Client_modules.Desq_GUI.scripts.PlotSinkManager import PlotSinkManager
from MasterProject.Client_modules.Desq_GUI.scripts.DirectoryTreePanel import DirectoryTreePanel
from MasterProject.Client_modules.Desq_GUI.scripts.AuxiliaryThread import AuxiliaryThread
from MasterProject.Client_modules.Desq_GUI.scripts.ConfigCodeEditor import ConfigCodeEditor
from MasterProject.Client_modules.Desq_GUI.scripts.SettingsWindow import SettingsWindow
from MasterProject.Client_modules.Desq_GUI.scripts import ExperimentLoader
from MasterProject.Client_modules.Desq_GUI.scripts.LoadDataWindow import LoadDataWindow
from MasterProject.Client_modules.Desq_GUI.scripts.ImageViewTab import ImageViewTab
import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers

script_directory = os.path.dirname(os.path.realpath(__file__))
script_parent_directory = os.path.dirname(script_directory)
try:
    os.add_dll_directory(os.path.join(script_parent_directory, 'PythonDrivers'))
except AttributeError:
    os.environ["PATH"] = script_parent_directory + '\\PythonDrivers' + ";" + os.environ["PATH"]

# Use HighDef
QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

TESTING: bool = True
"""
Testing flag - if True, no RFSoC connection required for experiment execution.
Used with mock experiments for GUI development and testing.
"""


class Desq(QMainWindow):
    """
    Main application window for the Desq GUI.

    Desq is a comprehensive quantum computing experiment control system for managing
    superconducting qubit experiments on RFSoC hardware. This class provides the main
    window interface with experiment tabs, configuration panels, voltage control,
    and logging capabilities.

    :ivar experiment_worker: The worker thread instance running the current experiment.
    :vartype experiment_worker: ExperimentThread or None
    :ivar soc: The RFSoC Proxy connection instance via Pyro4.
    :vartype soc: Proxy or None
    :ivar soccfg: The QICK configuration object from the RFSoC.
    :vartype soccfg: QickConfig or None
    :ivar soc_connected: Flag indicating whether the RFSoC is currently connected.
    :vartype soc_connected: bool
    :ivar workspace: The current workspace directory path.
    :vartype workspace: str or None
    :ivar central_widget: The central widget container of the main window.
    :vartype central_widget: QWidget
    :ivar current_tab: Reference to the currently active experiment/data tab.
    :vartype current_tab: QDesqTab or None
    :ivar currently_running_tab: Reference to the tab that has an experiment currently running.
    :vartype currently_running_tab: QDesqTab or None
    :ivar plot_sink_manager: Manager for intercepting and routing matplotlib figures to tabs.
    :vartype plot_sink_manager: PlotSinkManager

    Example usage::

        app = QApplication(sys.argv)
        window = Desq()
        window.show()
        sys.exit(app.exec_())
    """

    rfsoc_connection_updated = pyqtSignal(str, str)
    """Signal emitted after RFSoC connection attempt with (ip_address, status)."""

    def __init__(self) -> None:
        """
        Initialize the Desq main application window.

        Sets up the GUI components, establishes signal connections, and prepares
        the plot sink manager for matplotlib figure interception.
        """
        super().__init__()

        # Stores the thread that runs an experiment
        self.experiment_worker: Optional[ExperimentThread] = None

        # Instance variables for the rfsoc connection
        self.soc = None
        self.soccfg = None
        self.soc_connected: bool = False
        self.workspace: Optional[str] = None

        # Tracks the central tab module by the currently selected tab
        self.current_tab: Optional[QDesqTab] = None
        self.currently_running_tab: Optional[QDesqTab] = None
        self.tabs_added: bool = False

        # Backend-based plot interception
        # This replaces the brittle plt.show() monkey-patching with canvas-level interception
        self.plot_sink_manager: PlotSinkManager = PlotSinkManager(parent=self)
        self.plot_sink_manager.figureReceived.connect(
            self._on_figure_received,
            Qt.QueuedConnection  # Ensure delivery on GUI thread
        )

        # The settings window
        self.settings_window: SettingsWindow = SettingsWindow()

        # The load data window
        self.load_data_window: LoadDataWindow = LoadDataWindow()
        self.load_data_window.load_requested.connect(self._on_load_data_requested)

        self.setup_ui()  # Setup up the PyQt UI

        # Window Event Handling (Resize and Hide)

        # Resize Grip
        self.size_grip: QSizeGrip = QSizeGrip(self)
        self.size_grip.setStyleSheet("background: transparent;")
        self.size_grip.setFixedSize(12, 12)
        self.size_grip.raise_()  # Ensure it's above other widgets

        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """
        Filter application events to handle window activation.

        :param obj: The object that received the event.
        :type obj: QObject
        :param event: The event to be filtered.
        :type event: QEvent
        :returns: True if the event was handled, False otherwise.
        :rtype: bool
        """
        if event.type() == QEvent.ApplicationActivate:
            self.show()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        """
        Handle window resize events to reposition the size grip.

        :param event: The resize event containing new window dimensions.
        :type event: QResizeEvent
        """
        self.size_grip.move(self.width() - self.size_grip.width(), self.height() - self.size_grip.height())
        super().resizeEvent(event)

    def setup_ui(self) -> None:
        """
        Initialize all UI elements of the main window.

        Sets up the main layout structure including:

        - Custom menu bar with experiment controls
        - Central tabs container for experiment and data tabs
        - Directory tree panel for file navigation
        - Global configuration panel
        - Side panel with voltage, accounts, and log tabs
        - Config code editor for universal config loading

        The layout hierarchy is::

            central_widget
            +-- central_layout
                +-- wrapper
                    +-- main_layout
                        +-- custom_menu_bar
                        +-- main_splitter
                            +-- vert_splitter
                            |   +-- config_code_editor
                            |   +-- tab_splitter
                            |       +-- directory_tree_panel
                            |       +-- central_tabs_container
                            +-- global_config_panel
                            +-- side_tabs
        """
        # Central Widget, Layout, and Wrapper
        # To support responsive resizing of content within a widget, the content must be within a layout & widget
        # Thus, the central_layout contains all the elements of the UI within the wrapper widget
        # central widget <-- central layout <-- wrapper <-- all content elements
        self.setWindowTitle("Desq")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)  # removes native title bar but a bit finicky
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.resize(1300, 820)
        # self.setWindowIcon(QIcon('DesqLogo.png'))
        self.central_widget = QWidget()
        self.central_widget.setMinimumSize(1350, 820)
        self.central_widget.setObjectName("central_widget")
        self.central_layout = QVBoxLayout(self.central_widget)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.wrapper = QWidget()
        self.wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.wrapper.setObjectName("wrapper")

        # Main layout (vertical) <-- (top bar) + (main splitter that has all panels)
        self.main_layout = QVBoxLayout(self.wrapper)
        self.main_layout.setContentsMargins(0, 0, 0, 5)
        self.main_layout.setObjectName("main_layout")
        self.main_layout.setSpacing(10)

        # Custom Menu Bar
        self.custom_menu_bar = CustomMenuBar(self)
        self.custom_menu_bar.setObjectName("custom_menu_bar")
        self.main_layout.addWidget(self.custom_menu_bar)

        # Extracting the buttons in the top bar to connect
        # TODO: Fix some of the signals to just be handled in the custom Menu Bar Class
        self.start_experiment_button = self.custom_menu_bar.start_experiment_button
        self.stop_experiment_button = self.custom_menu_bar.stop_experiment_button
        self.soc_status_label = self.custom_menu_bar.soc_status_label
        self.experiment_progress_bar = self.custom_menu_bar.experiment_progress_bar
        self.experiment_progress_bar_label = self.custom_menu_bar.experiment_progress_bar_label
        self.load_data_button = self.custom_menu_bar.load_data_button
        self.load_experiment_button = self.custom_menu_bar.load_experiment_button
        self.documentation_button = self.custom_menu_bar.documentation_button
        self.settings_button = self.custom_menu_bar.settings_button

        # Create a context menu for the stop button
        self.stop_menu = QMenu()
        self.safe_stop_action = self.stop_menu.addAction("Safe Stop")
        self.safe_stop_action.setToolTip("Complete current set, then stop")
        self.stop_menu.addSeparator()
        self.force_stop_action = self.stop_menu.addAction("Force Stop")
        self.force_stop_action.setToolTip("Interrupt immediately")

        # Main Splitter with all main components: Code Editor, Tabs, Voltage Panel, Config Tree
        self.main_splitter = QSplitter(self.wrapper)
        self.main_splitter.setOpaqueResize(False)  # Setting to False allows faster resizing (doesn't look as good)
        self.main_splitter.setHandleWidth(6)
        self.main_splitter.setChildrenCollapsible(True)
        self.main_splitter.setObjectName("main_splitter")
        self.main_splitter.setContentsMargins(10, 0, 10, 0)

        # Vertical Splitter with Tabs and config Editor
        self.vert_splitter = QSplitter(self.main_splitter)
        self.vert_splitter.setOpaqueResize(False)
        self.vert_splitter.setHandleWidth(6)
        self.vert_splitter.setChildrenCollapsible(True)
        self.vert_splitter.setObjectName("vert_splitter")
        self.vert_splitter.setOrientation(Qt.Vertical)

        # Define the Universal Config Loader section
        self.config_code_editor = ConfigCodeEditor(self, self.vert_splitter)

        # Tab Splitter with the directory tree and tabs
        self.tab_splitter = QSplitter(self.vert_splitter)
        self.tab_splitter.setOpaqueResize(False)  # Setting to False allows faster resizing (doesn't look as good)
        self.tab_splitter.setHandleWidth(6)
        self.tab_splitter.setChildrenCollapsible(True)
        self.tab_splitter.setObjectName("tab_splitter")
        self.tab_splitter.setContentsMargins(0, 0, 0, 0)

        # Directory Tree panel
        self.directory_tree_panel = DirectoryTreePanel(
            parent=self.tab_splitter,
            file_filters=['.py', '.h5', *ImageViewTab.SUPPORTED_EXTENSIONS],
            history_key="load_directory"
        )

        # The Central Tabs (contains experiment tabs and data tab)
        self.central_tabs_container = QWidget(self.tab_splitter)
        self.central_tabs_container.setObjectName("central_tabs_container")
        self.central_tabs_layout = QVBoxLayout(self.central_tabs_container)
        self.central_tabs_layout.setContentsMargins(0, 0, 0, 0)

        self.central_tabs = QTabWidget(self.main_splitter)
        tab_bar = self.central_tabs.tabBar()
        tab_bar.setUsesScrollButtons(True)  # enable left/right scroll buttons
        tab_bar.setExpanding(False)
        tab_bar.setElideMode(Qt.ElideNone)
        central_tab_sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Expanding)
        central_tab_sizepolicy.setHorizontalStretch(0)
        central_tab_sizepolicy.setVerticalStretch(0)
        central_tab_sizepolicy.setHeightForWidth(self.central_tabs.sizePolicy().hasHeightForWidth())
        self.central_tabs.setSizePolicy(central_tab_sizepolicy)
        self.central_tabs.setMinimumSize(QSize(650, 0))
        self.central_tabs.setTabPosition(QTabWidget.North)
        self.central_tabs.setUsesScrollButtons(True)
        self.central_tabs.setDocumentMode(False)
        self.central_tabs.setTabsClosable(True)
        self.central_tabs.setMovable(True)
        self.central_tabs.setTabBarAutoHide(False)
        self.central_tabs.setObjectName("central_tabs")

        self.central_tabs_layout.addWidget(self.central_tabs)
        self.central_tabs_container.setLayout(self.central_tabs_layout)

        # Template Experiment Tab
        template_experiment_tab = QDesqTab(app=self)
        self.central_tabs.addTab(template_experiment_tab, "No Tabs Added")
        self.central_tabs.setCurrentIndex(0)
        self.current_tab = template_experiment_tab

        # Config Tree Panel
        self.global_config_panel = QConfigTreePanel(
            self,
            "Global",
            "Global",
            self.main_splitter,
            {}
        )

        # Side Tabs Panel (Contains voltage, accounts, and log panels)
        self.side_tabs = QTabWidget(self.main_splitter)
        self.side_tabs.setObjectName("side_tabs")
        side_tab_sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Expanding)
        side_tab_sizepolicy.setHorizontalStretch(0)
        side_tab_sizepolicy.setVerticalStretch(0)
        side_tab_sizepolicy.setHeightForWidth(self.side_tabs.sizePolicy().hasHeightForWidth())
        self.side_tabs.setSizePolicy(side_tab_sizepolicy)
        self.side_tabs.setMinimumSize(QSize(200, 0))
        self.side_tabs.setTabPosition(QTabWidget.North)
        self.side_tabs.setTabShape(QTabWidget.Rounded)
        self.side_tabs.setDocumentMode(True)
        self.side_tabs.setTabsClosable(False)
        self.side_tabs.setMovable(False)
        side_tab_bar = self.side_tabs.tabBar()
        side_tab_bar.setExpanding(True)
        side_tab_bar.setObjectName("side_tab_bar")
        self.side_tabs.setObjectName("side_tabs")

        # Voltage Controller Panel
        self.voltage_controller_panel = QVoltagePanel(self.global_config_panel, template_experiment_tab,
                                                      parent=self.side_tabs)
        self.side_tabs.addTab(self.voltage_controller_panel, "Voltage")
        # Accounts Panel
        self.accounts_panel = QAccountPanel(parent=self.side_tabs)
        self.workspace = self.accounts_panel.workspace_edit.text().strip()
        template_experiment_tab.experiment_config_panel.directory_tree.set_directory(self.workspace)
        self.global_config_panel.directory_tree.set_directory(self.workspace)
        self.side_tabs.addTab(self.accounts_panel, "Accounts")
        # Log Panel
        self.log_panel = QLogPanel(parent=self.side_tabs)
        self.side_tabs.addTab(self.log_panel, "Log")

        self.side_tabs.setCurrentIndex(1)  # select accounts panel by default

        # Defining default sizes for tab splitter
        self.tab_splitter.setStretchFactor(0, 2)
        self.tab_splitter.setStretchFactor(1, 6)
        self.tab_splitter.setStretchFactor(2, 2)

        # Defining default sizes for vertical splitter
        self.vert_splitter.setStretchFactor(0, 3)
        self.vert_splitter.setStretchFactor(1, 7)
        # self.vert_splitter.setSizes([1, 0])  # collapse the config extractor

        # Defining the default sizes for the splitter
        self.main_splitter.setStretchFactor(0, 8)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 1)

        self.main_layout.addWidget(self.main_splitter)

        # Completing the hierarchy mentioned at the top
        self.wrapper.setLayout(self.main_layout)
        self.central_layout.addWidget(self.wrapper)
        self.setCentralWidget(self.central_widget)

        self.setup_signals()

    def setup_signals(self) -> None:
        """
        Set up all signal-slot connections for the main application window.

        Establishes connections for:

        - Top bar button clicks (start, stop, load, settings)
        - Directory tree file loading
        - Tab change and close events
        - RFSoC connection status updates
        - Log message handling
        - Config tree runtime prediction updates
        - Settings window updates
        - Config editor extraction
        """
        # Connecting the top bar buttons to their respective functions
        self.start_experiment_button.clicked.connect(self.run_experiment)
        self.stop_experiment_button.clicked.connect(self.show_stop_menu)
        self.safe_stop_action.triggered.connect(self.safe_stop_experiment)
        self.force_stop_action.triggered.connect(self.force_stop_experiment)
        self.load_experiment_button.clicked.connect(self.load_experiment_file)
        self.load_data_button.clicked.connect(self.load_data_file)
        self.documentation_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://houcklab.github.io/HouckLab_QICK/index.html")))
        self.settings_button.clicked.connect(self.show_settings)

        # Directory symbols
        self.directory_tree_panel.load_file.connect(self.load_file)

        # Tab Change and Close signals
        self.central_tabs.currentChanged.connect(self.change_tab)
        self.central_tabs.tabCloseRequested.connect(self.close_tab)
        self.side_tabs.currentChanged.connect(self.check_log_read)

        # Signals for RFSoC from the accounts panel
        self.accounts_panel.rfsoc_attempt_connection.connect(self.connect_rfsoc)
        self.accounts_panel.rfsoc_disconnect.connect(self.disconnect_rfsoc)
        self.accounts_panel.workspace_changed.connect(self.update_config_workspaces)
        # Signals for the RFSoC to the accounts panel
        self.rfsoc_connection_updated.connect(self.accounts_panel.rfsoc_connection_updated)

        # Log message handler installation
        qInstallMessageHandler(self.log_panel.message_handler)
        # self.test_logging()

        # Config Tree Panel signal
        self.global_config_panel.update_runtime_prediction.connect(self.call_tab_runtime_prediction)

        # Settings Window
        self.settings_window.update_settings.connect(self.apply_settings)
        self.settings_window.apply_settings()  # Apply the saved settings

        # Config editor
        self.config_code_editor.extracted_config.connect(self.extracted_config)

        self.update_progress(0)
        if TESTING:
            qWarning("WARNING: The TESTING global variable is set to True, removing important checks.")

    def disconnect_rfsoc(self) -> None:
        """
        Disconnect from the RFSoC instance.

        Resets all RFSoC-related attributes to None and updates the connection
        status flag. Also resets the base configuration.
        """
        self.soc = None
        self.soccfg = None
        self.soc_connected = False
        qInfo("Disconnected from RFSoC")

    def save_RFSoC(self, soc: Any, soccfg: Any, ip_address: str) -> None:
        """
        Save the RFSoC connection objects after successful connection.

        Updates the UI to reflect the successful connection status.

        :param soc: The RFSoC Proxy instance returned from makeProxy.
        :type soc: Proxy
        :param soccfg: The QICK configuration object returned from makeProxy.
        :type soccfg: QickConfig
        :param ip_address: The IP address of the connected RFSoC instance.
        :type ip_address: str
        """
        self.soc, self.soccfg = soc, soccfg

        # UI updates
        self.soc_connected = True
        self.is_connecting = False
        self.soc_status_label.setText('Soc connected')
        self.soc_status_label.setStyleSheet("color: #4CAF50;")
        self.rfsoc_connection_updated.emit(ip_address, 'success')  # emit success to accounts tab
        self.accounts_panel.connect_button.setEnabled(True)

    def failed_rfsoc_error(self, e: str, ip_address: str, timeout: bool = False) -> None:
        """
        Handle a failed RFSoC connection attempt.

        Displays appropriate error messages and updates the UI to reflect
        the failed connection status.

        :param e: The error message describing the connection failure.
        :type e: str
        :param ip_address: The IP address of the RFSoC that failed to connect.
        :type ip_address: str
        :param timeout: Whether the failure was due to a connection timeout.
            Defaults to False.
        :type timeout: bool
        """
        if timeout:
            qCritical("Timeout: Connecting to RFSoC took too long (>2s) - check your ip_address is correct.")
            QMessageBox.critical(None, "Timeout Error", "Connection to RFSoC took too long. " +
                                 "Connection attempt will continue in the background until termination.")
        else:
            self.soc_connected = False
            self.soc_status_label.setText('Soc Disconnected')
            self.soc_status_label.setStyleSheet("color: lightgray;")
            QMessageBox.critical(None, "Error", "RFSoC connection failed (see log).")
            qCritical("RFSoC connection to " + ip_address + " failed: " + str(e))

            self.is_connecting = False
            self.accounts_panel.connect_button.setText("Connect")
            self.accounts_panel.connect_button.setEnabled(True)

        if TESTING:
            self.rfsoc_connection_updated.emit(ip_address, 'success')  # emit success to accounts tab if TESTING
        else:
            self.rfsoc_connection_updated.emit(ip_address, 'failure')  # emit failure to accounts tab
        self.soc = None
        self.soccfg = None

    def connect_rfsoc(self, ip_address: str, config: str) -> None:
        """
        Initiate connection to an RFSoC instance.

        Spawns an auxiliary thread to perform the connection via makeProxy
        to avoid blocking the GUI. Also extracts the BaseConfig of the
        connected account.

        :param ip_address: The IP address of the RFSoC instance to connect to.
        :type ip_address: str
        :param config: The path to the module containing the BaseConfig.
        :type config: str

        .. note::
            The connection is performed asynchronously using AuxiliaryThread.
            Results are delivered via Qt signals to :meth:`save_RFSoC` on success
            or :meth:`failed_rfsoc_error` on failure.
        """
        qInfo("Attempting to connect to RFSoC")
        if ip_address is not None:

            self.aux_thread = QThread()
            self.aux_worker = AuxiliaryThread(target_func=makeProxy, func_kwargs={"ns_host": ip_address}, timeout=5)
            self.aux_worker.moveToThread(self.aux_thread)

            # Connecting started and finished signals
            self.aux_thread.started.connect(self.aux_worker.run)  # run function
            self.aux_worker.finished.connect(self.aux_thread.quit)  # stop thread
            self.aux_worker.finished.connect(self.aux_worker.deleteLater)  # delete worker
            self.aux_thread.finished.connect(self.aux_thread.deleteLater)  # delete thread

            # Connecting data related slots
            self.aux_worker.error_signal.connect(lambda err: self.failed_rfsoc_error(err, ip_address, timeout=False))
            self.aux_worker.result_signal.connect(lambda result: self.save_RFSoC(result[0], result[1], ip_address))
            self.aux_worker.timeout_signal.connect(lambda err: self.failed_rfsoc_error(err, ip_address, timeout=True))

            self.aux_thread.start()

            self.is_connecting = True
            self.connecting_dot_count = 0
            self.animate_connecting()

        else:
            qCritical("RFSoC IP address is unspecified, param passed is " + str(ip_address))
            QMessageBox.critical(None, "Error", "RFSoC IP Address not given.")

    def animate_connecting(self) -> None:
        """
        Animate the connecting button with a dot animation.

        Provides visual feedback that a connection attempt is in progress
        by cycling through 0-3 dots appended to "Connecting" text.
        Repeats every 500ms until ``is_connecting`` becomes False.
        """
        if self.is_connecting:
            # Update the label with the current number of dots
            self.accounts_panel.connect_button.setEnabled(False)
            self.accounts_panel.connect_button.setText(f"Connecting{'.' * (self.connecting_dot_count)}")
            self.connecting_dot_count = (self.connecting_dot_count + 1) % 4  # Cycle through 0, 1, 2
            QTimer.singleShot(500, self.animate_connecting)  # Repeat every 500 ms

    def load_file(self, path: str) -> None:
        """
        Load a file based on its extension.

        Routes the file to the appropriate handler based on file type:

        - ``.py`` files: Create experiment tab
        - ``.h5`` files: Open LoadDataWindow
        - Image files: Create image viewing tab

        :param path: The full path to the file to be loaded.
        :type path: str

        .. seealso::
            :meth:`create_experiment_tab`, :meth:`create_image_tab`
        """
        qInfo("Attempting to load " + path)

        ext = os.path.splitext(path)[1].lower()
        if ext == '.py':
            self.create_experiment_tab(str(path))
        elif ext == '.h5':
            # Open LoadDataWindow with the h5 path pre-filled
            self.load_data_window.set_h5_path(str(path))
            self.load_data_window.show()
            self.load_data_window.raise_()
        elif ext in ImageViewTab.SUPPORTED_EXTENSIONS:  # NEW
            self.create_image_tab(str(path))
        else:
            pass

    def run_experiment(self) -> None:
        """
        Execute the experiment from the currently active tab.

        Creates a new ExperimentThread worker and starts the experiment
        execution. Merges global and experiment-specific configurations
        and sets up all necessary signal connections for progress updates
        and error handling.

        The merged configuration format is a flat dictionary::

            config = {
                "config_field1": value1,
                "config_field2": value2,
                ...
            }

        .. note::
            Requires either an active RFSoC connection or TESTING mode enabled.
            Creates a new plot session for figure isolation before starting.

        :raises: Displays QMessageBox on errors including:

            - No RFSoC connection (when not in TESTING mode)
            - Attempting to run a data tab instead of experiment tab
            - Any exception during experiment initialization
        """
        try:
            if TESTING or self.soc_connected:  # ensure RFSoC connection
                if self.current_tab.experiment_obj is None:  # ensure tab is not a data tab
                    qCritical("Attempted execution of a data tab (" + self.current_tab.tab_name +
                              ")rather than an experiment tab")
                    QMessageBox.critical(None, "Error", "Tab is a Data tab.")
                    return

                self.thread = QThread()

                # Handling config specific to the current tab
                # An experiment (both old and T2, want base and experiment config combined and flatted.
                current_experiment_config = self.current_tab.experiment_config_panel.config.copy()
                current_global_config = self.global_config_panel.config.copy()

                experiment_format_config = {}
                experiment_format_config.update(current_global_config)
                experiment_format_config.update(current_experiment_config)  # will override duplicates

                qInfo("Starting experiment: " + self.current_tab.tab_name + "...")
                self.current_tab.last_run_experiment_config = {
                    "Base Config": current_global_config,
                    "Experiment Config": current_experiment_config,
                }
                print(f"Experiment Format Config: {experiment_format_config}")
                qInfo("Gathered Config: " + str(self.current_tab.last_run_experiment_config))

                if "sets" not in experiment_format_config:
                    experiment_format_config["sets"] = 1

                # Create experiment object using updated config and current tab's experiment instance
                experiment_class = self.current_tab.experiment_obj.experiment_class
                # print(inspect.getsourcelines(experiment_class))

                experiment_type = self.current_tab.experiment_obj.experiment_type

                # TODO: This is a problem specific to triangle lattice
                # Inject outerFolder variable manually for triangle lattice (this should be changed later to be more general)
                # This solves the weird pycharm workspace issue
                obj = object.__new__(experiment_class)  # runs without init
                if self.soc_connected:  # inject before init
                    setattr(
                        obj,
                        "outerFolder",
                        self.workspace  # "Z:\\QSimMeasurements\\Measurements\\8QV1_Triangle_Lattice\\"
                    )
                experiment_class.__init__(obj, soc=self.soc, soccfg=self.soccfg, cfg=experiment_format_config)
                self.experiment_instance = obj

                # Start a new plot session BEFORE creating the worker
                # This clears old plots, closes figures, and gets a new session_id for isolation
                plot_session_id = self.current_tab.start_plot_session()
                qInfo(f"Started plot session {plot_session_id} for {self.current_tab.tab_name}")

                # Creating the experiment worker from ExperimentThread and Connecting Signals
                self.experiment_worker = ExperimentThread(
                    experiment_format_config,
                    soccfg=self.soccfg,
                    exp=self.experiment_instance,
                    soc=self.soc,
                    plot_sink_manager=self.plot_sink_manager,
                    target_tab=self.current_tab,
                    session_id=plot_session_id  # Session ID for isolation
                )
                self.experiment_worker.moveToThread(self.thread)  # Move the ExperimentThread onto the actual QThread

                # Connecting started and finished signals
                self.thread.started.connect(self.current_tab.prepare_file_naming)
                # NOTE: clear_plots is now called by start_plot_session() above
                self.thread.started.connect(self.experiment_worker.run)  # run experiment
                self.experiment_worker.finished.connect(self.thread.quit)  # stop thread
                self.experiment_worker.finished.connect(self.experiment_worker.deleteLater)  # delete worker
                self.thread.finished.connect(self.thread.deleteLater)  # delete thread
                self.thread.finished.connect(self.finished_experiment)  # update UI

                # UI updates for tab
                self.currently_running_tab = self.current_tab
                idx = self.central_tabs.indexOf(self.currently_running_tab)
                self.central_tabs.setTabText(idx, '* ' + self.currently_running_tab.tab_name + ".py")

                # Connecting data related slots
                self.experiment_worker.updateData.connect(self.currently_running_tab.update_data)  # update data & plot
                self.experiment_worker.updateRuntime.connect(
                    self.currently_running_tab.update_runtime_estimation)  # update runtime

                self.experiment_worker.updateProgress.connect(self.update_progress)  # update progress bar
                self.experiment_worker.RFSOC_error.connect(self.RFSOC_error)  # connect any RFSoC errors

                # button and GUI updates
                self.update_progress(0)
                self.experiment_progress_bar.setValue(5)

                self.start_experiment_button.setEnabled(False)
                self.stop_experiment_button.setEnabled(True)
                self.start_experiment_button.setStyleSheet(
                    "image: url('MasterProject/Client_modules/Desq_GUI/assets/radio-tower.svg');")
                self.stop_experiment_button.setStyleSheet(
                    "image: url('MasterProject/Client_modules/Desq_GUI/assets/octagon-x-white.svg');")

                self.central_tabs.setTabsClosable(False)  # Disable closing tabs
                # self.central_tabs.tabBar().setEnabled(False)  # Disable tab bar interaction (safer but not needed)
                # self.load_experiment_button.setEnabled(False)
                # self.load_data_button.setEnabled(False)

                self.thread.start()
            else:
                qCritical("The RfSoC instance is not yet connected. Current soc has the value: " + str(self.soc))
                QMessageBox.critical(None, "Error", "RfSoC Disconnected.")
                return

        except Exception as e:
            qCritical("Error while starting experiment: " + str(e))
            format_exc = traceback.format_exc()
            qCritical(format_exc)
            print(format_exc)

    def show_stop_menu(self) -> None:
        """
        Display the stop options context menu below the stop button.

        Shows a menu with "Safe Stop" and "Force Stop" options for
        stopping the currently running experiment.
        """
        pos = self.stop_experiment_button.mapToGlobal(
            self.stop_experiment_button.rect().bottomLeft()
        )
        self.stop_menu.exec_(pos)

    def safe_stop_experiment(self) -> None:
        """
        Initiate a safe stop of the running experiment.

        Signals the experiment to complete the current set before stopping.
        This allows for graceful termination with data integrity preserved.
        """
        if self.experiment_worker:
            self.experiment_worker.stop()
            qInfo("Safe stop initiated - completing current set...")
        self._update_stop_ui()

    def force_stop_experiment(self) -> None:
        """
        Initiate an immediate forced stop of the running experiment.

        Interrupts the experiment immediately without waiting for the
        current set to complete. Falls back to safe stop if force stop fails.
        """
        if self.experiment_worker:
            success = self.experiment_worker.force_stop()
            if success:
                qInfo("Force stop initiated - interrupting...")
            else:
                qWarning("Force stop failed - using safe stop")
        self._update_stop_ui()

    def _update_stop_ui(self) -> None:
        """
        Update UI elements after a stop action is initiated.

        Disables both start and stop buttons and updates their icons
        to indicate the stopping state.
        """
        self.stop_experiment_button.setEnabled(False)
        self.start_experiment_button.setEnabled(False)
        self.start_experiment_button.setStyleSheet(
            "image: url('MasterProject/Client_modules/Desq_GUI/assets/play.svg');")
        self.stop_experiment_button.setStyleSheet(
            "image: url('MasterProject/Client_modules/Desq_GUI/assets/timer-off.svg');")

    def finished_experiment(self) -> None:
        """
        Handle experiment completion and update UI accordingly.

        Called when an experiment thread finishes (either normally or stopped).
        Isolates matplotlib figures to prevent interference from future
        experiments and restores UI controls to their idle state.
        """
        self.is_stopping = False

        # IMPORTANT: Isolate matplotlib figures on the finished tab
        # This creates copies of the figures that won't be affected by future experiments
        # that might reuse the same figure numbers
        if self.currently_running_tab is not None:
            try:
                if hasattr(self.currently_running_tab, 'isolate_matplotlib_figures'):
                    self.currently_running_tab.isolate_matplotlib_figures()
            except Exception as e:
                qWarning(f"Failed to isolate matplotlib figures: {e}")

        if self.current_tab.experiment_obj is None:  # check if tab is a data or experiment tab
            self.start_experiment_button.setEnabled(False)
            self.stop_experiment_button.setEnabled(False)
            self.start_experiment_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/play.svg');")
            self.stop_experiment_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/octagon-x.svg');")
        else:
            self.start_experiment_button.setEnabled(True)
            self.stop_experiment_button.setEnabled(False)
            self.start_experiment_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/play-white.svg');")
            self.stop_experiment_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/octagon-x.svg');")

        self.central_tabs.setTabsClosable(True)  # Enable closing tabs
        # self.central_tabs.tabBar().setEnabled(True)  # Enable tab bar interaction
        # self.load_experiment_button.setEnabled(True)
        # self.load_data_button.setEnabled(True)

        # UI updates for tab
        idx = self.central_tabs.indexOf(self.currently_running_tab)
        self.central_tabs.setTabText(idx, self.currently_running_tab.tab_name + ".py")

        self.voltage_controller_panel.update_voltage_channels()  # update voltages
        if hasattr(self.currently_running_tab, 'tab_name'):  # dumb way to make sure not accessing empty tab_name
            qInfo("Stopping Experiment: " + str(self.currently_running_tab.tab_name))

        self.currently_running_tab = None

    def closeEvent(self, event) -> None:
        """
        Handle application close event with proper cleanup.

        Ensures all threads are stopped and resources are released before
        the application closes. Safe against double-shutdown and
        already-deleted QObjects.

        :param event: The close event to be handled.
        :type event: QCloseEvent
        """
        # Ask the experiment to stop (async)
        try:
            self.safe_stop_experiment()
        except Exception:
            pass

        # Stop aux worker
        if getattr(self, "aux_worker", None) is not None:
            try:
                self.aux_worker.stop()
            except Exception:
                pass

        # IMPORTANT: your worker attribute in this file is `experiment_worker`, not `worker`
        # Don't explicitly delete worker/thread here because you already connected finished->deleteLater.
        # Just try to shut down if still alive.
        th = getattr(self, "thread", None)
        if th is not None:
            try:
                # If it's already deleted, either of these can throw RuntimeError
                if th.isRunning():
                    th.quit()
                    th.wait(5000)
            except RuntimeError:
                # Underlying C++ object already deleted
                pass
            except Exception:
                pass
            finally:
                self.thread = None

        wk = getattr(self, "experiment_worker", None)
        if wk is not None:
            try:
                self.experiment_worker.deleteLater()
            except RuntimeError:
                pass
            finally:
                self.experiment_worker = None

        try:
            if getattr(self, "settings_window", None) is not None:
                self.settings_window.close()
        except Exception:
            pass

        try:
            if getattr(self, "load_data_window", None) is not None:
                self.load_data_window.close()
        except Exception:
            pass

        event.accept()
        QApplication.processEvents()
        QApplication.quit()

    def load_experiment_file(self) -> None:
        """
        Open a file dialog to select and load a Python experiment file.

        Prompts the user to select a ``.py`` file and creates experiment
        tab(s) for the selected file.

        .. seealso::
            :meth:`create_experiment_tab`
        """
        file = Helpers.open_file_dialog("Open Python Experiment File", "Python Files (*.py)",
                                        "load_experiment", self, file=True)

        if not file:
            return
        else:
            path = Path(file)

            # No longer needed as extract experiment now runs on a timeout thread
            # imports = self.extract_direct_imports(str(path))
            # if "socProxy" in imports:
            #     qCritical("Do not import socProxy in your experiment files, connect to an RFSoc via the GUI (comment out that import line).")
            #     QMessageBox.critical(None, "Error", "No socProxy import allowed (see log).")
            #     return

            qInfo("Loading experiment file: " + str(path))
            self.create_experiment_tab(str(path))  # pass full path of the experiment file

    def create_experiment_tab(self, path: str) -> None:
        """
        Create experiment tab(s) from a Python experiment file.

        Searches for all ExperimentClass subclasses in the file and prompts
        the user to select which classes to load. Creates a separate tab
        for each selected experiment class.

        :param path: The full path to the Python experiment file.
        :type path: str

        .. note::
            Uses ExperimentLoader to dynamically find ExperimentClass subclasses.
            Displays a MultiCheckboxDialog for class selection when multiple
            classes are found.
        """
        tab_count = self.central_tabs.count()
        file_name = os.path.splitext(os.path.basename(path))[0]  # just for tooltip/logging

        # Use ExperimentLoader to find classes
        _, experiment_classes = ExperimentLoader.load_and_find(path)

        if not experiment_classes:
            qCritical("No valid ExperimentClass subclasses found.")
            QMessageBox.critical(None, "Error", "No valid ExperimentClass subclasses found in this file.")
            return

        # Extract class names
        class_names = [cls_name for cls_name, _ in experiment_classes]
        # Prompt user to select classes using multi-checkbox dialog
        dialog = MultiCheckboxDialog(class_names, "Select Experiments")
        if dialog.exec_():
            selected = dialog.get_selected()
        else:
            selected = []

        if not selected:
            return  # user cancelled or selected nothing

        # Create a tab for each selected class
        for class_name in selected:
            experiment_name = class_name

            # Pass absolute file path + class name to QDesqTab
            new_experiment_tab = QDesqTab(
                (path, class_name),
                experiment_name,
                file_name,
                True,
                app=self,
                workspace=self.workspace,
            )

            if new_experiment_tab.experiment_obj.experiment_module is None:
                qCritical(f"Failed to load experiment: {class_name}")
                continue

            tab_idx = self.central_tabs.addTab(
                new_experiment_tab,
                f"{class_name}"
            )
            self.central_tabs.setCurrentIndex(tab_idx)

            if self.currently_running_tab is None:
                self.stop_experiment_button.setEnabled(False)
                self.start_experiment_button.setEnabled(True)
                self.start_experiment_button.setStyleSheet(
                    "image: url('MasterProject/Client_modules/Desq_GUI/assets/play-white.svg');"
                )
                self.stop_experiment_button.setStyleSheet(
                    "image: url('MasterProject/Client_modules/Desq_GUI/assets/octagon-x.svg');"
                )

            self.current_tab = new_experiment_tab
            self.central_tabs.setTabToolTip(tab_idx, f"{class_name} ({file_name}.py)")
            self.current_tab.updated_tab.connect(self.update_tab)

            if not self.tabs_added and tab_count == 1:
                self.central_tabs.removeTab(0)
            self.tabs_added = True

    def update_tab(self) -> None:
        """
        Update tab UI elements after tab content changes.

        Currently updates the voltage panel to reflect the current tab's
        configuration.
        """
        self.voltage_controller_panel.changed_tabs(self.current_tab)  # Important: update voltage panel

    def change_tab(self, idx: int) -> None:
        """
        Handle tab change events in the central tabs widget.

        Updates the current tab reference and adjusts UI elements
        (buttons, voltage panel) based on the newly selected tab type.

        :param idx: The index of the newly selected tab.
        :type idx: int
        """
        # update old tab
        if self.current_tab is not None:
            # before current_tab is changed
            pass

        # now handle new tab
        if self.central_tabs.count() != 0:
            self.current_tab = self.central_tabs.widget(idx)
            self.voltage_controller_panel.changed_tabs(self.current_tab)  # Important: update voltage panel

            if self.currently_running_tab is None:
                if self.current_tab.experiment_obj is None:  # check if tab is a data or experiment tab
                    self.start_experiment_button.setEnabled(False)
                    self.stop_experiment_button.setEnabled(False)
                    self.start_experiment_button.setStyleSheet(
                        "image: url('MasterProject/Client_modules/Desq_GUI/assets/play.svg');")
                    self.stop_experiment_button.setStyleSheet(
                        "image: url('MasterProject/Client_modules/Desq_GUI/assets/octagon-x.svg');")
                else:
                    self.start_experiment_button.setEnabled(True)
                    self.stop_experiment_button.setEnabled(False)
                    self.start_experiment_button.setStyleSheet(
                        "image: url('MasterProject/Client_modules/Desq_GUI/assets/play-white.svg');")
                    self.stop_experiment_button.setStyleSheet(
                        "image: url('MasterProject/Client_modules/Desq_GUI/assets/octagon-x.svg');")

    def close_tab(self, idx: int) -> None:
        """
        Handle tab close requests from the central tabs widget.

        Removes the specified tab and cleans up resources. Updates
        UI if no tabs remain.

        :param idx: The index of the tab to be closed.
        :type idx: int
        """
        tab_to_delete = self.central_tabs.widget(idx)
        tab_name = tab_to_delete.tab_name

        self.central_tabs.removeTab(idx)  # remove tab from widget

        if self.central_tabs.count() == 0:  # if no tabs remaining
            self.start_experiment_button.setEnabled(False)
            self.stop_experiment_button.setEnabled(False)
            self.start_experiment_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/play.svg');")
            self.stop_experiment_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/octagon-x.svg');")
            self.current_tab = None
        else:
            current_tab_idx = self.central_tabs.currentIndex()  # get the tab changed to upon closure
            self.change_tab(current_tab_idx)

        tab_to_delete.deleteLater()  # safely delete the tab

    def update_config_workspaces(self, workspace: str) -> None:
        """
        Update workspace path across all configuration panels.

        :param workspace: The new workspace directory path.
        :type workspace: str
        """
        self.workspace = workspace
        self.global_config_panel.directory_tree.change_workspace(workspace)

    def update_progress(self, sets_complete: int) -> None:
        """
        Update the experiment progress bar based on completion status.

        Retrieves the reps and sets fields from the current tab's configuration
        to calculate progress percentage.

        :param sets_complete: The number of experiment sets that have been completed.
        :type sets_complete: int

        .. note::
            Usually called via a signal from ExperimentThread during experiment
            execution.
        """
        if self.currently_running_tab is None:
            self.experiment_progress_bar.setValue(0)
            self.experiment_progress_bar_label.setText("--/--")
            return

        unformatted_config = {
            **self.currently_running_tab.last_run_experiment_config["Experiment Config"],
            **self.currently_running_tab.last_run_experiment_config["Base Config"]
        }
        # Getting the total reps and sets to be run from the experiment configs
        reps, sets = 1, 1
        if 'reps' in unformatted_config and 'sets' in unformatted_config:
            reps, sets = unformatted_config['reps'], unformatted_config['sets']
        self.experiment_progress_bar.setValue(math.floor(float(sets_complete) / sets * 100))  # calculate completed %
        self.experiment_progress_bar_label.setText(str(sets_complete * reps) + "/" + str(sets * reps))  # set label

    def call_tab_runtime_prediction(self, config: Dict[str, Any]) -> None:
        """
        Forward runtime prediction request to the current tab.

        Called when the config changed signal is emitted. Routes the
        prediction call to whichever tab is currently active.

        :param config: The configuration dictionary to use for runtime estimation.
        :type config: Dict[str, Any]
        """
        if self.current_tab is not None:
            self.current_tab.predict_runtime(config)

    def RFSOC_error(self, e: Exception, traceback_str: str) -> None:
        """
        Handle and display RFSoC errors during experiment execution.

        :param e: The exception that was raised.
        :type e: Exception
        :param traceback_str: The formatted traceback string.
        :type traceback_str: str
        """
        qCritical("RFSoC thew the error: " + str(e))
        qCritical(traceback_str)
        print(traceback_str)
        QMessageBox.critical(None, "RFSOC error", "RfSoc has thrown an error (see log).")

    def load_data_file(self) -> None:
        """
        Show the LoadDataWindow for selecting data files.

        Opens a dialog for the user to select an H5 data file and
        optionally an experiment class for visualization.
        """
        self.load_data_window.show()
        self.load_data_window.raise_()

    def create_data_tab(self, file: str) -> None:
        """
        Create a new data viewing tab for an H5 file.

        :param file: The path to the H5 data file.
        :type file: str

        .. seealso::
            :class:`QDesqTab`
        """
        tab_count = self.central_tabs.count()
        file_name = os.path.basename(file)
        # Creates the new QQuarkTab instance specifying not an experiment tab
        new_data_tab = QDesqTab((None, None), file_name, file_name, False, file, app=self)

        # Handle UI updates
        tab_idx = self.central_tabs.addTab(new_data_tab, (file_name))
        self.central_tabs.setCurrentIndex(tab_idx)
        self.start_experiment_button.setEnabled(False)
        self.current_tab = new_data_tab

        if not self.tabs_added:
            if tab_count == 1:
                self.central_tabs.removeTab(0)
        self.tabs_added = True

    def create_image_tab(self, file_path: str) -> None:
        """
        Create a new image viewing tab for displaying image files.

        :param file_path: The full path to the image file.
        :type file_path: str

        :raises Exception: Displays a QMessageBox if the image fails to load.
        """
        tab_count = self.central_tabs.count()
        file_name = os.path.basename(file_path)

        try:
            new_image_tab = ImageViewTab(file_path, parent=self)

            tab_idx = self.central_tabs.addTab(new_image_tab, file_name)
            self.central_tabs.setCurrentIndex(tab_idx)
            self.central_tabs.setTabToolTip(tab_idx, file_path)

            # Image tabs can't run experiments
            self.start_experiment_button.setEnabled(False)
            self.stop_experiment_button.setEnabled(False)
            self.start_experiment_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/play.svg');")
            self.stop_experiment_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/octagon-x.svg');")

            self.current_tab = new_image_tab

            if not self.tabs_added:
                if tab_count == 1:
                    self.central_tabs.removeTab(0)
            self.tabs_added = True

            qInfo(f"Created image tab for: {file_name}")

        except Exception as e:
            qCritical(f"Failed to create image tab: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to open image:\n{str(e)}")

    def _on_load_data_requested(self, h5_path: str, experiment_path: str, class_name: str) -> None:
        """
        Handle load request signal from LoadDataWindow.

        Creates a data tab and uses the specified experiment's display()
        method for visualization.

        :param h5_path: Path to the H5 data file.
        :type h5_path: str
        :param experiment_path: Path to the experiment Python file.
        :type experiment_path: str
        :param class_name: Name of the experiment class to use for display.
        :type class_name: str
        """
        try:
            qInfo(f"Loading data with experiment display: {h5_path} -> {class_name}")

            # Load the experiment module
            module_name, experiment_classes = ExperimentLoader.load_and_find(experiment_path)
            if not experiment_classes:
                QMessageBox.critical(self, "Error", "No experiment classes found in file.")
                return

            # Find the specified class
            experiment_class = None
            for name, cls in experiment_classes:
                if name == class_name:
                    experiment_class = cls
                    break

            if experiment_class is None:
                QMessageBox.critical(self, "Error", f"Experiment class '{class_name}' not found.")
                return

            # Load the data from H5 file
            data = Helpers.h5_to_dict(h5_path)
            qInfo(f"Loaded data keys: {list(data.keys())}")

            # Create the data tab
            tab_count = self.central_tabs.count()
            h5_filename = os.path.basename(h5_path)
            # tab_name = f"{h5_filename} ({class_name})"
            tab_name = f"{h5_filename}"

            new_data_tab = QDesqTab(
                experiment_id=(None, None),
                tab_name=tab_name,
                source_file_name=h5_filename,
                is_experiment=False,
                dataset_file=None,  # Don't auto-load, we'll handle it manually
                app=self
            )

            # Store the data in the tab
            new_data_tab.data = data

            # Extract config if present
            if "config" in data:
                qInfo("Config in h5 metadata found")
                temp_config = data["config"]
                new_data_tab.experiment_config_panel.update_config_dict(temp_config, reset=True)
                new_data_tab.data.pop("config", None)

            # Add the tab to the UI
            tab_idx = self.central_tabs.addTab(new_data_tab, tab_name)
            self.central_tabs.setCurrentIndex(tab_idx)
            self.start_experiment_button.setEnabled(False)
            self.current_tab = new_data_tab

            if not self.tabs_added:
                if tab_count == 1:
                    self.central_tabs.removeTab(0)
            self.tabs_added = True

            # Now call the experiment's display() method
            self._call_experiment_display(new_data_tab, experiment_class, data)

        except Exception as e:
            qCritical(f"Error loading data with experiment display: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to load data:\n{str(e)}")

    def _call_experiment_display(self, tab: 'QDesqTab', experiment_class: type, data: Dict[str, Any]) -> None:
        """
        Call an experiment's display() method to visualize data.

        Creates a minimal experiment instance and invokes its display()
        method to generate visualization figures. Routes generated figures
        to the tab's carousel.

        :param tab: The data tab to display the visualization in.
        :type tab: QDesqTab
        :param experiment_class: The experiment class containing the display() method.
        :type experiment_class: type
        :param data: The data dictionary to visualize.
        :type data: Dict[str, Any]

        .. note::
            Falls back to auto-plotting if the experiment class has no display()
            method or if display() raises an error.
        """

        try:
            # Start a plot session for figure isolation
            session_id = tab.start_plot_session()
            qInfo(f"Started plot session {session_id} for data display")

            # Create a minimal experiment instance for display
            # We create the object without calling __init__ to avoid hardware requirements
            exp_instance = object.__new__(experiment_class)

            # Set minimal attributes that display() might need
            exp_instance.cfg = data.get("config", {})
            if hasattr(experiment_class, 'outerFolder'):
                exp_instance.outerFolder = self.workspace

            # Check if the class has a display method
            if not hasattr(experiment_class, 'display'):
                qWarning(f"Experiment class {experiment_class.__name__} has no display() method")
                # Fall back to auto-plotting
                tab.plot_data(exp_instance=None, data_to_plot=data)
                return

            # Record existing figure numbers BEFORE calling display()
            existing_fig_nums = set(plt.get_fignums())

            # Call display() - this may create new matplotlib figures
            try:
                experiment_class.display(exp_instance, data, plotDisp=True)
            except TypeError:
                # Some display methods might not take plotDisp argument
                experiment_class.display(exp_instance, data)
            except Exception as e:
                qCritical(f"Error loading data with experiment display: {e}")
                return

            # Find NEW figures created during display()
            new_fig_nums = set(plt.get_fignums()) - existing_fig_nums

            if new_fig_nums:
                qInfo(f"display() created {len(new_fig_nums)} new figure(s)")

                # Route each new figure to the tab with session_id=-1 (trusted)
                for fig_num in sorted(new_fig_nums):
                    fig = plt.figure(fig_num)
                    tab.receive_figure(fig, 'draw', session_id=-1)

                qInfo(f"Routed {len(new_fig_nums)} figures to carousel")
            else:
                # display() didn't create new figures - fall back to auto_plot
                qWarning("display() created no new figures, falling back to auto_plot")
                tab.plot_data(exp_instance=None, data_to_plot=data)

        except Exception as e:
            qCritical(f"Error calling experiment display: {e}")
            traceback.print_exc()

            # Fall back to auto-plotting
            qInfo("Falling back to auto_plot due to display() error")
            tab.plot_data(exp_instance=None, data_to_plot=data)

    def check_log_read(self) -> None:
        """
        Check if the Log tab is selected and mark it as read.

        Resets the tab text to remove any unread notification indicator
        when the user switches to the Log tab.
        """
        log_index = self.side_tabs.indexOf(self.log_panel)

        if log_index == self.side_tabs.currentIndex():
            self.side_tabs.setTabText(log_index, "Log")
            self.log_panel.logger.setFocus()

    def show_settings(self) -> None:
        """
        Display the settings window.

        Shows the SettingsWindow dialog and brings it to the foreground.
        """
        self.settings_window.show()
        self.settings_window.raise_()

    def apply_settings(self, theme: Optional[str] = None, font_size: Optional[int] = None) -> None:
        """
        Apply theme and font settings to the application.

        Loads the appropriate QSS stylesheet and applies color/font
        substitutions based on the selected theme.

        :param theme: The theme to apply ('Dark Mode' or 'Light Mode').
            Uses current settings value if None.
        :type theme: str or None
        :param font_size: The base font size to apply.
            Uses current settings value if None.
        :type font_size: int or None
        """
        if theme is None:
            theme = self.settings_window.curr_theme
        if font_size is None:
            font_size = int(self.settings_window.curr_font_size)

        self.theme = theme
        self.font_size = font_size

        # print("applying settings")
        if theme == "Dark Mode":
            with open("MasterProject/Client_modules/Desq_GUI/assets/style.qss", "r") as file:
                style = file.read()

            # Backgrounds
            style = style.replace('$MAIN_BACKGROUND_COLOR', f"#090716")
            style = style.replace('$MAIN_ACCENT_BACKGROUND_COLOR', f"#2B2B2F")
            style = style.replace('$GENERAL_FONT_COLOR', f"#FFFFFF")
            style = style.replace('$GENERAL_BORDER_COLOR', f"#3D3D3D")
            style = style.replace('$GENERAL_BORDER_DARKER_COLOR', f"#4F4F4F")
            style = style.replace('$MENU_BAR_BACKGROUND_COLOR', f"#2B2B2F")
            style = style.replace('$CONFIG_TREE_BASE_BACKGROUND_COLOR', f"#222226")
            style = style.replace('$CONFIG_TREE_ALT_BACKGROUND_COLOR', f"#313135")
            style = style.replace('$CONFIG_TREE_HEADER_BACKGROUND_COLOR', f"#12121C")
            # Button
            style = style.replace('$BUTTON_BACKGROUND_COLOR', f"#404044")
            style = style.replace('$BUTTON_TEXT_COLOR', f"#FFFFFF")
            style = style.replace('$BUTTON_HOVER_BORDER_COLOR', f"#57575A")
            style = style.replace('$BUTTON_PRESSED_BACKGROUND_COLOR', f"#090716")
            style = style.replace('$BUTTON_PRESSED_TEXT_COLOR', f"#FFFFFF")
            style = style.replace('$BUTTON_DISABLED_BACKGROUND_COLOR', f"#1A1A1E")
            style = style.replace('$BUTTON_DISABLED_TEXT_COLOR', f"#424242")
            style = style.replace('$BUTTON_CONNECT_COLOR', f"#6495ED")
            style = style.replace('$BUTTON_CONNECT_TEXT_COLOR', f"#FFFFFF")
            style = style.replace('$BUTTON_CONNECT_DISABLED_COLOR', f"#AABEDC")
            style = style.replace('$BUTTON_CONNECT_DISABLED_TEXT_COLOR', f"#DDDDDD")
            style = style.replace('$BUTTON_RUN_COLOR', f"#3CB371")
            style = style.replace('$BUTTON_RUN_HOVER_COLOR', f"#64DB99")
            style = style.replace('$BUTTON_STOP_COLOR', f"#CD5C5C")
            style = style.replace('$BUTTON_STOP_HOVER_COLOR', f"#F58484")
            style = style.replace('$BUTTON_EDITOR_HOVER_COLOR', f"#4A4A4A")
            style = style.replace('$BUTTON_MENU_BACKGROUND_COLOR', f"#404044")
            style = style.replace('$BUTTON_MENU_BACKGROUND_HOVER_COLOR', f"#57575A")
            # Tabs
            style = style.replace('$TAB_BACKGROUND_COLOR', f"#2D2D31")
            style = style.replace('$TAB_BAR_BACKGROUND_COLOR', f"#111116")
            style = style.replace('$TAB_TEXT_COLOR', f"#FFFFFF")
            style = style.replace('$TAB_BORDER_COLOR', f"#454545")
            style = style.replace('$TAB_SELECTED_ACCENT_COLOR', f"#8AC6F2")
            # Misc
            style = style.replace('$CODE_FILE_LABEL_TEXT_COLOR', f"#979797")
            style = style.replace('$FIND_BAR_COLOR', f"#12121C")
            style = style.replace('$PROGRESS_BAR_BACKGROUND_COLOR', f"#090716")
        else:
            with open("MasterProject/Client_modules/Desq_GUI/assets/style.qss", "r") as file:
                style = file.read()

            # Backgrounds
            style = style.replace('$MAIN_BACKGROUND_COLOR', f"#FFFFFF")
            style = style.replace('$MAIN_ACCENT_BACKGROUND_COLOR', f"#F0F1F2")
            style = style.replace('$GENERAL_FONT_COLOR', f"#000000")
            style = style.replace('$GENERAL_BORDER_COLOR', f"#EAEBE9")
            style = style.replace('$GENERAL_BORDER_DARKER_COLOR', f"#C4C4C3")
            style = style.replace('$MENU_BAR_BACKGROUND_COLOR', f"#2B2B2F")
            style = style.replace('$CONFIG_TREE_BASE_BACKGROUND_COLOR', f"#F0F1F2")
            style = style.replace('$CONFIG_TREE_ALT_BACKGROUND_COLOR', f"#FFFFFF")
            style = style.replace('$CONFIG_TREE_HEADER_BACKGROUND_COLOR', f"#E0E1E2")
            # Button
            style = style.replace('$BUTTON_BACKGROUND_COLOR', f"#FFFFFF")
            style = style.replace('$BUTTON_TEXT_COLOR', f"#000000")
            style = style.replace('$BUTTON_HOVER_BORDER_COLOR', f"#B6B6B6")
            style = style.replace('$BUTTON_PRESSED_BACKGROUND_COLOR', f"#F0F0F0")
            style = style.replace('$BUTTON_PRESSED_TEXT_COLOR', f"#FFFFFF")
            style = style.replace('$BUTTON_DISABLED_BACKGROUND_COLOR', f"#ECEEF1")
            style = style.replace('$BUTTON_DISABLED_TEXT_COLOR', f"#B6B6B6")
            style = style.replace('$BUTTON_CONNECT_COLOR', f"#6495ED")
            style = style.replace('$BUTTON_CONNECT_TEXT_COLOR', f"#FFFFFF")
            style = style.replace('$BUTTON_CONNECT_DISABLED_COLOR', f"#AABEDC")
            style = style.replace('$BUTTON_CONNECT_DISABLED_TEXT_COLOR', f"#DDDDDD")
            style = style.replace('$BUTTON_RUN_COLOR', f"#3CB371")
            style = style.replace('$BUTTON_RUN_HOVER_COLOR', f"#64DB99")
            style = style.replace('$BUTTON_STOP_COLOR', f"#CD5C5C")
            style = style.replace('$BUTTON_STOP_HOVER_COLOR', f"#F58484")
            style = style.replace('$BUTTON_EDITOR_HOVER_COLOR', f"#DCDCDC")
            style = style.replace('$BUTTON_MENU_BACKGROUND_COLOR', f"#404044")
            style = style.replace('$BUTTON_MENU_BACKGROUND_HOVER_COLOR', f"#57575A")
            # Tabs
            style = style.replace('$TAB_BACKGROUND_COLOR', f"#F6F6F6")
            style = style.replace('$TAB_BAR_BACKGROUND_COLOR', f"#F7F8FA")
            style = style.replace('$TAB_TEXT_COLOR', f"#000000")
            style = style.replace('$TAB_BORDER_COLOR', f"#C4C4C3")
            style = style.replace('$TAB_SELECTED_ACCENT_COLOR', f"#8AC6F2")
            # Misc
            style = style.replace('$CODE_FILE_LABEL_TEXT_COLOR', f"#878787")
            style = style.replace('$FIND_BAR_COLOR', f"#E0E1E2")
            style = style.replace('$PROGRESS_BAR_BACKGROUND_COLOR', f"#090716")

        # Fonts
        style = style.replace('$GLOBAL_FONT_SIZE', f"{font_size}")
        style = style.replace('$LARGER_FONT_SIZE', f"{(font_size + 2)}")
        style = style.replace('$MEDIUM_FONT_SIZE', f"{(font_size - 1)}")
        style = style.replace('$TAB_FONT_SIZE', f"{(font_size - 2)}")
        style = style.replace('$SMALL_FONT_SIZE', f"{(font_size - 2)}")

        # Slightly fragile implementation here that relies on the main block's global app variable
        app.setStyleSheet(style)

    def extracted_config(self, global_config: Dict[str, Any], exp_config: Dict[str, Any]) -> None:
        """
        Handle extracted configuration from the config code editor.

        Updates both the global and experiment configuration panels with
        the extracted values.

        :param global_config: The extracted global configuration dictionary.
        :type global_config: Dict[str, Any]
        :param exp_config: The extracted experiment-specific configuration dictionary.
        :type exp_config: Dict[str, Any]
        """
        print(f"Global: {global_config}, Exp: {exp_config}")
        qInfo(f"Global: {str(global_config)}, Exp: {str(exp_config)}")

        # Update global panel
        self.global_config_panel.update_config_dict(global_config)
        self.global_config_panel.populate_config_view()

        # Update experiment panel
        self.current_tab.experiment_config_panel.update_config_dict(exp_config)
        self.current_tab.experiment_config_panel.populate_config_view()

    def extract_direct_imports(self, file_path: str) -> List[str]:
        """
        Extract direct module names from import statements in a Python file.

        Parses the AST of the given file and extracts the most direct
        (rightmost) module name from each import statement.

        :param file_path: Full path to the Python file to analyze.
        :type file_path: str
        :returns: List of direct module names from import statements.
        :rtype: List[str]

        Example::

            # For a file containing:
            # import os.path
            # from collections.abc import Mapping

            # Returns: ['path', 'abc']
        """
        with open(file_path, "r") as file:
            tree = ast.parse(file.read(), filename=file_path)

        # List to store the direct module names
        direct_imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Split the full module path and take the last part as the direct module name
                    module_name = alias.name.split('.')[-1]
                    direct_imports.append(module_name)
            elif isinstance(node, ast.ImportFrom):
                # Split the full module path and take the last part as the direct module name
                module_name = node.module.split('.')[-1]
                direct_imports.append(module_name)

        return direct_imports

    def _on_figure_received(
        self,
        figure: Any,
        target_tab: Optional['QDesqTab'],
        event_type: str,
        session_id: int
    ) -> None:
        """
        Handle figures received from the backend-based plot sink.

        Called when any matplotlib figure is drawn in a worker thread.
        The figure is automatically routed to the correct tab via Qt signals.

        :param figure: The matplotlib Figure object to display.
        :type figure: matplotlib.figure.Figure
        :param target_tab: The tab that should display this figure.
        :type target_tab: QDesqTab or None
        :param event_type: The type of draw event, either 'draw' or 'draw_idle'.
        :type event_type: str
        :param session_id: The plot session ID for validation and figure isolation.
        :type session_id: int

        .. note::
            The target tab validates the session_id and rejects figures from
            old sessions to prevent cross-contamination between experiments.
        """
        if target_tab is None:
            qWarning("Figure received but no valid target tab")
            return

        # Check if the tab has the receive_figure method (carousel-aware)
        if not hasattr(target_tab, 'receive_figure'):
            qWarning("Target tab does not have receive_figure method")
            return

        try:
            # Pass figure to tab's carousel-aware receiver with session_id
            # The tab validates session_id and rejects figures from old sessions
            target_tab.receive_figure(figure, event_type, session_id)
        except Exception as e:
            qWarning(f"Error handling received figure: {e}")
            import traceback
            traceback.print_exc()


# Creating the Desq GUI Main Window
if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        ex = Desq()

        ex.show()
        sys.exit(app.exec_())

    except Exception as e:
        QMessageBox.critical(None, "Critical Error", f"A GUI error occurred: {e}")
        traceback.print_exc()