"""Application bootstrap: build the QApplication, apply the theme, show the window."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import STYLESHEET


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LumSat")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()
