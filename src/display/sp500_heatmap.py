#!/usr/bin/env python3
"""S&P 500 heat map for 64x64 LED matrix.

Each pixel block represents one S&P 500 company.
Green = up today, Red = down today. Brightness = magnitude of change.
Companies are sorted by market cap (largest get bigger blocks).
"""

import time
import json
import os
import logging
import requests
from PIL import Image
from src.display._shared import should_stop

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 64, 64
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_PATH = os.path.join(PROJECT_ROOT, "logs", "sp500_cache.json")

# Top S&P 500 companies by approximate market cap (as of 2024)
# We include ~500 symbols; the display will fill the 64x64 grid
SP500_SYMBOLS = [
    # Mega cap (largest blocks)
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "LLY", "AVGO", "JPM",
    "TSLA", "UNH", "XOM", "V", "MA", "PG", "COST", "JNJ", "HD", "ABBV",
    "WMT", "NFLX", "BAC", "CRM", "MRK", "CVX", "KO", "ORCL", "AMD", "PEP",
    "TMO", "ACN", "LIN", "CSCO", "MCD", "ADBE", "ABT", "WFC", "DHR", "PM",
    "TXN", "GE", "QCOM", "ISRG", "INTU", "CAT", "IBM", "NEE", "AMGN", "AMAT",
    # Large cap
    "DIS", "VZ", "BKNG", "PFE", "T", "UBER", "RTX", "HON", "UNP", "LOW",
    "SPGI", "SYK", "GS", "BLK", "ELV", "SCHW", "PLD", "MDLZ", "ADP", "DE",
    "TJX", "GILD", "CB", "MMC", "BMY", "VRTX", "LRCX", "ADI", "SLB", "PANW",
    "AXP", "CME", "FI", "CI", "REGN", "MO", "ETN", "KLAC", "SNPS", "SO",
    "BSX", "CDNS", "EQIX", "DUK", "ICE", "BDX", "MU", "NOC", "SHW", "MCK",
    "PH", "CMG", "PNC", "ITW", "CL", "APD", "USB", "PYPL", "GD", "TGT",
    "MMM", "MSI", "CTAS", "EMR", "ORLY", "NXPI", "CEG", "TDG", "MCO", "EOG",
    "AJG", "WELL", "HCA", "AFL", "CARR", "WMB", "OKE", "AIG", "SPG", "ROP",
    "PSA", "TFC", "NSC", "KMB", "SRE", "FDX", "DLR", "MPC", "GM", "AZO",
    "HUM", "F", "COR", "ALL", "AEP", "D", "FAST", "ROST", "CPRT", "KHC",
    # Mid-large cap
    "PSX", "PCG", "DHI", "MSCI", "O", "GWW", "PAYX", "TEL", "KDP", "BK",
    "FTNT", "AMP", "AME", "LHX", "CTVA", "YUM", "EXC", "A", "VRSK", "STZ",
    "PCAR", "CNC", "DAL", "IDXX", "EW", "GEHC", "XEL", "MNST", "IQV", "IT",
    "DD", "OTIS", "CTSH", "DXCM", "GIS", "HES", "MCHP", "ON", "NUE", "KMI",
    "HPQ", "RCL", "BKR", "LULU", "ED", "EIX", "MTD", "ACGL", "AWK", "CDW",
    "CBRE", "DOW", "VMC", "PPG", "WEC", "MLM", "ROK", "FANG", "RMD", "EBAY",
    "WAB", "TSCO", "OXY", "HSY", "EFX", "AVB", "EQR", "HIG", "FITB", "KEYS",
    "STT", "CHD", "ANSS", "MTB", "HAL", "BR", "IRM", "DOV", "TER", "TRGP",
    "GPN", "WST", "VICI", "FE", "DTE", "PPL", "CSGP", "NTAP", "WTW", "PHM",
    "LYB", "ES", "TDY", "MPWR", "CLX", "STE", "PTC", "CBOE", "ULTA", "WAT",
    # More S&P 500 members
    "LDOS", "LVS", "MAA", "IFF", "K", "WRB", "HUBB", "BAX", "SNA", "TYL",
    "CAH", "HPE", "RF", "HBAN", "WDC", "LH", "COO", "PKG", "CFG", "LUV",
    "IP", "CNP", "NTRS", "MAS", "J", "POOL", "JBHT", "NRG", "CCL", "SWK",
    "RL", "TRMB", "DGX", "DPZ", "AES", "KIM", "AVY", "AMCR", "ZBRA", "BBY",
    "BRO", "TECH", "CMS", "LNT", "EVRG", "TAP", "ATO", "MKC", "CINF", "WBA",
    "GRMN", "L", "EMN", "FMC", "TXT", "IPG", "ALB", "UDR", "HST", "REG",
    "NDAQ", "PEAK", "CPT", "NI", "ETSY", "BIO", "AIZ", "BWA", "PNR", "CRL",
    "ALLE", "HRL", "IEX", "CE", "MKTX", "WYNN", "BEN", "FRT", "GL", "DVA",
    "PARA", "VTR", "SEE", "CZR", "MTCH", "GNRC", "PAYC", "NWS", "NWSA", "MHK",
    "HAS", "CMA", "ZION", "PNW", "DVN", "RHI", "JKHY", "BXP", "MGM", "FOX",
]


