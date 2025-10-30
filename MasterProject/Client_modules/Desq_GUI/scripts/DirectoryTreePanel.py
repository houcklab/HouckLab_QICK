"""
====================
DirectoryTreePanel.py
====================

This module contains the directory tree panel component that shows a navigable file system view.
"""

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeView,
    QFileSystemModel,
    QFileDialog,
    QToolBar,
    QAction, QHBoxLayout, QSpacerItem, QSizePolicy, QAbstractItemView, QMessageBox
)
from PyQt5.QtCore import Qt, QDir, QSettings, pyqtSignal, qWarning, QSize
from PyQt5.QtGui import QIcon
import os

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers


class FilteredFileSystemModel(QFileSystemModel):
    """
    Custom QFileSystemModel that shows all files but disables those that don't match the file filters.
    """

    def __init__(self, parent=None, file_filters=None):
        super().__init__(parent)
        self.file_filters = file_filters if file_filters else []

    def set_file_filters(self, file_filters):
        """Update the file filters."""
        self.file_filters = file_filters

    def flags(self, index):
        """
        Override flags to disable files that don't match the file filters.
        Directories remain enabled for navigation.
        """
        if not index.isValid():
            return super().flags(index)

        # Get default flags
        default_flags = super().flags(index)

        # Get the file path
        path = self.filePath(index)

        # If it's a directory, keep it enabled
        if os.path.isdir(path):
            return default_flags

        # If it's a file, check if it matches our filters
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in self.file_filters:
                # File matches filter - keep it enabled
                return default_flags
            else:
                # File doesn't match filter - disable it
                # Remove selectable and enabled flags
                return Qt.NoItemFlags

        return default_flags

    def data(self, index, role=Qt.DisplayRole):
        """
        Override data to style disabled items (gray them out).
        """
        if role == Qt.ForegroundRole:
            if not index.isValid():
                return super().data(index, role)

            path = self.filePath(index)

            # Only apply styling to files
            if os.path.isfile(path):
                ext = os.path.splitext(path)[1].lower()
                if ext not in self.file_filters:
                    # Return a gray color for disabled files
                    from PyQt5.QtGui import QColor
                    return QColor(128, 128, 128)  # Gray color

        return super().data(index, role)


