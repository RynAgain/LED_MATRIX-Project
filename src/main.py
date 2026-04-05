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

# Pending command detected by the background watcher thread
_pending_command = None
_pending_lock = threading.Lock()


def check_command():
    """Check for and consume a command from the web panel.
    
    First checks the pending command buffer (set by the background watcher),
    then falls back to reading the command file directly.
    
    Returns:
        dict with 'command' and 'data' keys, or None if no command.
    """
    global _pending_command

    # Check pending command from background watcher first
    with _pending_lock:
        if _pending_command is not None:
            cmd = _pending_command
            _pending_command = None
            logger.info("Command consumed from pending buffer: %s", cmd.get("command"))
            return cmd

    # Fallback: direct file check (for commands arriving between watcher polls)
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


def _command_watcher():
    """Background thread that polls command.json every 0.5s.

    When a new command arrives, it stores the command in the pending buffer
    and calls request_stop() so the currently-running display module breaks
    out of its render loop immediately (within one frame / ~55ms).
    """
    global _pending_command
    logger.info("Command watcher thread started")
    while not _shutdown:
        try:
            if os.path.exists(COMMAND_PATH):
                mtime = os.path.getmtime(COMMAND_PATH)
                if time.time() - mtime < 30:
                    with open(COMMAND_PATH, "r") as f:
                        cmd = json.load(f)
                    os.remove(COMMAND_PATH)
                    with _pending_lock:
                        _pending_command = cmd
                    # Signal the running display module to stop NOW
                    request_stop()
                    logger.info("Command watcher: detected '%s', requested stop",
                                cmd.get("command"))
                else:
                    # Stale command, remove it
                    try:
                        os.remove(COMMAND_PATH)
                    except OSError:
                        pass
        except (json.JSONDecodeError, OSError, KeyError):
            pass
        # Poll interval: 0.5 seconds for responsive UI
        time.sleep(0.5)
    logger.info("Command watcher thread stopped")


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


# Minimal fallback config so the system can boot even with a corrupt config.json.
# Shows time_display so the user at least sees something on the matrix.
_DEFAULT_CONFIG = {
    "display_duration": 60,
    "sequence": [
        {"name": "time_display", "type": "utility", "enabled": True},
        {"name": "fire", "type": "effect", "enabled": True},
    ]
}


