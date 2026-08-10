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
import random
import logging
from PIL import Image
from src.display._shared import should_stop, interruptible_sleep
from src.display._utils import _hsv_to_rgb

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30  # 30 FPS


# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------

def _depth_color(depth, max_depth, hue_offset=0.0):
    """Map a recursion/iteration depth to a vibrant color."""
    if max_depth == 0:
        t = 0.0
    else:
        t = depth / max_depth
    hue = (t * 0.7 + hue_offset) % 1.0
    return _hsv_to_rgb(hue, 1.0, 1.0)


# ---------------------------------------------------------------------------
# Fractal 1: Sierpinski Triangle (pixel-by-pixel unfold)
# ---------------------------------------------------------------------------

# Chaos-game iterates converge onto the attractor exponentially; the first
# handful start from an arbitrary seed point and land off the triangle.
_CHAOS_BURN_IN = 10


def _sierpinski_points(max_points=None):
    """Generate Sierpinski triangle points using the chaos game algorithm.

    Yields (x, y) coordinates one at a time for progressive reveal. With
    ``max_points=None`` the generator is unbounded, so the reveal fills in over
    the wall-clock duration regardless of the frame rate actually achieved --
    pre-sizing it to an assumed 30fps left the triangle half-drawn on hardware
    that renders slower.
    """
    # Triangle vertices scaled to 64x64
    vertices = [(32, 2), (2, 61), (61, 61)]
    x, y = 32.0, 32.0

    for _ in range(_CHAOS_BURN_IN):
        v = random.choice(vertices)
        x = (x + v[0]) / 2.0
        y = (y + v[1]) / 2.0

    emitted = 0
    while max_points is None or emitted < max_points:
        v = random.choice(vertices)
        x = (x + v[0]) / 2.0
        y = (y + v[1]) / 2.0
        emitted += 1
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

    point_gen = _sierpinski_points()  # unbounded: reveal is paced by wall clock

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


def _mandelbrot_view(t):
    """Camera for progress ``t`` in 0..1: (scale, cx, cy, max_iter).

    The centre sits ON the zoom target for the whole flight. An earlier
    version interpolated the centre from (-0.5, 0) toward the target while
    the scale was already zooming exponentially; the viewport spent most of
    the segment over set interior where nothing escapes within the 80
    iteration cap, so the panel rendered fully black from roughly t=0.15 to
    t=0.88. Zooming straight at a boundary point keeps escaping pixels in
    frame at every depth (measured 20-100%% lit along the whole trajectory).
    """
    target_cx, target_cy = -0.7436439, 0.1318259
    initial_scale = 3.5
    final_scale = 0.0002

    eased_t = t * (2 - t)  # Ease-out so we slow down as we get deeper
    scale = initial_scale * math.exp(
        math.log(final_scale / initial_scale) * eased_t)
    zoom_factor = initial_scale / scale
    max_iter = int(30 + math.log2(max(1, zoom_factor)) * 25)
    max_iter = min(max_iter, 80)  # 64x64 needs no more; 300 = ~1fps on Pi
    return scale, target_cx, target_cy, max_iter


def _run_mandelbrot(matrix, duration=20):
    """Mandelbrot set that progressively increases iteration depth and zooms in.

    The fractal "unfolds" as more iterations reveal finer boundary detail,
    and a slow zoom pulls the viewer into an interesting boundary region.
    Stays on the edge of the set where detail is infinite.
    """
    start = time.time()

    while time.time() - start < duration:
        if should_stop():
            return False
        frame_start = time.time()

        # Progress 0..1 over the duration; the camera maths lives in
        # _mandelbrot_view so the no-blackout property is testable.
        t = min(1.0, (time.time() - start) / duration)
        scale, cx, cy, max_iter = _mandelbrot_view(t)

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
                    # Smooth coloring with shifted palette as we zoom
                    color = _depth_color(iters, max_iter, hue_offset=t * 0.5)
                    pixels[px, py] = color

        matrix.SetImage(image)

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

    # 11 iterations (2048 points) has a 63x52 bounding box, which lands on the
    # panel at scale 1.0 -- i.e. lattice-aligned, no collapsing. 12 iterations
    # is 95 wide, so it has to be squashed to 0.63 and two thirds of the points
    # pile onto pixels already drawn: twice the work for less visible detail.
    iterations = 11
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

    # Fit within the panel leaving a 1px margin (uniform scale, aspect kept).
    available = float(WIDTH - 1)
    scale = min(available / range_x, available / range_y)
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
    # run() can hand us a duration shorter than a single frame interval; int()
    # then floors to 0 and the division below raises ZeroDivisionError.
    expected_frames = max(1, int(duration / FRAME_INTERVAL))
    segments_per_frame = max(1, total_segments // expected_frames)
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

            # Adjacent points are a single pixel; anything further apart (only
            # possible when the curve is upscaled) needs interpolating.
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
            while time.time() - start < duration:
                if should_stop():
                    return False
                matrix.SetImage(image)  # keep pushing frames for watchdog
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

# A 64px panel supports exactly three carpet levels: successive thirds are
# 64 -> 21.3 -> 7.1 -> 2.4, and below ~3px there is no room left to carve out a
# centre square. max_level was 4, so levels 3 and 4 never drew anything while
# still claiming two fifths of the segment's time budget -- the deepest visible
# level finished 54% of the way in and the remaining 46% was a frozen image.
_CARPET_MAX_LEVEL = 2


def _run_carpet(matrix, duration=15):
    """Sierpinski carpet that unfolds level by level with animation.

    Each recursion level subdivides existing squares, filling in the pattern
    progressively from level 0 up to :data:`_CARPET_MAX_LEVEL`.
    """
    start = time.time()
    max_level = _CARPET_MAX_LEVEL
    time_per_level = duration / (max_level + 1)

    image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    pixels = image.load()

    def _draw_carpet_level(level, x, y, size, current_time):
        """Recursively draw one level of the carpet with fade-in.

        ``x``, ``y`` and ``size`` are floats: keeping sub-square boundaries
        exact and only rounding when painting means the three columns absorb
        the remainder (21/21/22 px for a 64px parent) instead of integer
        division truncating 64 to 63 and leaving a dead edge column.
        """
        if level < 0:
            return
        if should_stop():
            return

        # The center square of the 3x3 grid is "cut out" (drawn bright)
        third = size / 3.0
        if third < 1.0:
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
            px0 = max(0, int(round(x + third)))
            px1 = min(WIDTH, int(round(x + 2 * third)))
            py0 = max(0, int(round(y + third)))
            py1 = min(HEIGHT, int(round(y + 2 * third)))
            for py in range(py0, py1):
                for px in range(px0, px1):
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
        _draw_carpet_level(0, 0.0, 0.0, float(WIDTH), time.time())

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
            interruptible_sleep(0.3)

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
