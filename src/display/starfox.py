#!/usr/bin/env python3
"""Star Fox -- AI-driven (demo) or controller-playable (interactive) on 64x64 LED.

A rail-shooter inspired by Star Fox (SNES, 1993). The Arwing flies forward
automatically; the player (or AI) controls lateral movement, fires lasers,
and performs barrel rolls to deflect incoming fire.

Control scheme (INTERACTIVE mode, ``controller is not None``)
-------------------------------------------------------------
- **D-pad / analog LEFT/RIGHT** moves the ship laterally.
- **D-pad UP/DOWN** moves the ship vertically (this is how you aim high/low).
- **A** fires dual lasers (hold for continuous fire).
- **B** barrel-rolls toward the held direction (deflects enemy fire).
- **SELECT (hold)** boosts -- drains the boost meter, regenerates on release.
- **Start + Select** (or hold Start) quits to menu.

Aiming: lasers travel forward in world space; the HUD reticle shows exactly
where they will be at the target's depth. Put the reticle on the enemy.

DEMO mode (``controller is None``) uses the same game logic with an
autopilot AI that dodges, aims, fires, barrel-rolls, and fights bosses.

Scoring:
- Enemy kill: 10 pts x combo multiplier (combo builds on consecutive kills)
- Ring flythrough: 25 pts (GOLD rings also restore one shield)
- Deflect with barrel roll: 5 pts
- Wave cleared: 50 pts
- Boss core hit: 5 pts; boss destroyed: 200 pts
- Colliding with a pylon costs one shield -- dodge them.
"""

import math
import random
import time
import logging
from PIL import Image, ImageDraw

from src.display._shared import (
    should_stop,
    read_direction,
    safe_rumble,
    show_banner,
)
from src.display._fonts import _draw_text, _text_width
from src.input import Button, EventType, wants_quit

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
CX, CY = WIDTH // 2, HEIGHT // 2
FPS = 30
FRAME_INTERVAL = 1.0 / FPS
HORIZON_Y = 26

# ---------------------------------------------------------------------------
# Stage themes
# ---------------------------------------------------------------------------
STAGES = [
    {"name": "CORNERIA", "sky_top": (5, 5, 30), "sky_bottom": (15, 10, 50),
     "ground_a": (20, 70, 20), "ground_b": (12, 50, 12),
     "grid": (35, 160, 35), "horizon": (60, 40, 100), "mountain": (25, 18, 50)},
    {"name": "SECTOR Y", "sky_top": (2, 2, 15), "sky_bottom": (8, 8, 30),
     "ground_a": (30, 30, 50), "ground_b": (20, 20, 35),
     "grid": (60, 60, 120), "horizon": (40, 40, 80), "mountain": (20, 20, 40)},
    {"name": "VENOM", "sky_top": (20, 2, 2), "sky_bottom": (40, 10, 5),
     "ground_a": (60, 25, 15), "ground_b": (40, 15, 8),
     "grid": (180, 60, 30), "horizon": (100, 40, 20), "mountain": (50, 15, 10)},
    {"name": "AQUAS", "sky_top": (2, 10, 25), "sky_bottom": (5, 20, 45),
     "ground_a": (15, 50, 60), "ground_b": (8, 35, 45),
     "grid": (30, 140, 160), "horizon": (20, 80, 100), "mountain": (10, 35, 50)},
]

# Colors
SHIP_BODY = (220, 220, 240)
SHIP_WING = (180, 190, 210)
SHIP_ACCENT = (50, 110, 220)
SHIP_ENGINE = (255, 140, 40)
SHIP_ENGINE_HOT = (255, 240, 120)
SHIP_SHIELD = (80, 180, 255)
LASER_CORE = (255, 255, 120)
LASER_GLOW = (180, 200, 60)
ENEMY_LASER_COLOR = (255, 60, 60)
RETICLE_NORMAL = (100, 40, 40)
RETICLE_LOCK = (255, 80, 80)
RETICLE_FIRE = (255, 200, 100)
HUD_GREEN = (60, 200, 80)
HUD_DIM = (30, 90, 40)
CALLOUT_COLOR = (255, 255, 200)
EXPLOSION_PALETTE = [
    (255, 255, 220), (255, 240, 140), (255, 200, 60),
    (255, 140, 30), (255, 80, 15), (180, 40, 5), (80, 15, 2),
]
ENEMY_PALETTES = [(220, 50, 50), (50, 160, 255), (255, 200, 40),
                  (180, 50, 200), (50, 200, 100)]


# ===========================================================================
# Game Objects
# ===========================================================================

