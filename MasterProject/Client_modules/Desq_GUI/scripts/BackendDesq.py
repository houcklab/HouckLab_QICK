"""
===============
BackendDesq.py
===============

Custom Matplotlib backend for Desq GUI that intercepts ALL rendering operations.

Design Rationale
----------------

Unlike monkey-patching ``plt.show()``, this approach intercepts at the FigureCanvas level,
which is the single point where ALL matplotlib rendering converges:

- ``plt.show()`` eventually calls ``canvas.draw()``
- ``fig.canvas.draw()`` calls ``canvas.draw()``
- ``fig.canvas.draw_idle()`` calls ``canvas.draw_idle()``
- Animations call ``canvas.draw()``
- GUI paint events call ``canvas.draw()``
- ``fig.savefig()`` calls ``canvas.draw()`` internally

By owning the canvas, we capture ALL of these code paths without needing to wrap
each API individually. This is the same approach used by PyCharm's ``backend_interagg``.

Architecture
------------

1. :class:`FigureCanvasDesq` extends ``FigureCanvasAgg`` (headless raster backend)
2. Overrides ``draw()`` and ``draw_idle()`` to notify a "plot sink"
3. PlotSink is thread-local, routing figures from worker threads to correct GUI tabs
4. Qt signals are used for thread-safe GUI updates (never touch widgets from workers)
5. :class:`FigureManagerDesq` prevents any OS-level window creation

Usage
-----

Before any experiment code imports matplotlib.pyplot::

    import matplotlib
    matplotlib.use('module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq')

Or set environment variable::

    os.environ['MPLBACKEND'] = 'module://MasterProject.Client_modules.Desq_GUI.scripts.BackendDesq'

Then set the plot sink for the current thread::

    from BackendDesq import set_plot_sink, clear_plot_sink
    set_plot_sink(my_sink_callable)  # Called with (figure, event_type) on each draw
    # ... run experiment code ...
    clear_plot_sink()

:var _DEBUG: Flag to enable/disable debug logging.
:vartype _DEBUG: bool

:var _thread_local: Thread-local storage for plot sinks.
:vartype _thread_local: threading.local

:var FigureCanvas: Alias for :class:`FigureCanvasDesq` (required by matplotlib).
:vartype FigureCanvas: type

:var FigureManager: Alias for :class:`FigureManagerDesq` (required by matplotlib).
:vartype FigureManager: type

.. seealso::
    - :class:`FigureCaptureSink` for testing/batch capture scenarios
    - :class:`QtSignalSink` for thread-safe Qt GUI integration
"""

from __future__ import annotations

import threading
import weakref
import time
import warnings
from typing import Any, Callable, List, Optional, Set, Union

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backend_bases import FigureManagerBase
from matplotlib.figure import Figure

# =============================================================================
# DEBUG FLAG
# =============================================================================

_DEBUG: bool = True
"""Debug flag to enable/disable verbose logging. Set to False in production."""


def _log(message: str) -> None:
    """
    Thread-safe debug logging using print.

    Only outputs messages when :data:`_DEBUG` is True. Each message is prefixed
    with the module name and current thread ID for debugging multi-threaded issues.

    :param message: The message to log.
    :type message: str

    :returns: None

    .. note::
        Uses ``print()`` instead of ``qDebug()`` for broader compatibility
        and to avoid Qt dependency in logging.
    """
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

_thread_local: threading.local = threading.local()
"""
Thread-local storage for plot sinks.

Each thread can have its own plot sink, ensuring figures from different
experiments/tabs don't get mixed up. The sink callable receives
``(figure, event_type)`` on each draw operation.
"""


