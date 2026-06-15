#!/usr/bin/env python3
"""
Force-update screen: simple git pull + service restart from the menu.

On the Pi, runs:
    cd ~/LED_MATRIX-Project && git pull && sudo systemctl restart led-matrix.service

That's it. No complex stash/merge/recovery logic. If the user has local
config changes, git pull will fast-forward (configs are in .gitignore or
unchanged). If it fails, we show the error and still offer to restart.

On Windows/dev machines where systemctl doesn't exist, shows a brief
"UPDATE: PI ONLY" message and returns gracefully.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import time

from PIL import Image, ImageDraw

from src.display import _fonts

logger = logging.getLogger(__name__)

SIZE = 64
BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 200, 50)
OK_COLOR = (50, 255, 50)
WARN_COLOR = (255, 150, 50)
ERR_COLOR = (255, 80, 80)
INFO_COLOR = (150, 150, 160)


def run_force_update(matrix) -> None:
    """Pull latest code from GitHub and restart the display service.

    Steps:
    1. Show "UPDATING..." on the matrix
    2. cd to project directory and run `git pull`
    3. Restart `led-matrix.service` via systemctl
    4. We get killed by the restart (this is expected)

    If git pull fails, we still try to restart the service so the user
    isn't stuck with a broken state.
    """
    _show_message(matrix, "UPDATING...", TEXT_COLOR)

    if platform.system() != "Linux":
        # Not on a Pi — show message and return.
        time.sleep(1.0)
        _show_message(matrix, "UPDATE:", TEXT_COLOR, sub="PI ONLY")
        time.sleep(1.5)
        return

    # Find project root: either from this file's location or fallback to ~/LED_MATRIX-Project
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    home_dir = os.path.expanduser("~")
    fallback_root = os.path.join(home_dir, "LED_MATRIX-Project")

    # Use whichever path has a .git directory
    if os.path.isdir(os.path.join(project_root, ".git")):
        work_dir = project_root
    elif os.path.isdir(os.path.join(fallback_root, ".git")):
        work_dir = fallback_root
    else:
        work_dir = project_root  # Best guess

    logger.info("Force update: working directory = %s", work_dir)

    # --- Step 1: git fetch + reset --hard (ALWAYS works, even with local changes) ---
    # NOTE: This intentionally does NOT backup/restore config.json.
    # The new config from GitHub includes new features (like starfox).
    # User's carousel toggles get reset, but all new features appear immediately.
    _show_message(matrix, "FETCHING...", TEXT_COLOR)
    time.sleep(0.3)

    pull_ok = False
    try:
        # Remove stale lock file
        lock_file = os.path.join(work_dir, ".git", "index.lock")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                logger.info("Removed stale git lock file")
            except OSError:
                pass

        # Fetch latest from origin
        fetch_result = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=work_dir,
            capture_output=True, text=True, timeout=60
        )
        if fetch_result.returncode != 0:
            logger.error("git fetch failed: %s", fetch_result.stderr.strip()[:200])
            _show_message(matrix, "FETCH FAIL", ERR_COLOR)
            time.sleep(2.0)
        else:
            # Hard reset to remote (guaranteed to sync regardless of local state)
            _show_message(matrix, "UPDATING...", TEXT_COLOR)
            reset_result = subprocess.run(
                ["git", "reset", "--hard", "origin/main"],
                cwd=work_dir,
                capture_output=True, text=True, timeout=15
            )
            if reset_result.returncode == 0:
                _show_message(matrix, "UPDATED!", OK_COLOR)
                pull_ok = True
                logger.info("Update succeeded: %s", reset_result.stdout.strip()[:200])
            else:
                _show_message(matrix, "RESET FAIL", ERR_COLOR)
                logger.error("git reset failed: %s", reset_result.stderr.strip()[:200])
    except subprocess.TimeoutExpired:
        logger.error("git operation timed out")
        _show_message(matrix, "TIMEOUT", ERR_COLOR)
    except FileNotFoundError:
        logger.error("git not found on this system")
        _show_message(matrix, "NO GIT!", ERR_COLOR)
        time.sleep(2.0)
        return
    except Exception as e:
        logger.error("Update error: %s", e)
        _show_message(matrix, "ERROR", ERR_COLOR)

    time.sleep(1.0)

    # --- Step 2: Restart the display service ---
    _show_message(matrix, "RESTARTING..", TEXT_COLOR)
    time.sleep(0.5)

    try:
        # Use Popen so we don't block waiting (we'll get killed by the restart)
        subprocess.Popen(
            ["sudo", "systemctl", "restart", "led-matrix.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Restart command issued")
    except Exception as e:
        logger.error("Failed to restart service: %s", e)
        _show_message(matrix, "RESTART FAIL", ERR_COLOR)
        time.sleep(2.0)
        return

    # Give systemd time to kill us (we ARE the display service being restarted)
    time.sleep(5.0)


def _try_hard_reset(matrix, work_dir) -> bool:
    """Fallback: git fetch + git reset --hard origin/main.

    Used when a simple git pull fails (e.g., local changes conflict).
    """
    _show_message(matrix, "RESETTING..", TEXT_COLOR)
    try:
        # Fetch
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=work_dir,
            capture_output=True, text=True, timeout=30
        )
        # Hard reset
        result = subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            cwd=work_dir,
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            _show_message(matrix, "RESET OK!", OK_COLOR)
            logger.info("Hard reset succeeded")
            return True
        else:
            _show_message(matrix, "RESET FAIL", ERR_COLOR)
            logger.error("Hard reset failed: %s", result.stderr.strip()[:200])
            return False
    except Exception as e:
        logger.error("Hard reset error: %s", e)
        _show_message(matrix, "RESET ERR", ERR_COLOR)
        return False


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
