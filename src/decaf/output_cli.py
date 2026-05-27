"""Rich terminal output for tax report."""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from decaf.models import TaxReport


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


def _strip_acquired(description: str) -> str:
    idx = description.find(" (acquired ")
    return description[:idx] if idx >= 0 else description


def print_report(report: TaxReport) -> None:
    """Print the full tax report as fancy CLI tables."""
    console = Console()
    console.print()

    # --- Header ---
    header = Text()
    header.append("MODELLO REDDITI PF ", style="bold blue")
    header.append(str(report.tax_year), style="bold white")
    header.append(f"\n{report.account.broker_name}", style="dim")
    header.append(f" | {report.account.account_id}", style="dim")
    console.print(Panel(header, border_style="blue"))

    # --- Summary ---
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("Label", style="bold")
    summary.add_column("Value", justify="right", style="green")

    summary.add_row("IVAFE (Quadro RW)", f"EUR {_eur(report.total_ivafe)}")

    net_rt = report.net_capital_gain_loss
    rt_style = "red" if net_rt < 0 else "green"
    summary.add_row("Plusvalenze (Quadro RT)", Text(f"EUR {_eur(net_rt)}", style=rt_style))

    summary.add_row(
        "Redditi di capitale (Quadro RL)",
        f"EUR {_eur(report.total_gross_interest_eur)}",
    )
    summary.add_row("Ritenute estere (Quadro RL)", f"EUR {_eur(report.total_wht_eur)}")

    breach_text = (
        Text("SUPERATA", style="bold red")
        if report.forex_threshold_breached
        else Text("NON SUPERATA", style="green")
    )
    summary.add_row("Soglia valutaria", breach_text)
    summary.add_row("  Giorni lavorativi consecutivi", f"{report.forex_max_consecutive_days} / 7")

    if report.rsu_vest_count:
        summary.add_row(
            f"Reddito RSU tassato ({report.rsu_vest_count} vest)",
            f"EUR {_eur(report.rsu_income_eur)}",
        )

    console.print(Panel(summary, title="Riepilogo", border_style="green"))

    # --- RSU cross-check hint ---
    if report.rsu_vest_count:
        msg = (
            f"[bold]Controllo coerenza RSU[/bold] — "
            f"[green]EUR {_eur(report.rsu_income_eur)}[/green] su "
            f"[cyan]{report.rsu_vest_count}[/cyan] vest dell'anno, calcolato come "
            "[italic]Valore Normale (ITA FMV x net shares) x cambio BCE "
            "del giorno di vest[/italic].\n"
            "Questo numero deve essere un [bold]sottoinsieme[/bold] del punto 1 "
            'della tua Certificazione Unica "Redditi di lavoro dipendente". '
            "Differenza = stipendio + bonus + altri compensi.\n"
            "Se non combacia, verifica che la colonna [italic]ITA FMV[/italic] "
            "sull'Annual Withholding Statement sia stata letta correttamente "
            '(grep log per "vest FMV").'
        )
        console.print(
            Panel(
                Text.from_markup(msg),
                title="Sanity check - Valore Normale RSU ex art. 9 c. 4 TUIR",
                border_style="yellow",
            )
        )

    # --- Quadro RW ---
    if report.rw_lines:
        rw = Table(
            title="Quadro RW - Investimenti e attivita finanziarie all'estero",
            border_style="blue",
            caption=(
                "Monitoraggio fiscale + IVAFE (D.L. 201/2011). "
                "Cod. 20 = titoli, Cod. 1 = depositi.\n"
                "IVAFE: 0.2% annuo sul valore di mercato, pro-rata per giorni detenuti."
            ),
            caption_style="dim",
        )
        rw.add_column("Symbol", style="cyan")
        rw.add_column("Qty", justify="right")
        rw.add_column("Acquisto", justify="center", style="dim")
        rw.add_column("Vendita", justify="center", style="dim")
        rw.add_column("Giorni", justify="right")
        rw.add_column("Val. fin.", justify="right")
        rw.add_column("USD→EUR", justify="right", style="dim")
        rw.add_column("Val. fin. EUR", justify="right")
        rw.add_column("IVAFE EUR", justify="right", style="green")

        for line in report.rw_lines:
            acq_str = line.acquisition_date.isoformat() if line.acquisition_date else ""
            sold_str = line.disposed_date.isoformat() if line.disposed_date else "31/12"
            ccy = "$" if line.currency == "USD" else "€"

            rw.add_row(
                line.symbol,
                f"{line.quantity:,.0f}",
                acq_str,
                sold_str,
                str(line.days_held),
                f"{ccy}{line.final_value:,.2f}",
                (
                    f"{Decimal(1) / line.ecb_rate_final:.4f}"
                    if line.currency != "EUR" and line.ecb_rate_final
                    else ""
                ),
                _eur(line.final_value_eur),
                _eur(line.ivafe_due),
            )

        # Year-end portfolio value (only held lots)
        held = [
            rw
            for rw in report.rw_lines
            if rw.codice_investimento == 20 and rw.disposed_date is None
        ]
        eoy_eur = sum((rw.final_value_eur for rw in held), Decimal(0))
        eoy_shares = sum((rw.quantity for rw in held), Decimal(0))

        rw.add_section()
        rw.add_row(
            "",
            "",
            "",
            "31/12",
            f"{eoy_shares:,.0f}",
            "",
            "",
            Text(_eur(eoy_eur), style="bold"),
            Text(_eur(report.total_ivafe), style="bold green"),
        )
        console.print(rw)
        console.print()

    # --- Quadro RT ---
    rt_title = "Quadro RT - Plusvalenze di natura finanziaria"
    if report.rt_lines:
        rt = Table(
            title=rt_title,
            border_style="blue",
            caption=(
                "Sez. II-A, righi RT21+. Imposta sostitutiva 26% "
                "(art. 67(1)(c-bis) TUIR).\n"
                "Costo e corrispettivo convertiti in EUR al cambio BCE "
                "alla data di regolamento."
            ),
            caption_style="dim",
        )
        rt.add_column("Symbol", style="cyan")
        rt.add_column("ISIN", style="dim")
        rt.add_column("Acquisto", justify="center", style="dim")
        rt.add_column("Vendita", justify="center")
        rt.add_column("Qty", justify="right")
        rt.add_column("Costo base EUR", justify="right")
        rt.add_column("Costo/sh", justify="right", style="dim")
        rt.add_column("Corrisp. EUR", justify="right")
        rt.add_column("P/L EUR", justify="right")
        rt.add_column("Cambio", justify="right", style="dim")
        rt.add_column("Broker cost", justify="right", style="dim")
        rt.add_column("Broker P/L", justify="right", style="dim")

        for line in report.rt_lines:
            gl_style = "red" if line.gain_loss_eur < 0 else "green"
            rt.add_row(
                line.symbol,
                line.isin,
                line.acquisition_date.isoformat(),
                line.sell_date.isoformat(),
                f"{line.quantity:,.0f}",
                _eur(line.cost_basis_eur),
                _per_share(line.normal_value_cost, line.quantity, line.currency),
                _eur(line.proceeds_eur),
                Text(_eur(line.gain_loss_eur), style=gl_style),
                f"{line.ecb_rate:.4f}" if line.ecb_rate != 1 else "",
                _money(line.broker_cost_basis, line.currency)
                if line.broker_cost_basis and not line.is_forex
                else "",
                _money(line.broker_pnl, line.currency)
                if line.broker_pnl and not line.is_forex
                else "",
            )

        total_proceeds = sum((rt.proceeds_eur for rt in report.rt_lines), Decimal(0))
        total_cost = sum((rt.cost_basis_eur for rt in report.rt_lines), Decimal(0))
        broker_cost_by_ccy: dict[str, Decimal] = {}
        broker_pnl_by_ccy: dict[str, Decimal] = {}
        for line in report.rt_lines:
            if line.is_forex:
                continue
            if line.broker_cost_basis:
                broker_cost_by_ccy[line.currency] = (
                    broker_cost_by_ccy.get(line.currency, Decimal(0)) + line.broker_cost_basis
                )
            if line.broker_pnl:
                broker_pnl_by_ccy[line.currency] = (
                    broker_pnl_by_ccy.get(line.currency, Decimal(0)) + line.broker_pnl
                )
        broker_cost_str = " / ".join(_money(v, c) for c, v in sorted(broker_cost_by_ccy.items()))
        broker_pnl_str = " / ".join(_money(v, c) for c, v in sorted(broker_pnl_by_ccy.items()))
        rt.add_section()
        net_style = "red" if net_rt < 0 else "green"
        rt.add_row(
            "",
            "",
            "",
            "TOTALI",
            "",
            Text(_eur(total_cost), style="bold"),
            "",
            Text(_eur(total_proceeds), style="bold"),
            Text(_eur(net_rt), style=f"bold {net_style}"),
            "",
            Text(broker_cost_str, style="dim"),
            Text(broker_pnl_str, style="dim"),
        )
        console.print(rt)
        console.print()
    else:
        console.print(f"[dim]{rt_title}: nessuna plusvalenza/minusvalenza realizzata[/dim]\n")

    # --- Quadro RL ---
    rl_title = "Quadro RL - Altri redditi (Sez. I - Redditi di capitale)"
    if report.rl_lines:
        rl = Table(
            title=rl_title,
            border_style="blue",
            caption=(
                "Redditi di capitale di fonte estera (art. 44 TUIR), "
                "rigo RL2.\n"
                "Interessi e dividendi da intermediario estero "
                "(non sostituto d'imposta italiano). "
                "Ritenute estere detraibili."
            ),
            caption_style="dim",
        )
        rl.add_column("Descrizione")
        rl.add_column("Valuta", justify="center")
        rl.add_column("Lordo", justify="right")
        rl.add_column("Lordo EUR", justify="right")
        rl.add_column("Ritenuta", justify="right", style="red")
        rl.add_column("Rit. EUR", justify="right", style="red")
        rl.add_column("Netto EUR", justify="right", style="green")

        for line in report.rl_lines:
            rl.add_row(
                line.description[:50],
                line.currency,
                _eur(line.gross_amount),
                _eur(line.gross_amount_eur),
                _eur(line.wht_amount),
                _eur(line.wht_amount_eur),
                _eur(line.net_amount_eur),
            )

        total_net = report.total_gross_interest_eur - report.total_wht_eur
        rl.add_section()
        rl.add_row(
            "",
            "TOTALI",
            "",
            Text(_eur(report.total_gross_interest_eur), style="bold"),
            "",
            Text(_eur(report.total_wht_eur), style="bold red"),
            Text(_eur(total_net), style="bold green"),
        )
        console.print(rl)
        console.print()
    else:
        console.print(f"[dim]{rl_title}: nessun reddito di capitale[/dim]\n")

    # --- Per la dichiarazione precompilata (RPF26) ---
    _print_precompilata(console, report)

    # --- Forex threshold ---
    fx_label = "Soglia valutaria (art. 67(1)(c-ter) TUIR)"
    if report.forex_threshold_breached:
        console.print(
            Panel(
                "[bold red]SOGLIA SUPERATA[/bold red]\n"
                f"Giacenza in valuta estera > EUR 51.645,69 per "
                f"{report.forex_max_consecutive_days} giorni lavorativi consecutivi "
                f"(soglia: 7).\n"
                "Le plusvalenze da cessione di valuta estera sono tassabili al 26%.",
                title=fx_label,
                border_style="red",
            )
        )
    else:
        console.print(
            Panel(
                "[green]Soglia non superata[/green]\n"
                f"Max {report.forex_max_consecutive_days} giorni lavorativi "
                f"consecutivi sopra soglia (servono 7).\n"
                "Le plusvalenze da conversione valutaria sono esenti.",
                title=fx_label,
                border_style="green",
            )
        )

    # --- Forex daily detail ---
    if report.forex_daily_records:
        _print_forex_detail(console, report)

    console.print()


