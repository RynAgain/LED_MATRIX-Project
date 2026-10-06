"""Guardian positioning, deterministic pulse timing and persisted encounter state."""
import copy
import json

import pytest

from src.display.zelda_quest.campaign import CampaignGame
from src.display.zelda_quest.game import Actor, MAX_HEARTS
from src.display.zelda_quest.persistence import SaveStore, decode, encode
from src.display.zelda_quest.preview import CampaignRenderer
from src.display.zelda_quest.render import PALETTE, Renderer, _center
from src.display.zelda_quest.pulse import EXPOSED_TICKS, SAFE_RUNES, WARNING_TICKS, RootPulse


@pytest.fixture(scope="module")
def pulse_saves():
    game = CampaignGame()
    saves = {}
    for _ in range(60 * 600):
        game.update(1 / 60)
        key = (game.root_pulse.mode, game.root_pulse.cycle)
        if game.room == 2 and game.phase == "explore":
            saves.setdefault(key, encode(game))
        if game.room == 2 and game.visit.exit:
            saves["return"] = encode(game)
            break
    assert game.room == 2 and game.visit.exit and game.deaths == 0
    return saves


@pytest.fixture
def guardian(pulse_saves):
    return decode(copy.deepcopy(pulse_saves[("warning", 0)]))


def test_warning_needs_correct_rune_and_strike_alternates_it():
    pulse = RootPulse()
    assert pulse.tick(SAFE_RUNES[0]) is None
    pulse.warn()
    for _ in range(WARNING_TICKS - 1):
        assert pulse.tick(pulse.safe_tile) is None
    assert pulse.tick(pulse.safe_tile) == "exposed"
    assert pulse.ticks == EXPOSED_TICKS
    pulse.struck(False)
    assert pulse.safe_tile == SAFE_RUNES[1]
    assert pulse.mode == "warning" and pulse.ticks == WARNING_TICKS
    with pytest.raises(ValueError, match="shielded"):
        pulse.struck(False)


def test_wrong_rune_causes_one_damage_event_per_warning():
    pulse = RootPulse("warning", WARNING_TICKS, 0)
    events = [pulse.tick(SAFE_RUNES[1]) for _ in range(WARNING_TICKS * 2)]
    assert [index for index, event in enumerate(events) if event == "damage"] == [89, 179]
    assert pulse.mode == "warning" and pulse.cycle == 0


def test_missed_exposure_restarts_warning_without_advancing_cycle():
    pulse = RootPulse("exposed", EXPOSED_TICKS, 1)
    for _ in range(EXPOSED_TICKS):
        assert pulse.tick(pulse.safe_tile) is None
    assert pulse.mode == "warning" and pulse.ticks == WARNING_TICKS
    assert pulse.cycle == 1


@pytest.mark.parametrize("safe", [False, True])
def test_live_pulse_damage_depends_on_position_not_contact(guardian, safe):
    guardian.hero = Actor(*(guardian.root_pulse.safe_tile if safe else (8, 2)), hp=MAX_HEARTS)
    guardian.hero_clock = 0.30
    guardian.root_pulse.ticks = 1
    guardian.update(1 / 60)
    assert guardian.hero.hp == (MAX_HEARTS if safe else MAX_HEARTS - 1)
    assert guardian.root_pulse.mode == ("exposed" if safe else "warning")
    guardian.update(1 / 60)
    assert guardian.hero.hp == (MAX_HEARTS if safe else MAX_HEARTS - 1)


def test_shield_requires_safety_before_each_of_four_hits(guardian):
    enemy = guardian.root_guardian
    guardian.hero = Actor(8, 2)
    guardian._strike(enemy)
    assert enemy.hp == 4 and guardian.root_pulse.cycle == 0
    for cycle in range(4):
        guardian.root_pulse.ticks = 1
        assert guardian.root_pulse.tick(SAFE_RUNES[cycle % 2]) == "exposed"
        guardian._strike(enemy)
        assert enemy.hp == 3 - cycle
        assert guardian.root_pulse.cycle == cycle + 1
    assert guardian.root_guardian is None
    assert guardian.root_pulse.mode == "cleared"
    assert guardian.root_pulse.ticks == 0


@pytest.mark.parametrize("mode", ["warning", "exposed"])
@pytest.mark.parametrize("cycle", range(4))
def test_every_autonomous_pulse_stage_roundtrips_and_continues(pulse_saves, mode, cycle):
    game = decode(copy.deepcopy(pulse_saves[(mode, cycle)]))
    restored = decode(json.loads(json.dumps(encode(game))))
    for _ in range(180):
        game.update(1 / 60)
        restored.update(1 / 60)
    assert encode(restored) == encode(game)


