"""CLI entry point for decaf.

Two subcommands:
    decaf fetch              Fetch from IBKR and store in local SQLite
    decaf report --year 2025 Generate tax report from stored data
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "decaf"


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="decaf",
        description="De-CAF: Italian tax report generator. No commercialista needed.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--db", type=Path,
        default=_DEFAULT_CACHE_DIR / "statements.db",
        help="Path to statement SQLite database",
    )

    sub = parser.add_subparsers(dest="command")

    # --- decaf fetch ---
    fetch_p = sub.add_parser(
        "fetch",
        help="Fetch/import broker data and store in local database",
    )
    fetch_p.add_argument(
        "--broker", choices=["ibkr", "schwab"], default="ibkr",
        help="Broker source (default: ibkr)",
    )
    fetch_p.add_argument(
        "--file", type=Path, default=None,
        help="Import from local file (IBKR: FlexQuery XML, Schwab: JSON export)",
    )
    fetch_p.add_argument(
        "--token", default=None,
        help="IBKR Flex token (default: IBKR_TOKEN env var)",
    )
    fetch_p.add_argument(
        "--query-id", default=None,
        help="IBKR Flex Query ID (default: IBKR_QUERY_ID env var)",
    )

    # --- decaf report ---
    report_p = sub.add_parser("report", help="Generate tax report from stored data")
    report_p.add_argument(
        "--year", type=int, required=True,
        help="Tax year to report on (e.g., 2025)",
    )
    report_p.add_argument(
        "--output-dir", type=Path, default=Path("."),
        help="Directory for output files (default: current dir)",
    )
    report_p.add_argument(
        "--ecb-db", type=Path,
        default=_DEFAULT_CACHE_DIR / "ecb_rates.db",
        help="Path to ECB rates SQLite cache",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "fetch":
        asyncio.run(_cmd_fetch(args))
    elif args.command == "report":
        asyncio.run(_cmd_report(args))


# -----------------------------------------------------------------------
# decaf fetch
# -----------------------------------------------------------------------


async def _cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch/import statement data and store in SQLite."""
    import aiohttp

    from decaf.ecb_cache import EcbRateCache
    from decaf.statement_store import StatementStore

    if args.broker == "schwab":
        data = await _fetch_schwab(args)
    else:
        data = await _fetch_ibkr(args)

    print(
        f"Parsed: {data.account.account_id} | "
        f"{data.statement_from} to {data.statement_to}"
    )
    print(
        f"  Trades: {len(data.trades)}  "
        f"Positions: {len(data.positions)} lots  "
        f"Cash txns: {len(data.cash_transactions)}  "
        f"FX rates: {len(data.conversion_rates)}"
    )

    # Store in SQLite
    with StatementStore(args.db) as store:
        store.store(data)
        total_fetches = store.fetch_count()

    print(f"Stored in {args.db} (fetch #{total_fetches})")

    # Also fetch + cache ECB rates for years covered by the statement
    ecb_db = _DEFAULT_CACHE_DIR / "ecb_rates.db"
    years = set(range(data.statement_from.year, data.statement_to.year + 1))
    print(f"Fetching ECB rates for {sorted(years)}...")
    async with EcbRateCache(ecb_db) as ecb_cache:
        async with aiohttp.ClientSession() as session:
            for year in sorted(years):
                count = await ecb_cache.ensure_year(session, year)
                print(f"  {year}: {count} days cached")


async def _fetch_ibkr(args: argparse.Namespace):
    """Fetch/import IBKR data."""
    from decaf.parse import parse_statement_all

    if args.file:
        print(f"Loading FlexQuery XML from {args.file}")
        xml_text = args.file.read_text()
    else:
        xml_text = await _fetch_from_ibkr(args)

    return parse_statement_all(xml_text)


