"""
==================
ConfigTreePanel.py
==================
The sidepanel that contains the interactable Tree object with the Experiment/Dataset configurations. These
configurations are specified by each experiment file or in the metadata of a dataset. The Base Configuration
is given by Init.initialize.py.

This is the basic formatting of the Config dictionary:

.. code-block:: python

    { "Experiment Config" : {
            "field_name" : 0,
        },
      "Base Config": {
            "field_name" : 0,
        },
    }
"""

import os
import json
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import (
    Qt,
    qInfo,
    qWarning,
    qCritical,
    QTimer
)
from PyQt5.QtWidgets import (
    QFileDialog,
    QTreeView,
    QHBoxLayout,
    QVBoxLayout,
    QAbstractItemView,
    QMessageBox,
    QApplication,
    QLabel,
)

import scripts.Helpers as Helpers

class QConfigTreePanel(QTreeView):
    """
    A custom QTreeView class for the configurations panel.

    **Important Attributes:**

        * config (dict): The dictionary containing the active configuration
        * tree (QTreeView): The TreeView containing the configuration
    """

    def __init__(self, parent=None, config=None):
        """
        Initialize the custom QTreeView class.

        Note: For UI spacing purposes, QConfigTreePanel is itself a QTreeView,
        but not the Tree that consists of the configurations. Instead, the instance `tree` of type QTreeView that
        resides within the parent tree is the one that has the configurations.

        :param parent: The parent of the QTreeView
        :type parent: QWidget
        :param config: The dictionary containing the configuration to set (can be None)
        :type config: dict
        """

        super().__init__(parent)
        self.config = config if config else {}

        # Set up layout
        self.toolbar_layout = QHBoxLayout()
        self.toolbar_layout.setContentsMargins(0, 7, 0, 2)
        self.toolbar_layout.setSpacing(5)
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(10, 5, 10, 10)
        self.main_layout.setSpacing(0)
        self.setLayout(self.main_layout)
        self.setMinimumSize(200, 0)

        self.title_label = QLabel("Configuration Panel")  # estimated experiment time
        self.title_label.setStyleSheet("font-size: 11px; background-color: #ECECEC; padding: 3px;")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        # toolbar setup
        self.save_config_button = Helpers.create_button("Save", "save_config", True, self)
        self.copy_config_button = Helpers.create_button("Copy", "copy_config", True, self)
        self.load_config_button = Helpers.create_button("Load", "load_config", True, self)
        self.toolbar_layout.addWidget(self.save_config_button)
        self.toolbar_layout.addWidget(self.copy_config_button)
        self.toolbar_layout.addWidget(self.load_config_button)
        self.main_layout.addLayout(self.toolbar_layout)

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
        """
        Sets up all the signals and slots of the ConfigTree Panel. Includes connecting the toolbar button functionality.
        """

        self.save_config_button.clicked.connect(self.save_config)
        self.copy_config_button.clicked.connect(self.copy_config)
        self.load_config_button.clicked.connect(self.load_config)

    def populate_tree(self):
        """
        Populates the `tree` QTreeView widget with the configuration data by iterating through the dictionary and
        creating a QStandardItem for each Key (Parameter) and Value.
        """

        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])  # Reset headers after clear

        for category, params in self.config.items():
            if not params:
                continue

            # Track the current parent (either Experiment or Base Config) to place fields under
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
        """
        Updates the config and repopulates the tree.

        :param config_update: A dictionary containing the configuration to update to.
        :type config_update: dict
        """

        if config_update is not None:
            self.config = config_update

        self.populate_tree()

    def get_config(self):
        """
        Returns the current configuration dictionary.

        :return: The configuration dictionary.
        :rtype: dict
        """

        return self.config

    def handleItemChanged(self, item):
        """
        The function called that handles updates when the value of a parameter in the tree is edited. It modifies the
        current configuration dictionary value.

        :param item: The QStandardItem of the value of the QTreeView item that was altered.
        :type item: QStandardItem
        """

        if not item.parent():
            return  # Ignore category headers
            # (if there is a way to disable editing in the value of a parent field that would work nicer)

        category = item.parent().text()
        key = item.parent().child(item.row(), 0).text()

        # Ensure the key exists in the config before modifying
        if category in self.config and key in self.config[category]:
            try:
                self.config[category][key] = type(self.config[category][key])(item.text())
            except ValueError:
                pass  # Handle invalid input types gracefully

    def save_config(self):
        """
        Prompts the user for a folder and saves the config dictionary as a JSON file.
        """

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
        """
        opies the config dictionary as a formatted JSON string to the clipboard.
        """

        json_string = json.dumps(self.config) # can incldue indent=4 if formatting wanted
        clipboard = QApplication.clipboard()
        clipboard.setText(json_string)
        qInfo("Current configuration copied to clipboard!")

        self.copy_config_button.setText('Done!')
        QTimer.singleShot(3000, lambda: self.copy_config_button.setText('Copy'))

    def load_config(self):
        """
        Prompts the user for a JSON file and loads it into the `config` variable, then updates the tree.
        """

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

