#!/usr/bin/env python3
"""
Boot screen animation for LED Matrix Project.

Displays a startup animation when the service first launches.
Shown once at boot before the main feature loop begins.

Design (~4 seconds total):
  - Phase 1: RGB panel self-test -- red/green/blue light bands sweep
    across the matrix like a hardware check, with trailing sparkle
  - Phase 2: "LED" letters drop in one by one with overshoot;
    "MATRIX" types itself out underneath with a blinking cursor
  - Phase 3: loading bar with a moving shine + the running version
    (auto-bumping, from src.version) shown above it
"""

import math
import random
import time
import threading
import logging
from PIL import Image, ImageDraw
from src.display._fonts import FONT_5X7, _draw_char, _draw_text, _text_width
from src.version import get_version

logger = logging.getLogger(__name__)

SIZE = 64
CENTER = SIZE // 2
FPS = 30
FRAME_DUR = 1.0 / FPS

# Color palette
BG = (0, 0, 0)
TEXT_COLOR_LED = (255, 255, 255)   # White for "LED"
LED_GLOW = (0, 90, 140)            # Drop-shadow glow behind "LED"
TEXT_COLOR_MATRIX = (0, 180, 255)  # Cyan for "MATRIX"
BAR_BG = (20, 20, 30)              # Dark loading bar background
BAR_FG = (0, 200, 100)             # Green loading bar fill
BAR_SHINE = (180, 255, 210)        # Moving highlight on the bar
VERSION_COLOR = (150, 150, 170)    # Version line
DOT_COLOR = (80, 80, 120)          # Dim corner dots
SWEEP_COLORS = [(255, 40, 40), (40, 255, 40), (60, 60, 255)]  # R, G, B bands

# Duration of each phase in seconds
PHASE_SWEEP = 1.1       # RGB self-test sweep
PHASE_TEXT = 1.6        # Letter drop + typewriter
PHASE_LOADING = 1.3     # Loading bar + version
TOTAL_DURATION = PHASE_SWEEP + PHASE_TEXT + PHASE_LOADING

# Layout
LED_TEXT = "LED"
LED_SCALE = 3
LED_Y = 12
MATRIX_TEXT = "MATRIX"
MATRIX_Y = 38
BAR_Y = 56
BAR_H = 3
BAR_MARGIN = 8
VERSION_Y = 47


def _blend_color(color, alpha):
    """Apply alpha (0.0-1.0) to an RGB color tuple against black background."""
    return tuple(int(c * alpha) for c in color)


def _ease_out_back(t):
    """Ease-out with a small overshoot (letters land with a bounce)."""
    c1 = 1.70158
    c3 = c1 + 1
    t -= 1
    return 1 + c3 * t * t * t + c1 * t * t


def _version_text():
    """Short version line for the boot screen, e.g. 'V1.1.18'."""
    ver = get_version()
    if len(ver) > 9:          # bare hash fallback etc.
        ver = ver[:9]
    return "V" + ver.upper()


def _draw_sweep_frame(draw, t, max_t, rng):
    """Phase 1: R/G/B light bands sweep across like a panel self-test."""
    progress = t / max_t  # 0.0 to 1.0

    band_w = 10
    travel = SIZE + band_w * 2
    for i, color in enumerate(SWEEP_COLORS):
        # Staggered starts; each band crosses the full panel
        band_progress = progress * 1.6 - i * 0.22
        if band_progress <= 0 or band_progress > 1.0:
            continue
        head_x = int(band_progress * travel) - band_w
        for x_off in range(band_w):
            x = head_x - x_off
            if 0 <= x < SIZE:
                fade = 1.0 - (x_off / band_w)
                draw.line([(x, 0), (x, SIZE - 1)],
                          fill=_blend_color(color, fade * fade))

    # Sparkle: random pixels twinkle in the swept area
    sparkle_count = 14
    swept_limit = min(SIZE, int(progress * 1.6 * travel))
    if swept_limit > 4:
        for _ in range(sparkle_count):
            px = rng.randrange(0, swept_limit)
            py = rng.randrange(0, SIZE)
            if px < SIZE:
                draw.point((px, py), fill=_blend_color((255, 255, 255),
                                                       rng.uniform(0.2, 0.8)))

    # Fade the whole show out at the end of the phase
    # (handled by the bands leaving the panel; sparkles thin naturally)


