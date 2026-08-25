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
SKY_TOP = (8, 6, 24)
SKY_BOTTOM = (34, 16, 50)
MOON_CENTER = (50, 12)
MOON_R = 7
MOON_COLOR = (222, 216, 186)
MOON_SHADOW = (176, 168, 142)
STAR_COLOR = (255, 250, 235)
STARS = [  # fixed positions, seeded once for a stable night sky
    (x, y, phase)
    for x, y, phase in (
        (4, 6, 0.0), (14, 4, 1.1), (24, 9, 2.3), (36, 5, 0.4),
        (58, 22, 3.1), (8, 18, 1.7), (46, 6, 2.8), (30, 15, 0.9),
        (18, 24, 4.2), (60, 8, 5.0), (2, 28, 2.1),
    )
]

# --- Pumpkin body --------------------------------------------------------
PUMPKIN_CX, PUMPKIN_CY = 32, 40
PUMPKIN_RX, PUMPKIN_RY = 25, 19
RIND = (222, 104, 18)
RIND_SHADOW = (168, 68, 10)
RIND_HILITE = (250, 158, 60)
RIND_DARK = (54, 24, 6)          # cavity wall behind the candle
STEM = (94, 128, 50)
STEM_SHADOW = (60, 88, 30)

GLOW_HOT = (255, 208, 96)        # candle at its brightest
GLOW_LOW = (110, 34, 4)          # dim ember during a gust

FLICKER_MIN, FLICKER_MAX = 0.55, 1.0
BLINK_SPEED = 3.2                 # phase units / second

# --- Expressions ---------------------------------------------------------
# Each shape is either ("poly", [(dx, dy), ...]) or ("circle", dx, dy, r),
# offsets relative to (PUMPKIN_CX, PUMPKIN_CY). Eyes are given for the
# right side only; the left eye mirrors dx -> -dx.
EXPRESSIONS = [
    {  # classic grin
        "eye": ("poly", [(7, -9), (16, -3), (7, 1)]),
        "nose": ("poly", [(0, 3), (5, 10), (-5, 10)]),
        "mouth": ("poly", [
            (-17, 15), (-12, 21), (-8, 15), (-4, 21), (0, 15),
            (4, 21), (8, 15), (12, 21), (17, 15), (17, 19), (-17, 19),
        ]),
    },
    {  # surprised
        "eye": ("circle", 13, -4, 5),
        "nose": ("poly", [(0, 4), (3, 9), (-3, 9)]),
        "mouth": ("circle", 0, 18, 6),
    },
    {  # angry
        "eye": ("poly", [(4, -9), (17, -5), (17, 1), (6, -2)]),
        "nose": ("poly", [(0, 3), (5, 10), (-5, 10)]),
        "mouth": ("poly", [
            (-16, 20), (-11, 15), (-6, 19), (-1, 14),
            (4, 19), (9, 14), (14, 19), (16, 20),
        ]),
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


def _draw_shape(draw, shape, cx, cy, color):
    kind = shape[0]
    if kind == "circle":
        _, dx, dy, r = shape
        x, y = cx + dx, cy + dy
        if r < 0.5:
            return
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    else:
        _, points = shape
        pts = [(cx + x, cy + y) for x, y in points]
        draw.polygon(pts, fill=color)


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

    mx, my = MOON_CENTER
    draw.ellipse([mx - MOON_R, my - MOON_R, mx + MOON_R, my + MOON_R],
                 fill=MOON_COLOR)
    draw.ellipse([mx - MOON_R * 0.55, my - MOON_R * 1.1,
                  mx + MOON_R * 1.3, my + MOON_R * 1.1],
                 fill=SKY_BOTTOM if my - MOON_R * 1.1 > 0 else SKY_TOP)
    draw.ellipse([mx - 2, my - 3, mx + 1, my], fill=MOON_SHADOW)
    draw.ellipse([mx - 3, my + 1, mx, my + 3], fill=MOON_SHADOW)

    cx, cy, rx, ry = PUMPKIN_CX, PUMPKIN_CY, PUMPKIN_RX, PUMPKIN_RY
    draw.polygon([(cx - 2, cy - ry - 1), (cx + 5, cy - ry - 1),
                  (cx + 2, cy - ry - 7), (cx - 1, cy - ry - 7)],
                 fill=STEM_SHADOW)
    draw.polygon([(cx - 2, cy - ry - 1), (cx + 2, cy - ry - 1),
                  (cx, cy - ry - 8)], fill=STEM)

    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=RIND)
    for i in range(-3, 4):
        lobe_x = cx + i * (rx * 2 // 7)
        shade = RIND_HILITE if i < 0 else RIND_SHADOW
        draw.arc([lobe_x - 3, cy - ry, lobe_x + 3, cy + ry], 0, 360, fill=shade)
    # Kept clear of the eye row (which starts around cy - ry*0.5) so a
    # blinking eye is never mistaken for this static sheen.
    draw.ellipse([cx - rx * 0.6, cy - ry * 0.9, cx - rx * 0.2, cy - ry * 0.6],
                 fill=RIND_HILITE)

    return img


def _render(base, state):
    """(pre-rendered base layer, PumpkinState) -> a fresh 64x64 RGB frame."""
    frame = base.copy()
    draw = ImageDraw.Draw(frame)

    for x, y, phase in STARS:
        twinkle = 0.5 + 0.5 * math.sin(time.time() * 2.0 + phase)
        c = tuple(int(v * (0.4 + 0.6 * twinkle)) for v in STAR_COLOR)
        draw.point((x, y), fill=c)

    if state.bat is not None:
        _draw_bat(draw, state.bat)

    _draw_face(draw, state)

    return frame


def _draw_bat(draw, bat):
    x = int(round(bat.x))
    y = int(round(bat.y + math.sin(bat.bob_phase) * 1.5))
    flap = math.sin(bat.flap_phase)
    wing_lift = 3 + int(round(flap * 3))
    color = (18, 14, 26)
    draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=color)
    draw.line([(x, y), (x - 4, y - wing_lift)], fill=color)
    draw.line([(x, y), (x + 4, y - wing_lift)], fill=color)


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
