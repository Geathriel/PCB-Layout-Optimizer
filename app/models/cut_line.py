from dataclasses import dataclass, field


@dataclass(slots=True)
class CutSegment:
    start_x: float
    start_y: float
    end_x: float
    end_y: float


@dataclass(slots=True)
class CutPath:
    cut_type: str  # "straight" albo "contour"
    segments: list[CutSegment] = field(default_factory=list)
    footprint_id: str | None = None