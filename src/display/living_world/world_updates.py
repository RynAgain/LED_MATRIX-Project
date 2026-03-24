"""Non-villager entity updates: trees, clouds, birds, ambient life."""

import random
import math

from .constants import (
    WORLD_WIDTH, DISPLAY_WIDTH, DISPLAY_HEIGHT, WATER, GRASS,
    WEATHER_RAIN, WEATHER_STORM, WEATHER_CLOUD_PARAMS,
    FLOWER_COLORS, HOUSE_TEMPLATES,
    MAX_TORCH_POSTS, TORCH_POST_PATH_THRESHOLD, TORCH_POST_CHECK_INTERVAL,
    RAIN_GROWTH_MULTIPLIER, STORM_GROWTH_MULTIPLIER,
    RAIN_FLOWER_SPAWN_BOOST, STORM_FLOWER_SPAWN_BOOST,
    CLOUD_WIDTH_RANGE, CLOUD_HEIGHT_RANGE,
    STORM_CLOUD_WIDTH_RANGE, STORM_CLOUD_HEIGHT_RANGE,
    CLOUD_ALPHA, STORM_CLOUD_ALPHA,
    TREE_BUILDING_MIN_SPACING,
    HOUSE_FLATTEN_RADIUS, HOUSE_FLATTEN_INTERVAL, HOUSE_FLATTEN_RATE,
)
from .entities import Tree, Bird, Cloud, Firefly, Smoke, FishJump, Flower
from .utils import _clamp
from .terrain import _get_valley_cols, _flatten_column_toward
from .day_night import _compute_ambient


def _too_close_to_structure(x, structures, spacing=TREE_BUILDING_MIN_SPACING):
    """Return True if x is within `spacing` pixels of any structure's footprint."""
    for s in structures:
        if s.x - spacing <= x <= s.x + s.width - 1 + spacing:
            return True
    return False

def _grow_trees(trees, heights, world, sim_tick, weather=None, structures=None):
    if structures is None:
        structures = []
    for tree in trees:
        if not tree.alive: tree.dead_timer += 1; continue
        if tree.on_fire:
            tree.fire_timer -= 1
            if tree.fire_timer <= 0: tree.alive = False; tree.on_fire = False; tree.dead_timer = 0
            continue
        if tree.dying:
            tree.dying_progress += 0.004
            if tree.dying_progress >= 1.0: tree.alive = False; tree.dead_timer = 0
            continue
        if tree.growth < 1.0:
            # If a structure was built nearby since planting, kill the sapling
            if _too_close_to_structure(tree.x, structures):
                tree.alive = False; tree.dead_timer = 0; continue
            base_rate = 0.003
            if weather is not None and weather.is_storming():
                rate = base_rate * STORM_GROWTH_MULTIPLIER
            elif weather is not None and weather.is_raining():
                rate = base_rate * RAIN_GROWTH_MULTIPLIER
            else:
                rate = base_rate
            tree.growth = min(1.0, tree.growth + rate)
        else:
            tree.mature_timer += 1
            if tree.mature_timer > random.randint(324,540): tree.dying = True
    if sum(1 for t in trees if t.alive) >= 24: return
    vc = _get_valley_cols(world)
    for i, tree in enumerate(trees):
        if not tree.alive and tree.dead_timer > 108:
            nx = random.randint(4, WORLD_WIDTH-5); att = 0
            while att < 20:
                if nx not in vc and not any(o is not tree and o.alive and abs(o.x-nx)<8 for o in trees):
                    if not _too_close_to_structure(nx, structures):
                        break
                nx = random.randint(4, WORLD_WIDTH-5); att += 1
            if att < 20:
                trees[i] = Tree(nx, heights[nx], 0.0, random.randint(5,9), random.randint(2,4), random.randint(0,1))

def _move_clouds(clouds, weather):
    sm = 2.0 if weather.is_storming() else (1.5 if weather.is_raining() else 1.0)
    for c in clouds: c.x += c.speed * c.direction * sm
    rm = [i for i,c in enumerate(clouds) if (c.direction>0 and c.x>WORLD_WIDTH+20) or (c.direction<0 and c.x+c.width<-20)]
    for i in reversed(rm): clouds.pop(i)