def test_guardian_stays_cleared_on_return(pulse_saves):
    game = decode(pulse_saves["return"])
    assert game.room == 2 and game.root_pulse.mode == "cleared"
    for _ in range(120):
        game.update(1 / 60)
        assert game.root_guardian is None


def test_death_rewinds_pulse_boots_and_content_not_viewing_time(guardian):
    active = guardian.active_seconds
    guardian.hero.hp = 0
    guardian._contacts()
    for _ in range(180):
        guardian.update(1 / 60)
        if guardian.deaths:
            break
    assert guardian.deaths == 1 and guardian.capture() == guardian.checkpoint
    assert guardian.root_pulse.mode == "dormant" and not guardian.has_boots
    assert guardian.content_seconds < active == guardian.active_seconds
    assert encode(decode(encode(guardian))) == encode(guardian)


@pytest.mark.parametrize("mutation", [
    lambda s: s["root_pulse"].update(mode="unknown"),
    lambda s: s["root_pulse"].update(ticks=0),
    lambda s: s["root_pulse"].update(ticks=WARNING_TICKS + 1),
    lambda s: s["root_pulse"].update(cycle=True),
    lambda s: s["root_pulse"].update(cycle=4),
    lambda s: s.update(enemies=[]),
    lambda s: s["enemies"][0].update(hp=3),
    lambda s: s.update(has_boots=False),
])
def test_bad_pulse_save_is_preserved(guardian, tmp_path, mutation):
    data = encode(guardian)
    mutation(data["current"])
    path = tmp_path / "invalid-pulse.json"
    original = json.dumps(data)
    path.write_text(original)
    store = SaveStore(path)
    recovered = store.load()
    assert recovered.room == 0
    assert not store.writable and not store.save(recovered)
    assert path.read_text() == original


def test_pulse_art_changes_below_fixed_hud(guardian):
    guardian.hero = Actor(*SAFE_RUNES[0])
    renderer = CampaignRenderer(guardian.areas)
    warning = renderer.render(guardian)
    guardian.root_pulse = RootPulse("exposed", EXPOSED_TICKS, 0)
    exposed = renderer.render(guardian)
    assert warning.size == exposed.size == (64, 64)
    assert warning.crop((0, 0, 64, 8)).tobytes() == exposed.crop((0, 0, 64, 8)).tobytes()
    assert warning.tobytes() != exposed.tobytes()


@pytest.mark.parametrize("mode, ticks, cycle", [
    ("dormant", 0, 1), ("cleared", 0, 0), ("cleared", 0, 3),
    ("warning", WARNING_TICKS, 4), ("exposed", EXPOSED_TICKS, -1),
    ("warning", True, 0), ("exposed", 0, 0),
])
def test_impossible_pulse_states_rejected(mode, ticks, cycle):
    with pytest.raises(ValueError, match="root pulse"):
        RootPulse(mode, ticks, cycle)


@pytest.mark.parametrize("hp", [1, 2, 3, 4])
def test_guardian_health_bar_uses_actual_campaign_maximum(guardian, hp):
    from PIL import Image, ImageDraw
    guardian.root_guardian.hp = hp
    image = Image.new("RGB", (144, 104))
    CampaignRenderer(guardian.areas)._actors(ImageDraw.Draw(image), guardian)
    x, y = _center(guardian.root_guardian.position)
    filled = sum(image.getpixel((px, y - 5)) == PALETTE["r"] for px in range(x - 3, x + 4))
    assert filled == int(6 * hp / 4) + 1
    assert Renderer.guardian_health == 8


def test_arrival_on_impact_tick_counts_as_safe(guardian):
    guardian.hero = Actor(8, 2)
    guardian.hero_clock = 1 / 60
    guardian.root_pulse.ticks = 1
    assert encode(decode(encode(guardian))) == encode(guardian)
    guardian.update(1 / 60)
    assert guardian.hero.position == guardian.root_pulse.safe_tile
    assert guardian.hero.hp == MAX_HEARTS
    assert guardian.root_pulse.mode == "exposed"


def test_fatal_pulse_enters_defeat_on_same_tick_and_freezes_encounter(guardian):
    guardian.hero = Actor(8, 2, hp=1)
    guardian.hero_clock = 0.30
    guardian.root_pulse.ticks = 1
    guardian.update(1 / 60)
    assert guardian.hero.hp == 0 and guardian.phase == "defeat"
    pulse = vars(guardian.root_pulse).copy()
    guardian.update(1 / 60)
    assert vars(guardian.root_pulse) == pulse
