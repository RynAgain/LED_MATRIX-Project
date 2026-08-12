#!/usr/bin/env python3
"""Precipitation radar over the local street map for a 64x64 LED matrix.

Animated rain cells (RainViewer composite radar) sweeping over the same
Austin basemap the flight radar uses (``config/flight_radar_map.json``:
major highways and the river, pre-fetched from OpenStreetMap). The last
hour or so of radar history loops, holding on the newest frame, followed
by RainViewer's short nowcast when one is published -- so during storm
season you can watch a cell march toward your own street.

All network work lives on a background thread (index poll + tile
fetches); the render loop only ever reads the latest list of pre-built
64x64 overlays. With no network the basemap still draws and the HUD
blinks NO LINK, matching the flight radar's behaviour.

Tile pipeline (built once per radar frame, then cached by tile path):
RainViewer serves Web-Mercator tiles up to zoom 7 for radar (higher
zooms return an error *image*, not an error status), and the tilecache
ignores the colour-scheme path segment: every request comes back in
their standard palette (translucent khaki drizzle, blues, then yellow /
orange / red cores). Intensity is therefore recovered from hue and
brightness rather than trusted grey values. The tiles covering the
configured box are stitched, cropped, resized with alpha-weighted
channels (plain bilinear would bleed background into cell edges) and
quantised to an LED-friendly ramp.
"""

import colorsys
import math
import io
import threading
import time
import logging

import requests
from PIL import Image, ImageChops, ImageDraw

from src.display._shared import should_stop
from src.display._fonts import _draw_text, _text_width
from src.display.flight_radar import (
    _load_config as _radar_config,
    _load_map,
    _project,
)

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
CX, CY = 32, 32
FRAME_INTERVAL = 1.0 / 30

INDEX_URL = "https://api.rainviewer.com/public/weather-maps.json"
USER_AGENT = "LED-Matrix-Project/rain_radar"
TILE_SIZE = 512
ZOOM = 7                    # RainViewer's radar maximum; 512px tiles keep
                            # ~183px across a 60 mile box at 30N
PAST_FRAMES = 7             # radar history frames kept (10 min apart)
NOWCAST_FRAMES = 3          # forecast frames appended after "now"
POLL_SECONDS = 300.0        # RainViewer publishes every ~10 minutes

FRAME_DWELL = 0.5           # seconds per animation frame
HOLD_DWELL = 2.0            # extra dwell on the newest observed frame

ECHO_MIN_ALPHA = 40         # below this the resampled echo is noise

# RainViewer's composite paints large fields of near-transparent khaki
# over dry air (verified live: ~5% of the Austin box on a rain-free day,
# alpha 32-95). Those pixels rank 0.05-0.08 in _intensity; anything below
# this floor is dropped instead of rendered as drizzle. Real echoes
# (blues and up) rank 0.15+.
RAIN_MIN_RANK = 0.10

# Intensity rank (0..1, from _intensity) -> LED colour ramp.
RAIN_BANDS = [
    (0.12, (18, 84, 34)),    # drizzle
    (0.35, (30, 150, 46)),   # light rain
    (0.60, (188, 168, 32)),  # moderate
    (0.80, (216, 118, 24)),  # heavy
    (0.93, (228, 44, 36)),   # very heavy
    (1.01, (196, 60, 202)),  # extreme / hail core
]

MAP_ROAD = (30, 36, 34)
MAP_WATER = (18, 40, 66)
CENTRE_MARK = (110, 110, 120)
RING = (26, 30, 34)

HUD_HEIGHT = 7
HUD_BG = (6, 8, 10)
HUD_DIM = (90, 100, 110)
HUD_TEXT = (190, 200, 210)
ALERT = (220, 60, 50)
TICK_PAST = (70, 80, 88)
TICK_NOW = (240, 240, 240)
TICK_FORECAST = (60, 150, 190)

MILES_PER_DEG_LAT = 69.172


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def _mercator_px(lat, lon, zoom):
    """Global Web-Mercator pixel coordinates of a lat/lon at a zoom level."""
    scale = TILE_SIZE * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * scale
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * scale
    return x, y


def _box_px(lat, lon, radius_miles, zoom):
    """Mercator pixel square covering +/- radius miles around the centre.

    Mercator is conformal, so the box is square in tile pixels; its size
    only depends on the latitude's map scale.
    """
    cx, cy = _mercator_px(lat, lon, zoom)
    deg_lon = radius_miles / (MILES_PER_DEG_LAT * math.cos(math.radians(lat)))
    half = deg_lon * TILE_SIZE * (2 ** zoom) / 360.0
    return cx - half, cy - half, cx + half, cy + half


