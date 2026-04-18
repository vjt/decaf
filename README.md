# decaf

**De-CAF** — Generatore di report fiscale per investimenti esteri. Niente commercialista.

Scarica i dati dai tuoi broker esteri e i tassi BCE, poi calcola tutto il necessario per il **Modello Redditi PF**:

- **Quadro RW** — Monitoraggio attività finanziarie estere + IVAFE
- **Quadro RT** — Plusvalenze di natura finanziaria (26%)
- **Quadro RL** — Redditi di capitale (interessi, dividendi, ritenute estere)
- **Soglia valutaria** — Analisi art. 67(1)(c-ter) TUIR

Output: tabelle colorate nel terminale, Excel (un foglio per quadro), PDF e YAML.

> ⚠️ **Disclaimer.** Questo strumento automatizza i calcoli ma **non sostituisce un commercialista**. Le leggi fiscali cambiano, i tuoi dati e la tua situazione sono tuoi — verifica sempre i numeri prima di firmare il Modello Redditi. Gli autori non si assumono responsabilità per errori, omissioni, o interpretazioni della normativa. Usalo come punto di partenza, non come oracolo.

## Broker Supportati

| Broker | Sorgente dati | Note |
|--------|--------------|------|
| **Interactive Brokers** (Irlanda) | Flex Query API o file XML | Automatico |
| **Charles Schwab** (account EAC/RSU) | 3 file: PDF Year-End Summary + PDF Withholding + JSON transazioni | Manuale da schwab.com |

## Installazione

```bash
git clone --recursive git@github.com:vjt/decaf.git
cd decaf
python3 -m venv .venv
source .venv/bin/activate
pip install -e vendor/ibkr-flex-client -e vendor/ecb-fx-rates -e ".[dev]"

# Serve anche poppler-utils per il parsing dei PDF Schwab
sudo apt install poppler-utils  # Debian/Ubuntu
brew install poppler             # macOS
```

## Uso

Il flusso è in due fasi: **carica dati** poi **genera report**.

### 1. Caricare i dati

I dati vengono salvati in un database SQLite locale (`~/.cache/decaf/`). I caricamenti sono idempotenti — puoi rieseguirli senza duplicare nulla.

#### IBKR

```bash
# Da API (token e query ID in .env o prompt interattivo)
python -m decaf fetch

# Da file XML scaricato
python -m decaf fetch --file flexquery.xml
```

Per configurare la Flex Query, vedi la [guida con screenshot](doc/QUERY_SETUP.md).

Credenziali in `.env` (gitignored):
```
IBKR_TOKEN=il_tuo_token
IBKR_QUERY_ID=il_tuo_query_id
```

#### Charles Schwab

Schwab richiede tre file, ognuno con dati diversi:

| File | Dove scaricarlo | Cosa contiene |
|------|----------------|---------------|
| **Transaction JSON** | schwab.com → Accounts → History → Export (JSON) | Dividendi, ritenute (RL), bonifici (forex FIFO) |
| **Year-End Summary PDF** | schwab.com → Statements → Tax Documents → Year-End Summary | Plusvalenze per lotto (RT) |
| **Annual Withholding PDF** | schwab.com → Equity Award Center → Documents | FMV al vest per IVAFE (RW) |

```bash
python -m decaf fetch --broker schwab \
  --file Individual_XXX123_Transactions_*.json \
  --gains-pdfs "Year-End Summary - *.PDF" \
  --vest-pdfs "Annual Withholding Statement_*.PDF"
```

### 2. Generare il report

```bash
# Report anno fiscale 2025
python -m decaf report --year 2025

# Con directory di output specifica
python -m decaf report --year 2025 --output-dir /tmp/decaf_2025
```

Il report mostra tabelle colorate nel terminale con i totali per quadro, le etichette ufficiali AdE, e i riferimenti normativi. Genera anche Excel, PDF e YAML.

## Bring Your Own Data — Backtesting

Il comando `decaf backtest <dir>` riesegue l'intera pipeline su una directory di file broker e confronta l'output con oracoli YAML committati. Utile per:

- verificare che un cambio di codice non alteri output storici;
- congelare i risultati dell'anno N come regressione per l'anno N+1;
- condividere casi di test senza toccare dati sensibili.

Ogni directory di fixture contiene file broker reali o sintetici + un `decaf_<year>.yaml` per anno:

```
tests/reference/mascetti/
├── ibkr_flex_2024.xml
├── ibkr_flex_2025.xml
├── Individual_XXX066_Transactions_*.json
├── Year-End Summary*.PDF
├── Annual Withholding*.PDF
├── prices.yaml           # opzionale — override mark prices
├── decaf_2024.yaml       # oracolo
└── decaf_2025.yaml
```

