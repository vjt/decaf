"""Tests for Quadro RT per-lot ECB conversion (art. 9 c. 2 TUIR)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from decaf.fx import FxService
from decaf.models import Trade
from decaf.quadro_rt import compute_rt


def _fx(usd_ecb_rates: dict[date, Decimal]) -> FxService:
    return FxService(ib_rates=[], ecb_rates=usd_ecb_rates)


def _sell_trade(
    *,
    symbol: str = "META",
    acquisition_date: date,
    trade_date: date,
    settle_date: date,
    proceeds: Decimal,
    cost: Decimal,
    broker_pnl: Decimal,
    quantity: Decimal = Decimal("-1"),
    currency: str = "USD",
    fx_rate_to_base: Decimal = Decimal("0"),
) -> Trade:
    return Trade(
        account_id="U1",
        asset_category="STK",
        symbol=symbol,
        isin="US30303M1027",
        description=f"{symbol} (acquired {acquisition_date})",
        currency=currency,
        fx_rate_to_base=fx_rate_to_base,
        trade_datetime=trade_date,
        settle_date=settle_date,
        buy_sell="SELL",
        quantity=quantity,
        trade_price=Decimal("600"),
        proceeds=proceeds,
        cost=cost,
        commission=Decimal(0),
        commission_currency=currency,
        broker_pnl_realized=broker_pnl,
        listing_exchange="NASDAQ",
        acquisition_date=acquisition_date,
    )


class TestPerLotEcb:
    def test_per_lot_ecb_conversion_uses_acquisition_rate(self) -> None:
        """Art. 9 c. 2 TUIR: cost basis converted at ECB(acquisition_date),
        proceeds at ECB(settle_date).

        Lot bought 2024-02-15 at $500 (ECB 1.08), sold 2025-09-10 settling
        2025-09-12 at $600 (ECB 1.12). Expected:
          cost_eur     = 500 / 1.08 = 462.96
          proceeds_eur = 600 / 1.12 = 535.71
          gain_eur     = 535.71 - 462.96 = 72.75

        Old code (single rate at settle): gain_eur = 100 / 1.12 = 89.29 WRONG.
        """
        rates = {
            date(2024, 2, 15): Decimal("1.08"),
            date(2025, 9, 10): Decimal("1.12"),
            date(2025, 9, 12): Decimal("1.12"),
        }
        trade = _sell_trade(
            acquisition_date=date(2024, 2, 15),
            trade_date=date(2025, 9, 10),
            settle_date=date(2025, 9, 12),
            proceeds=Decimal("600"),
            cost=Decimal("-500"),
            broker_pnl=Decimal("100"),
        )
        lines = compute_rt([trade], _fx(rates), 2025)
        assert len(lines) == 1
        line = lines[0]
        assert line.cost_basis_eur == Decimal("462.96"), f"cost: {line.cost_basis_eur}"
        assert line.proceeds_eur == Decimal("535.71"), f"proceeds: {line.proceeds_eur}"
        assert line.gain_loss_eur == Decimal("72.75"), f"gain: {line.gain_loss_eur}"

    def test_same_day_acquisition_and_sell_matches_single_rate(self) -> None:
        """When acquisition_date == settle_date and ECB rate is the same,
        per-lot result equals the old single-rate result."""
        rates = {date(2025, 9, 10): Decimal("1.10"), date(2025, 9, 12): Decimal("1.10")}
        trade = _sell_trade(
            acquisition_date=date(2025, 9, 10),
            trade_date=date(2025, 9, 10),
            settle_date=date(2025, 9, 12),
            proceeds=Decimal("1100"),
            cost=Decimal("-1000"),
            broker_pnl=Decimal("100"),
        )
        lines = compute_rt([trade], _fx(rates), 2025)
        assert len(lines) == 1
        line = lines[0]
        # 1100/1.10=1000, 1000/1.10=909.09, gain=90.91
        assert line.proceeds_eur == Decimal("1000.00")
        assert line.cost_basis_eur == Decimal("909.09")
        assert line.gain_loss_eur == Decimal("90.91")

    def test_falls_back_to_broker_rate_when_ecb_missing(self) -> None:
        """If ECB rate missing on either date, fall back to broker's
        fxRateToBase and log a warning."""
        trade = _sell_trade(
            acquisition_date=date(2024, 2, 15),
            trade_date=date(2025, 9, 10),
            settle_date=date(2025, 9, 12),
            proceeds=Decimal("600"),
            cost=Decimal("-500"),
            broker_pnl=Decimal("100"),
            fx_rate_to_base=Decimal("0.92"),
        )
        lines = compute_rt([trade], _fx({}), 2025)
        assert len(lines) == 1
        line = lines[0]
        # 600 * 0.92 = 552.00; 500 * 0.92 = 460.00; gain = 92.00
        assert line.proceeds_eur == Decimal("552.00")
        assert line.cost_basis_eur == Decimal("460.00")
        assert line.gain_loss_eur == Decimal("92.00")

    def test_eur_currency_uses_native_amounts(self) -> None:
        """EUR-denominated trade: no conversion needed."""
        trade = _sell_trade(
            acquisition_date=date(2024, 2, 15),
            trade_date=date(2025, 9, 10),
            settle_date=date(2025, 9, 12),
            proceeds=Decimal("600"),
            cost=Decimal("-500"),
            broker_pnl=Decimal("100"),
            currency="EUR",
        )
        lines = compute_rt([trade], _fx({}), 2025)
        assert len(lines) == 1
        line = lines[0]
        assert line.proceeds_eur == Decimal("600")
        assert line.cost_basis_eur == Decimal("500")
        assert line.gain_loss_eur == Decimal("100")
