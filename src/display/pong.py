"""
Pong -- AI vs AI (demo) or player-vs-AI (interactive) on a 64x64 LED matrix.

Features:
- Ball trail effect (last 5 positions drawn with fading brightness)
- Score display at top (each player's score in their color)
- Ball color changes on each bounce (cycles through bright colors)
- Paddles drawn with gradient (bright center, dim edges)
- Center line drawn as dashed line
- Ball speed indicator (color intensity = speed)
- Court boundary drawn in dim blue
- AI vs AI gameplay (DEMO) or player vs AI (INTERACTIVE)

Control scheme (INTERACTIVE mode, ``controller is not None``)
------------------------------------------------------------
- **UP / DOWN** (D-pad or analog Y) move the **left** paddle; level-polled via
  ``get_direction`` so holding moves continuously. The **right** paddle stays
  AI-controlled.
- **Start + Select** (or hold Start ~1.5s) quits to the menu at any time, via
  :func:`src.input.controller.wants_quit`.
- **Win / lose condition**: first player to :data:`WIN_SCORE` points. When
  either side reaches it, a brief result banner ("YOU WIN" / "YOU LOSE") is
  shown and ``run()`` returns to the menu. A scored point pauses briefly and the
  round resets (scores persist), matching demo pacing.

DEMO mode (``controller is None``) is unchanged: both paddles are AI, rounds
auto-restart, and the match resets after someone reaches 5. Existing tests
calling ``run(matrix, duration)`` behave exactly as before.
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import (
    should_stop,
    interruptible_sleep,
    safe_rumble,
    show_banner,
)
from src.display._utils import _draw_digit, _draw_number, _lerp_color, _scale_color

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

    def _predict_ball_y_at_x(self, target_x):
        """Predict the ball's Y position when it reaches target_x.

        Simulates the ball's trajectory accounting for top/bottom wall bounces.
        This gives the AI perfect knowledge of where the ball will arrive,
        enabling it to intercept every shot.
        """
        # Simulate ball trajectory from current position
        sim_x = self.ball_x
        sim_y = self.ball_y
        sim_vx = self.ball_vx
        sim_vy = self.ball_vy

        # If ball is moving away from target, predict where it will return
        # after bouncing off the opposite paddle's side (approximate)
        if sim_vx == 0:
            return sim_y  # Ball not moving horizontally; just return current Y

        # Determine if ball is heading toward or away from target_x
        heading_toward = (sim_vx > 0 and target_x > sim_x) or (sim_vx < 0 and target_x < sim_x)

        if not heading_toward:
            # Ball going away — predict where it'll be after bouncing back.
            # Estimate: it will travel to the opposite wall, bounce, then come back.
            # For simplicity, just move toward center when ball is going away.
            return float(SIZE / 2.0)

        # Simulate step-by-step until ball reaches target_x
        # Use small steps to accurately model wall bounces
        max_iterations = 500  # Safety cap to avoid infinite loops
        step = 0.5  # Simulation step size (pixels)

        while max_iterations > 0:
            max_iterations -= 1
            # How far to target_x?
            if sim_vx > 0:
                dist_to_target = target_x - sim_x
                if dist_to_target <= 0:
                    break
            else:
                dist_to_target = sim_x - target_x
                if dist_to_target <= 0:
                    break

            # Time to reach target at current velocity
            time_to_target = abs(dist_to_target / sim_vx)

            # Take a step (or reach target if close enough)
            dt = min(step / (abs(sim_vx) + abs(sim_vy) + 0.01), time_to_target)
            sim_x += sim_vx * dt
            sim_y += sim_vy * dt

            # Bounce off top/bottom walls (playable area is y=1 to y=SIZE-BALL_SIZE-1)
            if sim_y <= 1:
                sim_y = 1 + (1 - sim_y)
                sim_vy = abs(sim_vy)
            elif sim_y >= SIZE - BALL_SIZE - 1:
                wall = SIZE - BALL_SIZE - 1
                sim_y = wall - (sim_y - wall)
                sim_vy = -abs(sim_vy)

            # Check if we've reached or passed target_x
            if sim_vx > 0 and sim_x >= target_x:
                break
            elif sim_vx < 0 and sim_x <= target_x:
                break

        return sim_y

    def _move_paddle_ai(self, paddle_y, is_left):
        """Perfect AI paddle movement — predicts ball landing position.

        Uses trajectory simulation with wall-bounce prediction to determine
        exactly where the ball will arrive at the paddle's X coordinate.
        Moves at unlimited speed to guarantee interception every time,
        producing indefinite rallies in demo mode.
        """
        # Determine the X coordinate this paddle needs to defend
        if is_left:
            paddle_target_x = float(PADDLE_X_LEFT + PADDLE_WIDTH)
        else:
            paddle_target_x = float(PADDLE_X_RIGHT)

        # Predict where the ball will be when it reaches our paddle's X
        predicted_y = self._predict_ball_y_at_x(paddle_target_x)

        # Target: center the paddle on the predicted Y
        target_y = predicted_y - self.paddle_height / 2.0

        # Move toward target with no speed limit — perfect interception
        # (Use a generous max speed that ensures we always arrive in time)
        max_speed = 4.0  # Fast enough to cover full court between frames
        diff = target_y - paddle_y
        move = max(-max_speed, min(max_speed, diff))

        paddle_y += move
        paddle_y = max(0.0, min(float(SIZE - self.paddle_height), paddle_y))
        return paddle_y

    def _move_paddle_player(self, paddle_y, dy):
        """Move the left (player) paddle by ``dy`` (in {-1,0,1}) at paddle speed.

        Shares the same clamping as the AI mover so physics/rendering are
        identical; only the *decision* differs (input vs. _move_paddle_ai).
        """
        max_speed = 2.0
        paddle_y += dy * max_speed
        paddle_y = max(0.0, min(float(SIZE - self.paddle_height), paddle_y))
        return paddle_y

    def step(self, player_dy=None):
        """Advance one game frame.

        :param player_dy: when ``None`` (DEMO) both paddles use the AI mover.
            When provided (INTERACTIVE) it drives the **left** paddle (a value in
            ``{-1, 0, 1}``: -1 = up, +1 = down) while the right paddle stays AI.
        """
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

        # Move paddles. Left paddle is player-driven in interactive mode.
        if player_dy is None:
            self.p1_y = self._move_paddle_ai(self.p1_y, True)
        else:
            self.p1_y = self._move_paddle_player(self.p1_y, player_dy)
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


# First player to this many points wins (used by both modes for match reset /
# interactive win-lose).
WIN_SCORE = 5
# Generous safety cap (seconds) for INTERACTIVE play; the player normally exits
# when the match is decided or via the quit gesture.
_INTERACTIVE_MAX_SECONDS = 3600


def _carry_round_reset(game):
    """Reset the ball/round but preserve scores + paddle state (shared helper)."""
    old_p1 = game.p1_score
    old_p2 = game.p2_score
    old_ph = game.paddle_height
    old_pc = game.pass_count
    game._reset_round()
    game.p1_score = old_p1
    game.p2_score = old_p2
    game.paddle_height = old_ph
    game.pass_count = old_pc


def _run_demo(matrix, duration, start_time):
    """Autonomous DEMO loop (unchanged behavior)."""
    while time.time() - start_time < duration:
        if should_stop():
            break
        game = PongGame()

        while not game.round_over and time.time() - start_time < duration:
            if should_stop():
                break
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
            if not interruptible_sleep(0.8):
                break

            _carry_round_reset(game)

            # Reset game after someone reaches WIN_SCORE
            if game.p1_score >= WIN_SCORE or game.p2_score >= WIN_SCORE:
                # Show final score for a moment
                game.draw(matrix)
                if not interruptible_sleep(1.5):
                    break
                game.reset()


def _run_interactive(matrix, controller, start_time):
    """INTERACTIVE loop: player (left paddle) vs AI; first to WIN_SCORE."""
    from src.input.controller import wants_quit

    show_banner(matrix, ["PONG", "READY"], hold=0.8)

    game = PongGame()

    while time.time() - start_time < _INTERACTIVE_MAX_SECONDS:
        if should_stop():
            return
        # Play a round until a point is scored.
        while not game.round_over:
            if should_stop():
                return
            controller.poll_events()
            if wants_quit(controller):
                return
            frame_start = time.time()

            # Level-poll the player's vertical direction; UP = -1, DOWN = +1.
            d = controller.get_direction()
            player_dy = 0
            if d is not None:
                player_dy = d[1]  # screen coords: up is -1
            game.step(player_dy=player_dy)
            game.draw(matrix)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_DUR - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # A point was scored: brief pause, then check for match end.
        game.draw(matrix)
        if not interruptible_sleep(0.8):
            return

        if game.p1_score >= WIN_SCORE or game.p2_score >= WIN_SCORE:
            player_won = game.p1_score >= WIN_SCORE
            safe_rumble(controller, 1.0 if player_won else 0.6, 300)
            msg = "YOU WIN" if player_won else "YOU LOSE"
            color = (80, 255, 120) if player_won else (255, 80, 80)
            show_banner(matrix, [msg, f"{game.p1_score}-{game.p2_score}"],
                        color=color, hold=1.8)
            return

        _carry_round_reset(game)


def run(matrix, duration=60, controller=None):
    """Run the Pong feature.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds (DEMO mode only; INTERACTIVE play
            runs until the match is decided or the quit gesture, with a generous
            safety cap of :data:`_INTERACTIVE_MAX_SECONDS`).
        controller: optional :class:`src.input.Controller`. ``None`` -> DEMO
            (AI vs AI, unchanged). Not-None -> INTERACTIVE (player vs AI).
    """
    start_time = time.time()
    try:
        if controller is None:
            _run_demo(matrix, duration, start_time)
        else:
            _run_interactive(matrix, controller, start_time)
    except Exception as e:
        logger.error("Error in pong: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
