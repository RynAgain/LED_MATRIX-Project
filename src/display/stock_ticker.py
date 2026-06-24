#!/usr/bin/env python3
"""Stock ticker display for 64x64 LED matrix using Yahoo Finance API.

Features:
- Top 5 movers of the day (biggest % change, market cap > $1B)
- Industry label clearly displayed for each stock
- Crisp bitmap font rendering (5x7 from _fonts.py)
- Mini sparkline chart showing intraday price movement
- Color-coded price/change (green=up, red=down)
- Animated up/down arrow indicator
- Smooth fade transitions between stocks
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
INDUSTRY_COLOR = (180, 140, 255)
CHART_UP = (0, 180, 60)
CHART_DOWN = (200, 40, 40)
CHART_GRID = (20, 25, 40)
TICKER_BG = (10, 10, 20)
SEPARATOR_COLOR = (30, 40, 60)

# Yahoo Finance screener URL for day gainers
SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=5m"
QUOTE_SUMMARY_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=assetProfile,price"

# Common headers to avoid being blocked
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Minimum market cap in USD (1 billion)
MIN_MARKET_CAP = 1_000_000_000


def _load_config():
    """Load stock config from JSON file."""
    try:
        with open(STOCKS_PATH, "r") as f:
            data = json.load(f)
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"mode": "top_movers", "top_movers_count": 5, "min_market_cap_billions": 1}


def _fetch_top_movers(count=5, min_cap_billions=1):
    """Fetch top movers of the day filtered by market cap > threshold.

    Uses Yahoo Finance's day_gainers and day_losers screener endpoints
    to find stocks with the biggest absolute percent change, then filters
    by market cap.

    Returns list of symbols sorted by absolute percent change (descending).
    """
    min_cap = min_cap_billions * 1_000_000_000
    movers = []

    # Try fetching day gainers and losers from Yahoo screener
    for screener_type in ["day_gainers", "day_losers"]:
        try:
            params = {
                "scrIds": screener_type,
                "count": 50,
            }
            resp = requests.get(SCREENER_URL, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            results = (
                data.get("finance", {})
                .get("result", [{}])[0]
                .get("quotes", [])
            )

            for quote in results:
                market_cap = quote.get("marketCap", 0) or 0
                if market_cap < min_cap:
                    continue
                symbol = quote.get("symbol", "")
                change_pct = quote.get("regularMarketChangePercent", 0) or 0
                industry = quote.get("industry", "") or quote.get("sector", "") or "N/A"
                movers.append({
                    "symbol": symbol,
                    "change_pct": change_pct,
                    "abs_change_pct": abs(change_pct),
                    "market_cap": market_cap,
                    "industry": industry,
                })
        except Exception as e:
            logger.warning("Failed to fetch %s screener: %s", screener_type, e)

    # If screener failed, try alternative approach with trending tickers
    if not movers:
        movers = _fetch_movers_fallback(count, min_cap)

    # Sort by absolute percent change and return top N
    movers.sort(key=lambda x: x["abs_change_pct"], reverse=True)
    return movers[:count]


def _fetch_movers_fallback(count, min_cap):
    """Fallback: fetch trending tickers and filter by market cap and movement."""
    movers = []
    try:
        # Try trending tickers endpoint
        url = "https://query1.finance.yahoo.com/v1/finance/trending/US"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
        symbols = [q.get("symbol", "") for q in quotes[:25]]

        if not symbols:
            # Use a curated list of high-cap stocks to check for movers
            symbols = [
                "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
                "BRK-B", "JPM", "V", "JNJ", "WMT", "PG", "MA", "UNH",
                "HD", "DIS", "BAC", "XOM", "PFE", "NFLX", "AMD", "CRM",
                "COST", "ABBV",
            ]

        # Batch fetch quotes for all symbols
        symbols_str = ",".join(symbols)
        quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols_str}"
        resp = requests.get(quote_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("quoteResponse", {}).get("result", [])

        for q in results:
            market_cap = q.get("marketCap", 0) or 0
            if market_cap < min_cap:
                continue
            symbol = q.get("symbol", "")
            change_pct = q.get("regularMarketChangePercent", 0) or 0
            industry = q.get("industry", "") or q.get("sector", "") or "N/A"
            movers.append({
                "symbol": symbol,
                "change_pct": change_pct,
                "abs_change_pct": abs(change_pct),
                "market_cap": market_cap,
                "industry": industry,
            })
    except Exception as e:
        logger.warning("Fallback movers fetch failed: %s", e)

    return movers


def _fetch_industry(symbol):
    """Fetch industry/sector for a given symbol from Yahoo Finance quoteSummary."""
    try:
        url = QUOTE_SUMMARY_URL.format(symbol=symbol)
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("quoteSummary", {}).get("result", [{}])[0]
        profile = result.get("assetProfile", {})
        industry = profile.get("industry", "")
        if not industry:
            industry = profile.get("sector", "N/A")
        return industry
    except Exception as e:
        logger.debug("Failed to fetch industry for %s: %s", symbol, e)
        return "N/A"


def _fetch_quote(symbol):
    """Fetch stock quote with intraday price history using Yahoo Finance."""
    url = QUOTE_URL.format(symbol=symbol)
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
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


def _truncate_industry(industry, max_width=60, scale=1):
    """Truncate industry name to fit within pixel width."""
    if _text_width(industry, scale=scale, spacing=1) <= max_width:
        return industry

    # Try common abbreviations
    abbreviations = {
        "Semiconductor": "Semicon",
        "Technology": "Tech",
        "Biotechnology": "Biotech",
        "Pharmaceuticals": "Pharma",
        "Communication": "Comm",
        "Consumer": "Consmr",
        "Information": "Info",
        "Electronic": "Elec",
        "Entertainment": "Entmt",
        "Financial": "Fin",
        "Manufacturing": "Mfg",
        "International": "Intl",
        "Services": "Svcs",
        "Equipment": "Equip",
        "Instruments": "Instr",
        "Healthcare": "Health",
        "Aerospace": "Aero",
        "Automotive": "Auto",
        "Infrastructure": "Infra",
    }

    shortened = industry
    for full, abbr in abbreviations.items():
        shortened = shortened.replace(full, abbr)

    if _text_width(shortened, scale=scale, spacing=1) <= max_width:
        return shortened

    # Last resort: truncate with ellipsis
    while len(shortened) > 3 and _text_width(shortened + "..", scale=scale, spacing=1) > max_width:
        shortened = shortened[:-1]
    return shortened + ".."


def _draw_sparkline(draw, prices, x, y, w, h, is_up):
    """Draw a mini sparkline chart of intraday prices."""
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
        price_range = 1

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

    # Draw filled area under the line
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

    # Draw the line itself
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=color)

    # Highlight current price (last point)
    if points:
        last = points[-1]
        draw.point(last, fill=(255, 255, 255))
        if last[0] + 1 < x + w:
            draw.point((last[0] + 1, last[1]), fill=color)


def _draw_arrow(draw, x, y, is_up, tick):
    """Draw an animated up/down arrow."""
    bounce = int(math.sin(tick * 0.3) * 1)

    if is_up:
        ay = y + bounce
        draw.point((x + 2, ay), fill=UP_COLOR)
        draw.line([(x + 1, ay + 1), (x + 3, ay + 1)], fill=UP_COLOR)
        draw.line([(x, ay + 2), (x + 4, ay + 2)], fill=UP_COLOR)
    else:
        ay = y - bounce
        draw.line([(x, ay), (x + 4, ay)], fill=DOWN_COLOR)
        draw.line([(x + 1, ay + 1), (x + 3, ay + 1)], fill=DOWN_COLOR)
        draw.point((x + 2, ay + 2), fill=DOWN_COLOR)


def _render_stock(quote, tick, rank=None):
    """Render a stock quote with industry and sparkline chart to a PIL Image.

    Layout (64x64):
      Row 0-8:    Symbol (large) + arrow + rank badge
      Row 9:      Separator
      Row 10-16:  Industry label (clearly displayed)
      Row 17:     Separator
      Row 18-28:  Price (scale=2, large)
      Row 29-36:  Change + percent
      Row 37:     Separator
      Row 38-57:  Sparkline chart
      Row 58-63:  Bottom accent bar
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(image)

    symbol = quote["symbol"]
    price = quote["price"]
    change = quote["change"]
    change_pct = quote["change_pct"]
    prices = quote.get("prices", [])
    industry = quote.get("industry", "N/A")
    is_up = change >= 0

    # Determine colors
    price_color = UP_COLOR if is_up else DOWN_COLOR
    if abs(change_pct) < 0.05:
        price_color = FLAT_COLOR

    # --- Rank badge + Symbol (top, bold) ---
    x_offset = 2
    if rank is not None:
        rank_str = f"#{rank}"
        _draw_text(draw, rank_str, x_offset, 1, (255, 200, 50), scale=1, spacing=1)
        x_offset += _text_width(rank_str, scale=1, spacing=1) + 2

    _draw_text(draw, symbol, x_offset, 1, SYMBOL_COLOR, scale=1, spacing=1)

    # Animated arrow next to symbol
    sym_w = _text_width(symbol, scale=1, spacing=1)
    _draw_arrow(draw, x_offset + sym_w + 2, 2, is_up, tick)

    # --- Separator ---
    draw.line([(2, 9), (61, 9)], fill=SEPARATOR_COLOR)

    # --- Industry label (clearly displayed) ---
    industry_display = _truncate_industry(industry, max_width=58, scale=1)
    _draw_text(draw, industry_display, 2, 11, INDUSTRY_COLOR, scale=1, spacing=1)

    # --- Separator ---
    draw.line([(2, 18), (61, 18)], fill=SEPARATOR_COLOR)

    # --- Price (large, scale=2) ---
    if price >= 10000:
        price_str = f"${price:.0f}"
    elif price >= 1000:
        price_str = f"${price:.1f}"
    else:
        price_str = f"${price:.2f}"
    _draw_text(draw, price_str, 2, 20, price_color, scale=2, spacing=1)

    # --- Change + Percent ---
    arrow_char = "+" if is_up else ""
    change_str = f"{arrow_char}{change:.2f}"
    if abs(change) >= 100:
        change_str = f"{arrow_char}{change:.1f}"
    pct_str = f"{arrow_char}{change_pct:.1f}%"

    _draw_text(draw, change_str, 2, 35, price_color, scale=1, spacing=1)
    pct_w = _text_width(pct_str, scale=1, spacing=1)
    _draw_text(draw, pct_str, WIDTH - pct_w - 2, 35, price_color, scale=1, spacing=1)

    # --- Separator ---
    draw.line([(2, 43), (61, 43)], fill=SEPARATOR_COLOR)

    # --- Sparkline chart ---
    _draw_sparkline(draw, prices, x=2, y=45, w=60, h=14, is_up=is_up)

    # --- Bottom accent bar ---
    bar_color = UP_COLOR if is_up else DOWN_COLOR
    pulse = 0.6 + 0.4 * math.sin(tick * 0.1)
    bar_color = (
        int(bar_color[0] * pulse),
        int(bar_color[1] * pulse),
        int(bar_color[2] * pulse),
    )
    draw.rectangle([2, 61, 61, 63], fill=bar_color)

    return image


