"""Small Qt helpers shared across widgets."""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap


def ndarray_to_qimage(rgb8: np.ndarray) -> QImage:
    """Wrap a contiguous uint8 ``(H, W, 3)`` RGB array as a QImage.

    The array is copied so the QImage owns its pixels and stays valid after the
    numpy array is garbage-collected.
    """
    rgb8 = np.ascontiguousarray(rgb8, dtype=np.uint8)
    h, w, _ = rgb8.shape
    image = QImage(rgb8.data, w, h, 3 * w, QImage.Format.Format_RGB888)
    return image.copy()


def ndarray_to_qpixmap(rgb8: np.ndarray) -> QPixmap:
    return QPixmap.fromImage(ndarray_to_qimage(rgb8))


def float_rgb_to_qpixmap(rgb: np.ndarray) -> QPixmap:
    """Convert a float sRGB array (0..1) to a QPixmap (e.g. the original proxy)."""
    rgb8 = (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return ndarray_to_qpixmap(rgb8)
