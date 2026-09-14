"""Multiscale rasterization of 2D polylines.

This package exposes a Python-friendly wrapper around the C++ core. The heavy
computation happens in C++ (compiled as a CPython extension); this module only
validates inputs and converts between Python and C++ data structures.

Public API
----------
multiscale_rasterization
    Rasterize a polyline at multiple scales.
RasterizedObject
    Container for the squares touching the polyline and its interior.
Curve
    Input-geometry representation (vertices + closure metadata).
Curve2D
    Internal 2D primitive of the format-neutral intermediate representation;
    models both geometry and rasterized cells.
Layer, Scene
    Intermediate-representation containers (named curve groups / document).
scene_from_rasterized, scene_from_curve
    Converters into the intermediate representation.
plot_rasterization
    Matplotlib visualization of a curve and its rasterization.
plot_scene
    Matplotlib visualization of an intermediate-representation ``Scene``.
save_rasterization
    Render a rasterization to an image file.
plot_gallery
    Draw several curves and their rasterizations in a grid of subplots.
main
    Entry point of the standalone ``python -m multiscale_rasterization`` CLI.
__version__
    The package version as a string (e.g. ``"0.1.0"``).
"""

from ._core import multiscale_rasterization as _multiscale_rasterization
from ._core import version as _version
from .curve import Curve
from .scene import (
    Curve2D,
    Layer,
    Scene,
    scene_from_curve,
    scene_from_rasterized,
)
from .visualization import (
    plot_gallery,
    plot_rasterization,
    plot_scene,
    save_rasterization,
)

__all__ = [
    "multiscale_rasterization",
    "RasterizedObject",
    "Curve",
    "Curve2D",
    "Layer",
    "Scene",
    "scene_from_curve",
    "scene_from_rasterized",
    "plot_rasterization",
    "plot_scene",
    "save_rasterization",
    "plot_gallery",
    "main",
    "__version__",
]

# `_version` is the C++ `version()` function; call it to obtain the string.
__version__ = _version()

# The C++ `CellKind` enum, mirrored here so the Python side does not depend on
# magic numbers. `_core` returns the raw integer values.
_BOUNDARY = 0
_INTERIOR = 1

# Human-readable labels for the two cell kinds.
BOUNDARY = "boundary"
INTERIOR = "interior"


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
    kinds : list[str]
        ``"boundary"`` for squares intersected by the polyline and
        ``"interior"`` for squares inside the geometry. The four lists are
        parallel: entry ``i`` of each describes the same square.
    """

    __slots__ = ("corners", "sizes", "levels", "kinds")

    def __init__(self, corners, sizes, levels, kinds=None):
        self.corners = list(corners)
        self.sizes = list(sizes)
        self.levels = list(levels)
        if kinds is None:
            # Backwards-compatible fallback: infer the kind from the geometry
            # when the caller did not provide it (e.g. hand-built objects).
            kinds = _infer_kinds(self.corners, self.sizes)
        self.kinds = [_kind_label(k) for k in kinds]

    # -- convenience -------------------------------------------------------

    @property
    def n_squares(self) -> int:
        """The number of squares in the result."""
        return len(self.corners)

    def boundary_cells(self):
        """Returns ``(corners, sizes, levels)`` for the boundary squares."""
        return self._select(BOUNDARY)

    def interior_cells(self):
        """Returns ``(corners, sizes, levels)`` for the interior squares."""
        return self._select(INTERIOR)

    def _select(self, kind):
        corners, sizes, levels = [], [], []
        for corner, size, level, k in zip(
            self.corners, self.sizes, self.levels, self.kinds
        ):
            if k == kind:
                corners.append(corner)
                sizes.append(size)
                levels.append(level)
        return corners, sizes, levels

    def levels_present(self):
        """The sorted set of quadtree levels present in the result."""
        return sorted(set(self.levels))

    def __len__(self) -> int:
        return len(self.corners)

    def __repr__(self):
        return (
            f"RasterizedObject(n_squares={len(self.corners)}, "
            f"levels={sorted(set(self.levels))})"
        )


def _kind_label(kind) -> str:
    """Normalises a cell kind (int or str) into ``"boundary"``/``"interior"``."""
    if isinstance(kind, str):
        lowered = kind.lower()
        if lowered in (BOUNDARY, INTERIOR):
            return lowered
        raise ValueError(f"unknown cell kind: {kind!r}")
    if kind == _BOUNDARY:
        return BOUNDARY
    if kind == _INTERIOR:
        return INTERIOR
    raise ValueError(f"unknown cell kind: {kind!r}")


def _infer_kinds(corners, sizes):
    """Infers cell kinds when they are not supplied.

    This is a best-effort fallback used only for hand-constructed objects. It
    labels a square as ``"interior"`` when it is fully covered by a coarser
    square of the same result, which is a reasonable proxy for the quadtree's
    interior cells. Real results always carry explicit kinds from the C++ core.
    """
    kinds = []
    for corner, size in zip(corners, sizes):
        x, y = corner
        covered = False
        for other_corner, other_size in zip(corners, sizes):
            if other_size <= size:
                continue
            ox, oy = other_corner
            if (
                ox <= x
                and oy <= y
                and ox + other_size >= x + size
                and oy + other_size >= y + size
            ):
                covered = True
                break
        kinds.append(INTERIOR if covered else BOUNDARY)
    return kinds


def multiscale_rasterization(polyline, bounding_box, max_level):
    """Rasterize a 2D polyline at multiple scales.

    Parameters
    ----------
    polyline : sequence of (float, float) or Curve
        The vertices of the polyline, connected in order by straight edges.
        A :class:`Curve` is accepted directly; its closure metadata is
        respected (a closed curve is passed to the core with an explicit
        closing vertex).
    bounding_box : (min_x, min_y, max_x, max_y)
        The axis-aligned box that bounds the rasterization.
    max_level : int
        The finest subdivision depth (>= 0).

    Returns
    -------
    RasterizedObject
        The squares in the multiscale hierarchy touching the polyline.
    """
    if isinstance(polyline, Curve):
        polyline = polyline.to_polyline()

    corners, sizes, levels, kinds = _multiscale_rasterization(
        polyline, bounding_box, max_level
    )
    return RasterizedObject(corners, sizes, levels, kinds)


def __getattr__(name):
    """Lazily exposes the CLI entry point without importing it eagerly.

    ``main`` lives in :mod:`multiscale_rasterization.cli`, which pulls in
    :mod:`argparse`. Importing it on demand keeps ``import
    multiscale_rasterization`` lightweight for callers that only need the
    rasterizer or the plotting helpers.
    """
    if name == "main":
        from .cli import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

