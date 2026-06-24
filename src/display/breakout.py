"""
Breakout -- Enhanced brick-breaking game on 64x64 LED matrix.

Features:
- PLAYABLE: Controller support (LEFT/RIGHT move paddle, A launches ball)
- POWER-UPS: Wide paddle, multi-ball, fireball (breaks through), slow ball
- MULTIPLE LEVELS: 5 distinct brick patterns with increasing difficulty
- Multi-hit bricks (silver/gold take 2-3 hits)
- Ball speed increases with level
- Lives system with score tracking
- AI mode for demo carousel (no controller)
- Visual effects: ball trail, brick shatter particles, power-up glow

Control scheme (INTERACTIVE mode)
---------------------------------
- **LEFT / RIGHT** move paddle
- **A** launch ball (when stuck to paddle)
- **Start + Select** quit to menu
"""

import random
import logging
import time
import math
from PIL import Image, ImageDraw
from src.display._shared import should_stop, interruptible_sleep, show_banner, safe_rumble
from src.display._fonts import _draw_text, _text_width
from src.display._utils import _draw_digit, _draw_number, _scale_color

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 30
FRAME_DUR = 1.0 / FPS

# Colors
BG_COLOR = (0, 0, 0)
BORDER_COLOR = (15, 15, 50)
PADDLE_COLOR = (80, 180, 255)
PADDLE_WIDE_COLOR = (80, 255, 180)

# Brick colors by hit points
BRICK_COLORS = {
    1: [
        (255, 50, 50),     # red
        (255, 140, 40),    # orange
        (255, 230, 50),    # yellow
        (50, 220, 50),     # green
        (50, 130, 255),    # blue
        (200, 50, 255),    # purple
    ],
    2: (180, 180, 200),    # silver (2 hits)
    3: (255, 215, 0),      # gold (3 hits)
}

# Ball color cycle
BALL_COLORS = [
    (255, 255, 80),
    (80, 255, 80),
    (255, 80, 255),
    (80, 255, 255),
    (255, 160, 40),
    (255, 80, 80),
    (120, 120, 255),
]

# Power-up types and colors
POWERUP_WIDE = "wide"         # wider paddle
POWERUP_MULTI = "multi"       # spawn extra ball
POWERUP_FIRE = "fire"         # fireball (breaks through bricks)
POWERUP_SLOW = "slow"         # slow ball down
POWERUP_LIFE = "life"         # extra life

POWERUP_COLORS = {
    POWERUP_WIDE: (80, 255, 180),
    POWERUP_MULTI: (255, 80, 255),
    POWERUP_FIRE: (255, 100, 0),
    POWERUP_SLOW: (100, 200, 255),
    POWERUP_LIFE: (255, 80, 80),
}

# Layout
BRICK_COLS = 8
BRICK_W = 7
BRICK_H = 3
BRICK_GAP = 1
BRICK_AREA_TOP = 6
PADDLE_Y = SIZE - 6
PADDLE_WIDTH_NORMAL = 12
PADDLE_WIDTH_WIDE = 18
PADDLE_HEIGHT = 2
BALL_SIZE = 2
TRAIL_LENGTH = 4

# Power-up drop rate (% chance per brick destroyed)
POWERUP_DROP_CHANCE = 0.20


# ---------------------------------------------------------------------------
# Level definitions (brick patterns)
# ---------------------------------------------------------------------------

def _level_standard(rows=5):
    """Standard full-rows layout."""
    bricks = []
    for row in range(rows):
        for col in range(BRICK_COLS):
            bricks.append({"row": row, "col": col, "hp": 1, "color_idx": row})
    return bricks


def _level_checkerboard():
    """Checkerboard pattern with some multi-hit bricks."""
    bricks = []
    for row in range(6):
        for col in range(BRICK_COLS):
            if (row + col) % 2 == 0:
                hp = 2 if row < 2 else 1
                bricks.append({"row": row, "col": col, "hp": hp, "color_idx": row})
    return bricks


def _level_diamond():
    """Diamond/pyramid shape with gold center."""
    bricks = []
    for row in range(6):
        # Diamond pattern: fewer bricks on edges
        start = max(0, 3 - row) if row < 3 else max(0, row - 2)
        end = BRICK_COLS - start
        for col in range(start, end):
            hp = 3 if (row == 2 or row == 3) and (col == 3 or col == 4) else 1
            bricks.append({"row": row, "col": col, "hp": hp, "color_idx": row})
    return bricks


