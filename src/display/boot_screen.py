#!/usr/bin/env python3
"""
Boot screen animation for LED Matrix Project.

Displays a startup animation when the service first launches.
Shown once at boot before the main feature loop begins.

Design:
  - Expanding pixel ring burst from center
  - "LED" text fades in large, then "MATRIX" below
  - Loading bar fills across the bottom
  - Total duration: ~4 seconds
"""

import math
import time
import logging
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

SIZE = 64
CENTER = SIZE // 2
FPS = 30
FRAME_DUR = 1.0 / FPS

# Color palette
BG = (0, 0, 0)
RING_COLOR = (0, 120, 255)       # Blue expanding ring
TEXT_COLOR_LED = (255, 255, 255)  # White for "LED"
TEXT_COLOR_MATRIX = (0, 180, 255) # Cyan for "MATRIX"
BAR_BG = (20, 20, 30)            # Dark loading bar background
BAR_FG = (0, 200, 100)           # Green loading bar fill
DOT_COLOR = (80, 80, 120)        # Dim corner dots

# Duration of each phase in seconds
PHASE_RING = 1.0       # Expanding ring burst
PHASE_TEXT = 1.5        # Text fade-in
PHASE_LOADING = 1.5     # Loading bar
TOTAL_DURATION = PHASE_RING + PHASE_TEXT + PHASE_LOADING

