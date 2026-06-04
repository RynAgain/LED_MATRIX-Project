#!/usr/bin/env python3
"""
Force-update screen: triggers the led-matrix-updater systemd service.

On Linux (Raspberry Pi), runs:
    sudo systemctl start led-matrix-updater.service

On Windows/dev machines where systemctl doesn't exist, shows a brief
"UPDATE: PI ONLY" message and returns gracefully.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import time

from PIL import Image, ImageDraw

from src.display import _fonts

logger = logging.getLogger(__name__)

SIZE = 64
BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 200, 50)
INFO_COLOR = (150, 150, 160)


def run_force_update(matrix) -> None:
    """Show update UI and trigger the updater service.

    This function blocks for ~3 seconds while displaying status messages,
    then returns. The updater service may restart the display service
    underneath — that's expected and fine.
    """
    _show_message(matrix, "UPDATING...", TEXT_COLOR)

    if platform.system() != "Linux":
        # Not on a Pi — graceful no-op.
        time.sleep(1.5)
        _show_message(matrix, "UPDATE:", TEXT_COLOR, sub="PI ONLY")
        time.sleep(1.5)
        return

    # Trigger the updater service.
    try:
        subprocess.Popen(
            ["sudo", "systemctl", "start", "led-matrix-updater.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.warning("Failed to trigger updater: %s", e)
        _show_message(matrix, "UPDATE FAIL", (255, 80, 80))
        time.sleep(2.0)
        return

    # Give the service a moment to start.
    time.sleep(2.0)
    _show_message(matrix, "RESTARTING..", TEXT_COLOR)
    time.sleep(1.5)


def _show_message(matrix, text: str, color, sub: str | None = None) -> None:
    """Render a centered message (and optional subtitle) on the matrix."""
    img = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
    draw = ImageDraw.Draw(img)

    tw = _fonts._text_width(text, scale=1)
    x = max(0, (SIZE - tw) // 2)
    y = 24 if sub is None else 20
    _fonts._draw_text(draw, text, x, y, color)

    if sub is not None:
        sw = _fonts._text_width(sub, scale=1)
        sx = max(0, (SIZE - sw) // 2)
        _fonts._draw_text(draw, sub, sx, 34, INFO_COLOR)

    matrix.SetImage(img)
