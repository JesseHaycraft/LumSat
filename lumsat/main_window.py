"""The main application window: assembles the five zones and wires up behavior.

Layout (matching the product spec):

    +-----------------------------------------------------------+
    | [Import]                                                  |  top bar
    +-----------+-----------------------------+-----------------+
    | filmstrip |        preview (center)     |  options panel  |
    |  (left)   |                             |    (right)      |
    +-----------+-----------------------------+-----------------+
    |  saturation-vs-luminance curve editor          [Export]  |  bottom
    +-----------------------------------------------------------+

The window owns the list of imported :class:`ImageItem` objects and routes user
actions (import, curve edits, presets, export) to the engine and back to the UI.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .models.curve import Curve
from .models.image_item import ImageItem
from .models.preset import Preset, load_presets, save_preset
from .processing import imageio
from .processing.worker import ExportWorker, RenderWorker
from .qt_util import float_rgb_to_qpixmap, ndarray_to_qpixmap
from .widgets.curve_editor import CurveEditor
from .widgets.export_dialog import ExportDialog
from .widgets.filmstrip import Filmstrip
from .widgets.options_panel import OptionsPanel
from .widgets.point_value_panel import PointValuePanel
from .widgets.preview_panel import PreviewPanel

_IMPORT_FILTER = "Images (*.jpg *.jpeg *.png *.tif *.tiff)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LumSat — Luminance × Saturation Editor")
        self.resize(1280, 860)

        self._images: list[ImageItem] = []
        self._current_index = -1
        self._req_id = 0  # monotonic id so stale renders can be ignored
        self._fit_pending = False
        self._export_worker: ExportWorker | None = None
        self._export_progress: QProgressDialog | None = None

        # Hold-to-compare state: cache both renderings and which one is showing.
        self._edited_pixmap = None
        self._original_pixmap = None
        self._comparing = False

        self._build_ui()
        self._connect_signals()

        # Background renderer for live preview updates.
        self._render_worker = RenderWorker()
        self._render_worker.rendered.connect(self._on_rendered)
        self._render_worker.start()

        # Coalesce rapid curve edits into one render shortly after the last one.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(30)
        self._debounce.timeout.connect(self._render_current)

        self._refresh_presets()
        self._update_actions_enabled()
        self.statusBar().showMessage("Import photos to begin.")

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Top bar: Import top-left, Export top-right.
        top_bar = QHBoxLayout()
        self._import_btn = QPushButton("Import…")
        self._import_btn.setObjectName("Primary")
        self._unload_btn = QPushButton("Unload Images")
        self._export_btn = QPushButton("Export…")
        self._export_btn.setObjectName("Primary")
        top_bar.addWidget(self._import_btn)
        top_bar.addWidget(self._unload_btn)
        top_bar.addStretch(1)
        top_bar.addWidget(self._export_btn)
        root.addLayout(top_bar)

        # Widgets.
        self._filmstrip = Filmstrip()
        self._filmstrip.setMinimumWidth(110)
        self._preview_panel = PreviewPanel()
        self._preview = self._preview_panel.view  # the underlying PreviewView
        self._curve_editor = CurveEditor()
        self._point_panel = PointValuePanel()
        self._options = OptionsPanel()

        # Center column: preview on top, the curve row beneath it. The vertical
        # splitter lets the user drag the border between preview and graph.
        curve_row = QWidget()
        curve_layout = QHBoxLayout(curve_row)
        curve_layout.setContentsMargins(0, 0, 0, 0)
        curve_layout.setSpacing(8)
        curve_layout.addWidget(self._curve_editor, 1)
        curve_layout.addWidget(self._point_panel)

        center = QSplitter(Qt.Orientation.Vertical)
        center.addWidget(self._preview_panel)
        center.addWidget(curve_row)
        center.setStretchFactor(0, 1)  # preview takes the vertical slack
        center.setCollapsible(0, False)
        center.setCollapsible(1, False)
        center.setSizes([620, 220])

        # Outer split: filmstrip | center column | options, all full height.
        outer = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self._filmstrip)
        outer.addWidget(center)
        outer.addWidget(self._options)
        outer.setStretchFactor(1, 1)  # center column takes the slack
        outer.setCollapsible(0, False)
        outer.setCollapsible(2, False)
        outer.setSizes([150, 900, 220])
        root.addWidget(outer, 1)

    def _connect_signals(self) -> None:
        self._import_btn.clicked.connect(self._import_images)
        self._unload_btn.clicked.connect(self._unload_images)
        self._export_btn.clicked.connect(self._open_export_dialog)
        self._filmstrip.selection_changed.connect(self._on_selection_changed)
        self._curve_editor.curve_changed.connect(self._on_curve_changed)

        self._options.reset_curve_requested.connect(self._reset_curve)
        self._options.save_preset_requested.connect(self._save_preset)
        self._options.apply_preset_requested.connect(self._apply_preset_current)
        self._options.apply_preset_all_requested.connect(self._apply_preset_all)
        self._options.skin_protect_changed.connect(self._on_skin_protect_changed)

        # Hold-to-compare against the unedited original.
        self._preview_panel.compare_pressed.connect(self._on_compare_pressed)
        self._preview_panel.compare_released.connect(self._on_compare_released)

        # Numeric point editor mirrors the curve's selected point.
        self._curve_editor.point_selected.connect(self._point_panel.show_point)
        self._curve_editor.point_deselected.connect(self._point_panel.clear)
        self._point_panel.apply_requested.connect(self._curve_editor.set_selected_point)

    # ------------------------------------------------------------------ #
    # Import / selection
    # ------------------------------------------------------------------ #

    def _import_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import photos", os.path.expanduser("~"), _IMPORT_FILTER
        )
        if not paths:
            return

        first_new = len(self._images)
        errors: list[str] = []
        for path in paths:
            try:
                item = ImageItem.from_file(path)
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")
                continue
            self._images.append(item)
            self._filmstrip.add_image(item)

        if errors:
            QMessageBox.warning(
                self, "Some images could not be loaded", "\n".join(errors)
            )

        self._update_actions_enabled()
        # Select the first newly imported image if nothing was selected before.
        if self._current_index < 0 and len(self._images) > first_new:
            self._filmstrip.select(first_new)

    def _unload_images(self) -> None:
        if not self._images:
            return
        self._images.clear()
        self._filmstrip.clear()  # emits currentRowChanged(-1) → _on_selection_changed
        self._current_index = -1
        self._original_pixmap = None
        self._edited_pixmap = None
        self._comparing = False
        self._preview.clear()
        self._curve_editor.set_curve(Curve())
        self._point_panel.clear()
        self._options.set_skin_protect(0.0)
        self._update_actions_enabled()
        self.statusBar().showMessage("Unloaded all images.", 3000)

    def _on_selection_changed(self, index: int) -> None:
        self._current_index = index
        if not self._current_item():
            self._preview.clear()
            self._original_pixmap = None
            self._edited_pixmap = None
            return
        item = self._current_item()
        # Cache the unedited proxy so Hold-to-Compare can flip to it instantly.
        self._original_pixmap = float_rgb_to_qpixmap(item.proxy)
        self._edited_pixmap = None
        self._comparing = False
        # Show this image's own curve + settings, then render and fit it.
        self._curve_editor.set_curve(item.curve)
        self._options.set_skin_protect(item.skin_protect)
        self._fit_pending = True
        self._render_current()

    def _current_item(self) -> ImageItem | None:
        if 0 <= self._current_index < len(self._images):
            return self._images[self._current_index]
        return None

    # ------------------------------------------------------------------ #
    # Live preview rendering
    # ------------------------------------------------------------------ #

    def _on_curve_changed(self) -> None:
        # Restart the debounce timer; the actual render fires once edits settle.
        self._debounce.start()

    def _render_current(self) -> None:
        item = self._current_item()
        if item is None:
            return
        self._req_id += 1
        self._render_worker.submit(
            self._req_id, item.proxy, item.curve, item.skin_protect
        )

    def _on_rendered(self, request_id: int, rgb8) -> None:
        # Ignore results superseded by a newer request (stale image or curve).
        if request_id != self._req_id:
            return
        self._edited_pixmap = ndarray_to_qpixmap(rgb8)
        # While comparing we're showing the original; don't clobber it.
        if not self._comparing:
            self._preview.set_pixmap(self._edited_pixmap, fit=self._fit_pending)
        self._fit_pending = False

    def _on_compare_pressed(self) -> None:
        if self._original_pixmap is None:
            return
        self._comparing = True
        # Keep current zoom/pan so the comparison is pixel-aligned.
        self._preview.set_pixmap(self._original_pixmap, fit=False)

    def _on_compare_released(self) -> None:
        self._comparing = False
        if self._edited_pixmap is not None:
            self._preview.set_pixmap(self._edited_pixmap, fit=False)

    # ------------------------------------------------------------------ #
    # Curve / preset actions
    # ------------------------------------------------------------------ #

    def _on_skin_protect_changed(self, value: float) -> None:
        item = self._current_item()
        if item is None:
            return
        item.skin_protect = value
        # Reuse the curve debounce so dragging the strength slider stays smooth.
        self._debounce.start()

    def _reset_curve(self) -> None:
        item = self._current_item()
        if item is None:
            return
        item.curve.reset()
        self._curve_editor.set_curve(item.curve)
        self._render_current()

    def _save_preset(self) -> None:
        item = self._current_item()
        if item is None:
            return
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        save_preset(
            Preset(name=name, curve=item.curve.copy(), skin_protect=item.skin_protect)
        )
        self._refresh_presets()
        self._options.select_preset(name)  # make the new preset the active choice
        self.statusBar().showMessage(f"Saved preset “{name}”.", 4000)

    def _apply_preset_current(self, preset: Preset) -> None:
        item = self._current_item()
        if item is None:
            return
        item.curve = preset.curve.copy()
        item.skin_protect = preset.skin_protect
        self._curve_editor.set_curve(item.curve)
        self._options.set_skin_protect(item.skin_protect)
        self._render_current()
        self.statusBar().showMessage(f"Applied “{preset.name}” to this image.", 4000)

    def _apply_preset_all(self, preset: Preset) -> None:
        if not self._images:
            return
        for item in self._images:
            item.curve = preset.curve.copy()
            item.skin_protect = preset.skin_protect
        current = self._current_item()
        if current is not None:
            self._curve_editor.set_curve(current.curve)
            self._options.set_skin_protect(current.skin_protect)
            self._render_current()
        self.statusBar().showMessage(
            f"Applied “{preset.name}” to all {len(self._images)} images.", 4000
        )

    def _refresh_presets(self) -> None:
        self._options.set_presets(load_presets())

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #

    def _open_export_dialog(self) -> None:
        item = self._current_item()
        if item is None:
            return
        default_dir = os.path.dirname(item.source_path)
        dialog = ExportDialog(
            self, default_dir=default_dir, has_multiple=len(self._images) > 1
        )
        if dialog.exec() != ExportDialog.DialogCode.Accepted:
            return

        opts = dialog.options()
        if not opts.out_dir or not os.path.isdir(opts.out_dir):
            QMessageBox.warning(self, "Export", "Please choose a valid destination folder.")
            return

        targets = self._images if opts.all_images else [item]
        jobs = []
        for target in targets:
            stem = os.path.splitext(target.name)[0]
            out_path = os.path.join(opts.out_dir, f"{stem}{opts.suffix}{opts.extension()}")
            jobs.append(
                (target.pixels, target.curve.copy(), target.skin_protect, out_path)
            )

        save_kwargs = dict(
            fmt=opts.fmt,
            jpg_quality=opts.jpg_quality,
            jpg_subsampling=opts.jpg_subsampling,
            png_compress_level=opts.png_compress_level,
            tiff_bits=opts.tiff_bits,
            tiff_compression=opts.tiff_compression,
        )
        self._start_export(jobs, save_kwargs)

    def _start_export(self, jobs: list[tuple], save_kwargs: dict) -> None:
        # Disabling the Export button is enough to prevent a second concurrent
        # export; everything else (editing, import) stays usable meanwhile.
        self._export_btn.setEnabled(False)

        total = len(jobs)
        # Modeless progress window: the main window stays interactive so the user
        # can keep editing while the background worker writes files.
        progress = QProgressDialog("Exporting…", None, 0, total, self)
        progress.setWindowTitle("Exporting")
        progress.setWindowModality(Qt.WindowModality.NonModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        self._export_progress = progress
        progress.show()

        worker = ExportWorker(jobs, save_kwargs)
        worker.progress.connect(self._on_export_progress)
        worker.finished_all.connect(self._on_export_finished)
        self._export_worker = worker  # keep a reference so it isn't GC'd
        worker.start()

    def _on_export_progress(self, done: int, total: int, name: str) -> None:
        if self._export_progress is not None:
            # `done` counts the job now starting, so completed-so-far is done-1.
            self._export_progress.setValue(done - 1)
            self._export_progress.setLabelText(f"Exporting {done}/{total}: {name}")
        self.statusBar().showMessage(f"Exporting {done}/{total}: {name}")

    def _on_export_finished(self, success: int, errors: list) -> None:
        self._export_btn.setEnabled(True)
        if self._export_progress is not None:
            self._export_progress.close()
            self._export_progress = None
        if errors:
            QMessageBox.warning(
                self,
                "Export finished with errors",
                f"Exported {success} image(s).\n\nProblems:\n" + "\n".join(errors),
            )
        else:
            self.statusBar().showMessage(f"Exported {success} image(s).", 5000)
        self._export_worker = None

    # ------------------------------------------------------------------ #
    # Misc
    # ------------------------------------------------------------------ #

    def _update_actions_enabled(self) -> None:
        has_images = bool(self._images)
        self._export_btn.setEnabled(has_images)
        self._unload_btn.setEnabled(has_images)

    def closeEvent(self, event) -> None:
        # Cleanly stop the render thread before the window goes away.
        self._render_worker.stop()
        if self._export_worker is not None:
            self._export_worker.wait()
        super().closeEvent(event)
