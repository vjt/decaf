"""Parse Schwab Annual Withholding Statement PDFs for RSU vest FMVs.

Extracts the Fair Market Value per vest date from the Tax Details section.
Uses the ITA jurisdiction FMV when available (Italian tax resident),
falls back to IRL (Irish tax resident for pre-move vests).

Requires pdftotext (poppler-utils) on the system.
"""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict, cast

# IRL-1 is not a valid Python identifier, so we use the functional form.
_TaxDetailBlock = TypedDict(
    "_TaxDetailBlock",
    {"ITA": Decimal, "IRL": Decimal, "IRL-1": Decimal},
    total=False,
)

logger = logging.getLogger(__name__)


def parse_vest_fmvs(pdf_paths: list[Path]) -> dict[date, Decimal]:
    """Extract vest date → FMV mapping from one or more withholding PDFs.

    Returns a dict mapping each vest date to the authoritative FMV
    for Italian tax purposes.
    """
    result: dict[date, Decimal] = {}
    for path in sorted(pdf_paths):
        fmvs = _parse_single_pdf(path)
        result.update(fmvs)
        logger.info("Parsed %s: %d vest dates", path.name, len(fmvs))
    return result


def _parse_single_pdf(pdf_path: Path) -> dict[date, Decimal]:
    """Parse a single Annual Withholding Statement PDF."""
    text = _pdftotext(pdf_path)

    # Step 1: Extract (vest_date, award_id) pairs from Share Transaction table
    vest_awards = _parse_share_transactions(text)

    # Step 2: Extract FMVs per award block from Tax Details
    award_fmvs = _parse_tax_details(text)

    # Step 3: Map vest dates to FMVs
    # Award blocks in Tax Details appear in same order as Share Transaction rows
    result: dict[date, Decimal] = {}
    block_idx = 0

    # Group vest_awards by vest_date to know how many blocks per date
    from itertools import groupby
    for vest_date, group in groupby(vest_awards, key=lambda x: x[0]):
        awards_in_date = list(group)

        if vest_date in result:
            # Already have FMV for this date (from earlier block)
            block_idx += len(awards_in_date)
            continue

        # Take FMV from the first award block for this vest date
        if block_idx < len(award_fmvs):
            fmv_by_jur = award_fmvs[block_idx]
            # Prefer ITA, fall back to IRL
            fmv = fmv_by_jur.get("ITA") or fmv_by_jur.get("IRL") or fmv_by_jur.get("IRL-1")
            if fmv:
                result[vest_date] = fmv
                jur = "ITA" if "ITA" in fmv_by_jur else "IRL"
                logger.info("  %s: FMV %s = $%s", vest_date, jur, fmv)

        block_idx += len(awards_in_date)

    return result


def _parse_share_transactions(text: str) -> list[tuple[date, str]]:
    """Extract (vest_date, award_id) pairs from the Share Transaction table."""
    results = []
    for m in re.finditer(
        r'^\s+(\d{2}/\d{2}/\d{2})\s+(\d{7})\s+(\d{9})\b',
        text,
        re.MULTILINE,
    ):
        vest_date = _parse_date(m.group(1))
        award_id = m.group(3)
        results.append((vest_date, award_id))
    return results


def _parse_tax_details(text: str) -> list[_TaxDetailBlock]:
    """Extract FMV per jurisdiction for each award block in Tax Details.

    Returns a list of dicts, one per award block in document order.
    Each dict maps jurisdiction (IRL, IRL-1, ITA) to FMV.
    """
    blocks: list[_TaxDetailBlock] = []
    current_raw: dict[str, Decimal] | None = None

    for line in text.split("\n"):
        # New award block: line starts with award ID (9-digit number)
        award_match = re.match(r'\s+(\d{9})\s+', line)
        if award_match:
            if current_raw is not None:
                blocks.append(cast(_TaxDetailBlock, current_raw))
            current_raw = {}

        # Extract FMV and jurisdiction from this line
        fmv_match = re.search(r'\$([\d.]+)\s+(IRL(?:-1)?|ITA)\b(?!\s*Social)', line)
        if fmv_match and current_raw is not None:
            jur = fmv_match.group(2)
            fmv = Decimal(fmv_match.group(1))
            current_raw[jur] = fmv

    # Don't forget the last block
    if current_raw is not None:
        blocks.append(cast(_TaxDetailBlock, current_raw))

    return blocks


def _parse_date(date_str: str) -> date:
    """Parse MM/DD/YY date."""
    return datetime.strptime(date_str, "%m/%d/%y").date()


def _pdftotext(pdf_path: Path) -> str:
    """Extract text from PDF using pdftotext with layout preservation."""
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
