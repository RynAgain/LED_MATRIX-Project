"""
YouTube video streaming for 64x64 LED matrix.

Streams YouTube videos by extracting direct video URLs via yt-dlp,
then decoding frames with OpenCV and displaying on the matrix.

Requires: yt-dlp, opencv-python-headless, numpy, Pillow
"""

import os
import sys
import time
import csv
import subprocess
import logging
from PIL import Image
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

# Lazy imports for heavy dependencies -- allows the module to be imported
# even if cv2/yt_dlp are missing (e.g., during testing on dev machines).
cv2 = None
np = None
yt_dlp = None

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Target frame rate for video playback on 64x64 matrix.
# 15 FPS is visually smooth at this resolution and halves CPU load vs 30.
TARGET_FPS = 15
FRAME_INTERVAL = 1.0 / TARGET_FPS


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
    is the #1 cause of 'nothing plays' on the Pi.
    """
    try:
        logger.info("Updating yt-dlp to latest version...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", "yt-dlp"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            logger.info("yt-dlp updated successfully")
            # Reload the module to pick up the new version
            import importlib
            global yt_dlp
            if yt_dlp is not None:
                yt_dlp = importlib.reload(yt_dlp)
            else:
                import yt_dlp as _yt_dlp
                yt_dlp = _yt_dlp
            logger.info("yt-dlp version: %s", getattr(yt_dlp, 'version', {}).get('__version__', 'unknown'))
        else:
            logger.warning("yt-dlp update failed: %s", result.stderr.strip())
    except Exception as e:
        logger.warning("Could not update yt-dlp: %s (continuing with current version)", e)


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
    """Extract a streamable video URL via yt-dlp.

    Tries multiple format strategies to maximize compatibility.
    Returns the direct video URL string, or raises on failure.
    """
    if yt_dlp is None:
        raise RuntimeError("yt-dlp not available")

    # Try multiple format strategies in order of preference
    format_strategies = [
        # Strategy 1: Smallest MP4 video-only (least bandwidth)
        'worst[vcodec!=none][height<=240][ext=mp4]/worst[vcodec!=none][height<=360][ext=mp4]',
        # Strategy 2: Any small MP4
        'worst[ext=mp4]/worst',
        # Strategy 3: Best small format (any container)
        'best[height<=480]',
        # Strategy 4: Just get anything that works
        'best',
    ]

    last_error = None
    for i, fmt in enumerate(format_strategies):
        try:
            ydl_opts = {
                'format': fmt,
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 20,
                'retries': 2,
                'nocache': True,
                # Skip unavailable fragments instead of failing
                'skip_unavailable_fragments': True,
            }
            logger.info("Trying format strategy %d/%d for: %s", i + 1, len(format_strategies), url)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)

                # Extract the actual playback URL
                video_url = info_dict.get('url')
                if not video_url:
                    # Some formats use 'requested_formats' for merged streams
                    formats = info_dict.get('requested_formats', [])
                    for f in formats:
                        if f.get('vcodec', 'none') != 'none':
                            video_url = f.get('url')
                            break

                if not video_url:
                    # Last resort: try the manifest URL
                    video_url = info_dict.get('manifest_url')

                if video_url:
                    height = info_dict.get('height', '?')
                    vcodec = info_dict.get('vcodec', '?')
                    logger.info("Got stream URL (height=%s, codec=%s)", height, vcodec)
                    return video_url
                else:
                    last_error = "No playable URL found in extraction result"
                    logger.warning("Strategy %d: %s", i + 1, last_error)

        except Exception as e:
            last_error = str(e)
            logger.warning("Strategy %d failed: %s", i + 1, last_error)
            continue

    raise RuntimeError(f"All format strategies failed for {url}: {last_error}")


def _open_capture(video_url):
    """Open cv2.VideoCapture with optimized settings for Pi streaming.

    Returns an opened VideoCapture or None on failure.
    """
    logger.info("Opening video capture...")

    # Set environment hints for ffmpeg (used internally by OpenCV)
    os.environ.setdefault('OPENCV_FFMPEG_CAPTURE_OPTIONS', 'timeout;10000000')

    cap = cv2.VideoCapture(video_url)

    if not cap.isOpened():
        logger.error("cv2.VideoCapture failed to open stream")
        return None

    # Minimize internal buffer to reduce latency
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    logger.info("Video capture opened successfully")
    return cap


def stream_youtube_videos(urls, matrix):
    """Stream YouTube videos to LED matrix (legacy function)."""
    if not _ensure_dependencies():
        return

    try:
        for url, title, duration in urls:
            logger.info("Preparing to play: %s", title)

            try:
                video_url = stream_video(url)
            except Exception as e:
                logger.error("Failed to get stream URL for '%s': %s", title, e)
                continue

            cap = _open_capture(video_url)
            if cap is None:
                continue

            start_time = time.time()

            # Determine playback duration
            max_duration = None
            if duration.lower() != 'x':
                try:
                    max_duration = float(duration) * 60
                except ValueError:
                    pass

            frames_played = 0
            frames_dropped = 0

            while cap.isOpened():
                frame_start = time.time()

                if max_duration and time.time() - start_time > max_duration:
                    break

                ret, frame = cap.read()
                if not ret:
                    logger.info("End of stream for '%s' after %d frames (%d dropped)",
                                title, frames_played, frames_dropped)
                    break

                frame = cv2.resize(frame, (64, 64), interpolation=cv2.INTER_NEAREST)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame)
                matrix.SetImage(image)
                frames_played += 1

                elapsed = time.time() - frame_start
                sleep_time = FRAME_INTERVAL - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            cap.release()
            logger.info("Playback finished for '%s'", title)

    except KeyboardInterrupt:
        logger.info("Playback interrupted by user")
    except Exception as e:
        logger.error("Streaming error: %s", e, exc_info=True)


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

    Args:
        matrix: RGBMatrix instance (or mock).
        duration: How long to run in seconds.
    """
    if not _ensure_dependencies():
        logger.error("Cannot run YouTube streaming -- missing dependencies")
        return

    # Auto-update yt-dlp on first run (YouTube breaks old versions frequently)
    _update_ytdlp()

    csv_path = os.path.join(PROJECT_ROOT, "config", "youtube_urls.csv")
    start_time = time.time()

    try:
        urls = read_urls_from_csv(csv_path)
        if not urls:
            logger.warning("No YouTube URLs found in %s", csv_path)
            return

        total_videos = len(urls)
        videos_played = 0
        videos_failed = 0

        for url, title, dur in urls:
            if time.time() - start_time >= duration:
                logger.info("Total duration reached, stopping YouTube")
                break
            if should_stop():
                break

            logger.info("=== Video %d/%d: %s ===", videos_played + 1, total_videos, title)

            # Extract stream URL
            try:
                video_url = stream_video(url)
            except Exception as e:
                logger.error("FAILED to extract stream for '%s': %s", title, e)
                videos_failed += 1
                # Show an error indicator on the matrix briefly
                _show_error_frame(matrix, title)
                time.sleep(2)
                continue

            # Open video capture
            cap = _open_capture(video_url)
            if cap is None:
                logger.error("FAILED to open capture for '%s'", title)
                videos_failed += 1
                _show_error_frame(matrix, title)
                time.sleep(2)
                continue

            # Per-video max duration from CSV
            max_vid_duration = None
            if dur.lower() != 'x':
                try:
                    max_vid_duration = float(dur) * 60
                except ValueError:
                    pass

            vid_start = time.time()
            frames_played = 0

            while cap.isOpened():
                frame_start = time.time()

                if time.time() - start_time >= duration:
                    break
                if should_stop():
                    break
                if max_vid_duration and time.time() - vid_start >= max_vid_duration:
                    break

                ret, frame = cap.read()
                if not ret:
                    if frames_played == 0:
                        logger.error("First frame read failed for '%s' -- stream may be incompatible", title)
                    break

                frame = cv2.resize(frame, (64, 64), interpolation=cv2.INTER_NEAREST)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame)
                matrix.SetImage(image)
                frames_played += 1

                elapsed = time.time() - frame_start
                sleep_time = FRAME_INTERVAL - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            cap.release()
            vid_elapsed = time.time() - vid_start
            fps_actual = frames_played / max(vid_elapsed, 0.1)
            logger.info("Finished '%s': %d frames in %.1fs (%.1f FPS)",
                        title, frames_played, vid_elapsed, fps_actual)

            if frames_played > 0:
                videos_played += 1
            else:
                videos_failed += 1

        logger.info("YouTube session complete: %d played, %d failed out of %d",
                     videos_played, videos_failed, total_videos)

    except Exception as e:
        logger.error("YouTube stream error: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass


def _show_error_frame(matrix, title):
    """Show a brief red error indicator on the matrix when a video fails."""
    try:
        from src.display.boot_screen import _draw_text, _text_width
        img = Image.new("RGB", (64, 64), (40, 0, 0))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)

        # "ERROR" text
        err_w = _text_width("ERROR", scale=1, spacing=1)
        _draw_text(draw, "ERROR", (64 - err_w) // 2, 20, (255, 60, 60), scale=1, spacing=1)

        # Truncate title to fit
        display_title = title[:10] if len(title) > 10 else title
        tw = _text_width(display_title, scale=1, spacing=1)
        _draw_text(draw, display_title, (64 - tw) // 2, 35, (180, 180, 180), scale=1, spacing=1)

        matrix.SetImage(img)
    except Exception:
        # If even the error display fails, just clear
        try:
            matrix.Clear()
        except Exception:
            pass


if __name__ == "__main__":
    print("This module should be imported and used with the LED matrix.")
    print("Please run consolidated_games.py instead.")
