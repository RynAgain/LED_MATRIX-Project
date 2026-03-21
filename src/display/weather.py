#!/usr/bin/env python3
"""Weather display for 64x64 LED matrix using Open-Meteo free API."""

import time
import logging
import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64

# Open-Meteo free API (no key required)
# Default: Austin, TX area. User can override via config later.
DEFAULT_LAT = 30.27
DEFAULT_LON = -97.74

WMO_CODES = {
    0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Foggy", 48: "Rime Fog",
    51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
    61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
    71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
    80: "Light Showers", 81: "Showers", 82: "Heavy Showers",
    95: "Thunderstorm", 96: "T-Storm + Hail", 99: "T-Storm + Heavy Hail"
}

WMO_COLORS = {
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


def _fetch_weather(lat=DEFAULT_LAT, lon=DEFAULT_LON):
    """Fetch current weather from Open-Meteo (free, no API key)."""
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


def _render_weather(weather):
    """Render weather data to a PIL Image."""
    image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 15))
    draw = ImageDraw.Draw(image)
    
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    
    code = weather.get("code", 0)
    temp = weather.get("temp")
    wind = weather.get("wind")
    humidity = weather.get("humidity")
    
    condition = WMO_CODES.get(code, "Unknown")
    
    # Get color theme based on weather
    color_key = min(WMO_COLORS.keys(), key=lambda k: abs(k - code))
    accent = WMO_COLORS.get(color_key, (200, 200, 200))
    
    # Temperature (big, centered)
    if temp is not None:
        temp_text = f"{int(temp)}F"
        draw.text((8, 5), temp_text, fill=accent, font=font)
    
    # Condition
    # Truncate to fit 64px (roughly 10 chars at default font)
    short_cond = condition[:10]
    draw.text((2, 22), short_cond, fill=(200, 200, 200), font=font)
    
    # Wind
    if wind is not None:
        draw.text((2, 38), f"Wind:{int(wind)}mph", fill=(150, 200, 150), font=font)
    
    # Humidity
    if humidity is not None:
        draw.text((2, 50), f"Hum:{int(humidity)}%", fill=(150, 150, 200), font=font)
    
    return image


def run(matrix, duration=60):
    """Run the weather display for the specified duration."""
    start_time = time.time()
    last_fetch = 0
    weather = None
    
    try:
        while time.time() - start_time < duration:
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
