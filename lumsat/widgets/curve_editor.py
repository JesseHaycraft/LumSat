"""Bottom panel: the interactive saturation-vs-luminance curve editor.

* X axis is luminance, 0..100% (left = shadows, right = highlights).
* Y axis is the saturation multiplier, 0..150% (100% = unchanged).
* The background is a black->white gradient along X, a visual reminder that the
  horizontal position corresponds to image brightness.

Interaction:
* **Click on the curve** to drop a new control point, then drag it.
* **Drag a point** up/down (and left/right for interior points) to reshape.
* **Double-click a point** to delete it (the two endpoints can't be deleted).

Every edit mutates the shared :class:`Curve` in place and emits
``curve_changed`` so the preview can re-render.

This is drawn as a plain custom widget (rather than a QGraphicsScene) because
the coordinate math and hit-testing are simple and easier to read this way.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget

from ..models.curve import Curve, X_MAX, X_MIN, Y_DEFAULT, Y_MAX, Y_MIN

# Visual constants.
_MARGIN_LEFT = 44
_MARGIN_RIGHT = 12
_MARGIN_TOP = 12
_MARGIN_BOTTOM = 26
_POINT_RADIUS = 6
_HIT_RADIUS = 12  # pixels; how close a click must be to grab a point/curve
_CURVE_COLOR = QColor("#f2c14e")  # amber: readable over black and white alike


class CurveEditor(QWidget):
    curve_changed = Signal()
    # index, luminance, saturation, is_endpoint — for the numeric point editor.
    point_selected = Signal(int, float, float, bool)
    point_deselected = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._curve = Curve()
        self._drag_index: int | None = None  # point being dragged right now
        self._selected_index: int | None = None  # point shown in the value editor
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def set_curve(self, curve: Curve) -> None:
        """Point the editor at an image's curve (editing mutates it in place)."""
        self._curve = curve
        self._drag_index = None
        self._select(None)
        self.update()

    def curve(self) -> Curve:
        return self._curve

    def set_selected_point(self, x: float, y: float) -> None:
        """Snap the currently selected point to ``(x, y)`` (from the value editor).

        Constraints are handled by :meth:`Curve.move_point` (Y clamped to its
        range, interior X kept between neighbors, endpoints pinned).
        """
        if self._selected_index is None:
            return
        self._selected_index = self._curve.move_point(self._selected_index, x, y)
        self._drag_index = None
        self.update()
        self.curve_changed.emit()
        self._emit_selected()  # report the snapped (possibly clamped) values

    def _is_endpoint(self, index: int) -> bool:
        return index == 0 or index == len(self._curve.points) - 1

    def _select(self, index: int | None) -> None:
        """Update the selected point and notify listeners."""
        self._selected_index = index
        if index is None:
            self.point_deselected.emit()
        else:
            self._emit_selected()

    def _emit_selected(self) -> None:
        index = self._selected_index
        if index is None:
            return
        x, y = self._curve.points[index]
        self.point_selected.emit(index, float(x), float(y), self._is_endpoint(index))

    # ------------------------------------------------------------------ #
    # Coordinate mapping between data units and pixels
    # ------------------------------------------------------------------ #

    def _plot_rect(self) -> QRectF:
        return QRectF(
            _MARGIN_LEFT,
            _MARGIN_TOP,
            max(1, self.width() - _MARGIN_LEFT - _MARGIN_RIGHT),
            max(1, self.height() - _MARGIN_TOP - _MARGIN_BOTTOM),
        )

    def _data_to_px(self, x: float, y: float) -> QPointF:
        r = self._plot_rect()
        px = r.left() + (x - X_MIN) / (X_MAX - X_MIN) * r.width()
        py = r.bottom() - (y - Y_MIN) / (Y_MAX - Y_MIN) * r.height()
        return QPointF(px, py)

    def _px_to_data(self, px: float, py: float) -> tuple[float, float]:
        r = self._plot_rect()
        x = X_MIN + (px - r.left()) / r.width() * (X_MAX - X_MIN)
        y = Y_MIN + (r.bottom() - py) / r.height() * (Y_MAX - Y_MIN)
        return x, y

    # ------------------------------------------------------------------ #
    # Painting
    # ------------------------------------------------------------------ #

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._plot_rect()

        self._draw_background(painter, r)
        self._draw_grid(painter, r)
        self._draw_reference_line(painter, r)
        self._draw_curve(painter, r)
        self._draw_points(painter)

    def _draw_background(self, painter: QPainter, r: QRectF) -> None:
        # Black (luminance 0) on the left to white (luminance 100) on the right.
        gradient = QLinearGradient(r.left(), 0, r.right(), 0)
        gradient.setColorAt(0.0, QColor(0, 0, 0))
        gradient.setColorAt(1.0, QColor(255, 255, 255))
        painter.fillRect(r, QBrush(gradient))
        painter.setPen(QPen(QColor("#1e1e1e"), 1))
        painter.drawRect(r)

    def _draw_grid(self, painter: QPainter, r: QRectF) -> None:
        # Faint gridlines, drawn semi-transparent so they read on any gray.
        painter.setPen(QPen(QColor(128, 128, 128, 90), 1))
        font = QFont(painter.font())
        font.setPointSize(8)
        painter.setFont(font)

        for lum in (0, 25, 50, 75, 100):
            top = self._data_to_px(lum, Y_MAX)
            bottom = self._data_to_px(lum, Y_MIN)
            painter.drawLine(top, bottom)
            painter.setPen(QPen(QColor("#9a9a9a")))
            painter.drawText(
                QRectF(top.x() - 20, r.bottom() + 4, 40, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{lum}",
            )
            painter.setPen(QPen(QColor(128, 128, 128, 90), 1))

        for sat in (0, 50, 100, 150):
            left = self._data_to_px(X_MIN, sat)
            right = self._data_to_px(X_MAX, sat)
            painter.drawLine(left, right)
            painter.setPen(QPen(QColor("#9a9a9a")))
            painter.drawText(
                QRectF(0, left.y() - 9, _MARGIN_LEFT - 6, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{sat}",
            )
            painter.setPen(QPen(QColor(128, 128, 128, 90), 1))

    def _draw_reference_line(self, painter: QPainter, r: QRectF) -> None:
        # Dashed line at 100% marks the "no change" level.
        pen = QPen(QColor(200, 200, 200, 130), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        left = self._data_to_px(X_MIN, Y_DEFAULT)
        right = self._data_to_px(X_MAX, Y_DEFAULT)
        painter.drawLine(left, right)

    def _draw_curve(self, painter: QPainter, r: QRectF) -> None:
        # Sample the curve once per horizontal pixel for a smooth line.
        sample_px = np.linspace(r.left(), r.right(), int(r.width()) + 1)
        xs = np.array([self._px_to_data(px, 0)[0] for px in sample_px])
        ys = self._curve.evaluate(xs)

        path = QPainterPath()
        for i, (x, y) in enumerate(zip(xs, ys)):
            pt = self._data_to_px(x, y)
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)

        # Dark underlay first for contrast, then the amber curve on top.
        painter.setPen(QPen(QColor(0, 0, 0, 160), 4))
        painter.drawPath(path)
        painter.setPen(QPen(_CURVE_COLOR, 2))
        painter.drawPath(path)

    def _draw_points(self, painter: QPainter) -> None:
        for i, (x, y) in enumerate(self._curve.points):
            center = self._data_to_px(x, y)
            if i == self._selected_index:
                # Selected point: white fill plus an outer ring so it stands out.
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.setBrush(QBrush(QColor("#ffffff")))
                painter.drawEllipse(center, _POINT_RADIUS, _POINT_RADIUS)
                painter.setPen(QPen(_CURVE_COLOR, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(center, _POINT_RADIUS + 3, _POINT_RADIUS + 3)
            else:
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.setBrush(QBrush(_CURVE_COLOR))
                painter.drawEllipse(center, _POINT_RADIUS, _POINT_RADIUS)

    # ------------------------------------------------------------------ #
    # Mouse interaction
    # ------------------------------------------------------------------ #

    def _point_at(self, pos: QPointF) -> int | None:
        """Return the index of the control point nearest ``pos`` within reach."""
        best_index: int | None = None
        best_dist = _HIT_RADIUS
        for i, (x, y) in enumerate(self._curve.points):
            delta = self._data_to_px(x, y) - pos
            dist = (delta.x() ** 2 + delta.y() ** 2) ** 0.5
            if dist <= best_dist:
                best_dist = dist
                best_index = i
        return best_index

    def _near_curve(self, pos: QPointF) -> bool:
        """True if ``pos`` sits close to the drawn curve line."""
        x, _ = self._px_to_data(pos.x(), pos.y())
        y_curve = float(self._curve.evaluate(np.array([x]))[0])
        on_curve_px = self._data_to_px(x, y_curve)
        return abs(on_curve_px.y() - pos.y()) <= _HIT_RADIUS

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()

        # Grab an existing point if we clicked one...
        index = self._point_at(pos)
        if index is None and self._near_curve(pos):
            # ...otherwise, clicking on the curve creates a new point.
            x, y = self._px_to_data(pos.x(), pos.y())
            index = self._curve.add_point(x, y)
            self.curve_changed.emit()

        self._drag_index = index
        if index is not None:
            self._select(index)  # show it in the value editor
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_index is None:
            return
        x, y = self._px_to_data(event.position().x(), event.position().y())
        self._drag_index = self._curve.move_point(self._drag_index, x, y)
        self._selected_index = self._drag_index
        self.update()
        self.curve_changed.emit()
        self._emit_selected()  # live-update the value editor while dragging

    def mouseReleaseEvent(self, event) -> None:
        self._drag_index = None

    def mouseDoubleClickEvent(self, event) -> None:
        # Double-click a point to remove it (endpoints are protected).
        index = self._point_at(event.position())
        if index is not None and self._curve.remove_point(index):
            self._drag_index = None
            self._select(None)
            self.update()
            self.curve_changed.emit()
