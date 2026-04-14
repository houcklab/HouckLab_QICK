"""
==========
Helpers.py
==========

Module containing all helper functions for the Desq GUI.

This module provides utility functions for:

- Dynamic Python module importing with security controls
- HDF5 file I/O with recursive dictionary serialization
- PyQt5 widget creation helpers
- File dialog management with persistent path memory
- Time/date formatting utilities

:var NpEncoder: JSON encoder class that handles NumPy types.
:vartype NpEncoder: type

.. seealso::
    :mod:`SettingsWindow` which uses several functions from this module.
"""

import os
import json
import ast
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Union

import numpy as np
import importlib
import importlib.util
import importlib.machinery
import h5py
import sys
from types import ModuleType, SimpleNamespace

from PyQt5.QtWidgets import (
    QPushButton, QGraphicsDropShadowEffect, QFileDialog, QWidget
)
from PyQt5.QtCore import qWarning, QSettings
from PyQt5.QtGui import QColor


def import_file(
    full_path_to_module: str,
    banned_imports: Optional[List[str]] = None
) -> Tuple[ModuleType, str]:
    """
    Securely import a Python file with static and runtime protection against banned modules.

    This function provides a secure way to dynamically import Python modules while
    blocking specified imports. It uses a two-phase approach:

    1. **Static Analysis**: Parses the source code using AST to detect direct imports
       of banned modules and logs warnings.
    2. **Runtime Blocking**: Installs a custom import hook that intercepts import
       attempts during module execution, returning dummy modules for banned imports.

    :param full_path_to_module: Absolute path to the Python file to import.
    :type full_path_to_module: str
    :param banned_imports: List of module names to block from importing.
        These are matched against the final component of the module path
        (e.g., "socProxy" would block "some.package.socProxy").
        Defaults to an empty list if None.
    :type banned_imports: list of str, optional

    :returns: A tuple containing:
        - The imported module object
        - The module name (filename without extension)
    :rtype: tuple[ModuleType, str]

    :raises ImportError: If the module cannot be loaded due to syntax errors,
        missing file, or other import failures.

    .. note::
        The import hook is installed temporarily and removed in a finally block,
        ensuring cleanup even if an exception occurs.

    .. note::
        DEPRECATED CODE: There is a commented-out simpler version of this function
        (lines 142-163 in original) that lacks the banned import functionality.
        This was the original implementation before security controls were added.

    .. warning::
        This function modifies ``sys.meta_path`` temporarily. Concurrent imports
        from multiple threads may experience unexpected behavior.

    .. seealso::
        :class:`BlockImportHook` and :class:`DummyLoader` (nested classes)
        for implementation details of the import blocking mechanism.

    Example::

        module, name = import_file("/path/to/experiment.py", banned_imports=["socProxy"])
        experiment_class = getattr(module, "MyExperiment")
    """
    # Default to empty list if no banned imports specified
    # Note: Original comment mentioned socProxy as typical banned import
    if banned_imports is None:
        banned_imports = []

    class BlockImportHook:
        """
        Custom import hook that intercepts Python imports to skip banned modules.

        This class is inserted into ``sys.meta_path`` to check each import
        before Python attempts to load it normally. If an import matches
        a banned module, it returns a DummyLoader to simulate an empty module.

        .. note::
            This is a nested class within :func:`import_file` and captures
            the ``banned_imports`` list from the enclosing scope.
        """

        def find_spec(
            self_inner,
            fullname: str,
            path: Optional[str],
            target: Optional[ModuleType] = None
        ):
            """
            Determine if this hook should handle the import of a module.

            Called by Python's import machinery for each import statement.
            If the module name matches a banned import, returns a spec with
            a DummyLoader to fake an empty module.

            :param self_inner: The BlockImportHook instance.
            :type self_inner: BlockImportHook
            :param fullname: Fully qualified name of the module being imported
                (e.g., "package.submodule.module").
            :type fullname: str
            :param path: The path to search for the module (usually package __path__).
            :type path: str or None
            :param target: The target module object (used for reloading).
            :type target: ModuleType or None

            :returns: A ModuleSpec with DummyLoader if the module is banned,
                None otherwise to allow normal import processing.
            :rtype: ModuleSpec or None
            """
            # Check if the final component of the module name is in banned list
            if fullname is not None and fullname.split('.')[-1] in banned_imports:
                qWarning(f"[Import Skipped] '{fullname}' is in the banned list.")
                print(f"[Import Skipped] '{fullname}' is in the banned list.")
                return importlib.util.spec_from_loader(fullname, DummyLoader(fullname))
            return None  # Allow other imports to proceed normally

    class DummyLoader:
        """
        Loader that creates a dummy module to simulate skipped imports.

        When a banned module is imported, this loader creates a SimpleNamespace
        object with None values for expected attributes, preventing AttributeError
        when the importing code tries to access module members.

        :ivar name: The name of the module being faked.
        :vartype name: str
        """

        def __init__(self, name: str) -> None:
            """
            Initialize the DummyLoader with the module name.

            :param name: The fully qualified module name to fake.
            :type name: str
            """
            self.name = name

        def create_module(self, spec) -> SimpleNamespace:
            """
            Create a dummy module with expected attributes set to None.

            :param spec: The module spec (unused but required by import protocol).
            :type spec: ModuleSpec

            :returns: A SimpleNamespace object serving as the dummy module.
                For socProxy modules, includes makeProxy, soc, and soccfg
                attributes set to None.
            :rtype: SimpleNamespace
            """
            # Create a namespace object to serve as the dummy module
            dummy_module = SimpleNamespace()
            # Special handling for socProxy - add expected attributes
            if self.name.endswith('socProxy'):
                dummy_module.makeProxy = None
                dummy_module.soc = None
                dummy_module.soccfg = None
            return dummy_module

        def exec_module(self, module) -> None:
            """
            Execute the module (no-op for dummy modules).

            :param module: The module to execute.
            :type module: SimpleNamespace
            """
            pass  # Do nothing - module is already "loaded"

    import_hook = None
    try:
        # ========== Phase 1: Static AST Analysis ==========
        # Parse source code to detect and warn about banned imports at the top level
        with open(full_path_to_module, "r") as f:
            source_code = f.read()
        tree = ast.parse(source_code, filename=full_path_to_module)

        # Walk the AST to find import statements
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # Handle: import module, import package.module
                for alias in node.names:
                    if alias.name.split('.')[-1] in banned_imports:
                        qWarning(f"[Import Skipped] '{alias.name}' is in the banned list.")
                        print(f"[Import Skipped] '{alias.name}' is in the banned list.")
                        continue
            elif isinstance(node, ast.ImportFrom):
                # Handle: from package import module
                if node.module and node.module.split('.')[-1] in banned_imports:
                    qWarning(f"[Import Skipped] '{node.module}' is in the banned list.")
                    print(f"[Import Skipped] '{node.module}' is in the banned list.")
                    continue

        # ========== Phase 2: Runtime Import Blocking ==========
        # Install import hook to catch all imports during module execution
        import_hook = BlockImportHook()
        sys.meta_path.insert(0, import_hook)

        # Load the module using importlib machinery
        module_dir, module_file = os.path.split(full_path_to_module)
        module_name, _ = os.path.splitext(module_file)
        loader = importlib.machinery.SourceFileLoader(module_name, full_path_to_module)
        # NOTE: load_module() is deprecated in Python 3.4+, but still functional
        # Consider using loader.exec_module() with spec in future refactor
        module_obj = loader.load_module()
        module_obj.__file__ = full_path_to_module
        # Add to globals for potential later access (may not be necessary)
        globals()[module_name] = module_obj

        return module_obj, module_name

    except Exception as e:
        raise ImportError(f"Failed to import '{full_path_to_module}': {e}")

    finally:
        # ========== Cleanup: Remove Import Hook ==========
        # Ensure hook is removed even if an exception occurred
        try:
            if import_hook is not None:
                sys.meta_path.remove(import_hook)
        except ValueError:
            pass  # Hook was already removed (shouldn't happen)


