"""Campaign rendering and saved-session lifecycle shared by preview and forest demo."""

import time

from src.display._fonts import _draw_text
from . import run_session
from .persistence import SAVE_PATH, SaveStore
from .render import Renderer, _center, _sprite
from .puzzle import STONE_PLATE
from .sluice import COURT_ROOM, WHEELS, CROSSINGS, crossing_open
from .journey import SPIRIT_TILES
from .pulse import SAFE_RUNES, GUARDIAN_HEALTH
from .woodland import BROOK_ROOM, BROOK_ERRANDS, BROOK_CROSSINGS, brook_open
from PIL import ImageDraw


class CampaignRenderer(Renderer):
    guardian_health = GUARDIAN_HEALTH

    def _scenery(self, draw, game):
        super()._scenery(draw, game)
        if game.room == 0:
            for errand in game.journal.available:
                x, y = _center(errand.position)
                if errand.kind == "collect":
                    draw.rectangle((x - 2, y - 2, x + 2, y + 2), fill=(183, 124, 69), outline=(250, 210, 120))
                else:
                    _sprite(draw, "hero", x, y)
                    draw.line((x - 2, y, x + 2, y), fill=(120, 145, 240))
                draw.point((x, y - 5), fill=(255, 219, 89))
        if game.room == 2:
            self._root_pulse(draw, game)
            x, y = _center(STONE_PLATE)
            draw.rectangle((x - 3, y - 2, x + 3, y + 2), outline=(235, 195, 95))
            x, y = _center(game.stone)
            draw.rectangle((x - 3, y - 3, x + 3, y + 3), fill=(133, 141, 150), outline=(225, 226, 214))
        if game.room == BROOK_ROOM:
            self._brook(draw, game)
        if game.room == COURT_ROOM:
            self._canals(draw, game)
        if game.room == 1:
            for position in SPIRIT_TILES:
                x, y = _center(position)
                if not game.has_boots:
                    self._vines(draw, game, x - 4, y - 4)
        errand = game.next_return_errand
        if errand:
            x, y = _center(errand.position)
            if errand.kind == "rescue":
                draw.ellipse((x - 2, y - 3, x + 2, y + 2), fill=(129, 236, 223))
                draw.point((x, y - 1), fill=(27, 70, 76))
            elif errand.kind == "talk":
                _sprite(draw, "hero", x, y)
            else:
                draw.line((x, y + 3, x, y - 3), fill=(151, 109, 59), width=2)
                draw.ellipse((x - 3, y - 5, x + 3, y), fill=(110, 216, 101))
            draw.point((x, y - 6), fill=(255, 219, 89))
        if "restore_village" in game.return_errands and game.room == 0:
            for cell in ((4, 4), (6, 4), (9, 4), (11, 4)):
                x, y = _center(cell)
                _sprite(draw, "hero", x, y)

    def _brook(self, draw, game):
        for position in BROOK_CROSSINGS:
            x, y = _center(position)
            opened = brook_open(position, game.brook_stage)
            draw.rectangle((x - 4, y - 4, x + 3, y + 3),
                           fill=(163, 120, 68) if opened else (27, 77, 132))
            if opened:
                for offset in (-3, 0, 3):
                    draw.line((x + offset, y - 3, x + offset, y + 2), fill=(94, 67, 48))
        x, y = _center(BROOK_ERRANDS[0].position)
        _sprite(draw, "guard", x, y)
        draw.rectangle((x - 2, y, x + 2, y + 2), fill=(85, 142, 203))
        if game.brook_stage < len(BROOK_ERRANDS):
            errand = BROOK_ERRANDS[game.brook_stage]
            x, y = _center(errand.position)
            if errand.kind == "collect":
                for offset in (-2, 0, 2):
                    draw.line((x - 3, y + offset, x + 3, y + offset), fill=(214, 170, 101))
            elif errand.kind == "control":
                draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline=(244, 185, 83))
                draw.line((x - 2, y, x + 2, y), fill=(244, 185, 83))
            draw.point((x, y - 5), fill=(255, 219, 89))

    def _root_pulse(self, draw, game):
        pulse = game.root_pulse
        if pulse.mode not in ("warning", "exposed"):
            return
        for position in SAFE_RUNES:
            x, y = _center(position)
            color = (116, 240, 196) if position == pulse.safe_tile else (71, 85, 83)
            draw.rectangle((x - 3, y - 3, x + 3, y + 3), outline=color)
            draw.line((x - 2, y, x + 2, y), fill=color)
        if game.root_guardian:
            x, y = _center(game.root_guardian.position)
            color = (239, 171, 71) if pulse.mode == "warning" else (116, 240, 196)
            if pulse.mode == "warning":
                draw.rectangle((x - 4, y - 4, x + 4, y + 4), outline=color)
                for position in ((7, 1), (9, 1), (8, 2), (8, 3)):
                    rx, ry = _center(position)
                    draw.line((rx - 2, ry + 2, rx + 2, ry - 2), fill=color)

    def _canals(self, draw, game):
        for y, row in enumerate(game.area.tiles):
            for x, tile in enumerate(row):
                position = (x, y)
                if tile == "~" or position in CROSSINGS:
                    cx, cy = _center(position)
                    dry = position in CROSSINGS and crossing_open(position, game.sluice_stage)
                    color = (164, 132, 84) if dry else (26, 85, 137)
                    draw.rectangle((cx - 4, cy - 4, cx + 3, cy + 3), fill=color)
                    wave = int(game.elapsed * 3 + y) % 4
                    draw.line((cx - 3, cy + wave - 2, cx + 2, cy + wave - 2),
                              fill=(102, 76, 51) if dry else (80, 162, 196))
        for index, position in enumerate(WHEELS):
            x, y = _center(position)
            color = (104, 215, 163) if index < game.sluice_stage else (244, 185, 83)
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline=color)
            draw.line((x - 2, y, x + 2, y), fill=color)
            draw.line((x, y - 2, x, y + 2), fill=color)
            if index == game.sluice_stage:
                draw.point((x, y - 5), fill=(255, 240, 170))

    def render(self, game):
        image = super().render(game)
        draw = ImageDraw.Draw(image)
        if game.phase == "enter":
            draw.rectangle((0, 53, 63, 63), fill=(14, 19, 30))
            _draw_text(draw, game.next_area_name, 2, 55, (255, 219, 89))
        if game.phase == "interact":
            draw.rectangle((0, 53, 63, 63), fill=(14, 19, 30))
            _draw_text(draw, game.interaction_label, 2, 55, (255, 219, 89))
        if game.finished:
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 23, 61, 44), fill=(14, 19, 30))
            _draw_text(draw, "WOODS", 17, 25, (255, 219, 89))
            _draw_text(draw, "END", 23, 36, (255, 219, 89))
        return image


def run(matrix, duration=60, save_path=SAVE_PATH, repeat=False):
    store = SaveStore(save_path)
    game = store.load()
    if repeat and game.finished:
        game.__init__()
    next_save = time.monotonic() + 30
    finished_since = None

    def autosave(current):
        nonlocal next_save, finished_since
        now = time.monotonic()
        if repeat and current.finished:
            if finished_since is None:
                finished_since = now
            elif now - finished_since >= 3:
                current.__init__()
                finished_since = None
        if now >= next_save:
            if store.save(current):
                next_save = time.monotonic() + 30

    try:
        run_session(matrix, duration, game, CampaignRenderer(game.areas), autosave)
    finally:
        store.save(game)
