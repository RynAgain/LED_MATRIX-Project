"""
Shared test fixtures for LED Matrix Project tests.
"""

import sys
import os
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


@pytest.fixture
def matrix():
    """Provide a simulated RGBMatrix for testing."""
    from src.simulator.matrix import RGBMatrix, RGBMatrixOptions
    
    # Use headless mode - don't open pygame window during tests
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    
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
