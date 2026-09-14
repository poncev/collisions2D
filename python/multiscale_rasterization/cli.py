"""Standalone command-line tool for visualizing multiscale rasterizations.

This module provides a small, dependency-light CLI so that a user can render a
rasterization without writing any Python. It is exposed as
``python -m multiscale_rasterization`` (see :mod:`multiscale_rasterization.__main__`)
and can also be invoked programmatically through :func:`main`.

The tool accepts a curve either as a built-in shape (``square``, ``triangle``,
``hexagon``, ``circle``, ``l-shape``, ``diagonal``) or as a JSON file in the
format produced by :meth:`multiscale_rasterization.Curve.to_json`.

The argument surface, the built-in shapes and the rendering helpers are shared
with the standalone ``tools/visualize_rasterization.py`` script through
:mod:`multiscale_rasterization._cli_common`; this module contributes only its
program name, its description and the :func:`main` entry point.

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

import sys
from pathlib import Path

from ._cli_common import (
    BUILTIN_SHAPES,
    build_parser as _build_shared_parser,
    gallery_curves,
    load_curve as _load_curve,
    plot_kwargs as _plot_kwargs,
    render_one as _render_one,
    resolve_bbox as _resolve_bbox,
)

__all__ = ["main", "build_parser", "BUILTIN_SHAPES", "gallery_curves"]


def build_parser():
    """Builds the :class:`argparse.ArgumentParser` for the package CLI."""
    return _build_shared_parser(
        prog="multiscale_rasterization",
        description=(
            "Visualize the multiscale rasterization of a 2D polyline. "
            "Provide either a built-in --shape or a --curve JSON file."
        ),
    )


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
