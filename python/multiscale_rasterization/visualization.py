"""Matplotlib visualization for multiscale rasterization results.

This module renders a polyline/curve together with the quadtree cells produced
by :func:`multiscale_rasterization.multiscale_rasterization`. It is designed
for engineering documentation and debugging.

The rasterization is first converted into the format-neutral intermediate
representation defined in :mod:`multiscale_rasterization.scene`
(:class:`~multiscale_rasterization.Curve2D`, ``Layer``, ``Scene``); this module
only maps that representation onto matplotlib artists. Keeping the two apart
means an SVG/DXF/IGES exporter can reuse the same IR without touching any
plotting code.

Default styling
---------------
* the input polyline is drawn in **red**;
* **boundary** cells (the paper's "Gray" cells) are filled **gray** with an
  **orange** wireframe, so they read as wireframe rectangles;
* **interior** cells (the paper's "Black" cells) are filled **black** with a
  **blue** outline;
* with ``color_by_level`` (the default) the face opacity ramps from coarse to
  fine cells, so the quadtree depth is visible at a glance.

Public functions
----------------
plot_rasterization
    Draw a curve and its rasterization onto a matplotlib ``Axes``.
plot_scene
    Draw a pre-built intermediate-representation ``Scene``.
save_rasterization
    Render to a file (PNG, SVG, PDF, ...), inferring the format from the
    file extension.
plot_gallery
    Draw several curves and their rasterizations in a grid of subplots.

Soft dependency
---------------
matplotlib is imported lazily and its availability is recorded in
``HAVE_MATPLOTLIB``. This keeps the core package importable in environments
where matplotlib is not installed (a lean C++-only or headless CI environment);
only a call to a plotting function requires it, and that call raises an
actionable :class:`ImportError` when matplotlib is missing.

Examples
--------
>>> from multiscale_rasterization import Curve, plot_rasterization
>>> curve = Curve.rectangle(0.0, 0.0, 10.0, 10.0, name="box")
>>> ax = plot_rasterization(curve, (0.0, 0.0, 10.0, 10.0), max_level=4)
>>> save_rasterization(curve, (0.0, 0.0, 10.0, 10.0), max_level=4,
...                    path="box.svg")
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

from .curve import Curve
from .scene import (
    KIND_BOUNDARY,
    KIND_INTERIOR,
    LAYER_BOUNDARY,
    LAYER_INTERIOR,
    Scene,
    scene_from_rasterized,
)

__all__ = [
    "plot_rasterization",
    "plot_scene",
    "save_rasterization",
    "plot_gallery",
    "HAVE_MATPLOTLIB",
]

# --------------------------------------------------------------------------- #
# Matplotlib availability (soft dependency)
# --------------------------------------------------------------------------- #
#
# matplotlib is a *soft* dependency: the package must import and the core must
# run without it. We therefore probe for matplotlib at import time, record the
# outcome in ``HAVE_MATPLOTLIB``, and only raise if a plotting function is
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
# Default visual convention (see ``plot_scene`` for the full set of options):
#
#   * the input polyline is drawn in **red**;
#   * boundary cells (the paper's "Gray" cells) are filled **gray** with an
#     **orange** wireframe, i.e. the outline makes them read as wireframes;
#   * interior cells (the paper's "Black" cells) are filled **black** with a
#     **blue** outline;
#   * when ``color_by_level`` is enabled, finer cells are drawn with a higher
#     face opacity, so the multiscale structure is visible as a depth gradient.

#: Colour of the original polyline / curve overlay.
POLYLINE_COLOR = "#d62728"  # matplotlib "tab:red"
#: Fill colour of boundary cells (the paper's "Gray" cells).
BOUNDARY_FILL_COLOR = "#bdbdbd"
#: Wireframe colour of boundary cells.
BOUNDARY_EDGE_COLOR = "#ff7f0e"  # matplotlib "tab:orange"
#: Fill colour of interior cells (the paper's "Black" cells).
INTERIOR_FILL_COLOR = "#000000"
#: Outline colour of interior cells.
INTERIOR_EDGE_COLOR = "#1f77b4"  # matplotlib "tab:blue"
#: Colour of the bounding-box outline.
BOUNDING_BOX_COLOR = "#555555"

# -- Backwards-compatible aliases -------------------------------------------- #
# Earlier revisions of this module used these names; keep them working so the
# existing tools and scripts do not break.
CURVE_COLOR = POLYLINE_COLOR
BOUNDARY_COLOR = BOUNDARY_EDGE_COLOR
INTERIOR_COLOR = INTERIOR_EDGE_COLOR

#: Alpha applied to filled cell faces (0..1) when cells are *not* shaded by
#: level. Kept low so the curve and the cell edges remain legible.
_FACE_ALPHA = 0.35

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
# Input coercion helpers
# --------------------------------------------------------------------------- #

def _resolve_result(polyline, bounding_box, max_level, result):
    """Obtains a :class:`RasterizedObject` from either an explicit result or by
    running the rasterizer. Imported lazily to avoid a circular import.
    """
    from . import RasterizedObject, _multiscale_rasterization

    if result is not None:
        if not isinstance(result, RasterizedObject):
            raise TypeError(
                "result must be a RasterizedObject, got "
                f"{type(result).__name__}"
            )
        return result

    if bounding_box is None or max_level is None:
        raise ValueError(
            "either provide a precomputed `result`, or both `bounding_box` "
            "and `max_level` to run the rasterization"
        )

    if isinstance(polyline, Curve):
        polyline = polyline.to_polyline()
    corners, sizes, levels, kinds = _multiscale_rasterization(
        polyline, bounding_box, max_level
    )
    return RasterizedObject(corners, sizes, levels, kinds)


def _alpha_for_level(level, levels, base_alpha: float, color_by_level: bool) -> float:
    """Returns the face opacity for a cell at ``level``.

    When ``color_by_level`` is false the caller's ``base_alpha`` is used
    unchanged. Otherwise the opacity is ramped from ``_LEVEL_ALPHA_RANGE``
    across the levels present, scaled so that the finest level is drawn at
    exactly ``base_alpha``. This gives a readable, monotonic depth gradient
    without letting any cell become fully opaque.
    """
    if not color_by_level or not levels:
        return base_alpha
    lo, hi = min(levels), max(levels)
    if hi == lo:
        return base_alpha
    frac = (level - lo) / (hi - lo)
    a0, a1 = _LEVEL_ALPHA_RANGE
    return base_alpha * (a0 + (a1 - a0) * frac) / a1


#: Draw order and default styling for the two cell kinds. Interior cells come
#: first (and live on a lower z-order) so boundary wires stay on top.
_CELL_SPECS = (
    (
        LAYER_INTERIOR,
        KIND_INTERIOR,
        INTERIOR_FILL_COLOR,
        INTERIOR_EDGE_COLOR,
        2.0,
    ),
    (
        LAYER_BOUNDARY,
        KIND_BOUNDARY,
        BOUNDARY_FILL_COLOR,
        BOUNDARY_EDGE_COLOR,
        3.0,
    ),
)


# --------------------------------------------------------------------------- #
# Core drawing
# --------------------------------------------------------------------------- #

def _draw_cells(
    ax,
    scene: Scene,
    *,
    show_boundary: bool,
    show_interior: bool,
    color_by_level: bool,
    boundary_alpha: float,
    interior_alpha: float,
    linewidth: float,
    label_prefix: str,
):
    """Draws every rasterized cell of ``scene`` onto ``ax``.

    Cells are grouped by ``(kind, level)`` and drawn as one
    ``PatchCollection`` per group, ordered coarse-to-fine so finer cells sit on
    top and the multiscale structure stays readable. Interior cells are drawn
    beneath boundary cells.

    Returns
    -------
    list
        Legend handles (possibly empty).
    """
    _, _, Polygon, PatchCollection = _require_matplotlib()
    from matplotlib.patches import Patch

    levels = scene.levels()
    handles: list = []

    for layer_name, kind, fill, edge, zorder in _CELL_SPECS:
        if kind == KIND_BOUNDARY and not show_boundary:
            continue
        if kind == KIND_INTERIOR and not show_interior:
            continue

        base_alpha = (
            boundary_alpha if kind == KIND_BOUNDARY else interior_alpha
        )

        # Group the layer's primitives by level, preserving a coarse-to-fine
        # order (None sorts first, which only happens for hand-built scenes).
        by_level: dict[int | None, list] = {}
        for curve in scene.iter_layer(layer_name):
            by_level.setdefault(curve.level, []).append(curve)
        ordered = sorted(by_level, key=lambda lv: (lv is None, lv))

        total = sum(len(curves) for curves in by_level.values())
        if total == 0:
            continue

        for index, level in enumerate(ordered):
            curves = by_level[level]
            alpha = _alpha_for_level(level, levels, base_alpha, color_by_level)
            patches = [Polygon(curve.points, closed=True) for curve in curves]
            ax.add_collection(
                PatchCollection(
                    patches,
                    facecolors=fill,
                    edgecolors=edge,
                    linewidths=linewidth,
                    alpha=alpha,
                    match_original=False,
                    # Coarse cells first; the tiny index offset keeps the
                    # ordering stable without depending on level magnitude.
                    zorder=zorder + index * 1e-3,
                )
            )

        # One legend entry per level when shading by depth, otherwise a single
        # entry summarising the whole kind.
        if color_by_level:
            for level in ordered:
                n = len(by_level[level])
                label = (
                    f"{label_prefix}{kind}"
                    if level is None
                    else f"{label_prefix}{kind} L{level}"
                )
                handles.append(
                    Patch(
                        facecolor=fill,
                        edgecolor=edge,
                        alpha=0.9,
                        label=f"{label} ({n})",
                    )
                )
        else:
            handles.append(
                Patch(
                    facecolor=fill,
                    edgecolor=edge,
                    alpha=0.9,
                    label=f"{label_prefix}{kind} ({total})",
                )
            )

    return handles


def _draw_scene_curve(ax, scene: Scene, *, linewidth: float) -> bool:
    """Overlays the input geometry (non-cell primitives) on top of the cells.

    Returns ``True`` when anything was drawn.
    """
    drawn = False
    for curve in scene.iter_curves():
        if curve.is_cell:
            continue
        xs, ys = zip(*curve.to_polyline())
        if len(xs) < 2:
            continue
        label = curve.name or (
            "curve" if curve.closed else "polyline"
        )
        ax.plot(
            xs,
            ys,
            color=POLYLINE_COLOR,
            linewidth=linewidth,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=5,
            label=label,
        )
        # Emphasise the vertices only when the geometry is coarse enough to
        # read without the markers becoming noise.
        if len(xs) <= 64:
            ax.plot(
                xs,
                ys,
                linestyle="none",
                marker="o",
                markersize=3.0,
                markerfacecolor="white",
                markeredgecolor=POLYLINE_COLOR,
                markeredgewidth=linewidth * 0.6,
                zorder=6,
            )
        drawn = True
    return drawn


def _draw_bounding_box(ax, bounding_box, *, linewidth: float):
    """Draws the bounding box as a dashed reference outline."""
    if bounding_box is None:
        return
    xmin, ymin, xmax, ymax = bounding_box
    ax.plot(
        [xmin, xmax, xmax, xmin, xmin],
        [ymin, ymin, ymax, ymax, ymin],
        color=BOUNDING_BOX_COLOR,
        linewidth=linewidth,
        linestyle="--",
        zorder=1,
        label="bounding box",
    )


def _autolimits_scene(ax, scene: Scene, bounds):
    """Sets axis limits covering the scene's geometry and the given bounds.

    The scene's own bounds (which include every cell) are unioned with any
    explicit ``bounds`` so that neither the geometry nor the cells are clipped.
    """
    box = scene.bounds()
    if box is None:
        box = (math.inf, math.inf, -math.inf, -math.inf)

    xmin, ymin, xmax, ymax = box
    if bounds is not None:
        bxmin, bymin, bxmax, bymax = bounds
        xmin, xmax = min(xmin, bxmin), max(xmax, bxmax)
        ymin, ymax = min(ymin, bymin), max(ymax, bymax)

    _apply_limits(ax, (xmin, ymin, xmax, ymax))


def _apply_limits(ax, box):
    """Applies a padded axis limit from ``(xmin, ymin, xmax, ymax)``."""
    xmin, ymin, xmax, ymax = box
    if not (math.isfinite(xmin) and math.isfinite(xmax)
            and math.isfinite(ymin) and math.isfinite(ymax)):
        return
    if xmax - xmin == 0:
        xmin, xmax = xmin - 0.5, xmax + 0.5
    if ymax - ymin == 0:
        ymin, ymax = ymin - 0.5, ymax + 0.5

    pad_x = 0.04 * (xmax - xmin)
    pad_y = 0.04 * (ymax - ymin)
    ax.set_xlim(xmin - pad_x, xmax + pad_x)
    ax.set_ylim(ymin - pad_y, ymax + pad_y)


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


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def plot_rasterization(
    polyline,
    bounding_box: Sequence[float] | None = None,
    max_level: int | None = None,
    *,
    result=None,
    ax=None,
    title: str | None = None,
    show_boundary: bool = True,
    show_interior: bool = True,
    show_curve: bool = True,
    show_bounding_box: bool = True,
    color_by_level: bool = True,
    boundary_alpha: float = _FACE_ALPHA,
    interior_alpha: float = _FACE_ALPHA,
    linewidth: float = 0.8,
    curve_linewidth: float = 1.8,
    legend: bool = True,
    label_prefix: str = "",
):
    """Plots a polyline/curve together with its multiscale rasterization.

    The rasterization can be supplied either directly through ``result`` or
    computed on the fly by passing ``bounding_box`` and ``max_level``.

    Parameters
    ----------
    polyline : Curve or sequence of (float, float)
        The geometry to draw. A :class:`Curve` is preferred as it carries
        closure and name metadata.
    bounding_box : (min_x, min_y, max_x, max_y), optional
        Required unless ``result`` is given.
    max_level : int, optional
        Finest subdivision depth. Required unless ``result`` is given.
    result : RasterizedObject, optional
        A precomputed rasterization. When provided, ``bounding_box`` and
        ``max_level`` are ignored (only used for axis limits).
    ax : matplotlib.axes.Axes, optional
        Axes to draw on. A new figure and axes are created when omitted.
    title : str, optional
        Plot title. Defaults to the curve's name when it has one, otherwise a
        summary line describing the result.
    show_boundary, show_interior : bool
        Toggle the drawing of each cell kind. Default ``True``.
    show_curve : bool
        Draw the original geometry as a red overlay. Default ``True``.
    show_bounding_box : bool
        Draw the bounding box as a dashed outline. Default ``True``.
    color_by_level : bool
        When ``True`` (default) the face opacity is ramped from coarse to fine
        cells so the multiscale depth is visible; when ``False`` a single
        opacity per kind is used.
    boundary_alpha, interior_alpha : float
        Face transparency in ``[0, 1]`` for each cell kind, applied to the
        finest level when ``color_by_level`` is set.
    linewidth : float
        Edge width of the cell polygons.
    curve_linewidth : float
        Line width of the geometry overlay.
    legend : bool
        Whether to draw a legend. Default ``True``.
    label_prefix : str
        Prefix added to every legend label (useful when composing subplots).

    Returns
    -------
    matplotlib.axes.Axes
        The axes the rasterization was drawn on, so callers can further
        customise it or embed it in a larger figure.
    """
    resolved = _resolve_result(polyline, bounding_box, max_level, result)
    scene = scene_from_rasterized(
        resolved,
        curve=polyline,
        bounding_box=bounding_box,
    )
    resolved_bounds = bounding_box if bounding_box is not None else scene.bounds()

    return plot_scene(
        scene,
        ax=ax,
        title=title,
        bounds=resolved_bounds,
        show_boundary=show_boundary,
        show_interior=show_interior,
        show_curve=show_curve,
        show_bounding_box=show_bounding_box,
        color_by_level=color_by_level,
        boundary_alpha=boundary_alpha,
        interior_alpha=interior_alpha,
        linewidth=linewidth,
        curve_linewidth=curve_linewidth,
        legend=legend,
        label_prefix=label_prefix,
    )


def plot_scene(
    scene: Scene,
    *,
    ax=None,
    title: str | None = None,
    bounds: Sequence[float] | None = None,
    show_boundary: bool = True,
    show_interior: bool = True,
    show_curve: bool = True,
    show_bounding_box: bool = True,
    color_by_level: bool = True,
    boundary_alpha: float = _FACE_ALPHA,
    interior_alpha: float = _FACE_ALPHA,
    linewidth: float = 0.8,
    curve_linewidth: float = 1.8,
    legend: bool = True,
    label_prefix: str = "",
    figsize: tuple[float, float] = (7.0, 7.0),
    dpi: int = 110,
):
    """Renders an intermediate-representation :class:`Scene` with matplotlib.

    This is the rendering back end that :func:`plot_rasterization` uses. It is
    public so that callers who already hold a :class:`Scene` (for instance one
    that was cached to JSON, or built by hand or by a future importer) can draw
    it directly, without going through the rasterizer or the
    ``RasterizedObject`` container.

    Styling follows the module convention: the geometry is red, boundary cells
    are gray with an orange wireframe, and interior cells are black with a blue
    outline. With ``color_by_level`` (the default) the face opacity ramps from
    coarse to fine cells, so deeper levels read as denser.

    Parameters
    ----------
    scene : Scene
        The intermediate representation to draw.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on. A new figure and axes are created when omitted.
    title : str, optional
        Plot title. Defaults to a summary of the scene's contents.
    bounds : (min_x, min_y, max_x, max_y), optional
        Axis limits. Defaults to ``scene.bounds()``.
    show_boundary, show_interior, show_curve, show_bounding_box : bool
        Toggles for each element. Default ``True``.
    color_by_level : bool
        Ramp the face opacity by quadtree level. Default ``True``.
    boundary_alpha, interior_alpha : float
        Face opacity for each cell kind at the finest level.
    linewidth : float
        Edge width of the cell polygons.
    curve_linewidth : float
        Line width of the geometry overlay.
    legend : bool
        Whether to draw a legend. Default ``True``.
    label_prefix : str
        Prefix added to every legend label.
    figsize : (float, float)
        Figure size when a new figure is created.
    dpi : int
        Figure resolution when a new figure is created.

    Returns
    -------
    matplotlib.axes.Axes
        The axes the scene was drawn on.

    Raises
    ------
    TypeError
        If ``scene`` is not a :class:`Scene`.
    """
    _, plt, _, _ = _require_matplotlib()

    if not isinstance(scene, Scene):
        raise TypeError(
            f"plot_scene expects a Scene, got {type(scene).__name__}"
        )

    if ax is None:
        _, ax = plt.subplots(figsize=figsize, dpi=dpi)

    effective_bounds = bounds if bounds is not None else scene.bounds()

    if show_bounding_box and effective_bounds is not None:
        _draw_bounding_box(ax, effective_bounds, linewidth=linewidth)

    handles = _draw_cells(
        ax,
        scene,
        show_boundary=show_boundary,
        show_interior=show_interior,
        color_by_level=color_by_level,
        boundary_alpha=boundary_alpha,
        interior_alpha=interior_alpha,
        linewidth=linewidth,
        label_prefix=label_prefix,
    )

    curve_drawn = False
    if show_curve:
        curve_drawn = _draw_scene_curve(
            ax, scene, linewidth=curve_linewidth
        )

    _autolimits_scene(ax, scene, effective_bounds)

    if title is None:
        levels = scene.levels()
        counts = scene.counts()
        n_cells = counts.get(LAYER_BOUNDARY, 0) + counts.get(LAYER_INTERIOR, 0)
        if scene.name:
            title = f"{scene.name} — multiscale rasterization"
        else:
            title = f"Multiscale rasterization ({n_cells} cells, levels {levels})"
    _style_axes(ax, title)

    if legend:
        # Pass the cell handles explicitly: PatchCollections are not reliably
        # picked up by matplotlib's automatic legend detection. Line artists
        # (the curve overlay and the bounding box) are appended from the axes
        # so their labels are not lost.
        line_handles = [
            artist
            for artist in ax.get_lines()
            if artist.get_label() and not artist.get_label().startswith("_")
        ]
        combined = handles + line_handles
        if combined:
            ax.legend(
                handles=combined,
                loc="upper left",
                bbox_to_anchor=(1.01, 1.0),
                frameon=False,
                fontsize=8,
                borderaxespad=0.0,
            )

    return ax


def save_rasterization(
    polyline,
    bounding_box: Sequence[float] | None = None,
    max_level: int | None = None,
    *,
    path,
    result=None,
    format: str | None = None,
    dpi: int = 200,
    transparent: bool = False,
    **plot_kwargs,
) -> Path:
    """Renders a rasterization to a file.

    This is a thin convenience wrapper around :func:`plot_rasterization` that
    also writes the figure to disk and closes it, so it is safe to call in a
    loop.

    Parameters
    ----------
    polyline, bounding_box, max_level, result
        Forwarded to :func:`plot_rasterization`.
    path : str or pathlib.Path
        Destination file. The format is inferred from the extension unless
        ``format`` is given (``png``, ``svg``, ``pdf``, ... ).
    format : str, optional
        Explicit matplotlib format string overriding the extension.
    dpi : int
        Output resolution for raster formats. Default ``200``.
    transparent : bool
        Save with a transparent background. Default ``False``.
    **plot_kwargs
        Any remaining keyword arguments are forwarded to
        :func:`plot_rasterization` (e.g. ``color_by_level``, ``title``).

    Returns
    -------
    pathlib.Path
        The path that was written.

    Raises
    ------
    ValueError
        If the extension is missing and no explicit ``format`` is provided.
    """
    _, plt, _, _ = _require_matplotlib()

    out = Path(path).expanduser()

    if format is None:
        suffix = out.suffix.lower().lstrip(".")
        if not suffix:
            raise ValueError(
                f"cannot infer image format from {out!s}; pass format='png' "
                "(or another matplotlib format)"
            )
        format = suffix
    else:
        format = format.lower().lstrip(".")

    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7.0, 7.0), dpi=110)
    try:
        plot_rasterization(
            polyline,
            bounding_box,
            max_level,
            result=result,
            ax=ax,
            **plot_kwargs,
        )
        fig.savefig(
            out,
            format=format,
            dpi=dpi,
            bbox_inches="tight",
            transparent=transparent,
        )
    finally:
        plt.close(fig)

    return out


def plot_gallery(
    curves,
    bounding_box=None,
    max_level: int = 4,
    *,
    ncols: int = 3,
    figsize=None,
    suptitle: str | None = None,
    **plot_kwargs,
):
    """Draws several curves and their rasterizations in a grid of subplots.

    This is the publication-ready companion to :func:`plot_rasterization`: it
    lays out one panel per curve with a shared, consistent style, which is
    convenient for comparing shapes or subdivision depths side by side.

    Parameters
    ----------
    curves : iterable of Curve or (polyline, bounding_box, max_level)
        The items to plot. Each item is either a :class:`Curve` (in which case
        the shared ``bounding_box`` and ``max_level`` are used) or a
        ``(polyline, bounding_box, max_level)`` triple overriding them.
    bounding_box : (min_x, min_y, max_x, max_y), optional
        Default bounding box for items given as plain curves. When omitted,
        each curve's own bounding box is used.
    max_level : int
        Default finest subdivision depth for items given as plain curves.
    ncols : int
        Number of columns in the grid. Default ``3``.
    figsize : (float, float), optional
        Figure size in inches. Defaults to a size derived from the grid.
    suptitle : str, optional
        Overall figure title.
    **plot_kwargs
        Forwarded to :func:`plot_rasterization` for every panel (e.g.
        ``color_by_level``, ``show_interior``).

    Returns
    -------
    (matplotlib.figure.Figure, numpy.ndarray)
        The figure and the 2-D array of axes, so callers can post-process the
        result.
    """
    _, plt, _, _ = _require_matplotlib()
    import numpy as np

    items = list(curves)
    if not items:
        raise ValueError("plot_gallery needs at least one curve")

    n = len(items)
    ncols = max(1, min(ncols, n))
    nrows = math.ceil(n / ncols)

    if figsize is None:
        figsize = (4.2 * ncols, 4.2 * nrows)

    fig, axes = plt.subplots(
        nrows, ncols, figsize=figsize, dpi=110, squeeze=False
    )

    for index, item in enumerate(items):
        row, col = divmod(index, ncols)
        ax = axes[row][col]

        if isinstance(item, Curve):
            polyline = item
            bbox = bounding_box if bounding_box is not None else item.bounding_box()
            level = max_level
        else:
            polyline, bbox, level = item

        plot_rasterization(
            polyline,
            bbox,
            level,
            ax=ax,
            legend=False,
            **plot_kwargs,
        )

    # Hide any unused panels so the grid looks tidy.
    for index in range(n, nrows * ncols):
        row, col = divmod(index, ncols)
        axes[row][col].set_visible(False)

    if suptitle:
        fig.suptitle(suptitle, fontsize=14, fontweight="bold")
    fig.tight_layout()
    return fig, axes