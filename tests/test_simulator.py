"""
Tests for the LED matrix simulator.
"""

import pytest
from src.simulator.matrix import RGBMatrix, RGBMatrixOptions, FrameCanvas, _PixelBuffer
from src.simulator.graphics import Color, Font, DrawText, DrawCircle, DrawLine


class TestPixelBuffer:
    """Tests for the pixel buffer."""

    def test_initial_state_is_black(self):
        buf = _PixelBuffer(64, 64)
        snapshot = buf.get_snapshot()
        assert snapshot[0][0] == (0, 0, 0)
        assert snapshot[63][63] == (0, 0, 0)

    def test_set_pixel(self):
        buf = _PixelBuffer(64, 64)
        buf.set_pixel(10, 20, 255, 0, 0)
        snapshot = buf.get_snapshot()
        assert snapshot[20][10] == (255, 0, 0)

    def test_set_pixel_out_of_bounds(self):
        buf = _PixelBuffer(64, 64)
        # Should not raise
        buf.set_pixel(-1, 0, 255, 0, 0)
        buf.set_pixel(0, -1, 255, 0, 0)
        buf.set_pixel(64, 0, 255, 0, 0)
        buf.set_pixel(0, 64, 255, 0, 0)

    def test_fill(self):
        buf = _PixelBuffer(64, 64)
        buf.fill(0, 255, 0)
        snapshot = buf.get_snapshot()
        assert snapshot[0][0] == (0, 255, 0)
        assert snapshot[32][32] == (0, 255, 0)

    def test_clear(self):
        buf = _PixelBuffer(64, 64)
        buf.fill(255, 255, 255)
        buf.clear()
        snapshot = buf.get_snapshot()
        assert snapshot[0][0] == (0, 0, 0)

    def test_set_from_image(self):
        from PIL import Image
        img = Image.new("RGB", (4, 4), color=(100, 150, 200))
        buf = _PixelBuffer(64, 64)
        buf.set_from_image(img, offset_x=5, offset_y=10)
        snapshot = buf.get_snapshot()
        assert snapshot[10][5] == (100, 150, 200)
        assert snapshot[13][8] == (100, 150, 200)
        # Outside image area should still be black
        assert snapshot[0][0] == (0, 0, 0)


class TestRGBMatrix:
    """Tests for the simulated RGBMatrix."""

    def test_creation_default(self):
        import os
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        m = RGBMatrix(rows=64)
        assert m.width == 64
        assert m.height == 64

    def test_creation_with_options(self):
        import os
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        opts = RGBMatrixOptions()
        opts.rows = 64
        opts.cols = 64
        m = RGBMatrix(options=opts)
        assert m.width == 64
        assert m.height == 64

    def test_set_pixel(self, matrix):
        matrix.SetPixel(0, 0, 255, 0, 0)
        # Should not raise

    def test_fill(self, matrix):
        matrix.Fill(0, 0, 255)
        # Should not raise

    def test_clear(self, matrix):
        matrix.Fill(255, 255, 255)
        matrix.Clear()
        # Should not raise

    def test_set_image(self, matrix):
        from PIL import Image
        img = Image.new("RGB", (64, 64), color=(128, 128, 128))
        matrix.SetImage(img)
        # Should not raise

    def test_create_frame_canvas(self, matrix):
        canvas = matrix.CreateFrameCanvas()
        assert isinstance(canvas, FrameCanvas)
        assert canvas.width == 64
        assert canvas.height == 64

    def test_swap_on_vsync(self, matrix):
        canvas = matrix.CreateFrameCanvas()
        canvas.SetPixel(10, 10, 255, 0, 0)
        new_canvas = matrix.SwapOnVSync(canvas)
        assert isinstance(new_canvas, FrameCanvas)

    def test_properties(self, matrix):
        assert matrix.brightness == 100
        matrix.brightness = 50  # No-op but should not raise
        assert matrix.luminanceCorrect is True
        matrix.luminanceCorrect = False  # No-op


class TestFrameCanvas:
    """Tests for the simulated FrameCanvas."""

    def test_fill(self, canvas):
        canvas.Fill(255, 0, 0)
        # Should not raise

    def test_clear(self, canvas):
        canvas.Clear()
        # Should not raise

    def test_set_pixel(self, canvas):
        canvas.SetPixel(32, 32, 0, 255, 0)
        # Should not raise

    def test_set_image(self, canvas):
        from PIL import Image
        img = Image.new("RGB", (64, 64), color=(64, 64, 64))
        canvas.SetImage(img)

    def test_properties(self, canvas):
        assert canvas.width == 64
        assert canvas.height == 64
        assert canvas.pwmBits == 11
        assert canvas.brightness == 100


class TestGraphics:
    """Tests for the simulated graphics module."""

    def test_color_creation(self):
        c = Color(255, 128, 0)
        assert c.red == 255
        assert c.green == 128
        assert c.blue == 0

    def test_color_repr(self):
        c = Color(255, 0, 128)
        assert "255" in repr(c)
        assert "128" in repr(c)

    def test_font(self):
        f = Font()
        f.LoadFont("some_font.bdf")
        assert f.height > 0
        assert f.baseline > 0
        assert f.CharacterWidth(ord('A')) > 0

    def test_draw_text(self, canvas):
        c = Color(255, 255, 255)
        f = Font()
        f.LoadFont("test.bdf")
        result = DrawText(canvas, f, 0, 10, c, "Hello")
        assert result > 0

    def test_draw_circle(self, canvas):
        c = Color(255, 0, 0)
        DrawCircle(canvas, 32, 32, 10, c)
        # Should not raise

    def test_draw_line(self, canvas):
        c = Color(0, 255, 0)
        DrawLine(canvas, 0, 0, 63, 63, c)
        # Should not raise
