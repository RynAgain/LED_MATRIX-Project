"""
Ring World -- flying over the surface of a Niven Ring on a 64x64 LED matrix.

The camera skims forward along the inside of a ringworld:
- Procedural terrain scrolls below with perspective (fast near, slow far)
- The ring itself arches over the sky: wide where it meets the horizon
  (nearby surface) and thin at the zenith (the far side, ~2R away),
  textured with ocean/land/desert patches that creep as the ring spins
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
SUN_X, SUN_Y = 32, 7
SUN_RADIUS = 3

DAY_LENGTH = 30.0       # seconds for a full day/night cycle
NIGHT_FLOOR = 0.18      # minimum scene brightness at deep night

FLY_SPEED = 9.0         # world units/second forward
SPIN_SPEED = 0.35       # arch texture creep (segments/second)

# Palettes
SKY_DAY_TOP = (8, 14, 40)
SKY_DAY_HORIZON = (40, 70, 120)
SUN_COLOR = (255, 240, 180)
SUN_GLOW = (120, 100, 50)
SHADOW_SQUARE = (5, 5, 12)
STAR_COLOR = (200, 210, 255)

GROUND_PALETTE = [
    (30, 110, 40),    # grass
    (24, 95, 34),     # dark grass
    (45, 130, 50),    # bright grass
    (110, 95, 45),    # dirt
    (20, 60, 130),    # lake
    (140, 130, 90),   # sand
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

_NOISE_SIZE = 64


def _make_noise(seed=1337):
    """Small tileable pseudo-noise table for terrain patches."""
    rng = random.Random(seed)
    return [[rng.randrange(0, 256) for _ in range(_NOISE_SIZE)]
            for _ in range(_NOISE_SIZE)]


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
        rng = random.Random(seed ^ 0xBEEF)
        self.stars = [(rng.randrange(0, SIZE), rng.randrange(0, HORIZON_Y - 2),
                       rng.uniform(0.3, 1.0)) for _ in range(NUM_STARS)]
        # Arch texture: stable color index per segment
        arch_rng = random.Random(seed ^ 0xA5C4)
        self.arch_cells = [arch_rng.randrange(0, len(ARCH_PALETTE))
                           for _ in range(ARCH_SEGMENTS)]
        self.t = 0.0            # scene time in seconds

    def step(self, dt=FRAME_DUR):
        self.t += dt

    @property
    def phase(self):
        """Day phase in [0,1). Starts at high noon (phase 0)."""
        return (self.t / DAY_LENGTH) % 1.0

    # ------------------------------------------------------------------

    def _noise_at(self, ix, iy):
        return self.noise[iy % _NOISE_SIZE][ix % _NOISE_SIZE]

    def _ground_color(self, x, y):
        """Terrain color for screen pixel (x, y >= HORIZON_Y) at scene time."""
        row = y - HORIZON_Y            # 0 .. 19
        depth = 30.0 / (row + 1.5)     # far rows have big depth
        world_z = depth * 4.0 + self.t * FLY_SPEED
        world_x = (x - SIZE // 2) * depth * 0.18
        n = self._noise_at(int(world_x), int(world_z))
        # Big patches: quantize neighbouring noise for blobby terrain
        n2 = self._noise_at(int(world_x) // 3, int(world_z) // 3)
        idx = (n2 * len(GROUND_PALETTE)) // 256
        color = GROUND_PALETTE[idx]
        # Fine dither from n
        shade = 0.85 + (n / 255.0) * 0.3
        # Distance haze toward the horizon
        haze = 0.45 + 0.55 * (row / 19.0)
        return _scale(color, shade * haze)

    # ------------------------------------------------------------------

    def draw(self):
        day = _daylight(self.phase)
        night = 1.0 - (day - NIGHT_FLOOR) / (1.0 - NIGHT_FLOOR)

        image = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
        draw = ImageDraw.Draw(image)

        # --- Sky gradient (dimmed by night) ---
        for y in range(HORIZON_Y):
            g = y / float(HORIZON_Y)
            color = tuple(int((a + (b - a) * g) * day)
                          for a, b in zip(SKY_DAY_TOP, SKY_DAY_HORIZON))
            draw.line([(0, y), (SIZE - 1, y)], fill=color)

        # --- Stars (washed out by day, only drawn if they outshine the sky) ---
        star_level = night
        if star_level > 0.05:
            for sx, sy, mag in self.stars:
                twinkle = 0.75 + 0.25 * math.sin(self.t * 3.0 + sx * 1.7 + sy)
                color = _scale(STAR_COLOR, mag * star_level * twinkle)
                if sum(color) > sum(image.getpixel((sx, sy))):
                    draw.point((sx, sy), fill=color)

        # --- Ring arch (stays lit at night: sunlit elsewhere on the ring) ---
        spin = self.t * SPIN_SPEED
        arch_level = 0.55 + 0.45 * day     # only mild dimming at night
        steps = 96
        for i in range(steps + 1):
            t = i / float(steps)
            x, y, half_w = _arch_geometry(t)
            cell = int(t * ARCH_SEGMENTS + spin) % ARCH_SEGMENTS
            color = _scale(ARCH_PALETTE[self.arch_cells[cell]], arch_level)
            ix = int(x)
            for dy in range(-int(half_w), int(half_w) + 1):
                py = int(y) + dy
                if 0 <= ix < SIZE and 0 <= py < HORIZON_Y:
                    image.putpixel((ix, py), color)

        # --- Sun at the zenith, in front of the arch ---
        draw.ellipse([SUN_X - SUN_RADIUS - 1, SUN_Y - SUN_RADIUS - 1,
                      SUN_X + SUN_RADIUS + 1, SUN_Y + SUN_RADIUS + 1],
                     fill=_scale(SUN_GLOW, day))
        draw.ellipse([SUN_X - SUN_RADIUS, SUN_Y - SUN_RADIUS,
                      SUN_X + SUN_RADIUS, SUN_Y + SUN_RADIUS],
                     fill=_scale(SUN_COLOR, max(day, 0.25)))

        # --- Shadow square sliding across the sun around night ---
        # Enters from the right, covers the sun at phase 0.5, exits left.
        offset = (self.phase - 0.5) * 110.0
        if abs(offset) < 26:
            sq_x = SUN_X - offset
            sq_half = 7
            draw.rectangle([sq_x - sq_half, SUN_Y - SUN_RADIUS - 3,
                            sq_x + sq_half, SUN_Y + SUN_RADIUS + 3],
                           fill=SHADOW_SQUARE)

        # --- Ground ---
        for y in range(HORIZON_Y, SIZE):
            for x in range(SIZE):
                image.putpixel((x, y), _scale(self._ground_color(x, y), day))

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
