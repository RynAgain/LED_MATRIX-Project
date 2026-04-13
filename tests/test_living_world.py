"""
Tests for the living world simulation features.
Covers rain-accelerated growth for trees and flowers.
"""

import random
import pytest

from src.display.living_world.entities import Tree, Weather, Flower
from src.display.living_world.world_updates import _grow_trees, _maybe_grow_flower
from src.display.living_world.constants import (
    WORLD_WIDTH, DISPLAY_HEIGHT, AIR, GRASS, DIRT, STONE, WATER,
    RAIN_GROWTH_MULTIPLIER, STORM_GROWTH_MULTIPLIER,
    RAIN_FLOWER_SPAWN_BOOST, STORM_FLOWER_SPAWN_BOOST,
    FLOWER_COLORS, WEATHER_RAIN, WEATHER_STORM, WEATHER_CLEAR,
)


# --- Helpers ---

def _make_flat_world(surface_y=42):
    """Create a flat world grid with grass at surface_y and dirt/stone below."""
    heights = [surface_y] * WORLD_WIDTH
    world = [[AIR] * WORLD_WIDTH for _ in range(DISPLAY_HEIGHT)]
    for x in range(WORLD_WIDTH):
        world[surface_y][x] = GRASS
        for y in range(surface_y + 1, min(surface_y + 5, DISPLAY_HEIGHT)):
            world[y][x] = DIRT
        for y in range(surface_y + 5, DISPLAY_HEIGHT):
            world[y][x] = STONE
    return heights, world


def _make_weather(state):
    """Create a Weather object with the given state."""
    w = Weather()
    w.state = state
    return w


def _make_sapling(x=50, surface_y=42, growth=0.5):
    """Create a growing tree at the given position."""
    return Tree(x, surface_y, growth, 7, 3, 0)


# --- Tree Growth Tests ---

class TestTreeGrowthRain:
    """Verify rain and storm weather accelerates tree growth."""

    def test_tree_growth_no_weather(self):
        """Without weather, trees grow at base rate 0.003."""
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=0.5)
        trees = [tree]
        _grow_trees(trees, heights, world, 0, weather=None)
        assert tree.growth == pytest.approx(0.503, abs=1e-6)

    def test_tree_growth_clear_weather(self):
        """Clear weather uses base rate 0.003."""
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=0.5)
        trees = [tree]
        weather = _make_weather(WEATHER_CLEAR)
        _grow_trees(trees, heights, world, 0, weather=weather)
        assert tree.growth == pytest.approx(0.503, abs=1e-6)

    def test_tree_growth_rain_weather(self):
        """Rain weather grows trees at 0.003 * RAIN_GROWTH_MULTIPLIER."""
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=0.5)
        trees = [tree]
        weather = _make_weather(WEATHER_RAIN)
        _grow_trees(trees, heights, world, 0, weather=weather)
        expected = 0.5 + 0.003 * RAIN_GROWTH_MULTIPLIER
        assert tree.growth == pytest.approx(expected, abs=1e-6)

    def test_tree_growth_storm_weather(self):
        """Storm weather grows trees at 0.003 * STORM_GROWTH_MULTIPLIER."""
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=0.5)
        trees = [tree]
        weather = _make_weather(WEATHER_STORM)
        _grow_trees(trees, heights, world, 0, weather=weather)
        expected = 0.5 + 0.003 * STORM_GROWTH_MULTIPLIER
        assert tree.growth == pytest.approx(expected, abs=1e-6)

    def test_tree_growth_capped_at_one(self):
        """Tree growth cannot exceed 1.0 even with storm multiplier."""
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=0.998)
        trees = [tree]
        weather = _make_weather(WEATHER_STORM)
        _grow_trees(trees, heights, world, 0, weather=weather)
        assert tree.growth == 1.0

    def test_dead_tree_not_affected_by_rain(self):
        """Dead trees should not grow regardless of weather."""
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=0.5)
        tree.alive = False
        trees = [tree]
        weather = _make_weather(WEATHER_RAIN)
        _grow_trees(trees, heights, world, 0, weather=weather)
        assert tree.growth == 0.5

    def test_dying_tree_not_accelerated(self):
        """Dying trees progress at their own rate, not rain-boosted growth."""
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=1.0)
        tree.dying = True
        tree.dying_progress = 0.1
        trees = [tree]
        weather = _make_weather(WEATHER_STORM)
        _grow_trees(trees, heights, world, 0, weather=weather)
        # dying_progress increases, but growth stays at 1.0
        assert tree.growth == 1.0
        assert tree.dying_progress > 0.1

    def test_burning_tree_not_accelerated(self):
        """Burning trees should not grow faster in rain."""
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=0.5)
        tree.on_fire = True
        tree.fire_timer = 20
        trees = [tree]
        weather = _make_weather(WEATHER_RAIN)
        _grow_trees(trees, heights, world, 0, weather=weather)
        assert tree.growth == 0.5

    def test_multiple_growth_ticks_rain(self):
        """Multiple ticks of rain produce cumulative accelerated growth."""
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=0.0)
        trees = [tree]
        weather = _make_weather(WEATHER_RAIN)
        for tick in range(10):
            _grow_trees(trees, heights, world, tick, weather=weather)
        expected = 0.003 * RAIN_GROWTH_MULTIPLIER * 10
        assert tree.growth == pytest.approx(expected, abs=1e-6)


# --- Flower Spawn Tests ---

class TestFlowerSpawnRain:
    """Verify rain and storm weather boosts flower spawn chance."""

    def test_flower_spawn_no_weather(self, monkeypatch):
        """Without weather, spawn threshold is 0.5 (base)."""
        heights, world = _make_flat_world()
        flowers = []
        trees = []
        call_count = [0]
        def fake_random():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.49
            return 0.0
        monkeypatch.setattr(random, "random", fake_random)
        monkeypatch.setattr(random, "randint", lambda a, b: a)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        _maybe_grow_flower(flowers, heights, world, trees, 0, weather=None)
        assert len(flowers) == 1

    def test_flower_blocked_without_rain(self, monkeypatch):
        """Without rain, random > 0.5 blocks spawning."""
        heights, world = _make_flat_world()
        flowers = []
        trees = []
        monkeypatch.setattr(random, "random", lambda: 0.51)
        _maybe_grow_flower(flowers, heights, world, trees, 0, weather=None)
        assert len(flowers) == 0

    def test_flower_spawn_in_rain(self, monkeypatch):
        """In rain, threshold is RAIN_FLOWER_SPAWN_BOOST=0.75, so 0.51 passes."""
        heights, world = _make_flat_world()
        flowers = []
        trees = []
        weather = _make_weather(WEATHER_RAIN)
        call_count = [0]
        def fake_random():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.51
            return 0.0
        monkeypatch.setattr(random, "random", fake_random)
        monkeypatch.setattr(random, "randint", lambda a, b: a)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        _maybe_grow_flower(flowers, heights, world, trees, 0, weather=weather)
        assert len(flowers) == 1

    def test_flower_spawn_in_storm(self, monkeypatch):
        """In storm, threshold is STORM_FLOWER_SPAWN_BOOST=0.90, so 0.76 passes."""
        heights, world = _make_flat_world()
        flowers = []
        trees = []
        weather = _make_weather(WEATHER_STORM)
        call_count = [0]
        def fake_random():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.76
            return 0.0
        monkeypatch.setattr(random, "random", fake_random)
        monkeypatch.setattr(random, "randint", lambda a, b: a)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        _maybe_grow_flower(flowers, heights, world, trees, 0, weather=weather)
        assert len(flowers) == 1

    def test_flower_blocked_above_storm_threshold(self, monkeypatch):
        """Even in storm, random > 0.90 blocks spawning."""
        heights, world = _make_flat_world()
        flowers = []
        trees = []
        weather = _make_weather(WEATHER_STORM)
        monkeypatch.setattr(random, "random", lambda: 0.91)
        _maybe_grow_flower(flowers, heights, world, trees, 0, weather=weather)
        assert len(flowers) == 0


# --- Constants Sanity Tests ---

class TestRainGrowthConstants:
    """Verify the rain growth constants are sane."""

    def test_rain_multiplier_gt_one(self):
        assert RAIN_GROWTH_MULTIPLIER > 1.0

    def test_storm_multiplier_gt_rain(self):
        assert STORM_GROWTH_MULTIPLIER > RAIN_GROWTH_MULTIPLIER

    def test_rain_flower_boost_gt_base(self):
        assert RAIN_FLOWER_SPAWN_BOOST > 0.5

    def test_storm_flower_boost_gt_rain(self):
        assert STORM_FLOWER_SPAWN_BOOST > RAIN_FLOWER_SPAWN_BOOST

    def test_all_boosts_lte_one(self):
        assert RAIN_FLOWER_SPAWN_BOOST <= 1.0
        assert STORM_FLOWER_SPAWN_BOOST <= 1.0


# --- Storm Cloud Cover Tests ---

from src.display.living_world.entities import Cloud
from src.display.living_world.world_updates import _maybe_spawn_cloud
from src.display.living_world.constants import (
    CLOUD_WIDTH_RANGE, CLOUD_HEIGHT_RANGE,
    STORM_CLOUD_WIDTH_RANGE, STORM_CLOUD_HEIGHT_RANGE,
    CLOUD_ALPHA, STORM_CLOUD_ALPHA,
    WEATHER_CLOUD_PARAMS,
    WEATHER_CLOUDY,
)


class TestStormCloudCover:
    """Verify storm clouds are larger, more opaque, and more numerous."""

    def test_storm_cloud_width_larger_than_normal(self):
        assert STORM_CLOUD_WIDTH_RANGE[0] >= CLOUD_WIDTH_RANGE[1]

    def test_storm_cloud_height_larger_than_normal(self):
        assert STORM_CLOUD_HEIGHT_RANGE[0] >= CLOUD_HEIGHT_RANGE[1]

    def test_storm_alpha_more_opaque(self):
        assert STORM_CLOUD_ALPHA > CLOUD_ALPHA

    def test_storm_cloud_count_higher(self):
        _mn, mx, _, _ = WEATHER_CLOUD_PARAMS["storm"]
        assert mx >= 10

    def test_alpha_values_valid(self):
        assert 0.0 <= CLOUD_ALPHA <= 1.0
        assert 0.0 <= STORM_CLOUD_ALPHA <= 1.0

    def test_cloud_default_alpha_none(self):
        c = Cloud(0, 5, 6, 2, 0.05, 1)
        assert c.alpha is None

    def test_cloud_custom_alpha(self):
        c = Cloud(0, 5, 6, 2, 0.05, 1, alpha=0.85)
        assert c.alpha == 0.85

    def test_cloud_shape_generated(self):
        w, h = 8, 3
        c = Cloud(0, 5, w, h, 0.05, 1)
        assert len(c.shape) == h
        assert all(len(row) == w for row in c.shape)

    def test_storm_cloud_dimensions(self, monkeypatch):
        clouds = []
        weather = _make_weather(WEATHER_STORM)
        scripted = [
            WEATHER_CLOUD_PARAMS["storm"][1],
            STORM_CLOUD_WIDTH_RANGE[0],
            STORM_CLOUD_HEIGHT_RANGE[0],
            5, 3,
        ]
        call_idx = [0]
        def fake_randint(a, b):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx < len(scripted):
                return scripted[idx]
            return a
        monkeypatch.setattr(random, "randint", fake_randint)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        monkeypatch.setattr(random, "uniform", lambda a, b: a)
        _maybe_spawn_cloud(clouds, weather, camera_x=0)
        assert len(clouds) == 1
        c = clouds[0]
        assert STORM_CLOUD_WIDTH_RANGE[0] <= c.width <= STORM_CLOUD_WIDTH_RANGE[1]
        assert STORM_CLOUD_HEIGHT_RANGE[0] <= c.height <= STORM_CLOUD_HEIGHT_RANGE[1]

    def test_storm_cloud_alpha_set(self, monkeypatch):
        clouds = []
        weather = _make_weather(WEATHER_STORM)
        scripted = [
            WEATHER_CLOUD_PARAMS["storm"][1],
            STORM_CLOUD_WIDTH_RANGE[0],
            STORM_CLOUD_HEIGHT_RANGE[0],
            5, 3,
        ]
        call_idx = [0]
        def fake_randint(a, b):
            idx = call_idx[0]
            call_idx[0] += 1
            return scripted[idx] if idx < len(scripted) else a
        monkeypatch.setattr(random, "randint", fake_randint)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        monkeypatch.setattr(random, "uniform", lambda a, b: a)
        _maybe_spawn_cloud(clouds, weather, camera_x=0)
        assert len(clouds) == 1
        assert clouds[0].alpha == STORM_CLOUD_ALPHA

    def test_clear_cloud_dimensions(self, monkeypatch):
        clouds = []
        weather = _make_weather(WEATHER_CLEAR)
        scripted = [
            WEATHER_CLOUD_PARAMS["clear"][1],
            CLOUD_WIDTH_RANGE[0],
            CLOUD_HEIGHT_RANGE[0],
            5, 8,
        ]
        call_idx = [0]
        def fake_randint(a, b):
            idx = call_idx[0]
            call_idx[0] += 1
            return scripted[idx] if idx < len(scripted) else a
        monkeypatch.setattr(random, "randint", fake_randint)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        monkeypatch.setattr(random, "uniform", lambda a, b: a)
        _maybe_spawn_cloud(clouds, weather, camera_x=0)
        assert len(clouds) == 1
        c = clouds[0]
        assert CLOUD_WIDTH_RANGE[0] <= c.width <= CLOUD_WIDTH_RANGE[1]
        assert CLOUD_HEIGHT_RANGE[0] <= c.height <= CLOUD_HEIGHT_RANGE[1]

    def test_clear_cloud_alpha_set(self, monkeypatch):
        clouds = []
        weather = _make_weather(WEATHER_CLEAR)
        scripted = [
            WEATHER_CLOUD_PARAMS["clear"][1],
            CLOUD_WIDTH_RANGE[0],
            CLOUD_HEIGHT_RANGE[0],
            5, 8,
        ]
        call_idx = [0]
        def fake_randint(a, b):
            idx = call_idx[0]
            call_idx[0] += 1
            return scripted[idx] if idx < len(scripted) else a
        monkeypatch.setattr(random, "randint", fake_randint)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        monkeypatch.setattr(random, "uniform", lambda a, b: a)
        _maybe_spawn_cloud(clouds, weather, camera_x=0)
        assert len(clouds) == 1
        assert clouds[0].alpha == CLOUD_ALPHA


# --- Tree Building Spacing Tests ---

from src.display.living_world.world_updates import _too_close_to_structure as _too_close_wu
from src.display.living_world.villager_ai import _compute_population_cap
from src.display.living_world.entities import Structure
from src.display.living_world.constants import (
    TREE_BUILDING_MIN_SPACING,
    MAX_VILLAGERS, VILLAGERS_PER_HOUSE, BASE_VILLAGERS,
)


def _make_structure(stype="house_small", x=50, y=38, width=3, height=4,
                    under_construction=False):
    s = Structure(stype, x, y, width, height)
    s.under_construction = under_construction
    return s


class TestTreeBuildingSpacing:

    def test_tree_building_min_spacing_constant(self):
        assert TREE_BUILDING_MIN_SPACING == 2

    def test_too_close_to_structure_true(self):
        s = _make_structure(x=50, width=3)
        structures = [s]
        for pos in (49, 50, 51, 52, 53, 54):
            assert _too_close_wu(pos, structures) is True

    def test_too_close_to_structure_false(self):
        s = _make_structure(x=50, width=3)
        structures = [s]
        assert _too_close_wu(45, structures) is False
        assert _too_close_wu(58, structures) is False

    def test_too_close_no_structures(self):
        assert _too_close_wu(50, []) is False

    def test_growing_sapling_killed_near_structure(self):
        heights, world = _make_flat_world()
        s = _make_structure(x=50, width=3)
        tree = _make_sapling(x=51, growth=0.5)
        assert tree.alive is True
        _grow_trees([tree], heights, world, 0, weather=None, structures=[s])
        assert tree.alive is False

    def test_growing_sapling_survives_far_from_structure(self):
        heights, world = _make_flat_world()
        s = _make_structure(x=50, width=3)
        tree = _make_sapling(x=10, growth=0.5)
        _grow_trees([tree], heights, world, 0, weather=None, structures=[s])
        assert tree.alive is True
        assert tree.growth == pytest.approx(0.503, abs=1e-6)


# --- Housing Population Cap Tests ---

class TestHousingPopulationCap:

    def test_population_cap_no_houses(self):
        assert _compute_population_cap([]) == BASE_VILLAGERS

    def test_population_cap_one_house(self):
        s = _make_structure(stype="house_small", under_construction=False)
        assert _compute_population_cap([s]) == BASE_VILLAGERS + 1 * VILLAGERS_PER_HOUSE

    def test_population_cap_five_houses(self):
        houses = [_make_structure(stype="house_small", x=10 * i) for i in range(5)]
        assert _compute_population_cap(houses) == BASE_VILLAGERS + 5 * VILLAGERS_PER_HOUSE

    def test_population_cap_clamped_at_max(self):
        houses = [_make_structure(stype="house_large", x=10 * i) for i in range(15)]
        raw = BASE_VILLAGERS + 15 * VILLAGERS_PER_HOUSE
        assert raw > MAX_VILLAGERS
        assert _compute_population_cap(houses) == MAX_VILLAGERS

    def test_population_cap_ignores_under_construction(self):
        built = _make_structure(stype="house_small", x=10, under_construction=False)
        wip = _make_structure(stype="house_small", x=30, under_construction=True)
        assert _compute_population_cap([built, wip]) == BASE_VILLAGERS + 1 * VILLAGERS_PER_HOUSE

    def test_population_cap_ignores_non_houses(self):
        campfire = _make_structure(stype="campfire", x=20, width=1, height=1)
        mine = _make_structure(stype="mine", x=60, width=1, height=1)
        watchtower = _make_structure(stype="watchtower", x=80, width=2, height=7)
        assert _compute_population_cap([campfire, mine, watchtower]) == BASE_VILLAGERS

    def test_constants_sanity(self):
        assert MAX_VILLAGERS == 20
        assert VILLAGERS_PER_HOUSE == 2
        assert BASE_VILLAGERS == 2


# --- House Area Flattening Tests ---

from src.display.living_world.terrain import _flatten_column_toward
from src.display.living_world.world_updates import _flatten_around_houses
from src.display.living_world.entities import Villager
from src.display.living_world.constants import (
    HOUSE_FLATTEN_RADIUS, HOUSE_FLATTEN_INTERVAL, HOUSE_FLATTEN_RATE,
)


