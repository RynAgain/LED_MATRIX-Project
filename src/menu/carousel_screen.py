#!/usr/bin/env python3
"""
Carousel configuration screen — toggle demo features on/off in the idle carousel.

Similar to :class:`src.menu.settings_screen.SettingsScreen`, this is an inline
screen pushed by the menu engine. It shows all features from
``config/config.json``'s ``sequence`` array with an ``[ON]`` / ``[OFF]`` toggle
indicator. Controls:

* ``UP`` / ``DOWN`` — move the selection.
* ``A`` — toggle the selected feature's ``enabled`` state.
* ``B`` — save changes and return to the menu.

Changes are persisted atomically (read-modify-write with :func:`os.replace`)
to ``config/config.json``. Only the ``enabled`` field of each sequence entry is
modified; everything else stays intact. The DemoCarousel picks up the changes
on its next config reload (which happens between cycles).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any, List, Optional

from PIL import Image, ImageDraw

from src.display import _fonts
from src.display._shared import should_stop
from src.display._utils import _scale_color
from src.input import Button, EventType, wants_quit

logger = logging.getLogger(__name__)

# Project root -> config/config.json (canonical path).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config", "config.json")

SIZE = 64

# Layout
TITLE_Y = 2
LIST_TOP = 13
ROW_HEIGHT = 9
VISIBLE_ROWS = 5

# Colors
BG_COLOR = (0, 0, 0)
TITLE_COLOR = (120, 200, 255)
HILITE_BG = (30, 70, 120)
TEXT_SELECTED = (255, 255, 255)
TEXT_NORMAL = (150, 150, 160)
ON_COLOR = (80, 255, 80)
OFF_COLOR = (255, 80, 80)
HINT_COLOR = (100, 100, 110)


def _get_playable_names():
    """Get the set of playable game names for type detection."""
    try:
        from src.app_state import PLAYABLE_GAMES
        return PLAYABLE_GAMES
    except ImportError:
        return set()


class CarouselScreen:
    """Interactive carousel configuration screen.

    Shows all features from the config's ``sequence`` array with ON/OFF toggles.
    A toggles, B saves and exits.

    :param matrix: shared matrix for rendering.
    :param config: current parsed config dict (used to seed the feature list).
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
        self._controller: Any = None

        # Build the feature list from the sequence + auto-discover missing features
        # from the registry so ALL available features appear in the carousel screen.
        self.features: List[dict] = []
        seen_names = set()
        for entry in self.config.get("sequence", []):
            name = entry.get("name", "unknown")
            self.features.append({
                "name": name,
                "enabled": bool(entry.get("enabled", False)),
            })
            seen_names.add(name)

        # Add any registered features not yet in the config sequence
        # (they appear at the end as disabled, so users can discover and toggle them)
        try:
            from src.feature_registry import FEATURE_MODULES
            for name in sorted(FEATURE_MODULES.keys()):
                if name not in seen_names and name != "youtube_stream":
                    self.features.append({
                        "name": name,
                        "enabled": False,
                    })
        except ImportError:
            pass

    def attach_controller(self, controller) -> None:
        """Set the controller this screen polls in :meth:`run`."""
        self._controller = controller

    def _poll(self):
        if self._controller is None:
            return []
        return self._controller.poll_events()

    # ----- persistence -------------------------------------------------------
    def _persist(self) -> None:
        """Write the toggled enabled states back to ``config.json`` atomically.

        Only writes when something actually changed (``self._dirty``). Performs a
        read-modify-write: reads the current file, updates only the ``enabled``
        field of each sequence entry (matched by index), then atomically replaces
        the file.
        """
        if not self._dirty:
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                full_config = json.loads(f.read().strip() or "{}")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            full_config = {}

        sequence = full_config.get("sequence", [])
        # Build a name->index map for existing entries
        existing_names = {entry.get("name"): i for i, entry in enumerate(sequence)}

        for feat in self.features:
            name = feat["name"]
            if name in existing_names:
                # Update existing entry
                sequence[existing_names[name]]["enabled"] = feat["enabled"]
            else:
                # Append new feature discovered from registry
                sequence.append({
                    "name": name,
                    "type": "game" if name in _get_playable_names() else "effect",
                    "enabled": feat["enabled"],
                })

        full_config["sequence"] = sequence

        config_dir = os.path.dirname(self.config_path) or "."
        tmp_path = None
        try:
            os.makedirs(config_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", dir=config_dir, suffix=".tmp", delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(full_config, tmp, indent=2)
                tmp_path = tmp.name
            os.replace(tmp_path, self.config_path)
            logger.info("Carousel config persisted to %s", self.config_path)
            self._dirty = False
            # Update in-memory config to reflect changes.
            self.config = full_config
        except OSError as exc:
            logger.error("Failed to persist carousel config: %s", exc)
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    # ----- rendering ---------------------------------------------------------
    def _render(self) -> None:
        """Draw the carousel feature list with ON/OFF indicators."""
        img = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Title
        title = "CAROUSEL"
        tw = _fonts._text_width(title, scale=1)
        _fonts._draw_text(draw, title, max(0, (SIZE - tw) // 2), TITLE_Y, TITLE_COLOR)

        items = self.features
        selected = self.selected
        first, last = self._viewport(len(items), selected)

        for row, idx in enumerate(range(first, last)):
            feat = items[idx]
            y = LIST_TOP + row * ROW_HEIGHT
            is_sel = idx == selected

            if is_sel:
                draw.rectangle([0, y - 1, SIZE - 1, y + 7], fill=HILITE_BG)

            # Feature name (truncated to ~7 chars to leave room for toggle).
            label = feat["name"].upper()[:7]
            color = TEXT_SELECTED if is_sel else TEXT_NORMAL
            _fonts._draw_text(draw, label, 2, y, color)

            # Toggle indicator on the right.
            if feat["enabled"]:
                tag = "ON"
                tag_color = ON_COLOR
            else:
                tag = "OFF"
                tag_color = OFF_COLOR
            tag_w = _fonts._text_width(tag, scale=1)
            _fonts._draw_text(draw, tag, SIZE - tag_w - 2, y, tag_color)

        # Scroll indicators
        if first > 0:
            _draw_up_arrow(draw, SIZE - 6, LIST_TOP - 1, (160, 160, 90))
        if last < len(items):
            _draw_down_arrow(draw, SIZE - 6, SIZE - 6, (160, 160, 90))

        # Hint at bottom
        hint = "A TOG B SAVE"
        hw_ = _fonts._text_width(hint, scale=1)
        _fonts._draw_text(draw, hint, max(0, (SIZE - hw_) // 2), SIZE - 9, HINT_COLOR)

        self.matrix.SetImage(img)

    @staticmethod
    def _viewport(count: int, selected: int) -> tuple:
        """Return (first, last) indices for the visible window."""
        if count <= VISIBLE_ROWS:
            return 0, count
        first = selected - VISIBLE_ROWS // 2
        first = max(0, min(first, count - VISIBLE_ROWS))
        return first, first + VISIBLE_ROWS

    # ----- main loop ---------------------------------------------------------
    def run(self) -> None:
        """Loop until the user presses B; persist on exit.

        Controls:
        * UP/DOWN (PRESSED or REPEAT) — move selection.
        * A (PRESSED) — toggle the selected feature's enabled state.
        * B / START / quit gesture — save and return.
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
                    self.selected = (self.selected - 1) % max(1, len(self.features))
                    changed = True
                elif btn is Button.DOWN:
                    self.selected = (self.selected + 1) % max(1, len(self.features))
                    changed = True
                elif event.type is EventType.PRESSED and btn is Button.A:
                    if self.features:
                        feat = self.features[self.selected]
                        feat["enabled"] = not feat["enabled"]
                        self._dirty = True
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


# ---------------------------------------------------------------------------
# Small arrow glyphs for scroll indicators
# ---------------------------------------------------------------------------
def _draw_up_arrow(draw, x, y, color) -> None:
    """Draw a small upward triangle (~5px wide) at (x, y)."""
    draw.polygon([(x, y + 4), (x + 4, y + 4), (x + 2, y)], fill=color)


def _draw_down_arrow(draw, x, y, color) -> None:
    """Draw a small downward triangle (~5px wide) at (x, y)."""
    draw.polygon([(x, y), (x + 4, y), (x + 2, y + 4)], fill=color)
