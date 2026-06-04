#!/usr/bin/env python3
"""Weather display for 64x64 LED matrix using Open-Meteo free API.

Uses the shared 5x7 bitmap font from _fonts.py for crisp, readable text
on the LED matrix. Layout is optimized for the 64x64 pixel space with
clear sections for temperature, condition, wind, and humidity.
"""

import time
import logging
import json
import os
import requests
from PIL import Image, ImageDraw
from src.display._fonts import _draw_text, _text_width
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64

# Colors — high contrast for LED readability
BG_COLOR = (0, 0, 8)
TITLE_COLOR = (100, 160, 255)
TEMP_COLOR = (255, 255, 255)
CONDITION_COLOR = (200, 200, 220)
WIND_COLOR = (120, 220, 140)
HUMIDITY_COLOR = (140, 160, 255)
SEPARATOR_COLOR = (40, 40, 70)


def _load_location():
    """Load weather location from config."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config", "weather.json"
    )
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        return data.get("lat", 30.27), data.get("lon", -97.74)
    except (FileNotFoundError, json.JSONDecodeError):
        return 30.27, -97.74

WMO_CODES = {
    0: "CLEAR", 1: "CLEAR", 2: "CLOUDY", 3: "OVERCAST",
    45: "FOGGY", 48: "FOGGY",
    51: "DRIZZLE", 53: "DRIZZLE", 55: "DRIZZLE",
    61: "RAIN", 63: "RAIN", 65: "HEAVY RAIN",
    71: "SNOW", 73: "SNOW", 75: "HEAVY SNOW",
    80: "SHOWERS", 81: "SHOWERS", 82: "SHOWERS",
    95: "STORM", 96: "STORM", 99: "STORM"
}

WMO_ACCENT = {
    0: (255, 220, 50),    # Sunny yellow
    1: (200, 200, 150),   # Mostly clear
    2: (150, 150, 180),   # Partly cloudy
    3: (120, 120, 140),   # Overcast gray
    45: (100, 100, 120),  # Fog
    51: (100, 150, 200),  # Drizzle
    61: (50, 100, 200),   # Rain blue
    71: (200, 200, 255),  # Snow white-blue
    80: (80, 120, 200),   # Showers
    95: (200, 50, 200),   # Storm purple
}


def _fetch_weather(lat=None, lon=None):
    """Fetch current weather from Open-Meteo (free, no API key)."""
    if lat is None or lon is None:
        lat, lon = _load_location()
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        return {
            "temp": current.get("temperature_2m"),
            "code": current.get("weather_code", 0),
            "wind": current.get("wind_speed_10m"),
            "humidity": current.get("relative_humidity_2m"),
        }
    except Exception as e:
        logger.error("Weather fetch failed: %s", e)
        return None


def _get_accent_color(code):
    """Get accent color for a WMO weather code."""
    color_key = min(WMO_ACCENT.keys(), key=lambda k: abs(k - code))
    return WMO_ACCENT.get(color_key, (200, 200, 200))


def _render_weather(weather):
    """Render weather data to a PIL Image using the 5x7 bitmap font.

    Layout (64x64):
      Row  1-7:   "WEATHER" title centered
      Row  9:     Separator line
      Row 12-18:  Temperature (scale=2 for emphasis)
      Row 22-28:  Condition text
      Row 32:     Separator line
      Row 35-41:  Wind label + value
      Row 45-51:  Humidity label + value
      Row 55-61:  Accent bar (weather-themed color)
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(image)

    code = weather.get("code", 0)
    temp = weather.get("temp")
    wind = weather.get("wind")
    humidity = weather.get("humidity")

    condition = WMO_CODES.get(code, "UNKNOWN")
    accent = _get_accent_color(code)

    # Title "WEATHER" centered
    title = "WEATHER"
    tw = _text_width(title, scale=1)
    _draw_text(draw, title, (WIDTH - tw) // 2, 1, TITLE_COLOR, scale=1, spacing=1)

    # Separator line
    draw.line([(4, 9), (59, 9)], fill=SEPARATOR_COLOR)

    # Temperature — large (scale=2) for emphasis, centered
    if temp is not None:
        temp_str = "{}F".format(int(temp))
        tw2 = _text_width(temp_str, scale=2)
        _draw_text(draw, temp_str, (WIDTH - tw2) // 2, 12, TEMP_COLOR,
                   scale=2, spacing=1)
    else:
        na_str = "N/A"
        tw2 = _text_width(na_str, scale=2)
        _draw_text(draw, na_str, (WIDTH - tw2) // 2, 12, TEMP_COLOR,
                   scale=2, spacing=1)

    # Condition — centered, accent color
    cw = _text_width(condition, scale=1)
    _draw_text(draw, condition, max(0, (WIDTH - cw) // 2), 28, accent,
               scale=1, spacing=1)

    # Separator line
    draw.line([(4, 36), (59, 36)], fill=SEPARATOR_COLOR)

    # Wind
    if wind is not None:
        wind_label = "WIND"
        _draw_text(draw, wind_label, 2, 39, WIND_COLOR, scale=1, spacing=1)
        wind_val = "{}MPH".format(int(wind))
        vw = _text_width(wind_val, scale=1)
        _draw_text(draw, wind_val, WIDTH - vw - 2, 39, (255, 255, 255),
                   scale=1, spacing=1)

    # Humidity
    if humidity is not None:
        hum_label = "HUM"
        _draw_text(draw, hum_label, 2, 49, HUMIDITY_COLOR, scale=1, spacing=1)
        hum_val = "{}%".format(int(humidity))
        hw = _text_width(hum_val, scale=1)
        _draw_text(draw, hum_val, WIDTH - hw - 2, 49, (255, 255, 255),
                   scale=1, spacing=1)

    # Accent bar at bottom (weather-themed color indicator)
    draw.rectangle([4, 59, 59, 62], fill=accent)

    return image


def run(matrix, duration=60):
    """Run the weather display for the specified duration."""
    start_time = time.time()
    last_fetch = 0
    weather = None

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            now = time.time()

            # Fetch weather every 60 seconds
            if now - last_fetch > 60 or weather is None:
                weather = _fetch_weather()
                last_fetch = now

            if weather:
                image = _render_weather(weather)
                matrix.SetImage(image)

            # Sleep 1 second between refreshes (weather data doesn't need 30 FPS)
            time.sleep(1)

    except Exception as e:
        logger.error("Error in weather display: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
