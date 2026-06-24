#!/usr/bin/env python3
"""
Icy Tower -- Endless vertical platformer demo for 64x64 LED matrix.

Inspired by the classic PC game Icy Tower. A character jumps between
platforms that scroll upward. Features:
- Auto-scrolling camera that follows the character
- Platforms get thinner and more spaced as you climb
- Character bounces higher with combo jumps
- Speed increases with height
- Colorful platform palette that shifts with altitude
- Score based on height reached
- Particle effects on landing
"""

import time
import math
import random
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop
from src.display._fonts import _draw_text, _text_width

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FPS = 20
FRAME_DUR = 1.0 / FPS

# Physics
GRAVITY = 0.45
JUMP_VEL = -4.5
COMBO_BONUS = -1.2  # Extra velocity per combo level
MAX_COMBO = 5
MOVE_SPEED = 2.0
AIR_CONTROL = 0.85

# Colors
BG_TOP = (5, 5, 25)
BG_BOTTOM = (0, 0, 10)
CHAR_COLOR = (255, 220, 80)
CHAR_HAT = (200, 50, 50)
SCORE_COLOR = (180, 180, 220)
WALL_COLOR = (25, 25, 50)


def _platform_color(altitude):
    """Generate platform color based on altitude for variety."""
    hue_shift = (altitude * 0.02) % 1.0
    r = int(80 + 100 * abs(math.sin(hue_shift * math.pi * 2)))
    g = int(80 + 100 * abs(math.sin((hue_shift + 0.33) * math.pi * 2)))
    b = int(80 + 100 * abs(math.sin((hue_shift + 0.66) * math.pi * 2)))
    return (r, g, b)


class Platform:
    """A single platform."""

    def __init__(self, x, y, width):
        self.x = x
        self.y = y
        self.width = width
        self.color = _platform_color(y)


class Character:
    """The jumping character."""

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.facing = 1
        self.combo = 0
        self.highest_y = y

    def update(self):
        """Update physics."""
        self.vy += GRAVITY
        if self.vy > 10:
            self.vy = 10

        self.x += self.vx
        self.y += self.vy

        # Wrap horizontally
        if self.x < 0:
            self.x = WIDTH - 1
        elif self.x >= WIDTH:
            self.x = 0

        self.on_ground = False


