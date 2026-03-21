"""
Pong -- AI vs AI with visual effects on 64x64 LED matrix.

Features:
- Ball trail effect (last 5 positions drawn with fading brightness)
- Score display at top (each player's score in their color)
- Ball color changes on each bounce (cycles through bright colors)
- Paddles drawn with gradient (bright center, dim edges)
- Center line drawn as dashed line
- Ball speed indicator (color intensity = speed)
- Court boundary drawn in dim blue
- AI vs AI gameplay
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 30
FRAME_DUR = 1.0 / FPS

# Colors
BG_COLOR = (0, 0, 0)
COURT_BORDER = (15, 15, 50)        # dim blue border
CENTER_LINE = (20, 20, 60)         # dim blue dashed line
P1_COLOR = (80, 180, 255)          # player 1 (left) - blue
P2_COLOR = (255, 100, 80)          # player 2 (right) - red/orange

# Ball color cycle
BALL_COLORS = [
    (255, 255, 80),   # yellow
    (80, 255, 80),    # green
    (255, 80, 255),   # magenta
    (80, 255, 255),   # cyan
    (255, 160, 40),   # orange
    (255, 80, 80),    # red
    (120, 120, 255),  # light blue
]

# Paddle settings
PADDLE_WIDTH = 2
PADDLE_X_LEFT = 3
PADDLE_X_RIGHT = SIZE - 4
INITIAL_PADDLE_HEIGHT = 10
MIN_PADDLE_HEIGHT = 4

# Ball settings
BALL_SIZE = 2
TRAIL_LENGTH = 5

# Small 3x5 digit font bitmaps
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


def _lerp_color(c1, c2, t):
    """Linearly interpolate between two colors."""
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _scale_color(color, factor):
    """Scale a color by a factor."""
    return tuple(max(0, min(255, int(c * factor))) for c in color)


class PongGame:
    def __init__(self):
        self.reset()

    def reset(self):
        self.p1_score = 0
        self.p2_score = 0
        self.paddle_height = INITIAL_PADDLE_HEIGHT
        self.pass_count = 0
        self._reset_round()

    def _reset_round(self):
        self.ball_x = float(SIZE // 2)
        self.ball_y = float(SIZE // 2)
        angle = random.uniform(-0.5, 0.5)
        direction = random.choice([-1, 1])
        speed = 1.0
        self.ball_vx = direction * speed * math.cos(angle)
        self.ball_vy = speed * math.sin(angle)
        self.ball_speed = speed
        self.p1_y = float((SIZE - self.paddle_height) // 2)
        self.p2_y = float((SIZE - self.paddle_height) // 2)
        self.ball_color_idx = random.randint(0, len(BALL_COLORS) - 1)
        self.trail = []
        self.round_over = False

    def _bounce_color(self):
        """Cycle to next ball color."""
        self.ball_color_idx = (self.ball_color_idx + 1) % len(BALL_COLORS)

    def _move_paddle_ai(self, paddle_y, is_left):
        """AI paddle movement with slight imperfection."""
        # Target the ball's y position
        target_y = self.ball_y - self.paddle_height / 2.0
        max_speed = 2.0

        # Add slight reaction delay -- only track when ball is coming toward us
        ball_coming = (is_left and self.ball_vx < 0) or (not is_left and self.ball_vx > 0)

        if ball_coming:
            diff = target_y - paddle_y
            # Add slight randomness for imperfect play
            diff += random.uniform(-1.0, 1.0)
            move = max(-max_speed, min(max_speed, diff))
        else:
            # Drift toward center when ball going away
            center = (SIZE - self.paddle_height) / 2.0
            diff = center - paddle_y
            move = max(-0.5, min(0.5, diff))
            # Occasional random twitch
            if random.random() < 0.05:
                move += random.uniform(-1.0, 1.0)

        paddle_y += move
        paddle_y = max(0.0, min(float(SIZE - self.paddle_height), paddle_y))
        return paddle_y

    def step(self):
        """Advance one game frame."""
        if self.round_over:
            return

        # Store trail position
        self.trail.append((self.ball_x, self.ball_y))
        if len(self.trail) > TRAIL_LENGTH:
            self.trail.pop(0)

        # Move ball
        self.ball_x += self.ball_vx
        self.ball_y += self.ball_vy

        # Top/bottom bounce
        if self.ball_y <= 1:
            self.ball_y = 1
            self.ball_vy = abs(self.ball_vy)
            self._bounce_color()
        elif self.ball_y >= SIZE - BALL_SIZE - 1:
            self.ball_y = float(SIZE - BALL_SIZE - 1)
            self.ball_vy = -abs(self.ball_vy)
            self._bounce_color()

        # Left paddle collision
        if (self.ball_x <= PADDLE_X_LEFT + PADDLE_WIDTH and
                self.ball_vx < 0 and
                self.p1_y <= self.ball_y + BALL_SIZE and
                self.ball_y <= self.p1_y + self.paddle_height):
            self.ball_x = float(PADDLE_X_LEFT + PADDLE_WIDTH)
            # Angle based on where ball hits paddle
            hit_pos = (self.ball_y - self.p1_y) / self.paddle_height
            angle = (hit_pos - 0.5) * 1.2  # -0.6 to 0.6 radians
            self.ball_speed = min(3.0, self.ball_speed + 0.1)
            self.ball_vx = self.ball_speed * math.cos(angle)
            self.ball_vy = self.ball_speed * math.sin(angle)
            self._bounce_color()
            self.pass_count += 1

        # Right paddle collision
        elif (self.ball_x + BALL_SIZE >= PADDLE_X_RIGHT and
              self.ball_vx > 0 and
              self.p2_y <= self.ball_y + BALL_SIZE and
              self.ball_y <= self.p2_y + self.paddle_height):
            self.ball_x = float(PADDLE_X_RIGHT - BALL_SIZE)
            hit_pos = (self.ball_y - self.p2_y) / self.paddle_height
            angle = math.pi - (hit_pos - 0.5) * 1.2
            self.ball_speed = min(3.0, self.ball_speed + 0.1)
            self.ball_vx = self.ball_speed * math.cos(angle)
            self.ball_vy = self.ball_speed * math.sin(angle)
            self._bounce_color()
            self.pass_count += 1

        # Shrink paddles after many passes
        if self.pass_count >= 12:
            self.paddle_height = max(MIN_PADDLE_HEIGHT, self.paddle_height - 1)
            self.pass_count = 0

        # Ball out of bounds - scoring
        if self.ball_x < 0:
            self.p2_score += 1
            self.round_over = True
        elif self.ball_x > SIZE:
            self.p1_score += 1
            self.round_over = True

        # Move paddles
        self.p1_y = self._move_paddle_ai(self.p1_y, True)
        self.p2_y = self._move_paddle_ai(self.p2_y, False)

    def draw(self, matrix):
        """Render the game state."""
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Court boundary (dim blue rectangle)
        draw.rectangle([(0, 0), (SIZE - 1, SIZE - 1)], outline=COURT_BORDER)

        # Center dashed line
        for y in range(2, SIZE - 2, 4):
            draw.line([(SIZE // 2, y), (SIZE // 2, min(y + 2, SIZE - 2))], fill=CENTER_LINE)

        # Scores at top (leave room for border)
        _draw_number(image, self.p1_score, SIZE // 4 - 2, 3, P1_COLOR)
        _draw_number(image, self.p2_score, 3 * SIZE // 4 - 2, 3, P2_COLOR)

        # Draw paddles with gradient (bright center, dim edges)
        for paddle_x, paddle_y, color in [
            (PADDLE_X_LEFT, self.p1_y, P1_COLOR),
            (PADDLE_X_RIGHT, self.p2_y, P2_COLOR)
        ]:
            py = int(paddle_y)
            mid = self.paddle_height / 2.0
            for i in range(self.paddle_height):
                # Gradient: brightest at center, dimmer at edges
                dist_from_center = abs(i - mid) / mid
                brightness = 1.0 - 0.5 * dist_from_center
                c = _scale_color(color, brightness)
                y = py + i
                if 0 <= y < SIZE:
                    for wx in range(PADDLE_WIDTH):
                        px = paddle_x + wx
                        if 0 <= px < SIZE:
                            image.putpixel((px, y), c)

        # Draw ball trail (fading previous positions)
        ball_color = BALL_COLORS[self.ball_color_idx]
        for i, (tx, ty) in enumerate(self.trail):
            fade = (i + 1) / (TRAIL_LENGTH + 1)  # 0.16 to 0.83
            trail_color = _scale_color(ball_color, fade * 0.5)
            bx, by = int(tx), int(ty)
            for ox in range(BALL_SIZE):
                for oy in range(BALL_SIZE):
                    px, py = bx + ox, by + oy
                    if 0 <= px < SIZE and 0 <= py < SIZE:
                        image.putpixel((px, py), trail_color)

        # Draw ball (brightness based on speed)
        speed_factor = min(1.0, self.ball_speed / 3.0)
        intensity = 0.6 + 0.4 * speed_factor
        actual_color = _scale_color(ball_color, intensity)
        bx, by = int(self.ball_x), int(self.ball_y)
        for ox in range(BALL_SIZE):
            for oy in range(BALL_SIZE):
                px, py = bx + ox, by + oy
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    image.putpixel((px, py), actual_color)

        matrix.SetImage(image)


def run(matrix, duration=60):
    """Run the Pong display feature for the specified duration.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    start_time = time.time()
    try:
        while time.time() - start_time < duration:
            game = PongGame()

            while not game.round_over and time.time() - start_time < duration:
                frame_start = time.time()
                game.step()
                game.draw(matrix)

                elapsed = time.time() - frame_start
                sleep_time = FRAME_DUR - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            if game.round_over and time.time() - start_time < duration:
                # Flash the score briefly
                game.draw(matrix)
                time.sleep(0.8)

                # Reset round but keep scores
                old_p1 = game.p1_score
                old_p2 = game.p2_score
                old_ph = game.paddle_height
                old_pc = game.pass_count
                game._reset_round()
                game.p1_score = old_p1
                game.p2_score = old_p2
                game.paddle_height = old_ph
                game.pass_count = old_pc

                # Reset game after someone reaches 5
                if game.p1_score >= 5 or game.p2_score >= 5:
                    # Show final score for a moment
                    game.draw(matrix)
                    time.sleep(1.5)
                    game.reset()

    except Exception as e:
        logger.error("Error in pong: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
