"""SQLite storage for broker statement data.

Accumulates parsed statement data across multiple fetches so that
the 365-day IBKR sliding window doesn't cause data loss. Trades,
cash transactions, and conversion rates are deduped by natural keys.
Position snapshots are stored per fetch date.

Run `decaf --year XXXX` periodically to accumulate data. When
generating the final report, use `--no-fetch` to load from the store.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

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

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS accounts (
    account_id    TEXT PRIMARY KEY,
    base_currency TEXT NOT NULL,
    holder_name   TEXT NOT NULL,
    date_opened   TEXT NOT NULL,
    country       TEXT NOT NULL,
    broker_name   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS trades (
    id                  INTEGER PRIMARY KEY,
    account_id          TEXT NOT NULL,
    asset_category      TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL DEFAULT '',
    description         TEXT NOT NULL DEFAULT '',
    currency            TEXT NOT NULL,
    fx_rate_to_base     TEXT NOT NULL,
    trade_datetime      TEXT NOT NULL,
    settle_date         TEXT NOT NULL,
    buy_sell            TEXT NOT NULL,
    quantity            TEXT NOT NULL,
    trade_price         TEXT NOT NULL,
    proceeds            TEXT NOT NULL,
    cost                TEXT NOT NULL,
    commission          TEXT NOT NULL,
    commission_currency TEXT NOT NULL DEFAULT '',
    broker_pnl_realized TEXT NOT NULL,
    listing_exchange    TEXT NOT NULL DEFAULT '',
    UNIQUE(account_id, symbol, trade_datetime, settle_date, buy_sell, quantity, trade_price, description)
);

CREATE TABLE IF NOT EXISTS cash_transactions (
    id              INTEGER PRIMARY KEY,
    account_id      TEXT NOT NULL,
    tx_type         TEXT NOT NULL,
    currency        TEXT NOT NULL,
    fx_rate_to_base TEXT NOT NULL,
    date_time       TEXT NOT NULL,
    settle_date     TEXT NOT NULL,
    amount          TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    UNIQUE(account_id, date_time, currency, amount, tx_type, description)
);

CREATE TABLE IF NOT EXISTS conversion_rates (
    report_date   TEXT NOT NULL,
    from_currency TEXT NOT NULL,
    to_currency   TEXT NOT NULL,
    rate          TEXT NOT NULL,
    PRIMARY KEY(report_date, from_currency, to_currency)
);

CREATE TABLE IF NOT EXISTS position_lots (
    id              INTEGER PRIMARY KEY,
    fetch_date      TEXT NOT NULL,
    account_id      TEXT NOT NULL,
    asset_category  TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    isin            TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    currency        TEXT NOT NULL,
    fx_rate_to_base TEXT NOT NULL,
    quantity        TEXT NOT NULL,
    mark_price      TEXT NOT NULL,
    position_value  TEXT NOT NULL,
    cost_basis_money TEXT NOT NULL,
    open_datetime   TEXT NOT NULL,
    listing_exchange TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cash_report (
    id           INTEGER PRIMARY KEY,
    fetch_date   TEXT NOT NULL,
    currency     TEXT NOT NULL,
    starting_cash TEXT NOT NULL,
    ending_cash  TEXT NOT NULL,
    UNIQUE(fetch_date, currency)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    id             INTEGER PRIMARY KEY,
    fetch_date     TEXT NOT NULL,
    statement_from TEXT NOT NULL,
    statement_to   TEXT NOT NULL,
    accounts       TEXT NOT NULL,
    trade_count    INTEGER NOT NULL,
    position_count INTEGER NOT NULL,
    cash_txn_count INTEGER NOT NULL
);
"""


