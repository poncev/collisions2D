"""Matplotlib visualization for multiscale rasterization results.

This module renders the quadtree cells produced by
:func:`multiscale_rasterization.multiscale_rasterization` onto a matplotlib
axes object. It exists for engineering documentation and debugging.

The module exposes a single function, :func:`render_rasterization`, that draws
directly from a :class:`RasterizedObject` (there is no intermediate scene
representation). Simply create a matplotlib axis and pass it in:

>>> import matplotlib.pyplot as plt
>>> from multiscale_rasterization import multiscale_rasterization, render_rasterization
>>> result = multiscale_rasterization([(0, 0), (10, 10)], (0, 0, 10, 10), max_level=3)
>>> fig, ax = plt.subplots()
>>> render_rasterization(result, ax)
>>> plt.show()

Default styling
---------------
* **boundary** cells (the paper's "Gray" cells) are filled **gray** with an
  **orange** wireframe;
* **interior** cells (the paper's "Black" cells) are filled **black** with a
  **blue** outline;
* with ``color_by_level`` (the default) the face opacity ramps from coarse to
  fine cells, so the quadtree depth is visible at a glance.

Soft dependency
---------------
matplotlib is imported lazily and its availability is recorded in
``HAVE_MATPLOTLIB``. This keeps the core package importable in environments
where matplotlib is not installed (a lean C++-only or headless CI
environment); only a call to :func:`render_rasterization` requires it, and that
call raises an actionable :class:`ImportError` when matplotlib is missing.
"""

from __future__ import annotations

import math

__all__ = [
    "render_rasterization",
    "HAVE_MATPLOTLIB",
]

# --------------------------------------------------------------------------- #
# Matplotlib availability (soft dependency)
# --------------------------------------------------------------------------- #
#
# matplotlib is a *soft* dependency: the package must import and the core must
# run without it. We therefore probe for matplotlib at import time, record the
# outcome in ``HAVE_MATPLOTLIB``, and only raise if the plotting function is
# actually called. This keeps headless CI and C++-only environments working.

try:  # pragma: no cover - depends on the environment
    import matplotlib as _matplotlib

    HAVE_MATPLOTLIB = True
    _MATPLOTLIB_IMPORT_ERROR: ImportError | None = None
except ImportError as _exc:  # pragma: no cover - depends on the environment
    _matplotlib = None
    HAVE_MATPLOTLIB = False
    _MATPLOTLIB_IMPORT_ERROR = _exc

_MATPLOTLIB_HINT = (
    "Matplotlib is required for plotting but is not installed. Install it "
    "with `mamba install matplotlib` (or `pip install matplotlib`) and retry. "
    "The rest of multiscale_rasterization works without it."
)


# --------------------------------------------------------------------------- #
# Style constants
# --------------------------------------------------------------------------- #
#
# Default visual convention:
#
#   * boundary cells (the paper's "Gray" cells) are filled gray with an orange
#     wireframe, i.e. the outline makes them read as wireframes;
#   * interior cells (the paper's "Black" cells) are filled black with a blue
#     outline;
#   * when ``color_by_level`` is enabled, finer cells are drawn with a higher
#     face opacity, so the multiscale structure is visible as a depth gradient.

#: Fill colour of boundary cells (the paper's "Gray" cells).
BOUNDARY_FILL_COLOR = "#bdbdbd"
#: Wireframe colour of boundary cells.
BOUNDARY_EDGE_COLOR = "#ff7f0e"  # matplotlib "tab:orange"
#: Fill colour of interior cells (the paper's "Black" cells).
INTERIOR_FILL_COLOR = "#000000"
#: Outline colour of interior cells.
INTERIOR_EDGE_COLOR = "#1f77b4"  # matplotlib "tab:blue"

#: Alpha applied to filled cell faces (0..1) when cells are *not* shaded by
#: level, and to the finest level when they are.
_FACE_ALPHA = 0.5

#: Face-opacity range used by ``color_by_level``: coarse cells are the most
#: transparent, fine cells the most opaque. Edges stay fully opaque.
_LEVEL_ALPHA_RANGE = (0.30, 0.85)


# --------------------------------------------------------------------------- #
# Lazy matplotlib access
# --------------------------------------------------------------------------- #

