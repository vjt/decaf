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
                commission=_dec(elem, "ibCommission"),
                commission_currency=elem.get("ibCommissionCurrency", ""),
                broker_pnl_realized=_dec(elem, "fifoPnlRealized"),
                listing_exchange=elem.get("listingExchange", ""),
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
