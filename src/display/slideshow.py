#!/usr/bin/env python3
"""Image slideshow for 64x64 LED matrix. Shows uploaded images from config/images/."""

import time
import os
import logging
from PIL import Image
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMAGES_DIR = os.path.join(PROJECT_ROOT, "config", "images")


def _get_image_paths():
    """Return sorted list of image file paths from the images directory."""
    paths = []
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR, exist_ok=True)
        return paths

    for fname in sorted(os.listdir(IMAGES_DIR)):
        if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            paths.append(os.path.join(IMAGES_DIR, fname))

    return paths


def _load_single_image(path):
    """Load and resize a single image. Returns (filename, image) or None on failure."""
    try:
        img = Image.open(path).convert("RGB")
        img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
        return (os.path.basename(path), img)
    except Exception as e:
        logger.warning("Failed to load image %s: %s", path, e)
        return None


def run(matrix, duration=60):
    """Run the image slideshow."""
    start_time = time.time()
    image_paths = _get_image_paths()

    if not image_paths:
        # No images - show a placeholder
        img = Image.new("RGB", (WIDTH, HEIGHT), (10, 10, 20))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.text((4, 25), "No images", fill=(100, 100, 100))
        draw.text((2, 37), "Upload via", fill=(80, 80, 80))
        draw.text((6, 49), "web panel", fill=(80, 80, 80))

        while time.time() - start_time < duration:
            if should_stop():
                break
            matrix.SetImage(img)
            time.sleep(1)
        return

    idx = 0
    show_time = max(5, duration // max(len(image_paths), 1))  # Time per image
    current_img = None

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break

            # Lazy load: load one image at a time
            path = image_paths[idx % len(image_paths)]
            result = _load_single_image(path)
            if result is not None:
                # Release previous image reference
                current_img = None
                fname, current_img = result
                logger.info("Showing image: %s", fname)
                matrix.SetImage(current_img)
            else:
                # Skip failed images
                idx += 1
                continue

            # Hold image for show_time seconds
            img_start = time.time()
            while time.time() - img_start < show_time and time.time() - start_time < duration:
                if should_stop():
                    break
                time.sleep(0.5)

            idx += 1

    except Exception as e:
        logger.error("Error in slideshow: %s", e, exc_info=True)
    finally:
        current_img = None  # Release last image
        try:
            matrix.Clear()
        except Exception:
            pass
