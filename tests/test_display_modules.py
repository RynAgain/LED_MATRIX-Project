"""
Tests for display modules.
Verifies each module has a run(matrix, duration) function and can execute briefly.
"""

import pytest
import importlib


DISPLAY_MODULES = [
    "src.display.tic_tac_toe",
    "src.display.snake",
    "src.display.pong",
    "src.display.billiards",
    "src.display.time_display",
    "src.display.bitcoin_price",
    "src.display.youtube_stream",
    "src.display.fire",
    "src.display.plasma",
    "src.display.matrix_rain",
    "src.display.starfield",
    "src.display.game_of_life",
    "src.display.rainbow_waves",
    "src.display.weather",
    "src.display.text_scroller",
    "src.display.stock_ticker",
    "src.display.sp500_heatmap",
    "src.display.binary_clock",
    "src.display.countdown",
    "src.display.lava_lamp",
    "src.display.qr_code",
    "src.display.slideshow",
]


class TestDisplayModuleInterface:
    """Verify each display module has the required interface."""

    @pytest.mark.parametrize("module_path", DISPLAY_MODULES)
    def test_module_importable(self, module_path):
        """Each display module should be importable."""
        mod = importlib.import_module(module_path)
        assert mod is not None

    @pytest.mark.parametrize("module_path", DISPLAY_MODULES)
    def test_module_has_run_function(self, module_path):
        """Each display module must have a run(matrix, duration) function."""
        mod = importlib.import_module(module_path)
        assert hasattr(mod, "run"), f"{module_path} missing run() function"
        assert callable(mod.run)

    @pytest.mark.parametrize("module_path", [
        "src.display.tic_tac_toe",
        "src.display.snake",
        "src.display.pong",
    ])
    def test_game_runs_briefly(self, matrix, module_path):
        """Game modules should run for a short duration without crashing."""
        mod = importlib.import_module(module_path)
        # Run for just 2 seconds
        mod.run(matrix, duration=2)

    def test_time_display_runs_briefly(self, matrix):
        """Time display should run briefly without crashing."""
        mod = importlib.import_module("src.display.time_display")
        mod.run(matrix, duration=2)

    def test_billiards_runs_briefly(self, matrix):
        """Billiards should run briefly without crashing."""
        mod = importlib.import_module("src.display.billiards")
        mod.run(matrix, duration=2)


class TestMainModule:
    """Tests for src/main.py."""

    def test_load_config(self):
        """Config should load successfully."""
        from src.main import load_config
        config = load_config()
        assert "sequence" in config
        assert isinstance(config["sequence"], list)

    def test_feature_modules_mapping(self):
        """All feature module paths should be importable."""
        from src.main import FEATURE_MODULES
        assert len(FEATURE_MODULES) == 22, f"Expected 22 features, got {len(FEATURE_MODULES)}"
        for name, path in FEATURE_MODULES.items():
            mod = importlib.import_module(path)
            assert hasattr(mod, "run"), f"{name} ({path}) missing run()"
