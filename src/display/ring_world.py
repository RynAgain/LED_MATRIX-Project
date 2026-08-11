"""
Ring World -- flying over the surface of a Niven Ring on a 64x64 LED matrix.

The camera skims forward along the inside of a ringworld:
- Smooth value-noise terrain scrolls below with perspective; each screen
  row is rendered once per scroll step and cached, then pasted as a tiny
  image strip, so per-frame cost stays flat and Pi-friendly
- The ring itself arches over the sky as a connected band: wide where it
  meets the horizon (nearby surface), thin at the zenith (the far side,
  ~2R away), textured with ocean/land/desert patches that creep as the
  ring spins
- The sun hangs fixed at the zenith (eternal noon at ring center)
- Shadow squares slide across the sun for a full day/night cycle:
  the landscape darkens, stars come out, but the arch stays lit --
  local night never shadows the far side of the ring
- Star field brightens at night

Demo-only feature (no controller).
"""

import math
import random
import logging
import time
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

SIZE = 64
FPS = 20
FRAME_DUR = 1.0 / FPS

HORIZON_Y = 44          # first ground row
GROUND_ROWS = SIZE - HORIZON_Y
SUN_X, SUN_Y = 32, 7
SUN_RADIUS = 3

DAY_LENGTH = 30.0       # seconds for a full day/night cycle
NIGHT_FLOOR = 0.18      # minimum scene brightness at deep night

FLY_SPEED = 5.0         # world units/second forward
SPIN_SPEED = 0.25       # arch texture creep (cells/second)

# Palettes
SKY_DAY_TOP = (8, 14, 40)
SKY_DAY_HORIZON = (40, 70, 120)
SUN_COLOR = (255, 240, 180)
SUN_GLOW = (120, 100, 50)
SHADOW_SQUARE = (5, 5, 12)
STAR_COLOR = (200, 210, 255)

# Terrain bands, picked by smooth noise height (low -> high)
TERRAIN_BANDS = [
    (0.34, (20, 60, 130)),    # water
    (0.40, (140, 130, 90)),   # sand shore
    (0.62, (30, 110, 40)),    # grass
    (0.74, (24, 88, 32)),     # dark grass
    (0.85, (110, 95, 45)),    # dirt hills
    (1.01, (150, 140, 120)),  # rock tops
]
ARCH_PALETTE = [
    (30, 90, 160),    # ocean
    (40, 120, 60),    # land
    (150, 130, 80),   # desert
    (30, 90, 160),    # ocean again (weight water higher)
    (180, 185, 195),  # cloud/ice
]

NUM_STARS = 40
ARCH_SEGMENTS = 48      # texture cells along the arch
ARCH_STEPS = 64         # polyline resolution across the sky

_NOISE_SIZE = 64
_GROUND_XSCALE = 0.13   # world -> noise coords
_GROUND_ZSCALE = 0.11


def _make_noise(seed=1337):
    """Small tileable pseudo-noise table for terrain patches."""
    rng = random.Random(seed)
    return [[rng.randrange(0, 256) for _ in range(_NOISE_SIZE)]
            for _ in range(_NOISE_SIZE)]


def _smooth_table(noise):
    """3x3 box blur of the noise table (wrapping), scaled to 0..1 floats."""
    n = _NOISE_SIZE
    out = [[0.0] * n for _ in range(n)]
    for y in range(n):
        for x in range(n):
            acc = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    acc += noise[(y + dy) % n][(x + dx) % n]
            out[y][x] = acc / (9.0 * 255.0)
    return out


def _daylight(phase):
    """Scene brightness for a day phase in [0,1). Night is centred at 0.5.

    Returns a value in [NIGHT_FLOOR, 1.0]. Smooth shoulders (the shadow
    square's penumbra), symmetric around the night centre.
    """
    dist = abs(phase - 0.5)          # 0 at deep night, 0.5 at high noon
    lo, hi = 0.10, 0.20              # eclipse shoulder band
    if dist <= lo:
        t = 0.0
    elif dist >= hi:
        t = 1.0
    else:
        u = (dist - lo) / (hi - lo)
        t = u * u * (3 - 2 * u)      # smoothstep
    return NIGHT_FLOOR + (1.0 - NIGHT_FLOOR) * t


