"""PDF output for tax report — professional statement layout."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from decaf import __version__
from decaf.models import TaxReport

_MARGIN = 15
_COL_GRAY = (240, 240, 240)
_HEADER_BLUE = (41, 65, 122)


class _TaxPDF(FPDF):
    def __init__(self, report: TaxReport) -> None:
        super().__init__(orientation="L", unit="mm", format="A4")
        self._report = report
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)

    def header(self) -> None:
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*_HEADER_BLUE)
        self.cell(
            0, 10,
            f"Report Fiscale Italiano - Dichiarazione dei Redditi {self._report.tax_year}",
            new_x="LMARGIN", new_y="NEXT",
        )
        self.set_font("Helvetica", "", 8)
        self.set_text_color(100, 100, 100)
        self.cell(
            0, 5,
            f"Conto: {self._report.account.account_id} | "
            f"Titolare: {self._report.account.holder_name} | "
            f"Broker: {self._report.account.broker_name} | "
            f"Paese: {self._report.account.country} | "
            f"Valuta base: {self._report.account.base_currency}",
            new_x="LMARGIN", new_y="NEXT",
        )
        self.line(_MARGIN, self.get_y() + 1, self.w - _MARGIN, self.get_y() + 1)
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(140, 140, 140)
        self.cell(
            0, 10,
            f"Generato da decaf v{__version__} il {date.today().isoformat()} | "
            f"Pagina {self.page_no()}/{{nb}}",
            align="C",
        )

    def section_title(self, title: str) -> None:
        self.ln(3)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*_HEADER_BLUE)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def data_table(self, headers: list[str], widths: list[float], rows: list[list[str]]) -> None:
        # Header row
        self.set_font("Helvetica", "B", 7)
        self.set_fill_color(*_COL_GRAY)
        for hdr, w in zip(headers, widths, strict=True):
            self.cell(w, 6, hdr, border=1, fill=True, align="C")
        self.ln()

        # Data rows
        self.set_font("Helvetica", "", 7)
        for i, row in enumerate(rows):
            if i % 2 == 1:
                self.set_fill_color(250, 250, 255)
                fill = True
            else:
                fill = False
            for val, w in zip(row, widths, strict=True):
                align = "R" if _looks_numeric(val) else "L"
                self.cell(w, 5, val, border=0, fill=fill, align=align)
            self.ln()

    def summary_kv(self, items: list[tuple[str, str]]) -> None:
        self.set_font("Helvetica", "", 9)
        for label, value in items:
            self.cell(80, 6, label, new_x="END")
            self.set_font("Helvetica", "B", 9)
            self.cell(60, 6, value, new_x="LMARGIN", new_y="NEXT")
            self.set_font("Helvetica", "", 9)


def _eur(v: Decimal) -> str:
    return f"{v:,.2f}"


def write_pdf(report: TaxReport, path: Path) -> None:
    """Write the tax report as a professional PDF."""
    pdf = _TaxPDF(report)
    pdf.alias_nb_pages()

    # --- Page 1: Summary ---
    pdf.add_page()
    pdf.section_title("Riepilogo Fiscale")
    pdf.summary_kv([
        ("IVAFE totale (Quadro RW)", f"EUR {_eur(report.total_ivafe)}"),
        ("Plusvalenze nette (Quadro RT)", f"EUR {_eur(report.net_capital_gain_loss)}"),
        ("Redditi lordi (Quadro RL)", f"EUR {_eur(report.total_gross_interest_eur)}"),
        ("Ritenute estere (Quadro RL)", f"EUR {_eur(report.total_wht_eur)}"),
    ])

    pdf.ln(3)
    pdf.section_title("Analisi Soglia Valutaria (art. 67(1)(c-ter) TUIR)")
    pdf.summary_kv([
        ("Soglia", "EUR 51,645.69"),
        ("Risultato", "SUPERATA" if report.forex_threshold_breached else "NON SUPERATA"),
        ("Giorni lavorativi consecutivi", str(report.forex_max_consecutive_days)),
        (
            "Data prima violazione",
            report.forex_first_breach_date.isoformat()
            if report.forex_first_breach_date else "N/A",
        ),
    ])

    # --- Quadro RW ---
    pdf.ln(3)
    pdf.section_title("Quadro RW - Investimenti e attivita finanziarie all'estero")
    rw_headers = [
        "Cod.", "ISIN", "Simbolo", "Valuta", "Paese", "Quantita",
        "Acquisto", "Vendita", "Val. iniz. EUR", "Val. fin. EUR",
        "Giorni", "IVAFE",
    ]
    rw_widths = [12.0, 30.0, 18.0, 14.0, 14.0, 18.0, 22.0, 22.0, 28.0, 28.0, 16.0, 22.0]
    rw_rows = [
        [
            str(rw.codice_investimento), rw.isin, rw.symbol,
            rw.currency, rw.country, f"{rw.quantity:,.0f}",
            rw.acquisition_date.isoformat() if rw.acquisition_date else "",
            rw.disposed_date.isoformat() if rw.disposed_date else "",
            _eur(rw.initial_value_eur), _eur(rw.final_value_eur),
            str(rw.days_held), _eur(rw.ivafe_due),
        ]
        for rw in report.rw_lines
    ]
    rw_rows.append(["", "", "", "", "", "", "", "TOTALE", "", "", "", _eur(report.total_ivafe)])
    pdf.data_table(rw_headers, rw_widths, rw_rows)

    # --- Quadro RT ---
    pdf.section_title("Quadro RT - Plusvalenze di natura finanziaria")
    if report.rt_lines:
        rt_headers = [
            "Simbolo", "ISIN", "Acquisto", "Vendita", "Quantita",
            "Corrispettivo EUR", "Costo EUR", "+/- EUR",
            "Cambio", "Forex", "P/L broker",
        ]
        rt_widths = [
            16.0, 30.0, 22.0, 22.0, 16.0,
            27.0, 27.0, 27.0, 18.0, 13.0, 27.0,
        ]
        rt_rows = [
            [
                rt.symbol, rt.isin,
                rt.acquisition_date.isoformat(),
                rt.sell_date.isoformat(),
                f"{rt.quantity:,.0f}",
                _eur(rt.proceeds_eur), _eur(rt.cost_basis_eur),
                _eur(rt.gain_loss_eur),
                f"{rt.ecb_rate:.4f}" if rt.ecb_rate != 1 else "",
                "Si" if rt.is_forex else "",
                _eur(rt.broker_pnl),
            ]
            for rt in report.rt_lines
        ]
        rt_rows.append([
            "", "", "", "", "", "", "NETTO",
            _eur(report.net_capital_gain_loss), "", "", "",
        ])
        pdf.data_table(rt_headers, rt_widths, rt_rows)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(
            0, 6, "Nessuna plusvalenza o minusvalenza realizzata in questo anno fiscale.",
            new_x="LMARGIN", new_y="NEXT",
        )

    # --- Quadro RL ---
    pdf.section_title("Quadro RL - Redditi di capitale")
    if report.rl_lines:
        rl_headers = [
            "Descrizione", "Valuta", "Lordo", "Lordo EUR",
            "Ritenuta", "Ritenuta EUR", "Netto EUR",
        ]
        rl_widths = [70.0, 18.0, 25.0, 28.0, 25.0, 28.0, 28.0]
        rl_rows = [
            [
                rl.description[:40], rl.currency,
                _eur(rl.gross_amount), _eur(rl.gross_amount_eur),
                _eur(rl.wht_amount), _eur(rl.wht_amount_eur),
                _eur(rl.net_amount_eur),
            ]
            for rl in report.rl_lines
        ]
        total_net = report.total_gross_interest_eur - report.total_wht_eur
        rl_rows.append([
            "", "TOTALI", "",
            _eur(report.total_gross_interest_eur), "",
            _eur(report.total_wht_eur),
            _eur(total_net),
        ])
        pdf.data_table(rl_headers, rl_widths, rl_rows)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 6, "Nessun reddito di capitale in questo anno fiscale.",
                 new_x="LMARGIN", new_y="NEXT")

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def _looks_numeric(s: str) -> bool:
    s = s.replace(",", "").replace(" ", "").replace("EUR", "")
    try:
        float(s)
        return True
    except ValueError:
        return False
