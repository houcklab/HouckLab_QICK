"""
=================
LoadDataWindow.py
=================

Window for loading data with experiment display functions. Allows user to choose h5 data file
and corresponding experiment file + experiment class for displaying.
"""

import os
import traceback

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
    to use its display() function for visualization.

    Signals:
        load_requested: Emitted when the user clicks "Load" with valid selections.
                        Arguments: (h5_path: str, experiment_path: str, class_name: str)
    """

    load_requested = pyqtSignal(str, str, str)
    """
    Signal emitted when the user requests to load data with an experiment display.

    :param h5_path: Path to the H5 data file.
    :type h5_path: str
    :param experiment_path: Path to the experiment .py file.
    :type experiment_path: str
    :param class_name: Name of the experiment class to use.
    :type class_name: str
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Load Data with Experiment Display")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setFixedSize(500, 280)
        self.setObjectName("LoadDataWindow")

        # Track loaded experiment info
        self._experiment_module = None
        self._experiment_classes = []
        self._experiment_path = None

        self._setup_ui()
        self._setup_signals()

    def _setup_ui(self):
        """Set up the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # === H5 Data File Section ===
        h5_group = QGroupBox("1. Select Data File")
        h5_layout = QHBoxLayout(h5_group)
        h5_layout.setContentsMargins(10, 15, 10, 10)
        h5_layout.setSpacing(8)

        self.h5_path_edit = QLineEdit()
        self.h5_path_edit.setPlaceholderText("Path to .h5 data file...")
        self.h5_path_edit.setReadOnly(True)

        self.h5_browse_button = QPushButton("Browse...")
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

        self.exp_path_edit = QLineEdit()
        self.exp_path_edit.setPlaceholderText("Path to .py experiment file...")
        self.exp_path_edit.setReadOnly(True)

        self.exp_browse_button = QPushButton("Browse...")
        self.exp_browse_button.setFixedWidth(80)

        exp_path_layout.addWidget(self.exp_path_edit)
        exp_path_layout.addWidget(self.exp_browse_button)
        exp_layout.addLayout(exp_path_layout)

        # Experiment class selector row
        class_layout = QHBoxLayout()
        class_layout.setSpacing(8)

        class_label = QLabel("Experiment Class:")
        class_label.setFixedWidth(110)

        self.class_combo = QComboBox()
        self.class_combo.setEnabled(False)
        self.class_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        class_layout.addWidget(class_label)
        class_layout.addWidget(self.class_combo)
        exp_layout.addLayout(class_layout)

        main_layout.addWidget(exp_group)

        # === Status Label ===
        self.status_label = QLabel("")
        self.status_label.setObjectName("status_label")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        main_layout.addWidget(self.status_label)

        # === Action Buttons ===
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setFixedWidth(80)

        self.load_button = QPushButton("Load")
        self.load_button.setFixedWidth(80)
        self.load_button.setEnabled(False)
        self.load_button.setObjectName("load_button")

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.load_button)

        main_layout.addLayout(button_layout)

    def _setup_signals(self):
        """Connect signals to slots."""
        self.h5_browse_button.clicked.connect(self._browse_h5_file)
        self.exp_browse_button.clicked.connect(self._browse_experiment_file)
        self.cancel_button.clicked.connect(self.close)
        self.load_button.clicked.connect(self._on_load_clicked)
        self.class_combo.currentIndexChanged.connect(self._update_load_button_state)

    def _browse_h5_file(self):
        """Open file dialog to select an H5 data file."""
        settings = QSettings("Desq", "LoadDataWindow")
        last_dir = settings.value("last_h5_dir", "")

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

    def _browse_experiment_file(self):
        """Open file dialog to select a Python experiment file."""
        settings = QSettings("Desq", "LoadDataWindow")
        last_dir = settings.value("last_exp_dir", "")

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

    def _load_experiment_classes(self, file_path):
        """Load the experiment file and populate the class combo box."""
        self.class_combo.clear()
        self.class_combo.setEnabled(False)
        self._experiment_module = None
        self._experiment_classes = []
        self._experiment_path = None

        try:
            self.status_label.setText("Loading experiment file...")
            self.status_label.setStyleSheet("color: #666; font-style: italic;")

            # Use load_and_find to safely load the module
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

            # Populate the combo box
            for class_name, class_obj in experiment_classes:
                # Check if class has a display method
                has_display = hasattr(class_obj, 'display') and callable(getattr(class_obj, 'display'))
                display_indicator = "" if has_display else " [no display]"
                self.class_combo.addItem(f"{class_name}{display_indicator}", class_name)

            self.class_combo.setEnabled(True)
            self._update_status()
            self._update_load_button_state()

        except Exception as e:
            self.status_label.setText(f"Error loading file: {str(e)[:50]}...")
            self.status_label.setStyleSheet("color: #c00; font-style: italic;")
            qCritical(f"Error loading experiment file: {e}")
            qCritical(traceback.format_exc())

    def _update_status(self):
        """Update the status label based on current selections."""
        h5_path = self.h5_path_edit.text().strip()
        exp_path = self.exp_path_edit.text().strip()
        class_name = self.class_combo.currentData()

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
            self.status_label.setText(f"Ready to load: {os.path.basename(h5_path)} with {class_name}.display()")
            self.status_label.setStyleSheet("color: #080; font-style: italic;")

    def _update_load_button_state(self):
        """Enable/disable the Load button based on selections."""
        h5_path = self.h5_path_edit.text().strip()
        exp_path = self.exp_path_edit.text().strip()
        class_name = self.class_combo.currentData()

        can_load = bool(h5_path and exp_path and class_name)
        self.load_button.setEnabled(can_load)
        self._update_status()

    def _on_load_clicked(self):
        """Handle the Load button click."""
        h5_path = self.h5_path_edit.text().strip()
        exp_path = self.exp_path_edit.text().strip()
        class_name = self.class_combo.currentData()

        if not all([h5_path, exp_path, class_name]):
            QMessageBox.warning(self, "Missing Selection", "Please select all required files and options.")
            return

        # Verify files still exist
        if not os.path.isfile(h5_path):
            QMessageBox.critical(self, "File Not Found", f"H5 file not found:\n{h5_path}")
            return

        if not os.path.isfile(exp_path):
            QMessageBox.critical(self, "File Not Found", f"Experiment file not found:\n{exp_path}")
            return

        qInfo(f"Load requested: {h5_path} with {class_name} from {exp_path}")
        self.load_requested.emit(h5_path, exp_path, class_name)
        self.close()

    def reset(self):
        """Reset the window to its initial state."""
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

    def set_h5_path(self, path):
        """
        Pre-set the H5 file path. Call this before show() to open the window
        with a file already selected.

        :param path: Path to the H5 data file.
        :type path: str
        """
        self._preset_h5_path = path

    def showEvent(self, event):
        """Reset the window when it is shown, then apply any preset path."""
        # Save preset path before reset clears it
        preset_path = getattr(self, '_preset_h5_path', None)
        self.reset()
        super().showEvent(event)

        # Apply preset H5 path if provided
        if preset_path:
            self.h5_path_edit.setText(preset_path)
            self._update_status()
            self._update_load_button_state()