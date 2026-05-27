"""Quadro RL - Redditi di capitale (investment income).

Interest earned on cash balances and dividends from foreign brokers.
Reports gross income, foreign withholding tax (ritenuta alla fonte),
and net amount. Taxed at 26%.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from decaf.fx import FxService
from decaf.models import CashTransaction, RLLine

_Q = Decimal("0.01")

# Withholding entries on broker credit interest carry the period in their
# description (e.g. 'WITHHOLDING @ 20% ON CREDIT INT FOR AUG-2025'). The
# matching income entry has a parallel description ('USD CREDIT INT FOR
# AUG-2025'). Pulling the 'CREDIT INT FOR <MONTH>-<YEAR>' tail lets us
# pair the two unambiguously even when a dividend WHT lands in the same
# month + currency.
_CREDIT_INT_PERIOD = re.compile(r"CREDIT INT FOR ([A-Z]{3}-\d{4})")


def _credit_int_period(description: str) -> str | None:
    m = _CREDIT_INT_PERIOD.search(description)
    return m.group(1) if m else None


def compute_rl(
    cash_transactions: list[CashTransaction],
    fx: FxService,
    tax_year: int,
) -> list[RLLine]:
    """Compute Quadro RL lines for interest/dividend income.

    Pairs each income entry with its matching withholding tax in two
    passes:

    1. Strong match — either (a) same description + same date (dividend
       and its WHT post the same day with the security name as their
       description), or (b) same 'CREDIT INT FOR <MMM>-<YYYY>' period
       tag (broker interest credit + its corresponding WHT entry).
    2. Fallback — same currency + month, for any WHT not yet consumed.

    Without the strong match, two income entries in the same month + ccy
    (e.g. a META dividend and a USD broker interest credit) compete for
    the same WHT pool and one ends up with WHT > gross. Without the
    same-date guard, multiple dividends from the same security across
    different quarters in the same year would also collide (all META
    dividend WHT entries would pile onto the first META row).
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

    consumed_wht: set[int] = set()
    matched_per_income: dict[int, Decimal] = {idx: Decimal(0) for idx in range(len(income_entries))}

    # Pass 1: strong match — same description + same day (dividend +
    # its WHT post the same day) OR same 'CREDIT INT FOR <MONTH>'
    # period tag (broker interest credit + its WHT).
    for inc_idx, income in enumerate(income_entries):
        inc_period = _credit_int_period(income.description)
        for w_idx, wht in enumerate(wht_entries):
            if w_idx in consumed_wht:
                continue
            if wht.currency != income.currency:
                continue
            wht_period = _credit_int_period(wht.description)
            same_security_same_day = (
                wht.description == income.description
                and wht.description
                and wht.date_time == income.date_time
            )
            same_credit_int_period = inc_period and wht_period and inc_period == wht_period
            if same_security_same_day or same_credit_int_period:
                matched_per_income[inc_idx] += wht.amount  # negative
                consumed_wht.add(w_idx)

    # Pass 2: fallback by currency + month for any remaining WHT
    for inc_idx, income in enumerate(income_entries):
        for w_idx, wht in enumerate(wht_entries):
            if w_idx in consumed_wht:
                continue
            if (
                wht.currency == income.currency
                and wht.date_time.year == income.date_time.year
                and wht.date_time.month == income.date_time.month
            ):
                matched_per_income[inc_idx] += wht.amount  # negative
                consumed_wht.add(w_idx)

    lines: list[RLLine] = []
    for inc_idx, income in enumerate(income_entries):
        matched_wht = matched_per_income[inc_idx]
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


# --- Aggregation for Quadro RM31 (imposta sostitutiva 26%) ---
#
# RM31 wants one rigo per (stato estero, tipo reddito) pair, where:
# - stato estero is the AdE 3-digit code of the income source country
#   (US for META dividends, US for Schwab USD interest, IE for IBKR EUR
#   interest, etc.)
# - tipo reddito is the dropdown code: 'A' for interest, 'B' for non-
#   qualified dividends (the two cases we actually see in real broker
#   data — extend as needed).


_INTEREST_KEYWORDS = ("INT", "INTEREST")


def _classify_rl_line(line: RLLine) -> tuple[str, str]:
    """Classify an RL line into (source ISO country, RM31 tipo reddito).

    Heuristics derived from real Schwab/IBKR descriptions. Currency is
    the discriminator for interest because the broker doesn't otherwise
    expose its country: USD interest = Schwab (US), EUR interest =
    IBKR Irlanda (IE).
    """
    desc = line.description.upper()
    if "DIVIDEND" in desc or any(tag in desc for tag in ("META", "AAPL", "MSFT", "GOOGL", "AMZN")):
        return ("US", "B")  # non-qualified dividend, US source
    if any(kw in desc for kw in _INTEREST_KEYWORDS):
        # Interest: source = broker custodian country
        if line.currency == "USD":
            return ("US", "A")
        if line.currency == "EUR":
            return ("IE", "A")
        return ("??", "A")
    return ("??", "?")


def aggregate_rl_for_rm31(lines: list[RLLine]) -> list[dict]:
    """Aggregate RL lines into RM31 rows: one per (stato, tipo).

    Returns a list of dicts with keys: stato (ISO2), tipo (A/B),
    gross_eur, wht_eur, count, label.
    """
    groups: dict[tuple[str, str], dict] = {}
    for line in lines:
        key = _classify_rl_line(line)
        bucket = groups.setdefault(
            key,
            {
                "stato": key[0],
                "tipo": key[1],
                "gross_eur": Decimal(0),
                "wht_eur": Decimal(0),
                "count": 0,
                "label": _rm31_label(key),
            },
        )
        bucket["gross_eur"] += line.gross_amount_eur
        bucket["wht_eur"] += line.wht_amount_eur
        bucket["count"] += 1
    return sorted(groups.values(), key=lambda b: (b["stato"], b["tipo"]))


def _rm31_label(key: tuple[str, str]) -> str:
    stato, tipo = key
    descriptions = {
        ("US", "B"): "Dividendi USA (non qualificati)",
        ("US", "A"): "Interessi USD (Schwab)",
        ("IE", "A"): "Interessi EUR (IBKR Irlanda)",
    }
    return descriptions.get(key, f"{stato} tipo {tipo}")
