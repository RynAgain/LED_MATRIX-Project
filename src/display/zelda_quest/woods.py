"""Published forest slice: resume across carousel slots, repeat after its ending."""
from . import preview
from .persistence import SAVE_PATH as PREVIEW_SAVE_PATH

SAVE_PATH = PREVIEW_SAVE_PATH.with_name("zelda_woods_save.json")


def run(matrix, duration=60):
    preview.run(matrix, duration=duration, save_path=SAVE_PATH, repeat=True)
