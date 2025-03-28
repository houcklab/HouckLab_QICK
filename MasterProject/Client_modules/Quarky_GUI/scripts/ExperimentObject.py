"""
===================
ExperimentObject.py
===================
Each loaded experiment creates an ExperimentObject instance that extracts modules, important functions (such as
plotting), and stores experiment specific variables (name, path, tab).

How an experiment file should be written is defined in the Experiment Hub of documentation.
"""

import inspect
import numpy as np
from PyQt5.QtCore import qCritical, qInfo, qDebug
from PyQt5.QtWidgets import (
    QMessageBox
)
import pyqtgraph as pg

from scripts.Init.initialize import BaseConfig
from scripts.CoreLib.Experiment import ExperimentClass
import scripts.Helpers as Helpers

class ExperimentObject():
    """
    An ExperimentObject class that represents an experiment by extracting information from the python experiment file.

    **Important Attributes:**

        * experiment_path (str): The absolute path to the experiment file.
        * experiment_class (Class): The class of the custom experiment that is a subclass of ExperimentClass.
        * experiment_plotter (Callable): A callable @classmethod of the experiment_class that handles plotting.
        * experiment_exporter (Callable): A callable @classmethod of the experiment_class that handles data exporting.
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
        self.experiment_exporter = None

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

        for name, obj, in inspect.getmembers(experiment_module):

            # Cannot to issubclass as of now because inheriting from different ExperimentClass files.
            if inspect.isclass(obj) and obj.__bases__[0].__name__ == "ExperimentClass" and obj is not ExperimentClass:
                qInfo("Found experiment class: " + name)
                # Store the class reference
                self.experiment_class = obj

                # Store the class's export_data function
                if hasattr(obj, "export_data") and callable(getattr(obj, "export_data")):
                    qInfo("Found experiment data exporter.")
                    self.experiment_exporter = getattr(obj, "export_data")
                else:
                    qDebug("This experiment class does not have a data exporter.")

                # Store the class's plotter function
                if hasattr(obj, "plotter") and callable(getattr(obj, "plotter")):
                    qInfo("Found experiment plotter.")
                    self.experiment_plotter = getattr(obj, "plotter")
                else:
                    qDebug("This experiment class does not have a plotter function.")

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
        if self.experiment_class is None:
            qCritical("No Experiment Class instance found within the module give. Must adhere to the experiment " +
                      "class template provided.")
            QMessageBox.critical(None, "Error", "No Experiment Class Found.")