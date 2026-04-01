# Normativa — Riferimenti fiscali e interpretazioni

Raccolta dei riferimenti normativi e delle circolari AdE che governano
il calcolo del report fiscale. Ogni regola implementata nel codice
ha il suo riferimento qui.

## Fonti primarie

| Fonte | Argomento |
|-------|-----------|
| D.L. 201/2011, art. 19, commi 18-22 | IVAFE — istituzione e regole |
| D.P.R. 917/1986 (TUIR), art. 67(1)(c-bis) | Plusvalenze su titoli (26%) |
| D.P.R. 917/1986 (TUIR), art. 67(1)(c-ter) | Plusvalenze su valute estere (soglia + 26%) |
| D.P.R. 917/1986 (TUIR), art. 44 | Redditi di capitale (interessi, dividendi) |
| D.L. 167/1990, art. 4 | Obblighi di monitoraggio fiscale (Quadro RW) |

## Circolari e istruzioni AdE

| Fonte | Data | Argomento |
|-------|------|-----------|
| Circolare 28/E | 02/07/2012 | IVAFE: base imponibile, aliquote, modalita' di calcolo |
| Circolare 38/E | 23/12/2013 | Monitoraggio fiscale: compilazione Quadro RW, aggregazione, LIFO |
| Risoluzione 60/E | 09/12/2024 | Plusvalenze valutarie: giroconto = cessione ai fini art. 67(1)(c-ter) |
| Risposta 204/2023 | — | Soglia valutaria: somma di tutti i conti, LIFO per singolo conto |
| Istruzioni Redditi PF 2025 | Fascicolo 2 | Compilazione Quadro RW, colonne, formule IVAFE |

---

## Quadro RW — Monitoraggio + IVAFE

### Cosa si dichiara

Ogni attivita' finanziaria estera detenuta **in qualsiasi momento**
dell'anno fiscale. Anche se venduta o chiusa prima del 31 dicembre.

> *"occorre compilare il quadro anche se l'investimento non e' piu'
> posseduto al termine del periodo d'imposta (ad esempio il caso di un
> conto corrente all'estero chiuso nel corso del 2024)."*
> — Istruzioni Redditi PF 2025, Fascicolo 2, p. 50

### Valore iniziale e finale

