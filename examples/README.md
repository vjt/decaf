# Esempi di Output

Questa directory contiene gli output di `decaf report` generati dalle tre fixture sintetiche in [`tests/reference/`](../tests/reference/).

Per ogni fixture + anno trovi i tre file prodotti dal comando `decaf report`:

| File | Formato | Uso |
|------|---------|-----|
| `decaf_<year>.yaml` | YAML | Dump completo del `TaxReport` — diffabile tra run |
| `decaf_<year>.xlsx` | Excel | Un foglio per quadro (RW, RT, RL) + riepilogo |
| `decaf_<year>.pdf` | PDF | Prospetto stampabile con tabelle e totali |

## Come rigenerarli

```bash
python scripts/gen_examples.py
```

Lo script itera sulle fixture committate in `tests/reference/` e produce gli output con la stessa pipeline di `decaf report`.

## Fixture

### [`magnotta/`](magnotta/)

Solo IBKR, un anno (2024). Caso base: 4 titoli, IVAFE pro-rata, loss RT, un dividendo con ritenuta estera. Input: [`tests/reference/magnotta/`](../tests/reference/magnotta/).

### [`mosconi/`](mosconi/)

IBKR + Schwab, 2023 + 2024. Il ticker **SBTP** è detenuto sia a IBKR che a Schwab (stesso US equity, due broker) → il `TaxReport` mostra lotti separati ma mark price unificato. 4 vest quarterly, sell parziale in Ottobre su più lotti (il broker espone il P/L sul lotto ceduto). Input: [`tests/reference/mosconi/`](../tests/reference/mosconi/).

### [`mascetti/`](mascetti/)

IBKR + Schwab, 2024 + 2025 — stress test. Soglia forex superata per 17 giorni lavorativi consecutivi (2024) e 38 (2025). 4 vest quarterly per anno su award separati. Sell multi-lotto ST 2024 + LT 2025 da lotti dell'anno precedente. Dividendi con 4 diverse ritenute estere (US 30%, UK 0%, DE 26.375%, IT 26%). Input: [`tests/reference/mascetti/`](../tests/reference/mascetti/).
