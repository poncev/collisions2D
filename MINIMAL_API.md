# Multiscale Rasterization - Minimal Internal Library API

**Version:** 0.1.0  
**Status:** Simplified to minimal internal-use library  
**Tests:** 43/43 passing ✅

## Overview

This is now a **minimal, purpose-built Python library** for programmers who need to:
1. Rasterize a 2D polyline at multiple scales
2. Visualize the result with matplotlib

No CLI tools, no backwards compatibility, no Scene IR complexity. Just two calls: rasterize, then render.

## Public API

### Core Functions

#### `multiscale_rasterization(polyline, bounding_box, max_level)`
```python
from multiscale_rasterization import multiscale_rasterization

polyline = [(0, 0), (10, 10), (20, 0)]
result = multiscale_rasterization(
    polyline,
    bounding_box=(0, 0, 20, 20),
    max_level=3
)
# Returns: RasterizedObject
```

**Parameters:**
- `polyline`: list of (x, y) tuples or Curve object
- `bounding_box`: (min_x, min_y, max_x, max_y) tuple
- `max_level`: int, finest subdivision depth (0 = coarsest)

**Returns:** `RasterizedObject` with attributes:
- `corners`: list of (x, y) lower-left corners
- `sizes`: list of cell side lengths
- `levels`: list of quadtree depths
- `kinds`: list of "boundary" or "interior" labels

#### `render_rasterization(rasterized_object, output_axis, **kwargs)`
```python
import matplotlib.pyplot as plt
from multiscale_rasterization import render_rasterization

fig, ax = plt.subplots()
render_rasterization(result, ax, title="My Rasterization")
plt.show()
```

**Parameters:**
- `rasterized_object`: RasterizedObject from multiscale_rasterization()
- `output_axis`: matplotlib.axes.Axes instance
- `**kwargs`: optional styling
  - `title` (str): custom axis title
  - `show_boundary` (bool, default True): draw boundary cells (gray)
  - `show_interior` (bool, default True): draw interior cells (black)
  - `color_by_level` (bool, default True): opacity ramp by depth
  - `boundary_alpha` (float, default 0.5): opacity for boundary cells
  - `interior_alpha` (float, default 0.5): opacity for interior cells
  - `linewidth` (float, default 0.8): edge width
  - `legend` (bool, default True): show legend

**Returns:** `matplotlib.axes.Axes` (for further customization)

### Utility Classes

#### `Curve`
Create polylines programmatically:
```python
from multiscale_rasterization import Curve

# Create shapes
square = Curve.rectangle(0, 0, 10, 10, name="my_square")
triangle = Curve([(0, 0), (10, 0), (5, 8)], closed=True, name="triangle")

# Use in rasterization
result = multiscale_rasterization(square.to_polyline(), (0, 0, 10, 10), max_level=2)
```

**Methods:**
- `Curve.rectangle(x_min, y_min, x_max, y_max, name)`: create rectangle
- `Curve.regular_polygon(n_sides, radius, center, name)`: create regular polygon
- `Curve.circle(radius, center, n_segments, name)`: approximate circle
- `to_polyline()`: convert to list of vertices
- `to_dict()`, `from_dict()`: serialization
- `to_json()`, `from_json()`: JSON serialization
- `to_geojson()`: GeoJSON format
- `translated(dx, dy)`: translate curve
- `scaled(factor, origin)`: scale curve

#### `RasterizedObject`
Container for rasterization results (created by `multiscale_rasterization()`):
```python
result = multiscale_rasterization(polyline, bbox, max_level=3)

# Access data
print(f"Total cells: {result.n_squares}")
print(f"Boundary: {len(result.boundary_cells()[0])}")
print(f"Interior: {len(result.interior_cells()[0])}")

# Constants
from multiscale_rasterization import BOUNDARY, INTERIOR
```

