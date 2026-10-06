"""Original pixel art, tile layers, and HUD for Zelda Quest."""

import math

from PIL import Image, ImageDraw

from src.display._fonts import _draw_text, _text_width
from src.display._utils import _draw_number
from .game import CHEST, GATE, RELIC, HUD, TILE, WIDTH, HEIGHT, MAX_HEARTS, ROOMS

PALETTE = {
    "o": (22, 29, 38), "g": (62, 171, 65), "G": (128, 222, 87),
    "s": (255, 202, 133), "h": (194, 129, 49), "b": (113, 66, 43),
    "w": (235, 240, 218), "r": (213, 63, 70),
    "p": (100, 82, 160), "P": (176, 137, 208), "y": (255, 219, 89),
    "c": (81, 229, 208),
}
SPRITES = {
    "hero": ("..Gg...", ".GGgg..", "..hsh..", ".ossso.", ".wgggb.", "..ggg..", "..b.b.."),
    "slime": (".......", "..GGg..", ".GGggg.", ".gowog.", ".ggggg.", "..ooo..", "......."),
    "guard": ("..ooo..", ".wwwww.", ".wosow.", "..sss..", ".brrrw.", "..rrr..", "..b.b.."),
    "guardian": (".y...y.", ".pPPpp.", ".PoroP.", ".PrrrP.", "ppPPPpp", ".ppppp.", ".oo.oo."),
    "heart": (".r.r.", "rrrrr", "rrrrr", ".rrr.", "..r.."),
    "rupee": ("..c..", ".cwc.", ".cgc.", ".cgc.", "..c.."),
    "key": (".yy..", ".y.y.", "..y..", "..yy.", "..y.."),
    "relic": ("...y...", "..yyy..", ".yyyyy.", "...o...", "..yyy..", ".yy.yy.", "yyy.yyy"),
}