class IcyTowerGame:
    """Main game state."""

    def __init__(self):
        self.character = Character(WIDTH // 2, 500)
        self.platforms = []
        self.camera_y = 480.0  # World Y at bottom of screen
        self.score = 0
        self.particles = []
        self.tick = 0
        self.game_over = False

        # Generate initial platforms
        self._generate_platforms(400, 550)

    def _generate_platforms(self, y_top, y_bottom):
        """Generate platforms in a vertical range."""
        y = y_bottom
        while y > y_top:
            # Platform spacing increases with altitude (higher = harder)
            altitude = 550 - y
            spacing = 12 + min(altitude / 50, 10)
            y -= spacing + random.uniform(-2, 2)

            # Platform width decreases with altitude
            base_width = max(12, 30 - altitude / 30)
            width = int(base_width + random.uniform(-4, 4))
            width = max(8, min(40, width))

            x = random.randint(2, WIDTH - width - 2)
            self.platforms.append(Platform(x, y, width))

        # Always have a wide starting platform
        self.platforms.append(Platform(10, 540, 44))

    def _ensure_platforms_above(self):
        """Generate more platforms above visible area."""
        if not self.platforms:
            return

        highest = min(p.y for p in self.platforms)
        target = self.camera_y - HEIGHT - 50

        if highest > target:
            self._generate_platforms(target, highest - 5)

    def _remove_platforms_below(self):
        """Remove platforms that have scrolled off screen."""
        cutoff = self.camera_y + HEIGHT + 20
        self.platforms = [p for p in self.platforms if p.y < cutoff]

    def update(self, move_dx=0):
        """Update one game frame."""
        self.tick += 1
        char = self.character

        # Apply horizontal movement
        if move_dx != 0:
            speed = MOVE_SPEED if char.on_ground else MOVE_SPEED * AIR_CONTROL
            char.vx = move_dx * speed
            char.facing = 1 if move_dx > 0 else -1
        else:
            char.vx *= 0.7  # friction

        char.update()

        # Platform collisions (land on top only when falling)
        if char.vy > 0:
            for plat in self.platforms:
                if (char.x >= plat.x - 2 and char.x <= plat.x + plat.width + 2 and
                        char.y >= plat.y - 5 and char.y <= plat.y + 2):
                    char.y = plat.y - 5
                    char.vy = 0
                    char.on_ground = True

                    # Combo system: consecutive platforms without touching ground
                    char.combo = min(MAX_COMBO, char.combo + 1)

                    # Auto-jump
                    jump_power = JUMP_VEL + COMBO_BONUS * min(char.combo, 3)
                    char.vy = jump_power

                    # Spawn landing particles
                    for _ in range(3):
                        self.particles.append({
                            "x": char.x + random.uniform(-3, 3),
                            "y": char.y + 4,
                            "vx": random.uniform(-1, 1),
                            "vy": random.uniform(-1, 0.5),
                            "life": random.randint(5, 10),
                            "color": plat.color,
                        })
                    break

        # Update camera (smoothly follow character upward)
        target_cam = char.y - HEIGHT * 0.6
        if target_cam < self.camera_y:
            self.camera_y += (target_cam - self.camera_y) * 0.1

        # Track highest point
        if char.y < char.highest_y:
            char.highest_y = char.y
            self.score = max(0, int((550 - char.highest_y) / 5))

        # Game over if character falls below camera
        if char.y > self.camera_y + HEIGHT + 20:
            self.game_over = True

        # Platform management
        self._ensure_platforms_above()
        self._remove_platforms_below()

        # Update particles
        new_particles = []
        for p in self.particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.15
            p["life"] -= 1
            if p["life"] > 0:
                new_particles.append(p)
        self.particles = new_particles

    def draw(self):
        """Render the game."""
        image = Image.new("RGB", (WIDTH, HEIGHT), BG_BOTTOM)
        draw = ImageDraw.Draw(image)

        # Background gradient
        for y in range(HEIGHT):
            t = y / HEIGHT
            r = int(BG_TOP[0] * (1 - t) + BG_BOTTOM[0] * t)
            g = int(BG_TOP[1] * (1 - t) + BG_BOTTOM[1] * t)
            b = int(BG_TOP[2] * (1 - t) + BG_BOTTOM[2] * t)
            draw.line([(0, y), (WIDTH - 1, y)], fill=(r, g, b))

        # Side walls (subtle)
        draw.line([(0, 0), (0, HEIGHT - 1)], fill=WALL_COLOR)
        draw.line([(WIDTH - 1, 0), (WIDTH - 1, HEIGHT - 1)], fill=WALL_COLOR)

        cam = self.camera_y

        # Draw platforms
        for plat in self.platforms:
            screen_y = int(plat.y - cam)
            if -3 < screen_y < HEIGHT + 3:
                x1 = int(plat.x)
                x2 = int(plat.x + plat.width)
                # Platform body
                draw.rectangle([(x1, screen_y), (x2, screen_y + 2)], fill=plat.color)
                # Top highlight
                highlight = tuple(min(255, c + 40) for c in plat.color)
                draw.line([(x1, screen_y), (x2, screen_y)], fill=highlight)

        # Draw particles
        for p in self.particles:
            px = int(p["x"])
            py = int(p["y"] - cam)
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                alpha = p["life"] / 10.0
                c = tuple(int(v * alpha) for v in p["color"])
                draw.point((px, py), fill=c)

        # Draw character
        char = self.character
        cx = int(char.x)
        cy = int(char.y - cam)

        if 0 <= cy < HEIGHT - 4:
            # Body (3x4)
            draw.rectangle([cx - 1, cy, cx + 1, cy + 3], fill=CHAR_COLOR)
            # Hat
            draw.rectangle([cx - 1, cy - 1, cx + 1, cy - 1], fill=CHAR_HAT)
            draw.point((cx, cy - 2), fill=CHAR_HAT)
            # Eyes
            draw.point((cx + char.facing, cy + 1), fill=(0, 0, 0))

        # Score (top center)
        score_str = str(self.score)
        sw = _text_width(score_str, scale=1, spacing=1)
        _draw_text(draw, score_str, (WIDTH - sw) // 2, 2, SCORE_COLOR, scale=1, spacing=1)

        # Combo indicator
        if char.combo > 1:
            combo_str = f"x{char.combo}"
            _draw_text(draw, combo_str, 2, 2, (255, 200, 50), scale=1, spacing=0)

        return image


def _ai_control(game):
    """Simple AI that chases the nearest platform above."""
    char = game.character
    cam = game.camera_y

    # Find nearest platform above the character
    target = None
    min_dist = 999
    for plat in game.platforms:
        if plat.y < char.y - 3:  # Above character
            dy = char.y - plat.y
            if dy < min_dist and dy < 40:
                min_dist = dy
                target = plat

    if target:
        # Move toward platform center
        plat_cx = target.x + target.width / 2
        if char.x < plat_cx - 3:
            return 1
        elif char.x > plat_cx + 3:
            return -1

    # Default: slight random movement
    return random.choice([-1, 0, 0, 1])


def run(matrix, duration=60):
    """Run the Icy Tower demo for the specified duration."""
    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break

            game = IcyTowerGame()

            while not game.game_over and time.time() - start_time < duration:
                if should_stop():
                    return
                frame_start = time.time()

                # AI control
                move_dx = _ai_control(game)
                game.update(move_dx)

                image = game.draw()
                matrix.SetImage(image)

                elapsed = time.time() - frame_start
                sleep_time = FRAME_DUR - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # Game over - brief pause then restart
            if game.game_over:
                if not interruptible_sleep(1.5):
                    break

    except Exception as e:
        logger.error("Error in icy_tower: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
