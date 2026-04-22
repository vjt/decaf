# Changelog

Formato ispirato a [Keep a Changelog](https://keepachangelog.com/it-IT/1.1.0/).
Versioning [SemVer](https://semver.org/lang/it/).

## [Unreleased]

## [0.3.6] — 2026-04-22

### Fixed

- **`__version__` drift**: `src/decaf/__init__.py` portava `"0.1.0"` hardcoded dal primo commit, mai aggiornato durante i release cycle. Tutti i PDF generati da `decaf report` mostravano `decaf v0.1.0` nel footer anziche' la versione installata effettiva. Ora letto via `importlib.metadata.version("decaf-tax")` — sincronia automatica con `pyproject.toml`. Fallback a `0.0.0+src` quando il pacchetto non e' nel site-packages (sviluppo senza editable install).

### Added

- **Footer PDF con link cliccabile al repo**: i PDF generati riportano in footer "Generato da decaf vX.Y.Z | YYYY-MM-DD | Pagina N/M", dove `decaf vX.Y.Z` e' reso come hyperlink cliccabile a `https://github.com/vjt/decaf` — stesso blu degli header (RGB 31/56/100) + testo sottolineato, cosi' appare inequivocabilmente come link. Utile per trasparenza metodologica: chi riceve il PDF (commercialista, AdE in eventuale accertamento) puo' atterrare direttamente sul repo per CHANGELOG, `doc/NORMATIVA.md` e sorgenti.

## [0.3.5] — 2026-04-22

### Added

- **Controllo coerenza RSU nel report.** Ogni `decaf report` ora stampa (CLI) e include (YAML, XLSX, PDF) il totale del reddito RSU tassato nell'anno — sum(ITA FMV x net shares) convertito al cambio BCE del giorno di vest. Nuovi campi `TaxReport.rsu_vest_count` e `TaxReport.rsu_income_eur`. L'utente puo' cross-checkare contro il punto 1 della Certificazione Unica "Redditi di lavoro dipendente" per sanity-check: il numero decaf deve essere un sottoinsieme del totale CU (differenza = stipendio + bonus). Se non combacia, c'e' qualcosa di sbagliato nella lettura dell'Annual Withholding Statement Schwab (es. fallback IRL per vest con ITA mancante). Feature nata dal debug del fix cost basis RSU 0.3.4 per rendere verificabile a posteriori che i numeri usati da decaf combacino col tassato dichiarato dal datore di lavoro.
- Euristica identificazione vest Schwab: trade BUY in USD con `fx_rate_to_base == 0` e `commission == 0` e `broker_pnl_realized == 0` — mirrors `schwab_parse._parse_vest`. Trade IBKR (acquisti cash) portano fx_rate_to_base e commission non-zero e vengono esclusi, cosi' la somma resta specifica delle RSU.

## [0.3.4] — 2026-04-22

### Thanks

- **#thanks a Giacomo Ferroni** ([@mralgos](https://github.com/mralgos)) per aver segnalato il bug e portato avanti le verifiche che hanno permesso di fixarlo. La sua analisi puntava il dito esattamente sul punto del codice dove il bug risiedeva (`schwab_parse.py:186`, `cost=-lot.cost_basis` che legge il W-2 US basis invece del Valore Normale). Senza il suo cross-check sistematico l'errore sarebbe rimasto latente — non mi era saltato all'occhio, è visibile solo mettendo a confronto per molti lotti la colonna del Year-End Summary con la colonna ITA FMV dell'Annual Withholding Statement.

### Fixed

- **Schwab RSU: cost basis RT ora usa il Valore Normale invece del W-2 USA.** `src/decaf/schwab_parse.py` sostituisce il `cost_basis` riportato sullo Year-End Summary — che per le RSU e' il Fair Market Value del giorno di vest, base fiscale W-2 americana — con `quantity x ITA FMV` letto dall'Annual Withholding Statement quando `RealizedLot.date_acquired` corrisponde (±3 giorni) a un vest date noto. Il Valore Normale ex art. 9 c. 4 lett. a) TUIR (media aritmetica dei prezzi di chiusura del mese terminante il giorno di borsa precedente al vest) e' il valore tassato come reddito di lavoro dipendente sulla CU e, ex art. 68 c. 6 TUIR, il costo fiscalmente riconosciuto per il calcolo di plus/minusvalenze RT. Usare il W-2 USA al posto del Valore Normale sottostima le plusvalenze (o fabbrica minusvalenze) su titoli in uptrend nel mese precedente al vest — problema macroscopico su chi ha RSU di Big Tech US con vest 2024 su titolo in forte salita. **Chi ha depositato dichiarazioni passate con output di decaf < 0.3.4 deve ricontrollare il Quadro RT sulle vendite di RSU**: la plusvalenza corretta e' tipicamente piu' alta di quella emessa dalle versioni precedenti. Il campo `broker_pnl` della RTLine conserva il P/L originale Schwab (W-2 USA) come colonna di riconciliazione; `gain_loss_eur` e' calcolato sul Valore Normale convertito al cambio BCE della data di acquisto ex art. 9 c. 2. Lotti senza match (azioni comprate in contanti) mantengono il cost basis originale del broker.
- `doc/NORMATIVA.md`: aggiunta sezione "Costo fiscalmente riconosciuto per RSU — art. 68 co. 6 + art. 9 co. 4 TUIR" con lettera integrale di entrambi gli articoli e descrizione dell'algoritmo di sostituzione. Tabella riepilogativa aggiornata.
- `README.md §Limitazioni note`: documentato che la sostituzione opera solo per RSU su Schwab (dove l'Annual Withholding Statement espone l'ITA FMV). Per RSU trasferite Schwab -> IBKR decaf continua a usare `Lot@cost` IBKR, che eredita il basis W-2 USA; chi ha eseguito quel trasferimento deve rettificare manualmente.
- Fixture `tests/reference/mascetti`: cost_basis YES aggiornato a US FMV (ITA + $2/sh) per esercitare la sostituzione; oracoli rigenerati — `broker_pnl`/`broker_pnl_eur` riflettono i nuovi numeri broker, `cost_basis_eur`/`gain_loss_eur` restano invariati perche' decaf usa ora il Valore Normale.

## [0.3.3] — 2026-04-19

### Fixed

- **Manuale PDF**: link interni ora funzionano su Safari iOS / Apple PDFKit. Pandoc + hyperref emettono `/GoTo` con destinazioni nominate stringa (`section.2.3`) sotto `/Root/Names/Dests` — alcune versioni di PDFKit rispondono con "address invalid" al tap su link di questo tipo. Nuovo post-processor `scripts/pdf_flatten_dests.py` risolve tutte le destinazioni nominate verso array espliciti `[page_ref /XYZ x y zoom]`, che sono supportati senza ambiguità da tutti i viewer.
- **Manuale PDF**: link a `../README.md` e `../CLAUDE.md` dal sommario documentazione in `doc/GUIDA_FISCALE.md` non sono più URI invalidi nel PDF. `rewrite_cross_refs` in `scripts/manual.sh` ora intercetta anche il prefisso `../` e manda README al capitolo "Uso del software"; i rimanenti `../<FILE>.md` diventano URL GitHub cliccabili (CLAUDE.md non fa parte del manuale).

## [0.3.2] — 2026-04-19

### Changed

- `README.md`: aggiunto paragrafo **Quickstart solo Schwab (RSU) — 5 minuti** in testa a *Primo utilizzo*. Flusso mirato per dipendenti italiani di multinazionali con solo conto Stock Plan (i tipici "Meta / Google / Apple RSU holders"): tre file da scaricare da schwab.com, due comandi (`decaf load --broker schwab ...` + `decaf report`), nessuna Flex Query da configurare. Il flusso generico multi-broker resta subito sotto. Pull-in automatico nel manuale PDF tramite `scripts/manual.sh`.
- `doc/decaf_manual.pdf`: rigenerato per includere il nuovo quickstart e la versione aggiornata.

## [0.3.1] — 2026-04-19

### Changed

- **Conversione plusvalenze titoli per-lotto al cambio BCE (art. 9 c. 2 TUIR).** `quadro_rt.py` ora converte il costo di ciascun lotto ceduto al cambio BCE della data di *acquisto del lotto* e il corrispettivo al cambio BCE della data di *regolamento*, calcolando la plusvalenza EUR come differenza. La precedente implementazione convertiva il P/L aggregato del broker con un unico tasso (quello della data di vendita), producendo uno scostamento rispetto alla lettera dell'art. 9 c. 2 sui lotti con detenzione a cavallo di anni con cambio variato. Per gli utenti con vendite di lotti pluriennali i numeri filed cambiano — divergenza attesa e corretta.
- **IBKR Flex Query: richiesta obbligatoria la sezione Closed Lots (solo SELL azionari).** `parse.py` si aspetta elementi `<Lot>` come fratelli del `<Trade>` SELL con `assetCategory="STK"` (struttura reale Flex Query v3, openDateTime sul lotto = acquisition date). Se la Flex Query non ha Closed Lots abilitati, il parser solleva errore con puntatore a `doc/QUERY_SETUP.md` anziché ricadere silenziosamente sull'aggregato. Le SELL in CASH (conversioni forex EUR.USD) non richiedono Lots — passano direttamente a `forex_gains.py`. Per Schwab il dato per-lotto era già disponibile dallo Year-End Summary.
- **Data di assegnazione al periodo d'imposta (RT): ora settle date.** `quadro_rt.py` assegna la vendita all'anno fiscale in base alla data di regolamento (`settle_date.year`) anziché alla data di esecuzione (`trade_datetime.year`). Momento impositivo ex art. 68 TUIR. Impatto solo sulle vendite a cavallo d'anno.
- **Pro-rata commissioni IBKR sui Closed Lot.** Quando un SELL ha più lotti, la `ibCommission` del parent `<Trade>` viene distribuita pro-quantità tra i Trade per-lotto emessi dal parser; l'ultimo lotto assorbe il residuo Decimal così `sum(lot.commission) == parent.commission` esatto. Prima la commissione veniva azzerata su ogni per-lotto, producendo un drift sul saldo USD tracciato da `forex_gains.py` (i.e. `proceeds + commission`) pari alla somma annuale delle commissioni (ordine di grandezza: pochi dollari/anno).
- `doc/QUERY_SETUP.md`: aggiunta la checkbox Closed Lots + il campo Open Date Time nella lista campi della sezione Trades. Screenshot aggiornato. Traduzione in italiano.
- `doc/NORMATIVA.md §Metodo di determinazione del costo`: aggiunta §Conversione per-lotto (art. 9 co. 2 TUIR) che descrive il funzionamento attuale. Rimossa §Semplificazioni applicate (nessuna semplificazione residua).
- `README.md §Limitazioni note`: rimosse le righe "Conversione plusvalenze titoli" (art. 9 c. 2 — fix) e "Data di assegnazione RT" (fix). Restano 2 limitazioni note (obbligazioni fuori scope, IVAFE 0,4% black-list).
- Fixture `tests/reference/{magnotta,mosconi,mascetti}`: aggiunti `<Lot>` siblings per ogni SELL, inclusi scenari cross-anno (mascetti SPKZ 2025, MSCT 2025). Oracoli rigenerati con conversione per-lotto.

## [0.3.0] — 2026-04-19

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