def _sprite(draw, kind, x, y, flash=False, flip=False):
    rows = SPRITES[kind]
    for dy, row in enumerate(rows):
        for dx, pixel in enumerate(row[::-1] if flip else row):
            if pixel != ".":
                color = (255, 250, 218) if flash else PALETTE[pixel]
                draw.point((x + dx - len(row) // 2, y + dy - len(rows) // 2), fill=color)


def _tile(draw, room, tile, x, y):
    if room == 0:
        draw.rectangle((x, y, x + 7, y + 7), fill=(40, 98, 51))
        draw.point((x + 1, y + 2), fill=(73, 127, 61))
        draw.point((x + 6, y + 6), fill=(58, 116, 57))
        if tile == "#":
            draw.rectangle((x + 3, y + 4, x + 4, y + 7), fill=(98, 65, 40))
            draw.polygon([(x + 4, y), (x + 7, y + 5), (x, y + 5)], fill=(19, 58, 40))
            draw.polygon([(x + 3, y), (x + 6, y + 3), (x + 1, y + 3)], fill=(56, 137, 61))
        elif tile in "~=":
            draw.rectangle((x, y, x + 7, y + 7), fill=(27, 77, 132))
            if tile == "=":
                draw.rectangle((x, y + 1, x + 7, y + 6), fill=(163, 120, 68))
                for offset in (1, 4, 7):
                    draw.line((x + offset, y + 1, x + offset, y + 6), fill=(94, 67, 48))
        else:
            draw.rectangle((x + 1, y + 1, x + 6, y + 6), fill=(113, 123, 65))
    else:
        draw.rectangle((x, y, x + 7, y + 7), fill=(48, 47, 68))
        draw.line((x, y + 7, x + 7, y + 7), fill=(32, 33, 51))
        draw.line((x + 7, y, x + 7, y + 7), fill=(32, 33, 51))
        if tile == "#":
            draw.rectangle((x, y, x + 7, y + 6), fill=(93, 92, 111))
            draw.line((x, y, x + 7, y), fill=(136, 128, 142))
            draw.line((x + 3, y + 1, x + 3, y + 5), fill=(66, 65, 88))


def _center(cell):
    return cell[0] * TILE + TILE // 2, cell[1] * TILE + TILE // 2 + HUD


class Renderer:
    def __init__(self):
        self.backgrounds = []
        for room, rows in enumerate(ROOMS):
            image = Image.new("RGB", (WIDTH, HEIGHT))
            draw = ImageDraw.Draw(image)
            for y, row in enumerate(rows):
                for x, tile in enumerate(row):
                    _tile(draw, room, tile, x * TILE, y * TILE + HUD)
            self.backgrounds.append(image)

    def _scenery(self, draw, game):
        if game.room == 0:
            for y, row in enumerate(ROOMS[0]):
                for x, tile in enumerate(row):
                    if tile == "~":
                        wave = int(game.elapsed * 4 + y) % 5
                        draw.line((x * TILE + wave, y * TILE + HUD + 3,
                                   x * TILE + wave + 2, y * TILE + HUD + 3), fill=(83, 155, 181))
            x, y = _center(CHEST)
            draw.rectangle((x - 3, y - 2, x + 3, y + 2), fill=(111, 65, 32), outline=(237, 180, 67))
            draw.line((x - 2, y - 1, x + 2, y - 1), fill=(24, 27, 30) if game.chest_open else (255, 218, 106))
            draw.point((x, y + 1), fill=(255, 218, 106))
            x, y = _center(GATE)
            draw.rectangle((x - 4, y - 4, x + 3, y + 3), fill=(136, 132, 137))
            draw.rectangle((x - 2, y - 3, x + 2, y + 3), fill=(18, 24, 36))
            if not game.gate_open:
                draw.line((x - 1, y - 2, x - 1, y + 3), fill=(209, 178, 95))
                draw.line((x + 1, y - 2, x + 1, y + 3), fill=(209, 178, 95))
        else:
            for x, y in ((12, 20), (52, 20), (12, 52), (52, 52)):
                draw.rectangle((x - 1, y, x + 1, y + 2), fill=(149, 97, 46))
                flame = int(game.elapsed * 9 + x) % 2
                draw.polygon([(x, y - 4 - flame), (x + 2, y - 1), (x - 2, y - 1)],
                             fill=(255, 157 + flame * 40, 67))
            if not game.enemies and game.phase != "victory":
                x, y = _center(RELIC)
                _sprite(draw, "relic", x, y + int(math.sin(game.elapsed * 4)))

    def _actors(self, draw, game):
        for actor in sorted([game.hero] + game.enemies, key=lambda a: a.screen_position[1]):
            x, y = (int(round(v)) for v in actor.screen_position)
            draw.ellipse((x - 3, y + 2, x + 3, y + 3), fill=(22, 32, 36))
            if actor is game.hero and actor.flash > 0 and int(game.elapsed * 20) % 2:
                continue
            bob = int(actor.motion > 0 and int(game.elapsed * 12) % 2 == 0)
            _sprite(draw, actor.kind, x, y - bob, actor.flash > 0, actor.facing[0] < 0)
            if actor.kind == "hero":
                if actor.facing == (0, -1):
                    draw.line((x - 1, y - 1, x + 1, y - 1), fill=PALETTE["g"])
                if game.swing > 0:
                    self._sword(draw, game, x, y)
            elif actor.kind == "guardian":
                draw.line((x - 3, y - 5, x + 3, y - 5), fill=(61, 24, 40))
                draw.line((x - 3, y - 5, x - 3 + int(6 * actor.hp / 8), y - 5), fill=PALETTE["r"])

    def _sword(self, draw, game, x, y):
        dx, dy = game.hero.facing
        angle = math.atan2(dy, dx) + (0.5 - game.swing / 0.20) * 1.6
        tip = (x + int(math.cos(angle) * 8), y + int(math.sin(angle) * 8))
        draw.line((x + dx * 3, y + dy * 3, *tip), fill=(240, 250, 243))
        draw.point(tip, fill=(147, 224, 255))
        draw.point((x + dx * 3 - dy, y + dy * 3 + dx), fill=PALETTE["y"])

    def _hud(self, image, draw, game):
        draw.rectangle((0, 0, WIDTH - 1, HUD - 1), fill=(14, 19, 30))
        for heart in range(MAX_HEARTS):
            x = 3 + heart * 6
            if heart < game.hero.hp:
                _sprite(draw, "heart", x, 3)
            else:
                draw.point((x, 4), fill=(88, 53, 62))
        _sprite(draw, "rupee", 36, 3)
        _draw_number(image, game.rupees, 40, 1, (165, 237, 199))
        if game.has_key:
            _sprite(draw, "key", 53, 3)
        draw.rectangle((59, 2, 62, 5), fill=(87, 178, 79) if game.room == 0 else (154, 118, 202))

    def render(self, game):
        image = self.backgrounds[game.room].copy()
        draw = ImageDraw.Draw(image)
        self._scenery(draw, game)
        for position, kind in game.pickups.items():
            _sprite(draw, kind, *_center(position))
        self._actors(draw, game)
        if game.phase in ("key", "victory"):
            x, y = game.hero.screen_position
            _sprite(draw, "key" if game.phase == "key" else "relic", int(x), int(y) - 9)
        labels = {"key": "KEY!", "enter": "TEMPLE", "victory": "CLEAR!", "defeat": "RETRY"}
        if game.phase in labels:
            label = labels[game.phase]
            draw.rectangle((4, 53, 59, 63), fill=(16, 21, 34))
            _draw_text(draw, label, (WIDTH - _text_width(label)) // 2, 55, PALETTE["y"])
        self._hud(image, draw, game)
        return image
