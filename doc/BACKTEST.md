# Backtesting — Guida Completa

Il comando `decaf backtest <dir>` esegue la pipeline completa su una directory di dati broker e confronta il risultato contro un **oracolo** committato. È pensato per due scopi:

1. **Regressione**: verificare che modifiche al codice non alterino output storici già validati con il commercialista.
2. **Onboarding di dati nuovi**: congelare il primo anno fiscale come baseline, poi usarlo come oracolo per gli anni successivi.

Le fixture sintetiche in `tests/reference/` sono inoltre consumate da `tests/test_e2e.py`, quindi sono regression-tested ad ogni `pytest`.

## Indice

- [Layout di una fixture](#layout-di-una-fixture)
- [Comandi](#comandi)
- [Cosa produce il confronto](#cosa-produce-il-confronto)
- [Oracolo YAML](#oracolo-yaml)
- [File `prices.yaml`](#file-pricesyaml)
- [Ingresso del test suite](#ingresso-del-test-suite)
- [Flusso di lavoro tipico](#flusso-di-lavoro-tipico)
- [Fixture sintetiche incluse](#fixture-sintetiche-incluse)

## Layout di una fixture

Una directory di fixture è autocontenuta: tutti i dati broker + gli oracoli vivono al suo interno. Il nome dei file segue convenzioni che la pipeline riconosce automaticamente.

```
tests/reference/<nome_fixture>/
├── ibkr_flex_<year>.xml                   # IBKR XML — uno per anno
├── Individual_<acct>_Transactions_*.json  # Schwab JSON — uno per anno
├── Year-End Summary*.PDF                  # Schwab YES — uno per anno
├── Annual Withholding Statement*.PDF      # Schwab AWH — uno per anno
├── prices.yaml                            # opzionale
├── build_schwab.py                        # opzionale — generatore PDF sintetici
└── decaf_<year>.yaml                      # oracolo — uno per anno da verificare
```

| File | Obbligatorio? | Contenuto |
|------|---------------|-----------|
| `ibkr_flex_*.xml` | se usi IBKR | Export Flex Query |
| `Individual_*.json` | se usi Schwab | Transaction export (dividendi, sell, wire) |
| `Year-End Summary*.PDF` | se usi Schwab | Plusvalenze per lotto (RT) |
| `Annual Withholding*.PDF` | se usi Schwab | FMV ai vest (RW/IVAFE) |
| `prices.yaml` | no | Override dei prezzi di fine anno |
| `build_schwab.py` | no | Script Python che rigenera le 3 file Schwab da valori sintetici |
| `decaf_<year>.yaml` | sì per verifica | Dump YAML del `TaxReport` atteso |

L'anno fiscale di ogni file si ricava dal nome. Per i PDF Schwab, la pipeline estrae l'anno dal titolo + data di scadenza. Puoi avere più anni fiscali nella stessa directory: il backtest li processa tutti quelli per cui esiste un `decaf_<year>.yaml`.

## Comandi

```bash
# Verifica che l'oracolo matchi (default)
./decaf.sh backtest tests/reference/mascetti

# Rigenera l'oracolo (sovrascrive decaf_<year>.yaml)
./decaf.sh backtest tests/reference/mascetti --update

# Directory ECB rate cache personalizzata
./decaf.sh backtest tests/reference/mascetti --ecb-db /path/to/ecb.db
```

Il comando:
1. crea un DB SQLite temporaneo (`/tmp/decaf_bt_<pid>.db`) e lo cancella all'uscita;
2. ingestisce tutti gli XML IBKR + terne Schwab trovati;
3. per ogni anno con oracolo (`decaf_<year>.yaml` committato), chiama `_load_and_build_report` (stessa funzione di `decaf report`);
4. serializza il `TaxReport` via `pydantic.model_dump(mode="json")` e confronta con l'oracolo YAML.

## Cosa produce il confronto

| Caso | Output | Exit code |
|------|--------|-----------|
| Tutti gli oracoli matchano | `OK: <year> matches decaf_<year>.yaml` per ogni anno | 0 |
| Almeno un oracolo diverge | `FAIL: <year> diverges` + diff YAML stampato | 1 |
| `--update` passato | `Wrote oracle: <path>` per ogni anno | 0 |

Il diff è emesso come `actual` vs `expected` sui path divergenti nell'albero pydantic. È pensato per essere letto direttamente in terminale o redirigato in un file.

## Oracolo YAML

L'oracolo è il dump completo del `TaxReport`: account info, righe RW/RT/RL, record giornalieri forex, eventi LIFO per conto. È diffabile riga per riga tra run (ordinamento deterministico, `Decimal` serializzati come stringa).

Un diff inatteso sull'oracolo significa:
- hai modificato il codice in modo che cambia i numeri → decidi se è voluto e usa `--update`;
- hai modificato i dati di input → idem;
- c'è un bug → indaga prima di rigenerare.

Non usare `--update` per "far passare il test": l'oracolo è la specifica attesa. Se diverge senza che tu abbia toccato codice o input, fermati.

## File `prices.yaml`

Pinna i prezzi di fine anno per simboli che yfinance non risolve o per cui vuoi un valore esplicito:

```yaml
2024:
  MSCT: 14.00       # ticker sintetico, yfinance non trova
  SPKZ: 18.00       # broker estero non ha quotazione BCE
2025:
  ANTN: 6.00
```

**Doppio uso**: il file è consultato sia per il prezzo al 31/12 dell'anno fiscale (IVAFE di fine anno) sia per il prezzo al 31/12 dell'anno precedente (usato come `initial_value` nel pro-rata IVAFE per i titoli detenuti all'inizio dell'anno). Entrambi i lookup bypassano yfinance se il simbolo è presente.

Se un simbolo è in `prices.yaml` solo per un anno, l'altro anno usa yfinance. Per fixture sintetiche, popola tutti gli anni necessari per evitare che yfinance risolva un ticker reale con lo stesso nome (es. `SPRC` → SciSparc).

## Ingresso del test suite

`tests/test_e2e.py` esegue lo stesso codice di `decaf backtest` in modo parametrico su ogni `(fixture, year)` committato (`_FIXTURE_YEARS`). Ogni coppia verifica:

- `test_full_report_matches` — dump YAML completo == oracolo;
- `test_line_counts_stable` — numero di righe RW/RT/RL invariato;
- `test_rl_net_equals_gross_minus_wht` — invariante su ogni riga RL.

Se aggiungi una nuova fixture o un nuovo anno, aggiungi la coppia a `_FIXTURE_YEARS` nel test.

## Flusso di lavoro tipico

### Congelare l'anno appena chiuso come oracolo

```bash
# 1. Ingesti i dati broker in una fixture personale
mkdir -p tests/reference/my_2024
cp ~/Downloads/flex_2024.xml tests/reference/my_2024/ibkr_flex_2024.xml

# 2. Genera l'oracolo
./decaf.sh backtest tests/reference/my_2024 --update

# 3. Verifica con il commercialista, iterando sul codice + rigenerando
./decaf.sh backtest tests/reference/my_2024 --update

# 4. Una volta validato, committi l'oracolo (gitignora i file broker se sensibili)
git add tests/reference/my_2024/decaf_2024.yaml
```

### Verificare che un refactor non alteri output passati

```bash
# Prima del refactor
./decaf.sh backtest tests/reference/my_2024  # deve exit 0

# Refactor

# Dopo il refactor
./decaf.sh backtest tests/reference/my_2024  # exit 0 = tutto invariato
```

### Shipping di una nuova feature

1. Aggiungi una fixture sintetica in `tests/reference/<nome>/` che esercita la feature;
2. esegui `decaf backtest <dir> --update` per generare l'oracolo;
3. aggiungi `("nome", year)` a `_FIXTURE_YEARS` in `tests/test_e2e.py`;
4. `pytest` ora include la fixture.

## Fixture sintetiche incluse

| Fixture | Anni | Copertura |
|---------|------|-----------|
| `magnotta/` | 2024 | IBKR-only, caso base — IVAFE pro-rata, loss RT, dividendo con ritenuta |
| `mosconi/` | 2023-2024 | IBKR + Schwab, vendita parziale RSU su più lotti, stesso ticker a due broker (SBTP) |
| `mascetti/` | 2024-2025 | Stress — soglia forex superata 2 anni, LIFO per conto su più lotti USD, RSU multi-anno, dividendi con 4 ritenute (US 30%, UK 0%, DE 26.375%, IT 26%), sell multi-lotto ST+LT |

I nomi sono di personaggi immaginari (Amici Miei + Germano Mosconi). Account IDs contengono `666` per distinguerli da account reali.
