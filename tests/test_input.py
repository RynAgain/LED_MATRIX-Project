"""
Unit tests for the input abstraction layer (src/input/).

These tests run **without a physical controller** and **headless**. They use a
lightweight fake pygame module (injected via the ``Controller._pygame`` seam)
plus an injectable clock so timing-based behavior (key-repeat, hold-to-quit) is
deterministic. No real SDL/joystick is required.

Mirrors the project's existing test conventions (see tests/conftest.py and
tests/test_simulator.py): SDL dummy drivers are set by conftest's autouse
fixture, config files are snapshotted/restored, and we import from src.* with
the project root already on sys.path.
"""

import os
import json

import pytest

# Ensure dummy SDL drivers even if this module is imported directly.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from src.input import (
    Button,
    ButtonMapping,
    Controller,
    EventType,
    InputEvent,
    load_mapping,
    save_mapping,
    default_mapping,
    wants_quit,
)
from src.input.controller import START_HOLD_QUIT_SECONDS
from src.input import keyboard_fallback


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeEvent:
    """Minimal pygame-event stand-in with a ``type`` and arbitrary attrs."""

    def __init__(self, type, **attrs):
        self.type = type
        for k, v in attrs.items():
            setattr(self, k, v)


class FakeJoystick:
    """Stand-in for pygame.joystick.Joystick(0)."""

    def __init__(self):
        self._hat = (0, 0)
        self._axes = {0: 0.0, 1: 0.0}
        self._name = "FAKE PAD"
        self.rumble_calls = []
        self.quit_called = False

    def init(self):
        pass

    def quit(self):
        self.quit_called = True

    def get_name(self):
        return self._name

    def get_numhats(self):
        return 1

    def get_hat(self, idx):
        return self._hat

    def get_numaxes(self):
        return len(self._axes)

    def get_axis(self, idx):
        return self._axes.get(idx, 0.0)

    def rumble(self, low, high, duration_ms):
        self.rumble_calls.append((low, high, duration_ms))
        return True


class FakeJoystickModule:
    def __init__(self, count=0, joystick=None):
        self._count = count
        self._joystick = joystick
        self._init = True

    def get_init(self):
        return self._init

    def init(self):
        self._init = True

    def quit(self):
        self._init = False

    def get_count(self):
        return self._count

    def Joystick(self, idx):
        return self._joystick


class FakeEventModule:
    def __init__(self):
        self._queue = []

    def post(self, event):
        self._queue.append(event)

    def get(self):
        q = self._queue
        self._queue = []
        return q


class FakePygame:
    """A fake ``pygame`` module exposing only what the Controller touches.

    Event-type constants are arbitrary unique integers; tests build FakeEvents
    using these same constants so the controller's ``getattr(pg, "JOYBUTTONDOWN")``
    dispatch matches.
    """

    QUIT = 256
    KEYDOWN = 768
    KEYUP = 769
    JOYBUTTONDOWN = 1539
    JOYBUTTONUP = 1540
    JOYAXISMOTION = 1536
    JOYDEVICEADDED = 1541
    JOYDEVICEREMOVED = 1542

    # A couple of key constants used by the keyboard fallback resolution.
    K_UP = 1073741906
    K_DOWN = 1073741905
    K_LEFT = 1073741904
    K_RIGHT = 1073741903
    K_w = 119
    K_s = 115
    K_a = 97
    K_d = 100
    K_z = 122
    K_x = 120
    K_RETURN = 13
    K_KP_ENTER = 1073741912
    K_TAB = 9
    K_RSHIFT = 1073742053

    def __init__(self, joystick_count=0, joystick=None):
        self.event = FakeEventModule()
        self.joystick = FakeJoystickModule(joystick_count, joystick)
        self._inited = True

    def get_init(self):
        return self._inited

    def init(self):
        self._inited = True


class FakeClock:
    """Deterministic injectable monotonic clock."""

    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_controller(pygame_obj=None, clock=None, mapping=None, **kw):
    """Construct a Controller and forcibly swap in a fake pygame.

    The real ``_init_pygame`` runs (and may import the real pygame), then we
    overwrite ``_pygame`` / joystick state with the fake so polling is fully
    controlled. The keyboard fallback translator is also rebuilt against the
    fake's key constants.
    """
    clock = clock or FakeClock()
    ctrl = Controller(
        mapping=mapping or default_mapping(),
        enable_keyboard_fallback=True,
        clock=clock,
        **kw,
    )
    if pygame_obj is not None:
        ctrl._pygame = pygame_obj
        # Rebuild keyboard translator against the fake's key constants.
        key_map = {}
        for const_name, button in keyboard_fallback.DEFAULT_KEY_MAP.items():
            code = getattr(pygame_obj, const_name, None)
            if code is not None:
                key_map[int(code)] = button
        ctrl._kbd = keyboard_fallback.KeyboardFallback(key_map)
        # Hook up joystick if the fake provides one already attached.
        if pygame_obj.joystick.get_count() > 0:
            ctrl._joystick = pygame_obj.joystick.Joystick(0)
            ctrl._connected = True
        else:
            ctrl._joystick = None
            ctrl._connected = False
    return ctrl, clock


