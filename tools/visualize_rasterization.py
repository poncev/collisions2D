#!/usr/bin/env python3
"""Standalone visualization tool for multiscale rasterization results.

This script is a self-contained entry point for rendering the output of the
C++ multiscale rasterizer. It is intentionally independent of the package CLI
(``python -m multiscale_rasterization``) so that it can be copied into a
scratch directory, run from a checkout without installing the package, or
wired into a Makefile / CI job.

It supports three sources of geometry:

* a built-in shape (``square``, ``triangle``, ``hexagon``, ``circle``,
  ``l-shape``, ``diagonal``);
* a JSON file in the format produced by ``Curve.to_json``;
* a Python module path exposing a ``CURVE`` or ``CURVES`` object.

Typical usage
-------------
Render a built-in square to a PNG::

    python tools/visualize_rasterization.py --shape square --max-level 4 \\
        --output square.png

Render a curve stored as JSON, colouring cells by kind instead of level::

    python tools/visualize_rasterization.py --curve my_curve.json \\
        --max-level 5 --no-color-by-level --output my_curve.svg

Render every built-in shape into a directory as a gallery::

    python tools/visualize_rasterization.py --gallery --output-dir examples/

The script exits with status ``0`` on success and ``1`` on a handled error
(missing file, bad arguments, missing matplotlib), printing a short message to
stderr.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running the script directly from a checkout without installing the
# package: prepend the repository's ``python/`` directory to ``sys.path``.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYTHON_DIR = _REPO_ROOT / "python"
if _PYTHON_DIR.is_dir() and str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from multiscale_rasterization import (  # noqa: E402
    Curve,
    plot_gallery,
    save_rasterization,
)
from multiscale_rasterization.cli import BUILTIN_SHAPES, gallery_curves  # noqa: E402


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    """Builds the argument parser for the standalone tool."""
    parser = argparse.ArgumentParser(
        prog="visualize_rasterization",
        description=(
            "Render the multiscale rasterization of a 2D polyline. Provide a "
            "built-in --shape, a --curve JSON file, or --gallery to render "
            "every built-in shape."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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
        help="finest quadtree subdivision depth",
    )
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("MIN_X", "MIN_Y", "MAX_X", "MAX_Y"),
        default=None,
        help="bounding box; defaults to the curve's box padded by --padding",
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=0.0,
        help="padding added to the auto-computed bounding box",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output image path (default: <shape>.<format>)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="directory used by --gallery",
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
        help="output resolution for raster formats",
    )
    parser.add_argument(
        "--transparent",
        action="store_true",
        help="save with a transparent background",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="override the plot title",
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
        "--gallery-cols",
        type=int,
        default=3,
        help="number of columns in the --gallery grid",
    )
    parser.add_argument(
        "--gallery-figure",
        action="store_true",
        help=(
            "with --gallery, also write a single combined multi-panel figure "
            "named gallery.<format>"
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


def _render_gallery(args: argparse.Namespace) -> list[Path]:
    """Renders every built-in shape into ``--output-dir``.

    Each shape is written as its own image; when ``--gallery-figure`` is set a
    single combined multi-panel figure is produced as well.
    """
    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = args.format or "png"
    curves = gallery_curves()
    written = []
    for curve in curves:
        target = out_dir / f"{curve.name}.{suffix}"
        written.append(_render_one(curve, args, target))

    if args.gallery_figure:
        written.append(_render_gallery_figure(curves, out_dir, suffix, args))
    return written


def _render_gallery_figure(
    curves, out_dir: Path, suffix: str, args: argparse.Namespace
) -> Path:
    """Writes a single combined multi-panel figure of ``curves``."""
    import matplotlib.pyplot as plt

    # Compute union bounding box so all panels use the same scale
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
        fig.savefig(target, format=args.format or suffix, dpi=args.dpi,
                    bbox_inches="tight")
    finally:
        plt.close(fig)
    return target


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    """Runs the standalone visualization tool.

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
            written = _render_gallery(args)
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