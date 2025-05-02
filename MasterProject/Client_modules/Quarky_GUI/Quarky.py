"""
=========
Quarky.py
=========
Main entry point for the Quarky GUI application.

This module initializes the GUI, handles application-level logic, and manages interactions between
different components.
"""

import inspect
import sys, os
import ast
import math
import traceback
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
from PyQt5.QtGui import QIcon, QPixmap, QDesktopServices
from PyQt5.QtCore import (
    qInstallMessageHandler, qDebug, qInfo, qWarning, qCritical,
    Qt,
    QSize,
    QThread,
    pyqtSignal,
    QUrl,
)
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSplitter,
    QMessageBox,
    QFileDialog,
    QTabWidget,
    QSizePolicy
)

# Use absolute imports maybe
from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentT2 import ExperimentClassT2
from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface
from MasterProject.Client_modules.CoreLib.socProxy import makeProxy
from scripts.ExperimentThread import ExperimentThread
from scripts.QuarkTab import QQuarkTab
from scripts.VoltagePanel import QVoltagePanel
from scripts.AccountsPanel import QAccountPanel
from scripts.LogPanel import QLogPanel
from scripts.ConfigTreePanel import QConfigTreePanel
import scripts.Helpers as Helpers

### Importing the PythonDrivers --- not sure if it works currently since they aren't being used
script_directory = os.path.dirname(os.path.realpath(__file__))
script_parent_directory = os.path.dirname(script_directory)
try:
    os.add_dll_directory(os.path.join(script_parent_directory, 'PythonDrivers'))
except AttributeError:
    os.environ["PATH"] = script_parent_directory + '\\PythonDrivers' + ";" + os.environ["PATH"]

