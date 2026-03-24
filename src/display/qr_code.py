#!/usr/bin/env python3
"""QR code display for 64x64 LED matrix."""

import time
import json
import os
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QR_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "qr.json")


def _load_qr_config():
    try:
        with open(QR_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"content": "https://github.com/RynAgain/LED_MATRIX-Project", "label": "Scan Me"}


def _generate_qr_image(content, size=64):
    """Generate a QR code as a PIL Image.
    
    Uses a simple QR-like pattern if the qrcode library isn't available.
    If qrcode is installed, generates a real QR code.
    """
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(content)
        qr.make(fit=True)
        
        # Generate with custom colors
        img = qr.make_image(fill_color="white", back_color="black")
        img = img.convert("RGB")
        
        # Resize to fit matrix (with padding)
        qr_size = min(size - 4, size - 4)
        img = img.resize((qr_size, qr_size), Image.NEAREST)
        
        # Center on black background
        final = Image.new("RGB", (size, size), (0, 0, 0))
        offset = (size - qr_size) // 2
        final.paste(img, (offset, offset))
        return final
        
    except ImportError:
        # No qrcode library - draw a placeholder pattern
        logger.warning("qrcode library not installed. Install with: pip install qrcode")
        img = Image.new("RGB", (size, size), (0, 0, 10))
        draw = ImageDraw.Draw(img)
        
        # Draw finder patterns (the three corner squares of a QR code)
        def draw_finder(x, y, s=7):
            # Outer
            draw.rectangle([x, y, x + s - 1, y + s - 1], outline=(255, 255, 255))
            # Middle
            draw.rectangle([x + 1, y + 1, x + s - 2, y + s - 2], outline=(0, 0, 0))
            # Inner
            draw.rectangle([x + 2, y + 2, x + s - 3, y + s - 3], fill=(255, 255, 255))
        
        # Three finder patterns
        draw_finder(4, 4)
        draw_finder(size - 11, 4)
        draw_finder(4, size - 11)
        
        # Random data dots to look QR-like
        import random
        random.seed(hash(content))
        for dy in range(14, size - 4):
            for dx in range(14, size - 4):
                if random.random() > 0.5:
                    draw.point((dx, dy), fill=(255, 255, 255))
        
        # Label
        try:
            from PIL import ImageFont
            font = ImageFont.load_default()
            draw.text((size // 2 - 15, size - 8), "QR", fill=(100, 100, 150), font=font)
        except Exception:
            pass
        
        return img


def run(matrix, duration=60):
    """Run the QR code display."""
    start_time = time.time()
    config = _load_qr_config()
    content = config.get("content", "Hello World")
    label = config.get("label", "")
    
    try:
        # Generate QR code image
        if label:
            # Leave space at bottom for label
            qr_img = _generate_qr_image(content, size=56)
            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
            image.paste(qr_img, (4, 0))
            draw = ImageDraw.Draw(image)
            try:
                from PIL import ImageFont
                font = ImageFont.load_default()
            except Exception:
                font = None
            # Center label at bottom
            short_label = label[:10]
            tx = (WIDTH - len(short_label) * 6) // 2
            draw.text((tx, 57), short_label, fill=(0, 200, 100), font=font)
        else:
            image = _generate_qr_image(content, size=64)
        
        # Display (static image, just hold it)
        while time.time() - start_time < duration:
            if should_stop():
                break
            matrix.SetImage(image)
            time.sleep(1)
    
    except Exception as e:
        logger.error("Error in QR code display: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
