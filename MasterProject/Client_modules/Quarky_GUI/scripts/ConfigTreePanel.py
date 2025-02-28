import os
import json
from PyQt5 import QtGui, QtCore
from PyQt5.QtGui import QClipboard
from PyQt5.QtCore import (
    qInfo,
    qWarning,
    qCritical,
)
from PyQt5.QtWidgets import (
    QFileDialog,
    QTreeView,
    QHBoxLayout,
    QVBoxLayout,
    QAbstractItemView,
    QMessageBox,
    QApplication
)

import scripts.Helpers as Helpers

class QConfigTreePanel(QTreeView):
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config if config else {}

        # Set up layout
        self.toolbar_layout = QHBoxLayout()
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar_layout.setSpacing(5)
        self.main_layout = QVBoxLayout()
        self.main_layout.addLayout(self.toolbar_layout)
        self.main_layout.setContentsMargins(10, 5, 10, 10)
        self.main_layout.setSpacing(0)
        self.setLayout(self.main_layout)
        self.setMinimumSize(200, 0)

        # toolbar setup
        self.save_config_button = Helpers.create_button("Save", "save_config", True)
        self.copy_config_button = Helpers.create_button("Copy", "copy_config", True)
        self.load_config_button = Helpers.create_button("Load", "load_config", True)
        self.toolbar_layout.addWidget(self.save_config_button)
        self.toolbar_layout.addWidget(self.copy_config_button)
        self.toolbar_layout.addWidget(self.load_config_button)

        # Create and configure the tree view
        self.tree = QTreeView(self)
        self.main_layout.addWidget(self.tree)

        # Create the model
        self.model = QtGui.QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.tree.setModel(self.model)

        # Tree View settings
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.setHeaderHidden(False)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.tree.setColumnWidth(0, 100)
        self.tree.setColumnWidth(1, 50)
        self.tree.setIndentation(10)

        # Connect item change signal
        self.model.itemChanged.connect(self.handleItemChanged)

        # Load initial config
        self.populate_tree()
        self.setup_signals()

    def setup_signals(self):
        self.save_config_button.clicked.connect(self.save_config)
        self.copy_config_button.clicked.connect(self.copy_config)
        self.load_config_button.clicked.connect(self.load_config)

    def populate_tree(self):
        """Populates the tree with config data."""
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])  # Reset headers after clear

        for category, params in self.config.items():
            if not params:
                continue

            parent = QtGui.QStandardItem(category)
            parent.setFlags(QtCore.Qt.NoItemFlags)  # Category headers should not be selectable

            for key, value in params.items():
                child_key = QtGui.QStandardItem(key)
                child_key.setFlags(QtCore.Qt.ItemIsEnabled)

                child_value = QtGui.QStandardItem(str(value))
                child_value.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable)

                parent.appendRow([child_key, child_value])

            self.model.appendRow(parent)

        self.tree.expandAll()

    def set_config(self, config_update=None):
        """Updates the config and repopulates the tree."""
        if config_update is not None:
            self.config = config_update

        self.populate_tree()

    def get_config(self):
        """Returns the current configuration."""
        return self.config

    def handleItemChanged(self, item):
        """Handles updates when an item is edited."""
        if not item.parent():
            return  # Ignore category headers

        category = item.parent().text()
        key = item.parent().child(item.row(), 0).text()

        # Ensure the key exists in the config before modifying
        if category in self.config and key in self.config[category]:
            try:
                self.config[category][key] = type(self.config[category][key])(item.text())
            except ValueError:
                pass  # Handle invalid input types gracefully

    def save_config(self):
        """Prompts the user for a folder and saves the config dictionary as a JSON file."""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder to Save Config")

        if folder_path:
            file_path = os.path.join(folder_path, "config.json")
            try:
                with open(file_path, "w") as json_file:
                    json.dump(self.config, json_file, indent=4)
                qInfo(f"Configuration saved to {file_path}")
            except Exception as e:
                qCritical(f"Failed to save the configuration to {file_path}: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to save config.")


    def copy_config(self):
        """Copies the config dictionary as a formatted JSON string to the clipboard."""
        json_string = json.dumps(self.config) # can incldue indent=4 if formatting wanted
        clipboard = QApplication.clipboard()
        clipboard.setText(json_string)
        qInfo("Current configuration copied to clipboard!")

    def load_config(self):
        """Prompts the user for a JSON file and loads it into self.config, then updates the tree."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Config File", "", "JSON Files (*.json)")

        if file_path:  # If a file is selected
            try:
                with open(file_path, "r") as json_file:
                    self.config = json.load(json_file)
                self.populate_tree()  # Refresh the tree with the new config
                qInfo(f"Config loaded from {file_path}")
            except Exception as e:
                qCritical(f"The Config loaded from {file_path} has failed: {str(e)}")
                QMessageBox.critical(self, "Error", "Failed to load config")

