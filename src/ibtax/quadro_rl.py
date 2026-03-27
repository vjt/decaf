"""Quadro RL — Investment income (Redditi di Capitale).

Interest earned on cash balances is "redditi di capitale", taxed at 26%.
Reports gross interest, foreign withholding tax, and net amount.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from ibtax.fx import FxService
from ibtax.models import CashTransaction, RLLine


def compute_rl(
    cash_transactions: list[CashTransaction],
    fx: FxService,
    tax_year: int,
) -> list[RLLine]:
    """Compute Quadro RL lines for interest income.

    Pairs interest entries with their corresponding withholding tax
    entries by currency and month.
    """
    # Separate interest and WHT entries
    interest_entries = [
        ct for ct in cash_transactions
        if ct.date_time.year == tax_year and "Interest" in ct.tx_type and ct.amount > 0
    ]
    wht_entries = [
        ct for ct in cash_transactions
        if ct.date_time.year == tax_year and "Withholding" in ct.tx_type
    ]

    lines: list[RLLine] = []

    for interest in interest_entries:
        # Find matching WHT (same currency, same month)
        matching_wht = [
            w for w in wht_entries
            if w.currency == interest.currency
            and w.date_time.year == interest.date_time.year
            and w.date_time.month == interest.date_time.month
        ]

        wht_amount = sum(w.amount for w in matching_wht)  # negative

        gross_eur = fx.to_eur(interest.amount, interest.currency, interest.settle_date)
        wht_eur = fx.to_eur(abs(wht_amount), interest.currency, interest.settle_date)

        lines.append(RLLine(
            description=interest.description,
            currency=interest.currency,
            gross_amount=interest.amount,
            gross_amount_eur=gross_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            wht_amount=abs(wht_amount),
            wht_amount_eur=wht_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            net_amount_eur=(gross_eur - wht_eur).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            ),
        ))

    return lines
