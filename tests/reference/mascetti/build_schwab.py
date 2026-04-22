"""Build Mascetti Schwab fixture files (2024 + 2025).

Re-run from repo root when the fixture spec changes::

    python tests/reference/mascetti/build_schwab.py

Produces: Individual_*_Transactions_*.json, Year-End Summary*.PDF,
Annual Withholding Statement*.PDF
"""

from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

from gen_schwab_pdfs import (  # noqa: E402
    LotRow,
    VestRow,
    write_annual_withholding,
    write_year_end_summary,
)

ACCOUNT = "XXX066"
HOLDER = "Raffaello Mascetti"
ADDRESS = ["Via Supercazzola 1", "Firenze 50100 IT"]
SPRC_CUSIP = "13579C246"


def _vest_json(qty: int, vest_date: str) -> dict:
    return {
        "Date": vest_date,
        "Action": "Stock Plan Activity",
        "Symbol": "SPRC",
        "Description": "SUPERCAZZOLA PREMATURATA INC",
        "Quantity": str(qty),
        "Price": "",
        "Fees & Comm": "",
        "Amount": "",
        "AcctgRuleCd": "1",
    }


def _sell_json(qty: int, price: str, amount: str, sell_date: str) -> dict:
    return {
        "Date": sell_date,
        "Action": "Sell",
        "Symbol": "SPRC",
        "Description": "SUPERCAZZOLA PREMATURATA INC",
        "Quantity": str(qty),
        "Price": price,
        "Fees & Comm": "$0.00",
        "Amount": amount,
        "AcctgRuleCd": "1",
    }


def _wire_json(amount: str, wire_date: str) -> dict:
    return {
        "Date": wire_date,
        "Action": "MoneyLink Transfer",
        "Symbol": "",
        "Description": "FUNDS SENT",
        "Quantity": "",
        "Price": "",
        "Fees & Comm": "",
        "Amount": amount,
        "AcctgRuleCd": "1",
    }


def _build_json_2024() -> dict:
    return {
        "FromDate": "01/01/2024",
        "ToDate": "12/31/2024",
        "TotalTransactionsAmount": "$0.00",
        "TotalFeesAndCommAmount": "$0.00",
        "BrokerageTransactions": [
            _vest_json(25, "02/15/2024"),
            _vest_json(25, "05/15/2024"),
            _sell_json(30, "$55.00", "$1650.00", "09/10/2024"),
            _wire_json("-$1650.00", "09/20/2024"),
            _vest_json(25, "08/15/2024"),
            _vest_json(25, "11/15/2024"),
        ],
    }


def _build_json_2025() -> dict:
    return {
        "FromDate": "01/01/2025",
        "ToDate": "12/31/2025",
        "TotalTransactionsAmount": "$0.00",
        "TotalFeesAndCommAmount": "$0.00",
        "BrokerageTransactions": [
            _vest_json(30, "02/15/2025"),
            _vest_json(30, "05/15/2025"),
            _vest_json(30, "08/15/2025"),
            _sell_json(40, "$60.00", "$2400.00", "10/15/2025"),
            _wire_json("-$2400.00", "10/25/2025"),
            _vest_json(30, "11/15/2025"),
        ],
    }