# =============================================================================
# DEPRECATED: Original simple import_file without import blocking
# =============================================================================
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


def simple_h5_to_dict(h5file: str) -> Dict[str, np.ndarray]:
    """
    Convert an HDF5 file to a dictionary with all datasets loaded as arrays.

    This is a simplified loader that assumes all values in the HDF5 file are
    datasets (no groups) and loads them directly into memory. For more complex
    HDF5 structures with nested groups, use :func:`h5_to_dict` instead.

    :param h5file: Path to the HDF5 file to load.
    :type h5file: str

    :returns: Dictionary mapping dataset names to their data arrays.
    :rtype: dict[str, numpy.ndarray]

    :raises OSError: If the file cannot be opened.
    :raises KeyError: If the file structure is invalid.

    .. seealso::
        :func:`h5_to_dict` for recursive loading with group support and metadata.
    """
    with h5py.File(h5file, "r") as f:
        data_dict = {}
        for key in f.keys():
            # Load dataset into memory using [()] syntax
            data_dict[key] = f[key][()]
        return data_dict


def create_button(
    text: str,
    name: str,
    enabled: bool = True,
    parent: Optional[QWidget] = None,
    shadow: bool = True,
    checkable: bool = False
) -> QPushButton:
    """
    Create and configure a QPushButton with standard settings.

    Factory function for creating consistently styled buttons throughout
    the Desq GUI application.

    :param text: Display text for the button.
    :type text: str
    :param name: Object name for the button (used for styling and identification).
    :type name: str
    :param enabled: Whether the button starts enabled. Defaults to True.
    :type enabled: bool, optional
    :param parent: Parent widget for the button. Defaults to None.
    :type parent: QWidget, optional
    :param shadow: Whether to apply a drop shadow effect.
        **Currently unused** - shadow code is commented out.
        Defaults to True.
    :type shadow: bool, optional
    :param checkable: Whether the button can be toggled on/off. Defaults to False.
    :type checkable: bool, optional

    :returns: The configured QPushButton instance.
    :rtype: QPushButton

    Example::

        save_btn = create_button("Save", "save_button", True)
        toggle_btn = create_button("Toggle", "toggle_button", checkable=True)
    """
    btn = QPushButton(text, parent)
    btn.setObjectName(name)
    btn.setEnabled(enabled)
    btn.setCheckable(checkable)

    # Old button shadow effect
    # if shadow:
    #     # Create and configure shadow effect
    #     shadow = QGraphicsDropShadowEffect()
    #     shadow.setBlurRadius(10)  # How blurry the shadow is
    #     shadow.setXOffset(0)  # Horizontal offset
    #     shadow.setYOffset(0)  # Vertical offset
    #     shadow.setColor(QColor(182, 182, 182, 200))  # Semi-transparent gray
    #
    #     # Apply shadow to the widget
    #     btn.setGraphicsEffect(shadow)

    return btn


