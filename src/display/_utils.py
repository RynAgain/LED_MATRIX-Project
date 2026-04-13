"""Shared bitmap digit font and color utility functions for LED matrix display modules."""

import math

# 3x5 pixel digit font bitmaps.
# Each digit is a list of 5 rows; each row is a 3-bit integer (MSB = leftmost pixel).
DIGITS = {
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
    ':': [0b000, 0b010, 0b000, 0b010, 0b000],
}


def _draw_digit(image, ch, x, y, color, size=64):
    """Draw a 3x5 pixel digit on a PIL Image.

    Args:
        image: PIL Image instance.
        ch: Single character to render ('0'-'9').
        x, y: Top-left position.
        color: RGB tuple.
        size: Matrix dimension for bounds checking.
    """
    rows = DIGITS.get(ch, DIGITS['0'])
    for ri, bits in enumerate(rows):
        for ci in range(3):
            if bits & (1 << (2 - ci)):
                px, py = x + ci, y + ri
                if 0 <= px < size and 0 <= py < size:
                    image.putpixel((px, py), color)


def _draw_number(image, number, x, y, color, size=64):
    """Draw a multi-digit number on a PIL Image.

    Args:
        image: PIL Image instance.
        number: Integer to render.
        x, y: Top-left position of the first digit.
        color: RGB tuple.
        size: Matrix dimension for bounds checking.
    """
    digits = str(number)
    for i, ch in enumerate(digits):
        _draw_digit(image, ch, x + i * 4, y, color, size)


def _lerp_color(c1, c2, t):
    """Linearly interpolate between two RGB color tuples.

    Args:
        c1: Start color (r, g, b).
        c2: End color (r, g, b).
        t: Interpolation factor (0.0 = c1, 1.0 = c2), clamped to [0, 1].

    Returns:
        Interpolated (r, g, b) tuple.
    """
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _scale_color(color, factor):
    """Scale an RGB color by a brightness factor.

    Args:
        color: (r, g, b) tuple.
        factor: Multiplier (0.0 = black, 1.0 = unchanged).

    Returns:
        Scaled (r, g, b) tuple, clamped to [0, 255].
    """
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def _hsv_to_rgb(h, s, v):
    """Convert HSV color to RGB.

    Args:
        h: Hue in [0, 1).
        s: Saturation in [0, 1].
        v: Value (brightness) in [0, 1].

    Returns:
        (r, g, b) tuple with values in [0, 255].
    """
    if s == 0.0:
        c = int(v * 255)
        return (c, c, c)
    h_sector = h * 6.0
    i = int(h_sector)
    f = h_sector - i
    p = int(v * (1.0 - s) * 255)
    q = int(v * (1.0 - s * f) * 255)
    t = int(v * (1.0 - s * (1.0 - f)) * 255)
    v_int = int(v * 255)
    i %= 6
    if i == 0:
        return (v_int, t, p)
    if i == 1:
        return (q, v_int, p)
    if i == 2:
        return (p, v_int, t)
    if i == 3:
        return (p, q, v_int)
    if i == 4:
        return (t, p, v_int)
    return (v_int, p, q)
