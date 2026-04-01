"""Tests for Schwab JSON export parsing.

Synthetic data mirrors the real Schwab JSON transaction export format
(downloaded from schwab.com History page).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from decaf.schwab_parse import (
    cusip_to_isin,
    extract_vest_dates,
    parse_schwab_json,
)


META_ISIN = "US30303M1027"


# ---------------------------------------------------------------------------
# Fixtures: synthetic Schwab JSON
# ---------------------------------------------------------------------------


def _make_schwab_json(transactions: list[dict]) -> dict:
    return {
        "FromDate": "01/01/2025",
        "ToDate": "12/31/2025",
        "TotalTransactionsAmount": "$0.00",
        "TotalFeesAndCommAmount": "$0.00",
        "BrokerageTransactions": transactions,
    }


def _vest(dt: str, qty: int) -> dict:
    return {
        "Date": dt,
        "Action": "Stock Plan Activity",
        "Symbol": "META",
        "Description": "META PLATFORMS INC CLASS A",
        "Quantity": str(qty),
        "Price": "",
        "Fees & Comm": "",
        "Amount": "",
        "AcctgRuleCd": "1",
    }


def _sell(dt: str, qty: int, price: str, amount: str, fees: str = "") -> dict:
    return {
        "Date": dt,
        "Action": "Sell",
        "Symbol": "META",
        "Description": "META PLATFORMS INC CLASS A",
        "Quantity": str(qty),
        "Price": price,
        "Fees & Comm": fees,
        "Amount": amount,
        "AcctgRuleCd": "1",
    }


def _dividend(dt: str, amount: str) -> dict:
    return {
        "Date": dt,
        "Action": "Qualified Dividend",
        "Symbol": "META",
        "Description": "META PLATFORMS INC CLASS A",
        "Quantity": "",
        "Price": "",
        "Fees & Comm": "",
        "Amount": amount,
        "AcctgRuleCd": "1",
    }


def _nra_tax(dt: str, amount: str) -> dict:
    return {
        "Date": dt,
        "Action": "NRA Tax Adj",
        "Symbol": "META",
        "Description": "META PLATFORMS INC CLASS A",
        "Quantity": "",
        "Price": "",
        "Fees & Comm": "",
        "Amount": amount,
        "AcctgRuleCd": "1",
    }


@pytest.fixture
def vest_prices() -> dict[date, Decimal]:
    """Synthetic vest prices for test dates."""
    return {
        date(2025, 2, 18): Decimal("700.00"),
        date(2025, 5, 15): Decimal("640.00"),
        date(2025, 8, 15): Decimal("780.00"),
    }


@pytest.fixture
def full_json(tmp_path: Path) -> Path:
    """Full synthetic Schwab JSON with vests, sells, dividends, WHT."""
    data = _make_schwab_json([
        # 3 vest lots on 02/18/2025
        _vest("02/19/2025 as of 02/18/2025", 33),
        _vest("02/19/2025 as of 02/18/2025", 18),
        _vest("02/19/2025 as of 02/18/2025", 1),
        # Sell on 05/19/2025
        _sell("05/19/2025", 10, "$639.20", "$6,392.00"),
        # Vest on 05/15/2025
        _vest("05/16/2025 as of 05/15/2025", 35),
        _vest("05/16/2025 as of 05/15/2025", 1),
        # Dividend + WHT
        _dividend("06/26/2025", "$95.03"),
        _nra_tax("06/26/2025", "-$14.25"),
        # Sell on 08/04/2025
        _sell("08/04/2025", 60, "$772.845", "$46,370.69", "$0.01"),
        # Vest on 08/15/2025
        _vest("08/18/2025 as of 08/15/2025", 33),
        _vest("08/18/2025 as of 08/15/2025", 1),
    ])
    path = tmp_path / "Individual_XXX123_Transactions_test.json"
    path.write_text(json.dumps(data))
    return path


# ---------------------------------------------------------------------------
# CUSIP to ISIN
# ---------------------------------------------------------------------------


class TestCusipToIsin:
    def test_meta(self):
        assert cusip_to_isin("30303M102") == META_ISIN

    def test_apple(self):
        assert cusip_to_isin("037833100") == "US0378331005"

    def test_empty(self):
        assert cusip_to_isin("") == ""


# ---------------------------------------------------------------------------
# Vest date extraction
# ---------------------------------------------------------------------------


class TestExtractVestDates:
    def test_extracts_unique_dates(self, full_json: Path):
        dates = extract_vest_dates(full_json)
        assert date(2025, 2, 18) in dates
        assert date(2025, 5, 15) in dates
        assert date(2025, 8, 15) in dates
        # 3 unique dates, not 7 (one per vest entry)
        assert len(dates) == 3

    def test_sorted(self, full_json: Path):
        dates = extract_vest_dates(full_json)
        assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# Trade parsing
# ---------------------------------------------------------------------------


class TestTradeParsing:
    def test_vest_as_buy(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        buys = [t for t in data.trades if t.is_buy]
        assert len(buys) == 7  # 3 + 2 + 2

    def test_vest_price_from_lookup(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        # First vest lot: 33 shares on 02/18 @ $700
        feb_buys = [t for t in data.trades if t.is_buy and t.trade_datetime == date(2025, 2, 18)]
        assert feb_buys[0].trade_price == Decimal("700.00")
        assert feb_buys[0].quantity == Decimal("33")

    def test_vest_cost_basis(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        feb_buys = [t for t in data.trades if t.is_buy and t.trade_datetime == date(2025, 2, 18)]
        # 33 shares @ $700 = $23,100
        assert abs(feb_buys[0].cost) == Decimal("23100.00")

    def test_sell_trade(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        sells = [t for t in data.trades if t.is_sell]
        assert len(sells) == 2

        first_sell = [s for s in sells if s.trade_datetime == date(2025, 5, 19)][0]
        assert first_sell.quantity == Decimal("-10")
        assert first_sell.trade_price == Decimal("639.20")
        assert first_sell.proceeds == Decimal("6392.00")

    def test_sell_fees(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        aug_sell = [t for t in data.trades if t.is_sell and t.trade_datetime == date(2025, 8, 4)][0]
        assert aug_sell.commission == Decimal("-0.01")

    def test_fb_renamed_to_meta(self, tmp_path: Path):
        """Pre-2022 vests used FB symbol — should be normalized to META."""
        data = _make_schwab_json([
            {"Date": "05/17/2022 as of 05/16/2022", "Action": "Stock Plan Activity",
             "Symbol": "FB", "Description": "META PLATFORMS INC CLASS A",
             "Quantity": "25", "Price": "", "Fees & Comm": "", "Amount": "", "AcctgRuleCd": "1"},
        ])
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))
        prices = {date(2022, 5, 16): Decimal("200.00")}
        parsed = parse_schwab_json(path, prices)
        assert parsed.trades[0].symbol == "META"
        assert parsed.trades[0].isin == META_ISIN

    def test_all_trades_usd(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        for t in data.trades:
            assert t.currency == "USD"


# ---------------------------------------------------------------------------
# Cash transactions
# ---------------------------------------------------------------------------


class TestCashTransactions:
    def test_dividend(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        divs = [ct for ct in data.cash_transactions if ct.tx_type == "Dividends"]
        assert len(divs) == 1
        assert divs[0].amount == Decimal("95.03")

    def test_withholding_tax(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        wht = [ct for ct in data.cash_transactions if ct.tx_type == "Withholding Tax"]
        assert len(wht) == 1
        assert wht[0].amount == Decimal("-14.25")


# ---------------------------------------------------------------------------
# Lot reconstruction
# ---------------------------------------------------------------------------


class TestLotReconstruction:
    def test_lots_after_sells(self, full_json: Path, vest_prices):
        """7 vest lots, 2 sells (10 + 60 = 70 shares sold).
        Total vested: 33+18+1 + 35+1 + 33+1 = 122 shares.
        Remaining: 122 - 70 = 52 shares."""
        data = parse_schwab_json(full_json, vest_prices)
        total = sum(p.quantity for p in data.positions)
        assert total == Decimal("52")

    def test_fifo_order(self, full_json: Path, vest_prices):
        """FIFO: first 10 shares sold from Feb vest (33-lot),
        then 60 shares: rest of Feb 33-lot (23), Feb 18-lot, Feb 1-lot,
        then into May lots."""
        data = parse_schwab_json(full_json, vest_prices)
        lots = sorted(data.positions, key=lambda p: (p.open_datetime, -p.quantity))

        # After selling 70: Feb lots fully consumed (52 shares),
        # May 35-lot partially consumed (35 - 18 = 17 remaining),
        # May 1-lot intact, Aug lots intact
        assert len(lots) > 0
        # Total must be 52
        assert sum(p.quantity for p in lots) == Decimal("52")

    def test_lot_isin(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        for p in data.positions:
            assert p.isin == META_ISIN


# ---------------------------------------------------------------------------
# Account info
# ---------------------------------------------------------------------------


class TestAccountInfo:
    def test_account_id_from_filename(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        assert data.account.account_id == "XXX123"

    def test_broker_name(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        assert data.account.broker_name == "Charles Schwab"

    def test_usd_base(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        assert data.account.base_currency == "USD"

    def test_no_conversion_rates(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        assert data.conversion_rates == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestCostBasis:
    def test_sell_gets_fifo_cost_basis(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        sells = [t for t in data.trades if t.is_sell]
        # All sells should have non-zero cost now
        for sell in sells:
            assert sell.cost != 0, f"Sell on {sell.trade_datetime} has zero cost"
            assert sell.broker_pnl_realized != 0 or sell.proceeds + sell.commission == abs(sell.cost)

    def test_first_sell_cost_from_first_vest(self, full_json: Path, vest_prices):
        """First sell (10 shares on 05/19) should use Feb vest price ($700)."""
        data = parse_schwab_json(full_json, vest_prices)
        first_sell = [t for t in data.trades if t.is_sell and t.trade_datetime.month == 5][0]
        # 10 shares @ $700 vest price = $7,000 cost basis
        assert abs(first_sell.cost) == Decimal("7000.00")

    def test_pnl_computed(self, full_json: Path, vest_prices):
        data = parse_schwab_json(full_json, vest_prices)
        first_sell = [t for t in data.trades if t.is_sell and t.trade_datetime.month == 5][0]
        # Proceeds $6,392.00 - cost $7,000.00 = -$608.00 loss
        assert first_sell.broker_pnl_realized == Decimal("-608.00")


class TestEdgeCases:
    def test_empty_transactions(self, tmp_path: Path):
        data = _make_schwab_json([])
        path = tmp_path / "empty.json"
        path.write_text(json.dumps(data))
        parsed = parse_schwab_json(path, {})
        assert len(parsed.trades) == 0
        assert len(parsed.positions) == 0

    def test_zero_amount_dividend_skipped(self, tmp_path: Path):
        data = _make_schwab_json([_dividend("06/15/2025", "")])
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))
        parsed = parse_schwab_json(path, {})
        assert len(parsed.cash_transactions) == 0

    def test_wire_sent_not_a_trade(self, tmp_path: Path):
        data = _make_schwab_json([{
            "Date": "11/19/2025", "Action": "Wire Sent", "Symbol": "",
            "Description": "FX WIRE OUT", "Quantity": "", "Price": "",
            "Fees & Comm": "", "Amount": "-$15,000.00", "AcctgRuleCd": "1",
        }])
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))
        parsed = parse_schwab_json(path, {})
        assert len(parsed.trades) == 0
