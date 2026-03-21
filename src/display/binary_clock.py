#!/usr/bin/env python3
"""
Binary clock display for 64x64 LED matrix.

Displays HH:MM:SS in binary format where each column represents a digit
and each row represents a bit value (8, 4, 2, 1 from top to bottom).
Lit bits are colored, unlit bits are dim. Features smooth color cycling.
"""

import time
import math
import logging
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 15  # 15 FPS for smooth second transitions


def _hsv_to_rgb(h, s, v):
    """Convert HSV (0-1 range) to RGB (0-255)."""
    if s == 0:
        c = int(v * 255)
        return (c, c, c)
    h = h % 1.0
    i = int(h * 6)
    f = h * 6 - i
    p = int(v * (1 - s) * 255)
    q = int(v * (1 - s * f) * 255)
    t = int(v * (1 - s * (1 - f)) * 255)
    v = int(v * 255)
    if i == 0: return (v, t, p)
    elif i == 1: return (q, v, p)
    elif i == 2: return (p, v, t)
    elif i == 3: return (p, q, v)
    elif i == 4: return (t, p, v)
    else: return (v, p, q)


# Digit info: (max_value, num_bits)
DIGIT_INFO = [
    (2, 2),  # H tens: 0-2
    (9, 4),  # H ones: 0-9
    (5, 3),  # M tens: 0-5
    (9, 4),  # M ones: 0-9
    (5, 3),  # S tens: 0-5
    (9, 4),  # S ones: 0-9
]


def run(matrix, duration=60):
    """Run the binary clock display for the specified duration."""
    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            frame_start = time.time()
            now = datetime.now()
            h, m, s = now.hour, now.minute, now.second

            # Split into digits
            digits = [h // 10, h % 10, m // 10, m % 10, s // 10, s % 10]

            # Color cycling based on time
            base_hue = (time.time() * 0.02) % 1.0

            image = Image.new("RGB", (WIDTH, HEIGHT), (2, 2, 8))
            draw = ImageDraw.Draw(image)

            # Layout constants
            col_width = 8
            bit_height = 8
            bit_gap = 2
            col_gap = 2
            separator_width = 4

            # Calculate starting positions to center the display
            # 6 digit columns + 2 separators
            total_width = 6 * col_width + 2 * separator_width + 5 * col_gap
            start_x = (WIDTH - total_width) // 2
            start_y = 6

            # Labels
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

            label_y = start_y - 1
            # H, M, S labels positioned above their digit pairs
            for label_idx, (label, lx_offset) in enumerate([("H", 0), ("M", 2), ("S", 4)]):
                lx = start_x
                for i in range(lx_offset):
                    lx += col_width + col_gap
                    if i == 1 or i == 3:
                        lx += separator_width
                hue = (base_hue + label_idx * 0.15) % 1.0
                r, g, b = _hsv_to_rgb(hue, 0.5, 0.7)
                draw.text((lx + 1, 0), label, fill=(r, g, b), font=font)

            # Draw bit rows (4 rows: values 8, 4, 2, 1)
            bit_labels = ["8", "4", "2", "1"]
            for bit_row, label in enumerate(bit_labels):
                # Bit value label on the left
                by = start_y + bit_row * (bit_height + bit_gap)
                draw.text((0, by), label, fill=(50, 50, 60), font=font)

            # Draw digit columns
            x = start_x
            for col_idx, (digit, (max_val, num_bits)) in enumerate(zip(digits, DIGIT_INFO)):
                # Add separator before M and S groups
                if col_idx == 2 or col_idx == 4:
                    # Draw colon dots
                    sep_x = x
                    dot_y1 = start_y + 1 * (bit_height + bit_gap) + bit_height // 2
                    dot_y2 = start_y + 2 * (bit_height + bit_gap) + bit_height // 2
                    # Blink the colons with seconds
                    if now.microsecond < 500000:
                        draw.rectangle([sep_x, dot_y1 - 1, sep_x + 2, dot_y1 + 1], fill=(150, 150, 180))
                        draw.rectangle([sep_x, dot_y2 - 1, sep_x + 2, dot_y2 + 1], fill=(150, 150, 180))
                    x += separator_width

                # Column hue
                col_hue = (base_hue + col_idx * 0.08) % 1.0

                # Draw 4 bit positions (from MSB=8 at top to LSB=1 at bottom)
                for bit_row in range(4):
                    bit_value = 3 - bit_row  # bit 3=8, 2=4, 1=2, 0=1
                    by = start_y + bit_row * (bit_height + bit_gap)

                    # Is this bit position valid for this digit?
                    if bit_value >= num_bits:
                        # This bit position doesn't apply (e.g., H tens only has 2 bits)
                        continue

                    is_set = (digit >> bit_value) & 1

                    if is_set:
                        # Lit bit - vibrant color
                        hue = (col_hue + bit_row * 0.05) % 1.0
                        r, g, b = _hsv_to_rgb(hue, 0.9, 1.0)
                        # Outer glow
                        draw.rectangle(
                            [x - 1, by - 1, x + col_width, by + bit_height],
                            fill=None,
                            outline=_hsv_to_rgb(hue, 0.5, 0.3)
                        )
                        # Main bit
                        draw.rectangle(
                            [x, by, x + col_width - 1, by + bit_height - 1],
                            fill=(r, g, b)
                        )
                    else:
                        # Unlit bit - very dim
                        draw.rectangle(
                            [x, by, x + col_width - 1, by + bit_height - 1],
                            fill=(12, 12, 20)
                        )

                x += col_width + col_gap

            # Bottom: show actual time in decimal as reference
            time_str = now.strftime("%H:%M:%S")
            text_hue = (base_hue + 0.5) % 1.0
            r, g, b = _hsv_to_rgb(text_hue, 0.6, 0.8)
            draw.text((12, 54), time_str, fill=(r, g, b), font=font)

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
