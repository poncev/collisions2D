#!/usr/bin/env python3
"""
Test suite for Jordan curves (closed, non-self-intersecting curves).
This validates the algorithm works well with basic geometric shapes.

Besides checking the rasterizer, this module doubles as a worked example of
the visualization API. Running it with ``--visualize`` renders each shape to
an image (see :func:`visualize_examples`); running it without arguments keeps
the original, dependency-free test behaviour.

Examples
--------
Run the numerical tests::

    python tests/test_jordan_curves.py

Additionally render every shape to ``tests/out/`` as PNGs::

    python tests/test_jordan_curves.py --visualize

Render with a different depth and format::

    python tests/test_jordan_curves.py --visualize --max-level 5 --format svg
"""

import argparse
import math
import sys

from multiscale_rasterization import Curve, multiscale_rasterization

# Bounding box shared by every example shape. The shapes live in the unit
# square [0, 10] x [0, 10] (see ``_example_curves``), so a single box keeps the
# comparisons between panels fair.
BBOX = (0.0, 0.0, 10.0, 10.0)


def _square_curve():
    """A closed square, returned as a :class:`Curve` for the visualization API."""
    return Curve.rectangle(2.0, 2.0, 8.0, 8.0, name="square")


def _triangle_curve():
    """A closed triangle."""
    return Curve([(1.0, 1.0), (9.0, 1.0), (5.0, 8.0)], closed=True, name="triangle")


def _hexagon_curve():
    """A regular hexagon, radius 3, centred at (5, 5)."""
    return Curve.regular_polygon((5.0, 5.0), 3.0, 6, name="hexagon")


def _l_shape_curve():
    """An L-shaped closed curve."""
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


def _circle_curve():
    """A circle approximated by a 16-gon, radius 2.5, centred at (5, 5)."""
    return Curve.circle((5.0, 5.0), 2.5, n=16, name="circle")


def _example_curves():
    """Returns ``(name, Curve)`` pairs for every Jordan-curve example.

    The order matches the numerical tests below so that the gallery is easy to
    relate back to the assertions.
    """
    return [
        ("Square", _square_curve()),
        ("Triangle", _triangle_curve()),
        ("Hexagon", _hexagon_curve()),
        ("L-shape", _l_shape_curve()),
        ("Circle approximation", _circle_curve()),
    ]


def visualize_examples(
    output_dir="tests/out",
    *,
    max_level=3,
    fmt="png",
    gallery=False,
):
    """Renders every example curve to ``output_dir`` and returns the paths.

    This is the "example usage" companion to the numerical tests: it shows how
    a :class:`Curve`, a bounding box and a depth are all that is needed to go
    from geometry to a publication-ready figure.

    Parameters
    ----------
    output_dir : str or pathlib.Path
        Directory the images are written to. Created if needed.
    max_level : int
        Finest quadtree subdivision depth used for every shape.
    fmt : str
        Image format (``"png"``, ``"svg"``, ``"pdf"``, ...).
    gallery : bool
        When ``True``, additionally write a single combined multi-panel figure
        named ``jordan_gallery.<fmt>`` into ``output_dir``.

    Returns
    -------
    list[pathlib.Path]
        The paths that were written.
    """
    from pathlib import Path

    from multiscale_rasterization import plot_gallery, save_rasterization

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    written = []
    for name, curve in _example_curves():
        target = out / f"{curve.name}.{fmt}"
        written.append(
            save_rasterization(
                curve,
                BBOX,
                max_level,
                path=target,
                format=fmt,
                title=f"{name} — multiscale rasterization",
            )
        )

    if gallery:
        import matplotlib.pyplot as plt

        fig, _ = plot_gallery(
            [curve for _, curve in _example_curves()],
            BBOX,
            max_level,
            ncols=3,
            suptitle="Jordan curves — multiscale rasterization",
        )
        target = out / f"jordan_gallery.{fmt}"
        try:
            fig.savefig(target, format=fmt, dpi=200, bbox_inches="tight")
        finally:
            plt.close(fig)
        written.append(target)

    return written


def test_square():
    """Test a simple closed square."""
    polyline = [(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0), (2.0, 2.0)]
    bbox = BBOX
    max_level = 2
    
    result = multiscale_rasterization(polyline, bbox, max_level)
    
    print(f"Square test:")
    print(f"  Size: 6x6 square at max_level={max_level}")
    print(f"  Cells found: {len(result.corners)}")
    print(f"  Levels: {sorted(set(result.levels))}")
    print(f"  Expected: Square interior + boundary should give reasonable cell count")
    return len(result.corners) > 10  # Should have significant interior

