"""Quadro RL - Redditi di capitale (investment income).

Interest earned on cash balances and dividends from foreign brokers.
Reports gross income, foreign withholding tax (ritenuta alla fonte),
and net amount. Taxed at 26%.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from decaf.fx import FxService
from decaf.models import CashTransaction, RLLine

_Q = Decimal("0.01")


def compute_rl(
    cash_transactions: list[CashTransaction],
    fx: FxService,
    tax_year: int,
) -> list[RLLine]:
    """Compute Quadro RL lines for interest/dividend income.

    Pairs each income entry with its matching withholding tax by
    currency + month. WHT entries are consumed once matched to avoid
    double-counting when multiple income entries fall in the same month.
    """
    income_entries = [
        ct
        for ct in cash_transactions
        if ct.date_time.year == tax_year
        and ("Interest" in ct.tx_type or "Dividends" in ct.tx_type)
        and ct.amount > 0
    ]
    wht_entries = [
        ct
        for ct in cash_transactions
        if ct.date_time.year == tax_year and "Withholding" in ct.tx_type
    ]

    # Track consumed WHT entries to avoid double-counting
    consumed_wht: set[int] = set()
    lines: list[RLLine] = []

    for income in income_entries:
        # Match WHT: same currency, same month, not yet consumed
        matched_wht = Decimal(0)
        for i, wht in enumerate(wht_entries):
            if i in consumed_wht:
                continue
            if (
                wht.currency == income.currency
                and wht.date_time.year == income.date_time.year
                and wht.date_time.month == income.date_time.month
            ):
                matched_wht += wht.amount  # negative
                consumed_wht.add(i)

        gross_eur = fx.to_eur(income.amount, income.currency, income.settle_date)
        wht_eur = fx.to_eur(abs(matched_wht), income.currency, income.settle_date)

        lines.append(
            RLLine(
                description=income.description,
                currency=income.currency,
                gross_amount=income.amount,
                gross_amount_eur=gross_eur.quantize(_Q, rounding=ROUND_HALF_UP),
                wht_amount=abs(matched_wht),
                wht_amount_eur=wht_eur.quantize(_Q, rounding=ROUND_HALF_UP),
                net_amount_eur=(gross_eur - wht_eur).quantize(
                    _Q,
                    rounding=ROUND_HALF_UP,
                ),
            )
        )

    return lines
