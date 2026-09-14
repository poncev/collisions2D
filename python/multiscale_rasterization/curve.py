"""Internal curve representation for multiscale rasterization.

A :class:`Curve` is the canonical in-memory representation of the geometry
that is fed to the rasterizer and to the visualization tools. It is
deliberately lightweight: an ordered tuple of vertices plus a small amount of
metadata (an optional name and whether the curve is closed).

The representation is intentionally decoupled from the C++ core. The core
still receives a plain sequence of ``(x, y)`` pairs, so ``Curve`` is a
convenience layer that makes the geometry self-describing and reusable across
the rasterizer, the tests and the plotting helpers.

Examples
--------
>>> square = Curve.rectangle(0.0, 0.0, 10.0, 10.0, name="box")
>>> square.is_closed
True
>>> square.to_polyline()[0] == square.to_polyline()[-1]
True
>>> square.bounding_box()
(0.0, 0.0, 10.0, 10.0)
"""

from __future__ import annotations

import math
from typing import Iterable, Iterator, Sequence

from ._validation import BoundingBox, Point, coerce_point as _coerce_point

__all__ = ["Curve", "Point", "BoundingBox"]


class Curve:
    """An ordered sequence of vertices connected by straight edges.

    Parameters
    ----------
    vertices : iterable of (float, float)
        The vertices of the curve, in order. At least two are required.
    closed : bool, optional
        Whether the last vertex is implicitly connected back to the first.
        Defaults to ``False``.
    name : str, optional
        A human-readable label, used as the default plot title.

    Raises
    ------
    ValueError
        If fewer than two vertices are given, or if any vertex is not a pair
        of finite numbers.
    """

    __slots__ = ("_vertices", "_closed", "_name")

    def __init__(
        self,
        vertices: Iterable[Sequence[float]],
        *,
        closed: bool = False,
        name: str | None = None,
    ) -> None:
        verts = tuple(_coerce_point(v, i) for i, v in enumerate(vertices))
        if len(verts) < 2:
            raise ValueError("a curve needs at least two vertices")
        self._vertices = verts
        self._closed = bool(closed)
        self._name = name

    # -- construction ------------------------------------------------------

    @classmethod
    def from_polyline(
        cls,
        polyline: Iterable[Sequence[float]],
        *,
        name: str | None = None,
    ) -> "Curve":
        """Builds a curve from a polyline, detecting closure automatically.

        A polyline is considered closed when it has at least three vertices
        and its first and last vertices coincide. In that case the duplicated
        closing vertex is dropped and ``closed`` is set to ``True``.
        """
        verts = [_coerce_point(v, i) for i, v in enumerate(polyline)]
        if len(verts) >= 3 and verts[0] == verts[-1]:
            return cls(verts[:-1], closed=True, name=name)
        return cls(verts, closed=False, name=name)

    @classmethod
    def rectangle(
        cls,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        name: str | None = None,
    ) -> "Curve":
        """An axis-aligned rectangle, given by two opposite corners."""
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        return cls(
            [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
            closed=True,
            name=name,
        )

    @classmethod
    def regular_polygon(
        cls,
        center: Sequence[float],
        radius: float,
        n: int,
        *,
        name: str | None = None,
    ) -> "Curve":
        """A regular ``n``-gon inscribed in a circle.

        The first vertex is placed at angle ``0`` and the vertices are ordered
        counter-clockwise.
        """
        if n < 3:
            raise ValueError("a regular polygon needs at least three sides")
        if radius <= 0.0:
            raise ValueError("radius must be positive")
        cx, cy = _coerce_point(center, 0)
        verts = [
            (
                cx + radius * math.cos(2.0 * math.pi * i / n),
                cy + radius * math.sin(2.0 * math.pi * i / n),
            )
            for i in range(n)
        ]
        return cls(verts, closed=True, name=name)

    @classmethod
    def circle(
        cls,
        center: Sequence[float],
        radius: float,
        *,
        n: int = 64,
        name: str | None = None,
    ) -> "Curve":
        """A circle approximated by a regular ``n``-gon."""
        return cls.regular_polygon(center, radius, n, name=name)

    # -- properties --------------------------------------------------------

    @property
    def vertices(self) -> tuple[Point, ...]:
        """The vertices of the curve, without any implicit closing vertex."""
        return self._vertices

    @property
    def closed(self) -> bool:
        """Whether the curve is closed (last vertex connects to the first)."""
        return self._closed

    @property
    def is_closed(self) -> bool:
        """Alias for :attr:`closed`."""
        return self._closed

    @property
    def name(self) -> str | None:
        """The optional human-readable label of the curve."""
        return self._name

    @property
    def n_vertices(self) -> int:
        """The number of stored vertices."""
        return len(self._vertices)

    @property
    def n_edges(self) -> int:
        """The number of edges (one more than open, equal to closed)."""
        return len(self._vertices) if self._closed else len(self._vertices) - 1

    # -- geometry ----------------------------------------------------------

    def edges(self) -> Iterator[tuple[Point, Point]]:
        """Yields the ``(start, end)`` pairs of the curve's edges."""
        verts = self._vertices
        for i in range(len(verts) - 1):
            yield verts[i], verts[i + 1]
        if self._closed:
            yield verts[-1], verts[0]

    def to_polyline(self) -> list[Point]:
        """Returns the vertices as a polyline suitable for the C++ core.

        For a closed curve the first vertex is appended at the end so that the
        polyline explicitly closes the loop (as the core expects).
        """
        verts = list(self._vertices)
        if self._closed and verts[0] != verts[-1]:
            verts.append(verts[0])
        return verts

    def bounding_box(self, padding: float = 0.0) -> BoundingBox:
        """Returns ``(min_x, min_y, max_x, max_y)``, optionally padded."""
        xs = [p[0] for p in self._vertices]
        ys = [p[1] for p in self._vertices]
        return (
            min(xs) - padding,
            min(ys) - padding,
            max(xs) + padding,
            max(ys) + padding,
        )

    def translated(self, dx: float, dy: float) -> "Curve":
        """Returns a copy of the curve shifted by ``(dx, dy)``."""
        return Curve(
            [(x + dx, y + dy) for x, y in self._vertices],
            closed=self._closed,
            name=self._name,
        )

    def scaled(
        self, factor: float, origin: Sequence[float] = (0.0, 0.0)
    ) -> "Curve":
        """Returns a copy of the curve scaled about ``origin``."""
        ox, oy = _coerce_point(origin, 0)
        return Curve(
            [
                (ox + (x - ox) * factor, oy + (y - oy) * factor)
                for x, y in self._vertices
            ],
            closed=self._closed,
            name=self._name,
        )

    # -- serialization -----------------------------------------------------
    #
    # ``Curve`` is the canonical in-memory representation. The methods below
    # convert it to and from plain, JSON-serialisable structures so the
    # geometry can be persisted, shared, or handed to other tools without
    # depending on this package. The dictionary layout is deliberately simple
    # and stable:
    #
    #     {"name": str | None, "closed": bool, "vertices": [[x, y], ...]}

    def to_dict(self) -> dict:
        """Returns a JSON-serialisable ``dict`` describing the curve.

        The returned mapping has the keys ``"name"``, ``"closed"`` and
        ``"vertices"`` (a list of ``[x, y]`` pairs). It is the inverse of
        :meth:`from_dict`.
        """
        return {
            "name": self._name,
            "closed": self._closed,
            "vertices": [[x, y] for x, y in self._vertices],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Curve":
        """Rebuilds a curve from the mapping produced by :meth:`to_dict`.

        Unknown keys are ignored, which keeps the format forward-compatible.
        """
        if not isinstance(data, dict):
            raise TypeError(
                f"curve data must be a mapping, got {type(data).__name__}"
            )
        try:
            vertices = data["vertices"]
        except KeyError as exc:
            raise ValueError("curve data is missing the 'vertices' key") from exc
        return cls(
            vertices,
            closed=bool(data.get("closed", False)),
            name=data.get("name"),
        )

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialises the curve to a JSON string.

        Parameters
        ----------
        indent : int, optional
            Passed through to :func:`json.dumps`; ``None`` produces a compact
            single-line string.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "Curve":
        """Parses a curve from a JSON string produced by :meth:`to_json`."""
        import json

        return cls.from_dict(json.loads(text))

    def to_geojson(self) -> dict:
        """Returns a minimal GeoJSON ``Feature`` for the curve.

        The geometry is a ``LineString`` (or a ``Polygon`` when the curve is
        closed). This is a convenience for interoperability with GIS tooling;
        no coordinate reference system is attached.
        """
        coords = [[x, y] for x, y in self.to_polyline()]
        if self._closed:
            geometry = {"type": "Polygon", "coordinates": [coords]}
        else:
            geometry = {"type": "LineString", "coordinates": coords}
        properties = {"closed": self._closed}
        if self._name is not None:
            properties["name"] = self._name
        return {
            "type": "Feature",
            "properties": properties,
            "geometry": geometry,
        }

    # -- dunder ------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._vertices)

    def __iter__(self) -> Iterator[Point]:
        return iter(self._vertices)

    def __getitem__(self, index):
        return self._vertices[index]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Curve):
            return NotImplemented
        return (
            self._vertices == other._vertices
            and self._closed == other._closed
            and self._name == other._name
        )

    def __hash__(self) -> int:
        return hash((self._vertices, self._closed, self._name))

    def __repr__(self) -> str:
        kind = "closed" if self._closed else "open"
        label = f", name={self._name!r}" if self._name is not None else ""
        return f"Curve({kind}, n_vertices={len(self._vertices)}{label})"