#!/usr/bin/env python3
"""Fire effect simulation for 64x64 LED matrix."""

import time
import random
import logging
from PIL import Image
from src.display._shared import should_stop

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
            if should_stop():
                break
            frame_start = time.time()
            
            # Seed bottom row with random hot values
            for x in range(WIDTH):
                heat[HEIGHT][x] = random.randint(160, 255) if random.random() > 0.3 else random.randint(0, 100)
            
            # Propagate heat upward (pre-generate cooling per row to cut
            # 4096 random.uniform calls down to 64 random.choices calls)
            for y in range(0, HEIGHT):
                cool_row = [random.uniform(0.5, 3.0) for _ in range(WIDTH)]
                row_below = heat[y + 1]
                row_below2 = heat[min(y + 2, HEIGHT)]
                row_out = heat[y]
                for x in range(WIDTH):
                    left = row_below[(x - 1) % WIDTH]
                    center = row_below[x]
                    right = row_below[(x + 1) % WIDTH]
                    below = row_below2[x]
                    avg = (left + center + right + below) * 0.25
                    row_out[x] = max(0, min(255, int(avg - cool_row[x])))
            
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
