"""Tests for forex FIFO gains computation."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from decaf.forex_gains import compute_forex_gains
from decaf.fx import FxService
from decaf.models import CashTransaction, ForexGainEntry, Trade


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fx_service(rates: dict[date, Decimal] | None = None) -> FxService:
    """FxService with specified ECB rates (or constant 1.10 for all 2025 biz days)."""
    if rates is not None:
        return FxService([], rates)

    ecb: dict[date, Decimal] = {}
    d = date(2024, 1, 1)
    end = date(2025, 12, 31)
    while d <= end:
        if d.weekday() < 5:
            ecb[d] = Decimal("1.10")
        d += timedelta(days=1)
    return FxService([], ecb)


def _stock_sell(settle: str, proceeds: str, symbol: str = "META",
                commission: str = "0", account: str = "U1") -> Trade:
    """USD stock sell — acquires USD."""
    d = date.fromisoformat(settle)
    return Trade(
        account_id=account, asset_category="STK", symbol=symbol, isin="",
        description=f"SELL {symbol}", currency="USD",
        fx_rate_to_base=Decimal(0), trade_datetime=d, settle_date=d,
        buy_sell="SELL", quantity=Decimal("-10"),
        trade_price=Decimal("100"), proceeds=Decimal(proceeds),
        cost=Decimal("-500"), commission=Decimal(commission),
        commission_currency="USD", broker_pnl_realized=Decimal("500"),
    )


def _forex_buy_eur(settle: str, usd_amount: str, account: str = "U1") -> Trade:
    """BUY EUR.USD — disposes USD (proceeds negative)."""
    d = date.fromisoformat(settle)
    return Trade(
        account_id=account, asset_category="CASH", symbol="EUR.USD", isin="",
        description="EUR.USD", currency="USD",
        fx_rate_to_base=Decimal(0), trade_datetime=d, settle_date=d,
        buy_sell="BUY", quantity=Decimal("1000"),
        trade_price=Decimal("1.10"),
        proceeds=Decimal(f"-{usd_amount}"),
        cost=Decimal(0), commission=Decimal(0),
        commission_currency="USD", broker_pnl_realized=Decimal(0),
    )


def _dividend(settle: str, amount: str, account: str = "U1") -> CashTransaction:
    d = date.fromisoformat(settle)
    return CashTransaction(
        account_id=account, tx_type="Dividends", currency="USD",
        fx_rate_to_base=Decimal(0), date_time=d, settle_date=d,
        amount=Decimal(amount), description="DIVIDEND",
    )


def _wire_sent(settle: str, amount: str, account: str = "U1") -> CashTransaction:
    """Wire transfer out (negative amount)."""
    d = date.fromisoformat(settle)
    return CashTransaction(
        account_id=account, tx_type="Wire Sent", currency="USD",
        fx_rate_to_base=Decimal(0), date_time=d, settle_date=d,
        amount=Decimal(amount), description="WIRE OUT",
    )


# ---------------------------------------------------------------------------
# Basic FIFO
# ---------------------------------------------------------------------------


class TestBasicFifo:
    def test_single_acquisition_single_disposal(self) -> None:
        """Acquire 1000 USD, then dispose 1000 USD. Same rate = zero gain."""
        trades = [
            _stock_sell("2025-03-03", "1000"),
            _forex_buy_eur("2025-06-02", "1000"),
        ]
        gains = compute_forex_gains(trades, [], _fx_service(), 2025)

        assert len(gains) == 1
        assert gains[0].usd_amount == Decimal("1000")
        assert gains[0].acquisition_date == date(2025, 3, 3)
        assert gains[0].disposal_date == date(2025, 6, 2)
        # Same ECB rate → zero gain
        assert gains[0].gain_eur == Decimal("0.00")

    def test_rate_increase_produces_loss(self) -> None:
        """EUR/USD goes up (EUR strengthens) → converting USD back gives less EUR → loss."""
        # Acquire at 1.08 (1 USD = 0.9259 EUR), dispose at 1.12 (1 USD = 0.8929 EUR)
        rates = {
            date(2025, 3, 3): Decimal("1.08"),
            date(2025, 6, 2): Decimal("1.12"),
        }
        trades = [
            _stock_sell("2025-03-03", "1000"),
            _forex_buy_eur("2025-06-02", "1000"),
        ]
        gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        assert len(gains) == 1
        # 1000 × (1/1.12 - 1/1.08) = 1000 × (0.8929 - 0.9259) = -33.07
        assert gains[0].gain_eur < 0
        assert gains[0].gain_eur == Decimal("-33.07")

    def test_rate_decrease_produces_gain(self) -> None:
        """EUR/USD goes down (EUR weakens) → USD is worth more EUR → gain."""
        # Acquire at 1.12, dispose at 1.08
        rates = {
            date(2025, 3, 3): Decimal("1.12"),
            date(2025, 6, 2): Decimal("1.08"),
        }
        trades = [
            _stock_sell("2025-03-03", "1000"),
            _forex_buy_eur("2025-06-02", "1000"),
        ]
        gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        assert len(gains) == 1
        assert gains[0].gain_eur > 0
        assert gains[0].gain_eur == Decimal("33.07")


class TestFifoOrdering:
    def test_oldest_lot_consumed_first(self) -> None:
        """Two acquisitions at different rates, one disposal takes from oldest."""
        rates = {
            date(2025, 1, 2): Decimal("1.10"),   # first lot
            date(2025, 2, 3): Decimal("1.05"),   # second lot
            date(2025, 6, 2): Decimal("1.08"),   # disposal
        }
        trades = [
            _stock_sell("2025-01-02", "500"),     # first lot
            _stock_sell("2025-02-03", "500"),     # second lot
            _forex_buy_eur("2025-06-02", "500"),  # disposal
        ]
        gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        assert len(gains) == 1
        # Should consume from first lot (Jan 2, rate 1.10)
        assert gains[0].acquisition_date == date(2025, 1, 2)
        assert gains[0].ecb_rate_acquisition == Decimal("1.10")

    def test_partial_lot_consumption(self) -> None:
        """Dispose less than a full lot — remainder stays in queue."""
        rates = {
            date(2025, 1, 2): Decimal("1.10"),
            date(2025, 6, 2): Decimal("1.08"),
            date(2025, 9, 1): Decimal("1.06"),
        }
        trades = [
            _stock_sell("2025-01-02", "1000"),
            _forex_buy_eur("2025-06-02", "400"),
            _forex_buy_eur("2025-09-01", "400"),
        ]
        gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        assert len(gains) == 2
        # Both disposals come from the same lot (1000 USD at 1.10)
        assert gains[0].acquisition_date == date(2025, 1, 2)
        assert gains[0].usd_amount == Decimal("400")
        assert gains[1].acquisition_date == date(2025, 1, 2)
        assert gains[1].usd_amount == Decimal("400")

    def test_disposal_spans_multiple_lots(self) -> None:
        """One big disposal consumes multiple FIFO lots."""
        rates = {
            date(2025, 1, 2): Decimal("1.10"),
            date(2025, 2, 3): Decimal("1.08"),
            date(2025, 6, 2): Decimal("1.10"),
        }
        trades = [
            _stock_sell("2025-01-02", "300"),
            _stock_sell("2025-02-03", "300"),
            _forex_buy_eur("2025-06-02", "500"),
        ]
        gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        assert len(gains) == 2
        # First entry: 300 from lot 1
        assert gains[0].usd_amount == Decimal("300")
        assert gains[0].acquisition_date == date(2025, 1, 2)
        # Second entry: 200 from lot 2
        assert gains[1].usd_amount == Decimal("200")
        assert gains[1].acquisition_date == date(2025, 2, 3)


# ---------------------------------------------------------------------------
# Cash transaction sources
# ---------------------------------------------------------------------------


class TestCashTransactionSources:
    def test_dividends_as_acquisition(self) -> None:
        """Dividends in USD create acquisition lots."""
        rates = {
            date(2025, 3, 3): Decimal("1.10"),
            date(2025, 6, 2): Decimal("1.08"),
        }
        cash_txns = [_dividend("2025-03-03", "500")]
        trades = [_forex_buy_eur("2025-06-02", "500")]

        gains = compute_forex_gains(trades, cash_txns, _fx_service(rates), 2025)

        assert len(gains) == 1
        assert gains[0].acquisition_date == date(2025, 3, 3)
        assert gains[0].usd_amount == Decimal("500")

    def test_wire_sent_as_disposal(self) -> None:
        """Wire transfers out are disposals."""
        rates = {
            date(2025, 1, 2): Decimal("1.10"),
            date(2025, 6, 2): Decimal("1.08"),
        }
        trades = [_stock_sell("2025-01-02", "5000")]
        cash_txns = [_wire_sent("2025-06-02", "-3000")]

        gains = compute_forex_gains(trades, cash_txns, _fx_service(rates), 2025)

        assert len(gains) == 1
        assert gains[0].usd_amount == Decimal("3000")
        assert gains[0].disposal_date == date(2025, 6, 2)

    def test_mixed_sources(self) -> None:
        """Stock sells + dividends acquired, forex + wire disposed."""
        rates = {
            date(2025, 1, 2): Decimal("1.10"),
            date(2025, 2, 3): Decimal("1.10"),
            date(2025, 6, 2): Decimal("1.10"),
            date(2025, 9, 1): Decimal("1.10"),
        }
        trades = [
            _stock_sell("2025-01-02", "2000"),
            _forex_buy_eur("2025-06-02", "1000"),
        ]
        cash_txns = [
            _dividend("2025-02-03", "500"),
            _wire_sent("2025-09-01", "-1000"),
        ]
        gains = compute_forex_gains(trades, cash_txns, _fx_service(rates), 2025)

        # Two disposals: 1000 forex + 1000 wire
        assert len(gains) == 2
        total_disposed = sum(g.usd_amount for g in gains)
        assert total_disposed == Decimal("2000")


# ---------------------------------------------------------------------------
# Multi-year FIFO
# ---------------------------------------------------------------------------


class TestMultiYear:
    def test_prior_year_acquisition(self) -> None:
        """USD acquired in 2024, disposed in 2025 — only 2025 gain reported."""
        rates = {
            date(2024, 6, 3): Decimal("1.08"),
            date(2025, 3, 3): Decimal("1.12"),
        }
        trades = [
            _stock_sell("2024-06-03", "5000"),
            _forex_buy_eur("2025-03-03", "3000"),
        ]
        gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        assert len(gains) == 1
        assert gains[0].acquisition_date == date(2024, 6, 3)
        assert gains[0].disposal_date == date(2025, 3, 3)
        # 3000 × (1/1.12 - 1/1.08) = 3000 × -0.03307 = -99.21
        assert gains[0].gain_eur == Decimal("-99.21")

    def test_prior_year_disposal_not_reported(self) -> None:
        """Disposal in 2024 should not appear in 2025 report."""
        rates = {
            date(2024, 1, 2): Decimal("1.10"),
            date(2024, 6, 3): Decimal("1.08"),
            date(2025, 3, 3): Decimal("1.06"),
        }
        trades = [
            _stock_sell("2024-01-02", "5000"),
            _forex_buy_eur("2024-06-03", "2000"),   # 2024 disposal
            _forex_buy_eur("2025-03-03", "1000"),   # 2025 disposal
        ]
        gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        # Only the 2025 disposal should appear
        assert len(gains) == 1
        assert gains[0].disposal_date == date(2025, 3, 3)
        # The 2024 disposal consumed 2000 from the 5000 lot, so
        # the 2025 disposal takes from the remaining 3000
        assert gains[0].acquisition_date == date(2024, 1, 2)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_trades_no_gains(self) -> None:
        gains = compute_forex_gains([], [], _fx_service(), 2025)
        assert gains == []

    def test_acquisitions_only_no_gains(self) -> None:
        """If no disposals, no gains."""
        trades = [_stock_sell("2025-03-03", "5000")]
        gains = compute_forex_gains(trades, [], _fx_service(), 2025)
        assert gains == []

    def test_fifo_exhausted_logs_warning(self, caplog) -> None:
        """Disposing more than acquired should warn, not crash."""
        import logging
        rates = {
            date(2025, 1, 2): Decimal("1.10"),
            date(2025, 6, 2): Decimal("1.08"),
        }
        trades = [
            _stock_sell("2025-01-02", "100"),
            _forex_buy_eur("2025-06-02", "500"),
        ]
        with caplog.at_level(logging.WARNING, logger="decaf.forex_gains"):
            gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        # Should produce one gain entry for 100 (what was available)
        assert len(gains) == 1
        assert gains[0].usd_amount == Decimal("100")
        assert "FIFO queue exhausted" in caplog.text

    def test_same_day_acquisition_before_disposal(self) -> None:
        """Acquisition on same day as disposal — acquisition processed first."""
        rates = {date(2025, 3, 3): Decimal("1.10")}
        trades = [
            _stock_sell("2025-03-03", "1000"),
            _forex_buy_eur("2025-03-03", "800"),
        ]
        gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        assert len(gains) == 1
        assert gains[0].usd_amount == Decimal("800")

    def test_eur_cash_transactions_ignored(self) -> None:
        """EUR-denominated cash transactions should not create USD lots."""
        eur_dividend = CashTransaction(
            account_id="U1", tx_type="Dividends", currency="EUR",
            fx_rate_to_base=Decimal("1"), date_time=date(2025, 3, 3),
            settle_date=date(2025, 3, 3), amount=Decimal("500"),
            description="EUR DIVIDEND",
        )
        gains = compute_forex_gains([], [eur_dividend], _fx_service(), 2025)
        assert gains == []

    def test_stock_buy_not_acquisition(self) -> None:
        """Buying USD stock is NOT a forex acquisition (just exchanging USD for stock)."""
        buy = Trade(
            account_id="U1", asset_category="STK", symbol="META", isin="",
            description="BUY META", currency="USD",
            fx_rate_to_base=Decimal(0), trade_datetime=date(2025, 3, 3),
            settle_date=date(2025, 3, 3), buy_sell="BUY",
            quantity=Decimal("10"), trade_price=Decimal("500"),
            proceeds=Decimal("-5000"), cost=Decimal("-5000"),
            commission=Decimal("-5"), commission_currency="USD",
            broker_pnl_realized=Decimal(0),
        )
        gains = compute_forex_gains([buy], [], _fx_service(), 2025)
        assert gains == []


# ---------------------------------------------------------------------------
# Gain formula verification
# ---------------------------------------------------------------------------


class TestGainFormula:
    def test_exact_gain_calculation(self) -> None:
        """Verify: gain_eur = usd × (1/rate_disposal - 1/rate_acquisition)."""
        rates = {
            date(2025, 1, 2): Decimal("1.10"),
            date(2025, 6, 2): Decimal("1.05"),
        }
        trades = [
            _stock_sell("2025-01-02", "10000"),
            _forex_buy_eur("2025-06-02", "10000"),
        ]
        gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        assert len(gains) == 1
        # 10000 × (1/1.05 - 1/1.10) = 10000 × (0.952381 - 0.909091)
        # = 10000 × 0.043290 = 432.90
        expected = (Decimal("10000") / Decimal("1.05") - Decimal("10000") / Decimal("1.10"))
        assert gains[0].gain_eur == expected.quantize(Decimal("0.01"))

    def test_commission_reduces_acquisition(self) -> None:
        """Commission on stock sell reduces USD acquired."""
        rates = {
            date(2025, 1, 2): Decimal("1.10"),
            date(2025, 6, 2): Decimal("1.10"),
        }
        trades = [
            _stock_sell("2025-01-02", "1000", commission="-5"),
            _forex_buy_eur("2025-06-02", "995"),
        ]
        gains = compute_forex_gains(trades, [], _fx_service(rates), 2025)

        assert len(gains) == 1
        # Acquired 1000 - 5 = 995 USD
        assert gains[0].usd_amount == Decimal("995")
