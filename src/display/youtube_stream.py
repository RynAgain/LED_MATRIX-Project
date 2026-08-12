"""
Backward-compatibility wrapper for the former YouTube streaming module.

This module delegates to video_player.py, which downloads both direct
HTTP video URLs (archive.org, S3, GitHub Releases, etc.) and YouTube
links (via yt-dlp, auto-updated weekly) to the local cache.

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
    is_youtube_url,
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
    """Live streaming is not supported; videos are cached then played.

    Add the URL (direct MP4 or YouTube link) to config/video_urls.csv
    and it will be downloaded at boot and played from cache.
    """
    raise RuntimeError(
        "Streaming is not supported. Add the URL to "
        "config/video_urls.csv; it will be cached at boot and played "
        "from disk (YouTube links are handled via yt-dlp)."
    )

def stream_youtube_videos(urls, matrix):
    """No longer supported. Use video_player.run() instead."""
    return run(matrix, duration=300)

def play_videos_on_matrix(matrix):
    """No longer supported. Use video_player.run() instead."""
    return run(matrix, duration=300)
