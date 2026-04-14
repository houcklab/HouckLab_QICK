"""
===================
ExperimentObject.py
===================

Container class for loaded experiment instances within the Desq GUI.

This module provides the :class:`ExperimentObject` class, which wraps a loaded
experiment class and manages its associated metadata, configuration, and
lifecycle within a GUI tab.

Each loaded experiment creates an ``ExperimentObject`` instance that:

- Extracts the experiment module and class via safe import mechanisms
- Discovers and stores important class attributes (exporter, runtime estimator)
- Manages hardware requirements for experiment execution
- Synchronizes configuration templates with the GUI config panel

Architecture Notes
------------------
The experiment loading process uses an auxiliary thread with timeout protection
to prevent GUI freezes from blocking imports (e.g., failed ``socProxy`` imports).
Experiments are identified by a tuple of ``(path, class_name)`` to support
files containing multiple experiment class definitions.

Simplified Version
------------------
This version removes the ``experiment_plotter`` attribute and related logic.
Experiments now use a ``display()`` method for plotting, which integrates with
the ``BackendDesq`` plot interception system.

.. seealso::
    - :mod:`ExperimentLoader` for module loading utilities
    - :mod:`AuxiliaryThread` for threaded import execution
    - :mod:`Helpers` for safe import mechanisms
    - :class:`ExperimentClass` for the base experiment interface
"""

from __future__ import annotations

import inspect
import traceback
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple, Type

from Pyro4 import Proxy
from qick import QickConfig

from PyQt5.QtCore import qCritical, qInfo, qDebug, QThread, QEventLoop
from PyQt5.QtWidgets import QMessageBox

from MasterProject.Client_modules.Desq_GUI.CoreLib.Experiment import ExperimentClass
from MasterProject.Client_modules.Desq_GUI.scripts.AuxiliaryThread import AuxiliaryThread
import MasterProject.Client_modules.Desq_GUI.scripts.Helpers as Helpers

if TYPE_CHECKING:
    from MasterProject.Client_modules.Desq_GUI.scripts.DesqTab import QDesqTab


