"""
Tests for display modules.
Verifies each module has a run(matrix, duration) function and can execute briefly.
"""

import pytest
import importlib
from unittest.mock import patch, MagicMock


DISPLAY_MODULES = [
    "src.display.tic_tac_toe",
    "src.display.snake",
    "src.display.pong",
    "src.display.breakout",
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
    "src.display.galaga",
    "src.display.space_invaders",
    "src.display.logo_wholefoods",
    "src.display.github_stats",
    "src.display.tanks",
    "src.display.wireframe",
    "src.display.maze_3d",
    "src.display.terrain_ball",
    "src.display.system_stats",
    "src.display.living_world",
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

    # ----------------------------------------------------------------
    # Execution tests: game modules (parametrized)
    # ----------------------------------------------------------------

    @pytest.mark.parametrize("module_path", [
        "src.display.tic_tac_toe",
        "src.display.snake",
        "src.display.pong",
        "src.display.breakout",
        "src.display.galaga",
        "src.display.space_invaders",
        "src.display.tanks",
    ])
    def test_game_runs_briefly(self, matrix, module_path):
        """Game modules should run for a short duration without crashing."""
        mod = importlib.import_module(module_path)
        # Run for just 2 seconds
        mod.run(matrix, duration=2)

    # ----------------------------------------------------------------
    # Execution tests: visual / simple modules (no network)
    # ----------------------------------------------------------------

    def test_time_display_runs_briefly(self, matrix):
        """Time display should run briefly without crashing."""
        mod = importlib.import_module("src.display.time_display")
        mod.run(matrix, duration=2)

    def test_billiards_runs_briefly(self, matrix):
        """Billiards should run briefly without crashing."""
        mod = importlib.import_module("src.display.billiards")
        mod.run(matrix, duration=2)

    def test_logo_wholefoods_runs_briefly(self, matrix):
        """Whole Foods logo should run briefly without crashing."""
        mod = importlib.import_module("src.display.logo_wholefoods")
        mod.run(matrix, duration=2)

    def test_github_stats_runs_briefly(self, matrix):
        """GitHub stats should run briefly without crashing."""
        mod = importlib.import_module("src.display.github_stats")
        mod.run(matrix, duration=2)

    def test_wireframe_runs_briefly(self, matrix):
        """Wireframe should run briefly without crashing."""
        mod = importlib.import_module("src.display.wireframe")
        mod.run(matrix, duration=2)

    def test_maze_3d_runs_briefly(self, matrix):
        """Maze 3D should run briefly without crashing."""
        mod = importlib.import_module("src.display.maze_3d")
        mod.run(matrix, duration=2)

    def test_terrain_ball_runs_briefly(self, matrix):
        """Terrain ball should run briefly without crashing."""
        mod = importlib.import_module("src.display.terrain_ball")
        mod.run(matrix, duration=2)

    def test_system_stats_runs_briefly(self, matrix):
        """System stats should run briefly without crashing."""
        mod = importlib.import_module("src.display.system_stats")
        mod.run(matrix, duration=2)

    def test_living_world_runs_briefly(self, matrix):
        """Living world should run briefly without crashing."""
        mod = importlib.import_module("src.display.living_world")
        mod.run(matrix, duration=2)

    # ----------------------------------------------------------------
    # Execution tests: visual effects (no network, added Phase 8)
    # ----------------------------------------------------------------

    def test_fire_runs_briefly(self, matrix):
        """Fire effect should run briefly without crashing."""
        mod = importlib.import_module("src.display.fire")
        mod.run(matrix, duration=2)

    def test_plasma_runs_briefly(self, matrix):
        """Plasma effect should run briefly without crashing."""
        mod = importlib.import_module("src.display.plasma")
        mod.run(matrix, duration=2)

    def test_matrix_rain_runs_briefly(self, matrix):
        """Matrix rain effect should run briefly without crashing."""
        mod = importlib.import_module("src.display.matrix_rain")
        mod.run(matrix, duration=2)

    def test_starfield_runs_briefly(self, matrix):
        """Starfield effect should run briefly without crashing."""
        mod = importlib.import_module("src.display.starfield")
        mod.run(matrix, duration=2)

    def test_game_of_life_runs_briefly(self, matrix):
        """Game of Life should run briefly without crashing."""
        mod = importlib.import_module("src.display.game_of_life")
        mod.run(matrix, duration=2)

    def test_rainbow_waves_runs_briefly(self, matrix):
        """Rainbow waves should run briefly without crashing."""
        mod = importlib.import_module("src.display.rainbow_waves")
        mod.run(matrix, duration=2)

    def test_binary_clock_runs_briefly(self, matrix):
        """Binary clock should run briefly without crashing."""
        mod = importlib.import_module("src.display.binary_clock")
        mod.run(matrix, duration=2)

    def test_countdown_runs_briefly(self, matrix):
        """Countdown timer should run briefly without crashing."""
        mod = importlib.import_module("src.display.countdown")
        mod.run(matrix, duration=2)

    def test_lava_lamp_runs_briefly(self, matrix):
        """Lava lamp effect should run briefly without crashing."""
        mod = importlib.import_module("src.display.lava_lamp")
        mod.run(matrix, duration=2)

    def test_qr_code_runs_briefly(self, matrix):
        """QR code display should run briefly without crashing."""
        mod = importlib.import_module("src.display.qr_code")
        mod.run(matrix, duration=2)

    def test_text_scroller_runs_briefly(self, matrix):
        """Text scroller should run briefly without crashing."""
        mod = importlib.import_module("src.display.text_scroller")
        mod.run(matrix, duration=2)

    def test_slideshow_runs_briefly(self, matrix):
        """Slideshow should run briefly without crashing (even with no images)."""
        mod = importlib.import_module("src.display.slideshow")
        mod.run(matrix, duration=2)

    # ----------------------------------------------------------------
    # Execution tests: network-dependent modules (HTTP mocked)
    # ----------------------------------------------------------------

    def test_weather_runs_briefly(self, matrix):
        """Weather display should run briefly without crashing (network mocked)."""
        with patch("src.display.weather.requests.get",
                   side_effect=Exception("mocked network")):
            mod = importlib.import_module("src.display.weather")
            mod.run(matrix, duration=2)

    def test_bitcoin_price_runs_briefly(self, matrix):
        """Bitcoin price should run briefly without crashing (network mocked)."""
        with patch("src.display.bitcoin_price.requests.get",
                   side_effect=Exception("mocked network")):
            mod = importlib.import_module("src.display.bitcoin_price")
            mod.run(matrix, duration=2)

    def test_stock_ticker_runs_briefly(self, matrix):
        """Stock ticker should run briefly without crashing (network mocked)."""
        with patch("src.display.stock_ticker.requests.get",
                   side_effect=Exception("mocked network")):
            mod = importlib.import_module("src.display.stock_ticker")
            mod.run(matrix, duration=2)

    def test_sp500_heatmap_runs_briefly(self, matrix):
        """S&P 500 heatmap should run briefly without crashing (network mocked)."""
        with patch("src.display.sp500_heatmap.requests.get",
                   side_effect=Exception("mocked network")):
            mod = importlib.import_module("src.display.sp500_heatmap")
            mod.run(matrix, duration=2)

    # ----------------------------------------------------------------
    # Execution tests: special modules
    # ----------------------------------------------------------------

    def test_boot_screen_runs_briefly(self, matrix):
        """Boot screen show() should run briefly without crashing."""
        mod = importlib.import_module("src.display.boot_screen")
        assert hasattr(mod, "show"), "boot_screen missing show() function"
        # boot_screen uses show() rather than run()
        mod.show(matrix, duration=2)

    def test_youtube_stream_interface(self):
        """YouTube stream should be importable with correct interface."""
        mod = importlib.import_module("src.display.youtube_stream")
        assert hasattr(mod, "run"), "youtube_stream missing run()"
        assert callable(mod.run)
        assert hasattr(mod, "read_urls_from_csv"), "youtube_stream missing read_urls_from_csv()"
        assert hasattr(mod, "download_video"), "youtube_stream missing download_video()"

    def test_youtube_stream_runs_briefly(self, matrix):
        """YouTube stream should run briefly without crashing (no cached videos)."""
        mod = importlib.import_module("src.display.youtube_stream")
        # Mock _ensure_dependencies to return False so it exits immediately
        # without requiring cv2/yt-dlp
        with patch.object(mod, "_ensure_dependencies", return_value=False):
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
        assert len(FEATURE_MODULES) >= 20, f"Expected at least 20 features, got {len(FEATURE_MODULES)}"
        for name, path in FEATURE_MODULES.items():
            mod = importlib.import_module(path)
            assert hasattr(mod, "run"), f"{name} ({path}) missing run()"
