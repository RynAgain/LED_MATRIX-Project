#!/usr/bin/env python3
"""
Menu / UI system package (CONTROLLER_OVERHAUL.md §4).

Public API::

    from src.menu import MenuSystem

:class:`MenuSystem` implements the :class:`src.app_state.MenuController` protocol
(``run(self, matrix, controller) -> MenuResult``) and is the drop-in replacement
for the Phase-2 ``PlaceholderMenu``. The menu hierarchy itself is data-driven
(see :mod:`src.menu.menu_data`) and the on-device Settings editor lives in
:mod:`src.menu.settings_screen`.
"""

from .carousel_screen import CarouselScreen
from .menu_data import (
    ItemAction,
    Menu,
    MenuItem,
    build_demos_menu,
    build_games_menu,
    build_main_menu,
    build_menu_registry,
)
from .menu_system import MenuSystem
from .settings_screen import SettingsScreen, load_settings, save_settings

__all__ = [
    "MenuSystem",
    "CarouselScreen",
    "SettingsScreen",
    "load_settings",
    "save_settings",
    "Menu",
    "MenuItem",
    "ItemAction",
    "build_main_menu",
    "build_games_menu",
    "build_demos_menu",
    "build_menu_registry",
]
