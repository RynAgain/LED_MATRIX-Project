#!/usr/bin/env python3
"""
Pinball -- Lost World inspired pinball on 64x64 LED matrix.

Based on Bally's "Lost World" (1978) playfield layout. The world is 128x280
pixels but only a 64x64 viewport is shown, with the camera tracking the ball.

Features:
- Full physics: gravity, bounce, friction, spin
- Two flippers (left/right) controlled by player
- 3 pop bumpers (dinosaur eggs) that launch the ball
- 2 slingshots above flippers
- Drop targets (5 across the top)
- Ramps/lanes on left and right
- Rollover lanes at top
- Ball plunger with variable power
- Score display overlaid on viewport
- Camera smoothly follows ball vertically
- 3 balls per game

Control scheme (INTERACTIVE):
- LEFT trigger: left flipper
- RIGHT trigger: right flipper  
- A: launch ball (hold for power)
- DOWN: nudge table
- Start+Select: quit

Inspired by Bally "Lost World" 1978 layout:
- Top: rollover lanes + drop targets
- Middle: 3 pop bumpers in triangle formation
- Lower-middle: slingshots
- Bottom: flippers + drain
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import should_stop, show_banner, safe_rumble
from src.display._fonts import _draw_text, _text_width

logger = logging.getLogger(__name__)

# --- Constants ---
DISPLAY_W, DISPLAY_H = 64, 64
FPS = 30
FRAME_DUR = 1.0 / FPS

# Playfield dimensions (larger than display, camera follows ball)
PF_W = 128
PF_H = 280

# Physics
GRAVITY = 0.15
BALL_RADIUS = 2
BALL_FRICTION = 0.995
BALL_MAX_SPEED = 8.0
FLIPPER_POWER = 6.0
BUMPER_POWER = 4.0
SLINGSHOT_POWER = 3.5
PLUNGER_MAX = 7.0

# Scoring
BUMPER_SCORE = 100
SLINGSHOT_SCORE = 50
TARGET_SCORE = 500
ROLLOVER_SCORE = 200
RAMP_SCORE = 1000

# Colors
BG_COLOR = (5, 15, 5)  # Dark green playfield
WALL_COLOR = (60, 40, 20)  # Brown wood rails
FLIPPER_COLOR = (200, 200, 220)  # Chrome flippers
BALL_COLOR = (220, 220, 230)  # Steel ball
BALL_HIGHLIGHT = (255, 255, 255)
BUMPER_COLOR = (200, 50, 50)  # Red bumper caps
BUMPER_RING = (255, 200, 50)  # Yellow ring
SLINGSHOT_COLOR = (80, 200, 80)  # Green rubber
TARGET_COLOR = (255, 255, 80)  # Yellow targets
TARGET_HIT_COLOR = (60, 60, 30)  # Dim when hit
ROLLOVER_COLOR = (100, 150, 255)  # Blue lanes
PLUNGER_COLOR = (150, 100, 50)  # Bronze
RAMP_COLOR = (100, 80, 60)  # Dark rail
DRAIN_COLOR = (40, 10, 10)  # Dark red drain area
SCORE_COLOR = (255, 200, 50)
SCORE_BG = (0, 0, 0)


# ---------------------------------------------------------------------------
# Playfield elements (positions in world coordinates)
# Lost World inspired layout
# ---------------------------------------------------------------------------

# Walls (line segments): [(x1,y1,x2,y2), ...]
WALLS = [
    # Outer boundary
    (4, 0, 4, PF_H),          # Left wall
    (PF_W - 4, 0, PF_W - 4, PF_H),  # Right wall
    (4, 4, PF_W - 4, 4),      # Top wall (curved in real life)
    # Outlanes
    (20, PF_H - 60, 20, PF_H - 20),   # Left outlane wall
    (PF_W - 20, PF_H - 60, PF_W - 20, PF_H - 20),  # Right outlane wall
    # Inlanes (guide rails above flippers)
    (30, PF_H - 80, 20, PF_H - 60),   # Left inlane guide
    (PF_W - 30, PF_H - 80, PF_W - 20, PF_H - 60),  # Right inlane guide
    # Ramp entries
    (15, 60, 15, 130),   # Left ramp rail
    (25, 60, 25, 130),   # Left ramp inner
    (PF_W - 15, 60, PF_W - 15, 130),  # Right ramp rail
    (PF_W - 25, 60, PF_W - 25, 130),  # Right ramp inner
]

# Pop bumpers: (cx, cy, radius)
BUMPERS = [
    (64, 100, 8),   # Center top (big dinosaur egg)
    (44, 130, 7),   # Left
    (84, 130, 7),   # Right
]

# Slingshots: (x1, y1, x2, y2, nx, ny) - line + outward normal
SLINGSHOTS = [
    (25, PF_H - 90, 42, PF_H - 60, -0.5, -0.866),  # Left sling
    (PF_W - 42, PF_H - 60, PF_W - 25, PF_H - 90, 0.5, -0.866),  # Right sling
]

# Drop targets: (cx, cy, width, height)
DROP_TARGETS = [
    (34, 50, 8, 4),
    (49, 45, 8, 4),
    (64, 42, 8, 4),
    (79, 45, 8, 4),
    (94, 50, 8, 4),
]

# Rollover lanes: (cx, cy)
ROLLOVERS = [
    (40, 25),
    (55, 20),
    (73, 20),
    (88, 25),
]

# Flipper positions
FLIPPER_LEFT_PIVOT = (38, PF_H - 30)
FLIPPER_RIGHT_PIVOT = (PF_W - 38, PF_H - 30)
FLIPPER_LENGTH = 18
FLIPPER_REST_ANGLE_L = 0.4   # radians (slightly down from horizontal)
FLIPPER_UP_ANGLE_L = -0.6    # radians (angled up)
FLIPPER_REST_ANGLE_R = math.pi - 0.4
FLIPPER_UP_ANGLE_R = math.pi + 0.6

# Plunger lane
PLUNGER_X = PF_W - 10
PLUNGER_Y_TOP = PF_H - 100
PLUNGER_Y_BOTTOM = PF_H - 15

# Drain zone
DRAIN_Y = PF_H - 8


# ---------------------------------------------------------------------------
# Game classes
# ---------------------------------------------------------------------------

class Ball:
    """Pinball with physics."""

    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.active = False
        self.in_plunger = False

    def reset_to_plunger(self):
        """Place ball in plunger lane."""
        self.x = float(PLUNGER_X)
        self.y = float(PLUNGER_Y_BOTTOM)
        self.vx = 0.0
        self.vy = 0.0
        self.active = True
        self.in_plunger = True

    def launch(self, power):
        """Launch ball from plunger."""
        self.vy = -power
        self.vx = random.uniform(-0.3, 0.3)
        self.in_plunger = False

    def update(self):
        """Update ball physics."""
        if not self.active or self.in_plunger:
            return

        # Gravity
        self.vy += GRAVITY

        # Friction
        self.vx *= BALL_FRICTION
        self.vy *= BALL_FRICTION

        # Speed cap
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        if speed > BALL_MAX_SPEED:
            scale = BALL_MAX_SPEED / speed
            self.vx *= scale
            self.vy *= scale

        # Move
        self.x += self.vx
        self.y += self.vy

    def is_drained(self):
        """Check if ball fell below drain."""
        return self.y > DRAIN_Y


class Flipper:
    """A flipper that rotates between rest and active angles."""

    def __init__(self, pivot_x, pivot_y, rest_angle, up_angle, side):
        self.px = pivot_x
        self.py = pivot_y
        self.rest_angle = rest_angle
        self.up_angle = up_angle
        self.angle = rest_angle
        self.side = side  # 'left' or 'right'
        self.active = False
        self.angular_vel = 0.0

    def activate(self):
        self.active = True

    def deactivate(self):
        self.active = False

    def update(self):
        """Animate flipper toward target angle."""
        target = self.up_angle if self.active else self.rest_angle
        diff = target - self.angle
        # Snap quickly
        speed = 0.35 if self.active else 0.2
        self.angle += diff * speed
        self.angular_vel = diff * speed

    def get_tip(self):
        """Get flipper tip position."""
        tx = self.px + FLIPPER_LENGTH * math.cos(self.angle)
        ty = self.py + FLIPPER_LENGTH * math.sin(self.angle)
        return tx, ty

    def check_ball_hit(self, ball):
        """Check if ball is touching flipper and deflect it."""
        tx, ty = self.get_tip()
        # Line segment from pivot to tip
        # Check distance from ball center to this segment
        dx = tx - self.px
        dy = ty - self.py
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1:
            return False

        # Project ball onto segment
        t = max(0, min(1, ((ball.x - self.px) * dx + (ball.y - self.py) * dy) / seg_len_sq))
        closest_x = self.px + t * dx
        closest_y = self.py + t * dy

        dist = math.sqrt((ball.x - closest_x) ** 2 + (ball.y - closest_y) ** 2)

        if dist < BALL_RADIUS + 3:
            # Deflect ball
            if dist < 1:
                dist = 1
            nx = (ball.x - closest_x) / dist
            ny = (ball.y - closest_y) / dist

            # Relative velocity of flipper at contact point
            flip_vel = self.angular_vel * t * FLIPPER_LENGTH
            # Add flipper's angular velocity contribution
            power = abs(flip_vel) * 1.5 + 1.0
            if self.active:
                power = max(power, FLIPPER_POWER * 0.7)

            ball.vx = nx * power
            ball.vy = ny * power - 1.0  # Always push somewhat upward

            # Push ball out of flipper
            ball.x = closest_x + nx * (BALL_RADIUS + 4)
            ball.y = closest_y + ny * (BALL_RADIUS + 4)
            return True
        return False


# ---------------------------------------------------------------------------
# Main game
# ---------------------------------------------------------------------------

class PinballGame:
    """Full pinball game state."""

    def __init__(self):
        self.ball = Ball()
        self.flipper_l = Flipper(
            FLIPPER_LEFT_PIVOT[0], FLIPPER_LEFT_PIVOT[1],
            FLIPPER_REST_ANGLE_L, FLIPPER_UP_ANGLE_L, 'left'
        )
        self.flipper_r = Flipper(
            FLIPPER_RIGHT_PIVOT[0], FLIPPER_RIGHT_PIVOT[1],
            FLIPPER_REST_ANGLE_R, FLIPPER_UP_ANGLE_R, 'right'
        )
        self.score = 0
        self.balls_left = 3
        self.target_states = [True] * len(DROP_TARGETS)  # True = standing
        self.rollover_lit = [False] * len(ROLLOVERS)
        self.bumper_flash = [0] * len(BUMPERS)
        self.plunger_power = 0.0
        self.plunger_charging = False
        self.camera_y = PF_H - DISPLAY_H  # Start at bottom
        self.tick = 0
        self.game_over = False
        self.ball_launched = False

        # Start with ball in plunger
        self.ball.reset_to_plunger()

    def _wall_collision(self):
        """Bounce ball off walls."""
        ball = self.ball

        # Simple boundary walls
        if ball.x < 6 + BALL_RADIUS:
            ball.x = 6 + BALL_RADIUS
            ball.vx = abs(ball.vx) * 0.8
        if ball.x > PF_W - 6 - BALL_RADIUS:
            ball.x = PF_W - 6 - BALL_RADIUS
            ball.vx = -abs(ball.vx) * 0.8
        if ball.y < 6 + BALL_RADIUS:
            ball.y = 6 + BALL_RADIUS
            ball.vy = abs(ball.vy) * 0.8

        # Plunger lane right wall (keeps ball in lane until launched)
        if ball.in_plunger:
            ball.x = PLUNGER_X
            ball.vx = 0

        # Wall segments
        for x1, y1, x2, y2 in WALLS:
            # Distance from ball to line segment
            dx = x2 - x1
            dy = y2 - y1
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1:
                continue
            t = max(0, min(1, ((ball.x - x1) * dx + (ball.y - y1) * dy) / seg_len_sq))
            cx = x1 + t * dx
            cy = y1 + t * dy
            dist = math.sqrt((ball.x - cx) ** 2 + (ball.y - cy) ** 2)

            if dist < BALL_RADIUS + 2:
                if dist < 0.5:
                    dist = 0.5
                nx = (ball.x - cx) / dist
                ny = (ball.y - cy) / dist
                # Reflect velocity
                dot = ball.vx * nx + ball.vy * ny
                if dot < 0:  # Only if moving toward wall
                    ball.vx -= 2 * dot * nx * 0.7
                    ball.vy -= 2 * dot * ny * 0.7
                    ball.x = cx + nx * (BALL_RADIUS + 3)
                    ball.y = cy + ny * (BALL_RADIUS + 3)

    def _bumper_collision(self):
        """Check pop bumper hits."""
        ball = self.ball
        for i, (bx, by, br) in enumerate(BUMPERS):
            dx = ball.x - bx
            dy = ball.y - by
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < br + BALL_RADIUS:
                # Bounce away from bumper
                if dist < 1:
                    dist = 1
                nx = dx / dist
                ny = dy / dist
                ball.vx = nx * BUMPER_POWER
                ball.vy = ny * BUMPER_POWER
                ball.x = bx + nx * (br + BALL_RADIUS + 2)
                ball.y = by + ny * (br + BALL_RADIUS + 2)
                self.score += BUMPER_SCORE
                self.bumper_flash[i] = 6

    def _slingshot_collision(self):
        """Check slingshot hits."""
        ball = self.ball
        for x1, y1, x2, y2, nx, ny in SLINGSHOTS:
            # Distance from ball to slingshot line
            dx = x2 - x1
            dy = y2 - y1
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1:
                continue
            t = max(0, min(1, ((ball.x - x1) * dx + (ball.y - y1) * dy) / seg_len_sq))
            cx = x1 + t * dx
            cy = y1 + t * dy
            dist = math.sqrt((ball.x - cx) ** 2 + (ball.y - cy) ** 2)

            if dist < BALL_RADIUS + 4:
                ball.vx += nx * SLINGSHOT_POWER
                ball.vy += ny * SLINGSHOT_POWER
                ball.x += nx * 5
                ball.y += ny * 5
                self.score += SLINGSHOT_SCORE

    def _target_collision(self):
        """Check drop target hits."""
        ball = self.ball
        for i, (tx, ty, tw, th) in enumerate(DROP_TARGETS):
            if not self.target_states[i]:
                continue
            if (abs(ball.x - tx) < tw / 2 + BALL_RADIUS and
                    abs(ball.y - ty) < th / 2 + BALL_RADIUS):
                self.target_states[i] = False
                self.score += TARGET_SCORE
                ball.vy = abs(ball.vy) * 0.5  # Slow bounce back
                # Check if all targets down
                if not any(self.target_states):
                    self.score += TARGET_SCORE * 5  # Bonus
                    # Reset targets after delay
                    self.target_states = [True] * len(DROP_TARGETS)

    def _rollover_collision(self):
        """Check rollover lanes."""
        ball = self.ball
        for i, (rx, ry) in enumerate(ROLLOVERS):
            if abs(ball.x - rx) < 6 and abs(ball.y - ry) < 6:
                if not self.rollover_lit[i]:
                    self.rollover_lit[i] = True
                    self.score += ROLLOVER_SCORE
                    # Check if all lit
                    if all(self.rollover_lit):
                        self.score += RAMP_SCORE
                        self.rollover_lit = [False] * len(ROLLOVERS)

    def update(self, flip_l=False, flip_r=False):
        """Update one frame of game logic."""
        self.tick += 1

        # Flippers
        if flip_l:
            self.flipper_l.activate()
        else:
            self.flipper_l.deactivate()
        if flip_r:
            self.flipper_r.activate()
        else:
            self.flipper_r.deactivate()

        self.flipper_l.update()
        self.flipper_r.update()

        # Ball physics
        self.ball.update()

        if self.ball.active and not self.ball.in_plunger:
            # Collisions
            self._wall_collision()
            self._bumper_collision()
            self._slingshot_collision()
            self._target_collision()
            self._rollover_collision()

            # Flipper collision
            self.flipper_l.check_ball_hit(self.ball)
            self.flipper_r.check_ball_hit(self.ball)

            # Drain check
            if self.ball.is_drained():
                self.balls_left -= 1
                if self.balls_left <= 0:
                    self.game_over = True
                else:
                    self.ball.reset_to_plunger()
                    self.ball_launched = False

        # Decay bumper flash
        for i in range(len(self.bumper_flash)):
            if self.bumper_flash[i] > 0:
                self.bumper_flash[i] -= 1

        # Camera follows ball (smooth vertical tracking)
        if self.ball.active:
            target_cam = self.ball.y - DISPLAY_H // 2
            target_cam = max(0, min(PF_H - DISPLAY_H, target_cam))
            self.camera_y += (target_cam - self.camera_y) * 0.1

    def charge_plunger(self):
        """Increase plunger power while held."""
        if self.ball.in_plunger:
            self.plunger_power = min(PLUNGER_MAX, self.plunger_power + 0.15)
            self.plunger_charging = True

    def release_plunger(self):
        """Launch ball with accumulated power."""
        if self.ball.in_plunger and self.plunger_power > 0:
            self.ball.launch(self.plunger_power)
            self.ball_launched = True
        self.plunger_power = 0.0
        self.plunger_charging = False

    def draw(self):
        """Render the 64x64 viewport of the playfield."""
        image = Image.new("RGB", (DISPLAY_W, DISPLAY_H), BG_COLOR)
        draw = ImageDraw.Draw(image)

        cam_x = (PF_W - DISPLAY_W) // 2  # Center horizontally
        cam_y = int(self.camera_y)

        def wx(x):
            """World X to screen X."""
            return int(x - cam_x)

        def wy(y):
            """World Y to screen Y."""
            return int(y - cam_y)

        def visible(x, y, margin=10):
            """Check if world coord is in viewport."""
            sx, sy = wx(x), wy(y)
            return -margin < sx < DISPLAY_W + margin and -margin < sy < DISPLAY_H + margin

        # --- Draw playfield elements ---

        # Walls
        for x1, y1, x2, y2 in WALLS:
            if visible(x1, y1) or visible(x2, y2):
                draw.line([(wx(x1), wy(y1)), (wx(x2), wy(y2))], fill=WALL_COLOR)

        # Outer rails (always visible at edges)
        draw.line([(wx(4), max(0, wy(0))), (wx(4), min(DISPLAY_H, wy(PF_H)))], fill=WALL_COLOR)
        draw.line([(wx(PF_W - 4), max(0, wy(0))),
                   (wx(PF_W - 4), min(DISPLAY_H, wy(PF_H)))], fill=WALL_COLOR)

        # Drain zone
        if visible(PF_W // 2, DRAIN_Y):
            dy_screen = wy(DRAIN_Y)
            draw.rectangle([(wx(6), dy_screen), (wx(PF_W - 6), dy_screen + 4)], fill=DRAIN_COLOR)

        # Pop bumpers
        for i, (bx, by, br) in enumerate(BUMPERS):
            if visible(bx, by, br + 5):
                sx, sy = wx(bx), wy(by)
                # Ring
                ring_color = (255, 255, 100) if self.bumper_flash[i] > 0 else BUMPER_RING
                draw.ellipse([(sx - br, sy - br), (sx + br, sy + br)], outline=ring_color)
                # Cap
                cap_r = br - 3
                cap_color = (255, 100, 100) if self.bumper_flash[i] > 0 else BUMPER_COLOR
                draw.ellipse([(sx - cap_r, sy - cap_r), (sx + cap_r, sy + cap_r)], fill=cap_color)

        # Slingshots
        for x1, y1, x2, y2, nx, ny in SLINGSHOTS:
            if visible(x1, y1) or visible(x2, y2):
                draw.line([(wx(x1), wy(y1)), (wx(x2), wy(y2))], fill=SLINGSHOT_COLOR, width=2)

        # Drop targets
        for i, (tx, ty, tw, th) in enumerate(DROP_TARGETS):
            if visible(tx, ty):
                sx, sy = wx(tx), wy(ty)
                color = TARGET_COLOR if self.target_states[i] else TARGET_HIT_COLOR
                draw.rectangle([(sx - tw // 2, sy - th // 2),
                                (sx + tw // 2, sy + th // 2)], fill=color)

        # Rollover lanes
        for i, (rx, ry) in enumerate(ROLLOVERS):
            if visible(rx, ry):
                sx, sy = wx(rx), wy(ry)
                color = (200, 255, 200) if self.rollover_lit[i] else ROLLOVER_COLOR
                draw.ellipse([(sx - 3, sy - 3), (sx + 3, sy + 3)], outline=color)

        # Flippers
        for flipper in [self.flipper_l, self.flipper_r]:
            if visible(flipper.px, flipper.py, 20):
                tip_x, tip_y = flipper.get_tip()
                draw.line([(wx(flipper.px), wy(flipper.py)),
                           (wx(tip_x), wy(tip_y))], fill=FLIPPER_COLOR, width=3)

        # Plunger
        if visible(PLUNGER_X, PLUNGER_Y_BOTTOM):
            px_screen = wx(PLUNGER_X)
            plunger_top = wy(PLUNGER_Y_BOTTOM - 10 + int(self.plunger_power * 2))
            plunger_bot = wy(PLUNGER_Y_BOTTOM)
            draw.rectangle([(px_screen - 2, plunger_top), (px_screen + 2, plunger_bot)],
                           fill=PLUNGER_COLOR)
            # Power indicator
            if self.plunger_charging:
                pwr_h = int(self.plunger_power / PLUNGER_MAX * 15)
                draw.rectangle([(px_screen + 4, plunger_bot - pwr_h),
                                (px_screen + 5, plunger_bot)], fill=(255, 50, 50))

        # Ball
        if self.ball.active:
            bx_s, by_s = wx(self.ball.x), wy(self.ball.y)
            if -5 < bx_s < DISPLAY_W + 5 and -5 < by_s < DISPLAY_H + 5:
                draw.ellipse([(bx_s - BALL_RADIUS, by_s - BALL_RADIUS),
                              (bx_s + BALL_RADIUS, by_s + BALL_RADIUS)], fill=BALL_COLOR)
                # Highlight
                draw.point((bx_s - 1, by_s - 1), fill=BALL_HIGHLIGHT)

        # --- HUD overlay ---
        # Score (top, always visible)
        score_str = str(self.score)
        sw = _text_width(score_str, scale=1, spacing=1)
        # Dark background for readability
        draw.rectangle([(0, 0), (sw + 3, 8)], fill=SCORE_BG)
        _draw_text(draw, score_str, 2, 1, SCORE_COLOR, scale=1, spacing=1)

        # Balls left (top right)
        for i in range(self.balls_left):
            bx_ind = DISPLAY_W - 5 - i * 5
            draw.ellipse([(bx_ind - 2, 2), (bx_ind + 2, 6)], fill=BALL_COLOR)

        return image


# ---------------------------------------------------------------------------
# Demo mode (AI plays)
# ---------------------------------------------------------------------------

def _run_demo(matrix, duration, start_time):
    """AI-controlled pinball demo."""
    game = PinballGame()

    # Auto-launch ball
    game.plunger_power = PLUNGER_MAX * 0.8
    game.release_plunger()

    while time.time() - start_time < duration:
        if should_stop():
            return
        frame_start = time.time()

        # AI: flip when ball is near flippers and heading down
        ball = game.ball
        flip_l = False
        flip_r = False

        if ball.active and not ball.in_plunger:
            # Left flipper: activate when ball is near and heading down-left
            dist_l = math.sqrt((ball.x - FLIPPER_LEFT_PIVOT[0]) ** 2 +
                               (ball.y - FLIPPER_LEFT_PIVOT[1]) ** 2)
            if dist_l < 25 and ball.vy > 0 and ball.x < PF_W // 2 + 10:
                flip_l = True

            # Right flipper
            dist_r = math.sqrt((ball.x - FLIPPER_RIGHT_PIVOT[0]) ** 2 +
                               (ball.y - FLIPPER_RIGHT_PIVOT[1]) ** 2)
            if dist_r < 25 and ball.vy > 0 and ball.x > PF_W // 2 - 10:
                flip_r = True

        game.update(flip_l, flip_r)

        # Auto re-launch if ball in plunger
        if ball.in_plunger:
            game.plunger_power = PLUNGER_MAX * random.uniform(0.6, 0.95)
            game.release_plunger()

        # Game over -> restart
        if game.game_over:
            if not show_banner(matrix, ["GAME OVER", f"SCORE:{game.score}"],
                               color=SCORE_COLOR, hold=2.0):
                return
            game = PinballGame()
            game.plunger_power = PLUNGER_MAX * 0.8
            game.release_plunger()

        image = game.draw()
        matrix.SetImage(image)

        elapsed = time.time() - frame_start
        sleep_time = FRAME_DUR - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def _run_interactive(matrix, controller, start_time):
    """Player-controlled pinball."""
    from src.input.controller import wants_quit, Button, EventType

    game = PinballGame()
    show_banner(matrix, ["PINBALL", "L/R:FLIP A:PLUNGE"],
                color=FLIPPER_COLOR, hold=1.5)

    a_held = False

    while True:
        if should_stop():
            return
        frame_start = time.time()

        events = controller.poll_events()
        if wants_quit(controller):
            return

        # Input
        d = controller.get_direction()
        flip_l = False
        flip_r = False

        # Flippers via direction or shoulder buttons
        if d:
            if d[0] < 0:
                flip_l = True
            if d[0] > 0:
                flip_r = True
            # Nudge
            if d[1] > 0 and game.ball.active:
                game.ball.vy -= 0.5
                game.ball.vx += random.uniform(-0.5, 0.5)

        for ev in events:
            if ev.type is EventType.PRESSED:
                if ev.button is Button.A:
                    a_held = True
                elif ev.button is Button.LEFT:
                    flip_l = True
                elif ev.button is Button.RIGHT:
                    flip_r = True
                elif ev.button is Button.B:
                    # Alternative: B for left flipper
                    flip_l = True
            elif ev.type is EventType.RELEASED:
                if ev.button is Button.A:
                    a_held = False
                    game.release_plunger()

        # Charge plunger while A held
        if a_held and game.ball.in_plunger:
            game.charge_plunger()

        game.update(flip_l, flip_r)

        if game.game_over:
            safe_rumble(controller, 0.5, 300)
            show_banner(matrix, ["GAME OVER", f"SCORE:{game.score}"],
                        color=(255, 80, 80), hold=2.5)
            return

        image = game.draw()
        matrix.SetImage(image)

        elapsed = time.time() - frame_start
        sleep_time = FRAME_DUR - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60, controller=None):
    """Run Pinball.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds (DEMO mode).
        controller: optional Controller. None -> DEMO, not-None -> INTERACTIVE.
    """
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
