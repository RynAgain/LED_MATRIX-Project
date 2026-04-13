"""Main entry point, camera system, and frame loop orchestration."""

import time
import random
import logging
import json
import os

from PIL import Image

from src.display._shared import should_stop

from .constants import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT, WORLD_WIDTH,
    AIR, GRASS, WATER,
    FRAME_INTERVAL, FLOWER_COLORS,
    CAMERA_FOLLOW_RE_EVAL, CAMERA_SMOOTH_SPEED,
    FARM_GROWTH_CHECK_INTERVAL,
)
from .utils import _clamp
from .entities import Villager, Flower, Weather
from .terrain import (
    _generate_height_profile, _fill_terrain, _flood_valleys,
    _guarantee_pond, _settle_water, _place_sand, _place_trees,
    _generate_stars, _get_valley_cols, _simulate_water,
)
from .day_night import (
    _compute_day_phase, _compute_ambient, _compute_season_transition,
    _check_solar_eclipse, _check_lunar_eclipse,
)
from .constants import ECLIPSE_AMBIENT_MIN
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
    _maybe_spawn_animal, _update_animals,
    _maybe_spawn_shooting_star, _update_shooting_stars,
    _grow_crops,
    _update_snow,
    _maybe_spawn_caravan, _update_caravans,
)
from .rendering import (
    _render_sky, _render_sun_moon, _render_stars, _render_shooting_stars,
    _render_clouds,
    _render_terrain_and_water, _render_flowers, _render_bridges,
    _render_structures, _render_trees, _render_lumber_items,
    _render_villagers, _render_birds, _render_fish_jumps,
    _render_smoke, _render_fireflies, _render_rain,
    _render_grass_fires, _render_torch_posts, _render_lightning,
    _render_animals, _render_farms, _render_snow,
    _render_boats, _render_caravans,
)
from .lighting import (
    _apply_campfire_light, _apply_lantern_light,
    _apply_watchtower_light, _apply_torch_post_light,
)
from .persistence import save_world, load_world, delete_save, restore_entities

logger = logging.getLogger(__name__)

_LW_CMD_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs", "living_world_command.json")


def _check_living_world_command():
    """Check for and consume a living world command from the web UI.

    Returns a dict with 'action' and 'params' keys, or None.
    Uses a separate command file to avoid triggering main loop's request_stop().
    """
    path = os.path.abspath(_LW_CMD_PATH)
    if not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
        if time.time() - mtime > 30:
            os.remove(path)
            return None
        with open(path, "r") as f:
            cmd = json.load(f)
        os.remove(path)
        return cmd
    except Exception:
        return None


