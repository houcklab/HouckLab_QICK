"""
=================
FigureCarousel.py
=================

A horizontally scrollable carousel of figure thumbnails for multi-figure navigation.

This module provides widgets for displaying and navigating between multiple matplotlib
figures or PyQtGraph snapshots in a thumbnail carousel interface.

Design Decisions
----------------
- Carousel is hidden when only one figure exists (cleaner UI)
- Newest figure becomes active by default
- Clicking thumbnail does NOT re-run experiment, just switches display
- Full clear on rerun/replot to prevent cross-run figure mixing

Memory Management
-----------------
- Properly disposes QPixmaps when thumbnails are removed
- Figure references are stored but NOT owned (PlotManager handles lifecycle)

.. seealso::
    :class:`ThumbnailWidget` for individual thumbnail display
    :class:`FigureCarousel` for the main carousel container
"""

from typing import List, Optional, Any, Union

from PyQt5.QtGui import QImage, QPixmap, QPainter
from PyQt5.QtCore import (
    Qt,
    pyqtSignal,
)
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QFrame,
)


class ThumbnailWidget(QFrame):
    """
    A clickable thumbnail widget that displays a figure preview.

    This widget renders a scaled snapshot of a matplotlib figure or PyQtGraph plot
    as a clickable thumbnail with visual selection state.

    Features:
        - Displays scaled figure snapshot
        - Visual selection indicator (border highlight)
        - Clickable to select figure
        - Proper memory management for QPixmap

    :ivar clicked: Signal emitted when the thumbnail is clicked, passing the figure index.
    :vartype clicked: pyqtSignal(int)
    :ivar MAX_WIDTH: Maximum thumbnail width in pixels.
    :vartype MAX_WIDTH: int
    :ivar MAX_HEIGHT: Maximum thumbnail height in pixels.
    :vartype MAX_HEIGHT: int
    :ivar SELECTED_BORDER_WIDTH: Border width when selected.
    :vartype SELECTED_BORDER_WIDTH: int
    :ivar NORMAL_BORDER_WIDTH: Border width when not selected.
    :vartype NORMAL_BORDER_WIDTH: int
    :ivar index: The index of this thumbnail in the carousel.
    :vartype index: int

    .. note::
        The pixmap is stored internally but ownership remains with the caller.
        Call :meth:`cleanup` to properly dispose of pixmap resources.
    """

    clicked = pyqtSignal(int)  # Emits figure index when clicked

    MAX_WIDTH: int = 120  # Maximum thumbnail width
    MAX_HEIGHT: int = 80  # Maximum thumbnail height
    SELECTED_BORDER_WIDTH: int = 3
    NORMAL_BORDER_WIDTH: int = 1

    def __init__(self, index: int, pixmap: QPixmap, parent: Optional[QWidget] = None) -> None:
        """
        Initialize a thumbnail widget.

        :param index: The index of this thumbnail in the carousel (0-based).
        :type index: int
        :param pixmap: The QPixmap to display as the thumbnail image.
        :type pixmap: QPixmap
        :param parent: Optional parent widget.
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)
        self.index: int = index
        self._pixmap: QPixmap = pixmap
        self._selected: bool = False

        self.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"Figure {index + 1}")

        if not pixmap.isNull():
            # Scale to fit within max bounds while keeping aspect ratio
            self._scaled_pixmap: QPixmap = pixmap.scaled(
                self.MAX_WIDTH, self.MAX_HEIGHT,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            # Set widget size to match the actual scaled pixmap size
            # Add small padding (4px total) for border display
            self.setFixedSize(
                self._scaled_pixmap.width() + 4,
                self._scaled_pixmap.height() + 4
            )
        else:
            # Null pixmap case: use default square size
            self.setFixedSize(self.MAX_HEIGHT, self.MAX_HEIGHT)
            self._scaled_pixmap = pixmap

        self._update_style()

    def _update_style(self) -> None:
        """
        Update border style based on selection state.

        Applies different CSS styling for selected vs unselected states,
        including hover effects for unselected thumbnails.
        """
        if self._selected:
            # Selected state: solid blue border with light blue background
            self.setStyleSheet(f"""
                ThumbnailWidget {{
                    border: {self.SELECTED_BORDER_WIDTH}px solid #2196F3;
                    background-color: #E3F2FD;
                }}
            """)
        else:
            # Normal state with hover effect
            self.setStyleSheet(f"""
                ThumbnailWidget {{
                    border: {self.NORMAL_BORDER_WIDTH}px solid #BDBDBD;
                    background-color: #FFFFFF;
                }}
                ThumbnailWidget:hover {{
                    border: {self.NORMAL_BORDER_WIDTH}px solid #64B5F6;
                    background-color: #F5F5F5;
                }}
            """)

    def setSelected(self, selected: bool) -> None:
        """
        Set the selection state of this thumbnail.

        :param selected: True to mark as selected, False otherwise.
        :type selected: bool

        .. note::
            Only updates styling if the state actually changes.
        """
        if self._selected != selected:
            self._selected = selected
            self._update_style()

    def isSelected(self) -> bool:
        """
        Return whether this thumbnail is selected.

        :returns: True if this thumbnail is currently selected.
        :rtype: bool
        """
        return self._selected

    def mousePressEvent(self, event) -> None:
        """
        Handle mouse click to emit selection signal.

        :param event: The mouse event.
        :type event: QMouseEvent

        .. note::
            Only left-clicks trigger the :attr:`clicked` signal.
        """
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        """
        Paint the thumbnail image.

        Draws the scaled pixmap centered within the widget bounds.

        :param event: The paint event.
        :type event: QPaintEvent
        """
        super().paintEvent(event)
        if not self._scaled_pixmap.isNull():
            painter = QPainter(self)
            # Center the pixmap in the widget accounting for border padding
            x = (self.width() - self._scaled_pixmap.width()) // 2
            y = (self.height() - self._scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, self._scaled_pixmap)

    def cleanup(self) -> None:
        """
        Properly dispose of pixmap resources.

        Releases both the original and scaled pixmaps by replacing them
        with empty QPixmap instances. Should be called before removing
        the widget from the carousel.

        .. note::
            This method should be called before :meth:`deleteLater` to ensure
            proper memory cleanup of Qt pixmap resources.
        """
        self._pixmap = QPixmap()  # Release original
        self._scaled_pixmap = QPixmap()  # Release scaled


class FigureCarousel(QWidget):
    """
    A horizontally scrollable carousel of figure thumbnails.

    Supports both matplotlib figures and PyQtGraph snapshot pixmaps.
    The carousel automatically shows/hides based on the number of figures
    (hidden for 0-1 figures, visible for 2+ figures).

    Usage::

        carousel = FigureCarousel()
        carousel.add_figure(mpl_figure)  # For matplotlib
        carousel.add_pixmap(qpixmap, identifier)  # For pyqtgraph snapshots
        carousel.figure_selected.connect(on_figure_changed)

    :ivar figure_selected: Signal emitted when a figure is selected, passing the index.
    :vartype figure_selected: pyqtSignal(int)
    :ivar CAROUSEL_HEIGHT: Total carousel height including padding.
    :vartype CAROUSEL_HEIGHT: int

    .. note::
        Figure references are stored but NOT owned by the carousel.
        The PlotManager or caller is responsible for figure lifecycle management.
    """

    figure_selected = pyqtSignal(int)  # Emits index of selected figure

    CAROUSEL_HEIGHT: int = 100  # Total carousel height including padding

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the figure carousel.

        :param parent: Optional parent widget.
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)

        # Internal state tracking
        self._thumbnails: List[ThumbnailWidget] = []
        self._figure_data: List[Any] = []  # Can be matplotlib figures or identifiers
        self._selected_index: int = -1

        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        Initialize the carousel UI components.

        Creates the layout hierarchy:
            - Main vertical layout
                - Label showing figure count
                - Scroll area (horizontal)
                    - Thumbnail container with horizontal layout
        """
        self.setObjectName("FigureCarousel")
        self.setFixedHeight(self.CAROUSEL_HEIGHT)

        # Main layout with minimal margins for compact appearance
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 5, 0, 0)
        main_layout.setSpacing(0)

        # Label showing "Figures:" or "Figures (N):"
        self._label = QLabel("Figures:")
        self._label.setObjectName("carousel_label")
        self._label.setStyleSheet("font-size: 10px; color: #666; padding-left: 5px;")
        main_layout.addWidget(self._label)

        # Scroll area for horizontal thumbnail navigation
        self._scroll_area = QScrollArea()
        self._scroll_area.setObjectName("carousel_scroll_area")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #FAFAFA;
                border-top: 1px solid #E0E0E0;
            }
        """)

        # Container widget for thumbnails with horizontal layout
        self._thumbnail_container = QWidget()
        self._thumbnail_container.setObjectName("thumbnail_container")
        self._thumbnail_layout = QHBoxLayout(self._thumbnail_container)
        self._thumbnail_layout.setContentsMargins(5, 5, 5, 5)
        self._thumbnail_layout.setSpacing(8)
        self._thumbnail_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Add stretch at end to keep thumbnails left-aligned when few items
        self._thumbnail_layout.addStretch()

        self._scroll_area.setWidget(self._thumbnail_container)
        main_layout.addWidget(self._scroll_area)

        # Initially hidden (shown when multiple figures exist)
        self.hide()

    def add_figure(self, figure: Any, make_active: bool = True) -> int:
        """
        Add a matplotlib figure to the carousel.

        Generates a thumbnail by rendering the figure to an image buffer
        and creates a clickable thumbnail widget.

        :param figure: Matplotlib figure object to add.
        :type figure: matplotlib.figure.Figure
        :param make_active: If True, this figure becomes the active display.
        :type make_active: bool
        :returns: Index of the added figure in the carousel.
        :rtype: int

        .. seealso::
            :meth:`add_pixmap` for adding pre-rendered PyQtGraph snapshots.
        """
        # Generate thumbnail from figure using Agg backend
        thumbnail_pixmap = self._capture_figure_thumbnail(figure)
        return self._add_thumbnail(thumbnail_pixmap, figure, make_active)

    def add_pixmap(self, pixmap: QPixmap, identifier: Any = None, make_active: bool = True) -> int:
        """
        Add a pre-rendered pixmap to the carousel (for PyQtGraph).

        :param pixmap: QPixmap of the figure snapshot.
        :type pixmap: QPixmap
        :param identifier: Optional identifier to associate with this entry.
            Can be used to track which PyQtGraph widget this pixmap came from.
        :type identifier: Any
        :param make_active: If True, this becomes the active selection.
        :type make_active: bool
        :returns: Index of the added entry in the carousel.
        :rtype: int

        .. seealso::
            :meth:`add_figure` for adding matplotlib figures.
        """
        return self._add_thumbnail(pixmap, identifier, make_active)

    def _add_thumbnail(self, pixmap: QPixmap, data: Any, make_active: bool) -> int:
        """
        Internal method to add a thumbnail widget.

        :param pixmap: The thumbnail image to display.
        :type pixmap: QPixmap
        :param data: Associated data (matplotlib figure or identifier).
        :type data: Any
        :param make_active: Whether to make this the active selection.
        :type make_active: bool
        :returns: Index of the newly added thumbnail.
        :rtype: int
        """
        # Create thumbnail widget with next available index
        index = len(self._thumbnails)
        thumbnail = ThumbnailWidget(index, pixmap, self._thumbnail_container)
        thumbnail.clicked.connect(self._on_thumbnail_clicked)

        # Store references for later retrieval
        self._thumbnails.append(thumbnail)
        self._figure_data.append(data)

        # Insert before the stretch widget to maintain left alignment
        # The stretch is always at count-1, so insert at count-1
        self._thumbnail_layout.insertWidget(self._thumbnail_layout.count() - 1, thumbnail)

        # Update visibility (show carousel if now 2+ figures)
        self._update_visibility()

        # Make active if requested (typically True for newest figure)
        if make_active:
            self.select_figure(index)

        # Scroll to show the new thumbnail
        self._scroll_area.ensureWidgetVisible(thumbnail)

        return index

    def _capture_figure_thumbnail(self, figure: Any) -> QPixmap:
        """
        Capture a thumbnail image from a matplotlib figure.

        Renders figure to RGBA buffer using a fresh Agg canvas and converts
        to QPixmap. This approach avoids issues with Qt canvases that may
        have been deleted from previous embeddings.

        :param figure: Matplotlib figure to capture.
        :type figure: matplotlib.figure.Figure
        :returns: QPixmap containing the rendered figure, or empty QPixmap on failure.
        :rtype: QPixmap

        .. note::
            **ROBUSTNESS**: Always creates a fresh Agg canvas for rendering to avoid
            issues with deleted Qt canvases from previous embeddings. The original
            canvas is restored after rendering when possible.

        .. warning::
            If the figure has been closed or is no longer in matplotlib's registry,
            an empty QPixmap will be returned.
        """
        try:
            import matplotlib
            from matplotlib.backends.backend_agg import FigureCanvasAgg

            # Validate figure is not None
            if figure is None:
                print("[FigureCarousel] Cannot capture thumbnail: figure is None")
                return QPixmap()

            # Check if figure is still in matplotlib's registry
            import matplotlib.pyplot as plt
            try:
                fig_num = figure.number
                if fig_num not in plt.get_fignums():
                    print(f"[FigureCarousel] Figure {fig_num} no longer in registry")
                    return QPixmap()
            except (AttributeError, RuntimeError):
                # Figure might not have a number or be partially deleted
                # Continue anyway and let the rendering fail gracefully
                pass

            # CRITICAL: Always create a fresh Agg canvas for rendering
            # This avoids RuntimeError from deleted Qt canvases
            original_canvas = figure.canvas

            try:
                # Create pure Agg canvas (no Qt dependency)
                agg_canvas = FigureCanvasAgg(figure)

                # Render the figure to the Agg canvas buffer
                agg_canvas.draw()

                # Get the RGBA buffer dimensions and data
                width, height = agg_canvas.get_width_height()
                buf = agg_canvas.buffer_rgba()

                # Convert RGBA buffer to QImage
                qimage = QImage(buf, width, height, QImage.Format_RGBA8888)

                # Convert to QPixmap, using copy() to own the data
                # (buffer may be invalidated when canvas is destroyed)
                pixmap = QPixmap.fromImage(qimage.copy())

                return pixmap

            finally:
                # Restore original canvas if it exists and is valid
                # This maintains figure's connection to any existing Qt canvas
                try:
                    if original_canvas is not None:
                        figure.set_canvas(original_canvas)
                except (RuntimeError, AttributeError):
                    # Original canvas was deleted, leave the Agg canvas attached
                    pass

        except Exception as e:
            print(f"[FigureCarousel] Failed to capture figure thumbnail: {e}")
            # Return empty pixmap on failure
            return QPixmap()

    def _on_thumbnail_clicked(self, index: int) -> None:
        """
        Handle thumbnail click - select figure and emit signal.

        :param index: Index of the clicked thumbnail.
        :type index: int
        """
        self.select_figure(index)
        self.figure_selected.emit(index)

    def select_figure(self, index: int) -> None:
        """
        Select a figure by index.

        Updates visual selection state of all thumbnails, deselecting
        the previously selected thumbnail and selecting the new one.

        :param index: Index of the figure to select.
        :type index: int

        .. note::
            If index is out of range, this method silently returns without error.
        """
        if index < 0 or index >= len(self._thumbnails):
            return

        # Update selection state for all thumbnails
        for i, thumbnail in enumerate(self._thumbnails):
            thumbnail.setSelected(i == index)

        self._selected_index = index

    def get_selected_index(self) -> int:
        """
        Return the currently selected figure index.

        :returns: Index of the selected figure, or -1 if none selected.
        :rtype: int
        """
        return self._selected_index

    def get_figure_data(self, index: int) -> Optional[Any]:
        """
        Get figure/data at the given index.

        :param index: Index of the figure data to retrieve.
        :type index: int
        :returns: The figure data at the index, or None if index is invalid.
        :rtype: Optional[Any]
        """
        if 0 <= index < len(self._figure_data):
            return self._figure_data[index]
        return None

    def get_selected_figure_data(self) -> Optional[Any]:
        """
        Get the currently selected figure/data.

        :returns: The data associated with the selected figure, or None.
        :rtype: Optional[Any]
        """
        return self.get_figure_data(self._selected_index)

    def figure_count(self) -> int:
        """
        Return the number of figures in the carousel.

        :returns: Count of figures currently in the carousel.
        :rtype: int
        """
        return len(self._figure_data)

    def _update_visibility(self) -> None:
        """
        Update carousel visibility based on figure count.

        Design: Hidden when 0 or 1 figures, shown when 2+ figures.
        Also updates the label to show the current count.
        """
        count = len(self._figure_data)
        if count > 1:
            self.show()
            self._label.setText(f"Figures ({count}):")
        else:
            self.hide()

    def clear(self, close_figures: bool = True) -> None:
        """
        Clear all figures and thumbnails from the carousel.

        This method is called on rerun/replot to prevent cross-run mixing
        of figures from different experiment runs.

        :param close_figures: If True, close matplotlib figures to remove from
            global registry. This prevents old figures from being re-captured
            by new experiments.
        :type close_figures: bool

        .. warning::
            **CRITICAL**: This must be called on rerun/replot to prevent
            cross-run figure mixing which can cause confusing UI behavior.

        .. note::
            Uses print() instead of qInfo() to avoid threading issues when
            called from non-main threads.
        """
        import matplotlib.pyplot as plt

        # Use print instead of qInfo to avoid threading issues
        print(f"[FigureCarousel] Clearing carousel (close_figures={close_figures})...")

        # Close matplotlib figures FIRST before clearing references
        # This removes them from plt.get_fignums() global registry
        if close_figures:
            for data in self._figure_data:
                try:
                    # Check if it's a matplotlib figure (they have a 'number' attribute)
                    if hasattr(data, 'number'):
                        plt.close(data)
                        print(f"[FigureCarousel] Closed matplotlib figure {data.number}")
                except Exception as e:
                    print(f"[FigureCarousel] Failed to close figure: {e}")

        # Clear thumbnail widgets with proper cleanup
        for thumbnail in self._thumbnails:
            thumbnail.cleanup()  # Dispose pixmaps to free memory
            try:
                thumbnail.clicked.disconnect()  # Disconnect signal to prevent dangling refs
            except TypeError:
                pass
            self._thumbnail_layout.removeWidget(thumbnail)
            thumbnail.deleteLater()

        self._thumbnails.clear()

        # Clear figure references (does not affect figure lifecycle)
        self._figure_data.clear()

        # Reset selection state to "nothing selected"
        self._selected_index = -1

        # Hide carousel since there are no figures
        self.hide()

        print("[FigureCarousel] Carousel cleared")

    def update_thumbnail(self, index: int, figure_or_pixmap: Union[QPixmap, Any]) -> None:
        """
        Update the thumbnail for a specific figure (for live updates).

        Creates a new thumbnail widget with the updated image and replaces
        the old one at the same position in the layout.

        :param index: Index of the thumbnail to update.
        :type index: int
        :param figure_or_pixmap: Either a matplotlib figure or a QPixmap.
            If a figure, a new thumbnail will be captured from it.
        :type figure_or_pixmap: Union[QPixmap, matplotlib.figure.Figure]

        .. note::
            The selection state of the thumbnail is preserved during the update.
        """
        if not (0 <= index < len(self._thumbnails)):
            return

        # Get new pixmap either directly or by capturing from figure
        if isinstance(figure_or_pixmap, QPixmap):
            new_pixmap = figure_or_pixmap
        else:
            new_pixmap = self._capture_figure_thumbnail(figure_or_pixmap)

        if new_pixmap.isNull():
            return

        old_thumbnail = self._thumbnails[index]

        # Create new thumbnail widget preserving selection state
        new_thumbnail = ThumbnailWidget(index, new_pixmap, self._thumbnail_container)
        new_thumbnail.clicked.connect(self._on_thumbnail_clicked)
        new_thumbnail.setSelected(old_thumbnail.isSelected())

        # Replace in layout at the same position
        layout_index = self._thumbnail_layout.indexOf(old_thumbnail)
        if layout_index >= 0:
            self._thumbnail_layout.removeWidget(old_thumbnail)
            self._thumbnail_layout.insertWidget(layout_index, new_thumbnail)

        # Cleanup old thumbnail and update internal list
        old_thumbnail.cleanup()
        old_thumbnail.deleteLater()
        self._thumbnails[index] = new_thumbnail

        # Update figure reference if it's a matplotlib figure (not a pixmap)
        if not isinstance(figure_or_pixmap, QPixmap):
            self._figure_data[index] = figure_or_pixmap

    def has_figure(self, figure: Any) -> bool:
        """
        Check if a figure is already in the carousel (by identity).

        Uses Python object identity (id()) for comparison, not equality.

        :param figure: Figure to check for.
        :type figure: Any
        :returns: True if the figure is in the carousel.
        :rtype: bool
        """
        fig_id = id(figure)
        for data in self._figure_data:
            if id(data) == fig_id:
                return True
        return False

    def find_figure_index(self, figure: Any) -> int:
        """
        Find index of a figure by identity.

        Uses Python object identity (id()) for comparison, not equality.

        :param figure: Figure to find.
        :type figure: Any
        :returns: Index of the figure, or -1 if not found.
        :rtype: int
        """
        fig_id = id(figure)
        for i, data in enumerate(self._figure_data):
            if id(data) == fig_id:
                return i
        return -1