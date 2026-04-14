"""
=====================
ExperimentLoader.py
=====================

Helper functions for safely loading experiment files and discovering experiment classes.

This module provides utilities for dynamically importing Python experiment modules
and discovering classes that inherit from ``ExperimentClass``. It uses a custom
import mechanism that supports blocking specific imports (e.g., hardware proxies)
and ensures the custom matplotlib backend is installed before experiment imports.

Key Features
------------
- Safe module loading with configurable import blocking
- Automatic discovery of experiment classes via reflection
- Backend installation for matplotlib plot interception
- Thread-safe operation suitable for GUI applications

Backend Integration
-------------------
This module installs ``BackendDesq`` **before** importing experiment modules.
This is critical because matplotlib caches backends at import time. If an
experiment imports ``matplotlib.pyplot`` before our backend is set, it will
use whatever backend was active at that time (usually Agg), breaking plot
interception.

.. note::
    The backend installation happens transparently in :func:`load_module`.
    Callers don't need to manage backend state manually.

.. seealso::
    - :mod:`BackendDesq` for the custom matplotlib backend implementation
    - :mod:`ExperimentObject` for experiment class instantiation
    - :mod:`Helpers` for the underlying import mechanism

Module Attributes
-----------------
:var _BACKEND_MODULE: Full module path for the custom matplotlib backend.
:vartype _BACKEND_MODULE: str
"""

from __future__ import annotations

import inspect
import traceback
from types import ModuleType
from typing import Optional, Tuple, List

from PyQt5.QtCore import qCritical, qInfo

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers


#: Full module path for BackendDesq, used for matplotlib backend registration.
#: This path corresponds to the BackendDesq.py file in the scripts/ subfolder.
_BACKEND_MODULE: str = 'module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq'


def _ensure_backend_installed() -> bool:
    """
    Ensure the custom matplotlib backend is installed before experiment imports.

    This function is critical for plot interception to work correctly. Matplotlib
    caches backends at import time, so if an experiment module imports
    ``matplotlib.pyplot`` before our backend is set, it will use whatever backend
    was active at that time (typically Agg).

    By calling this function before importing experiment modules, we ensure that
    any ``matplotlib.pyplot`` import inside the experiment code will use our
    custom ``FigureCanvasDesq``, which intercepts all draw operations.

    The function uses two strategies:

    1. **Environment Variable** (preferred): If matplotlib hasn't been imported yet,
       sets ``MPLBACKEND`` environment variable so matplotlib uses our backend
       when it's first imported.

    2. **Force Switch**: If matplotlib is already imported, attempts to switch
       the backend using ``matplotlib.use(..., force=True)``.

    :returns: True if backend installation succeeded, False otherwise.
    :rtype: bool

    .. note::
        This function is called automatically by :func:`load_module`.
        Direct calls are typically unnecessary.

    .. warning::
        If matplotlib was imported with a different backend before this function
        runs, the force switch may fail in some edge cases. For best results,
        ensure this module is imported early in application startup.
    """
    import os
    import sys

    # Strategy 1: Set environment variable before matplotlib is imported
    if 'matplotlib' not in sys.modules:
        os.environ['MPLBACKEND'] = _BACKEND_MODULE
        print(f"[ExperimentLoader] Set MPLBACKEND before experiment import")
        return True

    # Strategy 2: Matplotlib already imported, try to switch backend
    import matplotlib
    current_backend = matplotlib.get_backend()

    # Case-insensitive comparison to handle various backend name formats
    if 'backenddesq' in current_backend.lower():
        print(f"[ExperimentLoader] Backend already installed: {current_backend}")
        return True  # Already using our custom backend

    try:
        matplotlib.use(_BACKEND_MODULE, force=True)
        print(f"[ExperimentLoader] Switched matplotlib backend from {current_backend} to BackendDesq")
        return True
    except Exception as e:
        qCritical(f"Could not install BackendDesq: {e}. Plot interception may not work.")
        print(f"[ExperimentLoader] ERROR: Could not install BackendDesq: {e}")
        return False


