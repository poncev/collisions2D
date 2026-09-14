"""Standalone command-line tool for visualizing multiscale rasterizations.

This module provides a small, dependency-light CLI so that a user can render a
rasterization without writing any Python. It is exposed as
``python -m multiscale_rasterization`` (see :mod:`multiscale_rasterization.__main__`)
and can also be invoked programmatically through :func:`main`.

The tool accepts a curve either as a built-in shape (``square``, ``triangle``,
``hexagon``, ``circle``, ``l-shape``, ``diagonal``) or as a JSON file in the
format produced by :meth:`multiscale_rasterization.Curve.to_json`.

Examples
--------
Render a built-in square to a PNG::

    python -m multiscale_rasterization --shape square --max-level 4 \\
        --output square.png

Render a curve stored as JSON, colouring cells by kind instead of level::

    python -m multiscale_rasterization --curve my_curve.json \\
        --max-level 5 --no-color-by-level --output my_curve.svg

Render every built-in example into a directory::

    python -m multiscale_rasterization --gallery --output-dir examples/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .curve import Curve

__all__ = ["main", "build_parser", "BUILTIN_SHAPES", "gallery_curves"]


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

def build_parser() -> argparse.ArgumentParser:
    """Builds the :class:`argparse.ArgumentParser` for the CLI."""
    parser = argparse.ArgumentParser(
        prog="multiscale_rasterization",
        description=(
            "Visualize the multiscale rasterization of a 2D polyline. "
            "Provide either a built-in --shape or a --curve JSON file."
        ),
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
    parser.set_defaults(
        color_by_level=True,
        show_interior=True,
        show_boundary=True,
        legend=True,
    )
    return parser


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _load_curve(args: argparse.Namespace) -> Curve:
    """Loads the curve selected by the parsed arguments."""
    if args.shape is not None:
        return BUILTIN_SHAPES[args.shape]()
    if args.curve is not None:
        path = Path(args.curve).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"curve file not found: {path}")
        return Curve.from_json(path.read_text(encoding="utf-8"))
    raise ValueError("no curve source selected")


def _resolve_bbox(curve: Curve, args: argparse.Namespace):
    """Returns the bounding box to rasterize, honouring ``--bbox``."""
    if args.bbox is not None:
        return tuple(float(v) for v in args.bbox)
    return curve.bounding_box(padding=args.padding)


def _plot_kwargs(args: argparse.Namespace) -> dict:
    """Collects the plotting options shared by single and gallery renders."""
    return {
        "color_by_level": args.color_by_level,
        "show_interior": args.show_interior,
        "show_boundary": args.show_boundary,
        "legend": args.legend,
        "title": args.title,
    }


def _render_one(curve: Curve, args: argparse.Namespace, output: Path) -> Path:
    """Renders a single curve to ``output`` and returns the written path."""
    from .visualization import save_rasterization

    bbox = _resolve_bbox(curve, args)
    return save_rasterization(
        curve,
        bbox,
        args.max_level,
        path=output,
        format=args.format,
        dpi=args.dpi,
        transparent=args.transparent,
        **_plot_kwargs(args),
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    """Runs the CLI.

    Parameters
    ----------
    argv : list[str], optional
        Argument list to parse. Defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        A process exit code: ``0`` on success, ``1`` on a handled error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.gallery:
            out_dir = Path(args.output_dir).expanduser()
            out_dir.mkdir(parents=True, exist_ok=True)
            written = []
            for curve in gallery_curves():
                suffix = args.format or "png"
                target = out_dir / f"{curve.name}.{suffix}"
                written.append(_render_one(curve, args, target))
            for path in written:
                print(f"wrote {path}")
            return 0

        curve = _load_curve(args)
        if args.output is not None:
            output = Path(args.output).expanduser()
        else:
            suffix = args.format or "png"
            output = Path(f"{curve.name or 'rasterization'}.{suffix}")
        written = _render_one(curve, args, output)
        print(f"wrote {written}")
        return 0
    except (FileNotFoundError, ValueError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
