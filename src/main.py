#!/usr/bin/env python3
"""
LED Matrix Project - Main Entry Point

Reads config/config.json and cycles through enabled display features
on a 64x64 RGB LED matrix. Designed for Raspberry Pi with rpi-rgb-led-matrix.

Control is via a USB gamepad (with keyboard fallback in the simulator) through
:class:`src.input.Controller` and :class:`src.app_state.AppStateMachine`. The
former Flask web control panel was removed in Phase 6 (CONTROLLER_OVERHAUL.md
§7); there is no longer any command.json / status.json / preview.png / PID
plumbing.
"""

import json
import importlib
import logging
import os
import sys
import time
import signal
import threading

from src.display._shared import request_stop, should_stop

logger = logging.getLogger(__name__)

# Features that require internet connectivity
INTERNET_FEATURES = {"bitcoin_price", "weather", "stock_ticker", "sp500_heatmap",
                     "video_player", "github_stats"}


def _check_internet(timeout=3):
    """Quick connectivity check. Returns True if internet is reachable.

    The endpoint is configurable via config.json -> internet_check_url.
    Defaults to Google's connectivity check endpoint (returns 204, very fast).
    """
    # Load configurable endpoint (fallback to reliable Google endpoint)
    url = "http://connectivitycheck.gstatic.com/generate_204"
    try:
        config_path = os.path.join(PROJECT_ROOT, "config", "config.json")
        with open(config_path, "r") as f:
            cfg = json.load(f)
        url = cfg.get("internet_check_url", url)
    except Exception:
        pass

    try:
        import requests
        requests.head(url, timeout=timeout)
        return True
    except Exception:
        return False


