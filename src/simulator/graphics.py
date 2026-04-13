#!/usr/bin/env python3
"""
Simulated rgbmatrix.graphics module for development.
Provides Color, Font, DrawText, DrawCircle, DrawLine matching the real API.
Uses PIL for actual drawing when needed.
"""

import math
import os

# Minimal 5x7 bitmap font for A-Z, 0-9, and common punctuation.
# Each character is a list of 7 rows, each row is 5 bits wide (MSB = leftmost pixel).
FONT_5X7 = {
    "A": [0x04, 0x0A, 0x11, 0x11, 0x1F, 0x11, 0x11],
    "B": [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    "C": [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    "D": [0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "F": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    "G": [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F],
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "I": [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "J": [0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
    "K": [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "M": [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    "N": [0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "P": [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    "Q": [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    "R": [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    "S": [0x0E, 0x11, 0x10, 0x0E, 0x01, 0x11, 0x0E],
    "T": [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    "U": [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "V": [0x11, 0x11, 0x11, 0x11, 0x0A, 0x0A, 0x04],
    "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
    "X": [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    "Y": [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    "Z": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F],
    "3": [0x0E, 0x11, 0x01, 0x06, 0x01, 0x11, 0x0E],
    "4": [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    "5": [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    "6": [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    "7": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    "8": [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    "9": [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    ".": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04],
    ",": [0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x08],
    ":": [0x00, 0x00, 0x04, 0x00, 0x00, 0x04, 0x00],
    "-": [0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00],
    "!": [0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04],
    "?": [0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04],
    "/": [0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10],
    "$": [0x04, 0x0F, 0x14, 0x0E, 0x05, 0x1E, 0x04],
    "%": [0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03],
    "+": [0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00],
    "=": [0x00, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00],
    "(": [0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02],
    ")": [0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08],
    " ": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
}


class Color:
    """Simulated rgbmatrix.graphics.Color."""

    def __init__(self, red=0, green=0, blue=0):
        self.red = max(0, min(255, int(red)))
        self.green = max(0, min(255, int(green)))
        self.blue = max(0, min(255, int(blue)))

    def __repr__(self):
        return f"Color(red={self.red}, green={self.green}, blue={self.blue})"


class Font:
    """Simulated rgbmatrix.graphics.Font."""

    def __init__(self):
        self._height = 0
        self._baseline = 0
        self._file = None
        self.char_width = 6  # default width (5 + 1 spacing)

    def LoadFont(self, path):
        """Load a BDF font file (simulated - parses metrics from filename)."""
        self.path = path
        # Default metrics
        self._height = 8
        self._baseline = 6
        # Try to infer metrics from filename pattern like "4x6.bdf", "7x13.bdf"
        basename = os.path.basename(path)
        name = os.path.splitext(basename)[0]
        parts = name.split("x")
        if len(parts) == 2:
            try:
                self.char_width = int(parts[0]) + 1  # +1 for spacing
                self._height = int(parts[1])
                self._baseline = int(self._height * 0.75)
            except ValueError:
                pass  # Keep defaults

    @property
    def height(self):
        return self._height

    @property
    def baseline(self):
        return self._baseline

    def CharacterWidth(self, char):
        """Return character width."""
        return self.char_width

    def DrawGlyph(self, canvas, x, y, color, char):
        """Draw a single glyph (simplified)."""
        return x + self.CharacterWidth(char)


def DrawText(canvas, font, x, y, color, text):
    """
    Draw text on canvas using the font.
    Uses FONT_5X7 bitmap patterns for known characters, falls back to a
    solid block for unknown characters.
    """
    cursor_x = x
    char_w = font.char_width if font else 6
    char_h = font.height if font else 8

    # Scale factors for fonts larger than 5x7
    glyph_w = 5  # native bitmap width
    glyph_h = 7  # native bitmap height
    scale_x = max(1, (char_w - 1) // glyph_w)  # -1 for spacing
    scale_y = max(1, char_h // glyph_h)

    for ch in str(text):
        # Map lowercase to uppercase for lookup
        lookup = ch.upper() if ch.islower() else ch

        bitmap = FONT_5X7.get(lookup)
        if bitmap is not None:
            # Render actual character shape from bitmap
            for row_idx, row_bits in enumerate(bitmap):
                for col_idx in range(glyph_w):
                    if row_bits & (1 << (glyph_w - 1 - col_idx)):
                        # Pixel is set -- draw scaled pixel(s)
                        for sy in range(scale_y):
                            for sx in range(scale_x):
                                px = cursor_x + col_idx * scale_x + sx
                                py = y - char_h + row_idx * scale_y + sy + 1
                                if hasattr(canvas, "SetPixel"):
                                    canvas.SetPixel(
                                        px, py, color.red, color.green, color.blue
                                    )
        else:
            # Unknown character -- fall back to solid block
            for cy in range(min(char_h, 8)):
                for cx in range(min(char_w - 1, 5)):
                    px = cursor_x + cx
                    py = y - char_h + cy + 1
                    if hasattr(canvas, "SetPixel"):
                        canvas.SetPixel(px, py, color.red, color.green, color.blue)

        cursor_x += char_w

    return cursor_x


def DrawCircle(canvas, x, y, radius, color):
    """Draw a circle outline on the canvas."""
    for angle_deg in range(360):
        angle = math.radians(angle_deg)
        px = int(round(x + radius * math.cos(angle)))
        py = int(round(y + radius * math.sin(angle)))
        if hasattr(canvas, 'SetPixel'):
            canvas.SetPixel(px, py, color.red, color.green, color.blue)


def DrawLine(canvas, x1, y1, x2, y2, color):
    """Draw a line on the canvas using Bresenham's algorithm."""
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx - dy

    while True:
        if hasattr(canvas, 'SetPixel'):
            canvas.SetPixel(x1, y1, color.red, color.green, color.blue)
        if x1 == x2 and y1 == y2:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x1 += sx
        if e2 < dx:
            err += dx
            y1 += sy
