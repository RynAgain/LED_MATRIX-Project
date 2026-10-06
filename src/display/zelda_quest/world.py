"""Authored area schema and the unpublished Greenwood mechanics slice."""

from collections import deque
from dataclasses import dataclass

TILES = "#.~=CGRHTVB"
BLOCKED = "#~H"


@dataclass(frozen=True)
class Area:
    name: str
    tiles: tuple
    start: tuple
    spawns: tuple = ()
    theme: int = 0
    chest: tuple = None
    gate: tuple = None
    relic: tuple = None
    gate_approach: tuple = None
    shuffle_enemies: bool = False
    sigils: tuple = ()
    boots: tuple = None
    boss: str = None
    sapling: tuple = None

    def __post_init__(self):
        if not self.tiles or not self.tiles[0] or len({len(row) for row in self.tiles}) != 1:
            raise ValueError("Area must have a rectangular map")
        if any(tile not in TILES for row in self.tiles for tile in row):
            raise ValueError("Unknown map tile")
        if bool(self.gate) != bool(self.gate_approach):
            raise ValueError("A gate needs an approach tile")
        if bool(self.gate) and bool(self.chest) == bool(self.sigils):
            raise ValueError("A gate needs exactly one unlock, a chest or a sigil order")
        if bool(self.chest or self.sigils) and not self.gate:
            raise ValueError("Chest keys and sigils must unlock a gate")
        if bool(self.relic) == bool(self.gate):
            raise ValueError("Area needs exactly one exit objective")
        if bool(self.boss) != bool(self.sapling):
            raise ValueError("A boss needs a reinforcement tile")
        if self.boss and self.boss not in {spawn[0] for spawn in self.spawns}:
            raise ValueError("Boss is never spawned")
        positions = [self.start] + [spawn[1:3] for spawn in self.spawns]
        if len(set(positions)) != len(positions):
            raise ValueError("Overlapping spawns")
        items = [p for p in (self.chest, self.gate, self.relic, self.gate_approach,
                             self.boots, self.sapling) if p] + list(self.sigils)
        if len(set(self.sigils)) != len(self.sigils):
            raise ValueError("Duplicate sigil in the order")
        for position in positions + items:
            x, y = position
            if not (0 <= y < len(self.tiles) and 0 <= x < len(self.tiles[0])):
                raise ValueError("Area landmark is off the map")
            if self.tiles[y][x] in BLOCKED:
                raise ValueError("Area landmark must be on land")
        for sigil in self.sigils:
            if self.tiles[sigil[1]][sigil[0]] != "T":
                raise ValueError("Sigil must stand on a sigil tile")
        if self.boots and self.tiles[self.boots[1]][self.boots[0]] != "B":
            raise ValueError("Boots must stand on a pedestal tile")
        if self.gate and sum(abs(a - b) for a, b in zip(self.gate, self.gate_approach)) != 1:
            raise ValueError("Gate approach must be adjacent")
        found = self.reachable()
        if any(position not in found for position in positions + items if position != self.gate):
            raise ValueError("Area spawn or objective is unreachable")

    def reachable(self, vines=True):
        """Tiles reachable from the start with the gate shut; vines need the boots."""
        passable = BLOCKED if vines else BLOCKED + "V"
        found = {self.start}
        queue = deque(found)
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                cell = (x + dx, y + dy)
                cx, cy = cell
                if (0 <= cy < len(self.tiles) and 0 <= cx < len(self.tiles[0])
                        and self.tiles[cy][cx] not in passable and cell != self.gate
                        and cell not in found):
                    found.add(cell)
                    queue.append(cell)
        return found


# Region one: Greenwood. Village, ordered Lost Woods, then the three-room Forest Shrine.
FOREST_REGION = (
    Area("GREENHOLLOW", (
        "####################",
        "#..................#",
        "#.HHH....HHH.......#",
        "#.HHH....HHH...C...#",
        "#..................#",
        "#....~~~...........#",
        "#....~~~....HHH....#",
        "#...........HHH....#",
        "#.HHH..............#",
        "#.HHH.....####.....#",
        "#.............#....#",
        "#......###....#..G.#",
        "#..................#",
        "####################",
    ), (1, 12), (("slime", 6, 10, 1), ("slime", 8, 7, 1), ("guard", 13, 4, 2)),
        chest=(15, 3), gate=(17, 11), gate_approach=(17, 12)),
    Area("LOST WOODS", (
        "######################",
        "#....T....#.......T..#",
        "#.........#..........#",
        "#..####...#...####...#",
        "#..#......#......#...#",
        "#..#...##########....#",
        "#......#....G...#....#",
        "####.###........###.##",
        "#......#........#....#",
        "#..#...####.#####....#",
        "#..#......#......#...#",
        "#..####...#...####...#",
        "#.........#..........#",
        "#....T....#..........#",
        "#....................#",
        "######################",
    ), (1, 14), (("slime", 8, 12, 1), ("slime", 5, 4, 1), ("guard", 19, 8, 2)),
        gate=(12, 6), gate_approach=(12, 7),
        sigils=((5, 13), (18, 1), (5, 1))),
    Area("ROOT HALL", (
        "##################",
        "#....#......#....#",
        "#....#..B...#....#",
        "#.........#......#",
        "####.#.....#.#####",
        "#......####.....C#",
        "#.##...#..#.##...#",
        "#..#...#..#..#...#",
        "#......#..#......#",
        "#.####....####...#",
        "#..............G.#",
        "##################",
    ), (1, 10), (("guard", 4, 7, 2), ("slime", 9, 8, 1), ("guard", 14, 2, 2)),
        theme=2, boots=(8, 2), chest=(16, 5), gate=(15, 10), gate_approach=(14, 10)),
    Area("VINE COURT", (
        "########################",
        "#.........~............#",
        "#..##.....~.........T..#",
        "#.......T.=............#",
        "#..##.....~...####.....#",
        "#####V#####............#",
        "#.........~............#",
        "#..###....~............#",
        "#.........#######=######",
        "#.....##..~............#",
        "#.....##..~..###.......#",
        "#.........~..###.......#",
        "#.........=............#",
        "#.G.......~..........C.#",
        "#.........~............#",
        "########################",
    ), (1, 14), (("slime", 3, 11, 1), ("guard", 7, 2, 2),
                 ("guard", 16, 5, 2), ("guard", 20, 12, 2)),
        theme=2, chest=(21, 13), gate=(2, 13), gate_approach=(2, 14)),
    Area("TREANT LAIR", (
        "################",
        "#..............#",
        "#..##......##..#",
        "#..............#",
        "#..~...##...~..#",
        "#..............#",
        "#..##......##..#",
        "#..............#",
        "#..~...##...~..#",
        "#...........R..#",
        "#..............#",
        "################",
    ), (1, 10), (("treant", 8, 3, 8), ("sapling", 5, 6, 2)),
        theme=2, relic=(12, 9), boss="treant", sapling=(10, 6)),
)
BOOTS_AREA = next(index for index, area in enumerate(FOREST_REGION) if area.boots)
