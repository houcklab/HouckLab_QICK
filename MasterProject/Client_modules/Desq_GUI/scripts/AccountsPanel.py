"""
================
AccountsPanel.py
================

The sidepanel that saves RFSoC connection information in different accounts for connection made easy.

Creates a local dataset of accounts in an ``accounts`` folder within the Desq_GUI directory and stores your
preferred default connection.

Each account is saved locally in a json file named after the account's name that it stores. Format:

.. code-block:: python

    { "ip_address": "111.111.1.111", "account_name": "houcklab" }

The accounts folder will also always have a file named ``default.json`` that stores the account name of the default
account. Format:

.. code-block:: python

    {"default_account_name": "houcklab"}

:var INVALID_CHARS: Characters that are not allowed in account names.
:vartype INVALID_CHARS: str

.. note::
    Account files are stored in ``LocalStorage/accounts/`` relative to the root directory.
    The default account is tracked separately in ``default.json``.
"""

from __future__ import annotations

import os
import json
import importlib
from typing import Optional

from PyQt5.QtCore import (
    QSize,
    QRect,
    Qt,
    pyqtSignal,
    QSettings, qInfo,
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
    QHBoxLayout,
    QFileDialog,
)

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers


class QAccountPanel(QWidget):
    """
    A custom QWidget class for the entire accounts panel.

    This panel provides a GUI for managing RFSoC connection accounts, including
    creating, editing, deleting, and connecting to accounts. Each account stores
    an IP address, account name, and workspace directory.

    :ivar accounts_list: The QListWidget item that lists all the accounts saved locally.
    :vartype accounts_list: QListWidget
    :ivar form_layout: The QFormLayout layout that has all relevant fields for editing/saving an account.
    :vartype form_layout: QFormLayout
    :ivar current_account_item: Stores the currently selected account item from the accounts list.
    :vartype current_account_item: Optional[QListWidgetItem]
    :ivar current_account_name: Currently selected account name.
    :vartype current_account_name: Optional[str]
    :ivar default_account_name: The default account name.
    :vartype default_account_name: Optional[str]
    :ivar default_account_item: The default account item.
    :vartype default_account_item: Optional[QListWidgetItem]
    :ivar connected_account_name: Currently connected account name (None if not connected).
    :vartype connected_account_name: Optional[str]
    :ivar root_dir: The root directory path of the Desq_GUI.
    :vartype root_dir: str
    :ivar account_dir: The path to the accounts storage directory.
    :vartype account_dir: str
    :ivar name_edit: Line edit widget for account name input.
    :vartype name_edit: QLineEdit
    :ivar ip_edit: Line edit widget for IP address input.
    :vartype ip_edit: QLineEdit
    :ivar workspace_edit: Line edit widget for workspace directory input.
    :vartype workspace_edit: QLineEdit
    :ivar save_button: Button to save account changes.
    :vartype save_button: QPushButton
    :ivar delete_button: Button to delete an account.
    :vartype delete_button: QPushButton
    :ivar create_new_button: Button to create a new account.
    :vartype create_new_button: QPushButton
    :ivar set_default_button: Button to set account as default.
    :vartype set_default_button: QPushButton
    :ivar connect_button: Button to connect/disconnect from RFSoC.
    :vartype connect_button: QPushButton

    .. seealso::
        :class:`Helpers.create_button` for button creation utility.
    """

    # -------------------------------------------------------------------------
    # Signal Definitions
    # -------------------------------------------------------------------------

    rfsoc_attempt_connection: pyqtSignal = pyqtSignal(str, str)
    """
    Signal sent to the main application (Desq.py) to attempt RFSoC connection.

    :param ip_address: The IP address to attempt a connection to.
    :type ip_address: str
    :param workspace: The path to the directory where workspace files will be stored.
    :type workspace: str

    .. note::
        This signal is connected to the main Desq application's connection handler.
    """

    rfsoc_disconnect: pyqtSignal = pyqtSignal()
    """
    Signal sent to the main application (Desq.py) to disconnect the RFSoC.

    This signal takes no arguments and triggers the disconnection procedure
    in the main application.
    """

    workspace_changed: pyqtSignal = pyqtSignal(str)
    """
    Signal sent to the main application when workspace has changed (account selected changed).

    :param workspace: The new workspace directory path.
    :type workspace: str
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize an instance of the AccountsPanel widget.

        Sets up the entire UI including the accounts list, form fields for
        editing account details, and action buttons for account management.

        :param parent: The parent QWidget that this widget belongs to.
        :type parent: Optional[QWidget]

        .. note::
            This constructor automatically loads existing accounts from disk
            and sets up all signal/slot connections.
        """
        super(QAccountPanel, self).__init__(parent)

        # Initialize account tracking variables
        self.current_account_name: Optional[str] = None
        self.current_account_item: Optional[QListWidgetItem] = None
        self.default_account_name: Optional[str] = None
        self.default_account_item: Optional[QListWidgetItem] = None
        self.connected_account_name: Optional[str] = None

        # Generate the direct path to the "accounts" folder (even if it doesn't exist)
        # Uses realpath to resolve symlinks and get absolute path
        self.root_dir: str = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.account_dir: str = os.path.join(self.root_dir, 'LocalStorage/accounts')

        # -------------------------------------------------------------------------
        # Size Policy Configuration
        # -------------------------------------------------------------------------
        # Configure responsive resizing behavior for the panel
        sizepolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        sizepolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setMinimumSize(QSize(175, 0))
        self.setSizePolicy(sizepolicy)
        self.setObjectName("accounts_panel")

        # Main layout container for all components
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # -------------------------------------------------------------------------
        # Scrollable Area Setup
        # -------------------------------------------------------------------------
        # Create scrollable area to contain the accounts list for overflow handling
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setFrameShadow(QFrame.Plain)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setObjectName("scroll_area")

        self.scroll_area_content = QWidget()
        self.scroll_area_content.setObjectName("scroll_area_content")
        self.scroll_area_layout = QVBoxLayout(self.scroll_area_content)
        self.scroll_area_layout.setContentsMargins(0, 5, 0, 0)

        # -------------------------------------------------------------------------
        # Accounts Group Box
        # -------------------------------------------------------------------------
        self.accounts_group = QGroupBox("Accounts")
        self.accounts_group.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignTop)
        self.accounts_group.setObjectName("accounts_group")
        self.accounts_layout = QVBoxLayout(self.accounts_group)
        self.accounts_layout.setContentsMargins(4, 5, 4, 5)
        self.accounts_layout.setObjectName("accounts_layout")

        # -------------------------------------------------------------------------
        # Accounts List Widget
        # -------------------------------------------------------------------------
        # List widget displaying all available accounts
        self.accounts_list = QListWidget()
        self.accounts_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.accounts_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.accounts_list.setAlternatingRowColors(False)
        self.accounts_list.setSortingEnabled(True)
        self.accounts_list.setObjectName("accounts_list")
        self.accounts_layout.addWidget(self.accounts_list)

        # -------------------------------------------------------------------------
        # Account Editing Form
        # -------------------------------------------------------------------------
        # Form layout for account name, IP address, and workspace directory inputs
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(5, 0, 5, 0)
        self.form_layout.setVerticalSpacing(0)
        self.form_layout.setObjectName("form_layout")

        # Account name field
        self.name_label = QLabel()
        self.name_label.setText("Name")
        self.name_label.setObjectName("name_label")
        self.form_layout.setWidget(0, QFormLayout.LabelRole, self.name_label)
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("name_edit")
        self.form_layout.setWidget(0, QFormLayout.FieldRole, self.name_edit)

        # IP address field
        self.ip_label = QLabel()
        self.ip_label.setText("IP")
        self.ip_label.setObjectName("ip_label")
        self.form_layout.setWidget(1, QFormLayout.LabelRole, self.ip_label)
        self.ip_edit = QLineEdit()
        self.ip_edit.setObjectName("ip_edit")
        self.form_layout.setWidget(1, QFormLayout.FieldRole, self.ip_edit)

        # Workspace directory field
        self.workspace_label = QLabel()
        self.workspace_label.setText("Dir")
        self.workspace_label.setToolTip("Directory for ConfigLibrary Workspace")
        self.workspace_label.setObjectName("workspace_label")
        self.form_layout.setWidget(2, QFormLayout.LabelRole, self.workspace_label)

        self.workspace_edit = QLineEdit()
        self.workspace_edit.setObjectName("workspace_edit")
        self.workspace_edit.setToolTip("Directory for ConfigLibrary Workspace")
        self.form_layout.setWidget(2, QFormLayout.FieldRole, self.workspace_edit)

        # Browse button for workspace directory selection
        self.browse_label = QLabel()  # Empty label for form layout alignment
        self.browse_label.setObjectName("browse_label")
        self.form_layout.setWidget(3, QFormLayout.LabelRole, self.browse_label)

        self.workspace_browse_button = QPushButton("Browse")
        self.workspace_browse_button.setObjectName("workspace_browse_button")
        self.workspace_browse_button.setToolTip("Select Directory for ConfigLibrary Workspace")
        self.workspace_browse_button.clicked.connect(self.browse_workspace)
        self.form_layout.setWidget(3, QFormLayout.FieldRole, self.workspace_browse_button)

        self.accounts_layout.addLayout(self.form_layout)

        # -------------------------------------------------------------------------
        # Account Action Buttons
        # -------------------------------------------------------------------------
        self.form_button_layout = QVBoxLayout()
        self.form_button_layout.setSpacing(5)
        self.form_button_layout.setObjectName("form_button_layout")

        # Create action buttons using helper function
        self.save_button: QPushButton = Helpers.create_button("Up to Date", "save_button", False)
        self.delete_button: QPushButton = Helpers.create_button("Delete", "delete_button", True)
        self.create_new_button: QPushButton = Helpers.create_button("Create as New", "create_new_button", False)
        self.set_default_button: QPushButton = Helpers.create_button("Set as Default", "set_default_button", False)
        self.connect_button: QPushButton = Helpers.create_button("Connect", "connect_button", True)

        self.form_button_layout.addWidget(self.save_button)
        self.form_button_layout.addWidget(self.delete_button)
        self.form_button_layout.addWidget(self.create_new_button)
        self.form_button_layout.addWidget(self.set_default_button)
        self.form_button_layout.addWidget(self.connect_button)

        # -------------------------------------------------------------------------
        # Assemble Final Layout
        # -------------------------------------------------------------------------
        self.accounts_layout.addLayout(self.form_button_layout)
        self.accounts_group.setLayout(self.accounts_layout)

        self.scroll_area_layout.addWidget(self.accounts_group)
        self.scroll_area_content.setLayout(self.scroll_area_layout)
        self.scroll_area.setWidget(self.scroll_area_content)

        self.main_layout.addWidget(self.scroll_area)
        self.setLayout(self.main_layout)

        # Load existing accounts and set up signal connections
        self.load_accounts()
        self.setup_signals()

    def browse_workspace(self) -> None:
        """
        Open a file dialog to select a workspace directory.

        Uses the Helpers module to display a directory selection dialog.
        If a directory is selected, updates the workspace edit field and
        marks the form as having unsaved changes.

        :returns: None

        .. seealso::
            :func:`Helpers.open_file_dialog` for the underlying dialog implementation.
        """
        workspace_dir = Helpers.open_file_dialog(
            prompt="Select Workspace Directory",
            file_args="",
            settings_id="workspace_directory",
            parent=self,
            file=False
        )

        if workspace_dir:
            self.workspace_edit.setText(workspace_dir)
            self.unsaved_indicate()

    def setup_signals(self) -> None:
        """
        Set up all signal/slot connections for the Accounts Panel.

        Connects form editing signals, action button clicks, and account list
        selection changes to their respective handler methods.

        :returns: None

        .. note::
            This method is called automatically during initialization.
        """
        # Action button connections
        self.save_button.clicked.connect(self.update_account)
        self.delete_button.clicked.connect(self.delete_account)
        self.create_new_button.clicked.connect(self.create_account)
        self.set_default_button.clicked.connect(self.set_as_default)
        self.connect_button.clicked.connect(self.attempt_connection_or_disconnect)

        # Form field change detection for unsaved state indication
        self.ip_edit.textChanged.connect(self.unsaved_indicate)
        self.name_edit.textChanged.connect(self.unsaved_indicate)
        self.workspace_edit.textChanged.connect(self.unsaved_indicate)

        # Account list selection handling
        self.accounts_list.currentItemChanged.connect(self.select_item)

    def load_accounts(self) -> None:
        """
        Populate the accounts_list QListWidget with all locally saved accounts.

        Reads account JSON files from the accounts directory and creates
        QListWidgetItem entries for each. Also handles creation of the
        accounts directory and default template if they don't exist.

        This method:
            1. Clears any existing items in the list
            2. Creates the accounts directory and template if needed
            3. Reads the default account from default.json
            4. Iterates through all account JSON files and populates the list
            5. Selects the default account

        :returns: None

        .. note::
            See module docstring for the JSON format of account files.
        """
        # Reset current selection state
        self.current_account_name = None
        self.current_account_item = None
        self.accounts_list.clear()

        # -------------------------------------------------------------------------
        # Create accounts folder with template if it doesn't exist
        # -------------------------------------------------------------------------
        default_file = os.path.join(self.account_dir, "default.json")
        if not os.path.exists(self.account_dir) or not os.path.exists(default_file):
            os.makedirs(self.account_dir, exist_ok=True)
            template_file = os.path.join(self.account_dir, "template.json")

            # Create default.json pointing to template account
            with open(default_file, "w") as f:
                json.dump({"default_account_name": "template"}, f, indent=4)

            # Create template account with placeholder values
            with open(template_file, "w") as f:
                json.dump({
                    "ip_address": "111.111.1.111",
                    "account_name": "template",
                    "workspace": os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                }, f, indent=4)

        # -------------------------------------------------------------------------
        # Read default account name
        # -------------------------------------------------------------------------
        with open(default_file, "r") as f:
            data = json.load(f)
            self.default_account_name = data["default_account_name"]

        # -------------------------------------------------------------------------
        # Populate accounts list from JSON files
        # -------------------------------------------------------------------------
        for file in os.listdir(self.account_dir):
            if file.endswith(".json") and file != "default.json":
                with open(os.path.join(self.account_dir, file), "r") as f:
                    data = json.load(f)
                    name = data["account_name"]
                    ip = data["ip_address"]
                    workspace = data["workspace"]

                    # Handle the default account with special display text
                    if name == self.default_account_name:
                        item = QListWidgetItem(str(name + ' (default)'))
                        self.default_account_item = item
                        # Set as current if no account is currently selected
                        if self.current_account_name is None or self.current_account_item is None:
                            self.current_account_name = self.default_account_name
                            self.current_account_item = item
                    else:
                        item = QListWidgetItem(str(name))
                    self.accounts_list.addItem(item)

        # Select the current (default) account and update UI state
        self.select_item(self.current_account_item)
        self.saved_indicate()

    def attempt_connection_or_disconnect(self) -> None:
        """
        Attempt to connect to an RFSoC or disconnect based on current connection state.

        If not currently connected (connected_account_name is None), emits the
        connection signal with the IP address and workspace. Otherwise, emits
        the disconnect signal and resets the UI state.

        :returns: None

        .. note::
            The actual connection/disconnection logic is handled by the main
            Desq application which receives the emitted signals.

        .. warning::
            After disconnection, this method reloads all accounts which is
            inefficient but provides a simple way to reset the UI state.
        """
        if self.connected_account_name is None:
            # Attempt new connection
            ip_address = self.ip_edit.text().strip()
            workspace = self.workspace_edit.text().strip()
            self.rfsoc_attempt_connection.emit(ip_address, workspace)
        else:
            # Disconnect from current connection
            self.rfsoc_disconnect.emit()

            # Reset UI and variables for disconnected state
            # NOTE: Reloading all accounts is inefficient but simplifies UI reset
            self.connect_button.setText("Connect")
            self.connected_account_name = None
            self.load_accounts()

            # Re-enable form fields that were disabled during connection
            self.ip_edit.setDisabled(False)
            self.name_edit.setDisabled(False)
            self.workspace_edit.setDisabled(False)
            self.workspace_browse_button.setDisabled(False)
            self.saved_indicate()

    def unsaved_indicate(self) -> None:
        """
        Update UI to indicate unsaved changes in the form fields.

        Called when any form field (IP, name, workspace) is edited.
        Enables save and create buttons while disabling default and connect buttons.

        Button states when unsaved:
            * **Enabled**: Save, Create as New, Delete
            * **Disabled**: Set as Default, Connect

        :returns: None
        """
        self.save_button.setText("Save")
        self.save_button.setEnabled(True)
        self.create_new_button.setEnabled(True)
        self.set_default_button.setEnabled(False)
        self.connect_button.setEnabled(False)

    def saved_indicate(self) -> None:
        """
        Update UI to indicate the form is in a saved/unmodified state.

        Called when account data matches what's stored on disk.
        Disables save and create buttons while enabling default and connect buttons.

        Button states when saved:
            * **Enabled**: Set as Default, Connect, Delete
            * **Disabled**: Save, Create as New

        :returns: None
        """
        self.save_button.setText("Up to Date")
        self.save_button.setEnabled(False)
        self.create_new_button.setEnabled(False)
        self.set_default_button.setEnabled(True)
        self.connect_button.setEnabled(True)

    def disable_since_connected(self) -> None:
        """
        Update UI to indicate active RFSoC connection.

        Disables all form editing and most action buttons, allowing only
        disconnection while connected.

        Button states when connected:
            * **Enabled**: Disconnect (via connect_button)
            * **Disabled**: Save, Delete, Create as New, Set as Default, all form fields

        :returns: None
        """
        self.save_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.create_new_button.setEnabled(False)
        self.set_default_button.setEnabled(False)

        # Disable form field editing
        self.ip_edit.setDisabled(True)
        self.name_edit.setDisabled(True)
        self.workspace_edit.setDisabled(True)
        self.workspace_browse_button.setDisabled(True)

    def update_account(self) -> None:
        """
        Update the currently selected account with form field values.

        Validates the form entries, updates the JSON file, and renames the
        file if the account name changed. Also updates the default account
        reference if the modified account is the default.

        :returns: None

        :raises json.JSONDecodeError: If the account JSON file is malformed.
        :raises FileNotFoundError: If the account JSON file doesn't exist.

        .. note::
            The workspace_changed signal is emitted after successful update.
        """
        if self.current_account_name:
            # Get and validate form entries
            new_ip_address = self.ip_edit.text().strip()
            new_account_name = self.name_edit.text().strip()
            new_workspace = self.workspace_edit.text().strip()

            if not self.validate_account_input(new_ip_address, new_account_name, new_workspace, 'update'):
                return

            # Load and update the existing JSON file
            file = os.path.join(self.account_dir, self.current_account_name + '.json')
            try:
                with open(file, "r") as f:
                    data = json.load(f)
                    # Update all fields
                    data["ip_address"] = new_ip_address
                    data["account_name"] = new_account_name
                    data["workspace"] = new_workspace

                with open(file, "w") as f:
                    json.dump(data, f, indent=4)

                # Rename file if account name changed
                new_filename = (new_account_name.strip() + ".json")
                os.rename(file, os.path.join(self.account_dir, new_filename))

                # Update default account reference if this is the default account
                if self.current_account_name == self.default_account_name:
                    self.update_default_account_name(new_account_name, self.current_account_item)
                    self.current_account_item.setText(new_account_name + ' (default)')
                else:
                    self.current_account_item.setText(new_account_name)

                self.current_account_name = new_account_name
                self.saved_indicate()

                # Notify main application of workspace change
                self.workspace_changed.emit(new_workspace)

            except (json.JSONDecodeError, FileNotFoundError):
                QMessageBox.critical(None, "Error", "Error updating Json file.")
                return

    def validate_account_input(
        self,
        new_ip_address: str,
        new_account_name: str,
        new_workspace: str,
        purpose: str
    ) -> bool:
        """
        Validate input for creating or updating accounts.

        Performs validation checks including:
            * Invalid characters in account name
            * Empty fields
            * IP address format (IPv4)
            * Workspace directory existence
            * Duplicate account names (for 'create' purpose only)

        :param new_ip_address: The new IP address of the account.
        :type new_ip_address: str
        :param new_account_name: The new account name of the account.
        :type new_account_name: str
        :param new_workspace: The new workspace directory path of the account.
        :type new_workspace: str
        :param purpose: The purpose of the validation - either ``'create'`` or ``'update'``.
        :type purpose: str

        :returns: True if the input is valid, False otherwise.
        :rtype: bool

        .. note::
            Invalid characters for account names: ``./:*?"<>|`` and spaces.

        .. warning::
            **BUG**: Line 467 uses single quotes around ``{new_workspace}`` instead of
            f-string formatting, so the variable won't be interpolated in the error message.

        .. warning::
            **BUG**: Lines 479-480 attempt to strip a checkmark character using the
            literal string "âœ"" which appears to be a UTF-8 encoding issue.
            The intended character is likely "✓" (U+2713 CHECK MARK).
        """
        # Character validation for account name
        invalid_chars = r'.\/:*?"<>| '
        if any(char in new_account_name for char in invalid_chars):
            QMessageBox.critical(None, "Error", "Invalid account name. No " + invalid_chars + "or spaces.")
            return False

        # Empty field validation
        if not new_ip_address or not new_account_name:
            QMessageBox.critical(None, "Error", "IP address or account name cannot be empty.")
            return False

        # IPv4 address format validation
        # Checks that each octet is a valid number between 0-255
        if not all(part.isdigit() and 0 <= int(part) <= 255 for part in new_ip_address.split('.') if part):
            QMessageBox.critical(None, "Error", "IP address invalid.")
            return False

        # Workspace directory validation
        if not new_workspace:
            QMessageBox.critical(None, "Error", "Workspace directory cannot be empty.")
            return False
        if not os.path.exists(new_workspace):
            # BUG: Missing f-string prefix - {new_workspace} won't be interpolated
            QMessageBox.critical(None, "Error", f"The workspace directory '{new_workspace}' does not exist.")
            return False
        if not os.path.isdir(new_workspace):
            QMessageBox.critical(None, "Error", f"'{new_workspace}' is not a directory.")
            return False

        # Duplicate name validation (only for account creation)
        if purpose == 'create':
            for idx in range(self.accounts_list.count()):
                item = self.accounts_list.item(idx)
                account_name = item.text().strip()
                # Strip "(default)" suffix if present
                if account_name.endswith("(default)"):
                    account_name = account_name[:-9]
                # Strip checkmark prefix if present
                if account_name.startswith("✓"):
                    account_name = account_name[1:]
                account_name = account_name.strip()
                if account_name == new_account_name:
                    QMessageBox.critical(None, "Error", "Account name already exists.")
                    return False

        return True

    def update_default_account_name(
        self,
        new_default_account_name: str,
        new_default_account_item: QListWidgetItem
    ) -> None:
        """
        Update the default account name in default.json.

        Writes the new default account name to the default.json file and
        updates the corresponding instance variables.

        :param new_default_account_name: The new default account name.
        :type new_default_account_name: str
        :param new_default_account_item: The new default account item.
        :type new_default_account_item: QListWidgetItem

        :returns: None

        :raises json.JSONDecodeError: If there's an error encoding the JSON.
        :raises FileNotFoundError: If the default.json file cannot be created.

        .. note::
            See module docstring for the format of default.json.
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

    def create_account(self) -> None:
        """
        Create a new account from the current form field values.

        Validates the input, creates a new JSON file with the account data,
        and adds a new item to the accounts list. The new account is then
        automatically selected.

        :returns: None

        .. seealso::
            :meth:`validate_account_input` for validation details.
        """
        new_ip_address = self.ip_edit.text().strip()
        new_account_name = self.name_edit.text().strip()
        new_workspace = self.workspace_edit.text().strip()

        if not self.validate_account_input(new_ip_address, new_account_name, new_workspace, 'create'):
            return

        # Create the new account JSON file
        new_filename = (new_account_name.strip() + ".json")
        new_account_file = os.path.join(self.account_dir, new_filename)

        with open(new_account_file, "w") as f:
            json.dump({
                "ip_address": str(new_ip_address),
                "account_name": str(new_account_name),
                "workspace": str(new_workspace)
            }, f, indent=4)

        # Add to list and select the new account
        item = QListWidgetItem(str(new_account_name))
        self.accounts_list.addItem(item)
        self.select_item(item)

    def select_item(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem] = None
    ) -> None:
        """
        Handle account selection from the accounts list.

        Called when the user clicks on a QListWidgetItem. Updates the current
        account tracking variables and populates the form fields with the
        account data from its JSON file.

        :param current: The newly selected item.
        :type current: Optional[QListWidgetItem]
        :param previous: The previously selected item (unused but required by signal signature).
        :type previous: Optional[QListWidgetItem]

        :returns: None

        .. note::
            This method handles both old format (with "config" key) and new format
            (with "workspace" key) account files for backward compatibility.
        """
        if current is not None:
            # Extract clean account name by stripping display decorations
            account_name = current.text().strip()
            if account_name.endswith("(default)"):
                account_name = account_name[:-9]
            if account_name.startswith("✓"):
                account_name = account_name[1:]
            self.current_account_name = account_name.strip()
            self.current_account_item = current
            self.accounts_list.setCurrentItem(current)

            # Load account data from JSON file
            file = os.path.join(self.account_dir, self.current_account_name + '.json')
            try:
                with open(file, "r") as f:
                    data = json.load(f)
                    name = data["account_name"]
                    ip = data["ip_address"]

                    # Handle both old format ("config") and new format ("workspace")
                    # for backward compatibility with existing account files
                    if "workspace" in data:
                        workspace = data["workspace"]
                    elif "config" in data:
                        workspace = data["config"]
                    else:
                        workspace = ""

                    # Populate form fields
                    self.name_edit.setText(name)
                    self.ip_edit.setText(ip)
                    self.workspace_edit.setText(workspace)

                    # Notify main application of workspace change
                    self.workspace_changed.emit(workspace)

            except Exception as e:
                QMessageBox.critical(None, "Error", f"Error loading account file: {str(e)}")
                return

            # Update UI state based on connection status
            if self.connected_account_name is not None:
                self.disable_since_connected()
            else:
                self.saved_indicate()

    def delete_account(self) -> None:
        """
        Delete the currently selected account.

        Removes the account's JSON file and its entry from the accounts list.
        Prevents deletion of the default account. If the deleted account was
        connected, emits the disconnect signal.

        :returns: None

        .. note::
            After deletion, the default account is automatically selected.

        .. warning::
            The default account cannot be deleted. Users must set a different
            account as default before deleting the current default.
        """
        # Prevent deletion of the default account
        if self.current_account_name == self.default_account_name:
            QMessageBox.critical(None, "Error", "Cannot delete default account.")
            return

        # Remove the JSON file
        file = os.path.join(self.account_dir, self.current_account_name + '.json')
        if os.path.exists(file):
            os.remove(file)
        else:
            QMessageBox.critical(None, "Error", "Cannot find file with account name.")
            return

        # Remove from list widget
        selected_item_row_idx = self.accounts_list.currentRow()
        self.accounts_list.takeItem(selected_item_row_idx)

        # Disconnect if this was the connected account
        if self.current_account_name == self.connected_account_name:
            self.rfsoc_disconnect.emit()

        # Select the default account
        self.select_item(self.default_account_item)

    def set_as_default(self) -> None:
        """
        Set the currently selected account as the default.

        Updates the default.json file with the current account name and
        reloads all accounts to update the display.

        :returns: None
        """
        self.update_default_account_name(self.current_account_name, self.current_account_item)
        self.load_accounts()

    def rfsoc_connection_updated(self, ip_address: str, status: str) -> None:
        """
        Handle RFSoC connection status update from the main application.

        Called when the main Desq application reports the result of a
        connection attempt. Updates the UI and tracking variables based
        on success or failure.

        :param ip_address: The IP address of the RFSoC.
        :type ip_address: str
        :param status: The status of the RFSoC connection - either ``'success'`` or ``'failure'``.
        :type status: str

        :returns: None

        .. note::
            On successful connection, a checkmark (✓) is prepended to the
            account name in the list display.
        """
        if status == 'success':
            # Successful connection - update tracking and display
            self.connected_account_name = self.current_account_name

            # Add checkmark to account name display
            if self.current_account_name == self.default_account_name:
                self.current_account_item.setText('✓ ' + self.current_account_name + ' (default)')
            else:
                self.current_account_item.setText('✓ ' + self.current_account_name)

            self.connect_button.setText("Disconnect")
            self.disable_since_connected()
        else:
            # Failed connection - reset to disconnected state
            self.connected_account_name = None
            self.saved_indicate()