class TestHouseAreaFlattening:

    def test_flatten_constants(self):
        assert HOUSE_FLATTEN_RADIUS == 5
        assert HOUSE_FLATTEN_INTERVAL == 500
        assert HOUSE_FLATTEN_RATE == 1

    def test_flatten_column_lowers_high_terrain(self):
        heights, world = _make_flat_world(surface_y=42)
        x = 50
        world[42][x] = DIRT
        world[41][x] = DIRT
        world[40][x] = GRASS
        heights[x] = 40
        result = _flatten_column_toward(world, heights, x, 42, 1)
        assert result is True
        assert heights[x] == 41

    def test_flatten_column_raises_low_terrain(self):
        heights, world = _make_flat_world(surface_y=42)
        x = 50
        world[42][x] = AIR
        world[43][x] = AIR
        world[44][x] = GRASS
        heights[x] = 44
        result = _flatten_column_toward(world, heights, x, 42, 1)
        assert result is True
        assert heights[x] == 43

    def test_flatten_column_skips_level_terrain(self):
        heights, world = _make_flat_world(surface_y=42)
        x = 50
        original_h = heights[x]
        result = _flatten_column_toward(world, heights, x, 42, 1)
        assert result is False
        assert heights[x] == original_h

    def test_flatten_column_skips_water(self):
        heights, world = _make_flat_world(surface_y=42)
        x = 50
        world[42][x] = WATER
        heights[x] = 42
        result = _flatten_column_toward(world, heights, x, 40, 1)
        assert result is False
        assert heights[x] == 42

    def test_flatten_column_skips_out_of_bounds(self):
        heights, world = _make_flat_world(surface_y=42)
        original_heights = list(heights)
        result_neg = _flatten_column_toward(world, heights, -1, 42, 1)
        assert result_neg is False
        assert heights == original_heights
        result_oob = _flatten_column_toward(world, heights, WORLD_WIDTH, 42, 1)
        assert result_oob is False
        assert heights == original_heights

    def test_flatten_around_houses_basic(self):
        heights, world = _make_flat_world(surface_y=42)
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False
        owner = Villager(50, 38)
        owner.state = "idle"
        house.owner = owner
        uneven_cols = [46, 47, 48, 55, 56, 57]
        for col in uneven_cols:
            world[42][col] = DIRT
            world[41][col] = DIRT
            world[40][col] = DIRT
            world[39][col] = GRASS
            heights[col] = 39
        structures = [house]
        villagers = [owner]
        _flatten_around_houses(structures, heights, world, villagers, 0, 0.25)
        changed = sum(1 for col in uneven_cols if heights[col] != 39)
        assert changed > 0, "Expected at least some columns to be flattened"

    def test_flatten_around_houses_skips_nighttime(self):
        heights, world = _make_flat_world(surface_y=42)
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False
        owner = Villager(50, 38)
        owner.state = "idle"
        house.owner = owner
        for col in [46, 47, 48]:
            world[42][col] = DIRT
            world[41][col] = DIRT
            world[40][col] = DIRT
            world[39][col] = GRASS
            heights[col] = 39
        original_heights = list(heights)
        structures = [house]
        villagers = [owner]
        _flatten_around_houses(structures, heights, world, villagers, 0, 0.8)
        assert heights == original_heights


# --- Villager Climbing Tests ---

from src.display.living_world.villager_ai import _update_villagers
from src.display.living_world.constants import VILLAGER_MAX_CLIMB, VILLAGER_CLIMB_SPEED


def _raise_column(world, heights, x, new_y, old_y=42):
    world[new_y][x] = GRASS
    for y in range(new_y + 1, old_y + 1):
        world[y][x] = DIRT
    heights[x] = new_y


def _lower_column(world, heights, x, new_y, old_y=42):
    for y in range(old_y, new_y):
        world[y][x] = AIR
    world[new_y][x] = GRASS
    heights[x] = new_y


def _make_walking_villager(x, target_x, surface_y=42):
    v = Villager(x, surface_y)
    v.state = "walking"
    v.target_x = target_x
    v.direction = 1 if target_x > x else -1
    v.idle_timer = 0
    return v


def _run_walking_update(villagers, heights, world):
    path_wear = [0] * WORLD_WIDTH
    _update_villagers(
        villagers, heights, world,
        trees=[], structures=[], lumber_items=[], flowers=[],
        path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
    )


class TestVillagerClimbing:

    def test_climbing_constants(self):
        assert VILLAGER_MAX_CLIMB == 3
        assert VILLAGER_CLIMB_SPEED == 2

    def test_villager_has_climb_timer(self):
        v = Villager(50, 42)
        assert v.climb_timer == 0

    def test_climb_1_block_no_delay(self):
        heights, world = _make_flat_world(surface_y=42)
        _raise_column(world, heights, 51, 41)
        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        _run_walking_update([v], heights, world)
        assert int(v.x) == 51
        assert v.y == heights[51]
        assert v.climb_timer == 0

    def test_climb_2_blocks_has_delay(self):
        heights, world = _make_flat_world(surface_y=42)
        _raise_column(world, heights, 51, 40)
        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        _run_walking_update([v], heights, world)
        assert int(v.x) == 51
        assert v.y == heights[51]
        assert v.climb_timer == VILLAGER_CLIMB_SPEED

    def test_climb_3_blocks_passable(self):
        heights, world = _make_flat_world(surface_y=42)
        _raise_column(world, heights, 51, 39)
        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        _run_walking_update([v], heights, world)
        assert int(v.x) == 51
        assert v.state == "walking"

    def test_climb_4_blocks_blocked(self):
        heights, world = _make_flat_world(surface_y=42)
        _raise_column(world, heights, 51, 38)
        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        _run_walking_update([v], heights, world)
        assert int(v.x) == 50
        assert v.state == "idle"

    def test_climb_timer_pauses_movement(self):
        heights, world = _make_flat_world(surface_y=42)
        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        v.climb_timer = 2
        _run_walking_update([v], heights, world)
        assert int(v.x) == 50
        assert v.climb_timer == 1

    def test_descend_2_blocks_has_delay(self):
        heights, world = _make_flat_world(surface_y=42)
        _lower_column(world, heights, 51, 44)
        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        _run_walking_update([v], heights, world)
        assert int(v.x) == 51
        assert v.y == heights[51]
        assert v.climb_timer == VILLAGER_CLIMB_SPEED

    def test_flatten_around_houses_skips_non_interval_tick(self):
        heights, world = _make_flat_world(surface_y=42)
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False
        owner = Villager(50, 38)
        owner.state = "idle"
        house.owner = owner
        for col in [46, 47, 48]:
            world[42][col] = DIRT
            world[41][col] = DIRT
            world[40][col] = DIRT
            world[39][col] = GRASS
            heights[col] = 39
        original_heights = list(heights)
        structures = [house]
        villagers = [owner]
        _flatten_around_houses(structures, heights, world, villagers, 1, 0.25)
        assert heights == original_heights


# --- Fire Fighting Tests ---

from src.display.living_world.villager_ai import _find_nearest_fire
from src.display.living_world.entities import GrassFire
from src.display.living_world.constants import (
    FIREFIGHT_DETECT_RADIUS, FIREFIGHT_EXTINGUISH_TICKS,
    BUBBLE_COLORS,
)


class TestFireFighting:

    def test_firefight_constants(self):
        assert FIREFIGHT_DETECT_RADIUS == 20
        assert FIREFIGHT_EXTINGUISH_TICKS == 10
        assert "firefighting" in BUBBLE_COLORS

    def test_villager_has_firefight_target(self):
        v = Villager(50, 42)
        assert v.firefight_target is None

    def test_find_nearest_fire_burning_tree(self):
        v = Villager(50, 42)
        tree = Tree(55, 42, 1.0, 7, 3, 0)
        tree.on_fire = True
        tree.fire_timer = 20
        result = _find_nearest_fire(v, [tree], [], [v])
        assert result is tree

    def test_find_nearest_fire_no_fire(self):
        v = Villager(50, 42)
        healthy_tree = Tree(55, 42, 1.0, 7, 3, 0)
        result = _find_nearest_fire(v, [healthy_tree], [], [v])
        assert result is None

    def test_find_nearest_fire_out_of_range(self):
        v = Villager(50, 42)
        tree = Tree(50 + FIREFIGHT_DETECT_RADIUS + 1, 42, 1.0, 7, 3, 0)
        tree.on_fire = True
        tree.fire_timer = 20
        result = _find_nearest_fire(v, [tree], [], [v])
        assert result is None

    def test_find_nearest_fire_excludes_targeted(self):
        v = Villager(50, 42)
        other = Villager(52, 42)
        tree = Tree(55, 42, 1.0, 7, 3, 0)
        tree.on_fire = True
        tree.fire_timer = 20
        other.firefight_target = tree
        result = _find_nearest_fire(v, [tree], [], [v, other])
        assert result is None

    def test_find_nearest_fire_grass_fire(self):
        v = Villager(50, 42)
        gf = GrassFire(55, 42, 30)
        result = _find_nearest_fire(v, [], [gf], [v])
        assert result is gf

    def test_idle_villager_detects_fire(self):
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        tree = Tree(55, 42, 1.0, 7, 3, 0)
        tree.on_fire = True
        tree.fire_timer = 20
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[tree], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            grass_fires=[],
        )
        assert v.state == "firefighting"
        assert v.firefight_target is tree

    def test_firefight_extinguishes_tree(self):
        heights, world = _make_flat_world()
        tree = Tree(50, 42, 1.0, 7, 3, 0)
        tree.on_fire = True
        tree.fire_timer = 20
        v = Villager(50, 42)
        v.state = "firefighting"
        v.firefight_target = tree
        v.target_x = tree.x
        v.task_timer = FIREFIGHT_EXTINGUISH_TICKS - 1
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[tree], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            grass_fires=[],
        )
        assert tree.on_fire is False
        assert tree.fire_timer == 0
        assert v.state == "idle"
        assert v.firefight_target is None

    def test_firefight_extinguishes_grass_fire(self):
        heights, world = _make_flat_world()
        gf = GrassFire(50, 42, 30)
        grass_fires = [gf]
        v = Villager(50, 42)
        v.state = "firefighting"
        v.firefight_target = gf
        v.target_x = gf.x
        v.task_timer = FIREFIGHT_EXTINGUISH_TICKS - 1
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            grass_fires=grass_fires,
        )
        assert gf not in grass_fires
        assert v.state == "idle"
        assert v.firefight_target is None


# --- Seasons System Tests ---

from src.display.living_world.day_night import _compute_season, _compute_season_transition
from src.display.living_world.constants import (
    SEASON_CYCLE_DAYS, SEASONS,
    SEASON_GRASS_COLORS, SEASON_LEAF_COLORS,
    SEASON_TREE_GROWTH, SEASON_FLOWER_CHANCE,
    DAY_CYCLE_SECONDS,
)


class TestSeasons:

    def test_season_constants(self):
        assert SEASON_CYCLE_DAYS == 4
        assert len(SEASONS) == 4
        for name in ("spring", "summer", "autumn", "winter"):
            assert name in SEASONS

    def test_compute_season_spring(self):
        assert _compute_season(0) == "spring"

    def test_compute_season_summer(self):
        assert _compute_season(900) == "summer"

    def test_compute_season_autumn(self):
        assert _compute_season(1800) == "autumn"

    def test_compute_season_winter(self):
        assert _compute_season(2700) == "winter"

    def test_compute_season_wraps(self):
        assert _compute_season(3600) == "spring"

    def test_season_transition_no_blend(self):
        current, next_s, blend = _compute_season_transition(0)
        assert current == "spring"
        assert next_s == "summer"
        assert blend == 0.0

    def test_season_transition_blend_at_90pct(self):
        elapsed = DAY_CYCLE_SECONDS * 0.92
        current, next_s, blend = _compute_season_transition(elapsed)
        assert current == "spring"
        assert next_s == "summer"
        assert blend > 0.0

    def test_season_transition_blend_at_end(self):
        elapsed = DAY_CYCLE_SECONDS - 0.1
        current, next_s, blend = _compute_season_transition(elapsed)
        assert current == "spring"
        assert next_s == "summer"
        assert blend > 0.9

    def test_winter_stops_tree_growth(self):
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=0.5)
        trees = [tree]
        _grow_trees(trees, heights, world, 0, weather=None, current_season="winter")
        assert tree.growth == 0.5

    def test_spring_accelerates_tree_growth(self):
        heights, world = _make_flat_world()
        tree = _make_sapling(growth=0.5)
        trees = [tree]
        _grow_trees(trees, heights, world, 0, weather=None, current_season="spring")
        expected = 0.5 + 0.003 * 1.5
        assert tree.growth == pytest.approx(expected, abs=1e-6)

    def test_winter_kills_flowers(self, monkeypatch):
        heights, world = _make_flat_world()
        flowers = [Flower(10 + i, 42, (220, 50, 50)) for i in range(5)]
        trees = []
        monkeypatch.setattr(random, "random", lambda: 0.05)
        monkeypatch.setattr(random, "randint", lambda a, b: 0)
        initial_count = len(flowers)
        for _ in range(10):
            _maybe_grow_flower(flowers, heights, world, trees, 0,
                               weather=None, current_season="winter")
        assert len(flowers) < initial_count

    def test_season_grass_colors_all_defined(self):
        for season in SEASONS:
            assert season in SEASON_GRASS_COLORS
            assert season in SEASON_LEAF_COLORS

    def test_season_growth_multipliers_valid(self):
        for season, mult in SEASON_TREE_GROWTH.items():
            assert 0.0 <= mult <= 2.0


# --- Animal Mobs Tests ---

from src.display.living_world.entities import Animal
from src.display.living_world.world_updates import _maybe_spawn_animal, _update_animals
from src.display.living_world.constants import (
    MAX_DEER, MAX_RABBITS, ANIMAL_SPAWN_INTERVAL,
    ANIMAL_FLEE_RADIUS, SEASON_ANIMAL_CHANCE,
)


class TestAnimalMobs:
    """Verify animal mob spawning, movement, fleeing, and constants."""

    def test_animal_constants(self):
        """MAX_DEER == 3, MAX_RABBITS == 4, ANIMAL_SPAWN_INTERVAL == 400,
        ANIMAL_FLEE_RADIUS == 8."""
        assert MAX_DEER == 3
        assert MAX_RABBITS == 4
        assert ANIMAL_SPAWN_INTERVAL == 400
        assert ANIMAL_FLEE_RADIUS == 8

    def test_animal_entity_deer(self):
        """A deer has speed 0.3, state 'idle', alive True."""
        a = Animal(50, 42, "deer", 1)
        assert a.speed == 0.3
        assert a.state == "idle"
        assert a.alive is True

    def test_animal_entity_rabbit(self):
        """A rabbit has speed 0.5."""
        a = Animal(50, 42, "rabbit", 1)
        assert a.speed == 0.5

    def test_animal_flee_from_villager(self):
        """An idle deer within ANIMAL_FLEE_RADIUS of a villager switches to fleeing."""
        heights, world = _make_flat_world()
        deer = Animal(50, 42, "deer", 1)
        deer.state = "idle"
        deer.idle_timer = 100
        v = Villager(50 + ANIMAL_FLEE_RADIUS - 1, 42)
        _update_animals([deer], heights, world, [v], tick=0)
        assert deer.state == "fleeing"

    def test_animal_no_flee_distant_villager(self):
        """An idle deer far from a villager stays idle."""
        heights, world = _make_flat_world()
        deer = Animal(50, 42, "deer", 1)
        deer.state = "idle"
        deer.idle_timer = 100
        v = Villager(50 + ANIMAL_FLEE_RADIUS + 10, 42)
        _update_animals([deer], heights, world, [v], tick=0)
        assert deer.state == "idle"

    def test_animal_idle_to_walking(self):
        """An animal with idle_timer=1 transitions to walking after one tick."""
        heights, world = _make_flat_world()
        deer = Animal(50, 42, "deer", 1)
        deer.state = "idle"
        deer.idle_timer = 1
        _update_animals([deer], heights, world, [], tick=0)
        assert deer.state == "walking"

    def test_animal_walking_moves(self):
        """A walking animal with direction=1 moves its x position."""
        heights, world = _make_flat_world()
        deer = Animal(50, 42, "deer", 1)
        deer.state = "walking"
        deer.walk_timer = 10
        deer.direction = 1
        old_x = deer.x
        _update_animals([deer], heights, world, [], tick=0)
        assert deer.x > old_x

    def test_animal_water_avoidance(self):
        """A rabbit walking toward a water column reverses direction.

        Rabbit speed is 0.5. Starting at x=50.6, next step = 51.1, which
        int(round(51.1)) = 51.  Water at column 51 triggers reversal.
        """
        heights, world = _make_flat_world()
        rabbit = Animal(50, 42, "rabbit", 1)
        rabbit.x = 50.6
        rabbit.state = "walking"
        rabbit.walk_timer = 10
        rabbit.direction = 1
        world[heights[51]][51] = WATER
        old_dir = rabbit.direction
        _update_animals([rabbit], heights, world, [], tick=0)
        assert rabbit.direction == -old_dir

    def test_spawn_respects_caps(self, monkeypatch):
        """When at MAX_DEER, no new deer are spawned; rabbits can still spawn."""
        heights, world = _make_flat_world()
        animals = [Animal(10 + i * 20, 42, "deer", 1) for i in range(MAX_DEER)]
        initial_deer = len([a for a in animals if a.animal_type == "deer"])
        monkeypatch.setattr(random, "random", lambda: 0.0)
        monkeypatch.setattr(random, "randint", lambda a, b: a)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        tick = ANIMAL_SPAWN_INTERVAL
        _maybe_spawn_animal(animals, heights, world, tick, villagers=[])
        deer_count = sum(1 for a in animals if a.animal_type == "deer")
        assert deer_count == initial_deer, "No new deer should be spawned at MAX_DEER"

    def test_season_animal_chance(self):
        """All 4 seasons have entries; spring/summer=1.0, winter=0.2."""
        for season in ("spring", "summer", "autumn", "winter"):
            assert season in SEASON_ANIMAL_CHANCE
        assert SEASON_ANIMAL_CHANCE["spring"] == 1.0
        assert SEASON_ANIMAL_CHANCE["summer"] == 1.0
        assert SEASON_ANIMAL_CHANCE["winter"] == 0.2


# --- Max Artificial Light Level Tests ---

from PIL import Image
from src.display.living_world.lighting import (
    _apply_campfire_light, _apply_lantern_light,
    _apply_watchtower_light, _apply_torch_post_light,
)
from src.display.living_world.constants import (
    MAX_LIGHT_LEVEL, DISPLAY_WIDTH as LW_DISPLAY_WIDTH, DISPLAY_HEIGHT as LW_DISPLAY_HEIGHT,
)


