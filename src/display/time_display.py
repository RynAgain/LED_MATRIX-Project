"""
Time Display -- Digital and Analog clock on 64x64 LED matrix.

Enhanced features:
- Large digital clock with thick pixel font (each digit ~8x12 pixels)
- Smooth rainbow color cycling with depth/shadow effect on digits
- Seconds progress arc around the display edge
- Date and day-of-week cleanly positioned
- Analog clock: smooth hands, glowing tick marks, sweeping second hand
- Subtle animated background gradient
- Smooth crossfade transitions between clock modes
- AM/PM indicator
"""

import logging
import time
import math
from datetime import datetime
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

# --- Constants ---
SIZE = 64
FPS = 20
FRAME_DUR = 1.0 / FPS
BG_COLOR = (0, 0, 0)

# Analog clock colors
SECOND_HAND_COLOR = (255, 60, 60)     # bright red
MINUTE_HAND_COLOR = (240, 240, 255)   # near-white
HOUR_HAND_COLOR = (255, 210, 60)      # gold
FACE_DOT_COLOR = (50, 55, 80)         # dim dots for hour markers
FACE_DOT_MAJOR = (100, 110, 160)      # brighter dot for 12/3/6/9
CENTER_DOT = (220, 220, 240)          # center point

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

# Small 3x5 letter bitmaps for day-of-week and AM/PM
SMALL_LETTERS = {
    'A': [0b010, 0b101, 0b111, 0b101, 0b101],
    'M': [0b101, 0b111, 0b111, 0b101, 0b101],
    'P': [0b111, 0b101, 0b111, 0b100, 0b100],
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


def _blend_color(c1, c2, t):
    """Blend two RGB colors by factor t (0.0 = c1, 1.0 = c2)."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _draw_large_digit(image, digit_char, x, y, color, shadow_color=None):
    """Draw an 8x12 pixel digit at position (x, y) with optional shadow."""
    rows = LARGE_DIGITS.get(digit_char)
    if rows is None:
        return

    # Draw shadow first (offset by 1 pixel)
    if shadow_color:
        for row_idx, bits in enumerate(rows):
            for col_idx in range(8):
                if bits & (1 << (7 - col_idx)):
                    px = x + col_idx + 1
                    py = y + row_idx + 1
                    if 0 <= px < SIZE and 0 <= py < SIZE:
                        image.putpixel((px, py), shadow_color)

    # Draw main digit
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


def _draw_colon(image, x, y, color, large=True):
    """Draw colon dots."""
    if large:
        # 2x2 dots for large clock
        for dx in range(2):
            for dy in range(2):
                px1, py1 = x + dx, y + 3 + dy
                if 0 <= px1 < SIZE and 0 <= py1 < SIZE:
                    image.putpixel((px1, py1), color)
                px2, py2 = x + dx, y + 8 + dy
                if 0 <= px2 < SIZE and 0 <= py2 < SIZE:
                    image.putpixel((px2, py2), color)
    else:
        # Single pixel dots for small
        if 0 <= x < SIZE and 0 <= y + 1 < SIZE:
            image.putpixel((x, y + 1), color)
        if 0 <= x < SIZE and 0 <= y + 3 < SIZE:
            image.putpixel((x, y + 3), color)


def _draw_seconds_arc(draw, seconds, microseconds, hue_offset):
    """Draw a progress arc around the edge representing seconds elapsed."""
    cx, cy = SIZE // 2, SIZE // 2
    radius = 31  # Just inside the border

    # How far through the minute we are (0.0 to 1.0)
    progress = (seconds + microseconds / 1_000_000) / 60.0

    # Draw the full dim track
    for deg in range(360):
        angle = math.radians(deg - 90)  # Start from top
        px = int(cx + radius * math.cos(angle))
        py = int(cy + radius * math.sin(angle))
        if 0 <= px < SIZE and 0 <= py < SIZE:
            draw.point((px, py), fill=(15, 15, 25))

    # Draw the bright progress arc
    end_deg = int(progress * 360)
    for deg in range(end_deg):
        angle = math.radians(deg - 90)
        px = int(cx + radius * math.cos(angle))
        py = int(cy + radius * math.sin(angle))
        if 0 <= px < SIZE and 0 <= py < SIZE:
            arc_hue = (hue_offset + deg * 0.5) % 360
            color = _hsv_to_rgb(arc_hue, 0.9, 0.6)
            draw.point((px, py), fill=color)

    # Bright dot at the leading edge
    if end_deg > 0:
        angle = math.radians(end_deg - 90)
        px = int(cx + radius * math.cos(angle))
        py = int(cy + radius * math.sin(angle))
        if 0 <= px < SIZE and 0 <= py < SIZE:
            bright = _hsv_to_rgb((hue_offset + end_deg * 0.5) % 360, 1.0, 1.0)
            draw.point((px, py), fill=bright)
            # Glow neighbors
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                gx, gy = px + dx, py + dy
                if 0 <= gx < SIZE and 0 <= gy < SIZE:
                    glow = _hsv_to_rgb((hue_offset + end_deg * 0.5) % 360, 0.8, 0.3)
                    draw.point((gx, gy), fill=glow)


def _draw_background_gradient(draw, hue_offset):
    """Draw a subtle animated background gradient."""
    for y in range(SIZE):
        for x in range(SIZE):
            # Very subtle radial gradient from center
            dx = x - SIZE // 2
            dy = y - SIZE // 2
            dist = math.sqrt(dx * dx + dy * dy) / 45.0
            val = max(0, 0.04 - dist * 0.03)
            if val > 0:
                hue = (hue_offset + dist * 30) % 360
                r, g, b = _hsv_to_rgb(hue, 0.3, val)
                draw.point((x, y), fill=(r, g, b))


def _draw_digital_clock(now, hue_offset):
    """Draw the enhanced digital clock display."""
    image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
    draw = ImageDraw.Draw(image)

    # Subtle background
    _draw_background_gradient(draw, hue_offset)

    # Seconds arc around the edge
    _draw_seconds_arc(draw, now.second, now.microsecond, hue_offset)

    hours = now.strftime("%H")
    minutes = now.strftime("%M")

    # Main digit color with shadow
    color = _hsv_to_rgb(hue_offset % 360, 0.85, 1.0)
    shadow = _hsv_to_rgb((hue_offset + 180) % 360, 0.4, 0.15)
    color2 = _hsv_to_rgb((hue_offset + 40) % 360, 0.85, 1.0)

    # Center the time display: HH:MM
    # Each digit 8px wide + 2px gap, colon 4px
    # Total: 10 + 10 + 4 + 10 + 10 = 44px, centered: offset = 10
    start_x = 4
    digit_y = 14

    # Hours (slightly different hue from minutes for contrast)
    _draw_large_digit(image, hours[0], start_x, digit_y, color, shadow)
    _draw_large_digit(image, hours[1], start_x + 10, digit_y, color, shadow)

    # Blinking colon with smooth fade
    colon_phase = (now.microsecond / 1_000_000) * math.pi * 2
    colon_alpha = (math.sin(colon_phase) + 1) / 2  # 0 to 1 smoothly
    colon_color = (
        int(color2[0] * colon_alpha),
        int(color2[1] * colon_alpha),
        int(color2[2] * colon_alpha),
    )
    if max(colon_color) > 10:
        _draw_colon(image, start_x + 21, digit_y, colon_color)

    # Minutes
    _draw_large_digit(image, minutes[0], start_x + 26, digit_y, color2, shadow)
    _draw_large_digit(image, minutes[1], start_x + 36, digit_y, color2, shadow)

    # Seconds in a clean position (top right corner)
    seconds = now.strftime("%S")
    sec_color = _hsv_to_rgb((hue_offset + 120) % 360, 0.7, 0.8)
    _draw_small_string(image, seconds, start_x + 48, digit_y + 4, sec_color)

    # AM/PM indicator
    is_pm = now.hour >= 12
    ampm_str = "PM" if is_pm else "AM"
    ampm_color = _hsv_to_rgb((hue_offset + 90) % 360, 0.5, 0.5)
    _draw_small_string(image, ampm_str, start_x + 48, digit_y + 12, ampm_color)

    # Date below time
    date_color = _hsv_to_rgb((hue_offset + 160) % 360, 0.6, 0.55)
    date_str = now.strftime("%m/%d")
    _draw_small_string(image, date_str, 14, 34, date_color)

    # Day of week
    day_name = DAY_NAMES[now.weekday()]
    day_color = _hsv_to_rgb((hue_offset + 200) % 360, 0.55, 0.5)
    _draw_small_string(image, day_name, 34, 34, day_color)

    # Year (subtle, bottom area)
    year_str = now.strftime("%Y")
    year_color = _hsv_to_rgb((hue_offset + 240) % 360, 0.4, 0.3)
    _draw_small_string(image, year_str, 20, 42, year_color)

    # Bottom decorative gradient bar
    for x in range(4, 60):
        line_hue = (hue_offset + x * 4) % 360
        brightness = 0.3 + 0.1 * math.sin(hue_offset * 0.02 + x * 0.2)
        line_color = _hsv_to_rgb(line_hue, 0.85, brightness)
        draw.point((x, 52), fill=line_color)
        dimmer = _hsv_to_rgb(line_hue, 0.6, brightness * 0.5)
        draw.point((x, 53), fill=dimmer)

    return image


def _draw_analog_clock(now, hue_offset):
    """Draw the enhanced analog clock display."""
    image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
    draw = ImageDraw.Draw(image)

    cx, cy = SIZE // 2, SIZE // 2
    clock_radius = 26

    # Draw subtle background gradient
    _draw_background_gradient(draw, hue_offset)

    # Outer rainbow ring (subtle)
    for deg in range(0, 360, 2):
        angle = math.radians(deg)
        ring_r = clock_radius + 4
        rx = int(cx + ring_r * math.cos(angle))
        ry = int(cy + ring_r * math.sin(angle))
        ring_color = _hsv_to_rgb((hue_offset + deg) % 360, 0.5, 0.2)
        if 0 <= rx < SIZE and 0 <= ry < SIZE:
            draw.point((rx, ry), fill=ring_color)

    # Draw hour markers (12 positions around the circle)
    for h in range(12):
        angle = math.radians(h * 30 - 90)  # 0=12 o'clock
        is_major = h % 3 == 0

        if is_major:
            # Larger tick marks for 12/3/6/9
            inner_r = clock_radius - 3
            outer_r = clock_radius
            tick_color = FACE_DOT_MAJOR
        else:
            # Smaller dots for other hours
            inner_r = clock_radius - 1
            outer_r = clock_radius
            tick_color = FACE_DOT_COLOR

        # Draw tick line
        for r in range(int(inner_r), int(outer_r) + 1):
            tx = int(cx + r * math.cos(angle))
            ty = int(cy + r * math.sin(angle))
            if 0 <= tx < SIZE and 0 <= ty < SIZE:
                draw.point((tx, ty), fill=tick_color)

        # Extra brightness for 12 o'clock
        if h == 0:
            for dr in range(-1, 2):
                tx = int(cx + (clock_radius + dr) * math.cos(angle))
                ty = int(cy + (clock_radius + dr) * math.sin(angle))
                if 0 <= tx < SIZE and 0 <= ty < SIZE:
                    draw.point((tx, ty), fill=(160, 170, 220))

    # Get time components with smooth interpolation
    hours = now.hour % 12
    minutes = now.minute
    seconds = now.second
    microseconds = now.microsecond

    # Smooth angles
    second_frac = seconds + microseconds / 1_000_000
    minute_frac = minutes + second_frac / 60.0
    hour_frac = hours + minute_frac / 60.0

    second_angle = math.radians(second_frac * 6 - 90)
    minute_angle = math.radians(minute_frac * 6 - 90)
    hour_angle = math.radians(hour_frac * 30 - 90)

    # Draw hour hand (thick, short, with glow)
    hour_len = 14
    hx = cx + int(hour_len * math.cos(hour_angle))
    hy = cy + int(hour_len * math.sin(hour_angle))
    # Glow
    draw.line([(cx, cy), (hx, hy)], fill=(80, 65, 15), width=5)
    draw.line([(cx, cy), (hx, hy)], fill=HOUR_HAND_COLOR, width=3)

    # Draw minute hand (medium thickness, longer)
    minute_len = 20
    minx = cx + int(minute_len * math.cos(minute_angle))
    miny = cy + int(minute_len * math.sin(minute_angle))
    # Glow
    draw.line([(cx, cy), (minx, miny)], fill=(40, 40, 50), width=3)
    draw.line([(cx, cy), (minx, miny)], fill=MINUTE_HAND_COLOR, width=2)

    # Draw second hand (thin, longest, with red glow)
    second_len = 23
    sx = cx + int(second_len * math.cos(second_angle))
    sy = cy + int(second_len * math.sin(second_angle))
    # Counter-balance (short tail in opposite direction)
    tail_len = 5
    tail_x = cx - int(tail_len * math.cos(second_angle))
    tail_y = cy - int(tail_len * math.sin(second_angle))
    draw.line([(tail_x, tail_y), (sx, sy)], fill=SECOND_HAND_COLOR, width=1)

    # Center dot (layered for 3D effect)
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= 2:
                brightness = 1.0 - dist / 3.0
                c = int(220 * brightness)
                px, py = cx + dx, cy + dy
                if 0 <= px < SIZE and 0 <= py < SIZE:
                    image.putpixel((px, py), (c, c, min(255, c + 20)))

    # Digital time in small text at bottom
    time_color = _hsv_to_rgb(hue_offset % 360, 0.4, 0.45)
    h_str = now.strftime("%H")
    m_str = now.strftime("%M")
    _draw_small_string(image, h_str, 22, 58, time_color)
    # Blinking colon
    if now.microsecond < 500000:
        _draw_colon(image, 30, 57, time_color, large=False)
    _draw_small_string(image, m_str, 33, 58, time_color)

    return image


def _draw_world_clock(now, hue_offset):
    """Draw a world/multi-timezone clock display.

    Shows local time large + 2 other timezone offsets below.
    Includes a simple day/night indicator.
    """
    image = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
    draw = ImageDraw.Draw(image)

    # Background
    _draw_background_gradient(draw, hue_offset)

    # Seconds progress arc
    _draw_seconds_arc(draw, now.second, now.microsecond, hue_offset)

    # Local time - large
    hours = now.strftime("%H")
    minutes = now.strftime("%M")

    local_color = _hsv_to_rgb(hue_offset % 360, 0.9, 1.0)
    shadow = (20, 20, 35)

    # "LOCAL" label
    label_color = _hsv_to_rgb((hue_offset + 60) % 360, 0.5, 0.5)
    _draw_small_string(image, "here", 3, 4, label_color)

    # Large local time
    _draw_large_digit(image, hours[0], 3, 12, local_color, shadow)
    _draw_large_digit(image, hours[1], 13, 12, local_color, shadow)

    # Blinking colon
    colon_vis = now.microsecond < 500000
    if colon_vis:
        _draw_colon(image, 22, 12, local_color)

    _draw_large_digit(image, minutes[0], 26, 12, local_color, shadow)
    _draw_large_digit(image, minutes[1], 36, 12, local_color, shadow)

    # Seconds small
    sec_color = _hsv_to_rgb((hue_offset + 120) % 360, 0.6, 0.65)
    _draw_small_string(image, now.strftime("%S"), 48, 16, sec_color)

    # UTC offset display (simplified: show UTC and one other)
    # UTC time
    utc_hour = (now.hour + 5) % 24  # Approximate UTC (assuming CST offset)
    utc_str = f"{utc_hour:02d}"
    utc_min = now.strftime("%M")

    utc_color = _hsv_to_rgb((hue_offset + 180) % 360, 0.7, 0.6)
    utc_label_color = _hsv_to_rgb((hue_offset + 180) % 360, 0.4, 0.4)
    _draw_small_string(image, "UTC", 4, 32, utc_label_color)
    _draw_small_string(image, utc_str, 18, 32, utc_color)
    if colon_vis:
        _draw_colon(image, 26, 31, utc_color, large=False)
    _draw_small_string(image, utc_min, 29, 32, utc_color)

    # Tokyo time (UTC+9, so +14 from CST)
    tokyo_hour = (now.hour + 14) % 24
    tokyo_str = f"{tokyo_hour:02d}"

    tokyo_color = _hsv_to_rgb((hue_offset + 270) % 360, 0.7, 0.6)
    tokyo_label_color = _hsv_to_rgb((hue_offset + 270) % 360, 0.4, 0.4)
    _draw_small_string(image, "TKO", 4, 40, tokyo_label_color)
    _draw_small_string(image, tokyo_str, 18, 40, tokyo_color)
    if colon_vis:
        _draw_colon(image, 26, 39, tokyo_color, large=False)
    _draw_small_string(image, utc_min, 29, 40, tokyo_color)

    # London time (UTC+0 in winter, UTC+1 in summer)
    london_hour = (now.hour + 5) % 24  # Approximate
    london_str = f"{london_hour:02d}"

    london_color = _hsv_to_rgb((hue_offset + 90) % 360, 0.7, 0.6)
    london_label_color = _hsv_to_rgb((hue_offset + 90) % 360, 0.4, 0.4)
    _draw_small_string(image, "LDN", 4, 48, london_label_color)
    _draw_small_string(image, london_str, 18, 48, london_color)
    if colon_vis:
        _draw_colon(image, 26, 47, london_color, large=False)
    _draw_small_string(image, utc_min, 29, 48, london_color)

    # Day/night indicator for local (sun/moon icon area)
    is_night = now.hour < 6 or now.hour >= 20
    if is_night:
        # Moon crescent
        moon_color = (200, 200, 140)
        draw.ellipse([50, 4, 58, 12], fill=moon_color)
        draw.ellipse([52, 3, 60, 11], fill=BG_COLOR)  # Crescent cutout
    else:
        # Sun rays
        sun_color = (255, 200, 50)
        draw.ellipse([52, 4, 58, 10], fill=sun_color)
        for angle_deg in range(0, 360, 45):
            angle = math.radians(angle_deg)
            rx = int(55 + 5 * math.cos(angle))
            ry = int(7 + 5 * math.sin(angle))
            if 0 <= rx < SIZE and 0 <= ry < SIZE:
                draw.point((rx, ry), fill=sun_color)

    # Bottom bar
    for x in range(4, 60):
        bar_hue = (hue_offset + x * 3) % 360
        bar_color = _hsv_to_rgb(bar_hue, 0.7, 0.25)
        draw.point((x, 56), fill=bar_color)

    return image


# Clock modes
CLOCK_MODES = ["digital", "analog", "world"]


def run(matrix, duration=60):
    """Run the Time Display feature for the specified duration.

    Cycles through digital, analog, and world clock modes with smooth
    crossfade transitions.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    start_time = time.time()
    deadline = start_time + duration
    hue_offset = 0.0
    mode_switch_interval = 20  # seconds between mode switches
    transition_duration = 1.0  # 1 second crossfade
    mode_idx = 0
    prev_image = None
    transitioning = False
    transition_start = 0

    try:
        last_mode_switch = start_time

        while time.time() < deadline:
            if should_stop():
                break
            frame_start = time.time()
            now = datetime.now()

            # Gradually shift hue (full rainbow cycle every ~60 seconds)
            hue_offset = ((frame_start - start_time) * 6) % 360

            # Check if it's time to switch modes
            if frame_start - last_mode_switch >= mode_switch_interval and not transitioning:
                transitioning = True
                transition_start = frame_start
                prev_image = current_image if 'current_image' in dir() else None

            # Handle transition completion
            if transitioning:
                t_elapsed = frame_start - transition_start
                if t_elapsed >= transition_duration:
                    transitioning = False
                    mode_idx = (mode_idx + 1) % len(CLOCK_MODES)
                    last_mode_switch = frame_start

            # Render current mode
            mode = CLOCK_MODES[mode_idx]
            if mode == "digital":
                current_image = _draw_digital_clock(now, hue_offset)
            elif mode == "analog":
                current_image = _draw_analog_clock(now, hue_offset)
            else:
                current_image = _draw_world_clock(now, hue_offset)

            # Apply crossfade during transition
            if transitioning and prev_image:
                t_elapsed = frame_start - transition_start
                alpha = min(1.0, t_elapsed / transition_duration)
                # Render the NEXT mode
                next_mode_idx = (mode_idx + 1) % len(CLOCK_MODES)
                next_mode = CLOCK_MODES[next_mode_idx]
                if next_mode == "digital":
                    next_image = _draw_digital_clock(now, hue_offset)
                elif next_mode == "analog":
                    next_image = _draw_analog_clock(now, hue_offset)
                else:
                    next_image = _draw_world_clock(now, hue_offset)

                # Blend
                display_image = Image.blend(current_image, next_image, alpha)
                matrix.SetImage(display_image)
            else:
                matrix.SetImage(current_image)

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
