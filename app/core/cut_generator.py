from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Iterable

from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union

from app.core.geometry import EPSILON, transformed_placement_polygon
from app.models.cut_line import CutPath, CutSegment
from app.models.footprint import Footprint
from app.models.panel import Panel
from app.models.placement import Placement

ROUND_DIGITS = 6


@dataclass(frozen=True, slots=True)
class _Segment:
    x1: float
    y1: float
    x2: float
    y2: float

    def is_zero_length(self) -> bool:
        return isclose(self.x1, self.x2, abs_tol=EPSILON) and isclose(
            self.y1,
            self.y2,
            abs_tol=EPSILON,
        )

    def normalized_direction(self) -> "_Segment":
        """Normalize only direction, not geometry.

        This makes identical segments with opposite directions collapse to the same
        LineString after unioning and also keeps output deterministic.
        """
        a = (round(self.x1, ROUND_DIGITS), round(self.y1, ROUND_DIGITS))
        b = (round(self.x2, ROUND_DIGITS), round(self.y2, ROUND_DIGITS))
        if b < a:
            a, b = b, a
        return _Segment(a[0], a[1], b[0], b[1])

    def to_cut_segment(self) -> CutSegment:
        return CutSegment(self.x1, self.y1, self.x2, self.y2)

    def to_linestring(self) -> LineString:
        return LineString([(self.x1, self.y1), (self.x2, self.y2)])


def _is_on_panel_edge(segment: _Segment, panel: Panel) -> bool:
    """Return True when a segment lies on the outer panel boundary.

    Those lines are not useful cutting paths: the panel boundary already exists,
    so drawing/cutting there creates visual noise and may duplicate the board edge.
    """
    x1, y1, x2, y2 = segment.x1, segment.y1, segment.x2, segment.y2

    same_x = isclose(x1, x2, abs_tol=EPSILON)
    same_y = isclose(y1, y2, abs_tol=EPSILON)

    if same_y and (
        isclose(y1, 0.0, abs_tol=EPSILON)
        or isclose(y1, panel.height, abs_tol=EPSILON)
    ):
        return True

    if same_x and (
        isclose(x1, 0.0, abs_tol=EPSILON)
        or isclose(x1, panel.width, abs_tol=EPSILON)
    ):
        return True

    return False


def _segments_from_rect(x1: float, y1: float, x2: float, y2: float) -> list[_Segment]:
    return [
        _Segment(x1, y1, x2, y1),
        _Segment(x2, y1, x2, y2),
        _Segment(x2, y2, x1, y2),
        _Segment(x1, y2, x1, y1),
    ]


def _segments_from_polygon_coords(coords: Iterable[tuple[float, float]]) -> list[_Segment]:
    points = list(coords)
    segments: list[_Segment] = []

    for start, end in zip(points, points[1:]):
        segments.append(_Segment(start[0], start[1], end[0], end[1]))

    return segments


def _clean_segments(
    raw_segments: Iterable[_Segment],
    panel: Panel | None = None,
) -> list[CutSegment]:
    """Remove useless panel-edge cuts and collapse duplicate/overlapping cuts.

    The important bit is using shapely's line union. It removes exact duplicates
    and merges overlapping collinear pieces, so two neighbouring boards do not
    produce two identical cuts on the same line.
    """
    filtered: list[_Segment] = []

    for segment in raw_segments:
        segment = segment.normalized_direction()
        if segment.is_zero_length():
            continue
        if panel is not None and _is_on_panel_edge(segment, panel):
            continue
        filtered.append(segment)

    if not filtered:
        return []

    unioned = unary_union([segment.to_linestring() for segment in filtered])

    if unioned.is_empty:
        return []

    lines: list[LineString]
    if isinstance(unioned, LineString):
        lines = [unioned]
    elif isinstance(unioned, MultiLineString):
        lines = list(unioned.geoms)
    else:
        # GeometryCollection can appear when lines intersect. Keep only line parts.
        lines = [geom for geom in getattr(unioned, "geoms", []) if isinstance(geom, LineString)]

    cleaned: list[_Segment] = []
    for line in lines:
        coords = list(line.coords)
        for start, end in zip(coords, coords[1:]):
            segment = _Segment(start[0], start[1], end[0], end[1]).normalized_direction()
            if segment.is_zero_length():
                continue
            if panel is not None and _is_on_panel_edge(segment, panel):
                continue
            cleaned.append(segment)

    # Final deterministic de-duplication after possible splitting by unary_union.
    unique: dict[tuple[float, float, float, float], _Segment] = {}
    for segment in cleaned:
        key = (segment.x1, segment.y1, segment.x2, segment.y2)
        unique[key] = segment

    result = sorted(unique.values(), key=lambda s: (s.y1, s.x1, s.y2, s.x2))
    return [segment.to_cut_segment() for segment in result]


def _single_cut_path(cut_type: str, segments: list[CutSegment]) -> list[CutPath]:
    if not segments:
        return []
    return [CutPath(cut_type=cut_type, segments=segments, footprint_id=None)]


def generate_straight_cuts(
    placements: list[Placement],
    panel: Panel | None = None,
) -> list[CutPath]:
    """Generate rectangular, axis-aligned cut paths where straight cuts are enough.

    This mode intentionally uses placement bounding boxes. It is useful for
    rectangular boards and for quick panel separation, while `contour` follows the
    actual polygon outline.
    """
    raw_segments: list[_Segment] = []

    for placement in placements:
        raw_segments.extend(
            _segments_from_rect(
                placement.x,
                placement.y,
                placement.x2,
                placement.y2,
            )
        )

    return _single_cut_path(
        "straight",
        _clean_segments(raw_segments, panel=panel),
    )


def generate_contour_cuts(
    placements: list[Placement],
    footprints_by_id: dict[str, Footprint],
    panel: Panel | None = None,
) -> list[CutPath]:
    """Generate contour cuts from the real transformed footprint polygons."""
    raw_segments: list[_Segment] = []

    for placement in placements:
        footprint = footprints_by_id[placement.footprint_id]
        poly = transformed_placement_polygon(footprint, placement)
        raw_segments.extend(_segments_from_polygon_coords(poly.exterior.coords))

    return _single_cut_path(
        "contour",
        _clean_segments(raw_segments, panel=panel),
    )


def generate_cut_paths(
    placements: list[Placement],
    footprints_by_id: dict[str, Footprint],
    mode: str = "none",
    panel: Panel | None = None,
) -> list[CutPath]:
    mode = mode.lower()

    if mode == "none":
        return []

    if mode == "straight":
        return generate_straight_cuts(placements, panel=panel)

    if mode == "contour":
        return generate_contour_cuts(
            placements=placements,
            footprints_by_id=footprints_by_id,
            panel=panel,
        )

    raise ValueError(f"Unsupported cut mode: {mode}")
