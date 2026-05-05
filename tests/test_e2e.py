"""End-to-end tests against synthetic fixtures.

For each (fixture, year) pair:
    1. Ingest IBKR XMLs + Schwab PDFs/JSONs into a fresh temp DB
    2. Build a TaxReport via the same pipeline as `decaf report`
    3. Compare the full YAML dump against the committed oracle

Fully deterministic: no network (ECB rates come from the committed cache
DB; fake-ticker prices come from `prices.yaml` alongside each fixture).
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from decaf.cli import _load_and_build_report
from decaf.parse import parse_statement_all
from decaf.schwab_parse import parse_schwab
from decaf.statement_store import StatementStore

_REF_DIR = Path(__file__).parent / "reference"
_ECB_DB = _REF_DIR / "ecb_rates.db"

# (fixture_name, tax_year) pairs — one entry per committed oracle
_FIXTURE_YEARS: list[tuple[str, int]] = [
    ("magnotta", 2024),
    ("mosconi", 2023),
    ("mosconi", 2024),
    ("mascetti", 2024),
    ("mascetti", 2025),
]

# Cache built reports per (fixture, year) — pipeline is expensive
_report_cache: dict[tuple[str, int], dict] = {}


def _build_fixture_db(fixture_dir: Path) -> Path:
    """Ingest every broker file in `fixture_dir` into a fresh temp DB."""
    tmp = Path(tempfile.gettempdir()) / f"decaf_test_{os.getpid()}_{fixture_dir.name}.db"
    tmp.unlink(missing_ok=True)

    for xml_path in sorted(fixture_dir.glob("*.xml")):
        with StatementStore(tmp) as store:
            store.store(parse_statement_all(xml_path.read_text()))

    schwab_json = sorted(fixture_dir.glob("Individual_*_Transactions_*.json"))
    gains_pdfs = sorted(fixture_dir.glob("Year-End Summary*.PDF"))
    vest_pdfs = sorted(fixture_dir.glob("Annual Withholding*.PDF"))
    if schwab_json and gains_pdfs and vest_pdfs:
        for j in schwab_json:
            with StatementStore(tmp) as store:
                store.store(parse_schwab(j, gains_pdfs, vest_pdfs))

    return tmp


def _load_prices(fixture_dir: Path) -> dict[int, dict[str, Decimal]]:
    """Load optional `prices.yaml` (year → symbol → price)."""
    p = fixture_dir / "prices.yaml"
    if not p.exists():
        return {}
    with open(p) as f:
        raw = yaml.safe_load(f) or {}
    return {
        int(y): {str(s): Decimal(str(v)) for s, v in (syms or {}).items()}
        for y, syms in raw.items()
    }


async def _get_report(fixture: str, year: int) -> dict:
    key = (fixture, year)
    if key in _report_cache:
        return _report_cache[key]

    fixture_dir = _REF_DIR / fixture
    db = _build_fixture_db(fixture_dir)
    prices = _load_prices(fixture_dir)
    try:
        report, _data = await _load_and_build_report(
            db,
            _ECB_DB,
            year,
            price_overrides=prices,
        )
    finally:
        db.unlink(missing_ok=True)

    dumped = report.model_dump(mode="json")
    _report_cache[key] = dumped
    return dumped


def _load_oracle(fixture: str, year: int) -> dict:
    oracle = _REF_DIR / fixture / f"decaf_{year}.yaml"
    assert oracle.exists(), f"missing oracle: {oracle}"
    with open(oracle) as f:
        return yaml.safe_load(f)


@pytest.mark.timeout(60)
@pytest.mark.parametrize(("fixture", "year"), _FIXTURE_YEARS)
class TestFixtureMatchesOracle:
    """Full TaxReport dump must match the committed oracle exactly."""

    async def test_full_report_matches(self, fixture: str, year: int) -> None:
        actual = await _get_report(fixture, year)
        expected = _load_oracle(fixture, year)
        assert actual == expected, (
            f"{fixture}/{year}: report diverges from oracle — "
            "run `decaf backtest <fixture> --update` to regenerate"
        )

    async def test_line_counts_stable(self, fixture: str, year: int) -> None:
        """Sanity check: shape of report is what we committed."""
        actual = await _get_report(fixture, year)
        expected = _load_oracle(fixture, year)
        assert len(actual["rw_lines"]) == len(expected["rw_lines"])
        assert len(actual["rt_lines"]) == len(expected["rt_lines"])
        assert len(actual["rl_lines"]) == len(expected["rl_lines"])

    async def test_rl_net_equals_gross_minus_wht(self, fixture: str, year: int) -> None:
        """Invariant: RL net = gross - WHT (within ±0.01 rounding)."""
        actual = await _get_report(fixture, year)
        for i, rl in enumerate(actual["rl_lines"]):
            gross = Decimal(str(rl["gross_amount_eur"]))
            wht = Decimal(str(rl["wht_amount_eur"]))
            net = Decimal(str(rl["net_amount_eur"]))
            assert abs(net - (gross - wht)) <= Decimal("0.01"), (
                f"{fixture}/{year} RL[{i}]: {net} != {gross} - {wht}"
            )
