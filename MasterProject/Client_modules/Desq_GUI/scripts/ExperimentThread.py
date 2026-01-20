"""
===================
ExperimentThread.py
===================
The experiment thread is a QObject (not a thread itself) that is used to execute RFSoC experiments. The intended usage
is for an ExterimentThread object to be created, moved to a new QThread, then run. Initialization is very important
by defining the experiment instance and configuration.

It will then communicate with the main program via signals, as intended in Qt, making it thread-safe.

CHANGES FOR BACKEND-BASED PLOT INTERCEPTION:
--------------------------------------------
- Added plot_sink_manager parameter to __init__
- Setup/cleanup of plot sink in run() method
- All matplotlib draws in acquire() are automatically routed to the correct GUI tab

IMPORTANT: Do NOT use qDebug/qInfo/qWarning from within the run() method!
           These run on a worker thread and the log panel's message handler
           updates a QTextEdit, causing "Cannot queue arguments of type 'QTextCursor'" errors.
           Use print() for worker thread debugging instead.
"""

import time
import traceback
import ctypes
import threading

from PyQt5.QtCore import QObject, pyqtSignal, qWarning, qDebug


class ExperimentInterrupted(Exception):
    """Raised when experiment is force-stopped."""
    pass


def _raise_in_thread(thread_id: int, exc_class: type) -> bool:
    """Inject exception into thread. Returns True on success."""
    result = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id),
        ctypes.py_object(exc_class)
    )
    if result > 1:  # Affected multiple threads - undo
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), 0)
    return result == 1