def set_plot_sink(sink: Optional[Callable[[Figure, str], None]]) -> None:
    """
    Set the plot sink for the current thread.

    The sink receives ``(figure, event_type)`` whenever a figure is drawn.
    It's the sink's responsibility to forward to the GUI thread safely.

    :param sink: Callable that accepts ``(figure, event_type)`` or None to disable.
    :type sink: Optional[Callable[[Figure, str], None]]

    :returns: None

    .. note::
        Each thread maintains its own independent sink. Setting a sink in
        one thread does not affect other threads.

    .. seealso::
        :func:`get_plot_sink`, :func:`clear_plot_sink`
    """
    _thread_local.plot_sink = sink
    _log(f"Plot sink set: {sink is not None}")


def get_plot_sink() -> Optional[Callable[[Figure, str], None]]:
    """
    Get the plot sink for the current thread.

    :returns: The current thread's plot sink, or None if not set.
    :rtype: Optional[Callable[[Figure, str], None]]
    """
    return getattr(_thread_local, 'plot_sink', None)


def clear_plot_sink() -> None:
    """
    Remove the plot sink for the current thread.

    After calling this, draw operations in the current thread will not
    trigger any sink notifications.

    :returns: None
    """
    _thread_local.plot_sink = None
    _log("Plot sink cleared")


# =============================================================================
# CUSTOM FIGURE CANVAS
# =============================================================================


class FigureCanvasDesq(FigureCanvasAgg):
    """
    Custom canvas that intercepts ALL draw operations.

    Extends ``FigureCanvasAgg`` (the headless raster backend) and overrides
    ``draw()`` and ``draw_idle()`` to notify the thread-local plot sink.

    This is the key interception point - matplotlib's architecture ensures
    that ALL rendering eventually passes through ``canvas.draw()``.

    :cvar _recent_notifications: Class-level tracking of recently-notified figures to avoid spam.
        Uses weak references so figures can be garbage collected.
    :vartype _recent_notifications: weakref.WeakSet

    :cvar _notification_lock: Lock for thread-safe access to notification tracking.
    :vartype _notification_lock: threading.Lock

    :ivar _desq_draw_pending: Flag indicating if a draw is pending.
    :vartype _desq_draw_pending: bool

    :ivar _desq_last_notification: Timestamp of last notification for debouncing.
    :vartype _desq_last_notification: float

    :ivar _is_desq_canvas: Marker attribute to identify this as a BackendDesq canvas.
    :vartype _is_desq_canvas: bool

    .. note::
        The debouncing mechanism prevents notification spam when matplotlib
        does multiple internal redraws in quick succession (e.g., during
        animation frames or interactive updates).
    """

    # Class-level tracking of recently-notified figures to avoid spam
    # Uses weak references so figures can be garbage collected
    _recent_notifications: weakref.WeakSet = weakref.WeakSet()
    _notification_lock: threading.Lock = threading.Lock()

    def __init__(self, figure: Optional[Figure] = None) -> None:
        """
        Initialize the canvas with an optional figure.

        :param figure: The matplotlib Figure to render. If None, a default
            Figure is created (matplotlib standard behavior).
        :type figure: Optional[Figure]

        :returns: None

        .. note::
            The ``_is_desq_canvas`` attribute is set to True as a marker
            for code that needs to identify BackendDesq canvases.
        """
        if figure is None:
            figure = Figure()
        super().__init__(figure)
        self._desq_draw_pending: bool = False
        self._desq_last_notification: float = 0
        # Marker attribute so we can identify this as a BackendDesq canvas
        self._is_desq_canvas: bool = True
        _log(f"FigureCanvasDesq created for figure {id(figure)}")

    def draw(self) -> None:
        """
        Override draw() to intercept the rendering operation.

        This is called by:
            - ``plt.show()``
            - ``fig.canvas.draw()``
            - Animations (FuncAnimation, etc.)
            - Interactive backends on paint events
            - ``savefig()`` (internally)

        The method first performs the actual rendering via the parent class,
        then notifies the sink (if any) after rendering completes.

        :returns: None
        """
        _log(f"draw() called for figure {id(self.figure)}")

        # Do the actual rendering first (updates the internal buffer)
        super().draw()

        # Notify the sink (if any) - this happens AFTER rendering completes
        self._notify_sink('draw')

    def draw_idle(self) -> None:
        """
        Override draw_idle() to intercept deferred drawing.

        ``draw_idle()`` is matplotlib's "please redraw when convenient" method.
        Some code paths use this instead of ``draw()`` for efficiency.

        :returns: None

        .. note::
            The figure may be in a partial state when draw_idle is called.
            The sink can choose to wait for a 'draw' event instead for
            complete renders.
        """
        # Call parent implementation (may schedule an actual draw)
        super().draw_idle()

        # Notify the sink - figure may be in partial state but that's OK
        # The sink can choose to wait for a 'draw' event instead
        self._notify_sink('draw_idle')

    def _notify_sink(self, event_type: str) -> None:
        """
        Notify the thread-local plot sink about a draw event.

        Implements debouncing to avoid notification spam when matplotlib
        does multiple internal redraws in quick succession.

        :param event_type: The type of draw event - either ``'draw'`` or ``'draw_idle'``.
        :type event_type: str

        :returns: None

        .. note::
            Notifications are debounced with a 50ms window. If multiple draw
            events occur within this window, only the first triggers a notification.

        .. warning::
            Exceptions from the sink are caught and logged to prevent
            sink errors from breaking matplotlib's rendering pipeline.
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
            # Don't let sink errors break matplotlib's rendering
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

    :ivar canvas: The FigureCanvasDesq instance managed by this manager.
    :vartype canvas: FigureCanvasDesq

    :ivar num: The figure number (used by ``plt.figure(num)``).
    :vartype num: int
    """

    def __init__(self, canvas: FigureCanvasDesq, num: int) -> None:
        """
        Initialize the manager with the given canvas and figure number.

        :param canvas: FigureCanvasDesq instance to manage.
        :type canvas: FigureCanvasDesq
        :param num: Figure number (used by ``plt.figure(num)``).
        :type num: int

        :returns: None
        """
        super().__init__(canvas, num)
        _log(f"FigureManagerDesq created for figure num={num}")

    def show(self) -> None:
        """
        Override show() to prevent window display.

        This is called by ``plt.show()`` for interactive backends.
        We trigger a canvas draw to ensure the figure is rendered,
        but no window is created. The sink notification happens during draw.

        :returns: None
        """
        _log(f"show() called - triggering canvas.draw()")
        # Ensure figure is fully rendered
        self.canvas.draw()
        # No window to show - sink was notified in draw()

    def destroy(self) -> None:
        """
        Clean up any resources.

        For this headless backend, there are no resources to clean up.

        :returns: None
        """
        pass


