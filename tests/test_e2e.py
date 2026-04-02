"""End-to-end tests against real broker data.

Runs the full computation pipeline (load -> ECB rates -> compute quadri ->
assemble report) and asserts every output value matches the verified
reference JSONs.

Uses committed fixture databases in tests/reference/ -- no external
dependencies, no network calls, fully deterministic.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

_REF_DIR = Path(__file__).parent / "reference"
_STMT_DB = _REF_DIR / "statements.db"
_ECB_DB = _REF_DIR / "ecb_rates.db"

# Year-end prices pinned from yfinance (no network calls in tests).
_YEAR_END_PRICES: dict[int, dict[str, Decimal]] = {
    2022: {"META": Decimal("119.40")},
    2023: {"META": Decimal("351.20")},
    2024: {"META": Decimal("583.17")},
    2025: {
        "VWRA": Decimal("170.62"),
        "META": Decimal("659.53"),
        "IGLD": Decimal("77.78"),
        "VWCE": Decimal("145.42"),
    },
}

_PRIOR_YEAR_PRICES: dict[int, dict[str, Decimal]] = {
    2022: {},
    2023: {"META": Decimal("119.40")},
    2024: {"META": Decimal("351.20")},
    2025: {"META": Decimal("583.17")},
}


def _load_reference(year: int) -> dict[str, object]:
    """Load reference JSON for a tax year."""
    matches = list(_REF_DIR.glob(f"*_{year}.json"))
    assert matches, f"No reference JSON for {year}"
    with open(matches[0]) as f:
        return json.load(f)


def _generate_report(tax_year: int):
    """Run the full pipeline from fixture DBs and return a TaxReport."""
    from decaf.ecb_cache import EcbRateCache
    from decaf.forex import analyze_forex_threshold
    from decaf.forex_gains import compute_forex_gains, forex_gains_to_rt_lines
    from decaf.fx import FxService
    from decaf.models import TaxReport
    from decaf.quadro_rl import compute_rl
    from decaf.quadro_rt import compute_rt
    from decaf.quadro_rw import compute_rw
    from decaf.statement_store import StatementStore

    with StatementStore(_STMT_DB) as store:
        data = store.load_for_year(tax_year)

    ecb_rates: dict[date, Decimal] = {}

    async def _load_ecb() -> None:
        async with EcbRateCache(_ECB_DB) as cache:
            trade_years = {t.trade_datetime.year for t in data.trades}
            trade_years.add(tax_year)
            for year in sorted(trade_years):
                rates = await cache.get_all_rates_for_year("USD", year)
                ecb_rates.update(rates)

    asyncio.new_event_loop().run_until_complete(_load_ecb())

    fx = FxService(data.conversion_rates, ecb_rates)

    forex = analyze_forex_threshold(
        data.trades, data.cash_transactions, fx, tax_year,
    )
    rw_lines = compute_rw(
        data.positions, data.trades, data.cash_report,
        data.cash_transactions, fx, tax_year,
        mark_prices=_YEAR_END_PRICES.get(tax_year, {}),
        prior_year_prices=_PRIOR_YEAR_PRICES.get(tax_year, {}),
    )
    rt_lines = compute_rt(data.trades, fx, tax_year)
    if forex.threshold_breached:
        forex_entries = compute_forex_gains(
            data.trades, data.cash_transactions, fx, tax_year,
        )
        rt_lines.extend(forex_gains_to_rt_lines(forex_entries))
    rl_lines = compute_rl(data.cash_transactions, fx, tax_year)

    return TaxReport(
        tax_year=tax_year,
        account=data.account,
        rw_lines=rw_lines,
        rt_lines=rt_lines,
        rl_lines=rl_lines,
        forex_threshold_breached=forex.threshold_breached,
        forex_max_consecutive_days=forex.max_consecutive_business_days,
        forex_first_breach_date=forex.first_breach_date,
        forex_daily_records=forex.daily_records,
        forex_usd_events=forex.usd_events,
    )


def _d(val: float | int) -> Decimal:
    """Convert JSON float to Decimal for comparison."""
    return Decimal(str(val))


# Cache reports per year to avoid recomputing for each test method
_report_cache: dict[int, object] = {}


def _get_report(year: int):
    if year not in _report_cache:
        _report_cache[year] = _generate_report(year)
    return _report_cache[year]


# ---------------------------------------------------------------------------
# Per-year parametrized tests
# ---------------------------------------------------------------------------


@pytest.mark.timeout(30)
@pytest.mark.parametrize("year", [2022, 2023, 2024, 2025])
class TestQuadroRW:
    """Quadro RW (IVAFE) against reference values."""

    def test_line_count(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        assert len(report.rw_lines) == len(ref["quadro_rw"]["lines"])

    def test_total_ivafe(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        assert report.total_ivafe == _d(ref["quadro_rw"]["total_ivafe"])

    def test_per_line_ivafe(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        for i, (actual, expected) in enumerate(
            zip(report.rw_lines, ref["quadro_rw"]["lines"], strict=True),
        ):
            assert actual.ivafe_due == _d(expected["ivafe_due"]), (
                f"RW[{i}] {actual.symbol}: "
                f"IVAFE {actual.ivafe_due} != {expected['ivafe_due']}"
            )

    def test_per_line_days_and_values(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        for i, (actual, expected) in enumerate(
            zip(report.rw_lines, ref["quadro_rw"]["lines"], strict=True),
        ):
            assert actual.symbol == expected["symbol"], f"RW[{i}] symbol"
            assert actual.days_held == expected["days_held"], (
                f"RW[{i}] {actual.symbol}: days {actual.days_held} != {expected['days_held']}"
            )
            assert actual.final_value_eur == _d(expected["final_value_eur"]), (
                f"RW[{i}] {actual.symbol}: final EUR"
            )
            assert actual.initial_value_eur == _d(expected["initial_value_eur"]), (
                f"RW[{i}] {actual.symbol}: initial EUR"
            )


@pytest.mark.timeout(30)
@pytest.mark.parametrize("year", [2022, 2023, 2024, 2025])
class TestQuadroRT:
    """Quadro RT (capital gains) against reference values."""

    def test_line_count(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        assert len(report.rt_lines) == len(ref["quadro_rt"]["lines"])

    def test_net_gain_loss(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        assert report.net_capital_gain_loss == _d(ref["quadro_rt"]["net_gain_loss_eur"])

    def test_per_line_gain_loss(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        for i, (actual, expected) in enumerate(
            zip(report.rt_lines, ref["quadro_rt"]["lines"], strict=True),
        ):
            assert actual.gain_loss_eur == _d(expected["gain_loss_eur"]), (
                f"RT[{i}] {actual.symbol}: "
                f"gain/loss {actual.gain_loss_eur} != {expected['gain_loss_eur']}"
            )

    def test_per_line_proceeds_and_cost(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        for i, (actual, expected) in enumerate(
            zip(report.rt_lines, ref["quadro_rt"]["lines"], strict=True),
        ):
            assert actual.proceeds_eur == _d(expected["proceeds_eur"]), (
                f"RT[{i}] {actual.symbol}: proceeds"
            )
            assert actual.cost_basis_eur == _d(expected["cost_basis_eur"]), (
                f"RT[{i}] {actual.symbol}: cost"
            )


@pytest.mark.timeout(30)
@pytest.mark.parametrize("year", [2022, 2023, 2024, 2025])
class TestQuadroRL:
    """Quadro RL (investment income) against reference values."""

    def test_line_count(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        assert len(report.rl_lines) == len(ref["quadro_rl"]["lines"])

    def test_totals(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        assert report.total_gross_interest_eur == _d(
            ref["quadro_rl"]["total_gross_interest_eur"],
        )
        assert report.total_wht_eur == _d(ref["quadro_rl"]["total_wht_eur"])

    def test_per_line(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        for i, (actual, expected) in enumerate(
            zip(report.rl_lines, ref["quadro_rl"]["lines"], strict=True),
        ):
            assert actual.gross_amount_eur == _d(expected["gross_amount_eur"]), (
                f"RL[{i}]: gross EUR"
            )
            assert actual.wht_amount_eur == _d(expected["wht_amount_eur"]), (
                f"RL[{i}]: WHT EUR"
            )
            assert actual.net_amount_eur == _d(expected["net_amount_eur"]), (
                f"RL[{i}]: net EUR"
            )


@pytest.mark.timeout(30)
@pytest.mark.parametrize("year", [2022, 2023, 2024, 2025])
class TestForex:
    """Forex threshold analysis against reference values."""

    def test_threshold_result(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        assert report.forex_threshold_breached == ref["forex_analysis"]["threshold_breached"]

    def test_consecutive_days(self, year: int) -> None:
        ref = _load_reference(year)
        report = _get_report(year)
        assert report.forex_max_consecutive_days == (
            ref["forex_analysis"]["max_consecutive_business_days"]
        )


@pytest.mark.timeout(30)
@pytest.mark.parametrize("year", [2022, 2023, 2024, 2025])
class TestCrossChecks:
    """Internal consistency: computed totals match per-line sums."""

    def test_ivafe_total_matches_lines(self, year: int) -> None:
        report = _get_report(year)
        line_sum = sum((rw.ivafe_due for rw in report.rw_lines), Decimal(0))
        assert report.total_ivafe == line_sum

    def test_rt_net_matches_lines(self, year: int) -> None:
        report = _get_report(year)
        line_sum = sum((rt.gain_loss_eur for rt in report.rt_lines), Decimal(0))
        assert report.net_capital_gain_loss == line_sum

    def test_rl_gross_matches_lines(self, year: int) -> None:
        report = _get_report(year)
        line_sum = sum(
            (rl.gross_amount_eur for rl in report.rl_lines), Decimal(0),
        )
        assert report.total_gross_interest_eur == line_sum

    def test_rl_net_equals_gross_minus_wht(self, year: int) -> None:
        report = _get_report(year)
        for i, rl in enumerate(report.rl_lines):
            expected_net = rl.gross_amount_eur - rl.wht_amount_eur
            # Allow +-0.01 rounding difference
            assert abs(rl.net_amount_eur - expected_net) <= Decimal("0.01"), (
                f"RL[{i}]: net {rl.net_amount_eur} != gross-wht {expected_net}"
            )

    def test_rt_gain_reasonable(self, year: int) -> None:
        """Each RT gain/loss should have consistent sign with proceeds-cost.

        Note: gain_loss_eur comes from broker's fifoPnlRealized (trusted),
        which may differ from proceeds-cost due to commission allocation
        and FX rounding. We only check the sign is consistent.
        """
        report = _get_report(year)
        for i, rt in enumerate(report.rt_lines):
            if rt.is_forex:
                continue  # forex RT lines have synthetic proceeds/cost
            simple_gl = rt.proceeds_eur - rt.cost_basis_eur
            # Sign should match (both positive or both negative)
            if rt.gain_loss_eur != Decimal(0) and simple_gl != Decimal(0):
                assert (rt.gain_loss_eur > 0) == (simple_gl > 0), (
                    f"RT[{i}] {rt.symbol}: sign mismatch "
                    f"gain_loss={rt.gain_loss_eur}, proceeds-cost={simple_gl}"
                )
