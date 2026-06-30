"""
Super Breakout -- Fez-style cube-rotating breakout on 64x64 LED matrix.

Features:
- 4 cube faces in a horizontal ring (front → right → back → left)
- Standard breakout on the visible face: paddle at bottom, ball bounces, bricks break
- Fez-style rotation: column-based horizontal compression/expansion over ~12 frames
- Ball wraps to adjacent face when exiting left/right edge
- Edge glow indicators showing which direction the ball went
- Ball can break bricks on hidden faces; loses life if it falls below paddle-Y while hidden
- Ball trail effect with color changes on bounce
- Screen shake, particles, flash effects for game juice
- Smooth sub-pixel rendering

Control scheme (INTERACTIVE mode)
---------------------------------
- **LEFT / RIGHT** move paddle
- **A** launch ball (when stuck to paddle)
- **B** rotate cube right (clockwise around Y)
- **SELECT** rotate cube left
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
BG_COLOR = (2, 2, 8)
PADDLE_COLOR = (100, 220, 255)
PADDLE_HIGHLIGHT = (180, 240, 255)
HUD_COLOR = (140, 150, 200)
BORDER_COLOR = (20, 20, 50)

# Ball color cycle (bright, vivid)
BALL_COLORS = [
    (255, 255, 100),
    (100, 255, 100),
    (255, 100, 255),
    (100, 255, 255),
    (255, 180, 60),
    (255, 100, 100),
    (150, 150, 255),
]

# Face accent colors
FACE_COLORS = [
    (80, 180, 255),   # front - cyan/blue
    (255, 160, 50),   # right - orange
    (80, 255, 120),   # back - green
    (220, 100, 255),  # left - purple
]

FACE_NAMES = ["F", "R", "B", "L"]

# Brick row colors (vivid gradient)
BRICK_ROW_COLORS = [
    (255, 60, 60),     # red
    (255, 130, 30),    # orange
    (255, 220, 40),    # yellow
    (60, 230, 60),     # green
    (40, 160, 255),    # blue
    (160, 60, 255),    # purple
    (255, 80, 160),    # pink
]

# Layout constants
HUD_HEIGHT = 6
BRICK_AREA_TOP = HUD_HEIGHT
BRICK_COLS = 8
BRICK_ROWS = 7
BRICK_W = 6       # 6px wide
BRICK_H = 3       # 3px tall
BRICK_GAP = 1     # 1px gap
BRICK_AREA_HEIGHT = BRICK_ROWS * (BRICK_H + BRICK_GAP)  # 28px

PLAY_AREA_TOP = BRICK_AREA_TOP + BRICK_AREA_HEIGHT  # 34
PLAY_AREA_HEIGHT = 23
PADDLE_ZONE_TOP = PLAY_AREA_TOP + PLAY_AREA_HEIGHT  # 57
PADDLE_ZONE_HEIGHT = 3
GLOW_ZONE_TOP = PADDLE_ZONE_TOP + PADDLE_ZONE_HEIGHT  # 60
GLOW_ZONE_HEIGHT = 4  # bottom 4px

PADDLE_WIDTH = 10
PADDLE_HEIGHT = 2
PADDLE_Y = PADDLE_ZONE_TOP

BALL_SIZE = 2
TRAIL_LENGTH = 4

# Rotation animation
ROTATION_FRAMES = 12

# Edge glow timing
GLOW_DURATION = 45  # frames (1.5s)

# Shake
SHAKE_DURATION = 6
SHAKE_INTENSITY = 2

# Flash
FLASH_DURATION = 4


# ---------------------------------------------------------------------------
# Brick layout generators for each face
# ---------------------------------------------------------------------------

def _bricks_front():
    """Full grid (all 56 bricks)."""
    bricks = []
    for row in range(BRICK_ROWS):
        for col in range(BRICK_COLS):
            bricks.append({"row": row, "col": col, "alive": True})
    return bricks


def _bricks_right():
    """Checkerboard pattern."""
    bricks = []
    for row in range(BRICK_ROWS):
        for col in range(BRICK_COLS):
            if (row + col) % 2 == 0:
                bricks.append({"row": row, "col": col, "alive": True})
    return bricks


def _bricks_back():
    """Diamond/X shape."""
    bricks = []
    cx, cy = 3.5, 3.0
    for row in range(BRICK_ROWS):
        for col in range(BRICK_COLS):
            dx = abs(col - cx)
            dy = abs(row - cy)
            if dx + dy <= 3.5 or abs(dx - dy) <= 0.8:
                bricks.append({"row": row, "col": col, "alive": True})
    return bricks


def _bricks_left():
    """Horizontal stripes (alternating rows filled)."""
    bricks = []
    for row in range(BRICK_ROWS):
        if row % 2 == 0:
            for col in range(BRICK_COLS):
                bricks.append({"row": row, "col": col, "alive": True})
    return bricks


FACE_BRICK_GENERATORS = [_bricks_front, _bricks_right, _bricks_back, _bricks_left]


# ---------------------------------------------------------------------------
# Helper: smooth easing functions
# ---------------------------------------------------------------------------

def _ease_in_out_cubic(t):
    """Smooth cubic ease-in-out (0-1 -> 0-1)."""
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0


def _ease_out_quad(t):
    """Quadratic ease out."""
    return 1.0 - (1.0 - t) * (1.0 - t)


def _lerp(a, b, t):
    """Linear interpolation."""
    return a + (b - a) * t


def _blend_color(c1, c2, t):
    """Blend two colors."""
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


# ---------------------------------------------------------------------------
# Game classes
# ---------------------------------------------------------------------------

class Ball:
    """Ball with position, velocity, trail, and face tracking."""

    def __init__(self, x, y, vx, vy):
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.trail = []
        self.color_idx = random.randint(0, len(BALL_COLORS) - 1)
        self.stuck = False
        self.face = 0  # which face the ball is on
        self.speed = 1.5
        self.hit_flash = 0  # frames of hit flash remaining

    def bounce_color(self):
        self.color_idx = (self.color_idx + 1) % len(BALL_COLORS)
        self.hit_flash = 3


class Particle:
    """Visual particle for effects."""

    def __init__(self, x, y, vx, vy, color, life=10, size=1):
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = life
        self.max_life = life
        self.size = size

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.08  # subtle gravity
        self.vx *= 0.97  # air resistance
        self.life -= 1
        return self.life > 0

    @property
    def alpha(self):
        return max(0.0, self.life / self.max_life)


# ---------------------------------------------------------------------------
# Main game
# ---------------------------------------------------------------------------

class SuperBreakoutGame:
    """4-face cube breakout with Fez-style rotation and heavy game juice."""

    def __init__(self):
        self.score = 0
        self.lives = 3
        self.current_face = 0
        self._frame_count = 0

        # Paddle
        self.paddle_x = float((SIZE - PADDLE_WIDTH) // 2)
        self.paddle_target_x = self.paddle_x  # for smooth movement
        self.paddle_glow = 0.0  # paddle glow intensity for catches

        # Bricks for each face
        self.face_bricks = [gen() for gen in FACE_BRICK_GENERATORS]

        # Ball
        self.ball = None
        self._reset_ball(stuck=True)

        # Rotation animation state
        self.rotating = False
        self.rotation_frame = 0
        self.rotation_dir = 0
        self.old_face = 0
        self.new_face = 0

        # Edge glow
        self.glow_left = 0
        self.glow_right = 0
        self.glow_left_color = (255, 100, 50)
        self.glow_right_color = (50, 100, 255)

        # Particles
        self.particles = []

        # Screen effects
        self.shake_timer = 0
        self.shake_x = 0
        self.shake_y = 0
        self.flash_timer = 0
        self.flash_color = (255, 255, 255)

        # Background pulse
        self.bg_pulse = 0.0

        # Game state
        self.game_over = False

        # Combo system
        self.combo = 0
        self.combo_timer = 0

        # Ball on other face indicator animation
        self.offscreen_indicator_phase = 0.0

    def _reset_ball(self, stuck=False):
        """Create/reset the ball above the paddle."""
        x = self.paddle_x + PADDLE_WIDTH / 2.0
        y = float(PADDLE_Y - BALL_SIZE - 1)
        self.ball = Ball(x, y, 0, 0)
        self.ball.face = self.current_face
        if stuck:
            self.ball.stuck = True
        else:
            angle = random.uniform(-0.6, 0.6)
            self.ball.vx = self.ball.speed * math.sin(angle)
            self.ball.vy = -self.ball.speed * math.cos(angle)

    def launch_ball(self):
        """Launch ball from paddle with a satisfying angle."""
        if self.ball and self.ball.stuck:
            # Launch angle biased by paddle movement direction
            angle = random.uniform(-0.5, 0.5)
            self.ball.vx = self.ball.speed * math.sin(angle)
            self.ball.vy = -self.ball.speed * math.cos(angle)
            self.ball.stuck = False
            # Visual feedback
            self._spawn_launch_particles()

    def _spawn_launch_particles(self):
        """Spawn particles when ball launches."""
        if self.ball:
            for _ in range(6):
                self.particles.append(Particle(
                    self.ball.x, self.ball.y,
                    random.uniform(-1.0, 1.0),
                    random.uniform(-0.5, 0.5),
                    PADDLE_COLOR, life=8, size=1
                ))

    def move_paddle(self, dx):
        """Move paddle by dx pixels with smooth interpolation."""
        self.paddle_x += dx
        self.paddle_x = max(0.0, min(float(SIZE - PADDLE_WIDTH), self.paddle_x))
        # Move stuck ball with paddle
        if self.ball and self.ball.stuck:
            self.ball.x = self.paddle_x + PADDLE_WIDTH / 2.0

    def start_rotation(self, direction):
        """Begin a Fez-style rotation animation."""
        if self.rotating:
            return
        self.rotating = True
        self.rotation_frame = 0
        self.rotation_dir = direction
        self.old_face = self.current_face
        self.new_face = (self.current_face + direction) % 4
        # Spawn edge particles for the rotation
        self._spawn_rotation_particles(direction)

    def _spawn_rotation_particles(self, direction):
        """Spawn particles along the rotation edge."""
        edge_x = SIZE - 1 if direction > 0 else 0
        color = FACE_COLORS[self.new_face]
        for y in range(BRICK_AREA_TOP, PADDLE_Y, 4):
            self.particles.append(Particle(
                edge_x, y,
                random.uniform(-0.5, 0.5) * direction,
                random.uniform(-0.5, 0.5),
                color, life=ROTATION_FRAMES + 4, size=1
            ))

    def _brick_rect(self, brick):
        """Get pixel rectangle for a brick."""
        col = brick["col"]
        row = brick["row"]
        total_w = BRICK_COLS * (BRICK_W + BRICK_GAP) - BRICK_GAP  # 55
        offset_x = (SIZE - total_w) // 2
        x1 = offset_x + col * (BRICK_W + BRICK_GAP)
        y1 = BRICK_AREA_TOP + row * (BRICK_H + BRICK_GAP)
        x2 = x1 + BRICK_W - 1
        y2 = y1 + BRICK_H - 1
        return x1, y1, x2, y2

    def _check_brick_collision(self, ball):
        """Check ball vs bricks on the ball's current face."""
        if ball.face < 0 or ball.face >= 4:
            return False

        bricks = self.face_bricks[ball.face]
        bx = int(ball.x)
        by = int(ball.y)
        hit = False

        for brick in bricks:
            if not brick["alive"]:
                continue
            x1, y1, x2, y2 = self._brick_rect(brick)

            if (bx + BALL_SIZE > x1 and bx < x2 + 1 and
                    by + BALL_SIZE > y1 and by < y2 + 1):
                brick["alive"] = False

                # Score with combo multiplier
                self.combo += 1
                self.combo_timer = 60  # 2 seconds to maintain combo
                base_score = (BRICK_ROWS - brick["row"]) * 10
                self.score += base_score * min(self.combo, 5)

                # Bounce direction
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

                # Juicy particles (more for higher combos)
                if ball.face == self.current_face:
                    color = BRICK_ROW_COLORS[brick["row"] % len(BRICK_ROW_COLORS)]
                    cx = (x1 + x2) / 2.0
                    cy = (y1 + y2) / 2.0
                    num_particles = 4 + min(self.combo, 4)
                    for _ in range(num_particles):
                        speed_mult = 1.0 + self.combo * 0.2
                        self.particles.append(Particle(
                            cx + random.uniform(-2, 2),
                            cy + random.uniform(-1, 1),
                            random.uniform(-2.0, 2.0) * speed_mult,
                            random.uniform(-2.5, 0.5) * speed_mult,
                            color, life=random.randint(8, 14), size=1
                        ))

                    # Screen shake on combo
                    if self.combo >= 3:
                        self.shake_timer = 3
                    # Flash on big combo
                    if self.combo >= 5:
                        self.flash_timer = 2
                        self.flash_color = color

                # Background pulse on hit
                self.bg_pulse = 0.3

                hit = True
                break

        return hit

    def _face_cleared(self, face_idx):
        """Check if all bricks on a face are destroyed."""
        return not any(b["alive"] for b in self.face_bricks[face_idx])

    def all_faces_cleared(self):
        """Check if all faces are cleared."""
        return all(self._face_cleared(i) for i in range(4))

    def _remaining_bricks(self, face_idx):
        """Count remaining bricks on a face."""
        return sum(1 for b in self.face_bricks[face_idx] if b["alive"])

    def step(self, ai_mode=False):
        """Advance one frame. Returns game state string."""
        self._frame_count += 1

        # Update timers
        if self.glow_left > 0:
            self.glow_left -= 1
        if self.glow_right > 0:
            self.glow_right -= 1
        if self.shake_timer > 0:
            self.shake_timer -= 1
            self.shake_x = random.randint(-SHAKE_INTENSITY, SHAKE_INTENSITY)
            self.shake_y = random.randint(-SHAKE_INTENSITY, SHAKE_INTENSITY)
        else:
            self.shake_x = 0
            self.shake_y = 0
        if self.flash_timer > 0:
            self.flash_timer -= 1
        if self.combo_timer > 0:
            self.combo_timer -= 1
            if self.combo_timer <= 0:
                self.combo = 0

        # Background pulse decay
        self.bg_pulse *= 0.85

        # Paddle glow decay
        self.paddle_glow *= 0.9

        # Offscreen indicator animation
        self.offscreen_indicator_phase += 0.15

        # Handle rotation animation
        if self.rotating:
            self.rotation_frame += 1
            if self.rotation_frame >= ROTATION_FRAMES:
                self.rotating = False
                self.current_face = self.new_face
                self.rotation_frame = 0
            # Update particles during rotation
            self.particles = [p for p in self.particles if p.update()]
            return "playing"

        # AI paddle
        if ai_mode:
            self._move_paddle_ai()

        # Update ball
        ball = self.ball
        if ball is None:
            return "playing"

        if ball.stuck:
            # Update particles even while stuck
            self.particles = [p for p in self.particles if p.update()]
            return "playing"

        # Hit flash decay
        if ball.hit_flash > 0:
            ball.hit_flash -= 1

        # Trail (with position history)
        ball.trail.append((ball.x, ball.y))
        if len(ball.trail) > TRAIL_LENGTH:
            ball.trail.pop(0)

        # Move ball
        ball.x += ball.vx
        ball.y += ball.vy

        # Top wall bounce
        if ball.y < BRICK_AREA_TOP:
            ball.y = float(BRICK_AREA_TOP)
            ball.vy = abs(ball.vy)
            ball.bounce_color()
            # Subtle particles on wall hit
            if ball.face == self.current_face:
                for _ in range(2):
                    self.particles.append(Particle(
                        ball.x, ball.y,
                        random.uniform(-1, 1), random.uniform(0.5, 1.5),
                        BALL_COLORS[ball.color_idx], life=6
                    ))

        # Left/right edge: wrap to adjacent face
        if ball.x < 0:
            new_face = (ball.face - 1) % 4
            old_face = ball.face
            ball.face = new_face
            ball.x = float(SIZE - BALL_SIZE - 1)
            ball.bounce_color()
            # Edge glow with face color
            if old_face == self.current_face:
                self.glow_left = GLOW_DURATION
                self.glow_left_color = FACE_COLORS[(self.current_face - 1) % 4]
            elif new_face == self.current_face:
                self.glow_right = GLOW_DURATION
                self.glow_right_color = FACE_COLORS[(self.current_face + 1) % 4]
            return self._post_ball_update()

        elif ball.x > SIZE - BALL_SIZE:
            new_face = (ball.face + 1) % 4
            old_face = ball.face
            ball.face = new_face
            ball.x = 0.0
            ball.bounce_color()
            # Edge glow with face color
            if old_face == self.current_face:
                self.glow_right = GLOW_DURATION
                self.glow_right_color = FACE_COLORS[(self.current_face + 1) % 4]
            elif new_face == self.current_face:
                self.glow_left = GLOW_DURATION
                self.glow_left_color = FACE_COLORS[(self.current_face - 1) % 4]
            return self._post_ball_update()

        # Paddle collision (only if ball is on visible face)
        if ball.face == self.current_face:
            if (ball.vy > 0 and
                    ball.y + BALL_SIZE >= PADDLE_Y and
                    ball.y + BALL_SIZE <= PADDLE_Y + PADDLE_HEIGHT + 2 and
                    ball.x + BALL_SIZE > self.paddle_x and
                    ball.x < self.paddle_x + PADDLE_WIDTH):
                ball.y = float(PADDLE_Y - BALL_SIZE)
                # Angle based on hit position
                hit_pos = (ball.x + BALL_SIZE / 2.0 - self.paddle_x) / PADDLE_WIDTH
                angle = (hit_pos - 0.5) * 1.3
                ball.vx = ball.speed * math.sin(angle)
                ball.vy = -ball.speed * math.cos(angle)
                ball.bounce_color()
                # Paddle glow on catch
                self.paddle_glow = 1.0
                # Paddle hit particles
                for _ in range(3):
                    self.particles.append(Particle(
                        ball.x, PADDLE_Y,
                        random.uniform(-1.5, 1.5), random.uniform(-1.5, -0.3),
                        PADDLE_COLOR, life=6
                    ))

        # Ball falls below paddle zone
        if ball.y > PADDLE_ZONE_TOP + PADDLE_ZONE_HEIGHT + 2:
            self.lives -= 1
            self.combo = 0
            self.combo_timer = 0
            # Screen shake on life loss
            self.shake_timer = SHAKE_DURATION
            self.flash_timer = FLASH_DURATION
            self.flash_color = (255, 40, 40)
            if self.lives <= 0:
                self.game_over = True
                return "game_over"
            self._reset_ball(stuck=True)
            return "lost_life"

        return self._post_ball_update()

    def _post_ball_update(self):
        """Check brick collisions and update particles."""
        ball = self.ball
        if ball and not ball.stuck:
            self._check_brick_collision(ball)

        # Update particles
        self.particles = [p for p in self.particles if p.update()]

        # Check win
        if self.all_faces_cleared():
            return "cleared"

        return "playing"

    def _move_paddle_ai(self):
        """AI paddle movement for demo mode - smarter and more entertaining."""
        ball = self.ball
        if ball is None:
            return

        if ball.stuck:
            if self._frame_count % 45 == 0:
                self.launch_ball()
            return

        # Ball on our face: track it
        if ball.face == self.current_face:
            predicted_x = self._predict_ball_x(ball)
            # Imperfection: slight oscillation and reaction delay
            noise = math.sin(self._frame_count * 0.07) * 3.0
            noise += random.uniform(-0.5, 0.5)
            target_x = predicted_x - PADDLE_WIDTH / 2.0 + noise

            diff = target_x - self.paddle_x
            # Smooth acceleration (more natural looking)
            max_speed = 2.5 + abs(diff) * 0.1
            max_speed = min(max_speed, 4.0)
            move = max(-max_speed, min(max_speed, diff * 0.3))
            self.paddle_x += move
            self.paddle_x = max(0.0, min(float(SIZE - PADDLE_WIDTH), self.paddle_x))
        else:
            # Ball is on another face - chase it by rotating
            if self._frame_count % 30 == 0:
                diff = (ball.face - self.current_face) % 4
                if diff == 1:
                    self.start_rotation(1)
                elif diff == 3:
                    self.start_rotation(-1)
                elif diff == 2:
                    self.start_rotation(random.choice([-1, 1]))

        # Showcase rotation periodically in demo
        if (ball.face == self.current_face and
                self._frame_count % 200 == 100 and
                not self.rotating):
            # Only rotate if current face is mostly cleared
            if self._remaining_bricks(self.current_face) < 5:
                direction = 1 if self._remaining_bricks((self.current_face + 1) % 4) > 0 else -1
                self.start_rotation(direction)

    def _predict_ball_x(self, ball):
        """Predict where ball will arrive at paddle Y."""
        sim_x, sim_y = ball.x, ball.y
        sim_vx, sim_vy = ball.vx, ball.vy
        if sim_vy <= 0:
            return sim_x

        target_y = float(PADDLE_Y - BALL_SIZE)
        for _ in range(200):
            speed = math.sqrt(sim_vx ** 2 + sim_vy ** 2)
            if speed < 0.01:
                break
            dt = 0.5 / speed
            sim_x += sim_vx * dt
            sim_y += sim_vy * dt
            if sim_x <= 0:
                sim_vx = abs(sim_vx)
            elif sim_x >= SIZE - BALL_SIZE:
                sim_vx = -abs(sim_vx)
            if sim_y < BRICK_AREA_TOP:
                sim_vy = abs(sim_vy)
            if sim_vy > 0 and sim_y >= target_y:
                break
        return sim_x

    def draw(self, frame_count):
        """Render the game state to a PIL Image with full visual effects."""
        image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Subtle animated background pattern
        self._draw_background(image, frame_count)

        if self.rotating:
            self._draw_rotation(image, draw)
        else:
            self._draw_normal(image, draw)

        # Draw particles (always on top of game elements)
        self._draw_particles(image)

        # HUD (always drawn on top)
        self._draw_hud(image, draw)

        # Edge glow indicators (bottom zone)
        self._draw_edge_glow(image, draw)

        # Screen flash effect
        if self.flash_timer > 0:
            flash_alpha = self.flash_timer / FLASH_DURATION * 0.3
            for y in range(SIZE):
                for x in range(SIZE):
                    if random.random() < flash_alpha:
                        existing = image.getpixel((x, y))
                        blended = _blend_color(existing, self.flash_color, flash_alpha)
                        image.putpixel((x, y), blended)

        # Apply screen shake (shift the final image)
        if self.shake_x != 0 or self.shake_y != 0:
            shifted = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
            shifted.paste(image, (self.shake_x, self.shake_y))
            image = shifted

        return image

    def _draw_background(self, image, frame_count):
        """Subtle animated background with face-tinted vignette."""
        face_color = FACE_COLORS[self.current_face]
        pulse = self.bg_pulse

        # Corner vignette with face color (very subtle)
        for y in range(HUD_HEIGHT, GLOW_ZONE_TOP):
            for x in [0, 1, SIZE - 2, SIZE - 1]:
                dist_from_edge = min(x, SIZE - 1 - x) / float(SIZE)
                intensity = (1.0 - dist_from_edge * 10) * 0.08
                if pulse > 0:
                    intensity += pulse * 0.15
                if intensity > 0:
                    c = _scale_color(face_color, intensity)
                    existing = image.getpixel((x, y))
                    blended = tuple(min(255, existing[i] + c[i]) for i in range(3))
                    image.putpixel((x, y), blended)

        # Subtle scan line effect (alternating darker rows)
        if frame_count % 3 == 0:
            for y in range(BRICK_AREA_TOP, GLOW_ZONE_TOP, 4):
                for x in range(SIZE):
                    existing = image.getpixel((x, y))
                    if existing != BG_COLOR:
                        continue
                    image.putpixel((x, y), (3, 3, 12))

    def _draw_normal(self, image, draw):
        """Draw the current face with full visual polish."""
        face_idx = self.current_face

        # Draw bricks with highlights and shadows
        bricks = self.face_bricks[face_idx]
        for brick in bricks:
            if not brick["alive"]:
                continue
            x1, y1, x2, y2 = self._brick_rect(brick)
            color = BRICK_ROW_COLORS[brick["row"] % len(BRICK_ROW_COLORS)]
            # Subtle face tint
            fc = FACE_COLORS[face_idx]
            color = tuple(min(255, int(c * 0.85 + f * 0.15)) for c, f in zip(color, fc))

            # Main brick body
            draw.rectangle([(x1, y1), (x2, y2)], fill=color)
            # Top highlight
            highlight = _scale_color(color, 1.3)
            highlight = tuple(min(255, c) for c in highlight)
            if y1 < SIZE:
                for hx in range(x1, x2 + 1):
                    if 0 <= hx < SIZE:
                        image.putpixel((hx, y1), highlight)
            # Bottom shadow
            shadow = _scale_color(color, 0.6)
            if y2 < SIZE:
                for hx in range(x1, x2 + 1):
                    if 0 <= hx < SIZE:
                        image.putpixel((hx, y2), shadow)

        # Draw paddle with glow and gradient
        self._draw_paddle(image)

        # Draw ball (only if on visible face)
        self._draw_ball(image)

    def _draw_paddle(self, image):
        """Draw paddle with gradient, glow effect, and smooth edges."""
        px = int(self.paddle_x)

        # Paddle glow halo (subtle spread behind paddle)
        if self.paddle_glow > 0.1:
            glow_color = _scale_color(PADDLE_COLOR, self.paddle_glow * 0.4)
            for i in range(-1, PADDLE_WIDTH + 1):
                for h in range(-1, PADDLE_HEIGHT + 1):
                    cx = px + i
                    cy = PADDLE_Y + h
                    if 0 <= cx < SIZE and 0 <= cy < SIZE:
                        existing = image.getpixel((cx, cy))
                        blended = tuple(min(255, existing[j] + glow_color[j]) for j in range(3))
                        image.putpixel((cx, cy), blended)

        # Main paddle body with gradient
        for i in range(PADDLE_WIDTH):
            dist = abs(i - PADDLE_WIDTH / 2.0) / (PADDLE_WIDTH / 2.0)
            brightness = 1.0 - 0.35 * dist * dist
            base_color = PADDLE_COLOR
            if self.paddle_glow > 0.1:
                base_color = _blend_color(PADDLE_COLOR, PADDLE_HIGHLIGHT, self.paddle_glow * 0.5)
            c = _scale_color(base_color, brightness)
            for h in range(PADDLE_HEIGHT):
                cx = px + i
                cy = PADDLE_Y + h
                if 0 <= cx < SIZE and 0 <= cy < SIZE:
                    # Top row slightly brighter
                    if h == 0:
                        c_row = _scale_color(c, 1.15)
                        c_row = tuple(min(255, v) for v in c_row)
                    else:
                        c_row = _scale_color(c, 0.85)
                    image.putpixel((cx, cy), c_row)

    def _draw_ball(self, image):
        """Draw ball with trail effect and glow."""
        ball = self.ball
        if not ball or ball.face != self.current_face:
            return

        ball_color = BALL_COLORS[ball.color_idx]

        # Hit flash override
        if ball.hit_flash > 0:
            flash_t = ball.hit_flash / 3.0
            ball_color = _blend_color(ball_color, (255, 255, 255), flash_t * 0.5)

        # Trail (fading positions)
        for i, (tx, ty) in enumerate(ball.trail):
            fade = (i + 1) / (TRAIL_LENGTH + 1)
            trail_color = _scale_color(ball_color, fade * 0.5)
            bx, by = int(tx), int(ty)
            for ox in range(BALL_SIZE):
                for oy in range(BALL_SIZE):
                    ppx, ppy = bx + ox, by + oy
                    if 0 <= ppx < SIZE and 0 <= ppy < SIZE:
                        existing = image.getpixel((ppx, ppy))
                        blended = tuple(max(existing[j], trail_color[j]) for j in range(3))
                        image.putpixel((ppx, ppy), blended)

        # Ball core glow (1px around ball)
        glow_color = _scale_color(ball_color, 0.3)
        bx, by = int(ball.x), int(ball.y)
        for ox in range(-1, BALL_SIZE + 1):
            for oy in range(-1, BALL_SIZE + 1):
                ppx, ppy = bx + ox, by + oy
                if 0 <= ppx < SIZE and 0 <= ppy < SIZE:
                    existing = image.getpixel((ppx, ppy))
                    blended = tuple(max(existing[j], glow_color[j]) for j in range(3))
                    image.putpixel((ppx, ppy), blended)

        # Ball core (bright center)
        for ox in range(BALL_SIZE):
            for oy in range(BALL_SIZE):
                ppx, ppy = bx + ox, by + oy
                if 0 <= ppx < SIZE and 0 <= ppy < SIZE:
                    image.putpixel((ppx, ppy), ball_color)

    def _draw_rotation(self, image, draw):
        """Draw the Fez-style rotation with smooth easing and depth."""
        raw_progress = self.rotation_frame / float(ROTATION_FRAMES)
        progress = _ease_in_out_cubic(raw_progress)  # smooth easing
        direction = self.rotation_dir

        old_face = self.old_face
        new_face = self.new_face

        if direction > 0:
            # Rotating right: old compresses to left, new expands from right
            split_x = int(SIZE * (1.0 - progress))

            # Old face (left portion, compressing)
            if split_x > 0:
                for dest_x in range(split_x):
                    src_col = int(dest_x / (1.0 - progress)) if progress < 1.0 else dest_x
                    src_col = min(src_col, SIZE - 1)
                    # Y-shear for depth (more shear at the compression edge)
                    edge_dist = dest_x / float(max(1, split_x))
                    shear = int(progress * 3.0 * edge_dist)
                    # Darken compressed side for depth
                    darken = 1.0 - progress * 0.4 * edge_dist
                    self._draw_face_column_smooth(image, old_face, src_col, dest_x,
                                                  y_shear=shear, darken=darken)

            # New face (right portion, expanding)
            if split_x < SIZE:
                for dest_x in range(split_x, SIZE):
                    local_x = dest_x - split_x
                    width = SIZE - split_x
                    src_col = int(local_x * SIZE / max(1, width))
                    src_col = min(src_col, SIZE - 1)
                    # Y-shear (opposite direction)
                    edge_dist = 1.0 - local_x / float(max(1, width))
                    shear = int((1.0 - progress) * 3.0 * edge_dist)
                    darken = 1.0 - (1.0 - progress) * 0.4 * edge_dist
                    self._draw_face_column_smooth(image, new_face, src_col, dest_x,
                                                  y_shear=-shear, darken=darken)
        else:
            # Rotating left: old compresses to right, new expands from left
            split_x = int(SIZE * progress)

            # New face (left portion, expanding)
            if split_x > 0:
                for dest_x in range(split_x):
                    src_col = int(dest_x * SIZE / max(1, split_x))
                    src_col = min(src_col, SIZE - 1)
                    edge_dist = 1.0 - dest_x / float(max(1, split_x))
                    shear = int((1.0 - progress) * 3.0 * edge_dist)
                    darken = 1.0 - (1.0 - progress) * 0.4 * edge_dist
                    self._draw_face_column_smooth(image, new_face, src_col, dest_x,
                                                  y_shear=shear, darken=darken)

            # Old face (right portion, compressing)
            if split_x < SIZE:
                for dest_x in range(split_x, SIZE):
                    local_x = dest_x - split_x
                    width = SIZE - split_x
                    src_col = int(local_x * SIZE / max(1, width)) if width > 0 else 0
                    src_col = min(src_col, SIZE - 1)
                    edge_dist = local_x / float(max(1, width))
                    shear = int(progress * 3.0 * edge_dist)
                    darken = 1.0 - progress * 0.4 * edge_dist
                    self._draw_face_column_smooth(image, old_face, src_col, dest_x,
                                                  y_shear=-shear, darken=darken)

        # Draw paddle during rotation (dimmed, frozen)
        px = int(self.paddle_x)
        dim_color = _scale_color(PADDLE_COLOR, 0.4)
        for i in range(PADDLE_WIDTH):
            cx = px + i
            for h in range(PADDLE_HEIGHT):
                cy = PADDLE_Y + h
                if 0 <= cx < SIZE and 0 <= cy < SIZE:
                    image.putpixel((cx, cy), dim_color)

    def _draw_face_column_smooth(self, image, face_idx, src_col, dest_x, y_shear=0, darken=1.0):
        """Draw a single column of a face's bricks with shading."""
        if dest_x < 0 or dest_x >= SIZE:
            return

        bricks = self.face_bricks[face_idx]
        for brick in bricks:
            if not brick["alive"]:
                continue
            x1, y1, x2, y2 = self._brick_rect(brick)
            if x1 <= src_col <= x2:
                color = BRICK_ROW_COLORS[brick["row"] % len(BRICK_ROW_COLORS)]
                fc = FACE_COLORS[face_idx]
                color = tuple(min(255, int(c * 0.85 + f * 0.15)) for c, f in zip(color, fc))
                color = _scale_color(color, darken)
                for py in range(y1, y2 + 1):
                    dy = py + y_shear
                    if BRICK_AREA_TOP <= dy < GLOW_ZONE_TOP:
                        image.putpixel((dest_x, dy), color)

    def _draw_particles(self, image):
        """Draw all particles with alpha blending."""
        for p in self.particles:
            px_p, py_p = int(p.x), int(p.y)
            alpha = p.alpha
            if alpha <= 0:
                continue
            color = _scale_color(p.color, alpha)
            for ox in range(p.size):
                for oy in range(p.size):
                    x, y = px_p + ox, py_p + oy
                    if 0 <= x < SIZE and 0 <= y < SIZE:
                        existing = image.getpixel((x, y))
                        blended = tuple(min(255, existing[j] + color[j]) for j in range(3))
                        image.putpixel((x, y), blended)

    def _draw_hud(self, image, draw):
        """Draw the HUD with score, face indicator, lives, and combo."""
        # Score (top-left)
        _draw_number(image, self.score, 1, 1, HUD_COLOR)

        # Face indicator (center) - 4 pips, current one bright and large
        center_x = SIZE // 2 - 5
        for i in range(4):
            dot_x = center_x + i * 3
            face_c = FACE_COLORS[i]
            if i == self.current_face:
                # Bright, 2x2 dot for current face
                for ox in range(2):
                    for oy in range(2):
                        px = dot_x + ox
                        py = 1 + oy
                        if 0 <= px < SIZE and 0 <= py < SIZE:
                            image.putpixel((px, py), face_c)
            else:
                # Dim single pixel
                dim = _scale_color(face_c, 0.25)
                if 0 <= dot_x < SIZE:
                    image.putpixel((dot_x, 2), dim)

        # Ball on different face indicator (animated arrow)
        if self.ball and self.ball.face != self.current_face and not self.ball.stuck:
            diff = (self.ball.face - self.current_face) % 4
            arrow_pulse = int(2 + math.sin(self.offscreen_indicator_phase) * 2)
            arrow_color = FACE_COLORS[self.ball.face]
            if diff == 1 or diff == 2:
                # Arrow pointing right
                ax = SIZE - 3
                ay = 2
                if 0 <= ax < SIZE:
                    image.putpixel((ax, ay), arrow_color)
                    if ax + 1 < SIZE:
                        image.putpixel((ax + 1, ay), arrow_color)
            if diff == 3 or diff == 2:
                # Arrow pointing left
                ax = center_x - 3
                ay = 2
                if 0 <= ax < SIZE:
                    image.putpixel((ax, ay), arrow_color)
                    if ax - 1 >= 0:
                        image.putpixel((ax - 1, ay), arrow_color)

        # Lives (top-right) - colored dots
        for i in range(self.lives):
            lx = SIZE - 3 - i * 3
            if 0 <= lx < SIZE:
                image.putpixel((lx, 1), (255, 80, 80))
                image.putpixel((lx, 2), (255, 40, 40))

        # Combo indicator (brief flash near score)
        if self.combo >= 2 and self.combo_timer > 40:
            combo_color = _scale_color((255, 255, 100), min(1.0, self.combo * 0.25))
            cx = 1
            cy = 4
            # Small "x2", "x3" etc using minimal pixels
            _draw_digit(image, 'x'[0] if False else str(min(self.combo, 9))[0],
                        cx + 14, 1, combo_color)

    def _draw_edge_glow(self, image, draw):
        """Draw edge glow indicators with smooth gradients."""
        # Left glow
        if self.glow_left > 0:
            intensity = _ease_out_quad(self.glow_left / GLOW_DURATION)
            pulse = 0.6 + 0.4 * math.sin(self._frame_count * 0.4)
            brightness = intensity * pulse
            color = self.glow_left_color
            for y in range(GLOW_ZONE_TOP, min(GLOW_ZONE_TOP + GLOW_ZONE_HEIGHT, SIZE)):
                for x in range(min(10, SIZE)):
                    fade = (1.0 - x / 10.0) ** 1.5
                    c = _scale_color(color, brightness * fade)
                    if c[0] > 2 or c[1] > 2 or c[2] > 2:
                        existing = image.getpixel((x, y))
                        blended = tuple(min(255, existing[j] + c[j]) for j in range(3))
                        image.putpixel((x, y), blended)

        # Right glow
        if self.glow_right > 0:
            intensity = _ease_out_quad(self.glow_right / GLOW_DURATION)
            pulse = 0.6 + 0.4 * math.sin(self._frame_count * 0.4)
            brightness = intensity * pulse
            color = self.glow_right_color
            for y in range(GLOW_ZONE_TOP, min(GLOW_ZONE_TOP + GLOW_ZONE_HEIGHT, SIZE)):
                for x in range(max(0, SIZE - 10), SIZE):
                    fade = ((x - (SIZE - 10)) / 10.0) ** 1.5
                    c = _scale_color(color, brightness * fade)
                    if c[0] > 2 or c[1] > 2 or c[2] > 2:
                        existing = image.getpixel((x, y))
                        blended = tuple(min(255, existing[j] + c[j]) for j in range(3))
                        image.putpixel((x, y), blended)

        # Persistent indicator when ball is offscreen (subtle pulsing border)
        if self.ball and self.ball.face != self.current_face and not self.ball.stuck:
            diff = (self.ball.face - self.current_face) % 4
            pulse = 0.3 + 0.3 * math.sin(self.offscreen_indicator_phase)
            ball_face_color = FACE_COLORS[self.ball.face]

            if diff == 1:  # one right
                for y in range(GLOW_ZONE_TOP, min(GLOW_ZONE_TOP + GLOW_ZONE_HEIGHT, SIZE)):
                    c = _scale_color(ball_face_color, pulse)
                    px = SIZE - 1
                    if 0 <= px < SIZE and 0 <= y < SIZE:
                        image.putpixel((px, y), c)
                    px = SIZE - 2
                    if 0 <= px < SIZE:
                        image.putpixel((px, y), _scale_color(ball_face_color, pulse * 0.5))
            elif diff == 3:  # one left
                for y in range(GLOW_ZONE_TOP, min(GLOW_ZONE_TOP + GLOW_ZONE_HEIGHT, SIZE)):
                    c = _scale_color(ball_face_color, pulse)
                    if 0 <= y < SIZE:
                        image.putpixel((0, y), c)
                        image.putpixel((1, y), _scale_color(ball_face_color, pulse * 0.5))
            elif diff == 2:  # opposite
                for y in range(GLOW_ZONE_TOP, min(GLOW_ZONE_TOP + GLOW_ZONE_HEIGHT, SIZE)):
                    c = _scale_color(ball_face_color, pulse * 0.5)
                    if 0 <= y < SIZE:
                        image.putpixel((0, y), c)
                        image.putpixel((SIZE - 1, y), c)


