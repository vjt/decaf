"""Excel output for tax report — one sheet per quadro."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from decaf.forex import THRESHOLD_EUR
from decaf.models import TaxReport

_HEADER_FONT = Font(bold=True, size=11)
_HEADER_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
_MONEY_FMT = '#,##0.00'
_THIN_BORDER = Border(
    bottom=Side(style="thin", color="B0B0B0"),
)


def write_xls(report: TaxReport, path: Path) -> None:
    """Write the tax report as an Excel workbook."""
    wb = Workbook()

    summary_ws = wb.active
    assert isinstance(summary_ws, Worksheet)
    _write_summary(summary_ws, report)
    _write_rw(wb.create_sheet("Quadro RW"), report)
    _write_rt(wb.create_sheet("Quadro RT"), report)
    _write_rl(wb.create_sheet("Quadro RL"), report)
    _write_forex(wb.create_sheet("Analisi Soglia Valutaria"), report)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))


def _write_summary(ws: Worksheet, report: TaxReport) -> None:
    ws.title = "Riepilogo"

    ws.append(["Report Fiscale Italiano", "", f"Anno fiscale {report.tax_year}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])

    ws.append(["Informazioni Conto"])
    ws["A3"].font = Font(bold=True, size=12)
    ws.append(["ID Conto", report.account.account_id])
    ws.append(["Intestatario", report.account.holder_name])
    ws.append(["Broker", report.account.broker_name])
    ws.append(["Paese", report.account.country])
    ws.append(["Valuta base", report.account.base_currency])
    ws.append(["Data apertura", report.account.date_opened.isoformat()])
    ws.append([])

    ws.append(["Riepilogo Fiscale"])
    ws["A11"].font = Font(bold=True, size=12)
    ws.append(["", "Importo (EUR)"])
    ws["B12"].font = _HEADER_FONT

    ws.append(["IVAFE totale (Quadro RW)", float(report.total_ivafe)])
    ws["B13"].number_format = _MONEY_FMT

    ws.append(["Plusvalenze nette (Quadro RT)", float(report.net_capital_gain_loss)])
    ws["B14"].number_format = _MONEY_FMT

    ws.append(["Redditi lordi (Quadro RL)", float(report.total_gross_interest_eur)])
    ws["B15"].number_format = _MONEY_FMT

    ws.append(["Ritenute estere (Quadro RL)", float(report.total_wht_eur)])
    ws["B16"].number_format = _MONEY_FMT

    ws.append([])
    ws.append(["Soglia Valutaria"])
    ws["A18"].font = Font(bold=True, size=12)
    ws.append(["Soglia (EUR)", float(THRESHOLD_EUR)])
    ws["B19"].number_format = _MONEY_FMT
    ws.append(["Superata", "SI" if report.forex_threshold_breached else "NO"])
    ws.append(["Giorni lavorativi consecutivi", report.forex_max_consecutive_days])
    if report.forex_first_breach_date:
        ws.append(["Data prima violazione", report.forex_first_breach_date.isoformat()])

    ws.column_dimensions["A"].width = 35
    ws.column_dimensions["B"].width = 25


def _write_rw(ws: Worksheet, report: TaxReport) -> None:
    headers = [
        "Cod.", "ISIN", "Simbolo", "Descrizione", "Valuta", "Paese",
        "Quantita", "Acquisto", "Vendita",
        "Val. iniz. orig.", "Val. fin. orig.",
        "Cambio iniz.", "Cambio fin.",
        "Val. iniz. EUR", "Val. fin. EUR",
        "Giorni", "Quota %", "IVAFE",
    ]
    _write_header(ws, headers)

    for line in report.rw_lines:
        row = [
            line.codice_investimento, line.isin, line.symbol,
            line.description, line.currency, line.country,
            float(line.quantity),
            line.acquisition_date.isoformat() if line.acquisition_date else "",
            line.disposed_date.isoformat() if line.disposed_date else "",
            float(line.initial_value), float(line.final_value),
            float(line.ecb_rate_initial), float(line.ecb_rate_final),
            float(line.initial_value_eur), float(line.final_value_eur),
            line.days_held, float(line.ownership_pct), float(line.ivafe_due),
        ]
        ws.append(row)

    ws.append([])
    total_row = ws.max_row + 1
    ws.append(["", "", "", "", "", "", "", "", "TOTALE", "", "",
               "", "", "", "", "", "", float(report.total_ivafe)])
    ws.cell(row=total_row, column=18).number_format = _MONEY_FMT
    ws.cell(row=total_row, column=18).font = _HEADER_FONT

    _format_money_columns(ws, [10, 11, 14, 15, 18], 2, ws.max_row)
    _auto_width(ws)


def _write_rt(ws: Worksheet, report: TaxReport) -> None:
    headers = [
        "Simbolo", "ISIN", "Data acquisto", "Data vendita", "Quantita",
        "Corrispettivo EUR", "Costo EUR", "+/- EUR",
        "Cambio BCE", "Forex", "P/L broker", "P/L broker EUR",
    ]
    _write_header(ws, headers)

    for line in report.rt_lines:
        ws.append([
            line.symbol, line.isin,
            line.acquisition_date.isoformat(), line.sell_date.isoformat(),
            float(line.quantity),
            float(line.proceeds_eur), float(line.cost_basis_eur),
            float(line.gain_loss_eur),
            float(line.ecb_rate),
            "Si" if line.is_forex else "No",
            float(line.broker_pnl), float(line.broker_pnl_eur),
        ])

    ws.append([])
    total_row = ws.max_row + 1
    ws.append(["", "", "", "", "", "", "NETTO", float(report.net_capital_gain_loss)])
    ws.cell(row=total_row, column=8).number_format = _MONEY_FMT
    ws.cell(row=total_row, column=8).font = _HEADER_FONT

    _format_money_columns(ws, [6, 7, 8, 11, 12], 2, ws.max_row)
    _auto_width(ws)


def _write_rl(ws: Worksheet, report: TaxReport) -> None:
    headers = [
        "Descrizione", "Valuta", "Lordo",
        "Lordo EUR", "Ritenuta", "Ritenuta EUR", "Netto EUR",
    ]
    _write_header(ws, headers)

    for line in report.rl_lines:
        ws.append([
            line.description, line.currency,
            float(line.gross_amount),
            float(line.gross_amount_eur), float(line.wht_amount),
            float(line.wht_amount_eur), float(line.net_amount_eur),
        ])

    ws.append([])
    total_row = ws.max_row + 1
    ws.append([
        "", "", "TOTALI",
        float(report.total_gross_interest_eur), "",
        float(report.total_wht_eur),
        float(report.total_gross_interest_eur - report.total_wht_eur),
    ])
    for col in (4, 6, 7):
        ws.cell(row=total_row, column=col).number_format = _MONEY_FMT
        ws.cell(row=total_row, column=col).font = _HEADER_FONT

    _format_money_columns(ws, [3, 4, 5, 6, 7], 2, ws.max_row)
    _auto_width(ws)


def _write_forex(ws: Worksheet, report: TaxReport) -> None:
    ws.append(["Analisi Soglia Valutaria", "", f"Anno fiscale {report.tax_year}"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([
        "Soglia: EUR 51.645,69",
        "",
        f"Risultato: {'SUPERATA' if report.forex_threshold_breached else 'NON SUPERATA'}",
        "",
        f"Massimo consecutivo: {report.forex_max_consecutive_days} giorni",
    ])
    ws.append([])

    headers = [
        "Data", "Saldo USD", "Equiv. EUR", "Cambio",
        "Giorno lavorativo", "Sopra soglia",
    ]
    _write_header(ws, headers, start_row=4)

    for rec in report.forex_daily_records:
        if rec.usd_balance == 0 and not rec.above_threshold:
            continue  # skip zero-balance days to keep sheet manageable
        ws.append([
            rec.date.isoformat(),
            float(rec.usd_balance),
            float(rec.eur_equivalent),
            float(rec.fx_rate),
            "Si" if rec.is_business_day else "",
            "SI" if rec.above_threshold else "",
        ])

    _format_money_columns(ws, [2, 3], 5, ws.max_row)
    _auto_width(ws)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_header(ws: Worksheet, headers: list[str], start_row: int = 1) -> None:
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center")


def _format_money_columns(ws: Worksheet, columns: list[int], start_row: int, end_row: int) -> None:
    for col in columns:
        for row in range(start_row, end_row + 1):
            cell = ws.cell(row=row, column=col)
            if isinstance(cell.value, (int, float)):
                cell.number_format = _MONEY_FMT


def _auto_width(ws: Worksheet) -> None:
    for col_idx in range(1, ws.max_column + 1):
        max_len = 0
        col_letter = get_column_letter(col_idx)
        for row in range(1, min(ws.max_row + 1, 50)):  # sample first 50 rows
            cell = ws.cell(row=row, column=col_idx)
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_len + 3, 40)
