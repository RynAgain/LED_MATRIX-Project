"""
LED Matrix Simulator for development on non-Pi platforms.
Uses pygame to render a virtual 64x64 LED matrix in a desktop window.
"""

from .matrix import RGBMatrix, RGBMatrixOptions, FrameCanvas
from . import graphics

__all__ = ["RGBMatrix", "RGBMatrixOptions", "FrameCanvas", "graphics"]
