# decaf.scripts — AdE precompilata autofill (sperimentale)

Script per automatizzare la compilazione del **Modello Redditi PF
RPF26** sulla [dichiarazione precompilata
AdE](https://dichiarazioneprecompilata.agenziaentrate.gov.it) usando i
dati prodotti da `decaf report` come fonte di verità. Pilotano un
browser Chrome aperto via [Chrome DevTools
Protocol](https://chromedevtools.github.io/devtools-protocol/) sulla
porta `9222`.

> ⚠️ **Sperimentale e ad alta manutenzione.** Il form AdE è una React
> app il cui markup/URL cambia ad ogni edizione annuale del modello.
> Quello che funziona oggi su RPF26 (tax year 2025) può rompersi al
> primo redesign. Gli script non sono testati end-to-end in CI: sono
> stati validati a mano sul form vero durante una vera dichiarazione.
> Trattali come un punto di partenza, non un oracolo.
>
> **Verifica sempre i valori inseriti prima di inviare.** Nessuno script
> clicca mai *Calcola, stampa e invia* — l'invio resta una scelta
> manuale e consapevole.

## Cosa fanno

| Script | Quadro | Cosa popola |
|--------|--------|-------------|
| `fill_rw` | **RW** | Monitoraggio fiscale + IVAFE. 5 righi per Modulo, un Modulo ogni 5 lotti. |
| `fill_rt_rm` | **RT** + **RM** | RT11 col.1/col.2 (totali plusvalenze 26%) + un rigo RM31 per coppia (stato estero, tipo reddito) — un Modulo di Quadro RM per gruppo. |

## Prerequisiti

1. Decaf installato (PyPI o sorgente).
2. Un report YAML aggiornato per l'anno di imposta:
   ```bash
   decaf report --year 2025
   # → genera private/decaf_2025.yaml (o nel cwd)
   ```
3. Chrome avviato in modalità debug:
   ```bash
   # macOS
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
       --remote-debugging-port=9222 \
       --user-data-dir=/tmp/chrome-precompilata
   # Linux
   google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-precompilata
   ```
   Conviene usare `--user-data-dir` separato per non interferire col
   profilo di tutti i giorni.
4. Login SPID/CIE sul Chrome di debug, navigato fino a:
   `https://dichiarazioneprecompilata.agenziaentrate.gov.it/PrecomWeb/compila/RPF26/...`

## Uso

```bash
# Quadro RW — monitoraggio + IVAFE, un rigo per lotto
python -m decaf.scripts.fill_rw private/decaf_2025.yaml

# Quadro RT + RM — plusvalenze + sostitutiva 26% su redditi capitale esteri
python -m decaf.scripts.fill_rt_rm private/decaf_2025.yaml
```

### Flag comuni

| Flag | Effetto |
|------|---------|
| `--dry-run` | Stampa cosa verrebbe inserito, non tocca il form. **Usalo sempre la prima volta.** |
| `--force` | Sovrascrive campi che hanno già un valore (di default rifiuta e abortisce). |

### Flag specifici `fill_rt_rm`

| Flag | Effetto |
|------|---------|
| `--rt-only` | Compila solo il Quadro RT. |
| `--rm-only` | Compila solo il Quadro RM. |

## Convenzioni di sicurezza

- **Refuse to overwrite**: se un campo target è già pieno con un valore
  diverso, lo script abortisce e ti chiede di passare `--force`. Serve
  per non distruggere dati inseriti a mano o da una run precedente.
- **Abort on save failure**: dopo ogni `Salva` viene controllato che
  non compaia il banner "*Salvataggio non effettuato*". Se compare,
  abort.
- **Mai click su "Calcola, stampa e invia"**: l'invio finale è sempre
  manuale.

## Workflow consigliato

1. `--dry-run` per vedere cosa lo script vuole inserire.
2. Confronta col PDF generato da `decaf report` (sezione "Per la
   dichiarazione precompilata") — devono essere gli stessi numeri.
3. Run reale senza `--dry-run`.
4. **Apri il browser, vai sul quadro compilato, leggi tutto.**
5. Clicca *Verifica i dati* nel menu della precompilata: 0 errori, 0
   anomalie.
6. Quando sei soddisfatto, *Calcola, stampa e invia* a mano.

## Internals

- `_cdp.py` — wrapper minimale su WebSocket CDP. Esegue JS nel
  contesto del tab aperto, imposta i valori dei campi bypassando il
  controllo React via *native setter* + invocazione diretta della prop
  `onChange`, gestisce il modal "Aggiungi modulo".
- `country_codes.py` (in `decaf/`) — mappa ISO 3166-1 alpha-2 → codice
  numerico AdE (US=069, IE=040, ...). Estendere quando serve.
- `quadro_rl.aggregate_rl_for_rm31()` — classifica le RL lines del
  report in coppie (stato estero, tipo reddito) per generare i righi
  RM31.

## Quando uno script si rompe

Il sintomo più comune: il form ha cambiato nome dei campi o URL. Per
ispezionare il DOM del tab corrente:

```python
import asyncio, json, urllib.request, websockets

async def dump():
    with urllib.request.urlopen('http://localhost:9222/json/list') as r:
        tab = next(t for t in json.loads(r.read()) if 'precompilata' in t.get('url',''))
    async with websockets.connect(tab['webSocketDebuggerUrl']) as ws:
        await ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
            'params': {'expression': "Array.from(document.querySelectorAll('input,select')).map(e=>e.name).filter(Boolean)",
                       'returnByValue': True}}))
        print(json.loads(await ws.recv()))

asyncio.run(dump())
```

I field name del modulo (es. `RW001001`, `RM031001`) sono solitamente
stabili tra edizioni; cambiano le URL `/RPF{NN}/M/quadro/...` e
occasionalmente la struttura di modal/conferme.
