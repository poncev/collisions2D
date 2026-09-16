# Multiscale Rasterization — API Guide

This guide documents the public Python API, the structure of the C++ core, and
how to test the project. It reflects the current implementation; when in doubt,
the docstrings in the source are authoritative.

## Overview

The library rasterizes a 2D polyline at multiple scales. It starts from a
single square covering a user-supplied bounding box and recursively subdivides
every square that intersects the polyline until a finest, user-defined scale
(`max_level`) is reached. The result is the set of squares in the multiscale
hierarchy that touch the polyline **and its interior**.

The heavy computation lives in C++ (compiled as a CPython extension named
`_core`); the Python package validates inputs, converts between Python and C++
data structures, and provides the plotting helper.

## Installation

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e '.[viz]'    # matplotlib, for render_rasterization
pip install -e '.[test]'   # pytest
```

## Public Python API

The package exports the following names from `multiscale_rasterization`:

| Name | Kind | Description |
| --- | --- | --- |
| `multiscale_rasterization` | function | Rasterize a polyline at multiple scales. |
| `RasterizedObject` | class | Container for the resulting squares. |
| `Curve` | class | Optional input-geometry representation (vertices + closure metadata). |
| `render_rasterization` | function | Draw a `RasterizedObject` onto a matplotlib axis. |
| `HAVE_MATPLOTLIB` | bool | Whether matplotlib is importable. |
| `BOUNDARY`, `INTERIOR` | str | The two cell-kind labels used in `RasterizedObject.kinds`. |
| `__version__` | str | The package version (e.g. `"0.1.0"`). |

### `multiscale_rasterization(polyline, bounding_box, max_level)`

Rasterizes a polyline.

- `polyline`: a sequence of `(x, y)` pairs, or a `Curve`. A closed `Curve` is
  passed to the core with an explicit closing vertex.
- `bounding_box`: `(min_x, min_y, max_x, max_y)`.
- `max_level`: the finest subdivision depth (`>= 0`).

Returns a `RasterizedObject`.

```python
from multiscale_rasterization import multiscale_rasterization

polyline = [(0, 0), (10, 10), (20, 0)]
result = multiscale_rasterization(
    polyline,
    bounding_box=(0, 0, 20, 20),
    max_level=3,
)
```

### `RasterizedObject`

The four attributes are parallel lists: entry `i` of each describes the same
square.

| Attribute | Type | Description |
| --- | --- | --- |
| `corners` | `list[tuple[float, float]]` | Lower-left corner of each square. |
| `sizes` | `list[float]` | Side length of each square. |
| `levels` | `list[int]` | Quadtree depth of each square (`0` = coarsest). |
| `kinds` | `list[str]` | `"boundary"` or `"interior"` (see `BOUNDARY`/`INTERIOR`). |

Convenience members: `n_squares`, `boundary_cells()`, `interior_cells()`,
`levels_present()`, and `len(result)`.

### `Curve`

An ordered sequence of vertices with optional closure metadata. It is a
convenience layer: the core still receives a plain sequence of `(x, y)` pairs.

```python
from multiscale_rasterization import Curve

square = Curve.rectangle(0.0, 0.0, 10.0, 10.0, name="box")
result = multiscale_rasterization(square, square.bounding_box(), max_level=4)
```

Construction helpers: `Curve.from_polyline`, `Curve.rectangle`,
`Curve.regular_polygon`, `Curve.circle`. Geometry helpers: `edges()`,
`to_polyline()`, `bounding_box()`, `translated()`, `scaled()`. Serialization:
`to_dict`/`from_dict`, `to_json`/`from_json`, `to_geojson`.

### `render_rasterization(rasterized_object, output, **kwargs)`

Draws a `RasterizedObject` onto a caller-provided matplotlib axis and returns
that axis. `output` must be a matplotlib `Axes`.

```python
import matplotlib.pyplot as plt
from multiscale_rasterization import multiscale_rasterization, render_rasterization

