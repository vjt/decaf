<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/vjt/decaf@v0.1.3/doc/img/logo.png" alt="decaf logo" width="180">
</p>

# decaf

**De-CAF** — Generatore di report fiscale per investimenti esteri. Niente commercialista.

<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/vjt/decaf@v0.1.3/doc/img/cover.png" alt="Mascetti, Mosconi e Magnotta alle prese con la dichiarazione dei redditi">
</p>

Scarica i dati dai tuoi broker esteri e i tassi BCE, poi calcola tutto il necessario per il **Modello Redditi PF**:

- **Quadro RW** — Monitoraggio attività finanziarie estere + IVAFE
- **Quadro RT** — Plusvalenze di natura finanziaria (26%)
- **Quadro RL** — Redditi di capitale (interessi, dividendi, ritenute estere)
- **Soglia valutaria** — Analisi art. 67(1)(c-ter) TUIR

Output: tabelle colorate nel terminale, Excel (un foglio per quadro), PDF e YAML.

📖 **Manuale completo**: [doc/decaf_manual.pdf](https://cdn.jsdelivr.net/gh/vjt/decaf@v0.1.3/doc/decaf_manual.pdf) — guida fiscale, normativa con riferimenti alla Gazzetta Ufficiale, architettura, internals per broker, setup Flex Query. Rigenerato ad ogni cambio in `doc/` via pre-commit hook.

🎬 **Guarda un esempio di output** — fixture sintetica `mascetti` (anno 2025, stress test con soglia forex superata, multi-broker, 4 ritenute estere):
[📄 PDF](https://cdn.jsdelivr.net/gh/vjt/decaf@v0.1.3/examples/mascetti/decaf_2025.pdf) ·
[📊 Excel](https://cdn.jsdelivr.net/gh/vjt/decaf@v0.1.3/examples/mascetti/decaf_2025.xlsx) ·
[📋 YAML](https://cdn.jsdelivr.net/gh/vjt/decaf@v0.1.3/examples/mascetti/decaf_2025.yaml)

Altri output in [`examples/`](https://github.com/vjt/decaf/tree/master/examples).

> ⚠️ **Disclaimer.** Questo strumento automatizza i calcoli ma **non sostituisce un commercialista**. Le leggi fiscali cambiano, i tuoi dati e la tua situazione sono tuoi — verifica sempre i numeri prima di firmare il Modello Redditi. Gli autori non si assumono responsabilità per errori, omissioni, o interpretazioni della normativa. Usalo come punto di partenza, non come oracolo.

## Broker Supportati

| Broker | Sorgente dati | Note |
|--------|--------------|------|
| **Interactive Brokers** (Irlanda) | Flex Query API o file XML | Automatico |
| **Charles Schwab** (account EAC/RSU) | 3 file: PDF Year-End Summary + PDF Withholding + JSON transazioni | Manuale da schwab.com |

## Prerequisiti

**Linux (Debian/Ubuntu)**:
```bash
sudo apt install python3 python3-venv poppler-utils git
```

**macOS**:
```bash
brew install python poppler git
```

`poppler-utils` (`pdftotext`) serve al parsing dei PDF Schwab. Windows non testato.

## Installazione

### Opzione 1 — da PyPI (consigliata)

```bash
pip install --user decaf-tax    # pacchetto: decaf-tax · comando: decaf
mkdir ~/decaf
decaf --help
```

Installazione isolata con pipx (alternativa, un venv dedicato al tool):

```bash
pipx install decaf-tax
```

Il comando `decaf` sarà disponibile nel tuo PATH. Tutti i comandi di questo README (`decaf load`, `decaf report`, `decaf backtest`) funzionano identici.

### Opzione 2 — dal sorgente (per hackare o leggere il codice)

```bash
git clone https://github.com/vjt/decaf.git
cd decaf
mkdir private                   # qui metterai i tuoi file broker (gitignored)
./decaf.sh --help
```

`./decaf.sh` crea `.venv/` alla prima invocazione e aggiorna le dipendenze automaticamente quando `pyproject.toml` cambia (utile dopo un `git pull`). Le due librerie vendor (`ibkr-flex-client`, `ecb-fx-rates`) sono pubblicate su PyPI, quindi non serve `--recursive` per l'uso normale — vedi la sezione [Sviluppo](#sviluppo) se vuoi modificarle localmente.

## Primo utilizzo

Da qui in poi il comando `decaf` si riferisce sia al binario installato via pip/pipx sia a `./decaf.sh` dal sorgente — funzionano identici. Scegli tu dove tenere i file broker (`~/decaf/` se hai installato via PyPI, `./private/` dal sorgente — dir già gitignored).

### 1. Prepara i file broker

```
~/decaf/
├── flexquery.xml                              # IBKR — esportato da Flex Query
├── Individual_XXX_Transactions_*.json         # Schwab — Accounts → History → Export (JSON)
├── Year-End Summary*.PDF                      # Schwab — Statements → Tax Documents
└── Annual Withholding Statement*.PDF          # Schwab — Equity Award Center → Documents
```

**Prima volta con IBKR?** Devi configurare una Flex Query dal portale Interactive Brokers — serve sia per il download via API sia per esportare l'XML. Guida completa con screenshot: **[doc/QUERY_SETUP.md](https://github.com/vjt/decaf/blob/master/doc/QUERY_SETUP.md)**. Una volta configurata, puoi saltare il file e usare l'API mettendo `IBKR_TOKEN` + `IBKR_QUERY_ID` in `.env` nella directory corrente (gitignored).

Per Schwab i tre file contengono dati diversi e servono tutti:

| File | Cosa contiene |
|------|---------------|
| `Individual_*.json` | Dividendi, ritenute (RL), vendite, bonifici (forex LIFO) |
| `Year-End Summary*.PDF` | Plusvalenze per lotto (RT) |
| `Annual Withholding*.PDF` | FMV al vest per IVAFE (RW) |

### 2. Carica i dati nel DB locale

```bash
cd ~/decaf

# IBKR — da file
decaf load --file flexquery.xml

# IBKR — da API (richiede .env)
decaf load

# Schwab
decaf load --broker schwab \
  --file Individual_*_Transactions_*.json \
  --gains-pdfs "Year-End Summary*.PDF" \
  --vest-pdfs "Annual Withholding Statement*.PDF"
```

I caricamenti sono idempotenti — puoi rieseguirli senza duplicare. Il DB sta in `~/.cache/decaf/`.

### 3. Genera il report

```bash
decaf report --year 2025 --output-dir ~/decaf
```

Produce `decaf_2025.yaml` + `.xlsx` + `.pdf` in `~/decaf/`, e stampa tabelle colorate nel terminale con totali per quadro, etichette AdE, e riferimenti normativi.

## Esempi

[`examples/`](https://github.com/vjt/decaf/tree/master/examples) contiene gli output reali generati su tre fixture sintetiche:

| Fixture | Anni | Copre |
|---------|------|-------|
| [`magnotta/`](https://github.com/vjt/decaf/tree/master/examples/magnotta) | 2024 | IBKR-only, caso base |
| [`mosconi/`](https://github.com/vjt/decaf/tree/master/examples/mosconi) | 2023-2024 | IBKR + Schwab, RSU, stesso ticker a 2 broker |
| [`mascetti/`](https://github.com/vjt/decaf/tree/master/examples/mascetti) | 2024-2025 | Stress — soglia forex, LIFO multi-lotto USD, 4 ritenute diverse |

Ogni sotto-directory contiene `decaf_<year>.{yaml,xlsx,pdf}`. Input corrispondenti in [`tests/reference/`](https://github.com/vjt/decaf/tree/master/tests/reference).

## File di Output

| File                | Formato | Uso                                                         | Esempio |
|---------------------|:-------:|-------------------------------------------------------------|:-------:|
| `decaf_<year>.xlsx` | Excel   | Un foglio per quadro + riepilogo                            | [xlsx](https://cdn.jsdelivr.net/gh/vjt/decaf@v0.1.3/examples/mascetti/decaf_2025.xlsx) |
| `decaf_<year>.pdf`  | PDF     | Prospetto con tabelle e totali                              | [pdf](https://cdn.jsdelivr.net/gh/vjt/decaf@v0.1.3/examples/mascetti/decaf_2025.pdf) |
| `decaf_<year>.yaml` | YAML    | Dump completo del `TaxReport` — diffabile, stabile tra run  | [yaml](https://cdn.jsdelivr.net/gh/vjt/decaf@v0.1.3/examples/mascetti/decaf_2025.yaml) |

## Come Funziona

1. **Load** — Scarica dati dal broker (API o file) e tassi BCE. Salva tutto in SQLite.
2. **Report** — Carica da SQLite, converte USD→EUR al cambio BCE, calcola:
   - **Soglia valutaria**: ricostruisce il saldo giornaliero in valuta estera, verifica 7+ giorni lavorativi consecutivi sopra €51.645,69
   - **IVAFE**: 0.2% annuo sul valore di mercato dei titoli (pro-rata per giorni), €34.20 fisso per depositi
   - **Plusvalenze titoli**: converte il P/L del broker in EUR al tasso BCE alla data di regolamento
   - **Plusvalenze valutarie**: se soglia superata, calcola i guadagni forex con LIFO per singolo conto sui lotti USD (acquisti da vendite titoli, dividendi, interessi → cessioni tramite conversioni EUR.USD e bonifici)
   - **Redditi di capitale**: abbina interessi lordi con ritenute estere
3. **Output** — Genera i file e il report terminale

## Regole Fiscali Implementate

| Regola | Riferimento | Implementazione |
|--------|------------|-----------------|
| IVAFE titoli | D.L. 201/2011, art. 19 | 0.2% su valore di mercato, pro-rata giorni |
| IVAFE depositi | D.L. 201/2011 | €34.20 fisso annuo |
| Plusvalenze titoli | Art. 67(1)(c-bis) TUIR | 26% imposta sostitutiva |
| Plusvalenze valutarie | Art. 67(1)(c-ter) TUIR + 1-bis + risposta 204/2023 | LIFO per singolo conto su lotti USD, 26% se soglia superata |
| Soglia valutaria | Art. 67(1)(c-ter) TUIR | €51.645,69 per 7+ giorni lavorativi |
| Cambio | D.P.R. 917/1986 | Tassi BCE (cambio ufficiale AdE) |
| Quadro RW | Modello Redditi PF, Sez. II-A | Cod. 20 titoli, Cod. 1 depositi |
| Quadro RT | Modello Redditi PF, righi RT21+ | Sez. II-A, imposta sostitutiva 26% |
| Quadro RL | Modello Redditi PF, rigo RL2 | Sez. I, redditi di capitale esteri |

## Bring Your Own Data — Backtesting

Il comando `decaf backtest <dir>` riesegue l'intera pipeline su una directory di file broker e confronta l'output con oracoli YAML committati. Utile per:

- verificare che un cambio di codice non alteri output storici;
- congelare i risultati dell'anno N come regressione per l'anno N+1;
- condividere casi di test senza toccare dati sensibili.

Guida approfondita: [doc/BACKTEST.md](https://github.com/vjt/decaf/blob/master/doc/BACKTEST.md).

### Layout della directory

```
tests/reference/mascetti/
├── ibkr_flex_2024.xml                             # IBKR XML per anno
├── ibkr_flex_2025.xml
├── Individual_XXX066_Transactions_*.json          # Schwab JSON per anno
├── Year-End Summary*.PDF                          # Schwab YES PDF per anno
├── Annual Withholding*.PDF                        # Schwab AWH PDF per anno
├── prices.yaml                                    # opzionale — override prezzi
├── decaf_2024.yaml                                # oracolo per anno
└── decaf_2025.yaml
```

L'anno fiscale di ogni file si ricava dal nome: `ibkr_flex_<year>.xml` per l'XML, le date nei nomi Schwab per JSON/PDF. Gli oracoli sono obbligatori solo per gli anni che vuoi verificare.

### Comandi

```bash
# Rigenera oracoli (uso iniziale o dopo modifiche volute)
./decaf.sh backtest tests/reference/mascetti --update

# Verifica regressione (exit 0 = match, 1 = diff)
./decaf.sh backtest tests/reference/mascetti
```

Il comando:
1. crea un DB SQLite temporaneo in `/tmp/decaf_bt_<pid>.db`;
2. ingestisce tutti i file broker trovati nella directory;
3. calcola il report per ogni anno con oracolo;
4. confronta il dump YAML completo contro l'oracolo (`--update` lo sovrascrive invece).

Exit code: `0` = tutti gli anni matchano, `1` = almeno un anno diverge.

### Override di prezzo (`prices.yaml`)

Pinna i prezzi di fine anno per simboli che yfinance non risolve (ticker sintetici, delistati, esteri) o che vuoi controllare esplicitamente:

```yaml
2024:
  MSCT: 14.00
  SPKZ: 18.00
2025:
  ANTN: 6.00
```

Il dizionario è consultato **due volte** per ogni anno fiscale:
- blocco `<year>` → prezzo a fine anno (IVAFE al 31/12);
- blocco `<year-1>` → prezzo a fine anno precedente (usato come `initial_value` nel calcolo pro-rata IVAFE per titoli portati dall'anno precedente).

Senza override, entrambi i lookup passano a yfinance.

### Fixture sintetiche incluse

| Fixture | Anni | Copertura |
|---------|------|-----------|
| `magnotta/` | 2024 | IBKR singolo, caso base — IVAFE pro-rata, loss RT, dividendo con ritenuta |
| `mosconi/` | 2023-2024 | IBKR + Schwab, FIFO broker su vendita parziale titoli, RSU vest, multi-anno |
| `mascetti/` | 2024-2025 | Stress test — soglia forex superata 2 anni, LIFO multi-lotto USD (forex), RSU multi-anno, dividendi con 4 ritenute diverse (US 30%, UK 0%, DE 26.375%, IT 26%) |

Nomi dei personaggi:
- `mascetti/` — Il Conte Raffaello Mascetti, [personaggio immaginario del film *Amici Miei*](https://it.wikipedia.org/wiki/Amici_miei)
- `mosconi/` — [Germano Mosconi](https://it.wikipedia.org/wiki/Germano_Mosconi), leggendario giornalista veronese
- `magnotta/` — [Mario Magnotta](https://it.wikipedia.org/wiki/Mario_Magnotta), icona internet ante-litteram di L'Aquila

Account IDs contengono `666` per distinguerli visivamente da account reali.

## Sviluppo

```bash
source .venv/bin/activate
scripts/lint.sh     # ruff + pyright
scripts/test.sh     # pytest -x
```

Test suite: holidays, XML parsing, FX service, forex threshold, forex LIFO gains, statement store, Schwab PDF parsing, end-to-end regression su tre fixture sintetiche.

Richiede Python 3.12+. Le dipendenze sono gestite da `./decaf.sh` (primo avvio crea `.venv/` + installa, run successivi aggiornano solo se `pyproject.toml` è cambiato).

Per rigenerare il manuale PDF (`scripts/manual.sh`, lanciato anche dal pre-commit hook quando cambia `doc/`) serve pandoc + xelatex:

```bash
# Linux (Debian/Ubuntu)
sudo apt install pandoc texlive-xetex texlive-latex-recommended texlive-latex-extra

# macOS
brew install pandoc
brew install --cask mactex-no-gui
```

Se vuoi modificare le due librerie vendor (`ibkr-flex-client`, `ecb-fx-rates`), clona con i submodule:

```bash
git submodule update --init --recursive
```

`./decaf.sh` rileva automaticamente `vendor/<dep>/pyproject.toml` e installa quelle versioni in modalità editable, sovrascrivendo le pin PyPI. Fai le tue modifiche in `vendor/<dep>/`, i test di decaf le useranno subito.

I submodule sono via HTTPS. Se hai accesso push e preferisci SSH, scopi la riscrittura alle sole due repo dei submodule:

```bash
git config --global url."git@github.com:vjt/ibkr-flex-client.git".insteadOf "https://github.com/vjt/ibkr-flex-client.git"
git config --global url."git@github.com:vjt/ecb-fx-rates.git".insteadOf "https://github.com/vjt/ecb-fx-rates.git"
```

Nessun altro repo (nemmeno altri di `vjt/`) viene toccato.

### Rilasciare una nuova versione

```bash
# 1. Bump version, pin delle URL jsdelivr al nuovo tag, aggiorna CHANGELOG.
#    Le URL nel README devono puntare a @vX.Y.Z (non @master) così la
#    pagina PyPI serve asset coerenti con la release: jsdelivr cache-a
#    @master 7 giorni → un pin al tag elimina ogni staleness.
NEW=X.Y.Z
sed -i "s|^version = .*|version = \"$NEW\"|" pyproject.toml
sed -i "s|cdn.jsdelivr.net/gh/vjt/decaf@v[0-9.]\+|cdn.jsdelivr.net/gh/vjt/decaf@v$NEW|g" README.md
vim CHANGELOG.md  # sposta [Unreleased] in una sezione [X.Y.Z] — YYYY-MM-DD

# 2. Build wheel + sdist
source .venv/bin/activate
rm -rf dist && python -m build
twine check dist/*

# 3. Upload a PyPI (richiede PYPI_TOKEN in .env con scope account)
set -a && source .env && set +a
TWINE_USERNAME=__token__ TWINE_PASSWORD="$PYPI_TOKEN" twine upload dist/*

# 4. Commit + tag + push
git add pyproject.toml CHANGELOG.md README.md
git commit -m "Release $NEW: <riassunto>"
git tag v$NEW
git push origin master --tags
```

Il pre-commit hook rigenera automaticamente `doc/decaf_manual.pdf` se hai toccato `doc/`, quindi non c'è niente da fare a mano per il manuale.

## Licenza

MIT
