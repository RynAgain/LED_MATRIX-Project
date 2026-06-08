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
    """Show update UI, pull latest code, and restart the display service.

    This function:
    1. Shows "UPDATING..." on the matrix
    2. Runs git fetch + git reset --hard (guaranteed to get latest code)
    3. Restarts the display service (which shows the boot screen)

    If no network or git fails, falls back to just restarting the service
    so the user at least gets a fresh start.
    """
    _show_message(matrix, "UPDATING...", TEXT_COLOR)

    if platform.system() != "Linux":
        # Not on a Pi — graceful no-op.
        time.sleep(1.5)
        _show_message(matrix, "UPDATE:", TEXT_COLOR, sub="PI ONLY")
        time.sleep(1.5)
        return

    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Step 1: Force pull latest code (git fetch + reset --hard)
    _show_message(matrix, "PULLING...", TEXT_COLOR)
    try:
        # Fetch latest
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=project_root,
            capture_output=True, text=True, timeout=30
        )
        # Hard reset to remote (guaranteed to sync)
        result = subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            cwd=project_root,
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            _show_message(matrix, "UPDATED!", (50, 255, 50))
        else:
            _show_message(matrix, "PULL FAIL", (255, 150, 50), sub="RESTARTING")
    except Exception as e:
        logger.warning("Git pull failed during force update: %s", e)
        _show_message(matrix, "GIT ERROR", (255, 150, 50), sub="RESTARTING")

    time.sleep(1.5)

    # Step 2: Always restart the display service (shows boot screen)
    _show_message(matrix, "RESTARTING..", TEXT_COLOR)
    time.sleep(0.5)

    try:
        subprocess.Popen(
            ["sudo", "systemctl", "restart", "led-matrix.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.warning("Failed to restart display service: %s", e)
        _show_message(matrix, "RESTART FAIL", (255, 80, 80))
        time.sleep(2.0)
        return

    # Give systemd a moment to kill us (we're the display service being restarted)
    time.sleep(5.0)


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
