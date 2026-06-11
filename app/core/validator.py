from dataclasses import dataclass, field

from app.core.geometry import (
    has_required_spacing_between_polygons,
    polygon_fits_in_panel,
    transformed_placement_polygon,
)
from app.models.placement import Placement
from app.models.project import Project


@dataclass(slots=True)
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.is_valid = False


def validate_project(project: Project) -> ValidationResult:
    result = ValidationResult(is_valid=True)

    if project.panel.width <= 0:
        result.add_error("Panel width must be greater than 0.")

    if project.panel.height <= 0:
        result.add_error("Panel height must be greater than 0.")

    if project.spacing < 0:
        result.add_error("Project spacing must be >= 0.")

    if not project.footprints:
        result.add_error("Project must contain at least one footprint.")

    seen_ids: set[str] = set()
    for index, footprint in enumerate(project.footprints):
        if not footprint.id.strip():
            result.add_error(f"Footprint at index {index} has an empty id.")

        if footprint.id in seen_ids:
            result.add_error(f"Duplicate footprint id detected: {footprint.id}")
        seen_ids.add(footprint.id)

        if footprint.width <= 0:
            result.add_error(f"Footprint '{footprint.id}' width must be greater than 0.")

        if footprint.height <= 0:
            result.add_error(f"Footprint '{footprint.id}' height must be greater than 0.")

        if footprint.quantity is not None and footprint.quantity <= 0:
            result.add_error(
                f"Footprint '{footprint.id}' quantity must be greater than 0 or None."
            )

    return result


def validate_placements(project: Project, placements: list[Placement]) -> ValidationResult:
    result = ValidationResult(is_valid=True)
    footprints_by_id = {footprint.id: footprint for footprint in project.footprints}

    placement_polygons = []
    for index, placement in enumerate(placements):
        footprint = footprints_by_id.get(placement.footprint_id)
        if footprint is None:
            result.add_error(
                f"Placement #{index + 1} references unknown footprint id '{placement.footprint_id}'."
            )
            continue

        poly = transformed_placement_polygon(footprint, placement)
        placement_polygons.append((placement, poly))

        if not polygon_fits_in_panel(project.panel, poly, project.spacing):
            result.add_error(
                f"Placement #{index + 1} ('{placement.footprint_id}') "
                f"does not fit in panel with required edge spacing {project.spacing}."
            )

    for i in range(len(placement_polygons)):
        placement_a, poly_a = placement_polygons[i]
        for j in range(i + 1, len(placement_polygons)):
            placement_b, poly_b = placement_polygons[j]

            if not has_required_spacing_between_polygons(poly_a, poly_b, project.spacing):
                result.add_error(
                    "Required spacing not preserved between "
                    f"#{i + 1} ('{placement_a.footprint_id}') and "
                    f"#{j + 1} ('{placement_b.footprint_id}')."
                )

    _validate_quantities(project, placements, result)

    return result


def _validate_quantities(
    project: Project,
    placements: list[Placement],
    result: ValidationResult,
) -> None:
    quantity_limits = {
        footprint.id: footprint.quantity
        for footprint in project.footprints
        if footprint.quantity is not None
    }

    placed_counts: dict[str, int] = {}
    for placement in placements:
        placed_counts[placement.footprint_id] = placed_counts.get(placement.footprint_id, 0) + 1

    for footprint_id, limit in quantity_limits.items():
        count = placed_counts.get(footprint_id, 0)
        if count > limit:
            result.add_error(
                f"Footprint '{footprint_id}' placed {count} times, exceeding quantity limit {limit}."
            )