def _level_fortress():
    """Fortress pattern with walls of multi-hit bricks."""
    bricks = []
    for row in range(6):
        for col in range(BRICK_COLS):
            # Walls on sides (silver)
            if col == 0 or col == BRICK_COLS - 1:
                bricks.append({"row": row, "col": col, "hp": 2, "color_idx": row})
            # Top row (gold)
            elif row == 0:
                bricks.append({"row": row, "col": col, "hp": 3, "color_idx": row})
            # Inner bricks
            elif row < 5:
                bricks.append({"row": row, "col": col, "hp": 1, "color_idx": row})
    return bricks


def _level_stripes():
    """Alternating rows with gaps and multi-hit."""
    bricks = []
    for row in range(7):
        if row % 2 == 0:  # Full rows
            for col in range(BRICK_COLS):
                hp = 2 if row == 0 else 1
                bricks.append({"row": row, "col": col, "hp": hp, "color_idx": row})
        else:  # Partial rows (gaps)
            for col in range(1, BRICK_COLS - 1):
                bricks.append({"row": row, "col": col, "hp": 1, "color_idx": row})
    return bricks


LEVELS = [
    _level_standard,
    _level_checkerboard,
    _level_diamond,
    _level_fortress,
    _level_stripes,
]


# ---------------------------------------------------------------------------
# Game entities
# ---------------------------------------------------------------------------

class Ball:
    """A single ball in play."""

    def __init__(self, x, y, vx, vy, speed):
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.speed = speed
        self.trail = []
        self.color_idx = random.randint(0, len(BALL_COLORS) - 1)
        self.fireball = False
        self.stuck = False  # Stuck to paddle until launched

    def bounce_color(self):
        self.color_idx = (self.color_idx + 1) % len(BALL_COLORS)


class PowerUp:
    """A falling power-up capsule."""

    def __init__(self, x, y, kind):
        self.x = float(x)
        self.y = float(y)
        self.kind = kind
        self.vy = 0.8  # Fall speed
        self.tick = 0

    def update(self):
        self.y += self.vy
        self.tick += 1
        return self.y < SIZE  # Still on screen


class Particle:
    """Brief visual particle for brick destruction."""

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
        self.vy += 0.1  # gravity
        self.life -= 1
        return self.life > 0


# ---------------------------------------------------------------------------
# Main game
# ---------------------------------------------------------------------------

