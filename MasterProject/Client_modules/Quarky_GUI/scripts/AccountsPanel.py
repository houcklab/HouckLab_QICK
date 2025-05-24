"""
================
AccountsPanel.py
================
The sidepanel that saves RFSoC connection information in different accounts for connection made easy.

Creates a local dataset of accounts in an ``accounts`` folder within the Quarky_GUI directory and stores your
preferred default connection.

Each account is saved locally in a json file named after the account's name that it stores. Format:

.. code-block:: python

    { "ip_address": "111.111.1.111", "account_name": "houcklab" }

The accounts folder will also always have a file named ``default.json`` that stores the account name of the default
account. Format:

.. code-block:: python

    {"default_account_name": "houcklab"}
"""

import os
import json
import importlib

from PyQt5.QtCore import (
    QSize,
    QRect,
    Qt,
    pyqtSignal,
)
from PyQt5.QtWidgets import (
    QWidget,
    QSizePolicy,
    QGroupBox,
    QLabel,
    QScrollArea,
    QFrame,
    QVBoxLayout,
    QListWidget,
    QAbstractItemView,
    QListWidgetItem,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QMessageBox,
)

class QAccountPanel(QWidget):
    """
    A custom QWidget class for the entire accounts panel.

    **Important Attributes:**

        * accounts_list (QListWidget): The QListWidget item that lists all the accounts saved locally
        * form_layout (QFormLayout): The QFormLayout layout that has all relevant fields for editing/saving an account.
        * current_account_item (QListWidgetItem): Stores the currently selected account item from the accounts list.
    """

    ### Defining Signals
    rfsoc_attempt_connection = pyqtSignal(str, str) # argument is ip_address
    """
    The Signal sent to the main application (Quarky.py) that tells the program to attempt a connection to a RFSoC via
    the given IP address.
    
    :param ip_address: The IP address to attempt a connection to.
    :type ip_address: str
    :param config: The path to the module that contains the BaseConfig.
    :type config: str
    """

    rfsoc_disconnect = pyqtSignal()
    """
    The Signal sent to the main application (Quarky.py) that tells the program to disconnect the RFSoC.
    """

    def __init__(self, parent=None):
        """
        Initializes an instance of this AccountsPanel widget (custom QWidget) class.

        :param parent: The parent QWidget that this widget belongs to.
        :type parent: QWidget
        """

        super(QAccountPanel, self).__init__(parent)

        self.current_account_name = None # currently selected account name (str)
        self.current_account_item = None # currently selected account item (QListWidget)
        self.default_account_name = None # the default account name (str)
        self.default_account_item = None # the default account item (str) (QListWidget)
        self.connected_account_name = None # currently connected account name (str)

        # This generates the direct path to the "accounts" folder (even if it doesn't exist)
        self.root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.account_dir = os.path.join(self.root_dir, 'LocalStorage/accounts')

        # UI stuff that allows for responsive resizing
        sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        sizepolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setMinimumSize(QSize(175, 0))
        self.setSizePolicy(sizepolicy)
        self.setObjectName("accounts_panel")

        # The main layout that will hold all components
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        ### Scrollable area that will hold the list of all accounts
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        # self.scroll_area.setGeometry(QRect(0, 0, 175, 500))
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setFrameShadow(QFrame.Plain)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setObjectName("scroll_area")

        self.scroll_area_content = QWidget()
        self.scroll_area_content.setObjectName("scroll_area_content")
        self.scroll_area_layout = QVBoxLayout(self.scroll_area_content)
        self.scroll_area_layout.setContentsMargins(0, 0, 0, 0)

        ### Accounts Group
        self.accounts_group = QGroupBox("Accounts")
        self.accounts_group.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignTop)
        self.accounts_group.setObjectName("accounts_group")
        self.accounts_layout = QVBoxLayout(self.accounts_group)
        self.accounts_layout.setContentsMargins(0, 10, 0, 0)
        self.accounts_layout.setObjectName("accounts_layout")

        ### Accounts List
        self.accounts_list = QListWidget()
        self.accounts_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.accounts_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.accounts_list.setAlternatingRowColors(False)
        self.accounts_list.setSortingEnabled(True)
        self.accounts_list.setObjectName("accounts_list")
        self.accounts_layout.addWidget(self.accounts_list)

        ### Account Editing Form
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(5, 0, 5, 0)
        self.form_layout.setVerticalSpacing(0)
        self.form_layout.setObjectName("form_layout")
        self.name_label = QLabel()
        self.name_label.setText("Name")
        self.name_label.setObjectName("name_label")
        self.form_layout.setWidget(0, QFormLayout.LabelRole, self.name_label)
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("name_edit")
        self.form_layout.setWidget(0, QFormLayout.FieldRole, self.name_edit)
        self.ip_label = QLabel()
        self.ip_label.setText("IP")
        self.ip_label.setObjectName("ip_label")
        self.form_layout.setWidget(1, QFormLayout.LabelRole, self.ip_label)
        self.ip_edit = QLineEdit()
        self.ip_edit.setObjectName("ip_edit")
        self.form_layout.setWidget(1, QFormLayout.FieldRole, self.ip_edit)
        self.config_label = QLabel()
        self.config_label.setText("Config")
        self.config_label.setObjectName("config_label")
        self.form_layout.setWidget(2, QFormLayout.LabelRole, self.config_label)
        self.config_edit = QLineEdit()
        self.config_edit.setObjectName("config_edit")
        self.form_layout.setWidget(2, QFormLayout.FieldRole, self.config_edit)

        self.accounts_layout.addLayout(self.form_layout)

        ### Account Action Buttons Layout
        self.form_button_layout = QVBoxLayout()
        self.form_button_layout.setSpacing(2)
        self.form_button_layout.setObjectName("form_button_layout")

        self.save_button = QPushButton("Up to Date")
        self.save_button.setObjectName("save_button")
        self.save_button.setEnabled(False)
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("delete_button")
        self.delete_button.setEnabled(True)
        self.create_new_button = QPushButton("Create as New")
        self.create_new_button.setObjectName("create_new_button")
        self.create_new_button.setEnabled(False)
        self.set_default_button = QPushButton("Set as Default")
        self.set_default_button.setObjectName("set_default_button")
        self.set_default_button.setEnabled(False)
        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("connect_button")
        self.connect_button.setEnabled(True)

        self.form_button_layout.addWidget(self.save_button)
        self.form_button_layout.addWidget(self.delete_button)
        self.form_button_layout.addWidget(self.create_new_button)
        self.form_button_layout.addWidget(self.set_default_button)
        self.form_button_layout.addWidget(self.connect_button)

        ### Adding all Layouts Together
        self.accounts_layout.addLayout(self.form_button_layout)
        self.accounts_group.setLayout(self.accounts_layout)

        self.scroll_area_layout.addWidget(self.accounts_group)
        self.scroll_area_content.setLayout(self.scroll_area_layout)
        self.scroll_area.setWidget(self.scroll_area_content)

        self.main_layout.addWidget(self.scroll_area)
        self.setLayout(self.main_layout)

        self.load_accounts() # Loads all the accounts saved locally
        self.setup_signals()

    def setup_signals(self):
        """
        Sets up all the signals and slots of the Accounts Panel. Including form editing/action buttons, RFSoC connection
        attempts, and accounts list selection.
        """

        self.save_button.clicked.connect(self.update_account)
        self.delete_button.clicked.connect(self.delete_account)
        self.create_new_button.clicked.connect(self.create_account)
        self.set_default_button.clicked.connect(self.set_as_default)
        self.connect_button.clicked.connect(self.attempt_connection_or_disconnect)

        self.ip_edit.textChanged.connect(self.unsaved_indicate)
        self.name_edit.textChanged.connect(self.unsaved_indicate)
        self.config_edit.textChanged.connect(self.unsaved_indicate)
        self.accounts_list.currentItemChanged.connect(self.select_item)

    def load_accounts(self):
        """
        This function populates accounts_list QListWidget with all the accounts locally saved in the accounts
        directory. See the top for the json format for storing an account. It populates the instance variables for
        the current/default account names and items. It also selects the default account.
        """

        self.current_account_name = None
        self.current_account_item = None
        self.accounts_list.clear()

        ### Creating an accounts folder with a template account and default.json file if one doesn't exist
        default_file = os.path.join(self.account_dir, "default.json")
        if not os.path.exists(self.account_dir) or not os.path.exists(default_file):
            os.makedirs(self.account_dir)
            template_file = os.path.join(self.account_dir, "template.json")

            with open(default_file, "w") as f:
                json.dump({"default_account_name": "template"}, f, indent=4)
            with open(template_file, "w") as f:
                json.dump({"ip_address": "111.111.1.111", "account_name": "template",
                                "config": "MasterProject.Client_modules.Init.initialize"}, f, indent=4)

        ### Handles the default.json file to retrieve the default account name
        with open(default_file, "r") as f:
            data = json.load(f)
            self.default_account_name = data["default_account_name"]

        ### Populates the accounts list by iterating through all json files in the accounts folder
        for file in os.listdir(self.account_dir):
            if file.endswith(".json") and file != "default.json":
                with open(os.path.join(self.account_dir, file), "r") as f:
                    data = json.load(f)
                    name = data["account_name"]
                    ip = data["ip_address"]
                    config = data["config"]

                    # handling the default account case
                    if name == self.default_account_name:
                        item = QListWidgetItem(str(name + ' (default)'))
                        self.default_account_item = item
                        if self.current_account_name is None or self.current_account_item is None:
                            self.current_account_name = self.default_account_name
                            self.current_account_item = item
                    else:
                        item = QListWidgetItem(str(name))
                    self.accounts_list.addItem(item) # add item to the list

        self.select_item(self.current_account_item)
        self.saved_indicate() # sets the button status

    def attempt_connection_or_disconnect(self):
        """
        Attempts to connect to an account or disconnect it based on whether or not the variable connected_account_name
        is None or not. In both cases, it emits the corresponding signal to the main GUI telling it how to handle the
        RFSoC.
        """

        if self.connected_account_name is None:
            ip_address = self.ip_edit.text().strip()
            config = self.config_edit.text().strip()

            self.rfsoc_attempt_connection.emit(ip_address, config)
        else:
            self.rfsoc_disconnect.emit()

            # Not very efficient but this is what resets all the UI and the variables for the disconnected status
            self.connect_button.setText("Connect")
            self.connected_account_name = None
            self.load_accounts() # reload all the accounts (very inefficient but is a simple way to handle UI)

            self.ip_edit.setDisabled(False)
            self.name_edit.setDisabled(False)
            self.cofig_edit.setDisabled(False)
            self.saved_indicate()


    def unsaved_indicate(self):
        """
        A UI function that handles the case where form entries have been edited, meaning changes are currently unsaved.
            * Allow: Saving, Creating, Connecting/Disconnecting, Deleting
            * Disallow: Setting as Default
        """

        self.save_button.setText("Save")
        self.save_button.setEnabled(True)
        self.create_new_button.setEnabled(True)
        self.set_default_button.setEnabled(False)
        self.connect_button.setEnabled(False)

    def saved_indicate(self):
        """
        A UI function that handles the case where the form entries are not edited.
            * Allow: Setting as Default, Connecting/Disconnecting, Deleting
            * Disallow: Saving, Creating
        """

        self.save_button.setText("Up to Date")
        self.save_button.setEnabled(False)
        self.create_new_button.setEnabled(False)
        self.set_default_button.setEnabled(True)
        self.connect_button.setEnabled(True)

    def disable_since_connected(self):
        """
        A UI function that handles the case where we are actively connected to an RFSoC.
            * Allow: Disconnecting
            * Disallow: Form editing, Saving, Deleting, Creating, Setting as Default
        """

        self.save_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.create_new_button.setEnabled(False)
        self.set_default_button.setEnabled(False)
        self.ip_edit.setDisabled(True)
        self.name_edit.setDisabled(True)
        self.config_edit.setDisabled(True)

    def update_account(self):
        """
        Updates an account by validating the form entries and editing the respective json form fields. See the top of
        the documentation for json format.
        """

        if self.current_account_name:
            # Validating form entries
            new_ip_address = self.ip_edit.text().strip()
            new_account_name = self.name_edit.text().strip()
            new_config = self.config_edit.text().strip()

            if not self.validate_account_input(new_ip_address, new_account_name, new_config,'update'): return

            # Load the existing JSON file
            file = os.path.join(self.account_dir, self.current_account_name + '.json')
            try:
                with open(file, "r") as f:
                    # update fields
                    data = json.load(f)
                    data["ip_address"] = new_ip_address
                    data["account_name"] = new_account_name
                    data["config"] = new_config
                with open(file, "w") as f:
                    # dump to json
                    json.dump(data, f, indent=4)

                # Update file name to the new account name as well
                new_filename = (new_account_name.strip() + ".json")
                os.rename(file, os.path.join(self.account_dir, new_filename))

                # If the old account name matches the default one (meaning this is the default account)
                # Then update the default account name
                if self.current_account_name == self.default_account_name:
                    self.update_default_account_name(new_account_name, self.current_account_item)
                    self.current_account_item.setText(new_account_name + ' (default)')
                else:
                    self.current_account_item.setText(new_account_name)

                self.current_account_name = new_account_name
                self.saved_indicate()
            except (json.JSONDecodeError, FileNotFoundError):
                QMessageBox.critical(None, "Error", "Error updating Json file.")
                return

    def validate_account_input(self, new_ip_address, new_account_name, new_config, purpose):
        """
        Validating the input to create accounts via an account name and an ip_address. Moreover, based on the purpose
        of the validation (either 'create' or 'update'), it will check for account name duplicates.

        :param new_ip_address: The new IP address of the account.
        :type new_ip_address: str
        :param new_account_name: The new account name of the account.
        :type new_account_name: str
        :param purpose: The purpose of the validation, to either 'create' or 'update' an account.
        :type purpose: str
        :return: True if the input is valid, False otherwise.
        :rtype: bool
        """

        # text validation
        invalid_chars = r'.\/:*?"<>| '
        if any(char in new_account_name for char in invalid_chars):
            QMessageBox.critical(None, "Error", "Invalid account name. No " + invalid_chars + "or spaces.")
            return False
        if not new_ip_address or not new_account_name:
            QMessageBox.critical(None, "Error", "IP address or account name cannot be empty.")
            return False
        if not all(part.isdigit() and 0 <= int(part) <= 255 for part in new_ip_address.split('.') if part):
            QMessageBox.critical(None, "Error", "IP address invalid.")
            return False

        # config import path validation
        try:
            module = importlib.import_module(new_config)
            config = getattr(module, "BaseConfig")
        except Exception as e:
            QMessageBox.critical(None, "Error", "Config import path is invalid. "
                                                "Verify BaseConfig exists and no socProxy imports are present.")
            return False

        # duplication validation
        if purpose == 'create':
            # no duplicate account names
            for idx in range(self.accounts_list.count()):
                item = self.accounts_list.item(idx)
                account_name = item.text().strip()
                if account_name.endswith("(default)"): account_name = account_name[:-9]
                if account_name.startswith("✔"): account_name = account_name[1:]
                account_name = account_name.strip()
                if account_name == new_account_name:
                    QMessageBox.critical(None, "Error", "Account name already exists.")
                    return False

        return True

    def update_default_account_name(self, new_default_account_name, new_default_account_item):
        """
        A function that updates the default account name within the default.json file (format at the top of the
        documentation) with the new passed account name. It also updates the default account list item.

        :param new_default_account_name: The new default account name.
        :type new_default_account_name: str
        :param new_default_account_item: The new default account item.
        :type new_default_account_item: QListWidgetItem
        """

        default_file = os.path.join(self.account_dir, "default.json")
        try:
            self.default_account_name = new_default_account_name
            self.default_account_item = new_default_account_item
            with open(default_file, "w") as f:
                json.dump({"default_account_name": new_default_account_name}, f, indent=4)
        except (json.JSONDecodeError, FileNotFoundError):
            QMessageBox.critical(None, "Error", "Error updating default file.")
            return

    def create_account(self):
        """
        Creates a new account by populating a new json file per the format listed at the top. Retrieves the text
        within the form boxes and validates them before doing so. Then, it creates a new QListWidgetItem and adds it
        to the accounts_list.
        """

        new_ip_address = self.ip_edit.text().strip()
        new_account_name = self.name_edit.text().strip()
        new_config = self.config_edit.text().strip()

        if not self.validate_account_input(new_ip_address, new_account_name, new_config, 'create'): return

        new_filename = (new_account_name.strip() + ".json")
        new_account_file = os.path.join(self.account_dir,new_filename)

        with open(new_account_file, "w") as f:
            json.dump({"ip_address": str(new_ip_address), "account_name": str(new_account_name),
                            "config": str(new_config)}, f, indent=4)

        item = QListWidgetItem(str(new_account_name))
        self.accounts_list.addItem(item)
        self.select_item(item)

    def select_item(self, current, previous=None):
        """
        The function that is called when the user selects an item from the accounts list (clicks on an
        QListWidgetItem. It updates the coresponding name and item variables and opens the json file to populate the
        form fields.

        :param current: The selected item.
        :type current: QListWidgetItem
        """

        if current is not None:
            account_name = current.text().strip()
            if account_name.endswith("(default)"): account_name = account_name[:-9]
            if account_name.startswith("✔"): account_name = account_name[1:]
            self.current_account_name = account_name.strip()
            self.current_account_item = current
            self.accounts_list.setCurrentItem(current)

            file = os.path.join(self.account_dir, self.current_account_name + '.json')
            with open(file, "r") as f:
                data = json.load(f)
                name = data["account_name"]
                ip = data["ip_address"]
                config = data["config"]

                self.name_edit.setText(name)
                self.ip_edit.setText(ip)
                self.config_edit.setText(config)

            if self.connected_account_name is not None:
                self.disable_since_connected()
            else:
                self.saved_indicate()

    def delete_account(self):
        """
        Deletes the selected account from the accounts_list and removes the corresponding json file. Prevents default
        account deletion.
        """

        if self.current_account_name == self.default_account_name:
            QMessageBox.critical(None, "Error", "Cannot delete default account.")
            return
        file = os.path.join(self.account_dir, self.current_account_name + '.json')
        if os.path.exists(file):
            os.remove(file)
        else:
            QMessageBox.critical(None, "Error", "Cannot find file with account name.")
            return
        selected_item_row_idx = self.accounts_list.currentRow()
        self.accounts_list.takeItem(selected_item_row_idx)
        if self.current_account_name == self.connected_account_name:
            self.rfsoc_disconnect.emit()

        self.select_item(self.default_account_item)

    def set_as_default(self):
        """
        Function triggered when the default_button is clicked. Calls the update_default_account_name function and
        reloads all accounts.
        """

        self.update_default_account_name(self.current_account_name, self.current_account_item)
        self.load_accounts()

    def rfsoc_connection_updated(self, ip_address, status):
        """
        Upon an RFSoC connection update of either 'failure' or 'success', the main widget sends a signal to the
        accounts panel that is handled via this function. If success, it updates the UI and corresponding name and item
        variables.

        :param ip_address: The IP address of the RFSoC.
        :type ip_address: str
        :param status: The status of the RFSoC connection ('success' or 'failure').
        :type status: str
        """

        if status == 'success':
            # Successful connection
            self.connected_account_name = self.current_account_name
            if self.current_account_name == self.default_account_name:
                self.current_account_item.setText('✔ ' + self.current_account_name + ' (default)')
            else:
                self.current_account_item.setText('✔ ' + self.current_account_name)

            self.connect_button.setText("Disconnect")
            self.disable_since_connected()
        else:
            # Unsuccessful connection
            self.connected_account_name = None
            self.saved_indicate()