# =============================================================================
# BACKEND ENTRY POINTS
# =============================================================================
#
# These functions are called by matplotlib when the backend is loaded.
# Names must match matplotlib's expected interface exactly.


def new_figure_manager(
    num: int,
    *args: Any,
    FigureClass: type = Figure,
    **kwargs: Any
) -> FigureManagerDesq:
    """
    Create a new figure manager for the given figure number.

    This is called by ``plt.figure()`` and ``plt.subplots()``.

    :param num: Figure number.
    :type num: int
    :param args: Positional arguments passed to Figure constructor.
    :param FigureClass: Figure class to instantiate. Defaults to matplotlib Figure.
    :type FigureClass: type
    :param kwargs: Keyword arguments passed to Figure constructor.

    :returns: A new FigureManagerDesq instance managing the created figure.
    :rtype: FigureManagerDesq

    .. note::
        This is a matplotlib backend entry point and must have this exact signature.
    """
    _log(f"new_figure_manager called: num={num}")
    fig = FigureClass(*args, **kwargs)
    canvas = FigureCanvasDesq(fig)
    manager = FigureManagerDesq(canvas, num)
    return manager


def new_figure_manager_given_figure(num: int, figure: Figure) -> FigureManagerDesq:
    """
    Create a new figure manager for an existing figure.

    This is called when matplotlib needs to manage a pre-existing Figure.

    :param num: Figure number to assign.
    :type num: int
    :param figure: Existing Figure instance.
    :type figure: Figure

    :returns: A new FigureManagerDesq instance managing the given figure.
    :rtype: FigureManagerDesq

    .. note::
        This is a matplotlib backend entry point and must have this exact signature.
    """
    _log(f"new_figure_manager_given_figure called: num={num}")
    canvas = FigureCanvasDesq(figure)
    manager = FigureManagerDesq(canvas, num)
    return manager