def _run_feature_with_watchdog(feature_callable, duration, feature_name):
    """Run a feature with a watchdog timeout. Returns True if completed normally.

    Args:
        feature_callable: A no-arg callable (closure) that runs the feature.
        duration: The configured duration, used to derive the watchdog timeout.
        feature_name: Name of the feature for logging.
    """
    timeout = max(duration * 2, 60)  # At least 60 seconds, or 2x duration

    thread = threading.Thread(target=feature_callable, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        logger.warning("Watchdog: %s hung after %ds, forcing stop", feature_name, timeout)
        request_stop()
        thread.join(timeout=5)  # Give it 5 more seconds after stop request
        if thread.is_alive():
            logger.error("Watchdog: %s did not respond to stop request", feature_name)
        return False
    return True


# Project root is one level up from this file
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Add project root to path for imports
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# Flag for graceful shutdown (thread-safe Event instead of bare bool)
_shutdown = threading.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Received signal %d, shutting down...", signum)
    _shutdown.set()


def sighup_handler(signum, frame):
    """Handle SIGHUP for config reload."""
    logger.info("Received SIGHUP, config will reload on next cycle")


def handle_play_video(matrix, url, title="Unknown", duration=300):
    """Handle a play_video request by playing a video from cache.

    Checks the local cache first (downloaded_videos/<md5hash>.mp4).
    Only cached videos are supported -- add URLs to config/video_urls.csv
    and reboot to download them.

    Playback breaks out within one frame when ``should_stop()`` is set (the
    state machine's input thread sets this on a START press), so video remains a
    carousel demo that the user can interrupt to open the menu.

    Args:
        matrix: RGBMatrix instance.
        url: Direct video URL.
        title: Video title for logging.
        duration: Max playback duration in seconds.
    """
    logger.info("Playing video: %s (%s)", title, url)
    try:
        from src.display.video_player import FRAME_INTERVAL, _url_to_cache_path, _is_cached
        import cv2
        from PIL import Image

        if _is_cached(url):
            video_url = _url_to_cache_path(url)
            logger.info("Playing from local cache: %s", video_url)
        else:
            logger.warning("Video not cached: %s -- add to config/video_urls.csv and reboot", url)
            return

        cap = cv2.VideoCapture(video_url)
        if not cap.isOpened():
            logger.error("Failed to open video: %s", video_url)
            return

        start = time.time()
        while cap.isOpened() and not _shutdown.is_set():
            frame_start = time.time()

            # Video interruption honors the shared stop flag (should_stop()),
            # which the state machine's input thread sets on a START press --
            # this breaks out within one frame when the user opens the menu.
            if should_stop():
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


class _SafeMatrixProxy:
    """Thin proxy around the real RGBMatrix that catches OverflowError in SetImage.

    On 32-bit ARM (Raspberry Pi), Pillow's unsafe_ptrs can return a pointer
    value that overflows uintptr_t in the Cython binding's SetPixelsPillow.
    This proxy intercepts SetImage, catches OverflowError, and retries with
    unsafe=False to use the safe tobytes() code path instead.

    All other attribute accesses are delegated transparently to the real matrix.
    """

    def __init__(self, matrix):
        object.__setattr__(self, '_matrix', matrix)

    def SetImage(self, image, offset_x=0, offset_y=0, unsafe=True):
        try:
            self._matrix.SetImage(image, offset_x, offset_y, unsafe)
        except OverflowError:
            self._matrix.SetImage(image, offset_x, offset_y, unsafe=False)

    def __getattr__(self, name):
        return getattr(self._matrix, name)

    def __setattr__(self, name, value):
        if name == '_matrix':
            object.__setattr__(self, name, value)
        else:
            setattr(self._matrix, name, value)


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

        # Wrap in a proxy to handle OverflowError from Pillow unsafe_ptrs on
        # 32-bit ARM. Cython extension types don't allow attribute assignment,
        # so we use a thin proxy that intercepts SetImage calls.
        return _SafeMatrixProxy(matrix)
    except ImportError:
        logger.warning("rgbmatrix not available - using simulator")
        return _create_simulator_matrix()
    except Exception as e:
        logger.error("Failed to initialize matrix: %s", e, exc_info=True)
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


# Import canonical feature registry (single source of truth)
from src.feature_registry import FEATURE_MODULES


def run_feature(feature_name, matrix, duration, controller=None):
    """
    Run a single display feature.

    Args:
        feature_name: Name of the feature to run (must be in FEATURE_MODULES).
        matrix: RGBMatrix instance.
        duration: How long to run the feature in seconds.
        controller: Optional src.input.Controller. When provided AND the target
            module's run() accepts a ``controller`` parameter, the feature is
            launched in INTERACTIVE mode (playable game, CONTROLLER_OVERHAUL.md
            §5.1). Demos always call with controller=None and behave exactly as
            before. Modules not yet converted simply never receive a controller
            because the idle carousel never passes one.

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

        # Forward the controller only when one was supplied AND the module's
        # run() advertises a 'controller' parameter (introspected to stay
        # backward compatible with the run(matrix, duration) contract).
        pass_controller = False
        if controller is not None and hasattr(module, "run"):
            try:
                import inspect
                params = inspect.signature(module.run).parameters
                pass_controller = "controller" in params
            except (TypeError, ValueError):
                pass_controller = False

        # Each display module should have a run(matrix, duration) function
        if hasattr(module, "run"):
            if pass_controller:
                feature_callable = lambda: module.run(
                    matrix, duration, controller=controller
                )
            else:
                feature_callable = lambda: module.run(matrix, duration)
        elif hasattr(module, "main"):
            # Fallback to main() for legacy modules
            feature_callable = lambda: module.main(matrix, duration)
        else:
            logger.warning("Feature '%s' has no run() or main() function, skipping", feature_name)
            return False

        # Use watchdog timer to kill hung features (timeout = 2x duration, min 60s)
        completed = _run_feature_with_watchdog(feature_callable, duration, feature_name)
        if completed:
            logger.info("Feature '%s' completed", feature_name)
        return completed
    except KeyboardInterrupt:
        raise
    except Exception as e:
        logger.error("Feature '%s' crashed: %s", feature_name, e, exc_info=True)
        # Track last error for diagnostics
        try:
            error_path = os.path.join(PROJECT_ROOT, "logs", "feature_error.json")
            with open(error_path, "w") as ef:
                json.dump({
                    "feature": feature_name,
                    "error": str(e),
                    "time": time.time()
                }, ef)
        except Exception:
            pass
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

    from datetime import datetime
    hour = datetime.now().hour

    night = sched.get("night_mode", {})
    if night.get("enabled", False):
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

    # --- Feature schedules (first matching wins) ---
    for entry in sched.get("schedules", []):
        s = entry.get("start_hour", 0)
        e = entry.get("end_hour", 0)
        if s == e:
            continue  # Skip invalid entries
        in_range = (hour >= s or hour < e) if s > e else (s <= hour < e)
        if in_range:
            result = {
                "allowed_features": entry.get("allowed_features", [])
            }
            brightness = entry.get("brightness")
            if brightness is not None:
                result["brightness"] = brightness
            return result

    return None


# Maximum time (seconds) the video precache can run at boot.
# Prevents the Pi from being saturated by downloads forever.
_PRECACHE_TIMEOUT = 180


def _precache_videos(matrix, enabled_features):
    """Pre-download videos at boot with a loading ring animation.

    Runs only if video_player (or legacy youtube_stream) is in the
    enabled features list. Downloads happen in a LOW-PRIORITY background
    thread with a hard timeout so the Pi stays responsive for the
    display. Already-cached videos are detected instantly.
    """
    # Check if video_player or legacy youtube_stream is enabled
    vp_enabled = any(f.get("name") in ("video_player", "youtube_stream")
                     for f in enabled_features)
    if not vp_enabled:
        return

    logger.info("Video player enabled -- pre-caching videos at boot (timeout: %ds)...",
                _PRECACHE_TIMEOUT)

    try:
        from src.display.video_player import (
            _ensure_dependencies, read_urls_from_csv,
            download_video, _is_cached, _get_csv_path
        )
    except ImportError as e:
        logger.warning("Cannot import video_player for precaching: %s", e)
        return

    if not _ensure_dependencies():
        logger.warning("Video player dependencies missing, skipping precache")
        return

    csv_path = _get_csv_path()
    urls = read_urls_from_csv(csv_path)
    if not urls:
        logger.info("No video URLs to precache")
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
            if _shutdown.is_set() or time.time() > boot_deadline:
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
            # (prevents CPU/network saturation)
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
        logger.info("Video precache: %d cached, %d failed, %d deferred to next boot", d, f, remaining)
    else:
        logger.info("Video precache complete: %d/%d cached, %d failed", d, t, f)


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
    """Main entry point: initialize matrix and run the controller state machine."""
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
    sequence = config.get("sequence", [])

    # Filter to enabled features only
    enabled_features = [f for f in sequence if f.get("enabled", False)]

    if not enabled_features:
        logger.error("No features enabled in config. Enable at least one feature in config/config.json")
        sys.exit(1)

    logger.info("Enabled features: %s", [f["name"] for f in enabled_features])

    # Pre-cache videos at boot if video_player is enabled.
    # Downloads happen in a background thread while a loading ring
    # animates on the matrix. If no internet, this gracefully skips.
    _precache_videos(matrix, enabled_features)

    # --- Controller + state machine ------------------------------------------
    # Construct ONE shared Controller (pygame has a single global event queue,
    # so there must be exactly one owner; see src/input/controller.py). The
    # constructor degrades gracefully when no gamepad / no display is present
    # (keyboard fallback in the simulator, no-op on a truly headless Pi), so
    # this never crashes the boot path.
    from src.input import Controller
    from src.app_state import AppStateMachine

    try:
        controller = Controller()
        if controller.is_connected():
            logger.info("Gamepad connected")
        else:
            logger.info(
                "No gamepad connected; running with keyboard fallback / "
                "demo-only idle until one is plugged in"
            )
    except Exception as e:  # noqa: BLE001 - never let input init break boot
        logger.warning("Controller init failed (%s); continuing without input", e)
        controller = None

    if controller is not None:
        # Delegate the whole run loop to the state machine. It owns the matrix,
        # cycles demos in IDLE, opens the menu on START, launches games, and
        # observes window-close via controller.is_quitting().
        state = AppStateMachine(matrix, controller, config,
                                shutdown_event=_shutdown)
        logger.info("Entering state machine loop...")
        try:
            state.run()
        finally:
            try:
                controller.close()
            except Exception:  # noqa: BLE001
                pass
    else:
        # Degraded fallback: no controller at all (e.g. pygame totally absent).
        # Run the demo carousel directly so the matrix still cycles features.
        from src.app_state import DemoCarousel
        logger.info("Entering demo-only loop (no controller available)...")
        carousel = DemoCarousel(matrix, config, _shutdown)
        while not _shutdown.is_set():
            carousel.run_cycle()

    # Cleanup
    logger.info("Shutting down, clearing matrix...")
    try:
        matrix.Clear()
    except Exception:
        pass
    logger.info("LED Matrix Project stopped")


if __name__ == "__main__":
    main()
