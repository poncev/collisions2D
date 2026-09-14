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

from multiscale_rasterization._cli_common import (  # noqa: E402
    build_parser as _build_shared_parser,
    load_curve as _load_curve,
    render_gallery as _render_gallery,
    render_one as _render_one,
)


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    """Builds the argument parser for the standalone tool.

    Delegates to the shared builder, adding the gallery-grid options
    (``--gallery-cols``, ``--gallery-figure``) that are specific to this tool.
    """
    return _build_shared_parser(
        prog="visualize_rasterization",
        description=(
            "Render the multiscale rasterization of a 2D polyline. Provide a "
            "built-in --shape, a --curve JSON file, or --gallery to render "
            "every built-in shape."
        ),
        defaults_in_help=True,
        gallery_options=True,
    )


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
            written = _render_gallery(args, figure=args.gallery_figure)
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