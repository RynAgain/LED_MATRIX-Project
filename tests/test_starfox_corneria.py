"""Corneria mission progression, real-loop rendering, and autopilot regressions."""

import math
import random
from types import SimpleNamespace
from unittest.mock import create_autospec

from PIL import Image, ImageDraw
import pytest

from src.display import starfox as sf
from src.display.starfox_scene import draw_arwing, draw_corneria
from src.input.controller import Controller
from src.simulator.matrix import RGBMatrix


@pytest.fixture(autouse=True)
def seeded_random():
    state = random.getstate()
    random.seed(7)
    yield
    random.setstate(state)


def test_opening_then_distinct_formations_and_one_boss():
    mission = sf._CorneriaMission()
    enemies, obstacles = [], []
    for _ in range(mission.OPENING_FRAMES - 1):
        assert mission.update(enemies, obstacles) == (False, False)
        assert not enemies and not obstacles
    for behavior in (sf._Enemy.STRAIGHT, sf._Enemy.SINE, sf._Enemy.DIVE):
        assert mission.update(enemies, obstacles) == (False, False)
        assert len(enemies) == 3
        assert {e.behavior for e in enemies} == {behavior}
        for _ in range(300):
            assert mission.update(enemies, obstacles) == (False, False)
        for enemy in enemies:
            enemy.alive = False
        assert mission.update(enemies, obstacles) == (False, True)
        enemies.clear()
        for _ in range(mission.WAVE_GAP - 1):
            assert mission.update(enemies, obstacles) == (False, False)
    assert mission.update(enemies, obstacles) == (True, False)
    assert mission.phase == "boss" and not obstacles
    for _ in range(300):
        assert mission.update(enemies, obstacles, sf._Boss()) == (False, False)
    assert mission.phase == "boss"
    mission.boss_defeated()
    for _ in range(mission.EXIT_FRAMES - 1):
        assert mission.update(enemies, obstacles) == (False, False)
        assert mission.phase == "victory"
    mission.update(enemies, obstacles)
    assert mission.phase == "complete"
    assert mission.update(enemies, obstacles) == (False, False)
    assert mission.wave_num == 4


def test_no_victory_before_boss():
    mission = sf._CorneriaMission()
    mission.boss_defeated()
    assert mission.phase == "opening"


@pytest.mark.parametrize("position,target,expected", [
    ((35, 38), (32, 48), -1),
    ((29, 38), (32, 48), 1),
    ((32, 53), (32, 90), 0),
    ((32, 38), (60, 48), 0),
    ((32, 48), (32, 48), 0),
])
def test_predictive_dodge(position, target, expected):
    ship = sf._Ship()
    laser = sf._EnemyLaser(*position, *target)
    dx, _, _, roll = sf._AI().decide(ship, [], [], [laser], 0, 0)
    assert roll == expected
    if roll:
        assert dx * roll > 0


def test_steering_brakes_before_overshoot():
    ship = sf._Ship()
    enemy = sf._Enemy()
    enemy.x, enemy.y, enemy.z = 0, 0.6, 6
    ship.vx = 2.0
    dx, _, _, _ = sf._AI().decide(ship, [enemy], [], [], 0, 0)
    assert dx < 0


@pytest.mark.parametrize("angle", [0, -0.5, 0.5, math.pi / 2, math.pi, 4.7])
def test_shaded_arwing_renders_bank_and_roll(angle):
    image = Image.new("RGB", (64, 64))
    draw_arwing(ImageDraw.Draw(image), 32, 45, angle, 5)
    colors = {color for _, color in image.getcolors(4096)}
    assert (55, 180, 250) in colors
    assert (150, 235, 255) in colors
    assert len(colors) >= 7
    assert image.getbbox()[0] >= 20
    assert image.getbbox()[2] <= 44


def test_corneria_is_animated_and_has_river_road_city():
    frames = []
    for scroll in (0, 3, 9):
        image = Image.new("RGB", (64, 64))
        draw_corneria(ImageDraw.Draw(image), scroll, 0, 64, 64, 26)
        colors = {color for _, color in image.getcolors(4096)}
        assert {(29, 91, 130), (83, 89, 85), (121, 147, 149)} <= colors
        frames.append(image.tobytes())
    assert len(set(frames)) == 3


