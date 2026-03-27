# decaf

**De-CAF** — Italian tax report generator. No commercialista needed.

Fetches data from your foreign brokerage accounts and ECB reference rates, then computes everything you need for the dichiarazione dei redditi:

- **Quadro RW** — Foreign asset monitoring + IVAFE (0.2% pro-rata)
- **Quadro RT** — Capital gains/losses (26% tax, FIFO)
- **Quadro RL** — Investment income (interest, withholding tax)
- **Forex threshold** — Art. 67(1)(c-ter) TUIR analysis

Outputs: Excel workbook (one sheet per quadro), PDF statement, and JSON.

## Supported Brokers

- **Interactive Brokers** (IBKR Ireland) — via Flex Query API
- **Charles Schwab** — coming soon (Trader API)

## Quick Start

```bash
# Clone with submodules
git clone --recursive git@github.com:vjt/decaf.git
cd decaf

# Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e vendor/ibkr-flex-client -e vendor/ecb-fx-rates -e ".[dev]"

# Run from a downloaded FlexQuery XML
python -m decaf --year 2025 --file flexquery.xml --output-dir ./out

# Or fetch directly from IBKR (token + query ID from .env or interactive prompt)
python -m decaf --year 2025 --output-dir ./out
```

## IBKR Setup

You need a Flex Query configured in your IBKR account. See the [Flex Query Setup Guide](doc/QUERY_SETUP.md) for a step-by-step walkthrough with screenshots.

For API fetch mode, set your credentials:

```bash
# .env file (gitignored)
IBKR_TOKEN=your_token_here
IBKR_QUERY_ID=your_query_id_here
```

Or pass them via `--token` / `--query-id`, or enter them interactively when prompted.

## CLI Options

```
python -m decaf --year YEAR [options]

Required:
  --year YEAR          Tax year to report on (e.g., 2025)

Input (one of):
  --file PATH          Load from a local FlexQuery XML file
  (default)            Fetch from IBKR API (needs token + query ID)

Output:
  --output-dir DIR     Where to write reports (default: current directory)
  --verbose            Print daily forex balance to terminal

Auth (for API fetch):
  --token TOKEN        IBKR Flex token (default: IBKR_TOKEN env var)
  --query-id ID        IBKR Flex Query ID (default: IBKR_QUERY_ID env var)
  --ecb-db PATH        ECB rates cache location (default: ~/.cache/decaf/ecb_rates.db)
```

## Output Files

| File | Format | Purpose |
|------|--------|---------|
| `decaf_<account>_<year>.xlsx` | Excel | One sheet per quadro + summary |
| `decaf_<account>_<year>.pdf` | PDF | Professional statement with tables and totals |
| `decaf_<account>_<year>.json` | JSON | Structured data for programmatic use |

## How It Works

1. **Fetch** — Downloads data from your broker's API (or reads a local file) and ECB reference rates in parallel
2. **Parse** — Converts broker data into typed domain models, filtered to the tax year
3. **FX Rates** — Uses ECB rates as primary source (cambio BCE, what Agenzia delle Entrate expects), broker rates for validation
4. **Compute** — Runs all tax calculations:
   - Forex threshold: reconstructs daily USD balance, checks 7+ consecutive business days above threshold
   - IVAFE: 0.2% per annum on each lot's market value, pro-rated by holding days
   - Capital gains: converts broker's FIFO P/L to EUR at ECB sell-settlement-date rate
   - Interest: matches gross interest with withholding tax by currency and month
5. **Output** — Generates Excel, PDF, and JSON reports

## Architecture

```
vendor/
  ibkr-flex-client/    Async IBKR Flex Web Service client (submodule)
  ecb-fx-rates/        Async ECB reference rate client (submodule)

src/decaf/
  cli.py               CLI entry point and orchestration
  parse.py             FlexQuery XML to domain models
  ecb_cache.py         SQLite cache for ECB rates
  fx.py                ECB primary, broker validation FX service
  holidays.py          Italian public holidays + business day logic
  forex.py             Daily USD balance + threshold analysis
  quadro_rw.py         IVAFE computation
  quadro_rt.py         Capital gains
  quadro_rl.py         Interest income + WHT
  output_xls.py        Excel workbook
  output_pdf.py        PDF statement
  output_json.py       JSON report
  models.py            All domain dataclasses
```

## Italian Tax Rules Implemented

- **IVAFE**: 0.2% annual tax on foreign financial assets, pro-rated by days held (settlement date based)
- **Capital gains**: 26% tax on redditi diversi. UCITS-harmonized ETFs (IE ISIN) classified as redditi diversi
- **Interest**: 26% tax on redditi di capitale. Reports gross, foreign WHT, and net
- **Forex threshold**: Art. 67(1)(c-ter) TUIR — daily foreign currency balance > EUR 51,645.69 for 7+ consecutive Italian business days triggers forex gain taxation
- **FX conversion**: ECB reference rates (cambio BCE) as required by Agenzia delle Entrate
- **FIFO**: Uses broker's pre-computed FIFO cost basis and realized P/L

## Development

```bash
# Run tests
pytest tests/ -x -v --rootdir=.

# Run with verbose forex output
python -m decaf --year 2025 --file flexquery.xml --verbose
```

## Requirements

- Python 3.12+
- Dependencies: aiohttp, aiosqlite, python-dotenv, openpyxl, fpdf2

## License

MIT
