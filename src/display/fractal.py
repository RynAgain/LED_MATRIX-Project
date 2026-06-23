#!/usr/bin/env python3
"""Pixel fractal unfolding demo for 64x64 LED matrix.

Renders fractals that progressively "unfold" on screen, revealing more detail
with each frame. Cycles through multiple fractal types:

1. **Sierpinski Triangle** – recursive subdivision that fills in pixel by pixel.
2. **Mandelbrot Zoom** – progressive zoom into the set with iteration-depth color.
3. **Dragon Curve** – L-system fractal drawn stroke by stroke.

Each fractal builds itself visually over time, creating an organic "unfolding"
effect before transitioning to the next.
"""

import time
import math
import logging
from PIL import Image
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30  # 30 FPS


# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------

def _hue_to_rgb(hue):
    """Convert a hue (0.0-1.0) to an RGB tuple using HSV with full saturation."""
    h = (hue % 1.0) * 6.0
    c = 255
    x = int(c * (1 - abs(h % 2 - 1)))
    c = int(c)
    if h < 1:
        return (c, x, 0)
    elif h < 2:
        return (x, c, 0)
    elif h < 3:
        return (0, c, x)
    elif h < 4:
        return (0, x, c)
    elif h < 5:
        return (x, 0, c)
    else:
        return (c, 0, x)


def _depth_color(depth, max_depth, hue_offset=0.0):
    """Map a recursion/iteration depth to a vibrant color."""
    if max_depth == 0:
        t = 0.0
    else:
        t = depth / max_depth
    hue = (t * 0.7 + hue_offset) % 1.0
    return _hue_to_rgb(hue)


# ---------------------------------------------------------------------------
# Fractal 1: Sierpinski Triangle (pixel-by-pixel unfold)
# ---------------------------------------------------------------------------

def _sierpinski_points(max_points):
    """Generate Sierpinski triangle points using the chaos game algorithm.

    Yields (x, y) coordinates one at a time for progressive reveal.
    """
    import random
    # Triangle vertices scaled to 64x64
    vertices = [(32, 2), (2, 61), (61, 61)]
    x, y = 32.0, 32.0

    for _ in range(max_points):
        v = random.choice(vertices)
        x = (x + v[0]) / 2.0
        y = (y + v[1]) / 2.0
        yield (int(x), int(y))


def _run_sierpinski(matrix, duration=15):
    """Sierpinski triangle unfolding via chaos game - points appear progressively."""
    start = time.time()
    image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    pixels = image.load()

    # Pre-generate points for smooth animation
    points_per_frame = 40
    total_points = 0
    hue_offset = 0.0

    point_gen = _sierpinski_points(points_per_frame * int(duration / FRAME_INTERVAL))

    while time.time() - start < duration:
        if should_stop():
            return False
        frame_start = time.time()

        # Add new points each frame
        for _ in range(points_per_frame):
            try:
                px, py = next(point_gen)
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    color = _depth_color(total_points % 200, 200, hue_offset)
                    pixels[px, py] = color
                    total_points += 1
            except StopIteration:
                break

        hue_offset += 0.001
        matrix.SetImage(image)

        elapsed = time.time() - frame_start
        sleep_time = FRAME_INTERVAL - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    return True


# ---------------------------------------------------------------------------
# Fractal 2: Mandelbrot zoom unfold
# ---------------------------------------------------------------------------

def _mandelbrot_iter(cx, cy, max_iter):
    """Compute Mandelbrot escape iteration for a point."""
    zx, zy = 0.0, 0.0
    for i in range(max_iter):
        if zx * zx + zy * zy > 4.0:
            return i
        zx, zy = zx * zx - zy * zy + cx, 2 * zx * zy + cy
    return max_iter


