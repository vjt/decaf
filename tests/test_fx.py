"""Tests for FX rate service."""

from datetime import date
from decimal import Decimal

from decaf.fx import FxService
from decaf.models import ConversionRate


def _make_ib_rates(*entries: tuple[str, str, str]) -> list[ConversionRate]:
    """Build IB ConversionRate list from (currency, date_str, rate) tuples."""
    return [
        ConversionRate(
            from_currency=cur,
            to_currency="EUR",
            report_date=date.fromisoformat(d),
            rate=Decimal(r),
        )
        for cur, d, r in entries
    ]


def _make_ecb_rates(*entries: tuple[str, str]) -> dict[date, Decimal]:
    """Build ECB rate dict from (date_str, rate) tuples."""
    return {date.fromisoformat(d): Decimal(r) for d, r in entries}


class TestToEur:
    def test_eur_passthrough(self) -> None:
        fx = FxService([], {})
        assert fx.to_eur(Decimal("100"), "EUR", date(2025, 12, 31)) == Decimal("100")

    def test_usd_with_ecb_rate(self) -> None:
        ecb = _make_ecb_rates(("2025-12-31", "1.08"))
        fx = FxService([], ecb)

        # 108 USD / 1.08 = 100 EUR
        result = fx.to_eur(Decimal("108"), "USD", date(2025, 12, 31))
        assert result == Decimal("100")

    def test_ecb_fill_forward_weekend(self) -> None:
        # Friday rate, query on Saturday
        ecb = _make_ecb_rates(("2025-12-26", "1.08"))
        fx = FxService([], ecb)

        result = fx.to_eur(Decimal("108"), "USD", date(2025, 12, 28))  # Sunday
        assert result == Decimal("100")

    def test_ib_fallback_when_no_ecb(self) -> None:
        ib = _make_ib_rates(("USD", "2025-12-31", "0.925"))
        fx = FxService(ib, {})

        # 100 USD * 0.925 = 92.5 EUR
        result = fx.to_eur(Decimal("100"), "USD", date(2025, 12, 31))
        assert result == Decimal("92.5")

    def test_ecb_preferred_over_ib(self) -> None:
        ecb = _make_ecb_rates(("2025-12-31", "1.08"))
        ib = _make_ib_rates(("USD", "2025-12-31", "0.99"))  # different
        fx = FxService(ib, ecb)

        # Should use ECB: 108 / 1.08 = 100
        result = fx.to_eur(Decimal("108"), "USD", date(2025, 12, 31))
        assert result == Decimal("100")

    def test_no_rate_raises(self) -> None:
        fx = FxService([], {})
        try:
            fx.to_eur(Decimal("100"), "USD", date(2025, 12, 31))
            assert False, "Should have raised"
        except ValueError as e:
            assert "No FX rate" in str(e)


class TestFillForward:
    def test_ib_fill_forward(self) -> None:
        ib = _make_ib_rates(("USD", "2025-12-29", "0.92"))  # Monday
        fx = FxService(ib, {})

        # Tuesday should find Monday's rate
        assert fx.ib_rate("USD", date(2025, 12, 30)) == Decimal("0.92")

    def test_ecb_fill_forward(self) -> None:
        ecb = _make_ecb_rates(("2025-12-29", "1.08"))
        fx = FxService([], ecb)

        assert fx.ecb_rate("USD", date(2025, 12, 31)) == Decimal("1.08")

    def test_fill_forward_limit(self) -> None:
        ecb = _make_ecb_rates(("2025-12-20", "1.08"))
        fx = FxService([], ecb)

        # 11 days back, exceeds max_lookback=5
        assert fx.ecb_rate("USD", date(2025, 12, 31)) is None

    def test_eur_always_one(self) -> None:
        fx = FxService([], {})
        assert fx.ecb_rate("EUR", date(2025, 12, 31)) == Decimal("1")
        assert fx.ib_rate("EUR", date(2025, 12, 31)) == Decimal("1")
