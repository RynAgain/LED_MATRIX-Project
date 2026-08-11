"""Tests for the precipitation radar demo.

Everything runs offline: RainViewer traffic is either mocked at the
``requests.get`` level (feed tests) or bypassed entirely by exercising
the pure helpers (geometry, colour ramp, resampling, frame cycling).
"""

import io
import json
import math
import time
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.display import rain_radar
from src.display.rain_radar import (
    ECHO_MIN_ALPHA,
    HEIGHT,
    RAIN_BANDS,
    RainFeed,
    TILE_SIZE,
    WIDTH,
    _age_label,
    _box_px,
    _build_basemap,
    _color_for,
    _colorize,
    _Cycler,
    _intensity,
    _mercator_px,
    _resample_echo,
)


@pytest.fixture(autouse=True)
def _clear_stop():
    from src.display import _shared
    _shared.clear_stop()
    yield
    _shared.clear_stop()


class _Recorder:
    def __init__(self):
        self.frames = 0
        self.last = None
        self.cleared = 0

    def SetImage(self, image, *a, **k):
        self.frames += 1
        self.last = image.copy()

    def Clear(self):
        self.cleared += 1


# --- geometry ----------------------------------------------------------------

def test_mercator_px_reference_points():
    scale = TILE_SIZE * (2 ** 8)
    x, y = _mercator_px(0.0, 0.0, 8)
    assert x == pytest.approx(scale / 2)
    assert y == pytest.approx(scale / 2)
    x_east, _ = _mercator_px(0.0, 90.0, 8)
    assert x_east == pytest.approx(scale * 0.75)
    _, y_north = _mercator_px(45.0, 0.0, 8)
    assert y_north < scale / 2, "north must be a smaller y"


def test_box_px_is_square_and_centred():
    x0, y0, x1, y1 = _box_px(30.27, -97.75, 30.0, rain_radar.ZOOM)
    assert (x1 - x0) == pytest.approx(y1 - y0)
    cx, cy = _mercator_px(30.27, -97.75, rain_radar.ZOOM)
    assert (x0 + x1) / 2 == pytest.approx(cx)
    assert (y0 + y1) / 2 == pytest.approx(cy)
    # ~183 px across a 60 mile box at this latitude/zoom/tile size
    assert 150 < (x1 - x0) < 220


# --- colour ramp --------------------------------------------------------------

def test_color_ramp_is_ordered_and_covers_all_ranks():
    ceilings = [c for c, _ in RAIN_BANDS]
    assert ceilings == sorted(ceilings)
    assert ceilings[-1] >= 1.0
    for rank in (0.0, 0.2, 0.5, 0.8, 1.0):
        color = _color_for(rank)
        assert len(color) == 3
        assert all(0 <= c <= 255 for c in color)


def test_intensity_ranks_the_rainviewer_palette_in_order():
    """Anchors sampled from live tiles must escalate correctly."""
    khaki_drizzle = _intensity(210, 196, 139)
    light_blue = _intensity(136, 221, 238)
    dark_blue = _intensity(0, 98, 149)
    yellow = _intensity(255, 216, 0)
    orange = _intensity(255, 130, 0)
    red = _intensity(220, 30, 30)
    magenta = _intensity(200, 40, 200)
    assert (khaki_drizzle < light_blue < dark_blue
            < yellow < orange < red < magenta)
    for v in (khaki_drizzle, light_blue, dark_blue, yellow, orange, red,
              magenta):
        assert 0.0 <= v <= 1.0


def test_colorize_maps_echo_and_keeps_silence_transparent():
    rgb = Image.new("RGB", (8, 8), (0, 0, 0))
    alpha = Image.new("L", (8, 8), 0)
    rgb.putpixel((2, 2), (200, 40, 200))         # magenta core
    alpha.putpixel((2, 2), 200)
    rgb.putpixel((5, 5), (220, 30, 30))
    alpha.putpixel((5, 5), ECHO_MIN_ALPHA - 1)   # sub-threshold noise
    out = _colorize(rgb, alpha)
    assert out.getpixel((2, 2))[:3] == RAIN_BANDS[-1][1]
    assert out.getpixel((2, 2))[3] > 0
    assert out.getpixel((5, 5)) == (0, 0, 0, 0)
    assert out.getpixel((0, 0)) == (0, 0, 0, 0)


def test_resample_echo_does_not_dilute_cell_interiors():
    """Alpha-weighted resize must keep a solid cell's colour intact."""
    rgb = Image.new("RGB", (128, 128), (0, 0, 0))
    alpha = Image.new("L", (128, 128), 0)
    for x in range(40, 90):
        for y in range(40, 90):
            rgb.putpixel((x, y), (0, 98, 149))
            alpha.putpixel((x, y), 220)
    echo, a = _resample_echo(rgb, alpha, (0, 0, 128, 128), (32, 32))
    # Centre of the blob maps to around (16, 16) at quarter scale.
    r, g, b = echo.getpixel((16, 16))
    assert r == pytest.approx(0, abs=8)
    assert g == pytest.approx(98, abs=8)
    assert b == pytest.approx(149, abs=8)
    assert a.getpixel((16, 16)) == pytest.approx(220, abs=8)
    assert a.getpixel((2, 2)) == 0


