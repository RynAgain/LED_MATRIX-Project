"""
Python bindings for rpi-rgb-led-matrix library.
Vendored from https://github.com/hzeller/rpi-rgb-led-matrix
"""

__version__ = "0.1.0"

from .core import RGBMatrix, RGBMatrixOptions, FrameCanvas

__all__ = ["RGBMatrix", "RGBMatrixOptions", "FrameCanvas"]
