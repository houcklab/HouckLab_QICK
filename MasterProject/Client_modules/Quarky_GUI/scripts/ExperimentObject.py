"""
===================
ExperimentObject.py
===================
Each loaded experiment creates an ExperimentObject instance that extracts modules, important functions (such as
plotting), and stores experiment specific variables (name, path, tab).

How an experiment file should be written is defined in the Experiment Hub of documentation.
"""

import inspect

from Pyro4 import Proxy
from qick import QickConfig

from PyQt5.QtCore import qCritical, qInfo, qDebug
from PyQt5.QtWidgets import (
    QMessageBox
)

from MasterProject.Client_modules.Init.initialize import BaseConfig
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentT2 import ExperimentClassT2
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
        self.experiment_exporter = ExperimentClass.export_data
        self.experiment_type = None # ExperimentClass, or ExperimentClassT2
        self.experiment_hardware_req = [Proxy, QickConfig]

        self.extract_experiment_attributes()


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

        # Loop through all members (classes) of the experiment module to find the matching class

        # Changes: Instead of searching for a matching name, it looks for the ExperimentClass class, that is the wrapper
        # class. But, the config attribute is given in the direct experiment class, not the wrapper.

        experiment_module, experiment_name = Helpers.import_file(str(self.experiment_path)) # gets experiment object from file
        # print(inspect.getsourcelines(experiment_module))

        cfg_found = False
        for name, obj, in inspect.getmembers(experiment_module):

            # Cannot to issubclass as of now because inheriting from different ExperimentClass files.
            if ((inspect.isclass(obj) and obj.__bases__[0] == ExperimentClass and obj is not ExperimentClass)
                    or
                    (inspect.isclass(obj) and obj.__bases__[0] == ExperimentClassT2 and obj is not ExperimentClassT2)):

                ### Extract the class type (either ExperimentClass or ExperimentClassT2)
                if inspect.isclass(obj) and obj.__bases__[0] == ExperimentClass:
                    self.experiment_type = ExperimentClass
                else:
                    self.experiment_type = ExperimentClassT2

                    ### Store the hardware_requirement if given (only in T2 experiments)
                    if hasattr(obj, "hardware_requirement") and obj.hardware_requirement is not None:
                        qInfo("Found experiment hardware requirements.")
                        self.experiment_hardware_req = getattr(obj, "hardware_requirement")
                    else:
                        qDebug("This experiment class does not have a hardware_requirement list.")


                qInfo("Found " + str(self.experiment_type.__name__) + " class: " + name)

                ### Store the class reference
                self.experiment_class = obj

                ### Store the class's export_data function
                if hasattr(obj, "export_data") and callable(getattr(obj, "export_data")):
                    qInfo("Found experiment data exporter.")
                    self.experiment_exporter = getattr(obj, "export_data")
                else:
                    qDebug("This experiment class doesn't have a custom exporter, using default.")

                ### Store the class's plotter function
                if hasattr(obj, "plotter") and callable(getattr(obj, "plotter")):
                    qInfo("Found experiment plotter.")
                    self.experiment_plotter = getattr(obj, "plotter")
                else:
                    qDebug("This experiment class does not have a plotter function.")

                ### Store the classes config if given
                if hasattr(obj, "config_template") and obj.config_template is not None:
                    cfg_found = True

                    qInfo("Found config variable in the class: " + name)
                    new_experiment_config = obj.config_template
                    # Remove overlapping keys from base config
                    for key in new_experiment_config:
                        self.experiment_tab.config["Base Config"].pop(key, None)

                    self.experiment_tab.config = self.experiment_tab.config | new_experiment_config


            ### If config not found yet, Look for config in program classes
            if not cfg_found and name == self.experiment_name:
                if not hasattr(obj, "config_template") or obj.config_template is None:
                    QMessageBox.critical(None, "Error", "No Config Template given.")
                else:
                    qInfo("Found config variable in the class: " + name)
                    new_experiment_config = obj.config_template
                    # Remove overlapping keys from base config
                    for key in new_experiment_config:
                        self.experiment_tab.config["Base Config"].pop(key, None)

                    self.experiment_tab.config = self.experiment_tab.config | new_experiment_config

        # Verify experiment_instance
        if self.experiment_class is None:
            qCritical("No valid Class found within the module given. Must adhere to the experiment guidelines.")
            QMessageBox.critical(None, "Error", "No ExperimentClass or ExperimentClassT2 Found.")