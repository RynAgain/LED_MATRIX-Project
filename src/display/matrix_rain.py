#!/usr/bin/env python3
"""Matrix digital rain effect for 64x64 LED matrix."""

import time
import random
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 15  # Slightly slower for readability

# Characters to use (katakana-inspired, but using ASCII for compatibility)
CHARS = "ABCDEFGHJKLMNPRSTUVWXYZabcdefghjkmnprstuvwxyz0123456789!@#$%&*=+<>"


class Drop:
    """A single falling column of characters."""
    
    def __init__(self, x):
        self.x = x
        self.reset()
    
    def reset(self):
        self.y = random.randint(-20, -1)
        self.speed = random.uniform(0.3, 1.0)
        self.length = random.randint(5, 20)
        self.chars = [random.choice(CHARS) for _ in range(self.length)]
    
    def update(self):
        self.y += self.speed
        # Randomly mutate characters
        if random.random() > 0.8:
            idx = random.randint(0, self.length - 1)
            self.chars[idx] = random.choice(CHARS)
        if self.y - self.length > HEIGHT:
            self.reset()


def run(matrix, duration=60):
    """Run the matrix rain effect for the specified duration."""
    start_time = time.time()
    
    # Create drops across the width (one per ~4 pixels for char spacing)
    columns = range(0, WIDTH, 4)
    drops = [Drop(x) for x in columns]
    # Add extra drops for density
    drops.extend([Drop(x + 2) for x in columns[:len(columns)//2]])
    
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    
    try:
        while time.time() - start_time < duration:
            frame_start = time.time()
            
            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
            draw = ImageDraw.Draw(image)
            
            for drop in drops:
                drop.update()
                
                for i, char in enumerate(drop.chars):
                    cy = int(drop.y) - i
                    if 0 <= cy < HEIGHT:
                        if i == 0:
                            # Head of the drop is bright white-green
                            color = (200, 255, 200)
                        elif i < 3:
                            # Near head is bright green
                            brightness = 255 - i * 30
                            color = (0, brightness, 0)
                        else:
                            # Tail fades
                            fade = max(40, 200 - i * 15)
                            color = (0, fade, 0)
                        
                        draw.text((drop.x, cy), char, fill=color, font=font)
            
            matrix.SetImage(image)
            
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    except Exception as e:
        logger.error("Error in matrix rain: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
