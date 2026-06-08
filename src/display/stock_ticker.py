#!/usr/bin/env python3
"""Stock ticker display for 64x64 LED matrix using Yahoo Finance API.

Features:
- Crisp bitmap font rendering (5x7 from _fonts.py)
- Mini sparkline chart showing intraday price movement
- Color-coded price/change (green=up, red=down)
- Animated up/down arrow indicator
- Smooth fade transitions between stocks
- Scrolling ticker bar at bottom with all symbols
"""

import time
import math
import json
import os
import logging
import requests
from PIL import Image, ImageDraw
from src.display._fonts import _draw_text, _text_width
from src.display._shared import should_stop, interruptible_sleep

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
FRAME_INTERVAL = 1.0 / 15  # 15 FPS for smooth animations
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STOCKS_PATH = os.path.join(PROJECT_ROOT, "config", "stocks.json")

# Colors
BG_COLOR = (0, 0, 8)
UP_COLOR = (0, 230, 80)
DOWN_COLOR = (255, 50, 50)
FLAT_COLOR = (180, 180, 180)
SYMBOL_COLOR = (255, 255, 255)
LABEL_COLOR = (100, 120, 150)
CHART_UP = (0, 180, 60)
CHART_DOWN = (200, 40, 40)
CHART_GRID = (20, 25, 40)
TICKER_BG = (10, 10, 20)
SEPARATOR_COLOR = (30, 40, 60)


def _load_stocks():
    """Load stock symbols from config."""
    try:
        with open(STOCKS_PATH, "r") as f:
            data = json.load(f)
        return data.get("symbols", ["AMZN"])
    except (FileNotFoundError, json.JSONDecodeError):
        return ["AMZN"]


def _fetch_quote(symbol):
    """Fetch stock quote with intraday price history using Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=5m"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev_close = meta.get("chartPreviousClose", price)
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        # Get intraday price history for sparkline
        indicators = result.get("indicators", {})
        closes = indicators.get("quote", [{}])[0].get("close", [])
        # Filter out None values
        prices = [p for p in closes if p is not None]

        return {
            "symbol": symbol,
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "prev_close": prev_close,
            "prices": prices,  # Intraday price list for sparkline
        }
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", symbol, e)
        return None


def _draw_sparkline(draw, prices, x, y, w, h, is_up):
    """Draw a mini sparkline chart of intraday prices.

    Args:
        draw: PIL ImageDraw context
        prices: list of price values
        x, y: top-left corner of chart area
        w, h: width and height of chart area
        is_up: True if stock is up (green), False if down (red)
    """
    if not prices or len(prices) < 2:
        return

    # Draw subtle grid lines
    for gy in range(y + h // 4, y + h, h // 4):
        for gx in range(x, x + w, 3):
            draw.point((gx, gy), fill=CHART_GRID)

    # Normalize prices to chart height
    min_p = min(prices)
    max_p = max(prices)
    price_range = max_p - min_p
    if price_range == 0:
        price_range = 1  # Avoid division by zero

    # Draw the sparkline
    color = CHART_UP if is_up else CHART_DOWN
    dim_color = (color[0] // 3, color[1] // 3, color[2] // 3)

    points = []
    step = max(1, len(prices) / w)
    for i in range(w):
        idx = min(int(i * step), len(prices) - 1)
        normalized = (prices[idx] - min_p) / price_range
        py = y + h - 1 - int(normalized * (h - 2))
        px = x + i
        points.append((px, py))

    # Draw filled area under the line (subtle gradient)
    for i, (px, py) in enumerate(points):
        for fill_y in range(py, y + h):
            alpha = max(0, 1.0 - (fill_y - py) / (h * 0.8))
            fill_color = (
                int(dim_color[0] * alpha),
                int(dim_color[1] * alpha),
                int(dim_color[2] * alpha),
            )
            if fill_color != (0, 0, 0):
                draw.point((px, fill_y), fill=fill_color)

    # Draw the line itself (brighter)
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=color)

    # Highlight current price (last point) with a bright dot
    if points:
        last = points[-1]
        draw.point(last, fill=(255, 255, 255))
        if last[0] + 1 < x + w:
            draw.point((last[0] + 1, last[1]), fill=color)


def _draw_arrow(draw, x, y, is_up, tick):
    """Draw an animated up/down arrow."""
    # Subtle bounce animation
    bounce = int(math.sin(tick * 0.3) * 1)

    if is_up:
        # Up arrow (▲)
        ay = y + bounce
        draw.point((x + 2, ay), fill=UP_COLOR)
        draw.line([(x + 1, ay + 1), (x + 3, ay + 1)], fill=UP_COLOR)
        draw.line([(x, ay + 2), (x + 4, ay + 2)], fill=UP_COLOR)
    else:
        # Down arrow (▼)
        ay = y - bounce
        draw.line([(x, ay), (x + 4, ay)], fill=DOWN_COLOR)
        draw.line([(x + 1, ay + 1), (x + 3, ay + 1)], fill=DOWN_COLOR)
        draw.point((x + 2, ay + 2), fill=DOWN_COLOR)


def _render_stock(quote, tick):
    """Render a stock quote with sparkline chart to a PIL Image.

    Layout (64x64):
      Row 0-8:    Symbol (large) + arrow indicator
      Row 9:      Separator
      Row 10-20:  Price (scale=2, large)
      Row 21-28:  Change + percent
      Row 29:     Separator
      Row 30-58:  Sparkline chart
      Row 59-63:  Bottom accent bar
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(image)

    symbol = quote["symbol"]
    price = quote["price"]
    change = quote["change"]
    change_pct = quote["change_pct"]
    prices = quote.get("prices", [])
    is_up = change >= 0

    # Determine colors
    price_color = UP_COLOR if is_up else DOWN_COLOR
    if abs(change_pct) < 0.05:
        price_color = FLAT_COLOR

    # --- Symbol (top, bold) ---
    _draw_text(draw, symbol, 2, 1, SYMBOL_COLOR, scale=1, spacing=1)

    # Animated arrow next to symbol
    sym_w = _text_width(symbol, scale=1, spacing=1)
    _draw_arrow(draw, sym_w + 4, 2, is_up, tick)

    # --- Separator ---
    draw.line([(2, 9), (61, 9)], fill=SEPARATOR_COLOR)

    # --- Price (large, scale=2) ---
    if price >= 10000:
        price_str = f"${price:.0f}"
    elif price >= 1000:
        price_str = f"${price:.1f}"
    else:
        price_str = f"${price:.2f}"
    _draw_text(draw, price_str, 2, 11, price_color, scale=2, spacing=1)

    # --- Change + Percent ---
    arrow_char = "+" if is_up else ""
    change_str = f"{arrow_char}{change:.2f}"
    if abs(change) >= 100:
        change_str = f"{arrow_char}{change:.1f}"
    pct_str = f"{arrow_char}{change_pct:.1f}%"

    _draw_text(draw, change_str, 2, 26, price_color, scale=1, spacing=1)
    pct_w = _text_width(pct_str, scale=1, spacing=1)
    _draw_text(draw, pct_str, WIDTH - pct_w - 2, 26, price_color, scale=1, spacing=1)

    # --- Separator ---
    draw.line([(2, 34), (61, 34)], fill=SEPARATOR_COLOR)

    # --- Sparkline chart (main visual) ---
    _draw_sparkline(draw, prices, x=2, y=36, w=60, h=22, is_up=is_up)

    # --- Bottom accent bar ---
    bar_color = UP_COLOR if is_up else DOWN_COLOR
    # Pulsing brightness
    pulse = 0.6 + 0.4 * math.sin(tick * 0.1)
    bar_color = (
        int(bar_color[0] * pulse),
        int(bar_color[1] * pulse),
        int(bar_color[2] * pulse),
    )
    draw.rectangle([2, 60, 61, 62], fill=bar_color)

    return image


