"""Tests for Schwab API response parsing.

Synthetic data: Meta RSU scenario.
- 3 RSU vest deposits (RECEIVE_AND_DELIVER)
- 1 sell trade (TRADE)
- 1 dividend (DIVIDEND_OR_INTEREST)
- 1 withholding tax (DIVIDEND_OR_INTEREST, negative)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from decaf.schwab_parse import cusip_to_isin, parse_schwab_data


# ---------------------------------------------------------------------------
# Synthetic Schwab API fixtures
# ---------------------------------------------------------------------------

META_CUSIP = "30303M102"
META_ISIN = "US30303M1027"


def _make_account_json(
    account_number: str = "12345678",
    cash_balance: float = 1685.00,
    positions: list | None = None,
) -> dict:
    """Synthetic Schwab account response."""
    if positions is None:
        positions = [
            {
                "longQuantity": 12.0,
                "settledLongQuantity": 12.0,
                "averagePrice": 516.67,
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": META_CUSIP,
                    "symbol": "META",
                    "description": "META PLATFORMS INC CLASS A",
                },
                "marketValue": 6720.00,
                "averageLongPrice": 516.67,
                "taxLotAverageLongPrice": 516.67,
                "longOpenProfitLoss": 520.00,
            }
        ]

    return {
        "securitiesAccount": {
            "type": "BROKERAGE",
            "accountNumber": account_number,
            "positions": positions,
            "currentBalances": {
                "cashBalance": cash_balance,
                "longMarketValue": 6720.00,
                "liquidationValue": cash_balance + 6720.00,
            },
        },
    }


def _make_rsu_vest(
    activity_id: int,
    trade_date: str,
    settle_date: str,
    shares: float,
    price_per_share: float,
) -> dict:
    """Synthetic RECEIVE_AND_DELIVER transaction for RSU vest."""
    return {
        "activityId": activity_id,
        "time": f"{trade_date}T00:00:00+0000",
        "description": "STOCK PLAN ACTIVITY RSU RELEASE",
        "accountNumber": "12345678",
        "type": "RECEIVE_AND_DELIVER",
        "status": "VALID",
        "subAccount": "1",
        "tradeDate": f"{trade_date}T00:00:00+0000",
        "settlementDate": f"{settle_date}T00:00:00+0000",
        "netAmount": 0.0,
        "transferItems": [
            {
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": META_CUSIP,
                    "symbol": "META",
                    "description": "META PLATFORMS INC CLASS A",
                },
                "amount": shares,
                "cost": shares * price_per_share,
                "price": price_per_share,
            }
        ],
    }


def _make_sell_trade(
    activity_id: int,
    trade_date: str,
    settle_date: str,
    shares: float,
    price: float,
    cost_basis: float,
) -> dict:
    """Synthetic TRADE (sell) transaction."""
    net_amount = shares * price  # Commission-free
    return {
        "activityId": activity_id,
        "time": f"{trade_date}T14:30:00+0000",
        "description": f"Sell {int(shares)} META @ {price:.2f}",
        "accountNumber": "12345678",
        "type": "TRADE",
        "status": "VALID",
        "subAccount": "1",
        "tradeDate": f"{trade_date}T00:00:00+0000",
        "settlementDate": f"{settle_date}T00:00:00+0000",
        "netAmount": net_amount,
        "transferItems": [
            {
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": META_CUSIP,
                    "symbol": "META",
                    "description": "META PLATFORMS INC CLASS A",
                },
                "amount": -shares,  # Negative = selling
                "cost": cost_basis,
                "price": price,
            }
        ],
    }


def _make_dividend(
    activity_id: int,
    trade_date: str,
    amount: float,
    description: str = "CASH DIV ON 12 SHS",
) -> dict:
    """Synthetic DIVIDEND_OR_INTEREST transaction."""
    return {
        "activityId": activity_id,
        "time": f"{trade_date}T00:00:00+0000",
        "description": description,
        "accountNumber": "12345678",
        "type": "DIVIDEND_OR_INTEREST",
        "status": "VALID",
        "subAccount": "1",
        "tradeDate": f"{trade_date}T00:00:00+0000",
        "settlementDate": f"{trade_date}T00:00:00+0000",
        "netAmount": amount,
        "transferItems": [
            {
                "instrument": {
                    "assetType": "EQUITY",
                    "cusip": META_CUSIP,
                    "symbol": "META",
                    "description": "META PLATFORMS INC CLASS A",
                },
                "amount": 0.0,
                "cost": 0.0,
                "price": 0.0,
            }
        ],
    }


@pytest.fixture
def meta_rsu_transactions() -> list[dict]:
    """Full Meta RSU scenario: 3 vests, 1 sell, 1 dividend, 1 WHT."""
    return [
        # Vest 1: Mar 15, 5 shares @ $500
        _make_rsu_vest(2001, "2025-03-15", "2025-03-18", 5.0, 500.00),
        # Vest 2: Jun 15, 5 shares @ $520
        _make_rsu_vest(2002, "2025-06-15", "2025-06-18", 5.0, 520.00),
        # Vest 3: Sep 15, 5 shares @ $540
        _make_rsu_vest(2003, "2025-09-15", "2025-09-18", 5.0, 540.00),
        # Sell: Nov 15, 3 shares @ $560, cost basis $1500 (FIFO from vest 1)
        _make_sell_trade(1001, "2025-11-15", "2025-11-18", 3.0, 560.00, 1500.00),
        # Dividend: Dec 15, $60 on 12 shares
        _make_dividend(3001, "2025-12-15", 60.00),
        # Withholding tax: Dec 15, -$9 (15% of $60)
        _make_dividend(3002, "2025-12-15", -9.00, "NRA TAX WITHHOLDING"),
    ]


@pytest.fixture
def account_json() -> dict:
    return _make_account_json()


# ---------------------------------------------------------------------------
# CUSIP to ISIN tests
# ---------------------------------------------------------------------------


class TestCusipToIsin:
    def test_meta_cusip(self):
        assert cusip_to_isin("30303M102") == META_ISIN

    def test_apple_cusip(self):
        # Apple Inc: CUSIP 037833100, ISIN US0378331005
        assert cusip_to_isin("037833100") == "US0378331005"

    def test_microsoft_cusip(self):
        # Microsoft: CUSIP 594918104, ISIN US5949181045
        assert cusip_to_isin("594918104") == "US5949181045"

    def test_empty_cusip(self):
        assert cusip_to_isin("") == ""

    def test_wrong_length(self):
        assert cusip_to_isin("12345") == ""


# ---------------------------------------------------------------------------
# Account parsing
# ---------------------------------------------------------------------------


class TestAccountParsing:
    def test_account_info(self, account_json, meta_rsu_transactions):
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        assert data.account.account_id == "12345678"
        assert data.account.base_currency == "USD"
        assert data.account.country == "US"

    def test_statement_dates(self, account_json, meta_rsu_transactions):
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        assert data.statement_from == date(2025, 1, 1)
        assert data.statement_to == date(2025, 12, 31)

    def test_cash_report(self, account_json, meta_rsu_transactions):
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        assert len(data.cash_report) == 1
        assert data.cash_report[0].currency == "USD"
        assert data.cash_report[0].ending_cash == Decimal("1685")

    def test_no_conversion_rates(self, account_json, meta_rsu_transactions):
        """Schwab doesn't provide FX rates — we use ECB."""
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        assert data.conversion_rates == []


