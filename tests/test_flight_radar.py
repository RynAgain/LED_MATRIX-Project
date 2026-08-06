"""Tests for the live flight radar scope.

The module talks to a network API, so the interesting failure modes are all
about bad or missing data rather than about geometry:

* ADS-B feeds return ``alt_baro: "ground"`` as a *string*, and ``track``,
  ``r``, ``t`` and ``squawk`` are frequently ``null``. Any of those naively
  coerced to a number crashes the render loop.
* positions can be a minute stale, in which case the contact should be dropped
  rather than drawn in the wrong place
* the network must never be touched from the render loop, because
  ``src/main.py`` has a frame-hang watchdog that would trip on a slow request

The rendering half is pinned on the two things that were actually wrong during
development: the beam trail must be uniform in brightness (accumulating a
bright leading edge turned it into a comb) and contacts must outlive the trail
by a wide margin.
"""

import json
import math
import time

import pytest

from src.display import flight_radar as fr
from src.display.flight_radar import (
    AircraftFeed,
    Contact,
    Scope,
    _alt_color,
    _bearing_of,
    _blip_size,
    _format_altitude,
    _hud_candidates,
    _parse_altitude,
    _parse_contacts,
    _project,
    _sweep_covers,
)


class _Recorder:
    def __init__(self):
        self.frames = 0
        self.last = None
        self.cleared = 0

    def SetImage(self, image, *args, **kwargs):
        self.frames += 1
        self.last = image.copy()

    def Clear(self):
        self.cleared += 1


