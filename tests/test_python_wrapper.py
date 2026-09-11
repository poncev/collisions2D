"""Smoke tests for the Python wrapper around the C++ core."""

import numpy as np
import pytest

from multiscale_rasterization import RasterizedObject, multiscale_rasterization


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