# ---------------------------------------------------------------------------
# Demo mode (AI plays)
# ---------------------------------------------------------------------------

def _run_demo(matrix, duration, start_time):
    """AI-controlled super breakout demo."""
    game = SuperBreakoutGame()

    while time.time() - start_time < duration:
        if should_stop():
            return
        frame_start = time.time()

        result = game.step(ai_mode=True)
        image = game.draw(game._frame_count)
        matrix.SetImage(image)

        if result == "cleared":
            if not interruptible_sleep(1.0):
                return
            game = SuperBreakoutGame()

        elif result == "lost_life":
            if not interruptible_sleep(0.3):
                return
            game.launch_ball()

        elif result == "game_over":
            if not interruptible_sleep(1.5):
                return
            game = SuperBreakoutGame()

        elapsed = time.time() - frame_start
        sleep_time = FRAME_DUR - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Interactive mode (player controls)
# ---------------------------------------------------------------------------

def _run_interactive(matrix, controller, start_time):
    """Player-controlled super breakout."""
    from src.input.controller import wants_quit, Button, EventType

    game = SuperBreakoutGame()
    show_banner(matrix, ["SUPER BREAKOUT", "B:ROTATE A:LAUNCH"],
                color=PADDLE_COLOR, hold=1.5)

    _MAX_SECONDS = 86400

    while time.time() - start_time < _MAX_SECONDS:
        if should_stop():
            return
        frame_start = time.time()

        events = controller.poll_events()
        if wants_quit(controller):
            return

        # Player input - smooth paddle movement
        d = controller.get_direction()
        if d:
            move_speed = 3.0
            game.move_paddle(d[0] * move_speed)

        for ev in events:
            if ev.type is EventType.PRESSED:
                if ev.button in (Button.A, Button.UP):
                    game.launch_ball()
                elif ev.button is Button.B:
                    game.start_rotation(1)
                elif ev.button is Button.SELECT:
                    game.start_rotation(-1)

        result = game.step(ai_mode=False)
        image = game.draw(game._frame_count)
        matrix.SetImage(image)

        if result == "cleared":
            safe_rumble(controller, 0.8, 300)
            show_banner(matrix, ["ALL CLEAR!", f"SCORE:{game.score}"],
                        color=(80, 255, 180), hold=2.0)
            game = SuperBreakoutGame()
            show_banner(matrix, ["NEXT ROUND"],
                        color=PADDLE_COLOR, hold=0.8)

        elif result == "lost_life":
            safe_rumble(controller, 0.4, 200)
            if not interruptible_sleep(0.4):
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
    """Run Super Breakout.

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
        logger.error("Error in super_breakout: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
