"""Layout tests for the stock ticker card.

The 64x64 card packs a price, an absolute change and a percent change into a
handful of 7px rows. Two fields used to collide: the left-aligned absolute
change ran into the right-aligned percent change, and a scale-2 price such as
``$123.45`` (76px) ran straight off the 64px panel. These tests pin the
fit-to-row behaviour so the regression can't come back silently.
"""

import pytest

from src.display._fonts import FONT_5X7, _text_width
from src.display.stock_ticker import (
    BG_COLOR,
    _fit_change_pct,
    _fit_price,
    _render_stock,
    _truncate_industry,
)

# Production call-site budgets (see _render_stock).
PRICE_MAX_WIDTH = 60
ROW_MAX_WIDTH = 62
ROW_GAP = 3

# (symbol, price, change, change_pct, rank)
CASES = [
    ("AAPL", 213.45, 2.31, 1.09, 1),
    ("GOOGL", 1234.56, -123.45, -9.09, 10),
    ("BRK.A", 645000.0, -12345.0, -1.87, 100),
    ("TSLA", 9.99, 4.99, 99.9, 3),
    ("VERYLONGSYM", 1999.99, 1899.99, 1899.9, 100),
    ("XYZ", 0.05, -0.001, -0.02, None),
    ("F", 11.07, -0.05, -0.45, None),
    ("NVDA", 99999.99, 1.0, 0.0, 7),
]


class TestFontCoverage:
    @pytest.mark.parametrize("char", list("$+%#.,-0123456789"))
    def test_ticker_glyphs_exist(self, char):
        """Every glyph the ticker renders must be in the font.

        A missing glyph was silently drawn as blank while _text_width still
        reserved a full cell, so "+1.2%" rendered as "1.2" with mystery gaps.
        """
        assert char in FONT_5X7

    def test_glyphs_fit_five_columns(self):
        """No glyph may set bits outside the 5 columns the metrics assume."""
        for char, rows in FONT_5X7.items():
            assert len(rows) == 7, char
            for row in rows:
                assert 0 <= row <= 0x1F, (char, hex(row))


class TestFitPrice:
    @pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
    def test_price_fits_row(self, case):
        _, price, _, _, _ = case
        dollars, cents, scale = _fit_price(price, PRICE_MAX_WIDTH, scale=2, spacing=1)
        width = _text_width(dollars, scale=scale, spacing=1)
        if cents:
            width += 1 + _text_width(cents, scale=1, spacing=0)
        assert width <= PRICE_MAX_WIDTH, (dollars, cents, scale, width)

    def test_cents_preserved_when_there_is_room(self):
        dollars, cents, scale = _fit_price(213.45, PRICE_MAX_WIDTH)
        assert (dollars, cents) == ("$213", ".45")
        assert scale == 2  # dollars stay large

    def test_large_price_drops_to_scale_one_without_cents(self):
        dollars, cents, scale = _fit_price(645000.0, PRICE_MAX_WIDTH)
        assert dollars == "$645000"
        assert cents == ""
        assert scale == 1

    def test_cents_rounding_never_overflows_into_100(self):
        dollars, cents, _ = _fit_price(9.999, PRICE_MAX_WIDTH)
        assert (dollars, cents) == ("$10", ".00")


class TestFitChangePct:
    @pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
    def test_change_and_pct_never_overlap(self, case):
        _, _, change, pct, _ = case
        change_str, pct_str = _fit_change_pct(
            change, pct, change >= 0, max_width=ROW_MAX_WIDTH
        )
        total = _text_width(pct_str, scale=1, spacing=1)
        if change_str:
            total += ROW_GAP + _text_width(change_str, scale=1, spacing=1)
        assert total <= ROW_MAX_WIDTH, (change_str, pct_str, total)

    def test_percent_always_shown(self):
        """The percent is the headline number and must survive every squeeze."""
        change_str, pct_str = _fit_change_pct(
            1899.99, 1899.9, True, max_width=ROW_MAX_WIDTH
        )
        assert pct_str.endswith("%")
        assert change_str == ""  # absolute change dropped instead of clipped

    def test_small_change_keeps_both_decimals(self):
        """A 5-cent move must never be rounded to "-0.1"."""
        change_str, _ = _fit_change_pct(-0.05, -0.45, False, max_width=ROW_MAX_WIDTH)
        assert change_str == "-0.05"

    def test_sign_only_on_positive(self):
        up_change, up_pct = _fit_change_pct(2.31, 1.09, True, max_width=ROW_MAX_WIDTH)
        assert up_change.startswith("+") and up_pct.startswith("+")
        dn_change, dn_pct = _fit_change_pct(-2.31, -1.09, False, max_width=ROW_MAX_WIDTH)
        assert dn_change.startswith("-") and dn_pct.startswith("-")


class TestTruncateIndustry:
    def test_no_dangling_space_before_ellipsis(self):
        out = _truncate_industry("Consumer Electronics Retail", max_width=58)
        assert ".." in out
        assert " .." not in out

    def test_short_name_untouched(self):
        assert _truncate_industry("BANKS", max_width=58) == "BANKS"


class TestRenderStock:
    @pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
    def test_renders_64x64_without_error(self, case):
        symbol, price, change, pct, rank = case
        quote = {
            "symbol": symbol,
            "price": price,
            "change": change,
            "change_pct": pct,
            "prices": [price * 0.9, price * 1.02, price, price * 1.05],
            "industry": "Consumer Electronics Retail",
        }
        img = _render_stock(quote, tick=5, rank=rank)
        assert img.size == (64, 64)

    @pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
    def test_nothing_bleeds_into_the_edge_columns(self, case):
        """Columns 0 and 63 stay background for every card.

        Every element is budgeted to x=1..62, so a lit outermost column means
        something overflowed its row (a long symbol, a wide rank badge, or a
        price that no longer fits) and is being clipped by the panel instead of
        laid out.
        """
        symbol, price, change, pct, rank = case
        quote = {
            "symbol": symbol,
            "price": price,
            "change": change,
            "change_pct": pct,
            "prices": [price * 0.9, price * 1.02, price, price * 1.05],
            "industry": "Consumer Electronics Retail",
        }
        img = _render_stock(quote, tick=0, rank=rank)
        px = img.load()
        for y in range(64):
            assert px[0, y] == BG_COLOR, f"col 0 lit at y={y}"
            assert px[63, y] == BG_COLOR, f"col 63 lit at y={y}"
