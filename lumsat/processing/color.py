"""Color-space conversions used by the edit pipeline.

Everything here is vectorized NumPy that operates on float images shaped
``(H, W, 3)`` with values in [0, 1]. We move between three representations:

    sRGB  <->  linear sRGB  <->  OKLab

* **sRGB** is what image files store (gamma-encoded, display-ready).
* **linear sRGB** is light-linear; the right space to do physical mixing in.
* **OKLab** is a modern perceptual space (Bjorn Ottosson, 2020). Its ``L`` axis
  tracks perceived lightness and the ``a``/``b`` axes carry color. We edit
  saturation here because scaling ``a``/``b`` changes color richness while
  leaving lightness (``L``) and hue (the a/b direction) untouched.

Matrix and transfer-function constants are taken directly from Ottosson's
reference implementation.
"""

from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------- #
# sRGB gamma <-> linear light
# --------------------------------------------------------------------------- #


def srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    """Decode gamma-encoded sRGB (0..1) into linear-light sRGB (0..1)."""
    srgb = np.asarray(srgb, dtype=np.float32)
    # The sRGB transfer function is linear near black, a power curve elsewhere.
    return np.where(
        srgb <= 0.04045,
        srgb / 12.92,
        ((srgb + 0.055) / 1.055) ** 2.4,
    )


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """Encode linear-light sRGB (0..1) back into gamma-encoded sRGB (0..1)."""
    linear = np.asarray(linear, dtype=np.float32)
    return np.where(
        linear <= 0.0031308,
        linear * 12.92,
        1.055 * np.clip(linear, 0.0, None) ** (1.0 / 2.4) - 0.055,
    )


# --------------------------------------------------------------------------- #
# linear sRGB <-> OKLab
# --------------------------------------------------------------------------- #

# linear sRGB -> LMS cone response (Ottosson's M1 matrix).
_RGB_TO_LMS = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ]
)

# nonlinear LMS (cube-rooted) -> OKLab (Ottosson's M2 matrix).
_LMS_TO_LAB = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ]
)

# Inverses, for the trip back to RGB. Kept in float64 so the matrix inversion
# is accurate; they are cast to the image's dtype (float32 in the hot path)
# when actually applied.
_LAB_TO_LMS = np.linalg.inv(_LMS_TO_LAB)
_LMS_TO_RGB = np.linalg.inv(_RGB_TO_LMS)


def _apply_matrix(img: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Apply a 3x3 color matrix to every pixel of an ``(H, W, 3)`` image."""
    # einsum keeps this a single vectorized pass over all pixels. Matching the
    # matrix dtype to the image keeps a float32 image from upcasting to float64.
    return np.einsum("ij,...j->...i", matrix.astype(img.dtype), img)


def linear_to_oklab(linear_rgb: np.ndarray) -> np.ndarray:
    """Convert linear-light sRGB to OKLab. Returns an ``(H, W, 3)`` L/a/b array."""
    lms = _apply_matrix(linear_rgb, _RGB_TO_LMS)
    # Cube root is the perceptual nonlinearity at the heart of OKLab.
    # np.cbrt handles any tiny negatives that round-off can produce.
    lms_nl = np.cbrt(lms)
    return _apply_matrix(lms_nl, _LMS_TO_LAB)


def oklab_to_linear(lab: np.ndarray) -> np.ndarray:
    """Convert OKLab back to linear-light sRGB (not yet gamut-clipped)."""
    lms_nl = _apply_matrix(lab, _LAB_TO_LMS)
    lms = lms_nl ** 3
    return _apply_matrix(lms, _LMS_TO_RGB)


# --------------------------------------------------------------------------- #
# Convenience round-trips used by the pipeline
# --------------------------------------------------------------------------- #


def srgb_to_oklab(srgb: np.ndarray) -> np.ndarray:
    """sRGB (0..1) straight to OKLab."""
    return linear_to_oklab(srgb_to_linear(srgb))


def oklab_to_srgb(lab: np.ndarray) -> np.ndarray:
    """OKLab back to sRGB (0..1), hard-clipped into the displayable gamut."""
    linear = oklab_to_linear(lab)
    srgb = linear_to_srgb(linear)
    # Extreme saturation pushes can land outside sRGB; clip to a valid image.
    return np.clip(srgb, 0.0, 1.0)
