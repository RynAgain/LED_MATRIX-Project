"""All visual rendering functions. These write to the pixels image buffer."""

import random
import math

from .constants import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT, WORLD_WIDTH,
    AIR, WATER, GRASS, LEAF, PATH_DIRT,
    BLOCK_COLORS, WATER_SURFACE_COLOR,
    BIRD_FRAMES, BIRD_COLOR,
    SUN_COLOR, MOON_COLOR,
    DYING_LEAF_COLORS, CAMPFIRE_COLORS, CAMPFIRE_LOW_FUEL_COLORS,
    CAMPFIRE_LOW_FUEL_THRESHOLD, LUMBER_BLOCK, WOOD,
    MINE_COLOR, STONE_HOUSE_COLOR,
    BRIDGE_COLOR, BRIDGE_RAILING_COLOR,
    HOUSE_TEMPLATES, HOUSE_COLORS,
    WATCHTOWER_HEIGHT,
    WT_STONE, WT_POLE, WT_PLATFORM, WT_TORCH,
    GRANARY_TEMPLATE, GRANARY_PAL,
    LIGHTNING_BOLT_COLOR,
)
from .utils import _clamp, _apply_ambient, _lerp_color
from .day_night import _compute_sky_colors, _compute_ambient, _seasonal_color_offset


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

def _render_sun_moon(pixels, day_phase):
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
        for dy in range(2):
            for dx in range(2):
                px, py = mx + dx, my + dy
                if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                    pixels[px, py] = MOON_COLOR

def _render_stars(pixels, stars, ambient, sim_tick):
    if ambient >= 0.4: return
    sb = max(0, int(200 * (0.4 - ambient) / 0.25))
    for sx, sy in stars:
        b = _clamp(sb + random.randint(-30, 30), 0, 255)
        if 0 <= sx < DISPLAY_WIDTH and 0 <= sy < DISPLAY_HEIGHT:
            pixels[sx, sy] = (b, b, min(255, b + 20))

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

def _render_terrain(pixels, world, heights, ambient, camera_x, path_wear, day_phase):
    offset = _seasonal_color_offset(day_phase)
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

def _render_trees(pixels, trees, ambient, sim_tick, camera_x, weather, day_phase):
    offset = _seasonal_color_offset(day_phase)
    sway = weather.tree_sway_offset if weather else 0
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
                lc_base = BLOCK_COLORS[LEAF]
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
