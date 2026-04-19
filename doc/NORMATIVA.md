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
| Risposta a interpello n. 204 | 07/02/2023 | Soglia valutaria (art. 67 c. 1-ter TUIR): si aggregano le giacenze di tutti i conti in valuta estera del contribuente; il calcolo delle plusvalenze si effettua analiticamente e distintamente **per ciascun conto**, applicando LIFO ex art. 67 c. 1-bis | [AdE PDF](https://www.agenziaentrate.gov.it/portale/documents/20143/4988698/Risposta+n.+204_2023.pdf/5189c15d-4fe7-f043-606b-2843bc00df74) |
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
- **€34.20** fisso per conti correnti bancari e libretti di risparmio
  (codice 1), ex art. 19 c. 20 D.L. 201/2011. L'imposta fissa si
  applica a rapporti autonomi di conto corrente presso banche italiane
  o estere; **non** si applica al saldo cash di un conto titoli presso
  intermediario finanziario estero, che costituisce un **conto di
  liquidita' accessorio** al rapporto di investimento e sconta
  l'aliquota ordinaria dello 0,2% (prodotti finanziari, codice 20).
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

### Metodo di determinazione del costo per le partecipazioni

Per le partecipazioni (azioni, ETF, quote di fondi), la
[circolare AdE 165/E del 24/06/1998 §2.3.2][circ165] stabilisce che
la plusvalenza imponibile e':

> *"la differenza tra il corrispettivo percepito (ovvero la somma o
> il valore normale dei beni rimborsati) ed il costo (ovvero il
> valore) d'acquisto, aumentato di ogni onere inerente alla loro
> produzione, compresa l'imposta di successione e donazione, con
> esclusione degli interessi passivi."*
> — Circ. AdE 165/E/1998 §2.3.2

Nessuna presunzione FIFO o LIFO. La base imponibile e' il **costo
effettivo di acquisto del lotto ceduto**, documentato. La stessa
§2.3.2 applica invece LIFO **esplicito** e **mandatorio** a due
categorie distinte:

> *"Nel caso di cessione a pronti di valute estere prelevate da
> depositi e conti correnti, la base imponibile e' pari alla
> differenza tra il corrispettivo della cessione ed il costo della
> valuta, rappresentato dal cambio storico calcolato sulla base del
> criterio 'L.I.F.O.', costo che deve essere documentato dal
> contribuente."*
> — Circ. 165/E §2.3.2 (valute estere, depositi e conti correnti)

> *"Per quanto concerne la determinazione della base imponibile
> della cessione a titolo oneroso di titoli diversi da quelli
> partecipativi essa e' determinata per differenza tra il prezzo di
> cessione ed il costo di acquisto, calcolato sulla base del
> criterio del 'L.I.F.O.' ed incrementato degli oneri strettamente
> inerenti."*
> — Circ. 165/E §2.3.2 (obbligazioni e titoli non partecipativi)