# ---------------------------------------------------------------------------
# Trade parsing
# ---------------------------------------------------------------------------


class TestTradeParsing:
    def test_trade_count(self, account_json, meta_rsu_transactions):
        """3 RSU vests (BUY) + 1 sell = 4 trades."""
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        assert len(data.trades) == 4

    def test_rsu_vest_as_buy(self, account_json, meta_rsu_transactions):
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        vest1 = data.trades[0]
        assert vest1.buy_sell == "BUY"
        assert vest1.symbol == "META"
        assert vest1.isin == META_ISIN
        assert vest1.quantity == Decimal("5")
        assert vest1.trade_price == Decimal("500")
        assert vest1.trade_datetime == date(2025, 3, 15)
        assert vest1.settle_date == date(2025, 3, 18)
        assert vest1.asset_category == "STK"
        assert vest1.currency == "USD"
        assert vest1.commission == Decimal(0)

    def test_sell_trade(self, account_json, meta_rsu_transactions):
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        sell = [t for t in data.trades if t.is_sell][0]
        assert sell.buy_sell == "SELL"
        assert sell.symbol == "META"
        assert sell.quantity == Decimal("-3")  # Negative for sells
        assert sell.trade_price == Decimal("560")
        assert sell.trade_datetime == date(2025, 11, 15)
        assert sell.settle_date == date(2025, 11, 18)
        # Broker P/L: proceeds ($1680) - cost basis ($1500) = $180
        assert sell.broker_pnl_realized == Decimal("180")

    def test_sell_proceeds(self, account_json, meta_rsu_transactions):
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        sell = [t for t in data.trades if t.is_sell][0]
        assert sell.proceeds == Decimal("1680")  # 3 * 560


