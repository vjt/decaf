"""Tests for forex threshold analysis."""

from datetime import date
from decimal import Decimal

from decaf.forex import analyze_forex_threshold
from decaf.fx import FxService
from decaf.models import CashTransaction, Trade


def _usd_deposit(settle: str, amount: str) -> CashTransaction:
    return CashTransaction(
        account_id="U1",
        tx_type="Deposits/Withdrawals",
        currency="USD",
        fx_rate_to_base=Decimal("0.92"),
        date_time=date.fromisoformat(settle),
        settle_date=date.fromisoformat(settle),
        amount=Decimal(amount),
        description="DEPOSIT",
    )


def _fx_service(ecb_rate: str = "1.08") -> FxService:
    """FxService with a constant ECB USD rate for 2024-12 + all of 2025.

    Includes late December 2024 so the Jan 1 rate lookup (fill-forward
    from the last business day) works correctly.
    """
    ecb = {}
    d = date(2024, 12, 28)
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


class TestCarryOverBalance:
    def test_prior_year_balance_carried_over(self) -> None:
        """USD deposited in 2024 should carry over to Jan 1 2025."""
        # 60,000 USD deposited in 2024 → above threshold from Jan 1 2025
        txns = [_usd_deposit("2024-06-15", "60000")]
        # Need ECB rates for 2024 too (for the deposit date) — but the
        # balance reconstruction doesn't need rates, only the threshold check does.
        # The FxService needs rates for 2025 to convert.
        result = analyze_forex_threshold([], txns, _fx_service(), 2025)
        assert result.threshold_breached
        # Should be breached from day 1
        assert result.first_breach_date == date(2025, 1, 2)  # Jan 1 is holiday

    def test_prior_year_balance_with_withdrawal(self) -> None:
        """Prior-year deposit minus prior-year withdrawal = net carry-over."""
        txns = [
            _usd_deposit("2024-03-01", "60000"),
            _usd_deposit("2024-09-01", "-55000"),  # withdraw most of it
        ]
        # Net carry-over: 5,000 USD → ~4,630 EUR at 1.08 → below threshold
        result = analyze_forex_threshold([], txns, _fx_service(), 2025)
        assert not result.threshold_breached

    def test_zero_carry_over_when_no_prior_data(self) -> None:
        """No prior-year events → balance starts at 0 on Jan 1."""
        result = analyze_forex_threshold([], [], _fx_service(), 2025)
        jan1 = next(r for r in result.daily_records if r.date == date(2025, 1, 1))
        assert jan1.usd_balance == 0


class TestRsuVestExclusion:
    def test_rsu_vest_does_not_affect_balance(self) -> None:
        """RSU vests (shares granted, no cash) must not change USD balance."""
        vest = Trade(
            account_id="XXX666",
            asset_category="STK",
            symbol="MOSC",
            isin="US0000000010",
            description="Stock Plan Activity",
            currency="USD",
            fx_rate_to_base=Decimal(0),
            trade_datetime=date(2025, 5, 15),
            settle_date=date(2025, 5, 16),
            buy_sell="BUY",
            quantity=Decimal("10"),
            trade_price=Decimal("500"),
            proceeds=Decimal("-5000"),
            cost=Decimal("-5000"),
            commission=Decimal(0),
            commission_currency="USD",
            broker_pnl_realized=Decimal(0),
            listing_exchange="",
            acquisition_date=date(2025, 3, 3),
        )
        result = analyze_forex_threshold([vest], [], _fx_service(), 2025)
        # Vest should not create any USD balance
        may16 = next(r for r in result.daily_records if r.date == date(2025, 5, 16))
        assert may16.usd_balance == 0

    def test_real_stock_buy_does_affect_balance(self) -> None:
        """A real market buy (with commission) DOES decrease USD cash."""
        buy = Trade(
            account_id="U1",
            asset_category="STK",
            symbol="LLY",
            isin="US5324571083",
            description="BUY LLY",
            currency="USD",
            fx_rate_to_base=Decimal("0.92"),
            trade_datetime=date(2025, 5, 15),
            settle_date=date(2025, 5, 16),
            buy_sell="BUY",
            quantity=Decimal("10"),
            trade_price=Decimal("500"),
            proceeds=Decimal("-5000"),
            cost=Decimal("-5005"),
            commission=Decimal("-5"),
            commission_currency="USD",
            broker_pnl_realized=Decimal(0),
            listing_exchange="",
            acquisition_date=date(2025, 3, 3),
        )
        # First deposit USD, then buy stock
        txns = [_usd_deposit("2025-01-02", "10000")]
        result = analyze_forex_threshold([buy], txns, _fx_service(), 2025)
        may16 = next(r for r in result.daily_records if r.date == date(2025, 5, 16))
        # 10000 deposit - 5000 proceeds - 5 commission = 4995
        assert may16.usd_balance == Decimal("4995")


class TestJan1Rate:
    def test_fixed_jan1_rate_used_for_threshold(self) -> None:
        """Threshold conversion must use Jan 1 rate, not daily rate."""
        # Jan 1 rate = 1.08, but later in the year rate is 1.20
        ecb = {}
        d = date(2024, 12, 29)
        while d <= date(2025, 12, 31):
            if d.weekday() < 5:
                # Jan 1 falls back to Dec 31 rate = 1.08
                if d <= date(2025, 1, 31):
                    ecb[d] = Decimal("1.08")
                else:
                    ecb[d] = Decimal("1.20")
            d += __import__("datetime").timedelta(days=1)
        fx = FxService([], ecb)

        # 56,000 USD at 1.08 = 51,851 EUR > threshold
        # 56,000 USD at 1.20 = 46,667 EUR < threshold
        # With Jan 1 rate (1.08), should be ABOVE threshold
        txns = [_usd_deposit("2025-06-02", "56000")]
        result = analyze_forex_threshold([], txns, fx, 2025)
        assert result.threshold_breached

        # The EUR equivalent should use 1.08, not the daily 1.20
        jun2 = next(r for r in result.daily_records if r.date == date(2025, 6, 2))
        expected_eur = Decimal("56000") / Decimal("1.08")
        assert abs(jun2.eur_equivalent - expected_eur) < Decimal("0.01")


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
