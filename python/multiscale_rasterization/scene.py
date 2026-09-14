"""Format-neutral 2D intermediate representation (IR) for rasterization.

This module defines the canonical *intermediate representation* (IR) that
sits between the rasterizer and any consumer (matplotlib today; SVG, DXF or
IGES exporters later). The design has three layers:

``Curve2D``
    A single 2D primitive: an ordered sequence of ``(x, y)`` vertices plus a
    small amount of semantic metadata. It deliberately models *both* the input
    geometry (an open polyline or a closed polygon) and a rasterized cell (a
    closed square tagged with its quadtree ``level`` and its ``kind``:
    ``"boundary"`` or ``"interior"``). One class therefore covers every
    primitive any rasterization result can contain.
``Layer``
    A named, ordered group of :class:`Curve2D` primitives. Layers are how a
    :class:`Scene` keeps the geometry, the boundary cells and the interior
    cells apart, so consumers can style or filter them independently.
``Scene``
    An ordered collection of layers plus an optional explicit bounding box.
    This is the document model: an exporter only has to walk the layers and
    convert each :class:`Curve2D` to the target format.

Why a separate IR?
------------------
The C++ core returns a flat, four-list :class:`RasterizedObject`
(``corners``/``sizes``/``levels``/``kinds``). That layout is efficient for the
core but awkward for consumers, which repeatedly re-derive rectangles, group by
kind and compute bounds. Converting once, here, gives:

* a single place to add per-primitive metadata without touching the C++ API;
* a lossless, JSON-serialisable round trip (``to_dict``/``from_dict``) useful
  for caching results and for golden-file tests;
* a stable seam for future formats: an SVG/DXF/IGES writer only needs to map
  ``Scene``/``Curve2D`` onto its own primitives, never onto the C++ structs.

Nothing in this module imports matplotlib, NumPy or the compiled extension, so
it is safe to import anywhere (including headless CI) and cheap to depend on.

Examples
--------
>>> from multiscale_rasterization import Curve2D
>>> cell = Curve2D.cell((0.0, 0.0), 5.0, kind="boundary", level=2)
>>> cell.kind, cell.level, cell.is_closed
('boundary', 2, True)
>>> cell.area()
25.0
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Sequence

from ._validation import BoundingBox, Point, coerce_point as _coerce_point

__all__ = [
    "Curve2D",
    "Layer",
    "Scene",
    "KIND_POLYLINE",
    "KIND_POLYGON",
    "KIND_BOUNDARY",
    "KIND_INTERIOR",
    "LAYER_CURVE",
    "LAYER_BOUNDARY",
    "LAYER_INTERIOR",
    "scene_from_curve",
    "scene_from_rasterized",
    "Point",
    "BoundingBox",
]

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
#: An open sequence of vertices (the input geometry, or its outline).
KIND_POLYLINE = "polyline"
#: A closed sequence of vertices with no further meaning beyond its outline.
KIND_POLYGON = "polygon"
#: A cell the geometry passes through (the paper's "Gray" cell).
KIND_BOUNDARY = "boundary"
#: A cell fully inside the geometry (the paper's "Black" cell).
KIND_INTERIOR = "interior"

#: Cell kinds, in draw order (interior first so boundary stays on top).
CELL_KINDS = (KIND_INTERIOR, KIND_BOUNDARY)

#: Default layer names used by :func:`scene_from_rasterized`.
LAYER_CURVE = "curve"
LAYER_BOUNDARY = "boundary"
LAYER_INTERIOR = "interior"

_VALID_KINDS = frozenset(
    {KIND_POLYLINE, KIND_POLYGON, KIND_BOUNDARY, KIND_INTERIOR}
)


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #

def _validate_kind(kind: str) -> str:
    """Normalises and validates a primitive kind."""
    if not isinstance(kind, str) or kind.lower() not in _VALID_KINDS:
        raise ValueError(
            f"unknown curve kind {kind!r}; expected one of "
            f"{', '.join(sorted(_VALID_KINDS))}"
        )
    return kind.lower()


def _coerce_level(level) -> int | None:
    """Normalises an optional quadtree level to a non-negative int."""
    if level is None:
        return None
    level = int(level)
    if level < 0:
        raise ValueError(f"level must be non-negative, got {level}")
    return level


# --------------------------------------------------------------------------- #
# Curve2D
# --------------------------------------------------------------------------- #

class Curve2D:
    """A single 2D primitive: vertices plus semantic metadata.

    Instances represent either a piece of input geometry (an open polyline or a
    closed polygon) or a rasterized cell (a closed square carrying its quadtree
    ``level`` and ``kind``). The class intentionally has no dependency on the
    rasterizer or on any plotting library.

    Parameters
    ----------
    points : iterable of (float, float)
        The vertices, in order. At least two are required.
    closed : bool, optional
        Whether the last vertex is implicitly connected to the first. Defaults
        to ``False`` (an open polyline).
    kind : str, optional
        One of ``"polyline"``, ``"polygon"``, ``"boundary"``, ``"interior"``.
        Defaults to ``"polyline"``.
    level : int, optional
        The quadtree depth of the primitive, when it comes from a
        rasterization. ``None`` for raw geometry.
    name : str, optional
        A human-readable label (used for titles and legend text).

    Raises
    ------
    ValueError
        If fewer than two vertices are supplied, a vertex is not a pair of
        finite numbers, the kind is unknown, or the level is negative.
    """

    __slots__ = ("_points", "_closed", "_kind", "_level", "_name")

    def __init__(
        self,
        points: Iterable[Sequence[float]],
        *,
        closed: bool = False,
        kind: str = KIND_POLYLINE,
        level: int | None = None,
        name: str | None = None,
    ) -> None:
        verts = tuple(_coerce_point(p, i) for i, p in enumerate(points))
        if len(verts) < 2:
            raise ValueError("a Curve2D needs at least two vertices")
        self._points = verts
        self._closed = bool(closed)
        self._kind = _validate_kind(kind)
        self._level = _coerce_level(level)
        self._name = name

    # -- construction ------------------------------------------------------

    @classmethod
    def from_polyline(
        cls,
        polyline: Iterable[Sequence[float]],
        *,
        kind: str = KIND_POLYLINE,
        level: int | None = None,
        name: str | None = None,
    ) -> "Curve2D":
        """Builds a primitive from a polyline, detecting closure automatically.

        A polyline is treated as closed when it has at least three vertices and
        its first and last vertices coincide; the duplicated closing vertex is
        then dropped and ``closed`` is set to ``True``.
        """
        verts = [_coerce_point(p, i) for i, p in enumerate(polyline)]
        if len(verts) >= 3 and verts[0] == verts[-1]:
            return cls(
                verts[:-1], closed=True, kind=kind, level=level, name=name
            )
        return cls(verts, closed=False, kind=kind, level=level, name=name)

    @classmethod
    def from_curve(
        cls,
        curve,
        *,
        kind: str | None = None,
        level: int | None = None,
        name: str | None = None,
    ) -> "Curve2D":
        """Builds a primitive from a :class:`~multiscale_rasterization.Curve`.

        Any object exposing ``vertices`` and ``closed`` attributes (and an
        optional ``name``) is accepted, which keeps this module free of a hard
        import of :mod:`multiscale_rasterization.curve`.
        """
        vertices = getattr(curve, "vertices", None)
        if vertices is None:
            raise TypeError(
                "from_curve expects an object with a 'vertices' attribute, "
                f"got {type(curve).__name__}"
            )
        closed = bool(getattr(curve, "closed", False))
        resolved_kind = kind if kind is not None else (
            KIND_POLYGON if closed else KIND_POLYLINE
        )
        resolved_name = name if name is not None else getattr(curve, "name", None)
        return cls(
            vertices,
            closed=closed,
            kind=resolved_kind,
            level=level,
            name=resolved_name,
        )

    @classmethod
    def rectangle(
        cls,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        kind: str = KIND_POLYGON,
        level: int | None = None,
        name: str | None = None,
    ) -> "Curve2D":
        """An axis-aligned, closed rectangle given by two opposite corners."""
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        return cls(
            [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
            closed=True,
            kind=kind,
            level=level,
            name=name,
        )

    @classmethod
    def cell(
        cls,
        corner: Sequence[float],
        size: float,
        *,
        kind: str = KIND_BOUNDARY,
        level: int | None = None,
        name: str | None = None,
    ) -> "Curve2D":
        """A quadtree cell: the closed square at ``corner`` with side ``size``.

        This is the canonical way to turn one entry of a
        :class:`RasterizedObject` into an IR primitive.
        """
        x, y = _coerce_point(corner, 0)
        size = float(size)
        if not math.isfinite(size) or size <= 0.0:
            raise ValueError(f"cell size must be positive and finite, got {size!r}")
        return cls.rectangle(
            x, y, x + size, y + size, kind=kind, level=level, name=name
        )

    # -- properties --------------------------------------------------------

    @property
    def points(self) -> tuple[Point, ...]:
        """The vertices, without any implicit closing vertex."""
        return self._points

    #: Alias for :attr:`points`, mirroring :class:`~multiscale_rasterization.Curve`.
    @property
    def vertices(self) -> tuple[Point, ...]:
        """Alias for :attr:`points`."""
        return self._points

    @property
    def closed(self) -> bool:
        """Whether the primitive is closed."""
        return self._closed

    @property
    def is_closed(self) -> bool:
        """Alias for :attr:`closed`."""
        return self._closed

    @property
    def kind(self) -> str:
        """The semantic kind of the primitive."""
        return self._kind

    @property
    def level(self) -> int | None:
        """The quadtree depth, or ``None`` for non-rasterized geometry."""
        return self._level

    @property
    def name(self) -> str | None:
        """The optional human-readable label."""
        return self._name

    @property
    def n_vertices(self) -> int:
        """The number of stored vertices."""
        return len(self._points)

    @property
    def n_edges(self) -> int:
        """The number of edges (equal to the vertex count when closed)."""
        return len(self._points) if self._closed else len(self._points) - 1

    @property
    def is_cell(self) -> bool:
        """Whether this primitive came from the rasterization."""
        return self._kind in (KIND_BOUNDARY, KIND_INTERIOR)

    # -- geometry ----------------------------------------------------------

    def edges(self) -> Iterator[tuple[Point, Point]]:
        """Yields the ``(start, end)`` pairs of the primitive's edges."""
        pts = self._points
        for i in range(len(pts) - 1):
            yield pts[i], pts[i + 1]
        if self._closed:
            yield pts[-1], pts[0]

    def to_polyline(self) -> list[Point]:
        """Returns the vertices as a polyline, closing the loop when needed."""
        pts = list(self._points)
        if self._closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        return pts

    def bounding_box(self, padding: float = 0.0) -> BoundingBox:
        """Returns ``(min_x, min_y, max_x, max_y)``, optionally padded."""
        xs = [p[0] for p in self._points]
        ys = [p[1] for p in self._points]
        return (
            min(xs) - padding,
            min(ys) - padding,
            max(xs) + padding,
            max(ys) + padding,
        )

    def area(self) -> float:
        """The signed-less area enclosed by the primitive (shoelace formula).

        Open primitives have zero area by definition.
        """
        if not self._closed or len(self._points) < 3:
            return 0.0
        pts = self._points
        acc = 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            acc += x0 * y1 - x1 * y0
        return abs(acc) * 0.5

    def centroid(self) -> Point:
        """The arithmetic mean of the vertices (the centre, for a cell)."""
        n = len(self._points)
        return (
            sum(p[0] for p in self._points) / n,
            sum(p[1] for p in self._points) / n,
        )

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        """Returns a JSON-serialisable mapping describing the primitive.

        The layout is stable and lossless (round-trips through
        :meth:`from_dict`):

            {"name": str | None, "closed": bool, "kind": str,
             "level": int | None, "points": [[x, y], ...]}
        """
        return {
            "name": self._name,
            "closed": self._closed,
            "kind": self._kind,
            "level": self._level,
            "points": [[x, y] for x, y in self._points],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Curve2D":
        """Rebuilds a primitive from :meth:`to_dict` output.

        Unknown keys are ignored, which keeps the format forward-compatible.
        """
        if not isinstance(data, dict):
            raise TypeError(
                f"curve data must be a mapping, got {type(data).__name__}"
            )
        try:
            points = data["points"]
        except KeyError as exc:
            raise ValueError("curve data is missing the 'points' key") from exc
        return cls(
            points,
            closed=bool(data.get("closed", False)),
            kind=data.get("kind", KIND_POLYLINE),
            level=data.get("level"),
            name=data.get("name"),
        )

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialises the primitive to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "Curve2D":
        """Parses a primitive from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))

    # -- dunder ------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._points)

    def __iter__(self) -> Iterator[Point]:
        return iter(self._points)

    def __getitem__(self, index):
        return self._points[index]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Curve2D):
            return NotImplemented
        return (
            self._points == other._points
            and self._closed == other._closed
            and self._kind == other._kind
            and self._level == other._level
            and self._name == other._name
        )

    def __hash__(self) -> int:  # cells are used as set members in consumers
        return hash((self._points, self._closed, self._kind, self._level))

    def __repr__(self) -> str:
        level = "" if self._level is None else f", level={self._level}"
        name = "" if self._name is None else f", name={self._name!r}"
        return (
            f"Curve2D(kind={self._kind!r}, n_vertices={len(self._points)}, "
            f"closed={self._closed}{level}{name})"
        )


# --------------------------------------------------------------------------- #
# Layer / Scene
# --------------------------------------------------------------------------- #

@dataclass
class Layer:
    """A named, ordered group of :class:`Curve2D` primitives."""

    name: str
    curves: list[Curve2D] = field(default_factory=list)

    def add(self, curve: Curve2D) -> Curve2D:
        """Appends ``curve`` to the layer and returns it."""
        if not isinstance(curve, Curve2D):
            raise TypeError(
                f"a layer holds Curve2D objects, got {type(curve).__name__}"
            )
        self.curves.append(curve)
        return curve

    def extend(self, curves: Iterable[Curve2D]) -> None:
        """Appends every primitive in ``curves`` to the layer."""
        for curve in curves:
            self.add(curve)

    def levels(self) -> list[int]:
        """The sorted, distinct quadtree levels present in the layer."""
        found = {c.level for c in self.curves if c.level is not None}
        return sorted(found)

    def to_dict(self) -> dict:
        """Returns a JSON-serialisable mapping describing the layer."""
        return {
            "name": self.name,
            "curves": [c.to_dict() for c in self.curves],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Layer":
        """Rebuilds a layer from :meth:`to_dict` output."""
        return cls(
            name=data.get("name", ""),
            curves=[Curve2D.from_dict(c) for c in data.get("curves", [])],
        )

    def __len__(self) -> int:
        return len(self.curves)

    def __iter__(self) -> Iterator[Curve2D]:
        return iter(self.curves)

    def __repr__(self) -> str:
        return f"Layer(name={self.name!r}, n_curves={len(self.curves)})"


class Scene:
    """An ordered collection of :class:`Layer` objects plus optional bounds.

    The scene is the document model that consumers render or export. Layers
    preserve insertion order so an exporter can emit them back-to-front.

    Parameters
    ----------
    bounds : (min_x, min_y, max_x, max_y), optional
        An explicit bounding box. When omitted it is derived from the
        primitives (see :meth:`bounds`).
    name : str, optional
        A label for the whole scene.
    """

    __slots__ = ("_layers", "_bounds", "_name")

    def __init__(
        self,
        bounds: Sequence[float] | None = None,
        *,
        name: str | None = None,
    ) -> None:
        self._layers: dict[str, Layer] = {}
        self._bounds = (
            tuple(float(v) for v in bounds) if bounds is not None else None
        )
        self._name = name

    # -- construction ------------------------------------------------------

    def add(self, curve: Curve2D, *, layer: str = LAYER_CURVE) -> Curve2D:
        """Adds ``curve`` to the named layer (creating it if needed)."""
        self.layer(layer).add(curve)
        return curve

    def extend(
        self, curves: Iterable[Curve2D], *, layer: str = LAYER_CURVE
    ) -> None:
        """Adds every primitive in ``curves`` to the named layer."""
        self.layer(layer).extend(curves)

    def layer(self, name: str, *, create: bool = True) -> Layer:
        """Returns the layer called ``name``.

        Parameters
        ----------
        name : str
            The layer name. The layer is created on first use when ``create``
            is true, so the usual call pattern is ``scene.layer("x").add(c)``.
        create : bool
            When ``False``, a missing layer raises :class:`KeyError` instead
            of being created.

        Raises
        ------
        KeyError
            If the layer does not exist and ``create`` is ``False``.
        """
        if name not in self._layers:
            if not create:
                raise KeyError(f"no such layer: {name!r}")
            self._layers[name] = Layer(name=name)
        return self._layers[name]

    # -- properties --------------------------------------------------------

    @property
    def name(self) -> str | None:
        """The optional label of the scene."""
        return self._name

    @property
    def layer_names(self) -> list[str]:
        """The layer names, in insertion order."""
        return list(self._layers)

    @property
    def layers(self) -> list[Layer]:
        """The layers, in insertion order."""
        return list(self._layers.values())

    # -- queries -----------------------------------------------------------

    def iter_curves(self) -> Iterator[Curve2D]:
        """Yields every primitive in the scene, layer by layer."""
        for layer in self._layers.values():
            yield from layer.curves

    def iter_layer(self, name: str) -> Iterator[Curve2D]:
        """Yields the primitives of one layer (empty when it does not exist)."""
        layer = self._layers.get(name)
        if layer is not None:
            yield from layer.curves

    def has_layer(self, name: str) -> bool:
        """Whether a layer with this name exists and is non-empty."""
        layer = self._layers.get(name)
        return layer is not None and len(layer) > 0

    def levels(self) -> list[int]:
        """The sorted, distinct quadtree levels across every layer."""
        found = {c.level for c in self.iter_curves() if c.level is not None}
        return sorted(found)

    def counts(self) -> dict[str, int]:
        """The number of primitives per layer."""
        return {name: len(layer) for name, layer in self._layers.items()}

    def bounds(self) -> BoundingBox | None:
        """The bounding box of the scene.

        Returns the explicit bounds when one was supplied, otherwise the union
        of every primitive's bounding box. ``None`` is returned only when the
        scene is empty and no explicit bounds were given.
        """
        if self._bounds is not None:
            return self._bounds
        curves = list(self.iter_curves())
        if not curves:
            return None
        xs_min = min(c.bounding_box()[0] for c in curves)
        ys_min = min(c.bounding_box()[1] for c in curves)
        xs_max = max(c.bounding_box()[2] for c in curves)
        ys_max = max(c.bounding_box()[3] for c in curves)
        return (xs_min, ys_min, xs_max, ys_max)

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        """Returns a JSON-serialisable mapping describing the scene.

        The layout is lossless and stable:

            {"name": str | None, "bounds": [x0, y0, x1, y1] | None,
             "layers": [{"name": str, "curves": [...]}, ...]}
        """
        return {
            "name": self._name,
            "bounds": list(self._bounds) if self._bounds is not None else None,
            "layers": [layer.to_dict() for layer in self._layers.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Scene":
        """Rebuilds a scene from :meth:`to_dict` output."""
        if not isinstance(data, dict):
            raise TypeError(
                f"scene data must be a mapping, got {type(data).__name__}"
            )
        scene = cls(bounds=data.get("bounds"), name=data.get("name"))
        for layer_data in data.get("layers", []):
            layer = Layer.from_dict(layer_data)
            scene._layers[layer.name] = layer
        return scene

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialises the scene to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "Scene":
        """Parses a scene from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))

    # -- dunder ------------------------------------------------------------

    def __len__(self) -> int:
        return sum(len(layer) for layer in self._layers.values())

    def __iter__(self) -> Iterator[Curve2D]:
        return self.iter_curves()

    def __contains__(self, name: object) -> bool:
        return name in self._layers

    def __repr__(self) -> str:
        return (
            f"Scene(name={self._name!r}, n_curves={len(self)}, "
            f"layers={self.layer_names})"
        )


