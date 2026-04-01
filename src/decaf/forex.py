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
from decaf.models import CashTransaction, ForexDayRecord, Trade, UsdEvent

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
    usd_events: list[UsdEvent]


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

    # Step 1: reconstruct daily USD balance + event timeline
    daily_usd, usd_events = _reconstruct_daily_usd_balance(trades, cash_transactions, tax_year)

    # Step 2: get the Jan 1 ECB rate (fixed for the whole year per law)
    # Art. 67(1)(c-ter) TUIR: threshold checked against the rate
    # "vigente all'inizio del periodo di riferimento" (Jan 1 rate).
    # Jan 1 is a holiday, so we use the last available rate before it.
    jan1_rate = fx.ecb_rate("USD", date(tax_year, 1, 1))
    if jan1_rate is None or jan1_rate == 0:
        logger.warning("No ECB rate for Jan 1 %d — threshold check may be inaccurate", tax_year)
        jan1_rate = Decimal("1")  # fallback, will warn

    logger.info("Forex threshold: using Jan 1 %d ECB rate EUR/USD = %s", tax_year, jan1_rate)

    # Step 3: convert to EUR using fixed Jan 1 rate and build daily records
    records: list[ForexDayRecord] = []
    start = date(tax_year, 1, 1)
    end = date(tax_year, 12, 31)
    current = start

    while current <= end:
        usd_balance = daily_usd.get(current, Decimal(0))
        biz_day = is_business_day(current, holidays)

        # Convert USD balance to EUR using fixed Jan 1 rate
        if usd_balance != 0:
            eur_equiv = usd_balance / jan1_rate
            fx_rate = jan1_rate
        else:
            eur_equiv = Decimal(0)
            fx_rate = jan1_rate

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
        usd_events=usd_events,
    )


def _reconstruct_daily_usd_balance(
    trades: list[Trade],
    cash_transactions: list[CashTransaction],
    tax_year: int,
) -> tuple[dict[date, Decimal], list[UsdEvent]]:
    """Reconstruct the USD cash balance for every day of the tax year.

    Returns (daily_balance, usd_events) where usd_events is the list
    of individual USD cash flow events for the timeline display.

    Includes carry-over from prior years: ALL USD events from ALL years
    are replayed to compute the correct opening balance on Jan 1.
    """
    # Collect individual events with descriptions
    raw_events: list[tuple[date, Decimal, str]] = []

    for ct in cash_transactions:
        if ct.currency == "USD":
            raw_events.append((
                ct.settle_date, ct.amount,
                f"{ct.tx_type}: {ct.description} [{ct.account_id}]",
            ))

    # Track which accounts have "Sell Proceeds" cash transactions
    # (Schwab — sells are already captured as cash txns including sell-to-cover)
    accounts_with_sell_proceeds = {
        ct.account_id for ct in cash_transactions
        if ct.tx_type == "Sell Proceeds"
    }

    for t in trades:
        if t.asset_category == "STK" and t.currency == "USD":
            # Skip RSU vests: shares appear from equity award, no cash moves.
            if t.is_buy and t.proceeds == t.cost and t.commission == 0:
                continue
            # Skip Schwab sells — proceeds already captured as "Sell Proceeds"
            # cash transactions (which include sell-to-cover amounts).
            if t.account_id in accounts_with_sell_proceeds:
                continue
            net = t.proceeds + t.commission
            raw_events.append((
                t.settle_date, net,
                f"{t.buy_sell} {t.symbol} qty={t.quantity} [{t.account_id}]",
            ))
        elif t.asset_category == "CASH" and "USD" in t.symbol:
            if t.currency == "USD":
                net = t.proceeds + t.commission
                raw_events.append((
                    t.settle_date, net,
                    f"FX {t.buy_sell} {t.symbol} qty={t.quantity} [{t.account_id}]",
                ))

    raw_events.sort(key=lambda e: e[0])

    # Build event list with running balance
    start_year = date(tax_year, 1, 1)
    end_year = date(tax_year, 12, 31)
    balance = Decimal(0)
    usd_events: list[UsdEvent] = []

    # Carry-over from prior years
    for d, amt, desc in raw_events:
        if d >= start_year:
            break
        balance += amt

    if balance != 0:
        logger.info("USD carry-over balance on %s: %.2f", start_year, float(balance))
        usd_events.append(UsdEvent(
            date=start_year, amount=Decimal(0), balance=balance,
            description="Riporto da anni precedenti",
        ))

    if balance < 0:
        logger.warning(
            "Negative USD carry-over (%.2f) — missing prior-year data "
            "(sell-to-cover from vests or earlier transactions?)",
            float(balance),
        )

    # Tax year events
    for d, amt, desc in raw_events:
        if d < start_year:
            continue
        if d > end_year:
            break
        balance += amt
        usd_events.append(UsdEvent(date=d, amount=amt, balance=balance, description=desc))

    # Build daily balance dict with carry-forward
    daily: dict[date, Decimal] = {}
    # Re-derive from events
    day_balance = usd_events[0].balance - usd_events[0].amount if usd_events else Decimal(0)
    # Actually easier: replay from the carry-over
    agg_events: dict[date, Decimal] = {}
    for d, amt, desc in raw_events:
        agg_events[d] = agg_events.get(d, Decimal(0)) + amt

    carry_over = sum(amt for d, amt in agg_events.items() if d < start_year)
    day_bal = carry_over
    current = start_year
    while current <= end_year:
        day_bal += agg_events.get(current, Decimal(0))
        daily[current] = day_bal
        current += timedelta(days=1)

    return daily, usd_events

    # Build daily balance for tax year with carry-forward
    daily: dict[date, Decimal] = {}
    current = start_year
    while current <= end_year:
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