def _fetch_batch_quotes(symbols, batch_size=10):
    """Fetch quotes for multiple symbols using Yahoo Finance.
    
    Returns dict of symbol -> change_pct
    """
    results = {}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        syms_str = ",".join(batch)
        
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms_str}"
        try:
            resp = requests.get(url, timeout=15, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            for quote in data.get("quoteResponse", {}).get("result", []):
                sym = quote.get("symbol", "")
                change_pct = quote.get("regularMarketChangePercent", 0)
                results[sym] = change_pct
        except Exception as e:
            logger.debug("Batch fetch failed for %s: %s", syms_str[:30], e)
            # Fill with zeros for failed symbols
            for sym in batch:
                if sym not in results:
                    results[sym] = 0
        
        # Rate limit: small delay between batches
        time.sleep(0.2)
    
    return results


def _load_cache():
    """Load cached S&P 500 data."""
    try:
        if os.path.exists(CACHE_PATH):
            mtime = os.path.getmtime(CACHE_PATH)
            # Cache valid for 5 minutes
            if time.time() - mtime < 300:
                with open(CACHE_PATH, "r") as f:
                    return json.load(f)
    except Exception:
        pass
    return None


def _save_cache(data):
    """Save S&P 500 data to cache."""
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _change_to_color(change_pct):
    """Convert a percentage change to a red/green color.
    
    Green for positive, red for negative. Brightness = magnitude.
    """
    # Clamp to +/- 5% for color scaling
    clamped = max(-5.0, min(5.0, change_pct))
    intensity = abs(clamped) / 5.0  # 0.0 to 1.0
    
    # Minimum brightness so all stocks are visible
    base = 30
    bright = int(base + intensity * (255 - base))
    
    if change_pct >= 0:
        return (0, bright, 0)  # Green
    else:
        return (bright, 0, 0)  # Red


def _render_heatmap(quotes, symbols):
    """Render the S&P 500 heat map to a PIL Image.
    
    Layout: fills 64x64 grid with stock blocks.
    Top stocks (by list order = market cap) get slightly larger blocks.
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), (5, 5, 5))
    pixels = image.load()
    
    num_stocks = min(len(symbols), len(quotes))
    if num_stocks == 0:
        return image
    
    # Calculate block layout
    # With ~500 stocks on 64x64 (4096 pixels), each stock gets ~8 pixels
    # Top 20 get 3x3 (9px), next 80 get 2x2 (4px), rest get 1x1
    idx = 0
    x, y = 0, 0
    
    for i, sym in enumerate(symbols):
        if y >= HEIGHT:
            break
            
        change = quotes.get(sym, 0)
        color = _change_to_color(change)
        
        # Determine block size based on rank
        if i < 10:
            size = 3  # Top 10: 3x3
        elif i < 50:
            size = 2  # Next 40: 2x2
        else:
            size = 1  # Rest: 1x1
        
        # Draw the block
        for dy in range(size):
            for dx in range(size):
                px, py = x + dx, y + dy
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    pixels[px, py] = color
        
        # Advance position
        x += size
        if x >= WIDTH:
            x = 0
            y += size if size > 1 else 1
            # After big blocks, ensure we don't overlap
            if i < 10:
                if x == 0 and (i + 1) % (WIDTH // 3) == 0:
                    pass  # Natural wrap
    
    return image


def _render_heatmap_grid(quotes, symbols):
    """Simpler grid layout: fill row by row with adaptive block sizes."""
    image = Image.new("RGB", (WIDTH, HEIGHT), (5, 5, 5))
    pixels = image.load()
    
    x, y = 0, 0
    row_height = 1
    
    for i, sym in enumerate(symbols):
        if y >= HEIGHT:
            break
        
        change = quotes.get(sym, 0)
        color = _change_to_color(change)
        
        # Top 10 get 3x3, next 40 get 2x2, rest get 1x1
        if i < 10:
            size = 3
        elif i < 50:
            size = 2
        else:
            size = 1
        
        # Check if block fits in current row
        if x + size > WIDTH:
            x = 0
            y += row_height
            row_height = size
        
        if y + size > HEIGHT:
            break
        
        row_height = max(row_height, size)
        
        # Draw block
        for dy in range(size):
            for dx in range(size):
                px, py = x + dx, y + dy
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    pixels[px, py] = color
        
        x += size
    
    return image


# Background data prefetcher
import threading

_bg_quotes = {}
_bg_lock = threading.Lock()
_bg_last_fetch = 0
_bg_fetching = False


def _background_fetch():
    """Fetch S&P 500 data in background thread."""
    global _bg_quotes, _bg_last_fetch, _bg_fetching
    _bg_fetching = True
    try:
        # Try cache first
        cached = _load_cache()
        if cached:
            with _bg_lock:
                _bg_quotes = cached
                _bg_last_fetch = time.time()
            logger.info("BG: Loaded %d S&P 500 quotes from cache", len(cached))
        
        # Always fetch fresh data in background
        logger.info("BG: Fetching S&P 500 data...")
        fresh = _fetch_batch_quotes(SP500_SYMBOLS)
        if fresh:
            _save_cache(fresh)
            with _bg_lock:
                _bg_quotes = fresh
                _bg_last_fetch = time.time()
            logger.info("BG: Fetched %d S&P 500 quotes", len(fresh))
    except Exception as e:
        logger.error("BG: S&P 500 fetch error: %s", e)
    finally:
        _bg_fetching = False


def _ensure_data():
    """Ensure data is available, trigger background fetch if stale."""
    global _bg_fetching
    now = time.time()
    
    # If data is stale (>5 min) and not already fetching, start background fetch
    if (now - _bg_last_fetch > 300 or not _bg_quotes) and not _bg_fetching:
        t = threading.Thread(target=_background_fetch, daemon=True)
        t.start()
    
    with _bg_lock:
        return dict(_bg_quotes)


# Start prefetch immediately when module is imported
threading.Thread(target=_background_fetch, daemon=True).start()


def run(matrix, duration=60):
    """Run the S&P 500 heat map for the specified duration."""
    start_time = time.time()
    
    try:
        while time.time() - start_time < duration:
            if should_stop():
                break
            # Get latest data (non-blocking, triggers bg fetch if stale)
            quotes = _ensure_data()
            
            if quotes:
                image = _render_heatmap_grid(quotes, SP500_SYMBOLS)
                matrix.SetImage(image)
            else:
                # No data yet, show loading indicator
                from PIL import ImageDraw, ImageFont
                img = Image.new("RGB", (WIDTH, HEIGHT), (5, 5, 5))
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.load_default()
                except Exception:
                    font = None
                draw.text((8, 28), "Loading...", fill=(100, 100, 100), font=font)
                matrix.SetImage(img)
            
            # Refresh display every 2 seconds
            time.sleep(2)
    
    except Exception as e:
        logger.error("Error in SP500 heat map: %s", e, exc_info=True)
    finally:
        try:
            matrix.Clear()
        except Exception:
            pass
