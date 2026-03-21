#!/usr/bin/env python3
"""Fire effect simulation for 64x64 LED matrix."""

import time
import random
import logging
from PIL import Image

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30

# Fire color palette (256 entries: black -> red -> orange -> yellow -> white)
def _build_palette():
    palette = []
    for i in range(256):
        if i < 64:
            r = i * 4
            g = 0
            b = 0
        elif i < 128:
            r = 255
            g = (i - 64) * 4
            b = 0
        elif i < 192:
            r = 255
            g = 255
            b = (i - 128) * 4
        else:
            r = 255
            g = 255
            b = 255
        palette.append((min(r, 255), min(g, 255), min(b, 255)))
    return palette

PALETTE = _build_palette()


def run(matrix, duration=60):
    """Run the fire effect for the specified duration."""
    start_time = time.time()
    
    # Heat buffer (extra row at bottom for seeding)
    heat = [[0] * WIDTH for _ in range(HEIGHT + 1)]
    
    try:
        while time.time() - start_time < duration:
            frame_start = time.time()
            
            # Seed bottom row with random hot values
            for x in range(WIDTH):
                heat[HEIGHT][x] = random.randint(160, 255) if random.random() > 0.3 else random.randint(0, 100)
            
            # Propagate heat upward
            for y in range(0, HEIGHT):
                for x in range(WIDTH):
                    # Average of surrounding pixels from row below
                    left = heat[y + 1][(x - 1) % WIDTH]
                    center = heat[y + 1][x]
                    right = heat[y + 1][(x + 1) % WIDTH]
                    below = heat[min(y + 2, HEIGHT)][x] if y + 2 <= HEIGHT else center
                    
                    avg = (left + center + right + below) / 4.0
                    # Cool as it rises
                    cooling = random.uniform(0.5, 3.0)
                    heat[y][x] = max(0, min(255, int(avg - cooling)))
            
            # Render to image
            image = Image.new("RGB", (WIDTH, HEIGHT))
            pixels = image.load()
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    idx = min(255, max(0, heat[y][x]))
                    pixels[x, y] = PALETTE[idx]
            
            matrix.SetImage(image)
            
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    except Exception as e:
        logger.error("Error in fire effect: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
