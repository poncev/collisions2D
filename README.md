# Multiscale Rasterization

## Overview

The Multiscale Rasterization project implements a 2D version of the algorithm described in the paper "Efficient and Robust Octree Generation for Implementing Topological Queries for Building Information Models" by Daum et al. (2012). This project aims to efficiently rasterize polylines at multiple scales, providing a robust solution for geometric modeling and visualization.

## Features

- **Efficient Octree Structure**: Utilizes a contiguous node pool for efficient memory management and fast access.
- **Cross-Linked Flood Fill**: Implements a cross-linked flood fill algorithm to classify interior and exterior cells accurately.
- **Flexible Geometry Representation**: Supports various geometric shapes, including rectangles, polygons, and circles.
- **Python Wrapper**: Provides a user-friendly Python interface for easy integration and visualization.

## Installation

To set up the project, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/multiscale-rasterization.git
   cd multiscale-rasterization
   ```

2. Install dependencies using `mamba`:
   ```bash
   mamba env create -f environment.yml
   mamba activate multiscale_rasterization
   ```

3. Build the C++ core:
   ```bash
   mkdir build
   cd build
   cmake ..
   cmake --build .
   ```

4. Run tests to ensure everything is working:
   ```bash
   ctest
   ```

## Usage

To use the Multiscale Rasterization library in your Python projects, you can import the necessary classes and functions:

```python
from multiscale_rasterization import Curve, RasterizedObject

# Example of creating a rectangle
rectangle = Curve.rectangle(0.0, 0.0, 10.0, 10.0)
```

## Documentation

For detailed documentation on the API and usage, please refer to the [API Guide](docs/API_GUIDE.md).

## Blog Post

For a deeper insight into the development process of this project, check out my blog post: [Developing Multiscale Rasterization](https://poncev.github.io/multiscale-rasterization).

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

## Acknowledgments

- Daum et al. (2012) for their foundational work on octree generation.
- The open-source community for their invaluable contributions and support.
