#!/usr/bin/env python3
"""
Data-driven menu engine + renderer + navigation (CONTROLLER_OVERHAUL.md §4.3/§4.4).

:class:`MenuSystem` implements the :class:`src.app_state.MenuController` protocol
(``run(self, matrix, controller) -> MenuResult``) so it is a drop-in replacement
for ``PlaceholderMenu``. It renders the data-defined :class:`src.menu.menu_data.Menu`
screens on the 64x64 matrix and navigates them with the gamepad.

Rendering (§4.3)
----------------
* Title row at the top (centered, 5x7 font), then a vertical list of items.
* The **selected** row is highlighted with a filled accent rectangle and bright
  text; non-selected rows are dim. Disabled items render greyed and are skipped
  when moving the cursor / cannot be activated.
* A **scrolling viewport** shows only ``VISIBLE_ROWS`` items at a time; when the
  list is longer, up/down arrow glyphs indicate off-screen items and the window
  follows the selection.
* Everything is drawn to a single ``PIL.Image`` then pushed with
  ``matrix.SetImage`` -- the same pattern every existing display module uses.

Navigation (§4.4)
------------------
* ``UP`` / ``DOWN`` (PRESSED **and** REPEAT, for smooth held auto-scroll) move
  the selection, wrapping around and skipping disabled rows.
* ``A`` activates the selected item.
* ``B`` pops one level off the navigation **stack**; at the root it returns
  ``MenuResult.resume()`` (back to IDLE).
* ``START`` resumes (back to IDLE) from anywhere.
* The quit gesture (``wants_quit`` / ``controller.is_quitting()``) returns
  ``MenuResult.quit()``.

Settings handling -- INLINE
---------------------------
Selecting **Settings** is handled **inline**: the :class:`SettingsScreen` is run
as a pushed screen, the user adjusts values, and on back we pop straight back to
the Main Menu without ever leaving :meth:`run`. We therefore never return
``MenuResult.open_settings()`` to the state machine -- only ``launch_game`` /
``resume`` / ``quit`` are returned. This keeps the flow seamless (the state
machine already treats OPEN_SETTINGS as "stay in MENU", so either approach works;
inline is the cleaner UX).
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from PIL import Image, ImageDraw

from src.app_state import MenuResult
from src.display import _fonts
from src.display._shared import should_stop
from src.display._utils import _scale_color
from src.input import Button, EventType, wants_quit
from src.menu.menu_data import (
    ItemAction,
    Menu,
    build_main_menu,
    build_menu_registry,
)
from src.menu.carousel_screen import CarouselScreen
from src.menu.controller_screen import ControllerScreen
from src.menu.settings_screen import DEFAULT_CONFIG_PATH, SettingsScreen
from src.menu.update_screen import run_force_update
from src.version import get_version

logger = logging.getLogger(__name__)

SIZE = 64

# Layout constants (5x7 font: glyph 5px + 1px spacing = 6px/char; ~10 chars/row).
TITLE_Y = 2
LIST_TOP = 13          # first item row y
ROW_HEIGHT = 9         # 7px glyph + 2px gap
VISIBLE_ROWS = 5       # rows that fit below the title (13 + 5*9 = 58 < 64)

# Colors
BG_COLOR = (0, 0, 0)
TITLE_COLOR = (120, 200, 255)
HILITE_BG = (30, 70, 120)
TEXT_SELECTED = (255, 255, 255)
TEXT_NORMAL = (150, 150, 160)
TEXT_DISABLED = (70, 70, 75)
ARROW_COLOR = (160, 160, 90)
VERSION_COLOR = (50, 50, 60)
ABOUT_TITLE_COLOR = (120, 200, 255)
ABOUT_TEXT_COLOR = (180, 180, 190)
ABOUT_DIM_COLOR = (100, 100, 110)


class MenuSystem:
    """Render + navigate the data-driven menu hierarchy.

    :param config: parsed ``config.json`` dict (seeds the games list + settings).
    :param config_path: path to ``config.json`` for the Settings screen to
        persist to (defaults to the canonical ``config/config.json``).
    :param fps: render/poll frame rate; ``0`` disables sleeping (used in tests
        for deterministic, instant loops).
    :param playable: optional override of the playable-game set (tests); defaults
        to :data:`src.app_state.PLAYABLE_GAMES` via the data builders.
    """

    def __init__(self, config: Optional[dict] = None,
                 config_path: str = DEFAULT_CONFIG_PATH,
                 fps: float = 30.0, playable=None):
        self._config = config or {}
        self._config_path = config_path
        self._frame_dt = 1.0 / fps if fps > 0 else 0.0
        self._playable = playable
        self._fps = fps

        self._registry = build_menu_registry(playable)
        # Navigation stack of (Menu, selected_index). The bottom is always the
        # freshly-built Main Menu.
        self._stack: List[list] = []

        # Cache version string once (avoid calling git every frame).
        self._version = get_version()

    # ----- state-machine integration ----------------------------------------
    def set_config(self, config: dict) -> None:
        """Refresh our config snapshot (called by the state machine each cycle)."""
        self._config = config or {}

    def run(self, matrix, controller) -> MenuResult:
        """Render + navigate until a terminal action; return a :class:`MenuResult`.

        Implements the :class:`src.app_state.MenuController` protocol. Settings is
        handled inline (see module docstring), so only ``launch_game`` /
        ``resume`` / ``quit`` are ever returned.
        """
        # Rebuild from a fresh Main Menu each entry so cursor + games list start
        # clean and reflect any config change.
        self._registry = build_menu_registry(self._playable)
        self._stack = [[build_main_menu(), 0]]

        # The user pressed START to open the menu, so START is likely still held.
        # We must ignore START until it has been released at least once, otherwise
        # the menu immediately closes on the first frame (wants_quit sees START
        # held and returns True, or _handle_events sees a START PRESSED edge).
        # In test mode (fps=0), START is never physically held so arm immediately.
        self._start_armed = (self._frame_dt == 0.0)

        self._render(matrix)
        while True:
            if should_stop():
                # Process shutdown: resume so the state machine returns to IDLE
                # and the outer loop exits cleanly.
                return MenuResult.resume()

            if controller.is_quitting():
                return MenuResult.quit()

            result = self._handle_events(matrix, controller)
            if result is not None:
                return result

            # Only check wants_quit after START has been released and re-pressed.
            if self._start_armed and wants_quit(controller):
                # Quit gesture from the menu resumes to idle (mirrors in-game UX
                # where the combo backs out one level).
                return MenuResult.resume()

            if self._frame_dt:
                time.sleep(self._frame_dt)

    # ----- event handling ----------------------------------------------------
    def _handle_events(self, matrix, controller) -> Optional[MenuResult]:
        """Consume one poll batch; return a MenuResult if a terminal action fired.

        Returns ``None`` to keep looping.
        """
        dirty = False
        for event in controller.poll_events():
            btn = event.button
            is_press = event.type is EventType.PRESSED
            is_release = event.type is EventType.RELEASED
            is_repeat = event.type is EventType.REPEAT

            # Track START release so we know when it's safe to accept START
            # as a "close menu" action. Without this, the START press that
            # *opened* the menu would immediately close it.
            if btn is Button.START and is_release:
                self._start_armed = True
                continue

            # UP/DOWN: honor PRESSED and REPEAT for smooth held auto-scroll.
            if btn is Button.UP and (is_press or is_repeat):
                self._move_selection(-1)
                dirty = True
            elif btn is Button.DOWN and (is_press or is_repeat):
                self._move_selection(+1)
                dirty = True
            elif is_press and btn is Button.A:
                result = self._activate(matrix, controller)
                if result is not None:
                    return result
                # Activation may have changed the screen (push/pop).
                dirty = True
            elif is_press and btn is Button.B:
                if self._pop():
                    dirty = True
                else:
                    # B at the root -> resume to idle.
                    return MenuResult.resume()
            elif is_press and btn is Button.START and self._start_armed:
                return MenuResult.resume()

        if dirty:
            self._render(matrix)
        return None

    # ----- stack / selection helpers -----------------------------------------
    @property
    def _current(self) -> Menu:
        return self._stack[-1][0]

    @property
    def _selected(self) -> int:
        return self._stack[-1][1]

    @_selected.setter
    def _selected(self, value: int) -> None:
        self._stack[-1][1] = value

    def _move_selection(self, direction: int) -> None:
        """Move the cursor by ``direction`` (+1 down / -1 up), wrapping and
        skipping disabled items so the cursor never lands on a greyed row."""
        items = self._current.items
        n = len(items)
        if n == 0:
            return
        idx = self._selected
        for _ in range(n):
            idx = (idx + direction) % n
            if items[idx].enabled:
                self._selected = idx
                return
        # All disabled (shouldn't happen) -- leave selection unchanged.

    def _push(self, menu: Menu) -> None:
        """Push a submenu onto the stack with a fresh selection at its first
        enabled item."""
        self._stack.append([menu, 0])
        # Snap to the first enabled item.
        for i, item in enumerate(menu.items):
            if item.enabled:
                self._selected = i
                break

    def _pop(self) -> bool:
        """Pop one level; return ``True`` if a level was popped, ``False`` if
        already at the root (caller then resumes to idle)."""
        if len(self._stack) > 1:
            self._stack.pop()
            return True
        return False

    # ----- activation --------------------------------------------------------
    def _activate(self, matrix, controller) -> Optional[MenuResult]:
        """Activate the currently-selected item.

        Returns a terminal :class:`MenuResult` (launch/resume/launch_demo) when
        applicable, otherwise ``None`` after mutating the navigation stack
        (push/pop) or running an inline screen.
        """
        items = self._current.items
        if not items:
            return None
        item = items[self._selected]
        if not item.enabled:
            return None

        action = item.action
        if action is ItemAction.LAUNCH_GAME:
            return MenuResult.launch_game(item.payload)
        if action is ItemAction.LAUNCH_DEMO:
            return MenuResult.launch_demo(item.payload)
        if action is ItemAction.RESUME_IDLE:
            return MenuResult.resume()
        if action is ItemAction.BACK:
            if not self._pop():
                return MenuResult.resume()
            return None
        if action is ItemAction.OPEN_SUBMENU:
            submenu = self._registry.get(item.payload)
            if submenu is not None:
                self._push(submenu)
            return None
        if action is ItemAction.OPEN_SETTINGS:
            self._open_settings(matrix, controller)
            # After settings, re-render the menu we returned to.
            self._render(matrix)
            return None
        if action is ItemAction.OPEN_CAROUSEL:
            self._open_carousel(matrix, controller)
            # After carousel, re-render the menu we returned to.
            self._render(matrix)
            return None
        if action is ItemAction.OPEN_CONTROLS:
            self._open_controls(matrix, controller)
            # After controls, re-render the menu we returned to.
            self._render(matrix)
            return None
        if action is ItemAction.OPEN_ABOUT:
            self._open_about(matrix, controller)
            self._render(matrix)
            return None
        if action is ItemAction.FORCE_UPDATE:
            run_force_update(matrix)
            self._render(matrix)
            return None
        return None

    def _open_settings(self, matrix, controller) -> None:
        """Run the inline Settings screen, then return here (no state-machine hop).

        The screen persists changes to ``config.json`` atomically and applies
        brightness live; we refresh our in-memory config from it so a subsequent
        re-entry shows the updated values.
        """
        screen = SettingsScreen(
            matrix, config=self._config, config_path=self._config_path,
            fps=self._fps,
        )
        screen.attach_controller(controller)
        screen.run()
        # Adopt any changes the screen wrote into the shared config dict.
        self._config = screen.config

    def _open_carousel(self, matrix, controller) -> None:
        """Run the inline Carousel config screen, then return here.

        The screen persists toggled enabled states to ``config.json`` atomically;
        we refresh our in-memory config from it so the carousel picks up changes.
        """
        screen = CarouselScreen(
            matrix, config=self._config, config_path=self._config_path,
            fps=self._fps,
        )
        screen.attach_controller(controller)
        screen.run()
        # Adopt any changes the screen wrote into the shared config dict.
        self._config = screen.config

    def _open_controls(self, matrix, controller) -> None:
        """Run the inline Controller mapping screen, then return here.

        The screen persists button remapping and Y-axis inversion to
        ``config/controller.json`` atomically and reloads the mapping into
        the live controller so changes take effect immediately.
        """
        from src.input.controller import CONTROLLER_CONFIG_PATH as ctrl_path

        screen = ControllerScreen(
            matrix, controller=controller, config_path=ctrl_path,
            fps=self._fps,
        )
        screen.run()

    def _open_about(self, matrix, controller) -> None:
        """Run the inline About screen showing project info.

        Displays: LED MATRIX title, version hash, controller status.
        Press B to return to the menu.
        """
        while True:
            if should_stop():
                return

            # Render the about screen.
            img = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
            draw = ImageDraw.Draw(img)

            # Title: "LED MATRIX" centered.
            title = "LED MATRIX"
            tw = _fonts._text_width(title, scale=1)
            _fonts._draw_text(draw, title, max(0, (SIZE - tw) // 2), 8,
                              ABOUT_TITLE_COLOR)

            # Version line.
            ver_line = f"v: {self._version}"
            vw = _fonts._text_width(ver_line, scale=1)
            _fonts._draw_text(draw, ver_line, max(0, (SIZE - vw) // 2), 22,
                              ABOUT_TEXT_COLOR)

            # Controller status.
            connected = controller.is_connected() if hasattr(controller, 'is_connected') else False
            ctrl_text = "CONNECTED" if connected else "NO CTRL"
            cw = _fonts._text_width(ctrl_text, scale=1)
            ctrl_color = (80, 200, 80) if connected else (200, 80, 80)
            _fonts._draw_text(draw, ctrl_text, max(0, (SIZE - cw) // 2), 36,
                              ctrl_color)

            # "B: BACK" hint.
            hint = "B: BACK"
            hw = _fonts._text_width(hint, scale=1)
            _fonts._draw_text(draw, hint, max(0, (SIZE - hw) // 2), 52,
                              ABOUT_DIM_COLOR)

            matrix.SetImage(img)

            # Poll for B to exit.
            for event in controller.poll_events():
                if event.type is EventType.PRESSED and event.button is Button.B:
                    return
                if event.type is EventType.PRESSED and event.button is Button.START:
                    return

            if self._frame_dt:
                time.sleep(self._frame_dt)

    # ----- rendering (§4.3) ---------------------------------------------------
    def _render(self, matrix) -> None:
        """Draw the current menu (title + scrolling item list) and SetImage it."""
        menu = self._current
        img = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Title (centered).
        title = menu.title
        tw = _fonts._text_width(title, scale=1)
        _fonts._draw_text(draw, title, max(0, (SIZE - tw) // 2), TITLE_Y, TITLE_COLOR)

        items = menu.items
        selected = self._selected
        first, last = self._viewport(len(items), selected)

        for row, idx in enumerate(range(first, last)):
            item = items[idx]
            y = LIST_TOP + row * ROW_HEIGHT
            is_sel = idx == selected
            if is_sel:
                draw.rectangle([0, y - 1, SIZE - 1, y + 7], fill=HILITE_BG)

            if not item.enabled:
                color = TEXT_DISABLED
            elif is_sel:
                color = TEXT_SELECTED
            else:
                color = TEXT_NORMAL
            _fonts._draw_text(draw, item.label, 3, y, color)

        # Scroll indicators when items extend beyond the viewport.
        if first > 0:
            _draw_up_arrow(draw, SIZE - 6, LIST_TOP - 1, ARROW_COLOR)
        if last < len(items):
            _draw_down_arrow(draw, SIZE - 6, SIZE - 6, ARROW_COLOR)

        # Version string at the bottom of the main menu (always visible, dim).
        ver_text = f"v:{self._version}"
        vw = _fonts._text_width(ver_text, scale=1)
        _fonts._draw_text(draw, ver_text, max(0, (SIZE - vw) // 2), SIZE - 7,
                          VERSION_COLOR)

        matrix.SetImage(img)

    @staticmethod
    def _viewport(count: int, selected: int) -> tuple:
        """Return ``(first, last)`` item indices to display so ``selected`` is
        always within the visible window of :data:`VISIBLE_ROWS` rows."""
        if count <= VISIBLE_ROWS:
            return 0, count
        first = selected - VISIBLE_ROWS // 2
        first = max(0, min(first, count - VISIBLE_ROWS))
        return first, first + VISIBLE_ROWS


# ---------------------------------------------------------------------------
# Small arrow glyphs for scroll indicators
# ---------------------------------------------------------------------------
def _draw_up_arrow(draw, x, y, color) -> None:
    """Draw a small upward triangle (~5px wide) at (x, y)."""
    draw.polygon([(x, y + 4), (x + 4, y + 4), (x + 2, y)], fill=color)


def _draw_down_arrow(draw, x, y, color) -> None:
    """Draw a small downward triangle (~5px wide) at (x, y)."""
    draw.polygon([(x, y), (x + 4, y), (x + 2, y + 4)], fill=color)
