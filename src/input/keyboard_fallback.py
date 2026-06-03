#!/usr/bin/env python3
"""
Keyboard fallback for the input abstraction layer.

This module maps pygame keyboard events onto the same logical ``Button`` model
used by the gamepad ``Controller``. It exists so the whole controller-driven UI
is testable and usable **without a physical USB gamepad** -- i.e. on a developer
machine running the pygame simulator, or on a headless CI box.

Pygame event-queue coexistence with the simulator
--------------------------------------------------
There is a **single, process-global pygame event queue** (``pygame.event.get()``
drains it for the whole process). The simulator window in
``src/simulator/matrix.py`` *also* pumps that queue inside
``_SimulatorWindow.render()`` -- but today it only looks for ``pygame.QUIT`` and
**discards every other event**, including the very keydown/keyup events this
fallback needs.

If both the simulator's ``render()`` and ``Controller.poll_events()`` blindly
called ``pygame.event.get()`` they would race: whichever drained the queue first
would starve the other (lost keypresses, or a window that never closes).

To coexist, this module never calls ``pygame.event.get()`` itself. Instead the
owning :class:`~src.input.controller.Controller` pumps the queue **once** per
``poll_events()`` and hands the already-fetched event objects to
:func:`translate_key_event` here for keyboard translation only. The controller is
the single queue owner; ``QUIT`` is surfaced via ``Controller.wants_quit`` /
the ``wants_quit()`` helper so the simulator no longer needs to drain the queue
independently (the integration that stops ``render()`` from draining is part of
the later state-machine phase; until then both can call ``poll_events`` -- see
the controller docstring for the peek-safe ``pump_shared_events`` note).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Import the logical Button enum from the controller module. Importing lazily at
# module top-level is fine: controller.py does NOT import this module at import
# time for the enum (it imports the translation function lazily) so there is no
# circular-import hazard for the enums themselves.
from .controller import Button


# ---------------------------------------------------------------------------
# Default keyboard -> logical Button mapping (per CONTROLLER_OVERHAUL.md §2.7)
# ---------------------------------------------------------------------------
# We key the mapping on the pygame key *constant name* (a string such as
# "K_UP") rather than the integer value. This keeps the table importable and
# inspectable even when pygame is not installed, and lets tests build synthetic
# events without pulling in real SDL key codes.
#
#   Arrow keys / WASD -> UP / DOWN / LEFT / RIGHT
#   Z or Enter        -> A
#   X or Backspace    -> B
#   Enter / Return    -> START   (spec lists Enter for both A and START; we make
#                                 Enter = START and use Z for A to avoid a clash,
#                                 matching the task's explicit table:
#                                 Z -> A, X -> B, Enter -> START, Tab -> SELECT)
#   Tab / Right Shift -> SELECT
#
# Task spec table (authoritative for this phase):
#   Arrow keys/WASD -> directions, Z -> A, X -> B, Enter -> START, Tab -> SELECT
DEFAULT_KEY_MAP: dict[str, Button] = {
    # Directions -- arrows
    "K_UP": Button.UP,
    "K_DOWN": Button.DOWN,
    "K_LEFT": Button.LEFT,
    "K_RIGHT": Button.RIGHT,
    # Directions -- WASD
    "K_w": Button.UP,
    "K_s": Button.DOWN,
    "K_a": Button.LEFT,
    "K_d": Button.RIGHT,
    # Action buttons
    "K_z": Button.A,
    "K_x": Button.B,
    "K_RETURN": Button.START,
    "K_KP_ENTER": Button.START,
    "K_TAB": Button.SELECT,
    "K_RSHIFT": Button.SELECT,
}


def _build_keycode_map() -> dict[int, Button]:
    """Resolve the string-keyed :data:`DEFAULT_KEY_MAP` to a pygame integer
    keycode -> :class:`Button` map.

    Returns an empty dict if pygame is unavailable (headless with no SDL),
    which simply means the keyboard fallback produces no events -- graceful
    degradation, never a crash.
    """
    try:
        import pygame
    except Exception:  # pragma: no cover - exercised only when pygame missing
        logger.debug("pygame unavailable; keyboard fallback disabled")
        return {}

    resolved: dict[int, Button] = {}
    for const_name, button in DEFAULT_KEY_MAP.items():
        keycode = getattr(pygame, const_name, None)
        if keycode is not None:
            resolved[int(keycode)] = button
    return resolved


class KeyboardFallback:
    """Translates pygame KEYDOWN/KEYUP events into logical button edges.

    The :class:`~src.input.controller.Controller` owns the pygame event queue
    and feeds individual events to :meth:`handle_event`. This class is purely a
    pure-ish translator + held-state tracker; it never touches the queue, so it
    cannot starve the simulator of events.
    """

    def __init__(self, key_map: dict[int, Button] | None = None):
        # Map of pygame keycode (int) -> Button. Lazily resolved from the
        # string table when not explicitly supplied (so tests can inject a
        # synthetic map without pygame).
        self._key_map: dict[int, Button] = (
            key_map if key_map is not None else _build_keycode_map()
        )

    @property
    def key_map(self) -> dict[int, Button]:
        return self._key_map

    def translate(self, event, is_press: bool) -> Button | None:
        """Translate a single (already-classified) key event to a :class:`Button`.

        The owning controller has *already* determined this is a KEYDOWN
        (``is_press=True``) or KEYUP (``is_press=False``) using its own pygame
        constants, so this method does NOT import pygame itself -- it only maps
        the event's ``key`` attribute through :attr:`key_map`. This keeps the
        translator usable with a fake pygame in tests and on boxes where the
        real pygame module is unavailable.

        Returns ``None`` if the key is not in the mapping.
        """
        return self._key_map.get(getattr(event, "key", None))


def translate_key_event(
    event, is_press: bool, key_map: dict[int, Button] | None = None
) -> Button | None:
    """Module-level convenience wrapper around :meth:`KeyboardFallback.translate`.

    Builds a one-shot translator. Prefer constructing a :class:`KeyboardFallback`
    once and reusing it in hot loops; this helper exists mainly for tests.
    """
    return KeyboardFallback(key_map).translate(event, is_press)
