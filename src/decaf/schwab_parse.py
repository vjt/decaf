"""Parse Schwab data from three sources into domain models.

Three input files, each with its job:
1. Year-End Summary PDF  → realized gains/losses (Quadro RT)
2. Annual Withholding PDF → vest FMVs for open positions (Quadro RW/IVAFE)
3. Transaction JSON       → dividends + withholding tax (Quadro RL)

No FIFO guessing — Schwab tells us the exact per-lot cost basis.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from decaf.models import (
    AccountInfo,
    CashReportEntry,
    CashTransaction,
    OpenPositionLot,
    Trade,
)
from decaf.parse import ParsedData
from decaf.schwab_gains_pdf import RealizedLot, parse_realized_gains
from decaf.schwab_vest_pdf import parse_vest_fmvs

logger = logging.getLogger(__name__)

_META_CUSIP = "30303M102"


def parse_schwab(
    json_path: Path,
    gains_pdfs: list[Path],
    vest_pdfs: list[Path],
    account_id: str = "",
) -> ParsedData:
    """Parse all Schwab sources into unified domain models.

    Args:
        json_path: Transaction JSON export (for dividends/WHT)
        gains_pdfs: Year-End Summary PDFs (for realized gains)
        vest_pdfs: Annual Withholding Statement PDFs (for vest FMVs)
        account_id: Override account ID (extracted from filename if empty)
    """
    # --- Account ID from filename ---
    if not account_id:
        match = re.search(r"XXX(\d+)", json_path.name)
        account_id = f"XXX{match.group(1)}" if match else "schwab"

    # --- Parse each source ---
    realized_lots = parse_realized_gains(gains_pdfs)
    vest_fmvs = parse_vest_fmvs(vest_pdfs)
    raw_json = json.loads(json_path.read_text())
    json_txns = raw_json.get("BrokerageTransactions", [])

    from_date = _parse_schwab_date(raw_json.get("FromDate", ""))
    to_date = _parse_schwab_date(raw_json.get("ToDate", ""))

    # --- Realized gains → Trade (sells with exact cost basis) ---
    trades: list[Trade] = []
    for lot in realized_lots:
        trades.append(_lot_to_trade(lot, account_id))

    # --- Vest FMVs + JSON vest entries → Trade (buys for open positions) ---
    for txn in json_txns:
        if txn.get("Action") == "Stock Plan Activity":
            trade = _parse_vest(txn, account_id, vest_fmvs)
            if trade:
                trades.append(trade)

    # --- JSON dividends + WHT + wire transfers → CashTransaction ---
    cash_txns: list[CashTransaction] = []
    cash_balance = Decimal(0)
    for txn in json_txns:
        action = txn.get("Action", "")
        if action == "Qualified Dividend":
            ct = _parse_dividend(txn, account_id)
            if ct:
                cash_txns.append(ct)
                cash_balance += ct.amount
        elif action == "NRA Tax Adj":
            ct = _parse_wht(txn, account_id)
            if ct:
                cash_txns.append(ct)
                cash_balance += ct.amount
        elif action in ("Wire Sent", "Wire Funds Sent", "MoneyLink Transfer"):
            ct = _parse_wire_transfer(txn, account_id)
            if ct:
                cash_txns.append(ct)
                cash_balance += ct.amount
        elif action == "Sell":
            # Sell proceeds as USD cash inflow (includes sell-to-cover from
            # RSU vests). RT gains come from Year-End Summary, not here.
            ct = _parse_sell_proceeds(txn, account_id)
            if ct:
                cash_txns.append(ct)
                cash_balance += ct.amount
        elif action in ("Service Fee", "Misc Cash Entry"):
            ct = _parse_service_fee(txn, account_id)
            if ct:
                cash_txns.append(ct)
                cash_balance += ct.amount

    # --- Open positions from vests minus sells ---
    positions = _compute_open_positions(trades, account_id)

    account = AccountInfo(
        account_id=account_id,
        base_currency="USD",
        holder_name="",
        date_opened=from_date,
        country="US",
        broker_name="Charles Schwab",
    )

    cash_report = [CashReportEntry(
        currency="USD",
        starting_cash=Decimal(0),
        ending_cash=max(cash_balance, Decimal(0)),
    )]

    return ParsedData(
        account=account,
        trades=trades,
        positions=positions,
        cash_transactions=cash_txns,
        cash_report=cash_report,
        conversion_rates=[],
        statement_from=from_date,
        statement_to=to_date,
    )


# ---------------------------------------------------------------------------
# Realized lots → Trade
# ---------------------------------------------------------------------------


def _lot_to_trade(lot: RealizedLot, account_id: str) -> Trade:
    """Convert a RealizedLot from the Year-End Summary to a Trade."""
    isin = cusip_to_isin(lot.cusip) if lot.cusip else ""
    settle_date = lot.date_sold + timedelta(days=1)  # T+1

    return Trade(
        account_id=account_id,
        asset_category="STK",
        symbol=lot.symbol,
        isin=isin,
        description=f"{lot.symbol} (acquired {lot.date_acquired})",
        currency="USD",
        fx_rate_to_base=Decimal(0),
        trade_datetime=lot.date_sold,
        settle_date=settle_date,
        buy_sell="SELL",
        quantity=-lot.quantity,
        trade_price=(lot.proceeds / lot.quantity).quantize(Decimal("0.0001")),
        proceeds=lot.proceeds,
        cost=-lot.cost_basis,
        commission=Decimal(0),
        commission_currency="USD",
        broker_pnl_realized=lot.gain_loss,
        listing_exchange="",
        acquisition_date=lot.date_acquired,
    )


# ---------------------------------------------------------------------------
# Vest entries → Trade (buys)
# ---------------------------------------------------------------------------


def _parse_vest(
    txn: dict[str, Any],
    account_id: str,
    vest_fmvs: dict[date, Decimal],
) -> Trade | None:
    """Parse a Stock Plan Activity (RSU vest) as a BUY trade."""
    quantity = _parse_quantity(txn.get("Quantity", ""))
    if quantity == 0:
        return None

    trade_date, vest_date = _parse_date_with_as_of(txn.get("Date", ""))

    result = _lookup_vest_price(vest_fmvs, vest_date, trade_date)
    if result is None:
        logger.error("No vest FMV for %s, skipping", vest_date)
        return None

    price, canonical_vest_date = result
    cost = quantity * price
    symbol = txn.get("Symbol", "")
    isin = cusip_to_isin(_META_CUSIP) if symbol in ("META", "FB") else ""
    settle_date = canonical_vest_date + timedelta(days=2)  # T+2 from vest

    return Trade(
        account_id=account_id,
        asset_category="STK",
        symbol="META" if symbol == "FB" else symbol,
        isin=isin,
        description=txn.get("Description", ""),
        currency="USD",
        fx_rate_to_base=Decimal(0),
        trade_datetime=canonical_vest_date,
        settle_date=settle_date,
        buy_sell="BUY",
        quantity=quantity,
        trade_price=price,
        proceeds=-cost,
        cost=-cost,
        commission=Decimal(0),
        commission_currency="USD",
        broker_pnl_realized=Decimal(0),
        listing_exchange="",
        acquisition_date=canonical_vest_date,
    )


# ---------------------------------------------------------------------------
# Dividends and WHT
# ---------------------------------------------------------------------------


def _parse_dividend(txn: dict[str, Any], account_id: str) -> CashTransaction | None:
    amount = _parse_dollar(txn.get("Amount", ""))
    if amount == 0:
        return None
    trade_date, _ = _parse_date_with_as_of(txn.get("Date", ""))
    return CashTransaction(
        account_id=account_id,
        tx_type="Dividends",
        currency="USD",
        fx_rate_to_base=Decimal(0),
        date_time=trade_date,
        settle_date=trade_date,
        amount=amount,
        description=txn.get("Description", ""),
    )


def _parse_wht(txn: dict[str, Any], account_id: str) -> CashTransaction | None:
    amount = _parse_dollar(txn.get("Amount", ""))
    if amount == 0:
        return None
    trade_date, _ = _parse_date_with_as_of(txn.get("Date", ""))
    return CashTransaction(
        account_id=account_id,
        tx_type="Withholding Tax",
        currency="USD",
        fx_rate_to_base=Decimal(0),
        date_time=trade_date,
        settle_date=trade_date,
        amount=amount,
        description=txn.get("Description", ""),
    )


# ---------------------------------------------------------------------------
# Cash flow entries (wire transfers, sell proceeds, fees)
# ---------------------------------------------------------------------------


def _parse_wire_transfer(txn: dict[str, Any], account_id: str) -> CashTransaction | None:
    """Parse a wire transfer as a CashTransaction (negative USD = disposal)."""
    amount = _parse_dollar(txn.get("Amount", ""))
    if amount == 0:
        return None
    trade_date, _ = _parse_date_with_as_of(txn.get("Date", ""))
    return CashTransaction(
        account_id=account_id,
        tx_type="Wire Sent",
        currency="USD",
        fx_rate_to_base=Decimal(0),
        date_time=trade_date,
        settle_date=trade_date,
        amount=amount,
        description=txn.get("Description", ""),
    )


def _parse_sell_proceeds(txn: dict[str, Any], account_id: str) -> CashTransaction | None:
    """Parse sell proceeds as USD cash inflow.

    This captures ALL sell proceeds including sell-to-cover from RSU vests.
    The Year-End Summary handles tax computation (RT) — this is only for
    USD cash balance tracking (forex threshold + FIFO).
    """
    amount = _parse_dollar(txn.get("Amount", ""))
    if amount == 0:
        return None
    trade_date, _ = _parse_date_with_as_of(txn.get("Date", ""))
    return CashTransaction(
        account_id=account_id,
        tx_type="Sell Proceeds",
        currency="USD",
        fx_rate_to_base=Decimal(0),
        date_time=trade_date,
        settle_date=trade_date,
        amount=amount,
        description=txn.get("Description", ""),
    )


def _parse_service_fee(txn: dict[str, Any], account_id: str) -> CashTransaction | None:
    """Parse service fees (e.g., wire fees)."""
    amount = _parse_dollar(txn.get("Amount", ""))
    if amount == 0:
        return None
    trade_date, _ = _parse_date_with_as_of(txn.get("Date", ""))
    return CashTransaction(
        account_id=account_id,
        tx_type="Service Fee",
        currency="USD",
        fx_rate_to_base=Decimal(0),
        date_time=trade_date,
        settle_date=trade_date,
        amount=amount,
        description=txn.get("Description", ""),
    )


# ---------------------------------------------------------------------------
# Open positions (vests minus sells)
# ---------------------------------------------------------------------------


def _compute_open_positions(
    trades: list[Trade],
    account_id: str,
) -> list[OpenPositionLot]:
    """Compute open positions from all buys and sells.

    Sells from the Year-End Summary already have exact lot allocation
    (date_acquired tells us which vest lot was sold). We subtract
    sold quantities from vest lots to find what's still held.
    """
    # Build vest lots: (vest_date, symbol) → total quantity, price
    vest_lots: dict[tuple[date, str], dict] = {}
    for t in trades:
        if not t.is_buy:
            continue
        key = (t.trade_datetime, t.symbol)
        if key not in vest_lots:
            vest_lots[key] = {
                "quantity": Decimal(0),
                "price": t.trade_price,
                "isin": t.isin,
                "description": t.description,
                "currency": t.currency,
                "settle_date": t.settle_date,
            }
        vest_lots[key]["quantity"] += t.quantity

    # Subtract sells: each sell's date_acquired maps to a vest lot
    for t in trades:
        if not t.is_sell:
            continue
        # Extract acquisition date from description
        acq_match = re.search(r"acquired (\d{4}-\d{2}-\d{2})", t.description)
        if acq_match:
            acq_date = date.fromisoformat(acq_match.group(1))
            key = (acq_date, t.symbol)
            if key in vest_lots:
                vest_lots[key]["quantity"] -= abs(t.quantity)

    # Remaining lots with positive quantity = open positions
    result: list[OpenPositionLot] = []
    for (_vest_date, symbol), lot in vest_lots.items():
        qty = lot["quantity"]
        if qty <= 0:
            continue
        result.append(OpenPositionLot(
            account_id=account_id,
            asset_category="STK",
            symbol=symbol,
            isin=lot["isin"],
            description=lot["description"],
            currency=lot["currency"],
            fx_rate_to_base=Decimal(0),
            quantity=qty,
            mark_price=lot["price"],
            position_value=qty * lot["price"],
            cost_basis_money=qty * lot["price"],
            open_datetime=lot["settle_date"],
            listing_exchange="",  # Schwab/US stock — routed via ISIN prefix
        ))

    return result


# ---------------------------------------------------------------------------
# CUSIP to ISIN
# ---------------------------------------------------------------------------


def cusip_to_isin(cusip: str, country: str = "US") -> str:
    """Convert a 9-character CUSIP to a 12-character ISIN."""
    if len(cusip) != 9:
        return ""
    base = country + cusip
    digits = ""
    for ch in base:
        if ch.isdigit():
            digits += ch
        elif ch.isalpha():
            digits += str(ord(ch.upper()) - ord("A") + 10)
        else:
            return ""
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


def _lookup_vest_price(
    vest_prices: dict[date, Decimal], vest_date: date, trade_date: date,
) -> tuple[Decimal, date] | None:
    """Look up vest FMV from the Annual Withholding PDF.

    Returns (price, canonical_vest_date). The canonical date is the one
    from the FMV PDF — used as the lot identifier across Year-End Summary
    sells and position reconstruction.

    Tries exact match on vest_date and trade_date first, then ±3 days
    to handle weekends/processing delays between the JSON date and the
    FMV PDF date.
    """
    for d in (vest_date, trade_date):
        if d in vest_prices:
            return vest_prices[d], d
    # Older Schwab JSON entries lack the "as of" field, so vest_date =
    # processing date (16th) while FMV PDF uses the actual vest date (15th).
    # Try ±3 days to reconcile. Vests are 3 months apart, no ambiguity.
    for base in (vest_date, trade_date):
        for offset in range(1, 4):
            for d in (base - timedelta(days=offset), base + timedelta(days=offset)):
                if d in vest_prices:
                    logger.info(
                        "Vest date reconciled: JSON %s → FMV PDF %s (offset %dd)",
                        vest_date, d, abs((d - vest_date).days),
                    )
                    return vest_prices[d], d
    return None


def _parse_date_with_as_of(date_str: str) -> tuple[date, date]:
    if " as of " in date_str:
        primary, _, as_of = date_str.partition(" as of ")
        return _parse_schwab_date(primary.strip()), _parse_schwab_date(as_of.strip())
    return _parse_schwab_date(date_str), _parse_schwab_date(date_str)


def _parse_schwab_date(date_str: str) -> date:
    if not date_str:
        return date(2000, 1, 1)
    return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()


def _parse_dollar(value: str) -> Decimal:
    if not value or not value.strip():
        return Decimal(0)
    clean = value.strip().replace("$", "").replace(",", "")
    return Decimal(clean)


def _parse_quantity(value: str) -> Decimal:
    if not value or not value.strip():
        return Decimal(0)
    return Decimal(value.strip())
