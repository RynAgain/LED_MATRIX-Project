"""Brook repair changes actual connectivity and survives interruption and death."""
import copy
import json

import pytest

from src.display.zelda_quest.campaign import CampaignGame
from src.display.zelda_quest.game import Actor
from src.display.zelda_quest.persistence import SaveStore, decode, encode
from src.display.zelda_quest.preview import CampaignRenderer
from src.display.zelda_quest.woodland import BROOK, BROOK_ROOM, BROOK_ERRANDS


@pytest.fixture(scope="module")
def brook_saves():
    game = CampaignGame()
    saves = {}
    for _ in range(30 * 600):
        game.update(1 / 30)
        if game.room == BROOK_ROOM:
            saves.setdefault(game.brook_stage, encode(game))
        if game.room == 2:
            saves["after"] = encode(game)
            break
    assert set(saves) == {0, 1, 2, 3, 4, "after"}
    assert game.deaths == 0
    return saves


@pytest.fixture
def brook(brook_saves):
    return decode(copy.deepcopy(brook_saves[0]))


def test_repair_then_winch_opens_separate_routes_without_bypass(brook):
    brook.enemies.clear()
    for stage, errand in enumerate(BROOK_ERRANDS):
        assert brook.brook_stage == stage
        assert not brook.path(BROOK.start, BROOK.chest)
        assert bool(brook.path(BROOK.start, BROOK_ERRANDS[-1].position)) == (stage == 3)
        assert brook.path(brook.hero.position, errand.position)
        brook.hero = Actor(*errand.position)
        brook.phase = "explore"
        brook._contacts()
        assert brook.brook_stage == stage + 1
    assert brook.path(BROOK.start, BROOK.chest)
    assert brook.path(BROOK.chest, BROOK.start)


def test_planks_and_winch_cannot_skip_request_and_delivery(brook):
    brook.enemies.clear()
    for index in (1, 3):
        brook.hero = Actor(*BROOK_ERRANDS[index].position)
        brook._contacts()
        assert brook.brook_stage == 0
    brook.hero = Actor(*BROOK_ERRANDS[0].position, hp=0)
    brook._contacts()
    assert brook.phase == "defeat" and brook.brook_stage == 0


@pytest.mark.parametrize("stage", range(5))
def test_each_brook_stage_resumes_exactly(brook_saves, stage):
    game = decode(copy.deepcopy(brook_saves[stage]))
    restored = decode(json.loads(json.dumps(encode(game))))
    for _ in range(300):
        game.update(1 / 30)
        restored.update(1 / 30)
    assert encode(restored) == encode(game)


def test_repair_death_restores_bank_and_objectives(brook_saves):
    game = decode(copy.deepcopy(brook_saves[3]))
    active = game.active_seconds
    game.hero.hp = 0
    game._contacts()
    for _ in range(180):
        game.update(1 / 60)
        if game.deaths:
            break
    assert game.deaths == 1 and game.capture() == game.checkpoint
    assert game.brook_stage == 0 and game.hero.position == BROOK.start
    assert game.content_seconds < active == game.active_seconds
    assert encode(decode(encode(game))) == encode(game)


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(brook_stage=-1),
    lambda s: s.update(brook_stage=5),
    lambda s: s.update(brook_stage=True),
    lambda s: s["hero"].update(x=25, y=3, previous=[25, 3]),
    lambda s: s["hero"].update(x=16, y=10, previous=[16, 10]),
    lambda s: s.update(pickups=[[20, 10, "heart"]]),
    lambda s: s.update(chest_open=True),
])
def test_invalid_bridge_progress_or_stranded_save_is_preserved(brook, mutation, tmp_path):
    data = encode(brook)
    mutation(data["current"])
    path = tmp_path / "brook.json"
    original = json.dumps(data)
    path.write_text(original)
    store = SaveStore(path)
    assert store.load().room == 0
    assert not store.writable and not store.save(brook)
    assert path.read_text() == original


def test_departed_brook_keeps_repair_and_cleared_treasury(brook_saves):
    game = decode(brook_saves["after"])
    assert game.brook_stage == 4
    cache = game.area_states[BROOK_ROOM]
    assert cache["chest_open"] and cache["gate_open"]
    assert not cache["enemies"] and not cache["pickups"]
    data = encode(game)
    data["current"]["brook_stage"] = 3
    with pytest.raises(ValueError, match="Brook progression"):
        decode(data)


def test_bridge_art_changes_with_passability_but_not_hud(brook):
    brook.hero = Actor(20, 12)
    renderer = CampaignRenderer(brook.areas)
    lowered = renderer.render(brook)
    brook.brook_stage = 4
    raised = renderer.render(brook)
    assert lowered.size == raised.size == (64, 64)
    assert lowered.crop((0, 0, 64, 8)).tobytes() == raised.crop((0, 0, 64, 8)).tobytes()
    assert lowered.tobytes() != raised.tobytes()
