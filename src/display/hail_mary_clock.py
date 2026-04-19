"""
Hail Mary Clock -- Eridian time display from Project Hail Mary.

Book-accurate representation of Rocky's base-6 numbering system:
- Eridian digit symbols: 0(circle), 1(line), 2(V), 3(lambda), 4(+), 5(nabla)
- Eridian time: day divided into 10,000 base-6 units (7,776 decimal)
- Astrophage amber glow aesthetic
- Shows both Earth time and Eridian time
- Rocky's "musical note" communication visualized as waveforms
- Deep space background with subtle star field

Eridians have 6 appendages, so they count in base 6.
Their day on 40 Eridiani e is approximately 40 Earth hours.
"""

import time
import math
import random
import logging
from datetime import datetime
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 12

# Astrophage-inspired colors (the glowing organisms from the book)
ASTROPHAGE_BRIGHT = (255, 180, 30)
ASTROPHAGE_MED = (200, 130, 15)
ASTROPHAGE_DIM = (120, 75, 8)

# Eridian "rocky" colors
ERIDIAN_METAL = (140, 150, 170)
ERIDIAN_DARK = (60, 65, 75)

# Space background
SPACE_BG = (1, 1, 3)

# Dim labels / separators
BRACKET_COLOR = (50, 40, 20)
LABEL_DIM = (60, 45, 15)

# Eridian day = 40 Earth hours = 144,000 Earth seconds
# Divided into 10,000 (base-6) Eridian units
# 10000 in base 6 = 1296 in decimal
# So 1 Eridian time unit = 144000 / 1296 ~= 111.11 Earth seconds
ERIDIAN_DAY_EARTH_SECONDS = 40.0 * 3600.0  # 144000
ERIDIAN_UNITS_PER_DAY = 6 ** 4  # 1296 (= "10000" in base 6)

# ---------------------------------------------------------------
# Book-accurate Eridian digit symbols as 7x7 pixel bitmaps
# 0 = circle        (empty/nothing)
# 1 = single line   (one appendage)
# 2 = V shape       (two lines meeting at bottom)
# 3 = lambda         (line with branch)
# 4 = plus/cross    (four directions)
# 5 = inverted triangle / nabla (five points implied)
# ---------------------------------------------------------------
# Each symbol is a list of (x, y) pixel offsets from top-left of a 7x7 cell.

