"""
Time Display -- Digital and Analog clock on 64x64 LED matrix.

Features:
- Large digital clock with thick pixel font (each digit ~8x12 pixels)
- Smooth color transitions: colors shift through rainbow over time
- Date displayed below in smaller text
- Colon between hours:minutes blinks (on/off every 0.5s)
- Analog clock mode: circular face with hour/minute/second hands
- Second hand in red, minute in white, hour in yellow
- Clock face with circle of dots for hour markers
- Alternates between digital and analog every 30 seconds
"""

import logging
import time
import math
from datetime import datetime
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 15
FRAME_DUR = 1.0 / FPS
BG_COLOR = (0, 0, 0)

# Analog clock colors
SECOND_HAND_COLOR = (220, 30, 30)    # red
MINUTE_HAND_COLOR = (240, 240, 240)  # white
HOUR_HAND_COLOR = (255, 220, 50)     # yellow
FACE_DOT_COLOR = (60, 60, 100)       # dim dots for hour markers
FACE_DOT_12 = (120, 120, 180)       # brighter dot for 12 o'clock
CENTER_DOT = (200, 200, 200)         # center point

# Large 8x12 digit bitmaps for digital clock
# Each digit is represented as 12 rows of 8-bit patterns
LARGE_DIGITS = {
    '0': [
        0b01111100,
        0b11111110,
        0b11000110,
        0b11000110,
        0b11000110,
        0b11000110,
        0b11000110,
        0b11000110,
        0b11000110,
        0b11000110,
        0b11111110,
        0b01111100,
    ],
    '1': [
        0b00011000,
        0b00111000,
        0b01111000,
        0b00011000,
        0b00011000,
        0b00011000,
        0b00011000,
        0b00011000,
        0b00011000,
        0b00011000,
        0b01111110,
        0b01111110,
    ],
    '2': [
        0b01111100,
        0b11111110,
        0b11000110,
        0b00000110,
        0b00001100,
        0b00011000,
        0b00110000,
        0b01100000,
        0b11000000,
        0b11000110,
        0b11111110,
        0b11111110,
    ],
    '3': [
        0b01111100,
        0b11111110,
        0b11000110,
        0b00000110,
        0b00000110,
        0b00111100,
        0b00111100,
        0b00000110,
        0b00000110,
        0b11000110,
        0b11111110,
        0b01111100,
    ],
    '4': [
        0b00001100,
        0b00011100,
        0b00111100,
        0b01101100,
        0b11001100,
        0b11001100,
        0b11111110,
        0b11111110,
        0b00001100,
        0b00001100,
        0b00001100,
        0b00001100,
    ],
    '5': [
        0b11111110,
        0b11111110,
        0b11000000,
        0b11000000,
        0b11111100,
        0b11111110,
        0b00000110,
        0b00000110,
        0b00000110,
        0b11000110,
        0b11111110,
        0b01111100,
    ],
    '6': [
        0b01111100,
        0b11111110,
        0b11000110,
        0b11000000,
        0b11000000,
        0b11111100,
        0b11111110,
        0b11000110,
        0b11000110,
        0b11000110,
        0b11111110,
        0b01111100,
    ],
    '7': [
        0b11111110,
        0b11111110,
        0b11000110,
        0b00000110,
        0b00001100,
        0b00001100,
        0b00011000,
        0b00011000,
        0b00110000,
        0b00110000,
        0b00110000,
        0b00110000,
    ],
    '8': [
        0b01111100,
        0b11111110,
        0b11000110,
        0b11000110,
        0b11000110,
        0b01111100,
        0b01111100,
        0b11000110,
        0b11000110,
        0b11000110,
        0b11111110,
        0b01111100,
    ],
    '9': [
        0b01111100,
        0b11111110,
        0b11000110,
        0b11000110,
        0b11000110,
        0b11111110,
        0b01111110,
        0b00000110,
        0b00000110,
        0b11000110,
        0b11111110,
        0b01111100,
    ],
}

