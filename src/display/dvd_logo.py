#!/usr/bin/env python3
"""Bouncing "DVD" logo screensaver for a 64x64 LED matrix.

The classic screensaver: a logo drifts in a straight line, reflects off
whichever wall it meets, and changes colour on every bounce. Landing
exactly in a corner (both walls hit on the same frame) is the one thing
everyone actually watches for, so it gets its own little celebration.

Split into pure state (``LogoState``, integer-free of any drawing calls
so it is trivial to unit test) and rendering (``_render``), the same
split used by ``big_eye.py``.
"""

import time
import random
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop
from src.display._fonts import _draw_text, _text_width

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 20

TEXT = "DVD"
SCALE = 2
PAD = 3                                  # border padding around the text
LOGO_W = _text_width(TEXT, scale=SCALE) + PAD * 2
LOGO_H = 7 * SCALE + PAD * 2

SPEED = 1.1                              # pixels per frame, per axis

COLORS = [
    (230, 40, 40),      # red
    (40, 120, 230),     # blue
    (40, 200, 90),      # green
    (230, 200, 30),     # yellow
    (200, 50, 200),     # magenta
    (40, 210, 210),     # cyan
    (230, 130, 30),     # orange
    (235, 235, 235),    # white
]

CELEBRATION_FRAMES = 24                  # ~1.2s of corner-hit fanfare


class LogoState:
    """Position, velocity and colour of the bouncing logo.

    No drawing here -- ``update()`` is pure arithmetic so a long soak can
    run headless in a test without a real matrix or PIL canvas.
    """

    def __init__(self, w=LOGO_W, h=LOGO_H, bounds_w=WIDTH, bounds_h=HEIGHT,
                 rng=None):
        self.w = w
        self.h = h
        self.bounds_w = bounds_w
        self.bounds_h = bounds_h
        rng = rng or random
        self.x = rng.uniform(0, bounds_w - w)
        self.y = rng.uniform(0, bounds_h - h)
        self.vx = SPEED if rng.random() < 0.5 else -SPEED
        self.vy = SPEED if rng.random() < 0.5 else -SPEED
        self.color_idx = rng.randrange(len(COLORS))
        self.celebrating = 0             # frames left in a corner fanfare
        self.corner_pos = None           # (x, y) of the last corner hit

    @property
    def color(self):
        return COLORS[self.color_idx % len(COLORS)]

    def _next_color(self, rng):
        # Never repeat the colour that's already showing.
        choices = [i for i in range(len(COLORS)) if i != self.color_idx]
        self.color_idx = rng.choice(choices)

    def update(self, rng=None):
        """Advance one frame. Returns True if a corner hit fired this frame."""
        rng = rng or random
        self.x += self.vx
        self.y += self.vy

        hit_x = hit_y = False
        if self.x <= 0:
            self.x = 0
            self.vx = abs(self.vx)
            hit_x = True
        elif self.x + self.w >= self.bounds_w:
            self.x = self.bounds_w - self.w
            self.vx = -abs(self.vx)
            hit_x = True

        if self.y <= 0:
            self.y = 0
            self.vy = abs(self.vy)
            hit_y = True
        elif self.y + self.h >= self.bounds_h:
            self.y = self.bounds_h - self.h
            self.vy = -abs(self.vy)
            hit_y = True

        if hit_x or hit_y:
            self._next_color(rng)

        corner_hit = hit_x and hit_y
        if corner_hit:
            self.celebrating = CELEBRATION_FRAMES
            self.corner_pos = (self.x + self.w / 2, self.y + self.h / 2)
        elif self.celebrating > 0:
            self.celebrating -= 1

        return corner_hit


def _render(state):
    """LogoState -> a 64x64 RGB frame."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    if state.celebrating > 0 and state.corner_pos:
        _draw_celebration(draw, state)

    x, y = int(round(state.x)), int(round(state.y))
    color = state.color
    draw.rounded_rectangle(
        [x, y, x + state.w - 1, y + state.h - 1],
        radius=3, outline=color, width=1)
    tx = x + (state.w - _text_width(TEXT, scale=SCALE)) // 2
    ty = y + (state.h - 7 * SCALE) // 2
    _draw_text(draw, TEXT, tx, ty, color, scale=SCALE)

    return img


def _draw_celebration(draw, state):
    """Radiating rings from the corner, fading out over the fanfare."""
    cx, cy = state.corner_pos
    progress = 1.0 - (state.celebrating / CELEBRATION_FRAMES)
    for ring in range(3):
        r = progress * 40 + ring * 10
        if r <= 0 or r > 46:
            continue
        fade = max(0, 1.0 - (r / 46))
        c = tuple(int(ch * fade) for ch in state.color)
        if sum(c) < 6:
            continue
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c)


def run(matrix, duration=60):
    """Run the DVD-logo screensaver for the specified duration."""
    state = LogoState()
    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()

            state.update()
            frame = _render(state)
            matrix.SetImage(frame)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception:
        logger.error("Error in dvd_logo demo", exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass


if __name__ == "__main__":
    print("This module should be imported and used with the LED matrix.")
    print("Please run src/main.py instead.")
