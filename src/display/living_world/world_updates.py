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
    SEASON_TREE_GROWTH, SEASON_FLOWER_CHANCE,
    MAX_DEER, MAX_RABBITS, ANIMAL_SPAWN_INTERVAL,
    ANIMAL_FLEE_RADIUS, ANIMAL_FLEE_DURATION,
    ANIMAL_IDLE_RANGE, ANIMAL_WALK_RANGE,
    SEASON_ANIMAL_CHANCE,
    BIRD_PERCH_CHANCE, BIRD_PERCH_DURATION,
    SHOOTING_STAR_CHANCE, SHOOTING_STAR_SPEED, SHOOTING_STAR_LENGTH,
    CROP_GROWTH_RATE, SEASON_CROP_GROWTH,
    RAIN_CROP_GROWTH_MULTIPLIER, STORM_CROP_GROWTH_MULTIPLIER,
)
from .entities import Tree, Bird, Cloud, Firefly, Smoke, FishJump, Flower, Animal, ShootingStar, Farm, SnowFlake
from .utils import _clamp
from .terrain import _get_valley_cols, _flatten_column_toward, _too_close_to_structure
from .day_night import _compute_ambient

def _grow_trees(trees, heights, world, sim_tick, weather=None, structures=None, current_season=None):
    if structures is None:
        structures = []
    season_mult = SEASON_TREE_GROWTH.get(current_season, 1.0) if current_season else 1.0
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
            # No growth in winter (season_mult == 0.0)
            if season_mult <= 0.0:
                continue
            base_rate = 0.003
            if weather is not None and weather.is_storming():
                rate = base_rate * STORM_GROWTH_MULTIPLIER
            elif weather is not None and weather.is_raining():
                rate = base_rate * RAIN_GROWTH_MULTIPLIER
            else:
                rate = base_rate
            rate *= season_mult
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

def _move_birds(birds, sim_tick, trees=None):
    for b in birds:
        if b.perched:
            b.perch_timer -= 1
            if b.perch_timer <= 0:
                # Take off: resume flying
                b.perched = False
                b.perch_tree = None
                b.direction = random.choice([-1, 1])
                b.base_y = b.y - 2  # launch slightly above perch point
            continue
        b.x += b.speed * b.direction
        b.y = b.screen_y(sim_tick)
        # Check for perching on trees
        if trees is not None and not b.perched:
            _try_perch_bird(b, trees)
    rm = [i for i, b in enumerate(birds) if not b.perched and (b.x < -10 or b.x > WORLD_WIDTH + 10)]
    for i in reversed(rm): birds.pop(i)


def _try_perch_bird(bird, trees):
    """Check if the bird is above a tree canopy and maybe perch."""
    bx = int(bird.x)
    for tree in trees:
        if not tree.alive or tree.on_fire or tree.growth < 0.6:
            continue
        cr = max(0, int(tree.canopy_radius * max(0, (tree.growth - 0.3) / 0.7)))
        if cr <= 0:
            continue
        th = max(1, int(tree.trunk_height * tree.growth))
        canopy_top_y = tree.base_y - 1 - th - cr
        # Bird must be within the canopy x-range and near the top
        if abs(bx - tree.x) <= cr and abs(int(bird.y) - canopy_top_y) <= 2:
            if random.random() < BIRD_PERCH_CHANCE:
                bird.perched = True
                bird.x = float(tree.x)
                bird.y = float(canopy_top_y)
                bird.perch_timer = random.randint(*BIRD_PERCH_DURATION)
                bird.perch_tree = tree
                return

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
    # --- Dense roll-in during rain/storm transitions ---
    # When transitioning into rain or storm, aggressively spawn clouds
    # from the wind direction to create a "rolling wall" effect.
    is_rolling_in = (weather.transition_frames > 0
                     and weather.state in (WEATHER_RAIN, WEATHER_STORM)
                     and weather.prev_state not in (WEATHER_RAIN, WEATHER_STORM))
    if is_rolling_in:
        # Force-spawn up to 3 clouds per tick during roll-in, all from wind dir
        spawns = min(3, tgt - len(clouds))
        for _ in range(max(1, spawns)):
            if len(clouds) >= tgt + 4:
                break  # Allow slight overflow during roll-in
            d = weather.wind_dir
            if weather.state == WEATHER_STORM:
                w = random.randint(*STORM_CLOUD_WIDTH_RANGE)
                h = random.randint(*STORM_CLOUD_HEIGHT_RANGE)
                alpha = STORM_CLOUD_ALPHA
            else:
                w = random.randint(CLOUD_WIDTH_RANGE[1], STORM_CLOUD_WIDTH_RANGE[0])
                h = random.randint(CLOUD_HEIGHT_RANGE[1], STORM_CLOUD_HEIGHT_RANGE[0])
                alpha = CLOUD_ALPHA + 0.05  # slightly darker for rolling in
            x = (camera_x - w - random.randint(0, 10)) if d > 0 else (camera_x + DISPLAY_WIDTH + random.randint(0, 10))
            y = random.randint(1, 8)  # pack clouds low in the sky
            spd = random.uniform(0.06, 0.14)  # faster than normal to "roll in"
            clouds.append(Cloud(x, y, w, h, spd, d, alpha=alpha))
        return

    if len(clouds) >= tgt: return
    if len(clouds) < mn or random.random() < 0.4:
        # During active rain/storm, bias spawn direction to wind_dir (70% chance)
        if weather.state in (WEATHER_RAIN, WEATHER_STORM) and random.random() < 0.7:
            d = weather.wind_dir
        else:
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

