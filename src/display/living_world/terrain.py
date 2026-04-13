"""World generation and terrain modification functions."""

import random
import math
import time

from .constants import (
    WORLD_WIDTH, DISPLAY_HEIGHT, BASE_GROUND, TERRAIN_MIN, TERRAIN_MAX,
    OCTAVES, AIR, GRASS, DIRT, STONE, WATER, SAND, DISPLAY_WIDTH,
    FLATTEN_STEEP_THRESHOLD, FLATTEN_EXTREME_THRESHOLD,
    TREE_BUILDING_MIN_SPACING,
)
from .utils import _clamp
from .entities import Tree


def _generate_height_profile(seed):
    rng = random.Random(seed)
    phases = [rng.uniform(0, 2*math.pi) for _ in OCTAVES]
    heights = []
    for x in range(WORLD_WIDTH):
        h = BASE_GROUND
        for i,(amp,freq) in enumerate(OCTAVES):
            h += amp * math.sin(freq*x + phases[i])
        heights.append(_clamp(int(round(h)), TERRAIN_MIN, TERRAIN_MAX))
    return heights

def _fill_terrain(world, heights):
    for x in range(WORLD_WIDTH):
        sy = heights[x]
        for y in range(DISPLAY_HEIGHT):
            if y < sy: world[y][x] = AIR
            elif y == sy: world[y][x] = GRASS
            elif y <= sy+4: world[y][x] = DIRT
            else: world[y][x] = STONE

def _flood_valleys(world, heights):
    for x in range(1, WORLD_WIDTH-1):
        if heights[x] <= heights[x-1] and heights[x] <= heights[x+1]:
            lr = heights[x]
            for lx in range(x-1,-1,-1):
                if heights[lx] > lr: lr = heights[lx]
                if heights[lx] < heights[lx+1] and lx < x-1: break
            rr = heights[x]
            for rx in range(x+1,WORLD_WIDTH):
                if heights[rx] > rr: rr = heights[rx]
                if heights[rx] < heights[rx-1] and rx > x+1: break
            wl = min(lr, rr, heights[x]+4)
            for fx in range(max(0,x-8), min(WORLD_WIDTH,x+9)):
                s = heights[fx]
                if s < wl:
                    for wy in range(s, wl):
                        if 0 <= wy < DISPLAY_HEIGHT and world[wy][fx] == AIR:
                            world[wy][fx] = WATER