def _render_loading():
    """Render a loading screen."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(image)
    text = "LOADING"
    tw = _text_width(text, scale=1)
    _draw_text(draw, text, (WIDTH - tw) // 2, 12, LABEL_COLOR, scale=1)
    text2 = "STOCKS"
    tw2 = _text_width(text2, scale=1)
    _draw_text(draw, text2, (WIDTH - tw2) // 2, 24, LABEL_COLOR, scale=1)
    return image


def run(matrix, duration=60):
    """Run the stock ticker for the specified duration."""
    start_time = time.time()
    symbols = _load_stocks()
    quotes = {}
    last_fetch = 0
    sym_idx = 0
    tick = 0
    display_start = 0  # When current stock started displaying
    display_seconds = 5  # Show each stock for 5 seconds
    transitioning = False
    transition_start = 0
    transition_duration = 0.5
    current_img = None
    next_img = None

    try:
        # Show loading screen while fetching
        matrix.SetImage(_render_loading())

        while time.time() - start_time < duration:
            if should_stop():
                break
            frame_start = time.time()
            tick += 1
            now = time.time()

            # Fetch all quotes every 60 seconds
            if now - last_fetch > 60 or not quotes:
                for sym in symbols:
                    q = _fetch_quote(sym)
                    if q:
                        quotes[sym] = q
                last_fetch = now

            if not quotes:
                matrix.SetImage(_render_loading())
                time.sleep(1)
                continue

            # Check if it's time to switch stocks
            if not transitioning and (now - display_start) >= display_seconds:
                sym_idx = (sym_idx + 1) % len(symbols)
                current_sym = symbols[sym_idx]
                if current_sym in quotes:
                    next_img = _render_stock(quotes[current_sym], tick)
                    if current_img is not None:
                        transitioning = True
                        transition_start = now
                    else:
                        current_img = next_img
                        next_img = None
                        display_start = now

            # Handle fade transition
            if transitioning:
                elapsed = now - transition_start
                alpha = min(1.0, elapsed / transition_duration)
                if alpha >= 1.0:
                    current_img = next_img
                    next_img = None
                    transitioning = False
                    display_start = now
                else:
                    blended = Image.blend(current_img, next_img, alpha)
                    matrix.SetImage(blended)
            elif current_img:
                # Re-render current stock (for animations like arrow bounce, pulse)
                current_sym = symbols[sym_idx % len(symbols)]
                if current_sym in quotes:
                    current_img = _render_stock(quotes[current_sym], tick)
                matrix.SetImage(current_img)

            # Frame rate control
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error("Error in stock ticker: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
