"""
=====================
DirectoryTreePanel.py
=====================

This module provides a directory tree panel component for navigable file system views
within the Desq GUI application.

The module contains two main classes:

- :class:`FilteredFileSystemModel`: A custom QFileSystemModel that displays all files
  but disables selection of files that don't match specified filters.
- :class:`DirectoryTreePanel`: A panel widget that displays an interactive directory
  tree view with file filtering capabilities.

Module-level Variables
----------------------

:var Helpers: Helper utilities module for GUI operations.
:vartype Helpers: module

.. seealso::

    :mod:`MasterProject.Client_modules.Desq_GUI.scripts.Helpers`
        Helper utilities used for button creation and file dialogs.
"""

from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeView,
    QFileSystemModel,
    QHBoxLayout,
    QAbstractItemView,
    QMessageBox
)
from PyQt5.QtCore import Qt, QDir, QSettings, pyqtSignal, qWarning, QSize
from PyQt5.QtGui import QIcon
import os
from typing import Optional, List

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers


class FilteredFileSystemModel(QFileSystemModel):
    """
    Custom QFileSystemModel that shows all files but disables those that don't match
    the specified file filters.

    This model extends :class:`QFileSystemModel` to provide visual filtering of files
    based on their extensions. Files that don't match the filter appear grayed out
    and cannot be selected, while directories remain navigable regardless of filters.

    :ivar file_filters: List of file extensions that should remain enabled
        (e.g., ``['.py', '.h5']``).
    :vartype file_filters: List[str]

    .. note::

        Files that don't match the filter are still visible but appear grayed out
        and cannot be selected. This provides better context than hiding files entirely.
    """

    def __init__(self, parent: Optional[QWidget] = None,
                 file_filters: Optional[List[str]] = None) -> None:
        """
        Initialize the FilteredFileSystemModel.

        :param parent: The parent widget for this model.
        :type parent: Optional[QWidget]
        :param file_filters: List of file extensions to keep enabled
            (e.g., ``['.py', '.h5', '.json']``). If ``None``, an empty list is used.
        :type file_filters: Optional[List[str]]
        """
        super().__init__(parent)
        self.file_filters: List[str] = file_filters if file_filters else []

    def set_file_filters(self, file_filters: List[str]) -> None:
        """
        Update the file filters used for enabling/disabling files.

        :param file_filters: List of file extensions to keep enabled.
        :type file_filters: List[str]

        .. note::

            After calling this method, you should refresh the view to apply
            the new filters visually.
        """
        self.file_filters = file_filters

    def flags(self, index) -> Qt.ItemFlags:
        """
        Override flags to disable files that don't match the file filters.

        Directories remain enabled for navigation regardless of filter settings.
        Files that match the filter retain default flags, while non-matching files
        are completely disabled (no selection, no interaction).

        :param index: The model index to get flags for.
        :type index: QModelIndex
        :returns: The item flags for the given index.
        :rtype: Qt.ItemFlags

        .. note::

            This method uses :data:`Qt.NoItemFlags` for non-matching files,
            which removes both selectable and enabled flags.
        """
        if not index.isValid():
            return super().flags(index)

        # Get default flags from the base QFileSystemModel implementation
        default_flags = super().flags(index)

        # Get the file path for the given index
        path = self.filePath(index)

        # Directories always remain enabled to allow navigation through the tree
        if os.path.isdir(path):
            return default_flags

        # For files, check if the extension matches our filter list
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in self.file_filters:
                # File matches filter - keep it fully enabled and selectable
                return default_flags
            else:
                # File doesn't match filter - completely disable it
                # Qt.NoItemFlags removes both ItemIsSelectable and ItemIsEnabled
                return Qt.NoItemFlags

        return default_flags

    def data(self, index, role: int = Qt.DisplayRole):
        """
        Override data to style disabled items with a gray foreground color.

        This method intercepts the :data:`Qt.ForegroundRole` to return a gray color
        for files that don't match the filter, providing visual feedback that
        these files are not selectable.

        :param index: The model index to get data for.
        :type index: QModelIndex
        :param role: The data role to retrieve (default: :data:`Qt.DisplayRole`).
        :type role: int
        :returns: The data for the given index and role. Returns a gray
            :class:`QColor` for non-matching files when role is
            :data:`Qt.ForegroundRole`.
        :rtype: Any

        .. note::

            The gray color (RGB 128, 128, 128) is hardcoded. Consider making
            this configurable for theme compatibility.
        """
        if role == Qt.ForegroundRole:
            if not index.isValid():
                return super().data(index, role)

            path = self.filePath(index)

            # Only apply gray styling to files, not directories
            if os.path.isfile(path):
                ext = os.path.splitext(path)[1].lower()
                if ext not in self.file_filters:
                    # Import QColor here to avoid circular imports at module level
                    # NOTE: This import could be moved to the top of the file for
                    # better performance if called frequently
                    from PyQt5.QtGui import QColor
                    return QColor(128, 128, 128)  # Gray color for disabled files

        return super().data(index, role)


