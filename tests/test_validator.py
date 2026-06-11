from app.core.geometry import (
    has_required_spacing_between_polygons,
    polygon_fits_in_panel,
    transformed_placement_polygon,
)
from app.core.packer_naive import pack_naive
from app.models.footprint import Footprint
from app.models.panel import Panel
from app.models.project import Project


def test_pack_single_footprint() -> None:
    project = Project(
        panel=Panel(width=100, height=80),
        spacing=0,
        footprints=[
            Footprint(id="A", width=20, height=10)
        ],
    )

    placements = pack_naive(project)

    assert len(placements) > 0


def test_pack_respects_panel_bounds() -> None:
    project = Project(
        panel=Panel(width=50, height=50),
        spacing=0,
        footprints=[
            Footprint(id="A", width=30, height=30)
        ],
    )

    placements = pack_naive(project)

    assert len(placements) == 1


def test_pack_with_spacing_and_edge_margin() -> None:
    project = Project(
        panel=Panel(width=70, height=70),
        spacing=5,
        footprints=[
            Footprint(id="A", width=20, height=20)
        ],
    )

    placements = pack_naive(project)

    assert len(placements) == 4


def test_pack_with_rotation() -> None:
    project = Project(
        panel=Panel(width=20, height=40),
        spacing=5,
        footprints=[
            Footprint(id="A", width=20, height=10, allow_rotation=True, quantity=1)
        ],
    )

    placements = pack_naive(project)

    assert len(placements) == 1
    assert placements[0].rotated is True


def test_pack_empty_when_too_big() -> None:
    project = Project(
        panel=Panel(width=10, height=10),
        spacing=0,
        footprints=[
            Footprint(id="A", width=20, height=20)
        ],
    )

    placements = pack_naive(project)

    assert len(placements) == 0


def test_pack_respects_quantity_limit() -> None:
    project = Project(
        panel=Panel(width=200, height=100),
        spacing=0,
        footprints=[
            Footprint(id="A", width=20, height=10, quantity=3)
        ],
    )

    placements = pack_naive(project)

    assert len(placements) == 3
    assert all(p.footprint_id == "A" for p in placements)


def test_pack_multiple_footprint_types() -> None:
    project = Project(
        panel=Panel(width=100, height=60),
        spacing=2,
        footprints=[
            Footprint(id="A", width=30, height=20, quantity=2),
            Footprint(id="B", width=10, height=10, quantity=4),
        ],
    )

    placements = pack_naive(project)

    ids = [p.footprint_id for p in placements]
    assert "A" in ids
    assert "B" in ids


def test_all_placements_fit_in_panel_with_edge_margin() -> None:
    project = Project(
        panel=Panel(width=120, height=80),
        spacing=2,
        footprints=[
            Footprint(id="A", width=20, height=10, quantity=4),
            Footprint(id="B", width=15, height=15, quantity=3),
        ],
    )

    placements = pack_naive(project)
    footprints_by_id = {fp.id: fp for fp in project.footprints}

    for placement in placements:
        poly = transformed_placement_polygon(footprints_by_id[placement.footprint_id], placement)
        assert polygon_fits_in_panel(project.panel, poly, project.spacing)


def test_no_placements_break_spacing() -> None:
    project = Project(
        panel=Panel(width=120, height=80),
        spacing=2,
        footprints=[
            Footprint(id="A", width=20, height=10, quantity=4),
            Footprint(id="B", width=15, height=15, quantity=3),
        ],
    )

    placements = pack_naive(project)
    footprints_by_id = {fp.id: fp for fp in project.footprints}

    for i in range(len(placements)):
        poly_i = transformed_placement_polygon(footprints_by_id[placements[i].footprint_id], placements[i])
        for j in range(i + 1, len(placements)):
            poly_j = transformed_placement_polygon(footprints_by_id[placements[j].footprint_id], placements[j])
            assert has_required_spacing_between_polygons(poly_i, poly_j, project.spacing)


def test_pack_custom_shape() -> None:
    project = Project(
        panel=Panel(width=40, height=40),
        spacing=2,
        footprints=[
            Footprint(
                id="L1",
                width=12,
                height=12,
                quantity=2,
                polygon_points=[(0, 0), (12, 0), (12, 4), (4, 4), (4, 12), (0, 12)],
            )
        ],
    )

    placements = pack_naive(project)

    assert len(placements) == 2