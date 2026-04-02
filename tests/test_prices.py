"""Tests for price fetching — ticker resolution and exchange mapping."""

from __future__ import annotations

from decaf.prices import EXCHANGE_TO_YF, yfinance_ticker


class TestYfinanceTicker:
    """Verify the IBKR exchange -> Yahoo Finance ticker mapping."""

    def test_us_stock_no_suffix(self) -> None:
        assert yfinance_ticker("META", "US30303M1027", "NASDAQ") == "META"
        assert yfinance_ticker("LLY", "US5324571083", "NYSE") == "LLY"

    def test_us_isin_overrides_exchange(self) -> None:
        """US ISIN always returns bare symbol, even with non-US exchange."""
        assert yfinance_ticker("META", "US30303M1027", "LSEETF") == "META"

    def test_lse_etf(self) -> None:
        assert yfinance_ticker("VWRA", "IE00BK5BQT80", "LSEETF") == "VWRA.L"

    def test_xetra(self) -> None:
        assert yfinance_ticker("IGLD", "IE00B4ND3602", "IBIS2") == "IGLD.DE"
        assert yfinance_ticker("VWCE", "IE00BK5BQT80", "IBIS") == "VWCE.DE"

    def test_euronext_paris(self) -> None:
        assert yfinance_ticker("DFND", "IE000JQ8O0Y0", "SBF") == "DFND.PA"

    def test_amsterdam(self) -> None:
        assert yfinance_ticker("IWDA", "IE00B4L5Y983", "AEB") == "IWDA.AS"

    def test_milan(self) -> None:
        assert yfinance_ticker("SWDA", "IE00B4L5Y983", "BVME") == "SWDA.MI"

    def test_swiss(self) -> None:
        assert yfinance_ticker("CSNDX", "IE00B53SZB19", "EBS") == "CSNDX.SW"

    def test_no_exchange_returns_bare(self) -> None:
        """Schwab positions have no exchange — return bare symbol."""
        assert yfinance_ticker("META", "US30303M1027", "") == "META"

    def test_unknown_exchange_returns_bare(self) -> None:
        """Unknown exchange code falls through to bare symbol."""
        assert yfinance_ticker("FOO", "IE12345678", "UNKNOWN") == "FOO"


class TestExchangeMapping:
    """Verify the exchange mapping covers all expected exchanges."""

    def test_us_exchanges_have_no_suffix(self) -> None:
        for exchange in ("NASDAQ", "NYSE", "ARCA", "AMEX", "BATS"):
            assert EXCHANGE_TO_YF[exchange] == "", f"{exchange} should have no suffix"

    def test_european_exchanges_have_suffix(self) -> None:
        expected = {
            "LSEETF": ".L", "LSE": ".L",
            "IBIS": ".DE", "IBIS2": ".DE",
            "AEB": ".AS",
            "SBF": ".PA",
            "BVME": ".MI",
            "EBS": ".SW",
        }
        for exchange, suffix in expected.items():
            assert EXCHANGE_TO_YF[exchange] == suffix, (
                f"{exchange} should map to {suffix}"
            )
