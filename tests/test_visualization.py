"""Tests for the format-neutral intermediate representation (``scene``) and the
matplotlib visualization module.

The tests are split into two groups:

* IR tests (no matplotlib required) cover ``Curve2D``, ``Layer``, ``Scene``,
  the converters and the JSON round trip.
* Rendering tests exercise the matplotlib code paths and are skipped when
  matplotlib is unavailable, so the suite still passes in a lean, headless
  environment (mirroring the module's soft-dependency contract).
"""

import json

import pytest

from multiscale_rasterization import (
    Curve,
    Curve2D,
    Layer,
    RasterizedObject,
    Scene,
    multiscale_rasterization,
    scene_from_curve,
    scene_from_rasterized,
)

BBOX = (0.0, 0.0, 10.0, 10.0)


# --------------------------------------------------------------------------- #
# Curve2D
# --------------------------------------------------------------------------- #

def test_cell_round_trips_geometry():
    cell = Curve2D.cell((2.0, 3.0), 5.0, kind="boundary", level=2)
    assert cell.is_closed
    assert cell.is_cell
    assert cell.kind == "boundary"
    assert cell.level == 2
    assert cell.area() == pytest.approx(25.0)
    assert cell.bounding_box() == (2.0, 3.0, 7.0, 8.0)
    assert cell.centroid() == pytest.approx((4.5, 5.5))


def test_from_polyline_detects_closure():
    closed = Curve2D.from_polyline([(0, 0), (1, 0), (1, 1), (0, 0)])
    assert closed.is_closed
    assert closed.n_vertices == 3
    open_ = Curve2D.from_polyline([(0, 0), (1, 0), (1, 1)])
    assert not open_.is_closed
    assert open_.n_vertices == 3


def test_from_curve_preserves_metadata():
    curve = Curve.rectangle(0.0, 0.0, 4.0, 4.0, name="box")
    primitive = Curve2D.from_curve(curve)
    assert primitive.is_closed
    assert primitive.kind == "polygon"  # closed geometry defaults to polygon
    assert primitive.name == "box"
    assert primitive.area() == pytest.approx(16.0)


def test_curve2d_rejects_bad_input():
    with pytest.raises(ValueError):
        Curve2D([(0.0, 0.0)])  # fewer than two vertices
    with pytest.raises(ValueError):
        Curve2D([(0.0, 0.0), (1.0, 1.0)], kind="nonsense")
    with pytest.raises(ValueError):
        Curve2D([(0.0, 0.0), (1.0, 1.0)], level=-1)
    with pytest.raises(ValueError):
        Curve2D.cell((0.0, 0.0), 0.0)  # non-positive size


def test_curve2d_equality_and_hashing():
    a = Curve2D.cell((0.0, 0.0), 2.5, kind="interior", level=3)
    b = Curve2D.cell((0.0, 0.0), 2.5, kind="interior", level=3)
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


# --------------------------------------------------------------------------- #
# Layer / Scene
# --------------------------------------------------------------------------- #

def test_scene_layers_are_created_on_demand_and_ordered():
    scene = Scene()
    scene.add(Curve2D.cell((0.0, 0.0), 1.0, kind="interior", level=1), layer="a")
    scene.add(Curve2D.cell((0.0, 0.0), 1.0, kind="boundary", level=0), layer="b")
    assert scene.layer_names == ["a", "b"]
    assert scene.counts() == {"a": 1, "b": 1}
    assert scene.levels() == [0, 1]
    assert len(scene) == 2
    assert scene.has_layer("a")
    assert not scene.has_layer("missing")


def test_scene_missing_layer_raises_when_create_is_false():
    scene = Scene()
    with pytest.raises(KeyError):
        scene.layer("nope", create=False)


def test_scene_bounds_prefers_explicit_box():
    scene = Scene(bounds=BBOX)
    scene.add(Curve2D.cell((1.0, 1.0), 2.0, kind="interior", level=1))
    assert scene.bounds() == BBOX
    assert Scene().bounds() is None


def test_scene_bounds_derived_from_primitives():
    scene = Scene()
    scene.add(Curve2D.cell((1.0, 1.0), 2.0, kind="interior", level=1))
    scene.add(Curve2D.cell((5.0, 5.0), 3.0, kind="boundary", level=2))
    assert scene.bounds() == (1.0, 1.0, 8.0, 8.0)


def test_scene_json_round_trip_is_lossless():
    curve = Curve.rectangle(2.0, 2.0, 8.0, 8.0, name="box")
    result = multiscale_rasterization(curve, BBOX, 3)
    scene = scene_from_rasterized(result, curve=curve, bounding_box=BBOX)

    restored = Scene.from_json(scene.to_json())
    assert restored.layer_names == scene.layer_names
    assert restored.counts() == scene.counts()
    assert restored.bounds() == BBOX
    assert restored.name == "box"
    assert [c.kind for c in restored.iter_curves()] == [
        c.kind for c in scene.iter_curves()
    ]
    assert [c.level for c in restored.iter_curves()] == [
        c.level for c in scene.iter_curves()
    ]


# --------------------------------------------------------------------------- #
# Converters
# --------------------------------------------------------------------------- #

def test_scene_from_rasterized_splits_kinds_into_layers():
    result = RasterizedObject(
        corners=[(0.0, 0.0), (5.0, 5.0)],
        sizes=[5.0, 5.0],
        levels=[0, 1],
        kinds=["boundary", "interior"],
    )
    scene = scene_from_rasterized(result, bounding_box=BBOX)
    assert scene.counts() == {"boundary": 1, "interior": 1}
    assert next(scene.iter_layer("boundary")).level == 0
    assert next(scene.iter_layer("interior")).kind == "interior"


