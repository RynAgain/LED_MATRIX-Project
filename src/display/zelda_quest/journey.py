"""Authored forest journey: purposeful returns reuse cleared areas, never respawn them."""
from dataclasses import dataclass

from .journal import Errand
from .woodland import BROOK, BROOK_ROOM


@dataclass(frozen=True)
class Visit:
    room: int
    arrival: tuple
    exit: tuple = None
    errands: tuple = ()


JOURNEY = (
    Visit(0, (1, 12)),
    Visit(1, (1, 14)),
    Visit(BROOK_ROOM, BROOK.start),
    Visit(2, (1, 10)),
    Visit(3, (1, 14)),
    Visit(2, (15, 10), (1, 10)),
    Visit(1, (12, 7), (1, 14), (
        Errand("spring_spirit", (2, 2), "rescue", label="SPRING"),
        Errand("grove_spirit", (19, 12), "rescue", label="GROVE"),
        Errand("elder_spirit", (12, 8), "rescue", label="ELDER"),
    )),
    Visit(0, (17, 12), (17, 11), (
        Errand("restoration_song", (5, 4), "talk", label="AWAKEN"),
    )),
    Visit(1, (1, 14), (12, 8), (
        Errand("restore_elder_tree", (12, 8), "restore", label="NEW LIFE"),
    )),
    Visit(4, (1, 10)),
    Visit(1, (12, 8), (1, 14)),
    Visit(0, (17, 12), (5, 4), (
        Errand("restore_village", (5, 4), "restore", label="HOME!"),
    )),
)
RETURN_ERRANDS = tuple(errand for visit in JOURNEY for errand in visit.errands)
SPIRIT_TILES = frozenset(
    errand.position for visit in JOURNEY if visit.room == 1
    for errand in visit.errands if errand.kind == "rescue"
)
LOCAL_FIELDS = ("has_key", "chest_open", "gate_open", "sigils_lit", "boss_reinforced", "enemies", "pickups")


def first_visit(room):
    return next(index for index, visit in enumerate(JOURNEY) if visit.room == room)


def departed_rooms(index):
    return list(dict.fromkeys(visit.room for visit in JOURNEY[:index]))
