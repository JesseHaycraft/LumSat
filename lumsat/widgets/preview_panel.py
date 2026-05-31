"""Center column: a toolbar (compare + zoom) stacked above the preview view.

Bundling the toolbar and the :class:`PreviewView` here keeps the main window
simple — it talks to one widget. The toolbar holds:

* a **Hold to Compare** button — while it is held down the main window shows the
  unedited original; releasing it returns to the edited result.
* zoom controls (−, Reset Zoom, +) wired straight to the view.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .preview_view import PreviewView


class PreviewPanel(QWidget):
    # Emitted while the compare button is pressed / released.
    compare_pressed = Signal()
    compare_released = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.view = PreviewView()
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self.view, 1)

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()

        # Hold-to-compare: pressed shows the original, released restores the edit.
        compare = QPushButton("Hold to view original")
        compare.setToolTip("Hold down to view the original, unedited image")
        compare.pressed.connect(self.compare_pressed)
        compare.released.connect(self.compare_released)
        bar.addWidget(compare)

        bar.addStretch(1)

        zoom_out = QPushButton("−")
        zoom_out.setToolTip("Zoom out")
        zoom_out.setFixedWidth(34)
        zoom_out.clicked.connect(self.view.zoom_out)

        reset = QPushButton("Reset Zoom")
        reset.clicked.connect(self.view.reset_zoom)

        zoom_in = QPushButton("＋")
        zoom_in.setToolTip("Zoom in")
        zoom_in.setFixedWidth(34)
        zoom_in.clicked.connect(self.view.zoom_in)

        bar.addWidget(zoom_out)
        bar.addWidget(reset)
        bar.addWidget(zoom_in)
        return bar

    # Convenience pass-throughs so the main window can treat this like the view.
    def set_pixmap(self, pixmap: QPixmap, *, fit: bool = False) -> None:
        self.view.set_pixmap(pixmap, fit=fit)

    def reset_zoom(self) -> None:
        self.view.reset_zoom()

    def clear(self) -> None:
        self.view.clear()
