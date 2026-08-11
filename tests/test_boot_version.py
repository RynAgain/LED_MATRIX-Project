"""
Tests for the auto-bumping version scheme and the redesigned boot screen.
"""

import random
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw

from src.version import _describe_to_version
from src.display import boot_screen as bs


class TestAutoBumpVersion:
    def test_commits_since_tag_become_patch(self):
        assert _describe_to_version("v1.1.0-18-g95c876a") == "1.1.18"

    def test_exact_tag_passes_through(self):
        assert _describe_to_version("v1.1.0") == "1.1.0"
        assert _describe_to_version("1.2.3") == "1.2.3"

    def test_patch_base_is_added_not_replaced(self):
        assert _describe_to_version("v2.3.4-100-gdeadbee") == "2.3.104"

    def test_bare_hash_unchanged(self):
        assert _describe_to_version("95c876a") == "95c876a"

    def test_every_commit_bumps(self):
        v1 = _describe_to_version("v1.1.0-18-gaaaaaaa")
        v2 = _describe_to_version("v1.1.0-19-gbbbbbbb")
        assert v1 != v2
        assert v2 == "1.1.19"


class TestBootScreenPhases:
    def _lit(self, img):
        return sum(1 for px in img.convert("RGB").getdata() if sum(px) > 20)

    def test_sweep_frame_draws_bands(self):
        img = Image.new("RGB", (bs.SIZE, bs.SIZE))
        draw = ImageDraw.Draw(img)
        bs._draw_sweep_frame(draw, 0.5, 1.0, random.Random(1))
        assert self._lit(img) > 50

    def test_text_frame_completed_shows_full_words(self):
        img = Image.new("RGB", (bs.SIZE, bs.SIZE))
        draw = ImageDraw.Draw(img)
        bs._draw_text_frame(draw, 1.0, 1.0, tick=1)
        assert self._lit(img) > 100  # LED at scale 3 + MATRIX

    def test_letters_stagger_in(self):
        early = Image.new("RGB", (bs.SIZE, bs.SIZE))
        bs._draw_led_letters(ImageDraw.Draw(early), 0.15)
        late = Image.new("RGB", (bs.SIZE, bs.SIZE))
        bs._draw_led_letters(ImageDraw.Draw(late), 1.0)
        assert 0 < self._lit(early) < self._lit(late)

    def test_typewriter_progresses(self):
        img_half = Image.new("RGB", (bs.SIZE, bs.SIZE))
        bs._draw_matrix_typewriter(ImageDraw.Draw(img_half), 0.7, tick=1)
        img_full = Image.new("RGB", (bs.SIZE, bs.SIZE))
        bs._draw_matrix_typewriter(ImageDraw.Draw(img_full), 1.0, tick=1)
        assert self._lit(img_half) < self._lit(img_full)

    def test_loading_frame_shows_version(self):
        img = Image.new("RGB", (bs.SIZE, bs.SIZE))
        draw = ImageDraw.Draw(img)
        with patch.object(bs, "get_version", return_value="1.1.18"):
            bs._draw_loading_frame(draw, 0.9, 1.0, tick=10)
        # Version row must have lit pixels
        version_row = [img.getpixel((x, y))
                       for x in range(bs.SIZE)
                       for y in range(bs.VERSION_Y, bs.VERSION_Y + 7)]
        assert any(sum(px) > 20 for px in version_row)
        # Loading bar mostly filled
        bar_row = [img.getpixel((x, bs.BAR_Y + 1)) for x in range(bs.SIZE)]
        assert sum(1 for px in bar_row if sum(px) > 20) > 20

    def test_version_text_truncates_long_hash(self):
        with patch.object(bs, "get_version",
                          return_value="abcdef0123456789"):
            txt = bs._version_text()
        assert len(txt) <= 10
        assert txt.startswith("V")

    def test_show_runs_and_draws(self):
        matrix = MagicMock()
        bs.show(matrix, duration=0.5)
        assert matrix.SetImage.call_count >= 2
        matrix.Clear.assert_called()

    def test_show_survives_matrix_error(self):
        matrix = MagicMock()
        matrix.SetImage.side_effect = RuntimeError("boom")
        bs.show(matrix, duration=0.3)  # must not raise
