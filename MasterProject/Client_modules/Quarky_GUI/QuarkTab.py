import sys, os, inspect
import h5py
import numpy as np
from pathlib import Path
from PyQt5.QtCore import Qt, QSize, QRect
from PyQt5.QtWidgets import (
    QWidget,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy,
    QLayout,
    QSpacerItem,
    QToolButton,
    QMessageBox,
    QLabel,
)
import pyqtgraph as pg

from MasterProject.Client_modules.Init.initialize import BaseConfig
import Helpers

class QQuarkTab(QWidget):

    def __init__(self, experiment_obj=None, tab_name=None, is_experiment=True, dataset_file=None):
        super().__init__()

        ### Experiment Variables ###
        self.experiment_obj = experiment_obj
        self.tab_name = str(tab_name)
        self.config = {"Experiment Config": {}, "Base Config": BaseConfig}
        self.is_experiment = is_experiment
        self.data = None
        self.experiment_type = None
        self.experiment_instance = None  # The actual experiment object
        self.plots = []

        #colormap (e.g., 'viridis', 'inferno', etc.)
        cmap = pg.colormap.get('viridis')
        self.lut = cmap.getLookupTable()

        ### Setting up the Tab
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        ### Plotter within Tab
        self.plot_layout = QHBoxLayout(self)
        self.plot_layout.setContentsMargins(2, 2, 2, 2)
        self.plot_layout.setObjectName("plot_layout")

        # Plot Button Toolbar
        self.plot_toolbar = QVBoxLayout()
        self.plot_toolbar.setObjectName("plot_toolbar")
        self.copy_plot_button = QToolButton()
        self.copy_plot_button.setText("📋")
        self.copy_plot_button.setObjectName("copy_plot_button")
        self.save_data_button = QToolButton()
        self.save_data_button.setText("💾")
        self.save_data_button.setObjectName("save_data_button")
        self.coord_label = QLabel("X: ___\nY: ___")
        self.coord_label.setStyleSheet("font-size: 10px;")
        self.coord_label.setFixedWidth(50)  # Set a fixed width of 100 pixels
        self.coord_label.setObjectName("coord_label")

        self.plot_toolbar.addWidget(self.copy_plot_button)
        self.plot_toolbar.addWidget(self.save_data_button)
        spacerItem = QSpacerItem(20, 318, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.plot_toolbar.addItem(spacerItem)
        self.plot_toolbar.addWidget(self.coord_label)
        self.plot_layout.setSpacing(0)
        self.plot_layout.addLayout(self.plot_toolbar)

        # The actual plot itself
        self.plot_widget = pg.GraphicsLayoutWidget(self)
        self.plot_widget.setBackground("w")
        self.plot_widget.ci.setSpacing(2)  # Reduce spacing
        self.plot_widget.ci.setContentsMargins(3, 3, 3, 3)  # Optional: Adjust margins
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_widget.setMinimumSize(QSize(375, 0))
        self.plot_widget.scene().sigMouseMoved.connect(self.update_coordinates)
        self.plot_widget.setObjectName("plot_widget")

        self.plot_layout.addWidget(self.plot_widget)
        self.plot_layout.setStretch(0, 1)
        self.plot_layout.setStretch(1, 10)

        self.setLayout(self.plot_layout)

        if self.is_experiment and experiment_obj is not None:
            self.extract_experiment_instance(experiment_obj)
        elif not self.is_experiment and dataset_file is not None:
            self.load_dataset_file(dataset_file)

    def extract_experiment_instance(self, experiment_obj):
        for name, obj, in inspect.getmembers(experiment_obj):
            if name == self.tab_name:
                if inspect.isclass(obj):
                    print("found class instance: " + name)

                    ### create instance of experiment
                    self.experiment_instance = obj

                    ### reset the config
                    if (not hasattr(self.experiment_instance, "config_template")
                            or self.experiment_instance.config_template is None):
                        QMessageBox.critical(None, "Error", "No Config Template given.")
                    ### HANDLE CONFIG ERROR HANDLING
                    else:
                        self.config["Experiment Config"] = self.experiment_instance.config_template

                    # HANDLE EXPERIMENT TYPE????
                    self.experiment_type = None
                    ### check what kind of experiment class it is

                    return

        if self.experiment_instance is None:
            QMessageBox.critical(None, "Error", "No Experiment Class matching File Name Found.")

    def load_dataset_file(self, dataset_file):
        self.data = Helpers.h5_to_dict(dataset_file)
        self.plot_data()

    def plot_data(self):
        self.clear_plots()
        num_plots = 0
        f = self.data
        if 'data' in self.data:
            f = self.data['data']
        for name, data in f.items():
            if isinstance(data, int):
                continue
            if isinstance(data, list):
                data = np.array(data[0][0])
            shape = data.shape

            # 1D data -> 2D Plots
            if len(shape) == 1:
                x_data = None
                if 'x_pts' in f:
                    x_data = list(f['x_pts'])
                    # Iterate through all keys in the file
                    if name == 'x_pts':
                        continue
                    y_data = list(data)
                    if len(x_data) == len(y_data):
                        num_plots += 1
                        plot = self.plot_widget.addPlot()
                        plot.plot(x_data, y_data, pen=None, symbol='o', symbolSize=3, symbolBrush='b',
                                  name=name)  # Scatter plot
                        plot.setLabel("left", name)
                        plot.showGrid(x=True, y=True)
                        self.plots.append(plot)
                        self.plot_widget.nextRow()
            elif len(shape) == 2:
                num_plots += 1
                plot = self.plot_widget.addPlot(title=name)
                # 2-column data -> IQ scatter plot
                if shape[1] == 2:
                    plot.plot(data[:, 0], data[:, 1], pen=None, symbol="o")
                    self.plot_widget.nextRow()
                # General 2D data -> Heatmap
                else:
                    img = pg.ImageItem(data.T)  # Transpose for correct orientation
                    img.setLookupTable(self.lut)
                    plot.addItem(img)
                    if num_plots % 2 == 0:
                        self.plot_widget.nextRow()
                self.plots.append(plot)
        print("plotted", self.data)

    def clear_plots(self):
        self.plot_widget.ci.clear()
        self.plots = []

    def update_coordinates(self, pos):
        ### find the active plot
        for plot in self.plots:
            vb = plot.vb  # ViewBox of each plot
            if plot.sceneBoundingRect().contains(pos):
                self.plot_widget.setCursor(Qt.CrossCursor)
                mouse_point = vb.mapSceneToView(pos)
                x, y = mouse_point.x(), mouse_point.y()
                self.coord_label.setText(f"X: {x:.2f}\nY: {y:.2f}")
                break

    def process_data(self, data):
        self.data = data

        ### check what set number is being run
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

        ### create a diction to feed into the plot widget for labels
        # plot_labels = {
        #     "x label": self.experiment.cfg["x_pts_label"],
        #     "y label": self.experiment.cfg["y_pts_label"],
        # }
        ### check for if the y label is none (for single varible sweep) and set the y label to I/Q or amp/phase
        # if plot_labels["y label"] == None:
        #     plot_labels["y label 1"] = "I (a.u.)"
        #     plot_labels["y label 2"] = "Q (a.u.)"

    def update_data(self, data):
        print("updating data")
        self.process_data(data)
        self.plot_data()