class _Ship:
    """The player's Arwing."""
    MAX_X = 20         # Ship can reach full lateral range on 64px screen
    MAX_Y_UP = 14      # highest climb (screen_y 34, just under the HUD)
    MAX_Y_DOWN = 8     # lowest drop before clipping the bottom edge

    # Physics: momentum/inertia so the ship feels weighty like real Star Fox
    FRICTION = 0.87    # velocity decay (< 1 = drift after releasing input)
    ACCEL = 0.4        # how fast input accelerates the ship
    MAX_VEL = 2.8      # top sliding speed

    def __init__(self):
        self.x = 0.0       # lateral position
        self.y = 0.0       # vertical position
        self.vx = 0.0      # velocity (momentum)
        self.vy = 0.0
        self.bank = 0.0    # visual bank angle
        self.barrel_roll = 0.0
        self.barrel_rolling = False
        self.roll_dir = 1
        self._roll_cd = 0
        self.shield = 3    # hits before game over
        self.shield_flash = 0
        self.boost = 0.0
        self.boost_meter = 1.0   # SELECT-boost fuel (0..1)
        self.boosting = False
        self.alive = True

    def move(self, dx, dy):
        """Apply input as acceleration (ship has momentum/inertia)."""
        self.vx += dx * self.ACCEL
        self.vy += dy * self.ACCEL
        self.vx = max(-self.MAX_VEL, min(self.MAX_VEL, self.vx))
        self.vy = max(-self.MAX_VEL, min(self.MAX_VEL, self.vy))  # Full vertical speed too
        # Bank angle tracks velocity (ship tilts as it slides)
        self.bank = max(-1.5, min(1.5, self.vx * 0.55))

    def do_barrel_roll(self, direction=1):
        if not self.barrel_rolling and self._roll_cd <= 0:
            self.barrel_rolling = True
            self.barrel_roll = 0.0
            self.roll_dir = direction
            self._roll_cd = 45
            return True
        return False

    def take_hit(self):
        """Take damage. Returns True if dead."""
        self.shield -= 1
        self.shield_flash = 8
        if self.shield <= 0:
            self.alive = False
            return True
        return False

    def update(self, frame):
        # Apply velocity to position (momentum)
        self.x += self.vx
        self.y += self.vy
        # Clamp position
        self.x = max(-self.MAX_X, min(self.MAX_X, self.x))
        self.y = max(-self.MAX_Y_UP, min(self.MAX_Y_DOWN, self.y))
        # Friction: velocity decays (gives inertia/drift feel)
        self.vx *= self.FRICTION
        self.vy *= self.FRICTION
        # Very slight gravity pulling ship back toward center (subtle, not aggressive)
        self.vy -= self.y * 0.005
        self.vx -= self.x * 0.003
        # Barrel roll
        if self.barrel_rolling:
            self.barrel_roll += 0.3
            if self.barrel_roll >= math.pi * 2:
                self.barrel_roll = 0.0
                self.barrel_rolling = False
        elif self._roll_cd > 0:
            self._roll_cd -= 1
        if self.shield_flash > 0:
            self.shield_flash -= 1
        # Boost meter: drains while boosting, regenerates otherwise
        if self.boosting and self.boost_meter > 0:
            self.boost_meter = max(0.0, self.boost_meter - 0.02)
            self.boost = 1.0
        else:
            self.boost_meter = min(1.0, self.boost_meter + 0.006)
            self.boost = max(0, self.boost - 0.06)

    @property
    def screen_x(self):
        return CX + int(self.x)

    @property
    def screen_y(self):
        # Ship moves freely across the play area (no forced idle bob)
        return int(HEIGHT - 16 + self.y)

    def draw(self, draw_ctx, frame):
        sx, sy = self.screen_x, self.screen_y
        roll_cos = math.cos(self.barrel_roll * self.roll_dir) if self.barrel_rolling else 1.0
        roll_sin = math.sin(self.barrel_roll * self.roll_dir) if self.barrel_rolling else 0.0

        # Fuselage
        draw_ctx.line([(sx, sy - 6), (sx - 2, sy - 1)], fill=SHIP_BODY)
        draw_ctx.line([(sx, sy - 6), (sx + 2, sy - 1)], fill=SHIP_BODY)
        draw_ctx.line([(sx - 2, sy - 1), (sx, sy + 3)], fill=SHIP_BODY)
        draw_ctx.line([(sx + 2, sy - 1), (sx, sy + 3)], fill=SHIP_BODY)
        draw_ctx.line([(sx - 2, sy - 1), (sx + 2, sy - 1)], fill=SHIP_ACCENT)

        # Wings
        ws = int(11 * roll_cos)
        wy = int(3 * roll_sin)
        bp = int(self.bank * 2.5)
        lt = (sx - ws + bp, sy + 1 + wy)
        rt = (sx + ws + bp, sy + 1 - wy)
        draw_ctx.line([(sx - 3, sy - 2), lt], fill=SHIP_WING)
        draw_ctx.line([lt, (sx - 3, sy + 2)], fill=SHIP_WING)
        draw_ctx.line([(sx + 3, sy - 2), rt], fill=SHIP_WING)
        draw_ctx.line([rt, (sx + 3, sy + 2)], fill=SHIP_WING)
        if abs(roll_cos) > 0.3:
            draw_ctx.point(lt, fill=SHIP_ACCENT)
            draw_ctx.point(rt, fill=SHIP_ACCENT)

        # Engines
        flicker = 0.5 + 0.5 * math.sin(frame * 0.6)
        eng = tuple(min(255, int(c * (flicker + self.boost * 0.4))) for c in SHIP_ENGINE)
        for dx in [-2, 0, 2]:
            if 0 <= sx + dx < WIDTH and 0 <= sy + 4 < HEIGHT:
                draw_ctx.point((sx + dx, sy + 4), fill=eng)
        if 0 <= sy + 5 < HEIGHT:
            draw_ctx.point((sx, sy + 5), fill=tuple(min(255, int(c * flicker)) for c in SHIP_ENGINE_HOT))

        # Barrel roll shield
        if self.barrel_rolling:
            alpha = 0.4 + 0.6 * abs(math.sin(self.barrel_roll * 2))
            sc = tuple(int(c * alpha) for c in SHIP_SHIELD)
            for i in range(8):
                a = self.barrel_roll * 2 + i * math.pi / 4
                tx = int(sx + 7 * math.cos(a))
                ty = int(sy + 4 * math.sin(a))
                if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                    draw_ctx.point((tx, ty), fill=sc)

        # Shield flash
        if self.shield_flash > 0:
            alpha = self.shield_flash / 8.0
            sc = tuple(int(c * alpha) for c in SHIP_SHIELD)
            for i in range(12):
                a = i * math.pi / 6
                tx = int(sx + 6 * math.cos(a))
                ty = int(sy + 4 * math.sin(a))
                if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                    draw_ctx.point((tx, ty), fill=sc)


