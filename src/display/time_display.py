import logging
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont


def display_time_and_date(matrix, end_time=None):
    """Display the current time and date on the LED matrix."""
    if end_time is None:
        end_time = time.time() + 60  # Display for 1 minute
    while time.time() < end_time:
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        current_date = now.strftime("%Y-%m-%d")
        
        image = Image.new("RGB", (64, 64))
        draw = ImageDraw.Draw(image)
        
        # Load a custom font
        try:
            font = ImageFont.truetype("arial.ttf", 10)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw time with a gradient color
        for i, char in enumerate(current_time):
            draw.text((i * 10, 0), char, font=font, fill=(255 - i * 20, 100 + i * 15, 150))
        
        # Draw date with a different color
        draw.text((0, 32), current_date, font=font, fill=(0, 255, 255))
        
        matrix.SetImage(image)
        time.sleep(1)

def display_binary_clock(matrix, end_time=None):
    """Display the current time in binary format on the LED matrix."""
    if end_time is None:
        end_time = time.time() + 60  # Display for 1 minute
    while time.time() < end_time:
        now = datetime.now()
        hours = now.hour
        minutes = now.minute
        seconds = now.second
        
        # Convert time to binary
        binary_time = [
            f"{hours:06b}",
            f"{minutes:06b}",
            f"{seconds:06b}"
        ]
        
        image = Image.new("RGB", (64, 64))
        draw = ImageDraw.Draw(image)
        
        # Draw binary time
        for row, binary in enumerate(binary_time):
            for col, bit in enumerate(binary):
                color = (0, 255, 0) if bit == '1' else (0, 0, 0)
                draw.rectangle((col * 10, row * 20, col * 10 + 9, row * 20 + 19), fill=color)
        
        matrix.SetImage(image)
        time.sleep(1)


def run(matrix, duration=60):
    """Run the Time Display feature for the specified duration.

    Alternates between the standard time/date display and the binary clock,
    splitting the duration roughly in half.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    logger = logging.getLogger(__name__)
    start_time = time.time()
    deadline = start_time + duration
    try:
        while time.time() < deadline:
            half = min((deadline - time.time()) / 2, 30)
            if half <= 0:
                break
            display_time_and_date(matrix, end_time=time.time() + half)
            if time.time() >= deadline:
                break
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            display_binary_clock(matrix, end_time=time.time() + min(remaining, 30))
    except Exception as e:
        logger.error("Error in time_display: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
