"""
=================
SettingsWindow.py
=================
A popout window that holds all the appearance settings for the main window.
"""
import os
import json
from PyQt5.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QLabel,
    QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

import MasterProject.Client_modules.Quarky_GUI.scripts.Helpers as Helpers


class SettingsWindow(QWidget):
    """
    A popout settings window containing options for theme selection, font size,
    and action buttons for apply, save, and reset. Overrides closeEvent to allow
    custom logic when the window is closed.
    """

    default_theme = "Light Mode"
    default_font_size = 13

    update_settings = pyqtSignal(str, int)
    """
    The signal sent back to the main application to apply the current settings.
    
    :param theme: The theme to update to.
    :type theme: str
    :param font_size: The font size to update to.
    :type font_size: int
    """

    def __init__(self):
        super().__init__()

        # Set window properties
        self.setWindowTitle("Settings")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setFixedSize(300, 175)
        self.setObjectName("SettingsWindow")

        # Main vertical layout
        main_layout = QVBoxLayout(self)

        # Form layout for settings
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(10, 10, 10, 0)
        self.form_layout.setSpacing(8)

        # Theme mode selection dropdown
        self.theme_selector = QComboBox()
        self.theme_selector.addItems(["Light Mode", "(Dark Coming Soon)"])
        self.form_layout.addRow("Theme Mode", self.theme_selector)

        # Font size input
        self.font_size_input = QLineEdit()
        self.font_size_input.setPlaceholderText("(Default 13)")
        self.form_layout.addRow("Font Size", self.font_size_input)

        main_layout.addLayout(self.form_layout)

        # Button layout
        button_layout = QHBoxLayout()

        self.reset_button = Helpers.create_button("Reset", "reset_button", True)
        self.save_button = Helpers.create_button("Save", "save_button", True)
        self.apply_button = Helpers.create_button("Apply", "apply_button", True)

        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.apply_button)

        main_layout.addLayout(button_layout)

        self.setup_signals()

    def setup_signals(self):
        """
        Setting up signals (mostly directory stuff).
        """

        # This generates the path to the settings
        self.root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.settings_dir = os.path.join(self.root_dir, 'LocalStorage')
        self.settings_path = os.path.join(self.settings_dir, 'settings.json')

        # Check if settings directory exists, create if not
        if not os.path.exists(self.settings_dir):
            os.makedirs(self.settings_dir)

        # Check if settings.json exists, create with defaults if not
        if not os.path.isfile(self.settings_path):
            default_settings = {
                "theme": self.default_theme,
                "font_size": self.default_font_size,
            }
            self.curr_theme = self.default_theme
            self.curr_font_size = self.default_font_size
            with open(self.settings_path, 'w') as f:
                json.dump(default_settings, f, indent=4)

        self.save_button.clicked.connect(self.save_settings)
        self.reset_button.clicked.connect(self.reset_settings)
        self.apply_button.clicked.connect(self.apply_settings)

        self.load_settings()

    def load_settings(self):
        """
        Load settings from the settings.json file into the form.
        """
        try:
            with open(self.settings_path, 'r') as f:
                settings = json.load(f)
                self.theme_selector.setCurrentText(settings["theme"])
                self.font_size_input.setText(str(settings["font_size"]))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load settings: {e}")

    def reset_settings(self):
        """
        Reset the settings to the default values.
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

        self.load_settings()

    def save_settings(self):
        """
        Save the form input to the settings.json file.
        """
        theme = self.theme_selector.currentText()
        font_size = self.font_size_input.text().strip()
        if not font_size.isdigit() or int(font_size) < 8 or int(font_size) > 32:
            QMessageBox.critical(self, "Error", "Font size must be a number between 8 and 32.")
            return

        settings = {
            "theme": theme,
            "font_size": font_size
        }
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f, indent=4)

            self.save_button.setText('Saved!')
            QTimer.singleShot(2000, lambda: self.save_button.setText('Save'))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    def apply_settings(self):
        """
        Apply the new settings by sending a signal to the main application.
        """
        theme = self.theme_selector.currentText()
        font_size = self.font_size_input.text().strip()
        if not font_size.isdigit() or int(font_size) < 8 or int(font_size) > 32:
            QMessageBox.critical(self, "Error", "Font size must be a number between 8 and 32.")
            return
        self.curr_theme = theme
        self.curr_font_size = font_size

        self.update_settings.emit(theme, int(font_size))

    def closeEvent(self, event):
        """
        Custom logic when the window is closed.
        """
        #print("window close")
        super().closeEvent(event)
