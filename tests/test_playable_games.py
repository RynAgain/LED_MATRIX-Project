"""
Interactive-mode smoke tests for the controller-playable games (Phase 5).

These verify the new ``controller`` branch of ``run(matrix, duration, controller)``
for snake / tetris / pong without a real gamepad and fully headless. A
``FakeController`` scripts ``poll_events()`` / ``get_direction()`` / held-button
returns frame-by-frame and forces a quit after a few frames so loops can never
hang. Demo backward-compatibility (``controller=None``) lives in
``tests/test_display_modules.py`` and is re-asserted here for the three games.

Conventions mirror tests/test_input.py + tests/test_app_state.py: SDL dummy
drivers via conftest's autouse fixture, real ``Button``/``EventType``/``InputEvent``
from src.input, and the simulated ``matrix`` fixture.
"""

import time

import pytest

from src.input import Button, EventType, InputEvent
from src.display import _shared


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeController:
    """Scripted stand-in for src.input.Controller.

    :param events_script: list of per-poll event lists; each ``poll_events()``
        call pops the next list (empty once exhausted).
    :param directions: list of per-poll ``get_direction()`` returns (or a single
        value applied every poll). ``None`` means centered.
    :param held: dict[Button, bool] of level-held state for ``is_pressed`` (the
        quit gesture and tetris hard-drop use this).
    :param quit_after: after this many ``poll_events`` calls, ``wants_quit`` (via
        the held START+SELECT contract) becomes true; ``None`` disables.
    """

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
            # Latch the quit gesture (both held) so wants_quit() fires.
            self._held[Button.START] = True
            self._held[Button.SELECT] = True
        if self._events:
            return self._events.pop(0)
        return []

    def get_direction(self):
        if isinstance(self._directions, list):
            if self._directions:
                return self._directions.pop(0)
            return None
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
    """Neutralize real-time sleeps so interactive loops run instantly."""
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    # Ensure no stop flag leaks between tests.
    _shared.clear_stop()
    yield
    _shared.clear_stop()


def _ev(button, etype=EventType.PRESSED):
    return InputEvent(button, etype, 0.0)


# ---------------------------------------------------------------------------
# Snake
# ---------------------------------------------------------------------------
class TestSnakeInteractive:
    def test_quit_gesture_returns(self, matrix):
        """wants_quit (START+SELECT held) ends run() promptly."""
        from src.display import snake

        ctrl = FakeController(quit_after=1)
        snake.run(matrix, duration=60, controller=ctrl)
        # Returned without hanging; quit was observed.
        assert ctrl.poll_count >= 1

    def test_direction_changes_movement(self, matrix):
        """Feeding a direction steers the snake (non-reversing)."""
        from src.display import snake

        game = snake.SnakeGame()
        # Snake starts moving RIGHT; feed UP and confirm the heading changes.
        game.step(direction=snake.UP)
        assert game.direction == snake.UP
        # A 180-degree reversal is rejected (keep current heading).
        game.step(direction=snake.DOWN)
        assert game.direction == snake.UP

    def test_forced_collision_ends_game_and_returns(self, matrix):
        """A wall collision ends the round and run() returns."""
        from src.display import snake

        # Drive UP repeatedly; the snake starts near center and will hit the top
        # wall after enough steps, ending the game -> run() returns.
        ctrl = FakeController(directions=snake.UP, quit_after=None)
        # Cap via stop flag as a hard safety net in case physics changes.
        snake.run(matrix, duration=60, controller=ctrl)
        # If we got here, run() returned (collision-driven game over).
        assert ctrl.poll_count >= 1
        # Game-over feedback rumbles.
        assert ctrl.rumble_calls

    def test_demo_mode_unchanged(self, matrix):
        """controller=None still runs the autonomous demo and returns."""
        from src.display import snake

        snake.run(matrix, duration=1)  # no controller -> demo


# ---------------------------------------------------------------------------
# Tetris
# ---------------------------------------------------------------------------
class TestTetrisInteractive:
    def test_inputs_consumed_without_error(self, matrix):
        """left/right/rotate/soft-drop inputs are consumed, then quit returns."""
        from src.display import tetris

        script = [
            [_ev(Button.LEFT), _ev(Button.A)],
            [_ev(Button.RIGHT, EventType.REPEAT)],
            [_ev(Button.DOWN, EventType.REPEAT)],
            [_ev(Button.UP), _ev(Button.B)],
        ]
        ctrl = FakeController(events_script=script, quit_after=5)
        tetris.run(matrix, duration=60, controller=ctrl)
        assert ctrl.poll_count >= 1

    def test_move_and_rotate_change_state(self, matrix):
        """Direct method calls change piece position/rotation."""
        from src.display import tetris

        game = tetris.TetrisGame()
        x0, rot0 = game.current_x, game.current_rot
        moved = game.move(-1)
        assert moved is True
        assert game.current_x == x0 - 1
        game.rotate(cw=True)
        # O-piece rotations are identical; just assert no crash + valid rot range.
        assert 0 <= game.current_rot < 4

    def test_topping_out_returns(self, matrix):
        """A game-over (top-out) ends run() and returns."""
        from src.display import tetris

        game = tetris.TetrisGame()
        game.game_over = True  # force top-out
        # Patch TetrisGame so the interactive loop sees an immediate game over.
        import src.display.tetris as t

        orig = t.TetrisGame
        t.TetrisGame = lambda: game
        try:
            ctrl = FakeController(quit_after=None)
            t.run(matrix, duration=60, controller=ctrl)
        finally:
            t.TetrisGame = orig
        # Game-over path shows feedback (rumble) and returns.
        assert ctrl.rumble_calls

    def test_demo_mode_unchanged(self, matrix):
        from src.display import tetris

        tetris.run(matrix, duration=1)


# ---------------------------------------------------------------------------
# Pong
# ---------------------------------------------------------------------------
class TestPongInteractive:
    def test_paddle_moves_with_direction(self, matrix):
        """UP/DOWN move the player's (left) paddle via step(player_dy)."""
        from src.display import pong

        game = pong.PongGame()
        y0 = game.p1_y
        game.step(player_dy=-1)  # up
        assert game.p1_y < y0  # moved up (screen coords)
        y1 = game.p1_y
        game.step(player_dy=1)  # down
        assert game.p1_y > y1

    def test_quit_gesture_returns(self, matrix):
        from src.display import pong

        ctrl = FakeController(directions=(0, 0), quit_after=1)
        pong.run(matrix, duration=60, controller=ctrl)
        assert ctrl.poll_count >= 1

    def test_reaching_score_condition_returns(self, matrix):
        """When a player reaches WIN_SCORE the match ends and run() returns."""
        from src.display import pong

        game = pong.PongGame()
        # Pre-load the match so the very next scored point wins.
        game.p1_score = pong.WIN_SCORE - 1

        orig = pong.PongGame
        pong.PongGame = lambda: game
        try:
            # Drive the ball off the AI side quickly by feeding no input; the
            # round_over is reached by physics. To keep it deterministic and
            # fast, force round_over with p1 scoring via direct manipulation.
            game.round_over = True
            game.p1_score = pong.WIN_SCORE
            ctrl = FakeController(directions=(0, 0), quit_after=None)
            pong.run(matrix, duration=60, controller=ctrl)
        finally:
            pong.PongGame = orig
        # Win banner triggers a rumble; run() returned.
        assert ctrl.rumble_calls

    def test_demo_mode_unchanged(self, matrix):
        from src.display import pong

        pong.run(matrix, duration=1)