def _render_loading():
    """Render a loading screen."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(image)
    text = "LOADING"
    tw = _text_width(text, scale=1)
    _draw_text(draw, text, (WIDTH - tw) // 2, 12, LABEL_COLOR, scale=1)
    text2 = "TOP MOVERS"
    tw2 = _text_width(text2, scale=1)
    _draw_text(draw, text2, (WIDTH - tw2) // 2, 24, INDUSTRY_COLOR, scale=1)
    text3 = ">$1B CAP"
    tw3 = _text_width(text3, scale=1)
    _draw_text(draw, text3, (WIDTH - tw3) // 2, 36, LABEL_COLOR, scale=1)
    return image


def run(matrix, duration=60):
    """Run the stock ticker showing top 5 movers of the day."""
    start_time = time.time()
    config = _load_config()
    mode = config.get("mode", "top_movers")
    top_count = config.get("top_movers_count", 5)
    min_cap_billions = config.get("min_market_cap_billions", 1)

    quotes = {}
    industries = {}
    symbols = []
    last_fetch = 0
    sym_idx = 0
    tick = 0
    display_start = 0
    display_seconds = 6  # Show each stock for 6 seconds
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

            # Fetch data every 120 seconds (movers change less frequently)
            if now - last_fetch > 120 or not quotes:
                if mode == "top_movers":
                    movers = _fetch_top_movers(count=top_count, min_cap_billions=min_cap_billions)
                    if movers:
                        symbols = [m["symbol"] for m in movers]
                        # Store industry info from screener results
                        for m in movers:
                            industries[m["symbol"]] = m.get("industry", "N/A")
                    else:
                        # Fallback to configured symbols
                        symbols = config.get("symbols", ["AMZN", "AAPL", "GOOGL", "MSFT", "NVDA"])
                else:
                    symbols = config.get("symbols", ["AMZN"])

                # Fetch detailed quotes for each symbol
                for sym in symbols:
                    q = _fetch_quote(sym)
                    if q:
                        # Add industry info
                        if sym not in industries or industries[sym] == "N/A":
                            industries[sym] = _fetch_industry(sym)
                        q["industry"] = industries.get(sym, "N/A")
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
                    rank = sym_idx + 1 if mode == "top_movers" else None
                    next_img = _render_stock(quotes[current_sym], tick, rank=rank)
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
                # Re-render current stock (for animations)
                current_sym = symbols[sym_idx % len(symbols)]
                if current_sym in quotes:
                    rank = sym_idx + 1 if mode == "top_movers" else None
                    current_img = _render_stock(quotes[current_sym], tick, rank=rank)
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
