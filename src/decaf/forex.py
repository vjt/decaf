"""Forex threshold analysis (art. 67(1)(c-ter) TUIR).

Reconstructs the daily USD balance for every calendar day of the tax year,
converts to EUR, and checks whether the balance exceeded €51,645.69 for
at least 7 consecutive Italian business days.

If the threshold is breached, ALL forex gains/losses for the year are taxable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from decaf.fx import FxService
from decaf.holidays import is_business_day, italian_holidays
from decaf.models import CashTransaction, ForexDayRecord, Trade

logger = logging.getLogger(__name__)

THRESHOLD_EUR = Decimal("51645.69")
MIN_CONSECUTIVE_DAYS = 7


@dataclass(frozen=True, slots=True)
class ForexAnalysis:
    """Result of the forex threshold analysis."""

    threshold_breached: bool
    max_consecutive_business_days: int
    first_breach_date: date | None
    daily_records: list[ForexDayRecord]


def analyze_forex_threshold(
    trades: list[Trade],
    cash_transactions: list[CashTransaction],
    fx: FxService,
    tax_year: int,
    threshold_eur: Decimal = THRESHOLD_EUR,
    min_consecutive_days: int = MIN_CONSECUTIVE_DAYS,
) -> ForexAnalysis:
    """Run the full forex threshold analysis for a tax year."""
    holidays = italian_holidays(tax_year)

    # Step 1: reconstruct daily USD balance
    daily_usd = _reconstruct_daily_usd_balance(trades, cash_transactions, tax_year)

    # Step 2: convert to EUR and build daily records
    records: list[ForexDayRecord] = []
    start = date(tax_year, 1, 1)
    end = date(tax_year, 12, 31)
    current = start

    while current <= end:
        usd_balance = daily_usd.get(current, Decimal(0))
        biz_day = is_business_day(current, holidays)

        # Convert USD balance to EUR using ECB rate
        if usd_balance != 0:
            ecb_rate = fx.ecb_rate("USD", current)
            if ecb_rate and ecb_rate != 0:
                eur_equiv = usd_balance / ecb_rate
                fx_rate = ecb_rate
            else:
                # Fallback to IB rate
                ib_rate = fx.ib_rate("USD", current)
                if ib_rate and ib_rate != 0:
                    eur_equiv = usd_balance * ib_rate
                    fx_rate = ib_rate
                else:
                    eur_equiv = Decimal(0)
                    fx_rate = Decimal(0)
        else:
            eur_equiv = Decimal(0)
            fx_rate = Decimal(0)

        records.append(ForexDayRecord(
            date=current,
            usd_balance=usd_balance,
            eur_equivalent=eur_equiv,
            fx_rate=fx_rate,
            is_business_day=biz_day,
            above_threshold=eur_equiv > threshold_eur,
        ))
        current += timedelta(days=1)

    # Step 3: find max consecutive business days above threshold
    max_run, first_breach = _find_max_consecutive_run(records)

    breached = max_run >= min_consecutive_days

    if breached:
        logger.info(
            "Forex threshold BREACHED: %d consecutive business days above €%s "
            "(first breach: %s)",
            max_run, threshold_eur, first_breach,
        )
    else:
        logger.info(
            "Forex threshold NOT breached: max %d consecutive business days "
            "(need %d)",
            max_run, min_consecutive_days,
        )

    return ForexAnalysis(
        threshold_breached=breached,
        max_consecutive_business_days=max_run,
        first_breach_date=first_breach,
        daily_records=records,
    )


def _reconstruct_daily_usd_balance(
    trades: list[Trade],
    cash_transactions: list[CashTransaction],
    tax_year: int,
) -> dict[date, Decimal]:
    """Reconstruct the USD cash balance for every day of the tax year.

    Events that affect the USD balance (applied on settlement date):
    - Deposits/withdrawals in USD
    - Interest credits in USD
    - Withholding tax debits in USD
    - Fees in USD
    - Stock trades in USD: buying USD stock decreases USD cash,
      selling USD stock increases USD cash
    - Forex conversions: EUR.USD buy = acquire EUR, spend USD;
      EUR.USD sell = acquire USD, spend EUR

    The balance is carried forward on days with no activity.
    """
    # Collect all USD-affecting events keyed by settlement date
    events: dict[date, Decimal] = {}

    def _add(d: date, amount: Decimal) -> None:
        events[d] = events.get(d, Decimal(0)) + amount

    # Cash transactions in USD (interest, WHT, deposits, fees)
    for ct in cash_transactions:
        if ct.currency == "USD" and ct.settle_date.year == tax_year:
            _add(ct.settle_date, ct.amount)

    # Stock trades in USD (settlement affects cash)
    for t in trades:
        if t.settle_date.year != tax_year:
            continue

        if t.asset_category == "STK" and t.currency == "USD":
            # BUY: proceeds is negative (cash outflow), commission is negative
            # SELL: proceeds is positive (cash inflow), commission is negative
            _add(t.settle_date, t.proceeds + t.ib_commission)

        elif t.asset_category == "CASH" and "USD" in t.symbol:
            # Forex: EUR.USD
            # BUY EUR.USD: buying EUR with USD → USD decreases
            #   proceeds is negative USD amount
            # SELL EUR.USD: selling EUR for USD → USD increases
            #   proceeds is positive USD amount
            if t.currency == "USD":
                _add(t.settle_date, t.proceeds + t.ib_commission)

    # Build daily balance with carry-forward
    start = date(tax_year, 1, 1)
    end = date(tax_year, 12, 31)
    daily: dict[date, Decimal] = {}
    balance = Decimal(0)
    current = start

    while current <= end:
        balance += events.get(current, Decimal(0))
        daily[current] = balance
        current += timedelta(days=1)

    return daily


def _find_max_consecutive_run(
    records: list[ForexDayRecord],
) -> tuple[int, date | None]:
    """Find the longest run of consecutive business days above threshold.

    Returns (max_run_length, first_breach_start_date).
    """
    max_run = 0
    current_run = 0
    max_run_start: date | None = None
    current_run_start: date | None = None

    for rec in records:
        if not rec.is_business_day:
            continue

        if rec.above_threshold:
            current_run += 1
            if current_run == 1:
                current_run_start = rec.date
            if current_run > max_run:
                max_run = current_run
                max_run_start = current_run_start
        else:
            current_run = 0
            current_run_start = None

    return max_run, max_run_start
