from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, box

from app.models.footprint import Footprint
from app.models.panel import Panel
from app.models.placement import Placement

EPSILON = 1e-9


def rotate_dimensions(width: float, height: float) -> tuple[float, float]:
    if width <= 0 or height <= 0:
        raise ValueError("Width and height must be greater than 0.")
    return height, width


def create_placement(
    footprint_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
    rotated: bool = False,
) -> Placement:
    if rotated:
        width, height = rotate_dimensions(width, height)

    return Placement(
        footprint_id=footprint_id,
        x=x,
        y=y,
        width=width,
        height=height,
        rotated=rotated,
    )


def default_footprint_polygon(footprint: Footprint) -> Polygon:
    return Polygon([
        (0.0, 0.0),
        (footprint.width, 0.0),
        (footprint.width, footprint.height),
        (0.0, footprint.height),
    ])


def footprint_polygon(footprint: Footprint) -> Polygon:
    if footprint.polygon_points is None:
        return default_footprint_polygon(footprint)

    poly = Polygon(footprint.polygon_points)
    if not poly.is_valid:
        poly = poly.buffer(0)

    if poly.is_empty:
        raise ValueError(f"Footprint '{footprint.id}' has an invalid polygon.")

    return poly


def normalized_footprint_polygon(
    footprint: Footprint,
    rotated: bool = False,
    rotation_angle: int | None = None,
) -> Polygon:
    poly = footprint_polygon(footprint)

    min_x, min_y, _, _ = poly.bounds
    poly = translate(poly, xoff=-min_x, yoff=-min_y)

    if rotation_angle is None:
        rotation_angle = 90 if rotated else 0

    angle = int(rotation_angle) % 360
    if angle % 90 != 0:
        raise ValueError("rotation_angle must be one of: 0, 90, 180, 270.")

    if angle:
        poly = rotate(poly, angle, origin=(0, 0), use_radians=False)
        min_x, min_y, _, _ = poly.bounds
        poly = translate(poly, xoff=-min_x, yoff=-min_y)

    return poly


def transformed_placement_polygon(footprint: Footprint, placement: Placement) -> Polygon:
    angle = getattr(placement, "rotation_angle", 90 if placement.rotated else 0)
    poly = normalized_footprint_polygon(footprint, rotation_angle=angle)
    return translate(poly, xoff=placement.x, yoff=placement.y)


def placement_dimensions_from_footprint(
    footprint: Footprint,
    rotated: bool = False,
    rotation_angle: int | None = None,
) -> tuple[float, float]:
    poly = normalized_footprint_polygon(
        footprint,
        rotated=rotated,
        rotation_angle=rotation_angle,
    )
    min_x, min_y, max_x, max_y = poly.bounds
    return max_x - min_x, max_y - min_y


def fits_in_panel(panel: Panel, placement: Placement) -> bool:
    return (
        placement.x >= -EPSILON
        and placement.y >= -EPSILON
        and placement.x2 <= panel.width + EPSILON
        and placement.y2 <= panel.height + EPSILON
    )


def fits_in_panel_with_margin(panel: Panel, placement: Placement, margin: float = 0.0) -> bool:
    if margin < 0:
        raise ValueError("Margin must be >= 0.")

    return (
        placement.x >= margin - EPSILON
        and placement.y >= margin - EPSILON
        and placement.x2 <= panel.width - margin + EPSILON
        and placement.y2 <= panel.height - margin + EPSILON
    )


def rectangles_overlap(a: Placement, b: Placement) -> bool:
    horizontal_overlap = a.x < b.x2 - EPSILON and a.x2 > b.x + EPSILON
    vertical_overlap = a.y < b.y2 - EPSILON and a.y2 > b.y + EPSILON
    return horizontal_overlap and vertical_overlap


def polygons_overlap(poly_a: Polygon, poly_b: Polygon) -> bool:
    return poly_a.intersects(poly_b) and not poly_a.touches(poly_b)


def has_required_spacing_between_polygons(poly_a: Polygon, poly_b: Polygon, spacing: float) -> bool:
    if spacing < 0:
        raise ValueError("Spacing must be >= 0.")

    if polygons_overlap(poly_a, poly_b):
        return False

    if poly_a.touches(poly_b):
        return spacing <= EPSILON

    return poly_a.distance(poly_b) + EPSILON >= spacing


def panel_polygon(panel: Panel, margin: float = 0.0) -> Polygon:
    if margin < 0:
        raise ValueError("Margin must be >= 0.")

    return box(margin, margin, panel.width - margin, panel.height - margin)


def polygon_fits_in_panel(panel: Panel, poly: Polygon, margin: float = 0.0) -> bool:
    allowed = panel_polygon(panel, margin)
    return allowed.buffer(EPSILON).contains(poly) or allowed.buffer(EPSILON).covers(poly)


def placement_area(placement: Placement) -> float:
    return placement.width * placement.height


def is_inside_bounds(
    x: float,
    y: float,
    width: float,
    height: float,
    panel_width: float,
    panel_height: float,
) -> bool:
    if width <= 0 or height <= 0:
        return False
    if x < -EPSILON or y < -EPSILON:
        return False
    return x + width <= panel_width + EPSILON and y + height <= panel_height + EPSILON