```bash
# Rigenera oracoli (uso iniziale o dopo modifiche volute)
python -m decaf backtest tests/reference/mascetti --update

# Verifica regressione (exit 0 = match, 1 = diff)
python -m decaf backtest tests/reference/mascetti
```

Il file opzionale `prices.yaml` permette di pinnare i prezzi di fine anno per simboli che yfinance non risolve (es. ticker sintetici in test) o che il broker non quota:

```yaml
2024:
  MSCT: 14.00
  SPKZ: 18.00
2025:
  ANTN: 6.00
```

### Fixture sintetiche incluse

| Fixture | Anni | Copertura |
|---------|------|-----------|
| `magnotta/` | 2024 | IBKR singolo, caso base — IVAFE pro-rata, loss RT, dividendo con ritenuta |
| `mosconi/` | 2023-2024 | IBKR + Schwab, FIFO su vendita parziale, RSU vest, multi-anno |
| `mascetti/` | 2024-2025 | Stress test — soglia forex superata 2 anni, FIFO multi-lotto, RSU multi-anno, dividendi con 4 ritenute diverse (US 30%, UK 0%, DE 26.375%, IT 26%) |

Tutti i nomi sono di personaggi immaginari (omaggi a Amici Miei e Germano Mosconi), IBAN/account IDs contengono `666` per distinguerli visivamente da account reali.

## File di Output

| File | Formato | Uso |
|------|---------|-----|
| `decaf_<year>.xlsx` | Excel | Un foglio per quadro + riepilogo |
| `decaf_<year>.pdf` | PDF | Prospetto con tabelle e totali |
| `decaf_<year>.yaml` | YAML | Dump completo del `TaxReport` — diffabile, stabile tra run |

## Come Funziona

1. **Fetch** — Scarica dati dal broker (API o file) e tassi BCE. Salva tutto in SQLite.
2. **Report** — Carica da SQLite, converte USD→EUR al cambio BCE, calcola:
   - **Soglia valutaria**: ricostruisce il saldo giornaliero in valuta estera, verifica 7+ giorni lavorativi consecutivi sopra €51.645,69
   - **IVAFE**: 0.2% annuo sul valore di mercato dei titoli (pro-rata per giorni), €34.20 fisso per depositi
   - **Plusvalenze titoli**: converte il P/L del broker in EUR al tasso BCE alla data di regolamento
   - **Plusvalenze valutarie**: se soglia superata, calcola i guadagni forex con FIFO sui lotti USD (acquisti da vendite titoli, dividendi, interessi → cessioni tramite conversioni EUR.USD e bonifici)
   - **Redditi di capitale**: abbina interessi lordi con ritenute estere
3. **Output** — Genera i file e il report terminale

## Regole Fiscali Implementate

| Regola | Riferimento | Implementazione |
|--------|------------|-----------------|
| IVAFE titoli | D.L. 201/2011, art. 19 | 0.2% su valore di mercato, pro-rata giorni |
| IVAFE depositi | D.L. 201/2011 | €34.20 fisso annuo |
| Plusvalenze titoli | Art. 67(1)(c-bis) TUIR | 26% imposta sostitutiva |
| Plusvalenze valutarie | Art. 67(1)(c-ter) TUIR | FIFO su lotti USD, 26% se soglia superata |
| Soglia valutaria | Art. 67(1)(c-ter) TUIR | €51.645,69 per 7+ giorni lavorativi |
| Cambio | D.P.R. 917/1986 | Tassi BCE (cambio ufficiale AdE) |
| Quadro RW | Modello Redditi PF, Sez. II-A | Cod. 20 titoli, Cod. 1 depositi |
| Quadro RT | Modello Redditi PF, righi RT21+ | Sez. II-A, imposta sostitutiva 26% |
| Quadro RL | Modello Redditi PF, rigo RL2 | Sez. I, redditi di capitale esteri |

## Sviluppo

```bash
source .venv/bin/activate
pytest tests/ -x -v --rootdir=.
```

143 test: holidays, XML parsing, FX service, forex threshold, forex FIFO gains, statement store, Schwab PDF parsing, end-to-end regression su tre fixture sintetiche (`magnotta`, `mosconi`, `mascetti`).

## Requisiti

- Python 3.12+
- poppler-utils (per `pdftotext`)
- Dipendenze Python: aiohttp, aiosqlite, python-dotenv, openpyxl, fpdf2, rich, yfinance, pydantic, pyyaml

## Licenza

MIT
