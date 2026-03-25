"""All visual rendering functions. These write to the pixels image buffer."""

import random
import math

from .constants import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT, WORLD_WIDTH,
    AIR, WATER, GRASS, LEAF, PATH_DIRT,
    BLOCK_COLORS, WATER_SURFACE_COLOR,
    BIRD_FRAMES, BIRD_PERCH_FRAME, BIRD_COLOR,
    SUN_COLOR, MOON_COLOR, MOON_PHASE_MASKS, MOON_DARK_COLOR,
    DYING_LEAF_COLORS, CAMPFIRE_COLORS, CAMPFIRE_LOW_FUEL_COLORS,
    CAMPFIRE_LOW_FUEL_THRESHOLD, LUMBER_BLOCK, WOOD,
    MINE_COLOR, STONE_HOUSE_COLOR,
    BRIDGE_COLOR, BRIDGE_RAILING_COLOR,
    HOUSE_TEMPLATES, HOUSE_COLORS,
    WATCHTOWER_HEIGHT,
    WT_STONE, WT_POLE, WT_PLATFORM, WT_TORCH,
    GRANARY_TEMPLATE, GRANARY_PAL,
    LIGHTNING_BOLT_COLOR,
    SHOOTING_STAR_COLOR, SHOOTING_STAR_TAIL_COLOR, SHOOTING_STAR_LENGTH,
    SEASON_GRASS_COLORS, SEASON_LEAF_COLORS,
    DEER_COLOR, DEER_HEAD_COLOR,
    RABBIT_COLOR, RABBIT_EAR_COLOR,
    TILLED_SOIL_COLOR, CROP_COLORS,
    WELL_STONE_COLOR, WELL_WATER_COLOR, WELL_ROOF_COLOR,
    CASTLE_TEMPLATE, CASTLE_PAL,
)
from .utils import _clamp, _apply_ambient, _lerp_color
from .day_night import (
    _compute_sky_colors, _compute_ambient, _seasonal_color_offset, _compute_moon_phase,
    _check_lunar_eclipse,
)


def _render_sky(pixels, day_phase, weather, camera_x):
    sky_top, sky_bot = _compute_sky_colors(day_phase)
    sf = weather.storm_factor
    if sf < 1.0:
        grey = (80, 80, 90)
        sky_top = _lerp_color(sky_top, grey, 1.0 - sf)
        sky_bot = _lerp_color(sky_bot, grey, (1.0 - sf) * 0.5)
    for y in range(DISPLAY_HEIGHT):
        t = y / float(DISPLAY_HEIGHT - 1) if DISPLAY_HEIGHT > 1 else 0.0
        c = _lerp_color(sky_top, sky_bot, t)
        for x in range(DISPLAY_WIDTH):
            pixels[x, y] = c

def _render_sun_moon(pixels, day_phase, elapsed=0.0):
    p = day_phase
    if 0.05 < p < 0.5:
        t = (p - 0.05) / 0.45
        sx = int(5 + t * 53)
        sy = int(18 - 14 * math.sin(t * math.pi))
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                px, py = sx + dx, sy + dy
                if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                    pixels[px, py] = SUN_COLOR
    elif p > 0.65 or p < 0.03:
        if p > 0.65:
            t = (p - 0.65) / 0.35
        else:
            t = (p + 0.35) / 0.35
        mx = int(5 + t * 53)
        my = int(18 - 12 * math.sin(t * math.pi))
        moon_phase = _compute_moon_phase(elapsed)
        mask = MOON_PHASE_MASKS.get(moon_phase)
        if mask is None:
            mask = MOON_PHASE_MASKS["full"]
        # Render 3x3 moon with phase mask
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                row, col = dy + 1, dx + 1
                px, py = mx + dx, my + dy
                if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                    if mask[row][col]:
                        pixels[px, py] = MOON_COLOR
                    elif moon_phase != "new":
                        pixels[px, py] = MOON_DARK_COLOR

def _render_stars(pixels, stars, ambient, sim_tick):
    if ambient >= 0.4: return
    sb = max(0, int(200 * (0.4 - ambient) / 0.25))
    for sx, sy in stars:
        b = _clamp(sb + random.randint(-30, 30), 0, 255)
        if 0 <= sx < DISPLAY_WIDTH and 0 <= sy < DISPLAY_HEIGHT:
            pixels[sx, sy] = (b, b, min(255, b + 20))

