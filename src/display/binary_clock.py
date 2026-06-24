#!/usr/bin/env python3
"""
Binary clock display for 64x64 LED matrix.

Enhanced visual design featuring:
- Circular LED-style bit indicators with glow effects
- Row labels (H/M/S) and column bit value headers (32,16,8,4,2,1)
- Smooth color gradients and cascading glow animations
- Particle shimmer on bit transitions
- Clean bitmap font time display at bottom
- Subtle background gradient with vignette
"""

import time
import math
import logging
from datetime import datetime
from PIL import Image, ImageDraw
from src.display._fonts import _draw_text, _text_width
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 15  # 15 FPS for smooth animations

# Color palette
BG_COLOR = (2, 2, 8)
HOUR_COLOR = (0, 180, 255)      # Bright cyan
MINUTE_COLOR = (0, 255, 100)    # Bright green
SECOND_COLOR = (255, 160, 40)   # Warm orange

# Dimmer versions for off-state
HOUR_DIM = (0, 20, 35)
MINUTE_DIM = (0, 30, 15)
SECOND_DIM = (30, 18, 6)

# Label colors
LABEL_COLOR = (60, 60, 90)
BIT_LABEL_COLOR = (40, 40, 65)
COLON_COLOR = (80, 80, 120)
SEPARATOR_COLOR = (15, 15, 30)


def _draw_circle(draw, cx, cy, r, fill_color, glow_color=None, glow_radius=0):
    """Draw a filled circle with optional glow effect."""
    # Draw glow layers (outer to inner)
    if glow_color and glow_radius > 0:
        for gr in range(glow_radius, 0, -1):
            alpha = (glow_radius - gr + 1) / (glow_radius + 1)
            alpha = alpha * 0.4  # Subtle glow
            gc = (
                int(glow_color[0] * alpha),
                int(glow_color[1] * alpha),
                int(glow_color[2] * alpha),
            )
            if gc != (0, 0, 0):
                draw.ellipse(
                    [cx - r - gr, cy - r - gr, cx + r + gr, cy + r + gr],
                    fill=gc,
                )

    # Main filled circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill_color)

    # Inner highlight (top-left bright spot for 3D effect)
    if fill_color != BG_COLOR and max(fill_color) > 40:
        highlight = (
            min(255, fill_color[0] + 80),
            min(255, fill_color[1] + 80),
            min(255, fill_color[2] + 80),
        )
        if r >= 3:
            draw.point((cx - 1, cy - 1), fill=highlight)


