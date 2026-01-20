"""
=================
FigureCarousel.py
=================
A horizontally scrollable carousel of figure thumbnails for multi-figure navigation.

Design Decisions:
- Carousel is hidden when only one figure exists (cleaner UI)
- Newest figure becomes active by default
- Clicking thumbnail does NOT re-run experiment, just switches display
- Full clear on rerun/replot to prevent cross-run figure mixing

Memory Management:
- Properly disposes QPixmaps when thumbnails are removed
- Figure references are stored but NOT owned (PlotManager handles lifecycle)
"""

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from typing import List, Optional, Any

from PyQt5.QtGui import QImage, QPixmap, QPainter
from PyQt5.QtCore import (
    Qt, qInfo,
    pyqtSignal, qWarning,
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

    Features:
    - Displays scaled figure snapshot
    - Visual selection indicator (border highlight)
    - Clickable to select figure
    - Proper memory management for QPixmap
    """

    clicked = pyqtSignal(int)  # Emits figure index when clicked

    MAX_WIDTH = 120  # Maximum thumbnail width
    MAX_HEIGHT = 80  # Maximum thumbnail height
    SELECTED_BORDER_WIDTH = 3
    NORMAL_BORDER_WIDTH = 1

    def __init__(self, index: int, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.index = index
        self._pixmap = pixmap
        self._selected = False

        self.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"Figure {index + 1}")

        if not pixmap.isNull():
            # Scale to fit within max bounds while keeping aspect ratio
            self._scaled_pixmap = pixmap.scaled(
                self.MAX_WIDTH, self.MAX_HEIGHT,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            # Set widget size to match the actual scaled pixmap size
            # Add small padding for border
            self.setFixedSize(
                self._scaled_pixmap.width() + 4,
                self._scaled_pixmap.height() + 4
            )
        else:
            self.setFixedSize(self.MAX_HEIGHT, self.MAX_HEIGHT)
            self._scaled_pixmap = pixmap

        self._update_style()

    def _update_style(self):
        """Update border style based on selection state."""
        if self._selected:
            self.setStyleSheet(f"""
                ThumbnailWidget {{
                    border: {self.SELECTED_BORDER_WIDTH}px solid #2196F3;
                    background-color: #E3F2FD;
                }}
            """)
        else:
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

    def setSelected(self, selected: bool):
        """Set the selection state of this thumbnail."""
        if self._selected != selected:
            self._selected = selected
            self._update_style()

    def isSelected(self) -> bool:
        """Return whether this thumbnail is selected."""
        return self._selected

    def mousePressEvent(self, event):
        """Handle mouse click to emit selection signal."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        """Paint the thumbnail image."""
        super().paintEvent(event)
        if not self._scaled_pixmap.isNull():
            painter = QPainter(self)
            # Center the pixmap in the widget
            x = (self.width() - self._scaled_pixmap.width()) // 2
            y = (self.height() - self._scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, self._scaled_pixmap)

    def cleanup(self):
        """Properly dispose of pixmap resources."""
        self._pixmap = QPixmap()  # Release original
        self._scaled_pixmap = QPixmap()  # Release scaled


class FigureCarousel(QWidget):
    """
    A horizontally scrollable carousel of figure thumbnails.

    Supports both matplotlib figures and PyQtGraph snapshot pixmaps.

    Usage:
        carousel.add_figure(mpl_figure)  # For matplotlib
        carousel.add_pixmap(qpixmap, identifier)  # For pyqtgraph snapshots
    """

    figure_selected = pyqtSignal(int)  # Emits index of selected figure

    CAROUSEL_HEIGHT = 100  # Total carousel height including padding

    def __init__(self, parent=None):
        super().__init__(parent)

        # Internal state
        self._thumbnails: List[ThumbnailWidget] = []
        self._figure_data: List[Any] = []  # Can be matplotlib figures or identifiers
        self._selected_index: int = -1

        self._setup_ui()

    def _setup_ui(self):
        """Initialize the carousel UI components."""
        self.setObjectName("FigureCarousel")
        self.setFixedHeight(self.CAROUSEL_HEIGHT)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 5, 0, 0)
        main_layout.setSpacing(0)

        # Label
        self._label = QLabel("Figures:")
        self._label.setObjectName("carousel_label")
        self._label.setStyleSheet("font-size: 10px; color: #666; padding-left: 5px;")
        main_layout.addWidget(self._label)

        # Scroll area for thumbnails
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

        # Container widget for thumbnails
        self._thumbnail_container = QWidget()
        self._thumbnail_container.setObjectName("thumbnail_container")
        self._thumbnail_layout = QHBoxLayout(self._thumbnail_container)
        self._thumbnail_layout.setContentsMargins(5, 5, 5, 5)
        self._thumbnail_layout.setSpacing(8)
        self._thumbnail_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Add stretch to keep thumbnails left-aligned
        self._thumbnail_layout.addStretch()

        self._scroll_area.setWidget(self._thumbnail_container)
        main_layout.addWidget(self._scroll_area)

        # Initially hidden (shown when multiple figures)
        self.hide()

    def add_figure(self, figure, make_active: bool = True) -> int:
        """
        Add a matplotlib figure to the carousel.

        Args:
            figure: matplotlib figure object
            make_active: If True, this figure becomes the active display

        Returns:
            Index of the added figure
        """
        # Generate thumbnail from figure
        thumbnail_pixmap = self._capture_figure_thumbnail(figure)
        return self._add_thumbnail(thumbnail_pixmap, figure, make_active)

    def add_pixmap(self, pixmap: QPixmap, identifier: Any = None, make_active: bool = True) -> int:
        """
        Add a pre-rendered pixmap to the carousel (for PyQtGraph).

        Args:
            pixmap: QPixmap of the figure snapshot
            identifier: Optional identifier to associate with this entry
            make_active: If True, this becomes the active selection

        Returns:
            Index of the added entry
        """
        return self._add_thumbnail(pixmap, identifier, make_active)

    def _add_thumbnail(self, pixmap: QPixmap, data: Any, make_active: bool) -> int:
        """Internal method to add a thumbnail widget."""
        # Create thumbnail widget
        index = len(self._thumbnails)
        thumbnail = ThumbnailWidget(index, pixmap, self._thumbnail_container)
        thumbnail.clicked.connect(self._on_thumbnail_clicked)

        # Store references
        self._thumbnails.append(thumbnail)
        self._figure_data.append(data)

        # Add to layout (before the stretch)
        self._thumbnail_layout.insertWidget(self._thumbnail_layout.count() - 1, thumbnail)

        # Update visibility
        self._update_visibility()

        # Make active if requested
        if make_active:
            self.select_figure(index)

        # Scroll to show the new thumbnail
        self._scroll_area.ensureWidgetVisible(thumbnail)

        return index

    def _capture_figure_thumbnail(self, figure) -> QPixmap:
        """
        Capture a thumbnail image from a matplotlib figure.

        Renders figure to RGBA buffer and converts to QPixmap.

        ROBUSTNESS: Always creates a fresh Agg canvas for rendering to avoid
        issues with deleted Qt canvases from previous embeddings.
        """
        try:
            import matplotlib
            from matplotlib.backends.backend_agg import FigureCanvasAgg

            # Check if figure is still valid
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
                pass  # Figure might not have a number or be partially deleted

            # ALWAYS create a fresh Agg canvas for rendering
            # This avoids issues with Qt canvases that have been deleted
            # Store original canvas to restore later
            original_canvas = figure.canvas

            try:
                # Create pure Agg canvas (no Qt dependency)
                agg_canvas = FigureCanvasAgg(figure)

                # Render to the Agg canvas
                agg_canvas.draw()

                # Get the RGBA buffer
                width, height = agg_canvas.get_width_height()
                buf = agg_canvas.buffer_rgba()

                # Convert to QImage
                qimage = QImage(buf, width, height, QImage.Format_RGBA8888)

                # Convert to QPixmap (copy to own the data)
                pixmap = QPixmap.fromImage(qimage.copy())

                return pixmap

            finally:
                # Restore original canvas if it exists and is valid
                try:
                    if original_canvas is not None:
                        figure.set_canvas(original_canvas)
                except (RuntimeError, AttributeError):
                    # Original canvas was deleted, leave the Agg canvas
                    pass

        except Exception as e:
            print(f"[FigureCarousel] Failed to capture figure thumbnail: {e}")
            # Return empty pixmap on failure
            return QPixmap()

    def _on_thumbnail_clicked(self, index: int):
        """Handle thumbnail click - select figure and emit signal."""
        self.select_figure(index)
        self.figure_selected.emit(index)

    def select_figure(self, index: int):
        """
        Select a figure by index.

        Updates visual selection state of all thumbnails.
        """
        if index < 0 or index >= len(self._thumbnails):
            return

        # Update selection state
        for i, thumbnail in enumerate(self._thumbnails):
            thumbnail.setSelected(i == index)

        self._selected_index = index

    def get_selected_index(self) -> int:
        """Return the currently selected figure index."""
        return self._selected_index

    def get_figure_data(self, index: int) -> Optional[Any]:
        """Get figure/data at the given index."""
        if 0 <= index < len(self._figure_data):
            return self._figure_data[index]
        return None

    def get_selected_figure_data(self) -> Optional[Any]:
        """Get the currently selected figure/data."""
        return self.get_figure_data(self._selected_index)

    def figure_count(self) -> int:
        """Return the number of figures in the carousel."""
        return len(self._figure_data)

    def _update_visibility(self):
        """
        Update carousel visibility based on figure count.

        Design: Hidden when 0 or 1 figures, shown when 2+ figures.
        """
        count = len(self._figure_data)
        if count > 1:
            self.show()
            self._label.setText(f"Figures ({count}):")
        else:
            self.hide()

    def clear(self, close_figures: bool = True):
        """
        Clear all figures and thumbnails from the carousel.

        CRITICAL: Called on rerun/replot to prevent cross-run mixing.

        Args:
            close_figures: If True, close matplotlib figures to remove from global registry.
                          This prevents old figures from being re-captured by new experiments.
        """
        import matplotlib.pyplot as plt

        # Use print instead of qInfo to avoid threading issues
        print(f"[FigureCarousel] Clearing carousel (close_figures={close_figures})...")

        # Close matplotlib figures FIRST before clearing references
        if close_figures:
            for data in self._figure_data:
                try:
                    # Check if it's a matplotlib figure
                    if hasattr(data, 'number'):  # matplotlib figures have a 'number' attribute
                        plt.close(data)
                        print(f"[FigureCarousel] Closed matplotlib figure {data.number}")
                except Exception as e:
                    print(f"[FigureCarousel] Failed to close figure: {e}")

        # Clear thumbnail widgets
        for thumbnail in self._thumbnails:
            thumbnail.cleanup()  # Dispose pixmaps
            try:
                thumbnail.clicked.disconnect()  # Disconnect signal
            except:
                pass
            self._thumbnail_layout.removeWidget(thumbnail)
            thumbnail.deleteLater()

        self._thumbnails.clear()

        # Clear figure references
        self._figure_data.clear()

        # Reset selection state
        self._selected_index = -1

        # Hide carousel
        self.hide()

        print("[FigureCarousel] Carousel cleared")

    def update_thumbnail(self, index: int, figure_or_pixmap):
        """
        Update the thumbnail for a specific figure (for live updates).

        Args:
            index: Index to update
            figure_or_pixmap: Either a matplotlib figure or a QPixmap
        """
        if not (0 <= index < len(self._thumbnails)):
            return

        # Get new pixmap
        if isinstance(figure_or_pixmap, QPixmap):
            new_pixmap = figure_or_pixmap
        else:
            new_pixmap = self._capture_figure_thumbnail(figure_or_pixmap)

        if new_pixmap.isNull():
            return

        old_thumbnail = self._thumbnails[index]

        # Create new thumbnail widget
        new_thumbnail = ThumbnailWidget(index, new_pixmap, self._thumbnail_container)
        new_thumbnail.clicked.connect(self._on_thumbnail_clicked)
        new_thumbnail.setSelected(old_thumbnail.isSelected())

        # Replace in layout
        layout_index = self._thumbnail_layout.indexOf(old_thumbnail)
        if layout_index >= 0:
            self._thumbnail_layout.removeWidget(old_thumbnail)
            self._thumbnail_layout.insertWidget(layout_index, new_thumbnail)

        # Cleanup old and update list
        old_thumbnail.cleanup()
        old_thumbnail.deleteLater()
        self._thumbnails[index] = new_thumbnail

        # Update figure reference if it's a matplotlib figure
        if not isinstance(figure_or_pixmap, QPixmap):
            self._figure_data[index] = figure_or_pixmap

    def has_figure(self, figure) -> bool:
        """Check if a figure is already in the carousel (by identity)."""
        fig_id = id(figure)
        for data in self._figure_data:
            if id(data) == fig_id:
                return True
        return False

    def find_figure_index(self, figure) -> int:
        """Find index of a figure by identity. Returns -1 if not found."""
        fig_id = id(figure)
        for i, data in enumerate(self._figure_data):
            if id(data) == fig_id:
                return i
        return -1