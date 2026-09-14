#!/usr/bin/env python3
"""Comprehensive demonstration of the multiscale-rasterization visualization API.

This script is a *showcase and smoke test* for
:mod:`multiscale_rasterization.visualization`. Unlike
``tools/visualize_rasterization.py`` (a thin, argument-driven renderer), this
tool walks through the capabilities of the existing visualization module and
verifies that they work end to end against the current C++ implementation.

It demonstrates, in one place:

* the different :class:`~multiscale_rasterization.Curve` constructors
  (:meth:`Curve.rectangle`, a hand-built closed polyline,
  :meth:`Curve.regular_polygon`, ...) for square / triangle / L-shape /
  hexagon geometry;
* :func:`~multiscale_rasterization.save_rasterization` for writing images to
  disk (PNG, SVG, PDF, ...);
* :func:`~multiscale_rasterization.plot_rasterization` for embedding a result
  in a caller-supplied ``Axes``;
* :func:`~multiscale_rasterization.plot_gallery` for multi-panel grids;
* interactive display via ``matplotlib.pyplot.show()``;
* the plotting options offered by the module (colouring by quadtree level vs.
  by cell kind, boundary-only / interior-only views, ...);
* the Jordan-curve examples from ``tests/test_jordan_curves.py``, reused here
  so the demo and the numerical test suite stay in sync.

Typical usage
-------------
Render every built-in demo curve and a gallery into ``tools/out/``::

    python tools/visualize.py

Render the Jordan-curve examples from the test suite instead::

    python tools/visualize.py --source jordan --output-dir tools/out/jordan

Write a comparison of the plotting options for one shape::

    python tools/visualize.py --options --max-level 4

Open the gallery in an interactive window (requires a GUI backend)::

    python tools/visualize.py --interactive

Validate that the visualization stack works without writing anything
(returns a non-zero exit code on failure) -- handy for CI::

    python tools/visualize.py --check

The script exits with status ``0`` on success and ``1`` on a handled error
(missing matplotlib, missing test file, bad arguments).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Path setup: allow running straight from a checkout without installing the
# package. matplotlib is imported lazily by the visualization module, so this
# only needs to make ``multiscale_rasterization`` importable.
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYTHON_DIR = _REPO_ROOT / "python"
for _candidate in (_PYTHON_DIR, _REPO_ROOT):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from multiscale_rasterization import (  # noqa: E402
    Curve,
    plot_gallery,
    plot_rasterization,
    save_rasterization,
)

__all__ = [
    "square_curve",
    "triangle_curve",
    "l_shape_curve",
    "hexagon_curve",
    "DEMO_CURVES",
    "DEFAULT_BBOX",
    "load_jordan_curves",
    "render_curves",
    "render_gallery",
    "render_options_comparison",
    "show_interactive",
    "check_visualization",
    "build_parser",
    "main",
]

# --------------------------------------------------------------------------- #
# Example geometry
# --------------------------------------------------------------------------- #

#: Bounding box shared by the built-in demo curves. All of them live inside
#: the unit square [0, 10] x [0, 10], which keeps panels directly comparable.
DEFAULT_BBOX = (0.0, 0.0, 10.0, 10.0)


def square_curve() -> Curve:
    """A closed square on ``[2, 8] x [2, 8]`` built with the rectangle helper."""
    return Curve.rectangle(2.0, 2.0, 8.0, 8.0, name="square")


def triangle_curve() -> Curve:
    """A closed triangle built from an explicit vertex list."""
    return Curve(
        [(1.0, 1.0), (9.0, 1.0), (5.0, 8.0)],
        closed=True,
        name="triangle",
    )


def l_shape_curve() -> Curve:
    """A closed, non-convex L-shape built from an explicit vertex list."""
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


def hexagon_curve() -> Curve:
    """A regular hexagon built with the ``regular_polygon`` helper."""
    return Curve.regular_polygon((5.0, 5.0), 3.0, 6, name="hexagon")


#: Ordered mapping of demo shape name to a zero-argument :class:`Curve` factory.
#: The order defines the panel order in galleries.
DEMO_CURVES = {
    "square": square_curve,
    "triangle": triangle_curve,
    "l-shape": l_shape_curve,
    "hexagon": hexagon_curve,
}


def demo_curves(names=None) -> list[Curve]:
    """Returns the built-in demo curves, optionally filtered by ``names``."""
    if not names:
        return [factory() for factory in DEMO_CURVES.values()]
    unknown = [n for n in names if n not in DEMO_CURVES]
    if unknown:
        raise ValueError(
            f"unknown demo curve(s): {', '.join(unknown)}; "
            f"choose from {', '.join(DEMO_CURVES)}"
        )
    return [DEMO_CURVES[n]() for n in names]


# --------------------------------------------------------------------------- #
# Reuse the Jordan-curve examples from the test suite
# --------------------------------------------------------------------------- #

def load_jordan_curves():
    """Loads the example curves defined in ``tests/test_jordan_curves.py``.

    The test module is imported by file path (``tests/`` is not an importable
    package), so this reuses the exact same geometry that the numerical test
    suite validates. That keeps the visualization demo and the tests in sync:
    if a shape changes in the test suite, the demo picks it up automatically.

    Returns
    -------
    (list[tuple[str, Curve]], tuple[float, float, float, float])
        The ``(name, curve)`` pairs and the shared bounding box.

    Raises
    ------
    FileNotFoundError
        If the test module cannot be found in the checkout.
    """
    path = _REPO_ROOT / "tests" / "test_jordan_curves.py"
    if not path.is_file():
        raise FileNotFoundError(f"Jordan-curve test module not found: {path}")

    spec = importlib.util.spec_from_file_location("_mr_jordan_examples", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load Jordan-curve examples from {path}")

    module = importlib.util.module_from_spec(spec)
    # Register before execution so dataclasses/typing in the module resolve.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    curves = module._example_curves()
    bbox = tuple(getattr(module, "BBOX", DEFAULT_BBOX))
    return curves, bbox


# --------------------------------------------------------------------------- #
# matplotlib backend handling
# --------------------------------------------------------------------------- #

def configure_matplotlib(interactive: bool):
    """Imports matplotlib and selects an appropriate backend.

    For file output the headless ``Agg`` backend is forced so the script is
    safe to run over SSH or in CI. For ``--interactive`` the user's default
    backend is kept; if that backend cannot display windows, a warning is
    printed and the caller is expected to fall back to file output.
    """
    try:
        import matplotlib

        if not interactive:
            matplotlib.use("Agg", force=True)
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "the visualization demo requires matplotlib; install it with "
            "`mamba install matplotlib` (or `pip install matplotlib`)"
        ) from exc
    return matplotlib


def backend_is_interactive(matplotlib) -> bool:
    """Heuristically reports whether the current backend can open windows."""
    backend = str(matplotlib.get_backend()).lower()
    headless = {"agg", "pdf", "ps", "svg", "cairo", "template", "pgf"}
    if backend in headless:
        return False
    # Non-interactive only when explicitly headless; GUI backends need a
    # display on Linux.
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return False
    return True


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #

def render_curves(curves, out_dir, *, bbox=None, max_level=3, fmt="png",
                  dpi=200, **plot_kwargs):
    """Writes one image per curve into ``out_dir`` and returns the paths.

    Accepts either :class:`Curve` objects or ``(name, Curve)`` pairs.
    """
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    written = []
    for item in curves:
        if isinstance(item, Curve):
            curve = item
        else:
            _, curve = item
        target = out / f"{curve.name or 'curve'}.{fmt}"
        written.append(
            save_rasterization(
                curve,
                bbox if bbox is not None else curve.bounding_box(),
                max_level,
                path=target,
                format=fmt,
                dpi=dpi,
                **plot_kwargs,
            )
        )
    return written


def render_gallery(curves, out_dir, *, bbox=None, max_level=3, fmt="png",
                   dpi=200, ncols=3, suptitle=None, **plot_kwargs):
    """Writes a single combined multi-panel figure and returns its path.

    ``curves`` may contain :class:`Curve` objects or ``(name, Curve)`` pairs;
    a shared bounding box and depth are used for every panel.
    """
    import matplotlib.pyplot as plt

    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    # plot_gallery takes a flat sequence of curves; extract them from pairs.
    plain = [item if isinstance(item, Curve) else item[1] for item in curves]
    if not plain:
        raise ValueError("render_gallery needs at least one curve")

    # When no shared box is supplied, use one that covers every curve so all
    # panels use the same scale.
    if bbox is None:
        xs_min = min(c.bounding_box()[0] for c in plain)
        ys_min = min(c.bounding_box()[1] for c in plain)
        xs_max = max(c.bounding_box()[2] for c in plain)
        ys_max = max(c.bounding_box()[3] for c in plain)
        bbox = (xs_min, ys_min, xs_max, ys_max)

    fig, _ = plot_gallery(
        plain,
        bbox,
        max_level,
        ncols=ncols,
        suptitle=suptitle or "Multiscale rasterization gallery",
        **plot_kwargs,
    )
    target = out / f"gallery.{fmt}"
    try:
        fig.savefig(target, format=fmt, dpi=dpi, bbox_inches="tight")
    finally:
        plt.close(fig)
    return target


def render_options_comparison(curve, out_dir, *, bbox=None, max_level=3,
                              fmt="png", dpi=200):
    """Renders a 2x2 panel comparing the visualization options for ``curve``.

    Panels show the effect of ``color_by_level`` and the ``show_boundary`` /
    ``show_interior`` toggles, illustrating when each is useful for
    documentation or debugging.
    """
    import matplotlib.pyplot as plt

    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    if bbox is None:
        bbox = curve.bounding_box()

    variants = [
        ("By quadtree level (default)", {"color_by_level": True}),
        ("By cell kind", {"color_by_level": False}),
        ("Boundary only", {"show_interior": False}),
        ("Interior only", {"show_boundary": False}),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(9.0, 8.6), dpi=110)
    for ax, (title, kw) in zip(axes.ravel(), variants):
        plot_rasterization(
            curve,
            bbox,
            max_level,
            ax=ax,
            title=title,
            legend=False,
            **kw,
        )
    fig.suptitle(
        f"{curve.name or 'curve'} — visualization options",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()

    target = out / f"{curve.name or 'curve'}_options.{fmt}"
    try:
        fig.savefig(target, format=fmt, dpi=dpi, bbox_inches="tight")
    finally:
        plt.close(fig)
    return target


def show_interactive(curves, *, bbox=None, max_level=3, ncols=3):
    """Opens one interactive gallery window for ``curves``.

    Returns the matplotlib figure so callers can keep a reference (otherwise
    the figure may be garbage-collected before the event loop runs).
    """
    import matplotlib.pyplot as plt

    plain = [item if isinstance(item, Curve) else item[1] for item in curves]
    if bbox is None and plain:
        bbox = (
            min(c.bounding_box()[0] for c in plain),
            min(c.bounding_box()[1] for c in plain),
            max(c.bounding_box()[2] for c in plain),
            max(c.bounding_box()[3] for c in plain),
        )

    fig, _ = plot_gallery(
        plain,
        bbox,
        max_level,
        ncols=ncols,
        suptitle="Multiscale rasterization — interactive gallery",
    )
    plt.show()
    return fig


def check_visualization(curve=None, *, bbox=None, max_level=2):
    """Exercises the visualization API headlessly and reports what works.

    Runs the rasterizer, draws onto an explicit ``Axes``, builds a gallery and
    renders to an in-memory buffer. Nothing is written to disk, which makes
    this suitable as a CI smoke check. Returns a list of ``(check, ok)`` pairs.
    """
    import io

    import matplotlib.pyplot as plt

    if curve is None:
        curve = square_curve()
    if bbox is None:
        bbox = curve.bounding_box()

    results = []

    # 1. Core rasterization through the visualization resolver.
    ax = plot_rasterization(curve, bbox, max_level)
    results.append(("plot_rasterization returns an Axes", hasattr(ax, "collections")))
    results.append(("cells were drawn", len(ax.collections) >= 1))
    plt.close(ax.figure)

    # 2. Colour-by-kind variant.
    ax = plot_rasterization(curve, bbox, max_level, color_by_level=False,
                            show_interior=False)
    results.append(("option flags accepted", len(ax.collections) >= 1))
    plt.close(ax.figure)

    # 3. Gallery grid.
    fig, axes = plot_gallery([curve], bbox, max_level, ncols=1)
    results.append(("plot_gallery builds a grid", axes.shape == (1, 1)))
    plt.close(fig)

    # 4. end-to-end file rendering into a memory buffer.
    fig, ax = plt.subplots()
    plot_rasterization(curve, bbox, max_level, ax=ax, legend=False)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    results.append(("figure encodes to PNG", buffer.getbuffer().nbytes > 0))

    return results


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    """Builds the argument parser for the demo tool."""
    parser = argparse.ArgumentParser(
        prog="visualize",
        description=(
            "Demonstrate the multiscale-rasterization visualization API: "
            "render built-in or Jordan-curve examples, compare plotting "
            "options, or open an interactive window."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=("demo", "jordan", "both"),
        default="demo",
        help="which curve set to visualize",
    )
    parser.add_argument(
        "--curves",
        nargs="+",
        metavar="NAME",
        default=None,
        help=(
            "subset of demo curves to use (square, triangle, l-shape, "
            "hexagon); default: all"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tools/out"),
        help="directory the rendered images are written to",
    )
    parser.add_argument(
        "--max-level",
        type=int,
        default=3,
        help="finest quadtree subdivision depth",
    )
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("MIN_X", "MIN_Y", "MAX_X", "MAX_Y"),
        default=None,
        help="bounding box; default: the curve's own box",
    )
    parser.add_argument(
        "--format",
        default="png",
        help="output image format (png, svg, pdf, ...)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="output resolution for raster formats",
    )
    parser.add_argument(
        "--ncols",
        type=int,
        default=3,
        help="number of columns in the gallery grid",
    )
    parser.add_argument(
        "--no-gallery",
        dest="gallery",
        action="store_false",
        help="skip the combined multi-panel gallery figure",
    )
    parser.add_argument(
        "--options",
        action="store_true",
        help="also write a 2x2 comparison of the plotting options",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="open the gallery in an interactive window",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="run a headless smoke check of the visualization API and exit",
    )
    parser.add_argument(
        "--list",
        dest="list_curves",
        action="store_true",
        help="list the available curve sources and exit",
    )
    parser.set_defaults(gallery=True)
    return parser


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def _select_curves(args):
    """Collects the ``(name, Curve)`` pairs and bounding box to visualize."""
    selected = []

    if args.source in ("demo", "both"):
        selected.extend((c.name, c) for c in demo_curves(args.curves))

    if args.source in ("jordan", "both"):
        jordan, jordan_bbox = load_jordan_curves()
        selected.extend((name, curve) for name, curve in jordan)
        default_bbox = jordan_bbox
    else:
        default_bbox = DEFAULT_BBOX

    bbox = tuple(args.bbox) if args.bbox is not None else default_bbox
    return selected, bbox


def main(argv: list[str] | None = None) -> int:
    """Runs the visualization demo.

    Returns
    -------
    int
        Process exit code: ``0`` on success, ``1`` on a handled error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_curves:
        print("Built-in demo curves:")
        for name in DEMO_CURVES:
            print(f"  - {name}")
        print("Jordan curves (from tests/test_jordan_curves.py):")
        try:
            for name, _ in load_jordan_curves()[0]:
                print(f"  - {name}")
        except (FileNotFoundError, ImportError) as exc:
            print(f"  (unavailable: {exc})")
        return 0

    try:
        # A headless check never needs file output or a display.
        if args.check:
            configure_matplotlib(interactive=False)
            curve = demo_curves(args.curves)[0]
            bbox = tuple(args.bbox) if args.bbox is not None else DEFAULT_BBOX
            results = check_visualization(curve, bbox=bbox,
                                          max_level=args.max_level)
            print("Visualization smoke check:")
            for label, ok in results:
                print(f"  [{'ok' if ok else 'FAIL'}] {label}")
            return 0 if all(ok for _, ok in results) else 1

        curves, bbox = _select_curves(args)
        if not curves:
            print("error: no curves selected", file=sys.stderr)
            return 1

        if args.interactive:
            configure_matplotlib(interactive=True)
            import matplotlib

            if not backend_is_interactive(matplotlib):
                print(
                    f"warning: matplotlib backend {matplotlib.get_backend()!r} "
                    "cannot display windows; use file output instead",
                    file=sys.stderr,
                )
            else:
                print("opening interactive gallery (close the window to exit)...")
                show_interactive(
                    curves,
                    bbox=bbox,
                    max_level=args.max_level,
                    ncols=args.ncols,
                )
                return 0

        # File output (default, and the fallback for a non-GUI backend).
        configure_matplotlib(interactive=False)

        written = render_curves(
            curves,
            args.output_dir,
            bbox=bbox,
            max_level=args.max_level,
            fmt=args.format,
            dpi=args.dpi,
        )
        for path in written:
            print(f"wrote {path}")

        if args.gallery:
            written = render_gallery(
                curves,
                args.output_dir,
                bbox=bbox,
                max_level=args.max_level,
                fmt=args.format,
                dpi=args.dpi,
                ncols=args.ncols,
                suptitle="Multiscale rasterization — gallery",
            )
            print(f"wrote {written}")

        if args.options:
            curve = curves[0] if isinstance(curves[0], Curve) else curves[0][1]
            written = render_options_comparison(
                curve,
                args.output_dir,
                bbox=bbox,
                max_level=args.max_level,
                fmt=args.format,
                dpi=args.dpi,
            )
            print(f"wrote {written}")

        return 0

    except (FileNotFoundError, ValueError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
