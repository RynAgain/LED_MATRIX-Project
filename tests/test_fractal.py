"""Tests for the fractal unfolding demo.

fractal.py had no test coverage at all (it was missing from DISPLAY_MODULES),
which is why a set of layout and pacing defects went unnoticed:

* the dragon curve raised ZeroDivisionError for any duration shorter than one
  frame interval, which run() then swallowed
* the Sierpinski carpet claimed 5 levels but a 64px panel only supports 3, so
  the deepest visible level finished 54% into the segment and the rest was a
  frozen image; integer thirds also pushed the pattern off-centre
* the dragon curve used 12 iterations, a 95px-wide bounding box squashed to
  scale 0.63, so two thirds of the computed points landed on already-lit pixels
* the Sierpinski triangle pre-sized its point budget to an assumed 30fps and
  came out half-drawn on hardware that rendered slower

These tests pin all of the above.
"""

import time

import pytest

from src.display import fractal
from src.display._utils import _hsv_to_rgb


class _Recorder:
    """Minimal matrix stand-in that keeps the last pushed frame."""

    def __init__(self):
        self.frames = 0
        self.last = None

    def SetImage(self, image, *args, **kwargs):
        self.frames += 1
        self.last = image.copy()

    def Clear(self):
        pass


@pytest.fixture(autouse=True)
def _clear_stop():
    from src.display import _shared
    _shared.clear_stop()
    yield
    _shared.clear_stop()


class TestSubFractalDurations:
    """Every sub-fractal must survive the short durations run() can hand it."""

    @pytest.mark.parametrize("fn_name", [
        "_run_sierpinski", "_run_mandelbrot", "_run_dragon_curve", "_run_carpet",
    ])
    @pytest.mark.parametrize("duration", [0.001, 0.02, 0.05, 0.4])
    def test_short_duration_does_not_raise(self, fn_name, duration):
        fn = getattr(fractal, fn_name)
        fn(_Recorder(), duration=duration)

    def test_dragon_curve_sub_frame_duration(self):
        """Regression: duration < FRAME_INTERVAL floored to 0 and divided by it."""
        assert fractal.FRAME_INTERVAL > 0.001
        fractal._run_dragon_curve(_Recorder(), duration=0.001)


class TestSierpinskiTriangle:
    def test_generator_is_unbounded_by_default(self):
        """The reveal must be paced by the wall clock, not an assumed 30fps."""
        gen = fractal._sierpinski_points()
        pts = [next(gen) for _ in range(20000)]
        assert len(pts) == 20000

    def test_generator_respects_explicit_limit(self):
        assert len(list(fractal._sierpinski_points(37))) == 37

    def test_all_points_land_on_the_triangle(self):
        """The chaos-game burn-in must discard the off-attractor transient."""
        pts = list(fractal._sierpinski_points(2000))
        assert all(0 <= x < fractal.WIDTH and 0 <= y < fractal.HEIGHT
                   for x, y in pts)

    def test_burn_in_is_applied(self):
        assert fractal._CHAOS_BURN_IN >= 5

    def test_draws_pixels(self):
        rec = _Recorder()
        fractal._run_sierpinski(rec, duration=1.0)
        px = rec.last.load()
        lit = sum(1 for y in range(64) for x in range(64) if px[x, y] != (0, 0, 0))
        assert lit > 200, f"only {lit} pixels lit"


class TestDragonCurve:
    def test_point_count(self):
        assert len(fractal._dragon_curve_points(11)) == 2048

    def test_iterations_fit_the_panel_at_unit_scale(self):
        """11 iterations is the largest curve that fits without being squashed."""
        pts = fractal._dragon_curve_points(11)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        range_x = max(xs) - min(xs)
        range_y = max(ys) - min(ys)
        available = float(fractal.WIDTH - 1)
        scale = min(available / range_x, available / range_y)
        assert scale == pytest.approx(1.0, abs=0.05), (
            f"curve is being rescaled by {scale:.3f}; detail collapses"
        )

    def test_steps_are_unit_length(self):
        """Consecutive lattice points must be adjacent, or the walk is broken."""
        pts = fractal._dragon_curve_points(9)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            assert abs(x1 - x0) + abs(y1 - y0) == 1

    def test_draws_pixels(self):
        rec = _Recorder()
        fractal._run_dragon_curve(rec, duration=1.0)
        px = rec.last.load()
        lit = sum(1 for y in range(64) for x in range(64) if px[x, y] != (0, 0, 0))
        assert lit > 100, f"only {lit} pixels lit"


