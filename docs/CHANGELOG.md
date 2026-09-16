# Changelog

All notable changes to the multiscale rasterization project are recorded here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] — 2026-09-16

Maintenance pass addressing the high-priority findings from
`docs/code_review_comprehensive_2026-09-16.md`.

### Changed

- **`pyproject.toml` — aligned the stable-ABI target with the minimum
  interpreter.** `wheel.py-api` was `"cp38"` while `requires-python` was
  `">=3.10"`. The package uses runtime PEP 585 generics (e.g.
  `tuple[float, float]` in `_validation.py`) and PEP 604 unions, so a
  `cp38`-tagged wheel could be installed on Python 3.8/3.9 and then fail at
  import time. `wheel.py-api` is now `"cp310"`, matching `requires-python`.
  A comment explains the constraint so the two values are not drifted apart
  again.

- **`cpp/src/quadtree.cpp` — removed unused includes.** Dropped `<algorithm>`
  and `<limits>`; neither is referenced anywhere in the translation unit
  (the only standard-library uses are `std::abs`/`std::sqrt` from `<cmath>`
  and `std::pair` from `<utility>`, both retained).

- **`cpp/src/python_module.cpp` — replaced the fragile function-pointer
  cast.** The `PyMethodDef` entry for `multiscale_rasterization` used the
  double C-style cast `(PyCFunction)(void (*)(void))`. It now goes through a
  small `MR_PY_CFUNCTION_CAST` macro that prefers CPython's official
  `PyCFunction_CAST` (Python 3.13+) and otherwise falls back to a single
  explicit `reinterpret_cast<PyCFunction>`. Behaviour is unchanged; the cast
  is now documented and less brittle.

- **`cpp/src/python_module.cpp` — added allocation-failure checks.** The
  per-square loop previously passed the results of `Py_BuildValue`,
  `PyFloat_FromDouble` and `PyLong_FromLong` straight to `PyList_SET_ITEM`
  without checking for `nullptr`. A failed allocation would have stored a
  null pointer in a list slot and crashed on deallocation. Each object is now
  checked, and on failure the partially built objects and the four lists are
  released before returning `nullptr`. A null check was also added after the
  final `Py_BuildValue("(OOOO)", ...)`.

- **`API_GUIDE.md` — rewritten to match the implementation.** The previous
  guide was outdated: it referenced `find_neighbor` (the function is
  `find_neighbors`, plural), omitted `Curve`, `RasterizedObject.kinds` and the
  `BOUNDARY`/`INTERIOR` constants, and did not mention the internal `scene`
  IR. The guide now documents the full public API, the internal modules, the
  C++ core structure, and how to run both the Python and C++ test suites.

### Verified

- `Curve` (in `python/multiscale_rasterization/curve.py`) is retained as the
  public geometry container.
- `Curve2D` (in `python/multiscale_rasterization/scene.py`) is **not** a
  duplicate to be removed: it is the internal IR primitive that additionally
  carries a `kind` and a quadtree `level`, and it is used by the `Layer`/
  `Scene` document model and by `tests/test_visualization.py`. Both classes
  are kept; the distinction is now documented in `API_GUIDE.md`.

### Tests

- C++ build succeeds; `ctest` passes (1/1).
- Python suite passes (44 passed).
