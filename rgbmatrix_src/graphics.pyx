# cython: language_level=3str
# distutils: language = c++

from libcpp cimport bool
from libc.stdint cimport uint8_t, uint32_t

from . cimport core

cdef class Color:
    def __init__(self, uint8_t red = 0, uint8_t green = 0, uint8_t blue = 0):
        self.__color.r = red
        self.__color.g = green
        self.__color.b = blue

    @property
    def red(self):
        return self.__color.r

    @red.setter
    def red(self, uint8_t value):
        self.__color.r = value

    @property
    def green(self):
        return self.__color.g

    @green.setter
    def green(self, uint8_t value):
        self.__color.g = value

    @property
    def blue(self):
        return self.__color.b

    @blue.setter
    def blue(self, uint8_t value):
        self.__color.b = value

    def __repr__(self):
        return f"Color(red={self.__color.r}, green={self.__color.g}, blue={self.__color.b})"

cdef class Font:
    def CharacterWidth(self, uint32_t char):
        return self.__font.CharacterWidth(char)

    def LoadFont(self, file):
        if (not self.__font.LoadFont(file.encode('utf-8'))):
            raise Exception("Couldn't load font " + file)

    def DrawGlyph(self, core.Canvas c, int x, int y, Color color, uint32_t char):
        return self.__font.DrawGlyph(c._getCanvas(), x, y, color.__color, char)

    @property
    def height(self):
        return self.__font.height()

    @property
    def baseline(self):
        return self.__font.baseline()

def DrawText(core.Canvas c not None, Font f not None, int x, int y, Color color not None, text, Color background=None, int kerning_offset=0):
    """Draw text on the canvas.

    Args:
        c: Canvas to draw on.
        f: Font to use.
        x: X position.
        y: Y position.
        color: Text color.
        text: String to draw.
        background: Optional background color.
        kerning_offset: Optional kerning adjustment (default 0).

    Returns:
        The x position after the last character.
    """
    cdef const char* c_text
    text_bytes = text.encode('utf-8') if isinstance(text, str) else text
    c_text = text_bytes

    if background is not None:
        return cppinc.DrawText(c._getCanvas(), f.__font, x, y, color.__color, &background.__color, c_text, kerning_offset)
    else:
        return cppinc.DrawText(c._getCanvas(), f.__font, x, y, color.__color, <cppinc.Color*>NULL, c_text, kerning_offset)

def VerticalDrawText(core.Canvas c not None, Font f not None, int x, int y, Color color not None, text, int kerning_offset=0):
    """Draw text vertically on the canvas.

    Args:
        c: Canvas to draw on.
        f: Font to use.
        x: X position.
        y: Y position.
        color: Text color.
        text: String to draw.
        kerning_offset: Optional kerning adjustment (default 0).

    Returns:
        The y position after the last character.
    """
    cdef const char* c_text
    text_bytes = text.encode('utf-8') if isinstance(text, str) else text
    c_text = text_bytes
    return cppinc.VerticalDrawText(c._getCanvas(), f.__font, x, y, color.__color, c_text, kerning_offset)

def DrawCircle(core.Canvas c, int x, int y, int r, Color color):
    cppinc.DrawCircle(c._getCanvas(), x, y, r, color.__color)

def DrawLine(core.Canvas c, int x1, int y1, int x2, int y2, Color color):
    cppinc.DrawLine(c._getCanvas(), x1, y1, x2, y2, color.__color)

# Local Variables:
# mode: python
# End:
