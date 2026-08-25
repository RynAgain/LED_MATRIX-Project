#!/usr/bin/env python3
"""Halloween jack-o'-lantern for a 64x64 LED matrix.

A carved pumpkin glows against a night sky: the candle inside flickers
(a smoothed random walk, occasionally gusting dim), the face swaps
between a handful of carved expressions every several seconds with a
blink in between, and a bat periodically flaps across the sky.

Rendering follows the same split as ``big_eye.py``: everything that
never changes (sky gradient, moon, static pumpkin rind/ridges/stem) is
pre-rendered once into a single base layer; each frame only redraws the
bat and the face cutouts on top of a copy of that layer.

State (``PumpkinState``, ``Bat``) is pure ``dt``-based arithmetic with
no drawing calls, so long soaks are testable headlessly.
"""

import time
import math
import random
import logging

from PIL import Image, ImageDraw

from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 24

# --- Sky ---------------------------------------------------------------
SKY_TOP = (6, 4, 16)
SKY_BOTTOM = (22, 11, 36)
MOON_CENTER = (52, 11)
MOON_R = 7
MOON_COLOR = (246, 243, 214)
MOON_SHADOW = (198, 194, 166)
STAR_COLOR = (255, 255, 240)
BAT_COLOR = (96, 84, 120)          # light enough to read against night sky
STARS = [
    (x, y, phase)
    for x, y, phase in (
        (4, 6, 0.0), (14, 3, 1.1), (24, 9, 2.3), (36, 5, 0.4),
        (60, 24, 3.1), (8, 18, 1.7), (44, 4, 2.8), (30, 15, 0.9),
        (18, 25, 4.2), (62, 8, 5.0), (2, 29, 2.1),
    )
]

# --- Pumpkin body --------------------------------------------------------
PUMPKIN_CX, PUMPKIN_CY = 32, 39
PUMPKIN_RX, PUMPKIN_RY = 24, 18
# Deep orange body so the lit face reads as much brighter than the rind.
RIND = (176, 70, 8)
RIND_SHADOW = (112, 40, 4)         # outer edge, gives the body its roundness
RIND_HILITE = (214, 104, 20)       # subtle centre sheen (kept off the face)
CARVE_EDGE = (34, 12, 2)           # dark cut edge: separates glow from rind
STEM = (96, 132, 52)
STEM_SHADOW = (58, 86, 30)

# Candle: even at its dimmest the face must stay clearly brighter than
# the rind, so the low end is still a strong orange, not a dark ember.
GLOW_LOW = (255, 146, 26)
GLOW_HOT = (255, 246, 176)

FLICKER_MIN, FLICKER_MAX = 0.72, 1.0
BLINK_SPEED = 3.2                 # phase units / second

# --- Expressions ---------------------------------------------------------
# Each shape is either ("poly", [(dx, dy), ...]) or ("circle", dx, dy, r),
# offsets relative to (PUMPKIN_CX, PUMPKIN_CY). Eyes are given for the
# right side only; the left eye mirrors dx -> -dx.
EXPRESSIONS = [
    {   # classic grin: chunky slanted eyes, wide toothy smile
        "eye": ("poly", [(5, -10), (17, -2), (5, 2)]),
        "nose": ("poly", [(0, 2), (5, 9), (-5, 9)]),
        "mouth": ("poly", [(-13, 7), (13, 7), (9, 15), (-9, 15)]),
        "teeth": [(-6, 7, -3, 11), (2, 7, 5, 11), (-2, 12, 1, 15)],
    },
    {   # surprised: big round eyes and a round "O"
        "eye": ("circle", 12, -4, 6),
        "nose": ("poly", [(0, 1), (5, 7), (-5, 7)]),
        "mouth": ("circle", 0, 10, 5),
        "teeth": [],
    },
    {   # angry: heavy downward-slanted brows, jagged frown
        "eye": ("poly", [(4, -10), (17, -4), (17, 2), (7, -2)]),
        "nose": ("poly", [(0, 2), (5, 9), (-5, 9)]),
        "mouth": ("poly", [(-12, 8), (12, 8), (12, 15), (-12, 15)]),
        "teeth": [(-8, 8, -5, 13), (-1, 8, 2, 13), (6, 8, 9, 13)],
    },
]


def _lerp(a, b, t):
    return a + (b - a) * t


def _lerp_color(c0, c1, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(_lerp(a, b, t))) for a, b in zip(c0, c1))


def _flatten_shape(shape, factor):
    """Scale a shape's vertical extent toward its own centre.

    ``factor`` 1.0 leaves it alone; 0.0 collapses it to a horizontal
    slit -- used to close an eye during a blink.
    """
    kind = shape[0]
    if kind == "circle":
        _, dx, dy, r = shape
        return ("circle", dx, dy, max(0.5, r * factor))
    _, points = shape
    ys = [p[1] for p in points]
    cy = sum(ys) / len(ys)
    return ("poly", [(x, cy + (y - cy) * factor) for x, y in points])


def _mirror_shape(shape):
    kind = shape[0]
    if kind == "circle":
        _, dx, dy, r = shape
        return ("circle", -dx, dy, r)
    _, points = shape
    return ("poly", [(-x, y) for x, y in points])


def _draw_shape(draw, shape, cx, cy, color, edge=CARVE_EDGE):
    """Fill a cutout in ``color`` with a 1px dark carved edge around it.

    The edge is what makes the lit face legible: without it the glow
    bleeds into the rind and the whole pumpkin reads as one orange blob.
    """
    kind = shape[0]
    if kind == "circle":
        _, dx, dy, r = shape
        x, y = cx + dx, cy + dy
        if r < 0.5:
            return
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=edge)
    else:
        _, points = shape
        pts = [(cx + x, cy + y) for x, y in points]
        draw.polygon(pts, fill=color, outline=edge)


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

class Bat:
    """A bat that flaps across the sky once, then is discarded."""

    def __init__(self, rng):
        left_to_right = rng.random() < 0.5
        self.dir = 1 if left_to_right else -1
        self.x = -8.0 if left_to_right else float(WIDTH + 8)
        self.y = rng.uniform(3, 17)
        self.speed = rng.uniform(9.0, 16.0)     # px / second
        self.flap_phase = rng.uniform(0, math.tau)
        self.bob_phase = rng.uniform(0, math.tau)

    def update(self, dt):
        self.x += self.dir * self.speed * dt
        self.flap_phase += dt * 9.0
        self.bob_phase += dt * 2.6

    def offscreen(self):
        return self.x < -10 or self.x > WIDTH + 10


