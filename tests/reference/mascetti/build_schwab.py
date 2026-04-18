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

from gen_schwab_pdfs import VestRow, write_annual_withholding, write_year_end_summary  # noqa: E402

ACCOUNT = "XXX066"
HOLDER = "Raffaello Mascetti"
ADDRESS = ["Via Supercazzola 1", "Firenze 50100 IT"]


def _build_json_2024() -> dict:
    return {
        "FromDate": "01/01/2024",
        "ToDate": "12/31/2024",
        "TotalTransactionsAmount": "$0.00",
        "TotalFeesAndCommAmount": "$0.00",
        "BrokerageTransactions": [
            {
                "Date": "05/15/2024",
                "Action": "Stock Plan Activity",
                "Symbol": "CMTH",
                "Description": "CAMETTO HOLDINGS INC CLASS A",
                "Quantity": "100",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "",
                "AcctgRuleCd": "1",
            },
        ],
    }


def _build_json_2025() -> dict:
    return {
        "FromDate": "01/01/2025",
        "ToDate": "12/31/2025",
        "TotalTransactionsAmount": "$0.00",
        "TotalFeesAndCommAmount": "$0.00",
        "BrokerageTransactions": [
            {
                "Date": "05/15/2025",
                "Action": "Stock Plan Activity",
                "Symbol": "CMTH",
                "Description": "CAMETTO HOLDINGS INC CLASS A",
                "Quantity": "120",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "",
                "AcctgRuleCd": "1",
            },
        ],
    }


def main() -> int:
    # 2024 JSON
    (_HERE / f"Individual_{ACCOUNT}_Transactions_20250115-120000.json").write_text(
        json.dumps(_build_json_2024(), indent=2),
    )
    # 2025 JSON
    (_HERE / f"Individual_{ACCOUNT}_Transactions_20260115-120000.json").write_text(
        json.dumps(_build_json_2025(), indent=2),
    )

    # Empty Year-End Summaries (no sells — all RSU held)
    write_year_end_summary(
        _HERE / "Year-End Summary - 2024_2025-01-24_066.PDF",
        2024, ACCOUNT, lots=[],
    )
    write_year_end_summary(
        _HERE / "Year-End Summary - 2025_2026-01-24_066.PDF",
        2025, ACCOUNT, lots=[],
    )

    # 2024 Annual Withholding — 1 vest
    vests_2024 = [
        VestRow(
            vest_date=date(2024, 5, 15),
            transaction_id=6000001,
            award_id=300000001,
            award_date=date(2023, 3, 20),
            fmv_ita=Decimal("50.0000"),
            fmv_irl=Decimal("48.5000"),
            shares_vested=100,
            net_shares=100,
            taxable_income_ita=Decimal("5000.00"),
        ),
    ]
    write_annual_withholding(
        _HERE / "Annual Withholding Statement_2024-12-31.PDF",
        2024, HOLDER, ADDRESS, vests_2024,
    )

    # 2025 Annual Withholding — 1 vest
    vests_2025 = [
        VestRow(
            vest_date=date(2025, 5, 15),
            transaction_id=6000002,
            award_id=300000002,
            award_date=date(2024, 3, 20),
            fmv_ita=Decimal("55.0000"),
            fmv_irl=Decimal("53.5000"),
            shares_vested=120,
            net_shares=120,
            taxable_income_ita=Decimal("6600.00"),
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
