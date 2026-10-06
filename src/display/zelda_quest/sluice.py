"""Vine Court controls drain crossings without reflooding occupied routes."""

COURT_ROOM = 3
WHEELS = ((8, 3), (20, 2))
CROSSINGS = {(10, 3): 1, (17, 8): 2, (10, 12): 2}
LABELS = ("DRAIN N", "DRAIN S")


def crossing_open(position, stage):
    return stage >= CROSSINGS.get(position, 0)
