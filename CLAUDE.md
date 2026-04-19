# decaf

Italian tax report generator for foreign investments. Modello Redditi PF.

## Architecture

Two-phase CLI: `decaf load` (broker data -> SQLite) + `decaf report` (SQLite -> output).
Full architecture with Mermaid diagrams: [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md).

```
src/decaf/
  cli.py                CLI with load/report subcommands
  parse.py              IBKR FlexQuery XML -> ParsedData
  schwab_parse.py       Schwab 3-file orchestrator -> ParsedData
  schwab_gains_pdf.py   Year-End Summary PDF -> RealizedLot (per-lot gains)
  schwab_vest_pdf.py    Annual Withholding PDF -> vest FMV per date
  statement_store.py    SQLite storage (deduplicating, idempotent)
  ecb_cache.py          ECB rate cache (SQLite)
  fx.py                 FX service (ECB primary, IB validation)
  prices.py             Year-end mark prices (yfinance)
  forex.py              Forex threshold analysis
  forex_gains.py        Forex LIFO gains per account (USD lot tracker)
  quadro_rw.py          IVAFE computation
  quadro_rt.py          Capital gains (stocks only; forex via forex_gains)
  quadro_rl.py          Interest + dividends + WHT
  output_cli.py         Rich terminal tables
  output_xls/pdf/json   File outputs
  models.py             Domain dataclasses
  holidays.py           Italian business days
  schwab_auth.py        OAuth2 (kept for future API use)
  schwab_client.py      Trader API client (kept for future API use)
```

## Key Decisions

- **Stock RT uses the cost basis on the actual lot sold.** Circ. AdE 165/E/1998 §2.3.2 mandates no FIFO/LIFO on partecipazioni: base imponibile = corrispettivo − costo effettivo di acquisto del lotto ceduto, documentato. Modern brokers track every lot and let the account holder choose which to sell (Schwab Tax Optimizer, IBKR matching method). Broker reports P/L on the chosen lot. This is the correct method, not a simplification. See doc/NORMATIVA.md §Metodo di determinazione del costo per le partecipazioni.
- **Forex LIFO per account: yes.** Valute are fungible, specific identification isn't possible. Art. 67 c. 1-bis TUIR + circ. 165/E §2.3.2 + risposta AdE 204/2023 mandate LIFO per singolo conto. Decaf computes it (brokers don't provide forex P/L). See doc/INTERNALS.md.
- **ECB rates primary.** Cambio BCE per AdE. IB rates for validation only.
- **Schwab API is broken** for EAC accounts. Use three PDF+JSON files instead. See doc/INTERNALS.md.
- **Decimal everywhere.** Never float for money. Architecture tests enforce this.
- **Settlement dates for IVAFE, trade dates for RT.**

## Running

```bash
source .venv/bin/activate
scripts/lint.sh                           # ruff + pyright
scripts/test.sh                           # 200 tests (includes e2e against reference data)
python -m decaf load                      # IBKR
python -m decaf load --broker schwab ...  # Schwab (see README.md)
python -m decaf report --year 2025        # Generate report
```

Pre-commit hook enforces ruff + pyright + tests on every commit.

## Collaboration

- **Bite-sized commits.** One logical change per commit. Don't batch unrelated
  work into a single commit, even if cli.py or a shared file hosts both.
  Use `git add -p` to split hunks when needed.

## Releases

Package is published to PyPI as `decaf-tax`. Full recipe in README § Sviluppo § Rilasciare una nuova versione. Non-obvious constraint:

- **README jsdelivr URLs must be pinned to the release tag** (`@vX.Y.Z`, not `@master`). jsdelivr caches the `@master` ref for 7 days, so a PyPI release shipped with `@master` URLs will render a stale manual/cover/examples on the project page for up to a week after push. The release `sed` in the README recipe does the pin automatically — never skip it.

## Documentation

| Doc | Language | Content |
|-----|----------|---------|
| [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md) | English | Data flow, module boundaries, type system, testing |
| [doc/GUIDA_FISCALE.md](doc/GUIDA_FISCALE.md) | Italian | How to fill the dichiarazione from decaf output |
| [doc/NORMATIVA.md](doc/NORMATIVA.md) | Italian | Tax law references with Gazzetta Ufficiale links |
| [doc/INTERNALS.md](doc/INTERNALS.md) | English | Implementation gotchas, broker quirks |
| [doc/QUERY_SETUP.md](doc/QUERY_SETUP.md) | English | IBKR Flex Query configuration |
| [doc/BACKTEST.md](doc/BACKTEST.md) | Italian | Backtesting workflow, fixture layout, prices.yaml |

## Forex LIFO Gains (per account)

Implemented in `forex_gains.py`. LIFO tracker keyed by `account_id`:
USD acquired from stock sells/dividends/interest enter their own
account's queue, disposed via EUR.USD conversions and wire transfers
consume the most-recently-acquired lot of the **same** account first.
Lots never cross accounts. `quadro_rt.py` always skips forex trades;
`forex_gains_to_rt_lines()` converts LIFO gains to RT lines when
threshold breached. Full details in doc/INTERNALS.md.
