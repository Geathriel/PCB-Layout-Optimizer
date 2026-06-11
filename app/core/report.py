from app.models.panel import Panel
from app.models.placement import Placement


def calculate_used_area(placements: list[Placement]) -> float:
    return sum(p.area for p in placements)


def calculate_utilization(panel: Panel, placements: list[Placement]) -> float:
    if panel.area == 0:
        return 0.0
    return calculate_used_area(placements) / panel.area * 100.0


def generate_text_report(panel: Panel, placements: list[Placement]) -> str:
    used_area = calculate_used_area(placements)
    utilization = calculate_utilization(panel, placements)

    lines = [
        "=== PCB Layout Report ===",
        f"Panel size: {panel.width} x {panel.height}",
        f"Panel area: {panel.area}",
        f"Placed footprints: {len(placements)}",
        f"Used area: {used_area}",
        f"Utilization: {utilization:.2f}%",
        "",
        "Placements:",
    ]

    if not placements:
        lines.append("  (none)")
    else:
        for index, placement in enumerate(placements, start=1):
            lines.append(
                f"  {index}. {placement.footprint_id} | "
                f"x={placement.x}, y={placement.y}, "
                f"w={placement.width}, h={placement.height}, "
                f"rotated={placement.rotated}"
            )

    return "\n".join(lines)