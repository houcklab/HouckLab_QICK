
from PyQt5 import QtGui, QtCore, uic

from PyQt5.QtWidgets import (
    QDialog,
    QApplication, 
    QMainWindow, 
    QFileDialog, 
    QWidget, 
    QGridLayout,
    QLineEdit,
    QTextEdit,
    QPushButton, 
    QLabel,
    QTreeView,
    QHBoxLayout,
    QVBoxLayout, 
    QAbstractItemView
    )

class QDictEdit(QTreeView):

    def __init__(self, config):
        
        super(QDictEdit, self).__init__()

        self.config = config
        self.tree = QTreeView()

        hbox = QHBoxLayout()
        hbox.addStretch(1)
        vbox = QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.tree)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)

        # Tree view
        self.tree.setModel(QtGui.QStandardItemModel())
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.setHeaderHidden(False)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectItems)

        self.tree.model().itemChanged.connect(self.handleItemChanged)

        self.tree.model().setHorizontalHeaderLabels(['Parameter', 'Value'])

        ### loop through the dictionary and load into tree
        for x in self.config:
            if not self.config[x]:
                continue
            parent = QtGui.QStandardItem(x)
            parent.setFlags(QtCore.Qt.NoItemFlags)
            for y in self.config[x]:
                value = self.config[x][y]
                child0 = QtGui.QStandardItem(y)
                child0.setFlags(QtCore.Qt.NoItemFlags |
                                QtCore.Qt.ItemIsEnabled)
                child1 = QtGui.QStandardItem(str(value))
                child1.setFlags(QtCore.Qt.ItemIsEnabled |
                                QtCore.Qt.ItemIsEditable |
                                ~ QtCore.Qt.ItemIsSelectable)
                parent.appendRow([child0, child1])

            self.tree.model().appendRow(parent)

#            self.tree.model().removeRow(0)

        self.tree.expandAll()

    def set_config(self, config_update = None):

        #### remove the current config
        #### remove current rows to add new
        self.tree.model().removeRow(0)
        self.tree.model().removeRow(0)



        ### set the config to something new and reshow it
        if config_update is not None:
            self.config = config_update

        ### loop through the dictionary and load into tree
        for x in self.config:
            if not self.config[x]:
                continue
            parent = QtGui.QStandardItem(x)
            parent.setFlags(QtCore.Qt.NoItemFlags)
            for y in self.config[x]:
                value = self.config[x][y]
                child0 = QtGui.QStandardItem(y)
                child0.setFlags(QtCore.Qt.NoItemFlags |
                                QtCore.Qt.ItemIsEnabled)
                child1 = QtGui.QStandardItem(str(value))
                child1.setFlags(QtCore.Qt.ItemIsEnabled |
                                QtCore.Qt.ItemIsEditable |
                                ~ QtCore.Qt.ItemIsSelectable)
                parent.appendRow([child0, child1])

            self.tree.model().appendRow(parent)

        self.tree.expandAll()


    def get_config(self):
        return self.config

    def handleItemChanged(self, item):
        parent = self.config[item.parent().text()]
        key = item.parent().child(item.row(), 0).text()
        parent[key] = type(parent[key])(item.text())