def run_frames(monkeypatch, count, controller=None, on_frame=None):
    matrix = create_autospec(RGBMatrix, instance=True)
    clock = [0.0]
    rendered = []

    def present(image, *args, **kwargs):
        assert isinstance(image, Image.Image)
        assert image.mode == "RGB" and image.size == (64, 64)
        rendered.append(image.copy())
        clock[0] += sf.FRAME_INTERVAL
        if on_frame:
            on_frame(len(rendered), image)

    matrix.SetImage.side_effect = present
    monkeypatch.setattr(sf, "time", SimpleNamespace(time=lambda: clock[0], sleep=lambda _: None))
    monkeypatch.setattr(sf, "should_stop", lambda: len(rendered) >= count)
    monkeypatch.setattr(sf, "show_banner", lambda *args, **kwargs: None)
    sf.run(matrix, duration=count / sf.FPS + 1, controller=controller)
    assert len(rendered) == count
    matrix.Clear.assert_called_once()
    return rendered


@pytest.mark.parametrize("seed", range(5))
def test_real_demo_completes_and_restarts(monkeypatch, caplog, seed):
    random.seed(seed)
    missions = []
    factory = sf._CorneriaMission

    def new_mission():
        mission = factory()
        missions.append(mission)
        return mission

    monkeypatch.setattr(sf, "_CorneriaMission", new_mission)
    monkeypatch.setattr(sf, "_draw_ground", lambda *args: pytest.fail("Demo left Corneria"))
    run_frames(monkeypatch, 1800)
    assert not [record for record in caplog.records if record.levelname == "ERROR"]
    assert any(m.phase == "complete" for m in missions), [m.phase for m in missions]
    assert len(missions) >= 2


def test_interactive_keeps_wave_manager_and_controller(monkeypatch, caplog):
    controller = create_autospec(Controller, instance=True)
    controller.get_direction.return_value = (1, -1)
    controller.poll_events.return_value = []
    controller.is_pressed.side_effect = lambda button: button in (sf.Button.A, sf.Button.SELECT)
    monkeypatch.setattr(sf, "wants_quit", lambda _: False)
    monkeypatch.setattr(sf, "_CorneriaMission", lambda: pytest.fail("Interactive used demo director"))
    frames = run_frames(monkeypatch, 60, controller)
    assert frames[0].tobytes() != frames[-1].tobytes()
    controller.get_direction.assert_called()
    assert not [record for record in caplog.records if record.levelname == "ERROR"]


def test_stop_clears_display_without_rendering(monkeypatch):
    matrix = create_autospec(RGBMatrix, instance=True)
    monkeypatch.setattr(sf, "should_stop", lambda: True)
    sf.run(matrix)
    matrix.SetImage.assert_not_called()
    matrix.Clear.assert_called_once()


def test_boss_approach_is_armored_until_fight():
    boss = sf._Boss()
    boss.z = 8
    laser = sf._Laser(32, 41, boss.x, boss.y + boss.CORE_DY)
    laser.z_prev, laser.z = 7, 9
    assert sf._check_laser_boss(laser, boss) == "body"
    boss.state = "fight"
    assert sf._check_laser_boss(laser, boss) == "core"


def test_cinematic_hides_reticle_and_radio_does_not_overlap_combo():
    ship = sf._Ship()
    images = []
    for combo in (1, 4):
        image = Image.new("RGB", (64, 64))
        sf._draw_hud(ImageDraw.Draw(image), 0, ship, (32, 28), 0,
                     ["ALL CLEAR", 60], False, combo_mult=combo, show_reticle=False)
        assert image.getpixel((32, 28)) == (0, 0, 0)
        images.append(image)
    assert images[0].crop((0, 9, 64, 16)).tobytes() == images[1].crop((0, 9, 64, 16)).tobytes()


def test_demo_death_restarts_with_clean_ship(monkeypatch):
    ships = []
    factory = sf._Ship

    def new_ship():
        ship = factory()
        ships.append(ship)
        return ship

    def kill_once(frame, image):
        if frame == 150:
            ships[0].shield = 0
            ships[0].alive = False

    monkeypatch.setattr(sf, "_Ship", new_ship)
    run_frames(monkeypatch, 170, on_frame=kill_once)
    assert len(ships) == 2
    assert ships[1].shield == 3
    assert ships[1].alive
    assert ships[1].x == ships[1].y == 0


def test_duration_limit_works_during_cinematic(monkeypatch):
    matrix = create_autospec(RGBMatrix, instance=True)
    clock = [0.0]

    def present(image):
        clock[0] += sf.FRAME_INTERVAL

    matrix.SetImage.side_effect = present
    monkeypatch.setattr(sf, "time", SimpleNamespace(time=lambda: clock[0], sleep=lambda _: None))
    monkeypatch.setattr(sf, "should_stop", lambda: False)
    sf.run(matrix, duration=0.15)
    assert matrix.SetImage.call_count == 5
    matrix.Clear.assert_called_once()
