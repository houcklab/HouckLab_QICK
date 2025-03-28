"""
==========
Helpers.py
==========
Module containing all helper functions for the Quarky GUI.
"""

import os
import numpy as np
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

def simple_h5_to_dict(h5file):
    """
    The simple direct conversion a h5 file to a dictionary that assums all key values are arrays.

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

def dict_to_h5(data_file, dictionary):
    """
    Recursively stores a dictionary into an HDF5 group.
    Handles nested dictionaries, lists, strings, and numerical data.

    :param data_file: A writeable reference to an h5 file
    :type data_file: h5py.File
    :param dictionary: The dictionary to convert into h5
    :type dictionary: dict
    """

    for key, datum in dictionary.items():
        if isinstance(datum, dict):
            # Create a subgroup for nested dictionaries
            subgroup = data_file.create_group(key)
            dict_to_h5(subgroup, datum)  # Recurse
        else:
            if isinstance(datum, list):
                # Handle list of numbers or strings
                if all(isinstance(v, (int, float, np.number)) for v in datum):
                    datum = np.array(datum, dtype=np.float64)  # Convert to NumPy array
                    data_file.create_dataset(key, data=datum)
                elif all(isinstance(v, str) for v in datum):
                    dt = h5py.special_dtype(vlen=str)  # Variable-length string dtype
                    data_file.create_dataset(key, data=np.array(datum, dtype=dt))
                else:
                    raise ValueError(f"Unsupported list type in key '{key}': Mixed types are not supported.")

            elif isinstance(datum, (int, float, np.ndarray)):
                data_file.create_dataset(key, data=np.array(datum, dtype=np.float64))

            elif isinstance(datum, str):
                dt = h5py.special_dtype(vlen=str)  # Variable-length string dtype
                data_file.create_dataset(key, data=np.array(datum, dtype=dt))

            print(key, datum)
            data_file[key][...] = datum

def h5_to_dict(h5file):
    """
    Recursively converts an HDF5 group back into a dictionary.
    Restores nested dictionaries, lists, and numerical/text data.
    """
    with h5py.File(h5file, "r") as f:
        print(f.items()[0])
        result = {}

        for key, item in f.items():
            if isinstance(item, h5py.Group):
                result[key] = h5_to_dict(item)  # Recurse

            elif isinstance(item, h5py.Dataset):
                data = item[()]
                if isinstance(data, np.ndarray):
                    data = data.tolist()  # Convert NumPy arrays back to lists
                elif isinstance(data, bytes):
                    data = data.decode('utf-8')  # Convert bytes to string
                result[key] = data

        return result