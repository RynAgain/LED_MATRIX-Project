"""Deterministic root-guardian warning/exposure state, independent of display timing."""
from dataclasses import dataclass

GUARDIAN_HEALTH = 4
GUARDIAN_POSITION = (8, 1)
SAFE_RUNES = ((7, 2), (9, 2))
WARNING_TICKS = 90
EXPOSED_TICKS = 72


@dataclass
class RootPulse:
    mode: str = "dormant"
    ticks: int = 0
    cycle: int = 0

    def __post_init__(self):
        limits = {"dormant": 0, "warning": WARNING_TICKS, "exposed": EXPOSED_TICKS, "cleared": 0}
        if self.mode not in limits or type(self.ticks) is not int or not 0 <= self.ticks <= limits[self.mode]:
            raise ValueError("Invalid root pulse state")
        cycles = {"dormant": (0,), "warning": range(GUARDIAN_HEALTH),
                  "exposed": range(GUARDIAN_HEALTH), "cleared": (GUARDIAN_HEALTH,)}
        if type(self.cycle) is not int or self.cycle not in cycles[self.mode]:
            raise ValueError("Invalid root pulse cycle")
        if self.mode in ("warning", "exposed") and self.ticks == 0:
            raise ValueError("Active root pulse needs remaining ticks")

    @property
    def safe_tile(self):
        return SAFE_RUNES[self.cycle % len(SAFE_RUNES)]

    def warn(self):
        self.mode = "warning"
        self.ticks = WARNING_TICKS

    def tick(self, hero_position):
        if self.mode not in ("warning", "exposed"):
            return None
        self.ticks -= 1
        if self.ticks:
            return None
        if self.mode == "warning":
            if hero_position == self.safe_tile:
                self.mode = "exposed"
                self.ticks = EXPOSED_TICKS
                return "exposed"
            self.warn()
            return "damage"
        self.warn()
        return None

    def struck(self, defeated):
        if self.mode != "exposed":
            raise ValueError("Guardian is shielded")
        self.cycle += 1
        if defeated:
            self.mode = "cleared"
            self.ticks = 0
        else:
            self.warn()
