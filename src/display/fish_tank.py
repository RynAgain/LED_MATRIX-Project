#!/usr/bin/env python3
"""
Fish Tank -- Animated aquarium demo for 64x64 LED matrix.

Features:
- Multiple colorful fish swimming left/right with smooth pixel movement
- Fish with varied body shapes, sizes, and color palettes
- Animated tail fin wiggle
- Bubbles rising from the bottom with slight horizontal drift
- Layered background: sand bottom, plants, subtle water gradient
- Gentle "current" that sways plants
- Fish avoid each other and turn around at edges
"""

import time
import math
import random
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FPS = 15
FRAME_DUR = 1.0 / FPS

# Water colors (top to bottom gradient)
WATER_TOP = (0, 5, 20)
WATER_BOTTOM = (0, 15, 35)

# Sand/gravel colors
SAND_COLORS = [(140, 120, 60), (130, 110, 50), (150, 130, 70), (120, 100, 45)]

# Plant colors
PLANT_GREEN = [(0, 100, 30), (0, 130, 40), (0, 80, 25), (20, 150, 50)]

# Fish color palettes (body_main, body_accent, fin_color)
FISH_PALETTES = [
    ((255, 100, 0), (255, 180, 0), (255, 50, 0)),       # Orange/gold clownfish
    ((0, 150, 255), (0, 200, 255), (0, 100, 200)),      # Blue tang
    ((255, 50, 100), (255, 150, 180), (200, 0, 60)),    # Pink/red
    ((100, 255, 100), (180, 255, 100), (0, 180, 0)),    # Green
    ((255, 255, 0), (255, 200, 0), (200, 150, 0)),      # Yellow
    ((200, 0, 255), (255, 100, 255), (150, 0, 200)),    # Purple
    ((255, 255, 255), (200, 200, 255), (150, 150, 200)),  # Silver
    ((255, 80, 80), (255, 200, 100), (200, 40, 40)),    # Red/orange
]

# Bubble color
BUBBLE_COLOR = (100, 180, 255)
BUBBLE_HIGHLIGHT = (200, 230, 255)