class DirectoryTreePanel(QWidget):
    """
    A panel widget that displays an interactive directory tree view.

    This panel provides a file browser interface using :class:`QFileSystemModel`
    with support for file filtering, directory selection, and persistent
    directory history via :class:`QSettings`.

    :ivar load_file: Signal emitted when a file is double-clicked (full path).
    :vartype load_file: pyqtSignal(str)
    :ivar file_selected: Signal emitted when a file is single-clicked (full path).
    :vartype file_selected: pyqtSignal(str)
    :ivar file_filters: List of enabled file extensions (e.g., ``['.py', '.h5']``).
    :vartype file_filters: List[str]
    :ivar history_key: QSettings key for persisting the last selected directory.
    :vartype history_key: Optional[str]
    :ivar workspace: Base workspace directory path.
    :vartype workspace: str
    :ivar default_folder_name: Default subfolder name within the Data directory.
    :vartype default_folder_name: Optional[str]
    :ivar layout: Main vertical layout for the panel.
    :vartype layout: QVBoxLayout
    :ivar toolbar_layout: Horizontal layout for the toolbar area.
    :vartype toolbar_layout: QHBoxLayout
    :ivar load_directory_button: Button to open directory selection dialog.
    :vartype load_directory_button: QPushButton
    :ivar tree_view: The tree view widget displaying the directory structure.
    :vartype tree_view: QTreeView
    :ivar model: The filtered file system model backing the tree view.
    :vartype model: FilteredFileSystemModel
    :ivar settings: QSettings instance for persisting user preferences.
    :vartype settings: QSettings

    .. note::

        The panel automatically creates a "Data" subdirectory in the workspace
        if it doesn't exist, and optionally creates an experiment-specific
        subfolder based on the parent widget's name.

    .. seealso::

        :class:`FilteredFileSystemModel`
            The custom model used for file filtering in the tree view.
    """

    # Signal emitted when a file is double-clicked, passing the full file path
    load_file: pyqtSignal = pyqtSignal(str)
    # Signal emitted when a file is single-clicked, passing the full file path
    file_selected: pyqtSignal = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None,
                 file_filters: Optional[List[str]] = None,
                 history_key: Optional[str] = None,
                 workspace: Optional[str] = None) -> None:
        """
        Initialize the DirectoryTreePanel.

        :param parent: The parent widget. If the parent has a ``name`` attribute,
            it will be used as the default folder name within the Data directory.
        :type parent: Optional[QWidget]
        :param file_filters: List of file extensions to enable for selection
            (e.g., ``['.py', '.h5', '.json']``). Defaults to common experiment
            and image file types if not provided.
        :type file_filters: Optional[List[str]]
        :param history_key: QSettings key for persisting the selected directory.
            If ``None``, the panel assumes it's a config selector and uses
            the Data directory instead of saved history.
        :type history_key: Optional[str]
        :param workspace: Base workspace directory path. Defaults to the parent
            directory of the module's location.
        :type workspace: Optional[str]

        .. note::

            When ``history_key`` is ``None``, the panel operates in "config selector"
            mode, creating and navigating to a ``Data`` subdirectory within the
            workspace rather than restoring a previously saved directory.
        """
        super().__init__(parent)
        self.setObjectName("DirectoryTreePanel")
        self.setMinimumSize(125, 0)

        # Set default file filters for common experiment and image file types
        self.file_filters: List[str] = file_filters if file_filters is not None else [
            '.py', '.h5',  # Experiments and data
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'  # Images
        ]

        self.history_key: Optional[str] = history_key
        # Default workspace is one level up from this module's directory
        self.workspace: str = workspace or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        # Extract default folder name from parent widget if available
        self.default_folder_name: Optional[str] = parent.name if parent and hasattr(parent, "name") else None
        # Treat empty string as None for consistency
        if self.default_folder_name and len(self.default_folder_name) == 0:
            self.default_folder_name = None

        # Create main layout with no spacing or margins for compact appearance
        self.layout: QVBoxLayout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # ----- Toolbar Setup -----
        self.toolbar_layout: QHBoxLayout = QHBoxLayout()
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar_layout.setSpacing(0)

        # Create directory selection button with dropdown chevron icon
        self.load_directory_button = Helpers.create_button("", "load_directory", True, self)
        self.load_directory_button.setToolTip("Select Directory")
        icon = QIcon("MasterProject/Client_modules/Desq_GUI/assets/chevron-down.svg")
        self.load_directory_button.setIcon(icon)
        self.load_directory_button.setIconSize(QSize(14, 14))  # exact display size in px
        # Right-to-left layout places icon after text
        self.load_directory_button.setLayoutDirection(Qt.RightToLeft)

        self.toolbar_layout.addWidget(self.load_directory_button)

        # Add toolbar layout to main layout
        self.layout.addLayout(self.toolbar_layout)

        # ----- Tree View Setup -----
        self.tree_view: QTreeView = QTreeView(self)
        self.tree_view.setObjectName("directory_tree_view")
        self.tree_view.setAnimated(False)  # Disable animations for performance
        self.tree_view.setIndentation(15)  # Pixels of indentation per tree level
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setHeaderHidden(True)  # Hide column headers for cleaner look
        self.tree_view.setTextElideMode(Qt.ElideNone)  # Don't truncate long names
        self.tree_view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        # Create custom model with file filtering capability
        self.model: FilteredFileSystemModel = FilteredFileSystemModel(file_filters=self.file_filters)
        self.model.setRootPath("")

        # Configure model filters to show all directories and files (filtering is
        # handled by the custom model's flags() method, not by hiding files)
        self.model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Files)

        # Connect model to tree view
        self.tree_view.setModel(self.model)

        # Configure column visibility - only show the Name column
        self.tree_view.setColumnWidth(0, 500)  # Name column - wide to accommodate long paths
        self.tree_view.hideColumn(1)  # Hide Size column
        self.tree_view.hideColumn(2)  # Hide Type column
        self.tree_view.hideColumn(3)  # Hide Date Modified column

        # Add tree view to main layout
        self.layout.addWidget(self.tree_view)

        # ----- Initialize Directory from Settings -----
        self.settings: QSettings = QSettings("HouckLab", "Desq")

        last_dir: Path = Path("..")

        if self.history_key is not None:
            # Restore last used directory from settings, defaulting to user home
            last_dir = self.settings.value("load_directory", os.path.expanduser("~"))
        else:
            # Config selector mode: use Data directory within workspace
            data_path = os.path.join(self.workspace, "Data")
            os.makedirs(data_path, exist_ok=True)

            # Create experiment-specific subfolder if default_folder_name is set
            if self.default_folder_name is not None:
                data_path = os.path.join(data_path, self.default_folder_name)
                os.makedirs(data_path, exist_ok=True)

            last_dir = data_path

        self.set_directory(last_dir)

        # ----- Connect Signals -----
        self.load_directory_button.clicked.connect(self.select_directory)
        self.tree_view.doubleClicked.connect(self.file_double_clicked)
        self.tree_view.clicked.connect(self.file_clicked)

    def change_workspace(self, workspace: str) -> None:
        """
        Change the workspace directory and update the tree view accordingly.

        This method validates that the new workspace exists, creates the
        required Data subdirectory structure, and navigates the tree view
        to the appropriate location.

        :param workspace: The new workspace directory path.
        :type workspace: str
        :raises FileNotFoundError: If the specified workspace directory does not exist.

        .. note::

            This method creates the following directory structure if it doesn't exist:
            ``<workspace>/Data/`` and optionally ``<workspace>/Data/<default_folder_name>/``
        """
        # Step 1: Validate that the base workspace directory exists
        if not os.path.isdir(workspace):
            raise FileNotFoundError(f"The directory '{workspace}' does not exist.")

        self.workspace = workspace

        # Step 2: Create Data folder inside the workspace if missing
        data_path = os.path.join(workspace, "Data")
        os.makedirs(data_path, exist_ok=True)

        # Step 3: Create experiment-specific folder inside Data if configured
        if self.default_folder_name is not None and len(self.default_folder_name) != 0:
            final_folder_path = os.path.join(data_path, self.default_folder_name)
            os.makedirs(final_folder_path, exist_ok=True)

            # Navigate to the experiment-specific folder
            self.set_directory(final_folder_path)
        else:
            # Navigate to the Data folder
            self.set_directory(data_path)

    def file_clicked(self, index) -> None:
        """
        Handle single-click events on items in the tree view.

        Emits the :attr:`file_selected` signal when a valid file matching
        the current filters is clicked.

        :param index: The model index of the clicked item.
        :type index: QModelIndex

        .. note::

            This method only emits signals for files that match the current
            filter settings. Clicks on directories or non-matching files
            are silently ignored.
        """
        if not index.isValid():
            return

        # Get the full filesystem path for the clicked item
        path = self.model.filePath(index)

        # Only emit signal for files that match the filter
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in self.file_filters:
                self.file_selected.emit(path)

    def file_double_clicked(self, index) -> None:
        """
        Handle double-click events on items in the tree view.

        Emits the :attr:`load_file` signal when a valid file matching
        the current filters is double-clicked. Shows an error dialog
        for unsupported file types.

        :param index: The model index of the double-clicked item.
        :type index: QModelIndex

        .. note::

            Double-clicking on directories triggers the default tree view
            expansion behavior and does not emit any signals from this method.
        """
        if not index.isValid():
            return

        # Get the full filesystem path for the double-clicked item
        path = self.model.filePath(index)

        # Only process files (directories use default tree expansion behavior)
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in self.file_filters:
                # Emit signal to load the file
                self.load_file.emit(path)
            else:
                # Show error for unsupported file types
                # NOTE: This error can occur even though the file appears disabled,
                # if the user somehow manages to double-click a grayed-out file
                qWarning(f"Unsupported file type, only {self.file_filters} supported.")
                QMessageBox.critical(None, "TypeError", f"Unsupported file type, only {self.file_filters} supported.")

    def select_directory(self) -> None:
        """
        Open a directory selection dialog and set the selected directory as root.

        Uses the :mod:`Helpers` module's file dialog with history support when
        a history_key is configured. The dialog's initial directory depends on
        whether history is enabled.

        .. seealso::

            :func:`Helpers.open_file_dialog`
                The helper function used to display the directory selection dialog.
        """
        directory: str = ""

        if self.history_key is not None:
            # Use history-enabled dialog that remembers last used directory
            directory = Helpers.open_file_dialog("Select Directory", "",
                                                 self.history_key, self, file=False)
        else:
            # Use dialog starting from current directory (no history persistence)
            directory = Helpers.open_file_dialog("Select Directory", "",
                                                 self.history_key, self, file=False,
                                                 initial_dir=self.get_current_directory())

        if directory:
            self.set_directory(directory)

    def set_directory(self, path: str) -> None:
        """
        Set the root directory for the tree view.

        Updates the model's root path, the tree view's root index, the button
        text to show the current folder name, and optionally saves the path
        to settings for persistence.

        :param path: The directory path to set as the tree view root.
        :type path: str

        .. note::

            If ``history_key`` is set, the directory path is saved to
            :class:`QSettings` for restoration on next launch.
        """
        # Set the root path in the model and get the corresponding index
        root_index = self.model.setRootPath(path)

        # Update the tree view to show from this root
        self.tree_view.setRootIndex(root_index)

        # Update button text to show current folder name
        # os.path.basename returns empty string for root paths, so fallback to full path
        folder_name = os.path.basename(path) or path
        self.load_directory_button.setText(folder_name)

        # Persist the directory to settings if history is enabled
        if self.history_key:
            self.settings.setValue(self.history_key, path)

    def refresh_view(self) -> None:
        """
        Refresh the directory view to show any new or modified files.

        Forces the model to reload the current directory by temporarily
        resetting the root path. This is useful after file operations
        that may have changed the directory contents.

        .. note::

            This is a workaround to force :class:`QFileSystemModel` to
            refresh its cache. The model's built-in file watching may
            not always detect changes immediately.
        """
        current_path = self.model.rootPath()
        # Force model to reload by clearing and resetting root path
        self.model.setRootPath("")
        self.model.setRootPath(current_path)

    def set_file_filters(self, file_filters: List[str]) -> None:
        """
        Set the file filters to determine which files can be selected.

        Updates both the panel's internal filter list and the underlying
        model's filters, then refreshes the view to apply the changes.

        :param file_filters: List of file extensions to enable
            (e.g., ``['.py', '.h5', '.json']``).
        :type file_filters: List[str]

        .. note::

            This method automatically calls :meth:`refresh_view` to
            apply the new filters visually.
        """
        self.file_filters = file_filters
        # Synchronize filters to the underlying model
        self.model.set_file_filters(file_filters)
        # Refresh the view to apply visual changes
        self.refresh_view()

    def get_current_directory(self) -> str:
        """
        Get the current root directory path.

        :returns: The current root directory path as set in the model.
        :rtype: str
        """
        return self.model.rootPath()