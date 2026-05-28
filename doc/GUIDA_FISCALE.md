# Guida Fiscale - Come compilare la dichiarazione con decaf

Guida pratica per usare l'output di decaf nella compilazione del
**Modello Redditi PF**. Per i riferimenti normativi esatti, vedi
[NORMATIVA.md](NORMATIVA.md). Per i dettagli tecnici del calcolo,
vedi [ARCHITECTURE.md](ARCHITECTURE.md).

## Come usare questa guida

Una volta lanciato `decaf report --year YYYY`, l'output (terminale,
PDF, foglio "Precompilata" dell'XLSX) contiene la sezione
**"Per la dichiarazione precompilata (anno fiscale YYYY)"** che ti
mostra, per ogni quadro:

- **rigo, colonna e valore esatto** da digitare nella precompilata AdE,
- l'origine del numero nel report decaf (utile a tracciarlo
  all'indietro durante una verifica),
- per il Quadro RM, il **break-even** per scegliere consapevolmente
  tra RL+CE e RM31.

**Hai due modi di trasferire i numeri nella precompilata:**

1. **Copia/incolla manuale**: apri il PDF (pagina "Per la
   dichiarazione precompilata") o il foglio "Precompilata"
   dell'Excel, e digita riga per riga sul sito AdE.
2. **Autofill via Chrome DevTools Protocol** (sperimentale): lancia
   `python -m decaf.scripts.fill_rw` e
   `python -m decaf.scripts.fill_rt_rm` mentre Chrome è aperto sulla
   precompilata. Gli script scrivono direttamente i campi del form.
   Vedi [`src/decaf/scripts/README.md`](../src/decaf/scripts/README.md).

> ⚠️ **In entrambi i casi, leggi quello che è stato scritto prima di
> cliccare *Calcola, stampa e invia*.** decaf è uno strumento, non un
> commercialista — l'invio finale è una tua responsabilità.

Questa guida spiega **cosa** decaf scrive in ogni rigo e **perché**:
serve a riconoscere le voci, capire la mappatura, e cogliere i casi
particolari (RM31 multi-Modulo, fallback 1 EUR su RW col.7, ecc.).

## Panoramica

decaf produce un report per ogni anno fiscale contenente quattro sezioni,
ciascuna corrispondente a un quadro del Modello Redditi PF:

| Sezione decaf | Quadro | Cosa contiene | Dove nel modello |
|---------------|--------|---------------|------------------|
| Quadro RW | RW | Monitoraggio attivita' estere + IVAFE | Fascicolo 2, righi RW1-RW5 (5 righi per Modulo) |
| Quadro RT | RT | Plusvalenze da cessione titoli (26%) | Fascicolo 2, Sez. II-A, rigo RT11 |
| Quadro RL / RM | RL o RM | Redditi di capitale (interessi, dividendi) | Fascicolo 2, RL2 oppure RM31 (mutuamente esclusivi) |
| Soglia valutaria | RT (se superata) | Plusvalenze da conversione valuta | Fascicolo 2, Sez. II-A (incluse in RT11) |

> ⚠️ **Sez. II-A vs Sez. III-A.** I righi RT21+ stanno nella **Sez. III-A** (partecipazioni qualificate), che decaf NON gestisce. La sostitutiva 26% per partecipazioni non qualificate va in **Sez. II-A righi RT11-RT16** — solo RT11 col.1/col.2 vengono compilati dall'output decaf.

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

L'output decaf produce una riga per ogni lotto/saldo da dichiarare,
**già nel formato del Modello Redditi PF**: la prima colonna ti dice
in quale rigo RW va il dato (RW1, RW2, ...) e poi una colonna per
ogni `col.N` da compilare. Per gli script CDP è ancora più immediato
— fanno tutto loro.

Il rigo RW dentro la precompilata ha 30 colonne; decaf ne popola
**otto** (1, 3, 4, 5, 6, 7, 8, 10). Le altre o non si applicano al
caso comune (titolare ≠ proprietario, percentuale di possesso ≠ 100,
casi particolari) o sono calcolate server-side dal form.

| Colonna modello | Valore che decaf emette | Note |
|----------------|------------------------|------|
| col.1 — Codice titolare | `1` (proprietà) | Fisso per conto individuale |
| col.3 — Codice investimento | `20` (titoli) o `1` (cash) | |
| col.4 — Codice Stato estero | **Numerico AdE** (US=069, IE=040, ...) | Tradotto da decaf, NON ISO |
| col.5 — % di possesso | `100` | Fisso per conto individuale |
| col.6 — Criterio determinazione valore | `1` (valore di mercato) | Richiesto, NON è server-computed |
| col.7 — Valore iniziale EUR | dal report | `1` di fallback per valori-zero (form rifiuta `0` esplicito) |
| col.8 — Valore finale EUR | dal report | Al 31/12 o data di vendita |
| col.10 — Giorni di possesso | dal report | |
| col.30 — IVAFE dovuta | — | **Calcolata server-side, NON inserire** |

**Aggregazione manuale**: è possibile collassare lotti omogenei
(stesso codice investimento + stesso stato) in una riga unica. In tal
caso i giorni vanno calcolati come media ponderata e la
documentazione di dettaglio (foglio Excel decaf "Quadro RW") va
conservata per eventuale richiesta AdE.
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
   per Schwab), che e' il P/L sul **lotto effettivamente ceduto** secondo
   il matching method configurato sul conto (Tax Optimizer Schwab o
   matching method IBKR)
