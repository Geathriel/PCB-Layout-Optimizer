from app.core.gcode_generator import generate_contour_gcode
from app.models.footprint import Footprint
from app.models.placement import Placement


def test_generate_contour_gcode_for_rectangle() -> None:
    placements = [Placement(footprint_id="A", x=2, y=3, width=10, height=5)]
    footprints_by_id = {"A": Footprint(id="A", width=10, height=5)}

    gcode = generate_contour_gcode(
        placements=placements,
        footprints_by_id=footprints_by_id,
        cut_z=-1.6,
    )

    assert "G21" in gcode
    assert "G90" in gcode
    assert "G1 Z-1.6" in gcode
    assert "; Board 1: A" in gcode
    assert "X2 Y3" in gcode
    assert "M30" in gcode


def test_generate_contour_gcode_for_custom_shape() -> None:
    placements = [Placement(footprint_id="L1", x=1, y=2, width=12, height=12)]
    footprints_by_id = {
        "L1": Footprint(
            id="L1",
            width=12,
            height=12,
            polygon_points=[(0, 0), (12, 0), (12, 4), (4, 4), (4, 12), (0, 12)],
        ),
    }

    gcode = generate_contour_gcode(
        placements=placements,
        footprints_by_id=footprints_by_id,
        cut_z=-2.0,
    )

    assert "; Board 1: L1" in gcode
    assert "G1 Z-2" in gcode
    assert "X13 Y2" in gcode
    assert "X5 Y14" in gcode


def test_generate_contour_gcode_rejects_unsafe_safe_z() -> None:
    placements = [Placement(footprint_id="A", x=0, y=0, width=10, height=5)]
    footprints_by_id = {"A": Footprint(id="A", width=10, height=5)}

    try:
        generate_contour_gcode(
            placements=placements,
            footprints_by_id=footprints_by_id,
            cut_z=5,
            safe_z=5,
        )
        assert False, "Expected ValueError"
    except ValueError:
        assert True
