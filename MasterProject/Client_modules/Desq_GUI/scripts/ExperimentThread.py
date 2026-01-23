"""
===================
ExperimentThread.py
===================

Worker object for executing RFSoC experiments in a separate thread.

This module provides the :class:`ExperimentThread` class, a QObject-based worker
that executes quantum experiments on RFSoC hardware. It is designed to be moved
to a QThread for non-blocking experiment execution while communicating with
the main GUI thread via Qt signals.

Architecture
------------
``ExperimentThread`` is a QObject (not a QThread subclass). The intended usage is:

1. Create an ``ExperimentThread`` instance with experiment configuration
2. Move it to a new ``QThread`` via ``moveToThread()``
3. Connect thread's ``started`` signal to the worker's ``run()`` slot
4. Start the thread

This pattern allows clean separation between the thread lifecycle and the
experiment execution logic, following Qt best practices.

Plot Interception
-----------------
The worker integrates with :class:`PlotSinkManager` for matplotlib figure routing:

- Plot sink is set up at the start of ``run()`` with a session ID
- All matplotlib draws during ``acquire()`` are tagged with this session ID
- The target tab rejects figures with non-matching session IDs
- Plot sink is cleaned up in the ``finally`` block

This ensures plots from concurrent or stale experiment runs don't contaminate
the wrong GUI tabs.

Threading Safety
----------------
.. warning::
    Do **NOT** use ``qDebug()``, ``qInfo()``, ``qWarning()``, or ``qCritical()``
    from within the ``run()`` method! These functions run on the worker thread
    and the log panel's message handler updates a ``QTextEdit``, causing
    "Cannot queue arguments of type 'QTextCursor'" errors.

    Use ``print()`` for worker thread debugging instead.

.. seealso::
    - :mod:`PlotSinkManager` for plot routing implementation
    - :mod:`AuxiliaryThread` for an alternative threaded worker pattern
    - :class:`ExperimentClass` for the experiment interface

Module Attributes
-----------------
:var ExperimentInterrupted: Exception class raised when an experiment is force-stopped.
:vartype ExperimentInterrupted: type
"""

from __future__ import annotations

import time
import traceback
import ctypes
import threading
from typing import TYPE_CHECKING, Any, Dict, Optional

from PyQt5.QtCore import QObject, pyqtSignal, qWarning, qDebug

if TYPE_CHECKING:
    from MasterProject.Client_modules.Desq_GUI.scripts.PlotSinkManager import PlotSinkManager
    from MasterProject.Client_modules.Desq_GUI.scripts.DesqTab import QDesqTab
    from MasterProject.Client_modules.Desq_GUI.CoreLib.Experiment import ExperimentClass
    from qick import QickConfig
    from Pyro4 import Proxy


class ExperimentInterrupted(Exception):
    """
    Exception raised when an experiment is force-stopped.

    This exception is injected into the experiment thread via
    :func:`_raise_in_thread` to immediately interrupt execution,
    even if the experiment is blocked in a long-running operation.

    .. note::
        This uses Python's ``PyThreadState_SetAsyncExc`` mechanism,
        which can only interrupt at Python bytecode boundaries.
        C extensions or system calls may not be immediately interruptible.
    """
    pass


def _raise_in_thread(thread_id: int, exc_class: type) -> bool:
    """
    Inject an exception into a running thread.

    Uses Python's C API to asynchronously raise an exception in the
    target thread. This allows interrupting threads that are blocked
    in Python code without cooperative checking.

    :param thread_id: The native thread identifier (from ``threading.current_thread().ident``).
    :type thread_id: int
    :param exc_class: The exception class to raise in the target thread.
    :type exc_class: type

    :returns: True if the exception was successfully injected, False otherwise.
    :rtype: bool

    .. warning::
        If the injection affects multiple threads (result > 1), the operation
        is automatically undone to prevent undefined behavior. This can happen
        in rare race conditions.

    .. note::
        The exception will only be raised at the next Python bytecode boundary.
        Code running in C extensions or blocked on system calls will not be
        immediately interrupted.
    """
    # Use ctypes to call Python's C API for async exception injection
    result = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id),
        ctypes.py_object(exc_class)
    )

    # Safety check: if we affected multiple threads, undo the operation
    if result > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), 0)

    return result == 1


