"""
Unit tests for the application state machine (src/app_state.py, Phase 2).

These tests are **headless-safe** (SDL dummy drivers set below + by conftest's
autouse fixture) and require **no physical controller**. They drive
:class:`AppStateMachine` with a scripted fake controller and a fake matrix and
assert the documented transition table, then exercise :class:`DemoCarousel`
including its ``should_stop()`` / menu-request interruption.

We deliberately call the per-mode handlers (``_run_idle`` / ``_run_menu`` /
``_run_game``) and the carousel directly rather than spinning the real
background-thread loop, so transitions are deterministic and fast. The
background input thread itself (START -> request_stop) is covered by a separate,
event-scripted test.
"""

import os
import threading
import time

import pytest

# Ensure dummy SDL drivers even if this module is imported directly.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import src.main as main_module
from src.app_state import (
    AppMode,
    AppStateMachine,
    DemoCarousel,
    MenuResult,
    MenuResultKind,
    PlaceholderMenu,
    PLAYABLE_GAMES,
)
from src.display import _shared
from src.input import Button, EventType, InputEvent


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeMatrix:
    """Minimal matrix stand-in: records SetImage / Clear / brightness."""

    def __init__(self):
        self.images = []
        self.cleared = 0
        self.brightness = 80

    def SetImage(self, image, *a, **kw):
        self.images.append(image)

    def Clear(self):
        self.cleared += 1


class FakeController:
    """Scripted controller.

    ``event_script`` is a list of "batches"; each call to :meth:`poll_events`
    pops and returns the next batch (then ``[]`` forever). ``held`` is the set of
    currently-pressed logical buttons (drives ``is_pressed`` and thus
    ``wants_quit``). ``quitting`` backs :meth:`is_quitting`.
    """

    def __init__(self, event_script=None, held=None, quitting=False,
                 start_hold=0.0):
        self._script = list(event_script or [])
        self._held = set(held or set())
        self._quitting = quitting
        self._start_hold = start_hold
        self.poll_count = 0
        self.closed = False

    def poll_events(self):
        self.poll_count += 1
        if self._script:
            return self._script.pop(0)
        return []

    def is_pressed(self, button):
        return button in self._held

    def is_connected(self):
        return True

    def is_quitting(self):
        return self._quitting

    def start_hold_seconds(self):
        return self._start_hold

    def close(self):
        self.closed = True