# --------------------------------------------------------------------------- #
# Converters into the IR
# --------------------------------------------------------------------------- #

def scene_from_curve(
    curve,
    *,
    layer: str = LAYER_CURVE,
    kind: str | None = None,
    bounds: Sequence[float] | None = None,
) -> Scene:
    """Converts input geometry (a :class:`Curve` or polyline) into a scene.

    Parameters
    ----------
    curve : Curve or sequence of (float, float)
        The geometry. Any object with ``vertices``/``closed`` attributes is
        used directly; a plain sequence is treated as a polyline and its
        closure is detected automatically.
    layer : str
        The layer the geometry is placed on. Defaults to ``"curve"``.
    kind : str, optional
        Overrides the primitive kind. By default a closed geometry becomes
        ``"polygon"`` and an open one ``"polyline"``.
    bounds : (min_x, min_y, max_x, max_y), optional
        Explicit scene bounds.

    Returns
    -------
    Scene
        A scene containing the geometry on a single layer.
    """
    primitive = _as_curve2d(curve, kind=kind)
    scene = Scene(bounds=bounds, name=primitive.name)
    scene.add(primitive, layer=layer)
    return scene


def _as_curve2d(curve, *, kind: str | None = None) -> Curve2D:
    """Coerces ``curve`` (a Curve, Curve2D or plain polyline) to a Curve2D."""
    if isinstance(curve, Curve2D):
        if kind is None or kind == curve.kind:
            return curve
        return Curve2D(
            curve.points,
            closed=curve.closed,
            kind=kind,
            level=curve.level,
            name=curve.name,
        )
    if hasattr(curve, "vertices"):
        return Curve2D.from_curve(curve, kind=kind)
    return Curve2D.from_polyline(curve, kind=kind or KIND_POLYLINE)


