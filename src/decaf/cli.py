"""CLI entry point for decaf.

Two subcommands:
    decaf load               Load broker data and store in local SQLite
    decaf report --year 2025 Generate tax report from stored data
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import aiohttp
import yaml
from dotenv import load_dotenv

from decaf.ecb_cache import EcbRateCache
from decaf.forex import analyze_forex_threshold
from decaf.forex_gains import compute_forex_gains, forex_gains_to_rt_lines
from decaf.fx import FxService
from decaf.models import TaxReport
from decaf.output_cli import print_report
from decaf.output_pdf import write_pdf
from decaf.output_xls import write_xls
from decaf.output_yaml import write_yaml
from decaf.parse import ParsedData, parse_statement_all
from decaf.prices import PriceFetchError, fetch_year_end_prices
from decaf.quadro_rl import compute_rl
from decaf.quadro_rt import compute_rt
from decaf.quadro_rw import compute_rw, symbols_needing_prices
from decaf.schwab_parse import parse_schwab
from decaf.statement_store import StatementStore

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

    # --- decaf load ---
    load_p = sub.add_parser(
        "load",
        help="Load broker data and store in local database",
    )
    load_p.add_argument(
        "--broker", choices=["ibkr", "schwab"], default="ibkr",
        help="Broker source (default: ibkr)",
    )
    load_p.add_argument(
        "--file", type=Path, default=None,
        help="Import from local file (IBKR: FlexQuery XML, Schwab: JSON export)",
    )
    load_p.add_argument(
        "--gains-pdfs", type=Path, nargs="+", default=None,
        help="Schwab Year-End Summary PDFs (realized gains per lot)",
    )
    load_p.add_argument(
        "--vest-pdfs", type=Path, nargs="+", default=None,
        help="Schwab Annual Withholding Statement PDFs (vest FMVs for open positions)",
    )
    load_p.add_argument(
        "--token", default=None,
        help="IBKR Flex token (default: IBKR_TOKEN env var)",
    )
    load_p.add_argument(
        "--query-id", default=None,
        help="IBKR Flex Query ID (default: IBKR_QUERY_ID env var)",
    )

    # --- decaf backtest ---
    backtest_p = sub.add_parser(
        "backtest",
        help="Run pipeline over a directory of broker exports and diff vs committed YAML",
    )
    backtest_p.add_argument(
        "directory", type=Path,
        help="Directory containing broker exports and decaf_<year>.yaml oracles",
    )
    backtest_p.add_argument(
        "--year", type=int, default=None,
        help="Restrict to a single tax year (default: all years found)",
    )
    backtest_p.add_argument(
        "--update", action="store_true",
        help="Write fresh YAML oracles instead of comparing",
    )
    backtest_p.add_argument(
        "--token", default=None,
        help="IBKR Flex token (default: IBKR_TOKEN env var; used only when no XML present)",
    )
    backtest_p.add_argument(
        "--query-id", default=None,
        help="IBKR Flex Query ID (default: IBKR_QUERY_ID env var)",
    )
    backtest_p.add_argument(
        "--ecb-db", type=Path,
        default=_DEFAULT_CACHE_DIR / "ecb_rates.db",
        help="Path to ECB rates SQLite cache",
    )

    # --- decaf manual ---
    sub.add_parser("manual", help="Generate project manual PDF from documentation")

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

    if args.command == "load":
        asyncio.run(_cmd_load(args))
    elif args.command == "report":
        asyncio.run(_cmd_report(args))
    elif args.command == "backtest":
        sys.exit(asyncio.run(_cmd_backtest(args)))
    elif args.command == "manual":
        _cmd_manual()


# -----------------------------------------------------------------------
# decaf manual
# -----------------------------------------------------------------------


def _cmd_manual() -> None:
    """Generate project manual PDF from doc/ markdown files."""
    import subprocess

    script = Path(__file__).resolve().parent.parent.parent / "scripts" / "manual.sh"
    if not script.exists():
        print(f"ERROR: {script} not found")
        sys.exit(1)

    result = subprocess.run([str(script)], cwd=script.parent.parent)
    sys.exit(result.returncode)


# -----------------------------------------------------------------------
# decaf load
# -----------------------------------------------------------------------


async def _cmd_load(args: argparse.Namespace) -> None:
    """Load broker statement data and store in SQLite."""
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
        total_loads = store.fetch_count()

    print(f"Stored in {args.db} (load #{total_loads})")

    # Also fetch + cache ECB rates for years covered by the statement
    ecb_db = _DEFAULT_CACHE_DIR / "ecb_rates.db"
    years = set(range(data.statement_from.year, data.statement_to.year + 1))
    print(f"Fetching ECB rates for {sorted(years)}...")
    async with EcbRateCache(ecb_db) as ecb_cache, aiohttp.ClientSession() as session:
        for year in sorted(years):
            count = await ecb_cache.ensure_year(session, year)
            print(f"  {year}: {count} days cached")


async def _fetch_ibkr(args: argparse.Namespace) -> ParsedData:
    """Fetch/import IBKR data."""
    if args.file:
        print(f"Loading FlexQuery XML from {args.file}")
        xml_text = args.file.read_text()
    else:
        xml_text = await _fetch_from_ibkr(args)

    return parse_statement_all(xml_text)


async def _fetch_schwab(args: argparse.Namespace) -> ParsedData:
    """Import Schwab data from three sources: PDFs + JSON."""
    if not args.file:
        print("Schwab requires --file (transaction JSON export).")
        print("Download from: schwab.com -> Accounts -> History -> Export (JSON)")
        sys.exit(1)
    if not args.gains_pdfs:
        print("Schwab requires --gains-pdfs (Year-End Summary PDFs).")
        print("Download from: schwab.com -> Tax Center -> Year-End Summary")
        sys.exit(1)
    if not args.vest_pdfs:
        print("Schwab requires --vest-pdfs (Annual Withholding Statement PDFs).")
        print("Download from: schwab.com -> Equity Award Center -> Documents")
        sys.exit(1)

    print("Loading Schwab data:")
    print(f"  JSON:       {args.file}")
    print(f"  Gains PDFs: {len(args.gains_pdfs)} files")
    print(f"  Vest PDFs:  {len(args.vest_pdfs)} files")

    return parse_schwab(args.file, args.gains_pdfs, args.vest_pdfs)


# -----------------------------------------------------------------------
# decaf report
# -----------------------------------------------------------------------


async def _cmd_report(args: argparse.Namespace) -> None:
    """Generate tax report from stored data + ECB rates."""
    tax_year = args.year
    report, _data = await _load_and_build_report(args.db, args.ecb_db, tax_year)
    print_report(report)
    _write_outputs(report, args.output_dir, tax_year)


async def _load_and_build_report(
    db_path: Path,
    ecb_db_path: Path,
    tax_year: int,
    price_overrides: dict[int, dict[str, Decimal]] | None = None,
) -> tuple[TaxReport, ParsedData]:
    """Load stored data for a year and build its TaxReport.

    `price_overrides` is the parsed `prices.yaml` keyed by calendar year:
    `{year: {symbol: price}}`. Both `tax_year` and `tax_year - 1` blocks are
    consulted — the former for year-end IVAFE marks, the latter for initial_value
    in the pro-rata computation.
    """
    with StatementStore(db_path) as store:
        if store.fetch_count() == 0:
            print(f"No data in {db_path}. Run 'decaf load' first.")
            sys.exit(1)
        data = store.load_for_year(tax_year)

    print(f"Loaded from {db_path} for tax year {tax_year}")
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

    report = await _build_report(data, ecb_db_path, tax_year, price_overrides)
    return report, data


async def _build_report(
    data: ParsedData,
    ecb_db_path: Path,
    tax_year: int,
    price_overrides: dict[int, dict[str, Decimal]] | None = None,
) -> TaxReport:
    """Core report computation: ECB rates + prices + RW/RT/RL/forex."""
    # --- Step 2: ECB rates ---
    trade_years = {t.trade_datetime.year for t in data.trades}
    trade_years.add(tax_year)
    all_years = sorted(trade_years)

    print(f"Fetching ECB rates for {all_years}...")
    ecb_rates: dict[date, Decimal] = {}
    async with EcbRateCache(ecb_db_path) as ecb_cache:
        async with aiohttp.ClientSession() as session:
            for year in all_years:
                count = await ecb_cache.ensure_year(session, year)
                print(f"  {year}: {count} days cached")

        for year in all_years:
            year_rates = await ecb_cache.get_all_rates_for_year("USD", year)
            ecb_rates.update(year_rates)

    # --- Step 3: Year-end mark prices from Yahoo Finance ---
    year_end = date(tax_year, 12, 31)
    prior_year_end = date(tax_year - 1, 12, 31)
    held_at_year_end, carried_from_prior = symbols_needing_prices(
        data.trades, tax_year,
    )

    # Build symbol -> (currency, isin, exchange) from trades + positions
    stk_info: dict[str, tuple[str, str, str]] = {}
    for trade in data.trades:
        if trade.asset_category == "STK" and (
            trade.symbol not in stk_info or trade.listing_exchange
        ):
            stk_info[trade.symbol] = (
                trade.currency, trade.isin, trade.listing_exchange,
            )
    for pos in data.positions:
        if pos.listing_exchange and pos.symbol in stk_info:
            cur, isin, _ = stk_info[pos.symbol]
            stk_info[pos.symbol] = (cur, isin, pos.listing_exchange)

    by_year = price_overrides or {}
    overrides = dict(by_year.get(tax_year, {}))
    prior_overrides = dict(by_year.get(tax_year - 1, {}))

    # Broker-provided year-end mark prices (from OpenPositions).
    # Skip placeholder marks where Schwab stuffs cost_basis/qty.
    broker_marks: dict[str, Decimal] = {}
    for pos in data.positions:
        if not (pos.quantity and pos.mark_price):
            continue
        cost_per_share = pos.cost_basis_money / pos.quantity
        if abs(cost_per_share - pos.mark_price) < Decimal("0.01"):
            continue
        broker_marks[pos.symbol] = pos.mark_price

    # Fetch year-end prices (overrides + broker cover most; yfinance fills gaps)
    ye_info = {
        s: stk_info[s] for s in held_at_year_end
        if s in stk_info and s not in broker_marks and s not in overrides
    }
    prior_info = {
        s: stk_info[s] for s in carried_from_prior
        if s in stk_info and s not in prior_overrides
    }
    try:
        year_end_prices = (
            fetch_year_end_prices(ye_info, year_end) if ye_info else {}
        )
    except PriceFetchError as exc:
        print(f"\nWARN: {exc}")
        print("Falling back to broker-provided mark prices where available.")
        year_end_prices = {}
    year_end_prices.update(broker_marks)
    year_end_prices.update(overrides)

    missing_ye = [s for s in held_at_year_end if s not in year_end_prices]
    if missing_ye:
        print(
            f"\nERROR: no year-end price for {', '.join(missing_ye)} "
            f"(yfinance + broker both failed)."
        )
        print("Cannot compute IVAFE without market prices. Aborting.")
        sys.exit(1)

    try:
        prior_year_prices = (
            fetch_year_end_prices(prior_info, prior_year_end)
            if prior_info else {}
        )
    except PriceFetchError as exc:
        print(f"\nWARN: {exc}")
        print("Prior-year prices unavailable; initial_value will fall back "
              "to acquisition cost per symbol. IVAFE is unaffected.")
        prior_year_prices = {}
    prior_year_prices.update(prior_overrides)

    # --- Step 4: Build FX service ---
    fx = FxService(data.conversion_rates, ecb_rates)

    # --- Step 5: Computations ---
    print("Computing tax report...")

    # Forex threshold (uses ALL cash txns for carry-over balance)
    forex = analyze_forex_threshold(
        data.trades, data.cash_transactions, fx, tax_year,
    )
    print(
        f"  Forex threshold: "
        f"{'BREACHED' if forex.threshold_breached else 'NOT breached'}"
        f" (max {forex.max_consecutive_business_days} consecutive business days)"
    )

    # Quadro RW
    rw_lines = compute_rw(
        data.positions, data.trades, data.cash_report, data.cash_transactions,
        fx, tax_year,
        mark_prices=year_end_prices,
        prior_year_prices=prior_year_prices,
    )
    total_ivafe = sum((rw.ivafe_due for rw in rw_lines), Decimal(0))
    print(f"  Quadro RW: {len(rw_lines)} lines, IVAFE: EUR {total_ivafe:.2f}")

    # Quadro RT (stock gains only — forex handled separately)
    rt_lines = compute_rt(data.trades, fx, tax_year)
    net_rt = sum((rt.gain_loss_eur for rt in rt_lines), Decimal(0))
    print(f"  Quadro RT: {len(rt_lines)} stock lines, net: EUR {net_rt:.2f}")

    # Forex LIFO gains per account (only when threshold breached)
    if forex.threshold_breached:
        forex_entries = compute_forex_gains(
            data.trades, data.cash_transactions, fx, tax_year,
        )
        net_forex = sum((e.gain_eur for e in forex_entries), Decimal(0))
        print(
            f"  Forex gains: {len(forex_entries)} LIFO entries, "
            f"net: EUR {net_forex:.2f}"
        )
        rt_lines.extend(forex_gains_to_rt_lines(forex_entries))

    # Quadro RL
    rl_lines = compute_rl(data.cash_transactions, fx, tax_year)
    total_interest = sum((rl.gross_amount_eur for rl in rl_lines), Decimal(0))
    total_wht = sum((rl.wht_amount_eur for rl in rl_lines), Decimal(0))
    print(
        f"  Quadro RL: {len(rl_lines)} lines, "
        f"gross: EUR {total_interest:.2f}, WHT: EUR {total_wht:.2f}"
    )

    # --- Step 6: Assemble report ---
    return TaxReport(
        tax_year=tax_year,
        account=data.account,
        rw_lines=rw_lines,
        rt_lines=rt_lines,
        rl_lines=rl_lines,
        forex_threshold_breached=forex.threshold_breached,
        forex_max_consecutive_days=forex.max_consecutive_business_days,
        forex_first_breach_date=forex.first_breach_date,
        forex_daily_records=forex.daily_records,
        forex_usd_events=forex.usd_events,
    )


def _write_outputs(
    report: TaxReport,
    output_dir: Path,
    tax_year: int,
) -> None:
    """Write YAML (canonical), Excel, and PDF outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"decaf_{tax_year}"

    yaml_path = output_dir / f"{prefix}.yaml"
    write_yaml(report, yaml_path)
    print(f"\nYAML:  {yaml_path}")

    xls_path = output_dir / f"{prefix}.xlsx"
    write_xls(report, xls_path)
    print(f"Excel: {xls_path}")

    pdf_path = output_dir / f"{prefix}.pdf"
    write_pdf(report, pdf_path)
    print(f"PDF:   {pdf_path}")

    print("\nDone.")


