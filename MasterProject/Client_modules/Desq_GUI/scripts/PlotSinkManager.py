"""
==================
PlotSinkManager.py
==================

Manages the connection between the custom Matplotlib backend and the Desq GUI.

This module provides:

1. A Qt-based plot receiver that can be connected to GUI handlers
2. Context managers for setting up plot sinks in worker threads
3. Integration with the QDesqTab for routing figures

Thread Safety
-------------

- Figures are rendered in worker threads (where experiments run)
- GUI updates must happen on the Qt main thread
- This module uses Qt signals with QueuedConnection for safe cross-thread communication

.. warning::

    Do **NOT** use ``qDebug``/``qInfo``/``qWarning`` from worker threads!
    The log panel's message handler updates a ``QTextEdit`` which causes
    ``"Cannot queue arguments of type 'QTextCursor'"`` errors.
    Use ``print()`` for worker thread debugging instead.

Usage
-----

In the main GUI (Desq.py)::

    from PlotSinkManager import PlotSinkManager

    self.plot_sink_manager = PlotSinkManager()
    self.plot_sink_manager.figureReceived.connect(self.handle_figure_received)

    def handle_figure_received(self, figure, target_tab, event_type):
        '''Handle figure from worker thread - runs on GUI thread'''
        if target_tab is not None:
            target_tab.receive_figure(figure, event_type)

In experiment runner (before starting experiment)::

    # Clear carousel state for new run
    tab.start_new_run()

In experiment worker threads::

    with plot_sink_manager.sink_context(tab):
        # Run experiment code - all matplotlib draws will be captured
        experiment.acquire()

:var BACKEND_MODULE: Full module path for the BackendDesq matplotlib backend.
:vartype BACKEND_MODULE: str

.. seealso::

    :mod:`BackendDesq` - The custom matplotlib backend that intercepts plot calls.
"""

from __future__ import annotations

import threading
import weakref
from collections import deque
from functools import wraps
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple, TYPE_CHECKING

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt

if TYPE_CHECKING:
    from matplotlib.figure import Figure


