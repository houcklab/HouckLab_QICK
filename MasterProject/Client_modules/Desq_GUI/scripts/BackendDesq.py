"""
===============
BackendDesq.py
===============
Custom Matplotlib backend for Desq GUI that intercepts ALL rendering operations.

DESIGN RATIONALE:
-----------------
Unlike monkey-patching plt.show(), this approach intercepts at the FigureCanvas level,
which is the single point where ALL matplotlib rendering converges:
  - plt.show() eventually calls canvas.draw()
  - fig.canvas.draw() calls canvas.draw()
  - fig.canvas.draw_idle() calls canvas.draw_idle()
  - Animations call canvas.draw()
  - GUI paint events call canvas.draw()
  - fig.savefig() calls canvas.draw() internally

By owning the canvas, we capture ALL of these code paths without needing to wrap
each API individually. This is the same approach used by PyCharm's backend_interagg.

ARCHITECTURE:
-------------
1. FigureCanvasDesq extends FigureCanvasAgg (headless raster backend)
2. Overrides draw() and draw_idle() to notify a "plot sink"
3. PlotSink is thread-local, routing figures from worker threads to correct GUI tabs
4. Qt signals are used for thread-safe GUI updates (never touch widgets from workers)
5. FigureManagerDesq prevents any OS-level window creation

USAGE:
------
Before any experiment code imports matplotlib.pyplot:
    import matplotlib
    matplotlib.use('module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq')

Or set environment variable:
    os.environ['MPLBACKEND'] = 'module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq'

Then set the plot sink for the current thread:
    from BackendDesq import set_plot_sink, clear_plot_sink
    set_plot_sink(my_sink_callable)  # Called with (figure, event_type) on each draw
    # ... run experiment code ...
    clear_plot_sink()
"""

import threading
import weakref
import time
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backend_bases import FigureManagerBase
from matplotlib.figure import Figure

# =============================================================================
# DEBUG FLAG
# =============================================================================
_DEBUG = True


def _log(message):
    """Thread-safe debug logging using print (not qDebug)."""
    if _DEBUG:
        thread_id = threading.current_thread().ident
        print(f"[BackendDesq][Thread-{thread_id}] {message}")


# =============================================================================
# THREAD-LOCAL PLOT SINK
# =============================================================================
#
# Why thread-local? Experiments run in worker threads, and each tab needs its
# own sink to receive figures. Global state would cause figures from one
# experiment to appear in another tab.
#
# The sink is a callable: sink(figure, event_type) where event_type is 'draw'
# or 'draw_idle'. The sink is responsible for thread-safe forwarding to the GUI.

_thread_local = threading.local()


def set_plot_sink(sink):
    """
    Set the plot sink for the current thread.

    The sink receives (figure, event_type) whenever a figure is drawn.
    It's the sink's responsibility to forward to the GUI thread safely.

    Args:
        sink: Callable(figure, event_type) or None to disable
    """
    _thread_local.plot_sink = sink
    _log(f"Plot sink set: {sink is not None}")


def get_plot_sink():
    """
    Get the plot sink for the current thread, or None if not set.
    """
    return getattr(_thread_local, 'plot_sink', None)


def clear_plot_sink():
    """
    Remove the plot sink for the current thread.
    """
    _thread_local.plot_sink = None
    _log("Plot sink cleared")


# =============================================================================
# CUSTOM FIGURE CANVAS
# =============================================================================