# Small 3x5 digit font for date display
SMALL_DIGITS = {
    '0': [0b111, 0b101, 0b101, 0b101, 0b111],
    '1': [0b010, 0b110, 0b010, 0b010, 0b111],
    '2': [0b111, 0b001, 0b111, 0b100, 0b111],
    '3': [0b111, 0b001, 0b111, 0b001, 0b111],
    '4': [0b101, 0b101, 0b111, 0b001, 0b001],
    '5': [0b111, 0b100, 0b111, 0b001, 0b111],
    '6': [0b111, 0b100, 0b111, 0b101, 0b111],
    '7': [0b111, 0b001, 0b010, 0b010, 0b010],
    '8': [0b111, 0b101, 0b111, 0b101, 0b111],
    '9': [0b111, 0b101, 0b111, 0b001, 0b111],
    '-': [0b000, 0b000, 0b111, 0b000, 0b000],
    '/': [0b001, 0b001, 0b010, 0b100, 0b100],
    ' ': [0b000, 0b000, 0b000, 0b000, 0b000],
}

# Small 3x5 letter bitmaps for day-of-week abbreviations
SMALL_LETTERS = {
    'M': [0b101, 0b111, 0b111, 0b101, 0b101],
    'T': [0b111, 0b010, 0b010, 0b010, 0b010],
    'W': [0b101, 0b101, 0b111, 0b111, 0b101],
    'F': [0b111, 0b100, 0b111, 0b100, 0b100],
    'S': [0b111, 0b100, 0b111, 0b001, 0b111],
    'o': [0b000, 0b111, 0b101, 0b101, 0b111],
    'u': [0b000, 0b101, 0b101, 0b101, 0b111],
    'e': [0b000, 0b111, 0b111, 0b100, 0b111],
    'h': [0b100, 0b100, 0b111, 0b101, 0b101],
    'r': [0b000, 0b111, 0b100, 0b100, 0b100],
    'i': [0b010, 0b000, 0b010, 0b010, 0b010],
    'a': [0b000, 0b111, 0b001, 0b111, 0b111],
    't': [0b010, 0b111, 0b010, 0b010, 0b011],
    'n': [0b000, 0b111, 0b101, 0b101, 0b101],
    'd': [0b001, 0b001, 0b111, 0b101, 0b111],
}

DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _hsv_to_rgb(h, s, v):
    """Convert HSV (h: 0-360, s: 0-1, v: 0-1) to RGB tuple."""
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c

    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))


def _draw_large_digit(image, digit_char, x, y, color):
    """Draw an 8x12 pixel digit at position (x, y)."""
    rows = LARGE_DIGITS.get(digit_char)
    if rows is None:
        return
    for row_idx, bits in enumerate(rows):
        for col_idx in range(8):
            if bits & (1 << (7 - col_idx)):
                px = x + col_idx
                py = y + row_idx
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    image.putpixel((px, py), color)


def _draw_small_char(image, char, x, y, color):
    """Draw a 3x5 pixel character at position (x, y)."""
    lookup = SMALL_DIGITS if char in SMALL_DIGITS else SMALL_LETTERS
    rows = lookup.get(char)
    if rows is None:
        return
    for row_idx, bits in enumerate(rows):
        for col_idx in range(3):
            if bits & (1 << (2 - col_idx)):
                px = x + col_idx
                py = y + row_idx
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    image.putpixel((px, py), color)


def _draw_small_string(image, text, x, y, color):
    """Draw a string using small 3x5 font."""
    for i, ch in enumerate(text):
        _draw_small_char(image, ch, x + i * 4, y, color)


def _draw_colon(image, x, y, color):
    """Draw blinking colon (two 2x2 dots)."""
    for dx in range(2):
        for dy in range(2):
            # Upper dot
            px1, py1 = x + dx, y + 3 + dy
            if 0 <= px1 < SIZE and 0 <= py1 < SIZE:
                image.putpixel((px1, py1), color)
            # Lower dot
            px2, py2 = x + dx, y + 8 + dy
            if 0 <= px2 < SIZE and 0 <= py2 < SIZE:
                image.putpixel((px2, py2), color)