class PlotSinkManager(QObject):
    """
    Central manager for routing matplotlib figures from worker threads to GUI tabs.

    Uses Qt signals for thread-safe communication. Figures are captured in worker
    threads and emitted via signal to the GUI thread for display.

    Session-Based Isolation
    -----------------------

    Each sink is created with a ``session_id``. When figures are emitted, the
    ``session_id`` is included so the receiving tab can validate it matches the
    current session. This prevents cross-tab and cross-run figure contamination.

    :ivar figureReceived: Signal emitted when a figure is drawn.
    :vartype figureReceived: pyqtSignal(object, object, str, int)

    :ivar _active_sinks: Maps thread IDs to their active sink configurations.
        Each entry contains (sink_callable, target_tab_weakref, session_id).
    :vartype _active_sinks: Dict[int, Tuple[Callable, weakref.ref, int]]

    :ivar _lock: Threading lock for protecting ``_active_sinks`` access.
    :vartype _lock: threading.Lock

    :ivar _pending_figures: Queue for debouncing rapid figure updates (currently unused).
    :vartype _pending_figures: Deque

    :ivar _flush_timer: Timer for flushing pending figures (currently unused).
    :vartype _flush_timer: Optional[QTimer]

    :ivar _debug: Flag to enable debug logging via print statements.
    :vartype _debug: bool

    """

    # Signal emitted when a figure is received from any worker thread
    # Args: (figure object, target tab widget, event_type string, session_id int)
    figureReceived: pyqtSignal = pyqtSignal(object, object, str, int)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """
        Initialize the plot sink manager.

        :param parent: Optional Qt parent object for proper Qt object hierarchy.
        :type parent: Optional[QObject]
        """
        super().__init__(parent)

        # Track active sinks by thread ID
        # Maps thread_id -> (sink_callable, target_tab_weakref, session_id)
        self._active_sinks: Dict[int, Tuple[Callable, weakref.ref, int]] = {}
        self._lock: threading.Lock = threading.Lock()

        # NOTE: These are unused in current implementation - possible future feature
        # Debounce queue for coalescing rapid figure updates
        self._pending_figures: Deque = deque()
        self._flush_timer: Optional[QTimer] = None

        # Debug flag - set to True to enable print debugging
        self._debug: bool = True

    def _log(self, message: str) -> None:
        """
        Thread-safe logging that uses ``print()`` instead of ``qDebug()``.

        This method exists because Qt's logging functions (``qDebug``, ``qInfo``,
        ``qWarning``) cannot be safely called from worker threads when a custom
        message handler updates Qt widgets.

        :param message: The message to log.
        :type message: str

        .. warning::

            We cannot use ``qDebug``/``qInfo``/``qWarning`` from worker threads
            because the log panel's message handler updates a ``QTextEdit``,
            which causes ``QTextCursor`` threading errors.
        """
        if self._debug:
            thread_id = threading.current_thread().ident
            print(f"[PlotSinkManager][Thread-{thread_id}] {message}")

    def create_sink_for_tab(self, tab: Any, session_id: int) -> Callable[['Figure', str], None]:
        """
        Create a plot sink callable that routes figures to the specified tab.

        The returned callable should be passed to ``BackendDesq.set_plot_sink()``.
        It captures figures drawn in the current thread and emits them via signal.

        :param tab: QDesqTab instance that should receive the figures.
        :type tab: QDesqTab
        :param session_id: The plot session ID to associate with captured figures.
            The receiving tab will validate this matches its current session.
        :type session_id: int

        :returns: A callable that can be passed to ``set_plot_sink()``. The callable
            accepts ``(figure, event_type)`` arguments.
        :rtype: Callable[[Figure, str], None]

        .. note::

            The sink uses weak references to both the tab and manager to avoid
            preventing garbage collection of these objects.
        """
        # Use weak reference to avoid preventing tab garbage collection
        tab_ref: weakref.ref = weakref.ref(tab)
        manager_ref: weakref.ref = weakref.ref(self)

        # Track last notification time per figure for time-based debouncing
        last_notification_time: Dict[int, float] = {}

        # Debounce interval of 50ms prevents spam from rapid redraws
        # while still allowing live update responsiveness
        DEBOUNCE_INTERVAL: float = 0.05  # 50ms debounce for live updates

        # Capture debug flag and session_id at creation time to avoid
        # accessing self from the closure (which would prevent GC)
        debug: bool = self._debug
        captured_session_id: int = session_id

        def sink(figure: 'Figure', event_type: str) -> None:
            """
            Sink callable invoked by BackendDesq on each draw.

            This inner function is called by the matplotlib backend whenever a
            figure is drawn. It filters events, applies debouncing, and emits
            the figure to the GUI thread via Qt signal.

            :param figure: The matplotlib figure that was drawn.
            :type figure: matplotlib.figure.Figure
            :param event_type: Type of draw event ('draw' or 'draw_idle').
            :type event_type: str
            """
            import time

            # Only capture on 'draw' (complete render), not 'draw_idle'
            # 'draw_idle' is a deferred draw that hasn't completed yet
            if event_type != 'draw':
                return

            # Check tab still exists (weak reference may be dead)
            tab = tab_ref()
            if tab is None:
                if debug:
                    print(f"[PlotSink] Tab no longer exists, ignoring figure")
                return

            # Check manager still exists (weak reference may be dead)
            manager = manager_ref()
            if manager is None:
                if debug:
                    print(f"[PlotSink] Manager no longer exists, ignoring figure")
                return

            # Time-based debounce: skip if we notified for this figure too recently
            # This allows live updates while preventing spam from rapid redraws
            fig_id: int = id(figure)
            current_time: float = time.monotonic()
            last_time: float = last_notification_time.get(fig_id, 0)

            if current_time - last_time < DEBOUNCE_INTERVAL:
                if debug:
                    print(f"[PlotSink] Figure {fig_id} debounced (last: {last_time:.3f}, now: {current_time:.3f})")
                return

            last_notification_time[fig_id] = current_time

            if debug:
                print(f"[PlotSink] Emitting figure {fig_id} to GUI thread (session={captured_session_id})")

            # Emit signal with session_id - Qt handles thread-safe delivery
            # via QueuedConnection when crossing thread boundaries
            manager.figureReceived.emit(figure, tab, event_type, captured_session_id)

        return sink

    def sink_context(self, tab: Any, session_id: int) -> '_SinkContext':
        """
        Context manager for setting up a plot sink in a worker thread.

        This is the preferred way to capture matplotlib figures from experiment
        code running in worker threads.

        :param tab: QDesqTab that should receive figures.
        :type tab: QDesqTab
        :param session_id: The plot session ID for this context.
        :type session_id: int

        :returns: A context manager that sets up the sink on entry and
            cleans up on exit.
        :rtype: _SinkContext

        Example::

            with plot_sink_manager.sink_context(tab, session_id):
                # All matplotlib draws in this block route to `tab`
                plt.figure()
                plt.plot(data)
                # Figure automatically captured and sent to tab
        """
        return _SinkContext(self, tab, session_id)

    def setup_sink_for_thread(self, tab: Any, session_id: int) -> None:
        """
        Set up the plot sink for the current thread to route to the given tab.

        Call this at the start of a worker thread that will generate plots.
        Must call :meth:`cleanup_sink_for_thread` when done.

        :param tab: QDesqTab that should receive figures.
        :type tab: QDesqTab
        :param session_id: The plot session ID to associate with this sink.
        :type session_id: int

        :raises ImportError: If BackendDesq module cannot be imported.

        .. note::

            Prefer using :meth:`sink_context` instead of calling this method
            directly, as the context manager ensures proper cleanup even if
            exceptions occur.

        .. seealso::

            :meth:`cleanup_sink_for_thread` - Must be called when done.
        """
        # Import from same package (scripts/)
        from MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq import set_plot_sink

        sink: Callable = self.create_sink_for_tab(tab, session_id)
        thread_id: int = threading.current_thread().ident

        # Thread-safe registration of the sink
        with self._lock:
            self._active_sinks[thread_id] = (sink, weakref.ref(tab), session_id)

        set_plot_sink(sink)

        # Use print() instead of qDebug() - see class docstring for why
        self._log(f"Plot sink activated for thread {thread_id} (session={session_id})")

    def cleanup_sink_for_thread(self) -> None:
        """
        Remove the plot sink for the current thread.

        Call this when a worker thread finishes generating plots.

        .. note::

            This method is automatically called by :class:`_SinkContext`
            when exiting the context manager.

        .. seealso::

            :meth:`setup_sink_for_thread` - Sets up the sink that this cleans up.
        """
        from MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq import clear_plot_sink

        thread_id: int = threading.current_thread().ident

        # Thread-safe removal of the sink
        with self._lock:
            self._active_sinks.pop(thread_id, None)

        clear_plot_sink()

        # Use print() instead of qDebug() - see class docstring for why
        self._log(f"Plot sink deactivated for thread {thread_id}")