def load_module(
    path: str,
    banned_imports: Optional[List[str]] = None
) -> Tuple[Optional[ModuleType], Optional[str]]:
    """
    Load a Python module from a file path, blocking specified imports if needed.

    This function safely imports a Python file as a module, with support for
    blocking problematic imports (e.g., hardware proxy modules that would fail
    in testing environments). It also ensures the custom matplotlib backend
    is installed before import.

    :param path: Absolute path to the Python file to import.
    :type path: str
    :param banned_imports: List of module names to block during import.
        Defaults to ``["socProxy"]`` if None.
    :type banned_imports: list[str] | None

    :returns: Tuple of (module object, module name) on success,
        or (None, None) on failure.
    :rtype: tuple[ModuleType | None, str | None]

    :raises: Logs errors via qCritical but does not raise exceptions.

    .. note::
        The custom matplotlib backend is installed **before** the module import.
        This is essential for plot interception to work correctly.

    .. seealso::
        :func:`Helpers.import_file` for the underlying import mechanism.

    Example
    -------
    ::

        module, name = load_module("/path/to/experiment.py")
        if module is not None:
            # Module loaded successfully
            experiment_class = getattr(module, "MyExperiment")
    """
    # CRITICAL: Install custom backend before experiment import to ensure
    # all matplotlib usage in experiment code uses our custom canvas for
    # intercepting draw() calls and routing figures to the GUI
    _ensure_backend_installed()

    try:
        mod, name = Helpers.import_file(str(path), banned_imports=banned_imports or ["socProxy"])
        return mod, name
    except Exception as e:
        qCritical(f"Failed to load module {path}: {e}")
        qCritical(traceback.format_exc())
        return None, None


def find_experiment_classes(module: Optional[ModuleType]) -> List[Tuple[str, type]]:
    """
    Find all experiment classes inside a loaded module.

    A valid experiment class is any class whose base class hierarchy includes
    a class named ``ExperimentClass``. String matching on class names is used
    because different files may define different versions of ``ExperimentClass``
    (i.e., the class identity may differ even if the name matches).

    :param module: The Python module object to search, or None.
    :type module: ModuleType | None

    :returns: List of (class_name, class_object) tuples for all discovered
        experiment classes. Returns empty list if module is None.
    :rtype: list[tuple[str, type]]

    .. note::
        Only classes **defined** in the given module are considered.
        Imported classes from other modules are excluded to avoid
        false positives from base class imports.

    Example
    -------
    ::

        module, _ = load_module("/path/to/experiments.py")
        classes = find_experiment_classes(module)
        for name, cls in classes:
            print(f"Found experiment: {name}")
    """
    if module is None:
        return []

    experiment_classes: List[Tuple[str, type]] = []

    for name, obj in inspect.getmembers(module, inspect.isclass):
        # Skip classes that are imported from other modules (not defined here)
        if obj.__module__ != module.__name__:
            continue

        # Check if any base class (excluding the class itself) is named "ExperimentClass"
        # Using string matching instead of issubclass() to handle multiple
        # ExperimentClass definitions across different module versions
        if any(base.__name__ in {"ExperimentClass"} for base in obj.__mro__[1:]):
            qInfo(f"Discovered experiment class: {name}")
            experiment_classes.append((name, obj))

    return experiment_classes


def load_and_find(
    path: str,
    banned_imports: Optional[List[str]] = None
) -> Tuple[Optional[str], List[Tuple[str, type]]]:
    """
    Load a module and find experiment classes in one step.

    This is a convenience wrapper that combines :func:`load_module` and
    :func:`find_experiment_classes` into a single call.

    :param path: Absolute path to the experiment file.
    :type path: str
    :param banned_imports: Imports to block during loading.
        Defaults to ``["socProxy"]`` if None.
    :type banned_imports: list[str] | None

    :returns: Tuple of (module_name, list of (class_name, class_object) tuples).
        Returns (None, []) if module loading fails.
    :rtype: tuple[str | None, list[tuple[str, type]]]

    Example
    -------
    ::

        module_name, experiments = load_and_find("/path/to/my_experiments.py")
        if module_name:
            for exp_name, exp_class in experiments:
                print(f"Found {exp_name} in {module_name}")
    """
    module, module_name = load_module(path, banned_imports=banned_imports)
    if module is None:
        return None, []
    return module_name, find_experiment_classes(module)