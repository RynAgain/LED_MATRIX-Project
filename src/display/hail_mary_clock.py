"""
Hail Mary Clock -- Eridian time display from Project Hail Mary.

Book-accurate representation of Rocky's base-6 numbering system:
- Eridian digit symbols: 0(circle), 1(line), 2(V), 3(lambda), 4(+), 5(nabla)
- Eridian time: day divided into 10,000 base-6 units (1,296 decimal)
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
from PIL import Image
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 12

# Astrophage-inspired colors
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
LABEL_DIM = (55, 40, 12)

# Eridian day = 40 Earth hours, divided into base-6 "10000" = 1296 decimal units
ERIDIAN_UNITS_PER_DAY = 6 ** 4  # 1296

# ---------------------------------------------------------------
# Book-accurate Eridian digit symbols as 5x5 pixel bitmaps
# Compact version for 64x64 display (fits 6 symbols + separators)
# 0 = circle, 1 = line, 2 = V, 3 = lambda, 4 = plus, 5 = nabla
# ---------------------------------------------------------------
ERIDIAN_SYMBOLS = {
    0: [  # Circle (hollow)
        (1, 0), (2, 0), (3, 0),
        (0, 1), (4, 1),
        (0, 2), (4, 2),
        (0, 3), (4, 3),
        (1, 4), (2, 4), (3, 4),
    ],
    1: [  # Single vertical line
        (2, 0),
        (2, 1),
        (2, 2),
        (2, 3),
        (2, 4),
    ],
    2: [  # V shape
        (0, 0), (4, 0),
        (0, 1), (4, 1),
        (1, 2), (3, 2),
        (1, 3), (3, 3),
        (2, 4),
    ],
    3: [  # Lambda (diagonal with branch)
        (0, 0),
        (1, 1),
        (2, 2), (3, 2),
        (2, 3), (4, 3),
        (2, 4), (4, 4),
    ],
    4: [  # Plus / cross
        (2, 0),
        (2, 1),
        (0, 2), (1, 2), (2, 2), (3, 2), (4, 2),
        (2, 3),
        (2, 4),
    ],
    5: [  # Inverted triangle / nabla
        (0, 0), (1, 0), (2, 0), (3, 0), (4, 0),
        (0, 1), (4, 1),
        (1, 2), (3, 2),
        (1, 3), (3, 3),
        (2, 4),
    ],
}

SYMBOL_W = 5  # 5px wide symbol
SYMBOL_GAP = 1  # 1px gap between symbols in same group
SYMBOL_H = 5
GROUP_GAP = 3  # gap between digit groups (includes separator dot space)


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


def _draw_eridian_group(image, digits, x, y, color):
    """Draw a group of Eridian digits. Returns width used."""
    cx = x
    for d in digits:
        _draw_eridian_digit(image, d, cx, y, color)
        cx += SYMBOL_W + SYMBOL_GAP
    return cx - x - SYMBOL_GAP  # subtract trailing gap


def _draw_separator(image, x, y, color, blink_on):
    """Draw two separator dots (like colon in time)."""
    if blink_on:
        for dy in [1, 3]:
            py = y + dy
            if 0 <= x < WIDTH and 0 <= py < HEIGHT:
                image.putpixel((x, py), color)


def _draw_astrophage(image, x, y, phase, intensity=1.0):
    """Draw a glowing astrophage particle with halo."""
    pulse = 0.6 + 0.4 * math.sin(phase)
    b = pulse * intensity
    r = min(255, int(ASTROPHAGE_BRIGHT[0] * b))
    g = min(255, int(ASTROPHAGE_BRIGHT[1] * b))
    blue = min(255, int(ASTROPHAGE_BRIGHT[2] * b))
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        image.putpixel((x, y), (r, g, blue))
    # Subtle halo
    hb = b * 0.2
    hr = int(ASTROPHAGE_BRIGHT[0] * hb)
    hg = int(ASTROPHAGE_BRIGHT[1] * hb)
    hbl = int(ASTROPHAGE_BRIGHT[2] * hb)
    for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        px, py = x + ddx, y + ddy
        if 0 <= px < WIDTH and 0 <= py < HEIGHT:
            ex = image.getpixel((px, py))
            image.putpixel((px, py), (min(255, ex[0] + hr),
                                       min(255, ex[1] + hg),
                                       min(255, ex[2] + hbl)))


def _draw_waveform(image, y, phase, color, amplitude=2, wavelength=16):
    """Draw a sine waveform (Rocky's musical communication)."""
    for x in range(WIDTH):
        wy = y + int(amplitude * math.sin(phase + x * 2 * math.pi / wavelength))
        if 0 <= x < WIDTH and 0 <= wy < HEIGHT:
            image.putpixel((x, wy), color)


def _draw_stars(image, star_positions):
    """Draw background stars."""
    for sx, sy, brightness in star_positions:
        if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
            image.putpixel((sx, sy), (brightness, brightness,
                                       min(255, brightness + 12)))


def _draw_scan_line(image, y, phase, color, speed=15.0, width=10):
    """Draw a scanning glow line across the full width."""
    scan_x = (phase * speed) % WIDTH
    for x in range(WIDTH):
        dist = abs(x - scan_x)
        if dist > WIDTH / 2:
            dist = WIDTH - dist
        intensity = max(0.0, 1.0 - dist / width)
        if intensity > 0:
            r = int(color[0] * intensity * 0.5)
            g = int(color[1] * intensity * 0.5)
            b = int(color[2] * intensity * 0.15)
            image.putpixel((x, y), (r, g, b))


def _earth_to_eridian_units(now):
    """Convert Earth time-of-day to Eridian time units (0-1295)."""
    earth_seconds = now.hour * 3600 + now.minute * 60 + now.second + \
        now.microsecond / 1e6
    fraction = earth_seconds / 86400.0  # fraction of Earth day
    return int(fraction * ERIDIAN_UNITS_PER_DAY) % ERIDIAN_UNITS_PER_DAY


def _draw_tiny_label(image, text, x, y, color):
    """Draw tiny 3x5 pixel label text."""
    from src.display._utils import DIGITS
    LETTERS = {
        'E': [0b111, 0b100, 0b110, 0b100, 0b111],
        'R': [0b110, 0b101, 0b110, 0b101, 0b101],
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

    # Static star positions (placed in safe zones to avoid symbol overlap)
    rng = random.Random(42)
    stars = []
    for _ in range(18):
        sy = rng.randint(0, HEIGHT - 1)
        sx = rng.randint(0, WIDTH - 1)
        # Only place stars in areas that won't be overdrawn
        if sy > 43 and sy < 56:
            stars.append((sx, sy, rng.randint(15, 45)))
        elif rng.random() < 0.5:
            stars.append((sx, sy, rng.randint(10, 35)))

    # Astrophage particles in the energy bar / bottom zone only
    astrophage_positions = [
        (rng.randint(3, WIDTH - 3), rng.randint(44, 54))
        for _ in range(4)
    ]

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            now = datetime.now()
            t = time.time() - start_time  # time since feature start
            phase = t * 2.5

            image = Image.new("RGB", (WIDTH, HEIGHT), SPACE_BG)

            # --- Background stars ---
            _draw_stars(image, stars)

            blink_on = math.sin(phase * 1.5) > 0

            # =========================================================
            # ROW 1: Earth time in Eridian symbols (y=1)
            # Hours: always 2 base-6 digits (max 23 = 35 in base 6)
            # Minutes: always 2 base-6 digits (max 59 = 133, show as 2 groups)
            # We show HH : MM only (seconds on the reference line below)
            # =========================================================
            h6 = _to_base6(now.hour)
            m6 = _to_base6(now.minute)
            while len(h6) < 2:
                h6.insert(0, 0)
            while len(m6) < 2:
                m6.insert(0, 0)
            # If minutes need 3 digits (36-59), show all 3
            # Layout: E | HH : MMM  (max width = 4 + 2*6 + 3 + 3*6 = 37px at x=6)

            row1_y = 1
            pulse = 0.85 + 0.15 * math.sin(phase * 0.8)
            earth_color = tuple(min(255, int(c * pulse))
                                for c in ASTROPHAGE_BRIGHT)

            # "E" label
            _draw_tiny_label(image, "E", 1, row1_y + 0, LABEL_DIM)

            x = 6
            _draw_eridian_group(image, h6, x, row1_y, earth_color)
            x += len(h6) * (SYMBOL_W + SYMBOL_GAP) + 1
            _draw_separator(image, x, row1_y, ASTROPHAGE_DIM, blink_on)
            x += 2
            _draw_eridian_group(image, m6, x, row1_y, earth_color)

            # =========================================================
            # Scan line divider (y=8)
            # =========================================================
            _draw_scan_line(image, 8, t, ASTROPHAGE_BRIGHT, speed=18, width=10)

            # =========================================================
            # ROW 2: Eridian time -- 4 base-6 digits (y=10)
            # Eridian day = 1296 units, displayed as 4 symbols: XX:XX
            # =========================================================
            eridian_units = _earth_to_eridian_units(now)
            ed = _to_base6(eridian_units)
            while len(ed) < 4:
                ed.insert(0, 0)

            row2_y = 10
            pulse_r = 0.85 + 0.15 * math.sin(phase * 0.6 + 1.0)
            eridian_color = tuple(min(255, int(c * pulse_r))
                                  for c in ERIDIAN_METAL)

            # "R" label (for Rocky)
            _draw_tiny_label(image, "R", 1, row2_y + 0, ERIDIAN_DARK)

            x = 6
            # First 2 digits
            _draw_eridian_group(image, ed[:2], x, row2_y, eridian_color)
            x += 2 * (SYMBOL_W + SYMBOL_GAP) + 1
            _draw_separator(image, x, row2_y, ERIDIAN_DARK, blink_on)
            x += 2
            # Last 2 digits
            _draw_eridian_group(image, ed[2:], x, row2_y, eridian_color)

            # =========================================================
            # Scan line divider (y=17)
            # =========================================================
            _draw_scan_line(image, 17, t + 2.0, ASTROPHAGE_DIM,
                            speed=12, width=8)

            # =========================================================
            # ROW 3: Symbol legend -- all 6 Eridian digits (y=20)
            # =========================================================
            legend_y = 20
            legend_color = tuple(c // 2 for c in ASTROPHAGE_MED)
            for d in range(6):
                lx = 2 + d * (SYMBOL_W + 5)  # 10px per symbol cell
                _draw_eridian_digit(image, d, lx, legend_y, legend_color)
                # Small decimal label below each symbol
                from src.display._utils import _draw_digit
                _draw_digit(image, str(d), lx + 1, legend_y + 6,
                            tuple(c // 3 for c in legend_color))

            # =========================================================
            # Waveform -- Rocky's voice (y=30)
            # =========================================================
            _draw_waveform(image, 30, phase * 1.0, ASTROPHAGE_DIM,
                           amplitude=2, wavelength=18)
            _draw_waveform(image, 31, phase * 0.6 + 2.0,
                           tuple(c // 2 for c in ERIDIAN_METAL),
                           amplitude=1, wavelength=12)

            # =========================================================
            # Astrophage energy bar (y=36-37)
            # Fills based on seconds (0-59 -> 0-100%)
            # =========================================================
            bar_y = 36
            energy = (now.second + now.microsecond / 1e6) / 60.0
            bar_len = int(energy * (WIDTH - 4))
            for bx in range(2, 2 + bar_len):
                glow = 0.3 + 0.7 * (bx / WIDTH)
                pm = 0.9 + 0.1 * math.sin(phase + bx * 0.4)
                r = min(255, int(ASTROPHAGE_BRIGHT[0] * glow * pm))
                g = min(255, int(ASTROPHAGE_BRIGHT[1] * glow * pm * 0.7))
                b = min(255, int(ASTROPHAGE_BRIGHT[2] * glow * pm * 0.2))
                image.putpixel((bx, bar_y), (r, g, b))
                if bar_y + 1 < HEIGHT:
                    image.putpixel((bx, bar_y + 1), (r // 2, g // 2, b // 2))

            # =========================================================
            # Floating astrophage particles (bottom zone, y=44-54)
            # =========================================================
            for i, (ax, ay) in enumerate(astrophage_positions):
                drift_x = ax + int(2 * math.sin(t * 0.3 + i * 1.5))
                drift_y = ay + int(1 * math.cos(t * 0.25 + i * 2.0))
                drift_x = max(1, min(WIDTH - 2, drift_x))
                drift_y = max(40, min(HEIGHT - 8, drift_y))
                _draw_astrophage(image, drift_x, drift_y,
                                 phase + i, intensity=0.3)

            # =========================================================
            # Bottom: Earth decimal time (y=57)
            # =========================================================
            ref_y = HEIGHT - 7
            ref_str = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
            rx = (WIDTH - len(ref_str) * 4) // 2
            for i, ch in enumerate(ref_str):
                _draw_digit(image, ch, rx + i * 4, ref_y, BRACKET_COLOR)

            # Tau Ceti star glow (bottom right)
            tcx, tcy = WIDTH - 5, HEIGHT - 5
            sp = 0.5 + 0.5 * math.sin(t * 1.0)
            sr = int(180 * sp)
            sg = int(160 * sp)
            sb = int(90 * sp)
            if 0 <= tcx < WIDTH and 0 <= tcy < HEIGHT:
                image.putpixel((tcx, tcy), (sr, sg, sb))
                for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    px, py = tcx + ddx, tcy + ddy
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
