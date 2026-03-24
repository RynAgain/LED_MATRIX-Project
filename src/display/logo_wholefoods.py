#!/usr/bin/env python3
"""Whole Foods Market logo display for 64x64 LED matrix."""

import time
import math
import logging
from PIL import Image, ImageDraw, ImageFont
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64


def _draw_logo():
    """Draw a clean Whole Foods-inspired logo using PIL drawing primitives."""
    image = Image.new("RGB", (WIDTH, HEIGHT), (0, 40, 15))
    draw = ImageDraw.Draw(image)

    cx, cy = 32, 26

    # Solid green circle (filled)
    draw.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill=(0, 80, 35))

    # Bright green circle outline
    draw.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], outline=(60, 200, 80), width=2)

    # Inner lighter circle
    draw.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(0, 90, 40))

    # Leaf shape using a tilted ellipse (upper portion)
    # Draw a green leaf tilted slightly
    leaf_points = []
    for angle in range(360):
        rad = math.radians(angle)
        # Leaf is an ellipse stretched horizontally and tilted
        lx = 14 * math.cos(rad)
        ly = 6 * math.sin(rad)
        # Rotate -30 degrees
        rot = math.radians(-30)
        rx = lx * math.cos(rot) - ly * math.sin(rot)
        ry = lx * math.sin(rot) + ly * math.cos(rot)
        leaf_points.append((int(cx + rx), int(cy - 4 + ry)))

    draw.polygon(leaf_points, fill=(50, 170, 60))

    # Leaf vein (center line)
    for i in range(15):
        t = i / 14.0 - 0.5
        lx = t * 26
        ly = t * -10
        px = int(cx + lx)
        py = int(cy - 4 + ly)
        if 0 <= px < WIDTH and 0 <= py < HEIGHT:
            draw.point((px, py), fill=(30, 120, 40))

    # Small veins branching off
    for i in range(3, 12, 3):
        t = i / 14.0 - 0.5
        base_x = int(cx + t * 26)
        base_y = int(cy - 4 + t * -10)
        for j in range(1, 4):
            vx = base_x + j
            vy = base_y - j
            if 0 <= vx < WIDTH and 0 <= vy < HEIGHT:
                draw.point((vx, vy), fill=(35, 130, 45))
            vy2 = base_y + j
            if 0 <= vx < WIDTH and 0 <= vy2 < HEIGHT:
                draw.point((vx, vy2), fill=(35, 130, 45))

    # Text
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # "WHOLE FOODS" text centered
    draw.text((10, 22), "WHOLE", fill=(255, 255, 255), font=font)
    draw.text((10, 31), "FOODS", fill=(220, 220, 220), font=font)

    # "MARKET" smaller at bottom
    draw.text((13, 53), "MARKET", fill=(80, 160, 80), font=font)

    return image


def run(matrix, duration=60):
    """Display the Whole Foods logo."""
    start_time = time.time()
    logo = _draw_logo()

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            matrix.SetImage(logo)
            time.sleep(1)
    except Exception as e:
        logger.error("Error in Whole Foods logo: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