# ---------------------------------------------------------------------------
# ButtonMapping load/save
# ---------------------------------------------------------------------------
class TestButtonMapping:
    def test_default_mapping_has_core_buttons(self):
        m = default_mapping()
        assert Button.A in m.buttons.values()
        assert Button.B in m.buttons.values()
        assert Button.START in m.buttons.values()
        assert Button.SELECT in m.buttons.values()

    def test_roundtrip_to_from_dict(self):
        m = default_mapping()
        m2 = ButtonMapping.from_dict(m.to_dict())
        assert m2.buttons == m.buttons
        assert m2.axis_x == m.axis_x
        assert m2.axis_y == m.axis_y
        assert m2.deadzone == m.deadzone

    def test_load_from_temp_file(self, tmp_path):
        p = tmp_path / "controller.json"
        data = {
            "buttons": {"2": "A", "3": "B", "7": "START", "6": "SELECT"},
            "hat_index": 0,
            "axis_x": 4,
            "axis_y": 5,
            "invert_y": True,
            "deadzone": 0.3,
        }
        p.write_text(json.dumps(data), encoding="utf-8")
        m = load_mapping(str(p))
        assert m.buttons == {2: Button.A, 3: Button.B, 7: Button.START, 6: Button.SELECT}
        assert m.axis_x == 4
        assert m.axis_y == 5
        assert m.invert_y is True
        assert m.deadzone == 0.3

    def test_load_missing_file_falls_back_to_default(self, tmp_path):
        m = load_mapping(str(tmp_path / "does_not_exist.json"))
        assert m.buttons == default_mapping().buttons

    def test_load_invalid_json_falls_back_to_default(self, tmp_path):
        p = tmp_path / "controller.json"
        p.write_text("{ this is not valid json", encoding="utf-8")
        m = load_mapping(str(p))
        assert m.buttons == default_mapping().buttons

    def test_load_partial_invalid_entries_skipped(self, tmp_path):
        p = tmp_path / "controller.json"
        data = {"buttons": {"0": "A", "1": "NOPE", "9": "START"}}
        p.write_text(json.dumps(data), encoding="utf-8")
        m = load_mapping(str(p))
        # Bad entry dropped; valid ones kept.
        assert m.buttons[0] == Button.A
        assert m.buttons[9] == Button.START
        assert 1 not in m.buttons

    def test_save_is_atomic_and_reloadable(self, tmp_path):
        p = tmp_path / "controller.json"
        m = default_mapping()
        assert save_mapping(m, str(p)) is True
        assert p.exists()
        reloaded = load_mapping(str(p))
        assert reloaded.buttons == m.buttons


# ---------------------------------------------------------------------------
# poll_events: PRESSED / RELEASED edges
# ---------------------------------------------------------------------------
class TestPressRelease:
    def test_button_press_then_release_via_keyboard(self):
        pg = FakePygame()
        ctrl, clock = make_controller(pygame_obj=pg)

        # KEYDOWN Z -> Button.A pressed.
        pg.event.post(FakeEvent(pg.KEYDOWN, key=pg.K_z))
        events = ctrl.poll_events()
        assert InputEvent(Button.A, EventType.PRESSED, clock.t) in events
        assert ctrl.is_pressed(Button.A)

        # No new events while held and nothing happens.
        clock.advance(0.01)
        events = ctrl.poll_events()
        assert all(e.type != EventType.RELEASED for e in events)
        assert ctrl.is_pressed(Button.A)

        # KEYUP Z -> Button.A released.
        clock.advance(0.01)
        pg.event.post(FakeEvent(pg.KEYUP, key=pg.K_z))
        events = ctrl.poll_events()
        assert any(
            e.button == Button.A and e.type == EventType.RELEASED for e in events
        )
        assert not ctrl.is_pressed(Button.A)

    def test_joystick_button_press_release(self):
        joy = FakeJoystick()
        pg = FakePygame(joystick_count=1, joystick=joy)
        # Default mapping: button 0 -> A.
        ctrl, clock = make_controller(pygame_obj=pg)

        pg.event.post(FakeEvent(pg.JOYBUTTONDOWN, button=0))
        events = ctrl.poll_events()
        assert any(e.button == Button.A and e.type == EventType.PRESSED for e in events)

        clock.advance(0.01)
        pg.event.post(FakeEvent(pg.JOYBUTTONUP, button=0))
        events = ctrl.poll_events()
        assert any(e.button == Button.A and e.type == EventType.RELEASED for e in events)


