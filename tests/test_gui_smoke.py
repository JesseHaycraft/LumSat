"""Headless GUI smoke test for the v2 interaction changes.

Run with the offscreen platform so it needs no display:

    QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_gui_smoke.py

Exercises: hold-to-compare swaps the preview to the original and back,
button zoom respects clamps, and the numeric point editor drives the curve.
"""

from __future__ import annotations

import os
import tempfile
import time

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from lumsat.main_window import MainWindow
from lumsat.models.preset import Preset
from lumsat.processing import imageio, pipeline


def _make_test_image(path: str) -> None:
    # A horizontal brightness ramp with some color so saturation edits show.
    h, w = 64, 96
    x = np.linspace(0.0, 1.0, w)
    rgb = np.zeros((h, w, 3), dtype=np.float64)
    rgb[..., 0] = x
    rgb[..., 1] = 0.5
    rgb[..., 2] = 1.0 - x
    Image.fromarray((rgb * 255 + 0.5).astype(np.uint8)).save(path)


def _pixmap_signature(pixmap) -> int:
    img = pixmap.toImage()
    return hash(bytes(img.constBits()))


def main() -> None:
    app = QApplication.instance() or QApplication([])
    win = MainWindow()

    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "ramp.png")
        _make_test_image(img_path)

        item = __import__(
            "lumsat.models.image_item", fromlist=["ImageItem"]
        ).ImageItem.from_file(img_path)
        win._images.append(item)
        win._filmstrip.add_image(item)
        win._filmstrip.select(0)
        win._update_actions_enabled()

        def wait_for_render() -> None:
            for _ in range(200):
                app.processEvents()
                if win._edited_pixmap is not None:
                    return
                time.sleep(0.01)

        # Pump the render worker so the edited pixmap lands.
        wait_for_render()
        assert win._edited_pixmap is not None, "preview never rendered"
        assert win._original_pixmap is not None, "original pixmap not cached"

        # --- Hold to compare ---
        orig_sig = _pixmap_signature(win._original_pixmap)
        # Edit the curve so original != edited, then wait for a fresh render.
        item.curve.add_point(50.0, 0.0)  # crush saturation mid-tones
        win._edited_pixmap = None
        win._render_current()
        wait_for_render()
        assert win._edited_pixmap is not None, "edited curve never re-rendered"
        edited_sig = _pixmap_signature(win._edited_pixmap)
        assert edited_sig != orig_sig, "edited render identical to original"

        win._on_compare_pressed()
        assert win._comparing is True
        shown = _pixmap_signature(win._preview._item.pixmap())
        assert shown == _pixmap_signature(win._original_pixmap), "compare did not show original"
        win._on_compare_released()
        assert win._comparing is False
        shown = _pixmap_signature(win._preview._item.pixmap())
        assert shown == _pixmap_signature(win._edited_pixmap), "release did not restore edit"

        # --- Button zoom respects clamps ---
        view = win._preview
        before = view.transform().m11()
        view.zoom_in()
        assert view.transform().m11() > before, "zoom_in did not magnify"
        view.zoom_out()
        view.zoom_out()
        assert view.transform().m11() < before * 1.01, "zoom_out did not shrink"
        # Hammer the clamps.
        for _ in range(100):
            view.zoom_in()
        assert view.transform().m11() <= view._MAX_SCALE + 1e-6, "exceeded max scale"
        for _ in range(200):
            view.zoom_out()
        assert view.transform().m11() >= view._MIN_SCALE - 1e-6, "exceeded min scale"

        # --- Numeric point editor drives the curve + live select on drag ---
        captured = {}
        win._curve_editor.point_selected.connect(
            lambda i, x, y, e: captured.update(i=i, x=x, y=y, e=e)
        )
        # Select an endpoint (index 0) by simulating the selection path.
        win._curve_editor._select(0)
        assert captured.get("i") == 0, "point_selected not emitted on select"
        assert captured.get("e") is True, "endpoint not flagged"

        # Apply a typed saturation value; endpoint X is pinned at 0.
        win._curve_editor.set_selected_point(0.0, 130.0)
        x0, y0 = item.curve.points[0]
        assert abs(x0 - 0.0) < 1e-6, "endpoint X moved off 0"
        assert abs(y0 - 130.0) < 1e-6, "saturation not applied"

        # --- New preset becomes the active dropdown selection ---
        win._options.set_presets(
            [Preset(name="Alpha", curve=item.curve.copy()),
             Preset(name="Zeta", curve=item.curve.copy())]
        )
        win._options.select_preset("Zeta")
        assert win._options._preset_combo.currentText() == "Zeta", "preset not selected"

        # --- Skin-protect control updates the item and re-renders ---
        win._options.set_skin_protect(0.0)  # sync to a known off state
        win._edited_pixmap = None
        win._options._skin_check.setChecked(True)  # fires skin_protect_changed
        assert item.skin_protect > 0.0, "skin_protect not propagated to item"
        win._debounce.stop()
        win._render_current()
        wait_for_render()
        assert win._edited_pixmap is not None, "skin-protect change did not render"
        item.skin_protect = 0.0  # reset for the export snapshot test below

        # --- Modeless export survives a concurrent edit (changes #3 + #4) ---
        out_path = os.path.join(tmp, "out_export.png")
        pre_curve = item.curve.copy()  # what the export should capture
        jobs = [(item.pixels, pre_curve.copy(), item.skin_protect, out_path)]
        save_kwargs = dict(
            fmt="png", jpg_quality=90, png_compress_level=1,
            tiff_bits=16, tiff_compression="none",
        )
        win._start_export(jobs, save_kwargs)
        assert win._export_progress is not None, "no progress window shown"
        assert (
            win._export_progress.windowModality() == Qt.WindowModality.NonModal
        ), "progress window is modal (would block editing)"

        # Mutate the live curve while the export runs — must not affect output.
        item.curve.add_point(50.0, 0.0)

        for _ in range(500):
            app.processEvents()
            if win._export_progress is None:
                break
            time.sleep(0.005)
        assert win._export_progress is None, "export never finished"
        assert os.path.exists(out_path), "export file missing"

        loaded = imageio.load_image(out_path).pixels.astype(np.float64)
        expected = pipeline.apply_curve(item.pixels, pre_curve, skin_protect=0.0)
        assert np.max(np.abs(loaded - expected)) < 0.02, (
            "exported file reflects the post-edit curve, not the snapshot"
        )

    win._export_worker = None
    win._render_worker.stop()
    print("GUI smoke test passed.")


if __name__ == "__main__":
    main()