# -----------------------------------------------------------------------
# decaf backtest
# -----------------------------------------------------------------------


async def _cmd_backtest(args: argparse.Namespace) -> int:
    """Run the decaf pipeline over a BYOD directory, diff vs committed YAML."""
    import re
    import tempfile

    d: Path = args.directory
    if not d.is_dir():
        print(f"ERROR: {d} is not a directory")
        return 2

    # --- Discover inputs ---
    xml_files = sorted(d.glob("*.xml"))
    schwab_json = sorted(d.glob("Individual_*_Transactions_*.json"))
    gains_pdfs = sorted(d.glob("Year-End Summary*.PDF"))
    vest_pdfs = sorted(d.glob("Annual Withholding*.PDF"))
    yamls = sorted(d.glob("decaf_*.yaml"))
    prices_path = d / "prices.yaml"

    yaml_years: dict[int, Path] = {}
    for p in yamls:
        m = re.match(r"decaf_(\d{4})\.yaml$", p.name)
        if m:
            yaml_years[int(m.group(1))] = p

    price_overrides_by_year: dict[int, dict[str, Decimal]] = {}
    if prices_path.exists():
        with open(prices_path) as f:
            raw = yaml.safe_load(f) or {}
        for y, syms in raw.items():
            price_overrides_by_year[int(y)] = {
                str(s): Decimal(str(p)) for s, p in (syms or {}).items()
            }
        print(f"  Price overrides: {prices_path.name} ({sorted(price_overrides_by_year)})")

    if args.year is not None:
        target_years = [args.year]
    elif yaml_years:
        target_years = sorted(yaml_years)
    elif args.update:
        print("ERROR: --update needs at least one --year or existing decaf_<year>.yaml.")
        return 2
    else:
        print("ERROR: no decaf_<year>.yaml oracles found; pass --year or --update.")
        return 2

    print(f"Backtest dir: {d}")
    print(
        f"  XML: {len(xml_files)}  Schwab JSON: {len(schwab_json)}  "
        f"gains PDF: {len(gains_pdfs)}  vest PDF: {len(vest_pdfs)}  "
        f"YAML oracles: {len(yaml_years)}"
    )
    print(f"  Target years: {target_years}")

    # --- Temp DB (never touch fixture dir) ---
    tmp_db = Path(tempfile.gettempdir()) / f"decaf_bt_{os.getpid()}.db"
    tmp_db.unlink(missing_ok=True)
    print(f"  Temp DB: {tmp_db}")

    try:
        # --- Ingest IBKR ---
        if xml_files:
            for xml_path in xml_files:
                print(f"Ingesting IBKR XML: {xml_path.name}")
                ibkr_data = parse_statement_all(xml_path.read_text())
                with StatementStore(tmp_db) as store:
                    store.store(ibkr_data)
        elif os.environ.get("IBKR_TOKEN") or args.token:
            print("No XML found — falling back to IBKR API fetch.")
            fetch_args = argparse.Namespace(
                token=args.token,
                query_id=args.query_id,
            )
            xml_text = await _fetch_from_ibkr(fetch_args)
            ibkr_data = parse_statement_all(xml_text)
            with StatementStore(tmp_db) as store:
                store.store(ibkr_data)
        else:
            print("No XML and no IBKR_TOKEN — skipping IBKR ingest.")

        # --- Ingest Schwab (needs all three file types) ---
        if schwab_json and gains_pdfs and vest_pdfs:
            print(
                f"Ingesting Schwab: {len(schwab_json)} JSON, "
                f"{len(gains_pdfs)} gains PDF, {len(vest_pdfs)} vest PDF"
            )
            for json_path in schwab_json:
                schwab_data = parse_schwab(json_path, gains_pdfs, vest_pdfs)
                with StatementStore(tmp_db) as store:
                    store.store(schwab_data)
        elif schwab_json or gains_pdfs or vest_pdfs:
            print(
                "Schwab requires all three: Individual_*.json, "
                "Year-End Summary*.PDF, Annual Withholding*.PDF. Skipping Schwab."
            )

        # --- Fetch ECB rates for all target years (and prior years for RT) ---
        all_years = set(target_years)
        for y in list(target_years):
            all_years.add(y - 1)
        async with (
            EcbRateCache(args.ecb_db) as ecb_cache,
            aiohttp.ClientSession() as session,
        ):
            for y in sorted(all_years):
                await ecb_cache.ensure_year(session, y)

        # --- Per-year build + compare/update ---
        had_mismatch = False
        for year in target_years:
            print(f"\n--- Year {year} ---")
            report, _data = await _load_and_build_report(
                tmp_db, args.ecb_db, year,
                price_overrides=price_overrides_by_year,
            )

            if args.update:
                yaml_path = d / f"decaf_{year}.yaml"
                write_yaml(report, yaml_path)
                print(f"Wrote oracle: {yaml_path}")
                continue

            expected_path = yaml_years.get(year)
            if expected_path is None:
                print(f"No oracle for {year}; skipping compare.")
                continue

            with open(expected_path) as f:
                expected = yaml.safe_load(f)
            actual = report.model_dump(mode="json")
            diffs = _diff_reports(expected, actual, path="")
            if not diffs:
                print(f"OK: {year} matches {expected_path.name}")
            else:
                had_mismatch = True
                print(f"MISMATCH {year} vs {expected_path.name}:")
                for d_msg in diffs:
                    print(f"  {d_msg}")

        return 1 if had_mismatch else 0
    finally:
        tmp_db.unlink(missing_ok=True)


