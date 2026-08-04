#!/usr/bin/env python3
"""Giant staring eyeball for a 64x64 LED matrix.

One enormous eye that fills the whole panel and behaves like it is alive: it
darts around (saccades), occasionally tracks something smoothly, blinks,
double-blinks, squints suspiciously, goes wide with surprise, and its pupil
dilates and contracts. Every so often a long, slow blink changes the iris
colour.

Rendering strategy (the panel is only 4096 pixels, but Python is slow):
everything static is pre-rendered once at start-up into full-frame layers --
the skin/lid background, the sclera with its blood vessels, and the iris disc
with its radial fibres. Each frame is then a handful of C-level PIL composites
plus a few ellipse draws, rather than per-pixel Python:

    frame  = sclera background copy
    paste    iris disc at the current gaze offset
    draw     pupil + specular highlights
    paste    skin over everything outside the eye opening (clips the iris)
    paste    skin over the closed part of the lids (the blink)

That keeps the cost flat regardless of how much detail the pre-rendered layers
contain.
"""

import time
import math
import random
import logging

from PIL import Image, ImageDraw

from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30

# --- Eye opening (an almond: the upper lid curves more than the lower) -------
EYE_CX, EYE_CY = 32, 33
APERTURE_HALF_W = 31.0
APERTURE_UP = 25.0
APERTURE_DOWN = 21.0

# --- Iris / pupil -----------------------------------------------------------
IRIS_R = 19
PUPIL_MIN, PUPIL_MAX = 4.0, 11.0
GAZE_X_LIMIT = 13.0
GAZE_UP_LIMIT, GAZE_DOWN_LIMIT = 8.0, 6.0

# --- Colours ----------------------------------------------------------------
SKIN = (168, 116, 92)
SKIN_SHADOW = (120, 78, 62)
SKIN_HIGHLIGHT = (198, 146, 118)
LASH = (28, 16, 14)
SCLERA = (232, 230, 226)
SCLERA_SHADOW = (176, 172, 178)
SCLERA_CORNER = (206, 168, 166)
VEIN = (196, 96, 96)
LIMBAL = (14, 12, 20)
PUPIL = (0, 0, 0)
GLINT = (255, 255, 255)
GLINT_SOFT = (208, 226, 255)

# Iris palettes: (deep, mid, bright) - fibres interpolate between them.
IRIS_PALETTES = [
    ((60, 34, 10), (150, 96, 24), (226, 172, 70)),    # amber
    ((10, 44, 30), (28, 118, 76), (110, 198, 140)),   # emerald
    ((12, 30, 66), (34, 82, 168), (120, 176, 246)),   # sapphire
    ((44, 16, 60), (104, 48, 150), (186, 132, 228)),  # violet
    ((60, 12, 16), (152, 34, 38), (226, 96, 84)),     # blood
    ((40, 40, 46), (110, 112, 124), (196, 200, 210)),  # steel
]


def _lerp(a, b, t):
    return a + (b - a) * t


def _mix(c0, c1, t):
    """Blend two RGB tuples; t=0 gives c0."""
    t = max(0.0, min(1.0, t))
    return (
        int(_lerp(c0[0], c1[0], t)),
        int(_lerp(c0[1], c1[1], t)),
        int(_lerp(c0[2], c1[2], t)),
    )


def _aperture_bounds():
    """Per-column (top_y, bottom_y) of the eye opening.

    ``None`` for columns outside the opening. The two half-heights differ, so
    the curves meet at a point at each corner and the result reads as an almond
    rather than an ellipse.
    """
    bounds = []
    for x in range(WIDTH):
        u = (x - EYE_CX) / APERTURE_HALF_W
        if abs(u) >= 1.0:
            bounds.append(None)
            continue
        k = math.sqrt(1.0 - u * u)
        bounds.append((EYE_CY - APERTURE_UP * k, EYE_CY + APERTURE_DOWN * k))
    return bounds


