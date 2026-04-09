#!/usr/bin/env python3
"""Scrolling text marquee for 64x64 LED matrix.

Uses a built-in 5x7 pixel font for crisp rendering at LED matrix resolution.
No external font files required.
"""

import json
import os
import time
import math
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30

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

# ---------------------------------------------------------------------------
# Built-in 5x7 pixel font -- covers ASCII 32-126
# Each character is 5 pixels wide, 7 pixels tall, 1 pixel gap between chars.
# Stored as 7 rows of 5-bit bitmaps (MSB = leftmost pixel).
# ---------------------------------------------------------------------------
_FONT_5x7 = {
    ' ':  [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000],
    '!':  [0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00000, 0b00100],
    '"':  [0b01010, 0b01010, 0b01010, 0b00000, 0b00000, 0b00000, 0b00000],
    '#':  [0b01010, 0b01010, 0b11111, 0b01010, 0b11111, 0b01010, 0b01010],
    '$':  [0b00100, 0b01111, 0b10100, 0b01110, 0b00101, 0b11110, 0b00100],
    '%':  [0b11000, 0b11001, 0b00010, 0b00100, 0b01000, 0b10011, 0b00011],
    '&':  [0b01100, 0b10010, 0b10100, 0b01000, 0b10101, 0b10010, 0b01101],
    "'":  [0b00100, 0b00100, 0b00100, 0b00000, 0b00000, 0b00000, 0b00000],
    '(':  [0b00010, 0b00100, 0b01000, 0b01000, 0b01000, 0b00100, 0b00010],
    ')':  [0b01000, 0b00100, 0b00010, 0b00010, 0b00010, 0b00100, 0b01000],
    '*':  [0b00000, 0b00100, 0b10101, 0b01110, 0b10101, 0b00100, 0b00000],
    '+':  [0b00000, 0b00100, 0b00100, 0b11111, 0b00100, 0b00100, 0b00000],
    ',':  [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00100, 0b01000],
    '-':  [0b00000, 0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000],
    '.':  [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00100],
    '/':  [0b00000, 0b00001, 0b00010, 0b00100, 0b01000, 0b10000, 0b00000],
    '0':  [0b01110, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b01110],
    '1':  [0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    '2':  [0b01110, 0b10001, 0b00001, 0b00010, 0b00100, 0b01000, 0b11111],
    '3':  [0b11111, 0b00010, 0b00100, 0b00010, 0b00001, 0b10001, 0b01110],
    '4':  [0b00010, 0b00110, 0b01010, 0b10010, 0b11111, 0b00010, 0b00010],
    '5':  [0b11111, 0b10000, 0b11110, 0b00001, 0b00001, 0b10001, 0b01110],
    '6':  [0b00110, 0b01000, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110],
    '7':  [0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b01000, 0b01000],
    '8':  [0b01110, 0b10001, 0b10001, 0b01110, 0b10001, 0b10001, 0b01110],
    '9':  [0b01110, 0b10001, 0b10001, 0b01111, 0b00001, 0b00010, 0b01100],
    ':':  [0b00000, 0b00000, 0b00100, 0b00000, 0b00100, 0b00000, 0b00000],
    ';':  [0b00000, 0b00000, 0b00100, 0b00000, 0b00100, 0b00100, 0b01000],
    '<':  [0b00010, 0b00100, 0b01000, 0b10000, 0b01000, 0b00100, 0b00010],
    '=':  [0b00000, 0b00000, 0b11111, 0b00000, 0b11111, 0b00000, 0b00000],
    '>':  [0b01000, 0b00100, 0b00010, 0b00001, 0b00010, 0b00100, 0b01000],
    '?':  [0b01110, 0b10001, 0b00001, 0b00010, 0b00100, 0b00000, 0b00100],
    '@':  [0b01110, 0b10001, 0b10111, 0b10101, 0b10110, 0b10000, 0b01110],
    'A':  [0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001],
    'B':  [0b11110, 0b10001, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110],
    'C':  [0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110],
    'D':  [0b11100, 0b10010, 0b10001, 0b10001, 0b10001, 0b10010, 0b11100],
    'E':  [0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111],
    'F':  [0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b10000],
    'G':  [0b01110, 0b10001, 0b10000, 0b10111, 0b10001, 0b10001, 0b01111],
    'H':  [0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001],
    'I':  [0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    'J':  [0b00111, 0b00010, 0b00010, 0b00010, 0b00010, 0b10010, 0b01100],
    'K':  [0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b10001],
    'L':  [0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111],
    'M':  [0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001],
    'N':  [0b10001, 0b10001, 0b11001, 0b10101, 0b10011, 0b10001, 0b10001],
    'O':  [0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
    'P':  [0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000],
    'Q':  [0b01110, 0b10001, 0b10001, 0b10001, 0b10101, 0b10010, 0b01101],
    'R':  [0b11110, 0b10001, 0b10001, 0b11110, 0b10100, 0b10010, 0b10001],
    'S':  [0b01111, 0b10000, 0b10000, 0b01110, 0b00001, 0b00001, 0b11110],
    'T':  [0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100],
    'U':  [0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
    'V':  [0b10001, 0b10001, 0b10001, 0b10001, 0b01010, 0b01010, 0b00100],
    'W':  [0b10001, 0b10001, 0b10001, 0b10101, 0b10101, 0b10101, 0b01010],
    'X':  [0b10001, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b10001],
    'Y':  [0b10001, 0b10001, 0b01010, 0b00100, 0b00100, 0b00100, 0b00100],
    'Z':  [0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b10000, 0b11111],
    '[':  [0b01110, 0b01000, 0b01000, 0b01000, 0b01000, 0b01000, 0b01110],
    '\\': [0b00000, 0b10000, 0b01000, 0b00100, 0b00010, 0b00001, 0b00000],
    ']':  [0b01110, 0b00010, 0b00010, 0b00010, 0b00010, 0b00010, 0b01110],
    '^':  [0b00100, 0b01010, 0b10001, 0b00000, 0b00000, 0b00000, 0b00000],
    '_':  [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b11111],
    '`':  [0b01000, 0b00100, 0b00010, 0b00000, 0b00000, 0b00000, 0b00000],
    'a':  [0b00000, 0b00000, 0b01110, 0b00001, 0b01111, 0b10001, 0b01111],
    'b':  [0b10000, 0b10000, 0b10110, 0b11001, 0b10001, 0b10001, 0b11110],
    'c':  [0b00000, 0b00000, 0b01110, 0b10000, 0b10000, 0b10001, 0b01110],
    'd':  [0b00001, 0b00001, 0b01101, 0b10011, 0b10001, 0b10001, 0b01111],
    'e':  [0b00000, 0b00000, 0b01110, 0b10001, 0b11111, 0b10000, 0b01110],
    'f':  [0b00110, 0b01001, 0b01000, 0b11100, 0b01000, 0b01000, 0b01000],
    'g':  [0b00000, 0b01111, 0b10001, 0b10001, 0b01111, 0b00001, 0b01110],
    'h':  [0b10000, 0b10000, 0b10110, 0b11001, 0b10001, 0b10001, 0b10001],
    'i':  [0b00100, 0b00000, 0b01100, 0b00100, 0b00100, 0b00100, 0b01110],
    'j':  [0b00010, 0b00000, 0b00110, 0b00010, 0b00010, 0b10010, 0b01100],
    'k':  [0b10000, 0b10000, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010],
    'l':  [0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    'm':  [0b00000, 0b00000, 0b11010, 0b10101, 0b10101, 0b10001, 0b10001],
    'n':  [0b00000, 0b00000, 0b10110, 0b11001, 0b10001, 0b10001, 0b10001],
    'o':  [0b00000, 0b00000, 0b01110, 0b10001, 0b10001, 0b10001, 0b01110],
    'p':  [0b00000, 0b00000, 0b11110, 0b10001, 0b11110, 0b10000, 0b10000],
    'q':  [0b00000, 0b00000, 0b01101, 0b10011, 0b01111, 0b00001, 0b00001],
    'r':  [0b00000, 0b00000, 0b10110, 0b11001, 0b10000, 0b10000, 0b10000],
    's':  [0b00000, 0b00000, 0b01110, 0b10000, 0b01110, 0b00001, 0b11110],
    't':  [0b01000, 0b01000, 0b11100, 0b01000, 0b01000, 0b01001, 0b00110],
    'u':  [0b00000, 0b00000, 0b10001, 0b10001, 0b10001, 0b10011, 0b01101],
    'v':  [0b00000, 0b00000, 0b10001, 0b10001, 0b10001, 0b01010, 0b00100],
    'w':  [0b00000, 0b00000, 0b10001, 0b10001, 0b10101, 0b10101, 0b01010],
    'x':  [0b00000, 0b00000, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001],
    'y':  [0b00000, 0b00000, 0b10001, 0b10001, 0b01111, 0b00001, 0b01110],
    'z':  [0b00000, 0b00000, 0b11111, 0b00010, 0b00100, 0b01000, 0b11111],
    '{':  [0b00010, 0b00100, 0b00100, 0b01000, 0b00100, 0b00100, 0b00010],
    '|':  [0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100],
    '}':  [0b01000, 0b00100, 0b00100, 0b00010, 0b00100, 0b00100, 0b01000],
    '~':  [0b00000, 0b00000, 0b01000, 0b10101, 0b00010, 0b00000, 0b00000],
}

CHAR_W = 5   # pixels per character
CHAR_H = 7   # pixels per character
CHAR_GAP = 1 # gap between characters


def _draw_char(image, ch, x, y, color):
    """Draw a single character using the 5x7 pixel font.

    Args:
        image: PIL Image to draw on.
        ch: Character to draw.
        x: X position (left edge).
        y: Y position (top edge).
        color: (r, g, b) tuple.
    """
    glyph = _FONT_5x7.get(ch, _FONT_5x7.get(ch.upper(), _FONT_5x7.get('?', _FONT_5x7[' '])))
    for row_idx, bits in enumerate(glyph):
        for col_idx in range(CHAR_W):
            if bits & (1 << (CHAR_W - 1 - col_idx)):
                px = x + col_idx
                py = y + row_idx
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    image.putpixel((px, py), color)


def _text_width(text):
    """Calculate pixel width of a text string."""
    if not text:
        return 0
    return len(text) * (CHAR_W + CHAR_GAP) - CHAR_GAP


def _draw_text(image, text, x, y, color):
    """Draw a string of text at (x, y) using the pixel font."""
    cx = x
    for ch in text:
        _draw_char(image, ch, cx, y, color)
        cx += CHAR_W + CHAR_GAP


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
    return (max(40, r), max(40, g), max(40, b))


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
            text_w = _text_width(message)

            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))

            # Vertically center the 7-pixel-tall text
            y_pos = (HEIGHT - CHAR_H) // 2

            # Draw each character with rainbow color
            char_step = CHAR_W + CHAR_GAP
            for i, char in enumerate(message):
                char_x = int(scroll_x) + i * char_step
                # Only draw if character is on screen (with margin)
                if -(CHAR_W + 1) < char_x < WIDTH + 1:
                    char_color = _rainbow_color(i + scroll_x * 0.3)
                    _draw_char(image, char, char_x, y_pos, char_color)

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
