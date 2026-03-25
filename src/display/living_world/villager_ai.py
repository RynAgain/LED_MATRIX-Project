"""All villager behavior: the massive _update_villagers function and its supporting logic."""

import random

from .event_log import log_event, CAT_VILLAGER, CAT_BUILDING, CAT_ECONOMY, CAT_DEATH, CAT_BIRTH, CAT_COMBAT
from .constants import (
    MAX_VILLAGERS, VILLAGER_SPAWN_INTERVAL,
    VILLAGERS_PER_HOUSE, BASE_VILLAGERS, TREE_BUILDING_MIN_SPACING,
    VILLAGER_MAX_CLIMB, VILLAGER_CLIMB_SPEED,
    VILLAGER_CHOP_THRESHOLD, VILLAGER_EXPLORE_CHANCE, VILLAGER_PLANT_CHANCE,
    CAMPFIRE_REFUEL_AMOUNT, CAMPFIRE_LOW_FUEL_THRESHOLD, CAMPFIRE_MIN_SPACING,
    FLATTEN_DURATION, MINE_DIG_FRAMES, MAX_MINES, MINE_POPULATION_THRESHOLD,
    BRIDGE_BUILD_FRAMES, MAX_BRIDGES,
    MAX_WELLS, WELL_BUILD_FRAMES, WELL_WIDTH, WELL_HEIGHT, WELL_POPULATION_THRESHOLD,
    WELL_COST_LUMBER, WELL_COST_STONE,
    CASTLE_COST_LUMBER, CASTLE_COST_STONE, CASTLE_BUILD_FRAMES,
    CASTLE_WIDTH, CASTLE_HEIGHT, CASTLE_POPULATION_THRESHOLD, MAX_CASTLES,
    HOUSE_TEMPLATES, HOUSE_DIMENSIONS,
    BUBBLE_COLORS, BUBBLE_DURATION,
    WATCHTOWER_COST_LUMBER, WATCHTOWER_COST_STONE, WATCHTOWER_BUILD_FRAMES,
    WATCHTOWER_WIDTH, WATCHTOWER_HEIGHT, WATCHTOWER_POPULATION_THRESHOLD,
    GRANARY_COST_LUMBER, GRANARY_BUILD_FRAMES, GRANARY_WIDTH, GRANARY_HEIGHT,
    GRANARY_POPULATION_THRESHOLD,
    STORAGE_COST_LUMBER, STORAGE_COST_STONE, STORAGE_BUILD_FRAMES,
    STORAGE_WIDTH, STORAGE_HEIGHT, STORAGE_POPULATION_THRESHOLD, MAX_STORAGES,
    STORAGE_MAX_LUMBER, STORAGE_MAX_STONE, STORAGE_MAX_FOOD,
    STORAGE_DEPOSIT_THRESHOLD_LUMBER, STORAGE_DEPOSIT_THRESHOLD_STONE, STORAGE_DEPOSIT_THRESHOLD_FOOD,
    BANK_COST_LUMBER, BANK_COST_STONE, BANK_BUILD_FRAMES,
    BANK_WIDTH, BANK_HEIGHT, BANK_POPULATION_THRESHOLD, MAX_BANKS,
    GOLD_MINE_CHANCE,
    BOAT_COST_LUMBER,
    WORLD_WIDTH, DISPLAY_HEIGHT, GRASS, WATER, PATH_DIRT, AIR, DIRT, STONE,
    REPRODUCTION_MIN_AGE, REPRODUCTION_MAX_AGE, REPRODUCTION_CHANCE, MAX_CHILDREN,
    CREMATION_FLASH_FRAMES,
    FIREFIGHT_DETECT_RADIUS, FIREFIGHT_EXTINGUISH_TICKS,
    FARM_COST_LUMBER, FARM_BUILD_FRAMES, FARM_POPULATION_THRESHOLD,
    MAX_FARMS_PER_HOUSE, FARM_WIDTH, FARM_PLANT_FRAMES, FARM_HARVEST_FRAMES,
    CROP_HARVEST_YIELD,
    HUNGER_MAX, HUNGER_RATE, HUNGER_THRESHOLD, HUNGER_CRITICAL,
    HUNGER_SPEED_PENALTY, FOOD_SATIATION, EATING_FRAMES, HUNGER_EAT_THRESHOLD,
    GOAL_PRIORITY, GOAL_PREREQS, GOAL_EVAL_INTERVAL, FOOD_SHARE_THRESHOLD,
    TRAIT_GOAL_BONUS,
    HUNTING_HUNGER_THRESHOLD, HUNTING_CATCH_RADIUS, HUNTING_KILL_FOOD,
    HUNTING_CHASE_FRAMES, ANIMAL_FLEE_RADIUS,
    BOW_COST_LUMBER, BOW_RANGE, BOW_SHOOT_FRAMES, BOW_HUNTING_FOOD,
)
from .entities import Villager, Tree, Structure, LumberItem, GrassFire, Farm, Animal, Boat
from .utils import _clamp
from .structures import (
    _find_campfire_site, _find_build_site, _find_mine_site,
    _find_bridge_at, _find_water_gap, _level_foundation,
    _min_campfire_distance, _transfer_house_ownership, _claim_unowned_house,
    _find_well_site, _find_storage_site, _find_bank_site,
    _get_storage, _get_bank,
)
from .terrain import (
    _get_valley_cols, _flatten_terrain, _find_steep_spot,
    _find_extreme_terrain_near_home, _too_close_to_structure,
)
from .day_night import _compute_ambient


def _compute_population_cap(structures):
    """Housing-based population cap: BASE_VILLAGERS + houses * VILLAGERS_PER_HOUSE, capped at MAX_VILLAGERS."""
    num_houses = sum(1 for s in structures if s.type in ("house_small", "house_large") and not s.under_construction)
    return min(BASE_VILLAGERS + num_houses * VILLAGERS_PER_HOUSE, MAX_VILLAGERS)

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

def _find_farm_site(villager, farms, heights, world, structures, trees):
    """Find a suitable location near the villager's home to place a farm.

    Farm needs FARM_WIDTH contiguous flat grass columns, near the house,
    not overlapping water, structures, or trees.
    Returns the leftmost x of the plot, or None.
    """
    if villager.home is None:
        return None
    home_x = villager.home.x
    vc = _get_valley_cols(world)
    # Search outward from house in both directions
    for dist in range(3, 20):
        for direction in (1, -1):
            start_x = home_x + dist * direction
            # Check FARM_WIDTH contiguous columns
            ok = True
            for dx in range(FARM_WIDTH):
                cx = start_x + dx
                if cx < 2 or cx >= WORLD_WIDTH - 2:
                    ok = False; break
                if cx in vc:
                    ok = False; break
                sy = heights[cx]
                if sy < 0 or sy >= DISPLAY_HEIGHT:
                    ok = False; break
                if world[sy][cx] != GRASS:
                    ok = False; break
                # Check height consistency (must be flat)
                if abs(heights[cx] - heights[start_x]) > 1:
                    ok = False; break
                # Not too close to structures
                for s in structures:
                    if s.x - 2 <= cx <= s.x + s.width + 1:
                        ok = False; break
                if not ok: break
                # Not too close to trees
                for t in trees:
                    if t.alive and abs(t.x - cx) < 2:
                        ok = False; break
                if not ok: break
                # Not overlapping existing farms
                for f in farms:
                    if f.x <= cx < f.x + f.width:
                        ok = False; break
                if not ok: break
            if ok:
                return start_x
    return None

