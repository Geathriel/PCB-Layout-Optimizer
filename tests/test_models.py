import pytest

from app.models.panel import Panel
from app.models.footprint import Footprint
from app.models.placement import Placement
from app.models.project import Project


def test_panel_area() -> None:
    panel = Panel(width=100, height=80)
    assert panel.area == 8000


def test_panel_invalid_dimensions() -> None:
    with pytest.raises(ValueError):
        Panel(width=0, height=80)

    with pytest.raises(ValueError):
        Panel(width=100, height=-1)


def test_footprint_area() -> None:
    fp = Footprint(id="A", width=20, height=10)
    assert fp.area == 200


def test_footprint_rotated_dimensions() -> None:
    fp = Footprint(id="A", width=20, height=10)
    assert fp.rotated_dimensions() == (10, 20)


def test_footprint_invalid_id() -> None:
    with pytest.raises(ValueError):
        Footprint(id="", width=10, height=10)


def test_footprint_invalid_quantity() -> None:
    with pytest.raises(ValueError):
        Footprint(id="A", width=10, height=10, quantity=0)


def test_footprint_custom_shape_flag() -> None:
    fp = Footprint(
        id="L1",
        width=12,
        height=12,
        polygon_points=[(0, 0), (12, 0), (12, 4), (4, 4), (4, 12), (0, 12)],
    )
    assert fp.has_custom_shape is True


def test_footprint_without_custom_shape_flag() -> None:
    fp = Footprint(id="A", width=10, height=5)
    assert fp.has_custom_shape is False


def test_footprint_invalid_polygon_too_few_points() -> None:
    with pytest.raises(ValueError):
        Footprint(
            id="X",
            width=10,
            height=10,
            polygon_points=[(0, 0), (1, 1)],
        )


def test_footprint_invalid_polygon_point_format() -> None:
    with pytest.raises(ValueError):
        Footprint(
            id="X",
            width=10,
            height=10,
            polygon_points=[(0, 0), (1, 1), 5],  # type: ignore[list-item]
        )


def test_placement_coordinates_and_bounds() -> None:
    placement = Placement(
        footprint_id="A",
        x=5,
        y=10,
        width=20,
        height=15,
        rotated=False,
    )
    assert placement.x2 == 25
    assert placement.y2 == 25
    assert placement.area == 300


def test_placement_invalid_values() -> None:
    with pytest.raises(ValueError):
        Placement(footprint_id="A", x=-1, y=0, width=10, height=10)

    with pytest.raises(ValueError):
        Placement(footprint_id="A", x=0, y=0, width=0, height=10)


def test_project_creation() -> None:
    panel = Panel(width=100, height=80)
    footprints = [
        Footprint(id="A", width=20, height=10),
        Footprint(id="B", width=15, height=15),
    ]
    project = Project(panel=panel, footprints=footprints, spacing=2)
    assert project.spacing == 2
    assert len(project.footprints) == 2


def test_project_requires_footprints() -> None:
    panel = Panel(width=100, height=80)
    with pytest.raises(ValueError):
        Project(panel=panel, footprints=[], spacing=2)


def test_project_spacing_cannot_be_negative() -> None:
    panel = Panel(width=100, height=80)
    footprints = [Footprint(id="A", width=20, height=10)]
    with pytest.raises(ValueError):
        Project(panel=panel, footprints=footprints, spacing=-1)


def test_project_requires_unique_footprint_ids() -> None:
    panel = Panel(width=100, height=80)
    footprints = [
        Footprint(id="A", width=20, height=10),
        Footprint(id="A", width=15, height=15),
    ]
    with pytest.raises(ValueError):
        Project(panel=panel, footprints=footprints, spacing=2)