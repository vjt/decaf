"""Tests for FlexStatement XML parsing."""

from datetime import date
from decimal import Decimal

import pytest

from decaf.parse import parse_statement


def _wrap_statement(
    *sections: str,
    account_id: str = "U9999999",
    from_date: str = "20250101",
    to_date: str = "20251231",
    base_currency: str = "EUR",
) -> str:
    """Build a minimal FlexQuery XML string."""
    acct_info = (
        f'<AccountInformation accountId="{account_id}" currency="{base_currency}" '
        f'name="Test User" accountType="Individual" customerType="Individual" '
        f'dateOpened="20250101" country="Italy" />'
    )
    body = acct_info + "\n".join(sections)
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<FlexQueryResponse queryName="Test" type="AF">'
        f'<FlexStatements count="1">'
        f'<FlexStatement accountId="{account_id}" fromDate="{from_date}" '
        f'toDate="{to_date}" period="Last365CalendarDays" '
        f'whenGenerated="20260327;100000">'
        f'{body}'
        f'</FlexStatement>'
        f'</FlexStatements>'
        f'</FlexQueryResponse>'
    )


class TestParseAccountInfo:
    def test_basic_fields(self) -> None:
        xml = _wrap_statement()
        data = parse_statement(xml, 2025)

        assert data.account.account_id == "U9999999"
        assert data.account.base_currency == "EUR"
        assert data.account.holder_name == "Test User"
        assert data.account.country == "Italy"
        assert data.account.date_opened == date(2025, 1, 1)

    def test_statement_dates(self) -> None:
        xml = _wrap_statement(from_date="20250327", to_date="20260326")
        data = parse_statement(xml, 2025)

        assert data.statement_from == date(2025, 3, 27)
        assert data.statement_to == date(2026, 3, 26)


class TestParseTrades:
    TRADE_BUY = (
        '<Trades>'
        '<Trade accountId="U9999999" assetCategory="STK" symbol="VWCE" '
        'isin="IE00BK5BQT80" description="VANGUARD FTSE AW" '
        'currency="EUR" fxRateToBase="1" '
        'dateTime="20250910;040742" settleDateTarget="20250912" '
        'buySell="BUY" quantity="100" tradePrice="140.50" '
        'proceeds="-14050" cost="14053" ibCommission="-3" '
        'ibCommissionCurrency="EUR" fifoPnlRealized="0" />'
        '</Trades>'
    )

    TRADE_SELL = (
        '<Trades>'
        '<Trade accountId="U9999999" assetCategory="STK" symbol="VWCE" '
        'isin="IE00BK5BQT80" description="VANGUARD FTSE AW" '
        'currency="EUR" fxRateToBase="1" '
        'dateTime="20251115;101500" settleDateTarget="20251117" '
        'buySell="SELL" quantity="-50" tradePrice="145.00" '
        'proceeds="7250" cost="-7026.50" ibCommission="-1.50" '
        'ibCommissionCurrency="EUR" fifoPnlRealized="222" />'
        '</Trades>'
    )

    TRADE_FOREX = (
        '<Trades>'
        '<Trade accountId="U9999999" assetCategory="CASH" symbol="EUR.USD" '
        'isin="" description="EUR.USD" '
        'currency="USD" fxRateToBase="0.92" '
        'dateTime="20251001;120000" settleDateTarget="20251003" '
        'buySell="BUY" quantity="10000" tradePrice="1.08" '
        'proceeds="-10800" cost="0" ibCommission="-2" '
        'ibCommissionCurrency="USD" fifoPnlRealized="0" />'
        '</Trades>'
    )

    def test_buy_trade(self) -> None:
        data = parse_statement(_wrap_statement(self.TRADE_BUY), 2025)
        assert len(data.trades) == 1

        t = data.trades[0]
        assert t.symbol == "VWCE"
        assert t.isin == "IE00BK5BQT80"
        assert t.asset_category == "STK"
        assert t.buy_sell == "BUY"
        assert t.is_buy
        assert not t.is_sell
        assert not t.is_forex
        assert t.quantity == Decimal("100")
        assert t.trade_price == Decimal("140.50")
        assert t.proceeds == Decimal("-14050")
        assert t.cost == Decimal("14053")
        assert t.commission == Decimal("-3")
        assert t.broker_pnl_realized == Decimal("0")
        assert t.trade_datetime == date(2025, 9, 10)
        assert t.settle_date == date(2025, 9, 12)

    def test_sell_trade(self) -> None:
        data = parse_statement(_wrap_statement(self.TRADE_SELL), 2025)
        t = data.trades[0]

        assert t.is_sell
        assert t.quantity == Decimal("-50")
        assert t.proceeds == Decimal("7250")
        assert t.cost == Decimal("-7026.50")
        assert t.broker_pnl_realized == Decimal("222")

    def test_forex_trade(self) -> None:
        data = parse_statement(_wrap_statement(self.TRADE_FOREX), 2025)
        t = data.trades[0]

        assert t.is_forex
        assert t.symbol == "EUR.USD"
        assert t.isin == ""
        assert t.cost == Decimal("0")

    def test_filters_by_year(self) -> None:
        # Trade in 2026 — cash_transactions filter, but trades list keeps all
        trade_2026 = (
            '<Trades>'
            '<Trade accountId="U9999999" assetCategory="STK" symbol="VWCE" '
            'isin="IE00BK5BQT80" description="VANGUARD FTSE AW" '
            'currency="EUR" fxRateToBase="1" '
            'dateTime="20260115;040742" settleDateTarget="20260117" '
            'buySell="BUY" quantity="10" tradePrice="150" '
            'proceeds="-1500" cost="1501" ibCommission="-1" '
            'ibCommissionCurrency="EUR" fifoPnlRealized="0" />'
            '</Trades>'
        )
        data = parse_statement(_wrap_statement(trade_2026), 2025)
        # All trades are kept (for FIFO context), even outside tax year
        assert len(data.trades) == 1

    def test_empty_trades(self) -> None:
        data = parse_statement(_wrap_statement("<Trades />"), 2025)
        assert data.trades == []


