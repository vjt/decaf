"""Tests for Schwab data parsing (PDFs + JSON)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from decaf.schwab_gains_pdf import RealizedLot
from decaf.schwab_parse import cusip_to_isin

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