def _maybe_grow_flower(flowers, heights, world, trees, camera_x, weather=None, current_season=None):
    # In winter, flowers die off rather than spawn
    if current_season == "winter":
        if flowers and random.random() < 0.1:
            flowers.pop(random.randint(0, len(flowers) - 1))
        return
    if len(flowers) >= 12: return
    season_flower_mult = SEASON_FLOWER_CHANCE.get(current_season, 1.0) if current_season else 1.0
    if season_flower_mult <= 0.0:
        return
    if weather is not None and weather.is_storming():
        threshold = STORM_FLOWER_SPAWN_BOOST
    elif weather is not None and weather.is_raining():
        threshold = RAIN_FLOWER_SPAWN_BOOST
    else:
        threshold = 0.5
    threshold *= season_flower_mult
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


def _maybe_spawn_animal(animals, heights, world, tick, villagers, current_season=None):
    """Spawn deer or rabbits periodically, respecting max counts and season."""
    if tick % ANIMAL_SPAWN_INTERVAL != 0:
        return
    # Season modifier -- fewer animals in autumn/winter
    season_chance = SEASON_ANIMAL_CHANCE.get(current_season, 1.0) if current_season else 1.0
    if season_chance <= 0.0:
        return
    if random.random() > season_chance:
        return
    deer_count = sum(1 for a in animals if a.animal_type == "deer")
    rabbit_count = sum(1 for a in animals if a.animal_type == "rabbit")
    can_deer = deer_count < MAX_DEER
    can_rabbit = rabbit_count < MAX_RABBITS
    if not can_deer and not can_rabbit:
        return
    # Decide type: 50/50 but respect caps
    if can_deer and can_rabbit:
        animal_type = random.choice(["deer", "rabbit"])
    elif can_deer:
        animal_type = "deer"
    else:
        animal_type = "rabbit"
    # Find a valid spawn column far from villagers
    for _ in range(30):
        col = random.randint(4, WORLD_WIDTH - 5)
        sy = heights[col]
        if sy < 0 or sy >= DISPLAY_HEIGHT:
            continue
        if world[sy][col] != GRASS:
            continue
        # Check water in adjacent columns (don't spawn on water edge)
        if col > 0 and world[sy][col - 1] == WATER:
            continue
        if col < WORLD_WIDTH - 1 and world[sy][col + 1] == WATER:
            continue
        # Must be >15px from any villager
        too_close = False
        for v in villagers:
            if abs(v.x - col) < 15:
                too_close = True
                break
        if too_close:
            continue
        direction = random.choice([-1, 1])
        animal = Animal(col, sy, animal_type, direction)
        animal.idle_timer = random.randint(*ANIMAL_IDLE_RANGE)
        animals.append(animal)
        return