class TestParsePositions:
    POSITION_LOT = (
        '<OpenPositions>'
        '<OpenPosition accountId="U9999999" assetCategory="STK" '
        'symbol="IGLD" isin="IE0009JOT9U1" description="ISHARES GOLD" '
        'currency="EUR" fxRateToBase="1" '
        'position="200" markPrice="75.50" positionValue="15100" '
        'costBasisMoney="14800" openDateTime="20250901;100000" />'
        '</OpenPositions>'
    )

    def test_lot_fields(self) -> None:
        data = parse_statement(_wrap_statement(self.POSITION_LOT), 2025)
        assert len(data.positions) == 1

        p = data.positions[0]
        assert p.symbol == "IGLD"
        assert p.isin == "IE0009JOT9U1"
        assert p.currency == "EUR"
        assert p.quantity == Decimal("200")
        assert p.mark_price == Decimal("75.50")
        assert p.position_value == Decimal("15100")
        assert p.cost_basis_money == Decimal("14800")
        assert p.open_datetime == date(2025, 9, 1)

    def test_multiple_lots(self) -> None:
        xml = _wrap_statement(
            '<OpenPositions>'
            '<OpenPosition accountId="U9999999" assetCategory="STK" '
            'symbol="IGLD" isin="IE0009JOT9U1" description="ISHARES GOLD" '
            'currency="EUR" fxRateToBase="1" '
            'position="100" markPrice="75" positionValue="7500" '
            'costBasisMoney="7200" openDateTime="20250801;100000" />'
            '<OpenPosition accountId="U9999999" assetCategory="STK" '
            'symbol="IGLD" isin="IE0009JOT9U1" description="ISHARES GOLD" '
            'currency="EUR" fxRateToBase="1" '
            'position="50" markPrice="75" positionValue="3750" '
            'costBasisMoney="3700" openDateTime="20250901;100000" />'
            '</OpenPositions>'
        )
        data = parse_statement(xml, 2025)
        assert len(data.positions) == 2
        assert data.positions[0].open_datetime == date(2025, 8, 1)
        assert data.positions[1].open_datetime == date(2025, 9, 1)


