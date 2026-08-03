#!/usr/bin/env python3
"""Monthly calendar display with a themed animation for each month.

Layout (64x64):
  Rows 0-8:   header -- "SEP 30" (3-letter month + day), month accent color
  Rows 10-34: animation band, full width, one scene per month
  Rows 38-62: dot-grid calendar (7 columns Sun-Sat, one block per day;
              past days dim, today pulses in the month accent, future brighter)

Month scenes:
  JAN snowfall + snowman        JUL fireworks
  FEB floating hearts           AUG blazing sun + melting ice cream
  MAR drifting shamrocks        SEP trees with falling leaves
  APR rain + tulip              OCT jack-o'-lantern, moon and bats
  MAY blooming flowers          NOV strutting turkey
  JUN sun over ocean waves      DEC pine tree, star and snow
"""

import calendar as _cal
import logging
import math
import random
import time
from datetime import datetime

from PIL import Image, ImageDraw

from src.display._fonts import _draw_text, _text_width
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
BG_COLOR = (0, 0, 6)

# Animation band
BAND_Y, BAND_H = 10, 25

# Calendar grid
GRID_X, GRID_Y = 4, 38
CELL_W, CELL_H = 8, 4   # cell pitch; blocks are 6x3 inside

MONTH_NAMES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
               "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

MONTH_ACCENT = {
    1: (150, 200, 255),   # ice blue
    2: (255, 90, 130),    # valentine pink
    3: (60, 200, 80),     # shamrock green
    4: (120, 170, 255),   # spring rain blue
    5: (255, 150, 200),   # blossom pink
    6: (255, 210, 60),    # summer yellow
    7: (255, 80, 60),     # firework red
    8: (255, 140, 0),     # blazing orange
    9: (230, 120, 30),    # autumn orange
    10: (255, 120, 20),   # pumpkin
    11: (180, 100, 40),   # turkey brown
    12: (80, 220, 100),   # evergreen
}

PAST_COLOR = (45, 45, 55)
FUTURE_COLOR = (110, 110, 130)


