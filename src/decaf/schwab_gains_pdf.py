"""Parse Schwab Year-End Summary PDFs for realized gains/losses.

Extracts per-lot realized gain/loss data from the "Realized Gain or (Loss)"
section. Each lot has: symbol, CUSIP, quantity, date acquired, date sold,
proceeds, cost basis, wash sale adjustment, and realized gain/loss.

Short-term and long-term are tracked separately (though Italian tax
doesn't distinguish — both are 26%).

Requires pdftotext (poppler-utils) on the system.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RealizedLot:
    """One lot-level realized gain/loss from a sell."""

    symbol: str
    cusip: str
    quantity: Decimal
    date_acquired: date
    date_sold: date
    proceeds: Decimal
    cost_basis: Decimal
    wash_sale_adj: Decimal
    gain_loss: Decimal
    is_long_term: bool


def parse_realized_gains(pdf_paths: list[Path]) -> list[RealizedLot]:
    """Parse realized gains from one or more Year-End Summary PDFs."""
    result: list[RealizedLot] = []
    for path in sorted(pdf_paths):
        lots = _parse_single_pdf(path)
        result.extend(lots)
        short = sum(1 for lot in lots if not lot.is_long_term)
        long_term = sum(1 for lot in lots if lot.is_long_term)
        logger.info(
            "Parsed %s: %d lots (%d short-term, %d long-term)",
            path.name,
            len(lots),
            short,
            long_term,
        )
    return result


def _parse_single_pdf(pdf_path: Path) -> list[RealizedLot]:
    """Parse a single Year-End Summary PDF."""
    text = _pdftotext(pdf_path)
    lots: list[RealizedLot] = []

    is_long_term = False

    for line in text.split("\n"):
        # Detect short/long-term section headers
        if "Long-Term Realized Gain" in line and "Short" not in line:
            is_long_term = True
        elif "Short-Term Realized Gain" in line:
            is_long_term = False

        # Parse transaction lines: symbol + CUSIP + numbers
        # Pattern: description CUSIP qty date_acq date_sold $ proceeds $ cost -- $ gain
        m = re.match(
            r"\s*(.+?)\s{2,}"  # Description (e.g., "META PLATFORMS INC CLASS")
            r"(\d{5}[A-Z]\d{3})\s+"  # CUSIP (e.g., 30303M102)
            r"([\d.]+)\s+"  # Quantity
            r"(\d{2}/\d{2}/\d{2})\s+"  # Date Acquired
            r"(\d{2}/\d{2}/\d{2})\s+"  # Date Sold
            r"\$\s*([\d,.]+)\s+"  # Total Proceeds
            r"\$\s*([\d,.]+)\s+"  # Cost Basis
            r"--\s+"  # Wash Sale (-- = none)
            r"\$\s*([\d,.()]+)",  # Realized Gain or (Loss)
            line,
        )
        if not m:
            continue

        description = m.group(1).strip()
        cusip = m.group(2)
        quantity = Decimal(m.group(3))
        date_acquired = _parse_date(m.group(4))
        date_sold = _parse_date(m.group(5))
        proceeds = _parse_amount(m.group(6))
        cost_basis = _parse_amount(m.group(7))
        gain_loss = _parse_amount(m.group(8))

        # Extract ticker from description
        symbol = _extract_symbol(description)

        lots.append(
            RealizedLot(
                symbol=symbol,
                cusip=cusip,
                quantity=quantity,
                date_acquired=date_acquired,
                date_sold=date_sold,
                proceeds=proceeds,
                cost_basis=cost_basis,
                wash_sale_adj=Decimal(0),
                gain_loss=gain_loss,
                is_long_term=is_long_term,
            )
        )

    return lots


def _extract_symbol(description: str) -> str:
    """Extract ticker symbol from description like 'META PLATFORMS INC CLASS'."""
    # First word is usually the ticker
    return description.split()[0] if description else ""


def _parse_date(date_str: str) -> date:
    """Parse MM/DD/YY date."""
    return datetime.strptime(date_str, "%m/%d/%y").date()


def _parse_amount(value: str) -> Decimal:
    """Parse dollar amount, handling parentheses for negative values."""
    clean = value.replace(",", "").replace(" ", "")
    if clean.startswith("(") and clean.endswith(")"):
        return -Decimal(clean[1:-1])
    return Decimal(clean)


def _pdftotext(pdf_path: Path) -> str:
    """Extract text from PDF using pdftotext with layout preservation."""
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