# ---------------------------------------------------------------------------
# poll_events: REPEAT timing
# ---------------------------------------------------------------------------
class TestRepeat:
    def test_repeat_fires_after_delay_then_at_interval(self):
        pg = FakePygame()
        ctrl, clock = make_controller(
            pygame_obj=pg, repeat_delay=0.35, repeat_interval=0.12
        )

        # Hold UP (keyboard arrow).
        pg.event.post(FakeEvent(pg.KEYDOWN, key=pg.K_UP))
        events = ctrl.poll_events()
        assert any(e.button == Button.UP and e.type == EventType.PRESSED for e in events)
        assert all(e.type != EventType.REPEAT for e in events)

        # Before repeat_delay: no REPEAT yet.
        clock.advance(0.20)
        events = ctrl.poll_events()
        assert all(e.type != EventType.REPEAT for e in events)

        # Past repeat_delay (0.35): first REPEAT.
        clock.advance(0.20)  # total 0.40
        events = ctrl.poll_events()
        assert any(e.button == Button.UP and e.type == EventType.REPEAT for e in events)

        # After one interval (0.12): another REPEAT.
        clock.advance(0.12)
        events = ctrl.poll_events()
        assert any(e.button == Button.UP and e.type == EventType.REPEAT for e in events)

    def test_release_stops_repeat(self):
        pg = FakePygame()
        ctrl, clock = make_controller(
            pygame_obj=pg, repeat_delay=0.35, repeat_interval=0.12
        )
        pg.event.post(FakeEvent(pg.KEYDOWN, key=pg.K_UP))
        ctrl.poll_events()
        clock.advance(0.40)
        ctrl.poll_events()  # first repeat
        # Release.
        pg.event.post(FakeEvent(pg.KEYUP, key=pg.K_UP))
        clock.advance(0.12)
        events = ctrl.poll_events()
        assert any(e.button == Button.UP and e.type == EventType.RELEASED for e in events)
        # No further repeat after release.
        clock.advance(0.50)
        events = ctrl.poll_events()
        assert all(e.type != EventType.REPEAT for e in events)


# ---------------------------------------------------------------------------
# get_direction
# ---------------------------------------------------------------------------
class TestDirection:
    def test_centered_returns_none(self):
        pg = FakePygame()
        ctrl, _ = make_controller(pygame_obj=pg)
        ctrl.poll_events()
        assert ctrl.get_direction() is None

    def test_keyboard_direction_vector(self):
        pg = FakePygame()
        ctrl, _ = make_controller(pygame_obj=pg)
        pg.event.post(FakeEvent(pg.KEYDOWN, key=pg.K_RIGHT))
        ctrl.poll_events()
        assert ctrl.get_direction() == (1, 0)

    def test_analog_axis_direction(self):
        joy = FakeJoystick()
        joy._axes[0] = 0.9  # push right past deadzone
        pg = FakePygame(joystick_count=1, joystick=joy)
        ctrl, _ = make_controller(pygame_obj=pg)
        ctrl.poll_events()
        assert ctrl.get_direction() == (1, 0)
        assert ctrl.is_pressed(Button.RIGHT)

    def test_hat_direction_up(self):
        joy = FakeJoystick()
        joy._hat = (0, 1)  # pygame hat: +1 == up
        pg = FakePygame(joystick_count=1, joystick=joy)
        ctrl, _ = make_controller(pygame_obj=pg)
        ctrl.poll_events()
        assert ctrl.get_direction() == (0, -1)
        assert ctrl.is_pressed(Button.UP)


