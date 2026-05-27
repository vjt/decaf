"""PDF output for tax report - professional statement layout."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from fpdf import FPDF

from decaf import __version__
from decaf.models import RTLine, TaxReport

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

_FONT = "DejaVu"  # bundled TTF: supports €, £, accented glyphs


def _register_fonts(pdf: FPDF) -> None:
    """Register the bundled DejaVu Sans family on the PDF."""
    fonts_dir = files("decaf").joinpath("assets/fonts")
    pdf.add_font(_FONT, "", str(fonts_dir.joinpath("DejaVuSans.ttf")))
    pdf.add_font(_FONT, "B", str(fonts_dir.joinpath("DejaVuSans-Bold.ttf")))
    pdf.add_font(_FONT, "I", str(fonts_dir.joinpath("DejaVuSans-Oblique.ttf")))


class _TaxPDF(FPDF):
    def __init__(self, report: TaxReport) -> None:
        super().__init__(orientation="L", unit="mm", format="A4")
        self._report = report
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)
        _register_fonts(self)

    def header(self) -> None:
        # Blue banner
        self.set_fill_color(*_BLUE)
        self.rect(0, 0, self.w, 22, "F")

        # Title on banner
        self.set_font(_FONT, "B", 16)
        self.set_text_color(*_WHITE)
        self.set_y(4)
        self.cell(
            0,
            8,
            f"Dichiarazione dei Redditi {self._report.tax_year}",
            new_x="LMARGIN",
            new_y="NEXT",
            align="L",
        )
        self.set_font(_FONT, "", 8)
        self.set_text_color(200, 210, 230)
        acct = self._report.account
        self.cell(
            0,
            5,
            f"{acct.broker_name}  |  "
            f"Conto {acct.account_id}  |  "
            f"{acct.holder_name}  |  "
            f"{acct.country}  |  "
            f"{acct.base_currency}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-12)
        repo_url = "https://github.com/vjt/decaf"
        prefix = "Generato da "
        version_label = f"decaf v{__version__}"
        suffix = f"  |  {date.today().isoformat()}  |  Pagina {self.page_no()}/{{nb}}"
        # Measure each piece with its own style so total width is accurate
        self.set_font(_FONT, "", 6.5)
        w_prefix = self.get_string_width(prefix)
        w_suffix = self.get_string_width(suffix)
        self.set_font(_FONT, "U", 6.5)
        w_version = self.get_string_width(version_label)
        total_w = w_prefix + w_version + w_suffix
        left = (self.w - total_w) / 2
        self.set_x(left)
        # Prefix: gray, normal
        self.set_font(_FONT, "", 6.5)
        self.set_text_color(*_MED_GRAY)
        self.cell(w_prefix, 8, prefix)
        # Version: blue, underlined, clickable — looks like a link
        self.set_font(_FONT, "U", 6.5)
        self.set_text_color(*_BLUE)
        self.cell(w_version, 8, version_label, link=repo_url)
        # Suffix: gray, normal again
        self.set_font(_FONT, "", 6.5)
        self.set_text_color(*_MED_GRAY)
        self.cell(w_suffix, 8, suffix)

    def section_title(self, title: str, subtitle: str = "") -> None:
        self.ln(2)
        # Accent bar
        self.set_fill_color(*_ACCENT)
        self.rect(self.get_x(), self.get_y(), 2, 7, "F")
        self.set_x(self.get_x() + 4)
        self.set_font(_FONT, "B", 10)
        self.set_text_color(*_BLUE)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        if subtitle:
            self.set_font(_FONT, "I", 7)
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
        budget = max_width_mm - 1.0
        ellipsis = "..."
        while text and self.get_string_width(text + ellipsis) > budget:
            text = text[:-1]
        return text + ellipsis if text else ""

    def _draw_table_header(self, headers: list[str], widths: list[float]) -> None:
        self.set_font(_FONT, "B", 6.5)
        self.set_fill_color(*_BLUE)
        self.set_text_color(*_WHITE)
        for hdr, w in zip(headers, widths, strict=True):
            self.cell(w, 5.5, hdr, border=0, fill=True, align="C")
        self.ln()

    def data_table(
        self,
        headers: list[str],
        widths: list[float],
        rows: list[list[str]],
        *,
        total_row: bool = True,
    ) -> None:
        # Suppress fpdf2's auto page-break so we can insert headers ourselves
        # — otherwise a row landing on the new page would have no header above it.
        prev_auto = self.auto_page_break
        prev_margin = self.b_margin
        self.set_auto_page_break(False)

        row_h = 4.5
        page_limit = self.h - prev_margin

        self._draw_table_header(headers, widths)

        # Data rows
        self.set_font(_FONT, "", 6.5)
        self.set_text_color(*_DARK_GRAY)
        n_rows = len(rows)
        last_idx = n_rows - 1 if total_row else -1

        for i, row in enumerate(rows):
            is_total = i == last_idx
            # Reserve room for this row + bottom border; if we'd cross the
            # page limit, break the page and re-emit the table header.
            if self.get_y() + row_h + 1 > page_limit:
                self.add_page()
                self._draw_table_header(headers, widths)
                self.set_font(_FONT, "", 6.5)
                self.set_text_color(*_DARK_GRAY)
            if is_total:
                self.set_font(_FONT, "B", 6.5)
                self.set_fill_color(*_LIGHT_BLUE)
                fill = True
            elif i % 2 == 1:
                self.set_fill_color(*_ROW_ALT)
                fill = True
            else:
                fill = False
            for val, w in zip(row, widths, strict=True):
                align = "R" if _looks_numeric(val) else "L"
                self.cell(w, row_h, val, border=0, fill=fill, align=align)
            self.ln()
            if is_total:
                self.set_font(_FONT, "", 6.5)

        # Bottom border
        self.set_draw_color(*_ACCENT)
        x = self.get_x()
        y = self.get_y()
        self.line(x, y, x + sum(widths), y)
        self.set_draw_color(0, 0, 0)
        self.ln(1)

        # Restore the user's auto-page-break setting for whatever comes next.
        self.set_auto_page_break(prev_auto, margin=prev_margin)

    def summary_kv(self, items: list[tuple[str, str]]) -> None:
        self.set_text_color(*_DARK_GRAY)
        for label, value in items:
            self.set_font(_FONT, "", 8.5)
            self.cell(75, 5.5, label, new_x="END")
            self.set_font(_FONT, "B", 8.5)
            self.cell(55, 5.5, value, new_x="LMARGIN", new_y="NEXT")


def _eur(v: Decimal) -> str:
    return f"{v:,.2f}"


_CURRENCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£"}


def _ccy_prefix(currency: str) -> str:
    return _CURRENCY_SYMBOL.get(currency, currency + " ")


def _money(value: Decimal, currency: str) -> str:
    return f"{_ccy_prefix(currency)}{value:,.2f}"


def _per_share(total: Decimal, quantity: Decimal, currency: str) -> str:
    if quantity == 0 or total == 0:
        return ""
    return f"{_ccy_prefix(currency)}{(total / quantity).quantize(Decimal('0.01')):,.2f}/sh"


def _per_share_only(total: Decimal, quantity: Decimal, currency: str) -> str:
    """Per-share value without the '/sh' suffix (column header carries the unit)."""
    if quantity == 0 or total == 0:
        return ""
    return f"{_ccy_prefix(currency)}{(total / quantity).quantize(Decimal('0.01')):,.2f}"


def _strip_acquired(description: str) -> str:
    """Drop trailing ' (acquired YYYY-MM-DD)' — date is in its own column."""
    idx = description.find(" (acquired ")
    return description[:idx] if idx >= 0 else description


def _broker_cost_total(rt: RTLine) -> str:
    if rt.is_forex or rt.broker_cost_basis == 0:
        return ""
    return _money(rt.broker_cost_basis, rt.currency)


def _broker_pnl_cell(rt: RTLine) -> str:
    if rt.is_forex or rt.broker_pnl == 0:
        return ""
    return _money(rt.broker_pnl, rt.currency)


def _sum_by_currency(
    lines: list[RTLine],
    extract: Callable[[RTLine], Decimal],
) -> dict[str, Decimal]:
    """Aggregate a Decimal field across RT lines, grouped by currency.
    Skips forex lines (their broker fields are zero/meaningless).
    """
    totals: dict[str, Decimal] = {}
    for line in lines:
        if line.is_forex:
            continue
        value = extract(line)
        if value == 0:
            continue
        totals[line.currency] = totals.get(line.currency, Decimal(0)) + value
    return totals


def _multi_currency_sum(totals: dict[str, Decimal]) -> str:
    """Render '$1,234.56' for a single ccy or '$X / €Y' for mixed."""
    if not totals:
        return ""
    return " / ".join(_money(v, ccy) for ccy, v in sorted(totals.items()))


def write_pdf(report: TaxReport, path: Path) -> None:
    """Write the tax report as a professional PDF."""
    pdf = _TaxPDF(report)
    pdf.alias_nb_pages()

    # --- Page 1: Summary ---
    pdf.add_page()
    pdf.section_title("Riepilogo Fiscale")

    net_rt = report.net_capital_gain_loss
    rt_sign = "+" if net_rt >= 0 else ""

    pdf.summary_kv(
        [
            ("IVAFE totale (Quadro RW)", f"EUR {_eur(report.total_ivafe)}"),
            ("Plusvalenze nette (Quadro RT)", f"EUR {rt_sign}{_eur(net_rt)}"),
            ("Redditi lordi (Quadro RL)", f"EUR {_eur(report.total_gross_interest_eur)}"),
            ("Ritenute estere (Quadro RL)", f"EUR {_eur(report.total_wht_eur)}"),
        ]
    )

    pdf.ln(2)
    pdf.section_title(
        "Soglia Valutaria",
        "Art. 67(1)(c-ter) TUIR - giacenza in valuta estera > EUR 51.645,69",
    )
    breach = report.forex_threshold_breached
    pdf.summary_kv(
        [
            ("Risultato", "SUPERATA" if breach else "NON SUPERATA"),
            ("Giorni lavorativi consecutivi", f"{report.forex_max_consecutive_days} / 7"),
            (
                "Data prima violazione",
                report.forex_first_breach_date.isoformat()
                if report.forex_first_breach_date
                else "-",
            ),
        ]
    )

    if report.rsu_vest_count:
        pdf.ln(2)
        pdf.section_title(
            "Controllo coerenza RSU",
            "Valore Normale ex art. 9 c. 4 lett. a) + art. 68 c. 6 TUIR",
        )
        pdf.summary_kv(
            [
                ("Vest events nell'anno", f"{report.rsu_vest_count}"),
                ("Reddito RSU tassato", f"EUR {_eur(report.rsu_income_eur)}"),
            ]
        )
        pdf.ln(1)
        pdf.set_font(_FONT, "I", 7.5)
        pdf.set_text_color(*_DARK_GRAY)
        note = (
            "Cross-check: questo valore deve essere un sottoinsieme del "
            'punto 1 della Certificazione Unica "Redditi di lavoro dipendente". '
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
        "Cod.",
        "ISIN",
        "Simbolo",
        "Azienda",
        "Val.",
        "Paese",
        "Qty",
        "Acquisto",
        "Vendita",
        "Val. iniz. EUR",
        "Val. fin. EUR",
        "Giorni",
        "IVAFE EUR",
    ]
    rw_widths = [
        10.0,
        26.0,
        16.0,
        38.0,
        12.0,
        13.0,
        16.0,
        20.0,
        20.0,
        26.0,
        26.0,
        14.0,
        22.0,
    ]
    # Pre-truncate the Azienda column against the actual font metrics.
    # Width minus ~1mm of cell padding keeps text off the border.
    pdf.set_font(_FONT, "", 6.5)
    rw_rows = [
        [
            str(rw.codice_investimento),
            rw.isin,
            rw.symbol,
            pdf.fit_to_width(rw.long_description, 38.0),
            rw.currency,
            rw.country,
            f"{rw.quantity:,.0f}",
            rw.acquisition_date.isoformat() if rw.acquisition_date else "",
            rw.disposed_date.isoformat() if rw.disposed_date else "",
            _eur(rw.initial_value_eur),
            _eur(rw.final_value_eur),
            str(rw.days_held),
            _eur(rw.ivafe_due),
        ]
        for rw in report.rw_lines
    ]
    rw_rows.append(
        [
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "TOTALE",
            "",
            "",
            "",
            _eur(report.total_ivafe),
        ]
    )
    pdf.data_table(rw_headers, rw_widths, rw_rows)

    # --- Quadro RT ---
    pdf.section_title(
        "Quadro RT - Plusvalenze di natura finanziaria",
        "Sez. II-A, imposta sostitutiva 26% (art. 67(1)(c-bis) TUIR)",
    )
    if report.rt_lines:
        rt_headers = [
            "Simbolo",
            "ISIN",
            "Azienda",
            "Acquisto",
            "VN/sh",
            "Broker/sh",
            "Vendita",
            "Sell/sh",
            "Qty",
            "Base",
            "Corrispettivo",
            "Comm.",
            "P/L",
            "Cambio",
            "Broker cost",
            "Broker P/L",
        ]
        rt_widths = [
            12.0,
            22.0,
            20.0,
            19.0,
            16.0,
            16.0,
            19.0,
            16.0,
            10.0,
            20.0,
            22.0,
            14.0,
            18.0,
            12.0,
            22.0,
            22.0,
        ]
        pdf.set_font(_FONT, "", 6.5)
        rt_rows = [
            [
                rt.symbol,
                rt.isin,
                pdf.fit_to_width(_strip_acquired(rt.long_description), 20.0),
                rt.acquisition_date.isoformat(),
                _per_share_only(rt.normal_value_cost, rt.quantity, rt.currency),
                _per_share_only(rt.broker_cost_basis, rt.quantity, rt.currency)
                if not rt.is_forex
                else "",
                rt.sell_date.isoformat(),
                _per_share_only(rt.proceeds_native, rt.quantity, rt.currency),
                f"{rt.quantity:,.0f}",
                _money(rt.cost_basis_eur, "EUR"),
                _money(rt.proceeds_eur, "EUR"),
                _money(rt.commission_eur, "EUR") if rt.commission_eur else "",
                _money(rt.gain_loss_eur, "EUR"),
                f"{rt.ecb_rate:.4f}" if rt.ecb_rate != 1 else "",
                _broker_cost_total(rt),
                _broker_pnl_cell(rt),
            ]
            for rt in report.rt_lines
        ]
        # Per-currency broker totals — match the Schwab Year-End Summary
        # 'TOTAL REALIZED GAIN OR (LOSS)' line for direct cross-check.
        broker_pnl_by_ccy = _sum_by_currency(report.rt_lines, lambda r: r.broker_pnl)
        broker_cost_by_ccy = _sum_by_currency(report.rt_lines, lambda r: r.broker_cost_basis)
        total_cost_eur = sum((r.cost_basis_eur for r in report.rt_lines), Decimal(0))
        total_proceeds_eur = sum((r.proceeds_eur for r in report.rt_lines), Decimal(0))
        total_comm_eur = sum((r.commission_eur for r in report.rt_lines), Decimal(0))
        rt_rows.append(
            [
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "NETTO",
                _money(total_cost_eur, "EUR"),
                _money(total_proceeds_eur, "EUR"),
                _money(total_comm_eur, "EUR") if total_comm_eur else "",
                _money(report.net_capital_gain_loss, "EUR"),
                "",
                _multi_currency_sum(broker_cost_by_ccy),
                _multi_currency_sum(broker_pnl_by_ccy),
            ]
        )
        pdf.data_table(rt_headers, rt_widths, rt_rows)
    else:
        pdf.set_font(_FONT, "I", 8)
        pdf.set_text_color(*_MED_GRAY)
        pdf.cell(
            0,
            6,
            "Nessuna plusvalenza o minusvalenza realizzata.",
            new_x="LMARGIN",
            new_y="NEXT",
        )

    # --- Quadro RL ---
    pdf.section_title(
        "Quadro RL - Redditi di capitale",
        "Sez. I, rigo RL2 - redditi di fonte estera (art. 44 TUIR)",
    )
    if report.rl_lines:
        rl_headers = [
            "Descrizione",
            "Valuta",
            "Lordo",
            "Lordo EUR",
            "Ritenuta",
            "Ritenuta EUR",
            "Netto EUR",
        ]
        rl_widths = [68.0, 16.0, 24.0, 27.0, 24.0, 27.0, 27.0]
        rl_rows = [
            [
                rl.description[:45],
                rl.currency,
                _eur(rl.gross_amount),
                _eur(rl.gross_amount_eur),
                _eur(rl.wht_amount),
                _eur(rl.wht_amount_eur),
                _eur(rl.net_amount_eur),
            ]
            for rl in report.rl_lines
        ]
        total_net = report.total_gross_interest_eur - report.total_wht_eur
        rl_rows.append(
            [
                "",
                "TOTALI",
                "",
                _eur(report.total_gross_interest_eur),
                "",
                _eur(report.total_wht_eur),
                _eur(total_net),
            ]
        )
        pdf.data_table(rl_headers, rl_widths, rl_rows)
    else:
        pdf.set_font(_FONT, "I", 8)
        pdf.set_text_color(*_MED_GRAY)
        pdf.cell(
            0,
            6,
            "Nessun reddito di capitale.",
            new_x="LMARGIN",
            new_y="NEXT",
        )

    # --- Per la dichiarazione precompilata ---
    _write_precompilata(pdf, report)

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def _write_precompilata(pdf: _TaxPDF, report: TaxReport) -> None:
    """Render the 'Per la dichiarazione precompilata' guidance block.

    Maps decaf aggregates to the exact rigo/colonna of the current AdE
    precompilata Modello Redditi PF form so the user can copy values directly.
    """
    if not (report.rw_lines or report.rt_lines or report.rl_lines):
        return

    pdf.add_page()
    pdf.section_title(
        f"Per la dichiarazione precompilata (anno fiscale {report.tax_year})",
        "Mappa decaf -> Modello Redditi PF. I valori sono in EUR salvo dove indicato.",
    )

    # --- Quadro RW ---
    if report.rw_lines:
        pdf.section_title(
            "Quadro RW - un modulo per ogni riga",
            "Colonne fisse: col.1=1 (proprieta), col.5=100%, col.6=1 (valore di mercato).",
        )
        rw_headers = [
            "Modulo",
            "col.3\nCod. bene",
            "col.4\nStato",
            "col.7\nVal. iniziale",
            "col.8\nVal. finale",
            "col.10\nGiorni",
            "col.30\nIVAFE dovuta",
            "Note",
        ]
        rw_widths = [16.0, 18.0, 14.0, 26.0, 26.0, 16.0, 26.0, 48.0]
        rw_rows = [
            [
                f"RW{idx}",
                str(line.codice_investimento),
                line.country,
                _eur(line.initial_value_eur),
                _eur(line.final_value_eur),
                str(line.days_held),
                _eur(line.ivafe_due),
                pdf.fit_to_width(f"{line.symbol} {_strip_acquired(line.long_description)}", 48.0),
            ]
            for idx, line in enumerate(report.rw_lines, start=1)
        ]
        pdf.data_table(rw_headers, rw_widths, rw_rows, total_row=False)

    # --- Quadro RT ---
    if report.rt_lines:
        pdf.section_title(
            "Quadro RT - Sez. II-A (imposta sostitutiva 26%)",
            "Partecipazioni non qualificate. Un solo rigo aggregato (RT11). "
            "Minus pregresse: RT13 (manuale, decaf non le conosce).",
        )
        net = report.net_capital_gain_loss
        rt_headers = ["Rigo", "Colonna", "Valore EUR", "Origine"]
        rt_widths = [22.0, 70.0, 32.0, 66.0]
        rt_rows = [
            [
                "RT11",
                "col.1 - Totale corrispettivi",
                _eur(report.rt_total_proceeds_eur),
                f"somma proceeds_eur ({len(report.rt_lines)} righe)",
            ],
            [
                "RT11",
                "col.2 - Totale costi",
                _eur(report.rt_total_cost_basis_eur),
                f"somma cost_basis_eur ({len(report.rt_lines)} righe)",
            ],
            [
                "",
                "Differenza (plus/minus netta)",
                f"{'+' if net >= 0 else ''}{_eur(net)}",
                "calcolata in automatico dal software AdE",
            ],
        ]
        if net > 0:
            rt_rows.append(
                [
                    "",
                    "Imposta sostitutiva 26%",
                    _eur(net * Decimal("0.26")),
                    "calcolata in automatico dal software AdE",
                ]
            )
        pdf.data_table(rt_headers, rt_widths, rt_rows, total_row=False)

    # --- Quadro RL + Quadro RM (mutually exclusive — show comparison) ---
    if report.rl_lines:
        gross = report.total_gross_interest_eur
        wht = report.total_wht_eur

        pdf.section_title(
            "Alternativa A: Quadro RL - Sez. I-A, rigo RL2",
            "IRPEF marginale + credito d'imposta estera (richiede anche Quadro CE).",
        )
        rl_headers = ["Rigo", "Colonna", "Valore EUR", "Origine"]
        rl_widths = [22.0, 70.0, 32.0, 66.0]
        rl_rows = [
            ["RL2", "col.1 - Tipo reddito (dropdown)", "manuale", "es. B (dividendi non qualif.)"],
            ["RL2", "col.2 - Redditi (lordo)", _eur(gross), "somma gross_amount_eur"],
            [
                "RL2",
                "col.3 - Ritenute",
                _eur(wht),
                "somma wht_amount_eur (credito art. 165 -> CE)",
            ],
        ]
        pdf.data_table(rl_headers, rl_widths, rl_rows, total_row=False)

        pdf.section_title(
            "Alternativa B: Quadro RM - Sez. II-A, rigo RM31",
            "Imposta sostitutiva 26% sul lordo. Niente Quadro CE - ritenute estere perse.",
        )
        rm_rows = [
            ["RM31", "col.1 - Tipo (dropdown)", "manuale", "es. B (interessi/dividendi esteri)"],
            ["RM31", "col.2 - Codice stato estero", "manuale", "stato della fonte (es. US)"],
            ["RM31", "col.3 - Ammontare reddito (lordo)", _eur(gross), "somma gross_amount_eur"],
            ["RM31", "col.4 - Aliquota", "26", ""],
            [
                "RM31",
                "col.8 - Imposta sostitutiva dovuta",
                _eur(gross * Decimal("0.26")),
                "lordo x 26%",
            ],
        ]
        pdf.data_table(rl_headers, rl_widths, rm_rows, total_row=False)

        # Convenience comparison
        pdf.section_title(
            "Scegli UNA delle due vie - confronto imposta italiana",
            "Le due vie sono MUTUAMENTE ESCLUSIVE per la stessa tipologia (circ. 165/E §6). "
            "Aliquote IRPEF 2025 (senza addizionali regionali/comunali).",
        )
        rm_imposta = gross * Decimal("0.26")
        cmp_headers = ["Scenario", "Imposta italiana EUR", "Calcolo"]
        cmp_widths = [60.0, 38.0, 92.0]
        cmp_rows: list[list[str]] = [
            ["RM31 (sost. 26%)", _eur(rm_imposta), f"{_eur(gross)} x 26%"],
        ]
        for rate, label in [
            (Decimal("0.23"), "RL+CE @23% (fino 28k EUR)"),
            (Decimal("0.35"), "RL+CE @35% (28-50k EUR)"),
            (Decimal("0.43"), "RL+CE @43% (oltre 50k EUR)"),
        ]:
            irpef = gross * rate
            credito = min(wht, irpef)
            netta = irpef - credito
            adv = "  <- piu' conveniente" if netta < rm_imposta else ""
            cmp_rows.append(
                [
                    label,
                    _eur(netta),
                    f"{_eur(gross)} x {int(rate * 100)}% - credito {_eur(credito)}{adv}",
                ]
            )
        pdf.data_table(cmp_headers, cmp_widths, cmp_rows, total_row=False)
        be = (Decimal("0.26") + wht / gross) if gross else Decimal(0)
        pdf.set_font(_FONT, "I", 7.5)
        pdf.set_text_color(*_MED_GRAY)
        pdf.cell(
            0,
            5,
            f"Break-even aliquota marginale: {be * 100:.1f}%. "
            "Sotto -> RL+CE conviene; sopra -> RM31 conviene.",
            new_x="LMARGIN",
            new_y="NEXT",
        )


def _looks_numeric(s: str) -> bool:
    s = s.replace(",", "").replace(" ", "").replace("EUR", "")
    try:
        float(s)
        return True
    except ValueError:
        return False
