"""Post-processing light passes applied after all rendering."""

import random

from .constants import (
    LIGHT_MASK, LANTERN_MASK, WATCHTOWER_LIGHT_MASK, TORCH_POST_LIGHT_MASK,
    DISPLAY_WIDTH, DISPLAY_HEIGHT, CAMPFIRE_LOW_FUEL_THRESHOLD,
    MAX_LIGHT_LEVEL,
)


def _apply_campfire_light(pixels, structures, ambient, camera_x):
    if ambient > 0.6: return
    nf = max(0.0, (0.6 - ambient) / 0.45)
    cap = MAX_LIGHT_LEVEL
    for s in structures:
        if s.type != "campfire" or s.fuel <= 0: continue
        fx = s.x - camera_x
        fy = s.y
        for dx, dy, intensity in LIGHT_MASK:
            px, py = fx + dx, fy + dy
            if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                boost = (intensity / 255.0) * 0.85 * nf
                r, g, b = pixels[px, py]
                r = min(cap, int(r + r * boost + 40 * (intensity / 255.0) * nf))
                g = min(cap, int(g + g * boost * 0.6 + 20 * (intensity / 255.0) * nf))
                b = min(cap, int(b + b * boost * 0.3))
                pixels[px, py] = (r, g, b)

def _apply_lantern_light(pixels, structures, ambient, camera_x):
    if ambient > 0.3: return
    nf = max(0.0, (0.3 - ambient) / 0.15)
    cap = MAX_LIGHT_LEVEL
    for s in structures:
        if s.type not in ("house_small", "house_large") or s.under_construction: continue
        lx = s.door_x - camera_x
        ly = s.y + s.height - 2
        if not (0 <= lx < DISPLAY_WIDTH and 0 <= ly < DISPLAY_HEIGHT): continue
        flicker = random.randint(-20, 20)
        pixels[lx, ly] = (min(cap, max(200, 255 + flicker)), min(cap, max(160, 200 + flicker)), 80)
        for dx, dy, intensity in LANTERN_MASK:
            px, py = lx + dx, ly + dy
            if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                boost = (intensity / 255.0) * 0.5 * nf
                r, g, b = pixels[px, py]
                r = min(cap, int(r + r * boost + 20 * (intensity / 255.0) * nf))
                g = min(cap, int(g + g * boost * 0.5 + 10 * (intensity / 255.0) * nf))
                b = min(cap, int(b + b * boost * 0.2))
                pixels[px, py] = (r, g, b)

def _apply_watchtower_light(pixels, structures, ambient, camera_x):
    if ambient > 0.3: return
    nf = max(0.0, (0.3 - ambient) / 0.15)
    cap = MAX_LIGHT_LEVEL
    for s in structures:
        if s.type != "watchtower" or s.under_construction: continue
        lx = s.x - camera_x
        ly = s.y
        for dx, dy, intensity in WATCHTOWER_LIGHT_MASK:
            px, py = lx + dx, ly + dy
            if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                boost = (intensity / 255.0) * 0.7 * nf
                r, g, b = pixels[px, py]
                r = min(cap, int(r + r * boost + 30 * (intensity / 255.0) * nf))
                g = min(cap, int(g + g * boost * 0.5 + 15 * (intensity / 255.0) * nf))
                b = min(cap, int(b + b * boost * 0.2))
                pixels[px, py] = (r, g, b)

def _apply_torch_post_light(pixels, torch_posts, ambient, camera_x):
    if ambient > 0.3: return
    nf = max(0.0, (0.3 - ambient) / 0.15)
    cap = MAX_LIGHT_LEVEL
    for tx, ty in torch_posts:
        lx = tx - camera_x
        ly = ty - 1
        for dx, dy, intensity in TORCH_POST_LIGHT_MASK:
            px, py = lx + dx, ly + dy
            if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                boost = (intensity / 255.0) * 0.5 * nf
                r, g, b = pixels[px, py]
                r = min(cap, int(r + r * boost + 20 * (intensity / 255.0) * nf))
                g = min(cap, int(g + g * boost * 0.4 + 10 * (intensity / 255.0) * nf))
                b = min(cap, int(b + b * boost * 0.2))
                pixels[px, py] = (r, g, b)