result = multiscale_rasterization([(0, 0), (10, 10)], (0, 0, 10, 10), max_level=3)
fig, ax = plt.subplots()
render_rasterization(result, ax)
plt.show()
```

Styling keywords: `title`, `show_boundary`, `show_interior`,
`color_by_level`, `boundary_alpha`, `interior_alpha`, `linewidth`, `legend`.

matplotlib is a **soft** dependency: the package imports and the core runs
without it. Only calling `render_rasterization` requires it, and that call
raises an actionable `ImportError` when it is missing.

## Internal modules

These are not part of the public API and may change without notice:

- `multiscale_rasterization._validation` — shared vertex coercion and the
  `Point`/`BoundingBox` aliases.
- `multiscale_rasterization.scene` — a format-neutral intermediate
  representation (`Curve2D`, `Layer`, `Scene`) intended as a seam for future
  export formats (SVG/DXF). It is imported directly by the tests.

> **Note on `Curve` vs `Curve2D`.** `Curve` (in `curve.py`) is the public
> geometry container. `Curve2D` (in `scene.py`) is an internal IR primitive
> that additionally carries a `kind` and a quadtree `level`, so it can model
> both input geometry and rasterized cells. They overlap in their vertex
> handling but are not interchangeable; `Curve2D` is retained because the
> `Layer`/`Scene` document model and the visualization tests depend on it.

## Basic structure of the C++ implementation

The core is a quadtree over the bounding box. Nodes are stored in a contiguous
pool (`Quadtree::nodes`) and referenced by index, which keeps the structure
cache-friendly and avoids pointer chasing.

Key types and functions (see `cpp/include/multiscale_rasterization/`):

- `Point`, `BoundingBox` — basic geometry (`point.h`, `bounding_box.h`).
- `QuadtreeNode` — a node: `bounds`, `level`, `color`, `parent`, `children`,
  `xbit`/`ybit` location bits, `candidate_edges`, and `neighbors`.
- `Quadtree` — the node pool plus `max_level`.
- `CellColor` — the paper's tri-color scheme: `Undetermined`, `Gray`
  (boundary), `Black` (interior), `White` (exterior).
- `initialize_quadtree(box, max_level)` — creates the root.
- `liang_barsky_intersect(a, b, box)` — segment/square clip test.
- `subdivide_node(tree, node_index, polyline)` — splits a node into four
  children, propagating the candidate-edge list.
- `cross_link_leaves(tree)` — the paper's Section 4.2 optimization: links each
  leaf to its axis-aligned leaf neighbors.
- `find_neighbors(tree, index, dir, path, out)` — hierarchical neighbor
  lookup used by `cross_link_leaves` (note the plural name).
- `flood_fill(tree, polyline)` — classifies free cells as interior/exterior
  using the Gray boundary cells as barriers.
- `multiscale_rasterization(polyline, bounding_box, max_level)` — the public
  entry point; orchestrates seed → boundary → flood → collect.
- `RasterizedObject` — the flat result (`corners`, `sizes`, `levels`,
  `kinds`).

## Testing

The Python tests use `pytest`:

```bash
pytest tests/ -v
```

The C++ unit tests are built with CMake:

```bash
cmake -S cpp -B cpp/build -DMR_BUILD_TESTS=ON
cmake --build cpp/build
ctest --test-dir cpp/build --output-on-failure
```

Test groups:

- **Core algorithm tests** — validate the rasterization and the
  `RasterizedObject` contents.
- **Curve / IR tests** — geometry operations and the internal `scene` IR.
- **Visualization tests** — rendering, skipped when matplotlib is unavailable.

## Future work

- Additional geometric shapes and input formats.
- Export functionality (SVG, DXF) built on the internal `scene` IR.
- Performance tuning for large-scale rasterizations.

## References

- Daum, J., & Borrmann, A. (2012). *Efficient and Robust Octree Generation for
  Implementing Topological Queries for Building Information Models.*