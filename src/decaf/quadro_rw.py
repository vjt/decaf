"""Quadro RW — Foreign asset monitoring + IVAFE.

Every foreign financial asset held at any point during the tax year
must be reported. IVAFE = 0.2% per annum on market value, pro-rated
by days held.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from decaf.fx import FxService
from decaf.models import CashReportEntry, OpenPositionLot, RWLine, Trade


# IVAFE: 0.2% (2 per mille) on securities, fixed EUR 34.20 on bank deposits
_IVAFE_RATE = Decimal("0.002")
_IVAFE_FIXED_DEPOSIT = Decimal("34.20")


def compute_rw(
    positions: list[OpenPositionLot],
    trades: list[Trade],
    cash_report: list[CashReportEntry],
    fx: FxService,
    tax_year: int,
) -> list[RWLine]:
    """Compute Quadro RW lines with IVAFE for a tax year."""
    year_days = 366 if _is_leap(tax_year) else 365
    year_end = date(tax_year, 12, 31)
    lines: list[RWLine] = []

    # --- Securities (codice investimento 20) ---
    # Each lot in OpenPositions that was opened during or before the tax year
    for lot in positions:
        if lot.open_datetime.year > tax_year:
            continue

        country = _country_from_isin(lot.isin)

        # Days held: from open date (or Jan 1 if opened in prior year) to Dec 31
        hold_start = max(lot.open_datetime, date(tax_year, 1, 1))
        hold_end = year_end
        days_held = (hold_end - hold_start).days + 1

        # Initial value: cost basis at acquisition, converted to EUR
        initial_eur = fx.to_eur(lot.cost_basis_money, lot.currency, lot.open_datetime)

        # Final value: market value at year end, converted to EUR
        final_eur = fx.to_eur(lot.position_value, lot.currency, year_end)

        # IVAFE: 0.2% of final value, pro-rated
        ivafe = (final_eur * _IVAFE_RATE * days_held / year_days).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )

        lines.append(RWLine(
            codice_investimento=20,
            isin=lot.isin,
            symbol=lot.symbol,
            description=lot.description,
            country=country,
            initial_value_eur=initial_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            final_value_eur=final_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            days_held=days_held,
            ownership_pct=Decimal("100"),
            ivafe_due=ivafe,
        ))

    # --- Positions sold during the year (no longer in OpenPositions) ---
    # These still need RW reporting for the days they were held
    sold_symbols = _find_sold_positions(trades, positions, tax_year)
    for symbol, isin, currency, sell_date, first_buy_date in sold_symbols:
        country = _country_from_isin(isin)
        hold_start = max(first_buy_date, date(tax_year, 1, 1))
        hold_end = sell_date
        days_held = (hold_end - hold_start).days + 1
        if days_held <= 0:
            continue

        # For sold positions, initial = cost basis, final = sale proceeds
        sell_trades = [
            t for t in trades
            if t.symbol == symbol and t.is_sell
            and t.trade_datetime.year == tax_year
        ]
        if not sell_trades:
            continue

        total_proceeds = sum(t.proceeds for t in sell_trades)
        total_cost = sum(abs(t.cost) for t in sell_trades)

        initial_eur = fx.to_eur(total_cost, currency, first_buy_date)
        final_eur = fx.to_eur(total_proceeds, currency, sell_date)

        ivafe = (final_eur * _IVAFE_RATE * days_held / year_days).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )

        lines.append(RWLine(
            codice_investimento=20,
            isin=isin,
            symbol=symbol,
            description=sell_trades[0].description,
            country=country,
            initial_value_eur=initial_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            final_value_eur=final_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            days_held=days_held,
            ownership_pct=Decimal("100"),
            ivafe_due=ivafe,
        ))

    # --- Foreign currency cash (codice investimento 1) ---
    # Brokerage cash is a "deposito" (not a conto corrente), so IVAFE
    # is 0.2% like securities — NOT the €34.20 flat fee which applies
    # only to actual bank accounts (conti correnti e libretti di risparmio).
    for cr in cash_report:
        if cr.currency == "EUR":
            continue
        if cr.ending_cash == 0 and cr.starting_cash == 0:
            continue

        final_eur = fx.to_eur(cr.ending_cash, cr.currency, year_end)
        initial_eur = fx.to_eur(cr.starting_cash, cr.currency, date(tax_year, 1, 1))

        ivafe = (final_eur * _IVAFE_RATE * year_days / year_days).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )

        lines.append(RWLine(
            codice_investimento=1,
            isin="",
            symbol=cr.currency,
            description=f"Cash balance ({cr.currency})",
            country="IE",  # IBKR Ireland
            initial_value_eur=initial_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            final_value_eur=final_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            days_held=year_days,
            ownership_pct=Decimal("100"),
            ivafe_due=ivafe,
        ))

    return lines


def _find_sold_positions(
    trades: list[Trade],
    positions: list[OpenPositionLot],
    tax_year: int,
) -> list[tuple[str, str, str, date, date]]:
    """Find symbols that were fully sold during the tax year.

    Returns (symbol, isin, currency, last_sell_date, first_buy_date).
    Only includes symbols NOT present in open positions.
    """
    open_symbols = {(p.symbol, p.currency) for p in positions}

    # Find sell trades for symbols no longer held
    sells_by_sym: dict[tuple[str, str], list[Trade]] = {}
    buys_by_sym: dict[tuple[str, str], list[Trade]] = {}

    for t in trades:
        if t.asset_category != "STK":
            continue
        key = (t.symbol, t.currency)
        if key in open_symbols:
            continue  # still held, already covered above
        if t.is_sell and t.trade_datetime.year == tax_year:
            sells_by_sym.setdefault(key, []).append(t)
        if t.is_buy:
            buys_by_sym.setdefault(key, []).append(t)

    result = []
    for (sym, cur), sell_trades in sells_by_sym.items():
        buy_trades = buys_by_sym.get((sym, cur), [])
        first_buy = min(t.settle_date for t in buy_trades) if buy_trades else sell_trades[0].settle_date
        last_sell = max(t.settle_date for t in sell_trades)
        isin = sell_trades[0].isin
        result.append((sym, isin, cur, last_sell, first_buy))

    return result


def _country_from_isin(isin: str) -> str:
    """Extract country code from ISIN prefix."""
    if len(isin) >= 2:
        return isin[:2]
    return ""


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
