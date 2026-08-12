"""Enemies and pickups. Pure state, no rendering."""

import math

from .constants import ENEMY_STATS, TOUCH_RANGE, HURT_IFRAMES


def _can_walk(fm, x, y):
    return not fm.is_solid(int(x), int(y))


def _try_move(fm, ex, ey, nx, ny):
    """Axis-separated move so entities slide along walls."""
    if _can_walk(fm, nx, ey):
        ex = nx
    if _can_walk(fm, ex, ny):
        ey = ny
    return ex, ey


class Pickup:
    """Something lying on the floor: gold, potion, or the key."""

    def __init__(self, kind, x, y):
        self.kind = kind
        self.x = x
        self.y = y
        self.taken = False


class Enemy:
    """One monster. Behaviour differs by kind but shares the chassis."""

    def __init__(self, kind, x, y):
        self.kind = kind
        hp, speed, damage, aggro, gold_chance = ENEMY_STATS[kind]
        self.x = x
        self.y = y
        self.hp = hp
        self.speed = speed
        self.damage = damage
        self.aggro = aggro
        self.gold_chance = gold_chance
        self.dead = False
        self.flash = 0.0          # white hit-flash timer
        self.anim = 0.0           # animation clock
        self.wander_t = 0.0
        self.wander_dir = 0.0

    def hit(self, damage):
        self.hp -= damage
        self.flash = 0.18
        if self.hp <= 0:
            self.dead = True

    def update(self, game, dt, rng):
        if self.dead:
            return
        self.anim += dt
        self.flash = max(0.0, self.flash - dt)
        hero = game.hero
        dx = hero.x - self.x
        dy = hero.y - self.y
        dist = math.hypot(dx, dy)

        if dist < self.aggro and game.line_of_sight(self.x, self.y,
                                                    hero.x, hero.y):
            ang = math.atan2(dy, dx)
            if self.kind == "bat":
                # Bats weave: a sine wobble perpendicular to the approach.
                ang += math.sin(self.anim * 5.0) * 0.9
            step = self.speed * dt
            nx = self.x + math.cos(ang) * step
            ny = self.y + math.sin(ang) * step
            self.x, self.y = _try_move(game.floor, self.x, self.y, nx, ny)
        else:
            # Idle wander: pick a heading now and then, drift along it.
            self.wander_t -= dt
            if self.wander_t <= 0.0:
                self.wander_t = rng.uniform(1.0, 3.0)
                self.wander_dir = rng.uniform(0, math.tau)
                if rng.random() < 0.4:
                    self.wander_dir = None    # sometimes just stand still
            if self.wander_dir is not None:
                step = self.speed * 0.4 * dt
                nx = self.x + math.cos(self.wander_dir) * step
                ny = self.y + math.sin(self.wander_dir) * step
                moved = _try_move(game.floor, self.x, self.y, nx, ny)
                if moved == (self.x, self.y):
                    self.wander_t = 0.0       # bumped a wall: rethink
                self.x, self.y = moved

        # Touch damage.
        if dist < TOUCH_RANGE and hero.iframes <= 0.0:
            hero.hp -= self.damage
            hero.iframes = HURT_IFRAMES
            hero.hurt_flash = 0.35
