#!/usr/bin/env python3
"""System stats display for 64x64 LED matrix.

Shows CPU usage, RAM usage, CPU temperature as animated bar graphs,
plus hostname and IP address at the bottom. Refreshes every 2 seconds.

Uses psutil for cross-platform stats. Falls back to reading
/sys/class/thermal/thermal_zone0/temp for CPU temp on Raspberry Pi
when psutil doesn't report it.
"""

import time
import socket
import platform
import logging
from PIL import Image, ImageDraw
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
REFRESH_INTERVAL = 2.0

# Colors
BG_COLOR = (0, 0, 0)
LABEL_COLOR = (180, 180, 200)
VALUE_COLOR = (255, 255, 255)
BAR_BG = (30, 30, 50)
BAR_CPU = (0, 150, 255)
BAR_RAM = (180, 0, 255)
HOSTNAME_COLOR = (100, 100, 140)
IP_COLOR = (80, 160, 120)

# Temperature color thresholds
TEMP_GREEN = (0, 200, 80)
TEMP_YELLOW = (255, 200, 0)
TEMP_RED = (255, 40, 40)

# 5x7 pixel font -- same as boot_screen.py FONT_5X7
FONT_5X7 = {
    'A': [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    'B': [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    'C': [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    'D': [0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C],
    'E': [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    'F': [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    'G': [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0E],
    'H': [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    'I': [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    'J': [0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
    'K': [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    'L': [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    'M': [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    'N': [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    'O': [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    'P': [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    'Q': [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    'R': [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    'S': [0x0E, 0x11, 0x10, 0x0E, 0x01, 0x11, 0x0E],
    'T': [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    'U': [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    'V': [0x11, 0x11, 0x11, 0x11, 0x0A, 0x0A, 0x04],
    'W': [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
    'X': [0x11, 0x0A, 0x04, 0x04, 0x04, 0x0A, 0x11],
    'Y': [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    'Z': [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    '0': [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    '1': [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    '2': [0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F],
    '3': [0x0E, 0x11, 0x01, 0x06, 0x01, 0x11, 0x0E],
    '4': [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    '5': [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    '6': [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    '7': [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    '8': [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    '9': [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04],
    ':': [0x00, 0x04, 0x04, 0x00, 0x04, 0x04, 0x00],
    '/': [0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10],
    '-': [0x00, 0x00, 0x00, 0x0E, 0x00, 0x00, 0x00],
    '%': [0x19, 0x19, 0x02, 0x04, 0x08, 0x13, 0x13],
    '!': [0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04],
    '?': [0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04],
}


def _draw_char(draw, char, x, y, color, scale=1):
    """Draw a single character from the 5x7 font."""
    glyph = FONT_5X7.get(char.upper(), FONT_5X7.get(' '))
    for row_idx, row_bits in enumerate(glyph):
        for col in range(5):
            if row_bits & (0x10 >> col):
                px = x + col * scale
                py = y + row_idx * scale
                if scale == 1:
                    draw.point((px, py), fill=color)
                else:
                    draw.rectangle(
                        [px, py, px + scale - 1, py + scale - 1],
                        fill=color
                    )


def _draw_text(draw, text, x, y, color, scale=1, spacing=1):
    """Draw a string of text using the 5x7 font."""
    char_w = 5 * scale + spacing
    for i, ch in enumerate(text):
        _draw_char(draw, ch, x + i * char_w, y, color, scale)
    return len(text) * char_w - spacing


def _text_width(text, scale=1, spacing=1):
    """Calculate the pixel width of a text string."""
    if not text:
        return 0
    char_w = 5 * scale + spacing
    return len(text) * char_w - spacing


def _get_cpu_percent():
    """Get CPU usage percentage."""
    try:
        import psutil
        return psutil.cpu_percent(interval=0)
    except Exception:
        return 0.0


def _get_ram_percent():
    """Get RAM usage percentage."""
    try:
        import psutil
        return psutil.virtual_memory().percent
    except Exception:
        return 0.0


def _get_cpu_temp():
    """Get CPU temperature in Celsius.

    Tries psutil first, then falls back to the Raspberry Pi thermal zone file.
    Returns None if temperature cannot be read.
    """
    # Try psutil sensors_temperatures (Linux)
    try:
        import psutil
        if hasattr(psutil, 'sensors_temperatures'):
            temps = psutil.sensors_temperatures()
            if temps:
                # Try common sensor names
                for name in ('coretemp', 'cpu_thermal', 'cpu-thermal',
                             'soc_thermal', 'k10temp', 'zenpower'):
                    if name in temps and temps[name]:
                        return temps[name][0].current
                # Fall back to first available sensor
                for sensor_list in temps.values():
                    if sensor_list:
                        return sensor_list[0].current
    except Exception:
        pass

    # Raspberry Pi fallback: read thermal zone
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            millidegrees = int(f.read().strip())
            return millidegrees / 1000.0
    except (FileNotFoundError, ValueError, OSError):
        pass

    return None


def _get_hostname():
    """Get the system hostname (truncated to fit display)."""
    try:
        name = platform.node()
        if not name:
            name = socket.gethostname()
        return name[:10].upper()
    except Exception:
        return "UNKNOWN"


def _get_ip_address():
    """Get the primary IP address."""
    try:
        # Connect to a public DNS to determine our local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "NO IP"


def _temp_color(temp_c):
    """Return color based on temperature threshold."""
    if temp_c is None:
        return LABEL_COLOR
    if temp_c < 50:
        return TEMP_GREEN
    if temp_c < 70:
        return TEMP_YELLOW
    return TEMP_RED


def _lerp_color(color_a, color_b, t):
    """Linearly interpolate between two RGB colors."""
    t = max(0.0, min(1.0, t))
    return (
        int(color_a[0] + (color_b[0] - color_a[0]) * t),
        int(color_a[1] + (color_b[1] - color_a[1]) * t),
        int(color_a[2] + (color_b[2] - color_a[2]) * t),
    )


def _draw_bar(draw, x, y, width, height, percent, bar_color, animated_pct=None):
    """Draw a horizontal bar graph with animated fill.

    Args:
        draw: PIL ImageDraw instance.
        x, y: Top-left corner.
        width, height: Bar dimensions.
        percent: Target percentage (0-100).
        bar_color: RGB tuple for the fill color.
        animated_pct: Current animated percentage (for smooth transitions).
    """
    pct = animated_pct if animated_pct is not None else percent

    # Background
    draw.rectangle([x, y, x + width - 1, y + height - 1], fill=BAR_BG)

    # Fill
    fill_w = int((width - 2) * pct / 100.0)
    if fill_w > 0:
        for col_offset in range(fill_w):
            frac = col_offset / max(width - 2, 1)
            # Gradient: bar_color dims slightly toward the right edge
            c = _lerp_color(
                bar_color,
                (bar_color[0] // 2, bar_color[1] // 2, bar_color[2] // 2),
                frac * 0.3
            )
            draw.line([(x + 1 + col_offset, y + 1),
                       (x + 1 + col_offset, y + height - 2)], fill=c)

    # Border
    draw.rectangle([x, y, x + width - 1, y + height - 1], outline=(50, 50, 70))


def _draw_frame(draw, cpu_pct, ram_pct, cpu_temp, hostname, ip_addr,
                anim_cpu, anim_ram):
    """Render one frame of the system stats display.

    Layout (64x64):
      Row  0-7:   Title "SYSTEM" centered
      Row  9:     Thin separator line
      Row 12-18:  CPU label + percentage text
      Row 20-24:  CPU bar
      Row 28-34:  RAM label + percentage text
      Row 36-40:  RAM bar
      Row 44-50:  TEMP label + value (color-coded)
      Row 52-54:  TEMP bar
      Row 57-63:  Hostname / IP
    """
    # Title
    title = "SYSTEM"
    tw = _text_width(title, scale=1, spacing=1)
    _draw_text(draw, title, (WIDTH - tw) // 2, 1, (100, 160, 255),
               scale=1, spacing=1)

    # Separator line
    draw.line([(4, 9), (59, 9)], fill=(40, 40, 70))

    # --- CPU Section ---
    _draw_text(draw, "CPU", 2, 12, LABEL_COLOR, scale=1, spacing=1)
    cpu_str = "{}%".format(int(cpu_pct))
    csw = _text_width(cpu_str, scale=1, spacing=1)
    _draw_text(draw, cpu_str, WIDTH - csw - 2, 12, VALUE_COLOR,
               scale=1, spacing=1)
    _draw_bar(draw, 2, 20, 60, 5, cpu_pct, BAR_CPU, animated_pct=anim_cpu)

    # --- RAM Section ---
    _draw_text(draw, "RAM", 2, 28, LABEL_COLOR, scale=1, spacing=1)
    ram_str = "{}%".format(int(ram_pct))
    rsw = _text_width(ram_str, scale=1, spacing=1)
    _draw_text(draw, ram_str, WIDTH - rsw - 2, 28, VALUE_COLOR,
               scale=1, spacing=1)
    _draw_bar(draw, 2, 36, 60, 5, ram_pct, BAR_RAM, animated_pct=anim_ram)

    # --- Temperature Section ---
    _draw_text(draw, "TEMP", 2, 44, LABEL_COLOR, scale=1, spacing=1)
    if cpu_temp is not None:
        temp_str = "{}C".format(int(cpu_temp))
        tc = _temp_color(cpu_temp)
    else:
        temp_str = "N/A"
        tc = LABEL_COLOR
    tsw = _text_width(temp_str, scale=1, spacing=1)
    _draw_text(draw, temp_str, WIDTH - tsw - 2, 44, tc, scale=1, spacing=1)

    # Temperature bar (visual indicator)
    if cpu_temp is not None:
        # Scale 0-100C to bar width
        temp_pct = min(100, max(0, cpu_temp))
        _draw_bar(draw, 2, 52, 60, 3, temp_pct, tc)

    # --- Hostname ---
    hw = _text_width(hostname, scale=1, spacing=1)
    host_x = max(0, (WIDTH - hw) // 2)
    _draw_text(draw, hostname, host_x, 57, HOSTNAME_COLOR,
               scale=1, spacing=1)


def run(matrix, duration=60):
    """Run the system stats display for the specified duration.

    Args:
        matrix: RGBMatrix instance (or simulator).
        duration: How long to run in seconds.
    """
    start_time = time.time()

    # Animated bar values (for smooth transitions)
    anim_cpu = 0.0
    anim_ram = 0.0

    # Cache hostname and IP (don't re-query every frame)
    hostname = _get_hostname()
    ip_addr = _get_ip_address()

    # Initial psutil CPU reading (first call always returns 0)
    try:
        import psutil
        psutil.cpu_percent(interval=0)
    except Exception:
        pass

    last_refresh = 0.0

    # Current target values
    target_cpu = 0.0
    target_ram = 0.0
    cpu_temp = None

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break

            frame_start = time.time()
            now = time.time()

            # Refresh stats every REFRESH_INTERVAL
            if now - last_refresh >= REFRESH_INTERVAL:
                target_cpu = _get_cpu_percent()
                target_ram = _get_ram_percent()
                cpu_temp = _get_cpu_temp()
                last_refresh = now

                # Refresh IP periodically in case network changes
                ip_addr = _get_ip_address()

            # Animate bars toward target (smooth interpolation)
            lerp_speed = 0.15
            anim_cpu += (target_cpu - anim_cpu) * lerp_speed
            anim_ram += (target_ram - anim_ram) * lerp_speed

            # Render frame
            image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
            draw = ImageDraw.Draw(image)

            _draw_frame(draw, target_cpu, target_ram, cpu_temp,
                        hostname, ip_addr, anim_cpu, anim_ram)

            matrix.SetImage(image)

            # ~15 FPS for smooth bar animation
            elapsed = time.time() - frame_start
            sleep_time = (1.0 / 15) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in system stats display: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
