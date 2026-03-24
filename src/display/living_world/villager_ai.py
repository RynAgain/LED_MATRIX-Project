"""All villager behavior: the massive _update_villagers function and its supporting logic."""

import random

from .constants import (
    MAX_VILLAGERS, VILLAGER_SPAWN_INTERVAL,
    VILLAGERS_PER_HOUSE, BASE_VILLAGERS, TREE_BUILDING_MIN_SPACING,
    VILLAGER_MAX_CLIMB, VILLAGER_CLIMB_SPEED,
    CAMPFIRE_REFUEL_AMOUNT, CAMPFIRE_LOW_FUEL_THRESHOLD, CAMPFIRE_MIN_SPACING,
    FLATTEN_DURATION, MINE_DIG_FRAMES, MAX_MINES, MINE_POPULATION_THRESHOLD,
    BRIDGE_BUILD_FRAMES, MAX_BRIDGES,
    HOUSE_TEMPLATES, HOUSE_DIMENSIONS,
    BUBBLE_COLORS, BUBBLE_DURATION,
    WATCHTOWER_COST_LUMBER, WATCHTOWER_COST_STONE, WATCHTOWER_BUILD_FRAMES,
    WATCHTOWER_WIDTH, WATCHTOWER_HEIGHT, WATCHTOWER_POPULATION_THRESHOLD,
    GRANARY_COST_LUMBER, GRANARY_BUILD_FRAMES, GRANARY_WIDTH, GRANARY_HEIGHT,
    GRANARY_POPULATION_THRESHOLD,
    WORLD_WIDTH, DISPLAY_HEIGHT, GRASS, WATER, PATH_DIRT, AIR, DIRT, STONE,
    REPRODUCTION_MIN_AGE, REPRODUCTION_MAX_AGE, REPRODUCTION_CHANCE, MAX_CHILDREN,
    CREMATION_FLASH_FRAMES,
    FIREFIGHT_DETECT_RADIUS, FIREFIGHT_EXTINGUISH_TICKS,
)
from .entities import Villager, Tree, Structure, LumberItem, GrassFire
from .utils import _clamp
from .structures import (
    _find_campfire_site, _find_build_site, _find_mine_site,
    _find_bridge_at, _find_water_gap, _level_foundation,
    _min_campfire_distance, _transfer_house_ownership, _claim_unowned_house,
)
from .terrain import (
    _get_valley_cols, _flatten_terrain, _find_steep_spot,
    _find_extreme_terrain_near_home,
)
from .day_night import _compute_ambient


def _compute_population_cap(structures):
    """Housing-based population cap: BASE_VILLAGERS + houses * VILLAGERS_PER_HOUSE, capped at MAX_VILLAGERS."""
    num_houses = sum(1 for s in structures if s.type in ("house_small", "house_large") and not s.under_construction)
    return min(BASE_VILLAGERS + num_houses * VILLAGERS_PER_HOUSE, MAX_VILLAGERS)

def _too_close_to_structure(x, structures, spacing=TREE_BUILDING_MIN_SPACING):
    """Return True if x is within `spacing` pixels of any structure's footprint."""
    for s in structures:
        if s.x - spacing <= x <= s.x + s.width - 1 + spacing:
            return True
    return False

def _set_bubble(v, task_name):
    color = BUBBLE_COLORS.get(task_name)
    if color is not None:
        v.bubble_timer = BUBBLE_DURATION
        v.bubble_color = color

def _nearest_campfire_x(x, structures):
    best_x = None
    best_dist = 999
    for s in structures:
        if s.type == "campfire" and s.fuel > 0:
            d = abs(s.x - x)
            if d < best_dist:
                best_dist = d
                best_x = s.x
    return best_x

def _get_granary(structures):
    for s in structures:
        if s.type == "granary" and not s.under_construction:
            return s
    return None

