"""
===================
ExperimentObject.py
===================
Each loaded experiment creates an ExperimentObject instance that extracts modules, important functions (such as
plotting), and stores experiment specific variables (name, path, tab).

How an experiment file should be written is defined in the Experiment Hub of documentation.
"""

import inspect
import ast
import traceback
from Pyro4 import Proxy
from qick import QickConfig
import concurrent.futures
import threading

from PyQt5.QtCore import (
    qCritical, qInfo, qDebug, QThread, QEventLoop
)
from PyQt5.QtWidgets import (
    QMessageBox
)

from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus
from scripts.AuxiliaryThread import AuxiliaryThread
import scripts.Helpers as Helpers

class ExperimentObject():
    """
    An ExperimentObject class that represents an experiment by extracting information from the python experiment file.

    **Important Attributes:**

        * experiment_path (str): The absolute path to the experiment file.
        * experiment_class (Class): The class of the custom experiment that is a subclass of ExperimentClass.
        * experiment_plotter (Callable): A callable @classmethod of the experiment_class that handles plotting.
        * experiment_exporter (Callable): A callable @classmethod of the experiment_class that handles data exporting.
        * experiment_hardware_req (list): A list containing the hardware requirements for a T2 experiment.
    """

    def __init__(self, experiment_tab, experiment_name, experiment_path=None):
        """
        Initializes an ExperimentObject given the corresponding parameters.

        :param experiment_tab: The QQuarkTab corresponding to the experiment.
        :type experiment_tab: QQuarkTab
        :param experiment_name: The name of the experiment.
        :type experiment_name: str
        :param experiment_path: The absolute path to the experiment file.
        :type experiment_path: str
        """

        if experiment_path is None:
            return None

        self.experiment_path = experiment_path
        self.experiment_name = experiment_name
        self.experiment_tab = experiment_tab
        self.experiment_class = None
        self.experiment_plotter = None
        self.experiment_runtime_estimator = None
        self.experiment_exporter = ExperimentClass.export_data
        self.experiment_type = None # ExperimentClass, or ExperimentClassPlus
        self.experiment_hardware_req = [Proxy, QickConfig]
        self.experiment_module = None

        self.extract_experiment_attributes()

    def run_import(self, path):
        """
        A Helper function to run imports to be used with concurrent threader.

        :param path: The absolute path to the experiment file.
        :type path: str
        """
        mod, name = Helpers.import_file(str(path))
        return mod, name

    def find_attribute(self, obj, attribute_name):
        """
        Given an arbitrary object, find if the appropriate attribute exists and return it.

        :param obj: The  object to search
        :type obj: any
        :param attribute_name: The name of the attribute to search for.
        :type attribute_name: str

        :return: The attribute value if found, else None
        :rtype: any
        """

        if hasattr(obj, attribute_name):
            qInfo("Found experiment's " + str(attribute_name) + ".")
            return getattr(obj, attribute_name)
        else:
            qDebug("This experiment class doesn't have a " + str(attribute_name) + ".")
            return None

    def find_config(self, obj, name):
        """
        Given an object, find if the config attribute exists, and process it appropriately.

        :param obj: The object to search
        :type obj: any
        :param name: The name of the object.
        :type name: str

        :return: True if config value is found, else False
        :rtype: bool
        """

        if hasattr(obj, "config_template") and obj.config_template is not None:
            qInfo("Found config variable in the class: " + name)

            # Process config
            new_experiment_config = obj.config_template
            # Remove overlapping keys from base config after updating Base Config
            keys_to_remove = []
            for key in new_experiment_config:
                if key in self.experiment_tab.config["Base Config"]:
                    self.experiment_tab.config["Base Config"][key] = new_experiment_config[key]
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                new_experiment_config.pop(key, None)

            self.experiment_tab.config["Experiment Config"] = new_experiment_config

            return True
        return False

    def failed_import_error(self, e, timeout=False):
        """
        Function to handle a failed import error (used by aux thread).

        :param e: Error message
        :type e: str
        :param timeout: Whether there was a timeout error
        :type timeout: bool
        """

        if timeout:
            qCritical(
                "Timeout: Experiment loading took too long. Likely error is a socProxy import with a failing IP "
                "address somewhere in import modules")
            QMessageBox.critical(None, "Timeout Error",
                                 "Experiment loading took too long (>2s). Possible failing socProxy import. "
                                 "Extracting will continue to execute in the background until error.")
        else:
            if isinstance(e, ImportError):
                qCritical("Import Error: " + str(e))
                QMessageBox.critical(None, "Import Error",
                                     f"Import Error Loading Experiment. See log or terminal for details.")
            else:
                qCritical("Error loading experiment file: " + str(e))
                QMessageBox.critical(None, "Error", f"Error loading Experiment. See log or terminal for details.")
            qCritical(traceback.format_exc())

    def save_import(self, experiment_module, experiment_name):
        """
        Helper function for saving the import returned from a run_import call.

        :param experiment_module: The experiment module
        :type experiment_module: module
        :param experiment_name: The name of the experiment.
        :type experiment_name: str
        """

        self.experiment_module, self.experiment_name = experiment_module, experiment_name

    def extract_experiment_attributes(self):
        """
        Extracts all important experiment attributes from the specified experiment_path. It does so by generating a
        module for the python experiment file, retrieving all members, and iterating through them to find the subclass
        of ExperimentClass (that is the wrapper class). Then it saves the class for the main module to make an instance
        of when running an  experiment. It also searches for any important @classmethods such as the Plotter.

        Currently, the config resides in a different class that matches the experiment file name, usually a
        subclass of a qick averager program. Moving it to the wrapper class somehow would allow for the search to be
        more efficient.
        """

        # Using a separate thread to import module in case of import errors that may freeze the GUI

        self.aux_thread = QThread()
        self.aux_worker = AuxiliaryThread(target_func=self.run_import, func_kwargs={"path": self.experiment_path}, timeout=2)
        self.aux_worker.moveToThread(self.aux_thread)

        # Connecting started and finished signals
        self.aux_thread.started.connect(self.aux_worker.run)  # run function
        self.aux_worker.finished.connect(self.aux_thread.quit)  # stop thread
        self.aux_worker.finished.connect(self.aux_worker.deleteLater)  # delete worker
        self.aux_thread.finished.connect(self.aux_thread.deleteLater)  # delete thread

        # Connecting data related slots
        self.aux_worker.error_signal.connect(lambda err: self.failed_import_error(err, timeout=False))
        self.aux_worker.result_signal.connect(lambda result: self.save_import(result[0], result[1]))
        self.aux_worker.timeout_signal.connect(lambda err: self.failed_import_error(err, timeout=True))


        # Create a local event loop to wait until thread complete
        loop = QEventLoop()
        self.aux_thread.finished.connect(loop.quit)

        self.aux_thread.start()
        loop.exec_()

        if self.experiment_module is not None:
            self.search_experiment_attributes()


    def search_experiment_attributes(self):
        """
        Searches self.experiment_module for the necessary attributes to run an experiment.

        Attributes:
            * experiment_type
            * experiment_hardware_req
            * experiment_class
            * experiment_exporter
            * experiment_plotter
            * experiment_runtime_estimator
            * config
        """

        # Loop through all members (classes) of the experiment module to find the matching class

        # Changes: Instead of searching for a matching name, it looks for the ExperimentClass class, that is the wrapper
        # class. But, the config attribute is given in the direct experiment class, not the wrapper.

        cfg_found = False
        for name, obj, in inspect.getmembers(self.experiment_module):

            # Cannot use issubclass because inheriting from different ExperimentClass files, but can match string.
            # If the object is a subclass of {*} but not the class itself
            if inspect.isclass(obj) and any(base.__name__ in {"ExperimentClass", "ExperimentClassPlus"}
                                            for base in obj.__mro__[1:]):

                ### Extract the class type (either ExperimentClass or ExperimentClassPlus)
                if any(base.__name__ == "ExperimentClassPlus" for base in obj.__mro__[1:]):
                    self.experiment_type = ExperimentClassPlus
                    ### Store the hardware_requirement if given (only in T2 experiments)
                    self.experiment_hardware_req = self.find_attribute(obj, "hardware_requirement") or \
                                               self.experiment_hardware_req
                else:
                    self.experiment_type = ExperimentClass
                qInfo("Found " + str(self.experiment_type.__name__) + " class: " + name)

                ### Store the class reference
                self.experiment_class = obj
                ### Store the class's export_data function
                self.experiment_exporter = self.find_attribute(obj, "export_data") or \
                                           self.experiment_exporter
                ### Store the class's plotter function
                self.experiment_plotter = self.find_attribute(obj, "plotter")
                ### Store the class's runtime estimator/predictor function
                self.experiment_runtime_estimator = self.find_attribute(obj, "estimate_runtime")


                ### Store the classes config if given
                cfg_found = self.find_config(obj, name)


            ### If config not found yet, Look for config in program classes
            if not cfg_found and name == self.experiment_name:
                cfg_found = self.find_config(obj, name)

        # Add sets if missing
        if ("sets" not in self.experiment_tab.config["Base Config"] and
                "sets" not in self.experiment_tab.config["Experiment Config"]):
            self.experiment_tab.config["Experiment Config"]["sets"] = 1

        # Verify experiment_instance
        if self.experiment_class is None:
            qCritical("No valid Class found within the module given. Must adhere to the experiment guidelines.")
            QMessageBox.critical(None, "Error", "No ExperimentClass or ExperimentClassPlus Found.")
