#!/usr/bin/env python3
"""Live flight radar: a PPI scope showing real aircraft overhead.

A plan-position-indicator radar scope fills the panel, centred on the
configured location with a real map underlay (major highways and the river,
pre-fetched from OpenStreetMap into ``config/flight_radar_map.json``) so the
traffic has geography under it. A cosmetic beam sweeps the scope; aircraft
are drawn live every frame -- coloured by altitude, sized by weight class,
tagged with a short heading vector -- so they read as crisp moving symbols.
An early version only painted contacts as the beam passed them, decaying like
real phosphor; authentic, but a moving plane smeared into an unreadable blob
trail at 64px. A HUD bar cycles the contacts with callsign and flight level.

The panel is 64x64 and the default range is 30 miles, which makes the scale a
convenient 1 pixel per mile.

Data comes from a free community ADS-B aggregator (adsb.lol, with
airplanes.live as a fallback). No API key is needed. Both expose a
point-and-radius endpoint that is exactly the shape of a radar query:

    https://api.adsb.lol/v2/point/<lat>/<lon>/<radius_nm>

Polling happens on a background thread so the render loop never blocks on the
network (``src/main.py`` has a frame-hang watchdog that would otherwise trip).
Between polls the contacts are dead-reckoned along their last known track and
ground speed, so blips drift smoothly instead of teleporting every poll.
"""

import os
import json
import math
import time
import logging
import threading

import requests
from PIL import Image, ImageDraw, ImageChops

from src.display._shared import should_stop
from src.display._fonts import _draw_text, _text_width

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 30

# Scope geometry. The centre sits between pixels so the scope is symmetric.
CX, CY = 31.5, 31.5
SCOPE_R = 30.0

# Defaults, overridable in config/flight_radar.json.
DEFAULT_RADIUS_MILES = 30.0
DEFAULT_POLL_SECONDS = 12.0
SWEEP_PERIOD = 4.0          # seconds per revolution

# The beam trail has to fade in well under a second or it becomes a bright
# wedge covering a quarter of the scope.
BEAM_DECAY = 0.80           # ~27 degrees of visible trail at 30fps
BEAM_FILL = 0.30            # trail brightness relative to the leading edge
BEAM_STEP_DEG = 1.0         # sub-step the trail so it has no comb gaps

# The map underlay must sit below everything: brighter than the scope
# background, dimmer than the range rings, far dimmer than any aircraft.
MAP_ROAD = (36, 58, 44)
MAP_WATER = (22, 48, 78)
CENTRE_MARK = (255, 255, 255)   # "you are here" -- brightest thing but a dot
MAP_MAX_CENTRE_DRIFT_MILES = 3.0
HUD_HEIGHT = 9
HUD_DWELL = 2.5             # seconds per contact in the HUD
STALE_SECONDS = 60.0        # drop contacts whose position is older than this

# Statute miles per degree of latitude (WGS84 mean). Good to well under a
# pixel over a 30 mile scope.
MILES_PER_DEG_LAT = 69.055
NM_PER_MILE = 0.868976

# Colours.
SCOPE_BG = (0, 8, 6)
RING = (0, 52, 34)
RING_MAJOR = (0, 78, 50)
TICK = (0, 96, 60)
BEAM = (40, 255, 120)
HUD_BG = (0, 14, 20)
HUD_TEXT = (120, 220, 255)
HUD_DIM = (40, 90, 110)
ALERT = (255, 40, 40)

# Altitude bands: (ceiling_ft, colour). Low and fast reads hot, high reads cold.
ALT_BANDS = [
    (0, (105, 105, 115)),        # on the ground
    (3000, (255, 96, 64)),       # departure / final approach
    (10000, (255, 200, 72)),     # climb-out and pattern work
    (20000, (140, 255, 130)),    # mid level
    (30000, (96, 224, 255)),     # high
    (float("inf"), (170, 180, 255)),  # cruise
]

# ADS-B emitter categories -> blip size in pixels.
BLIP_SIZE = {
    "A1": 1,   # light
    "A2": 1,   # small
    "A3": 2,   # large (737 / A320 class)
    "A4": 2,   # high vortex large
    "A5": 3,   # heavy
    "A6": 2,   # high performance
    "A7": 1,   # rotorcraft
}
DEFAULT_BLIP_SIZE = 1

