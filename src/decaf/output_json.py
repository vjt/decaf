"""JSON output for tax report."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from decaf.models import TaxReport


class _ReportEncoder(json.JSONEncoder):
    def default(self, o: object) -> object:
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, date):
            return o.isoformat()
        return super().default(o)


def write_json(report: TaxReport, path: Path) -> None:
    """Write the tax report as a JSON file."""
    data = {
        "tax_year": report.tax_year,
        "account": {
            "id": report.account.account_id,
            "holder": report.account.holder_name,
            "base_currency": report.account.base_currency,
            "country": report.account.country,
            "date_opened": report.account.date_opened,
            "broker": "Interactive Brokers Ireland Limited",
            "broker_country": "IE",
        },
        "quadro_rw": [
            {
                "codice_investimento": line.codice_investimento,
                "isin": line.isin,
                "symbol": line.symbol,
                "description": line.description,
                "country": line.country,
                "initial_value_eur": line.initial_value_eur,
                "final_value_eur": line.final_value_eur,
                "days_held": line.days_held,
                "ownership_pct": line.ownership_pct,
                "ivafe_due": line.ivafe_due,
            }
            for line in report.rw_lines
        ],
        "quadro_rw_totals": {
            "total_ivafe": report.total_ivafe,
        },
        "quadro_rt": {
            "lines": [
                {
                    "symbol": line.symbol,
                    "isin": line.isin,
                    "sell_date": line.sell_date,
                    "quantity": line.quantity,
                    "proceeds_eur": line.proceeds_eur,
                    "cost_basis_eur": line.cost_basis_eur,
                    "gain_loss_eur": line.gain_loss_eur,
                    "is_forex": line.is_forex,
                    "ib_fifo_pnl": line.ib_fifo_pnl,
                    "ib_fifo_pnl_eur": line.ib_fifo_pnl_eur,
                }
                for line in report.rt_lines
            ],
            "net_gain_loss_eur": report.net_capital_gain_loss,
        },
        "quadro_rl": {
            "lines": [
                {
                    "description": line.description,
                    "currency": line.currency,
                    "gross_amount": line.gross_amount,
                    "gross_amount_eur": line.gross_amount_eur,
                    "wht_amount": line.wht_amount,
                    "wht_amount_eur": line.wht_amount_eur,
                    "net_amount_eur": line.net_amount_eur,
                }
                for line in report.rl_lines
            ],
            "total_gross_interest_eur": report.total_gross_interest_eur,
            "total_wht_eur": report.total_wht_eur,
        },
        "forex_analysis": {
            "threshold_eur": Decimal("51645.69"),
            "threshold_breached": report.forex_threshold_breached,
            "max_consecutive_business_days": report.forex_max_consecutive_days,
            "first_breach_date": report.forex_first_breach_date,
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, cls=_ReportEncoder, indent=2, ensure_ascii=False)