class TestParseCashTransactions:
    INTEREST_AND_WHT = (
        '<CashTransactions>'
        '<CashTransaction accountId="U9999999" type="Broker Interest Received" '
        'currency="EUR" fxRateToBase="1" '
        'dateTime="20251003;170000" settleDate="20251003" '
        'amount="1.78" description="EUR CREDIT INT FOR SEP-2025" />'
        '<CashTransaction accountId="U9999999" type="Withholding Tax" '
        'currency="EUR" fxRateToBase="1" '
        'dateTime="20251003;170000" settleDate="20251003" '
        'amount="-0.36" description="EUR W/H TAX FOR SEP-2025" />'
        '<CashTransaction accountId="U9999999" type="Deposits/Withdrawals" '
        'currency="EUR" fxRateToBase="1" '
        'dateTime="20260115;090000" settleDate="20260115" '
        'amount="5000" description="DEPOSIT" />'
        '</CashTransactions>'
    )

    def test_filters_to_tax_year(self) -> None:
        data = parse_statement(_wrap_statement(self.INTEREST_AND_WHT), 2025)
        # 2 entries in 2025, 1 in 2026 (filtered out)
        assert len(data.cash_transactions) == 2

    def test_interest_fields(self) -> None:
        data = parse_statement(_wrap_statement(self.INTEREST_AND_WHT), 2025)
        interest = [ct for ct in data.cash_transactions if "Interest" in ct.tx_type]
        assert len(interest) == 1
        assert interest[0].amount == Decimal("1.78")
        assert interest[0].currency == "EUR"

    def test_wht_fields(self) -> None:
        data = parse_statement(_wrap_statement(self.INTEREST_AND_WHT), 2025)
        wht = [ct for ct in data.cash_transactions if "Withholding" in ct.tx_type]
        assert len(wht) == 1
        assert wht[0].amount == Decimal("-0.36")


class TestParseCashReport:
    CASH_REPORT = (
        '<CashReport>'
        '<CashReportCurrency accountId="U9999999" currency="BASE_SUMMARY" '
        'startingCash="0" endingCash="100000" />'
        '<CashReportCurrency accountId="U9999999" currency="EUR" '
        'startingCash="0" endingCash="70000" />'
        '<CashReportCurrency accountId="U9999999" currency="USD" '
        'startingCash="0" endingCash="30000" />'
        '</CashReport>'
    )

    def test_skips_base_summary(self) -> None:
        data = parse_statement(_wrap_statement(self.CASH_REPORT), 2025)
        currencies = [cr.currency for cr in data.cash_report]
        assert "BASE_SUMMARY" not in currencies

    def test_per_currency_entries(self) -> None:
        data = parse_statement(_wrap_statement(self.CASH_REPORT), 2025)
        assert len(data.cash_report) == 2

        eur = next(cr for cr in data.cash_report if cr.currency == "EUR")
        assert eur.starting_cash == Decimal("0")
        assert eur.ending_cash == Decimal("70000")


class TestParseConversionRates:
    RATES = (
        '<ConversionRates>'
        '<ConversionRate fromCurrency="USD" toCurrency="EUR" '
        'reportDate="20251231" rate="0.92" />'
        '<ConversionRate fromCurrency="GBP" toCurrency="EUR" '
        'reportDate="20251231" rate="1.17" />'
        '</ConversionRates>'
    )

    def test_parses_rates(self) -> None:
        data = parse_statement(_wrap_statement(self.RATES), 2025)
        assert len(data.conversion_rates) == 2

        usd = next(r for r in data.conversion_rates if r.from_currency == "USD")
        assert usd.rate == Decimal("0.92")
        assert usd.report_date == date(2025, 12, 31)


class TestParseErrors:
    def test_no_flex_statement_raises(self) -> None:
        with pytest.raises(ValueError, match="No FlexStatement"):
            parse_statement("<FlexQueryResponse></FlexQueryResponse>", 2025)

    def test_no_account_info_raises(self) -> None:
        xml = (
            '<FlexQueryResponse><FlexStatements count="1">'
            '<FlexStatement accountId="U1" fromDate="20250101" toDate="20251231">'
            '</FlexStatement></FlexStatements></FlexQueryResponse>'
        )
        with pytest.raises(ValueError, match="No AccountInformation"):
            parse_statement(xml, 2025)