def _run_mandelbrot(matrix, duration=20):
    """Mandelbrot set that progressively increases iteration depth and zooms in.

    The fractal "unfolds" as more iterations reveal finer boundary detail,
    and a slow zoom pulls the viewer into an interesting region.
    """
    start = time.time()

    # Zoom target: Seahorse Valley
    target_cx, target_cy = -0.745, 0.186

    # Start wide, zoom in over time
    initial_scale = 3.0
    final_scale = 0.005

    frame_count = 0
    max_frames = int(duration / FRAME_INTERVAL)

    while time.time() - start < duration:
        if should_stop():
            return False
        frame_start = time.time()

        # Progress 0..1 over the duration
        t = min(1.0, (time.time() - start) / duration)

        # Exponential zoom
        scale = initial_scale * math.exp(math.log(final_scale / initial_scale) * t)

        # Increase max iterations as we zoom (reveals more detail)
        max_iter = int(20 + t * 80)

        # Center interpolates toward target
        cx = -0.5 + (target_cx - (-0.5)) * t
        cy = 0.0 + (target_cy - 0.0) * t

        image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        pixels = image.load()

        for py in range(HEIGHT):
            for px in range(WIDTH):
                # Map pixel to complex plane
                real = cx + (px - WIDTH / 2) * scale / WIDTH
                imag = cy + (py - HEIGHT / 2) * scale / HEIGHT

                iters = _mandelbrot_iter(real, imag, max_iter)

                if iters == max_iter:
                    pixels[px, py] = (0, 0, 0)
                else:
                    # Smooth coloring
                    color = _depth_color(iters, max_iter, hue_offset=t * 0.3)
                    pixels[px, py] = color

        matrix.SetImage(image)
        frame_count += 1

        elapsed = time.time() - frame_start
        sleep_time = FRAME_INTERVAL - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    return True


# ---------------------------------------------------------------------------
# Fractal 3: Dragon Curve (L-system stroke-by-stroke unfold)
# ---------------------------------------------------------------------------

def _dragon_curve_points(iterations):
    """Generate dragon curve points using iterative folding.

    Returns a list of (x, y) points representing the curve path.
    """
    # Build direction sequence
    turns = [1]  # 1 = right, 0 = left
    for _ in range(iterations - 1):
        turns = turns + [1] + [1 - t for t in reversed(turns)]

    # Walk the path
    dx = [1, 0, -1, 0]  # East, South, West, North
    dy = [0, 1, 0, -1]
    direction = 0
    x, y = 0, 0
    points = [(x, y)]

    for turn in turns:
        if turn == 1:
            direction = (direction + 1) % 4
        else:
            direction = (direction - 1) % 4
        x += dx[direction]
        y += dy[direction]
        points.append((x, y))

    return points


