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
from PIL import Image, ImageDraw, ImageChops
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

# Food flakes (feeding events)
FLAKE_COLORS = [(220, 170, 80), (200, 140, 60), (230, 190, 110)]
FEED_INTERVAL_MIN = 15 * FPS   # ticks between feeding events
FEED_INTERVAL_MAX = 35 * FPS
FLAKE_SEEK_RADIUS = 28.0       # fish notice food within this distance
FLAKE_EAT_RADIUS = 2.5

# Light rays / caustics
RAY_COLOR = (36, 55, 75)       # additive tint, strongest at the surface


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

    def update(self, tick, other_fish, flakes=None):
        """Update fish position and behavior."""
        # Tail animation
        self.tail_phase += 0.4

        # Food seeking: dart toward the nearest flake in range and eat it.
        seeking = False
        if flakes:
            best, best_d2 = None, FLAKE_SEEK_RADIUS * FLAKE_SEEK_RADIUS
            for flake in flakes:
                if flake.eaten:
                    continue
                fdx = flake.x - self.x
                fdy = flake.y - self.y
                d2 = fdx * fdx + fdy * fdy
                if d2 < best_d2:
                    best, best_d2 = flake, d2
            if best is not None:
                seeking = True
                if best_d2 <= FLAKE_EAT_RADIUS * FLAKE_EAT_RADIUS:
                    best.eaten = True
                    seeking = False
                else:
                    if abs(best.x - self.x) > 1.0:
                        self.direction = 1 if best.x > self.x else -1
                    # Swim harder toward food, pull vertically toward it
                    self.x += self.speed * 0.8 * self.direction
                    dy = best.y - self.y
                    self.y += max(-0.5, min(0.5, dy * 0.12))

        # Horizontal movement
        self.x += self.speed * self.direction

        # Gentle vertical drift (sinusoidal) -- skipped while chasing food
        self.drift_phase += 0.03
        if not seeking:
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


class Crab:
    """A crab walking along the sand bottom with animated claws."""

    def __init__(self):
        self.x = random.uniform(8, WIDTH - 8)
        self.y = float(HEIGHT - 7)  # On the sand
        self.direction = random.choice([-1, 1])
        self.speed = random.uniform(0.15, 0.35)
        self.claw_phase = random.uniform(0, math.pi * 2)
        self.color = random.choice([
            (200, 60, 30),   # Red crab
            (180, 100, 40),  # Orange-brown crab
            (160, 50, 50),   # Dark red crab
        ])
        self.pause_timer = 0

    def update(self, tick):
        """Move crab sideways along the sand."""
        self.claw_phase += 0.25

        if self.pause_timer > 0:
            self.pause_timer -= 1
            return

        self.x += self.speed * self.direction

        # Turn around at edges
        if self.x < 4:
            self.direction = 1
        elif self.x > WIDTH - 4:
            self.direction = -1

        # Occasionally pause and change direction
        if random.random() < 0.01:
            self.direction = -self.direction
            self.pause_timer = random.randint(10, 30)

    def draw(self, draw_ctx, tick):
        """Draw the crab: oval body + 2 animated claws + legs."""
        ix, iy = int(self.x), int(self.y)
        d = self.direction

        # Body (3x2 oval)
        if 0 <= ix < WIDTH - 2 and 0 <= iy < HEIGHT - 1:
            draw_ctx.rectangle([(ix - 1, iy), (ix + 1, iy + 1)], fill=self.color)

        # Claws (animated open/close)
        claw_open = math.sin(self.claw_phase) > 0
        # Left claw
        cx_l = ix - 2
        cy_l = iy
        if 0 <= cx_l < WIDTH and 0 <= cy_l < HEIGHT:
            draw_ctx.point((cx_l, cy_l), fill=self.color)
            if claw_open and 0 <= cx_l < WIDTH and 0 <= cy_l - 1 < HEIGHT:
                draw_ctx.point((cx_l, cy_l - 1), fill=self.color)
        # Right claw
        cx_r = ix + 2
        if 0 <= cx_r < WIDTH and 0 <= cy_l < HEIGHT:
            draw_ctx.point((cx_r, cy_l), fill=self.color)
            if claw_open and 0 <= cx_r < WIDTH and 0 <= cy_l - 1 < HEIGHT:
                draw_ctx.point((cx_r, cy_l - 1), fill=self.color)

        # Tiny eyes
        if 0 <= ix - 1 < WIDTH and 0 <= iy - 1 < HEIGHT:
            draw_ctx.point((ix - 1, iy - 1), fill=(255, 255, 255))
        if 0 <= ix + 1 < WIDTH and 0 <= iy - 1 < HEIGHT:
            draw_ctx.point((ix + 1, iy - 1), fill=(255, 255, 255))


