# Normativa -- Riferimenti fiscali e interpretazioni

Raccolta dei riferimenti normativi e delle circolari AdE che governano
il calcolo del report fiscale. Ogni regola implementata nel codice
ha il suo riferimento qui.

Per la guida pratica alla compilazione, vedi [GUIDA_FISCALE.md](GUIDA_FISCALE.md).
Per l'architettura tecnica, vedi [ARCHITECTURE.md](ARCHITECTURE.md).
Per i dettagli implementativi, vedi [INTERNALS.md](INTERNALS.md).

## Fonti primarie

| Fonte | Argomento | Gazzetta Ufficiale |
|-------|-----------|-------------------|
| D.L. 201/2011, art. 19, commi 18-22 | IVAFE -- istituzione e regole | [GU 284 del 06/12/2011](https://www.gazzettaufficiale.it/eli/id/2011/12/06/011G0247/sg) |
| L. 213/2023 (Legge di Bilancio 2024), art. 1 c. 91 | IVAFE: aliquota maggiorata 0,4% per Stati a fiscalita' privilegiata dal FY 2024 | [GU 303 del 30/12/2023](https://www.gazzettaufficiale.it/eli/id/2023/12/30/23G00222/sg) |
| D.P.R. 917/1986 (TUIR), art. 67(1)(c-bis) | Plusvalenze su titoli (26%) | [GU 302 del 31/12/1986](https://www.gazzettaufficiale.it/eli/id/1986/12/31/086U0917/sg) |
| D.P.R. 917/1986 (TUIR), art. 67(1)(c-ter) | Plusvalenze su valute estere (soglia + 26%) | [GU 302 del 31/12/1986](https://www.gazzettaufficiale.it/eli/id/1986/12/31/086U0917/sg) |
| D.P.R. 917/1986 (TUIR), art. 44 | Redditi di capitale (interessi, dividendi) | [GU 302 del 31/12/1986](https://www.gazzettaufficiale.it/eli/id/1986/12/31/086U0917/sg) |
| D.L. 167/1990, art. 4 | Obblighi di monitoraggio fiscale (Quadro RW) | [GU 143 del 21/06/1990](https://www.gazzettaufficiale.it/eli/id/1990/06/21/090G0214/sg) |

## Circolari e istruzioni AdE

| Fonte | Data | Argomento | Link |
|-------|------|-----------|------|
| Circolare 28/E | 02/07/2012 | IVAFE: base imponibile, aliquote, modalita' di calcolo | [AdE](https://www.agenziaentrate.gov.it/portale/documents/20143/302998/Circolare+n+28E+del+2+luglio+2012_circolare+n28E+del+02+07+2012.pdf) |
| Circolare 38/E | 23/12/2013 | Monitoraggio fiscale: compilazione Quadro RW, aggregazione, LIFO | [AdE](https://www.agenziaentrate.gov.it/portale/documents/20143/302998/circolare+38E+del+23+dicembre+2013_Circolare_38_231213.pdf) |
| Risoluzione 60/E | 09/12/2024 | Plusvalenze valutarie: giroconto fra conti dello stesso soggetto nella stessa valuta **non integra** cessione ex art. 67(1)(c-ter); resta fiscalmente neutro | [AdE PDF](https://www.agenziaentrate.gov.it/portale/documents/20143/6581869/Ris.+n.+60+del+9+dicembre+2024+plusvalenze+art.+67+TUIR.pdf/3d6dd94c-326d-7e7c-f383-190bf5b713a5) |
| Risposta 204/2023 | -- | Soglia valutaria: somma di tutti i conti, LIFO per singolo conto | [AdE interpelli](https://www.agenziaentrate.gov.it/portale/web/guest/normativa-e-prassi/risposte-agli-interpelli) |
| Istruzioni Redditi PF 2025 | Fascicolo 2 | Compilazione Quadro RW, colonne, formule IVAFE | [AdE modelli](https://www.agenziaentrate.gov.it/portale/web/guest/redditi-pf-istruzioni) |

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

### Aliquota maggiorata 0,4% per Stati a fiscalita' privilegiata

La L. 213/2023 (Legge di Bilancio 2024), art. 1 c. 91, ha modificato
l'art. 19 c. 18 del D.L. 201/2011 introducendo dal periodo d'imposta
2024 un'aliquota IVAFE del **4 per mille (0,4%)** per i prodotti
finanziari detenuti in Stati o territori a regime fiscale privilegiato
individuati dal D.M. 04/05/1999 (i cosiddetti *black-list*). Per gli
altri Paesi resta l'aliquota ordinaria dello 0,2%.

**Limitazione corrente di decaf**: la rilevazione automatica della
giurisdizione dell'intermediario e l'applicazione dell'aliquota
maggiorata non sono implementate. Decaf applica sempre lo 0,2%. Chi
detiene posizioni presso intermediari in Paesi black-list deve
rettificare manualmente l'IVAFE o astenersi dall'usare decaf per
quelle posizioni. Fix programmato per release successiva.

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

## Semplificazioni applicate

Alcune scelte implementative si discostano dalla lettera della norma per
ragioni pratiche. Sono documentate qui per trasparenza.

### Conversione plusvalenze titoli al cambio della data di vendita

**Norma:** art. 9 co. 2 TUIR prescrive di convertire *corrispettivi* e
*costi* in valuta estera al cambio BCE *della rispettiva data*: il
costo al cambio vigente al giorno in cui e' stato sostenuto (data di
acquisto), il corrispettivo al cambio della data di realizzo (data di
vendita).

> *"I corrispettivi, i proventi, le spese e gli oneri in valuta
> estera sono valutati secondo il cambio del giorno in cui sono stati
> percepiti o sostenuti o del giorno antecedente piu' prossimo…"*
> — art. 9 co. 2 TUIR

**Cosa fa decaf oggi:** prende la plusvalenza in USD dal broker
(`fifoPnlRealized` IBKR o `Realized Gain/Loss` dallo Year-End Summary
Schwab) e la converte in EUR al cambio BCE della **data di regolamento
della vendita**. Un unico tasso, applicato all'intero P/L aggregato.

**Impatto numerico.** Se il cambio EUR/USD e' cambiato tra acquisto e
vendita, la plusvalenza in EUR calcolata da decaf non coincide con
quella ottenuta applicando alla lettera l'art. 9 co. 2 TUIR. Esempio:
titolo acquistato a $5.000 il 2022-06-15 (EUR/USD = 1,10) e venduto a
$5.500 il 2024-11-20 (EUR/USD = 1,05):

- Calcolo TUIR-corretto: corrispettivo 5.500/1,05 = €5.238,10, costo
  5.000/1,10 = €4.545,45, plusvalenza = **€692,65**
- Calcolo decaf: P/L broker $500 / 1,05 = **€476,19**
- Differenza: €216,46 (31% di scostamento in questo caso specifico).

Lo scostamento cresce con la durata della detenzione e con la volatilita'
del cambio. Per periodi brevi o cambi stabili e' trascurabile.

**Perche' questa scelta:** IBKR espone `fifoPnlRealized` come aggregato
per riga di vendita, senza esplicitare il costo di ciascun lotto chiuso
ne' la sua data di acquisto. Ricostruire il costo per lotto richiede:
(a) abilitare la sezione **Closed Lots** nella Flex Query IBKR; (b)
modificare parser e storage. Schwab espone gia' per-lotto via Year-End
Summary.

**Mitigazione parziale:** quando la soglia valutaria e' superata, il
modulo `forex_gains.py` cattura una parte della componente valutaria
sul capitale reinvestito. La compensazione non e' esatta e non copre
gli anni in cui la soglia non e' superata.

**Stato:** fix programmato. Richiede abilitazione Closed Lots nella
Flex Query IBKR (per Schwab il dato e' gia' presente). Fino al
rilascio della correzione, chi valuta lo scostamento come rilevante
per la propria posizione puo' ricalcolare manualmente le plusvalenze
per i titoli con detenzione pluriennale e cambio significativamente
variato tra acquisto e vendita.

### Data di assegnazione al periodo d'imposta (RT)

**Stato attuale:** `quadro_rt.py` assegna una vendita all'anno fiscale
in base alla *data di esecuzione* (`trade_datetime.year`). La prassi
prevalente in Italia (circ. 165/E/1998 succ.) usa invece la *data di
regolamento* come momento impositivo ex art. 68 TUIR.

**Impatto:** marginale. Colpisce solo le vendite a cavallo d'anno
(trade a fine dicembre, regolamento a inizio gennaio). Puo' spostare
l'anno di una minusvalenza riportabile (art. 68 co. 5 TUIR).

**Stato:** fix programmato.

---

## Implementazione in decaf

| Regola | Modulo | Note |
|--------|--------|------|
| IVAFE per-lot pro-rata | `quadro_rw.py` | LIFO per IBKR, lot matching per Schwab |
| IVAFE 0.2% su depositi broker | `quadro_rw.py` | NON €34.20 (non e' conto corrente) |
| Val. iniziale carry-over | `quadro_rw.py` | Prezzo mercato Dec 31 anno precedente |
| Val. finale year-end | `quadro_rw.py` + `cli.py` | Da Yahoo Finance |
| Val. finale venduti | `quadro_rw.py` | Proventi di vendita (~ quotazione) |
| Soglia al tasso 1 gennaio | `forex.py` | Tasso fisso per tutto l'anno |
| Soglia su tutti i conti | `forex.py` | IBKR + Schwab sommati |
| RSU vest != giacenza USD | `forex.py` | Vest escluse dal saldo cash |
| Forex FIFO gains | `forex_gains.py` | Solo se soglia superata |
| RT: trust broker FIFO | `quadro_rt.py` | `fifoPnlRealized` / Year-End Summary (vedi Semplificazioni) |
| Tasso BCE primario | `fx.py` | IB rates solo per validazione |
