"""
Headless tests for the starfox gameplay rework.

Covers: 3D laser aiming model, aimed enemy lasers, boss lifecycle,
wave-manager difficulty curve + boss scheduling, ship clamps/boost meter,
barrel-roll direction, and AI targeting math.

Run with the mocked-PIL harness (no matrix required):
    python ~/.aki/tmp/run_tests.py tests/test_starfox_sim.py
"""

import math
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import src.display.starfox as sf


def _fire_aligned_laser(ship):
    """Build a laser exactly as run() does."""
    wx, wy = sf._ship_aim_world(ship)
    return sf._Laser(ship.screen_x, ship.screen_y - 7, wx, wy)


class TestLaserModel:
    def test_laser_advances_and_dies_at_zmax(self):
        ship = sf._Ship()
        laser = _fire_aligned_laser(ship)
        steps = 0
        while not laser.is_dead() and steps < 60:
            laser.update()
            steps += 1
        assert laser.z >= laser.Z_MAX
        assert steps < 15, "laser should cross the field in under half a second"

    def test_aligned_ship_hits_enemy(self):
        # Enemy at world (1.0, 0.5); ship aims by sliding to x=5*1.0, y=5*0.5-3
        enemy = sf._Enemy(sf._Enemy.STRAIGHT)
        enemy.x, enemy.y, enemy.z = 1.0, 0.5, 6.0
        ship = sf._Ship()
        ship.x, ship.y = 5.0, -0.5
        laser = _fire_aligned_laser(ship)
        hit = False
        for _ in range(30):
            laser.update()
            if sf._check_laser_enemy(laser, enemy):
                hit = True
                break
        assert hit, "aligned shot must connect"

    def test_misaligned_ship_misses(self):
        enemy = sf._Enemy(sf._Enemy.STRAIGHT)
        enemy.x, enemy.y, enemy.z = 2.0, 0.5, 6.0
        ship = sf._Ship()
        ship.x, ship.y = -5.0, -0.5  # aiming at wx=-1, enemy at +2
        laser = _fire_aligned_laser(ship)
        for _ in range(30):
            laser.update()
            assert not sf._check_laser_enemy(laser, enemy), "off-line shot must miss"

    def test_no_hit_without_depth_crossing(self):
        # Enemy behind the laser's whole travel (z > Z_MAX) is unhittable
        enemy = sf._Enemy(sf._Enemy.STRAIGHT)
        enemy.x, enemy.y, enemy.z = 0.0, 0.0, 15.0
        ship = sf._Ship()
        ship.x, ship.y = 0.0, -3.0
        laser = _fire_aligned_laser(ship)
        for _ in range(30):
            laser.update()
            assert not sf._check_laser_enemy(laser, enemy)


class TestEnemyLaserAiming:
    def test_shot_flies_toward_given_target(self):
        el = sf._EnemyLaser(10.0, 10.0, 40.0, 50.0)
        start = math.hypot(40 - el.x, 50 - el.y)
        for _ in range(8):
            el.update()
        assert math.hypot(40 - el.x, 50 - el.y) < start, "must close on the aim point"

    def test_shot_overshoots_past_target(self):
        # Aim line extends beyond the target so dodged shots fly through
        el = sf._EnemyLaser(10.0, 10.0, 40.0, 50.0)
        assert math.hypot(el.tx - 10, el.ty - 10) > 100


class TestBoss:
    def test_approach_then_fight(self):
        boss = sf._Boss(level=1)
        assert boss.state == "approach"
        for f in range(200):
            boss.update(f)
        assert boss.state == "fight"
        assert 5.0 < boss.z < 8.5

    def test_core_hits_kill_body_hits_dont(self):
        boss = sf._Boss(level=1)
        boss.state = "fight"
        boss.z = 6.5
        boss.x, boss.y = 0.0, -0.4
        # Core shot: ship aims at (boss.x, boss.y + CORE_DY)
        ship = sf._Ship()
        ship.x = 5.0 * boss.x
        ship.y = 5.0 * (boss.y + boss.CORE_DY) - 3.0
        hits = 0
        for _ in range(boss.max_hp + 5):
            laser = _fire_aligned_laser(ship)
            while not laser.is_dead():
                laser.update()
                part = sf._check_laser_boss(laser, boss)
                if part == "core":
                    boss.take_hit()
                    hits += 1
                    break
                elif part == "body":
                    break
            if not boss.alive:
                break
        assert hits == boss.max_hp
        assert not boss.alive

        # Wing shot (world x offset 1.5) must be armor, never core
        boss2 = sf._Boss(level=1)
        boss2.state = "fight"
        boss2.z = 6.5
        ship.x = 5.0 * 1.5
        ship.y = 5.0 * boss2.y - 3.0
        laser = _fire_aligned_laser(ship)
        saw = set()
        while not laser.is_dead():
            laser.update()
            part = sf._check_laser_boss(laser, boss2)
            if part:
                saw.add(part)
                break
        assert saw == {"body"}
        assert boss2.hp == boss2.max_hp

    def test_rage_fires_faster_when_hurt(self):
        boss = sf._Boss(level=1)
        boss.state = "fight"
        boss._fire_cd = 0
        boss.should_fire()
        healthy_cd = boss._fire_cd
        boss.hp = 1
        boss._fire_cd = 0
        boss.should_fire()
        assert boss._fire_cd < healthy_cd


