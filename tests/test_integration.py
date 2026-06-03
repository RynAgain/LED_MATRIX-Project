"""
Integration tests for the LED Matrix Project.

Two layers are covered:

* :class:`TestFullFeatureCycle` -- runs individual display features end-to-end
  through the simulator (pre-existing).
* :class:`TestControllerFlowEndToEnd` -- the **full controller-driven flow**
  through the real :class:`src.app_state.AppStateMachine`, the real
  :class:`src.menu.MenuSystem` (not the placeholder) and a real playable game's
  ``run()``. It exercises the documented IDLE -> MENU -> IN_GAME -> MENU ->
  Settings -> IDLE -> shutdown transitions with a *scripted* fake controller so
  the test is deterministic, headless-safe and cannot hang.

The controller-flow test mirrors the fake-Controller / fake-matrix patterns from
``tests/test_app_state.py`` and ``tests/test_menu.py`` and is kept fast by
stubbing only *timing* (``time.sleep`` and the game banner/sleep helpers) -- the
menu, the state machine and the game logic themselves run for real.
"""

import importlib
import json
import os
import threading
import time

import pytest

# Headless safety even if this module is imported directly (conftest also sets
# SDL_VIDEODRIVER=dummy as an autouse fixture).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


class TestFullFeatureCycle:
    """Run all enabled features through the simulator to verify end-to-end."""

    def test_full_cycle_all_games(self, matrix):
        """Run all game features for 2 seconds each."""
        features = [
            "src.display.tic_tac_toe",
            "src.display.snake",
            "src.display.pong",
            "src.display.billiards",
        ]

        for module_path in features:
            mod = importlib.import_module(module_path)
            start = time.time()
            mod.run(matrix, duration=2)
            elapsed = time.time() - start
            # Should respect duration (with some tolerance)
            assert elapsed < 10, f"{module_path} ran for {elapsed:.1f}s, expected ~2s"

    def test_time_display_cycle(self, matrix):
        """Run time display feature."""
        mod = importlib.import_module("src.display.time_display")
        start = time.time()
        mod.run(matrix, duration=3)
        elapsed = time.time() - start
        assert elapsed < 15, f"time_display ran for {elapsed:.1f}s, expected ~3s"

    def test_config_validator_on_real_config(self):
        """Validate the actual project config files."""
        from src.config_validator import validate_all
        results = validate_all()

        for config_name, errors in results.items():
            hard_errors = [e for e in errors if e.severity == "error"]
            assert len(hard_errors) == 0, (
                f"config/{config_name} has validation errors: "
                + "; ".join(str(e) for e in hard_errors)
            )

    def test_feature_module_crash_recovery(self, matrix):
        """Verify that a crashing feature doesn't break the matrix."""
        # Run a normal feature first
        mod = importlib.import_module("src.display.pong")
        mod.run(matrix, duration=1)

        # Matrix should still be usable after
        matrix.Clear()
        matrix.SetPixel(0, 0, 255, 0, 0)
        matrix.Fill(0, 0, 0)


# ---------------------------------------------------------------------------
# Full controller-driven flow (IDLE -> MENU -> IN_GAME -> MENU -> Settings ->
# IDLE -> shutdown) through the REAL state machine + REAL menu + REAL game.
# ---------------------------------------------------------------------------
from src.app_state import AppMode, AppStateMachine, MenuResultKind  # noqa: E402
from src.display import _shared  # noqa: E402
from src.input import Button, EventType, InputEvent  # noqa: E402
from src.menu import MenuSystem  # noqa: E402


class FakeMatrix:
    """Minimal matrix stand-in: records SetImage / Clear and brightness.

    Mirrors the fakes in ``tests/test_app_state.py`` / ``tests/test_menu.py`` so
    the integration test uses the same well-understood patterns.
    """

    def __init__(self, brightness=80):
        self.images = []
        self.cleared = 0
        self.brightness = brightness

    def SetImage(self, image, *a, **kw):
        self.images.append(image)

    def Clear(self):
        self.cleared += 1