EMERGENCY_SQUAWKS = {"7500", "7600", "7700"}

API_ENDPOINTS = [
    "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}",
    "https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}",
]
USER_AGENT = "LED-Matrix-Project/flight_radar"


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

def _load_config():
    """Radar settings, falling back to the weather module's location.

    Most installs already have a lat/lon in ``config/weather.json``, so the
    radar works with no extra configuration at all.
    """
    cfg = {}
    path = os.path.join(PROJECT_ROOT, "config", "flight_radar.json")
    try:
        with open(path, "r") as f:
            cfg = json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    lat, lon = cfg.get("lat"), cfg.get("lon")
    if lat is None or lon is None:
        wpath = os.path.join(PROJECT_ROOT, "config", "weather.json")
        try:
            with open(wpath, "r") as f:
                wcfg = json.load(f) or {}
            lat = wcfg.get("lat", 30.27) if lat is None else lat
            lon = wcfg.get("lon", -97.74) if lon is None else lon
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            lat = 30.27 if lat is None else lat
            lon = -97.74 if lon is None else lon

    try:
        radius = float(cfg.get("radius_miles", DEFAULT_RADIUS_MILES))
    except (TypeError, ValueError):
        radius = DEFAULT_RADIUS_MILES
    radius = max(5.0, min(150.0, radius))

    try:
        poll = float(cfg.get("poll_seconds", DEFAULT_POLL_SECONDS))
    except (TypeError, ValueError):
        poll = DEFAULT_POLL_SECONDS
    poll = max(5.0, min(300.0, poll))

    return {
        "lat": float(lat),
        "lon": float(lon),
        "radius_miles": radius,
        "poll_seconds": poll,
        "show_ground": bool(cfg.get("show_ground", True)),
    }


def _load_map(lat, lon, radius_miles):
    """Load the pre-fetched map underlay, or None if it does not apply.

    The geometry is fetched once at development time (OSM Overpass) and
    committed, so the device never needs the map API. If the configured
    centre has moved away from the cached one, the stale map is worse than
    no map -- roads would be drawn in the wrong place under real aircraft --
    so it is rejected and the scope falls back to plain rings.
    """
    path = os.path.join(PROJECT_ROOT, "config", "flight_radar_map.json")
    try:
        with open(path, "r") as f:
            data = json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    try:
        mlat = float(data["lat"])
        mlon = float(data["lon"])
        roads = data.get("roads") or []
        water = data.get("water") or []
    except (KeyError, TypeError, ValueError):
        logger.warning("flight_radar: malformed map cache ignored")
        return None
    east, north = _project(mlat, mlon, lat, lon)
    drift = math.hypot(east, north)
    if drift > MAP_MAX_CENTRE_DRIFT_MILES:
        logger.warning(
            "flight_radar: map cache centred %.1f mi away from the configured "
            "location; ignoring it (regenerate flight_radar_map.json)", drift)
        return None
    return {"roads": roads, "water": water}


# --------------------------------------------------------------------------
# geometry and styling helpers
# --------------------------------------------------------------------------

def _project(lat, lon, lat0, lon0):
    """Local flat-earth projection to (east, north) offsets in statute miles."""
    north = (lat - lat0) * MILES_PER_DEG_LAT
    east = (lon - lon0) * MILES_PER_DEG_LAT * math.cos(math.radians(lat0))
    return east, north


def _bearing_of(east, north):
    """Compass bearing (0 = north, clockwise) of an east/north offset."""
    return math.degrees(math.atan2(east, north)) % 360.0


def _alt_color(alt_ft):
    for ceiling, color in ALT_BANDS:
        if alt_ft <= ceiling:
            return color
    return ALT_BANDS[-1][1]


def _parse_altitude(raw):
    """ADS-B altitude is feet, or the string 'ground'. Returns (ft, on_ground)."""
    if raw is None:
        return None, False
    if isinstance(raw, str):
        if raw.strip().lower() == "ground":
            return 0, True
        try:
            return int(float(raw)), False
        except ValueError:
            return None, False
    try:
        return int(raw), False
    except (TypeError, ValueError):
        return None, False


def _blip_size(category):
    return BLIP_SIZE.get(category, DEFAULT_BLIP_SIZE)


def _decay_table(factor):
    """768-entry point() table so the decay runs at C speed on all 3 bands."""
    band = [int(v * factor) for v in range(256)]
    return band * 3