class FigureCanvasDesq(FigureCanvasAgg):
    """
    Custom canvas that intercepts ALL draw operations.

    Extends FigureCanvasAgg (the headless raster backend) and overrides
    draw() and draw_idle() to notify the thread-local plot sink.

    This is the key interception point - matplotlib's architecture ensures
    that ALL rendering eventually passes through canvas.draw().
    """

    # Class-level tracking of recently-notified figures to avoid spam
    # Uses weak references so figures can be garbage collected
    _recent_notifications = weakref.WeakSet()
    _notification_lock = threading.Lock()

    def __init__(self, figure=None):
        """
        Initialize the canvas with an optional figure.

        Note: If figure is None, a default Figure is created (matplotlib standard).
        """
        if figure is None:
            figure = Figure()
        super().__init__(figure)
        self._desq_draw_pending = False
        self._desq_last_notification = 0
        _log(f"FigureCanvasDesq created for figure {id(figure)}")

    def draw(self):
        """
        Override draw() to intercept the rendering operation.

        This is called by:
        - plt.show()
        - fig.canvas.draw()
        - Animations (FuncAnimation, etc.)
        - Interactive backends on paint events
        - savefig() (internally)
        """
        _log(f"draw() called for figure {id(self.figure)}")

        # Do the actual rendering first (updates the internal buffer)
        super().draw()

        # Notify the sink (if any) - this happens AFTER rendering completes
        self._notify_sink('draw')

    def draw_idle(self):
        """
        Override draw_idle() to intercept deferred drawing.

        draw_idle() is matplotlib's "please redraw when convenient" method.
        Some code paths use this instead of draw() for efficiency.
        """
        # Call parent implementation (may schedule an actual draw)
        super().draw_idle()

        # Notify the sink - figure may be in partial state but that's OK
        # The sink can choose to wait for a 'draw' event instead
        self._notify_sink('draw_idle')

    def _notify_sink(self, event_type):
        """
        Notify the thread-local plot sink about a draw event.

        Args:
            event_type: 'draw' or 'draw_idle'
        """
        sink = get_plot_sink()
        if sink is None:
            _log(f"No sink set, skipping notification for {event_type}")
            return

        # Debounce: avoid notifying for the same figure repeatedly in quick succession
        # This prevents spam when matplotlib does multiple internal redraws
        now = time.monotonic()
        if now - self._desq_last_notification < 0.05:  # 50ms debounce
            _log(f"Debouncing {event_type} notification")
            return
        self._desq_last_notification = now

        _log(f"Notifying sink: {event_type} for figure {id(self.figure)}")

        try:
            sink(self.figure, event_type)
        except Exception as e:
            # Don't let sink errors break matplotlib
            import warnings
            warnings.warn(f"Desq plot sink error: {e}")
            print(f"[BackendDesq] ERROR in sink: {e}")


# =============================================================================
# CUSTOM FIGURE MANAGER
# =============================================================================

class FigureManagerDesq(FigureManagerBase):
    """
    Custom figure manager that prevents OS-level window creation.

    FigureManager is responsible for window management in interactive backends.
    By providing a no-op implementation, we ensure no GUI windows ever appear.
    """

    def __init__(self, canvas, num):
        """
        Initialize the manager with the given canvas and figure number.

        Args:
            canvas: FigureCanvasDesq instance
            num: Figure number (used by plt.figure(num))
        """
        super().__init__(canvas, num)
        _log(f"FigureManagerDesq created for figure num={num}")

    def show(self):
        """
        Override show() to prevent window display.

        This is called by plt.show() for interactive backends.
        We do nothing here - the sink notification already happened in draw().
        """
        _log(f"show() called - triggering canvas.draw()")
        # Ensure figure is fully rendered
        self.canvas.draw()
        # No window to show - sink was notified in draw()

    def destroy(self):
        """
        Clean up any resources (none for headless backend).
        """
        pass


# =============================================================================
# BACKEND ENTRY POINTS
# =============================================================================
#
# These functions are called by matplotlib when the backend is loaded.
# Names must match matplotlib's expected interface exactly.

def new_figure_manager(num, *args, FigureClass=Figure, **kwargs):
    """
    Create a new figure manager for the given figure number.

    This is called by plt.figure() and plt.subplots().

    Args:
        num: Figure number
        *args, **kwargs: Passed to Figure constructor
        FigureClass: Figure class to instantiate

    Returns:
        FigureManagerDesq instance
    """
    _log(f"new_figure_manager called: num={num}")
    fig = FigureClass(*args, **kwargs)
    canvas = FigureCanvasDesq(fig)
    manager = FigureManagerDesq(canvas, num)
    return manager


