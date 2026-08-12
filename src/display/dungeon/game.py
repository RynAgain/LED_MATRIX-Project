"""DungeonGame: one continuous run, floor by floor. Pure state.

Everything the renderer needs is readable from here; everything random
flows through one RNG so runs are seedable in tests.
"""

import math
import random

from . import worldgen
from .constants import (
    PHASE_PLAY, PHASE_DESCEND, PHASE_DEATH, DESCEND_TIME, DEATH_TIME,
    GOLD_TOAST_TIME, T_STAIRS, T_LOCKED, T_DOOR,
)
from .entities import Enemy, Pickup
from .hero import Hero, HeroAI


class DungeonGame:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.depth = 1
        self.phase = PHASE_PLAY
        self.phase_t = 0.0
        self.events = []          # one-frame event strings for sfx/flashes
        self.gold_toast = 0.0
        self.deepest = 1
        self._load_floor(self.depth)

    # -- floor lifecycle -------------------------------------------------------
    def _load_floor(self, depth):
        self.floor = worldgen.generate(depth, self.rng)
        self.hero = getattr(self, "hero", None) or Hero(*self.floor.start)
        self.hero.x, self.hero.y = self.floor.start
        self.hero.has_key = False
        self.hero.heading = 0.0
        self.ai = HeroAI()
        self.enemies = [Enemy(k, x, y) for k, x, y in self.floor.enemy_spawns]
        self.pickups = [Pickup(k, x, y) for k, x, y in self.floor.pickup_spawns]
        if self.floor.key_pos is not None:
            kx, ky = self.floor.key_pos
            self.pickups.append(Pickup("key", kx + 0.5, ky + 0.5))

    def _new_run(self):
        self.depth = 1
        hero = Hero(0, 0)
        self.hero = hero
        self._load_floor(self.depth)

    # -- shared queries ----------------------------------------------------------
    def line_of_sight(self, x0, y0, x1, y1):
        """Coarse ray on the grid; good enough for aggro checks."""
        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(dist * 3))
        for i in range(1, steps):
            t = i / steps
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            if self.floor.blocks_ray(int(x), int(y)):
                return False
        return True

    def touch_doors(self, x, y):
        """Walking into a door starts it opening (locked ones need the key)."""
        tile = (int(x), int(y))
        door = self.floor.doors.get(tile)
        if door is None or door.opening:
            return
        t = self.floor.tile(*tile)
        if t == T_DOOR:
            door.opening = True
            self.events.append("door")
        elif t == T_LOCKED and self.hero.has_key:
            door.opening = True
            self.events.append("unlock")

    def on_enemy_killed(self, enemy):
        self.events.append("kill")
        if self.rng.random() < enemy.gold_chance:
            self.pickups.append(Pickup("gold", enemy.x, enemy.y))

    # -- update ---------------------------------------------------------------------
    def update(self, dt):
        self.events = []
        self.gold_toast = max(0.0, self.gold_toast - dt)

        if self.phase == PHASE_DESCEND:
            self.phase_t += dt
            if self.phase_t >= DESCEND_TIME:
                self.depth += 1
                self.deepest = max(self.deepest, self.depth)
                self._load_floor(self.depth)
                self.phase = PHASE_PLAY
                self.phase_t = 0.0
            return

        if self.phase == PHASE_DEATH:
            self.phase_t += dt
            if self.phase_t >= DEATH_TIME:
                self._new_run()
                self.phase = PHASE_PLAY
                self.phase_t = 0.0
            return

        # PLAY
        for door in self.floor.doors.values():
            door.update(dt)
        self.ai.update(self, dt)
        for e in self.enemies:
            e.update(self, dt, self.rng)
        self.enemies = [e for e in self.enemies if not e.dead]
        self._collect_pickups()

        if self.hero.hp <= 0:
            self.phase = PHASE_DEATH
            self.phase_t = 0.0
            self.events.append("death")
            return

        if self.floor.tile(int(self.hero.x), int(self.hero.y)) == T_STAIRS:
            self.phase = PHASE_DESCEND
            self.phase_t = 0.0
            self.events.append("descend")

    def _collect_pickups(self):
        hero = self.hero
        for p in self.pickups:
            if p.taken:
                continue
            if math.hypot(p.x - hero.x, p.y - hero.y) > 0.55:
                continue
            p.taken = True
            if p.kind == "gold":
                hero.gold += self.rng.randint(3, 9)
                self.gold_toast = GOLD_TOAST_TIME
                self.events.append("gold")
            elif p.kind == "potion":
                hero.potions += 1
                self.events.append("pickup")
            elif p.kind == "key":
                hero.has_key = True
                self.floor.key_pos = None
                self.events.append("key")
        self.pickups = [p for p in self.pickups if not p.taken]