def _press(button):
    """A one-batch event script entry: a single PRESSED event."""
    return [InputEvent(button, EventType.PRESSED, 0.0)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clear_shared_stop():
    """Reset the global _shared stop flag around every test."""
    _shared.clear_stop()
    yield
    _shared.clear_stop()


@pytest.fixture
def config():
    return {
        "display_duration": 30,
        "sequence": [
            {"name": "fire", "type": "effect", "enabled": True},
            {"name": "snake", "type": "game", "enabled": True},
            {"name": "plasma", "type": "effect", "enabled": False},
        ],
    }


def make_sm(controller, config, menu=None):
    """Build an AppStateMachine with fakes and a fresh shutdown event."""
    return AppStateMachine(
        FakeMatrix(), controller, config,
        shutdown_event=threading.Event(),
        menu=menu,
    )


# ---------------------------------------------------------------------------
# MenuResult / PlaceholderMenu
# ---------------------------------------------------------------------------
class TestMenuSeam:
    def test_menuresult_constructors(self):
        assert MenuResult.resume().kind is MenuResultKind.RESUME
        assert MenuResult.launch_game("snake").payload == "snake"
        assert MenuResult.open_settings().kind is MenuResultKind.OPEN_SETTINGS
        assert MenuResult.quit().kind is MenuResultKind.QUIT

    def test_placeholder_first_playable_from_config(self, config):
        menu = PlaceholderMenu(config)
        # snake is the first playable in the configured sequence.
        assert menu._first_playable() == "snake"
        assert menu._first_playable() in PLAYABLE_GAMES

    def test_placeholder_default_playable_when_none_configured(self):
        menu = PlaceholderMenu({"sequence": []})
        assert menu._first_playable() == "snake"

    def test_placeholder_a_launches_game(self, config):
        menu = PlaceholderMenu(config, fps=0)  # no sleep
        ctrl = FakeController(event_script=[_press(Button.A)])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.LAUNCH_GAME
        assert result.payload == "snake"

    def test_placeholder_b_resumes(self, config):
        menu = PlaceholderMenu(config, fps=0)
        ctrl = FakeController(event_script=[_press(Button.B)])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME

    def test_placeholder_quit_window_close(self, config):
        menu = PlaceholderMenu(config, fps=0)
        ctrl = FakeController(quitting=True)
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.QUIT

    def test_placeholder_should_stop_resumes(self, config):
        menu = PlaceholderMenu(config, fps=0)
        ctrl = FakeController()
        _shared.request_stop()
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------
class TestTransitions:
    def test_idle_to_menu_on_start(self, config):
        """START during IDLE -> MENU (simulating the input thread's flag)."""
        ctrl = FakeController()
        sm = make_sm(ctrl, config)
        assert sm.mode is AppMode.IDLE

        # Simulate the background input thread having seen START: it sets the
        # menu-requested flag + request_stop(). Stub the carousel so run_cycle
        # returns immediately (as it would once request_stop fires).
        sm._carousel.run_cycle = lambda: None
        sm._menu_requested.set()
        _shared.request_stop()

        sm._run_idle()
        assert sm.mode is AppMode.MENU
        # Flag consumed and stop cleared for the menu/next feature.
        assert not sm._menu_requested.is_set()
        assert not _shared.should_stop()

    def test_idle_stays_idle_without_request(self, config):
        ctrl = FakeController()
        sm = make_sm(ctrl, config)
        sm._carousel.run_cycle = lambda: None
        sm._run_idle()
        assert sm.mode is AppMode.IDLE

    def test_menu_to_in_game_on_launch(self, config):
        """A on a playable game -> IN_GAME (placeholder picks first playable)."""
        ctrl = FakeController(event_script=[_press(Button.A)])
        sm = make_sm(ctrl, config, menu=PlaceholderMenu(config, fps=0))
        sm.mode = AppMode.MENU
        sm._run_menu()
        assert sm.mode is AppMode.IN_GAME
        assert sm._pending_game == "snake"

    def test_menu_to_idle_on_resume(self, config):
        """B / Resume -> IDLE."""
        ctrl = FakeController(event_script=[_press(Button.B)])
        sm = make_sm(ctrl, config, menu=PlaceholderMenu(config, fps=0))
        sm.mode = AppMode.MENU
        sm._run_menu()
        assert sm.mode is AppMode.IDLE

    def test_menu_open_settings_stays_in_menu(self, config):
        """OPEN_SETTINGS is deferred to Phase 3 -> stay in MENU (seam exists)."""
        class SettingsMenu:
            def run(self, matrix, controller):
                return MenuResult.open_settings()

        ctrl = FakeController()
        sm = make_sm(ctrl, config, menu=SettingsMenu())
        sm.mode = AppMode.MENU
        sm._run_menu()
        assert sm.mode is AppMode.MENU

    def test_menu_quit_sets_shutdown(self, config):
        class QuitMenu:
            def run(self, matrix, controller):
                return MenuResult.quit()

        ctrl = FakeController()
        sm = make_sm(ctrl, config, menu=QuitMenu())
        sm.mode = AppMode.MENU
        sm._run_menu()
        assert sm._shutdown.is_set()

    def test_in_game_returns_to_menu(self, config, monkeypatch):
        """A game run() that returns (game over / quit) -> MENU."""
        launched = {}

        def fake_run_feature(name, matrix, duration, controller=None):
            launched["name"] = name
            launched["controller"] = controller
            return True  # game returns immediately

        monkeypatch.setattr(main_module, "run_feature", fake_run_feature)

        ctrl = FakeController()
        sm = make_sm(ctrl, config)
        sm.mode = AppMode.IN_GAME
        sm._pending_game = "snake"
        sm._run_game()

        assert sm.mode is AppMode.MENU
        assert launched["name"] == "snake"
        # The controller is forwarded so the game runs interactively.
        assert launched["controller"] is ctrl

    def test_in_game_no_pending_game_returns_to_menu(self, config):
        ctrl = FakeController()
        sm = make_sm(ctrl, config)
        sm.mode = AppMode.IN_GAME
        sm._pending_game = None
        sm._run_game()
        assert sm.mode is AppMode.MENU

    def test_in_game_crash_returns_to_menu(self, config, monkeypatch):
        def boom(name, matrix, duration, controller=None):
            raise RuntimeError("game exploded")

        monkeypatch.setattr(main_module, "run_feature", boom)
        ctrl = FakeController()
        sm = make_sm(ctrl, config)
        sm.mode = AppMode.IN_GAME
        sm._pending_game = "snake"
        sm._run_game()  # must not raise
        assert sm.mode is AppMode.MENU


# ---------------------------------------------------------------------------
# Top-level run() loop: QUIT shutdown
# ---------------------------------------------------------------------------
class TestRunLoop:
    def test_quit_via_is_quitting_shuts_down(self, config):
        """controller.is_quitting() -> clean shutdown, loop exits."""
        ctrl = FakeController(quitting=True)
        sm = make_sm(ctrl, config)
        # run() should observe is_quitting() and exit promptly.
        t = threading.Thread(target=sm.run)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "run() did not exit on is_quitting()"
        assert sm._shutdown.is_set()

    def test_run_exits_when_shutdown_preset(self, config):
        ctrl = FakeController()
        sm = make_sm(ctrl, config)
        sm._shutdown.set()
        t = threading.Thread(target=sm.run)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive()

    def test_input_thread_requests_menu_on_start(self, config):
        """Background input thread sets menu flag + request_stop on START."""
        ctrl = FakeController(event_script=[_press(Button.START)])
        sm = make_sm(ctrl, config)
        sm.mode = AppMode.IDLE
        # Run a single iteration of the watcher body by calling it briefly.
        sm._start_input_thread()
        # Give the daemon thread a moment to consume the scripted START.
        deadline = time.time() + 2.0
        while time.time() < deadline and not sm._menu_requested.is_set():
            time.sleep(0.01)
        sm._shutdown.set()
        assert sm._menu_requested.is_set()
        assert _shared.should_stop()


# ---------------------------------------------------------------------------
# DemoCarousel
# ---------------------------------------------------------------------------
class TestDemoCarousel:
    def test_cycles_enabled_features(self, config, monkeypatch):
        """run_cycle runs each enabled feature exactly once (in order)."""
        ran = []

        def fake_run_feature(name, matrix, duration, controller=None):
            ran.append(name)
            return True

        monkeypatch.setattr(main_module, "run_feature", fake_run_feature)
        # Avoid real network + schedule + config-reload side effects.
        monkeypatch.setattr(main_module, "_check_internet", lambda *a, **k: True)
        monkeypatch.setattr(main_module, "_check_schedule", lambda *a, **k: None)
        monkeypatch.setattr(main_module, "load_config", lambda: config)

        shutdown = threading.Event()
        carousel = DemoCarousel(FakeMatrix(), config, shutdown)
        carousel.run_cycle()

        # Only the two enabled features (fire, snake) run; plasma is disabled.
        assert ran == ["fire", "snake"]

    def test_skips_internet_features_when_offline(self, monkeypatch):
        ran = []

        def fake_run_feature(name, matrix, duration, controller=None):
            ran.append(name)
            return True

        cfg = {
            "display_duration": 10,
            "sequence": [
                {"name": "fire", "enabled": True},
                {"name": "weather", "enabled": True},  # internet feature
            ],
        }
        monkeypatch.setattr(main_module, "run_feature", fake_run_feature)
        monkeypatch.setattr(main_module, "_check_internet", lambda *a, **k: False)
        monkeypatch.setattr(main_module, "_check_schedule", lambda *a, **k: None)
        monkeypatch.setattr(main_module, "load_config", lambda: cfg)

        carousel = DemoCarousel(FakeMatrix(), cfg, threading.Event())
        carousel.run_cycle()

        assert "fire" in ran
        assert "weather" not in ran  # skipped: no internet

    def test_menu_request_interrupts_carousel(self, config, monkeypatch):
        """A START press (menu_requested -> True) breaks the carousel mid-cycle.

        We simulate the input thread by having the first fake feature set the
        menu-requested flag (as request_stop() would cause the real feature to
        return). The carousel must NOT run the second feature.
        """
        ran = []
        requested = {"flag": False}

        def fake_run_feature(name, matrix, duration, controller=None):
            ran.append(name)
            # Simulate: while 'fire' was running the user pressed START.
            requested["flag"] = True
            return True

        monkeypatch.setattr(main_module, "run_feature", fake_run_feature)
        monkeypatch.setattr(main_module, "_check_internet", lambda *a, **k: True)
        monkeypatch.setattr(main_module, "_check_schedule", lambda *a, **k: None)
        monkeypatch.setattr(main_module, "load_config", lambda: config)

        carousel = DemoCarousel(
            FakeMatrix(), config, threading.Event(),
            menu_requested=lambda: requested["flag"],
        )
        carousel.run_cycle()

        # Interrupted after the first feature; snake never runs this cycle.
        assert ran == ["fire"]

    def test_shutdown_interrupts_carousel(self, config, monkeypatch):
        ran = []
        shutdown = threading.Event()

        def fake_run_feature(name, matrix, duration, controller=None):
            ran.append(name)
            shutdown.set()  # process shutdown mid-cycle
            return True

        monkeypatch.setattr(main_module, "run_feature", fake_run_feature)
        monkeypatch.setattr(main_module, "_check_internet", lambda *a, **k: True)
        monkeypatch.setattr(main_module, "_check_schedule", lambda *a, **k: None)
        monkeypatch.setattr(main_module, "load_config", lambda: config)

        carousel = DemoCarousel(FakeMatrix(), config, shutdown)
        carousel.run_cycle()
        assert ran == ["fire"]

    def test_update_config_refreshes_enabled(self, config):
        carousel = DemoCarousel(FakeMatrix(), config, threading.Event())
        assert [f["name"] for f in carousel.enabled_features] == ["fire", "snake"]
        carousel.update_config({
            "display_duration": 99,
            "sequence": [{"name": "plasma", "enabled": True}],
        })
        assert carousel.duration == 99
        assert [f["name"] for f in carousel.enabled_features] == ["plasma"]

    def test_schedule_brightness_applied_between_cycles(self, monkeypatch):
        """A schedule override sets matrix brightness after the cycle."""
        cfg = {"display_duration": 10, "sequence": [{"name": "fire", "enabled": True}]}
        monkeypatch.setattr(main_module, "run_feature", lambda *a, **k: True)
        monkeypatch.setattr(main_module, "_check_internet", lambda *a, **k: True)
        monkeypatch.setattr(main_module, "load_config", lambda: cfg)
        monkeypatch.setattr(
            main_module, "_check_schedule",
            lambda: {"brightness": 15, "allowed_features": []},
        )

        matrix = FakeMatrix()
        carousel = DemoCarousel(matrix, cfg, threading.Event())
        carousel.run_cycle()
        assert matrix.brightness == 15