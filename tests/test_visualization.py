"""Tests for the visualization module and the Curve representation.

The tests are split into three groups:

* Curve tests (no matplotlib required) cover the geometry container that users
  build polylines with.
* IR tests (no matplotlib required) cover ``Curve2D``, ``Layer`` and ``Scene``.
  The scene IR is *internal*: it is no longer part of the public API, so these
  tests import it from the module directly.
* Rendering tests exercise ``render_rasterization`` and are skipped when
  matplotlib is unavailable, mirroring the module's soft-dependency contract.
"""

import pytest

from multiscale_rasterization import (
    RasterizedObject,
    multiscale_rasterization,
)

# The scene IR is internal-only now; import it straight from the module.
from multiscale_rasterization.scene import (
    Curve2D,
    Layer,
    Scene,
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
    from multiscale_rasterization import Curve

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
# Layer / Scene (internal)
# --------------------------------------------------------------------------- #

def test_layer_rejects_non_curve2d():
    layer = Layer(name="a")
    with pytest.raises(TypeError):
        layer.add("not a curve")


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
    from multiscale_rasterization import Curve

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
# Converters (internal)
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
    from multiscale_rasterization import Curve

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
    from multiscale_rasterization import Curve

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

from multiscale_rasterization import render_rasterization  # noqa: E402
from multiscale_rasterization import visualization  # noqa: E402


def test_matplotlib_is_optional_but_detected():
    # The module always exposes the flag, whatever the environment.
    assert isinstance(visualization.HAVE_MATPLOTLIB, bool)
    assert visualization.HAVE_MATPLOTLIB is True


def test_render_rasterization_draws_cells():
    from multiscale_rasterization import Curve

    result = multiscale_rasterization(Curve.rectangle(2.0, 2.0, 8.0, 8.0), BBOX, 3)
    fig, ax = plt.subplots()
    try:
        returned = render_rasterization(result, ax)
        assert returned is ax
        assert len(ax.collections) >= 1
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert any("Boundary" in label for label in labels)
        assert any("Interior" in label for label in labels)
    finally:
        plt.close(fig)


def test_render_rasterization_rejects_bad_input():
    from multiscale_rasterization import Curve

    result = multiscale_rasterization(Curve.rectangle(2.0, 2.0, 8.0, 8.0), BBOX, 2)
    fig, ax = plt.subplots()
    try:
        with pytest.raises(TypeError):
            render_rasterization("not a rasterized object", ax)
        with pytest.raises(TypeError):
            render_rasterization(result, "not an axis")
    finally:
        plt.close(fig)


def test_render_rasterization_show_toggles():
    from multiscale_rasterization import Curve

    result = multiscale_rasterization(Curve.rectangle(2.0, 2.0, 8.0, 8.0), BBOX, 3)

    fig, ax = plt.subplots()
    try:
        render_rasterization(result, ax, show_interior=False)
        (collection,) = ax.collections
        assert "Boundary" in collection.get_label()
    finally:
        plt.close(fig)

    fig, ax = plt.subplots()
    try:
        render_rasterization(result, ax, show_boundary=False)
        (collection,) = ax.collections
        assert "Interior" in collection.get_label()
    finally:
        plt.close(fig)


def test_render_rasterization_color_by_level_ramps_opacity():
    from multiscale_rasterization import Curve

    result = multiscale_rasterization(Curve.rectangle(2.0, 2.0, 8.0, 8.0), BBOX, 4)
    fig, ax = plt.subplots()
    try:
        render_rasterization(result, ax, color_by_level=True, show_interior=False)
        (collection,) = ax.collections
        # Cell kinds are drawn as single collections; alpha is per-face.
        alphas = [rgba[3] for rgba in collection.get_facecolor()]
        assert alphas == sorted(alphas)
    finally:
        plt.close(fig)


def test_render_rasterization_handles_empty_result():
    result = multiscale_rasterization([(1.0, 1.0)], BBOX, 2)  # degenerate → empty
    fig, ax = plt.subplots()
    try:
        render_rasterization(result, ax)  # must not raise
        assert len(ax.collections) == 0
    finally:
        plt.close(fig)


# --------------------------------------------------------------------------- #
# Curve serialization and transformations
# --------------------------------------------------------------------------- #

def test_curve_to_dict_and_from_dict_round_trip():
    from multiscale_rasterization import Curve

    original = Curve([(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)],
                     closed=True, name="test_curve")

    d = original.to_dict()
    assert [tuple(v) for v in d["vertices"]] == [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
    assert d["closed"] is True
    assert d["name"] == "test_curve"

    restored = Curve.from_dict(d)
    assert restored.vertices == original.vertices
    assert restored.closed == original.closed
    assert restored.name == original.name


def test_curve_to_json_and_from_json_round_trip():
    from multiscale_rasterization import Curve

    original = Curve.rectangle(1.0, 2.0, 9.0, 8.0, name="rect_json")

    json_str = original.to_json()
    assert isinstance(json_str, str)
    assert "rect_json" in json_str

    restored = Curve.from_json(json_str)
    assert restored.vertices == original.vertices
    assert restored.closed == original.closed
    assert restored.name == original.name


def test_curve_to_geojson_format():
    from multiscale_rasterization import Curve

    curve = Curve([(1.0, 2.0), (3.0, 4.0)], closed=True, name="geo")

    geojson = curve.to_geojson()
    assert geojson["type"] == "Feature"
    assert geojson["geometry"]["type"] in ("Polygon", "LineString", "LinearRing")
    assert geojson["properties"]["name"] == "geo"
    assert geojson["properties"]["closed"] is True


def test_curve_translated_returns_new_curve_with_offset():
    from multiscale_rasterization import Curve

    original = Curve([(1.0, 2.0), (3.0, 4.0)], name="orig")

    translated = original.translated(10.0, 20.0)
    assert translated.vertices == ((11.0, 22.0), (13.0, 24.0))
    assert translated.closed == original.closed
    assert translated.name == original.name  # Preserve name


def test_curve_scaled_returns_new_curve_with_scale():
    from multiscale_rasterization import Curve

    original = Curve([(2.0, 4.0), (4.0, 6.0)], name="orig")

    scaled = original.scaled(2.0, origin=(0.0, 0.0))
    assert scaled.vertices == ((4.0, 8.0), (8.0, 12.0))
    assert scaled.closed == original.closed
    assert scaled.name == original.name


def test_curve_indexing_via_getitem():
    from multiscale_rasterization import Curve

    curve = Curve([(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)])

    assert curve[0] == (1.0, 2.0)
    assert curve[1] == (3.0, 4.0)
    assert curve[2] == (5.0, 6.0)
    assert curve[-1] == (5.0, 6.0)


def test_curve_length_via_len():
    from multiscale_rasterization import Curve

    curve = Curve([(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)])
    assert len(curve) == 3
