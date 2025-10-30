"""
==================
ConfigTreePanel.py
==================
A PyQt5 widget for viewing and editing configuration parameters from JSON files.
This implementation uses a tree view for configuration parameters and includes:
1. Directory tree panel to navigate and select JSON files
2. Toggle between tree and JSON text editor views
3. Support for saving, loading, and copying configuration
"""

import os
import json
import ast
import datetime
import re
import traceback

import numpy as np
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import (
    QEvent,
    QObject,
    Qt,
    qInfo,
    qWarning,
    qCritical,
    QTimer,
    qDebug,
    pyqtSignal,
    QRegExp
)
from PyQt5.QtWidgets import (
    QWidget,
    QFileDialog,
    QTreeView,
    QHBoxLayout,
    QVBoxLayout,
    QAbstractItemView,
    QMessageBox,
    QApplication,
    QLabel,
    QInputDialog,
    QButtonGroup,
    QSizePolicy,
    QHeaderView,
    QToolButton,
    QPushButton,
    QFrame,
    QSplitter,
    QSpacerItem,
    QPlainTextEdit,
    QComboBox
)
from PyQt5.QtGui import QKeySequence, QTextCursor

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers
from MasterProject.Client_modules.Desq_GUI.scripts.DirectoryTreePanel import DirectoryTreePanel


