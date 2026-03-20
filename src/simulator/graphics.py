#!/usr/bin/env python3
"""
Simulated rgbmatrix.graphics module for development.
Provides Color, Font, DrawText, DrawCircle, DrawLine matching the real API.
Uses PIL for actual drawing when needed.
"""

import math


class Color:
    """Simulated rgbmatrix.graphics.Color."""

    def __init__(self, red=0, green=0, blue=0):
        self.red = red
        self.green = green
        self.blue = blue

    def __repr__(self):
        return f"Color(red={self.red}, green={self.green}, blue={self.blue})"


class Font:
    """Simulated rgbmatrix.graphics.Font."""

    def __init__(self):
        self._height = 0
        self._baseline = 0
        self._file = None

    def LoadFont(self, file):
        """Load a BDF font file (simulated - just stores the path)."""
        self._file = file
        # Approximate common BDF font metrics
        self._height = 8
        self._baseline = 6

    @property
    def height(self):
        return self._height

    @property
    def baseline(self):
        return self._baseline

    def CharacterWidth(self, char):
        """Return character width (approximate)."""
        return 6

    def DrawGlyph(self, canvas, x, y, color, char):
        """Draw a single glyph (simplified)."""
        return x + self.CharacterWidth(char)


def DrawText(canvas, font, x, y, color, text):
    """
    Draw text on canvas using the font.
    Simplified: draws each character as a block of colored pixels.
    """
    cursor_x = x
    char_w = 6
    char_h = font.height if font else 8

    for ch in str(text):
        if ch == ' ':
            cursor_x += char_w
            continue
        # Draw a simplified character representation
        for cy in range(min(char_h, 8)):
            for cx in range(min(char_w - 1, 5)):
                px = cursor_x + cx
                py = y - char_h + cy + 1
                if hasattr(canvas, 'SetPixel'):
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
