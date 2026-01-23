"""
Experiment Module
=================

This module provides base classes for managing quantum experiments, including
data file handling, configuration management, and experiment workflow orchestration.

The module contains:

- :class:`MakeFile`: HDF5 file wrapper for experimental data storage
- :class:`NpEncoder`: JSON encoder with NumPy type support
- :class:`ExperimentClass`: Base class for all experiment implementations

:var Path: Path class from pathlib for filesystem operations
:vartype Path: type

.. note::
    This module requires the ``MasterProject.Client_modules.Desq_GUI.scripts.Helpers``
    module for HDF5 dictionary serialization utilities.
"""

import os
import json
import numpy as np
import h5py
import datetime
from pathlib import Path
from typing import Any, Optional, Dict, Tuple, Union

import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers


class MakeFile(h5py.File):
    """
    HDF5 file wrapper with automatic dataset creation and update capabilities.

    This class extends :class:`h5py.File` to provide convenient methods for
    adding and updating datasets with automatic shape and dtype handling.

    :ivar mode: The file access mode ('r', 'w', 'a', etc.)
    :vartype mode: str

    .. seealso::
        :class:`h5py.File` for base class documentation
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize the HDF5 file wrapper.

        :param args: Positional arguments passed to :class:`h5py.File`
        :type args: Any
        :param kwargs: Keyword arguments passed to :class:`h5py.File`
        :type kwargs: Any

        """
        h5py.File.__init__(self, *args, **kwargs)

        self.flush()

    def add(self, key: str, data: Any) -> None:
        """
        Add or update a dataset in the HDF5 file.

        Creates a new dataset with the given key, or replaces an existing one
        if a dataset with that key already exists. The dataset is created with
        unlimited dimensions (resizable) and float64 dtype.

        :param key: The name/path of the dataset in the HDF5 file
        :type key: str
        :param data: The data to store, will be converted to numpy array
        :type data: Any

        :raises RuntimeError: Caught internally when dataset already exists,
            triggers deletion and recreation

        .. note::
            The dataset is always stored as float64 regardless of input dtype.
            The ``maxshape`` is set to ``(None, ...)`` allowing unlimited growth
            in all dimensions.
        """
        # Convert input to numpy array for consistent handling
        data = np.array(data)
        try:
            # Create dataset with resizable dimensions (maxshape=None for each dim)
            self.create_dataset(key, shape=data.shape,
                                maxshape=tuple([None] * len(data.shape)),
                                dtype=str(data.astype(np.float64).dtype))
        except RuntimeError:
            # Dataset already exists - delete and recreate
            del self[key]
            self.create_dataset(key, shape=data.shape,
                                maxshape=tuple([None] * len(data.shape)),
                                dtype=str(data.astype(np.float64).dtype))
        # Write data to the dataset using ellipsis indexing
        self[key][...] = data


class NpEncoder(json.JSONEncoder):
    """
    JSON encoder that handles NumPy data types.

    Extends :class:`json.JSONEncoder` to properly serialize NumPy integers,
    floats, and arrays to their Python equivalents for JSON compatibility.

    .. note::
        This encoder converts:

        - ``np.integer`` types to Python ``int``
        - ``np.floating`` types to Python ``float``
        - ``np.ndarray`` to Python ``list``

    .. seealso::
        :class:`json.JSONEncoder` for base class documentation
    """

    def default(self, obj: Any) -> Any:
        """
        Convert NumPy types to JSON-serializable Python types.

        :param obj: Object to encode
        :type obj: Any

        :returns: JSON-serializable Python equivalent of the input
        :rtype: Union[int, float, list, Any]

        :raises TypeError: Via super().default() if object type is not
            supported by this encoder or the base encoder
        """
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


