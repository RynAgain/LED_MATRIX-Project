#!/usr/bin/env python3
"""Plasma color-cycling effect for 64x64 LED matrix."""

import time
import math
import logging
from PIL import Image
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30


def _plasma_color(value):
    """Convert a plasma value (0-1) to RGB using smooth color cycling."""
    r = int((math.sin(value * 2 * math.pi) * 0.5 + 0.5) * 255)
    g = int((math.sin(value * 2 * math.pi + 2.094) * 0.5 + 0.5) * 255)
    b = int((math.sin(value * 2 * math.pi + 4.189) * 0.5 + 0.5) * 255)
    return (r, g, b)


def run(matrix, duration=60):
    """Run the plasma effect for the specified duration."""
    start_time = time.time()
    t = 0
    
    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            
            image = Image.new("RGB", (WIDTH, HEIGHT))
            pixels = image.load()
            
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    # Multiple overlapping sine waves create plasma
                    v1 = math.sin(x * 0.1 + t)
                    v2 = math.sin(y * 0.1 + t * 0.7)
                    v3 = math.sin((x + y) * 0.1 + t * 0.5)
                    v4 = math.sin(math.sqrt((x - 32)**2 + (y - 32)**2) * 0.15 + t * 1.2)
                    
                    value = (v1 + v2 + v3 + v4) / 4.0  # -1 to 1
                    value = (value + 1) / 2.0  # 0 to 1
                    
                    pixels[x, y] = _plasma_color(value)
            
            matrix.SetImage(image)
            
            t += 0.05
            
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    except Exception as e:
        logger.error("Error in plasma effect: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