class JSONTextEdit(QPlainTextEdit):
    """A text editor specifically for JSON editing with validation and improved editing features."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setObjectName("json_editor")

    def set_json(self, json_data):
        """Set the text to the pretty-printed JSON data."""
        if json_data is None:
            self.setPlainText("")
            return

        try:
            # Format the JSON with indentation for readability
            formatted_json = json.dumps(json_data, indent=4, default=self.json_serializer)
            self.setPlainText(formatted_json)
        except Exception as e:
            qDebug(f"Error formatting JSON: {str(e)}")
            QMessageBox.warning(self, "JSON Error", f"Error formatting JSON: {str(e)}")

    def get_json(self):
        """Parse the text as JSON and return the data structure."""
        try:
            text = self.toPlainText().strip()
            if not text:
                return {}

            # Handle trailing commas by preprocessing the JSON text
            # This regex finds trailing commas in arrays and objects
            text = re.sub(r',\s*([}\]])', r'\1', text)

            return json.loads(text)
        except json.JSONDecodeError as e:
            line_no = e.lineno
            col_no = e.colno
            QMessageBox.warning(self, "JSON Parse Error",
                                f"Error parsing JSON at line {line_no}, column {col_no}: {str(e)}")
            return None

    def json_serializer(self, obj):
        """Custom serializer for JSON dumps to handle numpy types."""
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return str(obj)

    def keyPressEvent(self, event):
        """Handle key presses, particularly to support proper JSON indentation."""
        # Handle tab key to preserve indentation
        if event.key() == Qt.Key_Tab:
            # Insert 4 spaces instead of tab
            cursor = self.textCursor()
            cursor.insertText("    ")
            return

        # Handle Enter key to preserve indentation
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()

            # Get current line's indentation
            indentation = ""
            for char in text:
                if char == ' ' or char == '\t':
                    indentation += char
                else:
                    break

            # Default QPlainTextEdit behavior
            super().keyPressEvent(event)

            # Add the same indentation to the new line
            cursor = self.textCursor()
            cursor.insertText(indentation)

            # Add extra indentation if the line ends with '{' or '['
            if text.rstrip().endswith('{') or text.rstrip().endswith('['):
                cursor.insertText("    ")

            return

        # For all other keys, use default behavior
        super().keyPressEvent(event)


class QConfigTreePanel(QWidget):
    """
    A widget for viewing and editing configuration parameters from JSON files.

    Displays configuration parameters (nested dictionaries of key-value pairs)
    in a tree view and allows editing them directly in the UI.
    """

    # Signal emitted when a parameter is changed
    parameter_changed = pyqtSignal(str, object)

    # Additional signals from original implementation
    update_voltage_panel = pyqtSignal()
    update_runtime_prediction = pyqtSignal(dict)

    def __init__(self, app=None, name="Global", type=None, parent=None, config=None, workspace=None):
        """
        Initialize the QConfigTreePanel.

        Args:
            app: The main application instance (optional)
            name: The name of the panel to display in the header
            type: Type information (from original implementation)
            parent: The parent widget
            config: The dictionary containing the configuration to set (can be None)
        """
        super(QConfigTreePanel, self).__init__(parent)

        self.app = app
        self.type = type
        self.config = config if config else {}
        self.current_file_path = None
        self.current_directory = None
        self.has_unsaved_changes = False
        self.current_view = "tree"  # Default view: "tree" or "json"
        self.workspace = workspace
        self.name = name

        self.setObjectName("config_tree_panel")

        # Setup the UI
        self.setup_ui()

    def setup_ui(self):
        """Set up the UI components."""
        # Main layout - reduced margins for compact display
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(6, 0, 6, 3)
        self.main_layout.setSpacing(2)
        self.setLayout(self.main_layout)
        self.setMinimumSize(215, 0)

        # Panel name label - compact style
        name = self.name if self.name else "Experiment"
        self.config_title_label = QLabel(name + " Config")
        self.config_title_label.setObjectName("config_title_label")
        self.config_title_label.setAlignment(Qt.AlignCenter)
        self.config_title_label.setMaximumHeight(25)  # Fixed height
        self.main_layout.addWidget(self.config_title_label)

        # Create splitter for directory tree and config content
        self.splitter = QSplitter(self)
        self.splitter.setOpaqueResize(True)
        self.splitter.setHandleWidth(6)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setObjectName("config_panel_splitter")
        self.splitter.setOrientation(Qt.Vertical)

        # ====== Directory Tree Section ======
        self.directory_section = QWidget()
        directory_layout = QVBoxLayout(self.directory_section)
        directory_layout.setContentsMargins(0, 0, 0, 0)
        directory_layout.setSpacing(2)

        # Create Directory Tree Panel with JSON filter
        self.directory_tree = DirectoryTreePanel(self, file_filters=['.json'], workspace=self.workspace)
        directory_layout.addWidget(self.directory_tree)

        # Add directory section to splitter
        self.splitter.addWidget(self.directory_section)

        # ====== Config Content Section ======
        self.config_content_section = QWidget()
        config_content_layout = QVBoxLayout(self.config_content_section)
        config_content_layout.setContentsMargins(0, 0, 0, 0)
        config_content_layout.setSpacing(2)

        # Config toolbar - compact
        self.config_toolbar_layout = QHBoxLayout()
        self.config_toolbar_layout.setContentsMargins(0, 2, 0, 2)
        self.config_toolbar_layout.setSpacing(0)

        # New file button (moved from directory toolbar)
        self.new_file_button = Helpers.create_button("New", "new_file_config", True, self)
        self.new_file_button.setToolTip("Create New Config File")
        self.config_toolbar_layout.addWidget(self.new_file_button)

        # Save button
        self.save_config_button = Helpers.create_button("Save", "save_config", True, self)
        self.save_config_button.setToolTip("Save Config")
        self.config_toolbar_layout.addWidget(self.save_config_button)

        # Save As button
        self.save_as_config_button = Helpers.create_button("Save As", "save_as_config", True, self)
        self.save_as_config_button.setToolTip("Save Config As...")
        self.config_toolbar_layout.addWidget(self.save_as_config_button)

        # Copy button
        self.copy_config_button = Helpers.create_button("Copy", "copy_config", True, self)
        self.copy_config_button.setToolTip("Copy Config to Clipboard")
        self.config_toolbar_layout.addWidget(self.copy_config_button)

        config_content_layout.addLayout(self.config_toolbar_layout)

        # View dropdown selector instead of toggle buttons
        self.view_selector = QComboBox(self)
        self.view_selector.addItem("Table", "tree")
        self.view_selector.addItem("Json", "json")
        self.view_selector.setCurrentIndex(0)  # Default to Tree View
        self.view_selector.setFixedWidth(100)
        self.view_selector.setToolTip("Select View Mode")

        config_content_layout.addWidget(self.view_selector)

        # Config content stack - contains tree view and JSON editor
        self.config_stack_layout = QVBoxLayout()
        self.config_stack_layout.setContentsMargins(0, 0, 0, 0)
        self.config_stack_layout.setSpacing(0)

        # Create and configure the tree view (from old implementation)
        self.tree = QTreeView()
        self.tree.setObjectName("config_tree")

        # Create the model
        self.model = QtGui.QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.tree.setModel(self.model)

        # Tree View settings
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.setHeaderHidden(False)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.tree.setIndentation(8)

        # Set header properties
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        # Add tree view to layout
        self.config_stack_layout.addWidget(self.tree)

        # Create JSON editor
        self.json_editor = JSONTextEdit()
        self.config_stack_layout.addWidget(self.json_editor)
        self.json_editor.hide()  # Start with tree view

        config_content_layout.addLayout(self.config_stack_layout)

        # Status bar with unsaved indicator and current file path
        self.status_layout = QHBoxLayout()
        self.status_layout.setContentsMargins(0, 3, 0, 0)
        self.unsaved_label = QLabel("")
        self.status_layout.addWidget(self.unsaved_label)

        # self.file_path_label = QLabel("")
        # self.file_path_label.setAlignment(Qt.AlignRight)
        # self.status_layout.addWidget(self.file_path_label)

        config_content_layout.addLayout(self.status_layout)

        # Add config section to splitter
        self.splitter.addWidget(self.config_content_section)

        # Add splitter to main layout
        self.main_layout.addWidget(self.splitter)

        # Set initial splitter sizes (30% directory, 70% config)
        self.splitter.setSizes([300, 700])

        # Connect model change signal (from old implementation)
        self.model.itemChanged.connect(self.handleItemChanged)

        # Setup signals
        self.setup_signals()

        # Load initial config
        self.populate_tree()

        # Update button states
        self.update_button_states()

    def setup_signals(self):
        """Setup signal connections for UI elements."""
        # Directory tree signals
        self.directory_tree.file_selected.connect(self.load_config)

        # Config view signals - use combobox instead of buttons
        self.view_selector.currentIndexChanged.connect(self.handle_view_selection_changed)

        # Config operation signals
        self.new_file_button.clicked.connect(self.create_new_config)
        self.save_config_button.clicked.connect(self.save_config)
        self.save_as_config_button.clicked.connect(self.save_config_as)
        self.copy_config_button.clicked.connect(self.copy_config)

        # JSON editor signals
        self.json_editor.textChanged.connect(lambda: self.mark_unsaved_changes(True))

    def handle_view_selection_changed(self, index):
        """Handle the view selector dropdown change"""
        view_type = self.view_selector.itemData(index)
        self.switch_view(view_type)

    def switch_view(self, view_type):
        """
        Switch between tree view and JSON editor view.

        Args:
            view_type: "tree" or "json"
        """
        if view_type == self.current_view:
            return

        if view_type == "tree":
            # Switch from JSON to Tree - validate and update config
            if self.current_view == "json":
                json_data = self.json_editor.get_json()
                if json_data is not None:  # Only update if valid JSON
                    self.config = json_data
                    self.populate_tree()

            # Update UI
            self.tree.show()
            self.json_editor.hide()
            self.view_selector.setCurrentIndex(0)
            self.current_view = "tree"

        else:  # view_type == "json"
            # Update JSON editor with current config
            self.json_editor.set_json(self.config)

            # Update UI
            self.tree.hide()
            self.json_editor.show()
            self.view_selector.setCurrentIndex(1)
            self.current_view = "json"

    def populate_tree(self, allow_voltage_editing=True):
        """
        Populates the `tree` QTreeView widget with the configuration data by iterating through the dictionary and
        creating a QStandardItem for each Key (Parameter) and Value.

        Handles both nested configs (e.g., {"Category": {"field": 10}}) and flat configs (e.g., {"field": 10}).
        """
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])

        for category, params in self.config.items():
            if isinstance(params, dict):
                # Nested dictionary - add as category with children
                if not params:  # Skip empty dicts
                    continue

                parent = QtGui.QStandardItem(category)
                parent.setFlags(QtCore.Qt.NoItemFlags)  # Categories are not selectable

                self.add_tree_items_recursive(parent, params, allow_voltage_editing)

                # For nested items, append just the parent (original behavior)
                # The parent already has children added via add_tree_items_recursive
                self.model.appendRow(parent)
            else:
                # Flat value - add as editable key-value pair at top level
                if isinstance(params, (np.integer, np.floating, np.bool_)):
                    params = params.item()

                key_item = QtGui.QStandardItem(category)
                key_item.setFlags(QtCore.Qt.ItemIsEnabled)

                value_item = QtGui.QStandardItem(str(params))
                value_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable)

                # For flat items, append as a row with two columns
                self.model.appendRow([key_item, value_item])

        self.tree.expandAll()

    def update_config_dict(self, update_config, reset=False):
        """
        Updates the config dictionary with a new one.
        If Experiment panel, only consider Experiment Config, otherwise, use Base Config.
        """
        if reset:
            self.config = {}

        if self.type == "Experiment" and "Experiment Config" in update_config:
            # Flatten Experiment Config
            update_config = {**update_config, **update_config["Experiment Config"]}
        elif self.type == "Global" and "Base Config" in update_config:
            # Flatten Base Config
            update_config = {**update_config, **update_config["Base Config"]}

        update_config.pop("Experiment Config", None)
        update_config.pop("Base Config", None)

        self.config.update(update_config)
        self.populate_tree()

    def add_tree_items_recursive(self, parent_item, data, allow_voltage_editing):
        """
        Recursively adds items to the tree structure.

        Implementation from the original version.
        """
        for key, value in sorted(data.items()):
            # if not allow_voltage_editing and (str(key).startswith("Voltage") or str(key) == "DACs"):
            #     continue
            key_item = QtGui.QStandardItem(str(key))
            key_item.setFlags(QtCore.Qt.ItemIsEnabled)

            if isinstance(value, dict):
                value_item = QtGui.QStandardItem("")  # Placeholder, not editable
                value_item.setFlags(QtCore.Qt.NoItemFlags)
                parent_item.appendRow([key_item, value_item])
                self.add_tree_items_recursive(key_item, value, allow_voltage_editing)
            else:
                # Convert numpy types to Python types for display and editing
                if isinstance(value, (np.integer, np.floating, np.bool_)):
                    value = value.item()
                value_item = QtGui.QStandardItem(str(value))
                value_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable)
                parent_item.appendRow([key_item, value_item])

    def handleItemChanged(self, item):
        """
        Called when an item in the model is changed by editing.

        Handles both flat and nested configs.
        """
        if item.column() != 1:  # Only handle value column
            return

        parent = item.parent()

        # Handle flat config (top-level items)
        if parent is None:
            # Get key from first column
            key_item = self.model.item(item.row(), 0)
            if key_item is None:
                return
            key = key_item.text()
            value_text = item.text()

            # Try to convert string to the appropriate Python type
            try:
                value = ast.literal_eval(value_text)
            except (ValueError, SyntaxError):
                value = value_text

            # Update value in top-level config dictionary
            self.config[key] = value

            # Mark that we have unsaved changes
            self.mark_unsaved_changes(True)

            # Emit the parameter_changed signal
            self.parameter_changed.emit(key, value)

            # Emit runtime prediction signal with updated config
            self.update_runtime_prediction.emit(self.config)

            # If the parameter changed is a voltage, emit the update_voltage_panel signal
            if key.startswith("Voltage"):
                self.update_voltage_panel.emit()

            return

        # Handle nested config (existing logic)
        # Get key from first column
        key_item = parent.child(item.row(), 0)
        key = key_item.text()
        value_text = item.text()

        # Try to convert string to the appropriate Python type
        try:
            # Try to evaluate as a Python literal
            value = ast.literal_eval(value_text)
        except (ValueError, SyntaxError):
            # If evaluation fails, treat as string
            value = value_text

        # Build path to the item in the config dictionary
        path = []
        current = parent
        while current is not None and current.text():
            path.insert(0, current.text())
            current = current.parent()

        # Navigate to the correct nested dictionary in config
        config_ref = self.config
        for part in path:
            if part in config_ref:
                config_ref = config_ref[part]
            else:
                qWarning(f"Path part '{part}' not found in config")
                return

        # Update value in config dictionary
        config_ref[key] = value

        # Mark that we have unsaved changes
        self.mark_unsaved_changes(True)

        # Emit the parameter_changed signal with the full path
        full_path = ".".join(path + [key])
        self.parameter_changed.emit(full_path, value)

        # Emit runtime prediction signal with updated config
        self.update_runtime_prediction.emit(self.config)

        # If the parameter changed is a voltage, emit the update_voltage_panel signal
        if key.startswith("Voltage") or any(p.startswith("Voltage") for p in path) or "DACs" in path:
            self.update_voltage_panel.emit()

    # def update_file_path_label(self):
    #     """Update the file path display in the status bar."""
    #     if self.current_file_path:
    #         file_name = os.path.basename(self.current_file_path)
    #         dir_name = os.path.dirname(self.current_file_path)
    #         if len(dir_name) > 30:
    #             dir_name = "..." + dir_name[-30:]
    #         self.file_path_label.setText(f"{dir_name}/{file_name}")
    #     else:
    #         self.file_path_label.setText("No file loaded")

    def mark_unsaved_changes(self, has_changes):
        """
        Mark whether the current configuration has unsaved changes.

        Args:
            has_changes: True if there are unsaved changes, False otherwise
        """
        self.has_unsaved_changes = has_changes
        if has_changes:
            self.unsaved_label.setText("● Unsaved Changes")
            self.unsaved_label.setStyleSheet("color: red;")
        else:
            self.unsaved_label.setText("")
            self.unsaved_label.setStyleSheet("")

        # Update button states whenever unsaved changes state changes
        self.update_button_states()

    def update_button_states(self):
        """
        Update the enabled/disabled state of Save and Save As buttons based on whether
        there is a currently selected file.

        Logic:
        - Save button: Enabled only if a file is currently loaded (self.current_file_path is not None)
        - Save As button: Always enabled
        """
        # Save button should only be enabled if we have a current file path
        self.save_config_button.setEnabled(self.current_file_path is not None)

        # Save As button is always enabled
        self.save_as_config_button.setEnabled(True)

    def create_new_config(self):
        """
        Create a new configuration file with a default name and prompt user for save location.
        The file is created with an empty config.
        """
        # Check for unsaved changes
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Would you like to save them first?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                self.save_config()
                if self.has_unsaved_changes:  # If save failed, abort new config
                    return
            elif reply == QMessageBox.Cancel:
                return

        # Generate default filename with timestamp
        date_time_now = datetime.datetime.now()
        date_time_string = date_time_now.strftime("%Y_%m_%d_%H_%M_%S")
        default_folder_name = self.name if self.name else "config"
        default_filename = default_folder_name + "_" + date_time_string + '.json'

        # Get the current directory from the directory tree
        current_dir = self.directory_tree.get_current_directory()
        config_filename = os.path.join(current_dir, default_filename)

        # Prompt for save location with default filename
        file_path = QFileDialog.getSaveFileName(
            self,
            "Create New Config File",
            config_filename,
            "JSON Files (*.json)"
        )[0]

        if file_path:
            # Create empty config
            self.config = {}

            # Save the empty config to the file
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.config, f, indent=4)

                # Set this as the current file
                self.current_file_path = file_path

                # Update UI based on current view
                if self.current_view == "tree":
                    self.populate_tree()
                else:
                    self.json_editor.set_json(self.config)

                # Reset unsaved changes indicator
                self.mark_unsaved_changes(False)

                # Refresh directory view to show the new file
                self.directory_tree.refresh_view()

                qInfo(f"Created new configuration file: {file_path}")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create config file: {str(e)}")
                qCritical(f"Error creating config file: {str(e)}")

    def save_config(self):
        """
        Save the configuration to the current JSON file.
        If no file is currently open, prompt for a save location.
        """
        if self.current_file_path:
            # Save to the existing file
            self._save_config_to_file(self.current_file_path)
        else:
            # No current file, prompt for save location
            self.save_config_as()

    def save_config_as(self):
        """
        Save the configuration to a new JSON file.
        """
        # Prompt for save location
        file_path = QFileDialog.getSaveFileName(
            self,
            "Save Config File",
            self.directory_tree.get_current_directory() or os.path.expanduser("~"),
            "JSON Files (*.json)"
        )[0]

        if file_path:
            self._save_config_to_file(file_path)

    def _save_config_to_file(self, file_path):
        """
        Internal method to save configuration to a file.

        Args:
            file_path: Path to save the file.
        """
        # If in JSON view, update config from editor
        if self.current_view == "json":
            json_data = self.json_editor.get_json()
            if json_data is None:
                return  # JSON parse error
            self.config = json_data

        try:
            with open(file_path, 'w') as f:
                json.dump(self.config, f, indent=4, default=self.json_serializer)

            # Update current file path
            self.current_file_path = file_path

            # Reset unsaved changes indicator (this also updates button states)
            self.mark_unsaved_changes(False)

            # Update file path label
            # self.update_file_path_label()

            # Refresh directory view to show changes
            self.directory_tree.refresh_view()

            qInfo(f"Configuration saved to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {str(e)}")

    def json_serializer(self, obj):
        """Custom JSON serializer for handling numpy types."""
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return str(obj)

    def copy_config(self):
        """Copy the current configuration to the clipboard."""
        try:
            # Get the JSON string based on the current view
            if self.current_view == "json":
                json_string = self.json_editor.toPlainText()
            else:
                json_string = json.dumps(
                    self.config,
                    indent=4,
                    default=self.json_serializer
                )

            # Copy to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(json_string)

            # Visual feedback
            qInfo("Current configuration copied to clipboard!")
            self.copy_config_button.setText("Copied!")
            self.copy_config_button.setStyleSheet("color: green;")
            QTimer.singleShot(2000, lambda: self.copy_config_button.setText("Copy"))
            QTimer.singleShot(2000, lambda: self.copy_config_button.setStyleSheet(""))

        except Exception as e:
            qCritical(f"Error copying configuration: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to copy configuration: {str(e)}")

    def load_config(self, file_path=None):
        """
        Load configuration from a JSON file.

        Args:
            file_path: Path to the JSON file. If None, a file dialog will be shown.
        """
        if file_path is None:
            file_path = QFileDialog.getOpenFileName(
                self,
                "Select Config File",
                self.directory_tree.get_current_directory() or os.path.expanduser("~"),
                "JSON Files (*.json)"
            )[0]

        if file_path:
            # Check for unsaved changes
            if self.has_unsaved_changes:
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Would you like to save them first?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Save
                )

                if reply == QMessageBox.Save:
                    self.save_config()
                    if self.has_unsaved_changes:  # If save failed, abort load
                        return
                elif reply == QMessageBox.Cancel:
                    return

            try:
                with open(file_path, "r") as json_file:
                    self.update_config_dict(json.load(json_file), reset=True)

                self.current_file_path = file_path

                # Update UI based on the current view
                if self.current_view == "tree":
                    self.populate_tree()
                else:
                    self.json_editor.set_json(self.config)

                # Update file path label
                # self.update_file_path_label()

                # Emit runtime prediction signal
                self.update_runtime_prediction.emit(self.config)

                # Reset unsaved changes indicator (this also updates button states)
                self.mark_unsaved_changes(False)

                qInfo(f"Config loaded from {file_path}")

            except Exception as e:
                qCritical(f"Error loading config from {file_path}: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to load config: {str(e)}")

    def set_config(self, config_update=None):
        """
        Updates the config and repopulates the tree.
        Maintains compatibility with the original implementation.

        Args:
            config_update: A dictionary containing the configuration to update to.
        """
        if config_update is not None:
            self.config = config_update

        if self.current_view == "tree":
            self.populate_tree()
        else:
            self.json_editor.set_json(self.config)

        # Clear current file path since config was set programmatically
        self.current_file_path = None

        # Reset unsaved changes indicator (this also updates button states)
        self.mark_unsaved_changes(False)

    def get_config(self):
        """
        Returns the current configuration dictionary.
        Maintains compatibility with the original implementation.

        Returns:
            The configuration dictionary.
        """
        # If in JSON view, update config from editor first
        if self.current_view == "json":
            json_data = self.json_editor.get_json()
            if json_data is not None:
                self.config = json_data

        return self.config

    def paste_config(self):
        """
        Creates a text prompt for the user to paste in a dictionary that is then diff'd with the current config.
        Maintains compatibility with the original implementation.
        This method is kept for compatibility but not connected to any UI elements.
        """
        text, ok = QInputDialog.getMultiLineText(
            self,
            "Paste Config",
            "Paste config in dictionary format to be diff'd with current config. (ex: {'field': 50})"
        )
        if not ok or not text.strip():
            return

        try:
            # Clean up the text for JSON parsing
            str_dict = text.strip().replace("\'", '\"')
            str_dict = re.sub(r"np\.int64\((-?\d+)\)", r"\1", str_dict)
            str_dict = re.sub(r"np\.float64\((-?[\d\.]+)\)", r"\1", str_dict)
            str_dict = str_dict.replace("False", "false").replace("True", "true").replace("None", "null")

            update_config = json.loads(str_dict)

            # Update the config
            self.config.update(update_config)

            # Update UI
            if self.current_view == "tree":
                self.populate_tree()
            else:
                self.json_editor.set_json(self.config)

            # Mark that we have unsaved changes
            self.mark_unsaved_changes(True)

            # Emit runtime prediction
            self.update_runtime_prediction.emit(self.config)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error parsing pasted configuration: {e}")
            qCritical(f"Error parsing pasted configuration: {str(e)}")
            traceback.print_exc()