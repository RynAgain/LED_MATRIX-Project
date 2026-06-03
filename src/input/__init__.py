#!/usr/bin/env python3
"""
Input abstraction layer package.

Public API re-exported for convenience::

    from src.input import Controller, Button, EventType, InputEvent, \
        ButtonMapping, wants_quit

See :mod:`src.input.controller` for the full design and the pygame
event-queue coexistence contract with the simulator.
"""

from .controller import (
    Button,
    ButtonMapping,
    Controller,
    EventType,
    InputEvent,
    default_mapping,
    load_mapping,
    save_mapping,
    wants_quit,
    CONTROLLER_CONFIG_PATH,
    START_HOLD_QUIT_SECONDS,
)

__all__ = [
    "Controller",
    "Button",
    "EventType",
    "InputEvent",
    "ButtonMapping",
    "wants_quit",
    "default_mapping",
    "load_mapping",
    "save_mapping",
    "CONTROLLER_CONFIG_PATH",
    "START_HOLD_QUIT_SECONDS",
]
