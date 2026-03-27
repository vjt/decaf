"""Tests for forex threshold analysis."""

from datetime import date
from decimal import Decimal

from decaf.forex import ForexAnalysis, analyze_forex_threshold
from decaf.fx import FxService
from decaf.models import CashTransaction, ConversionRate, Trade


def _usd_deposit(settle: str, amount: str) -> CashTransaction:
    return CashTransaction(
        account_id="U1", tx_type="Deposits/Withdrawals", currency="USD",
        fx_rate_to_base=Decimal("0.92"), date_time=date.fromisoformat(settle),
        settle_date=date.fromisoformat(settle), amount=Decimal(amount),
        description="DEPOSIT",
    )


def _fx_service(ecb_rate: str = "1.08") -> FxService:
    """FxService with a constant ECB USD rate for all of 2025."""
    ecb = {}
    d = date(2025, 1, 1)
    end = date(2025, 12, 31)
    while d <= end:
        if d.weekday() < 5:  # business days only
            ecb[d] = Decimal(ecb_rate)
        d += __import__("datetime").timedelta(days=1)
    return FxService([], ecb)


class TestBelowThreshold:
    def test_zero_balance_not_breached(self) -> None:
        result = analyze_forex_threshold([], [], _fx_service(), 2025)
        assert not result.threshold_breached
        assert result.max_consecutive_business_days == 0
        assert result.first_breach_date is None
        assert len(result.daily_records) == 365

    def test_small_balance_not_breached(self) -> None:
        # Deposit 10,000 USD on Aug 20 → ~9,259 EUR at 1.08 rate
        # Well below 51,645.69 threshold
        txns = [_usd_deposit("2025-08-20", "10000")]
        result = analyze_forex_threshold([], txns, _fx_service(), 2025)
        assert not result.threshold_breached


class TestAboveThreshold:
    def test_large_balance_breached(self) -> None:
        # Deposit 60,000 USD on Aug 1 → ~55,555 EUR > threshold
        # Stays there for the rest of the year (>7 business days)
        txns = [_usd_deposit("2025-08-01", "60000")]
        result = analyze_forex_threshold([], txns, _fx_service(), 2025)
        assert result.threshold_breached
        assert result.max_consecutive_business_days > 7
        assert result.first_breach_date == date(2025, 8, 1)

    def test_exactly_seven_days_breached(self) -> None:
        # Deposit 60,000 USD on Mon Sep 1, withdraw on Wed Sep 10
        # Business days above: Sep 1,2,3,4,5,8,9 = 7 → breached
        txns = [
            _usd_deposit("2025-09-01", "60000"),
            _usd_deposit("2025-09-10", "-60000"),
        ]
        result = analyze_forex_threshold([], txns, _fx_service(), 2025)
        assert result.threshold_breached
        assert result.max_consecutive_business_days >= 7

    def test_six_days_not_breached(self) -> None:
        # Deposit 60,000 USD on Mon Sep 1, withdraw on Tue Sep 9
        # Business days above: Sep 1,2,3,4,5,8 = 6 → NOT breached
        txns = [
            _usd_deposit("2025-09-01", "60000"),
            _usd_deposit("2025-09-09", "-60000"),
        ]
        result = analyze_forex_threshold([], txns, _fx_service(), 2025)
        assert not result.threshold_breached
        assert result.max_consecutive_business_days == 6


class TestDailyRecords:
    def test_records_cover_full_year(self) -> None:
        result = analyze_forex_threshold([], [], _fx_service(), 2025)
        assert result.daily_records[0].date == date(2025, 1, 1)
        assert result.daily_records[-1].date == date(2025, 12, 31)
        assert len(result.daily_records) == 365

    def test_weekend_days_marked(self) -> None:
        result = analyze_forex_threshold([], [], _fx_service(), 2025)
        # Jan 4, 2025 is Saturday
        jan4 = next(r for r in result.daily_records if r.date == date(2025, 1, 4))
        assert not jan4.is_business_day

    def test_holiday_marked(self) -> None:
        result = analyze_forex_threshold([], [], _fx_service(), 2025)
        # Jan 1 is Capodanno (holiday, also Wednesday in 2025)
        jan1 = next(r for r in result.daily_records if r.date == date(2025, 1, 1))
        assert not jan1.is_business_day

    def test_balance_carries_forward(self) -> None:
        txns = [_usd_deposit("2025-06-02", "1000")]
        result = analyze_forex_threshold([], txns, _fx_service(), 2025)

        jun1 = next(r for r in result.daily_records if r.date == date(2025, 6, 1))
        jun2 = next(r for r in result.daily_records if r.date == date(2025, 6, 2))
        jun3 = next(r for r in result.daily_records if r.date == date(2025, 6, 3))

        assert jun1.usd_balance == Decimal(0)
        assert jun2.usd_balance == Decimal("1000")
        assert jun3.usd_balance == Decimal("1000")  # carried forward
