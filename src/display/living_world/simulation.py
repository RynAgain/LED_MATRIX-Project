"""Main entry point, camera system, and frame loop orchestration."""

import time
import random
import logging

from PIL import Image

from src.display._shared import should_stop

from .constants import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT, WORLD_WIDTH,
    AIR, GRASS, WATER,
    FRAME_INTERVAL, FLOWER_COLORS,
    CAMERA_FOLLOW_RE_EVAL, CAMERA_SMOOTH_SPEED,
)
from .utils import _clamp
from .entities import Villager, Flower, Weather
from .terrain import (
    _generate_height_profile, _fill_terrain, _flood_valleys,
    _guarantee_pond, _settle_water, _place_sand, _place_trees,
    _generate_stars, _get_valley_cols, _simulate_water,
)
from .day_night import _compute_day_phase, _compute_ambient
from .weather import (
    _update_weather, _update_rain, _update_lightning,
    _update_grass_fires, _update_water_levels,
)
from .structures import _update_structures, _claim_unowned_house
from .villager_ai import (
    _update_villagers, _maybe_spawn_villager, _handle_reproduction,
    _handle_villager_aging, _respawn_if_empty,
)
from .world_updates import (
    _grow_trees, _move_clouds, _move_birds, _animate_bird_wings,
    _maybe_spawn_bird, _maybe_spawn_cloud,
    _update_fireflies, _emit_smoke, _update_smoke,
    _maybe_fish_jump, _update_fish_jumps,
    _maybe_grow_flower, _update_torch_posts,
    _flatten_around_houses,
)
from .rendering import (
    _render_sky, _render_sun_moon, _render_stars, _render_clouds,
    _render_terrain, _render_water, _render_flowers, _render_bridges,
    _render_structures, _render_trees, _render_lumber_items,
    _render_villagers, _render_birds, _render_fish_jumps,
    _render_smoke, _render_fireflies, _render_rain,
    _render_grass_fires, _render_torch_posts, _render_lightning,
)
from .lighting import (
    _apply_campfire_light, _apply_lantern_light,
    _apply_watchtower_light, _apply_torch_post_light,
)

logger = logging.getLogger(__name__)


def _select_follow_target(villagers, structures):
    if not villagers:
        return None
    best = None
    best_score = (-1, -1)
    for v in villagers:
        house_level = v.home.level if v.home is not None else 0
        resources = v.lumber + v.stone
        score = (house_level, resources)
        if score > best_score:
            best_score = score
            best = v
    return best

