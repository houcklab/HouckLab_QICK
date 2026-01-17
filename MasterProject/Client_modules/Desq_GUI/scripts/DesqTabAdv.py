"""
============
DesqTab.py - SIMPLIFIED PLOTTING VERSION
============
The custom QDesqTab class for the central tabs module of the main application.

SIMPLIFIED PLOTTING ARCHITECTURE:
- Experiments plot via their `display()` method only
- No plotter-selection UI or logic
- Loaded datasets use auto-plotting
- Single, clear plotting entry point

Each QDesqTab is either an experiment tab or a data tab that stores its own object attributes,
configuration, data, and plotting.
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
import matplotlib
# Don't override backend here - let PlotSinkManager handle it
# matplotlib.use("Agg")  # REMOVED - conflicts with BackendDesq
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from PyQt5.QtGui import QKeySequence, QCursor, QImage, QPixmap, QColor
from PyQt5.QtCore import (
    Qt, QSize, qCritical, qInfo, qDebug, QRect, QTimer,
    pyqtSignal, qWarning, QSettings, QObject, QMutex, QMutexLocker
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
    QStackedWidget,
)
import pyqtgraph as pg
from matplotlib.collections import PathCollection
from matplotlib.patches import Rectangle

from MasterProject.Client_modules.Desq_GUI.scripts.ConfigTreePanelAdv import QConfigTreePanel
from MasterProject.Client_modules.Desq_GUI.scripts.ExperimentObject import ExperimentObject
import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers
from MasterProject.Client_modules.Desq_GUI.scripts.SmartFitter import FitManager, FitResult


# =============================================================================
# NEW: Plot Tracking Data Structures
# =============================================================================

@dataclass
class PyQtGraphPlotItem:
    """Tracks a single PyQtGraph plot with its associated label."""
    plot: pg.PlotItem
    label: Optional[Any] = None  # Label widget in GraphicsLayout
    row: int = 0
    col: int = 0


@dataclass
class MatplotlibFigureItem:
    """Tracks a matplotlib figure with all its associated widgets."""
    figure: Any  # matplotlib.figure.Figure
    canvas: FigureCanvas
    toolbar: NavigationToolbar
    container: QWidget
    labels: List[Any] = field(default_factory=list)  # Label widgets


class PlotManager:
    """
    Centralized plot management with thread safety.
    Handles both PyQtGraph and Matplotlib plots.
    """

    def __init__(self):
        self.mutex = QMutex()

        # PyQtGraph tracking
        self.pyqtgraph_plots: List[PyQtGraphPlotItem] = []
        self.pyqtgraph_labels: List[Any] = []  # Global labels (titles, etc.)

        # Matplotlib tracking
        self.matplotlib_figures: List[MatplotlibFigureItem] = []

        # Fit overlays (can be on either backend)
        self.fit_overlays: List[Any] = []

    def clear_all(self, plot_widget, matplotlib_layout):
        """Thread-safe clearing of all plots and labels."""
        with QMutexLocker(self.mutex):
            # Clear PyQtGraph
            for label in self.pyqtgraph_labels:
                try:
                    plot_widget.ci.removeItem(label)
                except:
                    pass

            for plot_item in self.pyqtgraph_plots:
                try:
                    plot_widget.ci.removeItem(plot_item.plot)
                    if plot_item.label is not None:
                        plot_widget.ci.removeItem(plot_item.label)
                except:
                    pass

            plot_widget.ci.clear()
            self.pyqtgraph_plots.clear()
            self.pyqtgraph_labels.clear()

            # Clear Matplotlib
            for fig_item in self.matplotlib_figures:
                for label in fig_item.labels:
                    label.deleteLater()
                fig_item.toolbar.deleteLater()
                fig_item.canvas.deleteLater()
                try:
                    plt.close(fig_item.figure)
                except:
                    pass

                try:
                    if fig_item.container is not None:
                        fig_item.container.setParent(None)
                        fig_item.container.deleteLater()
                except Exception:
                    pass

            # Clear matplotlib layout
            while matplotlib_layout.count():
                item = matplotlib_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            self.matplotlib_figures.clear()

            # Clear fit overlays
            self.fit_overlays.clear()

    def remove_pyqtgraph_plot(self, plot_widget, plot_to_remove):
        """Remove a specific PyQtGraph plot and its label."""
        with QMutexLocker(self.mutex):
            for i, plot_item in enumerate(self.pyqtgraph_plots):
                if plot_item.plot == plot_to_remove:
                    try:
                        plot_widget.ci.removeItem(plot_item.plot)
                        if plot_item.label is not None:
                            plot_widget.ci.removeItem(plot_item.label)
                    except:
                        pass
                    self.pyqtgraph_plots.pop(i)
                    return True
            return False

    def add_pyqtgraph_plot(self, plot, label=None, row=0, col=0):
        """Add a PyQtGraph plot with thread safety."""
        with QMutexLocker(self.mutex):
            plot_item = PyQtGraphPlotItem(plot=plot, label=label, row=row, col=col)
            self.pyqtgraph_plots.append(plot_item)

    def add_pyqtgraph_label(self, label):
        """Add a global PyQtGraph label (e.g., figure title)."""
        with QMutexLocker(self.mutex):
            self.pyqtgraph_labels.append(label)

    def add_matplotlib_figure(self, fig_item: MatplotlibFigureItem):
        """Add a matplotlib figure with all its widgets."""
        with QMutexLocker(self.mutex):
            self.matplotlib_figures.append(fig_item)

    def get_matplotlib_canvases(self):
        """Get all matplotlib canvases (thread-safe)."""
        with QMutexLocker(self.mutex):
            return [fig.canvas for fig in self.matplotlib_figures]

    def get_matplotlib_figures(self):
        """Get all matplotlib figure objects (thread-safe)."""
        with QMutexLocker(self.mutex):
            return [fig.figure for fig in self.matplotlib_figures]

    def get_pyqtgraph_plots(self):
        """Get all PyQtGraph plots (thread-safe)."""
        with QMutexLocker(self.mutex):
            return [item.plot for item in self.pyqtgraph_plots]

    def has_pyqtgraph_content(self):
        """Check if there are any PyQtGraph plots or labels (thread-safe)."""
        with QMutexLocker(self.mutex):
            return len(self.pyqtgraph_plots) > 0 or len(self.pyqtgraph_labels) > 0

    def has_matplotlib_content(self):
        """Check if there are any matplotlib figures (thread-safe)."""
        with QMutexLocker(self.mutex):
            return len(self.matplotlib_figures) > 0

    def clear_fit_overlays(self):
        """Clear all fit overlay references."""
        with QMutexLocker(self.mutex):
            self.fit_overlays.clear()


# =============================================================================
# ExperimentInfoBar
# =============================================================================

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
            # Calculate needed height dynamically
            header_height = self.header.sizeHint().height()
            content_height = self.content_widget.sizeHint().height()
            total_height = header_height + content_height

            # Cap the maximum to avoid it growing too big
            max_allowed = 300
            final_height = min(total_height, max_allowed)

            self.content_area.setMaximumHeight(content_height)
            self.setMaximumHeight(final_height)
        else:
            self.toggle_button.setStyleSheet(
                "image: url('MasterProject/Client_modules/Desq_GUI/assets/chevron-right.svg');")
            # Collapse
            self.content_area.setMaximumHeight(0)
            self.setMaximumHeight(self.header.sizeHint().height())


# =============================================================================
# Main QDesqTab Class - SIMPLIFIED PLOTTING VERSION
# =============================================================================

class QDesqTab(QWidget):
    """
    A tab widget that holds either an experiment instance or a data instance.

    SIMPLIFIED PLOTTING ARCHITECTURE:
    - Experiments plot via their `display()` method
    - No plotter-selection UI or logic
    - Loaded datasets use auto-plotting
    - Thread-safe plot management via PlotManager
    - Proper resource cleanup (no orphaned labels/widgets)
    """

    updated_tab = pyqtSignal()
    """Signal sent to main application when tab is updated."""

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
        Initializes a QDesqTab widget that will either be an experiment or dataset tab.

        Parameters:
        -----------
        experiment_id : tuple(str, str)
            The experiment path and class name
        tab_name : str
            Name of the tab widget
        source_file_name : str
            Name of the file the experiment lies in
        is_experiment : bool
            Whether the tab corresponds to an experiment or dataset
        dataset_file : str
            Path to the dataset file
        app : QApplication
            The main application (Desq.py)
        workspace : str
            The workspace directory
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

        # NEW: Use PlotManager for centralized, thread-safe plot tracking
        self.plot_manager = PlotManager()

        # --- incremental plotting caches (PyQtGraph + Matplotlib embed) ---
        self._auto_plot_signature = None
        self._auto_plot_cache = []  # list of per-plot handles (curve/image/etc)
        self._mpl_embed_signature = None  # tuple of figure ids currently embedded
        self._mpl_content_signature = None  # Content-based signature for figure isolation

        # PyQtGraph live update tracking
        self._pyqtgraph_signature = None
        self._pyqtgraph_axes_map = []

        # Track whether initial labels/layout have been set up
        # This prevents duplicate labels when updating plots in-place
        self.labels_added = False

        # Fit manager and results
        self.fit_manager = FitManager()
        self.fit_results = []
        self.fit_overlays = []  # Delegated to plot_manager

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
        self.replot_button.setToolTip("Replots the current data")
        self.snip_plot_button = Helpers.create_button("Snip", "snip_plot_button", True, self.plot_utilities_container)
        self.snip_plot_button.setToolTip("Snip Plot to Clipboard")
        self.export_data_button = Helpers.create_button("Export", "export_data_button", False,
                                                        self.plot_utilities_container)
        self.coord_label = QLabel("X: _____ Y: _____")
        self.coord_label.setAlignment(Qt.AlignRight)
        self.coord_label.setObjectName("coord_label")

        spacerItem = QSpacerItem(0, 30, QSizePolicy.Expanding, QSizePolicy.Fixed)
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
        self.runtime_label = QLabel("Estimated Runtime: ---")
        self.runtime_label.setObjectName("runtime_label")
        self.endtime_label = QLabel("End: ---")
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

        ### Plot Settings Bar (simplified - no plotter selection)
        self.plot_settings_container = QWidget()
        self.plot_settings_container.setMaximumHeight(30)
        self.plot_settings = QHBoxLayout(self.plot_settings_container)
        self.plot_settings.setContentsMargins(10, 0, 0, 5)
        self.plot_settings.setSpacing(5)
        self.plot_settings.setObjectName("plot_settings")

        self.average_simult_checkbox = QCheckBox("Average Simult.", self.plot_settings_container)
        self.average_simult_checkbox.setToolTip("Average intermediate data simultaneously versus at end of set.")

        self.use_matplotlib_checkbox = QCheckBox("Matplotlib", self.plot_settings_container)
        self.use_matplotlib_checkbox.setToolTip("Use native Matplotlib rendering instead of converting to PyQtGraph.")
        self.use_matplotlib_checkbox.setChecked(False)

        self.fit_label = QLabel("Fit:")
        self.fit_label.setObjectName("fit_label")
        self.fit_combo = QComboBox(self.plot_settings_container)
        self.fit_combo.setFixedWidth(150)
        self.fit_combo.setObjectName("fit_combo")
        # Add 1D models and 2D analysis methods
        fit_options = ["None", "Auto"] + self.fit_manager.get_available_models_1d() + ["---", "Chevron Pattern"]
        self.fit_combo.addItems(fit_options)
        self.fit_combo.setToolTip("Select fitting model (1D or 2D)")

        self.fit_button = Helpers.create_button("Fit", "fit_button", True, self.plot_settings_container)
        self.fit_button.setToolTip("Fit data and overlay results")
        self.fit_button.setFixedWidth(50)

        self.delete_label = QLabel("")
        self.delete_label.setAlignment(Qt.AlignRight)
        self.delete_label.setObjectName("delete_label")

        spacerItem = QSpacerItem(0, 30, QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.plot_settings.addWidget(self.fit_label)
        self.plot_settings.addWidget(self.fit_combo)
        self.plot_settings.addWidget(self.fit_button)
        self.plot_settings.addWidget(self.average_simult_checkbox)
        self.plot_settings.addWidget(self.use_matplotlib_checkbox)
        self.plot_settings.addItem(spacerItem)
        self.plot_settings.addWidget(self.delete_label)
        self.plot_layout.addWidget(self.plot_settings_container)

        # Create a stacked widget to switch between PyQtGraph and Matplotlib
        self.plot_stack = QStackedWidget()
        self.plot_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # PyQtGraph widget (index 0)
        self.plot_widget = pg.GraphicsLayoutWidget(self)
        label = self.plot_widget.ci.addLabel("Nothing to plot.", row=0, col=0, colspan=2, size='12pt')
        self.plot_manager.add_pyqtgraph_label(label)
        self.plot_widget.setBackground("w")
        self.plot_widget.ci.setSpacing(2)
        self.plot_widget.ci.setContentsMargins(3, 3, 3, 3)
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_widget.setMinimumSize(QSize(375, 0))
        self.plot_widget.setObjectName("plot_widget")

        # Matplotlib widget (index 1)
        self.matplotlib_container = QWidget()
        self.matplotlib_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.matplotlib_layout = QVBoxLayout(self.matplotlib_container)
        self.matplotlib_layout.setContentsMargins(0, 0, 0, 0)
        self.matplotlib_layout.setSpacing(5)

        # Add both to stacked widget
        self.plot_stack.addWidget(self.plot_widget)  # Index 0
        self.plot_stack.addWidget(self.matplotlib_container)  # Index 1
        self.plot_stack.setCurrentIndex(0)  # Start with PyQtGraph

        self.plot_layout.addWidget(self.plot_stack)
        self.plot_layout.setStretch(0, 1)
        self.plot_layout.setStretch(1, 10)
        self.plot_wrapper.setLayout(self.plot_layout)

        # Add config panel
        self.experiment_config_panel.setParent(self.splitter)

        # Defining the default sizes for the splitter
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)
        self.tab_layout.addWidget(self.splitter)
        self.setLayout(self.tab_layout)

        # extract dataset file depending on the tab type being a dataset
        if not self.is_experiment and self.dataset_file is not None:
            self.load_dataset_file(self.dataset_file)
        self.setup_signals()

    # =========================================================================
    # BACKWARDS COMPATIBILITY PROPERTIES
    # =========================================================================

    @property
    def plots(self):
        """Backwards compatibility: return list of PyQtGraph plots."""
        return self.plot_manager.get_pyqtgraph_plots()

    @plots.setter
    def plots(self, value):
        """Backwards compatibility: ignore direct assignment."""
        pass  # Managed internally by plot_manager

    @property
    def labels(self):
        """Backwards compatibility: return list of labels."""
        return list(self.plot_manager.pyqtgraph_labels)

    @labels.setter
    def labels(self, value):
        """Backwards compatibility: ignore direct assignment."""
        pass  # Managed internally by plot_manager

    # =========================================================================
    # SIGNAL SETUP
    # =========================================================================

    def setup_signals(self):
        """Sets up all the signals and slots of the QDesqTab widget."""
        self.plot_widget.scene().sigMouseMoved.connect(self.update_coordinates)
        self.snip_plot_button.clicked.connect(self.capture_plot_to_clipboard)
        self.export_data_button.clicked.connect(self.export_data)
        self.reExtract_experiment_button.clicked.connect(self.reExtract_experiment)
        self.replot_button.clicked.connect(self.replot_data)
        self.fit_button.clicked.connect(self.perform_fit)

        self.use_matplotlib_checkbox.toggled.connect(self.on_matplotlib_toggled)

        self.remove_plot_shortcut = QShortcut(QKeySequence("D"), self)
        self.remove_plot_shortcut.activated.connect(self.remove_plot)

        if self.is_experiment:
            self.experiment_config_panel.update_runtime_prediction.connect(self.app.call_tab_runtime_prediction)
            self.reExtract_experiment_button.setEnabled(True)
            self.predict_runtime(self.experiment_config_panel.config)

        if self.tab_name != "None":
            self.export_data_button.setEnabled(True)
            self.replot_button.setEnabled(True)

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def capture_plot_to_clipboard(self):
        """Captures a screenshot of the plot and saves it to clipboard."""
        if self.use_matplotlib_checkbox.isChecked():
            pixmap = self.matplotlib_container.grab()
        else:
            pixmap = self.plot_widget.grab()

        clipboard = QApplication.clipboard()
        clipboard.setPixmap(pixmap)
        qInfo("Current graph snipped to clipboard!")

        self.snip_plot_button.setText('Done!')
        QTimer.singleShot(3000, lambda: self.snip_plot_button.setText('Snip'))

    # =========================================================================
    # CORE PLOTTING METHODS (SIMPLIFIED)
    # =========================================================================

    def clear_plots(self):
        """
        Thread-safe clearing of all plots and labels.
        Properly cleans up all resources in both PyQtGraph and Matplotlib modes.
        """
        qInfo(f"Clearing all plots for tab: {self.tab_name}...")

        # Use plot_manager for thread-safe cleanup
        self.plot_manager.clear_all(self.plot_widget, self.matplotlib_layout)

        # Clear fit overlays
        self.clear_fit_overlays()

        # Reset flags
        self.labels_added = False

        # Reset incremental plotting caches
        self._auto_plot_signature = None
        self._auto_plot_cache = []
        self._mpl_embed_signature = None
        self._mpl_content_signature = None  # Content-based signature for figure isolation

        # Reset PyQtGraph live update tracking
        self._pyqtgraph_signature = None
        self._pyqtgraph_axes_map = []

        qInfo(f"All plots cleared successfully for tab: {self.tab_name}")

    def remove_plot(self):
        """
        Removes a plot at the mouse cursor position with proper label cleanup.
        Only works for PyQtGraph mode.
        """
        if self.use_matplotlib_checkbox.isChecked():
            qWarning("Plot removal not supported in Matplotlib mode")
            return

        pos = self.plot_widget.mapFromGlobal(QCursor.pos())

        # Find which plot is under the cursor
        for plot in self.plot_manager.get_pyqtgraph_plots():
            vb = plot.vb
            if plot.sceneBoundingRect().contains(pos):
                # Remove the plot and its label using plot_manager
                if self.plot_manager.remove_pyqtgraph_plot(self.plot_widget, plot):
                    self.plot_widget.update()
                    qInfo("Plot removed successfully")
                    return

        qWarning("No plot found at cursor position")

    def plot_data(self, exp_instance=None, data_to_plot=None):
        """
        SIMPLIFIED: Main plotting entry point.

        Plotting behavior:
        - For experiments: Call display() method if available, fall back to auto_plot
        - For loaded data: Always use auto_plot
        """
        if data_to_plot is None:
            data_to_plot = self.data

        # Clear plots if starting fresh (mode-aware!)
        if self.use_matplotlib_checkbox.isChecked():
            if len(self.plot_manager.matplotlib_figures) == 0:
                self.clear_plots()
        else:
            if len(self.plot_manager.get_pyqtgraph_plots()) == 0:
                self.clear_plots()

        # SIMPLIFIED PLOTTING LOGIC:
        # 1. For experiments with display() method: use display()
        # 2. For loaded data (non-experiments): use auto_plot
        # 3. Fall back to auto_plot if display() fails or doesn't exist

        if self.is_experiment and exp_instance is not None:
            # Try to use the experiment's display() method
            if self._try_experiment_display(exp_instance, data_to_plot):
                return  # display() succeeded
            # Fall back to auto_plot
            qInfo("Falling back to auto_plot for experiment")
            self.auto_plot_prepare(data_to_plot)
        else:
            # Loaded data: always use auto_plot
            self.auto_plot_prepare(data_to_plot)

    def _try_experiment_display(self, exp_instance, data_to_plot):
        """
        Attempt to call the experiment's display() method.

        Returns True if display() was called successfully, False otherwise.
        """
        try:
            # Check if exp_instance has an overridden display() method
            if not hasattr(exp_instance, "display"):
                return False

            display_method = getattr(exp_instance, "display")
            if not callable(display_method):
                return False

            # Check if display() is overridden (not the base ExperimentClass.display)
            # by checking if it does more than just 'pass'
            for cls in type(exp_instance).__mro__[1:]:
                if "display" in cls.__dict__:
                    parent_method = cls.__dict__["display"]
                    break
            else:
                parent_method = None

            # If display is not overridden, use auto_plot
            if parent_method is not None and display_method.__func__ is parent_method:
                return False

            # Call display() with plot sink context if available
            psm = getattr(self.app, "plot_sink_manager", None)
            if psm is not None:
                with psm.sink_context(self):
                    exp_instance.display(data_to_plot, plotDisp=True)
            else:
                exp_instance.display(data_to_plot, plotDisp=True)

            return True

        except Exception as e:
            qWarning(f"Experiment display() failed: {str(e)}")
            qWarning(traceback.format_exc())
            return False

    def handle_pltplot(self, *args, **kwargs):
        """
        Handles matplotlib plots by routing to appropriate backend.
        Supports any number of figures with any layout.
        """
        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()

        # Route to appropriate backend
        if self.use_matplotlib_checkbox.isChecked():
            self.embed_matplotlib_plots(*args, **kwargs)
        else:
            self.convert_matplotlib_to_pyqtgraph(*args, **kwargs)

    def _copy_matplotlib_figure(self, original_fig):
        """
        Create an independent copy of a matplotlib figure.

        This isolates the figure from matplotlib's global state so that
        other experiments can't interfere with it.

        Returns:
            A new Figure object that's a copy of the original
        """
        import pickle
        import io

        try:
            # Use pickle to create a deep copy of the figure
            buf = io.BytesIO()
            pickle.dump(original_fig, buf)
            buf.seek(0)
            new_fig = pickle.load(buf)
            buf.close()

            # The copied figure won't have a number in matplotlib's registry
            # which is exactly what we want for isolation
            return new_fig

        except Exception as e:
            qWarning(f"Failed to copy figure via pickle: {e}, using original")
            return original_fig

    def _compute_figure_content_signature(self, figures):
        """
        Compute a signature based on figure CONTENT rather than object id.

        This allows us to detect when the same logical figure is being updated
        (same axes structure, same data shapes) vs when a completely new figure
        is being created.
        """
        sig_parts = []
        for fig in figures:
            fig_sig = []
            # Include figure size
            fig_sig.append(fig.get_size_inches().tobytes())
            # Include number of axes
            fig_sig.append(len(fig.axes))
            for ax in fig.axes:
                # Include axis position
                pos = ax.get_position()
                fig_sig.append((round(pos.x0, 2), round(pos.y0, 2),
                                round(pos.width, 2), round(pos.height, 2)))
                # Include data presence indicators
                fig_sig.append(len(ax.lines))
                fig_sig.append(len(ax.images))
                # Include data shapes for lines
                for line in ax.lines[:3]:  # Just first 3 to keep signature small
                    xdata = line.get_xdata()
                    if hasattr(xdata, '__len__'):
                        fig_sig.append(len(xdata))
                # Include data shapes for images
                for img in ax.images[:2]:
                    data = img.get_array()
                    if data is not None:
                        fig_sig.append(data.shape)
            sig_parts.append(tuple(fig_sig))
        return tuple(sig_parts)

    def isolate_matplotlib_figures(self):
        """
        Isolate embedded matplotlib figures from the global registry.

        This should be called when an experiment finishes to ensure the displayed
        figures won't be affected by future experiments that may reuse figure numbers.

        The method:
        1. Creates copies of all embedded figures
        2. Replaces the canvases with new ones displaying the copies
        3. Closes the original figures to free their figure numbers
        """
        if not self.plot_manager.matplotlib_figures:
            return

        qInfo(f"[{self.tab_name}] Isolating {len(self.plot_manager.matplotlib_figures)} matplotlib figures...")

        for fig_item in self.plot_manager.matplotlib_figures:
            try:
                original_fig = fig_item.figure

                # Create isolated copy
                copied_fig = self._copy_matplotlib_figure(original_fig)

                # Update the canvas to use the copied figure
                # We need to create a new canvas since FigureCanvas binds to a specific figure
                old_canvas = fig_item.canvas
                new_canvas = FigureCanvas(copied_fig)

                # Copy size settings
                new_canvas.setMinimumHeight(old_canvas.minimumHeight())
                new_canvas.setMaximumHeight(old_canvas.maximumHeight())
                new_canvas.setSizePolicy(old_canvas.sizePolicy())

                # Replace canvas in the layout
                layout = fig_item.container.layout()
                if layout:
                    # Find and replace the canvas
                    for i in range(layout.count()):
                        item = layout.itemAt(i)
                        if item and item.widget() == old_canvas:
                            layout.removeWidget(old_canvas)
                            layout.insertWidget(i, new_canvas)
                            break

                # Update toolbar to use new canvas
                fig_item.toolbar.canvas = new_canvas

                # Update fig_item references
                fig_item.figure = copied_fig
                fig_item.canvas = new_canvas

                # Clean up old canvas
                old_canvas.deleteLater()

                # Close the original figure to remove from global registry
                try:
                    plt.close(original_fig)
                except:
                    pass

                new_canvas.draw_idle()

            except Exception as e:
                qWarning(f"Failed to isolate figure: {e}")

        # Reset signatures since figures changed
        self._mpl_embed_signature = None
        self._mpl_content_signature = None

        qInfo(f"[{self.tab_name}] Figure isolation complete")

    def embed_matplotlib_plots(self, *args, **kwargs):
        """
        Embed matplotlib figures in the tab.

        LIVE UPDATE STRATEGY:
        - During live plotting (experiment running), we embed the ORIGINAL figures
          so the experiment can continue updating them
        - When the experiment finishes, call isolate_matplotlib_figures() to create
          independent copies that won't be affected by future experiments
        - For in-place updates, we just redraw existing canvases
        """
        self.plot_stack.setCurrentIndex(1)

        figures = kwargs.pop("_captured_figures", None)
        if not figures:
            # Fallback (GUI-thread view)
            figures = [m.canvas.figure for m in _pylab.Gcf.get_all_fig_managers()]

        if not figures:
            qWarning("No matplotlib figures to embed")
            return

        # Use content-based signature for detecting updates vs rebuilds
        content_sig = self._compute_figure_content_signature(figures)
        obj_sig = tuple(id(fig) for fig in figures)

        # Decide whether this is an in-place update or a layout change
        existing_items = list(self.plot_manager.matplotlib_figures)

        # Can update in-place if same figure objects are being updated
        same_objects = (self._mpl_embed_signature == obj_sig and len(existing_items) > 0)

        # Or if same content structure (same logical figure being redrawn)
        same_content = (hasattr(self, '_mpl_content_signature') and
                        self._mpl_content_signature == content_sig and
                        len(existing_items) == len(figures) and
                        len(existing_items) > 0)

        can_update_in_place = same_objects or same_content

        if can_update_in_place:
            # In-place update path: just redraw existing canvases
            available_height = max(200, self.matplotlib_container.height() - 50)
            fig_height = max(150, available_height // max(1, len(figures)))

            for fig_item in self.plot_manager.matplotlib_figures:
                fig_item.canvas.draw_idle()

            self.labels_added = True
            return

        # Layout changed or first time: rebuild widgets
        qInfo(f"[{self.tab_name}] Embedding {len(figures)} matplotlib figure(s)...")
        self.clear_plots()
        self._mpl_embed_signature = obj_sig
        self._mpl_content_signature = content_sig

        for i, fig in enumerate(figures):
            # During live plotting, embed the ORIGINAL figure so experiment can update it
            # Isolation will happen when experiment finishes (via isolate_matplotlib_figures)

            try:
                if hasattr(fig, '_layoutgrid') and fig._layoutgrid is not None:
                    pass
                else:
                    fig.set_constrained_layout(False)
                    fig.tight_layout(pad=2.0)
            except (ValueError, ZeroDivisionError, Exception):
                pass

            available_height = max(200, self.matplotlib_container.height() - 50)
            fig_height = max(150, available_height // max(1, len(figures)))

            canvas = FigureCanvas(fig)
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            toolbar = NavigationToolbar(canvas, self.matplotlib_container)
            toolbar.setIconSize(QSize(14, 14))
            toolbar.setStyleSheet(
                "QToolBar { padding: 1px; spacing: 2px; } "
                "QToolButton { margin: 0; padding: 0; }"
            )
            toolbar.setFixedHeight(30)

            fig_layout = QVBoxLayout()
            fig_layout.addWidget(toolbar)
            fig_layout.addWidget(canvas)
            fig_layout.setContentsMargins(0, 0, 0, 0)
            fig_layout.setSpacing(0)

            fig_widget = QWidget()
            fig_widget.setLayout(fig_layout)
            fig_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            self.matplotlib_layout.addWidget(fig_widget)

            fig_item = MatplotlibFigureItem(
                figure=fig,
                canvas=canvas,
                toolbar=toolbar,
                container=fig_widget,
                labels=[]
            )
            self.plot_manager.add_matplotlib_figure(fig_item)

            canvas.draw_idle()

        self.matplotlib_layout.addStretch()
        self.labels_added = True
        qInfo(f"[{self.tab_name}] Successfully embedded {len(figures)} matplotlib figure(s)")

    def convert_matplotlib_to_pyqtgraph(self, *args, **kwargs):
        """
        Converts ANY matplotlib figure/axes layout to PyQtGraph.
        Handles complex multi-figure, multi-axes scenarios.

        NEW: Supports live updates by:
        1. Computing figure signature to detect layout changes
        2. Only rebuilding layout when structure changes
        3. Not closing figures (needed for live updates)
        4. Preserving original grid layout from matplotlib
        """
        self.plot_stack.setCurrentIndex(0)
        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()

        figures = kwargs.pop("_captured_figures", None)
        if not figures:
            figures = [m.canvas.figure for m in _pylab.Gcf.get_all_fig_managers()]

        if not figures:
            qWarning("No matplotlib figures to convert")
            return

        # Compute signature for this set of figures (structure only, not data)
        new_sig = self._compute_pyqtgraph_signature(figures)

        # Check if we can update in place
        can_update_in_place = (
                hasattr(self, '_pyqtgraph_signature') and
                self._pyqtgraph_signature == new_sig and
                len(self.plot_manager.get_pyqtgraph_plots()) > 0
        )

        if can_update_in_place:
            # Update existing plots without rebuilding layout
            self._update_pyqtgraph_plots(figures)
            return

        # Layout changed - need to rebuild
        self.clear_plots()
        self._pyqtgraph_signature = new_sig

        # Add title label if this is a dataset
        if not self.labels_added and not self.is_experiment:
            label = self.plot_widget.ci.addLabel(self.file_name, row=0, col=0, colspan=2, size='12pt')
            self.plot_manager.add_pyqtgraph_label(label)

        curr_row = 0 if self.is_experiment else 1
        self._pyqtgraph_axes_map = []  # Track (fig_idx, ax_idx, plot) for updates

        for fig_idx, fig in enumerate(figures):
            axes = fig.get_axes()

            if len(axes) == 0:
                continue

            # Detect grid layout from axes positions
            grid_layout = self._detect_axes_grid(axes)
            nrows, ncols = grid_layout['nrows'], grid_layout['ncols']

            # Add figure title
            fig_title = fig._suptitle.get_text() if fig._suptitle else f"{self.file_name} fig{fig_idx + 1}"
            if not self.labels_added:
                label = self.plot_widget.ci.addLabel(fig_title, row=curr_row, col=0,
                                                     colspan=ncols, size='12pt')
                self.plot_manager.add_pyqtgraph_label(label)

            curr_row += 1
            self.plot_widget.nextRow()

            # Process each axis in detected grid order
            for ax_row in range(nrows):
                for ax_col in range(ncols):
                    ax_idx = grid_layout['grid'].get((ax_row, ax_col))
                    if ax_idx is None:
                        continue

                    ax = axes[ax_idx]

                    # Skip empty axes
                    if self._is_axis_empty(ax):
                        continue

                    # Add axis title as a sublabel (only if there's meaningful content)
                    ax_title = ax.get_title()
                    if ax_title and not self.labels_added:
                        label = self.plot_widget.ci.addLabel(ax_title, row=curr_row, col=ax_col,
                                                             colspan=1, size='9pt')
                        self.plot_manager.add_pyqtgraph_label(label)

                # After titles for this row, start a new row for plots
                if any(grid_layout['grid'].get((ax_row, c)) is not None for c in range(ncols)):
                    if not self.labels_added:
                        curr_row += 1
                        self.plot_widget.nextRow()

                    # Add the actual plots for this row
                    for ax_col in range(ncols):
                        ax_idx = grid_layout['grid'].get((ax_row, ax_col))
                        if ax_idx is None:
                            continue

                        ax = axes[ax_idx]
                        if self._is_axis_empty(ax):
                            continue

                        # Extract and plot the axis data
                        plot = self.extract_and_plot_pyqtgraph(ax, curr_row, ax_col, None)
                        if plot is not None:  # Only track successfully created plots
                            self._pyqtgraph_axes_map.append((fig_idx, ax_idx, plot))

                    curr_row += 1
                    self.plot_widget.nextRow()

            # Add spacing between figures
            curr_row += 1
            self.plot_widget.nextRow()

        self.labels_added = True
        # NOTE: Don't call plt.close('all') here - it breaks live plotting!
        # Figures will be closed when tab is closed or experiment stops
        qInfo(f"Converted matplotlib figures to PyQtGraph (preserved layout)")

    def _compute_pyqtgraph_signature(self, figures):
        """
        Compute a signature for figure structure to detect layout changes.
        Only includes structure info, not data values.
        """
        sig_parts = []
        for fig in figures:
            axes = fig.get_axes()
            fig_sig = []
            for ax in axes:
                # Include axis position and whether it has images/lines/scatter
                pos = ax.get_position()
                ax_sig = (
                    round(pos.x0, 2), round(pos.y0, 2),
                    round(pos.width, 2), round(pos.height, 2),
                    len(ax.get_lines()) > 0,
                    len(ax.get_images()) > 0,
                    len([c for c in ax.collections if isinstance(c, PathCollection)]) > 0
                )
                fig_sig.append(ax_sig)
            sig_parts.append(tuple(fig_sig))
        return tuple(sig_parts)

    def _detect_axes_grid(self, axes):
        """
        Detect grid layout from axes positions.
        Returns dict with nrows, ncols, and grid mapping (row, col) -> ax_index.
        """
        if len(axes) == 0:
            return {'nrows': 0, 'ncols': 0, 'grid': {}}

        if len(axes) == 1:
            return {'nrows': 1, 'ncols': 1, 'grid': {(0, 0): 0}}

        # Get axis positions (bounding boxes)
        positions = []
        for i, ax in enumerate(axes):
            pos = ax.get_position()
            positions.append({
                'idx': i,
                'x0': pos.x0, 'y0': pos.y0,
                'x1': pos.x0 + pos.width,
                'y1': pos.y0 + pos.height,
                'cx': pos.x0 + pos.width / 2,
                'cy': pos.y0 + pos.height / 2
            })

        # Cluster by y-position (rows) and x-position (columns)
        # Use center points with tolerance for clustering
        tol = 0.05

        # Find unique row positions (by y center)
        y_centers = sorted(set(round(p['cy'] / tol) * tol for p in positions), reverse=True)
        x_centers = sorted(set(round(p['cx'] / tol) * tol for p in positions))

        nrows = len(y_centers)
        ncols = len(x_centers)

        # Map each axis to grid position
        grid = {}
        for p in positions:
            # Find closest row
            row_idx = min(range(nrows), key=lambda r: abs(y_centers[r] - p['cy']))
            col_idx = min(range(ncols), key=lambda c: abs(x_centers[c] - p['cx']))
            grid[(row_idx, col_idx)] = p['idx']

        return {'nrows': nrows, 'ncols': ncols, 'grid': grid}

    def _update_pyqtgraph_plots(self, figures):
        """
        Update existing PyQtGraph plots with new data from matplotlib figures.
        Called when figure structure hasn't changed (live update path).
        """
        if not hasattr(self, '_pyqtgraph_axes_map'):
            return

        for fig_idx, ax_idx, plot in self._pyqtgraph_axes_map:
            # Skip entries with None plot (from empty axes)
            if plot is None:
                continue

            if fig_idx >= len(figures):
                continue

            fig = figures[fig_idx]
            axes = fig.get_axes()
            if ax_idx >= len(axes):
                continue

            ax = axes[ax_idx]

            try:
                # Update lines
                plot_items = [item for item in plot.items if isinstance(item, pg.PlotDataItem)]
                lines = ax.get_lines()
                for i, line in enumerate(lines):
                    x, y = line.get_xdata(), line.get_ydata()
                    if x is None or y is None or len(x) == 0:
                        continue
                    if i < len(plot_items):
                        # Handle NaN values in line data
                        x_clean = np.asarray(x, dtype=float)
                        y_clean = np.asarray(y, dtype=float)
                        plot_items[i].setData(x_clean, y_clean)

                # Update images
                image_items = [item for item in plot.items if isinstance(item, pg.ImageItem)]
                images = ax.get_images()
                for i, img in enumerate(images):
                    data = img.get_array()
                    if data is None or data.size == 0:
                        continue
                    if i >= len(image_items):
                        continue

                    # Convert to numpy array and handle masked arrays
                    if hasattr(data, 'mask'):
                        # Masked array - fill masked values with NaN
                        data = np.ma.filled(data.astype(float), np.nan)
                    else:
                        data = np.asarray(data, dtype=float)

                    # Compute valid min/max for levels
                    valid_mask = ~np.isnan(data)
                    if np.any(valid_mask):
                        vmin, vmax = np.nanmin(data), np.nanmax(data)
                        if vmin == vmax:
                            vmax = vmin + 1  # Avoid zero-range
                        # Replace NaN with vmin for display
                        display_data = np.where(np.isnan(data), vmin, data)
                    else:
                        # All NaN - skip update to preserve previous view
                        continue

                    # Update image with explicit levels
                    image_items[i].setImage(display_data.T, levels=(vmin, vmax))

            except Exception as e:
                # If update fails, force a rebuild on next call
                qWarning(f"PyQtGraph live update failed: {e}")
                self._pyqtgraph_signature = None

    def _is_axis_empty(self, ax):
        """Check if a matplotlib axis has any plottable data."""
        has_lines = len(ax.get_lines()) > 0
        has_images = len(ax.get_images()) > 0
        has_scatter = len([c for c in ax.collections if isinstance(c, PathCollection)]) > 0
        has_bars = len([p for p in ax.patches if isinstance(p, Rectangle)]) > 0

        return not (has_lines or has_images or has_scatter or has_bars)

    def extract_and_plot_pyqtgraph(self, ax, row, col, plot_index=None):
        """
        Extract matplotlib axis data and plot in PyQtGraph.
        Properly tracks plots and labels.

        Returns:
            The PyQtGraph PlotItem created or updated
        """
        if self._is_axis_empty(ax):
            return None

        def mpl_color_to_pg(color):
            """Convert matplotlib color to PyQtGraph format."""
            if isinstance(color, str):
                rgba = mcolors.to_rgba(color)
            else:
                rgba = color
            r, g, b, a = [int(255 * c) for c in rgba]
            return (r, g, b, a)

        # Get existing plots for update mode
        existing_plots = self.plot_manager.get_pyqtgraph_plots()

        # Determine if we're updating an existing plot or creating new one
        if plot_index is not None and plot_index < len(existing_plots):
            # Update mode
            plot = existing_plots[plot_index]
            plot_data_items = [item for item in plot.items if
                               isinstance(item, pg.PlotDataItem) or isinstance(item, pg.ImageItem)]
            new_plot = False
        else:
            # Create new plot
            plot = self.plot_widget.ci.addPlot(row, col)
            self.plot_manager.add_pyqtgraph_plot(plot, row=row, col=col)
            new_plot = True
            plot_data_items = []

        plot_item_num = 0

        # Extract and plot lines
        for line in ax.get_lines():
            plot.setLabel('left', ax.get_ylabel())
            plot.setLabel('bottom', ax.get_xlabel())

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

            style = {
                'pen': pg.mkPen(color=color, width=width),
                'symbol': 'o',
                'symbolSize': 5,
                'symbolBrush': 'b'
            }

            if not new_plot and plot_item_num < len(plot_data_items):
                plot_data_items[plot_item_num].setData(x, y)
                plot_item_num += 1
            else:
                plot.plot(x, y, **style)

        # Extract and plot images
        for img in ax.get_images():
            data = img.get_array()
            extent = img.get_extent()  # [xmin, xmax, ymin, ymax]

            if data is None or data.size == 0:
                continue

            # Convert to numpy array and handle masked arrays
            if hasattr(data, 'mask'):
                # Masked array - fill masked values with NaN
                data = np.ma.filled(data.astype(float), np.nan)
            else:
                data = np.asarray(data, dtype=float)

            # Compute valid min/max for levels, handling all-NaN case
            # IMPORTANT: We ALWAYS create the ImageItem so it can be updated later during live plotting
            valid_mask = ~np.isnan(data)
            if np.any(valid_mask):
                vmin, vmax = np.nanmin(data), np.nanmax(data)
                if vmin == vmax:
                    vmax = vmin + 1  # Avoid zero-range
                # For display, replace NaN with vmin (will show as lowest color)
                display_data = np.where(np.isnan(data), vmin, data)
            else:
                # All NaN - use placeholder values but still create the ImageItem
                vmin, vmax = 0, 1
                display_data = np.zeros_like(data)

            if not new_plot and plot_item_num < len(plot_data_items):
                img_image = plot_data_items[plot_item_num]
                img_image.setImage(display_data.T, levels=(vmin, vmax))
                plot_item_num += 1
            else:
                plot.setLabel('left', ax.get_ylabel())
                plot.setLabel('bottom', ax.get_xlabel())

                img_item = pg.ImageItem(image=display_data.T)
                img_item.setLevels((vmin, vmax))
                plot.addItem(img_item)

                color_map = pg.colormap.get("viridis")
                img_item.setLookupTable(color_map.getLookupTable())
                img_item.setRect(pg.QtCore.QRectF(
                    extent[0], extent[2],
                    extent[1] - extent[0],
                    extent[3] - extent[2]
                ))

                color_bar = pg.ColorBarItem(
                    values=(vmin, vmax),
                    colorMap=color_map
                )
                color_bar.setImageItem(img_item, insert_in=plot)

        # Extract and plot scatter plots
        for coll in ax.collections:
            if isinstance(coll, PathCollection):
                offsets = coll.get_offsets()
                if len(offsets) > 0:
                    x, y = offsets[:, 0], offsets[:, 1]
                    facecolors = coll.get_facecolors()
                    color = (255, 0, 0, 150) if len(facecolors) == 0 else \
                        tuple((facecolors[0, :3] * 255).astype(int)) + (int(facecolors[0, 3] * 255),)
                    plot.plot(x, y, pen=None, symbol='o', symbolSize=5, symbolBrush=color)

        # Extract and plot bars/rectangles
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

        return plot

    # =========================================================================
    # AUTO PLOTTING
    # =========================================================================

    def auto_plot_prepare(self, data_to_plot=None):
        """
        Auto-plot for datasets / fallback plotting.

        NEW behavior (PyQtGraph):
        - If the structure of the plot is unchanged (same keys + same dimensionality),
          update existing PlotDataItem/ImageItem in place.
        - Only call clear_plots() when the plot layout truly changes.

        Supported inputs:
        - dict[str, array-like]  -> multiple 1D traces vs index
        - dict[str, (x, y)]      -> multiple 1D traces with explicit x
        - 2D array-like          -> image
        - (x, y)                 -> single trace
        """
        self.plot_stack.setCurrentIndex(0)

        if data_to_plot is None:
            data_to_plot = self.data

        if data_to_plot is None:
            qWarning("auto_plot_prepare: no data to plot")
            return

        # -----------------------------
        # Helpers
        # -----------------------------
        def _as_array(v):
            try:
                return np.asarray(v)
            except Exception:
                return None

        def _is_xy_pair(v):
            return (
                    isinstance(v, (tuple, list))
                    and len(v) == 2
                    and _as_array(v[0]) is not None
                    and _as_array(v[1]) is not None
            )

        # -----------------------------
        # Normalize input into a list of "plot specs"
        # Each spec is one of:
        #   ("curve", title, x, y)
        #   ("image", title, img2d)
        # -----------------------------
        specs = []

        if _is_xy_pair(data_to_plot):
            x = _as_array(data_to_plot[0])
            y = _as_array(data_to_plot[1])
            specs.append(("curve", "Plot", x, y))

        elif isinstance(data_to_plot, dict):
            # dict[str, y] or dict[str, (x,y)] or dict[str, 2D]
            for k, v in data_to_plot.items():
                if _is_xy_pair(v):
                    x = _as_array(v[0])
                    y = _as_array(v[1])
                    specs.append(("curve", str(k), x, y))
                else:
                    arr = _as_array(v)
                    if arr is None:
                        continue
                    if arr.ndim == 2:
                        specs.append(("image", str(k), arr))
                    elif arr.ndim == 1:
                        x = np.arange(arr.shape[0])
                        specs.append(("curve", str(k), x, arr))
                    else:
                        # Skip higher-dim silently
                        continue

        else:
            arr = _as_array(data_to_plot)
            if arr is None:
                qWarning(f"auto_plot_prepare: unsupported data type: {type(data_to_plot)}")
                return
            if arr.ndim == 2:
                specs.append(("image", "Image", arr))
            elif arr.ndim == 1:
                x = np.arange(arr.shape[0])
                specs.append(("curve", "Plot", x, arr))
            else:
                qWarning(f"auto_plot_prepare: unsupported ndarray dim: {arr.ndim}")
                return

        if not specs:
            qWarning("auto_plot_prepare: nothing plottable found")
            return

        # -----------------------------
        # Compute a signature for "layout"
        # (don't include actual data values; only structure)
        # -----------------------------
        def _shape_sig(a):
            try:
                a = np.asarray(a)
                return tuple(a.shape)
            except Exception:
                return None

        sig_parts = []
        for s in specs:
            if s[0] == "curve":
                _, title, x, y = s
                sig_parts.append(("curve", title, _shape_sig(x), _shape_sig(y)))
            else:
                _, title, img = s
                sig_parts.append(("image", title, _shape_sig(img)))

        new_signature = tuple(sig_parts)

        # -----------------------------
        # Decide update vs rebuild
        # -----------------------------
        can_update = (
                self._auto_plot_signature == new_signature
                and len(self._auto_plot_cache) == len(specs)
                and len(self._auto_plot_cache) > 0
        )

        if not can_update:
            # Rebuild
            self.clear_plots()
            self._auto_plot_signature = new_signature
            self._auto_plot_cache = []

            # Optional dataset title label (like your other paths)
            if (not self.labels_added) and (not self.is_experiment) and hasattr(self, "file_name"):
                label = self.plot_widget.ci.addLabel(self.file_name, row=0, col=0, colspan=1, size="12pt")
                self.plot_manager.add_pyqtgraph_label(label)

            # Create one plot per spec (stacked vertically)
            row = 1
            for idx, s in enumerate(specs):
                kind = s[0]
                title = s[1]

                # axis title label
                label = self.plot_widget.ci.addLabel(title, row=row, col=0, colspan=1, size="10pt")
                self.plot_manager.add_pyqtgraph_label(label)
                row += 1
                self.plot_widget.nextRow()

                plot = self.plot_widget.ci.addPlot(row, 0)
                plot.showGrid(x=True, y=True, alpha=0.3)
                self.plot_manager.add_pyqtgraph_plot(plot, label=None, row=row, col=0)

                if kind == "curve":
                    _, _, x, y = s
                    curve = plot.plot(x, y)
                    self._auto_plot_cache.append(("curve", curve, plot))
                else:
                    _, _, img = s
                    img_item = pg.ImageItem(img)
                    plot.addItem(img_item)
                    plot.setAspectLocked(True)
                    self._auto_plot_cache.append(("image", img_item, plot))

                row += 1
                self.plot_widget.nextRow()

            self.labels_added = True
            return

        # -----------------------------
        # Update in place (no clear)
        # -----------------------------
        for spec, cached in zip(specs, self._auto_plot_cache):
            kind = spec[0]
            if kind == "curve":
                _, _, x, y = spec
                _, curve, _plot = cached
                try:
                    curve.setData(x, y)
                except Exception:
                    # fallback: if something about the curve broke, force rebuild next time
                    self._auto_plot_signature = None
            else:
                _, _, img = spec
                _, img_item, _plot = cached
                try:
                    img_item.setImage(img, autoLevels=False)
                except Exception:
                    self._auto_plot_signature = None

        self.labels_added = True

    def auto_plot_plot(self, prepared_data):
        """
        Auto plots data using pyqtgraph with proper plot tracking.
        """
        # Create line plots
        if "plots" in prepared_data:
            for i, plot in enumerate(prepared_data["plots"]):
                p = self.plot_widget.ci.addPlot(title=plot["label"])
                p.addLegend()
                p.plot(plot["x"], plot["y"], pen='b', symbol='o', symbolSize=5, symbolBrush='b')
                p.setLabel('bottom', plot["xlabel"])
                p.setLabel('left', plot["ylabel"])
                p.showGrid(x=True, y=True)

                x_min, x_max = min(plot["x"]), max(plot["x"])
                y_min, y_max = min(plot["y"]), max(plot["y"])
                p.setRange(xRange=[x_min, x_max], yRange=[y_min, y_max])

                self.plot_manager.add_pyqtgraph_plot(p)
                self.plot_widget.nextRow()

        # Create image plots
        if "images" in prepared_data:
            for i, img in enumerate(prepared_data["images"]):
                p = self.plot_widget.ci.addPlot(title=img["label"])
                p.setLabel('bottom', img["xlabel"])
                p.setLabel('left', img["ylabel"])
                p.showGrid(x=True, y=True)

                image_item = pg.ImageItem(np.flipud(img["data"].T))
                p.addItem(image_item)
                color_map = pg.colormap.get(img["colormap"])
                image_item.setLookupTable(color_map.getLookupTable())

                color_bar = pg.ColorBarItem(values=(image_item.image.min(), image_item.image.max()),
                                            colorMap=color_map)
                color_bar.setImageItem(image_item, insert_in=p)

                self.plot_manager.add_pyqtgraph_plot(p)
                if len(self.plot_manager.get_pyqtgraph_plots()) % 2 == 0:
                    self.plot_widget.nextRow()

        # Create column plots
        if "columns" in prepared_data:
            for i, column in enumerate(prepared_data["columns"]):
                x_data = column["data"][:, 0]
                y_data = column["data"][:, 1]

                p = self.plot_widget.ci.addPlot(title=column["label"])
                p.setLabel('bottom', column["xlabel"])
                p.setLabel('left', column["ylabel"])
                p.showGrid(x=True, y=True)

                p.plot(x_data, y_data, pen=None, symbol='o', symbolSize=5, symbolBrush='b')

                self.plot_manager.add_pyqtgraph_plot(p)
                if len(self.plot_manager.get_pyqtgraph_plots()) % 2 == 0:
                    self.plot_widget.nextRow()

    # =========================================================================
    # DATASET LOADING
    # =========================================================================

    def load_dataset_file(self, dataset_file):
        """Takes the dataset file and loads the dict, before calling the plotter."""
        self.data = Helpers.h5_to_dict(dataset_file)

        # Extracting the Config
        if "config" in self.data:
            qInfo("Config in h5 metadata found")
            temp_config = self.data["config"]
            self.experiment_config_panel.update_config_dict(temp_config, reset=True)
            self.data.pop("config")
        else:
            qDebug("No config in metadata found")

        self.plot_data()

    # =========================================================================
    # FITTING METHODS
    # =========================================================================

    def perform_fit(self):
        """
        Performs fitting on the current plots based on fit_combo selection.
        Handles both 1D line plots and 2D image data in both backends.
        """
        fit_model = self.fit_combo.currentText()

        if fit_model == "None":
            qInfo("No fitting model selected")
            return

        # Check which rendering mode is active
        if self.use_matplotlib_checkbox.isChecked():
            self.perform_fit_matplotlib(fit_model)
        else:
            self.perform_fit_pyqtgraph(fit_model)

    def perform_fit_pyqtgraph(self, fit_model: str):
        """Performs fitting on PyQtGraph plots with plot_manager."""
        plots = self.plot_manager.get_pyqtgraph_plots()

        if not plots:
            qWarning("No plots available to fit")
            return

        # Clear previous fit overlays
        self.clear_fit_overlays()

        qInfo(f"Performing fit with model: {fit_model}")

        fit_count = 0
        for plot_idx, plot in enumerate(plots):
            # Check if this is a 2D image plot or 1D line plot
            has_image = any(isinstance(item, pg.ImageItem) for item in plot.items)

            if has_image:
                # Handle 2D fitting
                result = self.fit_2d_plot(plot, fit_model)
                if result and result.get("success"):
                    fit_count += 1
                    self.display_2d_fit_results(result)

                    if result.get("fit_performed"):
                        self.overlay_chevron_fit_on_pyqtgraph(plot, result)
            else:
                # Handle 1D fitting
                x_data, y_data = self.extract_plot_data(plot)

                if x_data is not None and y_data is not None and len(x_data) > 3:
                    # Perform fit
                    if fit_model == "Auto":
                        result = self.fit_manager.fit_1d(x_data, y_data, model_name="Auto")
                    else:
                        result = self.fit_manager.fit_1d(x_data, y_data, model_name=fit_model)

                    if result.success:
                        qInfo(f"Fit successful on plot {plot_idx}: {result.model_name}, R^2={result.r_squared:.4f}")
                        self.fit_results.append(result)

                        # Overlay fit on plot
                        self.overlay_fit_on_plot(plot, result)
                        fit_count += 1

                        # Display fit parameters
                        self.display_fit_results(result)
                    else:
                        qWarning(f"Fit failed on plot {plot_idx}: {result.message}")

        if fit_count > 0:
            self.fit_button.setText('Done!')
            QTimer.singleShot(2000, lambda: self.fit_button.setText('Fit'))
            qInfo(f"Successfully fitted {fit_count} plot(s)")
        else:
            qWarning("No fits were successful")

    def perform_fit_matplotlib(self, fit_model: str):
        """Performs fitting on matplotlib plots with plot_manager."""
        canvases = self.plot_manager.get_matplotlib_canvases()

        if not canvases:
            qWarning("No matplotlib plots available to fit")
            return

        # Clear previous fit overlays
        self.clear_fit_overlays()

        qInfo(f"Performing matplotlib fit with model: {fit_model}")

        figures = self.plot_manager.get_matplotlib_figures()

        if not figures:
            qWarning("No matplotlib figures found")
            return

        fit_count = 0

        for fig_idx, fig in enumerate(figures):
            for ax_idx, ax in enumerate(fig.get_axes()):

                # Check for 2D image data
                if ax.get_images():
                    qInfo(f"Found 2D image in figure {fig_idx}, axis {ax_idx}")
                    result = self.fit_2d_matplotlib(ax, fit_model)
                    if result and result.get("success"):
                        fit_count += 1
                        self.display_2d_fit_results(result)

                        if result.get("fit_performed"):
                            self.overlay_chevron_fit_on_matplotlib(ax, result)

                # Check for 1D line data
                elif ax.get_lines():
                    qInfo(f"Found {len(ax.get_lines())} line(s) in figure {fig_idx}, axis {ax_idx}")

                    # Get the first line (main data, not fits)
                    lines = [line for line in ax.get_lines() if line.get_linestyle() != '--']

                    if not lines:
                        continue

                    line = lines[0]
                    x_data = line.get_xdata()
                    y_data = line.get_ydata()

                    if x_data is not None and y_data is not None and len(x_data) > 3:
                        # Perform fit
                        if fit_model == "Auto":
                            result = self.fit_manager.fit_1d(x_data, y_data, model_name="Auto")
                        else:
                            result = self.fit_manager.fit_1d(x_data, y_data, model_name=fit_model)

                        if result.success:
                            qInfo(f"Fit successful: {result.model_name}, R^2={result.r_squared:.4f}")
                            self.fit_results.append(result)

                            # Overlay fit on matplotlib axis
                            self.overlay_fit_on_matplotlib(ax, result)
                            fit_count += 1

                            # Display fit parameters
                            self.display_fit_results(result)
                        else:
                            qWarning(f"Fit failed: {result.message}")

        # Redraw all matplotlib canvases to show the overlaid fits
        for canvas in canvases:
            try:
                canvas.draw()
            except Exception as e:
                qWarning(f"Failed to redraw canvas: {str(e)}")

        if fit_count > 0:
            self.fit_button.setText('Done!')
            QTimer.singleShot(2000, lambda: self.fit_button.setText('Fit'))
            qInfo(f"Successfully fitted {fit_count} plot(s)")
        else:
            qWarning("No fits were successful")

    def fit_2d_matplotlib(self, ax, fit_model: str) -> Optional[Dict]:
        """Fit 2D image data in a matplotlib axis (e.g., chevron pattern)."""
        try:
            images = ax.get_images()
            if not images:
                return None

            img = images[0]
            data = img.get_array()

            # Try to get extent information for axes
            extent = img.get_extent()

            if extent:
                left, right, bottom, top = extent
                ny, nx = data.shape
                x_axis = np.linspace(left, right, nx)
                y_axis = np.linspace(bottom, top, ny)
            else:
                # Fallback to pixel coordinates
                ny, nx = data.shape
                x_axis = np.arange(nx)
                y_axis = np.arange(ny)

            qInfo(f"2D matplotlib data shape: {data.shape}, "
                  f"x range: [{x_axis[0]:.3f}, {x_axis[-1]:.3f}], "
                  f"y range: [{y_axis[0]:.3f}, {y_axis[-1]:.3f}]")

            # Perform 2D analysis
            if fit_model == "Auto":
                result = self.fit_manager.analyze_2d(data, method_name="Auto",
                                                     x_axis=x_axis, y_axis=y_axis, do_fit=True)
            elif fit_model == "Chevron Pattern":
                result = self.fit_manager.analyze_2d(data, method_name="Chevron Pattern",
                                                     x_axis=x_axis, y_axis=y_axis, do_fit=True)
            else:
                qWarning(f"2D analysis not available for model: {fit_model}")
                return None

            return result

        except Exception as e:
            qCritical(f"2D matplotlib fitting failed: {str(e)}")
            traceback.print_exc()
            return None

    def fit_2d_plot(self, plot, fit_model: str) -> Optional[Dict]:
        """Fit 2D image data in PyQtGraph plot."""
        try:
            # Extract ImageItem
            image_items = [item for item in plot.items if isinstance(item, pg.ImageItem)]
            if not image_items:
                return None

            img_item = image_items[0]
            data = img_item.image.T

            # Try to get real axis values from data dictionary
            x_axis_data, y_axis_data = self.try_extract_axes_from_data()

            if x_axis_data is not None and y_axis_data is not None:
                qInfo(f"Using axis data from self.data")
                x_axis = x_axis_data
                y_axis = y_axis_data
            else:
                # Fallback to pixel coordinates
                qInfo("No axis data found, using pixel coordinates")
                rect = img_item.boundingRect()
                x_min, x_max = rect.left(), rect.right()
                y_min, y_max = rect.top(), rect.bottom()

                ny, nx = data.shape
                x_axis = np.linspace(x_min, x_max, nx)
                y_axis = np.linspace(y_min, y_max, ny)

            qInfo(f"2D data shape: {data.shape}, x range: [{x_axis[0]:.3f}, {x_axis[-1]:.3f}], "
                  f"y range: [{y_axis[0]:.3f}, {y_axis[-1]:.3f}]")

            # Perform 2D analysis
            if fit_model == "Auto":
                result = self.fit_manager.analyze_2d(data, method_name="Auto",
                                                     x_axis=x_axis, y_axis=y_axis, do_fit=True)
            elif fit_model == "Chevron Pattern":
                result = self.fit_manager.analyze_2d(data, method_name="Chevron Pattern",
                                                     x_axis=x_axis, y_axis=y_axis, do_fit=True)
            else:
                qWarning(f"2D analysis not available for model: {fit_model}")
                return None

            return result

        except Exception as e:
            qCritical(f"2D fitting failed: {str(e)}")
            traceback.print_exc()
            return None

    def display_2d_fit_results(self, result: Dict):
        """Display 2D fit results (e.g., chevron parameters)."""
        if not result.get("success"):
            qWarning(f"2D analysis unsuccessful: {result.get('message')}")
            return

        qInfo(f"2D Analysis Result: {result.get('pattern_type', 'Unknown')}")
        if result.get("fit_performed"):
            g = result.get("coupling_g")
            delta0 = result.get("center_detuning")
            qInfo(f"Coupling g: {g:.3e}, Center detuning: {delta0:.3f}")

    def try_extract_axes_from_data(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Try to extract x and y axis arrays from self.data for 2D fitting."""
        if self.data is None:
            return None, None

        data_dict = self.data.get('data', self.data) if isinstance(self.data, dict) else {}

        # Common x-axis names
        x_keys = ['times', 'time', 'pulse_lengths', 'pulse_length', 'x_pts', 'x_axis', 'x', 'expt_samples']
        # Common y-axis names
        y_keys = ['gains', 'gain', 'detunings', 'detuning', 'frequencies', 'frequency', 'y_pts', 'y_axis', 'y',
                  'Gain_Expt', 'Gain_BS']

        x_axis = None
        y_axis = None

        for key in x_keys:
            if key in data_dict:
                try:
                    x_axis = np.array(data_dict[key])
                    qInfo(f"Found x-axis: {key}, shape: {x_axis.shape}")
                    break
                except:
                    pass

        for key in y_keys:
            if key in data_dict:
                try:
                    y_axis = np.array(data_dict[key])
                    qInfo(f"Found y-axis: {key}, shape: {y_axis.shape}")
                    break
                except:
                    pass

        return x_axis, y_axis

    def extract_plot_data(self, plot) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Extract x and y data from a PyQtGraph plot."""
        try:
            items = [item for item in plot.items if isinstance(item, pg.PlotDataItem)]

            if not items:
                return None, None

            item = items[0]
            x_data = item.xData
            y_data = item.yData

            if x_data is not None and y_data is not None:
                return np.array(x_data), np.array(y_data)

        except Exception as e:
            qWarning(f"Failed to extract plot data: {str(e)}")

        return None, None

    def on_matplotlib_toggled(self):
        if self.use_matplotlib_checkbox.isChecked():
            self.coord_label.hide()
        else:
            self.coord_label.show()

    def overlay_fit_on_matplotlib(self, ax, fit_result: FitResult):
        """Overlay the fitted curve on a matplotlib axis."""
        try:
            if fit_result.fit_data.size == 0:
                qWarning("No fit data to overlay")
                return

            x_fit = fit_result.fit_data[:, 0]
            y_fit = fit_result.fit_data[:, 1]

            # Add fit curve with distinct style
            line, = ax.plot(x_fit, y_fit, 'r--', linewidth=2.5,
                            label=f'{fit_result.model_name} Fit (RÂ²={fit_result.r_squared:.3f})',
                            zorder=10)

            # Store reference for later removal
            self.fit_overlays.append(line)

            # Update or add legend
            handles, labels = ax.get_legend_handles_labels()
            if labels:
                ax.legend(loc='best', framealpha=0.9, fontsize='small')

            qInfo(f"Overlaid fit curve for {fit_result.model_name}")

        except Exception as e:
            qCritical(f"Failed to overlay fit on matplotlib: {str(e)}")
            traceback.print_exc()

    def overlay_fit_on_plot(self, plot, fit_result: FitResult):
        """Overlay the fitted curve on a PyQtGraph plot."""
        try:
            if fit_result.fit_data.size == 0:
                return

            x_fit = fit_result.fit_data[:, 0]
            y_fit = fit_result.fit_data[:, 1]

            # Add fit curve with distinct color
            fit_curve = plot.plot(x_fit, y_fit, pen=pg.mkPen(color='r', width=2, style=Qt.DashLine))

            # Store reference
            self.fit_overlays.append(fit_curve)

        except Exception as e:
            qCritical(f"Failed to overlay fit: {str(e)}")

    def clear_fit_overlays(self):
        """
        Clear all fit overlay curves from both PyQtGraph and matplotlib plots.
        """
        # Clear from plot_manager first
        self.plot_manager.clear_fit_overlays()

        # Clear individual overlays
        for overlay in self.fit_overlays:
            try:
                # PyQtGraph overlay
                if hasattr(overlay, 'scene') and overlay.scene() is not None:
                    overlay.scene().removeItem(overlay)
                # Matplotlib line
                elif hasattr(overlay, 'remove'):
                    overlay.remove()
            except Exception as e:
                qWarning(f"Failed to remove overlay: {str(e)}")

        # Redraw matplotlib canvases if in matplotlib mode
        if self.use_matplotlib_checkbox.isChecked():
            for canvas in self.plot_manager.get_matplotlib_canvases():
                try:
                    canvas.draw()
                except Exception as e:
                    qWarning(f"Failed to redraw canvas: {str(e)}")

        self.fit_overlays.clear()
        self.fit_results.clear()

    def display_fit_results(self, fit_result: FitResult):
        """Display fit results in console."""
        result_text = fit_result.format_params()
        qInfo(f"Fit Results:\n{result_text}")

    def overlay_chevron_fit_on_pyqtgraph(self, plot, result: Dict):
        """Overlay chevron fit visualization on a PyQtGraph plot."""
        try:
            if not result.get("fit_performed"):
                qWarning("No chevron fit to overlay")
                return

            # Extract fitted parameters
            g = result.get("coupling_g")
            delta0 = result.get("center_detuning")
            b = result.get("asymmetry_b", 0)

            # Draw horizontal line at center detuning (sweet spot)
            center_line = pg.InfiniteLine(
                pos=delta0,
                angle=0,
                pen=pg.mkPen(color='cyan', width=2, style=Qt.DashLine),
                label=f'Center Î”â‚€={delta0:.3f}',
                labelOpts={'position': 0.70, 'color': 'cyan'}
            )
            plot.addItem(center_line)
            self.fit_overlays.append(center_line)

            qInfo(f"Overlaid chevron fit: g={g:.3e}, delta_0={delta0:.3f}")

        except Exception as e:
            qCritical(f"Failed to overlay chevron fit on PyQtGraph: {str(e)}")
            traceback.print_exc()

    def overlay_chevron_fit_on_matplotlib(self, ax, result: Dict):
        """Overlay chevron fit visualization on a matplotlib axis."""
        try:
            if not result.get("fit_performed"):
                qWarning("No chevron fit to overlay")
                return

            # Extract fitted parameters
            g = result.get("coupling_g")
            delta0 = result.get("center_detuning")
            b = result.get("asymmetry_b", 0)

            # Draw horizontal line at center detuning
            hline = ax.axhline(
                y=delta0,
                color='cyan', linestyle='--', linewidth=2.5,
                label=f'Center Î”â‚€={delta0:.3f}',
                zorder=14
            )
            self.fit_overlays.append(hline)

            # Update legend
            ax.legend(loc='best', framealpha=0.9, fontsize='small', ncol=1)

            qInfo(f"Overlaid chevron fit on matplotlib: g={g:.3e}, Delta_0={delta0:.3f}")

        except Exception as e:
            qCritical(f"Failed to overlay chevron fit on matplotlib: {str(e)}")
            traceback.print_exc()

    # =========================================================================
    # DATA HANDLING
    # =========================================================================

    def intermediate_data(self, data, exp_instance):
        """
        Handles intermediate data during acquisition.
        """
        set_num = data["data"]["set_num"]
        inter_data = copy.deepcopy(data)

        if set_num == 0:
            self.data = inter_data

        if self.average_simult_checkbox.isChecked() and self.data is not None and set_num > 0:
            inter_data["data"] = self.recursive_average(self.data["data"], inter_data["data"], set_num)

        self.plot_data(exp_instance, inter_data)

    def process_data(self, data):
        """Processes incoming data from experiments."""
        if "data" not in data or "set_num" not in data["data"]:
            qWarning("Input data must have 'data' key with 'set_num'.")
            self.data = data
        else:
            set_num = data["data"]["set_num"]

            if self.data is None or set_num == 0:
                self.data = data
            else:
                self.data["data"] = self.recursive_average(self.data["data"], data["data"], set_num)

    def recursive_average(self, current, new, set_num):
        """
        Recursively averages dictionary data, ignoring NaN values.
        """
        # Handle scalars
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
                np.isnan(new),
                current,
                np.where(
                    np.isnan(current),
                    new,
                    (current * (set_num) + new) / (set_num + 1)
                )
            )

        # Handle dictionaries
        elif isinstance(new, dict):
            return {
                k: (v if k == "set_num" else self.recursive_average(current.get(k, None), v, set_num))
                for k, v in new.items()
            }

        else:
            qWarning(f"Unsupported data type: {type(new)}")

    # =========================================================================
    # UI INTERACTION
    # =========================================================================

    def update_coordinates(self, pos):
        """
        Updates the coordinates label with plot_manager.
        """

        if not self.use_matplotlib_checkbox.isChecked():

            # Find the active plot
            for plot in self.plot_manager.get_pyqtgraph_plots():
                vb = plot.vb
                if plot.sceneBoundingRect().contains(pos):
                    self.plot_widget.setCursor(Qt.CrossCursor)
                    mouse_point = vb.mapSceneToView(pos)
                    x, y = mouse_point.x(), mouse_point.y()

                    # Try to find an ImageItem for color data
                    image_items = [item for item in plot.items if isinstance(item, pg.ImageItem)]
                    if image_items:
                        img_item = image_items[0]
                        image = img_item.image.T
                        if image is not None:
                            # Map view coordinates to array indices
                            transform = img_item.transform()
                            inv_transform = transform.inverted()[0]
                            mapped = inv_transform.map(mouse_point)

                            ix, iy = int(mapped.x()), int(mapped.y())
                            if 0 <= ix < image.shape[1] and 0 <= iy < image.shape[0]:
                                value = image[iy, ix]
                                self.coord_label.setText(f"X: {x:.4f} Y: {y:.4f} Val: {value:.4f}")
                                return

                    self.coord_label.setText(f"X: {x:.4f} Y: {y:.4f}")
                    return

    # =========================================================================
    # EXPERIMENT MANAGEMENT
    # =========================================================================

    def reExtract_experiment(self):
        """ReExtracts the current experiment to reflect code changes."""
        if self.experiment_obj is not None:
            self.experiment_obj.load_module_and_class()

            if self.experiment_obj is not None and self.experiment_obj.experiment_hardware_req is not None:
                hardware_str = "[" + (
                    ", ".join(cls.__name__ for cls in self.experiment_obj.experiment_hardware_req)) + "]"
                self.hardware_label.setText("Hardware: " + hardware_str)

            qDebug("ReExtracted Experiment: experiment attributes extracted.")
            self.updated_tab.emit()

            self.reExtract_experiment_button.setText('Done!')
            QTimer.singleShot(3000, lambda: self.reExtract_experiment_button.setText('ReExtract'))

    def predict_runtime(self, config):
        """Predicts the runtime if estimate_runtime method is provided."""
        if self.experiment_obj.experiment_runtime_estimator is not None:
            flattened_config = config.copy()
            time_delta = self.experiment_obj.experiment_runtime_estimator(flattened_config)
            self.update_runtime_estimation(time_delta, 0)

    def update_runtime_estimation(self, time_delta, set_num):
        """Updates the estimated runtime and endtime."""
        total_sets = 1
        if "sets" in self.experiment_config_panel.config:
            total_sets = self.experiment_config_panel.config["sets"]
        sets_left = total_sets - set_num

        runtime_estimate = time_delta * total_sets
        runtime_string = Helpers.format_time_duration_pretty(runtime_estimate)

        leftover_runtime_estimate = (time_delta * sets_left)
        leftover_runtime_string = Helpers.format_time_duration_pretty(leftover_runtime_estimate)

        end_time = datetime.datetime.now() + datetime.timedelta(seconds=leftover_runtime_estimate)
        end_time_string = end_time.strftime("%H:%M:%S")

        self.runtime_label.setText("Estimated Runtime: " + runtime_string)
        self.endtime_label.setText("End: " + end_time_string + " (" + leftover_runtime_string + ")")

    def update_data(self, data, exp_instance):
        """
        Slot for the emission of data from the experiment thread.
        Calls the methods to process and plot the data.
        """
        self.exp_instance = exp_instance
        self.process_data(data)
        self.plot_data(exp_instance)
        self.save_data()

    def replot_data(self):
        """Function called when RePlot button pressed."""
        self.clear_plots()
        if hasattr(self, "exp_instance"):
            self.plot_data(self.exp_instance)
        else:
            self.plot_data()

    # =========================================================================
    # DATA EXPORT
    # =========================================================================

    def export_data(self):
        """Called when the export button clicked."""
        self.prepare_file_naming()
        self.save_data(custom_path=True)

        self.export_data_button.setText('Done!')
        QTimer.singleShot(3000, lambda: self.export_data_button.setText('Export'))

    def prepare_file_naming(self):
        """Prepares naming conventions with experiment type and timestamps."""
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
        h5, json, and PNG.
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
                        # Capture the appropriate plot widget
                        if self.use_matplotlib_checkbox.isChecked():
                            pixmap = self.matplotlib_container.grab()
                        else:
                            pixmap = self.plot_widget.grab()
                        file_path = os.path.join(folder_path, self.file_name + ".png")
                        pixmap.save(file_path)
                        qInfo("Saved dataset to " + str(folder_path))
                    except Exception as e:
                        qCritical(f"Failed to save the dataset to {file_path}: {str(e)}")
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

            # Make directories if they don't exist
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
                        self.last_run_experiment_config,
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
                if self.use_matplotlib_checkbox.isChecked():
                    pixmap = self.matplotlib_container.grab()
                else:
                    pixmap = self.plot_widget.grab()
                pixmap.save(image_filename, "PNG")
            except Exception as e:
                qCritical(f"Failed to save the plot image to {image_filename}: {str(e)}")

            qDebug("Data export attempted at " + date_time_string +
                   " to: " + folder_path + "/" + self.tab_name + "/" + self.folder_name)

    def backup_exporter(self, data_filename):
        """
        Backup exporter used if no custom exporter is provided.
        """
        data_file = h5py.File(data_filename, 'w')

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

                # If datum is still a list of arrays, pad it
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