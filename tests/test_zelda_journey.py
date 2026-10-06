"""Actual revisit state, return objectives, checkpoint rollback and save validation."""
import copy
import json

import pytest

from src.display.zelda_quest.campaign import CampaignGame
from src.display.zelda_quest.journey import JOURNEY, RETURN_ERRANDS, SPIRIT_TILES, departed_rooms, first_visit
from src.display.zelda_quest.persistence import decode, encode


RESCUE_VISIT = next(index for index, visit in enumerate(JOURNEY)
                    if any(errand.name == "spring_spirit" for errand in visit.errands))
RESTORE_VISIT = next(index for index, visit in enumerate(JOURNEY)
                     if any(errand.name == "restore_elder_tree" for errand in visit.errands))


@pytest.fixture(scope="module")
def visit_saves():
    game = CampaignGame()
    saves = {0: encode(game)}
    for _ in range(30 * 600):
        game.update(1 / 30)
        if game.visit_index not in saves:
            saves[game.visit_index] = encode(game)
        if game.finished:
            break
    assert game.finished and game.deaths == 0
    saves["finished"] = encode(game)
    return saves


def test_revisits_keep_cleared_enemies_open_chests_and_equipment(visit_saves):
    for index, visit in enumerate(JOURNEY):
        if visit.room not in departed_rooms(index):
            continue
        game = decode(copy.deepcopy(visit_saves[index]))
        assert game.room == JOURNEY[index].room
        assert game.hero.position == JOURNEY[index].arrival
        assert not game.enemies and not game.pickups
        assert game.has_boots
        assert game.gate_open
        assert game.chest_open if game.area.chest else game.sigils_lit == len(game.area.sigils)
    rescue_cache = visit_saves[RESCUE_VISIT]["current"]["area_states"][1]
    assert rescue_cache == visit_saves[RESTORE_VISIT]["current"]["area_states"][1]


def test_return_interactions_finish_at_restored_village_not_boss(visit_saves):
    game = decode(visit_saves["finished"])
    assert game.room == 0 and game.visit_index == len(JOURNEY) - 1
    assert game.return_errands == [errand.name for errand in RETURN_ERRANDS]
    assert game.completed_areas == departed_rooms(len(JOURNEY))
    assert game.wins == 1 and decode(encode(game)).wins == 1
    assert not visit_saves[first_visit(4) + 1]["finished"]


def test_spirit_clearings_need_boots(visit_saves):
    outward = decode(visit_saves[first_visit(1)])
    returned = decode(visit_saves[RESCUE_VISIT])
    for position in SPIRIT_TILES:
        assert not outward.passable(position)
        assert returned.passable(position)
        assert returned.path(returned.hero.position, position)


@pytest.mark.parametrize("visit", range(len(JOURNEY)))
def test_every_visit_roundtrips_and_continues_exactly(visit_saves, visit):
    game = decode(copy.deepcopy(visit_saves[visit]))
    restored = decode(json.loads(json.dumps(encode(game))))
    for _ in range(120):
        game.update(1 / 30)
        restored.update(1 / 30)
    assert encode(restored) == encode(game)


def test_revisit_death_restores_quest_and_cache_without_repopulating(visit_saves):
    game = decode(copy.deepcopy(visit_saves[RESCUE_VISIT]))
    for _ in range(30 * 60):
        game.update(1 / 30)
        if game.return_errands:
            break
    assert game.return_errands == ["spring_spirit"]
    game.hero.hp = 0
    game._contacts()
    for _ in range(180):
        game.update(1 / 60)
        if game.deaths:
            break
    assert game.capture() == game.checkpoint
    assert not game.enemies and not game.return_errands
    assert encode(decode(encode(game))) == encode(game)


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(visit_index=0),
    lambda s: s.update(return_errands=["restore_village"]),
    lambda s: s["area_states"].__setitem__(0, None),
    lambda s: s["area_states"][0].update(enemies=[{"kind": "fake"}]),
    lambda s: s["area_states"][0].update(chest_open=False),
])
def test_bad_journey_and_cached_state_rejected(visit_saves, mutation):
    data = copy.deepcopy(visit_saves[RESCUE_VISIT])
    mutation(data["current"])
    with pytest.raises(ValueError):
        decode(data)


def test_encoded_snapshot_does_not_share_mutable_live_state(visit_saves):
    game = decode(copy.deepcopy(visit_saves[RESCUE_VISIT]))
    snapshot = encode(game)
    original = copy.deepcopy(snapshot)
    game.completed_areas.append(4)
    game.checkpoint["return_errands"].append("spring_spirit")
    assert snapshot == original
    restored = decode(snapshot)
    restored.completed_areas.append(4)
    restored.checkpoint["return_errands"].append("spring_spirit")
    assert snapshot == original


def test_spirit_tiles_derive_from_rescue_objectives_not_visit_index():
    expected = {errand.position for visit in JOURNEY if visit.room == 1
                for errand in visit.errands if errand.kind == "rescue"}
    assert SPIRIT_TILES == expected


def test_first_visit_follows_route_not_area_number(monkeypatch):
    from src.display.zelda_quest import journey
    route = (journey.Visit(0, (1, 1)), journey.Visit(5, (1, 1)),
             journey.Visit(2, (1, 1)), journey.Visit(5, (1, 1)))
    monkeypatch.setattr(journey, "JOURNEY", route)
    assert journey.first_visit(5) == 1
    assert journey.first_visit(2) == 2
    assert journey.departed_rooms(4) == [0, 5, 2]
