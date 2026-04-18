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
                "Symbol": "SPRC",
                "Description": "SUPERCAZZOLA PREMATURATA INC",
                "Quantity": "100",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "",
                "AcctgRuleCd": "1",
            },
            {
                "Date": "09/10/2024",
                "Action": "Sell",
                "Symbol": "SPRC",
                "Description": "SUPERCAZZOLA PREMATURATA INC",
                "Quantity": "30",
                "Price": "$55.00",
                "Fees & Comm": "$0.00",
                "Amount": "$1650.00",
                "AcctgRuleCd": "1",
            },
            {
                "Date": "09/20/2024",
                "Action": "MoneyLink Transfer",
                "Symbol": "",
                "Description": "FUNDS SENT",
                "Quantity": "",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "-$1650.00",
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
                "Symbol": "SPRC",
                "Description": "SUPERCAZZOLA PREMATURATA INC",
                "Quantity": "120",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "",
                "AcctgRuleCd": "1",
            },
            {
                "Date": "10/15/2025",
                "Action": "Sell",
                "Symbol": "SPRC",
                "Description": "SUPERCAZZOLA PREMATURATA INC",
                "Quantity": "40",
                "Price": "$60.00",
                "Fees & Comm": "$0.00",
                "Amount": "$2400.00",
                "AcctgRuleCd": "1",
            },
            {
                "Date": "10/25/2025",
                "Action": "MoneyLink Transfer",
                "Symbol": "",
                "Description": "FUNDS SENT",
                "Quantity": "",
                "Price": "",
                "Fees & Comm": "",
                "Amount": "-$2400.00",
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

    # 2024 YES — 30sh sold, short-term (vested May 15, sold Sep 10)
    lots_2024 = [
        LotRow(
            description="SPRC SUPERCAZZOLA PREMATURATA",
            cusip=SPRC_CUSIP,
            quantity=Decimal("30"),
            date_acquired=date(2024, 5, 15),
            date_sold=date(2024, 9, 10),
            proceeds=Decimal("1650.00"),
            cost_basis=Decimal("1500.00"),
            gain_loss=Decimal("150.00"),
            is_long_term=False,
        ),
    ]
    write_year_end_summary(
        _HERE / "Year-End Summary - 2024_2025-01-24_066.PDF",
        2024, ACCOUNT, lots=lots_2024,
    )
    # 2025 YES — 40sh sold FIFO from 2024 lot (cost $50), long-term
    lots_2025 = [
        LotRow(
            description="SPRC SUPERCAZZOLA PREMATURATA",
            cusip=SPRC_CUSIP,
            quantity=Decimal("40"),
            date_acquired=date(2024, 5, 15),
            date_sold=date(2025, 10, 15),
            proceeds=Decimal("2400.00"),
            cost_basis=Decimal("2000.00"),
            gain_loss=Decimal("400.00"),
            is_long_term=True,
        ),
    ]
    write_year_end_summary(
        _HERE / "Year-End Summary - 2025_2026-01-24_066.PDF",
        2025, ACCOUNT, lots=lots_2025,
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
