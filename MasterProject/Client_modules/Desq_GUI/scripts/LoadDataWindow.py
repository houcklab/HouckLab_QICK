"""
=================
LoadDataWindow.py
=================

Window for loading data with experiment display functions.

This module provides a dialog window that allows users to:

1. Select an HDF5 data file containing experiment results
2. Select a Python experiment file containing display logic
3. Choose an experiment class from the file to use for visualization

The window emits a signal when the user has made valid selections and
clicks "Load", allowing the parent application to handle the actual
data loading and visualization.

:var QSettings: Used to persist last-used directories for file browsing.

.. seealso::

    :mod:`ExperimentLoader` - Module used to dynamically load experiment classes.
"""

from __future__ import annotations

import os
import traceback
from types import ModuleType
from typing import Any, List, Optional, Tuple

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QMessageBox, QFileDialog, QGroupBox,
    QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QSettings
from PyQt5.QtCore import qCritical, qInfo

from MasterProject.Client_modules.Desq_GUI.scripts import ExperimentLoader


class LoadDataWindow(QWidget):
    """
    A popout window for selecting an H5 data file and an experiment file
    to use its ``display()`` function for visualization.

    This window provides a two-step workflow:

    1. User selects an HDF5 data file containing experiment results
    2. User selects a Python experiment file and chooses which
       ``ExperimentClass`` subclass to use for displaying the data

    :ivar load_requested: Signal emitted when user clicks "Load" with valid selections.
    :vartype load_requested: pyqtSignal(str, str, str)

    :ivar h5_path_edit: Text field displaying the selected H5 file path.
    :vartype h5_path_edit: QLineEdit

    :ivar h5_browse_button: Button to open H5 file browser dialog.
    :vartype h5_browse_button: QPushButton

    :ivar exp_path_edit: Text field displaying the selected experiment file path.
    :vartype exp_path_edit: QLineEdit

    :ivar exp_browse_button: Button to open experiment file browser dialog.
    :vartype exp_browse_button: QPushButton

    :ivar class_combo: Dropdown for selecting experiment class from loaded file.
    :vartype class_combo: QComboBox

    :ivar status_label: Label showing current status/instructions to user.
    :vartype status_label: QLabel

    :ivar cancel_button: Button to close the window without loading.
    :vartype cancel_button: QPushButton

    :ivar load_button: Button to confirm selections and emit load_requested signal.
    :vartype load_button: QPushButton

    :ivar _experiment_module: The loaded Python module (currently unused).
    :vartype _experiment_module: Optional[ModuleType]

    :ivar _experiment_classes: List of (class_name, class_object) tuples found
        in the loaded experiment file.
    :vartype _experiment_classes: List[Tuple[str, type]]

    :ivar _experiment_path: Path to the currently loaded experiment file.
    :vartype _experiment_path: Optional[str]

    :ivar _preset_h5_path: H5 path to pre-fill when window is shown.
    :vartype _preset_h5_path: Optional[str]

    .. note::

        The ``_experiment_module`` instance variable is set to ``None`` during loading
        and never actually populated with the module. The classes are not stored as
        they are only used to call the display function.

    Example::

        window = LoadDataWindow(parent=main_window)
        window.load_requested.connect(handle_load)
        window.show()

        def handle_load(h5_path, exp_path, class_name):
            # Load and display the data
            pass
    """

    #: Signal emitted when the user requests to load data with an experiment display.
    #:
    #: :param h5_path: Path to the H5 data file.
    #: :param experiment_path: Path to the experiment .py file.
    #: :param class_name: Name of the experiment class to use.
    load_requested: pyqtSignal = pyqtSignal(str, str, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the LoadDataWindow.

        :param parent: Optional parent widget for Qt object hierarchy.
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)

        self.setWindowTitle("Load Data with Experiment Display")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setFixedSize(500, 280)
        self.setObjectName("LoadDataWindow")

        # Track loaded experiment info
        self._experiment_module: Optional[ModuleType] = None
        self._experiment_classes: List[Tuple[str, type]] = []
        self._experiment_path: Optional[str] = None

        self._setup_ui()
        self._setup_signals()

    def _setup_ui(self) -> None:
        """
        Set up the UI components.

        Creates the following layout structure:

        - H5 Data File section (GroupBox with path edit + browse button)
        - Experiment File section (GroupBox with path edit + browse + class selector)
        - Status label for user feedback
        - Action buttons (Cancel, Load)
        """
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # === H5 Data File Section ===
        h5_group = QGroupBox("1. Select Data File")
        h5_layout = QHBoxLayout(h5_group)
        h5_layout.setContentsMargins(10, 15, 10, 10)
        h5_layout.setSpacing(8)

        self.h5_path_edit: QLineEdit = QLineEdit()
        self.h5_path_edit.setPlaceholderText("Path to .h5 data file...")
        self.h5_path_edit.setReadOnly(True)

        self.h5_browse_button: QPushButton = QPushButton("Browse...")
        self.h5_browse_button.setFixedWidth(80)

        h5_layout.addWidget(self.h5_path_edit)
        h5_layout.addWidget(self.h5_browse_button)

        main_layout.addWidget(h5_group)

        # === Experiment File Section ===
        exp_group = QGroupBox("2. Select Experiment File")
        exp_layout = QVBoxLayout(exp_group)
        exp_layout.setContentsMargins(10, 15, 10, 10)
        exp_layout.setSpacing(8)

        # Experiment file path row
        exp_path_layout = QHBoxLayout()
        exp_path_layout.setSpacing(8)

        self.exp_path_edit: QLineEdit = QLineEdit()
        self.exp_path_edit.setPlaceholderText("Path to .py experiment file...")
        self.exp_path_edit.setReadOnly(True)

        self.exp_browse_button: QPushButton = QPushButton("Browse...")
        self.exp_browse_button.setFixedWidth(80)

        exp_path_layout.addWidget(self.exp_path_edit)
        exp_path_layout.addWidget(self.exp_browse_button)
        exp_layout.addLayout(exp_path_layout)

        # Experiment class selector row
        class_layout = QHBoxLayout()
        class_layout.setSpacing(8)

        class_label = QLabel("Experiment Class:")
        class_label.setFixedWidth(110)

        self.class_combo: QComboBox = QComboBox()
        self.class_combo.setEnabled(False)
        self.class_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        class_layout.addWidget(class_label)
        class_layout.addWidget(self.class_combo)
        exp_layout.addLayout(class_layout)

        main_layout.addWidget(exp_group)

        # === Status Label ===
        self.status_label: QLabel = QLabel("")
        self.status_label.setObjectName("status_label")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        main_layout.addWidget(self.status_label)

        # === Action Buttons ===
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.cancel_button: QPushButton = QPushButton("Cancel")
        self.cancel_button.setFixedWidth(80)

        self.load_button: QPushButton = QPushButton("Load")
        self.load_button.setFixedWidth(80)
        self.load_button.setEnabled(False)
        self.load_button.setObjectName("load_button")

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.load_button)

        main_layout.addLayout(button_layout)

    def _setup_signals(self) -> None:
        """
        Connect signals to slots.

        Establishes the following connections:

        - h5_browse_button.clicked → _browse_h5_file
        - exp_browse_button.clicked → _browse_experiment_file
        - cancel_button.clicked → close
        - load_button.clicked → _on_load_clicked
        - class_combo.currentIndexChanged → _update_load_button_state
        """
        self.h5_browse_button.clicked.connect(self._browse_h5_file)
        self.exp_browse_button.clicked.connect(self._browse_experiment_file)
        self.cancel_button.clicked.connect(self.close)
        self.load_button.clicked.connect(self._on_load_clicked)
        self.class_combo.currentIndexChanged.connect(self._update_load_button_state)

    def _browse_h5_file(self) -> None:
        """
        Open file dialog to select an H5 data file.

        Uses QSettings to remember the last directory used for H5 file selection.
        Updates the path edit field and triggers status/button state updates
        when a file is selected.
        """
        settings = QSettings("Desq", "LoadDataWindow")
        last_dir: str = settings.value("last_h5_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select H5 Data File",
            last_dir,
            "HDF5 Files (*.h5);;All Files (*)"
        )

        if file_path:
            self.h5_path_edit.setText(file_path)
            settings.setValue("last_h5_dir", os.path.dirname(file_path))
            self._update_status()
            self._update_load_button_state()

    def _browse_experiment_file(self) -> None:
        """
        Open file dialog to select a Python experiment file.

        Uses QSettings to remember the last directory used for experiment
        file selection. When a file is selected, triggers loading of
        experiment classes from that file.
        """
        settings = QSettings("Desq", "LoadDataWindow")
        last_dir: str = settings.value("last_exp_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Experiment File",
            last_dir,
            "Python Files (*.py);;All Files (*)"
        )

        if file_path:
            self.exp_path_edit.setText(file_path)
            settings.setValue("last_exp_dir", os.path.dirname(file_path))
            self._load_experiment_classes(file_path)

    def _load_experiment_classes(self, file_path: str) -> None:
        """
        Load the experiment file and populate the class combo box.

        Dynamically loads the Python file at ``file_path`` and searches for
        subclasses of ``ExperimentClass``. Each found class is added to the
        combo box, with an indicator if it lacks a ``display()`` method.

        :param file_path: Path to the Python experiment file to load.
        :type file_path: str

        .. note::

            Classes without a ``display()`` method are still shown in the
            combo box but marked with "[no display]" suffix. Users can still
            select these, which may lead to errors when trying to display.
        """
        # Reset state before loading
        self.class_combo.clear()
        self.class_combo.setEnabled(False)
        self._experiment_module = None
        self._experiment_classes = []
        self._experiment_path = None

        try:
            self.status_label.setText("Loading experiment file...")
            self.status_label.setStyleSheet("color: #666; font-style: italic;")

            # Use load_and_find to safely load the module
            # NOTE: module_name is returned but not stored - _experiment_module
            module_name, experiment_classes = ExperimentLoader.load_and_find(file_path)

            if not experiment_classes:
                self.status_label.setText("No ExperimentClass subclasses found in file.")
                self.status_label.setStyleSheet("color: #c00; font-style: italic;")
                QMessageBox.warning(
                    self,
                    "No Experiments Found",
                    "No valid ExperimentClass subclasses were found in this file."
                )
                return

            # Store the loaded info
            self._experiment_path = file_path
            self._experiment_classes = experiment_classes

            # Populate the combo box with discovered classes
            for class_name, class_obj in experiment_classes:
                # Check if class has a display method
                has_display: bool = hasattr(class_obj, 'display') and callable(getattr(class_obj, 'display'))
                display_indicator: str = "" if has_display else " [no display]"
                # Store class_name as item data for retrieval via currentData()
                self.class_combo.addItem(f"{class_name}{display_indicator}", class_name)

            self.class_combo.setEnabled(True)
            self._update_status()
            self._update_load_button_state()

        except Exception as e:
            # Show truncated error in status label, full error in log
            self.status_label.setText(f"Error loading file: {str(e)[:50]}...")
            self.status_label.setStyleSheet("color: #c00; font-style: italic;")
            qCritical(f"Error loading experiment file: {e}")
            qCritical(traceback.format_exc())

    def _update_status(self) -> None:
        """
        Update the status label based on current selections.

        Provides user guidance on what step they need to complete next,
        or confirms when all selections are ready for loading.
        """
        h5_path: str = self.h5_path_edit.text().strip()
        exp_path: str = self.exp_path_edit.text().strip()
        class_name: Optional[str] = self.class_combo.currentData()

        if not h5_path:
            self.status_label.setText("Please select an H5 data file.")
            self.status_label.setStyleSheet("color: #666; font-style: italic;")
        elif not exp_path:
            self.status_label.setText("Please select an experiment file.")
            self.status_label.setStyleSheet("color: #666; font-style: italic;")
        elif not class_name:
            self.status_label.setText("Please select an experiment class.")
            self.status_label.setStyleSheet("color: #666; font-style: italic;")
        else:
            # All selections valid - show ready message in green
            self.status_label.setText(f"Ready to load: {os.path.basename(h5_path)} with {class_name}.display()")
            self.status_label.setStyleSheet("color: #080; font-style: italic;")

    def _update_load_button_state(self) -> None:
        """
        Enable/disable the Load button based on selections.

        The Load button is only enabled when all three required selections
        are made: H5 file, experiment file, and experiment class.
        """
        h5_path: str = self.h5_path_edit.text().strip()
        exp_path: str = self.exp_path_edit.text().strip()
        class_name: Optional[str] = self.class_combo.currentData()

        can_load: bool = bool(h5_path and exp_path and class_name)
        self.load_button.setEnabled(can_load)
        self._update_status()

    def _on_load_clicked(self) -> None:
        """
        Handle the Load button click.

        Validates that all selections are present and that the selected
        files still exist on disk. If validation passes, emits the
        :attr:`load_requested` signal and closes the window.

        :raises: Does not raise - shows QMessageBox for validation errors.
        """
        h5_path: str = self.h5_path_edit.text().strip()
        exp_path: str = self.exp_path_edit.text().strip()
        class_name: Optional[str] = self.class_combo.currentData()

        # Final validation before emitting signal
        if not all([h5_path, exp_path, class_name]):
            QMessageBox.warning(self, "Missing Selection", "Please select all required files and options.")
            return

        # Verify files still exist (they may have been deleted/moved since selection)
        if not os.path.isfile(h5_path):
            QMessageBox.critical(self, "File Not Found", f"H5 file not found:\n{h5_path}")
            return

        if not os.path.isfile(exp_path):
            QMessageBox.critical(self, "File Not Found", f"Experiment file not found:\n{exp_path}")
            return

        qInfo(f"Load requested: {h5_path} with {class_name} from {exp_path}")
        self.load_requested.emit(h5_path, exp_path, class_name)
        self.close()

    def reset(self) -> None:
        """
        Reset the window to its initial state.

        Clears all path fields, disables the class combo and load button,
        and resets internal tracking variables. This is called automatically
        in :meth:`showEvent` to ensure a fresh state each time the window
        is shown.

        .. note::

            This method also clears ``_preset_h5_path``, which may cause
            issues if called after :meth:`set_h5_path` but before the
            preset is applied in :meth:`showEvent`. The current implementation
            in ``showEvent`` saves the preset before calling reset to avoid this.
        """
        self.h5_path_edit.clear()
        self.exp_path_edit.clear()
        self.class_combo.clear()
        self.class_combo.setEnabled(False)
        self.load_button.setEnabled(False)
        self._experiment_module = None
        self._experiment_classes = []
        self._experiment_path = None
        self.status_label.setText("")
        self._preset_h5_path = None

    def set_h5_path(self, path: str) -> None:
        """
        Pre-set the H5 file path.

        Call this before :meth:`show` to open the window with a file already
        selected. This is useful when launching the window from a context
        where the data file is already known (e.g., right-click on a file
        in a file browser).

        :param path: Path to the H5 data file.
        :type path: str

        Example::

            window = LoadDataWindow()
            window.set_h5_path("/path/to/data.h5")
            window.show()  # Window opens with H5 path pre-filled
        """
        self._preset_h5_path = path

    def showEvent(self, event: Any) -> None:
        """
        Handle the window show event.

        Resets the window when it is shown, then applies any preset path
        that was set via :meth:`set_h5_path`.

        :param event: The Qt show event.
        :type event: QShowEvent

        .. note::

            The preset path is saved before calling :meth:`reset` because
            reset clears ``_preset_h5_path``. This ensures the preset survives
            the reset process.
        """
        # Save preset path before reset clears it
        preset_path: Optional[str] = getattr(self, '_preset_h5_path', None)
        self.reset()
        super().showEvent(event)

        # Apply preset H5 path if provided
        if preset_path:
            self.h5_path_edit.setText(preset_path)
            self._update_status()
            self._update_load_button_state()