"""Internal validation utilities and shared type aliases.

Both the geometry module (:mod:`multiscale_rasterization.curve`) and the
format-neutral intermediate representation
(:mod:`multiscale_rasterization.scene`) accept vertices as loose,
user-supplied sequences and must coerce them into finite ``(x, y)`` pairs of
floats. Rather than duplicate that logic (and its error messages) in both
modules, it lives here.

The aliases :data:`Point` and :data:`BoundingBox` are re-exported by the
modules that use them, so ``from multiscale_rasterization.curve import Point``
keeps working.

This module has no third-party dependencies and is safe to import anywhere.
"""

from __future__ import annotations

import math

__all__ = ["Point", "BoundingBox", "coerce_point"]

#: A 2D point as an ``(x, y)`` tuple of floats.
Point = tuple[float, float]

#: An axis-aligned box as an ``(min_x, min_y, max_x, max_y)`` tuple.
BoundingBox = tuple[float, float, float, float]


def coerce_point(value: object, index: int) -> Point:
    """Coerces ``value`` into a finite ``(x, y)`` pair of floats.

    Parameters
    ----------
    value : object
        The candidate vertex. It must be an iterable that unpacks into exactly
        two numeric values (a tuple, list, or any other length-2 sequence).
    index : int
        Position of the vertex in the caller's sequence, used only to build a
        descriptive error message.

    Returns
    -------
    Point
        The vertex as a ``(float, float)`` tuple.

    Raises
    ------
    ValueError
        If ``value`` is not a pair of numbers, or if either coordinate is not
        finite.
    """
    try:
        x, y = value  # type: ignore[misc]
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"vertex {index} must be a pair (x, y), got {value!r}"
        ) from exc
    x = float(x)
    y = float(y)
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(
            f"vertex {index} must have finite coordinates, got {value!r}"
        )
    return (x, y)


# Backwards-compatible private alias: the geometry modules historically called
# this helper ``_coerce_point``. Keep the name importable so any internal or
# downstream import path keeps working, while new code uses the public name.
_coerce_point = coerce_point
