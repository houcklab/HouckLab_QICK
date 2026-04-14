"""
==================
AuxiliaryThread.py
==================

An auxiliary thread used to run a function without freezing up the GUI.

Most crucially, examples include RFSoC connection establishment, Experiment extraction,
and voltage interface connector. This module provides a wrapper around QThread that
handles function execution with optional timeout support.

Sample Usage:

.. code-block:: python

    self.aux_thread = QThread()
    self.aux_worker = AuxiliaryThread(target_func=makeProxy, func_kwargs={"ns_host": ip_address}, timeout=2)
    self.aux_worker.moveToThread(self.aux_thread)

    # Connecting started and finished signals
    self.aux_thread.started.connect(self.aux_worker.run)  # run function
    self.aux_worker.finished.connect(self.aux_thread.quit)  # stop thread
    self.aux_worker.finished.connect(self.aux_worker.deleteLater)  # delete worker
    self.aux_thread.finished.connect(self.aux_thread.deleteLater)  # delete thread

    # Connecting data related slots
    self.aux_worker.error_signal.connect(lambda err: self.failed_rfsoc_error(err, ip_address, timeout=False))
    self.aux_worker.result_signal.connect(lambda result: self.save_RFSoC(result[0], result[1], ip_address))
    self.aux_worker.timeout_signal.connect(lambda err: self.failed_rfsoc_error(err, ip_address, timeout=True))

    self.aux_thread.start()

.. note::
    The timeout mechanism does not forcibly terminate the function execution.
    It only emits a timeout signal while the function continues running in the background
    until safe completion.

.. seealso::
    :class:`_FunctionWorker` for the internal worker implementation that actually executes the function.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QThread

class AuxiliaryThread(QObject):
    """
    Auxiliary thread wrapper that executes a function with optional timeout tracking.

    This class provides a mechanism to run potentially long-running functions
    on a separate thread while monitoring execution time. The main thread remains
    responsive while the function executes.

    The architecture uses two threads:
        1. The AuxiliaryThread itself runs a QTimer for timeout tracking
        2. An internal _FunctionWorker runs the actual function

    :ivar target_func: The function to execute.
    :vartype target_func: Callable
    :ivar func_kwargs: Keyword arguments to pass to the target function.
    :vartype func_kwargs: Dict[str, Any]
    :ivar timeout: Timeout duration in seconds, or None for no timeout.
    :vartype timeout: Optional[int]
    :ivar _timer: Internal QTimer for timeout tracking.
    :vartype _timer: Optional[QTimer]
    :ivar _worker_thread: Internal thread for function execution.
    :vartype _worker_thread: Optional[QThread]
    :ivar _worker: Internal worker object that executes the function.
    :vartype _worker: Optional[_FunctionWorker]

    .. warning::
        A timeout does not stop the threads. The threads continue to execute
        until safe completion in the background, at which point they auto-delete.
    """

    # -------------------------------------------------------------------------
    # Signal Definitions
    # -------------------------------------------------------------------------

    finished: pyqtSignal = pyqtSignal()
    """
    Signal emitted upon function execution completion.

    Emitted regardless of whether the function succeeded, failed, or timed out.
    Use this signal to clean up the thread and worker objects.
    """

    result_signal: pyqtSignal = pyqtSignal(object)
    """
    Signal emitted when function finishes successfully.

    :param rtn_object: The return value of the executed function.
    :type rtn_object: object
    """

    error_signal: pyqtSignal = pyqtSignal(str)
    """
    Signal emitted when an error occurs during function execution.

    :param error_str: The error message from the exception.
    :type error_str: str
    """

    timeout_signal: pyqtSignal = pyqtSignal(str)
    """
    Signal emitted if timeout occurs before function completion.

    :param error_str: The error message (typically empty string).
    :type error_str: str

    .. note::
        The function continues running even after timeout is signaled.
    """

    def __init__(
        self,
        target_func: Callable[..., Any],
        func_kwargs: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        parent: Optional[QObject] = None
    ) -> None:
        """
        Initialize the Auxiliary thread.

        :param target_func: The target function to execute.
        :type target_func: Callable[..., Any]
        :param func_kwargs: Keyword arguments to pass to the function. Defaults to empty dict.
        :type func_kwargs: Optional[Dict[str, Any]]
        :param timeout: Timeout in seconds. None means no timeout.
        :type timeout: Optional[int]
        :param parent: Parent QObject for Qt ownership hierarchy.
        :type parent: Optional[QObject]

        :returns: None
        """
        super().__init__(parent)
        self.target_func: Callable[..., Any] = target_func
        self.func_kwargs: Dict[str, Any] = func_kwargs or {}
        self.timeout: Optional[int] = timeout
        self._timer: Optional[QTimer] = None
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[_FunctionWorker] = None

    def run(self) -> None:
        """
        Start the function execution with optional timeout tracking.

        Creates an internal worker thread that runs the function while
        this thread maintains a timer for timeout tracking. If a timeout
        was specified, emits :attr:`timeout_signal` when the time expires.

        This method:
            1. Starts a QTimer if timeout is specified
            2. Creates a _FunctionWorker and moves it to a new QThread
            3. Connects all signals for result/error/completion handling
            4. Starts the worker thread

        :returns: None

        .. warning::
            A timeout does not stop the threads. The threads continue to
            execute until safe completion in the background, at which point
            they will auto-delete via the deleteLater connections.
        """
        # -------------------------------------------------------------------------
        # Timeout Timer Setup
        # -------------------------------------------------------------------------
        # Create a single-shot timer if timeout was specified
        if self.timeout:
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._on_timeout)
            # Convert seconds to milliseconds for QTimer
            self._timer.start(self.timeout * 1000)

        # -------------------------------------------------------------------------
        # Worker Thread Setup
        # -------------------------------------------------------------------------
        # Create a new thread and worker for function execution
        self._worker_thread = QThread()
        self._worker = _FunctionWorker(self.target_func, self.func_kwargs)
        self._worker.moveToThread(self._worker_thread)

        # Connect worker signals to our handler slots
        self._worker.result_signal.connect(self._on_result)
        self._worker.error_signal.connect(self._on_error)

        # Connect thread lifecycle signals
        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._worker_thread.quit)

        # Setup automatic cleanup via deleteLater
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        # Start execution
        self._worker_thread.start()

    def _on_result(self, result: Any) -> None:
        """
        Handle successful function completion.

        Stops the timeout timer if active, emits the result signal,
        and signals completion.

        :param result: The return value from the target function.
        :type result: Any

        :returns: None
        """
        # Cancel timeout timer if still running
        if self._timer and self._timer.isActive():
            self._timer.stop()
        self.result_signal.emit(result)
        self.finished.emit()

    def _on_error(self, error_str: str) -> None:
        """
        Handle function execution error.

        Stops the timeout timer if active, emits the error signal,
        and signals completion.

        :param error_str: The error message from the exception.
        :type error_str: str

        :returns: None
        """
        # Cancel timeout timer if still running
        if self._timer and self._timer.isActive():
            self._timer.stop()
        self.error_signal.emit(error_str)
        self.finished.emit()

    def _on_timeout(self) -> None:
        """
        Handle timeout expiration.

        Emits the timeout signal with an empty string. Note that this
        does not stop the function execution - the worker continues
        running in the background.

        :returns: None

        .. note::
            The finished signal is NOT emitted here because the function
            is still running. It will be emitted when the function
            eventually completes (successfully or with error).
        """
        self.timeout_signal.emit("")


class _FunctionWorker(QObject):
    """
    Internal worker class that executes a function and emits results.

    This is a private helper class used by :class:`AuxiliaryThread`.
    It runs the target function and emits signals for the result or
    any errors that occur.

    :ivar func: The function to execute.
    :vartype func: Callable[..., Any]
    :ivar kwargs: Keyword arguments to pass to the function.
    :vartype kwargs: Dict[str, Any]

    .. note::
        This class is intended for internal use only. Use :class:`AuxiliaryThread`
        as the public API.
    """

    # -------------------------------------------------------------------------
    # Signal Definitions
    # -------------------------------------------------------------------------

    finished: pyqtSignal = pyqtSignal()
    """Signal emitted when function execution completes (success or failure)."""

    result_signal: pyqtSignal = pyqtSignal(object)
    """Signal emitted with the function's return value on success."""

    error_signal: pyqtSignal = pyqtSignal(str)
    """Signal emitted with the error message on failure."""

    def __init__(self, func: Callable[..., Any], kwargs: Dict[str, Any]) -> None:
        """
        Initialize the function worker.

        :param func: The function to execute.
        :type func: Callable[..., Any]
        :param kwargs: Keyword arguments to pass to the function.
        :type kwargs: Dict[str, Any]

        :returns: None
        """
        super().__init__()
        self.func: Callable[..., Any] = func
        self.kwargs: Dict[str, Any] = kwargs

    def run(self) -> None:
        """
        Execute the target function and emit appropriate signals.

        Runs the function with the stored keyword arguments. On success,
        emits :attr:`result_signal` with the return value. On exception,
        prints the traceback and emits :attr:`error_signal` with the
        error message. Always emits :attr:`finished` at the end.

        :returns: None

        :raises Exception: Any exception from the target function is caught,
            logged via traceback, and emitted via error_signal.
        """
        try:
            result = self.func(**self.kwargs)
            self.result_signal.emit(result)
        except Exception as e:
            # Print full traceback for debugging purposes
            traceback.print_exc()
            self.error_signal.emit(str(e))
        finally:
            # Always signal completion
            self.finished.emit()