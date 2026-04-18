# Decaf — Open-source rollout plan (LIVE, v3)

**Obiettivo:** aprire `github.com/vjt/decaf` al pubblico senza esporre dati
privati. Tre fixture pubbliche fake che coprono tutti i code path attuali,
più flusso BYOD (Bring Your Own Data) per backtest su dati reali in locale.

> **Status:** in esecuzione. Aggiornato ad ogni decisione rilevante in corso
> d'opera. **Questo file supera tutte le versioni precedenti.** Se c'è
> ambiguità tra conversazione e questo file, questo file vince (purché
> aggiornato).

> **Regola d'oro:** il repo NON diventa pubblico finché l'utente dà OK
> esplicito. Tutto il lavoro succede su repo privato.

---

## Architettura decisa

### Output format

- **Solo YAML.** `decaf report` emette `decaf_<year>.yaml`. **Nome per anno,
  non per account** (es. `decaf_2024.yaml`). `xlsx` + `pdf` restano come
  output binari (regressione visiva). **JSON è droppato completamente.**
- Motivo: un formato solo, diff umani su PR, no conversioni YAML↔JSON nei
  test.

### Modelli: pydantic

- **`src/decaf/models.py` migrato a `pydantic.BaseModel`** con
  `model_config = ConfigDict(frozen=True)`.
- Motivo (flippato dopo discussione): `model_dump(mode='json')` emette
  `Decimal` come stringa nativamente → no custom PyYAML representer.
  `model_validate(dict_from_yaml)` ricostruisce tipato con Decimal. Schema
  validation al load = sentinella migrazione schema gratuita.
- Dep aggiunta: `pydantic>=2.0`.
- Callsite changes: `dataclasses.asdict(x)` → `x.model_dump(mode='json')`;
  `dataclasses.replace(x, ...)` → `x.model_copy(update={...})`.

### Backtest CLI

```
decaf backtest <dir>                 # esegue pipeline, confronta output vs committed yaml
decaf backtest <dir> --year N        # singolo anno
decaf backtest <dir> --update        # riscrive yaml committati (oracolo)
```

- Discovery in `<dir>`: `ibkr_flex.xml` (opzionale), `Individual_*_Transactions_*.json`
  (Schwab, opzionale), `Year-End Summary*.PDF`, `Annual Withholding*.PDF`,
  `decaf_<year>.yaml` (oracolo). Anni inferiti dai yaml presenti.
- Pipeline: ingest inputs → **temp DB in `$TMPDIR`** (mai DB nella fixture
  dir) → report per anno → struct diff vs committed YAML.
