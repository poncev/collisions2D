"""Multiscale rasterization of 2D polylines.

This package exposes a Python-friendly wrapper around the C++ core. The heavy
computation happens in C++ (compiled as a CPython extension); this module only
validates inputs and converts between Python and C++ data structures.
"""

from ._core import multiscale_rasterization as _multiscale_rasterization
from ._core import version as _version

__all__ = ["multiscale_rasterization", "RasterizedObject", "__version__"]

__version__ = _version


class RasterizedObject:
    """The squares in the multiscale hierarchy touching a polyline.

    Attributes
    ----------
    corners : list[tuple[float, float]]
        Lower-left corner of each square.
    sizes : list[float]
        Side length of each square.
    levels : list[int]
        Quadtree depth of each square (0 = coarsest).
    """

    def __init__(self, corners, sizes, levels):
        self.corners = corners
        self.sizes = sizes
        self.levels = levels

    def __repr__(self):
        return (
            f"RasterizedObject(n_squares={len(self.corners)}, "
            f"levels={sorted(set(self.levels))})"
        )


def multiscale_rasterization(polyline, bounding_box, max_level):
    """Rasterize a 2D polyline at multiple scales.

    Parameters
    ----------
    polyline : sequence of (float, float)
        The vertices of the polyline, connected in order by straight edges.
    bounding_box : (min_x, min_y, max_x, max_y)
        The axis-aligned box that bounds the rasterization.
    max_level : int
        The finest subdivision depth (>= 0).

    Returns
    -------
    RasterizedObject
        The squares in the multiscale hierarchy touching the polyline.
    """
    corners, sizes, levels = _multiscale_rasterization(
        polyline, bounding_box, max_level
    )
    return RasterizedObject(corners, sizes, levels)