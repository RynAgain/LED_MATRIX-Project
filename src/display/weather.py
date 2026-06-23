#!/usr/bin/env python3
"""Weather display for 64x64 LED matrix using Open-Meteo free API.

Uses the shared 5x7 bitmap font from _fonts.py for crisp, readable text
on the LED matrix. Features animated weather icons (sun rays, rain drops,
snow flakes, cloud movement, lightning) alongside temperature and conditions.
"""

import time
import math
import logging
import json
import os
import random
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

# Weather animation categories
ANIM_CLEAR = 0
ANIM_CLOUDY = 1
ANIM_RAIN = 2
ANIM_SNOW = 3
ANIM_STORM = 4
ANIM_FOG = 5

def _code_to_anim(code):
    """Map WMO weather code to animation type."""
    if code in (0, 1):
        return ANIM_CLEAR
    elif code in (2, 3):
        return ANIM_CLOUDY
    elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
        return ANIM_RAIN
    elif code in (71, 73, 75):
        return ANIM_SNOW
    elif code in (95, 96, 99):
        return ANIM_STORM
    elif code in (45, 48):
        return ANIM_FOG
    return ANIM_CLEAR


class WeatherAnimator:
    """Draws animated weather icons in a given region of the image."""

    def __init__(self, anim_type):
        self.anim_type = anim_type
        self.tick = 0
        # Rain/snow particles: (x, y) positions
        self.particles = []
        self._init_particles()

    def _init_particles(self):
        """Initialize particles for rain/snow animations."""
        if self.anim_type in (ANIM_RAIN, ANIM_STORM):
            self.particles = [[random.randint(2, 20), random.randint(0, 28)] for _ in range(8)]
        elif self.anim_type == ANIM_SNOW:
            self.particles = [[random.randint(2, 20), random.randint(0, 28)] for _ in range(6)]

    def draw(self, draw_ctx, x_offset, y_offset, w=22, h=28):
        """Draw one frame of the weather animation.

        Args:
            draw_ctx: PIL ImageDraw context
            x_offset: left edge of the animation area
            y_offset: top edge of the animation area
            w: width of animation area
            h: height of animation area
        """
        self.tick += 1

        if self.anim_type == ANIM_CLEAR:
            self._draw_sun(draw_ctx, x_offset, y_offset, w, h)
        elif self.anim_type == ANIM_CLOUDY:
            self._draw_clouds(draw_ctx, x_offset, y_offset, w, h)
        elif self.anim_type == ANIM_RAIN:
            self._draw_clouds(draw_ctx, x_offset, y_offset, w, h)
            self._draw_rain(draw_ctx, x_offset, y_offset, w, h)
        elif self.anim_type == ANIM_SNOW:
            self._draw_clouds(draw_ctx, x_offset, y_offset, w, h)
            self._draw_snow(draw_ctx, x_offset, y_offset, w, h)
        elif self.anim_type == ANIM_STORM:
            self._draw_clouds(draw_ctx, x_offset, y_offset, w, h)
            self._draw_rain(draw_ctx, x_offset, y_offset, w, h)
            self._draw_lightning(draw_ctx, x_offset, y_offset, w, h)
        elif self.anim_type == ANIM_FOG:
            self._draw_fog(draw_ctx, x_offset, y_offset, w, h)

    def _draw_sun(self, draw_ctx, xo, yo, w, h):
        """Animated sun with rotating rays."""
        cx = xo + w // 2
        cy = yo + h // 2
        # Sun body
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx * dx + dy * dy <= 9:
                    draw_ctx.point((cx + dx, cy + dy), fill=(255, 200, 0))

        # Rotating rays
        num_rays = 8
        ray_len = 4
        angle_offset = self.tick * 0.1
        for i in range(num_rays):
            angle = angle_offset + i * (2 * math.pi / num_rays)
            # Ray start (just outside sun body)
            sx = cx + int(4 * math.cos(angle))
            sy = cy + int(4 * math.sin(angle))
            # Ray end
            ex = cx + int((4 + ray_len) * math.cos(angle))
            ey = cy + int((4 + ray_len) * math.sin(angle))
            # Pulsing brightness
            pulse = int(180 + 75 * math.sin(self.tick * 0.2 + i))
            color = (pulse, pulse // 2, 0)
            draw_ctx.line([(sx, sy), (ex, ey)], fill=color)

    def _draw_clouds(self, draw_ctx, xo, yo, w, h):
        """Drifting cloud shapes."""
        # Cloud 1 (larger, drifts slowly)
        drift1 = int(math.sin(self.tick * 0.05) * 3)
        cx1 = xo + 10 + drift1
        cy1 = yo + 6
        for dx in range(-4, 5):
            for dy in range(-2, 3):
                if (dx * dx) / 16 + (dy * dy) / 4 <= 1:
                    draw_ctx.point((cx1 + dx, cy1 + dy), fill=(140, 140, 160))

        # Cloud 2 (smaller, drifts faster)
        drift2 = int(math.sin(self.tick * 0.08 + 1.5) * 2)
        cx2 = xo + 6 + drift2
        cy2 = yo + 10
        for dx in range(-3, 4):
            for dy in range(-1, 2):
                if (dx * dx) / 9 + (dy * dy) / 1 <= 1:
                    draw_ctx.point((cx2 + dx, cy2 + dy), fill=(120, 120, 140))

    def _draw_rain(self, draw_ctx, xo, yo, w, h):
        """Falling rain drops."""
        speed = 2 if self.anim_type == ANIM_STORM else 1
        for p in self.particles:
            p[1] += speed
            if p[1] > h - 2:
                p[1] = random.randint(10, 14)
                p[0] = random.randint(2, w - 2)

            px = xo + p[0]
            py = yo + p[1]
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                draw_ctx.point((px, py), fill=(80, 140, 255))
                if py + 1 < HEIGHT:
                    draw_ctx.point((px, py + 1), fill=(40, 80, 180))

    def _draw_snow(self, draw_ctx, xo, yo, w, h):
        """Gently falling snowflakes with drift."""
        for p in self.particles:
            p[1] += 0.5
            p[0] += math.sin(self.tick * 0.1 + p[1] * 0.3) * 0.3
            if p[1] > h - 2:
                p[1] = random.randint(10, 14)
                p[0] = random.randint(2, w - 2)

            px = xo + int(p[0])
            py = yo + int(p[1])
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                # Snowflake: single bright pixel
                brightness = int(180 + 75 * math.sin(self.tick * 0.15 + p[0]))
                draw_ctx.point((px, py), fill=(brightness, brightness, brightness))

    def _draw_lightning(self, draw_ctx, xo, yo, w, h):
        """Occasional lightning flash."""
        # Flash every ~40 ticks for a few frames
        cycle = self.tick % 60
        if cycle < 3:
            # Lightning bolt shape
            bx = xo + w // 2
            by = yo + 12
            points = [(bx, by), (bx - 1, by + 4), (bx + 2, by + 4),
                      (bx, by + 8), (bx + 3, by + 5), (bx + 1, by + 5),
                      (bx + 2, by + 2)]
            for px, py in points:
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    draw_ctx.point((px, py), fill=(255, 255, 200))
            # Brief screen flash effect
            if cycle == 0:
                for fx in range(xo, xo + w):
                    for fy in range(yo, yo + h):
                        if 0 <= fx < WIDTH and 0 <= fy < HEIGHT:
                            if random.random() < 0.05:
                                draw_ctx.point((fx, fy), fill=(100, 100, 120))

    def _draw_fog(self, draw_ctx, xo, yo, w, h):
        """Drifting fog layers."""
        for layer in range(4):
            y = yo + 5 + layer * 6
            drift = int(math.sin(self.tick * 0.03 + layer * 1.2) * 4)
            alpha = 60 + layer * 20
            for x in range(w - 4):
                px = xo + x + drift
                # Wavy fog line
                wave = int(math.sin((x + self.tick * 0.1) * 0.5) * 1.5)
                py = y + wave
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    draw_ctx.point((px, py), fill=(alpha, alpha, alpha + 20))


def _sanity_check_code(code, rain, cloud_cover):
    """Cross-check weather_code against actual precipitation and cloud data.

    Open-Meteo's weather_code is model-predicted and often reports storms
    (code 95+) or rain (61+) when precipitation is actually 0mm and skies
    are clear. Override bogus codes using real observations.
    """
    # If code says rain/storm but there's no precipitation, fix it
    rain_codes = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}
    if code in rain_codes and rain is not None and rain <= 0.0:
        # No actual rain — determine condition from cloud cover
        if cloud_cover is not None:
            if cloud_cover < 10:
                return 0   # Clear
            elif cloud_cover < 30:
                return 1   # Mostly clear
            elif cloud_cover < 70:
                return 2   # Partly cloudy
            else:
                return 3   # Overcast
        return 2  # Default to partly cloudy if no cloud data

    return code


