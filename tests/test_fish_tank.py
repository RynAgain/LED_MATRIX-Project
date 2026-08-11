"""
Tests for the fish tank improvements: minnow school, feeding events,
light rays, and surface shimmer.
"""

import math
import time
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw

from src.display.fish_tank import (
    WIDTH, HEIGHT, Fish, Flake, School, Bubble,
    _build_rays_image, _draw_background, _draw_surface_shimmer,
    FLAKE_EAT_RADIUS,
)


class TestFlake:
    def test_flake_sinks(self):
        flake = Flake(x=32, y=2)
        y0 = flake.y
        for _ in range(20):
            flake.update()
        assert flake.y > y0

    def test_flake_dies_at_sand(self):
        flake = Flake(x=32, y=HEIGHT - 10)
        alive = True
        for _ in range(60):
            alive = flake.update()
            if not alive:
                break
        assert not alive
        assert flake.y >= HEIGHT - 9 - 1

    def test_eaten_flake_is_removed(self):
        flake = Flake(x=32, y=20)
        flake.eaten = True
        assert flake.update() is False

    def test_flake_draws_in_bounds(self):
        img = Image.new("RGB", (WIDTH, HEIGHT))
        draw = ImageDraw.Draw(img)
        flake = Flake(x=32, y=20)
        flake.draw(draw)
        assert img.getpixel((int(flake.x), int(flake.y))) != (0, 0, 0)


class TestFishFeeding:
    def test_fish_turns_toward_food(self):
        fish = Fish()
        fish.x, fish.y = 20.0, 30.0
        fish.direction = -1
        flake = Flake(x=40, y=30)
        flake.vy = 0.0
        fish.update(0, [fish], [flake])
        assert fish.direction == 1

    def test_fish_closes_distance_to_food(self):
        fish = Fish()
        fish.x, fish.y = 20.0, 30.0
        flake = Flake(x=38, y=34)
        flake.vy = 0.0
        flake.drift_phase = 0.0
        d0 = math.hypot(flake.x - fish.x, flake.y - fish.y)
        for _ in range(12):
            fish.update(0, [fish], [flake])
        d1 = math.hypot(flake.x - fish.x, flake.y - fish.y)
        assert d1 < d0

    def test_fish_eats_adjacent_flake(self):
        fish = Fish()
        fish.x, fish.y = 30.0, 30.0
        flake = Flake(x=30.5, y=30.5)
        fish.update(0, [fish], [flake])
        assert flake.eaten

    def test_fish_ignores_distant_food(self):
        fish = Fish()
        fish.x, fish.y = 32.0, 12.0
        flake = Flake(x=32, y=52)  # far outside seek radius
        d = fish.direction
        fish.update(0, [fish], [flake])
        assert not flake.eaten
        assert fish.direction == d  # not steered by it

    def test_update_without_flakes_still_works(self):
        fish = Fish()
        fish.update(0, [fish])
        fish.update(0, [fish], None)
        fish.update(0, [fish], [])


class TestSchool:
    def test_school_stays_cohesive(self):
        school = School()
        for _ in range(150):
            school.update()
        cx = sum(m[0] for m in school.minnows) / len(school.minnows)
        cy = sum(m[1] for m in school.minnows) / len(school.minnows)
        for m in school.minnows:
            assert math.hypot(m[0] - cx, m[1] - cy) < 14

    def test_school_stays_in_tank(self):
        school = School()
        school.vx, school.vy = 1.2, 0.4
        for _ in range(400):
            school.update()
            cx = sum(m[0] for m in school.minnows) / len(school.minnows)
            assert -6 <= cx <= WIDTH + 6
            for m in school.minnows:
                assert 5 <= m[1] <= HEIGHT - 11

    def test_school_steers_toward_food(self):
        school = School()
        # Park the school and put food nearby
        for m in school.minnows:
            m[0], m[1] = 20.0, 25.0
        school.vx, school.vy = 0.0, 0.0
        flake = Flake(x=35, y=30)
        flake.vy = 0.0
        flake.drift_phase = 0.0
        for _ in range(30):
            school.update([flake])
            if flake.eaten:
                break
        cx = sum(m[0] for m in school.minnows) / len(school.minnows)
        assert flake.eaten or cx > 21.0

    def test_minnows_eat_flakes(self):
        school = School()
        m = school.minnows[0]
        flake = Flake(x=m[0], y=m[1])
        school.update([flake])
        assert flake.eaten

    def test_school_draws_pixels(self):
        img = Image.new("RGB", (WIDTH, HEIGHT))
        draw = ImageDraw.Draw(img)
        school = School()
        school.draw(draw)
        lit = sum(1 for px in img.getdata() if px != (0, 0, 0))
        assert lit >= len(school.minnows)


class TestRaysAndShimmer:
    def test_rays_image_brighter_than_background(self):
        bg = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        _draw_background(ImageDraw.Draw(bg))
        rays = _build_rays_image(bg)
        assert rays.size == bg.size
        bg_sum = sum(sum(px) for px in bg.getdata())
        rays_sum = sum(sum(px) for px in rays.getdata())
        assert rays_sum > bg_sum

    def test_rays_never_dim_the_background(self):
        bg = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        _draw_background(ImageDraw.Draw(bg))
        rays = _build_rays_image(bg)
        for (b, r) in zip(bg.getdata(), rays.getdata()):
            assert r[0] >= b[0] and r[1] >= b[1] and r[2] >= b[2]

    def test_shimmer_lights_surface_rows(self):
        img = Image.new("RGB", (WIDTH, HEIGHT))
        draw = ImageDraw.Draw(img)
        _draw_surface_shimmer(draw, tick=10)
        top_two = [img.getpixel((x, y)) for x in range(WIDTH) for y in (0, 1)]
        assert any(px != (0, 0, 0) for px in top_two)
        # Nothing below row 1
        rest = [img.getpixel((x, 2)) for x in range(WIDTH)]
        assert all(px == (0, 0, 0) for px in rest)


class TestRunSmoke:
    def test_run_draws_frames(self):
        from src.display import fish_tank
        matrix = MagicMock()
        with patch("src.display.fish_tank.should_stop", return_value=False):
            fish_tank.run(matrix, duration=0.4)
        assert matrix.SetImage.call_count >= 2
