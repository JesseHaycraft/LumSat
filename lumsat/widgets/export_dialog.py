"""Export dialog: choose format, format-specific options, destination, scope.

The dialog only *collects* choices; the main window runs the actual full-
resolution render and file writing on a background thread. Call
:meth:`ExportDialog.options` after the dialog is accepted to read the result.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt


@dataclass
class ExportOptions:
    fmt: str  # "jpg" | "png" | "tiff"
    out_dir: str
    suffix: str
    all_images: bool
    jpg_quality: int
    jpg_subsampling: str  # "4:2:0" (web standard) | "4:4:4" (full chroma)
    png_compress_level: int
    tiff_bits: int
    tiff_compression: str

    def extension(self) -> str:
        return {"jpg": ".jpg", "png": ".png", "tiff": ".tif"}[self.fmt]


class ExportDialog(QDialog):
    def __init__(self, parent=None, *, default_dir: str = "", has_multiple: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(420)

        outer = QVBoxLayout(self)
        form = QFormLayout()
        outer.addLayout(form)

        # Format selector drives which option page is visible.
        self._format = QComboBox()
        self._format.addItems(["JPEG (.jpg)", "PNG (.png)", "TIFF (.tif)"])
        self._format.currentIndexChanged.connect(self._on_format_changed)
        form.addRow("Format", self._format)

        # One options page per format, swapped via a stack.
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_jpg_page())
        self._stack.addWidget(self._build_png_page())
        self._stack.addWidget(self._build_tiff_page())
        form.addRow(self._stack)

        # Destination folder + browse.
        self._dir_edit = QLineEdit(default_dir)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self._dir_edit, 1)
        dir_row.addWidget(browse)
        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)
        form.addRow("Destination", dir_widget)

        # Filename suffix so exports don't clobber originals.
        self._suffix = QLineEdit("_lumsat")
        form.addRow("Name suffix", self._suffix)

        # Scope: current image only, or every loaded image.
        self._scope_current = QRadioButton("Current image")
        self._scope_all = QRadioButton("All loaded images")
        self._scope_current.setChecked(True)
        self._scope_all.setEnabled(has_multiple)
        scope_row = QHBoxLayout()
        scope_row.addWidget(self._scope_current)
        scope_row.addWidget(self._scope_all)
        scope_widget = QWidget()
        scope_widget.setLayout(scope_row)
        form.addRow("Scope", scope_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------ #
    # Per-format option pages
    # ------------------------------------------------------------------ #

    def _build_jpg_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._jpg_quality = QSlider(Qt.Orientation.Horizontal)
        self._jpg_quality.setRange(1, 100)
        self._jpg_quality.setValue(85)
        self._jpg_quality_label = QLabel("85")
        self._jpg_quality.valueChanged.connect(
            lambda v: self._jpg_quality_label.setText(str(v))
        )
        row = QHBoxLayout()
        row.addWidget(self._jpg_quality, 1)
        row.addWidget(self._jpg_quality_label)
        wrap = QWidget()
        wrap.setLayout(row)
        form.addRow("Quality", wrap)

        # Chroma subsampling: 4:2:0 is the web standard (smaller files); 4:4:4
        # keeps full color detail for saturated edges at the cost of size.
        self._jpg_subsampling = QComboBox()
        self._jpg_subsampling.addItems(
            ["4:2:0 (web standard)", "4:4:4 (full color detail)"]
        )
        form.addRow("Chroma", self._jpg_subsampling)
        return page

    def _build_png_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._png_level = QSpinBox()
        self._png_level.setRange(0, 9)
        self._png_level.setValue(6)
        form.addRow("Compression (0–9)", self._png_level)
        return page

    def _build_tiff_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._tiff_bits = QComboBox()
        self._tiff_bits.addItems(["16-bit", "8-bit"])
        form.addRow("Bit depth", self._tiff_bits)
        self._tiff_comp = QComboBox()
        self._tiff_comp.addItems(["None", "LZW", "ZIP"])
        form.addRow("Compression", self._tiff_comp)
        return page

    # ------------------------------------------------------------------ #
    # Handlers
    # ------------------------------------------------------------------ #

    def _on_format_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose export folder", self._dir_edit.text() or os.path.expanduser("~")
        )
        if folder:
            self._dir_edit.setText(folder)

    # ------------------------------------------------------------------ #
    # Result
    # ------------------------------------------------------------------ #

    def options(self) -> ExportOptions:
        fmt = ["jpg", "png", "tiff"][self._format.currentIndex()]
        return ExportOptions(
            fmt=fmt,
            out_dir=self._dir_edit.text().strip(),
            suffix=self._suffix.text(),
            all_images=self._scope_all.isChecked(),
            jpg_quality=self._jpg_quality.value(),
            jpg_subsampling=["4:2:0", "4:4:4"][self._jpg_subsampling.currentIndex()],
            png_compress_level=self._png_level.value(),
            tiff_bits=16 if self._tiff_bits.currentIndex() == 0 else 8,
            tiff_compression=["none", "lzw", "zip"][self._tiff_comp.currentIndex()],
        )