def _find_nearest_fire(villager, trees, grass_fires, villagers):
    """Search for burning trees and grass fires within FIREFIGHT_DETECT_RADIUS.

    Returns the nearest fire object (Tree or GrassFire) or None.
    Excludes fires already targeted by another villager.
    """
    vx = int(villager.x)
    targeted = set()
    for other in villagers:
        if other is not villager and other.firefight_target is not None:
            targeted.add(id(other.firefight_target))
    best = None
    best_dist = FIREFIGHT_DETECT_RADIUS + 1
    # Check burning trees
    for t in trees:
        if t.alive and t.on_fire and id(t) not in targeted:
            d = abs(t.x - vx)
            if d <= FIREFIGHT_DETECT_RADIUS and d < best_dist:
                best_dist = d
                best = t
    # Check grass fires
    if grass_fires is not None:
        for gf in grass_fires:
            if id(gf) not in targeted:
                d = abs(gf.x - vx)
                if d <= FIREFIGHT_DETECT_RADIUS and d < best_dist:
                    best_dist = d
                    best = gf
    return best

def _handle_villager_trading(villagers):
    for i,v1 in enumerate(villagers):
        if v1.state == "trading": continue
        for j,v2 in enumerate(villagers):
            if i >= j or v2.state == "trading": continue
            if abs(int(v1.x)-int(v2.x)) <= 2 and abs(v1.y-v2.y) <= 2:
                if v1.lumber >= 3 and v2.lumber == 0:
                    v1.lumber -= 1; v2.lumber += 1
                    v1.state = v2.state = "trading"; v1.task_timer = v2.task_timer = 10; v1.idle_timer = v2.idle_timer = 0
                    _set_bubble(v1, "trading"); _set_bubble(v2, "trading")
                elif v2.lumber >= 3 and v1.lumber == 0:
                    v2.lumber -= 1; v1.lumber += 1
                    v1.state = v2.state = "trading"; v1.task_timer = v2.task_timer = 10; v1.idle_timer = v2.idle_timer = 0
                    _set_bubble(v1, "trading"); _set_bubble(v2, "trading")

def _handle_villager_aging(villagers, structures):
    for v in villagers: v.age += 1
    rm = [i for i,v in enumerate(villagers) if v.age >= v.max_age]
    for i in reversed(rm):
        v = villagers[i]
        if v.home is not None:
            _transfer_house_ownership(v.home, [vv for vi, vv in enumerate(villagers) if vi != i])
        col = int(v.x)
        best = None; bd = 999
        for s in structures:
            if s.type == "campfire" and s.fuel > 0:
                d = abs(s.x-col)
                if d < bd: bd = d; best = s
        if best is not None: best.cremation_flash = CREMATION_FLASH_FRAMES
        villagers.pop(i)

def _respawn_if_empty(villagers, heights, world, structures):
    if len(villagers) > 0: return
    vc = _get_valley_cols(world); sp = 0
    center = WORLD_WIDTH // 2
    for _ in range(50):
        if sp >= 2: break
        col = random.randint(center - 20, center + 20)
        col = _clamp(col, 4, WORLD_WIDTH - 5)
        if col in vc: continue
        sy = heights[col]
        if world[sy][col] == GRASS:
            baby = Villager(col, sy)
            _claim_unowned_house(baby, structures)
            villagers.append(baby)
            sp += 1