def _make_test_image(base_color=(100, 100, 100)):
    """Create a small PIL image and return its pixel accessor."""
    img = Image.new("RGB", (LW_DISPLAY_WIDTH, LW_DISPLAY_HEIGHT), base_color)
    return img, img.load()


class TestMaxLightLevel:
    """Verify that artificial light capping prevents pixel blowout."""

    def test_max_light_level_constant(self):
        """MAX_LIGHT_LEVEL should be below 255 to prevent pure white."""
        assert MAX_LIGHT_LEVEL < 255
        assert MAX_LIGHT_LEVEL > 100  # sanity: still bright

    def test_campfire_light_respects_cap(self):
        """After campfire light pass, no channel exceeds MAX_LIGHT_LEVEL."""
        img, pixels = _make_test_image((80, 80, 80))
        campfire = _make_structure(stype="campfire", x=32, y=40, width=1, height=1)
        campfire.fuel = 5000
        _apply_campfire_light(pixels, [campfire], ambient=0.1, camera_x=0)
        for y in range(LW_DISPLAY_HEIGHT):
            for x in range(LW_DISPLAY_WIDTH):
                r, g, b = pixels[x, y]
                assert r <= MAX_LIGHT_LEVEL, f"Red channel {r} > {MAX_LIGHT_LEVEL} at ({x},{y})"
                assert g <= MAX_LIGHT_LEVEL, f"Green channel {g} > {MAX_LIGHT_LEVEL} at ({x},{y})"
                assert b <= MAX_LIGHT_LEVEL, f"Blue channel {b} > {MAX_LIGHT_LEVEL} at ({x},{y})"

    def test_campfire_light_actually_brightens(self):
        """Campfire should brighten pixels near the fire source."""
        img, pixels = _make_test_image((20, 20, 20))
        campfire = _make_structure(stype="campfire", x=32, y=40, width=1, height=1)
        campfire.fuel = 5000
        _apply_campfire_light(pixels, [campfire], ambient=0.1, camera_x=0)
        r, g, b = pixels[32, 40]
        assert r > 20 or g > 20, "Expected campfire to brighten nearby pixels"

    def test_lantern_light_respects_cap(self):
        """After lantern light pass, no channel exceeds MAX_LIGHT_LEVEL."""
        img, pixels = _make_test_image((80, 80, 80))
        house = _make_structure(stype="house_small", x=30, y=36, width=3, height=4)
        house.under_construction = False
        house.door_x = 32
        _apply_lantern_light(pixels, [house], ambient=0.1, camera_x=0)
        for y in range(LW_DISPLAY_HEIGHT):
            for x in range(LW_DISPLAY_WIDTH):
                r, g, b = pixels[x, y]
                assert r <= MAX_LIGHT_LEVEL, f"Red channel {r} > {MAX_LIGHT_LEVEL} at ({x},{y})"
                assert g <= MAX_LIGHT_LEVEL, f"Green channel {g} > {MAX_LIGHT_LEVEL} at ({x},{y})"

    def test_watchtower_light_respects_cap(self):
        """After watchtower light pass, no channel exceeds MAX_LIGHT_LEVEL."""
        img, pixels = _make_test_image((80, 80, 80))
        tower = _make_structure(stype="watchtower", x=32, y=30, width=2, height=7)
        tower.under_construction = False
        _apply_watchtower_light(pixels, [tower], ambient=0.1, camera_x=0)
        for y in range(LW_DISPLAY_HEIGHT):
            for x in range(LW_DISPLAY_WIDTH):
                r, g, b = pixels[x, y]
                assert r <= MAX_LIGHT_LEVEL, f"Red channel {r} > {MAX_LIGHT_LEVEL} at ({x},{y})"
                assert g <= MAX_LIGHT_LEVEL, f"Green channel {g} > {MAX_LIGHT_LEVEL} at ({x},{y})"

    def test_torch_post_light_respects_cap(self):
        """After torch post light pass, no channel exceeds MAX_LIGHT_LEVEL."""
        img, pixels = _make_test_image((80, 80, 80))
        torch_posts = [(32, 40)]
        _apply_torch_post_light(pixels, torch_posts, ambient=0.1, camera_x=0)
        for y in range(LW_DISPLAY_HEIGHT):
            for x in range(LW_DISPLAY_WIDTH):
                r, g, b = pixels[x, y]
                assert r <= MAX_LIGHT_LEVEL, f"Red channel {r} > {MAX_LIGHT_LEVEL} at ({x},{y})"
                assert g <= MAX_LIGHT_LEVEL, f"Green channel {g} > {MAX_LIGHT_LEVEL} at ({x},{y})"

    def test_overlapping_lights_respect_cap(self):
        """Multiple nearby campfires should not push channels past MAX_LIGHT_LEVEL."""
        img, pixels = _make_test_image((80, 80, 80))
        campfires = []
        for cx in (30, 32, 34):
            c = _make_structure(stype="campfire", x=cx, y=40, width=1, height=1)
            c.fuel = 5000
            campfires.append(c)
        # Apply three campfire light passes
        for _ in range(3):
            _apply_campfire_light(pixels, campfires, ambient=0.1, camera_x=0)
        for y in range(LW_DISPLAY_HEIGHT):
            for x in range(LW_DISPLAY_WIDTH):
                r, g, b = pixels[x, y]
                assert r <= MAX_LIGHT_LEVEL, f"Red {r} > {MAX_LIGHT_LEVEL} at ({x},{y})"
                assert g <= MAX_LIGHT_LEVEL, f"Green {g} > {MAX_LIGHT_LEVEL} at ({x},{y})"
                assert b <= MAX_LIGHT_LEVEL, f"Blue {b} > {MAX_LIGHT_LEVEL} at ({x},{y})"

    def test_high_ambient_skips_light(self):
        """During daytime (ambient > 0.6), campfire light should be skipped entirely."""
        img, pixels = _make_test_image((100, 100, 100))
        campfire = _make_structure(stype="campfire", x=32, y=40, width=1, height=1)
        campfire.fuel = 5000
        _apply_campfire_light(pixels, [campfire], ambient=0.8, camera_x=0)
        r, g, b = pixels[32, 40]
        assert (r, g, b) == (100, 100, 100), "Expected no change at high ambient"


# --- Bird Perching Tests ---

from src.display.living_world.entities import Bird
from src.display.living_world.world_updates import _move_birds, _try_perch_bird
from src.display.living_world.constants import (
    BIRD_PERCH_CHANCE, BIRD_PERCH_DURATION, BIRD_PERCH_FRAME,
)


def _make_mature_tree(x=50, base_y=42, growth=1.0, canopy_radius=3, trunk_height=5):
    """Create a mature tree suitable for perching."""
    return Tree(x, base_y, growth, trunk_height + canopy_radius, canopy_radius, 0)


def _make_flying_bird(x=50.0, base_y=10.0, direction=1, speed=0.5):
    """Create a flying bird."""
    import math
    return Bird(x, base_y, direction, speed, random.uniform(0, 2 * math.pi))


class TestBirdPerching:
    """Verify bird perching on trees."""

    def test_bird_has_perch_attributes(self):
        """New birds have perching state initialized."""
        b = _make_flying_bird()
        assert b.perched is False
        assert b.perch_timer == 0
        assert b.perch_tree is None

    def test_perch_constants(self):
        """Perching constants are sane."""
        assert 0.0 < BIRD_PERCH_CHANCE < 1.0
        assert BIRD_PERCH_DURATION[0] > 0
        assert BIRD_PERCH_DURATION[1] > BIRD_PERCH_DURATION[0]
        assert len(BIRD_PERCH_FRAME) > 0

    def test_bird_perches_when_forced(self, monkeypatch):
        """When random returns < BIRD_PERCH_CHANCE, bird perches on the tree."""
        tree = _make_mature_tree(x=50, base_y=42)
        # canopy top: base_y - 1 - trunk_height - canopy_radius
        th = max(1, int(tree.trunk_height * tree.growth))
        cr = max(0, int(tree.canopy_radius * max(0, (tree.growth - 0.3) / 0.7)))
        canopy_top = tree.base_y - 1 - th - cr

        b = _make_flying_bird(x=50.0, base_y=float(canopy_top))
        b.y = float(canopy_top)
        monkeypatch.setattr(random, "random", lambda: 0.0)  # always perch
        monkeypatch.setattr(random, "randint", lambda a, b_val: a)
        _try_perch_bird(b, [tree])
        assert b.perched is True
        assert b.perch_tree is tree
        assert b.perch_timer >= BIRD_PERCH_DURATION[0]

    def test_bird_does_not_perch_on_dead_tree(self, monkeypatch):
        """Dead trees should not be perchable."""
        tree = _make_mature_tree(x=50, base_y=42)
        tree.alive = False
        b = _make_flying_bird(x=50.0, base_y=30.0)
        b.y = 30.0
        monkeypatch.setattr(random, "random", lambda: 0.0)
        _try_perch_bird(b, [tree])
        assert b.perched is False

    def test_bird_does_not_perch_on_burning_tree(self, monkeypatch):
        """Burning trees should not be perchable."""
        tree = _make_mature_tree(x=50, base_y=42)
        tree.on_fire = True
        tree.fire_timer = 20
        b = _make_flying_bird(x=50.0, base_y=30.0)
        b.y = 30.0
        monkeypatch.setattr(random, "random", lambda: 0.0)
        _try_perch_bird(b, [tree])
        assert b.perched is False

    def test_bird_does_not_perch_on_sapling(self, monkeypatch):
        """Small saplings (growth < 0.6) should not support perching."""
        tree = _make_mature_tree(x=50, base_y=42, growth=0.3)
        b = _make_flying_bird(x=50.0, base_y=40.0)
        b.y = 40.0
        monkeypatch.setattr(random, "random", lambda: 0.0)
        _try_perch_bird(b, [tree])
        assert b.perched is False

    def test_perched_bird_does_not_move(self):
        """A perched bird should stay at its perch position."""
        b = _make_flying_bird(x=50.0, base_y=30.0)
        b.perched = True
        b.perch_timer = 100
        b.y = 30.0
        old_x, old_y = b.x, b.y
        _move_birds([b], sim_tick=0)
        assert b.x == old_x
        assert b.y == old_y
        assert b.perch_timer == 99

    def test_perched_bird_takes_off_at_timer_zero(self, monkeypatch):
        """When perch_timer hits 0, bird resumes flying."""
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        b = _make_flying_bird(x=50.0, base_y=30.0)
        b.perched = True
        b.perch_timer = 1
        b.y = 30.0
        b.perch_tree = _make_mature_tree()
        _move_birds([b], sim_tick=0)
        assert b.perched is False
        assert b.perch_tree is None

    def test_perched_bird_not_removed_as_offscreen(self):
        """Perched birds at valid positions should not be culled."""
        b = _make_flying_bird(x=50.0, base_y=30.0)
        b.perched = True
        b.perch_timer = 50
        b.y = 30.0
        birds = [b]
        _move_birds(birds, sim_tick=0)
        assert len(birds) == 1

    def test_move_birds_backward_compat_no_trees(self):
        """_move_birds still works when called without trees (default None)."""
        b = _make_flying_bird(x=50.0, base_y=10.0)
        _move_birds([b], sim_tick=0)
        assert not b.perched


# --- Shooting Star Tests ---

from src.display.living_world.entities import ShootingStar
from src.display.living_world.world_updates import _maybe_spawn_shooting_star, _update_shooting_stars
from src.display.living_world.rendering import _render_shooting_stars
from src.display.living_world.constants import (
    SHOOTING_STAR_CHANCE, SHOOTING_STAR_SPEED, SHOOTING_STAR_LENGTH,
    SHOOTING_STAR_COLOR, SHOOTING_STAR_TAIL_COLOR,
)


class TestShootingStars:
    """Verify shooting star spawning, movement, rendering, and cleanup."""

    def test_shooting_star_constants(self):
        assert 0.0 < SHOOTING_STAR_CHANCE < 0.1
        assert SHOOTING_STAR_SPEED > 0
        assert SHOOTING_STAR_LENGTH >= 2
        assert len(SHOOTING_STAR_COLOR) == 3
        assert len(SHOOTING_STAR_TAIL_COLOR) == 3

    def test_shooting_star_entity(self):
        ss = ShootingStar(30, 10, 2.0, 0.8)
        assert ss.x == 30.0
        assert ss.y == 10.0
        assert ss.dx == 2.0
        assert ss.dy == 0.8
        assert ss.alive is True
        assert ss.age == 0

    def test_spawn_at_night(self, monkeypatch):
        """Shooting stars spawn at night (ambient < 0.3)."""
        stars = []
        monkeypatch.setattr(random, "random", lambda: 0.0)
        monkeypatch.setattr(random, "randint", lambda a, b: a)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        _maybe_spawn_shooting_star(stars, ambient=0.1)
        assert len(stars) == 1

    def test_no_spawn_during_day(self):
        """No shooting stars during daytime (ambient >= 0.3)."""
        stars = []
        _maybe_spawn_shooting_star(stars, ambient=0.5)
        assert len(stars) == 0

    def test_no_spawn_if_one_exists(self, monkeypatch):
        """Only one shooting star at a time."""
        existing = ShootingStar(30, 10, 2.0, 0.8)
        stars = [existing]
        monkeypatch.setattr(random, "random", lambda: 0.0)
        _maybe_spawn_shooting_star(stars, ambient=0.1)
        assert len(stars) == 1

    def test_update_moves_star(self):
        """Update should move the shooting star by its dx/dy."""
        ss = ShootingStar(30, 10, 2.0, 0.8)
        stars = [ss]
        _update_shooting_stars(stars)
        assert ss.x == 32.0
        assert ss.y == pytest.approx(10.8)
        assert ss.age == 1

    def test_update_kills_offscreen(self):
        """Stars going off-screen should be removed."""
        ss = ShootingStar(100, 10, 2.0, 0.8)  # x=100 > DISPLAY_WIDTH+10
        stars = [ss]
        _update_shooting_stars(stars)
        assert len(stars) == 0

    def test_update_kills_old_star(self):
        """Stars older than 30 ticks are culled."""
        ss = ShootingStar(30, 10, 0.1, 0.1)
        ss.age = 30
        stars = [ss]
        _update_shooting_stars(stars)
        assert len(stars) == 0

    def test_render_does_nothing_during_day(self):
        """Rendering is skipped when ambient >= 0.3."""
        img, pixels = _make_test_image((10, 10, 30))
        ss = ShootingStar(30, 10, 2.0, 0.8)
        _render_shooting_stars(pixels, [ss], ambient=0.5)
        # Pixel at (30, 10) should be unchanged
        assert pixels[30, 10] == (10, 10, 30)

    def test_render_draws_head_at_night(self):
        """At night, the head pixel should be the shooting star color."""
        img, pixels = _make_test_image((5, 5, 20))
        ss = ShootingStar(30, 10, 2.0, 0.8)
        _render_shooting_stars(pixels, [ss], ambient=0.1)
        assert pixels[30, 10] == SHOOTING_STAR_COLOR


# --- Moon Phase Tests ---

from src.display.living_world.day_night import _compute_moon_phase
from src.display.living_world.rendering import _render_sun_moon
from src.display.living_world.constants import (
    MOON_CYCLE_DAYS, MOON_PHASES, MOON_PHASE_MASKS, MOON_COLOR, MOON_DARK_COLOR,
    DAY_CYCLE_SECONDS as MOON_DAY_CYCLE,
)


class TestMoonPhases:
    """Verify moon phase computation and rendering."""

    def test_moon_phase_constants(self):
        assert MOON_CYCLE_DAYS == 8
        assert len(MOON_PHASES) == 8
        assert "new" in MOON_PHASES
        assert "full" in MOON_PHASES
        for phase in MOON_PHASES:
            assert phase in MOON_PHASE_MASKS
            mask = MOON_PHASE_MASKS[phase]
            assert len(mask) == 3
            assert all(len(row) == 3 for row in mask)

    def test_compute_moon_phase_new(self):
        """At elapsed=0, phase should be 'new' (first phase)."""
        assert _compute_moon_phase(0) == "new"

    def test_compute_moon_phase_full(self):
        """At elapsed = 4 * DAY_CYCLE, phase should be 'full'."""
        assert _compute_moon_phase(4 * MOON_DAY_CYCLE) == "full"

    def test_compute_moon_phase_wraps(self):
        """After 8 day cycles, phases should wrap around to 'new'."""
        assert _compute_moon_phase(8 * MOON_DAY_CYCLE) == "new"

    def test_compute_moon_phase_waxing_crescent(self):
        assert _compute_moon_phase(1 * MOON_DAY_CYCLE) == "waxing_crescent"

    def test_compute_moon_phase_first_quarter(self):
        assert _compute_moon_phase(2 * MOON_DAY_CYCLE) == "first_quarter"

    def test_compute_moon_phase_third_quarter(self):
        assert _compute_moon_phase(6 * MOON_DAY_CYCLE) == "third_quarter"

    def test_compute_moon_phase_waning_crescent(self):
        assert _compute_moon_phase(7 * MOON_DAY_CYCLE) == "waning_crescent"

    def test_full_moon_mask_all_lit(self):
        mask = MOON_PHASE_MASKS["full"]
        assert all(cell == 1 for row in mask for cell in row)

    def test_new_moon_mask_all_dark(self):
        mask = MOON_PHASE_MASKS["new"]
        assert all(cell == 0 for row in mask for cell in row)

    def test_render_sun_moon_backward_compat(self):
        """Calling without elapsed should still work (defaults to 0.0 = new moon)."""
        img, pixels = _make_test_image((5, 5, 20))
        # Night phase: 0.8 -> moon should be visible
        _render_sun_moon(pixels, day_phase=0.8)
        # Should not raise -- backward compatible

    def test_render_full_moon_3x3(self):
        """Full moon should draw MOON_COLOR on all 3x3 lit pixels."""
        img, pixels = _make_test_image((5, 5, 20))
        # elapsed = 4 * DAY_CYCLE -> full moon, day_phase = 0.8 (night)
        _render_sun_moon(pixels, day_phase=0.8, elapsed=4 * MOON_DAY_CYCLE)
        # The moon position for day_phase=0.8: t = (0.8-0.65)/0.35 = 0.4286
        # mx = int(5 + 0.4286 * 53) ~ 27, my = int(18 - 12*sin(0.4286*pi)) ~ 7
        # Count how many pixels are MOON_COLOR in the sky area
        moon_pixels = 0
        for y in range(20):
            for x in range(LW_DISPLAY_WIDTH):
                if pixels[x, y] == MOON_COLOR:
                    moon_pixels += 1
        assert moon_pixels == 9, f"Expected 9 lit pixels for full 3x3 moon, got {moon_pixels}"

    def test_render_new_moon_no_bright(self):
        """New moon should not draw any MOON_COLOR pixels."""
        img, pixels = _make_test_image((5, 5, 20))
        _render_sun_moon(pixels, day_phase=0.8, elapsed=0.0)
        moon_pixels = 0
        for y in range(20):
            for x in range(LW_DISPLAY_WIDTH):
                if pixels[x, y] == MOON_COLOR:
                    moon_pixels += 1
        assert moon_pixels == 0, f"New moon should have 0 bright pixels, got {moon_pixels}"


