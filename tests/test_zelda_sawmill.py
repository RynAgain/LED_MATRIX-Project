"""Sawmill legal push route and persistent shutter state."""
import copy
import json

import pytest

from src.display.zelda_quest.campaign import CampaignGame
from src.display.zelda_quest.game import Actor, MAX_HEARTS, distance
from src.display.zelda_quest.persistence import SaveStore, decode, encode
from src.display.zelda_quest.preview import CampaignRenderer
from src.display.zelda_quest.woodland import (
    SAWMILL, SAWMILL_ROOM, SAWMILL_LOG, SAWMILL_PLATE, SAWMILL_SHUTTER, SAWMILL_LOG_POSITIONS,
)


@pytest.fixture(scope="module")
def mill_saves():
    game = CampaignGame()
    saves = {}
    for _ in range(30 * 600):
        game.update(1 / 30)
        if game.room == SAWMILL_ROOM:
            saves.setdefault(game.sawmill_log, encode(game))
        if game.room == 2:
            saves["after"] = encode(game)
            break
    assert set(saves) == set(SAWMILL_LOG_POSITIONS) | {"after"}
    assert game.deaths == 0
    return saves


def test_three_legal_pushes_open_real_shutter(mill_saves):
    game = decode(copy.deepcopy(mill_saves[SAWMILL_LOG]))
    game.enemies.clear()
    game.pickups.clear()
    assert not game.path(game.hero.position, SAWMILL.chest)
    assert not game.passable(SAWMILL_SHUTTER)
    positions = [game.sawmill_log]
    for _ in range(100):
        hero, log = game.hero.position, game.sawmill_log
        game._hero_turn()
        if game.sawmill_log != log:
            assert distance(hero, log) == 1 and distance(log, game.sawmill_log) == 1
            assert game.sawmill_log == (2 * log[0] - hero[0], 2 * log[1] - hero[1])
            assert game.hero.position == log
            positions.append(game.sawmill_log)
        if game.sawmill_log == SAWMILL_PLATE:
            break
    assert positions == list(SAWMILL_LOG_POSITIONS)
    assert game.passable(SAWMILL_SHUTTER)
    assert game.path(game.hero.position, SAWMILL.chest)


@pytest.mark.parametrize("position", SAWMILL_LOG_POSITIONS)
def test_each_push_resumes_exactly(mill_saves, position):
    game = decode(copy.deepcopy(mill_saves[position]))
    restored = decode(json.loads(json.dumps(encode(game))))
    for _ in range(300):
        game.update(1 / 30)
        restored.update(1 / 30)
    assert encode(game) == encode(restored)


def test_death_restores_log_and_shutter(mill_saves):
    game = decode(copy.deepcopy(mill_saves[SAWMILL_PLATE]))
    game.hero.hp = 0
    game._contacts()
    for _ in range(180):
        game.update(1 / 60)
        if game.deaths:
            break
    assert game.deaths == 1 and game.capture() == game.checkpoint
    assert game.sawmill_log == SAWMILL_LOG and not game.passable(SAWMILL_SHUTTER)


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(sawmill_log=[True, 11]),
    lambda s: s.update(sawmill_log=[15, 11]),
    lambda s: s.update(chest_open=True),
    lambda s: s["hero"].update(x=26, y=5, previous=[26, 5]),
    lambda s: s["hero"].update(x=12, y=11, previous=[12, 11]),
    lambda s: s.update(pickups=[[21, 11, "heart"]]),
])
def test_invalid_mill_saves_preserved(mill_saves, mutation, tmp_path):
    data = copy.deepcopy(mill_saves[SAWMILL_LOG])
    mutation(data["current"])
    path = tmp_path / "mill.json"
    original = json.dumps(data)
    path.write_text(original)
    store = SaveStore(path)
    game = store.load()
    assert not store.writable and not store.save(game)
    assert path.read_text() == original


def test_departed_mill_retains_solved_state(mill_saves):
    game = decode(copy.deepcopy(mill_saves["after"]))
    cache = game.area_states[SAWMILL_ROOM]
    assert game.sawmill_log == SAWMILL_PLATE
    assert cache["chest_open"] and cache["gate_open"] and not cache["enemies"]


def test_shutter_pixels_change_without_hud_change(mill_saves):
    game = decode(copy.deepcopy(mill_saves[SAWMILL_LOG]))
    game.hero = Actor(20, 11)
    renderer = CampaignRenderer(game.areas)
    closed = renderer.render(game)
    game.sawmill_log = SAWMILL_PLATE
    opened = renderer.render(game)
    assert closed.tobytes() != opened.tobytes()
    assert closed.crop((0, 0, 64, 8)).tobytes() == opened.crop((0, 0, 64, 8)).tobytes()


@pytest.mark.parametrize("kind", ["heart", "rupee"])
@pytest.mark.parametrize("health", [2, 4, MAX_HEARTS])
def test_reachable_pickup_collected_before_log_with_unreachable_enemies(kind, health):
    game = CampaignGame()
    game._load_room(SAWMILL_ROOM)
    game.hero = Actor(6, 6, hp=health)
    game.enemies = [Actor(24, 12, kind="guard", hp=2)]
    game.pickups = {(6, 7): kind}
    game._hero_turn()
    assert game.hero.position == (6, 7)
    assert game.sawmill_log == SAWMILL_LOG
    game._contacts()
    assert not game.pickups
    for _ in range(40):
        game._hero_turn()
        if game.sawmill_log == SAWMILL_PLATE:
            break
    assert game.sawmill_log == SAWMILL_PLATE
    assert game.enemies