- **Fallback IBKR API**: se `ibkr_flex.xml` manca ma `.env` ha
  `IBKR_TOKEN` + `IBKR_QUERY_ID`, auto-fetch via `vendor/ibkr-flex-client`.
  Serve solo per `/private/` nel workflow reale (le fixture pubbliche
  committano sempre l'XML).
- **Null handling**: se un campo YAML committato è `null`, il diff emette
  warning + skip di quel campo (no fail). Serve per valori non calcolabili
  in alcuni scenari fixture.

### Layout directory

```
tests/reference/                     # fixture pubbliche (committate)
├── ecb_rates.db                     # shared ECB cache (tutti i fixture)
├── magnotta/
│   ├── ibkr_flex.xml                # hand-written
│   ├── decaf_2024.yaml              # oracolo
│   ├── decaf_2024.xlsx              # regressione visiva
│   └── decaf_2024.pdf               # regressione visiva
├── mosconi/
│   ├── ibkr_flex.xml
│   ├── schwab_transactions.json
│   ├── Year-End Summary - 2023*.PDF     # generato da reportlab
│   ├── Year-End Summary - 2024*.PDF
│   ├── Annual Withholding Statement_2023*.PDF
│   ├── Annual Withholding Statement_2024*.PDF
│   ├── decaf_{2023,2024}.{yaml,xlsx,pdf}
└── mascetti/
    ├── (idem + 2025)
    └── decaf_{2023,2024,2025}.{yaml,xlsx,pdf}

/private/                            # gitignored totalmente, top-level
├── README.md
├── ibkr_flex.xml                    # reale (user's IBKR Flex export)
├── Individual_*_Transactions_*.json # reale Schwab
├── Year-End Summary*.PDF            # reali Schwab
├── Annual Withholding*.PDF          # reali Schwab
└── decaf_<year>.yaml                # generato, non committato
```

### .gitignore

- `*.xml *.pdf *.PDF *.yml *.yaml` globalmente ignorati
- **Eccezione: `!tests/reference/**`** → solo fixture pubbliche possono
  committare input/output binari
- `/private/` top-level esplicitamente ignorato → no modo di commit per
  errore
- `doc/**/*.{yml,yaml}` eccezione preventiva (nel caso)

---

## Regole di progetto (DON'T BREAK)

1. **Never loosen the parser for test convenience.** Se un fake Schwab PDF
   non parsa, fix generator, non parser. Prod code non si rilascia per test.
2. **Repo stays private until explicit user OK.** Nessun push pubblico,
   nessuna GitHub Settings → Public.
3. **No database come input di test.** Input test = file broker (XML, PDF,
   JSON). `tests/reference/statements.db` rimosso. `ecb_rates.db` OK (è
   cache interna, non dato utente).
4. **Fake account IDs contengono "666"**: Magnotta `U66666660`, Mosconi
   `U66666606 / MSC666`, Mascetti `U66666066 / CMT666`. Grep visivo per
   distinguere fake da reali.
5. **Decimal ovunque per i soldi.** Architecture tests già lo enforce.
6. **Settlement dates per IVAFE, trade dates per RT.**

---

## Fixture pubbliche: specifica

### Fixture 1 — Mario Magnotta (EASY, IBKR-only, 2024)

**Holder:** Mario Magnotta
**CF:** MGNMRA42J14A345Z (fake, L'Aquila)
**IBKR:** `U66666660`

| Ticker | Nome | Settore | Note |
|--------|------|---------|------|
| SGRG | San Giorgio Industries SpA | Food & Beverage | Buy 500 @ 2.00, sell 500 @ 1.504 → **loss -247.90 EUR** (480.000 ITL al cambio fisso 1936.27) |
| CIMP | Cinque Imperia Holdings SpA | Diversified Financials | 100 azioni open a fine anno, IVAFE pro-rata |
| BGMP | Bongempi Alimentari SpA | Consumer Staples | 200 azioni, dividendo lordo 45 EUR + ritenuta 15% = 6.75 EUR |

Cash balance IBKR = 1247 USD a fine 2024 → IVAFE depositi 34.20 EUR.

**Path esercitati:** IBKR Flex XML, IVAFE titoli pro-rata, IVAFE depositi,
RT loss (riportabile no imposta), RL dividendi con ritenuta singola.

### Fixture 2 — Germano Mosconi (MEDIO, IBKR+Schwab, 2023-2024)

**Holder:** Germano Mosconi
**CF:** MSCGMN41A02G489X (fake, San Bonifacio VR)
**IBKR:** `U66666606` | **Schwab:** `MSC666`

| Ticker | Nome | Broker | Note |
|--------|------|--------|------|
| MKEO | Mkeo Broadcasting Inc | IBKR | Acquisto 2023, dividendo semestrale |
| SBTP | Sbatter Porte Industries Ltd | IBKR | Multi-anno, RW pro-rata |
| SBRS | Sbarra Spatial Services plc | IBKR | 2 lotti 2023+2024, FIFO su vendita parziale |
| BSTM | Bestemmi Asset Management SA | IBKR | Cash-like (bond fund) |
| MOSC | Mosconi Holdings Inc (employer RSU) | Schwab | 50 RSU vest 2024 + withholding 22% |

Cash balance Schwab 820 USD fine 2024 → IVAFE depositi 34.20 EUR.

**Path aggiuntivi:** Schwab JSON+2 PDF parsing, RSU vest FMV, FIFO lotti USD,
soglia forex borderline non superata, multi-anno.

### Fixture 3 — Conte Mascetti (STRESS, IBKR+Schwab, 2023-2025)

**Holder:** Conte Raffaello Mascetti
**CF:** MSCRFL25A01F205X (fake, Firenze)
**IBKR:** `U66666066` | **Schwab:** `CMT666`

12 posizioni tema supercazzola: TPPC, SPKZ, MSCT, SCPL, COMR, BLPP, PRST,
STZC, CLCN, ANTN, CMTH (RSU), CSHB (cash > 50k USD).

**Forex intensivo:**
- Bonifico EUR→USD 55.000 a feb 2024 (sopra soglia 51.645,69)
- Saldo USD sopra soglia 14+ gg 2024, 21+ gg 2025
- Bonifico USD→EUR ott 2025 con FIFO gain

**Path aggiuntivi:** soglia forex superata (2y/3), FIFO forex, FIFO titoli
multi-lot (3 lotti SPKZ), dividendi 4 paesi (US 30%, UK 0%, DE 26.375%,
IT 26%), RSU multi-year, RL interessi con ritenuta.

---

## Stato avanzamento (aggiornato live)

### ✅ Done

- `.gitignore` aggiornato (eccezione `!tests/reference/**`, `/private/` ignorato)
- `/private/` creato con README
- `input/` → `/private/` (4 Schwab PDF + 1 Schwab JSON)
- `tests/reference/decaf_*.json` → `/private/` (4 reference)
- `tests/reference/statements.db` rimosso da git
- **Validazione dati privati**: con `private/ibkr_flex.xml` (rigenerato
  dall'utente, 2 account U66666666+U66666600), `decaf fetch + report` su
  tutti gli anni 2022-2025 produce JSON **byte-identico** ai reference
  JSON spostati in `private/`. Zero diff.

### 🚧 In progress / coda

- ✅ Task #5: `models.py` migrato a pydantic v2 (frozen BaseModel)
- ✅ Task #6: `output_yaml.py` aggiunto, `output_json.py` rimosso, filename `decaf_<year>.{yaml,xlsx,pdf}`
- ✅ Task #7: `decaf backtest <dir> [--year N] [--update]` funzionante, null-skip, fallback IBKR API
- ✅ Task #8: `private/decaf_{2022,2023,2024,2025}.yaml` rigenerati, roundtrip OK su tutti
- Fixture Magnotta (task #9)
- Schwab PDF generator reportlab (task #10)
- Fixture Mosconi (task #11)
- Fixture Mascetti (task #12)
- Parametrizzare `test_e2e.py` (task #13)
- Update README con sezione Backtesting + BYOD (task #14)
- Verifica finale — tests verdi, grep ID reali = 0 match, exit 0 su 4
  fixture (task #15)

### ⏳ Postponed fino a OK esplicito user

- `git filter-repo --path tests/reference --invert-paths` (scrub history
  di statements.db e JSON reference che erano committati)
- `git push --force-with-lease origin master`
- GitHub Settings → Change visibility → Public

---

## Decisions & why (cronologia flip)

1. **Ordine esecuzione**: prima fixture + tests verdi, POI scrub history.
   Motivo: riduce finestra rotta; repo privato, no fretta.

2. **Scrub history rinviato**: non necessario finché repo privato.
   Motivo: utente esplicito "that is my data out of repo why do we need to
   nuke it".

3. **No DB come test input**: rimuove `statements.db` committato, ingest
   parte sempre da file broker. Motivo: BYOD coerente, "input is what user
   fetches from broker".

4. **Schwab file reali in `/private/`, NON in `tests/reference/private/`**.
   Motivo: top-level riduce rischio di commit accidentale; `/private/`
   in `.gitignore` è inequivoco.

5. **expected YAML = full TaxReport dump, non summary schema**. Motivo:
   "must be fucking exact, if needed re-run decaf and grab output".
   Regressione completa, non solo totali.

6. **YAML-only, JSON droppato**. Motivo: "perché non drop json completely
   e use yaml only to avoid conversions". Un formato, diff umani.

7. **Un YAML per anno, non per account**. Motivo: richiesta esplicita user.
   `decaf_2024.yaml`, no `decaf_<acct>_2024.yaml`.

8. **Pydantic invece di dataclass**. Motivo (flippato dopo
   "why not taxreport pydantic?"): `model_dump(mode='json')` nativo per
   Decimal, schema validation al load, roundtrip tipato. Costo migrazione
   ~1h, 13 classi in models.py.

9. **ECB cache resta committata in `tests/reference/ecb_rates.db`**.
   Motivo: determinismo test, no rete; se date fixture escono dal range
   cache, extend cache, non rimuovi. Shared tra tutti i fixture.

10. **Gitignore keep `*.pdf *.yml *.yaml` per safety**. Motivo: evita
    commit accidentale di private data con quei nomi. Eccezione limitata
    a `tests/reference/**`.

11. **Null in committed YAML → warning, no fail**. Motivo: serve per
    scenari dove un valore non è calcolabile senza prima aver eseguito
    (es. cross-year state). Utente: "if data is null we print warning
    and we don't fail".

12. **`decaf backtest` con fallback auto-fetch IBKR**: se `ibkr_flex.xml`
    manca in `/private/`, usa `IBKR_TOKEN` + `IBKR_QUERY_ID` dal `.env`.
    Motivo: "you should have been able to fetch this yourself, that's
    fucking why it was not on disk".

---

## Tempi residui

| Task | Tempo |
|------|-------|
| #5 pydantic migration | 1 h |
| #6 YAML output | 30 min |
| #7 backtest CLI | 1 h |
| #8 private yaml regen | 15 min |
| #9 Magnotta | 30 min |
| #10 Schwab PDF gen | 45 min |
| #11 Mosconi | 1 h |
| #12 Mascetti | 2 h |
| #13 parametrize e2e | 30 min |
| #14 README | 30 min |
| #15 final verify | 30 min |
| **Totale** | **~8.5 h** |

---

## Domande aperte → Risolte

Tutte chiuse in chat. Cristalizzate nelle sezioni "Decisions & why" e
"Architettura decisa" sopra.

Se un'ambiguità riemerge post-compact: la risposta è qui, questo file è
source of truth. Se anche qui è ambiguo, chiedere all'utente PRIMA di
agire.
