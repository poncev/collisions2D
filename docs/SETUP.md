# Setup Guide

This document describes how to configure the development environment for the
multiscale rasterization project, which combines a C++ core with a Python
wrapper.

## Overview

The project has two parts:

- **C++ core** (`cpp/`): the fast computational engine. It is a self-contained
  library built with CMake. The vcpkg toolchain is wired in so that future
  dependencies can be added through the `cpp/vcpkg.json` manifest.
- **Python wrapper** (`python/`): a user-friendly interface. It is built as a
  CPython extension using `scikit-build-core`, which drives CMake under the
  hood. A user only needs to `import multiscale_rasterization` and call
  `multiscale_rasterization(polyline, bounding_box, max_level)`.

## Prerequisites

- **CMake** >= 3.16 (tested with 3.28)
- **Ninja** (optional but recommended)
- **A C++ compiler** (GCC 13 on Linux)
- **vcpkg** (for future C++ dependencies)
- **conda / mamba** with the `multiai` environment

## 1. Python environment

The project uses a conda environment named `multiai`. The dependencies are
declared in `env.yml` at the repository root.

Create or update the environment:

```bash
mamba env create -f env.yml          # first time
mamba env update -f env.yml --prune  # after editing env.yml
```

Activate it:

```bash
mamba activate multiai
```

The build backend (`scikit-build-core`) is installed as a build requirement
declared in `pyproject.toml`, so it is fetched automatically when building.
If you prefer it installed explicitly, add it to `env.yml`.

## 2. Building the Python extension

From the repository root, with the `multiai` environment active:

```bash
pip install -e .
```

This compiles the C++ core and the CPython extension, then installs the
package in editable mode. The compiled `_core` extension is placed inside the
`python/multiscale_rasterization/` package directory.

> **Note on editable installs:** with `scikit-build-core`, an editable install
> builds the extension in place. If you change C++ sources, rebuild with
> `pip install -e .` again (or `pip install -e . --no-build-isolation` to skip
> re-fetching the build backend).

## 3. Running the tests

```bash
pytest tests/
```

This runs the Python smoke tests, which exercise the full
Python -> C++ -> Python pipeline.

## 4. Building and testing the C++ core standalone

You can also build and test the C++ core on its own:

```bash
cmake -S cpp -B cpp/build -DMR_BUILD_TESTS=ON
cmake --build cpp/build
ctest --test-dir cpp/build --output-on-failure
```

The vcpkg toolchain can be enabled for future dependencies:

```bash
cmake -S cpp -B cpp/build \
    -DCMAKE_TOOLCHAIN_FILE=/home/felipe/software/vcpkg/scripts/buildsystems/vcpkg.cmake \
    -DMR_BUILD_TESTS=ON
```

## 5. Quick usage

```python
from multiscale_rasterization import multiscale_rasterization

polyline = [(0.0, 0.0), (10.0, 0.0)]
bbox = (0.0, 0.0, 10.0, 10.0)

result = multiscale_rasterization(polyline, bbox, max_level=2)
print(result.corners)  # lower-left corners of the squares
print(result.sizes)    # side lengths
print(result.levels)   # quadtree depths
```

## Project layout

```
cpp/
  CMakeLists.txt          # builds the core library and the Python extension
  vcpkg.json              # vcpkg manifest (future C++ dependencies)
  include/                # public C++ headers
  src/                    # C++ sources (core + CPython bridge)
  tests/                  # C++ unit tests
python/
  multiscale_rasterization/
    __init__.py           # public Python API
    _core.*.so            # compiled extension (generated)
pyproject.toml            # scikit-build-core build configuration
tests/                    # Python smoke tests
docs/SETUP.md             # this document
```

## Troubleshooting

- **`_core` module not found on import**: the extension was not built. Run
  `pip install -e .` from the repository root.
- **CMake cannot find Python**: make sure the `multiai` environment is active
  so that `find_package(Python3)` locates the right interpreter.
- **Stale build artifacts**: delete `build/` and re-run
  `pip install -e . --no-build-isolation`.