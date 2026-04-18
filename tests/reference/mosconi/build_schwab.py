"""Build Mosconi Schwab fixture files.

Re-run from repo root when the fixture spec changes::

    python tests/reference/mosconi/build_schwab.py

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

ACCOUNT = "XXX666"
HOLDER = "Germano Mosconi"
ADDRESS = ["Via Cenisio 12", "San Bonifacio 37047 IT"]

MOSC_CUSIP = "67777M666"


def _build_json() -> dict:
    return {
        "FromDate": "01/01/2024",
        "ToDate": "12/31/2024",
        "TotalTransactionsAmount": "$0.00",
        "TotalFeesAndCommAmount": "$0.00",
        "BrokerageTransactions": [
            {
                "Date": "06/15/2024",
                "Action": "Stock Plan Activity",
                "Symbol": "MOSC",
                "Description": "MOSCONI HOLDINGS INC CLASS A",
                "Quantity": "50",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "",
                "AcctgRuleCd": "1",
            },
            {
                "Date": "10/15/2024",
                "Action": "Sell",
                "Symbol": "MOSC",
                "Description": "MOSCONI HOLDINGS INC CLASS A",
                "Quantity": "20",
                "Price": "$115.00",
                "Fees & Comm": "$0.00",
                "Amount": "$2300.00",
                "AcctgRuleCd": "1",
            },
            {
                "Date": "11/01/2024",
                "Action": "MoneyLink Transfer",
                "Symbol": "",
                "Description": "FUNDS SENT",
                "Quantity": "",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "-$2300.00",
                "AcctgRuleCd": "1",
            },
        ],
    }


def main() -> int:
    (_HERE / f"Individual_{ACCOUNT}_Transactions_20250115-120000.json").write_text(
        json.dumps(_build_json(), indent=2),
    )

    lots_2024 = [
        LotRow(
            description="MOSC HOLDINGS INC CLASS A",
            cusip=MOSC_CUSIP,
            quantity=Decimal("20"),
            date_acquired=date(2024, 6, 15),
            date_sold=date(2024, 10, 15),
            proceeds=Decimal("2300.00"),
            cost_basis=Decimal("2000.00"),
            gain_loss=Decimal("300.00"),
            is_long_term=False,
        ),
    ]
    write_year_end_summary(
        _HERE / "Year-End Summary - 2024_2025-01-24_666.PDF",
        2024, ACCOUNT, lots=lots_2024,
    )

    vests = [
        VestRow(
            vest_date=date(2024, 6, 15),
            transaction_id=5000001,
            award_id=200000001,
            award_date=date(2023, 3, 20),
            fmv_ita=Decimal("100.0000"),
            fmv_irl=Decimal("98.5000"),
            shares_vested=50,
            net_shares=50,
            taxable_income_ita=Decimal("5000.00"),
        ),
    ]
    write_annual_withholding(
        _HERE / "Annual Withholding Statement_2024-12-31.PDF",
        2024, HOLDER, ADDRESS, vests,
    )
    print(f"Wrote Mosconi Schwab fixture to {_HERE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
