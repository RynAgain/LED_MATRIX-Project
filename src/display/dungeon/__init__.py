"""First-person dungeon crawl that plays itself.

A hero explores procedurally generated floors: textured raycast walls
with torch flicker and depth fog, monsters with distinct behaviours,
loot, keys and locked stair rooms, descent transitions, and death
followed by a fresh run. All game state lives in ``game.DungeonGame``
(pure, seedable); all pixels in ``render.Renderer``.
"""

import time
import logging

from src.display._shared import should_stop
from .constants import WIDTH, HEIGHT, FRAME_INTERVAL
from .game import DungeonGame
from .render import Renderer

logger = logging.getLogger(__name__)

__all__ = ["run", "DungeonGame", "Renderer", "WIDTH", "HEIGHT"]


def run(matrix, duration=60):
    """Run the dungeon crawl demo."""
    start = time.time()
    game = DungeonGame()
    renderer = Renderer()
    last = start

    try:
        while time.time() - start < duration:
            if should_stop():
                break
            frame_start = time.time()
            dt = min(0.1, max(0.001, frame_start - last))
            last = frame_start

            game.update(dt)
            matrix.SetImage(renderer.render(game, frame_start))

            sleep_time = FRAME_INTERVAL - (time.time() - frame_start)
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception:
        logger.error("Error in dungeon demo", exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
