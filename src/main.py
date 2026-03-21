#!/usr/bin/env python3
"""
LED Matrix Project - Main Entry Point

Reads config/config.json and cycles through enabled display features
on a 64x64 RGB LED matrix. Designed for Raspberry Pi with rpi-rgb-led-matrix.
"""

import json
import importlib
import logging
import os
import sys
import time
import signal
import threading

from src.display._shared import request_stop, clear_stop, should_stop

logger = logging.getLogger(__name__)

# Global reference for web panel preview access
_matrix_ref = None

# Project root is one level up from this file
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Add project root to path for imports
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def write_status(feature_name=None, status="running"):
    """Write current display status to logs/status.json for the web panel."""
    status_path = os.path.join(PROJECT_ROOT, "logs", "status.json")
    try:
        data = {
            "status": status,
            "current_feature": feature_name,
            "timestamp": time.time(),
            "uptime": "N/A"
        }
        if hasattr(write_status, '_start_time'):
            elapsed = time.time() - write_status._start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            data["uptime"] = f"{hours}h {minutes}m"
        with open(status_path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def write_pid():
    """Write the current PID for web panel communication."""
    pid_path = os.path.join(PROJECT_ROOT, "logs", "display.pid")
    try:
        with open(pid_path, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


# Flag for graceful shutdown
_shutdown = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown
    logger.info("Received signal %d, shutting down...", signum)
    _shutdown = True


def sighup_handler(signum, frame):
    """Handle SIGHUP for config reload."""
    logger.info("Received SIGHUP, config will reload on next cycle")


COMMAND_PATH = os.path.join(PROJECT_ROOT, "logs", "command.json")


def check_command():
    """Check for and consume a command from the web panel.
    
    Returns:
        dict with 'command' and 'data' keys, or None if no command.
    """
    try:
        if os.path.exists(COMMAND_PATH):
            mtime = os.path.getmtime(COMMAND_PATH)
            # Only process commands less than 30 seconds old
            if time.time() - mtime < 30:
                with open(COMMAND_PATH, "r") as f:
                    cmd = json.load(f)
                # Delete the command file so it's not processed again
                os.remove(COMMAND_PATH)
                logger.info("Command received: %s", cmd.get("command"))
                return cmd
            else:
                # Stale command, remove it
                os.remove(COMMAND_PATH)
    except (json.JSONDecodeError, OSError, KeyError):
        pass
    return None


def handle_play_video(matrix, url, title="Unknown", duration=300):
    """Handle a play_video command by streaming a YouTube video.
    
    Args:
        matrix: RGBMatrix instance.
        url: YouTube video URL.
        title: Video title for logging.
        duration: Max playback duration in seconds.
    """
    logger.info("Playing video: %s (%s)", title, url)
    write_status(f"YouTube: {title}", "running")
    try:
        from src.display.youtube_stream import stream_video, FRAME_INTERVAL
        import cv2
        from PIL import Image

        video_url = stream_video(url)
        cap = cv2.VideoCapture(video_url)
        if not cap.isOpened():
            logger.error("Failed to open video stream: %s", video_url)
            return

        start = time.time()
        while cap.isOpened() and not _shutdown:
            frame_start = time.time()

            # Check for new commands (allows interrupting)
            new_cmd = check_command()
            if new_cmd:
                # Re-write the command for the main loop to pick up
                try:
                    with open(COMMAND_PATH, "w") as f:
                        json.dump(new_cmd, f)
                except Exception:
                    pass
                break

            if time.time() - start >= duration:
                break

            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.resize(frame, (64, 64), interpolation=cv2.INTER_NEAREST)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame)
            matrix.SetImage(image)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        cap.release()
    except Exception as e:
        logger.error("Video playback error: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass


def load_config():
    """
    Load display sequence configuration.

    Returns:
        dict: Configuration dictionary with sequence and settings.
    """
    config_path = os.path.join(PROJECT_ROOT, "config", "config.json")
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        logger.info("Loaded config from %s", config_path)
        return config
    except FileNotFoundError:
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in config: %s", e)
        sys.exit(1)


def _create_simulator_matrix(options=None):
    """Create a simulator matrix for development/testing."""
    from src.simulator import RGBMatrix as SimRGBMatrix
    from src.simulator import RGBMatrixOptions as SimOptions

    if options is None:
        options = SimOptions()
        options.rows = 64
        options.cols = 64

    matrix = SimRGBMatrix(options=options)
    logger.info("Using LED Matrix Simulator (pygame window)")
    return matrix


def init_matrix():
    """
    Initialize the RGB LED matrix.
    On Raspberry Pi: uses the real rgbmatrix library.
    On other platforms: falls back to pygame-based simulator.
    """
    try:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        options = RGBMatrixOptions()
        options.rows = 64
        options.cols = 64
        options.chain_length = 1
        options.parallel = 1
        options.hardware_mapping = "regular"
        options.gpio_slowdown = 4
        options.brightness = 80
        options.drop_privileges = False

        matrix = RGBMatrix(options=options)
        logger.info("RGB LED Matrix initialized (64x64)")
        return matrix
    except ImportError:
        logger.warning("rgbmatrix not available - using simulator")
        return _create_simulator_matrix()
    except Exception as e:
        logger.error("Failed to initialize matrix: %s", e)
        logger.warning("Falling back to simulator")
        return _create_simulator_matrix()


def _register_simulator_modules():
    """
    Register the simulator as 'rgbmatrix' in sys.modules.
    This allows display modules that do 'from rgbmatrix import ...' to work
    on platforms where the real rgbmatrix C library is not available.
    """
    try:
        import rgbmatrix
        # Real rgbmatrix is available, no need to patch
        return
    except ImportError:
        pass

    import src.simulator as sim
    import src.simulator.matrix as sim_matrix
    import src.simulator.graphics as sim_graphics

    # Create a mock rgbmatrix module
    import types
    mock_rgbmatrix = types.ModuleType("rgbmatrix")
    mock_rgbmatrix.RGBMatrix = sim_matrix.RGBMatrix
    mock_rgbmatrix.RGBMatrixOptions = sim_matrix.RGBMatrixOptions
    mock_rgbmatrix.FrameCanvas = sim_matrix.FrameCanvas
    mock_rgbmatrix.graphics = sim_graphics

    sys.modules["rgbmatrix"] = mock_rgbmatrix
    sys.modules["rgbmatrix.graphics"] = sim_graphics

    logger.info("Registered simulator as rgbmatrix module")


# Map of feature names to their module paths
FEATURE_MODULES = {
    # Existing
    "tic_tac_toe": "src.display.tic_tac_toe",
    "snake": "src.display.snake",
    "pong": "src.display.pong",
    "billiards": "src.display.billiards",
    "time_display": "src.display.time_display",
    "bitcoin_price": "src.display.bitcoin_price",
    "youtube_stream": "src.display.youtube_stream",
    # New visual effects
    "fire": "src.display.fire",
    "plasma": "src.display.plasma",
    "matrix_rain": "src.display.matrix_rain",
    "starfield": "src.display.starfield",
    "game_of_life": "src.display.game_of_life",
    "rainbow_waves": "src.display.rainbow_waves",
    # New info displays
    "weather": "src.display.weather",
    "text_scroller": "src.display.text_scroller",
    "stock_ticker": "src.display.stock_ticker",
    "sp500_heatmap": "src.display.sp500_heatmap",
    "binary_clock": "src.display.binary_clock",
    "countdown": "src.display.countdown",
    "lava_lamp": "src.display.lava_lamp",
    "qr_code": "src.display.qr_code",
    "slideshow": "src.display.slideshow",
    "galaga": "src.display.galaga",
    "space_invaders": "src.display.space_invaders",
    "logo_wholefoods": "src.display.logo_wholefoods",
    "github_stats": "src.display.github_stats",
    "tanks": "src.display.tanks",
}


def run_feature(feature_name, matrix, duration):
    """
    Run a single display feature.

    Args:
        feature_name: Name of the feature to run (must be in FEATURE_MODULES).
        matrix: RGBMatrix instance.
        duration: How long to run the feature in seconds.

    Returns:
        True if feature completed successfully, False on error.
    """
    module_path = FEATURE_MODULES.get(feature_name)
    if not module_path:
        logger.warning("Unknown feature: %s", feature_name)
        return False

    try:
        logger.info("Starting feature: %s (duration: %ds)", feature_name, duration)
        module = importlib.import_module(module_path)

        # Each display module should have a run(matrix, duration) function
        if hasattr(module, "run"):
            module.run(matrix, duration)
        elif hasattr(module, "main"):
            # Fallback to main() for legacy modules
            module.main(matrix, duration)
        else:
            logger.warning("Feature '%s' has no run() or main() function, skipping", feature_name)
            return False

        logger.info("Feature '%s' completed", feature_name)
        return True
    except KeyboardInterrupt:
        raise
    except Exception as e:
        logger.error("Feature '%s' crashed: %s", feature_name, e, exc_info=True)
        # Clear the matrix on crash
        try:
            matrix.Clear()
        except Exception:
            pass
        return False


def _check_schedule():
    """Check if night mode or scheduling should override current settings.
    
    Returns:
        dict with 'brightness' and 'allowed_features' keys, or None for normal mode.
    """
    schedule_path = os.path.join(PROJECT_ROOT, "config", "schedule.json")
    try:
        with open(schedule_path, "r") as f:
            sched = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    
    if not sched.get("enabled", False):
        return None
    
    night = sched.get("night_mode", {})
    if night.get("enabled", False):
        from datetime import datetime
        hour = datetime.now().hour
        start = night.get("start_hour", 22)
        end = night.get("end_hour", 7)
        
        # Check if current hour is in night range
        is_night = False
        if start > end:  # Crosses midnight (e.g., 22-7)
            is_night = hour >= start or hour < end
        else:  # Same day (e.g., 1-5)
            is_night = start <= hour < end
        
        if is_night:
            return {
                "brightness": night.get("brightness", 20),
                "allowed_features": night.get("allowed_features", [])
            }
    
    return None


def _show_pixel_art(matrix):
    """Display pixel art from the web editor."""
    pixel_path = os.path.join(PROJECT_ROOT, "logs", "pixel_art.json")
    try:
        with open(pixel_path, "r") as f:
            data = json.load(f)
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (64, 64))
        pixels = img.load()
        for y in range(64):
            for x in range(64):
                if y < len(data["pixels"]) and x < len(data["pixels"][y]):
                    c = data["pixels"][y][x]
                    pixels[x, y] = (c[0], c[1], c[2])
        matrix.SetImage(img)
        time.sleep(30)  # Show for 30 seconds
    except Exception as e:
        logger.error("Failed to show pixel art: %s", e)


def _handle_command(cmd, matrix, duration):
    """Handle a web panel command."""
    cmd_type = cmd.get("command")
    cmd_data = cmd.get("data", {})

    if cmd_type == "play_video":
        url = cmd_data.get("url")
        title = cmd_data.get("title", "Unknown")
        if url:
            handle_play_video(matrix, url, title, duration=duration)
    elif cmd_type == "play_feature":
        feat_name = cmd_data.get("feature")
        if feat_name:
            logger.info("Command: switch to %s", feat_name)
            clear_stop()
            write_status(feat_name, "running")
            run_feature(feat_name, matrix, duration)
    elif cmd_type == "set_brightness":
        brightness = cmd_data.get("brightness", 100)
        try:
            matrix.brightness = brightness
            logger.info("Brightness set to %d", brightness)
        except Exception:
            pass
    elif cmd_type == "show_pixel_art":
        _show_pixel_art(matrix)


def ensure_wifi():
    """
    Ensure WiFi connectivity before starting display loop.

    Returns:
        True if connected, False if connection failed.
    """
    try:
        from src.wifi import WiFiManager
        wifi = WiFiManager()
        return wifi.ensure_connection()
    except ImportError:
        logger.warning("WiFi manager not available, assuming connected")
        return True
    except Exception as e:
        logger.warning("WiFi check failed: %s, continuing anyway", e)
        return True


def main():
    """Main entry point: initialize matrix and run feature loop."""
    # Setup logging
    log_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                os.path.join(log_dir, "display.log"),
                mode="a"
            )
        ]
    )

    logger.info("=" * 60)
    logger.info("LED Matrix Project starting up")
    logger.info("=" * 60)

    # Register simulator as rgbmatrix if real hardware library is unavailable.
    # Must happen before any display modules are imported, since they do
    # 'from rgbmatrix import ...' at the top level.
    _register_simulator_modules()

    # Validate configuration
    from src.config_validator import validate_all
    validation_results = validate_all()
    for config_name, errors in validation_results.items():
        for err in errors:
            if err.severity == "error":
                logger.error("Config validation: %s -> %s", config_name, err)
            else:
                logger.warning("Config validation: %s -> %s", config_name, err)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Web panel integration: write PID, start uptime timer, register SIGHUP
    write_pid()
    write_status._start_time = time.time()
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, sighup_handler)

    # Ensure WiFi connectivity
    logger.info("Checking WiFi connectivity...")
    if ensure_wifi():
        logger.info("WiFi connectivity confirmed")
    else:
        logger.warning("WiFi connection failed - some features may not work")

    # Load configuration
    config = load_config()
    duration = config.get("display_duration", 60)
    sequence = config.get("sequence", [])

    # Filter to enabled features only
    enabled_features = [f for f in sequence if f.get("enabled", False)]

    if not enabled_features:
        logger.error("No features enabled in config. Enable at least one feature in config/config.json")
        sys.exit(1)

    logger.info("Enabled features: %s", [f["name"] for f in enabled_features])

    # Initialize the matrix
    matrix = init_matrix()

    # Store matrix reference for web panel preview
    import src.main as _self_module
    _self_module._matrix_ref = matrix

    # Main display loop
    logger.info("Entering display loop...")
    while not _shutdown:
        for feature in enabled_features:
            if _shutdown:
                break

            # Check for commands before each feature
            cmd = check_command()
            if cmd:
                _handle_command(cmd, matrix, duration)
                continue

            name = feature.get("name", "unknown")
            feat_duration = feature.get("duration", duration)  # Per-feature or global
            clear_stop()
            write_status(name, "running")
            run_feature(name, matrix, feat_duration)

            # Brief pause + command check between features
            if not _shutdown:
                time.sleep(0.5)
                cmd = check_command()
                if cmd:
                    _handle_command(cmd, matrix, duration)

        # Reload config between full cycles to pick up changes
        if not _shutdown:
            config = load_config()
            duration = config.get("display_duration", 60)
            sequence = config.get("sequence", [])
            enabled_features = [f for f in sequence if f.get("enabled", False)]

            # Check night mode / scheduling
            schedule_override = _check_schedule()
            if schedule_override:
                # Apply brightness
                try:
                    matrix.brightness = schedule_override["brightness"]
                except Exception:
                    pass
                # Filter features if night mode specifies allowed list
                allowed = schedule_override.get("allowed_features", [])
                if allowed:
                    enabled_features = [f for f in enabled_features if f.get("name") in allowed]
                    if not enabled_features:
                        # Fallback to time display
                        enabled_features = [{"name": "time_display", "type": "utility", "enabled": True}]

            if not enabled_features:
                logger.warning("No features enabled after config reload, waiting 30s...")
                time.sleep(30)

    write_status(None, "stopped")

    # Cleanup
    logger.info("Shutting down, clearing matrix...")
    try:
        matrix.Clear()
    except Exception:
        pass
    logger.info("LED Matrix Project stopped")


if __name__ == "__main__":
    main()
