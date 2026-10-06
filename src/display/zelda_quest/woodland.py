"""Authored woodland subareas and their spatial objective dependencies."""
from .world import Area
from .journal import Errand


BROOK_ROOM = 5
BROOK = Area("BROOK", (
    '################################',
    '#..............................#',
    '#.HHHHH....####........#######.#',
    '#.HHHHH....####........#.....#.#',
    '#.HHHHH....####...........C..#.#',
    '#..........####........#.....#.#',
    '#......................#######.#',
    '#............................G.#',
    '#..............................#',
    '#~~~~~~~~~~~~~~~~~~~==~~~~~~~~~#',
    '#~~~~~~~~~~~~~~~.~~~==~~~~~~~~~#',
    '#~~~~~~~~~~~~~~~=~~~==~~~~~~~~~#',
    '#........#.........#...........#',
    '#..HHH...#.........#...........#',
    '#..HHH...#.........#...........#',
    '#........#.........#...........#',
    '#........#.........#...........#',
    '#..............................#',
    '#........#.........#...HHHHH...#',
    '#........#.........#...HHHHH...#',
    '#........#.........#...........#',
    '################################',
), (3, 19), (
    ("guard", 7, 13, 2), ("slime", 13, 16, 1), ("guard", 26, 14, 2),
    ("slime", 10, 4, 1), ("guard", 25, 4, 2),
), chest=(26, 4), gate=(29, 7), gate_approach=(28, 7))
WOODLAND_AREAS = (BROOK,)

BROOK_ERRANDS = (
    Errand("dam_request", (5, 15), "talk", label="DAM BROKE"),
    Errand("bridge_planks", (29, 16), "collect", ("dam_request",), "planks", "PLANKS"),
    Errand("repair_dam", (5, 15), "deliver", ("bridge_planks",), label="DAM FIXED"),
    Errand("bridge_winch", (16, 10), "control", ("repair_dam",), label="BRIDGE UP"),
)
BROOK_CROSSINGS = {(16, 11): 3, **{(x, y): 4 for x in (20, 21) for y in (9, 10, 11)}}


def brook_open(position, stage):
    return stage >= BROOK_CROSSINGS.get(position, 0)
