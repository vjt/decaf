# ibtax

Italian tax report generator for Interactive Brokers accounts.
Produces Quadro RW (IVAFE), RT (capital gains), RL (interest),
and forex threshold analysis for the dichiarazione dei redditi.

## Architecture

Three repos, one concern each:

- `vendor/ibkr-flex-client/` — Async IBKR Flex Web Service client (submodule)
- `vendor/ecb-fx-rates/` — Async ECB reference rate client (submodule)
- `src/ibtax/` — Tax computation, parsing, output

```
CLI (cli.py)
  ├─ fetch: FlexClient or file input
  ├─ parse: XML → domain models (parse.py)
  ├─ ECB rates: fetch + SQLite cache (ecb_cache.py)
  ├─ FX service: ECB primary, IB validation (fx.py)
  ├─ compute:
  │   ├─ forex.py    → threshold analysis (runs first)
  │   ├─ quadro_rw.py → IVAFE per lot
  │   ├─ quadro_rt.py → capital gains (trusts IB FIFO)
  │   └─ quadro_rl.py → interest + WHT
  └─ output: JSON, Excel, PDF
```

## Key Design Decisions

- **Trust IB's FIFO.** No reimplementation. Use `fifoPnlRealized` and
  `cost` directly from IB. Convert USD P/L to EUR at ECB rate on
  sell settlement date.
- **ECB rates are primary.** Cambio BCE is what Agenzia delle Entrate
  expects. IB ConversionRates used for validation only. Flag
  discrepancies > 0.5%.
- **Proper types everywhere.** Frozen dataclasses, Decimal for money,
  no raw tuples.
- **FIFO by (symbol, currency).** VWCE (EUR) and VWRA (USD) share
  ISIN IE00BK5BQT80 but have separate FIFO ledgers.
- **Per-lot IVAFE.** Open Positions in "Lot" mode gives per-lot
  `openDateTime` for pro-rata day counting.
- **Settlement dates for IVAFE, trade dates for RT.** Per Italian
  tax regulations.

## Tech Stack

- Python 3.12+, async (aiohttp) for I/O, sync for computation
- aiosqlite for ECB rate cache (~/.cache/ibtax/ecb_rates.db)
- openpyxl for Excel, fpdf2 for PDF
- Decimal for all monetary amounts (never float)
- stdlib xml.etree.ElementTree for XML parsing

## Engineering Standards

- Submodules are standalone OSS libraries — zero ibtax dependencies
- All test data is synthetic — no real account data in the repo
- Secrets (.env, tokens) are gitignored
- Output files (.json, .xlsx, .pdf, .xml) are gitignored

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -x -v --rootdir=.
```

55 tests covering: holidays, XML parsing, FX service, forex threshold.

## Running the Tool

```bash
# From file
python -m ibtax --year 2025 --file flexquery.xml

# From IBKR API (token in .env or interactive prompt)
python -m ibtax --year 2025
```

## Flex Query Configuration

See doc/QUERY_SETUP.md for the exact IB UI field selections. Critical:
Open Positions must use **Lot** mode (not Summary) to get per-lot
open dates for IVAFE.
