#!/usr/bin/env python3
"""Image slideshow for 64x64 LED matrix. Shows uploaded images from config/images/."""

import time
import os
import logging
from PIL import Image

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMAGES_DIR = os.path.join(PROJECT_ROOT, "config", "images")


def _load_images():
    """Load all images from the images directory."""
    images = []
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR, exist_ok=True)
        return images
    
    for fname in sorted(os.listdir(IMAGES_DIR)):
        if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            path = os.path.join(IMAGES_DIR, fname)
            try:
                img = Image.open(path).convert("RGB")
                img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
                images.append((fname, img))
            except Exception as e:
                logger.warning("Failed to load image %s: %s", fname, e)
    
    return images


def run(matrix, duration=60):
    """Run the image slideshow."""
    start_time = time.time()
    images = _load_images()
    
    if not images:
        # No images - show a placeholder
        img = Image.new("RGB", (WIDTH, HEIGHT), (10, 10, 20))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.text((4, 25), "No images", fill=(100, 100, 100))
        draw.text((2, 37), "Upload via", fill=(80, 80, 80))
        draw.text((6, 49), "web panel", fill=(80, 80, 80))
        
        while time.time() - start_time < duration:
            matrix.SetImage(img)
            time.sleep(1)
        return
    
    idx = 0
    show_time = max(5, duration // max(len(images), 1))  # Time per image
    
    try:
        while time.time() - start_time < duration:
            fname, img = images[idx % len(images)]
            logger.info("Showing image: %s", fname)
            
            matrix.SetImage(img)
            
            # Hold image for show_time seconds
            img_start = time.time()
            while time.time() - img_start < show_time and time.time() - start_time < duration:
                time.sleep(0.5)
            
            idx += 1
    
    except Exception as e:
        logger.error("Error in slideshow: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
