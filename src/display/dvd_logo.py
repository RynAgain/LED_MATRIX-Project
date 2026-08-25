#!/usr/bin/env python3
"""Bouncing "DVD" logo screensaver for a 64x64 LED matrix.

The classic screensaver: a logo drifts in a straight line, reflects off
whichever wall it meets, and changes colour on every bounce. Landing
exactly in a corner (both walls hit on the same frame) is the one thing
everyone actually watches for, so it also splits: the logo that hit the
corner is replaced by two smaller copies flying apart in a "V" from
that point, each free to bounce, change colour, and split again. A cap
keeps the swarm from growing without bound, and a minimum size keeps
the text readable -- once a logo can't shrink any further, a corner
hit still gets its ring fanfare, it just stops multiplying.

Split into pure state (``LogoState`` for one logo, ``LogoSwarm`` for
the population -- neither does any drawing, so both are trivial to
soak-test) and rendering (``_render`` for one logo, ``_render_scene``
for the swarm), the same split used by ``big_eye.py``.
"""

import time
import math
import random
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop
from src.display._fonts import _draw_text, _text_width

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 20

TEXT = "DVD"
SCALE = 2                                # the starting (largest) logo size
SPEED = 1.1                               # pixels per frame, per axis

MAX_LOGOS = 6                             # population cap for the swarm
MIN_SCALE = 1                             # font can't shrink below this
SPLIT_ANGLE = math.radians(28)            # half-angle of the post-split "V"

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


def _logo_dims(scale):
    """(width, height, border padding) in pixels for a logo at this scale."""
    pad = 3 if scale >= 2 else 2
    w = _text_width(TEXT, scale=scale) + pad * 2
    h = 7 * scale + pad * 2
    return w, h, pad


def _child_scale(scale):
    """The size a logo's children shrink to. Floors at MIN_SCALE so the
    text never becomes illegible -- logos already at the floor still
    split (the swarm keeps multiplying), they just stop shrinking."""
    return max(MIN_SCALE, scale - 1)


LOGO_W, LOGO_H, PAD = _logo_dims(SCALE)


class LogoState:
    """Position, velocity, colour and size of one bouncing logo.

    No drawing here -- ``update()`` is pure arithmetic so a long soak can
    run headless in a test without a real matrix or PIL canvas.
    """

    def __init__(self, bounds_w=WIDTH, bounds_h=HEIGHT, rng=None, scale=2,
                 spawn_center=None, velocity_angle=None):
        self.scale = scale
        self.w, self.h, self.pad = _logo_dims(scale)
        self.bounds_w = bounds_w
        self.bounds_h = bounds_h
        rng = rng or random

        if spawn_center is not None:
            cx, cy = spawn_center
            x, y = cx - self.w / 2.0, cy - self.h / 2.0
        else:
            x = rng.uniform(0, bounds_w - self.w)
            y = rng.uniform(0, bounds_h - self.h)
        # A child spawned right at a corner would otherwise sit half
        # off-panel; clamp it fully inside like any other bounce would.
        self.x = max(0.0, min(bounds_w - self.w, x))
        self.y = max(0.0, min(bounds_h - self.h, y))

        if velocity_angle is not None:
            self.vx = SPEED * math.cos(velocity_angle)
            self.vy = SPEED * math.sin(velocity_angle)
        else:
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


class LogoSwarm:
    """The population of logos on screen: one to start, more after splits.

    Pure state -- ``update()`` never draws anything, so the cap, the
    "V" split geometry and the size floor are all soak-testable headless.
    """

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.logos = [LogoState(rng=self.rng)]

    def update(self):
        corner_hitters = [lg for lg in self.logos if lg.update(rng=self.rng)]
        for parent in corner_hitters:
            self._maybe_split(parent)

    def _maybe_split(self, parent):
        """Replace a logo that just hit a corner with two smaller ones,
        unless the swarm is already at its population cap."""
        if len(self.logos) >= MAX_LOGOS:
            return   # still got its celebration; just no room to multiply

        child_scale = _child_scale(parent.scale)
        base_angle = math.atan2(parent.vy, parent.vx)
        children = [
            LogoState(bounds_w=parent.bounds_w, bounds_h=parent.bounds_h,
                      rng=self.rng, scale=child_scale,
                      spawn_center=parent.corner_pos,
                      velocity_angle=base_angle + sign * SPLIT_ANGLE)
            for sign in (-1, 1)
        ]
        # The parent is discarded, but its ring fanfare shouldn't be --
        # both children inherit it (fixed at the split point) so the
        # celebration keeps playing while they fly apart from it.
        for child in children:
            child.celebrating = parent.celebrating
            child.corner_pos = parent.corner_pos
        self.logos.remove(parent)
        self.logos.extend(children)


def _draw_logo(draw, state):
    """Draw one logo (and its corner-hit celebration, if active) onto an
    existing PIL draw context."""
    if state.celebrating > 0 and state.corner_pos:
        _draw_celebration(draw, state)

    x, y = int(round(state.x)), int(round(state.y))
    color = state.color
    draw.rounded_rectangle(
        [x, y, x + state.w - 1, y + state.h - 1],
        radius=min(3, state.scale + 1), outline=color, width=1)
    tx = x + (state.w - _text_width(TEXT, scale=state.scale)) // 2
    ty = y + (state.h - 7 * state.scale) // 2
    _draw_text(draw, TEXT, tx, ty, color, scale=state.scale)


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


def _render(state):
    """LogoState -> a 64x64 RGB frame with just that one logo."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    _draw_logo(draw, state)
    return img


def _render_scene(logos):
    """[LogoState, ...] -> a single 64x64 RGB frame with the whole swarm."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    for state in logos:
        _draw_logo(draw, state)
    return img


def run(matrix, duration=60):
    """Run the DVD-logo screensaver for the specified duration."""
    swarm = LogoSwarm()
    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()

            swarm.update()
            frame = _render_scene(swarm.logos)
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
