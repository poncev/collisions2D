"""Smoke tests for the Python wrapper around the C++ core."""

import numpy as np
import pytest

from multiscale_rasterization import (
    RasterizedObject,
    __version__,
    multiscale_rasterization,
)


def test_version_is_a_string():
    assert isinstance(__version__, str)
    assert __version__.count(".") == 2  # semver-like "major.minor.patch"


def test_level_zero_single_square():
    polyline = [(0.0, 0.0), (10.0, 0.0)]
    bbox = (0.0, 0.0, 10.0, 10.0)
    result = multiscale_rasterization(polyline, bbox, 0)
    assert isinstance(result, RasterizedObject)
    assert len(result.corners) == 1
    assert result.sizes == [10.0]
    assert result.levels == [0]


def test_level_one_two_squares():
    polyline = [(0.0, 0.0), (10.0, 0.0)]
    bbox = (0.0, 0.0, 10.0, 10.0)
    result = multiscale_rasterization(polyline, bbox, 1)
    assert len(result.corners) == 2
    assert result.sizes == [5.0, 5.0]
    assert result.levels == [1, 1]


def test_accepts_numpy_arrays():
    polyline = np.array([[0.0, 0.0], [10.0, 0.0]])
    bbox = np.array([0.0, 0.0, 10.0, 10.0])
    result = multiscale_rasterization(polyline, bbox, 1)
    assert len(result.corners) == 2


def test_degenerate_polyline_yields_nothing():
    polyline = [(1.0, 1.0)]
    bbox = (0.0, 0.0, 10.0, 10.0)
    result = multiscale_rasterization(polyline, bbox, 2)
    assert len(result.corners) == 0


def test_invalid_bounding_box_raises():
    polyline = [(0.0, 0.0), (10.0, 0.0)]
    bbox = (10.0, 0.0, 0.0, 10.0)
    with pytest.raises(ValueError):
        multiscale_rasterization(polyline, bbox, 1)


def test_negative_max_level_yields_nothing():
    polyline = [(0.0, 0.0), (10.0, 0.0)]
    bbox = (0.0, 0.0, 10.0, 10.0)
    result = multiscale_rasterization(polyline, bbox, -1)
    assert len(result.corners) == 0


def test_parallel_lists_have_equal_lengths():
    polyline = [(0.0, 0.0), (10.0, 0.0)]
    bbox = (0.0, 0.0, 10.0, 10.0)
    result = multiscale_rasterization(polyline, bbox, 3)
    assert len(result.corners) == len(result.sizes) == len(result.levels)


def test_rasterized_object_repr():
    obj = RasterizedObject([(0.0, 0.0)], [10.0], [0])
    assert "RasterizedObject" in repr(obj)
    assert "n_squares=1" in repr(obj)


def test_invalid_polyline_vertex_raises():
    polyline = [(0.0, 0.0), (10.0,)]  # not a pair
    bbox = (0.0, 0.0, 10.0, 10.0)
    with pytest.raises(ValueError):
        multiscale_rasterization(polyline, bbox, 1)