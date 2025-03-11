import inspect
import numpy as np
from PyQt5.QtCore import qCritical, qInfo
from PyQt5.QtWidgets import (
    QMessageBox
)
import pyqtgraph as pg

from scripts.Init.initialize import BaseConfig
from scripts.CoreLib.Experiment import ExperimentClass

class ExperimentObject():
    def __init__(self, experiment_tab, experiment_name, experiment_module=None):
        if experiment_module is None:
            return

        self.experiment_module = experiment_module
        self.experiment_name = experiment_name
        self.experiment_tab = experiment_tab
        self.experiment_instance = None
        self.experiment_plotting = None

        self.extract_experiment_attributes()


    def extract_experiment_attributes(self):
        """
        From the experiment module of the specific tab, find the correct class to make an instance of.

        TODO: Based on the Experiment Class to-be set.
        """

        # Loop through all members (classes) of the experiment module to find the matching class
        """
        Changes: Instead of searching for a matching name, it looks for the ExperimentClass class, that is the wrapper 
        class. But, the config attribute is given in the direct experiment class, not the wrapper.
        """
        for name, obj, in inspect.getmembers(self.experiment_module):

            if inspect.isclass(obj) and obj.__bases__[0].__name__ == "ExperimentClass" and obj is not ExperimentClass:
                qInfo("Found experiment class: " + name)
                # Store the class reference
                self.experiment_instance = obj

            if name == self.experiment_name:
                if not hasattr(obj, "config_template") or obj.config_template is None:
                    QMessageBox.critical(None, "Error", "No Config Template given.")
                else:
                    qInfo("Found config variable in the class: " + name)
                    new_experiment_config = obj.config_template
                    # Remove overlapping keys from base config
                    for key in new_experiment_config:
                        self.experiment_tab.config["Base Config"].pop(key, None)

                    self.experiment_tab.config["Experiment Config"] = new_experiment_config

        # Verify experiment_instance
        if self.experiment_instance is None:
            qCritical("No Experiment Class instance found within the module give. Must adhere to the experiment " +
                      "class template provided.")
            QMessageBox.critical(None, "Error", "No Experiment Class Found.")