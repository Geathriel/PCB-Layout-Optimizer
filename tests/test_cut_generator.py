from app.core.cut_generator import (
    generate_contour_cuts,
    generate_cut_paths,
    generate_straight_cuts,
)
from app.models.footprint import Footprint
from app.models.placement import Placement


def test_generate_straight_cuts_for_single_rectangle() -> None:
    placements = [
        Placement(footprint_id="A", x=2, y=3, width=10, height=5),
    ]

    cut_paths = generate_straight_cuts(placements)

    assert len(cut_paths) == 1
    assert cut_paths[0].cut_type == "straight"
    assert len(cut_paths[0].segments) == 4


def test_generate_contour_cuts_for_rectangle() -> None:
    placements = [
        Placement(footprint_id="A", x=2, y=3, width=10, height=5),
    ]
    footprints_by_id = {
        "A": Footprint(id="A", width=10, height=5),
    }

    cut_paths = generate_contour_cuts(placements, footprints_by_id)

    assert len(cut_paths) == 1
    assert cut_paths[0].cut_type == "contour"
    assert len(cut_paths[0].segments) == 4


def test_generate_contour_cuts_for_custom_shape() -> None:
    placements = [
        Placement(footprint_id="L1", x=0, y=0, width=12, height=12),
    ]
    footprints_by_id = {
        "L1": Footprint(
            id="L1",
            width=12,
            height=12,
            polygon_points=[(0, 0), (12, 0), (12, 4), (4, 4), (4, 12), (0, 12)],
        ),
    }

    cut_paths = generate_contour_cuts(placements, footprints_by_id)

    assert len(cut_paths) == 1
    assert cut_paths[0].cut_type == "contour"
    assert len(cut_paths[0].segments) == 6


def test_generate_cut_paths_none_mode() -> None:
    placements = [
        Placement(footprint_id="A", x=0, y=0, width=10, height=10),
    ]
    footprints_by_id = {
        "A": Footprint(id="A", width=10, height=10),
    }

    cut_paths = generate_cut_paths(placements, footprints_by_id, mode="none")

    assert cut_paths == []


def test_generate_cut_paths_invalid_mode() -> None:
    placements = [
        Placement(footprint_id="A", x=0, y=0, width=10, height=10),
    ]
    footprints_by_id = {
        "A": Footprint(id="A", width=10, height=10),
    }

    try:
        generate_cut_paths(placements, footprints_by_id, mode="weird")
        assert False, "Expected ValueError"
    except ValueError:
        assert True

def _segment_key(segment):
    a = (round(segment.start_x, 6), round(segment.start_y, 6))
    b = (round(segment.end_x, 6), round(segment.end_y, 6))
    if b < a:
        a, b = b, a
    return a, b


def test_straight_cuts_do_not_duplicate_shared_edge() -> None:
    from app.models.panel import Panel

    placements = [
        Placement(footprint_id="A", x=0, y=0, width=10, height=10),
        Placement(footprint_id="A", x=10, y=0, width=10, height=10),
    ]

    cut_paths = generate_straight_cuts(placements, panel=Panel(width=30, height=20))
    segments = cut_paths[0].segments
    keys = [_segment_key(segment) for segment in segments]

    shared_edge = ((10, 0), (10, 10))
    assert keys.count(shared_edge) == 1
    assert len(keys) == len(set(keys))


def test_straight_cuts_skip_panel_outer_edge() -> None:
    from app.models.panel import Panel

    placements = [
        Placement(footprint_id="A", x=0, y=0, width=10, height=10),
    ]

    cut_paths = generate_straight_cuts(placements, panel=Panel(width=20, height=20))
    keys = [_segment_key(segment) for segment in cut_paths[0].segments]

    assert ((0, 0), (10, 0)) not in keys
    assert ((0, 0), (0, 10)) not in keys
    assert ((10, 0), (10, 10)) in keys
    assert ((0, 10), (10, 10)) in keys


def test_contour_cuts_do_not_duplicate_shared_edge() -> None:
    from app.models.panel import Panel

    placements = [
        Placement(footprint_id="A", x=0, y=0, width=10, height=10),
        Placement(footprint_id="A", x=10, y=0, width=10, height=10),
    ]
    footprints_by_id = {"A": Footprint(id="A", width=10, height=10)}

    cut_paths = generate_contour_cuts(
        placements,
        footprints_by_id,
        panel=Panel(width=30, height=20),
    )
    keys = [_segment_key(segment) for segment in cut_paths[0].segments]

    shared_edge = ((10, 0), (10, 10))
    assert keys.count(shared_edge) == 1
    assert len(keys) == len(set(keys))


def test_contour_cuts_skip_panel_outer_edge() -> None:
    from app.models.panel import Panel

    placements = [
        Placement(footprint_id="A", x=0, y=0, width=10, height=10),
    ]
    footprints_by_id = {"A": Footprint(id="A", width=10, height=10)}

    cut_paths = generate_contour_cuts(
        placements,
        footprints_by_id,
        panel=Panel(width=20, height=20),
    )
    keys = [_segment_key(segment) for segment in cut_paths[0].segments]

    assert ((0, 0), (10, 0)) not in keys
    assert ((0, 0), (0, 10)) not in keys
    assert ((10, 0), (10, 10)) in keys
    assert ((0, 10), (10, 10)) in keys
