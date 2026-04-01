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
        "--gains-pdfs", type=Path, nargs="+", default=None,
        help="Schwab Year-End Summary PDFs (realized gains per lot)",
    )
    fetch_p.add_argument(
        "--vest-pdfs", type=Path, nargs="+", default=None,
        help="Schwab Annual Withholding Statement PDFs (vest FMVs for open positions)",
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
    """Import Schwab data from three sources: PDFs + JSON.

    With --positions, also fetches current positions via API to get
    real market prices for year-end IVAFE valuation.
    """
    from decaf.schwab_parse import parse_schwab

    if not args.file:
        print("Schwab requires --file (transaction JSON export).")
        print("Download from: schwab.com → Accounts → History → Export (JSON)")
        sys.exit(1)
    if not args.gains_pdfs:
        print("Schwab requires --gains-pdfs (Year-End Summary PDFs).")
        print("Download from: schwab.com → Tax Center → Year-End Summary")
        sys.exit(1)
    if not args.vest_pdfs:
        print("Schwab requires --vest-pdfs (Annual Withholding Statement PDFs).")
        print("Download from: schwab.com → Equity Award Center → Documents")
        sys.exit(1)

    print(f"Loading Schwab data:")
    print(f"  JSON:       {args.file}")
    print(f"  Gains PDFs: {len(args.gains_pdfs)} files")
    print(f"  Vest PDFs:  {len(args.vest_pdfs)} files")

    return parse_schwab(args.file, args.gains_pdfs, args.vest_pdfs)


# -----------------------------------------------------------------------
# decaf report
# -----------------------------------------------------------------------


async def _cmd_report(args: argparse.Namespace) -> None:
    """Generate tax report from stored data + ECB rates."""
    import aiohttp

    from decimal import Decimal, ROUND_HALF_UP

    from decaf.ecb_cache import EcbRateCache
    from decaf.forex import analyze_forex_threshold
    from decaf.forex_gains import compute_forex_gains
    from decaf.fx import FxService
    from decaf.models import RTLine, TaxReport
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
        all_cash_txns = store.load_all_cash_transactions()

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
    # Load rates for all years covered by trades (vest dates can go back years)
    trade_years = {t.trade_datetime.year for t in data.trades}
    trade_years.add(tax_year)
    all_years = sorted(trade_years)

    print(f"Fetching ECB rates for {all_years}...")
    ecb_rates: dict = {}
    async with EcbRateCache(args.ecb_db) as ecb_cache:
        async with aiohttp.ClientSession() as session:
            for year in all_years:
                count = await ecb_cache.ensure_year(session, year)
                print(f"  {year}: {count} days cached")

        for year in all_years:
            year_rates = await ecb_cache.get_all_rates_for_year("USD", year)
            ecb_rates.update(year_rates)

    # --- Step 3: Year-end mark prices from Yahoo Finance ---
    # Only fetch prices for symbols HELD at year-end (not sold before Dec 31).
    from datetime import date as _date
    from decaf.quadro_rw import _reconstruct_lot_slices

    year_end = _date(tax_year, 12, 31)
    slices = _reconstruct_lot_slices(data.trades, tax_year)
    held_at_year_end = {
        s.symbol for s in slices
        if s.disposed is None or s.disposed > year_end
    }

    stk_info: dict[str, tuple[str, str, str]] = {}
    for t in data.trades:
        if t.asset_category == "STK" and t.symbol in held_at_year_end:
            if t.symbol not in stk_info or t.listing_exchange:
                stk_info[t.symbol] = (t.currency, t.isin, t.listing_exchange)
    for p in data.positions:
        if p.listing_exchange and p.symbol in stk_info:
            cur, isin, _ = stk_info[p.symbol]
            stk_info[p.symbol] = (cur, isin, p.listing_exchange)

    year_end_prices = _fetch_year_end_prices(stk_info, year_end)

    # --- Step 4: Build FX service ---
    fx = FxService(data.conversion_rates, ecb_rates)

    # --- Step 5: Computations ---
    print("Computing tax report...")

    # Forex threshold (must run first — uses ALL cash txns for carry-over balance)
    forex = analyze_forex_threshold(data.trades, all_cash_txns, fx, tax_year)
    print(
        f"  Forex threshold: {'BREACHED' if forex.threshold_breached else 'NOT breached'}"
        f" (max {forex.max_consecutive_business_days} consecutive business days)"
    )

    # Quadro RW (reconstructs positions from trades for the tax year)
    rw_lines = compute_rw(
        data.positions, data.trades, data.cash_report, all_cash_txns,
        fx, tax_year, mark_prices=year_end_prices,
    )
    total_ivafe = sum(l.ivafe_due for l in rw_lines)
    print(f"  Quadro RW: {len(rw_lines)} lines, IVAFE: EUR {total_ivafe:.2f}")

    # Quadro RT (stock gains only — forex handled separately)
    rt_lines = compute_rt(data.trades, fx, tax_year)
    net_rt = sum(l.gain_loss_eur for l in rt_lines)
    print(f"  Quadro RT: {len(rt_lines)} stock lines, net: EUR {net_rt:.2f}")

    # Forex FIFO gains (only when threshold breached)
    if forex.threshold_breached:
        forex_gain_entries = compute_forex_gains(
            data.trades, all_cash_txns, fx, tax_year,
        )
        net_forex = sum(e.gain_eur for e in forex_gain_entries)
        print(f"  Forex gains: {len(forex_gain_entries)} FIFO entries, net: EUR {net_forex:.2f}")

        # Convert to RTLine and append
        _q = Decimal("0.01")
        for entry in forex_gain_entries:
            eur_at_disposal = (entry.usd_amount / entry.ecb_rate_disposal).quantize(_q, ROUND_HALF_UP)
            eur_at_acquisition = (entry.usd_amount / entry.ecb_rate_acquisition).quantize(_q, ROUND_HALF_UP)
            rt_lines.append(RTLine(
                symbol="EUR.USD",
                isin="",
                sell_date=entry.disposal_date,
                quantity=entry.usd_amount,
                proceeds_eur=eur_at_disposal,
                cost_basis_eur=eur_at_acquisition,
                gain_loss_eur=entry.gain_eur,
                is_forex=True,
                broker_pnl=Decimal(0),
                broker_pnl_eur=Decimal(0),
            ))

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
        forex_usd_events=forex.usd_events,
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
# Year-end mark prices from Yahoo Finance
# -----------------------------------------------------------------------


def _fetch_year_end_prices(
    symbols_info: dict[str, tuple[str, str, str]],
    year_end: "date",
) -> dict[str, "Decimal"]:
    """Fetch closing prices on or before year_end from Yahoo Finance.

    Args:
        symbols_info: {symbol: (currency, isin, listing_exchange)}
        year_end: Date to fetch prices for

    Returns:
        {symbol: closing_price} in the symbol's native currency

    Raises:
        SystemExit: if any symbol fails — missing price = wrong IVAFE
    """
    from datetime import timedelta
    from decimal import Decimal

    import yfinance as yf

    start = year_end - timedelta(days=10)
    end = year_end + timedelta(days=1)

    prices: dict[str, Decimal] = {}
    failed: list[str] = []

    for symbol, (currency, isin, exchange) in symbols_info.items():
        ticker_id = _yfinance_ticker(symbol, isin, exchange)
        try:
            ticker = yf.Ticker(ticker_id)
            hist = ticker.history(start=start.isoformat(), end=end.isoformat())
            if hist.empty:
                failed.append(f"{symbol} (tried {ticker_id})")
                continue
            last_close = float(hist["Close"].iloc[-1])
            prices[symbol] = Decimal(str(last_close)).quantize(Decimal("0.01"))
            ccy = "€" if currency == "EUR" else "$"
            print(f"  {symbol} ({ticker_id}) year-end close: {ccy}{prices[symbol]}")
        except Exception as e:
            failed.append(f"{symbol} ({ticker_id}): {e}")

    if failed:
        print(f"\nERROR: Failed to fetch year-end prices for: {', '.join(failed)}")
        print("Cannot compute IVAFE without market prices. Aborting.")
        sys.exit(1)

    return prices


# IBKR listingExchange → Yahoo Finance suffix
_EXCHANGE_TO_YF = {
    # US exchanges
    "NASDAQ": "", "NYSE": "", "ARCA": "", "AMEX": "", "BATS": "",
    # London
    "LSEETF": ".L", "LSE": ".L",
    # XETRA
    "IBIS": ".DE", "IBIS2": ".DE",
    # Amsterdam
    "AEB": ".AS",
    # Paris
    "SBF": ".PA",
    # Milan
    "BVME": ".MI",
    # Swiss
    "EBS": ".SW",
}


def _yfinance_ticker(symbol: str, isin: str, exchange: str) -> str:
    """Map broker symbol + exchange to Yahoo Finance ticker.

    US stocks (ISIN US*) need no suffix. Non-US stocks use the IBKR
    listingExchange to determine the correct Yahoo Finance suffix.
    """
    if isin[:2] == "US":
        return symbol
    if exchange:
        suffix = _EXCHANGE_TO_YF.get(exchange, "")
        if suffix:
            return f"{symbol}{suffix}"
    # No exchange info — this is a Schwab position (US stock, handled above)
    # or missing data. Return as-is, will fail loudly if wrong.
    return symbol


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