class StatementStore:
    """SQLite store for accumulating broker statement data."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: sqlite3.Connection | None = None

    def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self._db_path))
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        if self._db:
            self._db.close()
            self._db = None

    def __enter__(self) -> StatementStore:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def store(self, data: ParsedData) -> None:
        """Store parsed statement data, deduplicating on natural keys."""
        assert self._db is not None
        fetch_date = date.today().isoformat()

        self._store_account(data.account)
        n_trades = self._store_trades(data.trades)
        n_cash = self._store_cash_transactions(data.cash_transactions)
        self._store_conversion_rates(data.conversion_rates)
        n_pos = self._store_positions(data.positions, fetch_date)
        self._store_cash_report(data.cash_report, fetch_date)

        self._db.execute(
            "INSERT INTO fetch_log "
            "(fetch_date, statement_from, statement_to, accounts, "
            " trade_count, position_count, cash_txn_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                fetch_date,
                data.statement_from.isoformat(),
                data.statement_to.isoformat(),
                data.account.account_id,
                n_trades, n_pos, n_cash,
            ),
        )
        self._db.commit()

        logger.info(
            "Stored: %d new trades, %d new cash txns, %d positions (fetch %s)",
            n_trades, n_cash, n_pos, fetch_date,
        )

    def load_for_year(self, tax_year: int) -> ParsedData:
        """Load accumulated data for a tax year.

        Trades: all stored trades (caller filters by year as needed).
        Cash transactions: filtered to tax_year.
        Positions: latest snapshot available.
        Conversion rates: all stored.
        """
        assert self._db is not None

        accounts = self._load_accounts()
        if not accounts:
            raise ValueError("No account data in store. Run a fetch first.")

        trades = self._load_trades()
        cash_txns = self._load_cash_transactions(tax_year)
        conversion_rates = self._load_conversion_rates()
        positions = self._load_latest_positions()
        cash_report = self._load_latest_cash_report()

        # Merge account info
        if len(accounts) == 1:
            account = accounts[0]
        else:
            combined_ids = ", ".join(a.account_id for a in accounts)
            earliest = min(a.date_opened for a in accounts)
            account = AccountInfo(
                account_id=combined_ids,
                base_currency=accounts[0].base_currency,
                holder_name=accounts[0].holder_name,
                date_opened=earliest,
                country=accounts[0].country,
                broker_name=accounts[0].broker_name,
            )

        # Statement period from fetch log
        row = self._db.execute(
            "SELECT MIN(statement_from), MAX(statement_to) FROM fetch_log",
        ).fetchone()
        stmt_from = date.fromisoformat(row[0]) if row and row[0] else date(tax_year, 1, 1)
        stmt_to = date.fromisoformat(row[1]) if row and row[1] else date(tax_year, 12, 31)

        return ParsedData(
            account=account,
            trades=trades,
            positions=positions,
            cash_transactions=cash_txns,
            cash_report=cash_report,
            conversion_rates=conversion_rates,
            statement_from=stmt_from,
            statement_to=stmt_to,
        )

    def fetch_count(self) -> int:
        """Number of fetches stored."""
        assert self._db is not None
        row = self._db.execute("SELECT COUNT(*) FROM fetch_log").fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Store helpers
    # ------------------------------------------------------------------

    def _store_account(self, account: AccountInfo) -> None:
        assert self._db is not None
        # Multi-account IDs like "U123, U456" — store each separately
        for acct_id in account.account_id.split(", "):
            self._db.execute(
                "INSERT OR REPLACE INTO accounts VALUES (?, ?, ?, ?, ?, ?)",
                (
                    acct_id.strip(),
                    account.base_currency,
                    account.holder_name,
                    account.date_opened.isoformat(),
                    account.country,
                    account.broker_name,
                ),
            )

    def _store_trades(self, trades: list[Trade]) -> int:
        assert self._db is not None
        stored = 0
        for t in trades:
            try:
                self._db.execute(
                    "INSERT OR IGNORE INTO trades "
                    "(account_id, asset_category, symbol, isin, description, "
                    " currency, fx_rate_to_base, trade_datetime, settle_date, "
                    " buy_sell, quantity, trade_price, proceeds, cost, "
                    " commission, commission_currency, broker_pnl_realized,"
                    " listing_exchange) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        t.account_id, t.asset_category, t.symbol, t.isin,
                        t.description, t.currency, str(t.fx_rate_to_base),
                        t.trade_datetime.isoformat(), t.settle_date.isoformat(),
                        t.buy_sell, str(t.quantity), str(t.trade_price),
                        str(t.proceeds), str(t.cost), str(t.commission),
                        t.commission_currency, str(t.broker_pnl_realized),
                        t.listing_exchange,
                    ),
                )
                if self._db.execute("SELECT changes()").fetchone()[0] > 0:
                    stored += 1
            except sqlite3.IntegrityError:
                pass  # Duplicate, skip
        return stored

    def _store_cash_transactions(self, txns: list[CashTransaction]) -> int:
        assert self._db is not None
        stored = 0
        for ct in txns:
            try:
                self._db.execute(
                    "INSERT OR IGNORE INTO cash_transactions "
                    "(account_id, tx_type, currency, fx_rate_to_base, "
                    " date_time, settle_date, amount, description) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        ct.account_id, ct.tx_type, ct.currency,
                        str(ct.fx_rate_to_base),
                        ct.date_time.isoformat(), ct.settle_date.isoformat(),
                        str(ct.amount), ct.description,
                    ),
                )
                if self._db.execute("SELECT changes()").fetchone()[0] > 0:
                    stored += 1
            except sqlite3.IntegrityError:
                pass
        return stored

    def _store_conversion_rates(self, rates: list[ConversionRate]) -> None:
        assert self._db is not None
        self._db.executemany(
            "INSERT OR IGNORE INTO conversion_rates VALUES (?, ?, ?, ?)",
            [
                (
                    cr.report_date.isoformat(), cr.from_currency,
                    cr.to_currency, str(cr.rate),
                )
                for cr in rates
            ],
        )

    def _store_positions(self, positions: list[OpenPositionLot], fetch_date: str) -> int:
        assert self._db is not None
        # Clear previous snapshot for this fetch date + account, then insert fresh
        acct_ids = {p.account_id for p in positions}
        for acct_id in acct_ids:
            self._db.execute(
                "DELETE FROM position_lots WHERE fetch_date = ? AND account_id = ?",
                (fetch_date, acct_id),
            )
        for p in positions:
            self._db.execute(
                "INSERT INTO position_lots "
                "(fetch_date, account_id, asset_category, symbol, isin, "
                " description, currency, fx_rate_to_base, quantity, "
                " mark_price, position_value, cost_basis_money, open_datetime,"
                " listing_exchange) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fetch_date, p.account_id, p.asset_category, p.symbol,
                    p.isin, p.description, p.currency, str(p.fx_rate_to_base),
                    str(p.quantity), str(p.mark_price), str(p.position_value),
                    str(p.cost_basis_money), p.open_datetime.isoformat(),
                    p.listing_exchange,
                ),
            )
        return len(positions)

    def _store_cash_report(self, entries: list[CashReportEntry], fetch_date: str) -> None:
        assert self._db is not None
        for e in entries:
            self._db.execute(
                "INSERT OR REPLACE INTO cash_report "
                "(fetch_date, currency, starting_cash, ending_cash) "
                "VALUES (?, ?, ?, ?)",
                (fetch_date, e.currency, str(e.starting_cash), str(e.ending_cash)),
            )

    # ------------------------------------------------------------------
    # Load helpers
    # ------------------------------------------------------------------

    def _load_accounts(self) -> list[AccountInfo]:
        assert self._db is not None
        rows = self._db.execute("SELECT * FROM accounts ORDER BY account_id").fetchall()
        return [
            AccountInfo(
                account_id=r[0],
                base_currency=r[1],
                holder_name=r[2],
                date_opened=date.fromisoformat(r[3]),
                country=r[4],
                broker_name=r[5],
            )
            for r in rows
        ]

    def _load_trades(self) -> list[Trade]:
        assert self._db is not None
        rows = self._db.execute(
            "SELECT account_id, asset_category, symbol, isin, description, "
            "currency, fx_rate_to_base, trade_datetime, settle_date, "
            "buy_sell, quantity, trade_price, proceeds, cost, "
            "commission, commission_currency, broker_pnl_realized, "
            "COALESCE(listing_exchange, '') "
            "FROM trades ORDER BY trade_datetime",
        ).fetchall()
        return [
            Trade(
                account_id=r[0], asset_category=r[1], symbol=r[2], isin=r[3],
                description=r[4], currency=r[5], fx_rate_to_base=Decimal(r[6]),
                trade_datetime=date.fromisoformat(r[7]),
                settle_date=date.fromisoformat(r[8]),
                buy_sell=r[9], quantity=Decimal(r[10]),
                trade_price=Decimal(r[11]), proceeds=Decimal(r[12]),
                cost=Decimal(r[13]), commission=Decimal(r[14]),
                commission_currency=r[15], broker_pnl_realized=Decimal(r[16]),
                listing_exchange=r[17],
            )
            for r in rows
        ]

    def load_all_cash_transactions(self) -> list[CashTransaction]:
        """Load ALL cash transactions (no year filter). For forex FIFO."""
        assert self._db is not None
        rows = self._db.execute(
            "SELECT account_id, tx_type, currency, fx_rate_to_base, "
            "date_time, settle_date, amount, description "
            "FROM cash_transactions ORDER BY date_time",
        ).fetchall()
        return [
            CashTransaction(
                account_id=r[0], tx_type=r[1], currency=r[2],
                fx_rate_to_base=Decimal(r[3]),
                date_time=date.fromisoformat(r[4]),
                settle_date=date.fromisoformat(r[5]),
                amount=Decimal(r[6]), description=r[7],
            )
            for r in rows
        ]

    def _load_cash_transactions(self, tax_year: int) -> list[CashTransaction]:
        assert self._db is not None
        rows = self._db.execute(
            "SELECT account_id, tx_type, currency, fx_rate_to_base, "
            "date_time, settle_date, amount, description "
            "FROM cash_transactions "
            "WHERE date_time >= ? AND date_time <= ? "
            "ORDER BY date_time",
            (f"{tax_year}-01-01", f"{tax_year}-12-31"),
        ).fetchall()
        return [
            CashTransaction(
                account_id=r[0], tx_type=r[1], currency=r[2],
                fx_rate_to_base=Decimal(r[3]),
                date_time=date.fromisoformat(r[4]),
                settle_date=date.fromisoformat(r[5]),
                amount=Decimal(r[6]), description=r[7],
            )
            for r in rows
        ]

    def _load_conversion_rates(self) -> list[ConversionRate]:
        assert self._db is not None
        rows = self._db.execute(
            "SELECT report_date, from_currency, to_currency, rate "
            "FROM conversion_rates ORDER BY report_date",
        ).fetchall()
        return [
            ConversionRate(
                report_date=date.fromisoformat(r[0]),
                from_currency=r[1], to_currency=r[2],
                rate=Decimal(r[3]),
            )
            for r in rows
        ]

    def _load_latest_positions(self) -> list[OpenPositionLot]:
        """Load the latest position snapshot per account.

        Each broker's positions are stored separately, so we load the
        latest snapshot for each account_id and combine them.
        """
        assert self._db is not None
        # Get the latest fetch date per account
        rows = self._db.execute(
            "SELECT account_id, MAX(fetch_date) "
            "FROM position_lots GROUP BY account_id",
        ).fetchall()
        if not rows:
            return []

        result: list[OpenPositionLot] = []
        for acct_id, fetch_date in rows:
            lot_rows = self._db.execute(
                "SELECT account_id, asset_category, symbol, isin, description, "
                "currency, fx_rate_to_base, quantity, mark_price, "
                "position_value, cost_basis_money, open_datetime, "
                "COALESCE(listing_exchange, '') "
                "FROM position_lots WHERE fetch_date = ? AND account_id = ?",
                (fetch_date, acct_id),
            ).fetchall()
            result.extend(
                OpenPositionLot(
                    account_id=r[0], asset_category=r[1], symbol=r[2], isin=r[3],
                    description=r[4], currency=r[5], fx_rate_to_base=Decimal(r[6]),
                    quantity=Decimal(r[7]), mark_price=Decimal(r[8]),
                    position_value=Decimal(r[9]), cost_basis_money=Decimal(r[10]),
                    open_datetime=date.fromisoformat(r[11]),
                    listing_exchange=r[12],
                )
                for r in lot_rows
            )
        return result

    def _load_latest_cash_report(self) -> list[CashReportEntry]:
        assert self._db is not None
        row = self._db.execute(
            "SELECT MAX(fetch_date) FROM cash_report",
        ).fetchone()
        if not row or not row[0]:
            return []

        fetch_date = row[0]
        rows = self._db.execute(
            "SELECT currency, starting_cash, ending_cash "
            "FROM cash_report WHERE fetch_date = ?",
            (fetch_date,),
        ).fetchall()
        return [
            CashReportEntry(
                currency=r[0],
                starting_cash=Decimal(r[1]),
                ending_cash=Decimal(r[2]),
            )
            for r in rows
        ]
