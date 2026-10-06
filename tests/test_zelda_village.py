"""Authored village prerequisite, inventory and autonomous integration contracts."""
import json

import pytest

from src.display.zelda_quest.campaign import CampaignGame
from src.display.zelda_quest.journal import VILLAGE_ERRANDS, VillageJournal
from src.display.zelda_quest.persistence import decode, encode
from src.display.zelda_quest.world import FOREST_REGION


def test_every_authored_errand_is_reachable():
    reachable = FOREST_REGION[0].reachable()
    assert all(errand.position in reachable for errand in VILLAGE_ERRANDS)


def test_supplies_require_request_and_are_consumed_on_delivery():
    journal = VillageJournal()
    with pytest.raises(ValueError):
        journal.complete("ranger_map", (10, 4))
    journal.complete("elder_request", (5, 4))
    for name in ("mill_tools", "orchard_food", "watchpost_medicine"):
        errand = next(item for item in journal.available if item.name == name)
        journal.complete(name, errand.position)
    assert journal.inventory == {"food", "tools", "medicine"}
    journal.complete("restore_supplies", (5, 4))
    assert not journal.inventory
    journal.complete("ranger_map", (10, 4))
    assert journal.finished and journal.inventory == {"woodland_map"}


@pytest.mark.parametrize("completed", [
    ["ranger_map"], ["elder_request", "elder_request"], ["unknown"],
    ["elder_request", "restore_supplies"],
])
def test_invalid_journal_is_rejected(completed):
    with pytest.raises(ValueError):
        VillageJournal(completed)


def test_interaction_requires_actual_location():
    journal = VillageJournal()
    with pytest.raises(ValueError):
        journal.complete("elder_request", (1, 1))
    assert not journal.completed


def test_self_play_delivers_supplies_before_leaving_village():
    game = CampaignGame()
    interactions = set()
    for frame in range(30 * 90):
        game.update(1 / 30)
        if game.phase == "interact":
            interactions.add(game.interaction_label)
        if frame % 71 == 0:
            game = decode(json.loads(json.dumps(encode(game))))
        if game.room:
            break
    assert game.room == 1
    assert game.journal.finished
    assert game.journal.inventory == {"woodland_map"}
    assert interactions == {errand.label for errand in VILLAGE_ERRANDS}


def test_failed_attempt_does_not_inflate_content_clock():
    game = CampaignGame()
    for _ in range(120):
        game.update(1 / 60)
    assert game.content_seconds > 0
    active_before = game.active_seconds
    checkpoint_content = game.checkpoint["content_seconds"]
    game.hero.hp = 0
    game._contacts()
    for _ in range(180):
        game.update(1 / 60)
        if game.deaths:
            break
    assert game.deaths == 1
    assert game.content_seconds == checkpoint_content
    assert game.active_seconds == active_before
    assert encode(decode(encode(game))) == encode(game)
