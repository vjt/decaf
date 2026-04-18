# Changelog

Formato ispirato a [Keep a Changelog](https://keepachangelog.com/it-IT/1.1.0/).
Versioning [SemVer](https://semver.org/lang/it/).

## [Unreleased]

## [0.1.0] — 2026-04-18

Prima release **open-source**. Repo pubblicato su GitHub, vendor deps su PyPI, fixture + esempi committati, documentazione estesa.

### Added

- `./decaf.sh` launcher con gestione automatica `.venv/` e refresh dipendenze su cambio `pyproject.toml` (utile dopo `git pull`).
- `decaf backtest <dir>` + guida completa in [doc/BACKTEST.md](doc/BACKTEST.md). Output YAML diffabile come oracolo, `prices.yaml` per pinnare i prezzi di fine anno (sia anno corrente sia precedente per IVAFE pro-rata).
- Tre fixture sintetiche in `tests/reference/` coperte da `tests/test_e2e.py`:
  - `magnotta/` — IBKR-only, caso base (dedicato a [Mario Magnotta](https://it.wikipedia.org/wiki/Mario_Magnotta))
  - `mosconi/` — IBKR + Schwab, stesso ticker (SBTP) detenuto a due broker (dedicato a [Germano Mosconi](https://it.wikipedia.org/wiki/Germano_Mosconi))
  - `mascetti/` — stress test: soglia forex superata 2 anni, FIFO multi-lotto, 4 ritenute estere diverse (Conte Mascetti da *Amici Miei*)
- Showcase outputs pubblicati in `examples/<fixture>/decaf_<year>.{yaml,xlsx,pdf}`, rigenerabili con `scripts/gen_examples.py`.
- Colonna "Azienda" in xls + pdf con il nome esteso della società (campo `long_description` in `RWLine` / `RTLine`).
- Manuale PDF unificato in `doc/decaf_manual.pdf`, rigenerato dal pre-commit hook quando cambia `doc/`.
- Skill `.claude/skills/{start,close}` per onboarding di agenti su questo repo.

### Changed

- Vendor deps `ibkr-flex-client` e `ecb-fx-rates` pubblicate su PyPI (entrambe 0.1.0); `decaf` le consuma da PyPI di default, submodule solo per chi vuole modificarle.
- `yfinance.history(auto_adjust=False)`: i close storici non vengono più riscritti retroattivamente dai dividendi successivi — IVAFE di un anno chiuso resta stabile nel tempo.
- `price_overrides` in `_build_report` passa come singolo `dict[int, dict[str, Decimal]]` (anno → simbolo → prezzo), consultato sia per fine anno sia per fine anno precedente.
- README ristrutturato attorno al flusso `mkdir private/ → ./decaf.sh fetch → ./decaf.sh report`, con link prominenti al manuale e agli esempi.

### Fixed

- Prior-year price fetch ora rispetta `prices.yaml`: prima saltava il lookup solo per l'anno corrente, ora anche per l'anno precedente. Senza questo i ticker overridden cadevano su yfinance per l'anno N-1, sporcando l'IVAFE pro-rata.
- Pipeline pre-commit genera il manual PDF con filename stabile (`doc/decaf_manual.pdf` invece che dated).

### Security

- Scrub della history via `git filter-repo` per rimuovere real broker account IDs, codice fiscale e altri identificativi personali da blob storici.
- `.gitignore` cover aggressivo su `*.xml`, `*.pdf`, `*.xlsx`, `*.yaml`, `*.db`, `private/`, con whitelist esplicito per `tests/reference/`, `examples/`, `doc/`, `.claude/skills/`.
- Submodule URLs convertiti a HTTPS (no SSH key richiesta per clone pubblico).

## [0.0.1] — pre open-source

Core tax engine prima del rollout pubblico. Queste versioni non sono taggate; i commit fino a ~2026-04-17 coprono il lavoro interno originale.

### Added

- CLI bifase: `decaf fetch` (IBKR via Flex API o XML; Schwab via 3 file JSON + Year-End Summary PDF + Annual Withholding PDF) → SQLite locale; `decaf report --year N` → output Excel/PDF/YAML.
- Computazioni:
  - **Quadro RW + IVAFE**: 0.2% pro-rata su titoli, €34.20 fisso su depositi, lot slicing con vendita parziale.
  - **Quadro RT**: plusvalenze titoli (26%) dal P/L FIFO del broker, più FIFO forex USD→EUR sintetico quando superata la soglia valutaria.
  - **Quadro RL**: interessi + dividendi + ritenute estere con conversione EUR via tasso BCE.
  - **Soglia valutaria** art. 67(1)(c-ter) TUIR: ricostruzione saldo giornaliero USD, verifica 7+ giorni lavorativi consecutivi sopra €51.645,69.
- ECB rate cache locale (SQLite) per i cambi ufficiali AdE.
- Parser IBKR FlexQuery XML e Schwab PDF (via `pdftotext`).
- Modelli dominio in `pydantic v2` frozen.
- Test suite: ~100 unit test su holiday, XML parsing, FX, forex threshold, forex FIFO, statement store, Schwab PDF parsing.
