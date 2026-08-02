"""
Billiards -- AI-driven pool simulation on 64x64 LED matrix.

Uses PIL pre-rendered background + SetImage (ported from SetPixel).

Features:
- Rich green felt background
- Brown/wood colored table borders
- Balls with color variety (2-3 pixels each for visibility)
- Cue ball is white and larger (3x3)
- Pocket indicators (dark circles in corners/sides)
- Ball shadows (1 pixel offset in dark color)
- Shot animation: brief cue stick line before first shot
- Physics simulation with AI
"""

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, FrameCanvas
except ImportError:
    RGBMatrix = None
    RGBMatrixOptions = None
    FrameCanvas = None

import logging
import math
from PIL import Image, ImageDraw
from src.display._shared import should_stop, interruptible_sleep
import random
import time

logger = logging.getLogger(__name__)

# Constants
WIDTH, HEIGHT = 64, 64
BALL_RADIUS = 2
CUE_RADIUS = 2       # cue ball drawn 3x3 (radius 1 from center, but we'll use special draw)
POCKET_RADIUS = 3
FRICTION = 0.993
AI_STRENGTH_MIN = 0.6
AI_STRENGTH_MAX = 1.8
MAX_SHOTS = 100
BORDER_WIDTH = 2

# Colors
BLACK = (0, 0, 0)
FELT_GREEN = (10, 60, 20)          # rich green felt
BORDER_BROWN = (90, 50, 15)        # wood border
BORDER_HIGHLIGHT = (120, 70, 25)   # lighter wood edge
POCKET_COLOR = (5, 15, 5)          # dark pocket
SHADOW_COLOR = (3, 20, 8)          # shadow on felt
WHITE = (255, 255, 255)
CUE_STICK_COLOR = (180, 140, 60)   # wooden cue stick

# Ball colors -- distinctive colors for each ball
BALL_COLORS = [
    (255, 255, 255),  # 0: cue ball (white)
    (220, 30, 30),    # 1: red
    (30, 30, 220),    # 2: blue
    (220, 180, 20),   # 3: yellow
    (20, 180, 60),    # 4: green
    (200, 80, 20),    # 5: orange
    (160, 30, 160),   # 6: purple
    (180, 40, 80),    # 7: maroon
]


class Ball:
    def __init__(self, x, y, color_idx=0):
        self.initial_x = x
        self.initial_y = y
        self.x = float(x)
        self.y = float(y)
        self.color_idx = color_idx
        self.color = BALL_COLORS[color_idx % len(BALL_COLORS)]
        self.vx = 0.0
        self.vy = 0.0
        self.is_cue = (color_idx == 0)
        self.pocketed = False

    def draw(self, pixels):
        """Draw ball onto PIL pixel accessor with shadow."""
        ix, iy = int(self.x), int(self.y)

        # Shadow (1 pixel offset down-right)
        if self.is_cue:
            # Cue ball shadow: 3x3
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    sx, sy = ix + dx + 1, iy + dy + 1
                    if BORDER_WIDTH < sx < WIDTH - BORDER_WIDTH and BORDER_WIDTH < sy < HEIGHT - BORDER_WIDTH:
                        pixels[sx, sy] = SHADOW_COLOR
        else:
            # Regular ball shadow: 2x2
            for dx in range(2):
                for dy in range(2):
                    sx, sy = ix + dx + 1, iy + dy + 1
                    if BORDER_WIDTH < sx < WIDTH - BORDER_WIDTH and BORDER_WIDTH < sy < HEIGHT - BORDER_WIDTH:
                        pixels[sx, sy] = SHADOW_COLOR

        # Ball itself
        r, g, b = self.color
        if self.is_cue:
            # Cue ball: 3x3 with bright center
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    bx, by = ix + dx, iy + dy
                    if BORDER_WIDTH < bx < WIDTH - BORDER_WIDTH and BORDER_WIDTH < by < HEIGHT - BORDER_WIDTH:
                        # Brighter at center
                        if dx == 0 and dy == 0:
                            pixels[bx, by] = (255, 255, 255)
                        else:
                            pixels[bx, by] = (200, 200, 200)
        else:
            # Regular ball: 2x2 with highlight
            for dx in range(2):
                for dy in range(2):
                    bx, by = ix + dx, iy + dy
                    if BORDER_WIDTH < bx < WIDTH - BORDER_WIDTH and BORDER_WIDTH < by < HEIGHT - BORDER_WIDTH:
                        if dx == 0 and dy == 0:
                            # Highlight pixel (brighter)
                            hr = min(255, int(r * 1.3))
                            hg = min(255, int(g * 1.3))
                            hb = min(255, int(b * 1.3))
                            pixels[bx, by] = (hr, hg, hb)
                        else:
                            pixels[bx, by] = (r, g, b)

    def move(self):
        self.x += self.vx
        self.y += self.vy
        self.vx *= FRICTION
        self.vy *= FRICTION

        # Boundary: keep within table borders
        min_x = BORDER_WIDTH + BALL_RADIUS
        max_x = WIDTH - BORDER_WIDTH - BALL_RADIUS
        min_y = BORDER_WIDTH + BALL_RADIUS
        max_y = HEIGHT - BORDER_WIDTH - BALL_RADIUS

        if self.x < min_x:
            self.x = float(min_x)
            self.vx = -self.vx * 0.8
        elif self.x > max_x:
            self.x = float(max_x)
            self.vx = -self.vx * 0.8

        if self.y < min_y:
            self.y = float(min_y)
            self.vy = -self.vy * 0.8
        elif self.y > max_y:
            self.y = float(max_y)
            self.vy = -self.vy * 0.8

    def check_collision(self, other):
        dx = self.x - other.x
        dy = self.y - other.y
        dist = math.hypot(dx, dy)
        min_dist = BALL_RADIUS * 2
        if self.is_cue or other.is_cue:
            min_dist = BALL_RADIUS + CUE_RADIUS

        if dist < min_dist and dist > 0:
            # Normal vector
            nx = dx / dist
            ny = dy / dist
            # Relative velocity
            dvx = self.vx - other.vx
            dvy = self.vy - other.vy
            # Relative velocity along normal
            dvn = dvx * nx + dvy * ny
            if dvn > 0:
                return  # Moving apart

            # Update velocities (equal mass elastic collision)
            self.vx -= dvn * nx
            self.vy -= dvn * ny
            other.vx += dvn * nx
            other.vy += dvn * ny

            # Separate balls to prevent sticking
            overlap = min_dist - dist
            self.x += nx * overlap / 2
            self.y += ny * overlap / 2
            other.x -= nx * overlap / 2
            other.y -= ny * overlap / 2

    def is_in_pocket(self, pockets):
        for px, py in pockets:
            if math.hypot(self.x - px, self.y - py) <= POCKET_RADIUS + 1:
                return True
        return False

    def is_moving(self):
        return abs(self.vx) > 0.02 or abs(self.vy) > 0.02

    def reset_position(self):
        self.x = float(self.initial_x)
        self.y = float(self.initial_y)
        self.vx = 0.0
        self.vy = 0.0


