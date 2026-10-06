"""Canal traversal, control prerequisites, save safety and real autonomous progress."""
import json

import pytest

from src.display.zelda_quest.campaign import CampaignGame
from src.display.zelda_quest.game import Actor
from src.display.zelda_quest.persistence import SaveStore, decode, encode
from src.display.zelda_quest.preview import CampaignRenderer
from src.display.zelda_quest.sluice import COURT_ROOM, CROSSINGS, WHEELS


@pytest.fixture
def court():
    game = CampaignGame()
    for _ in range(30 * 600):
        game.update(1 / 30)
        if game.room == COURT_ROOM:
            break
    assert game.room == COURT_ROOM
    return game


def test_wheels_change_actual_reachability_and_leave_return_routes(court):
    court.enemies.clear()
    assert court.path(court.hero.position, WHEELS[0])
    assert not court.path(court.hero.position, WHEELS[1])
    assert not court.path(court.hero.position, court.area.chest)
    court.hero = Actor(*WHEELS[0])
    court._contacts()
    assert court.sluice_stage == 1
    assert court.path(court.hero.position, WHEELS[1])
    assert not court.path(court.hero.position, court.area.chest)
    court.phase = "explore"
    court.hero = Actor(*WHEELS[1])
    court._contacts()
    assert court.sluice_stage == 2
    assert court.path(court.hero.position, court.area.chest)
    assert court.path(court.area.chest, court.area.gate_approach)
    assert all(court.passable(cell) for cell in CROSSINGS)
    court.phase = "explore"
    court._contacts()
    assert court.sluice_stage == 2


def test_second_wheel_cannot_skip_first_and_dead_hero_cannot_operate(court):
    court.enemies.clear()
    court.hero = Actor(*WHEELS[1])
    court._contacts()
    assert court.sluice_stage == 0
    court.hero = Actor(*WHEELS[0], hp=0)
    court._contacts()
    assert court.phase == "defeat" and court.sluice_stage == 0


def test_unreachable_enemy_does_not_stall_sluice_objective(court):
    court.enemies = [Actor(20, 12, kind="guard", hp=2)]
    assert not court.path(court.hero.position, court.enemies[0].position)
    for _ in range(100):
        court._hero_turn()
        court._contacts()
        if court.sluice_stage:
            break
    assert court.sluice_stage == 1 and len(court.enemies) == 1


def test_mid_control_roundtrip_and_checkpoint_rollback(court):
    for _ in range(30 * 90):
        court.update(1 / 30)
        if court.sluice_stage == 1:
            break
    assert court.sluice_stage == 1
    restored = decode(json.loads(json.dumps(encode(court))))
    assert encode(restored) == encode(court)
    for _ in range(30 * 10):
        court.update(1 / 30)
        restored.update(1 / 30)
    assert encode(restored) == encode(court)
    restored.hero.hp = 0
    restored._contacts()
    for _ in range(180):
        restored.update(1 / 60)
        if restored.deaths:
            break
    assert restored.deaths == 1
    assert restored.sluice_stage == 0
    assert restored.capture() == restored.checkpoint


@pytest.mark.parametrize("stage", [-1, 3, True, 1.5, None])
def test_invalid_sluice_state_rejected(court, stage):
    data = encode(court)
    data["current"]["sluice_stage"] = stage
    with pytest.raises(ValueError, match="sluice"):
        decode(data)


def test_flooded_crossing_cannot_hold_saved_actor(court):
    court.hero = Actor(10, 3)
    with pytest.raises(ValueError, match="undrained|flooded"):
        decode(encode(court))


def test_canal_rendering_changes_only_world_not_hud(court):
    court.hero = Actor(9, 3)
    renderer = CampaignRenderer(court.areas)
    flooded = renderer.render(court)
    court.sluice_stage = 1
    drained = renderer.render(court)
    assert flooded.size == drained.size == (64, 64)
    assert flooded.crop((0, 0, 64, 8)).tobytes() == drained.crop((0, 0, 64, 8)).tobytes()
    assert flooded.tobytes() != drained.tobytes()


@pytest.mark.parametrize("stage, position", [(0, (20, 2)), (1, (21, 13))])
def test_stranded_side_save_is_preserved_without_loading(court, tmp_path, stage, position):
    court.hero = Actor(*position)
    court.sluice_stage = stage
    path = tmp_path / "stranded.json"
    original = json.dumps(encode(court))
    path.write_text(original)
    store = SaveStore(path)
    recovered = store.load()
    assert recovered.room == 0
    assert not store.writable and not store.save(recovered)
    assert path.read_text() == original


@pytest.mark.parametrize("position", list(CROSSINGS))
def test_flooded_pickups_are_rejected(court, position):
    court.pickups[position] = "heart"
    with pytest.raises(ValueError, match="Pickup inside flooded"):
        decode(encode(court))


def test_owned_boots_require_solved_stone(court):
    from src.display.zelda_quest.puzzle import STONE_START
    court.stone = STONE_START
    with pytest.raises(ValueError, match="Boots obtained before"):
        decode(encode(court))
