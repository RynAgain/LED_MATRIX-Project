"""
Tests for the Ring World flyover demo.
"""

import math
from unittest.mock import MagicMock, patch

import pytest

from src.display.ring_world import (
    RingWorldScene, _daylight, _arch_geometry, _make_noise,
    SIZE, HORIZON_Y, NIGHT_FLOOR, DAY_LENGTH, SUN_X, SUN_Y, FRAME_DUR,
)


class TestDaylight:
    def test_noon_is_full_brightness(self):
        assert _daylight(0.0) == pytest.approx(1.0)

    def test_midnight_is_night_floor(self):
        assert _daylight(0.5) == pytest.approx(NIGHT_FLOOR)

    def test_symmetric_around_night(self):
        for d in (0.05, 0.1, 0.15, 0.2):
            assert _daylight(0.5 - d) == pytest.approx(_daylight(0.5 + d))

    def test_monotonic_into_night(self):
        values = [_daylight(p) for p in (0.25, 0.35, 0.42, 0.46, 0.5)]
        for a, b in zip(values, values[1:]):
            assert b <= a + 1e-9

    def test_bounded(self):
        for i in range(100):
            v = _daylight(i / 100.0)
            assert NIGHT_FLOOR - 1e-9 <= v <= 1.0 + 1e-9


class TestArchGeometry:
    def test_feet_sit_on_horizon(self):
        for t in (0.0, 1.0):
            x, y, w = _arch_geometry(t)
            assert y == pytest.approx(HORIZON_Y - 1)

    def test_zenith_is_high(self):
        x, y, w = _arch_geometry(0.5)
        assert y < 8
        assert x == pytest.approx((SIZE - 1) / 2)

    def test_wide_at_feet_thin_at_zenith(self):
        _, _, w_foot = _arch_geometry(0.02)
        _, _, w_top = _arch_geometry(0.5)
        assert w_foot > w_top * 2

    def test_path_in_bounds(self):
        for i in range(101):
            x, y, w = _arch_geometry(i / 100.0)
            assert 0 <= x <= SIZE - 1
            assert 0 <= y <= HORIZON_Y - 1


class TestScene:
    def test_noise_deterministic(self):
        assert _make_noise(42) == _make_noise(42)
        assert _make_noise(42) != _make_noise(43)

    def test_phase_wraps(self):
        scene = RingWorldScene()
        scene.t = DAY_LENGTH * 2.25
        assert scene.phase == pytest.approx(0.25)

    def test_ground_scrolls_with_time(self):
        scene = RingWorldScene()
        c0 = [scene._ground_color(x, 60) for x in range(SIZE)]
        scene.t += 3.0
        c1 = [scene._ground_color(x, 60) for x in range(SIZE)]
        assert c0 != c1

    def test_draw_returns_full_frame(self):
        scene = RingWorldScene()
        img = scene.draw()
        assert img.size == (SIZE, SIZE)

    def test_night_is_darker_than_day(self):
        scene = RingWorldScene()
        scene.t = 0.0                      # noon
        day_img = scene.draw()
        scene.t = DAY_LENGTH * 0.5         # deep night
        night_img = scene.draw()
        day_sum = sum(sum(px) for px in day_img.convert("RGB").getdata())
        night_sum = sum(sum(px) for px in night_img.convert("RGB").getdata())
        assert night_sum < day_sum * 0.6

    def test_arch_still_lit_at_night(self):
        """The far side of the ring is sunlit even during local night."""
        scene = RingWorldScene()
        scene.t = DAY_LENGTH * 0.5
        img = scene.draw()
        # Sample along the arch, avoiding the shadow square near the zenith
        from src.display.ring_world import _arch_geometry
        lit = 0
        for t in (0.1, 0.2, 0.3, 0.7, 0.8, 0.9):
            x, y, w = _arch_geometry(t)
            if sum(img.getpixel((int(x), int(y)))) > 60:
                lit += 1
        assert lit >= 4

    def test_no_dark_star_speckles_at_noon(self):
        """At high noon stars are fully washed out: a starless render of the
        same scene must be pixel-identical (regression for dark speckles)."""
        scene = RingWorldScene()
        scene.t = 0.0
        with_stars = scene.draw()
        scene.stars = []
        without_stars = scene.draw()
        assert list(with_stars.getdata()) == list(without_stars.getdata())

    def test_sun_visible_at_noon_covered_at_night(self):
        scene = RingWorldScene()
        scene.t = 0.0
        noon = scene.draw().getpixel((SUN_X, SUN_Y))
        scene.t = DAY_LENGTH * 0.5
        night = scene.draw().getpixel((SUN_X, SUN_Y))
        assert sum(noon) > 400      # bright sun disc
        assert sum(night) < 60      # behind the shadow square


class TestRunSmoke:
    def test_run_draws_frames(self):
        from src.display import ring_world
        matrix = MagicMock()
        with patch("src.display.ring_world.should_stop", return_value=False):
            ring_world.run(matrix, duration=0.4)
        assert matrix.SetImage.call_count >= 2
        matrix.Clear.assert_called()
