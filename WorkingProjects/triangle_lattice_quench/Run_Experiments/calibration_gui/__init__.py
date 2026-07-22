"""Calibration GUI package.

This was a single ``calibration_gui.py`` module; it is being split into a package
(``main_window`` + shared modules + one module per tab) for readability and easier
modification. The public surface that other code relies on is re-exported here so
nothing that did ``import ...Run_Experiments.calibration_gui`` has to change:

  * ``AutoCalibWorker`` -- imported (lazily) by ``agent_chat_tab``.
  * ``MainWindow`` / ``CalibState`` / ``main`` -- GUI entry points.

Launch is unchanged: ``python -m ...Run_Experiments.calibration_gui`` runs
``__main__.py`` -> ``main()``.
"""
from .state import CalibState
from .tabs.auto_calib import AutoCalibWorker
from .main_window import MainWindow, main

__all__ = ["MainWindow", "CalibState", "AutoCalibWorker", "main"]
