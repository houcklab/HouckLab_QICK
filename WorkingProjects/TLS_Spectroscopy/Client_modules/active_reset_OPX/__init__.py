"""Isolated OPX-style active reset development package.

Nothing in the production experiment stack imports this package.  Use
``benchmark_q3.py`` directly while the implementation is under validation.
"""

from .classifier import ClassifierCalibration, Zone, classify, fit_classifier
from .config import OPXResetConfig
from .records import ShotRecord, TerminalStatus

__all__ = [
    "ClassifierCalibration",
    "OPXResetConfig",
    "ShotRecord",
    "TerminalStatus",
    "Zone",
    "classify",
    "fit_classifier",
]
