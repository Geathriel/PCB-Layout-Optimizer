from dataclasses import dataclass, field

from app.models.panel import Panel
from app.models.footprint import Footprint


@dataclass(slots=True)
class Project:
    panel: Panel
    footprints: list[Footprint] = field(default_factory=list)
    spacing: float = 0.0

    def __post_init__(self) -> None:
        if self.spacing < 0:
            raise ValueError("Project spacing must be >= 0.")
        if not self.footprints:
            raise ValueError("Project must contain at least one footprint.")

        footprint_ids = [fp.id for fp in self.footprints]
        if len(footprint_ids) != len(set(footprint_ids)):
            raise ValueError("Footprint ids must be unique.")