@pytest.fixture(autouse=True)
def _clear_stop():
    from src.display import _shared
    _shared.clear_stop()
    yield
    _shared.clear_stop()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Nothing in this file may make a real HTTP request."""
    def boom(*a, **k):
        raise AssertionError("test made a real network call")
    monkeypatch.setattr(fr.requests, "get", boom)


def _contact(east=0.0, north=10.0, alt=10000, on_ground=False, speed=400.0,
             track=90.0, squawk="1200", category="A3", callsign="TEST123"):
    return Contact(hex_id="abc123", callsign=callsign, kind="B738",
                   east=east, north=north, alt=alt, on_ground=on_ground,
                   speed=speed, track=track, climb=0.0, squawk=squawk,
                   category=category, age=0.0)


# --- projection and bearings ------------------------------------------------

def test_projection_is_centred_on_the_station():
    east, north = _project(30.27, -97.74, 30.27, -97.74)
    assert east == pytest.approx(0.0)
    assert north == pytest.approx(0.0)


def test_projection_north_is_positive_and_scaled_in_miles():
    _, north = _project(30.27 + 1.0, -97.74, 30.27, -97.74)
    assert north == pytest.approx(fr.MILES_PER_DEG_LAT, rel=1e-6)


def test_projection_compresses_longitude_by_latitude():
    east, _ = _project(30.27, -97.74 + 1.0, 30.27, -97.74)
    expected = fr.MILES_PER_DEG_LAT * math.cos(math.radians(30.27))
    assert east == pytest.approx(expected, rel=1e-6)
    assert east < fr.MILES_PER_DEG_LAT      # a degree of lon is shorter here


@pytest.mark.parametrize("east,north,bearing", [
    (0, 10, 0),      # due north
    (10, 0, 90),     # due east
    (0, -10, 180),   # due south
    (-10, 0, 270),   # due west
])
def test_bearing_uses_compass_convention(east, north, bearing):
    assert _bearing_of(east, north) == pytest.approx(bearing)


# --- feed parsing ----------------------------------------------------------

def test_parse_altitude_handles_the_ground_string():
    assert _parse_altitude("ground") == (0, True)
    assert _parse_altitude("GROUND") == (0, True)
    assert _parse_altitude(36000) == (36000, False)
    assert _parse_altitude("2475") == (2475, False)
    assert _parse_altitude(None) == (None, False)
    assert _parse_altitude("banana") == (None, False)


def test_parse_contacts_survives_null_fields():
    """Every optional field null at once -- the shape a real feed sends."""
    payload = {"ac": [{
        "hex": "a1b2c3", "lat": 30.30, "lon": -97.75,
        "alt_baro": "ground", "track": None, "gs": None,
        "baro_rate": None, "squawk": None, "r": None, "t": None,
        "flight": None, "category": None, "seen_pos": 1.0,
    }]}
    contacts = _parse_contacts(payload, 30.27, -97.74)
    assert len(contacts) == 1
    c = contacts[0]
    assert c.on_ground is True
    assert c.alt == 0
    assert c.track is None
    assert c.speed == 0.0
    assert c.callsign == "A1B2C3"     # falls back to the hex id
    assert c.emergency is False


def test_parse_contacts_skips_records_without_a_position():
    payload = {"ac": [
        {"hex": "a", "lat": None, "lon": -97.0},
        {"hex": "b", "lon": -97.0},
        {"hex": "c", "lat": 30.3, "lon": -97.75, "alt_baro": 3000},
    ]}
    assert [c.hex for c in _parse_contacts(payload, 30.27, -97.74)] == ["c"]


def test_parse_contacts_drops_stale_positions():
    payload = {"ac": [
        {"hex": "fresh", "lat": 30.3, "lon": -97.75, "alt_baro": 3000,
         "seen_pos": 2.0},
        {"hex": "stale", "lat": 30.3, "lon": -97.75, "alt_baro": 3000,
         "seen_pos": fr.STALE_SECONDS + 1},
    ]}
    assert [c.hex for c in _parse_contacts(payload, 30.27, -97.74)] == ["fresh"]


def test_parse_contacts_handles_an_empty_or_missing_list():
    assert _parse_contacts({}, 30.27, -97.74) == []
    assert _parse_contacts({"ac": None}, 30.27, -97.74) == []
    assert _parse_contacts({"ac": []}, 30.27, -97.74) == []


def test_parse_contacts_sorts_by_distance():
    payload = {"ac": [
        {"hex": "far", "lat": 30.60, "lon": -97.74, "alt_baro": 30000},
        {"hex": "near", "lat": 30.28, "lon": -97.74, "alt_baro": 3000},
        {"hex": "mid", "lat": 30.40, "lon": -97.74, "alt_baro": 10000},
    ]}
    assert [c.hex for c in _parse_contacts(payload, 30.27, -97.74)] == [
        "near", "mid", "far"]


def test_callsigns_are_stripped():
    """Feeds pad the callsign field with trailing spaces."""
    payload = {"ac": [{"hex": "a", "lat": 30.3, "lon": -97.75,
                       "alt_baro": 3000, "flight": "SWA3803 "}]}
    assert _parse_contacts(payload, 30.27, -97.74)[0].callsign == "SWA3803"


def test_falls_back_to_geometric_altitude():
    payload = {"ac": [{"hex": "a", "lat": 30.3, "lon": -97.75,
                       "alt_baro": None, "alt_geom": 4200}]}
    assert _parse_contacts(payload, 30.27, -97.74)[0].alt == 4200


@pytest.mark.parametrize("squawk", ["7500", "7600", "7700"])
def test_emergency_squawks_are_flagged(squawk):
    assert _contact(squawk=squawk).emergency is True


def test_ordinary_squawk_is_not_an_emergency():
    assert _contact(squawk="1200").emergency is False
    assert _contact(squawk="").emergency is False


# --- dead reckoning --------------------------------------------------------

def test_dead_reckoning_moves_along_the_track():
    c = _contact(east=0.0, north=0.0, speed=600.0, track=90.0)  # due east
    c.advance(3600.0)
    assert c.east == pytest.approx(600.0 / fr.NM_PER_MILE, rel=1e-6)
    assert c.north == pytest.approx(0.0, abs=1e-9)


def test_dead_reckoning_is_a_noop_without_usable_data():
    for kwargs in ({"track": None}, {"speed": 0.0}, {"on_ground": True}):
        c = _contact(east=1.0, north=2.0, **kwargs)
        c.advance(60.0)
        assert (c.east, c.north) == (1.0, 2.0)


def test_contact_distance_and_bearing():
    c = _contact(east=3.0, north=4.0)
    assert c.distance == pytest.approx(5.0)
    assert c.bearing == pytest.approx(math.degrees(math.atan2(3.0, 4.0)))


# --- styling ---------------------------------------------------------------

def test_altitude_colours_are_distinct_and_ordered():
    colors = [_alt_color(a) for a in (0, 1500, 6000, 15000, 25000, 40000)]
    assert len(set(colors)) == len(colors)


def test_altitude_colour_is_defined_beyond_the_top_band():
    assert _alt_color(70000) == fr.ALT_BANDS[-1][1]
    assert _alt_color(-500) == fr.ALT_BANDS[0][1]


def test_blip_size_scales_with_weight_class_and_has_a_default():
    assert _blip_size("A5") > _blip_size("A1")
    assert _blip_size("A3") >= _blip_size("A1")
    assert _blip_size("") == fr.DEFAULT_BLIP_SIZE
    assert _blip_size(None) == fr.DEFAULT_BLIP_SIZE


def test_format_altitude_is_three_chars_wide():
    assert _format_altitude(_contact(on_ground=True)) == "GND"
    assert _format_altitude(_contact(alt=36000)) == "360"
    assert _format_altitude(_contact(alt=1775)) == "018"
    assert len(_format_altitude(_contact(alt=999999))) == 3


# --- sweep -----------------------------------------------------------------

def test_sweep_covers_a_simple_span():
    assert _sweep_covers(10.0, 20.0, 15.0) is True
    assert _sweep_covers(10.0, 20.0, 25.0) is False
    assert _sweep_covers(10.0, 20.0, 5.0) is False


def test_sweep_covers_wraps_through_north():
    assert _sweep_covers(355.0, 5.0, 359.0) is True
    assert _sweep_covers(355.0, 5.0, 2.0) is True
    assert _sweep_covers(355.0, 5.0, 180.0) is False


def test_every_bearing_is_swept_exactly_once_per_revolution():
    """A contact must not be missed or double-painted by rounding."""
    scope = Scope(30.0)
    dt = 1.0 / 30
    hits = {b: 0 for b in range(0, 360, 7)}
    frames = int(fr.SWEEP_PERIOD / dt) + 2
    for _ in range(frames):
        start, _end = scope.advance_sweep(dt)
        for b in hits:
            if _sweep_covers(start, scope.sweep, float(b)):
                hits[b] += 1
    assert all(v == 1 for v in hits.values()), hits


def test_sweep_period_is_respected():
    scope = Scope(30.0)
    for _ in range(30):
        scope.advance_sweep(fr.SWEEP_PERIOD / 30.0)
    assert scope.sweep == pytest.approx(0.0, abs=1e-6) or \
        scope.sweep == pytest.approx(360.0, abs=1e-6)


# --- scope rendering -------------------------------------------------------

def test_scope_scale_is_one_pixel_per_mile_at_thirty():
    assert Scope(30.0).px_per_mile == pytest.approx(1.0)


def test_scope_places_north_above_centre():
    scope = Scope(30.0)
    x, y = scope.to_screen(_contact(east=0.0, north=10.0))
    assert x == pytest.approx(fr.CX)
    assert y < fr.CY, "north must render upward"


def test_scope_places_east_to_the_right():
    scope = Scope(30.0)
    x, y = scope.to_screen(_contact(east=10.0, north=0.0))
    assert x > fr.CX
    assert y == pytest.approx(fr.CY)


def test_in_range_uses_the_configured_radius():
    scope = Scope(30.0)
    assert scope.in_range(_contact(east=0.0, north=29.0)) is True
    assert scope.in_range(_contact(east=0.0, north=31.0)) is False


def test_compose_returns_a_full_panel_frame():
    frame = Scope(30.0).compose()
    assert frame.size == (fr.WIDTH, fr.HEIGHT)
    assert frame.mode == "RGB"


def test_nothing_is_drawn_outside_the_scope_disc():
    """Phosphor must be clipped to the disc.

    The tolerance is 1.5px because PIL rasterises the scope bezel from a float
    bounding box and lands marginally outside the ideal radius; the mask is
    built from the same box, so the two agree.
    """
    scope = Scope(30.0)
    for _ in range(60):
        scope.decay()
        start, _e = scope.advance_sweep(1.0 / 30)
        scope.paint(_contact(east=0.0, north=29.5))
        scope.draw_beam(start)
    frame = scope.compose()
    for x in range(fr.WIDTH):
        for y in range(fr.HEIGHT):
            if math.hypot(x - fr.CX, y - fr.CY) <= fr.SCOPE_R + 1.5:
                continue
            assert frame.getpixel((x, y)) == (0, 0, 0), f"spill at {(x, y)}"


def test_hud_corners_are_clear_of_the_scope():
    """The count and range readouts live in the top corners, over nothing."""
    scope = Scope(30.0)
    for _ in range(60):
        scope.decay()
        start, _e = scope.advance_sweep(1.0 / 30)
        scope.draw_beam(start)
    frame = scope.compose()
    for x in list(range(0, 11)) + list(range(53, 64)):
        for y in range(0, 7):
            assert frame.getpixel((x, y)) == (0, 0, 0), f"HUD clash at {(x, y)}"


def test_beam_trail_is_uniform_not_a_comb():
    """Accumulating a bright leading edge used to leave alternating rays.

    Sampled at a fixed radius across the trail, brightness must fall off
    monotonically-ish rather than alternating bright/dim ray by ray.
    """
    scope = Scope(30.0)
    scope.sweep = 90.0          # beam pointing due east
    for _ in range(40):
        scope.decay()
        start, _e = scope.advance_sweep(1.0 / 30)
        scope.draw_beam(start)

    # Sample the trail behind the leading edge along an arc.
    r = 20.0
    samples = []
    for back in range(2, 22):
        bearing = scope.sweep - back
        rad = math.radians(bearing - 90)
        x = int(round(fr.CX + r * math.cos(rad)))
        y = int(round(fr.CY + r * math.sin(rad)))
        samples.append(sum(scope.beam_layer.getpixel((x, y))))

    lit = [v for v in samples if v > 0]
    assert len(lit) > 8, "trail is too short to judge"
    # No sample may be dimmer than a third of the one behind it: that is the
    # signature of the comb artefact.
    for near, far in zip(samples, samples[1:]):
        if far > 0:
            assert near >= far * 0.33, f"comb artefact: {samples}"


def test_contacts_outlive_the_beam_trail():
    scope = Scope(30.0)
    scope.paint(_contact(east=0.0, north=15.0))
    scope.draw_beam(None)
    for _ in range(90):     # three seconds
        scope.decay()
    blip = sum(scope.blip_layer.getpixel((int(fr.CX), int(fr.CY - 15))))
    assert blip > 0, "contact faded within a single sweep"
    assert fr.BLIP_DECAY > fr.BEAM_DECAY


def test_ground_contacts_get_no_heading_vector():
    """A parked aircraft has no meaningful track, so it must not grow a tail."""
    air = Scope(30.0)
    air.paint(_contact(east=0.0, north=10.0, on_ground=False))
    ground = Scope(30.0)
    ground.paint(_contact(east=0.0, north=10.0, on_ground=True, track=None))
    air_lit = sum(1 for v in air.blip_layer.tobytes() if v)
    gnd_lit = sum(1 for v in ground.blip_layer.tobytes() if v)
    assert air_lit > gnd_lit


def test_emergency_contact_paints_in_the_alert_colour():
    scope = Scope(30.0)
    scope.paint(_contact(east=0.0, north=10.0, squawk="7700", category="A1"))
    assert scope.blip_layer.getpixel((int(fr.CX), int(fr.CY - 10))) == fr.ALERT


def test_the_contact_is_brighter_than_its_heading_vector():
    """The leader line is drawn from the blip outward and must not dim it."""
    scope = Scope(30.0)
    scope.paint(_contact(east=0.0, north=10.0, track=90.0, speed=460.0,
                         category="A1", alt=36000))
    blip = scope.blip_layer.getpixel((int(fr.CX), int(fr.CY - 10)))
    leader = scope.blip_layer.getpixel((int(fr.CX) + 2, int(fr.CY - 10)))
    assert blip == fr._alt_color(36000)
    assert sum(leader) > 0, "heading vector missing"
    assert sum(blip) > sum(leader)


# --- HUD -------------------------------------------------------------------

def test_hud_prefers_airborne_traffic():
    ground = [_contact(callsign="PARKED%d" % i, on_ground=True, north=6.0)
              for i in range(5)]
    air = _contact(callsign="OVERHEAD", on_ground=False, north=12.0)
    chosen = _hud_candidates(ground + [air])
    assert chosen == [air]


def test_hud_falls_back_to_ground_when_nothing_is_flying():
    ground = [_contact(callsign="PARKED", on_ground=True)]
    assert _hud_candidates(ground) == ground


def test_hud_candidates_of_nothing_is_nothing():
    assert _hud_candidates([]) == []


@pytest.mark.parametrize("online,contacts", [
    (None, []),          # acquiring
    (False, []),         # network down
    (True, []),          # no traffic
])
def test_hud_degraded_states_render_without_a_contact(online, contacts):
    scope = Scope(30.0)
    frame = scope.compose()
    named = fr._draw_hud(frame, contacts, online, 0, 30.0, True)
    assert named is None
    assert frame.size == (fr.WIDTH, fr.HEIGHT)


def test_hud_returns_the_contact_it_named():
    scope = Scope(30.0)
    frame = scope.compose()
    contacts = [_contact(callsign="AAL100"), _contact(callsign="UAL200")]
    first = fr._draw_hud(frame, contacts, True, 0, 30.0, True)
    second = fr._draw_hud(frame, contacts, True, 1, 30.0, True)
    assert first in contacts and second in contacts
    assert first is not second, "HUD must cycle through contacts"


def test_hud_index_wraps_past_the_contact_count():
    scope = Scope(30.0)
    frame = scope.compose()
    contacts = [_contact(callsign="ONLY1")]
    assert fr._draw_hud(frame, contacts, True, 99, 30.0, True) is contacts[0]


def test_marker_draws_inside_the_frame_for_an_edge_contact():
    scope = Scope(30.0)
    frame = scope.compose()
    fr._draw_marker(frame, scope, _contact(east=0.0, north=29.5))
    assert frame.size == (fr.WIDTH, fr.HEIGHT)


# --- config ----------------------------------------------------------------

def test_config_falls_back_to_the_weather_location(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "PROJECT_ROOT", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "weather.json").write_text(
        json.dumps({"lat": 47.6, "lon": -122.3}))
    cfg = fr._load_config()
    assert cfg["lat"] == pytest.approx(47.6)
    assert cfg["lon"] == pytest.approx(-122.3)
    assert cfg["radius_miles"] == fr.DEFAULT_RADIUS_MILES


def test_config_prefers_its_own_location(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "PROJECT_ROOT", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "weather.json").write_text(
        json.dumps({"lat": 47.6, "lon": -122.3}))
    (tmp_path / "config" / "flight_radar.json").write_text(
        json.dumps({"lat": 51.5, "lon": -0.12, "radius_miles": 50}))
    cfg = fr._load_config()
    assert cfg["lat"] == pytest.approx(51.5)
    assert cfg["radius_miles"] == pytest.approx(50.0)


def test_config_survives_garbage(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "PROJECT_ROOT", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "flight_radar.json").write_text("{not json")
    cfg = fr._load_config()
    assert -90 <= cfg["lat"] <= 90
    assert -180 <= cfg["lon"] <= 180


def test_config_clamps_absurd_values(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "PROJECT_ROOT", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "flight_radar.json").write_text(json.dumps({
        "lat": 30.0, "lon": -97.0,
        "radius_miles": 99999, "poll_seconds": 0.001}))
    cfg = fr._load_config()
    assert cfg["radius_miles"] <= 150
    assert cfg["poll_seconds"] >= 5.0


def test_config_ignores_non_numeric_values(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "PROJECT_ROOT", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "flight_radar.json").write_text(json.dumps({
        "lat": 30.0, "lon": -97.0,
        "radius_miles": "wide", "poll_seconds": None}))
    cfg = fr._load_config()
    assert cfg["radius_miles"] == fr.DEFAULT_RADIUS_MILES
    assert cfg["poll_seconds"] == fr.DEFAULT_POLL_SECONDS


# --- feed threading --------------------------------------------------------

def test_feed_requests_the_radius_in_nautical_miles(monkeypatch):
    """The scope is labelled in statute miles; the API takes nautical."""
    seen = {}

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"ac": []}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen["headers"] = kwargs.get("headers", {})
        return Resp()

    monkeypatch.setattr(fr.requests, "get", fake_get)
    feed = AircraftFeed(30.27, -97.74, 30.0, 12.0)
    assert feed._poll_once() == []
    assert seen["url"].endswith("/26")      # 30 statute miles = 26 nm
    assert "User-Agent" in seen["headers"]


def test_feed_falls_back_to_the_second_endpoint(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, code):
            self.status_code = code

        def json(self):
            return {"ac": [{"hex": "z", "lat": 30.3, "lon": -97.75,
                            "alt_baro": 5000}]}

    def fake_get(url, **kwargs):
        calls.append(url)
        return Resp(500 if len(calls) == 1 else 200)

    monkeypatch.setattr(fr.requests, "get", fake_get)
    feed = AircraftFeed(30.27, -97.74, 30.0, 12.0)
    contacts = feed._poll_once()
    assert len(calls) == 2
    assert [c.hex for c in contacts] == ["z"]


def test_feed_returns_none_when_every_endpoint_fails(monkeypatch):
    def fake_get(url, **kwargs):
        raise fr.requests.RequestException("down")

    monkeypatch.setattr(fr.requests, "get", fake_get)
    feed = AircraftFeed(30.27, -97.74, 30.0, 12.0)
    assert feed._poll_once() is None


def test_feed_survives_a_non_json_body(monkeypatch):
    class Resp:
        status_code = 200

        @staticmethod
        def json():
            raise ValueError("not json")

    monkeypatch.setattr(fr.requests, "get", lambda url, **k: Resp())
    feed = AircraftFeed(30.27, -97.74, 30.0, 12.0)
    assert feed._poll_once() is None


def test_feed_snapshot_starts_empty_and_unknown():
    feed = AircraftFeed(30.27, -97.74, 30.0, 12.0)
    contacts, online = feed.snapshot()
    assert contacts == []
    assert online is None, "must report 'acquiring' before the first poll"


def test_feed_thread_stops_promptly(monkeypatch):
    """stop() must not wait out a poll interval."""
    monkeypatch.setattr(AircraftFeed, "_poll_once", lambda self: [])
    feed = AircraftFeed(30.27, -97.74, 30.0, 300.0)
    feed.start()
    time.sleep(0.05)
    feed.stop()
    feed._thread.join(timeout=2.0)
    assert not feed._thread.is_alive(), "poll wait is not interruptible"


def test_feed_marks_itself_offline_after_a_failure(monkeypatch):
    monkeypatch.setattr(AircraftFeed, "_poll_once", lambda self: None)
    feed = AircraftFeed(30.27, -97.74, 30.0, 300.0)
    feed.start()
    deadline = time.time() + 2.0
    while time.time() < deadline and feed.snapshot()[1] is None:
        time.sleep(0.02)
    feed.stop()
    feed._thread.join(timeout=2.0)
    assert feed.snapshot()[1] is False


# --- run() -----------------------------------------------------------------

def test_run_pushes_frames_and_clears(monkeypatch):
    monkeypatch.setattr(AircraftFeed, "_poll_once", lambda self: [])
    m = _Recorder()
    fr.run(m, duration=0.4)
    assert m.frames > 0
    assert m.cleared == 1
    assert m.last.size == (fr.WIDTH, fr.HEIGHT)


def test_run_renders_contacts_without_network(monkeypatch):
    payload = {"ac": [
        {"hex": "a", "lat": 30.35, "lon": -97.74, "alt_baro": 36000,
         "gs": 460, "track": 280, "flight": "JBU277", "category": "A3",
         "squawk": "3643", "seen_pos": 0.2},
        {"hex": "b", "lat": 30.20, "lon": -97.67, "alt_baro": "ground",
         "gs": 2, "track": None, "flight": "SWA3803", "category": "A3",
         "seen_pos": 1.0},
    ]}
    monkeypatch.setattr(
        AircraftFeed, "_poll_once",
        lambda self: _parse_contacts(payload, self.lat, self.lon))
    m = _Recorder()
    fr.run(m, duration=0.5)
    assert m.frames > 0


def test_run_stops_on_request(monkeypatch):
    from src.display import _shared
    monkeypatch.setattr(AircraftFeed, "_poll_once", lambda self: [])
    _shared.request_stop()
    m = _Recorder()
    fr.run(m, duration=30)
    assert m.frames == 0
    assert m.cleared == 1


def test_run_survives_a_broken_matrix(monkeypatch):
    monkeypatch.setattr(AircraftFeed, "_poll_once", lambda self: [])

    class Broken:
        def SetImage(self, *a, **k):
            raise RuntimeError("panel gone")

        def Clear(self):
            raise RuntimeError("still gone")

    fr.run(Broken(), duration=0.2)      # must not raise


def test_run_leaves_no_thread_behind(monkeypatch):
    import threading
    monkeypatch.setattr(AircraftFeed, "_poll_once", lambda self: [])
    before = threading.active_count()
    fr.run(_Recorder(), duration=0.3)
    deadline = time.time() + 2.0
    while time.time() < deadline and threading.active_count() > before:
        time.sleep(0.02)
    assert threading.active_count() <= before, "poll thread outlived the demo"


def test_frame_interval_is_a_sane_frame_rate():
    fps = 1.0 / fr.FRAME_INTERVAL
    assert 15 <= fps <= 60