class DirectoryTreePanel(QWidget):
    """
    A panel that displays a directory tree view using QFileSystemModel.
    Allows selecting and navigating directories.
    """

    load_file = pyqtSignal(str)  # emits the full path of the file
    file_selected = pyqtSignal(str)  # emits the full path of the file when selected (single click)

    def __init__(self, parent=None, file_filters=None, history_key=None, workspace=None):
        """
        Initialize the DirectoryTreePanel.

        :param parent: The parent widget
        :type parent: QWidget
        :param file_filters: List of file extensions to filter (e.g. ['.py', '.h5', '.json'])
        :type file_filters: list
        """
        super().__init__(parent)
        self.setObjectName("DirectoryTreePanel")
        self.setMinimumSize(125, 0)

        # Set default file filters if none provided
        self.file_filters = file_filters if file_filters is not None else ['.py', '.h5']

        self.history_key = history_key
        self.workspace = workspace or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.default_folder_name = parent.name if parent and hasattr(parent, "name") else None
        if self.default_folder_name and len(self.default_folder_name) == 0:
            self.default_folder_name = None

        # Create main layout
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar setup
        self.toolbar_layout = QHBoxLayout()
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar_layout.setSpacing(0)

        self.load_directory_button = Helpers.create_button("", "load_directory", True, self)
        self.load_directory_button.setToolTip("Select Directory")
        icon = QIcon("MasterProject/Client_modules/Desq_GUI/assets/chevron-down.svg")
        self.load_directory_button.setIcon(icon)
        self.load_directory_button.setIconSize(QSize(14, 14))  # exact display size in px
        self.load_directory_button.setLayoutDirection(Qt.RightToLeft)

        self.toolbar_layout.addWidget(self.load_directory_button)

        # Add toolbar to main layout
        self.layout.addLayout(self.toolbar_layout)

        # Create tree view
        self.tree_view = QTreeView(self)
        self.tree_view.setObjectName("directory_tree_view")
        self.tree_view.setAnimated(False)
        self.tree_view.setIndentation(15)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setTextElideMode(Qt.ElideNone)
        self.tree_view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        # Create and set up custom model with file filters
        self.model = FilteredFileSystemModel(file_filters=self.file_filters)
        self.model.setRootPath("")

        # Set Filters - show all files and directories
        self.model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Files)

        # Set the model to tree view
        self.tree_view.setModel(self.model)

        # Hide unnecessary columns
        self.tree_view.setColumnWidth(0, 500)  # Name column
        self.tree_view.hideColumn(1)  # Size column
        self.tree_view.hideColumn(2)  # Type column
        self.tree_view.hideColumn(3)  # Date Modified column

        # Add tree view to main layout
        self.layout.addWidget(self.tree_view)

        # Set initial directory as the saved one in QSettings
        self.settings = QSettings("HouckLab", "Desq")
        last_dir = "..\\"
        if self.history_key is not None:
            last_dir = self.settings.value("load_directory", os.path.expanduser("~"))
        else:  # If no history key is specified, assume it is a config selector directory panel
            data_path = os.path.join(self.workspace, "Data")
            os.makedirs(data_path, exist_ok=True)

            if self.default_folder_name is not None:
                data_path = os.path.join(data_path, self.default_folder_name)
                os.makedirs(data_path, exist_ok=True)

            last_dir = data_path
        self.set_directory(last_dir)

        # Signals
        self.load_directory_button.clicked.connect(self.select_directory)
        self.tree_view.doubleClicked.connect(self.file_double_clicked)
        self.tree_view.clicked.connect(self.file_clicked)

    def change_workspace(self, workspace):
        # Step 1: make sure the base_dir exists
        if not os.path.isdir(workspace):
            raise FileNotFoundError(f"The directory '{workspace}' does not exist.")

        self.workspace = workspace
        # Step 2: create Data folder inside the final folder if missing
        data_path = os.path.join(workspace, "Data")
        os.makedirs(data_path, exist_ok=True)

        # Step 3: create Experiment Folder inside Data folder if missing
        if self.default_folder_name is not None and len(self.default_folder_name) != 0:
            final_folder_path = os.path.join(data_path, self.default_folder_name)
            os.makedirs(final_folder_path, exist_ok=True)

            # set directory there
            self.set_directory(final_folder_path)
        else:
            self.set_directory(data_path)

    def file_clicked(self, index):
        """
        Called when an item in the tree view is clicked.

        :param index: The QModelIndex of the clicked item
        """
        if not index.isValid():
            return

        # Get the full path of the item
        path = self.model.filePath(index)

        # Check if it's a file
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in self.file_filters:
                self.file_selected.emit(path)

    def file_double_clicked(self, index):
        """
        Called when an item in the tree view is double-clicked.

        :param index: The QModelIndex of the clicked item
        """
        if not index.isValid():
            return

        # Get the full path of the item
        path = self.model.filePath(index)

        # Check if it's a file
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in self.file_filters:
                self.load_file.emit(path)
            else:
                qWarning(f"Unsupported file type, only {self.file_filters} supported.")
                QMessageBox.critical(None, "TypeError", f"Unsupported file type, only {self.file_filters} supported.")

    def select_directory(self):
        """
        Open a directory selection dialog and set the selected directory as root.
        """
        directory = ""
        if self.history_key is not None:
            directory = Helpers.open_file_dialog("Select Directory", "",
                                                 self.history_key, self, file=False)
        else:
            directory = Helpers.open_file_dialog("Select Directory", "",
                                                 self.history_key, self, file=False, dir=self.get_current_directory())
        if directory:
            self.set_directory(directory)

    def set_directory(self, path):
        """
        Set the root directory for the tree view.

        :param path: The path to set as root
        :type path: str
        """
        # Set the root path in the model
        root_index = self.model.setRootPath(path)

        # Set the root index in the tree view
        self.tree_view.setRootIndex(root_index)

        # Update button text
        folder_name = os.path.basename(path) or path
        self.load_directory_button.setText(folder_name)

        # Save the directory in settings
        if self.history_key:
            self.settings.setValue(self.history_key, path)

    def refresh_view(self):
        """
        Refresh the directory view to show any new or modified files.
        """
        current_path = self.model.rootPath()
        # Force model to reload directory
        self.model.setRootPath("")
        self.model.setRootPath(current_path)

    def set_file_filters(self, file_filters):
        """
        Set the file filters to determine which files can be selected.

        :param file_filters: List of file extensions to filter (e.g. ['.py', '.h5', '.json'])
        :type file_filters: list
        """
        self.file_filters = file_filters
        # Update the model's filters as well
        self.model.set_file_filters(file_filters)
        # Refresh the view to apply the new filters
        self.refresh_view()

    def get_current_directory(self):
        """
        Get the current directory path.

        :return: Current directory path
        :rtype: str
        """
        return self.model.rootPath()