class BreakoutGame:
    def __init__(self):
        self.score = 0
        self.lives = 3
        self.level = 0
        self.balls = []
        self.powerups = []
        self.particles = []
        self.paddle_x = float((SIZE - PADDLE_WIDTH_NORMAL) // 2)
        self.paddle_width = PADDLE_WIDTH_NORMAL
        self.wide_timer = 0  # Frames remaining for wide paddle
        self.fire_timer = 0  # Frames remaining for fireball
        self.slow_timer = 0  # Frames remaining for slow
        self._frame_count = 0
        self._load_level()
        self._reset_ball(stuck=True)

    def _load_level(self):
        """Load bricks for current level."""
        level_fn = LEVELS[self.level % len(LEVELS)]
        self.bricks = level_fn()

    def _reset_ball(self, stuck=False):
        """Reset to a single ball above paddle."""
        self.balls.clear()
        speed = 1.2 + self.level * 0.15  # Faster each level
        ball = Ball(
            self.paddle_x + self.paddle_width / 2,
            PADDLE_Y - BALL_SIZE - 1,
            0, 0, speed
        )
        if stuck:
            ball.stuck = True
        else:
            angle = random.uniform(-0.6, 0.6)
            ball.vx = speed * math.sin(angle)
            ball.vy = -speed * math.cos(angle)
        self.balls.append(ball)

    def launch_ball(self):
        """Launch ball from paddle (player pressed A)."""
        for ball in self.balls:
            if ball.stuck:
                angle = random.uniform(-0.5, 0.5)
                ball.vx = ball.speed * math.sin(angle)
                ball.vy = -ball.speed * math.cos(angle)
                ball.stuck = False

    def _brick_rect(self, brick):
        """Get pixel rectangle for a brick."""
        col = brick["col"]
        row = brick["row"]
        x1 = 1 + col * (BRICK_W + BRICK_GAP)
        y1 = BRICK_AREA_TOP + row * (BRICK_H + BRICK_GAP)
        x2 = x1 + BRICK_W - 1
        y2 = y1 + BRICK_H - 1
        return x1, y1, x2, y2

    def _get_brick_color(self, brick):
        """Get display color for a brick based on HP."""
        hp = brick["hp"]
        if hp >= 3:
            return BRICK_COLORS[3]
        elif hp == 2:
            return BRICK_COLORS[2]
        else:
            colors = BRICK_COLORS[1]
            return colors[brick["color_idx"] % len(colors)]

    def _spawn_powerup(self, x, y):
        """Maybe spawn a power-up at brick position."""
        if random.random() < POWERUP_DROP_CHANCE:
            kind = random.choice([POWERUP_WIDE, POWERUP_MULTI, POWERUP_FIRE,
                                  POWERUP_SLOW, POWERUP_LIFE])
            self.powerups.append(PowerUp(x, y, kind))

    def _apply_powerup(self, kind):
        """Apply a collected power-up."""
        if kind == POWERUP_WIDE:
            self.paddle_width = PADDLE_WIDTH_WIDE
            self.wide_timer = FPS * 10  # 10 seconds
        elif kind == POWERUP_MULTI:
            # Spawn 2 extra balls from current ball positions
            if self.balls:
                src = self.balls[0]
                for _ in range(2):
                    angle = random.uniform(-1.0, 1.0)
                    nb = Ball(src.x, src.y,
                              src.speed * math.sin(angle),
                              -src.speed * math.cos(angle),
                              src.speed)
                    nb.fireball = src.fireball
                    self.balls.append(nb)
        elif kind == POWERUP_FIRE:
            self.fire_timer = FPS * 8  # 8 seconds
            for ball in self.balls:
                ball.fireball = True
        elif kind == POWERUP_SLOW:
            self.slow_timer = FPS * 6  # 6 seconds
            for ball in self.balls:
                ball.speed = max(0.8, ball.speed * 0.6)
                # Rescale velocity
                spd = math.sqrt(ball.vx ** 2 + ball.vy ** 2)
                if spd > 0:
                    ratio = ball.speed / spd
                    ball.vx *= ratio
                    ball.vy *= ratio
        elif kind == POWERUP_LIFE:
            self.lives = min(5, self.lives + 1)

    def _check_brick_collision(self, ball):
        """Check ball vs bricks. Returns True if hit."""
        bx = int(ball.x)
        by = int(ball.y)
        hit = False

        for brick in self.bricks:
            if brick["hp"] <= 0:
                continue
            x1, y1, x2, y2 = self._brick_rect(brick)

            if (bx + BALL_SIZE > x1 and bx < x2 + 1 and
                    by + BALL_SIZE > y1 and by < y2 + 1):
                brick["hp"] -= 1

                if brick["hp"] <= 0:
                    self.score += (6 - brick["row"]) * 10
                    # Spawn particles
                    color = self._get_brick_color(brick)
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    for _ in range(4):
                        self.particles.append(Particle(
                            cx, cy,
                            random.uniform(-1.5, 1.5),
                            random.uniform(-2, 0.5),
                            color, life=10
                        ))
                    # Maybe drop power-up
                    self._spawn_powerup(cx, cy)

                # Fireball breaks through without bouncing
                if not ball.fireball:
                    overlap_left = (bx + BALL_SIZE) - x1
                    overlap_right = (x2 + 1) - bx
                    overlap_top = (by + BALL_SIZE) - y1
                    overlap_bottom = (y2 + 1) - by
                    min_overlap = min(overlap_left, overlap_right,
                                      overlap_top, overlap_bottom)
                    if min_overlap == overlap_top or min_overlap == overlap_bottom:
                        ball.vy = -ball.vy
                    else:
                        ball.vx = -ball.vx

                ball.bounce_color()
                hit = True

                if not ball.fireball:
                    break  # Only hit one brick per frame (unless fireball)

        return hit

    def all_bricks_cleared(self):
        return not any(b["hp"] > 0 for b in self.bricks)

    def move_paddle(self, dx):
        """Move paddle by dx pixels."""
        self.paddle_x += dx
        self.paddle_x = max(1.0, min(float(SIZE - self.paddle_width - 1), self.paddle_x))
        # Move stuck ball with paddle
        for ball in self.balls:
            if ball.stuck:
                ball.x = self.paddle_x + self.paddle_width / 2

    def _move_paddle_ai(self):
        """AI paddle for demo mode."""
        if not self.balls:
            return

        # Find the lowest ball heading down
        target_ball = None
        for ball in self.balls:
            if ball.stuck:
                self.launch_ball()
                return
            if ball.vy > 0:
                if target_ball is None or ball.y > target_ball.y:
                    target_ball = ball
        if target_ball is None:
            target_ball = self.balls[0]

        # Predict landing
        predicted_x = self._predict_ball_x(target_ball)
        offset = math.sin(self._frame_count * 0.05) * 3
        target_x = predicted_x - self.paddle_width / 2.0 + offset

        diff = target_x - self.paddle_x
        max_speed = 3.5
        move = max(-max_speed, min(max_speed, diff))
        self.paddle_x += move
        self.paddle_x = max(1.0, min(float(SIZE - self.paddle_width - 1), self.paddle_x))

    def _predict_ball_x(self, ball):
        """Predict where ball lands at paddle Y."""
        sim_x, sim_y = ball.x, ball.y
        sim_vx, sim_vy = ball.vx, ball.vy
        if sim_vy <= 0:
            return sim_x

        target_y = float(PADDLE_Y - BALL_SIZE)
        for _ in range(500):
            speed = math.sqrt(sim_vx ** 2 + sim_vy ** 2)
            if speed < 0.01:
                break
            dt = 0.5 / speed
            sim_x += sim_vx * dt
            sim_y += sim_vy * dt
            if sim_x <= 1:
                sim_vx = abs(sim_vx)
            elif sim_x >= SIZE - BALL_SIZE - 1:
                sim_vx = -abs(sim_vx)
            if sim_y <= 1:
                sim_vy = abs(sim_vy)
            if sim_vy > 0 and sim_y >= target_y:
                break
        return sim_x

    def step(self, ai_mode=False):
        """Advance one frame. Returns 'playing', 'lost_life', 'cleared', 'game_over'."""
        self._frame_count += 1

        # Update power-up timers
        if self.wide_timer > 0:
            self.wide_timer -= 1
            if self.wide_timer <= 0:
                self.paddle_width = PADDLE_WIDTH_NORMAL
        if self.fire_timer > 0:
            self.fire_timer -= 1
            if self.fire_timer <= 0:
                for ball in self.balls:
                    ball.fireball = False
        if self.slow_timer > 0:
            self.slow_timer -= 1
            if self.slow_timer <= 0:
                # Restore speed
                base_speed = 1.2 + self.level * 0.15
                for ball in self.balls:
                    ball.speed = base_speed
                    spd = math.sqrt(ball.vx ** 2 + ball.vy ** 2)
                    if spd > 0:
                        ratio = ball.speed / spd
                        ball.vx *= ratio
                        ball.vy *= ratio

        # AI paddle
        if ai_mode:
            self._move_paddle_ai()

        # Update balls
        balls_to_remove = []
        for ball in self.balls:
            if ball.stuck:
                continue

            # Trail
            ball.trail.append((ball.x, ball.y))
            if len(ball.trail) > TRAIL_LENGTH:
                ball.trail.pop(0)

            # Move
            ball.x += ball.vx
            ball.y += ball.vy

            # Wall bounces
            if ball.x <= 1:
                ball.x = 1.0
                ball.vx = abs(ball.vx)
                ball.bounce_color()
            elif ball.x >= SIZE - BALL_SIZE - 1:
                ball.x = float(SIZE - BALL_SIZE - 1)
                ball.vx = -abs(ball.vx)
                ball.bounce_color()
            if ball.y <= 1:
                ball.y = 1.0
                ball.vy = abs(ball.vy)
                ball.bounce_color()

            # Paddle collision
            pw = self.paddle_width
            px = int(self.paddle_x)
            if (ball.vy > 0 and
                    ball.y + BALL_SIZE >= PADDLE_Y and
                    ball.y + BALL_SIZE <= PADDLE_Y + PADDLE_HEIGHT + 2 and
                    ball.x + BALL_SIZE > px and
                    ball.x < px + pw):
                ball.y = float(PADDLE_Y - BALL_SIZE)
                hit_pos = (ball.x - self.paddle_x) / pw
                angle = (hit_pos - 0.5) * 1.4
                ball.vx = ball.speed * math.sin(angle)
                ball.vy = -ball.speed * math.cos(angle)
                ball.bounce_color()

            # Brick collision
            self._check_brick_collision(ball)

            # Ball falls below
            if ball.y > SIZE:
                balls_to_remove.append(ball)

        # Remove lost balls
        for ball in balls_to_remove:
            self.balls.remove(ball)

        # If all balls lost
        if not self.balls:
            self.lives -= 1
            if self.lives > 0:
                self._reset_ball(stuck=True)
                self.paddle_width = PADDLE_WIDTH_NORMAL
                self.fire_timer = 0
                self.slow_timer = 0
                self.wide_timer = 0
                return "lost_life"
            else:
                return "game_over"

        # Update power-ups
        active_powerups = []
        for pu in self.powerups:
            if pu.update():
                # Check paddle catch
                px = int(self.paddle_x)
                pw = self.paddle_width
                if (pu.y >= PADDLE_Y - 2 and pu.y <= PADDLE_Y + PADDLE_HEIGHT and
                        pu.x >= px and pu.x <= px + pw):
                    self._apply_powerup(pu.kind)
                else:
                    active_powerups.append(pu)
        self.powerups = active_powerups

        # Update particles
        self.particles = [p for p in self.particles if p.update()]

        # Level cleared
        if self.all_bricks_cleared():
            return "cleared"

        return "playing"

    def draw(self, matrix):
        """Render game state."""
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Border
        draw.rectangle([(0, 0), (SIZE - 1, SIZE - 1)], outline=BORDER_COLOR)

        # Level indicator (top center)
        lvl_str = f"L{self.level + 1}"
        lw = _text_width(lvl_str, scale=1, spacing=0)
        _draw_text(draw, lvl_str, (SIZE - lw) // 2, 1, (80, 80, 120), scale=1, spacing=0)

        # Score (top-left)
        _draw_number(image, self.score, 2, 1, (200, 200, 200))

        # Lives as dots (top-right)
        for i in range(self.lives):
            lx = SIZE - 4 - i * 4
            if 0 <= lx < SIZE:
                draw.rectangle([(lx, 2), (lx + 1, 3)], fill=(255, 80, 80))

        # Bricks
        for brick in self.bricks:
            if brick["hp"] <= 0:
                continue
            x1, y1, x2, y2 = self._brick_rect(brick)
            color = self._get_brick_color(brick)
            draw.rectangle([(x1, y1), (x2, y2)], fill=color)
            # Highlight for multi-hit bricks
            if brick["hp"] >= 2:
                draw.point((x1 + 1, y1), fill=(255, 255, 255))

        # Power-ups (falling capsules)
        for pu in self.powerups:
            px, py = int(pu.x), int(pu.y)
            color = POWERUP_COLORS.get(pu.kind, (255, 255, 255))
            # Pulsing capsule
            pulse = 0.7 + 0.3 * math.sin(pu.tick * 0.3)
            c = tuple(int(v * pulse) for v in color)
            if 0 <= px < SIZE - 2 and 0 <= py < SIZE - 2:
                draw.rectangle([(px, py), (px + 2, py + 2)], fill=c)

        # Paddle
        px = int(self.paddle_x)
        pw = self.paddle_width
        p_color = PADDLE_WIDE_COLOR if self.wide_timer > 0 else PADDLE_COLOR
        # Flash when wide timer almost done
        if self.wide_timer > 0 and self.wide_timer < FPS * 2 and self._frame_count % 6 < 3:
            p_color = PADDLE_COLOR
        for i in range(pw):
            dist = abs(i - pw / 2.0) / (pw / 2.0)
            brightness = 1.0 - 0.3 * dist
            c = _scale_color(p_color, brightness)
            for h in range(PADDLE_HEIGHT):
                cx = px + i
                cy = PADDLE_Y + h
                if 0 <= cx < SIZE and 0 <= cy < SIZE:
                    image.putpixel((cx, cy), c)

        # Balls
        for ball in self.balls:
            ball_color = BALL_COLORS[ball.color_idx]
            if ball.fireball:
                ball_color = (255, 100, 0)

            # Trail
            for i, (tx, ty) in enumerate(ball.trail):
                fade = (i + 1) / (TRAIL_LENGTH + 1)
                trail_color = _scale_color(ball_color, fade * 0.4)
                bx, by = int(tx), int(ty)
                for ox in range(BALL_SIZE):
                    for oy in range(BALL_SIZE):
                        ppx, ppy = bx + ox, by + oy
                        if 0 <= ppx < SIZE and 0 <= ppy < SIZE:
                            image.putpixel((ppx, ppy), trail_color)

            # Ball core
            bx, by = int(ball.x), int(ball.y)
            for ox in range(BALL_SIZE):
                for oy in range(BALL_SIZE):
                    ppx, ppy = bx + ox, by + oy
                    if 0 <= ppx < SIZE and 0 <= ppy < SIZE:
                        image.putpixel((ppx, ppy), ball_color)

        # Particles
        for p in self.particles:
            px, py = int(p.x), int(p.y)
            if 0 <= px < SIZE and 0 <= py < SIZE:
                alpha = p.life / 10.0
                c = tuple(int(v * alpha) for v in p.color)
                draw.point((px, py), fill=c)

        # Fireball indicator
        if self.fire_timer > 0:
            draw.point((1, SIZE - 2), fill=(255, 100, 0))
            draw.point((2, SIZE - 2), fill=(255, 100, 0))

        matrix.SetImage(image)


# ---------------------------------------------------------------------------
# Demo mode (AI plays)
# ---------------------------------------------------------------------------

def _run_demo(matrix, duration, start_time):
    """AI-controlled breakout demo."""
    game = BreakoutGame()

    while time.time() - start_time < duration:
        if should_stop():
            return
        frame_start = time.time()

        result = game.step(ai_mode=True)
        game.draw(matrix)

        if result == "cleared":
            if not interruptible_sleep(0.8):
                return
            game.level += 1
            game._load_level()
            game._reset_ball(stuck=False)

        elif result == "lost_life":
            if not interruptible_sleep(0.4):
                return
            # AI auto-launches
            game.launch_ball()

        elif result == "game_over":
            if not interruptible_sleep(1.5):
                return
            game = BreakoutGame()

        elapsed = time.time() - frame_start
        sleep_time = FRAME_DUR - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Interactive mode (player controls paddle)
# ---------------------------------------------------------------------------

def _run_interactive(matrix, controller, start_time):
    """Player-controlled breakout."""
    from src.input.controller import wants_quit, Button, EventType

    game = BreakoutGame()
    show_banner(matrix, ["BREAKOUT", "L/R:MOVE A:LAUNCH"],
                color=PADDLE_COLOR, hold=1.2)

    _MAX_SECONDS = 86400  # No timeout for interactive

    while time.time() - start_time < _MAX_SECONDS:
        if should_stop():
            return
        frame_start = time.time()

        events = controller.poll_events()
        if wants_quit(controller):
            return

        # Player input
        d = controller.get_direction()
        if d:
            move_speed = 3.0
            game.move_paddle(d[0] * move_speed)

        for ev in events:
            if ev.event_type == EventType.PRESSED:
                if ev.button in (Button.A, Button.UP):
                    game.launch_ball()

        result = game.step(ai_mode=False)
        game.draw(matrix)

        if result == "cleared":
            safe_rumble(controller, 0.5, 200)
            game.level += 1
            lvl_msg = f"LEVEL {game.level + 1}"
            show_banner(matrix, [lvl_msg, f"SCORE:{game.score}"],
                        color=(80, 255, 180), hold=1.5)
            game._load_level()
            game._reset_ball(stuck=True)

        elif result == "lost_life":
            safe_rumble(controller, 0.3, 150)
            if not interruptible_sleep(0.5):
                return

        elif result == "game_over":
            safe_rumble(controller, 1.0, 500)
            show_banner(matrix, ["GAME OVER", f"SCORE:{game.score}"],
                        color=(255, 80, 80), hold=2.5)
            return

        elapsed = time.time() - frame_start
        sleep_time = FRAME_DUR - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60, controller=None):
    """Run Breakout.

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
        logger.error("Error in breakout: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