class MonthScene:
    """Draws the animated scene for one month in the band area."""

    def __init__(self, month):
        self.month = month
        self.tick = 0
        self.particles = []
        self._init_particles()

    # -- particle setup ----------------------------------------------------
    def _init_particles(self):
        m = self.month
        if m == 1:   # snowflakes: [x, y, speed]
            self.particles = [[random.uniform(0, WIDTH), random.uniform(0, BAND_H),
                               random.uniform(0.2, 0.5)] for _ in range(14)]
        elif m == 2:  # hearts: [x, y, speed, phase]
            self.particles = [[random.uniform(4, WIDTH - 4), random.uniform(0, BAND_H),
                               random.uniform(0.15, 0.35), random.uniform(0, 6.28)]
                              for _ in range(6)]
        elif m == 3:  # shamrocks: [x, y, drift, phase]
            self.particles = [[random.uniform(0, WIDTH), random.uniform(0, BAND_H),
                               random.uniform(0.2, 0.45), random.uniform(0, 6.28)]
                              for _ in range(7)]
        elif m == 4:  # raindrops: [x, y, speed]
            self.particles = [[random.uniform(0, WIDTH), random.uniform(0, BAND_H),
                               random.uniform(0.8, 1.4)] for _ in range(12)]
        elif m == 7:  # fireworks: list of bursts [x, y, age, hue]
            self.particles = []
        elif m == 8:  # ice cream drips: [x, y, speed]
            self.particles = []
        elif m == 9:  # leaves: [x, y, fall, phase, color_idx]
            self.particles = [[random.uniform(0, WIDTH), random.uniform(0, BAND_H),
                               random.uniform(0.15, 0.4), random.uniform(0, 6.28),
                               random.randint(0, 2)] for _ in range(10)]
        elif m == 12:  # snowflakes (gentler than Jan)
            self.particles = [[random.uniform(0, WIDTH), random.uniform(0, BAND_H),
                               random.uniform(0.15, 0.35)] for _ in range(10)]

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _pt(draw, x, y, color):
        if 0 <= x < WIDTH and BAND_Y <= y < BAND_Y + BAND_H:
            draw.point((int(x), int(y)), fill=color)

    def draw(self, draw):
        self.tick += 1
        fn = getattr(self, "_m{:02d}".format(self.month), None)
        if fn:
            fn(draw)

    # -- January: snowfall + snowman ---------------------------------------
    def _m01(self, d):
        yo = BAND_Y
        # snowman, right side
        sx, ground = 50, yo + BAND_H - 1
        for r, cy in ((4, ground - 4), (3, ground - 10), (2, ground - 15)):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if dx * dx + dy * dy <= r * r:
                        self._pt(d, sx + dx, cy + dy, (230, 235, 245))
        self._pt(d, sx - 1, ground - 16, (10, 10, 20))  # eyes
        self._pt(d, sx + 1, ground - 16, (10, 10, 20))
        self._pt(d, sx, ground - 15, (255, 140, 0))     # carrot
        for f in self.particles:
            f[1] += f[2]
            f[0] += math.sin(self.tick * 0.05 + f[1] * 0.3) * 0.3
            if f[1] > BAND_H:
                f[0], f[1] = random.uniform(0, WIDTH), 0
            self._pt(d, f[0] % WIDTH, yo + f[1], (220, 225, 240))

    # -- February: floating hearts ------------------------------------------
    def _m02(self, d):
        yo = BAND_Y
        for h in self.particles:
            h[1] -= h[2]
            if h[1] < 0:
                h[0], h[1] = random.uniform(4, WIDTH - 4), BAND_H
            x = h[0] + math.sin(self.tick * 0.06 + h[3]) * 2
            y = yo + h[1]
            glow = int(180 + 60 * math.sin(self.tick * 0.1 + h[3]))
            c = (glow, 40, 80)
            # 3x3 heart: two lobes on top, point at the bottom
            for dx, dy in ((-1, -1), (1, -1), (-1, 0), (0, 0), (1, 0), (0, 1)):
                self._pt(d, x + dx, y + dy, c)

    # -- March: drifting shamrocks -------------------------------------------
    def _m03(self, d):
        yo = BAND_Y
        green = (60, 200, 80)
        dark = (30, 130, 50)
        for s in self.particles:
            s[0] += s[2]
            if s[0] > WIDTH + 2:
                s[0], s[1] = -2, random.uniform(0, BAND_H)
            x, y = s[0], yo + s[1] + math.sin(self.tick * 0.05 + s[3]) * 1.5
            for dx, dy in ((0, -1), (-1, 0), (1, 0)):   # three leaves
                self._pt(d, x + dx, y + dy, green)
            self._pt(d, x, y, dark)
            self._pt(d, x, y + 1, dark)                  # stem

    # -- April: rain + tulip ---------------------------------------------------
    def _m04(self, d):
        yo = BAND_Y
        ground = yo + BAND_H - 1
        # tulip
        tx = 32
        self._pt(d, tx, ground, (40, 140, 50))
        self._pt(d, tx, ground - 1, (40, 140, 50))
        self._pt(d, tx, ground - 2, (40, 140, 50))
        for dx in (-1, 0, 1):
            self._pt(d, tx + dx, ground - 3, (255, 60, 90))
            self._pt(d, tx + dx, ground - 4, (255, 60, 90))
        self._pt(d, tx - 1, ground - 5, (255, 60, 90))
        self._pt(d, tx + 1, ground - 5, (255, 60, 90))
        for r in self.particles:
            r[1] += r[2]
            if r[1] > BAND_H:
                r[0], r[1] = random.uniform(0, WIDTH), 0
            self._pt(d, r[0], yo + r[1], (90, 140, 230))

    # -- May: blooming flowers ---------------------------------------------------
    def _m05(self, d):
        yo = BAND_Y
        ground = yo + BAND_H - 1
        random.seed(5)  # stable flower field
        spots = [(random.randint(3, WIDTH - 4), random.randint(0, 3),
                  random.choice([(255, 120, 180), (255, 200, 60), (200, 120, 255)]))
                 for _ in range(9)]
        random.seed()
        for i, (fx, drop, color) in enumerate(spots):
            fy = ground - drop
            bloom = 0.5 + 0.5 * math.sin(self.tick * 0.05 + i)
            self._pt(d, fx, fy, (40, 150, 60))
            self._pt(d, fx, fy - 1, (40, 150, 60))
            petal = tuple(int(c * (0.55 + 0.45 * bloom)) for c in color)
            self._pt(d, fx, fy - 2, (255, 230, 120))
            if bloom > 0.35:
                for dx, dy in ((-1, -2), (1, -2), (0, -3), (0, -1)):
                    self._pt(d, fx + dx, fy + dy, petal)

    # -- June: sun over ocean waves -----------------------------------------------
    def _m06(self, d):
        yo = BAND_Y
        cx, cy = 14, yo + 7
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                if dx * dx + dy * dy <= 16:
                    self._pt(d, cx + dx, cy + dy, (255, 210, 60))
        for i in range(8):
            a = self.tick * 0.03 + i * math.pi / 4
            self._pt(d, cx + 6 * math.cos(a), cy + 6 * math.sin(a), (255, 180, 40))
        # waves
        for row in range(3):
            wy = yo + BAND_H - 6 + row * 2
            for x in range(WIDTH):
                lvl = math.sin(x * 0.25 + self.tick * 0.08 + row * 1.5)
                if lvl > 0.2:
                    c = (30, 90, 200) if lvl < 0.8 else (150, 210, 255)
                    self._pt(d, x, wy, c)

    # -- July: fireworks -------------------------------------------------------------
    def _m07(self, d):
        yo = BAND_Y
        if self.tick % 22 == 0:
            self.particles.append([random.randint(8, WIDTH - 8),
                                   random.randint(3, BAND_H - 8), 0,
                                   random.choice([(255, 80, 60), (80, 160, 255),
                                                  (255, 220, 80), (200, 100, 255)])])
        for b in self.particles[:]:
            b[2] += 1
            if b[2] > 18:
                self.particles.remove(b)
                continue
            r = b[2] * 0.6
            fade = max(0, 1.0 - b[2] / 18.0)
            c = tuple(int(ch * fade) for ch in b[3])
            for i in range(10):
                a = i * math.pi / 5 + b[2] * 0.02
                self._pt(d, b[0] + r * math.cos(a), yo + b[1] + r * math.sin(a), c)

    # -- August: blazing sun + melting ice cream --------------------------------------
    def _m08(self, d):
        yo = BAND_Y
        cx, cy = 13, yo + 6
        pulse = int(210 + 45 * math.sin(self.tick * 0.15))
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                if dx * dx + dy * dy <= 16:
                    self._pt(d, cx + dx, cy + dy, (pulse, pulse // 2, 0))
        for i in range(8):
            a = self.tick * 0.05 + i * math.pi / 4
            ln = 6 + int(math.sin(self.tick * 0.2 + i) * 1.5)
            self._pt(d, cx + ln * math.cos(a), cy + ln * math.sin(a), (pulse, pulse // 3, 0))
        # ice cream cone, right of center
        ix, iy = 42, yo + 9
        for row in range(5):  # cone (tapering down)
            half = max(0, 2 - row // 2)
            for dx in range(-half, half + 1):
                self._pt(d, ix + dx, iy + 3 + row, (200, 140, 60))
        for dx in range(-3, 4):  # scoop
            for dy in range(-3, 2):
                if dx * dx + dy * dy <= 9:
                    self._pt(d, ix + dx, iy + dy, (255, 170, 190))
        # melt drips
        if self.tick % 30 == 0:
            self.particles.append([ix + random.randint(-2, 2), iy + 2, random.uniform(0.2, 0.4)])
        for p in self.particles[:]:
            p[1] += p[2]
            if p[1] > BAND_Y + BAND_H - 1:
                p[1] = BAND_Y + BAND_H - 1
                if random.random() < 0.02:
                    self.particles.remove(p)
                    continue
            self._pt(d, p[0], p[1], (255, 170, 190))
        # heat shimmer
        for sy in range(yo + 2, yo + BAND_H - 2, 5):
            wx = 28 + int(math.sin(self.tick * 0.12 + sy) * 2)
            self._pt(d, wx, sy, (120, 60, 10))

    # -- September: falling leaves --------------------------------------------------------
    def _m09(self, d):
        yo = BAND_Y
        ground = yo + BAND_H - 1
        leaf_colors = [(230, 120, 30), (200, 60, 20), (240, 190, 40)]
        # two trees with full autumn canopies
        for tx in (10, 52):
            for py in range(ground - 8, ground + 1):     # trunk
                self._pt(d, tx, py, (110, 70, 30))
                self._pt(d, tx + 1, py, (90, 55, 25))
            cy = ground - 12
            for dx in range(-6, 8):                       # canopy (round, mostly full)
                for dy in range(-4, 5):
                    if (dx - 0.5) ** 2 / 42.0 + dy * dy / 17.0 <= 1:
                        if (dx * 3 + dy * 5 + tx) % 7 != 0:   # sparse gaps
                            ci = (dx * 2 + dy + tx) % 3
                            self._pt(d, tx + dx, cy + dy, leaf_colors[ci])
        for f in self.particles:
            f[1] += f[2]
            f[0] += math.sin(self.tick * 0.04 + f[3]) * 0.5
            if f[1] > BAND_H:
                f[0] = random.choice([random.uniform(4, 18), random.uniform(46, 60)])
                f[1] = random.uniform(2, 8)
            self._pt(d, f[0] % WIDTH, yo + f[1], leaf_colors[f[4]])

    # -- October: jack-o'-lantern, moon and bats ---------------------------------------------
    def _m10(self, d):
        yo = BAND_Y
        ground = yo + BAND_H - 1
        # moon
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx * dx + dy * dy <= 9 and (dx + 1) ** 2 + dy * dy > 5:
                    self._pt(d, 55 + dx, yo + 5 + dy, (230, 230, 200))
        # pumpkin
        px = 20
        flick = int(200 + 55 * math.sin(self.tick * 0.3) * random.uniform(0.6, 1.0))
        for dx in range(-4, 5):
            for dy in range(-3, 3):
                if (dx / 4.5) ** 2 + (dy / 3.0) ** 2 <= 1:
                    self._pt(d, px + dx, ground - 3 + dy, (235, 110, 15))
        self._pt(d, px, ground - 7, (60, 120, 40))        # stem
        for ex in (px - 2, px + 2):                        # glowing eyes
            self._pt(d, ex, ground - 4, (flick, flick // 2, 0))
        for mx in (px - 1, px, px + 1):                    # jagged mouth
            self._pt(d, mx, ground - 2, (flick, flick // 2, 0))
        # bats (two, figure-eight paths, flapping)
        for i, ph in enumerate((0.0, 2.6)):
            bx = 32 + math.sin(self.tick * 0.045 + ph) * 24
            by = yo + 6 + math.sin(self.tick * 0.09 + ph * 2) * 4
            flap = (self.tick // 4 + i) % 2
            self._pt(d, bx, by, (150, 150, 170))
            if flap:
                self._pt(d, bx - 2, by - 1, (120, 120, 145))
                self._pt(d, bx + 2, by - 1, (120, 120, 145))
                self._pt(d, bx - 1, by - 1, (120, 120, 145))
                self._pt(d, bx + 1, by - 1, (120, 120, 145))
            else:
                self._pt(d, bx - 2, by + 1, (120, 120, 145))
                self._pt(d, bx + 2, by + 1, (120, 120, 145))
                self._pt(d, bx - 1, by, (120, 120, 145))
                self._pt(d, bx + 1, by, (120, 120, 145))

    # -- November: strutting turkey --------------------------------------------------------------
    def _m11(self, d):
        yo = BAND_Y
        ground = yo + BAND_H - 1
        tx = 30 + int(math.sin(self.tick * 0.02) * 12)    # slow strut
        bob = int(math.sin(self.tick * 0.15) > 0)          # body bob
        ty = ground - 6 - bob
        # tail fan: radial feathers behind the body (dark base -> bright tip)
        shades = [(140, 45, 20), (200, 90, 25), (240, 180, 45)]
        fan_cx, fan_cy = tx - 2, ty + 1
        for i in range(7):
            a = math.pi * (0.12 + 0.76 * i / 6)            # 22..158 degrees
            for r in range(3, 9):
                fx = fan_cx - r * math.cos(a)
                fy = fan_cy - r * math.sin(a)
                self._pt(d, fx, fy, shades[(r - 3) // 2])
        # body
        for dx in range(-3, 4):
            for dy in range(-2, 3):
                if (dx / 3.4) ** 2 + (dy / 2.6) ** 2 <= 1:
                    self._pt(d, tx + dx, ty + dy, (120, 70, 30))
        # head + neck (front = +x)
        self._pt(d, tx + 3, ty - 2, (120, 70, 30))
        self._pt(d, tx + 4, ty - 3, (150, 90, 40))
        self._pt(d, tx + 5, ty - 3, (150, 90, 40))
        self._pt(d, tx + 5, ty - 2, (220, 40, 40))         # wattle
        self._pt(d, tx + 6, ty - 3, (255, 200, 60))        # beak
        # legs (alternate with strut)
        step = (self.tick // 8) % 2
        self._pt(d, tx - 1 + step, ground - 1, (200, 160, 60))
        self._pt(d, tx - 1 + step, ground, (200, 160, 60))
        self._pt(d, tx + 1 - step, ground - 1, (200, 160, 60))
        self._pt(d, tx + 1 - step, ground, (200, 160, 60))
        # scattered ground seeds
        random.seed(11)
        for _ in range(6):
            self._pt(d, random.randint(2, WIDTH - 3), ground, (100, 80, 40))
        random.seed()

    # -- December: pine tree, star and snow ------------------------------------------------------------
    def _m12(self, d):
        yo = BAND_Y
        ground = yo + BAND_H - 1
        tx = 32
        for row in range(10):                              # tree (triangle)
            half = 1 + row // 2
            ty = ground - 11 + row
            for dx in range(-half, half + 1):
                self._pt(d, tx + dx, ty, (20, 130, 50))
        self._pt(d, tx, ground, (110, 70, 30))
        self._pt(d, tx, ground - 1, (110, 70, 30))
        # ornaments (twinkle)
        random.seed(12)
        orns = [(tx + random.randint(-3, 3), ground - 10 + random.randint(2, 9),
                 random.choice([(255, 60, 60), (80, 140, 255), (255, 220, 80)]))
                for _ in range(5)]
        random.seed()
        for i, (ox, oy, oc) in enumerate(orns):
            if (self.tick // 6 + i) % 3:
                self._pt(d, ox, oy, oc)
        # star
        glow = int(200 + 55 * math.sin(self.tick * 0.2))
        self._pt(d, tx, ground - 12, (glow, glow, 60))
        self._pt(d, tx - 1, ground - 12, (glow // 2, glow // 2, 30))
        self._pt(d, tx + 1, ground - 12, (glow // 2, glow // 2, 30))
        for f in self.particles:
            f[1] += f[2]
            if f[1] > BAND_H:
                f[0], f[1] = random.uniform(0, WIDTH), 0
            self._pt(d, f[0], yo + f[1], (220, 225, 240))


def _draw_grid(draw, now, accent, tick):
    """Dot-grid calendar: 7 columns (Sun..Sat), one 6x3 block per day."""
    first_wd, n_days = _cal.monthrange(now.year, now.month)
    first_col = (first_wd + 1) % 7        # convert Mon=0 to Sun=0
    for day in range(1, n_days + 1):
        idx = first_col + day - 1
        row, col = divmod(idx, 7)
        x = GRID_X + col * CELL_W
        y = GRID_Y + row * CELL_H
        if day == now.day:
            pulse = 0.6 + 0.4 * math.sin(tick * 0.15)
            c = tuple(int(ch * pulse) for ch in accent)
        elif day < now.day:
            c = PAST_COLOR
        else:
            c = FUTURE_COLOR
        draw.rectangle([x, y, x + 5, y + 2], fill=c)


def _render(now, scene, tick):
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(image)
    accent = MONTH_ACCENT[now.month]

    header = "{} {}".format(MONTH_NAMES[now.month - 1], now.day)
    hx = max(0, (WIDTH - _text_width(header, scale=1)) // 2)
    _draw_text(draw, header, hx, 1, accent, scale=1, spacing=1)

    scene.draw(draw)
    _draw_grid(draw, now, accent, tick)
    return image


def run(matrix, duration=60):
    """Run the monthly calendar display for the specified duration."""
    start_time = time.time()
    scene = None
    tick = 0
    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            now = datetime.now()
            if scene is None or scene.month != now.month:
                scene = MonthScene(now.month)
            image = _render(now, scene, tick)
            matrix.SetImage(image)
            tick += 1
            time.sleep(0.1)   # ~10 FPS
    except Exception as e:
        logger.error("Error in month_calendar display: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