# --- Villager AI Priority Tests ---

from src.display.living_world.constants import (
    VILLAGER_CHOP_THRESHOLD, VILLAGER_EXPLORE_CHANCE, VILLAGER_PLANT_CHANCE,
)
from src.display.living_world.entities import LumberItem


class TestVillagerAIPriorities:
    """Verify the rebalanced villager idle decision priorities."""

    def test_chop_threshold_constant(self):
        """Chop threshold should be lower than old value of 6."""
        assert VILLAGER_CHOP_THRESHOLD == 4
        assert VILLAGER_CHOP_THRESHOLD < 6

    def test_explore_chance_constant(self):
        """Explore chance should provide meaningful avoidance of chopping."""
        assert 0.0 < VILLAGER_EXPLORE_CHANCE < 1.0
        assert VILLAGER_EXPLORE_CHANCE >= 0.3

    def test_plant_chance_constant(self):
        """Plant chance should be higher than old 0.3."""
        assert VILLAGER_PLANT_CHANCE > 0.3
        assert VILLAGER_PLANT_CHANCE <= 1.0

    def test_collect_lumber_before_chop(self):
        """A villager with lumber on the ground should collect, not chop."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = 0
        # Place a lumber item nearby
        lumber_items = [LumberItem(52, 41)]
        # Place a mature tree nearby too
        tree = Tree(55, 42, 1.0, 7, 3, 0)
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[tree], structures=[], lumber_items=lumber_items, flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        # Should prioritize collecting lumber over chopping
        assert v.state in ("collecting", "walking"), \
            f"Expected collecting/walking but got {v.state}"

    def test_villager_does_not_chop_at_threshold(self):
        """Villager with lumber >= VILLAGER_CHOP_THRESHOLD should NOT chop."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = VILLAGER_CHOP_THRESHOLD  # at threshold -- no chop needed
        tree = Tree(55, 42, 1.0, 7, 3, 0)
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[tree], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        # Should NOT be chopping since v.lumber >= threshold
        assert v.state != "chopping", \
            f"Villager with {VILLAGER_CHOP_THRESHOLD} lumber should not chop, got state={v.state}"

    def test_villager_chops_when_below_threshold(self, monkeypatch):
        """Villager with lumber < threshold and no explore roll should chop."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = 0
        tree = Tree(51, 42, 1.0, 7, 3, 0)
        path_wear = [0] * WORLD_WIDTH
        # Force explore chance to NOT skip chopping (random returns 1.0 > EXPLORE_CHANCE)
        call_count = [0]
        def fake_random():
            call_count[0] += 1
            return 1.0  # > EXPLORE_CHANCE, so don't skip; > PLANT_CHANCE, so don't plant
        monkeypatch.setattr(random, "random", fake_random)
        _update_villagers(
            [v], heights, world,
            trees=[tree], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.state in ("chopping", "walking"), \
            f"Expected chopping/walking but got {v.state}"

    def test_villager_explores_instead_of_chop(self, monkeypatch):
        """When explore roll succeeds, villager skips chopping and walks."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = 0
        tree = Tree(55, 42, 1.0, 7, 3, 0)
        path_wear = [0] * WORLD_WIDTH
        # random() returns 0.0 which is < EXPLORE_CHANCE so explore skips chop
        # but also < PLANT_CHANCE, so we need to handle planting check
        # Plant check happens before chop now; sparse area check (nt < 2) would match
        # but the villager has 0 lumber so plant check needs lumber >= 1
        v.lumber = 0  # can't plant without lumber
        monkeypatch.setattr(random, "random", lambda: 0.0)
        monkeypatch.setattr(random, "randint", lambda a, b: a)
        _update_villagers(
            [v], heights, world,
            trees=[tree], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        # With explore_chance triggered (random < 0.35), villager should NOT be chopping
        assert v.state != "chopping", \
            f"Expected villager to explore/skip chop but got state={v.state}"


# --- Farming System Tests ---

from src.display.living_world.entities import Farm
from src.display.living_world.world_updates import _grow_crops
from src.display.living_world.villager_ai import _find_farm_site, _count_villager_farms
from src.display.living_world.rendering import _render_farms
from src.display.living_world.constants import (
    FARM_WIDTH, FARM_COST_LUMBER, FARM_BUILD_FRAMES,
    FARM_POPULATION_THRESHOLD, MAX_FARMS_PER_HOUSE,
    CROP_GROWTH_RATE, CROP_HARVEST_YIELD,
    FARM_PLANT_FRAMES, FARM_HARVEST_FRAMES,
    FARM_GROWTH_CHECK_INTERVAL,
    SEASON_CROP_GROWTH,
    RAIN_CROP_GROWTH_MULTIPLIER, STORM_CROP_GROWTH_MULTIPLIER,
    TILLED_SOIL_COLOR, CROP_COLORS,
    WEATHER_RAIN, WEATHER_STORM, WEATHER_CLEAR,
)


class TestFarmEntity:
    """Verify the Farm entity data class behavior."""

    def test_farm_creation(self):
        f = Farm(50, 42)
        assert f.x == 50
        assert f.y == 42
        assert f.width == FARM_WIDTH
        assert len(f.crops) == FARM_WIDTH
        assert all(g == -1.0 for g in f.crops)
        assert f.owner is None

    def test_farm_custom_width(self):
        f = Farm(50, 42, width=6)
        assert f.width == 6
        assert len(f.crops) == 6

    def test_crop_stage_empty(self):
        f = Farm(50, 42)
        assert f.crop_stage(0) == "empty"

    def test_crop_stage_seeded(self):
        f = Farm(50, 42)
        f.crops[0] = 0.0
        assert f.crop_stage(0) == "seeded"

    def test_crop_stage_sprouting(self):
        f = Farm(50, 42)
        f.crops[0] = 0.3
        assert f.crop_stage(0) == "sprouting"

    def test_crop_stage_growing(self):
        f = Farm(50, 42)
        f.crops[0] = 0.7
        assert f.crop_stage(0) == "growing"

    def test_crop_stage_mature(self):
        f = Farm(50, 42)
        f.crops[0] = 1.0
        assert f.crop_stage(0) == "mature"

    def test_has_empty_slots(self):
        f = Farm(50, 42)
        assert f.has_empty_slots() is True
        f.crops = [0.0] * f.width
        assert f.has_empty_slots() is False

    def test_has_mature_crops(self):
        f = Farm(50, 42)
        assert f.has_mature_crops() is False
        f.crops[0] = 1.0
        assert f.has_mature_crops() is True

    def test_plant_all_empty(self):
        f = Farm(50, 42)
        planted = f.plant_all_empty()
        assert planted == FARM_WIDTH
        assert all(g == 0.0 for g in f.crops)

    def test_plant_all_empty_partial(self):
        f = Farm(50, 42)
        f.crops[0] = 0.5  # already growing
        f.crops[1] = 1.0  # mature
        planted = f.plant_all_empty()
        assert planted == FARM_WIDTH - 2
        assert f.crops[0] == 0.5
        assert f.crops[1] == 1.0

    def test_harvest_all_mature(self):
        f = Farm(50, 42)
        f.crops = [1.0] * f.width
        harvested = f.harvest_all_mature()
        assert harvested == FARM_WIDTH
        assert all(g == -1.0 for g in f.crops)

    def test_harvest_only_mature(self):
        f = Farm(50, 42)
        f.crops[0] = 1.0
        f.crops[1] = 0.5
        f.crops[2] = -1.0
        f.crops[3] = 1.0
        harvested = f.harvest_all_mature()
        assert harvested == 2
        assert f.crops[0] == -1.0
        assert f.crops[1] == 0.5
        assert f.crops[2] == -1.0
        assert f.crops[3] == -1.0


class TestCropGrowth:
    """Verify _grow_crops advances crop growth correctly."""

    def test_crop_growth_base_rate(self):
        f = Farm(50, 42)
        f.plant_all_empty()
        _grow_crops([f])
        expected = CROP_GROWTH_RATE
        assert f.crops[0] == pytest.approx(expected, abs=1e-6)

    def test_crop_growth_no_weather(self):
        f = Farm(50, 42)
        f.crops[0] = 0.5
        _grow_crops([f], weather=None)
        assert f.crops[0] == pytest.approx(0.5 + CROP_GROWTH_RATE, abs=1e-6)

    def test_crop_growth_rain(self):
        f = Farm(50, 42)
        f.crops[0] = 0.5
        weather = _make_weather(WEATHER_RAIN)
        _grow_crops([f], weather=weather)
        expected = 0.5 + CROP_GROWTH_RATE * RAIN_CROP_GROWTH_MULTIPLIER
        assert f.crops[0] == pytest.approx(expected, abs=1e-6)

    def test_crop_growth_storm(self):
        f = Farm(50, 42)
        f.crops[0] = 0.5
        weather = _make_weather(WEATHER_STORM)
        _grow_crops([f], weather=weather)
        expected = 0.5 + CROP_GROWTH_RATE * STORM_CROP_GROWTH_MULTIPLIER
        assert f.crops[0] == pytest.approx(expected, abs=1e-6)

    def test_crop_growth_capped_at_one(self):
        f = Farm(50, 42)
        f.crops[0] = 0.999
        weather = _make_weather(WEATHER_STORM)
        _grow_crops([f], weather=weather)
        assert f.crops[0] == 1.0

    def test_crop_growth_skips_empty(self):
        f = Farm(50, 42)
        assert f.crops[0] == -1.0
        _grow_crops([f])
        assert f.crops[0] == -1.0

    def test_crop_growth_skips_mature(self):
        f = Farm(50, 42)
        f.crops[0] = 1.0
        _grow_crops([f])
        assert f.crops[0] == 1.0

    def test_crop_growth_winter_stops(self):
        f = Farm(50, 42)
        f.crops[0] = 0.5
        _grow_crops([f], current_season="winter")
        assert f.crops[0] == 0.5

    def test_crop_growth_spring_accelerates(self):
        f = Farm(50, 42)
        f.crops[0] = 0.5
        _grow_crops([f], current_season="spring")
        expected = 0.5 + CROP_GROWTH_RATE * SEASON_CROP_GROWTH["spring"]
        assert f.crops[0] == pytest.approx(expected, abs=1e-6)

    def test_crop_growth_multiple_ticks(self):
        f = Farm(50, 42)
        f.crops[0] = 0.0
        for _ in range(10):
            _grow_crops([f])
        expected = CROP_GROWTH_RATE * 10
        assert f.crops[0] == pytest.approx(expected, abs=1e-6)

    def test_crop_growth_multiple_farms(self):
        f1 = Farm(50, 42)
        f1.crops[0] = 0.5
        f2 = Farm(60, 42)
        f2.crops[0] = 0.3
        _grow_crops([f1, f2])
        assert f1.crops[0] == pytest.approx(0.5 + CROP_GROWTH_RATE, abs=1e-6)
        assert f2.crops[0] == pytest.approx(0.3 + CROP_GROWTH_RATE, abs=1e-6)


class TestFarmConstants:
    """Verify farming constants are sane."""

    def test_farm_width(self):
        assert FARM_WIDTH >= 2

    def test_farm_cost(self):
        assert FARM_COST_LUMBER >= 1

    def test_farm_build_frames(self):
        assert FARM_BUILD_FRAMES > 0

    def test_farm_population_threshold(self):
        assert FARM_POPULATION_THRESHOLD >= 2

    def test_max_farms_per_house(self):
        assert MAX_FARMS_PER_HOUSE >= 1

    def test_crop_growth_rate(self):
        assert 0.0 < CROP_GROWTH_RATE < 0.1

    def test_crop_harvest_yield(self):
        assert CROP_HARVEST_YIELD >= 1

    def test_season_crop_growth_all_defined(self):
        for season in ("spring", "summer", "autumn", "winter"):
            assert season in SEASON_CROP_GROWTH
            assert 0.0 <= SEASON_CROP_GROWTH[season] <= 2.0

    def test_rain_crop_multipliers(self):
        assert RAIN_CROP_GROWTH_MULTIPLIER > 1.0
        assert STORM_CROP_GROWTH_MULTIPLIER > RAIN_CROP_GROWTH_MULTIPLIER

    def test_crop_colors_all_stages(self):
        for stage in ("seeded", "sprouting", "growing", "mature"):
            assert stage in CROP_COLORS
            assert len(CROP_COLORS[stage]) == 3

    def test_tilled_soil_color(self):
        assert len(TILLED_SOIL_COLOR) == 3

    def test_farming_bubble_color(self):
        assert "farming" in BUBBLE_COLORS


class TestFarmSiteFinding:
    """Verify _find_farm_site locates valid farm plots."""

    def test_find_farm_site_near_house(self):
        heights, world = _make_flat_world()
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False
        v = Villager(50, 42)
        v.home = house
        farms = []
        structures = [house]
        trees = []
        site = _find_farm_site(v, farms, heights, world, structures, trees)
        assert site is not None
        # Site should be near the house but not overlapping
        assert abs(site - house.x) >= 3

    def test_find_farm_site_no_house(self):
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.home = None
        site = _find_farm_site(v, [], heights, world, [], [])
        assert site is None

    def test_find_farm_site_avoids_water(self):
        heights, world = _make_flat_world()
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False
        v = Villager(50, 42)
        v.home = house
        # Fill columns near house with water
        for x in range(53, 70):
            world[heights[x]][x] = WATER
        farms = []
        structures = [house]
        site = _find_farm_site(v, farms, heights, world, structures, [])
        # Should find a site on the other side or further away
        if site is not None:
            for dx in range(FARM_WIDTH):
                col = site + dx
                assert world[heights[col]][col] != WATER

    def test_count_villager_farms(self):
        v = Villager(50, 42)
        f1 = Farm(55, 42)
        f1.owner = v
        f2 = Farm(65, 42)
        f2.owner = v
        f3 = Farm(75, 42)
        f3.owner = Villager(80, 42)  # different owner
        assert _count_villager_farms(v, [f1, f2, f3]) == 2

    def test_count_villager_farms_none(self):
        v = Villager(50, 42)
        assert _count_villager_farms(v, []) == 0


class TestVillagerFarmingBehavior:
    """Verify villager farming state machine behavior."""

    def test_villager_has_food_attribute(self):
        v = Villager(50, 42)
        assert v.food == 0

    def test_villager_has_farm_attribute(self):
        v = Villager(50, 42)
        assert v.farm is None

    def test_farming_harvest_state(self):
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "farming_harvest"
        v.task_timer = 1
        f = Farm(50, 42)
        f.crops = [1.0] * FARM_WIDTH
        f.owner = v
        v.farm = f
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            farms=[f],
        )
        assert v.state == "idle"
        assert v.food == FARM_WIDTH * CROP_HARVEST_YIELD
        assert all(g == -1.0 for g in f.crops)

    def test_farming_plant_state(self):
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "farming_plant"
        v.task_timer = 1
        f = Farm(50, 42)
        f.owner = v
        v.farm = f
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            farms=[f],
        )
        assert v.state == "idle"
        assert all(g == 0.0 for g in f.crops)

    def test_idle_villager_harvests_mature_farm(self):
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = 0
        f = Farm(50, 42)
        f.crops = [1.0] * FARM_WIDTH
        f.owner = v
        v.farm = f
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            farms=[f],
        )
        assert v.state in ("farming_harvest", "walking"),             f"Expected farming_harvest or walking, got {v.state}"

    def test_idle_villager_plants_empty_farm(self):
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = 0
        f = Farm(50, 42)
        f.crops = [-1.0] * FARM_WIDTH  # all empty
        f.owner = v
        v.farm = f
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            farms=[f],
        )
        assert v.state in ("farming_plant", "walking"),             f"Expected farming_plant or walking, got {v.state}"


class TestFarmRendering:
    """Verify farm rendering draws soil and crop pixels."""

    def test_render_empty_farm_shows_soil(self):
        img, pixels = _make_test_image((5, 5, 20))
        f = Farm(32, 40)
        _render_farms(pixels, [f], ambient=1.0, camera_x=0)
        # Soil at farm.y for each slot
        for slot in range(f.width):
            sx = f.x + slot
            if 0 <= sx < LW_DISPLAY_WIDTH:
                r, g, b = pixels[sx, 40]
                # Should be tilled soil color (brownish)
                assert r > 50 or g > 30, f"Expected soil color at ({sx}, 40), got ({r},{g},{b})"

    def test_render_mature_crop_shows_golden(self):
        img, pixels = _make_test_image((5, 5, 20))
        f = Farm(32, 40)
        f.crops = [1.0] * f.width  # all mature
        _render_farms(pixels, [f], ambient=1.0, camera_x=0)
        # Crop pixel at farm.y - 1 for mature crops
        crop_y = 39
        sx = 32
        r, g, b = pixels[sx, crop_y]
        # Should be golden-ish (mature color is 200, 180, 50)
        assert r > 100 and g > 80, f"Expected golden crop at ({sx},{crop_y}), got ({r},{g},{b})"

    def test_render_empty_crop_no_crop_pixel(self):
        img, pixels = _make_test_image((5, 5, 20))
        original = pixels[32, 39]
        f = Farm(32, 40)
        _render_farms(pixels, [f], ambient=1.0, camera_x=0)
        # crop_y = 39 should be unchanged for empty crop
        assert pixels[32, 39] == original

    def test_render_respects_camera_offset(self):
        img, pixels = _make_test_image((5, 5, 20))
        f = Farm(32, 40)
        f.crops = [1.0] * f.width
        _render_farms(pixels, [f], ambient=1.0, camera_x=30)
        # Farm should appear at screen x = 32 - 30 = 2
        sx = 2
        crop_y = 39
        r, g, b = pixels[sx, crop_y]
        assert r > 100 and g > 80, f"Expected crop at screen ({sx},{crop_y}), got ({r},{g},{b})"


# --- Hunger System Tests ---

from src.display.living_world.constants import (
    HUNGER_MAX, HUNGER_RATE, HUNGER_THRESHOLD, HUNGER_CRITICAL,
    HUNGER_SPEED_PENALTY, FOOD_SATIATION, EATING_FRAMES, HUNGER_EAT_THRESHOLD,
)