**Attributes:**
- `corners`: list[tuple[float, float]]
- `sizes`: list[float]
- `levels`: list[int]
- `kinds`: list[str]

**Methods:**
- `n_squares`: property, total number of cells
- `boundary_cells()`: returns (corners, sizes, levels) for boundary cells
- `interior_cells()`: returns (corners, sizes, levels) for interior cells
- `levels_present()`: sorted list of unique levels

### Constants

```python
from multiscale_rasterization import BOUNDARY, INTERIOR
# BOUNDARY = "boundary"
# INTERIOR = "interior"
```

## Complete Example

```python
import matplotlib.pyplot as plt
from multiscale_rasterization import (
    multiscale_rasterization,
    render_rasterization,
    Curve,
)

# Define geometry
polyline = [(1, 1), (9, 1), (9, 9), (1, 9), (1, 1)]

# Rasterize at multiple scales
result = multiscale_rasterization(
    polyline,
    bounding_box=(0, 0, 10, 10),
    max_level=3
)

# Visualize
fig, ax = plt.subplots(figsize=(8, 8))
render_rasterization(result, ax, title="Multiscale Rasterization")
plt.tight_layout()
plt.show()

# Multi-panel comparison
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for i, max_level in enumerate([1, 2, 3]):
    r = multiscale_rasterization(polyline, (0, 0, 10, 10), max_level=max_level)
    render_rasterization(r, axes[i], title=f"Level {max_level}")
plt.tight_layout()
plt.show()
```

## Visualization Color Scheme

- **Red polyline**: original geometry (if show_curve=True)
- **Gray fill + orange edges**: boundary cells (intersecting the polyline)
- **Black fill + blue edges**: interior cells (inside the geometry)
- **Opacity ramp**: when `color_by_level=True`, coarse cells are opaque, fine cells are more transparent

## What Was Removed

**Intentionally removed (no longer needed):**
- CLI infrastructure (argparse, main entry point, tools)
- Scene intermediate representation (public API only; internal copy kept for tests)
- Legacy visualization functions: `plot_rasterization()`, `plot_scene()`, `save_rasterization()`, `plot_gallery()`
- Backwards compatibility layer

**Result:** Simple, focused library with ~7000 lines of C++ core + ~500 lines of Python wrapper

## Internal Implementation

- **C++ Core** (`cpp/src/`): Quadtree subdivision with Liang-Barsky intersection testing
- **Python Wrapper** (`python/`): Type validation, data conversion, matplotlib rendering
- **Scene IR** (`scene.py`): Internal format-neutral representation (kept for internal flexibility, not exported)

## Testing

All tests passing (43/43):
- Core rasterization tests: Jordan curves, edge cases
- Curve class: geometry operations, serialization
- RasterizedObject: data integrity, cell selection
- Visualization: rendering, styling, edge cases

Run tests:
```bash
pytest tests/ -v
```

## Performance Notes

- **Rasterization**: O(2^(2·max_level)) cells worst-case, typically much faster due to early termination
- **Rendering**: O(n) where n = number of cells
- **Memory**: Proportional to cells generated (quadtree depth and polyline complexity)

## Future Extensibility

While this is a minimal library, the architecture supports easy future additions:
- **IGES/SVG/DXF export**: Scene IR can be extended with new exporters
- **Performance optimization**: C++ core can be enhanced without API changes
- **Additional curve operations**: New methods in Curve class
- **Advanced visualization**: New rendering backends on top of Scene IR

## Development

Branch: `feature/simplify-to-minimal-api`

To test locally:
```bash
# Install in development mode
pip install -e .

# Run tests
pytest tests/ -v

# Try the API
python -c "from multiscale_rasterization import multiscale_rasterization, render_rasterization; print('Ready to use!')"
```

## License & Attribution

Based on "Efficient and Robust Octree Generation for Implementing Topological Queries for Building Information Models" (Daum & Borrmann, 2012), adapted for 2D quadtrees.