def _run_dragon_curve(matrix, duration=15):
    """Dragon curve that draws itself stroke by stroke."""
    start = time.time()

    # Generate curve with enough iterations to fill the screen
    iterations = 12  # 2^12 = 4096 segments
    points = _dragon_curve_points(iterations)

    # Scale and center the points to fit 64x64
    if not points:
        return True

    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)

    range_x = max_x - min_x or 1
    range_y = max_y - min_y or 1

    # Scale to fit with 2px margin
    scale = min(60.0 / range_x, 60.0 / range_y)
    offset_x = (WIDTH - range_x * scale) / 2 - min_x * scale
    offset_y = (HEIGHT - range_y * scale) / 2 - min_y * scale

    scaled_points = []
    for px, py in points:
        sx = int(px * scale + offset_x)
        sy = int(py * scale + offset_y)
        sx = max(0, min(WIDTH - 1, sx))
        sy = max(0, min(HEIGHT - 1, sy))
        scaled_points.append((sx, sy))

    image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    pixels = image.load()

    total_segments = len(scaled_points) - 1
    segments_per_frame = max(1, total_segments // int(duration / FRAME_INTERVAL))
    current_segment = 0

    while time.time() - start < duration:
        if should_stop():
            return False
        frame_start = time.time()

        # Draw new segments this frame
        end_segment = min(current_segment + segments_per_frame, total_segments)
        for i in range(current_segment, end_segment):
            x0, y0 = scaled_points[i]
            x1, y1 = scaled_points[i + 1]

            # Color based on progress through curve
            color = _depth_color(i, total_segments, hue_offset=0.6)

            # Draw pixel at endpoint (and interpolate for longer segments)
            pixels[x1, y1] = color
            # Simple line between consecutive points
            if abs(x1 - x0) <= 1 and abs(y1 - y0) <= 1:
                pixels[x1, y1] = color
            else:
                # Bresenham-ish for longer segments
                steps = max(abs(x1 - x0), abs(y1 - y0))
                for s in range(steps + 1):
                    t = s / max(steps, 1)
                    lx = int(x0 + (x1 - x0) * t)
                    ly = int(y0 + (y1 - y0) * t)
                    if 0 <= lx < WIDTH and 0 <= ly < HEIGHT:
                        pixels[lx, ly] = color

        current_segment = end_segment
        matrix.SetImage(image)

        # If we've drawn everything, hold the final image
        if current_segment >= total_segments:
            # Slowly cycle hue on the completed fractal
            while time.time() - start < duration:
                if should_stop():
                    return False
                time.sleep(FRAME_INTERVAL)
            break

        elapsed = time.time() - frame_start
        sleep_time = FRAME_INTERVAL - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    return True


# ---------------------------------------------------------------------------
# Fractal 4: Recursive square subdivision (Sierpinski carpet unfold)
# ---------------------------------------------------------------------------

def _run_carpet(matrix, duration=15):
    """Sierpinski carpet that unfolds level by level with animation.

    Each recursion level subdivides existing squares, filling in the pattern
    progressively from level 0 up to level 4.
    """
    start = time.time()
    max_level = 4
    time_per_level = duration / (max_level + 1)

    image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    pixels = image.load()

    def _draw_carpet_level(level, x, y, size, current_time):
        """Recursively draw one level of the carpet with fade-in."""
        if level < 0 or size < 1:
            return
        if should_stop():
            return

        # The center square of the 3x3 grid is "cut out" (drawn bright)
        third = size // 3
        if third < 1:
            return

        # Calculate fade based on when this level should appear
        level_start = start + level * time_per_level
        fade = min(1.0, max(0.0, (current_time - level_start) / (time_per_level * 0.7)))

        if fade > 0:
            color = _depth_color(level, max_level, hue_offset=0.15 * level)
            r, g, b = color
            r = int(r * fade)
            g = int(g * fade)
            b = int(b * fade)

            # Fill center square
            for py in range(y + third, min(y + 2 * third, HEIGHT)):
                for px in range(x + third, min(x + 2 * third, WIDTH)):
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        pixels[px, py] = (r, g, b)

        # Recurse into the 8 surrounding sub-squares
        if level < max_level:
            for row in range(3):
                for col in range(3):
                    if row == 1 and col == 1:
                        continue  # Skip center (it's the "hole")
                    _draw_carpet_level(
                        level + 1,
                        x + col * third,
                        y + row * third,
                        third,
                        current_time
                    )

    while time.time() - start < duration:
        if should_stop():
            return False
        frame_start = time.time()

        # Clear and redraw with current time for fade effects
        image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        pixels = image.load()
        _draw_carpet_level(0, 0, 0, 64, time.time())

        matrix.SetImage(image)

        elapsed = time.time() - frame_start
        sleep_time = FRAME_INTERVAL - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(matrix, duration=60):
    """Run the pixel fractal unfolding demo.

    Cycles through multiple fractal types, each building itself on screen
    progressively for a mesmerizing unfolding effect.
    """
    fractals = [
        ("Sierpinski Triangle", _run_sierpinski),
        ("Mandelbrot Zoom", _run_mandelbrot),
        ("Dragon Curve", _run_dragon_curve),
        ("Sierpinski Carpet", _run_carpet),
    ]

    # Divide time among fractals
    time_per_fractal = duration / len(fractals)
    start_time = time.time()

    try:
        for name, fractal_fn in fractals:
            if should_stop():
                break
            if time.time() - start_time >= duration:
                break

            logger.debug("Fractal unfold: starting %s", name)

            # Brief fade-to-black transition
            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
            matrix.SetImage(image)
            time.sleep(0.3)

            if should_stop():
                break

            remaining = duration - (time.time() - start_time)
            frac_duration = min(time_per_fractal, remaining)
            if frac_duration <= 0:
                break

            fractal_fn(matrix, duration=frac_duration)

    except Exception as e:
        logger.error("Error in fractal unfold: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