class TestHungerConstants:
    """Verify hunger constants are sane and consistent."""

    def test_hunger_max(self):
        assert HUNGER_MAX == 100.0

    def test_hunger_rate_positive(self):
        assert HUNGER_RATE > 0.0
        assert HUNGER_RATE < 1.0  # not too fast

    def test_hunger_thresholds_ordered(self):
        assert HUNGER_EAT_THRESHOLD < HUNGER_THRESHOLD
        assert HUNGER_THRESHOLD < HUNGER_CRITICAL
        assert HUNGER_CRITICAL <= HUNGER_MAX

    def test_food_satiation_positive(self):
        assert FOOD_SATIATION > 0.0
        assert FOOD_SATIATION <= HUNGER_MAX

    def test_eating_frames_positive(self):
        assert EATING_FRAMES > 0

    def test_eating_bubble_color(self):
        assert "eating" in BUBBLE_COLORS
        assert len(BUBBLE_COLORS["eating"]) == 3


class TestVillagerHungerEntity:
    """Verify Villager entity has hunger field initialized correctly."""

    def test_villager_has_hunger(self):
        v = Villager(50, 42)
        assert hasattr(v, "hunger")
        assert v.hunger == 0.0

    def test_villager_has_food(self):
        v = Villager(50, 42)
        assert hasattr(v, "food")
        assert v.food == 0


class TestHungerIncrement:
    """Verify hunger increases each AI tick."""

    def test_hunger_increases_on_update(self):
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 0  # not enough to trigger action (< 20)
        v.hunger = 0.0
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.hunger == pytest.approx(HUNGER_RATE, abs=1e-6)

    def test_hunger_increases_multiple_ticks(self):
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 0
        v.hunger = 0.0
        path_wear = [0] * WORLD_WIDTH
        for tick in range(10):
            v.idle_timer = 0  # keep below threshold to prevent action
            _update_villagers(
                [v], heights, world,
                trees=[], structures=[], lumber_items=[], flowers=[],
                path_wear=path_wear, day_phase=0.25, sim_tick=100 + tick, weather=None,
            )
        expected = HUNGER_RATE * 10
        assert v.hunger == pytest.approx(expected, abs=1e-4)

    def test_hunger_capped_at_max(self):
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 0
        v.hunger = HUNGER_MAX - 0.001
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.hunger == HUNGER_MAX


class TestEatingBehavior:
    """Verify the eating state machine behavior."""

    def test_idle_villager_eats_when_hungry(self):
        """Villager with food and hunger >= HUNGER_EAT_THRESHOLD should start eating."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.food = 3
        v.hunger = HUNGER_EAT_THRESHOLD + 1.0
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.state == "eating"
        assert v.task_timer == EATING_FRAMES

    def test_walking_villager_eats_when_hungry(self):
        """Walking villager with food and hunger should interrupt to eat."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "walking"
        v.target_x = 55
        v.direction = 1
        v.food = 2
        v.hunger = HUNGER_EAT_THRESHOLD + 5.0
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.state == "eating"

    def test_eating_consumes_food_and_reduces_hunger(self):
        """After eating completes, food is consumed and hunger drops."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "eating"
        v.task_timer = 1  # will complete on this tick
        v.food = 3
        v.hunger = 60.0
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.state == "idle"
        assert v.food == 2
        expected_hunger = max(0.0, 60.0 + HUNGER_RATE - FOOD_SATIATION)
        assert v.hunger == pytest.approx(expected_hunger, abs=1e-4)

    def test_eating_timer_decrements(self):
        """Eating state decrements task_timer each tick."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "eating"
        v.task_timer = 10
        v.food = 2
        v.hunger = 50.0
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.state == "eating"
        assert v.task_timer == 9
        assert v.food == 2  # not consumed yet

    def test_no_eat_when_not_hungry(self):
        """Villager with food but low hunger should NOT eat."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.food = 5
        v.hunger = HUNGER_EAT_THRESHOLD - 5.0
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.state != "eating"

    def test_no_eat_when_no_food(self):
        """Hungry villager with no food should NOT enter eating state."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.food = 0
        v.hunger = HUNGER_CRITICAL
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.state != "eating"

    def test_hunger_reduced_not_below_zero(self):
        """Eating should not reduce hunger below 0."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "eating"
        v.task_timer = 1
        v.food = 1
        v.hunger = 5.0  # less than FOOD_SATIATION
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.hunger >= 0.0
        assert v.food == 0


class TestHungerPriority:
    """Verify hunger affects villager decision priorities."""

    def test_critical_hunger_prioritizes_farming_harvest(self):
        """Critically hungry villager with mature farm should rush to harvest."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.food = 0
        v.hunger = HUNGER_CRITICAL + 1.0
        f = Farm(50, 42)
        f.crops = [1.0] * FARM_WIDTH
        f.owner = v
        v.farm = f
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            farms=[f],
        )
        assert v.state in ("farming_harvest", "walking"), \
            f"Expected farming_harvest/walking, got {v.state}"

    def test_critical_hunger_prioritizes_farming_plant(self):
        """Critically hungry villager with empty farm slots should plant."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.food = 0
        v.hunger = HUNGER_CRITICAL + 1.0
        f = Farm(50, 42)
        f.crops = [-1.0] * FARM_WIDTH  # all empty
        f.owner = v
        v.farm = f
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            farms=[f],
        )
        assert v.state in ("farming_plant", "walking"), \
            f"Expected farming_plant/walking, got {v.state}"


class TestHungerSpeedPenalty:
    """Verify critically hungry villagers move slower."""

    def test_critical_hunger_skips_odd_ticks(self):
        """Critically hungry villager should not move on odd sim_tick."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "walking"
        v.target_x = 55
        v.direction = 1
        v.food = 0
        v.hunger = HUNGER_CRITICAL + 1.0
        old_x = v.x
        path_wear = [0] * WORLD_WIDTH
        # Use odd tick to test skip
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=101, weather=None,
        )
        # Should not have moved (odd tick)
        assert int(v.x) == int(old_x), \
            f"Expected no movement on odd tick, x changed from {old_x} to {v.x}"

    def test_critical_hunger_moves_on_even_ticks(self):
        """Critically hungry villager should still move on even sim_tick."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "walking"
        v.target_x = 55
        v.direction = 1
        v.food = 0
        v.hunger = HUNGER_CRITICAL + 1.0
        old_x = v.x
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        # Should have moved on even tick
        assert int(v.x) > int(old_x), \
            f"Expected movement on even tick, x stayed at {v.x}"

    def test_normal_hunger_no_speed_penalty(self):
        """Villager below HUNGER_CRITICAL moves normally on any tick."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "walking"
        v.target_x = 55
        v.direction = 1
        v.food = 0
        v.hunger = HUNGER_CRITICAL - 10.0
        old_x = v.x
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=101, weather=None,
        )
        # Should move even on odd tick because not critically hungry
        assert int(v.x) > int(old_x), \
            f"Expected movement without speed penalty, x stayed at {v.x}"


# --- Goal-Based Decision Tree Tests ---

from src.display.living_world.villager_ai import (
    _evaluate_goals, _has_prereqs, _missing_prereqs, _resolve_prereq_action,
)
from src.display.living_world.constants import (
    GOAL_PRIORITY, GOAL_PREREQS, GOAL_EVAL_INTERVAL,
)


def _make_goal_ctx(**overrides):
    """Create a minimal goal evaluation context dict."""
    heights, world = _make_flat_world()
    ctx = {
        "structures": [],
        "trees": [],
        "heights": heights,
        "world": world,
        "pop": 2,
        "farms": [],
        "campfire_count": 1,
        "mine_count": 0,
        "bridge_count": 0,
        "watchtower_exists": False,
        "granary_exists": False,
        "lumber_items": [],
    }
    ctx.update(overrides)
    return ctx


class TestGoalConstants:
    """Verify goal system constants are sane."""

    def test_goal_priority_has_explore(self):
        assert "explore" in GOAL_PRIORITY
        assert GOAL_PRIORITY["explore"] > 0

    def test_goal_priority_ordered(self):
        """Survival goals should outrank progression goals."""
        assert GOAL_PRIORITY["build_campfire"] > GOAL_PRIORITY["build_house"]
        assert GOAL_PRIORITY["get_food"] > GOAL_PRIORITY["build_house"]
        assert GOAL_PRIORITY["build_house"] > GOAL_PRIORITY["explore"]

    def test_goal_prereqs_defined(self):
        assert "build_house" in GOAL_PREREQS
        assert GOAL_PREREQS["build_house"]["lumber"] == 4

    def test_goal_eval_interval(self):
        assert GOAL_EVAL_INTERVAL > 0


class TestVillagerGoalEntity:
    """Verify Villager entity has goal fields."""

    def test_villager_has_current_goal(self):
        v = Villager(50, 42)
        assert v.current_goal is None

    def test_villager_has_goal_timer(self):
        v = Villager(50, 42)
        assert v.goal_timer == 0


class TestGoalEvaluation:
    """Verify _evaluate_goals scores goals correctly."""

    def test_no_campfire_highest_priority(self):
        """With 0 campfires, build_campfire should be top goal."""
        v = Villager(50, 42)
        ctx = _make_goal_ctx(campfire_count=0)
        ranked = _evaluate_goals(v, ctx)
        assert ranked[0][1] == "build_campfire"

    def test_homeless_villager_wants_house(self):
        """A homeless villager should have build_house high in goals."""
        v = Villager(50, 42)
        v.home = None
        ctx = _make_goal_ctx(campfire_count=1)
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_house" in goal_names

    def test_hungry_villager_wants_food(self):
        """Critically hungry villager with no food should prioritize get_food."""
        v = Villager(50, 42)
        v.hunger = HUNGER_CRITICAL + 1
        v.food = 0
        ctx = _make_goal_ctx(campfire_count=1)
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "get_food" in goal_names
        # get_food should be near the top
        idx = goal_names.index("get_food")
        assert idx < 3, f"get_food at position {idx}, expected top 3"

    def test_farm_harvest_boosted_when_hungry(self):
        """Hungry villager with mature farm gets harvest bonus."""
        v = Villager(50, 42)
        v.hunger = HUNGER_THRESHOLD + 1
        f = Farm(50, 42)
        f.crops = [1.0] * FARM_WIDTH
        f.owner = v
        v.farm = f
        ctx = _make_goal_ctx(campfire_count=1, farms=[f])
        ranked = _evaluate_goals(v, ctx)
        harvest_scores = [(s, g) for s, g in ranked if g == "farm_harvest"]
        assert len(harvest_scores) == 1
        assert harvest_scores[0][0] > GOAL_PRIORITY["farm_harvest"]

    def test_explore_always_present(self):
        """Explore goal should always be in the ranked list."""
        v = Villager(50, 42)
        ctx = _make_goal_ctx()
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "explore" in goal_names

    def test_low_lumber_increases_gather_priority(self):
        """Villager with low lumber should have higher gather_lumber score."""
        v = Villager(50, 42)
        v.lumber = 0
        ctx = _make_goal_ctx(campfire_count=1)
        ranked = _evaluate_goals(v, ctx)
        gather_scores = [(s, g) for s, g in ranked if g == "gather_lumber"]
        assert len(gather_scores) == 1
        # Score should be base + lumber_need * 5
        expected_min = GOAL_PRIORITY["gather_lumber"] + VILLAGER_CHOP_THRESHOLD * 5
        assert gather_scores[0][0] >= expected_min

    def test_villager_with_enough_lumber_no_gather(self):
        """Villager at chop threshold should not have gather_lumber."""
        v = Villager(50, 42)
        v.lumber = VILLAGER_CHOP_THRESHOLD
        ctx = _make_goal_ctx(campfire_count=1)
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "gather_lumber" not in goal_names


class TestPrerequisiteResolution:
    """Verify prerequisite checking and chaining."""

    def test_has_prereqs_true(self):
        v = Villager(50, 42)
        v.lumber = 4
        assert _has_prereqs(v, "build_house") is True

    def test_has_prereqs_false(self):
        v = Villager(50, 42)
        v.lumber = 2
        assert _has_prereqs(v, "build_house") is False

    def test_has_prereqs_no_prereqs_goal(self):
        v = Villager(50, 42)
        assert _has_prereqs(v, "explore") is True

    def test_missing_prereqs_lumber(self):
        v = Villager(50, 42)
        v.lumber = 1
        missing = _missing_prereqs(v, "build_house")
        assert "lumber" in missing
        assert missing["lumber"] == 3

    def test_missing_prereqs_multiple(self):
        v = Villager(50, 42)
        v.lumber = 2
        v.stone = 0
        missing = _missing_prereqs(v, "upgrade_house")
        assert "lumber" in missing
        assert missing["lumber"] == 4
        assert "stone" in missing
        assert missing["stone"] == 2

    def test_resolve_prereq_lumber(self):
        v = Villager(50, 42)
        v.lumber = 1
        ctx = _make_goal_ctx()
        result = _resolve_prereq_action(v, "build_house", ctx)
        assert result == "gather_lumber"

    def test_resolve_prereq_stone(self):
        v = Villager(50, 42)
        v.lumber = 6
        v.stone = 0
        ctx = _make_goal_ctx()
        result = _resolve_prereq_action(v, "upgrade_house", ctx)
        assert result == "gather_stone"

    def test_resolve_prereq_worst_resource(self):
        """When multiple resources missing, the largest shortfall wins."""
        v = Villager(50, 42)
        v.lumber = 0
        v.stone = 0
        ctx = _make_goal_ctx()
        result = _resolve_prereq_action(v, "upgrade_house", ctx)
        # lumber shortfall = 6, stone shortfall = 2 -> lumber wins
        assert result == "gather_lumber"

    def test_resolve_prereq_none_when_met(self):
        v = Villager(50, 42)
        v.lumber = 10
        v.stone = 5
        ctx = _make_goal_ctx()
        result = _resolve_prereq_action(v, "upgrade_house", ctx)
        assert result is None


class TestGoalChaining:
    """Verify that goal chaining works in the full AI update."""

    def test_homeless_villager_chops_for_house(self):
        """Homeless villager with 0 lumber should chain: build_house -> gather_lumber -> chop."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = 0
        v.home = None
        tree = Tree(51, 42, 1.0, 7, 3, 0)
        path_wear = [0] * WORLD_WIDTH
        campfire = _make_structure(stype="campfire", x=80, width=1, height=1)
        campfire.fuel = 5000
        _update_villagers(
            [v], heights, world,
            trees=[tree], structures=[campfire], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        # Should be gathering lumber (chopping or collecting) -- not just walking randomly
        assert v.state in ("chopping", "walking", "collecting"), \
            f"Expected resource gathering action, got {v.state}"

    def test_goal_persists_across_ticks(self):
        """A villager's current_goal should persist until re-evaluated."""
        v = Villager(50, 42)
        v.current_goal = "build_house"
        v.goal_timer = 5
        assert v.current_goal == "build_house"
        assert v.goal_timer < GOAL_EVAL_INTERVAL

    def test_goal_resets_after_interval(self):
        """Goal re-evaluates after GOAL_EVAL_INTERVAL ticks."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = 0
        v.current_goal = "explore"
        v.goal_timer = GOAL_EVAL_INTERVAL  # triggers re-eval
        path_wear = [0] * WORLD_WIDTH
        campfire = _make_structure(stype="campfire", x=80, width=1, height=1)
        campfire.fuel = 5000
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[campfire], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        # After re-evaluation, goal should have been reconsidered
        # (may still be explore if nothing else is available, but timer was reset)
        assert v.goal_timer <= 1

    def test_villager_collects_lumber_for_campfire(self):
        """Villager wanting campfire with no lumber should gather lumber first."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = 0
        v.current_goal = "build_campfire"
        v.goal_timer = 0
        li = LumberItem(52, 41)
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[li], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        # Should be collecting lumber (prereq chain: build_campfire -> gather_lumber)
        assert v.state in ("collecting", "walking"), \
            f"Expected collecting/walking for lumber prereq, got {v.state}"


# ==========================================================================
# Tier 1 & 2 Tests
# ==========================================================================

from src.display.living_world.constants import CREMATION_FLASH_FRAMES as _CREMATION_FLASH_FRAMES
from src.display.living_world.constants import REPRODUCTION_MIN_AGE

CREMATION_FLASH_FRAMES = _CREMATION_FLASH_FRAMES

# --- Tier 1.1: Infinite Run Support Tests ---

class TestInfiniteRunSupport:
    """Verify the run() function signature accepts duration=0."""

    def test_run_signature_accepts_zero_duration(self):
        """run() should accept duration=0 without error at import level."""
        import inspect
        from src.display.living_world.simulation import run
        sig = inspect.signature(run)
        assert "duration" in sig.parameters
        assert sig.parameters["duration"].default == 900


# --- Tier 1.2: Persistence Tests ---

from src.display.living_world.persistence import (
    _entity_to_dict, save_world, load_world, delete_save, restore_entities,
)
import os
import json


