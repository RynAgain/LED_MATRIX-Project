#!/usr/bin/env python3
"""Album art display for 64x64 LED matrix using Apple Music/iTunes Search API.

Fetches album cover art from the iTunes Search API (free, no auth required)
and cycles through them with fade transitions. Configurable via
config/album_art.json with search terms, display duration, and shuffle option.

The iTunes API returns artworkUrl100 which can be hacked to get larger sizes
by replacing '100x100' with any desired resolution (we use 64x64 for direct
matrix display without scaling overhead).
"""

import io
import json
import logging
import os
import random
import time

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from src.display._fonts import _draw_text, _text_width
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 20  # 20 FPS for smooth transitions

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "album_art.json")

# iTunes Search API endpoint
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"


def _load_config():
    """Load album art configuration from JSON file."""
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        return {
            "search_terms": data.get("search_terms", ["dark side of the moon"]),
            "display_seconds": data.get("display_seconds", 10),
            "transition": data.get("transition", "fade"),
            "shuffle": data.get("shuffle", True),
        }
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Could not load album_art.json: %s. Using defaults.", e)
        return {
            "search_terms": [
                "dark side of the moon",
                "abbey road beatles",
                "thriller michael jackson",
            ],
            "display_seconds": 10,
            "transition": "fade",
            "shuffle": True,
        }


def _fetch_album_art(search_term):
    """Fetch album artwork URL from iTunes Search API.

    Args:
        search_term: Album/artist search query string.

    Returns:
        PIL Image (64x64) or None on failure.
    """
    try:
        params = {
            "term": search_term,
            "entity": "album",
            "limit": 1,
        }
        resp = requests.get(ITUNES_SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            logger.warning("No results for: %s", search_term)
            return None

        # Get artwork URL and hack it to 600x600 for quality
        artwork_url = results[0].get("artworkUrl100", "")
        if not artwork_url:
            return None

        # Replace 100x100 with 600x600 for higher quality source
        artwork_url = artwork_url.replace("100x100", "600x600")

        # Download the image
        img_resp = requests.get(artwork_url, timeout=15)
        img_resp.raise_for_status()

        # Open and resize to 64x64
        img = Image.open(io.BytesIO(img_resp.content))
        img = img.convert("RGB")
        img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)

        return img

    except Exception as e:
        logger.error("Failed to fetch album art for '%s': %s", search_term, e)
        return None


def _fetch_album_info(search_term):
    """Fetch album name and artist from iTunes Search API.

    Returns:
        Tuple of (album_name, artist_name) or (None, None) on failure.
    """
    try:
        params = {
            "term": search_term,
            "entity": "album",
            "limit": 1,
        }
        resp = requests.get(ITUNES_SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            return None, None

        album = results[0].get("collectionName", "")
        artist = results[0].get("artistName", "")
        return album, artist

    except Exception:
        return None, None


def _create_loading_frame():
    """Create a 'loading' placeholder image."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 10))
    draw = ImageDraw.Draw(img)
    text = "LOADING"
    tw = _text_width(text, scale=1)
    _draw_text(draw, text, (WIDTH - tw) // 2, 28, (80, 80, 100), scale=1)
    return img


def _create_error_frame(term):
    """Create an error placeholder when art can't be fetched."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (10, 0, 0))
    draw = ImageDraw.Draw(img)
    text = "NO ART"
    tw = _text_width(text, scale=1)
    _draw_text(draw, text, (WIDTH - tw) // 2, 28, (100, 40, 40), scale=1)
    return img


def _blend_images(img1, img2, alpha):
    """Blend two images together with given alpha (0.0 = img1, 1.0 = img2)."""
    return Image.blend(img1, img2, alpha)


def run(matrix, duration=60):
    """Run the album art display for the specified duration.

    Cycles through album covers fetched from iTunes Search API with
    configurable transitions and timing.
    """
    start_time = time.time()
    config = _load_config()

    search_terms = list(config["search_terms"])
    display_seconds = config["display_seconds"]
    transition = config["transition"]
    shuffle = config["shuffle"]

    if shuffle:
        random.shuffle(search_terms)

    # Pre-fetch first image
    current_idx = 0
    current_img = None
    next_img = None
    transitioning = False
    transition_start = 0
    transition_duration = 1.0  # 1 second fade
    last_switch = time.time()

    # Fetch first album art
    if search_terms:
        loading_img = _create_loading_frame()
        matrix.SetImage(loading_img)
        current_img = _fetch_album_art(search_terms[current_idx])
        if current_img is None:
            current_img = _create_error_frame(search_terms[current_idx])

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            now = time.time()

            # Check if it's time to switch to next album
            if not transitioning and (now - last_switch) >= display_seconds:
                # Start transition to next image
                current_idx = (current_idx + 1) % len(search_terms)
                next_img = _fetch_album_art(search_terms[current_idx])
                if next_img is None:
                    next_img = _create_error_frame(search_terms[current_idx])

                if transition == "fade":
                    transitioning = True
                    transition_start = now
                else:
                    # Instant switch
                    current_img = next_img
                    next_img = None
                    last_switch = now

            # Handle fade transition
            if transitioning:
                elapsed = now - transition_start
                alpha = min(1.0, elapsed / transition_duration)

                if alpha >= 1.0:
                    # Transition complete
                    current_img = next_img
                    next_img = None
                    transitioning = False
                    last_switch = now
                    matrix.SetImage(current_img)
                else:
                    # Blend frames
                    blended = _blend_images(current_img, next_img, alpha)
                    matrix.SetImage(blended)
            else:
                # Static display
                if current_img:
                    matrix.SetImage(current_img)

            # Frame rate control
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in album art display: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
