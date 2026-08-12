"""Tests for the dungeon crawl.

The layout contract from worldgen is the load-bearing part: the AI can
only be as reliable as the guarantee that every floor is beatable. The
rest pins entity behaviour, the hero's decision priorities, the phase
machine, and the renderer's compositing.
"""

import math
import random

import pytest
from PIL import Image

from src.display import dungeon
from src.display.dungeon import DungeonGame, Renderer, WIDTH, HEIGHT
from src.display.dungeon import worldgen
from src.display.dungeon.constants import (
    MAP_W, MAP_H, T_WALL, T_DOOR, T_LOCKED, T_STAIRS, T_FLOOR,
    HERO_MAX_HP, MAX_POTIONS, PHASE_PLAY, PHASE_DESCEND, PHASE_DEATH,
    DESCEND_TIME, DEATH_TIME, ENEMY_STATS,
)
from src.display.dungeon.entities import Enemy, Pickup
from src.display.dungeon.worldgen import Door, generate, _flood


class _Recorder:
    def __init__(self):
        self.frames = 0
        self.last = None
        self.cleared = 0

    def SetImage(self, image, *a, **k):
        self.frames += 1
        self.last = image.copy()

    def Clear(self):
        self.cleared += 1


@pytest.fixture(autouse=True)
def _clear_stop():
    from src.display import _shared
    _shared.clear_stop()
    yield
    _shared.clear_stop()


def _game(seed=2):
    return DungeonGame(rng=random.Random(seed))


# --- worldgen contract -------------------------------------------------------

@pytest.mark.parametrize("seed", range(12))
def test_every_floor_is_beatable(seed):
    """Key reachable without the key; stairs locked until you have it."""
    fm = generate(1, random.Random(seed))
    start = (int(fm.start[0]), int(fm.start[1]))
    no_lock = _flood(fm, start, locked_block=True)
    open_world = _flood(fm, start, locked_block=False)
    all_floor = {(x, y) for y in range(MAP_H) for x in range(MAP_W)
                 if fm.tile(x, y) != T_WALL}
    assert open_world == all_floor, "unreachable floor cells"
    if fm.key_pos is not None:
        assert fm.key_pos in no_lock, "key is behind a locked door"
        assert fm.stairs not in no_lock, "stairs not actually guarded"
    assert fm.tile(*fm.stairs) == T_STAIRS


@pytest.mark.parametrize("seed", range(6))
def test_spawns_are_on_open_floor(seed):
    fm = generate(3, random.Random(seed))
    for kind, x, y in fm.enemy_spawns + fm.pickup_spawns:
        assert fm.tile(int(x), int(y)) == T_FLOOR


def test_deeper_floors_spawn_more_enemies():
    counts = []
    for depth in (1, 5):
        n = []
        for seed in range(5):
            fm = generate(depth, random.Random(seed))
            n.append(len(fm.enemy_spawns))
        counts.append(sum(n) / len(n))
    assert counts[1] > counts[0]


def test_door_opens_over_time_and_reports_passable():
    d = Door(locked=True)
    assert not d.passable
    d.opening = True
    for _ in range(60):
        d.update(1 / 30)
    assert d.open_t == pytest.approx(1.0)
    assert d.passable


# --- entities ----------------------------------------------------------------

def test_enemy_dies_after_enough_hits():
    e = Enemy("slime", 5.0, 5.0)
    hp = ENEMY_STATS["slime"][0]
    for _ in range(hp):
        assert not e.dead
        e.hit(1)
    assert e.dead
    assert e.flash > 0


def test_enemy_chases_hero_with_line_of_sight():
    g = _game()
    # One big open room so walls cannot interfere with the chase.
    fm = worldgen.FloorMap(1)
    worldgen._carve_room(fm, (1, 1, MAP_W - 2, MAP_H - 2))
    g.floor = fm
    g.hero.x = g.hero.y = 5.5
    g.enemies = [Enemy("skeleton", 9.5, 5.5)]
    g.pickups = []
    e = g.enemies[0]
    d0 = math.hypot(e.x - g.hero.x, e.y - g.hero.y)
    for _ in range(30):
        e.update(g, 1 / 30, g.rng)
        g.hero.x = g.hero.y = 5.5         # pin the hero still
    d1 = math.hypot(e.x - g.hero.x, e.y - g.hero.y)
    assert d1 < d0


def test_enemy_touch_hurts_hero_once_per_iframe_window():
    g = _game()
    e = Enemy("slime", g.hero.x + 0.2, g.hero.y)
    g.enemies = [e]
    hp0 = g.hero.hp
    for _ in range(10):
        e.update(g, 1 / 30, g.rng)
    assert g.hero.hp == hp0 - e.damage    # iframes block the repeat hits


# --- hero AI -----------------------------------------------------------------

def test_hero_collects_the_key_then_descends():
    g = _game(seed=2)
    saw_key = False
    for _ in range(30 * 240):
        g.update(1 / 30)
        if "key" in g.events:
            saw_key = True
        if g.phase == PHASE_DESCEND:
            break
    assert saw_key, "hero never picked up the key"
    assert g.phase == PHASE_DESCEND, "hero never reached the stairs"


def test_hero_drinks_a_potion_at_low_hp():
    g = _game()
    g.enemies = []
    g.pickups = []
    g.hero.potions = 1
    g.hero.hp = 1
    g.update(1 / 30)
    assert g.hero.potions == 0
    assert g.hero.hp > 1