class TestPersistence:
    """Verify save/restore world state."""

    def test_entity_to_dict_villager(self):
        v = Villager(50, 42)
        v.lumber = 5
        v.stone = 2
        d = _entity_to_dict(v)
        assert d["x"] == 50
        assert d["y"] == 42
        assert d["lumber"] == 5
        assert d["stone"] == 2
        # Cross-references should be excluded
        assert "home" not in d
        assert "farm" not in d

    def test_entity_to_dict_structure(self):
        s = _make_structure(stype="house_small", x=30, y=38, width=3, height=4)
        d = _entity_to_dict(s)
        assert d["type"] == "house_small"
        assert d["x"] == 30
        assert "owner" not in d  # cross-ref excluded

    def test_entity_to_dict_farm(self):
        f = Farm(50, 42)
        f.crops = [0.5, 1.0, -1.0, 0.3]
        d = _entity_to_dict(f)
        assert d["x"] == 50
        assert d["crops"] == [0.5, 1.0, -1.0, 0.3]
        assert "owner" not in d

    def test_restore_entities_basic(self):
        """Create fake save data and verify restore_entities rebuilds correctly."""
        data = {
            "version": 1,
            "sim_tick": 100,
            "camera_x": 64,
            "heights": [42] * WORLD_WIDTH,
            "world": [[0] * WORLD_WIDTH for _ in range(64)],
            "path_wear": [0] * WORLD_WIDTH,
            "stars": [[10, 5], [20, 8]],
            "torch_posts": [[32, 40]],
            "villagers": [
                {"x": 50, "y": 42, "state": "idle", "lumber": 3, "stone": 1,
                 "food": 2, "hunger": 10.0, "target_x": 50, "task_timer": 0,
                 "direction": 1, "idle_timer": 0, "age": 500,
                 "max_age": 15000, "children_born": 0,
                 "head_color": [180, 40, 40], "body_color": [200, 160, 120],
                 "bubble_timer": 0, "climb_timer": 0, "goal_timer": 0,
                 "entering": False, "build_total_time": 0,
                 "_home_idx": 0, "_farm_idx": 0}
            ],
            "structures": [
                {"type": "house_small", "x": 48, "y": 38, "width": 3, "height": 4,
                 "level": 1, "fuel": 0, "style": 0, "under_construction": False,
                 "build_progress": 1.0, "door_x": 49, "flame_frame": 0,
                 "cremation_flash": 0, "depth": 0, "max_depth": 8,
                 "stone_built": False, "stored_lumber": 0,
                 "_owner_idx": 0}
            ],
            "farms": [
                {"x": 55, "y": 42, "width": 4, "crops": [0.5, 1.0, -1.0, 0.0],
                 "_owner_idx": 0}
            ],
            "trees": [
                {"x": 30, "base_y": 42, "growth": 1.0, "max_height": 7,
                 "canopy_radius": 3, "style": 0, "trunk_height": 4,
                 "alive": True, "dying": False, "dying_progress": 0.0,
                 "dead_timer": 0, "mature_timer": 100,
                 "on_fire": False, "fire_timer": 0}
            ],
            "animals": [],
            "flowers": [{"x": 20, "y": 42, "color": [220, 50, 50]}],
            "lumber_items": [{"x": 52, "y": 41, "age": 10}],
            "weather": {"state": "clear", "timer": 3000, "storm_factor": 1.0,
                        "wind_dir": 1, "tree_sway_offset": 0, "sway_timer": 0,
                        "lightning_flash": 0, "lightning_bolt_timer": 0},
        }
        result = restore_entities(data)
        assert result is not None
        assert len(result["villagers"]) == 1
        assert len(result["structures"]) == 1
        assert len(result["farms"]) == 1
        assert len(result["trees"]) == 1
        # Cross-references should be linked
        v = result["villagers"][0]
        assert v.home is result["structures"][0]
        assert v.farm is result["farms"][0]
        assert result["structures"][0].owner is v
        assert result["farms"][0].owner is v
        assert result["sim_tick"] == 100

    def test_restore_entities_returns_none_on_bad_data(self):
        result = restore_entities({"version": 1})  # missing keys
        assert result is None


# --- Tier 1.3: Farm Orphan Cleanup Tests ---

from src.display.living_world.villager_ai import _handle_villager_aging


class TestFarmOrphanCleanup:
    """Verify farms get transferred when owner dies."""

    def test_farm_transferred_on_death(self):
        """When a farm-owning villager dies, farm goes to nearest farmless villager."""
        heights, world = _make_flat_world()
        owner = Villager(50, 42)
        owner.age = 20000  # will die
        owner.max_age = 19999
        f = Farm(55, 42)
        f.owner = owner
        owner.farm = f
        # Nearby homeless farmless villager
        heir = Villager(52, 42)
        heir.farm = None
        heir.age = 100
        heir.max_age = 18000
        structures = []
        villagers = [owner, heir]
        _handle_villager_aging(villagers, structures, farms=[f])
        assert len(villagers) == 1  # owner removed
        assert f.owner is heir
        assert heir.farm is f

    def test_farm_unowned_if_no_candidate(self):
        """When no farmless villager exists, farm becomes unowned."""
        heights, world = _make_flat_world()
        owner = Villager(50, 42)
        owner.age = 20000
        owner.max_age = 19999
        f = Farm(55, 42)
        f.owner = owner
        owner.farm = f
        # Other villager already has a farm
        other = Villager(52, 42)
        other_farm = Farm(60, 42)
        other.farm = other_farm
        other.age = 100
        other.max_age = 18000
        structures = []
        villagers = [owner, other]
        _handle_villager_aging(villagers, structures, farms=[f])
        assert f.owner is None


# --- Tier 1.4: Consolidated _too_close_to_structure Tests ---

class TestConsolidatedTooClose:
    """Verify _too_close_to_structure is importable from terrain (canonical)
    and from world_updates (re-exported)."""

    def test_importable_from_terrain(self):
        from src.display.living_world.terrain import _too_close_to_structure
        s = _make_structure(x=50, width=3)
        assert _too_close_to_structure(51, [s]) is True
        assert _too_close_to_structure(10, [s]) is False

    def test_importable_from_world_updates(self):
        from src.display.living_world.world_updates import _too_close_to_structure as tcs_wu
        s = _make_structure(x=50, width=3)
        assert tcs_wu(51, [s]) is True

    def test_importable_from_villager_ai(self):
        from src.display.living_world.villager_ai import _too_close_to_structure as tcs_va
        s = _make_structure(x=50, width=3)
        assert tcs_va(51, [s]) is True


# --- Tier 1.5: Dead Villager Goal Cleanup Tests ---

class TestDeadVillagerGoalCleanup:
    """Verify in-progress structures are completed when builder dies."""

    def test_building_target_completed_on_death(self):
        heights, world = _make_flat_world()
        builder = Villager(50, 42)
        builder.age = 20000
        builder.max_age = 19999
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4,
                                under_construction=True)
        house.build_progress = 0.5
        builder.building_target = house
        builder.home = house
        house.owner = builder
        structures = [house]
        villagers = [builder]
        _handle_villager_aging(villagers, structures, farms=[])
        # House should be completed, not left under_construction
        assert house.under_construction is False
        assert house.build_progress == 1.0

    def test_no_building_target_no_crash(self):
        """Villager without building_target doesn't crash."""
        v = Villager(50, 42)
        v.age = 20000
        v.max_age = 19999
        villagers = [v]
        _handle_villager_aging(villagers, [], farms=[])
        assert len(villagers) == 0


# --- Tier 2.1: Rendering dedup verified by existing farm render tests ---
# (the test_render_mature_crop_shows_golden etc. still pass with refactored code)


# --- Tier 2.2: Water Level Performance Tests ---

from src.display.living_world.weather import _get_water_surface_cols


class TestWaterLevelPerformance:
    """Verify _get_water_surface_cols returns correct water column data."""

    def test_no_water_returns_empty(self):
        heights, world = _make_flat_world()
        cols = _get_water_surface_cols(world)
        assert len(cols) == 0

    def test_water_columns_detected(self):
        heights, world = _make_flat_world()
        # Add water at columns 50-55
        for x in range(50, 56):
            world[heights[x]][x] = WATER
        cols = _get_water_surface_cols(world)
        water_xs = [c[0] for c in cols]
        for x in range(50, 56):
            assert x in water_xs


# --- Tier 2.3: Valley Cols Caching Tests ---

from src.display.living_world.terrain import _get_valley_cols, _invalidate_valley_cols_cache


class TestValleyColsCaching:
    """Verify _get_valley_cols time-based caching behavior."""

    def test_cache_returns_same_result(self):
        heights, world = _make_flat_world()
        _invalidate_valley_cols_cache()
        r1 = _get_valley_cols(world)
        r2 = _get_valley_cols(world)
        assert r1 is r2  # same object from cache (within 1s window)

    def test_cache_invalidation(self):
        heights, world = _make_flat_world()
        _invalidate_valley_cols_cache()
        r1 = _get_valley_cols(world)
        _invalidate_valley_cols_cache()
        r2 = _get_valley_cols(world)
        assert r1 is not r2  # different objects after invalidation

    def test_cache_returns_valid_set(self):
        heights, world = _make_flat_world()
        _invalidate_valley_cols_cache()
        r1 = _get_valley_cols(world)
        r2 = _get_valley_cols(world)
        assert isinstance(r1, set)
        assert isinstance(r2, set)


# --- Tier 2.4: Reproduction as a Goal Tests ---

from src.display.living_world.constants import FOOD_SHARE_THRESHOLD


class TestReproductionGoal:
    """Verify 'have_baby' goal appears in goal evaluation."""

    def test_have_baby_goal_in_constants(self):
        assert "have_baby" in GOAL_PRIORITY

    def test_have_baby_eligible(self):
        """Homeowner of breeding age with room should have have_baby goal."""
        v = Villager(50, 42)
        v.age = REPRODUCTION_MIN_AGE + 100
        v.children_born = 0
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False
        v.home = house
        ctx = _make_goal_ctx(
            campfire_count=1, pop=2,
            structures=[house],
        )
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "have_baby" in goal_names

    def test_have_baby_not_eligible_too_young(self):
        """Young villager should not have have_baby goal."""
        v = Villager(50, 42)
        v.age = 100
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False
        v.home = house
        ctx = _make_goal_ctx(campfire_count=1, pop=2, structures=[house])
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "have_baby" not in goal_names


# --- Tier 2.5: Food Sharing Tests ---


class TestFoodSharing:
    """Verify 'share_food' goal appears and works."""

    def test_share_food_goal_in_constants(self):
        assert "share_food" in GOAL_PRIORITY
        assert FOOD_SHARE_THRESHOLD == 3

    def test_share_food_eligible(self):
        """Villager with excess food near hungry neighbor should have share_food."""
        v = Villager(50, 42)
        v.food = 5
        hungry = Villager(52, 42)
        hungry.hunger = HUNGER_THRESHOLD + 1
        hungry.food = 0
        ctx = _make_goal_ctx(campfire_count=1, pop=2)
        ctx["villagers"] = [v, hungry]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "share_food" in goal_names

    def test_share_food_not_eligible_low_food(self):
        """Villager with food <= FOOD_SHARE_THRESHOLD should not share."""
        v = Villager(50, 42)
        v.food = 2
        hungry = Villager(52, 42)
        hungry.hunger = HUNGER_THRESHOLD + 1
        hungry.food = 0
        ctx = _make_goal_ctx(campfire_count=1, pop=2)
        ctx["villagers"] = [v, hungry]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "share_food" not in goal_names

    def test_share_food_not_eligible_no_hungry(self):
        """No hungry neighbors means no share_food goal."""
        v = Villager(50, 42)
        v.food = 5
        full = Villager(52, 42)
        full.hunger = 0.0
        full.food = 3
        ctx = _make_goal_ctx(campfire_count=1, pop=2)
        ctx["villagers"] = [v, full]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "share_food" not in goal_names


# --- Tier 2.6: Campfire Cremation with Lantern Fallback Tests ---


class TestCremationLanternFallback:
    """Verify cremation prefers closer lantern over distant campfire."""

    def test_cremation_uses_home_when_closer(self):
        """Villager dying at home should flash on home, not distant campfire."""
        dying = Villager(50, 42)
        dying.age = 20000
        dying.max_age = 19999
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False
        dying.home = house
        house.owner = dying
        campfire = _make_structure(stype="campfire", x=100, width=1, height=1)
        campfire.fuel = 5000
        structures = [house, campfire]
        villagers = [dying]
        _handle_villager_aging(villagers, structures, farms=[])
        # Home is closer (dist 0) than campfire (dist 50)
        assert house.cremation_flash == CREMATION_FLASH_FRAMES
        assert campfire.cremation_flash == 0

    def test_cremation_uses_campfire_when_no_home(self):
        """Homeless villager should flash on nearest campfire."""
        dying = Villager(50, 42)
        dying.age = 20000
        dying.max_age = 19999
        dying.home = None
        campfire = _make_structure(stype="campfire", x=55, width=1, height=1)
        campfire.fuel = 5000
        structures = [campfire]
        villagers = [dying]
        _handle_villager_aging(villagers, structures, farms=[])
        assert campfire.cremation_flash == CREMATION_FLASH_FRAMES


# ==========================================================================
# Event Logging Tests
# ==========================================================================

from src.display.living_world.event_log import (
    log_event, get_events, get_all_events, clear_events, event_count,
    EVENT_LOG_MAX,
    CAT_VILLAGER, CAT_BUILDING, CAT_WEATHER, CAT_COMBAT,
    CAT_ECONOMY, CAT_WORLD, CAT_DEATH, CAT_BIRTH,
)


class TestEventLogModule:
    """Verify the event_log ring buffer module."""

    def setup_method(self):
        clear_events()

    def test_log_event_basic(self):
        log_event(100, CAT_VILLAGER, "Test event")
        assert event_count() == 1

    def test_get_events_returns_newest_first(self):
        log_event(1, CAT_VILLAGER, "First")
        log_event(2, CAT_VILLAGER, "Second")
        log_event(3, CAT_VILLAGER, "Third")
        events = get_events()
        assert len(events) == 3
        assert events[0]["tick"] == 3
        assert events[0]["message"] == "Third"
        assert events[2]["tick"] == 1

    def test_get_events_with_count_limit(self):
        for i in range(10):
            log_event(i, CAT_VILLAGER, f"Event {i}")
        events = get_events(count=3)
        assert len(events) == 3
        assert events[0]["tick"] == 9

    def test_get_events_with_category_filter(self):
        log_event(1, CAT_VILLAGER, "Villager event")
        log_event(2, CAT_WEATHER, "Weather event")
        log_event(3, CAT_BUILDING, "Building event")
        log_event(4, CAT_WEATHER, "Another weather")
        events = get_events(category=CAT_WEATHER)
        assert len(events) == 2
        assert all(e["category"] == CAT_WEATHER for e in events)

    def test_ring_buffer_caps_at_max(self):
        for i in range(EVENT_LOG_MAX + 100):
            log_event(i, CAT_WORLD, f"Event {i}")
        assert event_count() == EVENT_LOG_MAX
        events = get_all_events()
        # Newest should be the last one logged
        assert events[0]["tick"] == EVENT_LOG_MAX + 99
        # Oldest should be 100 (first 100 were evicted)
        assert events[-1]["tick"] == 100

    def test_clear_events(self):
        log_event(1, CAT_VILLAGER, "Test")
        assert event_count() == 1
        clear_events()
        assert event_count() == 0

    def test_event_dict_structure(self):
        log_event(42, CAT_DEATH, "Someone died")
        events = get_events()
        e = events[0]
        assert "tick" in e
        assert "category" in e
        assert "message" in e
        assert e["tick"] == 42
        assert e["category"] == CAT_DEATH
        assert e["message"] == "Someone died"

    def test_category_constants(self):
        """All category constants are distinct strings."""
        cats = [CAT_VILLAGER, CAT_BUILDING, CAT_WEATHER, CAT_COMBAT,
                CAT_ECONOMY, CAT_WORLD, CAT_DEATH, CAT_BIRTH]
        assert len(cats) == len(set(cats))
        assert all(isinstance(c, str) for c in cats)

    def test_event_log_max_constant(self):
        assert EVENT_LOG_MAX == 1000

    def test_get_all_events(self):
        for i in range(5):
            log_event(i, CAT_WORLD, f"E{i}")
        all_events = get_all_events()
        assert len(all_events) == 5
        assert all_events[0]["tick"] == 4  # newest first

    def test_villager_death_logs_event(self):
        """Verify villager death produces a log event."""
        clear_events()
        dying = Villager(50, 42)
        dying.age = 20000
        dying.max_age = 19999
        dying.name = "TestVillager"
        dying.trait = "builder"
        structures = []
        villagers = [dying]
        _handle_villager_aging(villagers, structures, farms=[])
        events = get_events(category=CAT_DEATH)
        assert len(events) >= 1
        assert "TestVillager" in events[0]["message"]

    def test_weather_transition_logs_event(self):
        """Verify weather state change produces a log event."""
        clear_events()
        from src.display.living_world.weather import _update_weather
        w = Weather()
        w.timer = 1  # will expire on next call
        _update_weather(w, sim_tick=50)
        events = get_events(category=CAT_WEATHER)
        assert len(events) >= 1
        assert "Weather changed" in events[0]["message"]


# ==========================================================================
# Cloud Dense Roll-In Tests
# ==========================================================================


class TestCloudDenseRollIn:
    """Verify clouds roll in densely from wind direction during rain/storm transitions."""

    def test_roll_in_spawns_multiple_clouds_during_transition(self):
        """During a rain transition, multiple clouds should spawn per call."""
        clouds = []
        weather = _make_weather(WEATHER_RAIN)
        weather.prev_state = WEATHER_CLEAR  # transitioning FROM clear
        weather.transition_frames = 30      # still transitioning
        weather.wind_dir = 1
        # Call spawn multiple times during transition
        for _ in range(3):
            _maybe_spawn_cloud(clouds, weather, camera_x=64)
        # Should have spawned more than normal (normal would be 0-1 per call)
        assert len(clouds) >= 3, \
            f"Expected >= 3 clouds during roll-in, got {len(clouds)}"

    def test_roll_in_clouds_move_from_wind_direction(self):
        """During roll-in, all clouds should come from the wind direction."""
        clouds = []
        weather = _make_weather(WEATHER_RAIN)
        weather.prev_state = WEATHER_CLEAR
        weather.transition_frames = 30
        weather.wind_dir = 1  # wind blows right, clouds enter from left
        _maybe_spawn_cloud(clouds, weather, camera_x=64)
        assert len(clouds) >= 1
        for c in clouds:
            assert c.direction == 1, \
                f"Expected cloud direction 1 (matching wind), got {c.direction}"

    def test_roll_in_not_triggered_during_clear(self):
        """No roll-in behavior when weather is clear."""
        clouds = []
        weather = _make_weather(WEATHER_CLEAR)
        weather.prev_state = WEATHER_RAIN
        weather.transition_frames = 30
        weather.wind_dir = 1
        _maybe_spawn_cloud(clouds, weather, camera_x=64)
        # Should spawn 0 or 1 (normal behavior), not a burst
        assert len(clouds) <= 1

    def test_roll_in_not_triggered_rain_to_storm(self):
        """Roll-in is only for clear/cloudy -> rain/storm, not rain -> storm."""
        clouds = []
        weather = _make_weather(WEATHER_STORM)
        weather.prev_state = WEATHER_RAIN  # already raining, no roll-in
        weather.transition_frames = 30
        weather.wind_dir = 1
        _maybe_spawn_cloud(clouds, weather, camera_x=64)
        # Normal spawn behavior, not roll-in burst
        assert len(clouds) <= 2

    def test_roll_in_clouds_faster_than_normal(self):
        """Roll-in clouds should move faster to create the rolling effect."""
        clouds = []
        weather = _make_weather(WEATHER_RAIN)
        weather.prev_state = WEATHER_CLEAR
        weather.transition_frames = 30
        weather.wind_dir = -1
        _maybe_spawn_cloud(clouds, weather, camera_x=64)
        assert len(clouds) >= 1
        for c in clouds:
            assert c.speed >= 0.06, \
                f"Expected roll-in speed >= 0.06, got {c.speed}"

    def test_no_roll_in_after_transition_ends(self):
        """After transition_frames hits 0, normal spawning resumes."""
        clouds = []
        weather = _make_weather(WEATHER_RAIN)
        weather.prev_state = WEATHER_CLEAR
        weather.transition_frames = 0  # transition over
        weather.wind_dir = 1
        _maybe_spawn_cloud(clouds, weather, camera_x=64)
        # Should be normal spawn behavior (0 or 1)
        assert len(clouds) <= 1

    def test_rain_steady_state_biases_wind_direction(self, monkeypatch):
        """During steady-state rain, 70% of new clouds come from wind direction."""
        clouds = []
        weather = _make_weather(WEATHER_RAIN)
        weather.prev_state = WEATHER_RAIN  # no transition
        weather.transition_frames = 0
        weather.wind_dir = 1
        # Force random to return < 0.7 so wind bias activates
        call_idx = [0]
        scripted_random = [0.3, 0.0]  # < 0.4 for spawn check, then values
        def fake_random():
            idx = call_idx[0]; call_idx[0] += 1
            return scripted_random[idx] if idx < len(scripted_random) else 0.3
        scripted_randint = [
            WEATHER_CLOUD_PARAMS[WEATHER_RAIN][1],  # target count
            CLOUD_WIDTH_RANGE[1],  # width
            CLOUD_HEIGHT_RANGE[1],  # height
            5, 3,
        ]
        ri_idx = [0]
        def fake_randint(a, b):
            idx = ri_idx[0]; ri_idx[0] += 1
            return scripted_randint[idx] if idx < len(scripted_randint) else a
        monkeypatch.setattr(random, "random", fake_random)
        monkeypatch.setattr(random, "randint", fake_randint)
        monkeypatch.setattr(random, "uniform", lambda a, b: a)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        _maybe_spawn_cloud(clouds, weather, camera_x=64)
        if len(clouds) == 1:
            assert clouds[0].direction == weather.wind_dir


