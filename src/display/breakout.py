"""
Breakout -- Classic brick-breaking game on 64x64 LED matrix.

Features:
- 5 rows of colored bricks at the top
- AI-controlled paddle at the bottom
- Ball trail effect with fading
- Ball color changes on each bounce
- Ball speed increases as bricks are destroyed
- Score display
- Auto-resets when all bricks are cleared or ball is lost
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 30
FRAME_DUR = 1.0 / FPS

# Colors
BG_COLOR = (0, 0, 0)
BORDER_COLOR = (15, 15, 50)
PADDLE_COLOR = (80, 180, 255)

# Brick colors (one per row, top to bottom)
BRICK_COLORS = [
    (255, 50, 50),     # red
    (255, 140, 40),    # orange
    (255, 230, 50),    # yellow
    (50, 220, 50),     # green
    (50, 130, 255),    # blue
]

# Ball color cycle
BALL_COLORS = [
    (255, 255, 80),    # yellow
    (80, 255, 80),     # green
    (255, 80, 255),    # magenta
    (80, 255, 255),    # cyan
    (255, 160, 40),    # orange
    (255, 80, 80),     # red
    (120, 120, 255),   # light blue
]

# Layout
BRICK_ROWS = 5
BRICK_COLS = 8
BRICK_W = 7          # pixels wide (8 cols * 7 = 56, + gaps)
BRICK_H = 3          # pixels tall
BRICK_GAP = 1        # gap between bricks
BRICK_AREA_TOP = 6   # y offset for first row of bricks
PADDLE_Y = SIZE - 6  # paddle vertical position
PADDLE_WIDTH = 12
PADDLE_HEIGHT = 2
BALL_SIZE = 2
TRAIL_LENGTH = 4

# Small 3x5 digit font bitmaps (same as pong)
DIGITS = {
    '0': [0b111, 0b101, 0b101, 0b101, 0b111],
    '1': [0b010, 0b110, 0b010, 0b010, 0b111],
    '2': [0b111, 0b001, 0b111, 0b100, 0b111],
    '3': [0b111, 0b001, 0b111, 0b001, 0b111],
    '4': [0b101, 0b101, 0b111, 0b001, 0b001],
    '5': [0b111, 0b100, 0b111, 0b001, 0b111],
    '6': [0b111, 0b100, 0b111, 0b101, 0b111],
    '7': [0b111, 0b001, 0b010, 0b010, 0b010],
    '8': [0b111, 0b101, 0b111, 0b101, 0b111],
    '9': [0b111, 0b101, 0b111, 0b001, 0b111],
}


def _draw_digit(image, ch, x, y, color):
    """Draw a 3x5 pixel digit."""
    rows = DIGITS.get(ch, DIGITS['0'])
    for ri, bits in enumerate(rows):
        for ci in range(3):
            if bits & (1 << (2 - ci)):
                px, py = x + ci, y + ri
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    image.putpixel((px, py), color)


def _draw_number(image, number, x, y, color):
    """Draw a multi-digit number."""
    digits = str(number)
    for i, ch in enumerate(digits):
        _draw_digit(image, ch, x + i * 4, y, color)


def _scale_color(color, factor):
    """Scale a color by a factor."""
    return tuple(max(0, min(255, int(c * factor))) for c in color)


class BreakoutGame:
    def __init__(self):
        self.score = 0
        self.lives = 3
        self._init_bricks()
        self._reset_ball()

    def _init_bricks(self):
        """Create the brick grid. Each brick is (row, col, alive)."""
        self.bricks = []
        for row in range(BRICK_ROWS):
            for col in range(BRICK_COLS):
                self.bricks.append({
                    "row": row,
                    "col": col,
                    "alive": True,
                })

    def _reset_ball(self):
        """Reset ball to center above paddle."""
        self.ball_x = float(SIZE // 2)
        self.ball_y = float(PADDLE_Y - 8)
        # Random angle upward
        angle = random.uniform(-0.8, 0.8)
        speed = 1.2
        self.ball_vx = speed * math.sin(angle)
        self.ball_vy = -speed * math.cos(angle)  # upward
        self.ball_speed = speed
        self.paddle_x = float((SIZE - PADDLE_WIDTH) // 2)
        self.ball_color_idx = random.randint(0, len(BALL_COLORS) - 1)
        self.trail = []

    def _bounce_color(self):
        """Cycle to next ball color."""
        self.ball_color_idx = (self.ball_color_idx + 1) % len(BALL_COLORS)

    def _brick_rect(self, brick):
        """Get pixel rectangle (x1, y1, x2, y2) for a brick."""
        col = brick["col"]
        row = brick["row"]
        x1 = 1 + col * (BRICK_W + BRICK_GAP)
        y1 = BRICK_AREA_TOP + row * (BRICK_H + BRICK_GAP)
        x2 = x1 + BRICK_W - 1
        y2 = y1 + BRICK_H - 1
        return x1, y1, x2, y2

    def _check_brick_collision(self):
        """Check if ball hits any brick. Returns True if a brick was hit."""
        bx = int(self.ball_x)
        by = int(self.ball_y)

        for brick in self.bricks:
            if not brick["alive"]:
                continue

            x1, y1, x2, y2 = self._brick_rect(brick)

            # Check if ball overlaps brick
            if (bx + BALL_SIZE > x1 and bx < x2 + 1 and
                    by + BALL_SIZE > y1 and by < y2 + 1):
                brick["alive"] = False
                self.score += (BRICK_ROWS - brick["row"]) * 10  # top rows worth more

                # Determine bounce direction
                # Find which side the ball hit
                overlap_left = (bx + BALL_SIZE) - x1
                overlap_right = (x2 + 1) - bx
                overlap_top = (by + BALL_SIZE) - y1
                overlap_bottom = (y2 + 1) - by

                min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)

                if min_overlap == overlap_top or min_overlap == overlap_bottom:
                    self.ball_vy = -self.ball_vy
                else:
                    self.ball_vx = -self.ball_vx

                self._bounce_color()

                # Speed up slightly with each brick destroyed
                self.ball_speed = min(3.0, self.ball_speed + 0.02)
                speed_ratio = self.ball_speed / math.sqrt(
                    self.ball_vx ** 2 + self.ball_vy ** 2 + 0.001)
                self.ball_vx *= speed_ratio
                self.ball_vy *= speed_ratio

                return True
        return False

    def _move_paddle_ai(self):
        """AI paddle tracks the ball with slight imperfection."""
        target_x = self.ball_x - PADDLE_WIDTH / 2.0
        max_speed = 2.5

        diff = target_x - self.paddle_x
        diff += random.uniform(-0.5, 0.5)  # slight imperfection
        move = max(-max_speed, min(max_speed, diff))
        self.paddle_x += move
        self.paddle_x = max(1.0, min(float(SIZE - PADDLE_WIDTH - 1), self.paddle_x))

    def all_bricks_cleared(self):
        """Check if all bricks are destroyed."""
        return not any(b["alive"] for b in self.bricks)

    def step(self):
        """Advance one game frame. Returns 'playing', 'lost_life', or 'cleared'."""
        # Store trail
        self.trail.append((self.ball_x, self.ball_y))
        if len(self.trail) > TRAIL_LENGTH:
            self.trail.pop(0)

        # Move ball
        self.ball_x += self.ball_vx
        self.ball_y += self.ball_vy

        # Wall bounces (left, right, top)
        if self.ball_x <= 1:
            self.ball_x = 1.0
            self.ball_vx = abs(self.ball_vx)
            self._bounce_color()
        elif self.ball_x >= SIZE - BALL_SIZE - 1:
            self.ball_x = float(SIZE - BALL_SIZE - 1)
            self.ball_vx = -abs(self.ball_vx)
            self._bounce_color()

        if self.ball_y <= 1:
            self.ball_y = 1.0
            self.ball_vy = abs(self.ball_vy)
            self._bounce_color()

        # Paddle collision
        px = int(self.paddle_x)
        if (self.ball_vy > 0 and
                self.ball_y + BALL_SIZE >= PADDLE_Y and
                self.ball_y + BALL_SIZE <= PADDLE_Y + PADDLE_HEIGHT + 2 and
                self.ball_x + BALL_SIZE > px and
                self.ball_x < px + PADDLE_WIDTH):
            self.ball_y = float(PADDLE_Y - BALL_SIZE)
            # Angle based on where ball hits paddle
            hit_pos = (self.ball_x - self.paddle_x) / PADDLE_WIDTH
            angle = (hit_pos - 0.5) * 1.4  # -0.7 to 0.7 radians
            self.ball_vx = self.ball_speed * math.sin(angle)
            self.ball_vy = -self.ball_speed * math.cos(angle)
            self._bounce_color()

        # Brick collision
        self._check_brick_collision()

        # Ball falls below paddle - lose life
        if self.ball_y > SIZE:
            self.lives -= 1
            if self.lives > 0:
                self._reset_ball()
                return "lost_life"
            else:
                return "game_over"

        # All bricks cleared
        if self.all_bricks_cleared():
            return "cleared"

        # Move paddle
        self._move_paddle_ai()

        return "playing"

    def draw(self, matrix):
        """Render the game state."""
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Border
        draw.rectangle([(0, 0), (SIZE - 1, SIZE - 1)], outline=BORDER_COLOR)

        # Score (top-left) and lives (top-right) -- use the 1-pixel border area
        _draw_number(image, self.score, 2, 1, (200, 200, 200))

        # Lives as small dots
        for i in range(self.lives):
            lx = SIZE - 4 - i * 4
            image.putpixel((lx, 2), (255, 80, 80))
            image.putpixel((lx + 1, 2), (255, 80, 80))
            image.putpixel((lx, 3), (255, 80, 80))
            image.putpixel((lx + 1, 3), (255, 80, 80))

        # Bricks
        for brick in self.bricks:
            if not brick["alive"]:
                continue
            x1, y1, x2, y2 = self._brick_rect(brick)
            color = BRICK_COLORS[brick["row"] % len(BRICK_COLORS)]
            draw.rectangle([(x1, y1), (x2, y2)], fill=color)

        # Paddle (with subtle gradient)
        px = int(self.paddle_x)
        for i in range(PADDLE_WIDTH):
            dist = abs(i - PADDLE_WIDTH / 2.0) / (PADDLE_WIDTH / 2.0)
            brightness = 1.0 - 0.3 * dist
            c = _scale_color(PADDLE_COLOR, brightness)
            for h in range(PADDLE_HEIGHT):
                cx = px + i
                cy = PADDLE_Y + h
                if 0 <= cx < SIZE and 0 <= cy < SIZE:
                    image.putpixel((cx, cy), c)

        # Ball trail
        ball_color = BALL_COLORS[self.ball_color_idx]
        for i, (tx, ty) in enumerate(self.trail):
            fade = (i + 1) / (TRAIL_LENGTH + 1)
            trail_color = _scale_color(ball_color, fade * 0.4)
            bx, by = int(tx), int(ty)
            for ox in range(BALL_SIZE):
                for oy in range(BALL_SIZE):
                    ppx, ppy = bx + ox, by + oy
                    if 0 <= ppx < SIZE and 0 <= ppy < SIZE:
                        image.putpixel((ppx, ppy), trail_color)

        # Ball
        speed_factor = min(1.0, self.ball_speed / 3.0)
        intensity = 0.6 + 0.4 * speed_factor
        actual_color = _scale_color(ball_color, intensity)
        bx, by = int(self.ball_x), int(self.ball_y)
        for ox in range(BALL_SIZE):
            for oy in range(BALL_SIZE):
                ppx, ppy = bx + ox, by + oy
                if 0 <= ppx < SIZE and 0 <= ppy < SIZE:
                    image.putpixel((ppx, ppy), actual_color)

        matrix.SetImage(image)


def run(matrix, duration=60):
    """Run the Breakout display feature for the specified duration.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break

            game = BreakoutGame()

            while time.time() - start_time < duration:
                if should_stop():
                    break

                frame_start = time.time()
                result = game.step()
                game.draw(matrix)

                if result == "cleared":
                    # Flash and reset bricks, keep score
                    time.sleep(1.0)
                    old_score = game.score
                    old_lives = game.lives
                    game._init_bricks()
                    game._reset_ball()
                    game.score = old_score
                    game.lives = old_lives

                elif result == "lost_life":
                    # Brief pause on life loss
                    time.sleep(0.5)

                elif result == "game_over":
                    # Show final score briefly, then restart
                    game.draw(matrix)
                    time.sleep(2.0)
                    break

                elapsed = time.time() - frame_start
                sleep_time = FRAME_DUR - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in breakout: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
