"""
=================
PlotSinkManager.py
=================
Manages the connection between the custom Matplotlib backend and the Desq GUI.

This module provides:
1. A Qt-based plot receiver that can be connected to GUI handlers
2. Context managers for setting up plot sinks in worker threads
3. Integration with the QDesqTab for routing figures

THREAD SAFETY:
--------------
- Figures are rendered in worker threads (where experiments run)
- GUI updates must happen on the Qt main thread
- This module uses Qt signals with QueuedConnection for safe cross-thread communication

IMPORTANT: Do NOT use qDebug/qInfo/qWarning from worker threads!
           The log panel's message handler updates a QTextEdit which causes
           "Cannot queue arguments of type 'QTextCursor'" errors.
           Use print() for worker thread debugging instead.

USAGE:
------
In the main GUI (Desq.py):
    from PlotSinkManager import PlotSinkManager

    self.plot_sink_manager = PlotSinkManager()
    self.plot_sink_manager.figureReceived.connect(self.handle_figure_received)

In experiment worker threads:
    with plot_sink_manager.sink_context(tab):
        # Run experiment code - all matplotlib draws will be captured
        experiment.acquire()
"""

import threading
import weakref
from collections import deque
from functools import wraps

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt


class PlotSinkManager(QObject):
    """
    Central manager for routing matplotlib figures from worker threads to GUI tabs.

    Uses Qt signals for thread-safe communication. Figures are captured in worker
    threads and emitted via signal to the GUI thread for display.

    Signals:
        figureReceived: Emitted when a figure is drawn. Args: (figure, target_tab, event_type)
    """

    # Signal emitted when a figure is received from any worker thread
    # Args: (figure object, target tab widget, event_type string)
    figureReceived = pyqtSignal(object, object, str)

    def __init__(self, parent=None):
        """
        Initialize the plot sink manager.

        Args:
            parent: Optional Qt parent object
        """
        super().__init__(parent)

        # Track active sinks by thread ID
        # Maps thread_id -> (sink_callable, target_tab_weakref)
        self._active_sinks = {}
        self._lock = threading.Lock()

        # Debounce queue for coalescing rapid figure updates
        self._pending_figures = deque()
        self._flush_timer = None

        # Debug flag - set to True to enable print debugging
        self._debug = True

    def _log(self, message):
        """
        Thread-safe logging that uses print() instead of qDebug().

        IMPORTANT: We cannot use qDebug/qInfo/qWarning from worker threads
        because the log panel's message handler updates a QTextEdit,
        which causes QTextCursor threading errors.
        """
        if self._debug:
            thread_id = threading.current_thread().ident
            print(f"[PlotSinkManager][Thread-{thread_id}] {message}")

    def create_sink_for_tab(self, tab):
        """
        Create a plot sink callable that routes figures to the specified tab.

        The returned callable should be passed to BackendDesq.set_plot_sink().
        It captures figures drawn in the current thread and emits them via signal.

        Args:
            tab: QDesqTab instance that should receive the figures

        Returns:
            Callable that can be passed to set_plot_sink()
        """
        # Use weak reference to avoid preventing tab garbage collection
        tab_ref = weakref.ref(tab)
        manager_ref = weakref.ref(self)

        # Track last notification time per figure for time-based debouncing
        last_notification_time = {}
        DEBOUNCE_INTERVAL = 0.05  # 50ms debounce for live updates

        # Capture debug flag at creation time
        debug = self._debug

        def sink(figure, event_type):
            """
            Sink callable invoked by BackendDesq on each draw.
            """
            import time

            # Only capture on 'draw' (complete render), not 'draw_idle'
            if event_type != 'draw':
                return

            # Check tab still exists
            tab = tab_ref()
            if tab is None:
                if debug:
                    print(f"[PlotSink] Tab no longer exists, ignoring figure")
                return

            # Check manager still exists
            manager = manager_ref()
            if manager is None:
                if debug:
                    print(f"[PlotSink] Manager no longer exists, ignoring figure")
                return

            # Time-based debounce: skip if we notified for this figure too recently
            # This allows live updates while preventing spam from rapid redraws
            fig_id = id(figure)
            current_time = time.monotonic()
            last_time = last_notification_time.get(fig_id, 0)

            if current_time - last_time < DEBOUNCE_INTERVAL:
                if debug:
                    print(f"[PlotSink] Figure {fig_id} debounced (last: {last_time:.3f}, now: {current_time:.3f})")
                return

            last_notification_time[fig_id] = current_time

            if debug:
                print(f"[PlotSink] Emitting figure {fig_id} to GUI thread")

            # Emit signal - Qt handles thread-safe delivery
            # Note: Qt signal emission from non-GUI thread uses QueuedConnection
            manager.figureReceived.emit(figure, tab, event_type)

        return sink

    def sink_context(self, tab):
        """
        Context manager for setting up a plot sink in a worker thread.

        Usage:
            with plot_sink_manager.sink_context(tab):
                # All matplotlib draws in this block route to `tab`
                plt.figure()
                plt.plot(data)
                # Figure automatically captured and sent to tab

        Args:
            tab: QDesqTab that should receive figures

        Returns:
            Context manager
        """
        return _SinkContext(self, tab)

    def setup_sink_for_thread(self, tab):
        """
        Set up the plot sink for the current thread to route to the given tab.

        Call this at the start of a worker thread that will generate plots.
        Must call cleanup_sink_for_thread() when done.

        Args:
            tab: QDesqTab that should receive figures
        """
        # Import from same package (scripts/)
        from MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq import set_plot_sink

        sink = self.create_sink_for_tab(tab)
        thread_id = threading.current_thread().ident

        with self._lock:
            self._active_sinks[thread_id] = (sink, weakref.ref(tab))

        set_plot_sink(sink)

        # Use print() instead of qDebug() - see docstring for why
        self._log(f"Plot sink activated for thread {thread_id}")

    def cleanup_sink_for_thread(self):
        """
        Remove the plot sink for the current thread.

        Call this when a worker thread finishes generating plots.
        """
        from MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq import clear_plot_sink

        thread_id = threading.current_thread().ident

        with self._lock:
            self._active_sinks.pop(thread_id, None)

        clear_plot_sink()

        # Use print() instead of qDebug() - see docstring for why
        self._log(f"Plot sink deactivated for thread {thread_id}")