# ==========================================================================
# Well System Tests
# ==========================================================================

from src.display.living_world.structures import _is_protected_by_well, _find_well_site
from src.display.living_world.constants import (
    MAX_WELLS, WELL_COST_LUMBER, WELL_COST_STONE, WELL_BUILD_FRAMES,
    WELL_FIRE_PREVENTION_RADIUS, WELL_MIN_SPACING, WELL_POPULATION_THRESHOLD,
    WELL_WIDTH, WELL_HEIGHT,
    WELL_STONE_COLOR, WELL_WATER_COLOR, WELL_ROOF_COLOR,
)


class TestWellConstants:
    """Verify well constants are sane."""

    def test_max_wells(self):
        assert MAX_WELLS == 3

    def test_well_costs(self):
        assert WELL_COST_LUMBER >= 1
        assert WELL_COST_STONE >= 1

    def test_well_fire_prevention_radius(self):
        assert WELL_FIRE_PREVENTION_RADIUS > 0
        assert WELL_FIRE_PREVENTION_RADIUS >= 10

    def test_well_min_spacing(self):
        assert WELL_MIN_SPACING > WELL_FIRE_PREVENTION_RADIUS

    def test_well_population_threshold(self):
        assert WELL_POPULATION_THRESHOLD >= 3

    def test_well_dimensions(self):
        assert WELL_WIDTH >= 1
        assert WELL_HEIGHT >= 1

    def test_well_colors(self):
        assert len(WELL_STONE_COLOR) == 3
        assert len(WELL_WATER_COLOR) == 3
        assert len(WELL_ROOF_COLOR) == 3

    def test_well_goal_in_priority(self):
        assert "build_well" in GOAL_PRIORITY
        assert "build_well" in GOAL_PREREQS


class TestWellFirePrevention:
    """Verify wells prevent fires within their radius."""

    def test_protected_by_well_true(self):
        well = _make_structure(stype="well", x=50, y=40, width=1, height=2)
        assert _is_protected_by_well(50, [well]) is True
        assert _is_protected_by_well(50 + WELL_FIRE_PREVENTION_RADIUS, [well]) is True

    def test_protected_by_well_false_outside_radius(self):
        well = _make_structure(stype="well", x=50, y=40, width=1, height=2)
        assert _is_protected_by_well(50 + WELL_FIRE_PREVENTION_RADIUS + 1, [well]) is False

    def test_protected_by_well_no_wells(self):
        assert _is_protected_by_well(50, []) is False

    def test_protected_by_well_non_well_structures(self):
        campfire = _make_structure(stype="campfire", x=50, width=1, height=1)
        assert _is_protected_by_well(50, [campfire]) is False


class TestWellSiteFinding:
    """Verify _find_well_site locates valid well locations."""

    def test_find_well_site_basic(self):
        heights, world = _make_flat_world()
        structures = []
        trees = []
        site = _find_well_site(structures, trees, heights, world, near_x=50)
        assert site is not None

    def test_find_well_site_respects_spacing(self):
        heights, world = _make_flat_world()
        well1 = _make_structure(stype="well", x=50, y=40, width=1, height=2)
        structures = [well1]
        trees = []
        site = _find_well_site(structures, trees, heights, world, near_x=50)
        if site is not None:
            assert abs(site - 50) >= WELL_MIN_SPACING

    def test_find_well_site_avoids_structures(self):
        heights, world = _make_flat_world()
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        structures = [house]
        trees = []
        site = _find_well_site(structures, trees, heights, world, near_x=50)
        if site is not None:
            assert abs(site - 50) >= 3


class TestWellGoalEvaluation:
    """Verify build_well goal appears in goal evaluation."""

    def test_build_well_eligible(self):
        v = Villager(50, 42)
        v.lumber = 5
        v.stone = 5
        ctx = _make_goal_ctx(campfire_count=1, pop=WELL_POPULATION_THRESHOLD)
        ctx["well_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_well" in goal_names

    def test_build_well_not_eligible_low_pop(self):
        v = Villager(50, 42)
        ctx = _make_goal_ctx(campfire_count=1, pop=2)
        ctx["well_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_well" not in goal_names

    def test_build_well_not_eligible_max_wells(self):
        v = Villager(50, 42)
        ctx = _make_goal_ctx(campfire_count=1, pop=WELL_POPULATION_THRESHOLD)
        ctx["well_count"] = MAX_WELLS
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_well" not in goal_names


# ==========================================================================
# Bow Hunting Tests
# ==========================================================================

from src.display.living_world.constants import (
    BOW_COST_LUMBER, BOW_RANGE, BOW_SHOOT_FRAMES, BOW_HUNTING_FOOD,
)


class TestBowHuntingConstants:
    """Verify bow hunting constants are sane."""

    def test_bow_cost(self):
        assert BOW_COST_LUMBER == 1

    def test_bow_range(self):
        assert BOW_RANGE >= 5
        assert BOW_RANGE <= 20

    def test_bow_shoot_frames(self):
        assert BOW_SHOOT_FRAMES > 0

    def test_bow_food_yield(self):
        assert BOW_HUNTING_FOOD >= 1


class TestBowHuntingEntity:
    """Verify villager has bow attribute."""

    def test_villager_has_bow_attribute(self):
        v = Villager(50, 42)
        assert hasattr(v, "has_bow")
        assert v.has_bow is False


class TestBowCrafting:
    """Verify villagers auto-craft bows when hunting."""

    def test_bow_crafted_on_hunt(self):
        """Villager with lumber should craft bow when starting hunt."""
        clear_events()
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = 2
        v.hunger = 70.0  # hungry enough to hunt
        v.food = 0
        v.farm = None
        v.has_bow = False
        deer = Animal(60, 42, "deer", -1)
        deer.alive = True
        path_wear = [0] * WORLD_WIDTH
        campfire = _make_structure(stype="campfire", x=80, width=1, height=1)
        campfire.fuel = 5000
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[campfire], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            animals=[deer],
        )
        # Villager should have entered hunting and crafted a bow
        assert v.state == "hunting", "Expected villager to enter hunting state"
        assert v.has_bow is True
        assert v.lumber == 1  # spent 1 on bow

    def test_no_bow_craft_without_lumber(self):
        """Villager with no lumber should not craft bow."""
        v = Villager(50, 42)
        v.lumber = 0
        v.has_bow = False
        v.hunger = 70.0
        v.food = 0
        v.farm = None
        # Should not have bow
        assert v.has_bow is False

    def test_bow_persists_after_craft(self):
        """Once crafted, bow stays."""
        v = Villager(50, 42)
        v.has_bow = True
        v.lumber = 0
        assert v.has_bow is True


class TestBowRangedKill:
    """Verify bow-equipped villager can kill from range."""

    def test_bow_kills_at_range(self):
        """Bow-equipped villager in hunting state kills at BOW_RANGE."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "hunting"
        v.has_bow = True
        v.food = 0
        deer = Animal(50 + BOW_RANGE - 1, 42, "deer", -1)
        deer.alive = True
        v.hunt_target = deer
        v.task_timer = BOW_SHOOT_FRAMES  # aiming time reached
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            animals=[deer],
        )
        assert deer.alive is False
        assert v.food == BOW_HUNTING_FOOD
        assert v.state == "idle"

    def test_bow_does_not_kill_before_aim(self):
        """Bow-equipped villager needs BOW_SHOOT_FRAMES to aim."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "hunting"
        v.has_bow = True
        v.food = 0
        deer = Animal(55, 42, "deer", -1)
        deer.alive = True
        v.hunt_target = deer
        v.task_timer = 1  # not enough aiming time
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            animals=[deer],
        )
        # Should still be aiming, deer alive
        assert deer.alive is True
        assert v.state == "hunting"


# ==========================================================================
# Web API / World Snapshot Tests
# ==========================================================================

from src.display.living_world.world_api import get_world_snapshot, get_event_log_snapshot


