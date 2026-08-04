"""Tests for the giant eyeball demo.

The module splits cleanly into pure behaviour (``EyeState``) and pre-rendered
compositing (``_Renderer``), so both halves are pinned here:

* gaze, pupil and lid values must stay inside their declared limits no matter
  what the random walk does -- the renderer pastes the iris at ``gx``/``gy``
  without re-clamping, so a runaway value would slide the iris out of the
  opening
* the almond aperture must be left/right symmetric, otherwise the eye looks
  broken on a 64px panel
* nothing may be painted outside the aperture: the skin overlay is the only
  thing that hides the sclera rectangle's edges
* ``NEUTRAL_OVERLAP`` exists so a surprised stare renders differently from a
  neutral one; before it, openness > 1.0 was a silent no-op
"""

import math
import random

import pytest

from src.display import big_eye
from src.display.big_eye import (
    EyeState,
    GAZE_DOWN_LIMIT,
    GAZE_UP_LIMIT,
    GAZE_X_LIMIT,
    HEIGHT,
    IRIS_PALETTES,
    IRIS_R,
    PUPIL_MAX,
    PUPIL_MIN,
    WIDTH,
    _Renderer,
    _aperture_bounds,
    _build_iris,
    _build_masks,
    _mix,
)


class _Recorder:
    """Minimal matrix stand-in that counts pushed frames."""

    def __init__(self):
        self.frames = 0
        self.last = None
        self.cleared = 0

    def SetImage(self, image, *args, **kwargs):
        self.frames += 1
        self.last = image.copy()

    def Clear(self):
        self.cleared += 1


@pytest.fixture(autouse=True)
def _clear_stop():
    from src.display import _shared
    _shared.clear_stop()
    yield
    _shared.clear_stop()


# --- helpers ---------------------------------------------------------------

def _state(seed=7):
    return EyeState(rng=random.Random(seed))


def _renderer():
    return _Renderer(0)


# --- constants -------------------------------------------------------------

def test_palettes_are_well_formed():
    assert len(IRIS_PALETTES) >= 2
    for palette in IRIS_PALETTES:
        assert len(palette) == 3
        for color in palette:
            assert len(color) == 3
            assert all(0 <= c <= 255 for c in color)


def test_mix_clamps_and_interpolates():
    assert _mix((0, 0, 0), (100, 200, 250), 0.0) == (0, 0, 0)
    assert _mix((0, 0, 0), (100, 200, 250), 1.0) == (100, 200, 250)
    assert _mix((0, 0, 0), (100, 200, 250), -5.0) == (0, 0, 0)
    assert _mix((0, 0, 0), (100, 200, 250), 5.0) == (100, 200, 250)
    assert _mix((0, 0, 0), (100, 100, 100), 0.5) == (50, 50, 50)


# --- aperture --------------------------------------------------------------

def test_aperture_is_left_right_symmetric():
    bounds = _aperture_bounds()
    assert len(bounds) == WIDTH
    for d in range(0, 32):
        left = bounds[big_eye.EYE_CX - d]
        right = bounds[big_eye.EYE_CX + d]
        if left is None or right is None:
            assert left is None and right is None, f"asymmetric at d={d}"
            continue
        assert left == pytest.approx(right)


def test_aperture_is_an_almond_not_an_ellipse():
    """Upper lid curves more than the lower, and the edges close off."""
    bounds = _aperture_bounds()
    centre = bounds[big_eye.EYE_CX]
    assert centre is not None
    top, bot = centre
    assert big_eye.EYE_CY - top == pytest.approx(big_eye.APERTURE_UP)
    assert bot - big_eye.EYE_CY == pytest.approx(big_eye.APERTURE_DOWN)
    # More travel above the centre line than below.
    assert big_eye.APERTURE_UP > big_eye.APERTURE_DOWN
    # The extreme columns are outside the opening.
    assert bounds[0] is None
    assert bounds[WIDTH - 1] is None


def test_aperture_stays_on_the_panel():
    for b in _aperture_bounds():
        if b is None:
            continue
        top, bot = b
        assert 0 <= top < bot < HEIGHT


def test_masks_are_complementary():
    inside, outside = _build_masks(_aperture_bounds())
    assert inside.size == (WIDTH, HEIGHT)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            assert inside.getpixel((x, y)) + outside.getpixel((x, y)) == 255
    # The opening actually covers a meaningful part of the panel.
    lit = sum(1 for p in inside.tobytes() if p)
    assert 1200 < lit < WIDTH * HEIGHT


# --- iris ------------------------------------------------------------------

def test_build_iris_shape_and_mask():
    img, mask = _build_iris(IRIS_PALETTES[0])
    size = IRIS_R * 2 + 1
    assert img.size == (size, size)
    assert mask.size == (size, size)
    assert mask.getpixel((0, 0)) == 0                    # corner outside disc
    assert mask.getpixel((IRIS_R, IRIS_R)) == 255        # centre inside
    assert mask.getpixel((IRIS_R, 0)) == 255             # top of the circle


