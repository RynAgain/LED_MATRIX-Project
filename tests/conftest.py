"""
Shared test fixtures for LED Matrix Project tests.
"""

import sys
import os
import glob
import types
import pytest

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _register_simulator():
    """Register the simulator as rgbmatrix in sys.modules for testing."""
    try:
        import rgbmatrix
        return  # Real rgbmatrix available
    except ImportError:
        pass

    import src.simulator as sim
    import src.simulator.matrix as sim_matrix
    import src.simulator.graphics as sim_graphics

    mock_rgbmatrix = types.ModuleType("rgbmatrix")
    mock_rgbmatrix.RGBMatrix = sim_matrix.RGBMatrix
    mock_rgbmatrix.RGBMatrixOptions = sim_matrix.RGBMatrixOptions
    mock_rgbmatrix.FrameCanvas = sim_matrix.FrameCanvas
    mock_rgbmatrix.graphics = sim_graphics

    sys.modules["rgbmatrix"] = mock_rgbmatrix
    sys.modules["rgbmatrix.graphics"] = sim_graphics


# Register simulator before any display imports
_register_simulator()


@pytest.fixture(autouse=True)
def preserve_config_files():
    """Backup and restore config files to prevent tests from polluting the repo.

    Every test that triggers create_app() or hits a POST endpoint may write to
    config/*.json or config/*.csv (e.g. wifi.json, web.json, schedule.json).
    This fixture snapshots all config data files before the test and restores
    them afterward so that ``git diff config/`` stays clean.
    """
    config_dir = os.path.join(PROJECT_ROOT, "config")
    backups = {}

    # Snapshot every JSON and CSV file in config/
    for pattern in ("*.json", "*.csv"):
        for filepath in glob.glob(os.path.join(config_dir, pattern)):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    backups[filepath] = f.read()
            except OSError:
                pass

    # Record which files existed before the test
    pre_existing = set(backups.keys())

    try:
        yield
    finally:
        # Restore original content for files that existed before the test
        for filepath, content in backups.items():
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
            except OSError:
                pass

        # Remove any *new* config files that a test may have created
        for pattern in ("*.json", "*.csv"):
            for filepath in glob.glob(os.path.join(config_dir, pattern)):
                if filepath not in pre_existing:
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass


@pytest.fixture(autouse=True)
def _sdl_videodriver_dummy(monkeypatch):
    """Set SDL_VIDEODRIVER=dummy for every test and restore the original value
    on teardown via monkeypatch (guarantees cleanup even on test failure)."""
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")


@pytest.fixture
def matrix():
    """Provide a simulated RGBMatrix for testing."""
    from src.simulator.matrix import RGBMatrix, RGBMatrixOptions

    options = RGBMatrixOptions()
    options.rows = 64
    options.cols = 64
    m = RGBMatrix(options=options)
    yield m
    try:
        m.Clear()
    except Exception:
        pass


@pytest.fixture
def canvas(matrix):
    """Provide a simulated FrameCanvas for testing."""
    return matrix.CreateFrameCanvas()