def scene_from_rasterized(
    result,
    *,
    curve=None,
    bounding_box: Sequence[float] | None = None,
    curve_layer: str = LAYER_CURVE,
    boundary_layer: str = LAYER_BOUNDARY,
    interior_layer: str = LAYER_INTERIOR,
    name: str | None = None,
) -> Scene:
    """Converts a :class:`RasterizedObject` (and optional input curve) to a scene.

    Each rasterized cell becomes one :class:`Curve2D` of kind ``"boundary"`` or
    ``"interior"``, tagged with its quadtree ``level``. When ``curve`` is
    given, the input geometry is added on the ``curve_layer`` so that a
    consumer can overlay it on the cells.

    Parameters
    ----------
    result : RasterizedObject or any object with corners/sizes/levels/kinds
        The rasterization to convert. Duck typing is used so this module does
        not depend on the package's own container class.
    curve : Curve or sequence of (float, float), optional
        The original geometry, added to the scene when supplied.
    bounding_box : (min_x, min_y, max_x, max_y), optional
        Explicit scene bounds. When omitted, the bounds are derived from the
        cells and the curve.
    curve_layer, boundary_layer, interior_layer : str
        Layer names for the geometry, boundary cells and interior cells.
    name : str, optional
        A label for the scene. Falls back to the curve's ``name``.

    Returns
    -------
    Scene
        A scene with up to three layers: geometry, boundary cells, interior
        cells (in that insertion order).
    """
    corners = getattr(result, "corners", None)
    sizes = getattr(result, "sizes", None)
    levels = getattr(result, "levels", None)
    kinds = getattr(result, "kinds", None)
    if corners is None or sizes is None or levels is None or kinds is None:
        raise TypeError(
            "scene_from_rasterized expects an object with corners, sizes, "
            f"levels and kinds attributes, got {type(result).__name__}"
        )

    scene_name = name
    if scene_name is None and curve is not None:
        scene_name = getattr(curve, "name", None)
    scene = Scene(bounds=bounding_box, name=scene_name)

    if curve is not None:
        scene.add(_as_curve2d(curve), layer=curve_layer)

    for corner, size, level, kind in zip(corners, sizes, levels, kinds):
        normalised = str(kind).lower()
        if normalised == KIND_INTERIOR:
            target = interior_layer
        elif normalised == KIND_BOUNDARY:
            target = boundary_layer
        else:
            raise ValueError(
                f"unknown cell kind {kind!r}; expected 'boundary' or 'interior'"
            )
        scene.add(
            Curve2D.cell(corner, size, kind=normalised, level=level),
            layer=target,
        )

    return scene