def _update_villagers(villagers, heights, world, trees, structures, lumber_items, flowers, path_wear, day_phase, sim_tick, weather=None, grass_fires=None):
    ambient = _compute_ambient(day_phase)
    is_night = ambient < 0.3
    is_bad_weather = weather is not None and weather.is_raining()
    pop = len(villagers)
    max_campfires = max(1, pop//3) if pop > 0 else 0
    max_houses = max(1, pop//3) if pop > 0 else 0
    campfire_count = sum(1 for s in structures if s.type == "campfire")
    mine_count = sum(1 for s in structures if s.type == "mine")
    bridge_count = sum(1 for s in structures if s.type == "bridge")
    watchtower_exists = any(s.type == "watchtower" for s in structures)
    granary_exists = any(s.type == "granary" for s in structures)
    granary = _get_granary(structures)
    _handle_villager_trading(villagers)
    for v in villagers:
        v.idle_timer += 1
        if v.bubble_timer > 0:
            v.bubble_timer -= 1
        # Granary deposit: villager has excess lumber (> 6)
        if granary is not None and v.lumber > 6 and v.state == "idle":
            excess = v.lumber - 4
            granary.stored_lumber += excess
            v.lumber -= excess
        # Granary withdrawal: villager has 0 lumber, granary has stored
        if granary is not None and v.lumber == 0 and granary.stored_lumber > 0 and v.state == "idle":
            withdraw = min(2, granary.stored_lumber)
            v.lumber += withdraw
            granary.stored_lumber -= withdraw
        if v.state == "entering":
            if v.x < v.target_x: v.direction = 1; nx = v.x+1
            elif v.x > v.target_x: v.direction = -1; nx = v.x-1
            else: v.state = "idle"; v.idle_timer = 0; v.entering = False; continue
            nx = _clamp(nx,0,WORLD_WIDTH-1); v.x = nx; v.y = heights[_clamp(int(nx),0,WORLD_WIDTH-1)]
            if int(v.x) == int(v.target_x): v.state = "idle"; v.idle_timer = 0; v.entering = False
            continue
        if v.state == "walking":
            # Consume climbing pause before moving again
            if v.climb_timer > 0:
                v.climb_timer -= 1
                continue
            # --- Fire detection while walking: interrupt to fight fire ---
            fire = _find_nearest_fire(v, trees, grass_fires, villagers)
            if fire is not None:
                v.firefight_target = fire
                fire_x = fire.x
                v.target_x = fire_x
                v.state = "firefighting"
                v.task_timer = 0
                _set_bubble(v, "firefighting")
                # Fall through to firefighting handler below on next tick
                continue
            if v.x < v.target_x: v.direction = 1; nx = v.x+1
            elif v.x > v.target_x: v.direction = -1; nx = v.x-1
            else: v.state = "idle"; v.idle_timer = 0; v.on_bridge = None; continue
            nx = _clamp(nx,1,WORLD_WIDTH-2); nc = int(nx)
            # Bridge-aware walking
            bridge_at_nc = _find_bridge_at(nc, structures)
            bridge_at_cur = _find_bridge_at(int(v.x), structures)
            if bridge_at_nc is not None:
                v.x = nx; v.y = bridge_at_nc.y; v.on_bridge = bridge_at_nc
            elif bridge_at_cur is not None and world[heights[nc]][nc] != WATER:
                v.x = nx; v.y = heights[nc]; v.on_bridge = None
            else:
                height_diff = abs(heights[int(v.x)] - heights[nc])
                if height_diff > VILLAGER_MAX_CLIMB:
                    v.state = "idle"; v.idle_timer = 0; continue
                if world[heights[nc]][nc] == WATER:
                    bridge = _find_bridge_at(nc, structures)
                    if bridge is not None:
                        v.x = nx; v.y = bridge.y; v.on_bridge = bridge
                    else:
                        v.state = "idle"; v.idle_timer = 0; continue
                else:
                    v.x = nx; v.y = heights[nc]; v.on_bridge = None
                    # Apply climbing pause for steep height differences (2-3 blocks)
                    if height_diff >= 2:
                        v.climb_timer = VILLAGER_CLIMB_SPEED
            col = int(v.x)
            if 0 <= col < WORLD_WIDTH: path_wear[col] = min(path_wear[col]+1, 100)
            rm = [fi for fi,f in enumerate(flowers) if f.x == col and f.y == v.y]
            for fi in reversed(rm): flowers.pop(fi)
            if int(v.x) == int(v.target_x): v.state = "idle"; v.idle_timer = 0; v.on_bridge = None
        elif v.state == "firefighting":
            # Validate target still exists and is on fire
            target = v.firefight_target
            if target is None:
                v.state = "idle"; v.idle_timer = 0; continue
            # Check if target is still a valid fire
            target_still_burning = False
            if isinstance(target, Tree):
                target_still_burning = target.alive and target.on_fire
            elif isinstance(target, GrassFire):
                if grass_fires is not None:
                    target_still_burning = target in grass_fires and target.timer > 0
                else:
                    target_still_burning = False
            if not target_still_burning:
                v.firefight_target = None; v.state = "idle"; v.idle_timer = 0; continue
            fire_x = target.x
            dist = abs(int(v.x) - fire_x)
            if dist <= 2:
                # Adjacent to fire: extinguish
                v.task_timer += 1
                _set_bubble(v, "firefighting")
                if v.task_timer >= FIREFIGHT_EXTINGUISH_TICKS:
                    if isinstance(target, Tree):
                        target.on_fire = False
                        target.fire_timer = 0
                    elif isinstance(target, GrassFire):
                        if grass_fires is not None and target in grass_fires:
                            grass_fires.remove(target)
                    v.firefight_target = None; v.state = "idle"; v.idle_timer = 0
            else:
                # Walk toward the fire
                v.target_x = fire_x
                _set_bubble(v, "firefighting")
                if v.x < v.target_x: v.direction = 1; nx = v.x+1
                elif v.x > v.target_x: v.direction = -1; nx = v.x-1
                else: continue
                nx = _clamp(nx,1,WORLD_WIDTH-2); nc = int(nx)
                # Bridge-aware walking (same as walking state)
                bridge_at_nc = _find_bridge_at(nc, structures)
                bridge_at_cur = _find_bridge_at(int(v.x), structures)
                if bridge_at_nc is not None:
                    v.x = nx; v.y = bridge_at_nc.y; v.on_bridge = bridge_at_nc
                elif bridge_at_cur is not None and world[heights[nc]][nc] != WATER:
                    v.x = nx; v.y = heights[nc]; v.on_bridge = None
                else:
                    height_diff = abs(heights[int(v.x)] - heights[nc])
                    if height_diff > VILLAGER_MAX_CLIMB:
                        v.firefight_target = None; v.state = "idle"; v.idle_timer = 0; continue
                    if world[heights[nc]][nc] == WATER:
                        bridge = _find_bridge_at(nc, structures)
                        if bridge is not None:
                            v.x = nx; v.y = bridge.y; v.on_bridge = bridge
                        else:
                            # Can't cross water to reach fire; abandon
                            v.firefight_target = None; v.state = "idle"; v.idle_timer = 0; continue
                    else:
                        v.x = nx; v.y = heights[nc]; v.on_bridge = None
                        if height_diff >= 2:
                            v.climb_timer = VILLAGER_CLIMB_SPEED
                col = int(v.x)
                if 0 <= col < WORLD_WIDTH: path_wear[col] = min(path_wear[col]+1, 100)
        elif v.state == "chopping":
            v.task_timer -= 1
            if v.task_timer <= 0:
                if v.target_tree is not None and v.target_tree.alive:
                    v.target_tree.alive = False; v.target_tree.dead_timer = 0
                    for _ in range(random.randint(2,3)):
                        lx = _clamp(v.target_tree.x+random.randint(-1,1),0,WORLD_WIDTH-1)
                        ly = heights[lx]-1
                        if 0 <= ly < DISPLAY_HEIGHT: lumber_items.append(LumberItem(lx,ly))
                v.target_tree = None; v.state = "idle"; v.idle_timer = 0
        elif v.state == "planting":
            v.task_timer -= 1
            if v.task_timer <= 0:
                col = int(v.x); tt = sum(1 for t in trees if t.alive)
                if tt < 36 and not any(abs(t.x-col)<8 for t in trees if t.alive) and 4<=col<=WORLD_WIDTH-5:
                    if not _too_close_to_structure(col, structures):
                        trees.append(Tree(col,heights[col],0.0,random.randint(5,9),random.randint(2,4),random.randint(0,1)))
                v.state = "idle"; v.idle_timer = 0
        elif v.state == "building":
            v.task_timer -= 1
            if v.building_target is not None and v.build_total_time > 0:
                v.building_target.build_progress = _clamp(1.0-(v.task_timer/v.build_total_time),0.0,1.0)
            if v.task_timer <= 0:
                col = int(v.x)
                if v.build_type == "campfire":
                    if _min_campfire_distance(col,structures) >= CAMPFIRE_MIN_SPACING:
                        structures.append(Structure("campfire",col,heights[col]-1,1,1))
                elif v.build_type == "house_small":
                    if v.building_target is not None: v.building_target.under_construction = False; v.building_target.build_progress = 1.0
                elif v.build_type == "mine":
                    s = Structure("mine",col,heights[col],1,1); s.depth = 0; structures.append(s)
                elif v.build_type == "bridge":
                    gap_info = getattr(v, '_bridge_gap', None)
                    if gap_info is not None:
                        ws, we, wsy = gap_info
                        bw = we - ws + 1
                        by = wsy - 1
                        bs = Structure("bridge", ws, by, bw, 1)
                        structures.append(bs)
                        v._bridge_gap = None
                elif v.build_type == "watchtower":
                    if v.building_target is not None:
                        v.building_target.under_construction = False
                        v.building_target.build_progress = 1.0
                elif v.build_type == "granary":
                    if v.building_target is not None:
                        v.building_target.under_construction = False
                        v.building_target.build_progress = 1.0
                v.build_type = None; v.building_target = None; v.state = "idle"; v.idle_timer = 0
        elif v.state == "upgrading":
            v.task_timer -= 1
            if v.task_timer <= 0:
                if v.upgrade_target is not None and v.upgrade_target.level < 3:
                    ol = v.upgrade_target.level; nl = ol+1
                    ow,oh = HOUSE_DIMENSIONS[ol]; nw,nh = HOUSE_DIMENSIONS[nl]
                    v.upgrade_target.level = nl; v.upgrade_target.width = nw; v.upgrade_target.height = nh
                    v.upgrade_target.x = max(0, v.upgrade_target.x-(nw-ow)//2)
                    v.upgrade_target.y -= (nh-oh)
                    tmpl = HOUSE_TEMPLATES[nl]
                    for _row in tmpl['grid']:
                        for _ci,_ch in enumerate(_row):
                            if _ch == 'D': v.upgrade_target.door_x = v.upgrade_target.x+_ci; break
                        else: continue
                        break
                v.upgrade_target = None; v.state = "idle"; v.idle_timer = 0
        elif v.state == "refueling":
            v.task_timer -= 1
            if v.task_timer <= 0:
                if v.refuel_target is not None and v.lumber >= 1: v.refuel_target.fuel += CAMPFIRE_REFUEL_AMOUNT; v.lumber -= 1
                v.refuel_target = None; v.state = "idle"; v.idle_timer = 0
        elif v.state == "trading":
            v.task_timer -= 1
            if v.task_timer <= 0: v.state = "idle"; v.idle_timer = 0
        elif v.state == "collecting":
            v.task_timer -= 1
            if v.task_timer <= 0:
                col = int(v.x); bd = 999; bi = -1
                for li,it in enumerate(lumber_items):
                    d = abs(it.x-col)
                    if d < bd and d <= 2: bd = d; bi = li
                if bi >= 0: lumber_items.pop(bi); v.lumber += 1
                v.state = "idle"; v.idle_timer = 0
        elif v.state == "resting":
            # Urgent: if no campfires and has lumber, wake up to build one
            if campfire_count == 0 and v.lumber >= 2:
                v.state = "idle"; v.idle_timer = 0
            elif ambient > 0.4 and not is_bad_weather:
                v.state = "idle"; v.idle_timer = 0
        elif v.state == "flattening":
            v.task_timer -= 1
            if v.task_timer <= 0:
                if v.flatten_target is not None: _flatten_terrain(v.flatten_target, heights, world)
                v.flatten_target = None; v.state = "idle"; v.idle_timer = 0
        elif v.state == "mining":
            v.task_timer -= 1
            if v.task_timer <= 0:
                if v.mine_target is not None and v.mine_target.depth < v.mine_target.max_depth:
                    m = v.mine_target; m.depth += 1
                    my = m.y+m.depth
                    if 0<=my<DISPLAY_HEIGHT and 0<=m.x<WORLD_WIDTH: world[my][m.x] = AIR
                    if m.depth % 2 == 0: v.stone += 1
                    if m.depth < m.max_depth: v.task_timer = MINE_DIG_FRAMES
                    else:
                        for cy in range(DISPLAY_HEIGHT):
                            if world[cy][m.x] != AIR:
                                heights[m.x] = cy
                                if world[cy][m.x] not in (WATER,GRASS): world[cy][m.x] = GRASS
                                break
                        v.mine_target = None; v.state = "idle"; v.idle_timer = 0
                else: v.mine_target = None; v.state = "idle"; v.idle_timer = 0
        elif v.state == "idle":
            if v.idle_timer < 20: continue
            # Try to claim an unowned house first if homeless
            if v.home is None:
                _claim_unowned_house(v, structures)
            # --- Fire detection: high priority interrupt from idle ---
            fire = _find_nearest_fire(v, trees, grass_fires, villagers)
            if fire is not None:
                v.firefight_target = fire
                fire_x = fire.x
                v.target_x = fire_x
                v.task_timer = 0
                _set_bubble(v, "firefighting")
                if abs(int(v.x) - fire_x) <= 2:
                    v.state = "firefighting"
                else:
                    v.state = "firefighting"
                continue
            # --- Night behavior: return home unless tasked ---
            if is_night:
                # Urgent: build campfire if none exist
                if campfire_count == 0 and v.lumber >= 2:
                    site = _find_campfire_site(structures,trees,heights,world)
                    if site is not None:
                        v.target_x = site; v.build_type = "campfire"; v.lumber -= 2; v.task_timer = 60
                        _set_bubble(v, "building")
                        v.state = "building" if abs(int(v.x)-site)<=1 else "walking"; continue
                # Go home and rest
                if v.home is not None:
                    if abs(int(v.x)-v.home.x) <= 1:
                        v.state = "resting"; continue
                    else:
                        v.target_x = v.home.x; v.state = "walking"; continue
                else:
                    # No home: walk toward nearest campfire and idle there
                    cf_x = _nearest_campfire_x(int(v.x), structures)
                    if cf_x is not None:
                        if abs(int(v.x)-cf_x) <= 2:
                            v.state = "resting"; continue
                        else:
                            v.target_x = cf_x; v.state = "walking"; continue
                    # No campfire either; just idle in place
                    continue
            if is_bad_weather and v.home is not None:
                v.target_x = v.home.x
                v.state = "resting" if abs(int(v.x)-v.home.x)<=1 else "walking"; continue
            if campfire_count == 0 and v.lumber >= 2:
                site = _find_campfire_site(structures,trees,heights,world)
                if site is not None:
                    v.target_x = site; v.build_type = "campfire"; v.lumber -= 2; v.task_timer = 60
                    _set_bubble(v, "building")
                    v.state = "building" if abs(int(v.x)-site)<=1 else "walking"; continue
            if is_bad_weather:
                col = int(v.x); v.target_x = _clamp(col+random.randint(-6,6),2,WORLD_WIDTH-3); v.state = "walking"; continue
            hc = sum(1 for s in structures if s.type in ("house_small","house_large"))
            if v.lumber >= 4 and v.home is None and hc < max_houses:
                hw,hh = HOUSE_DIMENSIONS[1]
                site = _find_build_site(structures,trees,heights,world,hw,hh)
                if site is not None:
                    sx,sy = site; s = Structure("house_small",sx,sy,hw,hh)
                    _level_foundation(sx, hw, heights, world, v, structures)
                    sy = heights[sx] - hh
                    s.y = sy
                    s.under_construction = True; s.build_progress = 0.0; s.owner = v
                    if v.stone >= 2: s.stone_built = True; v.stone -= 2
                    for _r in HOUSE_TEMPLATES[1]['grid']:
                        for _ci,_ch in enumerate(_r):
                            if _ch=='D': s.door_x = sx+_ci; break
                        else: continue
                        break
                    v.home = s; structures.append(s); v.target_x = sx; v.build_type = "house_small"
                    v.building_target = s; v.lumber -= 4; v.build_total_time = 120; v.task_timer = 120
                    _set_bubble(v, "building")
                    v.state = "building" if abs(int(v.x)-sx)<=1 else "walking"; continue
                else:
                    steep = _find_steep_spot(heights,world,near_x=int(v.x),radius=15)
                    if steep is not None:
                        v.flatten_target = steep; v.target_x = steep; v.task_timer = FLATTEN_DURATION
                        v.state = "flattening" if abs(int(v.x)-steep)<=1 else "walking"; continue
            if v.lumber >= 2 and campfire_count < max_campfires:
                if v.home is None or campfire_count == 0:
                    site = _find_campfire_site(structures,trees,heights,world)
                    if site is not None:
                        v.target_x = site; v.build_type = "campfire"; v.lumber -= 2; v.task_timer = 60
                        _set_bubble(v, "building")
                        v.state = "building" if abs(int(v.x)-site)<=1 else "walking"; continue
            # Granary build trigger
            if not granary_exists and pop >= GRANARY_POPULATION_THRESHOLD and v.lumber >= GRANARY_COST_LUMBER:
                site = _find_build_site(structures, trees, heights, world, GRANARY_WIDTH, GRANARY_HEIGHT)
                if site is not None:
                    sx, sy = site
                    _level_foundation(sx, GRANARY_WIDTH, heights, world, v, structures)
                    sy = heights[sx] - GRANARY_HEIGHT
                    s = Structure("granary", sx, sy, GRANARY_WIDTH, GRANARY_HEIGHT)
                    s.under_construction = True; s.build_progress = 0.0
                    structures.append(s); v.target_x = sx; v.build_type = "granary"
                    v.building_target = s; v.lumber -= GRANARY_COST_LUMBER
                    v.build_total_time = GRANARY_BUILD_FRAMES; v.task_timer = GRANARY_BUILD_FRAMES
                    _set_bubble(v, "building")
                    v.state = "building" if abs(int(v.x) - sx) <= 1 else "walking"; continue
            # Watchtower build trigger
            if not watchtower_exists and pop >= WATCHTOWER_POPULATION_THRESHOLD and v.lumber >= WATCHTOWER_COST_LUMBER and v.stone >= WATCHTOWER_COST_STONE:
                site = _find_build_site(structures, trees, heights, world, WATCHTOWER_WIDTH, WATCHTOWER_HEIGHT)
                if site is not None:
                    sx, sy = site
                    _level_foundation(sx, WATCHTOWER_WIDTH, heights, world, v, structures)
                    sy = heights[sx] - WATCHTOWER_HEIGHT
                    s = Structure("watchtower", sx, sy, WATCHTOWER_WIDTH, WATCHTOWER_HEIGHT)
                    s.under_construction = True; s.build_progress = 0.0
                    structures.append(s); v.target_x = sx; v.build_type = "watchtower"
                    v.building_target = s; v.lumber -= WATCHTOWER_COST_LUMBER; v.stone -= WATCHTOWER_COST_STONE
                    v.build_total_time = WATCHTOWER_BUILD_FRAMES; v.task_timer = WATCHTOWER_BUILD_FRAMES
                    _set_bubble(v, "building")
                    v.state = "building" if abs(int(v.x) - sx) <= 1 else "walking"; continue
            # Bridge build trigger
            if bridge_count < MAX_BRIDGES and v.lumber >= 2:
                col = int(v.x)
                _started_bridge = False
                for bd in (1, -1):
                    nc = col + bd
                    if 0 <= nc < WORLD_WIDTH and world[heights[nc]][nc] == WATER:
                        gap = _find_water_gap(world, heights, nc, bd)
                        if gap is not None:
                            ws, we, wsy = gap
                            gw = we - ws + 1
                            cost = 2 if gw <= 6 else 3
                            if v.lumber >= cost:
                                v.lumber -= cost; v._bridge_gap = gap
                                v.target_x = ws; v.build_type = "bridge"
                                v.build_total_time = BRIDGE_BUILD_FRAMES; v.task_timer = BRIDGE_BUILD_FRAMES
                                _set_bubble(v, "building")
                                v.state = "building" if abs(col - ws) <= 1 else "walking"
                                _started_bridge = True; break
                if _started_bridge: continue
            if v.home is not None and v.home.level < 3 and v.lumber >= 6 and v.stone >= 2:
                v.upgrade_target = v.home; v.target_x = v.home.x
                v.lumber -= 6; v.stone -= 2; v.task_timer = 120
                _set_bubble(v, "building")
                v.state = "upgrading" if abs(int(v.x) - v.home.x) <= 1 else "walking"; continue
            if pop >= MINE_POPULATION_THRESHOLD and mine_count < MAX_MINES and v.lumber >= 2:
                mc = _find_mine_site(structures, trees, heights, world, int(v.x))
                if mc is not None:
                    v.target_x = mc; v.build_type = "mine"; v.lumber -= 2; v.task_timer = MINE_DIG_FRAMES
                    _set_bubble(v, "mining")
                    v.state = "mining" if abs(int(v.x) - mc) <= 1 else "walking"; continue
            _did_refuel = False
            for s in structures:
                if s.type == "campfire" and s.fuel < CAMPFIRE_LOW_FUEL_THRESHOLD and v.lumber >= 1:
                    v.refuel_target = s; v.target_x = s.x
                    v.state = "refueling" if abs(int(v.x) - s.x) <= 1 else "walking"
                    v.task_timer = 20; _did_refuel = True; break
            if _did_refuel: continue
            mt = [t for t in trees if t.alive and t.growth >= 1.0 and not t.dying and not t.on_fire and abs(t.x - int(v.x)) < 30]
            if mt and v.lumber < 6:
                tt = min(mt, key=lambda t: abs(t.x - int(v.x)))
                v.target_tree = tt; v.target_x = tt.x - 1 if tt.x > int(v.x) else tt.x + 1
                v.task_timer = 60
                _set_bubble(v, "chopping")
                v.state = "chopping" if abs(int(v.x) - tt.x) <= 1 else "walking"; continue
            if v.lumber >= 1 and random.random() < 0.3:
                col = int(v.x); nt = sum(1 for t in trees if t.alive and abs(t.x - col) < 10)
                if nt < 2:
                    v.task_timer = 30
                    _set_bubble(v, "planting")
                    v.state = "planting"; continue
            li_near = [li for li, it in enumerate(lumber_items) if abs(it.x - int(v.x)) < 15]
            if li_near:
                bi = min(li_near, key=lambda i: abs(lumber_items[i].x - int(v.x)))
                v.target_x = lumber_items[bi].x; v.task_timer = 10
                v.state = "collecting" if abs(int(v.x) - lumber_items[bi].x) <= 1 else "walking"; continue
            steep = _find_steep_spot(heights, world, near_x=int(v.x), radius=12)
            if steep is not None and random.random() < 0.4:
                v.flatten_target = steep; v.target_x = steep; v.task_timer = FLATTEN_DURATION
                v.state = "flattening" if abs(int(v.x) - steep) <= 1 else "walking"; continue
            extreme = _find_extreme_terrain_near_home(v, heights, world)
            if extreme is not None:
                v.flatten_target = extreme; v.target_x = extreme; v.task_timer = FLATTEN_DURATION
                v.state = "flattening" if abs(int(v.x) - extreme) <= 1 else "walking"; continue
            col = int(v.x)
            v.target_x = _clamp(col + random.randint(-12, 12), 2, WORLD_WIDTH - 3)
            v.state = "walking"

def _maybe_spawn_villager(villagers, heights, world, structures, trees, sim_tick):
    pop_cap = _compute_population_cap(structures)
    if len(villagers) >= pop_cap: return
    if sim_tick % VILLAGER_SPAWN_INTERVAL != 0 or sim_tick == 0: return
    vc = _get_valley_cols(world)
    for _ in range(30):
        col = random.randint(8, WORLD_WIDTH - 9)
        if col in vc: continue
        sy = heights[col]
        if 0 <= sy < DISPLAY_HEIGHT and world[sy][col] == GRASS:
            baby = Villager(col, sy)
            _claim_unowned_house(baby, structures)
            villagers.append(baby)
            return

def _handle_reproduction(villagers, heights, world, structures, sim_tick):
    pop_cap = _compute_population_cap(structures)
    if len(villagers) >= pop_cap: return
    if sim_tick % 90 != 0: return
    vc = _get_valley_cols(world)
    for v in villagers:
        if v.age < REPRODUCTION_MIN_AGE or v.age > REPRODUCTION_MAX_AGE: continue
        if v.children_born >= MAX_CHILDREN: continue
        if random.randint(0, REPRODUCTION_CHANCE) != 0: continue
        if v.home is None: continue
        col = _clamp(int(v.x) + random.choice([-1, 0, 1]), 2, WORLD_WIDTH - 3)
        if col in vc: continue
        sy = heights[col]
        if 0 <= sy < DISPLAY_HEIGHT and world[sy][col] in (GRASS, PATH_DIRT):
            baby = Villager(col, sy)
            _claim_unowned_house(baby, structures)
            villagers.append(baby)
            v.children_born += 1
            return
