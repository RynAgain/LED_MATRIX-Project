"""Third-person 3D Snake with autonomous demo and controller play.

Left/right turn relative to the chase camera once per press; release to rearm.
Up or neutral continues forward, and down cannot reverse into the neck.
Start+Select (or hold Start) returns to the menu. Interactive play is one round;
the demo restarts automatically. Movement remains on the classic flat board.
"""

from collections import deque

import random
import logging
import time
from src.display._shared import (
    should_stop,
    interruptible_sleep,
    read_direction,
    safe_rumble,
    show_banner,
)
from src.display.snake_scene import render

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 15  # Faster than original 10fps for smoother movement
FRAME_DUR = 1.0 / FPS
INPUT_INTERVAL = 1.0 / 120
# Directions
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
DIRECTIONS = [UP, DOWN, LEFT, RIGHT]


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

    def step(self, direction=None):
        """Advance the game by one frame.

        :param direction: when ``None`` (DEMO) the autonomous AI chooses the next
            heading via :meth:`_ai_decide`. When a ``(dx, dy)`` tuple is supplied
            (INTERACTIVE) it becomes the requested heading, except a 180-degree
            reversal into the neck is rejected (the current heading is kept).
        """
        if not self.alive:
            return

        if direction is None:
            self._ai_decide()
        else:
            # Reject reversals; ignore unknown vectors and keep current heading.
            if direction in DIRECTIONS and direction != _opposite(self.direction):
                self.direction = direction
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
        matrix.SetImage(render(self, pulse_phase, board_size=SIZE))

    def draw_death(self, matrix):
        segments_per_frame = max(1, len(self.snake) // 20)
        red_count = 0
        while red_count < len(self.snake):
            if should_stop():
                return
            red_count = min(red_count + segments_per_frame, len(self.snake))
            matrix.SetImage(render(self, red_count=red_count, board_size=SIZE))
            interruptible_sleep(FRAME_DUR)
        interruptible_sleep(0.5)


# Generous safety cap (seconds) for INTERACTIVE play so a forgotten game can't
# run forever; the player normally exits via game-over or the quit gesture.
_INTERACTIVE_MAX_SECONDS = 3600


def _run_demo(matrix, duration, start_time):
    """Autonomous DEMO loop (unchanged behavior)."""
    while time.time() - start_time < duration:
        if should_stop():
            break
        game = SnakeGame()
        pulse_phase = 0.0

        while game.alive and time.time() - start_time < duration:
            if should_stop():
                break
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
        interruptible_sleep(0.5)


def _run_interactive(matrix, controller, start_time):
    """INTERACTIVE loop: the player steers one round; see module docstring."""
    from src.input.controller import wants_quit

    show_banner(matrix, ["SNAKE", "READY"], hold=0.8)

    game = SnakeGame()
    pulse_phase = 0.0
    held_turn = None
    turns = deque()
    next_step = time.monotonic()

    while game.alive and time.time() - start_time < _INTERACTIVE_MAX_SECONDS:
        if should_stop():
            return
        controller.poll_events()
        if wants_quit(controller):
            return

        d = read_direction(controller, cardinal_only=True)
        turn = d if d in (LEFT, RIGHT) else None
        if turn is not None and turn != held_turn and len(turns) < 2:
            turns.append(turn)
        held_turn = turn

        now = time.monotonic()
        if now >= next_step:
            requested = game.direction
            if turns:
                dx, dy = game.direction
                requested = (dy, -dx) if turns.popleft() == LEFT else (-dy, dx)
            game.step(direction=requested)
            game.draw(matrix, pulse_phase)
            pulse_phase += 0.4
            next_step = now + FRAME_DUR

        remaining = next_step - time.monotonic()
        if remaining > 0:
            time.sleep(min(INPUT_INTERVAL, remaining))

    # Game over: animation + feedback, then return to the menu (no auto-restart).
    if not game.alive:
        game.draw_death(matrix)
        safe_rumble(controller, 0.8, 300)
        show_banner(matrix, ["GAME OVER", f"SCORE {game.score}"],
                    color=(255, 80, 80), hold=1.5)


def run(matrix, duration=60, controller=None):
    """Run the Snake feature.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds (DEMO mode only; INTERACTIVE play
            is bounded by game-over / the quit gesture, with a generous safety
            cap of :data:`_INTERACTIVE_MAX_SECONDS`).
        controller: optional :class:`src.input.Controller`. ``None`` -> DEMO
            (autonomous AI, unchanged). Not-None -> INTERACTIVE (player control).
    """
    start_time = time.time()
    try:
        if controller is None:
            _run_demo(matrix, duration, start_time)
        else:
            _run_interactive(matrix, controller, start_time)
    except Exception as e:
        logger.error("Error in snake: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
