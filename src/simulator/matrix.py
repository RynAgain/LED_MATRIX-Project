#!/usr/bin/env python3
"""
Pygame-based LED Matrix Simulator.
Provides the same API as rgbmatrix.RGBMatrix / FrameCanvas for development.
Renders a 64x64 LED matrix in a desktop window using pygame.
"""

import os
import sys
import threading
import logging

logger = logging.getLogger(__name__)

# Pygame is optional - only needed when simulator is actually used
try:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logger.warning("pygame not installed -- simulator will run headless (no visual output)")

# Simulator configuration
PIXEL_SIZE = 8       # Size of each LED pixel in screen pixels
PIXEL_GAP = 1        # Gap between LED pixels
MATRIX_SIZE = 64     # 64x64 matrix
WINDOW_TITLE = "LED Matrix Simulator (64x64)"
BG_COLOR = (20, 20, 20)  # Dark gray background between pixels
FPS_CAP = 60         # Max frames per second for the display window


class _PixelBuffer:
    """Thread-safe pixel buffer for the simulated matrix."""

    def __init__(self, width=MATRIX_SIZE, height=MATRIX_SIZE):
        self.width = width
        self.height = height
        self._pixels = [[(0, 0, 0)] * width for _ in range(height)]
        self._lock = threading.Lock()

    def set_pixel(self, x, y, r, g, b):
        if 0 <= x < self.width and 0 <= y < self.height:
            with self._lock:
                self._pixels[y][x] = (r, g, b)

    def fill(self, r, g, b):
        with self._lock:
            for y in range(self.height):
                for x in range(self.width):
                    self._pixels[y][x] = (r, g, b)

    def clear(self):
        self.fill(0, 0, 0)

    def get_snapshot(self):
        """Return a copy of the current pixel state."""
        with self._lock:
            return [row[:] for row in self._pixels]

    def set_from_image(self, image, offset_x=0, offset_y=0):
        """Set pixels from a PIL Image."""
        try:
            if image.mode != "RGB":
                image = image.convert("RGB")
            pixels = image.load()
            img_w, img_h = image.size
            with self._lock:
                for y in range(min(img_h, self.height - offset_y)):
                    for x in range(min(img_w, self.width - offset_x)):
                        tx, ty = x + offset_x, y + offset_y
                        if 0 <= tx < self.width and 0 <= ty < self.height:
                            r, g, b = pixels[x, y]
                            self._pixels[ty][tx] = (r, g, b)
        except Exception as e:
            logger.error("Failed to set image on pixel buffer: %s", e)


