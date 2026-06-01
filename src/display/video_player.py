"""
Video player for 64x64 LED matrix.

Downloads videos from direct HTTP/HTTPS URLs to local cache, then plays
from disk. Supports any direct MP4/video link (archive.org, S3, GitHub
Releases, self-hosted, etc.).

Replaces the previous youtube_stream module which relied on yt-dlp and
was subject to constant breakage from YouTube's anti-bot measures.

Architecture:
  - Videos are downloaded via simple HTTP GET to downloaded_videos/
  - Main thread plays videos from local cache
  - Already-cached videos play immediately (no download wait)
  - Downloads persist across reboots (only downloaded once per URL)
  - Background pre-caching at boot downloads any uncached videos

Requires: opencv-python-headless, numpy, Pillow
"""

import os
import sys
import time
import csv
import hashlib
import logging
import threading
import queue
import urllib.request
import urllib.error
from PIL import Image
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

# Lazy imports for heavy dependencies
cv2 = None
np = None

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(PROJECT_ROOT, "downloaded_videos")

# Target frame rate for playback on 64x64 matrix.
TARGET_FPS = 15
FRAME_INTERVAL = 1.0 / TARGET_FPS


def _ensure_dependencies():
    """Lazy-import heavy dependencies. Returns True if all available."""
    global cv2, np
    if cv2 is not None and np is not None:
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

    if missing:
        logger.error("Missing dependencies for video playback: %s", ", ".join(missing))
        logger.error("Install with: pip install %s", " ".join(missing))
        return False
    return True


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
    """Download a video from a direct URL to local cache.

    Supports any direct HTTP/HTTPS link to a video file
    (archive.org, S3, GitHub Releases, CDN, self-hosted, etc.).

    Args:
        url: Direct URL to a video file (MP4, WebM, etc.).
        title: Video title for logging.

    Returns:
        Path to the downloaded file, or None on failure.
    """
    cache_path = _url_to_cache_path(url)

    if _is_cached(url):
        logger.info("Already cached: '%s'", title)
        return cache_path

    os.makedirs(CACHE_DIR, exist_ok=True)

    if not _check_disk_space(CACHE_DIR):
        logger.error("Insufficient disk space for video download of '%s'", title)
        return None

    logger.info("Downloading '%s' from %s", title, url)
    start = time.time()

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'LED-Matrix-Project/1.0'
        })
        with urllib.request.urlopen(req, timeout=120) as response:
            with open(cache_path, 'wb') as out_file:
                # Stream in chunks to avoid memory issues with large files
                chunk_size = 65536  # 64KB
                total_bytes = 0
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    total_bytes += len(chunk)

        elapsed = time.time() - start

        if os.path.exists(cache_path):
            size_mb = os.path.getsize(cache_path) / (1024 * 1024)
            if size_mb < 0.01:  # Less than 10KB
                logger.error("Downloaded file too small (%.1f KB) for '%s' -- "
                             "URL may not be a direct video link",
                             size_mb * 1024, title)
                try:
                    os.remove(cache_path)
                except OSError:
                    pass
                return None
            logger.info("Downloaded '%s' (%.1f MB) in %.1fs", title, size_mb, elapsed)
            return cache_path

        logger.error("Download completed but no file found for '%s'", title)
        return None

    except urllib.error.HTTPError as e:
        logger.error("HTTP %d downloading '%s': %s", e.code, title, e.reason)
    except urllib.error.URLError as e:
        logger.error("URL error downloading '%s': %s", title, e.reason)
    except Exception as e:
        logger.error("Failed to download '%s': %s", title, e, exc_info=True)

    # Clean up partial downloads
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
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
    """Read video URLs and durations from a CSV file.

    Supports both the new video_urls.csv and legacy youtube_urls.csv format.
    CSV format: url,title,duration
    """
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


def _get_csv_path():
    """Get the video URLs CSV path, preferring video_urls.csv over legacy youtube_urls.csv."""
    new_path = os.path.join(PROJECT_ROOT, "config", "video_urls.csv")
    legacy_path = os.path.join(PROJECT_ROOT, "config", "youtube_urls.csv")

    if os.path.exists(new_path):
        return new_path
    if os.path.exists(legacy_path):
        logger.info("Using legacy youtube_urls.csv (consider renaming to video_urls.csv)")
        return legacy_path
    return new_path  # Default to new path for creation


def run(matrix, duration=60):
    """Run the Video Player display feature for the specified duration.

    Plays videos from the local cache (downloaded_videos/).
    Videos are pre-cached at boot by main.py -- this function does NOT
    download anything. If no cached videos exist, it logs a warning and
    returns immediately so the system continues to the next feature.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    if not _ensure_dependencies():
        logger.error("Cannot run video playback -- missing dependencies")
        return

    csv_path = _get_csv_path()
    start_time = time.time()
    global_deadline = start_time + duration

    try:
        urls = read_urls_from_csv(csv_path)
        if not urls:
            logger.warning("No video URLs found in %s", csv_path)
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

        logger.info("Video session complete: played %d video segments", videos_played)

    except Exception as e:
        logger.error("Video player error: %s", e, exc_info=True)
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
    print("Please run src/main.py instead.")
