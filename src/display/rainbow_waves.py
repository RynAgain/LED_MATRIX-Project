#!/usr/bin/env python3
"""Rainbow wave patterns for 64x64 LED matrix."""

import time
import math
import logging
from PIL import Image

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30


def _hsv_to_rgb(h, s, v):
    """Convert HSV (0-1 range) to RGB (0-255 range)."""
    if s == 0:
        r = g = b = int(v * 255)
        return (r, g, b)
    
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


# Different wave patterns
def _diagonal_wave(x, y, t):
    return (x + y) * 0.03 + t * 0.5

def _radial_wave(x, y, t):
    dx = x - 32
    dy = y - 32
    dist = math.sqrt(dx*dx + dy*dy)
    return dist * 0.05 + t * 0.4

def _horizontal_wave(x, y, t):
    return x * 0.04 + math.sin(y * 0.1 + t) * 0.3 + t * 0.3

def _spiral_wave(x, y, t):
    dx = x - 32
    dy = y - 32
    angle = math.atan2(dy, dx)
    dist = math.sqrt(dx*dx + dy*dy)
    return angle / math.pi * 0.5 + dist * 0.03 + t * 0.4


PATTERNS = [_diagonal_wave, _radial_wave, _horizontal_wave, _spiral_wave]


def run(matrix, duration=60):
    """Run rainbow waves for the specified duration."""
    start_time = time.time()
    t = 0
    pattern_idx = 0
    pattern_switch_interval = 15  # Switch pattern every 15 seconds
    
    try:
        while time.time() - start_time < duration:
            frame_start = time.time()
            
            # Switch patterns periodically
            elapsed_total = time.time() - start_time
            pattern_idx = int(elapsed_total / pattern_switch_interval) % len(PATTERNS)
            pattern = PATTERNS[pattern_idx]
            
            image = Image.new("RGB", (WIDTH, HEIGHT))
            pixels = image.load()
            
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    hue = pattern(x, y, t) % 1.0
                    pixels[x, y] = _hsv_to_rgb(hue, 1.0, 1.0)
            
            matrix.SetImage(image)
            
            t += 0.04
            
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    except Exception as e:
        logger.error("Error in rainbow waves: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