2. Converte in EUR al cambio BCE alla data di regolamento della vendita
3. Dettagli + citazioni verbatim: [NORMATIVA.md - Metodo di determinazione del costo](NORMATIVA.md#metodo-di-determinazione-del-costo-per-le-partecipazioni)

Il metodo e' quello prescritto dalla circolare AdE 165/E §2.3.2 per le
partecipazioni: base imponibile = corrispettivo − costo effettivo di
acquisto del lotto ceduto. Nessuna presunzione LIFO/FIFO.

Per le plusvalenze valutarie (se soglia superata):
1. Ricostruisce l'intero storico dei flussi USD con metodo LIFO per
   singolo conto (§2.3.2 per le valute + risposta AdE 204/2023)
2. Calcola il gain su ogni conversione EUR.USD e su ogni bonifico in uscita
3. Vedi sezione "Soglia Valutaria" sotto

### Come compilare il Quadro RT

L'output decaf emette **due valori** già aggregati per la
precompilata, nel rigo RT11 Sez. II-A:

| Rigo / Colonna | Valore | Origine in decaf |
|----------------|--------|------------------|
| RT11 col. 1 — Totale corrispettivi | `Valore EUR` emesso da decaf | somma `proceeds_eur` su tutte le righe RT |
| RT11 col. 2 — Totale costi | `Valore EUR` emesso da decaf | somma `cost_basis_eur` su tutte le righe RT |

decaf mostra anche, sotto i due totali, la **differenza** (plus/minus
netta) e l'**imposta sostitutiva 26%** stimata — entrambi sono
calcolati in automatico dal software AdE dopo che hai inserito col.1
e col.2, ti servono solo per cross-check.

**Altri righi della Sez. II-A** (non gestiti da decaf, vanno
compilati manualmente se applicabili):

- RT12 col.1/col.2 — costo rideterminato/affrancato (rare)
- **RT13** — eccedenza minusvalenze anni precedenti (riportate dalla
  tua dichiarazione dell'anno scorso). Compensano la plusvalenza fino
  a concorrenza. **decaf non conosce le tue minus pregresse.**
- RT14 — eccedenza minusvalenze certificate dall'intermediario
- RT15 — eccedenza imposta sostitutiva da precedente dichiarazione
- RT16 — plusvalenze cessione partecipazioni in paesi a regime
  fiscale agevolato (rare)

### Forex nel Quadro RT

Se la soglia valutaria e' superata, decaf aggiunge righe con simbolo
`EUR.USD` e `Forex = Si`. Queste sono gia' incluse nei totali RT11
sopra (i totali del foglio Excel "Quadro RT") perche' vanno comunque
nella stessa sezione II-A 26%.

### Verifica incrociata

L'output Excel contiene anche il "P/L broker" (valore originale del
broker prima della conversione in EUR) per confronto. La differenza
tra il gain/loss decaf e il P/L broker e' dovuta unicamente al cambio
BCE utilizzato per la conversione.

---

## Redditi di Capitale esteri — Quadro RL o Quadro RM

### Cos'e'

Interessi e dividendi da intermediario estero (che non e' sostituto
d'imposta italiano). Due vie di tassazione **mutuamente esclusive**:

| Scelta | Quadro | Rigo | Aliquota | Credito estero | Base imponibile |
|--------|--------|------|----------|----------------|-----------------|
| Opzione A | Quadro RL Sez. I-A + Quadro CE | RL2 | IRPEF marginale (23-43% + addizionali) | Si', art. 165 TUIR | Lordo |
| Opzione B | Quadro RM Sez. II-A | RM31 | 26% sostitutiva | **No** | Lordo |

Riferimenti: [NORMATIVA.md - Redditi di capitale esteri](NORMATIVA.md#redditi-di-capitale-esteri--quadro-rl-vs-quadro-rm).

### Come decaf presenta i dati

1. Identifica interessi ("Broker Interest Received") e dividendi
   ("Qualified Dividend") dalle cash transaction del broker.
2. Associa le ritenute alla fonte (WHT, "Withholding Tax" o "NRA Tax Adj")
   alla relativa entrata, con un matching forte (stessa descrizione +
   stessa data per i dividendi; stesso tag `CREDIT INT FOR <MMM>-<YYYY>`
   per gli interessi broker) e fallback per valuta+mese (vedi
   [INTERNALS.md - WHT matching](INTERNALS.md)).
3. Converte tutto in EUR al cambio BCE alla data di accredito.

Nella sezione "Per la dichiarazione precompilata" del report, decaf
ti mostra, **già pronti per la precompilata**:

- la tabella **Opzione B — Quadro RM rigo RM31**: una riga per ogni
  coppia (stato estero, tipo reddito) con i valori esatti di col.1,
  col.2, col.3, col.4, col.8 da inserire — un Modulo di Quadro RM da
  creare per ciascuna riga (vedi `decaf.scripts.fill_rt_rm` per
  l'autofill);
- la tabella **Opzione A — Quadro RL rigo RL2 + Quadro CE**: i totali
  di col.2 (redditi lordi) e col.3 (ritenute);
- una tabella **comparativa** che simula l'imposta italiana effettiva
  per i tre scaglioni IRPEF (23%, 35%, 43%) contro RM31 sostitutiva,
  con annotazione "← più conveniente" sullo scenario migliore per i
  tuoi numeri;
- il **break-even** sull'aliquota marginale (sopra → RM31; sotto →
  RL+CE);
- un blocco **Raccomandazione operativa** che default-a a RM31 per i
  dividendi non qualificati esteri (motivazione in dettaglio sotto).

### Opzione A: Quadro RL Sez. I-A, rigo RL2 (+ Quadro CE)

decaf emette i due totali aggregati per RL2:

| Colonna | Valore | Origine in decaf |
|---------|--------|------------------|
| RL2 col. 1 — Tipo reddito | dropdown manuale | es. `B` per dividendi non qualificati, `A` per interessi |
| RL2 col. 2 — Redditi | `Valore EUR` emesso | somma `gross_amount_eur` |
| RL2 col. 3 — Ritenute | `Valore EUR` emesso | somma `wht_amount_eur` |

Vai anche al **Quadro CE** per il credito d'imposta estera ex art. 165
TUIR (importo: somma `ritenuta_EUR`). Il massimale di credito è limitato
dalla quota di IRPEF italiana attribuibile al reddito estero e dai tassi
convenzionali (per i dividendi USA: 15% W-8BEN).

> ⚠️ **Zona grigia per i dividendi non qualificati.** L'AdE
> tradizionalmente considera la sostitutiva 26% via RM31
> **obbligatoria** per dividendi non qualificati percepiti tramite
> intermediario non residente (art. 27 c. 4-bis DPR 600/1973). La via
> RL+CE è stata aperta da Cass. 35454/2022 ma resta contestabile. Per
> gli interessi le considerazioni sono analoghe (art. 26 c. 5 DPR
> 600). Se vuoi percorrere l'Opzione A consapevolmente, valuta col
> commercialista; in caso di dubbio, RM31 è il default sicuro.

### Opzione B: Quadro RM Sez. II-A, rigo RM31

decaf emette **una riga per ogni coppia (stato estero, tipo reddito)**
e ogni riga corrisponde a un Modulo di Quadro RM separato (RM/1,
RM/2, ...): un solo rigo RM31 per Modulo. Esempio reale: dividendi
USA + interessi USD Schwab + interessi EUR IBKR-Irlanda → tre Moduli
di Quadro RM.

Per ogni Modulo, l'output decaf ti dà i valori esatti:

| Colonna | Valore | Origine in decaf |
|---------|--------|------------------|
| RM31 col. 1 — Tipo | `A` (interessi) o `B` (dividendi non qualificati) | classificato da `decaf.quadro_rl._classify_rl_line()` |
| RM31 col. 2 — Codice stato estero | **Numerico AdE** (US=069, IE=040, ...) | tradotto da decaf, NON ISO |
| RM31 col. 3 — Ammontare reddito | `Lordo EUR` emesso | somma `gross_amount_eur` del gruppo |
| RM31 col. 4 — Aliquota | `26` | |
| RM31 col. 8 — Imposta sostitutiva dovuta | `Imp. dovuta` emesso | lordo × 26%, arrotondata all'intero |

**Le ritenute estere NON sono recuperabili** in questa opzione (niente
Quadro CE). L'art. 165 c.1 TUIR concede il credito d'imposta estera
solo per redditi che concorrono al reddito complessivo IRPEF — i
redditi sostitutivi del Quadro RM sono fuori dal perimetro. Per
dividendi USA con WHT 15%, perdere il credito vuol dire pagare
effettivamente 26% + 15% = 41% sul lordo.

### Quale scegliere

**decaf calcola direttamente il break-even per i tuoi dati** — vedi
la tabella "Scegli UNA via — confronto imposta italiana" + il blocco
"Raccomandazione operativa" nell'output. Il consiglio operativo
default-a a RM31 per dividendi non qualificati esteri (motivazione:
art. 27 c.4-bis DPR 600/1973 + zona grigia di RL+CE post-Cass.
35454/2022). In generale:

- Per dividendi USA (WHT 15%): break-even ~41% → RL+CE conviene per
  quasi tutti i contribuenti italiani (anche al massimo scaglione
  IRPEF), ma è la via rischiosa;
- Per dividendi paesi senza convenzione (WHT 0%): break-even 26% →
  RM31 conviene per scaglioni IRPEF > 26%.

In caso di dubbio, consultare un commercialista.

### Avvertenza importante

Le due vie sono **incompatibili**: non e' consentito dichiarare una
parte in RM31 e chiedere contestualmente credito art. 165 sulla stessa
tipologia di reddito (circ. 165/E/1998 §6). La scelta vale per la
totalita' dei redditi di capitale esteri della stessa natura percepiti
nell'anno.

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
   separatamente per ciascun conto
2. Raccoglie tutte le cessioni di USD (conversioni EUR.USD, bonifici)
   separatamente per ciascun conto
3. Applica il metodo **LIFO per singolo conto** (art. 67 c. 1-bis TUIR,
   risposta AdE 204/2023): gli ultimi dollari acquistati in quel conto
   sono i primi ceduti da quel conto. I lotti non si trasferiscono fra
   conti diversi.
4. Per ogni cessione: `gain = USD x (1/cambio_cessione - 1/cambio_acquisto)`
5. I gain appaiono nel Quadro RT con simbolo EUR.USD

Dettagli: [NORMATIVA.md - Forex LIFO Gains](NORMATIVA.md#forex-lifo-gains),
[INTERNALS.md - Forex LIFO](INTERNALS.md#forex-lifo-gains-module-forex_gainspy).

### Cosa fare se la soglia NON e' superata

Se decaf riporta "NON SUPERATA", le plusvalenze da conversione
valutaria sono esenti. Non vanno dichiarate nel Quadro RT.
Il Quadro RW va comunque compilato per il saldo in valuta estera.

---

## Riepilogo Output

decaf produce tre file per ogni anno fiscale + un riepilogo a terminale:

| File | Formato | Uso |
|------|---------|-----|
| `decaf_{anno}.yaml` | YAML | Dump canonico del `TaxReport`, diffabile, stabile tra run |
| `decaf_{anno}.xlsx` | Excel | Un foglio per quadro + foglio "Precompilata" |
| `decaf_{anno}.pdf` | PDF | Report professionale, da allegare o stampare |
| Terminale | Rich | Riepilogo interattivo con tabelle colorate |

Tutti gli output **PDF, Excel e Terminale** contengono una sezione
**"Per la dichiarazione precompilata"** che mappa direttamente i valori
ai righi/colonne del Modello Redditi PF dell'anno corrente, includendo:

- **Quadro RW**: una riga per ogni lotto con valori per col.3, 4, 7, 8, 10 (col.30 IVAFE è server-side)
- **Quadro RT**: rigo RT11 col.1 e col.2 (totali aggregati)
- **Quadri RL + RM** con:
  - breakdown **RM31 per (stato, tipo reddito)** — un blocco per Modulo
  - tabella **comparativa di convenienza** che calcola l'imposta italiana effettiva per ogni scaglione IRPEF (23/35/43%)
  - **break-even** sull'aliquota marginale per scegliere tra RL+CE e RM31

**Per la dichiarazione**: usare il foglio "Precompilata" dell'Excel
oppure la pagina dedicata del PDF — i valori sono pronti per
copia/incolla nella precompilata AdE, o per l'autofill via
`decaf.scripts.fill_rw` / `decaf.scripts.fill_rt_rm` (vedi
[`src/decaf/scripts/README.md`](../src/decaf/scripts/README.md)).

**Per l'AdE**: conservare l'Excel + il PDF + gli estratti conto
dei broker (Flex Query XML, Year-End Summary, Annual Withholding)
come documentazione di supporto.

### Backup e portabilità

```bash
# Pacchettizza DB + flexquery XML storici + directory extra
decaf archive backup-2025.tgz --tree private/

# Ripristina su altra macchina
decaf unarchive backup-2025.tgz --target-dir ~
```

`decaf archive` include `~/.cache/decaf/statements.db`,
`~/.cache/decaf/ecb_rates.db` e `~/.cache/decaf/flexquery/` (l'archivio
perpetuo gzippato di ogni FlexQuery IBKR scaricata — IBKR retiene solo
~365 giorni di storico, decaf li conserva per sempre dalla 0.6.0 in poi).

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
