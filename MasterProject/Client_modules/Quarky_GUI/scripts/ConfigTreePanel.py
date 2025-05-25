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
import ast
import datetime
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import (
    QEvent,
    QObject,
    Qt,
    qInfo,
    qWarning,
    qCritical,
    QTimer, qDebug, pyqtSignal
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
    QButtonGroup
)

import scripts.Helpers as Helpers

class QConfigTreePanel(QTreeView):
    """
    A custom QTreeView class for the configurations panel.

    **Important Attributes:**

        * config (dict): The dictionary containing the active configuration
        * tree (QTreeView): The TreeView containing the configuration
    """

    update_voltage_panel = pyqtSignal()
    """
    The Signal to send to update the voltage panel.
    """

    update_runtime_prediction = pyqtSignal(dict)
    """
    The Signal to send to update the runtime prediction.
    
    :param dict config: The dictionary containing the active configuration
    :type config: dict
    """

    def __init__(self, app, parent=None, config=None):
        """
        Initialize the custom QTreeView class.

        Note: For UI spacing purposes, QConfigTreePanel is itself a QTreeView,
        but not the Tree that consists of the configurations. Instead, the instance `tree` of type QTreeView that
        resides within the parent tree is the one that has the configurations.

        :param app: The main application instance
        :type app: QWidget
        :param parent: The parent of the QTreeView
        :type parent: QWidget
        :param config: The dictionary containing the configuration to set (can be None)
        :type config: dict
        """

        super().__init__(parent)
        self.app = app
        self.config = config if config else {}

        self.setObjectName("ConfigTreePanel")

        # Set up layout
        self.toolbar_layout = QHBoxLayout()
        self.toolbar_layout.setContentsMargins(0, 7, 0, 7)
        self.toolbar_layout.setSpacing(0)
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(10, 5, 10, 5)
        self.main_layout.setSpacing(3)
        self.setLayout(self.main_layout)
        self.setMinimumSize(225, 0)

        self.title_label = QLabel("Configuration Panel")  # estimated experiment time
        self.title_label.setStyleSheet("font-size: 11px; background-color: #ECECEC; padding: 3px; border-radius: 5px;")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        # toolbar setup
        self.save_config_button = Helpers.create_button("Save", "save_config", True, self)
        self.load_config_button = Helpers.create_button("Load", "load_config", True, self)
        self.copy_config_button = Helpers.create_button("Copy", "copy_config", True, self)
        self.paste_config_button = Helpers.create_button("Paste", "paste_config", True, self)

        self.toolbar_layout.addWidget(self.save_config_button)
        self.toolbar_layout.addWidget(self.load_config_button)
        self.toolbar_layout.addWidget(self.copy_config_button)
        self.toolbar_layout.addWidget(self.paste_config_button)

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
        self.tree.setIndentation(6)

        instructions_label = QLabel("Drag and Drop .json Files")
        instructions_label.setStyleSheet("font-size: 10px;")
        self.main_layout.addWidget(instructions_label)

        # Connect item change signal (this needs to happen before populate_tree (I think))
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
        self.load_config_button.clicked.connect(lambda : self.load_config())
        self.paste_config_button.clicked.connect(self.paste_config)

        # File dropping
        self.tree.setAcceptDrops(True)
        self.tree.installEventFilter(self)

    def eventFilter(self, obj, event):
        """
        The event filter installed on the config tree to link its drag and drop to the drag and drop functions below.

        :param obj: The QObject to be dragged and dropped
        :type obj: QObject
        :param event: The event being filtered
        :type event: QEvent
        """
        if event.type() in (QEvent.DragEnter, QEvent.Drop):
            self.dragEnterEvent(event) if event.type() == QEvent.DragEnter else self.dropEvent(event)
            return True
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event):
        """
        The Function called when a file has entered the drop area. Accepts if it is a .json file (allows the drop),
        otherwise ignores.

        :param event: The event that triggered the drag event.
        :type event: QDragEnterEvent
        """
        print("has entered")
        if event.mimeData().hasUrls():
            # Check if any URL ends with .json
            for url in event.mimeData().urls():
                if url.toLocalFile().endswith('.json'):
                    print("valid")
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        """
        The Function called when a file has been dropped into the drop area. This is only possible if the file is of
        type .json. Simply mimics the load_config function.

        :param event: The event that triggered the drop event.
        :type event: QDropEvent
        """
        print("has dropped")

        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.endswith('.json'):
                    qInfo("Config file dropped into config panel to be loaded.")
                    self.load_config(file_path)
                    break  # Accept only one .json file at a time
            event.acceptProposedAction()
        else:
            event.ignore()

    def populate_tree(self, allow_voltage_editing=True):
        """
        Populates the `tree` QTreeView widget with the configuration data by iterating through the dictionary and
        creating a QStandardItem for each Key (Parameter) and Value.
        """
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])

        for category, params in self.config.items():
            if not params:
                continue

            parent = QtGui.QStandardItem(category)
            parent.setFlags(QtCore.Qt.NoItemFlags)

            self.add_tree_items_recursive(parent, params, allow_voltage_editing)

            self.model.appendRow(parent)

        self.tree.expandAll()

    def add_tree_items_recursive(self, parent_item, data, allow_voltage_editing):
        for key, value in data.items():
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
                value_item = QtGui.QStandardItem(str(value))
                value_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable)
                parent_item.appendRow([key_item, value_item])

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

        if not item or not item.parent():
            return

        path = []
        current_item = item

        # Climb the tree, collecting keys
        while current_item.parent():
            row = current_item.row()
            key_item = current_item.parent().child(row, 0)
            path.insert(0, key_item.text())
            current_item = current_item.parent()

        # Top-level category
        path.insert(0, current_item.text())

        # Traverse the config dict
        config_ref = self.config

        try:
            for key in path[:-1]:
                config_ref = config_ref[key]
            final_key = path[-1]
            old_value = config_ref[final_key]
        except (KeyError, ValueError, TypeError):
            qDebug("Failed to traverse config path.")
            return

        try:
            new_value = ast.literal_eval(item.text()) # attempt to keep the old type
            config_ref[final_key] = new_value
            if str(final_key).startswith("Voltage") or str(final_key) == "DACs":
                # update the voltage panel section to reflect changes
                self.update_voltage_panel.emit()
        except (KeyError, ValueError, TypeError):
            qDebug("Failed updating config field to match type. Resetting.")
            config_ref[final_key] = old_value
            pass  # Graceful failure on conversion or path error
        # print(self.config)

        # emit runtime prediction when config values changed
        self.update_runtime_prediction.emit(self.config)

    def update_config_dict(self, update_config):
        """
        Updates the config dictionary with a new one but keeps all Base Config fields in Base Config.
        """
        keys_to_remove = []
        for key in update_config:
            if key in self.config["Base Config"]:
                self.config["Base Config"][key] = update_config[key]
                keys_to_remove.append(key)

        for key in keys_to_remove:
            update_config.pop(key, None)
        self.config["Experiment Config"] = update_config

    def save_config(self):
        """
        Prompts the user for a folder and saves the config dictionary as a JSON file.
        """

        folder_path = Helpers.open_file_dialog("Select Folder to Save Config", "",
                                        "config_save_folder", self, file=False)

        date_time_now = datetime.datetime.now()
        date_string = date_time_now.strftime("%Y_%m_%d")
        if self.app.current_tab:
            file_name = "config_" + self.app.current_tab.tab_name + "_" + date_string + ".json"
        else:
            file_name = "config_" + date_string + ".json"

        if folder_path:
            file_path = os.path.join(folder_path, file_name)
            try:
                unformatted_config = self.config.copy()
                unformatted_config.update(unformatted_config.pop("Base Config", {}))
                unformatted_config.update(unformatted_config.pop("Experiment Config", {}))

                with open(file_path, "w") as json_file:
                    json.dump(unformatted_config, json_file, indent=4)
                qInfo(f"Configuration saved to {file_path}")
            except Exception as e:
                qCritical(f"Failed to save the configuration to {file_path}: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to save config.")


    def copy_config(self):
        """
        copies the config dictionary as a formatted JSON string to the clipboard.
        """

        unformatted_config = self.config.copy()
        unformatted_config.update(unformatted_config.pop("Base Config", {}))
        unformatted_config.update(unformatted_config.pop("Experiment Config", {}))

        json_string = json.dumps(unformatted_config) # can incldue indent=4 if formatting wanted
        clipboard = QApplication.clipboard()
        clipboard.setText(json_string)
        qInfo("Current configuration copied to clipboard!")

        self.copy_config_button.setText('Done!')
        QTimer.singleShot(3000, lambda: self.copy_config_button.setText('Copy'))

    def load_config(self, file_path=None):
        """
        Prompts the user for a JSON file and loads it into the `config` variable, then updates the tree.
        """

        if file_path is None:
            file_path = Helpers.open_file_dialog("Select Config File", "JSON Files (*.json)",
                                            "load_config", self, file=True)

        if file_path:  # If a file is selected
            try:
                with open(file_path, "r") as json_file:
                    update_config = json.load(json_file)
                    update_config.update(update_config.pop("Base Config", {}))
                    update_config.update(update_config.pop("Experiment Config", {}))
                    self.update_config_dict(update_config)

                self.populate_tree()  # Refresh the tree with the new config
                # emit runtime prediction when config values changed
                self.update_runtime_prediction.emit(self.config)

                qInfo(f"Config loaded from {file_path}")
            except Exception as e:
                qCritical(f"The Config loaded from {file_path} has failed: {str(e)}")
                QMessageBox.critical(self, "Error", "Failed to load config")

    def paste_config(self):
        """
        Creates a text prompt for the user to paste in a dictionary that is then diff'd with the current config.
        """
        text, ok = QInputDialog.getMultiLineText(
            self,
            "Paste Config",
            "Paste config in dictionary format to be diff'd with current config. (ex: {'field': 50})"
        )
        if not ok or not text.strip():
            return

        try:
            update_config = json.loads(text.strip())
            update_config.update(update_config.pop("Base Config", {}))
            update_config.update(update_config.pop("Experiment Config", {}))
            self.update_config_dict(update_config)

            self.populate_tree()

            # emit runtime prediction when config values changed
            self.update_runtime_prediction.emit(self.config)

        except Exception as e:
            QMessageBox.critical(None, "Error", f"Error parsing dictionary: {e}")