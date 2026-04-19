"""
Base 6 (Senary) Clock -- inspired by Rocky from Project Hail Mary.

Eridians use base-6 numbering because they have 6 appendages.
This display converts current time into senary (base 6) notation
with a distinctive alien-inspired aesthetic.

Layout:
- Large senary digits for hours, minutes, seconds (top area)
- Senary digit tally marks rendered as dot clusters (middle area)
- Small decimal reference time at bottom
- Warm amber color palette evoking Eridian technology
"""

import time
import math
import logging
from datetime import datetime
from PIL import Image, ImageDraw
from src.display._shared import should_stop
from src.display._utils import _draw_digit

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 10

# Eridian-inspired color palette (warm ambers and alien greens)
BG_COLOR = (2, 1, 4)
AMBER = (255, 170, 40)
AMBER_DIM = (120, 75, 15)
AMBER_GLOW = (255, 200, 80)
ERIDIAN_GREEN = (40, 255, 120)
ERIDIAN_GREEN_DIM = (15, 80, 40)
SEPARATOR_COLOR = (80, 50, 15)
LABEL_COLOR = (100, 65, 20)

# Senary digit bitmaps (5x7 pixel font, wider than the 3x5 util font)
# Each digit 0-5 represented as 7 rows of 5-bit values
SENARY_FONT = {
    0: [0b01110, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b01110],
    1: [0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    2: [0b01110, 0b10001, 0b00001, 0b00110, 0b01000, 0b10000, 0b11111],
    3: [0b01110, 0b10001, 0b00001, 0b00110, 0b00001, 0b10001, 0b01110],
    4: [0b00010, 0b00110, 0b01010, 0b10010, 0b11111, 0b00010, 0b00010],
    5: [0b11111, 0b10000, 0b11110, 0b00001, 0b00001, 0b10001, 0b01110],
}


def _to_base6(n):
    """Convert a non-negative integer to a list of base-6 digits (most significant first)."""
    if n == 0:
        return [0]
    digits = []
    while n > 0:
        digits.append(n % 6)
        n //= 6
    digits.reverse()
    return digits


def _draw_senary_digit(image, digit, x, y, color):
    """Draw a single senary digit (0-5) using the 5x7 font."""
    rows = SENARY_FONT.get(digit, SENARY_FONT[0])
    for ri, bits in enumerate(rows):
        for ci in range(5):
            if bits & (1 << (4 - ci)):
                px, py = x + ci, y + ri
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    image.putpixel((px, py), color)


def _draw_senary_number(image, digits, x, y, color, spacing=6):
    """Draw a sequence of senary digits with given spacing."""
    for i, d in enumerate(digits):
        _draw_senary_digit(image, d, x + i * spacing, y, color)


def _draw_tally_dots(image, digit, cx, cy, color, radius=3):
    """Draw a tally-dot cluster representing a senary digit (0-5).

    Dots are arranged in a 2x3 grid pattern:
      0 = empty
      1 = top-left
      2 = top-left, top-right
      3 = top row filled
      4 = top row + bottom-left
      5 = top row + bottom-left + bottom-right (nearly full)
    """
    positions = [
        (cx - 2, cy - 2), (cx, cy - 2), (cx + 2, cy - 2),  # top row
        (cx - 2, cy + 1), (cx, cy + 1), (cx + 2, cy + 1),  # bottom row
    ]
    # Fill dots based on digit value
    for i in range(min(digit, 6)):
        px, py = positions[i]
        if 0 <= px < WIDTH and 0 <= py < HEIGHT:
            image.putpixel((px, py), color)
        # Draw slightly larger dots (cross pattern)
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = px + dx, py + dy
            if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                dim = tuple(max(0, c // 2) for c in color)
                image.putpixel((nx, ny), dim)


def _draw_separator(image, x, y, color, phase):
    """Draw a pulsing double-dot separator (like a colon)."""
    brightness = 0.5 + 0.5 * math.sin(phase)
    c = tuple(int(v * brightness) for v in color)
    for dy in [-2, 2]:
        py = y + dy
        if 0 <= x < WIDTH and 0 <= py < HEIGHT:
            image.putpixel((x, py), c)


def run(matrix, duration=60):
    """Run the Base 6 clock display.

    Shows current time in senary (base 6) notation, inspired by Rocky
    the Eridian from Project Hail Mary.
    """
    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            now = datetime.now()

            image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
            draw = ImageDraw.Draw(image)

            elapsed_s = time.time()
            phase = elapsed_s * 3.0  # animation phase for pulsing

            # --- Convert time to base 6 ---
            h6 = _to_base6(now.hour)
            m6 = _to_base6(now.minute)
            s6 = _to_base6(now.second)

            # Pad to 2 senary digits minimum (max hours=23 -> base6: 35, 2 digits)
            # Minutes max 59 -> base6: 133 (3 digits), seconds same
            while len(h6) < 2:
                h6.insert(0, 0)
            while len(m6) < 3:
                m6.insert(0, 0)
            while len(s6) < 3:
                s6.insert(0, 0)

            # --- Row 1: "BASE 6" label (tiny pixels) ---
            label = "BASE 6"
            lx = 2
            ly = 1
            for i, ch in enumerate(label):
                if ch == ' ':
                    continue
                _draw_digit(image, ch, lx + i * 4, ly, LABEL_COLOR)

            # --- Draw decorative border lines ---
            for x in range(WIDTH):
                glow = int(15 + 8 * math.sin(x * 0.3 + phase * 0.5))
                if 0 <= x < WIDTH:
                    image.putpixel((x, 7), (glow, glow // 2, 0))

            # --- Row 2: Large senary time (HH : MMM : SSS) ---
            row_y = 10
            # Hours (2 digits)
            pulse_h = 0.85 + 0.15 * math.sin(phase + 0.0)
            h_color = tuple(min(255, int(c * pulse_h)) for c in AMBER_GLOW)
            _draw_senary_number(image, h6, 3, row_y, h_color)

            # Separator
            _draw_separator(image, 15, row_y + 3, AMBER, phase * 2)

            # Minutes (3 digits)
            pulse_m = 0.85 + 0.15 * math.sin(phase + 1.0)
            m_color = tuple(min(255, int(c * pulse_m)) for c in ERIDIAN_GREEN)
            _draw_senary_number(image, m6, 18, row_y, m_color)

            # Separator
            _draw_separator(image, 36, row_y + 3, ERIDIAN_GREEN_DIM, phase * 2)

            # Seconds (3 digits)
            pulse_s = 0.85 + 0.15 * math.sin(phase + 2.0)
            s_color = tuple(min(255, int(c * pulse_s)) for c in AMBER)
            _draw_senary_number(image, s6, 39, row_y, s_color)

            # --- Row 3: Tally dot clusters for each digit ---
            tally_y = 22

            # Draw tally dots for hours
            for i, d in enumerate(h6):
                _draw_tally_dots(image, d, 5 + i * 8, tally_y, AMBER_GLOW)

            # Draw tally dots for minutes
            for i, d in enumerate(m6):
                _draw_tally_dots(image, d, 22 + i * 8, tally_y, ERIDIAN_GREEN)

            # Draw tally dots for seconds
            for i, d in enumerate(s6):
                _draw_tally_dots(image, d, 42 + i * 8, tally_y, AMBER)

            # --- Decorative mid-line ---
            for x in range(WIDTH):
                glow = int(10 + 5 * math.sin(x * 0.2 + phase * 0.3))
                if 0 <= x < WIDTH:
                    image.putpixel((x, 30), (glow, glow // 3, 0))

            # --- Row 4: Senary breakdown display ---
            # Show the conversion: e.g., "14:53:20" -> visual representation
            info_y = 33

            # Draw labels "H" "M" "S" in dim color
            _draw_digit(image, '1' if now.hour >= 10 else '0', 2, info_y,
                        AMBER_DIM)
            # Show decimal values small
            _draw_digit(image, str(now.hour // 10), 2, info_y, AMBER_DIM)
            _draw_digit(image, str(now.hour % 10), 6, info_y, AMBER_DIM)

            _draw_digit(image, str(now.minute // 10), 22, info_y,
                        ERIDIAN_GREEN_DIM)
            _draw_digit(image, str(now.minute % 10), 26, info_y,
                        ERIDIAN_GREEN_DIM)

            _draw_digit(image, str(now.second // 10), 42, info_y, AMBER_DIM)
            _draw_digit(image, str(now.second % 10), 46, info_y, AMBER_DIM)

            # --- Row 5: Animated "heartbeat" bar (Eridian tech feel) ---
            bar_y = 41
            for x in range(WIDTH):
                # Create a scanning pulse effect
                scan_pos = (elapsed_s * 20) % WIDTH
                dist = abs(x - scan_pos)
                if dist > WIDTH / 2:
                    dist = WIDTH - dist
                intensity = max(0, 1.0 - dist / 12.0)
                if intensity > 0:
                    r = int(AMBER[0] * intensity * 0.4)
                    g = int(AMBER[1] * intensity * 0.4)
                    b = int(AMBER[2] * intensity * 0.1)
                    if 0 <= x < WIDTH:
                        image.putpixel((x, bar_y), (r, g, b))

            # --- Row 6: Full senary string representation ---
            str_y = 45
            # Format: "HH:MMM:SSS" in base 6, using 3x5 digit font
            senary_str = (
                "".join(str(d) for d in h6) + ":" +
                "".join(str(d) for d in m6) + ":" +
                "".join(str(d) for d in s6)
            )
            sx = (WIDTH - len(senary_str) * 4) // 2
            for i, ch in enumerate(senary_str):
                _draw_digit(image, ch, sx + i * 4, str_y, AMBER_GLOW)

            # --- Bottom: Decimal reference time ---
            ref_y = HEIGHT - 9
            ref_str = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
            rx = (WIDTH - len(ref_str) * 4) // 2
            for i, ch in enumerate(ref_str):
                _draw_digit(image, ch, rx + i * 4, ref_y, SEPARATOR_COLOR)

            # --- Bottom decorative line ---
            for x in range(WIDTH):
                glow = int(8 + 4 * math.sin(x * 0.25 - phase * 0.4))
                if 0 <= x < WIDTH:
                    image.putpixel((x, HEIGHT - 2), (glow, glow // 3, 0))

            matrix.SetImage(image)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in base6 clock: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