class _SimulatorWindow:
    """Manages the pygame window for rendering the LED matrix."""

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """Get or create the singleton simulator window."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._running = False
        self._screen = None
        self._clock = None
        self._initialized = False

    def _ensure_init(self):
        """Initialize pygame if not already done."""
        if self._initialized or not PYGAME_AVAILABLE:
            return

        try:
            pygame.init()
            cell = PIXEL_SIZE + PIXEL_GAP
            win_w = MATRIX_SIZE * cell + PIXEL_GAP
            win_h = MATRIX_SIZE * cell + PIXEL_GAP
            self._screen = pygame.display.set_mode((win_w, win_h))
            pygame.display.set_caption(WINDOW_TITLE)
            self._clock = pygame.time.Clock()
            self._initialized = True
            self._running = True
            logger.info("Simulator window opened (%dx%d px)", win_w, win_h)
        except Exception as e:
            logger.error("Failed to initialize pygame: %s", e)
            self._initialized = False

    def render(self, pixel_buffer):
        """Render the pixel buffer to the pygame window."""
        if not PYGAME_AVAILABLE or not self._initialized:
            return

        # Process pygame events (needed to keep window responsive)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
                return

        if not self._running:
            return

        snapshot = pixel_buffer.get_snapshot()
        cell = PIXEL_SIZE + PIXEL_GAP

        self._screen.fill(BG_COLOR)

        for y in range(MATRIX_SIZE):
            for x in range(MATRIX_SIZE):
                color = snapshot[y][x]
                rect = pygame.Rect(
                    PIXEL_GAP + x * cell,
                    PIXEL_GAP + y * cell,
                    PIXEL_SIZE,
                    PIXEL_SIZE
                )
                self._screen.fill(color, rect)

        pygame.display.flip()
        self._clock.tick(FPS_CAP)

    def close(self):
        """Close the simulator window."""
        if PYGAME_AVAILABLE and self._initialized:
            try:
                pygame.quit()
            except Exception:
                pass
            self._initialized = False
            self._running = False


class FrameCanvas:
    """Simulated FrameCanvas matching the rgbmatrix.FrameCanvas API."""

    def __init__(self, width=MATRIX_SIZE, height=MATRIX_SIZE):
        self._buffer = _PixelBuffer(width, height)
        self._width = width
        self._height = height

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def pwmBits(self):
        return 11

    @pwmBits.setter
    def pwmBits(self, value):
        pass  # No-op in simulator

    @property
    def brightness(self):
        return 100

    @brightness.setter
    def brightness(self, value):
        pass  # No-op in simulator

    def Fill(self, red, green, blue):
        self._buffer.fill(red, green, blue)

    def Clear(self):
        self._buffer.clear()

    def SetPixel(self, x, y, red, green, blue):
        self._buffer.set_pixel(x, y, red, green, blue)

    def SetImage(self, image, offset_x=0, offset_y=0, unsafe=True):
        self._buffer.set_from_image(image, offset_x, offset_y)

    def SetPixelsPillow(self, xstart, ystart, width, height, image):
        self._buffer.set_from_image(image, xstart, ystart)


class RGBMatrixOptions:
    """Simulated RGBMatrixOptions matching the rgbmatrix.RGBMatrixOptions API."""

    def __init__(self):
        self.hardware_mapping = "regular"
        self.rows = 64
        self.cols = 64
        self.chain_length = 1
        self.parallel = 1
        self.pwm_bits = 11
        self.pwm_lsb_nanoseconds = 130
        self.brightness = 100
        self.scan_mode = 0
        self.multiplexing = 0
        self.row_address_type = 0
        self.disable_hardware_pulsing = False
        self.show_refresh_rate = False
        self.inverse_colors = False
        self.led_rgb_sequence = "RGB"
        self.pixel_mapper_config = ""
        self.panel_type = ""
        self.pwm_dither_bits = 0
        self.limit_refresh_rate_hz = 0
        self.gpio_slowdown = 4
        self.daemon = False
        self.drop_privileges = True
        self.drop_priv_user = ""
        self.drop_priv_group = ""


class RGBMatrix:
    """
    Simulated RGBMatrix matching the rgbmatrix.RGBMatrix API.
    Renders to a pygame window instead of hardware GPIO.
    """

    def __init__(self, rows=0, chains=0, parallel=0, options=None):
        if options is not None:
            self._rows = options.rows
            self._cols = options.cols
        else:
            self._rows = rows if rows > 0 else MATRIX_SIZE
            self._cols = MATRIX_SIZE

        self._buffer = _PixelBuffer(self._cols, self._rows)
        self._window = _SimulatorWindow.get_instance()
        self._window._ensure_init()

        # Render initial blank state
        self._window.render(self._buffer)

        logger.info("LED Matrix Simulator initialized (%dx%d)", self._cols, self._rows)

    @property
    def width(self):
        return self._cols

    @property
    def height(self):
        return self._rows

    @property
    def luminanceCorrect(self):
        return True

    @luminanceCorrect.setter
    def luminanceCorrect(self, value):
        pass

    @property
    def pwmBits(self):
        return 11

    @pwmBits.setter
    def pwmBits(self, value):
        pass

    @property
    def brightness(self):
        return 100

    @brightness.setter
    def brightness(self, value):
        pass

    def Fill(self, red, green, blue):
        self._buffer.fill(red, green, blue)
        self._window.render(self._buffer)

    def Clear(self):
        self._buffer.clear()
        self._window.render(self._buffer)

    def SetPixel(self, x, y, red, green, blue):
        self._buffer.set_pixel(x, y, red, green, blue)

    def SetImage(self, image, offset_x=0, offset_y=0, unsafe=True):
        self._buffer.set_from_image(image, offset_x, offset_y)
        self._window.render(self._buffer)

    def SetPixelsPillow(self, xstart, ystart, width, height, image):
        self._buffer.set_from_image(image, xstart, ystart)
        self._window.render(self._buffer)

    def CreateFrameCanvas(self):
        canvas = FrameCanvas(self._cols, self._rows)
        return canvas

    def SwapOnVSync(self, canvas, framerate_fraction=1):
        """Swap the frame canvas to display. In simulator, copy canvas buffer to display."""
        # Copy canvas pixels to main buffer
        snapshot = canvas._buffer.get_snapshot()
        with self._buffer._lock:
            for y in range(self._rows):
                for x in range(self._cols):
                    self._buffer._pixels[y][x] = snapshot[y][x]
        self._window.render(self._buffer)
        # Return a new canvas for the next frame (simulates double buffering)
        new_canvas = FrameCanvas(self._cols, self._rows)
        return new_canvas

    def __del__(self):
        """Cleanup when the matrix is destroyed."""
        try:
            self._buffer.clear()
        except Exception:
            pass
