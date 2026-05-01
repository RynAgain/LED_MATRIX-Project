"""
YouTube video streaming for 64x64 LED matrix.

Downloads YouTube videos to local cache at low resolution, then plays
from disk. Uses a background thread to download videos concurrently
with playback -- plays each video as soon as it's ready.

Architecture:
  - Background thread downloads videos to downloaded_videos/
  - Main thread plays videos from local cache as they become available
  - Already-cached videos play immediately (no download wait)
  - New videos download in background and are available for future cycles
  - Downloads persist across reboots (only downloaded once per URL)

Requires: yt-dlp, opencv-python-headless, numpy, Pillow
"""

import os
import sys
import time
import csv
import subprocess
import hashlib
import logging
import threading
import queue
from PIL import Image
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

# Lazy imports for heavy dependencies
cv2 = None
np = None
yt_dlp = None

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(PROJECT_ROOT, "downloaded_videos")

# Target frame rate for playback on 64x64 matrix.
TARGET_FPS = 15
FRAME_INTERVAL = 1.0 / TARGET_FPS

# Maximum resolution to download (we resize to 64x64 anyway)
MAX_HEIGHT = 240


def _ensure_dependencies():
    """Lazy-import heavy dependencies. Returns True if all available."""
    global cv2, np, yt_dlp
    if cv2 is not None and yt_dlp is not None:
        return True

    missing = []
    try:
        import cv2 as _cv2
        cv2 = _cv2
    except ImportError:
        missing.append("opencv-python-headless")

    try:
        import numpy as _np
        np = _np
    except ImportError:
        missing.append("numpy")

    try:
        import yt_dlp as _yt_dlp
        yt_dlp = _yt_dlp
    except ImportError:
        missing.append("yt-dlp")

    if missing:
        logger.error("Missing dependencies for YouTube streaming: %s", ", ".join(missing))
        logger.error("Install with: pip install %s", " ".join(missing))
        return False
    return True


def _update_ytdlp():
    """Update yt-dlp from GitHub source (latest fixes, ahead of PyPI).

    YouTube frequently changes their extraction methods. Installing from
    GitHub master gets fixes hours before they hit PyPI. Falls back to
    PyPI if GitHub source fails.
    """
    try:
        logger.info("Updating yt-dlp from GitHub source...")
        # Try GitHub source first (most up-to-date)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet",
             "yt-dlp @ https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz"],
            capture_output=True, text=True, timeout=90
        )
        if result.returncode != 0:
            # Fallback to PyPI
            logger.info("GitHub source failed, falling back to PyPI...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", "yt-dlp"],
                capture_output=True, text=True, timeout=60
            )

        if result.returncode == 0:
            logger.info("yt-dlp updated successfully")
            import importlib
            global yt_dlp
            if yt_dlp is not None:
                yt_dlp = importlib.reload(yt_dlp)
            else:
                import yt_dlp as _yt_dlp
                yt_dlp = _yt_dlp
        else:
            logger.warning("yt-dlp update failed: %s", result.stderr.strip()[:200])
    except Exception as e:
        logger.warning("Could not update yt-dlp: %s", e)


