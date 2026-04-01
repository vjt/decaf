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
                "IVAFE: 0.2% sul valore di mercato (titoli), EUR 34.20 fisso (depositi)."
            ),
            caption_style="dim",
        )
        rw.add_column("Cod", justify="center", style="dim")
        rw.add_column("Symbol", style="cyan")
        rw.add_column("ISIN", style="dim")
        rw.add_column("Stato", justify="center")
        rw.add_column("Val. iniziale", justify="right")
        rw.add_column("Val. finale", justify="right")
        rw.add_column("Giorni", justify="right")
        rw.add_column("IVAFE", justify="right", style="green")

        for line in report.rw_lines:
            rw.add_row(
                str(line.codice_investimento),
                line.symbol,
                line.isin,
                line.country,
                _EUR(line.initial_value_eur),
                _EUR(line.final_value_eur),
                str(line.days_held),
                _EUR(line.ivafe_due),
            )

        rw.add_section()
        rw.add_row("", "", "", "", "", "", "TOTALE",
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
        rt.add_column("Data vendita", justify="center")
        rt.add_column("Qty", justify="right")
        rt.add_column("Corrispettivo", justify="right")
        rt.add_column("Costo", justify="right")
        rt.add_column("Plus/Minus", justify="right")
        rt.add_column("Forex", justify="center")

        for line in report.rt_lines:
            gl_style = "red" if line.gain_loss_eur < 0 else "green"
            rt.add_row(
                line.symbol,
                line.isin,
                line.sell_date.isoformat(),
                f"{line.quantity:,.0f}",
                _EUR(line.proceeds_eur),
                _EUR(line.cost_basis_eur),
                Text(_EUR(line.gain_loss_eur), style=gl_style),
                "Si" if line.is_forex else "",
            )

        rt.add_section()
        net_style = "red" if net_rt < 0 else "green"
        rt.add_row("", "", "", "", "", "NETTO",
                    Text(_EUR(net_rt), style=f"bold {net_style}"), "")
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
        rl.add_column("Ritenuta EUR", justify="right", style="red")
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
    """Print forex daily balance — only days where the balance changes."""
    from datetime import timedelta

    records = report.forex_daily_records
    if not records:
        return

    breach_start = report.forex_first_breach_date

    if breach_start is None:
        days_above = [r for r in records if r.above_threshold and r.is_business_day]
        if days_above:
            console.print(
                f"  [dim]{len(days_above)} giorni lavorativi sopra soglia "
                f"(max {report.forex_max_consecutive_days} consecutivi)[/dim]",
            )
        return

    # Build compact table: Jan 1 + every day the balance changes + Dec 31
    shown: list[tuple] = []  # (record, note)
    prev_balance = None
    jan1 = records[0]
    dec31 = records[-1]

    for rec in records:
        if rec.date == jan1.date:
            note = "riporto" if rec.usd_balance != 0 else ""
            shown.append((rec, note))
            prev_balance = rec.usd_balance
        elif rec.date == dec31.date:
            shown.append((rec, ""))
        elif rec.usd_balance != prev_balance:
            shown.append((rec, ""))
            prev_balance = rec.usd_balance

    # Find breach end
    breach_end = breach_start
    in_run = False
    biz_count = 0
    for rec in records:
        if not rec.is_business_day:
            continue
        if rec.above_threshold:
            if not in_run:
                in_run = True
                run_start = rec.date
                biz_count = 1
            else:
                biz_count += 1
            if biz_count >= report.forex_max_consecutive_days and run_start == breach_start:
                breach_end = rec.date
        else:
            in_run = False
            biz_count = 0

    fx_table = Table(
        title="Dettaglio soglia valutaria — variazioni saldo USD",
        border_style="red",
        caption=(
            f"Tasso BCE fisso 1 gennaio: {jan1.fx_rate:.4f} "
            f"(art. 67(1)(c-ter) TUIR).\n"
            f"Periodo di superamento: {breach_start.isoformat()} — "
            f"{breach_end.isoformat()} "
            f"({report.forex_max_consecutive_days} giorni lavorativi)."
        ),
        caption_style="dim",
    )
    fx_table.add_column("Data", justify="center")
    fx_table.add_column("Saldo USD", justify="right")
    fx_table.add_column("EUR equiv.", justify="right")
    fx_table.add_column("Soglia", justify="center")
    fx_table.add_column("Note", style="dim")

    for rec, note in shown:
        above_text = Text("SI", style="bold red") if rec.above_threshold \
            else Text("no", style="dim")

        fx_table.add_row(
            rec.date.isoformat(),
            f"{rec.usd_balance:,.2f}",
            f"{rec.eur_equivalent:,.2f}",
            above_text,
            note,
        )

    console.print(fx_table)