def _update_animals(animals, heights, world, villagers, tick):
    """Update animal behavior: idle, walk, flee from villagers."""
    for animal in animals:
        if not animal.alive:
            continue

        # -- Villager proximity check: enter fleeing if not already --
        if animal.state != "fleeing":
            for v in villagers:
                dist = abs(v.x - animal.x)
                if dist < ANIMAL_FLEE_RADIUS:
                    animal.state = "fleeing"
                    # Flee away from the villager
                    animal.direction = -1 if v.x > animal.x else 1
                    animal.flee_timer = ANIMAL_FLEE_DURATION
                    break

        if animal.state == "idle":
            animal.idle_timer -= 1
            if animal.idle_timer <= 0:
                animal.state = "walking"
                animal.direction = random.choice([-1, 1])
                animal.walk_timer = random.randint(*ANIMAL_WALK_RANGE)

        elif animal.state == "walking":
            new_x = animal.x + animal.speed * animal.direction
            ix = int(round(new_x))
            ix = _clamp(ix, 0, WORLD_WIDTH - 1)
            # Boundary check
            if ix <= 0 or ix >= WORLD_WIDTH - 1:
                animal.direction *= -1
                new_x = animal.x + animal.speed * animal.direction
                ix = int(round(new_x))
                ix = _clamp(ix, 0, WORLD_WIDTH - 1)
            # Water avoidance
            sy = heights[ix]
            if 0 <= sy < DISPLAY_HEIGHT and world[sy][ix] == WATER:
                animal.direction *= -1
            else:
                animal.x = float(_clamp(new_x, 0, WORLD_WIDTH - 1))
                animal.y = heights[_clamp(int(round(animal.x)), 0, WORLD_WIDTH - 1)]
            animal.walk_timer -= 1
            if animal.walk_timer <= 0:
                animal.state = "idle"
                animal.idle_timer = random.randint(*ANIMAL_IDLE_RANGE)

        elif animal.state == "fleeing":
            flee_speed = animal.speed * 2.0
            new_x = animal.x + flee_speed * animal.direction
            ix = int(round(new_x))
            ix = _clamp(ix, 0, WORLD_WIDTH - 1)
            # Boundary check
            if ix <= 0 or ix >= WORLD_WIDTH - 1:
                animal.direction *= -1
                new_x = animal.x + flee_speed * animal.direction
                ix = int(round(new_x))
                ix = _clamp(ix, 0, WORLD_WIDTH - 1)
            # Water avoidance -- if water ahead, turn around
            sy = heights[ix]
            if 0 <= sy < DISPLAY_HEIGHT and world[sy][ix] == WATER:
                animal.direction *= -1
            else:
                animal.x = float(_clamp(new_x, 0, WORLD_WIDTH - 1))
                animal.y = heights[_clamp(int(round(animal.x)), 0, WORLD_WIDTH - 1)]
            animal.flee_timer -= 1
            if animal.flee_timer <= 0:
                animal.state = "idle"
                animal.idle_timer = random.randint(*ANIMAL_IDLE_RANGE)

        # Kill off-screen or invalid animals
        ix = _clamp(int(round(animal.x)), 0, WORLD_WIDTH - 1)
        if animal.y < 0 or animal.y >= DISPLAY_HEIGHT:
            animal.alive = False

    # Remove dead animals
    animals[:] = [a for a in animals if a.alive]


def _maybe_spawn_shooting_star(shooting_stars, ambient):
    """Spawn a shooting star at night with low probability."""
    if ambient >= 0.3:
        return  # Only at night
    if len(shooting_stars) >= 1:
        return  # Max one at a time
    if random.random() > SHOOTING_STAR_CHANCE:
        return
    # Spawn at random position in the upper sky
    x = random.randint(5, DISPLAY_WIDTH - 5)
    y = random.randint(2, 15)
    # Diagonal direction: mostly horizontal with slight downward angle
    dx = random.choice([-1, 1]) * SHOOTING_STAR_SPEED
    dy = SHOOTING_STAR_SPEED * 0.4
    shooting_stars.append(ShootingStar(x, y, dx, dy))


def _update_shooting_stars(shooting_stars):
    """Move shooting stars and cull dead ones."""
    for ss in shooting_stars:
        ss.x += ss.dx
        ss.y += ss.dy
        ss.age += 1
        # Kill if off-screen or too old
        if (ss.x < -10 or ss.x > DISPLAY_WIDTH + 10 or
                ss.y < -5 or ss.y > DISPLAY_HEIGHT or ss.age > 30):
            ss.alive = False
    shooting_stars[:] = [s for s in shooting_stars if s.alive]


def _grow_crops(farms, weather=None, current_season=None):
    """Advance crop growth on all farms. Called every FARM_GROWTH_CHECK_INTERVAL ticks."""
    season_mult = SEASON_CROP_GROWTH.get(current_season, 1.0) if current_season else 1.0
    if season_mult <= 0.0:
        return  # No crop growth in winter
    # Weather multiplier
    weather_mult = 1.0
    if weather is not None and weather.is_storming():
        weather_mult = STORM_CROP_GROWTH_MULTIPLIER
    elif weather is not None and weather.is_raining():
        weather_mult = RAIN_CROP_GROWTH_MULTIPLIER
    rate = CROP_GROWTH_RATE * season_mult * weather_mult
    for farm in farms:
        for i in range(farm.width):
            g = farm.crops[i]
            if g < 0:
                continue  # empty slot
            if g >= 1.0:
                continue  # already mature
            farm.crops[i] = min(1.0, g + rate)