def _render_shooting_stars(pixels, shooting_stars, ambient):
    """Render shooting stars as a bright head with a fading tail."""
    if ambient >= 0.3: return
    for ss in shooting_stars:
        # Draw the tail (trail behind the head)
        for i in range(SHOOTING_STAR_LENGTH):
            tx = int(ss.x - ss.dx * i * 0.5)
            ty = int(ss.y - ss.dy * i * 0.5)
            if 0 <= tx < DISPLAY_WIDTH and 0 <= ty < DISPLAY_HEIGHT:
                if i == 0:
                    pixels[tx, ty] = SHOOTING_STAR_COLOR
                else:
                    fade = max(0.2, 1.0 - i / SHOOTING_STAR_LENGTH)
                    c = (int(SHOOTING_STAR_TAIL_COLOR[0] * fade),
                         int(SHOOTING_STAR_TAIL_COLOR[1] * fade),
                         int(SHOOTING_STAR_TAIL_COLOR[2] * fade))
                    pixels[tx, ty] = c

def _render_clouds(pixels, clouds, ambient, camera_x):
    for c in clouds:
        cx = int(c.x) - camera_x
        base_col = _apply_ambient((240, 240, 250), max(0.3, ambient))
        alpha = c.alpha if c.alpha is not None else 0.7
        bg_weight = int((1.0 - alpha) * 10)
        fg_weight = int(alpha * 10)
        for ry in range(c.height):
            for rx in range(c.width):
                if not c.shape[ry][rx]: continue
                px, py = cx + rx, c.y + ry
                if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                    bg = pixels[px, py]
                    pixels[px, py] = (
                        _clamp((bg[0] * bg_weight + base_col[0] * fg_weight) // 10, 0, 255),
                        _clamp((bg[1] * bg_weight + base_col[1] * fg_weight) // 10, 0, 255),
                        _clamp((bg[2] * bg_weight + base_col[2] * fg_weight) // 10, 0, 255),
                    )

def _render_terrain(pixels, world, heights, ambient, camera_x, path_wear, day_phase, season_info=None):
    offset = _seasonal_color_offset(day_phase)
    # Compute blended seasonal colors for grass and leaves
    if season_info is not None:
        current_season, next_season, blend = season_info
        grass_color = _lerp_color(
            SEASON_GRASS_COLORS[current_season],
            SEASON_GRASS_COLORS[next_season],
            blend,
        )
        leaf_color = _lerp_color(
            SEASON_LEAF_COLORS[current_season],
            SEASON_LEAF_COLORS[next_season],
            blend,
        )
    else:
        grass_color = BLOCK_COLORS[GRASS]
        leaf_color = BLOCK_COLORS[LEAF]
    for sx in range(DISPLAY_WIDTH):
        wx = sx + camera_x
        if wx < 0 or wx >= WORLD_WIDTH: continue
        for y in range(DISPLAY_HEIGHT):
            b = world[y][wx]
            if b == AIR or b == WATER: continue
            bc = BLOCK_COLORS.get(b)
            if bc is None: continue
            if b == GRASS and path_wear[wx] >= 50:
                bc = BLOCK_COLORS[PATH_DIRT]
            elif b == GRASS:
                bc = grass_color
            elif b == LEAF:
                bc = leaf_color
            c = _apply_ambient(bc, ambient)
            if b in (GRASS, LEAF):
                c = (_clamp(c[0] + offset[0], 0, 255),
                     _clamp(c[1] + offset[1], 0, 255),
                     _clamp(c[2] + offset[2], 0, 255))
            pixels[sx, y] = c

def _render_water(pixels, world, heights, ambient, sim_tick, camera_x):
    for sx in range(DISPLAY_WIDTH):
        wx = sx + camera_x
        if wx < 0 or wx >= WORLD_WIDTH: continue
        for y in range(DISPLAY_HEIGHT):
            if world[y][wx] != WATER: continue
            is_surface = (y == 0 or world[y - 1][wx] != WATER)
            if is_surface:
                bc = WATER_SURFACE_COLOR
            else:
                bc = BLOCK_COLORS[WATER]
            shimmer = int(15 * math.sin(wx * 0.5 + sim_tick * 0.15))
            c = _apply_ambient(bc, ambient)
            c = (_clamp(c[0], 0, 255), _clamp(c[1], 0, 255), _clamp(c[2] + shimmer, 0, 255))
            if ambient < 0.3 and random.random() < 0.05:
                c = (_clamp(c[0] + 10, 0, 255), _clamp(c[1] + 15, 0, 255), _clamp(c[2] + 30, 0, 255))
            pixels[sx, y] = c

def _render_flowers(pixels, flowers, ambient, camera_x):
    for f in flowers:
        sx = f.x - camera_x
        if 0 <= sx < DISPLAY_WIDTH and 0 <= f.y < DISPLAY_HEIGHT:
            pixels[sx, f.y] = _apply_ambient(f.color, ambient)

def _render_bridges(pixels, structures, ambient, camera_x):
    for s in structures:
        if s.type != "bridge": continue
        for dx in range(s.width):
            sx = s.x + dx - camera_x
            if 0 <= sx < DISPLAY_WIDTH and 0 <= s.y < DISPLAY_HEIGHT:
                pixels[sx, s.y] = _apply_ambient(BRIDGE_COLOR, ambient)
                if dx % 4 == 0 and s.y - 1 >= 0:
                    pixels[sx, s.y - 1] = _apply_ambient(BRIDGE_RAILING_COLOR, ambient)

def _render_structures(pixels, structures, ambient, sim_tick, camera_x, day_phase):
    is_night = _compute_ambient(day_phase) < 0.3
    for s in structures:
        if s.type == "bridge": continue
        if s.type == "campfire":
            sx = s.x - camera_x
            if 0 <= sx < DISPLAY_WIDTH and 0 <= s.y < DISPLAY_HEIGHT:
                if s.fuel < CAMPFIRE_LOW_FUEL_THRESHOLD:
                    ci = (sim_tick // 2 + random.randint(0, 1)) % len(CAMPFIRE_LOW_FUEL_COLORS)
                    pixels[sx, s.y] = CAMPFIRE_LOW_FUEL_COLORS[ci]
                else:
                    ci = (sim_tick // 2 + random.randint(0, 1)) % len(CAMPFIRE_COLORS)
                    pixels[sx, s.y] = CAMPFIRE_COLORS[ci]
        elif s.type == "mine":
            sx = s.x - camera_x
            if 0 <= sx < DISPLAY_WIDTH:
                for dy in range(s.depth + 1):
                    my = s.y + dy
                    if 0 <= my < DISPLAY_HEIGHT:
                        pixels[sx, my] = _apply_ambient(MINE_COLOR, max(0.2, ambient - dy * 0.05))
        elif s.type == "watchtower":
            _render_watchtower(pixels, s, ambient, camera_x, is_night)
        elif s.type == "granary":
            _render_granary(pixels, s, ambient, camera_x)
        elif s.type == "well":
            _render_well(pixels, s, ambient, camera_x)
        elif s.type == "castle":
            _render_castle(pixels, s, ambient, camera_x, is_night)
        elif s.type in ("house_small", "house_large"):
            _render_house(pixels, s, ambient, camera_x, is_night)

def _render_house(pixels, s, ambient, camera_x, is_night):
    level = s.level
    tmpl = HOUSE_TEMPLATES.get(level)
    palette = HOUSE_COLORS.get(level)
    if tmpl is None or palette is None: return
    pal = palette[s.style % len(palette)]
    grid = tmpl['grid']
    rows_to_draw = len(grid)
    if s.under_construction:
        rows_to_draw = max(1, int(len(grid) * s.build_progress))
    draw_rows = grid[-rows_to_draw:] if s.under_construction else grid
    start_y = s.y + (len(grid) - rows_to_draw) if s.under_construction else s.y
    for ri, row in enumerate(draw_rows):
        for ci, ch in enumerate(row):
            if ch == 'A': continue
            px = s.x + ci - camera_x
            py = start_y + ri
            if not (0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT): continue
            if ch == 'W':
                bc = pal['wall']
                if s.stone_built: bc = STONE_HOUSE_COLOR
            elif ch == 'R': bc = pal['roof']
            elif ch == 'D': bc = pal['door']
            elif ch == 'N': bc = pal['window_night'] if is_night else pal['window_day']
            elif ch == 'C': bc = pal.get('chimney') or pal['wall']
            else: bc = pal['wall']
            pixels[px, py] = _apply_ambient(bc, ambient)

def _render_watchtower(pixels, s, ambient, camera_x, is_night):
    bx = s.x - camera_x
    rows_to_draw = WATCHTOWER_HEIGHT
    if s.under_construction:
        rows_to_draw = max(1, int(WATCHTOWER_HEIGHT * s.build_progress))
    draw_start = WATCHTOWER_HEIGHT - rows_to_draw
    for row in range(draw_start, WATCHTOWER_HEIGHT):
        ry = s.y + row
        if row >= 5:
            for dx in range(2):
                px = bx + dx
                if 0 <= px < DISPLAY_WIDTH and 0 <= ry < DISPLAY_HEIGHT:
                    pixels[px, ry] = _apply_ambient(WT_STONE, ambient)
        elif row >= 2:
            if 0 <= bx < DISPLAY_WIDTH and 0 <= ry < DISPLAY_HEIGHT:
                pixels[bx, ry] = _apply_ambient(WT_POLE, ambient)
        elif row == 1:
            for dx in range(2):
                px = bx + dx
                if 0 <= px < DISPLAY_WIDTH and 0 <= ry < DISPLAY_HEIGHT:
                    pixels[px, ry] = _apply_ambient(WT_PLATFORM, ambient)
        elif row == 0:
            if 0 <= bx < DISPLAY_WIDTH and 0 <= ry < DISPLAY_HEIGHT:
                if is_night:
                    pixels[bx, ry] = (255, _clamp(180 + random.randint(-20, 20), 0, 255), 50)
                else:
                    pixels[bx, ry] = _apply_ambient(WT_TORCH, ambient)

def _render_granary(pixels, s, ambient, camera_x):
    grid = GRANARY_TEMPLATE
    pal = GRANARY_PAL
    rows_to_draw = len(grid)
    if s.under_construction:
        rows_to_draw = max(1, int(len(grid) * s.build_progress))
    draw_rows = grid[-rows_to_draw:] if s.under_construction else grid
    start_y = s.y + (len(grid) - rows_to_draw) if s.under_construction else s.y
    for ri, row in enumerate(draw_rows):
        for ci, ch in enumerate(row):
            if ch == 'A': continue
            px = s.x + ci - camera_x
            py = start_y + ri
            if not (0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT): continue
            if ch == 'W': bc = pal['wall']
            elif ch == 'R': bc = pal['roof']
            elif ch == 'D': bc = pal['door']
            else: bc = pal['wall']
            pixels[px, py] = _apply_ambient(bc, ambient)

def _render_well(pixels, s, ambient, camera_x):
    """Render a well structure: stone base with water and small roof post."""
    sx = s.x - camera_x
    if not (0 <= sx < DISPLAY_WIDTH):
        return
    rows_to_draw = s.height
    if s.under_construction:
        rows_to_draw = max(1, int(s.height * s.build_progress))
    # Well is 1 pixel wide, 2 pixels tall:
    #   row 0 (top): roof post / overhang
    #   row 1 (bottom): stone base with water
    base_y = s.y + s.height - 1  # bottom row
    top_y = s.y + s.height - rows_to_draw
    for row_y in range(top_y, s.y + s.height):
        if 0 <= row_y < DISPLAY_HEIGHT:
            if row_y == s.y:  # top row: roof
                pixels[sx, row_y] = _apply_ambient(WELL_ROOF_COLOR, ambient)
            else:  # bottom row: stone with water
                pixels[sx, row_y] = _apply_ambient(WELL_STONE_COLOR, ambient)
    # Water pixel inside the well base
    if rows_to_draw >= 2 and 0 <= base_y < DISPLAY_HEIGHT:
        pixels[sx, base_y] = _apply_ambient(WELL_WATER_COLOR, ambient)

def _render_castle(pixels, s, ambient, camera_x, is_night):
    """Render a castle using CASTLE_TEMPLATE pixel art."""
    grid = CASTLE_TEMPLATE
    pal = CASTLE_PAL
    rows_to_draw = len(grid)
    if s.under_construction:
        rows_to_draw = max(1, int(len(grid) * s.build_progress))
    draw_rows = grid[-rows_to_draw:] if s.under_construction else grid
    start_y = s.y + (len(grid) - rows_to_draw) if s.under_construction else s.y
    for ri, row in enumerate(draw_rows):
        for ci, ch in enumerate(row):
            if ch == 'A':
                continue
            px = s.x + ci - camera_x
            py = start_y + ri
            if not (0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT):
                continue
            if ch == 'W':
                bc = pal['wall']
            elif ch == 'T':
                bc = pal['tower']
            elif ch == 'B':
                bc = pal['battlement']
            elif ch == 'D':
                bc = pal['door']
            elif ch == 'G':
                bc = pal['gate']
            elif ch == 'N':
                bc = pal['window_night'] if is_night else pal['window_day']
            else:
                bc = pal['wall']
            pixels[px, py] = _apply_ambient(bc, ambient)

def _render_trees(pixels, trees, ambient, sim_tick, camera_x, weather, day_phase, season_info=None):
    offset = _seasonal_color_offset(day_phase)
    sway = weather.tree_sway_offset if weather else 0
    # Compute blended seasonal leaf color
    if season_info is not None:
        current_season, next_season, blend = season_info
        seasonal_leaf = _lerp_color(
            SEASON_LEAF_COLORS[current_season],
            SEASON_LEAF_COLORS[next_season],
            blend,
        )
    else:
        seasonal_leaf = BLOCK_COLORS[LEAF]
    for tree in trees:
        if not tree.alive: continue
        sx = tree.x - camera_x
        if tree.on_fire:
            fc = random.choice(CAMPFIRE_COLORS)
            th = max(1, int(tree.trunk_height * tree.growth))
            cr = max(0, int(tree.canopy_radius * max(0, (tree.growth - 0.3) / 0.7)))
            for dy in range(th):
                py = tree.base_y - 1 - dy
                if 0 <= sx < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                    pixels[sx, py] = fc
            if cr > 0:
                top = tree.base_y - 1 - th
                for cy in range(-cr, cr + 1):
                    for cx_off in range(-cr, cr + 1):
                        if cx_off * cx_off + cy * cy <= cr * cr:
                            px = sx + cx_off
                            py = top + cy
                            if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                                pixels[px, py] = random.choice(CAMPFIRE_COLORS)
            continue
        th = max(1, int(tree.trunk_height * tree.growth))
        cr = max(0, int(tree.canopy_radius * max(0, (tree.growth - 0.3) / 0.7)))
        tc = _apply_ambient(BLOCK_COLORS[WOOD], ambient)
        for dy in range(th):
            py = tree.base_y - 1 - dy
            if 0 <= sx < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                pixels[sx, py] = tc
        if cr > 0:
            top = tree.base_y - 1 - th
            if tree.dying:
                idx = min(len(DYING_LEAF_COLORS) - 1, int(tree.dying_progress * len(DYING_LEAF_COLORS)))
                lc_base = DYING_LEAF_COLORS[idx]
            else:
                lc_base = seasonal_leaf
            lc = _apply_ambient(lc_base, ambient)
            lc = (_clamp(lc[0] + offset[0], 0, 255), _clamp(lc[1] + offset[1], 0, 255), _clamp(lc[2] + offset[2], 0, 255))
            if tree.style == 0:
                for cy in range(-cr, cr + 1):
                    for cx_off in range(-cr, cr + 1):
                        if cx_off * cx_off + cy * cy <= cr * cr:
                            px = sx + cx_off + sway
                            py = top + cy
                            if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                                pixels[px, py] = lc
            else:
                for ly in range(cr * 2 + 1):
                    w = max(1, cr - abs(ly - cr) + 1)
                    for lx in range(-w // 2, w // 2 + 1):
                        px = sx + lx + sway
                        py = top + ly - cr
                        if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                            pixels[px, py] = lc

def _render_lumber_items(pixels, lumber_items, ambient, camera_x):
    for it in lumber_items:
        sx = it.x - camera_x
        if 0 <= sx < DISPLAY_WIDTH and 0 <= it.y < DISPLAY_HEIGHT:
            pixels[sx, it.y] = _apply_ambient(BLOCK_COLORS[LUMBER_BLOCK], ambient)

def _render_villagers(pixels, villagers, ambient, sim_tick, camera_x):
    for v in villagers:
        sx = int(v.x) - camera_x
        by = int(v.y) - 1
        hy = by - 1
        if v.state == "resting": continue
        if 0 <= sx < DISPLAY_WIDTH:
            body_c = _apply_ambient(v.body_color, ambient)
            head_c = _apply_ambient(v.head_color, ambient)
            if v.state == "chopping" and sim_tick % 8 < 4:
                body_c = (255, 255, 255)
            elif v.state == "building" and sim_tick % 12 < 6:
                body_c = head_c
            elif v.state == "eating" and sim_tick % 6 < 3:
                body_c = (50, min(body_c[1] + 80, 255), 50)
            if 0 <= by < DISPLAY_HEIGHT:
                pixels[sx, by] = body_c
            if 0 <= hy < DISPLAY_HEIGHT:
                pixels[sx, hy] = head_c
            if v.bubble_timer > 0 and v.bubble_color is not None:
                bub_y = hy - 1
                if 0 <= bub_y < DISPLAY_HEIGHT:
                    pixels[sx, bub_y] = v.bubble_color

def _render_birds(pixels, birds, ambient, sim_tick, camera_x):
    if ambient < 0.3: return
    bc = _apply_ambient(BIRD_COLOR, ambient)
    for b in birds:
        bx = int(b.x) - camera_x
        by_bird = int(b.y)
        if b.perched:
            frame = BIRD_PERCH_FRAME
        else:
            frame = BIRD_FRAMES[b.wing_frame]
        for dx, dy in frame:
            px = bx + dx
            py = by_bird + dy
            if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                pixels[px, py] = bc

def _render_fish_jumps(pixels, fish_jumps, camera_x):
    for fj in fish_jumps:
        sx = fj.x - camera_x
        prog = fj.progress / 16.0
        dy = int(fj.max_height * math.sin(prog * math.pi))
        py = fj.base_y - 1 - dy
        if 0 <= sx < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
            pixels[sx, py] = (160, 160, 180)

def _render_smoke(pixels, smoke_particles, ambient, camera_x):
    for sp in smoke_particles:
        sx = int(sp.x) - camera_x
        sy = int(sp.y)
        if 0 <= sx < DISPLAY_WIDTH and 0 <= sy < DISPLAY_HEIGHT:
            t = sp.age / sp.max_age if sp.max_age > 0 else 1.0
            g = int(120 - 60 * t)
            a_val = max(0.0, 1.0 - t)
            bg = pixels[sx, sy]
            c = (_clamp(int(bg[0] + g * a_val * 0.3), 0, 255),
                 _clamp(int(bg[1] + g * a_val * 0.3), 0, 255),
                 _clamp(int(bg[2] + (g + 10) * a_val * 0.3), 0, 255))
            pixels[sx, sy] = c

def _render_fireflies(pixels, fireflies, sim_tick, camera_x):
    for ff in fireflies:
        sx = int(ff.x) - camera_x
        sy = int(ff.y)
        if 0 <= sx < DISPLAY_WIDTH and 0 <= sy < DISPLAY_HEIGHT:
            gb = int(180 + 60 * math.sin(sim_tick * 0.15 + ff.phase))
            gg = int(200 + 40 * math.sin(sim_tick * 0.15 + ff.phase))
            pixels[sx, sy] = (_clamp(gb, 0, 255), _clamp(gg, 0, 255), 40)

def _render_rain(pixels, rain_drops, camera_x):
    for rd in rain_drops:
        if rd.splash:
            sx = int(rd.splash_x) - camera_x
            sy = int(rd.splash_y)
            if 0 <= sx < DISPLAY_WIDTH and 0 <= sy < DISPLAY_HEIGHT:
                bg = pixels[sx, sy]
                pixels[sx, sy] = (_clamp(bg[0] + 30, 0, 255), _clamp(bg[1] + 30, 0, 255), _clamp(bg[2] + 40, 0, 255))
        else:
            sx = int(rd.x) - camera_x
            sy = int(rd.y)
            if 0 <= sx < DISPLAY_WIDTH and 0 <= sy < DISPLAY_HEIGHT:
                pixels[sx, sy] = rd.color

def _render_lightning(pixels, weather):
    if weather.lightning_flash > 0:
        for y in range(DISPLAY_HEIGHT):
            for x in range(DISPLAY_WIDTH):
                r, g, b = pixels[x, y]
                pixels[x, y] = (_clamp(r + 80, 0, 255), _clamp(g + 80, 0, 255), _clamp(b + 90, 0, 255))
    if weather.lightning_bolt is not None and weather.lightning_bolt_timer > 0:
        bx, by_top, by_bot = weather.lightning_bolt
        for y in range(by_top, min(by_bot + 1, DISPLAY_HEIGHT)):
            lx = bx + random.randint(-1, 1)
            if 0 <= lx < DISPLAY_WIDTH and 0 <= y < DISPLAY_HEIGHT:
                pixels[lx, y] = LIGHTNING_BOLT_COLOR

def _render_torch_posts(pixels, torch_posts, ambient, camera_x):
    is_night = ambient < 0.3
    for tx, ty in torch_posts:
        sx = tx - camera_x
        if 0 <= sx < DISPLAY_WIDTH:
            if 0 <= ty < DISPLAY_HEIGHT:
                pixels[sx, ty] = _apply_ambient((80, 45, 15), ambient)
            top_y = ty - 1
            if 0 <= top_y < DISPLAY_HEIGHT:
                if is_night:
                    pixels[sx, top_y] = (255, _clamp(160 + random.randint(-20, 20), 0, 255), 30)
                else:
                    pixels[sx, top_y] = _apply_ambient((255, 160, 30), ambient)

def _render_grass_fires(pixels, grass_fires, camera_x):
    for gf in grass_fires:
        sx = gf.x - camera_x
        if 0 <= sx < DISPLAY_WIDTH and 0 <= gf.y < DISPLAY_HEIGHT:
            pixels[sx, gf.y] = random.choice(CAMPFIRE_COLORS)

def _render_animals(pixels, animals, heights, ambient, camera_x):
    """Render deer and rabbits on the terrain surface."""
    for animal in animals:
        ax = int(round(animal.x))
        sx = ax - camera_x  # screen x for the animal's main position
        sy = animal.y        # ground surface y

        if animal.animal_type == "deer":
            # Deer: 3px wide, 2px tall
            # Body row at ground level (sy - 1), head 1px ahead at same height
            body_y = sy - 1
            head_y = sy - 1
            body_color = _apply_ambient(DEER_COLOR, ambient)
            head_color = _apply_ambient(DEER_HEAD_COLOR, ambient)
            # Body: 2 pixels at (sx, body_y) and (sx - direction, body_y)
            rear_sx = sx - animal.direction
            head_sx = sx + animal.direction
            # Draw rear body pixel
            if 0 <= rear_sx < DISPLAY_WIDTH and 0 <= body_y < DISPLAY_HEIGHT:
                pixels[rear_sx, body_y] = body_color
            # Draw center body pixel
            if 0 <= sx < DISPLAY_WIDTH and 0 <= body_y < DISPLAY_HEIGHT:
                pixels[sx, body_y] = body_color
            # Draw head pixel (1 ahead in facing direction)
            if 0 <= head_sx < DISPLAY_WIDTH and 0 <= head_y < DISPLAY_HEIGHT:
                pixels[head_sx, head_y] = head_color
            # Draw legs: 1 row below body (at ground level sy) for center
            # Optional: a pixel above center for the back/torso height
            top_y = body_y - 1
            if 0 <= sx < DISPLAY_WIDTH and 0 <= top_y < DISPLAY_HEIGHT:
                pixels[sx, top_y] = body_color

        elif animal.animal_type == "rabbit":
            # Rabbit: 2px wide, 1px tall body at ground level
            body_y = sy - 1
            ear_y = body_y - 1
            body_color = _apply_ambient(RABBIT_COLOR, ambient)
            ear_color = _apply_ambient(RABBIT_EAR_COLOR, ambient)
            # Body pixel
            if 0 <= sx < DISPLAY_WIDTH and 0 <= body_y < DISPLAY_HEIGHT:
                pixels[sx, body_y] = body_color
            # Second body pixel (in direction of movement)
            sx2 = sx + animal.direction
            if 0 <= sx2 < DISPLAY_WIDTH and 0 <= body_y < DISPLAY_HEIGHT:
                pixels[sx2, body_y] = body_color
            # Ear pixel above first body pixel
            if 0 <= sx < DISPLAY_WIDTH and 0 <= ear_y < DISPLAY_HEIGHT:
                pixels[sx, ear_y] = ear_color


def _render_farms(pixels, farms, ambient, camera_x):
    """Render farm plots with tilled soil and crops at various growth stages.

    Each farm is FARM_WIDTH pixels wide, rendered at ground level (farm.y).
    The soil row is drawn at farm.y, and crops grow upward (farm.y - 1).
    """
    for farm in farms:
        for slot in range(farm.width):
            wx = farm.x + slot
            sx = wx - camera_x
            if sx < 0 or sx >= DISPLAY_WIDTH:
                continue
            soil_y = farm.y
            crop_y = farm.y - 1
            # Draw tilled soil at ground level
            if 0 <= soil_y < DISPLAY_HEIGHT:
                pixels[sx, soil_y] = _apply_ambient(TILLED_SOIL_COLOR, ambient)
            # Draw crop based on growth stage
            stage = farm.crop_stage(slot)
            if stage in ("empty", "seeded"):
                continue  # no visible crop pixel
            crop_color = CROP_COLORS.get(stage)
            if crop_color is not None and 0 <= crop_y < DISPLAY_HEIGHT:
                pixels[sx, crop_y] = _apply_ambient(crop_color, ambient)


def _render_boats(pixels, boats, ambient, camera_x):
    """Render active boats on water surface."""
    from .constants import BOAT_COLOR, BOAT_DECK_COLOR
    for boat in boats:
        if not boat.active:
            continue
        sx = int(round(boat.x)) - camera_x
        sy = boat.y
        hull_color = _apply_ambient(BOAT_COLOR, ambient)
        deck_color = _apply_ambient(BOAT_DECK_COLOR, ambient)
        # 3-pixel boat: left hull, center deck, right hull
        for dx in (-1, 0, 1):
            px = sx + dx
            if 0 <= px < DISPLAY_WIDTH and 0 <= sy < DISPLAY_HEIGHT:
                pixels[px, sy] = hull_color if dx != 0 else deck_color


def _render_caravans(pixels, caravans, ambient, camera_x):
    """Render trade caravans as 2px-tall figures with a pack."""
    from .constants import CARAVAN_COLOR, CARAVAN_PACK_COLOR
    for caravan in caravans:
        sx = int(round(caravan.x)) - camera_x
        sy = caravan.y
        body_y = sy - 1
        head_y = sy - 2
        cloak = _apply_ambient(CARAVAN_COLOR, ambient)
        pack = _apply_ambient(CARAVAN_PACK_COLOR, ambient)
        # Body
        if 0 <= sx < DISPLAY_WIDTH and 0 <= body_y < DISPLAY_HEIGHT:
            pixels[sx, body_y] = cloak
        # Head
        if 0 <= sx < DISPLAY_WIDTH and 0 <= head_y < DISPLAY_HEIGHT:
            pixels[sx, head_y] = (200, 160, 120)  # skin
        # Pack on back (offset by -direction)
        pack_x = sx - caravan.direction
        if 0 <= pack_x < DISPLAY_WIDTH and 0 <= body_y < DISPLAY_HEIGHT:
            pixels[pack_x, body_y] = pack


def _render_snow(pixels, snow_flakes, camera_x):
    """Render falling snow particles as white dots."""
    from .constants import SNOW_COLOR
    for sf in snow_flakes:
        sx = int(sf.x) - camera_x
        sy = int(sf.y)
        if 0 <= sx < DISPLAY_WIDTH and 0 <= sy < DISPLAY_HEIGHT:
            pixels[sx, sy] = SNOW_COLOR
