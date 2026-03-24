#!/usr/bin/env python3
"""
Binary clock display for 64x64 LED matrix.

Clean minimal design: just colored bit squares and a time reference.
3 rows (hours, minutes, seconds) x 6 columns (bits 32 to 1).
"""

import time
import math
import logging
from datetime import datetime
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 10


def run(matrix, duration=60):
    """Run the binary clock display."""
    start_time = time.time()

    # Layout: 3 rows of 6 squares, centered, with clean time at bottom
    sq = 8              # Square size (8x8 pixels)
    gap = 2             # Gap between squares
    step = sq + gap     # 10px per cell

    # Center horizontally: 6 * 10 - 2 = 58px -> offset = 3
    start_x = (WIDTH - (6 * step - gap)) // 2
    # Vertical: 3 rows of 10px = 30px, plus gaps, centered in top portion
    start_y = 6
    row_step = sq + 5   # 13px between rows

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            now = datetime.now()

            image = Image.new("RGB", (WIDTH, HEIGHT), (2, 2, 6))
            draw = ImageDraw.Draw(image)

            rows = [
                (now.hour,   (0, 160, 255)),   # Cyan for hours
                (now.minute, (0, 255, 80)),     # Green for minutes
                (now.second, (255, 140, 40)),   # Orange for seconds
            ]

            for row_idx, (value, on_color) in enumerate(rows):
                y = start_y + row_idx * row_step

                for bit_idx in range(6):
                    bit_pos = 5 - bit_idx
                    x = start_x + bit_idx * step
                    is_set = (value >> bit_pos) & 1

                    if is_set:
                        pulse = 0.85 + 0.15 * math.sin(time.time() * 4 + bit_idx * 0.7)
                        r = min(255, int(on_color[0] * pulse))
                        g = min(255, int(on_color[1] * pulse))
                        b = min(255, int(on_color[2] * pulse))
                        draw.rectangle([x, y, x + sq - 1, y + sq - 1], fill=(r, g, b))
                    else:
                        draw.rectangle([x, y, x + sq - 1, y + sq - 1],
                                      fill=(10, 10, 16), outline=(22, 22, 32))

            # Clean time at bottom, properly centered
            h_str = f"{now.hour:02d}"
            m_str = f"{now.minute:02d}"
            s_str = f"{now.second:02d}"

            # Draw each part in its row color, separated by dim colons
            # Using pixel-level positioning for clean centering
            # Each char ~6px wide, colon ~3px, total ~6+6+3+6+6+3+6+6 = 42px
            ty = HEIGHT - 12
            tx = (WIDTH - 42) // 2

            # Hours in cyan
            draw.text((tx, ty), h_str, fill=(0, 100, 160))
            # Colon
            blink = now.microsecond < 500000
            colon_color = (60, 60, 80) if blink else (20, 20, 30)
            draw.text((tx + 12, ty), ":", fill=colon_color)
            # Minutes in green
            draw.text((tx + 16, ty), m_str, fill=(0, 160, 50))
            # Colon
            draw.text((tx + 28, ty), ":", fill=colon_color)
            # Seconds in orange
            draw.text((tx + 32, ty), s_str, fill=(160, 90, 25))

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