def _require_matplotlib():
    """Imports and returns the matplotlib modules used by this package.

    The modules are imported lazily (rather than at module import time) so
    that ``import multiscale_rasterization`` succeeds without matplotlib.

    Returns
    -------
    (module, module, type, type)
        ``(matplotlib, pyplot, Polygon, PatchCollection)``.

    Raises
    ------
    ImportError
        If matplotlib is not available, with an actionable message.
    """
    if not HAVE_MATPLOTLIB:  # pragma: no cover - depends on environment
        raise ImportError(_MATPLOTLIB_HINT) from _MATPLOTLIB_IMPORT_ERROR
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon
        from matplotlib.collections import PatchCollection
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(_MATPLOTLIB_HINT) from exc
    return matplotlib, plt, Polygon, PatchCollection


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _alpha_for_level(level, levels, base_alpha: float, color_by_level: bool) -> float:
    """Returns the face opacity for a cell at ``level``.

    When ``color_by_level`` is false the caller's ``base_alpha`` is used
    unchanged. Otherwise the opacity is ramped from ``_LEVEL_ALPHA_RANGE``
    across the levels present, scaled so that the finest level is drawn at
    exactly ``base_alpha``. This gives a readable, monotonic depth gradient
    without letting any cell become fully opaque.
    """
    if not color_by_level or not levels or level is None:
        return base_alpha
    lo, hi = min(levels), max(levels)
    if hi == lo:
        return base_alpha
    frac = (level - lo) / (hi - lo)
    a0, a1 = _LEVEL_ALPHA_RANGE
    return base_alpha * (a0 + (a1 - a0) * frac) / a1


def _cell_polygons(corners, sizes):
    """Builds one square :class:`Polygon` per ``(corner, size)`` pair."""
    _, _, Polygon, _ = _require_matplotlib()
    return [
        Polygon(
            [
                (x, y),
                (x + size, y),
                (x + size, y + size),
                (x, y + size),
            ]
        )
        for (x, y), size in zip(corners, sizes)
    ]


def _draw_cells(
    ax,
    polygons,
    levels_of_cells,
    *,
    levels,
    fill_color,
    edge_color,
    base_alpha,
    color_by_level,
    linewidth,
    label,
    zorder,
):
    """Draws one group of squares as a single :class:`PatchCollection`.

    Cells are ordered coarse-to-fine and grouped by level; the face opacity is
    ramped by the level when ``color_by_level`` is enabled. Returns ``True``
    when something was drawn (so the caller can build a legend handle).
    """
    from matplotlib.collections import PatchCollection

    if not polygons:
        return False

    order = sorted(
        range(len(polygons)),
        key=lambda i: (levels_of_cells[i] is None, levels_of_cells[i]),
    )
    ordered_polygons = [polygons[i] for i in order]
    ordered_levels = [levels_of_cells[i] for i in order]
    alphas = [
        _alpha_for_level(lv, levels, base_alpha, color_by_level)
        for lv in ordered_levels
    ]

    import matplotlib.colors as mcolors

    fill_rgb = mcolors.to_rgb(fill_color)
    edge_rgb = mcolors.to_rgb(edge_color)

    collection = PatchCollection(
        ordered_polygons,
        facecolors=[(*fill_rgb, a) for a in alphas],
        edgecolors=[(*edge_rgb, 1.0)] * len(ordered_polygons),
        linewidths=linewidth,
        label=label,
        zorder=zorder,
    )
    ax.add_collection(collection)
    return True


