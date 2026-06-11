import json
from pathlib import Path
from typing import Any

from app.models.project import Project


def project_to_dict(project: Project) -> dict[str, Any]:
    return {
        "panel": {
            "width": project.panel.width,
            "height": project.panel.height,
        },
        "spacing": project.spacing,
        "footprints": [
            {
                "id": footprint.id,
                "width": footprint.width,
                "height": footprint.height,
                "allow_rotation": footprint.allow_rotation,
                "quantity": footprint.quantity,
                "polygon_points": footprint.polygon_points,
            }
            for footprint in project.footprints
        ],
    }


def save_project_to_json(project: Project, path: str | Path) -> None:
    file_path = Path(path)
    data = project_to_dict(project)

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)