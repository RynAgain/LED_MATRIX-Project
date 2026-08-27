#!/usr/bin/env python3
"""Matrix digital rain for a 64x64 LED matrix.

Bright white leading characters fall down grid-aligned columns, trailing
a green tail that fades toward black.

Two things keep the white heads legible, which the first version got
wrong. First, rendering is two-pass: every trail in the scene is drawn,
*then* every head on top, so no column's tail can ever paint over
another column's head. Second, characters live on a real cell grid
(``CELL_W`` x ``CELL_H``) drawn with the project's 5x7 bitmap font --
previously PIL's ~6x11 default font was drawn at 4px column spacing and
1px row spacing, so glyphs overlapped each other into an unreadable
smear.

State (``Column``, ``RainState``) is pure ``dt``-based arithmetic and
exposes the frame's cells via :meth:`RainState.draw_lists`, so both the
ordering guarantee and the fall behaviour are testable headlessly.
"""

import time
import random
import logging

from PIL import Image, ImageDraw

from src.display._shared import should_stop
from src.display._fonts import _draw_text

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 20

# One glyph per cell: 5x7 font plus a 1px gutter so neighbours never touch.
CELL_W, CELL_H = 6, 8
COLS = WIDTH // CELL_W                    # 10 columns
ROWS = HEIGHT // CELL_H                   # 8 rows
X_OFFSET = (WIDTH - COLS * CELL_W) // 2   # centre the grid horizontally

# Only characters the 5x7 font actually defines -- anything else would
# silently render as a blank cell.
CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%*+<=>?/"

HEAD_COLOR = (255, 255, 255)   # the leading character: always pure white
TRAIL_HEAD_GREEN = 235         # brightness of the cell right behind the head
TRAIL_FALLOFF = 34             # brightness lost per cell further back
TRAIL_MIN_GREEN = 40           # dimmest a tail cell gets before cutting off


def _cell_color(index_from_head):
    """Colour for a cell ``index_from_head`` cells behind the head."""
    if index_from_head == 0:
        return HEAD_COLOR
    green = max(TRAIL_MIN_GREEN,
                TRAIL_HEAD_GREEN - (index_from_head - 1) * TRAIL_FALLOFF)
    return (0, green, 0)


class Column:
    """One falling column of characters. Pure state -- never draws."""

    def __init__(self, cell_x, rng):
        self.cell_x = cell_x
        self.rng = rng
        self._respawn(initial=True)

    def _respawn(self, initial=False):
        # Start above the panel so a column fades in rather than popping.
        if initial:
            self.head = -float(self.rng.randint(0, ROWS))
        else:
            self.head = -1.0 - self.rng.random() * 4.0
        self.speed = self.rng.uniform(2.5, 7.0)          # cells per second
        self.length = self.rng.randint(4, ROWS + 4)
        self.chars = [self.rng.choice(CHARS) for _ in range(self.length)]

    def update(self, dt):
        self.head += self.speed * dt
        # Occasionally flip a character, the way the film's glyphs churn.
        if self.chars and self.rng.random() < dt * 6.0:
            self.chars[self.rng.randrange(len(self.chars))] = \
                self.rng.choice(CHARS)
        if self.head - self.length > ROWS:
            self._respawn()

    def cells(self):
        """Yield ``(row, char, index_from_head)`` for on-panel cells only."""
        head_row = int(self.head)
        for i, ch in enumerate(self.chars):
            row = head_row - i
            if 0 <= row < ROWS:
                yield row, ch, i


class RainState:
    """Every column in the scene. Pure state -- never draws."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.columns = [Column(i, self.rng) for i in range(COLS)]

    def update(self, dt):
        for column in self.columns:
            column.update(dt)

    def draw_lists(self):
        """Return ``(trails, heads)``, each a list of (x, y, char, colour).

        Keeping heads in their own list is what guarantees they land on
        top: the renderer draws every trail cell first, then these.
        """
        trails, heads = [], []
        for column in self.columns:
            x = X_OFFSET + column.cell_x * CELL_W
            for row, ch, i in column.cells():
                cell = (x, row * CELL_H, ch, _cell_color(i))
                (heads if i == 0 else trails).append(cell)
        return trails, heads


def _render(state):
    """RainState -> a 64x64 RGB frame, trails first and heads last."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    trails, heads = state.draw_lists()
    for x, y, ch, color in trails:
        _draw_text(draw, ch, x, y, color)
    for x, y, ch, color in heads:
        _draw_text(draw, ch, x, y, color)
    return img


def run(matrix, duration=60):
    """Run the matrix rain effect for the specified duration."""
    state = RainState()
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
            matrix.SetImage(_render(state))

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in matrix rain: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass


if __name__ == "__main__":
    print("This module should be imported and used with the LED matrix.")
    print("Please run src/main.py instead.")
