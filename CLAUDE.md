# decaf

Italian tax report generator for foreign investments. Modello Redditi PF.

## Architecture

Two-phase CLI: `decaf fetch` (load data → SQLite) + `decaf report` (SQLite → output).

```
src/decaf/
  cli.py                CLI with fetch/report subcommands
  parse.py              IBKR FlexQuery XML → ParsedData
  schwab_parse.py       Schwab 3-file orchestrator → ParsedData
  schwab_gains_pdf.py   Year-End Summary PDF → RealizedLot (per-lot gains)
  schwab_vest_pdf.py    Annual Withholding PDF → vest FMV per date
  statement_store.py    SQLite storage (deduplicating, idempotent)
  ecb_cache.py          ECB rate cache (SQLite)
  fx.py                 FX service (ECB primary, IB validation)
  forex.py              Forex threshold analysis
  forex_gains.py        Forex FIFO gains (USD lot tracker)
  quadro_rw.py          IVAFE computation
  quadro_rt.py          Capital gains (stocks only; forex via forex_gains)
  quadro_rl.py          Interest + WHT
  output_cli.py         Rich terminal tables
  output_xls/pdf/json   File outputs
  models.py             Domain dataclasses
  holidays.py           Italian business days
  schwab_auth.py        OAuth2 (kept for future API use)
  schwab_client.py      Trader API client (kept for future API use)
```

## Key Decisions

- **Trust broker data.** IBKR fifoPnlRealized, Schwab Year-End Summary cost basis. No stock FIFO reimplementation.
- **Forex FIFO: yes.** The one FIFO we must compute — brokers don't provide forex P/L. See doc/INTERNALS.md.
- **ECB rates primary.** Cambio BCE per AdE. IB rates for validation only.
- **Schwab API is broken** for EAC accounts. Use three PDF+JSON files instead. See doc/INTERNALS.md.
- **Decimal everywhere.** Never float for money.
- **Settlement dates for IVAFE, trade dates for RT.**

## Running

```bash
source .venv/bin/activate
pytest tests/ -x -v --rootdir=.          # 99 tests
python -m decaf fetch                     # IBKR
python -m decaf fetch --broker schwab ... # Schwab (see README.md)
python -m decaf report --year 2025        # Generate report
```

## Forex FIFO Gains

Implemented in `forex_gains.py`. Threshold breached in 2025 (28 days).
FIFO tracker: USD acquired from stock sells/dividends/interest, disposed
via EUR.USD conversions and wire transfers. `quadro_rt.py` always skips
forex trades; `cli.py` adds FIFO-computed gains as RT lines when threshold
breached. Full details in doc/INTERNALS.md.
