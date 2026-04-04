"""
YouTube video streaming for 64x64 LED matrix.

Downloads YouTube videos to local cache at low resolution, then plays
from disk. This is far more reliable than real-time streaming on a Pi:
  - No network jitter during playback
  - No stream URL expiration mid-video
  - Faster frame decode from local files
  - Videos persist across reboots (only downloaded once)

Requires: yt-dlp, opencv-python-headless, numpy, Pillow
"""

import os
import sys
import time
import csv
import subprocess
import hashlib
import logging
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
    """Attempt to update yt-dlp to the latest version.

    YouTube frequently changes their extraction methods. An outdated yt-dlp
    is the #1 cause of videos failing to download.
    """
    try:
        logger.info("Checking for yt-dlp updates...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", "yt-dlp"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            logger.info("yt-dlp is up to date")
            # Reload the module to pick up new version
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


def _url_to_cache_path(url):
    """Generate a deterministic cache filename from a URL.

    Returns the full path to the cached video file.
    """
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{url_hash}.mp4")


def _is_cached(url):
    """Check if a video is already downloaded and valid."""
    path = _url_to_cache_path(url)
    if not os.path.exists(path):
        return False
    # Check file isn't empty or corrupt (at least 10KB)
    size = os.path.getsize(path)
    if size < 10240:
        logger.warning("Cached file too small (%d bytes), will re-download: %s", size, path)
        os.remove(path)
        return False
    return True


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

    # Already cached?
    if _is_cached(url):
        logger.info("Using cached video for '%s': %s", title, cache_path)
        return cache_path

    os.makedirs(CACHE_DIR, exist_ok=True)

    # Download at lowest available resolution
    ydl_opts = {
        'format': (
            f'worst[vcodec!=none][height<={MAX_HEIGHT}][ext=mp4]/'
            f'worst[vcodec!=none][ext=mp4]/'
            'worst[ext=mp4]/'
            'worst/'
            f'best[height<={MAX_HEIGHT}]/'
            'best'
        ),
        'outtmpl': cache_path,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 3,
        # Merge to MP4 if needed
        'merge_output_format': 'mp4',
        # Don't post-process (save CPU)
        'postprocessors': [],
    }

    logger.info("Downloading '%s' to cache...", title)
    start = time.time()

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        elapsed = time.time() - start

        if os.path.exists(cache_path):
            size_mb = os.path.getsize(cache_path) / (1024 * 1024)
            logger.info("Downloaded '%s' (%.1f MB) in %.1fs", title, size_mb, elapsed)
            return cache_path
        else:
            # yt-dlp may have added a different extension
            # Check for any file matching the hash prefix
            prefix = os.path.splitext(os.path.basename(cache_path))[0]
            for f in os.listdir(CACHE_DIR):
                if f.startswith(prefix):
                    actual_path = os.path.join(CACHE_DIR, f)
                    logger.info("Downloaded '%s' as %s", title, f)
                    return actual_path

            logger.error("Download appeared to succeed but file not found: %s", cache_path)
            return None

    except Exception as e:
        logger.error("Failed to download '%s': %s", title, e)
        # Clean up partial downloads
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except OSError:
                pass
        return None


def prebuffer_all(urls):
    """Download all videos in the playlist to local cache.

    Args:
        urls: List of (url, title, duration) tuples.

    Returns:
        List of (local_path, title, duration) tuples for successfully cached videos.
    """
    cached = []
    for url, title, dur in urls:
        if should_stop():
            break

        if _is_cached(url):
            cached.append((_url_to_cache_path(url), title, dur))
            logger.info("Already cached: '%s'", title)
        else:
            path = download_video(url, title)
            if path:
                cached.append((path, title, dur))

    logger.info("Prebuffer complete: %d/%d videos ready", len(cached), len(urls))
    return cached


def _play_local_video(matrix, video_path, title, max_duration=None, global_deadline=None):
    """Play a local video file on the matrix.

    Args:
        matrix: RGBMatrix instance.
        video_path: Path to local video file.
        title: Video title for logging.
        max_duration: Maximum seconds to play this video (None = full video).
        global_deadline: Absolute time.time() deadline to stop (None = no limit).

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

            # Check stop conditions
            if should_stop():
                break
            if global_deadline and time.time() >= global_deadline:
                break
            if max_duration and time.time() - vid_start >= max_duration:
                break

            ret, frame = cap.read()
            if not ret:
                break

            # Resize to matrix dimensions (INTER_AREA is best for downscaling quality,
            # INTER_NEAREST is fastest -- use AREA since we're playing from local disk)
            frame = cv2.resize(frame, (64, 64), interpolation=cv2.INTER_AREA)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame)
            matrix.SetImage(image)
            frames_played += 1

            # Frame rate control
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            elif frames_played % 100 == 0:
                # Skip frames if we're falling behind (every 100 frames check)
                # Read and discard a frame to catch up
                cap.read()

    finally:
        cap.release()

    vid_elapsed = time.time() - vid_start
    fps_actual = frames_played / max(vid_elapsed, 0.1)
    logger.info("Played '%s': %d frames in %.1fs (%.1f FPS)", title, frames_played, vid_elapsed, fps_actual)
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
    Prefer download_video() + local playback instead.
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
            # Try merged format
            for f in info_dict.get('requested_formats', []):
                if f.get('vcodec', 'none') != 'none':
                    video_url = f.get('url')
                    break
        if not video_url:
            raise RuntimeError("No playable URL found")
    return video_url


def stream_youtube_videos(urls, matrix):
    """Stream YouTube videos to LED matrix (legacy function, now uses prebuffer)."""
    if not _ensure_dependencies():
        return

    cached = prebuffer_all(urls)
    for path, title, dur in cached:
        if should_stop():
            break
        max_dur = None
        if dur.lower() != 'x':
            try:
                max_dur = float(dur) * 60
            except ValueError:
                pass
        _play_local_video(matrix, path, title, max_duration=max_dur)


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

    Downloads all videos to local cache first (prebuffer), then plays
    them from disk for reliable, smooth playback.

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    if not _ensure_dependencies():
        logger.error("Cannot run YouTube streaming -- missing dependencies")
        return

    # Auto-update yt-dlp (YouTube breaks old versions constantly)
    _update_ytdlp()

    csv_path = os.path.join(PROJECT_ROOT, "config", "youtube_urls.csv")
    start_time = time.time()
    global_deadline = start_time + duration

    try:
        urls = read_urls_from_csv(csv_path)
        if not urls:
            logger.warning("No YouTube URLs found in %s", csv_path)
            return

        # --- Phase 1: Prebuffer (download all videos) ---
        logger.info("=== Prebuffering %d videos ===", len(urls))
        _show_status_frame(matrix, "DOWNLOADING", f"{len(urls)} VIDEOS")

        cached = prebuffer_all(urls)

        if not cached:
            logger.error("No videos could be downloaded")
            _show_error_frame(matrix, "NO VIDEOS")
            time.sleep(3)
            return

        logger.info("=== Prebuffer complete: %d/%d videos ready ===", len(cached), len(urls))

        # --- Phase 2: Playback loop from local files ---
        videos_played = 0

        while time.time() < global_deadline and not should_stop():
            for path, title, dur in cached:
                if time.time() >= global_deadline:
                    break
                if should_stop():
                    break

                logger.info("=== Playing: %s ===", title)

                # Per-video max duration from CSV
                max_vid_dur = None
                if dur.lower() != 'x':
                    try:
                        max_vid_dur = float(dur) * 60
                    except ValueError:
                        pass

                frames = _play_local_video(
                    matrix, path, title,
                    max_duration=max_vid_dur,
                    global_deadline=global_deadline
                )

                if frames > 0:
                    videos_played += 1

            # If we've looped through all videos and still have time, loop again
            if time.time() < global_deadline and not should_stop():
                logger.info("Looping playlist...")

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
    """Show a brief red error indicator on the matrix when a video fails."""
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
    """Remove cached videos older than max_age_days.

    Can be called periodically to prevent the cache from growing forever.
    """
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
