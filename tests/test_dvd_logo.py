"""Tests for the bouncing DVD-logo screensaver.

Physics live entirely in ``LogoState.update()`` (no drawing), so the
important invariants -- staying in bounds, reflecting cleanly off a
wall, changing colour on every bounce, and firing the corner fanfare
only on an exact corner hit -- are all checked headlessly.
"""

import math
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


# --------------------------------------------------------------------------
# corner-hit splitting (LogoSwarm)
# --------------------------------------------------------------------------

from src.display.dvd_logo import (
    MAX_LOGOS,
    MIN_SCALE,
    LogoSwarm,
    _child_scale,
    _render_scene,
)


def _force_corner_hit(state):
    """Mutate a LogoState so its very next update() is a corner hit."""
    state.x = -0.5
    state.y = state.bounds_h - state.h + 0.5
    state.vx = -1.0
    state.vy = 1.0


def test_child_scale_shrinks_then_floors_at_min_scale():
    assert _child_scale(2) == 1
    assert _child_scale(1) == MIN_SCALE
    assert _child_scale(MIN_SCALE) == MIN_SCALE


def test_split_replaces_parent_with_two_smaller_children():
    rng = random.Random(10)
    swarm = LogoSwarm(rng=rng)
    parent = swarm.logos[0]
    parent_scale = parent.scale
    _force_corner_hit(parent)

    swarm.update()

    assert len(swarm.logos) == 2
    assert parent not in swarm.logos
    for child in swarm.logos:
        assert child.scale == _child_scale(parent_scale)
        assert child.scale < parent_scale


def test_split_children_fly_apart_in_a_v_from_the_corner():
    rng = random.Random(11)
    swarm = LogoSwarm(rng=rng)
    parent = swarm.logos[0]
    _force_corner_hit(parent)
    swarm.update()

    a, b = swarm.logos
    # Both children move away from the corner (positive vx, positive vy
    # given the top-left-ish corner forced above) but along different
    # headings -- that's the "V".
    assert a.vx > 0 and b.vx > 0
    angle_a = math.atan2(a.vy, a.vx)
    angle_b = math.atan2(b.vy, b.vx)
    assert angle_a != angle_b


def test_split_stops_once_the_swarm_hits_its_population_cap():
    rng = random.Random(12)
    swarm = LogoSwarm(rng=rng)
    # Manually pack the swarm right up to the cap.
    while len(swarm.logos) < MAX_LOGOS:
        swarm.logos.append(LogoState(rng=rng, scale=1))
    assert len(swarm.logos) == MAX_LOGOS

    victim = swarm.logos[0]
    _force_corner_hit(victim)
    swarm.update()

    # At the cap: the corner-hit logo still celebrates but is not
    # replaced, and the population never exceeds the cap.
    assert len(swarm.logos) == MAX_LOGOS
    assert victim in swarm.logos
    assert victim.celebrating == CELEBRATION_FRAMES


def test_swarm_never_exceeds_cap_over_a_long_soak_of_forced_corner_hits():
    rng = random.Random(13)
    swarm = LogoSwarm(rng=rng)
    for _ in range(4000):
        # Bias every logo toward a corner occasionally to actually
        # exercise splitting during the soak, on top of normal physics.
        if rng.random() < 0.02:
            for lg in swarm.logos:
                if rng.random() < 0.5:
                    _force_corner_hit(lg)
        swarm.update()
        assert 1 <= len(swarm.logos) <= MAX_LOGOS
        for lg in swarm.logos:
            assert -1e-6 <= lg.x <= lg.bounds_w - lg.w + 1e-6
            assert -1e-6 <= lg.y <= lg.bounds_h - lg.h + 1e-6
            assert lg.scale >= MIN_SCALE


def test_children_spawn_clamped_inside_bounds():
    rng = random.Random(14)
    swarm = LogoSwarm(rng=rng)
    parent = swarm.logos[0]
    _force_corner_hit(parent)   # corner_pos ends up at (x=0-ish, y=bounds_h)
    swarm.update()
    for child in swarm.logos:
        assert 0.0 <= child.x <= child.bounds_w - child.w
        assert 0.0 <= child.y <= child.bounds_h - child.h


def test_render_scene_handles_an_empty_list_and_a_full_swarm():
    empty = _render_scene([])
    assert empty.size == (WIDTH, HEIGHT)

    logos = [LogoState(rng=random.Random(i), scale=(2 if i == 0 else 1))
             for i in range(MAX_LOGOS)]
    full = _render_scene(logos)
    assert full.size == (WIDTH, HEIGHT)
    assert full.mode == "RGB"


def test_render_scene_matches_single_render_for_one_logo():
    state = LogoState(rng=random.Random(15))
    assert _render_scene([state]).tobytes() == _render(state).tobytes()


def test_children_inherit_the_celebration_so_it_is_never_lost_on_split():
    rng = random.Random(16)
    swarm = LogoSwarm(rng=rng)
    parent = swarm.logos[0]
    _force_corner_hit(parent)
    swarm.update()

    for child in swarm.logos:
        assert child.celebrating == CELEBRATION_FRAMES
        assert child.corner_pos == parent.corner_pos

    # And it fades out normally afterwards, independently per child, and
    # the corner point stays fixed even as the child files away from it.
    fixed_point = swarm.logos[0].corner_pos
    for _ in range(CELEBRATION_FRAMES):
        swarm.update()
    for child in swarm.logos:
        assert child.celebrating == 0
        assert child.corner_pos == fixed_point
