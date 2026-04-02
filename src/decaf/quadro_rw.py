"""Quadro RW — Foreign asset monitoring + IVAFE.

Every foreign financial asset held at any point during the tax year
must be reported. IVAFE = 0.2% per annum on market value, pro-rated
by days held (settlement date).

Positions are reconstructed per-lot from trades for the specific tax year.
This is necessary because the broker's position snapshot only shows
today's state, not what was held at a historical year-end.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from decaf.fx import FxService
from decaf.models import CashReportEntry, CashTransaction, OpenPositionLot, RWLine, Trade

logger = logging.getLogger(__name__)

_IVAFE_RATE = Decimal("0.002")  # 0.2% per annum
_Q = Decimal("0.01")


def compute_rw(
    positions: list[OpenPositionLot],
    trades: list[Trade],
    cash_report: list[CashReportEntry],
    cash_transactions: list[CashTransaction],
    fx: FxService,
    tax_year: int,
    mark_prices: dict[str, Decimal] | None = None,
    prior_year_prices: dict[str, Decimal] | None = None,
) -> list[RWLine]:
    """Compute Quadro RW lines with IVAFE for a tax year."""
    year_days = 366 if _is_leap(tax_year) else 365
    year_start = date(tax_year, 1, 1)
    year_end = date(tax_year, 12, 31)
    lines: list[RWLine] = []

    if mark_prices is None:
        mark_prices = {}
    if prior_year_prices is None:
        prior_year_prices = {}

    # Build mark price lookups
    _mark = dict(mark_prices)
    _prior = dict(prior_year_prices)
    for p in positions:
        if p.symbol not in _mark and p.quantity and p.mark_price:
            cost_per_share = p.cost_basis_money / p.quantity
            if abs(cost_per_share - p.mark_price) >= _Q:
                _mark[p.symbol] = p.mark_price

    # --- Reconstruct per-lot holdings from trades ---
    slices = _reconstruct_lot_slices(trades, tax_year)

    for s in slices:
        country = _country_from_isin(s.isin)

        # Skip same-day sell-to-cover (acquired == disposed, 0 holding)
        if s.disposed and s.disposed <= s.acquired:
            continue

        hold_start = max(s.acquired, year_start)
        hold_end = min(s.disposed, year_end) if s.disposed else year_end
        days_held = (hold_end - hold_start).days + 1
        if days_held <= 0:
            continue

        # Initial value
        if s.acquired < year_start:
            # Carried from prior year — val. iniziale = market value at Jan 1
            prior_price = _prior.get(s.symbol, s.cost_price)
            initial = s.quantity * prior_price
            initial_eur = fx.to_eur(initial, s.currency, year_start)
        else:
            # Acquired during year — val. iniziale = acquisition cost
            initial = s.quantity * s.cost_price
            initial_eur = fx.to_eur(initial, s.currency, s.acquired)

        # Final value
        if s.disposed and s.disposed <= year_end:
            # Sold during tax year — final = sell proceeds
            final_eur = fx.to_eur(s.sell_proceeds, s.currency, s.disposed)
        else:
            # Held at year-end — use mark price
            mark = _mark.get(s.symbol, s.cost_price)
            final = s.quantity * mark
            final_eur = fx.to_eur(final, s.currency, year_end)

        ivafe = (final_eur * _IVAFE_RATE * days_held / year_days).quantize(
            _Q, rounding=ROUND_HALF_UP,
        )

        lines.append(RWLine(
            codice_investimento=20,
            isin=s.isin,
            symbol=s.symbol,
            description=f"{s.symbol} ({s.acquired.isoformat()})",
            country=country,
            acquisition_date=s.acquired,
            disposed_date=s.disposed if s.disposed and s.disposed <= year_end else None,
            initial_value_eur=initial_eur.quantize(_Q, ROUND_HALF_UP),
            final_value_eur=final_eur.quantize(_Q, ROUND_HALF_UP),
            days_held=days_held,
            ownership_pct=Decimal("100"),
            ivafe_due=ivafe,
        ))

    # --- Foreign currency cash (codice investimento 1) ---
    _add_cash_lines(lines, cash_report, cash_transactions, fx, tax_year, year_days)

    return lines


# ---------------------------------------------------------------------------
# Lot reconstruction
# ---------------------------------------------------------------------------


@dataclass
class _LotSlice:
    """A portion of a lot with a known lifecycle."""

    symbol: str
    isin: str
    currency: str
    quantity: Decimal
    cost_price: Decimal        # per-share acquisition cost
    acquired: date             # settlement date
    disposed: date | None      # settlement date of sale (None = still held)
    sell_proceeds: Decimal     # total USD proceeds if sold


def _reconstruct_lot_slices(
    trades: list[Trade],
    tax_year: int,
) -> list[_LotSlice]:
    """Build per-lot slices from buy/sell trades for a tax year.

    Each vest/buy creates a lot. Each sell consumes part or all of a lot.
    The consumed portion becomes a "disposed slice", the remainder stays.
    Returns all slices that overlap with the tax year.
    """
    year_start = date(tax_year, 1, 1)
    year_end = date(tax_year, 12, 31)

    # Step 1: Build acquisition lots keyed by (acquisition_date, symbol)
    # acquisition_date = canonical vest date from FMV PDF, same date used
    # by the Year-End Summary's date_acquired for sell lot matching.
    acq_lots: dict[tuple[date, str], _AcqLot] = {}
    for t in trades:
        if not t.is_buy or t.asset_category != "STK":
            continue
        key = (t.acquisition_date, t.symbol)
        if key not in acq_lots:
            acq_lots[key] = _AcqLot(
                symbol=t.symbol, isin=t.isin, currency=t.currency,
                total_qty=Decimal(0), cost_price=t.trade_price,
                acquired=t.settle_date, sells=[],  # settle_date for IVAFE day count
            )
        acq_lots[key].total_qty += t.quantity

    # Step 2: Match sells to lots
    sells = [t for t in trades if t.is_sell and t.asset_category == "STK"]
    sells.sort(key=lambda t: t.settle_date)

    for t in sells:
        acq_date = _extract_acquisition_date(t)
        if acq_date:
            # Schwab: exact lot match via date_acquired in description
            key = (acq_date, t.symbol)
            if key in acq_lots:
                acq_lots[key].sells.append(_SellEvent(
                    quantity=abs(t.quantity),
                    settle_date=t.settle_date,
                    proceeds_per_share=(t.proceeds / abs(t.quantity) if t.quantity else Decimal(0)),
                ))
        else:
            # IBKR: LIFO — most recently acquired lot sold first
            # (Circolare 38/E par. 1.4.1, Istruzioni RW 2025)
            candidates = sorted(
                [v for v in acq_lots.values() if v.symbol == t.symbol and v.remaining > 0],
                key=lambda v: v.acquired, reverse=True,
            )
            remaining = abs(t.quantity)
            pps = t.proceeds / abs(t.quantity) if t.quantity else Decimal(0)
            for lot in candidates:
                if remaining <= 0:
                    break
                consumed = min(lot.remaining, remaining)
                lot.sells.append(_SellEvent(
                    quantity=consumed,
                    settle_date=t.settle_date,
                    proceeds_per_share=pps,
                ))
                remaining -= consumed

    # Step 3: Generate slices from lots
    slices: list[_LotSlice] = []
    for lot in acq_lots.values():
        slices.extend(lot.to_slices(year_end))

    # Step 4: Filter to slices overlapping with tax year
    return [
        s for s in slices
        if s.acquired <= year_end
        and (s.disposed is None or s.disposed >= year_start)
    ]


@dataclass
class _SellEvent:
    quantity: Decimal
    settle_date: date
    proceeds_per_share: Decimal


@dataclass
class _AcqLot:
    """An acquisition lot that may be partially or fully sold."""

    symbol: str
    isin: str
    currency: str
    total_qty: Decimal
    cost_price: Decimal
    acquired: date
    sells: list[_SellEvent] = field(default_factory=list)

    @property
    def remaining(self) -> Decimal:
        sold = sum(s.quantity for s in self.sells)
        return self.total_qty - sold

    def to_slices(self, year_end: date) -> list[_LotSlice]:
        """Split into up to two slices for a tax year:

        1. Portion sold during the year (disposed <= year_end)
        2. Portion still held at year-end (unsold + sold after year-end)
        """
        result: list[_LotSlice] = []

        # Sells within the tax year
        year_sells = [s for s in self.sells if s.settle_date <= year_end]
        if year_sells:
            qty_sold = sum(s.quantity for s in year_sells)
            proceeds = sum(s.quantity * s.proceeds_per_share for s in year_sells)
            last_sell = max(s.settle_date for s in year_sells)
            result.append(_LotSlice(
                symbol=self.symbol,
                isin=self.isin,
                currency=self.currency,
                quantity=qty_sold,
                cost_price=self.cost_price,
                acquired=self.acquired,
                disposed=last_sell,
                sell_proceeds=proceeds,
            ))

        # Portion still held at year-end: total - all sells through year-end
        sold_thru_year = sum(s.quantity for s in self.sells if s.settle_date <= year_end)
        rem = self.total_qty - sold_thru_year
        if rem > 0:
            result.append(_LotSlice(
                symbol=self.symbol,
                isin=self.isin,
                currency=self.currency,
                quantity=rem,
                cost_price=self.cost_price,
                acquired=self.acquired,
                disposed=None,
                sell_proceeds=Decimal(0),
            ))

        return result


def _extract_acquisition_date(sell_trade: Trade) -> date | None:
    """Get the acquisition date for lot matching."""
    if sell_trade.acquisition_date != sell_trade.trade_datetime:
        return sell_trade.acquisition_date
    return None


# ---------------------------------------------------------------------------
# Cash deposits
# ---------------------------------------------------------------------------


def _add_cash_lines(
    lines: list[RWLine],
    cash_report: list[CashReportEntry],
    cash_transactions: list[CashTransaction],
    fx: FxService,
    tax_year: int,
    year_days: int,
) -> None:
    """Add codice 1 lines for foreign currency cash deposits.

    Brokerage cash is a "deposito" → IVAFE 0.2% (not the €34.20
    flat fee for conti correnti).
    """
    year_start = date(tax_year, 1, 1)
    year_end = date(tax_year, 12, 31)

    for cr in cash_report:
        if cr.currency == "EUR":
            continue
        if cr.ending_cash == 0 and cr.starting_cash == 0:
            continue

        # Days held: from first USD activity or Jan 1 if starting balance > 0
        if cr.starting_cash != 0:
            hold_start = year_start
        else:
            first_usd = min(
                (ct.settle_date for ct in cash_transactions
                 if ct.currency == cr.currency and year_start <= ct.settle_date <= year_end),
                default=year_start,
            )
            hold_start = first_usd

        days_held = (year_end - hold_start).days + 1

        final_eur = fx.to_eur(cr.ending_cash, cr.currency, year_end)
        initial_eur = fx.to_eur(cr.starting_cash, cr.currency, year_start)

        ivafe = (final_eur * _IVAFE_RATE * days_held / year_days).quantize(
            _Q, rounding=ROUND_HALF_UP,
        )

        lines.append(RWLine(
            codice_investimento=1,
            isin="",
            symbol=cr.currency,
            description=f"Cash balance ({cr.currency})",
            country="IE",
            acquisition_date=None,
            disposed_date=None,
            initial_value_eur=initial_eur.quantize(_Q, ROUND_HALF_UP),
            final_value_eur=final_eur.quantize(_Q, ROUND_HALF_UP),
            days_held=days_held,
            ownership_pct=Decimal("100"),
            ivafe_due=ivafe,
        ))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _country_from_isin(isin: str) -> str:
    if len(isin) >= 2:
        return isin[:2]
    return ""


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
