#!/usr/bin/env python3
"""
On-device Settings screen (CONTROLLER_OVERHAUL.md §6).

With the web UI removed, settings are edited directly on the matrix with the
gamepad. This module provides:

* :func:`load_settings` / :func:`save_settings` -- read-modify-write helpers for
  ``config/config.json`` using an **atomic** temp-file + :func:`os.replace`
  swap (matching ``living_world/persistence.py``). Only the touched keys are
  changed; every other config key is preserved.
* :class:`SettingsScreen` -- an interactive list of adjustable settings rendered
  on the 64x64 matrix and driven by the controller. ``UP/DOWN`` move between
  settings, ``LEFT/RIGHT`` adjust the focused value (clamped to a sane range),
  ``A`` confirms/persists, ``B`` goes back (also persisting any pending change).

Adjustable settings this phase (§6.1):

==============  =============================  ===============  =====================
Setting         config.json key                Range / step     Apply
==============  =============================  ===============  =====================
Brightness      ``matrix_hardware.brightness`` 10-100, step 5   Live: ``matrix.brightness`` + persist
Demo duration   ``display_duration``           10-300 s, step 5 Persist (next cycle)
==============  =============================  ===============  =====================

The screen is rendered by the same PIL + ``matrix.SetImage`` pattern as every
other display module, reusing the ``_fonts`` 5x7 helpers and ``_utils`` color
helpers; it honors ``should_stop()`` so process shutdown never hangs.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from PIL import Image, ImageDraw

from src.display import _fonts
from src.display._shared import should_stop
from src.display._utils import _scale_color
from src.input import Button, EventType, wants_quit

logger = logging.getLogger(__name__)

# Project root -> config/config.json (canonical, same path main.load_config uses).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config", "config.json")

SIZE = 64

# Colors
BG_COLOR = (0, 0, 0)
TITLE_COLOR = (120, 200, 255)
HILITE_BG = (30, 60, 110)
TEXT_BRIGHT = (255, 255, 255)
TEXT_DIM = (120, 120, 130)
VALUE_COLOR = (120, 255, 160)
ARROW_COLOR = (200, 200, 80)


# ---------------------------------------------------------------------------
# Config read / atomic write helpers (§6.3)
# ---------------------------------------------------------------------------
def load_settings(config_path: str = DEFAULT_CONFIG_PATH) -> dict:
    """Read and parse ``config.json``.

    Returns an empty dict if the file is missing or corrupt (callers then fall
    back to defaults); never raises, mirroring ``main.load_config``'s tolerance.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load settings from %s: %s", config_path, exc)
        return {}


