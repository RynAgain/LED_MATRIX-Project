#!/usr/bin/env python3
"""
Moon & Planet Tracker -- Animated solar system display for 64x64 LED matrix.

Shows an animated orrery (solar system model) with:
- Sun at center with pulsing glow
- Inner planets (Mercury, Venus, Earth, Mars) orbiting with correct relative speeds
- Moon orbiting Earth
- Jupiter and Saturn as outer planets
- Planet sizes roughly proportional
- Orbital paths shown as dim rings
- Current moon phase indicator
- Planet labels on hover
"""

import time
import math
import logging
from datetime import datetime
from PIL import Image, ImageDraw
from src.display._shared import should_stop
from src.display._fonts import _draw_text, _text_width

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FPS = 15
FRAME_DUR = 1.0 / FPS
CX, CY = WIDTH // 2, HEIGHT // 2

# Planet data: (name, orbit_radius, orbital_period_days, size, color)
# Orbital periods relative to Earth (365.25 days)
PLANETS = [
    ("Mercury", 8, 88, 1, (180, 180, 160)),
    ("Venus", 12, 225, 1, (255, 200, 100)),
    ("Earth", 17, 365, 2, (80, 150, 255)),
    ("Mars", 22, 687, 1, (220, 80, 40)),
    ("Jupiter", 28, 4333, 3, (200, 170, 120)),
    ("Saturn", 30, 10759, 2, (220, 200, 150)),
]

# Moon data
MOON_ORBIT_RADIUS = 4  # Distance from Earth
MOON_PERIOD = 27.3  # Days
MOON_SIZE = 1
MOON_COLOR = (200, 200, 210)

# Sun
SUN_RADIUS = 4
SUN_COLOR = (255, 200, 50)
SUN_GLOW_COLOR = (100, 80, 20)

# Orbit ring color
ORBIT_COLOR = (15, 15, 25)

# Saturn ring
SATURN_RING_COLOR = (180, 160, 120)


def _get_planet_angle(orbital_period_days):
    """Calculate current orbital angle based on real time.

    Uses J2000 epoch as reference. Not astronomically precise but gives
    nice relative motion that corresponds roughly to reality.
    """
    # Days since J2000 epoch (Jan 1, 2000 12:00 UTC)
    now = datetime.utcnow()
    j2000 = datetime(2000, 1, 1, 12, 0, 0)
    days_since = (now - j2000).total_seconds() / 86400.0

    # Angle in radians (full orbit = 2*pi)
    angle = (days_since / orbital_period_days) * 2 * math.pi
    return angle


def _get_moon_phase():
    """Get current moon phase as 0.0-1.0 (0=new, 0.5=full)."""
    now = datetime.utcnow()
    # Known new moon: Jan 6, 2000
    ref = datetime(2000, 1, 6, 18, 14, 0)
    days = (now - ref).total_seconds() / 86400.0
    phase = (days % 29.53) / 29.53
    return phase


def _draw_moon_phase_indicator(draw, phase):
    """Draw a small moon phase icon in the corner."""
    # Position in bottom-left corner
    mx, my = 8, HEIGHT - 8
    r = 4

    # Draw full circle in dark
    draw.ellipse([(mx - r, my - r), (mx + r, my + r)], fill=(30, 30, 40))

    # Illuminate based on phase
    # phase: 0=new (dark), 0.25=first quarter, 0.5=full, 0.75=last quarter
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                # Determine if this pixel is illuminated
                # Map dx to -1..1 range relative to radius
                norm_x = dx / r
                # Terminator position based on phase
                if phase < 0.5:
                    # Waxing: right side lit, terminator moves left
                    terminator = math.cos(phase * 2 * math.pi)
                    lit = norm_x > terminator
                else:
                    # Waning: left side lit, terminator moves right
                    terminator = math.cos(phase * 2 * math.pi)
                    lit = norm_x < -terminator

                if lit:
                    px, py = mx + dx, my + dy
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        draw.point((px, py), fill=(220, 220, 230))


def _draw_sun(draw, tick):
    """Draw the sun at center with animated glow."""
    # Pulsing glow
    pulse = 0.7 + 0.3 * math.sin(tick * 0.08)

    # Outer glow layers
    for gr in range(SUN_RADIUS + 3, SUN_RADIUS, -1):
        alpha = (SUN_RADIUS + 3 - gr + 1) / 4.0 * pulse
        color = (
            int(SUN_GLOW_COLOR[0] * alpha),
            int(SUN_GLOW_COLOR[1] * alpha),
            int(SUN_GLOW_COLOR[2] * alpha),
        )
        draw.ellipse([(CX - gr, CY - gr), (CX + gr, CY + gr)], fill=color)

    # Sun body
    bright = int(255 * (0.9 + 0.1 * pulse))
    sun_c = (bright, int(bright * 0.78), int(bright * 0.2))
    draw.ellipse([(CX - SUN_RADIUS, CY - SUN_RADIUS),
                  (CX + SUN_RADIUS, CY + SUN_RADIUS)], fill=sun_c)

    # Hot center
    draw.ellipse([(CX - 2, CY - 2), (CX + 2, CY + 2)],
                 fill=(255, 255, 200))


