"""Tests for Quadro RL — income/WHT matching."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from decaf.models import CashTransaction
from decaf.quadro_rl import compute_rl


class _StubFx:
    """Minimal FxService stand-in: identity 1.0 USD->EUR, no ECB hits."""

    def __init__(self, rate: Decimal = Decimal("1.10")) -> None:
        self.rate = rate

    def to_eur(self, amount: Decimal, currency: str, on: date) -> Decimal:
        if currency == "EUR":
            return amount
        return amount / self.rate


def _ct(
    dt: date,
    tx_type: str,
    currency: str,
    amount: Decimal,
    description: str,
) -> CashTransaction:
    return CashTransaction(
        account_id="X",
        tx_type=tx_type,
        currency=currency,
        fx_rate_to_base=Decimal(1),
        date_time=dt,
        settle_date=dt,
        amount=amount,
        description=description,
    )


def test_dividend_and_wht_same_day_pair_correctly():
    txs = [
        _ct(date(2025, 3, 26), "Dividends", "USD", Decimal("86.63"), "META PLATFORMS INC CLASS A"),
        _ct(
            date(2025, 3, 26),
            "Withholding Tax",
            "USD",
            Decimal("-12.99"),
            "META PLATFORMS INC CLASS A",
        ),
    ]
    lines = compute_rl(txs, _StubFx(), 2025)
    assert len(lines) == 1
    assert lines[0].gross_amount == Decimal("86.63")
    assert lines[0].wht_amount == Decimal("12.99")


def test_multiple_quarterly_dividends_dont_collide():
    """Regression: all META quarterly WHT entries used to pile onto the
    first META dividend row because the strong-match ignored the date."""
    txs = []
    quarters = [
        (date(2025, 3, 26), Decimal("86.63"), Decimal("-12.99")),
        (date(2025, 6, 26), Decimal("95.03"), Decimal("-14.25")),
        (date(2025, 9, 29), Decimal("72.45"), Decimal("-10.87")),
        (date(2025, 12, 23), Decimal("23.10"), Decimal("-3.47")),
    ]
    for d, gross, wht in quarters:
        txs.append(_ct(d, "Dividends", "USD", gross, "META PLATFORMS INC CLASS A"))
        txs.append(_ct(d, "Withholding Tax", "USD", wht, "META PLATFORMS INC CLASS A"))
    lines = compute_rl(txs, _StubFx(), 2025)
    assert len(lines) == 4
    grosses = [line.gross_amount for line in lines]
    whts = [line.wht_amount for line in lines]
    assert grosses == [Decimal("86.63"), Decimal("95.03"), Decimal("72.45"), Decimal("23.10")]
    assert whts == [Decimal("12.99"), Decimal("14.25"), Decimal("10.87"), Decimal("3.47")]


def test_dividend_and_interest_same_month_dont_steal_wht():
    """Regression: a META dividend WHT used to be matched to the
    September USD broker interest credit because both landed in the same
    month + currency and the matcher had no way to tell them apart."""
    txs = [
        _ct(
            date(2025, 9, 4),
            "Broker Interest Received",
            "USD",
            Decimal("2.99"),
            "USD CREDIT INT FOR AUG-2025",
        ),
        _ct(
            date(2025, 9, 5),
            "Withholding Tax",
            "USD",
            Decimal("-0.60"),
            "WITHHOLDING @ 20% ON CREDIT INT FOR AUG-2025",
        ),
        _ct(date(2025, 9, 29), "Dividends", "USD", Decimal("72.45"), "META PLATFORMS INC CLASS A"),
        _ct(
            date(2025, 9, 29),
            "Withholding Tax",
            "USD",
            Decimal("-10.87"),
            "META PLATFORMS INC CLASS A",
        ),
    ]
    lines = compute_rl(txs, _StubFx(), 2025)
    assert len(lines) == 2
    by_desc = {line.description: line for line in lines}
    assert by_desc["USD CREDIT INT FOR AUG-2025"].wht_amount == Decimal("0.60")
    assert by_desc["META PLATFORMS INC CLASS A"].wht_amount == Decimal("10.87")


def test_credit_interest_period_match_works_across_days():
    """Broker interest is credited on day N, its WHT often on day N+1."""
    txs = [
        _ct(
            date(2025, 9, 4),
            "Broker Interest Received",
            "USD",
            Decimal("2.99"),
            "USD CREDIT INT FOR AUG-2025",
        ),
        _ct(
            date(2025, 9, 5),
            "Withholding Tax",
            "USD",
            Decimal("-0.60"),
            "WITHHOLDING @ 20% ON CREDIT INT FOR AUG-2025",
        ),
    ]
    lines = compute_rl(txs, _StubFx(), 2025)
    assert len(lines) == 1
    assert lines[0].wht_amount == Decimal("0.60")


def test_negative_amount_entries_excluded():
    """Refunds / corrections that appear as negative non-WHT entries
    shouldn't be treated as income."""
    txs = [
        _ct(date(2025, 3, 26), "Dividends", "USD", Decimal("-5.00"), "REFUND"),
        _ct(date(2025, 3, 26), "Dividends", "USD", Decimal("86.63"), "META PLATFORMS INC CLASS A"),
    ]
    lines = compute_rl(txs, _StubFx(), 2025)
    assert len(lines) == 1
    assert lines[0].description == "META PLATFORMS INC CLASS A"


def test_other_year_entries_ignored():
    txs = [
        _ct(date(2024, 3, 26), "Dividends", "USD", Decimal("100"), "META PLATFORMS INC CLASS A"),
        _ct(date(2025, 3, 26), "Dividends", "USD", Decimal("86.63"), "META PLATFORMS INC CLASS A"),
    ]
    lines = compute_rl(txs, _StubFx(), 2025)
    assert len(lines) == 1
    assert lines[0].gross_amount == Decimal("86.63")
