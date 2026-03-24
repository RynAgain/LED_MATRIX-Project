#!/usr/bin/env python3
"""3D starfield / warp tunnel effect for 64x64 LED matrix."""

import time
import random
import math
import logging
from PIL import Image
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
CENTER_X, CENTER_Y = WIDTH // 2, HEIGHT // 2
NUM_STARS = 150
FRAME_INTERVAL = 1.0 / 30


class Star:
    """A star in 3D space projected to 2D."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.x = random.uniform(-1, 1)
        self.y = random.uniform(-1, 1)
        self.z = random.uniform(0.1, 1.0)
        self.prev_sx = None
        self.prev_sy = None
    
    def update(self, speed=0.01):
        self.z -= speed
        if self.z <= 0.01:
            self.reset()
            self.z = 1.0
    
    def project(self):
        """Project 3D position to 2D screen coordinates."""
        sx = int(CENTER_X + (self.x / self.z) * CENTER_X)
        sy = int(CENTER_Y + (self.y / self.z) * CENTER_Y)
        return sx, sy
    
    def brightness(self):
        """Closer stars are brighter."""
        return max(50, min(255, int((1.0 - self.z) * 255)))


def run(matrix, duration=60):
    """Run the starfield effect for the specified duration."""
    start_time = time.time()
    stars = [Star() for _ in range(NUM_STARS)]
    speed = 0.015
    
    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            
            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 5))  # Very dark blue
            pixels = image.load()
            
            for star in stars:
                old_sx, old_sy = star.project()
                star.update(speed)
                sx, sy = star.project()
                
                if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                    b = star.brightness()
                    # Draw the star as a bright pixel
                    pixels[sx, sy] = (b, b, b)
                    
                    # Draw a streak for fast-moving close stars
                    if star.z < 0.3 and 0 <= old_sx < WIDTH and 0 <= old_sy < HEIGHT:
                        # Simple line between old and new position
                        streak_b = b // 3
                        mid_x = (sx + old_sx) // 2
                        mid_y = (sy + old_sy) // 2
                        if 0 <= mid_x < WIDTH and 0 <= mid_y < HEIGHT:
                            pixels[mid_x, mid_y] = (streak_b, streak_b, streak_b)
            
            matrix.SetImage(image)
            
            # Slightly vary speed for interest
            t = time.time() - start_time
            speed = 0.015 + 0.005 * math.sin(t * 0.5)
            
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    except Exception as e:
        logger.error("Error in starfield: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