def _fetch_weather(lat=None, lon=None):
    """Fetch current weather from Open-Meteo (free, no API key).

    Requests additional fields (rain, cloud_cover) to cross-check the
    weather_code which is often unreliable (predicts storms that aren't
    happening based on model interpolation rather than observations).
    """
    if lat is None or lon is None:
        lat, lon = _load_location()
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weather_code,wind_speed_10m,"
        f"relative_humidity_2m,rain,cloud_cover,precipitation"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})

        # Get raw code and cross-check against actual conditions
        raw_code = current.get("weather_code", 0)
        rain = current.get("rain", current.get("precipitation", 0.0))
        cloud_cover = current.get("cloud_cover")
        corrected_code = _sanity_check_code(raw_code, rain, cloud_cover)

        if corrected_code != raw_code:
            logger.info(
                "Weather code corrected: %d -> %d (rain=%.1f, clouds=%s%%)",
                raw_code, corrected_code, rain or 0,
                cloud_cover if cloud_cover is not None else "?"
            )

        return {
            "temp": current.get("temperature_2m"),
            "code": corrected_code,
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


def _render_weather(weather, animator, stale=False):
    """Render weather data with animated icon to a PIL Image.

    Layout (64x64):
      Left side (0-22):  Animated weather icon
      Right side (24-63): Temperature, condition, wind, humidity

    Args:
        weather: Dict with temp, code, wind, humidity
        animator: WeatherAnimator instance
        stale: If True, data is outdated (>15 min since last successful fetch)
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(image)

    code = weather.get("code", 0)
    temp = weather.get("temp")
    wind = weather.get("wind")
    humidity = weather.get("humidity")

    condition = WMO_CODES.get(code, "UNKNOWN")
    accent = _get_accent_color(code)

    # --- Left side: animated weather icon (columns 0-22, rows 2-30) ---
    animator.draw(draw, x_offset=0, y_offset=2, w=22, h=28)

    # --- Right side: text data (columns 24-63) ---
    text_x = 24

    # Temperature — large (scale=2) for emphasis
    if temp is not None:
        temp_str = "{}F".format(int(temp))
        _draw_text(draw, temp_str, text_x, 4, TEMP_COLOR, scale=2, spacing=1)
    else:
        _draw_text(draw, "N/A", text_x, 4, TEMP_COLOR, scale=2, spacing=1)

    # Condition text — below temperature
    _draw_text(draw, condition, text_x, 20, accent, scale=1, spacing=1)

    # Separator line
    draw.line([(2, 32), (61, 32)], fill=SEPARATOR_COLOR)

    # Wind — full width below separator
    if wind is not None:
        wind_label = "WIND"
        _draw_text(draw, wind_label, 2, 36, WIND_COLOR, scale=1, spacing=1)
        wind_val = "{}MPH".format(int(wind))
        vw = _text_width(wind_val, scale=1)
        _draw_text(draw, wind_val, WIDTH - vw - 2, 36, (255, 255, 255),
                   scale=1, spacing=1)

    # Humidity
    if humidity is not None:
        hum_label = "HUM"
        _draw_text(draw, hum_label, 2, 46, HUMIDITY_COLOR, scale=1, spacing=1)
        hum_val = "{}%".format(int(humidity))
        hw = _text_width(hum_val, scale=1)
        _draw_text(draw, hum_val, WIDTH - hw - 2, 46, (255, 255, 255),
                   scale=1, spacing=1)

    # Accent bar at bottom (weather-themed color indicator)
    draw.rectangle([4, 58, 59, 61], fill=accent)

    # Stale data indicator — dim dot in top-right corner
    if stale:
        draw.point((62, 1), fill=(80, 40, 0))

    return image


def run(matrix, duration=60):
    """Run the weather display for the specified duration."""
    start_time = time.time()
    last_fetch = 0
    last_successful_fetch = 0
    weather = None
    animator = None

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            now = time.time()

            # Fetch weather every 5 minutes (API updates ~15min, no need to hammer)
            if now - last_fetch > 300 or weather is None:
                new_weather = _fetch_weather()
                last_fetch = now
                if new_weather is not None:
                    weather = new_weather
                    last_successful_fetch = now
                    anim_type = _code_to_anim(weather.get("code", 0))
                    if animator is None or animator.anim_type != anim_type:
                        animator = WeatherAnimator(anim_type)
                else:
                    logger.warning("Weather fetch failed, keeping last known data")

            if weather and animator:
                # If data is stale (>15 min), show a dim indicator
                stale = (now - last_successful_fetch > 900) if last_successful_fetch else False
                image = _render_weather(weather, animator, stale=stale)
                matrix.SetImage(image)

            # Animate at ~10 FPS for smooth weather animations
            time.sleep(0.1)

    except Exception as e:
        logger.error("Error in weather display: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
