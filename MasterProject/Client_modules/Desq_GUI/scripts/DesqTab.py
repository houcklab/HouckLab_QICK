"""
============
DesqTab.py
============
The custom QQuarkTab class for the central tabs module of the main application.

Each QQuarkTab is either an experiment tab or a data tab that stores its own object attributes, configuration,
data, and plotting. Arguable is more important for functionality than the main Desq.py file.
"""
import copy
import os
import json
import time
import h5py
import traceback
from pathlib import Path
import datetime
import shutil
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import numpy as np
from PyQt5.QtGui import QKeySequence, QCursor, QImage, QPixmap, QColor
from PyQt5.QtCore import (
    Qt, QSize, qCritical, qInfo, qDebug, QRect, QTimer,
    pyqtSignal, qWarning, QSettings
)
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy,
    QSpacerItem,
    QMessageBox,
    QLabel,
    QComboBox,
    QFileDialog,
    QShortcut,
    QCheckBox,
    QGraphicsDropShadowEffect,
    QScrollArea,
    QPushButton,
    QSplitter,
)
import pyqtgraph as pg
from matplotlib.collections import PathCollection
from matplotlib.patches import Rectangle

# from MasterProject.Client_modules.Desq_GUI.scripts.ConfigTreePanel import QConfigTreePanel
from MasterProject.Client_modules.Desq_GUI.scripts.ConfigTreePanelAdv import QConfigTreePanel

from MasterProject.Client_modules.Desq_GUI.scripts.ExperimentObject import ExperimentObject
import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers


class ExperimentInfoBar(QWidget):
    """
    Collapsible experiment information section.
    Can store multiple rows of data and expand/collapse on click.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExperimentInfoBar")
        self.setContentsMargins(0, 0, 0, 0)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Header bar with toggle button
        self.header = QWidget()
        self.header.setObjectName("info_headerbar")
        self.header.setContentsMargins(0, 0, 0, 0)
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(0)

        self.toggle_button = Helpers.create_button("", "toggle_button", True, self.header)
        self.toggle_button.setChecked(False)
        self.toggle_button.setStyleSheet(
            "image: url('MasterProject/Client_modules/Desq_GUI/assets/chevron-right.svg');")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.toggle_button.clicked.connect(self.toggle_content)

        self.header_label = QLabel("Info")

        self.header_layout.addWidget(self.toggle_button)
        self.header_layout.addWidget(self.header_label)
        self.header_layout.addStretch()

        self.main_layout.addWidget(self.header)

        # Scrollable content area
        self.content_area = QScrollArea()
        self.content_area.setObjectName("info_content_area")
        self.content_area.setWidgetResizable(True)
        self.content_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_area.setMaximumHeight(0)  # collapsed initially
        self.content_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.content_widget = QWidget()
        self.content_widget.setObjectName("info_content_widget")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.content_layout.setSpacing(3)

        self.content_area.setWidget(self.content_widget)
        self.main_layout.addWidget(self.content_area)

        self.setMaximumHeight(15)

    def add_info_row(self, widget: QWidget):
        """Adds a widget row to the content area."""
        self.content_layout.addWidget(widget)

    def toggle_content(self):
        """Expand or collapse the content area."""
        if self.toggle_button.isChecked():
            self.toggle_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/chevron-down.svg');")
            # Calculate needed height dynamically: header + content
            header_height = self.header.sizeHint().height()
            content_height = self.content_widget.sizeHint().height()
            total_height = header_height + content_height

            # Cap the maximum to avoid it growing too big
            max_allowed = 300  # adjust if needed
            final_height = min(total_height, max_allowed)

            self.content_area.setMaximumHeight(content_height)
            self.setMaximumHeight(final_height)
        else:
            self.toggle_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/chevron-right.svg');")
            # Collapse
            self.content_area.setMaximumHeight(0)
            self.setMaximumHeight(self.header.sizeHint().height())


class QDesqTab(QWidget):
    """
    A tab widget that holds either an experiment instance or a data instance. See __init__ for
    initialization types.
    """

    custom_plot_methods = {}
    """
    custom_plot_methods (dict): A dictionary of the added custom plotting methods.
    """

    updated_tab = pyqtSignal()  # argument is ip_address
    """
    The Signal sent to the main application (Desq.py) that tells the program the current tab was updated.
    """

    def __init__(
            self,
            experiment_id=(None, None),
            tab_name=None,
            source_file_name=None,
            is_experiment=None,
            dataset_file=None,
            app=None,
            workspace=None,
    ):
        """
        Initializes an instance of a QQuarkTab widget that will either be of type experiment based on the parameters
        passed.
            * An experiment will pass: [experiment_path, tab_name, is_experiment=True].
            * A dataset will pass: [tab_name, is_experiment=False, dataset_file]

        :param experiment_id: The experiment path and the class name in a tuple
        :type experiment_id: tuple(str, str)
        :param tab_name: The name of the tab widget.
        :type tab_name: str
        :param source_file_name: The name of the file the experiment lies in.
        :type source_file_name: str
        :param is_experiment: Whether the tab corresponds to an experiment or dataset.
        :type is_experiment: bool
        :param dataset_file: The path to the dataset file.
        :type dataset_file: str
        :param app: The main application (Desq.py).
        :type app: QApplication
        """

        super().__init__()
        self.app = app

        ### Experiment Variables
        self.tab_name = str(tab_name) if tab_name else None
        self.source_file_name = source_file_name
        self.is_experiment = is_experiment
        self.workspace = workspace or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        # Experiment config panel
        self.experiment_config_panel = QConfigTreePanel(
            self,
            self.tab_name if self.is_experiment else None,
            "Experiment",
            None,
            {},
            workspace=self.workspace,
        )

        self.experiment_obj = None if experiment_id == (None, None) \
            else ExperimentObject(self, experiment_id)
        self.dataset_file = dataset_file
        self.data = None
        self.plots = []
        self.labels_added = False
        self.labels = []
        self.matplotlib_canvases = []
        self.matplotlib_proxies = []
        self.matplotlib_viewboxes = []
        self.last_run_experiment_config = {}

        ### Setting up the Tab
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("QDesqTab")

        self.tab_layout = QHBoxLayout(self)
        self.tab_layout.setContentsMargins(0, 0, 0, 0)
        self.wrapper = QWidget()
        self.wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.wrapper.setObjectName("wrapper")

        # Create splitter for plot and config panel
        self.splitter = QSplitter(self.wrapper)
        self.splitter.setOpaqueResize(True)
        self.splitter.setHandleWidth(6)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setObjectName("desq_tab_splitter")
        self.splitter.setOrientation(Qt.Horizontal)

        ### Plotter within Tab
        self.plot_wrapper = QWidget(self.splitter)
        self.plot_layout = QVBoxLayout(self.plot_wrapper)
        self.plot_layout.setContentsMargins(10, 0, 2, 7)
        self.plot_layout.setSpacing(0)
        self.plot_layout.setObjectName("plot_layout")

        ### Plot Utilities Bar
        self.plot_utilities_container = QWidget()
        self.plot_utilities_container.setMaximumHeight(30)
        self.plot_utilities_container.setObjectName("plot_utilities_container")
        self.plot_utilities = QHBoxLayout(self.plot_utilities_container)
        self.plot_utilities.setContentsMargins(2, 0, 2, 0)
        self.plot_utilities.setSpacing(0)
        self.plot_utilities.setObjectName("plot_utilities")

        self.reExtract_experiment_button = Helpers.create_button("ReExtract", "reExtract_experiment_button", False,
                                                                 self.plot_utilities_container)
        self.reExtract_experiment_button.setToolTip("Re-extracts the experiment file to reflect changes to code file")
        self.replot_button = Helpers.create_button("RePlot", "replot_button", False, self.plot_utilities_container)
        self.replot_button.setToolTip("Replots the current data using plot method")
        self.snip_plot_button = Helpers.create_button("Snip", "snip_plot_button", True, self.plot_utilities_container)
        self.snip_plot_button.setToolTip("Snip Plot to Clipboard")
        self.export_data_button = Helpers.create_button("Export", "export_data_button", False,
                                                        self.plot_utilities_container)
        self.coord_label = QLabel("X: _____ Y: _____")  # coordinate of the mouse over the current plot
        self.coord_label.setAlignment(Qt.AlignRight)
        self.coord_label.setObjectName("coord_label")

        spacerItem = QSpacerItem(0, 30, QSizePolicy.Expanding, QSizePolicy.Fixed)  # spacer
        self.plot_utilities.addWidget(self.reExtract_experiment_button)
        self.plot_utilities.addWidget(self.replot_button)
        self.plot_utilities.addWidget(self.snip_plot_button)
        self.plot_utilities.addWidget(self.export_data_button)
        self.plot_utilities.addItem(spacerItem)
        self.plot_utilities.addWidget(self.coord_label)
        self.plot_layout.addWidget(self.plot_utilities_container)

        ### Experiment Information Bar
        self.experiment_infobar = ExperimentInfoBar(self)

        self.source_file_label = QLabel(f"Source File: {self.source_file_name}.py")
        self.source_file_label.setObjectName("source_file_label")
        self.runtime_label = QLabel("Estimated Runtime: ---")  # estimated experiment time
        self.runtime_label.setObjectName("runtime_label")
        self.endtime_label = QLabel("End: ---")  # estimated experiment time
        self.endtime_label.setObjectName("endtime_label")
        self.hardware_label = QLabel(f"Hardware: [Proxy, QickConfig]")

        if self.experiment_obj is not None and self.experiment_obj.experiment_hardware_req is not None:
            hardware_str = "[" + (", ".join(cls.__name__ for cls in self.experiment_obj.experiment_hardware_req)) + "]"
            self.hardware_label.setText("Hardware: " + hardware_str)
        self.hardware_label.setObjectName("hardware_label")

        self.experiment_infobar.add_info_row(self.source_file_label)
        self.experiment_infobar.add_info_row(self.runtime_label)
        self.experiment_infobar.add_info_row(self.endtime_label)
        self.experiment_infobar.add_info_row(self.hardware_label)
        self.plot_layout.addWidget(self.experiment_infobar)

        ### Plot Settings Bar
        self.plot_settings_container = QWidget()
        self.plot_settings_container.setMaximumHeight(30)
        self.plot_settings = QHBoxLayout(self.plot_settings_container)
        self.plot_settings.setContentsMargins(10, 0, 0, 5)
        self.plot_settings.setSpacing(5)
        self.plot_settings.setObjectName("plot_settings")

        self.plot_method_label = QLabel("Plotter:")
        self.plot_method_label.setObjectName("plot_method_label")
        self.plot_method_combo = QComboBox(self.plot_settings_container)

        self.plot_method_combo.setFixedWidth(100)
        self.plot_method_combo.setObjectName("plot_method_combo")

        self.average_simult_checkbox = QCheckBox("Average Simult.", self.plot_settings_container)
        self.average_simult_checkbox.setToolTip("Average intermediate data simultaneously versus at end of set.")

        self.use_matplotlib_checkbox = QCheckBox("Matplotlib", self.plot_settings_container)
        self.use_matplotlib_checkbox.setToolTip("Use native Matplotlib rendering instead of converting to PyQtGraph.")
        self.use_matplotlib_checkbox.setChecked(False)

        self.delete_label = QLabel("hover + \'d\' to delete")  # coordinate of the mouse over the current plot
        self.delete_label.setAlignment(Qt.AlignRight)
        self.delete_label.setObjectName("delete_label")

        spacerItem = QSpacerItem(0, 30, QSizePolicy.Expanding, QSizePolicy.Fixed)  # spacer
        self.plot_settings.addWidget(self.plot_method_label)
        self.plot_settings.addWidget(self.plot_method_combo)
        self.plot_settings.addWidget(self.average_simult_checkbox)
        self.plot_settings.addWidget(self.use_matplotlib_checkbox)
        self.plot_settings.addItem(spacerItem)
        self.plot_settings.addWidget(self.delete_label)
        self.plot_layout.addWidget(self.plot_settings_container)

        # The actual plot itself (lots of styling attributes
        self.plot_widget = pg.GraphicsLayoutWidget(self)
        label = self.plot_widget.ci.addLabel("Nothing to plot.", row=0, col=0, colspan=2, size='12pt')
        self.labels.append(label)
        self.plot_widget.setBackground("w")
        self.plot_widget.ci.setSpacing(2)  # Reduce spacing
        self.plot_widget.ci.setContentsMargins(3, 3, 3, 3)  # Adjust margins of plots
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_widget.setMinimumSize(QSize(375, 0))
        self.plot_widget.setObjectName("plot_widget")

        self.plot_layout.addWidget(self.plot_widget)
        self.plot_layout.setStretch(0, 1)
        self.plot_layout.setStretch(1, 10)
        self.plot_wrapper.setLayout(self.plot_layout)

        self.setup_plotter_options()

        # Add config panel
        self.experiment_config_panel.setParent(self.splitter)

        # Defining the default sizes for the splitter and adding everything together
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)
        self.tab_layout.addWidget(self.splitter)
        self.setLayout(self.tab_layout)

        # extract dataset file depending on the tab type being a dataset
        if not self.is_experiment and self.dataset_file is not None:
            self.load_dataset_file(self.dataset_file)
        self.setup_signals()

    def setup_signals(self):
        """
        Sets up all the signals and slots of the QQuarkTab widget. This includes the toolbar buttons, plot
        functionalities, and export settings.
        """

        # self.plot_method_combo.currentIndexChanged.connect(self.plot_method_changed)
        self.plot_widget.scene().sigMouseMoved.connect(self.update_coordinates)  # coordinates viewer
        self.snip_plot_button.clicked.connect(self.capture_plot_to_clipboard)
        self.export_data_button.clicked.connect(self.export_data)
        self.reExtract_experiment_button.clicked.connect(self.reExtract_experiment)
        self.replot_button.clicked.connect(self.replot_data)
        self.plot_method_combo.currentIndexChanged.connect(self.handle_plot_combo_selection)

        self.remove_plot_shortcut = QShortcut(QKeySequence("D"), self)
        self.remove_plot_shortcut.activated.connect(self.remove_plot)

        # Create the default export output_dir for autosaving if of type experiment
        if self.is_experiment:
            # Experiment Config Tree Panel signal
            self.experiment_config_panel.update_voltage_panel.connect(self.app.voltage_controller_panel.update_sweeps)
            self.experiment_config_panel.update_runtime_prediction.connect(self.app.call_tab_runtime_prediction)

            self.reExtract_experiment_button.setEnabled(True)

            # add custom plotter to options
            if self.is_experiment and self.experiment_obj is not None:
                if self.experiment_obj.experiment_plotter is not None:
                    QDesqTab.custom_plot_methods[self.tab_name] = self.experiment_obj.experiment_plotter

            # predict runtime
            self.predict_runtime(self.experiment_config_panel.config)

        if self.tab_name != "None":
            self.export_data_button.setEnabled(True)
            self.replot_button.setEnabled(True)

    def setup_plotter_options(self):
        """
        This method sets up the plotting options based on the current experiment. If the experiment gave a plotter
        function, it is automatically set as the default method. Otherwise, the current methods available only include
        'Auto'.
        """
        self.plot_method_combo.blockSignals(True)

        self.plot_method_combo.clear()
        self.plot_method_combo.addItems(["None"])

        # print(QQuarkTab.custom_plot_methods)

        for key in QDesqTab.custom_plot_methods.keys():
            if self.tab_name is not None and key == self.tab_name:
                self.plot_method_combo.insertItem(0, key)
                self.plot_method_combo.setCurrentText(key)
            else:
                self.plot_method_combo.addItems([key])

        self.plot_method_combo.addItems(["Add..."])

        self.plot_method_combo.blockSignals(False)

    def handle_plot_combo_selection(self):
        """
        Handler for when the Plotting Methods Combo is changed. If it is changed to "Plot: Add...", then it performs the
        functionality for adding a plotter function. This method is used because a PyQt Combo cannot add buttons,
        this is the workaround.
        """
        if self.plot_method_combo.currentText() == "Add...":
            self.plot_method_combo.blockSignals(True)  # Prevent adding a new combo from calling it again in a loop

            file = Helpers.open_file_dialog("Open Python File", "Python Files (*.py)",
                                            "add_plotter_method", self, file=True)

            if file:
                path = str(Path(file))
                qInfo("Retrieving experiment plotter from: " + path)
                experiment_name = os.path.splitext(os.path.basename(path))[0]
                temp_experiment = ExperimentObject(self, experiment_name, path)
                if temp_experiment.experiment_plotter is not None:
                    self.plot_method_combo.insertItem(0, experiment_name)
                    self.plot_method_combo.setCurrentText(experiment_name)
                    QDesqTab.custom_plot_methods[experiment_name] = temp_experiment.experiment_plotter
                    qInfo("Added " + experiment_name + " plotter.")
                    self.replot_data()
                else:
                    self.plot_method_combo.setCurrentText("None")
                    qDebug("No plotter function found within " + experiment_name)
            else:
                self.plot_method_combo.setCurrentText("None")

            self.plot_method_combo.blockSignals(False)  # re_enable plotting
        else:
            if self.data is not None:
                self.replot_data()

    def load_dataset_file(self, dataset_file):
        """
        Takes the dataset file and loads the dict, before calling the plotter.

        :param dataset_file: The path to the dataset file.
        :type dataset_file: str
        """

        self.data = Helpers.h5_to_dict(dataset_file)

        # Extracting the Config
        if "config" in self.data:
            qInfo("Config in h5 metadata found")
            temp_config = self.data["config"]

            self.experiment_config_panel.update_config_dict(temp_config, reset=True)
            self.data.pop("config")
        else:
            qDebug("No config in metadata found")

        # print(self.data)

        self.plot_data()

    def clear_plots(self):
        """
        Clears the plots.
        """
        qInfo("Clearing plots")
        for label in self.labels:
            self.plot_widget.ci.removeItem(label)
        for plot in self.plots:
            self.plot_widget.ci.removeItem(plot)

        # Clear matplotlib canvases and related widgets if they exist
        if hasattr(self, 'matplotlib_canvases'):
            for canvas in self.matplotlib_canvases:
                canvas.close()
            self.matplotlib_canvases = []

        if hasattr(self, 'matplotlib_proxies'):
            for proxy in self.matplotlib_proxies:
                if proxy.scene():
                    self.plot_widget.scene().removeItem(proxy)
            self.matplotlib_proxies = []

        if hasattr(self, 'matplotlib_viewboxes'):
            for vb in self.matplotlib_viewboxes:
                self.plot_widget.ci.removeItem(vb)
            self.matplotlib_viewboxes = []

        self.plot_widget.ci.clear()
        self.plots = []
        self.labels = []
        self.labels_added = False

    def reExtract_experiment(self):
        """
        ReExtracts the current experiment via the experiment_path given. This allows a user to change the experiment code
        or even the plotter without having to exit the GUI, close any tabs, or import the experiment from scratch.
        """

        if self.experiment_obj is not None:
            self.experiment_obj.load_module_and_class()

            if self.experiment_obj.experiment_plotter is not None:
                self.custom_plot_methods[self.tab_name] = self.experiment_obj.experiment_plotter

            if self.experiment_obj is not None and self.experiment_obj.experiment_hardware_req is not None:
                hardware_str = "[" + (
                    ", ".join(cls.__name__ for cls in self.experiment_obj.experiment_hardware_req)) + "]"
                self.hardware_label.setText("Hardware: " + hardware_str)
            qDebug("ReExtracted Experiment: experiment attributes extracted.")
            self.updated_tab.emit()

            self.reExtract_experiment_button.setText('Done!')
            QTimer.singleShot(3000, lambda: self.reExtract_experiment_button.setText('ReExtract'))

    def update_coordinates(self, pos):
        """
        Updates the coordinates label to reflect the cursor's location on a plot's axis. Also gets the value of the
        plot at the coordinates if the plot is a color plot.

        :param pos: The coordinates of the cursor
        :type pos: tuple
        """

        # find the active plot
        for plot in self.plots:
            vb = plot.vb  # ViewBox of each plot
            if plot.sceneBoundingRect().contains(pos):
                self.plot_widget.setCursor(Qt.CrossCursor)  # make cursor cross-hairs
                mouse_point = vb.mapSceneToView(pos)  # translate location to axis coordinates
                x, y = mouse_point.x(), mouse_point.y()

                # Try to find an ImageItem in the plot (for color data)
                image_items = [item for item in plot.items if isinstance(item, pg.ImageItem)]
                if image_items:
                    img_item = image_items[0]
                    image = img_item.image.T  # The underlying numpy array, assuming plotting origins
                    if image is not None:
                        # Map view coordinates to array indices
                        transform = img_item.transform()
                        inv_transform = transform.inverted()[0]
                        mapped = inv_transform.map(mouse_point)

                        ix, iy = int(mapped.x()), int(mapped.y())
                        if 0 <= ix < image.shape[1] and 0 <= iy < image.shape[0]:
                            value = image[iy, ix]  # Note: row = y, col = x
                            self.coord_label.setText(f"X: {x:.4f} Y: {y:.4f} Val: {value:.4f}")
                            return

                # If no image or outside bounds
                self.coord_label.setText(f"X: {x:.4f} Y: {y:.4f}")
                return

    def capture_plot_to_clipboard(self):
        """
        Captures a screenshot of the plot via a QPixmap and saves it to the users clipboard. Paste normally.
        """
        pixmap = self.plot_widget.grab()  # This grabs the content of the plot_widget
        clipboard = QApplication.clipboard()
        clipboard.setPixmap(pixmap)
        qInfo("Current graph snipped to clipboard!")

        self.snip_plot_button.setText('Done!')
        QTimer.singleShot(3000, lambda: self.snip_plot_button.setText('Snip'))

    def remove_plot(self):
        """
        Retrieves the cursor's current position and removes the corresponding plot that it is hovering over
        from the layout.
        """

        # Get cursor position
        global_pos = QCursor.pos()
        pos = self.plot_widget.mapFromGlobal(global_pos)  # maps it to its position relative to the plotting space

        # Loops through the list of plots
        for plot in self.plots:
            vb = plot.vb  # ViewBox of each plot
            if plot.sceneBoundingRect().contains(pos):
                self.plots.remove(plot)
                self.plot_widget.removeItem(plot)
                self.plot_widget.update()

    def plot_data(self, exp_instance=None, data_to_plot=None):
        """
        Plots the data of the QQuarkTab experiment/dataset using prepared data that is prepared by
        the specified plotting method of the dropdown menu.

        :param exp_instance: The instance of the experiment.
        :type exp_instance: object
        :param data_to_plot: The data to be plotted.
        :type data_to_plot: dict
        """
        if data_to_plot is None:
            data_to_plot = self.data
        if len(self.plots) == 0:
            self.clear_plots()

        plotting_method = self.plot_method_combo.currentText()  # Get the Plotting Method
        try:
            if plotting_method == "None":  # No longer using auto preparation
                if not self.is_experiment:
                    self.auto_plot_prepare()
                else:
                    if hasattr(exp_instance, "display") and callable(getattr(exp_instance, "display")):
                        # Get the method bound to the instance
                        instance_method = exp_instance.display

                        # Walk through the MRO and find where 'display' was first defined
                        for cls in type(exp_instance).__mro__[1:]:  # Skip the subclass itself
                            if "display" in cls.__dict__:
                                parent_method = cls.__dict__["display"]
                                break
                        else:
                            parent_method = None

                        # Check if it's actually overridden
                        if parent_method is not None and instance_method.__func__ is not parent_method:
                            exp_instance.display(data_to_plot, plotDisp=True)
                        else:
                            self.auto_plot_prepare()
                    else:
                        self.auto_plot_prepare()
            elif plotting_method in QDesqTab.custom_plot_methods:
                QDesqTab.custom_plot_methods[plotting_method](self.plot_widget, self.plots, data_to_plot)
        except Exception as e:
            qCritical("Failed to plot using method [" + plotting_method + "]: " + str(e))
            qCritical(traceback.print_exc())

    def handle_pltplot(self, *args, **kwargs):
        """
        Handles a matplotlib plot by either:
        1. Embedding it natively if "Matplotlib" checkbox is checked
        2. Extracting its data and plotting it using pyqtgraph (default)
        """

        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()

        # Check if matplotlib checkbox is checked
        if self.use_matplotlib_checkbox.isChecked():
            return self.embed_matplotlib_plots(*args, **kwargs)
        else:
            return self.convert_matplotlib_to_pyqtgraph(*args, **kwargs)

    def embed_matplotlib_plots(self, *args, **kwargs):
        """
        Embeds matplotlib plots directly into the GraphicsLayout using QGraphicsProxyWidget.
        """

        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()

        figures = list(map(plt.figure, plt.get_fignums()))
        curr_row = 0

        for i, fig in enumerate(figures):
            ncols = len(fig.get_axes()) if len(fig.get_axes()) > 0 else 1

            # Set figure size to be reasonable and tight
            dpi = fig.get_dpi()
            fig.set_size_inches(8, 6)
            fig.tight_layout(pad=0.5)

            # Create matplotlib canvas for the figure
            canvas = FigureCanvas(fig)
            canvas.draw()  # Ensure the canvas is fully rendered

            # Set reasonable size constraints
            canvas.setMinimumSize(600, 450)
            canvas.setMaximumSize(1200, 900)
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            # Create a proxy widget to embed the matplotlib canvas
            proxy = self.plot_widget.scene().addWidget(canvas)

            # Add the proxy to a ViewBox in the GraphicsLayout
            view_box = self.plot_widget.ci.addViewBox(row=curr_row, col=0, colspan=ncols)
            view_box.setAspectLocked(True)
            view_box.invertY(True)  # Ensure Y axis is inverted
            view_box.addItem(proxy)

            # Store references to prevent garbage collection and allow cleanup
            if not hasattr(self, 'matplotlib_canvases'):
                self.matplotlib_canvases = []
            if not hasattr(self, 'matplotlib_proxies'):
                self.matplotlib_proxies = []
            if not hasattr(self, 'matplotlib_viewboxes'):
                self.matplotlib_viewboxes = []

            self.matplotlib_canvases.append(canvas)
            self.matplotlib_proxies.append(proxy)
            self.matplotlib_viewboxes.append(view_box)

            curr_row += 1
            self.plot_widget.nextRow()

        self.labels_added = True
        plt.close('all')  # Close matplotlib figures after creating canvases
        qInfo(f"Finished embedding {len(figures)} matplotlib figure(s).")

        return

    def convert_matplotlib_to_pyqtgraph(self, *args, **kwargs):
        """
        Converts matplotlib plots to pyqtgraph by extracting their data.
        (This is the original handle_pltplot behavior)
        """

        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()

        # Title is filename if it is a datafile
        if len(self.plots) == 0 and not self.is_experiment:
            if not self.labels_added:
                label = self.plot_widget.ci.addLabel(self.file_name, row=0, col=0, colspan=2, size='12pt')
                self.labels.append(label)

        figures = list(map(plt.figure, plt.get_fignums()))
        curr_row = 0
        self.curr_plot = 0
        for i, fig in enumerate(figures):
            ncols = len(fig.get_axes())  # This currently places all plots on the same row

            # Get figure title and display
            fig_title = fig._suptitle.get_text() if fig._suptitle else f"{self.file_name} fig{i + 1}"
            if not self.labels_added:
                label = self.plot_widget.ci.addLabel(fig_title, row=curr_row, col=0, colspan=ncols, size='12pt')
                self.labels.append(label)

            curr_row += 1
            self.plot_widget.nextRow()

            for j, ax in enumerate(fig.get_axes()):

                if (
                        len(ax.get_lines()) == 0 and
                        len(ax.get_images()) == 0 and
                        len([coll for coll in ax.collections if isinstance(coll, PathCollection)]) == 0 and
                        len([pat for pat in ax.patches if isinstance(pat, Rectangle)]) == 0
                ):  # Skip plotting if no data in axes
                    continue

                # Extract title for specific plot
                ax_title = ax.get_title() or f"Plot {self.curr_plot + 1}"
                if not self.labels_added:
                    label = self.plot_widget.ci.addLabel(ax_title, row=curr_row, col=j % ncols, colspan=1, size='10pt')
                    self.labels.append(label)
                curr_row += 1
                self.plot_widget.nextRow()

                # Extract and plot the actual axes
                self.extract_and_plot_pyqtgraph(ax, curr_row, j % ncols)

                # Determine when to go next row
                if (j + 1) % ncols == 0:
                    curr_row += 1
                    self.plot_widget.nextRow()

            # Next figure should appear on the next row
            curr_row += 1
            self.plot_widget.nextRow()

        self.labels_added = True
        plt.close()  # close all figs
        qInfo(f"Finished plotting {self.curr_plot} matplotlib extractions.")

        return

    def extract_and_plot_pyqtgraph(self, ax, row, col):
        """
        Convert a matplotlib Axes to a PyQtGraph plot.

        :param ax: Matplotlib axis containing plot data to convert.
        :type ax: matplotlib.axes.Axes
        :param row: Row to plot to on the layout.
        :type row: int
        :param col: Column to plot to on the layout.
        :type col: int
        """

        def mpl_color_to_pg(color):
            """
            Convert a matplotlib color to a format accepted by PyQtGraph (e.g., '#RRGGBB').

            :param color: The color to convert.
            :type color: str
            """
            if isinstance(color, str):
                rgba = mcolors.to_rgba(color)
            else:
                rgba = color
            r, g, b, a = [int(255 * c) for c in rgba]
            return (r, g, b, a)

        if (
                len(ax.get_lines()) == 0 and
                len(ax.get_images()) == 0 and
                len([coll for coll in ax.collections if isinstance(coll, PathCollection)]) == 0 and
                len([pat for pat in ax.patches if isinstance(pat, Rectangle)]) == 0
        ):  # Skip plotting if no data in axes
            return

        new_plot = True
        plot_item_num = 0

        if len(self.plots) > self.curr_plot:  # If plots already exist, then don't create new plots, simply update the existing
            plot = self.plots[self.curr_plot]
            plot_data_items = [item for item in plot.items if
                               isinstance(item, pg.PlotDataItem) or isinstance(item, pg.ImageItem)]
            new_plot = False
        else:
            plot = self.plot_widget.ci.addPlot(row, col)  # Otherwise, create new plots
            self.plots.append(plot)
        self.curr_plot += 1

        # Lines
        for i, line in enumerate(ax.get_lines()):
            # Axis labels
            plot.setLabel('left', ax.get_ylabel())
            plot.setLabel('bottom', ax.get_xlabel())

            # Axis limits
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            plot.setXRange(*xlim)
            plot.setYRange(*ylim)

            x = line.get_xdata()
            y = line.get_ydata()
            if x is None or y is None or len(x) == 0 or len(y) == 0:
                continue

            color = mpl_color_to_pg(line.get_color())
            width = line.get_linewidth()

            style = {'pen': pg.mkPen(color=color, width=width), 'symbol': 'o', 'symbolSize': 5, 'symbolBrush': 'b'}
            if not new_plot:
                plot_data_items[plot_item_num].setData(x, y)
                plot_item_num += 1
            else:
                plot.plot(x, y, **style)

        # Images
        for i, img in enumerate(ax.get_images()):
            data = img.get_array()
            extent = img.get_extent()  # [xmin, xmax, ymin, ymax]

            if data.size == 0:
                continue

            if not new_plot:
                img_image = plot_data_items[plot_item_num]
                img_image.setImage(data.T,
                                   levels=img_image.levels)  # Transpose assumes data was plotted with 'origin="lower"'
                plot_item_num += 1
            else:
                plot.setLabel('left', ax.get_ylabel())
                plot.setLabel('bottom', ax.get_xlabel())

                img_item = pg.ImageItem(image=data.T)  # Transpose assumes data was plotted with 'origin="lower"'
                plot.addItem(img_item)
                color_map = pg.colormap.get("viridis")  # e.g., 'viridis', 'inferno'
                img_item.setLookupTable(color_map.getLookupTable())
                img_item.setRect(pg.QtCore.QRectF(extent[0], extent[2], extent[1] - extent[0], extent[3] - extent[2]))

                # Create ColorBarItem
                color_bar = pg.ColorBarItem(values=(np.nanmin(img_item.image), np.nanmax(img_item.image)),
                                            colorMap=color_map)
                color_bar.setImageItem(img_item, insert_in=plot)  # Add color bar to the plot

        # Handle scatter plots (PathCollection)
        for coll in ax.collections:
            if isinstance(coll, PathCollection):
                offsets = coll.get_offsets()
                if len(offsets) > 0:
                    x, y = offsets[:, 0], offsets[:, 1]
                    # Grab color info (fallback red)
                    facecolors = coll.get_facecolors()
                    color = (255, 0, 0, 150) if len(facecolors) == 0 else tuple(
                        (facecolors[0, :3] * 255).astype(int)) + (int(facecolors[0, 3] * 255),)
                    plot.plot(x, y, pen=None, symbol='o', symbolSize=5, symbolBrush=color)

        # Handle histogram bars (Rectangles)
        for patch in ax.patches:
            if isinstance(patch, Rectangle):
                x = patch.get_x()
                y = patch.get_y()
                w = patch.get_width()
                h = patch.get_height()
                rect = pg.QtWidgets.QGraphicsRectItem(x, y, w, h)
                color = patch.get_facecolor()
                brush = pg.mkBrush([int(c * 255) for c in color])
                rect.setBrush(brush)
                rect.setPen(pg.mkPen(None))
                plot.addItem(rect)

        if new_plot:  # only add legends if your plotting for the first time
            # Legends
            legend = ax.get_legend()
            if legend:
                pg_legend = plot.addLegend(offset=(1, 1))  # 1px, 1px from top left
                data_items = plot.listDataItems()
                for line, item in zip(ax.get_lines(), data_items):
                    label = line.get_label()
                    if label and not label.startswith('_'):
                        pg_legend.addItem(item, label)
            # set legend location

    def auto_plot_prepare(self, data_to_plot=None):
        """
        Automatically prepares the data based on its shape. This is not always correct but attempts to infer. This
        method can be helpful when writing a custom plotter function. Works for both loading data as well as experiment
        data. Autoplotting will clear all plots before plotting, meaning it is inefficient - providing a display matplotlib
        function or even better, a plotter pyqtgraph function is recommended.

        The prepared data will be in the format:

        .. code-block:: python

            {
                "plots": [
                    {"x": x_data,
                    "y": y_data,
                    "label": name,
                    "xlabel": "Qubit Frequency (GHz)",
                    "ylabel": "a.u."},
                ],
                "images": [
                    {"data": data,
                    "label": name,
                    "xlabel": "X-axis",
                    "ylabel": "Y-axis",
                    "colormap": "viridis"},
                ],
                "columns": [
                    {"data": data,
                    "label": name,
                    "xlabel": "X-axis",
                    "ylabel": "Y-axis"},
                ]
            }

        :param data_to_plot: The data to prepare to be plotted.
        :type data_to_plot: dict

        """

        self.clear_plots()

        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()
        label = self.plot_widget.ci.addLabel(self.file_name, row=0, col=0, colspan=2, size='12pt')
        self.labels.append(label)
        self.plot_widget.nextRow()

        prepared_data = {"plots": [], "images": [], "columns": []}

        if data_to_plot is None:
            data_to_plot = self.data
        f = data_to_plot
        if 'data' in data_to_plot:
            f = data_to_plot['data']

        for name, data in f.items():
            if isinstance(data, int):
                continue

            try:
                data = np.array(data, dtype=np.float64).squeeze()
                data = np.nan_to_num(data, nan=0)
                shape = data.shape
            except Exception as e:
                qDebug("Auto plotter could not handle data: " + str(e))
                qDebug(traceback.print_exc())
                label = self.plot_widget.ci.addLabel("Could not handle plotting", colspan=2, size='12pt')
                self.labels.append(label)
                return

            # Handle 1D data -> 2D Plots
            if len(shape) == 1:
                x_data = None
                if 'x_pts' in f:
                    x_data = list(f['x_pts'])
                    if name == 'x_pts':
                        continue
                    y_data = list(data)
                    if len(x_data) == len(y_data):
                        prepared_data["plots"].append({
                            "x": x_data,
                            "y": y_data,
                            "label": name,
                            "xlabel": "Qubit Frequency (GHz)",
                            "ylabel": "a.u."
                        })
            # Handle 3D data -> Column Plots (you can define a specific format for 3D data)
            elif len(shape) == 2 and shape[1] == 2:
                prepared_data["columns"].append({
                    "data": data,
                    "label": name,
                    "xlabel": "X-axis",
                    "ylabel": "Y-axis"
                })
            # Handle 2D data -> Image Plots (e.g., heatmaps, spectrograms)
            elif len(shape) == 2:
                prepared_data["images"].append({
                    "data": data,
                    "label": name,
                    "xlabel": "X-axis",
                    "ylabel": "Y-axis",
                    "colormap": "viridis"
                })

        # print(prepared_data)
        self.auto_plot_plot(prepared_data)

    def auto_plot_plot(self, prepared_data):
        """
        Auto plots the data using pyqtgraph using a format specified in the auto_plot_prepare() function via the passed
        dictionary.

        :param prepared_data: The prepared data to plot
        :type prepared_data: dict
        """

        # print(prepared_data)

        # Create the plots
        if "plots" in prepared_data:
            for i, plot in enumerate(prepared_data["plots"]):
                p = self.plot_widget.ci.addPlot(title=plot["label"])
                p.addLegend()
                p.plot(plot["x"], plot["y"], pen='b', symbol='o', symbolSize=5, symbolBrush='b')
                p.setLabel('bottom', plot["xlabel"])
                p.setLabel('left', plot["ylabel"])
                p.showGrid(x=True, y=True)

                # Automatically adjust the x and y axis ranges
                x_min, x_max = min(plot["x"]), max(plot["x"])
                y_min, y_max = min(plot["y"]), max(plot["y"])
                # print(x_min, x_max, y_min, y_max)
                p.setRange(xRange=[x_min, x_max], yRange=[y_min, y_max])

                self.plots.append(p)
                self.plot_widget.nextRow()

        if "images" in prepared_data:
            for i, img in enumerate(prepared_data["images"]):
                # Create PlotItem
                p = self.plot_widget.ci.addPlot(title=img["label"])
                p.setLabel('bottom', img["xlabel"])
                p.setLabel('left', img["ylabel"])
                p.showGrid(x=True, y=True)

                # Create ImageItem
                image_item = pg.ImageItem(np.flipud(img["data"].T))  # Plots the same as a matplotlib 'origin="lower"'
                p.addItem(image_item)
                color_map = pg.colormap.get(img["colormap"])  # e.g., 'viridis'
                image_item.setLookupTable(color_map.getLookupTable())

                # Create ColorBarItem
                color_bar = pg.ColorBarItem(values=(image_item.image.min(), image_item.image.max()),
                                            colorMap=color_map)
                color_bar.setImageItem(image_item, insert_in=p)  # Add color bar to the plot

                self.plots.append(p)
                if len(self.plots) % 2 == 0: self.plot_widget.nextRow()

        if "columns" in prepared_data:
            for i, column in enumerate(prepared_data["columns"]):
                x_data = column["data"][:, 0]  # X-values (real part)
                y_data = column["data"][:, 1]  # Y-values (imaginary part)

                # Create PlotItem for IQ plot
                p = self.plot_widget.ci.addPlot(title=column["label"])
                p.setLabel('bottom', column["xlabel"])
                p.setLabel('left', column["ylabel"])
                p.showGrid(x=True, y=True)

                # Plot the scatter plot (IQ plot)
                p.plot(x_data, y_data, pen=None, symbol='o', symbolSize=5, symbolBrush='b')

                self.plots.append(p)
                if len(self.plots) % 2 == 0:  # Move to next row every 2 plots
                    self.plot_widget.nextRow()
        return

    def intermediate_data(self, data, exp_instance):
        """
        Handles intermediate data - meaning data passed from within a set, not at the end. The difference being it
        does not save this intermediate data nor process it. The saving and averaging is done when the set is complete.
        :param data: The intermediate data.
        :type data: dict
        :param exp_instance: The instance of the experiment.
        :type exp_instance: object
        """
        set_num = data["data"]["set_num"]
        inter_data = copy.deepcopy(data)

        if set_num == 0:
            self.data = inter_data

        if self.average_simult_checkbox.isChecked() and self.data is not None and set_num > 0:
            # The code that averages simultaneously. Quite complex since we need to identify which data from the new
            # intermediate data has been seen before, and which is new, and average accordingly.
            inter_data["data"] = self.recursive_average(self.data["data"], inter_data["data"],
                                                        set_num)  # average without changing self.data

        self.plot_data(exp_instance, inter_data)

    def process_data(self, data):
        """
        Processes the dataset in the form of averaging.

        :param data: The data to be processed.
        :type data: dict
        """

        # Outdated averaging code that only averages avgi and avgq. Migrated to a general recursive averager
        # self.data = data
        # # check what set number is being run and average the data
        # if "avgi" in self.data["data"] and "avgq" in self.data["data"]:
        #     set_num = data['data']['set_num']
        #     if set_num == 0:
        #         self.data_cur = data
        #     elif set_num > 0:
        #         avgi = (self.data_cur['data']['avgi'][0][0] * (set_num) + data['data']['avgi'][0][0]) / (set_num + 1)
        #         avgq = (self.data_cur['data']['avgq'][0][0] * (set_num) + data['data']['avgq'][0][0]) / (set_num + 1)
        #         self.data_cur['data']['avgi'][0][0] = avgi
        #         self.data_cur['data']['avgq'][0][0] = avgq
        #     self.data['data']['avgi'][0][0] = self.data_cur['data']['avgi'][0][0]
        #     self.data['data']['avgq'][0][0] = self.data_cur['data']['avgq'][0][0]

        if "data" not in data or "set_num" not in data["data"]:
            raise qWarning("Input data must have 'data' key with 'set_num'.")
            self.data = data

        else:
            set_num = data["data"]["set_num"]

            if self.data is None or set_num == 0:
                self.data = data
            else:
                self.data["data"] = self.recursive_average(self.data["data"], data["data"], set_num)

    def recursive_average(self, current, new, set_num):
        """
        Recursively averages dictionary 'new' data into 'current' using the provided set_num,
        ignoring NaN values during averaging.

        :param current: The current dictionary.
        :type current: dict
        :param new: The newest set's data dictionary.
        :type new: dict
        :param set_num: The set number.
        :type set_num: int
        """

        # Handle scalars (int, float, np.number)
        if isinstance(new, (int, float, np.number)):
            if np.isnan(new):
                return current
            elif current is None or np.isnan(current):
                return new
            else:
                return (current * (set_num) + new) / (set_num + 1)

        # Handle lists
        elif isinstance(new, list):
            if not isinstance(current, list):
                current = [np.nan] * len(new)
            return [
                self.recursive_average(c, n, set_num)
                for c, n in zip(current, new)
            ]

        # Handle NumPy arrays
        elif isinstance(new, np.ndarray):
            if not isinstance(current, np.ndarray):
                current = np.full_like(new, np.nan)
            return np.where(
                np.isnan(new),  # if the new entry is nan
                current,  # then just use the current value
                np.where(  # otherwise, then if new entry is not nan
                    np.isnan(current),  # and the current value is nan
                    new,  # them use the new value
                    (current * (set_num) + new) / (set_num + 1)  # otherwise, both are not nan, and average
                )
            )

        # Handle dictionaries (recurse through keys)
        elif isinstance(new, dict):
            return {
                k: (v if k == "set_num" else self.recursive_average(current.get(k, None), v, set_num))
                for k, v in new.items()
            }

        # Unsupported type
        else:
            qWarning(f"Unsupported data type: {type(new)}")

    def predict_runtime(self, config):
        """
        Predicts the runtime upon a config change or load if a classmethod estimate_runtime is given for the experiment.
        """
        # Get runtime prediction if method is implemented
        if self.experiment_obj.experiment_runtime_estimator is not None:
            flattened_config = config.copy()

            time_delta = self.experiment_obj.experiment_runtime_estimator(flattened_config)
            self.update_runtime_estimation(time_delta, 0)

    def update_runtime_estimation(self, time_delta, set_num):
        """
        Updates the estimated runtime and endtime.

        :param time_delta: The time delta in seconds of a single set.
        :type time_delta: float
        :param set_num: The set number.
        :type set_num: int
        """
        total_sets = 1
        if "sets" in self.experiment_config_panel.config:
            total_sets = self.experiment_config_panel.config["sets"]
        sets_left = total_sets - set_num

        runtime_estimate = time_delta * total_sets
        runtime_string = Helpers.format_time_duration_pretty(runtime_estimate)

        leftover_runtime_estimate = (time_delta * sets_left)
        endtime_string = Helpers.format_date_time_pretty(leftover_runtime_estimate)
        # Note: this endtime is calculated from the time this function was called, meaning after a minute, its no longer
        # correct. Not sure if it is worth it to have it update constantly. It will update the next time this func called.

        self.runtime_label.setText("Estimated Runtime: " + runtime_string)
        self.endtime_label.setText("End: " + endtime_string)

    def update_data(self, data, exp_instance):
        """
        Is the slot for the emission of data from the experiment thread. Calls the methods to process and plot the data.

        :param data: The data to be processed.
        :type data: dict
        :param exp_instance: The instance of the experiment.
        :type exp_instance: object
        """

        self.exp_instance = exp_instance

        self.process_data(data)
        self.plot_data(exp_instance)
        self.save_data()

    def replot_data(self):
        """
        Function called when RePlot button pressed. As of now, it simply calls the plot_data() function.
        """
        self.clear_plots()
        if hasattr(self, "exp_instance"):
            self.plot_data(self.exp_instance)
        else:
            self.plot_data()

    def export_data(self):
        """
        Is the function called when the export button clicked. Prepares file naming and saves data.
        """
        self.prepare_file_naming()
        self.save_data(custom_path=True)

        self.export_data_button.setText('Done!')
        QTimer.singleShot(3000, lambda: self.export_data_button.setText('Export'))  # called after 3 seconds

    def prepare_file_naming(self):
        """
        Prepares naming conventions by creating folder and file names with experiment type and timestamps.
        """

        # Setting up variables necessary for saving data files
        date_time_now = datetime.datetime.now()
        date_time_string = date_time_now.strftime("%Y_%m_%d_%H_%M_%S")
        date_string = date_time_now.strftime("%Y_%m_%d")

        if not self.is_experiment and self.dataset_file is not None:
            path_obj = Path(self.dataset_file)
            self.folder_name = "data" + "_" + date_string
            self.file_name = path_obj.stem
        elif self.is_experiment:
            self.folder_name = self.tab_name + "_" + date_string
            self.file_name = self.tab_name + "_" + date_time_string

    def save_data(self, custom_path=False):
        """
        Performs the saving of an experiment's data via 3 files:
            * h5 : Saves data by force dumping it into an h5 format with the config stored as metadata
            * json : Saves the config into a json file
            * PNG : Saves the data as a PNG image
        """

        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()

        # Saving datasets
        if not self.is_experiment:
            folder_path = Helpers.open_file_dialog("Select Folder to Save Dataset", "",
                                                   "save_dataset", self, file=False)

            if folder_path:
                folder_path = Path(os.path.join(folder_path, self.folder_name))
                if not folder_path.is_dir():
                    folder_path.mkdir(parents=True, exist_ok=True)

                if folder_path:
                    try:
                        shutil.copy2(self.dataset_file, folder_path)
                        pixmap = self.plot_widget.grab()
                        file_path = os.path.join(folder_path, self.file_name + ".png")
                        pixmap.save(file_path)
                        qInfo("Saved dataset to " + str(folder_path))
                    except Exception as e:
                        qCritical(f"Failed to save the dataset to {file_path}: {str(e)}")
                        qCritical(traceback.print_exc())
                        QMessageBox.critical(self, "Error", f"Failed to save dataset.")

        # Saving experiments
        elif self.is_experiment:
            folder_path = self.workspace
            if custom_path:
                folder_path = Helpers.open_file_dialog("Select Folder to Save Dataset", "",
                                                       "save_dataset", self, file=False)
            else:
                if not Path(os.path.join(folder_path, 'Data')).is_dir():
                    os.mkdir(os.path.join(folder_path, 'Data'))
                folder_path = os.path.join(folder_path, 'Data')

            date_time_now = datetime.datetime.now()
            date_time_string = date_time_now.strftime("%Y_%m_%d_%H_%M_%S")
            data_filename = os.path.join(folder_path, self.tab_name, self.folder_name, self.file_name + '.h5')
            config_filename = os.path.join(folder_path, self.tab_name, self.folder_name, self.file_name + '.json')
            image_filename = os.path.join(folder_path, self.tab_name, self.folder_name, self.file_name + '.png')

            # Make directories if they don't already exist
            if not Path(os.path.join(folder_path, self.tab_name)).is_dir():
                os.mkdir(os.path.join(folder_path, self.tab_name))
            if not Path(os.path.join(folder_path, self.tab_name, self.folder_name)).is_dir():
                os.mkdir(os.path.join(folder_path, self.tab_name, self.folder_name))

            # Save dataset
            if self.experiment_obj.experiment_exporter is not None:
                try:
                    self.experiment_obj.experiment_exporter(data_filename, self.data, self.last_run_experiment_config)
                except RuntimeError as e:
                    qCritical(f"Failed to save the dataset to {data_filename}: {str(e)}")
            else:
                self.backup_exporter(data_filename)

            # Save config
            try:
                with open(config_filename, "w") as json_file:
                    json.dump(
                        self.last_run_experiment_config,  # Saves the last run experiment config
                        json_file,
                        indent=4,
                        default=lambda x: (
                            int(x) if isinstance(x, np.integer) else
                            float(x) if isinstance(x, np.floating) else
                            bool(x) if isinstance(x, np.bool_) else
                            str(x)
                        )
                    )

            except Exception as e:
                qCritical(f"Failed to save the configuration to {config_filename}: {str(e)}")

            # Save image
            try:
                pixmap = self.plot_widget.grab()
                pixmap.save(image_filename, "PNG")
            except Exception as e:
                qCritical(f"Failed to save the plot image to {image_filename}: {str(e)}")

            qDebug("Data export attempted at " + date_time_string +
                   " to: " + folder_path + "/" + self.tab_name + "/" + self.folder_name)

    def backup_exporter(self, data_filename):
        """
        In the case where an exporter cannot be found (which shouldn't happen as the ExperimentClass provides a
        default data exporter, this backup function will be used. It is the same as the one given in the
        ExperimentClass.
        """
        data_file = h5py.File(data_filename, 'w')  # Create file if does not exist, truncate mode if exists

        dictionary = self.data
        if "data" in self.data:
            dictionary = self.data["data"]

        for key, datum in dictionary.items():

            if isinstance(datum, dict):
                data_file.attrs[key] = json.dumps(datum, cls=Helpers.NpEncoder)
            else:
                # Convert to NumPy array and handle jagged arrays
                datum = [np.array(sub_arr, dtype=np.float64) for sub_arr in datum] \
                    if isinstance(datum, list) else np.array(datum, dtype=np.float64)

                # If datum is still a list of arrays, pad it to make a rectangular array
                if isinstance(datum, list):
                    max_len = max(len(arr) for arr in datum)
                    datum = np.array(
                        [np.pad(arr, (0, max_len - len(arr)), constant_values=np.nan) for arr in datum])

                try:
                    data_file.create_dataset(key, shape=datum.shape,
                                             maxshape=tuple([None] * len(datum.shape)),
                                             dtype=str(datum.astype(np.float64).dtype))
                except RuntimeError as e:
                    del data_file[key]
                    raise e

                data_file[key][...] = datum

        data_file.close()