class Fish:
    """A single fish swimming in the tank."""

    def __init__(self):
        palette = random.choice(FISH_PALETTES)
        self.body_color = palette[0]
        self.accent_color = palette[1]
        self.fin_color = palette[2]

        # Size (body length in pixels)
        self.size = random.choice([3, 4, 5, 6])

        # Position (float for smooth movement)
        self.x = random.uniform(4, WIDTH - 4)
        self.y = random.uniform(8, HEIGHT - 14)

        # Direction: 1 = right, -1 = left
        self.direction = random.choice([-1, 1])

        # Speed (pixels per frame)
        self.speed = random.uniform(0.3, 0.8)

        # Vertical drift (subtle up/down movement)
        self.vy = random.uniform(-0.1, 0.1)
        self.drift_phase = random.uniform(0, math.pi * 2)

        # Tail wiggle phase
        self.tail_phase = random.uniform(0, math.pi * 2)

        # Eye position relative to body front
        self.eye_offset = max(1, self.size - 2)

    def update(self, tick, other_fish):
        """Update fish position and behavior."""
        # Tail animation
        self.tail_phase += 0.4

        # Horizontal movement
        self.x += self.speed * self.direction

        # Gentle vertical drift (sinusoidal)
        self.drift_phase += 0.03
        self.y += math.sin(self.drift_phase) * 0.15 + self.vy

        # Boundary avoidance (turn around before hitting walls)
        margin = self.size + 2
        if self.x < margin:
            self.direction = 1
            self.x = margin
        elif self.x > WIDTH - margin:
            self.direction = -1
            self.x = WIDTH - margin

        # Vertical boundaries (stay in water, above sand)
        if self.y < 6:
            self.y = 6
            self.vy = abs(self.vy)
        elif self.y > HEIGHT - 14:
            self.y = HEIGHT - 14
            self.vy = -abs(self.vy)

        # Avoid other fish (simple repulsion)
        for other in other_fish:
            if other is self:
                continue
            dx = self.x - other.x
            dy = self.y - other.y
            dist_sq = dx * dx + dy * dy
            if dist_sq < 64:  # Within 8 pixels
                if dist_sq > 0:
                    dist = math.sqrt(dist_sq)
                    # Push away
                    self.x += (dx / dist) * 0.3
                    self.y += (dy / dist) * 0.2

        # Occasionally change vertical drift
        if random.random() < 0.005:
            self.vy = random.uniform(-0.1, 0.1)

    def draw(self, draw, tick):
        """Draw the fish at its current position -- proper fish shape.

        Shape: pointed nose -> wide middle -> narrow tail stem -> V-tail fork.
        """
        ix = int(self.x)
        iy = int(self.y)

        # Tail wiggle offset
        tail_wiggle = int(math.sin(self.tail_phase) * 1)

        # Body direction (1=right, -1=left)
        d = self.direction

        # Fish body profile: define height at each x-offset from center
        # Positive offsets go toward the HEAD (facing direction)
        # Negative offsets go toward the TAIL
        body_len = self.size
        half = body_len // 2

        # Draw body: elongated oval shape (wide middle, tapers to nose)
        for bx_offset in range(-half, half + 1):
            # Position along body: -1 (tail end) to +1 (nose)
            t = bx_offset / (half + 0.1)

            # Height profile: oval, widest at center, tapers both ends
            # Nose tapers more sharply than tail
            if t > 0:
                # Nose side: sharp taper
                h = max(0, int(1.5 * (1 - t * t) * (body_len / 4)))
            else:
                # Tail side: gentler taper (but NOT wider than middle)
                h = max(0, int(1.5 * (1 - t * t * 0.7) * (body_len / 4)))

            px = ix + bx_offset * d
            for by in range(-h, h + 1):
                py = iy + by
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    color = self.accent_color if by <= 0 else self.body_color
                    draw.point((px, py), fill=color)

        # Tail fork (V-shape, behind the body)
        tail_base_x = ix - d * (half + 1)
        # Upper fork
        ty1 = iy - 1 + tail_wiggle
        tx1 = tail_base_x - d
        if 0 <= tx1 < WIDTH and 0 <= ty1 < HEIGHT:
            draw.point((tx1, ty1), fill=self.fin_color)
        ty1u = iy - 2 + tail_wiggle
        tx1u = tail_base_x - d * 2
        if 0 <= tx1u < WIDTH and 0 <= ty1u < HEIGHT:
            draw.point((tx1u, ty1u), fill=self.fin_color)
        # Lower fork
        ty2 = iy + 1 + tail_wiggle
        if 0 <= tx1 < WIDTH and 0 <= ty2 < HEIGHT:
            draw.point((tx1, ty2), fill=self.fin_color)
        ty2d = iy + 2 + tail_wiggle
        if 0 <= tx1u < WIDTH and 0 <= ty2d < HEIGHT:
            draw.point((tx1u, ty2d), fill=self.fin_color)

        # Eye (single bright pixel near nose)
        eye_x = ix + d * (half - 1)
        eye_y = iy
        if 0 <= eye_x < WIDTH and 0 <= eye_y < HEIGHT:
            draw.point((eye_x, eye_y), fill=(255, 255, 255))


class Bubble:
    """A rising bubble in the tank."""

    def __init__(self, x=None, y=None):
        self.x = x if x is not None else random.uniform(4, WIDTH - 4)
        self.y = y if y is not None else float(HEIGHT - random.randint(8, 12))
        self.speed = random.uniform(0.3, 0.6)
        self.size = random.choice([1, 1, 1, 2])  # Mostly small
        self.drift = random.uniform(-0.05, 0.05)
        self.phase = random.uniform(0, math.pi * 2)

    def update(self):
        """Move bubble upward with slight drift."""
        self.y -= self.speed
        self.phase += 0.1
        self.x += self.drift + math.sin(self.phase) * 0.1
        return self.y > 0  # Return False if off-screen

    def draw(self, draw):
        """Draw the bubble."""
        ix, iy = int(self.x), int(self.y)
        if self.size == 1:
            if 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
                draw.point((ix, iy), fill=BUBBLE_COLOR)
        else:
            draw.ellipse([(ix - 1, iy - 1), (ix + 1, iy + 1)],
                         outline=BUBBLE_COLOR)
            if 0 <= ix < WIDTH and 0 <= iy - 1 < HEIGHT:
                draw.point((ix, iy - 1), fill=BUBBLE_HIGHLIGHT)


