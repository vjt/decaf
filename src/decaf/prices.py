"""Year-end mark prices from Yahoo Finance.

Fetches closing prices for IVAFE valuation. Uses yfinance (imported lazily
because it's slow to load).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal


class PriceFetchError(Exception):
    """Raised when year-end price fetching fails for one or more symbols."""

    def __init__(self, failed_symbols: list[str]) -> None:
        self.failed_symbols = failed_symbols
        msg = (
            f"Failed to fetch year-end prices for: {', '.join(failed_symbols)}. "
            f"Cannot compute IVAFE without market prices."
        )
        super().__init__(msg)


# IBKR listingExchange -> Yahoo Finance suffix
EXCHANGE_TO_YF: dict[str, str] = {
    # US exchanges
    "NASDAQ": "",
    "NYSE": "",
    "ARCA": "",
    "AMEX": "",
    "BATS": "",
    # London
    "LSEETF": ".L",
    "LSE": ".L",
    # XETRA
    "IBIS": ".DE",
    "IBIS2": ".DE",
    # Amsterdam
    "AEB": ".AS",
    # Paris
    "SBF": ".PA",
    # Milan
    "BVME": ".MI",
    # Swiss
    "EBS": ".SW",
}


def yfinance_ticker(symbol: str, isin: str, exchange: str) -> str:
    """Map broker symbol + exchange to Yahoo Finance ticker.

    US stocks (ISIN US*) need no suffix. Non-US stocks use the IBKR
    listingExchange to determine the correct Yahoo Finance suffix.
    """
    if isin[:2] == "US":
        return symbol
    if exchange:
        suffix = EXCHANGE_TO_YF.get(exchange, "")
        if suffix:
            return f"{symbol}{suffix}"
    return symbol


def fetch_year_end_prices(
    symbols_info: dict[str, tuple[str, str, str]],
    year_end: date,
) -> dict[str, Decimal]:
    """Fetch closing prices on or before year_end from Yahoo Finance.

    Args:
        symbols_info: {symbol: (currency, isin, listing_exchange)}
        year_end: Date to fetch prices for

    Returns:
        {symbol: closing_price} in the symbol's native currency

    Raises:
        PriceFetchError: if any symbol fails -- missing price = wrong IVAFE
    """
    import yfinance as yf

    start = year_end - timedelta(days=10)
    end = year_end + timedelta(days=1)

    prices: dict[str, Decimal] = {}
    failed: list[str] = []

    for symbol, (currency, isin, exchange) in symbols_info.items():
        ticker_id = yfinance_ticker(symbol, isin, exchange)
        try:
            ticker = yf.Ticker(ticker_id)
            # auto_adjust=False: raw close, not retroactively adjusted for
            # dividends. IVAFE needs the actual market value at 31/12 as
            # published, not a figure that keeps shrinking every time the
            # company declares a future dividend.
            hist = ticker.history(
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=False,
            )
            if hist.empty:
                failed.append(f"{symbol} (tried {ticker_id})")
                continue
            last_close = float(hist["Close"].iloc[-1])
            prices[symbol] = Decimal(str(last_close)).quantize(Decimal("0.01"))
            ccy = "\u20ac" if currency == "EUR" else "$"
            print(f"  {symbol} ({ticker_id}) year-end close: {ccy}{prices[symbol]}")
        except Exception as exc:
            failed.append(f"{symbol} ({ticker_id}): {exc}")

    if failed:
        raise PriceFetchError(failed)

    return prices