def _style_axes(ax, title):
    """Applies the clean, documentation-oriented look."""
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    if title:
        ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(True, which="major", color="#e6e6e6", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color("#cccccc")


def _apply_limits(ax, box, *, pad_fraction: float = 0.0):
    """Applies axis limits from ``(xmin, ymin, xmax, ymax)``."""
    xmin, ymin, xmax, ymax = box
    if not (
        math.isfinite(xmin)
        and math.isfinite(xmax)
        and math.isfinite(ymin)
        and math.isfinite(ymax)
    ):
        return
    if xmax - xmin == 0:
        xmin, xmax = xmin - 0.5, xmax + 0.5
    if ymax - ymin == 0:
        ymin, ymax = ymin - 0.5, ymax + 0.5

    pad_x = pad_fraction * (xmax - xmin)
    pad_y = pad_fraction * (ymax - ymin)
    ax.set_xlim(xmin - pad_x, xmax + pad_x)
    ax.set_ylim(ymin - pad_y, ymax + pad_y)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def render_rasterization(rasterized_object, output, **kwargs):
    """Render a :class:`RasterizedObject` onto a matplotlib axis.

    This is the single visualization entry point. It draws the rasterization
    result (the output of :func:`multiscale_rasterization`) directly onto a
    caller-provided matplotlib axis.

    Parameters
    ----------
    rasterized_object : RasterizedObject
        The rasterization result to render. Must expose ``corners``, ``sizes``,
        ``levels`` and ``kinds``.
    output : matplotlib.axes.Axes
        The matplotlib axis to draw on. It is modified in place and returned.
    **kwargs : optional
        Additional styling options:

        title : str, optional
            Axis title. Defaults to a summary of the cell counts and levels.
        show_boundary : bool
            Draw boundary cells (gray fill, orange edges). Default: ``True``.
        show_interior : bool
            Draw interior cells (black fill, blue edges). Default: ``True``.
        color_by_level : bool
            Ramp cell opacity by quadtree level (coarse→fine). Default: ``True``.
        boundary_alpha : float
            Face opacity for boundary cells ``[0, 1]``. Default: ``0.5``.
        interior_alpha : float
            Face opacity for interior cells ``[0, 1]``. Default: ``0.5``.
        linewidth : float
            Edge width of the cell polygons. Default: ``0.8``.
        legend : bool
            Draw a legend identifying the cell types. Default: ``True``.

    Returns
    -------
    matplotlib.axes.Axes
        The output axis (the same object that was passed in).

    Raises
    ------
    TypeError
        If ``rasterized_object`` is not a :class:`RasterizedObject` or if
        ``output`` does not look like a matplotlib axis.
    ImportError
        If matplotlib is not installed.

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> from multiscale_rasterization import multiscale_rasterization
    >>> polyline = [(0, 0), (10, 10), (20, 0)]
    >>> result = multiscale_rasterization(polyline, (0, 0, 20, 20), max_level=3)
    >>> fig, ax = plt.subplots()
    >>> render_rasterization(result, ax, color_by_level=False)
    >>> plt.show()
    """
    from . import RasterizedObject

    _require_matplotlib()

    if not isinstance(rasterized_object, RasterizedObject):
        raise TypeError(
            "rasterized_object must be a RasterizedObject, got "
            f"{type(rasterized_object).__name__}"
        )
    if not hasattr(output, "add_collection"):
        raise TypeError(
            "output must be a matplotlib Axes, got "
            f"{type(output).__name__}"
        )

    title = kwargs.get("title")
    show_boundary = kwargs.get("show_boundary", True)
    show_interior = kwargs.get("show_interior", True)
    color_by_level = kwargs.get("color_by_level", True)
    boundary_alpha = kwargs.get("boundary_alpha", _FACE_ALPHA)
    interior_alpha = kwargs.get("interior_alpha", _FACE_ALPHA)
    linewidth = kwargs.get("linewidth", 0.8)
    legend = kwargs.get("legend", True)

    levels = rasterized_object.levels_present()
    handles = []

    # Interior cells are drawn first, on a lower z-order, so boundary wires
    # stay readable on top of them.
    if show_interior:
        i_corners, i_sizes, i_levels = rasterized_object.interior_cells()
        if _draw_cells(
            output,
            _cell_polygons(i_corners, i_sizes),
            i_levels,
            levels=levels,
            fill_color=INTERIOR_FILL_COLOR,
            edge_color=INTERIOR_EDGE_COLOR,
            base_alpha=interior_alpha,
            color_by_level=color_by_level,
            linewidth=linewidth,
            label="Interior cells",
            zorder=2.0,
        ):
            from matplotlib.patches import Patch

            handles.append(
                Patch(
                    facecolor=INTERIOR_FILL_COLOR,
                    edgecolor=INTERIOR_EDGE_COLOR,
                    label="Interior cells",
                )
            )

    if show_boundary:
        b_corners, b_sizes, b_levels = rasterized_object.boundary_cells()
        if _draw_cells(
            output,
            _cell_polygons(b_corners, b_sizes),
            b_levels,
            levels=levels,
            fill_color=BOUNDARY_FILL_COLOR,
            edge_color=BOUNDARY_EDGE_COLOR,
            base_alpha=boundary_alpha,
            color_by_level=color_by_level,
            linewidth=linewidth,
            label="Boundary cells",
            zorder=3.0,
        ):
            from matplotlib.patches import Patch

            handles.append(
                Patch(
                    facecolor=BOUNDARY_FILL_COLOR,
                    edgecolor=BOUNDARY_EDGE_COLOR,
                    label="Boundary cells",
                )
            )

    # Fit the axis to the cells that were drawn.
    corners = rasterized_object.corners
    sizes = rasterized_object.sizes
    if corners and sizes:
        xs = [x for x, _ in corners] + [
            x + size for (x, _), size in zip(corners, sizes)
        ]
        ys = [y for _, y in corners] + [
            y + size for (_, y), size in zip(corners, sizes)
        ]
        _apply_limits(output, (min(xs), min(ys), max(xs), max(ys)))

    if title is None:
        n_boundary = len(rasterized_object.boundary_cells()[0])
        n_interior = len(rasterized_object.interior_cells()[0])
        title = (
            f"Multiscale rasterization "
            f"({n_boundary + n_interior} cells, levels {levels})"
        )
    _style_axes(output, title)

    if legend and handles:
        output.legend(
            handles=handles,
            loc="upper left",
            bbox_to_anchor=(1.01, 1.0),
            frameon=False,
            fontsize=8,
            borderaxespad=0.0,
        )

    return output