ERIDIAN_SYMBOLS = {
    0: [  # Circle (hollow)
        (2, 0), (3, 0), (4, 0),
        (1, 1), (5, 1),
        (0, 2), (6, 2),
        (0, 3), (6, 3),
        (0, 4), (6, 4),
        (1, 5), (5, 5),
        (2, 6), (3, 6), (4, 6),
    ],
    1: [  # Single vertical line
        (3, 0),
        (3, 1),
        (3, 2),
        (3, 3),
        (3, 4),
        (3, 5),
        (3, 6),
    ],
    2: [  # V shape (two lines meeting at bottom)
        (0, 0), (6, 0),
        (0, 1), (6, 1),
        (1, 2), (5, 2),
        (1, 3), (5, 3),
        (2, 4), (4, 4),
        (2, 5), (4, 5),
        (3, 6),
    ],
    3: [  # Lambda shape (line with branch going right)
        (0, 0),
        (0, 1), (1, 1),
        (1, 2), (2, 2),
        (2, 3), (3, 3),
        (3, 4), (4, 4),
        (3, 5), (5, 5),
        (3, 6), (6, 6),
    ],
    4: [  # Plus / cross
        (3, 0),
        (3, 1),
        (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (6, 2),
        (3, 3),
        (3, 4),
        (3, 5),
        (3, 6),
    ],
    5: [  # Inverted triangle / nabla
        (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0),
        (0, 1), (6, 1),
        (1, 2), (5, 2),
        (1, 3), (5, 3),
        (2, 4), (4, 4),
        (2, 5), (4, 5),
        (3, 6),
    ],
}

# Symbol width (including 1px gap on right)
SYMBOL_W = 8
SYMBOL_H = 7


def _to_base6(n):
    """Convert a non-negative integer to a list of base-6 digits."""
    if n == 0:
        return [0]
    digits = []
    while n > 0:
        digits.append(n % 6)
        n //= 6
    digits.reverse()
    return digits


def _draw_eridian_digit(image, digit, x, y, color):
    """Draw a single Eridian digit symbol at (x, y)."""
    pixels = ERIDIAN_SYMBOLS.get(digit, ERIDIAN_SYMBOLS[0])
    for dx, dy in pixels:
        px, py = x + dx, y + dy
        if 0 <= px < WIDTH and 0 <= py < HEIGHT:
            image.putpixel((px, py), color)


def _draw_eridian_number(image, digits, x, y, color, gap=1):
    """Draw a multi-digit Eridian number. Returns total width."""
    cx = x
    for d in digits:
        _draw_eridian_digit(image, d, cx, y, color)
        cx += SYMBOL_W + gap
    return cx - x


def _draw_separator_dots(image, x, y, color, phase):
    """Draw pulsing separator dots between digit groups."""
    blink = math.sin(phase) > 0
    if blink:
        for dy in [1, 4]:
            py = y + dy
            if 0 <= x < WIDTH and 0 <= py < HEIGHT:
                image.putpixel((x, py), color)


def _draw_astrophage(image, x, y, phase, intensity=1.0):
    """Draw a single glowing astrophage particle."""
    pulse = 0.6 + 0.4 * math.sin(phase)
    brightness = pulse * intensity

    r = min(255, int(ASTROPHAGE_BRIGHT[0] * brightness))
    g = min(255, int(ASTROPHAGE_BRIGHT[1] * brightness))
    b = min(255, int(ASTROPHAGE_BRIGHT[2] * brightness))
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        image.putpixel((x, y), (r, g, b))

    # Glow halo
    halo = brightness * 0.25
    hr = int(ASTROPHAGE_BRIGHT[0] * halo)
    hg = int(ASTROPHAGE_BRIGHT[1] * halo)
    hb = int(ASTROPHAGE_BRIGHT[2] * halo)
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        px, py = x + dx, y + dy
        if 0 <= px < WIDTH and 0 <= py < HEIGHT:
            existing = image.getpixel((px, py))
            image.putpixel((px, py), (min(255, existing[0] + hr),
                                       min(255, existing[1] + hg),
                                       min(255, existing[2] + hb)))


def _draw_waveform(image, y, phase, color, amplitude=2, wavelength=14):
    """Draw a sine waveform (Rocky's musical communication)."""
    for x in range(WIDTH):
        wy = y + int(amplitude * math.sin(phase + x * 2 * math.pi / wavelength))
        if 0 <= x < WIDTH and 0 <= wy < HEIGHT:
            image.putpixel((x, wy), color)


def _draw_stars(image, star_positions):
    """Draw background stars."""
    for sx, sy, b in star_positions:
        if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
            image.putpixel((sx, sy), (b, b, min(255, b + 15)))


def _earth_to_eridian_units(now):
    """Convert Earth time-of-day to Eridian time units.

    Eridian day = 40 Earth hours, divided into 10000 (base-6) = 1296 units.
    We map the current Earth seconds-since-midnight into the Eridian cycle.
    Returns the Eridian unit count (0-1295).
    """
    earth_seconds = now.hour * 3600 + now.minute * 60 + now.second + \
        now.microsecond / 1e6
    # Scale 24h Earth day -> 40h Eridian day proportionally
    eridian_fraction = earth_seconds / (24.0 * 3600.0)
    eridian_units = int(eridian_fraction * ERIDIAN_UNITS_PER_DAY)
    return eridian_units % ERIDIAN_UNITS_PER_DAY


def _draw_label_pixels(image, text, x, y, color):
    """Draw tiny label text using the shared 3x5 font."""
    from src.display._utils import _draw_digit, DIGITS
    # Letters not in DIGITS -- define minimal 3x5 pixel bitmaps
    LETTERS = {
        'E': [0b111, 0b100, 0b110, 0b100, 0b111],
        'R': [0b110, 0b101, 0b110, 0b101, 0b101],
        'I': [0b111, 0b010, 0b010, 0b010, 0b111],
        'D': [0b110, 0b101, 0b101, 0b101, 0b110],
        'A': [0b010, 0b101, 0b111, 0b101, 0b101],
        'T': [0b111, 0b010, 0b010, 0b010, 0b010],
        'H': [0b101, 0b101, 0b111, 0b101, 0b101],
    }
    cx = x
    for ch in text:
        rows = LETTERS.get(ch, DIGITS.get(ch, [0, 0, 0, 0, 0]))
        for ri, bits in enumerate(rows):
            for ci in range(3):
                if bits & (1 << (2 - ci)):
                    px, py = cx + ci, y + ri
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        image.putpixel((px, py), color)
        cx += 4


def run(matrix, duration=60):
    """Run the Hail Mary / Eridian clock display."""
    start_time = time.time()

    # Static star positions
    rng = random.Random(42)
    stars = [(rng.randint(0, WIDTH - 1), rng.randint(0, HEIGHT - 1),
              rng.randint(15, 50)) for _ in range(20)]

    # Floating astrophage particles
    astrophage = [(rng.randint(5, WIDTH - 5), rng.randint(3, HEIGHT - 3),
                   rng.uniform(0, 6.28)) for _ in range(5)]

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            now = datetime.now()
            elapsed = time.time()
            phase = elapsed * 2.0

            image = Image.new("RGB", (WIDTH, HEIGHT), SPACE_BG)

            # --- Background stars ---
            _draw_stars(image, stars)

            # --- Floating astrophage ---
            for i, (ax, ay, ap) in enumerate(astrophage):
                dx = ax + int(2 * math.sin(phase * 0.3 + i * 1.5))
                dy = ay + int(1.5 * math.cos(phase * 0.2 + i * 2.0))
                _draw_astrophage(image, dx, dy, phase + i, intensity=0.35)

            # === EARTH TIME in Eridian symbols (base 6) ===
            h6 = _to_base6(now.hour)
            m6 = _to_base6(now.minute)
            s6 = _to_base6(now.second)

            while len(h6) < 2:
                h6.insert(0, 0)
            while len(m6) < 2:
                m6.insert(0, 0)
            while len(s6) < 2:
                s6.insert(0, 0)

            # Row 1 label: "E" for Earth
            _draw_label_pixels(image, "E", 1, 2, LABEL_DIM)

            # Draw Earth time: HH : MM : SS using Eridian symbols
            row1_y = 1
            pulse_e = 0.85 + 0.15 * math.sin(phase)
            earth_color = tuple(min(255, int(c * pulse_e))
                                for c in ASTROPHAGE_BRIGHT)

            x_pos = 7
            _draw_eridian_number(image, h6, x_pos, row1_y, earth_color, gap=0)
            x_pos += len(h6) * SYMBOL_W + 1
            _draw_separator_dots(image, x_pos, row1_y, ASTROPHAGE_DIM,
                                 phase * 2)
            x_pos += 3
            _draw_eridian_number(image, m6, x_pos, row1_y, earth_color, gap=0)
            x_pos += len(m6) * SYMBOL_W + 1
            _draw_separator_dots(image, x_pos, row1_y, ASTROPHAGE_DIM,
                                 phase * 2)
            x_pos += 3
            _draw_eridian_number(image, s6, x_pos, row1_y, earth_color, gap=0)

            # === Astrophage glow divider ===
            div_y = 10
            for x in range(WIDTH):
                scan = (elapsed * 18) % WIDTH
                dist = abs(x - scan)
                if dist > WIDTH / 2:
                    dist = WIDTH - dist
                intensity = max(0, 1.0 - dist / 10.0)
                base_i = 0.12
                total = base_i + intensity * 0.5
                r = int(ASTROPHAGE_BRIGHT[0] * total * 0.4)
                g = int(ASTROPHAGE_BRIGHT[1] * total * 0.4)
                b = int(ASTROPHAGE_BRIGHT[2] * total * 0.1)
                image.putpixel((x, div_y), (r, g, b))

            # === ERIDIAN TIME ===
            # Convert Earth time to Eridian units (0 to 1295)
            eridian_units = _earth_to_eridian_units(now)
            eridian_digits = _to_base6(eridian_units)
            while len(eridian_digits) < 4:
                eridian_digits.insert(0, 0)

            # Row 2 label: "R" for Rocky
            _draw_label_pixels(image, "R", 1, 14, ERIDIAN_DARK)

            # Draw Eridian time: 4 symbols
            row2_y = 12
            e_color = ERIDIAN_METAL
            x_pos = 7
            for i, d in enumerate(eridian_digits):
                pulse_r = 0.85 + 0.15 * math.sin(phase + i * 0.8)
                dc = tuple(min(255, int(c * pulse_r)) for c in e_color)
                _draw_eridian_digit(image, d, x_pos, row2_y, dc)
                x_pos += SYMBOL_W + 1

                # Add separator after first 2 digits (like HH:MM)
                if i == 1:
                    _draw_separator_dots(image, x_pos, row2_y,
                                         ERIDIAN_DARK, phase * 1.5)
                    x_pos += 3

            # === Waveform (Rocky's voice) ===
            wave_y = 23
            _draw_waveform(image, wave_y, phase * 1.2, ASTROPHAGE_DIM,
                           amplitude=2, wavelength=16)
            _draw_waveform(image, wave_y + 1, phase * 0.7 + 2.0,
                           tuple(c // 2 for c in ERIDIAN_METAL),
                           amplitude=1, wavelength=11)

            # === Second astrophage divider ===
            div_y2 = 27
            for x in range(WIDTH):
                scan = (elapsed * 12 + WIDTH / 2) % WIDTH
                dist = abs(x - scan)
                if dist > WIDTH / 2:
                    dist = WIDTH - dist
                intensity = max(0, 1.0 - dist / 8.0)
                r = int(ASTROPHAGE_DIM[0] * intensity * 0.5)
                g = int(ASTROPHAGE_DIM[1] * intensity * 0.5)
                b = int(ASTROPHAGE_DIM[2] * intensity * 0.2)
                image.putpixel((x, div_y2), (r, g, b))

            # === Eridian symbol legend (bottom section) ===
            # Show all 6 symbols with their decimal values
            legend_y = 30
            legend_color = tuple(c // 2 for c in ASTROPHAGE_MED)
            for d in range(6):
                lx = 2 + d * 10
                _draw_eridian_digit(image, d, lx, legend_y, legend_color)

            # === Astrophage energy bar ===
            bar_y = 40
            energy = (now.second + now.microsecond / 1e6) / 60.0
            bar_len = int(energy * (WIDTH - 4))
            for x in range(2, 2 + bar_len):
                glow = 0.3 + 0.7 * (x / WIDTH)
                pm = 0.9 + 0.1 * math.sin(phase + x * 0.5)
                r = min(255, int(ASTROPHAGE_BRIGHT[0] * glow * pm))
                g = min(255, int(ASTROPHAGE_BRIGHT[1] * glow * pm * 0.7))
                b = min(255, int(ASTROPHAGE_BRIGHT[2] * glow * pm * 0.2))
                image.putpixel((x, bar_y), (r, g, b))
                if bar_y + 1 < HEIGHT:
                    image.putpixel((x, bar_y + 1),
                                   (r // 2, g // 2, b // 2))

            # === Bottom: Earth decimal time reference ===
            from src.display._utils import _draw_digit
            ref_y = HEIGHT - 7
            ref_str = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
            rx = (WIDTH - len(ref_str) * 4) // 2
            for i, ch in enumerate(ref_str):
                _draw_digit(image, ch, rx + i * 4, ref_y, BRACKET_COLOR)

            # === Tau Ceti star glow (bottom right) ===
            sx, sy = WIDTH - 5, HEIGHT - 5
            sp = 0.5 + 0.5 * math.sin(phase * 0.5)
            sr, sg, sb = int(200 * sp), int(180 * sp), int(100 * sp)
            if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                image.putpixel((sx, sy), (sr, sg, sb))
                for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    px, py = sx + ddx, sy + ddy
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        image.putpixel((px, py), (sr // 3, sg // 3, sb // 3))

            matrix.SetImage(image)

            elapsed_frame = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed_frame
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in hail mary clock: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