def _arch_geometry(t):
    """Screen path of the ring arch for t in [0,1] (left foot -> right foot).

    Returns (x, y, half_width). Wide at the feet (nearby ring surface),
    thin at the zenith (far side of the ring).
    """
    x = t * (SIZE - 1)
    rise = math.sin(math.pi * t)
    y = HORIZON_Y - 1 - rise * (HORIZON_Y - 4)
    half_w = 1.0 + 3.5 * (1.0 - rise)
    return x, y, half_w


def _scale(color, k):
    return (int(color[0] * k), int(color[1] * k), int(color[2] * k))


class RingWorldScene:
    """Holds the state and rendering for the ringworld flyover."""

    def __init__(self, seed=1337):
        self.noise = _make_noise(seed)
        self.smooth = _smooth_table(self.noise)
        rng = random.Random(seed ^ 0xBEEF)
        self.stars = [(rng.randrange(0, SIZE), rng.randrange(0, HORIZON_Y - 2),
                       rng.uniform(0.3, 1.0)) for _ in range(NUM_STARS)]
        arch_rng = random.Random(seed ^ 0xA5C4)
        self.arch_cells = [arch_rng.randrange(0, len(ARCH_PALETTE))
                           for _ in range(ARCH_SEGMENTS)]
        self.t = 0.0            # scene time in seconds

        # Per-row ground cache: row -> (zq, 64x1 RGB Image). A row is only
        # re-rendered when its integer scroll step changes, so steady-state
        # frames just paste 20 cached strips (C-speed, no Python pixel work).
        self._row_cache = {}
        self._row_renders = 0   # instrumentation (used by tests)

    def step(self, dt=FRAME_DUR):
        self.t += dt

    @property
    def phase(self):
        """Day phase in [0,1). Starts at high noon (phase 0)."""
        return (self.t / DAY_LENGTH) % 1.0

    # ------------------------------------------------------------------
    # Terrain
    # ------------------------------------------------------------------

    def _sample(self, fx, fz):
        """Bilinear sample of the smoothed noise table (wrapping)."""
        n = _NOISE_SIZE
        x0 = math.floor(fx)
        z0 = math.floor(fz)
        tx = fx - x0
        tz = fz - z0
        x0 %= n
        z0 %= n
        x1 = (x0 + 1) % n
        z1 = (z0 + 1) % n
        s = self.smooth
        top = s[z0][x0] * (1 - tx) + s[z0][x1] * tx
        bot = s[z1][x0] * (1 - tx) + s[z1][x1] * tx
        return top * (1 - tz) + bot * tz

    @staticmethod
    def _row_depth(row):
        return 30.0 / (row + 1.5)

    def _terrain_color(self, world_x, zq, row):
        """Terrain color at world coords (smooth bands, haze with distance)."""
        h = self._sample(world_x * _GROUND_XSCALE, zq * _GROUND_ZSCALE)
        for threshold, color in TERRAIN_BANDS:
            if h < threshold:
                break
        # Gentle shading from a second, offset sample
        shade = 0.8 + 0.4 * self._sample(world_x * 0.31 + 17.0,
                                         zq * 0.27 + 5.0)
        haze = 0.45 + 0.55 * (row / float(GROUND_ROWS - 1))
        return _scale(color, min(1.25, shade) * haze)

    def _ground_color(self, x, y):
        """Terrain color for screen pixel (x, y >= HORIZON_Y) at scene time."""
        row = y - HORIZON_Y
        depth = self._row_depth(row)
        zq = int(depth * 4.0 + self.t * FLY_SPEED)
        world_x = (x - SIZE // 2) * depth * 0.18
        return self._terrain_color(world_x, zq, row)

    def _row_strip(self, row):
        """Cached 64x1 image strip for a ground row at the current scroll."""
        depth = self._row_depth(row)
        zq = int(depth * 4.0 + self.t * FLY_SPEED)
        cached = self._row_cache.get(row)
        if cached is not None and cached[0] == zq:
            return cached[1]
        buf = bytearray()
        for x in range(SIZE):
            world_x = (x - SIZE // 2) * depth * 0.18
            buf.extend(self._terrain_color(world_x, zq, row))
        strip = Image.frombytes("RGB", (SIZE, 1), bytes(buf))
        self._row_cache[row] = (zq, strip)
        self._row_renders += 1
        return strip

    def _draw_ground(self, image, day):
        block = Image.new("RGB", (SIZE, GROUND_ROWS))
        for row in range(GROUND_ROWS):
            block.paste(self._row_strip(row), (0, row))
        if day < 0.999:
            lut = [int(i * day) for i in range(256)] * 3
            block = block.point(lut)
        image.paste(block, (0, HORIZON_Y))

    # ------------------------------------------------------------------
    # Sky
    # ------------------------------------------------------------------

    def _draw_sky(self, draw, day):
        for y in range(HORIZON_Y):
            g = y / float(HORIZON_Y)
            color = tuple(int((a + (b - a) * g) * day)
                          for a, b in zip(SKY_DAY_TOP, SKY_DAY_HORIZON))
            draw.line([(0, y), (SIZE - 1, y)], fill=color)

    def _draw_stars(self, image, draw, night):
        if night <= 0.05:
            return
        for sx, sy, mag in self.stars:
            twinkle = 0.75 + 0.25 * math.sin(self.t * 3.0 + sx * 1.7 + sy)
            color = _scale(STAR_COLOR, mag * night * twinkle)
            if sum(color) > sum(image.getpixel((sx, sy))):
                draw.point((sx, sy), fill=color)

    def _draw_arch(self, draw, day):
        """Connected polyline band -- no gaps even on the steep sections."""
        spin = self.t * SPIN_SPEED
        arch_level = 0.55 + 0.45 * day
        prev = _arch_geometry(0.0)
        for i in range(1, ARCH_STEPS + 1):
            t = i / float(ARCH_STEPS)
            cur = _arch_geometry(t)
            cell = int((t - 0.5 / ARCH_STEPS) * ARCH_SEGMENTS + spin) \
                % ARCH_SEGMENTS
            color = _scale(ARCH_PALETTE[self.arch_cells[cell]], arch_level)
            width = max(2, int(prev[2] + cur[2]))
            draw.line([(prev[0], prev[1]), (cur[0], cur[1])],
                      fill=color, width=width)
            prev = cur

    def _draw_sun(self, draw, day):
        draw.ellipse([SUN_X - SUN_RADIUS - 1, SUN_Y - SUN_RADIUS - 1,
                      SUN_X + SUN_RADIUS + 1, SUN_Y + SUN_RADIUS + 1],
                     fill=_scale(SUN_GLOW, day))
        draw.ellipse([SUN_X - SUN_RADIUS, SUN_Y - SUN_RADIUS,
                      SUN_X + SUN_RADIUS, SUN_Y + SUN_RADIUS],
                     fill=_scale(SUN_COLOR, max(day, 0.25)))

    def _draw_shadow_square(self, draw):
        offset = (self.phase - 0.5) * 110.0
        if abs(offset) < 26:
            sq_x = SUN_X - offset
            sq_half = 7
            draw.rectangle([sq_x - sq_half, SUN_Y - SUN_RADIUS - 3,
                            sq_x + sq_half, SUN_Y + SUN_RADIUS + 3],
                           fill=SHADOW_SQUARE)

    # ------------------------------------------------------------------

    def draw(self):
        day = _daylight(self.phase)
        night = 1.0 - (day - NIGHT_FLOOR) / (1.0 - NIGHT_FLOOR)

        image = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
        draw = ImageDraw.Draw(image)

        self._draw_sky(draw, day)
        self._draw_stars(image, draw, night)
        self._draw_arch(draw, day)          # may spill below the horizon...
        self._draw_sun(draw, day)
        self._draw_shadow_square(draw)
        self._draw_ground(image, day)       # ...ground paste covers the spill

        return image


def run(matrix, duration=60):
    """Run the ring world flyover for the given duration."""
    scene = RingWorldScene()
    start = time.time()

    try:
        while time.time() - start < duration:
            if should_stop():
                break
            frame_start = time.time()

            scene.step()
            matrix.SetImage(scene.draw())

            elapsed = time.time() - frame_start
            sleep_time = FRAME_DUR - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in ring_world: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
