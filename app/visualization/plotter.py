from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.patches import Rectangle

from app.core.geometry import transformed_placement_polygon
from app.models.footprint import Footprint
from app.models.panel import Panel
from app.models.placement import Placement


def plot_layout(
    panel: Panel,
    placements: list[Placement],
    footprints_by_id: dict[str, Footprint],
    output_path: str | Path,
    title: str = "PCB Layout",
) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 8))

    panel_rect = Rectangle(
        (0, 0),
        panel.width,
        panel.height,
        fill=False,
        linewidth=2,
    )
    ax.add_patch(panel_rect)

    for placement in placements:
        footprint = footprints_by_id[placement.footprint_id]
        poly = transformed_placement_polygon(footprint, placement)

        x, y = poly.exterior.xy
        points = list(zip(x, y))
        patch = MplPolygon(points, closed=True, fill=False, linewidth=1.5)
        ax.add_patch(patch)

        ax.text(
            placement.x + placement.width / 2,
            placement.y + placement.height / 2,
            placement.footprint_id,
            ha="center",
            va="center",
            fontsize=8,
        )

    ax.set_xlim(0, panel.width)
    ax.set_ylim(0, panel.height)
    ax.set_aspect("equal")
    ax.set_title(title)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.grid(True)

    plt.tight_layout()
    fig.savefig(output_file, dpi=150)
    plt.close(fig)