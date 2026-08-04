"""Interactive-mode tests for galaga / space_invaders / tanks.

These three shipped as demo-only display modules and were promoted to
controller-playable games. The tests cover the player-input plumbing (clamping,
fire-rate limiting, charge-shot power) and re-assert that ``controller=None``
still runs the original autonomous demo.

Follows tests/test_playable_games.py conventions: a scripted FakeController,
neutralized sleeps, and the simulated ``matrix`` fixture.
"""

import time

import pytest

from src.display import _shared
from src.input import Button, EventType, InputEvent


class FakeController:
    """Scripted stand-in for src.input.Controller (see test_playable_games)."""

    def __init__(self, events_script=None, directions=None, held=None,
                 quit_after=None):
        self._events = list(events_script or [])
        self._directions = directions
        self._held = dict(held or {})
        self._quit_after = quit_after
        self.poll_count = 0
        self.rumble_calls = []

    def poll_events(self):
        self.poll_count += 1
        if self._quit_after is not None and self.poll_count >= self._quit_after:
            self._held[Button.START] = True
            self._held[Button.SELECT] = True
        if self._events:
            return self._events.pop(0)
        return []

    def get_direction(self):
        if isinstance(self._directions, list):
            return self._directions.pop(0) if self._directions else None
        return self._directions

    def is_pressed(self, button):
        return bool(self._held.get(button, False))

    def is_connected(self):
        return True

    def start_hold_seconds(self):
        return 0.0

    def rumble(self, strength=1.0, duration_ms=200):
        self.rumble_calls.append((strength, duration_ms))


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    _shared.clear_stop()
    yield
    _shared.clear_stop()


def _ev(button, etype=EventType.PRESSED):
    return InputEvent(button, etype, 0.0)


# ---------------------------------------------------------------------------
# Galaga
# ---------------------------------------------------------------------------
class TestGalagaInteractive:
    def test_manual_update_clamps_to_playfield(self):
        from src.display import galaga

        ship = galaga.Ship()
        for _ in range(200):
            ship.manual_update(-5, -5, False)
        assert ship.x >= 2
        assert ship.y >= galaga.HEIGHT - 18
        for _ in range(400):
            ship.manual_update(5, 5, False)
        assert ship.x <= galaga.WIDTH - 3
        assert ship.y <= galaga.HEIGHT - 3

    def test_manual_update_ticks_cooldown_when_not_firing(self):
        """The cooldown must drain between shots, or fire stays locked out."""
        from src.display import galaga

        ship = galaga.Ship()
        ship.shoot()
        assert ship.cooldown > 0
        before = ship.cooldown
        ship.manual_update(0, 0, False)
        assert ship.cooldown < before

    def test_fire_rate_is_limited_by_cooldown(self):
        """Holding fire cannot emit a bullet on every single frame."""
        from src.display import galaga

        ship = galaga.Ship()
        for _ in range(10):
            ship.manual_update(0, 0, True)
        # 10 frames of held fire must not produce 10 bullets.
        assert 0 < len(ship.bullets) < 10

    def test_bullets_travel_upward_and_expire(self):
        from src.display import galaga

        ship = galaga.Ship()
        ship.manual_update(0, 0, True)
        assert ship.bullets
        start_y = ship.bullets[0][1]
        ship.manual_update(0, 0, False)
        assert ship.bullets[0][1] < start_y
        for _ in range(60):
            ship.manual_update(0, 0, False)
        assert ship.bullets == []

    def test_quit_gesture_returns(self, matrix):
        from src.display import galaga

        ctrl = FakeController(quit_after=1)
        galaga.run(matrix, duration=60, controller=ctrl)
        assert ctrl.poll_count >= 1

    def test_inputs_consumed_without_error(self, matrix):
        from src.display import galaga

        ctrl = FakeController(
            events_script=[[_ev(Button.A)], [], [_ev(Button.A)]],
            directions=[(-1, 0), (1, 0), (0, -1), (0, 1)],
            quit_after=6,
        )
        galaga.run(matrix, duration=60, controller=ctrl)
        assert ctrl.poll_count >= 1

    def test_demo_mode_unchanged(self, matrix):
        from src.display import galaga

        galaga.run(matrix, duration=1)


