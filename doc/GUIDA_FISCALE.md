# Guida Fiscale - Come compilare la dichiarazione con decaf

Guida pratica per usare l'output di decaf nella compilazione del
**Modello Redditi PF**. Per i riferimenti normativi esatti, vedi
[NORMATIVA.md](NORMATIVA.md). Per i dettagli tecnici del calcolo,
vedi [ARCHITECTURE.md](ARCHITECTURE.md).

## Panoramica

decaf produce un report per ogni anno fiscale contenente quattro sezioni,
ciascuna corrispondente a un quadro del Modello Redditi PF:

| Sezione decaf | Quadro | Cosa contiene | Dove nel modello |
|---------------|--------|---------------|------------------|
| Quadro RW | RW | Monitoraggio attivita' estere + IVAFE | Fascicolo 2, righi RW1-RW5 |
| Quadro RT | RT | Plusvalenze da cessione titoli (26%) | Fascicolo 2, Sez. II-A, righi RT21+ |
| Quadro RL | RL | Redditi di capitale (interessi, dividendi) | Fascicolo 2, Sez. I, rigo RL2 |
| Soglia valutaria | RT (se superata) | Plusvalenze da conversione valuta | Fascicolo 2, Sez. II-A |

---

## Quadro RW - Monitoraggio e IVAFE

### Cos'e'

Obbligo di dichiarare TUTTE le attivita' finanziarie detenute all'estero,
anche se vendute durante l'anno. L'IVAFE e' l'imposta patrimoniale sulle
attivita' estere (0.2% annuo, proporzionale ai giorni di detenzione).

