#!/usr/bin/env python3
"""
Data-driven menu definitions (CONTROLLER_OVERHAUL.md §4.1 / §4.2).

A menu is purely **data**: a :class:`Menu` (title + list of :class:`MenuItem`).
Each :class:`MenuItem` pairs a label with an :class:`ItemAction` and an optional
payload. The :class:`src.menu.menu_system.MenuSystem` engine renders and
navigates these structures generically -- it never hard-codes any specific menu.

**Extensibility contract:** adding a new game or menu entry should mean editing
*this* file only (e.g. extending :func:`build_games_menu`), never the engine in
``menu_system.py``. The playable-game list is derived from
:data:`src.app_state.PLAYABLE_GAMES` so converting a demo into a playable game
later is a one-line change there.

Menu hierarchy (§4.2)::

    Main Menu
      ├── Games      -> Games submenu
      ├── Demos      -> Demos submenu (watch any feature as a demo)
      ├── Lock Demo  -> Lock submenu (pin one demo for a chosen time)
      ├── Carousel   -> Carousel config screen (toggle demos on/off)
      ├── Settings   -> Settings screen (handled inline by the engine)
      └── Resume     -> back to the demo carousel (IDLE)

    Lock Demo submenu
      ├── Fire       -> duration menu (5 MIN ... 8 HOURS) -> launch_locked
      ├── ...        -> (all features from the registry)
      └── Back       -> pop to Main Menu

    Games submenu
      ├── Snake      -> launch_game("snake")
      ├── Tetris     -> launch_game("tetris")
      ├── Pong       -> launch_game("pong")
      └── Back       -> pop to Main Menu

    Demos submenu
      ├── Fire       -> launch_demo("fire")
      ├── Plasma     -> launch_demo("plasma")
      ├── ...        -> (all features from the registry)
      └── Back       -> pop to Main Menu
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ---------------------------------------------------------------------------
# Menu IDs -- stable string identifiers used as OPEN_SUBMENU payloads so the
# engine can look submenus up in the menu registry without circular references.
# ---------------------------------------------------------------------------
MENU_MAIN = "main"
MENU_GAMES = "games"
MENU_DEMOS = "demos"
MENU_LOCK = "lock"
MENU_LOCK_DURATION = "lock_duration"
MENU_SETTINGS = "settings"


class ItemAction(Enum):
    """What activating (pressing **A** on) a :class:`MenuItem` does.

    The engine maps each action to a concrete behavior:

    * ``LAUNCH_GAME``  -> return ``MenuResult.launch_game(payload)`` (enter game).
    * ``LAUNCH_DEMO``  -> return ``MenuResult.launch_demo(payload)`` (watch demo).
    * ``PICK_LOCK_DEMO`` -> push a duration menu for the chosen demo (payload).
    * ``LAUNCH_LOCKED``-> return ``MenuResult.launch_locked_demo(...)``; the
      payload is ``"<demo_name>:<seconds>"``.
    * ``OPEN_SUBMENU`` -> push the submenu identified by ``payload``.
    * ``OPEN_SETTINGS``-> push the inline Settings screen.
    * ``OPEN_CAROUSEL``-> push the inline Carousel config screen.
    * ``OPEN_CONTROLS``-> push the inline Controller mapping screen.
    * ``OPEN_ABOUT``   -> push the inline About screen.
    * ``FORCE_UPDATE`` -> trigger the led-matrix-updater service.
    * ``RESUME_IDLE``  -> return ``MenuResult.resume()`` (back to demo carousel).
    * ``BACK``         -> pop one level (or resume at the root).
    """

    LAUNCH_GAME = "LAUNCH_GAME"
    LAUNCH_DEMO = "LAUNCH_DEMO"
    PICK_LOCK_DEMO = "PICK_LOCK_DEMO"
    LAUNCH_LOCKED = "LAUNCH_LOCKED"
    OPEN_SUBMENU = "OPEN_SUBMENU"
    OPEN_SETTINGS = "OPEN_SETTINGS"
    OPEN_CAROUSEL = "OPEN_CAROUSEL"
    OPEN_CONTROLS = "OPEN_CONTROLS"
    OPEN_ABOUT = "OPEN_ABOUT"
    FORCE_UPDATE = "FORCE_UPDATE"
    RESUME_IDLE = "RESUME_IDLE"
    BACK = "BACK"


@dataclass
class MenuItem:
    """A single selectable row in a :class:`Menu`.

    :param label: display text (rendered uppercase via the 5x7 font).
    :param action: the :class:`ItemAction` performed when activated.
    :param payload: action-specific data -- a game name for ``LAUNCH_GAME`` or a
        submenu id for ``OPEN_SUBMENU``.
    :param enabled: ``False`` renders the row greyed-out and makes it
        non-selectable/non-activatable (e.g. telegraphing future games).
    """

    label: str
    action: ItemAction
    payload: Optional[str] = None
    enabled: bool = True


@dataclass
class Menu:
    """A complete menu screen: a title plus an ordered list of items."""

    id: str
    title: str
    items: List[MenuItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builders -- functions (not module-level constants) so the playable-game list
# is resolved fresh from PLAYABLE_GAMES every time, keeping the data current
# even if PLAYABLE_GAMES is extended at runtime/in tests.
# ---------------------------------------------------------------------------
# Pretty labels for the known playable games; unknown names fall back to the
# game name uppercased so adding a game to PLAYABLE_GAMES "just works".
_GAME_LABELS = {
    "snake": "SNAKE",
    "tetris": "TETRIS",
    "pong": "PONG",
    "starfox": "STARFOX",
    "barricade": "BARRICADE",
    "package_boy": "PKG BOY",
    "death_ball": "DEATHBALL",
    "super_breakout": "S.BREAKOUT",
    "breakout": "BREAKOUT",
    "portal_arena": "PORTAL",
    "pinball": "PINBALL",
    "galaga": "GALAGA",
    "missile_command": "MISSILES",
    "space_invaders": "INVADERS",
    "tanks": "TANKS",
}

# A stable display order for games so the menu does not jitter run-to-run
# (PLAYABLE_GAMES is a set, which is unordered).
_GAME_ORDER = ["snake", "tetris", "pong", "pinball", "starfox", "galaga",
               "missile_command", "space_invaders", "tanks", "barricade",
               "package_boy",
               "death_ball", "breakout", "super_breakout", "portal_arena"]


def _ordered_games(playable) -> List[str]:
    """Return playable game names in a stable order.

    Names present in :data:`_GAME_ORDER` come first (in that order); any extra
    games not yet listed there are appended alphabetically so newly-added
    playable games still appear without touching this module.
    """
    playable = set(playable)
    ordered = [g for g in _GAME_ORDER if g in playable]
    extras = sorted(g for g in playable if g not in _GAME_ORDER)
    return ordered + extras


def build_games_menu(playable=None) -> Menu:
    """Build the **Games** submenu from the playable-game set.

    :param playable: iterable of playable game names; defaults to
        :data:`src.app_state.PLAYABLE_GAMES`. Each becomes a ``LAUNCH_GAME``
        item. A trailing ``Back`` item pops to the Main Menu (B also works).
    """
    if playable is None:
        # Imported lazily to avoid a hard import cycle at module load.
        from src.app_state import PLAYABLE_GAMES as playable  # noqa: N811

    items: List[MenuItem] = []
    for name in _ordered_games(playable):
        label = _GAME_LABELS.get(name, name.upper())
        items.append(MenuItem(label, ItemAction.LAUNCH_GAME, payload=name))
    items.append(MenuItem("BACK", ItemAction.BACK))
    return Menu(MENU_GAMES, "GAMES", items)


# Friendly labels for demo names whose 10-char truncation is unreadable.
_DEMO_LABELS = {
    "big_eye": "BIG EYE",
    "flight_radar": "AIR RADAR",
    "rain_radar": "RAINRADAR",
    "month_calendar": "CALENDAR",
    "bitcoin_price": "BITCOIN",
    "space_invaders": "INVADERS",
    "missile_command": "MISSILES",
    "hail_mary_clock": "HAIL MARY",
    "logo_wholefoods": "WFM LOGO",
    "system_stats": "SYS STATS",
    "youtube_stream": "YT STREAM",
    "terrain_ball": "TERRABALL",
    "github_stats": "GITHUB",
    "sp500_heatmap": "SP500 MAP",
    "rainbow_waves": "RAINBOW",
    "stock_ticker": "STOCKS",
    "text_scroller": "SCROLLER",
    "video_player": "VIDEO",
    "binary_clock": "BIN CLOCK",
    "base6_clock": "BASE6 CLK",
    "time_display": "CLOCK",
    "living_world": "WORLD",
    "ring_world": "RINGWORLD",
    "moon_tracker": "MOON",
    "game_of_life": "LIFE",
    "matrix_rain": "MATRIX",
    "rubiks_cube": "RUBIKS",
    "super_breakout": "S.BREAKOUT",
    "portal_arena": "PORTAL",
    "package_boy": "PKG BOY",
    "death_ball": "DEATHBALL",
}


def build_demos_menu() -> Menu:
    """Build the **Demos** submenu from the feature registry.

    Lists ALL known features (sorted alphabetically) as ``LAUNCH_DEMO`` items.
    Selecting one runs it in demo mode (no controller) for the configured
    duration, then returns to the menu.
    """
    from src.feature_registry import FEATURE_MODULES

    items: List[MenuItem] = []
    for name in sorted(FEATURE_MODULES.keys()):
        # Friendly label if we have one; otherwise truncate to fit the
        # 64px display (~10 chars at 6px each).
        label = _DEMO_LABELS.get(name, name.upper()[:10])
        items.append(MenuItem(label, ItemAction.LAUNCH_DEMO, payload=name))
    items.append(MenuItem("BACK", ItemAction.BACK))
    return Menu(MENU_DEMOS, "DEMOS", items)


# Duration choices for the Lock Demo flow. Labels fit the 64px row width.
LOCK_DURATIONS = [
    ("5 MIN", 5 * 60),
    ("10 MIN", 10 * 60),
    ("15 MIN", 15 * 60),
    ("30 MIN", 30 * 60),
    ("1 HOUR", 60 * 60),
    ("2 HOURS", 2 * 60 * 60),
    ("4 HOURS", 4 * 60 * 60),
    ("8 HOURS", 8 * 60 * 60),
]


def build_lock_menu() -> Menu:
    """Build the **Lock Demo** submenu: every feature, as PICK_LOCK_DEMO items.

    Same feature list and labels as :func:`build_demos_menu`, but activating an
    item does not launch it -- the engine pushes a duration menu for it instead.
    """
    from src.feature_registry import FEATURE_MODULES

    items: List[MenuItem] = []
    for name in sorted(FEATURE_MODULES.keys()):
        label = _DEMO_LABELS.get(name, name.upper()[:10])
        items.append(MenuItem(label, ItemAction.PICK_LOCK_DEMO, payload=name))
    items.append(MenuItem("BACK", ItemAction.BACK))
    return Menu(MENU_LOCK, "LOCK DEMO", items)


def build_duration_menu(name: str, label: str) -> Menu:
    """Build the duration menu for one demo picked in the Lock Demo submenu.

    Each row is a ``LAUNCH_LOCKED`` item whose payload packs the demo name and
    the duration in seconds as ``"<name>:<seconds>"`` (feature names never
    contain a colon). The title is the demo's own label so it stays obvious
    what is being locked.
    """
    items = [
        MenuItem(dlabel, ItemAction.LAUNCH_LOCKED, payload="%s:%d" % (name, secs))
        for dlabel, secs in LOCK_DURATIONS
    ]
    items.append(MenuItem("BACK", ItemAction.BACK))
    return Menu(MENU_LOCK_DURATION, label[:10], items)


def build_main_menu() -> Menu:
    """Build the top-level **Main Menu**.

    Order: GAMES / DEMOS / LOCK DEMO / CAROUSEL / CONTROLS / SETTINGS /
    UPDATE / ABOUT / RESUME.
    """
    return Menu(
        MENU_MAIN,
        "MAIN MENU",
        [
            MenuItem("GAMES", ItemAction.OPEN_SUBMENU, payload=MENU_GAMES),
            MenuItem("DEMOS", ItemAction.OPEN_SUBMENU, payload=MENU_DEMOS),
            MenuItem("LOCK DEMO", ItemAction.OPEN_SUBMENU, payload=MENU_LOCK),
            MenuItem("CAROUSEL", ItemAction.OPEN_CAROUSEL),
            MenuItem("CONTROLS", ItemAction.OPEN_CONTROLS),
            MenuItem("SETTINGS", ItemAction.OPEN_SETTINGS),
            MenuItem("UPDATE", ItemAction.FORCE_UPDATE),
            MenuItem("ABOUT", ItemAction.OPEN_ABOUT),
            MenuItem("RESUME", ItemAction.RESUME_IDLE),
        ],
    )


def build_menu_registry(playable=None) -> dict:
    """Return ``{menu_id: Menu}`` for every navigable submenu.

    The engine uses this to resolve ``OPEN_SUBMENU`` payloads into the actual
    :class:`Menu` to push. Settings and Carousel are intentionally *not* in the
    registry -- they are special inline screens pushed via their own actions
    rather than plain data menus.
    """
    return {
        MENU_GAMES: build_games_menu(playable),
        MENU_DEMOS: build_demos_menu(),
        MENU_LOCK: build_lock_menu(),
    }