def test_build_iris_is_deterministic():
    a, _ = _build_iris(IRIS_PALETTES[1])
    b, _ = _build_iris(IRIS_PALETTES[1])
    assert a.tobytes() == b.tobytes()


def test_iris_fits_inside_the_aperture_at_rest():
    """A centred iris must not poke through the left/right corners."""
    assert IRIS_R <= big_eye.APERTURE_HALF_W


# --- gaze ------------------------------------------------------------------

def test_gaze_is_clamped_to_its_limits():
    s = _state()
    s.tx, s.ty = 1000.0, 1000.0
    for _ in range(30):
        s.update(0.01)
    assert s.gx <= GAZE_X_LIMIT + 1e-9
    assert s.gy <= GAZE_DOWN_LIMIT + 1e-9

    s = _state()
    s.tx, s.ty = -1000.0, -1000.0
    for _ in range(30):
        s.update(0.01)
    assert s.gx >= -GAZE_X_LIMIT - 1e-9
    assert s.gy >= -GAZE_UP_LIMIT - 1e-9


def test_long_run_keeps_every_value_in_range():
    s = _state(seed=99)
    seen_blink = False
    min_open = 2.0
    max_open = -1.0
    for _ in range(30 * 120):  # two simulated minutes
        s.update(1.0 / 30)
        assert -GAZE_X_LIMIT - 1e-9 <= s.gx <= GAZE_X_LIMIT + 1e-9
        assert -GAZE_UP_LIMIT - 1e-9 <= s.gy <= GAZE_DOWN_LIMIT + 1e-9
        assert PUPIL_MIN - 1e-9 <= s.pupil <= PUPIL_MAX + 1e-9
        o = s.lid_openness()
        assert 0.0 <= o <= 1.15 + 1e-9
        min_open = min(min_open, o)
        max_open = max(max_open, o)
        if s.blink_phase is not None:
            seen_blink = True
    assert seen_blink, "no blink in two minutes"
    assert min_open < 0.05, "lids never fully shut"
    assert max_open > 0.95, "lids never fully opened"


def test_pupil_target_stays_within_limits_after_saccade():
    s = _state()
    s.pupil_target = PUPIL_MIN
    s._new_gaze_target()
    assert s.pupil_target >= PUPIL_MIN


# --- blinks ----------------------------------------------------------------

def test_single_blink_shuts_then_completes():
    s = _state()
    s.blink_timer = 999.0          # no spontaneous blink
    s.start_blink()
    assert s.blink_phase is not None
    shut = 2.0
    for _ in range(200):
        s._tick_blink(1.0 / 30)
        shut = min(shut, s.lid_openness())
        if s.blink_phase is None:
            break
    assert s.blink_phase is None, "blink never finished"
    assert shut < 0.02, "lids did not close"
    assert s.lid_openness() == pytest.approx(s.open)


def test_double_blink_closes_twice():
    s = _state()
    s.blink_timer = 999.0
    s.start_blink(count=2)
    closures = 0
    was_open = True
    for _ in range(400):
        s._tick_blink(1.0 / 30)
        closed = s.lid_openness() < 0.05
        if closed and was_open:
            closures += 1
        was_open = not closed
        if s.blink_phase is None:
            break
    assert s.blink_phase is None
    assert closures == 2, f"expected two closures, saw {closures}"


def test_long_blink_changes_the_palette():
    s = _state()
    s.blink_timer = 999.0
    start = s.palette_index
    s.start_blink(count=1, long=True)
    assert s.blink_speed < 6.0, "long blink should be slower"
    for _ in range(400):
        s._tick_blink(1.0 / 30)
        if s.blink_phase is None:
            break
    assert s.palette_changed is True
    assert s.palette_index != start
    assert 0 <= s.palette_index < len(IRIS_PALETTES)
    assert s.long_blink is False


def test_palette_changed_is_a_one_frame_pulse():
    s = _state()
    s.palette_changed = True
    s.update(1.0 / 30)
    # update() clears the flag unless a long blink finished on this very tick.
    if s.blink_phase is not None or not s.long_blink:
        assert s.palette_changed is False


def test_start_blink_does_not_restart_an_in_flight_blink():
    s = _state()
    s.blink_timer = 999.0
    s.start_blink()
    s._tick_blink(1.0 / 30)
    phase = s.blink_phase
    s.start_blink()
    assert s.blink_phase == phase


# --- renderer --------------------------------------------------------------

def test_render_returns_a_full_panel_frame():
    r = _renderer()
    s = _state()
    frame = r.render(s)
    assert frame.size == (WIDTH, HEIGHT)
    assert frame.mode == "RGB"