def show(*args: Any, block: Optional[bool] = None, **kwargs: Any) -> None:
    """
    Backend's ``plt.show()`` implementation.

    .. warning::
        **CRITICAL FIX**: Do NOT draw ALL figures. Only draw figures that haven't
        been drawn yet. This prevents cross-tab contamination where calling
        ``plt.show()`` in one tab would re-draw (and re-capture) figures from
        other tabs.

    For our headless backend, individual ``figure.draw()`` calls already
    trigger sink notifications. We only need to ensure NEW figures
    (that haven't been drawn) get their initial draw.

    :param args: Ignored positional arguments.
    :param block: Ignored (no event loop to block).
    :type block: Optional[bool]
    :param kwargs: Ignored keyword arguments.

    :returns: None

    .. note::
        Figures are tracked via a custom ``_desq_initial_draw_done`` attribute
        to determine if they need their initial draw.
    """
    from matplotlib._pylab_helpers import Gcf

    managers = list(Gcf.get_all_fig_managers())
    _log(f"show() called with {len(managers)} figures")

    # Only draw figures that haven't been drawn yet
    # We track this with a custom attribute on the figure
    for manager in managers:
        fig = manager.canvas.figure
        if not getattr(fig, '_desq_initial_draw_done', False):
            _log(f"Drawing figure {fig.number} (first time)")
            manager.canvas.draw()
            fig._desq_initial_draw_done = True
        else:
            _log(f"Skipping figure {fig.number} (already drawn)")


# -------------------------------------------------------------------------
# Required Backend Attributes
# -------------------------------------------------------------------------
# These module-level attributes are required by matplotlib's backend system

FigureCanvas: type = FigureCanvasDesq
"""Alias for :class:`FigureCanvasDesq` - required by matplotlib backend system."""

FigureManager: type = FigureManagerDesq
"""Alias for :class:`FigureManagerDesq` - required by matplotlib backend system."""

# Log that the backend was loaded
_log("BackendDesq module loaded successfully")


# =============================================================================
# OPTIONAL: HELPER FOR CAPTURING FIGURES
# =============================================================================