class ExperimentThread(QObject):
    """
    This class is used to run an RFSOC experiment, meant to be used on a separate QThread than the main loop.
    Communicates to the main GUI thread via signals and emitting data.

    **Important Attributes:**

        * config (dict): The dictionary containing the configuration for the experiment
        * experiment_instance (Class ExperimentClass): The experiment instance
        * soc (Proxy): The RFSoC connection proxy
        * plot_sink_manager (PlotSinkManager): Manager for routing matplotlib figures to GUI (NEW)
        * target_tab (QDesqTab): The tab that should receive plots from this experiment (NEW)
    """

    finished = pyqtSignal()
    """
    The Signal to send upon experiment execution completion.
    """

    updateData = pyqtSignal(object, object)
    """
    Signal to send when receiving new data, including the new data dictionary

    :param data: The data object.
    :type data: object
    :param exp_instance: The experiment instance object.
    :type exp_instance: object
    """

    intermediateData = pyqtSignal(object, object)
    """
    Signal to send when receiving intermediate data, meaning from within a set, rather than at the end of a set.

    :param data: The data object.
    :type data: object
    :param exp_instance: The experiment instance object.
    :type exp_instance: object
    """

    updateProgress = pyqtSignal(int)
    """
    Signal to send when finishing a set to update the setsComplete bar

    :param sets_completed: The number of sets completed
    :type sets_completed: int
    """

    updateRuntime = pyqtSignal(float, int)
    """
    Signal to send when finishing a set to update the runtime estimations

    :param runtime_delta: The runtime delta of the experiment
    :type runtime_delta: float
    :param sets_completed: The number of sets completed
    :type sets_completed: int
    """

    RFSOC_error = pyqtSignal(Exception, str)
    """
    Signal to send when the RFSoC encounters an error

    :param error: The exception raised by the RFSoC
    :type error: Exception
    :param traceback: The traceback of the exception
    :type traceback: str
    """

    forceStopCompleted = pyqtSignal()
    """
    Signal to send when the experiment is force-stopped.
    """

    def __init__(self, config, soccfg, exp, soc, plot_sink_manager=None, target_tab=None, session_id=0, parent=None):
        """
        Initializes an ExperimentThread object with the actual experiment instance, configuration, and soc connection.

        Args:
            config: The config dictionary for the experiment
            soccfg: The SoC configuration
            exp: The experiment instance
            soc: The RFSoC connection proxy
            plot_sink_manager: PlotSinkManager instance for routing matplotlib figures
            target_tab: QDesqTab that should receive plots from this experiment
            session_id: Plot session ID for isolating figures (obtained from tab.start_plot_session())
            parent: Optional Qt parent
        """

        super().__init__(parent)
        self.config = config  # The config file used to run the experiment
        self.parent = parent  # We don't actually want to give it the parent window, that can cause blocking
        self.experiment_instance = exp  # The object representing an instance of a QickProgram subclass to be run
        self.soc = soc  # The RFSOC!

        # Plot sink management with session isolation
        self.plot_sink_manager = plot_sink_manager
        self.target_tab = target_tab
        self.session_id = session_id

        self._thread_id = None
        self._was_force_stopped = False

        if not exp:
            qDebug('Warning: None experiment. Going to crash in 3, 2, 1...')

        # Connecting intermediate data signal if experiment uses it
        if hasattr(self.experiment_instance, 'intermediateData'):
            self.experiment_instance.intermediateData.connect(self.intermediate_data_handler)

    def run(self):
        """
        Run the RFSOC experiment. Each set execution is done with a simple while loop for now. Future implementations
        can change configuration variables at each set iteration. Sends appropriate signals at each set execution to
        update the data and progress bar.

        SESSION ISOLATION:
        - Sets up plot sink with session_id at the start of execution
        - All matplotlib draws during acquire() are tagged with this session_id
        - The target tab rejects figures with non-matching session_id

        IMPORTANT: This method runs on a WORKER THREAD!
        Do NOT use qDebug/qInfo/qWarning here - use print() instead.
        """
        self._thread_id = threading.current_thread().ident

        # =====================================================================
        # Set up plot sink for this thread with session_id
        # This routes all matplotlib draws to the target tab via Qt signals
        # The session_id ensures figures from old/different runs are rejected
        # =====================================================================
        if self.plot_sink_manager and self.target_tab:
            self.plot_sink_manager.setup_sink_for_thread(self.target_tab, self.session_id)
            print(f"[ExperimentThread] Plot sink set up for {self.target_tab.tab_name} (session={self.session_id})")
        else:
            print(f"[ExperimentThread] Plot sink not configured")

        try:
            self.running = True
            self.idx_set = 0
            prev_time = time.perf_counter()

            print(f"[ExperimentThread] Starting experiment loop, sets={self.config.get('sets', 1)}, session={self.session_id}")

            ### loop over all the sets for the data taking
            while self.running and self.idx_set < self.config["sets"]:

                try:
                    data = self.experiment_instance.acquire()
                    data['data']['set_num'] = self.idx_set

                except ExperimentInterrupted:
                    print("[ExperimentThread] Force stopped!")
                    self._was_force_stopped = True
                    self.forceStopCompleted.emit()
                    break

                except Exception as e:
                    format_exc = traceback.format_exc()
                    print(f"[ExperimentThread] RFSOC error: {e}")
                    self.RFSOC_error.emit(e, format_exc)
                    self.finished.emit()
                    return  # Do not want to update data -- no new data was recorded!

                # Emit the signal with new data and update the progress bar with additional set complete
                # Each set clears and recreates the plot (inefficient)
                self.updateData.emit(data, self.experiment_instance)

                self.idx_set += 1
                curr_time = time.perf_counter()
                time_delta = curr_time - prev_time
                prev_time = curr_time

                self.updateRuntime.emit(time_delta, self.idx_set)
                self.updateProgress.emit(self.idx_set)

                print(f"[ExperimentThread] Completed set {self.idx_set}/{self.config['sets']}")

            print(f"[ExperimentThread] Experiment loop completed")
            self.finished.emit()

        except ExperimentInterrupted:  # NEW: Catch if raised between iterations
            print("[ExperimentThread] Force stopped between sets")
            self._was_force_stopped = True
            self.forceStopCompleted.emit()
        except Exception as e:
            # emit an error signal (add one if you don't have it)
            print(f"[ExperimentThread] Experiment thread crashed: {e}")
            self.RFSOC_error.emit(str(e), traceback.format_exc())
        finally:
            self.running = False
            self._thread_id = None

            # =====================================================================
            # NEW: Clean up plot sink for this thread
            # =====================================================================
            if self.plot_sink_manager:
                self.plot_sink_manager.cleanup_sink_for_thread()
                print(f"[ExperimentThread] Plot sink cleaned up")

            # emit finished either way
            self.finished.emit()

    def intermediate_data_handler(self, data):
        """
        The function that handles an intermediate_data signal from the experiment instance.

        :param data: The data dictionary.
        :type data: dict
        """

        data['data']['set_num'] = self.idx_set
        self.intermediateData.emit(data, self.experiment_instance)


    def stop(self):
        """
        Safe stop an experiment.
        """
        self.running = False
        if hasattr(self.experiment_instance, 'stop_flag'):
            self.experiment_instance.stop_flag = True
        qDebug("Safe stop requested, stopping the thread at the next set iteration......")

    def force_stop(self) -> bool:  # NEW METHOD
        """
        Force stop - interrupt immediately.
        """
        self.stop()  # Also set flags

        if self._thread_id is None:
            return False

        return _raise_in_thread(self._thread_id, ExperimentInterrupted)