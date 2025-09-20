"""
===================
ExperimentObject.py
===================
Each loaded experiment creates an ExperimentObject instance that extracts modules, important functions (such as
plotting), and stores experiment specific variables (name, path, tab).

Now supports specifying a particular experiment class via experiment_id = (path, class_name)
"""

import inspect
import traceback
from Pyro4 import Proxy
from qick import QickConfig

from PyQt5.QtCore import qCritical, qInfo, qDebug, QThread, QEventLoop
from PyQt5.QtWidgets import QMessageBox

from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
from MasterProject.Client_modules.Desq_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus
from MasterProject.Client_modules.Desq_GUI.scripts.AuxiliaryThread import AuxiliaryThread
import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers


class ExperimentObject:
    """
    Represents a single experiment class extracted from a Python experiment file.

    Attributes:
        * experiment_path (str): Absolute path to the experiment file.
        * experiment_name (str): Name of the experiment class.
        * experiment_class (type): Class reference of the experiment.
        * experiment_plotter (callable): Class method for plotting.
        * experiment_exporter (callable): Class method for exporting data.
        * experiment_hardware_req (list): Hardware requirements (if any).
    """

    def __init__(self, experiment_tab, experiment_id=(None, None)):
        """
        :param experiment_tab: The QDesqTab corresponding to the experiment.
        :param experiment_id: Tuple (path, class_name)
        """
        if experiment_id == (None, None):
            return

        self.experiment_tab = experiment_tab
        self.experiment_path, self.experiment_name = experiment_id

        self.experiment_module = None
        self.experiment_class = None
        self.experiment_type = None
        self.experiment_plotter = None
        self.experiment_exporter = ExperimentClass.export_data
        self.experiment_runtime_estimator = None
        self.experiment_hardware_req = [Proxy, QickConfig]

        self.load_module_and_class()

    def run_import(self, path):
        """
        Import the experiment module safely, blocking problematic imports.
        """
        return Helpers.import_file(str(path), banned_imports=["socProxy"])

    def failed_import_error(self, e, timeout=False):
        if timeout:
            qCritical("Timeout: Experiment loading took too long. Likely blocked socProxy import.")
            QMessageBox.critical(None, "Timeout Error",
                                 "Experiment loading took too long (>4s). Possibly failing socProxy import.")
        else:
            qCritical(f"Error loading experiment: {str(e)}")
            QMessageBox.critical(None, "Error", f"Error loading experiment. See log or terminal.")
        qCritical(traceback.format_exc())

    def find_attribute(self, obj, attr_name):
        if hasattr(obj, attr_name):
            qInfo(f"Found experiment's {attr_name}.")
            return getattr(obj, attr_name)
        qDebug(f"No {attr_name} found in this experiment class.")
        return None

    def find_config(self, obj):
        """
        Extract the config_template from the experiment class if it exists.
        """
        if hasattr(obj, "config_template") and obj.config_template is not None:
            qInfo(f"Found config_template in {self.experiment_name}.")
            new_config = obj.config_template.copy()

            # Merge into tab config
            base_config = self.experiment_tab.config.get("Base Config", {})
            overlap_keys = [k for k in new_config if k in base_config]
            for key in overlap_keys:
                base_config[key] = new_config.pop(key)

            self.experiment_tab.config["Experiment Config"] = new_config
            return True
        return False

    def save_import(self, experiment_module):
        self.experiment_module = experiment_module

    def load_module_and_class(self):
        """
        Imports the module and extracts only the specified class and its attributes.
        """
        # Use auxiliary thread to prevent GUI freezing
        self.aux_thread = QThread()
        self.aux_worker = AuxiliaryThread(
            target_func=self.run_import,
            func_kwargs={"path": self.experiment_path},
            timeout=4
        )
        self.aux_worker.moveToThread(self.aux_thread)

        # Thread signal connections
        self.aux_thread.started.connect(self.aux_worker.run)
        self.aux_worker.finished.connect(self.aux_thread.quit)
        self.aux_worker.finished.connect(self.aux_worker.deleteLater)
        self.aux_thread.finished.connect(self.aux_thread.deleteLater)
        self.aux_worker.error_signal.connect(lambda err: self.failed_import_error(err))
        self.aux_worker.timeout_signal.connect(lambda err: self.failed_import_error(err, timeout=True))
        self.aux_worker.result_signal.connect(lambda result: self.save_import(result[0]))

        loop = QEventLoop()
        self.aux_thread.finished.connect(loop.quit)
        self.aux_thread.start()
        loop.exec_()

        if self.experiment_module is not None:
            self.extract_class_attributes()

    def extract_class_attributes(self):
        """
        Extracts attributes from the specified experiment class only.
        """
        try:
            obj = getattr(self.experiment_module, self.experiment_name)
        except AttributeError:
            qCritical(f"Experiment class {self.experiment_name} not found in module.")
            QMessageBox.critical(None, "Error", f"Experiment class {self.experiment_name} not found.")
            return

        # Determine type
        bases = [b.__name__ for b in obj.__mro__[1:]]
        if "ExperimentClassPlus" in bases:
            self.experiment_type = ExperimentClassPlus
            self.experiment_hardware_req = self.find_attribute(obj, "hardware_requirement") or self.experiment_hardware_req
        elif "ExperimentClass" in bases:
            self.experiment_type = ExperimentClass
        else:
            qCritical(f"{self.experiment_name} does not inherit from ExperimentClass or ExperimentClassPlus.")
            QMessageBox.critical(None, "Error", f"{self.experiment_name} must inherit from ExperimentClass or ExperimentClassPlus.")
            return

        qInfo(f"Loaded {self.experiment_type.__name__} class: {self.experiment_name}")

        # Save class reference and important methods
        self.experiment_class = obj
        self.experiment_plotter = self.find_attribute(obj, "plotter")
        self.experiment_exporter = self.find_attribute(obj, "export_data") or self.experiment_exporter
        self.experiment_runtime_estimator = self.find_attribute(obj, "estimate_runtime")

        # Extract config
        self.find_config(obj)

        # Ensure "sets" exists
        exp_config = self.experiment_tab.config.setdefault("Experiment Config", {})
        if "sets" not in exp_config:
            exp_config["sets"] = 1
