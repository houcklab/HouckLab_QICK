"""
==========
Helpers.py
==========
Module containing all helper functions for the Desq GUI.
"""

import os
import json
import ast
import time
from datetime import datetime, timedelta
import numpy as np
import importlib
import h5py
from PyQt5.QtWidgets import (
    QPushButton, QGraphicsDropShadowEffect, QFileDialog
)
from PyQt5.QtCore import qWarning, QSettings
from PyQt5.QtGui import QColor

import importlib.machinery
import sys
from types import ModuleType, SimpleNamespace

def import_file(full_path_to_module, banned_imports=None):
    """
    Securely imports a Python file with static and runtime protection against banned modules.

    :param full_path_to_module: Full path to the Python file
    :type full_path_to_module: str
    :param banned_imports: List of modules to ban from importing (ie skip)
    :type banned_imports: list
    :returns: A tuple containing the imported module object and its name
    :rtype: tuple[ModuleType, str]
    """

    # banned_imports = {"socProxy"} # Usually speaking, its always socProxy
    if banned_imports is None:
        banned_imports = []
    
    class BlockImportHook:
        """
        A custom import hook that intercepts Python imports to skip loading
        banned modules. This is inserted into sys.meta_path to check each import
        before Python attempts to load it normally.

        If the import name matches a module in the banned list, it returns a
        DummyLoader to simulate an empty module, effectively skipping the import
        without raising an error.
        """

        def find_spec(self_inner, fullname, path, target=None):
            """
            Called by the import machinery to determine if this hook wants to handle
            the import of the module named 'fullname'.

            If the top-level module name is in the banned list, returns a DummyLoader
            to fake an empty import and skip execution. Otherwise, returns None to
            let Python continue with its normal import process.

            :param self_inner: self inner module
            :type self_inner: ModuleType
            :param fullname: The full name of the module
            :type fullname: str
            :param path: The full path to the module
            :type path: str
            :param target: The target module
            :type target: ModuleType
            """
            if fullname is not None and fullname.split('.')[-1] in banned_imports:
                qWarning(f"[Import Skipped] '{fullname}' is in the banned list.")
                print(f"[Import Skipped] '{fullname}' is in the banned list.")
                return importlib.util.spec_from_loader(fullname, DummyLoader(fullname))
            return None  # allow other imports normally

    class DummyLoader:
        """
        The DummyLoader class is used to simulate an empty import and skip execution.
        """

        def __init__(self, name):
            self.name = name

        def create_module(self, spec):
            # Create a dummy module with the expected attributes as None or dummy functions
            dummy_module = SimpleNamespace()
            if self.name.endswith('socProxy'):
                dummy_module.makeProxy = None  # or a dummy function if needed
                dummy_module.soc = None
                dummy_module.soccfg = None
            return dummy_module

        def exec_module(self, module):
            pass  # do nothing

    import_hook = None
    try:
        # AST Check for direct level imports only
        with open(full_path_to_module, "r") as f:
            source_code = f.read()
        tree = ast.parse(source_code, filename=full_path_to_module)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split('.')[-1] in banned_imports:
                        qWarning(f"[Import Skipped] '{alias.name}' is in the banned list.")
                        print(f"[Import Skipped] '{alias.name}' is in the banned list.")
                        continue
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split('.')[-1] in banned_imports:
                    qWarning(f"[Import Skipped] '{node.module}' is in the banned list.")
                    print(f"[Import Skipped] '{node.module}' is in the banned list.")
                    continue

        # Insert import hook to catch all level imports dynamically
        import_hook = BlockImportHook()
        sys.meta_path.insert(0, import_hook)

        # Load the module dynamically
        module_dir, module_file = os.path.split(full_path_to_module)
        module_name, _ = os.path.splitext(module_file)
        loader = importlib.machinery.SourceFileLoader(module_name, full_path_to_module)
        module_obj = loader.load_module()
        module_obj.__file__ = full_path_to_module
        globals()[module_name] = module_obj

        return module_obj, module_name

    except Exception as e:
        raise ImportError(f"Failed to import '{full_path_to_module}': {e}")

    finally:
        # Remove the import hook afterwards
        try:
            if import_hook is not None:
                sys.meta_path.remove(import_hook)
        except ValueError:
            pass
        
