"""
=================
SettingsWindow.py
=================

A popout window that holds all the appearance settings for the main window.

This module provides a settings dialog for the Desq GUI application, allowing
users to customize theme and font size preferences. Settings are persisted
to a JSON file in the LocalStorage directory.

.. note::
    Dark mode theme is listed but not yet implemented (marked as "Coming Soon").

.. seealso::
    :mod:`Helpers` for the ``create_button`` utility function used here.
"""

from __future__ import annotations

import os
import json
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers


class SettingsWindow(QWidget):
    """
    A popout settings window for configuring application appearance.

    This window provides controls for theme selection and font size configuration.
    Settings can be applied immediately, saved to persistent storage, or reset
    to defaults. The window overrides closeEvent to allow custom logic when closed.

    :ivar default_theme: The default theme name.
    :vartype default_theme: str
    :ivar default_font_size: The default font size in points.
    :vartype default_font_size: int
    :ivar theme_selector: Dropdown for selecting the application theme.
    :vartype theme_selector: QComboBox
    :ivar font_size_input: Input field for specifying font size.
    :vartype font_size_input: QLineEdit
    :ivar reset_button: Button to reset settings to defaults.
    :vartype reset_button: QPushButton
    :ivar save_button: Button to save current settings to file.
    :vartype save_button: QPushButton
    :ivar apply_button: Button to apply settings without saving.
    :vartype apply_button: QPushButton
    :ivar root_dir: Root directory of the application (parent of script directory).
    :vartype root_dir: str
    :ivar settings_dir: Directory path where settings file is stored.
    :vartype settings_dir: str
    :ivar settings_path: Full path to the settings.json file.
    :vartype settings_path: str
    :ivar curr_theme: Currently applied theme name.
    :vartype curr_theme: str
    :ivar curr_font_size: Currently applied font size.
    :vartype curr_font_size: int

    .. note::
        The ``curr_theme`` and ``curr_font_size`` instance variables are only
        initialized when the settings file doesn't exist (in ``setup_signals``)
        or when ``apply_settings`` is called. This could lead to AttributeError
        if accessed before either occurs.
    """

    default_theme: str = "Light Mode"
    default_font_size: int = 13

    #: Signal emitted when settings should be applied to the main application.
    #: Carries the theme name (str) and font size (int).
    update_settings = pyqtSignal(str, int)

    def __init__(self) -> None:
        """
        Initialize the SettingsWindow.

        Creates the window with theme selector, font size input, and action buttons.
        The window is set to a fixed size of 300x175 pixels.
        """
        super().__init__()

        # Configure window properties
        self.setWindowTitle("Settings")
        # Window has close button only, no minimize/maximize
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setFixedSize(300, 175)
        self.setObjectName("SettingsWindow")

        # Main vertical layout container
        main_layout = QVBoxLayout(self)

        # Form layout for labeled input fields
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(10, 10, 10, 0)
        self.form_layout.setSpacing(8)

        # Theme mode selection dropdown
        # NOTE: Dark mode is listed but not implemented yet
        self.theme_selector = QComboBox()
        self.theme_selector.addItems(["Light Mode", "(Dark Coming Soon)"])
        self.form_layout.addRow("Theme Mode", self.theme_selector)

        # Font size input with placeholder showing default value
        self.font_size_input = QLineEdit()
        self.font_size_input.setPlaceholderText("(Default 13)")
        self.form_layout.addRow("Font Size", self.font_size_input)

        main_layout.addLayout(self.form_layout)

        # Horizontal layout for action buttons
        button_layout = QHBoxLayout()

        self.reset_button = Helpers.create_button("Reset", "reset_button", True)
        self.save_button = Helpers.create_button("Save", "save_button", True)
        self.apply_button = Helpers.create_button("Apply", "apply_button", True)

        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.apply_button)

        main_layout.addLayout(button_layout)

        self.setup_signals()

    def setup_signals(self) -> None:
        """
        Initialize signal connections and settings file paths.

        This method:
        1. Determines the settings directory path (LocalStorage in parent directory)
        2. Creates the settings directory if it doesn't exist
        3. Creates a default settings.json if it doesn't exist
        4. Connects button click signals to their handler methods
        5. Loads existing settings into the form

        .. note::
            The settings directory is located relative to this file's location,
            specifically at ``../../LocalStorage/settings.json`` from the script.

        :raises OSError: If directory creation fails (from os.makedirs).
        :raises IOError: If settings file cannot be written (from json.dump).
        """
        # Generate the path to the settings directory
        # Goes up two directory levels from this file to find the root
        self.root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.settings_dir = os.path.join(self.root_dir, 'LocalStorage')
        self.settings_path = os.path.join(self.settings_dir, 'settings.json')

        # Ensure settings directory exists
        if not os.path.exists(self.settings_dir):
            os.makedirs(self.settings_dir)

        # Create default settings file if it doesn't exist
        if not os.path.isfile(self.settings_path):
            default_settings = {
                "theme": self.default_theme,
                "font_size": self.default_font_size,
            }
            # Initialize current values to defaults
            self.curr_theme = self.default_theme
            self.curr_font_size = self.default_font_size
            with open(self.settings_path, 'w') as f:
                json.dump(default_settings, f, indent=4)

        # Connect button signals to handlers
        self.save_button.clicked.connect(self.save_settings)
        self.reset_button.clicked.connect(self.reset_settings)
        self.apply_button.clicked.connect(self.apply_settings)

        # Load saved settings into the form
        self.load_settings()

    def load_settings(self) -> None:
        """
        Load settings from the settings.json file into the form widgets.

        Reads the theme and font_size values from the JSON file and updates
        the corresponding UI elements (theme_selector and font_size_input).

        :raises Exception: If file reading or JSON parsing fails, displays
            an error dialog to the user.

        .. note::
            This method assumes the settings file exists and contains valid JSON
            with "theme" and "font_size" keys. Missing keys will raise KeyError.
        """
        try:
            with open(self.settings_path, 'r') as f:
                settings = json.load(f)
                self.theme_selector.setCurrentText(settings["theme"])
                self.font_size_input.setText(str(settings["font_size"]))
                # Initialize current values from loaded settings
                self.curr_theme = settings["theme"]
                self.curr_font_size = int(settings["font_size"])

        except Exception as e:
            # Fallback to defaults if loading fails
            self.curr_theme = self.default_theme
            self.curr_font_size = self.default_font_size
            QMessageBox.critical(self, "Error", f"Failed to load settings: {e}")

    def reset_settings(self) -> None:
        """
        Reset all settings to their default values.

        Overwrites the settings.json file with default values and reloads
        the form to reflect the changes.

        :raises Exception: If file writing fails, displays an error dialog
            to the user but still attempts to reload settings.
        """
        try:
            default_settings = {
                "theme": self.default_theme,
                "font_size": self.default_font_size,
            }
            with open(self.settings_path, 'w') as f:
                json.dump(default_settings, f, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reset settings: {e}")

        # Reload form even if save failed (will show previous values)
        self.load_settings()

    def save_settings(self) -> None:
        """
        Validate and save the current form values to settings.json.

        Performs validation on font_size (must be integer between 8 and 32)
        before saving. On successful save, temporarily changes the save button
        text to "Saved!" for 2 seconds as visual feedback.

        :raises Exception: If file writing fails, displays an error dialog.
        """
        theme = self.theme_selector.currentText()
        font_size = self.font_size_input.text().strip()

        # Validate font size: must be numeric and within acceptable range
        if not font_size.isdigit() or int(font_size) < 8 or int(font_size) > 32:
            QMessageBox.critical(self, "Error", "Font size must be a number between 8 and 32.")
            return

        settings = {
            "theme": theme,
            "font_size": int(font_size)
        }
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f, indent=4)

            # Provide visual feedback that save succeeded
            self.save_button.setText('Saved!')
            QTimer.singleShot(2000, lambda: self.save_button.setText('Save'))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    def apply_settings(self) -> None:
        """
        Validate form values and emit update signal to apply settings.

        Validates the font_size (must be integer between 8 and 32), updates
        internal state variables, and emits the ``update_settings`` signal
        to notify the main application of the new settings.

        .. note::
            This method applies settings immediately without saving them to
            the settings.json file. Use ``save_settings`` to persist changes.
        """
        theme = self.theme_selector.currentText()
        font_size = self.font_size_input.text().strip()

        # Validate font size before applying
        if not font_size.isdigit() or int(font_size) < 8 or int(font_size) > 32:
            QMessageBox.critical(self, "Error", "Font size must be a number between 8 and 32.")
            return

        # Update internal state
        self.curr_theme = theme
        self.curr_font_size = font_size

        # Notify main application of new settings
        self.update_settings.emit(theme, int(font_size))

    def closeEvent(self, event) -> None:
        """
        Handle the window close event.

        This override allows for custom logic when the settings window is closed.
        Currently just calls the parent implementation.

        :param event: The close event object.
        :type event: QCloseEvent

        .. note::
            Contains commented debug print statement. The method currently
            doesn't add any functionality beyond the parent class.
        """
        # Debug: print("settings window close")
        super().closeEvent(event)