def _draw_bit_indicator(draw, cx, cy, is_set, on_color, dim_color, tick, bit_idx, row_idx):
    """Draw a single bit indicator as a glowing circle."""
    r = 3  # Circle radius

    if is_set:
        # Pulsing glow animation - each bit pulses slightly offset
        phase = tick * 0.12 + bit_idx * 0.5 + row_idx * 1.2
        pulse = 0.8 + 0.2 * math.sin(phase)

        # Compute pulsed color
        color = (
            min(255, int(on_color[0] * pulse)),
            min(255, int(on_color[1] * pulse)),
            min(255, int(on_color[2] * pulse)),
        )

        # Draw with glow
        _draw_circle(draw, cx, cy, r, color, glow_color=on_color, glow_radius=2)

        # Bright center dot
        center_color = (
            min(255, on_color[0] + 100),
            min(255, on_color[1] + 100),
            min(255, on_color[2] + 100),
        )
        draw.point((cx, cy), fill=center_color)
    else:
        # Off state - subtle ring outline
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=dim_color)
        # Even dimmer center
        inner_dim = (dim_color[0] // 2, dim_color[1] // 2, dim_color[2] // 2)
        draw.ellipse([cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1], fill=inner_dim)


def _draw_background(draw, tick):
    """Draw subtle animated background with vignette."""
    # Subtle gradient from dark blue at top to near-black at bottom
    for y in range(HEIGHT):
        grad = max(0, 8 - y // 10)
        row_color = (grad // 2, grad // 2, grad + 2)
        draw.line([(0, y), (WIDTH - 1, y)], fill=row_color)

    # Subtle corner vignette
    for corner_x, corner_y in [(0, 0), (63, 0), (0, 63), (63, 63)]:
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                px, py = corner_x + dx, corner_y + dy
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist < 4:
                        draw.point((px, py), fill=(0, 0, 0))


def _draw_shimmer_particles(draw, prev_values, curr_values, tick, row_colors):
    """Draw shimmer particles on bits that just changed."""
    # Simple sparkle effect at positions where bits transitioned
    sq_step = 9
    start_x = 11
    start_y = 14
    row_step = 15

    for row_idx in range(3):
        for bit_idx in range(6):
            prev_bit = (prev_values[row_idx] >> (5 - bit_idx)) & 1
            curr_bit = (curr_values[row_idx] >> (5 - bit_idx)) & 1

            if prev_bit != curr_bit:
                cx = start_x + bit_idx * sq_step
                cy = start_y + row_idx * row_step

                # Sparkle animation
                color = row_colors[row_idx]
                for angle_step in range(4):
                    angle = tick * 0.5 + angle_step * (math.pi / 2)
                    spark_dist = 4 + (tick % 4)
                    sx = int(cx + math.cos(angle) * spark_dist)
                    sy = int(cy + math.sin(angle) * spark_dist)
                    if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                        fade = max(0, 1.0 - (tick % 8) / 8.0)
                        sc = (
                            int(color[0] * fade),
                            int(color[1] * fade),
                            int(color[2] * fade),
                        )
                        if sc != (0, 0, 0):
                            draw.point((sx, sy), fill=sc)


def run(matrix, duration=60):
    """Run the enhanced binary clock display."""
    start_time = time.time()
    tick = 0
    prev_values = [0, 0, 0]  # Track previous H, M, S for transition effects
    transition_tick = [0, 0, 0]  # Tick when last transition happened per row

    # Layout constants
    bit_step = 9          # Horizontal spacing between bit centers
    start_x = 11         # First bit center X position
    start_y = 14         # First row center Y
    row_step = 15        # Vertical spacing between rows

    # Row configs: (label, on_color, dim_color)
    row_configs = [
        ("H", HOUR_COLOR, HOUR_DIM),
        ("M", MINUTE_COLOR, MINUTE_DIM),
        ("S", SECOND_COLOR, SECOND_DIM),
    ]

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            tick += 1
            now = datetime.now()

            image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
            draw = ImageDraw.Draw(image)

            # Draw background
            _draw_background(draw, tick)

            # Current time values
            values = [now.hour, now.minute, now.second]

            # Detect transitions for shimmer effect
            for i in range(3):
                if values[i] != prev_values[i]:
                    transition_tick[i] = tick

            # --- Bit column headers (32, 16, 8, 4, 2, 1) ---
            bit_labels = ["32", "16", "8", "4", "2", "1"]
            for bit_idx, label in enumerate(bit_labels):
                lx = start_x + bit_idx * bit_step
                lw = _text_width(label, scale=1, spacing=0)
                _draw_text(draw, label, lx - lw // 2, 2, BIT_LABEL_COLOR, scale=1, spacing=0)

            # --- Draw the 3 rows of bit indicators ---
            for row_idx, (label, on_color, dim_color) in enumerate(row_configs):
                cy = start_y + row_idx * row_step
                value = values[row_idx]

                # Row label on the left
                _draw_text(draw, label, 2, cy - 3, LABEL_COLOR, scale=1, spacing=0)

                # Draw 6 bits
                for bit_idx in range(6):
                    bit_pos = 5 - bit_idx
                    cx = start_x + bit_idx * bit_step
                    is_set = (value >> bit_pos) & 1

                    _draw_bit_indicator(
                        draw, cx, cy, is_set,
                        on_color, dim_color, tick, bit_idx, row_idx
                    )

            # --- Shimmer particles on transitions ---
            for row_idx in range(3):
                age = tick - transition_tick[row_idx]
                if 0 < age < 10:
                    _draw_shimmer_particles(
                        draw, prev_values, values, age,
                        [HOUR_COLOR, MINUTE_COLOR, SECOND_COLOR]
                    )

            # --- Separator line ---
            sep_y = start_y + 2 * row_step + 8
            for x in range(4, 60):
                # Dotted separator with subtle color
                if x % 3 != 0:
                    draw.point((x, sep_y), fill=SEPARATOR_COLOR)

            # --- Clean time display at bottom using bitmap font ---
            time_y = sep_y + 4
            h_str = f"{now.hour:02d}"
            m_str = f"{now.minute:02d}"
            s_str = f"{now.second:02d}"

            # Calculate total width for centering
            # "HH:MM:SS" with spacing
            h_w = _text_width(h_str, scale=1, spacing=1)
            m_w = _text_width(m_str, scale=1, spacing=1)
            s_w = _text_width(s_str, scale=1, spacing=1)
            colon_w = _text_width(":", scale=1, spacing=1)
            total_w = h_w + colon_w + m_w + colon_w + s_w + 4  # +4 for padding
            tx = (WIDTH - total_w) // 2

            # Hours in their color
            _draw_text(draw, h_str, tx, time_y, HOUR_COLOR, scale=1, spacing=1)
            tx += h_w + 1

            # Blinking colon
            blink = now.microsecond < 500000
            colon_c = COLON_COLOR if blink else (20, 20, 35)
            _draw_text(draw, ":", tx, time_y, colon_c, scale=1, spacing=1)
            tx += colon_w + 1

            # Minutes in their color
            _draw_text(draw, m_str, tx, time_y, MINUTE_COLOR, scale=1, spacing=1)
            tx += m_w + 1

            # Blinking colon
            _draw_text(draw, ":", tx, time_y, colon_c, scale=1, spacing=1)
            tx += colon_w + 1

            # Seconds in their color
            _draw_text(draw, s_str, tx, time_y, SECOND_COLOR, scale=1, spacing=1)

            # Update previous values
            prev_values = values[:]

            matrix.SetImage(image)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in binary clock: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
