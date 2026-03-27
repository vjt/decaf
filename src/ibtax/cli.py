"""CLI entry point for ibtax."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="ibtax",
        description="Italian tax report generator for Interactive Brokers accounts",
    )
    parser.add_argument(
        "--year", type=int, required=True,
        help="Tax year to report on (e.g., 2025)",
    )
    parser.add_argument(
        "--file", type=Path, default=None,
        help="Path to a local FlexQuery XML file (skip IBKR fetch)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("."),
        help="Directory for output files (default: current dir)",
    )
    parser.add_argument(
        "--ecb-db", type=Path,
        default=Path.home() / ".cache" / "ibtax" / "ecb_rates.db",
        help="Path to ECB rates SQLite cache",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print detailed forex daily balance to terminal",
    )
    parser.add_argument(
        "--token", default=None,
        help="IBKR Flex token (default: IBKR_TOKEN env var)",
    )
    parser.add_argument(
        "--query-id", default=None,
        help="IBKR Flex Query ID (default: IBKR_QUERY_ID env var)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    import aiohttp

    from ibtax.ecb_cache import EcbRateCache
    from ibtax.forex import analyze_forex_threshold
    from ibtax.fx import FxService
    from ibtax.models import TaxReport
    from ibtax.output_json import write_json
    from ibtax.output_pdf import write_pdf
    from ibtax.output_xls import write_xls
    from ibtax.parse import parse_statement
    from ibtax.quadro_rl import compute_rl
    from ibtax.quadro_rt import compute_rt
    from ibtax.quadro_rw import compute_rw

    tax_year = args.year

    # --- Step 1: Get the FlexQuery XML ---
    if args.file:
        print(f"Loading FlexQuery XML from {args.file}")
        xml_text = args.file.read_text()
    else:
        xml_text = await _fetch_from_ibkr(args)

    # --- Step 2: Parse ---
    print(f"Parsing statement for tax year {tax_year}...")
    data = parse_statement(xml_text, tax_year)
    print(
        f"  Account: {data.account.account_id} ({data.account.base_currency})"
        f"  Period: {data.statement_from} to {data.statement_to}"
    )
    print(
        f"  Trades: {len(data.trades)}  "
        f"Positions: {len(data.positions)} lots  "
        f"Cash txns: {len(data.cash_transactions)}  "
        f"FX rates: {len(data.conversion_rates)}"
    )

    # --- Step 3: ECB rates ---
    print("Fetching ECB rates...")
    async with EcbRateCache(args.ecb_db) as ecb_cache:
        async with aiohttp.ClientSession() as session:
            count = await ecb_cache.ensure_year(session, tax_year)
        print(f"  ECB rates: {count} days cached for {tax_year}")

        ecb_rates = await ecb_cache.get_all_rates_for_year("USD", tax_year)

    # --- Step 4: Build FX service ---
    fx = FxService(data.conversion_rates, ecb_rates)

    # --- Step 5: Computations ---
    print("Computing tax report...")

    # Forex threshold (must run first)
    forex = analyze_forex_threshold(data.trades, data.cash_transactions, fx, tax_year)
    print(
        f"  Forex threshold: {'BREACHED' if forex.threshold_breached else 'NOT breached'}"
        f" (max {forex.max_consecutive_business_days} consecutive business days)"
    )

    # Quadro RW
    rw_lines = compute_rw(data.positions, data.trades, data.cash_report, fx, tax_year)
    total_ivafe = sum(l.ivafe_due for l in rw_lines)
    print(f"  Quadro RW: {len(rw_lines)} lines, IVAFE: \u20ac{total_ivafe:.2f}")

    # Quadro RT
    rt_lines = compute_rt(data.trades, fx, tax_year, forex.threshold_breached)
    net_rt = sum(l.gain_loss_eur for l in rt_lines)
    print(f"  Quadro RT: {len(rt_lines)} lines, net: \u20ac{net_rt:.2f}")

    # Quadro RL
    rl_lines = compute_rl(data.cash_transactions, fx, tax_year)
    total_interest = sum(l.gross_amount_eur for l in rl_lines)
    total_wht = sum(l.wht_amount_eur for l in rl_lines)
    print(f"  Quadro RL: {len(rl_lines)} lines, gross: \u20ac{total_interest:.2f}, WHT: \u20ac{total_wht:.2f}")

    # --- Step 6: Assemble report ---
    report = TaxReport(
        tax_year=tax_year,
        account=data.account,
        rw_lines=rw_lines,
        rt_lines=rt_lines,
        rl_lines=rl_lines,
        forex_threshold_breached=forex.threshold_breached,
        forex_max_consecutive_days=forex.max_consecutive_business_days,
        forex_first_breach_date=forex.first_breach_date,
        forex_daily_records=forex.daily_records,
    )

    # --- Step 7: Verbose forex output ---
    if args.verbose:
        print("\n=== Daily USD Balance (non-zero days) ===")
        for rec in forex.daily_records:
            if rec.usd_balance != 0:
                biz = "BIZ" if rec.is_business_day else "   "
                above = " >THRESHOLD" if rec.above_threshold else ""
                print(
                    f"  {rec.date} {biz} USD={rec.usd_balance:>12.2f} "
                    f"EUR={rec.eur_equivalent:>12.2f} rate={rec.fx_rate:.6f}{above}"
                )

    # --- Step 8: Output ---
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"ibtax_{data.account.account_id}_{tax_year}"

    json_path = output_dir / f"{prefix}.json"
    write_json(report, json_path)
    print(f"\nJSON:  {json_path}")

    xls_path = output_dir / f"{prefix}.xlsx"
    write_xls(report, xls_path)
    print(f"Excel: {xls_path}")

    pdf_path = output_dir / f"{prefix}.pdf"
    write_pdf(report, pdf_path)
    print(f"PDF:   {pdf_path}")

    print("\nDone.")


async def _fetch_from_ibkr(args: argparse.Namespace) -> str:
    """Fetch FlexQuery XML from IBKR API."""
    import aiohttp

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ibkr-flex-client" / "src"))
    from ibkr_flex_client import FlexClient

    token = args.token or os.environ.get("IBKR_TOKEN")
    query_id = args.query_id or os.environ.get("IBKR_QUERY_ID")

    if not token:
        token = getpass.getpass("IBKR Flex Token: ")
    if not query_id:
        query_id = input("IBKR Flex Query ID: ")

    print(f"Fetching FlexQuery {query_id} from IBKR...")
    client = FlexClient(token=token, query_id=query_id)

    async with aiohttp.ClientSession() as session:
        statement = await client.fetch(session)

    print(f"  Received {len(statement.xml)} bytes, {statement.from_date} to {statement.to_date}")
    return statement.xml
