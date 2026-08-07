"""Tests for the Lock Demo feature (pin one demo for a chosen time).

Menu side: a LOCK DEMO entry on the main menu opens the feature list; picking
a feature pushes a duration menu; picking a duration returns
``MenuResult.launch_locked_demo(name, seconds)``.

State-machine side: ``LAUNCH_LOCKED_DEMO`` enters ``AppMode.LOCKED``, which
relaunches the demo until the deadline, throttles instant returns so a
crashing demo cannot hot-spin for hours, and exits early only for START
(-> MENU) or shutdown. On natural expiry it resumes the carousel (IDLE).

The escape hatch matters most: the input watcher must poll the controller in
LOCKED mode exactly as it does in IDLE, because the locked demo runs with
``controller=None`` and nothing else is listening.
"""

import os
import threading
import time

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from src.app_state import (
    AppMode,
    AppStateMachine,
    MenuResult,
    MenuResultKind,
)
from src.display import _shared
from src.feature_registry import FEATURE_MODULES
from src.input import Button, EventType, InputEvent
from src.menu import MenuSystem
from src.menu.menu_data import (
    LOCK_DURATIONS,
    MENU_LOCK,
    MENU_LOCK_DURATION,
    ItemAction,
    build_duration_menu,
    build_lock_menu,
    build_main_menu,
    build_menu_registry,
)


# ---------------------------------------------------------------------------
# Fakes (same pattern as test_menu.py / test_app_state.py)
# ---------------------------------------------------------------------------
class FakeMatrix:
    def __init__(self):
        self.images = []
        self.cleared = 0
        self.brightness = 80

    def SetImage(self, image, *a, **kw):
        self.images.append(image)

    def Clear(self):
        self.cleared += 1


class FakeController:
    def __init__(self, event_script=None, held=None, quitting=False):
        self._script = list(event_script or [])
        self._held = set(held or set())
        self._quitting = quitting
        self.poll_count = 0

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
        return 0.0

    def close(self):
        pass


def _press(button):
    return [InputEvent(button, EventType.PRESSED, 0.0)]


@pytest.fixture(autouse=True)
def _clear_shared_stop():
    _shared.clear_stop()
    yield
    _shared.clear_stop()


@pytest.fixture
def config():
    return {
        "display_duration": 30,
        "matrix_hardware": {"brightness": 50, "rows": 64, "cols": 64},
        "sequence": [{"name": "snake", "type": "game", "enabled": True}],
    }


def make_sm(controller, config, menu=None):
    return AppStateMachine(
        FakeMatrix(), controller, config,
        shutdown_event=threading.Event(),
        menu=menu,
    )


# ---------------------------------------------------------------------------
# Menu data
# ---------------------------------------------------------------------------
class TestLockMenuData:
    def test_main_menu_has_lock_entry_after_demos(self):
        menu = build_main_menu()
        labels = [i.label for i in menu.items]
        assert "LOCK DEMO" in labels
        assert labels.index("LOCK DEMO") == labels.index("DEMOS") + 1
        item = menu.items[labels.index("LOCK DEMO")]
        assert item.action is ItemAction.OPEN_SUBMENU
        assert item.payload == MENU_LOCK

    def test_lock_menu_mirrors_the_feature_registry(self):
        menu = build_lock_menu()
        names = [i.payload for i in menu.items if i.action is ItemAction.PICK_LOCK_DEMO]
        assert names == sorted(FEATURE_MODULES.keys())
        assert menu.items[-1].action is ItemAction.BACK

    def test_lock_menu_is_registered(self):
        registry = build_menu_registry()
        assert MENU_LOCK in registry
        assert registry[MENU_LOCK].id == MENU_LOCK

    def test_duration_menu_payloads_pack_name_and_seconds(self):
        menu = build_duration_menu("fire", "FIRE")
        assert menu.id == MENU_LOCK_DURATION
        assert menu.title == "FIRE"
        launch = [i for i in menu.items if i.action is ItemAction.LAUNCH_LOCKED]
        assert len(launch) == len(LOCK_DURATIONS)
        for item, (label, secs) in zip(launch, LOCK_DURATIONS):
            assert item.label == label
            assert item.payload == "fire:%d" % secs
        assert menu.items[-1].action is ItemAction.BACK

    def test_durations_are_positive_and_ascending(self):
        secs = [s for _, s in LOCK_DURATIONS]
        assert all(s > 0 for s in secs)
        assert secs == sorted(secs)
        assert secs[0] >= 60          # nothing uselessly short
        assert secs[-1] <= 24 * 3600  # nothing effectively infinite

    def test_duration_labels_fit_the_panel(self):
        # 64px wide / 6px per 5x7 glyph, minus the selection cursor -> 9 chars.
        for label, _ in LOCK_DURATIONS:
            assert len(label) <= 9

    def test_duration_menu_title_is_truncated(self):
        menu = build_duration_menu("x", "A" * 30)
        assert len(menu.title) <= 10