class ExperimentThread(QObject):
    """
    Worker object for executing RFSoC experiments on a separate thread.

    This class manages the execution loop for quantum experiments, handling
    multiple "sets" (repetitions), progress reporting, error handling, and
    integration with the matplotlib plot interception system.

    The worker communicates with the main GUI thread exclusively via Qt signals,
    ensuring thread-safe updates to the user interface.

    :param config: Configuration dictionary for the experiment.
    :type config: dict
    :param soccfg: The SoC configuration object.
    :type soccfg: QickConfig
    :param exp: The experiment instance to execute.
    :type exp: ExperimentClass
    :param soc: The RFSoC connection proxy.
    :type soc: Proxy
    :param plot_sink_manager: Manager for routing matplotlib figures to GUI.
        If None, plot interception is disabled.
    :type plot_sink_manager: PlotSinkManager | None
    :param target_tab: The GUI tab that should receive plots from this experiment.
    :type target_tab: QDesqTab | None
    :param session_id: Plot session ID for isolating figures. Obtained from
        ``tab.start_plot_session()``.
    :type session_id: int
    :param parent: Optional Qt parent object.
    :type parent: QObject | None

    :ivar config: The experiment configuration dictionary.
    :vartype config: dict
    :ivar experiment_instance: The experiment instance being executed.
    :vartype experiment_instance: ExperimentClass
    :ivar soc: The RFSoC hardware proxy.
    :vartype soc: Proxy
    :ivar plot_sink_manager: Manager for plot routing, or None if disabled.
    :vartype plot_sink_manager: PlotSinkManager | None
    :ivar target_tab: Target tab for plot output, or None if disabled.
    :vartype target_tab: QDesqTab | None
    :ivar session_id: Session ID for plot isolation.
    :vartype session_id: int
    :ivar running: Flag indicating if experiment loop is active.
    :vartype running: bool
    :ivar idx_set: Current set index (0-based).
    :vartype idx_set: int

    Example
    -------
    ::

        # Create worker and thread
        worker = ExperimentThread(config, soccfg, exp, soc,
                                  plot_sink_manager=manager,
                                  target_tab=tab,
                                  session_id=tab.start_plot_session())
        thread = QThread()
        worker.moveToThread(thread)

        # Connect signals
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.updateData.connect(handle_data)

        # Start execution
        thread.start()
    """

    #: Signal emitted when experiment execution completes (success or failure).
    finished: pyqtSignal = pyqtSignal()

    #: Signal emitted when new data is available after completing a set.
    #:
    #: :param data: The data dictionary from ``acquire()``.
    #: :param exp_instance: The experiment instance for access to analysis methods.
    updateData: pyqtSignal = pyqtSignal(object, object)

    #: Signal emitted for intermediate data during a set (live plotting).
    #:
    #: :param data: The intermediate data dictionary.
    #: :param exp_instance: The experiment instance.
    intermediateData: pyqtSignal = pyqtSignal(object, object)

    #: Signal emitted to update the progress bar after each set.
    #:
    #: :param sets_completed: Number of sets completed so far.
    updateProgress: pyqtSignal = pyqtSignal(int)

    #: Signal emitted to update runtime estimates after each set.
    #:
    #: :param runtime_delta: Time taken for the last set in seconds.
    #: :param sets_completed: Number of sets completed so far.
    updateRuntime: pyqtSignal = pyqtSignal(float, int)

    #: Signal emitted when the RFSoC encounters an error.
    #:
    #: :param error: The exception that was raised.
    #: :param traceback_str: Formatted traceback string.
    RFSOC_error: pyqtSignal = pyqtSignal(Exception, str)

    #: Signal emitted when experiment is force-stopped via :meth:`force_stop`.
    forceStopCompleted: pyqtSignal = pyqtSignal()

    def __init__(
        self,
        config: Dict[str, Any],
        soccfg: QickConfig,
        exp: ExperimentClass,
        soc: Proxy,
        plot_sink_manager: Optional[PlotSinkManager] = None,
        target_tab: Optional[QDesqTab] = None,
        session_id: int = 0,
        parent: Optional[QObject] = None
    ) -> None:
        """
        Initialize the experiment worker with configuration and hardware references.

        :param config: The config dictionary for the experiment.
        :type config: dict
        :param soccfg: The SoC configuration.
        :type soccfg: QickConfig
        :param exp: The experiment instance to execute.
        :type exp: ExperimentClass
        :param soc: The RFSoC connection proxy.
        :type soc: Proxy
        :param plot_sink_manager: PlotSinkManager instance for routing matplotlib figures.
        :type plot_sink_manager: PlotSinkManager | None
        :param target_tab: QDesqTab that should receive plots from this experiment.
        :type target_tab: QDesqTab | None
        :param session_id: Plot session ID for isolating figures.
        :type session_id: int
        :param parent: Optional Qt parent.
        :type parent: QObject | None
        """
        super().__init__(parent)

        self.config: Dict[str, Any] = config
        # Note: parent is stored but intentionally not used as Qt parent to avoid blocking
        self.parent: Optional[QObject] = parent
        self.experiment_instance: ExperimentClass = exp
        self.soc: Proxy = soc

        # Plot sink management with session isolation for figure routing
        self.plot_sink_manager: Optional[PlotSinkManager] = plot_sink_manager
        self.target_tab: Optional[QDesqTab] = target_tab
        self.session_id: int = session_id

        # Thread management state (set during run())
        self._thread_id: Optional[int] = None
        self._was_force_stopped: bool = False

        if not exp:
            qDebug('Warning: None experiment. Going to crash in 3, 2, 1...')

        # Connect intermediate data signal if experiment supports live updates
        if hasattr(self.experiment_instance, 'intermediateData'):
            self.experiment_instance.intermediateData.connect(self.intermediate_data_handler)

    def run(self) -> None:
        """
        Execute the RFSoC experiment loop.

        This is the main execution method, typically connected to a QThread's
        ``started`` signal. It:

        1. Sets up the plot sink for this thread (with session_id)
        2. Iterates through all sets defined in ``config["sets"]``
        3. Calls ``experiment_instance.acquire()`` for each set
        4. Emits progress and data signals after each set
        5. Handles errors and force-stop interruptions
        6. Cleans up plot sink in finally block

        Session Isolation
        -----------------
        The plot sink is configured with a ``session_id`` at the start. All
        matplotlib draws during ``acquire()`` are tagged with this session_id.
        The target tab rejects figures with non-matching session_id, preventing
        plot contamination from concurrent or stale runs.

        .. warning::
            This method runs on a **WORKER THREAD**!
            Do NOT use ``qDebug``/``qInfo``/``qWarning`` here - use ``print()`` instead.
            Qt message handlers update QTextEdit which is not thread-safe.

        :raises ExperimentInterrupted: Caught internally when force-stopped.
        """
        # Store thread ID for force_stop() to target this thread
        self._thread_id = threading.current_thread().ident

        # Set up plot sink for this thread to route matplotlib figures to GUI
        # The session_id ensures figures from old/different runs are rejected
        if self.plot_sink_manager and self.target_tab:
            self.plot_sink_manager.setup_sink_for_thread(self.target_tab, self.session_id)
            print(f"[ExperimentThread] Plot sink set up for {self.target_tab.tab_name} (session={self.session_id})")
        else:
            print(f"[ExperimentThread] Plot sink not configured")

        try:
            self.running: bool = True
            self.idx_set: int = 0
            prev_time: float = time.perf_counter()

            print(f"[ExperimentThread] Starting experiment loop, sets={self.config.get('sets', 1)}, session={self.session_id}")

            # Main experiment loop: iterate through all sets
            while self.running and self.idx_set < self.config["sets"]:

                try:
                    # Execute the experiment's acquire method (this is where hardware interaction happens)
                    data = self.experiment_instance.acquire()
                    data['data']['set_num'] = self.idx_set

                except ExperimentInterrupted:
                    # Force stop was requested - exit cleanly
                    print("[ExperimentThread] Force stopped!")
                    self._was_force_stopped = True
                    self.forceStopCompleted.emit()
                    break

                except Exception as e:
                    # Hardware or experiment error - report and exit
                    format_exc = traceback.format_exc()
                    print(f"[ExperimentThread] RFSOC error: {e}")
                    self.RFSOC_error.emit(e, format_exc)
                    self.finished.emit()
                    return  # Exit without updating data - no new data was recorded

                # Emit signals to update GUI with new data and progress
                # Note: Each set typically clears and recreates the plot (known inefficiency)
                self.updateData.emit(data, self.experiment_instance)

                # Update timing and progress tracking
                self.idx_set += 1
                curr_time = time.perf_counter()
                time_delta = curr_time - prev_time
                prev_time = curr_time

                self.updateRuntime.emit(time_delta, self.idx_set)
                self.updateProgress.emit(self.idx_set)

                print(f"[ExperimentThread] Completed set {self.idx_set}/{self.config['sets']}")

            print(f"[ExperimentThread] Experiment loop completed")
            self.finished.emit()

        except ExperimentInterrupted:
            # Force stop raised between loop iterations
            print("[ExperimentThread] Force stopped between sets")
            self._was_force_stopped = True
            self.forceStopCompleted.emit()

        except Exception as e:
            # Unexpected error in experiment loop
            print(f"[ExperimentThread] Experiment thread crashed: {e}")
            self.RFSOC_error.emit(str(e), traceback.format_exc())

        finally:
            # Always clean up state regardless of how we exit
            self.running = False
            self._thread_id = None

            # Clean up plot sink for this thread
            if self.plot_sink_manager:
                self.plot_sink_manager.cleanup_sink_for_thread()
                print(f"[ExperimentThread] Plot sink cleaned up")

            # Ensure finished is emitted (may be duplicate if already emitted above)
            self.finished.emit()

    def intermediate_data_handler(self, data: Dict[str, Any]) -> None:
        """
        Handle intermediate data signals from the experiment instance.

        This slot receives data emitted by the experiment during acquisition
        (not just at the end of a set), enabling live plotting updates.

        :param data: The intermediate data dictionary from the experiment.
        :type data: dict
        """
        data['data']['set_num'] = self.idx_set
        self.intermediateData.emit(data, self.experiment_instance)

    def stop(self) -> None:
        """
        Request a safe stop of the experiment.

        Sets the ``running`` flag to False, which will cause the experiment
        loop to exit after the current set completes. Also sets the experiment's
        ``stop_flag`` if it exists, allowing cooperative stopping within
        ``acquire()``.

        This is a "soft" stop that waits for the current operation to complete.
        For immediate interruption, use :meth:`force_stop` instead.

        .. note::
            This method is safe to call from any thread.
        """
        self.running = False

        # Set experiment's internal stop flag if it supports cooperative stopping
        if hasattr(self.experiment_instance, 'stop_flag'):
            self.experiment_instance.stop_flag = True

        qDebug("Safe stop requested, stopping the thread at the next set iteration......")

    def force_stop(self) -> bool:
        """
        Force-stop the experiment immediately.

        Injects an :class:`ExperimentInterrupted` exception into the worker
        thread, causing it to exit as soon as possible. This is more aggressive
        than :meth:`stop` and will interrupt the current ``acquire()`` call.

        Also calls :meth:`stop` to set flags for cooperative stopping.

        :returns: True if the exception was successfully injected, False if
            the thread ID was not available (thread not running).
        :rtype: bool

        .. warning::
            The exception can only be raised at Python bytecode boundaries.
            If the thread is blocked in a C extension or system call, there
            may be a delay before the interruption takes effect.

        .. seealso::
            :func:`_raise_in_thread` for the injection mechanism.
        """
        # Also set soft-stop flags
        self.stop()

        if self._thread_id is None:
            return False

        return _raise_in_thread(self._thread_id, ExperimentInterrupted)