def _build_skin(bounds):
    """Skin/lid background: brow shadow above, cheek light below, lid crease."""
    img = Image.new("RGB", (WIDTH, HEIGHT), SKIN)
    draw = ImageDraw.Draw(img)

    # Vertical shading: shadowed under the brow, lighter toward the cheek.
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        if t < 0.5:
            color = _mix(SKIN_SHADOW, SKIN, t / 0.5)
        else:
            color = _mix(SKIN, SKIN_HIGHLIGHT, (t - 0.5) / 0.5)
        draw.line([(0, y), (WIDTH - 1, y)], fill=color)

    # Lid crease: a darker arc a few pixels above the opening.
    crease = []
    for x in range(WIDTH):
        b = bounds[x]
        if b is None:
            continue
        crease.append((x, max(0, int(b[0]) - 5)))
    if len(crease) > 1:
        draw.line(crease, fill=_mix(SKIN_SHADOW, SKIN, 0.25))

    return img


def _build_sclera(bounds, skin):
    """Skin background with the eye white, its shading and blood vessels."""
    img = skin.copy()
    draw = ImageDraw.Draw(img)

    for x in range(WIDTH):
        b = bounds[x]
        if b is None:
            continue
        top, bot = b
        y0, y1 = int(round(top)), int(round(bot))
        # Corners are pinker; the top sits in the lid's shadow.
        corner_t = abs(x - EYE_CX) / APERTURE_HALF_W
        base = _mix(SCLERA, SCLERA_CORNER, corner_t ** 2)
        for y in range(max(0, y0), min(HEIGHT, y1 + 1)):
            depth = (y - top) / max(1.0, bot - top)
            if depth < 0.35:
                color = _mix(SCLERA_SHADOW, base, depth / 0.35)
            else:
                color = base
            img.putpixel((x, y), color)

    # Blood vessels: random walks inward from each corner, with forks.
    rng = random.Random(0xE1E)  # fixed seed: vessels are part of the artwork
    for side in (-1, 1):
        for _ in range(7):
            x = EYE_CX + side * rng.uniform(0.62, 0.95) * APERTURE_HALF_W
            y = EYE_CY + rng.uniform(-8, 8)
            heading = math.pi if side > 0 else 0.0
            heading += rng.uniform(-0.5, 0.5)
            length = rng.randint(6, 16)
            _draw_vein(img, bounds, x, y, heading, length, rng, depth=0)

    return img


