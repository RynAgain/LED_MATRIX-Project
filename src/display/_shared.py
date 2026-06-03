"""Shared state and helpers for display modules to support instant switching
and (Phase 5) controller-driven interactive games.

The controller-facing helpers here keep the three playable games
(snake/tetris/pong) thin: they centralize the *interactive* concerns -- reading
a logical direction from the controller, rendering entry/game-over banners, and
best-effort haptics -- so each game's ``run()`` only has to branch on
``controller is None`` (DEMO) vs not-None (INTERACTIVE) without duplicating UI
or input-translation logic. None of these helpers alter demo-mode behavior; the
``controller=None`` path in every game remains byte-for-byte the original.
"""
import threading
import time

_stop_event = threading.Event()


def request_stop():
    """Signal the current feature to stop ASAP."""
    _stop_event.set()


def clear_stop():
    """Clear the stop flag before starting a new feature."""
    _stop_event.clear()


def should_stop():
    """Check if the current feature should stop. Call this in your render loop."""
    return _stop_event.is_set()


def interruptible_sleep(seconds, interval=0.1):
    """Sleep for the given duration, returning early if stop is signalled.
    Returns True if sleep completed, False if interrupted by stop signal."""
    if _stop_event.wait(timeout=seconds):
        return False  # interrupted
    return True


# ---------------------------------------------------------------------------
# Interactive-mode helpers (Phase 5 -- controller-driven playable games)
# ---------------------------------------------------------------------------
# These are intentionally dependency-light: they accept a duck-typed
# ``controller`` exposing the public API documented in
# ``src/input/controller.py`` (``poll_events``, ``get_direction``,
# ``is_pressed``, ``rumble``). Importing the concrete ``Button`` enum lazily
# keeps ``_shared`` free of an import cycle and lets these helpers no-op
# gracefully if the input package is ever unavailable.


def read_direction(controller, cardinal_only=True):
    """Return the controller's current direction as ``(dx, dy)`` or ``None``.

    ``dx, dy`` use **screen coordinates** (up is ``dy == -1``), matching the
    convention used by every game module's direction constants.

    :param cardinal_only: when ``True`` (the default), diagonal input is resolved
        to a single dominant axis so games that only accept the four cardinal
        directions (snake) never receive an ambiguous diagonal. The dominant
        axis is chosen by preferring the most-recently distinct axis is not
        tracked here; instead horizontal wins ties, which is irrelevant for the
        consuming games since they reject reversals/keep their current axis.
    """
    try:
        d = controller.get_direction()
    except Exception:  # noqa: BLE001 - a flaky controller must never crash a game
        return None
    if d is None:
        return None
    dx, dy = d
    if cardinal_only and dx != 0 and dy != 0:
        # Resolve a diagonal to a single dominant axis. We can't know magnitude
        # from the (-1,0,1) tuple, so collapse to horizontal deterministically;
        # consuming games keep their current axis when the chosen one is a
        # reversal, so this tie-break never causes surprising movement.
        dy = 0
    return (dx, dy)


def safe_rumble(controller, strength=1.0, duration_ms=200):
    """Invoke ``controller.rumble`` if available; never raise.

    Used for game-over feedback. A ``None`` controller (demo mode) or a device
    without haptics is a silent no-op.
    """
    if controller is None:
        return
    try:
        controller.rumble(strength, duration_ms)
    except Exception:  # noqa: BLE001 - haptics are strictly best-effort
        pass


def show_banner(matrix, lines, color=(180, 220, 255), size=64,
                hold=1.0, bg=(0, 0, 0)):
    """Render one or more centered text ``lines`` and hold briefly.

    Reuses the shared 5x7 font (``_fonts``). Honors :func:`should_stop` via
    :func:`interruptible_sleep`. Used for the interactive entry splash ("READY")
    and game-over screens so the player gets clear feedback before control
    returns to the menu.

    :param lines: a single string or an iterable of strings (stacked vertically).
    :param hold: seconds to display the banner (interruptible).
    :returns: ``True`` if the hold completed, ``False`` if interrupted by stop.
    """
    if isinstance(lines, str):
        lines = [lines]
    lines = [str(s).upper() for s in lines]

    try:
        from PIL import Image, ImageDraw
        from src.display._fonts import _draw_text, _text_width
    except Exception:  # noqa: BLE001 - degrade gracefully if PIL/font missing
        return interruptible_sleep(hold)

    image = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(image)

    line_h = 7 + 3  # glyph height + gap
    total_h = line_h * len(lines) - 3
    start_y = max(0, (size - total_h) // 2)
    for i, text in enumerate(lines):
        w = _text_width(text, scale=1, spacing=1)
        x = max(0, (size - w) // 2)
        y = start_y + i * line_h
        _draw_text(draw, text, x, y, color, scale=1, spacing=1)

    try:
        matrix.SetImage(image)
    except Exception:  # noqa: BLE001
        pass
    return interruptible_sleep(hold)
