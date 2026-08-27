"""Tests for the Matrix digital rain effect.

The bug this suite exists to prevent: white leading characters being
painted over by another column's green trail. ``RainState.draw_lists()``
separates heads from trails precisely so the renderer can draw every
trail first and every head last, and that ordering is pinned here with
a contrived overlap that the old single-pass renderer would have failed.

The other historical failure was geometry: PIL's ~6x11 default font drawn
at 4px column / 1px row spacing overlapped itself into an unreadable
smear, so the cell grid and the font's character coverage are pinned too.
"""

import random

from PIL import Image

from src.display._fonts import FONT_5X7
from src.display.matrix_rain import (
    CELL_H,
    CELL_W,
    CHARS,
    COLS,
    HEAD_COLOR,
    HEIGHT,
    ROWS,
    TRAIL_MIN_GREEN,
    WIDTH,
    Column,
    RainState,
    _cell_color,
    _render,
)


def test_every_character_is_renderable_by_the_5x7_font():
    """An unsupported glyph renders as an empty cell, so the alphabet
    must stay inside the font's coverage."""
    missing = [c for c in CHARS if c not in FONT_5X7]
    assert not missing, f"characters missing from FONT_5X7: {missing}"


def test_cell_grid_fits_the_panel():
    assert COLS * CELL_W <= WIDTH
    assert ROWS * CELL_H <= HEIGHT


def test_head_is_white_and_trail_fades_to_a_floor():
    assert _cell_color(0) == HEAD_COLOR
    assert HEAD_COLOR == (255, 255, 255)

    # Trail cells are green-only and get dimmer with distance.
    brightness = [_cell_color(i)[1] for i in range(1, ROWS + 5)]
    assert all(_cell_color(i)[0] == 0 and _cell_color(i)[2] == 0
               for i in range(1, ROWS + 5))
    assert brightness == sorted(brightness, reverse=True)
    assert min(brightness) >= TRAIL_MIN_GREEN
    assert all(0 <= v <= 255 for v in brightness)


def test_draw_lists_puts_only_heads_in_the_head_list():
    state = RainState(rng=random.Random(1))
    for _ in range(200):
        state.update(1 / 20)
        trails, heads = state.draw_lists()
        for _x, _y, _ch, color in heads:
            assert color == HEAD_COLOR
        for _x, _y, _ch, color in trails:
            assert color != HEAD_COLOR
            assert color[0] == 0 and color[2] == 0


def test_head_stays_visible_on_top_of_an_overlapping_trail():
    """The regression that motivated the rewrite: a long trail sharing a
    column with another drop's head must not paint over that head."""
    state = RainState(rng=random.Random(2))

    # Two columns in the SAME screen column: one is a long trail whose
    # body covers row 3, the other's head sits exactly on row 3.
    trail_col, head_col = state.columns[0], state.columns[1]
    head_col.cell_x = trail_col.cell_x

    trail_col.head = float(ROWS + 2)
    trail_col.length = ROWS + 4
    trail_col.chars = ["W"] * trail_col.length

    head_col.head = 3.0
    head_col.length = 4
    head_col.chars = ["W"] * head_col.length

    # Sanity: the trail really does cover the head's cell.
    assert any(row == 3 and i != 0 for row, _ch, i in trail_col.cells())

    frame = _render(state)
    x0 = state.columns[0].cell_x * CELL_W
    cell = frame.crop((x0, 3 * CELL_H, x0 + CELL_W, 3 * CELL_H + CELL_H))
    assert HEAD_COLOR in list(cell.getdata()), \
        "head glyph was overpainted by the overlapping trail"


def test_cells_are_always_on_panel_over_a_long_soak():
    state = RainState(rng=random.Random(3))
    for _ in range(5000):
        state.update(1 / 20)
        trails, heads = state.draw_lists()
        for x, y, ch, _color in trails + heads:
            assert 0 <= x <= WIDTH - CELL_W
            assert 0 <= y <= HEIGHT - CELL_H
            assert ch in CHARS


def test_column_respawns_above_the_panel_after_falling_through():
    rng = random.Random(4)
    column = Column(0, rng)
    column.head = float(ROWS + column.length + 1)
    column.update(1 / 20)
    assert column.head < 0, "a spent column should restart above the panel"


def test_column_head_advances_with_dt():
    column = Column(0, random.Random(5))
    column.head = 0.0
    column.speed = 4.0
    column.update(0.5)
    assert column.head == 2.0


def test_render_produces_a_64x64_rgb_frame_with_content():
    state = RainState(rng=random.Random(6))
    for _ in range(60):
        state.update(1 / 20)
    frame = _render(state)
    assert isinstance(frame, Image.Image)
    assert frame.size == (WIDTH, HEIGHT)
    assert frame.mode == "RGB"
    assert frame.getextrema() != ((0, 0), (0, 0), (0, 0))