# The old basic import file without import blocking functionality
# def import_file(full_path_to_module):
#     """
#     Imports a python file to load it as a module (meaning an iterable list of classes and callables).
#
#     :param full_path_to_module: Full path to the python file
#     :type full_path_to_module: str
#     :returns: A tuple containing the imported module object and its name.
#     :rtype: tuple[ModuleType, str]
#     """
#
#     # attempts a module loading via the full path given
#     try:
#         module_dir, module_file = os.path.split(full_path_to_module)
#         module_name, module_ext = os.path.splitext(module_file)
#         loader = importlib.machinery.SourceFileLoader(module_name, full_path_to_module)
#         module_obj = loader.load_module()
#         module_obj.__file__ = full_path_to_module
#         globals()[module_name] = module_obj
#     except Exception as e:
#         raise ImportError(e)
#     return module_obj, module_name

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

def create_button(text, name, enabled=True, parent=None, shadow=True):
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

    # if shadow:
    #     # Create and configure shadow effect
    #     shadow = QGraphicsDropShadowEffect()
    #     shadow.setBlurRadius(10)  # How blurry the shadow is
    #     shadow.setXOffset(0)  # Horizontal offset
    #     shadow.setYOffset(0)  # Vertical offset
    #     shadow.setColor(QColor(182, 182, 182, 200))  # Shadow color (semi-transparent black)
    #
    #     # Apply shadow to the widget
    #     btn.setGraphicsEffect(shadow)

    return btn

def open_file_dialog(prompt, file_args, settings_id, parent=None, file=True):
    """
    Opens a file dialog to open a file/directory based on the specified parameters and retrieves the last opened
    folder location in QSettings via the identifier to open to.

    :param prompt: The prompt text.
    :type prompt: str
    :param file_args: The file arguments.
    :type file_args: str
    :param settings_id: The settings identifier.
    :type settings_id: str
    :param parent: The parent widget.
    :type parent: QWidget
    :param file: Whether a file should be opened. (Alternative is directory)
    :type file: bool
    """

    settings = QSettings("HouckLab", "Desq") # The identifiers of the application
    last_dir = settings.value(str(settings_id), "..\\")  # Default to "..\\" if not set

    options = QFileDialog.Options()
    if file:
        file_path, _ = QFileDialog.getOpenFileName(parent, str(prompt), last_dir, file_args, options=options)

        if file_path:
            # Save the directory for next time
            settings.setValue(str(settings_id), os.path.dirname(file_path))
            return file_path
    else:
        folder_path = QFileDialog.getExistingDirectory(parent, str(prompt), last_dir, options=options)

        if folder_path:
            # Save the directory for next time
            settings.setValue(str(settings_id), folder_path)
            return folder_path

    return None

def dict_to_h5(data_file, dictionary):
    """
    Stores a dictionary to a h5 file using h5ify.

    :param data_file: The path and name of the h5 file.
    :type data_file: str
    :param dictionary: The dictionary to store.
    :type dictionary: dict
    """
    with h5py.File(data_file, 'w') as f:
        _recursive_save(f, dictionary)

def _recursive_save(h, d):
    """
    Recursively saves a dictionary to a h5 file.

    :param h: The h5 file.
    :type h: h5py.File
    :param d: The dictionary to store.
    :type d: dict
    """
    for key, val in d.items():
        if key == 'config':
            h.attrs['config'] = json.dumps(val, cls=NpEncoder)
        elif isinstance(val, dict):
            h.create_group(key)
            _recursive_save(h[key], val)
        elif isinstance(val, (list, np.ndarray)):
            if all(isinstance(x, str) for x in val):
                # Handle list of strings with variable-length dtype
                dt = h5py.string_dtype(encoding='utf-8')
                h.create_dataset(key, data=np.array(val, dtype=object), dtype=dt)
            else:
                # Handle list of numbers as a variable-length array
                datum = [np.array(sub_arr, dtype=np.float64) for sub_arr in val] \
                            if isinstance(val, list) else np.array(val, dtype=np.float64)

                # If datum is still a list of arrays, pad it to make a rectangular array
                if isinstance(datum, list):
                    max_len = max(len(arr) for arr in datum)
                    datum = np.array(
                        [np.pad(arr, (0, max_len - len(arr)), constant_values=np.nan) for arr in datum])

                try:
                    h.create_dataset(key, data=datum, shape=datum.shape,
                                             maxshape=tuple([None] * len(datum.shape)),
                                             dtype=str(datum.astype(np.float64).dtype))
                except RuntimeError as e:
                    del h[key]
                    raise e

        elif isinstance(val, str):
            # Store single strings
            dt = h5py.string_dtype(encoding='utf-8')
            h.create_dataset(key, data=val, dtype=dt)
        elif isinstance(val, (int, float, np.number)):
            # Store individual numbers directly
            h.create_dataset(key, data=val)
        else:
            raise TypeError(f"Unsupported data type {type(val)} for key '{key}'")