def _intensity(r, g, b):
    """0..1 rank of a RainViewer palette colour.

    The tilecache serves one fixed palette regardless of the colour-scheme
    URL segment, so intensity is recovered from hue and brightness:
    low-saturation khaki haze is drizzle, blues run light-to-moderate as
    they darken, then yellow, orange, red and magenta escalate.
    """
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    if s < 0.20:
        return 0.05                          # grey haze
    if 0.42 <= h <= 0.75:
        return min(0.45, 0.15 + (1.0 - v) * 0.45)   # blues
    if 0.20 <= h < 0.42:
        return 0.40                          # green
    if 0.11 <= h < 0.20:
        return 0.08 if s < 0.60 else 0.55    # khaki drizzle vs true yellow
    if 0.04 <= h < 0.11:
        return 0.72                          # orange
    if 0.75 < h < 0.93:
        return 0.97                          # magenta / purple core
    return 0.88                              # red


def _color_for(rank):
    """LED colour for an intensity rank (0..1)."""
    for ceiling, color in RAIN_BANDS:
        if rank < ceiling:
            return color
    return RAIN_BANDS[-1][1]


def _colorize(rgb, alpha):
    """(RGB echo, L alpha) at panel size -> RGBA rain overlay.

    Alpha-weighting has already happened during the resize; here each
    echo pixel is ranked and quantised to the LED palette, and weak
    resampled edges are dropped so antialiasing haze does not litter
    the map.
    """
    out = Image.new("RGBA", rgb.size, (0, 0, 0, 0))
    rp = rgb.load()
    ap = alpha.load()
    op = out.load()
    w, h = rgb.size
    for y in range(h):
        for x in range(w):
            a = ap[x, y]
            if a < ECHO_MIN_ALPHA:
                continue
            rank = _intensity(*rp[x, y][:3])
            if rank < RAIN_MIN_RANK:
                continue    # dry-air khaki / grey haze, not rain
            r, g, b = _color_for(rank)
            op[x, y] = (r, g, b, min(255, int(a * 2.2)))
    return out


