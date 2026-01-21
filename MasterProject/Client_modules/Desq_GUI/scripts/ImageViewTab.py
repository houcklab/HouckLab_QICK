"""
===============
ImageViewTab.py
===============

A simple tab widget for displaying image files (.png, .jpg, .jpeg, .gif, .bmp, .svg).
Uses Qt's native image handling for efficient display with zoom and pan support.
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QSlider, QFrame, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QPalette, QColor
from PyQt5.QtSvg import QSvgWidget


class ImageViewTab(QWidget):
    """
    A tab widget for viewing image files.

    Features:
    - Supports common image formats: PNG, JPG, JPEG, GIF, BMP, SVG
    - Zoom controls (fit to view, 100%, zoom in/out)
    - Scroll/pan for large images
    - Dark theme compatible

    Attributes:
        tab_name (str): Display name for the tab
        experiment_obj: Always None (required for tab compatibility)
        file_path (str): Path to the image file
    """

    # Required signal for tab compatibility (though not used for images)
    updated_tab = pyqtSignal()

    # Supported image extensions
    SUPPORTED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp']

    def __init__(self, file_path: str, parent=None):
        """
        Initialize the ImageViewTab.

        :param file_path: Path to the image file
        :type file_path: str
        :param parent: Parent widget
        :type parent: QWidget
        """
        super().__init__(parent)

        self.file_path = file_path
        self.tab_name = os.path.basename(file_path)

        # Required for tab compatibility - images are not experiments
        self.experiment_obj = None
        self.experiment_config_panel = _DummyConfigPanel()  # Minimal stub for compatibility

        # Image state
        self._original_pixmap = None
        self._current_scale = 1.0
        self._is_svg = file_path.lower().endswith('.svg')

        self._setup_ui()
        self._load_image()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("image_toolbar")
        toolbar.setFrameShape(QFrame.NoFrame)
        toolbar.setFixedHeight(36)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(8)

        # File name label
        self.filename_label = QLabel(self.tab_name)
        self.filename_label.setStyleSheet("color: #888; font-size: 11px;")
        toolbar_layout.addWidget(self.filename_label)

        toolbar_layout.addStretch()

        # Zoom controls
        self.fit_button = QPushButton("Fit")
        self.fit_button.setFixedSize(40, 24)
        self.fit_button.setToolTip("Fit image to view")
        self.fit_button.clicked.connect(self._fit_to_view)
        toolbar_layout.addWidget(self.fit_button)

        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setFixedSize(35, 24)
        self.zoom_out_button.setToolTip("Zoom out")
        self.zoom_out_button.clicked.connect(self._zoom_out)
        toolbar_layout.addWidget(self.zoom_out_button)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(50)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setStyleSheet("font-size: 11px;")
        toolbar_layout.addWidget(self.zoom_label)

        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setFixedSize(35, 24)
        self.zoom_in_button.setToolTip("Zoom in")
        self.zoom_in_button.clicked.connect(self._zoom_in)
        toolbar_layout.addWidget(self.zoom_in_button)

        self.actual_size_button = QPushButton("1:1")
        self.actual_size_button.setFixedSize(40, 24)
        self.actual_size_button.setToolTip("Actual size (100%)")
        self.actual_size_button.clicked.connect(self._actual_size)
        toolbar_layout.addWidget(self.actual_size_button)

        layout.addWidget(toolbar)

        # Scroll area for the image
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("image_scroll_area")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
            }
        """)

        # Image display widget
        if self._is_svg:
            self.image_widget = QSvgWidget()
            self.image_widget.setStyleSheet("background-color: transparent;")
        else:
            self.image_widget = QLabel()
            self.image_widget.setAlignment(Qt.AlignCenter)
            self.image_widget.setStyleSheet("background-color: transparent;")

        self.scroll_area.setWidget(self.image_widget)
        layout.addWidget(self.scroll_area)

    def _load_image(self):
        """Load the image from file."""
        if not os.path.isfile(self.file_path):
            self._show_error(f"File not found: {self.file_path}")
            return

        try:
            if self._is_svg:
                self.image_widget.load(self.file_path)
                # Get default size from SVG
                default_size = self.image_widget.sizeHint()
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

    def _show_error(self, message: str):
        """Display an error message in place of the image."""
        if isinstance(self.image_widget, QLabel):
            self.image_widget.setText(message)
            self.image_widget.setStyleSheet("color: #ff6666; font-size: 14px; padding: 20px;")

    def _fit_to_view(self):
        """Scale image to fit within the scroll area."""
        if self._is_svg:
            # For SVG, scale to fit viewport
            viewport_size = self.scroll_area.viewport().size()
            svg_size = self.image_widget.sizeHint()
            if svg_size.isValid() and svg_size.width() > 0 and svg_size.height() > 0:
                scale_w = viewport_size.width() / svg_size.width()
                scale_h = viewport_size.height() / svg_size.height()
                scale = min(scale_w, scale_h) * 0.95  # 95% to leave a small margin
                self._current_scale = scale
                new_size = QSize(int(svg_size.width() * scale), int(svg_size.height() * scale))
                self.image_widget.setFixedSize(new_size)
                self._update_zoom_label()
        else:
            if self._original_pixmap is None or self._original_pixmap.isNull():
                return

            viewport_size = self.scroll_area.viewport().size()
            pixmap_size = self._original_pixmap.size()

            # Calculate scale to fit
            scale_w = viewport_size.width() / pixmap_size.width()
            scale_h = viewport_size.height() / pixmap_size.height()
            scale = min(scale_w, scale_h) * 0.95  # 95% to leave a small margin

            self._current_scale = scale
            self._apply_scale()

    def _actual_size(self):
        """Show image at 100% (actual size)."""
        self._current_scale = 1.0
        self._apply_scale()

    def _zoom_in(self):
        """Zoom in by 25%."""
        self._current_scale = min(self._current_scale * 1.25, 10.0)
        self._apply_scale()

    def _zoom_out(self):
        """Zoom out by 25%."""
        self._current_scale = max(self._current_scale / 1.25, 0.1)
        self._apply_scale()

    def _apply_scale(self):
        """Apply the current scale to the image."""
        if self._is_svg:
            svg_size = self.image_widget.sizeHint()
            if svg_size.isValid():
                new_size = QSize(
                    int(svg_size.width() * self._current_scale),
                    int(svg_size.height() * self._current_scale)
                )
                self.image_widget.setFixedSize(new_size)
        else:
            if self._original_pixmap is None or self._original_pixmap.isNull():
                return

            new_size = self._original_pixmap.size() * self._current_scale
            scaled_pixmap = self._original_pixmap.scaled(
                new_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_widget.setPixmap(scaled_pixmap)

        self._update_zoom_label()

    def _update_zoom_label(self):
        """Update the zoom percentage label."""
        self.zoom_label.setText(f"{int(self._current_scale * 100)}%")

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming when Ctrl is held."""
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._zoom_in()
            elif delta < 0:
                self._zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    # === Tab compatibility methods ===

    def predict_runtime(self, config):
        """Stub for tab compatibility."""
        pass

    def receive_figure(self, figure, event_type, session_id):
        """Stub for tab compatibility."""
        pass

    def start_plot_session(self):
        """Stub for tab compatibility."""
        return None

    def isolate_matplotlib_figures(self):
        """Stub for tab compatibility."""
        pass


class _DummyConfigPanel:
    """Minimal stub config panel for tab compatibility."""

    def __init__(self):
        self.config = {}

    def update_config_dict(self, config, reset=False):
        pass

    def populate_config_view(self):
        pass