class _SinkContext:
    """
    Context manager for setting up and tearing down plot sinks.

    Ensures sink is properly cleaned up even if an exception occurs.
    This class is not intended to be instantiated directly; use
    :meth:`PlotSinkManager.sink_context` instead.

    :ivar manager: Reference to the PlotSinkManager that created this context.
    :vartype manager: PlotSinkManager

    :ivar tab: The QDesqTab that should receive figures.
    :vartype tab: QDesqTab

    :ivar session_id: The plot session ID for this context.
    :vartype session_id: int
    """

    def __init__(self, manager: PlotSinkManager, tab: Any, session_id: int) -> None:
        """
        Initialize the sink context.

        :param manager: The PlotSinkManager instance.
        :type manager: PlotSinkManager
        :param tab: The QDesqTab that should receive figures.
        :type tab: Any
        :param session_id: The plot session ID for this context.
        :type session_id: int
        """
        self.manager: PlotSinkManager = manager
        self.tab: Any = tab
        self.session_id: int = session_id

    def __enter__(self) -> '_SinkContext':
        """
        Enter the context and set up the plot sink.

        :returns: This context manager instance.
        :rtype: _SinkContext
        """
        self.manager.setup_sink_for_thread(self.tab, self.session_id)
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any]
    ) -> bool:
        """
        Exit the context and clean up the plot sink.

        :param exc_type: Exception type if an exception was raised, else None.
        :type exc_type: Optional[type]
        :param exc_val: Exception instance if an exception was raised, else None.
        :type exc_val: Optional[BaseException]
        :param exc_tb: Traceback if an exception was raised, else None.
        :type exc_tb: Optional[TracebackType]

        :returns: False to propagate any exceptions (never suppresses).
        :rtype: bool
        """
        self.manager.cleanup_sink_for_thread()
        return False  # Don't suppress exceptions