def open_file_dialog(
    prompt: str,
    file_args: str,
    settings_id: str,
    parent: Optional[QWidget] = None,
    file: bool = True,
    initial_dir: Optional[str] = None
) -> Optional[str]:
    """
    Open a file or directory selection dialog with persistent path memory.

    Opens a Qt file dialog and remembers the last used directory for each
    unique ``settings_id``, restoring it on subsequent calls. This provides
    a better user experience by starting in familiar locations.

    :param prompt: Title text displayed in the dialog window.
    :type prompt: str
    :param file_args: File filter string (e.g., "Python Files (*.py);;All Files (*)").
        Ignored when ``file=False``.
    :type file_args: str
    :param settings_id: Unique identifier for storing/retrieving the last
        used directory in QSettings.
    :type settings_id: str
    :param parent: Parent widget for the dialog. Defaults to None.
    :type parent: QWidget, optional
    :param file: If True, opens a file selection dialog. If False, opens a
        directory selection dialog. Defaults to True.
    :type file: bool, optional
    :param initial_dir: Override directory to start in, ignoring saved path.
        Defaults to None (use saved path).
    :type initial_dir: str, optional

    :returns: Selected file/directory path, or None if dialog was cancelled.
    :rtype: str or None

    .. note::
        Uses QSettings with organization "HouckLab" and application "Desq".
        Settings are stored in platform-specific locations:

        - Windows: Registry under HKEY_CURRENT_USER\\Software\\HouckLab\\Desq
        - macOS: ~/Library/Preferences/com.houcklab.Desq.plist
        - Linux: ~/.config/HouckLab/Desq.conf

    Example::

        path = open_file_dialog(
            "Select Experiment File",
            "Python Files (*.py);;All Files (*)",
            "last_experiment_dir"
        )
        if path:
            print(f"Selected: {path}")
    """
    # Retrieve QSettings for persistent path storage
    settings = QSettings("HouckLab", "Desq")
    # Get last used directory, defaulting to parent directory
    last_dir = settings.value(str(settings_id), "..\\")

    # Override with explicit directory if provided
    if initial_dir:
        last_dir = initial_dir

    options = QFileDialog.Options()

    if file:
        # Open file selection dialog
        file_path, _ = QFileDialog.getOpenFileName(
            parent, str(prompt), last_dir, file_args, options=options
        )

        if file_path:
            # Save directory for next time (just the directory, not the file)
            settings.setValue(str(settings_id), os.path.dirname(file_path))
            return file_path
    else:
        # Open directory selection dialog
        folder_path = QFileDialog.getExistingDirectory(
            parent, str(prompt), last_dir, options=options
        )

        if folder_path:
            # Save directory for next time
            settings.setValue(str(settings_id), folder_path)
            return folder_path

    return None


