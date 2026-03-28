"""Quadro RT — Capital gains/losses (Redditi Diversi).

Reports realized gains/losses on security sales and forex conversions.
Tax rate: 26%. We trust the broker's FIFO computation and convert
to EUR using the ECB rate at the sell settlement date.

Forex gains are only taxable if the forex threshold was breached.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from decaf.fx import FxService
from decaf.models import RTLine, Trade


def compute_rt(
    trades: list[Trade],
    fx: FxService,
    tax_year: int,
    forex_threshold_breached: bool,
) -> list[RTLine]:
    """Compute Quadro RT lines for realized gains/losses."""
    lines: list[RTLine] = []

    for t in trades:
        if not t.is_sell:
            continue
        if t.trade_datetime.year != tax_year:
            continue

        is_forex = t.is_forex

        # Skip forex trades if threshold not breached
        if is_forex and not forex_threshold_breached:
            continue

        # Convert broker's FIFO P/L to EUR at ECB rate on settlement date
        if t.currency == "EUR":
            pnl_eur = t.broker_pnl_realized
            proceeds_eur = t.proceeds
            cost_eur = abs(t.cost)
            broker_pnl_eur_ = t.broker_pnl_realized
        else:
            ecb_rate = fx.ecb_rate(t.currency, t.settle_date)
            if ecb_rate and ecb_rate != 0:
                pnl_eur = (t.broker_pnl_realized / ecb_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                proceeds_eur = (t.proceeds / ecb_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                cost_eur = (abs(t.cost) / ecb_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                broker_pnl_eur_ = pnl_eur
            else:
                # Fallback to broker's own fxRateToBase
                pnl_eur = (t.broker_pnl_realized * t.fx_rate_to_base).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                proceeds_eur = (t.proceeds * t.fx_rate_to_base).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                cost_eur = (abs(t.cost) * t.fx_rate_to_base).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                broker_pnl_eur_ = pnl_eur

        lines.append(RTLine(
            symbol=t.symbol,
            isin=t.isin,
            sell_date=t.trade_datetime,
            quantity=abs(t.quantity),
            proceeds_eur=proceeds_eur,
            cost_basis_eur=cost_eur,
            gain_loss_eur=pnl_eur,
            is_forex=is_forex,
            broker_pnl=t.broker_pnl_realized,
            broker_pnl_eur=broker_pnl_eur_,
        ))

    return lines