def _render_static_bg(pockets):
    """Pre-render table (felt + borders + pockets) to a PIL Image once."""
    bg = Image.new("RGB", (WIDTH, HEIGHT), FELT_GREEN)
    draw = ImageDraw.Draw(bg)
    for t in range(BORDER_WIDTH):
        c = BORDER_HIGHLIGHT if t == 0 else BORDER_BROWN
        draw.line([(0, t), (WIDTH-1, t)], fill=c)
        draw.line([(0, HEIGHT-1-t), (WIDTH-1, HEIGHT-1-t)], fill=c)
        draw.line([(t, 0), (t, HEIGHT-1)], fill=c)
        draw.line([(WIDTH-1-t, 0), (WIDTH-1-t, HEIGHT-1)], fill=c)
    for px, py in pockets:
        draw.ellipse([(px-POCKET_RADIUS, py-POCKET_RADIUS),
                      (px+POCKET_RADIUS, py+POCKET_RADIUS)], fill=POCKET_COLOR)
    return bg


def _draw_cue_stick(draw, cue_ball, target_angle, strength):
    """Draw a brief cue stick line behind the cue ball."""
    cx, cy = int(cue_ball.x), int(cue_ball.y)
    # Stick extends behind the ball (opposite of shot direction)
    stick_len = int(8 + strength * 5)
    for i in range(3, stick_len):
        sx = int(cx - math.cos(target_angle) * i)
        sy = int(cy - math.sin(target_angle) * i)
        if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
            # Gradient along stick
            fade = 1.0 - (i - 3) / max(stick_len - 3, 1)
            r = int(CUE_STICK_COLOR[0] * fade)
            g = int(CUE_STICK_COLOR[1] * fade)
            b = int(CUE_STICK_COLOR[2] * fade)
            draw.point((sx, sy), fill=(r, g, b))