class TestWaveManager:
    def test_boss_wave_every_fifth(self):
        wm = sf._WaveManager()
        wm.wave_num = 4
        wm.wave_timer = 1
        spawn_boss, _ = wm.update([], [])
        assert spawn_boss and wm.wave_num == 5

    def test_boss_holds_wave_clock(self):
        wm = sf._WaveManager()
        wm.wave_timer = 1
        boss = sf._Boss()
        enemies = []
        for _ in range(10):
            spawn, _ = wm.update(enemies, [], boss)
            assert not spawn and not enemies

    def test_wave_clear_bonus_signalled_once(self):
        wm = sf._WaveManager()
        wm.awaiting_clear = True
        wm.wave_timer = 999
        _, cleared = wm.update([], [])
        assert cleared
        _, cleared = wm.update([], [])
        assert not cleared

    def test_difficulty_scales(self):
        e_easy = sf._Enemy(speed_bonus=0.0, fire_scale=1.0)
        e_hard = sf._Enemy(speed_bonus=0.05, fire_scale=0.55)
        assert e_hard.speed >= 0.09 + 0.05 - 1e-9
        assert e_hard._fire_cd <= int(90 * 0.55)
        assert e_easy._fire_cd >= 40


class TestShipControls:
    def test_vertical_clamp_keeps_ship_on_screen(self):
        ship = sf._Ship()
        for _ in range(120):
            ship.move(0, 1.4)
            ship.update(0)
        assert ship.screen_y <= sf.HEIGHT - 16 + ship.MAX_Y_DOWN
        for _ in range(240):
            ship.move(0, -1.4)
            ship.update(0)
        assert ship.screen_y >= sf.HEIGHT - 16 - ship.MAX_Y_UP

    def test_roll_direction_honoured(self):
        ship = sf._Ship()
        assert ship.do_barrel_roll(-1)
        assert ship.roll_dir == -1
        ship2 = sf._Ship()
        assert ship2.do_barrel_roll(1)
        assert ship2.roll_dir == 1

    def test_boost_meter_drains_and_regens(self):
        ship = sf._Ship()
        ship.boosting = True
        for _ in range(30):
            ship.update(0)
        drained = ship.boost_meter
        assert drained < 1.0
        ship.boosting = False
        for _ in range(60):
            ship.update(0)
        assert ship.boost_meter > drained


class TestAI:
    def test_ai_targets_enemy_with_aim_math(self):
        ai = sf._AI()
        ship = sf._Ship()
        enemy = sf._Enemy(sf._Enemy.STRAIGHT)
        enemy.x, enemy.y, enemy.z = 2.0, 0.0, 6.0
        # Slide toward target for many frames; ship should converge on x=10
        for f in range(200):
            dx, dy, fire, roll = ai.decide(ship, [enemy], [], [], 0, f)
            ship.move(dx, dy)
            ship.update(f)
        assert abs(ship.x - 5.0 * enemy.x) < 3.0
        # And once lined up, it should decide to fire
        dx, dy, fire, roll = ai.decide(ship, [enemy], [], [], 0, 999)
        assert fire

    def test_ai_targets_boss_core(self):
        ai = sf._AI()
        ship = sf._Ship()
        boss = sf._Boss()
        boss.state = "fight"
        boss.z = 6.5
        boss.x, boss.y = 1.0, -0.4
        for f in range(240):
            dx, dy, fire, roll = ai.decide(ship, [], [], [], 0, f, boss=boss)
            ship.move(dx, dy)
            ship.update(f)
        assert abs(ship.x - 5.0 * boss.x) < 3.0

    def test_ai_dodges_incoming(self):
        ai = sf._AI()
        ship = sf._Ship()
        el = sf._EnemyLaser(ship.screen_x, sf.HEIGHT * 0.6, ship.screen_x, ship.screen_y)
        dx, dy, fire, roll = ai.decide(ship, [], [], [el], 0, 0)
        assert roll in (-1, 1)