def _print_precompilata(console: Console, report: TaxReport) -> None:
    """Print the 'Per la dichiarazione precompilata RPF26' guidance block.

    Maps decaf aggregates to the exact rigo/colonna of the current AdE
    precompilata form so the user can copy values directly.
    """
    sections: list[tuple[str, Table]] = []

    # Quadro RW — one row per lot
    if report.rw_lines:
        rw = Table(
            border_style="cyan",
            caption=(
                "Quadro RW - un modulo per ogni riga sotto. Colonne fisse: "
                "col.1=1 (proprietà), col.5=100%, col.6=1 (valore di mercato)."
            ),
            caption_style="dim",
        )
        rw.add_column("Modulo", justify="center", style="bold")
        rw.add_column("col.3\nCod. bene", justify="center")
        rw.add_column("col.4\nStato", justify="center")
        rw.add_column("col.7\nVal. iniziale", justify="right")
        rw.add_column("col.8\nVal. finale", justify="right")
        rw.add_column("col.10\nGiorni", justify="right")
        rw.add_column("col.30\nIVAFE dovuta", justify="right", style="green")
        rw.add_column("Descrizione", style="dim")

        for idx, line in enumerate(report.rw_lines, start=1):
            rw.add_row(
                f"RW{idx}",
                str(line.codice_investimento),
                line.country,
                _eur(line.initial_value_eur),
                _eur(line.final_value_eur),
                str(line.days_held),
                _eur(line.ivafe_due),
                f"{line.symbol} {line.long_description[:25]}",
            )
        sections.append(("Quadro RW — Monitoraggio + IVAFE", rw))

    # Quadro RT — Sez. II-A, unico rigo RT11
    if report.rt_lines:
        rt = Table(border_style="cyan")
        rt.add_column("Rigo", style="bold")
        rt.add_column("Colonna")
        rt.add_column("Valore EUR", justify="right", style="green")
        rt.add_column("Origine", style="dim")
        rt.add_row(
            "RT11",
            "col.1 — Totale corrispettivi",
            _eur(report.rt_total_proceeds_eur),
            f"somma proceeds_eur di {len(report.rt_lines)} righe",
        )
        rt.add_row(
            "RT11",
            "col.2 — Totale costi",
            _eur(report.rt_total_cost_basis_eur),
            f"somma cost_basis_eur di {len(report.rt_lines)} righe",
        )
        net = report.net_capital_gain_loss
        net_style = "red" if net < 0 else "green"
        rt.add_section()
        rt.add_row(
            "",
            "Differenza (calcolata dall'AdE)",
            Text(_eur(net), style=net_style),
            "plus o minus netta",
        )
        if net > 0:
            rt.add_row(
                "",
                "Imposta sostitutiva 26%",
                Text(_eur(net * Decimal("0.26")), style="green"),
                "calcolata in automatico dal software AdE",
            )
        rt.caption = (
            "Sez. II-A 26% (partecipazioni non qualificate). Le minus pregresse "
            "vanno in RT13 (decaf non le conosce). Eventuali eccedenze "
            "minus certificate dall'intermediario: RT14."
        )
        rt.caption_style = "dim"
        sections.append(("Quadro RT — Sez. II-A (26%)", rt))

    # Quadro RL + Quadro RM (mutually exclusive — show comparison)
    if report.rl_lines:
        gross = report.total_gross_interest_eur
        wht = report.total_wht_eur

        rl = Table(border_style="cyan")
        rl.add_column("Rigo", style="bold")
        rl.add_column("Colonna")
        rl.add_column("Valore EUR", justify="right", style="green")
        rl.add_column("Origine", style="dim")
        rl.add_row(
            "RL2",
            "col.1 — Tipo reddito (dropdown)",
            "manuale",
            "es. B (dividendi non qualif.), A (interessi)",
        )
        rl.add_row("RL2", "col.2 — Redditi (lordo)", _eur(gross), "somma gross_amount_eur")
        rl.add_row(
            "RL2",
            "col.3 — Ritenute",
            _eur(wht),
            "somma wht_amount_eur (credito art. 165 → Quadro CE)",
        )
        rl.caption = "Quadro RL Sez. I-A + Quadro CE (credito imposta estera)."
        rl.caption_style = "dim"
        sections.append(("Alternativa A: Quadro RL — IRPEF marginale + credito CE", rl))

        rm = Table(border_style="cyan")
        rm.add_column("Rigo", style="bold")
        rm.add_column("Colonna")
        rm.add_column("Valore EUR", justify="right", style="green")
        rm.add_column("Origine", style="dim")
        rm.add_row(
            "RM31", "col.1 — Tipo (dropdown)", "manuale", "es. B (interessi/dividendi esteri)"
        )
        rm.add_row(
            "RM31",
            "col.2 — Codice stato estero",
            "manuale",
            "stato della fonte (es. US per dividendi USA)",
        )
        rm.add_row(
            "RM31",
            "col.3 — Ammontare reddito (lordo)",
            _eur(gross),
            "somma gross_amount_eur",
        )
        rm.add_row("RM31", "col.4 — Aliquota", "26", "")
        rm.add_row(
            "RM31",
            "col.8 — Imposta sostitutiva dovuta",
            _eur(gross * Decimal("0.26")),
            "lordo x 26% (le ritenute estere sono perse)",
        )
        rm.caption = "Quadro RM Sez. II-A. Niente Quadro CE — credito estero non recuperabile."
        rm.caption_style = "dim"
        sections.append(("Alternativa B: Quadro RM — imposta sostitutiva 26%", rm))

        # Comparison table
        cmp = Table(border_style="yellow")
        cmp.add_column("Scenario", style="bold")
        cmp.add_column("Imposta italiana", justify="right")
        cmp.add_column("Calcolo", style="dim")
        rm_imposta = gross * Decimal("0.26")
        cmp.add_row(
            "RM31 (sost. 26%)",
            Text(_eur(rm_imposta), style="bold"),
            f"{_eur(gross)} x 26%",
        )
        cmp.add_section()
        for rate_pct, label in [
            (Decimal("0.23"), "RL+CE @23% (reddito fino 28k€)"),
            (Decimal("0.35"), "RL+CE @35% (reddito 28-50k€)"),
            (Decimal("0.43"), "RL+CE @43% (reddito oltre 50k€)"),
        ]:
            irpef = gross * rate_pct
            credito = min(wht, irpef)  # credito cap = IRPEF italiana sul reddito estero
            netta = irpef - credito
            advantage = ""
            if netta < rm_imposta:
                advantage = "← più conveniente"
            cmp.add_row(
                label,
                Text(_eur(netta), style="green" if netta < rm_imposta else ""),
                f"{_eur(gross)} x {int(rate_pct * 100)}% - credito {_eur(credito)} {advantage}",
            )
        break_even = (Decimal("0.26") + wht / gross) if gross else Decimal(0)
        cmp.caption = (
            f"Break-even aliquota marginale: {break_even * 100:.1f}%. "
            "Sotto → RL+CE conviene; sopra → RM31 conviene. "
            "Le aliquote NON includono addizionali regionali/comunali (~1-2.5%)."
        )
        cmp.caption_style = "dim"
        sections.append(("⚠ Scegli UNA delle due vie — confronto imposta italiana", cmp))

    if not sections:
        return

    console.print()
    title = f"Per la dichiarazione precompilata (anno fiscale {report.tax_year})"
    console.print(Panel(Text(title, style="bold blue"), border_style="blue"))
    for sec_title, table in sections:
        table.title = sec_title
        console.print(table)
        console.print()