class Plant:
    """A swaying plant on the tank floor."""

    def __init__(self, x, height):
        self.x = x
        self.height = height
        self.color = random.choice(PLANT_GREEN)
        self.phase = random.uniform(0, math.pi * 2)
        self.sway_speed = random.uniform(0.02, 0.05)

    def draw(self, draw, tick):
        """Draw the plant with gentle sway."""
        self.phase += self.sway_speed
        base_y = HEIGHT - 8  # Sand starts at HEIGHT-8

        for seg in range(self.height):
            # More sway at the top
            sway = math.sin(self.phase + seg * 0.3) * (seg * 0.3)
            px = int(self.x + sway)
            py = base_y - seg

            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                # Slightly vary green along the stalk
                brightness = 1.0 - (seg / self.height) * 0.3
                color = (
                    int(self.color[0] * brightness),
                    int(self.color[1] * brightness),
                    int(self.color[2] * brightness),
                )
                draw.point((px, py), fill=color)

                # Draw leaves on taller plants
                if self.height > 6 and seg > 2 and seg % 3 == 0:
                    leaf_dir = 1 if seg % 2 == 0 else -1
                    for lx in range(1, 3):
                        lpx = px + lx * leaf_dir
                        lpy = py + (lx - 1)
                        if 0 <= lpx < WIDTH and 0 <= lpy < HEIGHT:
                            draw.point((lpx, lpy), fill=color)


def _draw_background(draw):
    """Draw the tank background: water gradient + sand bottom."""
    # Water gradient (top to bottom)
    for y in range(HEIGHT - 8):
        t = y / (HEIGHT - 8)
        r = int(WATER_TOP[0] + (WATER_BOTTOM[0] - WATER_TOP[0]) * t)
        g = int(WATER_TOP[1] + (WATER_BOTTOM[1] - WATER_TOP[1]) * t)
        b = int(WATER_TOP[2] + (WATER_BOTTOM[2] - WATER_TOP[2]) * t)
        draw.line([(0, y), (WIDTH - 1, y)], fill=(r, g, b))

    # Sand/gravel bottom (bottom 8 pixels)
    for y in range(HEIGHT - 8, HEIGHT):
        for x in range(WIDTH):
            # Random gravel texture
            color = SAND_COLORS[(x * 7 + y * 13) % len(SAND_COLORS)]
            # Slight variation
            variation = ((x + y) * 3) % 10 - 5
            color = (
                max(0, min(255, color[0] + variation)),
                max(0, min(255, color[1] + variation)),
                max(0, min(255, color[2] + variation)),
            )
            draw.point((x, y), fill=color)


def run(matrix, duration=60):
    """Run the fish tank animation for the specified duration."""
    start_time = time.time()
    tick = 0

    # Create fish
    num_fish = random.randint(5, 8)
    fish_list = [Fish() for _ in range(num_fish)]

    # Create plants
    plants = []
    num_plants = random.randint(4, 7)
    for _ in range(num_plants):
        px = random.randint(3, WIDTH - 3)
        ph = random.randint(5, 12)
        plants.append(Plant(px, ph))

    # Bubbles list
    bubbles = []

    # Pre-render background (static, only computed once)
    bg_image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_image)
    _draw_background(bg_draw)

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            tick += 1

            # Start with the pre-rendered background
            image = bg_image.copy()
            draw = ImageDraw.Draw(image)

            # Draw plants (behind fish)
            for plant in plants:
                plant.draw(draw, tick)

            # Update and draw bubbles
            bubbles = [b for b in bubbles if b.update()]
            for bubble in bubbles:
                bubble.draw(draw)

            # Spawn new bubbles occasionally
            if random.random() < 0.08:
                # Sometimes bubbles come from plant positions
                if plants and random.random() < 0.5:
                    plant = random.choice(plants)
                    bubbles.append(Bubble(x=plant.x, y=HEIGHT - 8 - plant.height))
                else:
                    bubbles.append(Bubble())

            # Update and draw fish
            for fish in fish_list:
                fish.update(tick, fish_list)
            for fish in fish_list:
                fish.draw(draw, tick)

            matrix.SetImage(image)

            # Frame rate control
            elapsed = time.time() - frame_start
            sleep_time = FRAME_DUR - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in fish tank: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