def _draw_digital_clock(matrix, now, hue_offset):
    """Draw the digital clock display."""
    image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)

    hours = now.strftime("%H")
    minutes = now.strftime("%M")

    # Rainbow color based on time
    color = _hsv_to_rgb(hue_offset % 360, 0.9, 1.0)
    color2 = _hsv_to_rgb((hue_offset + 60) % 360, 0.9, 1.0)
    date_color = _hsv_to_rgb((hue_offset + 120) % 360, 0.7, 0.6)

    # Center the time display: 2 digits + colon + 2 digits
    # Each digit 8px wide + 1px gap = 9px, colon 4px
    # Total: 9 + 9 + 4 + 9 + 9 = 40px, centered in 64 = offset 12
    start_x = 3
    digit_y = 10

    # Hours
    _draw_large_digit(image, hours[0], start_x, digit_y, color)
    _draw_large_digit(image, hours[1], start_x + 10, digit_y, color)

    # Blinking colon (on/off every 0.5s)
    if now.microsecond < 500000:
        _draw_colon(image, start_x + 21, digit_y, color2)

    # Minutes
    _draw_large_digit(image, minutes[0], start_x + 26, digit_y, color)
    _draw_large_digit(image, minutes[1], start_x + 36, digit_y, color)

    # Seconds in smaller font at right
    seconds = now.strftime("%S")
    sec_color = _hsv_to_rgb((hue_offset + 180) % 360, 0.8, 0.7)
    _draw_small_string(image, seconds, start_x + 48, digit_y + 7, sec_color)

    # Date below
    date_str = now.strftime("%m/%d")
    _draw_small_string(image, date_str, 12, 30, date_color)

    # Day of week
    day_name = DAY_NAMES[now.weekday()]
    day_color = _hsv_to_rgb((hue_offset + 90) % 360, 0.6, 0.5)
    _draw_small_string(image, day_name, 32, 30, day_color)

    # Year in small text
    year_str = now.strftime("%Y")
    year_color = _hsv_to_rgb((hue_offset + 150) % 360, 0.5, 0.35)
    _draw_small_string(image, year_str, 16, 38, year_color)

    # Decorative line at bottom that shifts with hue
    for x in range(SIZE):
        line_hue = (hue_offset + x * 5) % 360
        line_color = _hsv_to_rgb(line_hue, 0.8, 0.3)
        image.putpixel((x, 50), line_color)
        image.putpixel((x, 51), line_color)

    matrix.SetImage(image)


def _draw_analog_clock(matrix, now, hue_offset):
    """Draw the analog clock display."""
    image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
    draw = ImageDraw.Draw(image)

    cx, cy = SIZE // 2, SIZE // 2
    clock_radius = 28

    # Draw hour markers (12 dots around the circle)
    for h in range(12):
        angle = math.radians(h * 30 - 90)  # 0=12 o'clock
        mx = cx + int(clock_radius * math.cos(angle))
        my = cy + int(clock_radius * math.sin(angle))
        dot_color = FACE_DOT_12 if h == 0 else FACE_DOT_COLOR
        # Draw 2x2 dot for 12, 3, 6, 9; 1x1 for others
        if h % 3 == 0:
            for dx in range(2):
                for dy in range(2):
                    px, py = mx + dx - 1, my + dy - 1
                    if 0 <= px < SIZE and 0 <= py < SIZE:
                        image.putpixel((px, py), dot_color)
        else:
            if 0 <= mx < SIZE and 0 <= my < SIZE:
                image.putpixel((mx, my), dot_color)

    # Get time components
    hours = now.hour % 12
    minutes = now.minute
    seconds = now.second
    microseconds = now.microsecond

    # Calculate angles (smooth movement)
    second_angle = math.radians((seconds + microseconds / 1e6) * 6 - 90)
    minute_angle = math.radians((minutes + seconds / 60.0) * 6 - 90)
    hour_angle = math.radians((hours + minutes / 60.0) * 30 - 90)

    # Draw hour hand (thick, short)
    hour_len = 14
    hx = cx + int(hour_len * math.cos(hour_angle))
    hy = cy + int(hour_len * math.sin(hour_angle))
    draw.line([(cx, cy), (hx, hy)], fill=HOUR_HAND_COLOR, width=3)

    # Draw minute hand (medium, longer)
    minute_len = 20
    minx = cx + int(minute_len * math.cos(minute_angle))
    miny = cy + int(minute_len * math.sin(minute_angle))
    draw.line([(cx, cy), (minx, miny)], fill=MINUTE_HAND_COLOR, width=2)

    # Draw second hand (thin, longest)
    second_len = 24
    sx = cx + int(second_len * math.cos(second_angle))
    sy = cy + int(second_len * math.sin(second_angle))
    draw.line([(cx, cy), (sx, sy)], fill=SECOND_HAND_COLOR, width=1)

    # Center dot
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            px, py = cx + dx, cy + dy
            if 0 <= px < SIZE and 0 <= py < SIZE:
                image.putpixel((px, py), CENTER_DOT)

    # Draw subtle outer ring with rainbow shift
    for angle_deg in range(0, 360, 3):
        angle = math.radians(angle_deg)
        ring_r = clock_radius + 2
        rx = cx + int(ring_r * math.cos(angle))
        ry = cy + int(ring_r * math.sin(angle))
        ring_color = _hsv_to_rgb((hue_offset + angle_deg) % 360, 0.6, 0.25)
        if 0 <= rx < SIZE and 0 <= ry < SIZE:
            image.putpixel((rx, ry), ring_color)

    # Digital time in small text at bottom
    time_str = now.strftime("%H") + now.strftime("%M")
    time_color = _hsv_to_rgb(hue_offset % 360, 0.5, 0.4)
    # Just show HH:MM small at bottom
    _draw_small_string(image, now.strftime("%H"), 22, 57, time_color)
    # Colon
    if now.microsecond < 500000:
        image.putpixel((30, 58), time_color)
        image.putpixel((30, 60), time_color)
    _draw_small_string(image, now.strftime("%M"), 32, 57, time_color)

    matrix.SetImage(image)