def ai_play(balls, pockets):
    """AI selects and executes a shot. Returns the shot angle for cue animation."""
    cue_ball = balls[0]
    if len(balls) <= 1:
        return 0.0, 0.0

    # Find best target: closest ball to a pocket
    target_ball = min(
        balls[1:],
        key=lambda b: min(math.hypot(b.x - p[0], b.y - p[1]) for p in pockets)
    )

    # Find nearest pocket to target
    nearest_pocket = min(
        pockets,
        key=lambda p: math.hypot(target_ball.x - p[0], target_ball.y - p[1])
    )

    # Angle from target ball to pocket
    dx_tp = nearest_pocket[0] - target_ball.x
    dy_tp = nearest_pocket[1] - target_ball.y
    angle_to_pocket = math.atan2(dy_tp, dx_tp)

    # Angle from cue to target
    dx_ct = target_ball.x - cue_ball.x
    dy_ct = target_ball.y - cue_ball.y
    angle_to_target = math.atan2(dy_ct, dx_ct)

    # Adjust angle
    angle_offset = math.atan2(
        math.sin(angle_to_pocket - angle_to_target),
        math.cos(angle_to_pocket - angle_to_target)
    )
    optimal_angle = angle_to_target + angle_offset / 2

    # Strength based on distance
    distance = math.hypot(dx_ct, dy_ct)
    strength = min(max(distance / 10, AI_STRENGTH_MIN), AI_STRENGTH_MAX)

    # Add human-like randomness
    randomness = random.uniform(-0.12, 0.12)
    final_angle = optimal_angle + randomness

    cue_ball.vx = math.cos(final_angle) * strength
    cue_ball.vy = math.sin(final_angle) * strength

    return final_angle, strength


def main(matrix, _deadline=None):
    """Run one billiards game."""

    # Place balls in a triangle rack formation
    cx, cy = WIDTH // 2, HEIGHT // 2
    balls = [
        Ball(WIDTH // 4, cy, 0),       # Cue ball (white)
    ]

    # Rack balls in triangle at right side of table
    rack_x = 3 * WIDTH // 4
    rack_y = cy
    color_idx = 1
    for row in range(4):
        for col in range(row + 1):
            bx = rack_x + row * 4
            by = rack_y + (col - row / 2.0) * 4
            balls.append(Ball(bx, by, color_idx))
            color_idx = (color_idx % 7) + 1
            if color_idx == 0:
                color_idx = 1

    # Pockets: 4 corners + 2 side pockets
    pockets = [
        (BORDER_WIDTH, BORDER_WIDTH),                          # top-left
        (WIDTH - BORDER_WIDTH - 1, BORDER_WIDTH),              # top-right
        (BORDER_WIDTH, HEIGHT - BORDER_WIDTH - 1),             # bottom-left
        (WIDTH - BORDER_WIDTH - 1, HEIGHT - BORDER_WIDTH - 1), # bottom-right
        (WIDTH // 2, BORDER_WIDTH),                            # top-center
        (WIDTH // 2, HEIGHT - BORDER_WIDTH - 1),               # bottom-center
    ]

    _bg = _render_static_bg(pockets)

    shot_count = 0
    first_shot = True
    running = True

    while running:
        if _deadline is not None and time.time() >= _deadline:
            break
        if should_stop():
            break

        image = _bg.copy()
        pixels = image.load()

        # Check cue ball in pocket -> reset position
        if balls[0].is_in_pocket(pockets):
            balls[0].reset_position()
            balls[0].vx = 0.0
            balls[0].vy = 0.0

        # Remove pocketed balls (except cue)
        active_balls = [balls[0]]
        for ball in balls[1:]:
            if ball.is_in_pocket(pockets):
                ball.pocketed = True
            else:
                active_balls.append(ball)
        balls = active_balls

        # Move all balls
        for ball in balls:
            ball.move()

        # Check collisions
        for i in range(len(balls)):
            for j in range(i + 1, len(balls)):
                balls[i].check_collision(balls[j])

        # Draw all balls
        for ball in balls:
            ball.draw(pixels)

        # Check if all balls stopped
        if not any(ball.is_moving() for ball in balls):
            if first_shot or shot_count < MAX_SHOTS:
                # Show cue stick animation before shot
                shot_angle, strength = ai_play(balls, pockets)

                if first_shot or random.random() < 0.3:  # Show cue stick sometimes
                    # Animate cue stick for a few frames
                    for anim_frame in range(6):
                        if should_stop():
                            return
                        frame = _bg.copy()
                        fp = frame.load()
                        for ball in balls:
                            ball.draw(fp)
                        pull_back = 1.0 + (5 - anim_frame) * 0.5  # Pull back then strike
                        _draw_cue_stick(ImageDraw.Draw(frame), balls[0], shot_angle, pull_back)
                        matrix.SetImage(frame)
                        if _deadline is not None and time.time() >= _deadline:
                            return
                        if not interruptible_sleep(0.04): return

                shot_count += 1
                first_shot = False

        # Win condition: only cue ball left
        if len(balls) <= 1:
            running = False

        if shot_count >= MAX_SHOTS:
            running = False

        matrix.SetImage(image)


def run(matrix, duration=60):
    """Run the Billiards display feature for the specified duration.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    start_time = time.time()
    deadline = start_time + duration
    try:
        while time.time() < deadline:
            if should_stop():
                break
            main(matrix, _deadline=deadline)
            if not interruptible_sleep(1): return
    except Exception as e:
        logger.error("Error in billiards: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