class TestCarpet:
    def test_max_level_matches_what_the_panel_can_render(self):
        """64 -> 21.3 -> 7.1 -> 2.4; below ~3px there is no centre to carve."""
        size = float(fractal.WIDTH)
        levels = 0
        while size / 3.0 >= 1.0:
            size /= 3.0
            levels += 1
        assert fractal._CARPET_MAX_LEVEL == levels - 1

    def test_only_declared_levels_draw(self, monkeypatch):
        seen = []
        real = fractal._depth_color

        def spy(depth, max_depth, hue_offset=0.0):
            seen.append(depth)
            return real(depth, max_depth, hue_offset)

        monkeypatch.setattr(fractal, "_depth_color", spy)
        fractal._run_carpet(_Recorder(), duration=0.4)
        assert sorted(set(seen)) == list(range(fractal._CARPET_MAX_LEVEL + 1))

    def test_deepest_level_finishes_near_the_end_of_the_segment(self):
        """Otherwise the tail of the segment is a frozen image."""
        max_level = fractal._CARPET_MAX_LEVEL
        time_per_level = 1.0 / (max_level + 1)
        done = max_level * time_per_level + time_per_level * 0.7
        assert done >= 0.85, f"deepest level done at {done:.0%}, tail is frozen"

    def test_pattern_is_horizontally_centred(self):
        """Integer thirds truncated 64->63 and pushed the carpet left/up."""
        rec = _Recorder()
        fractal._run_carpet(rec, duration=1.2)
        px = rec.last.load()
        lit_cols = [x for x in range(64)
                    if any(px[x, y] != (0, 0, 0) for y in range(64))]
        left_margin = min(lit_cols)
        right_margin = 63 - max(lit_cols)
        assert left_margin == right_margin, (
            f"carpet off-centre: {left_margin}px left vs {right_margin}px right"
        )

    def test_pattern_is_vertically_centred(self):
        rec = _Recorder()
        fractal._run_carpet(rec, duration=1.2)
        px = rec.last.load()
        lit_rows = [y for y in range(64)
                    if any(px[x, y] != (0, 0, 0) for x in range(64))]
        assert min(lit_rows) == 63 - max(lit_rows)


class TestMandelbrot:
    def test_iteration_is_bounded(self):
        """Interior points must return max_iter rather than looping forever."""
        assert fractal._mandelbrot_iter(0.0, 0.0, 50) == 50

    def test_escaping_point_returns_early(self):
        assert fractal._mandelbrot_iter(2.0, 2.0, 50) < 5

    def test_known_boundary_point_has_detail(self):
        """The zoom target must not be inside the set (a blank screen)."""
        iters = fractal._mandelbrot_iter(-0.7436439, 0.1318259, 80)
        assert 0 < iters <= 80

    def test_draws_pixels(self):
        rec = _Recorder()
        fractal._run_mandelbrot(rec, duration=0.5)
        px = rec.last.load()
        lit = sum(1 for y in range(64) for x in range(64) if px[x, y] != (0, 0, 0))
        assert lit > 100, f"only {lit} pixels lit"


class TestColorHelper:
    def test_uses_the_shared_hsv_helper(self):
        """The local _hue_to_rgb copy was a duplicate of _utils._hsv_to_rgb."""
        assert not hasattr(fractal, "_hue_to_rgb")

    def test_depth_color_matches_shared_helper(self):
        for depth in (0, 3, 7, 10):
            hue = (depth / 10 * 0.7) % 1.0
            assert fractal._depth_color(depth, 10) == _hsv_to_rgb(hue, 1.0, 1.0)

    def test_zero_max_depth_does_not_divide_by_zero(self):
        assert fractal._depth_color(0, 0) is not None


class TestRun:
    def test_run_completes_within_its_budget(self):
        rec = _Recorder()
        start = time.time()
        fractal.run(rec, duration=6)
        elapsed = time.time() - start
        assert 5.0 <= elapsed <= 9.0, f"took {elapsed:.1f}s for a 6s budget"
        assert rec.frames > 50

    @pytest.mark.parametrize("duration", [0.001, 0.05, 0.5, 2.0])
    def test_run_survives_odd_durations(self, duration):
        fractal.run(_Recorder(), duration=duration)

    def test_stop_flag_ends_run_promptly(self):
        from src.display import _shared

        _shared.request_stop()
        start = time.time()
        fractal.run(_Recorder(), duration=60)
        assert time.time() - start < 5.0
