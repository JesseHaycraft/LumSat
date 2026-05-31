"""Loading and saving photos.

The app works internally in a single, simple representation: a float32 sRGB
array shaped ``(H, W, 3)`` with values in [0, 1]. Loading normalizes whatever
the file gave us into that form (and remembers the original bit depth so export
can offer a sensible default); saving converts back out to the requested format.

* JPG / PNG go through Pillow.
* TIFF goes through ``tifffile`` so we can read and write true 16-bit data.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import tifffile
from PIL import Image, ImageCms

# File extensions we accept on import, grouped for building dialog filters.
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def _srgb_profile_bytes() -> bytes:
    """Standard sRGB ICC profile, generated once and reused.

    Tagging exported files as sRGB is the key web-sharing convention: it tells
    color-managed browsers and wide-gamut displays how to render the pixels
    instead of guessing. Cached because building the profile isn't free.
    """
    global _SRGB_ICC
    if _SRGB_ICC is None:
        _SRGB_ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    return _SRGB_ICC


_SRGB_ICC: bytes | None = None


@dataclass
class LoadedImage:
    """A decoded photo plus the metadata export wants to know about."""

    pixels: np.ndarray  # float32 sRGB, (H, W, 3), 0..1
    source_path: str
    bit_depth: int  # original bits per channel (8 or 16)


def load_image(path: str) -> LoadedImage:
    """Decode an image file into a normalized float sRGB array."""
    ext = os.path.splitext(path)[1].lower()

    if ext in (".tif", ".tiff"):
        raw = tifffile.imread(path)
        pixels, bit_depth = _normalize_array(raw)
    else:
        with Image.open(path) as im:
            im = im.convert("RGB")  # drop alpha / palette / grayscale quirks
            raw = np.asarray(im)
        pixels, bit_depth = _normalize_array(raw)

    return LoadedImage(pixels=pixels, source_path=path, bit_depth=bit_depth)


def _normalize_array(raw: np.ndarray) -> tuple[np.ndarray, int]:
    """Turn a decoded array into float32 RGB in [0, 1]; report its bit depth."""
    # Collapse grayscale or alpha into a plain 3-channel RGB image.
    if raw.ndim == 2:
        raw = np.stack([raw] * 3, axis=-1)
    if raw.shape[-1] == 4:
        raw = raw[..., :3]
    if raw.shape[-1] == 1:
        raw = np.repeat(raw, 3, axis=-1)

    if raw.dtype == np.uint16:
        bit_depth = 16
        pixels = raw.astype(np.float32) / 65535.0
    elif np.issubdtype(raw.dtype, np.floating):
        # Some TIFFs are already float; assume they are normalized 0..1.
        bit_depth = 16
        pixels = np.clip(raw.astype(np.float32), 0.0, 1.0)
    else:  # uint8 and anything else
        bit_depth = 8
        pixels = raw.astype(np.float32) / 255.0

    return pixels, bit_depth


def save_image(
    pixels: np.ndarray,
    path: str,
    *,
    fmt: str,
    jpg_quality: int = 85,
    jpg_subsampling: str = "4:2:0",
    png_compress_level: int = 6,
    tiff_bits: int = 16,
    tiff_compression: str = "none",
) -> None:
    """Write a float sRGB array (0..1) to ``path`` in the requested format.

    ``fmt`` is one of ``"jpg"``, ``"png"``, ``"tiff"``. The remaining keyword
    options mirror the choices offered in the export dialog.

    Web-facing formats (JPEG, PNG) are tagged with an sRGB ICC profile and, for
    JPEG, written progressively with optimized Huffman tables — the same
    defaults photo apps use for "export for web". TIFF stays an archival format.
    """
    pixels = np.clip(np.asarray(pixels, dtype=np.float32), 0.0, 1.0)
    fmt = fmt.lower()

    if fmt in ("jpg", "jpeg"):
        arr8 = _to_uint8(pixels)
        # "4:2:0" -> Pillow's integer code 2; "4:4:4" (full chroma) -> 0.
        subsampling = 0 if jpg_subsampling == "4:4:4" else 2
        Image.fromarray(arr8, mode="RGB").save(
            path,
            format="JPEG",
            quality=int(jpg_quality),
            subsampling=subsampling,
            progressive=True,
            optimize=True,
            icc_profile=_srgb_profile_bytes(),
        )
    elif fmt == "png":
        arr8 = _to_uint8(pixels)
        Image.fromarray(arr8, mode="RGB").save(
            path,
            format="PNG",
            compress_level=int(png_compress_level),
            optimize=True,
            icc_profile=_srgb_profile_bytes(),
        )
    elif fmt in ("tif", "tiff"):
        if int(tiff_bits) == 16:
            arr = (pixels * 65535.0 + 0.5).astype(np.uint16)
        else:
            arr = _to_uint8(pixels)
        # Map our friendly option names onto the codec names tifffile expects.
        comp_map = {"none": None, "lzw": "lzw", "zip": "deflate"}
        comp = comp_map.get(tiff_compression.lower(), None)
        tifffile.imwrite(path, arr, compression=comp, photometric="rgb")
    else:
        raise ValueError(f"Unsupported export format: {fmt!r}")


def _to_uint8(pixels: np.ndarray) -> np.ndarray:
    """Round float (0..1) to 8-bit, matching how displays quantize."""
    return (pixels * 255.0 + 0.5).astype(np.uint8)


def make_thumbnail(pixels: np.ndarray, max_edge: int = 120) -> np.ndarray:
    """Cheap nearest-neighbor downscale for filmstrip thumbnails (uint8 RGB)."""
    h, w = pixels.shape[:2]
    scale = max_edge / max(h, w)
    if scale >= 1.0:
        return _to_uint8(pixels)
    new_h = max(1, int(round(h * scale)))
    new_w = max(1, int(round(w * scale)))
    ys = (np.linspace(0, h - 1, new_h)).astype(np.intp)
    xs = (np.linspace(0, w - 1, new_w)).astype(np.intp)
    small = pixels[np.ix_(ys, xs)]
    return _to_uint8(small)


def make_proxy(pixels: np.ndarray, max_edge: int = 1600) -> np.ndarray:
    """Downscale a large image for fast, interactive preview rendering.

    Returns the original array untouched when it is already small enough.
    """
    h, w = pixels.shape[:2]
    if max(h, w) <= max_edge:
        return pixels
    scale = max_edge / max(h, w)
    new_h = max(1, int(round(h * scale)))
    new_w = max(1, int(round(w * scale)))
    ys = (np.linspace(0, h - 1, new_h)).astype(np.intp)
    xs = (np.linspace(0, w - 1, new_w)).astype(np.intp)
    return pixels[np.ix_(ys, xs)]
