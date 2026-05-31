"""Numeric editor for the selected curve point, shown right of the graph.

It mirrors whichever curve point is selected: the spin boxes track the point
live as it is dragged, and typing values + pressing **Apply** snaps the point to
those exact numbers. Endpoints have a pinned luminance, so that field is
disabled for them.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..models.curve import X_MAX, X_MIN, Y_MAX, Y_MIN


class PointValuePanel(QFrame):
    apply_requested = Signal(float, float)  # luminance, saturation

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self.setFixedWidth(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        heading = QLabel("Point")
        heading.setObjectName("Heading")
        layout.addWidget(heading)

        layout.addWidget(QLabel("Luminance"))
        self._lum = QDoubleSpinBox()
        self._lum.setRange(X_MIN, X_MAX)
        self._lum.setDecimals(1)
        self._lum.setSuffix(" %")
        layout.addWidget(self._lum)

        layout.addWidget(QLabel("Saturation"))
        self._sat = QDoubleSpinBox()
        self._sat.setRange(Y_MIN, Y_MAX)
        self._sat.setDecimals(1)
        self._sat.setSuffix(" %")
        layout.addWidget(self._sat)

        self._apply = QPushButton("Apply")
        self._apply.clicked.connect(self._emit_apply)
        layout.addWidget(self._apply)

        layout.addStretch(1)
        self.clear()

    def show_point(self, index: int, x: float, y: float, is_endpoint: bool) -> None:
        """Display a point's values; called on select and live during drag."""
        # Block signals so programmatic updates don't echo back as edits.
        for box, value in ((self._lum, x), (self._sat, y)):
            box.blockSignals(True)
            box.setEnabled(True)
            box.setValue(value)
            box.blockSignals(False)
        # An endpoint's luminance is fixed at 0 or 100, so don't let it be typed.
        self._lum.setEnabled(not is_endpoint)
        self._apply.setEnabled(True)

    def clear(self) -> None:
        """No point selected: disable the inputs."""
        for box in (self._lum, self._sat):
            box.setEnabled(False)
        self._apply.setEnabled(False)

    def _emit_apply(self) -> None:
        self.apply_requested.emit(self._lum.value(), self._sat.value())