def test_scene_from_rasterized_includes_curve_layer():
    result = multiscale_rasterization(Curve.rectangle(2, 2, 8, 8), BBOX, 2)
    curve = Curve.rectangle(2.0, 2.0, 8.0, 8.0, name="box")
    scene = scene_from_rasterized(result, curve=curve, bounding_box=BBOX)
    assert "curve" in scene.layer_names
    assert scene.name == "box"
    assert sum(1 for c in scene.iter_layer("curve") if not c.is_cell) == 1


def test_scene_from_rasterized_rejects_unknown_kind():
    result = RasterizedObject([(0.0, 0.0)], [1.0], [0], kinds=["boundary"])
    result.kinds = ["weird"]
    with pytest.raises(ValueError):
        scene_from_rasterized(result)


def test_scene_from_curve_wraps_geometry():
    scene = scene_from_curve(Curve([(0, 0), (1, 0), (1, 1)], closed=True, name="tri"))
    assert scene.name == "tri"
    (primitive,) = list(scene.iter_curves())
    assert primitive.kind == "polygon"
    assert primitive.is_closed


# --------------------------------------------------------------------------- #
# Rendering (requires matplotlib)
# --------------------------------------------------------------------------- #

mpl = pytest.importorskip("matplotlib")
mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from multiscale_rasterization import (  # noqa: E402
    plot_gallery,
    plot_rasterization,
    plot_scene,
    save_rasterization,
)
from multiscale_rasterization import visualization  # noqa: E402


def test_matplotlib_is_optional_but_detected():
    # The module always exposes the flag, whatever the environment.
    assert isinstance(visualization.HAVE_MATPLOTLIB, bool)
    assert visualization.HAVE_MATPLOTLIB is True


def test_plot_rasterization_draws_cells_and_red_curve():
    curve = Curve.rectangle(2.0, 2.0, 8.0, 8.0, name="box")
    ax = plot_rasterization(curve, BBOX, 3)
    try:
        assert len(ax.collections) >= 1
        colors = {line.get_color() for line in ax.get_lines()}
        assert visualization.POLYLINE_COLOR in colors
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert any("boundary" in label for label in labels)
        assert any("interior" in label for label in labels)
    finally:
        plt.close(ax.figure)


def test_boundary_cells_use_gray_fill_and_orange_edge():
    curve = Curve.rectangle(2.0, 2.0, 8.0, 8.0)
    ax = plot_rasterization(
        curve, BBOX, 3, color_by_level=False, show_interior=False
    )
    try:
        (collection,) = ax.collections
        assert tuple(collection.get_facecolor()[0][:3]) == pytest.approx(
            _rgb(visualization.BOUNDARY_FILL_COLOR)
        )
        assert tuple(collection.get_edgecolor()[0][:3]) == pytest.approx(
            _rgb(visualization.BOUNDARY_EDGE_COLOR)
        )
    finally:
        plt.close(ax.figure)


def test_interior_cells_use_black_fill_and_blue_edge():
    curve = Curve.rectangle(2.0, 2.0, 8.0, 8.0)
    ax = plot_rasterization(
        curve, BBOX, 3, color_by_level=False, show_boundary=False
    )
    try:
        (collection,) = ax.collections
        assert tuple(collection.get_facecolor()[0][:3]) == pytest.approx(
            _rgb(visualization.INTERIOR_FILL_COLOR)
        )
        assert tuple(collection.get_edgecolor()[0][:3]) == pytest.approx(
            _rgb(visualization.INTERIOR_EDGE_COLOR)
        )
    finally:
        plt.close(ax.figure)


def test_color_by_level_ramps_opacity_coarse_to_fine():
    curve = Curve.rectangle(2.0, 2.0, 8.0, 8.0)
    ax = plot_rasterization(curve, BBOX, 4, color_by_level=True)
    try:
        # Collections are added coarse-to-fine; opacity must be non-decreasing.
        alphas = [c.get_alpha() for c in ax.collections]
        assert alphas == sorted(alphas)
    finally:
        plt.close(ax.figure)


def test_plot_scene_accepts_ir_and_rejects_other_types():
    result = multiscale_rasterization(Curve.rectangle(2, 2, 8, 8), BBOX, 2)
    scene = scene_from_rasterized(result, bounding_box=BBOX)
    ax = plot_scene(scene)
    try:
        assert len(ax.collections) >= 1
    finally:
        plt.close(ax.figure)

    with pytest.raises(TypeError):
        plot_scene("not a scene")


def test_save_rasterization_writes_a_file(tmp_path):
    curve = Curve.rectangle(2.0, 2.0, 8.0, 8.0, name="box")
    target = tmp_path / "box.png"
    written = save_rasterization(curve, BBOX, 3, path=target)
    assert written == target
    assert target.is_file() and target.stat().st_size > 0


def test_save_rasterization_requires_a_format(tmp_path):
    curve = Curve.rectangle(2.0, 2.0, 8.0, 8.0)
    with pytest.raises(ValueError):
        save_rasterization(curve, BBOX, 2, path=tmp_path / "noextension")


def test_plot_gallery_builds_a_grid():
    curves = [
        Curve.rectangle(2.0, 2.0, 8.0, 8.0, name="square"),
        Curve([(1, 1), (9, 1), (5, 8)], closed=True, name="triangle"),
    ]
    fig, axes = plot_gallery(curves, BBOX, 3, ncols=2)
    try:
        assert axes.shape == (1, 2)
    finally:
        plt.close(fig)


def _rgb(hex_color):
    """Converts ``"#rrggbb"`` to a ``(r, g, b)`` triple in the 0..1 range."""
    import matplotlib.colors as mcolors

    return mcolors.to_rgb(hex_color)