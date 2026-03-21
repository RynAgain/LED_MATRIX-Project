#!/usr/bin/env python3
"""GitHub contribution stats display for 64x64 LED matrix.

Shows a contribution heatmap (like GitHub's profile page) for a configured user.
Uses the GitHub public API (no auth required for public profiles).
"""

import time
import json
import os
import logging
import requests
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GITHUB_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "github_stats.json")

# Contribution colors (GitHub-style green palette)
COLORS = [
    (10, 10, 15),      # 0 contributions - very dim
    (0, 60, 30),       # Low
    (0, 110, 50),      # Medium-low
    (0, 170, 70),      # Medium
    (0, 220, 90),      # Medium-high
    (50, 255, 100),    # High
]


def _load_config():
    try:
        with open(GITHUB_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"username": "RynAgain"}


def _fetch_contributions(username):
    """Fetch contribution data using GitHub's GraphQL API (public, no auth for events).
    
    Falls back to the events API if GraphQL isn't available without auth.
    """
    # Use the public events API to approximate contributions
    contributions = {}
    
    try:
        # Fetch recent events (up to 10 pages of 30 events)
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "LED-Matrix-Bot"}
        
        for page in range(1, 4):  # 3 pages of events
            url = f"https://api.github.com/users/{username}/events?page={page}&per_page=100"
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                logger.warning("GitHub API returned %d for %s", resp.status_code, username)
                break
            
            events = resp.json()
            if not events:
                break
            
            for event in events:
                date_str = event.get("created_at", "")[:10]  # YYYY-MM-DD
                if date_str:
                    contributions[date_str] = contributions.get(date_str, 0) + 1
            
            time.sleep(0.5)  # Rate limit courtesy
        
        logger.info("Fetched %d contribution days for %s", len(contributions), username)
        return contributions
        
    except Exception as e:
        logger.error("Failed to fetch GitHub stats for %s: %s", username, e)
        return {}


def _get_color(count):
    """Map contribution count to a color."""
    if count == 0:
        return COLORS[0]
    elif count <= 1:
        return COLORS[1]
    elif count <= 3:
        return COLORS[2]
    elif count <= 5:
        return COLORS[3]
    elif count <= 10:
        return COLORS[4]
    else:
        return COLORS[5]


def _render_stats(username, contributions):
    """Render the contribution heatmap to a PIL Image."""
    image = Image.new("RGB", (WIDTH, HEIGHT), (2, 2, 6))
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # Username at top (small)
    short_name = username[:8]
    draw.text((1, 0), short_name, fill=(120, 120, 150), font=font)

    # Heatmap grid: weeks go left-to-right, days go top-to-bottom
    # 30 days = 4-5 weeks
    today = datetime.now().date()
    days = 35  # 5 full weeks
    
    cell = 3        # 3x3 pixel cells
    gap = 1         # 1px gap
    step = cell + gap  # 4px per cell
    
    # Grid position
    grid_x = 2
    grid_y = 10
    
    # Calculate starting date (align to Monday)
    start_date = today - timedelta(days=days - 1)
    # Adjust to start on Monday
    while start_date.weekday() != 0:
        start_date -= timedelta(days=1)
        days += 1
    
    total = 0
    max_count = 0
    
    for day_offset in range(days):
        date = start_date + timedelta(days=day_offset)
        if date > today:
            break
            
        date_str = date.strftime("%Y-%m-%d")
        count = contributions.get(date_str, 0)
        total += count
        max_count = max(max_count, count)
        
        week = day_offset // 7   # Column (left to right)
        day = day_offset % 7      # Row (top to bottom, Mon=0)
        
        x = grid_x + week * step
        y = grid_y + day * step
        
        if x + cell > WIDTH or y + cell > HEIGHT:
            continue
        
        color = _get_color(count)
        draw.rectangle([x, y, x + cell - 1, y + cell - 1], fill=color)
    
    # Stats below the grid
    grid_bottom = grid_y + 7 * step + 2
    draw.text((1, grid_bottom), f"{total} events", fill=(80, 160, 80), font=font)
    draw.text((1, grid_bottom + 9), f"30 days", fill=(60, 60, 80), font=font)

    return image


def run(matrix, duration=60):
    """Run the GitHub stats display."""
    start_time = time.time()
    config = _load_config()
    username = config.get("username", "RynAgain")
    
    # Fetch data once
    contributions = _fetch_contributions(username)
    
    try:
        while time.time() - start_time < duration:
            image = _render_stats(username, contributions)
            matrix.SetImage(image)
            time.sleep(2)
    
    except Exception as e:
        logger.error("Error in GitHub stats: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