def _draw_binary_clock(matrix, now, hue_offset):
    """Draw a binary clock display.
    
    Each column represents a digit of HH:MM:SS.
    Each row represents a bit (1, 2, 4, 8 from bottom to top).
    Lit bits are colored, unlit bits are dim.
    """
    image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
    draw = ImageDraw.Draw(image)

    h, m, s = now.hour, now.minute, now.second
    # Split into individual digits: H1 H2 : M1 M2 : S1 S2
    digits = [h // 10, h % 10, m // 10, m % 10, s // 10, s % 10]
    max_bits = [2, 9, 5, 9, 5, 9]  # Max value per digit position

    # Column positions for 6 digits with separators
    col_positions = [6, 14, 28, 36, 50, 58]
    bit_size = 6
    start_y = 10
    row_spacing = 12

    # Labels at top
    r, g, b = _hsv_to_rgb(hue_offset / 360.0, 0.6, 0.8)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((4, 1), "H", fill=(r, g, b), font=font)
    draw.text((30, 1), "M", fill=(r, g, b), font=font)
    draw.text((52, 1), "S", fill=(r, g, b), font=font)

    for col_idx, (digit, max_val) in enumerate(zip(digits, max_bits)):
        cx = col_positions[col_idx]
        num_bits = 4 if max_val > 7 else (3 if max_val > 3 else 2)

        for bit in range(num_bits):
            by = start_y + (3 - bit) * row_spacing
            is_set = (digit >> bit) & 1

            if is_set:
                # Lit bit - colored
                hue = ((hue_offset + col_idx * 40 + bit * 20) % 360) / 360.0
                r, g, b = _hsv_to_rgb(hue, 1.0, 1.0)
                draw.rectangle([cx, by, cx + bit_size, by + bit_size], fill=(r, g, b))
            else:
                # Unlit bit - very dim
                draw.rectangle([cx, by, cx + bit_size, by + bit_size], fill=(20, 20, 30))

    # Separator dots
    draw.rectangle([22, 24, 24, 26], fill=(80, 80, 100))
    draw.rectangle([22, 36, 24, 38], fill=(80, 80, 100))
    draw.rectangle([44, 24, 46, 26], fill=(80, 80, 100))
    draw.rectangle([44, 36, 46, 38], fill=(80, 80, 100))

    matrix.SetImage(image)


# Clock modes: 0=digital, 1=analog, 2=binary
CLOCK_MODES = ["digital", "analog", "binary"]


def run(matrix, duration=60):
    """Run the Time Display feature for the specified duration.

    Cycles through digital, analog, and binary clock every 20 seconds.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    start_time = time.time()
    deadline = start_time + duration
    hue_offset = 0.0
    mode_switch_interval = 20  # seconds between mode switches
    mode_idx = 0

    try:
        last_mode_switch = start_time

        while time.time() < deadline:
            frame_start = time.time()
            now = datetime.now()

            # Check if it's time to switch modes
            if frame_start - last_mode_switch >= mode_switch_interval:
                mode_idx = (mode_idx + 1) % len(CLOCK_MODES)
                last_mode_switch = frame_start

            # Gradually shift hue (full rainbow cycle every ~60 seconds)
            hue_offset = ((frame_start - start_time) * 6) % 360

            mode = CLOCK_MODES[mode_idx]
            if mode == "digital":
                _draw_digital_clock(matrix, now, hue_offset)
            elif mode == "analog":
                _draw_analog_clock(matrix, now, hue_offset)
            else:
                _draw_binary_clock(matrix, now, hue_offset)

            # Frame timing
            elapsed = time.time() - frame_start
            sleep_time = FRAME_DUR - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in time_display: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
