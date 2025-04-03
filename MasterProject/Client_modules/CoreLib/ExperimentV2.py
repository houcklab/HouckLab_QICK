import os
import json
import numpy as np
import h5py
import datetime
from pathlib import Path

import MasterProject.Client_modules.Quarky_GUI.scripts.Helpers as Helpers

class ExperimentClassV2:
    """
    The Base class for all experiments
    """

    hardware_keywords = ["RFSoC", "VoltageInterface", "ReadoutFilter"]

    def __init__(self, path='', outerFolder='', prefix='data',
                 hardware=None, hardware_requirement=None,
                 cfg = None, config_file=None, **kwargs):
        """
        Initializes experiment class.

        :param path: Relative path to the data/config folder of the experiment
        :type path: str
        :param outerFolder: Absolute path to the relative path of current experiment location
        :type outerFolder: str
        :param prefix: The prefix to use when creating data files
        :type prefix: str
        :param hardware: A dictionary of the required hardware
        :type hardware: dict
        :param hardware_requirement: A list of the required hardware
        :type hardware_requirement: list
        :param cfg: Configuration dictionary of the experiment
        :type cfg: dict
        :param config_file: Name of the configuration file, total path should be os.path.join(path, config_file)
        :type config_file: str
        :param kwargs: Keyword arguments updated to class dict
        :type kwargs: dict
        """
        self.__dict__.update(kwargs)

        # Loading all parameters
        self.path = path
        self.outerFolder = outerFolder
        self.prefix = prefix

        # Handling Config
        if cfg is None and config_file is None:
            raise ValueError("Missing both a config dictionary or filepath to a config, must supply at least one.")
        elif cfg is None:
            self.load_config(os.path.join(path, config_file))
        else:
            self.cfg = cfg

        # Handling hardware
        self.hardware = hardware
        self.hardware_requirement = hardware_requirement
        self.handle_hardware()

        # File Naming Conventions
        datetimenow = datetime.datetime.now()
        datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
        datestring = datetimenow.strftime("%Y_%m_%d")
        DataFolderBool = Path(self.outerFolder + self.path).is_dir()
        if DataFolderBool == False:
            os.mkdir(self.outerFolder + self.path)
        DataSubFolderBool = Path(os.path.join(self.outerFolder + self.path, self.path + "_" + datestring)).is_dir()
        if DataSubFolderBool == False:
            os.mkdir(os.path.join(self.outerFolder + self.path, self.path + "_" + datestring))

        self.fname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring,
                                  self.path + "_" + datetimestring + "_" + self.prefix + '.h5')
        self.iname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring,
                                  self.path + "_" + datetimestring + "_" + self.prefix + '.png')
        self.cname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring,
                                  self.path + "_" + datetimestring + "_" + self.prefix + '.json')

    def go(self, save=False, analyze=False, display=False, progress=False):
        # get data

        data=self.acquire(progress)
        if analyze:
            data=self.analyze(data)
        if save:
            self.save_data(data)
        if display:
            self.display(data)

    def acquire(self, progress=False, debug=False):
        pass

    def analyze(self, data=None, **kwargs):
        pass

    def display(self, data=None, **kwargs):
        pass

    def handle_hardware(self):
        for item in self.hardware_requirement:
            if item not in self.hardware_keywords:
                raise ValueError(f"Missing key: {item}")
                break
        else:
            print("All hardware items provided")

    @classmethod
    def plotter(cls, plot_widget, plots, data):
        """
        [QUARKY GUI FUNCTION]
        Specifies a plotting function to use for display on the Quarky GUI.

        :param plot_widget: A GraphicsLayoutWidget instance that plots are appended to
        :type plot_widget: GraphicsLayoutWidget
        :param plots: A reference to a list of all the plots
        :type plots: list
        :param data: Data to be plotted
        :type data: list
        """
        pass

    @classmethod
    def export_data(cls, data_filename, data, config):
        """
        [QUARKY GUI FUNCTION]
        Exports a dictionary with nested data into an HDF5 file.
        Supports hierarchical storage for nested dictionaries and direct key-value pairs.

        :param data_file: A path to the dataset file that is to be created
        :type data_file: str
        :param data: The data dictionary
        :type data: dict
        :param config: The config dictionary
        :type config: dict
        """

        # Store the data dictionary
        Helpers.dict_to_h5(data_filename, data)

    def load_config(self, config_file):
        """
        Loads the config from the provided config_file. Can handle h5 or JSON files.

        :param config_file: relative path to config file
        :type config_file: str
        """
        if config_file is None:
            raise ValueError("Missing a config file path.")
            return
        try:
            if config_file[-3:].lower() == '.h5':
                metadata = Helpers.extract_metadata(config_file)
                if "config" in metadata:
                    self.cfg = metadata["config"]
                else:
                    raise ValueError("No Config provided in the h5's metadata.")
            elif config_file[-5:].lower() =='.json':
                with open(config_file, "r") as json_file:
                    self.cfg = json.load(json_file)
            else:
                raise TypeError("Invalid config file type - must be h5 or JSON.")

        except Exception as e:
            raise RuntimeError("Could not load the config file.")

    def save_config(self):
        """
        Saves the current configuration to a json file via cname.
        """
        try:
            with open(self.cname, "w") as json_file:
                json.dump(self.config, json_file, indent=4)
        except Exception as e:
            raise RuntimeError("Could not save the config file to cname.")

    def save_data(self, data=None):
        """
        Saves the data to fname h5 via the dict_to_h5 Helper function.

        :param data: The data dictionary [Optional]
        :type data: dict
        """
        if data is None:
            data=self.data

        Helpers.dict_to_h5(self.fname, data)

    def load_data(self, f):
        """
        Loads the data from given filepath f to an h5 via the h5_to_dict Helper function.

        :param f: filepath
        :type f: str
        """
        data = Helpers.h5_to_dict(f)
        return data

class NpEncoder(json.JSONEncoder):
    """ Ensure json dump can handle np arrays """
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)