def _draw_led_letters(draw, progress):
    """Draw 'LED' with per-letter staggered drop-in and glow shadow."""
    led_w = _text_width(LED_TEXT, scale=LED_SCALE, spacing=2)
    led_x = (SIZE - led_w) // 2
    char_w = 5 * LED_SCALE + 2  # glyph + spacing

    for i, ch in enumerate(LED_TEXT):
        # Each letter animates in its own staggered window
        t = max(0.0, min(1.0, progress * 3.0 - i * 0.55))
        if t <= 0:
            continue
        eased = _ease_out_back(t)
        y = int(LED_Y - (1.0 - eased) * 20)
        alpha = min(1.0, t * 2.0)
        x = led_x + i * char_w
        # Glow shadow (offset down-right)
        _draw_char(draw, ch, x + 1, y + 1, _blend_color(LED_GLOW, alpha),
                   scale=LED_SCALE)
        _draw_char(draw, ch, x, y, _blend_color(TEXT_COLOR_LED, alpha),
                   scale=LED_SCALE)


def _draw_matrix_typewriter(draw, progress, tick):
    """Draw 'MATRIX' typing itself out with a blinking cursor."""
    # Typing happens in the second half of the text phase
    type_progress = max(0.0, (progress - 0.45) / 0.55)
    shown = min(len(MATRIX_TEXT), int(type_progress * (len(MATRIX_TEXT) + 1)))
    if shown <= 0 and type_progress <= 0:
        return
    full_w = _text_width(MATRIX_TEXT, scale=1, spacing=1)
    x = (SIZE - full_w) // 2
    text = MATRIX_TEXT[:shown]
    if text:
        _draw_text(draw, text, x, MATRIX_Y, TEXT_COLOR_MATRIX,
                   scale=1, spacing=1)
    # Blinking cursor after the last typed char (hidden once complete)
    if shown < len(MATRIX_TEXT) and (tick // 4) % 2 == 0:
        cx = x + _text_width(text, scale=1, spacing=1) + (1 if text else 0)
        draw.rectangle([cx, MATRIX_Y, cx + 2, MATRIX_Y + 6],
                       fill=TEXT_COLOR_MATRIX)


def _draw_text_frame(draw, t, max_t, tick):
    """Phase 2: letter drop-in + typewriter."""
    progress = t / max_t
    _draw_led_letters(draw, progress)
    _draw_matrix_typewriter(draw, progress, tick)

    # Corner dots fade in late
    corner_alpha = max(0.0, min(1.0, (progress - 0.7) * 3.0))
    if corner_alpha > 0:
        dc = _blend_color(DOT_COLOR, corner_alpha)
        for cx, cy in [(2, 2), (SIZE - 3, 2), (2, SIZE - 3), (SIZE - 3, SIZE - 3)]:
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                draw.point((cx + dx, cy + dy), fill=dc)


def _draw_loading_frame(draw, t, max_t, tick):
    """Phase 3: held text + loading bar with shine + version line."""
    progress = t / max_t

    # Keep the finished text visible
    _draw_text_frame(draw, max_t, max_t, tick=1)  # tick=1: cursor hidden

    # Version line (auto-bumping, e.g. V1.1.18)
    ver = _version_text()
    vw = _text_width(ver, scale=1, spacing=1)
    _draw_text(draw, ver, (SIZE - vw) // 2, VERSION_Y,
               VERSION_COLOR, scale=1, spacing=1)

    # Loading bar
    bar_x0 = BAR_MARGIN
    bar_x1 = SIZE - BAR_MARGIN - 1
    bar_w = bar_x1 - bar_x0
    draw.rectangle([bar_x0, BAR_Y, bar_x1, BAR_Y + BAR_H], fill=BAR_BG)

    eased = progress * progress * (3 - 2 * progress)  # smoothstep
    fill_w = int(bar_w * eased)
    if fill_w > 0:
        for x_off in range(fill_w):
            frac = x_off / max(bar_w, 1)
            r = int(BAR_FG[0] + (50 * frac))
            g = int(BAR_FG[1] + (55 * frac))
            b = int(BAR_FG[2] - (50 * frac))
            col = (min(r, 255), min(g, 255), max(b, 0))
            draw.line([(bar_x0 + x_off, BAR_Y + 1),
                       (bar_x0 + x_off, BAR_Y + BAR_H - 1)], fill=col)
        # Moving shine sweeps the filled part
        shine_x = bar_x0 + int((tick * 2) % max(fill_w, 1))
        if shine_x <= bar_x0 + fill_w:
            draw.line([(shine_x, BAR_Y + 1), (shine_x, BAR_Y + BAR_H - 1)],
                      fill=BAR_SHINE)


def show(matrix, duration=None):
    """Display the boot screen animation on the LED matrix.

    Args:
        matrix: RGBMatrix instance (or simulator).
        duration: Override total duration in seconds. None uses default (~4s).
    """
    if duration is None:
        duration = TOTAL_DURATION

    logger.info("Showing boot screen (%.1fs)", duration)
    start = time.time()
    rng = random.Random(1234)  # deterministic sparkle
    tick = 0

    # Scale phase durations proportionally if total duration differs
    scale = duration / TOTAL_DURATION
    p_sweep = PHASE_SWEEP * scale
    p_text = PHASE_TEXT * scale
    p_loading = PHASE_LOADING * scale

    try:
        while True:
            frame_start = time.time()
            elapsed = frame_start - start

            if elapsed >= duration:
                break

            img = Image.new("RGB", (SIZE, SIZE), BG)
            draw = ImageDraw.Draw(img)
            tick += 1

            if elapsed < p_sweep:
                _draw_sweep_frame(draw, elapsed, p_sweep, rng)
            elif elapsed < p_sweep + p_text:
                _draw_text_frame(draw, elapsed - p_sweep, p_text, tick)
            else:
                _draw_loading_frame(draw, elapsed - p_sweep - p_text,
                                    p_loading, tick)

            matrix.SetImage(img)

            # Frame rate limiting
            frame_time = time.time() - frame_start
            sleep_time = FRAME_DUR - frame_time
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Boot screen error: %s", e, exc_info=True)
    finally:
        # Clear before handing off to main loop
        try:
            matrix.Clear()
        except Exception:
            pass

    logger.info("Boot screen complete")


def show_loading_ring(matrix, status_func, done_event):
    """Display an animated loading ring with status text.

    Runs until done_event is set. Calls status_func() each frame to get
    the current (line1, line2) text to display below the ring.

    Args:
        matrix: RGBMatrix instance.
        status_func: Callable returning (str, str) tuple for status text.
        done_event: threading.Event -- animation stops when set.
    """
    ring_radius = 14
    ring_cx, ring_cy = CENTER, 18
    arc_length = 1.8  # radians of visible arc (~100 degrees)
    spin_speed = 3.0  # radians per second

    frame_count = 0
    try:
        while not done_event.is_set():
            frame_start = time.time()
            angle = (time.time() * spin_speed) % (2 * math.pi)

            img = Image.new("RGB", (SIZE, SIZE), BG)
            draw = ImageDraw.Draw(img)

            # Draw ring track (dim)
            track_color = (20, 20, 40)
            for i in range(36):
                a = (2 * math.pi / 36) * i
                px = int(ring_cx + math.cos(a) * ring_radius)
                py = int(ring_cy + math.sin(a) * ring_radius)
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    draw.point((px, py), fill=track_color)

            # Draw bright arc (spinning)
            arc_steps = 16
            for i in range(arc_steps):
                frac = i / arc_steps
                a = angle + frac * arc_length
                brightness = 1.0 - (frac * 0.7)  # head is brightest
                px = int(ring_cx + math.cos(a) * ring_radius)
                py = int(ring_cy + math.sin(a) * ring_radius)
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    c = _blend_color((80, 180, 255), brightness)
                    draw.point((px, py), fill=c)
                    # Thicken the arc slightly
                    for dx, dy in [(1, 0), (0, 1)]:
                        nx, ny = px + dx, py + dy
                        if 0 <= nx < SIZE and 0 <= ny < SIZE:
                            draw.point((nx, ny), fill=_blend_color((40, 90, 128), brightness * 0.5))

            # Status text
            try:
                line1, line2 = status_func()
            except Exception:
                line1, line2 = "LOADING", ""

            w1 = _text_width(line1, scale=1, spacing=1)
            _draw_text(draw, line1, (SIZE - w1) // 2, 38,
                       (100, 180, 255), scale=1, spacing=1)

            if line2:
                w2 = _text_width(line2, scale=1, spacing=1)
                _draw_text(draw, line2, (SIZE - w2) // 2, 50,
                           (140, 140, 160), scale=1, spacing=1)

            matrix.SetImage(img)
            frame_count += 1

            elapsed = time.time() - frame_start
            sleep_time = FRAME_DUR - elapsed
            if sleep_time > 0:
                # Use event.wait() instead of time.sleep() so we can
                # exit immediately when done_event is set
                done_event.wait(sleep_time)

    except Exception as e:
        logger.error("Loading ring error: %s", e)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
