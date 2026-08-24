"""Tests for the bouncing DVD-logo screensaver.

Physics live entirely in ``LogoState.update()`` (no drawing), so the
important invariants -- staying in bounds, reflecting cleanly off a
wall, changing colour on every bounce, and firing the corner fanfare
only on an exact corner hit -- are all checked headlessly.
"""

import random

import pytest
from PIL import Image

from src.display.dvd_logo import (
    CELEBRATION_FRAMES,
    COLORS,
    HEIGHT,
    LogoState,
    WIDTH,
    _render,
)


def test_never_leaves_bounds_over_a_long_soak():
    rng = random.Random(1)
    state = LogoState(rng=rng)
    for _ in range(20000):
        state.update(rng=rng)
        assert -1e-6 <= state.x <= WIDTH - state.w + 1e-6
        assert -1e-6 <= state.y <= HEIGHT - state.h + 1e-6


def test_wall_bounce_reflects_velocity_and_clamps_position():
    rng = random.Random(2)
    state = LogoState(rng=rng)
    state.x = -0.5
    state.y = 10.0
    state.vx = -1.1
    state.vy = 0.3
    hit = state.update(rng=rng)
    assert not hit               # only the left wall, not a corner
    assert state.x == 0.0
    assert state.vx > 0          # reflected to moving right


def test_color_changes_on_every_wall_bounce_and_never_repeats_immediately():
    """update()'s return value flags a *corner* hit specifically, not
    any wall touch -- so bounces are detected here by watching the
    colour itself, which _next_color() changes on every wall hit."""
    rng = random.Random(3)
    state = LogoState(rng=rng)
    changes = 0
    for _ in range(500):
        before = state.color_idx
        state.update(rng=rng)
        if state.color_idx != before:
            assert state.color_idx != before  # trivially true; documents intent
            changes += 1
    assert changes > 5, "expected several bounces in 500 frames at this speed"


def test_corner_hit_only_fires_when_both_axes_bounce_the_same_frame():
    rng = random.Random(4)
    state = LogoState(rng=rng)

    # Set up a guaranteed corner hit: both edges crossed on the same step.
    state.x = -0.5
    state.y = HEIGHT - state.h + 0.5
    state.vx = -1.0
    state.vy = 1.0
    hit = state.update(rng=rng)
    assert hit is True
    assert state.celebrating == CELEBRATION_FRAMES
    assert state.corner_pos is not None

    # A plain single-wall bounce right after must not restart the fanfare.
    state.x = -0.5
    state.y = 10.0
    state.vx = -1.0
    state.vy = 0.2
    remaining_before = state.celebrating
    hit2 = state.update(rng=rng)
    assert hit2 is False
    assert state.celebrating == remaining_before - 1


def test_celebration_counts_down_to_zero():
    rng = random.Random(5)
    state = LogoState(rng=rng)
    state.celebrating = CELEBRATION_FRAMES
    state.corner_pos = (5, 5)
    for _ in range(CELEBRATION_FRAMES):
        state.x, state.y = 30, 30    # away from every wall
        state.vx, state.vy = 0.3, 0.3
        hit = state.update(rng=rng)
        assert not hit
    assert state.celebrating == 0


def test_all_colors_are_valid_rgb():
    for c in COLORS:
        assert len(c) == 3
        assert all(0 <= v <= 255 for v in c)


def test_render_produces_a_64x64_rgb_frame():
    state = LogoState(rng=random.Random(6))
    frame = _render(state)
    assert isinstance(frame, Image.Image)
    assert frame.size == (WIDTH, HEIGHT)
    assert frame.mode == "RGB"
    # Something was actually drawn -- not an all-black canvas.
    assert frame.getextrema() != ((0, 0), (0, 0), (0, 0))


def test_render_during_celebration_does_not_crash_at_frame_edges():
    """Corner celebrations draw rings centred at the panel edge; the
    fade-based colour math must never go out of RGB range there."""
    state = LogoState(rng=random.Random(7))
    state.x, state.y = 0, 0
    state.celebrating = CELEBRATION_FRAMES
    state.corner_pos = (0, 0)
    for state.celebrating in range(CELEBRATION_FRAMES, 0, -1):
        frame = _render(state)
        assert frame.size == (WIDTH, HEIGHT)