class Quarky(QMainWindow):
    """
    The class for the main Quarky application window.

    **Important Attributes:**

        * experiment_worker (ExperimentThread): The instance of the experiment worker thread.
        * soc (Proxy): The instance of the RFSoC Proxy connection via Pyro4.
        * soccfg (QickConfig): The qick Config of the RFSoC.
        * central_widget (QWidget): The central widget of the Quarky GUI.
    """

    ### Defining Signals
    rfsoc_connection_updated = pyqtSignal(str, str)
    """
    The Signal sent to the accounts tab after an rfsoc connection attempt 
    
    :param ip_address: The IP address of the RFSoC instance.
    :type ip_address: str
    :param status: The status of the attempt, either success or failure.
    :type status: str
    """

    def __init__(self):
        """
        Initializes an instance of a Quarky GUI application.
        """

        super().__init__()

        # Stores the thread that runs an experiment
        self.experiment_worker = None

        # Instance variables for the rfsoc connection
        self.soc = None
        self.soccfg = None
        self.soc_connected = False

        # Tracks the central tab module by the currently selected tab
        self.current_tab = None
        self.tabs_added = False

        self.setup_ui() # Setup up the PyQt UI

    def setup_ui(self):
        """
        Initializes all the UI elements. The main sections include the central widgets tab, config panel, and the side
        panel (voltage, accounts, log).
        """

        ### Central Widget, Layout, and Wrapper
        ### To support responsive resizing of content within a widget, the content must be within a layout & widget
        ### Thus, the central_layout contains all the elements of the UI within the wrapper widget
        ### central widget <-- central layout <-- wrapper <-- all content elements
        self.setWindowTitle("Quarky")
        self.resize(1075, 600)
        self.setWindowIcon(QIcon('QuarkyLogo.png'))
        self.central_widget = QWidget() # Defining the central widget that holds everything
        self.central_widget.setMinimumSize(1000, 600)
        self.central_widget.setObjectName("central_widget")
        self.central_layout = QVBoxLayout(self.central_widget)
        self.wrapper = QWidget()
        self.wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.wrapper.setObjectName("wrapper")

        ### Main layout (vertical) <-- (top bar) + (main splitter that has all panels)
        self.main_layout = QVBoxLayout(self.wrapper)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setObjectName("main_layout")

        ### Top Control Bar (contains loading and experiment run buttons + progress bar)
        self.top_bar = QHBoxLayout()
        self.top_bar.setContentsMargins(-1, 10, -1, 10)
        self.top_bar.setObjectName("top_bar")

        # Creating top bar items
        # self.quarky_icon = QLabel()
        # self.quarky_icon.setPixmap(QPixmap("QuarkyLogo.png").scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.documentation_button = Helpers.create_button("?", "documentation", True, self.wrapper)
        self.documentation_button.setToolTip("Documentation")
        self.documentation_button.setStyleSheet("border: 1px solid gray; font-size: 10px; border-radius:6px; color: gray; width: 12px;")

        self.start_experiment_button = Helpers.create_button("▶","start_experiment",False,self.wrapper)
        self.start_experiment_button.setToolTip("Run")
        self.stop_experiment_button = Helpers.create_button("◼️","stop_experiment",False,self.wrapper)
        self.stop_experiment_button.setToolTip("Stop")
        self.soc_status_label = QLabel('<html><b>✖ Soc Disconnected</b></html>', self.wrapper)
        self.soc_status_label.setObjectName("soc_status_label")
        self.experiment_progress_bar = QProgressBar(self.wrapper, value=0)
        self.experiment_progress_bar.setObjectName("experiment_progress_bar")
        self.load_data_button = Helpers.create_button("Load Data","load_data_button",True,self.wrapper)
        self.load_experiment_button = Helpers.create_button("Extract Experiment","load_experiment_button",True,self.wrapper)

        # Adding items to top bar, top bar to main layout
        # self.top_bar.addWidget(self.quarky_icon)
        self.top_bar.addWidget(self.start_experiment_button)
        self.top_bar.addWidget(self.stop_experiment_button)
        self.top_bar.addWidget(self.soc_status_label)
        self.top_bar.addWidget(self.experiment_progress_bar)
        self.top_bar.addWidget(self.load_data_button)
        self.top_bar.addWidget(self.load_experiment_button)
        self.top_bar.addWidget(self.documentation_button)
        self.main_layout.addLayout(self.top_bar)

        ### Main Splitter with Tabs, Voltage Panel, Config Tree
        self.main_splitter = QSplitter(self.wrapper)
        self.main_splitter.setLineWidth(2)
        self.main_splitter.setOpaqueResize(True) # Setting to False allows faster resizing (doesn't look as good)
        self.main_splitter.setHandleWidth(7)
        self.main_splitter.setChildrenCollapsible(True)
        self.main_splitter.setObjectName("main_splitter")

        ### The Central Tabs (contains experiment tabs and data tab)
        self.central_tabs = QTabWidget(self.main_splitter)
        central_tab_sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Expanding)
        central_tab_sizepolicy.setHorizontalStretch(0)
        central_tab_sizepolicy.setVerticalStretch(0)
        central_tab_sizepolicy.setHeightForWidth(self.central_tabs.sizePolicy().hasHeightForWidth())
        self.central_tabs.setSizePolicy(central_tab_sizepolicy)
        self.central_tabs.setMinimumSize(QSize(620, 0))
        self.central_tabs.setTabPosition(QTabWidget.North)
        self.central_tabs.setTabShape(QTabWidget.Rounded)
        self.central_tabs.setUsesScrollButtons(True)
        self.central_tabs.setDocumentMode(True)
        self.central_tabs.setTabsClosable(True)
        self.central_tabs.setMovable(True)
        self.central_tabs.setTabBarAutoHide(False)
        self.central_tabs.setObjectName("central_tabs")

        #Template Experiment Tab
        template_experiment_tab = QQuarkTab()
        self.central_tabs.addTab(template_experiment_tab, "No Tabs Added")
        self.central_tabs.setCurrentIndex(0)

        ### Config Tree Panel
        self.config_tree_panel = QConfigTreePanel(self.main_splitter, template_experiment_tab.config)

        ### Side Tabs Panel (Contains voltage, accounts, and log panels)
        self.side_tabs = QTabWidget(self.main_splitter)
        side_tab_sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Expanding)
        side_tab_sizepolicy.setHorizontalStretch(0)
        side_tab_sizepolicy.setVerticalStretch(0)
        side_tab_sizepolicy.setHeightForWidth(self.side_tabs.sizePolicy().hasHeightForWidth())
        self.side_tabs.setSizePolicy(side_tab_sizepolicy)
        self.side_tabs.setMinimumSize(QSize(175, 0))
        self.side_tabs.setTabPosition(QTabWidget.North)
        self.side_tabs.setTabShape(QTabWidget.Rounded)
        self.side_tabs.setDocumentMode(True)
        self.side_tabs.setTabsClosable(False)
        self.side_tabs.setMovable(False)
        self.side_tabs.setObjectName("side_tabs")

        ### Voltage Controller Panel
        self.voltage_controller_panel = QVoltagePanel(self.config_tree_panel, template_experiment_tab, parent=self.side_tabs)
        self.side_tabs.addTab(self.voltage_controller_panel, "Voltage")
        ### Accounts Panel
        self.accounts_panel = QAccountPanel(parent=self.side_tabs)
        self.side_tabs.addTab(self.accounts_panel, "RFSoC")
        ### Log Panel
        self.log_panel = QLogPanel(parent=self.side_tabs)
        self.side_tabs.addTab(self.log_panel, "Log")
        self.side_tabs.setCurrentIndex(1) # select accounts panel by default

        # Defining the default sizes for the splitter
        self.main_splitter.setStretchFactor(0, 8)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2,1)
        self.main_layout.addWidget(self.main_splitter)
        self.main_layout.setStretch(0, 1) # make top bar small
        self.main_layout.setStretch(1, 10) # make main body large

        # Completing the hierarchy mentioned at the top
        self.wrapper.setLayout(self.main_layout)
        self.central_layout.addWidget(self.wrapper)
        self.setCentralWidget(self.central_widget)

        self.setup_signals()

    def setup_signals(self):
        """
        Sets up all signals and slots of the main application window. These include button presses, RFSoC connections,
        log messages, and tab changes.
        """

        # Connecting the top bar buttons to their respective functions
        self.start_experiment_button.clicked.connect(self.run_experiment)
        self.stop_experiment_button.clicked.connect(self.stop_experiment)
        self.load_experiment_button.clicked.connect(self.load_experiment_file)
        self.load_data_button.clicked.connect(self.load_data_file)
        # self.documentation_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://houcklab.github.io/HouckLab_QICK/index.html")))
        self.documentation_button.clicked.connect(self.generate_plot)

        # Tab Change and Close signals
        self.central_tabs.currentChanged.connect(self.change_tab)
        self.central_tabs.tabCloseRequested.connect(self.close_tab)
        self.side_tabs.currentChanged.connect(self.check_log_read)

        # Signals for RFSoC from the accounts panel
        self.accounts_panel.rfsoc_attempt_connection.connect(self.connect_rfsoc)
        self.accounts_panel.rfsoc_disconnect.connect(self.disconnect_rfsoc)
        # Signals for the RFSoC to the accounts panel
        self.rfsoc_connection_updated.connect(self.accounts_panel.rfsoc_connection_updated)

        # Log message handler installation
        qInstallMessageHandler(self.log_panel.message_handler)
        # self.test_logging()

        # Plot Interceptor
        self._original_show = plt.show
        plt.show = self._intercept_plt_show_wrapper()

    def disconnect_rfsoc(self):
        """
        Disconnects the RFSoC instance by setting RFSoC attributes to None.
        """
        self.soc = None
        self.soccfg = None
        self.soc_connected = False
        qInfo("Disconnected from RFSoC")

    def connect_rfsoc(self, ip_address):
        """
        Connects the RFSoC instance to the specified IP address by calling makeProxy.

        :param ip_address: The IP address of the RFSoC instance.
        :type ip_address: str
        """

        qInfo("Attempting to connect to RFSoC")
        if ip_address is not None:
            # Attempt RFSoC connection via makeProxy
            try:
                self.soc, self.soccfg = makeProxy(ip_address)
            except Exception as e:
                self.soc_connected = False
                self.soc_status_label.setText('<html><b>✖ Soc Disconnected</b></html>')
                QMessageBox.critical(None, "Error", "RFSoC connection to failed (see log).")
                qCritical("RFSoC connection to " + ip_address + " failed: " + str(e))
                self.rfsoc_connection_updated.emit(ip_address, 'failure') # emit failure to accounts tab
                return

            # Verifying RFSoc connection
            try:
                msg = str(self.soc)
                # qInfo(f"RFSoC Info: " + msg)
                # print("Available Methods:", self.soc._pyroMethods)
            except Exception as e:
                # Connection invalid despite makeProxy success
                self.disconnect_rfsoc()
                self.soc_status_label.setText('<html><b>✖ Soc Disconnected</b></html>')
                QMessageBox.critical(None, "Error", "RFSoC connection invalid (see log).")
                qCritical("RFSoC connection to " + ip_address + " invalid: " + str(e))
                self.rfsoc_connection_updated.emit(ip_address, 'failure')
                return
            else:
                self.soc_connected = True
                self.soc_status_label.setText('<html><b>✔ Soc connected</b></html>')
                self.rfsoc_connection_updated.emit(ip_address, 'success') # emit success to accounts tab
        else:
            qCritical("RFSoC IP address is unspecified, param passed is " + str(ip_address))
            QMessageBox.critical(None, "Error", "RFSoC IP Address not given.")

    def run_experiment(self):
        """
        Runs the experiment instance of the current active tab via the RFSoC connection. This function is where the
        new Experiment Worker Thread is created and all signals for data updating and experiment termination
        are connected.

        The desired config format for running an experiment merges Base and Experiment Config as well as downgrades
        their level.

        .. code-block:: python

            config = {
              "config_field1": 000,
              "config_field2": 000,
              "config_field3": 000,
              ...
              "config_field": 000,
            }
        """

        if self.soc_connected: # ensure RFSoC connection
            if self.current_tab.experiment_obj is None: # ensure tab is not a data tab
                qCritical("Attempted execution of a data tab (" + self.current_tab.tab_name +
                          ")rather than an experiment tab")
                QMessageBox.critical(None, "Error", "Tab is a Data tab.")
                return

            self.thread = QThread()


            # Handling config specific to the current tab
            # An experiment (both old and T2, want base and experiment config combined and flatted. Voltage Config stays as is.
            self.current_tab.config = self.config_tree_panel.config
            experiment_format_config = self.current_tab.config.copy()
            experiment_format_config.update(experiment_format_config.pop("Base Config", {}))
            experiment_format_config.update(experiment_format_config.pop("Experiment Config", {})) # will override duplicates

            if "sets" not in experiment_format_config:
                experiment_format_config["sets"] = 1

            # Create experiment object using updated config and current tab's experiment instance
            experiment_class = self.current_tab.experiment_obj.experiment_class
            # print(inspect.getsourcelines(experiment_class))

            experiment_type = self.current_tab.experiment_obj.experiment_type
            if experiment_type == ExperimentClassT2:
                # Retrieving hardware (ie. if voltage interface required, make sure it is included)
                collected_hardware = [self.soc, self.soccfg]
                hardware_req = self.current_tab.experiment_obj.experiment_hardware_req

                if any(issubclass(cls, VoltageInterface) for cls in hardware_req):
                    if not self.voltage_controller_panel.connected or self.voltage_controller_panel.voltage_interface is None:
                        QMessageBox.critical(None, "Error", "Voltage Controller needed but not connected.")
                        qCritical("Voltage Controller needed but not connected.")
                        return

                    voltage_hardware = self.voltage_controller_panel.voltage_hardware # get the connected interface
                    if not any(issubclass(type(voltage_hardware), cls) for cls in hardware_req): # check it is of the right type
                        QMessageBox.critical(None, "Error", "Voltage Controller not of correct type.")
                        qCritical("Voltage Controller not of right type. Requires, " + str(hardware_req))
                        return
                    else:
                        collected_hardware.append(voltage_hardware)

                self.experiment_instance = experiment_class(hardware=collected_hardware, cfg=experiment_format_config)

            # Normal Experiments
            else:
                self.experiment_instance = experiment_class(soc=self.soc, soccfg=self.soccfg, cfg=experiment_format_config)


            ### Creating the experiment worker from ExperimentThread and Connecting Signals
            self.experiment_worker = ExperimentThread(experiment_format_config, soccfg=self.soccfg,
                                                      exp=self.experiment_instance, soc=self.soc)
            self.experiment_worker.moveToThread(self.thread) # Move the ExperimentThread onto the actual QThread

            # Connecting started and finished signals
            self.thread.started.connect(self.current_tab.prepare_file_naming)
            self.thread.started.connect(self.experiment_worker.run) # run experiment
            self.experiment_worker.finished.connect(self.thread.quit) # stop thread
            self.experiment_worker.finished.connect(self.experiment_worker.deleteLater) # delete worker
            self.thread.finished.connect(self.thread.deleteLater) # delete thread
            self.thread.finished.connect(self.stop_experiment) # update UI

            # Connecting data related slots
            self.experiment_worker.updateData.connect(self.current_tab.update_data) # update data & plot
            self.experiment_worker.updateProgress.connect(self.update_progress) # update progress bar
            self.experiment_worker.RFSOC_error.connect(self.RFSOC_error) # connect any RFSoC errors


            ### button and GUI updates
            self.update_progress(0)
            self.experiment_progress_bar.setValue(1)
            self.start_experiment_button.setEnabled(False)
            self.stop_experiment_button.setEnabled(True)

            self.thread.start()
        else:
            qCritical("The RfSoC instance is not yet connected. Current soc has the value: " + str(self.soc))
            QMessageBox.critical(None, "Error", "RfSoC Disconnected.")
            return

    def stop_experiment(self):
        """
        Stop an Experiment if not auto-terminated and update respective UI.
        """

        if self.experiment_worker:
            self.experiment_worker.stop()
            qDebug("Stopping the experiment worker...")

        self.stop_experiment_button.setEnabled(False)
        self.start_experiment_button.setEnabled(True)
        self.voltage_controller_panel.update_voltage_channels()  # update voltages
        if hasattr(self.current_tab, 'tab_name'): # dumb way to make sure not accessing empty tab_bane
            qInfo("Stopped Experiment: " + str(self.current_tab.tab_name))

    def closeEvent(self, event):
        """
        Overrides the default closeEvent() function in a PyQt widget by first ensuring all threads have stopped.

        :param event: The PyQt widget to close.
        :type event: QCloseEvent
        """

        self.stop_experiment()

        # reassign plt.show
        plt.show = self._original_show

        event.accept()

    def load_experiment_file(self):
        """
        Gets an .py experiment file per user input and calls the create_experiment_tab() function.
        """

        options = QFileDialog.Options()
        file, _ = QFileDialog.getOpenFileName(self, "Open Python File", "..\\",
                                              "Python Files (*.py)", options=options)
        if not file:
            return
        else:
            path = Path(file)

            imports = self.extract_direct_imports(str(path))
            if "socProxy" in imports:
                qCritical("Do not import socProxy in your experiment files, connect to an RFSoc via the GUI (comment out that import line).")
                QMessageBox.critical(None, "Error", "No socProxy import allowed (see log).")
                return

            qInfo("Loading experiment file: " + str(path))
            self.create_experiment_tab(str(path)) # pass full path of the experiment file

    def create_experiment_tab(self, path):
        """
        Creates a new QQuarkTab instance for the new tab of an experiment type by passing the absolute path of the
        selected experiment file. Also handles UI updates. See QQuarkTab class for how information is extracted from
        the given path.

        :param path: The path to the experiment file.
        :type path: str
        """

        tab_count = self.central_tabs.count()
        experiment_name = os.path.splitext(os.path.basename(path))[0]

        # Creating a new QQuarkTab that extracts all features from the experiment file (see QQuarkTab documentation)
        new_experiment_tab = QQuarkTab(path, experiment_name, True)
        if new_experiment_tab.experiment_obj.experiment_class is None: # not valid experiment file
            qCritical("The experiment tab failed to be created - source of the error found in QQuarkTab module.")
            return

        # Handling UI updates: Update current tab, enable experiment running, update ConfigPanel
        tab_idx = self.central_tabs.addTab(new_experiment_tab, (experiment_name + ".py"))
        self.central_tabs.setCurrentIndex(tab_idx)
        self.start_experiment_button.setEnabled(True)
        self.config_tree_panel.set_config(new_experiment_tab.config) # important, update config panel
        self.current_tab = new_experiment_tab

        # Signals from QuarkTabs
        self.current_tab.updated_tab.connect(self.update_tab)

        # Remove the template tab created on GUI initialization
        if not self.tabs_added and tab_count == 1:
                self.central_tabs.removeTab(0)
        self.tabs_added = True

    def update_tab(self):
        """
        Updates a tab UI, which currently just means the config and voltage panel.
        """
        self.config_tree_panel.set_config(self.current_tab.config) # Important, update config panel
        self.voltage_controller_panel.changed_tabs(self.current_tab)  # Important: update voltage panel
        self.current_tab.setup_plotter_options()  # setup plotter options

    def change_tab(self, idx):
        """
        Called upon tab change of the central tab widget. Updates UI and current tab attributes.

        :param idx: The index of the newly selected tab widget.
        :type idx: int
        """

        if self.central_tabs.count() != 0:
            self.current_tab = self.central_tabs.widget(idx)
            self.config_tree_panel.set_config(self.current_tab.config) # Important: update config panel
            self.voltage_controller_panel.changed_tabs(self.current_tab) # Important: update voltage panel
            self.current_tab.setup_plotter_options() # setup plotter options

            if self.current_tab.experiment_obj is None: # check if tab is a data or experiment tab
                self.start_experiment_button.setEnabled(False)
            else:
                self.start_experiment_button.setEnabled(True)

    def close_tab(self, idx):
        """
        Called upon a user closing a central experiment or data tab. Updates tab list and UI.

        :param idx: The index of the closed tab widget.
        :type idx: int
        """

        tab_to_delete = self.central_tabs.widget(idx)
        tab_name = tab_to_delete.experiment_name
        QQuarkTab.custom_plot_methods.pop(tab_name, None)

        self.central_tabs.removeTab(idx) # remove tab from widget

        if self.central_tabs.count() == 0: # if no tabs remaining
            self.start_experiment_button.setEnabled(False)
            self.current_tab = None
        else:
            current_tab_idx = self.central_tabs.currentIndex() # get the tab changed to upon closure
            self.change_tab(current_tab_idx)
            self.current_tab.setup_plotter_options()

        tab_to_delete.deleteLater() # safely delete the tab

    def update_progress(self, sets_complete):
        """
        The function that updates the progress bar based on experiment progress. It retrieves the reps and sets fields
        of the current tab's config to do so. Usually called via a signal from an ExperimentThread.

        :param sets_complete: The number of sets of the experiment that have been completed
        :type sets_complete: int
        """

        unformatted_config = self.current_tab.config["Base Config"] | self.current_tab.config["Experiment Config"]
        # Getting the total reps and sets to be run from the experiment configs
        if 'reps' in unformatted_config and 'sets' in unformatted_config:
            reps, sets = unformatted_config['reps'], unformatted_config['sets']
            self.experiment_progress_bar.setValue(math.floor(float(sets_complete) / sets * 100)) # calculate completed %
            self.experiment_progress_bar.setFormat(str(sets_complete * reps) + "/" + str(sets * reps)) # update text

    def RFSOC_error(self, e):
        """
        The function called when RFSoC returns an error to display in the Log.
        """

        qCritical("RFSoC thew the error: " + str(e))
        qCritical(traceback.print_exc())
        QMessageBox.critical(None, "RFSOC error", "RfSoc has thrown an error (see log).")

    def load_data_file(self):
        """
        Gets an .h5 experiment file per user input. Then calls the create_data_tab() function with the file's path.
        """

        # Load an data file
        options = QFileDialog.Options()
        file, _ = QFileDialog.getOpenFileName(self, "Open Data h5 File", "..\\",
                                              "h5 Files (*.h5)", options=options)
        if not file:
            return
        else:
            path = Path(file)
            qInfo("Loading dataset file: " + str(path))
            self.create_data_tab(file)  # pass full path of the data file

    def create_data_tab(self, file):
        """
        Creates a new QQuarkTab instance for the new tab of type dataset. See QQuarkTab class for how dataset
        information is extracted via the given path. Also handles UI updates.

        :param path: The path to the data file.
        :type path: str
        """

        tab_count = self.central_tabs.count()
        file_name = os.path.basename(file)
        # Creates the new QQuarkTab instance specifying not an experiment tab
        new_data_tab = QQuarkTab(None, file_name, False, file)

        # Handle UI updates
        tab_idx = self.central_tabs.addTab(new_data_tab, (file_name))
        self.central_tabs.setCurrentIndex(tab_idx)
        self.start_experiment_button.setEnabled(False)
        self.config_tree_panel.set_config(new_data_tab.config) # update config (when data files have config)
        self.current_tab = new_data_tab

        if not self.tabs_added:
            if tab_count == 1:
                self.central_tabs.removeTab(0)
        self.tabs_added = True

    def check_log_read(self):
        """
        Check if the Log tab has been opened and set the Log to the state read.
        """
        log_index = self.side_tabs.indexOf(self.log_panel)

        if log_index == self.side_tabs.currentIndex():
            self.side_tabs.setTabText(log_index, "Log")
            self.log_panel.logger.setFocus()

    def extract_direct_imports(self, file_path):
        """
        Extracts and returns the most direct module name from each import statement in a Python file.

        :param file_path: Full path to the Python file.
        :type file_path: str
        :returns: List of direct module names from the import statements.
        :rtype: list[str]
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

    def _intercept_plt_show_wrapper(self):
        """
        The wrapper function used to intercept any calls plt.show that is run from the GUI. This wrapper intercept
        method is required for a pyqt thread to catch calls.
        """

        def wrapper(*args, **kwargs):
            """
            The wrapper function that intercepts the call and calls handle_pltplot.
            """
            qInfo("Matplotlib plt.plot intercepted.")
            return self.current_tab.handle_pltplot(*args, **kwargs)
        return wrapper

    def generate_plot(self):
        x = np.linspace(-10, 10, 100)
        y = x
        plt.plot(x, y, label='y=x')
        plt.xlabel('x')
        plt.ylabel('y')
        plt.title('Plot of y = x')
        plt.legend()
        plt.grid(True)
        plt.show()

# Creating the Quarky GUI Main Window
if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)

        # with open("style.qss", "r") as file:
        #     style = file.read()
        # app.setStyleSheet(style)

        ex = Quarky()
        ex.show()
        sys.exit(app.exec_())

    except Exception as e:
        QMessageBox.critical(None, "Critical Error", f"A GUI error occurred: {e}")
        traceback.print_exc()