def main() -> int:
    (_HERE / f"Individual_{ACCOUNT}_Transactions_20250115-120000.json").write_text(
        json.dumps(_build_json_2024(), indent=2),
    )
    (_HERE / f"Individual_{ACCOUNT}_Transactions_20260115-120000.json").write_text(
        json.dumps(_build_json_2025(), indent=2),
    )

    # 2024 YES — Sep 10 sell of 30 drawn FIFO: 25 from Feb + 5 from May. Both ST.
    # Note: YES cost_basis is the US tax basis = FMV at vest day (W-2), which
    # systematically differs from the Italian Valore Normale (monthly average
    # ending the trading day before vest, art. 9 c. 4 TUIR) reported on the
    # Annual Withholding Statement as ITA FMV. Here we set US FMV $2/share
    # higher than ITA FMV to exercise the Normal Value substitution.
    lots_2024 = [
        LotRow(
            description="SPRC SUPERCAZZOLA PREMATURATA",
            cusip=SPRC_CUSIP,
            quantity=Decimal("25"),
            date_acquired=date(2024, 2, 15),
            date_sold=date(2024, 9, 10),
            proceeds=Decimal("1375.00"),
            cost_basis=Decimal("1250.00"),  # 25 × $50 (US FMV at vest)
            gain_loss=Decimal("125.00"),
            is_long_term=False,
        ),
        LotRow(
            description="SPRC SUPERCAZZOLA PREMATURATA",
            cusip=SPRC_CUSIP,
            quantity=Decimal("5"),
            date_acquired=date(2024, 5, 15),
            date_sold=date(2024, 9, 10),
            proceeds=Decimal("275.00"),
            cost_basis=Decimal("260.00"),  # 5 × $52 (US FMV at vest)
            gain_loss=Decimal("15.00"),
            is_long_term=False,
        ),
    ]
    write_year_end_summary(
        _HERE / "Year-End Summary - 2024_2025-01-24_066.PDF",
        2024, ACCOUNT, lots=lots_2024,
    )

    # 2025 YES — Oct 15 sell of 40 drawn FIFO from 2024 leftovers:
    # 20 from May + 20 from Aug. Both LT.
    lots_2025 = [
        LotRow(
            description="SPRC SUPERCAZZOLA PREMATURATA",
            cusip=SPRC_CUSIP,
            quantity=Decimal("20"),
            date_acquired=date(2024, 5, 15),
            date_sold=date(2025, 10, 15),
            proceeds=Decimal("1200.00"),
            cost_basis=Decimal("1040.00"),  # 20 × $52 (US FMV at vest)
            gain_loss=Decimal("160.00"),
            is_long_term=True,
        ),
        LotRow(
            description="SPRC SUPERCAZZOLA PREMATURATA",
            cusip=SPRC_CUSIP,
            quantity=Decimal("20"),
            date_acquired=date(2024, 8, 15),
            date_sold=date(2025, 10, 15),
            proceeds=Decimal("1200.00"),
            cost_basis=Decimal("1080.00"),  # 20 × $54 (US FMV at vest)
            gain_loss=Decimal("120.00"),
            is_long_term=True,
        ),
    ]
    write_year_end_summary(
        _HERE / "Year-End Summary - 2025_2026-01-24_066.PDF",
        2025, ACCOUNT, lots=lots_2025,
    )

    # 2024 AWH — 4 quarterly vests, original award (granted 2023-03-20)
    vests_2024 = [
        VestRow(
            vest_date=date(2024, 2, 15),
            transaction_id=6000001,
            award_id=300000001,
            award_date=date(2023, 3, 20),
            fmv_ita=Decimal("48.0000"),
            fmv_irl=Decimal("46.5000"),
            shares_vested=25,
            net_shares=25,
            taxable_income_ita=Decimal("1200.00"),
        ),
        VestRow(
            vest_date=date(2024, 5, 15),
            transaction_id=6000002,
            award_id=300000001,
            award_date=date(2023, 3, 20),
            fmv_ita=Decimal("50.0000"),
            fmv_irl=Decimal("48.5000"),
            shares_vested=25,
            net_shares=25,
            taxable_income_ita=Decimal("1250.00"),
        ),
        VestRow(
            vest_date=date(2024, 8, 15),
            transaction_id=6000003,
            award_id=300000001,
            award_date=date(2023, 3, 20),
            fmv_ita=Decimal("52.0000"),
            fmv_irl=Decimal("50.5000"),
            shares_vested=25,
            net_shares=25,
            taxable_income_ita=Decimal("1300.00"),
        ),
        VestRow(
            vest_date=date(2024, 11, 15),
            transaction_id=6000004,
            award_id=300000001,
            award_date=date(2023, 3, 20),
            fmv_ita=Decimal("54.0000"),
            fmv_irl=Decimal("52.5000"),
            shares_vested=25,
            net_shares=25,
            taxable_income_ita=Decimal("1350.00"),
        ),
    ]
    write_annual_withholding(
        _HERE / "Annual Withholding Statement_2024-12-31.PDF",
        2024, HOLDER, ADDRESS, vests_2024,
    )

    # 2025 AWH — 4 quarterly vests, new award (granted 2024-03-20)
    vests_2025 = [
        VestRow(
            vest_date=date(2025, 2, 15),
            transaction_id=6000005,
            award_id=300000002,
            award_date=date(2024, 3, 20),
            fmv_ita=Decimal("56.0000"),
            fmv_irl=Decimal("54.5000"),
            shares_vested=30,
            net_shares=30,
            taxable_income_ita=Decimal("1680.00"),
        ),
        VestRow(
            vest_date=date(2025, 5, 15),
            transaction_id=6000006,
            award_id=300000002,
            award_date=date(2024, 3, 20),
            fmv_ita=Decimal("58.0000"),
            fmv_irl=Decimal("56.5000"),
            shares_vested=30,
            net_shares=30,
            taxable_income_ita=Decimal("1740.00"),
        ),
        VestRow(
            vest_date=date(2025, 8, 15),
            transaction_id=6000007,
            award_id=300000002,
            award_date=date(2024, 3, 20),
            fmv_ita=Decimal("60.0000"),
            fmv_irl=Decimal("58.5000"),
            shares_vested=30,
            net_shares=30,
            taxable_income_ita=Decimal("1800.00"),
        ),
        VestRow(
            vest_date=date(2025, 11, 15),
            transaction_id=6000008,
            award_id=300000002,
            award_date=date(2024, 3, 20),
            fmv_ita=Decimal("62.0000"),
            fmv_irl=Decimal("60.5000"),
            shares_vested=30,
            net_shares=30,
            taxable_income_ita=Decimal("1860.00"),
        ),
    ]
    write_annual_withholding(
        _HERE / "Annual Withholding Statement_2025-12-31.PDF",
        2025, HOLDER, ADDRESS, vests_2025,
    )
    print(f"Wrote Mascetti Schwab fixture to {_HERE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
