"""SQLite cache for ECB reference rates.

Wraps ecb-fx-rates client with persistent local storage.
Fetches once, serves from cache on subsequent runs.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import aiohttp
import aiosqlite
from ecb_fx_rates import EcbDailyRates, EcbRatesClient

logger = logging.getLogger(__name__)

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS ecb_rates (
    currency  TEXT NOT NULL,
    rate_date TEXT NOT NULL,
    rate      TEXT NOT NULL,
    PRIMARY KEY (currency, rate_date)
);
"""


class EcbRateCache:
    """SQLite-backed cache for ECB daily reference rates."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(str(self._db_path))
        await db.executescript(_SCHEMA)
        self._db = db

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def __aenter__(self) -> EcbRateCache:
        await self.open()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def ensure_year(self, session: aiohttp.ClientSession, year: int) -> int:
        """Ensure we have ECB rates cached for the given year.

        Returns the number of rate-days stored. Skips fetch if the year
        is already complete in the cache (has a Dec 31 or Dec 30 entry).
        """
        assert self._db is not None

        if await self._year_complete(year):
            count = await self._count_year(year)
            logger.info("ECB rates for %d already cached (%d days)", year, count)
            return count

        client = EcbRatesClient()
        days = await client.fetch_year(session, year)

        if not days:
            logger.warning("ECB returned no rates for year %d", year)
            return 0

        await self._store(days)
        count = await self._count_year(year)
        logger.info("Cached %d ECB rate-days for %d", count, year)
        return count

    async def get_rate(self, currency: str, d: date) -> Decimal | None:
        """Get the ECB rate for a currency on an exact date."""
        if currency == "EUR":
            return Decimal("1")
        assert self._db is not None

        cursor = await self._db.execute(
            "SELECT rate FROM ecb_rates WHERE currency = ? AND rate_date = ?",
            (currency, d.isoformat()),
        )
        row = await cursor.fetchone()
        return Decimal(row[0]) if row else None

    async def get_rate_fill_forward(
        self,
        currency: str,
        d: date,
        max_lookback: int = 5,
    ) -> Decimal | None:
        """Get the ECB rate, looking back up to N days for weekends/holidays."""
        if currency == "EUR":
            return Decimal("1")
        assert self._db is not None

        earliest = d - timedelta(days=max_lookback)
        cursor = await self._db.execute(
            "SELECT rate FROM ecb_rates "
            "WHERE currency = ? AND rate_date <= ? AND rate_date >= ? "
            "ORDER BY rate_date DESC LIMIT 1",
            (currency, d.isoformat(), earliest.isoformat()),
        )
        row = await cursor.fetchone()
        return Decimal(row[0]) if row else None

    async def get_dec31_rate(self, currency: str, year: int) -> Decimal:
        """Get the ECB rate for Dec 31 (or last available rate of the year).

        This is the rate used for Quadro RW year-end valuations.
        For incomplete years (running mid-year), falls back to the latest
        available rate instead of crashing.
        Raises ValueError if no rate at all is found for the year.
        """
        # Try Dec 31 with normal lookback first
        rate = await self.get_rate_fill_forward(currency, date(year, 12, 31))
        if rate is not None:
            return rate

        # Incomplete year — use the latest available rate
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT rate FROM ecb_rates "
            "WHERE currency = ? AND rate_date >= ? AND rate_date <= ? "
            "ORDER BY rate_date DESC LIMIT 1",
            (currency, f"{year}-01-01", f"{year}-12-31"),
        )
        row = await cursor.fetchone()
        if row is not None:
            return Decimal(row[0])

        raise ValueError(f"No ECB rate found for {currency} in {year}")

    async def get_all_rates_for_year(
        self,
        currency: str,
        year: int,
    ) -> dict[date, Decimal]:
        """Get all cached rates for a currency in a year.

        Returns a dict mapping date → rate for every ECB publication day.
        """
        if currency == "EUR":
            return {}
        assert self._db is not None

        cursor = await self._db.execute(
            "SELECT rate_date, rate FROM ecb_rates "
            "WHERE currency = ? AND rate_date >= ? AND rate_date <= ? "
            "ORDER BY rate_date",
            (currency, f"{year}-01-01", f"{year}-12-31"),
        )
        rows = await cursor.fetchall()
        return {date.fromisoformat(r[0]): Decimal(r[1]) for r in rows}

    # -------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------

    async def _year_complete(self, year: int) -> bool:
        """Check if we have rates near Dec 31 for the year."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM ecb_rates WHERE rate_date >= ? AND rate_date <= ?",
            (f"{year}-12-28", f"{year}-12-31"),
        )
        row = await cursor.fetchone()
        return row is not None and row[0] > 0

    async def _count_year(self, year: int) -> int:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT COUNT(DISTINCT rate_date) FROM ecb_rates "
            "WHERE rate_date >= ? AND rate_date <= ?",
            (f"{year}-01-01", f"{year}-12-31"),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def _store(self, days: list[EcbDailyRates]) -> None:
        assert self._db is not None
        rows = [
            (currency, day.date.isoformat(), str(rate))
            for day in days
            for currency, rate in day.rates.items()
        ]
        await self._db.executemany(
            "INSERT OR REPLACE INTO ecb_rates (currency, rate_date, rate) VALUES (?, ?, ?)",
            rows,
        )
        await self._db.commit()
