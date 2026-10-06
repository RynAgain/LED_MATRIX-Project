"""Watchwood reflectors route sunlight through two real shutter sensors."""
from functools import lru_cache

from .world import Area, BLOCKED


WATCHWOOD_ROOM = 7
WATCHWOOD = Area("WATCHWOOD", (
    '################################',
    '#...........#.........#........#',
    '#...........#.........#........#',
    '#...........#.........#........#',
    '#...........#.HHH.....#.....C..#',
    '#...........#.HHH.....#........#',
    '#..HHH......#.HHH.....=........#',
    '#..HHH......#.........#........#',
    '#..HHH......#.........#........#',
    '#...........#.........#..HHHH..#',
    '#...........~.........#..HHHH..#',
    '#...........#.........#..HHHH..#',
    '#...........#.........#........#',
    '#...........#.........#........#',
    '#....HHH....#.........#........#',
    '#....HHH....=..HHH....#.HHH....#',
    '#....HHH....#..HHH....#.HHH....#',
    '#...........#..HHH....#........#',
    '#...........#.........#......G.#',
    '#...........#.........#........#',
    '#...........#.........#........#',
    '################################',
), (3, 18), (("slime", 9, 17, 1), ("guard", 4, 4, 2),
             ("guard", 15, 13, 2), ("slime", 20, 4, 1),
             ("guard", 27, 5, 2), ("slime", 28, 17, 1)),
    chest=(28, 4), gate=(29, 18), gate_approach=(28, 18))

SOURCE = (2, 3)
CONTROLS = ((8, 4), (18, 11))
SENSORS = ((13, 10), (18, 3))
SHUTTERS = ((12, 15), (22, 6))
LABELS = ("SIDE LIT", "TOWER LIT")


def reflectors(stage):
    return {(8, 3): "/" if stage == 0 else "\\", (8, 10): "\\",
            (18, 10): "\\" if stage < 2 else "/"}


@lru_cache(maxsize=3)
def beam_path(stage):
    mirrors = reflectors(stage)
    cell, direction = SOURCE, (1, 0)
    path, seen = [], set()
    while (cell, direction) not in seen:
        seen.add((cell, direction))
        x, y = cell
        if (not 0 <= y < len(WATCHWOOD.tiles) or not 0 <= x < len(WATCHWOOD.tiles[0])
                or WATCHWOOD.tiles[y][x] in "#H"):
            break
        path.append(cell)
        dx, dy = direction
        if mirrors.get(cell) == "/":
            direction = (-dy, -dx)
        elif mirrors.get(cell) == "\\":
            direction = (dy, dx)
        cell = (x + direction[0], y + direction[1])
    return tuple(path)


def watchwood_passable(cell, stage):
    x, y = cell
    if (not 0 <= y < len(WATCHWOOD.tiles) or not 0 <= x < len(WATCHWOOD.tiles[0])
            or WATCHWOOD.tiles[y][x] in BLOCKED):
        return False
    return cell not in SHUTTERS or SENSORS[SHUTTERS.index(cell)] in beam_path(stage)
