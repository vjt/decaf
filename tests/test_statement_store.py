"""Tests for statement SQLite store."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from decaf.models import (
    AccountInfo,
    CashReportEntry,
    CashTransaction,
    ConversionRate,
    OpenPositionLot,
    Trade,
)
from decaf.parse import ParsedData
from decaf.statement_store import StatementStore


@pytest.fixture
def store(tmp_path: Path) -> StatementStore:
    s = StatementStore(tmp_path / "test_statements.db")
    s.open()
    yield s
    s.close()


def _make_account(acct_id: str = "U12345678") -> AccountInfo:
    return AccountInfo(
        account_id=acct_id,
        base_currency="EUR",
        holder_name="Test User",
        date_opened=date(2025, 8, 17),
        country="IE",
        broker_name="Interactive Brokers",
    )


def _make_trade(
    symbol: str = "VWCE",
    trade_date: str = "2025-09-15",
    settle_date: str = "2025-09-17",
    buy_sell: str = "BUY",
    quantity: str = "10",
    price: str = "100.50",
    account_id: str = "U12345678",
) -> Trade:
    qty = Decimal(quantity)
    prc = Decimal(price)
    return Trade(
        account_id=account_id,
        asset_category="STK",
        symbol=symbol,
        isin="IE00BK5BQT80",
        description=f"{symbol} ETF",
        currency="EUR",
        fx_rate_to_base=Decimal("1"),
        trade_datetime=date.fromisoformat(trade_date),
        settle_date=date.fromisoformat(settle_date),
        buy_sell=buy_sell,
        quantity=qty if buy_sell == "BUY" else -qty,
        trade_price=prc,
        proceeds=-qty * prc if buy_sell == "BUY" else qty * prc,
        cost=-qty * prc,
        commission=Decimal("-1.50"),
        commission_currency="EUR",
        broker_pnl_realized=Decimal("0"),
        listing_exchange="IBIS2", acquisition_date=date.fromisoformat("2025-08-01"),
    )


def _make_cash_txn(
    tx_type: str = "Broker Interest Received",
    amount: str = "5.23",
    dt: str = "2025-10-15",
) -> CashTransaction:
    return CashTransaction(
        account_id="U12345678",
        tx_type=tx_type,
        currency="USD",
        fx_rate_to_base=Decimal("0.92"),
        date_time=date.fromisoformat(dt),
        settle_date=date.fromisoformat(dt),
        amount=Decimal(amount),
        description=f"Test {tx_type}",
    )


def _make_position(
    symbol: str = "VWCE",
    quantity: str = "10",
    open_date: str = "2025-09-17",
) -> OpenPositionLot:
    return OpenPositionLot(
        account_id="U12345678",
        asset_category="STK",
        symbol=symbol,
        isin="IE00BK5BQT80",
        description=f"{symbol} ETF",
        currency="EUR",
        fx_rate_to_base=Decimal("1"),
        quantity=Decimal(quantity),
        mark_price=Decimal("102.00"),
        position_value=Decimal(quantity) * Decimal("102.00"),
        cost_basis_money=Decimal(quantity) * Decimal("100.50"),
        open_datetime=date.fromisoformat(open_date),
        listing_exchange="IBIS2",
    )


def _make_parsed_data(
    trades: list[Trade] | None = None,
    cash_txns: list[CashTransaction] | None = None,
    positions: list[OpenPositionLot] | None = None,
    account: AccountInfo | None = None,
) -> ParsedData:
    return ParsedData(
        account=account or _make_account(),
        trades=trades or [],
        positions=positions or [],
        cash_transactions=cash_txns or [],
        cash_report=[
            CashReportEntry(
                currency="EUR", starting_cash=Decimal("1000"), ending_cash=Decimal("500"),
            ),
            CashReportEntry(
                currency="USD", starting_cash=Decimal("0"), ending_cash=Decimal("200"),
            ),
        ],
        conversion_rates=[
            ConversionRate(
                report_date=date(2025, 9, 15),
                from_currency="USD",
                to_currency="EUR",
                rate=Decimal("0.9200"),
            ),
        ],
        statement_from=date(2025, 3, 28),
        statement_to=date(2026, 3, 27),
    )


# ---------------------------------------------------------------------------
# Store + load roundtrip
# ---------------------------------------------------------------------------


class TestRoundtrip:
    def test_trades_roundtrip(self, store: StatementStore):
        trades = [_make_trade(), _make_trade(symbol="LLY", price="800.00")]
        store.store(_make_parsed_data(trades=trades))

        loaded = store.load_for_year(2025)
        assert len(loaded.trades) == 2
        symbols = {t.symbol for t in loaded.trades}
        assert symbols == {"VWCE", "LLY"}

    def test_trade_fields_preserved(self, store: StatementStore):
        trade = _make_trade(quantity="7", price="123.45")
        store.store(_make_parsed_data(trades=[trade]))

        loaded = store.load_for_year(2025)
        t = loaded.trades[0]
        assert t.quantity == Decimal("7")
        assert t.trade_price == Decimal("123.45")
        assert t.commission == Decimal("-1.50")
        assert t.isin == "IE00BK5BQT80"
        assert t.buy_sell == "BUY"

    def test_cash_transactions_roundtrip(self, store: StatementStore):
        txns = [_make_cash_txn(), _make_cash_txn(tx_type="Withholding Tax", amount="-1.05")]
        store.store(_make_parsed_data(cash_txns=txns))

        loaded = store.load_for_year(2025)
        assert len(loaded.cash_transactions) == 2

    def test_cash_transactions_include_all_years(self, store: StatementStore):
        """load_for_year returns ALL cash txns (forex FIFO needs full history)."""
        txns = [
            _make_cash_txn(dt="2024-12-15"),  # previous year
            _make_cash_txn(dt="2025-06-15"),  # target year
        ]
        store.store(_make_parsed_data(cash_txns=txns))

        loaded = store.load_for_year(2025)
        assert len(loaded.cash_transactions) == 2

    def test_positions_roundtrip(self, store: StatementStore):
        positions = [_make_position(), _make_position(symbol="LLY", quantity="5")]
        store.store(_make_parsed_data(positions=positions))

        loaded = store.load_for_year(2025)
        assert len(loaded.positions) == 2

    def test_conversion_rates_roundtrip(self, store: StatementStore):
        store.store(_make_parsed_data())

        loaded = store.load_for_year(2025)
        assert len(loaded.conversion_rates) == 1
        assert loaded.conversion_rates[0].rate == Decimal("0.9200")

    def test_cash_report_roundtrip(self, store: StatementStore):
        store.store(_make_parsed_data())

        loaded = store.load_for_year(2025)
        assert len(loaded.cash_report) == 2
        eur = next(r for r in loaded.cash_report if r.currency == "EUR")
        assert eur.ending_cash == Decimal("500")

    def test_account_info_roundtrip(self, store: StatementStore):
        store.store(_make_parsed_data())

        loaded = store.load_for_year(2025)
        assert loaded.account.account_id == "U12345678"
        assert loaded.account.broker_name == "Interactive Brokers"
        assert loaded.account.date_opened == date(2025, 8, 17)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_duplicate_trades_ignored(self, store: StatementStore):
        """Storing the same trade twice doesn't create duplicates."""
        trade = _make_trade()
        store.store(_make_parsed_data(trades=[trade]))
        store.store(_make_parsed_data(trades=[trade]))

        loaded = store.load_for_year(2025)
        assert len(loaded.trades) == 1

    def test_overlapping_fetches_accumulate(self, store: StatementStore):
        """Two fetches with overlapping and unique trades merge correctly."""
        trade_a = _make_trade(symbol="VWCE", trade_date="2025-09-15")
        trade_b = _make_trade(symbol="LLY", trade_date="2025-10-01", price="800")
        trade_c = _make_trade(symbol="IGLD", trade_date="2025-11-01", price="50")

        # First fetch: A + B
        store.store(_make_parsed_data(trades=[trade_a, trade_b]))
        # Second fetch: B + C (B is duplicate)
        store.store(_make_parsed_data(trades=[trade_b, trade_c]))

        loaded = store.load_for_year(2025)
        assert len(loaded.trades) == 3
        symbols = {t.symbol for t in loaded.trades}
        assert symbols == {"VWCE", "LLY", "IGLD"}

    def test_duplicate_cash_transactions_ignored(self, store: StatementStore):
        txn = _make_cash_txn()
        store.store(_make_parsed_data(cash_txns=[txn]))
        store.store(_make_parsed_data(cash_txns=[txn]))

        loaded = store.load_for_year(2025)
        assert len(loaded.cash_transactions) == 1

    def test_duplicate_conversion_rates_ignored(self, store: StatementStore):
        store.store(_make_parsed_data())
        store.store(_make_parsed_data())

        loaded = store.load_for_year(2025)
        assert len(loaded.conversion_rates) == 1

    def test_positions_use_latest_snapshot(self, store: StatementStore):
        """Positions from a later fetch replace earlier ones."""
        pos_v1 = [_make_position(quantity="10")]
        pos_v2 = [_make_position(quantity="15")]  # Bought more

        store.store(_make_parsed_data(positions=pos_v1))
        # Simulate later fetch (same day — both stored under today's date,
        # so the second replaces the first)
        store.store(_make_parsed_data(positions=pos_v2))

        loaded = store.load_for_year(2025)
        assert len(loaded.positions) == 1
        assert loaded.positions[0].quantity == Decimal("15")


