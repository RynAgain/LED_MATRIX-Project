"""Structure-related helpers: finding build sites, bridge logic, foundation leveling, ownership."""

import random

from .constants import (
    CAMPFIRE_MIN_SPACING, WORLD_WIDTH, DISPLAY_HEIGHT,
    BRIDGE_MAX_GAP, WATER, GRASS, DIRT, STONE, AIR, MINE_MAX_DEPTH,
    CAMPFIRE_LOW_FUEL_THRESHOLD, CREMATION_FLASH_FRAMES,
)
from .utils import _clamp
from .terrain import _get_valley_cols


def _min_campfire_distance(x, structures):
    md = 999
    for s in structures:
        if s.type == "campfire":
            md = min(md, abs(s.x - x))
    return md

def _find_water_gap(world, heights, start_x, direction):
    """Scan from start_x in direction to find a water gap. Returns (start, end, surface_y) or None."""
    x = start_x
    water_start = None
    water_end = None
    water_surface_y = None
    scan_limit = 0
    while 0 <= x < WORLD_WIDTH and scan_limit < 20:
        scan_limit += 1
        col_has_water = False
        for y in range(DISPLAY_HEIGHT):
            if world[y][x] == WATER:
                col_has_water = True
                if water_surface_y is None or y < water_surface_y:
                    water_surface_y = y
                break
        if col_has_water:
            if water_start is None:
                water_start = x
            water_end = x
        else:
            if water_start is not None:
                break
        x += direction
    if water_start is None or water_end is None:
        return None
    if water_start > water_end:
        water_start, water_end = water_end, water_start
    gap_width = water_end - water_start + 1
    if gap_width > BRIDGE_MAX_GAP or gap_width < 1:
        return None
    return (water_start, water_end, water_surface_y)

def _find_bridge_at(x, structures):
    """Check if a bridge covers column x. Returns the bridge Structure or None."""
    for s in structures:
        if s.type == "bridge" and s.x <= x < s.x + s.width:
            return s
    return None

def _find_campfire_site(structures, trees, heights, world):
    vc = _get_valley_cols(world)
    cands = list(range(8, WORLD_WIDTH - 8))
    random.shuffle(cands)
    for x in cands:
        if x in vc: continue
        if _min_campfire_distance(x, structures) < CAMPFIRE_MIN_SPACING: continue
        if any(s.type in ("house_small", "house_large") and abs(s.x - x) < 3 for s in structures): continue
        if any(t.alive and abs(t.x - x) < 3 for t in trees): continue
        h = heights[x]
        if 0 <= h < DISPLAY_HEIGHT and world[h][x] == GRASS: return x
    return None

def _find_build_site(structures, trees, heights, world, w, h):
    vc = _get_valley_cols(world)
    cands = list(range(4, WORLD_WIDTH - w - 4))
    random.shuffle(cands)
    for x in cands:
        ok = True
        for dx in range(w):
            cx = x + dx
            if cx in vc: ok = False; break
            if cx >= WORLD_WIDTH: ok = False; break
            ch = heights[cx]
            if abs(ch - heights[x]) > 2: ok = False; break
            if 0 <= ch < DISPLAY_HEIGHT and world[ch][cx] == WATER: ok = False; break
        if not ok: continue
        if any(abs(s.x - x) < s.width + 2 for s in structures): continue
        if any(t.alive and abs(t.x - x) < 4 for t in trees): continue
        sy = heights[x] - h
        if sy < 2: continue
        return (x, sy)
    return None

def _find_mine_site(structures, trees, heights, world, near_x):
    vc = _get_valley_cols(world)
    cands = list(range(max(4, near_x - 20), min(WORLD_WIDTH - 4, near_x + 20)))
    random.shuffle(cands)
    for x in cands:
        if x in vc: continue
        if any(s.type == "mine" and abs(s.x - x) < 5 for s in structures): continue
        if any(t.alive and abs(t.x - x) < 3 for t in trees): continue
        h = heights[x]
        if 0 <= h < DISPLAY_HEIGHT and world[h][x] in (GRASS, DIRT): return x
    return None

def _has_mine_at(x, structures):
    for s in structures:
        if s.type == "mine" and s.x == x:
            return True
    return False

def _level_foundation(x, width, heights, world, villager, structures):
    cols = list(range(x, x + width))
    col_heights = [heights[c] for c in cols if 0 <= c < WORLD_WIDTH]
    if not col_heights:
        return
    avg_h = int(round(sum(col_heights) / len(col_heights)))
    needs_leveling = any(abs(h - avg_h) > 1 for h in col_heights)
    if not needs_leveling:
        return
    if villager.stone > 0:
        villager.stone -= 1
    elif villager.lumber > 0:
        villager.lumber -= 1
    for c in cols:
        if c < 0 or c >= WORLD_WIDTH:
            continue
        if _has_mine_at(c, structures):
            continue
        old_h = heights[c]
        if old_h < avg_h:
            for y in range(old_h, avg_h):
                if 0 <= y < DISPLAY_HEIGHT:
                    world[y][c] = AIR
            heights[c] = avg_h
            if avg_h < DISPLAY_HEIGHT:
                if world[avg_h][c] in (DIRT, STONE):
                    world[avg_h][c] = GRASS
        elif old_h > avg_h:
            for y in range(avg_h, old_h):
                if 0 <= y < DISPLAY_HEIGHT:
                    world[y][c] = DIRT
            if 0 <= avg_h < DISPLAY_HEIGHT:
                world[avg_h][c] = GRASS
            heights[c] = avg_h

def _update_structures(structures, villagers):
    rm = []
    for i,s in enumerate(structures):
        if s.type == "campfire":
            s.fuel -= 1
            if s.fuel <= 0: rm.append(i); continue
        if s.cremation_flash > 0: s.cremation_flash -= 1
    for i in reversed(rm): structures.pop(i)

def _transfer_house_ownership(house, villagers):
    best = None
    best_dist = 999
    for v in villagers:
        if v.home is None:
            d = abs(int(v.x) - house.x)
            if d < best_dist:
                best_dist = d
                best = v
    if best is not None:
        house.owner = best
        best.home = house
    else:
        house.owner = None

def _claim_unowned_house(villager, structures):
    best = None
    best_dist = 999
    for s in structures:
        if s.type in ("house_small", "house_large") and s.owner is None and not s.under_construction:
            d = abs(int(villager.x) - s.x)
            if d < best_dist:
                best_dist = d
                best = s
    if best is not None:
        best.owner = villager
        villager.home = best
        return True
    return False
