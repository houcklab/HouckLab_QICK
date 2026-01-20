"""
=============
DesqTabAdv.py
=============
The custom QDesqTab class for the central tabs module of the main application.

SIMPLIFIED PLOTTING ARCHITECTURE:
- Experiments plot via their `display()` method only
- No plotter-selection UI or logic
- Loaded datasets use auto-plotting
- Single, clear plotting entry point

FIGURE CAROUSEL WITH STACKED WIDGETS:
- When multiple matplotlib figures are generated, thumbnails appear in a carousel
- Each figure gets PERSISTENT plot widgets (both matplotlib and pyqtgraph versions)
- Widgets are stored in QStackedWidgets for instant switching
- Clicking a thumbnail just changes the stack index - NO re-rendering
- This eliminates geometry instability and enables proper live plotting

STACKED WIDGET STRUCTURE:
- plot_stack: Main switcher between modes
  - Index 0: pyqtgraph_stack (contains all PyQtGraph GraphicsLayoutWidgets)
  - Index 1: matplotlib_stack (contains all Matplotlib FigureCanvas containers)
- Each sub-stack:
  - Index 0: Default placeholder widget ("Nothing to plot")
  - Index 1+: One widget per figure from the carousel

LIVE PLOTTING:
- Live updates modify data on the EXISTING persistent widgets
- No widget recreation or re-rendering on data updates
- Proper tracking of which figure is being updated

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

from PyQt5.QtGui import QKeySequence, QCursor, QImage, QPixmap, QColor, QPainter, QPen
from PyQt5.QtCore import (
    Qt, QSize, qCritical, qInfo, qDebug, QRect, QTimer, QEvent,
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
    QFrame,
)
import pyqtgraph as pg
from matplotlib.collections import PathCollection
from matplotlib.patches import Rectangle

from MasterProject.Client_modules.Desq_GUI.scripts.ConfigTreePanelAdv import QConfigTreePanel
from MasterProject.Client_modules.Desq_GUI.scripts.ExperimentObject import ExperimentObject
import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers
from MasterProject.Client_modules.Desq_GUI.scripts.SmartFitter import FitManager, FitResult
from MasterProject.Client_modules.Desq_GUI.scripts.FigureCarousel import FigureCarousel


# =============================================================================
# Plot Tracking Data Structures
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

    FIGURE CAROUSEL:
    - Shows thumbnails of all matplotlib figures generated
    - Allows switching between figures without re-running
    - Cleared on each new run to prevent cross-run mixing
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
        self.splitter.setOpaqueResize(False)
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

        self.reExtract_experiment_button = Helpers.create_button("Sync Experiment", "reExtract_experiment_button",
                                                                 False,
                                                                 self.plot_utilities_container)
        self.reExtract_experiment_button.setToolTip("Syncs extracted experiment file to reflect changes to code file")
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
        fixed_spacer = QSpacerItem(20, 30, QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.plot_utilities.addWidget(self.replot_button)
        self.plot_utilities.addWidget(self.snip_plot_button)
        self.plot_utilities.addWidget(self.export_data_button)
        self.plot_utilities.addItem(fixed_spacer)
        self.plot_utilities.addWidget(self.reExtract_experiment_button)
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

        # Create a stacked widget to switch between PyQtGraph and Matplotlib MODES
        self.plot_stack = QStackedWidget()
        self.plot_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # === PYQTGRAPH MODE (index 0) ===
        # A stacked widget containing multiple GraphicsLayoutWidgets (one per figure)
        self.pyqtgraph_stack = QStackedWidget()
        self.pyqtgraph_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Default PyQtGraph widget for when no figures exist (shows "Nothing to plot")
        self.plot_widget = pg.GraphicsLayoutWidget(self)
        label = self.plot_widget.ci.addLabel("Nothing to plot.", row=0, col=0, colspan=2, size='12pt')
        self.plot_manager.add_pyqtgraph_label(label)
        self.plot_widget.setBackground("w")
        self.plot_widget.ci.setSpacing(2)
        self.plot_widget.ci.setContentsMargins(3, 3, 3, 3)
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_widget.setMinimumSize(QSize(375, 0))
        self.plot_widget.setObjectName("plot_widget")
        self.pyqtgraph_stack.addWidget(self.plot_widget)  # Default at index 0

        # Track PyQtGraph widgets: list of (GraphicsLayoutWidget, axes_map) per figure
        self._pyqtgraph_figure_widgets: List[Tuple[pg.GraphicsLayoutWidget, List]] = []

        # === MATPLOTLIB MODE (index 1) ===
        # A stacked widget containing multiple FigureCanvas containers (one per figure)
        self.matplotlib_stack = QStackedWidget()
        self.matplotlib_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Default matplotlib container for when no figures exist
        self.matplotlib_container = QWidget()
        self.matplotlib_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.matplotlib_layout = QVBoxLayout(self.matplotlib_container)
        self.matplotlib_layout.setContentsMargins(0, 0, 0, 0)
        self.matplotlib_layout.setSpacing(5)
        # Add placeholder label
        placeholder = QLabel("Nothing to plot.")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("font-size: 12pt; color: #666;")
        self.matplotlib_layout.addWidget(placeholder)
        self.matplotlib_stack.addWidget(self.matplotlib_container)  # Default at index 0

        # Track matplotlib figure widgets: list of (container_widget, FigureCanvas, toolbar) per figure
        self._matplotlib_figure_widgets: List[Tuple[QWidget, FigureCanvas, NavigationToolbar]] = []

        # Matplotlib resize/relayout support
        self._mpl_in_relayout = False

        # Add both mode stacks to the main plot_stack
        self.plot_stack.addWidget(self.pyqtgraph_stack)  # Index 0 = PyQtGraph mode
        self.plot_stack.addWidget(self.matplotlib_stack)  # Index 1 = Matplotlib mode
        self.plot_stack.setCurrentIndex(0)  # Start with PyQtGraph

        self.plot_layout.addWidget(self.plot_stack)

        # === FIGURE CAROUSEL ===
        # Add carousel below plot_stack for multi-figure navigation
        self.figure_carousel = FigureCarousel(self)
        self.figure_carousel.figure_selected.connect(self._on_carousel_figure_selected)
        self.plot_layout.addWidget(self.figure_carousel)

        # Track carousel-related state
        self._carousel_figures: List[Any] = []  # Figures managed by carousel
        self._displayed_figure_index: int = -1  # Currently displayed figure
        self._run_figure_count: int = 0  # Track figures in current run

        # SESSION-BASED PLOT ISOLATION
        # Each run/replot increments this ID. Figures from old sessions are rejected.
        self._plot_session_id: int = 0

        # PLOT SLOT SNAPSHOT (for fixed-size, aspect-preserving plotting)
        # The plot area (width/height) is snapshotted at the START of each run/replot session.
        # Plots are then rendered at a fixed maximum size that preserves the original figure aspect.
        # GUI resizing does NOT resize the plots unless a new session is started (Run/RePlot).
        self._plot_slot_snapshot_px: Optional[Tuple[int, int]] = None

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
            # Grab from the current matplotlib stack widget
            current_idx = self.matplotlib_stack.currentIndex()
            widget = self.matplotlib_stack.widget(current_idx)
            if widget:
                pixmap = widget.grab()
            else:
                pixmap = self.matplotlib_stack.grab()
        else:
            # Grab from the current pyqtgraph stack widget
            current_idx = self.pyqtgraph_stack.currentIndex()
            widget = self.pyqtgraph_stack.widget(current_idx)
            if widget:
                pixmap = widget.grab()
            else:
                pixmap = self.pyqtgraph_stack.grab()

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

        CRITICAL: Also clears the figure carousel to prevent cross-run mixing.
        """
        qInfo(f"Clearing all plots for tab: {self.tab_name}...")

        # Use plot_manager for thread-safe cleanup of the default widgets
        self.plot_manager.clear_all(self.plot_widget, self.matplotlib_layout)

        # === CLEAR STACKED PYQTGRAPH FIGURE WIDGETS ===
        # Remove all figure widgets from the pyqtgraph stack (keep index 0 = default widget)
        while self.pyqtgraph_stack.count() > 1:
            widget = self.pyqtgraph_stack.widget(1)
            self.pyqtgraph_stack.removeWidget(widget)
            widget.deleteLater()
        self._pyqtgraph_figure_widgets.clear()
        self.pyqtgraph_stack.setCurrentIndex(0)  # Show default "Nothing to plot"

        # Reset the default PyQtGraph widget to show placeholder
        self.plot_widget.ci.clear()
        label = self.plot_widget.ci.addLabel("Nothing to plot.", row=0, col=0, colspan=2, size='12pt')
        self.plot_manager.add_pyqtgraph_label(label)

        # === CLEAR STACKED MATPLOTLIB FIGURE WIDGETS ===
        # Remove all figure widgets from the matplotlib stack (keep index 0 = default widget)
        while self.matplotlib_stack.count() > 1:
            widget = self.matplotlib_stack.widget(1)
            self.matplotlib_stack.removeWidget(widget)
            widget.deleteLater()
        self._matplotlib_figure_widgets.clear()
        self.matplotlib_stack.setCurrentIndex(0)  # Show default placeholder

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

        # === CLEAR FIGURE CAROUSEL ===
        # Critical: close figures AND clear carousel to prevent cross-run mixing
        # Pass close_figures=True to remove from matplotlib's global registry
        self.figure_carousel.clear(close_figures=True)
        self._carousel_figures.clear()
        self._displayed_figure_index = -1

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
        # FIXED: Check the new stacked widget lists, not the old plot_manager lists
        if self.use_matplotlib_checkbox.isChecked():
            # Check both old plot_manager AND new stacked widget lists
            has_matplotlib = (len(self.plot_manager.matplotlib_figures) > 0 or
                              len(self._matplotlib_figure_widgets) > 0 or
                              len(self._carousel_figures) > 0)
            if not has_matplotlib:
                self.clear_plots()
        else:
            # Check both old plot_manager AND new stacked widget lists
            has_pyqtgraph = (len(self.plot_manager.get_pyqtgraph_plots()) > 0 or
                             len(self._pyqtgraph_figure_widgets) > 0 or
                             len(self._carousel_figures) > 0)
            if not has_pyqtgraph:
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
        Attempt to call the experiment's display() method and capture any figures it creates.

        This method:
        1. Records existing figure numbers BEFORE calling display()
        2. Calls display()
        3. Identifies NEW figures created during display()
        4. Passes new figures to receive_figure() for carousel handling

        Returns True if display() was called successfully, False otherwise.
        """
        import matplotlib.pyplot as plt

        try:
            # Check if exp_instance has an overridden display() method
            if not hasattr(exp_instance, "display"):
                return False

            display_method = getattr(exp_instance, "display")
            if not callable(display_method):
                return False

            # Check if display() is overridden (not the base ExperimentClass.display)
            for cls in type(exp_instance).__mro__[1:]:
                if "display" in cls.__dict__:
                    parent_method = cls.__dict__["display"]
                    break
            else:
                parent_method = None

            # If display is not overridden, use auto_plot
            if parent_method is not None and display_method.__func__ is parent_method:
                return False

            # Record existing figure numbers BEFORE calling display()
            existing_fig_nums = set(plt.get_fignums())

            # Call display() - this may create new matplotlib figures
            exp_instance.display(data_to_plot, plotDisp=True)

            # Find NEW figures created during display()
            new_fig_nums = set(plt.get_fignums()) - existing_fig_nums

            if new_fig_nums:
                print(f"[{self.tab_name}] display() created {len(new_fig_nums)} new figure(s)")

                # Get the actual figure objects and pass to receive_figure
                # Use session_id=-1 to indicate "trusted" (GUI-thread origin)
                for fig_num in sorted(new_fig_nums):
                    fig = plt.figure(fig_num)
                    self.receive_figure(fig, 'draw', session_id=-1)
            else:
                # display() didn't create new figures - maybe it updated existing ones
                # or used some other mechanism. That's fine.
                print(f"[{self.tab_name}] display() called but no new figures created")

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

        DEPRECATED: Deep copying via pickle is unreliable with Qt canvases.
        This method now just returns the original figure.
        Use isolate_matplotlib_figures() which detaches from the global registry instead.
        """
        qWarning("_copy_matplotlib_figure is deprecated - use registry detachment instead")
        return original_fig

    def _detach_figure_from_registry(self, fig):
        """
        Remove a figure from matplotlib's global registry WITHOUT closing it.

        This prevents future plt.figure(N) calls from returning this figure,
        while keeping the figure object fully functional for display.

        The figure remains valid and renderable - we just remove matplotlib's
        reference to it so it won't be affected by global state operations.
        """
        import matplotlib.pyplot as plt
        from matplotlib._pylab_helpers import Gcf

        try:
            fig_num = fig.number
            # Remove from Gcf (the global figure manager)
            if Gcf.figs.get(fig_num) is not None:
                del Gcf.figs[fig_num]
                qInfo(f"Detached figure {fig_num} from matplotlib registry")

            # Clear the figure's number so it won't be found by get_fignums()
            # But keep it as an attribute so we can reference it for debugging
            fig._detached_number = fig_num
            fig.number = None  # This makes it "orphaned" from matplotlib's perspective

            return True
        except Exception as e:
            qWarning(f"Failed to detach figure from registry: {e}")
            return False

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

        SIMPLIFIED APPROACH:
        Instead of deep-copying figures (which fails with Qt canvases), we simply
        remove them from matplotlib's global registry. The figures remain fully
        functional for display - we just prevent them from being returned by
        future plt.figure(N) calls.

        This is safe because:
        1. We hold direct Python references to the figure objects
        2. The Qt canvas widgets hold references to their figures
        3. Removing from registry doesn't invalidate the figure
        """
        if not self._matplotlib_figure_widgets:
            return

        qInfo(f"[{self.tab_name}] Isolating {len(self._matplotlib_figure_widgets)} matplotlib figures...")

        detached_count = 0

        for i, (container, canvas, toolbar) in enumerate(self._matplotlib_figure_widgets):
            try:
                fig = canvas.figure
                if fig is None:
                    continue

                # Simply detach from registry - no copying needed
                if self._detach_figure_from_registry(fig):
                    detached_count += 1

            except Exception as e:
                qWarning(f"Failed to isolate figure {i}: {e}")
                import traceback
                traceback.print_exc()

        qInfo(f"[{self.tab_name}] Figure isolation complete: {detached_count} detached from registry")

    # =========================================================================
    # FIGURE CAROUSEL METHODS
    # =========================================================================

    def start_plot_session(self) -> int:
        """
        Start a new plot session for this tab.

        MUST be called BEFORE starting any experiment or replot operation.
        This is the PRIMARY entry point for session-based isolation.

        Actions:
        1. Increments session_id (invalidates any in-flight figures from old sessions)
        2. Clears all plot state (PlotManager, carousel, signatures)
        3. Closes matplotlib figures from the previous session

        Returns:
            The new session_id to pass to ExperimentThread/PlotSinkManager
        """
        # Increment session ID FIRST - this invalidates any in-flight figures
        self._plot_session_id += 1
        new_session = self._plot_session_id

        # Snapshot the current plot slot size ONCE for this session.
        # Plots will be rendered at a fixed maximum size based on this snapshot,
        # and GUI resizing will not affect plot sizes until a new session starts.
        self._plot_slot_snapshot_px = self._get_plot_slot_size_px()

        print(f"[{self.tab_name}] Starting plot session {new_session}")

        # Clear all plot state (this also clears carousel and closes figures)
        self.clear_plots()

        return new_session

    def get_plot_session_id(self) -> int:
        """Get the current plot session ID for this tab."""
        return self._plot_session_id

    def receive_figure(self, figure, event_type: str = 'draw', session_id: int = -1):
        """
        Receive a figure and add it to this tab's carousel with a PERSISTENT widget.

        STACKED WIDGET ARCHITECTURE:
        - Each figure gets ONE persistent widget (FigureCanvas for matplotlib,
          GraphicsLayoutWidget for PyQtGraph)
        - Widgets are added to stacked containers and NEVER recreated
        - Switching figures is just setCurrentIndex() - no re-rendering

        Args:
            figure: matplotlib Figure object
            event_type: Type of draw event ('draw' or 'draw_idle')
            session_id: Plot session ID. MUST match current session or figure is rejected.
                       Use -1 to bypass validation (for GUI-thread display() calls on current tab).

        Returns:
            True if figure was accepted, False if rejected
        """
        # SESSION VALIDATION
        # session_id of -1 means "trust this figure" (used for GUI-thread display() calls)
        if session_id != -1 and session_id != self._plot_session_id:
            print(f"[{self.tab_name}] REJECTING figure {id(figure)}: "
                  f"session {session_id} != current {self._plot_session_id}")
            return False

        # Validate figure is still valid (not closed)
        import matplotlib.pyplot as plt
        try:
            if figure.number not in plt.get_fignums():
                print(f"[{self.tab_name}] Ignoring closed/invalid figure {id(figure)}")
                return False
        except Exception:
            pass

        print(f"[{self.tab_name}] receive_figure: fig {id(figure)}, "
              f"session={session_id}, event={event_type}")

        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()

        # Check if this figure is already in the carousel
        existing_index = self.figure_carousel.find_figure_index(figure)

        if existing_index >= 0:
            # Figure already exists - this is a LIVE UPDATE
            print(f"[{self.tab_name}] Live update for figure at index {existing_index}")
            self.figure_carousel.update_thumbnail(existing_index, figure)

            # Update the persistent widgets with new data
            self._live_update_figure_widgets(figure, existing_index)
            return True

        # NEW FIGURE - create persistent widgets and add to stacks
        print(f"[{self.tab_name}] Adding new figure to carousel with persistent widgets")

        # Store reference
        self._carousel_figures.append(figure)
        new_index = len(self._carousel_figures) - 1

        # Add to carousel (makes it active by default)
        self.figure_carousel.add_figure(figure, make_active=True)

        # Create PERSISTENT widgets for both modes
        self._create_persistent_matplotlib_widget(figure, new_index)
        self._create_persistent_pyqtgraph_widget(figure, new_index)

        # Display the new figure (just switch stack index)
        self._displayed_figure_index = new_index
        self._switch_to_figure(new_index)

        print(f"[{self.tab_name}] Now showing figure {new_index + 1} of {len(self._carousel_figures)}")
        return True

    def _create_persistent_matplotlib_widget(self, fig, figure_index: int):
        """
        Create a PERSISTENT matplotlib widget for a figure and add to the stack.

        This widget is created ONCE and never recreated. Switching figures
        just changes the stack index.

        CRITICAL: We preserve the BackendDesq canvas after creating the Qt canvas
        so that live updates still trigger sink notifications.
        """
        # Store original figure properties
        original_size = fig.get_size_inches()
        original_dpi = fig.get_dpi()

        # Intended aspect ratio from figsize (respect the experiment's original fig aspect)
        aspect = (float(original_size[0]) / float(original_size[1])) if float(original_size[1]) else 1.0

        # Snapshot-based fixed sizing: compute max canvas size that fits the plot slot
        slot_w, slot_h = self._plot_slot_snapshot_px or self._get_plot_slot_size_px()

        # Account for container layout margins + toolbar height + layout spacing
        toolbar_h = 30
        margin_l = margin_r = margin_t = margin_b = 6
        spacing = 4
        overhead_w = margin_l + margin_r
        overhead_h = toolbar_h + margin_t + margin_b + spacing

        max_canvas_w = max(1, int(slot_w) - int(overhead_w))
        max_canvas_h = max(1, int(slot_h) - int(overhead_h))
        target_w, target_h = self._fit_size_keep_aspect(max_canvas_w, max_canvas_h, aspect)

        # Apply tight_layout ONLY if never applied before
        if not hasattr(fig, '_desq_layout_applied'):
            try:
                if not (hasattr(fig, '_layoutgrid') and fig._layoutgrid is not None):
                    for ax in fig.axes:
                        ax.tick_params(labelsize=7)  # tick labels
                        ax.xaxis.label.set_size(8)  # x-label
                        ax.yaxis.label.set_size(8)  # y-label
                        ax.title.set_size(9)  # axes title

                    fig.tight_layout(
                        pad=3,  # overall padding (in font-size units)
                        h_pad=3,  # vertical spacing between subplots
                        w_pad=3,  # horizontal spacing between subplots
                        rect=[0.05, 0.05, 0.95, 0.95]  # fractional figure region to fit into
                    )
                fig._desq_layout_applied = True
            except (ValueError, ZeroDivisionError, Exception) as e:
                print(f"[{self.tab_name}] tight_layout failed: {e}")

        # Restore original size after tight_layout
        fig.set_size_inches(original_size, forward=False)
        fig.set_dpi(original_dpi)

        # CRITICAL: Save the BackendDesq canvas BEFORE creating the Qt canvas
        # FigureCanvas(fig) will replace fig.canvas, but we need to restore it
        # so that live updates from the worker thread still go through BackendDesq
        original_canvas = fig.canvas
        is_backend_desq = getattr(original_canvas, '_is_desq_canvas', False)

        # Create display canvas (this will steal the figure temporarily)
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # CRITICAL: Restore BackendDesq canvas to the figure for live update notifications
        # The Qt canvas will still work for display because it holds a reference to the figure
        if is_backend_desq and original_canvas is not None:
            try:
                fig.set_canvas(original_canvas)
                # Also store reference on the figure so we never lose it
                fig._desq_backend_canvas = original_canvas
                print(f"[{self.tab_name}] Restored BackendDesq canvas for live updates")
            except Exception as e:
                print(f"[{self.tab_name}] Warning: Could not restore BackendDesq canvas: {e}")

        # Store reference to display canvas on the figure for easy access
        fig._desq_display_canvas = canvas

        # Fixed-size canvas: preserve aspect and letterbox within the GUI slot.
        # NOTE: GUI resizing will not resize this canvas until a new plot session starts.
        canvas.setFixedSize(int(target_w), int(target_h))
        canvas.updateGeometry()

        # Sync Matplotlib figure inches to the fixed pixel budget so layout/text sizing is stable.
        try:
            dpi = float(fig.get_dpi() or original_dpi or 100.0)
            fig.set_size_inches(float(target_w) / dpi, float(target_h) / dpi, forward=False)
        except Exception:
            pass

        # Create container widget with toolbar
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        toolbar = NavigationToolbar(canvas, container)
        toolbar.setIconSize(QSize(15, 15))
        toolbar.setStyleSheet(
            "QToolBar { padding: 1px; spacing: 2px; } "
            "QToolButton { margin: 0; padding: 0; }"
        )
        toolbar.setFixedHeight(toolbar_h)

        # Figure label
        layout = QVBoxLayout(container)
        layout.addWidget(toolbar)
        layout.addWidget(canvas, stretch=1, alignment=Qt.AlignCenter)
        layout.setContentsMargins(margin_l, margin_t, margin_r, margin_b)
        layout.setSpacing(spacing)

        # Make the container fixed as well so Qt layouts don't stretch it
        try:
            container.setFixedSize(int(target_w + overhead_w), int(target_h + overhead_h))
        except Exception:
            print(f"[{self.tab_name}] Warning: container sizing failed: {e}")

        # Add to the matplotlib stack
        self.matplotlib_stack.addWidget(container)

        # Track the widget for live updates
        self._matplotlib_figure_widgets.append((container, canvas, toolbar))

        # Initial draw
        canvas.draw_idle()

        print(
            f"[{self.tab_name}] Created persistent matplotlib widget at stack index {self.matplotlib_stack.count() - 1}")

    def _create_persistent_pyqtgraph_widget(self, figure, figure_index: int):
        """
        Create a PERSISTENT PyQtGraph widget for a figure and add to the stack.

        This widget is created ONCE and never recreated. Switching figures
        just changes the stack index.
        """
        # Create a new GraphicsLayoutWidget for this figure
        pg_widget = pg.GraphicsLayoutWidget()
        pg_widget.setBackground("w")
        pg_widget.ci.setSpacing(2)
        pg_widget.ci.setContentsMargins(3, 3, 3, 3)
        # Snapshot-based fixed sizing: preserve original matplotlib figure aspect (figsize)
        try:
            w_in, h_in = figure.get_size_inches()
            aspect = (float(w_in) / float(h_in)) if float(h_in) else 1.0
        except Exception:
            aspect = 1.0

        slot_w, slot_h = self._plot_slot_snapshot_px or self._get_plot_slot_size_px()

        # Account for GraphicsLayoutWidget content margins (3 px each side)
        overhead_w = 6
        overhead_h = 6

        max_w = max(1, int(slot_w) - int(overhead_w))
        max_h = max(1, int(slot_h) - int(overhead_h))
        target_w, target_h = self._fit_size_keep_aspect(max_w, max_h, aspect)

        pg_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        pg_widget.setFixedSize(int(target_w), int(target_h))
        pg_widget.updateGeometry()

        axes = figure.get_axes()
        axes_map = []  # Track (ax_idx, plot_item) for live updates

        if not axes:
            # Empty figure - just show a label
            pg_widget.ci.addLabel(f"Figure {figure_index + 1} (empty)", row=0, col=0, size='12pt')
        else:
            # Detect grid layout from axes positions (including spans)
            grid_layout = self._detect_axes_grid(axes)
            nrows, ncols = grid_layout['nrows'], grid_layout['ncols']
            spans = grid_layout.get('spans', {})

            # Add figure title at row 0
            fig_title = ""
            if figure._suptitle:
                fig_title = figure._suptitle.get_text()
            if not fig_title:
                fig_title = f"Figure {figure_index + 1}"

            pg_widget.ci.addLabel(fig_title, row=0, col=0, colspan=ncols, size='12pt')

            # Process each axis from the grid
            # grid maps (row, col) -> ax_index, where (row, col) is the top-left cell
            for (ax_row, ax_col), ax_idx in grid_layout['grid'].items():
                ax = axes[ax_idx]
                rowspan, colspan = spans.get(ax_idx, (1, 1))

                if self._is_axis_empty(ax):
                    continue

                # Place plot at row+1 (to account for title row)
                plot_row = ax_row + 1

                # Create plot item for this axis with spanning
                plot = self._extract_and_plot_to_widget(pg_widget, ax, plot_row, ax_col, rowspan, colspan)
                if plot is not None:
                    axes_map.append((ax_idx, plot))

        # Add to the pyqtgraph stack
        self.pyqtgraph_stack.addWidget(pg_widget)

        # Track the widget and axes map for live updates
        self._pyqtgraph_figure_widgets.append((pg_widget, axes_map))

        print(
            f"[{self.tab_name}] Created persistent PyQtGraph widget at stack index {self.pyqtgraph_stack.count() - 1}")

    def _extract_and_plot_to_widget(self, pg_widget, ax, row, col, rowspan=1, colspan=1):
        """
        Extract matplotlib axis data and plot in a specific PyQtGraph widget.

        ENHANCED: Now properly handles colors, labels, and legends.

        Returns the PlotItem for tracking live updates.
        """
        if self._is_axis_empty(ax):
            return None

        def mpl_color_to_pg(color):
            if isinstance(color, str):
                rgba = mcolors.to_rgba(color)
            else:
                rgba = color
            return tuple(int(c * 255) for c in rgba[:3])

        # Create PlotItem at the specified position with spanning
        plot = pg_widget.ci.addPlot(row=row, col=col, rowspan=rowspan, colspan=colspan)
        plot.setLabel('bottom', ax.get_xlabel())
        plot.setLabel('left', ax.get_ylabel())

        # Set axis title if present
        ax_title = ax.get_title()
        if ax_title:
            plot.setTitle(ax_title)

        plot.showGrid(x=True, y=True, alpha=0.3)

        # Check if we have any labeled items - must create legend BEFORE adding items
        has_legend_items = False
        for line in ax.get_lines():
            label = line.get_label()
            if label and not label.startswith('_'):
                has_legend_items = True
                break
        if not has_legend_items:
            for collection in ax.collections:
                if isinstance(collection, PathCollection):
                    label = collection.get_label()
                    if label and not label.startswith('_'):
                        has_legend_items = True
                        break

        # Create legend BEFORE adding items (PyQtGraph requires this)
        if has_legend_items:
            legend = plot.addLegend()
            legend.anchor(itemPos=(1, 0), parentPos=(1, 0))

        # Handle line plots with labels
        for line in ax.get_lines():
            x, y = line.get_xdata(), line.get_ydata()
            if x is None or y is None or len(x) == 0:
                continue

            x_arr = np.asarray(x, dtype=float)
            y_arr = np.asarray(y, dtype=float)

            color = mpl_color_to_pg(line.get_color())
            linestyle = line.get_linestyle()

            pen_style = Qt.SolidLine
            if linestyle == '--':
                pen_style = Qt.DashLine
            elif linestyle == ':':
                pen_style = Qt.DotLine
            elif linestyle == '-.':
                pen_style = Qt.DashDotLine

            marker = line.get_marker()
            symbol = None
            if marker == 'o':
                symbol = 'o'
            elif marker == 's':
                symbol = 's'
            elif marker == '^':
                symbol = 't'
            elif marker == 'x':
                symbol = 'x'
            elif marker == '+':
                symbol = '+'
            elif marker == 'd' or marker == 'D':
                symbol = 'd'
            elif marker == 'v':
                symbol = 't1'  # inverted triangle

            # Get label for legend - skip internal matplotlib labels
            label = line.get_label()
            name = label if label and not label.startswith('_') else None

            plot.plot(x_arr, y_arr,
                      pen=pg.mkPen(color=color, width=line.get_linewidth() + 1, style=pen_style),
                      symbol=symbol,
                      symbolSize=line.get_markersize() if marker and marker != 'None' else 5,
                      symbolBrush=color,
                      name=name)  # name is used for legend

        # Handle scatter plots with labels
        for collection in ax.collections:
            if isinstance(collection, PathCollection):
                offsets = collection.get_offsets()
                if len(offsets) == 0:
                    continue

                x = offsets[:, 0]
                y = offsets[:, 1]

                facecolors = collection.get_facecolor()
                if len(facecolors) > 0:
                    color = mpl_color_to_pg(facecolors[0])
                else:
                    color = (0, 0, 255)

                sizes = collection.get_sizes()
                size = np.sqrt(sizes[0]) if len(sizes) > 0 else 5

                # Get label for legend
                label = collection.get_label()
                name = label if label and not label.startswith('_') else None

                plot.plot(x, y, pen=None, symbol='o', symbolSize=size, symbolBrush=color, name=name)

        # Handle bar plots / histograms (Rectangle patches)
        bars = [p for p in ax.patches if isinstance(p, Rectangle)]
        if bars:
            x_vals = []
            heights = []
            widths = []

            for bar in bars:
                x_vals.append(bar.get_x())
                heights.append(bar.get_height())
                widths.append(bar.get_width())

            if x_vals and heights:
                x_arr = np.array(x_vals)
                h_arr = np.array(heights)
                w_arr = np.array(widths)

                # Get bar color
                if bars[0].get_facecolor() is not None:
                    bar_color = mpl_color_to_pg(bars[0].get_facecolor())
                else:
                    bar_color = (70, 130, 180)  # Steel blue default

                # Use BarGraphItem for proper bar rendering
                bar_item = pg.BarGraphItem(
                    x=x_arr + w_arr / 2,  # Center x position
                    height=h_arr,
                    width=w_arr * 0.9,  # Slight gap between bars
                    brush=bar_color
                )
                plot.addItem(bar_item)

        # Handle images
        for img in ax.get_images():
            data = img.get_array()
            if data is None or data.size == 0:
                continue

            if hasattr(data, 'mask'):
                data = np.ma.filled(data.astype(float), np.nan)
            else:
                data = np.asarray(data, dtype=float)

            # Compute valid min/max for levels
            valid_mask = ~np.isnan(data)
            if np.any(valid_mask):
                vmin, vmax = np.nanmin(data), np.nanmax(data)
                if vmin == vmax:
                    vmax = vmin + 1
                display_data = np.where(np.isnan(data), vmin, data)
            else:
                display_data = data
                vmin, vmax = 0, 1

            # PyQtGraph expects data in (width, height) format
            img_item = pg.ImageItem(display_data.T, levels=(vmin, vmax))
            plot.addItem(img_item)

            # Apply colormap
            pg_cmap = None
            try:
                cmap = img.get_cmap()
                if cmap is not None:
                    cmap_name = cmap.name
                    try:
                        pg_cmap = pg.colormap.get(cmap_name)
                        img_item.setLookupTable(pg_cmap.getLookupTable())
                    except:
                        pg_cmap = pg.colormap.get('viridis')
                        img_item.setLookupTable(pg_cmap.getLookupTable())
            except Exception:
                pass

            # Set extent if available
            extent = img.get_extent()
            if extent is not None:
                x0, x1, y0, y1 = extent
                data_h, data_w = display_data.shape

                scale_x = (x1 - x0) / data_w if data_w > 0 else 1.0
                scale_y = (y1 - y0) / data_h if data_h > 0 else 1.0

                from PyQt5.QtGui import QTransform
                transform = QTransform()
                transform.translate(x0, y0)
                transform.scale(scale_x, scale_y)
                img_item.setTransform(transform)

                plot.setXRange(x0, x1, padding=0)
                plot.setYRange(y0, y1, padding=0)

            # Add colorbar if colormap was applied
            if pg_cmap is not None:
                try:
                    colorbar = pg.ColorBarItem(values=(vmin, vmax), colorMap=pg_cmap)
                    colorbar.setImageItem(img_item, insert_in=plot)
                except:
                    pass

        return plot

    def _matplotlib_cmap_to_lut(self, cmap, n=256):
        """Convert a matplotlib colormap to a PyQtGraph lookup table."""
        try:
            lut = np.zeros((n, 4), dtype=np.uint8)
            for i in range(n):
                rgba = cmap(i / (n - 1))
                lut[i] = [int(c * 255) for c in rgba]
            return lut
        except Exception:
            return None

    def _switch_to_figure(self, index: int):
        """
        Switch to display a figure by index.

        STACKED WIDGET: This is just setCurrentIndex() - NO re-rendering!
        """
        if index < 0 or index >= len(self._carousel_figures):
            return

        # Stack indices: 0 = default placeholder, 1+ = actual figures
        stack_index = index + 1  # Offset by 1 because index 0 is the default widget

        if self.use_matplotlib_checkbox.isChecked():
            # Matplotlib mode
            self.plot_stack.setCurrentIndex(1)  # Show matplotlib stack
            if stack_index < self.matplotlib_stack.count():
                self.matplotlib_stack.setCurrentIndex(stack_index)
                print(f"[{self.tab_name}] Switched matplotlib stack to index {stack_index}")
        else:
            # PyQtGraph mode
            self.plot_stack.setCurrentIndex(0)  # Show pyqtgraph stack
            if stack_index < self.pyqtgraph_stack.count():
                self.pyqtgraph_stack.setCurrentIndex(stack_index)
                print(f"[{self.tab_name}] Switched pyqtgraph stack to index {stack_index}")

    def _live_update_figure_widgets(self, figure, figure_index: int):
        """
        Update the persistent widgets for a figure with new data (live plotting).

        This updates data IN PLACE without recreating widgets.
        Handles axes that were empty at creation but now have data.

        Note: The figure's canvas may be BackendDesq (for notifications) while
        we have a separate Qt canvas stored for display. We update the Qt canvas
        directly here.
        """
        # Update matplotlib canvas - this updates the matplotlib display
        if figure_index < len(self._matplotlib_figure_widgets):
            container, display_canvas, toolbar = self._matplotlib_figure_widgets[figure_index]
            try:
                # Force the display canvas to re-render the figure
                # This works even if fig.canvas points to BackendDesq
                display_canvas.draw_idle()
            except Exception as e:
                print(f"[{self.tab_name}] Matplotlib live update failed: {e}")

        # Update pyqtgraph plots - this syncs pyqtgraph display from matplotlib data
        if figure_index < len(self._pyqtgraph_figure_widgets):
            pg_widget, axes_map = self._pyqtgraph_figure_widgets[figure_index]
            axes = figure.get_axes()

            # Create a lookup of which axes already have plots
            tracked_axes = {ax_idx for ax_idx, _ in axes_map}

            print(f"[{self.tab_name}] PyQtGraph live update: {len(axes_map)} tracked plots, {len(axes)} axes")

            # Update existing plots
            for ax_idx, plot in axes_map:
                if ax_idx >= len(axes):
                    continue
                ax = axes[ax_idx]
                self._update_pyqtgraph_plot_data(plot, ax)

            # Check for axes that weren't tracked but now have data
            # This handles the case where an axis was empty at creation time
            # but has data now during a live update
            for ax_idx, ax in enumerate(axes):
                if ax_idx in tracked_axes:
                    continue  # Already tracked

                if not self._is_axis_empty(ax):
                    # This axis has data now but wasn't tracked
                    # We need to add a new plot for it
                    print(f"[{self.tab_name}] Live update: axis {ax_idx} now has data, adding new plot")

                    # Find a position for the new plot (use a simple row layout)
                    # This is a simplified approach - ideally we'd recreate the grid layout
                    new_row = pg_widget.ci.rowCount()
                    plot = self._extract_and_plot_to_widget(pg_widget, ax, new_row, 0)
                    if plot is not None:
                        axes_map.append((ax_idx, plot))
                        # Update the stored axes_map
                        self._pyqtgraph_figure_widgets[figure_index] = (pg_widget, axes_map)

    def _update_pyqtgraph_plot_data(self, plot, ax):
        """
        Update a single PyQtGraph plot with new data from a matplotlib axis.

        Uses listDataItems() for reliable PlotDataItem retrieval.
        Now handles scatter plots (PathCollection) for live updates.
        """
        try:
            def mpl_color_to_pg(color):
                """Convert matplotlib color to PyQtGraph format."""
                if isinstance(color, str):
                    rgba = mcolors.to_rgba(color)
                else:
                    rgba = color
                return tuple(int(c * 255) for c in rgba[:3])

            # Update lines using listDataItems() for reliable access
            try:
                plot_items = plot.listDataItems()
            except:
                plot_items = [item for item in plot.items if isinstance(item, pg.PlotDataItem)]

            lines = ax.get_lines()

            # Separate line items from scatter items
            # Line items have pens, scatter items have pen=None
            line_items = []
            scatter_items = []
            for item in plot_items:
                opts = item.opts
                pen = opts.get('pen')
                # Check if it's a scatter plot (no line)
                if pen is None:
                    scatter_items.append(item)
                elif hasattr(pen, 'style') and pen.style() == Qt.NoPen:
                    scatter_items.append(item)
                else:
                    line_items.append(item)

            # Update line plots
            for i, line in enumerate(lines):
                x, y = line.get_xdata(), line.get_ydata()
                if x is None or y is None:
                    continue

                x_arr = np.asarray(x, dtype=float)
                y_arr = np.asarray(y, dtype=float)

                if len(x_arr) == 0:
                    continue

                if i < len(line_items):
                    try:
                        line_items[i].setData(x_arr, y_arr)
                    except Exception as e:
                        print(f"[LiveUpdate] Failed to update line {i}: {e}")
                else:
                    # Line exists in matplotlib but not in pyqtgraph - add it
                    color = mpl_color_to_pg(line.get_color())
                    label = line.get_label()
                    name = label if label and not label.startswith('_') else None
                    plot.plot(x_arr, y_arr, pen=pg.mkPen(color=color, width=line.get_linewidth() + 1), name=name)

            # =====================================================================
            # FIX: Update scatter plots (PathCollection)
            # =====================================================================
            scatter_collections = [c for c in ax.collections if isinstance(c, PathCollection)]

            for i, collection in enumerate(scatter_collections):
                offsets = collection.get_offsets()
                if len(offsets) == 0:
                    continue

                x = np.asarray(offsets[:, 0], dtype=float)
                y = np.asarray(offsets[:, 1], dtype=float)

                if i < len(scatter_items):
                    try:
                        scatter_items[i].setData(x, y)
                    except Exception as e:
                        print(f"[LiveUpdate] Failed to update scatter {i}: {e}")
                else:
                    # Scatter exists in matplotlib but not in pyqtgraph - add it
                    facecolors = collection.get_facecolor()
                    if len(facecolors) > 0:
                        color = mpl_color_to_pg(facecolors[0])
                    else:
                        color = (0, 0, 255)

                    sizes = collection.get_sizes()
                    size = np.sqrt(sizes[0]) if len(sizes) > 0 else 5

                    # Get label for legend
                    label = collection.get_label()
                    name = label if label and not label.startswith('_') else None

                    plot.plot(x, y, pen=None, symbol='o', symbolSize=size, symbolBrush=color, name=name)

            # Update images
            image_items = [item for item in plot.items if isinstance(item, pg.ImageItem)]
            images = ax.get_images()
            for i, img in enumerate(images):
                data = img.get_array()
                if data is None or data.size == 0:
                    continue
                if i >= len(image_items):
                    continue

                if hasattr(data, 'mask'):
                    data = np.ma.filled(data.astype(float), np.nan)
                else:
                    data = np.asarray(data, dtype=float)

                valid_mask = ~np.isnan(data)
                if np.any(valid_mask):
                    vmin, vmax = np.nanmin(data), np.nanmax(data)
                    if vmin == vmax:
                        vmax = vmin + 1
                    display_data = np.where(np.isnan(data), vmin, data)
                    image_items[i].setImage(display_data.T, levels=(vmin, vmax))

            # Update bar graphs if present
            bar_items = [item for item in plot.items if isinstance(item, pg.BarGraphItem)]
            bars = [p for p in ax.patches if isinstance(p, Rectangle)]
            if bars and bar_items:
                x_vals = [bar.get_x() for bar in bars]
                heights = [bar.get_height() for bar in bars]
                widths = [bar.get_width() for bar in bars]

                if x_vals and heights:
                    x_arr = np.array(x_vals)
                    h_arr = np.array(heights)
                    w_arr = np.array(widths)

                    for bar_item in bar_items:
                        bar_item.setOpts(x=x_arr + w_arr / 2, height=h_arr, width=w_arr * 0.9)

        except Exception as e:
            print(f"PyQtGraph plot data update failed: {e}")
            import traceback
            traceback.print_exc()

    def _refresh_current_display(self):
        """Refresh the currently displayed figure (for live updates)."""
        if self._displayed_figure_index < 0:
            return
        if self._displayed_figure_index >= len(self._carousel_figures):
            return

        fig = self._carousel_figures[self._displayed_figure_index]
        self._live_update_figure_widgets(fig, self._displayed_figure_index)

    def _on_carousel_figure_selected(self, index: int):
        """
        Handle carousel thumbnail click - switch displayed figure.

        STACKED WIDGET: This is just setCurrentIndex() - NO re-rendering!
        """
        if index < 0 or index >= len(self._carousel_figures):
            qWarning(f"Invalid carousel figure index: {index}")
            return

        if index == self._displayed_figure_index:
            return  # Already displaying this figure

        qInfo(f"Switching to figure {index + 1} of {len(self._carousel_figures)}")
        self._displayed_figure_index = index
        self._switch_to_figure(index)

    def _display_figure_for_current_mode(self, figure, index: int):
        """
        Display a figure using the currently selected backend mode.

        STACKED WIDGET: This just switches the appropriate stack index.
        """
        self._switch_to_figure(index)

    def embed_matplotlib_plots(self, *args, **kwargs):
        """
        Embed matplotlib figures in the tab with carousel support.

        STACKED WIDGET ARCHITECTURE:
        - Each figure gets a persistent widget in the matplotlib stack
        - Switching figures is just setCurrentIndex() - no re-rendering

        CRITICAL: This method does NOT scan the global Matplotlib registry.
        Figures MUST be passed explicitly via _captured_figures kwarg.
        """
        self.plot_stack.setCurrentIndex(1)  # Show matplotlib mode

        figures = kwargs.pop("_captured_figures", None)

        # CRITICAL: Do NOT scan global Matplotlib registry!
        if not figures:
            qWarning(f"[{self.tab_name}] embed_matplotlib_plots called without figures - ignoring")
            return

        # Use content-based signature for detecting updates vs rebuilds
        content_sig = self._compute_figure_content_signature(figures)
        obj_sig = tuple(id(fig) for fig in figures)

        # Can update in-place if same figure objects or same content structure
        same_objects = (self._mpl_embed_signature == obj_sig and
                        len(self._matplotlib_figure_widgets) == len(figures))
        same_content = (hasattr(self, '_mpl_content_signature') and
                        self._mpl_content_signature == content_sig and
                        len(self._carousel_figures) == len(figures) and
                        len(self._carousel_figures) > 0)

        can_update_in_place = same_objects or same_content

        if can_update_in_place:
            # In-place update: just redraw canvases and update thumbnails
            qInfo(f"[{self.tab_name}] In-place update for {len(figures)} figures")
            for i, fig in enumerate(figures):
                if i < len(self._matplotlib_figure_widgets):
                    container, canvas, toolbar = self._matplotlib_figure_widgets[i]
                    canvas.draw_idle()
                if i < self.figure_carousel.figure_count():
                    self.figure_carousel.update_thumbnail(i, fig)
            self.labels_added = True
            return

        # Layout changed or first time: create persistent widgets
        qInfo(f"[{self.tab_name}] Creating {len(figures)} persistent matplotlib widgets...")

        # Clear previous state
        self.clear_plots()

        self._mpl_embed_signature = obj_sig
        self._mpl_content_signature = content_sig

        # Store all figures for carousel navigation
        self._carousel_figures = list(figures)

        # Create persistent widgets for all figures
        for i, fig in enumerate(figures):
            self.figure_carousel.add_figure(fig, make_active=(i == len(figures) - 1))
            self._create_persistent_matplotlib_widget(fig, i)
            # Also create pyqtgraph widgets (for mode switching)
            self._create_persistent_pyqtgraph_widget(fig, i)

        # Display the last (newest) figure
        if figures:
            last_index = len(figures) - 1
            self._displayed_figure_index = last_index
            self.matplotlib_stack.setCurrentIndex(last_index + 1)  # +1 for default widget
            self.figure_carousel.select_figure(last_index)

        self.labels_added = True
        qInfo(f"[{self.tab_name}] Successfully created {len(figures)} persistent matplotlib widgets")

    def convert_matplotlib_to_pyqtgraph(self, *args, **kwargs):
        """
        Converts ANY matplotlib figure/axes layout to PyQtGraph.

        STACKED WIDGET ARCHITECTURE:
        - Each figure gets a persistent GraphicsLayoutWidget in the pyqtgraph stack
        - Switching figures is just setCurrentIndex() - no re-rendering

        CRITICAL: This method does NOT scan the global Matplotlib registry.
        Figures MUST be passed explicitly via _captured_figures kwarg.
        """
        self.plot_stack.setCurrentIndex(0)  # Show pyqtgraph mode
        if not hasattr(self, 'file_name') or not hasattr(self, 'folder_name'):
            self.prepare_file_naming()

        figures = kwargs.pop("_captured_figures", None)

        # CRITICAL: Do NOT scan global Matplotlib registry!
        if not figures:
            qWarning(f"[{self.tab_name}] convert_matplotlib_to_pyqtgraph called without figures - ignoring")
            return

        # Compute signature for this set of figures (structure only, not data)
        new_sig = self._compute_pyqtgraph_signature(figures)

        # Check if we can update in place
        can_update_in_place = (
                hasattr(self, '_pyqtgraph_signature') and
                self._pyqtgraph_signature == new_sig and
                len(self._pyqtgraph_figure_widgets) == len(figures)
        )

        if can_update_in_place:
            # In-place update: update data on persistent widgets
            qInfo(f"[{self.tab_name}] In-place PyQtGraph update for {len(figures)} figures")
            for i, fig in enumerate(figures):
                if i < len(self._pyqtgraph_figure_widgets):
                    pg_widget, axes_map = self._pyqtgraph_figure_widgets[i]
                    axes = fig.get_axes()
                    for ax_idx, plot in axes_map:
                        if ax_idx < len(axes):
                            self._update_pyqtgraph_plot_data(plot, axes[ax_idx])
                if i < self.figure_carousel.figure_count():
                    self.figure_carousel.update_thumbnail(i, fig)
            self.labels_added = True
            return

        # Layout changed - create persistent widgets
        qInfo(f"[{self.tab_name}] Creating {len(figures)} persistent PyQtGraph widgets...")
        self.clear_plots()
        self._pyqtgraph_signature = new_sig

        # Store all figures for carousel navigation
        self._carousel_figures = list(figures)

        # Create persistent widgets for all figures
        for i, fig in enumerate(figures):
            self.figure_carousel.add_figure(fig, make_active=(i == len(figures) - 1))
            self._create_persistent_pyqtgraph_widget(fig, i)
            # Also create matplotlib widgets (for mode switching)
            self._create_persistent_matplotlib_widget(fig, i)

        # Display the last (newest) figure
        if figures:
            last_index = len(figures) - 1
            self._displayed_figure_index = last_index
            self.pyqtgraph_stack.setCurrentIndex(last_index + 1)  # +1 for default widget
            self.figure_carousel.select_figure(last_index)

        self.labels_added = True
        qInfo(f"[{self.tab_name}] Successfully created {len(figures)} persistent PyQtGraph widgets")

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

    def _fit_size_keep_aspect(self, max_w: int, max_h: int, aspect: float) -> Tuple[int, int]:
        """Return (w,h) that fits within (max_w,max_h) while preserving w/h=aspect."""
        if max_w <= 1 or max_h <= 1 or aspect <= 0:
            return max(1, max_w), max(1, max_h)

        w = max_w
        h = int(round(w / aspect))
        if h > max_h:
            h = max_h
            w = int(round(h * aspect))
        return max(1, w), max(1, h)

    def _get_plot_slot_size_px(self) -> Tuple[int, int]:
        """Return the available (w,h) for plotting inside the GUI slot.

        This intentionally measures the plot_stack area (which excludes the carousel below it).
        The returned value is used as a *snapshot* at the start of each plot session so that
        GUI resizes do not resize plots unless RePlot/Run is clicked.
        """
        try:
            w = int(self.plot_stack.width())
            h = int(self.plot_stack.height())
        except Exception:
            w, h = 1, 1

        # Subtract container margins if present
        try:
            m = self.plot_stack.contentsMargins()
            w -= int(m.left() + m.right())
            h -= int(m.top() + m.bottom())
        except Exception:
            pass

        return max(1, w), max(1, h)

    def _detect_axes_grid(self, axes):
        """
        Detect grid layout from axes positions, including spanning axes.

        Returns dict with:
            - nrows, ncols: grid dimensions
            - grid: mapping (row, col) -> ax_index (for the top-left cell of each axis)
            - spans: mapping ax_index -> (rowspan, colspan)
        """
        if len(axes) == 0:
            return {'nrows': 0, 'ncols': 0, 'grid': {}, 'spans': {}}

        if len(axes) == 1:
            return {'nrows': 1, 'ncols': 1, 'grid': {(0, 0): 0}, 'spans': {0: (1, 1)}}

        # Get axis positions (bounding boxes)
        positions = []
        for i, ax in enumerate(axes):
            pos = ax.get_position()
            positions.append({
                'idx': i,
                'x0': pos.x0, 'y0': pos.y0,
                'x1': pos.x0 + pos.width,
                'y1': pos.y0 + pos.height,
            })

        # Find unique edge positions to determine grid lines
        tol = 0.03

        def cluster_values(values, tol):
            """Cluster nearby values and return sorted unique representatives."""
            if not values:
                return []
            sorted_vals = sorted(values)
            clusters = [[sorted_vals[0]]]
            for v in sorted_vals[1:]:
                if v - clusters[-1][-1] < tol:
                    clusters[-1].append(v)
                else:
                    clusters.append([v])
            return [sum(c) / len(c) for c in clusters]

        # Collect all x and y edges
        x_edges = []
        y_edges = []
        for p in positions:
            x_edges.extend([p['x0'], p['x1']])
            y_edges.extend([p['y0'], p['y1']])

        # Cluster to find grid lines
        x_lines = cluster_values(x_edges, tol)  # sorted left to right
        y_lines = cluster_values(y_edges, tol)  # sorted bottom to top
        y_lines = y_lines[::-1]  # reverse so row 0 is at top (highest y)

        # Grid dimensions: n lines = n-1 cells
        ncols = max(1, len(x_lines) - 1)
        nrows = max(1, len(y_lines) - 1)

        # Map each axis to its grid position and span
        grid = {}
        spans = {}

        for p in positions:
            idx = p['idx']

            # Find which column the left edge falls into
            col_start = 0
            for i, x in enumerate(x_lines[:-1]):
                if p['x0'] < x + tol:
                    col_start = i
                    break
                col_start = i

            # Find which column the right edge reaches
            col_end = ncols - 1
            for i, x in enumerate(x_lines[1:], 1):
                if p['x1'] < x + tol:
                    col_end = i - 1
                    break
                col_end = i - 1 if i < len(x_lines) - 1 else ncols - 1

            # Find which row the top edge falls into (remember y_lines is reversed)
            row_start = 0
            for i, y in enumerate(y_lines[:-1]):
                if p['y1'] > y - tol:
                    row_start = i
                    break
                row_start = i

            # Find which row the bottom edge reaches
            row_end = nrows - 1
            for i, y in enumerate(y_lines[1:], 1):
                if p['y0'] > y - tol:
                    row_end = i - 1
                    break
                row_end = i - 1 if i < len(y_lines) - 1 else nrows - 1

            # Ensure valid ranges
            col_start = max(0, min(col_start, ncols - 1))
            col_end = max(col_start, min(col_end, ncols - 1))
            row_start = max(0, min(row_start, nrows - 1))
            row_end = max(row_start, min(row_end, nrows - 1))

            colspan = col_end - col_start + 1
            rowspan = row_end - row_start + 1

            grid[(row_start, col_start)] = idx
            spans[idx] = (rowspan, colspan)

        return {'nrows': nrows, 'ncols': ncols, 'grid': grid, 'spans': spans}

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
            return tuple(int(c * 255) for c in rgba[:3])

        # Create PlotItem at the specified position
        plot = self.plot_widget.ci.addPlot(row=row, col=col)
        self.plot_manager.add_pyqtgraph_plot(plot, row=row, col=col)

        plot.setLabel('bottom', ax.get_xlabel())
        plot.setLabel('left', ax.get_ylabel())
        plot.showGrid(x=True, y=True, alpha=0.3)

        # Handle line plots
        for line in ax.get_lines():
            x, y = line.get_xdata(), line.get_ydata()
            if x is None or y is None or len(x) == 0:
                continue

            # Handle NaN values in line data
            x_arr = np.asarray(x, dtype=float)
            y_arr = np.asarray(y, dtype=float)

            color = mpl_color_to_pg(line.get_color())
            linestyle = line.get_linestyle()

            pen_style = Qt.SolidLine
            if linestyle == '--':
                pen_style = Qt.DashLine
            elif linestyle == ':':
                pen_style = Qt.DotLine
            elif linestyle == '-.':
                pen_style = Qt.DashDotLine

            marker = line.get_marker()
            symbol = None
            if marker == 'o':
                symbol = 'o'
            elif marker == 's':
                symbol = 's'
            elif marker == '^':
                symbol = 't'
            elif marker == 'x':
                symbol = 'x'
            elif marker == '+':
                symbol = '+'

            plot.plot(x_arr, y_arr,
                      pen=pg.mkPen(color=color, width=line.get_linewidth() + 1, style=pen_style),
                      symbol=symbol, symbolSize=line.get_markersize() if marker else 5,
                      symbolBrush=color)

        # Handle scatter plots
        for collection in ax.collections:
            if isinstance(collection, PathCollection):
                offsets = collection.get_offsets()
                if len(offsets) == 0:
                    continue

                x = offsets[:, 0]
                y = offsets[:, 1]

                facecolors = collection.get_facecolor()
                if len(facecolors) > 0:
                    color = mpl_color_to_pg(facecolors[0])
                else:
                    color = (0, 0, 255)

                sizes = collection.get_sizes()
                size = np.sqrt(sizes[0]) if len(sizes) > 0 else 5

                plot.plot(x, y, pen=None, symbol='o', symbolSize=size, symbolBrush=color)

        # Handle bar plots / histograms (Rectangle patches)
        bars = [p for p in ax.patches if isinstance(p, Rectangle)]
        if bars:
            # Extract bar data
            x_vals = []
            heights = []
            widths = []

            for bar in bars:
                x_vals.append(bar.get_x())
                heights.append(bar.get_height())
                widths.append(bar.get_width())

            if x_vals and heights:
                x_arr = np.array(x_vals)
                h_arr = np.array(heights)
                w_arr = np.array(widths)

                # Get bar color
                if bars[0].get_facecolor() is not None:
                    bar_color = mpl_color_to_pg(bars[0].get_facecolor())
                else:
                    bar_color = (70, 130, 180)  # Steel blue default

                # Use BarGraphItem for proper bar rendering
                bar_item = pg.BarGraphItem(
                    x=x_arr + w_arr / 2,  # Center x position
                    height=h_arr,
                    width=w_arr * 0.9,  # Slight gap between bars
                    brush=bar_color
                )
                plot.addItem(bar_item)

        # Handle images (2D data)
        for img in ax.get_images():
            data = img.get_array()
            if data is None or data.size == 0:
                continue

            # Convert to numpy array and handle masked arrays
            if hasattr(data, 'mask'):
                data = np.ma.filled(data.astype(float), np.nan)
            else:
                data = np.asarray(data, dtype=float)

            # Compute valid min/max for levels
            valid_mask = ~np.isnan(data)
            if np.any(valid_mask):
                vmin, vmax = np.nanmin(data), np.nanmax(data)
                if vmin == vmax:
                    vmax = vmin + 1
                display_data = np.where(np.isnan(data), vmin, data)
            else:
                display_data = data
                vmin, vmax = 0, 1

            # Apply colormap
            cmap_name = img.get_cmap().name
            try:
                pg_cmap = pg.colormap.get(cmap_name)
            except:
                pg_cmap = pg.colormap.get('viridis')

            # PyQtGraph expects data in (width, height) format, matplotlib uses (height, width)
            # So we transpose to convert from matplotlib's row-major to pyqtgraph's column-major
            image_item = pg.ImageItem(display_data.T, levels=(vmin, vmax))
            image_item.setLookupTable(pg_cmap.getLookupTable())
            plot.addItem(image_item)

            # Set extent if available - use proper transform
            extent = img.get_extent()
            if extent is not None:
                x0, x1, y0, y1 = extent
                # Calculate scale and translation for the image
                # After transpose, data shape is (original_width, original_height)
                data_h, data_w = display_data.shape  # Original shape before transpose

                # Scale factors
                scale_x = (x1 - x0) / data_w if data_w > 0 else 1.0
                scale_y = (y1 - y0) / data_h if data_h > 0 else 1.0

                # Apply transform: translate then scale
                from PyQt5.QtGui import QTransform
                transform = QTransform()
                transform.translate(x0, y0)
                transform.scale(scale_x, scale_y)
                image_item.setTransform(transform)

                # Set axis ranges to match extent
                plot.setXRange(x0, x1, padding=0)
                plot.setYRange(y0, y1, padding=0)

            plot.setAspectLocked(True)

            # Add colorbar
            try:
                colorbar = pg.ColorBarItem(values=(vmin, vmax), colorMap=pg_cmap)
                colorbar.setImageItem(image_item, insert_in=plot)
            except:
                pass

        return plot

    # =========================================================================
    # COORDINATE DISPLAY
    # =========================================================================

    def update_coordinates(self, pos):
        """Updates the coordinate label with the current mouse position."""
        if not self.use_matplotlib_checkbox.isChecked():
            mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(pos) if hasattr(self.plot_widget,
                                                                                      'plotItem') else None
            if mouse_point:
                x, y = mouse_point.x(), mouse_point.y()
                self.coord_label.setText(f"X: {x:.4f} Y: {y:.4f}")

    # =========================================================================
    # EXPERIMENT CONTROL
    # =========================================================================

    def reExtract_experiment(self):
        """Re-extracts the experiment from its source file."""
        if self.experiment_obj is not None:
            try:
                self.experiment_obj.reload_experiment()
                self.reExtract_experiment_button.setText('Done!')
                QTimer.singleShot(2000, lambda: self.reExtract_experiment_button.setText('Sync Experiment'))
                qInfo(f"Re-extracted experiment: {self.tab_name}")
            except Exception as e:
                qCritical(f"Failed to re-extract experiment: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to re-extract experiment: {str(e)}")

    def process_data(self, data):
        """Process incoming data from experiment thread."""
        self.data = data

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
        # Start a new plot session so the fixed plot size is recalculated once.
        # This also clears plot state safely (carousel + widgets + signatures).
        self.start_plot_session()
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
                        # Capture the appropriate plot widget from the stacks
                        if self.use_matplotlib_checkbox.isChecked():
                            current_idx = self.matplotlib_stack.currentIndex()
                            widget = self.matplotlib_stack.widget(current_idx)
                            pixmap = widget.grab() if widget else self.matplotlib_stack.grab()
                        else:
                            current_idx = self.pyqtgraph_stack.currentIndex()
                            widget = self.pyqtgraph_stack.widget(current_idx)
                            pixmap = widget.grab() if widget else self.pyqtgraph_stack.grab()
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
                    current_idx = self.matplotlib_stack.currentIndex()
                    widget = self.matplotlib_stack.widget(current_idx)
                    pixmap = widget.grab() if widget else self.matplotlib_stack.grab()
                else:
                    current_idx = self.pyqtgraph_stack.currentIndex()
                    widget = self.pyqtgraph_stack.widget(current_idx)
                    pixmap = widget.grab() if widget else self.pyqtgraph_stack.grab()
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

    # =========================================================================
    # AUTO-PLOTTING METHODS
    # =========================================================================

    def auto_plot_prepare(self, data_to_plot):
        """
        Prepares data for plotting by extracting arrays from various formats.
        Supports incremental updates for live plotting.
        """
        # This method handles auto-plotting for loaded data and experiments
        # without a custom display() method

        if data_to_plot is None:
            qWarning("auto_plot_prepare: no data to plot")
            return

        # Build a "spec list" describing what to plot
        specs = []

        def _as_array(v):
            """Convert value to numpy array if possible, else return None."""
            try:
                arr = np.asarray(v)
                if arr.dtype.kind in ('f', 'i', 'u', 'c'):
                    return arr
                return None
            except Exception:
                return None

        if isinstance(data_to_plot, dict):
            # Handle 'data' key if present
            inner = data_to_plot.get("data", data_to_plot)
            if isinstance(inner, dict):
                data_to_plot = inner

            for k, v in data_to_plot.items():
                if k.lower() in ('config', 'metadata', 'settings'):
                    continue
                if isinstance(v, (tuple, list)) and len(v) == 2:
                    x = _as_array(v[0])
                    y = _as_array(v[1])
                    if x is not None and y is not None and x.ndim == 1 and y.ndim == 1:
                        specs.append(("curve", str(k), x, y))
                    elif x is not None and y is not None:
                        # Try to interpret as image
                        arr = _as_array(v)
                        if arr is not None and arr.ndim == 2:
                            specs.append(("image", str(k), arr))
                elif isinstance(v, (tuple, list)) and len(v) > 2:
                    # Could be a list of arrays
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
        """
        Performs fitting on PyQtGraph plots for the CURRENTLY SELECTED figure only.

        FIXED: Now uses the stacked widget architecture - only fits the selected figure.
        """
        # Check if we have any figures
        if self._displayed_figure_index < 0:
            qWarning("No figure currently displayed")
            return

        if self._displayed_figure_index >= len(self._pyqtgraph_figure_widgets):
            qWarning("Invalid figure index")
            return

        # Get the currently displayed PyQtGraph widget and its axes map
        pg_widget, axes_map = self._pyqtgraph_figure_widgets[self._displayed_figure_index]

        if not axes_map:
            qWarning("No plots available to fit in current figure")
            return

        # Clear previous fit overlays
        self.clear_fit_overlays()

        qInfo(f"Performing fit with model: {fit_model} on figure {self._displayed_figure_index + 1}")

        fit_count = 0

        # Iterate through plots in the current figure only
        for ax_idx, plot in axes_map:
            # Check if this is a 2D image plot or 1D line plot
            has_image = any(isinstance(item, pg.ImageItem) for item in plot.items)

            if has_image:
                # Handle 2D fitting
                result = self.fit_2d_plot(plot, fit_model)
                if result and result.get("success"):
                    fit_count += 1
                    self.display_2d_fit_results(result)
                    # Always try to overlay - method handles both full fit and basic detection
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
                        qInfo(f"Fit successful on axis {ax_idx}: {result.model_name}, R^2={result.r_squared:.4f}")
                        self.fit_results.append(result)

                        # Overlay fit on plot
                        self.overlay_fit_on_plot(plot, result)
                        fit_count += 1

                        # Display fit parameters
                        self.display_fit_results(result)
                    else:
                        qWarning(f"Fit failed on axis {ax_idx}: {result.message}")

        if fit_count > 0:
            self.fit_button.setText('Done!')
            QTimer.singleShot(2000, lambda: self.fit_button.setText('Fit'))
            qInfo(f"Successfully fitted {fit_count} plot(s) in figure {self._displayed_figure_index + 1}")
        else:
            qWarning("No fits were successful")

    def perform_fit_matplotlib(self, fit_model: str):
        """
        Performs fitting on matplotlib plots for the CURRENTLY SELECTED figure only.

        FIXED: Now uses the stacked widget architecture - only fits the selected figure.
        """
        # Check if we have any figures
        if self._displayed_figure_index < 0:
            qWarning("No figure currently displayed")
            return

        if self._displayed_figure_index >= len(self._matplotlib_figure_widgets):
            qWarning("Invalid figure index")
            return

        # Get the currently displayed matplotlib widget
        container, canvas, toolbar = self._matplotlib_figure_widgets[self._displayed_figure_index]

        # Clear previous fit overlays
        self.clear_fit_overlays()

        qInfo(f"Performing matplotlib fit with model: {fit_model} on figure {self._displayed_figure_index + 1}")

        fit_count = 0
        fig = canvas.figure

        for ax_idx, ax in enumerate(fig.get_axes()):
            # Check if this is a 2D image or 1D line plot
            has_image = len(ax.get_images()) > 0

            if has_image:
                # Handle 2D fitting for matplotlib
                result = self.fit_2d_matplotlib(ax, fit_model)
                if result and result.get("success"):
                    fit_count += 1
                    self.display_2d_fit_results(result)
                    # Always try to overlay - method handles both full fit and basic detection
                    self.overlay_chevron_fit_on_matplotlib(ax, result)
            else:
                # Handle 1D fitting for matplotlib
                lines = ax.get_lines()
                if not lines:
                    continue

                for line_idx, line in enumerate(lines):
                    # Skip fit overlay lines (they have specific labels)
                    label = line.get_label()
                    if label and 'Fit' in label:
                        continue

                    x_data = np.array(line.get_xdata())
                    y_data = np.array(line.get_ydata())

                    if len(x_data) > 3:
                        if fit_model == "Auto":
                            result = self.fit_manager.fit_1d(x_data, y_data, model_name="Auto")
                        else:
                            result = self.fit_manager.fit_1d(x_data, y_data, model_name=fit_model)

                        if result.success:
                            qInfo(f"Fit successful: {result.model_name}, R^2={result.r_squared:.4f}")
                            self.fit_results.append(result)

                            # Overlay fit on matplotlib
                            self.overlay_fit_on_matplotlib(ax, result)
                            fit_count += 1

                            self.display_fit_results(result)

        canvas.draw()

        if fit_count > 0:
            self.fit_button.setText('Done!')
            QTimer.singleShot(2000, lambda: self.fit_button.setText('Fit'))
            qInfo(f"Successfully fitted {fit_count} plot(s) in figure {self._displayed_figure_index + 1}")
        else:
            qWarning("No fits were successful")

    def fit_2d_plot(self, plot, fit_model: str):
        """Fit 2D data in a PyQtGraph plot."""
        try:
            image_items = [item for item in plot.items if isinstance(item, pg.ImageItem)]
            if not image_items:
                return None

            data = image_items[0].image
            if data is None:
                return None

            # Transpose back since we transposed for display
            data = data.T

            # Try to get axis values from experiment data
            x_axis, y_axis = self.try_extract_axes_from_data()

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

    def fit_2d_matplotlib(self, ax, fit_model: str):
        """Fit 2D data in a matplotlib axis."""
        try:
            images = ax.get_images()
            if not images:
                return None

            data = images[0].get_array()
            if data is None:
                return None

            x_axis, y_axis = self.try_extract_axes_from_data()

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
        """Handle matplotlib checkbox toggle - switch between rendering modes."""
        if self.use_matplotlib_checkbox.isChecked():
            self.coord_label.hide()
            # Switch to matplotlib mode
            self.plot_stack.setCurrentIndex(1)
            # Show the correct figure in matplotlib stack
            if self._displayed_figure_index >= 0:
                stack_index = self._displayed_figure_index + 1  # +1 for default widget
                if stack_index < self.matplotlib_stack.count():
                    self.matplotlib_stack.setCurrentIndex(stack_index)
        else:
            self.coord_label.show()
            # Switch to pyqtgraph mode
            self.plot_stack.setCurrentIndex(0)
            # Show the correct figure in pyqtgraph stack
            if self._displayed_figure_index >= 0:
                stack_index = self._displayed_figure_index + 1  # +1 for default widget
                if stack_index < self.pyqtgraph_stack.count():
                    self.pyqtgraph_stack.setCurrentIndex(stack_index)

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
                            label=f'{fit_result.model_name} Fit (R^2={fit_result.r_squared:.3f})',
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
            # Check if full fit was performed
            if result.get("fit_performed"):
                # Extract fitted parameters
                g = result.get("coupling_g")
                delta0 = result.get("center_detuning")

                qInfo(f"Overlaying chevron fit: g={g:.3e}, delta_0={delta0:.3f}")

                # Draw horizontal line at center detuning (sweet spot)
                center_line = pg.InfiniteLine(
                    pos=delta0,
                    angle=0,
                    pen=pg.mkPen(color='cyan', width=3, style=Qt.DashLine),
                    label=f'Center={delta0:.3f}',
                    labelOpts={'position': 0.70, 'color': (0, 255, 255), 'fill': (0, 0, 0, 100)}
                )
                plot.addItem(center_line)
                self.fit_overlays.append(center_line)

            elif result.get("sweet_spot") is not None:
                # Use basic detection result if full fit wasn't performed
                sweet_spot_row, sweet_spot_col = result.get("sweet_spot")
                qInfo(f"Using basic detection: sweet_spot=({sweet_spot_row}, {sweet_spot_col})")

                # Draw crosshairs at sweet spot
                h_line = pg.InfiniteLine(
                    pos=sweet_spot_row,
                    angle=0,
                    pen=pg.mkPen(color='yellow', width=2, style=Qt.DashLine),
                    label=f'Row={sweet_spot_row}',
                    labelOpts={'position': 0.70, 'color': (255, 255, 0)}
                )
                v_line = pg.InfiniteLine(
                    pos=sweet_spot_col,
                    angle=90,
                    pen=pg.mkPen(color='yellow', width=2, style=Qt.DashLine),
                    label=f'Col={sweet_spot_col}',
                    labelOpts={'position': 0.70, 'color': (255, 255, 0)}
                )
                plot.addItem(h_line)
                plot.addItem(v_line)
                self.fit_overlays.append(h_line)
                self.fit_overlays.append(v_line)
            else:
                qWarning("No chevron fit data available to overlay")
                return

            # Force update of the plot widget
            plot.update()

        except Exception as e:
            qCritical(f"Failed to overlay chevron fit on PyQtGraph: {str(e)}")
            traceback.print_exc()

    def overlay_chevron_fit_on_matplotlib(self, ax, result: Dict):
        """Overlay chevron fit visualization on a matplotlib axis."""
        try:
            # Check if full fit was performed
            if result.get("fit_performed"):
                delta0 = result.get("center_detuning")

                qInfo(f"Overlaying matplotlib chevron fit: delta_0={delta0:.3f}")

                # Draw horizontal line at center detuning
                line = ax.axhline(y=delta0, color='cyan', linestyle='--', linewidth=2,
                                  label=f'Center={delta0:.3f}', zorder=10)
                self.fit_overlays.append(line)
                ax.legend(loc='best')

            elif result.get("sweet_spot") is not None:
                # Use basic detection result if full fit wasn't performed
                sweet_spot_row, sweet_spot_col = result.get("sweet_spot")
                qInfo(f"Using basic detection: sweet_spot=({sweet_spot_row}, {sweet_spot_col})")

                # Draw crosshairs at sweet spot
                h_line = ax.axhline(y=sweet_spot_row, color='yellow', linestyle='--',
                                    linewidth=2, label=f'Row={sweet_spot_row}', zorder=10)
                v_line = ax.axvline(x=sweet_spot_col, color='yellow', linestyle='--',
                                    linewidth=2, label=f'Col={sweet_spot_col}', zorder=10)
                self.fit_overlays.append(h_line)
                self.fit_overlays.append(v_line)
                ax.legend(loc='best')
            else:
                qWarning("No chevron fit data available to overlay")
                return

        except Exception as e:
            qCritical(f"Failed to overlay chevron fit on matplotlib: {str(e)}")
            traceback.print_exc()