def _diff_reports(expected: object, actual: object, path: str) -> list[str]:
    """Recursive structural diff. `None` in expected with non-null actual = warning + skip."""
    if expected is None and actual is None:
        return []
    if expected is None:
        print(f"  WARN: oracle null at {path or '<root>'} — skipping field (actual={actual!r})")
        return []
    if type(expected) is not type(actual):
        return [f"{path}: type {type(expected).__name__} != {type(actual).__name__}"]
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        msgs: list[str] = []
        keys = set(expected) | set(actual)
        for k in sorted(keys):
            sub = f"{path}.{k}" if path else k
            if k not in expected:
                msgs.append(f"{sub}: missing in oracle (actual={actual[k]!r})")
                continue
            if k not in actual:
                msgs.append(f"{sub}: missing in actual (oracle={expected[k]!r})")
                continue
            msgs.extend(_diff_reports(expected[k], actual[k], sub))
        return msgs
    if isinstance(expected, list):
        assert isinstance(actual, list)
        if len(expected) != len(actual):
            return [
                f"{path}: list length {len(expected)} != {len(actual)}"
            ]
        msgs = []
        for i, (e, a) in enumerate(zip(expected, actual, strict=True)):
            msgs.extend(_diff_reports(e, a, f"{path}[{i}]"))
        return msgs
    if expected != actual:
        return [f"{path}: {expected!r} != {actual!r}"]
    return []


# -----------------------------------------------------------------------
# IBKR fetch helper
# -----------------------------------------------------------------------


async def _fetch_from_ibkr(args: argparse.Namespace) -> str:
    """Fetch FlexQuery XML from IBKR API."""
    vendor_path = (
        Path(__file__).resolve().parent.parent.parent
        / "vendor" / "ibkr-flex-client" / "src"
    )
    sys.path.insert(0, str(vendor_path))
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

    print(
        f"  Received {len(statement.xml)} bytes, "
        f"{statement.from_date} to {statement.to_date}"
    )
    return statement.xml
