#!/usr/bin/env python3
"""Scrolling text marquee for 64x64 LED matrix."""

import json
import os
import time
import math
import logging
from PIL import Image, ImageDraw, ImageFont

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
    r = int((math.sin(offset * 0.1) * 0.5 + 0.5) * 255)
    g = int((math.sin(offset * 0.1 + 2.094) * 0.5 + 0.5) * 255)
    b = int((math.sin(offset * 0.1 + 4.189) * 0.5 + 0.5) * 255)
    return (r, g, b)


def run(matrix, duration=60):
    """Run the text scroller for the specified duration."""
    start_time = time.time()
    
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    
    messages = _load_messages()
    msg_idx = 0
    scroll_x = WIDTH  # Start off-screen right
    color_idx = 0
    
    try:
        while time.time() - start_time < duration:
            frame_start = time.time()
            
            message = messages[msg_idx % len(messages)]
            color = COLORS[color_idx % len(COLORS)]
            
            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
            draw = ImageDraw.Draw(image)
            
            # Calculate text width for scroll bounds
            try:
                bbox = draw.textbbox((0, 0), message, font=font)
                text_width = bbox[2] - bbox[0]
            except Exception:
                text_width = len(message) * 6
            
            # Draw the scrolling text vertically centered
            y_pos = (HEIGHT - 10) // 2
            
            # Rainbow mode: each character gets a different color
            for i, char in enumerate(message):
                char_x = int(scroll_x) + i * 6
                if -6 < char_x < WIDTH:
                    char_color = _rainbow_color(i + scroll_x * 0.5)
                    draw.text((char_x, y_pos), char, fill=char_color, font=font)
            
            matrix.SetImage(image)
            
            # Move scroll
            scroll_x -= 1.0
            
            # If fully scrolled off screen, switch to next message
            if scroll_x < -text_width - 10:
                scroll_x = WIDTH
                msg_idx += 1
                color_idx += 1
            
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
