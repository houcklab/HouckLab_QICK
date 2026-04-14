"""
==================
ConfigTreePanel.py
==================

A PyQt5 widget for viewing and editing configuration parameters from JSON files.

This module provides a comprehensive configuration management interface with the
following features:

1. Directory tree panel to navigate and select JSON files
2. Toggle between tree and JSON text editor views
3. Support for saving, loading, and copying configuration
4. **Builder mode** for combining multiple JSON configs with deep merging

.. note::
    The builder mode uses deep merging via ConfigManager, which means nested
    dictionaries are merged recursively rather than overwritten.

:var np: NumPy module for handling numpy types in JSON serialization
:vartype np: module

.. seealso::
    :class:`DirectoryTreePanel` for file navigation
    :class:`ConfigManager` for configuration merging logic
"""

from __future__ import annotations

import os
import json
import ast
import datetime
import re
import traceback
from typing import Any, Dict, List, Optional, Union

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
    QHeaderView,
    QSplitter,
    QPlainTextEdit,
    QComboBox,
    QCheckBox,
    QListWidget,
    QListWidgetItem
)
from PyQt5.QtGui import QKeySequence

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers
from MasterProject.Client_modules.Desq_GUI.scripts.DirectoryTreePanel import DirectoryTreePanel
from MasterProject.Client_modules.Desq_GUI.scripts.ConfigManager import ConfigManager


