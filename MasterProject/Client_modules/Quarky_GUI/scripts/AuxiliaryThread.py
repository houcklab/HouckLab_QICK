"""
==================
AuxiliaryThread.py
==================
An auxiliary thread used to a function without freezing up the GUI. Most crucially, examples include RFSoC connection
establishment, Experiment extraction, and voltage interface connector.

Sample Usage:

.. code-block:: python

    self.aux_thread = QThread()
    self.aux_worker = AuxiliaryThread(target_func=makeProxy, func_kwargs={"ns_host": ip_address}, timeout=2)
    self.aux_worker.moveToThread(self.aux_thread)

    # Connecting started and finished signals
    # self.thread.started.connect(self.current_tab.prepare_file_naming) # animate connecting
    self.aux_thread.started.connect(self.aux_worker.run)  # run function
    self.aux_worker.finished.connect(self.aux_thread.quit)  # stop thread
    self.aux_worker.finished.connect(self.aux_worker.deleteLater)  # delete worker
    self.aux_thread.finished.connect(self.aux_thread.deleteLater)  # delete thread

    # Connecting data related slots
    self.aux_worker.error_signal.connect(lambda err: self.failed_rfsoc_error(err, ip_address, timeout=False))
    self.aux_worker.result_signal.connect(lambda result: self.save_RFSoC(result[0], result[1], ip_address))
    self.aux_worker.timeout_signal.connect(lambda err: self.failed_rfsoc_error(err, ip_address, timeout=True))

    self.aux_thread.start()
    self.accounts_panel.connect_button.setEnabled(False)

"""
import traceback

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QThread

class AuxiliaryThread(QObject):
    """
    The Auxiliary class thread that takes a function, parameter, and timeout specification to run the function on a
    separate thread for a timeout amount of time.
    """

    finished = pyqtSignal()
    """
    The Signal to send upon function execution completion.
    """

    result_signal = pyqtSignal(object)
    """
    Emitted when function finishes successfully.
    :param rtn_object: The return of the function
    :type rtn_object: object
    """

    error_signal = pyqtSignal(str)
    """
    Emitted on error.
    :param error_str: The error message
    :type error_str: str
    """

    timeout_signal = pyqtSignal(str)
    """
    Emitted if timeout occurs.
    :param error_str: The error message
    :type error_str: str
    """

    def __init__(self, target_func, func_kwargs=None, timeout=None, parent=None):
        """
        Initialise the Auxiliary thread.

        :param target_func: The target function
        :type target_func: Callable
        :param func_kwargs: The function arguments
        :type func_kwargs: dict
        :param timeout: The timeout
        :type timeout: int
        """
        super().__init__(parent)
        self.target_func = target_func
        self.func_kwargs = func_kwargs or {}
        self.timeout = timeout
        self._timer = None
        self._worker_thread = None

    def run(self):

        if self.timeout:
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._on_timeout)
            self._timer.start(self.timeout * 1000)

        self._worker_thread = QThread()
        self._worker = _FunctionWorker(self.target_func, self.func_kwargs)
        self._worker.moveToThread(self._worker_thread)

        self._worker.result_signal.connect(self._on_result)
        self._worker.error_signal.connect(self._on_error)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._worker_thread.quit)

        self._worker.finished.connect(self._worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        self._worker_thread.start()

    def _on_result(self, result):
        if self._timer and self._timer.isActive():
            self._timer.stop()
        self.result_signal.emit(result)
        self.finished.emit()

    def _on_error(self, error_str):
        if self._timer and self._timer.isActive():
            self._timer.stop()
        self.error_signal.emit(error_str)
        self.finished.emit()

    def _on_timeout(self):
        self.timeout_signal.emit("")
        self.finished.emit()

class _FunctionWorker(QObject):
    finished = pyqtSignal()
    result_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)

    def __init__(self, func, kwargs):
        super().__init__()
        self.func = func
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.func(**self.kwargs)
            self.result_signal.emit(result)
        except Exception as e:
            traceback.print_exc()
            self.error_signal.emit(str(e))
        finally:
            self.finished.emit()