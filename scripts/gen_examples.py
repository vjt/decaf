"""Regenerate showcase outputs in examples/ for each fixture+year.

Mirrors what `decaf report --year N` produces but drives the pipeline
directly off the committed fixtures so contributors can eyeball real
xlsx/pdf/yaml without needing to ingest broker data first.

Run from repo root::

    python scripts/gen_examples.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

from decaf.cli import _load_and_build_report  # noqa: E402
from decaf.output_pdf import write_pdf  # noqa: E402
from decaf.output_xls import write_xls  # noqa: E402
from decaf.output_yaml import write_yaml  # noqa: E402
from decaf.parse import parse_statement_all  # noqa: E402
from decaf.schwab_parse import parse_schwab  # noqa: E402
from decaf.statement_store import StatementStore  # noqa: E402

_REF = _REPO / "tests" / "reference"
_ECB = _REF / "ecb_rates.db"
_OUT = _REPO / "examples"

# One entry per committed oracle
_FIXTURES: list[tuple[str, list[int]]] = [
    ("magnotta", [2024]),
    ("mosconi", [2023, 2024]),
    ("mascetti", [2024, 2025]),
]


def _build_db(fixture_dir: Path) -> Path:
    tmp = Path(tempfile.gettempdir()) / f"decaf_examples_{os.getpid()}_{fixture_dir.name}.db"
    tmp.unlink(missing_ok=True)

    for xml in sorted(fixture_dir.glob("*.xml")):
        with StatementStore(tmp) as store:
            store.store(parse_statement_all(xml.read_text()))

    schwab_json = sorted(fixture_dir.glob("Individual_*_Transactions_*.json"))
    gains_pdfs = sorted(fixture_dir.glob("Year-End Summary*.PDF"))
    vest_pdfs = sorted(fixture_dir.glob("Annual Withholding*.PDF"))
    if schwab_json and gains_pdfs and vest_pdfs:
        for j in schwab_json:
            with StatementStore(tmp) as store:
                store.store(parse_schwab(j, gains_pdfs, vest_pdfs))

    return tmp


def _load_prices(fixture_dir: Path) -> dict[int, dict[str, Decimal]]:
    p = fixture_dir / "prices.yaml"
    if not p.exists():
        return {}
    with open(p) as f:
        raw = yaml.safe_load(f) or {}
    return {
        int(y): {str(s): Decimal(str(v)) for s, v in (syms or {}).items()}
        for y, syms in raw.items()
    }


async def main() -> int:
    _OUT.mkdir(exist_ok=True)
    for fixture, years in _FIXTURES:
        fixture_dir = _REF / fixture
        out_dir = _OUT / fixture
        out_dir.mkdir(exist_ok=True)

        db = _build_db(fixture_dir)
        prices = _load_prices(fixture_dir)
        try:
            for year in years:
                report, _ = await _load_and_build_report(
                    db, _ECB, year, price_overrides=prices,
                )
                prefix = out_dir / f"decaf_{year}"
                write_yaml(report, prefix.with_suffix(".yaml"))
                write_xls(report, prefix.with_suffix(".xlsx"))
                write_pdf(report, prefix.with_suffix(".pdf"))
                print(f"Wrote {fixture}/{year}: yaml + xlsx + pdf")
        finally:
            db.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