# ---------------------------------------------------------------------------
# Cash transaction parsing (dividends, WHT)
# ---------------------------------------------------------------------------


class TestCashTransactionParsing:
    def test_dividend(self, account_json, meta_rsu_transactions):
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        divs = [ct for ct in data.cash_transactions if ct.tx_type == "Dividends"]
        assert len(divs) == 1
        assert divs[0].amount == Decimal("60")
        assert divs[0].currency == "USD"
        assert divs[0].date_time == date(2025, 12, 15)

    def test_withholding_tax(self, account_json, meta_rsu_transactions):
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        wht = [ct for ct in data.cash_transactions if ct.tx_type == "Withholding Tax"]
        assert len(wht) == 1
        assert wht[0].amount == Decimal("-9")  # Negative (tax deducted)

    def test_tax_year_filter(self, account_json):
        """Cash transactions outside tax year are excluded."""
        txns = [
            _make_dividend(3001, "2024-12-15", 50.00),  # Previous year
            _make_dividend(3002, "2025-06-15", 60.00),   # Current year
        ]
        data = parse_schwab_data(account_json, txns, 2025)
        assert len(data.cash_transactions) == 1
        assert data.cash_transactions[0].amount == Decimal("60")


# ---------------------------------------------------------------------------
# Lot reconstruction (FIFO)
# ---------------------------------------------------------------------------