def _print_forex_detail(console: Console, report: TaxReport) -> None:
    """Print USD event timeline showing every balance change."""
    events = report.forex_usd_events
    records = report.forex_daily_records
    if not events and not records:
        return

    # Get Jan 1 rate from the first daily record
    jan1_rate = records[0].fx_rate if records else Decimal(0)

    # USD event timeline
    border = "red" if report.forex_threshold_breached else "green"
    from decaf.forex import THRESHOLD_EUR

    threshold_eur = THRESHOLD_EUR

    tl = Table(
        title="Timeline saldo USD — tutti i movimenti",
        border_style=border,
        caption_style="dim",
    )
    tl.add_column("Data", justify="center")
    tl.add_column("Movimento", justify="right")
    tl.add_column("Saldo EOD", justify="right")
    tl.add_column("EUR equiv.", justify="right")
    tl.add_column("Soglia", justify="center")
    tl.add_column("Descrizione")

    # Show every event, but only show balance on the last event of each day
    prev_date = None
    for i, ev in enumerate(events):
        is_last_of_day = i + 1 >= len(events) or events[i + 1].date != ev.date
        eod_balance = ev.balance if is_last_of_day else None

        amt_str = f"{ev.amount:+,.2f}" if ev.amount != 0 else ""

        if eod_balance is not None:
            eur_equiv = eod_balance / jan1_rate if jan1_rate else Decimal(0)
            above = eur_equiv > threshold_eur and eod_balance > 0
            above_text = Text("SI", style="bold red") if above else Text("", style="dim")
            bal_str = f"{eod_balance:,.2f}"
            eur_str = f"{eur_equiv:,.2f}"
        else:
            above_text = Text("", style="dim")
            bal_str = ""
            eur_str = ""

        tl.add_row(
            ev.date.isoformat() if ev.date != prev_date else "",
            amt_str,
            bal_str,
            eur_str,
            above_text,
            ev.description,
        )
        prev_date = ev.date

    # Caption with summary
    caption = f"Tasso BCE fisso 1 gennaio: {jan1_rate:.4f} (art. 67(1)(c-ter) TUIR)."
    if report.forex_threshold_breached:
        caption += (
            f"\nSoglia SUPERATA: {report.forex_max_consecutive_days} giorni "
            f"lavorativi consecutivi (dal {report.forex_first_breach_date})."
        )
    else:
        caption += (
            f"\nSoglia non superata: max {report.forex_max_consecutive_days} "
            f"giorni lavorativi consecutivi (servono 7)."
        )

    # Warn only about materially negative balance (> $100 = likely missing data)
    min_balance = min((ev.balance for ev in events), default=Decimal(0))
    if min_balance < Decimal("-100"):
        caption += (
            f"\n[yellow]Attenzione: saldo minimo USD {min_balance:,.2f}"
            " — possibili dati mancanti da anni precedenti.[/yellow]"
        )

    tl.caption = caption
    console.print(tl)
