#!/usr/bin/env python3
"""
LED Matrix Project - Development Launcher

Starts the LED matrix display simulator for local development. The simulator
provides a pygame window and accepts keyboard input as a fallback for the USB
gamepad control layer (see src/input/keyboard_fallback.py).

The former Flask web control panel was removed in Phase 6; control is now via a
USB gamepad (or the simulator's keyboard fallback).

Usage:
    python dev.py            # Start the display simulator
"""

import sys
import os
import logging

# Project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def run_display():
    """Run the LED matrix display (simulator on non-Pi platforms)."""
    from src.main import main as display_main
    display_main()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logger = logging.getLogger("dev")

    logger.info("=" * 50)
    logger.info("LED Matrix Development Launcher")
    logger.info("=" * 50)
    logger.info("Starting display simulator...")
    logger.info(
        "Control with a USB gamepad, or the keyboard fallback in the "
        "simulator window (arrows/WASD, Z=A, X=B, Enter=Start, Tab=Select)."
    )

    try:
        run_display()
    except KeyboardInterrupt:
        logger.info("Shutting down...")

    logger.info("Dev launcher stopped.")


if __name__ == "__main__":
    main()