class _SinkContext:
    """
    Context manager for setting up and tearing down plot sinks.

    Ensures sink is properly cleaned up even if an exception occurs.
    """

    def __init__(self, manager, tab):
        self.manager = manager
        self.tab = tab

    def __enter__(self):
        self.manager.setup_sink_for_thread(self.tab)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.manager.cleanup_sink_for_thread()
        return False  # Don't suppress exceptions


# =============================================================================
# CONVENIENCE: Figure Collection Helpers
# =============================================================================

def collect_all_figures():
    """
    Get all currently open matplotlib figures.

    Useful for capturing figures after code that doesn't use plt.show().

    Returns:
        List of matplotlib Figure objects
    """
    from matplotlib._pylab_helpers import Gcf

    managers = Gcf.get_all_fig_managers()
    return [m.canvas.figure for m in managers]


def close_all_figures():
    """
    Close all matplotlib figures.

    Call this after capturing figures to free memory.
    """
    import matplotlib.pyplot as plt
    plt.close('all')


# =============================================================================
# INTEGRATION: Install Backend Before Experiment Import
# =============================================================================

def ensure_backend_installed():
    """
    Ensure the custom backend is installed.

    Call this before any code that might import matplotlib.pyplot.
    Safe to call multiple times.

    Returns:
        True if backend was installed, False if already installed
    """
    import matplotlib

    # Full module path since BackendDesq.py is in scripts/ subfolder
    BACKEND_MODULE = 'module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq'

    current_backend = matplotlib.get_backend()

    # Check if already using our backend (case-insensitive check)
    # FIXED: Use lowercase comparison on both sides
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


def install_backend_if_needed():
    """
    Install backend if matplotlib hasn't been imported yet.

    This sets the environment variable so that when matplotlib IS imported,
    it will use our backend.
    """
    import os
    import sys

    # Full module path since BackendDesq.py is in scripts/ subfolder
    BACKEND_MODULE = 'module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq'

    # If matplotlib already imported, use force switch
    if 'matplotlib' in sys.modules:
        ensure_backend_installed()
    else:
        # Set environment variable for future import
        os.environ['MPLBACKEND'] = BACKEND_MODULE
        print(f"[PlotSinkManager] Set MPLBACKEND={BACKEND_MODULE}")