@pytest.mark.parametrize("gx,gy", [
    (0.0, 0.0),
    (GAZE_X_LIMIT, GAZE_DOWN_LIMIT),
    (-GAZE_X_LIMIT, -GAZE_UP_LIMIT),
    (GAZE_X_LIMIT, -GAZE_UP_LIMIT),
])
def test_nothing_is_painted_outside_the_aperture(gx, gy):
    r = _renderer()
    s = _state()
    s.gx, s.gy = gx, gy
    s.pupil = PUPIL_MAX
    frame = r.render(s)
    for x in range(WIDTH):
        for y in range(HEIGHT):
            b = r.bounds[x]
            if b is not None and b[0] - 1 <= y <= b[1] + 1:
                continue
            assert frame.getpixel((x, y)) == r.skin.getpixel((x, y)), (
                f"leak at ({x}, {y}) with gaze ({gx}, {gy})")


def _visible_sclera(frame, skin):
    """Pixels that differ from the bare skin layer, i.e. eye is showing."""
    return sum(1 for a, b in zip(frame.tobytes(), skin.tobytes()) if a != b) // 3


def test_surprise_exposes_more_of_the_eye_than_neutral():
    r = _renderer()
    s = _state()
    s.gx = s.gy = 0.0

    s.open = 1.0
    neutral = _visible_sclera(r.render(s), r.skin)
    s.open = 1.14
    wide = _visible_sclera(r.render(s), r.skin)
    s.open = 0.5
    squint = _visible_sclera(r.render(s), r.skin)

    assert wide > neutral > squint > 0


def test_shut_lids_hide_the_eye_completely():
    r = _renderer()
    s = _state()
    s.open = 0.0
    frame = r.render(s)
    # Only the lash lines survive; the sclera and iris are gone.
    assert _visible_sclera(frame, r.skin) < 200


def test_neutral_overlap_crops_the_iris():
    """At rest the lids overlap the opening, so some of it is covered."""
    assert 0.0 < _Renderer.NEUTRAL_OVERLAP < 0.5
    r = _renderer()
    s = _state()
    s.open = 1.0
    frame = r.render(s)
    # The very top of the opening at the centre column must be lid, not sclera.
    top = int(round(r.bounds[big_eye.EYE_CX][0]))
    assert frame.getpixel((big_eye.EYE_CX, top)) == r.skin.getpixel(
        (big_eye.EYE_CX, top))


def test_set_palette_swaps_the_iris_and_wraps():
    r = _renderer()
    first = r.iris.tobytes()
    r.set_palette(1)
    assert r.iris.tobytes() != first
    r.set_palette(len(IRIS_PALETTES))       # wraps back to 0
    assert r.iris.tobytes() == first
    r.set_palette(-1)                       # negative index must not raise
    assert r.iris.size == (IRIS_R * 2 + 1,) * 2


def test_pupil_is_black_at_the_gaze_centre():
    r = _renderer()
    s = _state()
    s.gx = s.gy = 0.0
    s.pupil = 8.0
    s.open = 1.0
    frame = r.render(s)
    assert frame.getpixel((big_eye.EYE_CX, big_eye.EYE_CY)) == (0, 0, 0)


# --- run() -----------------------------------------------------------------

def test_run_pushes_frames_and_clears():
    m = _Recorder()
    big_eye.run(m, duration=0.4)
    assert m.frames > 0
    assert m.cleared == 1
    assert m.last.size == (WIDTH, HEIGHT)


def test_run_honours_a_zero_duration():
    m = _Recorder()
    big_eye.run(m, duration=0.0)
    assert m.frames == 0
    assert m.cleared == 1


def test_run_stops_on_request():
    from src.display import _shared
    m = _Recorder()
    _shared.request_stop()
    big_eye.run(m, duration=30)
    assert m.frames == 0
    assert m.cleared == 1


def test_run_survives_a_broken_matrix():
    class Broken:
        def SetImage(self, *a, **k):
            raise RuntimeError("panel gone")

        def Clear(self):
            raise RuntimeError("still gone")

    big_eye.run(Broken(), duration=0.2)   # must not raise


def test_run_applies_a_palette_change_mid_demo(monkeypatch):
    """A long blink finishing must reach the renderer, not just the state."""
    swaps = []
    original = _Renderer.set_palette

    def spy(self, index):
        swaps.append(index)
        return original(self, index)

    monkeypatch.setattr(_Renderer, "set_palette", spy)

    real_update = EyeState.update
    calls = {"n": 0}

    def forced(self, dt):
        real_update(self, dt)
        calls["n"] += 1
        if calls["n"] == 2:
            self.palette_index = 3
            self.palette_changed = True

    monkeypatch.setattr(EyeState, "update", forced)
    big_eye.run(_Recorder(), duration=0.3)
    assert 3 in swaps[1:], f"palette change never applied: {swaps}"


def test_frame_interval_is_a_sane_frame_rate():
    fps = 1.0 / big_eye.FRAME_INTERVAL
    assert 15 <= fps <= 60
    assert math.isfinite(fps)
