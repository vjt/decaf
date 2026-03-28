"""Parse Schwab Trader API responses into domain models.

Converts Schwab JSON (accounts + transactions) into the same ParsedData
used by the IBKR pipeline. The computation and output layers don't care
which broker the data came from.

Key differences from IBKR:
- Schwab gives JSON, not XML
- No per-lot position endpoint — we reconstruct lots from transactions
- CUSIP instead of ISIN — we convert (US + CUSIP + check digit)
- All amounts in USD (Schwab is a US broker)
- Schwab provides cost basis on sell transactions (we trust their FIFO)
- RSU vest deposits appear as RECEIVE_AND_DELIVER transactions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from decaf.models import (
    AccountInfo,
    CashReportEntry,
    CashTransaction,
    ConversionRate,
    OpenPositionLot,
    Trade,
)
from decaf.parse import ParsedData

logger = logging.getLogger(__name__)


def parse_schwab_data(
    account_json: dict[str, Any],
    transactions_json: list[dict[str, Any]],
    tax_year: int,
) -> ParsedData:
    """Parse Schwab API responses into domain models.

    Args:
        account_json: Response from GET /accounts/{hash}?fields=positions
        transactions_json: Response from GET /accounts/{hash}/transactions
        tax_year: Tax year to filter for
    """
    account = _parse_account_info(account_json)

    # Parse all transactions by type
    trades: list[Trade] = []
    cash_txns: list[CashTransaction] = []

    for txn in transactions_json:
        txn_type = txn.get("type", "")

        if txn_type == "TRADE":
            trade = _parse_trade(txn, account.account_id)
            if trade:
                trades.append(trade)

        elif txn_type == "RECEIVE_AND_DELIVER":
            # RSU vest deposits → treat as BUY trades for lot tracking
            trade = _parse_rsu_deposit(txn, account.account_id)
            if trade:
                trades.append(trade)

        elif txn_type == "DIVIDEND_OR_INTEREST":
            ct = _parse_dividend(txn, account.account_id)
            if ct:
                cash_txns.append(ct)

    # Filter cash transactions to tax year
    cash_txns = [ct for ct in cash_txns if ct.date_time.year == tax_year]

    # Reconstruct open position lots from transaction history
    positions = _reconstruct_lots(trades, account.account_id)

    # Cash report from account balances
    cash_report = _parse_cash_report(account_json)

    # Statement period = tax year boundaries
    statement_from = date(tax_year, 1, 1)
    statement_to = date(tax_year, 12, 31)

    return ParsedData(
        account=account,
        trades=trades,
        positions=positions,
        cash_transactions=cash_txns,
        cash_report=cash_report,
        conversion_rates=[],  # Schwab doesn't provide FX rates; we use ECB
        statement_from=statement_from,
        statement_to=statement_to,
    )


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


def _parse_account_info(account_json: dict[str, Any]) -> AccountInfo:
    """Extract account metadata from Schwab account response."""
    sec = account_json.get("securitiesAccount", {})
    account_number = sec.get("accountNumber", "")

    return AccountInfo(
        account_id=account_number,
        base_currency="USD",
        holder_name="",  # Schwab API doesn't expose holder name
        date_opened=date(2000, 1, 1),  # Not available via API
        country="US",
        broker_name="Charles Schwab",
    )


# ---------------------------------------------------------------------------
# Trades (TRADE transactions)
# ---------------------------------------------------------------------------


def _parse_trade(txn: dict[str, Any], account_id: str) -> Trade | None:
    """Parse a TRADE transaction into a Trade domain model."""
    items = txn.get("transferItems", [])
    if not items:
        return None

    item = items[0]
    instrument = item.get("instrument", {})

    amount = Decimal(str(item.get("amount", 0)))
    price = Decimal(str(item.get("price", 0)))
    cost = Decimal(str(item.get("cost", 0)))
    net_amount = Decimal(str(txn.get("netAmount", 0)))

    # Schwab: negative amount = sell, positive = buy
    is_sell = amount < 0
    buy_sell = "SELL" if is_sell else "BUY"
    quantity = amount  # Keep sign convention (negative for sells)

    # For sells: proceeds = netAmount (positive), cost = FIFO cost basis
    # For buys: proceeds is negative (cash outflow)
    if is_sell:
        proceeds = net_amount
        broker_pnl = net_amount - cost
    else:
        proceeds = -abs(net_amount)
        broker_pnl = Decimal(0)

    cusip = instrument.get("cusip", "")
    isin = cusip_to_isin(cusip) if cusip else ""

    return Trade(
        account_id=account_id,
        asset_category="STK",
        symbol=instrument.get("symbol", ""),
        isin=isin,
        description=instrument.get("description", ""),
        currency="USD",
        fx_rate_to_base=Decimal(0),  # Not provided; we use ECB
        trade_datetime=_parse_schwab_date(txn.get("tradeDate", "")),
        settle_date=_parse_schwab_date(txn.get("settlementDate", "")),
        buy_sell=buy_sell,
        quantity=quantity,
        trade_price=price,
        proceeds=proceeds,
        cost=-cost if is_sell else -abs(cost),  # Negative for sells (IB convention)
        commission=Decimal(0),  # Schwab is commission-free for equities
        commission_currency="USD",
        broker_pnl_realized=broker_pnl,
    )


# ---------------------------------------------------------------------------
# RSU deposits (RECEIVE_AND_DELIVER transactions)
# ---------------------------------------------------------------------------


def _parse_rsu_deposit(txn: dict[str, Any], account_id: str) -> Trade | None:
    """Parse an RSU vest deposit as a BUY trade.

    RECEIVE_AND_DELIVER with positive amount = shares received.
    The cost and price represent the Fair Market Value at vest date,
    which becomes the cost basis for Italian capital gains tax.
    """
    items = txn.get("transferItems", [])
    if not items:
        return None

    item = items[0]
    instrument = item.get("instrument", {})

    amount = Decimal(str(item.get("amount", 0)))
    if amount <= 0:
        # Negative = shares transferred out, not an acquisition
        return None

    price = Decimal(str(item.get("price", 0)))
    cost = Decimal(str(item.get("cost", 0)))

    cusip = instrument.get("cusip", "")
    isin = cusip_to_isin(cusip) if cusip else ""

    trade_date = _parse_schwab_date(txn.get("tradeDate", ""))
    settle_date = _parse_schwab_date(txn.get("settlementDate", ""))

    return Trade(
        account_id=account_id,
        asset_category="STK",
        symbol=instrument.get("symbol", ""),
        isin=isin,
        description=instrument.get("description", txn.get("description", "")),
        currency="USD",
        fx_rate_to_base=Decimal(0),
        trade_datetime=trade_date,
        settle_date=settle_date,
        buy_sell="BUY",
        quantity=amount,
        trade_price=price,
        proceeds=-cost,  # Cash outflow (notional for RSU)
        cost=-cost,      # Negative cost (IB convention for buys)
        commission=Decimal(0),
        commission_currency="USD",
        broker_pnl_realized=Decimal(0),
    )


# ---------------------------------------------------------------------------
# Dividends/Interest (DIVIDEND_OR_INTEREST transactions)
# ---------------------------------------------------------------------------


def _parse_dividend(txn: dict[str, Any], account_id: str) -> CashTransaction | None:
    """Parse a dividend or interest payment into CashTransaction."""
    net_amount = Decimal(str(txn.get("netAmount", 0)))
    if net_amount == 0:
        return None

    trade_date = _parse_schwab_date(txn.get("tradeDate", ""))
    settle_date = _parse_schwab_date(
        txn.get("settlementDate", txn.get("tradeDate", "")),
    )

    description = txn.get("description", "")

    # Schwab separates withholding tax as a separate transaction
    # with negative netAmount. Detect via description.
    desc_lower = description.lower()
    if "withholding" in desc_lower or "tax" in desc_lower:
        tx_type = "Withholding Tax"
    elif "interest" in desc_lower:
        tx_type = "Broker Interest Received"
    else:
        tx_type = "Dividends"

    return CashTransaction(
        account_id=account_id,
        tx_type=tx_type,
        currency="USD",
        fx_rate_to_base=Decimal(0),
        date_time=trade_date,
        settle_date=settle_date,
        amount=net_amount,
        description=description,
    )


# ---------------------------------------------------------------------------
# Open position lots (reconstructed from transactions via FIFO)
# ---------------------------------------------------------------------------


def _reconstruct_lots(
    trades: list[Trade],
    account_id: str,
) -> list[OpenPositionLot]:
    """Reconstruct open position lots from transaction history.

    Schwab's positions endpoint gives aggregated data (no per-lot detail).
    For IVAFE we need per-lot acquisition dates. So we reconstruct:
    1. Collect all acquisitions (BUY trades, including RSU deposits)
    2. Apply sells FIFO to consume the earliest lots first
    3. Remaining lots = current open positions
    """
    # Group by (symbol, ISIN) since that's what FIFO operates on
    lots_by_symbol: dict[str, list[_Lot]] = {}
    sells_by_symbol: dict[str, list[_Sell]] = {}

    for t in sorted(trades, key=lambda x: x.trade_datetime):
        key = t.symbol

        if t.is_buy:
            lots_by_symbol.setdefault(key, []).append(_Lot(
                quantity=abs(t.quantity),
                price=t.trade_price,
                cost_total=abs(t.cost),
                trade_date=t.trade_datetime,
                settle_date=t.settle_date,
                isin=t.isin,
                description=t.description,
                currency=t.currency,
            ))
        elif t.is_sell:
            sells_by_symbol.setdefault(key, []).append(_Sell(
                quantity=abs(t.quantity),
                trade_date=t.trade_datetime,
            ))

    # Apply FIFO: consume lots with sells
    for symbol, sells in sells_by_symbol.items():
        lots = lots_by_symbol.get(symbol, [])
        for sell in sorted(sells, key=lambda s: s.trade_date):
            remaining = sell.quantity
            while remaining > 0 and lots:
                lot = lots[0]
                if lot.quantity <= remaining:
                    remaining -= lot.quantity
                    lots.pop(0)
                else:
                    # Partial consumption
                    lots[0] = _Lot(
                        quantity=lot.quantity - remaining,
                        price=lot.price,
                        cost_total=lot.cost_total * (lot.quantity - remaining) / lot.quantity,
                        trade_date=lot.trade_date,
                        settle_date=lot.settle_date,
                        isin=lot.isin,
                        description=lot.description,
                        currency=lot.currency,
                    )
                    remaining = Decimal(0)

    # Convert remaining lots to OpenPositionLot
    result: list[OpenPositionLot] = []
    for symbol, lots in lots_by_symbol.items():
        for lot in lots:
            if lot.quantity <= 0:
                continue
            result.append(OpenPositionLot(
                account_id=account_id,
                asset_category="STK",
                symbol=symbol,
                isin=lot.isin,
                description=lot.description,
                currency=lot.currency,
                fx_rate_to_base=Decimal(0),
                quantity=lot.quantity,
                mark_price=lot.price,  # Use acquisition price as placeholder
                position_value=lot.quantity * lot.price,
                cost_basis_money=lot.cost_total,
                open_datetime=lot.settle_date,  # Settlement date for IVAFE
            ))

    return result


@dataclass
class _Lot:
    """Internal lot for FIFO reconstruction."""
    quantity: Decimal
    price: Decimal
    cost_total: Decimal
    trade_date: date
    settle_date: date
    isin: str
    description: str
    currency: str


@dataclass
class _Sell:
    """Internal sell for FIFO reconstruction."""
    quantity: Decimal
    trade_date: date


# ---------------------------------------------------------------------------
# Cash report
# ---------------------------------------------------------------------------


def _parse_cash_report(account_json: dict[str, Any]) -> list[CashReportEntry]:
    """Extract cash balance from Schwab account data."""
    sec = account_json.get("securitiesAccount", {})
    balances = sec.get("currentBalances", {})

    cash_balance = Decimal(str(balances.get("cashBalance", 0)))

    return [CashReportEntry(
        currency="USD",
        starting_cash=Decimal(0),  # Not available from single snapshot
        ending_cash=cash_balance,
    )]


# ---------------------------------------------------------------------------
# CUSIP to ISIN conversion
# ---------------------------------------------------------------------------


def cusip_to_isin(cusip: str, country: str = "US") -> str:
    """Convert a 9-character CUSIP to a 12-character ISIN.

    ISIN = country code (2) + CUSIP (9) + check digit (1).
    Check digit uses the Luhn algorithm on the alphanumeric characters
    with A=10, B=11, ..., Z=35.
    """
    if len(cusip) != 9:
        return ""

    base = country + cusip

    # Convert alphanumeric to digits: A=10, B=11, ..., Z=35
    digits = ""
    for ch in base:
        if ch.isdigit():
            digits += ch
        elif ch.isalpha():
            digits += str(ord(ch.upper()) - ord("A") + 10)
        else:
            return ""  # Invalid character

    # Luhn algorithm
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n

    check = (10 - (total % 10)) % 10
    return base + str(check)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_schwab_date(date_str: str) -> date:
    """Parse Schwab's ISO-8601 date format.

    Accepts: "2025-06-15T00:00:00+0000", "2025-06-15", etc.
    """
    if not date_str:
        return date(2000, 1, 1)  # Fallback for missing dates

    # Strip time component if present
    date_part = date_str[:10]
    return datetime.strptime(date_part, "%Y-%m-%d").date()