def dict_to_h5(data_file: str, dictionary: Dict[str, Any]) -> None:
    """
    Store a dictionary to an HDF5 file with recursive structure preservation.

    Recursively traverses the dictionary and stores each value using the
    appropriate HDF5 structure (datasets, groups, or attributes).

    :param data_file: Path where the HDF5 file will be created.
    :type data_file: str
    :param dictionary: Dictionary to serialize. Supports nested dicts,
        lists, NumPy arrays, strings, and numeric types.
    :type dictionary: dict

    :raises TypeError: If the dictionary contains unsupported data types.
    :raises OSError: If the file cannot be created.

    .. seealso::
        :func:`_recursive_save` for the implementation details.
        :func:`h5_to_dict` for the inverse operation.
        :class:`NpEncoder` for JSON encoding of NumPy types in config.

    Example::

        data = {
            "config": {"param1": 1.0, "param2": "value"},
            "measurements": np.array([1, 2, 3]),
            "nested": {"inner": np.array([4, 5, 6])}
        }
        dict_to_h5("experiment_data.h5", data)
    """
    with h5py.File(data_file, 'w') as f:
        _recursive_save(f, dictionary)


def _recursive_save(h: Union[h5py.File, h5py.Group], d: Dict[str, Any]) -> None:
    """
    Recursively save dictionary contents to an HDF5 file or group.

    This is an internal helper function used by :func:`dict_to_h5`.
    It handles different data types appropriately:

    - **config key**: Stored as JSON string in file attributes
    - **Nested dicts**: Creates HDF5 groups recursively
    - **Lists of strings**: Stored with variable-length UTF-8 dtype
    - **Lists containing dicts**: Creates indexed subgroups (0000, 0001, ...)
    - **Numeric arrays/lists**: Stored as float64 datasets with NaN padding
    - **Single strings**: Stored as UTF-8 datasets
    - **Numbers**: Stored as scalar datasets

    :param h: HDF5 file or group to write to.
    :type h: h5py.File or h5py.Group
    :param d: Dictionary to save.
    :type d: dict

    :raises TypeError: If a value has an unsupported data type.
    :raises RuntimeError: If dataset creation fails (attempts cleanup).

    .. note::
        Numeric lists with varying lengths are padded with NaN values to create
        rectangular arrays. This is handled in the else branch of the
        list/ndarray handling code.

    .. warning::
        If dataset creation fails with RuntimeError, the function attempts to
        delete the partially created dataset before re-raising the exception.
    """
    for key, val in d.items():
        if key == 'config':
            # Store config as JSON string in file attributes
            # Uses NpEncoder to handle NumPy types
            h.attrs['config'] = json.dumps(val, cls=NpEncoder)

        elif isinstance(val, dict):
            # Create group for nested dictionary
            h.create_group(key)
            _recursive_save(h[key], val)

        elif isinstance(val, (list, np.ndarray)):
            # Handle list of strings specially
            if all(isinstance(x, str) for x in val):
                # Variable-length UTF-8 string dtype
                dt = h5py.string_dtype(encoding='utf-8')
                h.create_dataset(key, data=np.array(val, dtype=object), dtype=dt)

            elif isinstance(val, list):
                # Check if list contains dictionaries
                if any(isinstance(x, dict) for x in val):
                    # Store as indexed subgroups: key/0000, key/0001, etc.
                    h.create_group(key)
                    for i, item in enumerate(val):
                        subkey = f"{i:04d}"  # Zero-padded 4-digit index
                        if isinstance(item, dict):
                            h[key].create_group(subkey)
                            _recursive_save(h[key][subkey], item)
                        else:
                            # Store non-dict items as JSON string attributes
                            h[key].attrs[subkey] = json.dumps(item, cls=NpEncoder)
                    continue

            else:
                # Handle numeric arrays/lists
                # Convert list elements to float64 arrays
                datum = [np.array(sub_arr, dtype=np.float64) for sub_arr in val] \
                    if isinstance(val, list) else np.array(val, dtype=np.float64)

                # If datum is still a list of arrays, pad to make rectangular
                if isinstance(datum, list):
                    # Ensure all elements are at least 1D arrays
                    arrs = [np.atleast_1d(arr) if isinstance(arr, np.ndarray)
                            else np.atleast_1d(np.asarray(arr))
                            for arr in datum]

                    # Find maximum length for padding
                    max_len = max(a.shape[0] for a in arrs)

                    # Pad shorter arrays with NaN to create rectangular array
                    datum = np.array(
                        [np.pad(a, (0, max_len - a.shape[0]), constant_values=np.nan)
                         for a in arrs],
                        dtype=float
                    )

                try:
                    # Create resizable dataset (maxshape with None allows growth)
                    h.create_dataset(
                        key, data=datum, shape=datum.shape,
                        maxshape=tuple([None] * len(datum.shape)),
                        dtype=str(datum.astype(np.float64).dtype)
                    )
                except RuntimeError as e:
                    # Cleanup partially created dataset
                    del h[key]
                    raise e

        elif isinstance(val, str):
            # Store single string with UTF-8 encoding
            dt = h5py.string_dtype(encoding='utf-8')
            h.create_dataset(key, data=val, dtype=dt)

        elif isinstance(val, (int, float, np.number)):
            # Store scalar numeric values directly
            h.create_dataset(key, data=val)

        else:
            raise TypeError(f"Unsupported data type {type(val)} for key '{key}'")