# --- frame cycling -------------------------------------------------------------

def test_cycler_steps_through_frames_and_wraps():
    c = _Cycler()
    seen = set()
    for _ in range(200):
        seen.add(c.advance(rain_radar.FRAME_DWELL, 5, hold_index=-1))
    assert seen == {0, 1, 2, 3, 4}


def test_cycler_holds_longer_on_the_newest_frame():
    c = _Cycler()
    # Advance to the hold frame.
    while c.advance(rain_radar.FRAME_DWELL, 4, hold_index=2) != 2:
        pass
    # One ordinary dwell must NOT move it off the hold frame.
    assert c.advance(rain_radar.FRAME_DWELL, 4, hold_index=2) == 2


def test_cycler_survives_an_empty_frame_list():
    c = _Cycler()
    c.index = 7
    assert c.advance(0.5, 0, hold_index=-1) == 0


# --- age label -----------------------------------------------------------------

def test_age_label():
    now = 1000000.0
    assert _age_label(now, now) == "NOW"
    assert _age_label(now - 120, now) == "NOW"          # within tolerance
    assert _age_label(now - 2400, now) == "-40M"
    assert _age_label(now + 1200, now) == "+20M"


# --- feed ------------------------------------------------------------------------

def _fake_index(host="https://tiles.example"):
    return {
        "host": host,
        "radar": {
            "past": [{"time": 1000 + i, "path": "/v2/radar/p%d" % i}
                     for i in range(10)],
            "nowcast": [{"time": 2000 + i, "path": "/v2/radar/n%d" % i}
                        for i in range(3)],
        },
    }


def _tile_png():
    img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    for x in range(100, 140):
        for y in range(100, 140):
            img.putpixel((x, y), (0, 98, 149, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fake_get(url, **kwargs):
    resp = MagicMock()
    resp.status_code = 200
    if "weather-maps.json" in url:
        resp.json.return_value = _fake_index()
    else:
        resp.content = _tile_png()
    return resp


def test_feed_poll_builds_frames_with_nowcast_flags():
    feed = RainFeed(30.27, -97.75, 30.0)
    with patch("src.display.rain_radar.requests.get", side_effect=_fake_get):
        frames = feed._poll_once()
    assert frames is not None
    past = [f for f in frames if not f["nowcast"]]
    nowcast = [f for f in frames if f["nowcast"]]
    assert len(past) == rain_radar.PAST_FRAMES
    assert len(nowcast) == rain_radar.NOWCAST_FRAMES
    for f in frames:
        assert f["overlay"].size == (WIDTH, HEIGHT)
        assert f["overlay"].mode == "RGBA"


def test_feed_reuses_cached_overlays_between_polls():
    feed = RainFeed(30.27, -97.75, 30.0)
    calls = []

    def counting_get(url, **kwargs):
        calls.append(url)
        return _fake_get(url, **kwargs)

    with patch("src.display.rain_radar.requests.get",
               side_effect=counting_get):
        feed._poll_once()
        first = len(calls)
        feed._poll_once()
        second = len(calls) - first
    # Second poll refetches the index but no tiles.
    assert second < first
    assert second <= 2


def test_feed_offline_returns_none():
    feed = RainFeed(30.27, -97.75, 30.0)
    with patch("src.display.rain_radar.requests.get",
               side_effect=Exception("no network")):
        assert feed._poll_once() is None


def test_feed_malformed_index_returns_none():
    def bad_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"unexpected": True}
        return resp

    feed = RainFeed(30.27, -97.75, 30.0)
    with patch("src.display.rain_radar.requests.get", side_effect=bad_get):
        assert feed._poll_once() is None


# --- basemap / run ---------------------------------------------------------------

def test_basemap_draws_something():
    img = _build_basemap(30.2706, -97.7525, 30.0)
    assert img.size == (WIDTH, HEIGHT)
    lit = sum(1 for px in img.convert("RGB").tobytes() if px)
    assert lit > 50


def test_basemap_far_from_cache_falls_back_to_rings():
    img = _build_basemap(51.5, -0.1, 30.0)   # London: map cache must be rejected
    assert img.size == (WIDTH, HEIGHT)


def test_run_pushes_frames_offline():
    m = _Recorder()
    with patch("src.display.rain_radar.requests.get",
               side_effect=Exception("no network")):
        rain_radar.run(m, duration=0.4)
    assert m.frames > 0
    assert m.cleared == 1
    assert m.last.size == (WIDTH, HEIGHT)


def test_run_renders_rain_overlay_online():
    m = _Recorder()
    with patch("src.display.rain_radar.requests.get", side_effect=_fake_get):
        rain_radar.run(m, duration=0.6)
    assert m.frames > 0
    # The synthetic blob must actually reach the panel in some frame.
    lit = sum(1 for px in m.last.convert("RGB").tobytes() if px > 60)
    assert lit > 0


def test_run_stops_on_request():
    from src.display import _shared
    m = _Recorder()
    _shared.request_stop()
    with patch("src.display.rain_radar.requests.get",
               side_effect=Exception("no network")):
        rain_radar.run(m, duration=30)
    assert m.frames == 0
    assert m.cleared == 1
