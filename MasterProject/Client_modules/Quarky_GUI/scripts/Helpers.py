"""
==========
Helpers.py
==========
Module containing all helper functions for the Quarky GUI.
"""

import os
import importlib
import h5py
from PyQt5.QtWidgets import (
    QPushButton,
)

def import_file(full_path_to_module):
    """
    Imports a python file to load it as a module (meaning an iterable list of classes and callables).

    :param full_path_to_module: Full path to the python file
    :type full_path_to_module: str
    :returns: A tuple containing the imported module object and its name.
    :rtype: tuple[ModuleType, str]
    """

    # attempts a module loading via the full path given
    try:
        module_dir, module_file = os.path.split(full_path_to_module)
        module_name, module_ext = os.path.splitext(module_file)
        loader = importlib.machinery.SourceFileLoader(module_name, full_path_to_module)
        module_obj = loader.load_module()
        module_obj.__file__ = full_path_to_module
        globals()[module_name] = module_obj
    except Exception as e:
        raise ImportError(e)
    return module_obj, module_name

def h5_to_dict(h5file):
    """
    Converts a h5 file to a dictionary.

    :param h5file: h5 file
    :type h5file: h5py.File
    :return: A dictionary containing the h5 file's data.
    :rtype: dict
    """
    with h5py.File(h5file, "r") as f:
        data_dict = {}
        for key in f.keys():
            data_dict[key] = f[key][()]  # Load dataset into memory
        return data_dict

def create_button(text, name, enabled=True, parent=None):
    """
    Creates a QPushButton.

    :param text: The text of the button.
    :type text: str
    :param name: The name of the button object.
    :type name: str
    :param enabled: Whether the button is enabled.
    :type enabled: bool
    :param parent: The parent widget.
    :type parent: QWidget
    :return: The created button.
    :rtype: QPushButton
    """

    btn = QPushButton(text, parent)
    btn.setObjectName(name)
    btn.setEnabled(enabled)
    return btn