Riferimenti: [NORMATIVA.md - Quadro RW](NORMATIVA.md#quadro-rw--monitoraggio--ivafe)

### Come decaf lo calcola

Per ogni lotto di titoli:
```
IVAFE = valore_finale_EUR x 0.002 x giorni_detenzione / giorni_anno
```

- **Valore finale**: prezzo di mercato al 31/12 (o alla data di vendita)
  convertito in EUR al cambio BCE della stessa data
- **Giorni**: dalla data di regolamento (settlement) dell'acquisto al
  31/12 (o alla data di regolamento della vendita)
- I lotti sono ricostruiti dai trade: il metodo LIFO (per IBKR) o il
  lot matching esatto (per Schwab) determinano quali lotti sono ancora
  detenuti. Vedi [ARCHITECTURE.md - Key Design Decisions](ARCHITECTURE.md#key-design-decisions)

Il saldo cash in USD presso il broker e' dichiarato come codice
investimento 1 (deposito) con IVAFE 0.2% (NON EUR 34.20 che si
applica solo a conti correnti bancari).

### Come compilare il Quadro RW

Per ogni riga dell'output decaf:

| Colonna modello | Dato decaf | Note |
|----------------|------------|------|
| Codice investimento | `Cod.` | 20 = titoli, 1 = depositi |
| Codice Stato estero | `Paese` | IE = Irlanda, US = Stati Uniti |
| Quota di possesso | 100% | Sempre 100 per conto individuale |
| Valore iniziale | `Val. iniz. EUR` | |
| Valore finale | `Val. fin. EUR` | |
| Giorni | `Giorni` | |
| IVAFE dovuta | `IVAFE` | Somma nella colonna 22 del rigo RW6 |

**Aggregazione**: e' possibile aggregare lotti omogenei (stesso codice
investimento + stesso stato) in una riga. In tal caso i giorni sono
la media ponderata. Conservare il dettaglio per-lotto (l'output Excel
di decaf) da esibire su richiesta AdE.
Vedi [NORMATIVA.md - Aggregazione](NORMATIVA.md#aggregazione).

### Verifica incrociata

L'output Excel ("Quadro RW") contiene tutte le colonne necessarie per
la verifica: ISIN, quantita', date acquisto/vendita, valori in valuta
originale, cambi BCE utilizzati, valori in EUR, giorni e IVAFE.

---

## Quadro RT - Plusvalenze

### Cos'e'

Plusvalenze (e minusvalenze) da cessione di titoli. Imposta sostitutiva 26%.
Le minusvalenze si riportano e compensano con plusvalenze future (max 4 anni).

Riferimenti: [NORMATIVA.md - Quadro RT](NORMATIVA.md#quadro-rt--plusvalenze)

### Come decaf lo calcola

Per ogni vendita di titoli:
1. Prende il P/L dal broker (`fifoPnlRealized` per IBKR, Year-End Summary
   per Schwab) — **decaf non reimplementa il FIFO**
2. Converte in EUR al cambio BCE alla data di regolamento della vendita
3. Per i dettagli tecnici: [ARCHITECTURE.md - Trust broker FIFO](ARCHITECTURE.md#key-design-decisions)

Per le plusvalenze valutarie (se soglia superata):
1. Ricostruisce l'intero storico dei flussi USD con metodo FIFO
2. Calcola il gain su ogni conversione EUR.USD e su ogni bonifico in uscita
3. Vedi sezione "Soglia Valutaria" sotto

### Come compilare il Quadro RT

Sezione II-A, righi RT21 e seguenti:

| Rigo | Dato decaf | Note |
|------|------------|------|
| RT21 col. 1 | Somma corrispettivi (colonna "Corrispettivo EUR") | Solo plusvalenze |
| RT22 col. 1 | Somma costi (colonna "Costo EUR") | Solo plusvalenze |
| RT23 | RT21 - RT22 | Plusvalenza netta |
| RT24 | Somma corrispettivi per minusvalenze | Se gain/loss < 0 |
| RT25 | Somma costi per minusvalenze | Se gain/loss < 0 |
| RT26 | RT24 - RT25 | Minusvalenza netta (riportabile) |
| RT27 | Imposta: RT23 x 26% | |

**Importante**: decaf riporta il valore netto (+/- EUR) per ogni operazione.
Per la dichiarazione, occorre separare plusvalenze (RT21-23) da minusvalenze
(RT24-26). L'output Excel contiene tutti i dati necessari per questa
separazione.

### Forex nel Quadro RT

Se la soglia valutaria e' superata, decaf aggiunge righe con simbolo
`EUR.USD` e `Forex = Si`. Queste vanno sommate ai righi RT21-27
insieme alle plusvalenze su titoli.

### Verifica incrociata

L'output Excel contiene anche il "P/L broker" (valore originale del
broker prima della conversione in EUR) per confronto. La differenza
tra il gain/loss decaf e il P/L broker e' dovuta unicamente al cambio
BCE utilizzato per la conversione.

---

## Quadro RL - Redditi di Capitale

### Cos'e'

Interessi e dividendi da intermediario estero (che non e' sostituto
d'imposta italiano). Vanno dichiarati al lordo, con indicazione delle
ritenute estere gia' subite (detraibili).

Riferimenti: [NORMATIVA.md - Quadro RL](NORMATIVA.md#quadro-rl--redditi-di-capitale)

### Come decaf lo calcola

1. Identifica interessi ("Broker Interest Received") e dividendi
   ("Qualified Dividend") dalle cash transaction del broker
2. Associa le ritenute alla fonte (WHT, "Withholding Tax" o "NRA Tax Adj")
   alla relativa entrata per valuta e mese
3. Converte tutto in EUR al cambio BCE alla data di accredito

### Come compilare il Quadro RL

Rigo RL2 (Sez. I):

| Colonna | Dato decaf | Note |
|---------|------------|------|
| RL2 col. 1 | Somma "Lordo EUR" | Redditi lordi |
| RL2 col. 2 | Somma "Ritenuta EUR" | Ritenute estere detraibili |

Le ritenute estere dichiarate in RL2 col. 2 generano un credito
d'imposta (art. 165 TUIR) da indicare nel Quadro CR.

---

## Soglia Valutaria

### Cos'e'

Se la giacenza complessiva in valuta estera (cash, NON titoli) supera
EUR 51.645,69 per almeno 7 giorni lavorativi italiani consecutivi,
TUTTE le plusvalenze da conversione valutaria dell'anno sono tassabili
al 26%.

Riferimenti: [NORMATIVA.md - Soglia Valutaria](NORMATIVA.md#soglia-valutaria--art-671c-ter-tuir)

### Come decaf lo calcola

1. Ricostruisce il saldo giornaliero USD da TUTTI i conti (IBKR + Schwab)
2. Converte al tasso BCE fisso del 1 gennaio (un solo tasso per tutto l'anno)
3. Conta i giorni lavorativi italiani consecutivi sopra soglia
4. Se >= 7 giorni: soglia superata

La timeline completa dei movimenti USD e' visibile nell'output terminale.
Dettagli tecnici: [ARCHITECTURE.md - FxService](ARCHITECTURE.md#fxservice-architecture),
[INTERNALS.md - Forex Threshold](INTERNALS.md#forex-threshold-art-671c-ter-tuir).

### Come decaf calcola i gain forex (se soglia superata)

Se la soglia e' superata, decaf:
1. Raccoglie tutte le acquisizioni di USD (vendite titoli, dividendi, interessi)
2. Raccoglie tutte le cessioni di USD (conversioni EUR.USD, bonifici)
3. Applica il metodo FIFO: i primi dollari acquistati sono i primi ceduti
4. Per ogni cessione: `gain = USD x (1/cambio_cessione - 1/cambio_acquisto)`
5. I gain appaiono nel Quadro RT con simbolo EUR.USD

Dettagli: [NORMATIVA.md - Forex FIFO Gains](NORMATIVA.md#forex-fifo-gains),
[INTERNALS.md - Forex FIFO](INTERNALS.md#forex-fifo-gains-module-forex_gainspy).

### Cosa fare se la soglia NON e' superata

Se decaf riporta "NON SUPERATA", le plusvalenze da conversione
valutaria sono esenti. Non vanno dichiarate nel Quadro RT.
Il Quadro RW va comunque compilato per il saldo in valuta estera.

---

## Riepilogo Output

decaf produce quattro file per ogni anno fiscale:

| File | Formato | Uso |
|------|---------|-----|
| `decaf_*_{anno}.json` | JSON | Export completo e canonico, tutti i campi |
| `decaf_*_{anno}.xlsx` | Excel | Un foglio per quadro, dettaglio completo, per la compilazione |
| `decaf_*_{anno}.pdf` | PDF | Report professionale, da allegare o stampare |
| Terminale | Rich | Riepilogo interattivo con tabelle colorate |

**Per la dichiarazione**: usare l'Excel come fonte primaria.
Contiene tutti i campi necessari, i cambi BCE usati, e i valori
di riscontro del broker.

**Per l'AdE**: conservare l'Excel + il PDF + gli estratti conto
dei broker (Flex Query XML, Year-End Summary, Annual Withholding)
come documentazione di supporto.

---

## Documentazione correlata

| Documento | Lingua | Contenuto |
|-----------|--------|-----------|
| [NORMATIVA.md](NORMATIVA.md) | Italiano | Testo esatto delle norme e circolari AdE |
| [ARCHITECTURE.md](ARCHITECTURE.md) | English | Data flow, module boundaries, type system, testing |
| [INTERNALS.md](INTERNALS.md) | English | Implementation gotchas, broker-specific quirks |
| [QUERY_SETUP.md](QUERY_SETUP.md) | English | IBKR Flex Query configuration guide |
| [README.md](../README.md) | Italiano | Installazione e uso |
| [CLAUDE.md](../CLAUDE.md) | English | AI development instructions |
