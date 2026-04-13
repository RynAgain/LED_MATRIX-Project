#!/usr/bin/env python3
"""Stock ticker display for 64x64 LED matrix using Yahoo Finance API."""

import time
import json
import os
import logging
import requests
from PIL import Image, ImageDraw, ImageFont
from src.display._shared import should_stop, interruptible_sleep

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STOCKS_PATH = os.path.join(PROJECT_ROOT, "config", "stocks.json")


def _load_stocks():
    """Load stock symbols from config."""
    try:
        with open(STOCKS_PATH, "r") as f:
            data = json.load(f)
        return data.get("symbols", ["AMZN"])
    except (FileNotFoundError, json.JSONDecodeError):
        return ["AMZN"]


def _fetch_quote(symbol):
    """Fetch stock quote using Yahoo Finance v8 API (free, no key)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m"
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
        return {
            "symbol": symbol,
            "price": price,
            "change": change,
            "change_pct": change_pct,
        }
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", symbol, e)
        return None


def _render_stock(quote):
    """Render a stock quote to a PIL Image."""
    image = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 10))
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    symbol = quote["symbol"]
    price = quote["price"]
    change = quote["change"]
    change_pct = quote["change_pct"]

    # Color based on up/down
    if change >= 0:
        price_color = (0, 255, 80)    # Green for up
        arrow = "+"
    else:
        price_color = (255, 50, 50)   # Red for down
        arrow = ""

    # Symbol at top
    draw.text((2, 2), symbol, fill=(255, 255, 255), font=font)

    # Price (large)
    price_text = f"${price:.2f}"
    if price >= 1000:
        price_text = f"${price:.1f}"
    if price >= 10000:
        price_text = f"${price:.0f}"
    draw.text((2, 18), price_text, fill=price_color, font=font)

    # Change
    change_text = f"{arrow}{change:.2f}"
    draw.text((2, 34), change_text, fill=price_color, font=font)

    # Percent
    pct_text = f"{arrow}{change_pct:.1f}%"
    draw.text((2, 48), pct_text, fill=price_color, font=font)

    return image


def run(matrix, duration=60):
    """Run the stock ticker for the specified duration."""
    start_time = time.time()
    symbols = _load_stocks()
    quotes = {}
    last_fetch = 0
    sym_idx = 0

    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            now = time.time()

            # Fetch all quotes every 30 seconds
            if now - last_fetch > 30 or not quotes:
                for sym in symbols:
                    q = _fetch_quote(sym)
                    if q:
                        quotes[sym] = q
                last_fetch = now

            # Display current symbol
            if symbols:
                current_sym = symbols[sym_idx % len(symbols)]
                if current_sym in quotes:
                    image = _render_stock(quotes[current_sym])
                    matrix.SetImage(image)

            # Show each stock for 5 seconds
            if not interruptible_sleep(5):
                break
            sym_idx += 1

    except Exception as e:
        logger.error("Error in stock ticker: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
