"""
============
QuarkyTab.py
============
The custom QQuarkTab class for the central tabs module of the main application.

Each QQuarkTab is either an experiment tab or a data tab that stores its own object attributes, configuration,
data, and plotting. Arguable is more important for functionality than the main Quarky.py file.
"""

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
import numpy as np
from PyQt5.QtGui import QKeySequence, QCursor, QImage, QPixmap
from PyQt5.QtCore import (
    Qt, QSize, qCritical, qInfo, qDebug, QRect, QTimer,
    pyqtSignal,
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
)
import pyqtgraph as pg
from MasterProject.Client_modules.Init.initialize import BaseConfig
from scripts.ExperimentObject import ExperimentObject
import scripts.Helpers as Helpers

class QQuarkTab(QWidget):
    """
    The class for QQuarkTabs that make up the central tabular module that hold specific experiments or datasets.

    Plotting functionality makes up the bulk of the code. If a "plotter" classmethod is written for the class (recommended)
    then the GUI will extract it to be used to plot - as well as stored in all the custom plot methods to be used on any dataset
    or experiment. Otherwise, the GUI will call the display function of a instance if provided, and intercept plt.plot calls.
    These display instance methods cannot be stored as custom plot methods.

    **Important Attributes:**

        * experiment_obj (Experiment Module): The experiment module object that was passed.
        * config (dict): The full configuration of the QQuarkTab experiment/dataset.
        * data (dict): The data of the QQuarkTab experiment/dataset.
        * plots (pyqtgraph.PlotWidget[]): Array of the pyqtgraph plots of the data.
        * plot_widget (pyqtgraph.GraphicsLayoutWidget): The graphics layout of the plotting area
        * custom_plot_methods (dict): A dictionary of the added custom plotting methods.
    """

    custom_plot_methods = {}
    """
    custom_plot_methods (dict): A dictionary of the added custom plotting methods.
    """

    updated_tab = pyqtSignal()  # argument is ip_address
    """
    The Signal sent to the main application (Quarky.py) that tells the program the current tab was updated.
    """

    def __init__(self, experiment_path=None, tab_name=None, is_experiment=None, dataset_file=None):
        """
        Initializes an instance of a QQuarkTab widget that will either be of type experiment based on the parameters
        passed.
            * An experiment will pass: [experiment_path, tab_name, is_experiment=True].
            * A dataset will pass: [tab_name, is_experiment=False, dataset_file]

        :param experiment_obj: The experiment module object extracted from an experiment file.
        :type experiment_obj: Experiment Module
        :param tab_name: The name of the tab widget.
        :type tab_name: str
        :param is_experiment: Whether the tab corresponds to an experiment or dataset.
        :type is_experiment: bool
        :param dataset_file: The path to the dataset file.
        :type dataset_file: str
        """

        super().__init__()

        ### Experiment Variables
        self.config = {"Experiment Config": {}, "Base Config": BaseConfig} # default config found in initialize.py
        self.tab_name = str(tab_name)
        self.experiment_obj = None if experiment_path is None \
            else ExperimentObject(self, self.tab_name, experiment_path)
        self.is_experiment = is_experiment
        self.dataset_file = dataset_file
        self.data = None
        self.plots = []
        self.output_dir = None

        ### Setting up the Tab
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        ### Plotter within Tab
        self.plot_layout = QVBoxLayout(self)
        self.plot_layout.setContentsMargins(5, 5, 5, 0)
        self.plot_layout.setSpacing(0)
        self.plot_layout.setObjectName("plot_layout")

        ### Experiment Information Bar
        self.experiment_infobar_container = QWidget()
        self.experiment_infobar_container.setMaximumHeight(15)
        self.experiment_infobar = QHBoxLayout(self.experiment_infobar_container)
        self.experiment_infobar.setContentsMargins(0, 0, 0, 0)
        self.experiment_infobar.setSpacing(3)
        self.experiment_infobar.setObjectName("experiment_infobar")

        self.runtime_label = QLabel("Estimated Runtime: ---")  # estimated experiment time
        self.runtime_label.setStyleSheet("font-size: 11px;")
        self.endtime_label = QLabel("End: ---")  # estimated experiment time
        self.endtime_label.setStyleSheet("font-size: 11px;")
        self.hardware_label = QLabel("Hardware Requirement: [Proxy, QickConfig]")
        if self.experiment_obj is not None and self.experiment_obj.experiment_hardware_req is not None:
            hardware_str = "[" + (", ".join(cls.__name__ for cls in self.experiment_obj.experiment_hardware_req)) + "]"
            self.hardware_label.setText("Hardware Requirement: " + hardware_str)
        self.hardware_label.setAlignment(Qt.AlignRight)
        self.hardware_label.setStyleSheet("font-size: 11px;")
        # TODO: Runtime Functions: calculate estimation, at updateprogress, calc runtime remaining, log actual time used

        self.experiment_infobar.addWidget(self.runtime_label)
        self.experiment_infobar.addWidget(self.endtime_label)
        self.experiment_infobar.addWidget(self.hardware_label)
        self.plot_layout.addWidget(self.experiment_infobar_container)

        ### Plot Utilities Bar
        self.plot_utilities_container = QWidget()
        self.plot_utilities_container.setMaximumHeight(35)
        self.plot_utilities = QHBoxLayout(self.plot_utilities_container)
        self.plot_utilities.setContentsMargins(0, 0, 0, 0)
        self.plot_utilities.setSpacing(3)
        self.plot_utilities.setObjectName("plot_utilities")

        self.reExtract_experiment_button = Helpers.create_button("ReExtract", "reExtract_experiment_button", False, self.plot_utilities_container)
        self.replot_button = Helpers.create_button("RePlot", "replot_button", False, self.plot_utilities_container)
        self.snip_plot_button = Helpers.create_button("Snip", "snip_plot_button", True, self.plot_utilities_container)
        self.export_data_button = Helpers.create_button("Export", "export_data_button", False, self.plot_utilities_container)
        self.output_dir_button = Helpers.create_button("Save To...", "output_dir_button", False, self.plot_utilities_container)
        self.plot_method_combo = QComboBox(self.plot_utilities_container)
        self.plot_method_combo.setFixedWidth(130)
        self.plot_method_combo.setObjectName("plot_method_combo")
        self.coord_label = QLabel("X: _____ Y: _____ \n hover + \'d\' to delete")  # coordinate of the mouse over the current plot
        self.coord_label.setAlignment(Qt.AlignRight)
        self.coord_label.setStyleSheet("font-size: 10px;")
        self.coord_label.setObjectName("coord_label")

        spacerItem = QSpacerItem(0, 30, QSizePolicy.Expanding, QSizePolicy.Fixed)  # spacer
        self.plot_utilities.addWidget(self.reExtract_experiment_button)
        self.plot_utilities.addWidget(self.replot_button)
        self.plot_utilities.addWidget(self.snip_plot_button)
        self.plot_utilities.addWidget(self.export_data_button)
        self.plot_utilities.addWidget(self.output_dir_button)
        self.plot_utilities.addWidget(self.plot_method_combo)
        self.plot_utilities.addItem(spacerItem)
        self.plot_utilities.addWidget(self.coord_label)
        self.plot_layout.addWidget(self.plot_utilities_container)

        # The actual plot itself (lots of styling attributes
        self.plot_widget = pg.GraphicsLayoutWidget(self)
        self.plot_widget.addLabel("Nothing to plot.", row=0, col=0, colspan=2, size='12pt')
        self.plot_widget.setBackground("w")
        self.plot_widget.ci.setSpacing(2)  # Reduce spacing
        self.plot_widget.ci.setContentsMargins(3, 3, 3, 3)  # Adjust margins of plots
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_widget.setMinimumSize(QSize(375, 0))
        self.plot_widget.setObjectName("plot_widget")

        self.plot_layout.addWidget(self.plot_widget)
        self.plot_layout.setStretch(0, 1)
        self.plot_layout.setStretch(1, 10)

        self.setLayout(self.plot_layout)
        self.setup_plotter_options()

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
        self.plot_widget.scene().sigMouseMoved.connect(self.update_coordinates) # coordinates viewer
        self.snip_plot_button.clicked.connect(self.capture_plot_to_clipboard)
        self.export_data_button.clicked.connect(self.export_data)
        self.output_dir_button.clicked.connect(self.change_output_dir)
        self.reExtract_experiment_button.clicked.connect(self.reExtract_experiment)
        self.replot_button.clicked.connect(self.replot_data)
        self.plot_method_combo.currentIndexChanged.connect(self.handle_plot_combo_selection)

        self.remove_plot_shortcut = QShortcut(QKeySequence("D"), self)
        self.remove_plot_shortcut.activated.connect(self.remove_plot)

        # Create the default export output_dir for autosaving if of type experiment
        if self.is_experiment:
            self.reExtract_experiment_button.setEnabled(True)
            self.output_dir_button.setEnabled(True)
            self.output_dir = os.path.join(os.path.abspath(""), "data")
            qInfo("Default output_dir for " + self.tab_name + " is at: " + str(self.output_dir))
            if not Path(self.output_dir).is_dir():
                os.mkdir(self.output_dir)

            # add custom plotter to options
            if self.is_experiment and self.experiment_obj is not None:
                if self.experiment_obj.experiment_plotter is not None:
                    QQuarkTab.custom_plot_methods[self.tab_name] = self.experiment_obj.experiment_plotter

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

        for key in QQuarkTab.custom_plot_methods.keys():
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
            self.plot_method_combo.blockSignals(True) # Prevent adding a new combo from calling it again in a loop

            options = QFileDialog.Options()
            file, _ = QFileDialog.getOpenFileName(self, "Open Python File", "..\\",
                                                  "Python Files (*.py)", options=options)
            if file:
                path = str(Path(file))
                qInfo("Retrieving experiment plotter from: " + path)
                experiment_name = os.path.splitext(os.path.basename(path))[0]
                temp_experiment = ExperimentObject(self, experiment_name, path)
                if temp_experiment.experiment_plotter is not None:
                    self.plot_method_combo.insertItem(0, experiment_name)
                    self.plot_method_combo.setCurrentText(experiment_name)
                    QQuarkTab.custom_plot_methods[experiment_name] = temp_experiment.experiment_plotter
                    qInfo("Added " + experiment_name + " plotter.")
                    self.replot_data()
                else:
                    self.plot_method_combo.setCurrentText("None")
                    qDebug("No plotter function found within " + experiment_name)

            self.plot_method_combo.blockSignals(False) # re_enable plotting
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
        self.config["Base Config"] = {}
        if "config" in self.data:
            qInfo("Config in h5 metadata found")
            temp_config = self.data["config"]

            if "Experiment Config" in temp_config:
                self.config = temp_config
            else:
                self.config["Experiment Config"] = temp_config

            self.data.pop("config")
        else:
            qDebug("No config in metadata found")

        # print(self.data)

        self.plot_data()

    def clear_plots(self):
        """
        Clears the plots.
        """

        self.plot_widget.ci.clear()
        self.plots = []

    def reExtract_experiment(self):
        """
        ReExtracts the current experiment via the experiment_path given. This allows a user to change the experiment code
        or even the plotter without having to exit the GUI, close any tabs, or import the experiment from scratch.
        """

        if self.experiment_obj is not None:
            self.experiment_obj.extract_experiment_attributes()
            if self.experiment_obj.experiment_plotter is not None:
                self.custom_plot_methods[self.tab_name] = self.experiment_obj.experiment_plotter

            if self.experiment_obj is not None and self.experiment_obj.experiment_hardware_req is not None:
                hardware_str = "[" + (
                    ", ".join(cls.__name__ for cls in self.experiment_obj.experiment_hardware_req)) + "]"
                self.hardware_label.setText("Hardware Requirement: " + hardware_str)
            qDebug("ReExtracted Experiment: experiment attributes extracted.")
            self.updated_tab.emit()

            self.reExtract_experiment_button.setText('Done!')
            QTimer.singleShot(3000, lambda: self.reExtract_experiment_button.setText('ReExtract'))

    def update_coordinates(self, pos):
        """
        Updates the coordinates label to reflect the cursor's location on a plot's axis.

        :param pos: The coordinates of the cursor
        :type pos: tuple
        """

        # find the active plot
        for plot in self.plots:
            vb = plot.vb  # ViewBox of each plot
            if plot.sceneBoundingRect().contains(pos):
                self.plot_widget.setCursor(Qt.CrossCursor) # make cursor cross-hairs
                mouse_point = vb.mapSceneToView(pos) # translate location to axis coordinates
                x, y = mouse_point.x(), mouse_point.y()
                self.coord_label.setText(f"X: {x:.4f} Y: {y:.4f} \n hover + d to delete")
                break

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
        pos = self.plot_widget.mapFromGlobal(global_pos) # maps it to its position relative to the plotting space

        # Loops through the list of plots
        for plot in self.plots:
            vb = plot.vb  # ViewBox of each plot
            if plot.sceneBoundingRect().contains(pos):
                self.plots.remove(plot)
                self.plot_widget.removeItem(plot)
                self.plot_widget.update()

    def plot_data(self, exp_instance=None):
        """
        Plots the data of the QQuarkTab experiment/dataset using prepared data that is prepared by
        the specified plotting method of the dropdown menu.

        :param exp_instance: The instance of the experiment.
        :type exp_instance: object
        """
        if len(self.plots) == 0:
            self.clear_plots()

        plotting_method = self.plot_method_combo.currentText() # Get the Plotting Method
        try:
            if plotting_method == "None": # No longer using auto preparation
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
                            exp_instance.display(self.data, plotDisp=True)
                        else:
                            self.auto_plot_prepare()
                    else:
                        self.auto_plot_prepare()
            elif plotting_method in QQuarkTab.custom_plot_methods:
                QQuarkTab.custom_plot_methods[plotting_method](self.plot_widget, self.plots, self.data)
        except Exception as e:
            qCritical("Failed to plot using method [" + plotting_method + "]: " + str(e))
            qCritical(traceback.print_exc())

    def handle_pltplot(self, *args, **kwargs):
        """
        Handles a matplotlib by extracting its data and plotting it using pyqtgraph.
        """
        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()

        if len(self.plots) == 0:
            self.plot_widget.addLabel(self.file_name, row=0, col=0, colspan=2, size='12pt')

        figures = list(map(plt.figure, plt.get_fignums()))
        self.curr_plot = 0
        for i, fig in enumerate(figures):
            for ax in fig.get_axes():
                if i % 2 == 0:
                    self.plot_widget.nextRow()
                self.extract_and_plot_pyqtgraph(i, ax)
        return

    def extract_and_plot_pyqtgraph(self, i, ax):
        """
        Convert a matplotlib Axes to a PyQtGraph plot.

        :param i: The index of the figure.
        :type i: int
        :param ax: Matplotlib axis containing plot data to convert.
        :type ax: matplotlib.axes.Axes
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

        if len(ax.get_lines()) == 0 and len(ax.get_images()) == 0: # Skip plotting if no data in axes
            return

        new_plot = True
        plot_item_num = 0
        if len(self.plots) > self.curr_plot: # If plots already exist, then don't create new plots, simply update the existing
            plot = self.plots[self.curr_plot]
            plot_data_items = [item for item in plot.items if isinstance(item, pg.PlotDataItem) or isinstance(item, pg.ImageItem)]
            new_plot = False
        else:
            plot = self.plot_widget.addPlot() # Otherwise, create new plots
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
                plot_data_items[plot_item_num].setImage(data.T) # Transpose assumes data was plotted with 'origin="lower"'
                plot_item_num += 1
            else:
                plot.setLabel('left', ax.get_ylabel())
                plot.setLabel('bottom', ax.get_xlabel())

                img_item = pg.ImageItem(image=data.T) # Transpose assumes data was plotted with 'origin="lower"'
                plot.addItem(img_item)
                color_map = pg.colormap.get("inferno")  # e.g., 'viridis'
                img_item.setLookupTable(color_map.getLookupTable())
                img_item.setRect(pg.QtCore.QRectF(extent[0], extent[2], extent[1] - extent[0], extent[3] - extent[2]))

                # Create ColorBarItem
                color_bar = pg.ColorBarItem(values=(img_item.image.min(), img_item.image.max()), colorMap=color_map)
                color_bar.setImageItem(img_item, insert_in=plot)  # Add color bar to the plot

        if new_plot: # only add legends if your plotting for the first time
            # Legends
            legend = ax.get_legend()
            if legend:
                pg_legend = plot.addLegend()
                data_items = plot.listDataItems()
                for line, item in zip(ax.get_lines(), data_items):
                    label = line.get_label()
                    if label and not label.startswith('_'):
                        pg_legend.addItem(item, label)

    def auto_plot_prepare(self):
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
                    "colormap": "inferno"},
                ],
                "columns": [
                    {"data": data,
                    "label": name,
                    "xlabel": "X-axis",
                    "ylabel": "Y-axis"},
                ]
            }

        """

        self.clear_plots()

        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()
        self.plot_widget.addLabel(self.file_name, row=0, col=0, colspan=2, size='12pt')
        self.plot_widget.nextRow()

        prepared_data = {"plots": [], "images": [], "columns": []}

        f = self.data
        # print(self.data)
        if 'data' in self.data:
            f = self.data['data']

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
                self.plot_widget.addLabel("Could not handle plotting", colspan=2, size='12pt')
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
                    "colormap": "inferno"
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
                p = self.plot_widget.addPlot(title=plot["label"])
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
                p = self.plot_widget.addPlot(title=img["label"])
                p.setLabel('bottom', img["xlabel"])
                p.setLabel('left', img["ylabel"])
                p.showGrid(x=True, y=True)

                # Create ImageItem
                image_item = pg.ImageItem(np.flipud(img["data"].T)) # Plots the same as a matplotlib 'origin="lower"'
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
                p = self.plot_widget.addPlot(title=column["label"])
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
        does not save this intermediate data.
        :param data: The intermediate data.
        :type data: dict
        :param exp_instance: The instance of the experiment.
        :type exp_instance: object
        """

        self.process_data(data)
        self.plot_data(exp_instance)

    def process_data(self, data):
        """
        Processes the dataset usually in the form of averaging.
        TODO

        :param data: The data to be processed.
        :type data: dict
        """

        self.data = data
        # check what set number is being run and average the data
        if "avgi" in self.data["data"] and "avgq" in self.data["data"]:
            set_num = data['data']['set_num']
            if set_num == 0:
                self.data_cur = data
            elif set_num > 0:
                avgi = (self.data_cur['data']['avgi'][0][0] * (set_num) + data['data']['avgi'][0][0]) / (set_num + 1)
                avgq = (self.data_cur['data']['avgq'][0][0] * (set_num) + data['data']['avgq'][0][0]) / (set_num + 1)
                self.data_cur['data']['avgi'][0][0] = avgi
                self.data_cur['data']['avgq'][0][0] = avgq
            self.data['data']['avgi'][0][0] = self.data_cur['data']['avgi'][0][0]
            self.data['data']['avgq'][0][0] = self.data_cur['data']['avgq'][0][0]

    def update_runtime_estimation(self, time_delta, set_num):
        """
        Updates the estimated runtime and endtime.

        :param time_delta: The time delta in seconds of a single set.
        :type time_delta: float
        :param set_num: The set number.
        :type set_num: int
        """
        total_sets = 1
        if "sets" in self.config["Experiment Config"]:
            total_sets = self.config["Experiment Config"]["sets"]
        sets_left = total_sets - set_num

        runtime_estimate = time_delta * total_sets
        runtime_string = Helpers.format_time_duration_pretty(runtime_estimate)

        leftover_runtime_estimate = (time_delta * sets_left)
        endtime_string = Helpers.format_date_time_pretty(leftover_runtime_estimate)

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

        self.process_data(data)
        self.plot_data(exp_instance)
        self.save_data()

    def replot_data(self):
        """
        Function called when RePlot button pressed. As of now, it simply calls the plot_data() function.
        """
        self.clear_plots()
        self.plot_data()

    def export_data(self):
        """
        Is the function called when the export button clicked. Prepares file naming and saves data.
        """

        self.prepare_file_naming()
        self.save_data()

        self.export_data_button.setText('Done!')
        QTimer.singleShot(3000, lambda: self.export_data_button.setText('Export')) # called after 3 seconds

    def change_output_dir(self):
        """
        Changes the output directory that data is autosaved to via a file dialog.
        """

        self.output_dir = QFileDialog.getExistingDirectory(self, "Select Folder for Autosave", self.output_dir)
        qInfo("Output directory for experiment data changed to: " + self.output_dir)

        self.output_dir_button.setText('Changed!')
        QTimer.singleShot(3000, lambda: self.output_dir_button.setText('Output Dir'))

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

    def save_data(self):
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
            folder_path = QFileDialog.getExistingDirectory(self, "Select Folder to Save Dataset")
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
            date_time_now = datetime.datetime.now()
            date_time_string = date_time_now.strftime("%Y_%m_%d_%H_%M_%S")
            data_filename = os.path.join(self.output_dir, self.tab_name, self.folder_name, self.file_name + '.h5')
            config_filename = os.path.join(self.output_dir, self.tab_name, self.folder_name, self.file_name + '.json')
            image_filename = os.path.join(self.output_dir, self.tab_name, self.folder_name, self.file_name + '.png')

            # Make directories if they don't already exist
            if not Path(os.path.join(self.output_dir, self.tab_name)).is_dir():
                os.mkdir(os.path.join(self.output_dir, self.tab_name))
            if not Path(os.path.join(self.output_dir, self.tab_name, self.folder_name)).is_dir():
                os.mkdir(os.path.join(self.output_dir, self.tab_name, self.folder_name))

            # Save dataset
            if self.experiment_obj.experiment_exporter is not None:
                try:
                    self.experiment_obj.experiment_exporter(data_filename, self.data, self.config)
                except RuntimeError as e:
                    qCritical(f"Failed to save the dataset to {data_filename}: {str(e)}")
            else :
                self.backup_exporter(data_filename)

            # Save config
            try:
                with open(config_filename, "w") as json_file:
                    json.dump(self.config, json_file, indent=4)

            except Exception as e:
                qCritical(f"Failed to save the configuration to {config_filename}: {str(e)}")

            # Save image
            try:
                pixmap = self.plot_widget.grab()
                pixmap.save(image_filename, "PNG")
            except Exception as e:
                qCritical(f"Failed to save the plot image to {image_filename}: {str(e)}")

            qDebug("Data export attempted at " + date_time_string +
                  " to: " + self.output_dir + "/" + self.tab_name + "/" + self.folder_name)

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
                data_file.attrs[key] = json.dumps(datum, cls=NpEncoder)
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