def _count_villager_farms(villager, farms):
    """Count how many farms are owned by this villager."""
    return sum(1 for f in farms if f.owner is villager)

# ---------------------------------------------------------------------------
# Goal-based decision tree
# ---------------------------------------------------------------------------

def _evaluate_goals(v, ctx):
    """Score all applicable goals for this villager and return sorted list
    of (score, goal_name) in descending priority.

    ``ctx`` is a dict with shared simulation state:
        structures, trees, heights, world, pop, farms,
        campfire_count, mine_count, bridge_count,
        watchtower_exists, granary_exists, lumber_items
    """
    scores = []
    pop = ctx["pop"]
    campfire_count = ctx["campfire_count"]
    mine_count = ctx["mine_count"]
    bridge_count = ctx["bridge_count"]
    watchtower_exists = ctx["watchtower_exists"]
    granary_exists = ctx["granary_exists"]
    structures = ctx["structures"]
    trees = ctx["trees"]
    farms = ctx["farms"]
    lumber_items = ctx["lumber_items"]
    heights = ctx["heights"]
    world = ctx["world"]

    # --- Survival goals ---
    if campfire_count == 0:
        scores.append((GOAL_PRIORITY["build_campfire"] + 15, "build_campfire"))
    elif v.home is None and campfire_count < max(1, pop // 3):
        scores.append((GOAL_PRIORITY["build_campfire"], "build_campfire"))

    if v.hunger >= HUNGER_CRITICAL and v.food == 0:
        scores.append((GOAL_PRIORITY["get_food"], "get_food"))

    # --- Housing ---
    if v.home is None:
        hc = sum(1 for s in structures if s.type in ("house_small", "house_large"))
        max_houses = max(1, pop // 3) if pop > 0 else 0
        if hc < max_houses:
            # Rain/storm motivates homeless villagers to build shelter
            weather = ctx.get("weather")
            rain_bonus = 0
            if weather is not None and weather.is_storming():
                rain_bonus = 20  # strong motivation in storms
            elif weather is not None and weather.is_raining():
                rain_bonus = 12  # moderate motivation in rain
            scores.append((GOAL_PRIORITY["build_house"] + rain_bonus, "build_house"))

    # --- House upgrade ---
    if v.home is not None and v.home.level < 3:
        scores.append((GOAL_PRIORITY["upgrade_house"], "upgrade_house"))

    # --- Farming: harvest first (free payoff) ---
    if v.farm is not None and v.farm.has_mature_crops():
        # Boost if hungry
        bonus = 10 if v.hunger >= HUNGER_THRESHOLD else 0
        scores.append((GOAL_PRIORITY["farm_harvest"] + bonus, "farm_harvest"))

    # --- Farming: plant ---
    if v.farm is not None and v.farm.has_empty_slots():
        scores.append((GOAL_PRIORITY["farm_plant"], "farm_plant"))

    # --- Build farm ---
    if (v.home is not None and pop >= FARM_POPULATION_THRESHOLD
            and _count_villager_farms(v, farms) < MAX_FARMS_PER_HOUSE):
        scores.append((GOAL_PRIORITY["build_farm"], "build_farm"))

    # --- Refuel campfire ---
    for s in structures:
        if s.type == "campfire" and s.fuel < CAMPFIRE_LOW_FUEL_THRESHOLD:
            scores.append((GOAL_PRIORITY["refuel_campfire"], "refuel_campfire"))
            break

    # --- Community structures ---
    if not granary_exists and pop >= GRANARY_POPULATION_THRESHOLD:
        scores.append((GOAL_PRIORITY["build_granary"], "build_granary"))
    if not watchtower_exists and pop >= WATCHTOWER_POPULATION_THRESHOLD:
        scores.append((GOAL_PRIORITY["build_watchtower"], "build_watchtower"))
    if pop >= MINE_POPULATION_THRESHOLD and mine_count < MAX_MINES:
        scores.append((GOAL_PRIORITY["build_mine"], "build_mine"))
    well_count = ctx.get("well_count", 0)
    if pop >= WELL_POPULATION_THRESHOLD and well_count < MAX_WELLS:
        scores.append((GOAL_PRIORITY["build_well"], "build_well"))
    castle_count = ctx.get("castle_count", 0)
    if pop >= CASTLE_POPULATION_THRESHOLD and castle_count < MAX_CASTLES:
        scores.append((GOAL_PRIORITY["build_castle"], "build_castle"))
    storage_count = ctx.get("storage_count", 0)
    if pop >= STORAGE_POPULATION_THRESHOLD and storage_count < MAX_STORAGES:
        scores.append((GOAL_PRIORITY["build_storage"], "build_storage"))
    bank_count = ctx.get("bank_count", 0)
    if pop >= BANK_POPULATION_THRESHOLD and bank_count < MAX_BANKS:
        scores.append((GOAL_PRIORITY["build_bank"], "build_bank"))

    # --- Community storage deposit/withdraw ---
    storage = _get_storage(structures)
    if storage is not None:
        # Withdraw: villager needs lumber but storage has some
        if v.lumber == 0 and storage.stored_lumber > 0:
            scores.append((GOAL_PRIORITY["withdraw_storage"], "withdraw_storage"))
        if v.stone == 0 and storage.stored_stone > 0:
            scores.append((GOAL_PRIORITY["withdraw_storage"], "withdraw_storage"))
        if v.food == 0 and v.hunger >= HUNGER_THRESHOLD and storage.stored_food > 0:
            scores.append((GOAL_PRIORITY["withdraw_storage"] + 5, "withdraw_storage"))
        # Deposit: villager has excess
        has_excess = (v.lumber > STORAGE_DEPOSIT_THRESHOLD_LUMBER
                      or v.stone > STORAGE_DEPOSIT_THRESHOLD_STONE
                      or v.food > STORAGE_DEPOSIT_THRESHOLD_FOOD)
        if has_excess:
            scores.append((GOAL_PRIORITY["deposit_storage"], "deposit_storage"))

    if bridge_count < MAX_BRIDGES:
        col = int(v.x)
        for bd in (1, -1):
            nc = col + bd
            if 0 <= nc < WORLD_WIDTH and world[heights[nc]][nc] == WATER:
                scores.append((GOAL_PRIORITY["build_bridge"], "build_bridge"))
                break

    # --- Resource gathering ---
    # Dynamic lumber priority: increases as lumber drops below threshold
    lumber_need = max(0, VILLAGER_CHOP_THRESHOLD - v.lumber)
    if lumber_need > 0:
        li_near = [it for it in lumber_items if abs(it.x - int(v.x)) < 15]
        # Prefer collecting free lumber over chopping
        gather_score = GOAL_PRIORITY["gather_lumber"] + lumber_need * 5
        if li_near:
            gather_score += 10  # bonus for free pickup
        scores.append((gather_score, "gather_lumber"))

    # Stone gathering (needed for upgrades / watchtower)
    if v.stone < 2 and mine_count > 0:
        scores.append((GOAL_PRIORITY["gather_stone"], "gather_stone"))

    # --- Reproduction as a goal (Tier 2.4) ---
    if (v.home is not None and v.age >= REPRODUCTION_MIN_AGE
            and v.age <= REPRODUCTION_MAX_AGE and v.children_born < MAX_CHILDREN):
        pop_cap = _compute_population_cap(structures)
        if pop < pop_cap:
            scores.append((GOAL_PRIORITY["have_baby"], "have_baby"))

    # --- Food sharing (Tier 2.5) ---
    if v.food > FOOD_SHARE_THRESHOLD:
        # Check if any nearby villager is hungry
        vx = int(v.x)
        hungry_near = any(
            ov is not v and ov.hunger >= HUNGER_THRESHOLD and ov.food == 0
            and abs(int(ov.x) - vx) < 10
            for ov in ctx.get("villagers", [])
        )
        if hungry_near:
            scores.append((GOAL_PRIORITY["share_food"], "share_food"))

    # --- Hunting: hungry villager with no farm may hunt animals ---
    if (v.hunger >= HUNTING_HUNGER_THRESHOLD and v.food == 0
            and v.farm is None and ctx.get("animals")):
        nearby_animals = [a for a in ctx["animals"]
                          if a.alive and abs(a.x - int(v.x)) < 20]
        if nearby_animals:
            scores.append((GOAL_PRIORITY.get("get_food", 80) - 5, "hunt"))

    # --- Sustainability ---
    col = int(v.x)
    nt = sum(1 for t in trees if t.alive and abs(t.x - col) < 10)
    if nt < 2 and v.lumber >= 1:
        scores.append((GOAL_PRIORITY["plant_tree"], "plant_tree"))

    # --- Terrain ---
    scores.append((GOAL_PRIORITY["flatten_terrain"], "flatten_terrain"))

    # --- Explore (always available) ---
    scores.append((GOAL_PRIORITY["explore"], "explore"))

    # --- Trait bonus: boost scores for goals matching villager personality ---
    trait = getattr(v, "trait", None)
    if trait is not None:
        trait_goals = {
            "builder":    {"build_house", "build_campfire", "build_granary", "build_watchtower", "build_mine", "build_bridge", "upgrade_house", "build_farm"},
            "farmer":     {"farm_harvest", "farm_plant", "build_farm", "get_food", "share_food"},
            "lumberjack": {"gather_lumber", "plant_tree", "refuel_campfire"},
            "explorer":   {"explore", "flatten_terrain"},
        }
        preferred = trait_goals.get(trait, set())
        scores = [(s * (1.0 + TRAIT_GOAL_BONUS) if g in preferred else s, g)
                  for s, g in scores]

    scores.sort(key=lambda x: -x[0])
    return scores


def _has_prereqs(v, goal):
    """Check if villager has enough resources for the given goal."""
    prereqs = GOAL_PREREQS.get(goal)
    if prereqs is None:
        return True
    for resource, amount in prereqs.items():
        if getattr(v, resource, 0) < amount:
            return False
    return True


def _missing_prereqs(v, goal):
    """Return dict of {resource: shortfall} for the goal, or empty dict if met."""
    prereqs = GOAL_PREREQS.get(goal)
    if prereqs is None:
        return {}
    missing = {}
    for resource, amount in prereqs.items():
        current = getattr(v, resource, 0)
        if current < amount:
            missing[resource] = amount - current
    return missing


def _resolve_prereq_action(v, goal, ctx):
    """Given a goal whose prereqs are NOT met, return a sub-goal that works
    toward satisfying them.  Returns None if no viable sub-action exists.

    This is the prerequisite chaining engine:
      build_house(needs 4 lumber) -> gather_lumber
      upgrade_house(needs 6 lumber + 2 stone) -> gather_lumber or gather_stone
      build_watchtower(needs 4 lumber + 2 stone) -> gather_lumber or gather_stone
    """
    missing = _missing_prereqs(v, goal)
    if not missing:
        return None
    # Prioritize the largest shortfall
    worst_resource = max(missing, key=lambda r: missing[r])
    if worst_resource == "lumber":
        return "gather_lumber"
    elif worst_resource == "stone":
        return "gather_stone"
    return None


def _handle_villager_trading(villagers, sim_tick=0):
    for i,v1 in enumerate(villagers):
        if v1.state == "trading": continue
        for j,v2 in enumerate(villagers):
            if i >= j or v2.state == "trading": continue
            if abs(int(v1.x)-int(v2.x)) <= 2 and abs(v1.y-v2.y) <= 2:
                if v1.lumber >= 3 and v2.lumber == 0:
                    v1.lumber -= 1; v2.lumber += 1
                    v1.state = v2.state = "trading"; v1.task_timer = v2.task_timer = 10; v1.idle_timer = v2.idle_timer = 0
                    _set_bubble(v1, "trading"); _set_bubble(v2, "trading")
                    log_event(sim_tick, CAT_ECONOMY, f"{v1.name} traded 1 lumber to {v2.name}")
                elif v2.lumber >= 3 and v1.lumber == 0:
                    v2.lumber -= 1; v1.lumber += 1
                    v1.state = v2.state = "trading"; v1.task_timer = v2.task_timer = 10; v1.idle_timer = v2.idle_timer = 0
                    _set_bubble(v1, "trading"); _set_bubble(v2, "trading")
                    log_event(sim_tick, CAT_ECONOMY, f"{v2.name} traded 1 lumber to {v1.name}")

def _handle_villager_aging(villagers, structures, farms=None):
    """Age villagers; remove dead ones with proper cleanup of owned resources."""
    if farms is None:
        farms = []
    for v in villagers: v.age += 1
    rm = [i for i,v in enumerate(villagers) if v.age >= v.max_age]
    for i in reversed(rm):
        v = villagers[i]
        surviving = [vv for vi, vv in enumerate(villagers) if vi != i]
        # --- Transfer house ownership ---
        if v.home is not None:
            _transfer_house_ownership(v.home, surviving)
        # --- Farm orphan cleanup (Tier 1.3) ---
        for f in farms:
            if f.owner is v:
                # Transfer to nearest homeless villager, else mark unowned
                best_farmer = None
                best_dist = 999
                for sv in surviving:
                    if sv.farm is None:
                        d = abs(int(sv.x) - f.x)
                        if d < best_dist:
                            best_dist = d
                            best_farmer = sv
                if best_farmer is not None:
                    f.owner = best_farmer
                    best_farmer.farm = f
                else:
                    f.owner = None
        # --- Dead villager goal cleanup (Tier 1.5) ---
        # Abandon in-progress structures so they don't stay under_construction forever
        if v.building_target is not None and v.building_target.under_construction:
            v.building_target.under_construction = False
            v.building_target.build_progress = 1.0
        # --- Cremation flash: nearest campfire OR home lantern (Tier 2.6) ---
        col = int(v.x)
        best = None; bd = 999
        for s in structures:
            if s.type == "campfire" and s.fuel > 0:
                d = abs(s.x - col)
                if d < bd: bd = d; best = s
        # Also consider the villager's home if it has a lantern (completed house)
        if v.home is not None and not v.home.under_construction:
            home_d = abs(v.home.x - col)
            if home_d < bd:
                best = v.home
        if best is not None: best.cremation_flash = CREMATION_FLASH_FRAMES
        log_event(v.age, CAT_DEATH, f"{v.name} ({v.trait}) died at age {v.age} (x={int(v.x)})")
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

def _update_villagers(villagers, heights, world, trees, structures, lumber_items, flowers, path_wear, day_phase, sim_tick, weather=None, grass_fires=None, farms=None, animals=None):
    if farms is None:
        farms = []
    if animals is None:
        animals = []
    ambient = _compute_ambient(day_phase)
    is_night = ambient < 0.3
    is_bad_weather = weather is not None and weather.is_raining()
    pop = len(villagers)
    max_campfires = max(1, pop//3) if pop > 0 else 0
    max_houses = max(1, pop//3) if pop > 0 else 0
    campfire_count = sum(1 for s in structures if s.type == "campfire")
    mine_count = sum(1 for s in structures if s.type == "mine")
    bridge_count = sum(1 for s in structures if s.type == "bridge")
    well_count = sum(1 for s in structures if s.type == "well")
    castle_count = sum(1 for s in structures if s.type == "castle")
    storage_count = sum(1 for s in structures if s.type == "storage")
    bank_count = sum(1 for s in structures if s.type == "bank")
    watchtower_exists = any(s.type == "watchtower" for s in structures)
    granary_exists = any(s.type == "granary" for s in structures)
    granary = _get_granary(structures)
    storage = _get_storage(structures)
    _handle_villager_trading(villagers, sim_tick=sim_tick)
    for v in villagers:
        v.idle_timer += 1
        if v.bubble_timer > 0:
            v.bubble_timer -= 1
        # --- Hunger: increase hunger each AI tick ---
        v.hunger = min(HUNGER_MAX, v.hunger + HUNGER_RATE)
        # --- Hunger: auto-eat when hungry and has food (interrupt from non-critical states) ---
        if (v.hunger >= HUNGER_EAT_THRESHOLD and v.food >= 1
                and v.state in ("idle", "walking")):
            v.state = "eating"
            v.task_timer = EATING_FRAMES
            _set_bubble(v, "eating")
            continue
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
            # --- Hunger speed penalty: critically hungry villagers move every other tick ---
            if v.hunger >= HUNGER_CRITICAL and sim_tick % 2 != 0:
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
                    elif v.has_boat or v.lumber >= BOAT_COST_LUMBER:
                        # Boat travel: craft boat if needed, then ride across water
                        if not v.has_boat:
                            v.lumber -= BOAT_COST_LUMBER
                            v.has_boat = True
                            log_event(sim_tick, CAT_ECONOMY, f"{v.name} crafted a boat")
                        # Create/activate boat and ride on water surface
                        water_y = heights[nc]
                        if v.boat is None:
                            v.boat = Boat(v.x, water_y, v)
                        v.boat.active = True
                        v.boat.x = float(nx)
                        v.boat.y = water_y
                        v.x = nx; v.y = water_y; v.on_bridge = None
                    else:
                        v.state = "idle"; v.idle_timer = 0; continue
                else:
                    v.x = nx; v.y = heights[nc]; v.on_bridge = None
                    # Deactivate boat when stepping onto land
                    if v.boat is not None and v.boat.active:
                        v.boat.active = False
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
                    log_event(sim_tick, CAT_ECONOMY, f"{v.name} chopped a tree at x={v.target_tree.x}")
                    lumber_gained = random.randint(2,3)
                    for _ in range(lumber_gained):
                        lx = _clamp(v.target_tree.x+random.randint(-1,1),0,WORLD_WIDTH-1)
                        ly = heights[lx]-1
                        if 0 <= ly < DISPLAY_HEIGHT: lumber_items.append(LumberItem(lx,ly))
                    # Auto-collect one piece immediately so villager gets tangible reward
                    v.lumber += 1
                v.target_tree = None; v.state = "idle"; v.idle_timer = 0
        elif v.state == "planting":
            v.task_timer -= 1
            if v.task_timer <= 0:
                col = int(v.x); tt = sum(1 for t in trees if t.alive)
                v.lumber -= 1  # Planting costs 1 lumber
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
                        log_event(sim_tick, CAT_BUILDING, f"{v.name} built a campfire at x={col}")
                elif v.build_type == "house_small":
                    if v.building_target is not None:
                        v.building_target.under_construction = False; v.building_target.build_progress = 1.0
                        log_event(sim_tick, CAT_BUILDING, f"{v.name} finished building a house at x={col}")
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
                        log_event(sim_tick, CAT_BUILDING, f"{v.name} finished building a watchtower at x={col}")
                elif v.build_type == "granary":
                    if v.building_target is not None:
                        v.building_target.under_construction = False
                        v.building_target.build_progress = 1.0
                        log_event(sim_tick, CAT_BUILDING, f"{v.name} finished building a granary at x={col}")
                elif v.build_type == "well":
                    if v.building_target is not None:
                        v.building_target.under_construction = False
                        v.building_target.build_progress = 1.0
                        log_event(sim_tick, CAT_BUILDING, f"{v.name} finished building a well at x={col}")
                elif v.build_type == "castle":
                    if v.building_target is not None:
                        v.building_target.under_construction = False
                        v.building_target.build_progress = 1.0
                        log_event(sim_tick, CAT_BUILDING, f"{v.name} finished building a CASTLE at x={col}")
                elif v.build_type == "storage":
                    if v.building_target is not None:
                        v.building_target.under_construction = False
                        v.building_target.build_progress = 1.0
                        log_event(sim_tick, CAT_BUILDING, f"{v.name} finished building a storage at x={col}")
                elif v.build_type == "bank":
                    if v.building_target is not None:
                        v.building_target.under_construction = False
                        v.building_target.build_progress = 1.0
                        log_event(sim_tick, CAT_BUILDING, f"{v.name} finished building a bank at x={col}")
                elif v.build_type == "farm":
                    # Farm was already created and added to farms list; mark complete
                    if v.farm is not None:
                        pass  # farm is live and ready
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
                    if m.depth % 2 == 0:
                        v.stone += 1
                        # Gold mining chance
                        if random.random() < GOLD_MINE_CHANCE:
                            v.gold += 1
                            log_event(sim_tick, CAT_ECONOMY, f"{v.name} found gold while mining!")
                    if m.depth < m.max_depth: v.task_timer = MINE_DIG_FRAMES
                    else:
                        for cy in range(DISPLAY_HEIGHT):
                            if world[cy][m.x] != AIR:
                                heights[m.x] = cy
                                if world[cy][m.x] not in (WATER,GRASS): world[cy][m.x] = GRASS
                                break
                        v.mine_target = None; v.state = "idle"; v.idle_timer = 0
                else: v.mine_target = None; v.state = "idle"; v.idle_timer = 0
        elif v.state == "farming_plant":
            v.task_timer -= 1
            if v.task_timer <= 0:
                if v.farm is not None:
                    v.farm.plant_all_empty()
                v.state = "idle"; v.idle_timer = 0
        elif v.state == "farming_harvest":
            v.task_timer -= 1
            if v.task_timer <= 0:
                if v.farm is not None:
                    count = v.farm.harvest_all_mature()
                    v.food += count * CROP_HARVEST_YIELD
                v.state = "idle"; v.idle_timer = 0
        elif v.state == "eating":
            v.task_timer -= 1
            _set_bubble(v, "eating")
            if v.task_timer <= 0:
                if v.food >= 1:
                    v.food -= 1
                    v.hunger = max(0.0, v.hunger - FOOD_SATIATION)
                v.state = "idle"; v.idle_timer = 0
        elif v.state == "hunting":
            target = v.hunt_target
            v.task_timer += 1
            if target is None or not target.alive or v.task_timer > HUNTING_CHASE_FRAMES:
                v.hunt_target = None; v.state = "idle"; v.idle_timer = 0; continue
            _set_bubble(v, "hunting")
            dist = abs(int(v.x) - int(round(target.x)))
            if v.has_bow and dist <= BOW_RANGE:
                # Bow hunting: stand still and shoot after aiming
                v.direction = 1 if target.x > v.x else -1
                if v.task_timer >= BOW_SHOOT_FRAMES:
                    target.alive = False
                    v.food += BOW_HUNTING_FOOD
                    log_event(sim_tick, CAT_COMBAT, f"{v.name} shot a {target.animal_type} with bow for {BOW_HUNTING_FOOD} food")
                    v.hunt_target = None; v.state = "idle"; v.idle_timer = 0
                # else: still aiming, stay put
            elif dist <= HUNTING_CATCH_RADIUS:
                # Melee catch (no bow, very close)
                target.alive = False
                v.food += HUNTING_KILL_FOOD
                log_event(sim_tick, CAT_COMBAT, f"{v.name} hunted a {target.animal_type} for {HUNTING_KILL_FOOD} food")
                v.hunt_target = None; v.state = "idle"; v.idle_timer = 0
            else:
                # Chase: move toward animal
                if v.x < target.x: v.direction = 1; v.x += 1
                elif v.x > target.x: v.direction = -1; v.x -= 1
                v.x = _clamp(v.x, 1, WORLD_WIDTH - 2)
                nc = int(v.x)
                v.y = heights[nc]
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
                v.state = "firefighting"
                continue
            # --- Hunger: eat food when hungry (high priority after fire) ---
            if v.hunger >= HUNGER_EAT_THRESHOLD and v.food >= 1:
                v.state = "eating"
                v.task_timer = EATING_FRAMES
                _set_bubble(v, "eating")
                continue
            # --- Hunger: critically hungry with no food -- rush to farm ---
            if v.hunger >= HUNGER_CRITICAL and v.food == 0:
                # Prioritize harvesting mature crops
                if v.farm is not None and v.farm.has_mature_crops():
                    v.target_x = v.farm.x
                    v.task_timer = FARM_HARVEST_FRAMES
                    _set_bubble(v, "farming")
                    if abs(int(v.x) - v.farm.x) <= 2:
                        v.state = "farming_harvest"
                    else:
                        v.state = "walking"
                    continue
                # Prioritize planting if farm has empty slots
                if v.farm is not None and v.farm.has_empty_slots():
                    v.target_x = v.farm.x
                    v.task_timer = FARM_PLANT_FRAMES
                    _set_bubble(v, "farming")
                    if abs(int(v.x) - v.farm.x) <= 2:
                        v.state = "farming_plant"
                    else:
                        v.state = "walking"
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
            if is_bad_weather and v.home is None:
                # Homeless in rain: fall through to goal tree so rain-boosted
                # build_house priority motivates them to build shelter
                pass  # continue to goal-based decision tree below
            elif is_bad_weather and v.home is not None:
                # Home-owning villagers with nothing urgent shelter at home in bad weather
                # (This branch is dead -- already handled above at line 875. Keep for safety.)
                v.target_x = v.home.x
                v.state = "resting" if abs(int(v.x)-v.home.x)<=1 else "walking"; continue
            # ===================================================================
            # GOAL-BASED DECISION TREE
            # Evaluates all possible goals, scores them, picks the best one.
            # If the goal needs resources the villager doesn't have, the system
            # chains to a prerequisite sub-goal (e.g. gather_lumber).
            # ===================================================================
            ctx = {
                "structures": structures, "trees": trees,
                "heights": heights, "world": world,
                "pop": pop, "farms": farms,
                "campfire_count": campfire_count,
                "mine_count": mine_count,
                "bridge_count": bridge_count,
                "well_count": well_count,
                "castle_count": castle_count,
                "storage_count": storage_count,
                "bank_count": bank_count,
                "watchtower_exists": watchtower_exists,
                "granary_exists": granary_exists,
                "lumber_items": lumber_items,
                "villagers": villagers,
                "animals": animals,
                "weather": weather,
            }
            # Re-evaluate goals periodically or when current goal is None
            if v.current_goal is None or v.goal_timer >= GOAL_EVAL_INTERVAL:
                ranked = _evaluate_goals(v, ctx)
                if ranked:
                    v.current_goal = ranked[0][1]
                    v.goal_timer = 0
            v.goal_timer += 1
            goal = v.current_goal if v.current_goal else "explore"

            # --- Prerequisite chaining: if goal needs resources, redirect ---
            if not _has_prereqs(v, goal):
                sub = _resolve_prereq_action(v, goal, ctx)
                if sub is not None:
                    goal = sub

            # --- Execute the chosen goal ---
            _executed = False

            if goal == "build_campfire":
                if v.lumber >= 2:
                    site = _find_campfire_site(structures, trees, heights, world)
                    if site is not None:
                        v.target_x = site; v.build_type = "campfire"; v.lumber -= 2; v.task_timer = 60
                        _set_bubble(v, "building"); v.current_goal = None
                        v.state = "building" if abs(int(v.x) - site) <= 1 else "walking"; _executed = True

            elif goal == "build_house":
                if v.lumber >= 4 and v.home is None:
                    hw, hh = HOUSE_DIMENSIONS[1]
                    site = _find_build_site(structures, trees, heights, world, hw, hh)
                    if site is not None:
                        sx, sy = site; s = Structure("house_small", sx, sy, hw, hh)
                        _level_foundation(sx, hw, heights, world, v, structures)
                        sy = heights[sx] - hh; s.y = sy
                        s.under_construction = True; s.build_progress = 0.0; s.owner = v
                        if v.stone >= 2: s.stone_built = True; v.stone -= 2
                        for _r in HOUSE_TEMPLATES[1]['grid']:
                            for _ci, _ch in enumerate(_r):
                                if _ch == 'D': s.door_x = sx + _ci; break
                            else: continue
                            break
                        v.home = s; structures.append(s); v.target_x = sx; v.build_type = "house_small"
                        v.building_target = s; v.lumber -= 4; v.build_total_time = 120; v.task_timer = 120
                        _set_bubble(v, "building"); v.current_goal = None
                        v.state = "building" if abs(int(v.x) - sx) <= 1 else "walking"; _executed = True
                    else:
                        steep = _find_steep_spot(heights, world, near_x=int(v.x), radius=15)
                        if steep is not None:
                            v.flatten_target = steep; v.target_x = steep; v.task_timer = FLATTEN_DURATION
                            v.state = "flattening" if abs(int(v.x) - steep) <= 1 else "walking"; _executed = True

            elif goal == "upgrade_house":
                if v.home is not None and v.home.level < 3 and v.lumber >= 6 and v.stone >= 2:
                    v.upgrade_target = v.home; v.target_x = v.home.x
                    v.lumber -= 6; v.stone -= 2; v.task_timer = 120
                    _set_bubble(v, "building"); v.current_goal = None
                    v.state = "upgrading" if abs(int(v.x) - v.home.x) <= 1 else "walking"; _executed = True

            elif goal == "get_food":
                # Chain: harvest mature -> plant empty -> build farm
                if v.farm is not None and v.farm.has_mature_crops():
                    v.target_x = v.farm.x; v.task_timer = FARM_HARVEST_FRAMES
                    _set_bubble(v, "farming")
                    v.state = "farming_harvest" if abs(int(v.x) - v.farm.x) <= 2 else "walking"; _executed = True
                elif v.farm is not None and v.farm.has_empty_slots():
                    v.target_x = v.farm.x; v.task_timer = FARM_PLANT_FRAMES
                    _set_bubble(v, "farming")
                    v.state = "farming_plant" if abs(int(v.x) - v.farm.x) <= 2 else "walking"; _executed = True
                elif (v.home is not None and pop >= FARM_POPULATION_THRESHOLD
                        and v.lumber >= FARM_COST_LUMBER
                        and _count_villager_farms(v, farms) < MAX_FARMS_PER_HOUSE):
                    farm_x = _find_farm_site(v, farms, heights, world, structures, trees)
                    if farm_x is not None:
                        farm_y = heights[farm_x]
                        new_farm = Farm(farm_x, farm_y, FARM_WIDTH)
                        new_farm.owner = v; v.farm = new_farm; farms.append(new_farm)
                        v.lumber -= FARM_COST_LUMBER; v.target_x = farm_x
                        v.build_type = "farm"; v.task_timer = FARM_BUILD_FRAMES
                        v.build_total_time = FARM_BUILD_FRAMES; _set_bubble(v, "farming")
                        v.state = "building" if abs(int(v.x) - farm_x) <= 1 else "walking"; _executed = True

            elif goal == "farm_harvest":
                if v.farm is not None and v.farm.has_mature_crops():
                    v.target_x = v.farm.x; v.task_timer = FARM_HARVEST_FRAMES
                    _set_bubble(v, "farming"); v.current_goal = None
                    v.state = "farming_harvest" if abs(int(v.x) - v.farm.x) <= 2 else "walking"; _executed = True

            elif goal == "farm_plant":
                if v.farm is not None and v.farm.has_empty_slots():
                    v.target_x = v.farm.x; v.task_timer = FARM_PLANT_FRAMES
                    _set_bubble(v, "farming"); v.current_goal = None
                    v.state = "farming_plant" if abs(int(v.x) - v.farm.x) <= 2 else "walking"; _executed = True

            elif goal == "build_farm":
                if (v.home is not None and v.lumber >= FARM_COST_LUMBER
                        and _count_villager_farms(v, farms) < MAX_FARMS_PER_HOUSE):
                    farm_x = _find_farm_site(v, farms, heights, world, structures, trees)
                    if farm_x is not None:
                        farm_y = heights[farm_x]
                        new_farm = Farm(farm_x, farm_y, FARM_WIDTH)
                        new_farm.owner = v; v.farm = new_farm; farms.append(new_farm)
                        v.lumber -= FARM_COST_LUMBER; v.target_x = farm_x
                        v.build_type = "farm"; v.task_timer = FARM_BUILD_FRAMES
                        v.build_total_time = FARM_BUILD_FRAMES; _set_bubble(v, "farming")
                        v.current_goal = None
                        v.state = "building" if abs(int(v.x) - farm_x) <= 1 else "walking"; _executed = True

            elif goal == "refuel_campfire":
                if v.lumber >= 1:
                    for s in structures:
                        if s.type == "campfire" and s.fuel < CAMPFIRE_LOW_FUEL_THRESHOLD:
                            v.refuel_target = s; v.target_x = s.x; v.task_timer = 20
                            v.current_goal = None
                            v.state = "refueling" if abs(int(v.x) - s.x) <= 1 else "walking"; _executed = True; break

            elif goal == "build_granary":
                if v.lumber >= GRANARY_COST_LUMBER:
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
                        _set_bubble(v, "building"); v.current_goal = None
                        v.state = "building" if abs(int(v.x) - sx) <= 1 else "walking"; _executed = True

            elif goal == "build_watchtower":
                if v.lumber >= WATCHTOWER_COST_LUMBER and v.stone >= WATCHTOWER_COST_STONE:
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
                        _set_bubble(v, "building"); v.current_goal = None
                        v.state = "building" if abs(int(v.x) - sx) <= 1 else "walking"; _executed = True

            elif goal == "build_mine":
                if v.lumber >= 2:
                    mc = _find_mine_site(structures, trees, heights, world, int(v.x))
                    if mc is not None:
                        v.target_x = mc; v.build_type = "mine"; v.lumber -= 2; v.task_timer = MINE_DIG_FRAMES
                        _set_bubble(v, "mining"); v.current_goal = None
                        v.state = "mining" if abs(int(v.x) - mc) <= 1 else "walking"; _executed = True

            elif goal == "build_bridge":
                if v.lumber >= 2:
                    col = int(v.x)
                    for bd in (1, -1):
                        nc = col + bd
                        if 0 <= nc < WORLD_WIDTH and world[heights[nc]][nc] == WATER:
                            gap = _find_water_gap(world, heights, nc, bd)
                            if gap is not None:
                                ws, we, wsy = gap; gw = we - ws + 1
                                cost = 2 if gw <= 6 else 3
                                if v.lumber >= cost:
                                    v.lumber -= cost; v._bridge_gap = gap
                                    v.target_x = ws; v.build_type = "bridge"
                                    v.build_total_time = BRIDGE_BUILD_FRAMES; v.task_timer = BRIDGE_BUILD_FRAMES
                                    _set_bubble(v, "building"); v.current_goal = None
                                    v.state = "building" if abs(col - ws) <= 1 else "walking"; _executed = True; break

            elif goal == "build_well":
                if v.lumber >= WELL_COST_LUMBER and v.stone >= WELL_COST_STONE:
                    wc = _find_well_site(structures, trees, heights, world, int(v.x))
                    if wc is not None:
                        v.lumber -= WELL_COST_LUMBER; v.stone -= WELL_COST_STONE
                        s = Structure("well", wc, heights[wc] - WELL_HEIGHT, WELL_WIDTH, WELL_HEIGHT)
                        s.under_construction = True; s.build_progress = 0.0
                        structures.append(s); v.target_x = wc; v.build_type = "well"
                        v.building_target = s
                        v.build_total_time = WELL_BUILD_FRAMES; v.task_timer = WELL_BUILD_FRAMES
                        _set_bubble(v, "building"); v.current_goal = None
                        v.state = "building" if abs(int(v.x) - wc) <= 1 else "walking"; _executed = True

            elif goal == "build_castle":
                if v.lumber >= CASTLE_COST_LUMBER and v.stone >= CASTLE_COST_STONE:
                    site = _find_build_site(structures, trees, heights, world, CASTLE_WIDTH, CASTLE_HEIGHT)
                    if site is not None:
                        sx, sy = site
                        _level_foundation(sx, CASTLE_WIDTH, heights, world, v, structures)
                        sy = heights[sx] - CASTLE_HEIGHT
                        s = Structure("castle", sx, sy, CASTLE_WIDTH, CASTLE_HEIGHT)
                        s.under_construction = True; s.build_progress = 0.0
                        structures.append(s); v.target_x = sx; v.build_type = "castle"
                        v.building_target = s
                        v.lumber -= CASTLE_COST_LUMBER; v.stone -= CASTLE_COST_STONE
                        v.build_total_time = CASTLE_BUILD_FRAMES; v.task_timer = CASTLE_BUILD_FRAMES
                        _set_bubble(v, "building"); v.current_goal = None
                        v.state = "building" if abs(int(v.x) - sx) <= 1 else "walking"; _executed = True

            elif goal == "gather_lumber":
                # Prefer collecting free items, then chopping
                li_near = [li for li, it in enumerate(lumber_items) if abs(it.x - int(v.x)) < 15]
                if li_near:
                    bi = min(li_near, key=lambda i: abs(lumber_items[i].x - int(v.x)))
                    v.target_x = lumber_items[bi].x; v.task_timer = 10
                    v.state = "collecting" if abs(int(v.x) - lumber_items[bi].x) <= 1 else "walking"; _executed = True
                else:
                    mt = [t for t in trees if t.alive and t.growth >= 1.0 and not t.dying and not t.on_fire and abs(t.x - int(v.x)) < 30]
                    if mt and (v.lumber == 0 or random.random() >= VILLAGER_EXPLORE_CHANCE):
                        tt = min(mt, key=lambda t: abs(t.x - int(v.x)))
                        v.target_tree = tt; v.target_x = tt.x - 1 if tt.x > int(v.x) else tt.x + 1
                        v.task_timer = 60; _set_bubble(v, "chopping")
                        v.state = "chopping" if abs(int(v.x) - tt.x) <= 1 else "walking"; _executed = True

            elif goal == "gather_stone":
                for s in structures:
                    if s.type == "mine" and s.depth < s.max_depth:
                        v.mine_target = s; v.target_x = s.x; v.task_timer = MINE_DIG_FRAMES
                        _set_bubble(v, "mining")
                        v.state = "mining" if abs(int(v.x) - s.x) <= 1 else "walking"; _executed = True; break

            elif goal == "have_baby":
                # Reproduction goal: walk home and idle there
                if (v.home is not None and v.age >= REPRODUCTION_MIN_AGE
                        and v.age <= REPRODUCTION_MAX_AGE and v.children_born < MAX_CHILDREN):
                    if abs(int(v.x) - v.home.x) <= 1:
                        # At home -- idle; reproduction is checked via _handle_reproduction
                        v.current_goal = None
                        _executed = True
                    else:
                        v.target_x = v.home.x
                        v.state = "walking"; _executed = True
                        # Don't clear goal -- keep walking home

            elif goal == "hunt":
                # Auto-craft bow if villager has lumber and doesn't have one
                if not v.has_bow and v.lumber >= BOW_COST_LUMBER:
                    v.lumber -= BOW_COST_LUMBER
                    v.has_bow = True
                    log_event(sim_tick, CAT_ECONOMY, f"{v.name} crafted a bow (lumber: {v.lumber})")
                # Find nearest alive animal and hunt it
                vx = int(v.x)
                best_animal = None
                best_d = 999
                search_range = 20 if v.has_bow else 20
                for a in animals:
                    if a.alive:
                        d = abs(int(round(a.x)) - vx)
                        if d < best_d and d < search_range:
                            best_d = d
                            best_animal = a
                if best_animal is not None:
                    v.hunt_target = best_animal
                    v.task_timer = 0
                    v.state = "hunting"
                    v.current_goal = None
                    _set_bubble(v, "hunting")
                    _executed = True

            elif goal == "share_food":
                # Find nearest hungry villager within range and give 1 food
                vx = int(v.x)
                best_target = None
                best_dist = 999
                for ov in villagers:
                    if ov is v: continue
                    if ov.hunger >= HUNGER_THRESHOLD and ov.food == 0:
                        d = abs(int(ov.x) - vx)
                        if d < best_dist:
                            best_dist = d
                            best_target = ov
                if best_target is not None:
                    if best_dist <= 2:
                        # Adjacent: give food
                        v.food -= 1
                        best_target.food += 1
                        _set_bubble(v, "trading"); _set_bubble(best_target, "trading")
                        log_event(sim_tick, CAT_ECONOMY, f"{v.name} shared 1 food with {best_target.name}")
                        v.current_goal = None; _executed = True
                    else:
                        # Walk toward hungry villager
                        v.target_x = int(best_target.x)
                        v.state = "walking"; v.current_goal = None; _executed = True

            elif goal == "plant_tree":
                if v.lumber >= 1:
                    col = int(v.x); nt = sum(1 for t in trees if t.alive and abs(t.x - col) < 10)
                    if nt < 2:
                        v.task_timer = 30; _set_bubble(v, "planting"); v.current_goal = None
                        v.state = "planting"; _executed = True

            elif goal == "build_storage":
                if v.lumber >= STORAGE_COST_LUMBER and v.stone >= STORAGE_COST_STONE:
                    site = _find_storage_site(structures, trees, heights, world, int(v.x))
                    if site is not None:
                        sx, sy = site
                        _level_foundation(sx, STORAGE_WIDTH, heights, world, v, structures)
                        sy = heights[sx] - STORAGE_HEIGHT
                        s = Structure("storage", sx, sy, STORAGE_WIDTH, STORAGE_HEIGHT)
                        s.under_construction = True; s.build_progress = 0.0
                        structures.append(s); v.target_x = sx; v.build_type = "storage"
                        v.building_target = s
                        v.lumber -= STORAGE_COST_LUMBER; v.stone -= STORAGE_COST_STONE
                        v.build_total_time = STORAGE_BUILD_FRAMES; v.task_timer = STORAGE_BUILD_FRAMES
                        _set_bubble(v, "building"); v.current_goal = None
                        v.state = "building" if abs(int(v.x) - sx) <= 1 else "walking"; _executed = True

            elif goal == "build_bank":
                if v.lumber >= BANK_COST_LUMBER and v.stone >= BANK_COST_STONE:
                    site = _find_bank_site(structures, trees, heights, world, int(v.x))
                    if site is not None:
                        sx, sy = site
                        _level_foundation(sx, BANK_WIDTH, heights, world, v, structures)
                        sy = heights[sx] - BANK_HEIGHT
                        s = Structure("bank", sx, sy, BANK_WIDTH, BANK_HEIGHT)
                        s.under_construction = True; s.build_progress = 0.0
                        structures.append(s); v.target_x = sx; v.build_type = "bank"
                        v.building_target = s
                        v.lumber -= BANK_COST_LUMBER; v.stone -= BANK_COST_STONE
                        v.build_total_time = BANK_BUILD_FRAMES; v.task_timer = BANK_BUILD_FRAMES
                        _set_bubble(v, "building"); v.current_goal = None
                        v.state = "building" if abs(int(v.x) - sx) <= 1 else "walking"; _executed = True

            elif goal == "withdraw_storage":
                if storage is not None:
                    if abs(int(v.x) - storage.x) <= 2:
                        # At storage: withdraw what we need
                        if v.lumber == 0 and storage.stored_lumber > 0:
                            amt = min(2, storage.stored_lumber)
                            v.lumber += amt; storage.stored_lumber -= amt
                        if v.food == 0 and storage.stored_food > 0:
                            amt = min(2, storage.stored_food)
                            v.food += amt; storage.stored_food -= amt
                        if v.stone == 0 and storage.stored_stone > 0:
                            amt = min(2, storage.stored_stone)
                            v.stone += amt; storage.stored_stone -= amt
                        v.current_goal = None; _executed = True
                    else:
                        v.target_x = storage.x
                        v.state = "walking"; v.current_goal = None; _executed = True

            elif goal == "deposit_storage":
                if storage is not None:
                    if abs(int(v.x) - storage.x) <= 2:
                        # At storage: deposit excess
                        if v.lumber > STORAGE_DEPOSIT_THRESHOLD_LUMBER and storage.stored_lumber < STORAGE_MAX_LUMBER:
                            amt = min(v.lumber - STORAGE_DEPOSIT_THRESHOLD_LUMBER, STORAGE_MAX_LUMBER - storage.stored_lumber)
                            v.lumber -= amt; storage.stored_lumber += amt
                        if v.stone > STORAGE_DEPOSIT_THRESHOLD_STONE and storage.stored_stone < STORAGE_MAX_STONE:
                            amt = min(v.stone - STORAGE_DEPOSIT_THRESHOLD_STONE, STORAGE_MAX_STONE - storage.stored_stone)
                            v.stone -= amt; storage.stored_stone += amt
                        if v.food > STORAGE_DEPOSIT_THRESHOLD_FOOD and storage.stored_food < STORAGE_MAX_FOOD:
                            amt = min(v.food - STORAGE_DEPOSIT_THRESHOLD_FOOD, STORAGE_MAX_FOOD - storage.stored_food)
                            v.food -= amt; storage.stored_food += amt
                        # Deposit gold to bank if available
                        bank = _get_bank(structures)
                        if bank is not None and v.gold > 0:
                            bank.stored_gold += v.gold; v.gold = 0
                        v.current_goal = None; _executed = True
                    else:
                        v.target_x = storage.x
                        v.state = "walking"; v.current_goal = None; _executed = True

            elif goal == "flatten_terrain":
                steep = _find_steep_spot(heights, world, near_x=int(v.x), radius=12)
                if steep is not None and random.random() < 0.4:
                    v.flatten_target = steep; v.target_x = steep; v.task_timer = FLATTEN_DURATION
                    v.current_goal = None
                    v.state = "flattening" if abs(int(v.x) - steep) <= 1 else "walking"; _executed = True
                else:
                    extreme = _find_extreme_terrain_near_home(v, heights, world)
                    if extreme is not None:
                        v.flatten_target = extreme; v.target_x = extreme; v.task_timer = FLATTEN_DURATION
                        v.current_goal = None
                        v.state = "flattening" if abs(int(v.x) - extreme) <= 1 else "walking"; _executed = True

            # --- Fallback: explore if goal couldn't be executed ---
            if not _executed:
                v.current_goal = None
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
            log_event(sim_tick, CAT_BIRTH, f"{baby.name} ({baby.trait}) immigrated at x={col}")
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
            log_event(sim_tick, CAT_BIRTH, f"{v.name} had a child: {baby.name} ({baby.trait}) at x={col}")
            return