def _apply_living_world_command(cmd, weather, villagers, heights, world, structures, sim_tick, start_time):
    """Apply a living world control command from the web UI."""
    from .entities import Villager
    from .event_log import log_event, CAT_WORLD
    from .terrain import _get_valley_cols
    from .structures import _claim_unowned_house

    action = cmd.get("action", "")
    params = cmd.get("params", {})

    if action == "set_weather":
        new_state = params.get("state", "clear")
        valid = ("clear", "cloudy", "rain", "storm")
        if new_state in valid:
            weather.prev_state = weather.state
            weather.state = new_state
            weather.timer = random.randint(2000, 5000)
            weather.transition_frames = 60
            log_event(sim_tick, CAT_WORLD, f"Web UI set weather to {new_state}")
            logger.info("Living world command: weather -> %s", new_state)

    elif action == "spawn_villager":
        vc = _get_valley_cols(world)
        center = WORLD_WIDTH // 2
        for _ in range(30):
            col = random.randint(center - 20, center + 20)
            col = max(4, min(col, WORLD_WIDTH - 5))
            if col in vc:
                continue
            sy = heights[col]
            if 0 <= sy < DISPLAY_HEIGHT and world[sy][col] in (1,):  # GRASS=1
                baby = Villager(col, sy)
                _claim_unowned_house(baby, structures)
                villagers.append(baby)
                log_event(sim_tick, CAT_WORLD, f"Web UI spawned villager {baby.name} at x={col}")
                logger.info("Living world command: spawned villager %s", baby.name)
                break

    elif action == "set_time":
        phase = params.get("phase", "day")
        if phase == "day":
            # Jump elapsed to 25% of day cycle (mid-day)
            pass  # Time is derived from start_time; we can't easily change elapsed
            log_event(sim_tick, CAT_WORLD, "Web UI requested day (note: time is continuous)")
        elif phase == "night":
            log_event(sim_tick, CAT_WORLD, "Web UI requested night (note: time is continuous)")
        logger.info("Living world command: set_time %s", phase)

    elif action == "toggle_season":
        log_event(sim_tick, CAT_WORLD, "Web UI toggled season (note: seasons are time-based)")
        logger.info("Living world command: toggle_season")

    elif action == "reset_world":
        log_event(sim_tick, CAT_WORLD, "Web UI requested world reset")
        logger.info("Living world command: reset_world")
        # Signal the main loop to regenerate
        from .persistence import delete_save
        delete_save()
        # Set a flag on weather object to signal reset to main loop
        weather._reset_requested = True


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
    """Run the living world simulation.

    Args:
        matrix: LED matrix or simulator object.
        duration: Seconds to run.  0 means run indefinitely (until should_stop()).
    """
    logger.info("Starting Living World simulation (duration=%s)", duration)
    # --- Attempt to restore saved world state ---
    restored = False
    saved = load_world()
    if saved is not None:
        result = restore_entities(saved)
        if result is not None:
            villagers = result["villagers"]
            structures = result["structures"]
            trees = result["trees"]
            farms = result["farms"]
            animals = result["animals"]
            flowers = result["flowers"]
            lumber_items = result["lumber_items"]
            weather = result["weather"]
            heights = result["heights"]
            world = result["world"]
            path_wear = result["path_wear"]
            stars = result["stars"]
            torch_posts = result["torch_posts"]
            camera_x = result["camera_x"]
            sim_tick = result["sim_tick"]
            clouds, birds = [], []
            shooting_stars = []
            snow_flakes = []
            caravans = []
            fireflies, smoke_particles, fish_jumps = [], [], []
            rain_drops, grass_fires = [], []
            follow_target = None
            delete_save()
            restored = True
            logger.info("Restored world from save (tick=%d, %d villagers)", sim_tick, len(villagers))
    if not restored:
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
        animals = []
        shooting_stars = []
        caravans = []
        farms = []
        fireflies, smoke_particles, fish_jumps = [], [], []
        snow_flakes = []
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
        while not should_stop():
            if duration > 0 and time.time() - start_time >= duration:
                break
            # --- Check for world reset request (e.g. from web UI) ---
            if getattr(weather, '_reset_requested', False):
                weather._reset_requested = False
                logger.info("World reset requested -- regenerating")
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
                animals = []
                shooting_stars = []
                caravans = []
                farms = []
                fireflies, smoke_particles, fish_jumps = [], [], []
                snow_flakes = []
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
                        if col in vc:
                            continue
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
                continue
            frame_start = time.time()
            elapsed = time.time() - start_time
            day_phase = _compute_day_phase(elapsed)
            ambient = _compute_ambient(day_phase)
            # Eclipse ambient override
            solar_eclipse = _check_solar_eclipse(elapsed, day_phase)
            lunar_eclipse = _check_lunar_eclipse(elapsed, day_phase)
            if solar_eclipse > 0:
                ambient = max(ECLIPSE_AMBIENT_MIN, ambient * (1.0 - solar_eclipse * 0.9))
            season_info = _compute_season_transition(elapsed)
            current_season = season_info[0]
            _update_weather(weather, sim_tick)
            _move_clouds(clouds, weather)
            _move_birds(birds, sim_tick, trees)
            if sim_tick % 3 == 0:
                _update_villagers(villagers, heights, world, trees, structures, lumber_items, flowers, path_wear, day_phase, sim_tick, weather, farms=farms, animals=animals)
            if sim_tick % 4 == 0:
                _simulate_water(world)
                _animate_bird_wings(birds)
            if sim_tick % 10 == 0:
                _grow_trees(trees, heights, world, sim_tick, weather, structures, current_season=current_season)
            if sim_tick % FARM_GROWTH_CHECK_INTERVAL == 0:
                _grow_crops(farms, weather=weather, current_season=current_season)
            if sim_tick % 90 == 0:
                _maybe_spawn_bird(birds, day_phase, weather, camera_x)
                _maybe_spawn_cloud(clouds, weather, camera_x)
            if sim_tick % 2 == 0:
                _update_fireflies(fireflies, day_phase, heights, trees, camera_x)
                _update_animals(animals, heights, world, villagers, sim_tick)
            _maybe_spawn_shooting_star(shooting_stars, ambient)
            _update_shooting_stars(shooting_stars)
            _maybe_spawn_animal(animals, heights, world, sim_tick, villagers, current_season=current_season)
            _maybe_spawn_caravan(caravans, heights, world, sim_tick, villagers)
            _update_caravans(caravans, heights, world, villagers, sim_tick)
            if sim_tick % 3 == 0:
                _emit_smoke(smoke_particles, structures, camera_x)
                _update_smoke(smoke_particles)
            if sim_tick % 200 == 0:
                _maybe_fish_jump(fish_jumps, world, heights, day_phase, camera_x)
            _update_fish_jumps(fish_jumps)
            if sim_tick % 500 == 0:
                _maybe_grow_flower(flowers, heights, world, trees, camera_x, weather, current_season=current_season)
            _maybe_spawn_villager(villagers, heights, world, structures, trees, sim_tick)
            _handle_reproduction(villagers, heights, world, structures, sim_tick)
            _handle_villager_aging(villagers, structures, farms=farms)
            _respawn_if_empty(villagers, heights, world, structures)
            _update_structures(structures, villagers)
            _update_rain(rain_drops, weather, heights, world, camera_x)
            _update_lightning(weather, trees, grass_fires, heights, world, camera_x, sim_tick, structures=structures)
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
            _render_sun_moon(pixels, day_phase, elapsed)
            _render_stars(pixels, stars, ambient, sim_tick)
            _render_shooting_stars(pixels, shooting_stars, ambient)
            _render_clouds(pixels, clouds, ambient, camera_x)
            _render_terrain_and_water(pixels, world, heights, ambient, camera_x, path_wear, day_phase, sim_tick, season_info=season_info)
            _render_flowers(pixels, flowers, ambient, camera_x)
            _render_bridges(pixels, structures, ambient, camera_x)
            _render_structures(pixels, structures, ambient, sim_tick, camera_x, day_phase)
            _render_trees(pixels, trees, ambient, sim_tick, camera_x, weather, day_phase, season_info=season_info)
            _render_lumber_items(pixels, lumber_items, ambient, camera_x)
            _render_farms(pixels, farms, ambient, camera_x)
            _render_villagers(pixels, villagers, ambient, sim_tick, camera_x)
            # Render active boats from villagers
            active_boats = [v.boat for v in villagers if v.boat is not None and v.boat.active]
            _render_boats(pixels, active_boats, ambient, camera_x)
            _render_caravans(pixels, caravans, ambient, camera_x)
            _render_animals(pixels, animals, heights, ambient, camera_x)
            _render_birds(pixels, birds, ambient, sim_tick, camera_x)
            _render_fish_jumps(pixels, fish_jumps, camera_x)
            _render_smoke(pixels, smoke_particles, ambient, camera_x)
            _render_fireflies(pixels, fireflies, sim_tick, camera_x)
            _render_rain(pixels, rain_drops, camera_x)
            _update_snow(snow_flakes, heights, world, camera_x, current_season)
            _render_snow(pixels, snow_flakes, camera_x)
            _render_grass_fires(pixels, grass_fires, camera_x)
            _render_torch_posts(pixels, torch_posts, ambient, camera_x)
            _render_lightning(pixels, weather)
            _apply_campfire_light(pixels, structures, ambient, camera_x)
            _apply_lantern_light(pixels, structures, ambient, camera_x)
            _apply_watchtower_light(pixels, structures, ambient, camera_x)
            _apply_torch_post_light(pixels, torch_posts, ambient, camera_x)
            matrix.SetImage(image)
            # --- Live snapshot for web UI (every ~3s) ---
            from .world_api import write_live_snapshot
            write_live_snapshot(
                villagers=villagers, structures=structures, trees=trees,
                farms=farms, animals=animals, heights=heights,
                weather=weather, camera_x=camera_x, sim_tick=sim_tick,
            )
            # --- Check for web UI commands (non-disruptive, throttled) ---
            lw_cmd = None
            if sim_tick % 30 == 0:
                lw_cmd = _check_living_world_command()
            if lw_cmd is not None:
                _apply_living_world_command(lw_cmd, weather, villagers, heights, world, structures, sim_tick, start_time)
            sim_tick += 1
            frame_elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - frame_elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception as e:
        logger.error("Error in living_world: %s", e, exc_info=True)
    finally:
        # --- Save world state for next run ---
        try:
            save_world(
                villagers=villagers, structures=structures, trees=trees,
                farms=farms, heights=heights, world=world, weather=weather,
                clouds=clouds, birds=birds, animals=animals,
                shooting_stars=shooting_stars, fireflies=fireflies,
                smoke_particles=smoke_particles, fish_jumps=fish_jumps,
                flowers=flowers, rain_drops=rain_drops,
                grass_fires=grass_fires, path_wear=path_wear,
                torch_posts=torch_posts, lumber_items=lumber_items,
                stars=stars, camera_x=camera_x, sim_tick=sim_tick,
                start_time=start_time,
            )
        except Exception as save_err:
            logger.warning("Could not save world: %s", save_err)
        try:
            matrix.Clear()
        except Exception:
            pass
