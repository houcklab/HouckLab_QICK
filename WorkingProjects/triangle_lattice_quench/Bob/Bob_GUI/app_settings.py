"""Where the GUI remembers things (last calibration file, station, window size).

Normally the platform's usual place (macOS preferences, Windows registry, ~/.config).
Set BOB_SETTINGS_FILE to a path to use that .ini file instead. The test suite does this so
it never reads or writes a user's settings.
"""
import os

from PyQt5.QtCore import QSettings

ENV_VAR = "BOB_SETTINGS_FILE"


def app_settings() -> QSettings:
    path = os.environ.get(ENV_VAR)
    if path:
        return QSettings(path, QSettings.IniFormat)
    return QSettings("HouckLab", "Bob")
