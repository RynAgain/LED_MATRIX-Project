"""Campaign foundation contracts: route, viewport, save/resume and preview lifecycle."""

import copy
import json
from unittest.mock import create_autospec

import pytest
from PIL import Image

from src.display import _shared
from src.display.zelda_quest.campaign import CampaignGame
from src.display.zelda_quest.game import Actor
from src.display.zelda_quest.persistence import SaveStore, decode, encode, MAX_SAVE_BYTES
from src.display.zelda_quest.preview import CampaignRenderer, run
from src.display.zelda_quest.render import Renderer, camera_origin
from src.display.zelda_quest.world import Area, FOREST_REGION
from src.display.zelda_quest.journey import JOURNEY, departed_rooms
from src.simulator.matrix import RGBMatrix


@pytest.fixture(autouse=True)
def clear_stop():
    _shared.clear_stop()
    yield
    _shared.clear_stop()


def simulate(game, seconds=600, dt=1 / 30):
    phases = set()
    for _ in range(round(seconds / dt)):
        if game.finished:
            break
        game.update(dt)
        phases.add((game.room, game.phase))
    return phases


def test_route_is_autonomously_completed_and_does_not_loop():
    game = CampaignGame()
    phases = simulate(game)
    assert game.finished
    assert game.completed_areas == departed_rooms(len(JOURNEY))
    assert {(0, "key"), (1, "rune"), (2, "boots"), (4, "roar"), (4, "victory")} <= phases
    assert 174 < game.active_seconds < 600
    before = encode(game)
    simulate(game, 10)
    assert encode(game) == before


@pytest.mark.parametrize("dt", [1 / 60, 1 / 30, 1 / 24, 0.1])
def test_forest_slice_all_frame_rates(dt):
    game = CampaignGame()
    simulate(game, 600, dt)
    assert game.finished and game.completed_areas == departed_rooms(len(JOURNEY))


def test_vine_court_requires_boots_to_reach_key():
    game = CampaignGame()
    game._load_room(3)
    assert game.path(game.hero.position, game.area.chest) == []
    assert not game.passable((5, 5))
    game.has_boots = True
    assert game.path(game.hero.position, (8, 3))
    assert game.path(game.hero.position, game.area.chest) == []
    game.sluice_stage = 2
    route = game.path(game.hero.position, game.area.chest)
    assert route[-1] == game.area.chest and (10, 12) in route
    assert game.path(game.hero.position, game.area.gate) == []


def test_viewport_scrolls_and_clamps_in_both_directions():
    game = CampaignGame()
    renderer = Renderer(game.areas)
    assert camera_origin(game) == (0, 56)
    initial = renderer.render(game)
    assert initial.size == (64, 64)
    game.hero = Actor(18, 2)
    assert camera_origin(game) == (96, 0)
    distant = renderer.render(game)
    assert distant.getpixel((4, 4)) == initial.getpixel((4, 4))
    assert initial.tobytes() != distant.tobytes()
    game.hero = Actor(18, 12)
    assert camera_origin(game) == (96, 56)
    assert renderer.render(game).size == (64, 64)


def test_checkpoint_recovery_preserves_campaign_clock():
    game = CampaignGame()
    for _ in range(2000):
        game.update(1 / 30)
        if game.room == 1:
            break
    assert game.room == 1
    checkpoint = copy.deepcopy(game.checkpoint)
    game.hero.hp = 0
    game._contacts()
    assert game.phase == "defeat"
    before = game.active_seconds
    for _ in range(180):
        game.update(1 / 60)
        if game.deaths:
            break
    assert game.deaths == 1 and game.room == 1
    assert game.capture() == checkpoint
    assert game.active_seconds == before
    game.update(1 / 30)
    assert game.active_seconds > before
    assert game.completed_areas == [0]


def test_roundtrip_exact_state_and_independent_rng():
    game = CampaignGame()
    for _ in range(88):
        game.update(1 / 30)
    restored = decode(json.loads(json.dumps(encode(game))))
    assert encode(restored) == encode(game)
    assert restored is not game and restored.hero is not game.hero
    simulate(game)
    simulate(restored)
    assert encode(restored) == encode(game)


def test_save_resumes_between_sessions_and_across_area_transition(tmp_path):
    store = SaveStore(tmp_path / "campaign.json")
    game = store.load()
    for _ in range(1800):
        game.update(1 / 30)
        if game.room == 1:
            break
    assert game.room == 1
    assert store.save(game)
    next_session = SaveStore(store.path).load()
    assert encode(next_session) == encode(game)
    assert simulate(next_session)
    assert next_session.finished and next_session.active_seconds > game.active_seconds
    assert SaveStore(store.path).save(next_session)
    assert SaveStore(store.path).load().finished


