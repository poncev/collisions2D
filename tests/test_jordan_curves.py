#!/usr/bin/env python3
"""Tests for Jordan curves (closed, non-self-intersecting curves).

This validates that the rasterizer works well with basic geometric shapes:
a square, a triangle, a hexagon, an L-shape and a circle approximation.

The module also doubles as a worked example of the minimal visualization API:
:func:`square_figure` shows how a :class:`Curve`, a bounding box and a depth are
all that is needed to go from geometry to a matplotlib axis, using the
:func:`~multiscale_rasterization.render_rasterization` entry point.

The tests are plain functions returning a boolean and can be run directly::

    python tests/test_jordan_curves.py
"""

import math

from multiscale_rasterization import Curve, multiscale_rasterization

# Bounding box shared by every example shape. The shapes live in the unit
# square [0, 10] x [0, 10] (see ``_example_curves``), so a single box keeps the
# comparisons between panels fair.
BBOX = (0.0, 0.0, 10.0, 10.0)


def _square_curve():
    """A closed square, returned as a :class:`Curve` for the visualization API."""
    return Curve.rectangle(2.0, 2.0, 8.0, 8.0, name="square")


def square_figure(max_level=3):
    """Builds a matplotlib figure for the example square.

    This is the minimal example of the public visualization API: rasterize a
    :class:`Curve` and render the result onto an axis. Matplotlib is imported
    lazily so that importing this test module stays dependency-free.

    Returns
    -------
    (matplotlib.figure.Figure, matplotlib.axes.Axes)
    """
    import matplotlib.pyplot as plt

    from multiscale_rasterization import render_rasterization

    curve = _square_curve()
    result = multiscale_rasterization(curve, BBOX, max_level)
    fig, ax = plt.subplots(figsize=(6.0, 6.0), dpi=110)
    render_rasterization(result, ax)
    return fig, ax


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


# Expected rasterization of the off-grid square (2.7, 2.7)-(7.7, 7.7) at
# max_level=3, as ``(corner, size, kind)`` triples. The square's edges fall
# strictly inside level-3 cells (size 1.25), so the boundary is refined to
# level 3. The interior is covered by five level-3 cells plus a single level-2
# cell (size 2.5) in the top-right corner: that coarser cell is what makes the
# result genuinely multiscale rather than a uniform grid.
_OFF_GRID_SQUARE_EXPECTED = [
    # Boundary cells (level 3).
    ((2.5, 2.5), 1.25, "boundary"),
    ((2.5, 3.75), 1.25, "boundary"),
    ((2.5, 5.0), 1.25, "boundary"),
    ((2.5, 6.25), 1.25, "boundary"),
    ((2.5, 7.5), 1.25, "boundary"),
    ((7.5, 2.5), 1.25, "boundary"),
    ((7.5, 3.75), 1.25, "boundary"),
    ((7.5, 5.0), 1.25, "boundary"),
    ((7.5, 6.25), 1.25, "boundary"),
    ((7.5, 7.5), 1.25, "boundary"),
    ((3.75, 2.5), 1.25, "boundary"),
    ((5.0, 2.5), 1.25, "boundary"),
    ((6.25, 2.5), 1.25, "boundary"),
    ((3.75, 7.5), 1.25, "boundary"),
    ((5.0, 7.5), 1.25, "boundary"),
    ((6.25, 7.5), 1.25, "boundary"),
    # Interior cells (level 3, except the level-2 cell in the top-right).
    ((3.75, 3.75), 1.25, "interior"),
    ((3.75, 5.0), 1.25, "interior"),
    ((3.75, 6.25), 1.25, "interior"),
    ((5.0, 3.75), 1.25, "interior"),
    ((6.25, 3.75), 1.25, "interior"),
    ((5.0, 5.0), 2.5, "interior"),
]


def test_square_off_grid():
    """Test a square whose edges do not align with the quadtree grid.

    The square (2.7, 2.7)-(7.7, 7.7) is deliberately offset from the grid so
    that the boundary is refined to level 3 while the interior keeps a coarser
    level-2 cell in its top-right corner. Unlike the other Jordan-curve tests,
    this one pins the exact multiscale decomposition (see
    ``_OFF_GRID_SQUARE_EXPECTED``) instead of only checking a cell count.
    """
    polyline = [(2.7, 2.7), (7.7, 2.7), (7.7, 7.7), (2.7, 7.7), (2.7, 2.7)]
    bbox = BBOX
    max_level = 3

    result = multiscale_rasterization(polyline, bbox, max_level)

    expected = _OFF_GRID_SQUARE_EXPECTED
    expected_corners = [corner for corner, _, _ in expected]
    expected_sizes = [size for _, size, _ in expected]
    expected_kinds = [kind for _, _, kind in expected]

    print(f"\nOff-grid square test:")
    print(f"  Square (2.7,2.7)-(7.7,7.7) at max_level={max_level}")
    print(f"  Cells found: {len(result.corners)} (expected {len(expected)})")
    print(f"  Levels: {sorted(set(result.levels))}")

    # The four parallel lists must always agree in length.
    assert (
        len(result.corners)
        == len(result.sizes)
        == len(result.levels)
        == len(result.kinds)
    ), "corners, sizes, levels and kinds must be parallel lists"

    # Cheap checks first: a length or kind-count mismatch is a definite error.
    assert len(result.corners) == len(expected_corners), (
        "number of corners does not match"
    )
    assert result.kinds.count("boundary") == expected_kinds.count("boundary"), (
        "number of boundary cells does not match"
    )
    assert result.kinds.count("interior") == expected_kinds.count("interior"), (
        "number of interior cells does not match"
    )
    assert result.sizes.count(2.5) == expected_sizes.count(2.5), (
        "number of level-2 cells does not match"
    )

    # Strong check: the cells must coincide up to reordering. The core does not
    # promise an order, so compare the sorted (corner, size, kind) triples.
    actual = sorted(zip(result.corners, result.sizes, result.kinds))
    assert actual == sorted(expected), (
        "rasterized cells do not match the expected multiscale decomposition"
    )

    return True


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
        ("Off-grid square", test_square_off_grid),
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


def main():
    """Runs the Jordan-curve tests."""
    run_all_tests()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