class ExperimentClass:
    """
    Base class for all quantum experiments.

    Provides infrastructure for experiment execution including:

    - Automatic directory creation and file path management
    - Configuration file handling (JSON format)
    - HDF5 data file management
    - Standard experiment workflow (acquire -> analyze -> save -> display)

    :ivar path: Subdirectory name for experiment data
    :vartype path: str
    :ivar outerFolder: Base directory for all experiment data
    :vartype outerFolder: str
    :ivar prefix: Suffix used when creating data files
    :vartype prefix: str
    :ivar cfg: Experiment configuration dictionary
    :vartype cfg: Optional[dict]
    :ivar soc: QICK system-on-chip instance for hardware control
    :vartype soc: Optional[Any]
    :ivar soccfg: QICK system-on-chip configuration
    :vartype soccfg: Optional[Any]
    :ivar config_file: Path to configuration file (JSON)
    :vartype config_file: Optional[str]
    :ivar dname: Base path for data files (without extension)
    :vartype dname: str
    :ivar fname: Full path to HDF5 data file (.h5)
    :vartype fname: str
    :ivar iname: Full path to image file (.png)
    :vartype iname: str
    :ivar cname: Full path to configuration file (.json)
    :vartype cname: str

    .. note::
        The ``load_config`` method and associated functionality (InstrumentManager,
        LivePlotter, dataserver_client) have been commented out in the original
        implementation and are not currently functional.

    .. seealso::
        :class:`MakeFile` for HDF5 file handling
        :class:`NpEncoder` for configuration JSON serialization
    """

    def __init__(
        self,
        path: str = '',
        outerFolder: str = '',
        prefix: str = 'data',
        soc: Optional[Any] = None,
        soccfg: Optional[Any] = None,
        cfg: Optional[Dict[str, Any]] = None,
        config_file: Optional[str] = None,
        liveplot_enabled: bool = False,
        short_directory_names: bool = False,
        **kwargs: Any
    ) -> None:
        """
        Initialize the experiment class with file paths and configuration.

        Creates the necessary directory structure for data storage and sets up
        file paths for data (.h5), images (.png), and configuration (.json).

        :param path: Subdirectory name for experiment data within outerFolder
        :type path: str
        :param outerFolder: Base directory path for all experiment data
        :type outerFolder: str
        :param prefix: Suffix to use when creating data files (despite the name,
            this is actually used as a suffix in filenames)
        :type prefix: str
        :param soc: QICK system-on-chip instance for hardware control
        :type soc: Optional[Any]
        :param soccfg: QICK system-on-chip configuration object
        :type soccfg: Optional[Any]
        :param cfg: Experiment configuration dictionary
        :type cfg: Optional[Dict[str, Any]]
        :param config_file: Path to configuration file. If relative path (no leading /),
            it is joined with the path parameter. If None, no config file is loaded.
        :type config_file: Optional[str]
        :param liveplot_enabled: Whether to enable live plotting (currently unused)
        :type liveplot_enabled: bool
        :param short_directory_names: If True, use simplified directory naming
            (date only). If False, include path prefix in directory names.
        :type short_directory_names: bool
        :param kwargs: Additional keyword arguments are added to instance ``__dict__``
        :type kwargs: Any

        .. note::
            The ``prefix`` parameter name is misleading - it is actually used as
            a suffix in the generated filenames (e.g., ``datetime_prefix.h5``). This is old
            code so it is kept for backwards compatibility.
        """

        # Update instance dict with any additional kwargs
        self.__dict__.update(kwargs)
        self.path = path
        self.outerFolder = outerFolder

        # Generate timestamp strings for file naming
        datetimenow = datetime.datetime.now()
        datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
        datestring = datetimenow.strftime("%Y_%m_%d")

        self.prefix = prefix
        self.cfg = cfg
        self.soc = soc
        self.soccfg = soccfg

        # Handle config file path - join with path if relative
        if config_file is not None:
            self.config_file = os.path.join(path, config_file)
        else:
            self.config_file = None

        # Create main data directory if it doesn't exist
        DataFolderBool = Path(os.path.join(self.outerFolder, self.path)).is_dir()
        if self.path != '' and self.outerFolder != '' and DataFolderBool == False:
            os.mkdir(self.outerFolder + self.path)

        # Create date-based subdirectory
        # Directory naming depends on short_directory_names setting
        DataSubFolderBool = Path(os.path.join(self.outerFolder + self.path, datestring)).is_dir() if short_directory_names \
                            else Path(os.path.join(self.outerFolder + self.path, self.path + "_" + datestring)).is_dir()
        if DataSubFolderBool == False:
            if short_directory_names:
                os.mkdir(os.path.join(self.outerFolder + self.path, datestring))
            else:
                os.mkdir(os.path.join(self.outerFolder + self.path, self.path + "_" + datestring))

        # Set up file paths based on naming convention
        if short_directory_names:
            # Short naming: outerFolder/path/date/datetime_prefix.ext
            self.dname = os.path.join(self.outerFolder + self.path, datestring, datetimestring + "_" + self.prefix)
            self.fname = os.path.join(self.outerFolder + self.path, datestring, datetimestring + "_" + self.prefix + '.h5')
            self.iname = os.path.join(self.outerFolder + self.path, datestring, datetimestring + "_" + self.prefix + '.png')
            self.cname = os.path.join(self.outerFolder +  self.path, datestring, datetimestring + "_" + self.prefix + '.json')
        else:
            # Long naming: outerFolder/path/path_date/path_datetime_prefix.ext
            self.dname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring, self.path + "_"+datetimestring + "_" + self.prefix)
            self.fname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring, self.path + "_"+datetimestring + "_" + self.prefix + '.h5')
            self.iname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring, self.path + "_"+datetimestring + "_" + self.prefix + '.png')
            self.cname = os.path.join(self.outerFolder +  self.path, self.path + "_" + datestring, self.path + "_" + datetimestring + "_" + self.prefix + '.json')

    def save_config(self) -> None:
        """
        Save the experiment configuration to JSON file and HDF5 attributes.

        Writes the ``cfg`` dictionary to both a standalone JSON file (at ``cname``)
        and as an attribute in the HDF5 data file.

        .. note::
            Uses :class:`NpEncoder` to handle NumPy types in the configuration.
        """
        if self.cname[-3:] != '.h5':
            with open(self.cname, 'w') as fid:
                json.dump(self.cfg, fid, cls=NpEncoder),
            self.datafile().attrs['config'] = json.dumps(self.cfg, cls=NpEncoder)

    def datafile(
        self,
        group: Optional[str] = None,
        remote: bool = False,
        data_file: Optional[str] = None,
        swmr: bool = False
    ) -> MakeFile:
        """
        Get an HDF5 file handle for data storage.

        Returns a :class:`MakeFile` instance for the experiment's data file,
        opened in append mode.

        :param group: Group path within HDF5 file (currently unused)
        :type group: Optional[str]
        :param remote: Whether to use remote/proxy access (not implemented)
        :type remote: bool
        :param data_file: Override path to data file. If None, uses ``self.fname``
        :type data_file: Optional[str]
        :param swmr: Single Writer Multiple Reader mode (currently unused)
        :type swmr: bool

        :returns: HDF5 file handle opened in append mode
        :rtype: MakeFile

        .. note::
            The ``group``, ``remote``, and ``swmr`` parameters are accepted
            but not currently implemented. Legacy code for these features
            has been commented out.

            Original implementation supported:

            - SWMR mode for concurrent access
            - Group-based file organization
            - Automatic config attribute storage
        """
        if data_file == None:
            data_file = self.fname

        f = MakeFile(data_file, 'a')

        return f

    def go(
        self,
        save: bool = False,
        analyze: bool = False,
        display: bool = False,
        progress: bool = False
    ) -> None:
        """
        Execute the full experiment workflow.

        Runs the experiment through its standard phases: acquire data,
        optionally analyze, optionally save, and optionally display results.

        :param save: If True, save data after acquisition/analysis
        :type save: bool
        :param analyze: If True, run analysis on acquired data
        :type analyze: bool
        :param display: If True, display results after processing
        :type display: bool
        :param progress: If True, show progress during acquisition
        :type progress: bool

        .. note::
            The workflow order is fixed: acquire -> analyze -> save -> display.
            Each step passes its data to the next enabled step.
        """
        # Acquire experimental data
        data = self.acquire(progress)

        # Optional analysis step
        if analyze:
            data = self.analyze(data)

        # Optional save step
        if save:
            self.save_data(data)

        # Optional display step
        if display:
            self.display(data)

    def acquire(
        self,
        progress: bool = False,
        debug: bool = False
    ) -> Any:
        """
        Acquire experimental data.

        This is a placeholder method that should be overridden by subclasses
        to implement actual data acquisition logic.

        :param progress: If True, show progress during acquisition
        :type progress: bool
        :param debug: If True, enable debug output
        :type debug: bool

        :returns: Acquired data (implementation-dependent)
        :rtype: Any

        .. note::
            Subclasses must override this method to implement actual
            data acquisition from hardware.
        """
        pass

    def analyze(
        self,
        data: Optional[Any] = None,
        **kwargs: Any
    ) -> Any:
        """
        Analyze acquired experimental data.

        This is a placeholder method that should be overridden by subclasses
        to implement data analysis logic.

        :param data: Data to analyze, typically from :meth:`acquire`
        :type data: Optional[Any]
        :param kwargs: Additional analysis parameters
        :type kwargs: Any

        :returns: Analyzed data (implementation-dependent)
        :rtype: Any

        .. note::
            Subclasses should override this method to implement
            experiment-specific analysis routines.
        """
        pass

    def display(
        self,
        data: Optional[Any] = None,
        **kwargs: Any
    ) -> Any:
        """
        Display experimental results.

        This is a placeholder method that should be overridden by subclasses
        to implement visualization logic.

        :param data: Data to display, typically from :meth:`acquire` or :meth:`analyze`
        :type data: Optional[Any]
        :param kwargs: Additional display parameters
        :type kwargs: Any

        :returns: Display output (implementation-dependent)
        :rtype: Any

        .. note::
            Subclasses should override this method to implement
            experiment-specific visualization.
        """
        pass

    @classmethod
    def plotter(
        cls,
        plot_widget: Any,
        plots: Any,
        data: Any
    ) -> None:
        """
        Class method for live plotting integration.

        This is a placeholder method that should be overridden by subclasses
        to implement live plotting capabilities.

        :param plot_widget: The widget to plot into (e.g., PyQtGraph or matplotlib)
        :type plot_widget: Any
        :param plots: Plot configuration or existing plot objects
        :type plots: Any
        :param data: Data to plot
        :type data: Any

        .. note::
            This is a classmethod to allow use without instantiating
            the experiment class. Subclasses should override to provide
            experiment-specific live plotting.
        """
        pass

    @classmethod
    def export_data(
        cls,
        data_file: str,
        data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> None:
        """
        Export experiment data to an HDF5 file.

        Exports a dictionary with potentially nested data into an HDF5 file.
        Supports hierarchical storage for nested dictionaries and direct
        key-value pairs.

        :param data_file: Path to the HDF5 file to create
        :type data_file: str
        :param data: Dictionary containing experiment data, may be nested
        :type data: Dict[str, Any]
        :param config: Configuration dictionary (currently unused in implementation)
        :type config: Dict[str, Any]

        .. note::
            The ``config`` parameter is accepted but not used in the current
            implementation. Only ``data`` is exported via ``Helpers.dict_to_h5()``.

        .. seealso::
            :func:`Helpers.dict_to_h5` for the underlying serialization
        """
        # Store the data dictionary with general recursive method
        Helpers.dict_to_h5(data_file, data)

    def save_data(self, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Save experiment data to the instance's HDF5 file.

        :param data: Dictionary of data to save. If None, uses ``self.data``
        :type data: Optional[Dict[str, Any]]

        :raises AttributeError: If ``data`` is None and ``self.data`` doesn't exist

        .. note::
            This method uses :func:`Helpers.dict_to_h5` for recursive dictionary
            serialization, replacing the older simple implementation that only
            handled flat dictionaries.

        .. seealso::
            :meth:`export_data` for class-level data export
            :func:`Helpers.dict_to_h5` for serialization details
        """
        if data is None:
            data = self.data

        # Store the data dictionary with general recursive method
        Helpers.dict_to_h5(self.fname, data)

        # Legacy: Simple flat dictionary implementation (replaced)
        # with self.datafile() as f:
        #     for k, d in data.items():
        #         f.add(k, np.array(d))

    def load_data(self, file_name: str) -> Any:
        """
        Load experiment data from an HDF5 file.

        :param file_name: Path to the HDF5 file to load
        :type file_name: str

        .. seealso::
            :func:`Helpers.h5_to_dict` for deserialization details
        """
        return Helpers.h5_to_dict(file_name)

        # Legacy: Simple flat dictionary implementation (replaced)
        # data={}
        # for k in f.keys():
        #     data[k]=np.array(f[k])
        # data['attrs']=f.get_dict()
        # return data