def test_triangle():
    """Test a triangular Jordan curve."""
    polyline = [(1.0, 1.0), (9.0, 1.0), (5.0, 8.0), (1.0, 1.0)]
    bbox = BBOX
    max_level = 3
    
    result = multiscale_rasterization(polyline, bbox, max_level)
    
    print(f"\nTriangle test:")
    print(f"  Triangle from (1,1)-(9,1)-(5,8) at max_level={max_level}")
    print(f"  Cells found: {len(result.corners)}")
    print(f"  Levels: {sorted(set(result.levels))}")
    return len(result.corners) > 5  # Triangle should have some interior

def test_hexagon():
    """Test a regular hexagon."""
    # Create regular hexagon centered at (5,5) with radius 3
    center_x, center_y = 5.0, 5.0
    radius = 3.0
    polyline = []
    for i in range(6):
        angle = i * math.pi / 3  # 60 degrees each
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        polyline.append((x, y))
    polyline.append(polyline[0])  # Close the curve
    
    bbox = BBOX
    max_level = 3
    
    result = multiscale_rasterization(polyline, bbox, max_level)
    
    print(f"\nHexagon test:")
    print(f"  Regular hexagon, radius=3, center=(5,5) at max_level={max_level}")
    print(f"  Cells found: {len(result.corners)}")
    print(f"  Levels: {sorted(set(result.levels))}")
    return len(result.corners) > 8  # Hexagon should have good interior

def test_l_shape():
    """Test an L-shaped Jordan curve."""
    polyline = [
        (1.0, 1.0), (6.0, 1.0), (6.0, 4.0), 
        (4.0, 4.0), (4.0, 7.0), (1.0, 7.0), 
        (1.0, 1.0)
    ]
    bbox = (0.0, 0.0, 8.0, 8.0)
    max_level = 3
    
    result = multiscale_rasterization(polyline, bbox, max_level)
    
    print(f"\nL-shape test:")
    print(f"  L-shaped curve at max_level={max_level}")
    print(f"  Cells found: {len(result.corners)}")
    print(f"  Levels: {sorted(set(result.levels))}")
    return len(result.corners) > 10  # L-shape should have substantial interior

def test_circle_approximation():
    """Test a circle approximated by many line segments."""
    center_x, center_y = 5.0, 5.0
    radius = 2.5
    num_points = 16  # 16-sided polygon approximating circle
    
    polyline = []
    for i in range(num_points):
        angle = i * 2 * math.pi / num_points
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        polyline.append((x, y))
    polyline.append(polyline[0])  # Close the curve
    
    bbox = BBOX
    max_level = 3
    
    result = multiscale_rasterization(polyline, bbox, max_level)
    
    print(f"\nCircle approximation test:")
    print(f"  16-gon approximating circle, radius=2.5 at max_level={max_level}")
    print(f"  Cells found: {len(result.corners)}")
    print(f"  Levels: {sorted(set(result.levels))}")
    return len(result.corners) > 6  # Circle should have interior

def run_all_tests():
    """Run all Jordan curve tests."""
    print("=== Testing Jordan Curves (Closed, Non-Self-Intersecting) ===\n")
    
    tests = [
        ("Square", test_square),
        ("Triangle", test_triangle), 
        ("Hexagon", test_hexagon),
        ("L-shape", test_l_shape),
        ("Circle approximation", test_circle_approximation)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status}")
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results.append((name, False))
    
    print(f"\n=== Results Summary ===")
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for name, passed in results:
        status = "✓" if passed else "✗"
        print(f"{status} {name}")
    
    print(f"\nPassed: {passed_count}/{total_count}")
    
    if passed_count == total_count:
        print("🎉 All tests passed! The algorithm works well for basic Jordan curves.")
    elif passed_count >= total_count * 0.8:
        print("👍 Most tests passed. The algorithm shows good promise for Jordan curves.")
    else:
        print("⚠️  Several tests failed. The algorithm may need more work.")


def build_parser():
    """Builds the CLI parser for this test/example script."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the Jordan-curve tests and optionally render the example "
            "shapes with the visualization API."
        )
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="render every example curve to --output-dir after the tests",
    )
    parser.add_argument(
        "--output-dir",
        default="tests/out",
        help="directory the visualization images are written to",
    )
    parser.add_argument(
        "--max-level",
        type=int,
        default=3,
        help="finest quadtree depth used for the rendered examples",
    )
    parser.add_argument(
        "--format",
        default="png",
        help="image format for the rendered examples (png, svg, pdf, ...)",
    )
    parser.add_argument(
        "--gallery",
        action="store_true",
        help="also write a single combined multi-panel figure",
    )
    return parser


def main(argv=None):
    """Runs the tests, and optionally the visualization examples."""
    args = build_parser().parse_args(argv)

    run_all_tests()

    if args.visualize:
        print("\n=== Visualizing examples ===")
        try:
            written = visualize_examples(
                output_dir=args.output_dir,
                max_level=args.max_level,
                fmt=args.format,
                gallery=args.gallery,
            )
        except ImportError as exc:
            print(f"could not render examples: {exc}", file=sys.stderr)
            return 1
        for path in written:
            print(f"wrote {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())