"""
Tests for Missile Command: entities, wave flow, combat, AI, and rendering.
"""

import math
from unittest.mock import MagicMock, patch

import pytest

from src.display.missile_command import (
    MissileCommandGame, EnemyMissile, Interceptor, Explosion,
    SIZE, CITY_Y, CITY_XS, BATTERY_X, BATTERY_TIP_Y,
    INTERCEPTOR_SPEED, EXPLOSION_MAX_RADIUS, MAX_INTERCEPTORS,
    CURSOR_MIN_Y, CURSOR_MAX_Y, MIRV_WAVE, SCORE_PER_MISSILE,
)


def _step_n(game, n, ai=False):
    results = []
    for _ in range(n):
        results.append(game.step(ai_mode=ai))
    return results


class TestEnemyMissile:
    def test_flies_toward_target(self):
        m = EnemyMissile(10, 0, 50, CITY_Y, speed=0.5)
        d0 = math.hypot(m.target_x - m.x, m.target_y - m.y)
        for _ in range(20):
            m.update()
        d1 = math.hypot(m.target_x - m.x, m.target_y - m.y)
        assert d1 < d0

    def test_reports_arrival(self):
        m = EnemyMissile(30, 0, 30, CITY_Y, speed=2.0)
        arrived = False
        for _ in range(100):
            if m.update():
                arrived = True
                break
        assert arrived
        assert m.y >= CITY_Y


class TestInterceptor:
    def test_reaches_detonation_point(self):
        it = Interceptor(10, 20)
        arrived = False
        for _ in range(100):
            if it.update():
                arrived = True
                break
        assert arrived
        assert math.hypot(it.x - 10, it.y - 20) <= INTERCEPTOR_SPEED * 2

    def test_starts_at_battery(self):
        it = Interceptor(50, 10)
        assert it.x == BATTERY_X
        assert it.y == BATTERY_TIP_Y


class TestExplosion:
    def test_grows_holds_shrinks_and_dies(self):
        e = Explosion(32, 32)
        max_seen = 0.0
        alive = True
        for _ in range(300):
            alive = e.update()
            max_seen = max(max_seen, e.radius)
            if not alive:
                break
        assert not alive
        assert max_seen == pytest.approx(EXPLOSION_MAX_RADIUS)

    def test_contains(self):
        e = Explosion(32, 32)
        e.radius = 5.0
        assert e.contains(34, 34)
        assert not e.contains(45, 45)


class TestGameFlow:
    def test_initial_state(self):
        game = MissileCommandGame()
        assert game.wave == 1
        assert game.ammo > 0
        assert all(c["alive"] for c in game.cities)
        assert game.battery_alive

    def test_enemies_spawn_over_time(self):
        game = MissileCommandGame()
        _step_n(game, 120)
        assert len(game.enemies) >= 1

    def test_enemies_target_alive_ground_structures(self):
        game = MissileCommandGame()
        _step_n(game, 600)
        valid_x = set(CITY_XS) | {BATTERY_X}
        for e in game.enemies:
            assert e.target_x in valid_x

    def test_fire_spends_ammo_and_caps_in_flight(self):
        game = MissileCommandGame()
        ammo0 = game.ammo
        fired = 0
        for _ in range(10):
            if game.fire():
                fired += 1
        assert fired == MAX_INTERCEPTORS
        assert game.ammo == ammo0 - MAX_INTERCEPTORS

    def test_no_fire_without_ammo(self):
        game = MissileCommandGame()
        game.ammo = 0
        assert not game.fire()

    def test_no_fire_with_dead_battery(self):
        game = MissileCommandGame()
        game.battery_alive = False
        assert not game.fire()

    def test_cursor_clamped(self):
        game = MissileCommandGame()
        game.move_cursor(-1000, -1000)
        assert game.cursor_x >= 2
        assert game.cursor_y == CURSOR_MIN_Y
        game.move_cursor(1000, 1000)
        assert game.cursor_x <= SIZE - 3
        assert game.cursor_y == CURSOR_MAX_Y

    def test_explosion_kills_warhead_and_scores(self):
        game = MissileCommandGame()
        game._to_spawn = 0
        enemy = EnemyMissile(30, 0, 30, CITY_Y, speed=0.0)
        enemy.vx = enemy.vy = 0.0
        enemy.y = 20.0
        game.enemies = [enemy]
        boom = Explosion(30, 20)
        boom.radius = 5.0
        boom.phase = "hold"
        game.explosions = [boom]
        score0 = game.score
        game.step()
        assert enemy not in game.enemies
        assert game.score == score0 + SCORE_PER_MISSILE * game.wave

    def test_chain_explosion_spawned_on_kill(self):
        game = MissileCommandGame()
        game._to_spawn = 0
        enemy = EnemyMissile(30, 0, 30, CITY_Y, speed=0.0)
        enemy.vx = enemy.vy = 0.0
        enemy.y = 20.0
        game.enemies = [enemy]
        boom = Explosion(30, 20)
        boom.radius = 5.0
        game.explosions = [boom]
        game.step()
        assert len(game.explosions) >= 2

    def test_ground_impact_destroys_city(self):
        game = MissileCommandGame()
        city_x = CITY_XS[0]
        game._ground_impact(city_x)
        assert not game.cities[0]["alive"]

    def test_battery_impact_kills_ammo(self):
        game = MissileCommandGame()
        game._ground_impact(BATTERY_X)
        assert not game.battery_alive
        assert game.ammo == 0

    def test_wave_clear_and_bonus(self):
        game = MissileCommandGame()
        game._to_spawn = 0
        game.enemies = []
        game.interceptors = []
        game.explosions = []
        score0 = game.score
        result = game.step()
        assert result == "wave_clear"
        assert game.score > score0  # ammo + city bonus

    def test_next_wave_escalates(self):
        game = MissileCommandGame()
        speed1 = game.enemy_speed
        count1 = game._to_spawn
        game.next_wave()
        assert game.wave == 2
        assert game.enemy_speed > speed1
        assert game._to_spawn > count1
        assert game.ammo > 0

    def test_game_over_when_all_cities_dead(self):
        game = MissileCommandGame()
        for c in game.cities:
            c["alive"] = False
        game._to_spawn = 0
        game.enemies = []
        game.explosions = []
        result = game.step()
        assert result == "game_over"
        assert game.game_over

    def test_bonus_city_rebuilt_on_score(self):
        game = MissileCommandGame()
        game.cities[2]["alive"] = False
        game.score = 2600
        game._maybe_award_bonus_city()
        assert game.cities[2]["alive"]

    def test_mirv_splits(self):
        game = MissileCommandGame()
        game.wave = MIRV_WAVE
        game._to_spawn = 0
        mirv = EnemyMissile(30, 0, 30, CITY_Y, speed=0.5, can_split=True)
        mirv.split_y = 5.0
        mirv.y = 6.0
        game.enemies = [mirv]
        game.step()
        assert len(game.enemies) >= 2
        assert not mirv.can_split