class Angelfish:
    """A tall, thin angelfish that moves slowly and gracefully."""

    def __init__(self):
        self.x = random.uniform(10, WIDTH - 10)
        self.y = random.uniform(12, HEIGHT - 18)
        self.direction = random.choice([-1, 1])
        self.speed = random.uniform(0.1, 0.25)  # Very slow
        self.fin_phase = random.uniform(0, math.pi * 2)
        self.drift_phase = random.uniform(0, math.pi * 2)
        # Angelfish are typically striped black/white/yellow
        self.body_color = random.choice([
            (255, 255, 100),   # Yellow angelfish
            (200, 200, 220),   # Silver angelfish
            (255, 180, 50),    # Gold angelfish
        ])
        self.stripe_color = (20, 20, 30)
        self.fin_color = (self.body_color[0] // 2, self.body_color[1] // 2, self.body_color[2] // 2)

    def update(self, tick):
        """Slow, graceful movement."""
        self.fin_phase += 0.15
        self.drift_phase += 0.02

        self.x += self.speed * self.direction
        self.y += math.sin(self.drift_phase) * 0.05

        # Turn around at edges
        if self.x < 6:
            self.direction = 1
        elif self.x > WIDTH - 6:
            self.direction = -1

        # Stay in water
        if self.y < 8:
            self.y = 8
        elif self.y > HEIGHT - 16:
            self.y = HEIGHT - 16

    def draw(self, draw_ctx, tick):
        """Draw angelfish: triangular profile, tall top fin and long bottom fin.

        Angelfish have a round/triangular body that's taller than wide,
        with dramatic dorsal (top) and anal (bottom) fins that make them
        look like a triangle/arrow pointing sideways.
        """
        ix, iy = int(self.x), int(self.y)
        d = self.direction

        # Body (round, 3px wide x 3px tall center)
        for dy in range(-1, 2):
            for dx in range(0, 3):
                px = ix + (dx - 1) * d
                py = iy + dy
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    # Stripe pattern
                    c = self.stripe_color if dx == 1 else self.body_color
                    draw_ctx.point((px, py), fill=c)

        # Tall dorsal fin (extends 3px above body, waves slightly)
        fin_wave = int(math.sin(self.fin_phase) * 0.7)
        for fy in range(1, 4):
            fx = ix + fin_wave
            py = iy - 1 - fy
            if 0 <= fx < WIDTH and 0 <= py < HEIGHT:
                alpha = 1.0 - fy / 4.0
                c = tuple(int(v * alpha) for v in self.body_color)
                draw_ctx.point((fx, py), fill=c)

        # Long anal fin (extends 3px below body)
        for fy in range(1, 4):
            fx = ix - fin_wave
            py = iy + 1 + fy
            if 0 <= fx < WIDTH and 0 <= py < HEIGHT:
                alpha = 1.0 - fy / 4.0
                c = tuple(int(v * alpha) for v in self.body_color)
                draw_ctx.point((fx, py), fill=c)

        # Tail (small, behind body)
        tail_x = ix - d * 2
        if 0 <= tail_x < WIDTH:
            if 0 <= iy - 1 < HEIGHT:
                draw_ctx.point((tail_x, iy - 1), fill=self.fin_color)
            if 0 <= iy + 1 < HEIGHT:
                draw_ctx.point((tail_x, iy + 1), fill=self.fin_color)

        # Eye (at front of body)
        eye_x = ix + d
        if 0 <= eye_x < WIDTH and 0 <= iy < HEIGHT:
            draw_ctx.point((eye_x, iy), fill=(0, 0, 0))


class Flake:
    """A food flake sinking from the surface during a feeding event."""

    def __init__(self, x, y=1.0):
        self.x = float(x)
        self.y = float(y)
        self.vy = random.uniform(0.10, 0.22)
        self.drift_phase = random.uniform(0, math.pi * 2)
        self.color = random.choice(FLAKE_COLORS)
        self.eaten = False

    def update(self):
        """Sink slowly. Returns False when eaten or settled on the sand."""
        if self.eaten:
            return False
        self.y += self.vy
        self.drift_phase += 0.08
        self.x += math.sin(self.drift_phase) * 0.12
        return self.y < HEIGHT - 9  # vanishes when it reaches the sand

    def draw(self, draw_ctx):
        ix, iy = int(self.x), int(self.y)
        if 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
            draw_ctx.point((ix, iy), fill=self.color)


class School:
    """A tight school of tiny minnows that dart around as one."""

    SIZE_MIN, SIZE_MAX = 6, 9

    def __init__(self):
        n = random.randint(self.SIZE_MIN, self.SIZE_MAX)
        cx = random.uniform(16, WIDTH - 16)
        cy = random.uniform(12, HEIGHT - 22)
        self.minnows = [
            [cx + random.uniform(-4, 4), cy + random.uniform(-3, 3)]
            for _ in range(n)
        ]
        angle = random.uniform(0, math.pi * 2)
        self.vx = math.cos(angle) * 0.9
        self.vy = math.sin(angle) * 0.3
        self.color = random.choice([
            (150, 200, 255),   # silver-blue
            (200, 220, 180),   # pale green
            (255, 210, 150),   # sandy gold
        ])
        self.turn_timer = random.randint(FPS * 2, FPS * 6)

    def _centroid(self):
        n = len(self.minnows)
        return (sum(m[0] for m in self.minnows) / n,
                sum(m[1] for m in self.minnows) / n)

    def update(self, flakes=None):
        cx, cy = self._centroid()

        # Steer toward food if any is in range
        target = None
        if flakes:
            best_d2 = FLAKE_SEEK_RADIUS * FLAKE_SEEK_RADIUS
            for flake in flakes:
                if flake.eaten:
                    continue
                d2 = (flake.x - cx) ** 2 + (flake.y - cy) ** 2
                if d2 < best_d2:
                    target, best_d2 = flake, d2
        if target is not None:
            dx, dy = target.x - cx, target.y - cy
            dist = math.hypot(dx, dy) or 1.0
            self.vx += (dx / dist) * 0.12
            self.vy += (dy / dist) * 0.08
        else:
            # Occasional random dart in a new direction
            self.turn_timer -= 1
            if self.turn_timer <= 0:
                angle = random.uniform(0, math.pi * 2)
                self.vx = math.cos(angle) * random.uniform(0.6, 1.1)
                self.vy = math.sin(angle) * random.uniform(0.15, 0.4)
                self.turn_timer = random.randint(FPS * 2, FPS * 6)

        # Clamp speed
        speed = math.hypot(self.vx, self.vy)
        if speed > 1.2:
            self.vx *= 1.2 / speed
            self.vy *= 1.2 / speed

        # Bounce the whole school off walls
        if cx < 8 and self.vx < 0:
            self.vx = abs(self.vx)
        elif cx > WIDTH - 8 and self.vx > 0:
            self.vx = -abs(self.vx)
        if cy < 8 and self.vy < 0:
            self.vy = abs(self.vy)
        elif cy > HEIGHT - 16 and self.vy > 0:
            self.vy = -abs(self.vy)

        for m in self.minnows:
            # Shared velocity + cohesion pull toward centroid + jitter
            m[0] += self.vx + (cx - m[0]) * 0.03 + random.uniform(-0.15, 0.15)
            m[1] += self.vy + (cy - m[1]) * 0.03 + random.uniform(-0.1, 0.1)
            m[1] = max(6.0, min(float(HEIGHT - 12), m[1]))

            # Minnows eat too
            if flakes:
                for flake in flakes:
                    if (not flake.eaten and
                            abs(flake.x - m[0]) <= FLAKE_EAT_RADIUS and
                            abs(flake.y - m[1]) <= FLAKE_EAT_RADIUS):
                        flake.eaten = True

    def draw(self, draw_ctx):
        d = 1 if self.vx >= 0 else -1
        tail = tuple(c // 2 for c in self.color)
        for m in self.minnows:
            ix, iy = int(m[0]), int(m[1])
            if 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
                draw_ctx.point((ix, iy), fill=self.color)
            tx = ix - d
            if 0 <= tx < WIDTH and 0 <= iy < HEIGHT:
                draw_ctx.point((tx, iy), fill=tail)


def _build_rays_image(bg_image):
    """Pre-render the background WITH light rays baked in.

    Per frame the tank blends between the plain background and this one
    (single C-level Image.blend), which makes the rays swell and fade with
    zero per-pixel Python work at draw time.
    """
    rays = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    rdraw = ImageDraw.Draw(rays)
    ray_defs = [(10, 5, 0.55), (30, 7, 0.4), (50, 4, 0.5)]  # (top_x, width, slope)
    for top_x, width, slope in ray_defs:
        for y in range(HEIGHT - 8):
            depth = 1.0 - y / float(HEIGHT - 8)   # fade with depth
            x0 = int(top_x + y * slope)
            for i in range(width):
                x = x0 + i
                if 0 <= x < WIDTH:
                    # Soft edges: dimmer at the sides of the beam
                    edge = 1.0 - abs((i - (width - 1) / 2.0) / (width / 2.0)) * 0.6
                    c = tuple(int(v * depth * edge) for v in RAY_COLOR)
                    rdraw.point((x, y), fill=c)
    return ImageChops.add(bg_image, rays)


def _draw_surface_shimmer(draw, tick):
    """Animated light ripple along the water surface (top two rows)."""
    for x in range(WIDTH):
        v = math.sin(x * 0.45 + tick * 0.18) + math.sin(x * 0.13 - tick * 0.07)
        if v > 1.0:
            draw.point((x, 0), fill=(70, 130, 190))
        elif v > 0.4:
            draw.point((x, 1), fill=(30, 70, 120))


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
    num_fish = random.randint(4, 6)
    fish_list = [Fish() for _ in range(num_fish)]

    # Create angelfish (1-2)
    angelfish_list = [Angelfish() for _ in range(random.randint(1, 2))]

    # Create crabs (1-2 on the sand)
    crab_list = [Crab() for _ in range(random.randint(1, 2))]

    # Create plants
    plants = []
    num_plants = random.randint(4, 7)
    for _ in range(num_plants):
        px = random.randint(3, WIDTH - 3)
        ph = random.randint(5, 12)
        plants.append(Plant(px, ph))

    # Minnow school
    school = School()

    # Bubbles and food flakes
    bubbles = []
    flakes = []
    next_feed_tick = random.randint(FEED_INTERVAL_MIN // 3, FEED_INTERVAL_MAX)

    # Pre-render background (static, only computed once) and a second copy
    # with light rays baked in; per-frame we blend between the two so the
    # rays breathe without any per-pixel work.
    bg_image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_image)
    _draw_background(bg_draw)
    bg_rays = _build_rays_image(bg_image)

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            tick += 1

            # Start with the background, rays breathing via a single blend
            ray_alpha = 0.35 + 0.3 * math.sin(tick * 0.02) + 0.15 * math.sin(tick * 0.047)
            ray_alpha = max(0.0, min(1.0, ray_alpha))
            image = Image.blend(bg_image, bg_rays, ray_alpha)
            draw = ImageDraw.Draw(image)

            # Surface shimmer
            _draw_surface_shimmer(draw, tick)

            # Draw plants (behind fish)
            for plant in plants:
                plant.draw(draw, tick)

            # Feeding events: sprinkle flakes from the surface now and then
            if tick >= next_feed_tick:
                feed_x = random.uniform(10, WIDTH - 10)
                for _ in range(random.randint(6, 10)):
                    flakes.append(Flake(feed_x + random.uniform(-5, 5),
                                        y=random.uniform(0, 3)))
                next_feed_tick = tick + random.randint(FEED_INTERVAL_MIN,
                                                       FEED_INTERVAL_MAX)

            # Update and draw flakes
            flakes = [f for f in flakes if f.update()]
            for flake in flakes:
                flake.draw(draw)

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

            # Update and draw crabs (on sand, drawn before fish)
            for crab in crab_list:
                crab.update(tick)
                crab.draw(draw, tick)

            # Update and draw the minnow school (behind the big fish)
            school.update(flakes)
            school.draw(draw)

            # Update and draw fish
            for fish in fish_list:
                fish.update(tick, fish_list, flakes)
            for fish in fish_list:
                fish.draw(draw, tick)

            # Fish occasionally blow a bubble from the mouth
            if fish_list and random.random() < 0.02:
                fish = random.choice(fish_list)
                nose_x = fish.x + fish.direction * (fish.size // 2 + 1)
                bubbles.append(Bubble(x=nose_x, y=fish.y - 1))

            # Update and draw angelfish (in front of regular fish)
            for angel in angelfish_list:
                angel.update(tick)
                angel.draw(draw, tick)

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