def _resample_echo(rgb, alpha, box, size):
    """Crop + resize an echo layer with alpha-weighted channels.

    A plain bilinear resize would average the tile's transparent
    background into every cell edge and shift the palette colours off
    their anchors. Weighting each channel by alpha before the resize and
    dividing it back out afterwards keeps edge colours honest.
    """
    rgb = rgb.crop(box)
    alpha = alpha.crop(box)
    a = alpha.resize(size, Image.BILINEAR)
    ap = a.load()
    channels = []
    for ch in rgb.split():
        w = ImageChops.multiply(ch, alpha).resize(size, Image.BILINEAR)
        wp = w.load()
        out = Image.new("L", size, 0)
        op = out.load()
        for y in range(size[1]):
            for x in range(size[0]):
                av = ap[x, y]
                if av:
                    op[x, y] = min(255, wp[x, y] * 255 // av)
        channels.append(out)
    return Image.merge("RGB", channels), a


# --------------------------------------------------------------------------
# feed
# --------------------------------------------------------------------------

class RainFeed:
    """Polls RainViewer on a background thread and pre-builds overlays."""

    def __init__(self, lat, lon, radius_miles, poll_seconds=POLL_SECONDS,
                 zoom=ZOOM):
        self.lat = lat
        self.lon = lon
        self.radius_miles = radius_miles
        self.poll_seconds = poll_seconds
        self.zoom = zoom
        self._lock = threading.Lock()
        self._frames = []
        self._cache = {}        # tile path -> built overlay
        self._stop = threading.Event()
        self._thread = None
        self.online = None      # None = acquiring, then True/False
        self.last_update = 0.0

    # -- lifecycle -----------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    # -- data ------------------------------------------------------------
    def snapshot(self):
        with self._lock:
            return list(self._frames), self.online

    def _loop(self):
        while not self._stop.is_set():
            try:
                frames = self._poll_once()
            except Exception:
                logger.warning("rain_radar: poll crashed", exc_info=True)
                frames = None
            with self._lock:
                if frames is None:
                    self.online = False
                else:
                    self._frames = frames
                    self.online = True
                    self.last_update = time.time()
            # Interruptible wait so stopping the demo never hangs a poll.
            self._stop.wait(self.poll_seconds)

    # -- network -----------------------------------------------------------
    def _fetch_index(self):
        """(host, entries) from the frame index, or None on failure."""
        try:
            resp = requests.get(INDEX_URL, timeout=10,
                                headers={"User-Agent": USER_AGENT})
            if resp.status_code != 200:
                logger.warning("rain_radar: index HTTP %s", resp.status_code)
                return None
            data = resp.json() or {}
            host = data["host"]
            radar = data.get("radar") or {}
            past = list(radar.get("past") or [])[-PAST_FRAMES:]
            nowcast = list(radar.get("nowcast") or [])[:NOWCAST_FRAMES]
        except Exception as e:
            # Broad on purpose: the feed thread must survive anything the
            # network or a hostile payload can throw at it.
            logger.warning("rain_radar: index fetch failed: %s", e)
            return None
        entries = ([{"time": f["time"], "path": f["path"], "nowcast": False}
                    for f in past if "path" in f and "time" in f] +
                   [{"time": f["time"], "path": f["path"], "nowcast": True}
                    for f in nowcast if "path" in f and "time" in f])
        return (host, entries) if entries else None

    def _fetch_tile(self, host, path, tx, ty):
        url = "%s%s/%d/%d/%d/%d/0/0_0.png" % (
            host, path, TILE_SIZE, self.zoom, tx, ty)
        try:
            resp = requests.get(url, timeout=10,
                                headers={"User-Agent": USER_AGENT})
            if resp.status_code != 200:
                return None
            return Image.open(io.BytesIO(resp.content)).convert("RGBA")
        except Exception as e:
            logger.warning("rain_radar: tile %s failed: %s", url, e)
            return None

    def _build_overlay(self, host, path):
        """One radar frame -> 64x64 RGBA overlay, or None on any failure."""
        x0, y0, x1, y1 = _box_px(self.lat, self.lon, self.radius_miles,
                                 self.zoom)
        tx0, ty0 = int(x0 // TILE_SIZE), int(y0 // TILE_SIZE)
        tx1, ty1 = int(x1 // TILE_SIZE), int(y1 // TILE_SIZE)
        w = (tx1 - tx0 + 1) * TILE_SIZE
        h = (ty1 - ty0 + 1) * TILE_SIZE
        rgb = Image.new("RGB", (w, h), (0, 0, 0))
        alpha = Image.new("L", (w, h), 0)
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                tile = self._fetch_tile(host, path, tx, ty)
                if tile is None:
                    return None
                ox = (tx - tx0) * TILE_SIZE
                oy = (ty - ty0) * TILE_SIZE
                bands = tile.split()
                rgb.paste(Image.merge("RGB", bands[:3]), (ox, oy))
                alpha.paste(bands[3], (ox, oy))
        box = (x0 - tx0 * TILE_SIZE, y0 - ty0 * TILE_SIZE,
               x1 - tx0 * TILE_SIZE, y1 - ty0 * TILE_SIZE)
        echo, a = _resample_echo(rgb, alpha, box, (WIDTH, HEIGHT))
        return _colorize(echo, a)

    def _poll_once(self):
        """Full poll: index + any overlays not already cached."""
        index = self._fetch_index()
        if index is None:
            return None
        host, entries = index
        frames = []
        for e in entries:
            overlay = self._cache.get(e["path"])
            if overlay is None:
                overlay = self._build_overlay(host, e["path"])
                if overlay is None:
                    continue
                self._cache[e["path"]] = overlay
            frames.append({"time": e["time"], "nowcast": e["nowcast"],
                           "overlay": overlay})
        # Drop overlays for frames RainViewer no longer serves.
        keep = {e["path"] for e in entries}
        self._cache = {k: v for k, v in self._cache.items() if k in keep}
        return frames or None


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _build_basemap(lat, lon, radius_miles):
    """The static street map underlay, or faint range rings without one."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    px_per_mile = (WIDTH / 2.0) / radius_miles

    map_data = _load_map(lat, lon, radius_miles)
    if map_data:
        for ways, color in ((map_data.get("water") or [], MAP_WATER),
                            (map_data.get("roads") or [], MAP_ROAD)):
            for way in ways:
                pts = []
                for pt in way:
                    try:
                        east, north = _project(float(pt[0]), float(pt[1]),
                                               lat, lon)
                    except (TypeError, ValueError, IndexError):
                        pts = []
                        break
                    pts.append((CX + east * px_per_mile,
                                CY - north * px_per_mile))
                if len(pts) > 1:
                    draw.line(pts, fill=color)
    else:
        for frac in (1 / 3, 2 / 3, 1.0):
            r = (WIDTH / 2.0 - 1) * frac
            draw.ellipse([CX - r, CY - r, CX + r, CY + r], outline=RING)

    # Home marker: the configured centre (Whole Foods on Lamar).
    draw.line([(CX - 2, CY), (CX + 2, CY)], fill=CENTRE_MARK)
    draw.line([(CX, CY - 2), (CX, CY + 2)], fill=CENTRE_MARK)
    return img


def _age_label(frame_time, now):
    """Relative age of a radar frame: -40M, NOW, +20M."""
    minutes = int(round((frame_time - now) / 60.0))
    if abs(minutes) < 5:
        return "NOW"
    return "%+dM" % minutes


class _Cycler:
    """Steps through the frame list, holding on the newest observed one."""

    def __init__(self):
        self.index = 0
        self._t = 0.0

    def advance(self, dt, count, hold_index):
        if count <= 0:
            self.index = 0
            self._t = 0.0
            return 0
        self.index %= count
        self._t += dt
        dwell = HOLD_DWELL if self.index == hold_index else FRAME_DWELL
        if self._t >= dwell:
            self._t = 0.0
            self.index = (self.index + 1) % count
        return self.index


def _draw_hud(frame, frames, index, online, radius_miles, blink):
    draw = ImageDraw.Draw(frame)
    draw.rectangle([0, HEIGHT - HUD_HEIGHT, WIDTH - 1, HEIGHT - 1],
                   fill=HUD_BG)
    draw.line([(0, HEIGHT - HUD_HEIGHT), (WIDTH - 1, HEIGHT - HUD_HEIGHT)],
              fill=(40, 46, 52))
    y = HEIGHT - HUD_HEIGHT + 2

    if online is None:
        _draw_text(draw, "ACQUIRING", 2, y, HUD_DIM)
        return
    if online is False:
        _draw_text(draw, "NO LINK", 2, y, ALERT if blink else HUD_DIM)
        return
    if not frames:
        _draw_text(draw, "NO ECHO", 2, y, HUD_DIM)
        return

    current = frames[index % len(frames)]
    label = _age_label(current["time"], time.time())
    color = TICK_FORECAST if current["nowcast"] else HUD_TEXT
    _draw_text(draw, label, 1, y, color)
    rng = "%dMI" % int(radius_miles)
    _draw_text(draw, rng, WIDTH - _text_width(rng) - 1, y, HUD_DIM)

    # Timeline ticks along the top edge of the bar.
    ty = HEIGHT - HUD_HEIGHT + 1
    for i, f in enumerate(frames[:15]):
        x = 24 + i * 2
        if i == index:
            draw.point((x, ty), fill=TICK_NOW)
        else:
            draw.point((x, ty),
                       fill=TICK_FORECAST if f["nowcast"] else TICK_PAST)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def run(matrix, duration=60):
    """Run the precipitation radar demo."""
    cfg = _radar_config()
    basemap = _build_basemap(cfg["lat"], cfg["lon"], cfg["radius_miles"])
    feed = RainFeed(cfg["lat"], cfg["lon"], cfg["radius_miles"])
    feed.start()

    cycler = _Cycler()
    start = time.time()
    last = start

    try:
        while time.time() - start < duration:
            if should_stop():
                break
            frame_start = time.time()
            dt = min(0.2, max(0.001, frame_start - last))
            last = frame_start

            frames, online = feed.snapshot()
            hold = -1
            for i, f in enumerate(frames):
                if not f["nowcast"]:
                    hold = i
            index = cycler.advance(dt, len(frames), hold)

            frame = basemap.copy()
            if frames:
                overlay = frames[index]["overlay"]
                frame.paste(overlay, (0, 0), overlay)

            blink = int(frame_start * 2) % 2 == 0
            _draw_hud(frame, frames, index, online, cfg["radius_miles"],
                      blink)

            matrix.SetImage(frame)

            sleep_time = FRAME_INTERVAL - (time.time() - frame_start)
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception:
        logger.error("Error in rain_radar demo", exc_info=True)
    finally:
        feed.stop()
        try:
            matrix.Clear()
        except Exception:
            pass
