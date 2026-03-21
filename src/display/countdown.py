#!/usr/bin/env python3
"""Countdown timer for 64x64 LED matrix. Configurable from web panel."""

import time
import math
import json
import os
import logging
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 15
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COUNTDOWN_PATH = os.path.join(PROJECT_ROOT, "config", "countdown.json")


def _load_countdown():
    """Load countdown target from config."""
    try:
        with open(COUNTDOWN_PATH, "r") as f:
            data = json.load(f)
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"label": "Countdown", "seconds": 300}  # Default 5 min


def _format_time(seconds):
    """Format seconds into HH:MM:SS or MM:SS."""
    if seconds <= 0:
        return "00:00"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _draw_digit(draw, x, y, digit, color, scale=2):
    """Draw a large pixel digit at position (x,y)."""
    # 3x5 pixel font scaled up
    DIGITS = {
        '0': ["###", "# #", "# #", "# #", "###"],
        '1': [" # ", "## ", " # ", " # ", "###"],
        '2': ["###", "  #", "###", "#  ", "###"],
        '3': ["###", "  #", "###", "  #", "###"],
        '4': ["# #", "# #", "###", "  #", "  #"],
        '5': ["###", "#  ", "###", "  #", "###"],
        '6': ["###", "#  ", "###", "# #", "###"],
        '7': ["###", "  #", "  #", "  #", "  #"],
        '8': ["###", "# #", "###", "# #", "###"],
        '9': ["###", "# #", "###", "  #", "###"],
        ':': ["   ", " # ", "   ", " # ", "   "],
    }
    pattern = DIGITS.get(digit, DIGITS['0'])
    for row_idx, row in enumerate(pattern):
        for col_idx, ch in enumerate(row):
            if ch == '#':
                px = x + col_idx * scale
                py = y + row_idx * scale
                draw.rectangle([px, py, px + scale - 1, py + scale - 1], fill=color)


def run(matrix, duration=60):
    """Run the countdown timer."""
    config = _load_countdown()
    label = config.get("label", "Countdown")
    target_seconds = config.get("seconds", 300)

    countdown_start = time.time()
    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            frame_start = time.time()

            elapsed = time.time() - countdown_start
            remaining = max(0, target_seconds - elapsed)

            image = Image.new("RGB", (WIDTH, HEIGHT), (2, 2, 8))
            draw = ImageDraw.Draw(image)

            # Label at top
            try:
                from PIL import ImageFont
                font = ImageFont.load_default()
            except Exception:
                font = None

            # Truncate label
            short_label = label[:10]
            draw.text((2, 1), short_label, fill=(100, 100, 140), font=font)

            # Time remaining - large digits
            time_str = _format_time(remaining)

            # Color based on remaining time
            if remaining <= 0:
                # Finished - flash red/white
                if int(time.time() * 2) % 2:
                    color = (255, 50, 50)
                else:
                    color = (255, 255, 255)
            elif remaining < 10:
                color = (255, 50, 50)   # Red - urgent
            elif remaining < 60:
                color = (255, 200, 0)   # Yellow - getting close
            else:
                color = (0, 255, 100)   # Green - plenty of time

            # Draw large time centered
            char_w = 3 * 2 + 1  # 7px per char at scale=2
            total_w = len(time_str) * char_w
            tx = (WIDTH - total_w) // 2
            ty = 18

            for ch in time_str:
                _draw_digit(draw, tx, ty, ch, color, scale=2)
                tx += char_w

            # Progress bar at bottom
            bar_y = HEIGHT - 8
            bar_h = 4
            progress = 1.0 - (remaining / max(target_seconds, 1))
            bar_w = int((WIDTH - 4) * min(1.0, progress))

            # Background
            draw.rectangle([2, bar_y, WIDTH - 3, bar_y + bar_h], fill=(20, 20, 30))
            # Fill
            if bar_w > 0:
                draw.rectangle([2, bar_y, 2 + bar_w, bar_y + bar_h], fill=color)

            # Percentage
            pct = int(progress * 100)
            draw.text((2, bar_y - 9), f"{pct}%", fill=(80, 80, 100), font=font)

            matrix.SetImage(image)

            elapsed_frame = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed_frame
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in countdown: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
