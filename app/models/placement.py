from dataclasses import dataclass


@dataclass(slots=True)
class Placement:
    footprint_id: str
    x: float
    y: float
    width: float
    height: float
    rotated: bool = False
    rotation_angle: int = 0

    def __post_init__(self) -> None:
        if not self.footprint_id or not self.footprint_id.strip():
            raise ValueError("Placement footprint_id must not be empty.")
        if self.x < 0:
            raise ValueError("Placement x must be >= 0.")
        if self.y < 0:
            raise ValueError("Placement y must be >= 0.")
        if self.width <= 0:
            raise ValueError("Placement width must be greater than 0.")
        if self.height <= 0:
            raise ValueError("Placement height must be greater than 0.")

        angle = int(self.rotation_angle) % 360
        if angle % 90 != 0:
            raise ValueError("Placement rotation_angle must be one of: 0, 90, 180, 270.")

        # Backward compatibility: older code used rotated=True to mean 90 degrees.
        if self.rotated and angle == 0:
            angle = 90

        self.rotation_angle = angle
        self.rotated = angle % 180 != 0

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return self.width * self.height
