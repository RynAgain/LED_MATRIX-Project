"""Actual light routing gates Watchwood travel and survives save/checkpoint recovery."""
import copy
import json

import pytest

from src.display.zelda_quest import watchwood
from src.display.zelda_quest.campaign import CampaignGame
from src.display.zelda_quest.game import Actor
from src.display.zelda_quest.persistence import SaveStore, decode, encode
from src.display.zelda_quest.preview import CampaignRenderer
from src.display.zelda_quest.watchwood import (
    WATCHWOOD, WATCHWOOD_ROOM, CONTROLS, SENSORS, SHUTTERS, beam_path, watchwood_passable,
)


@pytest.fixture(scope="module")
def watch_saves():
    game = CampaignGame()
    saves = {}
    for _ in range(30 * 600):
        game.update(1 / 30)
        if game.room == WATCHWOOD_ROOM:
            saves.setdefault(game.watchwood_stage, encode(game))
        if game.room == 2:
            saves["after"] = encode(game)
            break
    assert set(saves) == {0, 1, 2, "after"}
    assert game.deaths == 0
    return saves


@pytest.mark.parametrize("stage,lit", [(0, (False, False)), (1, (True, False)), (2, (True, True))])
def test_actual_sensor_hits_gate_routes(stage, lit):
    game = CampaignGame()
    game._load_room(WATCHWOOD_ROOM)
    game.watchwood_stage = stage
    path = beam_path(stage)
    assert tuple(sensor in path for sensor in SENSORS) == lit
    assert tuple(game.passable(cell) for cell in SHUTTERS) == lit
    assert bool(game.path(WATCHWOOD.start, CONTROLS[1])) == lit[0]
    assert bool(game.path(WATCHWOOD.start, WATCHWOOD.chest)) == lit[1]
    assert bool(game.path(WATCHWOOD.start, WATCHWOOD.gate_approach)) == lit[1]
    assert game.path(WATCHWOOD.start, CONTROLS[0])
    assert not game.passable((12, 10))
    assert ((12, 10) in path) == lit[0]
    for first, second in zip(path, path[1:]):
        assert sum(abs(a - b) for a, b in zip(first, second)) == 1
    assert len(path) == len(set(path))


def test_shutter_requires_actual_light_not_only_stage(monkeypatch):
    monkeypatch.setattr(watchwood, "beam_path", lambda stage: ())
    assert not any(watchwood_passable(cell, 2) for cell in SHUTTERS)


@pytest.mark.parametrize("cell", [(-1, 0), (32, 2), (2, -1), (2, 22), (0, 0), (3, 6)])
def test_wall_obstacle_and_map_bounds_block_walking(cell):
    assert not watchwood_passable(cell, 2)


def test_controls_require_correct_order_position_and_living_hero(watch_saves):
    game = decode(copy.deepcopy(watch_saves[0]))
    game.enemies.clear()
    game.hero = Actor(*CONTROLS[1])
    game._contacts()
    assert game.watchwood_stage == 0
    game.hero = Actor(CONTROLS[0][0] + 1, CONTROLS[0][1])
    game._contacts()
    assert game.watchwood_stage == 0
    game.hero = Actor(*CONTROLS[0], hp=0)
    game._contacts()
    assert game.phase == "defeat" and game.watchwood_stage == 0
    for stage, cell in enumerate(CONTROLS):
        game.hero = Actor(*cell)
        game.phase = "explore"
        game._contacts()
        assert game.watchwood_stage == stage + 1 and game.phase == "interact"
        game._contacts()
        assert game.watchwood_stage == stage + 1


@pytest.mark.parametrize("stage", range(3))
def test_stage_roundtrip_resumes_exactly(watch_saves, stage):
    game = decode(copy.deepcopy(watch_saves[stage]))
    restored = decode(json.loads(json.dumps(encode(game))))
    for _ in range(300):
        game.update(1 / 30)
        restored.update(1 / 30)
    assert encode(game) == encode(restored)


def test_death_rewinds_light_and_shutters(watch_saves):
    game = decode(copy.deepcopy(watch_saves[2]))
    game.hero.hp = 0
    game._contacts()
    for _ in range(180):
        game.update(1 / 60)
        if game.deaths:
            break
    assert game.deaths == 1 and game.capture() == game.checkpoint
    assert game.watchwood_stage == 0 and not any(game.passable(cell) for cell in SHUTTERS)


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(watchwood_stage=-1),
    lambda s: s.update(watchwood_stage=3),
    lambda s: s.update(watchwood_stage=True),
    lambda s: s.update(chest_open=True),
    lambda s: s["hero"].update(x=18, y=11, previous=[18, 11]),
    lambda s: s["hero"].update(x=28, y=4, previous=[28, 4]),
    lambda s: s["hero"].update(x=12, y=15, previous=[12, 15]),
    lambda s: s["enemies"][0].update(x=22, y=6, previous=[22, 6]),
    lambda s: s.update(pickups=[[12, 15, "heart"]]),
])
def test_invalid_save_preserved(watch_saves, mutation, tmp_path):
    data = copy.deepcopy(watch_saves[0])
    mutation(data["current"])
    path = tmp_path / "watchwood.json"
    original = json.dumps(data)
    path.write_text(original)
    store = SaveStore(path)
    game = store.load()
    assert not store.writable and not store.save(game)
    assert path.read_text() == original


def test_progression_before_and_after_visit(watch_saves):
    data = encode(CampaignGame())
    data["current"]["watchwood_stage"] = 1
    with pytest.raises(ValueError, match="Watchwood progression"):
        decode(data)
    game = decode(copy.deepcopy(watch_saves["after"]))
    cache = game.area_states[WATCHWOOD_ROOM]
    assert game.watchwood_stage == 2 and cache["chest_open"] and cache["gate_open"]
    assert not cache["enemies"]
    data = encode(game)
    data["current"]["watchwood_stage"] = 1
    with pytest.raises(ValueError, match="Watchwood progression"):
        decode(data)


@pytest.mark.parametrize("stage", [0, 1])
def test_light_and_control_pixels_change_without_hud(watch_saves, stage):
    game = decode(copy.deepcopy(watch_saves[stage]))
    game.hero = Actor(*CONTROLS[stage])
    renderer = CampaignRenderer(game.areas)
    before = renderer.render(game)
    game.watchwood_stage += 1
    after = renderer.render(game)
    assert before.tobytes() != after.tobytes()
    assert before.crop((0, 0, 64, 8)).tobytes() == after.crop((0, 0, 64, 8)).tobytes()