# ---------------------------------------------------------------------------
# Hot-plug / connection
# ---------------------------------------------------------------------------
class TestConnection:
    def test_no_joystick_at_start_is_disconnected(self):
        pg = FakePygame(joystick_count=0)
        ctrl, _ = make_controller(pygame_obj=pg)
        assert ctrl.is_connected() is False

    def test_device_added_then_removed(self):
        joy = FakeJoystick()
        pg = FakePygame(joystick_count=0)
        ctrl, _ = make_controller(pygame_obj=pg)
        assert ctrl.is_connected() is False

        # Simulate plug-in: make a joystick available and post ADDED.
        pg.joystick._count = 1
        pg.joystick._joystick = joy
        pg.event.post(FakeEvent(pg.JOYDEVICEADDED, device_index=0))
        ctrl.poll_events()
        assert ctrl.is_connected() is True

        # Simulate unplug: post REMOVED.
        pg.event.post(FakeEvent(pg.JOYDEVICEREMOVED, instance_id=0))
        ctrl.poll_events()
        assert ctrl.is_connected() is False

    def test_removed_releases_held_direction(self):
        joy = FakeJoystick()
        joy._axes[0] = 0.9
        pg = FakePygame(joystick_count=1, joystick=joy)
        ctrl, _ = make_controller(pygame_obj=pg)
        ctrl.poll_events()
        assert ctrl.is_pressed(Button.RIGHT)
        # Unplug.
        pg.event.post(FakeEvent(pg.JOYDEVICEREMOVED, instance_id=0))
        events = ctrl.poll_events()
        assert not ctrl.is_pressed(Button.RIGHT)
        assert any(
            e.button == Button.RIGHT and e.type == EventType.RELEASED for e in events
        )


# ---------------------------------------------------------------------------
# wants_quit
# ---------------------------------------------------------------------------
class TestWantsQuit:
    def test_start_plus_select_combo(self):
        pg = FakePygame()
        ctrl, _ = make_controller(pygame_obj=pg)
        # START via Enter, SELECT via Tab.
        pg.event.post(FakeEvent(pg.KEYDOWN, key=pg.K_RETURN))
        pg.event.post(FakeEvent(pg.KEYDOWN, key=pg.K_TAB))
        ctrl.poll_events()
        assert ctrl.is_pressed(Button.START)
        assert ctrl.is_pressed(Button.SELECT)
        assert wants_quit(ctrl) is True

    def test_start_alone_triggers_quit_immediately(self):
        """START pressed alone now returns to menu immediately."""
        pg = FakePygame()
        ctrl, clock = make_controller(pygame_obj=pg)
        pg.event.post(FakeEvent(pg.KEYDOWN, key=pg.K_RETURN))
        ctrl.poll_events()
        assert wants_quit(ctrl) is True

    def test_hold_start_fallback_also_triggers_quit(self):
        """Hold-START still triggers quit (backward compat path)."""
        pg = FakePygame()
        ctrl, clock = make_controller(pygame_obj=pg)
        pg.event.post(FakeEvent(pg.KEYDOWN, key=pg.K_RETURN))
        ctrl.poll_events()
        # START alone already triggers quit immediately now
        assert wants_quit(ctrl) is True
        # Hold past the fallback threshold -- still True (redundant but valid).
        clock.advance(START_HOLD_QUIT_SECONDS + 0.1)
        ctrl.poll_events()  # refresh START-hold timer at new time
        assert wants_quit(ctrl) is True

    def test_releasing_start_resets_hold_timer(self):
        pg = FakePygame()
        ctrl, clock = make_controller(pygame_obj=pg)
        pg.event.post(FakeEvent(pg.KEYDOWN, key=pg.K_RETURN))
        ctrl.poll_events()
        clock.advance(1.0)
        ctrl.poll_events()
        pg.event.post(FakeEvent(pg.KEYUP, key=pg.K_RETURN))
        ctrl.poll_events()
        assert ctrl.start_hold_seconds() == 0.0
        assert wants_quit(ctrl) is False


# ---------------------------------------------------------------------------
# QUIT surfacing + rumble + close
# ---------------------------------------------------------------------------
class TestMisc:
    def test_quit_event_sets_flag(self):
        pg = FakePygame()
        ctrl, _ = make_controller(pygame_obj=pg)
        assert ctrl.is_quitting() is False
        pg.event.post(FakeEvent(pg.QUIT))
        ctrl.poll_events()
        assert ctrl.is_quitting() is True

    def test_rumble_calls_joystick(self):
        joy = FakeJoystick()
        pg = FakePygame(joystick_count=1, joystick=joy)
        ctrl, _ = make_controller(pygame_obj=pg)
        ctrl.rumble(0.5, 100)
        assert joy.rumble_calls == [(0.5, 0.5, 100)]

    def test_rumble_no_joystick_is_noop(self):
        pg = FakePygame(joystick_count=0)
        ctrl, _ = make_controller(pygame_obj=pg)
        ctrl.rumble()  # should not raise

    def test_close_releases_joystick(self):
        joy = FakeJoystick()
        pg = FakePygame(joystick_count=1, joystick=joy)
        ctrl, _ = make_controller(pygame_obj=pg)
        ctrl.close()
        assert joy.quit_called is True
        assert ctrl.is_connected() is False