class JSONTextEdit(QPlainTextEdit):
    """
    A text editor specifically for JSON editing with validation and improved editing features.

    This widget extends QPlainTextEdit to provide JSON-specific functionality including:

    - Automatic indentation preservation when pressing Enter
    - Tab key inserts 4 spaces instead of tab character
    - Extra indentation after opening braces/brackets
    - Custom serialization for numpy types
    - Tolerance for trailing commas in JSON

    :ivar parent: Parent widget reference
    :vartype parent: Optional[QWidget]

    .. note::
        The JSON parser in :meth:`get_json` preprocesses text to remove trailing
        commas, which are not valid JSON but commonly appear in hand-edited configs.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the JSONTextEdit widget.

        :param parent: The parent widget, defaults to None
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setObjectName("json_editor")

    def set_json(self, json_data: Optional[Dict[str, Any]]) -> None:
        """
        Set the text to the pretty-printed JSON data.

        Formats the provided dictionary as indented JSON and displays it
        in the text editor. Handles numpy types via custom serializer.

        :param json_data: The JSON data to display, or None to clear the editor
        :type json_data: Optional[Dict[str, Any]]

        .. note::
            If json_data is None, the editor is cleared.
        """
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

    def get_json(self) -> Optional[Dict[str, Any]]:
        """
        Parse the text as JSON and return the data structure.

        Preprocesses the text to handle trailing commas before parsing.
        Shows a warning dialog if parsing fails.

        :returns: The parsed JSON data, empty dict if text is empty, or None on parse error
        :rtype: Optional[Dict[str, Any]]

        :raises: Shows QMessageBox on JSONDecodeError (does not raise to caller)
        """
        try:
            text = self.toPlainText().strip()
            if not text:
                return {}

            # Handle trailing commas by preprocessing the JSON text
            # This regex finds trailing commas before closing braces/brackets
            text = re.sub(r',\s*([}\]])', r'\1', text)

            return json.loads(text)
        except json.JSONDecodeError as e:
            line_no = e.lineno
            col_no = e.colno
            QMessageBox.warning(self, "JSON Parse Error",
                                f"Error parsing JSON at line {line_no}, column {col_no}: {str(e)}")
            return None

    def json_serializer(self, obj: Any) -> Union[int, float, bool, str]:
        """
        Custom serializer for JSON dumps to handle numpy types.

        Converts numpy scalar types to their Python equivalents for
        JSON serialization. Falls back to string representation for
        unknown types.

        :param obj: The object to serialize
        :type obj: Any
        :returns: Python-native representation of the object
        :rtype: Union[int, float, bool, str]

        .. note::
            This method is used as the ``default`` argument to ``json.dumps()``.
        """
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return str(obj)

    def keyPressEvent(self, event: QKeySequence) -> None:
        """
        Handle key presses, particularly to support proper JSON indentation.

        Overrides default behavior for:

        - **Tab**: Inserts 4 spaces instead of tab character
        - **Enter/Return**: Preserves current line indentation and adds
          extra indentation after ``{`` or ``[``

        :param event: The key press event
        :type event: QKeySequence
        """
        # Handle tab key - insert 4 spaces instead of tab character
        if event.key() == Qt.Key_Tab:
            cursor = self.textCursor()
            cursor.insertText("    ")
            return

        # Handle Enter key to preserve indentation
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()

            # Extract current line's leading whitespace (indentation)
            indentation = ""
            for char in text:
                if char == ' ' or char == '\t':
                    indentation += char
                else:
                    break

            # Default QPlainTextEdit behavior - insert newline
            super().keyPressEvent(event)

            # Add the same indentation to the new line
            cursor = self.textCursor()
            cursor.insertText(indentation)

            # Add extra indentation if the line ends with '{' or '['
            # This provides automatic nesting for JSON structures
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

    **Features:**

    - **Normal mode**: Single-click to select and load a config file
    - **Builder mode**: Double-click to add configs to a merged configuration
    - Toggle between tree view and JSON text editor
    - Save, load, copy configuration operations
    - Visual indicator for unsaved changes

    :ivar app: The main application instance
    :vartype app: Optional[Any]
    :ivar type: Panel type identifier ("Experiment" or "Global")
    :vartype type: Optional[str]
    :ivar _config: Internal configuration dictionary storage
    :vartype _config: Dict[str, Any]
    :ivar current_file_path: Path to the currently loaded config file
    :vartype current_file_path: Optional[str]
    :ivar current_directory: Current working directory
    :vartype current_directory: Optional[str]
    :ivar has_unsaved_changes: Flag indicating unsaved modifications
    :vartype has_unsaved_changes: bool
    :ivar current_view: Current view mode ("tree" or "json")
    :vartype current_view: str
    :ivar workspace: Workspace path for file operations
    :vartype workspace: Optional[str]
    :ivar name: Display name for the panel header
    :vartype name: str
    :ivar builder_mode: Whether builder mode is active
    :vartype builder_mode: bool
    :ivar config_manager: Manager for merging multiple configs
    :vartype config_manager: ConfigManager
    :ivar checked_config_files: Maps file paths to their loaded config dicts
    :vartype checked_config_files: Dict[str, Dict[str, Any]]

    .. note::
        In builder mode, the tree view becomes read-only to prevent
        editing of the merged configuration directly.

    .. seealso::
        :class:`JSONTextEdit` for the JSON editor component
        :class:`ConfigManager` for deep merge functionality
    """

    #: Signal emitted when a parameter value is changed.
    #: Emits (parameter_path: str, new_value: object)
    parameter_changed = pyqtSignal(str, object)

    #: Signal to trigger voltage panel update when voltage parameters change
    update_voltage_panel = pyqtSignal()

    #: Signal emitted with updated config for runtime prediction
    update_runtime_prediction = pyqtSignal(dict)

    def __init__(
        self,
        app: Optional[Any] = None,
        name: str = "Global",
        type: Optional[str] = None,
        parent: Optional[QWidget] = None,
        config: Optional[Dict[str, Any]] = None,
        workspace: Optional[str] = None
    ) -> None:
        """
        Initialize the QConfigTreePanel.

        :param app: The main application instance, defaults to None
        :type app: Optional[Any]
        :param name: The name of the panel to display in the header, defaults to "Global"
        :type name: str
        :param type: Type information ("Experiment" or "Global"), defaults to None
        :type type: Optional[str]
        :param parent: The parent widget, defaults to None
        :type parent: Optional[QWidget]
        :param config: The dictionary containing the initial configuration, defaults to None
        :type config: Optional[Dict[str, Any]]
        :param workspace: Workspace path for file operations, defaults to None
        :type workspace: Optional[str]

        .. note::
            The ``type`` parameter affects how configurations are flattened
            when loading. "Experiment" flattens "Experiment Config" sections,
            while "Global" flattens "Base Config" sections.
        """
        super(QConfigTreePanel, self).__init__(parent)

        self.app = app
        self.type = type
        self._config: Dict[str, Any] = config if config else {}
        self.current_file_path: Optional[str] = None
        self.current_directory: Optional[str] = None
        self.has_unsaved_changes: bool = False
        self.current_view: str = "tree"  # Default view: "tree" or "json"
        self.workspace = workspace
        self.name = name

        # Builder mode attributes
        self.builder_mode: bool = False
        self.config_manager = ConfigManager()
        self.checked_config_files: Dict[str, Dict[str, Any]] = {}  # Maps file path -> config dict

        self.setObjectName("config_tree_panel")

        # Setup the UI
        self.setup_ui()

    def setup_ui(self) -> None:
        """
        Set up the UI components.

        Creates and configures all UI elements including:

        - Main layout with compact margins
        - Title label
        - Directory tree panel for file navigation
        - Config toolbar with New, Save, Save As, Copy buttons
        - View selector dropdown and Builder mode checkbox
        - Tree view and JSON editor (stacked)
        - Builder mode config list
        - Status bar with unsaved changes indicator

        The layout uses a vertical splitter to allow resizing between
        the directory tree and config content sections.
        """
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

        # Config toolbar - compact layout for action buttons
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

        # View selector and Builder mode checkbox layout
        self.view_mode_layout = QHBoxLayout()
        self.view_mode_layout.setContentsMargins(0, 2, 0, 2)
        self.view_mode_layout.setSpacing(4)

        # View dropdown selector
        self.view_selector = QComboBox(self)
        self.view_selector.addItem("Table", "tree")
        self.view_selector.addItem("Json", "json")
        self.view_selector.setCurrentIndex(0)  # Default to Tree View
        self.view_selector.setFixedWidth(100)
        self.view_selector.setToolTip("Select View Mode")
        self.view_mode_layout.addWidget(self.view_selector)

        # Builder mode checkbox
        self.builder_mode_checkbox = QCheckBox("Build")
        self.builder_mode_checkbox.setToolTip(
            "Enable to combine multiple configs.\n"
            "Double-click files to add them to the merged config."
        )
        self.view_mode_layout.addWidget(self.builder_mode_checkbox)
        self.view_mode_layout.addStretch()

        config_content_layout.addLayout(self.view_mode_layout)

        # ====== Builder Mode: Config List Section ======
        self.builder_list_widget = QWidget()
        builder_list_layout = QVBoxLayout(self.builder_list_widget)
        builder_list_layout.setContentsMargins(0, 0, 0, 0)
        builder_list_layout.setSpacing(2)

        # Label for checked configs
        self.checked_configs_label = QLabel("Added Configs:")
        self.checked_configs_label.setObjectName("checked_configs_label")
        builder_list_layout.addWidget(self.checked_configs_label)

        # List widget for showing checked configs
        self.checked_configs_list = QListWidget()
        self.checked_configs_list.setObjectName("checked_configs_list")
        # NOTE: Max height removed to allow splitter resizing
        # self.checked_configs_list.setMaximumHeight(150)
        builder_list_layout.addWidget(self.checked_configs_list)

        # ====== Config Viewer Section ======
        self.config_viewer_widget = QWidget()
        config_viewer_layout = QVBoxLayout(self.config_viewer_widget)
        config_viewer_layout.setContentsMargins(0, 0, 0, 0)
        config_viewer_layout.setSpacing(0)

        # Create and configure the tree view (from old implementation)
        self.tree = QTreeView()
        self.tree.setObjectName("config_tree")

        # Create the model for tree data
        self.model = QtGui.QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.tree.setModel(self.model)

        # Tree View settings
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.setHeaderHidden(False)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.tree.setIndentation(8)

        # Set header properties for responsive column sizing
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        # Add tree view to layout
        config_viewer_layout.addWidget(self.tree)

        # Create JSON editor (hidden by default)
        self.json_editor = JSONTextEdit()
        config_viewer_layout.addWidget(self.json_editor)
        self.json_editor.hide()  # Start with tree view

        # ====== Create Splitter for Builder Mode ======
        # This splitter divides the builder list from the config viewer
        self.builder_content_splitter = QSplitter(Qt.Vertical)
        self.builder_content_splitter.setOpaqueResize(True)
        self.builder_content_splitter.setHandleWidth(6)
        self.builder_content_splitter.setChildrenCollapsible(False)
        self.builder_content_splitter.setObjectName("builder_content_splitter")

        # Add widgets to the splitter
        self.builder_content_splitter.addWidget(self.builder_list_widget)
        self.builder_content_splitter.addWidget(self.config_viewer_widget)

        # Initially in normal mode - collapse the builder list (give it 0 size)
        self.builder_content_splitter.setSizes([0, 1000])

        # Hide the builder list widget initially
        self.builder_list_widget.hide()

        # Add the splitter to config content layout
        config_content_layout.addWidget(self.builder_content_splitter)

        # Status bar with unsaved indicator and current file path
        self.status_layout = QHBoxLayout()
        self.status_layout.setContentsMargins(0, 3, 0, 0)
        self.unsaved_label = QLabel("")
        self.status_layout.addWidget(self.unsaved_label)

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

    def setup_signals(self) -> None:
        """
        Setup signal connections for UI elements.

        Connects the following signals:

        - Directory tree file selection and double-click
        - View selector dropdown changes
        - Builder mode checkbox state changes
        - Checked configs list item double-click (for removal)
        - Config operation buttons (New, Save, Save As, Copy)
        - JSON editor text changes (for unsaved changes tracking)
        """
        # Directory tree signals - connect based on mode
        self.directory_tree.file_selected.connect(self.handle_file_selected)
        self.directory_tree.load_file.connect(self.handle_file_double_clicked)

        # Config view signals - use combobox instead of buttons
        self.view_selector.currentIndexChanged.connect(self.handle_view_selection_changed)

        # Builder mode checkbox
        self.builder_mode_checkbox.stateChanged.connect(self.toggle_builder_mode)

        # Checked configs list signals - double-click removes item
        self.checked_configs_list.itemDoubleClicked.connect(self.remove_checked_config_item)

        # Config operation signals
        self.new_file_button.clicked.connect(self.create_new_config)
        self.save_config_button.clicked.connect(self.save_config)
        self.save_as_config_button.clicked.connect(self.save_config_as)
        self.copy_config_button.clicked.connect(self.copy_config)

        # JSON editor signals - mark unsaved on any text change
        self.json_editor.textChanged.connect(lambda: self.mark_unsaved_changes(True))

    def toggle_builder_mode(self, state: int) -> None:
        """
        Toggle builder mode on/off.

        When entering builder mode:

        - Shows the builder list widget
        - Clears current file path
        - Displays merged configuration

        When exiting builder mode:

        - Hides the builder list widget
        - Clears all builder state (ConfigManager, checked files, list)
        - Resets to empty configuration

        :param state: Qt checkbox state (Qt.Checked or Qt.Unchecked)
        :type state: int
        """
        self.builder_mode = (state == Qt.Checked)

        if self.builder_mode:
            # Entering builder mode
            self.builder_list_widget.show()
            # Set splitter sizes to show both (30% builder list, 70% config viewer)
            self.builder_content_splitter.setSizes([300, 700])

            # Clear current single-file state
            self.current_file_path = None

            # Show the merged config
            self.update_merged_config_display()

            qInfo("Builder mode enabled - double-click files to add to merged config")
        else:
            # Exiting builder mode
            self.builder_list_widget.hide()
            # Set splitter sizes to give all space to config viewer
            self.builder_content_splitter.setSizes([0, 1000])

            # Clear builder state
            self.config_manager.clear()
            self.checked_config_files.clear()
            self.checked_configs_list.clear()

            # Reset to empty config
            self._config = {}
            self.populate_tree()
            self.json_editor.set_json(self._config)

            qInfo("Builder mode disabled")

        # Update button states
        self.update_button_states()
        self.mark_unsaved_changes(False)

    def handle_file_selected(self, file_path: str) -> None:
        """
        Handle single-click file selection - only works in normal mode.

        In builder mode, single-click does nothing (user must double-click
        to add files).

        :param file_path: Path to the selected file
        :type file_path: str
        """
        if not self.builder_mode:
            # Normal mode - load the file
            self.load_config(file_path)

    def handle_file_double_clicked(self, file_path: str) -> None:
        """
        Handle double-click on file - behavior depends on mode.

        - **Builder mode**: Adds the file to the checked configs for merging
        - **Normal mode**: Loads the file (same as single click)

        :param file_path: Path to the double-clicked file
        :type file_path: str
        """
        if self.builder_mode:
            # Builder mode - add to checked configs
            self.add_config_to_builder(file_path)
        else:
            # Normal mode - load the file (same as single click)
            self.load_config(file_path)

    def add_config_to_builder(self, file_path: str) -> None:
        """
        Add a config file to the builder's checked list.

        Loads the config file, flattens it based on panel type, stores it
        in the config manager, and updates the UI.

        :param file_path: Path to the config file to add
        :type file_path: str

        :raises: Shows QMessageBox on file read or JSON parse errors

        .. note::
            If the file is already added, this method returns early
            with an info log message.
        """
        # Check if already added
        if file_path in self.checked_config_files:
            qInfo(f"Config already added: {os.path.basename(file_path)}")
            return

        try:
            # Load the config file
            with open(file_path, "r") as json_file:
                config_data = json.load(json_file)

                # Flatten nested config sections based on panel type
                if self.type == "Experiment" and "Experiment Config" in config_data:
                    # Flatten Experiment Config - merge nested dict into top level
                    exp_cfg = config_data.pop("Experiment Config")
                    config_data.update(exp_cfg)
                elif self.type == "Global" and "Base Config" in config_data:
                    # Flatten Base Config - merge nested dict into top level
                    exp_cfg = config_data.pop("Base Config")
                    config_data.update(exp_cfg)

            # Store the config
            self.checked_config_files[file_path] = config_data

            # Add to config manager for deep merging
            file_name = os.path.basename(file_path)
            self.config_manager.check_config(file_path, config_data)

            # Add to list widget with remove button
            self.add_config_to_list_widget(file_path, file_name)

            # Update the merged config display
            self.update_merged_config_display()

            qInfo(f"Added config to builder: {file_name}")

        except Exception as e:
            qCritical(f"Error adding config to builder: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to add config: {str(e)}")

    def add_config_to_list_widget(self, file_path: str, file_name: str) -> None:
        """
        Add a config file entry to the list widget.

        Creates a list item with a remove button and filename label.
        The file path is stored in the item's UserRole data.

        :param file_path: Full path to the config file (stored in item data)
        :type file_path: str
        :param file_name: Display name for the config (shown in label)
        :type file_name: str
        """
        # Create list item
        item = QListWidgetItem()
        item.setData(Qt.UserRole, file_path)  # Store file path in item data

        # Create widget for the list item with filename and remove button
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(2, 2, 2, 2)
        item_layout.setSpacing(4)

        # Remove button (small "x" button)
        remove_btn = Helpers.create_button("x", "remove_config_button", True, self)
        remove_btn.setFixedSize(20, 20)
        remove_btn.setToolTip("Remove this config")
        remove_btn.clicked.connect(lambda: self.remove_checked_config(file_path))
        item_layout.addWidget(remove_btn)

        # Label with filename (tooltip shows full path)
        label = QLabel(file_name)
        label.setToolTip(file_path)
        item_layout.addWidget(label)

        # Add to list
        self.checked_configs_list.addItem(item)
        item.setSizeHint(item_widget.sizeHint())
        self.checked_configs_list.setItemWidget(item, item_widget)

    def remove_checked_config_item(self, item: QListWidgetItem) -> None:
        """
        Remove a config when list item is double-clicked.

        Retrieves the file path from the item's UserRole data and
        delegates to :meth:`remove_checked_config`.

        :param item: The list item that was double-clicked
        :type item: QListWidgetItem
        """
        file_path = item.data(Qt.UserRole)
        self.remove_checked_config(file_path)

    def remove_checked_config(self, file_path: str) -> None:
        """
        Remove a config from the builder's checked list.

        Removes the config from:

        1. Internal tracking dict (``checked_config_files``)
        2. Config manager
        3. List widget display

        Then updates the merged config display.

        :param file_path: Path to the config file to remove
        :type file_path: str

        .. note::
            If the file_path is not in checked_config_files, this
            method returns early without error.
        """
        if file_path not in self.checked_config_files:
            return

        # Remove from our tracking
        del self.checked_config_files[file_path]

        # Remove from config manager
        self.config_manager.uncheck_config(file_path)

        # Remove from list widget by finding matching item
        for i in range(self.checked_configs_list.count()):
            item = self.checked_configs_list.item(i)
            if item.data(Qt.UserRole) == file_path:
                self.checked_configs_list.takeItem(i)
                break

        # Update the merged config display
        self.update_merged_config_display()

        qInfo(f"Removed config from builder: {os.path.basename(file_path)}")

    def update_merged_config_display(self) -> None:
        """
        Update the display with the merged configuration.

        Retrieves the deep-merged config from ConfigManager and updates
        both the internal config and the current view display.

        Also updates the unsaved changes indicator based on whether
        any configs are currently checked.
        """
        # Get the merged config from the manager
        merged_config = self.config_manager.get_config()

        # Update internal config
        self._config = merged_config

        # Update the display based on current view
        self.populate_config_view()

        # Mark as having changes if we have any configs
        if len(self.checked_config_files) > 0:
            self.mark_unsaved_changes(True)
        else:
            self.mark_unsaved_changes(False)

    def handle_view_selection_changed(self, index: int) -> None:
        """
        Handle the view selector dropdown change.

        Retrieves the view type from the combo box item data and
        delegates to :meth:`switch_view`.

        :param index: The selected index in the combo box
        :type index: int
        """
        view_type = self.view_selector.itemData(index)
        self.switch_view(view_type)

    def switch_view(self, view_type: str) -> None:
        """
        Switch between tree view and JSON editor view.

        When switching from JSON to tree view, validates the JSON and
        updates the config if valid. When switching to JSON view,
        populates the editor with the current config.

        :param view_type: Target view type ("tree" or "json")
        :type view_type: str

        .. note::
            If the JSON is invalid when switching from JSON to tree,
            the config is not updated (preserves previous state).
        """
        if view_type == self.current_view:
            return

        if view_type == "tree":
            # Switch from JSON to Tree - validate and update config
            if self.current_view == "json" and not self.builder_mode:
                json_data = self.json_editor.get_json()
                if json_data is not None:  # Only update if valid JSON
                    self._config = json_data
                    self.populate_tree()

            # Update UI visibility
            self.tree.show()
            self.json_editor.hide()
            self.view_selector.setCurrentIndex(0)
            self.current_view = "tree"

        else:  # view_type == "json"
            # Update JSON editor with current config
            self.json_editor.set_json(self._config)

            # Update UI visibility
            self.tree.hide()
            self.json_editor.show()
            self.view_selector.setCurrentIndex(1)
            self.current_view = "json"

    def populate_config_view(self) -> None:
        """
        Populate the current view (tree or JSON) with the config data.

        Delegates to either :meth:`populate_tree` or
        :meth:`JSONTextEdit.set_json` based on current view mode.
        """
        if self.current_view == "json":
            self.json_editor.set_json(self._config)
        else:  # type is tree
            self.populate_tree()

    def populate_tree(self, allow_voltage_editing: bool = True) -> None:
        """
        Populate the tree QTreeView widget with the configuration data.

        Iterates through the dictionary and creates a QStandardItem for each
        Key (Parameter) and Value. Handles both nested configs
        (e.g., {"Category": {"field": 10}}) and flat configs (e.g., {"field": 10}).

        :param allow_voltage_editing: Whether voltage parameters should be editable,
                                      defaults to True (currently unused but kept
                                      for API compatibility)
        :type allow_voltage_editing: bool

        .. note::
            In builder mode, all values are made read-only regardless of
            the allow_voltage_editing parameter.

        .. note::
            Numpy scalar types are converted to Python types for display.
        """
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])

        # Iterate through top-level config items
        for category, params in self._config.items():
            if isinstance(params, dict):
                # Nested dictionary - add as category with children
                if not params:  # Skip empty dicts
                    continue

                parent = QtGui.QStandardItem(category)
                parent.setFlags(QtCore.Qt.NoItemFlags)  # Categories are not selectable/editable

                self.add_tree_items_recursive(parent, params, allow_voltage_editing)

                # For nested items, append just the parent
                # The parent already has children added via add_tree_items_recursive
                self.model.appendRow(parent)
            else:
                # Flat value - add as editable key-value pair at top level
                # Convert numpy types to Python types for display
                if isinstance(params, (np.integer, np.floating, np.bool_)):
                    params = params.item()

                key_item = QtGui.QStandardItem(category)
                key_item.setFlags(QtCore.Qt.ItemIsEnabled)

                value_item = QtGui.QStandardItem(str(params))

                # In builder mode, make values read-only
                if self.builder_mode:
                    value_item.setFlags(QtCore.Qt.ItemIsEnabled)
                else:
                    value_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable)

                # For flat items, append as a row with two columns
                self.model.appendRow([key_item, value_item])

        self.tree.expandAll()

    def update_config_dict(self, update_config: Dict[str, Any], reset: bool = False) -> None:
        """
        Update the config dictionary with a new one.

        If panel type is "Experiment", only considers "Experiment Config" section.
        If panel type is "Global", only considers "Base Config" section.

        :param update_config: The configuration dictionary to merge/set
        :type update_config: Dict[str, Any]
        :param reset: If True, clears existing config before updating, defaults to False
        :type reset: bool

        .. note::
            The "Experiment Config" and "Base Config" keys are removed after
            flattening to avoid nested structure in the final config.
        """
        if reset:
            self._config = {}

        # Flatten nested config sections based on panel type
        if self.type == "Experiment" and "Experiment Config" in update_config:
            # Flatten Experiment Config - spread nested dict into top level
            update_config = {**update_config, **update_config["Experiment Config"]}
        elif self.type == "Global" and "Base Config" in update_config:
            # Flatten Base Config - spread nested dict into top level
            update_config = {**update_config, **update_config["Base Config"]}

        # Remove the nested keys to avoid duplication
        update_config.pop("Experiment Config", None)
        update_config.pop("Base Config", None)

        self._config.update(update_config)
        self.populate_config_view()

    def add_tree_items_recursive(
        self,
        parent_item: QtGui.QStandardItem,
        data: Dict[str, Any],
        allow_voltage_editing: bool
    ) -> None:
        """
        Recursively add items to the tree structure.

        Creates tree items for nested dictionaries, with proper flags for
        editability based on builder mode.

        :param parent_item: The parent item to add children to
        :type parent_item: QtGui.QStandardItem
        :param data: The dictionary data to add as children
        :type data: Dict[str, Any]
        :param allow_voltage_editing: Whether voltage parameters should be editable
                                      (currently unused but kept for API compatibility)
        :type allow_voltage_editing: bool

        .. note::
            Items are sorted alphabetically by key for consistent display.
        """
        for key, value in sorted(data.items()):
            key_item = QtGui.QStandardItem(str(key))
            key_item.setFlags(QtCore.Qt.ItemIsEnabled)

            if isinstance(value, dict):
                # Nested dict - create placeholder value and recurse
                value_item = QtGui.QStandardItem("")  # Placeholder, not editable
                value_item.setFlags(QtCore.Qt.NoItemFlags)
                parent_item.appendRow([key_item, value_item])
                self.add_tree_items_recursive(key_item, value, allow_voltage_editing)
            else:
                # Leaf value - convert numpy types and create editable item
                if isinstance(value, (np.integer, np.floating, np.bool_)):
                    value = value.item()
                value_item = QtGui.QStandardItem(str(value))

                # In builder mode, make values read-only
                if self.builder_mode:
                    value_item.setFlags(QtCore.Qt.ItemIsEnabled)
                else:
                    value_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable)

                parent_item.appendRow([key_item, value_item])

    def handleItemChanged(self, item: QtGui.QStandardItem) -> None:
        """
        Handle item change events when a value is edited in the tree.

        Called when an item in the model is changed by editing. Updates
        the internal config dictionary and emits appropriate signals.

        Handles both flat and nested configs by building the path to
        the item and navigating the config dictionary.

        :param item: The item that was changed
        :type item: QtGui.QStandardItem

        .. note::
            In builder mode, editing is disabled so this method returns early.

        .. note::
            Values are parsed using ``ast.literal_eval()`` to convert strings
            to appropriate Python types (int, float, list, etc.). Falls back
            to string if parsing fails.
        """
        if self.builder_mode:
            # No editing in builder mode
            return

        if item.column() != 1:  # Only handle value column changes
            return

        parent = item.parent()

        # Handle flat config (top-level items with no parent)
        if parent is None:
            # Get key from first column of same row
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
            self._config[key] = value

            # Mark that we have unsaved changes
            self.mark_unsaved_changes(True)

            # Emit the parameter_changed signal
            self.parameter_changed.emit(key, value)

            # Emit runtime prediction signal with updated config
            self.update_runtime_prediction.emit(self._config)

            # If the parameter changed is a voltage, emit the update_voltage_panel signal
            if key.startswith("Voltage"):
                self.update_voltage_panel.emit()

            return

        # Handle nested config (items with parent)
        # Get key from first column of same row under parent
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

        # Build path to the item in the config dictionary by walking up the tree
        path: List[str] = []
        current = parent
        while current is not None and current.text():
            path.insert(0, current.text())
            current = current.parent()

        # Navigate to the correct nested dictionary in config
        config_ref = self._config
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

        # Emit the parameter_changed signal with the full dotted path
        full_path = ".".join(path + [key])
        self.parameter_changed.emit(full_path, value)

        # Emit runtime prediction signal with updated config
        self.update_runtime_prediction.emit(self._config)

        # If the parameter changed is a voltage, emit the update_voltage_panel signal
        # Check key, path elements, and "DACs" for voltage-related changes
        if key.startswith("Voltage") or any(p.startswith("Voltage") for p in path) or "DACs" in path:
            self.update_voltage_panel.emit()

    def mark_unsaved_changes(self, has_changes: bool) -> None:
        """
        Mark whether the current configuration has unsaved changes.

        Updates the visual indicator and button states.

        :param has_changes: True if there are unsaved changes, False otherwise
        :type has_changes: bool
        """
        self.has_unsaved_changes = has_changes
        if has_changes:
            self.unsaved_label.setText("* Unsaved Changes")
            self.unsaved_label.setStyleSheet("color: red;")
        else:
            self.unsaved_label.setText("")
            self.unsaved_label.setStyleSheet("")

        # Update button states whenever unsaved changes state changes
        self.update_button_states()

    def update_button_states(self) -> None:
        """
        Update the enabled/disabled state of Save and Save As buttons.

        Logic:

        - **Builder mode**: Only Save As is enabled (Save is disabled)
        - **Normal mode**: Save is enabled only with a current file;
          Save As is always enabled
        """
        if self.builder_mode:
            # In builder mode, only Save As is available
            self.save_config_button.setEnabled(False)
            self.save_as_config_button.setEnabled(True)
        else:
            # Normal mode - Save button enabled only if we have a current file path
            self.save_config_button.setEnabled(self.current_file_path is not None)
            self.save_as_config_button.setEnabled(True)

    def create_new_config(self) -> None:
        """
        Create a new configuration file with a default name.

        Prompts for save location with auto-generated filename based on
        panel name and current timestamp. Creates the file with an empty
        config dictionary.

        Checks for unsaved changes first and prompts user to save.
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
            self._config = {}

            # Save the empty config to the file
            try:
                with open(file_path, 'w') as f:
                    json.dump(self._config, f, indent=4)

                # Set this as the current file (only in normal mode)
                if not self.builder_mode:
                    self.current_file_path = file_path

                # Update UI based on current view
                self.populate_config_view()

                # Reset unsaved changes indicator
                self.mark_unsaved_changes(False)

                # Refresh directory view to show the new file
                self.directory_tree.refresh_view()

                qInfo(f"Created new configuration file: {file_path}")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create config file: {str(e)}")
                qCritical(f"Error creating config file: {str(e)}")

    def save_config(self) -> None:
        """
        Save the configuration to the current JSON file.

        If no file is currently open, prompts for a save location.

        .. note::
            Disabled in builder mode - shows info dialog directing user
            to use "Save As" instead.
        """
        if self.builder_mode:
            QMessageBox.information(
                self,
                "Builder Mode Active",
                "Use 'Save As' to save the merged configuration in builder mode."
            )
            return

        if self.current_file_path:
            # Save to the existing file
            self._save_config_to_file(self.current_file_path)
        else:
            # No current file, prompt for save location
            self.save_config_as()

    def save_config_as(self) -> None:
        """
        Save the configuration to a new JSON file.

        Opens a file dialog for the user to choose the save location.
        Works in both normal and builder modes.
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

    def _save_config_to_file(self, file_path: str) -> None:
        """
        Internal method to save configuration to a file.

        Handles JSON view synchronization, file writing, and UI updates.

        :param file_path: Path to save the file
        :type file_path: str

        :raises: Shows QMessageBox on file write errors
        """
        # If in JSON view, update config from editor first
        if self.current_view == "json" and not self.builder_mode:
            json_data = self.json_editor.get_json()
            if json_data is None:
                return  # JSON parse error, abort save
            self._config = json_data

        try:
            with open(file_path, 'w') as f:
                json.dump(self._config, f, indent=4, default=self.json_serializer)

            # Update current file path (only in normal mode)
            if not self.builder_mode:
                self.current_file_path = file_path

            # Reset unsaved changes indicator (this also updates button states)
            self.mark_unsaved_changes(False)

            # Refresh directory view to show changes
            self.directory_tree.refresh_view()

            qInfo(f"Configuration saved to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {str(e)}")

    def json_serializer(self, obj: Any) -> Union[int, float, bool, str]:
        """
        Custom JSON serializer for handling numpy types.

        Used as the ``default`` argument to ``json.dump()`` when saving
        configuration files.

        :param obj: The object to serialize
        :type obj: Any
        :returns: Python-native representation of the object
        :rtype: Union[int, float, bool, str]
        """
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return str(obj)

    def copy_config(self) -> None:
        """
        Copy the current configuration to the clipboard.

        Copies either the JSON editor text (if in JSON view) or the
        formatted config dictionary. Provides visual feedback by
        temporarily changing button text to "Copied!".

        :raises: Shows QMessageBox on clipboard errors
        """
        try:
            # Get the JSON string based on the current view
            if self.current_view == "json":
                json_string = self.json_editor.toPlainText()
            else:
                json_string = json.dumps(
                    self._config,
                    indent=4,
                    default=self.json_serializer
                )

            # Copy to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(json_string)

            # Visual feedback - temporarily change button text
            qInfo("Current configuration copied to clipboard!")
            self.copy_config_button.setText("Copied!")
            self.copy_config_button.setStyleSheet("color: green;")
            QTimer.singleShot(2000, lambda: self.copy_config_button.setText("Copy"))
            QTimer.singleShot(2000, lambda: self.copy_config_button.setStyleSheet(""))

        except Exception as e:
            qCritical(f"Error copying configuration: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to copy configuration: {str(e)}")

    def load_config(self, file_path: Optional[str] = None) -> None:
        """
        Load configuration from a JSON file.

        Checks for unsaved changes before loading and prompts user to save.
        Updates the UI and emits runtime prediction signal after loading.

        :param file_path: Path to the JSON file. If None, a file dialog will be shown.
        :type file_path: Optional[str]

        :raises: Shows QMessageBox on file read or JSON parse errors
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
            if self.has_unsaved_changes and not self.builder_mode:
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
                self.populate_config_view()

                # Emit runtime prediction signal
                self.update_runtime_prediction.emit(self._config)

                # Reset unsaved changes indicator (this also updates button states)
                self.mark_unsaved_changes(False)

                qInfo(f"Config loaded from {file_path}")

            except Exception as e:
                qCritical(f"Error loading config from {file_path}: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to load config: {str(e)}")

    def set_config(self, config_update: Optional[Dict[str, Any]] = None) -> None:
        """
        Update the config and repopulate the tree.

        Maintains compatibility with the original implementation.
        Clears the current file path since config was set programmatically.

        :param config_update: A dictionary containing the configuration to update to,
                              defaults to None (no update, just refresh view)
        :type config_update: Optional[Dict[str, Any]]
        """
        if config_update is not None:
            self._config = config_update

        self.populate_config_view()

        # Clear current file path since config was set programmatically
        self.current_file_path = None

        # Reset unsaved changes indicator (this also updates button states)
        self.mark_unsaved_changes(False)

    @property
    def config(self) -> Dict[str, Any]:
        """
        Return the current configuration dictionary.

        Maintains compatibility with the original implementation.

        In builder mode, returns the deep merged configuration.
        In normal mode, returns the single config. If in JSON view,
        parses the editor content first to ensure it's up-to-date.

        :returns: The configuration dictionary
        :rtype: Dict[str, Any]
        """
        # If in JSON view, update config from editor first
        if self.current_view == "json" and not self.builder_mode:
            json_data = self.json_editor.get_json()
            if json_data is not None:
                self._config = json_data

        return self._config

    @config.setter
    def config(self, value: Dict[str, Any]) -> None:
        """
        Set the configuration dictionary.

        Maintains compatibility with the original implementation.

        :param value: The configuration dictionary to set
        :type value: Dict[str, Any]
        """
        self._config = value

    def get_config(self) -> Dict[str, Any]:
        """
        Return the current configuration dictionary.

        Maintains compatibility with the original implementation.
        Delegates to the :attr:`config` property.

        :returns: The configuration dictionary
        :rtype: Dict[str, Any]
        """
        return self.config
