"""
===============
ImageViewTab.py
===============

A simple tab widget for displaying image files (.png, .jpg, .jpeg, .gif, .bmp, .svg).

Uses Qt's native image handling for efficient display with zoom and pan support.
This module provides a read-only image viewer that integrates with the Desq
tab system for viewing image files alongside experiment data.

Features
--------

- Supports common image formats: PNG, JPG, JPEG, GIF, BMP, SVG, WebP
- Zoom controls (fit to view, 100%, zoom in/out)
- Scroll/pan for large images
- Ctrl+scroll wheel zooming
- Dark theme compatible

.. seealso::

    :class:`QDesqTab` - The main experiment tab class this is designed to be
    compatible with.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QSlider, QFrame, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QPalette, QColor, QWheelEvent
from PyQt5.QtSvg import QSvgWidget

if TYPE_CHECKING:
    from matplotlib.figure import Figure


class ImageViewTab(QWidget):
    """
    A tab widget for viewing image files.

    This widget provides a complete image viewing solution with zoom controls
    and scroll/pan support. It is designed to be compatible with the Desq
    tab system, implementing stub methods for experiment-related functionality.

    :ivar updated_tab: Signal for tab compatibility (not used for images).
    :vartype updated_tab: pyqtSignal

    :ivar SUPPORTED_EXTENSIONS: Class-level list of supported file extensions.
    :vartype SUPPORTED_EXTENSIONS: List[str]

    :ivar tab_name: Display name for the tab (defaults to filename).
    :vartype tab_name: str

    :ivar experiment_obj: Always None - required for tab interface compatibility.
    :vartype experiment_obj: None

    :ivar experiment_config_panel: Minimal stub config panel for tab compatibility.
    :vartype experiment_config_panel: _DummyConfigPanel

    :ivar file_path: Absolute path to the image file being displayed.
    :vartype file_path: str

    :ivar _original_pixmap: The original loaded image (None for SVG files).
    :vartype _original_pixmap: Optional[QPixmap]

    :ivar _current_scale: Current zoom scale factor (1.0 = 100%).
    :vartype _current_scale: float

    :ivar _is_svg: Whether the loaded file is an SVG image.
    :vartype _is_svg: bool

    :ivar filename_label: Label displaying the filename in the toolbar.
    :vartype filename_label: QLabel

    :ivar fit_button: Button to fit image to viewport.
    :vartype fit_button: QPushButton

    :ivar zoom_out_button: Button to zoom out by 25%.
    :vartype zoom_out_button: QPushButton

    :ivar zoom_label: Label showing current zoom percentage.
    :vartype zoom_label: QLabel

    :ivar zoom_in_button: Button to zoom in by 25%.
    :vartype zoom_in_button: QPushButton

    :ivar actual_size_button: Button to reset to 100% zoom.
    :vartype actual_size_button: QPushButton

    :ivar scroll_area: Scroll area containing the image for pan support.
    :vartype scroll_area: QScrollArea

    :ivar image_widget: The widget displaying the actual image
        (QLabel for raster, QSvgWidget for SVG).
    :vartype image_widget: Union[QLabel, QSvgWidget]

    Example::

        # Create an image viewer tab
        tab = ImageViewTab("/path/to/image.png")

        # Add to tab widget
        tab_widget.addTab(tab, tab.tab_name)
    """

    #: Signal emitted when tab is updated (required for tab compatibility, not used).
    updated_tab: pyqtSignal = pyqtSignal()

    #: List of supported image file extensions (lowercase with dot prefix).
    SUPPORTED_EXTENSIONS: List[str] = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp']

    def __init__(self, file_path: str, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the ImageViewTab.

        :param file_path: Path to the image file to display.
        :type file_path: str
        :param parent: Parent widget for Qt object hierarchy.
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)

        self.file_path: str = file_path
        self.tab_name: str = os.path.basename(file_path)

        # Required for tab compatibility - images are not experiments
        self.experiment_obj: None = None
        self.experiment_config_panel: _DummyConfigPanel = _DummyConfigPanel()  # Minimal stub for compatibility

        # Image state
        self._original_pixmap: Optional[QPixmap] = None
        self._current_scale: float = 1.0
        self._is_svg: bool = file_path.lower().endswith('.svg')

        self._setup_ui()
        self._load_image()

    def _setup_ui(self) -> None:
        """
        Set up the UI components.

        Creates the following layout structure:

        - Toolbar with filename label and zoom controls
        - Scroll area containing the image widget

        The image widget type depends on file format:

        - SVG files use QSvgWidget for proper vector rendering
        - All other formats use QLabel with QPixmap
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === Toolbar ===
        toolbar = QFrame()
        toolbar.setObjectName("image_toolbar")
        toolbar.setFrameShape(QFrame.NoFrame)
        toolbar.setFixedHeight(36)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(8)

        # File name label (left side of toolbar)
        self.filename_label: QLabel = QLabel(self.tab_name)
        self.filename_label.setStyleSheet("color: #888; font-size: 11px;")
        toolbar_layout.addWidget(self.filename_label)

        toolbar_layout.addStretch()

        # === Zoom controls (right side of toolbar) ===
        self.fit_button: QPushButton = QPushButton("Fit")
        self.fit_button.setFixedSize(40, 24)
        self.fit_button.setToolTip("Fit image to view")
        self.fit_button.clicked.connect(self._fit_to_view)
        toolbar_layout.addWidget(self.fit_button)

        self.zoom_out_button: QPushButton = QPushButton("-")
        self.zoom_out_button.setFixedSize(35, 24)
        self.zoom_out_button.setToolTip("Zoom out")
        self.zoom_out_button.clicked.connect(self._zoom_out)
        toolbar_layout.addWidget(self.zoom_out_button)

        self.zoom_label: QLabel = QLabel("100%")
        self.zoom_label.setFixedWidth(50)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setStyleSheet("font-size: 11px;")
        toolbar_layout.addWidget(self.zoom_label)

        self.zoom_in_button: QPushButton = QPushButton("+")
        self.zoom_in_button.setFixedSize(35, 24)
        self.zoom_in_button.setToolTip("Zoom in")
        self.zoom_in_button.clicked.connect(self._zoom_in)
        toolbar_layout.addWidget(self.zoom_in_button)

        self.actual_size_button: QPushButton = QPushButton("1:1")
        self.actual_size_button.setFixedSize(40, 24)
        self.actual_size_button.setToolTip("Actual size (100%)")
        self.actual_size_button.clicked.connect(self._actual_size)
        toolbar_layout.addWidget(self.actual_size_button)

        layout.addWidget(toolbar)

        # === Scroll area for the image ===
        self.scroll_area: QScrollArea = QScrollArea()
        self.scroll_area.setObjectName("image_scroll_area")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
            }
        """)

        # Image display widget - type depends on whether file is SVG
        if self._is_svg:
            self.image_widget: Union[QLabel, QSvgWidget] = QSvgWidget()
            self.image_widget.setStyleSheet("background-color: transparent;")
        else:
            self.image_widget = QLabel()
            self.image_widget.setAlignment(Qt.AlignCenter)
            self.image_widget.setStyleSheet("background-color: transparent;")

        self.scroll_area.setWidget(self.image_widget)
        layout.addWidget(self.scroll_area)

    def _load_image(self) -> None:
        """
        Load the image from file.

        For SVG files, uses QSvgWidget.load() directly.
        For raster images, loads into a QPixmap for scaling support.

        After loading, schedules a fit-to-view operation with a short delay
        to allow the layout to settle first.

        .. note::

            The 100ms delay before fit_to_view is a workaround for Qt layout
            timing - the scroll area viewport size may not be accurate
            immediately after widget creation.
        """
        if not os.path.isfile(self.file_path):
            self._show_error(f"File not found: {self.file_path}")
            return

        try:
            if self._is_svg:
                self.image_widget.load(self.file_path)
                # Get default size from SVG
                default_size: QSize = self.image_widget.sizeHint()
                if default_size.isValid() and default_size.width() > 0:
                    self.image_widget.setFixedSize(default_size)
            else:
                self._original_pixmap = QPixmap(self.file_path)
                if self._original_pixmap.isNull():
                    self._show_error(f"Failed to load image: {self.file_path}")
                    return

                self.image_widget.setPixmap(self._original_pixmap)

            # Initial fit to view after a short delay to let the layout settle
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, self._fit_to_view)

        except Exception as e:
            self._show_error(f"Error loading image: {e}")

    def _show_error(self, message: str) -> None:
        """
        Display an error message in place of the image.

        Only works for non-SVG images where image_widget is a QLabel.

        :param message: The error message to display.
        :type message: str
        """
        if isinstance(self.image_widget, QLabel):
            self.image_widget.setText(message)
            self.image_widget.setStyleSheet("color: #ff6666; font-size: 14px; padding: 20px;")

    def _fit_to_view(self) -> None:
        """
        Scale image to fit within the scroll area.

        Calculates the scale factor needed to fit the image within the
        viewport while maintaining aspect ratio. Applies a 95% factor
        to leave a small margin around the image.
        """
        if self._is_svg:
            # For SVG, scale to fit viewport
            viewport_size: QSize = self.scroll_area.viewport().size()
            svg_size: QSize = self.image_widget.sizeHint()
            if svg_size.isValid() and svg_size.width() > 0 and svg_size.height() > 0:
                scale_w: float = viewport_size.width() / svg_size.width()
                scale_h: float = viewport_size.height() / svg_size.height()
                # 95% margin factor to leave small border around image
                scale: float = min(scale_w, scale_h) * 0.95
                self._current_scale = scale
                new_size = QSize(int(svg_size.width() * scale), int(svg_size.height() * scale))
                self.image_widget.setFixedSize(new_size)
                self._update_zoom_label()
        else:
            if self._original_pixmap is None or self._original_pixmap.isNull():
                return

            viewport_size = self.scroll_area.viewport().size()
            pixmap_size: QSize = self._original_pixmap.size()

            # Calculate scale to fit with 95% margin
            scale_w = viewport_size.width() / pixmap_size.width()
            scale_h = viewport_size.height() / pixmap_size.height()
            scale = min(scale_w, scale_h) * 0.95

            self._current_scale = scale
            self._apply_scale()

    def _actual_size(self) -> None:
        """
        Show image at 100% (actual size).

        Resets the zoom scale to 1.0 and applies the scaling.
        """
        self._current_scale = 1.0
        self._apply_scale()

    def _zoom_in(self) -> None:
        """
        Zoom in by 25%.

        Increases the current scale by a factor of 1.25, with a maximum
        scale limit of 10.0 (1000% zoom).
        """
        self._current_scale = min(self._current_scale * 1.25, 10.0)
        self._apply_scale()

    def _zoom_out(self) -> None:
        """
        Zoom out by 25%.

        Decreases the current scale by a factor of 1.25, with a minimum
        scale limit of 0.1 (10% zoom).
        """
        self._current_scale = max(self._current_scale / 1.25, 0.1)
        self._apply_scale()

    def _apply_scale(self) -> None:
        """
        Apply the current scale to the image.

        For SVG images, resizes the QSvgWidget to the scaled size.
        For raster images, creates a scaled copy of the original pixmap
        using smooth transformation for quality.
        """
        if self._is_svg:
            svg_size: QSize = self.image_widget.sizeHint()
            if svg_size.isValid():
                new_size = QSize(
                    int(svg_size.width() * self._current_scale),
                    int(svg_size.height() * self._current_scale)
                )
                self.image_widget.setFixedSize(new_size)
        else:
            if self._original_pixmap is None or self._original_pixmap.isNull():
                return

            # Scale the original pixmap (not the currently displayed one)
            # to avoid quality degradation from repeated scaling
            new_size = self._original_pixmap.size() * self._current_scale
            scaled_pixmap: QPixmap = self._original_pixmap.scaled(
                new_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_widget.setPixmap(scaled_pixmap)

        self._update_zoom_label()

    def _update_zoom_label(self) -> None:
        """
        Update the zoom percentage label.

        Displays the current scale as an integer percentage.
        """
        self.zoom_label.setText(f"{int(self._current_scale * 100)}%")

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        Handle mouse wheel for zooming when Ctrl is held.

        When the Control modifier is active, scroll wheel up zooms in
        and scroll wheel down zooms out. Without Control, the event
        is passed to the parent for normal scroll behavior.

        :param event: The wheel event from Qt.
        :type event: QWheelEvent
        """
        if event.modifiers() & Qt.ControlModifier:
            delta: int = event.angleDelta().y()
            if delta > 0:
                self._zoom_in()
            elif delta < 0:
                self._zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    # =========================================================================
    # Tab compatibility methods
    # =========================================================================
    # These methods are required stubs to maintain compatibility with the
    # Desq tab system, which expects all tabs to have certain methods even
    # if they are not applicable to non-experiment content like images.

    def predict_runtime(self, config: Dict[str, Any]) -> None:
        """
        Stub for tab compatibility.

        Images do not have runtime predictions. This method exists only
        to satisfy the tab interface contract.

        :param config: Configuration dictionary (ignored).
        :type config: Dict[str, Any]
        """
        pass

    def receive_figure(
        self,
        figure: 'Figure',
        event_type: str,
        session_id: int
    ) -> None:
        """
        Stub for tab compatibility.

        Images do not receive matplotlib figures. This method exists only
        to satisfy the tab interface contract.

        :param figure: The matplotlib figure (ignored).
        :type figure: matplotlib.figure.Figure
        :param event_type: The event type string (ignored).
        :type event_type: str
        :param session_id: The session ID (ignored).
        :type session_id: int
        """
        pass

    def start_plot_session(self) -> None:
        """
        Stub for tab compatibility.

        Images do not have plot sessions. This method exists only
        to satisfy the tab interface contract.

        :returns: Always returns None.
        :rtype: None
        """
        return None

    def isolate_matplotlib_figures(self) -> None:
        """
        Stub for tab compatibility.

        Images do not have matplotlib figures to isolate. This method
        exists only to satisfy the tab interface contract.
        """
        pass


class _DummyConfigPanel:
    """
    Minimal stub config panel for tab compatibility.

    This class provides a minimal implementation of the config panel
    interface that the Desq tab system expects. It does nothing but
    prevents AttributeError when the tab system tries to interact
    with config panels.

    :ivar config: Empty configuration dictionary.
    :vartype config: Dict[str, Any]

    .. note::

        This is an internal class and should not be instantiated directly
        outside of :class:`ImageViewTab`.
    """

    def __init__(self) -> None:
        """
        Initialize the dummy config panel with an empty config.
        """
        self.config: Dict[str, Any] = {}

    def update_config_dict(
        self,
        config: Dict[str, Any],
        reset: bool = False
    ) -> None:
        """
        Stub method for config panel compatibility.

        :param config: Configuration dictionary (ignored).
        :type config: Dict[str, Any]
        :param reset: Whether to reset the config (ignored).
        :type reset: bool
        """
        pass

    def populate_config_view(self) -> None:
        """
        Stub method for config panel compatibility.

        Does nothing - there is no config view to populate.
        """
        pass