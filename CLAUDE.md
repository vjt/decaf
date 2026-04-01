# decaf

De-CAF: Generatore di report fiscale italiano per investimenti esteri.
Niente commercialista. Produce Quadro RW (IVAFE), RT (plusvalenze),
RL (redditi di capitale), e analisi soglia valutaria per il Modello
Redditi PF.

## Architettura

Tre repo, una responsabilità ciascuna:

- `vendor/ibkr-flex-client/` — Client async IBKR Flex Web Service (submodule)
- `vendor/ecb-fx-rates/` — Client async tassi BCE (submodule)
- `src/decaf/` — Calcolo fiscale, parsing, output

```
CLI (cli.py) — due sottocomandi:

  decaf fetch [--broker ibkr|schwab] [--file ...] [--gains-pdfs ...] [--vest-pdfs ...]
    │
    ├─ IBKR: FlexClient API o file XML
    │   └─ parse.py → parse_statement_all() → ParsedData
    │
    ├─ Schwab: tre sorgenti PDF+JSON
    │   ├─ schwab_gains_pdf.py → Year-End Summary (plusvalenze realizzate)
    │   ├─ schwab_vest_pdf.py  → Annual Withholding (FMV ai vest per IVAFE)
    │   └─ schwab_parse.py     → Transaction JSON (dividendi + WHT)
    │
    └─ statement_store.py → SQLite (~/.cache/decaf/statements.db)
        + ecb_cache.py → tassi BCE in SQLite

  decaf report --year YYYY [--output-dir ...]
    │
    ├─ statement_store.py → carica dati da SQLite
    ├─ ecb_cache.py → tassi BCE (tutti gli anni delle operazioni)
    ├─ fx.py → servizio FX (BCE primario, IB validazione)
    ├─ calcolo:
    │   ├─ forex.py     → analisi soglia valutaria (art. 67(1)(c-ter) TUIR)
    │   ├─ quadro_rw.py → IVAFE per lotto (0.2% titoli, €34.20 depositi)
    │   ├─ quadro_rt.py → plusvalenze (broker FIFO per IBKR, PDF per Schwab)
    │   └─ quadro_rl.py → interessi + ritenute
    └─ output: output_cli.py (rich), output_json.py, output_xls.py, output_pdf.py
```

## Broker Supportati

### Interactive Brokers (IBKR Ireland)
- **Sorgente dati**: Flex Query API (XML) o file locale
- **Plusvalenze**: fidiamo il FIFO di IB (`fifoPnlRealized`)
- **Posizioni**: modalità "Lot" per date di apertura per-lotto
- **Dati FX**: IB ConversionRates (validazione vs BCE)

### Charles Schwab (account EAC / Stock Plan)
- **Sorgente dati**: TRE file (l'API Trader non funziona per account EAC)
  1. `Year-End Summary PDF` → plusvalenze realizzate per lotto (RT)
  2. `Annual Withholding Statement PDF` → FMV ai vest per giurisdizione ITA (RW)
  3. `Transaction JSON export` → dividendi + NRA Tax Adj (RL)
- **Plusvalenze**: dal PDF Year-End Summary (costo esatto per lotto da Schwab)
- **NO FIFO nostro**: Schwab fornisce il costo per lotto, non indoviniamo
- **FMV vest**: dal PDF Withholding, giurisdizione ITA (non IRL)
- **API Trader**: funziona solo per posizioni live, NON per transazioni (bug noto per account EAC)
- **OAuth2**: schwab_auth.py + schwab_client.py restano nel codebase per future API fix

## Decisioni di Design

- **Dati broker = verità.** Per IBKR fidiamo fifoPnlRealized. Per Schwab
  usiamo il Year-End Summary. Non reimplementiamo FIFO per le azioni.
- **FIFO forex: sì.** L'unico FIFO che dobbiamo calcolare noi è sulle
  conversioni valutarie (EUR.USD). I broker non forniscono il P/L forex.
  **QUESTO È IL PROSSIMO MODULO DA COSTRUIRE** (vedi sezione sotto).
- **Tassi BCE sono primari.** Cambio BCE è quello che l'AdE si aspetta.
  Tassi IB usati solo per validazione. Flag se discrepanza > 0.5%.
- **Tipi corretti ovunque.** Frozen dataclasses, Decimal per importi,
  niente tuple grezze.
- **Date di regolamento per IVAFE, date operazione per RT.**
- **Modelli broker-agnostici.** Trade, OpenPositionLot, CashTransaction
  sono generici — ogni broker ha il suo parser che normalizza.

## Prossimo Lavoro: FIFO Forex

**Stato**: soglia valutaria SUPERATA (28 giorni consecutivi nel 2025).
Le plusvalenze da conversione valutaria sono tassabili al 26%.

**Problema**: né IBKR né Schwab forniscono il P/L sulle conversioni forex.
I trade EUR.USD di IBKR hanno `broker_pnl_realized = 0`. I bonifici
"FX WIRE OUT" di Schwab non sono nemmeno modellati come trade.

**Soluzione**: modulo `forex_gains.py` che:
1. Traccia quando USD viene acquisito (vendite azioni, interessi, dividendi)
   con il tasso BCE alla data di acquisizione
2. Traccia quando USD viene ceduto (conversioni EUR.USD su IBKR, bonifici
   wire da Schwab)
3. Calcola: `plusvalenza = importo_USD × (1/tasso_BCE_cessione - 1/tasso_BCE_acquisizione)`
4. FIFO sui lotti di valuta

**Dati disponibili**:
- Vendite META (Schwab Year-End Summary) → USD acquisito, date esatte
- Interessi/dividendi USD → USD acquisito
- Conversioni EUR.USD (IBKR FlexQuery, 13 trade nel 2025) → USD ceduto
- Bonifici "FX WIRE OUT" (Schwab JSON) → USD ceduto
- Tassi BCE per tutti gli anni in cache SQLite

## Stack Tecnico

- Python 3.12+, async (aiohttp) per I/O, sync per calcoli
- SQLite: statements.db (dati broker) + ecb_rates.db (tassi BCE)
- pdftotext (poppler-utils) per parsing PDF Schwab
- openpyxl per Excel, fpdf2 per PDF, rich per output terminale
- Decimal per tutti gli importi (mai float)
- stdlib xml.etree.ElementTree per XML IBKR

## Standard Ingegneristici

- I submodule sono librerie OSS standalone — zero dipendenze da decaf
- Tutti i dati di test sono sintetici — niente dati reali nel repo
- Secrets (.env, token, password) sono in .gitignore
- File di output (.json, .xlsx, .pdf, .xml) sono in .gitignore
- PDF Schwab (dati personali) sono in .gitignore

## Esecuzione Test

```bash
source .venv/bin/activate
pytest tests/ -x -v --rootdir=.
```

80 test: holidays, XML parsing, FX service, forex threshold, statement store,
CUSIP→ISIN, Schwab gains PDF, modelli RealizedLot.

## Uso

```bash
# Carica dati IBKR (da API, token in .env)
python -m decaf fetch

# Carica dati IBKR (da file XML)
python -m decaf fetch --file flexquery.xml

# Carica dati Schwab (tre sorgenti)
python -m decaf fetch --broker schwab \
  --file transactions.json \
  --gains-pdfs "Year-End Summary*.PDF" \
  --vest-pdfs "Annual Withholding*.PDF"

# Genera report per anno fiscale
python -m decaf report --year 2025 --output-dir output/
```

## Configurazione Flex Query IBKR

Vedi doc/QUERY_SETUP.md. Critico: Open Positions deve usare
modalità **Lot** (non Summary) per avere date apertura per-lotto per IVAFE.
