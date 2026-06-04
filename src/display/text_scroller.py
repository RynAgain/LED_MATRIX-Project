#!/usr/bin/env python3
"""Scrolling text marquee for 64x64 LED matrix.

Uses the shared 5x7 bitmap font from _fonts.py for crisp, readable text
that matches the menu system's style. Scrolls messages horizontally with
rainbow color cycling.
"""

import json
import os
import time
import math
import logging
from PIL import Image, ImageDraw
from src.display._fonts import _draw_text, _draw_char, _text_width, FONT_5X7
from src.display._shared import should_stop

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30

# Font metrics (from _fonts.py: 5px wide glyphs, scale=1, spacing=1)
CHAR_W = 5
CHAR_H = 7
CHAR_GAP = 1
CHAR_STEP = CHAR_W + CHAR_GAP  # 6px per character

# Default messages to scroll
DEFAULT_MESSAGES = [
    "Welcome to LED Matrix!",
    "Hello World!",
    "Raspberry Pi Rocks!",
    "LED Matrix Project v2.0",
]

# Color themes
COLORS = [
    (255, 0, 0),      # Red
    (0, 255, 0),       # Green
    (0, 100, 255),     # Blue
    (255, 255, 0),     # Yellow
    (255, 0, 255),     # Magenta
    (0, 255, 255),     # Cyan
    (255, 128, 0),     # Orange
    (255, 255, 255),   # White
]


def _load_messages():
    """Load custom messages from config/messages.json."""
    msg_path = os.path.join(PROJECT_ROOT, "config", "messages.json")
    try:
        with open(msg_path, "r") as f:
            data = json.load(f)
        msgs = data.get("messages", [])
        if msgs:
            return msgs
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return DEFAULT_MESSAGES


def _rainbow_color(offset):
    """Generate a rainbow color based on offset."""
    r = int((math.sin(offset * 0.15) * 0.5 + 0.5) * 255)
    g = int((math.sin(offset * 0.15 + 2.094) * 0.5 + 0.5) * 255)
    b = int((math.sin(offset * 0.15 + 4.189) * 0.5 + 0.5) * 255)
    # Ensure minimum brightness so text is always visible
    return (max(60, r), max(60, g), max(60, b))


def run(matrix, duration=60):
    """Run the text scroller for the specified duration."""
    start_time = time.time()

    messages = _load_messages()
    msg_idx = 0
    scroll_x = float(WIDTH)  # Start off-screen right

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()

            message = messages[msg_idx % len(messages)]
            text_w = _text_width(message, scale=1, spacing=CHAR_GAP)

            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
            draw = ImageDraw.Draw(image)

            # Vertically center the 7-pixel-tall text
            y_pos = (HEIGHT - CHAR_H) // 2

            # Draw each character with rainbow color using the shared font
            for i, char in enumerate(message):
                char_x = int(scroll_x) + i * CHAR_STEP
                # Only draw if character is on screen (with margin)
                if -(CHAR_W + 1) < char_x < WIDTH + 1:
                    char_color = _rainbow_color(i + scroll_x * 0.3)
                    _draw_char(draw, char, char_x, y_pos, char_color, scale=1)

            matrix.SetImage(image)

            # Scroll left
            scroll_x -= 1.0

            # If fully scrolled off screen, switch to next message
            if scroll_x < -text_w - 10:
                scroll_x = float(WIDTH)
                msg_idx += 1

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in text scroller: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
