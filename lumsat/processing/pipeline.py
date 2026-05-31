"""The edit pipeline: apply a saturation-vs-luminance curve to an image.

This is the heart of LumSat. For every pixel we:

1. Convert sRGB to OKLab (perceptual lightness ``L`` plus color axes ``a``/``b``).
2. Read the pixel's luminance from ``L`` (0..1) and look up a saturation
   multiplier for that luminance from the curve's LUT.
3. Scale the color axes (``a``/``b``) by that multiplier. This boosts or cuts
   color richness while keeping lightness and hue exactly where they were.
4. Convert back to sRGB, clipped into the displayable gamut.

A flat 100% curve produces a multiplier of 1.0 everywhere, i.e. no change.

Optionally, *skin-tone protection* damps the saturation change for pixels whose
hue falls in the skin-tone wedge, so a global saturation move doesn't drag faces
off-colour. It is applied last (outermost), blending the curve's factor back
toward 1.0 for skin pixels — so skin stays natural regardless of the curve.
"""

from __future__ import annotations

import numpy as np

from ..models.curve import Curve
from . import color

# Skin-tone wedge in OKLab hue (radians), calibrated from real skin samples:
# they cluster around ~50 degrees with flushed/cool variants spreading out.
_SKIN_CENTER = np.float32(np.radians(50.0))
_SKIN_HALF_WIDTH = np.float32(np.radians(22.0))
# Below this chroma a pixel is near-grey and its hue angle is meaningless, so
# skin protection ramps off to avoid touching neutrals.
_CHROMA_LO = 0.01
_CHROMA_HI = 0.03


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    """Classic smoothstep: 0 below edge0, 1 above edge1, smooth in between."""
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _skin_weight(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-pixel weight in [0, 1]: 1 deep in the skin wedge, 0 outside.

    Combines a raised-cosine window on hue angle with a chroma guard so that
    near-grey pixels (whose hue is unstable) are left alone.
    """
    hue = np.arctan2(b, a)
    # Wrap the hue difference into [-pi, pi] so the wedge works across the seam.
    dh = (hue - _SKIN_CENTER + np.pi) % (2.0 * np.pi) - np.pi
    d = np.abs(dh)
    # Raised cosine: 1 at the wedge centre, smoothly to 0 at the half-width.
    w_hue = np.where(
        d < _SKIN_HALF_WIDTH,
        0.5 * (1.0 + np.cos(np.pi * d / _SKIN_HALF_WIDTH)),
        0.0,
    )
    chroma = np.hypot(a, b)
    w_chroma = _smoothstep(_CHROMA_LO, _CHROMA_HI, chroma)
    return w_hue * w_chroma


def apply_curve(
    srgb: np.ndarray,
    curve: Curve,
    skin_protect: float = 0.0,
    lut_size: int = 1024,
) -> np.ndarray:
    """Apply ``curve`` to a float sRGB image ``(H, W, 3)`` in [0, 1].

    ``skin_protect`` (0..1) blends the saturation change back toward "no change"
    for skin-toned pixels; 0 disables it. Returns a new float sRGB image in
    [0, 1]; the input is left untouched, so editing stays non-destructive.
    """
    srgb_in = np.asarray(srgb)

    # Fast path: an identity curve changes nothing (skin protection only ever
    # damps a change toward 1.0, so with a flat curve it is a no-op too). Return
    # in the input's dtype so a no-op edit is bit-exact with the source.
    if curve.is_identity():
        return srgb_in.copy()

    # The perceptual pipeline runs in float32: it more than resolves 8/16-bit
    # output, halves memory traffic, and roughly doubles throughput vs float64.
    srgb = srgb_in.astype(np.float32, copy=False)

    lab = color.srgb_to_oklab(srgb)
    L = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]

    # Map each pixel's perceptual lightness (L, ~0..1) to a LUT index, then read
    # its saturation multiplier. Clipping guards against tiny out-of-range L.
    lut = curve.to_lut(lut_size).astype(np.float32)
    idx = np.clip((L * (lut_size - 1)).round().astype(np.intp), 0, lut_size - 1)
    factor = lut[idx]

    # Skin protection (outermost): pull the factor toward 1.0 for skin pixels so
    # the curve's effect is damped on faces. p=0 leaves the factor untouched.
    if skin_protect > 0.0:
        p = float(np.clip(skin_protect, 0.0, 1.0)) * _skin_weight(a, b)
        factor = 1.0 + (factor - 1.0) * (1.0 - p)

    # Scaling a/b preserves L (brightness) and the a/b direction (hue).
    lab_out = np.empty_like(lab)
    lab_out[..., 0] = L
    lab_out[..., 1] = a * factor
    lab_out[..., 2] = b * factor

    return color.oklab_to_srgb(lab_out)
