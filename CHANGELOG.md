# Changelog

Formato ispirato a [Keep a Changelog](https://keepachangelog.com/it-IT/1.1.0/).
Versioning [SemVer](https://semver.org/lang/it/).

## [Unreleased]

### Added

- **Matching automatico dei giroconti cross-broker in USD** (Ris. AdE 60/E del 09/12/2024). Un `Wire Sent` o `Wire Funds Sent` o `Deposits/Withdrawals` negativo su un conto abbinato a un `Deposits/Withdrawals` positivo su un altro conto, con stesso importo (tolleranza 0,01 USD) e settle date entro ±3 giorni lavorativi, viene ora riconosciuto come giroconto fiscalmente neutro: i lotti USD migrano dalla coda LIFO del conto di origine a quella di destinazione cronologicamente, preservando data di acquisizione e cambio BCE originali, senza generare plusvalenze/minusvalenze artificiali sulla data del giroconto. Casi ambigui (piu' candidati positivi) vengono loggati e cadono sul trattamento precedente (wire-out = cessione); la rettifica manuale resta a carico del contribuente in quei casi.
- `tests/reference/mascetti/ibkr_flex_2025.xml`: aggiunto un `Deposits/Withdrawals +2400.00 USD` su IBKR accoppiato al wire out Schwab di $2400 gia' esistente, per coprire end-to-end lo scenario Ris. 60/E nel backtest. L'oracolo `decaf_2025.yaml` e' stato rigenerato: scompare la plusvalenza valutaria artificiale di €1,78 che prima compariva per il wire del 10/25. `TestGirocontoMatching` in `tests/test_forex_gains.py` copre unit-level i 4 comportamenti chiave (coppia esatta, tolleranza ±3 biz days, ambiguita', preservazione data/rate del lotto).

### Changed

- `forex_gains.py`: nuovo evento interno `TRANSFER` + funzione `_match_giroconto_pairs()`. I `Deposits/Withdrawals` positivi in USD, prima ignorati dal collector, ora partecipano al matching. Il main loop di `compute_forex_gains` intercetta i TRANSFER pop-pando LIFO dalla coda di origine e inserendo via `bisect.insort` nella coda di destinazione.
- `doc/NORMATIVA.md §Giroconto cross-broker`: da "limitazione corrente" a "matching implementato" con descrizione della logica e del fallback.
- `doc/INTERNALS.md §Cross-account giroconti`: aggiornato per descrivere l'implementazione (source queue LIFO pop + chronological insort nella dest queue).
- `README.md §Limitazioni note`: rimossa la riga "Giroconto cross-broker in USD". Restano 4 limitazioni note (obbligazioni, art. 9 c. 2, IVAFE black-list, data assegnazione RT).

## [0.2.0] — 2026-04-19

### Changed

- **Breaking CLI.** Sottocomando `decaf fetch` rinominato in `decaf load`. Il vecchio nome sottintendeva una chiamata di rete, ma il comando gestisce anche import da file locali (FlexQuery XML, Schwab 3-file). `load` descrive meglio cosa fa: carica dati nel database locale, indipendentemente dalla sorgente. Nessun fallback sul vecchio nome — script esistenti vanno aggiornati.
- **Forex gains: da FIFO unificato a LIFO per singolo conto.** Il modulo `forex_gains.py` ora tiene una coda LIFO separata per ciascun `account_id`. Acquisizioni USD (vendite titoli, dividendi, interessi, forex buy) entrano nella coda del conto proprio; disposizioni (forex sell, bonifici) consumano dalla coda dello stesso conto, prima il lotto più recente. Base normativa verificata verbatim: art. 67 c. 1-bis TUIR ("cedute per prime le valute acquisite in data più recente") e risposta AdE 204/2023 ("analiticamente e distintamente, per ciascun conto"). Per l'utente con soglia valutaria mai sforata nell'anno, il cambio non produce differenze numeriche sul filed; per chi supera la soglia i numeri possono cambiare.

### Added

- **Documentazione normativa espansa con citazioni verbatim da fonti primarie:**
  - Circ. AdE 165/E/1998 §2.3.2 — trattamento differenziato partecipazioni (costo effettivo del lotto ceduto, nessun LIFO), valute (LIFO mandatorio), titoli non partecipativi (LIFO mandatorio).
  - Risposta AdE 204/2023 — calcolo forex "analiticamente e distintamente, per ciascun conto" + chiarimento che l'aggregazione cross-account opera solo sulla soglia ex art. 67 c. 1-ter, non sulla determinazione delle plusvalenze.
  - Risoluzione AdE 60/E del 09/12/2024 — giroconto stessa valuta tra conti dello stesso soggetto non integra cessione ex art. 67(1)(c-ter), fiscalmente neutro (limitazione nota: decaf non matcha ancora giroconti cross-broker).
  - L. 213/2023 art. 1 c. 91 — aliquota IVAFE 0,4% per attività in Stati a fiscalità privilegiata dal periodo d'imposta 2024.
- Sezione `doc/NORMATIVA.md §Redditi di capitale esteri — Quadro RL vs Quadro RM` con routing esplicito RM12 (sostitutiva 26%, no credito) vs RL + CE (IRPEF ordinario + art. 165 credito), mutuamente esclusivi per contribuente e rigo.
- Sezione `doc/NORMATIVA.md §Semplificazioni applicate` che documenta con esempio numerico lo scostamento della conversione ECB aggregata al trade date vs. la conversione per-lotto prescritta da art. 9 c. 2 TUIR. Fix previsto per v0.3.0.

### Changed (documentation)

- `doc/NORMATIVA.md §Quadro RT`: riscritto in `§Metodo di determinazione del costo per le partecipazioni` con citazioni verbatim di §2.3.2. La scelta di usare il P/L del broker per i titoli non è più descritta come "semplificazione" — è il metodo prescritto da §2.3.2 (base imponibile = corrispettivo − costo effettivo del lotto ceduto, specific identification accettata).
- `doc/NORMATIVA.md`, `doc/GUIDA_FISCALE.md`, `doc/INTERNALS.md`, `doc/ARCHITECTURE.md`, `doc/BACKTEST.md`, `CLAUDE.md`, `README.md`, `examples/README.md`: allineamento linguaggio forex (FIFO unificato → LIFO per conto) e RT (trust broker FIFO → §2.3.2).
- Test suite aggiornata con `TestPerAccountIsolation` (3 nuovi test): le code forex non si attraversano tra conti broker diversi.

### Fixed

- `doc/NORMATIVA.md §Risoluzione 60/E`: citazione invertita (era "integra cessione"; la risoluzione dice il contrario).
- Residui "FIFO" stantii in contesto forex ripuliti da docs e README dopo il passaggio a LIFO.

## [0.1.3] — 2026-04-18

### Fixed

- URL jsdelivr nel README pinnate al tag di release (`@v0.1.3` invece di `@master`). Così la pagina PyPI mostra sempre asset — manuale incluso — coerenti con la versione installata, senza la staleness della cache a 7 giorni del ref `@master`.

### Changed

- Ricetta release in `README.md § Sviluppo § Rilasciare una nuova versione` aggiornata con il bump automatico delle URL jsdelivr via `sed`, così la prossima release non dimentica di pinnare.

## [0.1.2] — 2026-04-18

### Changed

- Tutti gli asset statici servono da jsdelivr CDN (immagini, PDF, xlsx, yaml). Header `Content-Type` corretti + nessun `Content-Disposition: attachment` → mobile renderizza i PDF inline.
- Manuale PDF ora include un capitolo "Uso del software" estratto dal README (installazione + primo utilizzo + esempi) e una titlepage con logo + cover illustration.
- Tabella "File di Output" ribilanciata: colonna Uso più larga, colonna Esempio compatta.

### Fixed

- Link relativi nel README (`doc/BACKTEST.md`, `examples/`, `tests/reference/`) sostituiti con URL assoluti `https://github.com/vjt/decaf/...` così funzionano anche sulla pagina PyPI.

## [0.1.1] — 2026-04-18

### Fixed

- README usa URL assoluti (`raw.githubusercontent.com`) per logo e cover, così le immagini si vedono anche sulla pagina PyPI — PyPI non risolve i path relativi al repo.

## [0.1.0] — 2026-04-18

Prima release **open-source**. [Repo pubblico su GitHub](https://github.com/vjt/decaf), pacchetto [`decaf-tax` su PyPI](https://pypi.org/project/decaf-tax/) (`pip install decaf-tax`), vendor deps su PyPI, fixture + esempi committati, documentazione estesa.

### Added

- `./decaf.sh` launcher con gestione automatica `.venv/` e refresh dipendenze su cambio `pyproject.toml` (utile dopo `git pull`).
- `decaf backtest <dir>` + guida completa in [doc/BACKTEST.md](doc/BACKTEST.md). Output YAML diffabile come oracolo, `prices.yaml` per pinnare i prezzi di fine anno (sia anno corrente sia precedente per IVAFE pro-rata).
- Tre fixture sintetiche in `tests/reference/` coperte da `tests/test_e2e.py`:
  - `magnotta/` — IBKR-only, caso base (dedicato a [Mario Magnotta](https://it.wikipedia.org/wiki/Mario_Magnotta))
  - `mosconi/` — IBKR + Schwab, stesso ticker (SBTP) detenuto a due broker (dedicato a [Germano Mosconi](https://it.wikipedia.org/wiki/Germano_Mosconi))
  - `mascetti/` — stress test: soglia forex superata 2 anni, FIFO multi-lotto, 4 ritenute estere diverse (Conte Mascetti da [*Amici Miei*](https://it.wikipedia.org/wiki/Amici_miei))
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