# ---------------------------------------------------------------------------
# Multi-account
# ---------------------------------------------------------------------------


class TestMultiAccount:
    def test_multiple_accounts_stored(self, store: StatementStore):
        acct1 = _make_account("U11111111")
        acct2 = _make_account("U22222222")

        store.store(_make_parsed_data(
            account=acct1,
            trades=[_make_trade(account_id="U11111111")],
        ))
        store.store(_make_parsed_data(
            account=acct2,
            trades=[_make_trade(symbol="META", account_id="U22222222")],
        ))

        loaded = store.load_for_year(2025)
        assert len(loaded.trades) == 2
        assert "U11111111" in loaded.account.account_id
        assert "U22222222" in loaded.account.account_id

    def test_combined_account_ids_stored_separately(self, store: StatementStore):
        """When parse_statement merges accounts, store splits them back."""
        combined = AccountInfo(
            account_id="U11111111, U22222222",
            base_currency="EUR",
            holder_name="Test User",
            date_opened=date(2025, 1, 1),
            country="IE",
            broker_name="Interactive Brokers",
        )
        store.store(_make_parsed_data(account=combined))

        loaded = store.load_for_year(2025)
        # Should have both account IDs
        assert "U11111111" in loaded.account.account_id
        assert "U22222222" in loaded.account.account_id


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_store_raises(self, store: StatementStore):
        with pytest.raises(ValueError, match="No account data"):
            store.load_for_year(2025)

    def test_fetch_count(self, store: StatementStore):
        assert store.fetch_count() == 0
        store.store(_make_parsed_data())
        assert store.fetch_count() == 1
        store.store(_make_parsed_data())
        assert store.fetch_count() == 2

    def test_no_positions_returns_empty(self, store: StatementStore):
        store.store(_make_parsed_data(positions=[]))
        loaded = store.load_for_year(2025)
        assert loaded.positions == []