# --------------------------------------------------------------------------
# aircraft feed
# --------------------------------------------------------------------------

class Contact:
    """One aircraft, in scope-relative coordinates."""

    __slots__ = ("hex", "callsign", "kind", "east", "north", "alt", "on_ground",
                 "speed", "track", "climb", "squawk", "category", "age")

    def __init__(self, hex_id, callsign, kind, east, north, alt, on_ground,
                 speed, track, climb, squawk, category, age):
        self.hex = hex_id
        self.callsign = callsign
        self.kind = kind
        self.east = east
        self.north = north
        self.alt = alt
        self.on_ground = on_ground
        self.speed = speed
        self.track = track
        self.climb = climb
        self.squawk = squawk
        self.category = category
        self.age = age

    @property
    def distance(self):
        return math.hypot(self.east, self.north)

    @property
    def bearing(self):
        return _bearing_of(self.east, self.north)

    @property
    def emergency(self):
        return self.squawk in EMERGENCY_SQUAWKS

    def advance(self, dt):
        """Dead-reckon along the last known track. Keeps blips moving smoothly."""
        if self.on_ground or self.track is None or not self.speed:
            return
        # Ground speed is knots; the scope is in statute miles.
        miles = self.speed / NM_PER_MILE / 3600.0 * dt
        rad = math.radians(self.track)
        self.east += miles * math.sin(rad)
        self.north += miles * math.cos(rad)


def _parse_contacts(payload, lat0, lon0):
    """Turn an aggregator response into Contact objects, skipping bad records."""
    contacts = []
    for ac in (payload.get("ac") or []):
        try:
            lat = ac.get("lat")
            lon = ac.get("lon")
            if lat is None or lon is None:
                continue
            age = ac.get("seen_pos")
            age = float(age) if age is not None else 0.0
            if age > STALE_SECONDS:
                continue

            east, north = _project(float(lat), float(lon), lat0, lon0)
            alt, on_ground = _parse_altitude(ac.get("alt_baro"))
            if alt is None:
                alt, on_ground = _parse_altitude(ac.get("alt_geom"))
            if alt is None:
                alt, on_ground = 0, False

            track = ac.get("track")
            if track is None:
                track = ac.get("dir")
            track = float(track) % 360.0 if track is not None else None

            speed = ac.get("gs")
            speed = float(speed) if speed is not None else 0.0

            climb = ac.get("baro_rate")
            climb = float(climb) if climb is not None else 0.0

            callsign = (ac.get("flight") or ac.get("r") or ac.get("hex") or "")
            squawk = ac.get("squawk") or ""

            contacts.append(Contact(
                hex_id=ac.get("hex") or "",
                callsign=str(callsign).strip().upper()[:8],
                kind=str(ac.get("t") or "").strip().upper()[:4],
                east=east, north=north,
                alt=alt, on_ground=on_ground,
                speed=speed, track=track, climb=climb,
                squawk=str(squawk).strip(),
                category=str(ac.get("category") or ""),
                age=age,
            ))
        except (TypeError, ValueError):
            continue
    contacts.sort(key=lambda c: c.distance)
    return contacts