- **Valore iniziale**: valore di mercato al 1 gennaio (o alla data
  di primo acquisto se acquisito durante l'anno).
- **Valore finale**: valore di mercato al 31 dicembre (o alla data
  di cessione se venduto durante l'anno).

> *"nel quadro RW devono essere riportate le consistenze degli
> investimenti e delle attivita' valorizzate all'inizio di ciascun
> periodo d'imposta ovvero al primo giorno di detenzione (di seguito,
> "valore iniziale") e al termine dello stesso ovvero al termine del
> periodo di detenzione nello stesso (di seguito, "valore finale")"*
> — Circolare 38/E, par. 1.4

Per titoli quotati, il valore di mercato e' il prezzo di quotazione:

> *"Per le azioni, obbligazioni e altri titoli o strumenti finanziari
> negoziati in mercati regolamentati si deve fare riferimento al valore
> puntuale di quotazione alla data del 31 dicembre di ciascun anno o
> al termine del periodo di detenzione."*
> — Circolare 28/E, par. 2.3

### IVAFE — formula

```
IVAFE = valore_finale × 0.002 × giorni_detenzione / giorni_anno × quota_possesso
```

- **0.2%** (2 per mille) per prodotti finanziari (codice 20)
- **€34.20** fisso per conti correnti e libretti di risparmio (codice 1).
  NON si applica ai depositi presso intermediari finanziari (broker):
  il saldo cash di un conto titoli e' un "deposito" e paga 0.2%.
- Pro-rata per giorni di detenzione e quota di possesso.

> *"l'imposta e' dovuta in proporzione ai giorni di detenzione e alla
> quota di possesso in caso di attivita' finanziarie cointestate."*
> — Circolare 28/E, par. 2.4

### LIFO per lot matching nel Quadro RW

Quando si vendono titoli della stessa categoria acquistati in tempi
diversi, per determinare QUALI lotti sono ancora detenuti (e quindi
soggetti a monitoraggio) si usa il metodo **LIFO** (last-in, first-out):
si considerano ceduti per primi quelli acquistati piu' di recente.

> *"Nel caso in cui siano ceduti prodotti finanziari appartenenti alla
> stessa categoria, acquistati a prezzi e in tempi diversi, per stabilire
> quale dei prodotti finanziari e' detenuta nel periodo di riferimento
> il metodo che deve essere utilizzato e' il cosiddetto 'L.I.F.O.' e,
> pertanto, si considerano ceduti per primi quelli acquisiti in data
> piu' recente."*
> — Circolare 38/E, par. 1.4.1; Istruzioni 2025, righe 3331-3332

**Nota**: per Schwab il LIFO non si applica perche' il Year-End Summary
riporta l'esatto lotto ceduto (date_acquired). Per IBKR, dove non
abbiamo il lot matching dal broker, dobbiamo applicare LIFO.

### Aggregazione

E' possibile aggregare piu' prodotti finanziari omogenei (stesso codice
investimento e stesso stato estero) in un'unica riga. In tal caso:

- Valore iniziale e finale: somma dei valori complessivi
- Giorni: **media ponderata** dei giorni di detenzione per consistenza
- Conservare un prospetto di dettaglio da esibire su richiesta AdE

> *"il contribuente puo' aggregare i dati per indicare un insieme di
> prodotti finanziari omogenei caratterizzati, cioe', dai medesimi
> codici "investimento" e "Stato Estero". In tal caso il contribuente
> indichera' nel quadro RW i valori complessivi iniziali e finali del
> periodo di imposta, la media ponderata dei giorni di detenzione di
> ogni singolo prodotto finanziario rapportato alla relativa consistenza,
> nonche' l'IVAFE complessiva dovuta."*
> — Istruzioni Redditi PF 2025

---

## Quadro RT — Plusvalenze

### Imposta sostitutiva

26% sulle plusvalenze da cessione di titoli (art. 67(1)(c-bis) TUIR)
e da cessione di valute estere (art. 67(1)(c-ter) TUIR, se soglia
superata).

### Conversione in EUR

Costo e corrispettivo convertiti al tasso BCE alla data dell'operazione.
In pratica: data di regolamento (settlement date) o data di trade.
La norma dice "data di realizzo".

### Trust broker FIFO

Per i capital gain (RT), il broker applica il proprio metodo FIFO.
IBKR fornisce `fifoPnlRealized`, Schwab il Year-End Summary con
costo per lotto. Non reimplementiamo il FIFO per i titoli.

---

## Soglia valutaria — art. 67(1)(c-ter) TUIR

### Soglia

€51.645,69 (100 milioni di vecchie lire) di giacenza in valuta
estera per almeno 7 giorni lavorativi consecutivi italiani.

### Cosa conta

Solo la giacenza in **depositi e conti correnti** in valuta estera.
I titoli (azioni, ETF) NON contano. Le RSU che vestono (shares
depositate nel conto titoli) NON sono giacenza in valuta.

> *"cessioni di valute estere rivenienti da depositi e conti correnti"*
> — Art. 67(1)(c-ter) TUIR

### Tasso di conversione per la soglia

La soglia va verificata al tasso BCE **vigente all'inizio del periodo
di riferimento** (1 gennaio). Un unico tasso fisso per tutto l'anno.

> *"superino un controvalore di cento milioni di lire [€51.645,69] ...
> al cambio vigente all'inizio del periodo di riferimento"*
> — Art. 67(1)(c-ter) TUIR

### Conti multipli

La soglia si verifica sommando i saldi di **tutti i depositi e conti
correnti** in valuta estera, anche presso intermediari diversi.

> Risposta 204/2023: la soglia va verificata sommando i saldi di tutti
> i conti in valuta estera del contribuente.

### Se soglia superata

TUTTE le plusvalenze da cessione di valuta estera dell'anno sono
tassabili al 26%. Il calcolo del gain usa il metodo LIFO per singolo
rapporto (conto).

---

## Quadro RL — Redditi di capitale

### Interessi e dividendi esteri

Redditi di capitale di fonte estera (art. 44 TUIR), rigo RL2.
Interessi e dividendi da intermediario estero (non sostituto d'imposta
italiano). Ritenute estere detraibili.

### Conversione

Al tasso BCE alla data di percezione (accredito).

---

## Forex FIFO gains

### Problema

Ne' IBKR ne' Schwab forniscono il P/L sulle conversioni valutarie:
- IBKR EUR.USD: `broker_pnl_realized = 0`, `cost = 0`
- Schwab wire transfers: non modellati come operazioni forex

### Formula

Per ciascuna cessione di valuta (conversione EUR.USD o bonifico):

```
gain_eur = USD_importo × (1/tasso_BCE_cessione - 1/tasso_BCE_acquisto)
```

FIFO: i dollari acquistati per primi sono ceduti per primi.

### Acquisizione USD (lotti in coda FIFO)

- Proventi da vendita titoli in USD
- Dividendi e interessi in USD

### Cessione USD (consumo coda FIFO)

- Conversioni EUR.USD su IBKR (FlexQuery, asset_category=CASH)
- Bonifici in uscita da Schwab ("Wire Sent" / "FX WIRE OUT")

---

## Implementazione in decaf

| Regola | Modulo | Note |
|--------|--------|------|
| IVAFE per-lot pro-rata | `quadro_rw.py` | LIFO per IBKR, lot matching per Schwab |
| IVAFE 0.2% su depositi broker | `quadro_rw.py` | NON €34.20 (non e' conto corrente) |
| Val. iniziale carry-over | `quadro_rw.py` | Prezzo mercato Dec 31 anno precedente |
| Val. finale year-end | `quadro_rw.py` + `cli.py` | Da Yahoo Finance |
| Val. finale venduti | `quadro_rw.py` | Proventi di vendita (≈ quotazione) |
| Soglia al tasso 1 gennaio | `forex.py` | Tasso fisso per tutto l'anno |
| Soglia su tutti i conti | `forex.py` | IBKR + Schwab sommati |
| RSU vest ≠ giacenza USD | `forex.py` | Vest escluse dal saldo cash |
| Forex FIFO gains | `forex_gains.py` | Solo se soglia superata |
| RT: trust broker FIFO | `quadro_rt.py` | `fifoPnlRealized` / Year-End Summary |
| Tasso BCE primario | `fx.py` | IB rates solo per validazione |