class FigureCaptureSink:
    """
    A simple sink that captures figures into a list.

    Useful for testing or batch capture scenarios where you want to
    collect all figures generated during a code block.

    Usage::

        sink = FigureCaptureSink()
        set_plot_sink(sink)
        # ... run plotting code ...
        figures = sink.get_figures()
        clear_plot_sink()

    :ivar figures: List of captured figures.
    :vartype figures: List[Figure]

    :ivar capture_on: Which event type to capture on.
    :vartype capture_on: str

    :ivar _seen: Set of figure IDs already captured (to avoid duplicates).
    :vartype _seen: Set[int]
    """

    def __init__(self, capture_on: str = 'draw') -> None:
        """
        Initialize the capture sink.

        :param capture_on: Which event to capture on - ``'draw'``, ``'draw_idle'``,
            or ``'both'``. Defaults to ``'draw'`` for complete renders only.
        :type capture_on: str

        :returns: None
        """
        self.figures: List[Figure] = []
        self.capture_on: str = capture_on
        self._seen: Set[int] = set()  # Avoid duplicates by tracking figure IDs

    def __call__(self, figure: Figure, event_type: str) -> None:
        """
        Sink callable - receives (figure, event_type).

        Captures the figure if the event type matches the capture criteria
        and the figure hasn't been captured yet.

        :param figure: The matplotlib Figure that was drawn.
        :type figure: Figure
        :param event_type: The type of draw event - ``'draw'`` or ``'draw_idle'``.
        :type event_type: str

        :returns: None
        """
        if self.capture_on == 'both' or event_type == self.capture_on:
            fig_id = id(figure)
            if fig_id not in self._seen:
                self._seen.add(fig_id)
                self.figures.append(figure)
                print(f"[FigureCaptureSink] Captured figure {fig_id}")

    def get_figures(self) -> List[Figure]:
        """
        Get captured figures and reset the sink.

        :returns: List of captured figures.
        :rtype: List[Figure]

        .. note::
            This method clears the internal state after returning.
            Call :meth:`clear` explicitly if you want to reset without
            retrieving figures.
        """
        figs = self.figures.copy()
        self.clear()
        return figs

    def clear(self) -> None:
        """
        Clear captured figures without returning them.

        Resets the internal figure list and seen-ID set.

        :returns: None
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
    It handles thread-safety automatically by using Qt's signal/slot
    mechanism with queued connections.

    Usage::

        from PyQt5.QtCore import QObject, pyqtSignal

        class PlotReceiver(QObject):
            figureReady = pyqtSignal(object, str)

        receiver = PlotReceiver()
        receiver.figureReady.connect(my_handler)  # Connect on GUI thread

        sink = QtSignalSink(receiver.figureReady)
        set_plot_sink(sink)

    :ivar signal: The Qt signal to emit when figures are drawn.
    :vartype signal: pyqtSignal

    :ivar _seen_draws: Set of figure IDs for debouncing.
    :vartype _seen_draws: Set[int]

    .. note::
        Figure copying is not supported. Qt canvases cannot be pickled,
        and figure isolation should be handled by detaching from matplotlib's
        global registry after the experiment completes.

    .. seealso::
        ``DesqTabAdv.isolate_matplotlib_figures`` for figure isolation approach.
    """

    def __init__(self, signal: Any, copy_figure: bool = False) -> None:
        """
        Initialize the Qt signal sink.

        :param signal: Qt signal to emit. Must accept ``(figure, event_type)`` arguments.
        :type signal: pyqtSignal
        :param copy_figure: **DEPRECATED** - ignored. Figure copying is not supported
            with Qt canvases. Use registry detachment instead.
        :type copy_figure: bool

        :returns: None

        .. deprecated::
            The ``copy_figure`` parameter is deprecated and ignored.
            Qt canvases cannot be pickled. Use ``isolate_matplotlib_figures()``
            after experiment completion instead.
        """
        self.signal = signal
        if copy_figure:
            print("[QtSignalSink] WARNING: copy_figure=True is not supported "
                  "(Qt canvases cannot be pickled). Figures will be passed by reference. "
                  "Use isolate_matplotlib_figures() after experiment completion instead.")
        self._seen_draws: Set[int] = set()

    def __call__(self, figure: Figure, event_type: str) -> None:
        """
        Sink callable - emits signal with figure.

        Only emits on 'draw' events (complete renders), not 'draw_idle' (partial).
        Implements debouncing to avoid duplicate notifications for the same figure.

        :param figure: The matplotlib Figure that was drawn.
        :type figure: Figure
        :param event_type: The type of draw event - ``'draw'`` or ``'draw_idle'``.
        :type event_type: str

        :returns: None

        .. note::
            Debouncing allows re-notification after 100ms via a QTimer cleanup.
            This prevents spam while still allowing legitimate redraws.
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

        # Emit signal (Qt handles thread-safe delivery via queued connection)
        # Figure is passed by reference - isolation handled separately
        self.signal.emit(figure, event_type)