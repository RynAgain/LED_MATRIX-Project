"""
Backward-compatibility wrapper for the former YouTube streaming module.

YouTube support was removed due to YouTube's increasingly aggressive
anti-bot measures (PO tokens, cookie expiration, constant yt-dlp breakage).
This module now delegates to video_player.py which supports direct HTTP
video URLs from any host (archive.org, S3, GitHub Releases, etc.).

All public symbols are re-exported so existing imports continue to work.
"""

from src.display.video_player import (  # noqa: F401
    run,
    read_urls_from_csv,
    download_video,
    _ensure_dependencies,
    _url_to_cache_path,
    _is_cached,
    _play_local_video,
    _show_status_frame,
    _show_error_frame,
    _BackgroundDownloader,
    cleanup_cache,
    FRAME_INTERVAL,
    CACHE_DIR,
    TARGET_FPS,
)

# Legacy aliases -- these no longer do anything meaningful but prevent
# ImportError for code that references them.
def refresh_youtube_cookies():
    """No-op. YouTube cookie extraction is no longer used."""
    pass

def stream_video(url):
    """No longer supported. Use direct video URLs instead."""
    raise RuntimeError(
        "YouTube streaming is no longer supported. "
        "Use direct MP4 URLs in config/video_urls.csv instead."
    )

def stream_youtube_videos(urls, matrix):
    """No longer supported. Use video_player.run() instead."""
    return run(matrix, duration=300)

def play_videos_on_matrix(matrix):
    """No longer supported. Use video_player.run() instead."""
    return run(matrix, duration=300)
