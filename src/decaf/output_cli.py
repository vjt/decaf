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
    header.append("DICHIARAZIONE DEI REDDITI ", style="bold blue")
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
    summary.add_row("Capital Gains (Quadro RT)",
                     Text(f"EUR {_EUR(net_rt)}", style=rt_style))

    summary.add_row("Gross Interest (Quadro RL)", f"EUR {_EUR(report.total_gross_interest_eur)}")
    summary.add_row("Foreign WHT (Quadro RL)", f"EUR {_EUR(report.total_wht_eur)}")

    breach_text = Text("BREACHED", style="bold red") if report.forex_threshold_breached \
        else Text("NOT BREACHED", style="green")
    summary.add_row("Forex Threshold", breach_text)
    summary.add_row("  Max Consecutive Days",
                     f"{report.forex_max_consecutive_days} / 7")

    console.print(Panel(summary, title="Tax Summary", border_style="green"))

    # --- Quadro RW ---
    if report.rw_lines:
        rw = Table(title="Quadro RW - Foreign Assets + IVAFE", border_style="blue")
        rw.add_column("Cod", justify="center", style="dim")
        rw.add_column("Symbol", style="cyan")
        rw.add_column("ISIN", style="dim")
        rw.add_column("Country", justify="center")
        rw.add_column("Initial EUR", justify="right")
        rw.add_column("Final EUR", justify="right")
        rw.add_column("Days", justify="right")
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
        rw.add_row("", "", "", "", "", "", "TOTAL",
                    Text(_EUR(report.total_ivafe), style="bold green"))
        console.print(rw)
        console.print()

    # --- Quadro RT ---
    if report.rt_lines:
        rt = Table(title="Quadro RT - Capital Gains/Losses", border_style="blue")
        rt.add_column("Symbol", style="cyan")
        rt.add_column("ISIN", style="dim")
        rt.add_column("Sell Date", justify="center")
        rt.add_column("Qty", justify="right")
        rt.add_column("Proceeds EUR", justify="right")
        rt.add_column("Cost EUR", justify="right")
        rt.add_column("Gain/Loss EUR", justify="right")
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
                "Yes" if line.is_forex else "",
            )

        rt.add_section()
        net_style = "red" if net_rt < 0 else "green"
        rt.add_row("", "", "", "", "", "NET",
                    Text(_EUR(net_rt), style=f"bold {net_style}"), "")
        console.print(rt)
        console.print()
    else:
        console.print("[dim]Quadro RT: No realized gains or losses[/dim]\n")

    # --- Quadro RL ---
    if report.rl_lines:
        rl = Table(title="Quadro RL - Investment Income", border_style="blue")
        rl.add_column("Description")
        rl.add_column("Currency", justify="center")
        rl.add_column("Gross", justify="right")
        rl.add_column("Gross EUR", justify="right")
        rl.add_column("WHT", justify="right", style="red")
        rl.add_column("WHT EUR", justify="right", style="red")
        rl.add_column("Net EUR", justify="right", style="green")

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
        rl.add_row("", "TOTALS", "",
                    Text(_EUR(report.total_gross_interest_eur), style="bold"),
                    "",
                    Text(_EUR(report.total_wht_eur), style="bold red"),
                    Text(_EUR(total_net), style="bold green"))
        console.print(rl)
        console.print()
    else:
        console.print("[dim]Quadro RL: No investment income[/dim]\n")