def _move_birds(birds, sim_tick):
    for b in birds: b.x += b.speed*b.direction; b.y = b.screen_y(sim_tick)
    rm = [i for i,b in enumerate(birds) if b.x<-10 or b.x>WORLD_WIDTH+10]
    for i in reversed(rm): birds.pop(i)

def _animate_bird_wings(birds):
    for b in birds: b.wing_frame = 1 - b.wing_frame

def _maybe_spawn_bird(birds, day_phase, weather, camera_x):
    if weather.is_storming(): return
    amb = _compute_ambient(day_phase)
    if amb < 0.4: return
    mx = 3 if amb > 0.7 else 1
    if len(birds) >= mx: return
    if random.random() < 0.5:
        d = random.choice([-1,1])
        spawn_x = float(camera_x - 3) if d > 0 else float(camera_x + DISPLAY_WIDTH + 3)
        birds.append(Bird(spawn_x, random.uniform(5,22), d, random.uniform(0.3,0.7), random.uniform(0,2*math.pi)))

def _maybe_spawn_cloud(clouds, weather, camera_x):
    mn,mx,_,wider = WEATHER_CLOUD_PARAMS[weather.state]
    tgt = random.randint(mn,mx)
    if len(clouds) >= tgt: return
    if len(clouds) < mn or random.random() < 0.4:
        d = random.choice([-1,1])
        if weather.state == WEATHER_STORM:
            w = random.randint(*STORM_CLOUD_WIDTH_RANGE)
            h = random.randint(*STORM_CLOUD_HEIGHT_RANGE)
            alpha = STORM_CLOUD_ALPHA
        elif weather.state == WEATHER_RAIN:
            w = random.randint(CLOUD_WIDTH_RANGE[1], STORM_CLOUD_WIDTH_RANGE[0])
            h = random.randint(CLOUD_HEIGHT_RANGE[1], STORM_CLOUD_HEIGHT_RANGE[0])
            alpha = CLOUD_ALPHA
        else:
            w = random.randint(*CLOUD_WIDTH_RANGE)
            h = random.randint(*CLOUD_HEIGHT_RANGE)
            alpha = CLOUD_ALPHA
        x = (camera_x - w - random.randint(0,20)) if d>0 else (camera_x + DISPLAY_WIDTH + random.randint(0,20))
        y = random.randint(2,10) if weather.state in (WEATHER_RAIN,WEATHER_STORM) else random.randint(3,14)
        clouds.append(Cloud(x,y,w,h,random.uniform(0.02,0.08),d,alpha=alpha))

def _update_fireflies(fireflies, day_phase, heights, trees, camera_x):
    ambient = _compute_ambient(day_phase)
    for ff in fireflies:
        ff.x += random.uniform(-0.3, 0.3)
        ff.y += random.uniform(-0.3, 0.3)
        ff.x = _clamp(ff.x, 0, WORLD_WIDTH - 1)
        ff.y = _clamp(ff.y, 5, DISPLAY_HEIGHT - 10)
        ff.age += 1
    fireflies[:] = [f for f in fireflies if f.age < f.lifetime]
    if ambient < 0.4 and len(fireflies) < 10:
        if random.random() < 0.15:
            fx = random.randint(max(0, camera_x), min(camera_x + DISPLAY_WIDTH, WORLD_WIDTH - 1))
            col = _clamp(fx, 0, WORLD_WIDTH - 1)
            fy = random.uniform(heights[col] - 10, heights[col] - 3)
            fireflies.append(Firefly(fx, max(3, fy), random.uniform(0, 2 * math.pi)))

def _emit_smoke(smoke_particles, structures, camera_x):
    for s in structures:
        if s.type == "campfire" and s.fuel > 0:
            if random.random() < 0.12:
                smoke_particles.append(Smoke(s.x, s.y - 1))
        elif s.type in ("house_small", "house_large") and s.level >= 2 and not s.under_construction:
            if random.random() < 0.04:
                tmpl = HOUSE_TEMPLATES.get(s.level)
                if tmpl:
                    for ci, ch in enumerate(tmpl['grid'][0]):
                        if ch == 'C':
                            smoke_particles.append(Smoke(s.x + ci, s.y - 1))
                            break

