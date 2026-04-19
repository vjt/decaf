"""Parse FlexStatement XML into domain models.

Converts raw XML elements from ibkr-flex-client's FlexStatement
into typed decaf domain models.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from decaf.models import (
    AccountInfo,
    CashReportEntry,
    CashTransaction,
    ConversionRate,
    OpenPositionLot,
    Trade,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ParsedData:
    """All data extracted from a FlexStatement, filtered to a tax year."""

    account: AccountInfo
    trades: list[Trade]
    positions: list[OpenPositionLot]
    cash_transactions: list[CashTransaction]
    cash_report: list[CashReportEntry]
    conversion_rates: list[ConversionRate]
    statement_from: date
    statement_to: date


def parse_statement(xml_text: str, tax_year: int) -> ParsedData:
    """Parse a FlexQuery XML and filter cash transactions to tax_year."""
    data = parse_statement_all(xml_text)
    filtered_cash = [
        ct for ct in data.cash_transactions
        if ct.date_time.year == tax_year
    ]
    return ParsedData(
        account=data.account,
        trades=data.trades,
        positions=data.positions,
        cash_transactions=filtered_cash,
        cash_report=data.cash_report,
        conversion_rates=data.conversion_rates,
        statement_from=data.statement_from,
        statement_to=data.statement_to,
    )


def parse_statement_all(xml_text: str) -> ParsedData:
    """Parse a FlexQuery XML string into domain models. No filtering.

    Handles multi-account FlexQuery responses: iterates ALL
    FlexStatement elements and merges trades, positions, cash
    transactions, etc. into one ParsedData. Same dichiarazione
    dei redditi, all foreign accounts combined.
    """
    root = ET.fromstring(xml_text)
    statements = root.findall(".//FlexStatement")
    if not statements:
        raise ValueError("No FlexStatement element found in XML")

    accounts: list[AccountInfo] = []
    all_trades: list[Trade] = []
    all_positions: list[OpenPositionLot] = []
    all_cash_txns: list[CashTransaction] = []
    all_cash_report: list[CashReportEntry] = []
    all_conversion_rates: list[ConversionRate] = []
    from_dates: list[date] = []
    to_dates: list[date] = []

    for stmt in statements:
        from_dates.append(_parse_ib_date(stmt.get("fromDate", "")))
        to_dates.append(_parse_ib_date(stmt.get("toDate", "")))

        accounts.append(_parse_account_info(stmt))

        all_trades.extend(_parse_trades(stmt))
        all_positions.extend(_parse_positions(stmt))
        all_cash_txns.extend(_parse_cash_transactions(stmt))
        all_cash_report.extend(_parse_cash_report(stmt))
        all_conversion_rates.extend(_parse_conversion_rates(stmt))

    # Merge account info: combine IDs, use earliest open date
    primary = accounts[0]
    if len(accounts) > 1:
        combined_ids = ", ".join(a.account_id for a in accounts)
        earliest_opened = min(a.date_opened for a in accounts)
        account = AccountInfo(
            account_id=combined_ids,
            base_currency=primary.base_currency,
            holder_name=primary.holder_name,
            date_opened=earliest_opened,
            country=primary.country,
            broker_name=primary.broker_name,
        )
    else:
        account = primary

    return ParsedData(
        account=account,
        trades=all_trades,
        positions=all_positions,
        cash_transactions=all_cash_txns,
        cash_report=all_cash_report,
        conversion_rates=all_conversion_rates,
        statement_from=min(from_dates),
        statement_to=max(to_dates),
    )


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------


def _parse_account_info(stmt: ET.Element) -> AccountInfo:
    ai = stmt.find("AccountInformation")
    if ai is None:
        raise ValueError("No AccountInformation element found")

    return AccountInfo(
        account_id=ai.get("accountId", ""),
        base_currency=ai.get("currency", ""),
        holder_name=ai.get("name", ""),
        date_opened=_parse_ib_date(ai.get("dateOpened", "")),
        country=ai.get("country", ""),
        broker_name=ai.get("brokerName", "Interactive Brokers"),
    )


def _parse_trades(stmt: ET.Element) -> Iterator[Trade]:
    """Walk <Trades> linearly. <Lot> elements are flat siblings of <Trade>:
    they follow the SELL <Trade> they belong to, inheriting dateTime and
    accountId. Buffer the pending STK SELL plus its trailing <Lot> siblings
    until the next <Trade> arrives, then emit one Trade per Lot.

    Every STK SELL must have at least one <Lot> sibling — art. 9 c. 2 TUIR
    requires per-lot ECB conversion. If Closed Lots is not enabled in
    the Flex Query, raise rather than silently approximate. See
    doc/QUERY_SETUP.md for setup.

    CASH SELLs (EUR.USD forex conversions) don't need per-lot tracking
    here — forex_gains.py handles LIFO queue separately. They emit as
    plain Trade rows via _trade_from_element.
    """
    section = stmt.find("Trades")
    if section is None:
        return

    pending_sell: ET.Element | None = None
    pending_lots: list[ET.Element] = []

    for elem in section:
        tag = elem.tag
        if tag == "Lot":
            if pending_sell is None:
                raise ValueError(
                    f"Lot sibling without parent SELL: {elem.get('symbol', '?')}"
                )
            pending_lots.append(elem)
            continue

        if pending_sell is not None:
            yield from _emit_sell_with_lots(pending_sell, pending_lots)
            pending_sell = None
            pending_lots = []

        if tag != "Trade":
            raise ValueError(f"Unexpected element inside <Trades>: {tag}")

        is_stk_sell = (
            elem.get("buySell") == "SELL"
            and elem.get("assetCategory") == "STK"
        )
        if is_stk_sell:
            pending_sell = elem
        else:
            yield _trade_from_element(elem)

    if pending_sell is not None:
        yield from _emit_sell_with_lots(pending_sell, pending_lots)


def _trade_from_element(elem: ET.Element) -> Trade:
    """Build one Trade from a non-SELL <Trade> row (BUY, forex, etc.).

    SELL rows go through _emit_sell_with_lots — this path is reserved
    for anything that doesn't need per-lot acquisition tracking.
    """
    return Trade(
        account_id=elem.get("accountId", ""),
        asset_category=elem.get("assetCategory", ""),
        symbol=elem.get("symbol", ""),
        isin=elem.get("isin", ""),
        description=elem.get("description", ""),
        currency=elem.get("currency", ""),
        fx_rate_to_base=_dec(elem, "fxRateToBase"),
        trade_datetime=_parse_ib_datetime(elem.get("dateTime", "")),
        settle_date=_parse_ib_date(elem.get("settleDateTarget", "")),
        buy_sell=elem.get("buySell", ""),
        quantity=_dec(elem, "quantity"),
        trade_price=_dec(elem, "tradePrice"),
        proceeds=_dec(elem, "proceeds"),
        cost=_dec(elem, "cost"),
        commission=_dec(elem, "ibCommission"),
        commission_currency=elem.get("ibCommissionCurrency", ""),
        broker_pnl_realized=_dec(elem, "fifoPnlRealized"),
        listing_exchange=elem.get("listingExchange", ""),
        acquisition_date=_parse_ib_datetime(elem.get("dateTime", "")),
    )


def _emit_sell_with_lots(
    sell_el: ET.Element, lot_els: list[ET.Element],
) -> Iterator[Trade]:
    """Emit one Trade per <Lot> sibling of a SELL <Trade>.

    Real IBKR Closed Lots shape (Flex Query v3, 2026):
    - Lot@accountId, currency, fxRateToBase, assetCategory, symbol, isin,
      description, listingExchange — inherited verbatim from parent Trade
    - Lot@quantity is positive; negate for Trade semantics
    - Lot@cost is positive (cost basis of the lot); negate for Trade
    - Lot@proceeds is empty → pro-rata from parent by quantity
    - Lot@ibCommission is empty → pro-rata parent commission by quantity
    - Lot@settleDateTarget is empty → inherit parent's
    - Lot@openDateTime is the acquisition date (art. 9 c. 2 TUIR key)
    - Lot@fifoPnlRealized is already net of pro-rated commission

    Commission pro-rata preserves `proceeds + commission` = parent's net
    USD, which forex_gains.py consumes to build per-account LIFO queues.
    Last lot absorbs any rounding residual so the sum matches exactly.

    SELL without any Lot sibling means Closed Lots is not enabled in the
    Flex Query — raise rather than silently approximate.
    """
    symbol = sell_el.get("symbol", "?")
    if not lot_els:
        raise ValueError(
            f"SELL of {symbol} has no Lot siblings — enable Closed Lots "
            f"in the Flex Query Trades section (see doc/QUERY_SETUP.md)"
        )

    parent_qty_abs = abs(_dec(sell_el, "quantity"))
    parent_proceeds = _dec(sell_el, "proceeds")
    parent_commission = _dec(sell_el, "ibCommission")
    if parent_qty_abs == 0:
        raise ValueError(f"SELL of {symbol} has zero quantity")

    last_idx = len(lot_els) - 1
    allocated_proceeds = Decimal(0)
    allocated_commission = Decimal(0)
    for i, lot in enumerate(lot_els):
        lot_qty_pos = _dec(lot, "quantity")
        lot_cost_pos = _dec(lot, "cost")
        if i == last_idx:
            lot_proceeds = parent_proceeds - allocated_proceeds
            lot_commission = parent_commission - allocated_commission
        else:
            lot_proceeds = parent_proceeds * lot_qty_pos / parent_qty_abs
            lot_commission = parent_commission * lot_qty_pos / parent_qty_abs
            allocated_proceeds += lot_proceeds
            allocated_commission += lot_commission
        yield Trade(
            account_id=lot.get("accountId", ""),
            asset_category=lot.get("assetCategory", ""),
            symbol=lot.get("symbol", ""),
            isin=lot.get("isin", ""),
            description=lot.get("description", ""),
            currency=lot.get("currency", ""),
            fx_rate_to_base=_dec(lot, "fxRateToBase"),
            trade_datetime=_parse_ib_datetime(sell_el.get("dateTime", "")),
            settle_date=_parse_ib_date(sell_el.get("settleDateTarget", "")),
            buy_sell="SELL",
            quantity=-lot_qty_pos,
            trade_price=_dec(lot, "tradePrice"),
            proceeds=lot_proceeds,
            cost=-lot_cost_pos,
            commission=lot_commission,
            commission_currency=sell_el.get("ibCommissionCurrency", ""),
            broker_pnl_realized=_dec(lot, "fifoPnlRealized"),
            listing_exchange=lot.get("listingExchange", ""),
            acquisition_date=_parse_ib_datetime(lot.get("openDateTime", "")),
        )


def _parse_positions(stmt: ET.Element) -> Iterator[OpenPositionLot]:
    section = stmt.find("OpenPositions")
    if section is None:
        return

    for elem in section:
        try:
            yield OpenPositionLot(
                account_id=elem.get("accountId", ""),
                asset_category=elem.get("assetCategory", ""),
                symbol=elem.get("symbol", ""),
                isin=elem.get("isin", ""),
                description=elem.get("description", ""),
                currency=elem.get("currency", ""),
                fx_rate_to_base=_dec(elem, "fxRateToBase"),
                quantity=_dec(elem, "position"),
                mark_price=_dec(elem, "markPrice"),
                position_value=_dec(elem, "positionValue"),
                cost_basis_money=_dec(elem, "costBasisMoney"),
                open_datetime=_parse_ib_datetime(elem.get("openDateTime", "")),
                listing_exchange=elem.get("listingExchange", ""),
            )
        except (ValueError, InvalidOperation) as e:
            logger.warning(
                "Skipping unparseable position: %s (%s)",
                elem.get("symbol", "?"), e,
            )


def _parse_cash_transactions(stmt: ET.Element) -> Iterator[CashTransaction]:
    section = stmt.find("CashTransactions")
    if section is None:
        return

    for elem in section:
        try:
            yield CashTransaction(
                account_id=elem.get("accountId", ""),
                tx_type=elem.get("type", ""),
                currency=elem.get("currency", ""),
                fx_rate_to_base=_dec(elem, "fxRateToBase"),
                date_time=_parse_ib_datetime(elem.get("dateTime", "")),
                settle_date=_parse_ib_date(elem.get("settleDate", "")),
                amount=_dec(elem, "amount"),
                description=elem.get("description", ""),
            )
        except (ValueError, InvalidOperation) as e:
            logger.warning(
                "Skipping unparseable cash transaction: %s (%s)",
                elem.get("type", "?"), e,
            )


def _parse_cash_report(stmt: ET.Element) -> Iterator[CashReportEntry]:
    section = stmt.find("CashReport")
    if section is None:
        return

    for elem in section:
        currency = elem.get("currency", "")
        if currency == "BASE_SUMMARY":
            continue
        try:
            yield CashReportEntry(
                currency=currency,
                starting_cash=_dec(elem, "startingCash"),
                ending_cash=_dec(elem, "endingCash"),
            )
        except (ValueError, InvalidOperation) as e:
            logger.warning("Skipping unparseable cash report entry: %s (%s)", currency, e)


def _parse_conversion_rates(stmt: ET.Element) -> Iterator[ConversionRate]:
    section = stmt.find("ConversionRates")
    if section is None:
        return

    for elem in section:
        try:
            yield ConversionRate(
                report_date=_parse_ib_date(elem.get("reportDate", "")),
                from_currency=elem.get("fromCurrency", ""),
                to_currency=elem.get("toCurrency", ""),
                rate=_dec(elem, "rate"),
            )
        except (ValueError, InvalidOperation) as e:
            logger.warning("Skipping unparseable conversion rate: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dec(elem: ET.Element, attr: str) -> Decimal:
    """Extract a Decimal from an XML element attribute."""
    val = elem.get(attr, "0")
    if not val:
        return Decimal(0)
    return Decimal(val)


def _parse_ib_date(date_str: str) -> date:
    """Parse IB's yyyyMMdd date format."""
    if not date_str:
        raise ValueError("Empty date string")
    return datetime.strptime(date_str[:8], "%Y%m%d").date()


def _parse_ib_datetime(datetime_str: str) -> date:
    """Parse IB's yyyyMMdd;HHmmss datetime format, returning the date part.

    Accepts both 'yyyyMMdd;HHmmss' and plain 'yyyyMMdd'.
    """
    if not datetime_str:
        raise ValueError("Empty datetime string")
    return datetime.strptime(datetime_str[:8], "%Y%m%d").date()