class TestLotReconstruction:
    def test_lots_after_partial_sell(self, account_json, meta_rsu_transactions):
        """3 vests of 5 shares, sell 3 → remaining: 2 from vest1, 5 from vest2, 5 from vest3."""
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        assert len(data.positions) == 3

        # Sort by date to verify FIFO
        lots = sorted(data.positions, key=lambda p: p.open_datetime)

        # Lot 1: vest1 had 5 shares, sold 3 → 2 remaining
        assert lots[0].symbol == "META"
        assert lots[0].quantity == Decimal("2")
        assert lots[0].open_datetime == date(2025, 3, 18)  # Settlement date

        # Lot 2: vest2, untouched
        assert lots[1].quantity == Decimal("5")
        assert lots[1].open_datetime == date(2025, 6, 18)

        # Lot 3: vest3, untouched
        assert lots[2].quantity == Decimal("5")
        assert lots[2].open_datetime == date(2025, 9, 18)

    def test_total_shares(self, account_json, meta_rsu_transactions):
        """Total shares: 15 vested - 3 sold = 12."""
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        total = sum(p.quantity for p in data.positions)
        assert total == Decimal("12")

    def test_lots_with_full_sell(self, account_json):
        """Sell entire first vest lot → 2 remaining lots."""
        txns = [
            _make_rsu_vest(2001, "2025-03-15", "2025-03-18", 5.0, 500.00),
            _make_rsu_vest(2002, "2025-06-15", "2025-06-18", 5.0, 520.00),
            _make_sell_trade(1001, "2025-08-01", "2025-08-04", 5.0, 550.00, 2500.00),
        ]
        data = parse_schwab_data(account_json, txns, 2025)
        assert len(data.positions) == 1
        assert data.positions[0].quantity == Decimal("5")
        assert data.positions[0].open_datetime == date(2025, 6, 18)

    def test_no_sells(self, account_json):
        """No sells → all lots remain."""
        txns = [
            _make_rsu_vest(2001, "2025-03-15", "2025-03-18", 5.0, 500.00),
            _make_rsu_vest(2002, "2025-06-15", "2025-06-18", 3.0, 520.00),
        ]
        data = parse_schwab_data(account_json, txns, 2025)
        assert len(data.positions) == 2
        total = sum(p.quantity for p in data.positions)
        assert total == Decimal("8")

    def test_sell_all(self, account_json):
        """Sell everything → no open positions."""
        txns = [
            _make_rsu_vest(2001, "2025-03-15", "2025-03-18", 5.0, 500.00),
            _make_sell_trade(1001, "2025-08-01", "2025-08-04", 5.0, 550.00, 2500.00),
        ]
        data = parse_schwab_data(account_json, txns, 2025)
        assert len(data.positions) == 0

    def test_isin_on_lots(self, account_json, meta_rsu_transactions):
        """Lots should have ISIN derived from CUSIP."""
        data = parse_schwab_data(account_json, meta_rsu_transactions, 2025)
        for lot in data.positions:
            assert lot.isin == META_ISIN

    def test_cost_basis_prorated_on_partial_sell(self, account_json):
        """When a lot is partially consumed, cost basis is prorated."""
        txns = [
            _make_rsu_vest(2001, "2025-03-15", "2025-03-18", 10.0, 500.00),
            _make_sell_trade(1001, "2025-08-01", "2025-08-04", 4.0, 550.00, 2000.00),
        ]
        data = parse_schwab_data(account_json, txns, 2025)
        assert len(data.positions) == 1
        lot = data.positions[0]
        assert lot.quantity == Decimal("6")
        # Original cost: 10 * 500 = 5000. After selling 4, remaining 6/10 * 5000 = 3000
        assert lot.cost_basis_money == Decimal("3000")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_transactions(self, account_json):
        data = parse_schwab_data(account_json, [], 2025)
        assert len(data.trades) == 0
        assert len(data.positions) == 0
        assert len(data.cash_transactions) == 0

    def test_outbound_transfer_ignored(self, account_json):
        """RECEIVE_AND_DELIVER with negative amount (transfer out) is skipped."""
        txns = [
            {
                "activityId": 9001,
                "description": "TRANSFER OUT",
                "accountNumber": "12345678",
                "type": "RECEIVE_AND_DELIVER",
                "status": "VALID",
                "tradeDate": "2025-06-15T00:00:00+0000",
                "settlementDate": "2025-06-18T00:00:00+0000",
                "netAmount": 0.0,
                "transferItems": [{
                    "instrument": {
                        "assetType": "EQUITY",
                        "cusip": META_CUSIP,
                        "symbol": "META",
                        "description": "META PLATFORMS INC CLASS A",
                    },
                    "amount": -5.0,  # Negative = transfer out
                    "cost": 2500.00,
                    "price": 500.00,
                }],
            },
        ]
        data = parse_schwab_data(account_json, txns, 2025)
        assert len(data.trades) == 0

    def test_zero_dividend_ignored(self, account_json):
        txns = [_make_dividend(3001, "2025-06-15", 0.00)]
        data = parse_schwab_data(account_json, txns, 2025)
        assert len(data.cash_transactions) == 0

    def test_empty_transfer_items(self, account_json):
        """Transaction with empty transferItems is skipped."""
        txns = [{
            "activityId": 9002,
            "type": "TRADE",
            "status": "VALID",
            "tradeDate": "2025-06-15T00:00:00+0000",
            "settlementDate": "2025-06-18T00:00:00+0000",
            "netAmount": 100.0,
            "transferItems": [],
        }]
        data = parse_schwab_data(account_json, txns, 2025)
        assert len(data.trades) == 0
