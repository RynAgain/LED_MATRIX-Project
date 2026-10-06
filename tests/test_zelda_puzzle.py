"""Real push actions, pressure-plate traversal and checkpoint persistence."""
import json

from src.display.zelda_quest.campaign import CampaignGame
from src.display.zelda_quest.game import distance
from src.display.zelda_quest.persistence import decode, encode
from src.display.zelda_quest.puzzle import STONE_START, STONE_PLATE, next_stone_action


def test_stone_blocks_walking_and_plate_opens_boots_pedestal():
    game = CampaignGame()
    game._load_room(2)
    game.enemies.clear()
    assert not game.passable(STONE_START)
    assert not game.passable(game.area.boots)
    pushes = 0
    for _ in range(200):
        previous_stone = game.stone
        previous_hero = game.hero.position
        game._hero_turn()
        if game.stone != previous_stone:
            pushes += 1
            assert distance(previous_stone, game.stone) == 1
            assert distance(previous_hero, previous_stone) == 1
            assert game.hero.position == previous_stone
        if game.stone == STONE_PLATE:
            break
    assert pushes == 3
    assert game.passable(game.area.boots)
    assert not game.passable(STONE_PLATE)


def test_unsolvable_stone_does_not_teleport():
    floor = {(1, 1), (2, 1), (3, 1)}
    assert next_stone_action((1, 1), (3, 1), (2, 1), floor.__contains__) is None


def test_mid_push_save_and_death_restore_exact_stone():
    game = CampaignGame()
    for _ in range(30 * 600):
        game.update(1 / 30)
        if game.room == 2 and game.stone != STONE_START:
            break
    assert game.room == 2 and game.stone != STONE_START
    restored = decode(json.loads(json.dumps(encode(game))))
    assert restored.stone == game.stone
    assert encode(restored) == encode(game)
    restored.hero.hp = 0
    restored._contacts()
    for _ in range(180):
        restored.update(1 / 60)
        if restored.deaths:
            break
    assert restored.stone == STONE_START
    assert restored.content_seconds == restored.checkpoint["content_seconds"]
