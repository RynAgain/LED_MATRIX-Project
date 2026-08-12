"""The hero and the little brain that drives them.

The AI is a priority list rather than a planner, because a watchable
crawl needs legible intent: fight what is biting you, grab what is near,
fetch the key, open the way, take the stairs.
"""

import math
from collections import deque

from .constants import (
    HERO_MAX_HP, HERO_SPEED, HERO_TURN, ATTACK_RANGE, ATTACK_ARC,
    ATTACK_COOLDOWN, ATTACK_DAMAGE, POTION_HEAL, MAX_POTIONS, LOW_HP,
    T_LOCKED, T_DOOR, MAP_W, MAP_H,
)


class Hero:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.heading = 0.0
        self.hp = HERO_MAX_HP
        self.gold = 0
        self.potions = 0
        self.has_key = False
        self.iframes = 0.0
        self.hurt_flash = 0.0     # renderer: red vignette
        self.swing = 0.0          # renderer: attack arc, counts down
        self.attack_cd = 0.0


def _angle_diff(a, b):
    return (a - b + math.pi) % math.tau - math.pi


class HeroAI:
    """Drives the hero one decision at a time."""

    def __init__(self):
        self.path = []            # remaining waypoint tiles
        self.goal = None          # ("pickup", obj) / ("stairs",) / ("wander", tile)
        self.replan_t = 0.0
        self.stuck_t = 0.0
        self._last_pos = None

    # -- pathfinding ----------------------------------------------------------
    def _passable(self, game, x, y, with_key):
        t = game.floor.tile(x, y)
        if t == T_LOCKED and not with_key:
            return False
        return not (t == 0)       # walls only; doors open on contact

    def _bfs(self, game, start, targets, with_key):
        """Shortest path to the nearest of ``targets``. Returns tile list."""
        targets = set(targets)
        if not targets:
            return None
        seen = {start: None}
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur in targets:
                path = []
                while cur is not None:
                    path.append(cur)
                    cur = seen[cur]
                return path[::-1]
            x, y = cur
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (x + dx, y + dy)
                if nxt in seen:
                    continue
                if not (0 <= nxt[0] < MAP_W and 0 <= nxt[1] < MAP_H):
                    continue
                if not self._passable(game, nxt[0], nxt[1], with_key):
                    continue
                seen[nxt] = cur
                q.append(nxt)
        return None

    # -- goal selection ---------------------------------------------------------
    def _choose_goal(self, game):
        hero = game.hero
        start = (int(hero.x), int(hero.y))

        # Loot first: nearest reachable pickup (skip potions when full).
        live = [p for p in game.pickups if not p.taken
                and not (p.kind == "potion" and hero.potions >= MAX_POTIONS)]
        if live:
            path = self._bfs(game, start,
                             [(int(p.x), int(p.y)) for p in live],
                             hero.has_key)
            if path:
                return ("loot",), path

        # Then the stairs (via the key, which is a pickup handled above).
        path = self._bfs(game, start, [game.floor.stairs], hero.has_key)
        if path:
            return ("stairs",), path

        # Nothing reachable (waiting on the key): pace the open area.
        return None, None

    # -- per-tick drive -----------------------------------------------------------
    def update(self, game, dt):
        hero = game.hero
        hero.attack_cd = max(0.0, hero.attack_cd - dt)
        hero.swing = max(0.0, hero.swing - dt)
        hero.iframes = max(0.0, hero.iframes - dt)
        hero.hurt_flash = max(0.0, hero.hurt_flash - dt)

        # Emergency swig.
        if hero.hp <= LOW_HP and hero.potions > 0:
            hero.potions -= 1
            hero.hp = min(HERO_MAX_HP, hero.hp + POTION_HEAL)
            game.events.append("potion")

        # Combat beats navigation.
        target = self._nearest_enemy(game, limit=2.6)
        if target is not None:
            self._fight(game, target, dt)
            return

        # Navigation.
        self.replan_t -= dt
        if not self.path or self.replan_t <= 0.0:
            self.goal, path = self._choose_goal(game)
            self.path = path[1:] if path else []
            self.replan_t = 1.5
        self._follow_path(game, dt)

    def _nearest_loot(self, game, limit):
        hero = game.hero
        best, best_d = None, limit
        for p in game.pickups:
            if p.taken:
                continue
            if p.kind == "potion" and hero.potions >= MAX_POTIONS:
                continue
            d = math.hypot(p.x - hero.x, p.y - hero.y)
            if d < best_d:
                best, best_d = p, d
        return best

    def _nearest_enemy(self, game, limit):
        best, best_d = None, limit
        for e in game.enemies:
            if e.dead:
                continue
            d = math.hypot(e.x - game.hero.x, e.y - game.hero.y)
            if d < best_d and game.line_of_sight(game.hero.x, game.hero.y,
                                                 e.x, e.y):
                best, best_d = e, d
        return best

    def _fight(self, game, enemy, dt):
        hero = game.hero
        dx = enemy.x - hero.x
        dy = enemy.y - hero.y
        dist = math.hypot(dx, dy)
        want = math.atan2(dy, dx)
        self._turn_toward(hero, want, dt)

        facing = abs(_angle_diff(want, hero.heading)) < ATTACK_ARC
        if dist > ATTACK_RANGE * 0.85:
            self._step(game, hero.heading, dt)
        if dist <= ATTACK_RANGE and facing and hero.attack_cd <= 0.0:
            enemy.hit(ATTACK_DAMAGE)
            hero.attack_cd = ATTACK_COOLDOWN
            hero.swing = 0.22
            game.events.append("swing")
            if enemy.dead:
                game.on_enemy_killed(enemy)

    def _follow_path(self, game, dt):
        hero = game.hero
        if not self.path:
            # BFS paths are tile-granular, so loot in the CURRENT tile
            # produces an empty path while still sitting outside the
            # pickup radius. Steer at the item itself for the last yard.
            near = self._nearest_loot(game, limit=2.0)
            if near is not None:
                dx, dy = near.x - hero.x, near.y - hero.y
                want = math.atan2(dy, dx)
                self._turn_toward(hero, want, dt)
                if abs(_angle_diff(want, hero.heading)) < 1.2:
                    self._step(game, want, dt)
            return
        tx, ty = self.path[0]
        gx, gy = tx + 0.5, ty + 0.5
        dx, dy = gx - hero.x, gy - hero.y
        if math.hypot(dx, dy) < 0.30:
            self.path.pop(0)
            return
        want = math.atan2(dy, dx)
        self._turn_toward(hero, want, dt)
        # Move only when roughly facing the waypoint: the camera IS the
        # gameplay here, and gliding sideways reads as broken.
        if abs(_angle_diff(want, hero.heading)) < 0.9:
            self._step(game, want, dt)

        # Stuck detector: replan if barely moving.
        pos = (round(hero.x, 2), round(hero.y, 2))
        if self._last_pos == pos:
            self.stuck_t += dt
            if self.stuck_t > 1.0:
                self.path = []
                self.stuck_t = 0.0
        else:
            self.stuck_t = 0.0
        self._last_pos = pos

    def _turn_toward(self, hero, want, dt):
        diff = _angle_diff(want, hero.heading)
        step = HERO_TURN * dt
        if abs(diff) <= step:
            hero.heading = want
        else:
            hero.heading += step if diff > 0 else -step
        hero.heading %= math.tau

    def _step(self, game, ang, dt):
        hero = game.hero
        step = HERO_SPEED * dt
        nx = hero.x + math.cos(ang) * step
        ny = hero.y + math.sin(ang) * step
        # Knock on doors from a bit away so they start sliding early, and
        # wait at a distance where the camera still reads them as doors
        # instead of walking nose-first into a wall of texels.
        ax = hero.x + math.cos(ang) * 0.9
        ay = hero.y + math.sin(ang) * 0.9
        game.touch_doors(ax, ay)
        fm = game.floor
        door = fm.doors.get((int(ax), int(ay)))
        if door is not None and door.opening and not door.passable:
            return
        if not fm.is_solid(int(nx), int(hero.y)):
            hero.x = nx
        if not fm.is_solid(int(hero.x), int(ny)):
            hero.y = ny
