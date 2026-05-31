"""Per-image state: the source pixels plus this photo's own curve.

Each imported photo gets one :class:`ImageItem`. It keeps the untouched source
pixels (so editing is non-destructive), a downscaled proxy for fast preview
rendering, a thumbnail for the filmstrip, and its own :class:`Curve`. Selecting
a different photo simply swaps which item the UI is pointing at.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from ..processing import imageio
from .curve import Curve


@dataclass
class ImageItem:
    pixels: np.ndarray  # float32 sRGB, full resolution, 0..1
    source_path: str
    bit_depth: int
    curve: Curve = field(default_factory=Curve)
    skin_protect: float = 0.0  # 0..1 strength of skin-tone protection
    proxy: np.ndarray = field(default=None, repr=False)  # type: ignore[assignment]
    thumbnail: np.ndarray = field(default=None, repr=False)  # type: ignore[assignment]

    @classmethod
    def from_file(cls, path: str) -> "ImageItem":
        loaded = imageio.load_image(path)
        item = cls(
            pixels=loaded.pixels,
            source_path=loaded.source_path,
            bit_depth=loaded.bit_depth,
        )
        # Precompute the proxy + thumbnail once at load time.
        item.proxy = imageio.make_proxy(loaded.pixels)
        item.thumbnail = imageio.make_thumbnail(loaded.pixels)
        return item

    @property
    def name(self) -> str:
        return os.path.basename(self.source_path)