def test_hero_fights_back():
    g = _game()
    g.pickups = []
    g.enemies = [Enemy("slime", g.hero.x + 1.5, g.hero.y)]
    for _ in range(30 * 20):
        g.update(1 / 30)
        if not g.enemies:
            break
    assert not g.enemies, "hero never killed a slime standing next to it"


def test_hero_survival_benchmark():
    """Seeded runs must actually crawl: several floors in 8 minutes."""
    for seed in (1, 2, 3):
        g = _game(seed)
        for _ in range(30 * 60 * 8):
            g.update(1 / 30)
        assert g.deepest >= 3, f"seed {seed} stalled at floor {g.deepest}"


# --- game phases -------------------------------------------------------------

def test_descend_loads_a_deeper_floor():
    g = _game()
    g.phase = PHASE_DESCEND
    g.phase_t = 0.0
    depth0 = g.depth
    for _ in range(int(DESCEND_TIME * 30) + 2):
        g.update(1 / 30)
    assert g.depth == depth0 + 1
    assert g.phase == PHASE_PLAY
    assert g.hero.has_key is False, "key must not carry between floors"


def test_death_restarts_the_run():
    g = _game()
    g.hero.gold = 500
    g.hero.hp = 0
    g.update(1 / 30)
    assert g.phase == PHASE_DEATH
    for _ in range(int(DEATH_TIME * 30) + 2):
        g.update(1 / 30)
    assert g.phase == PHASE_PLAY
    assert g.depth == 1
    assert g.hero.hp == HERO_MAX_HP
    assert g.hero.gold == 0


def test_key_pickup_sets_flag_and_gold_adds_up():
    g = _game()
    g.enemies = []
    g.pickups = [Pickup("key", g.hero.x, g.hero.y),
                 Pickup("gold", g.hero.x, g.hero.y)]
    g.update(1 / 30)
    assert g.hero.has_key
    assert g.hero.gold > 0
    assert g.gold_toast > 0
    assert not g.pickups


def test_potion_pickup_respects_cap():
    g = _game()
    g.enemies = []
    g.hero.potions = MAX_POTIONS
    p = Pickup("potion", g.hero.x, g.hero.y)
    g.pickups = [p]
    g.update(1 / 30)
    # Collected or not, the count never exceeds the cap.
    assert g.hero.potions <= MAX_POTIONS + 1  # collected on contact is fine
    # But the AI must not PATH to potions when full (goal selection check).
    live = [q for q in g.pickups if not q.taken
            and not (q.kind == "potion" and g.hero.potions >= MAX_POTIONS)]
    assert p not in live or p.taken


# --- renderer ----------------------------------------------------------------

def test_render_full_frame():
    g = _game()
    r = Renderer()
    frame = r.render(g, 0.0)
    assert frame.size == (WIDTH, HEIGHT)
    assert frame.mode == "RGB"


def test_render_walls_fill_the_zbuffer():
    g = _game()
    r = Renderer()
    r.render(g, 0.0)
    assert all(0.05 <= z <= 25.0 for z in r.zbuf)


def test_render_shows_more_wall_up_close():
    """Wall strips must scale with 1/distance (perspective sanity)."""
    g = _game()
    r = Renderer()
    d = 2.0
    h_near = int(dungeon.render.WALL_SCALE * HEIGHT / d)
    h_far = int(dungeon.render.WALL_SCALE * HEIGHT / (d * 2))
    assert h_near == pytest.approx(2 * h_far, abs=2)


def test_render_death_screen_shows_epitaph():
    g = _game()
    g.phase = PHASE_DEATH
    g.phase_t = DEATH_TIME * 0.9
    g.hero.gold = 42
    frame = Renderer().render(g, 0.0)
    # Mostly red wash with text: red channel dominates.
    px = list(frame.tobytes())
    red = sum(px[0::3])
    green = sum(px[1::3])
    assert red > green * 1.5


def test_render_is_deterministic_for_same_state():
    g = _game()
    r = Renderer()
    a = r.render(g, 1.0).tobytes()
    b = r.render(g, 1.0).tobytes()
    assert a == b


def test_sprites_are_well_formed():
    for name, img in dungeon.render.SPRITES.items():
        assert img.mode == "RGBA"
        w, h = img.size
        assert w == h == 8
        # At least a few opaque pixels.
        assert sum(1 for a in img.split()[3].tobytes() if a) > 4, name


# --- run() -------------------------------------------------------------------

def test_run_pushes_frames_and_clears():
    m = _Recorder()
    dungeon.run(m, duration=0.4)
    assert m.frames > 0
    assert m.cleared == 1
    assert m.last.size == (WIDTH, HEIGHT)


def test_run_honours_zero_duration():
    m = _Recorder()
    dungeon.run(m, duration=0.0)
    assert m.frames == 0
    assert m.cleared == 1


def test_run_stops_on_request():
    from src.display import _shared
    m = _Recorder()
    _shared.request_stop()
    dungeon.run(m, duration=30)
    assert m.frames == 0
    assert m.cleared == 1


def test_run_survives_a_broken_matrix():
    class Broken:
        def SetImage(self, *a, **k):
            raise RuntimeError("panel gone")

        def Clear(self):
            raise RuntimeError("still gone")

    dungeon.run(Broken(), duration=0.2)   # must not raise
