# Internals — Technical Context for Development

This document captures implementation details, gotchas, and design rationale
that aren't obvious from the code. It's meant for AI assistants and developers
picking up the codebase.

For architecture overview, see [ARCHITECTURE.md](ARCHITECTURE.md).
For tax law references, see [NORMATIVA.md](NORMATIVA.md).
For the filing guide, see [GUIDA_FISCALE.md](GUIDA_FISCALE.md).

## Schwab Integration

### Why Not the Trader API?

The Schwab Trader API (v1) at `api.schwabapi.com/trader/v1` **does not return
transactions for EAC (Equity Award Center) accounts**. This is a known limitation
affecting all stock-plan-linked brokerage accounts.

- `GET /accounts/{hash}?fields=positions` → works (returns current positions)
- `GET /accounts/{hash}/transactions` → returns `[]` for ALL date ranges and types
- `GET /accounts/{hash}/orders` → returns `[]`

The OAuth2 flow works (schwab_auth.py). The position endpoint works. But
transaction history is completely absent. This has been confirmed by:
- schwab-py GitHub issues
- Reddit r/schwab and r/algotrading
- Our own testing (April 2026)

The OFX Direct Connect endpoint (`ofx.schwab.com`) was also tried — DNS is dead
post-TD Ameritrade merger.

**The OAuth code (schwab_auth.py, schwab_client.py) is kept** for:
- Live position snapshots (current market values for year-end IVAFE)
- Future use if Schwab fixes the API
- Callback URL registered: `https://127.0.0.1:8182` (SSH tunnel for headless)

### Three-File Approach

Since the API is useless, we parse files downloaded from schwab.com:

1. **Year-End Summary PDF** (`schwab_gains_pdf.py`)
   - Location: schwab.com → Statements → Tax Documents
   - Contains per-lot realized gain/loss with: date acquired, date sold,
     quantity, proceeds, cost basis, gain/loss
   - Short-term and long-term sections
   - Parsed with `pdftotext -layout` + regex
   - This is the AUTHORITATIVE source for Schwab capital gains — no FIFO

2. **Annual Withholding Statement PDF** (`schwab_vest_pdf.py`)
   - Location: schwab.com → Equity Award Center → Documents
   - Contains FMV per vest date per jurisdiction (IRL or ITA)
   - **CRITICAL**: ITA FMV != Yahoo Finance closing price != IRL FMV
     Example: Yahoo close may differ by $40-80 from ITA FMV on same date
   - Parser prefers ITA jurisdiction, falls back to IRL (for pre-Italy vests)
   - Handles jurisdiction transitions (e.g., IRL→ITA when moving to Italy)
   - Fuzzy date matching ±3 days for vest date alignment (PDF and JSON
     dates may differ by a few days due to weekends/processing)

3. **Transaction JSON** (`schwab_parse.py`)
   - Location: schwab.com → Accounts → History → Export (JSON)
   - Used for dividends ("Qualified Dividend"), WHT ("NRA Tax Adj"),
     and wire transfers ("Wire Sent" — USD disposals for forex LIFO)
   - Sells have NO cost basis in the JSON — that comes from the PDF
   - Stock Plan Activity has NO price — that comes from the Withholding PDF

### Open Position Reconstruction

Schwab positions API only gives aggregated data (no per-lot). We compute
open positions from: all vest buys (from JSON + Withholding PDF FMVs)
minus all sells (from Year-End Summary PDF, using date_acquired to match
exact lots). This gives per-lot open positions for IVAFE.

## IBKR Integration

### Flex Query API

- SendRequest URL: `https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest`
  (NOTE: slash separator, not dot — IB changed this, the old dot-separated URLs return 404)
- GetStatement URL: from `<Url>` element in SendRequest response
- The query returns ALL accounts under the login (multi-account support)
- `parse.py:parse_statement_all()` merges all FlexStatements into one ParsedData

### Multi-Account Handling

Multiple IBKR accounts under one login are merged into one report
(same dichiarazione dei redditi). The parser iterates all FlexStatements.

### 365-Day Window

IBKR Flex Query only returns "last 365 calendar days". To avoid data loss:
- `decaf fetch` stores everything in SQLite (statement_store.py)
- Run periodically to accumulate data
- `decaf report` loads from SQLite — no re-fetch needed
- Trades and cash transactions dedup on natural keys
- Position snapshots stored per (fetch_date, account_id)