# ---------------------------------------------------------------------------
# Space Invaders
# ---------------------------------------------------------------------------
class TestSpaceInvadersInteractive:
    def test_quit_gesture_returns(self, matrix):
        from src.display import space_invaders

        ctrl = FakeController(quit_after=1)
        space_invaders.run(matrix, duration=60, controller=ctrl)
        assert ctrl.poll_count >= 1

    def test_inputs_consumed_without_error(self, matrix):
        from src.display import space_invaders

        ctrl = FakeController(
            events_script=[[_ev(Button.A)], [_ev(Button.A)], [_ev(Button.A)]],
            directions=[(-1, 0), (1, 0), None],
            quit_after=8,
        )
        space_invaders.run(matrix, duration=60, controller=ctrl)
        assert ctrl.poll_count >= 1

    def test_demo_mode_unchanged(self, matrix):
        from src.display import space_invaders

        space_invaders.run(matrix, duration=1)


# ---------------------------------------------------------------------------
# Tanks
# ---------------------------------------------------------------------------
class TestTanksInteractive:
    def test_shoot_accepts_explicit_charge_power(self):
        from src.display import tanks

        tank = tanks.Tank(10, True, (0, 0, 255), (100, 100, 255))
        tank.cooldown = 0
        shell = tank.shoot(power=5.5)
        assert shell is not None
        assert tank.power == pytest.approx(5.5)

    def test_shoot_respects_cooldown(self):
        from src.display import tanks

        tank = tanks.Tank(10, True, (0, 0, 255), (100, 100, 255))
        tank.cooldown = 0
        assert tank.shoot(power=4.0) is not None
        assert tank.cooldown > 0
        assert tank.shoot(power=4.0) is None

    def test_higher_charge_gives_faster_shell(self):
        """The charge meter must actually translate into muzzle velocity."""
        from src.display import tanks

        def launch(power):
            tank = tanks.Tank(10, True, (0, 0, 255), (100, 100, 255))
            tank.cooldown = 0
            shell = tank.shoot(power=power)
            return abs(shell.vx) + abs(shell.vy)

        assert launch(5.5) > launch(2.5)

    def test_win_score_is_defined(self):
        from src.display import tanks

        assert tanks.WIN_SCORE >= 1

    def test_quit_gesture_returns(self, matrix):
        from src.display import tanks

        ctrl = FakeController(quit_after=1)
        tanks.run(matrix, duration=60, controller=ctrl)
        assert ctrl.poll_count >= 1

    def test_inputs_consumed_without_error(self, matrix):
        from src.display import tanks

        ctrl = FakeController(
            events_script=[[], [], []],
            directions=[(-1, 0), (1, 0), (0, -1), (0, 1)],
            held={Button.A: True},
            quit_after=8,
        )
        tanks.run(matrix, duration=60, controller=ctrl)
        assert ctrl.poll_count >= 1

    def test_demo_mode_unchanged(self, matrix):
        from src.display import tanks

        tanks.run(matrix, duration=1)


# ---------------------------------------------------------------------------
# Registration / wiring
# ---------------------------------------------------------------------------
class TestRegistration:
    @pytest.mark.parametrize("name", ["galaga", "space_invaders", "tanks"])
    def test_listed_as_playable(self, name):
        from src.app_state import PLAYABLE_GAMES

        assert name in PLAYABLE_GAMES

    @pytest.mark.parametrize("name", ["galaga", "space_invaders", "tanks"])
    def test_appears_in_games_menu(self, name):
        from src.menu.menu_data import build_games_menu

        menu = build_games_menu([name])
        payloads = [item.payload for item in menu.items]
        assert name in payloads

    @pytest.mark.parametrize("name", ["galaga", "space_invaders", "tanks"])
    def test_has_friendly_label(self, name):
        from src.menu.menu_data import build_games_menu

        menu = build_games_menu([name])
        labels = [item.label for item in menu.items if item.payload == name]
        assert labels and labels[0] == labels[0].upper()
        # A friendly label never leaks the raw module name's underscores.
        assert "_" not in labels[0]

    @pytest.mark.parametrize("name", ["galaga", "space_invaders", "tanks"])
    def test_run_signature_accepts_controller(self, name):
        """run_feature only forwards the controller when run() declares it."""
        import importlib
        import inspect

        mod = importlib.import_module(f"src.display.{name}")
        params = inspect.signature(mod.run).parameters
        assert "controller" in params
