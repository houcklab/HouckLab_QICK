import os
import importlib
import h5py
from PyQt5.QtWidgets import (
    QPushButton,
)

def import_file(full_path_to_module):
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
    with h5py.File(h5file, "r") as f:
        data_dict = {}
        for key in f.keys():
            data_dict[key] = f[key][()]  # Load dataset into memory
        return data_dict

# Should be moved to Helpers
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