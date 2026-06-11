import json

import pytest

from app.io.json_loader import load_project_from_dict, load_project_from_json
from app.io.json_saver import project_to_dict, save_project_to_json
from app.models.footprint import Footprint
from app.models.panel import Panel
from app.models.project import Project


def test_load_project_from_dict() -> None:
    data = {
        "panel": {
            "width": 100,
            "height": 80,
        },
        "spacing": 2,
        "footprints": [
            {
                "id": "A",
                "width": 20,
                "height": 10,
                "allow_rotation": True,
                "quantity": None,
            }
        ],
    }

    project = load_project_from_dict(data)

    assert project.panel.width == 100
    assert project.panel.height == 80
    assert project.spacing == 2
    assert len(project.footprints) == 1
    assert project.footprints[0].id == "A"
    assert project.footprints[0].polygon_points is None


def test_load_project_from_dict_with_polygon_points() -> None:
    data = {
        "panel": {
            "width": 50,
            "height": 40,
        },
        "footprints": [
            {
                "id": "L1",
                "width": 12,
                "height": 12,
                "polygon_points": [
                    [0, 0],
                    [12, 0],
                    [12, 4],
                    [4, 4],
                    [4, 12],
                    [0, 12],
                ],
            }
        ],
    }

    project = load_project_from_dict(data)

    assert project.footprints[0].polygon_points == [
        (0.0, 0.0),
        (12.0, 0.0),
        (12.0, 4.0),
        (4.0, 4.0),
        (4.0, 12.0),
        (0.0, 12.0),
    ]


def test_load_project_from_dict_defaults_allow_rotation() -> None:
    data = {
        "panel": {
            "width": 50,
            "height": 40,
        },
        "footprints": [
            {
                "id": "B",
                "width": 10,
                "height": 5,
            }
        ],
    }

    project = load_project_from_dict(data)

    assert project.spacing == 0.0
    assert project.footprints[0].allow_rotation is True
    assert project.footprints[0].quantity is None


def test_load_project_from_dict_missing_panel() -> None:
    data = {
        "spacing": 2,
        "footprints": [
            {
                "id": "A",
                "width": 20,
                "height": 10,
            }
        ],
    }

    with pytest.raises(ValueError, match="Missing 'panel'"):
        load_project_from_dict(data)


def test_load_project_from_dict_missing_footprints() -> None:
    data = {
        "panel": {
            "width": 100,
            "height": 80,
        }
    }

    with pytest.raises(ValueError, match="Missing 'footprints'"):
        load_project_from_dict(data)


def test_load_project_from_json(tmp_path) -> None:
    file_path = tmp_path / "project.json"
    data = {
        "panel": {
            "width": 120,
            "height": 90,
        },
        "spacing": 3,
        "footprints": [
            {
                "id": "X",
                "width": 30,
                "height": 15,
                "allow_rotation": False,
                "quantity": 2,
            }
        ],
    }

    file_path.write_text(json.dumps(data), encoding="utf-8")

    project = load_project_from_json(file_path)

    assert project.panel.width == 120
    assert project.panel.height == 90
    assert project.spacing == 3
    assert project.footprints[0].id == "X"
    assert project.footprints[0].allow_rotation is False
    assert project.footprints[0].quantity == 2


def test_load_project_from_json_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_project_from_json("this_file_does_not_exist.json")


def test_project_to_dict() -> None:
    project = Project(
        panel=Panel(width=100, height=80),
        spacing=2,
        footprints=[
            Footprint(id="A", width=20, height=10, allow_rotation=True, quantity=None),
            Footprint(
                id="L1",
                width=12,
                height=12,
                allow_rotation=True,
                quantity=3,
                polygon_points=[(0, 0), (12, 0), (12, 4), (4, 4), (4, 12), (0, 12)],
            ),
        ],
    )

    data = project_to_dict(project)

    assert data["panel"]["width"] == 100
    assert data["panel"]["height"] == 80
    assert data["spacing"] == 2
    assert len(data["footprints"]) == 2
    assert data["footprints"][0]["id"] == "A"
    assert data["footprints"][1]["quantity"] == 3
    assert data["footprints"][1]["polygon_points"] is not None


def test_save_project_to_json(tmp_path) -> None:
    project = Project(
        panel=Panel(width=60, height=40),
        spacing=1.5,
        footprints=[
            Footprint(id="C", width=12, height=8, allow_rotation=True, quantity=5)
        ],
    )

    file_path = tmp_path / "saved_project.json"
    save_project_to_json(project, file_path)

    assert file_path.exists()

    loaded_data = json.loads(file_path.read_text(encoding="utf-8"))
    assert loaded_data["panel"]["width"] == 60
    assert loaded_data["panel"]["height"] == 40
    assert loaded_data["spacing"] == 1.5
    assert loaded_data["footprints"][0]["id"] == "C"


def test_json_round_trip(tmp_path) -> None:
    original_project = Project(
        panel=Panel(width=150, height=100),
        spacing=2.5,
        footprints=[
            Footprint(id="A", width=20, height=10, allow_rotation=True, quantity=None),
            Footprint(
                id="B",
                width=25,
                height=12,
                allow_rotation=False,
                quantity=4,
                polygon_points=[(0, 0), (25, 0), (25, 12), (0, 12)],
            ),
        ],
    )

    file_path = tmp_path / "round_trip_project.json"
    save_project_to_json(original_project, file_path)
    loaded_project = load_project_from_json(file_path)

    assert loaded_project.panel.width == original_project.panel.width
    assert loaded_project.panel.height == original_project.panel.height
    assert loaded_project.spacing == original_project.spacing
    assert len(loaded_project.footprints) == len(original_project.footprints)

    for loaded_fp, original_fp in zip(
        loaded_project.footprints,
        original_project.footprints,
    ):
        assert loaded_fp.id == original_fp.id
        assert loaded_fp.width == original_fp.width
        assert loaded_fp.height == original_fp.height
        assert loaded_fp.allow_rotation == original_fp.allow_rotation
        assert loaded_fp.quantity == original_fp.quantity
        assert loaded_fp.polygon_points == original_fp.polygon_points