def _draw_orbit_rings(draw):
    """Draw faint orbital path rings."""
    for _, radius, _, _, _ in PLANETS:
        # Draw dotted circle
        for deg in range(0, 360, 6):
            angle = math.radians(deg)
            px = int(CX + radius * math.cos(angle))
            py = int(CY + radius * math.sin(angle))
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                draw.point((px, py), fill=ORBIT_COLOR)


def _draw_planet(draw, name, x, y, size, color):
    """Draw a planet at position."""
    ix, iy = int(x), int(y)

    if size == 1:
        if 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
            draw.point((ix, iy), fill=color)
    elif size == 2:
        draw.rectangle([(ix - 1, iy - 1), (ix, iy)], fill=color)
    else:
        r = size // 2
        draw.ellipse([(ix - r, iy - r), (ix + r, iy + r)], fill=color)

    # Saturn gets a ring
    if name == "Saturn":
        ring_y = iy
        draw.line([(ix - size - 1, ring_y), (ix + size + 1, ring_y)],
                  fill=SATURN_RING_COLOR)


def run(matrix, duration=60):
    """Run the moon & planet tracker animation."""
    start_time = time.time()
    tick = 0

    # Speed multiplier for demo animation (planets move faster for visual interest)
    # In real time they'd barely move on a 64x64 display
    time_accel = 200  # 200x real speed for visible orbital motion

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            tick += 1

            image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 3))
            draw = ImageDraw.Draw(image)

            # Starfield background (static, seeded)
            for i in range(30):
                sx = (i * 17 + 5) % WIDTH
                sy = (i * 23 + 11) % HEIGHT
                brightness = 40 + (i * 7) % 60
                draw.point((sx, sy), fill=(brightness, brightness, brightness + 20))

            # Orbit rings
            _draw_orbit_rings(draw)

            # Sun
            _draw_sun(draw, tick)

            # Elapsed time for animation (accelerated)
            elapsed_days = (time.time() - start_time) * time_accel / 86400.0

            # Draw planets
            earth_x, earth_y = 0, 0
            for name, radius, period, size, color in PLANETS:
                # Base angle from real time + accelerated demo offset
                base_angle = _get_planet_angle(period)
                demo_offset = (elapsed_days / period) * 2 * math.pi
                angle = base_angle + demo_offset

                px = CX + radius * math.cos(angle)
                py = CY + radius * math.sin(angle)

                _draw_planet(draw, name, px, py, size, color)

                # Track Earth for moon
                if name == "Earth":
                    earth_x, earth_y = px, py

            # Draw Moon orbiting Earth
            moon_base_angle = _get_planet_angle(MOON_PERIOD)
            moon_offset = (elapsed_days / MOON_PERIOD) * 2 * math.pi
            moon_angle = moon_base_angle + moon_offset

            moon_x = earth_x + MOON_ORBIT_RADIUS * math.cos(moon_angle)
            moon_y = earth_y + MOON_ORBIT_RADIUS * math.sin(moon_angle)
            if 0 <= int(moon_x) < WIDTH and 0 <= int(moon_y) < HEIGHT:
                draw.point((int(moon_x), int(moon_y)), fill=MOON_COLOR)

            # Moon phase indicator (actual current phase)
            phase = _get_moon_phase()
            _draw_moon_phase_indicator(draw, phase)

            # Label in top-right
            _draw_text(draw, "ORRERY", 2, 1, (50, 50, 80), scale=1, spacing=0)

            # Show current moon phase text
            if phase < 0.05 or phase > 0.95:
                phase_name = "NEW"
            elif 0.2 < phase < 0.3:
                phase_name = "1Q"
            elif 0.45 < phase < 0.55:
                phase_name = "FULL"
            elif 0.7 < phase < 0.8:
                phase_name = "3Q"
            else:
                phase_name = ""

            if phase_name:
                pw = _text_width(phase_name, scale=1, spacing=0)
                _draw_text(draw, phase_name, 2, HEIGHT - 14, (120, 120, 160),
                           scale=1, spacing=0)

            matrix.SetImage(image)

            elapsed = time.time() - frame_start
            sleep_time = FRAME_DUR - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in moon_tracker: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
