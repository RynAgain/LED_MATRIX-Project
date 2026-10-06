"""Autonomous progression, rendering, and carousel lifecycle contracts."""

import importlib
import json
import random
from unittest.mock import create_autospec

import pytest

from src.display import _shared, zelda_quest
from src.display.zelda_quest import QuestGame, Renderer
from src.display.zelda_quest.game import Actor, CHEST, GATE, RELIC, MAX_HEARTS, STEP_TIME
from src.feature_registry import FEATURE_MODULES
from src.simulator.matrix import RGBMatrix


@pytest.fixture(autouse=True)
def clear_stop():
    _shared.clear_stop()
    yield
    _shared.clear_stop()


@pytest.fixture
def game():
    return QuestGame(random.Random(3))


def advance(game, seconds):
    for _ in range(round(seconds * 30)):
        game.update(1 / 30)


@pytest.mark.parametrize("dt", [1 / 60, 1 / 30, 1 / 24, 0.1])
@pytest.mark.parametrize("seed", range(24))
def test_self_play_finishes_and_restarts_without_input(seed, dt):
    game = QuestGame(random.Random(seed))
    phases = set()
    for _ in range(round(60 / dt)):
        game.update(dt)
        phases.add((game.room, game.phase))
        actors = [game.hero] + game.enemies
        assert all(game.passable(actor.position) for actor in actors)
        assert len({a.position for a in actors}) == len(actors)
        assert 0 <= game.hero.hp <= MAX_HEARTS
    assert {(0, "key"), (0, "enter"), (1, "victory")} <= phases
    assert game.wins >= 2
    assert game.runs >= 3


def test_seeded_play_is_reproducible():
    games = [QuestGame(random.Random(42)) for _ in range(2)]
    for game in games:
        advance(game, 40)
    assert games[0].__dict__ | {"rng": None} == games[1].__dict__ | {"rng": None}


def test_chest_reachable_but_gate_blocked_without_key(game):
    route = game.path(game.hero.position, CHEST)
    assert route[-1] == CHEST
    assert (4, 3) in route
    assert all(game.passable(cell) for cell in route)
    assert game.path(game.hero.position, GATE) == []
    assert game.path(game.hero.position, game.hero.position) == []
    for cell in ((-1, 1), (8, 1), (1, -1), (1, 7), (0, 0), (4, 2)):
        assert not game.passable(cell)


def test_blocked_bridge_has_no_alternate_water_route(game):
    assert game.path(game.hero.position, CHEST, blocked={(4, 3)}) == []


def test_chest_key_is_consumed_by_gate(game):
    game.enemies.clear()
    game.hero = Actor(*CHEST)
    game._contacts()
    assert game.chest_open and game.has_key and game.phase == "key"
    advance(game, 1.3)
    game.hero = Actor(6, 4)
    game._hero_turn()
    assert game.gate_open and not game.has_key
    assert game.hero.position == GATE
    game._contacts()
    assert game.phase == "enter"
    advance(game, 0.8)
    assert game.room == 1
    assert any(e.kind == "guardian" for e in game.enemies)


def test_gate_cannot_be_opened_without_key(game):
    game.enemies.clear()
    game.chest_open = True
    game.hero = Actor(6, 4)
    game._hero_turn()
    assert not game.gate_open
    assert game.hero.position == (6, 4)


def test_sword_hits_adjacent_enemy_and_drops_loot(game):
    game.hero = Actor(1, 3)
    enemy = Actor(2, 3, kind="guard", hp=2)
    game.enemies = [enemy]
    game._hero_turn()
    assert enemy.hp == 1 and enemy.flash > 0 and game.swing > 0
    assert game.hero.facing == (1, 0)
    game._hero_turn()
    assert not game.enemies
    assert game.pickups[enemy.position] == "rupee"


def test_contact_damage_has_invulnerability_and_recovery(game):
    game.hero = Actor(1, 3)
    enemy = Actor(2, 3, kind="guard", hp=2)
    game.enemies = [enemy]
    game._contacts()
    assert game.hero.hp == MAX_HEARTS - 1
    enemy.cooldown = 0
    game._contacts()
    assert game.hero.hp == MAX_HEARTS - 1
    game._hero_turn()
    game._hero_turn()
    assert game.pickups[enemy.position] == "heart"
    game.hero.move(enemy.position)
    game._contacts()
    assert game.hero.hp == MAX_HEARTS
    assert not game.pickups


