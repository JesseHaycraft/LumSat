"""Center preview: shows the selected photo with pan and zoom.

Built on ``QGraphicsView`` so panning and zooming come almost for free. The
mouse wheel zooms toward the cursor, dragging pans, and :meth:`reset_zoom` fits
the whole image back into the viewport.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from ..qt_util import ndarray_to_qpixmap


class PreviewView(QGraphicsView):
    _MIN_SCALE = 0.05
    _MAX_SCALE = 40.0

    def __init__(self) -> None:
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(self._item)

        # Smooth rendering, drag-to-pan, and zoom anchored under the cursor.
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._has_image = False

    def set_image_array(self, rgb8: np.ndarray, *, fit: bool = False) -> None:
        """Display a uint8 RGB array. ``fit`` re-fits the view (use on load)."""
        self.set_pixmap(ndarray_to_qpixmap(rgb8), fit=fit)

    def set_pixmap(self, pixmap: QPixmap, *, fit: bool = False) -> None:
        new_size = pixmap.size()
        size_changed = (
            not self._has_image or self._item.pixmap().size() != new_size
        )
        self._item.setPixmap(pixmap)
        self._scene.setSceneRect(self._item.boundingRect())
        # Only re-fit on first load or when switching to a differently sized
        # image; live curve edits keep the user's current zoom/pan.
        if fit or (size_changed and not self._has_image):
            self.reset_zoom()
        self._has_image = True

    def clear(self) -> None:
        self._item.setPixmap(QPixmap())
        self._has_image = False

    def reset_zoom(self) -> None:
        """Fit the whole image inside the viewport."""
        if self._item.pixmap().isNull():
            return
        self.resetTransform()
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_in(self) -> None:
        """Zoom in one step, centered on the viewport (for toolbar buttons)."""
        self._zoom_by(1.25, QGraphicsView.ViewportAnchor.AnchorViewCenter)

    def zoom_out(self) -> None:
        """Zoom out one step, centered on the viewport (for toolbar buttons)."""
        self._zoom_by(1 / 1.25, QGraphicsView.ViewportAnchor.AnchorViewCenter)

    def _zoom_by(self, factor: float, anchor=None) -> None:
        """Scale by ``factor`` if the result stays within the zoom limits.

        ``anchor`` temporarily overrides the transformation anchor (the wheel
        zooms under the cursor; buttons zoom about the viewport center).
        """
        if self._item.pixmap().isNull():
            return
        new_scale = self.transform().m11() * factor
        if not (self._MIN_SCALE <= new_scale <= self._MAX_SCALE):
            return
        if anchor is not None:
            previous = self.transformationAnchor()
            self.setTransformationAnchor(anchor)
            self.scale(factor, factor)
            self.setTransformationAnchor(previous)
        else:
            self.scale(factor, factor)

    def wheelEvent(self, event) -> None:
        factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
        self._zoom_by(factor)  # anchored under the cursor (the view default)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Keep the image fitted while the window is resized and not yet zoomed.
        if self._has_image and abs(self.transform().m11() - 1.0) < 1e-6:
            self.reset_zoom()