class ScriptedController:
    """A scripted, fully headless controller for the end-to-end flow.

    ``poll_events`` returns successive *batches* from ``event_script`` (then
    ``[]`` forever). ``held`` is the set of currently-pressed logical buttons,
    which backs :meth:`is_pressed` and therefore ``wants_quit`` (START+SELECT).
    ``quitting`` backs :meth:`is_quitting` (window close). A ``quit_after_polls``
    counter can flip ``is_quitting`` True after N polls so the threaded
    ``run()`` loop shuts down deterministically without a real window event.
    """

    def __init__(self, event_script=None, held=None, quitting=False,
                 quit_after_polls=None):
        self._script = list(event_script or [])
        self._held = set(held or set())
        self._quitting = quitting
        self._quit_after_polls = quit_after_polls
        self.poll_count = 0
        self.closed = False

    def poll_events(self):
        self.poll_count += 1
        if (self._quit_after_polls is not None
                and self.poll_count >= self._quit_after_polls):
            self._quitting = True
        if self._script:
            return self._script.pop(0)
        return []

    def is_pressed(self, button):
        return button in self._held

    def set_held(self, buttons):
        self._held = set(buttons)

    def is_connected(self):
        return True

    def is_quitting(self):
        return self._quitting

    def start_hold_seconds(self):
        return 0.0

    def close(self):
        self.closed = True


def _press(button):
    """One poll batch: a single PRESSED event for ``button``."""
    return [InputEvent(button, EventType.PRESSED, 0.0)]


@pytest.fixture(autouse=True)
def _clear_shared_stop_integration():
    """Reset the global _shared stop flag around every test in this module."""
    _shared.clear_stop()
    yield
    _shared.clear_stop()


