import json
from pathlib import Path
from typing import Any

from app.models.footprint import Footprint
from app.models.panel import Panel
from app.models.project import Project


def _parse_polygon_points(data: Any) -> list[tuple[float, float]] | None:
    if data is None:
        return None

    if not isinstance(data, list):
        raise ValueError("'polygon_points' must be a list.")

    points: list[tuple[float, float]] = []
    for index, item in enumerate(data):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"polygon point at index {index} must contain exactly 2 values.")
        x, y = item
        points.append((float(x), float(y)))

    return points


def load_project_from_dict(data: dict[str, Any]) -> Project:
    if not isinstance(data, dict):
        raise ValueError("Project data must be a dictionary.")

    panel_data = data.get("panel")
    if panel_data is None:
        raise ValueError("Missing 'panel' section in project data.")

    footprints_data = data.get("footprints")
    if footprints_data is None:
        raise ValueError("Missing 'footprints' section in project data.")

    spacing = data.get("spacing", 0.0)

    if not isinstance(panel_data, dict):
        raise ValueError("'panel' must be a dictionary.")

    if not isinstance(footprints_data, list):
        raise ValueError("'footprints' must be a list.")

    panel = Panel(
        width=panel_data["width"],
        height=panel_data["height"],
    )

    footprints = []
    for index, footprint_data in enumerate(footprints_data):
        if not isinstance(footprint_data, dict):
            raise ValueError(f"Footprint at index {index} must be a dictionary.")

        footprint = Footprint(
            id=footprint_data["id"],
            width=footprint_data["width"],
            height=footprint_data["height"],
            allow_rotation=footprint_data.get("allow_rotation", True),
            quantity=footprint_data.get("quantity"),
            polygon_points=_parse_polygon_points(footprint_data.get("polygon_points")),
        )
        footprints.append(footprint)

    return Project(
        panel=panel,
        footprints=footprints,
        spacing=spacing,
    )


def load_project_from_json(path: str | Path) -> Project:
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"Project file does not exist: {file_path}")

    with file_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return load_project_from_dict(data)