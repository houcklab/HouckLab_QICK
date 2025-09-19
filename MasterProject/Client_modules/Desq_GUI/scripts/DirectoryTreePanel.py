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
from PyQt5.QtCore import Qt, QDir, QSettings, pyqtSignal, qWarning
from PyQt5.QtGui import QIcon
import os

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers

class DirectoryTreePanel(QWidget):
    """
    A panel that displays a directory tree view using QFileSystemModel.
    Allows selecting and navigating directories.
    """

    load_file = pyqtSignal(str)  # emits the full path of the file

    def __init__(self, parent=None):
        """
        Initialize the DirectoryTreePanel.

        :param parent: The parent widget
        :type parent: QWidget
        """
        super().__init__(parent)
        self.setObjectName("DirectoryTreePanel")
        self.setMinimumSize(125, 0)
        
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

        # Create and set up model
        self.model = QFileSystemModel()
        self.model.setRootPath("")
        
        # Set Filters
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
        last_dir = self.settings.value("load_directory", os.path.expanduser("~"))
        self.set_directory(last_dir)

        # Signals
        self.load_directory_button.clicked.connect(self.select_directory)
        self.tree_view.doubleClicked.connect(self.file_double_clicked)

    def file_double_clicked(self, index):
        """
        Called when an item in the tree view is double-clicked.

        :param index: The QModelIndex of the clicked item
        """
        if not index.isValid():
            return

        # Get the full path of the item
        path = self.model.filePath(index)

        # Optional: check if it's a file
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.py', '.h5']:
                self.load_file.emit(path)
            else:
                qWarning("Unsupported file type, only [.py, .h5] supported.")
                QMessageBox.critical(None, "TypeError", "Unsupported file type, only [.py, .h5] supported.")
            pass

    def select_directory(self):
        """
        Open a directory selection dialog and set the selected directory as root.
        """

        directory = Helpers.open_file_dialog("Select Directory", "",
                                        "load_directory", self, file=False)
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
        
        # Only set root index for tree view
        self.tree_view.setRootIndex(root_index)

        # Update button text
        folder_name = os.path.basename(path) or path
        self.load_directory_button.setText(folder_name)
