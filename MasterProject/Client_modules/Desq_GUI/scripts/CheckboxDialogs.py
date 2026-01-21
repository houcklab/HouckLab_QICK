from PyQt5.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox

class MultiCheckboxDialog(QDialog):
    """
    A generic dialog to allow the user to select multiple items from a list.
    """

    def __init__(self, items, dialog_name: str="Multi-selector", parent=None):
        """
        :param items: List of strings to display as checkboxes.
        :param parent: Parent QWidget.
        """
        super().__init__(parent)
        self.setWindowTitle(dialog_name)
        self.selected = []

        layout = QVBoxLayout()
        self.checkboxes = []

        for item in items:
            cb = QCheckBox(item)
            layout.addWidget(cb)
            self.checkboxes.append(cb)

        # OK / Cancel buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def accept(self):
        """
        Save all checked items before closing the dialog.
        """
        self.selected = [cb.text() for cb in self.checkboxes if cb.isChecked()]
        super().accept()

    def get_selected(self):
        """
        Returns a list of the selected items.
        """
        return self.selected

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QDialogButtonBox, QWidget
)


class DualMultiCheckboxDialog(QDialog):
    """
    A dialog with two columns of checkboxes: Global and Exp.
    Produces two separate selected lists.
    """

    def __init__(self, items, dialog_name: str = "Multi-selector", parent=None):
        super().__init__(parent)
        self.setWindowTitle(dialog_name)

        # To store selected items
        self.selected_global = []
        self.selected_exp = []

        # Main layout
        main_layout = QVBoxLayout(self)

        # Headers
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Global</b>"))
        header_layout.addWidget(QLabel("<b>Exp</b>"))
        main_layout.addLayout(header_layout)

        # Body layout for checkboxes
        self.global_checkboxes = []
        self.exp_checkboxes = []

        for item in items:
            row_layout = QHBoxLayout()

            cb_global = QCheckBox(item)
            cb_exp = QCheckBox(item)

            self.global_checkboxes.append(cb_global)
            self.exp_checkboxes.append(cb_exp)

            row_layout.addWidget(cb_global)
            row_layout.addWidget(cb_exp)
            main_layout.addLayout(row_layout)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def accept(self):
        """Save all checked items before closing the dialog."""
        self.selected_global = self._get_selected(self.global_checkboxes)
        self.selected_exp = self._get_selected(self.exp_checkboxes)
        super().accept()

    def _get_selected(self, checkbox_list):
        """Helper to extract checked checkbox labels."""
        return [cb.text() for cb in checkbox_list if cb.isChecked()]

    def get_selected(self):
        """Return two lists: selected Global items and selected Exp items."""
        return self.selected_global, self.selected_exp