def h5_to_dict(h5file: str) -> Dict[str, Any]:
    """
    Load an HDF5 file and return its contents as a nested dictionary.

    Recursively loads all groups and datasets from the HDF5 file, including
    metadata stored as attributes. The 'config' attribute is automatically
    parsed from JSON.

    :param h5file: Path to the HDF5 file to load.
    :type h5file: str

    :returns: Dictionary containing all data from the file. The 'attrs' key
        is removed if present (metadata is handled separately).
    :rtype: dict

    :raises OSError: If the file cannot be opened.
    :raises json.JSONDecodeError: If metadata JSON is malformed.

    .. seealso::
        :func:`_recursive_load` for the recursive loading implementation.
        :func:`extract_metadata` for extracting file attributes.
        :func:`dict_to_h5` for the inverse operation.

    .. note::
        NaN values in numeric arrays are replaced with 0 during loading.
        This behavior is implemented in :func:`_recursive_load`.
    """
    data = {}

    # Extract data recursively
    with h5py.File(h5file, 'r') as f:
        _recursive_load(f, data)

    # Remove 'attrs' key if present - metadata is handled separately
    data.pop("attrs", None)

    # Extract and parse metadata attributes
    metadata = extract_metadata(h5file)
    for key in metadata.keys():
        data[key] = json.loads(metadata[key])

    return data