# ---------------------------------------------------------------------------
# MenuResult
# ---------------------------------------------------------------------------
class TestLockedMenuResult:
    def test_launch_locked_demo_constructor(self):
        r = MenuResult.launch_locked_demo("fire", 900)
        assert r.kind is MenuResultKind.LAUNCH_LOCKED_DEMO
        assert r.payload == "fire"
        assert r.duration == 900

    def test_other_results_have_no_duration(self):
        assert MenuResult.launch_demo("fire").duration is None
        assert MenuResult.resume().duration is None


# ---------------------------------------------------------------------------
# Menu engine flow
# ---------------------------------------------------------------------------
def _make_menu(config):
    return MenuSystem(config, fps=0)


class TestLockMenuFlow:
    def test_full_flow_returns_launch_locked(self, config):
        """Main -> LOCK DEMO -> first feature -> first duration -> result."""
        menu = _make_menu(config)
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),   # -> DEMOS
            _press(Button.DOWN),   # -> LOCK DEMO
            _press(Button.A),      # open lock submenu
            _press(Button.A),      # pick first feature -> duration menu pushed
            _press(Button.A),      # pick first duration (5 MIN)
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.LAUNCH_LOCKED_DEMO
        assert result.payload == sorted(FEATURE_MODULES.keys())[0]
        assert result.duration == LOCK_DURATIONS[0][1]

    def test_second_duration_row_maps_to_second_duration(self, config):
        menu = _make_menu(config)
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),   # -> DEMOS
            _press(Button.DOWN),   # -> LOCK DEMO
            _press(Button.A),      # open lock submenu
            _press(Button.A),      # pick first feature
            _press(Button.DOWN),   # -> 10 MIN
            _press(Button.A),
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.duration == LOCK_DURATIONS[1][1]

    def test_b_from_duration_menu_backs_out_to_feature_list(self, config):
        """B in the duration menu must not launch anything -- it pops back to
        the lock feature list, and START then resumes normally."""
        menu = _make_menu(config)
        ctrl = FakeController(event_script=[
            _press(Button.DOWN),   # -> DEMOS
            _press(Button.DOWN),   # -> LOCK DEMO
            _press(Button.A),      # open lock submenu
            _press(Button.A),      # pick feature -> duration menu
            _press(Button.B),      # back out to the feature list
            _press(Button.START),  # resume to idle
        ])
        result = menu.run(FakeMatrix(), ctrl)
        assert result.kind is MenuResultKind.RESUME

    def test_bad_locked_payload_is_ignored(self, config):
        """A malformed LAUNCH_LOCKED payload must not crash or launch."""
        from src.menu.menu_data import Menu, MenuItem
        menu = _make_menu(config)
        menu._stack = [[Menu("x", "X", [
            MenuItem("BAD", ItemAction.LAUNCH_LOCKED, payload="fire:oops"),
            MenuItem("EMPTY", ItemAction.LAUNCH_LOCKED, payload=":300"),
            MenuItem("NONE", ItemAction.LAUNCH_LOCKED, payload=None),
        ]), 0]]
        for idx in range(3):
            menu._stack[-1][1] = idx
            assert menu._activate(FakeMatrix(), FakeController()) is None


# ---------------------------------------------------------------------------
# State machine: LOCKED mode
# ---------------------------------------------------------------------------
class _LockMenu:
    """Menu stub that immediately requests a locked demo, then resumes."""

    def __init__(self, name="fire", seconds=2):
        self._results = [MenuResult.launch_locked_demo(name, seconds)]

    def run(self, matrix, controller):
        if self._results:
            return self._results.pop(0)
        return MenuResult.resume()


