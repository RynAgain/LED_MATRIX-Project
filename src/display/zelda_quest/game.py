"""Seedable, autonomous sword-and-key adventure state."""

from collections import deque
from dataclasses import dataclass
import random

TILE = 8
HUD = 8
WIDTH = HEIGHT = 64
MAX_HEARTS = 5
STEP_TIME = 0.30
DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))
ROOMS = (
    (
        "########",
        "#...~.C#",
        "#.#.~..#",
        "#...=..#",
        "#.#.~#.#",
        "#...~.G#",
        "########",
    ),
    (
        "########",
        "#..R...#",
        "#.#..#.#",
        "#......#",
        "#.#..#.#",
        "#......#",
        "########",
    ),
)
CHEST = (6, 1)
GATE = (6, 5)
RELIC = (3, 1)


@dataclass
class Actor:
    x: int
    y: int
    kind: str = "hero"
    hp: int = MAX_HEARTS
    facing: tuple = (0, -1)
    motion: float = 0.0
    flash: float = 0.0
    cooldown: float = 0.0

    def __post_init__(self):
        self.previous = self.position

    @property
    def position(self):
        return self.x, self.y

    @property
    def screen_position(self):
        fraction = min(1.0, self.motion / STEP_TIME)
        x = self.x + (self.previous[0] - self.x) * fraction
        y = self.y + (self.previous[1] - self.y) * fraction
        return x * TILE + TILE // 2, y * TILE + TILE // 2 + HUD

    def move(self, position):
        self.previous = self.position
        self.facing = (position[0] - self.x, position[1] - self.y)
        self.x, self.y = position
        self.motion = STEP_TIME

    def update(self, dt):
        self.motion = max(0.0, self.motion - dt)
        self.flash = max(0.0, self.flash - dt)
        self.cooldown = max(0.0, self.cooldown - dt)


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class QuestGame:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.elapsed = 0.0
        self.runs = 0
        self.wins = 0
        self._restart()

    def _restart(self):
        self.runs += 1
        self.hero = Actor(1, 5)
        self.rupees = 0
        self.has_key = False
        self.chest_open = False
        self.gate_open = False
        self._load_room(0)

    def _load_room(self, room):
        self.room = room
        self.phase = "explore"
        self.phase_time = 0.0
        self.swing = 0.0
        self.hero_clock = STEP_TIME
        self.enemy_clock = 0.75
        self.pickups = {}
        self.hero.x, self.hero.y = (1, 5) if room == 0 else (3, 5)
        self.hero.previous = self.hero.position
        self.hero.motion = 0.0
        if room == 0:
            positions = [(3, 1), (2, 3), (6, 3)]
            self.rng.shuffle(positions)
            self.enemies = [Actor(*p, kind="slime" if i < 2 else "guard", hp=i // 2 + 1)
                            for i, p in enumerate(positions)]
        else:
            self.enemies = [Actor(1, 2, kind="guard", hp=2),
                            Actor(6, 3, kind="guard", hp=2),
                            Actor(3, 2, kind="guardian", hp=8)]

    def passable(self, position):
        x, y = position
        if not (0 <= y < len(ROOMS[self.room]) and 0 <= x < len(ROOMS[self.room][0])):
            return False
        tile = ROOMS[self.room][y][x]
        return tile not in "#~" and (tile != "G" or self.gate_open)

    def path(self, start, goal, blocked=()):
        if start == goal:
            return []
        blocked = set(blocked)
        queue = deque([start])
        parents = {start: None}
        while queue:
            x, y = queue.popleft()
            for dx, dy in DIRECTIONS:
                cell = (x + dx, y + dy)
                if cell in parents or cell in blocked or not self.passable(cell):
                    continue
                parents[cell] = (x, y)
                if cell == goal:
                    route = [cell]
                    while parents[route[-1]] != start:
                        route.append(parents[route[-1]])
                    return route[::-1]
                queue.append(cell)
        return []

    def _set_phase(self, phase, seconds):
        self.phase = phase
        self.phase_time = seconds

    def _strike(self, enemy):
        self.hero.facing = (enemy.x - self.hero.x, enemy.y - self.hero.y)
        self.swing = 0.20
        enemy.hp -= 1
        enemy.flash = 0.18
        if enemy.hp <= 0:
            self.enemies.remove(enemy)
            self.pickups[enemy.position] = "heart" if self.hero.hp < MAX_HEARTS else "rupee"

    def _hero_turn(self):
        occupied = {e.position for e in self.enemies}
        if self.hero.hp <= 2:
            routes = [self.path(self.hero.position, p, occupied)
                      for p, kind in self.pickups.items() if kind == "heart"]
            route = min((r for r in routes if r), key=len, default=[])
            if route:
                self.hero.move(route[0])
                return
        adjacent = [e for e in self.enemies if distance(self.hero.position, e.position) == 1]
        if adjacent:
            self._strike(adjacent[0])
            return
        if self.enemies:
            routes = [self.path(self.hero.position, e.position, occupied - {e.position})
                      for e in self.enemies]
            routes = [r for r in routes if r]
            route = min(routes, key=len) if routes else []
        elif self.pickups:
            routes = [self.path(self.hero.position, p) for p in self.pickups]
            route = min((r for r in routes if r), key=len, default=[])
        else:
            goal = CHEST if self.room == 0 and not self.chest_open else GATE if self.room == 0 else RELIC
            if goal == GATE and self.has_key and distance(self.hero.position, GATE) == 1:
                self.has_key = False
                self.gate_open = True
            # Approach the locked gate without treating it as walkable.
            target = (6, 4) if goal == GATE and not self.gate_open else goal
            route = self.path(self.hero.position, target)
        if route and route[0] not in occupied:
            self.hero.move(route[0])

    def _enemy_turn(self):
        occupied = {e.position for e in self.enemies}
        for enemy in self.enemies:
            if distance(enemy.position, self.hero.position) <= 1:
                continue
            blocked = occupied - {enemy.position}
            route = self.path(enemy.position, self.hero.position, blocked)
            if route and route[0] != self.hero.position:
                occupied.remove(enemy.position)
                enemy.move(route[0])
                occupied.add(enemy.position)

    def _contacts(self):
        pickup = self.pickups.pop(self.hero.position, None)
        if pickup == "heart":
            self.hero.hp = min(MAX_HEARTS, self.hero.hp + 1)
        elif pickup == "rupee":
            self.rupees += 1
        for enemy in self.enemies:
            if distance(enemy.position, self.hero.position) == 1 and enemy.cooldown <= 0:
                enemy.cooldown = 1.05 if enemy.kind != "guardian" else 0.85
                if self.hero.flash <= 0 and self.swing <= 0:
                    self.hero.hp = max(0, self.hero.hp - 1)
                    self.hero.flash = 0.65
        if self.hero.hp <= 0:
            self._set_phase("defeat", 2.0)
        elif self.room == 0 and self.hero.position == CHEST and not self.chest_open and not self.enemies:
            self.chest_open = self.has_key = True
            self._set_phase("key", 1.2)
        elif self.room == 0 and self.hero.position == GATE and self.gate_open:
            self._set_phase("enter", 0.7)
        elif self.room == 1 and self.hero.position == RELIC and not self.enemies:
            self.wins += 1
            self._set_phase("victory", 2.5)

    def update(self, dt):
        dt = max(0.0, min(dt, 0.1))
        if dt == 0:
            return
        self.elapsed += dt
        self.hero.update(dt)
        for enemy in self.enemies:
            enemy.update(dt)
        self.swing = max(0.0, self.swing - dt)
        if self.phase != "explore":
            self.phase_time -= dt
            if self.phase_time <= 0:
                if self.phase == "enter":
                    self._load_room(1)
                elif self.phase in ("victory", "defeat"):
                    self._restart()
                else:
                    self.phase = "explore"
            return
        self.hero_clock -= dt
        self.enemy_clock -= dt
        if self.hero_clock <= 0:
            self.hero_clock += STEP_TIME
            self._hero_turn()
        if self.enemy_clock <= 0:
            self.enemy_clock += 0.75
            self._enemy_turn()
        self._contacts()
