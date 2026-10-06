"""Zelda-inspired, self-playing adventure for the demo carousel."""

import time

from src.display._shared import interruptible_sleep, should_stop
from .game import QuestGame, WIDTH, HEIGHT
from .render import Renderer

__all__ = ["run", "QuestGame", "Renderer", "WIDTH", "HEIGHT"]
FRAME_INTERVAL = 1 / 30


def run(matrix, duration=60):
    game = QuestGame()
    renderer = Renderer()
    start = last = time.monotonic()
    try:
        while not should_stop():
            now = time.monotonic()
            if now - start >= duration:
                break
            game.update(now - last)
            last = now
            matrix.SetImage(renderer.render(game))
            remaining = min(FRAME_INTERVAL - (time.monotonic() - now),
                            duration - (time.monotonic() - start))
            if remaining > 0:
                interruptible_sleep(remaining)
    finally:
        matrix.Clear()
