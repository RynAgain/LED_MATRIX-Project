"""
Snake -- AI-driven with visual effects on 64x64 LED matrix.

Features:
- Uniform 1x1 pixel segments for classic snake look
- Head distinguished by bright white color, body gradient green
- Pulsing food effect (color pulse, 1x1 pixel)
- Food color: bright red, occasional golden food worth double points
- Death animation (body turns red one segment at a time)
- Score/length display in corner using small pixel font
- Faster frame rate for smoother movement
- Autonomous AI gameplay
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 15  # Faster than original 10fps for smoother movement
FRAME_DUR = 1.0 / FPS
BG_COLOR = (0, 0, 0)

# Snake colors (gradient from head to tail)
HEAD_COLOR = (255, 255, 255)  # Bright white head for visibility
BODY_COLOR_HEAD = (0, 255, 50)  # Bright green near head
TAIL_COLOR = (0, 60, 15)

# Food colors
FOOD_RED = (255, 20, 20)
FOOD_GOLD = (255, 215, 0)

# Death color
DEATH_COLOR = (200, 0, 0)

# Directions
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
DIRECTIONS = [UP, DOWN, LEFT, RIGHT]

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


def _draw_digit(image, digit_char, x, y, color):
    """Draw a 3x5 pixel digit at position (x, y)."""
    rows = DIGITS.get(digit_char, DIGITS['0'])
    for row_idx, row_bits in enumerate(rows):
        for col_idx in range(3):
            if row_bits & (1 << (2 - col_idx)):
                px = x + col_idx
                py = y + row_idx
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    image.putpixel((px, py), color)


def _draw_number(image, number, x, y, color):
    """Draw a multi-digit number at position (x, y)."""
    digits = str(number)
    for i, ch in enumerate(digits):
        _draw_digit(image, ch, x + i * 4, y, color)


def _lerp_color(c1, c2, t):
    """Linearly interpolate between two colors."""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _opposite(d):
    """Return the opposite direction."""
    return (-d[0], -d[1])


class SnakeGame:
    def __init__(self):
        self.reset()

    def reset(self):
        cx, cy = SIZE // 2, SIZE // 2
        self.snake = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
        self.direction = RIGHT
        self.food = None
        self.food_is_gold = False
        self.score = 0
        self.alive = True
        self.frame_count = 0
        self._place_food()

    def _place_food(self):
        """Place food at a random position not on the snake."""
        snake_set = set(self.snake)
        attempts = 0
        while attempts < 1000:
            pos = (random.randint(1, SIZE - 2), random.randint(1, SIZE - 2))
            if pos not in snake_set:
                self.food = pos
                # 15% chance of golden food
                self.food_is_gold = random.random() < 0.15
                return
            attempts += 1
        # Fallback
        self.food = (SIZE // 4, SIZE // 4)
        self.food_is_gold = False

    def _ai_decide(self):
        """AI pathfinding: move towards food while avoiding self-collision."""
        head = self.snake[0]
        hx, hy = head
        fx, fy = self.food

        # Score each possible direction
        snake_set = set(self.snake)
        best_dir = self.direction
        best_score = -999

        for d in DIRECTIONS:
            # Don't reverse into ourselves
            if d == _opposite(self.direction):
                continue

            nx, ny = hx + d[0], hy + d[1]

            # Wall collision check
            if nx < 0 or nx >= SIZE or ny < 0 or ny >= SIZE:
                continue

            # Self collision check (exclude tail since it will move)
            body_check = set(self.snake[:-1])
            if (nx, ny) in body_check:
                continue

            # Manhattan distance to food (lower is better)
            dist = abs(nx - fx) + abs(ny - fy)
            score = -dist

            # Count accessible neighbors (flood fill lite -- prefer open spaces)
            neighbors_free = 0
            for nd in DIRECTIONS:
                nnx, nny = nx + nd[0], ny + nd[1]
                if 0 <= nnx < SIZE and 0 <= nny < SIZE and (nnx, nny) not in body_check:
                    neighbors_free += 1
            score += neighbors_free * 0.5

            if score > best_score:
                best_score = score
                best_dir = d

        self.direction = best_dir

    def step(self):
        """Advance the game by one frame."""
        if not self.alive:
            return

        self._ai_decide()
        self.frame_count += 1

        hx, hy = self.snake[0]
        dx, dy = self.direction
        new_head = (hx + dx, hy + dy)

        # Wall collision
        if new_head[0] < 0 or new_head[0] >= SIZE or new_head[1] < 0 or new_head[1] >= SIZE:
            self.alive = False
            return

        # Self collision
        if new_head in set(self.snake[:-1]):
            self.alive = False
            return

        # Move
        self.snake.insert(0, new_head)

        # Food check
        if new_head == self.food:
            points = 2 if self.food_is_gold else 1
            self.score += points
            self._place_food()
        else:
            self.snake.pop()

    def draw(self, matrix, pulse_phase=0.0):
        """Render the game state."""
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)

        # Draw snake body with gradient (all 1x1 pixels)
        num_segments = len(self.snake)
        for i, (sx, sy) in enumerate(self.snake):
            if i == 0:
                continue  # head drawn separately with distinct color
            t = i / max(num_segments - 1, 1)
            color = _lerp_color(BODY_COLOR_HEAD, TAIL_COLOR, t)
            if 0 <= sx < SIZE and 0 <= sy < SIZE:
                image.putpixel((sx, sy), color)

        # Draw head as 1x1 pixel with bright white color
        hx, hy = self.snake[0]
        if 0 <= hx < SIZE and 0 <= hy < SIZE:
            image.putpixel((hx, hy), HEAD_COLOR)

        # Draw food as 1x1 pixel with pulsing color
        if self.food:
            fx, fy = self.food
            base_color = FOOD_GOLD if self.food_is_gold else FOOD_RED
            pulse = 0.6 + 0.4 * math.sin(pulse_phase)
            food_color = tuple(int(c * pulse) for c in base_color)

            if 0 <= fx < SIZE and 0 <= fy < SIZE:
                image.putpixel((fx, fy), food_color)

        # Draw score in top-left corner
        score_color = (200, 200, 200)
        _draw_number(image, self.score, 1, 1, score_color)

        matrix.SetImage(image)

    def draw_death(self, matrix):
        """Animate death: snake body turns red one segment at a time."""
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)

        # Draw full snake in current colors first
        num_segments = len(self.snake)
        colors = [HEAD_COLOR]  # head color
        for i in range(1, num_segments):
            t = i / max(num_segments - 1, 1)
            colors.append(_lerp_color(BODY_COLOR_HEAD, TAIL_COLOR, t))

        # Animate each segment turning red
        segments_per_frame = max(1, num_segments // 20)  # complete in ~20 frames
        red_count = 0

        while red_count < num_segments:
            image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
            red_count = min(red_count + segments_per_frame, num_segments)

            for i, (sx, sy) in enumerate(self.snake):
                if i < red_count:
                    color = DEATH_COLOR
                else:
                    color = colors[i]
                if 0 <= sx < SIZE and 0 <= sy < SIZE:
                    image.putpixel((sx, sy), color)

            # Score
            _draw_number(image, self.score, 1, 1, (200, 200, 200))
            matrix.SetImage(image)
            time.sleep(FRAME_DUR)

        # Hold death frame briefly
        time.sleep(0.5)


def run(matrix, duration=60):
    """Run the Snake display feature for the specified duration.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    start_time = time.time()
    try:
        while time.time() - start_time < duration:
            game = SnakeGame()
            pulse_phase = 0.0

            while game.alive and time.time() - start_time < duration:
                frame_start = time.time()
                game.step()
                game.draw(matrix, pulse_phase)
                pulse_phase += 0.4  # pulse speed

                elapsed = time.time() - frame_start
                sleep_time = FRAME_DUR - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # Death animation
            if not game.alive and time.time() - start_time < duration:
                game.draw_death(matrix)

            # Brief pause between games
            time.sleep(0.5)

    except Exception as e:
        logger.error("Error in snake: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