def _draw_vein(img, bounds, x, y, heading, length, rng, depth):
    """Walk a faint vessel inward, forking occasionally. Clipped to the sclera."""
    for step in range(length):
        heading += rng.uniform(-0.35, 0.35)
        x += math.cos(heading)
        y += math.sin(heading)
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < WIDTH and 0 <= iy < HEIGHT):
            return
        b = bounds[ix]
        if b is None or not (b[0] <= iy <= b[1]):
            return
        # Fade out along the length so vessels dissolve toward the iris.
        fade = 0.30 + 0.45 * (1.0 - step / max(1, length))
        img.putpixel((ix, iy), _mix(img.getpixel((ix, iy)), VEIN, fade))
        if depth < 2 and rng.random() < 0.12:
            _draw_vein(img, bounds, x, y, heading + rng.choice((-0.9, 0.9)),
                       max(2, length // 2), rng, depth + 1)


def _build_masks(bounds):
    """(inside, outside) L-masks for the eye opening."""
    inside = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(inside)
    for x in range(WIDTH):
        b = bounds[x]
        if b is None:
            continue
        draw.line([(x, int(round(b[0]))), (x, int(round(b[1])))], fill=255)
    outside = Image.eval(inside, lambda v: 255 - v)
    return inside, outside


def _build_iris(palette):
    """Pre-render the iris disc plus its circular mask.

    Radial fibres, a lighter collarette ring and a dark limbal ring at the rim.
    """
    deep, mid, bright = palette
    size = IRIS_R * 2 + 1
    img = Image.new("RGB", (size, size), mid)
    draw = ImageDraw.Draw(img)
    c = IRIS_R
    rng = random.Random(1234)

    draw.ellipse([0, 0, size - 1, size - 1], fill=mid)

    # Fibres: alternating light/dark strands from the pupil edge to the rim.
    fibres = 260
    for i in range(fibres):
        ang = i / fibres * math.tau + rng.uniform(-0.006, 0.006)
        shade = rng.random()
        if shade < 0.45:
            color = _mix(mid, deep, rng.uniform(0.25, 0.80))
        else:
            color = _mix(mid, bright, rng.uniform(0.15, 0.80))
        r0 = IRIS_R * rng.uniform(0.26, 0.34)
        r1 = IRIS_R * rng.uniform(0.90, 1.0)
        draw.line(
            [(c + r0 * math.cos(ang), c + r0 * math.sin(ang)),
             (c + r1 * math.cos(ang), c + r1 * math.sin(ang))],
            fill=color,
        )

    # Collarette: the raised ring around the pupil.
    cr = int(IRIS_R * 0.42)
    draw.ellipse([c - cr, c - cr, c + cr, c + cr],
                 outline=_mix(mid, bright, 0.75))
    cr2 = cr - 1
    if cr2 > 1:
        draw.ellipse([c - cr2, c - cr2, c + cr2, c + cr2],
                     outline=_mix(mid, deep, 0.35))

    # Limbal ring: dark border where the iris meets the sclera.
    draw.ellipse([0, 0, size - 1, size - 1], outline=LIMBAL)
    draw.ellipse([1, 1, size - 2, size - 2], outline=_mix(LIMBAL, deep, 0.45))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    return img, mask


class EyeState:
    """Gaze, blink and pupil behaviour. Pure state, so it is easy to test."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        # Gaze: target and eased current position, in pixels from centre.
        self.tx = self.ty = 0.0
        self.gx = self.gy = 0.0
        self.saccade_timer = 0.7
        self.pursuit_time = 0.0
        self.pursuit_ang = 0.0
        # Lids: 1.0 fully open, 0.0 shut.
        self.open = 1.0
        self.open_target = 1.0
        self.blink_timer = self.rng.uniform(1.5, 4.0)
        self.blink_phase = None
        self.blink_speed = 6.0
        self.blinks_queued = 0
        self.long_blink = False
        # Pupil radius in pixels.
        self.pupil = 6.5
        self.pupil_target = 6.5
        self.pupil_timer = 1.0
        self.palette_index = 0
        self.palette_changed = False

    # -- gaze ---------------------------------------------------------------
    def _new_gaze_target(self):
        if self.rng.random() < 0.18:
            # Occasionally lock back onto the viewer.
            self.tx = self.ty = 0.0
        else:
            self.tx = self.rng.uniform(-GAZE_X_LIMIT, GAZE_X_LIMIT)
            self.ty = self.rng.uniform(-GAZE_UP_LIMIT, GAZE_DOWN_LIMIT)
        self.saccade_timer = self.rng.uniform(0.35, 2.2)
        # A saccade briefly constricts the pupil (accommodation).
        self.pupil_target = max(PUPIL_MIN, self.pupil_target - 1.2)

    def _start_pursuit(self):
        self.pursuit_time = self.rng.uniform(1.8, 3.5)
        self.pursuit_ang = self.rng.uniform(0, math.tau)

    # -- lids ---------------------------------------------------------------
    def start_blink(self, count=1, long=False):
        self.blinks_queued = max(self.blinks_queued, count)
        self.long_blink = long
        self.blink_speed = 2.2 if long else 6.5
        if self.blink_phase is None:
            self.blink_phase = 0.0

    def _tick_blink(self, dt):
        if self.blink_phase is None:
            return
        self.blink_phase += dt * self.blink_speed
        if self.blink_phase >= 1.0:
            self.blinks_queued -= 1
            if self.blinks_queued > 0:
                self.blink_phase = 0.0
            else:
                self.blink_phase = None
                if self.long_blink:
                    # A long blink is the excuse for a new eye colour.
                    self.palette_index = (
                        self.palette_index + 1 + self.rng.randrange(
                            len(IRIS_PALETTES) - 1)
                    ) % len(IRIS_PALETTES)
                    self.palette_changed = True
                    self.long_blink = False

    def lid_openness(self):
        """Current opening, 0..1.15 (over 1.0 = lids retracted in surprise)."""
        if self.blink_phase is None:
            return self.open
        # A blink shuts fast and opens a little slower.
        p = self.blink_phase
        shut = math.sin(math.pi * min(1.0, p ** 0.75))
        return max(0.0, self.open * (1.0 - shut))

    # -- main update --------------------------------------------------------
    def update(self, dt):
        self.palette_changed = False

        # Gaze
        if self.pursuit_time > 0.0:
            self.pursuit_time -= dt
            self.pursuit_ang += dt * 1.6
            self.tx = math.cos(self.pursuit_ang) * GAZE_X_LIMIT * 0.7
            self.ty = math.sin(self.pursuit_ang) * GAZE_DOWN_LIMIT * 0.6
            ease = 0.18
        else:
            self.saccade_timer -= dt
            if self.saccade_timer <= 0.0:
                if self.rng.random() < 0.14:
                    self._start_pursuit()
                else:
                    self._new_gaze_target()
            ease = 0.42  # saccades are fast
        self.gx += (self.tx - self.gx) * ease
        self.gy += (self.ty - self.gy) * ease
        self.gx = max(-GAZE_X_LIMIT, min(GAZE_X_LIMIT, self.gx))
        self.gy = max(-GAZE_UP_LIMIT, min(GAZE_DOWN_LIMIT, self.gy))

        # Lids
        self.blink_timer -= dt
        if self.blink_timer <= 0.0 and self.blink_phase is None:
            roll = self.rng.random()
            if roll < 0.10:
                self.start_blink(count=1, long=True)
                self.blink_timer = self.rng.uniform(4.0, 8.0)
            elif roll < 0.30:
                self.start_blink(count=2)
                self.blink_timer = self.rng.uniform(2.5, 6.0)
            else:
                self.start_blink(count=1)
                self.blink_timer = self.rng.uniform(1.5, 5.0)
        self._tick_blink(dt)

        # Expression: mostly neutral, sometimes a squint or a wide stare.
        if self.blink_phase is None and self.rng.random() < 0.006:
            roll = self.rng.random()
            if roll < 0.5:
                self.open_target = self.rng.uniform(0.40, 0.60)  # squint
                self.pupil_target = min(PUPIL_MAX, self.pupil + 1.5)
            else:
                self.open_target = 1.14                          # surprise
                self.pupil_target = PUPIL_MIN
        elif self.rng.random() < 0.012:
            self.open_target = 1.0
        self.open += (self.open_target - self.open) * min(1.0, dt * 5.0)

        # Pupil: drifts on its own, eased toward the target.
        self.pupil_timer -= dt
        if self.pupil_timer <= 0.0:
            self.pupil_target = self.rng.uniform(PUPIL_MIN + 0.5, PUPIL_MAX - 1.0)
            self.pupil_timer = self.rng.uniform(0.8, 3.0)
        self.pupil += (self.pupil_target - self.pupil) * min(1.0, dt * 3.0)
        self.pupil = max(PUPIL_MIN, min(PUPIL_MAX, self.pupil))


class _Renderer:
    """Holds the pre-rendered layers and composites one frame at a time."""

    def __init__(self, palette_index=0):
        self.bounds = _aperture_bounds()
        self.skin = _build_skin(self.bounds)
        self.sclera = _build_sclera(self.bounds, self.skin)
        self.inside, self.outside = _build_masks(self.bounds)
        self.set_palette(palette_index)
        self._lid_mask = Image.new("L", (WIDTH, HEIGHT), 0)

    def set_palette(self, index):
        self.iris, self.iris_mask = _build_iris(
            IRIS_PALETTES[index % len(IRIS_PALETTES)])

    def render(self, state):
        frame = self.sclera.copy()

        # Iris disc at the gaze offset.
        ix = int(round(EYE_CX + state.gx)) - IRIS_R
        iy = int(round(EYE_CY + state.gy)) - IRIS_R
        frame.paste(self.iris, (ix, iy), self.iris_mask)

        draw = ImageDraw.Draw(frame)
        cx = EYE_CX + state.gx
        cy = EYE_CY + state.gy

        # Pupil.
        pr = state.pupil
        draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=PUPIL)

        # Specular highlights: the big one sits opposite the gaze so it reads
        # as a fixed light source rather than something glued to the eye.
        hx = cx - state.gx * 0.55 - IRIS_R * 0.40
        hy = cy - state.gy * 0.55 - IRIS_R * 0.44
        draw.ellipse([hx - 2.8, hy - 2.2, hx + 2.8, hy + 2.2], fill=GLINT)
        draw.point((hx - 3.5, hy + 0.5), fill=GLINT_SOFT)
        draw.point((hx + 0.5, hy + 3.2), fill=GLINT_SOFT)
        # Small counter-glint low on the opposite side.
        sx = cx + IRIS_R * 0.36
        sy = cy + IRIS_R * 0.42
        draw.ellipse([sx - 1.1, sy - 0.9, sx + 1.1, sy + 0.9], fill=GLINT_SOFT)

        # Clip everything back inside the eye opening.
        frame.paste(self.skin, (0, 0), self.outside)

        # Lids.
        self._draw_lids(frame, state.lid_openness())
        return frame

    # At rest the lids sit slightly over the eye opening, so they crop the top
    # of the iris the way real ones do. That overlap is also the headroom that
    # lets a surprised stare retract the lids and expose more sclera -- without
    # it, "wide open" and "neutral" rendered identically.
    NEUTRAL_OVERLAP = 0.22

    def _draw_lids(self, frame, openness):
        """Cover the shut part of the opening with skin, then draw the lashes."""
        openness = max(0.0, min(1.15, openness))
        if openness <= 1.0:
            shut = self.NEUTRAL_OVERLAP + (1.0 - openness) * (
                1.0 - self.NEUTRAL_OVERLAP)
        else:
            # Retract past the resting position for the wide-eyed look.
            shut = self.NEUTRAL_OVERLAP - (openness - 1.0) * 1.5
        shut = max(0.0, min(1.0, shut))
        upper = []
        lower = []
        for x in range(WIDTH):
            b = self.bounds[x]
            if b is None:
                continue
            top, bot = b
            span = bot - top
            # The upper lid does most of the travel, as a real one does.
            upper.append((x, top + shut * span * 0.82))
            lower.append((x, bot - shut * span * 0.18))

        if not upper:
            return

        self._lid_mask.paste(0, (0, 0, WIDTH, HEIGHT))
        mdraw = ImageDraw.Draw(self._lid_mask)
        x0 = upper[0][0]
        x1 = upper[-1][0]
        mdraw.polygon([(x0, -1)] + upper + [(x1, -1)], fill=255)
        mdraw.polygon([(x0, HEIGHT)] + lower + [(x1, HEIGHT)], fill=255)
        frame.paste(self.skin, (0, 0), self._lid_mask)

        fdraw = ImageDraw.Draw(frame)
        if len(upper) > 1:
            fdraw.line(upper, fill=LASH)
        if len(lower) > 1:
            fdraw.line(lower, fill=_mix(LASH, SKIN_SHADOW, 0.45))


def run(matrix, duration=60):
    """Run the giant eyeball demo."""
    start = time.time()
    state = EyeState()
    renderer = _Renderer(state.palette_index)
    last = time.time()

    try:
        while time.time() - start < duration:
            if should_stop():
                break
            frame_start = time.time()

            dt = min(0.2, max(0.001, frame_start - last))
            last = frame_start

            state.update(dt)
            if state.palette_changed:
                renderer.set_palette(state.palette_index)

            matrix.SetImage(renderer.render(state))

            sleep_time = FRAME_INTERVAL - (time.time() - frame_start)
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception:
        logger.error("Error in big_eye demo", exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
