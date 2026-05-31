"""Headless sanity checks for the color/curve/pipeline engine.

These run without a GUI (no PySide6 needed) so they're fast and CI-friendly:

    .venv/bin/python -m pytest tests/test_engine.py
    # or, without pytest installed:
    .venv/bin/python tests/test_engine.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lumsat.models.curve import Curve
from lumsat.processing import color, pipeline


def test_srgb_oklab_roundtrip():
    """sRGB -> OKLab -> sRGB should return the original within tight tolerance."""
    rng = np.random.default_rng(0)
    srgb = rng.random((64, 64, 3)).astype(np.float64)
    back = color.oklab_to_srgb(color.srgb_to_oklab(srgb))
    assert np.max(np.abs(back - srgb)) < 1e-4


def test_identity_curve_is_noop():
    """A flat 100% curve must leave the image essentially unchanged."""
    rng = np.random.default_rng(1)
    srgb = rng.random((32, 32, 3)).astype(np.float64)
    out = pipeline.apply_curve(srgb, Curve())  # default = identity
    assert np.array_equal(out, srgb)


def test_zero_saturation_makes_gray():
    """Pulling saturation to 0% should desaturate toward neutral gray.

    A gray pixel has equal R/G/B; we check the spread across channels collapses.
    """
    srgb = np.array([[[0.8, 0.2, 0.3]]], dtype=np.float64)
    curve = Curve(points=[(0.0, 0.0), (100.0, 0.0)])  # 0% everywhere
    out = pipeline.apply_curve(srgb, curve)
    spread = out.max(axis=-1) - out.min(axis=-1)
    assert float(spread[0, 0]) < 0.02


def test_curve_clamps_and_is_monotonic_between_points():
    """Curve values stay within [0, 150] and respect a monotone segment."""
    curve = Curve(points=[(0.0, 20.0), (50.0, 140.0), (100.0, 140.0)])
    xs = np.linspace(0, 100, 200)
    ys = curve.evaluate(xs)
    assert ys.min() >= 0.0 - 1e-9
    assert ys.max() <= 150.0 + 1e-9
    # Rising segment (0->50) should be non-decreasing under monotone cubic.
    rising = ys[xs <= 50]
    assert np.all(np.diff(rising) >= -1e-6)


def test_lut_endpoints_match_curve():
    """The baked LUT should agree with the curve at its ends."""
    curve = Curve(points=[(0.0, 50.0), (100.0, 150.0)])
    lut = curve.to_lut(256)
    assert abs(lut[0] - 0.5) < 1e-6
    assert abs(lut[-1] - 1.5) < 1e-6


def _oklab_chroma(srgb: np.ndarray) -> float:
    """Chroma (sqrt(a^2 + b^2)) of the first pixel of a 1x1x3 sRGB image."""
    lab = color.srgb_to_oklab(srgb)
    return float(np.hypot(lab[..., 1], lab[..., 2]).reshape(-1)[0])


def test_skin_protect_off_matches_default():
    """skin_protect=0 must reproduce the unprotected result byte-for-byte."""
    srgb = np.random.default_rng(2).random((16, 16, 3))
    curve = Curve(points=[(0.0, 50.0), (100.0, 50.0)])  # cut saturation in half
    assert np.array_equal(
        pipeline.apply_curve(srgb, curve),
        pipeline.apply_curve(srgb, curve, skin_protect=0.0),
    )


def test_skin_protect_preserves_skin():
    """A skin-hued pixel keeps most of its chroma under a desaturating curve."""
    skin = np.array([[[224 / 255, 172 / 255, 138 / 255]]], dtype=np.float64)
    curve = Curve(points=[(0.0, 50.0), (100.0, 50.0)])
    in_chroma = _oklab_chroma(skin)
    unprotected = _oklab_chroma(pipeline.apply_curve(skin, curve))
    protected = _oklab_chroma(pipeline.apply_curve(skin, curve, skin_protect=1.0))
    assert unprotected < in_chroma * 0.7  # without protection chroma collapses
    assert protected > in_chroma * 0.9  # with protection it is nearly preserved


def test_skin_protect_leaves_nonskin():
    """A blue pixel (far from the skin wedge) gets the full curve effect."""
    blue = np.array([[[0.1, 0.2, 0.9]]], dtype=np.float64)
    curve = Curve(points=[(0.0, 50.0), (100.0, 50.0)])
    base = pipeline.apply_curve(blue, curve)
    protected = pipeline.apply_curve(blue, curve, skin_protect=1.0)
    assert np.max(np.abs(base - protected)) < 1e-6


def test_skin_protect_ignores_neutrals():
    """A near-grey pixel is untouched by protection (chroma guard)."""
    grey = np.array([[[0.50, 0.495, 0.49]]], dtype=np.float64)  # faint warm tint
    curve = Curve(points=[(0.0, 50.0), (100.0, 50.0)])
    base = pipeline.apply_curve(grey, curve)
    protected = pipeline.apply_curve(grey, curve, skin_protect=1.0)
    assert np.max(np.abs(base - protected)) < 5e-3


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    _run_all()
