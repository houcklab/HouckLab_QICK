"""
=====================
ExperimentLoader.py
=====================

Helper functions for safely loading experiment files and discovering all experiment classes
they define. Uses the same custom import mechanism as ExperimentObject, including support
for blocking specific imports.

Functions:
    load_module(path, banned_imports=None) -> (module, name)
        Safely imports a Python file as a module.

    find_experiment_classes(module) -> list[(str, type)]
        Returns all classes in the module that inherit from ExperimentClass or ExperimentClassPlus,
        identified by base class name (string match, not issubclass).
"""

import inspect
import traceback
from PyQt5.QtCore import qCritical, qInfo

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers


def load_module(path, banned_imports=None):
    """
    Loads a Python module from a file path, blocking specified imports if needed.

    :param path: The absolute path to the file.
    :type path: str
    :param banned_imports: A list of module names to block.
    :type banned_imports: list[str] | None
    :return: (module, module_name)
    :rtype: tuple
    """
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
