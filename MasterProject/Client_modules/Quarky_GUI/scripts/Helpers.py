"""
==========
Helpers.py
==========
Module containing all helper functions for the Quarky GUI.
"""

import os
import json
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

# h5 functionality inspired by h5ify

def dict_to_h5(data_filename, dictionary):
    """
    Stores a dictionary to a h5 file using h5ify.

    :param data_filename: The path and name of the h5 file.
    :type data_filename: str
    :param dictionary: The dictionary to store.
    :type dictionary: dict
    """
    with h5py.File(data_filename, 'w') as f:
        _recursive_save(f, dictionary)

def _recursive_save(h, d):
    for key, val in d.items():
        if key == 'attrs':
            h.attrs.update(d[key])
        elif isinstance(val, dict):
            h.create_group(key)
            _recursive_save(h[key], val)
        elif isinstance(val, (list, np.ndarray)):
            if all(isinstance(x, str) for x in val):
                # Handle list of strings with variable-length dtype
                dt = h5py.string_dtype(encoding='utf-8')
                h.create_dataset(key, data=np.array(val, dtype=object), dtype=dt)
            else:
                # Handle lists/arrays of variable length using special dtype
                dt = h5py.special_dtype(vlen=np.float64)  # Adjust dtype as needed
                h.create_dataset(key, data=np.array(val, dtype=object), dtype=dt)
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
        loaded_dict = {}
        _recursive_load(f, loaded_dict)

    loaded_dict.pop("attrs", None) # we handle metadata using the extract_metadata() function
    data['data'] = loaded_dict

    # Extract other metadata (dictionaries)
    metadata = extract_metadata(h5file)
    for key in metadata.keys():
        data[key] = json.loads(metadata[key])

    print(data)
    return data

def _recursive_load(h, d):
    attrs = dict(h.attrs)
    if len(attrs) > 0:
        d['attrs'] = attrs
    for key, val in h.items():
        if isinstance(val, h5py.Group):
            d[key] = {}
            _recursive_load(val, d[key])
        elif isinstance(val, h5py.Dataset):
            d[key] = val[()]
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