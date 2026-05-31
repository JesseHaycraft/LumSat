"""A background thread that renders previews without freezing the UI.

Dragging a curve point fires many update requests per second. Running the
pipeline on the GUI thread would stutter, so we hand each request to this
worker. It always works on the *latest* request and discards stale ones, so the
preview keeps up with the cursor instead of falling behind.
"""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal

from ..models.curve import Curve
from . import imageio, pipeline


class RenderWorker(QThread):
    """Renders ``(pixels, curve)`` requests and emits uint8 RGB results.

    The ``rendered`` signal carries the request id (so callers can ignore
    results for an image they have since navigated away from) and a contiguous
    uint8 ``(H, W, 3)`` array ready to wrap in a QImage.
    """

    rendered = Signal(int, object)

    def __init__(self) -> None:
        super().__init__()
        self._mutex = QMutex()
        self._wake = QWaitCondition()
        self._pending: tuple[int, np.ndarray, Curve, float] | None = None
        self._stopping = False

    def submit(
        self, request_id: int, pixels: np.ndarray, curve: Curve, skin_protect: float
    ) -> None:
        """Queue a render. Replaces any request that hasn't started yet."""
        self._mutex.lock()
        # Copy the curve so later edits on the GUI thread can't race the render.
        self._pending = (request_id, pixels, curve.copy(), skin_protect)
        self._wake.wakeOne()
        self._mutex.unlock()

    def stop(self) -> None:
        """Ask the thread to finish and wait for it to exit."""
        self._mutex.lock()
        self._stopping = True
        self._wake.wakeOne()
        self._mutex.unlock()
        self.wait()

    def run(self) -> None:  # executes on the worker thread
        while True:
            self._mutex.lock()
            while self._pending is None and not self._stopping:
                self._wake.wait(self._mutex)
            if self._stopping:
                self._mutex.unlock()
                return
            request_id, pixels, curve, skin_protect = self._pending
            self._pending = None
            self._mutex.unlock()

            result = pipeline.apply_curve(pixels, curve, skin_protect=skin_protect)
            rgb8 = (np.clip(result, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
            # Ensure C-contiguous memory so QImage can wrap it safely.
            self.rendered.emit(request_id, np.ascontiguousarray(rgb8))


class ExportWorker(QThread):
    """Renders full-resolution images and writes them to disk in the background.

    Each job is a ``(pixels, curve, skin_protect, out_path)`` tuple plus a shared
    options dict forwarded to :func:`imageio.save_image`. Progress and completion
    are reported via signals so the UI can show progress and stay responsive.
    """

    progress = Signal(int, int, str)  # done_count, total, current filename
    finished_all = Signal(int, list)  # success_count, list of error strings

    def __init__(self, jobs: list[tuple], save_kwargs: dict) -> None:
        super().__init__()
        self._jobs = jobs
        self._save_kwargs = save_kwargs

    def run(self) -> None:
        total = len(self._jobs)
        errors: list[str] = []
        success = 0
        for i, (pixels, curve, skin_protect, out_path) in enumerate(self._jobs, start=1):
            name = os.path.basename(out_path)
            self.progress.emit(i, total, name)
            try:
                rendered = pipeline.apply_curve(pixels, curve, skin_protect=skin_protect)
                imageio.save_image(rendered, out_path, **self._save_kwargs)
                success += 1
            except Exception as exc:  # report, don't abort the whole batch
                errors.append(f"{name}: {exc}")
        self.finished_all.emit(success, errors)