class TestLockedMode:
    def _patch_speed(self, sm):
        sm._LOCK_MIN_CYCLE_SECONDS = 0.0

    def test_menu_result_enters_locked_mode(self, config):
        sm = make_sm(FakeController(), config, menu=_LockMenu("fire", 60))
        sm.mode = AppMode.MENU
        # Stop before actually running the lock: shutdown after menu returns.
        sm._pending_lock = None
        sm._run_menu()
        assert sm.mode is AppMode.LOCKED
        assert sm._pending_lock == ("fire", 60)

    def test_locked_relaunches_until_deadline_then_idles(self, config, monkeypatch):
        import src.main as main_module
        calls = []

        def fake_run_feature(name, matrix, duration, controller=None):
            calls.append((name, duration, controller))
            time.sleep(0.05)   # each "demo" exits early after 50ms

        monkeypatch.setattr(main_module, "run_feature", fake_run_feature)
        sm = make_sm(FakeController(), config)
        self._patch_speed(sm)
        sm._pending_lock = ("fire", 0.4)
        sm.mode = AppMode.LOCKED
        sm._run_locked()

        assert sm.mode is AppMode.IDLE
        assert len(calls) >= 3, "demo was not relaunched to hold the lock"
        assert all(c[0] == "fire" for c in calls)
        assert all(c[2] is None for c in calls), "locked demo must not get the controller"
        # Remaining time shrinks monotonically across relaunches.
        durations = [c[1] for c in calls]
        assert all(a >= b for a, b in zip(durations, durations[1:]))

    def test_locked_demo_crash_is_contained_and_throttled(self, config, monkeypatch):
        import src.main as main_module
        calls = []

        def boom(name, matrix, duration, controller=None):
            calls.append(time.monotonic())
            raise RuntimeError("demo exploded")

        monkeypatch.setattr(main_module, "run_feature", boom)
        sm = make_sm(FakeController(), config)
        sm._LOCK_MIN_CYCLE_SECONDS = 0.1
        sm._pending_lock = ("fire", 0.35)
        sm.mode = AppMode.LOCKED
        sm._run_locked()   # must not raise

        assert sm.mode is AppMode.IDLE
        # Throttle: ~0.35s / 0.1s floor -> a handful of attempts, not thousands.
        assert 1 <= len(calls) <= 6, f"hot spin: {len(calls)} relaunches"

    def test_menu_request_breaks_the_lock(self, config, monkeypatch):
        import src.main as main_module
        sm = make_sm(FakeController(), config)
        self._patch_speed(sm)

        def fake_run_feature(name, matrix, duration, controller=None):
            # Simulate the input thread: START arrives mid-demo.
            sm._menu_requested.set()
            _shared.request_stop()

        monkeypatch.setattr(main_module, "run_feature", fake_run_feature)
        sm._pending_lock = ("fire", 60.0)
        sm.mode = AppMode.LOCKED
        start = time.monotonic()
        sm._run_locked()
        elapsed = time.monotonic() - start

        assert sm.mode is AppMode.MENU
        assert elapsed < 5.0, "lock did not break promptly"
        assert not sm._menu_requested.is_set(), "request must be consumed"
        assert not _shared.should_stop(), "stop flag must be cleared for the menu"

    def test_shutdown_breaks_the_lock(self, config, monkeypatch):
        import src.main as main_module
        sm = make_sm(FakeController(), config)
        self._patch_speed(sm)

        def fake_run_feature(name, matrix, duration, controller=None):
            sm._shutdown.set()

        monkeypatch.setattr(main_module, "run_feature", fake_run_feature)
        sm._pending_lock = ("fire", 60.0)
        sm.mode = AppMode.LOCKED
        start = time.monotonic()
        sm._run_locked()
        assert time.monotonic() - start < 5.0

    def test_empty_pending_lock_falls_back_to_idle(self, config):
        sm = make_sm(FakeController(), config)
        for pending in (None, ("", 60), ("fire", 0), ("fire", -5)):
            sm._pending_lock = pending
            sm.mode = AppMode.LOCKED
            sm._run_locked()
            assert sm.mode is AppMode.IDLE

    def test_run_dispatches_locked_mode(self, config, monkeypatch):
        """The top-level loop must actually route LOCKED to _run_locked."""
        import src.main as main_module
        monkeypatch.setattr(main_module, "run_feature",
                            lambda *a, **k: None)
        sm = make_sm(FakeController(), config)
        self._patch_speed(sm)
        sm._pending_lock = ("fire", 0.1)
        sm.mode = AppMode.LOCKED

        # After the lock expires the machine goes IDLE; shut down right there
        # so run() exits instead of starting the carousel.
        original = AppStateMachine._run_idle

        def stop_idle(self):
            self._shutdown.set()

        monkeypatch.setattr(AppStateMachine, "_run_idle", stop_idle)
        t = threading.Thread(target=sm.run, daemon=True)
        t.start()
        t.join(timeout=5.0)
        assert not t.is_alive(), "run() never exited"
        assert sm.mode is AppMode.IDLE

    def test_locked_is_not_safe_for_auto_restart(self, config):
        """The updater must not restart the service mid-lock."""
        sm = make_sm(FakeController(), config)
        sm.mode = AppMode.LOCKED
        assert sm._safe_to_restart() is False

    def test_input_watcher_polls_in_locked_mode(self, config):
        """START during LOCKED must request the menu -- the escape hatch."""
        ctrl = FakeController(event_script=[_press(Button.START)])
        sm = make_sm(ctrl, config)
        sm.mode = AppMode.LOCKED
        sm._last_idle_entry_time = time.monotonic() - 60  # past the debounce
        sm._input_poll_interval = 0.01
        sm._start_input_thread()
        try:
            deadline = time.time() + 3.0
            while time.time() < deadline and not sm._menu_requested.is_set():
                time.sleep(0.02)
            assert sm._menu_requested.is_set(), "START ignored during LOCKED"
            assert _shared.should_stop(), "stop was not requested"
        finally:
            sm._shutdown.set()

    def test_input_watcher_still_ignores_menu_mode(self, config):
        """Foreground owns the controller in MENU: watcher must not poll."""
        ctrl = FakeController(event_script=[_press(Button.START)])
        sm = make_sm(ctrl, config)
        sm.mode = AppMode.MENU
        sm._input_poll_interval = 0.01
        sm._start_input_thread()
        try:
            time.sleep(0.3)
            assert ctrl.poll_count == 0, "watcher polled while menu owns input"
            assert not sm._menu_requested.is_set()
        finally:
            sm._shutdown.set()