# =============================================================================
# CONVENIENCE: Figure Collection Helpers
# =============================================================================


def collect_all_figures() -> List['Figure']:
    """
    Get all currently open matplotlib figures.

    Useful for capturing figures after code that doesn't use ``plt.show()``.

    :returns: List of all open matplotlib Figure objects.
    :rtype: List[matplotlib.figure.Figure]

    Example::

        # After running code that creates figures
        figures = collect_all_figures()
        for fig in figures:
            process_figure(fig)
    """
    from matplotlib._pylab_helpers import Gcf

    managers = Gcf.get_all_fig_managers()
    return [m.canvas.figure for m in managers]


def close_all_figures() -> None:
    """
    Close all matplotlib figures.

    Call this after capturing figures to free memory. This is especially
    important in long-running applications to prevent memory leaks.

    .. note::

        This calls ``plt.close('all')`` which closes all figures managed
        by the current matplotlib backend.
    """
    import matplotlib.pyplot as plt
    plt.close('all')


# =============================================================================
# INTEGRATION: Install Backend Before Experiment Import
# =============================================================================

#: Full module path for the BackendDesq matplotlib backend.
#: Used by :func:`ensure_backend_installed` and :func:`install_backend_if_needed`.
BACKEND_MODULE: str = 'module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq'


def ensure_backend_installed() -> bool:
    """
    Ensure the custom backend is installed.

    Call this before any code that might import ``matplotlib.pyplot``.
    Safe to call multiple times.

    :returns: True if backend was newly installed, False if already installed
        or if installation failed (falls back to Agg backend).
    :rtype: bool

    :raises: Does not raise - catches all exceptions and falls back to Agg.

    .. note::

        If the BackendDesq installation fails, this function falls back to
        the 'Agg' backend which is headless and won't route figures to the GUI.
        A warning is printed in this case.

    .. seealso::

        :func:`install_backend_if_needed` - Alternative that sets environment
        variable before matplotlib is imported.
    """
    import matplotlib

    current_backend: str = matplotlib.get_backend()

    # Check if already using our backend (case-insensitive check)
    # Use lowercase comparison on both sides for reliability
    if 'backenddesq' in current_backend.lower():
        print(f"[PlotSinkManager] Backend already installed: {current_backend}")
        return False

    # Install our backend
    try:
        matplotlib.use(BACKEND_MODULE, force=True)
        print(f"[PlotSinkManager] Installed BackendDesq as matplotlib backend")
        return True
    except Exception as e:
        print(f"[PlotSinkManager] WARNING: Failed to install BackendDesq: {e}")
        # Fall back to Agg (headless, but won't route to GUI)
        matplotlib.use('Agg', force=True)
        return False


def install_backend_if_needed() -> None:
    """
    Install backend if matplotlib hasn't been imported yet.

    This sets the ``MPLBACKEND`` environment variable so that when matplotlib
    IS imported, it will use our backend. If matplotlib is already imported,
    this delegates to :func:`ensure_backend_installed`.

    .. note::

        This function should be called as early as possible in the application
        startup, before any imports that might transitively import matplotlib.

    .. seealso::

        :func:`ensure_backend_installed` - Called if matplotlib already imported.
    """
    import os
    import sys

    # If matplotlib already imported, use force switch
    if 'matplotlib' in sys.modules:
        ensure_backend_installed()
    else:
        # Set environment variable for future import
        os.environ['MPLBACKEND'] = BACKEND_MODULE
        print(f"[PlotSinkManager] Set MPLBACKEND={BACKEND_MODULE}")