#!/usr/bin/env python3
"""Star Fox -- AI-driven (demo) or controller-playable (interactive) on 64x64 LED.

A rail-shooter inspired by Star Fox (SNES, 1993). The Arwing flies forward
automatically; the player (or AI) controls lateral movement, fires lasers,
and performs barrel rolls to deflect incoming fire.

Control scheme (INTERACTIVE mode, ``controller is not None``)
-------------------------------------------------------------
- **D-pad / analog LEFT/RIGHT** moves the ship laterally.
- **D-pad UP** moves ship up (tighter turns, near horizon).
- **D-pad DOWN** moves ship down (lower, wider view).
- **A** fires dual lasers at the nearest enemy / forward.
- **B** performs a barrel roll (deflects enemy fire, brief invulnerability).
- **Start + Select** (or hold Start) quits to menu.

DEMO mode (``controller is None``) uses the same game logic with an intelligent
autopilot AI that dodges, aims, fires, and barrel-rolls.

Scoring:
- Enemy kill: 10 pts
- Ring flythrough: 25 pts
- Deflect with barrel roll: 5 pts
- Survive a wave: bonus
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
    MAX_Y = 16         # Ship can reach enemies anywhere on the Y axis too

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
        self.y = max(-self.MAX_Y, min(self.MAX_Y, self.y))
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
        self.boost = max(0, self.boost - 0.03)

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

    def __init__(self, behavior=0, offset=(0, 0)):
        self.z = 14.0 + random.uniform(0, 3)
        self.x = random.uniform(-3.0, 3.0) + offset[0]
        self.y = random.uniform(-2.0, 1.5) + offset[1]  # Full vertical spread
        self.speed = random.uniform(0.09, 0.14)
        self.behavior = behavior
        self.color = random.choice(ENEMY_PALETTES)
        self.phase = random.uniform(0, math.pi * 2)
        self.alive = True
        self._init_x = self.x
        self._init_y = self.y
        self._fire_cd = random.randint(40, 90)

    def update(self, frame):
        if not self.alive:
            return
        self.z -= self.speed
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
            self._fire_cd = random.randint(50, 120)
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
        self.color = (60, 200, 200) if kind == "ring" else (200, 200, 60) if kind == "arch" else (60, 200, 60)
        self.rotation = random.uniform(0, math.pi * 2)
        self.passed = False

    def update(self):
        self.z -= self.speed
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
    """Laser fires STRAIGHT FORWARD from the ship's position toward the vanishing point.

    In Star Fox, the ship IS the cursor — lasers converge from the ship's screen
    position toward the center/horizon. You aim by MOVING THE SHIP.
    """
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        # Converge toward vanishing point (center of horizon)
        self.start_x = float(x)
        self.speed = 5.0
        self.life = 1.0

    def update(self):
        # Move toward vanishing point (CX, HORIZON_Y) from ship position
        # Lasers converge both X and Y toward the center vanishing point
        self.y -= self.speed
        # Converge X and Y toward vanishing point (perspective)
        self.x += (CX - self.x) * 0.07
        self.life -= 0.055
        self.speed *= 1.02

    def is_dead(self):
        return self.life <= 0 or self.y < HORIZON_Y - 5

    def draw(self, draw_ctx):
        x, y = int(self.x), int(self.y)
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            b = max(0.3, self.life)
            core = tuple(int(c * b) for c in LASER_CORE)
            glow = tuple(int(c * b * 0.5) for c in LASER_GLOW)
            draw_ctx.point((x, y), fill=core)
            if y + 1 < HEIGHT:
                draw_ctx.point((x, y + 1), fill=core)
            if y + 2 < HEIGHT:
                draw_ctx.point((x, y + 2), fill=glow)
            if y + 3 < HEIGHT:
                draw_ctx.point((x, y + 3), fill=glow)


class _EnemyLaser:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.tx = CX + random.randint(-15, 15)
        self.ty = HEIGHT + 5
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

    def decide(self, ship, enemies, obstacles, enemy_lasers, bank_offset, frame):
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

        # --- Pick a target to slide toward ---
        # Prefer enemies (since that's the core gameplay)
        alive = [e for e in enemies if e.alive and 1.5 < e.z < 10]
        rings = [o for o in obstacles if o.kind in ("ring", "arch") and 1.5 < o.z < 5 and not o.passed]
        pylons = [o for o in obstacles if o.kind == "pylon" and 1.0 < o.z < 3.5]

        target_x, target_y = CX, CY - 5  # Default: center/forward

        if alive:
            # Target the nearest enemy — snap ship to their screen pos
            nearest = min(alive, key=lambda e: e.z)
            sp = nearest.screen_pos(bank_offset)
            if sp:
                target_x, target_y = sp
        elif rings:
            # Fly through nearest ring
            ring = min(rings, key=lambda o: o.z)
            target_x = CX + int(ring.x * (30.0 / ring.z))
            target_y = CY - 5

        # --- Dodge pylons (override target if about to hit one) ---
        for pylon in pylons:
            pylon_sx = CX + int(pylon.x * (30.0 / pylon.z))
            if abs(pylon_sx - sx) < 8:
                # Pylon in our path! Dodge to the side with more room
                target_x = pylon_sx + (20 if pylon.x < 0 else -20)
                break

        # --- Slide ship toward target (this IS aiming in Star Fox) ---
        diff_x = target_x - sx
        diff_y = target_y - sy

        # Aggressive movement — a skilled player snaps to targets fast
        dx = max(-2.2, min(2.2, diff_x * 0.18))
        dy = max(-0.8, min(0.8, diff_y * 0.08))

        # --- Fire when lined up with an enemy ---
        if alive:
            nearest = min(alive, key=lambda e: e.z)
            sp = nearest.screen_pos(bank_offset)
            if sp:
                dist_to_target = math.hypot(sx - sp[0], sy - sp[1])
                # Fire when close to lined up (generous — skilled players spam fire while sliding)
                if dist_to_target < 10:
                    fire = True
                    self._on_target_frames += 1
                else:
                    self._on_target_frames = 0
                    # Still fire occasionally while sliding toward target (suppressive fire)
                    if random.random() < 0.15:
                        fire = True
        else:
            # No enemies — occasional forward shots
            if random.random() < 0.04:
                fire = True
            self._on_target_frames = 0

        return dx, dy, fire, roll


# ===========================================================================
# Wave Manager
# ===========================================================================

class _WaveManager:
    def __init__(self):
        self.wave_timer = 30
        self.wave_num = 0
        self.obs_timer = 25

    def update(self, enemies, obstacles):
        self.wave_timer -= 1
        self.obs_timer -= 1

        if self.wave_timer <= 0 and len(enemies) < 6:
            self.wave_num += 1
            p = self.wave_num % 5
            if p == 0:
                for i in range(4):
                    enemies.append(_Enemy(_Enemy.STRAIGHT, ((i - 1.5) * 1.2, abs(i - 1.5) * 0.3)))
            elif p == 1:
                for i in range(3):
                    e = _Enemy(_Enemy.SINE); e.phase = i * math.pi * 2 / 3; e._init_x = (i - 1) * 1.5
                    enemies.append(e)
            elif p == 2:
                for i in range(2):
                    e = _Enemy(_Enemy.DIVE); e.x = -1.5 + i * 3; e._init_x = e.x
                    enemies.append(e)
            elif p == 3:
                for i in range(4):
                    e = _Enemy(_Enemy.CIRCLE); e.phase = i * math.pi / 2; e._init_x = 0; e._init_y = -0.3
                    enemies.append(e)
            else:
                for i in range(5):
                    enemies.append(_Enemy(_Enemy.STRAIGHT, ((i - 2) * 0.9, 0)))
            self.wave_timer = random.randint(55, 100)

        if self.obs_timer <= 0 and len(obstacles) < 4:
            kind = random.choices(["ring", "arch", "pylon", "ring"], weights=[3, 2, 2, 3])[0]
            obstacles.append(_Obstacle(kind))
            self.obs_timer = random.randint(25, 55)


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


def _draw_hud(draw, frame, ship, aim_target, score, callout, firing):
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

    # Show entry banner in interactive mode
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
    enemies = []
    obstacles = []
    lasers = []
    enemy_lasers = []
    explosions = []
    callout = [STAGES[0]["name"], 50]
    firing_this_frame = False
    fire_cooldown = 0

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            frame += 1
            scroll_z += 0.05

            # --- Input ---
            move_dx, move_dy = 0.0, 0.0
            want_fire = False
            want_roll = 0

            if interactive:
                # Check quit
                if wants_quit(controller):
                    break
                events = controller.poll_events()
                for ev in events:
                    if ev.type is EventType.PRESSED:
                        if ev.button is Button.A:
                            want_fire = True
                        elif ev.button is Button.B:
                            want_roll = 1  # Roll right by default
                        elif ev.button is Button.START:
                            break
                # Directional held-state
                direction = read_direction(controller, cardinal_only=False)
                if direction:
                    dx, dy = direction
                    move_dx = dx * 1.8  # Speed multiplier for feel
                    move_dy = dy * 0.8
                # A held = continuous fire
                try:
                    if controller.is_pressed(Button.A):
                        want_fire = True
                except Exception:
                    pass
            else:
                # AI mode
                bank_offset_preview = ship.bank * 9
                move_dx, move_dy, want_fire, want_roll = ai.decide(
                    ship, enemies, obstacles, enemy_lasers, bank_offset_preview, frame)

            # --- Apply input to ship ---
            ship.move(move_dx, move_dy)
            if want_roll:
                if ship.do_barrel_roll(want_roll):
                    callout = ["BARREL ROLL!", 25]

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

            # --- Update ---
            ship.update(frame)
            stars.update(bank_offset)
            terrain.update(bank_offset)
            wave_mgr.update(enemies, obstacles)

            for e in enemies:
                e.update(frame)
                if e.should_fire():
                    sp = e.screen_pos(bank_offset)
                    if sp:
                        enemy_lasers.append(_EnemyLaser(sp[0], sp[1]))
            enemies = [e for e in enemies if not e.is_dead()]

            for o in obstacles:
                o.update()
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
                # Lasers fire STRAIGHT FORWARD from ship position (ship IS the cursor)
                sx = ship.screen_x
                sy = ship.screen_y - 7
                lasers.append(_Laser(sx - 4, sy))
                lasers.append(_Laser(sx + 4, sy))
                fire_cooldown = 4
                firing_this_frame = True

            # --- Collision: lasers hit enemies ---
            for laser in lasers:
                if laser.is_dead():
                    continue
                for enemy in enemies:
                    if not enemy.alive or enemy.z < 1 or enemy.z > 11:
                        continue
                    ex = CX + enemy.x * (30.0 / enemy.z)
                    ey = CY - 5 + enemy.y * (30.0 / enemy.z)
                    if math.hypot(laser.x - ex, laser.y - ey) < max(5, 14.0 / enemy.z):
                        enemy.alive = False
                        explosions.append(_Explosion(int(ex), int(ey), 1.0))
                        score += 10
                        laser.life = 0
                        if interactive:
                            safe_rumble(controller, 0.3, 80)
                        break

            # --- Collision: enemy lasers hit ship ---
            for el in enemy_lasers:
                if abs(el.x - ship.screen_x) < 5 and abs(el.y - ship.screen_y) < 5:
                    if ship.barrel_rolling:
                        el.life = 0
                        score += 5
                        explosions.append(_Explosion(int(el.x), int(el.y), 0.3))
                    else:
                        el.life = 0
                        dead = ship.take_hit()
                        if interactive:
                            safe_rumble(controller, 0.8, 200)
                        if dead:
                            explosions.append(_Explosion(ship.screen_x, ship.screen_y, 2.0))
                            break

            # --- Ring flythrough ---
            for o in obstacles:
                if o.kind in ("ring", "arch") and not o.passed and o.z < 1.2:
                    ship_world_x = ship.x / 4.0
                    if abs(ship_world_x - o.x) < 2.5:
                        o.passed = True
                        score += 25
                        callout = ["NICE!", 20]
                        ship.boost = 1.0

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

            # Aim target for HUD
            # Reticle shows where shots converge (between ship and vanishing point)
            # It moves with the ship but partway toward center (perspective)
            reticle_x = int(ship.screen_x * 0.6 + CX * 0.4)
            reticle_y = int(ship.screen_y * 0.3 + (HORIZON_Y + 5) * 0.7)
            _draw_hud(draw, frame, ship, (reticle_x, reticle_y), score, callout, firing_this_frame)

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