class _Enemy:
    STRAIGHT = 0
    SINE = 1
    DIVE = 2
    CIRCLE = 3

    def __init__(self, behavior=0, offset=(0, 0), speed_bonus=0.0, fire_scale=1.0):
        self.z = 14.0 + random.uniform(0, 3)
        self.x = random.uniform(-3.0, 3.0) + offset[0]
        self.y = random.uniform(-2.0, 1.5) + offset[1]  # Full vertical spread
        self.speed = random.uniform(0.09, 0.14) + speed_bonus
        self.fire_scale = fire_scale
        self.behavior = behavior
        self.color = random.choice(ENEMY_PALETTES)
        self.phase = random.uniform(0, math.pi * 2)
        self.alive = True
        self._init_x = self.x
        self._init_y = self.y
        self._fire_cd = random.randint(int(40 * fire_scale), int(90 * fire_scale))

    def update(self, frame, speed_mult=1.0):
        if not self.alive:
            return
        self.z -= self.speed * speed_mult
        if self.behavior == self.SINE:
            self.x = self._init_x + math.sin(frame * 0.05 + self.phase) * 1.8
        elif self.behavior == self.DIVE:
            if self.z < 6:
                self.y += 0.04
                self.speed = min(0.22, self.speed * 1.008)
        elif self.behavior == self.CIRCLE:
            t = frame * 0.04 + self.phase
            self.x = self._init_x + math.cos(t) * 1.5
            self.y = self._init_y + math.sin(t) * 0.6
        self._fire_cd -= 1

    def should_fire(self):
        if self._fire_cd <= 0 and self.z < 8 and self.z > 2:
            self._fire_cd = random.randint(int(50 * self.fire_scale),
                                            int(120 * self.fire_scale))
            return True
        return False

    def is_dead(self):
        return self.z < 0.4 or not self.alive

    def screen_pos(self, bank_offset):
        if self.z < 0.5:
            return None
        f = 30.0 / self.z
        return (int(CX + (self.x + bank_offset * 0.006) * f),
                int(CY - 5 + self.y * f))

    def draw(self, draw_ctx, bank_offset):
        if not self.alive:
            return
        c = self.screen_pos(bank_offset)
        if not c:
            return
        brightness = max(0.25, min(1.0, 1.0 - (self.z - 1.0) / 14.0))
        color = tuple(int(ch * brightness) for ch in self.color)
        size = max(2, int(10.0 / self.z))

        nose = (c[0], c[1] - size)
        left = (c[0] - size, c[1] + size // 2)
        right = (c[0] + size, c[1] + size // 2)
        draw_ctx.line([nose, left], fill=color)
        draw_ctx.line([nose, right], fill=color)
        draw_ctx.line([left, right], fill=color)
        if size > 3:
            draw_ctx.line([left, (c[0] - size - size // 2, c[1])], fill=color)
            draw_ctx.line([right, (c[0] + size + size // 2, c[1])], fill=color)
        if size > 2:
            draw_ctx.point((c[0], c[1] + size // 2 + 2), fill=tuple(min(255, int(ch * 1.4)) for ch in color))
        draw_ctx.point(c, fill=(255, 255, 255))


class _Obstacle:
    def __init__(self, kind="ring"):
        self.kind = kind
        self.z = 14.0 + random.uniform(0, 2)
        self.x = random.uniform(-2.0, 2.0) if kind in ("ring", "arch") else random.uniform(-3.5, 3.5)
        self.y = 0.0 if kind in ("ring", "arch") else 0.5
        self.speed = 0.13
        self.gold = kind == "ring" and random.random() < 0.25
        if self.gold:
            self.color = (255, 200, 50)   # gold ring: restores one shield
        else:
            self.color = (60, 200, 200) if kind == "ring" else (200, 200, 60) if kind == "arch" else (60, 200, 60)
        self.rotation = random.uniform(0, math.pi * 2)
        self.passed = False

    def update(self, speed_mult=1.0):
        self.z -= self.speed * speed_mult
        self.rotation += 0.04

    def is_dead(self):
        return self.z < 0.3

    def _proj(self, px, py, pz, bank_offset):
        if pz < 0.4:
            return None
        f = 30.0 / pz
        return (int(CX + (px + bank_offset * 0.006) * f), int(CY - 5 + py * f))

    def draw(self, draw_ctx, bank_offset):
        if self.z < 0.5:
            return
        brightness = max(0.2, min(1.0, 1.0 - (self.z - 1.0) / 13.0))
        color = tuple(int(c * brightness) for c in self.color)

        if self.kind == "pylon":
            base = self._proj(self.x, 1.5, self.z, bank_offset)
            top = self._proj(self.x, -1.2, self.z, bank_offset)
            if base and top:
                draw_ctx.line([base, top], fill=color)
                for frac in [0.3, 0.6]:
                    l = self._proj(self.x - 0.4, 1.5 - 2.7 * frac, self.z, bank_offset)
                    r = self._proj(self.x + 0.4, 1.5 - 2.7 * frac, self.z, bank_offset)
                    if l and r:
                        draw_ctx.line([l, r], fill=color)
        elif self.kind == "ring":
            center = self._proj(self.x, self.y, self.z, bank_offset)
            if center:
                radius = max(4, int(18.0 / self.z))
                segs = 12
                pts = []
                for i in range(segs):
                    a = self.rotation + i * math.pi * 2 / segs
                    pts.append((center[0] + int(radius * math.cos(a)),
                                center[1] + int(radius * 0.55 * math.sin(a))))
                for i in range(segs):
                    draw_ctx.line([pts[i], pts[(i + 1) % segs]], fill=color)
        elif self.kind == "arch":
            for side in [-1.5, 1.5]:
                b = self._proj(self.x + side, 1.5, self.z, bank_offset)
                t = self._proj(self.x + side, -1.0, self.z, bank_offset)
                if b and t:
                    draw_ctx.line([b, t], fill=color)
            tl = self._proj(self.x - 1.5, -1.0, self.z, bank_offset)
            tr = self._proj(self.x + 1.5, -1.0, self.z, bank_offset)
            m = self._proj(self.x, -1.5, self.z, bank_offset)
            if tl and tr and m:
                draw_ctx.line([tl, m], fill=color)
                draw_ctx.line([m, tr], fill=color)


class _Laser:
    """Player laser: travels forward in WORLD space from the ship.

    The laser's world line ``(wx, wy)`` is fixed at fire time from the ship's
    position (see :func:`_ship_aim_world`); its depth ``z`` advances each
    frame. An enemy is hit when the laser *crosses* the enemy's depth while
    the world offsets line up -- which is exactly what the HUD reticle shows.
    """
    Z_MAX = 12.0

    def __init__(self, x, y, wx=0.0, wy=0.0):
        self.sx0, self.sy0 = float(x), float(y)
        self.wx, self.wy = wx, wy
        self.z = 1.0
        self.z_prev = 1.0
        self.zspeed = 1.1
        self.life = 1.0
        # Visual endpoint: the laser line projected at max depth
        self._ex = CX + wx * (30.0 / self.Z_MAX)
        self._ey = (CY - 5) + wy * (30.0 / self.Z_MAX)

    def update(self):
        self.z_prev = self.z
        self.z += self.zspeed
        self.zspeed *= 1.05

    @property
    def _t(self):
        return min(1.0, (self.z - 1.0) / (self.Z_MAX - 1.0))

    @property
    def x(self):
        return self.sx0 + (self._ex - self.sx0) * self._t

    @property
    def y(self):
        return self.sy0 + (self._ey - self.sy0) * self._t

    def is_dead(self):
        return self.life <= 0 or self.z >= self.Z_MAX

    def draw(self, draw_ctx):
        x, y = int(self.x), int(self.y)
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            b = max(0.3, 1.0 - self._t * 0.7)
            core = tuple(int(c * b) for c in LASER_CORE)
            glow = tuple(int(c * b * 0.5) for c in LASER_GLOW)
            draw_ctx.point((x, y), fill=core)
            if self._t < 0.5:  # near = longer streak
                if y + 1 < HEIGHT:
                    draw_ctx.point((x, y + 1), fill=core)
                if y + 2 < HEIGHT:
                    draw_ctx.point((x, y + 2), fill=glow)
            elif y + 1 < HEIGHT:
                draw_ctx.point((x, y + 1), fill=glow)


class _EnemyLaser:
    """Enemy shot aimed at (or near) the player's ship at fire time."""

    def __init__(self, x, y, tx=None, ty=None):
        self.x, self.y = float(x), float(y)
        aim_x = tx if tx is not None else CX + random.randint(-15, 15)
        aim_y = ty if ty is not None else HEIGHT + 5
        # Extend the aim line well past the target so shots fly through
        ddx = aim_x - self.x
        ddy = aim_y - self.y
        dist = max(1.0, math.hypot(ddx, ddy))
        self.tx = self.x + ddx / dist * 120.0
        self.ty = self.y + ddy / dist * 120.0
        self.speed = 2.2
        self.life = 1.0

    def update(self):
        dx = self.tx - self.x
        dy = self.ty - self.y
        dist = max(1, math.hypot(dx, dy))
        self.x += (dx / dist) * self.speed
        self.y += (dy / dist) * self.speed
        self.life -= 0.035
        self.speed *= 1.01

    def is_dead(self):
        return self.life <= 0 or self.y > HEIGHT + 2

    def draw(self, draw_ctx):
        x, y = int(self.x), int(self.y)
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            b = max(0.3, self.life)
            draw_ctx.point((x, y), fill=tuple(int(c * b) for c in ENEMY_LASER_COLOR))
            if y - 1 >= 0:
                draw_ctx.point((x, y - 1), fill=tuple(int(c * b * 0.5) for c in ENEMY_LASER_COLOR))


class _Explosion:
    def __init__(self, x, y, size=1.0):
        self.particles = []
        for _ in range(int(12 * size)):
            a = random.uniform(0, math.pi * 2)
            s = random.uniform(0.3, 2.5) * size
            self.particles.append({"x": float(x), "y": float(y),
                                   "vx": math.cos(a) * s, "vy": math.sin(a) * s - 0.4,
                                   "life": random.uniform(0.5, 1.0), "decay": random.uniform(0.03, 0.06)})
        self.flash = 3

    def update(self):
        self.flash = max(0, self.flash - 1)
        for p in self.particles:
            p["x"] += p["vx"]; p["y"] += p["vy"]
            p["vy"] += 0.04; p["vx"] *= 0.95; p["life"] -= p["decay"]

    def is_dead(self):
        return all(p["life"] <= 0 for p in self.particles)

    def draw(self, draw_ctx):
        for p in self.particles:
            if p["life"] <= 0:
                continue
            x, y = int(p["x"]), int(p["y"])
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                idx = min(len(EXPLOSION_PALETTE) - 1, int((1 - p["life"]) * len(EXPLOSION_PALETTE)))
                final = tuple(int(c * max(0.15, p["life"])) for c in EXPLOSION_PALETTE[idx])
                draw_ctx.point((x, y), fill=final)
                if p["life"] > 0.6 and x + 1 < WIDTH:
                    draw_ctx.point((x + 1, y), fill=final)


# ===========================================================================
# Aiming model + boss
# ===========================================================================

LASER_AIM_Z = 6.0  # depth at which the ship's screen position IS the aim point


def _ship_aim_world(ship):
    """World-space lateral/vertical line the ship's lasers travel along.

    Calibrated so that at depth :data:`LASER_AIM_Z` the laser passes through
    the point the ship visually covers -- "the ship is the cursor" holds for
    mid-depth targets, nearer/farther ones need leading via the reticle.
    """
    return ship.x / 5.0, (ship.y + 3.0) / 5.0


def _check_laser_enemy(laser, enemy):
    """True if the laser crossed the enemy's depth close enough to hit."""
    if not enemy.alive or enemy.z > laser.Z_MAX:
        return False
    if not (laser.z_prev <= enemy.z <= laser.z):
        return False
    return (abs(laser.wx - enemy.x) < 0.65
            and abs(laser.wy - enemy.y) < 0.75)


def _check_laser_boss(laser, boss):
    """Return ``"core"``, ``"body"`` or ``None`` for a laser vs the boss."""
    if not boss.alive:
        return None
    if not (laser.z_prev <= boss.z <= laser.z):
        return None
    if (abs(laser.wx - boss.x) < 0.7
            and abs(laser.wy - (boss.y + boss.CORE_DY)) < 0.7):
        return "core"
    if abs(laser.wx - boss.x) < 2.4 and abs(laser.wy - boss.y) < 1.3:
        return "body"
    return None


class _Boss:
    """Every-5th-wave mini-boss: armored wing with a glowing core weak point.

    Body hits spark harmlessly off the armor; only core hits damage it. It
    fires three-shot fans aimed at the ship, faster as its health drops.
    """
    CORE_DY = 0.8  # core hangs below the hull centre (world units)

    def __init__(self, level=1):
        self.level = level
        self.z = 15.0
        self.x = 0.0
        self.y = -0.4
        self.hp = 10 + 4 * level
        self.max_hp = self.hp
        self.state = "approach"
        self.phase = random.uniform(0, math.pi * 2)
        self.alive = True
        self._fire_cd = 60
        self.core_flash = 0
        self.hit_flash = 0

    def update(self, frame, speed_mult=1.0):
        self.phase += 0.03
        if self.state == "approach":
            self.z -= 0.14 * speed_mult
            if self.z <= 6.5:
                self.z = 6.5
                self.state = "fight"
        else:
            self.x = math.sin(self.phase) * 2.0
            self.y = -0.4 + math.sin(self.phase * 1.7) * 0.7
            self.z = 6.5 + math.sin(self.phase * 0.6) * 0.7
        self._fire_cd -= 1
        if self.core_flash > 0:
            self.core_flash -= 1
        if self.hit_flash > 0:
            self.hit_flash -= 1

    def should_fire(self):
        if self.state == "fight" and self._fire_cd <= 0:
            # Fires faster as it takes damage (rage)
            rage = 1.0 - 0.4 * (1.0 - self.hp / self.max_hp)
            self._fire_cd = max(20, int((50 - self.level * 4) * rage))
            return True
        return False

    def take_hit(self):
        self.hp -= 1
        self.core_flash = 4
        self.hit_flash = 2
        if self.hp <= 0:
            self.alive = False

    def screen_pos(self):
        f = 30.0 / self.z
        return (int(CX + self.x * f), int(CY - 5 + self.y * f))

    def core_screen_pos(self):
        f = 30.0 / self.z
        return (int(CX + self.x * f), int(CY - 5 + (self.y + self.CORE_DY) * f))

    def draw(self, draw_ctx, frame):
        cx, cy = self.screen_pos()
        f = 30.0 / self.z
        w = max(6, int(f * 2.2))
        body = (255, 255, 255) if self.hit_flash else (170, 70, 190)
        dark = tuple(c // 2 for c in body)
        # Wing bar + upswept tips
        draw_ctx.line([(cx - w, cy), (cx + w, cy)], fill=body)
        draw_ctx.line([(cx - w, cy + 1), (cx + w, cy + 1)], fill=dark)
        draw_ctx.line([(cx - w, cy), (cx - w + 2, cy - 3)], fill=body)
        draw_ctx.line([(cx + w, cy), (cx + w - 2, cy - 3)], fill=body)
        # Hull
        draw_ctx.rectangle([cx - 2, cy - 3, cx + 2, cy + 2], fill=dark, outline=body)
        # Core weak point (pulsing gold; white when just hit)
        ccx, ccy = self.core_screen_pos()
        pulse = 0.55 + 0.45 * math.sin(frame * 0.25)
        core = ((255, 255, 255) if self.core_flash
                else (int(255 * pulse), int(210 * pulse), 40))
        for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            px, py = ccx + dx, ccy + dy
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                draw_ctx.point((px, py), fill=core)


# ===========================================================================
# Terrain / Stars (visual backdrop)
# ===========================================================================

class _Terrain:
    def __init__(self):
        self.peaks = []
        x = 0
        while x < WIDTH * 3:
            self.peaks.append((x, random.randint(3, 12), random.randint(5, 14)))
            x += self.peaks[-1][2] + random.randint(1, 6)
        self.scroll = 0.0

    def update(self, bank_offset):
        self.scroll += 0.2 + abs(bank_offset) * 0.01

    def draw(self, draw_ctx, stage):
        offset = int(self.scroll) % (WIDTH * 3)
        for px, h, w in self.peaks:
            cx = (px - offset) % (WIDTH * 3) - WIDTH // 2
            if -w - 5 < cx < WIDTH + w + 5:
                draw_ctx.polygon([(cx - w // 2, HORIZON_Y), (cx, HORIZON_Y - h),
                                  (cx + w // 2, HORIZON_Y)], fill=stage["mountain"])


class _StarField:
    def __init__(self):
        self.stars = [{"x": random.uniform(0, WIDTH), "y": random.uniform(0, HORIZON_Y - 1),
                       "speed": 0.05 + random.choice([0, 1, 2]) * 0.1,
                       "bright": 50 + random.choice([0, 1, 2]) * 60} for _ in range(30)]

    def update(self, bank_offset):
        for s in self.stars:
            s["x"] -= s["speed"] + bank_offset * 0.012
            if s["x"] < -1: s["x"] = WIDTH; s["y"] = random.uniform(0, HORIZON_Y - 1)
            elif s["x"] > WIDTH: s["x"] = -1

    def draw(self, draw_ctx):
        for s in self.stars:
            x, y = int(s["x"]), int(s["y"])
            if 0 <= x < WIDTH and 0 <= y < HORIZON_Y:
                b = min(255, s["bright"])
                draw_ctx.point((x, y), fill=(b, b, min(255, b + 20)))


# ===========================================================================
# Autopilot AI (used in demo mode)
# ===========================================================================

class _AI:
    """Plays Star Fox like a skilled human: positions ship over enemies to aim.

    In Star Fox, the ship IS the cursor. Lasers go straight forward from where
    the ship is. So aiming means MOVING THE SHIP onto the enemy's screen
    position, then firing a burst. A good player:
    - Snaps aggressively to the nearest enemy's screen position
    - Fires rapidly while lined up
    - Breaks away to dodge incoming fire (barrel roll)
    - Slides through rings for bonus points
    - Moves with purpose — always heading toward a target
    """

    def __init__(self):
        self._dodge_cd = 0
        self._current_target = None  # screen (x, y) we're sliding toward
        self._on_target_frames = 0   # how many frames we've been lined up
        self._target_switch_cd = 0   # cooldown before picking new target

    def decide(self, ship, enemies, obstacles, enemy_lasers, bank_offset, frame, boss=None):
        """Returns (dx, dy, fire, roll_dir_or_0)."""
        dx, dy = 0.0, 0.0
        fire = False
        roll = 0

        sx = ship.screen_x
        sy = ship.screen_y

        # --- Barrel roll to dodge incoming fire (highest priority) ---
        if self._dodge_cd > 0:
            self._dodge_cd -= 1
        incoming = [el for el in enemy_lasers
                    if el.y > HEIGHT * 0.4 and abs(el.x - sx) < 8]
        if incoming and not ship.barrel_rolling and self._dodge_cd <= 0:
            threat_x = sum(el.x for el in incoming) / len(incoming)
            roll = 1 if threat_x > sx else -1
            self._dodge_cd = 60
            return dx, dy, fire, roll  # Don't aim while rolling

        # --- Pick a target ---
        # Aiming mirrors _ship_aim_world: the laser line hits world (wx, wy)
        # where wx = ship.x/5 and wy = (ship.y+3)/5, so to hit a target at
        # world (tx, ty) the ship must slide to ship.x = 5*tx, ship.y = 5*ty-3.
        alive = [e for e in enemies if e.alive and 1.5 < e.z < 10]
        rings = [o for o in obstacles if o.kind in ("ring", "arch") and 1.5 < o.z < 5 and not o.passed]
        pylons = [o for o in obstacles if o.kind == "pylon" and 1.0 < o.z < 3.5]

        target_x, target_y = CX, sy  # default: hold height, drift to centre

        if boss is not None and boss.alive and boss.z < 12:
            target_x = CX + 5.0 * boss.x
            target_y = (HEIGHT - 16) + 5.0 * (boss.y + boss.CORE_DY) - 3.0
            if math.hypot(sx - target_x, sy - target_y) < 6:
                fire = True
            elif random.random() < 0.1:
                fire = True
        elif alive:
            nearest = min(alive, key=lambda e: e.z)
            target_x = CX + 5.0 * nearest.x
            target_y = (HEIGHT - 16) + 5.0 * nearest.y - 3.0
            if math.hypot(sx - target_x, sy - target_y) < 6:
                fire = True
            elif random.random() < 0.15:
                fire = True  # suppressive fire while sliding
        elif rings:
            ring = min(rings, key=lambda o: o.z)
            target_x = CX + ring.x * 4.0  # flythrough uses the ship.x/4 scale
            target_y = sy
            if random.random() < 0.04:
                fire = True

        # --- Dodge pylons (they cost a shield now) ---
        for pylon in pylons:
            pylon_ship_x = CX + pylon.x * 4.0  # ship.x that would collide
            if abs(pylon_ship_x - sx) < 8:
                target_x = pylon_ship_x + (20 if pylon.x < 0 else -20)
                break

        diff_x = target_x - sx
        diff_y = target_y - sy
        dx = max(-2.2, min(2.2, diff_x * 0.18))
        dy = max(-1.4, min(1.4, diff_y * 0.10))

        return dx, dy, fire, roll


# ===========================================================================
# Wave Manager
# ===========================================================================

class _WaveManager:
    """Spawns enemy waves with a difficulty curve; every Nth wave is a boss."""
    BOSS_EVERY = 5

    def __init__(self):
        self.wave_timer = 30
        self.wave_num = 0
        self.obs_timer = 25
        self.awaiting_clear = False  # a spawned wave is still on screen

    def update(self, enemies, obstacles, boss=None):
        """Advance timers. Returns ``(spawn_boss, wave_cleared)``."""
        cleared = False

        self.obs_timer -= 1
        if self.obs_timer <= 0 and len(obstacles) < 4:
            kind = random.choices(["ring", "arch", "pylon", "ring"], weights=[3, 2, 2, 3])[0]
            obstacles.append(_Obstacle(kind))
            # Fewer obstacles during a boss fight
            self.obs_timer = random.randint(25, 55) + (40 if boss is not None else 0)

        if boss is not None:
            return False, False  # the boss holds the wave clock

        if self.awaiting_clear and not enemies:
            self.awaiting_clear = False
            cleared = True
            self.wave_timer = max(self.wave_timer, 25)  # breathing room

        self.wave_timer -= 1
        if self.wave_timer <= 0 and len(enemies) < 6:
            self.wave_num += 1
            if self.wave_num % self.BOSS_EVERY == 0:
                self.wave_timer = 120  # normal waves resume after the boss
                return True, cleared

            # Difficulty curve: faster ships, quicker fire, bigger waves
            sb = min(0.05, 0.003 * self.wave_num)       # speed bonus
            fs = max(0.55, 1.0 - 0.03 * self.wave_num)  # fire-cooldown scale
            extra = min(2, self.wave_num // 4)          # extra ships per wave

            p = self.wave_num % 5
            if p == 0:
                for i in range(4 + extra):
                    enemies.append(_Enemy(_Enemy.STRAIGHT,
                                          ((i - 1.5) * 1.2, abs(i - 1.5) * 0.3),
                                          speed_bonus=sb, fire_scale=fs))
            elif p == 1:
                for i in range(3 + extra):
                    e = _Enemy(_Enemy.SINE, speed_bonus=sb, fire_scale=fs)
                    e.phase = i * math.pi * 2 / 3
                    e._init_x = (i - 1) * 1.5
                    enemies.append(e)
            elif p == 2:
                positions = [-1.5, 1.5, -3.0, 3.0]
                for i in range(2 + extra):
                    e = _Enemy(_Enemy.DIVE, speed_bonus=sb, fire_scale=fs)
                    e.x = positions[i % 4]
                    e._init_x = e.x
                    enemies.append(e)
            elif p == 3:
                for i in range(4):
                    e = _Enemy(_Enemy.CIRCLE, speed_bonus=sb, fire_scale=fs)
                    e.phase = i * math.pi / 2
                    e._init_x = 0
                    e._init_y = -0.3
                    enemies.append(e)
            else:
                for i in range(5):
                    enemies.append(_Enemy(_Enemy.STRAIGHT, ((i - 2) * 0.9, 0),
                                          speed_bonus=sb, fire_scale=fs))
            self.awaiting_clear = True
            self.wave_timer = random.randint(55, 100)

        return False, cleared


# ===========================================================================
# Rendering helpers
# ===========================================================================

def _draw_ground(draw, scroll_z, bank_offset, stage):
    vanish_x = CX + int(bank_offset * 0.35)
    for sy in range(HORIZON_Y + 1, HEIGHT):
        t = (sy - HORIZON_Y) / (HEIGHT - HORIZON_Y)
        if t < 0.01: continue
        depth = 1.0 / (t + 0.01)
        wz = depth + scroll_z * 8
        xo = bank_offset * depth * 0.03
        for sx in range(0, WIDTH, 2):
            wx = (sx - vanish_x) * depth * 0.06 + xo
            is_light = (int(wx * 0.4) + int(wz * 0.4)) % 2 == 0
            color = stage["ground_a"] if is_light else stage["ground_b"]
            final = tuple(int(c * max(0.25, t)) for c in color)
            draw.line([(sx, sy), (sx + 1, sy)], fill=final)
    for i in range(7):
        spread = (i - 3) * 16
        bx = CX + spread + int(bank_offset * 0.2)
        color = tuple(int(c * max(0.3, 1.0 - abs(i - 3) * 0.2) * 0.4) for c in stage["grid"])
        draw.line([(vanish_x, HORIZON_Y), (bx, HEIGHT - 1)], fill=color)
    draw.line([(0, HORIZON_Y), (WIDTH - 1, HORIZON_Y)], fill=stage["horizon"])


def _draw_hud(draw, frame, ship, aim_target, score, callout, firing,
              boss=None, combo_mult=1):
    # Reticle
    if aim_target:
        rx, ry = max(4, min(WIDTH - 4, aim_target[0])), max(4, min(HEIGHT - 16, aim_target[1]))
    else:
        rx, ry = CX, CY - 8
    rc = RETICLE_FIRE if firing else (RETICLE_LOCK if aim_target else RETICLE_NORMAL)
    s = 3
    draw.line([(rx - s, ry - s), (rx - 1, ry - s)], fill=rc)
    draw.line([(rx + 1, ry - s), (rx + s, ry - s)], fill=rc)
    draw.line([(rx - s, ry + s), (rx - 1, ry + s)], fill=rc)
    draw.line([(rx + 1, ry + s), (rx + s, ry + s)], fill=rc)
    draw.line([(rx - s, ry - s), (rx - s, ry - 1)], fill=rc)
    draw.line([(rx + s, ry - s), (rx + s, ry - 1)], fill=rc)
    draw.line([(rx - s, ry + 1), (rx - s, ry + s)], fill=rc)
    draw.line([(rx + s, ry + 1), (rx + s, ry + s)], fill=rc)
    draw.point((rx, ry), fill=rc)

    # Score
    s_str = str(score)
    sw = _text_width(s_str, scale=1, spacing=1)
    _draw_text(draw, s_str, WIDTH - sw - 1, 1, HUD_GREEN, scale=1, spacing=1)

    # Shield pips (top-left)
    for i in range(ship.shield):
        draw.point((2 + i * 3, 1), fill=HUD_GREEN)
        draw.point((3 + i * 3, 1), fill=HUD_GREEN)

    # Combo multiplier (under the shield pips)
    if combo_mult > 1:
        _draw_text(draw, "x{}".format(combo_mult), 2, 7, (255, 220, 80),
                   scale=1, spacing=1)

    # Boost meter (bottom-left; hidden when full)
    if ship.boost_meter < 0.999:
        draw.line([(2, 62), (12, 62)], fill=(20, 40, 60))
        bw = int(10 * ship.boost_meter)
        if bw:
            draw.line([(2, 62), (2 + bw, 62)], fill=(80, 180, 255))

    # Boss health bar (top centre)
    if boss is not None and boss.alive:
        frac = max(0.0, boss.hp / boss.max_hp)
        draw.line([(12, 7), (52, 7)], fill=(60, 10, 10))
        bw = int(40 * frac)
        if bw:
            draw.line([(12, 7), (12 + bw, 7)], fill=(255, 60, 60))

    # Callout
    if callout and callout[1] > 0:
        alpha = min(1.0, callout[1] / 15.0)
        color = tuple(int(c * alpha) for c in CALLOUT_COLOR)
        tw = _text_width(callout[0], scale=1, spacing=1)
        _draw_text(draw, callout[0], max(0, (WIDTH - tw) // 2), 9, color, scale=1, spacing=1)


# ===========================================================================
# Main game loop
# ===========================================================================

def run(matrix, duration=60, controller=None):
    """Run Star Fox.

    :param controller: if provided, human plays. If None, AI demo mode.
    """
    interactive = controller is not None

    if interactive:
        show_banner(matrix, ["STAR FOX", "READY!"], color=(100, 200, 255), hold=1.5)

    start_time = time.time()
    frame = 0
    scroll_z = 0.0
    score = 0
    stage_idx = 0
    stage_duration = 18.0

    ship = _Ship()
    ai = _AI() if not interactive else None
    stars = _StarField()
    terrain = _Terrain()
    wave_mgr = _WaveManager()
    boss = None
    enemies = []
    obstacles = []
    lasers = []
    enemy_lasers = []
    explosions = []
    callout = [STAGES[0]["name"], 50]
    firing_this_frame = False
    fire_cooldown = 0
    combo = 0        # consecutive kills without taking a hit
    combo_timer = 0  # frames until the combo decays

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            frame += 1

            # --- Input ---
            move_dx, move_dy = 0.0, 0.0
            want_fire = False
            want_roll = 0
            ship.boosting = False

            if interactive:
                if wants_quit(controller):
                    break
                # Read held direction BEFORE events so B can roll toward it
                direction = read_direction(controller, cardinal_only=False)
                held_dx = direction[0] if direction else 0
                events = controller.poll_events()
                for ev in events:
                    if ev.type is EventType.PRESSED:
                        if ev.button is Button.A:
                            want_fire = True
                        elif ev.button is Button.B:
                            # Roll toward the held direction (default: right)
                            want_roll = -1 if held_dx < 0 else 1
                if direction:
                    dx, dy = direction
                    move_dx = dx * 1.8
                    move_dy = dy * 1.4
                try:
                    if controller.is_pressed(Button.A):
                        want_fire = True  # A held = continuous fire
                    if controller.is_pressed(Button.SELECT):
                        ship.boosting = True  # hold SELECT = boost
                except Exception:
                    pass
            else:
                bank_offset_preview = ship.bank * 9
                move_dx, move_dy, want_fire, want_roll = ai.decide(
                    ship, enemies, obstacles, enemy_lasers, bank_offset_preview,
                    frame, boss=boss)

            # --- Apply input to ship ---
            ship.move(move_dx, move_dy)
            if want_roll:
                if ship.do_barrel_roll(want_roll):
                    callout = ["BARREL ROLL!", 25]

            # Boost stretches world speed while the meter lasts
            speed_mult = 1.45 if (ship.boosting and ship.boost_meter > 0) else 1.0
            scroll_z += 0.05 * speed_mult

            # --- Stage transitions ---
            elapsed = time.time() - start_time
            new_stage = int(elapsed / stage_duration) % len(STAGES)
            if new_stage != stage_idx:
                stage_idx = new_stage
                callout = [STAGES[stage_idx]["name"], 50]
            stage = STAGES[stage_idx]

            # Callout tick
            if callout and callout[1] > 0:
                callout[1] -= 1

            bank_offset = ship.bank * 9

            # --- Update world ---
            ship.update(frame)
            stars.update(bank_offset)
            terrain.update(bank_offset)
            spawn_boss, wave_cleared = wave_mgr.update(enemies, obstacles, boss)
            if spawn_boss:
                boss = _Boss(level=max(1, wave_mgr.wave_num // _WaveManager.BOSS_EVERY))
                callout = ["WARNING!", 45]
            if wave_cleared:
                score += 50
                callout = ["WAVE CLEAR +50", 30]

            # Enemy fire aims at the ship; spread tightens as waves progress
            spread = max(2, 12 - wave_mgr.wave_num)
            for e in enemies:
                e.update(frame, speed_mult)
                if e.should_fire():
                    sp = e.screen_pos(bank_offset)
                    if sp:
                        enemy_lasers.append(_EnemyLaser(
                            sp[0], sp[1],
                            ship.screen_x + random.randint(-spread, spread),
                            ship.screen_y + random.randint(-spread // 2, spread // 2)))
            enemies = [e for e in enemies if not e.is_dead()]

            if boss is not None and boss.alive:
                boss.update(frame, speed_mult)
                if boss.should_fire():
                    bp = boss.core_screen_pos()
                    for off in (-9, 0, 9):  # three-shot fan aimed at the ship
                        enemy_lasers.append(_EnemyLaser(
                            bp[0], bp[1], ship.screen_x + off, ship.screen_y))

            for o in obstacles:
                o.update(speed_mult)
            obstacles = [o for o in obstacles if not o.is_dead()]

            for l in lasers:
                l.update()
            lasers = [l for l in lasers if not l.is_dead()]

            for el in enemy_lasers:
                el.update()
            enemy_lasers = [el for el in enemy_lasers if not el.is_dead()]

            for ex in explosions:
                ex.update()
            explosions = [ex for ex in explosions if not ex.is_dead()]

            # --- Fire lasers ---
            firing_this_frame = False
            fire_cooldown = max(0, fire_cooldown - 1)
            if want_fire and fire_cooldown <= 0:
                sx = ship.screen_x
                sy = ship.screen_y - 7
                wx, wy = _ship_aim_world(ship)
                lasers.append(_Laser(sx - 4, sy, wx, wy))
                lasers.append(_Laser(sx + 4, sy, wx, wy))
                fire_cooldown = 4
                firing_this_frame = True

            # --- Collision: player lasers vs boss and enemies ---
            for laser in lasers:
                if laser.is_dead():
                    continue
                if boss is not None and boss.alive:
                    part = _check_laser_boss(laser, boss)
                    if part == "core":
                        laser.life = 0
                        boss.take_hit()
                        score += 5
                        cp = boss.core_screen_pos()
                        explosions.append(_Explosion(cp[0], cp[1], 0.4))
                        if not boss.alive:
                            bx, by = boss.screen_pos()
                            for _ in range(3):
                                explosions.append(_Explosion(
                                    bx + random.randint(-6, 6),
                                    by + random.randint(-3, 3), 1.6))
                            score += 200
                            combo += 3
                            combo_timer = 120
                            callout = ["BOSS DOWN! +200", 45]
                            boss = None
                            if interactive:
                                safe_rumble(controller, 1.0, 300)
                        continue
                    elif part == "body":
                        laser.life = 0  # armor spark, no damage
                        explosions.append(_Explosion(int(laser.x), int(laser.y), 0.2))
                        continue
                for enemy in enemies:
                    if _check_laser_enemy(laser, enemy):
                        enemy.alive = False
                        sp = enemy.screen_pos(bank_offset) or (int(laser.x), int(laser.y))
                        explosions.append(_Explosion(sp[0], sp[1], 1.0))
                        combo += 1
                        combo_timer = 90
                        mult = min(4, 1 + combo // 3)
                        score += 10 * mult
                        if combo in (3, 6, 9):
                            callout = ["COMBO x{}".format(mult), 20]
                        laser.life = 0
                        if interactive:
                            safe_rumble(controller, 0.3, 80)
                        break

            if combo_timer > 0:
                combo_timer -= 1
                if combo_timer == 0:
                    combo = 0

            # --- Collision: enemy lasers hit ship ---
            for el in enemy_lasers:
                if abs(el.x - ship.screen_x) < 5 and abs(el.y - ship.screen_y) < 5:
                    if ship.barrel_rolling:
                        el.life = 0
                        score += 5
                        explosions.append(_Explosion(int(el.x), int(el.y), 0.3))
                    else:
                        el.life = 0
                        combo = 0
                        combo_timer = 0
                        dead = ship.take_hit()
                        if interactive:
                            safe_rumble(controller, 0.8, 200)
                        if dead:
                            explosions.append(_Explosion(ship.screen_x, ship.screen_y, 2.0))
                            break

            # --- Ring flythrough / pylon collision ---
            for o in obstacles:
                if o.passed or o.z >= 1.2:
                    continue
                ship_world_x = ship.x / 4.0
                if o.kind in ("ring", "arch"):
                    if abs(ship_world_x - o.x) < 2.5:
                        o.passed = True
                        score += 25
                        if getattr(o, "gold", False) and ship.shield < 3:
                            ship.shield += 1
                            callout = ["SHIELD UP!", 25]
                        else:
                            callout = ["NICE!", 20]
                        ship.boost = 1.0
                elif o.kind == "pylon":
                    o.passed = True  # each pylon judged once
                    if abs(ship_world_x - o.x) < 1.4 and not ship.barrel_rolling:
                        combo = 0
                        combo_timer = 0
                        dead = ship.take_hit()
                        explosions.append(_Explosion(ship.screen_x, ship.screen_y, 0.8))
                        callout = ["CRASH!", 25]
                        if interactive:
                            safe_rumble(controller, 0.8, 200)
                        if dead:
                            break

            # --- Game over check ---
            if not ship.alive:
                if interactive:
                    show_banner(matrix, ["GAME OVER", f"SCORE {score}"],
                                color=(255, 80, 80), hold=3.0)
                    return
                else:
                    # Demo: restart
                    ship = _Ship()
                    score = 0
                    combo = 0
                    combo_timer = 0
                    boss = None
                    enemies.clear(); obstacles.clear(); lasers.clear()
                    enemy_lasers.clear(); explosions.clear()
                    wave_mgr = _WaveManager()
                    callout = ["RETRY", 30]

            # --- Render ---
            image = Image.new("RGB", (WIDTH, HEIGHT), stage["sky_top"])
            draw = ImageDraw.Draw(image)

            # Sky gradient
            for y in range(HORIZON_Y):
                t = y / max(1, HORIZON_Y)
                draw.line([(0, y), (WIDTH - 1, y)], fill=tuple(
                    int(stage["sky_top"][i] * (1 - t) + stage["sky_bottom"][i] * t) for i in range(3)))

            stars.draw(draw)
            terrain.draw(draw, stage)
            _draw_ground(draw, scroll_z, bank_offset, stage)

            for o in sorted(obstacles, key=lambda o: -o.z):
                o.draw(draw, bank_offset)
            if boss is not None and boss.alive:
                boss.draw(draw, frame)
            for e in sorted(enemies, key=lambda e: -e.z):
                e.draw(draw, bank_offset)
            for l in lasers:
                l.draw(draw)
            for el in enemy_lasers:
                el.draw(draw)
            for ex in explosions:
                ex.draw(draw)

            if any(ex.flash > 0 for ex in explosions):
                for _ in range(5):
                    draw.point((random.randint(0, WIDTH - 1), random.randint(0, HEIGHT - 1)), fill=(255, 255, 255))

            # HONEST reticle: project the ship's laser line at the target's depth
            if boss is not None and boss.alive:
                tz = boss.z
            else:
                zs = [e.z for e in enemies if e.alive and 1.5 < e.z < 11]
                tz = min(zs) if zs else LASER_AIM_Z
            wx, wy = _ship_aim_world(ship)
            reticle_x = int(CX + wx * (30.0 / tz))
            reticle_y = int((CY - 5) + wy * (30.0 / tz))
            _draw_hud(draw, frame, ship, (reticle_x, reticle_y), score, callout,
                      firing_this_frame, boss=boss,
                      combo_mult=min(4, 1 + combo // 3) if combo >= 3 else 1)

            if ship.alive:
                ship.draw(draw, frame)

            matrix.SetImage(image)

            sleep_time = FRAME_INTERVAL - (time.time() - frame_start)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in starfox: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