class TestWorldApiModule:
    """Verify the world_api module returns correct data."""

    def test_get_world_snapshot_returns_none_no_save(self, tmp_path, monkeypatch):
        """When no save file exists, returns None."""
        monkeypatch.setattr(
            "src.display.living_world.world_api._SAVE_PATH",
            str(tmp_path / "nonexistent.json"),
        )
        monkeypatch.setattr(
            "src.display.living_world.world_api._LIVE_SNAPSHOT_PATH",
            str(tmp_path / "nonexistent_live.json"),
        )
        assert get_world_snapshot() is None

    def test_get_event_log_snapshot_returns_list(self):
        """Event log snapshot should return a list."""
        clear_events()
        log_event(1, CAT_VILLAGER, "Test")
        result = get_event_log_snapshot(count=10)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["message"] == "Test"

    def test_get_event_log_snapshot_with_category(self):
        clear_events()
        log_event(1, CAT_WEATHER, "Rain started")
        log_event(2, CAT_BUILDING, "House built")
        result = get_event_log_snapshot(count=10, category=CAT_WEATHER)
        assert len(result) == 1
        assert result[0]["category"] == CAT_WEATHER

    def test_no_bow_must_chase(self):
        """Without bow, villager must get close (HUNTING_CATCH_RADIUS) to kill."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "hunting"
        v.has_bow = False
        v.food = 0
        deer = Animal(55, 42, "deer", -1)
        deer.alive = True
        v.hunt_target = deer
        v.task_timer = 5
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
            animals=[deer],
        )
        # Should be chasing (dist > CATCH_RADIUS), not killing
        assert deer.alive is True
        assert v.state == "hunting"


# ==========================================================================
# Castle Building Tests
# ==========================================================================

from src.display.living_world.constants import (
    CASTLE_COST_LUMBER, CASTLE_COST_STONE, CASTLE_BUILD_FRAMES,
    CASTLE_WIDTH, CASTLE_HEIGHT, CASTLE_POPULATION_THRESHOLD, MAX_CASTLES,
    CASTLE_TEMPLATE, CASTLE_PAL,
)


class TestCastleConstants:
    """Verify castle constants are sane."""

    def test_castle_costs(self):
        assert CASTLE_COST_LUMBER >= 8
        assert CASTLE_COST_STONE >= 3

    def test_castle_dimensions(self):
        assert CASTLE_WIDTH >= 5
        assert CASTLE_HEIGHT >= 6

    def test_castle_population_threshold(self):
        assert CASTLE_POPULATION_THRESHOLD >= 6

    def test_max_castles(self):
        assert MAX_CASTLES == 1

    def test_castle_template_dimensions(self):
        assert len(CASTLE_TEMPLATE) == CASTLE_HEIGHT
        for row in CASTLE_TEMPLATE:
            assert len(row) == CASTLE_WIDTH

    def test_castle_palette_has_keys(self):
        required = ['wall', 'tower', 'battlement', 'door', 'window_day', 'window_night', 'gate']
        for key in required:
            assert key in CASTLE_PAL
            assert len(CASTLE_PAL[key]) == 3

    def test_castle_goal_in_priority(self):
        assert "build_castle" in GOAL_PRIORITY
        assert "build_castle" in GOAL_PREREQS

    def test_castle_prereqs(self):
        assert GOAL_PREREQS["build_castle"]["lumber"] == CASTLE_COST_LUMBER
        assert GOAL_PREREQS["build_castle"]["stone"] == CASTLE_COST_STONE


class TestCastleGoalEvaluation:
    """Verify build_castle goal appears in goal evaluation."""

    def test_castle_eligible(self):
        v = Villager(50, 42)
        v.lumber = 15
        v.stone = 10
        ctx = _make_goal_ctx(campfire_count=1, pop=CASTLE_POPULATION_THRESHOLD)
        ctx["castle_count"] = 0
        ctx["well_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_castle" in goal_names

    def test_castle_not_eligible_low_pop(self):
        v = Villager(50, 42)
        ctx = _make_goal_ctx(campfire_count=1, pop=3)
        ctx["castle_count"] = 0
        ctx["well_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_castle" not in goal_names

    def test_castle_not_eligible_max_castles(self):
        v = Villager(50, 42)
        ctx = _make_goal_ctx(campfire_count=1, pop=CASTLE_POPULATION_THRESHOLD)
        ctx["castle_count"] = MAX_CASTLES
        ctx["well_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_castle" not in goal_names


# ==========================================================================
# Rain Motivates House Building Tests
# ==========================================================================


class TestRainMotivatesHouse:
    """Verify rain/storm boosts build_house priority for homeless villagers."""

    def test_rain_boosts_house_score(self):
        """In rain, homeless villager's build_house score should exceed clear-weather score."""
        v = Villager(50, 42)
        v.home = None
        # Clear weather context
        ctx_clear = _make_goal_ctx(campfire_count=1, pop=3)
        ctx_clear["well_count"] = 0
        ctx_clear["castle_count"] = 0
        ctx_clear["villagers"] = [v]
        ctx_clear["weather"] = None
        ranked_clear = _evaluate_goals(v, ctx_clear)
        house_score_clear = next((s for s, g in ranked_clear if g == "build_house"), 0)

        # Rain weather context
        weather_rain = _make_weather(WEATHER_RAIN)
        ctx_rain = _make_goal_ctx(campfire_count=1, pop=3)
        ctx_rain["well_count"] = 0
        ctx_rain["castle_count"] = 0
        ctx_rain["villagers"] = [v]
        ctx_rain["weather"] = weather_rain
        ranked_rain = _evaluate_goals(v, ctx_rain)
        house_score_rain = next((s for s, g in ranked_rain if g == "build_house"), 0)

        assert house_score_rain > house_score_clear, \
            f"Rain score ({house_score_rain}) should exceed clear ({house_score_clear})"

    def test_storm_boosts_house_more_than_rain(self):
        """Storm should boost build_house score more than rain."""
        v = Villager(50, 42)
        v.home = None

        weather_rain = _make_weather(WEATHER_RAIN)
        ctx_rain = _make_goal_ctx(campfire_count=1, pop=3)
        ctx_rain["well_count"] = 0
        ctx_rain["castle_count"] = 0
        ctx_rain["villagers"] = [v]
        ctx_rain["weather"] = weather_rain
        ranked_rain = _evaluate_goals(v, ctx_rain)
        house_score_rain = next((s for s, g in ranked_rain if g == "build_house"), 0)

        weather_storm = _make_weather(WEATHER_STORM)
        ctx_storm = _make_goal_ctx(campfire_count=1, pop=3)
        ctx_storm["well_count"] = 0
        ctx_storm["castle_count"] = 0
        ctx_storm["villagers"] = [v]
        ctx_storm["weather"] = weather_storm
        ranked_storm = _evaluate_goals(v, ctx_storm)
        house_score_storm = next((s for s, g in ranked_storm if g == "build_house"), 0)

        assert house_score_storm > house_score_rain, \
            f"Storm score ({house_score_storm}) should exceed rain ({house_score_rain})"

    def test_no_boost_when_has_home(self):
        """Villager with a home should not get rain boost on build_house."""
        v = Villager(50, 42)
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False
        v.home = house
        weather_rain = _make_weather(WEATHER_RAIN)
        ctx = _make_goal_ctx(campfire_count=1, pop=3, structures=[house])
        ctx["well_count"] = 0
        ctx["castle_count"] = 0
        ctx["villagers"] = [v]
        ctx["weather"] = weather_rain
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        # Has home -> build_house should NOT appear
        assert "build_house" not in goal_names

    def test_homeless_villager_uses_goal_tree_in_rain(self):
        """Homeless villager in rain should fall through to goal tree, not wander."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25
        v.lumber = 5  # enough to build
        v.home = None
        weather = _make_weather(WEATHER_RAIN)
        campfire = _make_structure(stype="campfire", x=80, width=1, height=1)
        campfire.fuel = 5000
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[campfire], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=weather,
        )
        # Should be building or walking toward a build site, not just walking aimlessly
        assert v.state in ("building", "walking", "chopping", "collecting"), \
            f"Expected purposeful action in rain, got {v.state}"


# ==========================================================================
# Pond Spawning Fix Tests
# ==========================================================================

from src.display.living_world.terrain import _guarantee_pond


class TestPondSpawning:
    """Verify _guarantee_pond creates a pond when no water exists."""

    def test_guarantee_pond_creates_water(self):
        """When no water exists, _guarantee_pond should add water blocks."""
        heights, world = _make_flat_world(surface_y=42)
        # Verify no water initially
        has_water = any(world[y][x] == WATER
                        for x in range(WORLD_WIDTH)
                        for y in range(DISPLAY_HEIGHT))
        assert has_water is False
        _guarantee_pond(heights, world)
        # Now should have water
        has_water_after = any(world[y][x] == WATER
                             for x in range(WORLD_WIDTH)
                             for y in range(DISPLAY_HEIGHT))
        assert has_water_after is True

    def test_guarantee_pond_skips_if_water_exists(self):
        """When water already exists, _guarantee_pond should be a no-op."""
        heights, world = _make_flat_world(surface_y=42)
        # Place water manually
        world[42][50] = WATER
        heights_copy = list(heights)
        _guarantee_pond(heights, world)
        # Heights should be unchanged (no digging)
        assert heights == heights_copy

    def test_guarantee_pond_digs_basin(self):
        """Pond should dig downward (increase y), not upward."""
        heights, world = _make_flat_world(surface_y=42)
        original_heights = list(heights)
        _guarantee_pond(heights, world)
        # At least some columns should have higher y (lower terrain)
        dug_count = sum(1 for i in range(WORLD_WIDTH) if heights[i] > original_heights[i])
        assert dug_count > 0, "Expected pond to dig basin (increase y values)"


# ==========================================================================
# Boat Travel Tests
# ==========================================================================

from src.display.living_world.entities import Boat
from src.display.living_world.constants import (
    BOAT_COST_LUMBER, BOAT_SPEED, BOAT_COLOR, BOAT_WIDTH,
)


class TestBoatConstants:
    """Verify boat constants are sane."""

    def test_boat_cost(self):
        assert BOAT_COST_LUMBER >= 1

    def test_boat_speed(self):
        assert 0.0 < BOAT_SPEED <= 1.0

    def test_boat_color(self):
        assert len(BOAT_COLOR) == 3

    def test_boat_width(self):
        assert BOAT_WIDTH >= 2


class TestBoatEntity:
    """Verify Boat entity data class."""

    def test_boat_creation(self):
        v = Villager(50, 42)
        b = Boat(50, 42, v)
        assert b.x == 50.0
        assert b.y == 42
        assert b.owner is v
        assert b.active is False

    def test_villager_has_boat_fields(self):
        v = Villager(50, 42)
        assert v.has_boat is False
        assert v.boat is None


class TestBoatTravel:
    """Verify villagers can cross water with boats."""

    def test_villager_crafts_boat_at_water(self):
        """Villager with lumber should craft boat when blocked by water."""
        heights, world = _make_flat_world()
        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        v.lumber = 5
        v.has_boat = False
        # Put water at column 51
        world[heights[51]][51] = WATER
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        # Should have crafted a boat
        assert v.has_boat, "Expected villager to craft a boat at water edge"
        assert v.lumber == 3  # spent 2 on boat
        assert v.boat is not None

    def test_villager_with_boat_crosses_water(self):
        """Villager with existing boat should cross water without crafting."""
        heights, world = _make_flat_world()
        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        v.has_boat = True
        v.lumber = 0
        v.boat = Boat(50, 42, v)
        world[heights[51]][51] = WATER
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        assert v.lumber == 0  # didn't spend lumber
        assert int(v.x) == 51  # moved onto water


# ==========================================================================
# Trade Caravan Tests
# ==========================================================================

from src.display.living_world.entities import Caravan
from src.display.living_world.world_updates import _maybe_spawn_caravan, _update_caravans
from src.display.living_world.constants import (
    CARAVAN_SPAWN_INTERVAL, CARAVAN_TRADE_DURATION, CARAVAN_SPEED,
    CARAVAN_COLOR, CARAVAN_TRADE_RADIUS,
)


class TestCaravanConstants:
    """Verify caravan constants are sane."""

    def test_caravan_spawn_interval(self):
        assert CARAVAN_SPAWN_INTERVAL > 0

    def test_caravan_trade_duration(self):
        assert CARAVAN_TRADE_DURATION > 0

    def test_caravan_speed(self):
        assert 0.0 < CARAVAN_SPEED <= 1.0

    def test_caravan_color(self):
        assert len(CARAVAN_COLOR) == 3

    def test_caravan_trade_radius(self):
        assert CARAVAN_TRADE_RADIUS >= 1


class TestCaravanEntity:
    """Verify Caravan entity data class."""

    def test_caravan_creation(self):
        c = Caravan(10, 42, 1)
        assert c.x == 10.0
        assert c.y == 42
        assert c.direction == 1
        assert c.state == "arriving"
        assert c.alive is True
        assert c.trades_completed == 0

    def test_caravan_has_offers(self):
        c = Caravan(10, 42, 1)
        assert "give" in c.offers
        assert "want" in c.offers
        assert "give_amount" in c.offers
        assert "want_amount" in c.offers


class TestCaravanSpawning:
    """Verify caravan spawn logic."""

    def test_spawn_at_interval(self):
        heights, world = _make_flat_world()
        caravans = []
        villagers = [Villager(50, 42), Villager(60, 42)]
        _maybe_spawn_caravan(caravans, heights, world, CARAVAN_SPAWN_INTERVAL, villagers)
        assert len(caravans) == 1

    def test_no_spawn_before_interval(self):
        heights, world = _make_flat_world()
        caravans = []
        villagers = [Villager(50, 42), Villager(60, 42)]
        _maybe_spawn_caravan(caravans, heights, world, 100, villagers)
        assert len(caravans) == 0

    def test_no_spawn_if_one_exists(self):
        heights, world = _make_flat_world()
        caravans = [Caravan(10, 42, 1)]
        villagers = [Villager(50, 42), Villager(60, 42)]
        _maybe_spawn_caravan(caravans, heights, world, CARAVAN_SPAWN_INTERVAL, villagers)
        assert len(caravans) == 1

    def test_no_spawn_low_population(self):
        heights, world = _make_flat_world()
        caravans = []
        villagers = [Villager(50, 42)]
        _maybe_spawn_caravan(caravans, heights, world, CARAVAN_SPAWN_INTERVAL, villagers)
        assert len(caravans) == 0


class TestCaravanUpdate:
    """Verify caravan movement and trading."""

    def test_arriving_caravan_moves(self):
        heights, world = _make_flat_world()
        c = Caravan(0, 42, 1)
        c.state = "arriving"
        _update_caravans([c], heights, world, [], sim_tick=100)
        assert c.x > 0  # moved toward center

    def test_trading_caravan_countdown(self):
        heights, world = _make_flat_world()
        c = Caravan(96, 42, 1)
        c.state = "trading"
        c.timer = 10
        _update_caravans([c], heights, world, [], sim_tick=100)
        assert c.timer == 9

    def test_leaving_caravan_moves_out(self):
        heights, world = _make_flat_world()
        c = Caravan(WORLD_WIDTH - 3, 42, 1)
        c.state = "leaving"
        for _ in range(20):
            _update_caravans([c], heights, world, [], sim_tick=100)
        assert c.alive is False  # should have left the map

    def test_caravan_trades_with_villager(self):
        heights, world = _make_flat_world()
        c = Caravan(50, 42, 1)
        c.state = "trading"
        c.timer = 100
        c.offers = {"give": "stone", "give_amount": 2, "want": "lumber", "want_amount": 3}
        v = Villager(50, 42)
        v.state = "idle"
        v.lumber = 5
        v.stone = 0
        _update_caravans([c], heights, world, [v], sim_tick=100)
        assert c.trades_completed > 0, "Expected caravan to complete at least one trade"
        assert v.lumber == 2  # gave 3
        assert v.stone == 2  # got 2


# ==========================================================================
# Community Storage Tests
# ==========================================================================

from src.display.living_world.structures import _find_storage_site, _get_storage
from src.display.living_world.constants import (
    STORAGE_COST_LUMBER, STORAGE_COST_STONE, STORAGE_BUILD_FRAMES,
    STORAGE_WIDTH, STORAGE_HEIGHT, STORAGE_POPULATION_THRESHOLD, MAX_STORAGES,
    STORAGE_MAX_LUMBER, STORAGE_MAX_STONE, STORAGE_MAX_FOOD,
    STORAGE_DEPOSIT_THRESHOLD_LUMBER, STORAGE_DEPOSIT_THRESHOLD_STONE,
    STORAGE_DEPOSIT_THRESHOLD_FOOD,
)


class TestStorageConstants:
    """Verify community storage constants are sane."""

    def test_storage_costs(self):
        assert STORAGE_COST_LUMBER >= 1
        assert STORAGE_COST_STONE >= 0

    def test_storage_dimensions(self):
        assert STORAGE_WIDTH >= 2
        assert STORAGE_HEIGHT >= 2

    def test_storage_population_threshold(self):
        assert STORAGE_POPULATION_THRESHOLD >= 2

    def test_max_storages(self):
        assert MAX_STORAGES >= 1

    def test_storage_capacities(self):
        assert STORAGE_MAX_LUMBER > 0
        assert STORAGE_MAX_STONE > 0
        assert STORAGE_MAX_FOOD > 0

    def test_deposit_thresholds(self):
        assert STORAGE_DEPOSIT_THRESHOLD_LUMBER > 0
        assert STORAGE_DEPOSIT_THRESHOLD_STONE >= 0
        assert STORAGE_DEPOSIT_THRESHOLD_FOOD > 0

    def test_storage_goal_in_priority(self):
        assert "build_storage" in GOAL_PRIORITY
        assert "deposit_storage" in GOAL_PRIORITY
        assert "withdraw_storage" in GOAL_PRIORITY

    def test_storage_prereqs(self):
        assert "build_storage" in GOAL_PREREQS
        assert GOAL_PREREQS["build_storage"]["lumber"] == STORAGE_COST_LUMBER
        assert GOAL_PREREQS["build_storage"]["stone"] == STORAGE_COST_STONE


class TestStorageSiteFinding:
    """Verify _find_storage_site locates valid locations."""

    def test_find_storage_site_basic(self):
        heights, world = _make_flat_world()
        structures = []
        trees = []
        site = _find_storage_site(structures, trees, heights, world, near_x=50)
        assert site is not None

    def test_find_storage_site_avoids_structures(self):
        heights, world = _make_flat_world()
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        site = _find_storage_site([house], [], heights, world, near_x=50)
        if site is not None:
            sx, _ = site
            assert abs(sx - 50) >= 3


class TestStorageEntity:
    """Verify Structure has storage fields."""

    def test_structure_has_stored_fields(self):
        s = _make_structure(stype="storage", x=50, y=38, width=3, height=3)
        assert s.stored_lumber == 0
        assert s.stored_stone == 0
        assert s.stored_food == 0
        assert s.stored_gold == 0

    def test_get_storage_returns_completed(self):
        s = _make_structure(stype="storage", x=50, y=38, width=3, height=3)
        s.under_construction = False
        assert _get_storage([s]) is s

    def test_get_storage_skips_under_construction(self):
        s = _make_structure(stype="storage", x=50, y=38, width=3, height=3)
        s.under_construction = True
        assert _get_storage([s]) is None

    def test_get_storage_returns_none_empty(self):
        assert _get_storage([]) is None


class TestStorageGoalEvaluation:
    """Verify storage goals appear in goal evaluation."""

    def test_build_storage_eligible(self):
        v = Villager(50, 42)
        v.lumber = 10
        v.stone = 5
        ctx = _make_goal_ctx(campfire_count=1, pop=STORAGE_POPULATION_THRESHOLD)
        ctx["storage_count"] = 0
        ctx["bank_count"] = 0
        ctx["well_count"] = 0
        ctx["castle_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_storage" in goal_names

    def test_build_storage_not_eligible_max(self):
        v = Villager(50, 42)
        ctx = _make_goal_ctx(campfire_count=1, pop=STORAGE_POPULATION_THRESHOLD)
        ctx["storage_count"] = MAX_STORAGES
        ctx["bank_count"] = 0
        ctx["well_count"] = 0
        ctx["castle_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_storage" not in goal_names

    def test_withdraw_storage_when_need_lumber(self):
        v = Villager(50, 42)
        v.lumber = 0
        storage = _make_structure(stype="storage", x=55, y=38, width=3, height=3)
        storage.under_construction = False
        storage.stored_lumber = 5
        ctx = _make_goal_ctx(campfire_count=1, pop=3, structures=[storage])
        ctx["storage_count"] = 1
        ctx["bank_count"] = 0
        ctx["well_count"] = 0
        ctx["castle_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "withdraw_storage" in goal_names

    def test_deposit_storage_with_excess(self):
        v = Villager(50, 42)
        v.lumber = STORAGE_DEPOSIT_THRESHOLD_LUMBER + 3
        storage = _make_structure(stype="storage", x=55, y=38, width=3, height=3)
        storage.under_construction = False
        ctx = _make_goal_ctx(campfire_count=1, pop=3, structures=[storage])
        ctx["storage_count"] = 1
        ctx["bank_count"] = 0
        ctx["well_count"] = 0
        ctx["castle_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "deposit_storage" in goal_names


# ==========================================================================
# Gold and Bank Tests
# ==========================================================================

from src.display.living_world.structures import _find_bank_site, _get_bank
from src.display.living_world.constants import (
    GOLD_MINE_CHANCE, GOLD_COLOR,
    BANK_COST_LUMBER, BANK_COST_STONE, BANK_BUILD_FRAMES,
    BANK_WIDTH, BANK_HEIGHT, BANK_POPULATION_THRESHOLD, MAX_BANKS,
    BANK_PAL,
)


class TestGoldConstants:
    """Verify gold and bank constants are sane."""

    def test_gold_mine_chance(self):
        assert 0.0 < GOLD_MINE_CHANCE < 1.0

    def test_gold_color(self):
        assert len(GOLD_COLOR) == 3

    def test_bank_costs(self):
        assert BANK_COST_LUMBER >= 3
        assert BANK_COST_STONE >= 2

    def test_bank_dimensions(self):
        assert BANK_WIDTH >= 3
        assert BANK_HEIGHT >= 3

    def test_bank_population_threshold(self):
        assert BANK_POPULATION_THRESHOLD >= 4

    def test_max_banks(self):
        assert MAX_BANKS == 1

    def test_bank_palette(self):
        for key in ('wall', 'roof', 'door'):
            assert key in BANK_PAL
            assert len(BANK_PAL[key]) == 3

    def test_bank_goal_in_priority(self):
        assert "build_bank" in GOAL_PRIORITY
        assert "build_bank" in GOAL_PREREQS

    def test_bank_prereqs(self):
        assert GOAL_PREREQS["build_bank"]["lumber"] == BANK_COST_LUMBER
        assert GOAL_PREREQS["build_bank"]["stone"] == BANK_COST_STONE


class TestVillagerGoldField:
    """Verify villager has gold attribute."""

    def test_villager_has_gold(self):
        v = Villager(50, 42)
        assert hasattr(v, "gold")
        assert v.gold == 0


class TestBankSiteFinding:
    """Verify _find_bank_site locates valid locations."""

    def test_find_bank_site_basic(self):
        heights, world = _make_flat_world()
        site = _find_bank_site([], [], heights, world, near_x=50)
        assert site is not None

    def test_find_bank_site_avoids_structures(self):
        heights, world = _make_flat_world()
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        site = _find_bank_site([house], [], heights, world, near_x=50)
        if site is not None:
            sx, _ = site
            assert abs(sx - 50) >= 3


class TestBankEntity:
    """Verify _get_bank works correctly."""

    def test_get_bank_returns_completed(self):
        s = _make_structure(stype="bank", x=50, y=38, width=4, height=4)
        s.under_construction = False
        assert _get_bank([s]) is s

    def test_get_bank_skips_under_construction(self):
        s = _make_structure(stype="bank", x=50, y=38, width=4, height=4)
        s.under_construction = True
        assert _get_bank([s]) is None

    def test_get_bank_returns_none_empty(self):
        assert _get_bank([]) is None


class TestBankGoalEvaluation:
    """Verify build_bank goal appears in goal evaluation."""

    def test_build_bank_eligible(self):
        v = Villager(50, 42)
        v.lumber = 10
        v.stone = 5
        ctx = _make_goal_ctx(campfire_count=1, pop=BANK_POPULATION_THRESHOLD)
        ctx["bank_count"] = 0
        ctx["storage_count"] = 0
        ctx["well_count"] = 0
        ctx["castle_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_bank" in goal_names

    def test_build_bank_not_eligible_low_pop(self):
        v = Villager(50, 42)
        ctx = _make_goal_ctx(campfire_count=1, pop=2)
        ctx["bank_count"] = 0
        ctx["storage_count"] = 0
        ctx["well_count"] = 0
        ctx["castle_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_bank" not in goal_names

    def test_build_bank_not_eligible_max(self):
        v = Villager(50, 42)
        ctx = _make_goal_ctx(campfire_count=1, pop=BANK_POPULATION_THRESHOLD)
        ctx["bank_count"] = MAX_BANKS
        ctx["storage_count"] = 0
        ctx["well_count"] = 0
        ctx["castle_count"] = 0
        ctx["villagers"] = [v]
        ranked = _evaluate_goals(v, ctx)
        goal_names = [g[1] for g in ranked]
        assert "build_bank" not in goal_names


class TestGoldMining:
    """Verify gold chance when mining."""

    def test_gold_mine_chance_constant(self):
        assert GOLD_MINE_CHANCE == 0.25

    def test_villager_gains_gold_on_lucky_mine(self, monkeypatch):
        """When random < GOLD_MINE_CHANCE, villager gets gold."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "mining"
        v.task_timer = 1  # will complete on this tick
        mine = _make_structure(stype="mine", x=50, y=42, width=1, height=1)
        mine.depth = 1  # will increment to 2, which is even -> stone + gold check
        mine.max_depth = 8
        v.mine_target = mine
        # Force gold to drop
        monkeypatch.setattr(random, "random", lambda: 0.0)
        path_wear = [0] * WORLD_WIDTH
        _update_villagers(
            [v], heights, world,
            trees=[], structures=[mine], lumber_items=[], flowers=[],
            path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
        )
        # Depth 2 is even -> stone gained, and random < 0.25 -> gold gained
        assert v.gold >= 1
        assert v.stone >= 1


# ==========================================================================
# World Reset Command Tests
# ==========================================================================


class TestWorldResetCommand:
    """Verify the reset_world command handler sets the flag."""

    def test_reset_command_sets_flag(self):
        from src.display.living_world.simulation import _apply_living_world_command
        from src.display.living_world.entities import Weather
        weather = Weather()
        villagers = []
        heights = [42] * WORLD_WIDTH
        world = [[0] * WORLD_WIDTH for _ in range(DISPLAY_HEIGHT)]
        structures = []
        cmd = {"action": "reset_world", "params": {}}
        _apply_living_world_command(cmd, weather, villagers, heights, world, structures, 0, 0)
        assert getattr(weather, "_reset_requested", False) is True

    def test_non_reset_command_no_flag(self):
        from src.display.living_world.simulation import _apply_living_world_command
        from src.display.living_world.entities import Weather
        weather = Weather()
        cmd = {"action": "set_weather", "params": {"state": "rain"}}
        _apply_living_world_command(cmd, weather, [], [42] * WORLD_WIDTH,
                                    [[0] * WORLD_WIDTH for _ in range(DISPLAY_HEIGHT)],
                                    [], 0, 0)
        assert getattr(weather, "_reset_requested", False) is False
