"""Raycast renderer: textured walls, fog, sprites, HUD.

Per-frame cost model: 64 DDA casts in pure Python (cheap: grid is
24x24), then one cached 1px strip paste per column, one paste per
visible sprite slice, and a handful of HUD draws. Texture scaling is
cached by (texture, column, height, band), so after a second or two of
play almost every strip is a dict hit.
"""

import math

from PIL import Image, ImageDraw

from src.display._fonts import _draw_text, _text_width
from .constants import (
    WIDTH, HEIGHT, FOV, MAX_DEPTH, WALL_SCALE, TEX_SIZE, SHADE_BANDS,
    SIDE_DIM, FOG_BASE, FOG_STEP, FOG_MIN, FLICKER_DEPTH, FLICKER_HZ,
    CEILING, FLOOR_NEAR, FLOOR_FAR, T_WALL, T_DOOR, T_LOCKED, T_STAIRS,
    PHASE_DESCEND, PHASE_DEATH, DESCEND_TIME, DEATH_TIME, HERO_MAX_HP,
)

HORIZON = HEIGHT // 2


def _mix(c0, c1, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a + (b - a) * t) for a, b in zip(c0, c1))


def _scale(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


# ---------------------------------------------------------------------------
# procedural textures
# ---------------------------------------------------------------------------

def _tex_brick(rng, base=(96, 82, 74), mortar=(52, 44, 40)):
    img = Image.new("RGB", (TEX_SIZE, TEX_SIZE), base)
    d = ImageDraw.Draw(img)
    for row in range(4):
        y = row * 4
        d.line([(0, y), (TEX_SIZE - 1, y)], fill=mortar)
        off = 0 if row % 2 == 0 else 4
        for x in range(off, TEX_SIZE + 1, 8):
            d.line([(x, y), (x, y + 3)], fill=mortar)
    # Grime speckle.
    for _ in range(26):
        x, y = rng.randrange(TEX_SIZE), rng.randrange(TEX_SIZE)
        img.putpixel((x, y), _scale(img.getpixel((x, y)),
                                    rng.uniform(0.75, 1.2)))
    return img


def _tex_moss(rng):
    img = _tex_brick(rng)
    for _ in range(30):
        x, y = rng.randrange(TEX_SIZE), rng.randrange(TEX_SIZE - 6) + 6
        img.putpixel((x, y), _mix(img.getpixel((x, y)), (52, 96, 44),
                                  rng.uniform(0.4, 0.9)))
    return img


def _tex_cracked(rng):
    img = _tex_brick(rng)
    d = ImageDraw.Draw(img)
    x, y = rng.randrange(4, 12), 0
    while y < TEX_SIZE - 1:
        nx = max(1, min(TEX_SIZE - 2, x + rng.randint(-2, 2)))
        d.line([(x, y), (nx, y + 2)], fill=(30, 24, 22))
        x, y = nx, y + 2
    return img


def _tex_torch(rng):
    """Brick with a sconce: drawn bright and excluded from full fog."""
    img = _tex_brick(rng)
    d = ImageDraw.Draw(img)
    cx = TEX_SIZE // 2
    d.line([(cx, 9), (cx, 12)], fill=(70, 48, 26))
    d.point((cx, 8), fill=(255, 196, 60))
    d.point((cx - 1, 7), fill=(255, 140, 30))
    d.point((cx + 1, 7), fill=(255, 140, 30))
    d.point((cx, 6), fill=(255, 230, 140))
    return img


def _tex_door(locked):
    img = Image.new("RGB", (TEX_SIZE, TEX_SIZE), (92, 62, 36))
    d = ImageDraw.Draw(img)
    for x in range(0, TEX_SIZE, 4):
        d.line([(x, 0), (x, TEX_SIZE - 1)], fill=(64, 42, 24))
    d.rectangle([0, 0, TEX_SIZE - 1, TEX_SIZE - 1], outline=(50, 34, 20))
    if locked:
        # Iron banding and a keyhole plate.
        d.line([(0, 4), (TEX_SIZE - 1, 4)], fill=(120, 120, 130))
        d.line([(0, 11), (TEX_SIZE - 1, 11)], fill=(120, 120, 130))
        d.rectangle([6, 6, 9, 9], fill=(150, 150, 160))
        d.point((7, 7), fill=(20, 20, 24))
        d.point((8, 8), fill=(20, 20, 24))
    else:
        d.ellipse([11, 7, 13, 9], fill=(160, 140, 80))
    return img


TEX_BRICK, TEX_MOSS, TEX_CRACK, TEX_TORCH, TEX_DOOR, TEX_LOCK = range(6)


# ---------------------------------------------------------------------------
# sprites
# ---------------------------------------------------------------------------

def _sprite(pixels, palette):
    """Tiny RGBA sprite from an ASCII grid ('.' = transparent)."""
    h = len(pixels)
    w = len(pixels[0])
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for y, row in enumerate(pixels):
        for x, ch in enumerate(row):
            if ch != ".":
                img.putpixel((x, y), palette[ch] + (255,))
    return img


SPRITES = {
    "slime": _sprite([
        "........",
        "..gggg..",
        ".gGGGGg.",
        ".gGwGwg.",
        "gGGGGGGg",
        "gGGGGGGg",
        ".gggggg.",
        "........",
    ], {"g": (40, 130, 50), "G": (70, 190, 80), "w": (240, 250, 240)}),
    "bat": _sprite([
        "w......w",
        "ww.pp.ww",
        ".wwPPww.",
        "..PrrP..",
        "..PPPP..",
        "...PP...",
        "........",
        "........",
    ], {"w": (90, 70, 110), "p": (140, 110, 160), "P": (110, 85, 130),
        "r": (230, 60, 60)}),
    "skeleton": _sprite([
        "..www...",
        "..wKw...",
        "...w....",
        ".wwwww..",
        "..www...",
        "..w.w...",
        "..w.w...",
        ".ww.ww..",
    ], {"w": (225, 225, 210), "K": (30, 30, 30)}),
    "gold": _sprite([
        "........",
        "........",
        "........",
        "...yy...",
        "..yYYy..",
        "..yYYy..",
        "...yy...",
        "........",
    ], {"y": (180, 140, 20), "Y": (255, 220, 70)}),
    "potion": _sprite([
        "........",
        "...ww...",
        "...ww...",
        "..rRRr..",
        ".rRRRRr.",
        ".rRRRRr.",
        "..rrrr..",
        "........",
    ], {"w": (200, 210, 220), "r": (150, 30, 40), "R": (230, 60, 80)}),
    "key": _sprite([
        "........",
        ".yy.....",
        "y..y....",
        ".yy.yyyy",
        ".......y",
        ".....y.y",
        "........",
        "........",
    ], {"y": (255, 210, 60)}),
}


# ---------------------------------------------------------------------------
# renderer
# ---------------------------------------------------------------------------

class Renderer:
    def __init__(self, seed=7):
        import random
        rng = random.Random(seed)   # textures are artwork: fixed per boot
        base = {
            TEX_BRICK: _tex_brick(rng),
            TEX_MOSS: _tex_moss(rng),
            TEX_CRACK: _tex_cracked(rng),
            TEX_TORCH: _tex_torch(rng),
            TEX_DOOR: _tex_door(False),
            TEX_LOCK: _tex_door(True),
        }
        # Pre-shade every texture: [tex][side][band] -> RGB image.
        self.shaded = {}
        for tid, img in base.items():
            for side in (0, 1):
                for band in range(SHADE_BANDS):
                    k = (1.0 - band / (SHADE_BANDS - 0.4))
                    if side:
                        k *= SIDE_DIM
                    self.shaded[(tid, side, band)] = img.point(
                        lambda v, k=k: int(v * k))
        self._strip_cache = {}
        self._sprite_cache = {}
        self._bg_cache = {}
        self.zbuf = [MAX_DEPTH] * WIDTH
        self._vignette = self._build_vignette()
        self._black = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        self._red = Image.new("RGB", (WIDTH, HEIGHT), (120, 8, 8))

    # -- static layers ---------------------------------------------------------
    def _background(self, depth, light_q):
        key = (depth, light_q)
        bg = self._bg_cache.get(key)
        if bg is not None:
            return bg
        k = 0.75 + 0.25 * (light_q / 3.0)
        deep = max(0.45, 1.0 - (depth - 1) * 0.06)
        img = Image.new("RGB", (WIDTH, HEIGHT))
        d = ImageDraw.Draw(img)
        for y in range(HORIZON):
            t = y / HORIZON
            d.line([(0, y), (WIDTH - 1, y)],
                   fill=_scale(_mix(_scale(CEILING, 0.4), CEILING, t),
                               k * deep))
        for y in range(HORIZON, HEIGHT):
            t = (y - HORIZON) / (HEIGHT - HORIZON)
            d.line([(0, y), (WIDTH - 1, y)],
                   fill=_scale(_mix(FLOOR_FAR, FLOOR_NEAR, t), k * deep))
        if len(self._bg_cache) > 24:
            self._bg_cache.clear()
        self._bg_cache[key] = img
        return img

    def _build_vignette(self):
        img = Image.new("L", (WIDTH, HEIGHT), 0)
        d = ImageDraw.Draw(img)
        for i in range(6):
            a = 110 - i * 18
            d.rectangle([i, i, WIDTH - 1 - i, HEIGHT - 1 - i], outline=a)
        return img

    # -- walls ---------------------------------------------------------------
    def _tex_for(self, fm, mx, my, tile):
        if tile == T_DOOR:
            return TEX_DOOR
        if tile == T_LOCKED:
            return TEX_LOCK
        if (mx, my) in fm.torches:
            return TEX_TORCH
        # Deterministic variety without storing a texture map.
        h = (mx * 928371 + my * 689287) & 0xFF
        if h < 40:
            return TEX_MOSS
        if h < 72:
            return TEX_CRACK
        return TEX_BRICK

    def _cast(self, fm, px, py, ang):
        """One DDA ray.

        Returns (dist, tex_id, tex_x, side, door_open, behind) where
        ``behind`` is the continuation hit past a partially open door --
        so a lifting door shows the room beyond through the growing gap
        instead of a void.
        """
        rdx = math.cos(ang)
        rdy = math.sin(ang)
        mx, my = int(px), int(py)
        ddx = abs(1.0 / rdx) if rdx else 1e30
        ddy = abs(1.0 / rdy) if rdy else 1e30
        if rdx < 0:
            stepx, sdx = -1, (px - mx) * ddx
        else:
            stepx, sdx = 1, (mx + 1.0 - px) * ddx
        if rdy < 0:
            stepy, sdy = -1, (py - my) * ddy
        else:
            stepy, sdy = 1, (my + 1.0 - py) * ddy

        door_hit = None
        for _ in range(64):
            if sdx < sdy:
                sdx += ddx
                mx += stepx
                side = 0
            else:
                sdy += ddy
                my += stepy
                side = 1
            tile = fm.tile(mx, my)
            if tile == T_WALL or (
                    tile in (T_DOOR, T_LOCKED) and fm.blocks_ray(mx, my)):
                if side == 0:
                    dist = sdx - ddx
                    wall_x = py + dist * rdy
                else:
                    dist = sdy - ddy
                    wall_x = px + dist * rdx
                wall_x -= math.floor(wall_x)
                door = fm.doors.get((mx, my))
                open_t = door.open_t if door is not None else 0.0
                hit = (max(0.05, dist), self._tex_for(fm, mx, my, tile),
                       min(TEX_SIZE - 1, int(wall_x * TEX_SIZE)), side,
                       open_t)
                if open_t > 0.0 and door_hit is None:
                    door_hit = hit          # see through the gap: keep going
                    continue
                if door_hit is not None:
                    return door_hit + (hit,)
                return hit + (None,)
        far = (MAX_DEPTH, TEX_BRICK, 0, 0, 0.0)
        if door_hit is not None:
            return door_hit + (far,)
        return far + (None,)

    def _strip(self, tex_id, tex_x, height, side, band):
        key = (tex_id, tex_x, height, side, band)
        strip = self._strip_cache.get(key)
        if strip is None:
            col = self.shaded[(tex_id, side, band)].crop(
                (tex_x, 0, tex_x + 1, TEX_SIZE))
            strip = col.resize((1, height), Image.NEAREST)
            if len(self._strip_cache) > 60000:
                self._strip_cache.clear()
            self._strip_cache[key] = strip
        return strip

    def _wall_strip(self, frame, col, dist, tex_id, tex_x, side, fog):
        """Draw one full wall column (no door slide)."""
        h = min(HEIGHT * 3, max(1, int(WALL_SCALE * HEIGHT / dist)))
        band = min(SHADE_BANDS - 1, int(dist / fog * SHADE_BANDS))
        if tex_id == TEX_TORCH:
            band = min(band, SHADE_BANDS // 2)       # sconces glow in fog
        if band >= SHADE_BANDS - 1:
            return                                   # fully fogged
        strip = self._strip(tex_id, tex_x, h, side, band)
        frame.paste(strip, (col, HORIZON - h // 2))

    # -- sprites --------------------------------------------------------------
    def _sprite_scaled(self, name, size, band, flash):
        key = (name, size, band, flash)
        img = self._sprite_cache.get(key)
        if img is None:
            base = SPRITES[name]
            if flash:
                white = Image.new("RGBA", base.size, (255, 255, 255, 0))
                white.putalpha(base.split()[3])
                base = white
            img = base.resize((size, size), Image.NEAREST)
            if band and not flash:
                k = 1.0 - band / (SHADE_BANDS - 0.4)
                r, g, b, a = img.split()
                img = Image.merge("RGBA", (
                    r.point(lambda v: int(v * k)),
                    g.point(lambda v: int(v * k)),
                    b.point(lambda v: int(v * k)), a))
            if len(self._sprite_cache) > 4000:
                self._sprite_cache.clear()
            self._sprite_cache[key] = img
        return img

    def _draw_sprites(self, frame, game, fog):
        hero = game.hero
        items = []
        for e in game.enemies:
            bob = math.sin(e.anim * 6.0) * (2 if e.kind == "bat" else 0.5)
            items.append((e.x, e.y, e.kind, e.flash > 0, bob,
                          -8 if e.kind == "bat" else 0))
        for p in game.pickups:
            items.append((p.x, p.y, p.kind, False, 0.0, 4))

        cs = math.cos(hero.heading)
        sn = math.sin(hero.heading)
        plane = math.tan(FOV / 2.0)
        ordered = sorted(
            items, key=lambda it: -((it[0] - hero.x) ** 2 +
                                    (it[1] - hero.y) ** 2))
        for (sx, sy, name, flash, bob, lift) in ordered:
            rx = sx - hero.x
            ry = sy - hero.y
            # Camera space: depth along view, lateral against the plane.
            depth = rx * cs + ry * sn
            lateral = -rx * sn + ry * cs
            if depth <= 0.2 or depth > MAX_DEPTH:
                continue
            screen_x = int(WIDTH / 2 * (1 + lateral / (depth * plane)))
            size = max(2, min(48, int(HEIGHT * 0.55 / depth)))
            band = min(SHADE_BANDS - 1, int(depth / fog * SHADE_BANDS))
            if band >= SHADE_BANDS - 1 and not flash:
                continue
            img = self._sprite_scaled(name, size, band, flash)
            top = HORIZON - size // 2 + int(size * 0.25) + int(bob) + int(
                lift * size / 16.0)
            left = screen_x - size // 2
            # Column-wise z-test against the wall buffer.
            x0 = max(0, left)
            x1 = min(WIDTH, left + size)
            col = x0
            while col < x1:
                if self.zbuf[col] > depth:
                    run = col
                    while run < x1 and self.zbuf[run] > depth:
                        run += 1
                    slice_ = img.crop((col - left, 0, run - left, size))
                    frame.paste(slice_, (col, top), slice_)
                    col = run
                else:
                    col += 1

    # -- HUD -------------------------------------------------------------------
    def _draw_hud(self, frame, game):
        d = ImageDraw.Draw(frame)
        hero = game.hero
        # Hearts: HERO_MAX_HP hp over 3 hearts, 2 hp each.
        for i in range(HERO_MAX_HP // 2):
            x = 2 + i * 6
            full = hero.hp >= (i + 1) * 2
            half = hero.hp == i * 2 + 1
            color = (220, 40, 50) if (full or half) else (60, 24, 26)
            d.point((x, 2), fill=color)
            d.point((x + 2, 2), fill=color)
            d.line([(x - 1, 3), (x + 3, 3)], fill=color)
            d.line([(x, 4), (x + 2, 4)], fill=color)
            d.point((x + 1, 5), fill=color)
            if half:
                dark = (60, 24, 26)
                d.point((x + 2, 2), fill=dark)
                d.line([(x + 2, 3), (x + 3, 3)], fill=dark)
                d.point((x + 2, 4), fill=dark)
        # Potions: small red dots under the hearts.
        for i in range(hero.potions):
            d.point((2 + i * 3, 8), fill=(230, 60, 80))
        # Floor number, top right; key icon when held.
        label = "F%d" % game.depth
        _draw_text(d, label, WIDTH - _text_width(label) - 1, 1, (150, 150, 160))
        if hero.has_key:
            img = SPRITES["key"]
            frame.paste(img, (WIDTH - 22, 0), img)
        # Gold toast after a change.
        if game.gold_toast > 0:
            g = "G%d" % hero.gold
            _draw_text(d, g, 2, HEIGHT - 8, (255, 210, 60))

    # -- overlays ---------------------------------------------------------------
    def _overlays(self, frame, game):
        hero = game.hero
        d = ImageDraw.Draw(frame)
        if hero.swing > 0:
            # A quick slash arc, bottom centre.
            t = 1.0 - hero.swing / 0.22
            x0 = 20 + int(24 * t)
            d.arc([x0 - 14, 40, x0 + 14, 68], 200, 340, fill=(235, 235, 245))
            d.arc([x0 - 13, 41, x0 + 13, 67], 210, 330, fill=(150, 150, 170))
        if hero.hurt_flash > 0:
            alpha = self._vignette.point(
                lambda v: int(v * min(1.0, hero.hurt_flash * 3)))
            frame.paste(self._red, (0, 0), alpha)

        if game.phase == PHASE_DESCEND:
            t = game.phase_t / DESCEND_TIME
            fade = math.sin(math.pi * min(1.0, t))
            mask = Image.new("L", (WIDTH, HEIGHT), int(220 * fade))
            frame.paste(self._black, (0, 0), mask)
            if 0.25 < t < 0.85:
                label = "FLOOR %d" % (game.depth + 1)
                _draw_text(ImageDraw.Draw(frame), label,
                           (WIDTH - _text_width(label)) // 2, 28,
                           (200, 200, 210))
        elif game.phase == PHASE_DEATH:
            t = min(1.0, game.phase_t / (DEATH_TIME * 0.4))
            mask = Image.new("L", (WIDTH, HEIGHT), int(200 * t))
            frame.paste(self._red, (0, 0), mask)
            if t >= 1.0:
                d = ImageDraw.Draw(frame)
                _draw_text(d, "RIP", 26, 20, (240, 230, 230))
                s = "FLOOR %d" % game.depth
                _draw_text(d, s, (WIDTH - _text_width(s)) // 2, 30,
                           (200, 170, 170))
                g = "G%d" % game.hero.gold
                _draw_text(d, g, (WIDTH - _text_width(g)) // 2, 40,
                           (255, 210, 60))

    # -- frame ------------------------------------------------------------------
    def render(self, game, now):
        fm = game.floor
        hero = game.hero
        flicker = (1.0
                   + math.sin(now * FLICKER_HZ) * FLICKER_DEPTH * 0.6
                   + math.sin(now * FLICKER_HZ * 2.7 + 1.7)
                   * FLICKER_DEPTH * 0.4)
        fog = max(FOG_MIN, FOG_BASE - (game.depth - 1) * FOG_STEP) * flicker
        light_q = max(0, min(3, int((flicker - 0.86) * 12)))

        frame = self._background(game.depth, light_q).copy()

        cos_fix = [0.0] * WIDTH
        for col in range(WIDTH):
            off = math.atan((2.0 * col / WIDTH - 1.0) * math.tan(FOV / 2.0))
            ang = hero.heading + off
            dist, tex_id, tex_x, side, open_t, behind = self._cast(
                fm, hero.x, hero.y, ang)
            # Correct fisheye with the angle offset from centre.
            fix = math.cos(off)
            dist = max(0.05, dist * fix)
            self.zbuf[col] = dist

            # Scene beyond a lifting door first, then the door flap on top.
            if behind is not None:
                bdist = max(0.05, behind[0] * fix)
                self._wall_strip(frame, col, bdist, behind[1], behind[2],
                                 behind[3], fog)
                if open_t >= 1.0:
                    self.zbuf[col] = bdist
                    continue
                h = min(HEIGHT * 3, max(1, int(WALL_SCALE * HEIGHT / dist)))
                band = min(SHADE_BANDS - 1, int(dist / fog * SHADE_BANDS))
                vis = int(h * (1.0 - open_t))
                if vis > 0 and band < SHADE_BANDS - 1:
                    # The door lifts: its BOTTOM edge stays visible at the
                    # top of the doorway.
                    strip = self._strip(tex_id, tex_x, h, side, band).crop(
                        (0, h - vis, 1, h))
                    frame.paste(strip, (col, HORIZON - h // 2))
                if open_t > 0.5:
                    self.zbuf[col] = bdist   # sprites show through the gap
                continue

            self._wall_strip(frame, col, dist, tex_id, tex_x, side, fog)

        self._draw_sprites(frame, game, fog)
        self._draw_hud(frame, game)
        self._overlays(frame, game)
        return frame
