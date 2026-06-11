import pytest

from app.core.geometry import (
    create_placement,
    default_footprint_polygon,
    fits_in_panel,
    fits_in_panel_with_margin,
    footprint_polygon,
    has_required_spacing_between_polygons,
    is_inside_bounds,
    placement_area,
    placement_dimensions_from_footprint,
    polygon_fits_in_panel,
    polygons_overlap,
    rotate_dimensions,
    transformed_placement_polygon,
)
from app.models.footprint import Footprint
from app.models.panel import Panel
from app.models.placement import Placement


def test_rotate_dimensions() -> None:
    assert rotate_dimensions(20, 10) == (10, 20)


def test_rotate_dimensions_invalid_values() -> None:
    with pytest.raises(ValueError):
        rotate_dimensions(0, 10)

    with pytest.raises(ValueError):
        rotate_dimensions(10, -1)


def test_create_placement_without_rotation() -> None:
    placement = create_placement(
        footprint_id="A",
        x=5,
        y=10,
        width=20,
        height=10,
        rotated=False,
    )

    assert placement.footprint_id == "A"
    assert placement.x == 5
    assert placement.y == 10
    assert placement.width == 20
    assert placement.height == 10
    assert placement.rotated is False


def test_create_placement_with_rotation() -> None:
    placement = create_placement(
        footprint_id="A",
        x=5,
        y=10,
        width=20,
        height=10,
        rotated=True,
    )

    assert placement.width == 10
    assert placement.height == 20
    assert placement.rotated is True


def test_default_footprint_polygon() -> None:
    fp = Footprint(id="A", width=20, height=10)
    poly = default_footprint_polygon(fp)
    assert poly.area == 200


def test_footprint_polygon_custom_shape() -> None:
    fp = Footprint(
        id="L1",
        width=12,
        height=12,
        polygon_points=[(0, 0), (12, 0), (12, 4), (4, 4), (4, 12), (0, 12)],
    )
    poly = footprint_polygon(fp)
    assert poly.area == 80


def test_placement_dimensions_from_custom_shape_rotation() -> None:
    fp = Footprint(
        id="L1",
        width=12,
        height=12,
        polygon_points=[(0, 0), (12, 0), (12, 4), (4, 4), (4, 12), (0, 12)],
    )

    w1, h1 = placement_dimensions_from_footprint(fp, rotated=False)
    w2, h2 = placement_dimensions_from_footprint(fp, rotated=True)

    assert w1 == 12
    assert h1 == 12
    assert w2 == 12
    assert h2 == 12


def test_transformed_placement_polygon() -> None:
    fp = Footprint(id="A", width=10, height=5)
    placement = Placement(footprint_id="A", x=2, y=3, width=10, height=5)
    poly = transformed_placement_polygon(fp, placement)

    assert poly.bounds == (2.0, 3.0, 12.0, 8.0)


def test_fits_in_panel_true() -> None:
    panel = Panel(width=100, height=80)
    placement = Placement(
        footprint_id="A",
        x=10,
        y=10,
        width=20,
        height=15,
    )

    assert fits_in_panel(panel, placement) is True


def test_fits_in_panel_false_when_exceeds_right_edge() -> None:
    panel = Panel(width=100, height=80)
    placement = Placement(
        footprint_id="A",
        x=90,
        y=10,
        width=20,
        height=15,
    )

    assert fits_in_panel(panel, placement) is False


def test_fits_in_panel_with_margin_true() -> None:
    panel = Panel(width=100, height=80)
    placement = Placement(footprint_id="A", x=2, y=2, width=20, height=10)
    assert fits_in_panel_with_margin(panel, placement, 2) is True


def test_fits_in_panel_with_margin_false() -> None:
    panel = Panel(width=100, height=80)
    placement = Placement(footprint_id="A", x=0, y=2, width=20, height=10)
    assert fits_in_panel_with_margin(panel, placement, 2) is False


def test_polygons_overlap_true() -> None:
    fp = Footprint(id="A", width=10, height=10)
    a = Placement(footprint_id="A", x=0, y=0, width=10, height=10)
    b = Placement(footprint_id="A", x=5, y=5, width=10, height=10)

    poly_a = transformed_placement_polygon(fp, a)
    poly_b = transformed_placement_polygon(fp, b)

    assert polygons_overlap(poly_a, poly_b) is True


def test_polygons_overlap_false_when_touching() -> None:
    fp = Footprint(id="A", width=10, height=10)
    a = Placement(footprint_id="A", x=0, y=0, width=10, height=10)
    b = Placement(footprint_id="A", x=10, y=0, width=10, height=10)

    poly_a = transformed_placement_polygon(fp, a)
    poly_b = transformed_placement_polygon(fp, b)

    assert polygons_overlap(poly_a, poly_b) is False


def test_has_required_spacing_between_polygons_true() -> None:
    fp = Footprint(id="A", width=10, height=10)
    a = Placement(footprint_id="A", x=0, y=0, width=10, height=10)
    b = Placement(footprint_id="A", x=12, y=0, width=10, height=10)

    poly_a = transformed_placement_polygon(fp, a)
    poly_b = transformed_placement_polygon(fp, b)

    assert has_required_spacing_between_polygons(poly_a, poly_b, 2) is True


def test_has_required_spacing_between_polygons_false() -> None:
    fp = Footprint(id="A", width=10, height=10)
    a = Placement(footprint_id="A", x=0, y=0, width=10, height=10)
    b = Placement(footprint_id="A", x=11, y=0, width=10, height=10)

    poly_a = transformed_placement_polygon(fp, a)
    poly_b = transformed_placement_polygon(fp, b)

    assert has_required_spacing_between_polygons(poly_a, poly_b, 2) is False


def test_polygon_fits_in_panel_true() -> None:
    panel = Panel(width=100, height=80)
    fp = Footprint(id="A", width=20, height=10)
    placement = Placement(footprint_id="A", x=2, y=2, width=20, height=10)
    poly = transformed_placement_polygon(fp, placement)

    assert polygon_fits_in_panel(panel, poly, margin=2) is True


def test_polygon_fits_in_panel_false() -> None:
    panel = Panel(width=100, height=80)
    fp = Footprint(id="A", width=20, height=10)
    placement = Placement(footprint_id="A", x=0, y=2, width=20, height=10)
    poly = transformed_placement_polygon(fp, placement)

    assert polygon_fits_in_panel(panel, poly, margin=2) is False


def test_placement_area() -> None:
    placement = Placement(footprint_id="A", x=0, y=0, width=12, height=8)
    assert placement_area(placement) == 96


def test_is_inside_bounds_true() -> None:
    assert is_inside_bounds(
        x=10,
        y=10,
        width=20,
        height=15,
        panel_width=100,
        panel_height=80,
    ) is True


def test_is_inside_bounds_false_when_outside() -> None:
    assert is_inside_bounds(
        x=90,
        y=10,
        width=20,
        height=15,
        panel_width=100,
        panel_height=80,
    ) is False


def test_is_inside_bounds_false_for_negative_position() -> None:
    assert is_inside_bounds(
        x=-1,
        y=10,
        width=20,
        height=15,
        panel_width=100,
        panel_height=80,
    ) is False


def test_is_inside_bounds_false_for_invalid_size() -> None:
    assert is_inside_bounds(
        x=0,
        y=0,
        width=0,
        height=10,
        panel_width=100,
        panel_height=80,
    ) is False