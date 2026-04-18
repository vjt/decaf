"""Forex LIFO gains computation (art. 67(1)(c-ter) TUIR).

Neither broker provides forex P/L:
- IBKR EUR.USD trades have broker_pnl_realized=0 and cost=0
- Schwab wire transfers aren't modeled as forex trades

We compute gains ourselves applying LIFO lot matching per single account,
as mandated by art. 67 c. 1-bis TUIR and clarified in AdE risposta a
interpello n. 204/2023:

    "si considerano cedute per prime ... le valute ... acquisite
     in data piu' recente"  (art. 67 c. 1-bis)

    "la determinazione delle plusvalenze ... deve essere effettuata
     analiticamente e distintamente, per ciascun conto"
     (risposta 204/2023)

Acquisitions (USD inflow):
- Stock sell proceeds, dividends, interest credited in USD

Disposals (USD outflow):
- EUR.USD conversions (IBKR), wire transfers out (Schwab, IBKR)

Each account keeps its own LIFO queue. Lots never cross between
accounts: a stock sell on Schwab does NOT fund a disposal on IBKR.
Cross-account same-currency giroconti (art. 67 neutrality per
Risoluzione 60/E del 09/12/2024) are not yet matched — documented as
limitation in doc/NORMATIVA.md §Semplificazioni applicate.

Formula per disposal (unchanged):
    gain_eur = usd_amount * (1/ecb_rate_disposal - 1/ecb_rate_acquisition)
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from decaf.fx import FxService
from decaf.models import CashTransaction, ForexGainEntry, RTLine, Trade

logger = logging.getLogger(__name__)

# Cash transaction types that represent USD income (acquisitions)
_USD_INCOME_TYPES = {
    "Dividends",
    "Broker Interest Received",
    "Broker Interest Paid",       # negative amounts, handled naturally
    "Payment In Lieu Of Dividends",
    "Sell Proceeds",              # Schwab sells (includes sell-to-cover)
}

# Cash transaction types that represent wire transfers OUT (disposals)
_WIRE_TRANSFER_TYPES = {
    "Wire Sent",
    "Wire Funds Sent",
    "Deposits/Withdrawals",       # negative amounts = withdrawals
}


@dataclass
class _UsdLot:
    """A lot of USD in an account's LIFO queue."""
    date: date
    remaining: Decimal  # USD still available in this lot
    ecb_rate: Decimal   # EUR/USD rate at acquisition


def compute_forex_gains(
    trades: list[Trade],
    cash_transactions: list[CashTransaction],
    fx: FxService,
    tax_year: int,
) -> list[ForexGainEntry]:
    """Compute forex conversion gains using LIFO per account for a tax year.

    Takes ALL trades and cash transactions (across all years) to build
    each account's LIFO queue. Returns gains only for disposals within
    tax_year.

    Args:
        trades: All trades from all years (stock sells + forex conversions)
        cash_transactions: All cash transactions from all years
        fx: FX service with ECB rates loaded for all relevant years
        tax_year: Only report gains from disposals in this year
    """
    events = _collect_usd_events(trades, cash_transactions, fx)
    # acquisitions before disposals on the same day
    events.sort(key=lambda e: (e.date, e.is_disposal))

    # Per-account LIFO queues
    queues: dict[str, deque[_UsdLot]] = {}
    gains: list[ForexGainEntry] = []
    total_usd_acquired = Decimal(0)
    total_usd_disposed = Decimal(0)

    for event in events:
        q = queues.setdefault(event.account_id, deque())

        if not event.is_disposal:
            q.append(_UsdLot(
                date=event.date,
                remaining=event.usd_amount,
                ecb_rate=event.ecb_rate,
            ))
            total_usd_acquired += event.usd_amount
            continue

        to_dispose = event.usd_amount
        total_usd_disposed += to_dispose

        while to_dispose > 0 and q:
            lot = q[-1]  # LIFO: most-recently-acquired lot first
            consumed = min(lot.remaining, to_dispose)

            # gain_eur = usd * (1/rate_disposal - 1/rate_acquisition)
            eur_at_disposal = consumed / event.ecb_rate
            eur_at_acquisition = consumed / lot.ecb_rate
            gain_eur = (eur_at_disposal - eur_at_acquisition).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            )

            if event.date.year == tax_year:
                gains.append(ForexGainEntry(
                    disposal_date=event.date,
                    usd_amount=consumed,
                    acquisition_date=lot.date,
                    ecb_rate_acquisition=lot.ecb_rate,
                    ecb_rate_disposal=event.ecb_rate,
                    gain_eur=gain_eur,
                ))

            lot.remaining -= consumed
            to_dispose -= consumed

            if lot.remaining <= 0:
                q.pop()

        if to_dispose > 0:
            logger.warning(
                "LIFO queue exhausted for account %s: %.2f USD disposed "
                "on %s without matching acquisitions in the same account. "
                "Cross-account transfers (Risoluzione 60/E/2024) are not "
                "matched: handle manually if this is a giroconto.",
                event.account_id, float(to_dispose), event.date,
            )

    per_account_residual = {
        acct: sum((lot.remaining for lot in q), Decimal(0))
        for acct, q in queues.items()
    }
    logger.info(
        "Forex LIFO: %.2f USD acquired, %.2f USD disposed, "
        "%d gain entries for %d, residual per account: %s",
        float(total_usd_acquired), float(total_usd_disposed),
        len(gains), tax_year,
        {acct: float(r) for acct, r in per_account_residual.items()},
    )

    return gains


