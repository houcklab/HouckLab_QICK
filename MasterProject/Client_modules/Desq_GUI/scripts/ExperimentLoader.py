"""
=====================
ExperimentLoader.py
=====================

Helper functions for safely loading experiment files and discovering all experiment classes
they define. Uses the same custom import mechanism as ExperimentObject, including support
for blocking specific imports.

CHANGES FOR BACKEND-BASED PLOT INTERCEPTION:
--------------------------------------------
- Installs BackendDesq BEFORE importing experiment modules
- This ensures all matplotlib usage in experiment code uses our custom canvas
- The custom canvas intercepts draw() calls and routes figures to the GUI

Functions:
    load_module(path, banned_imports=None) -> (module, name)
        Safely imports a Python module as a module.

    find_experiment_classes(module) -> list[(str, type)]
        Returns all classes in the module that inherit from ExperimentClass or ExperimentClassPlus,
        identified by base class name (string match, not issubclass).
"""

import inspect
import traceback
from PyQt5.QtCore import qCritical, qInfo

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers

# Full module path since BackendDesq.py is in scripts/ subfolder
_BACKEND_MODULE = 'module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq'


def _ensure_backend_installed():
    """
    Ensure the custom matplotlib backend is installed BEFORE experiment imports.

    WHY THIS IS IMPORTANT:
    ----------------------
    Matplotlib caches backends at import time. If an experiment module imports
    matplotlib.pyplot before our backend is set, it will use whatever backend
    was active at that time (probably Agg).

    By installing our backend here, BEFORE importing experiment modules, we ensure
    that any matplotlib.pyplot import inside the experiment code will use our
    custom FigureCanvasDesq, which intercepts all draw operations.

    This is the key to making plot interception work without monkey-patching.
    """
    import os
    import sys

    # Method 1: If matplotlib not yet imported, set environment variable
    if 'matplotlib' not in sys.modules:
        os.environ['MPLBACKEND'] = _BACKEND_MODULE
        print(f"[ExperimentLoader] Set MPLBACKEND before experiment import")
        return True

    # Method 2: If matplotlib already imported, try to switch backend
    import matplotlib
    current_backend = matplotlib.get_backend()

    # FIXED: Use lowercase on both sides for case-insensitive comparison
    if 'backenddesq' in current_backend.lower():
        print(f"[ExperimentLoader] Backend already installed: {current_backend}")
        return True  # Already using our backend

    try:
        matplotlib.use(_BACKEND_MODULE, force=True)
        print(f"[ExperimentLoader] Switched matplotlib backend from {current_backend} to BackendDesq")
        return True
    except Exception as e:
        qCritical(f"Could not install BackendDesq: {e}. Plot interception may not work.")
        print(f"[ExperimentLoader] ERROR: Could not install BackendDesq: {e}")
        return False


def load_module(path, banned_imports=None):
    """
    Loads a Python module from a file path, blocking specified imports if needed.

    CHANGES:
    --------
    - Calls _ensure_backend_installed() BEFORE importing to ensure experiments
      use our custom matplotlib canvas.

    :param path: The absolute path to the file.
    :type path: str
    :param banned_imports: A list of module names to block.
    :type banned_imports: list[str] | None
    :return: (module, module_name)
    :rtype: tuple
    """
    # =================================================================
    # NEW: Ensure custom backend is installed before experiment import
    # This is critical for plot interception to work!
    # =================================================================
    _ensure_backend_installed()

    try:
        mod, name = Helpers.import_file(str(path), banned_imports=banned_imports or ["socProxy"])
        return mod, name
    except Exception as e:
        qCritical(f"Failed to load module {path}: {e}")
        qCritical(traceback.format_exc())
        return None, None


def find_experiment_classes(module):
    """
    Finds all experiment classes inside a loaded module.

    A valid experiment class is any class whose base class has a name of
    'ExperimentClass' or 'ExperimentClassPlus'. String matching is used because
    different files may define different versions of ExperimentClass.

    :param module: The Python module object.
    :type module: module
    :return: A list of (class_name, class_object) tuples.
    :rtype: list[tuple[str, type]]
    """
    if module is None:
        return []

    experiment_classes = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        # Exclude classes that are defined outside this module
        if obj.__module__ != module.__name__:
            continue

        if any(base.__name__ in {"ExperimentClass", "ExperimentClassPlus"} for base in obj.__mro__[1:]):
            qInfo(f"Discovered experiment class: {name}")
            experiment_classes.append((name, obj))

    return experiment_classes


def load_and_find(path, banned_imports=None):
    """
    Convenience wrapper that loads a module and finds experiment classes in one step.

    :param path: The absolute path to the experiment file.
    :type path: str
    :param banned_imports: Imports to block during loading.
    :type banned_imports: list[str] | None
    :return: (module_name, [(class_name, class_object), ...])
    :rtype: tuple[str, list[tuple[str, type]]]
    """
    module, module_name = load_module(path, banned_imports=banned_imports)
    if module is None:
        return None, []
    return module_name, find_experiment_classes(module)