#!/usr/bin/env python3
"""
pygame joystick input abstraction layer.

This module wraps the pygame joystick API behind a **logical** button model so
the rest of the application (menus, games, the state machine in later phases)
never reasons about raw joystick button/axis/hat indices. It also provides a
keyboard fallback path so everything is usable and testable without a physical
gamepad.

Key responsibilities
---------------------
* Translate raw joystick buttons / hat / analog axes into logical
  :class:`Button` presses, releases, and auto-REPEAT events.
* Unify the D-pad (hat) and the analog stick into the four directional buttons
  via a configurable dead-zone.
* Tolerate device **absence** and **hot-plug** (``JOYDEVICEADDED`` /
  ``JOYDEVICEREMOVED``) without crashing.
* Load a per-device :class:`ButtonMapping` override from
  ``config/controller.json`` (written by the calibration CLI), falling back to a
  sane built-in default when missing/invalid.
* Provide a ``calibrate`` CLI entry point (``python -m src.input.controller
  calibrate``).

pygame event-queue coexistence with the simulator
--------------------------------------------------
``pygame.event.get()`` drains a **single process-global queue**. The simulator
window (``src/simulator/matrix.py``) also pumps that queue inside ``render()``,
but currently only to catch ``pygame.QUIT`` -- it throws away everything else.

If the controller and the simulator both called ``pygame.event.get()`` they
would race and steal events from each other (lost button presses, or a window
that never closes). The design here makes the **controller the single owner** of
the queue:

* :meth:`Controller.poll_events` calls ``pygame.event.get()`` exactly once per
  invocation and processes *all* event types it cares about (joystick + mapped
  keyboard), and it records ``QUIT`` into :attr:`Controller.wants_quit_flag`
  (surfaced via the module-level :func:`wants_quit` helper / :meth:`is_quitting`)
  so the simulator does not have to drain the queue itself.
* Joystick add/remove events drive hot-plug handling.
* Events the controller does not understand are simply ignored (not re-posted),
  which is safe because in this architecture nothing else needs them.

During this phase the simulator's ``render()`` still independently drains
``QUIT``; that is harmless for the tests here (they never run the window loop)
and is reconciled in the state-machine phase per the spec. The important
invariant honored here: the controller only *peeks/filters* the joystick +
relevant keyboard events and never assumes it owns unrelated events.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Path to the per-device override written by the calibration CLI.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTROLLER_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config", "controller.json")

# Seconds to hold START (with no Select pressed) before the hold-to-quit
# fallback fires. Clones often lack a real Select button (spec §9 risk 5).
START_HOLD_QUIT_SECONDS = 1.5


# ---------------------------------------------------------------------------
# Logical input model (CONTROLLER_OVERHAUL.md §2.2 / §2.3)
# ---------------------------------------------------------------------------
class Button(Enum):
    """Logical buttons the rest of the app reasons about."""

    A = "A"            # confirm / select / primary game action
    B = "B"            # back / cancel / secondary game action
    START = "START"    # open menu (from IDLE) / pause-or-quit (IN_GAME)
    SELECT = "SELECT"  # secondary; combined with START = quit game
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class EventType(Enum):
    """Kinds of logical events emitted by :meth:`Controller.poll_events`."""

    PRESSED = "PRESSED"    # edge: button went down this poll
    RELEASED = "RELEASED"  # edge: button went up this poll
    REPEAT = "REPEAT"      # held-down auto-repeat (for menu scrolling)


@dataclass(frozen=True)
class InputEvent:
    """A single logical input event."""

    button: Button
    type: EventType
    timestamp: float  # time.monotonic() (or injected clock) when generated


# Buttons that auto-repeat while held (directional, for menu scrolling and
# tetris-style movement). Action buttons never repeat.
_REPEATABLE = {Button.UP, Button.DOWN, Button.LEFT, Button.RIGHT}

# Direction -> (dx, dy) for get_direction(). dy: up is negative (screen coords).
_DIR_VECTORS = {
    Button.UP: (0, -1),
    Button.DOWN: (0, 1),
    Button.LEFT: (-1, 0),
    Button.RIGHT: (1, 0),
}


# ---------------------------------------------------------------------------
# Button mapping (CONTROLLER_OVERHAUL.md §2.5)
# ---------------------------------------------------------------------------
@dataclass
class ButtonMapping:
    """Maps physical joystick controls to logical buttons.

    ``buttons`` maps a pygame joystick *button index* to a logical
    :class:`Button`. The D-pad is read from ``hat_index`` and the analog stick
    from ``axis_x`` / ``axis_y`` (with optional Y inversion). Both feed the same
    four directional logical buttons via ``deadzone``.
    """

    buttons: dict[int, Button] = field(default_factory=dict)
    hat_index: int = 0
    axis_x: int = 0
    axis_y: int = 1
    invert_y: bool = False
    deadzone: float = 0.5

    # ----- (de)serialization -------------------------------------------------
    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict (logical buttons as their names)."""
        return {
            "buttons": {str(idx): btn.value for idx, btn in self.buttons.items()},
            "hat_index": self.hat_index,
            "axis_x": self.axis_x,
            "axis_y": self.axis_y,
            "invert_y": self.invert_y,
            "deadzone": self.deadzone,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ButtonMapping":
        """Build a mapping from a parsed JSON dict, tolerating partial data.

        Unknown / malformed entries are skipped rather than raising, so a
        slightly stale or hand-edited config still yields a usable mapping.
        """
        if not isinstance(data, dict):
            raise ValueError("controller mapping must be a JSON object")

        buttons: dict[int, Button] = {}
        raw_buttons = data.get("buttons", {})
        if isinstance(raw_buttons, dict):
            for idx, name in raw_buttons.items():
                try:
                    buttons[int(idx)] = Button(name)
                except (ValueError, TypeError):
                    logger.warning(
                        "Ignoring invalid controller button entry %r=%r", idx, name
                    )

        default = cls()
        return cls(
            buttons=buttons or dict(default_mapping().buttons),
            hat_index=int(data.get("hat_index", default.hat_index)),
            axis_x=int(data.get("axis_x", default.axis_x)),
            axis_y=int(data.get("axis_y", default.axis_y)),
            invert_y=bool(data.get("invert_y", default.invert_y)),
            deadzone=float(data.get("deadzone", default.deadzone)),
        )


def default_mapping() -> ButtonMapping:
    """A best-guess default mapping for a generic GameCube-style USB pad.

    Many cheap clones expose: button 0 = bottom face (A), button 1 = right face
    (B), and Start/Select around indices 9/8. The analog stick is usually axes
    0 (X) and 1 (Y); the D-pad is hat 0. These are guesses -- the calibration
    CLI exists precisely because the real indices are unknown until tested.
    """
    return ButtonMapping(
        buttons={
            0: Button.A,
            1: Button.B,
            9: Button.START,
            8: Button.SELECT,
        },
        hat_index=0,
        axis_x=0,
        axis_y=1,
        invert_y=False,
        deadzone=0.5,
    )


def load_mapping(path: str = CONTROLLER_CONFIG_PATH) -> ButtonMapping:
    """Load a :class:`ButtonMapping` override from ``path``.

    Falls back to :func:`default_mapping` when the file is missing, unreadable,
    or contains invalid JSON -- never raises for those cases (graceful
    degradation so the controller always has *some* mapping).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.info("No controller override at %s; using default mapping", path)
        return default_mapping()
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(
            "Invalid controller config %s (%s); using default mapping", path, e
        )
        return default_mapping()

    try:
        return ButtonMapping.from_dict(data)
    except Exception as e:  # noqa: BLE001 - any malformed structure -> default
        logger.warning("Could not parse controller mapping (%s); using default", e)
        return default_mapping()


def save_mapping(mapping: ButtonMapping, path: str = CONTROLLER_CONFIG_PATH) -> bool:
    """Atomically write ``mapping`` to ``path`` (temp file + ``os.replace``).

    Mirrors the atomic write strategy used elsewhere in the project
    (``living_world/persistence.py``): write to a sibling ``*.tmp`` file then
    ``os.replace`` so a crash mid-write cannot corrupt the config.
    """
    import tempfile

    tmp_path = None
    try:
        config_dir = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(config_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=config_dir, suffix=".tmp", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(mapping.to_dict(), tmp, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, path)
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to save controller mapping: %s", e)
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
def _real_hardware_present() -> bool:
    """True if the real ``rgbmatrix`` C-extension is importable (i.e. on a Pi).

    When absent we are on a dev machine / simulator and force-enable the
    keyboard fallback so the UI is drivable without a gamepad. The simulator
    registers itself as ``rgbmatrix`` in ``sys.modules`` during tests; we treat
    a module carrying the ``_IS_SIMULATOR`` marker as "not real hardware".
    """
    try:
        import rgbmatrix  # noqa: F401

        return not getattr(sys.modules.get("rgbmatrix"), "_IS_SIMULATOR", False)
    except ImportError:
        return False


class Controller:
    """Logical gamepad interface backed by pygame, with keyboard fallback.

    See the module docstring for the pygame event-queue coexistence contract:
    this class is the single owner of ``pygame.event.get()``.
    """

    def __init__(
        self,
        deadzone: float = 0.5,
        repeat_delay: float = 0.35,
        repeat_interval: float = 0.12,
        mapping: "ButtonMapping | None" = None,
        enable_keyboard_fallback: bool = True,
        clock=None,
    ):
        """
        :param deadzone: analog-stick magnitude past which a direction registers.
        :param repeat_delay: seconds a direction must be held before REPEAT fires.
        :param repeat_interval: seconds between REPEAT events while held.
        :param mapping: explicit :class:`ButtonMapping`; if ``None`` it is loaded
            from ``config/controller.json`` (falling back to the default).
        :param enable_keyboard_fallback: enable the keyboard path. Force-enabled
            anyway when no real ``rgbmatrix`` hardware is present (dev/sim).
        :param clock: callable returning a monotonically increasing float; used
            for repeat timing and event timestamps. Injectable for tests.
            Defaults to :func:`time.monotonic`.
        """
        self._mapping = mapping if mapping is not None else load_mapping()
        # Explicit deadzone arg wins; otherwise inherit the mapping's value.
        self._deadzone = deadzone if deadzone is not None else self._mapping.deadzone
        self._repeat_delay = repeat_delay
        self._repeat_interval = repeat_interval
        self._clock = clock or time.monotonic

        # Force keyboard fallback when running without real hardware.
        self._keyboard_enabled = (
            enable_keyboard_fallback or not _real_hardware_present()
        )

        # Logical held-state and repeat bookkeeping.
        self._held: dict[Button, bool] = {b: False for b in Button}
        # Keyboard-driven directional holds. Keyboard is edge-driven (KEYDOWN/
        # KEYUP) unlike the joystick hat/axis which we re-sample each poll, so we
        # must remember which directions the keyboard is currently holding and
        # re-apply them after the per-poll directional reset.
        self._kbd_dirs: set[Button] = set()
        # For each held repeatable button: the next monotonic time a REPEAT
        # should fire.
        self._next_repeat: dict[Button, float] = {}

        # pygame / joystick state.
        self._pygame = None
        self._joystick = None
        self._connected = False
        self._kbd = None

        # QUIT gesture surfaced for the simulator (see coexistence contract).
        self.wants_quit_flag = False

        # Hold-START fallback quit timing (for clones lacking a real Select).
        self._start_held_since: float | None = None

        self._init_pygame()

    # ----- initialization ----------------------------------------------------
    def _init_pygame(self) -> None:
        """Initialize pygame's joystick subsystem if available.

        On a headless box this may need ``SDL_VIDEODRIVER=dummy``; we set a
        default so importing/using the controller never hard-crashes when no
        display exists. Any failure leaves the controller in a disconnected but
        functional (keyboard-only / no-op) state.
        """
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            # Default to the dummy SDL drivers when nothing else is configured,
            # so joystick init works on a headless Pi / CI without a display.
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
            import pygame

            self._pygame = pygame
        except Exception as e:  # noqa: BLE001
            logger.warning("pygame unavailable (%s); controller will be a no-op", e)
            self._pygame = None
            return

        try:
            if not pygame.get_init():
                pygame.init()
            if not pygame.joystick.get_init():
                pygame.joystick.init()
        except Exception as e:  # noqa: BLE001
            logger.warning("pygame joystick init failed (%s); no-controller mode", e)

        # Build the keyboard translator (resolves key constants from pygame).
        if self._keyboard_enabled:
            try:
                from .keyboard_fallback import KeyboardFallback

                self._kbd = KeyboardFallback()
            except Exception as e:  # noqa: BLE001
                logger.warning("Keyboard fallback unavailable (%s)", e)
                self._kbd = None

        # Try to open any already-attached joystick.
        self._try_open_joystick()

    def _try_open_joystick(self) -> None:
        """Open joystick 0 if one is present; tolerate absence."""
        if self._pygame is None:
            return
        try:
            if self._pygame.joystick.get_count() > 0:
                self._joystick = self._pygame.joystick.Joystick(0)
                self._joystick.init()
                self._connected = True
                logger.info("Joystick connected: %s", self._safe_name())
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to open joystick (%s)", e)
            self._joystick = None
            self._connected = False

    def _safe_name(self) -> str:
        try:
            return self._joystick.get_name()
        except Exception:  # noqa: BLE001
            return "<unknown>"

    # ----- event source (simulator bridge or direct pygame) -------------------
    def _drain_simulator_events(self) -> list:
        """Get raw pygame events, bridging the Windows threading limitation.

        On Windows, pygame events can only be received from the thread that
        created the display. When running in simulator mode, the simulator's
        ``render()`` (main thread) collects events into a buffer; we drain
        that buffer here. On the Pi (real rgbmatrix, no simulator), we call
        ``pygame.event.get()`` directly since there's no display-thread issue.

        This method is safe to call from any thread.
        """
        # Try to get events from the simulator's buffer first
        try:
            from src.simulator.matrix import _SimulatorWindow
            window = _SimulatorWindow._instance
            if window is not None and window._initialized:
                return window.drain_events()
        except (ImportError, AttributeError):
            pass

        # Fallback: direct pygame.event.get() (works on Pi / when no simulator)
        return self._pygame.event.get()

    # ----- public API --------------------------------------------------------
    def poll_events(self) -> list[InputEvent]:
        """Pump pygame once and return logical edge + REPEAT events since the
        last call. Non-blocking. Also drives hot-plug detection and the QUIT
        gesture.

        This is the **single** place the process drains ``pygame.event.get()``.
        """
        now = self._clock()
        events: list[InputEvent] = []

        # Snapshot the previous logical-held state so we can diff after applying
        # this poll's raw inputs.
        prev_held = dict(self._held)
        # Directional held-state is recomputed each poll from hat+axis+keys, so
        # clear only the directional bits; action buttons are edge-driven and
        # persist across polls until their KEYUP/JOYBUTTONUP arrives.
        for d in _REPEATABLE:
            self._held[d] = False

        if self._pygame is not None:
            try:
                # On Windows, pygame events can only be received from the
                # thread that created the display. When running in simulator
                # mode, the simulator's render() (main thread) collects events
                # into a buffer; we drain that buffer here instead of calling
                # pygame.event.get() directly (which would return nothing from
                # a background thread). On the Pi with real rgbmatrix, there's
                # no simulator window, so we use pygame.event.get() directly.
                raw_events = self._drain_simulator_events()
            except Exception:  # noqa: BLE001 - SDL not ready, etc.
                raw_events = []

            for ev in raw_events:
                self._process_raw_event(ev)

            # Re-apply keyboard-held directions (edge-driven, so they persist
            # across polls until their KEYUP) on top of the per-poll reset.
            for d in self._kbd_dirs:
                self._held[d] = True

            # After discrete events, sample continuous hat/axis state for the
            # directional buttons (level-based). Keyboard directions set above
            # are OR'd (never reset here).
            self._sample_directions()

        # Diff held-state to emit PRESSED / RELEASED edges.
        for button in Button:
            was = prev_held.get(button, False)
            is_now = self._held.get(button, False)
            if is_now and not was:
                events.append(InputEvent(button, EventType.PRESSED, now))
                if button in _REPEATABLE:
                    self._next_repeat[button] = now + self._repeat_delay
            elif not is_now and was:
                events.append(InputEvent(button, EventType.RELEASED, now))
                self._next_repeat.pop(button, None)

        # Emit REPEAT events for still-held repeatable buttons.
        for button in _REPEATABLE:
            if self._held.get(button) and button in self._next_repeat:
                # Catch up if the caller polled slowly, but cap to avoid runaway.
                fired = 0
                while now >= self._next_repeat[button] and fired < 8:
                    events.append(InputEvent(button, EventType.REPEAT, now))
                    self._next_repeat[button] += self._repeat_interval
                    fired += 1

        # Track START-hold for the quit fallback gesture.
        if self._held.get(Button.START):
            if self._start_held_since is None:
                self._start_held_since = now
        else:
            self._start_held_since = None

        return events

    def _process_raw_event(self, ev) -> None:
        """Apply one raw pygame event to internal state."""
        pg = self._pygame
        etype = getattr(ev, "type", None)

        if etype == pg.QUIT:
            self.wants_quit_flag = True
            return

        # Hot-plug handling.
        if etype == getattr(pg, "JOYDEVICEADDED", None):
            self._try_open_joystick()
            return
        if etype == getattr(pg, "JOYDEVICEREMOVED", None):
            self._handle_disconnect()
            return

        # Joystick buttons -> mapped logical buttons.
        if etype == getattr(pg, "JOYBUTTONDOWN", None):
            button = self._mapping.buttons.get(getattr(ev, "button", None))
            if button is not None:
                self._held[button] = True
            return
        if etype == getattr(pg, "JOYBUTTONUP", None):
            button = self._mapping.buttons.get(getattr(ev, "button", None))
            if button is not None:
                self._held[button] = False
            return

        # Keyboard fallback. The controller (single queue owner) classifies the
        # event as KEYDOWN/KEYUP here; the translator only maps the keycode (so
        # it does not need to import pygame itself).
        if self._kbd is not None:
            is_down = etype == getattr(pg, "KEYDOWN", None)
            is_up = etype == getattr(pg, "KEYUP", None)
            if is_down or is_up:
                button = self._kbd.translate(ev, is_down)
                if button is not None:
                    self._held[button] = is_down
                    # Track keyboard directional holds separately so they
                    # survive the per-poll directional reset (keyboard is
                    # edge-driven, unlike the re-sampled joystick hat/axis).
                    if button in _REPEATABLE:
                        if is_down:
                            self._kbd_dirs.add(button)
                        else:
                            self._kbd_dirs.discard(button)

    def _sample_directions(self) -> None:
        """Recompute directional held-state from the D-pad hat and analog stick.

        Both sources feed the same logical UP/DOWN/LEFT/RIGHT buttons; diagonals
        are allowed. We only OR onto the directional bits (already reset at the
        start of ``poll_events``) so keyboard-driven directions are preserved.
        """
        if self._joystick is None or not self._connected:
            return

        dz = self._deadzone

        # D-pad / hat.
        try:
            if self._joystick.get_numhats() > self._mapping.hat_index:
                hx, hy = self._joystick.get_hat(self._mapping.hat_index)
                if hx < 0:
                    self._held[Button.LEFT] = True
                elif hx > 0:
                    self._held[Button.RIGHT] = True
                # pygame hats report +1 = up.
                if hy > 0:
                    self._held[Button.UP] = True
                elif hy < 0:
                    self._held[Button.DOWN] = True
        except Exception:  # noqa: BLE001
            pass

        # Analog stick.
        try:
            naxes = self._joystick.get_numaxes()
            if naxes > self._mapping.axis_x:
                ax = self._joystick.get_axis(self._mapping.axis_x)
                if ax <= -dz:
                    self._held[Button.LEFT] = True
                elif ax >= dz:
                    self._held[Button.RIGHT] = True
            if naxes > self._mapping.axis_y:
                ay = self._joystick.get_axis(self._mapping.axis_y)
                if self._mapping.invert_y:
                    ay = -ay
                # SDL axis: -1 = up by convention.
                if ay <= -dz:
                    self._held[Button.UP] = True
                elif ay >= dz:
                    self._held[Button.DOWN] = True
        except Exception:  # noqa: BLE001
            pass

    def _handle_disconnect(self) -> None:
        """Drop the joystick handle on hot-unplug.

        We clear the joystick handle and connection flag here; the next
        ``poll_events`` diff naturally emits RELEASED for any buttons/directions
        that were held (because ``_sample_directions`` returns early when
        disconnected and mapped joystick buttons stop being set). Keyboard
        fallback keeps working so dev/sim use is uninterrupted.
        """
        logger.info("Joystick disconnected")
        try:
            if self._joystick is not None:
                self._joystick.quit()
        except Exception:  # noqa: BLE001
            pass
        self._joystick = None
        self._connected = False

    def is_pressed(self, button: Button) -> bool:
        """Level query: True while the logical ``button`` is currently held."""
        return bool(self._held.get(button, False))

    def is_connected(self) -> bool:
        """True if a physical joystick is currently attached."""
        return self._connected

    def get_direction(self) -> "tuple[int, int] | None":
        """Current 8-way direction as ``(dx, dy)`` or ``None`` when centered.

        ``dx, dy`` are each in ``{-1, 0, 1}`` and combine the four directional
        logical buttons (D-pad + analog + keyboard) so diagonals are possible.
        """
        dx = 0
        dy = 0
        for button, (vx, vy) in _DIR_VECTORS.items():
            if self._held.get(button):
                dx += vx
                dy += vy
        dx = max(-1, min(1, dx))
        dy = max(-1, min(1, dy))
        if dx == 0 and dy == 0:
            return None
        return (dx, dy)

    def rumble(self, strength: float = 1.0, duration_ms: int = 200) -> None:
        """Optional haptics if the device supports it; no-op otherwise."""
        if self._joystick is None:
            return
        try:
            # pygame >= 2 exposes Joystick.rumble(low, high, duration_ms).
            rumble = getattr(self._joystick, "rumble", None)
            if rumble is not None:
                s = max(0.0, min(1.0, strength))
                rumble(s, s, int(duration_ms))
        except Exception:  # noqa: BLE001
            pass  # Haptics are best-effort.

    def is_quitting(self) -> bool:
        """True if a pygame ``QUIT`` was seen since construction.

        Lets the simulator/main loop observe window-close without draining the
        event queue itself (see the event-queue coexistence contract).
        """
        return self.wants_quit_flag

    def start_hold_seconds(self) -> float:
        """Seconds START has been continuously held (0.0 if not held).

        Used by :func:`wants_quit` for the hold-START quit fallback.
        """
        if self._start_held_since is None:
            return 0.0
        return max(0.0, self._clock() - self._start_held_since)

    def close(self) -> None:
        """Release pygame joystick resources (idempotent)."""
        try:
            if self._joystick is not None:
                self._joystick.quit()
        except Exception:  # noqa: BLE001
            pass
        self._joystick = None
        self._connected = False
        try:
            if self._pygame is not None and self._pygame.joystick.get_init():
                self._pygame.joystick.quit()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Quit-gesture helper (CONTROLLER_OVERHAUL.md §5.4 + §9 risk 5)
# ---------------------------------------------------------------------------
def wants_quit(controller: "Controller") -> bool:
    """Return True on the quit gesture.

    Three equivalent gestures (per the spec's risk note about clones lacking a
    real Select button):

    * **START pressed alone** (single press returns to menu immediately), or
    * **START + SELECT** held simultaneously (the deliberate combo), or
    * **holding START** alone for ~:data:`START_HOLD_QUIT_SECONDS` seconds.

    Callers should invoke this once per frame after ``poll_events()`` (which
    updates held-state and the START-hold timer).

    NOTE: This function is only called inside game ``run()`` loops (interactive
    mode). The menu system handles START separately in its own loop, so this
    does not conflict with menu navigation.
    """
    if controller.is_pressed(Button.START):
        return True
    if controller.is_pressed(Button.START) and controller.is_pressed(Button.SELECT):
        return True
    if controller.start_hold_seconds() >= START_HOLD_QUIT_SECONDS:
        return True
    return False


# ---------------------------------------------------------------------------
# Calibration CLI (CONTROLLER_OVERHAUL.md §2.5 / Phase 1)
# ---------------------------------------------------------------------------
def _calibrate(path: str = CONTROLLER_CONFIG_PATH) -> int:
    """Interactive calibration: prompt for each logical button, capture the
    physical pygame button/axis/hat IDs, and write ``config/controller.json``
    atomically.

    Returns a process exit code: 0 on success, non-zero if no joystick is
    connected or the user aborts.
    """
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    try:
        import pygame
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: pygame is required for calibration but is unavailable: {e}")
        return 2

    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print(
            "ERROR: No joystick/gamepad detected.\n"
            "Plug in your USB controller and try again."
        )
        pygame.quit()
        return 1

    js = pygame.joystick.Joystick(0)
    js.init()
    print(f"Calibrating controller: {js.get_name()}")
    print(
        f"  buttons={js.get_numbuttons()} axes={js.get_numaxes()} "
        f"hats={js.get_numhats()}"
    )
    print("Press the requested control for each prompt. Press Ctrl+C to abort.\n")

    # Logical face/menu buttons we discover via JOYBUTTONDOWN.
    to_capture = [Button.A, Button.B, Button.START, Button.SELECT]
    buttons: dict[int, Button] = {}

    def _wait_for_button(label: str) -> "int | None":
        print(f"  Press {label} ...", end="", flush=True)
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.JOYBUTTONDOWN:
                    print(f" got button {event.button}")
                    return event.button
            pygame.time.wait(10)

    try:
        for logical in to_capture:
            idx = _wait_for_button(logical.value)
            if idx is None:
                print("\nAborted.")
                pygame.quit()
                return 1
            buttons[idx] = logical
            # Debounce: wait for release so the next prompt doesn't re-trigger.
            _drain_until_release(pygame, idx)

        # Axis/hat discovery: ask the user to push the stick and we record which
        # axes move; fall back to defaults if nothing moves.
        print("\n  Push the LEFT analog stick fully RIGHT, then release ...")
        axis_x = _detect_axis(pygame)
        print(f"    -> using axis_x={axis_x}")
        print("  Push the LEFT analog stick fully DOWN, then release ...")
        axis_y = _detect_axis(pygame)
        print(f"    -> using axis_y={axis_y}")
    except KeyboardInterrupt:
        print("\nAborted by user.")
        pygame.quit()
        return 1

    mapping = ButtonMapping(
        buttons=buttons,
        hat_index=0,
        axis_x=axis_x if axis_x is not None else 0,
        axis_y=axis_y if axis_y is not None else 1,
        invert_y=False,
        deadzone=0.5,
    )

    if save_mapping(mapping, path):
        print(f"\nSaved controller mapping to {path}")
        pygame.quit()
        return 0
    print("\nERROR: failed to write controller mapping.")
    pygame.quit()
    return 3


def _drain_until_release(pygame, button_idx: int) -> None:
    """Block until the given joystick button is released (debounce helper)."""
    while True:
        for event in pygame.event.get():
            if event.type == pygame.JOYBUTTONUP and event.button == button_idx:
                return
            if event.type == pygame.QUIT:
                return
        pygame.time.wait(10)


def _detect_axis(pygame, threshold: float = 0.6, timeout_s: float = 8.0):
    """Return the index of the first axis that exceeds ``threshold``.

    Waits up to ``timeout_s`` for the user to move the stick; returns ``None``
    on timeout (caller falls back to a default axis index).
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.JOYAXISMOTION:
                if abs(event.value) >= threshold:
                    idx = event.axis
                    # Wait for the axis to recenter before returning.
                    _drain_axis_recenter(pygame, idx)
                    return idx
        pygame.time.wait(10)
    return None


def _drain_axis_recenter(pygame, axis_idx: int, threshold: float = 0.3) -> None:
    """Block until the given axis returns near center."""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        for event in pygame.event.get():
            if event.type == pygame.JOYAXISMOTION and event.axis == axis_idx:
                if abs(event.value) < threshold:
                    return
            if event.type == pygame.QUIT:
                return
        pygame.time.wait(10)


def main(argv: "list[str] | None" = None) -> int:
    """Entry point for ``python -m src.input.controller [calibrate]``."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "calibrate":
        return _calibrate()
    print("Usage: python -m src.input.controller calibrate")
    print("  calibrate  Interactively map your gamepad to config/controller.json")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())