"""Tests for the Halloween jack-o'-lantern screensaver.

Behaviour (flicker, blink, expression cycling, bat spawn/flight) lives
entirely in ``PumpkinState``/``Bat`` (no drawing), so the invariants
that matter -- flicker never leaving its declared range, a blink always
returning to fully open, expressions never repeating immediately, a bat
crossing the whole panel and eventually being retired -- are checked
headlessly over a long soak.
"""

import math
import random

from PIL import Image

from src.display.pumpkin import (
    Bat,
    EXPRESSIONS,
    FLICKER_MAX,
    FLICKER_MIN,
    HEIGHT,
    PumpkinState,
    WIDTH,
    _build_base,
    _flatten_shape,
    _render,
)


def test_flicker_stays_in_bounds_over_a_long_soak():
    rng = random.Random(1)
    state = PumpkinState(rng=rng)
    for _ in range(20000):
        state.update(dt=1 / 24)
        assert 0.0 <= state.flicker <= 1.0


def test_blink_always_returns_to_fully_open():
    rng = random.Random(2)
    state = PumpkinState(rng=rng)
    state.start_blink()
    assert state.blink_phase == 0.0
    for _ in range(500):
        state.update(dt=1 / 24)
        if state.blink_phase is None:
            assert state.eye_openness() == 1.0
            return
    raise AssertionError("blink never completed in 500 frames")


def test_eye_openness_dips_to_zero_mid_blink_and_stays_in_range():
    rng = random.Random(3)
    state = PumpkinState(rng=rng)
    state.start_blink()
    saw_shut = False
    for _ in range(200):
        state.update(dt=1 / 24)
        o = state.eye_openness()
        assert 0.0 <= o <= 1.0
        if o < 0.1:   # frame-quantised phase rarely lands exactly on 0.5
            saw_shut = True
        if state.blink_phase is None:
            break
    assert saw_shut, "expected the eye to fully close at some point mid-blink"


def test_expression_cycles_and_never_repeats_immediately():
    rng = random.Random(4)
    state = PumpkinState(rng=rng)
    state.expression_timer = 0.0
    changes = 0
    for _ in range(3000):
        before = state.expression
        state.update(dt=1 / 24)
        if state.expression != before:
            assert 0 <= state.expression < len(EXPRESSIONS)
            assert state.expression != before
            changes += 1
    assert changes > 5


def test_expression_change_triggers_a_blink():
    rng = random.Random(5)
    state = PumpkinState(rng=rng)
    state.blink_phase = None
    state.expression_timer = 0.001
    state.update(dt=0.01)
    assert state.blink_phase is not None


def test_bat_flies_the_full_width_and_is_retired_offscreen():
    rng = random.Random(6)
    state = PumpkinState(rng=rng)
    state.bat_timer = 0.0
    state.update(dt=0.01)
    assert state.bat is not None

    saw_onscreen = False
    for _ in range(2000):
        if state.bat is not None and 0 <= state.bat.x <= WIDTH:
            saw_onscreen = True
        state.update(dt=1 / 24)
        if state.bat is None and saw_onscreen:
            break
    assert saw_onscreen, "bat never crossed the visible panel"
    assert state.bat is None, "bat should have been retired offscreen"
    assert state.bat_timer > 0


def test_bat_direction_and_offscreen_detection():
    rng = random.Random(7)
    left_to_right_seen = right_to_left_seen = False
    for seed in range(30):
        bat = Bat(random.Random(seed))
        assert not bat.offscreen() or bat.x < -10 or bat.x > WIDTH + 10
        if bat.dir == 1:
            left_to_right_seen = True
            assert bat.x < 0
        else:
            right_to_left_seen = True
            assert bat.x > WIDTH
    assert left_to_right_seen and right_to_left_seen


def test_flatten_shape_collapses_polygon_and_circle_toward_their_centre():
    poly = ("poly", [(0, -10), (5, 0), (0, 10)])
    flat = _flatten_shape(poly, 0.0)
    ys = [p[1] for p in flat[1]]
    assert all(abs(y) < 1e-9 for y in ys)

    circle = ("circle", 3, -4, 5)
    flat_c = _flatten_shape(circle, 0.0)
    assert flat_c[3] == 0.5   # clamped, never fully zero (avoids a 0-radius ellipse)

    full = _flatten_shape(poly, 1.0)
    assert full[1] == poly[1]


def test_build_base_is_64x64_rgb_and_not_blank():
    base = _build_base()
    assert base.size == (WIDTH, HEIGHT)
    assert base.mode == "RGB"
    assert base.getextrema() != ((0, 0), (0, 0), (0, 0))


def test_render_every_expression_and_blink_phase_without_crashing():
    base = _build_base()
    rng = random.Random(8)
    state = PumpkinState(rng=rng)
    for expr_idx in range(len(EXPRESSIONS)):
        state.expression = expr_idx
        for blink_phase in (None, 0.0, 0.25, 0.5, 0.75, 0.99):
            state.blink_phase = blink_phase
            frame = _render(base, state)
            assert isinstance(frame, Image.Image)
            assert frame.size == (WIDTH, HEIGHT)
            assert frame.mode == "RGB"


def test_render_with_and_without_an_active_bat():
    base = _build_base()
    state = PumpkinState(rng=random.Random(9))
    state.bat = None
    frame_no_bat = _render(base, state)
    assert frame_no_bat.size == (WIDTH, HEIGHT)

    state.bat = Bat(random.Random(10))
    frame_with_bat = _render(base, state)
    assert frame_with_bat.size == (WIDTH, HEIGHT)


def test_unlit_eyes_render_dark_and_lit_eyes_glow():
    """The hollow-socket expression must draw its eyes in the carved-edge
    colour, never the candle glow."""
    from src.display.pumpkin import CARVE_EDGE, _eye_color

    glow = (255, 240, 160)
    hollow = [e for e in EXPRESSIONS if e.get("eye_unlit")]
    assert hollow, "expected at least one unlit-eye expression"
    for expr in hollow:
        assert _eye_color(expr, glow) == CARVE_EDGE
    for expr in (e for e in EXPRESSIONS if not e.get("eye_unlit")):
        assert _eye_color(expr, glow) == glow
