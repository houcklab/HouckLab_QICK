"""
==================
CheckboxDialogs.py
==================

Dialog widgets for multi-selection checkbox interfaces.

This module provides PyQt5 dialog classes for selecting multiple items
from a list using checkboxes. Two variants are available:

- :class:`MultiCheckboxDialog`: Single column of checkboxes
- :class:`DualMultiCheckboxDialog`: Two columns (Global/Exp) for dual selection

:var MultiCheckboxDialog: Dialog for single-column checkbox selection.
:var DualMultiCheckboxDialog: Dialog for dual-column checkbox selection.

.. note::
    These dialogs are modal and block until the user clicks OK or Cancel.
    Use :meth:`exec_` to show the dialog and wait for user input.
"""

from typing import List, Optional, Tuple

from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class MultiCheckboxDialog(QDialog):
    """
    A generic dialog to allow the user to select multiple items from a list.

    Displays a vertical list of checkboxes, one for each item, with OK/Cancel
    buttons at the bottom. Selected items can be retrieved after the dialog
    is accepted.

    :ivar selected: List of selected item strings after dialog is accepted.
    :vartype selected: List[str]
    :ivar checkboxes: List of QCheckBox widgets created for each item.
    :vartype checkboxes: List[QCheckBox]

    Example usage::

        dialog = MultiCheckboxDialog(["Item 1", "Item 2", "Item 3"])
        if dialog.exec_() == QDialog.Accepted:
            selected = dialog.get_selected()
            print(f"User selected: {selected}")

    .. seealso::
        :class:`DualMultiCheckboxDialog` for a two-column variant.
    """

    def __init__(
        self,
        items: List[str],
        dialog_name: str = "Multi-selector",
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize the multi-checkbox dialog.

        :param items: List of strings to display as checkboxes.
        :type items: List[str]
        :param dialog_name: Title for the dialog window.
        :type dialog_name: str
        :param parent: Parent QWidget for the dialog.
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)
        self.setWindowTitle(dialog_name)

        # Storage for selected items (populated on accept)
        self.selected: List[str] = []

        layout = QVBoxLayout()

        # List of checkbox widgets for later access
        self.checkboxes: List[QCheckBox] = []

        # Create a checkbox for each item in the provided list
        for item in items:
            cb = QCheckBox(item)
            layout.addWidget(cb)
            self.checkboxes.append(cb)

        # OK / Cancel buttons using standard QDialogButtonBox
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def accept(self) -> None:
        """
        Save all checked items before closing the dialog.

        Collects the text of all checked checkboxes into :attr:`selected`
        before calling the parent accept method to close the dialog.

        :returns: None
        :rtype: None
        """
        # Extract text from all checked checkboxes
        self.selected = [cb.text() for cb in self.checkboxes if cb.isChecked()]
        super().accept()

    def get_selected(self) -> List[str]:
        """
        Returns a list of the selected items.

        :returns: List of strings corresponding to checked checkbox labels.
        :rtype: List[str]

        .. note::
            This method should be called after the dialog is accepted.
            If called before :meth:`accept`, returns an empty list.
        """
        return self.selected


class DualMultiCheckboxDialog(QDialog):
    """
    A dialog with two columns of checkboxes: Global and Exp.

    Produces two separate selected lists, allowing users to independently
    select items for "Global" and "Exp" categories. Each item appears
    as two checkboxes side-by-side, one in each column.

    :ivar selected_global: List of items selected in the Global column.
    :vartype selected_global: List[str]
    :ivar selected_exp: List of items selected in the Exp column.
    :vartype selected_exp: List[str]
    :ivar global_checkboxes: List of QCheckBox widgets in the Global column.
    :vartype global_checkboxes: List[QCheckBox]
    :ivar exp_checkboxes: List of QCheckBox widgets in the Exp column.
    :vartype exp_checkboxes: List[QCheckBox]

    Example usage::

        dialog = DualMultiCheckboxDialog(["Param A", "Param B", "Param C"])
        if dialog.exec_() == QDialog.Accepted:
            global_items, exp_items = dialog.get_selected()
            print(f"Global: {global_items}, Exp: {exp_items}")

    .. seealso::
        :class:`MultiCheckboxDialog` for a single-column variant.
    """

    def __init__(
        self,
        items: List[str],
        dialog_name: str = "Multi-selector",
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize the dual multi-checkbox dialog.

        :param items: List of strings to display as checkboxes in both columns.
        :type items: List[str]
        :param dialog_name: Title for the dialog window.
        :type dialog_name: str
        :param parent: Parent QWidget for the dialog.
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)
        self.setWindowTitle(dialog_name)

        # Storage for selected items in each column (populated on accept)
        self.selected_global: List[str] = []
        self.selected_exp: List[str] = []

        # Main layout for the dialog
        main_layout = QVBoxLayout(self)

        # Column headers with bold text
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Global</b>"))
        header_layout.addWidget(QLabel("<b>Exp</b>"))
        main_layout.addLayout(header_layout)

        # Lists of checkbox widgets for each column
        self.global_checkboxes: List[QCheckBox] = []
        self.exp_checkboxes: List[QCheckBox] = []

        # Create a row of two checkboxes for each item
        for item in items:
            row_layout = QHBoxLayout()

            # Create checkbox for Global column
            cb_global = QCheckBox(item)
            # Create checkbox for Exp column
            cb_exp = QCheckBox(item)

            self.global_checkboxes.append(cb_global)
            self.exp_checkboxes.append(cb_exp)

            row_layout.addWidget(cb_global)
            row_layout.addWidget(cb_exp)
            main_layout.addLayout(row_layout)

        # OK / Cancel buttons using standard QDialogButtonBox
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def accept(self) -> None:
        """
        Save all checked items before closing the dialog.

        Collects checked items from both columns into their respective
        :attr:`selected_global` and :attr:`selected_exp` lists.

        :returns: None
        :rtype: None
        """
        self.selected_global = self._get_selected(self.global_checkboxes)
        self.selected_exp = self._get_selected(self.exp_checkboxes)
        super().accept()

    def _get_selected(self, checkbox_list: List[QCheckBox]) -> List[str]:
        """
        Helper to extract checked checkbox labels from a list.

        :param checkbox_list: List of QCheckBox widgets to check.
        :type checkbox_list: List[QCheckBox]
        :returns: List of text labels from checked checkboxes.
        :rtype: List[str]
        """
        return [cb.text() for cb in checkbox_list if cb.isChecked()]

    def get_selected(self) -> Tuple[List[str], List[str]]:
        """
        Return two lists: selected Global items and selected Exp items.

        :returns: A tuple of (global_selections, exp_selections).
        :rtype: Tuple[List[str], List[str]]

        .. note::
            This method should be called after the dialog is accepted.
            If called before :meth:`accept`, returns two empty lists.
        """
        return self.selected_global, self.selected_exp