class AircraftFeed:
    """Polls an ADS-B aggregator on a background thread.

    ``run()`` must never block on the network, so every network touch lives
    here and the render loop only ever reads the latest snapshot.
    """

    def __init__(self, lat, lon, radius_miles, poll_seconds):
        self.lat = lat
        self.lon = lon
        self.radius_miles = radius_miles
        self.poll_seconds = poll_seconds
        self._lock = threading.Lock()
        self._contacts = []
        self._stop = threading.Event()
        self._thread = None
        self.online = None      # None = still acquiring, then True/False
        self.last_update = 0.0

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    # -- data --------------------------------------------------------------
    def snapshot(self):
        with self._lock:
            return list(self._contacts), self.online

    def advance(self, dt):
        with self._lock:
            for c in self._contacts:
                c.advance(dt)

    def _loop(self):
        while not self._stop.is_set():
            contacts = self._poll_once()
            with self._lock:
                if contacts is None:
                    self.online = False
                else:
                    self._contacts = contacts
                    self.online = True
                    self.last_update = time.time()
            # Interruptible wait so stopping the demo does not hang for a poll.
            self._stop.wait(self.poll_seconds)

    def _poll_once(self):
        """Try each endpoint in turn. Returns None if all of them failed."""
        radius_nm = max(1, int(round(self.radius_miles * NM_PER_MILE)))
        for template in API_ENDPOINTS:
            url = template.format(lat=round(self.lat, 5),
                                  lon=round(self.lon, 5),
                                  radius=radius_nm)
            try:
                resp = requests.get(
                    url, timeout=8, headers={"User-Agent": USER_AGENT})
                if resp.status_code != 200:
                    logger.warning("flight_radar: %s returned HTTP %s",
                                   url, resp.status_code)
                    continue
                return _parse_contacts(resp.json(), self.lat, self.lon)
            except (requests.RequestException, ValueError) as e:
                logger.warning("flight_radar: %s failed: %s", url, e)
                continue
        return None


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _draw_map_layer(img, mask, map_data, lat0, lon0, px_per_mile):
    """Draw the road/river polylines, clipped to the scope disc.

    The polylines are drawn on their own layer and pasted through the disc
    mask, because a highway that leaves the 30 mile range would otherwise be
    drawn across the corner HUD text.
    """
    layer = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for ways, color in ((map_data.get("water") or [], MAP_WATER),
                        (map_data.get("roads") or [], MAP_ROAD)):
        for way in ways:
            pts = []
            for pt in way:
                try:
                    east, north = _project(float(pt[0]), float(pt[1]),
                                           lat0, lon0)
                except (TypeError, ValueError, IndexError):
                    pts = []
                    break
                pts.append((CX + east * px_per_mile,
                            CY - north * px_per_mile))
            if len(pts) > 1:
                draw.line(pts, fill=color)
    img.paste(layer, (0, 0), Image.composite(
        mask, Image.new("L", (WIDTH, HEIGHT), 0),
        layer.convert("L").point(lambda v: 255 if v else 0)))


