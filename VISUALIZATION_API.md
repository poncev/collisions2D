# Visualization API - Primary Method

## Quick Start

```python
import matplotlib.pyplot as plt
from multiscale_rasterization import multiscale_rasterization, render_rasterization

# Rasterize a polyline
polyline = [(1, 1), (9, 1), (9, 9), (1, 9), (1, 1)]
result = multiscale_rasterization(polyline, (0, 0, 10, 10), max_level=3)

# Create an axis and render
fig, ax = plt.subplots()
render_rasterization(result, ax)
plt.show()
```

## Function Signature

```python
render_rasterization(rasterized_object, output, **kwargs) -> matplotlib.axes.Axes
```

### Parameters

- **rasterized_object** : `RasterizedObject`
  - The output from `multiscale_rasterization()`
  - Contains `corners`, `sizes`, `levels`, `kinds` attributes

- **output** : `matplotlib.axes.Axes`
  - A matplotlib axis to render on
  - Can be created with `fig, ax = plt.subplots()`

### Optional Keyword Arguments

- **title** (str, optional)
  - Custom axis title. Auto-generated if omitted.

- **show_boundary** (bool, default=True)
  - Draw boundary cells (gray with orange edges)

- **show_interior** (bool, default=True)
  - Draw interior cells (black with blue edges)

- **show_curve** (bool, default=False)
  - Overlay the original polyline in red (requires curve in Scene)

- **show_bounding_box** (bool, default=False)
  - Draw dashed bounding box

- **color_by_level** (bool, default=True)
  - Ramp cell opacity by quadtree depth (coarse=opaque, fine=transparent)

- **boundary_alpha** (float, default=0.5)
  - Face transparency for boundary cells [0, 1]

- **interior_alpha** (float, default=0.5)
  - Face transparency for interior cells [0, 1]

- **linewidth** (float, default=0.8)
  - Edge width of cell polygons

- **legend** (bool, default=True)
  - Draw legend identifying cell kinds

### Returns

- **matplotlib.axes.Axes**
  - The same axis passed as `output`
  - Allows further customization by the caller

## Examples

### Basic Usage
```python
import matplotlib.pyplot as plt
from multiscale_rasterization import multiscale_rasterization, render_rasterization

result = multiscale_rasterization([(0,0), (10,10), (20,0)], (0, 0, 20, 20), max_level=4)
fig, ax = plt.subplots()
render_rasterization(result, ax)
plt.show()
```

### Custom Styling
```python
fig, ax = plt.subplots(figsize=(8, 8))
render_rasterization(result, ax, 
                     title="My Rasterization",
                     color_by_level=False,
                     boundary_alpha=0.7,
                     interior_alpha=0.8)
plt.show()
```

### Multi-Panel Figure
```python
fig, axes = plt.subplots(1, 2, figsize=(12, 6))

result1 = multiscale_rasterization(poly1, bbox1, max_level=2)
result2 = multiscale_rasterization(poly2, bbox2, max_level=3)

render_rasterization(result1, axes[0], title="Level 2")
render_rasterization(result2, axes[1], title="Level 3")

plt.tight_layout()
plt.show()
```

## Design Rationale

This is the **only recommended visualization method** as of v0.2.0. The signature `render_rasterization(rasterized_object, output)` follows the requirement from AGENTS.md (lines 40-43):

> Create a python function for visualization.
> It should work as a method like `render_rasterization(rasterized_object, output)`.
> The parameter `output` should a matplotlib axis
> so that the method add to this object the polyline and rasterization.

### Why this design?

1. **Simple API**: Direct RasterizedObject → matplotlib axis
2. **User control**: Caller owns the figure/axis lifecycle
3. **Composable**: Easy to embed in multi-panel figures or custom layouts
4. **Matplotlib native**: Returns axis for further customization
5. **Explicit**: Clear about what's being rendered

## Color Scheme

- **Red**: Original polyline (when `show_curve=True`)
- **Gray fill + orange edges**: Boundary cells
- **Black fill + blue edges**: Interior cells
- **Opacity**: Ramps from coarse (opaque) to fine (transparent) when `color_by_level=True`

## Legacy Functions

For backwards compatibility, these functions remain available but are not recommended:
- `plot_rasterization()` — Compute rasterization and plot in one call
- `plot_scene()` — Plot intermediate Scene representation
- `save_rasterization()` — Render to file
- `plot_gallery()` — Create multi-panel grid

Use `render_rasterization()` instead.
