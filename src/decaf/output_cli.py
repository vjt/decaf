"""Rich terminal output for tax report."""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from decaf.models import TaxReport

_EUR = lambda v: f"{v:,.2f}"


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

    summary.add_row("IVAFE (Quadro RW)", f"EUR {_EUR(report.total_ivafe)}")

    net_rt = report.net_capital_gain_loss
    rt_style = "red" if net_rt < 0 else "green"
    summary.add_row("Plusvalenze (Quadro RT)",
                     Text(f"EUR {_EUR(net_rt)}", style=rt_style))

    summary.add_row("Redditi di capitale (Quadro RL)", f"EUR {_EUR(report.total_gross_interest_eur)}")
    summary.add_row("Ritenute estere (Quadro RL)", f"EUR {_EUR(report.total_wht_eur)}")

    breach_text = Text("SUPERATA", style="bold red") if report.forex_threshold_breached \
        else Text("NON SUPERATA", style="green")
    summary.add_row("Soglia valutaria", breach_text)
    summary.add_row("  Giorni lavorativi consecutivi",
                     f"{report.forex_max_consecutive_days} / 7")

    console.print(Panel(summary, title="Riepilogo", border_style="green"))

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
        rw.add_column("Cod", justify="center", style="dim")
        rw.add_column("Symbol", style="cyan")
        rw.add_column("ISIN", style="dim")
        rw.add_column("Stato", justify="center")
        rw.add_column("Acquisto", justify="center", style="dim")
        rw.add_column("Val. iniz. EUR", justify="right")
        rw.add_column("Val. fin. EUR", justify="right")
        rw.add_column("Giorni", justify="right")
        rw.add_column("IVAFE EUR", justify="right", style="green")

        for line in report.rw_lines:
            # Extract acquisition date from description "SYMBOL (YYYY-MM-DD)"
            import re
            acq_match = re.search(r"\d{4}-\d{2}-\d{2}", line.description)
            acq_str = acq_match.group(0) if acq_match else ""

            rw.add_row(
                str(line.codice_investimento),
                line.symbol,
                line.isin,
                line.country,
                acq_str,
                _EUR(line.initial_value_eur),
                _EUR(line.final_value_eur),
                str(line.days_held),
                _EUR(line.ivafe_due),
            )

        total_initial = sum(l.initial_value_eur for l in report.rw_lines)
        total_final = sum(l.final_value_eur for l in report.rw_lines)
        rw.add_section()
        rw.add_row("", "", "", "", "TOTALI",
                    Text(_EUR(total_initial), style="bold"),
                    Text(_EUR(total_final), style="bold"),
                    "",
                    Text(_EUR(report.total_ivafe), style="bold green"))
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
        rt.add_column("Corrisp. EUR", justify="right")
        rt.add_column("Costo EUR", justify="right")
        rt.add_column("+/- EUR", justify="right")
        rt.add_column("Cambio", justify="right", style="dim")
        rt.add_column("Fx", justify="center")

        for line in report.rt_lines:
            gl_style = "red" if line.gain_loss_eur < 0 else "green"
            rt.add_row(
                line.symbol,
                line.isin,
                line.acquisition_date.isoformat(),
                line.sell_date.isoformat(),
                f"{line.quantity:,.0f}",
                _EUR(line.proceeds_eur),
                _EUR(line.cost_basis_eur),
                Text(_EUR(line.gain_loss_eur), style=gl_style),
                f"{line.ecb_rate:.4f}" if line.ecb_rate != 1 else "",
                "Si" if line.is_forex else "",
            )

        total_proceeds = sum(l.proceeds_eur for l in report.rt_lines)
        total_cost = sum(l.cost_basis_eur for l in report.rt_lines)
        rt.add_section()
        net_style = "red" if net_rt < 0 else "green"
        rt.add_row("", "", "", "", "TOTALI",
                    Text(_EUR(total_proceeds), style="bold"),
                    Text(_EUR(total_cost), style="bold"),
                    Text(_EUR(net_rt), style=f"bold {net_style}"), "", "")
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
                _EUR(line.gross_amount),
                _EUR(line.gross_amount_eur),
                _EUR(line.wht_amount),
                _EUR(line.wht_amount_eur),
                _EUR(line.net_amount_eur),
            )

        total_net = report.total_gross_interest_eur - report.total_wht_eur
        rl.add_section()
        rl.add_row("", "TOTALI", "",
                    Text(_EUR(report.total_gross_interest_eur), style="bold"),
                    "",
                    Text(_EUR(report.total_wht_eur), style="bold red"),
                    Text(_EUR(total_net), style="bold green"))
        console.print(rl)
        console.print()
    else:
        console.print(f"[dim]{rl_title}: nessun reddito di capitale[/dim]\n")

    # --- Forex threshold ---
    fx_label = "Soglia valutaria (art. 67(1)(c-ter) TUIR)"
    if report.forex_threshold_breached:
        console.print(Panel(
            "[bold red]SOGLIA SUPERATA[/bold red]\n"
            f"Giacenza in valuta estera > EUR 51.645,69 per "
            f"{report.forex_max_consecutive_days} giorni lavorativi consecutivi "
            f"(soglia: 7).\n"
            "Le plusvalenze da cessione di valuta estera sono tassabili al 26%.",
            title=fx_label,
            border_style="red",
        ))
    else:
        console.print(Panel(
            "[green]Soglia non superata[/green]\n"
            f"Max {report.forex_max_consecutive_days} giorni lavorativi "
            f"consecutivi sopra soglia (servono 7).\n"
            "Le plusvalenze da conversione valutaria sono esenti.",
            title=fx_label,
            border_style="green",
        ))

    # --- Forex daily detail ---
    if report.forex_daily_records:
        _print_forex_detail(console, report)

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
    threshold_eur = Decimal("51645.69")

    tl = Table(
        title="Timeline saldo USD — tutti i movimenti",
        border_style=border,
        caption_style="dim",
    )
    tl.add_column("Data", justify="center")
    tl.add_column("Movimento", justify="right")
    tl.add_column("Saldo USD", justify="right")
    tl.add_column("EUR equiv.", justify="right")
    tl.add_column("Soglia", justify="center")
    tl.add_column("Descrizione")

    for ev in events:
        eur_equiv = ev.balance / jan1_rate if jan1_rate else Decimal(0)
        above = eur_equiv > threshold_eur and ev.balance > 0
        above_text = Text("SI", style="bold red") if above else Text("", style="dim")

        amt_str = f"{ev.amount:+,.2f}" if ev.amount != 0 else ""
        bal_style = "red" if ev.balance < 0 else ""

        tl.add_row(
            ev.date.isoformat(),
            amt_str,
            Text(f"{ev.balance:,.2f}", style=bal_style),
            f"{eur_equiv:,.2f}",
            above_text,
            ev.description[:55],
        )

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

    # Warn about negative balance
    if any(ev.balance < 0 for ev in events):
        caption += (
            "\n[yellow]Attenzione: saldo negativo — dati mancanti da anni precedenti "
            "(sell-to-cover da vest RSU o transazioni pre-2023?).[/yellow]"
        )

    tl.caption = caption
    console.print(tl)
