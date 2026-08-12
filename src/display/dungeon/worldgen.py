"""Procedural floor generation: rooms, corridors, doors, key, stairs.

The layout contract (pinned by tests) is:
* every floor cell is reachable from the start with all doors open
* the stairs room is guarded by locked doors on every entrance
* the key is reachable WITHOUT crossing a locked door
"""

import random
from collections import deque

from .constants import (
    MAP_W, MAP_H, T_WALL, T_FLOOR, T_DOOR, T_LOCKED, T_STAIRS,
    ENEMY_BASE, ENEMY_PER_FLOOR, ENEMY_CAP,
)


class Door:
    """Shared state for one door tile. open_t slides 0 (shut) to 1 (open)."""

    def __init__(self, locked=False):
        self.locked = locked
        self.open_t = 0.0
        self.opening = False

    @property
    def passable(self):
        return self.open_t > 0.7

    def update(self, dt):
        if self.opening and self.open_t < 1.0:
            self.open_t = min(1.0, self.open_t + dt * 1.8)


class FloorMap:
    """One generated dungeon floor."""

    def __init__(self, depth):
        self.depth = depth
        self.grid = [[T_WALL] * MAP_W for _ in range(MAP_H)]
        self.rooms = []            # (x, y, w, h) rects, interior included
        self.doors = {}            # (x, y) -> Door
        self.start = (0.0, 0.0)    # hero spawn, cell-centre floats
        self.stairs = (0, 0)       # tile coords
        self.key_pos = None        # tile coords or None once collected
        self.torches = set()       # wall cells drawn with the torch texture
        self.enemy_spawns = []     # (kind, x, y)
        self.pickup_spawns = []    # (kind, x, y)

    # -- queries -------------------------------------------------------------
    def tile(self, x, y):
        if 0 <= x < MAP_W and 0 <= y < MAP_H:
            return self.grid[y][x]
        return T_WALL

    def is_solid(self, x, y):
        """Solid for movement: walls always, doors until they slide open."""
        t = self.tile(x, y)
        if t == T_WALL:
            return True
        if t in (T_DOOR, T_LOCKED):
            door = self.doors.get((x, y))
            return door is None or not door.passable
        return False

    def blocks_ray(self, x, y):
        """Solid for rendering: open doors vanish, everything else draws."""
        t = self.tile(x, y)
        if t == T_WALL:
            return True
        if t in (T_DOOR, T_LOCKED):
            door = self.doors.get((x, y))
            return door is None or door.open_t < 1.0
        return False

    def room_of(self, x, y):
        for i, (rx, ry, rw, rh) in enumerate(self.rooms):
            if rx <= x < rx + rw and ry <= y < ry + rh:
                return i
        return None


def _carve_room(fm, rect):
    x, y, w, h = rect
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            fm.grid[yy][xx] = T_FLOOR


def _carve_corridor(fm, x0, y0, x1, y1, rng):
    """L-shaped corridor, horizontal-then-vertical or the other way."""
    if rng.random() < 0.5:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            fm.grid[y0][x] = max(fm.grid[y0][x], T_FLOOR)
        for y in range(min(y0, y1), max(y0, y1) + 1):
            fm.grid[y][x1] = max(fm.grid[y][x1], T_FLOOR)
    else:
        for y in range(min(y0, y1), max(y0, y1) + 1):
            fm.grid[y][x0] = max(fm.grid[y][x0], T_FLOOR)
        for x in range(min(x0, x1), max(x0, x1) + 1):
            fm.grid[y1][x] = max(fm.grid[y1][x], T_FLOOR)


def _room_entrances(fm, room):
    """Floor cells just OUTSIDE the room that connect to its interior."""
    rx, ry, rw, rh = room
    cells = []
    for x in range(rx, rx + rw):
        for y in (ry - 1, ry + rh):
            if fm.tile(x, y) != T_WALL:
                cells.append((x, y))
    for y in range(ry, ry + rh):
        for x in (rx - 1, rx + rw):
            if fm.tile(x, y) != T_WALL:
                cells.append((x, y))
    return cells


def _flood(fm, start, locked_block):
    """Reachable tile set from start; locked doors optionally impassable."""
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in seen:
                continue
            t = fm.tile(nx, ny)
            if t == T_WALL:
                continue
            if locked_block and t == T_LOCKED:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def generate(depth, rng=None):
    """Generate one floor. Retries until the layout contract holds."""
    rng = rng or random.Random()
    for _ in range(60):
        fm = _generate_once(depth, rng)
        if fm is not None:
            return fm
    # Pathological RNG: fall back to one big room, no lock. Always valid.
    fm = FloorMap(depth)
    _carve_room(fm, (2, 2, MAP_W - 4, MAP_H - 4))
    fm.rooms = [(2, 2, MAP_W - 4, MAP_H - 4)]
    fm.start = (4.5, 4.5)
    fm.stairs = (MAP_W - 5, MAP_H - 5)
    fm.grid[MAP_H - 5][MAP_W - 5] = T_STAIRS
    return fm


