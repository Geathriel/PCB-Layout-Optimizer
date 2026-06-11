from dataclasses import dataclass
from typing import Optional


Point = tuple[float, float]


@dataclass(slots=True)
class Footprint:
    id: str
    width: float
    height: float
    allow_rotation: bool = True
    quantity: Optional[int] = None
    polygon_points: Optional[list[Point]] = None

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("Footprint id must not be empty.")
        if self.width <= 0:
            raise ValueError("Footprint width must be greater than 0.")
        if self.height <= 0:
            raise ValueError("Footprint height must be greater than 0.")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("Footprint quantity must be greater than 0 or None.")

        if self.polygon_points is not None:
            if len(self.polygon_points) < 3:
                raise ValueError("polygon_points must contain at least 3 points.")

            for index, point in enumerate(self.polygon_points):
                if not isinstance(point, tuple) or len(point) != 2:
                    raise ValueError(f"polygon point at index {index} must be a tuple (x, y).")

    @property
    def area(self) -> float:
        return self.width * self.height

    def rotated_dimensions(self) -> tuple[float, float]:
        return self.height, self.width

    @property
    def has_custom_shape(self) -> bool:
        return self.polygon_points is not None