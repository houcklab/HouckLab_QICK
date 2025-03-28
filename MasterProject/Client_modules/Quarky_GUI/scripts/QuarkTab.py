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
import h5py
from pathlib import Path
import datetime
import shutil

import numpy as np
from PyQt5.QtGui import QKeySequence, QCursor
from PyQt5.QtCore import (
    Qt, QSize, qCritical, qInfo, qDebug, QRect, QTimer,
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

    **Important Attributes:**

        * experiment_obj (Experiment Module): The experiment module object that was passed.
        * config (dict): The configuration of the QQuarkTab experiment/dataset.
        * data (dict): The data of the QQuarkTab experiment/dataset.
        * plots (pyqtgraph.PlotWidget[]): Array of the pyqtgraph plots of the data.
        * plot_widget (pyqtgraph.GraphicsLayoutWidget): The graphics layout of the plotting area
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

        ### Plot Utilities Bar
        self.plot_utilities_container = QWidget()
        self.plot_utilities_container.setMaximumHeight(35)
        self.plot_utilities = QHBoxLayout(self.plot_utilities_container)
        self.plot_utilities.setContentsMargins(0, 0, 0, 0)
        self.plot_utilities.setSpacing(3)
        self.plot_utilities.setObjectName("plot_utilities")
        self.reload_experiment_button = Helpers.create_button("Reload", "reload_experiment_button", False, self.plot_utilities_container)
        self.snip_plot_button = Helpers.create_button("Snip", "snip_plot_button", True, self.plot_utilities_container)
        self.export_data_button = Helpers.create_button("Export", "export_data_button", False, self.plot_utilities_container)
        self.output_dir_button = Helpers.create_button("Output Dir", "output_dir_button", False, self.plot_utilities_container)
        self.plot_method_combo = QComboBox(self.plot_utilities_container)
        self.plot_method_combo.setFixedWidth(120)
        self.plot_method_combo.setObjectName("plot_method_combo")
        self.coord_label = QLabel("X: _____ Y: _____ \n press d to delete a plot")  # coordinate of the mouse over the current plot
        self.coord_label.setAlignment(Qt.AlignRight)
        self.coord_label.setStyleSheet("font-size: 10px;")
        self.coord_label.setObjectName("coord_label")

        spacerItem = QSpacerItem(0, 30, QSizePolicy.Expanding, QSizePolicy.Fixed)  # spacer
        self.plot_utilities.addWidget(self.reload_experiment_button)
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
        self.reload_experiment_button.clicked.connect(self.reload_experiment)

        self.remove_plot_shortcut = QShortcut(QKeySequence("D"), self)
        self.remove_plot_shortcut.activated.connect(self.remove_plot)

        # Create the default export output_dir for autosaving if of type experiment
        if self.is_experiment:
            self.reload_experiment_button.setEnabled(True)
            self.output_dir_button.setEnabled(True)
            self.output_dir = os.path.join(os.path.abspath(""), "data")
            qInfo("Default output_dir for " + self.tab_name + " is at: " + str(self.output_dir))
            if not Path(self.output_dir).is_dir():
                os.mkdir(self.output_dir)
        if self.tab_name != "None":
            self.export_data_button.setEnabled(True)

    def setup_plotter_options(self):
        """
        This method sets up the plotting options based on the current experiment. If the experiment gave a plotter
        function, it is automatically set as the default method. Otherwise, the current methods available only include
        'Auto'.
        """

        self.plot_method_combo.addItems(["Plot: Auto"])
        if self.is_experiment and self.experiment_obj is not None:
            if self.experiment_obj.experiment_plotter is not None:
                self.plot_method_combo.addItems(["Plot: " + self.tab_name])
                self.plot_method_combo.setCurrentText("Plot: " + self.tab_name)

    def load_dataset_file(self, dataset_file):
        """
        Takes the dataset file and loads the dict, before calling the plotter.

        :param dataset_file: The path to the dataset file.
        :type dataset_file: str
        """

        self.data = Helpers.h5_to_dict(dataset_file)
        print(self.data)
        metadata = Helpers.extract_metadata(dataset_file)
        if "config" in metadata:
            qInfo("Config in h5 metadata found")
            self.config = json.loads(metadata["config"])
            print(self.config)
        else:
            qDebug("No config in metadata found")
        self.plot_data()

    def clear_plots(self):
        """
        Clears the plots.
        """

        self.plot_widget.ci.clear()
        self.plots = []

    def reload_experiment(self):
        """
        Reloads the current experiment via the experiment_path given. This allows a user to change the experiment code
        or even the plotter without having to exit the GUI, close any tabs, or import the experiment from scratch.
        """

        if self.experiment_obj is not None:
            self.experiment_obj.extract_experiment_attributes()
            qDebug("Reloaded Experiment: experiment attributes extracted.")

            self.reload_experiment_button.setText('Reloaded!')
            QTimer.singleShot(3000, lambda: self.reload_experiment_button.setText('Reload'))

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
                self.coord_label.setText(f"X: {x:.4f} Y: {y:.4f} \n press d to delete a plot")
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

    def plot_data(self):
        """
        Plots the data of the QQuarkTab experiment/dataset using prepared data that is prepared by
        the specified plotting method of the dropdown menu.
        """

        self.clear_plots()
        self.plots = []

        plotting_method = self.plot_method_combo.currentText()[6:] # Get the Plotting Method
        if plotting_method == "Auto": # Use auto preparation
            self.auto_plot_prepare()
        elif plotting_method == self.tab_name: # Use the experiment's preparation
            self.experiment_obj.experiment_plotter(self.plot_widget, self.plots, self.data)

    def auto_plot_prepare(self):
        """
        Automatically prepares the data based on its shape. This is not always correct but attempts to infer. This
        method can be helpful when writing a custom plotter function. Works for both loading data as well as experiment
        data.

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

        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()
        self.plot_widget.addLabel(self.file_name, row=0, col=0, colspan=2, size='12pt')
        self.plot_widget.nextRow()

        prepared_data = {"plots": [], "images": [], "columns": []}

        f = self.data
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
                qDebug("Auto plotter could not handle data")
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

        # Create the plots
        if "plots" in prepared_data:
            for i, plot in enumerate(prepared_data["plots"]):
                p = self.plot_widget.addPlot(title=plot["label"])
                p.addLegend()
                p.plot(plot["x"], plot["y"], pen='b', symbol='o', symbolSize=5, symbolBrush='b')
                p.setLabel('bottom', plot["xlabel"])
                p.setLabel('left', plot["ylabel"])
                p.showGrid(x=True, y=True)

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
                image_item = pg.ImageItem(img["data"].T)
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

    def process_data(self, data):
        """
        Processes the dataset usually in the form of averaging.

        :param data: The data to be processed.
        :type data: dict
        """

        self.data = data

        # check what set number is being run and average the data
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

    def update_data(self, data):
        """
        Is the slot for the emission of data from the experiment thread. Calls the methods to process and plot the data.

        :param data: The data to be processed.
        :type data: dict
        """

        self.process_data(data)
        self.plot_data()
        self.save_data()

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
            data_file = h5py.File(data_filename, 'w')  # Create file if does not exist, truncate mode if exists
            if self.experiment_obj.experiment_exporter is not None:
                try:
                    self.experiment_obj.experiment_exporter(data_file, self.data, self.config)
                except RuntimeError as e:
                    qCritical(f"Failed to save the dataset to {data_filename}: {str(e)}")
            else :
                self.backup_exporter(data_file)
            data_file.close()

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

    def backup_exporter(self, data_file):
        """
        In the case where an exporter cannot be found (which shouldn't happen as the ExperimentClass provides a
        default data exporter, this backup function will be used. It is the same as the one given in the
        ExperimentClass.
        """

        if isinstance(self.data, dict) and 'data' in self.data and isinstance(self.data['data'], dict):
            for key, datum in self.data['data'].items():

                if isinstance(datum, dict):
                    # somehow do something here
                    print("cannot store dicts yet")
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
                        qCritical(f"Failed to save the dataset to {data_filename}: {str(e)}")
                        del data_file[key]
                    data_file[key][...] = datum