def _generate_once(depth, rng):
    fm = FloorMap(depth)

    # Rooms: scattered rects, overlap rejected.
    attempts = 0
    while len(fm.rooms) < rng.randint(5, 7) and attempts < 80:
        attempts += 1
        w = rng.randint(4, 7)
        h = rng.randint(4, 7)
        x = rng.randint(1, MAP_W - w - 1)
        y = rng.randint(1, MAP_H - h - 1)
        rect = (x, y, w, h)
        if any(x < rx + rw + 1 and rx < x + w + 1 and
               y < ry + rh + 1 and ry < y + h + 1
               for rx, ry, rw, rh in fm.rooms):
            continue
        fm.rooms.append(rect)
        _carve_room(fm, rect)
    if len(fm.rooms) < 3:
        return None

    # Corridors: chain the rooms, then one extra loop for variety.
    centres = [(rx + rw // 2, ry + rh // 2) for rx, ry, rw, rh in fm.rooms]
    for i in range(1, len(centres)):
        _carve_corridor(fm, *centres[i - 1], *centres[i], rng)
    if len(centres) > 3:
        a, b = rng.sample(range(len(centres)), 2)
        _carve_corridor(fm, *centres[a], *centres[b], rng)

    # Stairs room: the one furthest from room 0.
    sx, sy = centres[0]
    stairs_room = max(range(len(fm.rooms)),
                      key=lambda i: abs(centres[i][0] - sx) +
                      abs(centres[i][1] - sy))
    stx, sty = centres[stairs_room]
    fm.grid[sty][stx] = T_STAIRS
    fm.stairs = (stx, sty)
    fm.start = (centres[0][0] + 0.5, centres[0][1] + 0.5)

    # Lock every entrance of the stairs room.
    entrances = _room_entrances(fm, fm.rooms[stairs_room])
    if not entrances:
        return None
    for (ex, ey) in entrances:
        fm.grid[ey][ex] = T_LOCKED
        fm.doors[(ex, ey)] = Door(locked=True)

    # Plain doors on some other room entrances.
    for i, room in enumerate(fm.rooms):
        if i == stairs_room:
            continue
        for (ex, ey) in _room_entrances(fm, room):
            if fm.tile(ex, ey) == T_FLOOR and rng.random() < 0.35:
                fm.grid[ey][ex] = T_DOOR
                fm.doors[(ex, ey)] = Door(locked=False)

    # Key: in a room that is neither the start nor the stairs room.
    key_rooms = [i for i in range(len(fm.rooms))
                 if i not in (0, stairs_room)]
    key_room = rng.choice(key_rooms) if key_rooms else 0
    rx, ry, rw, rh = fm.rooms[key_room]
    fm.key_pos = (rng.randint(rx + 1, rx + rw - 2),
                  rng.randint(ry + 1, ry + rh - 2))

    # Contract checks.
    start_tile = (int(fm.start[0]), int(fm.start[1]))
    open_world = _flood(fm, start_tile, locked_block=False)
    all_floor = {(x, y) for y in range(MAP_H) for x in range(MAP_W)
                 if fm.tile(x, y) != T_WALL}
    if open_world != all_floor:
        return None
    no_lock = _flood(fm, start_tile, locked_block=True)
    if fm.key_pos not in no_lock:
        return None
    if fm.stairs in no_lock:
        return None       # lock is not actually guarding the stairs

    # Torches: wall cells adjacent to floor, sparse.
    for y in range(MAP_H):
        for x in range(MAP_W):
            if fm.tile(x, y) != T_WALL:
                continue
            if any(fm.tile(x + dx, y + dy) == T_FLOOR
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                if rng.random() < 0.10:
                    fm.torches.add((x, y))

    _populate(fm, depth, rng, stairs_room, key_room, no_lock)
    return fm


def _populate(fm, depth, rng, stairs_room, key_room, no_lock):
    """Enemies and pickups, scaled by depth."""
    kinds = ["slime"]
    if depth >= 2:
        kinds.append("bat")
    if depth >= 3:
        kinds.append("skeleton")
    count = min(ENEMY_CAP, int(ENEMY_BASE + (depth - 1) * ENEMY_PER_FLOOR))

    start_tile = (int(fm.start[0]), int(fm.start[1]))
    spots = [c for c in no_lock
             if fm.tile(*c) == T_FLOOR
             and abs(c[0] - start_tile[0]) + abs(c[1] - start_tile[1]) > 5]
    rng.shuffle(spots)
    for i in range(min(count, len(spots))):
        x, y = spots[i]
        fm.enemy_spawns.append((rng.choice(kinds), x + 0.5, y + 0.5))

    # Pickups: some gold, a potion or two. The key is handled separately.
    loot_spots = spots[count:]
    n_gold = rng.randint(2, 4)
    n_potion = rng.randint(1, 2)
    for i, kind in enumerate(["gold"] * n_gold + ["potion"] * n_potion):
        if i >= len(loot_spots):
            break
        x, y = loot_spots[i]
        fm.pickup_spawns.append((kind, x + 0.5, y + 0.5))