## FX Service

ECB rates are primary (cambio BCE, legal requirement). IB ConversionRates
used for validation only — flag discrepancies > 0.5%.

**Important**: IB rates are "multiply to get EUR" while ECB rates are
"divide to get EUR". The FxService handles both conventions.

For incomplete years (running report for current year), `to_eur()` falls
back to the latest available ECB rate with a warning. The strict 5-day
lookback in `ecb_rate()` is preserved for direct rate queries.

## IVAFE Rules

- **Securities (codice 20)**: 0.2% per annum on year-end market value,
  pro-rated by days held (settlement date to Dec 31)
- **Cash deposits (codice 1)**: 0.2% per annum (brokerage cash is a
  "deposito", NOT a "conto corrente" — the EUR 34.20 flat fee only
  applies to bank accounts, not broker deposits)
- Both are in Quadro RW of Modello Redditi PF
- See [NORMATIVA.md - IVAFE](NORMATIVA.md#ivafe--formula) for the exact legal text

## Forex Threshold (Art. 67(1)(c-ter) TUIR)

Threshold: €51,645.69 (=100M old Lire) for 7+ consecutive Italian
business days. If breached, ALL forex conversion gains for the year
are taxable at 26%.

The forex.py module reconstructs daily USD balance from trades and
cash transactions, converts at ECB rate, checks consecutive runs.

If breached, forex conversion gains must be computed and taxed.

## Forex LIFO Gains Module (`forex_gains.py`)

Neither broker provides forex P/L — IBKR EUR.USD trades have
`broker_pnl_realized = 0`, Schwab wire transfers aren't forex trades.

### Rule

Art. 67 c. 1-bis TUIR + risposta AdE 204/2023 mandate **LIFO per single
account**: disposals pop the most-recently-acquired lot first, and
each account's queue is isolated from all others.

### How It Works

USD lot tracker using a `dict[account_id, deque[_UsdLot]]` keyed by
account. Acquisitions `.append()` onto the account's deque. Disposals
consume from the back (`deque[-1]` + `deque.pop()`).

**USD acquired** (lots enter queue of origin account):
- Stock sell proceeds (from Year-End Summary and FlexQuery)
- Interest/dividends in USD from both brokers

**USD disposed** (lots consumed LIFO within the disposal's account):
- EUR.USD conversions at IBKR (FlexQuery, asset_category=CASH)
- Wire transfers out (IBKR/Schwab, "Wire Sent" / "Wire Funds Sent")

**Formula per disposal:**
```
gain_eur = USD_amount × (1/ECB_rate_disposal - 1/ECB_rate_acquisition)
```

### Integration

- `compute_forex_gains()` takes ALL trades + ALL cash transactions (across
  all years) to build the per-account LIFO queues. Reports gains only for
  disposals within the tax year.
- `quadro_rt.py` always skips forex trades (broker P/L is useless).
- `forex_gains_to_rt_lines()` converts `ForexGainEntry` to `RTLine` with
  `is_forex=True`. `cli.py` appends these to the RT section when the
  forex threshold is breached.
- `statement_store.load_for_year()` loads ALL cash txns (no year filter)
  because the per-account LIFO queues need the full history for the
  carry-over balance.

### Cross-account giroconti (not yet matched)

A same-currency wire between two accounts of the same taxpayer is
fiscally neutral (Risoluzione AdE 60/E/2024). Decaf does not yet pair
"Wire Sent" from broker A with "Wire Received" on broker B: today the
outbound wire triggers an LIFO disposal and the inbound wire creates a
fresh acquisition at the wire-day rate, producing artificial gains.
Document as limitation; users must correct manually.

## Environment Notes

- Tested on Linux ARM (Raspberry Pi) and should work on any Linux/macOS
- Schwab OAuth needs SSH tunnel if running headless (`ssh -L 8182:127.0.0.1:8182`)
- Python 3.12+, .venv in project root
- poppler-utils required for pdftotext
- Credentials go in .env (gitignored): IBKR_TOKEN, IBKR_QUERY_ID,
  SCHWAB_APP_KEY, SCHWAB_SECRET