def load_config():
    """
    Load display sequence configuration.

    Falls back to a minimal default config if the file is missing or corrupt,
    instead of crashing. This prevents boot loops when config.json gets
    corrupted (e.g., by a failed write or disk issue).

    Returns:
        dict: Configuration dictionary with sequence and settings.
    """
    config_path = os.path.join(PROJECT_ROOT, "config", "config.json")
    try:
        with open(config_path, "r") as f:
            content = f.read().strip()
        if not content:
            raise json.JSONDecodeError("Empty file", "", 0)
        config = json.loads(content)
        logger.info("Loaded config from %s", config_path)
        return config
    except FileNotFoundError:
        logger.error("Config file not found: %s -- using defaults", config_path)
        return _DEFAULT_CONFIG.copy()
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in config: %s -- using defaults", e)
        logger.error("Fix your config/config.json or re-download it from GitHub")
        return _DEFAULT_CONFIG.copy()


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

    Reads hardware parameters from config/config.json -> "matrix_hardware".
    If no hardware config exists, uses sensible defaults for a 64x64 panel.

    On Raspberry Pi: uses the real rgbmatrix library.
    On other platforms: falls back to pygame-based simulator.
    """
    # Load hardware config (or use defaults)
    hw = _load_hardware_config()

    try:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        options = RGBMatrixOptions()
        options.rows = hw.get("rows", 64)
        options.cols = hw.get("cols", 64)
        options.chain_length = hw.get("chain_length", 1)
        options.parallel = hw.get("parallel", 1)
        options.hardware_mapping = hw.get("hardware_mapping", "regular")
        options.gpio_slowdown = hw.get("gpio_slowdown", 4)
        options.brightness = hw.get("brightness", 80)
        options.drop_privileges = hw.get("drop_privileges", False)
        options.pwm_bits = hw.get("pwm_bits", 11)
        options.pwm_lsb_nanoseconds = hw.get("pwm_lsb_nanoseconds", 130)
        options.pwm_dither_bits = hw.get("pwm_dither_bits", 0)
        options.scan_mode = hw.get("scan_mode", 0)
        options.multiplexing = hw.get("multiplexing", 0)
        options.row_address_type = hw.get("row_address_type", 0)
        options.disable_hardware_pulsing = hw.get("disable_hardware_pulsing", False)

        pixel_mapper = hw.get("pixel_mapper", "")
        if pixel_mapper:
            options.pixel_mapper_config = pixel_mapper

        total_w = options.cols * options.chain_length
        total_h = options.rows * options.parallel
        matrix = RGBMatrix(options=options)
        logger.info("RGB LED Matrix initialized (%dx%d, mapping=%s, slowdown=%d)",
                     total_w, total_h, options.hardware_mapping, options.gpio_slowdown)
        return matrix
    except ImportError:
        logger.warning("rgbmatrix not available - using simulator")
        return _create_simulator_matrix()
    except Exception as e:
        logger.error("Failed to initialize matrix: %s", e)
        logger.warning("Falling back to simulator")
        return _create_simulator_matrix()


def _load_hardware_config():
    """Load matrix hardware settings from config/config.json.

    Returns:
        dict with hardware parameters. Falls back to empty dict (defaults)
        if the key is missing or the file cannot be read.
    """
    config_path = os.path.join(PROJECT_ROOT, "config", "config.json")
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        hw = config.get("matrix_hardware", {})
        if hw:
            logger.info("Loaded matrix hardware config: %dx%d, mapping=%s",
                        hw.get("rows", 64), hw.get("cols", 64),
                        hw.get("hardware_mapping", "regular"))
        else:
            logger.info("No matrix_hardware in config, using defaults. "
                        "Run: sudo bash scripts/configure_matrix.sh")
        return hw
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Could not read hardware config: %s, using defaults", e)
        return {}


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
    "living_world": "src.display.living_world",
    "qr_code": "src.display.qr_code",
    "slideshow": "src.display.slideshow",
    "galaga": "src.display.galaga",
    "space_invaders": "src.display.space_invaders",
    "logo_wholefoods": "src.display.logo_wholefoods",
    "github_stats": "src.display.github_stats",
    "tanks": "src.display.tanks",
    "wireframe": "src.display.wireframe",
    "maze_3d": "src.display.maze_3d",
    "terrain_ball": "src.display.terrain_ball",
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


# Maximum time (seconds) the YouTube precache can run at boot.
# Prevents the Pi from being saturated by downloads forever.
_PRECACHE_TIMEOUT = 180


def _precache_youtube_videos(matrix, enabled_features):
    """Pre-download YouTube videos at boot with a loading ring animation.

    Runs only if youtube_stream is in the enabled features list.
    Downloads happen in a LOW-PRIORITY background thread with a hard
    timeout so the Pi stays responsive for the web panel and display.
    Already-cached videos are detected instantly (no download).
    """
    # Check if youtube_stream is enabled
    yt_enabled = any(f.get("name") == "youtube_stream" for f in enabled_features)
    if not yt_enabled:
        return

    logger.info("YouTube is enabled -- pre-caching videos at boot (timeout: %ds)...",
                _PRECACHE_TIMEOUT)

    try:
        from src.display.youtube_stream import (
            _ensure_dependencies, read_urls_from_csv,
            download_video, _is_cached
        )
    except ImportError as e:
        logger.warning("Cannot import youtube_stream for precaching: %s", e)
        return

    if not _ensure_dependencies():
        logger.warning("YouTube dependencies missing, skipping precache")
        return

    # Skip yt-dlp update at boot -- it's CPU-heavy and the updater timer
    # handles it separately. Videos will download fine with the current version.

    csv_path = os.path.join(PROJECT_ROOT, "config", "youtube_urls.csv")
    urls = read_urls_from_csv(csv_path)
    if not urls:
        logger.info("No YouTube URLs to precache")
        return

    # Check how many are already cached (instant, no downloads)
    already_cached = sum(1 for url, _, _ in urls if _is_cached(url))
    if already_cached == len(urls):
        logger.info("All %d videos already cached, skipping precache", already_cached)
        return

    logger.info("%d/%d videos already cached, downloading remaining...",
                already_cached, len(urls))

    # Shared state between download thread and animation thread
    status = {"downloaded": already_cached, "failed": 0, "total": len(urls), "current": ""}
    done_event = threading.Event()
    boot_deadline = time.time() + _PRECACHE_TIMEOUT

    def get_status():
        d = status["downloaded"]
        t = status["total"]
        current = status["current"]
        line1 = f"CACHING {d}/{t}"
        line2 = current[:10] if current else ""
        return line1, line2

    def download_worker():
        for url, title, dur in urls:
            if _shutdown or time.time() > boot_deadline:
                if time.time() > boot_deadline:
                    logger.info("Precache timeout reached, stopping downloads")
                break

            status["current"] = title

            if _is_cached(url):
                # Already counted above, skip
                continue

            # Single attempt at boot (retries waste too much time)
            logger.info("Downloading '%s'...", title)
            path = download_video(url, title)

            if path:
                status["downloaded"] += 1
                logger.info("Cached '%s' (%d/%d)",
                            title, status["downloaded"], status["total"])
            else:
                status["failed"] += 1
                logger.warning("Failed to cache '%s' (%d failed)",
                               title, status["failed"])

            # Brief pause between downloads to let the Pi breathe
            # (prevents CPU/network saturation that kills the web panel)
            time.sleep(1)

        status["current"] = ""
        done_event.set()

    # Start download in LOW-PRIORITY background thread
    dl_thread = threading.Thread(target=download_worker, daemon=True)
    dl_thread.start()

    # Show loading ring animation while downloading (with hard timeout)
    try:
        from src.display.boot_screen import show_loading_ring
        show_loading_ring(matrix, get_status, done_event)
    except Exception as e:
        logger.warning("Loading ring animation failed: %s", e)
        dl_thread.join(timeout=_PRECACHE_TIMEOUT)

    # Don't wait forever for the download thread
    dl_thread.join(timeout=5)

    d = status["downloaded"]
    f = status["failed"]
    t = status["total"]
    remaining = t - d - f
    if remaining > 0:
        logger.info("YouTube precache: %d cached, %d failed, %d deferred to next boot", d, f, remaining)
    else:
        logger.info("YouTube precache complete: %d/%d cached, %d failed", d, t, f)


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

    # Initialize matrix and show boot screen FIRST for immediate visual feedback.
    # WiFi and config loading happen after, so the user sees something right away.
    matrix = init_matrix()

    try:
        from src.display.boot_screen import show as show_boot_screen
        show_boot_screen(matrix)
    except Exception as e:
        logger.warning("Boot screen failed (non-fatal): %s", e)

    # Now do the slower startup tasks (WiFi, config)
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

    # Pre-cache YouTube videos at boot if youtube_stream is enabled.
    # Downloads happen in a background thread while a loading ring
    # animates on the matrix. If no internet, this gracefully skips.
    _precache_youtube_videos(matrix, enabled_features)

    # Store matrix reference for web panel preview
    import src.main as _self_module
    _self_module._matrix_ref = matrix

    # Start background command watcher thread
    # This thread polls command.json every 0.5s and calls request_stop()
    # so the currently running display module breaks out immediately.
    watcher = threading.Thread(target=_command_watcher, daemon=True)
    watcher.start()

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

            # After a feature returns (naturally or via should_stop()),
            # check if the watcher detected a command that caused the stop.
            cmd = check_command()
            if cmd:
                _handle_command(cmd, matrix, duration)
                continue

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
