#!/usr/bin/env python3
"""Lava lamp / metaball effect for 64x64 LED matrix."""

import time
import math
import random
import logging
from PIL import Image
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 20  # 20 FPS for smooth blobs
NUM_BLOBS = 6


class Blob:
    def __init__(self):
        self.x = random.uniform(10, WIDTH - 10)
        self.y = random.uniform(10, HEIGHT - 10)
        self.vx = random.uniform(-0.5, 0.5)
        self.vy = random.uniform(-0.5, 0.5)
        self.radius = random.uniform(8, 15)
        self.hue = random.uniform(0, 1)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        # Bounce off edges
        if self.x < 5 or self.x > WIDTH - 5:
            self.vx *= -1
            self.x = max(5, min(WIDTH - 5, self.x))
        if self.y < 5 or self.y > HEIGHT - 5:
            self.vy *= -1
            self.y = max(5, min(HEIGHT - 5, self.y))
        # Slow drift in direction
        self.vx += random.uniform(-0.02, 0.02)
        self.vy += random.uniform(-0.02, 0.02)
        self.vx = max(-0.8, min(0.8, self.vx))
        self.vy = max(-0.8, min(0.8, self.vy))
        # Slowly shift hue
        self.hue = (self.hue + 0.001) % 1.0


def _hsv_to_rgb(h, s=1.0, v=1.0):
    if s == 0:
        c = int(v * 255)
        return (c, c, c)
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


def run(matrix, duration=60):
    """Run the lava lamp effect."""
    start_time = time.time()
    blobs = [Blob() for _ in range(NUM_BLOBS)]
    threshold = 1.0  # Metaball threshold

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()

            # Update blob positions
            for blob in blobs:
                blob.update()

            image = Image.new("RGB", (WIDTH, HEIGHT), (5, 2, 10))
            pixels = image.load()

            for y in range(HEIGHT):
                for x in range(WIDTH):
                    # Calculate metaball field value
                    total = 0
                    weighted_hue = 0
                    for blob in blobs:
                        dx = x - blob.x
                        dy = y - blob.y
                        dist_sq = dx * dx + dy * dy + 1
                        influence = (blob.radius * blob.radius) / dist_sq
                        total += influence
                        weighted_hue += influence * blob.hue

                    if total > threshold:
                        # Inside a metaball - color it
                        avg_hue = weighted_hue / total
                        # Brightness based on field strength
                        brightness = min(1.0, (total - threshold) * 2)
                        r, g, b = _hsv_to_rgb(avg_hue, 0.8, brightness)
                        pixels[x, y] = (r, g, b)
                    elif total > threshold * 0.7:
                        # Edge glow
                        avg_hue = weighted_hue / total
                        edge_bright = (total - threshold * 0.7) / (threshold * 0.3) * 0.3
                        r, g, b = _hsv_to_rgb(avg_hue, 0.6, edge_bright)
                        pixels[x, y] = (r, g, b)

            matrix.SetImage(image)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in lava lamp: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
