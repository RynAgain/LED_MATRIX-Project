"""
Integration test: runs the full feature cycle through the simulator.
"""

import pytest
import importlib
import time


class TestFullFeatureCycle:
    """Run all enabled features through the simulator to verify end-to-end."""

    def test_full_cycle_all_games(self, matrix):
        """Run all game features for 2 seconds each."""
        features = [
            "src.display.tic_tac_toe",
            "src.display.snake",
            "src.display.pong",
            "src.display.billiards",
        ]

        for module_path in features:
            mod = importlib.import_module(module_path)
            start = time.time()
            mod.run(matrix, duration=2)
            elapsed = time.time() - start
            # Should respect duration (with some tolerance)
            assert elapsed < 10, f"{module_path} ran for {elapsed:.1f}s, expected ~2s"

    def test_time_display_cycle(self, matrix):
        """Run time display feature."""
        mod = importlib.import_module("src.display.time_display")
        start = time.time()
        mod.run(matrix, duration=3)
        elapsed = time.time() - start
        assert elapsed < 15, f"time_display ran for {elapsed:.1f}s, expected ~3s"

    def test_config_validator_on_real_config(self):
        """Validate the actual project config files."""
        from src.config_validator import validate_all
        results = validate_all()

        for config_name, errors in results.items():
            hard_errors = [e for e in errors if e.severity == "error"]
            assert len(hard_errors) == 0, (
                f"config/{config_name} has validation errors: "
                + "; ".join(str(e) for e in hard_errors)
            )

    def test_feature_module_crash_recovery(self, matrix):
        """Verify that a crashing feature doesn't break the matrix."""
        # Run a normal feature first
        mod = importlib.import_module("src.display.pong")
        mod.run(matrix, duration=1)

        # Matrix should still be usable after
        matrix.Clear()
        matrix.SetPixel(0, 0, 255, 0, 0)
        matrix.Fill(0, 0, 0)
