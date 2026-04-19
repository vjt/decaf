"""Quadro RT — Capital gains/losses (Redditi Diversi).

Reports realized gains/losses on security sales (forex conversion
gains are computed separately by forex_gains.py).

Tax rate: 26%. Base imponibile per le partecipazioni =
corrispettivo - costo effettivo del lotto ceduto (circ. AdE
165/E/1998 §2.3.2): the broker tracks each lot and the account
holder selects which to sell (Tax Optimizer on Schwab, matching
method on IBKR). The broker reports P/L on the actual lot sold;
decaf converts proceeds and cost to EUR separately, per art. 9 c. 2
TUIR: proceeds at the ECB rate on the sell-settlement date, cost at
the ECB rate on the lot's acquisition date. Gain in EUR is the
subtraction of the two — never the broker's aggregated USD P/L
converted at a single rate.

Forex gains are only taxable if the forex threshold was breached.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from decaf.fx import FxService
from decaf.models import RTLine, Trade

logger = logging.getLogger(__name__)

_Q = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_Q, rounding=ROUND_HALF_UP)


def compute_rt(
    trades: list[Trade],
    fx: FxService,
    tax_year: int,
) -> list[RTLine]:
    """Compute Quadro RT lines for realized gains/losses.

    Forex trades are always skipped here — forex conversion gains
    are computed separately by forex_gains.py using LIFO per account,
    because brokers report zero P/L on forex conversions.
    """
    lines: list[RTLine] = []

    for t in trades:
        if not t.is_sell:
            continue
        if t.trade_datetime.year != tax_year:
            continue

        # Skip forex — handled by forex_gains.py
        if t.is_forex:
            continue

        if t.currency == "EUR":
            proceeds_eur = t.proceeds
            cost_eur = abs(t.cost)
            pnl_eur = t.broker_pnl_realized
            rate_used = Decimal(1)
            broker_pnl_converted = t.broker_pnl_realized
        else:
            ecb_sell = fx.ecb_rate(t.currency, t.settle_date)
            ecb_buy = fx.ecb_rate(t.currency, t.acquisition_date)
            if ecb_sell and ecb_buy:
                proceeds_eur = _q(t.proceeds / ecb_sell)
                cost_eur = _q(abs(t.cost) / ecb_buy)
                pnl_eur = _q(proceeds_eur - cost_eur)
                rate_used = ecb_sell
                # Broker's aggregated USD P/L converted at sell-date rate —
                # kept as a comparison column. Diverges from pnl_eur whenever
                # ecb_buy != ecb_sell (cross-year lots).
                broker_pnl_converted = _q(t.broker_pnl_realized / ecb_sell)
            else:
                proceeds_eur = _q(t.proceeds * t.fx_rate_to_base)
                cost_eur = _q(abs(t.cost) * t.fx_rate_to_base)
                pnl_eur = _q(proceeds_eur - cost_eur)
                rate_used = t.fx_rate_to_base
                broker_pnl_converted = _q(
                    t.broker_pnl_realized * t.fx_rate_to_base,
                )
                logger.warning(
                    "Quadro RT %s %s: missing ECB rate on %s or %s, "
                    "fell back to broker fxRateToBase %s",
                    t.symbol, t.trade_datetime,
                    t.settle_date, t.acquisition_date, t.fx_rate_to_base,
                )

        lines.append(RTLine(
            symbol=t.symbol,
            isin=t.isin,
            long_description=t.description,
            acquisition_date=t.acquisition_date,
            sell_date=t.trade_datetime,
            quantity=abs(t.quantity),
            proceeds_eur=proceeds_eur,
            cost_basis_eur=cost_eur,
            gain_loss_eur=pnl_eur,
            ecb_rate=rate_used,
            is_forex=False,
            broker_pnl=t.broker_pnl_realized,
            broker_pnl_eur=broker_pnl_converted,
        ))

    return lines