def new_figure_manager_given_figure(num, figure):
    """
    Create a new figure manager for an existing figure.

    This is called when matplotlib needs to manage a pre-existing Figure.

    Args:
        num: Figure number to assign
        figure: Existing Figure instance

    Returns:
        FigureManagerDesq instance
    """
    _log(f"new_figure_manager_given_figure called: num={num}")
    canvas = FigureCanvasDesq(figure)
    manager = FigureManagerDesq(canvas, num)
    return manager


def show(*args, block=None, **kwargs):
    """
    Backend's plt.show() implementation.

    For our headless backend, this ensures all figures are drawn
    (which triggers sink notifications) but does not block or display windows.

    Args:
        block: Ignored (no event loop to block)
    """
    from matplotlib._pylab_helpers import Gcf

    managers = list(Gcf.get_all_fig_managers())
    _log(f"show() called with {len(managers)} figures")

    # Draw all figures (this triggers sink notifications)
    for manager in managers:
        manager.canvas.draw()


# Required backend attributes
FigureCanvas = FigureCanvasDesq
FigureManager = FigureManagerDesq

# Log that the backend was loaded
_log("BackendDesq module loaded successfully")


# =============================================================================
# OPTIONAL: HELPER FOR CAPTURING FIGURES
# =============================================================================

class FigureCaptureSink:
    """
    A simple sink that captures figures into a list.

    Useful for testing or batch capture scenarios.

    Usage:
        sink = FigureCaptureSink()
        set_plot_sink(sink)
        # ... run plotting code ...
        figures = sink.get_figures()
        clear_plot_sink()
    """

    def __init__(self, capture_on='draw'):
        """
        Initialize the capture sink.

        Args:
            capture_on: Which event to capture on ('draw', 'draw_idle', or 'both')
        """
        self.figures = []
        self.capture_on = capture_on
        self._seen = set()  # Avoid duplicates

    def __call__(self, figure, event_type):
        """
        Sink callable - receives (figure, event_type).
        """
        if self.capture_on == 'both' or event_type == self.capture_on:
            fig_id = id(figure)
            if fig_id not in self._seen:
                self._seen.add(fig_id)
                self.figures.append(figure)
                print(f"[FigureCaptureSink] Captured figure {fig_id}")

    def get_figures(self):
        """
        Get captured figures and reset.
        """
        figs = self.figures.copy()
        self.clear()
        return figs

    def clear(self):
        """
        Clear captured figures.
        """
        self.figures.clear()
        self._seen.clear()


# =============================================================================
# OPTIONAL: QT-SAFE SIGNAL SINK
# =============================================================================

class QtSignalSink:
    """
    A sink that safely forwards figures to the Qt GUI thread via signals.

    This is the recommended sink for use with PyQt/PySide applications.
    It handles thread-safety automatically.

    Usage:
        from PyQt5.QtCore import QObject, pyqtSignal

        class PlotReceiver(QObject):
            figureReady = pyqtSignal(object, str)

        receiver = PlotReceiver()
        receiver.figureReady.connect(my_handler)  # Connect on GUI thread

        sink = QtSignalSink(receiver.figureReady)
        set_plot_sink(sink)
    """

    def __init__(self, signal, copy_figure=False):
        """
        Initialize the Qt signal sink.

        Args:
            signal: Qt signal to emit (must accept (figure, event_type))
            copy_figure: If True, copy figure data before emitting (safer but slower)
        """
        self.signal = signal
        self.copy_figure = copy_figure
        self._seen_draws = set()

    def __call__(self, figure, event_type):
        """
        Sink callable - emits signal with figure.
        """
        # Only emit on 'draw' (complete render), not draw_idle (partial)
        if event_type != 'draw':
            return

        # Debounce: skip if we've already notified for this figure recently
        fig_id = id(figure)
        if fig_id in self._seen_draws:
            return
        self._seen_draws.add(fig_id)

        # Schedule removal from seen set (allow re-notification after 100ms)
        try:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, lambda: self._seen_draws.discard(fig_id))
        except ImportError:
            pass  # Non-Qt environment, skip debounce cleanup

        if self.copy_figure:
            # Deep copy figure to avoid thread issues
            import pickle
            figure = pickle.loads(pickle.dumps(figure))

        # Emit signal (Qt handles thread-safe delivery via queued connection)
        self.signal.emit(figure, event_type)