def _update_camera(camera_x, target_x, sim_tick):
    target_cam = _clamp(target_x - DISPLAY_WIDTH // 2, 0, WORLD_WIDTH - DISPLAY_WIDTH)
    if sim_tick % CAMERA_SMOOTH_SPEED == 0:
        if camera_x < target_cam:
            camera_x += 1
        elif camera_x > target_cam:
            camera_x -= 1
    return _clamp(camera_x, 0, WORLD_WIDTH - DISPLAY_WIDTH)


def run(matrix, duration=900):
    logger.info("Starting Living World simulation")
    seed = random.randint(0, 999999)
    heights = _generate_height_profile(seed)
    world = [[AIR] * WORLD_WIDTH for _ in range(DISPLAY_HEIGHT)]
    _fill_terrain(world, heights)
    _flood_valleys(world, heights)
    _guarantee_pond(heights, world)
    _settle_water(world, ticks=20)
    _place_sand(world)
    trees = _place_trees(heights, world)
    stars = _generate_stars()
    clouds, birds = [], []
    villagers, structures, lumber_items = [], [], []
    fireflies, smoke_particles, fish_jumps = [], [], []
    flowers, rain_drops, grass_fires = [], [], []
    path_wear = [0] * WORLD_WIDTH
    torch_posts = []
    weather = Weather()
    camera_x = WORLD_WIDTH // 2 - DISPLAY_WIDTH // 2
    follow_target = None
    sim_tick = 0
    vc = _get_valley_cols(world)
    center = WORLD_WIDTH // 2
    for _ in range(2):
        for __ in range(30):
            col = random.randint(center - 15, center + 15)
            col = _clamp(col, 4, WORLD_WIDTH - 5)
            if col in vc: continue
            sy = heights[col]
            if 0 <= sy < DISPLAY_HEIGHT and world[sy][col] == GRASS:
                villagers.append(Villager(col, sy))
                break
    for _ in range(random.randint(3, 6)):
        x = random.randint(4, WORLD_WIDTH - 5)
        sy = heights[x]
        if 0 <= sy < DISPLAY_HEIGHT and world[sy][x] == GRASS:
            if not any(f.x == x for f in flowers):
                flowers.append(Flower(x, sy, random.choice(FLOWER_COLORS)))
    start_time = time.time()
    image = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    try:
        while time.time() - start_time < duration and not should_stop():
            frame_start = time.time()
            elapsed = time.time() - start_time
            day_phase = _compute_day_phase(elapsed)
            ambient = _compute_ambient(day_phase)
            _update_weather(weather, sim_tick)
            _move_clouds(clouds, weather)
            _move_birds(birds, sim_tick)
            if sim_tick % 3 == 0:
                _update_villagers(villagers, heights, world, trees, structures, lumber_items, flowers, path_wear, day_phase, sim_tick, weather)
            if sim_tick % 4 == 0:
                _simulate_water(world)
                _animate_bird_wings(birds)
            if sim_tick % 10 == 0:
                _grow_trees(trees, heights, world, sim_tick, weather, structures)
            if sim_tick % 90 == 0:
                _maybe_spawn_bird(birds, day_phase, weather, camera_x)
                _maybe_spawn_cloud(clouds, weather, camera_x)
            if sim_tick % 2 == 0:
                _update_fireflies(fireflies, day_phase, heights, trees, camera_x)
            if sim_tick % 3 == 0:
                _emit_smoke(smoke_particles, structures, camera_x)
                _update_smoke(smoke_particles)
            if sim_tick % 200 == 0:
                _maybe_fish_jump(fish_jumps, world, heights, day_phase, camera_x)
            _update_fish_jumps(fish_jumps)
            if sim_tick % 500 == 0:
                _maybe_grow_flower(flowers, heights, world, trees, camera_x, weather)
            _maybe_spawn_villager(villagers, heights, world, structures, trees, sim_tick)
            _handle_reproduction(villagers, heights, world, structures, sim_tick)
            _handle_villager_aging(villagers, structures)
            _respawn_if_empty(villagers, heights, world, structures)
            _update_structures(structures, villagers)
            _update_rain(rain_drops, weather, heights, world, camera_x)
            _update_lightning(weather, trees, grass_fires, heights, world, camera_x, sim_tick)
            _update_grass_fires(grass_fires)
            _update_water_levels(world, heights, weather, sim_tick)
            _update_torch_posts(torch_posts, path_wear, heights, structures, sim_tick)
            _flatten_around_houses(structures, heights, world, villagers, sim_tick, day_phase)
            for it in lumber_items: it.age += 1
            lumber_items[:] = [it for it in lumber_items if it.age < 5400]
            if sim_tick % CAMERA_FOLLOW_RE_EVAL == 0:
                follow_target = _select_follow_target(villagers, structures)
            if follow_target is not None:
                camera_x = _update_camera(camera_x, int(follow_target.x), sim_tick)
            pixels = image.load()
            _render_sky(pixels, day_phase, weather, camera_x)
            _render_sun_moon(pixels, day_phase)
            _render_stars(pixels, stars, ambient, sim_tick)
            _render_clouds(pixels, clouds, ambient, camera_x)
            _render_terrain(pixels, world, heights, ambient, camera_x, path_wear, day_phase)
            _render_water(pixels, world, heights, ambient, sim_tick, camera_x)
            _render_flowers(pixels, flowers, ambient, camera_x)
            _render_bridges(pixels, structures, ambient, camera_x)
            _render_structures(pixels, structures, ambient, sim_tick, camera_x, day_phase)
            _render_trees(pixels, trees, ambient, sim_tick, camera_x, weather, day_phase)
            _render_lumber_items(pixels, lumber_items, ambient, camera_x)
            _render_villagers(pixels, villagers, ambient, sim_tick, camera_x)
            _render_birds(pixels, birds, ambient, sim_tick, camera_x)
            _render_fish_jumps(pixels, fish_jumps, camera_x)
            _render_smoke(pixels, smoke_particles, ambient, camera_x)
            _render_fireflies(pixels, fireflies, sim_tick, camera_x)
            _render_rain(pixels, rain_drops, camera_x)
            _render_grass_fires(pixels, grass_fires, camera_x)
            _render_torch_posts(pixels, torch_posts, ambient, camera_x)
            _render_lightning(pixels, weather)
            _apply_campfire_light(pixels, structures, ambient, camera_x)
            _apply_lantern_light(pixels, structures, ambient, camera_x)
            _apply_watchtower_light(pixels, structures, ambient, camera_x)
            _apply_torch_post_light(pixels, torch_posts, ambient, camera_x)
            matrix.SetImage(image)
            sim_tick += 1
            frame_elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - frame_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception as e:
        logger.error("Error in living_world: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