def h5_to_dict(h5file):
    """
    Loads an h5 file and returns a dictionary of the data.

    :param h5file: The path to the h5 file to load.
    :type h5file: str
    """
    data = {}

    # Extract data
    with h5py.File(h5file, 'r') as f:
        _recursive_load(f, data)

    data.pop("attrs", None) # we handle metadata using the extract_metadata() function
    # Extract metadata
    metadata = extract_metadata(h5file)
    for key in metadata.keys():
        data[key] = json.loads(metadata[key])

    return data

def _recursive_load(h, d):
    """
    TODO
    """
    for key, val in h.items():
        if isinstance(val, h5py.Group):
            d[key] = {}
            _recursive_load(val, d[key])
        elif isinstance(val, h5py.Dataset):
            datum = val[()]
            if isinstance(datum, np.ndarray):
                # Convert NumPy arrays back to lists, filter NaN
                datum = np.where(np.isnan(datum), 0, val)
            elif isinstance(datum, bytes):
                datum = datum.decode('utf-8')  # Convert bytes to string
            d[key] = datum
    return d

def extract_metadata(h5file):
    """
    Extracts all attributes (metadata) from an HDF5 file.

    :param h5file: Path to the HDF5 file.
    :type h5file: str
    :return: Dictionary containing all metadata attributes.
    :rtype: dict
    """
    metadata = {}
    with h5py.File(h5file, "r") as f:
        for key in f.attrs.keys():
            metadata[key] = f.attrs[key]  # Extract attribute values

    return metadata

class NpEncoder(json.JSONEncoder):
    """
    An encoder that ensures json dump can handle np arrays
    """
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)

def format_time_duration_pretty(seconds: float) -> str:
    """
    Formats a number of seconds into a pretty string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds - int(seconds)) * 1000)

    return f"{hours:02d}h {minutes:02d}m {secs:02d}s {milliseconds:03d}ms"

def format_date_time_pretty(seconds_from_now: float) -> str:
    future = datetime.now() + timedelta(seconds=seconds_from_now)
    return future.strftime("%m/%d %I:%M%p").lower()

# def dict_to_h5(data_file, dictionary):
#     """
#     Recursively stores a dictionary into an HDF5 group.
#     Handles nested dictionaries, lists, strings, and numerical data.
#
#     :param data_file: A writeable reference to an h5 file
#     :type data_file: h5py.File
#     :param dictionary: The dictionary to convert into h5
#     :type dictionary: dict
#     """
#
#     for key, datum in dictionary.items():
#
#         if isinstance(datum, dict):
#             data_file.attrs[key] = json.dumps(datum, cls=NpEncoder)
#         else:
#             # Convert to NumPy array and handle jagged arrays
#             datum = [np.array(sub_arr, dtype=np.float64) for sub_arr in datum] \
#                 if isinstance(datum, list) else np.array(datum, dtype=np.float64)
#
#             # If datum is still a list of arrays, pad it to make a rectangular array
#             if isinstance(datum, list):
#                 max_len = max(len(arr) for arr in datum)
#                 datum = np.array(
#                     [np.pad(arr, (0, max_len - len(arr)), constant_values=np.nan) for arr in datum])
#
#             try:
#                 data_file.create_dataset(key, shape=datum.shape,
#                                          maxshape=tuple([None] * len(datum.shape)),
#                                          dtype=str(datum.astype(np.float64).dtype))
#             except RuntimeError as e:
#                 del data_file[key]
#                 raise e
#
#             data_file[key][...] = datum
#
# def h5_to_dict(h5file):
#     """
#     Recursively converts an HDF5 group back into a dictionary.
#     Restores nested dictionaries, lists, and numerical/text data.
#     """
#     result = {}
#
#     with h5py.File(h5file, "r") as f:
#
#         for key, item in f.items():
#             if isinstance(item, h5py.Group):
#                 result[key] = h5_to_dict(item)  # Recurse
#
#             elif isinstance(item, h5py.Dataset):
#                 data = item[()]
#                 if isinstance(data, np.ndarray):
#                     data = data.tolist()  # Convert NumPy arrays back to lists
#                 elif isinstance(data, bytes):
#                     data = data.decode('utf-8')  # Convert bytes to string
#                 result[key] = data
#
#     return result