class TestAI:
    def test_ai_eventually_fires(self):
        game = MissileCommandGame()
        fired = False
        for _ in range(1200):
            ammo_before = game.ammo
            result = game.step(ai_mode=True)
            if game.ammo < ammo_before or game.interceptors:
                fired = True
                break
            if result == "wave_clear":
                game.next_wave()
        assert fired

    def test_ai_moves_cursor_toward_threat(self):
        game = MissileCommandGame()
        game._to_spawn = 0
        enemy = EnemyMissile(50, 0, 50, CITY_Y, speed=0.001)
        enemy.y = 30.0
        game.enemies = [enemy]
        game.cursor_x, game.cursor_y = 5.0, 10.0
        d0 = math.hypot(game.cursor_x - 50, game.cursor_y - 30)
        for _ in range(5):
            game._ai_defend()
        d1 = math.hypot(game.cursor_x - 50, game.cursor_y - 30)
        assert d1 < d0


class TestDrawing:
    def test_draw_produces_lit_pixels(self):
        game = MissileCommandGame()
        _step_n(game, 90)
        img = game.draw()
        assert img.size == (SIZE, SIZE)
        lit = sum(1 for px in img.convert("RGB").getdata() if sum(px) > 30)
        assert lit > 100  # ground + cities + HUD at minimum

    def test_dead_city_draws_differently(self):
        game = MissileCommandGame()
        img_alive = game.draw()
        for c in game.cities:
            c["alive"] = False
        img_dead = game.draw()
        assert list(img_alive.getdata()) != list(img_dead.getdata())


class TestRunSmoke:
    def test_demo_run_draws(self):
        from src.display import missile_command
        matrix = MagicMock()
        with patch("src.display.missile_command.should_stop", return_value=False):
            missile_command.run(matrix, duration=0.5)
        assert matrix.SetImage.call_count >= 2
        matrix.Clear.assert_called()


class TestAIFireDiscipline:
    def _lone_enemy_game(self, tx=32, speed=0.3):
        game = MissileCommandGame()
        game._to_spawn = 0
        game._spawn_timer = 10**9
        enemy = EnemyMissile(tx, 0, tx, CITY_Y, speed=speed)
        enemy.y = 12.0
        game.enemies = [enemy]
        return game

    def test_ai_does_not_double_target_a_covered_enemy(self):
        """One warhead must cost at most one round (plus one miss retry)."""
        game = self._lone_enemy_game(tx=25)
        ammo0 = game.ammo
        for _ in range(600):
            if game.step(ai_mode=True) != "playing":
                break
        assert not game.enemies, "AI never dealt with the lone warhead"
        assert ammo0 - game.ammo <= 2, (
            f"AI wasted {ammo0 - game.ammo} rounds on one warhead")

    def test_ai_intercepts_a_lone_threat_before_impact(self):
        game = self._lone_enemy_game(tx=CITY_XS[2])
        alive0 = sum(1 for c in game.cities if c["alive"])
        for _ in range(600):
            if game.step(ai_mode=True) != "playing":
                break
        assert sum(1 for c in game.cities if c["alive"]) == alive0

    def test_ai_holds_fire_on_dead_ground_when_ammo_is_tight(self):
        """A warhead falling on rubble is not worth one of the last rounds."""
        game = MissileCommandGame()
        game._to_spawn = 0
        game._spawn_timer = 10**9
        dead_x = CITY_XS[0]
        for c in game.cities:
            if c["x"] == dead_x:
                c["alive"] = False
        game.ammo = 2
        enemy = EnemyMissile(dead_x, 0, dead_x, CITY_Y, speed=0.3)
        enemy.y = 12.0
        game.enemies = [enemy]
        for _ in range(600):
            if game.step(ai_mode=True) != "playing":
                break
        assert game.ammo == 2, "AI wasted scarce ammo on a dud"

    def test_ai_survival_benchmark(self):
        """Seeded end-to-end run: the AI must hold the line for many waves.

        The pre-discipline AI died on wave 4 with 3 cities on this seed;
        anything below wave 6 with 2 cities is a regression.
        """
        import random as _random
        _random.seed(11)
        game = MissileCommandGame()
        for _ in range(30 * 60 * 6):    # up to six simulated minutes
            result = game.step(ai_mode=True)
            if result == "wave_clear":
                game.next_wave()
                if game.wave >= 6:
                    break
            elif result == "game_over":
                break
        assert not game.game_over
        assert game.wave >= 6
        assert sum(1 for c in game.cities if c["alive"]) >= 2
