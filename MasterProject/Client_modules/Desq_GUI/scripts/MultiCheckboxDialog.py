from PyQt5.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox

class MultiCheckboxDialog(QDialog):
    """
    A generic dialog to allow the user to select multiple items from a list.
    """

    def __init__(self, items, parent=None):
        """
        :param items: List of strings to display as checkboxes.
        :param parent: Parent QWidget.
        """
        super().__init__(parent)
        self.setWindowTitle("Select Experiment Classes")
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