# ---- Compact 5x7 font for boot text ----
# Each character is 5 columns wide, 7 rows tall
# Stored as list of 7 ints, each int's lower 5 bits = pixel columns
FONT_5X7 = {
    'L': [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    'E': [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    'D': [0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C],
    'M': [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    'A': [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    'T': [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    'R': [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    'I': [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    'X': [0x11, 0x0A, 0x04, 0x04, 0x04, 0x0A, 0x11],
    'O': [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    'N': [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    'G': [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0E],
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04],
}


def _draw_char(draw, char, x, y, color, scale=1):
    """Draw a single character from the 5x7 font.

    Args:
        draw: PIL ImageDraw instance.
        char: Single character to render.
        x, y: Top-left position.
        color: RGB tuple.
        scale: Pixel scale factor (1 = tiny, 2 = medium).
    """
    glyph = FONT_5X7.get(char.upper(), FONT_5X7.get(' '))
    for row_idx, row_bits in enumerate(glyph):
        for col in range(5):
            if row_bits & (0x10 >> col):
                px = x + col * scale
                py = y + row_idx * scale
                if scale == 1:
                    draw.point((px, py), fill=color)
                else:
                    draw.rectangle(
                        [px, py, px + scale - 1, py + scale - 1],
                        fill=color
                    )


def _draw_text(draw, text, x, y, color, scale=1, spacing=1):
    """Draw a string of text using the 5x7 font.

    Args:
        draw: PIL ImageDraw instance.
        text: String to render.
        x, y: Top-left position of the first character.
        color: RGB tuple.
        scale: Pixel scale factor.
        spacing: Pixels between characters.

    Returns:
        Total width of the rendered text in pixels.
    """
    char_w = 5 * scale + spacing
    for i, ch in enumerate(text):
        _draw_char(draw, ch, x + i * char_w, y, color, scale)
    return len(text) * char_w - spacing


def _text_width(text, scale=1, spacing=1):
    """Calculate the pixel width of a text string."""
    char_w = 5 * scale + spacing
    return len(text) * char_w - spacing


def _blend_color(color, alpha):
    """Apply alpha (0.0-1.0) to an RGB color tuple against black background."""
    return tuple(int(c * alpha) for c in color)


def _draw_ring_frame(draw, t, max_t):
    """Draw expanding ring burst animation.

    Multiple rings expand outward from center with fading trails.
    """
    progress = t / max_t  # 0.0 to 1.0

    # Draw 3 staggered rings
    for ring_idx in range(3):
        ring_delay = ring_idx * 0.2
        ring_progress = max(0.0, (progress - ring_delay) / (1.0 - ring_delay))
        if ring_progress <= 0:
            continue

        radius = ring_progress * (SIZE * 0.7)
        alpha = max(0.0, 1.0 - ring_progress * 1.2)
        thickness = max(1, int(3 * (1.0 - ring_progress)))

        color = _blend_color(RING_COLOR, alpha)
        if color == (0, 0, 0):
            continue

        bbox = [
            CENTER - radius, CENTER - radius,
            CENTER + radius, CENTER + radius
        ]
        draw.ellipse(bbox, outline=color, width=thickness)

    # Central bright dot that fades out
    dot_alpha = max(0.0, 1.0 - progress * 2)
    if dot_alpha > 0:
        dot_color = _blend_color((255, 255, 255), dot_alpha)
        dot_r = max(1, int(3 * (1.0 - progress)))
        draw.ellipse(
            [CENTER - dot_r, CENTER - dot_r,
             CENTER + dot_r, CENTER + dot_r],
            fill=dot_color
        )

    # Particle sparks radiating outward
    num_particles = 12
    for i in range(num_particles):
        angle = (2 * math.pi / num_particles) * i
        particle_progress = max(0.0, progress - 0.1)
        dist = particle_progress * SIZE * 0.5
        px = int(CENTER + math.cos(angle) * dist)
        py = int(CENTER + math.sin(angle) * dist)
        p_alpha = max(0.0, 1.0 - particle_progress * 1.5)
        if 0 <= px < SIZE and 0 <= py < SIZE and p_alpha > 0:
            p_color = _blend_color((200, 200, 255), p_alpha)
            draw.point((px, py), fill=p_color)


def _draw_text_frame(draw, t, max_t):
    """Draw text fade-in: 'LED' large, then 'MATRIX' below."""
    progress = t / max_t

    # "LED" - large text (scale=2), centered, fades in during first half
    led_alpha = min(1.0, progress * 2.5)
    led_text = "LED"
    led_scale = 3
    led_w = _text_width(led_text, scale=led_scale, spacing=2)
    led_x = (SIZE - led_w) // 2
    led_y = 12
    _draw_text(draw, led_text, led_x, led_y, _blend_color(TEXT_COLOR_LED, led_alpha),
               scale=led_scale, spacing=2)

    # "MATRIX" - smaller text, centered below, fades in during second half
    matrix_alpha = max(0.0, min(1.0, (progress - 0.3) * 2.5))
    matrix_text = "MATRIX"
    matrix_scale = 1
    matrix_w = _text_width(matrix_text, scale=matrix_scale, spacing=1)
    matrix_x = (SIZE - matrix_w) // 2
    matrix_y = 38
    _draw_text(draw, matrix_text, matrix_x, matrix_y,
               _blend_color(TEXT_COLOR_MATRIX, matrix_alpha),
               scale=matrix_scale, spacing=1)

    # Decorative dots in corners (subtle)
    corner_alpha = max(0.0, min(1.0, (progress - 0.5) * 3.0))
    if corner_alpha > 0:
        dc = _blend_color(DOT_COLOR, corner_alpha)
        for cx, cy in [(2, 2), (SIZE - 3, 2), (2, SIZE - 3), (SIZE - 3, SIZE - 3)]:
            draw.point((cx, cy), fill=dc)
            draw.point((cx + 1, cy), fill=dc)
            draw.point((cx, cy + 1), fill=dc)
            draw.point((cx + 1, cy + 1), fill=dc)


def _draw_loading_frame(draw, t, max_t):
    """Draw the text (held) plus an animated loading bar at the bottom."""
    progress = t / max_t

    # Keep the text visible
    _draw_text_frame(draw, max_t, max_t)

    # Loading bar dimensions
    bar_y = 54
    bar_h = 4
    bar_margin = 8
    bar_x0 = bar_margin
    bar_x1 = SIZE - bar_margin - 1
    bar_w = bar_x1 - bar_x0

    # Background
    draw.rectangle([bar_x0, bar_y, bar_x1, bar_y + bar_h], fill=BAR_BG)

    # Fill with eased progress
    eased = progress * progress * (3 - 2 * progress)  # smoothstep
    fill_w = int(bar_w * eased)
    if fill_w > 0:
        # Gradient fill: left green -> right bright green
        for x_off in range(fill_w):
            frac = x_off / max(bar_w, 1)
            r = int(BAR_FG[0] + (50 * frac))
            g = int(BAR_FG[1] + (55 * frac))
            b = int(BAR_FG[2] - (50 * frac))
            col = (min(r, 255), min(g, 255), max(b, 0))
            draw.line(
                [(bar_x0 + x_off, bar_y + 1),
                 (bar_x0 + x_off, bar_y + bar_h - 1)],
                fill=col
            )

    # Small "LOADING..." text above bar
    loading_alpha = min(1.0, progress * 3)
    blink = 1.0 if (int(t * 4) % 2 == 0) else 0.6
    txt = "LOADING..."
    tw = _text_width(txt, scale=1, spacing=1)
    tx = (SIZE - tw) // 2
    ty = 47
    _draw_text(draw, txt, tx, ty,
               _blend_color((100, 100, 120), loading_alpha * blink),
               scale=1, spacing=1)


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

    # Scale phase durations proportionally if total duration differs
    scale = duration / TOTAL_DURATION
    p_ring = PHASE_RING * scale
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

            if elapsed < p_ring:
                # Phase 1: Ring burst
                _draw_ring_frame(draw, elapsed, p_ring)
            elif elapsed < p_ring + p_text:
                # Phase 2: Text fade-in
                _draw_text_frame(draw, elapsed - p_ring, p_text)
            else:
                # Phase 3: Loading bar
                _draw_loading_frame(draw, elapsed - p_ring - p_text, p_loading)

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