class PumpkinState:
    """Flicker, expression, blink and bat behaviour. Pure -- no drawing."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.expression = 0
        self.expression_timer = self.rng.uniform(6.0, 12.0)

        self.blink_phase = None          # None = open; else 0..1 progress
        self.blink_timer = self.rng.uniform(2.5, 6.0)

        self.flicker = 0.8
        self.flicker_target = 0.8
        self.flicker_timer = 0.0

        self.bat = None
        self.bat_timer = self.rng.uniform(3.0, 9.0)

    # -- candle --------------------------------------------------------
    def _tick_flicker(self, dt):
        self.flicker_timer -= dt
        if self.flicker_timer <= 0:
            target = self.rng.uniform(FLICKER_MIN, FLICKER_MAX)
            if self.rng.random() < 0.12:
                target *= self.rng.uniform(0.3, 0.6)   # a gust dims it
            self.flicker_target = target
            self.flicker_timer = self.rng.uniform(0.05, 0.18)
        ease = min(1.0, dt * 8.0)
        self.flicker += (self.flicker_target - self.flicker) * ease
        self.flicker = max(0.0, min(1.0, self.flicker))

    # -- blink -----------------------------------------------------------
    def start_blink(self):
        if self.blink_phase is None:
            self.blink_phase = 0.0

    def eye_openness(self):
        """1.0 = fully open, 0.0 = fully shut."""
        if self.blink_phase is None:
            return 1.0
        return abs(1.0 - 2.0 * self.blink_phase)

    def _tick_blink(self, dt):
        if self.blink_phase is not None:
            self.blink_phase += dt * BLINK_SPEED
            if self.blink_phase >= 1.0:
                self.blink_phase = None
                self.blink_timer = self.rng.uniform(2.5, 6.0)
            return
        self.blink_timer -= dt
        if self.blink_timer <= 0:
            self.start_blink()

    # -- expression --------------------------------------------------------
    def _tick_expression(self, dt):
        self.expression_timer -= dt
        if self.expression_timer <= 0:
            choices = [i for i in range(len(EXPRESSIONS))
                       if i != self.expression]
            self.expression = self.rng.choice(choices)
            self.expression_timer = self.rng.uniform(6.0, 14.0)
            self.start_blink()

    # -- bat -----------------------------------------------------------
    def _tick_bat(self, dt):
        if self.bat is not None:
            self.bat.update(dt)
            if self.bat.offscreen():
                self.bat = None
                self.bat_timer = self.rng.uniform(4.0, 10.0)
            return
        self.bat_timer -= dt
        if self.bat_timer <= 0:
            self.bat = Bat(self.rng)

    def update(self, dt):
        self._tick_flicker(dt)
        self._tick_blink(dt)
        self._tick_expression(dt)
        self._tick_bat(dt)


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _build_base():
    """Sky gradient + moon + static pumpkin rind, rendered once."""
    img = Image.new("RGB", (WIDTH, HEIGHT), SKY_BOTTOM)
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        draw.line([(0, y), (WIDTH - 1, y)], fill=_lerp_color(SKY_TOP, SKY_BOTTOM, t))

    # The moon is built on its own transparent tile and pasted through its
    # own alpha, so the crescent bite reveals the real sky gradient. Cutting
    # it with a flat sky colour left a visible disc-shaped patch instead.
    mx, my = MOON_CENTER
    side = MOON_R * 2 + 2
    moon = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    md = ImageDraw.Draw(moon)
    c = MOON_R + 1
    md.ellipse([c - MOON_R, c - MOON_R, c + MOON_R, c + MOON_R],
               fill=MOON_COLOR + (255,))
    md.ellipse([c - 2, c - 3, c, c - 1], fill=MOON_SHADOW + (255,))
    md.ellipse([c - 3, c + 1, c - 1, c + 3], fill=MOON_SHADOW + (255,))
    # Bite out the crescent: writing alpha 0 erases those pixels outright.
    md.ellipse([c - MOON_R * 0.5, c - MOON_R * 1.2,
                c + MOON_R * 1.5, c + MOON_R * 1.2], fill=(0, 0, 0, 0))
    img.paste(moon, (mx - c, my - c), moon)

    cx, cy, rx, ry = PUMPKIN_CX, PUMPKIN_CY, PUMPKIN_RX, PUMPKIN_RY

    draw.polygon([(cx - 3, cy - ry + 1), (cx + 4, cy - ry + 1),
                  (cx + 2, cy - ry - 7), (cx - 2, cy - ry - 7)],
                 fill=STEM_SHADOW)
    draw.polygon([(cx - 2, cy - ry), (cx + 2, cy - ry), (cx, cy - ry - 8)],
                 fill=STEM)

    # Three concentric tones give the body its roundness. The old version
    # drew ribbing arcs across the whole rind, which at 64x64 just read as
    # stripe noise on top of the face.
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=RIND_SHADOW)
    draw.ellipse([cx - rx + 2, cy - ry + 2, cx + rx - 2, cy + ry - 2],
                 fill=RIND)
    draw.ellipse([cx - 7, cy - ry + 3, cx + 7, cy - ry + 9], fill=RIND_HILITE)

    return img


def _render(base, state):
    """(pre-rendered base layer, PumpkinState) -> a fresh 64x64 RGB frame."""
    frame = base.copy()
    draw = ImageDraw.Draw(frame)

    for x, y, phase in STARS:
        twinkle = 0.5 + 0.5 * math.sin(time.time() * 2.0 + phase)
        c = tuple(int(v * (0.65 + 0.35 * twinkle)) for v in STAR_COLOR)
        draw.point((x, y), fill=c)

    if state.bat is not None:
        _draw_bat(draw, state.bat)

    _draw_face(draw, state)

    return frame


def _draw_bat(draw, bat):
    x = int(round(bat.x))
    y = int(round(bat.y + math.sin(bat.bob_phase) * 1.5))
    flap = math.sin(bat.flap_phase)
    tip = int(round(flap * 4))          # wing tips sweep up and down
    c = BAT_COLOR
    draw.ellipse([x - 1, y - 1, x + 1, y + 2], fill=c)
    for sx in (-1, 1):
        draw.line([(x + sx, y), (x + sx * 3, y - tip)], fill=c)
        draw.line([(x + sx * 3, y - tip), (x + sx * 5, y - tip + 2)], fill=c)


def _draw_face(draw, state):
    expr = EXPRESSIONS[state.expression]
    openness = state.eye_openness()
    glow = _lerp_color(GLOW_LOW, GLOW_HOT, state.flicker)

    right_eye = _flatten_shape(expr["eye"], openness)
    left_eye = _mirror_shape(right_eye)
    for eye in (left_eye, right_eye):
        _draw_shape(draw, eye, PUMPKIN_CX, PUMPKIN_CY, glow)

    _draw_shape(draw, expr["nose"], PUMPKIN_CX, PUMPKIN_CY, glow)
    _draw_shape(draw, expr["mouth"], PUMPKIN_CX, PUMPKIN_CY, glow)

    # Teeth are rind left uncut, so they punch out of the lit mouth.
    for x0, y0, x1, y1 in expr.get("teeth", ()):
        draw.rectangle([PUMPKIN_CX + x0, PUMPKIN_CY + y0,
                        PUMPKIN_CX + x1, PUMPKIN_CY + y1], fill=CARVE_EDGE)


def run(matrix, duration=60):
    """Run the jack-o'-lantern screensaver for the specified duration."""
    base = _build_base()
    state = PumpkinState()
    start_time = time.time()
    last = start_time

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            dt = min(0.2, max(0.0, frame_start - last))
            last = frame_start

            state.update(dt)
            frame = _render(base, state)
            matrix.SetImage(frame)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception:
        logger.error("Error in pumpkin demo", exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass


if __name__ == "__main__":
    print("This module should be imported and used with the LED matrix.")
    print("Please run src/main.py instead.")
