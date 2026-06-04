#!/usr/bin/env python3
"""
On-device Controller Mapping screen.

Allows the user to remap physical joystick buttons (A, B, START, SELECT),
toggle Y-axis inversion, and save the mapping to ``config/controller.json``
atomically — all driven live on the 64x64 matrix via the controller itself.

Screen layout::

    CONTROLLER SETUP
    ─────────────────
    > REMAP A        [btn 2]
      REMAP B        [btn 3]
      REMAP START    [btn 9]
      REMAP SELECT   [btn 6]
      INVERT Y       [ON/OFF]
      SAVE & BACK

Navigation:
- UP/DOWN to select an item
- A on a REMAP item → enters "listening" mode (captures raw button press)
- A on INVERT Y → toggles the value
- A on SAVE & BACK → persists and returns
- B → save and go back
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

from PIL import Image, ImageDraw

from src.display import _fonts
from src.display._shared import should_stop
from src.display._utils import _scale_color
from src.input import Button, EventType, wants_quit
from src.input.controller import (
    ButtonMapping,
    CONTROLLER_CONFIG_PATH,
    load_mapping,
    save_mapping,
)

logger = logging.getLogger(__name__)

SIZE = 64

# Colors
BG_COLOR = (0, 0, 0)
TITLE_COLOR = (120, 200, 255)
HILITE_BG = (30, 60, 110)
TEXT_BRIGHT = (255, 255, 255)
TEXT_DIM = (120, 120, 130)
VALUE_COLOR = (120, 255, 160)
LISTEN_BG = (80, 20, 20)
LISTEN_TEXT = (255, 200, 80)
TIMEOUT_COLOR = (255, 60, 60)
SAVE_COLOR = (80, 255, 120)

# The logical buttons we allow remapping (in display order).
_REMAP_BUTTONS = [Button.A, Button.B, Button.START, Button.SELECT]


class ControllerScreen:
    """Interactive on-matrix controller mapping editor.

    :param matrix: shared matrix for rendering.
    :param controller: the Controller instance (used for polling and raw capture).
    :param config_path: path to ``controller.json`` for persistence.
    :param fps: render/poll frame rate; ``0`` disables sleeping (tests).
    """

    def __init__(
        self,
        matrix,
        controller=None,
        config_path: str = CONTROLLER_CONFIG_PATH,
        fps: float = 30.0,
    ):
        self.matrix = matrix
        self._controller = controller
        self.config_path = config_path
        self._frame_dt = 1.0 / fps if fps > 0 else 0.0
        self.selected = 0
        self._dirty = False

        # Load the current mapping as our working copy.
        self._mapping = load_mapping(config_path)
        # Build a mutable reverse map: logical Button -> physical index
        self._button_indices: dict[Button, int] = {}
        for phys_idx, logical in self._mapping.buttons.items():
            self._button_indices[logical] = phys_idx
        self._invert_y = self._mapping.invert_y

        # Menu items: 4 remap + invert_y + save&back
        self._items: List[str] = [
            f"REMAP {b.value}" for b in _REMAP_BUTTONS
        ] + ["INVERT Y", "SAVE+BACK"]

    @property
    def _num_items(self) -> int:
        return len(self._items)

    # ----- controller injection -----------------------------------------------
    def attach_controller(self, controller) -> None:
        """Set the controller this screen polls in :meth:`run`."""
        self._controller = controller

    # ----- persistence --------------------------------------------------------
    def _build_mapping(self) -> ButtonMapping:
        """Build a ButtonMapping from the current working state."""
        buttons: dict[int, Button] = {}
        for logical, phys_idx in self._button_indices.items():
            buttons[phys_idx] = logical
        return ButtonMapping(
            buttons=buttons,
            hat_index=self._mapping.hat_index,
            axis_x=self._mapping.axis_x,
            axis_y=self._mapping.axis_y,
            invert_y=self._invert_y,
            deadzone=self._mapping.deadzone,
        )

    def _save(self) -> None:
        """Persist the current mapping atomically and reload into the controller."""
        if not self._dirty:
            return
        new_mapping = self._build_mapping()
        save_mapping(new_mapping, self.config_path)
        # Reload into the live controller so changes take effect immediately.
        if self._controller is not None and hasattr(self._controller, "reload_mapping"):
            self._controller.reload_mapping(new_mapping)
        self._dirty = False

    # ----- rendering ----------------------------------------------------------
    def _value_for_item(self, idx: int) -> str:
        """Return the display value string for item at ``idx``."""
        if idx < len(_REMAP_BUTTONS):
            logical = _REMAP_BUTTONS[idx]
            phys = self._button_indices.get(logical)
            return f"btn {phys}" if phys is not None else "---"
        elif idx == len(_REMAP_BUTTONS):
            # INVERT Y
            return "ON" if self._invert_y else "OFF"
        else:
            # SAVE & BACK
            return ""

    def _render(self) -> None:
        """Draw the controller mapping list to the matrix."""
        img = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(img)

        title = "CONTROLS"
        tw = _fonts._text_width(title, scale=1)
        _fonts._draw_text(draw, title, (SIZE - tw) // 2, 2, TITLE_COLOR)
        draw.line([(2, 11), (SIZE - 3, 11)], fill=_scale_color(TITLE_COLOR, 0.4))

        row_h = 9
        top = 14
        for i, label in enumerate(self._items):
            y = top + i * row_h
            selected = i == self.selected
            if selected:
                draw.rectangle([1, y - 1, SIZE - 2, y + 7], fill=HILITE_BG)
            label_color = TEXT_BRIGHT if selected else TEXT_DIM

            # Truncate label to fit with value
            display_label = label[:8]
            _fonts._draw_text(draw, display_label, 3, y, label_color)

            value = self._value_for_item(i)
            if value:
                vw = _fonts._text_width(value, scale=1)
                value_color = VALUE_COLOR if selected else _scale_color(VALUE_COLOR, 0.5)
                _fonts._draw_text(draw, value, SIZE - vw - 3, y, value_color)

        self.matrix.SetImage(img)

    def _render_listening(self, logical_name: str) -> None:
        """Draw the 'listening for button press' prompt."""
        img = Image.new("RGB", (SIZE, SIZE), LISTEN_BG)
        draw = ImageDraw.Draw(img)

        line1 = "PRESS BTN"
        tw1 = _fonts._text_width(line1, scale=1)
        _fonts._draw_text(draw, line1, (SIZE - tw1) // 2, 20, LISTEN_TEXT)

        line2 = f"FOR {logical_name}"
        tw2 = _fonts._text_width(line2, scale=1)
        _fonts._draw_text(draw, line2, (SIZE - tw2) // 2, 32, TEXT_BRIGHT)

        line3 = "10S TIMEOUT"
        tw3 = _fonts._text_width(line3, scale=1)
        _fonts._draw_text(draw, line3, (SIZE - tw3) // 2, 48, TEXT_DIM)

        self.matrix.SetImage(img)

    def _render_timeout(self) -> None:
        """Flash a timeout message briefly."""
        img = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(img)
        msg = "TIMEOUT"
        tw = _fonts._text_width(msg, scale=1)
        _fonts._draw_text(draw, msg, (SIZE - tw) // 2, 28, TIMEOUT_COLOR)
        self.matrix.SetImage(img)

    # ----- actions ------------------------------------------------------------
    def _do_remap(self, idx: int) -> None:
        """Enter listening mode for the button at ``idx``."""
        logical = _REMAP_BUTTONS[idx]
        self._render_listening(logical.value)

        if self._controller is None:
            return

        raw_btn = self._controller.capture_raw_button(timeout=10.0)
        if raw_btn is None:
            # Timeout
            self._render_timeout()
            time.sleep(1.0)
        else:
            # Remove old mapping for this logical button if it existed
            # (avoid two physical buttons mapping to the same logical)
            old_phys = self._button_indices.get(logical)
            if old_phys is not None and old_phys != raw_btn:
                pass  # just overwrite
            self._button_indices[logical] = raw_btn
            self._dirty = True

    def _do_toggle_invert(self) -> None:
        """Toggle Y-axis inversion."""
        self._invert_y = not self._invert_y
        self._dirty = True

    # ----- main loop ----------------------------------------------------------
    def run(self) -> None:
        """Loop until the user backs out; persist on exit.

        Controls:
        * UP/DOWN (PRESSED or REPEAT) -- move the selection.
        * A -- activate the selected item (remap / toggle / save).
        * B -- save and return.
        """
        self._render()
        while True:
            if should_stop():
                self._save()
                return

            events = self._poll()
            changed = False
            exit_requested = False

            for event in events:
                if event.type not in (EventType.PRESSED, EventType.REPEAT):
                    continue
                btn = event.button
                if btn is Button.UP:
                    self.selected = (self.selected - 1) % self._num_items
                    changed = True
                elif btn is Button.DOWN:
                    self.selected = (self.selected + 1) % self._num_items
                    changed = True
                elif event.type is EventType.PRESSED and btn is Button.A:
                    if self.selected < len(_REMAP_BUTTONS):
                        self._do_remap(self.selected)
                        changed = True
                    elif self.selected == len(_REMAP_BUTTONS):
                        self._do_toggle_invert()
                        changed = True
                    else:
                        # SAVE & BACK
                        exit_requested = True
                        break
                elif event.type is EventType.PRESSED and btn in (Button.B, Button.START):
                    exit_requested = True
                    break

            if exit_requested:
                self._save()
                return

            if self._controller is not None and wants_quit(self._controller):
                self._save()
                return

            if changed:
                self._render()

            if self._frame_dt:
                time.sleep(self._frame_dt)

    def _poll(self):
        if self._controller is None:
            return []
        return self._controller.poll_events()
