# decaf

**De-CAF** — Generatore di report fiscale per investimenti esteri. Niente commercialista.

Scarica i dati dai tuoi broker esteri e i tassi BCE, poi calcola tutto il necessario per il **Modello Redditi PF**:

- **Quadro RW** — Monitoraggio attività finanziarie estere + IVAFE
- **Quadro RT** — Plusvalenze di natura finanziaria (26%)
- **Quadro RL** — Redditi di capitale (interessi, dividendi, ritenute estere)
- **Soglia valutaria** — Analisi art. 67(1)(c-ter) TUIR

Output: tabelle colorate nel terminale, Excel (un foglio per quadro), PDF e JSON.

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
| **Transaction JSON** | schwab.com → Accounts → History → Export (JSON) | Dividendi e ritenute (RL) |
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

Il report mostra tabelle colorate nel terminale con i totali per quadro, le etichette ufficiali AdE, e i riferimenti normativi. Genera anche Excel, PDF e JSON.

## File di Output

| File | Formato | Uso |
|------|---------|-----|
| `decaf_<account>_<year>.xlsx` | Excel | Un foglio per quadro + riepilogo |
| `decaf_<account>_<year>.pdf` | PDF | Prospetto con tabelle e totali |
| `decaf_<account>_<year>.json` | JSON | Dati strutturati per uso programmatico |

## Come Funziona

1. **Fetch** — Scarica dati dal broker (API o file) e tassi BCE. Salva tutto in SQLite.
2. **Report** — Carica da SQLite, converte USD→EUR al cambio BCE, calcola:
   - **Soglia valutaria**: ricostruisce il saldo giornaliero in valuta estera, verifica 7+ giorni lavorativi consecutivi sopra €51.645,69
   - **IVAFE**: 0.2% annuo sul valore di mercato dei titoli (pro-rata per giorni), €34.20 fisso per depositi
   - **Plusvalenze**: converte il P/L del broker in EUR al tasso BCE alla data di regolamento
   - **Redditi di capitale**: abbina interessi lordi con ritenute estere
3. **Output** — Genera i file e il report terminale

## Regole Fiscali Implementate

| Regola | Riferimento | Implementazione |
|--------|------------|-----------------|
| IVAFE titoli | D.L. 201/2011, art. 19 | 0.2% su valore di mercato, pro-rata giorni |
| IVAFE depositi | D.L. 201/2011 | €34.20 fisso annuo |
| Plusvalenze | Art. 67(1)(c-bis) TUIR | 26% imposta sostitutiva |
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

80 test: holidays, XML parsing, FX service, forex threshold, statement store, Schwab PDF parsing.

## Requisiti

- Python 3.12+
- poppler-utils (per `pdftotext`)
- Dipendenze Python: aiohttp, aiosqlite, python-dotenv, openpyxl, fpdf2, rich

## Licenza

MIT
