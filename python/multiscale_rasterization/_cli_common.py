"""Shared helpers for the two command-line front ends.

The package ships two entry points that expose essentially the same
functionality:

* ``python -m multiscale_rasterization`` — implemented in
  :mod:`multiscale_rasterization.cli`; the installed, package-relative CLI.
* ``python tools/visualize_rasterization.py`` — a self-contained script that
  can be run from a checkout without installing the package.

Both need the same built-in example shapes, the same argument surface, the
same curve/bbox loading logic and the same rendering helpers. Historically
each file carried its own copy, which drifted (different help text, slightly
different defaults, one supporting ``--gallery-figure`` and the other not).

This module is the single source of truth for that shared machinery. The two
front ends keep only what genuinely differs: their program name, their
description, and whether they expose the extra gallery-grid options.

Nothing here imports matplotlib at module import time; the rendering helpers
import it lazily so that ``--help`` and importing the package stay cheap.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .curve import Curve

__all__ = [
    "BUILTIN_SHAPES",
    "gallery_curves",
    "build_parser",
    "load_curve",
    "resolve_bbox",
    "plot_kwargs",
    "render_one",
    "render_gallery",
    "render_gallery_figure",
]


# --------------------------------------------------------------------------- #
# Built-in example shapes
# --------------------------------------------------------------------------- #

def _square() -> Curve:
    return Curve.rectangle(2.0, 2.0, 8.0, 8.0, name="square")


def _triangle() -> Curve:
    return Curve(
        [(1.0, 1.0), (9.0, 1.0), (5.0, 8.0)],
        closed=True,
        name="triangle",
    )


def _hexagon() -> Curve:
    return Curve.regular_polygon((5.0, 5.0), 3.0, 6, name="hexagon")


def _circle() -> Curve:
    return Curve.circle((5.0, 5.0), 2.5, n=32, name="circle")


def _l_shape() -> Curve:
    return Curve(
        [
            (1.0, 1.0),
            (6.0, 1.0),
            (6.0, 4.0),
            (4.0, 4.0),
            (4.0, 7.0),
            (1.0, 7.0),
        ],
        closed=True,
        name="l-shape",
    )


def _diagonal() -> Curve:
    return Curve([(0.0, 0.0), (10.0, 10.0)], closed=False, name="diagonal")


#: Mapping of built-in shape name to a zero-argument factory returning a
#: :class:`~multiscale_rasterization.curve.Curve`.
BUILTIN_SHAPES = {
    "square": _square,
    "triangle": _triangle,
    "hexagon": _hexagon,
    "circle": _circle,
    "l-shape": _l_shape,
    "diagonal": _diagonal,
}


def gallery_curves() -> list[Curve]:
    """Returns one :class:`Curve` per built-in shape, in a stable order."""
    return [factory() for factory in BUILTIN_SHAPES.values()]


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #

def build_parser(
    *,
    prog: str,
    description: str,
    defaults_in_help: bool = False,
    gallery_options: bool = False,
) -> argparse.ArgumentParser:
    """Builds the shared argument parser for a rasterization CLI.

    Parameters
    ----------
    prog : str
        Program name shown in ``--help`` (e.g. ``"multiscale_rasterization"``
        or ``"visualize_rasterization"``).
    description : str
        Description shown at the top of ``--help``.
    defaults_in_help : bool
        When ``True`` the help text annotates every option with its default
        (``ArgumentDefaultsHelpFormatter``). Default ``False``.
    gallery_options : bool
        When ``True`` two extra options are added for the gallery renderer:
        ``--gallery-cols`` and ``--gallery-figure``. Default ``False``.

    Returns
    -------
    argparse.ArgumentParser
        A parser exposing the common argument surface.
    """
    formatter_class = (
        argparse.ArgumentDefaultsHelpFormatter if defaults_in_help
        else argparse.HelpFormatter
    )
    parser = argparse.ArgumentParser(
        prog=prog,
        description=description,
        formatter_class=formatter_class,
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--shape",
        choices=sorted(BUILTIN_SHAPES),
        help="a built-in example shape",
    )
    source.add_argument(
        "--curve",
        type=Path,
        help="path to a curve JSON file (see Curve.to_json)",
    )
    source.add_argument(
        "--gallery",
        action="store_true",
        help="render every built-in shape into --output-dir",
    )

    parser.add_argument(
        "--max-level",
        type=int,
        default=4,
        help="finest quadtree subdivision depth (default: 4)",
    )
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("MIN_X", "MIN_Y", "MAX_X", "MAX_Y"),
        default=None,
        help=(
            "bounding box of the rasterization; defaults to the curve's "
            "bounding box padded by --padding"
        ),
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=0.0,
        help="padding added to the auto-computed bounding box (default: 0)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output image path (default: <shape>.png in the current dir)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="directory used by --gallery (default: current dir)",
    )
    parser.add_argument(
        "--format",
        default=None,
        help="explicit image format (png, svg, pdf, ...); inferred otherwise",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="output resolution for raster formats (default: 200)",
    )
    parser.add_argument(
        "--no-color-by-level",
        dest="color_by_level",
        action="store_false",
        help="colour cells by kind instead of by quadtree level",
    )
    parser.add_argument(
        "--no-interior",
        dest="show_interior",
        action="store_false",
        help="hide interior cells",
    )
    parser.add_argument(
        "--no-boundary",
        dest="show_boundary",
        action="store_false",
        help="hide boundary cells",
    )
    parser.add_argument(
        "--no-legend",
        dest="legend",
        action="store_false",
        help="do not draw a legend",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="override the plot title",
    )
    parser.add_argument(
        "--transparent",
        action="store_true",
        help="save with a transparent background",
    )

    if gallery_options:
        parser.add_argument(
            "--gallery-cols",
            type=int,
            default=3,
            help="number of columns in the --gallery grid",
        )
        parser.add_argument(
            "--gallery-figure",
            action="store_true",
            help=(
                "with --gallery, also write a single combined multi-panel "
                "figure named gallery.<format>"
            ),
        )

    parser.set_defaults(
        color_by_level=True,
        show_interior=True,
        show_boundary=True,
        legend=True,
    )
    return parser


# --------------------------------------------------------------------------- #
# Loading and rendering helpers
# --------------------------------------------------------------------------- #

def load_curve(args: argparse.Namespace) -> Curve:
    """Loads the curve selected by the parsed arguments.

    Resolves ``--shape`` against the built-in shapes, or ``--curve`` against a
    JSON file. Raises :class:`FileNotFoundError` when the file is missing and
    :class:`ValueError` when no source was selected.
    """
    if args.shape is not None:
        return BUILTIN_SHAPES[args.shape]()
    if args.curve is not None:
        path = Path(args.curve).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"curve file not found: {path}")
        return Curve.from_json(path.read_text(encoding="utf-8"))
    raise ValueError("no curve source selected")


def resolve_bbox(curve: Curve, args: argparse.Namespace):
    """Returns the bounding box to rasterize, honouring ``--bbox``.

    Falls back to the curve's own bounding box padded by ``--padding``.
    """
    if args.bbox is not None:
        return tuple(float(v) for v in args.bbox)
    return curve.bounding_box(padding=args.padding)


def plot_kwargs(args: argparse.Namespace) -> dict:
    """Collects the plotting options shared by single and gallery renders."""
    return {
        "color_by_level": args.color_by_level,
        "show_interior": args.show_interior,
        "show_boundary": args.show_boundary,
        "legend": args.legend,
        "title": args.title,
    }


def render_one(curve: Curve, args: argparse.Namespace, output: Path) -> Path:
    """Renders a single curve to ``output`` and returns the written path."""
    # Imported lazily: matplotlib is a soft dependency, and the CLI must be
    # able to parse arguments and print help without it installed.
    from .visualization import save_rasterization

    bbox = resolve_bbox(curve, args)
    return save_rasterization(
        curve,
        bbox,
        args.max_level,
        path=output,
        format=args.format,
        dpi=args.dpi,
        transparent=args.transparent,
        **plot_kwargs(args),
    )


def render_gallery(
    args: argparse.Namespace, *, figure: bool = False
) -> list[Path]:
    """Renders every built-in shape into ``--output-dir``.

    When ``figure`` is true a single combined multi-panel figure is produced
    as well. Returns the list of written paths.
    """
    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = args.format or "png"
    curves = gallery_curves()

    written = []
    for curve in curves:
        target = out_dir / f"{curve.name}.{suffix}"
        written.append(render_one(curve, args, target))

    if figure:
        written.append(render_gallery_figure(curves, out_dir, suffix, args))
    return written


def render_gallery_figure(
    curves, out_dir: Path, suffix: str, args: argparse.Namespace
) -> Path:
    """Writes a single combined multi-panel figure of ``curves``.

    All panels share one union bounding box so their axis scales are directly
    comparable, rather than each panel being scaled to its own curve.
    """
    import matplotlib.pyplot as plt

    from .visualization import plot_gallery

    # Union bounding box so all panels use the same scale.
    if curves:
        xs_min = min(c.bounding_box()[0] for c in curves)
        ys_min = min(c.bounding_box()[1] for c in curves)
        xs_max = max(c.bounding_box()[2] for c in curves)
        ys_max = max(c.bounding_box()[3] for c in curves)
        bbox = (xs_min, ys_min, xs_max, ys_max)
    else:
        bbox = None

    fig, _ = plot_gallery(
        curves,
        bbox,
        max_level=args.max_level,
        ncols=args.gallery_cols,
        suptitle="Multiscale rasterization gallery",
        color_by_level=args.color_by_level,
        show_interior=args.show_interior,
        show_boundary=args.show_boundary,
    )
    target = out_dir / f"gallery.{suffix}"
    try:
        fig.savefig(
            target,
            format=args.format or suffix,
            dpi=args.dpi,
            bbox_inches="tight",
        )
    finally:
        plt.close(fig)
    return target