def _recursive_load(
    h: Union[h5py.File, h5py.Group],
    d: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Recursively load HDF5 groups and datasets into a dictionary.

    Internal helper function for :func:`h5_to_dict`.

    :param h: HDF5 file or group to read from.
    :type h: h5py.File or h5py.Group
    :param d: Dictionary to populate with loaded data.
    :type d: dict

    :returns: The populated dictionary (same as input ``d``).
    :rtype: dict
    """
    for key, val in h.items():
        if isinstance(val, h5py.Group):
            # Recursively load group contents
            d[key] = {}
            _recursive_load(val, d[key])
        elif isinstance(val, h5py.Dataset):
            datum = val[()]
            if isinstance(datum, np.ndarray):
                # Convert NaN values to 0
                datum = np.where(np.isnan(datum), 0, datum)
            elif isinstance(datum, bytes):
                # Decode bytes to UTF-8 string
                datum = datum.decode('utf-8')
            d[key] = datum
    return d


def extract_metadata(h5file: str) -> Dict[str, Any]:
    """
    Extract all attributes (metadata) from an HDF5 file's root.

    Reads the top-level attributes of an HDF5 file, which typically contain
    configuration and experiment metadata stored by :func:`dict_to_h5`.

    :param h5file: Path to the HDF5 file.
    :type h5file: str

    :returns: Dictionary mapping attribute names to their values.
        Note that values may be JSON strings that need parsing.
    :rtype: dict

    :raises OSError: If the file cannot be opened.

    .. seealso::
        :func:`h5_to_dict` which uses this function internally.

    Example::

        metadata = extract_metadata("experiment.h5")
        config = json.loads(metadata.get("config", "{}"))
    """
    metadata = {}
    with h5py.File(h5file, "r") as f:
        for key in f.attrs.keys():
            metadata[key] = f.attrs[key]

    return metadata


class NpEncoder(json.JSONEncoder):
    """
    JSON encoder that handles NumPy data types.

    Extends the standard JSONEncoder to properly serialize NumPy integers,
    floats, and arrays which are not natively supported by the json module.

    :ivar default: Overridden method that converts NumPy types to native Python types.
    :vartype default: method

    Example::

        import numpy as np
        import json

        data = {"array": np.array([1, 2, 3]), "value": np.float64(3.14)}
        json_str = json.dumps(data, cls=NpEncoder)
        # Result: '{"array": [1, 2, 3], "value": 3.14}'

    .. seealso::
        :func:`dict_to_h5` which uses this encoder for config serialization.
    """

    def default(self, obj: Any) -> Any:
        """
        Convert NumPy types to JSON-serializable Python types.

        :param obj: Object to serialize.
        :type obj: Any

        :returns: JSON-serializable version of the object.
        :rtype: int, float, list, or result of parent default()

        :raises TypeError: If the object type is not supported (via parent class).
        """
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


def format_time_duration_pretty(seconds: float) -> str:
    """
    Format a duration in seconds as a human-readable string.

    Converts a floating-point number of seconds into a formatted string
    showing hours, minutes, seconds, and milliseconds.

    :param seconds: Duration in seconds (can include fractional seconds).
    :type seconds: float

    :returns: Formatted string in the format "XXh XXm XXs XXXms".
    :rtype: str

    Example::

        >>> format_time_duration_pretty(3661.5)
        '01h 01m 01s 500ms'
        >>> format_time_duration_pretty(45.123)
        '00h 00m 45s 123ms'
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds - int(seconds)) * 1000)

    return f"{hours:02d}h {minutes:02d}m {secs:02d}s {milliseconds:03d}ms"


def format_date_time_pretty(seconds_from_now: float) -> str:
    """
    Calculate a future datetime and format it as a readable string.

    Adds the specified number of seconds to the current time and returns
    a formatted date/time string.

    :param seconds_from_now: Number of seconds to add to current time.
    :type seconds_from_now: float

    :returns: Formatted string in "MM/DD HH:MMam/pm" format (lowercase am/pm).
    :rtype: str

    Example::

        # If current time is 01/15 2:30pm:
        >>> format_date_time_pretty(3600)  # 1 hour from now
        '01/15 03:30pm'
        >>> format_date_time_pretty(86400)  # 24 hours from now
        '01/16 02:30pm'
    """
    future = datetime.now() + timedelta(seconds=seconds_from_now)
    return future.strftime("%m/%d %I:%M%p").lower()