def forex_gains_to_rt_lines(entries: list[ForexGainEntry]) -> list[RTLine]:
    """Convert forex LIFO gain entries to Quadro RT lines."""
    _q = Decimal("0.01")
    lines: list[RTLine] = []
    for entry in entries:
        eur_at_disposal = (
            entry.usd_amount / entry.ecb_rate_disposal
        ).quantize(_q, ROUND_HALF_UP)
        eur_at_acquisition = (
            entry.usd_amount / entry.ecb_rate_acquisition
        ).quantize(_q, ROUND_HALF_UP)
        lines.append(RTLine(
            symbol="EUR.USD",
            isin="",
            long_description="Plusvalenza valutaria USD (LIFO per conto)",
            acquisition_date=entry.acquisition_date,
            sell_date=entry.disposal_date,
            quantity=entry.usd_amount,
            proceeds_eur=eur_at_disposal,
            cost_basis_eur=eur_at_acquisition,
            gain_loss_eur=entry.gain_eur,
            ecb_rate=entry.ecb_rate_disposal,
            is_forex=True,
            broker_pnl=Decimal(0),
            broker_pnl_eur=Decimal(0),
        ))
    return lines


# ---------------------------------------------------------------------------
# Event collection
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _UsdEvent:
    """A USD cash flow event for LIFO processing."""
    date: date
    account_id: str      # isolates lot matching per-account
    usd_amount: Decimal  # always positive
    ecb_rate: Decimal    # EUR/USD at event date
    is_disposal: bool    # True = USD leaving, False = USD entering
    description: str     # for debugging


def _collect_usd_events(
    trades: list[Trade],
    cash_transactions: list[CashTransaction],
    fx: FxService,
) -> list[_UsdEvent]:
    """Collect all USD acquisition and disposal events."""
    events: list[_UsdEvent] = []

    # Accounts with "Sell Proceeds" cash txns — skip their stock sells
    # to avoid double-counting (Schwab sells include sell-to-cover)
    accounts_with_sell_proceeds = {
        ct.account_id for ct in cash_transactions
        if ct.tx_type == "Sell Proceeds"
    }

    for t in trades:
        if t.asset_category == "STK" and t.currency == "USD" and t.is_sell:
            if t.account_id in accounts_with_sell_proceeds:
                continue  # handled via "Sell Proceeds" cash transactions
            # Stock sell → USD acquired (proceeds are positive for sells)
            usd_amount = t.proceeds + t.commission  # commission is negative
            if usd_amount > 0:
                ecb_rate = _get_ecb_rate(fx, t.settle_date)
                if ecb_rate:
                    events.append(_UsdEvent(
                        date=t.settle_date,
                        account_id=t.account_id,
                        usd_amount=usd_amount,
                        ecb_rate=ecb_rate,
                        is_disposal=False,
                        description=f"SELL {t.symbol} {t.quantity}",
                    ))

        elif t.asset_category == "CASH" and "USD" in t.symbol and t.currency == "USD":
            # EUR.USD forex conversion
            net_usd = t.proceeds + t.commission
            if net_usd < 0:
                # BUY EUR.USD → spending USD → disposal
                ecb_rate = _get_ecb_rate(fx, t.settle_date)
                if ecb_rate:
                    events.append(_UsdEvent(
                        date=t.settle_date,
                        account_id=t.account_id,
                        usd_amount=abs(net_usd),
                        ecb_rate=ecb_rate,
                        is_disposal=True,
                        description=f"EUR.USD conversion {t.quantity}",
                    ))
            elif net_usd > 0:
                # SELL EUR.USD → receiving USD → acquisition
                ecb_rate = _get_ecb_rate(fx, t.settle_date)
                if ecb_rate:
                    events.append(_UsdEvent(
                        date=t.settle_date,
                        account_id=t.account_id,
                        usd_amount=net_usd,
                        ecb_rate=ecb_rate,
                        is_disposal=False,
                        description=f"EUR.USD conversion {t.quantity}",
                    ))

    for ct in cash_transactions:
        if ct.currency != "USD":
            continue

        if ct.tx_type in _USD_INCOME_TYPES and ct.amount > 0:
            # Dividend / interest → USD acquired
            ecb_rate = _get_ecb_rate(fx, ct.settle_date)
            if ecb_rate:
                events.append(_UsdEvent(
                    date=ct.settle_date,
                    account_id=ct.account_id,
                    usd_amount=ct.amount,
                    ecb_rate=ecb_rate,
                    is_disposal=False,
                    description=f"{ct.tx_type}: {ct.description}",
                ))

        elif ct.tx_type in _WIRE_TRANSFER_TYPES and ct.amount < 0:
            # Wire transfer out → USD disposed
            ecb_rate = _get_ecb_rate(fx, ct.settle_date)
            if ecb_rate:
                events.append(_UsdEvent(
                    date=ct.settle_date,
                    account_id=ct.account_id,
                    usd_amount=abs(ct.amount),
                    ecb_rate=ecb_rate,
                    is_disposal=True,
                    description=f"{ct.tx_type}: {ct.description}",
                ))

    return events


def _get_ecb_rate(fx: FxService, d: date) -> Decimal | None:
    """Get ECB rate, logging warning on failure."""
    rate = fx.ecb_rate("USD", d)
    if rate is None:
        logger.warning("No ECB rate for USD on %s — skipping event", d)
    return rate