def _update_snow(snow_flakes, heights, world, camera_x, current_season):
    """Update snow particles: fall, drift, land on terrain. Only active in winter."""
    if current_season != "winter":
        snow_flakes.clear()
        return
    from .constants import SNOW_FALL_COUNT, SNOW_ACCUMULATION_MAX
    # Move existing flakes
    for sf in snow_flakes:
        if sf.landed:
            continue
        sf.y += sf.speed
        sf.x += sf.drift
        col = _clamp(int(round(sf.x)), 0, WORLD_WIDTH - 1)
        if int(sf.y) >= heights[col]:
            sf.landed = True
            sf.y = float(heights[col])
        elif int(sf.y) >= DISPLAY_HEIGHT:
            sf.landed = True
    # Cull landed/offscreen flakes
    snow_flakes[:] = [sf for sf in snow_flakes if not sf.landed and 0 <= sf.x < WORLD_WIDTH]
    # Spawn new flakes
    count = random.randint(*SNOW_FALL_COUNT)
    active = len(snow_flakes)
    for _ in range(min(3, count - active)):
        sx = random.randint(max(0, camera_x - 5), min(WORLD_WIDTH - 1, camera_x + DISPLAY_WIDTH + 5))
        snow_flakes.append(SnowFlake(sx, random.randint(-3, 3)))


def _maybe_spawn_caravan(caravans, heights, world, sim_tick, villagers):
    """Spawn a trade caravan from off-screen every CARAVAN_SPAWN_INTERVAL ticks."""
    from .constants import CARAVAN_SPAWN_INTERVAL
    from .entities import Caravan
    if len(caravans) >= 1:
        return  # only one caravan at a time
    if sim_tick % CARAVAN_SPAWN_INTERVAL != 0 or sim_tick == 0:
        return
    if len(villagers) < 2:
        return  # need population to trade with
    direction = random.choice([-1, 1])
    if direction == 1:
        start_x = 0
    else:
        start_x = WORLD_WIDTH - 1
    sy = heights[_clamp(start_x, 0, WORLD_WIDTH - 1)]
    caravans.append(Caravan(start_x, sy, direction))
    from .event_log import log_event, CAT_ECONOMY
    log_event(sim_tick, CAT_ECONOMY, "A trade caravan has arrived!")


def _update_caravans(caravans, heights, world, villagers, sim_tick):
    """Move caravans, handle trading, and cleanup."""
    from .constants import (
        CARAVAN_SPEED, CARAVAN_TRADE_DURATION, CARAVAN_TRADE_RADIUS,
        WORLD_WIDTH, WATER,
    )
    from .event_log import log_event, CAT_ECONOMY
    for caravan in caravans:
        if not caravan.alive:
            continue
        col = _clamp(int(round(caravan.x)), 0, WORLD_WIDTH - 1)
        caravan.y = heights[col]

        if caravan.state == "arriving":
            # Walk toward world center
            center = WORLD_WIDTH // 2
            if abs(caravan.x - center) < 20:
                caravan.state = "trading"
                caravan.timer = CARAVAN_TRADE_DURATION
            else:
                caravan.x += caravan.direction * CARAVAN_SPEED
                # Skip water columns
                nc = _clamp(int(round(caravan.x)), 0, WORLD_WIDTH - 1)
                if world[heights[nc]][nc] == WATER:
                    caravan.x -= caravan.direction * CARAVAN_SPEED  # back up

        elif caravan.state == "trading":
            caravan.timer -= 1
            # Check for nearby villagers to trade with
            for v in villagers:
                if abs(int(v.x) - int(round(caravan.x))) <= CARAVAN_TRADE_RADIUS:
                    offer = caravan.offers
                    want_res = offer["want"]
                    want_amt = offer["want_amount"]
                    give_res = offer["give"]
                    give_amt = offer["give_amount"]
                    if getattr(v, want_res, 0) >= want_amt and v.state == "idle":
                        setattr(v, want_res, getattr(v, want_res, 0) - want_amt)
                        setattr(v, give_res, getattr(v, give_res, 0) + give_amt)
                        caravan.trades_completed += 1
                        log_event(sim_tick, CAT_ECONOMY,
                                  f"Caravan traded {give_amt} {give_res} to {v.name} for {want_amt} {want_res}")
                        break  # one trade per tick
            if caravan.timer <= 0:
                caravan.state = "leaving"
                caravan.direction = -caravan.direction  # walk back

        elif caravan.state == "leaving":
            caravan.x += caravan.direction * CARAVAN_SPEED
            if caravan.x < -5 or caravan.x > WORLD_WIDTH + 5:
                caravan.alive = False
                log_event(sim_tick, CAT_ECONOMY,
                          f"Trade caravan departed ({caravan.trades_completed} trades)")

    caravans[:] = [c for c in caravans if c.alive]
