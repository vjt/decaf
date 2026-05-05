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

SBTP_CUSIP = "67777M666"


def _build_json() -> dict:
    return {
        "FromDate": "01/01/2024",
        "ToDate": "12/31/2024",
        "TotalTransactionsAmount": "$0.00",
        "TotalFeesAndCommAmount": "$0.00",
        "BrokerageTransactions": [
            {
                "Date": "03/15/2024",
                "Action": "Stock Plan Activity",
                "Symbol": "SBTP",
                "Description": "SBATTE LA PORTA PRODUCTIONS INC CLASS A",
                "Quantity": "15",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "",
                "AcctgRuleCd": "1",
            },
            {
                "Date": "06/15/2024",
                "Action": "Stock Plan Activity",
                "Symbol": "SBTP",
                "Description": "SBATTE LA PORTA PRODUCTIONS INC CLASS A",
                "Quantity": "15",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "",
                "AcctgRuleCd": "1",
            },
            {
                "Date": "09/15/2024",
                "Action": "Stock Plan Activity",
                "Symbol": "SBTP",
                "Description": "SBATTE LA PORTA PRODUCTIONS INC CLASS A",
                "Quantity": "15",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "",
                "AcctgRuleCd": "1",
            },
            {
                "Date": "10/15/2024",
                "Action": "Sell",
                "Symbol": "SBTP",
                "Description": "SBATTE LA PORTA PRODUCTIONS INC CLASS A",
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
            {
                "Date": "12/15/2024",
                "Action": "Stock Plan Activity",
                "Symbol": "SBTP",
                "Description": "SBATTE LA PORTA PRODUCTIONS INC CLASS A",
                "Quantity": "15",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "",
                "AcctgRuleCd": "1",
            },
        ],
    }


def main() -> int:
    (_HERE / f"Individual_{ACCOUNT}_Transactions_20250115-120000.json").write_text(
        json.dumps(_build_json(), indent=2),
    )

    # Sell 20 in Oct drawn FIFO from Mar (15) + Jun (5). Both ST — <1y from vest.
    lots_2024 = [
        LotRow(
            description="SBTP SBATTE LA PORTA PRODUCTIONS",
            cusip=SBTP_CUSIP,
            quantity=Decimal("15"),
            date_acquired=date(2024, 3, 15),
            date_sold=date(2024, 10, 15),
            proceeds=Decimal("1725.00"),
            cost_basis=Decimal("1425.00"),
            gain_loss=Decimal("300.00"),
            is_long_term=False,
        ),
        LotRow(
            description="SBTP SBATTE LA PORTA PRODUCTIONS",
            cusip=SBTP_CUSIP,
            quantity=Decimal("5"),
            date_acquired=date(2024, 6, 15),
            date_sold=date(2024, 10, 15),
            proceeds=Decimal("575.00"),
            cost_basis=Decimal("500.00"),
            gain_loss=Decimal("75.00"),
            is_long_term=False,
        ),
    ]
    write_year_end_summary(
        _HERE / "Year-End Summary - 2024_2025-01-24_666.PDF",
        2024,
        ACCOUNT,
        lots=lots_2024,
    )

    vests = [
        VestRow(
            vest_date=date(2024, 3, 15),
            transaction_id=5000001,
            award_id=200000001,
            award_date=date(2023, 3, 20),
            fmv_ita=Decimal("95.0000"),
            fmv_irl=Decimal("93.5000"),
            shares_vested=15,
            net_shares=15,
            taxable_income_ita=Decimal("1425.00"),
        ),
        VestRow(
            vest_date=date(2024, 6, 15),
            transaction_id=5000002,
            award_id=200000001,
            award_date=date(2023, 3, 20),
            fmv_ita=Decimal("100.0000"),
            fmv_irl=Decimal("98.5000"),
            shares_vested=15,
            net_shares=15,
            taxable_income_ita=Decimal("1500.00"),
        ),
        VestRow(
            vest_date=date(2024, 9, 15),
            transaction_id=5000003,
            award_id=200000001,
            award_date=date(2023, 3, 20),
            fmv_ita=Decimal("105.0000"),
            fmv_irl=Decimal("103.5000"),
            shares_vested=15,
            net_shares=15,
            taxable_income_ita=Decimal("1575.00"),
        ),
        VestRow(
            vest_date=date(2024, 12, 15),
            transaction_id=5000004,
            award_id=200000002,
            award_date=date(2024, 3, 20),
            fmv_ita=Decimal("110.0000"),
            fmv_irl=Decimal("108.5000"),
            shares_vested=15,
            net_shares=15,
            taxable_income_ita=Decimal("1650.00"),
        ),
    ]
    write_annual_withholding(
        _HERE / "Annual Withholding Statement_2024-12-31.PDF",
        2024,
        HOLDER,
        ADDRESS,
        vests,
    )
    print(f"Wrote Mosconi Schwab fixture to {_HERE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