def save_settings(config_path: str, updates: dict) -> bool:
    """Atomically merge ``updates`` into ``config.json`` (read-modify-write).

    Performs a deep merge for nested dict keys (e.g. ``matrix_hardware``) so
    only the specific leaf keys are changed and the rest of the config block is
    preserved. The write is atomic: serialize to a sibling ``*.tmp`` file then
    :func:`os.replace` it over the target, so a crash mid-write cannot corrupt
    the config.

    :param config_path: path to ``config.json``.
    :param updates: mapping of keys to set; nested dicts are merged recursively.
    :returns: ``True`` on success, ``False`` on any I/O error.
    """
    config = load_settings(config_path)

    def _merge(dst: dict, src: dict) -> None:
        for key, value in src.items():
            if isinstance(value, dict) and isinstance(dst.get(key), dict):
                _merge(dst[key], value)
            else:
                dst[key] = value

    _merge(config, updates)

    config_dir = os.path.dirname(config_path) or "."
    tmp_path = None
    try:
        os.makedirs(config_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=config_dir, suffix=".tmp", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(config, tmp, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, config_path)
        logger.info("Persisted settings to %s: %s", config_path, list(updates))
        return True
    except OSError as exc:
        logger.error("Failed to persist settings to %s: %s", config_path, exc)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


# ---------------------------------------------------------------------------
# Setting model -- one adjustable numeric value
# ---------------------------------------------------------------------------
@dataclass
class _Setting:
    """A single adjustable numeric setting.

    :param label: short uppercase label shown on the row.
    :param value: current value (int).
    :param minimum: inclusive lower clamp.
    :param maximum: inclusive upper clamp.
    :param step: increment/decrement applied by LEFT/RIGHT.
    :param suffix: optional unit suffix appended to the displayed value (e.g. "S").
    :param apply: optional callback invoked with the new value on every change
        (used for live brightness preview).
    """

    label: str
    value: int
    minimum: int
    maximum: int
    step: int
    suffix: str = ""
    apply: Optional[Callable[[int], None]] = None

    def adjust(self, direction: int) -> bool:
        """Increment (``+1``) or decrement (``-1``) by ``step``, clamped.

        :returns: ``True`` if the value actually changed.
        """
        new_value = self.value + direction * self.step
        new_value = max(self.minimum, min(self.maximum, new_value))
        if new_value != self.value:
            self.value = new_value
            if self.apply is not None:
                self.apply(new_value)
            return True
        return False

    def display_value(self) -> str:
        return f"{self.value}{self.suffix}"


# Clamp ranges / steps (§6.1)
BRIGHTNESS_MIN, BRIGHTNESS_MAX, BRIGHTNESS_STEP = 10, 100, 5
DURATION_MIN, DURATION_MAX, DURATION_STEP = 10, 300, 5


class SettingsScreen:
    """Interactive on-matrix settings editor.

    Constructed with the shared ``matrix`` (for live brightness preview and
    rendering) and the path to ``config.json``. :meth:`run` loops until the user
    backs out (``B`` / quit gesture / ``START``), persisting changes, then
    returns control to the caller (the :class:`MenuSystem`).

    :param matrix: shared matrix; brightness changes are applied to
        ``matrix.brightness`` immediately for live preview.
    :param config: current parsed config dict (used to seed initial values).
    :param config_path: path to ``config.json`` for persistence.
    :param fps: render/poll frame rate; ``0`` disables sleeping (tests).
    """

    def __init__(self, matrix, config: Optional[dict] = None,
                 config_path: str = DEFAULT_CONFIG_PATH, fps: float = 30.0):
        self.matrix = matrix
        self.config = config or {}
        self.config_path = config_path
        self._frame_dt = 1.0 / fps if fps > 0 else 0.0
        self.selected = 0
        self._dirty = False
        self.settings: List[_Setting] = self._build_settings()

    # ----- setting construction ---------------------------------------------
    def _build_settings(self) -> List[_Setting]:
        """Build the editable-setting list seeded from the current config."""
        hw = self.config.get("matrix_hardware", {}) if self.config else {}
        brightness = int(hw.get("brightness", 80))
        brightness = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, brightness))

        duration = int(self.config.get("display_duration", 60)) if self.config else 60
        duration = max(DURATION_MIN, min(DURATION_MAX, duration))

        return [
            _Setting(
                "BRIGHT", brightness, BRIGHTNESS_MIN, BRIGHTNESS_MAX,
                BRIGHTNESS_STEP, apply=self._apply_brightness,
            ),
            _Setting(
                "DEMO", duration, DURATION_MIN, DURATION_MAX,
                DURATION_STEP, suffix="S",
            ),
        ]

    def _apply_brightness(self, value: int) -> None:
        """Apply brightness to the live matrix immediately (best-effort)."""
        try:
            self.matrix.brightness = value
        except Exception:  # noqa: BLE001 - matrix may not support it
            logger.debug("Matrix does not support live brightness", exc_info=True)

    # ----- persistence -------------------------------------------------------
    def _persist(self) -> None:
        """Write the current setting values back to ``config.json`` atomically.

        Only writes when something actually changed (``self._dirty``) to avoid
        needless config churn. Updates the in-memory ``self.config`` too so the
        owning menu/state machine sees the new values without a reload.
        """
        if not self._dirty:
            return
        by_label = {s.label: s for s in self.settings}
        updates = {
            "display_duration": by_label["DEMO"].value,
            "matrix_hardware": {"brightness": by_label["BRIGHT"].value},
        }
        save_settings(self.config_path, updates)
        # Reflect into the in-memory snapshot.
        self.config.setdefault("matrix_hardware", {})
        self.config["matrix_hardware"]["brightness"] = by_label["BRIGHT"].value
        self.config["display_duration"] = by_label["DEMO"].value
        self._dirty = False

    # ----- rendering ---------------------------------------------------------
    def _render(self) -> None:
        """Draw the settings list to a PIL image and push it via SetImage."""
        img = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(img)

        title = "SETTINGS"
        tw = _fonts._text_width(title, scale=1)
        _fonts._draw_text(draw, title, (SIZE - tw) // 2, 2, TITLE_COLOR)
        draw.line([(2, 11), (SIZE - 3, 11)], fill=_scale_color(TITLE_COLOR, 0.4))

        # Each setting occupies a 12px-tall row starting at y=16.
        row_h = 13
        top = 16
        for i, setting in enumerate(self.settings):
            y = top + i * row_h
            selected = i == self.selected
            if selected:
                draw.rectangle([1, y - 1, SIZE - 2, y + 9], fill=HILITE_BG)
            label_color = TEXT_BRIGHT if selected else TEXT_DIM
            _fonts._draw_text(draw, setting.label, 3, y, label_color)

            value_text = setting.display_value()
            vw = _fonts._text_width(value_text, scale=1)
            value_color = VALUE_COLOR if selected else _scale_color(VALUE_COLOR, 0.5)
            # Right-aligned value, leaving room for the left/right arrows.
            vx = SIZE - vw - 8
            _fonts._draw_text(draw, value_text, vx, y, value_color)

            if selected:
                # Left/right adjust arrows flanking the value.
                _draw_left_arrow(draw, vx - 6, y + 1, ARROW_COLOR)
                _draw_right_arrow(draw, SIZE - 6, y + 1, ARROW_COLOR)

        hint = "B BACK"
        hw_ = _fonts._text_width(hint, scale=1)
        _fonts._draw_text(draw, hint, (SIZE - hw_) // 2, SIZE - 9,
                          _scale_color(TEXT_DIM, 0.8))

        self.matrix.SetImage(img)

    # ----- main loop ---------------------------------------------------------
    def run(self) -> None:
        """Loop until the user backs out; persist on exit.

        Controls:

        * ``UP`` / ``DOWN`` (PRESSED or REPEAT) -- move the selection.
        * ``LEFT`` / ``RIGHT`` (PRESSED or REPEAT) -- adjust the focused value.
        * ``A`` -- persist immediately (stay on the screen).
        * ``B`` / ``START`` / quit gesture -- persist pending changes and return.

        Honors ``should_stop()`` for shutdown safety.
        """
        self._render()
        while True:
            if should_stop():
                self._persist()
                return

            events = self._poll()
            changed = False
            exit_requested = False

            for event in events:
                if event.type not in (EventType.PRESSED, EventType.REPEAT):
                    continue
                btn = event.button
                if btn is Button.UP:
                    self.selected = (self.selected - 1) % len(self.settings)
                    changed = True
                elif btn is Button.DOWN:
                    self.selected = (self.selected + 1) % len(self.settings)
                    changed = True
                elif btn is Button.LEFT:
                    if self.settings[self.selected].adjust(-1):
                        self._dirty = True
                    changed = True
                elif btn is Button.RIGHT:
                    if self.settings[self.selected].adjust(+1):
                        self._dirty = True
                    changed = True
                elif event.type is EventType.PRESSED and btn is Button.A:
                    self._persist()
                    changed = True
                elif event.type is EventType.PRESSED and btn in (Button.B, Button.START):
                    exit_requested = True
                    break

            if exit_requested:
                self._persist()
                return

            if self._controller is not None and wants_quit(self._controller):
                self._persist()
                return

            if changed:
                self._render()

            if self._frame_dt:
                time.sleep(self._frame_dt)

    # The controller is injected by MenuSystem just before run(); kept as a
    # simple attribute so the loop can poll it and check the quit gesture.
    _controller: Any = None

    def _poll(self):
        if self._controller is None:
            return []
        return self._controller.poll_events()

    def attach_controller(self, controller) -> None:
        """Set the controller this screen polls in :meth:`run`."""
        self._controller = controller


# ---------------------------------------------------------------------------
# Tiny arrow glyphs (the 5x7 font has no triangle glyphs)
# ---------------------------------------------------------------------------
def _draw_left_arrow(draw, x, y, color) -> None:
    """Draw a small left-pointing triangle (~5px) at (x, y)."""
    draw.polygon([(x + 4, y), (x + 4, y + 6), (x, y + 3)], fill=color)


def _draw_right_arrow(draw, x, y, color) -> None:
    """Draw a small right-pointing triangle (~5px) at (x, y)."""
    draw.polygon([(x, y), (x, y + 6), (x + 4, y + 3)], fill=color)
