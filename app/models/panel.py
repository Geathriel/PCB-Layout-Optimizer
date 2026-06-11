from dataclasses import dataclass


@dataclass(slots=True)
class Panel:
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("Panel width must be greater than 0.")
        if self.height <= 0:
            raise ValueError("Panel height must be greater than 0.")

    @property
    def area(self) -> float:
        return self.width * self.height