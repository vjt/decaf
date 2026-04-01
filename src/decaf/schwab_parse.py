"""Parse Schwab JSON transaction export into domain models.

Parses the JSON file downloaded from schwab.com History page
(not the Trader API, which is useless for stock plan activity).

Key features:
- Stock Plan Activity → Trade(BUY) with vest price from Yahoo Finance
- Sell → Trade(SELL) with broker-provided price and cost basis
- Qualified Dividend → CashTransaction(Dividends)
- NRA Tax Adj → CashTransaction(Withholding Tax)
- Per-lot FIFO reconstruction for IVAFE
- CUSIP → ISIN conversion for US equities
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
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

# META's CUSIP — only equity in the Schwab account
_META_CUSIP = "30303M102"


def parse_schwab_json(
    json_path: Path,
    vest_prices: dict[date, Decimal],
    account_id: str = "",
) -> ParsedData:
    """Parse a Schwab transaction history JSON export.

    Args:
        json_path: Path to the downloaded JSON file.
        vest_prices: Mapping of vest date → closing price per share.
            Used as cost basis for Stock Plan Activity entries.
        account_id: Schwab account number (extracted from filename if empty).
    """
    raw = json.loads(json_path.read_text())
    txns = raw.get("BrokerageTransactions", [])

    if not account_id:
        # Try to extract from filename: Individual_XXX123_Transactions_...
        match = re.search(r"XXX(\d+)", json_path.name)
        account_id = f"XXX{match.group(1)}" if match else "schwab"

    from_date = _parse_schwab_date(raw.get("FromDate", ""))
    to_date = _parse_schwab_date(raw.get("ToDate", ""))

    trades: list[Trade] = []
    cash_txns: list[CashTransaction] = []
    cash_balance = Decimal(0)

    for txn in txns:
        action = txn.get("Action", "")

        if action == "Sell":
            trade = _parse_sell(txn, account_id)
            if trade:
                trades.append(trade)
                cash_balance += trade.proceeds + trade.commission

        elif action == "Stock Plan Activity":
            trade = _parse_vest(txn, account_id, vest_prices)
            if trade:
                trades.append(trade)

        elif action == "Qualified Dividend":
            ct = _parse_dividend(txn, account_id)
            if ct:
                cash_txns.append(ct)
                cash_balance += ct.amount

        elif action == "NRA Tax Adj":
            ct = _parse_wht(txn, account_id)
            if ct:
                cash_txns.append(ct)
                cash_balance += ct.amount

        elif action == "Wire Sent":
            amount = _parse_dollar(txn.get("Amount", ""))
            cash_balance += amount  # Negative, reduces balance

    # Assign FIFO cost basis to sells, then reconstruct remaining lots
    trades = _assign_cost_basis(trades)
    positions = _reconstruct_lots(trades, account_id)

    # Cash report: we only know the net effect, not start/end separately
    cash_report = [CashReportEntry(
        currency="USD",
        starting_cash=Decimal(0),
        ending_cash=max(cash_balance, Decimal(0)),
    )]

    account = AccountInfo(
        account_id=account_id,
        base_currency="USD",
        holder_name="",
        date_opened=from_date,
        country="US",
        broker_name="Charles Schwab",
    )

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


def extract_vest_dates(json_path: Path) -> list[date]:
    """Extract all unique vest dates from a Schwab JSON export.

    Call this first, fetch prices for these dates, then call parse_schwab_json.
    """
    raw = json.loads(json_path.read_text())
    dates: set[date] = set()
    for txn in raw.get("BrokerageTransactions", []):
        if txn.get("Action") == "Stock Plan Activity":
            _, vest_date = _parse_date_with_as_of(txn.get("Date", ""))
            dates.add(vest_date)
    return sorted(dates)


# ---------------------------------------------------------------------------
# Sell trades
# ---------------------------------------------------------------------------


def _parse_sell(txn: dict[str, Any], account_id: str) -> Trade | None:
    """Parse a Sell transaction."""
    quantity = _parse_quantity(txn.get("Quantity", ""))
    price = _parse_dollar(txn.get("Price", ""))
    amount = _parse_dollar(txn.get("Amount", ""))
    fees = _parse_dollar(txn.get("Fees & Comm", ""))

    if quantity == 0:
        return None

    trade_date, _ = _parse_date_with_as_of(txn.get("Date", ""))
    # Settlement: T+1 for US equities (since May 2024)
    from datetime import timedelta
    settle_date = trade_date + timedelta(days=1)

    symbol = txn.get("Symbol", "")
    isin = cusip_to_isin(_META_CUSIP) if symbol == "META" else ""

    return Trade(
        account_id=account_id,
        asset_category="STK",
        symbol=symbol,
        isin=isin,
        description=txn.get("Description", ""),
        currency="USD",
        fx_rate_to_base=Decimal(0),
        trade_datetime=trade_date,
        settle_date=settle_date,
        buy_sell="SELL",
        quantity=-quantity,  # Negative for sells
        trade_price=price,
        proceeds=amount,
        cost=Decimal(0),  # Schwab JSON doesn't include cost basis per sell
        commission=-abs(fees),
        commission_currency="USD",
        broker_pnl_realized=Decimal(0),  # Computed from lots later
    )


# ---------------------------------------------------------------------------
# RSU vest deposits (Stock Plan Activity)
# ---------------------------------------------------------------------------


def _parse_vest(
    txn: dict[str, Any],
    account_id: str,
    vest_prices: dict[date, Decimal],
) -> Trade | None:
    """Parse a Stock Plan Activity (RSU vest) as a BUY trade.

    The vest FMV (fair market value) is looked up from vest_prices.
    This is the cost basis for Italian capital gains tax.
    """
    quantity = _parse_quantity(txn.get("Quantity", ""))
    if quantity == 0:
        return None

    trade_date, vest_date = _parse_date_with_as_of(txn.get("Date", ""))

    price = _lookup_vest_price(vest_prices, vest_date, trade_date)
    if price is None:
        logger.error("No price available for vest on %s, skipping", vest_date)
        return None

    cost = quantity * price
    symbol = txn.get("Symbol", "")
    isin = cusip_to_isin(_META_CUSIP) if symbol in ("META", "FB") else ""

    # Settlement: same day for stock plan activity
    from datetime import timedelta
    settle_date = trade_date + timedelta(days=1)

    return Trade(
        account_id=account_id,
        asset_category="STK",
        symbol="META" if symbol == "FB" else symbol,  # FB → META rename
        isin=isin,
        description=txn.get("Description", ""),
        currency="USD",
        fx_rate_to_base=Decimal(0),
        trade_datetime=vest_date,  # Use the actual vest date
        settle_date=settle_date,
        buy_sell="BUY",
        quantity=quantity,
        trade_price=price,
        proceeds=-cost,
        cost=-cost,
        commission=Decimal(0),
        commission_currency="USD",
        broker_pnl_realized=Decimal(0),
    )


# ---------------------------------------------------------------------------
# Dividends and withholding tax
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
        amount=amount,  # Already negative
        description=txn.get("Description", ""),
    )


# ---------------------------------------------------------------------------
# Open position lots (FIFO reconstruction)
# ---------------------------------------------------------------------------


def _assign_cost_basis(trades: list[Trade]) -> list[Trade]:
    """Walk trades in chronological order, FIFO-assign cost basis to sells.

    Returns a new trade list with sell trades updated to include
    cost and broker_pnl_realized computed from the vest lot queue.
    """
    # Build lot queue from buys
    lots: list[_Lot] = []
    for t in sorted(trades, key=lambda x: x.trade_datetime):
        if t.is_buy and t.trade_price > 0:
            lots.append(_Lot(
                quantity=abs(t.quantity),
                price=t.trade_price,
                cost_total=abs(t.cost),
                trade_date=t.trade_datetime,
                settle_date=t.settle_date,
                isin=t.isin,
                description=t.description,
                currency=t.currency,
            ))

    # Process sells FIFO
    result: list[Trade] = []
    for t in trades:
        if not t.is_sell or t.asset_category != "STK":
            result.append(t)
            continue

        sell_qty = abs(t.quantity)
        cost_basis = Decimal(0)
        remaining = sell_qty

        while remaining > 0 and lots:
            lot = lots[0]
            if lot.quantity <= remaining:
                cost_basis += lot.cost_total
                remaining -= lot.quantity
                lots.pop(0)
            else:
                # Partial lot consumption
                fraction = remaining / lot.quantity
                cost_basis += lot.cost_total * fraction
                lots[0] = _Lot(
                    quantity=lot.quantity - remaining,
                    price=lot.price,
                    cost_total=lot.cost_total * (Decimal(1) - fraction),
                    trade_date=lot.trade_date,
                    settle_date=lot.settle_date,
                    isin=lot.isin,
                    description=lot.description,
                    currency=lot.currency,
                )
                remaining = Decimal(0)

        cost_basis = cost_basis.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        pnl = (t.proceeds + t.commission - cost_basis).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )

        # Replace the sell trade with cost basis filled in
        result.append(Trade(
            account_id=t.account_id,
            asset_category=t.asset_category,
            symbol=t.symbol,
            isin=t.isin,
            description=t.description,
            currency=t.currency,
            fx_rate_to_base=t.fx_rate_to_base,
            trade_datetime=t.trade_datetime,
            settle_date=t.settle_date,
            buy_sell=t.buy_sell,
            quantity=t.quantity,
            trade_price=t.trade_price,
            proceeds=t.proceeds,
            cost=-cost_basis,  # Negative (IB convention for sells)
            commission=t.commission,
            commission_currency=t.commission_currency,
            broker_pnl_realized=pnl,
        ))

    return result


def _reconstruct_lots(
    trades: list[Trade],
    account_id: str,
) -> list[OpenPositionLot]:
    """Reconstruct open position lots via FIFO from trade history."""
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

    # FIFO: consume lots with sells
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
                mark_price=lot.price,
                position_value=lot.quantity * lot.price,
                cost_basis_money=lot.cost_total,
                open_datetime=lot.settle_date,
            ))

    return result


@dataclass
class _Lot:
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
    quantity: Decimal
    trade_date: date


# ---------------------------------------------------------------------------
# CUSIP to ISIN conversion
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
# Yahoo Finance price lookup
# ---------------------------------------------------------------------------


async def fetch_vest_prices(
    session: Any,  # aiohttp.ClientSession
    symbol: str,
    dates: list[date],
) -> dict[date, Decimal]:
    """Fetch historical closing prices from Yahoo Finance.

    Returns a dict mapping each requested date to the closing price.
    For dates that fall on weekends/holidays, uses the previous
    trading day's close.
    """
    if not dates:
        return {}

    import aiohttp

    # Fetch a range covering all dates with some buffer
    from datetime import timedelta
    min_date = min(dates) - timedelta(days=5)
    max_date = max(dates) + timedelta(days=1)

    period1 = int(datetime.combine(min_date, datetime.min.time()).timestamp())
    period2 = int(datetime.combine(max_date, datetime.min.time()).timestamp())

    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={period1}&period2={period2}&interval=1d"
    )

    async with session.get(url, headers={"User-Agent": "decaf/0.1"}) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise RuntimeError(f"Yahoo Finance error {resp.status}: {body[:200]}")
        data = await resp.json()

    result_data = data.get("chart", {}).get("result", [])
    if not result_data:
        raise RuntimeError("No data from Yahoo Finance")

    timestamps = result_data[0].get("timestamp", [])
    closes = result_data[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])

    # Build date → close price mapping
    all_prices: dict[date, Decimal] = {}
    for ts, close in zip(timestamps, closes):
        if close is not None:
            d = datetime.fromtimestamp(ts).date()
            all_prices[d] = Decimal(str(round(close, 4)))

    # For each requested date, find exact or previous trading day
    prices: dict[date, Decimal] = {}
    sorted_trading_days = sorted(all_prices.keys())

    for target in dates:
        # Find the latest trading day <= target
        best = None
        for td in sorted_trading_days:
            if td <= target:
                best = td
            else:
                break
        if best is not None:
            prices[target] = all_prices[best]
            logger.info(
                "Vest price for %s: %s %s (trading day %s)",
                target, symbol, all_prices[best], best,
            )
        else:
            logger.warning("No price found for %s on or before %s", symbol, target)

    return prices


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lookup_vest_price(
    vest_prices: dict[date, Decimal],
    vest_date: date,
    trade_date: date,
) -> Decimal | None:
    """Look up vest price, fuzzy-matching ±3 days.

    The JSON "as of" dates (e.g., 02/18) may differ from the PDF vest
    dates (e.g., 02/15) due to weekends and processing delays.
    """
    from datetime import timedelta
    # Try exact match first
    for d in (vest_date, trade_date):
        if d in vest_prices:
            return vest_prices[d]
    # Fuzzy: look ±3 days around vest_date
    for offset in range(1, 4):
        for d in (vest_date - timedelta(days=offset), vest_date + timedelta(days=offset)):
            if d in vest_prices:
                return vest_prices[d]
    # Fuzzy around trade_date too
    for offset in range(1, 4):
        for d in (trade_date - timedelta(days=offset), trade_date + timedelta(days=offset)):
            if d in vest_prices:
                return vest_prices[d]
    return None


def _parse_date_with_as_of(date_str: str) -> tuple[date, date]:
    """Parse Schwab date, handling 'MM/DD/YYYY as of MM/DD/YYYY' format.

    Returns (primary_date, vest_date). If no 'as of', both are the same.
    """
    if " as of " in date_str:
        primary, _, as_of = date_str.partition(" as of ")
        return _parse_schwab_date(primary.strip()), _parse_schwab_date(as_of.strip())
    return _parse_schwab_date(date_str), _parse_schwab_date(date_str)


def _parse_schwab_date(date_str: str) -> date:
    """Parse MM/DD/YYYY date format."""
    if not date_str:
        return date(2000, 1, 1)
    return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()


def _parse_dollar(value: str) -> Decimal:
    """Parse '$1,234.56' or '-$1,234.56' to Decimal."""
    if not value or not value.strip():
        return Decimal(0)
    clean = value.strip().replace("$", "").replace(",", "")
    return Decimal(clean)


def _parse_quantity(value: str) -> Decimal:
    """Parse quantity string to Decimal."""
    if not value or not value.strip():
        return Decimal(0)
    return Decimal(value.strip())
