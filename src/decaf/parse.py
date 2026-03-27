"""Parse FlexStatement XML into domain models.

Converts raw XML elements from ibkr-flex-client's FlexStatement
into typed ibtax domain models, filtered by tax year.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterator

import xml.etree.ElementTree as ET

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
    """Parse a FlexQuery XML string into domain models.

    Filters trades and cash transactions to the given tax_year.
    Open positions are always included (they're a point-in-time snapshot).
    Conversion rates are included for the full statement period.
    """
    root = ET.fromstring(xml_text)
    stmt = root.find(".//FlexStatement")
    if stmt is None:
        raise ValueError("No FlexStatement element found in XML")

    from_date = _parse_ib_date(stmt.get("fromDate", ""))
    to_date = _parse_ib_date(stmt.get("toDate", ""))

    account = _parse_account_info(stmt)

    trades = [
        t for t in _parse_trades(stmt)
        if t.trade_datetime.year == tax_year
    ]

    # Include ALL buys (even outside tax year) for FIFO context,
    # but the caller will filter sells to tax_year for RT.
    all_trades = list(_parse_trades(stmt))

    positions = list(_parse_positions(stmt))

    cash_transactions = [
        ct for ct in _parse_cash_transactions(stmt)
        if ct.date_time.year == tax_year
    ]

    cash_report = list(_parse_cash_report(stmt))
    conversion_rates = list(_parse_conversion_rates(stmt))

    return ParsedData(
        account=account,
        trades=all_trades,
        positions=positions,
        cash_transactions=cash_transactions,
        cash_report=cash_report,
        conversion_rates=conversion_rates,
        statement_from=from_date,
        statement_to=to_date,
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
    )


def _parse_trades(stmt: ET.Element) -> Iterator[Trade]:
    section = stmt.find("Trades")
    if section is None:
        return

    for elem in section:
        try:
            yield Trade(
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
                ib_commission=_dec(elem, "ibCommission"),
                ib_commission_currency=elem.get("ibCommissionCurrency", ""),
                fifo_pnl_realized=_dec(elem, "fifoPnlRealized"),
            )
        except (ValueError, InvalidOperation) as e:
            logger.warning(
                "Skipping unparseable trade: %s (%s)",
                elem.get("symbol", "?"), e,
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