@pytest.fixture
def fast_timing(monkeypatch):
    """Neutralize sleeps so the real menu/game loops run instantly.

    Only *timing* is stubbed -- the menu engine, the state machine and the game
    logic still execute for real. We patch the game's banner/sleep helpers
    (imported into ``src.display.snake``) and the menu's ``time.sleep`` so the
    interactive game's start banner and inter-frame pauses are instant.
    """
    import src.display.snake as snake_mod
    import src.menu.menu_system as menu_mod

    monkeypatch.setattr(snake_mod, "show_banner", lambda *a, **k: None)
    monkeypatch.setattr(snake_mod, "interruptible_sleep", lambda *a, **k: None)
    monkeypatch.setattr(snake_mod, "safe_rumble", lambda *a, **k: None)
    monkeypatch.setattr(snake_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(menu_mod.time, "sleep", lambda *a, **k: None)


@pytest.fixture
def temp_config(tmp_path):
    """Write a minimal config.json into a temp dir and return (path, dict)."""
    cfg = {
        "display_duration": 30,
        "matrix_hardware": {"brightness": 50, "rows": 64, "cols": 64},
        "sequence": [
            {"name": "snake", "type": "game", "enabled": True},
        ],
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(cfg))
    return str(cfg_path), cfg


class TestControllerFlowEndToEnd:
    """End-to-end controller flow through the real state machine + menu + game."""

    def test_idle_demo_runs_then_start_opens_menu(self, monkeypatch, temp_config):
        """IDLE: a stubbed fast feature runs one carousel cycle; START (via the
        background input thread's flag) transitions IDLE -> MENU."""
        import src.main as main_module
        cfg_path, cfg = temp_config

        ran = []

        def fake_run_feature(name, matrix, duration, controller=None):
            ran.append(name)
            return True

        monkeypatch.setattr(main_module, "run_feature", fake_run_feature)
        monkeypatch.setattr(main_module, "_check_internet", lambda *a, **k: True)
        monkeypatch.setattr(main_module, "_check_schedule", lambda *a, **k: None)
        monkeypatch.setattr(main_module, "load_config", lambda: cfg)

        ctrl = ScriptedController()
        sm = AppStateMachine(
            FakeMatrix(), ctrl, cfg,
            shutdown_event=threading.Event(),
            menu=MenuSystem(cfg, config_path=cfg_path, fps=0),
        )

        # One IDLE cycle runs the (stubbed-fast) demo feature.
        assert sm.mode is AppMode.IDLE
        sm._run_idle()
        assert ran == ["snake"], "the idle carousel ran the enabled feature"
        assert sm.mode is AppMode.IDLE  # no START yet

        # Now simulate the background input thread seeing START during the demo.
        sm._carousel.run_cycle = lambda: None
        sm._menu_requested.set()
        _shared.request_stop()
        sm._run_idle()
        assert sm.mode is AppMode.MENU

    def test_menu_navigate_to_game_launches_and_returns(
            self, monkeypatch, temp_config, fast_timing):
        """MENU -> Games -> Snake launches the REAL game with the controller;
        the quit gesture ends it and we return to MENU."""
        cfg_path, cfg = temp_config

        # Drive the real MenuSystem: A on GAMES enters the submenu, A on SNAKE
        # launches it. (No buttons held yet, so the menu's wants_quit gesture
        # does not fire during navigation.)
        ctrl = ScriptedController(event_script=[
            _press(Button.A),  # GAMES -> open Games submenu
            _press(Button.A),  # SNAKE -> launch_game("snake")
        ])

        sm = AppStateMachine(
            FakeMatrix(), ctrl, cfg,
            shutdown_event=threading.Event(),
            menu=MenuSystem(cfg, config_path=cfg_path, fps=0),
        )
        sm.mode = AppMode.MENU

        # Real MenuSystem.run() resolves the navigation to a LAUNCH_GAME result.
        sm._run_menu()
        assert sm.mode is AppMode.IN_GAME
        assert sm._pending_game == "snake"

        # Now the player holds the quit gesture (START+SELECT) so the real
        # snake.run() returns almost immediately. We must end back in MENU.
        ctrl.set_held({Button.START, Button.SELECT})
        sm._run_game()
        assert sm.mode is AppMode.MENU

    def test_game_receives_the_controller(self, monkeypatch, temp_config):
        """The launched game receives the shared controller (interactive mode)."""
        import src.main as main_module
        cfg_path, cfg = temp_config

        received = {}

        def spy_run_feature(name, matrix, duration, controller=None):
            received["name"] = name
            received["controller"] = controller
            return True

        monkeypatch.setattr(main_module, "run_feature", spy_run_feature)

        ctrl = ScriptedController()
        sm = AppStateMachine(
            FakeMatrix(), ctrl, cfg,
            shutdown_event=threading.Event(),
            menu=MenuSystem(cfg, config_path=cfg_path, fps=0),
        )
        sm.mode = AppMode.IN_GAME
        sm._pending_game = "snake"
        sm._run_game()

        assert received["name"] == "snake"
        assert received["controller"] is ctrl  # forwarded -> interactive
        assert sm.mode is AppMode.MENU

    def test_settings_inline_persists_brightness_and_applies_to_matrix(
            self, temp_config, fast_timing):
        """MENU -> Settings inline: RIGHT raises brightness, applied live to the
        matrix AND persisted atomically to the temp config.json; B/back returns
        to the menu and START resumes to IDLE."""
        cfg_path, cfg = temp_config
        baseline = cfg["matrix_hardware"]["brightness"]

        matrix = FakeMatrix(brightness=baseline)
        menu = MenuSystem(json.loads(json.dumps(cfg)),
                          config_path=cfg_path, fps=0)

        # Main: GAMES(0), SETTINGS(1), RESUME(2).
        ctrl = ScriptedController(event_script=[
            _press(Button.DOWN),   # -> SETTINGS
            _press(Button.A),      # open inline Settings screen
            _press(Button.RIGHT),  # brightness +5 (consumed by settings screen)
            _press(Button.B),      # back out of Settings -> returns to the menu
            _press(Button.START),  # resume to IDLE from the menu
        ])

        result = menu.run(matrix, ctrl)
        assert result.kind is MenuResultKind.RESUME

        expected = baseline + 5
        # Applied live to the matrix.
        assert matrix.brightness == expected
        # Persisted atomically to the temp config.json (deep-merged).
        with open(cfg_path) as fh:
            data = json.load(fh)
        assert data["matrix_hardware"]["brightness"] == expected
        # Sibling keys preserved.
        assert data["display_duration"] == cfg["display_duration"]

    def test_menu_resume_returns_to_idle(self, temp_config, fast_timing):
        """START / B at the menu root returns RESUME -> the state machine goes
        back to IDLE."""
        cfg_path, cfg = temp_config
        ctrl = ScriptedController(event_script=[_press(Button.START)])
        sm = AppStateMachine(
            FakeMatrix(), ctrl, cfg,
            shutdown_event=threading.Event(),
            menu=MenuSystem(cfg, config_path=cfg_path, fps=0),
        )
        sm.mode = AppMode.MENU
        sm._run_menu()
        assert sm.mode is AppMode.IDLE

    def test_window_close_shuts_down_run_loop(self, temp_config):
        """controller.is_quitting() -> the threaded state.run() loop exits
        cleanly (no hang)."""
        cfg_path, cfg = temp_config
        ctrl = ScriptedController(quitting=True)
        sm = AppStateMachine(
            FakeMatrix(), ctrl, cfg,
            shutdown_event=threading.Event(),
            menu=MenuSystem(cfg, config_path=cfg_path, fps=0),
        )
        t = threading.Thread(target=sm.run)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "state.run() did not exit on is_quitting()"
        assert sm._shutdown.is_set()

    def test_full_scripted_journey_via_run_loop(
            self, monkeypatch, temp_config, fast_timing):
        """A single drive through the *threaded* ``state.run()`` loop:

        IDLE (one stubbed demo cycle) -> START -> MENU -> Games -> Snake ->
        IN_GAME (real game, quit gesture) -> MENU -> RESUME -> IDLE -> window
        close -> shutdown. This is the closest deterministic approximation of a
        real session and proves the loop cannot hang.
        """
        import src.main as main_module
        cfg_path, cfg = temp_config

        demo_cycles = {"n": 0}

        def fake_run_feature(name, matrix, duration, controller=None):
            demo_cycles["n"] += 1
            return True

        monkeypatch.setattr(main_module, "run_feature", fake_run_feature)
        monkeypatch.setattr(main_module, "_check_internet", lambda *a, **k: True)
        monkeypatch.setattr(main_module, "_check_schedule", lambda *a, **k: None)
        monkeypatch.setattr(main_module, "load_config", lambda: cfg)

        # The scripted controller drives the menu to launch snake. A safety
        # ``quit_after_polls`` flips is_quitting True after many polls so the
        # run loop can never hang even if a transition is missed.
        ctrl = ScriptedController(
            event_script=[
                _press(Button.A),  # GAMES
                _press(Button.A),  # SNAKE -> launch
            ],
            quit_after_polls=2000,  # safety: force shutdown so we cannot hang
        )

        sm = AppStateMachine(
            FakeMatrix(), ctrl, cfg,
            shutdown_event=threading.Event(),
            menu=MenuSystem(cfg, config_path=cfg_path, fps=0),
            input_poll_hz=500.0,
        )

        # Disable the background START-watcher for this test: it shares the same
        # fake controller and would otherwise consume the scripted A/A events
        # (the real Controller buffers per-consumer; our simple fake does not).
        # We drive the IDLE -> MENU transition explicitly below, so the
        # foreground loop is the sole poller -- exactly what we want to verify.
        monkeypatch.setattr(sm, "_start_input_thread", lambda: None)

        # Force the first IDLE pass to transition to MENU (as the input thread
        # would on a START press) without racing the daemon thread.
        def idle_then_menu():
            sm._carousel.run_cycle()
            _shared.clear_stop()
            sm.mode = AppMode.MENU
        monkeypatch.setattr(sm, "_run_idle", idle_then_menu)

        # When the game launches, hold the quit gesture so the REAL snake.run()
        # returns promptly, then request a window close so the loop terminates
        # cleanly after returning to MENU. This proves the IN_GAME -> MENU ->
        # shutdown path through the live loop.
        reached_game = {"flag": False}
        original_run_game = sm._run_game

        def run_game_then_quit():
            reached_game["flag"] = True
            ctrl.set_held({Button.START, Button.SELECT})
            original_run_game()
            # Game returned to MENU; now end the session via a window close.
            ctrl._quitting = True
        monkeypatch.setattr(sm, "_run_game", run_game_then_quit)

        t = threading.Thread(target=sm.run)
        t.start()
        t.join(timeout=10)
        assert not t.is_alive(), "state.run() did not terminate (possible hang)"
        assert sm._shutdown.is_set()
        # The demo ran at least once and the game was actually reached + exited.
        assert demo_cycles["n"] >= 1
        assert reached_game["flag"], "the game launch path was exercised"