def _guarantee_pond(heights, world):
    has_water = False
    for x in range(WORLD_WIDTH):
        for y in range(DISPLAY_HEIGHT):
            if world[y][x] == WATER:
                has_water = True
                break
        if has_water:
            break
    if has_water:
        return
    # Find the LOWEST terrain point (highest y-value = deepest valley)
    # so that water naturally settles instead of flowing off a hilltop.
    best_x, best_h = WORLD_WIDTH // 2, heights[WORLD_WIDTH // 2]
    for x in range(10, WORLD_WIDTH - 10):
        if heights[x] > best_h:
            best_h = heights[x]
            best_x = x
    pond_width = random.randint(8, 15)
    lower_by = random.randint(2, 3)
    start = max(0, best_x - pond_width // 2)
    end = min(WORLD_WIDTH, start + pond_width)
    # Water level = original surface minus 1 so water sits below surrounding terrain
    water_level = best_h
    for x in range(start, end):
        old_h = heights[x]
        new_h = old_h + lower_by  # Dig DOWN (increase y) to create a basin
        if new_h >= DISPLAY_HEIGHT - 1:
            new_h = DISPLAY_HEIGHT - 2
        # Clear old surface blocks and carve the basin
        for y in range(old_h, new_h + 1):
            if 0 <= y < DISPLAY_HEIGHT:
                world[y][x] = AIR
        # Set new bottom
        if 0 <= new_h < DISPLAY_HEIGHT:
            world[new_h][x] = GRASS
        for y in range(new_h + 1, min(new_h + 5, DISPLAY_HEIGHT)):
            world[y][x] = DIRT
        heights[x] = new_h
        # Fill basin with water from original surface down to the dug floor
        for y in range(water_level, new_h):
            if 0 <= y < DISPLAY_HEIGHT and world[y][x] == AIR:
                world[y][x] = WATER

def _simulate_water(world):
    for y in range(DISPLAY_HEIGHT-2,-1,-1):
        for x in range(WORLD_WIDTH):
            if world[y][x] != WATER: continue
            if y+1 < DISPLAY_HEIGHT and world[y+1][x] == AIR:
                world[y+1][x] = WATER; world[y][x] = AIR; continue
            if y+1 < DISPLAY_HEIGHT and world[y+1][x] != AIR:
                dirs = [1,-1] if random.random() < 0.5 else [-1,1]
                moved = False
                for d in dirs:
                    nx = x+d
                    if 0 < nx < WORLD_WIDTH-1 and world[y][nx] == AIR:
                        world[y][nx] = WATER; world[y][x] = AIR; moved = True; break
                if moved: continue
    for x in range(1, WORLD_WIDTH-1):
        for y in range(DISPLAY_HEIGHT):
            if world[y][x] != WATER: continue
            if y == 0 or world[y-1][x] == AIR:
                for d in [1,-1]:
                    nx = x+d
                    if 0 < nx < WORLD_WIDTH-1 and world[y][nx] == AIR and y+1 < DISPLAY_HEIGHT and world[y+1][nx] != WATER:
                        if random.random() < 0.3:
                            world[y][nx] = WATER; world[y][x] = AIR; break

def _settle_water(world, ticks=20):
    for _ in range(ticks): _simulate_water(world)

def _place_sand(world):
    spots = []
    for y in range(DISPLAY_HEIGHT):
        for x in range(WORLD_WIDTH):
            if world[y][x] != WATER: continue
            for dx in [-1,1]:
                nx = x+dx
                if 0 <= nx < WORLD_WIDTH:
                    if world[y][nx] in (DIRT,GRASS): spots.append((y,nx))
                    if y-1 >= 0 and world[y-1][nx] in (DIRT,GRASS): spots.append((y-1,nx))
    for (sy,sx) in spots: world[sy][sx] = SAND

def _too_close_to_structure(x, structures, spacing=TREE_BUILDING_MIN_SPACING):
    """Return True if x is within `spacing` pixels of any structure's footprint."""
    for s in structures:
        if s.x - spacing <= x <= s.x + s.width - 1 + spacing:
            return True
    return False

def _place_trees(heights, world, structures=None):
    if structures is None:
        structures = []
    trees = []
    vc = set()
    for x in range(WORLD_WIDTH):
        for y in range(DISPLAY_HEIGHT):
            if world[y][x] == WATER:
                for dx in range(-2,3): vc.add(x+dx)
                break
    cands = [x for x in range(4, WORLD_WIDTH-4) if x not in vc]
    random.shuffle(cands)
    chosen = []
    target_trees = random.randint(9, 18)
    for cx in cands:
        if len(chosen) >= target_trees: break
        if not any(abs(cx-e) < 8 for e in chosen):
            if not _too_close_to_structure(cx, structures):
                chosen.append(cx)
    for cx in chosen:
        trees.append(Tree(cx, heights[cx], random.uniform(0.1,0.9), random.randint(5,9), random.randint(2,4), random.randint(0,1)))
    return trees

def _generate_stars():
    return [(random.randint(0,DISPLAY_WIDTH-1), random.randint(0,28)) for _ in range(random.randint(15,25))]

# Module-level time-based cache for valley columns (expensive O(n*m) scan)
_valley_cols_cache = None
_valley_cols_cache_time = 0.0


def _get_valley_cols(world):
    """Return set of columns near water.  Cached for up to 1 second.

    Uses a simple time-based cache to avoid 20+ recomputations per tick
    without requiring an explicit invalidation mechanism.
    """
    global _valley_cols_cache, _valley_cols_cache_time
    now = time.time()
    if _valley_cols_cache is not None and (now - _valley_cols_cache_time) < 1.0:
        return _valley_cols_cache
    vc = set()
    for x in range(WORLD_WIDTH):
        for y in range(DISPLAY_HEIGHT):
            if world[y][x] == WATER:
                for dx in range(-2,3): vc.add(x+dx)
                break
    _valley_cols_cache = vc
    _valley_cols_cache_time = now
    return vc


def _invalidate_valley_cols_cache():
    """Force recomputation on next _get_valley_cols call."""
    global _valley_cols_cache, _valley_cols_cache_time
    _valley_cols_cache = None
    _valley_cols_cache_time = 0.0

def _flatten_terrain(x, heights, world):
    col = x
    if col < 1 or col >= WORLD_WIDTH-1: return False
    h, lh, rh = heights[col], heights[col-1], heights[col+1]
    if h <= lh-FLATTEN_STEEP_THRESHOLD or h <= rh-FLATTEN_STEEP_THRESHOLD:
        nh = h-1
        if nh >= 0 and world[h][col] != WATER:
            world[nh][col] = GRASS
            if world[h][col] == GRASS: world[h][col] = DIRT
            heights[col] = nh; return True
    elif h >= lh+FLATTEN_STEEP_THRESHOLD or h >= rh+FLATTEN_STEEP_THRESHOLD:
        if h < DISPLAY_HEIGHT and world[h][col] != WATER:
            world[h][col] = AIR; nh = h+1
            if nh < DISPLAY_HEIGHT:
                if world[nh][col] in (DIRT,STONE): world[nh][col] = GRASS
            heights[col] = nh; return True
    return False

def _find_steep_spot(heights, world, near_x=None, radius=20):
    s,e = (max(1,near_x-radius),min(WORLD_WIDTH-1,near_x+radius)) if near_x else (1,WORLD_WIDTH-1)
    cands = list(range(s,e)); random.shuffle(cands)
    for col in cands:
        if col < 1 or col >= WORLD_WIDTH-1: continue
        h = heights[col]
        if (abs(h-heights[col-1])>=FLATTEN_STEEP_THRESHOLD or abs(h-heights[col+1])>=FLATTEN_STEEP_THRESHOLD) and world[h][col]!=WATER:
            return col
    return None

def _find_extreme_terrain_near_home(v, heights, world):
    if v.home is None: return None
    for dx in range(-6,7):
        col = v.home.x+dx
        if col < 1 or col >= WORLD_WIDTH-1: continue
        h = heights[col]
        if (abs(h-heights[col-1])>=FLATTEN_EXTREME_THRESHOLD or abs(h-heights[col+1])>=FLATTEN_EXTREME_THRESHOLD) and world[h][col]!=WATER:
            return col
    return None

def _flatten_column_toward(world, heights, x, target_y, rate):
    """Adjust a single column's height toward target_y by up to `rate` blocks.

    Properly updates both the world grid (placing/removing dirt/grass blocks)
    and the heights array.  Returns True if any modification was made.
    """
    if x < 0 or x >= WORLD_WIDTH:
        return False
    current_y = heights[x]
    diff = current_y - target_y
    if diff == 0:
        return False
    # Don't touch water columns
    if world[current_y][x] == WATER:
        return False

    if diff > 0:
        # current_y > target_y  -->  ground is too low, raise it (add dirt above)
        steps = min(rate, diff)
        # Convert old surface grass to dirt before stacking
        if 0 <= current_y < DISPLAY_HEIGHT and world[current_y][x] == GRASS:
            world[current_y][x] = DIRT
        for i in range(1, steps + 1):
            ny = current_y - i
            if 0 <= ny < DISPLAY_HEIGHT:
                world[ny][x] = DIRT
        new_top = current_y - steps
        if 0 <= new_top < DISPLAY_HEIGHT:
            world[new_top][x] = GRASS
        heights[x] = new_top
        return True
    else:
        # diff < 0  -->  ground is too high, lower it (remove blocks from surface)
        steps = min(rate, -diff)
        for i in range(steps):
            cy = current_y + i
            if 0 <= cy < DISPLAY_HEIGHT:
                world[cy][x] = AIR
        new_top = current_y + steps
        if 0 <= new_top < DISPLAY_HEIGHT:
            if world[new_top][x] in (DIRT, STONE):
                world[new_top][x] = GRASS
        heights[x] = new_top
        return True
