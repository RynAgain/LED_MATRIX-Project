#!/usr/bin/env python3
"""
Pinball -- Lost World inspired pinball on 64x64 LED matrix.

128x500 pixel playfield with 64x64 scrolling viewport that follows the ball
on BOTH X and Y axes. Inspired by Bally's "Lost World" (1978).

Features:
- Huge playfield (128x500) viewed through a 64x64 camera window
- Camera smoothly tracks ball position on both axes
- Full physics: gravity, bounce, friction, angular deflection
- Two flippers with power-based deflection
- 5 pop bumpers arranged in patterns
- 4 slingshots
- 8 drop targets in two banks
- 3 rollover lane groups
- Spinner gate
- Orbit shot (loop around the top)
- Ball-save timer on new ball
- Variable plunger with visual power gauge
- 3 balls per game, bonus multiplier
- Rich visual playfield with colored regions

Controls (INTERACTIVE):
- LEFT: left flipper
- RIGHT: right flipper
- A (hold/release): plunger
- UP: nudge up
- B: nudge left
- Start+Select: quit
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import should_stop, show_banner, safe_rumble
from src.display._fonts import _draw_text, _text_width

logger = logging.getLogger(__name__)

# --- Display ---
DISPLAY_W, DISPLAY_H = 64, 64
FPS = 30
FRAME_DUR = 1.0 / FPS

# --- Playfield ---
PF_W = 128
PF_H = 500

# --- Physics ---
GRAVITY = 0.12
BALL_RADIUS = 2
BALL_FRICTION = 0.998
BALL_MAX_SPEED = 9.0
FLIPPER_POWER = 7.5
BUMPER_POWER = 5.0
SLINGSHOT_POWER = 4.0
PLUNGER_MAX = 9.0
NUDGE_POWER = 1.5

# --- Scoring ---
BUMPER_PTS = 100
SLING_PTS = 50
TARGET_PTS = 500
ROLLOVER_PTS = 200
SPINNER_PTS = 50
ORBIT_PTS = 2000
ALL_TARGETS_BONUS = 5000

# --- Colors ---
BG_COLOR = (4, 20, 8)
PLAYFIELD_DARK = (2, 12, 4)
WALL_COLOR = (80, 60, 30)
RAIL_COLOR = (120, 100, 60)
FLIPPER_COLOR = (210, 210, 230)
BALL_COLOR = (230, 230, 240)
BALL_SHINE = (255, 255, 255)
BUMPER_CAP = (220, 40, 40)
BUMPER_FLASH = (255, 255, 100)
BUMPER_RING = (255, 180, 40)
SLING_COLOR = (40, 200, 80)
SLING_FLASH = (150, 255, 150)
TARGET_UP = (255, 240, 60)
TARGET_DOWN = (50, 40, 15)
ROLLOVER_OFF = (40, 60, 120)
ROLLOVER_ON = (100, 200, 255)
SPINNER_COLOR = (200, 150, 50)
ORBIT_COLOR = (80, 40, 150)
PLUNGER_COLOR = (160, 100, 40)
POWER_COLOR = (255, 50, 50)
DRAIN_COLOR = (60, 10, 10)
SCORE_COLOR = (255, 200, 40)

# --- Playfield layout (world coordinates) ---
WALL_L = 8
WALL_R = PF_W - 8
WALL_TOP = 8

# Plunger lane
PLUNGER_LANE_X = PF_W - 14
PLUNGER_GATE_Y = 80

# Flippers
FLIP_Y = PF_H - 50
FLIP_L_PIVOT = (38, FLIP_Y)
FLIP_R_PIVOT = (PF_W - 38, FLIP_Y)
FLIP_LENGTH = 20
FLIP_REST_L = 0.35
FLIP_UP_L = -0.7
FLIP_REST_R = math.pi - 0.35
FLIP_UP_R = math.pi + 0.7

# Drain
DRAIN_Y = PF_H - 20

# Pop bumpers (5 total)
BUMPERS = [
    (50, 160, 9),
    (78, 150, 9),
    (64, 185, 10),
    (40, 210, 8),
    (88, 210, 8),
]

# Slingshots (4)
SLINGSHOTS = [
    {"p1": (22, FLIP_Y - 40), "p2": (38, FLIP_Y - 8), "nx": -0.7, "ny": -0.7},
    {"p1": (PF_W - 38, FLIP_Y - 8), "p2": (PF_W - 22, FLIP_Y - 40), "nx": 0.7, "ny": -0.7},
    {"p1": (20, 250), "p2": (35, 270), "nx": -0.8, "ny": -0.5},
    {"p1": (PF_W - 35, 270), "p2": (PF_W - 20, 250), "nx": 0.8, "ny": -0.5},
]

# Drop targets (2 banks of 4)
TARGET_BANK_A = [(30 + i * 14, 90, 10, 5) for i in range(4)]
TARGET_BANK_B = [(34 + i * 14, 120, 10, 5) for i in range(4)]
ALL_TARGETS = TARGET_BANK_A + TARGET_BANK_B

# Rollovers (3 groups)
ROLLOVERS_TOP = [(44 + i * 16, 40) for i in range(4)]
ROLLOVERS_MID = [(35 + i * 20, 280) for i in range(4)]
ROLLOVERS_BOT = [(45 + i * 12, FLIP_Y - 55) for i in range(3)]
ALL_ROLLOVERS = ROLLOVERS_TOP + ROLLOVERS_MID + ROLLOVERS_BOT

# Spinner
SPINNER_POS = (64, 70)

# Orbit markers
ORBIT_ENTRY_L = (18, 100)
ORBIT_EXIT_R = (PF_W - 18, 100)

# Wall segments
WALLS = [
    (WALL_L, WALL_TOP, WALL_L, PF_H),
    (WALL_R, WALL_TOP, WALL_R, PF_H),
    (WALL_L, WALL_TOP, WALL_R, WALL_TOP),
    (22, PF_H - 90, 22, PF_H - 40),
    (PF_W - 22, PF_H - 90, PF_W - 22, PF_H - 40),
    (32, PF_H - 90, 22, PF_H - 50),
    (PF_W - 32, PF_H - 90, PF_W - 22, PF_H - 50),
    (PF_W - 20, 60, PF_W - 20, PF_H - 10),
    (15, 50, 15, 110),
    (PF_W - 15, 50, PF_W - 15, 110),
    (15, 50, 30, 20),
    (PF_W - 15, 50, PF_W - 30, 20),
    (30, 20, PF_W - 30, 20),
    (50, 240, 50, 300),
    (78, 240, 78, 300),
    (44, 30, 44, 55),
    (60, 28, 60, 55),
    (76, 30, 76, 55),
    (92, 30, 92, 55),
]


# ---------------------------------------------------------------------------
# Game objects
# ---------------------------------------------------------------------------

class Particle:
    """Visual spark/particle effect."""
    __slots__ = ('x', 'y', 'vx', 'vy', 'color', 'life')

    def __init__(self, x, y, vx, vy, color, life=8):
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = life

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.05  # Slight gravity on sparks
        self.life -= 1
        return self.life > 0


class Ball:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.active = False
        self.in_plunger = False
        self.trail = []  # List of (x, y) recent positions
        self.trail_max = 6

    def reset_to_plunger(self):
        self.x = float(PLUNGER_LANE_X)
        self.y = float(PF_H - 60)
        self.vx = 0.0
        self.vy = 0.0
        self.active = True
        self.in_plunger = True

    def launch(self, power):
        self.vy = -power
        self.vx = random.uniform(-0.2, 0.2)
        self.in_plunger = False

    def update(self):
        """Update with substep physics to prevent tunneling through walls."""
        if not self.active or self.in_plunger:
            return
        self.vy += GRAVITY
        self.vx *= BALL_FRICTION
        self.vy *= BALL_FRICTION
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        if speed > BALL_MAX_SPEED:
            s = BALL_MAX_SPEED / speed
            self.vx *= s
            self.vy *= s
        # Substep: move in increments of max 2px to prevent tunneling
        steps = max(1, int(math.ceil(speed / 2.0)))
        step_x = self.vx / steps
        step_y = self.vy / steps
        for _ in range(steps):
            self.x += step_x
            self.y += step_y
        # Record trail position
        self.trail.append((self.x, self.y))
        if len(self.trail) > self.trail_max:
            self.trail.pop(0)

    def is_drained(self):
        return self.y > DRAIN_Y and abs(self.x - PF_W / 2) < 40


class Flipper:
    def __init__(self, px, py, rest, up, side):
        self.px = px
        self.py = py
        self.rest_angle = rest
        self.up_angle = up
        self.angle = rest
        self.side = side
        self.active = False
        self.omega = 0.0

    def set_active(self, state):
        self.active = state

    def update(self):
        target = self.up_angle if self.active else self.rest_angle
        diff = target - self.angle
        speed = 0.4 if self.active else 0.2
        self.omega = diff * speed
        self.angle += self.omega

    def get_tip(self):
        return (self.px + FLIP_LENGTH * math.cos(self.angle),
                self.py + FLIP_LENGTH * math.sin(self.angle))

    def hit_ball(self, ball):
        tx, ty = self.get_tip()
        dx, dy = tx - self.px, ty - self.py
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1:
            return False
        t = max(0, min(1, ((ball.x - self.px) * dx + (ball.y - self.py) * dy) / seg_len_sq))
        cx = self.px + t * dx
        cy = self.py + t * dy
        dist = math.sqrt((ball.x - cx) ** 2 + (ball.y - cy) ** 2)
        if dist < BALL_RADIUS + 4:
            if dist < 0.5:
                dist = 0.5
            nx = (ball.x - cx) / dist
            ny = (ball.y - cy) / dist
            flip_contrib = abs(self.omega) * t * FLIP_LENGTH * 1.5
            power = max(flip_contrib, 2.0)
            if self.active:
                power = max(power, FLIPPER_POWER * 0.8)
            ball.vx = nx * power * 0.7
            ball.vy = ny * power - 2.0
            ball.x = cx + nx * (BALL_RADIUS + 5)
            ball.y = cy + ny * (BALL_RADIUS + 5)
            return True
        return False


# ---------------------------------------------------------------------------
# Main game
# ---------------------------------------------------------------------------

class PinballGame:
    def __init__(self):
        self.ball = Ball()
        self.flip_l = Flipper(FLIP_L_PIVOT[0], FLIP_L_PIVOT[1], FLIP_REST_L, FLIP_UP_L, 'L')
        self.flip_r = Flipper(FLIP_R_PIVOT[0], FLIP_R_PIVOT[1], FLIP_REST_R, FLIP_UP_R, 'R')
        self.score = 0
        self.balls_left = 3
        self.bonus_mult = 1
        self.target_states = [True] * len(ALL_TARGETS)
        self.rollover_states = [False] * len(ALL_ROLLOVERS)
        self.bumper_flash = [0] * len(BUMPERS)
        self.sling_flash = [0] * len(SLINGSHOTS)
        self.spinner_angle = 0.0
        self.spinner_spinning = 0
        self.plunger_power = 0.0
        self.plunger_charging = False
        self.cam_x = (PF_W - DISPLAY_W) / 2.0
        self.cam_y = float(PF_H - DISPLAY_H)
        self.tick = 0
        self.game_over = False
        self.ball_save_timer = 0
        self.particles = []  # Visual spark effects
        self.ball.reset_to_plunger()

    def _collide_walls(self):
        b = self.ball
        if b.x < WALL_L + BALL_RADIUS:
            b.x = WALL_L + BALL_RADIUS
            b.vx = abs(b.vx) * 0.75
        if b.x > WALL_R - BALL_RADIUS:
            b.x = WALL_R - BALL_RADIUS
            b.vx = -abs(b.vx) * 0.75
        if b.y < WALL_TOP + BALL_RADIUS:
            b.y = WALL_TOP + BALL_RADIUS
            b.vy = abs(b.vy) * 0.75
        if b.in_plunger:
            b.x = PLUNGER_LANE_X
            b.vx = 0
        if not b.in_plunger and b.x > PF_W - 20 and b.y > PLUNGER_GATE_Y:
            b.x = PF_W - 20 - BALL_RADIUS
            b.vx = -abs(b.vx) * 0.5

        for x1, y1, x2, y2 in WALLS:
            dx, dy = x2 - x1, y2 - y1
            seg_sq = dx * dx + dy * dy
            if seg_sq < 1:
                continue
            t = max(0, min(1, ((b.x - x1) * dx + (b.y - y1) * dy) / seg_sq))
            cx, cy = x1 + t * dx, y1 + t * dy
            dist = math.sqrt((b.x - cx) ** 2 + (b.y - cy) ** 2)
            if dist < BALL_RADIUS + 2:
                if dist < 0.3:
                    dist = 0.3
                nx, ny = (b.x - cx) / dist, (b.y - cy) / dist
                dot = b.vx * nx + b.vy * ny
                if dot < 0:
                    b.vx -= 2 * dot * nx * 0.7
                    b.vy -= 2 * dot * ny * 0.7
                    b.x = cx + nx * (BALL_RADIUS + 3)
                    b.y = cy + ny * (BALL_RADIUS + 3)

    def _collide_bumpers(self):
        b = self.ball
        for i, (bx, by, br) in enumerate(BUMPERS):
            dx, dy = b.x - bx, b.y - by
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < br + BALL_RADIUS:
                if dist < 1:
                    dist = 1
                nx, ny = dx / dist, dy / dist
                b.vx = nx * BUMPER_POWER
                b.vy = ny * BUMPER_POWER
                b.x = bx + nx * (br + BALL_RADIUS + 2)
                b.y = by + ny * (br + BALL_RADIUS + 2)
                self.score += BUMPER_PTS * self.bonus_mult
                self.bumper_flash[i] = 8
                # Spawn sparks
                for _ in range(4):
                    self.particles.append(Particle(
                        b.x, b.y,
                        random.uniform(-2, 2), random.uniform(-2, 2),
                        BUMPER_FLASH, life=10
                    ))

    def _collide_slingshots(self):
        b = self.ball
        for i, sl in enumerate(SLINGSHOTS):
            p1, p2 = sl["p1"], sl["p2"]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            seg_sq = dx * dx + dy * dy
            if seg_sq < 1:
                continue
            t = max(0, min(1, ((b.x - p1[0]) * dx + (b.y - p1[1]) * dy) / seg_sq))
            cx = p1[0] + t * dx
            cy = p1[1] + t * dy
            dist = math.sqrt((b.x - cx) ** 2 + (b.y - cy) ** 2)
            if dist < BALL_RADIUS + 5:
                b.vx += sl["nx"] * SLINGSHOT_POWER
                b.vy += sl["ny"] * SLINGSHOT_POWER
                b.x += sl["nx"] * 6
                b.y += sl["ny"] * 6
                self.score += SLING_PTS * self.bonus_mult
                self.sling_flash[i] = 6
                for _ in range(3):
                    self.particles.append(Particle(
                        b.x, b.y,
                        random.uniform(-1.5, 1.5), random.uniform(-2, 0),
                        SLING_FLASH, life=8
                    ))

    def _collide_targets(self):
        b = self.ball
        for i, (tx, ty, tw, th) in enumerate(ALL_TARGETS):
            if not self.target_states[i]:
                continue
            if abs(b.x - tx) < tw / 2 + BALL_RADIUS and abs(b.y - ty) < th / 2 + BALL_RADIUS:
                self.target_states[i] = False
                self.score += TARGET_PTS * self.bonus_mult
                b.vy = abs(b.vy) * 0.4 + 1.0
                if not any(self.target_states):
                    self.score += ALL_TARGETS_BONUS * self.bonus_mult
                    self.bonus_mult = min(5, self.bonus_mult + 1)
                    self.target_states = [True] * len(ALL_TARGETS)

    def _collide_rollovers(self):
        b = self.ball
        for i, (rx, ry) in enumerate(ALL_ROLLOVERS):
            if abs(b.x - rx) < 7 and abs(b.y - ry) < 7:
                if not self.rollover_states[i]:
                    self.rollover_states[i] = True
                    self.score += ROLLOVER_PTS * self.bonus_mult

    def _collide_spinner(self):
        b = self.ball
        sx, sy = SPINNER_POS
        if abs(b.x - sx) < 8 and abs(b.y - sy) < 6:
            self.spinner_spinning = 20
            self.score += SPINNER_PTS * self.bonus_mult

    def update(self, flip_l=False, flip_r=False):
        self.tick += 1
        self.flip_l.set_active(flip_l)
        self.flip_r.set_active(flip_r)
        self.flip_l.update()
        self.flip_r.update()
        self.ball.update()

        if self.ball.active and not self.ball.in_plunger:
            self._collide_walls()
            self._collide_bumpers()
            self._collide_slingshots()
            self._collide_targets()
            self._collide_rollovers()
            self._collide_spinner()
            self.flip_l.hit_ball(self.ball)
            self.flip_r.hit_ball(self.ball)

            if self.ball.is_drained():
                if self.ball_save_timer > 0:
                    self.ball.reset_to_plunger()
                    self.ball_save_timer = 0
                else:
                    self.balls_left -= 1
                    if self.balls_left <= 0:
                        self.game_over = True
                    else:
                        self.ball.reset_to_plunger()
                        self.ball_save_timer = FPS * 3

        if self.ball_save_timer > 0:
            self.ball_save_timer -= 1
        for i in range(len(self.bumper_flash)):
            if self.bumper_flash[i] > 0:
                self.bumper_flash[i] -= 1
        for i in range(len(self.sling_flash)):
            if self.sling_flash[i] > 0:
                self.sling_flash[i] -= 1
        if self.spinner_spinning > 0:
            self.spinner_angle += 0.5
            self.spinner_spinning -= 1

        # Update particles
        self.particles = [p for p in self.particles if p.update()]

        # Camera follows ball on BOTH X and Y with aggressive tracking
        if self.ball.active:
            target_cx = self.ball.x - DISPLAY_W / 2
            target_cy = self.ball.y - DISPLAY_H / 2
            target_cx = max(0, min(PF_W - DISPLAY_W, target_cx))
            target_cy = max(0, min(PF_H - DISPLAY_H, target_cy))
            # Faster lerp + minimum catch-up speed ensures ball stays in view
            dx = target_cx - self.cam_x
            dy = target_cy - self.cam_y
            # Lerp 25% per frame, but also enforce minimum speed of 2px/frame
            move_x = dx * 0.25
            move_y = dy * 0.25
            if abs(dx) > 2:
                move_x = max(abs(move_x), 2.0) * (1 if dx > 0 else -1)
            if abs(dy) > 2:
                move_y = max(abs(move_y), 2.0) * (1 if dy > 0 else -1)
            # If ball is near edge of viewport, snap harder
            ball_screen_x = self.ball.x - self.cam_x
            ball_screen_y = self.ball.y - self.cam_y
            if ball_screen_x < 10 or ball_screen_x > DISPLAY_W - 10:
                move_x = dx * 0.5
            if ball_screen_y < 10 or ball_screen_y > DISPLAY_H - 10:
                move_y = dy * 0.5
            self.cam_x += move_x
            self.cam_y += move_y
            self.cam_x = max(0, min(PF_W - DISPLAY_W, self.cam_x))
            self.cam_y = max(0, min(PF_H - DISPLAY_H, self.cam_y))

    def charge_plunger(self):
        if self.ball.in_plunger:
            self.plunger_power = min(PLUNGER_MAX, self.plunger_power + 0.2)
            self.plunger_charging = True

    def release_plunger(self):
        if self.ball.in_plunger and self.plunger_power > 0.5:
            self.ball.launch(self.plunger_power)
            self.ball_save_timer = FPS * 3
        self.plunger_power = 0.0
        self.plunger_charging = False

    def nudge(self, dx, dy):
        if self.ball.active and not self.ball.in_plunger:
            self.ball.vx += dx * NUDGE_POWER
            self.ball.vy += dy * NUDGE_POWER

    def draw(self):
        image = Image.new("RGB", (DISPLAY_W, DISPLAY_H), PLAYFIELD_DARK)
        draw = ImageDraw.Draw(image)
        cx, cy = int(self.cam_x), int(self.cam_y)

        def sx(x):
            return int(x - cx)

        def sy(y):
            return int(y - cy)

        def vis(x, y, m=15):
            return -m < sx(x) < DISPLAY_W + m and -m < sy(y) < DISPLAY_H + m

        # Walls
        for x1, y1, x2, y2 in WALLS:
            if vis(x1, y1) or vis(x2, y2):
                draw.line([(sx(x1), sy(y1)), (sx(x2), sy(y2))], fill=WALL_COLOR)

        # Rails
        draw.line([(sx(WALL_L), max(0, sy(WALL_TOP))),
                   (sx(WALL_L), min(DISPLAY_H - 1, sy(PF_H)))], fill=RAIL_COLOR)
        draw.line([(sx(WALL_R), max(0, sy(WALL_TOP))),
                   (sx(WALL_R), min(DISPLAY_H - 1, sy(PF_H)))], fill=RAIL_COLOR)

        # Drain
        if vis(64, DRAIN_Y):
            draw.rectangle([(sx(WALL_L), sy(DRAIN_Y)),
                            (sx(WALL_R), sy(DRAIN_Y) + 3)], fill=DRAIN_COLOR)

        # Bumpers
        for i, (bx, by, br) in enumerate(BUMPERS):
            if vis(bx, by, br + 5):
                s_x, s_y = sx(bx), sy(by)
                flash = self.bumper_flash[i] > 0
                draw.ellipse([(s_x - br, s_y - br), (s_x + br, s_y + br)],
                             outline=BUMPER_FLASH if flash else BUMPER_RING)
                cr = br - 3
                draw.ellipse([(s_x - cr, s_y - cr), (s_x + cr, s_y + cr)],
                             fill=BUMPER_FLASH if flash else BUMPER_CAP)

        # Slingshots
        for i, sl in enumerate(SLINGSHOTS):
            p1, p2 = sl["p1"], sl["p2"]
            if vis(p1[0], p1[1]) or vis(p2[0], p2[1]):
                c = SLING_FLASH if self.sling_flash[i] > 0 else SLING_COLOR
                draw.line([(sx(p1[0]), sy(p1[1])), (sx(p2[0]), sy(p2[1]))], fill=c, width=2)

        # Targets
        for i, (tx, ty, tw, th) in enumerate(ALL_TARGETS):
            if vis(tx, ty):
                c = TARGET_UP if self.target_states[i] else TARGET_DOWN
                draw.rectangle([(sx(tx) - tw // 2, sy(ty) - th // 2),
                                (sx(tx) + tw // 2, sy(ty) + th // 2)], fill=c)

        # Rollovers
        for i, (rx, ry) in enumerate(ALL_ROLLOVERS):
            if vis(rx, ry):
                c = ROLLOVER_ON if self.rollover_states[i] else ROLLOVER_OFF
                draw.ellipse([(sx(rx) - 3, sy(ry) - 3), (sx(rx) + 3, sy(ry) + 3)], outline=c)
                if self.rollover_states[i]:
                    draw.point((sx(rx), sy(ry)), fill=c)

        # Spinner
        sp_x, sp_y = SPINNER_POS
        if vis(sp_x, sp_y):
            angle = self.spinner_angle
            ddx = int(5 * math.cos(angle))
            ddy = int(2 * math.sin(angle))
            draw.line([(sx(sp_x) - ddx, sy(sp_y) - ddy),
                       (sx(sp_x) + ddx, sy(sp_y) + ddy)], fill=SPINNER_COLOR)

        # Orbit arrows
        for ox, oy in [ORBIT_ENTRY_L, ORBIT_EXIT_R]:
            if vis(ox, oy):
                draw.polygon([(sx(ox), sy(oy) - 3), (sx(ox) - 2, sy(oy) + 2),
                              (sx(ox) + 2, sy(oy) + 2)], fill=ORBIT_COLOR)

        # Flippers
        for flip in [self.flip_l, self.flip_r]:
            if vis(flip.px, flip.py, 25):
                tip = flip.get_tip()
                draw.line([(sx(flip.px), sy(flip.py)), (sx(tip[0]), sy(tip[1]))],
                          fill=FLIPPER_COLOR, width=3)

        # Plunger
        if vis(PLUNGER_LANE_X, PF_H - 50):
            p_sx = sx(PLUNGER_LANE_X)
            p_top = sy(PF_H - 50 + int(self.plunger_power * 3))
            p_bot = sy(PF_H - 30)
            draw.rectangle([(p_sx - 2, p_top), (p_sx + 2, p_bot)], fill=PLUNGER_COLOR)
            if self.plunger_charging:
                pwr_pct = self.plunger_power / PLUNGER_MAX
                bar_h = int(pwr_pct * 20)
                draw.rectangle([(p_sx + 4, p_bot - bar_h), (p_sx + 5, p_bot)], fill=POWER_COLOR)

        # Ball trail (fading dots behind ball)
        if self.ball.active and self.ball.trail:
            trail_colors = [(180, 180, 190), (130, 130, 140), (80, 80, 90),
                            (50, 50, 60), (30, 30, 40), (15, 15, 20)]
            for i, (tx, ty) in enumerate(self.ball.trail):
                t_sx, t_sy = sx(tx), sy(ty)
                if 0 <= t_sx < DISPLAY_W and 0 <= t_sy < DISPLAY_H:
                    ci = min(i, len(trail_colors) - 1)
                    draw.point((t_sx, t_sy), fill=trail_colors[ci])

        # Ball
        if self.ball.active:
            b_sx, b_sy = sx(self.ball.x), sy(self.ball.y)
            if -5 < b_sx < DISPLAY_W + 5 and -5 < b_sy < DISPLAY_H + 5:
                draw.ellipse([(b_sx - BALL_RADIUS, b_sy - BALL_RADIUS),
                              (b_sx + BALL_RADIUS, b_sy + BALL_RADIUS)], fill=BALL_COLOR)
                draw.point((b_sx - 1, b_sy - 1), fill=BALL_SHINE)

        # Particles (sparks from bumpers/slings)
        for p in self.particles:
            p_sx, p_sy = sx(p.x), sy(p.y)
            if 0 <= p_sx < DISPLAY_W and 0 <= p_sy < DISPLAY_H:
                alpha = p.life / 10.0
                c = (int(p.color[0] * alpha), int(p.color[1] * alpha), int(p.color[2] * alpha))
                draw.point((p_sx, p_sy), fill=c)

        # HUD
        score_s = str(self.score)
        sw = _text_width(score_s, scale=1, spacing=1)
        draw.rectangle([(0, 0), (sw + 3, 8)], fill=(0, 0, 0))
        _draw_text(draw, score_s, 2, 1, SCORE_COLOR, scale=1, spacing=1)

        for i in range(self.balls_left):
            draw.ellipse([(DISPLAY_W - 6 - i * 6, 2), (DISPLAY_W - 3 - i * 6, 5)],
                         fill=BALL_COLOR)

        if self.bonus_mult > 1:
            _draw_text(draw, f"x{self.bonus_mult}", 2, DISPLAY_H - 8,
                       (200, 100, 255), scale=1, spacing=0)

        if self.ball_save_timer > 0 and self.tick % 10 < 6:
            _draw_text(draw, "SAVE", DISPLAY_W - 22, DISPLAY_H - 8,
                       (100, 255, 100), scale=1, spacing=0)

        return image


# ---------------------------------------------------------------------------
# Demo (AI)
# ---------------------------------------------------------------------------

def _run_demo(matrix, duration, start_time):
    game = PinballGame()
    game.plunger_power = PLUNGER_MAX * 0.85
    game.release_plunger()

    while time.time() - start_time < duration:
        if should_stop():
            return
        frame_start = time.time()

        b = game.ball
        fl, fr = False, False
        if b.active and not b.in_plunger:
            if b.vy > 0 and b.y > FLIP_Y - 30 and b.y < FLIP_Y + 5:
                if b.x < PF_W / 2:
                    fl = True
                else:
                    fr = True
                if abs(b.x - PF_W / 2) < 15:
                    fl = fr = True

        game.update(fl, fr)

        if b.in_plunger:
            game.plunger_power = PLUNGER_MAX * random.uniform(0.7, 0.95)
            game.release_plunger()

        if game.game_over:
            show_banner(matrix, ["GAME OVER", f"{game.score}"],
                        color=SCORE_COLOR, hold=2.0)
            game = PinballGame()
            game.plunger_power = PLUNGER_MAX * 0.85
            game.release_plunger()

        matrix.SetImage(game.draw())
        elapsed = time.time() - frame_start
        if elapsed < FRAME_DUR:
            time.sleep(FRAME_DUR - elapsed)


# ---------------------------------------------------------------------------
# Interactive
# ---------------------------------------------------------------------------

def _run_interactive(matrix, controller, start_time):
    from src.input.controller import wants_quit, Button, EventType

    game = PinballGame()
    show_banner(matrix, ["PINBALL", "L/R:FLIP A:LAUNCH"], color=FLIPPER_COLOR, hold=1.5)

    a_held = False

    while True:
        if should_stop():
            return
        frame_start = time.time()
        events = controller.poll_events()
        if wants_quit(controller):
            return

        fl, fr = False, False
        d = controller.get_direction()
        if d:
            if d[0] < 0:
                fl = True
            if d[0] > 0:
                fr = True
            if d[1] < 0:
                game.nudge(0, -1)
            if d[1] > 0:
                game.nudge(0, 1)

        for ev in events:
            if ev.type is EventType.PRESSED:
                if ev.button is Button.A:
                    a_held = True
                elif ev.button is Button.B:
                    game.nudge(-1, 0)
                elif ev.button is Button.LEFT:
                    fl = True
                elif ev.button is Button.RIGHT:
                    fr = True
            elif ev.type is EventType.RELEASED:
                if ev.button is Button.A:
                    a_held = False
                    game.release_plunger()

        if a_held and game.ball.in_plunger:
            game.charge_plunger()

        game.update(fl, fr)

        if game.game_over:
            safe_rumble(controller, 0.5, 300)
            show_banner(matrix, ["GAME OVER", f"{game.score}"], color=(255, 80, 80), hold=2.5)
            return

        matrix.SetImage(game.draw())
        elapsed = time.time() - frame_start
        if elapsed < FRAME_DUR:
            time.sleep(FRAME_DUR - elapsed)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def run(matrix, duration=60, controller=None):
    """Run Pinball. controller=None -> AI demo, otherwise interactive."""
    start_time = time.time()
    try:
        if controller is None:
            _run_demo(matrix, duration, start_time)
        else:
            _run_interactive(matrix, controller, start_time)
    except Exception as e:
        logger.error("Error in pinball: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
