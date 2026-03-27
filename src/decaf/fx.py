"""Unified FX rate service.

ECB rates are the PRIMARY source (cambio BCE) — this is what the
Agenzia delle Entrate expects. IB ConversionRates are used for
validation and as a fallback for dates the ECB doesn't cover.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from decaf.models import ConversionRate

logger = logging.getLogger(__name__)

# Flag discrepancies above this threshold (relative)
_DISCREPANCY_THRESHOLD = Decimal("0.005")  # 0.5%


class FxService:
    """Unified FX rate service: ECB primary, IB validation.

    IB rates are indexed by (from_currency, date) and represent the
    rate to convert from_currency → base_currency.

    ECB rates are indexed by (currency, date) and represent
    EUR/currency (1 EUR = rate units of currency). To convert
    X → EUR: eur = amount / rate.

    Both systems ultimately give us the same thing: a way to convert
    a foreign currency amount to EUR.
    """

    def __init__(
        self,
        ib_rates: list[ConversionRate],
        ecb_rates: dict[date, Decimal],
        base_currency: str = "EUR",
    ) -> None:
        self._base_currency = base_currency

        # Index IB rates: (from_currency, date) → rate
        self._ib: dict[tuple[str, date], Decimal] = {}
        for cr in ib_rates:
            self._ib[(cr.from_currency, cr.report_date)] = cr.rate

        # ECB rates: date → EUR/USD rate (we only need USD for now)
        self._ecb = ecb_rates

    def to_eur(self, amount: Decimal, currency: str, d: date) -> Decimal:
        """Convert an amount to EUR using ECB rate (primary).

        Falls back to IB rate if ECB is unavailable for this date.
        Logs a warning if the two sources disagree significantly.
        """
        if currency == "EUR":
            return amount
        if amount == 0:
            return Decimal(0)

        ecb_rate = self._get_ecb_rate(currency, d)
        ib_rate = self._get_ib_rate(currency, d)

        if ecb_rate is not None and ib_rate is not None:
            self._check_discrepancy(currency, d, ecb_rate, ib_rate)

        if ecb_rate is not None:
            # ECB rate: 1 EUR = ecb_rate units of currency
            # So: EUR amount = foreign amount / ecb_rate
            return amount / ecb_rate

        if ib_rate is not None:
            # IB rate: conversion factor to base currency (EUR)
            # For EUR-base accounts: eur_amount = usd_amount * ib_rate
            logger.warning(
                "Using IB rate (no ECB rate) for %s on %s: %s",
                currency, d, ib_rate,
            )
            return amount * ib_rate

        raise ValueError(f"No FX rate available for {currency} on {d}")

    def ecb_rate(self, currency: str, d: date) -> Decimal | None:
        """Get the ECB rate for a currency on a date (with fill-forward)."""
        if currency == "EUR":
            return Decimal("1")
        return self._get_ecb_rate(currency, d)

    def ib_rate(self, currency: str, d: date) -> Decimal | None:
        """Get the IB rate for a currency on a date (with fill-forward)."""
        if currency == "EUR":
            return Decimal("1")
        return self._get_ib_rate(currency, d)

    def _get_ecb_rate(self, currency: str, d: date, max_lookback: int = 5) -> Decimal | None:
        """ECB rate with fill-forward for weekends/holidays."""
        for offset in range(max_lookback + 1):
            rate = self._ecb.get(d - timedelta(days=offset))
            if rate is not None:
                return rate
        return None

    def _get_ib_rate(self, currency: str, d: date, max_lookback: int = 5) -> Decimal | None:
        """IB rate with fill-forward for weekends/holidays."""
        for offset in range(max_lookback + 1):
            rate = self._ib.get((currency, d - timedelta(days=offset)))
            if rate is not None:
                return rate
        return None

    def _check_discrepancy(
        self, currency: str, d: date,
        ecb_rate: Decimal, ib_rate: Decimal,
    ) -> None:
        """Log a warning if ECB and IB rates disagree significantly.

        IB rate is to_base (multiply), ECB is EUR/X (divide).
        To compare: ib gives eur = amount * ib_rate,
                    ecb gives eur = amount / ecb_rate.
        So ib_rate ≈ 1/ecb_rate for EUR-base accounts.
        """
        if ecb_rate == 0:
            return

        # Convert ECB to same basis as IB: 1/ecb_rate
        ecb_as_ib = Decimal("1") / ecb_rate
        if ib_rate == 0:
            return

        relative_diff = abs(ecb_as_ib - ib_rate) / ib_rate
        if relative_diff > _DISCREPANCY_THRESHOLD:
            logger.warning(
                "FX discrepancy for %s on %s: ECB=1/%s (≈%s), IB=%s, diff=%.2f%%",
                currency, d, ecb_rate, ecb_as_ib, ib_rate,
                float(relative_diff * 100),
            )