La distinzione e' funzionale. LIFO si applica dove l'asset e'
fungibile per natura — valute, titoli di debito identici tra loro —
e l'identificazione specifica del singolo lotto ceduto non e'
possibile. Per le **partecipazioni**, ogni lotto e' tracciato
individualmente dal broker con data di acquisto e costo effettivo;
il broker registra di preciso quale lotto e' ceduto a ogni vendita
(secondo il matching method che il correntista ha configurato —
Tax Optimizer Schwab, "matching method" IBKR, o default
dell'account), e il P/L riportato nel `fifoPnlRealized` IBKR e nel
Year-End Summary Schwab e' il risultato della coppia
acquisizione-cessione effettiva.

**Cosa fa decaf.** Prende il P/L che il broker ha registrato sul
lotto effettivamente ceduto, lo converte in EUR, e lo mette in
riga RT. Questo e' il metodo **corretto** ex §2.3.2 — non una
semplificazione. (Per le valute estere — caso distinto — decaf
calcola invece in proprio LIFO per singolo conto, sempre ex §2.3.2.
Vedi [Forex LIFO gains](#forex-lifo-gains).)

La conversione in EUR segue art. 9 co. 2 TUIR: costo al cambio BCE
della data di acquisto (lotto per lotto), corrispettivo al cambio
BCE della data di regolamento. Vedi
[Conversione per-lotto](#conversione-per-lotto-art-9-co-2-tuir).

[circ165]: https://def.finanze.it/DocTribFrontend/getPrassiDetail.do?id=%7B223C9DB9-C064-4DDA-84B2-819A66817892%7D

### Conversione per-lotto — art. 9 co. 2 TUIR

**Norma.** Art. 9 co. 2 TUIR:

> *"I corrispettivi, i proventi, le spese e gli oneri in valuta
> estera sono valutati secondo il cambio del giorno in cui sono
> stati percepiti o sostenuti o del giorno antecedente piu'
> prossimo…"*
> — art. 9 co. 2 TUIR

Il costo di ciascun lotto va convertito al cambio BCE della **data
di acquisto del lotto**; il corrispettivo al cambio BCE della
**data di regolamento della vendita**.

**Come decaf lo implementa.** Per ogni vendita, il parser prende
dal broker la lista dei lotti chiusi (Closed Lots IBKR, RealizedLot
Schwab) — ognuno con la sua `acquisition_date`. `quadro_rt.py`
converte il costo di quel lotto al cambio BCE della data di
acquisto e il corrispettivo (quota parte proporzionale alla
quantita') al cambio BCE della data di regolamento. La plusvalenza
EUR e' la differenza, mai derivata dal P/L aggregato in valuta.

**Fallback.** Se manca un cambio BCE (giorni non lavorativi
pre-1999 o simili), decaf ripiega sul `fxRateToBase` IBKR e logga
un `WARNING`.

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

## Redditi di capitale esteri — Quadro RL vs Quadro RM

Interessi e dividendi di fonte estera (art. 44 TUIR) percepiti
direttamente dal contribuente — senza intermediario italiano che
operi da sostituto d'imposta — si possono dichiarare in due quadri
**mutuamente esclusivi**.

### Opzione 1: Quadro RM rigo RM12 (imposta sostitutiva 26%)

Art. 18 c. 1 TUIR + art. 27 c. 4 D.P.R. 600/1973. Si applica il 26%
di imposta sostitutiva sul dividendo o interesse al **netto** della
ritenuta estera gia' subita ("netto frontiera").

**Nessun credito d'imposta per imposte estere** ex art. 165 TUIR:
la circolare AdE 165/E/1998 §6 e la risposta a interpello n. 111/2020
confermano che la scelta del regime sostitutivo preclude il recupero
della ritenuta estera.

E' la via ordinaria per partecipazioni non qualificate e per interessi
percepiti da persona fisica al di fuori del regime d'impresa.

### Opzione 2: Quadro RL rigo RL2 + Quadro CE (tassazione ordinaria IRPEF)

Si dichiara l'importo **lordo** in RL2 colonna 2; il reddito si cumula
al reddito complessivo e sconta IRPEF ad aliquota marginale (23-43%
+ addizionali regionali e comunali).

Il credito per l'imposta estera si richiede nel Quadro CE ex art. 165
TUIR, nei limiti previsti dalle convenzioni contro le doppie
imposizioni.

### Scelta

Le due opzioni sono **mutuamente esclusive**: non e' consentito
dichiarare in RM12 e chiedere contestualmente il credito art. 165.
La scelta va effettuata per la totalita' dei redditi di capitale
esteri della stessa natura percepiti nell'anno, non per singola
entrata (circ. 165/E/1998 §6).

Per aliquote marginali IRPEF superiori al 26% RM12 e' generalmente
piu' conveniente sull'imposta italiana, ma preclude il recupero della
ritenuta estera. Il punto di indifferenza dipende da aliquota
marginale del contribuente e aliquota di ritenuta alla fonte prevista
dalla convenzione bilaterale. Il calcolo va fatto caso per caso.

### Cosa produce decaf

`src/decaf/quadro_rl.py` emette una tabella con `lordo_EUR`,
`ritenuta_EUR` e `netto_EUR` per ciascuna entrata (interesse o
dividendo), convertita al cambio BCE della data di percezione
(accredito). **Decaf non prescrive il quadro di destinazione** e non
compila automaticamente ne' RM12 ne' RL+CE: il contribuente sceglie
la via e riporta manualmente i totali.

---

## Forex LIFO gains

### Problema

Ne' IBKR ne' Schwab forniscono il P/L sulle conversioni valutarie:
- IBKR EUR.USD: `broker_pnl_realized = 0`, `cost = 0`
- Schwab wire transfers: non modellati come operazioni forex

Il calcolo va fatto autonomamente. La norma di riferimento e' art. 67
c. 1-bis TUIR, chiarito dalla risposta AdE n. 204/2023.

### Regola fiscale: LIFO per singolo conto

Art. 67 c. 1-bis TUIR, richiamato espressamente dalla risposta 204/2023:

> *"Agli effetti dell'applicazione delle lettere c), c-bis) e c-ter)
> del comma 1, si considerano cedute per prime ... le valute ...
> acquisite in data piu' recente."*

Quindi **LIFO**, non FIFO.

La medesima risposta 204/2023 precisa inoltre:

> *"la determinazione delle plusvalenze ... deve essere effettuata
> analiticamente e distintamente, per ciascun conto."*

Quindi il calcolo avviene **separatamente per ciascun conto**, senza
mescolare lotti di conti diversi. La soglia di EUR 51.645,69 / 7 giorni
lavorativi continui si valuta invece aggregando la giacenza di tutti i
conti in valuta estera del contribuente (stessa risposta 204/2023).

### Formula

Per ciascuna cessione di valuta (conversione EUR.USD o bonifico in
uscita):

```
gain_eur = USD_importo × (1/tasso_BCE_cessione - 1/tasso_BCE_acquisto)
```

Il cambio BCE si inverte perche' la BCE pubblica EUR/USD (dollari per
euro), mentre ai fini del calcolo serve il valore di un dollaro in
euro (1 / EUR/USD).

### Acquisizione USD (lotti in coda LIFO del conto)

- Proventi da vendita titoli in USD
- Dividendi e interessi in USD

### Cessione USD (consumo LIFO del conto d'origine)

- Conversioni EUR.USD su IBKR (FlexQuery, asset_category=CASH)
- Bonifici in uscita da Schwab o IBKR ("Wire Sent", "Wire Funds Sent", "Deposits/Withdrawals" con importo negativo)

### Giroconto cross-broker (matching implementato)

Risoluzione AdE 60/E del 09/12/2024: un giroconto in USD tra due conti
dello stesso soggetto e' fiscalmente neutro. Da v0.3.0 decaf accoppia
automaticamente un "Wire Sent" (o "Wire Funds Sent" /
"Deposits/Withdrawals" negativo) con un "Deposits/Withdrawals" positivo
su un altro conto quando coincidono valuta, importo (tolleranza 0,01
USD) e settle date (tolleranza ±3 giorni lavorativi). La coppia genera
un evento `TRANSFER` interno: i lotti USD migrano dalla coda LIFO del
conto di origine a quella del conto di destinazione, cronologicamente,
preservando data di acquisizione e cambio BCE originali. Nessuna
plusvalenza/minusvalenza viene generata sulla data del giroconto.

Matching ambiguo (piu' di un candidato positivo) logga un WARNING e fa
fallback al trattamento precedente (wire in uscita = cessione): in
quel caso il contribuente rettifica manualmente come prima. Caso
residuo fuori tolleranza (giroconto con settle date a distanza > 3
giorni lavorativi, caso raro): stesso fallback, rettifica manuale.

---

## Obbligazioni e altri titoli non partecipativi (fuori scope)

**Norma:** circ. AdE 165/E/1998 §2.3.2 richiede LIFO esplicito per le
cessioni di *titoli non partecipativi* (tipicamente obbligazioni).

> *"Per le valute estere e per i titoli non partecipativi,
> cedute (o ceduti) per primi si considerano quelle (quelli)
> acquisite (acquisiti) in data piu' recente."*
> — circ. 165/E/1998 §2.3.2

**Cosa fa decaf oggi:** `quadro_rt.py` non distingue *partecipazioni*
da *titoli non partecipativi*: applica a tutti i titoli non-forex la
stessa logica (P/L per-lotto ex art. 9 co. 2 TUIR sul lotto ceduto
secondo il matching method configurato lato broker). Per le
partecipazioni questo e' il metodo corretto ex §2.3.2; per
obbligazioni e altri titoli non partecipativi §2.3.2 richiede invece
LIFO esplicito, indipendentemente dalla scelta del contribuente.

**Perche' fuori scope:** decaf non e' back-testato su portafogli
obbligazionari: nessuna fixture, nessun riscontro contro
commercialista, nessuna garanzia di aderenza a §2.3.2 per questa
categoria. Un utente che detiene obbligazioni estere deve rettificare
manualmente le plusvalenze RT applicando LIFO, o astenersi dall'usare
decaf per il reporting di quelle posizioni. L'IVAFE (monitoraggio e
imposta patrimoniale) viene invece computata correttamente perche'
il Quadro RW usa gia' LIFO (vedi §Quadro RW §LIFO per lot matching).

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
| Forex LIFO gains per conto | `forex_gains.py` | Solo se soglia superata — art. 67 c. 1-bis TUIR + risposta 204/2023 |
| RT: costo effettivo del lotto ceduto | `quadro_rt.py` | Metodo §2.3.2 — `fifoPnlRealized` IBKR / Year-End Summary Schwab (P/L sul lotto scelto al broker). Residua semplificazione solo sul cambio ECB per lotto (vedi Semplificazioni) |
| Tasso BCE primario | `fx.py` | IB rates solo per validazione |
