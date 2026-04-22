"""PDF output for tax report - professional statement layout."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from decaf import __version__
from decaf.models import TaxReport

_MARGIN = 12
_BLUE = (31, 56, 100)
_LIGHT_BLUE = (220, 230, 242)
_ACCENT = (46, 116, 181)
_DARK_GRAY = (60, 60, 60)
_MED_GRAY = (120, 120, 120)
_LIGHT_GRAY = (245, 245, 248)
_WHITE = (255, 255, 255)
_ROW_ALT = (248, 250, 253)
_GREEN = (34, 120, 60)
_RED = (180, 40, 40)


class _TaxPDF(FPDF):
    def __init__(self, report: TaxReport) -> None:
        super().__init__(orientation="L", unit="mm", format="A4")
        self._report = report
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)

    def header(self) -> None:
        # Blue banner
        self.set_fill_color(*_BLUE)
        self.rect(0, 0, self.w, 22, "F")

        # Title on banner
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*_WHITE)
        self.set_y(4)
        self.cell(
            0, 8,
            f"Dichiarazione dei Redditi {self._report.tax_year}",
            new_x="LMARGIN", new_y="NEXT", align="L",
        )
        self.set_font("Helvetica", "", 8)
        self.set_text_color(200, 210, 230)
        acct = self._report.account
        self.cell(
            0, 5,
            f"{acct.broker_name}  |  "
            f"Conto {acct.account_id}  |  "
            f"{acct.holder_name}  |  "
            f"{acct.country}  |  "
            f"{acct.base_currency}",
            new_x="LMARGIN", new_y="NEXT",
        )
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(*_MED_GRAY)
        self.cell(
            0, 8,
            f"decaf v{__version__}  |  "
            f"Generato il {date.today().isoformat()}  |  "
            f"Pagina {self.page_no()}/{{nb}}",
            align="C",
        )

    def section_title(self, title: str, subtitle: str = "") -> None:
        self.ln(2)
        # Accent bar
        self.set_fill_color(*_ACCENT)
        self.rect(self.get_x(), self.get_y(), 2, 7, "F")
        self.set_x(self.get_x() + 4)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*_BLUE)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        if subtitle:
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(*_MED_GRAY)
            self.cell(0, 4, subtitle, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def fit_to_width(self, text: str, max_width_mm: float) -> str:
        """Truncate `text` with an ellipsis so it fits in `max_width_mm`.

        Uses the current font to measure. Caller must have set the font
        before calling (same as what data_table uses for data rows).
        """
        if self.get_string_width(text) <= max_width_mm:
            return text
        # Reserve 1mm of padding to keep the ellipsis off the cell border.
        # Latin-1 ellipsis (built-in Helvetica doesn't have the Unicode one).
        budget = max_width_mm - 1.0
        ellipsis = "..."
        while text and self.get_string_width(text + ellipsis) > budget:
            text = text[:-1]
        return text + ellipsis if text else ""

    def data_table(
        self,
        headers: list[str],
        widths: list[float],
        rows: list[list[str]],
        *,
        total_row: bool = True,
    ) -> None:
        # Header row - dark blue background
        self.set_font("Helvetica", "B", 6.5)
        self.set_fill_color(*_BLUE)
        self.set_text_color(*_WHITE)
        for hdr, w in zip(headers, widths, strict=True):
            self.cell(w, 5.5, hdr, border=0, fill=True, align="C")
        self.ln()

        # Data rows
        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(*_DARK_GRAY)
        n_rows = len(rows)
        last_idx = n_rows - 1 if total_row else -1

        for i, row in enumerate(rows):
            is_total = i == last_idx
            if is_total:
                self.set_font("Helvetica", "B", 6.5)
                self.set_fill_color(*_LIGHT_BLUE)
                fill = True
            elif i % 2 == 1:
                self.set_fill_color(*_ROW_ALT)
                fill = True
            else:
                fill = False
            for val, w in zip(row, widths, strict=True):
                align = "R" if _looks_numeric(val) else "L"
                self.cell(w, 4.5, val, border=0, fill=fill, align=align)
            self.ln()
            if is_total:
                self.set_font("Helvetica", "", 6.5)

        # Bottom border
        self.set_draw_color(*_ACCENT)
        x = self.get_x()
        y = self.get_y()
        self.line(x, y, x + sum(widths), y)
        self.set_draw_color(0, 0, 0)
        self.ln(1)

    def summary_kv(self, items: list[tuple[str, str]]) -> None:
        self.set_text_color(*_DARK_GRAY)
        for label, value in items:
            self.set_font("Helvetica", "", 8.5)
            self.cell(75, 5.5, label, new_x="END")
            self.set_font("Helvetica", "B", 8.5)
            self.cell(55, 5.5, value, new_x="LMARGIN", new_y="NEXT")


def _eur(v: Decimal) -> str:
    return f"{v:,.2f}"


def write_pdf(report: TaxReport, path: Path) -> None:
    """Write the tax report as a professional PDF."""
    pdf = _TaxPDF(report)
    pdf.alias_nb_pages()

    # --- Page 1: Summary ---
    pdf.add_page()
    pdf.section_title("Riepilogo Fiscale")

    net_rt = report.net_capital_gain_loss
    rt_sign = "+" if net_rt >= 0 else ""

    pdf.summary_kv([
        ("IVAFE totale (Quadro RW)", f"EUR {_eur(report.total_ivafe)}"),
        ("Plusvalenze nette (Quadro RT)", f"EUR {rt_sign}{_eur(net_rt)}"),
        ("Redditi lordi (Quadro RL)", f"EUR {_eur(report.total_gross_interest_eur)}"),
        ("Ritenute estere (Quadro RL)", f"EUR {_eur(report.total_wht_eur)}"),
    ])

    pdf.ln(2)
    pdf.section_title(
        "Soglia Valutaria",
        "Art. 67(1)(c-ter) TUIR - giacenza in valuta estera > EUR 51.645,69",
    )
    breach = report.forex_threshold_breached
    pdf.summary_kv([
        ("Risultato",
         "SUPERATA" if breach else "NON SUPERATA"),
        ("Giorni lavorativi consecutivi",
         f"{report.forex_max_consecutive_days} / 7"),
        ("Data prima violazione",
         report.forex_first_breach_date.isoformat()
         if report.forex_first_breach_date else "-"),
    ])

    if report.rsu_vest_count:
        pdf.ln(2)
        pdf.section_title(
            "Controllo coerenza RSU",
            "Valore Normale ex art. 9 c. 4 lett. a) + art. 68 c. 6 TUIR",
        )
        pdf.summary_kv([
            ("Vest events nell'anno", f"{report.rsu_vest_count}"),
            ("Reddito RSU tassato",
             f"EUR {_eur(report.rsu_income_eur)}"),
        ])
        pdf.ln(1)
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(*_DARK_GRAY)
        note = (
            "Cross-check: questo valore deve essere un sottoinsieme del "
            "punto 1 della Certificazione Unica \"Redditi di lavoro dipendente\". "
            "Differenza = stipendio + bonus + altri compensi. Calcolato come "
            "sum(ITA FMV x net shares) convertito al cambio BCE del giorno di vest; "
            "la colonna ITA FMV dell'Annual Withholding Statement Schwab e' il Valore "
            "Normale tassato in busta paga e riportato sulla CU."
        )
        pdf.multi_cell(0, 3.5, note)

    # --- Quadro RW ---
    pdf.section_title(
        "Quadro RW - Monitoraggio fiscale e IVAFE",
        "Investimenti e attivita finanziarie all'estero (D.L. 201/2011)",
    )
    rw_headers = [
        "Cod.", "ISIN", "Simbolo", "Azienda", "Val.", "Paese", "Qty",
        "Acquisto", "Vendita",
        "Val. iniz. EUR", "Val. fin. EUR",
        "Giorni", "IVAFE EUR",
    ]
    rw_widths = [
        10.0, 26.0, 16.0, 38.0, 12.0, 13.0, 16.0,
        20.0, 20.0,
        26.0, 26.0,
        14.0, 22.0,
    ]
    # Pre-truncate the Azienda column against the actual font metrics.
    # Width minus ~1mm of cell padding keeps text off the border.
    pdf.set_font("Helvetica", "", 6.5)
    rw_rows = [
        [
            str(rw.codice_investimento), rw.isin, rw.symbol,
            pdf.fit_to_width(rw.long_description, 38.0),
            rw.currency, rw.country, f"{rw.quantity:,.0f}",
            rw.acquisition_date.isoformat() if rw.acquisition_date else "",
            rw.disposed_date.isoformat() if rw.disposed_date else "",
            _eur(rw.initial_value_eur), _eur(rw.final_value_eur),
            str(rw.days_held), _eur(rw.ivafe_due),
        ]
        for rw in report.rw_lines
    ]
    rw_rows.append([
        "", "", "", "", "", "", "", "", "TOTALE",
        "", "", "", _eur(report.total_ivafe),
    ])
    pdf.data_table(rw_headers, rw_widths, rw_rows)

    # --- Quadro RT ---
    pdf.section_title(
        "Quadro RT - Plusvalenze di natura finanziaria",
        "Sez. II-A, imposta sostitutiva 26% (art. 67(1)(c-bis) TUIR)",
    )
    if report.rt_lines:
        rt_headers = [
            "Simbolo", "ISIN", "Azienda", "Acquisto", "Vendita", "Qty",
            "Corrispettivo", "Costo", "+/- EUR",
            "Cambio", "Fx", "P/L broker",
        ]
        rt_widths = [
            14.0, 26.0, 38.0, 20.0, 20.0, 14.0,
            26.0, 26.0, 24.0,
            15.0, 8.0, 22.0,
        ]
        pdf.set_font("Helvetica", "", 6.5)
        rt_rows = [
            [
                rt.symbol, rt.isin,
                pdf.fit_to_width(rt.long_description, 38.0),
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
            "", "", "", "", "", "", "", "NETTO",
            _eur(report.net_capital_gain_loss), "", "", "",
        ])
        pdf.data_table(rt_headers, rt_widths, rt_rows)
    else:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*_MED_GRAY)
        pdf.cell(
            0, 6,
            "Nessuna plusvalenza o minusvalenza realizzata.",
            new_x="LMARGIN", new_y="NEXT",
        )

    # --- Quadro RL ---
    pdf.section_title(
        "Quadro RL - Redditi di capitale",
        "Sez. I, rigo RL2 - redditi di fonte estera (art. 44 TUIR)",
    )
    if report.rl_lines:
        rl_headers = [
            "Descrizione", "Valuta", "Lordo",
            "Lordo EUR", "Ritenuta", "Ritenuta EUR", "Netto EUR",
        ]
        rl_widths = [68.0, 16.0, 24.0, 27.0, 24.0, 27.0, 27.0]
        rl_rows = [
            [
                rl.description[:45], rl.currency,
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
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*_MED_GRAY)
        pdf.cell(
            0, 6,
            "Nessun reddito di capitale.",
            new_x="LMARGIN", new_y="NEXT",
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def _looks_numeric(s: str) -> bool:
    s = s.replace(",", "").replace(" ", "").replace("EUR", "")
    try:
        float(s)
        return True
    except ValueError:
        return False