@pytest.mark.parametrize("corruption", [b"{bad json", b"[]", "oversized"], ids=["json", "array", "oversized"])
def test_corrupt_or_oversized_save_is_preserved(tmp_path, corruption):
    path = tmp_path / "campaign.json"
    if corruption == "oversized":
        corruption = b"X" * (MAX_SAVE_BYTES + 1)
    path.write_bytes(corruption)
    store = SaveStore(path)
    assert store.load().room == 0
    assert not store.save(CampaignGame())
    assert path.read_bytes() == corruption


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(version=999),
    lambda d: d.update(content="old content"),
    lambda d: d.update(active_seconds="unknown"),
    lambda d: d["current"]["hero"].update(x=999),
    lambda d: d["current"]["hero"].update(kind="guardian"),
    lambda d: d["current"]["hero"].update(hp=float("nan")),
    lambda d: d["checkpoint"].update(room=2),
    lambda d: d.update(completed_areas=[2]),
    lambda d: d["current"].update(enemies=[d["current"]["hero"]]),
])
def test_invalid_saves_are_rejected(mutation, tmp_path):
    data = encode(CampaignGame())
    mutation(data)
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(data))
    store = SaveStore(path)
    game = store.load()
    assert game.room == 0 and not store.writable
    assert not store.save(game)
    assert path.read_text() == json.dumps(data)


def test_dead_checkpoint_is_preserved_and_never_loaded(tmp_path):
    data = encode(CampaignGame())
    data["checkpoint"]["hero"]["hp"] = 0
    path = tmp_path / "dead-checkpoint.json"
    original = json.dumps(data).encode()
    path.write_bytes(original)
    store = SaveStore(path)
    game = store.load()
    assert game.checkpoint["hero"]["hp"] > 0
    assert not store.writable and not store.save(game)
    assert path.read_bytes() == original


def test_atomic_save_failure_preserves_previous_save(monkeypatch, tmp_path):
    from src.display.zelda_quest import persistence

    store = SaveStore(tmp_path / "campaign.json")
    game = store.load()
    assert store.save(game)
    previous = store.path.read_bytes()
    game.update(0.1)

    def fail_replace(*args):
        raise OSError("replace failed")
    monkeypatch.setattr(persistence.os, "replace", fail_replace)
    assert not store.save(game)
    assert store.path.read_bytes() == previous
    assert not list(tmp_path.glob("*.tmp"))


def test_runner_resumes_and_clears_on_stop(monkeypatch, tmp_path):
    matrix = create_autospec(RGBMatrix, instance=True)
    matrix.SetImage.side_effect = lambda image: _shared.request_stop()
    path = tmp_path / "campaign.json"
    run(matrix, duration=60, save_path=path)
    matrix.SetImage.assert_called_once()
    assert isinstance(matrix.SetImage.call_args.args[0], Image.Image)
    matrix.Clear.assert_called_once()
    saved = SaveStore(path).load()
    assert saved.active_seconds + saved.pending_seconds > 0
    assert CampaignRenderer(saved.areas).render(saved).size == (64, 64)


def test_runner_saves_after_display_error(tmp_path):
    matrix = create_autospec(RGBMatrix, instance=True)
    matrix.SetImage.side_effect = RuntimeError("display failure")
    path = tmp_path / "campaign.json"
    with pytest.raises(RuntimeError, match="display failure"):
        run(matrix, save_path=path)
    matrix.Clear.assert_called_once()
    assert SaveStore(path).load().room == 0


def test_preview_is_not_published():
    from src.feature_registry import FEATURE_MODULES
    assert "src.display.zelda_quest.preview" not in FEATURE_MODULES.values()
    assert "zelda_quest" in FEATURE_MODULES


def test_area_schema_rejects_unbeatable_metadata():
    with pytest.raises(ValueError):
        Area("invalid", ("###", "#.?"), (1, 1), relic=(1, 1))
    assert len(FOREST_REGION) == 5


@pytest.mark.parametrize("dt", [1 / 24, 1 / 30, 0.1])
def test_fixed_simulation_is_identical_after_equal_playtime(dt):
    reference = CampaignGame()
    current = CampaignGame()
    for _ in range(60 * 10):
        reference.update(1 / 60)
    for _ in range(round(10 / dt)):
        current.update(dt)
    assert current.capture() == reference.capture()
    assert current.active_seconds == reference.active_seconds
    assert current.pending_seconds == pytest.approx(reference.pending_seconds, abs=1e-12)


def test_occupied_boss_spawn_uses_nearest_free_land():
    game = CampaignGame()
    game.has_boots = True
    game._load_room(4)
    game.enemies = [game.boss]
    game.hero = Actor(*game.area.sapling)
    game._reinforce()
    assert game.boss_reinforced
    assert game.boss_armored
    positions = [actor.position for actor in [game.hero] + game.enemies]
    assert len(positions) == len(set(positions))
    assert all(game.passable(position) for position in positions)


def test_sigil_order_resets_then_opens_gate_and_roundtrips():
    game = CampaignGame()
    for _ in range(30 * 90):
        game.update(1 / 30)
        if game.room == 1:
            break
    assert game.room == 1
    game._touch_sigil(2)
    assert game.sigils_lit == 0 and game.phase == "lost"
    assert game.hero.position == game.area.start
    for index in range(3):
        game._touch_sigil(index)
        restored = decode(json.loads(json.dumps(encode(game))))
        assert restored.sigils_lit == index + 1
        assert encode(restored) == encode(game)
    assert game.gate_open


def test_boss_armor_requires_sapling_defeat():
    game = CampaignGame()
    game.has_boots = True
    game._load_room(4)
    boss = game.boss
    health = boss.hp
    game._strike(boss)
    assert boss.hp == health
    game.enemies = [boss]
    game._strike(boss)
    assert boss.hp == health - 1
