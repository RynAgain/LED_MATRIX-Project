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
        # Force random.random to return 0.49 (just under 0.5 -- should spawn)
        call_count = [0]
        def fake_random():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.49  # passes threshold check
            return 0.0  # for any subsequent random calls
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
                return 0.51  # would fail base 0.5, passes rain 0.75
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
                return 0.76  # would fail rain 0.75, passes storm 0.90
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

    # --- Constants sanity ---

    def test_storm_cloud_width_larger_than_normal(self):
        """Storm cloud min width >= normal cloud max width."""
        assert STORM_CLOUD_WIDTH_RANGE[0] >= CLOUD_WIDTH_RANGE[1]

    def test_storm_cloud_height_larger_than_normal(self):
        """Storm cloud min height >= normal cloud max height."""
        assert STORM_CLOUD_HEIGHT_RANGE[0] >= CLOUD_HEIGHT_RANGE[1]

    def test_storm_alpha_more_opaque(self):
        """Storm cloud alpha should be higher (more opaque) than normal."""
        assert STORM_CLOUD_ALPHA > CLOUD_ALPHA

    def test_storm_cloud_count_higher(self):
        """Storm weather should allow at least 10 clouds."""
        _mn, mx, _, _ = WEATHER_CLOUD_PARAMS["storm"]
        assert mx >= 10

    def test_alpha_values_valid(self):
        """Both alpha values must be between 0.0 and 1.0."""
        assert 0.0 <= CLOUD_ALPHA <= 1.0
        assert 0.0 <= STORM_CLOUD_ALPHA <= 1.0

    # --- Cloud entity ---

    def test_cloud_default_alpha_none(self):
        """Cloud created without alpha kwarg stores alpha=None."""
        c = Cloud(0, 5, 6, 2, 0.05, 1)
        assert c.alpha is None

    def test_cloud_custom_alpha(self):
        """Cloud created with alpha=0.85 stores that value."""
        c = Cloud(0, 5, 6, 2, 0.05, 1, alpha=0.85)
        assert c.alpha == 0.85

    def test_cloud_shape_generated(self):
        """Cloud shape list has correct height (rows) and width (cols)."""
        w, h = 8, 3
        c = Cloud(0, 5, w, h, 0.05, 1)
        assert len(c.shape) == h
        assert all(len(row) == w for row in c.shape)

    # --- Cloud spawning behaviour ---

    def test_storm_cloud_dimensions(self, monkeypatch):
        """Storm clouds get dimensions from STORM_CLOUD_WIDTH/HEIGHT_RANGE."""
        clouds = []
        weather = _make_weather(WEATHER_STORM)
        scripted = [
            WEATHER_CLOUD_PARAMS["storm"][1],  # tgt = randint(mn, mx)
            STORM_CLOUD_WIDTH_RANGE[0],         # w
            STORM_CLOUD_HEIGHT_RANGE[0],         # h
            5,                                   # x offset
            3,                                   # y
        ]
        call_idx = [0]
        def fake_randint(a, b):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx < len(scripted):
                return scripted[idx]
            return a  # fallback for Cloud._generate_shape internal calls
        monkeypatch.setattr(random, "randint", fake_randint)
        monkeypatch.setattr(random, "choice", lambda lst: lst[0])
        monkeypatch.setattr(random, "uniform", lambda a, b: a)
        _maybe_spawn_cloud(clouds, weather, camera_x=0)
        assert len(clouds) == 1
        c = clouds[0]
        assert STORM_CLOUD_WIDTH_RANGE[0] <= c.width <= STORM_CLOUD_WIDTH_RANGE[1]
        assert STORM_CLOUD_HEIGHT_RANGE[0] <= c.height <= STORM_CLOUD_HEIGHT_RANGE[1]

    def test_storm_cloud_alpha_set(self, monkeypatch):
        """Clouds spawned during storm carry alpha == STORM_CLOUD_ALPHA."""
        clouds = []
        weather = _make_weather(WEATHER_STORM)
        scripted = [
            WEATHER_CLOUD_PARAMS["storm"][1],
            STORM_CLOUD_WIDTH_RANGE[0],
            STORM_CLOUD_HEIGHT_RANGE[0],
            5,
            3,
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
        """Clear-weather clouds use CLOUD_WIDTH_RANGE / CLOUD_HEIGHT_RANGE."""
        clouds = []
        weather = _make_weather(WEATHER_CLEAR)
        scripted = [
            WEATHER_CLOUD_PARAMS["clear"][1],   # tgt
            CLOUD_WIDTH_RANGE[0],                # w
            CLOUD_HEIGHT_RANGE[0],               # h
            5,                                   # x offset
            8,                                   # y
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
        """Clear-weather clouds carry alpha == CLOUD_ALPHA."""
        clouds = []
        weather = _make_weather(WEATHER_CLEAR)
        scripted = [
            WEATHER_CLOUD_PARAMS["clear"][1],
            CLOUD_WIDTH_RANGE[0],
            CLOUD_HEIGHT_RANGE[0],
            5,
            8,
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
    """Create a Structure with the given parameters."""
    s = Structure(stype, x, y, width, height)
    s.under_construction = under_construction
    return s


class TestTreeBuildingSpacing:
    """Verify tree-building minimum spacing logic."""

    def test_tree_building_min_spacing_constant(self):
        """TREE_BUILDING_MIN_SPACING should be 2."""
        assert TREE_BUILDING_MIN_SPACING == 2

    def test_too_close_to_structure_true(self):
        """Positions within 2px of structure footprint (50-52) are too close."""
        s = _make_structure(x=50, width=3)
        structures = [s]
        for pos in (49, 50, 51, 52, 53, 54):
            assert _too_close_wu(pos, structures) is True, (
                f"x={pos} should be too close to structure at x=50 width=3"
            )

    def test_too_close_to_structure_false(self):
        """Positions well outside the spacing band are not too close."""
        s = _make_structure(x=50, width=3)
        structures = [s]
        assert _too_close_wu(45, structures) is False
        assert _too_close_wu(58, structures) is False

    def test_too_close_no_structures(self):
        """Empty structure list always returns False."""
        assert _too_close_wu(50, []) is False

    def test_growing_sapling_killed_near_structure(self):
        """A sapling within spacing of a structure is killed by _grow_trees."""
        heights, world = _make_flat_world()
        # Place structure at x=50, width=3 -> footprint 50-52, exclusion 48-54
        s = _make_structure(x=50, width=3)
        # Sapling at x=51 (inside structure footprint)
        tree = _make_sapling(x=51, growth=0.5)
        assert tree.alive is True
        _grow_trees([tree], heights, world, 0, weather=None, structures=[s])
        assert tree.alive is False

    def test_growing_sapling_survives_far_from_structure(self):
        """A sapling far from any structure keeps growing normally."""
        heights, world = _make_flat_world()
        s = _make_structure(x=50, width=3)
        # Sapling at x=10, well outside exclusion zone 48-54
        tree = _make_sapling(x=10, growth=0.5)
        _grow_trees([tree], heights, world, 0, weather=None, structures=[s])
        assert tree.alive is True
        assert tree.growth == pytest.approx(0.503, abs=1e-6)


# --- Housing Population Cap Tests ---

class TestHousingPopulationCap:
    """Verify housing-based population cap logic."""

    def test_population_cap_no_houses(self):
        """With no structures, cap equals BASE_VILLAGERS (2)."""
        assert _compute_population_cap([]) == BASE_VILLAGERS

    def test_population_cap_one_house(self):
        """One completed house: cap = BASE_VILLAGERS + 1 * VILLAGERS_PER_HOUSE = 4."""
        s = _make_structure(stype="house_small", under_construction=False)
        assert _compute_population_cap([s]) == BASE_VILLAGERS + 1 * VILLAGERS_PER_HOUSE

    def test_population_cap_five_houses(self):
        """Five completed houses: cap = BASE_VILLAGERS + 5 * VILLAGERS_PER_HOUSE = 12."""
        houses = [_make_structure(stype="house_small", x=10 * i) for i in range(5)]
        assert _compute_population_cap(houses) == BASE_VILLAGERS + 5 * VILLAGERS_PER_HOUSE

    def test_population_cap_clamped_at_max(self):
        """With 15 houses the raw cap exceeds MAX_VILLAGERS; result is clamped to 20."""
        houses = [_make_structure(stype="house_large", x=10 * i) for i in range(15)]
        raw = BASE_VILLAGERS + 15 * VILLAGERS_PER_HOUSE  # 32
        assert raw > MAX_VILLAGERS
        assert _compute_population_cap(houses) == MAX_VILLAGERS

    def test_population_cap_ignores_under_construction(self):
        """Houses still under construction do not count toward the cap."""
        built = _make_structure(stype="house_small", x=10, under_construction=False)
        wip = _make_structure(stype="house_small", x=30, under_construction=True)
        # Only 1 completed house counts
        assert _compute_population_cap([built, wip]) == BASE_VILLAGERS + 1 * VILLAGERS_PER_HOUSE

    def test_population_cap_ignores_non_houses(self):
        """Campfires, mines, and other structure types do not increase the cap."""
        campfire = _make_structure(stype="campfire", x=20, width=1, height=1)
        mine = _make_structure(stype="mine", x=60, width=1, height=1)
        watchtower = _make_structure(stype="watchtower", x=80, width=2, height=7)
        assert _compute_population_cap([campfire, mine, watchtower]) == BASE_VILLAGERS

    def test_constants_sanity(self):
        """Core population constants have expected values."""
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
    """Verify house area flattening feature: constants, column flattening, and
    the periodic house-area flattening orchestrator."""

    # 1. Constants

    def test_flatten_constants(self):
        """Verify HOUSE_FLATTEN_RADIUS, HOUSE_FLATTEN_INTERVAL, and HOUSE_FLATTEN_RATE."""
        assert HOUSE_FLATTEN_RADIUS == 5
        assert HOUSE_FLATTEN_INTERVAL == 500
        assert HOUSE_FLATTEN_RATE == 1

    # 2. Column lowering (high terrain -> target)

    def test_flatten_column_lowers_high_terrain(self):
        """A column at y=40 (2 blocks above target y=42) moves to y=41 with rate=1."""
        heights, world = _make_flat_world(surface_y=42)
        x = 50
        # Raise column: move surface from y=42 to y=40 (higher terrain)
        world[42][x] = DIRT  # old surface becomes dirt
        world[41][x] = DIRT
        world[40][x] = GRASS  # new surface
        heights[x] = 40

        result = _flatten_column_toward(world, heights, x, 42, 1)
        assert result is True
        assert heights[x] == 41

    # 3. Column raising (low terrain -> target)

    def test_flatten_column_raises_low_terrain(self):
        """A column at y=44 (2 blocks below target y=42) moves to y=43 with rate=1."""
        heights, world = _make_flat_world(surface_y=42)
        x = 50
        # Lower column: move surface from y=42 to y=44 (lower terrain)
        world[42][x] = AIR  # clear old surface
        world[43][x] = AIR
        world[44][x] = GRASS  # new surface
        heights[x] = 44

        result = _flatten_column_toward(world, heights, x, 42, 1)
        assert result is True
        assert heights[x] == 43

    # 4. Column already level

    def test_flatten_column_skips_level_terrain(self):
        """A column already at target y=42 is unchanged."""
        heights, world = _make_flat_world(surface_y=42)
        x = 50
        original_h = heights[x]

        result = _flatten_column_toward(world, heights, x, 42, 1)
        assert result is False
        assert heights[x] == original_h

    # 5. Water column skip

    def test_flatten_column_skips_water(self):
        """A column whose surface block is WATER is not modified."""
        heights, world = _make_flat_world(surface_y=42)
        x = 50
        world[42][x] = WATER  # surface is water
        heights[x] = 42

        # Try to flatten toward a different target
        result = _flatten_column_toward(world, heights, x, 40, 1)
        assert result is False
        assert heights[x] == 42

    # 6. Out-of-bounds safety

    def test_flatten_column_skips_out_of_bounds(self):
        """Calling with x=-1 or x=WORLD_WIDTH does not crash or modify anything."""
        heights, world = _make_flat_world(surface_y=42)
        original_heights = list(heights)

        result_neg = _flatten_column_toward(world, heights, -1, 42, 1)
        assert result_neg is False
        assert heights == original_heights

        result_oob = _flatten_column_toward(world, heights, WORLD_WIDTH, 42, 1)
        assert result_oob is False
        assert heights == original_heights

    # 7. Orchestrator: basic flatten around house

    def test_flatten_around_houses_basic(self):
        """Completed house with idle owner flattens uneven terrain during daytime."""
        heights, world = _make_flat_world(surface_y=42)
        # Create a house: type="house_small", x=50, y=38, width=3, height=4
        # target_y = s.y + s.height = 38 + 4 = 42
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False

        # Create idle owner villager
        owner = Villager(50, 38)
        owner.state = "idle"
        house.owner = owner

        # Make columns uneven (differ by >= 2 from target 42)
        uneven_cols = [46, 47, 48, 55, 56, 57]
        for col in uneven_cols:
            # Raise these columns to y=39 (3 above target)
            world[42][col] = DIRT
            world[41][col] = DIRT
            world[40][col] = DIRT
            world[39][col] = GRASS
            heights[col] = 39

        structures = [house]
        villagers = [owner]

        # tick=0 is multiple of HOUSE_FLATTEN_INTERVAL, day_phase=0.25 -> daytime
        _flatten_around_houses(structures, heights, world, villagers, 0, 0.25)

        # At least some columns should have moved toward target (from 39 toward 42)
        changed = sum(1 for col in uneven_cols if heights[col] != 39)
        assert changed > 0, "Expected at least some columns to be flattened"

    # 8. Orchestrator: skip nighttime

    def test_flatten_around_houses_skips_nighttime(self):
        """No terrain changes when day_phase indicates nighttime (ambient < 0.3)."""
        heights, world = _make_flat_world(surface_y=42)
        house = _make_structure(stype="house_small", x=50, y=38, width=3, height=4)
        house.under_construction = False
        owner = Villager(50, 38)
        owner.state = "idle"
        house.owner = owner

        # Make columns uneven
        for col in [46, 47, 48]:
            world[42][col] = DIRT
            world[41][col] = DIRT
            world[40][col] = DIRT
            world[39][col] = GRASS
            heights[col] = 39

        original_heights = list(heights)
        structures = [house]
        villagers = [owner]

        # tick=0 (valid interval), day_phase=0.8 (nighttime, ambient=0.15)
        _flatten_around_houses(structures, heights, world, villagers, 0, 0.8)

        assert heights == original_heights


# --- Villager Climbing Tests ---

from src.display.living_world.villager_ai import _update_villagers
from src.display.living_world.constants import VILLAGER_MAX_CLIMB, VILLAGER_CLIMB_SPEED


def _raise_column(world, heights, x, new_y, old_y=42):
    """Raise a column so its surface moves from old_y to new_y (lower y = higher)."""
    world[new_y][x] = GRASS
    for y in range(new_y + 1, old_y + 1):
        world[y][x] = DIRT
    heights[x] = new_y


def _lower_column(world, heights, x, new_y, old_y=42):
    """Lower a column so its surface moves from old_y to new_y (higher y = lower)."""
    for y in range(old_y, new_y):
        world[y][x] = AIR
    world[new_y][x] = GRASS
    heights[x] = new_y


def _make_walking_villager(x, target_x, surface_y=42):
    """Create a villager in walking state at position x heading toward target_x."""
    v = Villager(x, surface_y)
    v.state = "walking"
    v.target_x = target_x
    v.direction = 1 if target_x > x else -1
    v.idle_timer = 0
    return v


def _run_walking_update(villagers, heights, world):
    """Run one tick of _update_villagers with minimal scaffolding."""
    path_wear = [0] * WORLD_WIDTH
    _update_villagers(
        villagers, heights, world,
        trees=[], structures=[], lumber_items=[], flowers=[],
        path_wear=path_wear, day_phase=0.25, sim_tick=100, weather=None,
    )


class TestVillagerClimbing:
    """Verify villager climbing feature: constants, climb_timer, height traversal."""

    # 1. Constants

    def test_climbing_constants(self):
        """VILLAGER_MAX_CLIMB is 3, VILLAGER_CLIMB_SPEED is 2."""
        assert VILLAGER_MAX_CLIMB == 3
        assert VILLAGER_CLIMB_SPEED == 2

    # 2. Villager entity

    def test_villager_has_climb_timer(self):
        """A new Villager has climb_timer initialized to 0."""
        v = Villager(50, 42)
        assert v.climb_timer == 0

    # 3. Climb 1 block -- no delay

    def test_climb_1_block_no_delay(self):
        """Stepping up 1 block moves the villager without setting climb_timer."""
        heights, world = _make_flat_world(surface_y=42)
        _raise_column(world, heights, 51, 41)  # 1 block higher

        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        _run_walking_update([v], heights, world)

        assert int(v.x) == 51, "Villager should have moved to column 51"
        assert v.y == heights[51], "Villager y should match destination column height"
        assert v.climb_timer == 0, "1-block step should not set climb_timer"

    # 4. Climb 2 blocks -- delay set

    def test_climb_2_blocks_has_delay(self):
        """Stepping up 2 blocks moves the villager and sets climb_timer."""
        heights, world = _make_flat_world(surface_y=42)
        _raise_column(world, heights, 51, 40)  # 2 blocks higher

        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        _run_walking_update([v], heights, world)

        assert int(v.x) == 51, "Villager should have moved to column 51"
        assert v.y == heights[51], "Villager y should match destination column height"
        assert v.climb_timer == VILLAGER_CLIMB_SPEED, (
            "2-block step should set climb_timer to VILLAGER_CLIMB_SPEED"
        )

    # 5. Climb 3 blocks -- still passable (max)

    def test_climb_3_blocks_passable(self):
        """Stepping up 3 blocks (the max) is allowed; villager moves."""
        heights, world = _make_flat_world(surface_y=42)
        _raise_column(world, heights, 51, 39)  # 3 blocks higher

        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        _run_walking_update([v], heights, world)

        assert int(v.x) == 51, "Villager should traverse a 3-block height diff"
        assert v.state == "walking", "Villager should still be walking"

    # 6. Climb 4 blocks -- blocked

    def test_climb_4_blocks_blocked(self):
        """A 4-block height diff exceeds VILLAGER_MAX_CLIMB; villager goes idle."""
        heights, world = _make_flat_world(surface_y=42)
        _raise_column(world, heights, 51, 38)  # 4 blocks higher

        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        _run_walking_update([v], heights, world)

        assert int(v.x) == 50, "Villager should NOT have moved past the 4-block wall"
        assert v.state == "idle", "Villager should go idle when blocked"

    # 7. Climb timer pauses movement

    def test_climb_timer_pauses_movement(self):
        """While climb_timer > 0, the villager does not move and timer decrements."""
        heights, world = _make_flat_world(surface_y=42)

        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        v.climb_timer = 2
        _run_walking_update([v], heights, world)

        assert int(v.x) == 50, "Villager should NOT move while climb_timer > 0"
        assert v.climb_timer == 1, "climb_timer should decrement by 1"

    # 8. Descend 2 blocks -- delay set

    def test_descend_2_blocks_has_delay(self):
        """Stepping down 2 blocks moves the villager and sets climb_timer."""
        heights, world = _make_flat_world(surface_y=42)
        _lower_column(world, heights, 51, 44)  # 2 blocks lower

        v = _make_walking_villager(x=50, target_x=55, surface_y=42)
        _run_walking_update([v], heights, world)

        assert int(v.x) == 51, "Villager should have moved to column 51"
        assert v.y == heights[51], "Villager y should match destination column height"
        assert v.climb_timer == VILLAGER_CLIMB_SPEED, (
            "2-block descent should set climb_timer to VILLAGER_CLIMB_SPEED"
        )

    # 9. Orchestrator: skip non-interval tick

    def test_flatten_around_houses_skips_non_interval_tick(self):
        """No changes when tick is not a multiple of HOUSE_FLATTEN_INTERVAL."""
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

        # tick=1 is NOT a multiple of HOUSE_FLATTEN_INTERVAL (500)
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
    """Verify villager fire fighting feature: constants, detection, extinguishing."""

    # 1. Constants

    def test_firefight_constants(self):
        """FIREFIGHT_DETECT_RADIUS is 20, FIREFIGHT_EXTINGUISH_TICKS is 10,
        and 'firefighting' is in BUBBLE_COLORS."""
        assert FIREFIGHT_DETECT_RADIUS == 20
        assert FIREFIGHT_EXTINGUISH_TICKS == 10
        assert "firefighting" in BUBBLE_COLORS

    # 2. Entity default

    def test_villager_has_firefight_target(self):
        """A new Villager has firefight_target initialized to None."""
        v = Villager(50, 42)
        assert v.firefight_target is None

    # 3. _find_nearest_fire: burning tree within radius

    def test_find_nearest_fire_burning_tree(self):
        """A burning tree within detect radius is returned."""
        v = Villager(50, 42)
        tree = Tree(55, 42, 1.0, 7, 3, 0)
        tree.on_fire = True
        tree.fire_timer = 20
        result = _find_nearest_fire(v, [tree], [], [v])
        assert result is tree

    # 4. _find_nearest_fire: no fires

    def test_find_nearest_fire_no_fire(self):
        """No burning trees and no grass fires returns None."""
        v = Villager(50, 42)
        # A healthy tree should not be detected
        healthy_tree = Tree(55, 42, 1.0, 7, 3, 0)
        result = _find_nearest_fire(v, [healthy_tree], [], [v])
        assert result is None

    # 5. _find_nearest_fire: out of range

    def test_find_nearest_fire_out_of_range(self):
        """A burning tree beyond FIREFIGHT_DETECT_RADIUS returns None."""
        v = Villager(50, 42)
        tree = Tree(50 + FIREFIGHT_DETECT_RADIUS + 1, 42, 1.0, 7, 3, 0)
        tree.on_fire = True
        tree.fire_timer = 20
        result = _find_nearest_fire(v, [tree], [], [v])
        assert result is None

    # 6. _find_nearest_fire: excludes targeted

    def test_find_nearest_fire_excludes_targeted(self):
        """A burning tree already targeted by another villager is excluded."""
        v = Villager(50, 42)
        other = Villager(52, 42)
        tree = Tree(55, 42, 1.0, 7, 3, 0)
        tree.on_fire = True
        tree.fire_timer = 20
        other.firefight_target = tree  # other villager already targeting this tree
        result = _find_nearest_fire(v, [tree], [], [v, other])
        assert result is None

    # 7. _find_nearest_fire: grass fire

    def test_find_nearest_fire_grass_fire(self):
        """A GrassFire within range with no burning trees is returned."""
        v = Villager(50, 42)
        gf = GrassFire(55, 42, 30)
        result = _find_nearest_fire(v, [], [gf], [v])
        assert result is gf

    # 8. Idle villager detects fire

    def test_idle_villager_detects_fire(self):
        """An idle villager near a burning tree switches to firefighting."""
        heights, world = _make_flat_world()
        v = Villager(50, 42)
        v.state = "idle"
        v.idle_timer = 25  # must be >= 20 for idle logic to run
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

    # 9. Firefighting extinguishes tree

    def test_firefight_extinguishes_tree(self):
        """A villager adjacent to a burning tree extinguishes it after enough ticks."""
        heights, world = _make_flat_world()
        tree = Tree(50, 42, 1.0, 7, 3, 0)
        tree.on_fire = True
        tree.fire_timer = 20
        v = Villager(50, 42)
        v.state = "firefighting"
        v.firefight_target = tree
        v.target_x = tree.x
        v.task_timer = FIREFIGHT_EXTINGUISH_TICKS - 1  # one tick away
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

    # 10. Firefighting extinguishes grass fire

    def test_firefight_extinguishes_grass_fire(self):
        """A villager adjacent to a GrassFire removes it from the list."""
        heights, world = _make_flat_world()
        gf = GrassFire(50, 42, 30)
        grass_fires = [gf]
        v = Villager(50, 42)
        v.state = "firefighting"
        v.firefight_target = gf
        v.target_x = gf.x
        v.task_timer = FIREFIGHT_EXTINGUISH_TICKS - 1  # one tick away
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