class ExperimentObject:
    """
    Represents a single experiment class extracted from a Python experiment file.

    This class serves as a container that wraps an experiment class definition
    and manages its integration with the Desq GUI. It handles:

    - Safe module import with timeout protection and blocked imports
    - Extraction of class attributes (exporter, runtime estimator, config)
    - Hardware requirement specification
    - Configuration template synchronization with the GUI

    :param experiment_tab: The QDesqTab widget corresponding to this experiment.
        Provides access to the config panel and other tab-specific resources.
    :type experiment_tab: QDesqTab
    :param experiment_id: Tuple of (file_path, class_name) identifying the
        specific experiment class to load. Defaults to (None, None) for
        empty initialization.
    :type experiment_id: tuple[str | None, str | None]

    :ivar experiment_tab: Reference to the parent GUI tab widget.
    :vartype experiment_tab: QDesqTab
    :ivar experiment_path: Absolute path to the experiment Python file.
    :vartype experiment_path: str | None
    :ivar experiment_name: Name of the experiment class within the module.
    :vartype experiment_name: str | None
    :ivar experiment_module: The loaded Python module object.
    :vartype experiment_module: ModuleType | None
    :ivar experiment_class: Reference to the experiment class object.
    :vartype experiment_class: type | None
    :ivar experiment_type: Base type of the experiment (typically ExperimentClass).
    :vartype experiment_type: type | None
    :ivar experiment_exporter: Method for exporting experiment data.
    :vartype experiment_exporter: Callable
    :ivar experiment_runtime_estimator: Method for estimating experiment runtime, if available.
    :vartype experiment_runtime_estimator: Callable | None
    :ivar experiment_hardware_req: List of required hardware types for execution.
    :vartype experiment_hardware_req: list[type]

    .. note::
        If ``experiment_id`` is ``(None, None)``, the constructor returns early
        without loading anything. This allows creating placeholder instances.

    .. warning::
        The import process runs in an auxiliary thread with a 4-second timeout.
        Experiments that hang during import (e.g., due to failed hardware connections)
        will trigger a timeout error dialog.

    Example
    -------
    ::

        # Load a specific experiment class from a file
        exp_obj = ExperimentObject(
            experiment_tab=my_tab,
            experiment_id=("/path/to/experiments.py", "MyRabiExperiment")
        )

        # Access the loaded class
        if exp_obj.experiment_class is not None:
            instance = exp_obj.experiment_class(config)
    """

    def __init__(
        self,
        experiment_tab: QDesqTab,
        experiment_id: Tuple[Optional[str], Optional[str]] = (None, None)
    ) -> None:
        """
        Initialize the ExperimentObject and load the specified experiment class.

        :param experiment_tab: The GUI tab widget that will host this experiment.
        :type experiment_tab: QDesqTab
        :param experiment_id: Tuple of (path, class_name) identifying the experiment.
        :type experiment_id: tuple[str | None, str | None]
        """
        # Early return for empty/placeholder initialization
        if experiment_id == (None, None):
            return

        self.experiment_tab: QDesqTab = experiment_tab
        self.experiment_path: Optional[str]
        self.experiment_name: Optional[str]
        self.experiment_path, self.experiment_name = experiment_id

        # Module and class references (populated by load_module_and_class)
        self.experiment_module: Optional[ModuleType] = None
        self.experiment_class: Optional[type] = None
        self.experiment_type: Optional[type] = None

        # Default exporter from base class; may be overridden if class defines its own
        self.experiment_exporter: Callable[..., Any] = ExperimentClass.export_data
        self.experiment_runtime_estimator: Optional[Callable[..., float]] = None

        # Default hardware requirements; may be overridden by class attribute
        self.experiment_hardware_req: List[type] = [Proxy, QickConfig]

        # Trigger the async module loading process
        self.load_module_and_class()

    def run_import(self, path: str) -> Tuple[Optional[ModuleType], Optional[str]]:
        """
        Import the experiment module safely, blocking problematic imports.

        This method is executed in an auxiliary thread to prevent GUI freezes
        during potentially slow or blocking import operations.

        :param path: Absolute path to the Python file to import.
        :type path: str

        :returns: Tuple of (module, module_name) from the import helper.
        :rtype: tuple[ModuleType | None, str | None]

        .. note::
            The ``socProxy`` import is blocked by default to prevent hangs
            when the hardware proxy server is unavailable.

        .. seealso::
            :func:`Helpers.import_file` for the underlying import mechanism.
        """
        return Helpers.import_file(str(path), banned_imports=["socProxy"])

    def failed_import_error(self, e: Exception, timeout: bool = False) -> None:
        """
        Handle and display errors from failed experiment imports.

        Shows an appropriate error dialog based on whether the failure was
        due to a timeout or another exception.

        :param e: The exception that caused the import failure.
        :type e: Exception
        :param timeout: If True, the failure was due to import timeout
            (likely a blocked socProxy import).
        :type timeout: bool
        """
        if timeout:
            qCritical("Timeout: Experiment loading took too long. Likely blocked socProxy import.")
            QMessageBox.critical(
                None,
                "Timeout Error",
                "Experiment loading took too long (>4s). Possibly failing socProxy import."
            )
        else:
            qCritical(f"Error loading experiment: {str(e)}")
            QMessageBox.critical(
                None,
                "Error",
                f"Error loading experiment. See log or terminal."
            )
        qCritical(traceback.format_exc())

    def find_attribute(self, obj: type, attr_name: str) -> Optional[Any]:
        """
        Safely retrieve an attribute from an experiment class if it exists.

        :param obj: The class object to search for the attribute.
        :type obj: type
        :param attr_name: Name of the attribute to find.
        :type attr_name: str

        :returns: The attribute value if found, None otherwise.
        :rtype: Any | None
        """
        if hasattr(obj, attr_name):
            qInfo(f"Found experiment's {attr_name}.")
            return getattr(obj, attr_name)
        qDebug(f"No {attr_name} found in this experiment class.")
        return None

    def find_config(self, obj: type) -> bool:
        """
        Extract and apply the config_template from the experiment class.

        If the experiment class defines a ``config_template`` attribute,
        copies it and updates the GUI's config panel with the template values.

        :param obj: The experiment class to extract config from.
        :type obj: type

        :returns: True if a config_template was found and applied, False otherwise.
        :rtype: bool

        .. note::
            The config template is **copied** before use to avoid modifying
            the class-level template.
        """
        if hasattr(obj, "config_template") and obj.config_template is not None:
            qInfo(f"Found config_template in {self.experiment_name}.")
            new_config = obj.config_template.copy()

            # Update the GUI config panel with the extracted template
            self.experiment_tab.experiment_config_panel.update_config_dict(new_config)
            return True
        return False

    def save_import(self, experiment_module: Optional[ModuleType]) -> None:
        """
        Store the successfully imported module reference.

        This callback is connected to the auxiliary thread's result signal.

        :param experiment_module: The imported module object, or None if import failed.
        :type experiment_module: ModuleType | None
        """
        self.experiment_module = experiment_module

    def load_module_and_class(self) -> None:
        """
        Import the module and extract the specified experiment class and its attributes.

        This method orchestrates the asynchronous import process:

        1. Creates an auxiliary thread with 4-second timeout
        2. Connects signals for success, error, and timeout handling
        3. Runs an event loop to wait for completion without blocking the GUI
        4. Extracts class attributes if import succeeded

        The auxiliary thread mechanism prevents the GUI from freezing when
        imports take a long time (e.g., due to network operations or failed
        hardware connections).

        .. note::
            The QEventLoop is used to block this method until the import
            completes, while still allowing Qt event processing to continue.
            This keeps the GUI responsive during the import.

        :raises: No exceptions raised; errors are displayed via message boxes.
        """
        # Create auxiliary thread for non-blocking import
        self.aux_thread: QThread = QThread()
        self.aux_worker: AuxiliaryThread = AuxiliaryThread(
            target_func=self.run_import,
            func_kwargs={"path": self.experiment_path},
            timeout=4  # 4-second timeout for import operations
        )
        self.aux_worker.moveToThread(self.aux_thread)

        # Connect thread lifecycle signals
        self.aux_thread.started.connect(self.aux_worker.run)
        self.aux_worker.finished.connect(self.aux_thread.quit)
        self.aux_worker.finished.connect(self.aux_worker.deleteLater)
        self.aux_thread.finished.connect(self.aux_thread.deleteLater)

        # Connect result/error handlers
        self.aux_worker.error_signal.connect(lambda err: self.failed_import_error(err))
        self.aux_worker.timeout_signal.connect(lambda err: self.failed_import_error(err, timeout=True))
        self.aux_worker.result_signal.connect(lambda result: self.save_import(result[0]))

        # Run event loop to wait for thread completion while keeping GUI responsive
        loop = QEventLoop()
        self.aux_thread.finished.connect(loop.quit)
        self.aux_thread.start()
        loop.exec_()

        # Extract class attributes if module was loaded successfully
        if self.experiment_module is not None:
            self.extract_class_attributes()

    def extract_class_attributes(self) -> None:
        """
        Extract and store attributes from the specified experiment class.

        This method:

        1. Retrieves the named class from the loaded module
        2. Validates that it inherits from ExperimentClass
        3. Extracts hardware requirements, exporter, and runtime estimator
        4. Applies any config template to the GUI
        5. Ensures a "sets" key exists in the config

        :raises: No exceptions raised; errors are displayed via message boxes.

        .. note::
            The base class check uses string matching on ``__mro__`` names
            rather than ``issubclass()`` to handle cases where different
            modules define their own ``ExperimentClass`` versions.
        """
        # Attempt to retrieve the named class from the module
        try:
            obj: type = getattr(self.experiment_module, self.experiment_name)
        except AttributeError:
            qCritical(f"Experiment class {self.experiment_name} not found in module.")
            QMessageBox.critical(
                None,
                "Error",
                f"Experiment class {self.experiment_name} not found."
            )
            return

        # Validate inheritance by checking base class names in method resolution order
        bases: List[str] = [b.__name__ for b in obj.__mro__[1:]]
        if "ExperimentClass" in bases:
            self.experiment_type = ExperimentClass
            # Override default hardware requirements if class specifies them
            self.experiment_hardware_req = (
                self.find_attribute(obj, "hardware_requirement") or self.experiment_hardware_req
            )
        else:
            qCritical(f"{self.experiment_name} does not inherit from ExperimentClass.")
            QMessageBox.critical(
                None,
                "Error",
                f"{self.experiment_name} must inherit from ExperimentClass."
            )
            return

        qInfo(f"Loaded {self.experiment_type.__name__} class: {self.experiment_name}")

        # Store class reference and extract important methods
        self.experiment_class = obj
        self.experiment_exporter = self.find_attribute(obj, "export_data") or self.experiment_exporter
        self.experiment_runtime_estimator = self.find_attribute(obj, "estimate_runtime")

        # Apply config template if available
        self.find_config(obj)

        # Ensure "sets" key exists in config (default to 1 repetition)
        exp_config = self.experiment_tab.experiment_config_panel.config
        if "sets" not in exp_config:
            exp_config["sets"] = 1