def test_low_health_ai_prioritizes_healing_over_combat(game):
    game.hero = Actor(1, 3, hp=2)
    enemy = Actor(2, 3, kind="guard", hp=2)
    game.enemies = [enemy]
    game.pickups[(1, 4)] = "heart"
    game._hero_turn()
    assert game.hero.position == (1, 4)
    assert enemy.hp == 2
    game._contacts()
    assert game.hero.hp == 3


def test_rupee_pickup_is_collected_once(game):
    game.enemies.clear()
    game.pickups[game.hero.position] = "rupee"
    game._contacts()
    game._contacts()
    assert game.rupees == 1 and not game.pickups


def test_preexisting_stop_never_renders():
    matrix = create_autospec(RGBMatrix, instance=True)
    _shared.request_stop()
    zelda_quest.run(matrix)
    matrix.SetImage.assert_not_called()
    matrix.Clear.assert_called_once()


def test_defeat_restarts_automatically(game):
    game.hero.hp = 0
    game._contacts()
    assert game.phase == "defeat"
    advance(game, 2.1)
    assert game.phase == "explore" and game.room == 0
    assert game.runs == 2 and game.hero.hp == MAX_HEARTS


def test_relic_requires_guardian_defeat(game):
    game._load_room(1)
    game.hero = Actor(*RELIC)
    game._contacts()
    assert game.phase == "explore" and game.wins == 0
    game.enemies.clear()
    game._contacts()
    assert game.phase == "victory" and game.wins == 1
    advance(game, 2.6)
    assert game.room == 0 and game.runs == 2


def test_motion_interpolates_between_tiles():
    actor = Actor(1, 1)
    start = actor.screen_position
    actor.move((2, 1))
    assert actor.screen_position == start
    actor.update(STEP_TIME / 2)
    assert actor.screen_position == (start[0] + 4, start[1])
    actor.update(STEP_TIME)
    assert actor.screen_position == (start[0] + 8, start[1])


def test_nonpositive_dt_is_noop_and_long_frames_are_bounded(game):
    game.update(-1)
    game.update(0)
    assert game.elapsed == 0
    game.update(500)
    assert game.elapsed == 0.1


def test_render_entire_run_without_mutating_backgrounds(game):
    renderer = Renderer()
    originals = [image.tobytes() for image in renderer.backgrounds]
    frames = set()
    for _ in range(750):
        game.update(1 / 30)
        image = renderer.render(game)
        assert image.mode == "RGB" and image.size == (64, 64)
        frames.add(image.tobytes())
    assert len(frames) > 150
    assert originals == [image.tobytes() for image in renderer.backgrounds]
    game.hero.hp = 0
    game._contacts()
    assert renderer.render(game).size == (64, 64)


@pytest.mark.parametrize("duration", [0, -1, 0.1])
def test_runner_honors_duration_and_clears(monkeypatch, duration):
    matrix = create_autospec(RGBMatrix, instance=True)
    clock = [0.0]
    monkeypatch.setattr(zelda_quest.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(zelda_quest, "interruptible_sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    zelda_quest.run(matrix, duration)
    assert clock[0] <= max(0, duration)
    assert matrix.SetImage.call_count == (3 if duration > 0 else 0)
    matrix.Clear.assert_called_once()


def test_runner_stops_immediately_when_carousel_requests_it(monkeypatch):
    matrix = create_autospec(RGBMatrix, instance=True)
    matrix.SetImage.side_effect = lambda image: _shared.request_stop()
    zelda_quest.run(matrix, 60)
    matrix.SetImage.assert_called_once()
    matrix.Clear.assert_called_once()


def test_runner_clears_after_display_failure():
    matrix = create_autospec(RGBMatrix, instance=True)
    matrix.SetImage.side_effect = RuntimeError("display failure")
    with pytest.raises(RuntimeError, match="display failure"):
        zelda_quest.run(matrix)
    matrix.Clear.assert_called_once()


def test_real_simulator_run(matrix):
    zelda_quest.run(matrix, duration=0.04)


def test_demo_and_carousel_registration(tmp_path):
    from src.main import _sync_sequence_with_registry
    from src.menu.menu_data import build_demos_menu

    assert importlib.import_module(FEATURE_MODULES["zelda_quest"]).run is zelda_quest.run
    menu = build_demos_menu()
    assert any(item.payload == "zelda_quest" and item.label == "ZELDA QUEST" for item in menu.items)
    config = {"sequence": []}
    path = tmp_path / "config.json"
    _sync_sequence_with_registry(config, str(path))
    entries = json.loads(path.read_text())["sequence"]
    assert {"name": "zelda_quest", "type": "effect", "enabled": True} in entries
