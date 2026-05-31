"""The editable saturation-vs-luminance curve.

The curve maps **luminance** (x, 0..100, perceptual lightness as a percentage)
to a **saturation multiplier** (y, 0..150, where 100 means "leave it alone").

It is defined by a handful of user-placed control points and smoothly
interpolated between them with a *monotone cubic* (Fritsch-Carlson) scheme.
Monotone cubics give the soft, photographer-friendly shape of a spline without
the overshoot that would make saturation dip or spike between points.

For fast per-pixel use the curve is baked into a lookup table (LUT) via
:meth:`Curve.to_lut`; the pipeline then indexes that table by luminance instead
of evaluating the spline millions of times.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

# Axis bounds, kept here so the model and the UI agree on the same numbers.
X_MIN, X_MAX = 0.0, 100.0  # luminance, percent
Y_MIN, Y_MAX = 0.0, 150.0  # saturation multiplier, percent
Y_DEFAULT = 100.0  # "no change"


@dataclass
class Curve:
    """A saturation multiplier as a function of luminance.

    Points are stored as ``(x, y)`` tuples sorted by x. A fresh curve is the
    identity edit: a flat line at y = 100% between the two axis endpoints.
    """

    points: List[Tuple[float, float]] = field(
        default_factory=lambda: [(X_MIN, Y_DEFAULT), (X_MAX, Y_DEFAULT)]
    )

    # ------------------------------------------------------------------ #
    # Construction / editing
    # ------------------------------------------------------------------ #

    def sort(self) -> None:
        """Keep control points ordered left-to-right by luminance."""
        self.points.sort(key=lambda p: p[0])

    def add_point(self, x: float, y: float) -> int:
        """Insert a control point, returning its index after sorting."""
        x = float(np.clip(x, X_MIN, X_MAX))
        y = float(np.clip(y, Y_MIN, Y_MAX))
        self.points.append((x, y))
        self.sort()
        return self.points.index((x, y))

    def move_point(self, index: int, x: float, y: float) -> int:
        """Move the point at ``index``.

        Endpoints are pinned to their x (0 or 100) so the curve always spans the
        full luminance range; interior points are clamped to stay between their
        neighbors. Returns the point's index after any re-sorting.
        """
        y = float(np.clip(y, Y_MIN, Y_MAX))
        is_first = index == 0
        is_last = index == len(self.points) - 1

        if is_first:
            x = X_MIN
        elif is_last:
            x = X_MAX
        else:
            # Stay strictly inside the neighbors so ordering never inverts.
            left = self.points[index - 1][0]
            right = self.points[index + 1][0]
            x = float(np.clip(x, left + 1e-3, right - 1e-3))

        self.points[index] = (x, y)
        return index

    def remove_point(self, index: int) -> bool:
        """Delete an interior point. Endpoints cannot be removed."""
        if index <= 0 or index >= len(self.points) - 1:
            return False
        del self.points[index]
        return True

    def reset(self) -> None:
        """Return to the identity curve (flat at 100%)."""
        self.points = [(X_MIN, Y_DEFAULT), (X_MAX, Y_DEFAULT)]

    def is_identity(self) -> bool:
        """True if the curve makes no change (every point sits at 100%)."""
        return all(abs(y - Y_DEFAULT) < 1e-6 for _, y in self.points)

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #

    def evaluate(self, xs: np.ndarray) -> np.ndarray:
        """Evaluate the curve (monotone cubic) at luminance values ``xs``.

        ``xs`` is an array of luminance percentages (0..100); the result is the
        matching saturation multiplier in percent, clamped to [Y_MIN, Y_MAX].
        """
        self.sort()
        px = np.array([p[0] for p in self.points], dtype=np.float64)
        py = np.array([p[1] for p in self.points], dtype=np.float64)
        xs = np.asarray(xs, dtype=np.float64)

        if len(px) == 1:
            return np.full_like(xs, py[0])

        ys = _monotone_cubic(px, py, np.clip(xs, X_MIN, X_MAX))
        return np.clip(ys, Y_MIN, Y_MAX)

    def to_lut(self, size: int = 1024) -> np.ndarray:
        """Bake the curve into a ``size``-entry multiplier LUT.

        Entry ``i`` is the saturation factor (1.0 == unchanged) for luminance
        ``i / (size - 1)`` in the 0..1 range. The pipeline indexes this directly.
        """
        xs = np.linspace(X_MIN, X_MAX, size)
        return self.evaluate(xs) / 100.0  # percent -> plain multiplier

    # ------------------------------------------------------------------ #
    # Serialization (for presets and per-image state)
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        return {"points": [[float(x), float(y)] for x, y in self.points]}

    @classmethod
    def from_dict(cls, data: dict) -> "Curve":
        pts = [(float(x), float(y)) for x, y in data.get("points", [])]
        curve = cls(points=pts or None)  # type: ignore[arg-type]
        if not pts:
            curve.reset()
        curve.sort()
        return curve

    def copy(self) -> "Curve":
        return Curve(points=list(self.points))


def _monotone_cubic(px: np.ndarray, py: np.ndarray, xs: np.ndarray) -> np.ndarray:
    """Fritsch-Carlson monotone cubic Hermite interpolation.

    Produces a smooth curve through ``(px, py)`` that never overshoots between
    points (no spurious bumps), evaluated at ``xs``. ``px`` must be sorted and
    strictly increasing.
    """
    n = len(px)
    if n == 2:
        # Two points: plain linear interpolation is already monotone.
        return np.interp(xs, px, py)

    # Secant slopes of each segment.
    h = np.diff(px)
    delta = np.diff(py) / h

    # Tangents at each knot, initialized to the average of adjacent secants.
    m = np.empty(n)
    m[0] = delta[0]
    m[-1] = delta[-1]
    m[1:-1] = (delta[:-1] + delta[1:]) / 2.0

    # Fritsch-Carlson correction: flatten tangents around local extrema and
    # rescale to keep each segment monotone.
    for i in range(n - 1):
        if delta[i] == 0.0:
            m[i] = 0.0
            m[i + 1] = 0.0
        else:
            a = m[i] / delta[i]
            b = m[i + 1] / delta[i]
            s = a * a + b * b
            if s > 9.0:
                t = 3.0 / np.sqrt(s)
                m[i] = t * a * delta[i]
                m[i + 1] = t * b * delta[i]

    # Locate which segment each query x falls in.
    idx = np.clip(np.searchsorted(px, xs) - 1, 0, n - 2)
    x0 = px[idx]
    x1 = px[idx + 1]
    y0 = py[idx]
    y1 = py[idx + 1]
    m0 = m[idx]
    m1 = m[idx + 1]
    hh = x1 - x0
    t = (xs - x0) / hh

    # Cubic Hermite basis functions.
    t2 = t * t
    t3 = t2 * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    return h00 * y0 + h10 * hh * m0 + h01 * y1 + h11 * hh * m1
