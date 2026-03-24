"""Weather state machine and weather-driven world effects."""

import random

from .constants import (
    WEATHER_CLEAR, WEATHER_CLOUDY, WEATHER_RAIN, WEATHER_STORM,
    WEATHER_DURATION, WEATHER_TRANSITION_FRAMES, WIND_SWAY_INTERVAL,
    RAIN_COUNT_RAIN, RAIN_COUNT_STORM,
    LIGHTNING_CHANCE, LIGHTNING_FLASH_FRAMES, LIGHTNING_BOLT_FRAMES,
    LIGHTNING_TREE_FIRE_CHANCE, LIGHTNING_GRASS_FIRE_CHANCE,
    TREE_FIRE_DURATION,
    WATER_RISE_RAIN_INTERVAL, WATER_RISE_STORM_INTERVAL, WATER_RECEDE_INTERVAL,
    WORLD_WIDTH, DISPLAY_WIDTH, DISPLAY_HEIGHT, AIR, WATER, GRASS,
)
from .entities import RainDrop, GrassFire
from .utils import _clamp


def _update_weather(weather, sim_tick):
    weather.timer -= 1
    if weather.timer <= 0:
        transitions = {
            WEATHER_CLEAR: [WEATHER_CLOUDY],
            WEATHER_CLOUDY: [WEATHER_CLEAR, WEATHER_RAIN],
            WEATHER_RAIN: [WEATHER_CLOUDY, WEATHER_STORM],
            WEATHER_STORM: [WEATHER_RAIN],
        }
        choices = transitions.get(weather.state, [WEATHER_CLEAR])
        weather.prev_state = weather.state
        weather.state = random.choice(choices)
        weather.timer = random.randint(*WEATHER_DURATION[weather.state])
        weather.transition_frames = WEATHER_TRANSITION_FRAMES
    if weather.transition_frames > 0:
        weather.transition_frames -= 1
    tgt = weather.target_storm_factor()
    if weather.storm_factor < tgt:
        weather.storm_factor = min(tgt, weather.storm_factor + 0.02)
    elif weather.storm_factor > tgt:
        weather.storm_factor = max(tgt, weather.storm_factor - 0.02)
    weather.sway_timer += 1
    if weather.sway_timer >= WIND_SWAY_INTERVAL:
        weather.sway_timer = 0
        if weather.is_storming():
            weather.tree_sway_offset = random.choice([-1, 0, 1])
        elif weather.is_raining():
            weather.tree_sway_offset = random.choice([0, 0, 1]) if weather.wind_dir > 0 else random.choice([0, 0, -1])
        else:
            weather.tree_sway_offset = 0

def _update_rain(rain_drops, weather, heights, world, camera_x):
    if not weather.is_raining():
        rain_drops.clear()
        return
    to_remove = []
    for idx, rd in enumerate(rain_drops):
        if rd.splash:
            rd.speed -= 1
            if rd.speed <= 0:
                to_remove.append(idx)
            continue
        rd.y += rd.speed
        rd.x += weather.wind_dir * 0.3
        col = _clamp(int(rd.x), 0, WORLD_WIDTH - 1)
        if int(rd.y) >= heights[col] or int(rd.y) >= DISPLAY_HEIGHT:
            rd.splash = True
            rd.splash_x = rd.x
            rd.splash_y = min(heights[col], DISPLAY_HEIGHT - 1)
            rd.speed = 3
    for idx in reversed(to_remove):
        rain_drops.pop(idx)
    ct = RAIN_COUNT_STORM if weather.is_storming() else RAIN_COUNT_RAIN
    target = random.randint(*ct)
    active = sum(1 for r in rain_drops if not r.splash)
    for _ in range(min(3, target - active)):
        rx = random.randint(camera_x, camera_x + DISPLAY_WIDTH)
        rain_drops.append(RainDrop(rx, random.randint(-5, 5)))

def _update_lightning(weather, trees, grass_fires, heights, world, camera_x, sim_tick):
    if weather.lightning_flash > 0:
        weather.lightning_flash -= 1
    if weather.lightning_bolt_timer > 0:
        weather.lightning_bolt_timer -= 1
        if weather.lightning_bolt_timer <= 0:
            weather.lightning_bolt = None
    if not weather.is_storming(): return
    if random.randint(0, LIGHTNING_CHANCE) == 0:
        weather.lightning_flash = LIGHTNING_FLASH_FRAMES
        bx = random.randint(0, DISPLAY_WIDTH - 1)
        weather.lightning_bolt = (bx, 0, random.randint(20, 40))
        weather.lightning_bolt_timer = LIGHTNING_BOLT_FRAMES
        wx = bx + camera_x
        if 0 <= wx < WORLD_WIDTH:
            for t in trees:
                if t.alive and not t.on_fire and abs(t.x - wx) <= 2:
                    if random.random() < LIGHTNING_TREE_FIRE_CHANCE:
                        t.on_fire = True; t.fire_timer = TREE_FIRE_DURATION; break
            sy = heights[wx]
            if 0 <= sy < DISPLAY_HEIGHT and world[sy][wx] == GRASS:
                if random.random() < LIGHTNING_GRASS_FIRE_CHANCE:
                    grass_fires.append(GrassFire(wx, sy, TREE_FIRE_DURATION))

def _update_grass_fires(grass_fires):
    for gf in grass_fires:
        gf.timer -= 1
    grass_fires[:] = [g for g in grass_fires if g.timer > 0]

def _update_water_levels(world, heights, weather, sim_tick):
    if weather.is_storming() and sim_tick % WATER_RISE_STORM_INTERVAL == 0:
        for x in range(WORLD_WIDTH):
            for y in range(DISPLAY_HEIGHT - 1, -1, -1):
                if world[y][x] == WATER:
                    if y - 1 >= 0 and world[y - 1][x] == AIR:
                        if random.random() < 0.02:
                            world[y - 1][x] = WATER
                    break
    elif weather.is_raining() and sim_tick % WATER_RISE_RAIN_INTERVAL == 0:
        for x in range(WORLD_WIDTH):
            for y in range(DISPLAY_HEIGHT - 1, -1, -1):
                if world[y][x] == WATER:
                    if y - 1 >= 0 and world[y - 1][x] == AIR:
                        if random.random() < 0.005:
                            world[y - 1][x] = WATER
                    break
    elif not weather.is_raining() and sim_tick % WATER_RECEDE_INTERVAL == 0:
        for x in range(WORLD_WIDTH):
            for y in range(DISPLAY_HEIGHT):
                if world[y][x] == WATER:
                    if y == 0 or world[y - 1][x] == AIR:
                        if y + 1 < DISPLAY_HEIGHT and world[y + 1][x] == WATER:
                            if random.random() < 0.01:
                                world[y][x] = AIR
                    break