def refresh_youtube_cookies():
    """Extract fresh YouTube cookies from the system browser at boot.

    Uses yt-dlp's --cookies-from-browser to pull cookies from Chromium
    (or Chrome/Firefox as fallback). This bypasses YouTube's bot-detection
    (HTTP 403) that blocks headless downloads without a valid session.

    Saves cookies to config/yt_cookies.txt which download_video() picks up.
    Called once at boot before the precache phase.

    Returns:
        True if cookies were successfully extracted, False otherwise.
    """
    cookies_path = os.path.join(PROJECT_ROOT, "config", "yt_cookies.txt")

    # Try browsers in order of likelihood on a Pi
    browsers = ["chromium", "chrome", "firefox", "chromium-browser"]

    for browser in browsers:
        try:
            logger.info("Extracting YouTube cookies from %s...", browser)
            result = subprocess.run(
                [
                    sys.executable, "-m", "yt_dlp",
                    "--cookies-from-browser", browser,
                    "--cookies", cookies_path,
                    "--skip-download",
                    "--quiet",
                    "https://www.youtube.com",
                ],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and os.path.exists(cookies_path):
                size = os.path.getsize(cookies_path)
                if size > 100:
                    logger.info("YouTube cookies extracted from %s (%d bytes)", browser, size)
                    return True
                else:
                    logger.warning("Cookie file from %s is too small (%d bytes), trying next", browser, size)
            else:
                logger.debug("Browser %s failed (rc=%d): %s", browser, result.returncode,
                             result.stderr.strip()[:200])
        except FileNotFoundError:
            logger.debug("Browser %s not found, trying next", browser)
        except subprocess.TimeoutExpired:
            logger.warning("Cookie extraction from %s timed out", browser)
        except Exception as e:
            logger.warning("Cookie extraction from %s failed: %s", browser, e)

    logger.warning(
        "Could not extract YouTube cookies from any browser. "
        "Downloads may fail with HTTP 403. "
        "To fix manually: yt-dlp --cookies-from-browser chromium "
        "--cookies config/yt_cookies.txt --skip-download https://www.youtube.com"
    )
    return False


def _url_to_cache_path(url):
    """Generate a deterministic cache filename from a URL."""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{url_hash}.mp4")


def _is_cached(url):
    """Check if a video is already downloaded and valid."""
    path = _url_to_cache_path(url)
    if not os.path.exists(path):
        return False
    size = os.path.getsize(path)
    if size < 10240:
        logger.warning("Cached file too small (%d bytes), will re-download: %s", size, path)
        try:
            os.remove(path)
        except OSError:
            pass
        return False
    return True


def _check_disk_space(path, min_mb=200):
    """Check if there's enough disk space for a video download.

    Args:
        path: Directory path to check free space on.
        min_mb: Minimum free megabytes required.

    Returns:
        True if sufficient space is available (or check cannot be performed).
    """
    try:
        import shutil
        usage = shutil.disk_usage(path)
        free_mb = usage.free / (1024 * 1024)
        if free_mb < min_mb:
            logger.warning("Low disk space: %.0f MB free (need %d MB)", free_mb, min_mb)
            return False
        return True
    except Exception:
        return True  # Can't check, proceed anyway


def download_video(url, title="Unknown"):
    """Download a YouTube video to local cache at low resolution.

    Args:
        url: YouTube video URL.
        title: Video title for logging.

    Returns:
        Path to the downloaded file, or None on failure.
    """
    if yt_dlp is None:
        logger.error("yt-dlp not available")
        return None

    cache_path = _url_to_cache_path(url)

    if _is_cached(url):
        logger.info("Already cached: '%s'", title)
        return cache_path

    os.makedirs(CACHE_DIR, exist_ok=True)

    # Check disk space before attempting download
    if not _check_disk_space(CACHE_DIR):
        logger.error("Insufficient disk space for video download of '%s'", title)
        return None

    # Request only pre-merged formats (video+audio in one file) so yt-dlp
    # does NOT need ffmpeg to merge separate streams. This is the #1 cause
    # of silent download failures on fresh Pi installs without ffmpeg.
    # The 'b' prefix means "best" pre-merged format at that quality level.
    ydl_opts = {
        'format': (
            # Pre-merged formats only (no separate audio+video requiring ffmpeg merge):
            f'best[height<={MAX_HEIGHT}][ext=mp4][vcodec!=none][acodec!=none]/'
            f'best[height<={MAX_HEIGHT}][vcodec!=none][acodec!=none]/'
            'worst[vcodec!=none][acodec!=none]/'
            f'best[height<={MAX_HEIGHT}]/'
            'worst/'
            'best'
        ),
        'outtmpl': cache_path,
        # Don't silence errors -- we need to see what's failing
        'quiet': False,
        'no_warnings': False,
        'verbose': False,
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 3,
        # Do NOT set merge_output_format -- avoids ffmpeg dependency
        'postprocessors': [],
        # Write to a temp file first, rename on success
        'nopart': True,
        # HTTP headers to reduce bot-detection fingerprinting
        'http_headers': {
            'User-Agent': (
                'Mozilla/5.0 (Linux; Android 11; Pixel 5) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Mobile Safari/537.36'
            ),
        },
    }

    # Use cookies file if present (fixes HTTP 403 bot-detection on Pi).
    # Export from Chrome/Firefox on your desktop:
    #   yt-dlp --cookies-from-browser chrome --cookies config/yt_cookies.txt ""
    # or use a browser extension like "Get cookies.txt LOCALLY".
    cookies_path = os.path.join(PROJECT_ROOT, "config", "yt_cookies.txt")
    if os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path
        logger.info("Using cookies file for YouTube download: %s", cookies_path)
    else:
        logger.debug("No cookies file found at %s -- downloads may 403 on some videos", cookies_path)

    logger.info("Downloading '%s'...", title)
    start = time.time()

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                logger.info("Download info: format=%s, height=%s, ext=%s",
                            info.get('format', '?'),
                            info.get('height', '?'),
                            info.get('ext', '?'))

        elapsed = time.time() - start

        # Check for the file -- yt-dlp may use a different extension
        if os.path.exists(cache_path):
            size_mb = os.path.getsize(cache_path) / (1024 * 1024)
            logger.info("Downloaded '%s' (%.1f MB) in %.1fs", title, size_mb, elapsed)
            return cache_path

        # Search for any file matching our hash prefix
        prefix = os.path.splitext(os.path.basename(cache_path))[0]
        for f in os.listdir(CACHE_DIR):
            if f.startswith(prefix) and not f.endswith('.part'):
                actual_path = os.path.join(CACHE_DIR, f)
                size = os.path.getsize(actual_path)
                if size > 1024:  # Must be > 1KB
                    # Rename to expected .mp4 path for consistent lookup
                    if actual_path != cache_path:
                        try:
                            os.rename(actual_path, cache_path)
                            logger.info("Renamed %s -> %s", f, os.path.basename(cache_path))
                        except OSError:
                            cache_path = actual_path
                    logger.info("Downloaded '%s' (%.1f MB) in %.1fs",
                                title, size / (1024 * 1024), elapsed)
                    return cache_path

        logger.error("Download appeared to complete but no file found for '%s'. "
                      "Expected: %s", title, cache_path)
        return None

    except Exception as e:
        logger.error("Failed to download '%s': %s", title, e, exc_info=True)
        # Clean up partial downloads
        for suffix in ['', '.part', '.ytdl']:
            p = cache_path + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return None


# ---------------------------------------------------------------------------
# Background downloader
# ---------------------------------------------------------------------------

class _BackgroundDownloader:
    """Downloads videos in a background thread, notifying the main thread
    as each video becomes ready for playback.

    Usage:
        dl = _BackgroundDownloader(urls)
        dl.start()
        while True:
            item = dl.get_next_ready(timeout=1.0)
            if item is not None:
                path, title, dur = item
                # play it
            if dl.is_done():
                break
        dl.stop()
    """

    def __init__(self, urls):
        """
        Args:
            urls: List of (url, title, duration) tuples.
        """
        self._urls = urls
        self._ready_queue = queue.Queue()
        self._thread = None
        self._stop_event = threading.Event()
        self._total = len(urls)
        self._downloaded = 0
        self._failed = 0

    def start(self):
        """Start the background download thread."""
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        logger.info("Background downloader started for %d videos", self._total)

    def stop(self):
        """Signal the downloader to stop."""
        self._stop_event.set()

    def is_done(self):
        """True if all videos have been attempted (downloaded or failed)."""
        return (self._downloaded + self._failed) >= self._total

    def has_pending(self):
        """True if there are downloaded videos waiting in the ready queue."""
        return not self._ready_queue.empty()

    def get_next_ready(self, timeout=1.0):
        """Get the next ready-to-play video.

        Returns:
            (path, title, duration) tuple, or None if nothing ready yet.
        """
        try:
            return self._ready_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_all_ready(self):
        """Drain the queue and return all currently ready videos as a list."""
        items = []
        while True:
            try:
                items.append(self._ready_queue.get_nowait())
            except queue.Empty:
                break
        return items

    @property
    def progress(self):
        """Returns (downloaded, failed, total) counts."""
        return self._downloaded, self._failed, self._total

    def _worker(self):
        """Background thread: download videos one by one."""
        for url, title, dur in self._urls:
            if self._stop_event.is_set():
                break

            # Check cache first (instant)
            if _is_cached(url):
                path = _url_to_cache_path(url)
                self._ready_queue.put((path, title, dur))
                self._downloaded += 1
                logger.info("BG: Cached hit for '%s' (%d/%d)",
                            title, self._downloaded, self._total)
                continue

            # Download
            path = download_video(url, title)
            if path:
                self._ready_queue.put((path, title, dur))
                self._downloaded += 1
                logger.info("BG: Downloaded '%s' (%d/%d)",
                            title, self._downloaded, self._total)
            else:
                self._failed += 1
                logger.warning("BG: Failed '%s' (%d failed / %d total)",
                               title, self._failed, self._total)

        logger.info("BG: Downloader finished: %d downloaded, %d failed",
                     self._downloaded, self._failed)


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------

def _play_local_video(matrix, video_path, title, max_duration=None, global_deadline=None):
    """Play a local video file on the matrix.

    Args:
        matrix: RGBMatrix instance.
        video_path: Path to local video file.
        title: Video title for logging.
        max_duration: Maximum seconds to play this video.
        global_deadline: Absolute time.time() deadline to stop.

    Returns:
        Number of frames played.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("Cannot open video file: %s", video_path)
        return 0

    vid_start = time.time()
    frames_played = 0

    try:
        while cap.isOpened():
            frame_start = time.time()

            if should_stop():
                break
            if global_deadline and time.time() >= global_deadline:
                break
            if max_duration and time.time() - vid_start >= max_duration:
                break

            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.resize(frame, (64, 64), interpolation=cv2.INTER_AREA)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame)
            matrix.SetImage(image)
            frames_played += 1

            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    finally:
        cap.release()

    vid_elapsed = time.time() - vid_start
    fps_actual = frames_played / max(vid_elapsed, 0.1)
    logger.info("Played '%s': %d frames in %.1fs (%.1f FPS)",
                title, frames_played, vid_elapsed, fps_actual)
    return frames_played


def read_urls_from_csv(file_path):
    """Read YouTube URLs and durations from a CSV file."""
    urls = []
    try:
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                urls.append((row['url'], row.get('title', 'Unknown'), row.get('duration', 'x')))
        logger.info("Loaded %d URLs from %s", len(urls), file_path)
        return urls
    except Exception as e:
        logger.error("Error reading CSV file %s: %s", file_path, e)
        return []


def stream_video(url):
    """Legacy API: extract a streamable video URL via yt-dlp.

    Kept for backward compatibility with handle_play_video() in main.py.
    """
    if yt_dlp is None:
        raise RuntimeError("yt-dlp not available")

    ydl_opts = {
        'format': f'worst[vcodec!=none][height<={MAX_HEIGHT}][ext=mp4]/worst[ext=mp4]/worst/best',
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 20,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        video_url = info_dict.get('url')
        if not video_url:
            for f in info_dict.get('requested_formats', []):
                if f.get('vcodec', 'none') != 'none':
                    video_url = f.get('url')
                    break
        if not video_url:
            raise RuntimeError("No playable URL found")
    return video_url


def stream_youtube_videos(urls, matrix):
    """Stream YouTube videos to LED matrix (legacy function)."""
    if not _ensure_dependencies():
        return

    downloader = _BackgroundDownloader(urls)
    downloader.start()

    try:
        while not downloader.is_done() or downloader.has_pending():
            item = downloader.get_next_ready(timeout=2.0)
            if item is None:
                downloaded, failed, total = downloader.progress
                _show_status_frame(matrix, "DOWNLOADING", f"{downloaded}/{total}")
                continue

            path, title, dur = item
            max_dur = None
            if dur.lower() != 'x':
                try:
                    max_dur = float(dur) * 60
                except ValueError:
                    pass
            _play_local_video(matrix, path, title, max_duration=max_dur)
    finally:
        downloader.stop()


def play_videos_on_matrix(matrix):
    """Main function to play videos on LED matrix."""
    csv_path = os.path.join(PROJECT_ROOT, "config", "youtube_urls.csv")
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    urls = read_urls_from_csv(csv_path)
    if urls:
        stream_youtube_videos(urls, matrix)


def run(matrix, duration=60):
    """Run the YouTube Stream display feature for the specified duration.

    Plays videos from the local cache (downloaded_videos/).
    Videos are pre-cached at boot by main.py -- this function does NOT
    download anything. If no cached videos exist, it logs a warning and
    returns immediately so the system continues to the next feature.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    if not _ensure_dependencies():
        logger.error("Cannot run YouTube streaming -- missing dependencies")
        return

    csv_path = os.path.join(PROJECT_ROOT, "config", "youtube_urls.csv")
    start_time = time.time()
    global_deadline = start_time + duration

    try:
        urls = read_urls_from_csv(csv_path)
        if not urls:
            logger.warning("No YouTube URLs found in %s", csv_path)
            return

        # Build playlist from already-cached videos only
        playlist = []
        for url, title, dur in urls:
            if _is_cached(url):
                playlist.append((_url_to_cache_path(url), title, dur))
            else:
                logger.info("Video not cached, skipping: '%s'", title)

        if not playlist:
            logger.warning("No cached videos available. "
                           "Videos are downloaded at boot -- try rebooting with internet.")
            return

        logger.info("Playing %d cached videos (out of %d in playlist)",
                     len(playlist), len(urls))

        # Play loop: cycle through cached videos until duration expires
        videos_played = 0
        playlist_idx = 0

        while time.time() < global_deadline and not should_stop():
            if playlist_idx >= len(playlist):
                playlist_idx = 0
                logger.info("Looping playlist")

            path, title, dur = playlist[playlist_idx]
            playlist_idx += 1

            # Per-video max duration from CSV
            max_vid_dur = None
            if dur.lower() != 'x':
                try:
                    max_vid_dur = float(dur) * 60
                except ValueError:
                    pass

            logger.info("=== Playing [%d/%d]: %s ===",
                        playlist_idx, len(playlist), title)

            frames = _play_local_video(
                matrix, path, title,
                max_duration=max_vid_dur,
                global_deadline=global_deadline
            )

            if frames > 0:
                videos_played += 1

        logger.info("YouTube session complete: played %d video segments", videos_played)

    except Exception as e:
        logger.error("YouTube stream error: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass


def _show_status_frame(matrix, line1, line2):
    """Show a status message on the matrix."""
    try:
        from src.display.boot_screen import _draw_text, _text_width
        from PIL import ImageDraw

        img = Image.new("RGB", (64, 64), (0, 0, 20))
        draw = ImageDraw.Draw(img)

        w1 = _text_width(line1, scale=1, spacing=1)
        _draw_text(draw, line1, (64 - w1) // 2, 22, (100, 180, 255), scale=1, spacing=1)

        w2 = _text_width(line2, scale=1, spacing=1)
        _draw_text(draw, line2, (64 - w2) // 2, 35, (180, 180, 180), scale=1, spacing=1)

        matrix.SetImage(img)
    except Exception:
        pass


def _show_error_frame(matrix, title):
    """Show a brief red error indicator on the matrix."""
    try:
        from src.display.boot_screen import _draw_text, _text_width
        from PIL import ImageDraw

        img = Image.new("RGB", (64, 64), (40, 0, 0))
        draw = ImageDraw.Draw(img)

        err_w = _text_width("ERROR", scale=1, spacing=1)
        _draw_text(draw, "ERROR", (64 - err_w) // 2, 20, (255, 60, 60), scale=1, spacing=1)

        display_title = title[:10] if len(title) > 10 else title
        tw = _text_width(display_title, scale=1, spacing=1)
        _draw_text(draw, display_title, (64 - tw) // 2, 35, (180, 180, 180), scale=1, spacing=1)

        matrix.SetImage(img)
    except Exception:
        try:
            matrix.Clear()
        except Exception:
            pass


def cleanup_cache(max_age_days=7):
    """Remove cached videos older than max_age_days."""
    if not os.path.isdir(CACHE_DIR):
        return

    cutoff = time.time() - (max_age_days * 86400)
    removed = 0

    for f in os.listdir(CACHE_DIR):
        fpath = os.path.join(CACHE_DIR, f)
        if os.path.isfile(fpath) and f.endswith('.mp4'):
            if os.path.getmtime(fpath) < cutoff:
                try:
                    os.remove(fpath)
                    removed += 1
                except OSError:
                    pass

    if removed:
        logger.info("Cleaned up %d cached videos older than %d days", removed, max_age_days)


if __name__ == "__main__":
    print("This module should be imported and used with the LED matrix.")
    print("Please run consolidated_games.py instead.")