async def _fetch_schwab(args: argparse.Namespace):
    """Import Schwab JSON export + fetch vest prices from Yahoo."""
    import aiohttp

    from decaf.schwab_parse import extract_vest_dates, fetch_vest_prices, parse_schwab_json

    if not args.file:
        print("Schwab requires a JSON export file.")
        print("Download from: schwab.com → Accounts → History → Export (JSON)")
        sys.exit(1)

    print(f"Loading Schwab JSON from {args.file}")

    # Extract vest dates and fetch closing prices from Yahoo
    vest_dates = extract_vest_dates(args.file)
    if vest_dates:
        print(f"Fetching META vest prices for {len(vest_dates)} dates...")
        async with aiohttp.ClientSession() as session:
            vest_prices = await fetch_vest_prices(session, "META", vest_dates)
        print(f"  Got prices for {len(vest_prices)} dates")
    else:
        vest_prices = {}

    return parse_schwab_json(args.file, vest_prices)


# -----------------------------------------------------------------------
# decaf report
# -----------------------------------------------------------------------


async def _cmd_report(args: argparse.Namespace) -> None:
    """Generate tax report from stored data + ECB rates."""
    import aiohttp

    from decaf.ecb_cache import EcbRateCache
    from decaf.forex import analyze_forex_threshold
    from decaf.fx import FxService
    from decaf.models import TaxReport
    from decaf.output_cli import print_report
    from decaf.output_json import write_json
    from decaf.output_pdf import write_pdf
    from decaf.output_xls import write_xls
    from decaf.quadro_rl import compute_rl
    from decaf.quadro_rt import compute_rt
    from decaf.quadro_rw import compute_rw
    from decaf.statement_store import StatementStore

    tax_year = args.year

    # --- Step 1: Load from store ---
    with StatementStore(args.db) as store:
        if store.fetch_count() == 0:
            print(f"No data in {args.db}. Run 'decaf fetch' first.")
            sys.exit(1)
        data = store.load_for_year(tax_year)

    print(f"Loaded from {args.db} for tax year {tax_year}")
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

    # --- Step 2: ECB rates ---
    print("Fetching ECB rates...")
    async with EcbRateCache(args.ecb_db) as ecb_cache:
        async with aiohttp.ClientSession() as session:
            count = await ecb_cache.ensure_year(session, tax_year)
        print(f"  ECB rates: {count} days cached for {tax_year}")

        ecb_rates = await ecb_cache.get_all_rates_for_year("USD", tax_year)

    # --- Step 3: Build FX service ---
    fx = FxService(data.conversion_rates, ecb_rates)

    # --- Step 4: Computations ---
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
    print(f"  Quadro RW: {len(rw_lines)} lines, IVAFE: EUR {total_ivafe:.2f}")

    # Quadro RT
    rt_lines = compute_rt(data.trades, fx, tax_year, forex.threshold_breached)
    net_rt = sum(l.gain_loss_eur for l in rt_lines)
    print(f"  Quadro RT: {len(rt_lines)} lines, net: EUR {net_rt:.2f}")

    # Quadro RL
    rl_lines = compute_rl(data.cash_transactions, fx, tax_year)
    total_interest = sum(l.gross_amount_eur for l in rl_lines)
    total_wht = sum(l.wht_amount_eur for l in rl_lines)
    print(f"  Quadro RL: {len(rl_lines)} lines, gross: EUR {total_interest:.2f}, WHT: EUR {total_wht:.2f}")

    # --- Step 5: Assemble report ---
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

    # --- Step 6: CLI output ---
    print_report(report)

    # --- Step 7: File output ---
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_id = data.account.account_id.replace(", ", "_")
    prefix = f"decaf_{safe_id}_{tax_year}"

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


# -----------------------------------------------------------------------
# IBKR fetch helper
# -----------------------------------------------------------------------


async def _fetch_from_ibkr(args: argparse.Namespace) -> str:
    """Fetch FlexQuery XML from IBKR API."""
    import aiohttp

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "vendor" / "ibkr-flex-client" / "src"))
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
