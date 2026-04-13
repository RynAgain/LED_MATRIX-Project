#!/usr/bin/env python3
"""
LED Matrix Project - Unified Development Launcher

Starts both the LED matrix simulator and the web control panel
in a single process for development convenience.

Usage:
    python dev.py           # Start both simulator + web panel
    python dev.py --web     # Start only the web panel
    python dev.py --display # Start only the display simulator
"""

import sys
import os
import threading
import logging
import time

# Project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def run_web(port=5000):
    """Run the Flask web panel in a background thread."""
    from src.web.app import create_app, _kill_existing_on_port
    _kill_existing_on_port(port)
    app = create_app()
    # Use threaded=True so Flask handles requests while main thread runs display
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def run_display():
    """Run the LED matrix display (simulator on Windows)."""
    from src.main import main as display_main
    display_main()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logger = logging.getLogger("dev")

    mode = "both"
    if "--web" in sys.argv:
        mode = "web"
    elif "--display" in sys.argv:
        mode = "display"

    logger.info("=" * 50)
    logger.info("LED Matrix Development Launcher")
    logger.info("=" * 50)

    if mode in ("both", "web"):
        port = 5000
        web_thread = threading.Thread(target=run_web, args=(port,), daemon=True)
        web_thread.start()
        logger.info("Web panel starting at http://127.0.0.1:%d", port)
        logger.info("Web panel ready -- credentials are in config/web.json")
        time.sleep(1)  # Let Flask start

    if mode in ("both", "display"):
        logger.info("Starting display simulator...")
        try:
            run_display()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
    elif mode == "web":
        logger.info("Web-only mode. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")

    logger.info("Dev launcher stopped.")


if __name__ == "__main__":
    main()