def _build_scope(radius_miles, map_data=None, lat0=None, lon0=None):
    """Static scope furniture: map underlay, range rings, cardinal ticks."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.ellipse([CX - SCOPE_R, CY - SCOPE_R, CX + SCOPE_R, CY + SCOPE_R],
                 fill=SCOPE_BG, outline=RING_MAJOR)

    # Geography first, so the rings and ticks stay legible on top of it.
    if map_data and lat0 is not None and lon0 is not None:
        _draw_map_layer(img, _scope_mask(), map_data, lat0, lon0,
                        SCOPE_R / radius_miles)
        draw = ImageDraw.Draw(img)
        draw.ellipse([CX - SCOPE_R, CY - SCOPE_R, CX + SCOPE_R, CY + SCOPE_R],
                     outline=RING_MAJOR)

    # Range rings every third of the range.
    for frac in (1 / 3, 2 / 3):
        r = SCOPE_R * frac
        draw.ellipse([CX - r, CY - r, CX + r, CY + r], outline=RING)

    # Cardinal ticks, longer for north.
    for bearing in range(0, 360, 30):
        rad = math.radians(bearing - 90)
        inner = SCOPE_R - (6 if bearing % 90 == 0 else 3)
        color = TICK if bearing % 90 == 0 else RING
        draw.line([(CX + inner * math.cos(rad), CY + inner * math.sin(rad)),
                   (CX + SCOPE_R * math.cos(rad), CY + SCOPE_R * math.sin(rad))],
                  fill=color)

    return img


def _scope_mask():
    """L mask of the scope disc, used to clip the phosphor to the circle."""
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(mask).ellipse(
        [CX - SCOPE_R, CY - SCOPE_R, CX + SCOPE_R, CY + SCOPE_R], fill=255)
    return mask


class Scope:
    """Holds the static layers plus the decaying phosphor layer."""

    def __init__(self, radius_miles, map_data=None, lat0=None, lon0=None):
        self.radius_miles = radius_miles
        self.px_per_mile = SCOPE_R / radius_miles
        self.background = _build_scope(radius_miles, map_data, lat0, lon0)
        self.mask = _scope_mask()
        self.beam_layer = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        self._beam_decay = _decay_table(BEAM_DECAY)
        self.sweep = 0.0

    # -- placement ---------------------------------------------------------
    def to_screen(self, contact):
        return (CX + contact.east * self.px_per_mile,
                CY - contact.north * self.px_per_mile)

    def in_range(self, contact):
        return contact.distance <= self.radius_miles

    # -- per-frame ---------------------------------------------------------
    def decay(self):
        self.beam_layer = self.beam_layer.point(self._beam_decay)

    def advance_sweep(self, dt):
        """Move the beam, returning the (start, end) bearings it just covered."""
        previous = self.sweep
        self.sweep = (self.sweep + 360.0 * dt / SWEEP_PERIOD) % 360.0
        return previous, self.sweep

    def _beam_ray(self, draw, bearing, color):
        rad = math.radians(bearing - 90)
        draw.line([(CX, CY),
                   (CX + SCOPE_R * math.cos(rad), CY + SCOPE_R * math.sin(rad))],
                  fill=color)

    def draw_beam(self, sweep_start=None):
        """Lay down the trail: uniform rays across the angle just traversed.

        Two rules matter here. Sub-stepping is needed because one frame of
        rotation is more than a pixel wide at the rim, which would leave gaps.
        And every ray must be the *same* brightness -- an earlier version
        stamped a bright leading edge into this layer each frame, and once
        those decayed alongside the dimmer fill the trail turned into a comb of
        alternating bright and dim lines. The bright leading edge is drawn at
        compose time instead, so it never accumulates.
        """
        draw = ImageDraw.Draw(self.beam_layer)
        fill = tuple(int(c * BEAM_FILL) for c in BEAM)
        span = 0.0
        if sweep_start is not None:
            span = (self.sweep - sweep_start) % 360.0
        steps = max(1, int(span / BEAM_STEP_DEG))
        for i in range(steps):
            self._beam_ray(draw, self.sweep - i * BEAM_STEP_DEG, fill)

    def paint(self, frame, contact):
        """Draw one contact live onto the composed frame.

        Contacts used to be stamped into a slow-decay phosphor layer as the
        beam passed. Authentic, but a moving aircraft turned into a smeared
        blob of stale positions -- at 64px legibility beats authenticity, so
        every contact is redrawn crisp at its current position every frame.
        """
        x, y = self.to_screen(contact)
        color = ALERT if contact.emergency else _alt_color(contact.alt)
        size = _blip_size(contact.category)
        draw = ImageDraw.Draw(frame)

        # Heading vector first: it is drawn from the blip position outward, so
        # painting it second would overwrite the aircraft itself with the
        # dimmed leader colour. The contact must stay the brightest pixel.
        if contact.track is not None and not contact.on_ground:
            rad = math.radians(contact.track - 90)
            length = 3.0 if contact.speed > 250 else 2.0
            draw.line([(x, y),
                       (x + length * math.cos(rad), y + length * math.sin(rad))],
                      fill=tuple(int(c * 0.55) for c in color))

        if size <= 1:
            draw.point((x, y), fill=color)
        else:
            r = (size - 1) / 2.0
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

    def compose(self):
        glow = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        glow.paste(self.beam_layer, (0, 0), self.mask)
        frame = ImageChops.add(self.background, glow)

        draw = ImageDraw.Draw(frame)
        # Leading edge, drawn live rather than accumulated (see draw_beam).
        self._beam_ray(draw, self.sweep, BEAM)

        # Centre marker: the station itself (Whole Foods on Lamar, per
        # config). Drawn after the beam so it never gets washed out --
        # knowing where the centre is turns the display from dots on a
        # circle into "that plane is over MY head".
        draw.line([(CX - 2, CY), (CX + 2, CY)], fill=CENTRE_MARK)
        draw.line([(CX, CY - 2), (CX, CY + 2)], fill=CENTRE_MARK)
        return frame


def _format_altitude(contact):
    if contact.on_ground:
        return "GND"
    hundreds = int(round(contact.alt / 100.0))
    return "%03d" % max(0, min(999, hundreds))


def _hud_candidates(contacts):
    """Contacts worth naming in the HUD, nearest first.

    Airliners parked at a nearby airport are perfectly valid contacts and
    should still be painted on the scope, but cycling a dozen stationary
    aircraft in the readout is dull and hides the traffic actually overhead.
    Ground contacts are therefore only offered if nothing is flying.
    """
    airborne = [c for c in contacts if not c.on_ground]
    return airborne if airborne else list(contacts)


def _draw_hud(frame, contacts, online, hud_index, radius_miles, blink):
    """Bottom status bar plus the corner readouts. Returns the named contact."""
    draw = ImageDraw.Draw(frame)
    draw.rectangle([0, HEIGHT - HUD_HEIGHT, WIDTH - 1, HEIGHT - 1], fill=HUD_BG)
    draw.line([(0, HEIGHT - HUD_HEIGHT), (WIDTH - 1, HEIGHT - HUD_HEIGHT)],
              fill=HUD_DIM)
    y = HEIGHT - HUD_HEIGHT + 1

    named = None
    candidates = _hud_candidates(contacts)
    if online is None:
        _draw_text(draw, "ACQUIRING", 2, y, HUD_DIM)
    elif online is False:
        color = ALERT if blink else HUD_DIM
        _draw_text(draw, "NO LINK", 2, y, color)
    elif not candidates:
        _draw_text(draw, "NO CONTACTS", 1, y, HUD_DIM)
    else:
        named = candidates[hud_index % len(candidates)]
        label = named.callsign or named.hex.upper() or "UNKNOWN"
        alt = _format_altitude(named)
        color = ALERT if (named.emergency and blink) else HUD_TEXT
        _draw_text(draw, label[:7], 1, y, color)
        _draw_text(draw, alt, WIDTH - _text_width(alt) - 1, y, HUD_DIM)

    # Corners sit outside the scope disc, so they are free real estate.
    if online:
        _draw_text(draw, "%d" % min(99, len(contacts)), 0, 0, HUD_DIM)
    rng = "%d" % int(radius_miles)
    _draw_text(draw, rng, WIDTH - _text_width(rng), 0, HUD_DIM)
    return named


def _draw_marker(frame, scope, contact):
    """Ring the contact the HUD is currently naming, so the two are linked."""
    x, y = scope.to_screen(contact)
    r = 3.0
    color = ALERT if contact.emergency else HUD_TEXT
    draw = ImageDraw.Draw(frame)
    draw.arc([x - r, y - r, x + r, y + r], 0, 360, fill=color)
    # The tracked target is drawn live rather than left to the decaying blip
    # layer, so the reticle is never sitting around an empty patch of scope.
    draw.point((x, y), fill=_alt_color(contact.alt))


def _draw_alert_ring(frame):
    ImageDraw.Draw(frame).ellipse(
        [CX - SCOPE_R, CY - SCOPE_R, CX + SCOPE_R, CY + SCOPE_R], outline=ALERT)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def run(matrix, duration=60):
    """Run the flight radar demo."""
    cfg = _load_config()
    scope = Scope(cfg["radius_miles"],
                  map_data=_load_map(cfg["lat"], cfg["lon"],
                                     cfg["radius_miles"]),
                  lat0=cfg["lat"], lon0=cfg["lon"])
    feed = AircraftFeed(cfg["lat"], cfg["lon"],
                        cfg["radius_miles"], cfg["poll_seconds"])
    feed.start()

    show_ground = cfg["show_ground"]
    start = time.time()
    last = start
    hud_timer = 0.0
    hud_index = 0

    try:
        while time.time() - start < duration:
            if should_stop():
                break
            frame_start = time.time()
            dt = min(0.2, max(0.001, frame_start - last))
            last = frame_start

            feed.advance(dt)
            contacts, online = feed.snapshot()
            visible = [c for c in contacts if scope.in_range(c)
                       and (show_ground or not c.on_ground)]

            scope.decay()
            sweep_start, _sweep_end = scope.advance_sweep(dt)
            scope.draw_beam(sweep_start)

            frame = scope.compose()
            for c in visible:
                scope.paint(frame, c)

            blink = int(frame_start * 2) % 2 == 0
            if any(c.emergency for c in visible) and blink:
                _draw_alert_ring(frame)

            hud_timer += dt
            if hud_timer >= HUD_DWELL:
                hud_timer = 0.0
                hud_index += 1
            named = _draw_hud(frame, visible, online, hud_index,
                              cfg["radius_miles"], blink)
            if named is not None:
                _draw_marker(frame, scope, named)

            matrix.SetImage(frame)

            sleep_time = FRAME_INTERVAL - (time.time() - frame_start)
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception:
        logger.error("Error in flight_radar demo", exc_info=True)
    finally:
        feed.stop()
        try:
            matrix.Clear()
        except Exception:
            pass
