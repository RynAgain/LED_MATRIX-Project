"""Seedable, autonomous sword-and-key adventure state."""

from collections import deque
from dataclasses import dataclass
import random

from .world import Area, BLOCKED

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


LEGACY_AREAS = (
    Area("FOREST", ROOMS[0], (1, 5),
         (("slime", 3, 1, 1), ("slime", 2, 3, 1), ("guard", 6, 3, 2)),
         chest=CHEST, gate=GATE, gate_approach=(6, 4), shuffle_enemies=True),
    Area("TEMPLE", ROOMS[1], (3, 5),
         (("guard", 1, 2, 2), ("guard", 6, 3, 2), ("guardian", 3, 2, 8)),
         theme=1, relic=RELIC),
)


class QuestGame:
    def __init__(self, rng=None, areas=LEGACY_AREAS):
        self.areas = areas
        self.rng = rng or random.Random()
        self.elapsed = 0.0
        self.runs = 0
        self.wins = 0
        self._restart()

    def _restart(self):
        self.runs += 1
        self.hero = Actor(*self.areas[0].start)
        self.rupees = 0
        self.has_key = False
        self.chest_open = False
        self.gate_open = False
        self.has_boots = False
        self._load_room(0)

    def _load_room(self, room):
        self.room = room
        self.phase = "explore"
        self.phase_time = 0.0
        self.swing = 0.0
        self.hero_clock = STEP_TIME
        self.enemy_clock = 0.75
        self.pickups = {}
        self.enemy_turns = 0
        self.sigils_lit = 0
        self.boss_reinforced = False
        self.hero.x, self.hero.y = self.area.start
        self.hero.previous = self.hero.position
        self.hero.motion = 0.0
        positions = [(x, y) for _, x, y, _ in self.area.spawns]
        if self.area.shuffle_enemies:
            self.rng.shuffle(positions)
        self.enemies = [Actor(*position, kind=spawn[0], hp=spawn[3])
                        for position, spawn in zip(positions, self.area.spawns)]

    @property
    def area(self):
        return self.areas[self.room]

    def passable(self, position):
        x, y = position
        if not (0 <= y < len(self.area.tiles) and 0 <= x < len(self.area.tiles[0])):
            return False
        tile = self.area.tiles[y][x]
        if tile in BLOCKED or (tile == "V" and not self.has_boots):
            return False
        return position != self.area.gate or self.gate_open

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

    @property
    def boss(self):
        return next((e for e in self.enemies if e.kind == self.area.boss), None)

    @property
    def boss_armored(self):
        """The treant's bark holds while any sapling is still rooted."""
        return self.boss is not None and any(e.kind == "sapling" for e in self.enemies)

    @property
    def next_sigil(self):
        sigils = self.area.sigils
        return sigils[self.sigils_lit] if self.sigils_lit < len(sigils) else None

    def _wrong_sigils(self):
        return {sigil for index, sigil in enumerate(self.area.sigils) if index > self.sigils_lit}

    def _set_phase(self, phase, seconds):
        self.phase = phase
        self.phase_time = seconds

    def _strike(self, enemy):
        self.hero.facing = (enemy.x - self.hero.x, enemy.y - self.hero.y)
        self.swing = 0.20
        if enemy is self.boss and self.boss_armored:
            enemy.flash = 0.18
            return
        enemy.hp -= 1
        enemy.flash = 0.18
        if enemy is self.boss and enemy.hp <= 4 and not self.boss_reinforced:
            self._reinforce()
        if enemy.hp <= 0:
            self.enemies.remove(enemy)
            self.pickups[enemy.position] = "heart" if self.hero.hp < MAX_HEARTS else "rupee"

    def _objective(self):
        """Ordered goals: boots first, then the sigil order, the key, then the exit."""
        if self.area.boots and not self.has_boots:
            return self.area.boots
        if self.next_sigil:
            return self.next_sigil
        if self.area.chest and not self.chest_open:
            return self.area.chest
        return self.area.gate or self.area.relic

    def _reinforce(self):
        """At half health the treant roars one sapling back out of the roots."""
        taken = {self.hero.position} | {e.position for e in self.enemies}
        candidates = self.area.reachable() - taken
        candidates = [cell for cell in candidates if self.passable(cell)]
        if not candidates:
            return
        position = min(candidates, key=lambda cell: (distance(cell, self.area.sapling), cell))
        self.enemies.append(Actor(*position, kind="sapling", hp=2))
        self.boss_reinforced = True
        self._set_phase("roar", 0.9)

    def _hero_turn(self):
        occupied = {e.position for e in self.enemies}
        taboo = self._wrong_sigils()
        if self.hero.hp <= 2:
            routes = [self.path(self.hero.position, p, occupied | taboo)
                      for p, kind in self.pickups.items() if kind == "heart"]
            route = min((r for r in routes if r), key=len, default=[])
            if route:
                self.hero.move(route[0])
                return
        threats = [e for e in self.enemies if not (e is self.boss and self.boss_armored)]
        adjacent = [e for e in threats if distance(self.hero.position, e.position) == 1]
        if adjacent:
            self._strike(adjacent[0])
            return
        route = []
        if threats:
            routes = [self.path(self.hero.position, e.position, occupied - {e.position} | taboo)
                      for e in threats]
            routes = [r for r in routes if r]
            route = min(routes, key=len) if routes else []
        elif self.pickups:
            routes = [self.path(self.hero.position, p, taboo) for p in self.pickups]
            route = min((r for r in routes if r), key=len, default=[])
        if not route:
            goal = self._objective()
            if goal == self.area.gate and self.has_key and distance(self.hero.position, goal) == 1:
                self.has_key = False
                self.gate_open = True
            target = self.area.gate_approach if goal == self.area.gate and not self.gate_open else goal
            route = self.path(self.hero.position, target, taboo - {target})
        if route and route[0] not in occupied:
            self.hero.move(route[0])

    def _enemy_turn(self):
        occupied = {e.position for e in self.enemies}
        self.enemy_turns += 1
        for enemy in self.enemies:
            if enemy.kind == "sapling" or distance(enemy.position, self.hero.position) <= 1:
                continue
            if enemy.kind == "treant" and self.enemy_turns % 2:
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
                enemy.cooldown = 0.85 if enemy.kind == "guardian" else 1.05
                if self.hero.flash <= 0 and self.swing <= 0:
                    self.hero.hp = max(0, self.hero.hp - 1)
                    self.hero.flash = 0.65
        if self.hero.hp <= 0:
            self._set_phase("defeat", 2.0)
        elif self.area.boots and self.hero.position == self.area.boots and not self.has_boots:
            self.has_boots = True
            self._set_phase("boots", 1.2)
        elif self.hero.position in self.area.sigils:
            self._touch_sigil(self.area.sigils.index(self.hero.position))
        elif self.area.chest and self.hero.position == self.area.chest and not self.chest_open and not self.enemies:
            self.chest_open = self.has_key = True
            self._set_phase("key", 1.2)
        elif self.area.gate and self.hero.position == self.area.gate and self.gate_open:
            self._set_phase("enter", 0.7)
        elif self.area.relic and self.hero.position == self.area.relic and not self.enemies:
            self.wins += 1
            self._set_phase("victory", 2.5)

    def _touch_sigil(self, index):
        """Sigils must be woken in order; a wrong stone sends the hero back out."""
        if index == self.sigils_lit:
            self.sigils_lit += 1
            self._set_phase("rune", 0.8)
            if self.sigils_lit == len(self.area.sigils):
                self.gate_open = True
        elif index > self.sigils_lit:
            self.sigils_lit = 0
            self.hero.x, self.hero.y = self.area.start
            self.hero.previous = self.hero.position
            self.hero.motion = 0.0
            self._set_phase("lost", 1.2)

    def _phase_expired(self):
        if self.phase == "enter":
            self._load_room(1)
        elif self.phase in ("victory", "defeat"):
            self._restart()
        else:
            self.phase = "explore"

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
                self._phase_expired()
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
