"""Tests for Schwab data parsing (PDFs + JSON)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from decaf.schwab_gains_pdf import RealizedLot
from decaf.schwab_parse import _lot_to_trade, cusip_to_isin

META_ISIN = "US30303M1027"


# ---------------------------------------------------------------------------
# CUSIP to ISIN
# ---------------------------------------------------------------------------


class TestCusipToIsin:
    def test_meta(self):
        assert cusip_to_isin("30303M102") == META_ISIN

    def test_apple(self):
        assert cusip_to_isin("037833100") == "US0378331005"

    def test_microsoft(self):
        assert cusip_to_isin("594918104") == "US5949181045"

    def test_empty(self):
        assert cusip_to_isin("") == ""

    def test_wrong_length(self):
        assert cusip_to_isin("12345") == ""


# ---------------------------------------------------------------------------
# RealizedLot model
# ---------------------------------------------------------------------------


class TestRealizedLot:
    def test_fields(self):
        lot = RealizedLot(
            symbol="META",
            cusip="30303M102",
            quantity=Decimal("10"),
            date_acquired=date(2024, 8, 15),
            date_sold=date(2025, 2, 5),
            proceeds=Decimal("7010.60"),
            cost_basis=Decimal("5373.30"),
            wash_sale_adj=Decimal(0),
            gain_loss=Decimal("1637.30"),
            is_long_term=False,
        )
        assert lot.symbol == "META"
        assert lot.gain_loss == Decimal("1637.30")
        assert not lot.is_long_term

    def test_negative_gain(self):
        lot = RealizedLot(
            symbol="META",
            cusip="30303M102",
            quantity=Decimal("10"),
            date_acquired=date(2025, 2, 15),
            date_sold=date(2025, 5, 19),
            proceeds=Decimal("6392.01"),
            cost_basis=Decimal("7366.70"),
            wash_sale_adj=Decimal(0),
            gain_loss=Decimal("-974.69"),
            is_long_term=False,
        )
        assert lot.gain_loss < 0


# ---------------------------------------------------------------------------
# Normal Value substitution in RSU cost basis (art. 68 c.6 TUIR)
# ---------------------------------------------------------------------------


class TestLotToTradeNormalValue:
    """Schwab Year-End Summary reports cost_basis = US FMV at vest day
    (basis W-2). For Italian RT the cost must be the Valore Normale taxed
    as reddito di lavoro (art. 68 c.6 + art. 9 c.4 TUIR) — available as
    ITA FMV on the Annual Withholding Statement. _lot_to_trade must
    substitute qty * vest_fmv when the lot's date_acquired is a known
    vest date.
    """

    def _lot(self, **overrides) -> RealizedLot:
        defaults = dict(
            symbol="META",
            cusip="30303M102",
            quantity=Decimal("10"),
            date_acquired=date(2024, 8, 15),
            date_sold=date(2024, 12, 20),
            proceeds=Decimal("5800.00"),
            cost_basis=Decimal("5800.00"),  # US FMV at vest × 10
            wash_sale_adj=Decimal(0),
            gain_loss=Decimal(0),
            is_long_term=False,
        )
        defaults.update(overrides)
        return RealizedLot(**defaults)

    def test_substitutes_cost_with_ita_fmv_when_vest_date_matches(self):
        lot = self._lot(gain_loss=Decimal("0"))  # broker sees zero P/L
        vest_fmvs = {date(2024, 8, 15): Decimal("550.0000")}  # ITA < US

        trade = _lot_to_trade(lot, "XXX001", vest_fmvs)

        # cost = -(qty * ITA FMV), not -(US cost basis)
        assert trade.cost == -(Decimal("10") * Decimal("550.0000"))
        # broker_pnl_realized is preserved as the broker's original number,
        # kept as a reconciliation column in quadro RT output.
        assert trade.broker_pnl_realized == Decimal("0")

    def test_falls_back_to_us_cost_basis_when_no_vest_match(self):
        """Non-RSU lot (cash purchase) must keep broker cost basis."""
        lot = self._lot(date_acquired=date(2024, 3, 11))
        vest_fmvs = {date(2024, 8, 15): Decimal("550.0000")}

        trade = _lot_to_trade(lot, "XXX001", vest_fmvs)

        assert trade.cost == -Decimal("5800.00")
        assert trade.broker_pnl_realized == Decimal("0")

    def test_reconciles_vest_date_within_three_days(self):
        """Year-End Summary may report processing date; Withholding PDF
        reports the actual vest date — reconcile within ±3 days."""
        lot = self._lot(date_acquired=date(2024, 8, 16))  # +1 day
        vest_fmvs = {date(2024, 8, 15): Decimal("550.0000")}

        trade = _lot_to_trade(lot, "XXX001", vest_fmvs)

        assert trade.cost == -(Decimal("10") * Decimal("550.0000"))

    def test_empty_vest_fmvs_preserves_legacy_behaviour(self):
        lot = self._lot()
        trade = _lot_to_trade(lot, "XXX001", {})
        assert trade.cost == -Decimal("5800.00")