def _update_smoke(smoke_particles):
    for sp in smoke_particles:
        sp.y -= 0.15
        sp.x += sp.dx
        sp.age += 1
    smoke_particles[:] = [s for s in smoke_particles if s.age < s.max_age]

def _maybe_fish_jump(fish_jumps, world, heights, day_phase, camera_x):
    if _compute_ambient(day_phase) < 0.5: return
    if len(fish_jumps) >= 1: return
    water_cols = []
    for x in range(max(0, camera_x), min(WORLD_WIDTH, camera_x + DISPLAY_WIDTH)):
        for y in range(DISPLAY_HEIGHT):
            if world[y][x] == WATER and (y == 0 or world[y - 1][x] != WATER):
                water_cols.append((x, y))
                break
    if water_cols and random.random() < 0.3:
        wx, wy = random.choice(water_cols)
        fish_jumps.append(FishJump(wx, wy, random.randint(2, 3)))

def _update_fish_jumps(fish_jumps):
    for fj in fish_jumps:
        fj.progress += 1
    fish_jumps[:] = [f for f in fish_jumps if f.progress <= 16]

def _maybe_grow_flower(flowers, heights, world, trees, camera_x, weather=None):
    if len(flowers) >= 12: return
    if weather is not None and weather.is_storming():
        threshold = STORM_FLOWER_SPAWN_BOOST
    elif weather is not None and weather.is_raining():
        threshold = RAIN_FLOWER_SPAWN_BOOST
    else:
        threshold = 0.5
    if random.random() > threshold:
        return
    for _ in range(10):
        x = random.randint(4, WORLD_WIDTH - 5)
        sy = heights[x]
        if 0 <= sy < DISPLAY_HEIGHT and world[sy][x] == GRASS:
            if not any(f.x == x for f in flowers):
                if not any(t.alive and abs(t.x - x) < 2 for t in trees):
                    flowers.append(Flower(x, sy, random.choice(FLOWER_COLORS)))
                    return

def _update_torch_posts(torch_posts, path_wear, heights, structures, sim_tick):
    if sim_tick % TORCH_POST_CHECK_INTERVAL != 0: return
    if len(torch_posts) >= MAX_TORCH_POSTS: return
    cands = []
    for x in range(WORLD_WIDTH):
        if path_wear[x] >= TORCH_POST_PATH_THRESHOLD:
            if not any(abs(tx - x) < 5 for tx, ty in torch_posts):
                if not any(abs(s.x - x) < 2 for s in structures):
                    cands.append(x)
    if cands:
        x = random.choice(cands)
        sy = heights[x]
        torch_posts.append((x, sy - 1))


def _flatten_around_houses(structures, heights, world, villagers, sim_tick, day_phase):
    """Periodically flatten terrain in a wider area around completed houses.

    House owners, when idle during daytime, gradually level surrounding terrain
    to the house's ground level -- creating flat ground for future farms and
    additional buildings.  Only a few columns are processed per invocation to
    keep the per-tick cost low.
    """
    if sim_tick % HOUSE_FLATTEN_INTERVAL != 0:
        return
    ambient = _compute_ambient(day_phase)
    if ambient < 0.3:
        return  # night-time -- villagers rest

    vc = _get_valley_cols(world)
    max_cols_per_house = 3  # efficiency cap per house per invocation

    for s in structures:
        if s.type not in ("house_small", "house_large"):
            continue
        if s.under_construction:
            continue
        if s.owner is None:
            continue
        # Owner must be idle to perform the work
        if s.owner.state != "idle":
            continue

        target_y = s.y + s.height  # ground level at house base
        flatten_left = max(0, s.x - HOUSE_FLATTEN_RADIUS)
        flatten_right = min(WORLD_WIDTH - 1, s.x + s.width - 1 + HOUSE_FLATTEN_RADIUS)

        cols = list(range(flatten_left, flatten_right + 1))
        random.shuffle(cols)
        cols_processed = 0

        for col in cols:
            if col in vc:
                continue  # skip water-adjacent columns
            if abs(heights[col] - target_y) <= 1:
                continue  # already close enough
            if _flatten_column_toward(world, heights, col, target_y, HOUSE_FLATTEN_RATE):
                cols_processed += 1
                if cols_processed >= max_cols_per_house:
                    break


