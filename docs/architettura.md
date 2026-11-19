# Come è fatto il codice

Questa pagina segue una richiesta dentro il pacchetto `osservare_a_strati/`: da dove parte, quali moduli attraversa,
dove finisce. Serve a chi apre il codice per la prima volta e vuole sapere in quale file guardare.

## Una run, dall'inizio alla fine

`strati run --strato 5 --guasto` attraversa questi moduli, in quest'ordine:

1. **`cli.py`** legge le opzioni e le controlla (`--maschera` solo allo strato 5, `--produzione` dallo strato 2, una
   correzione implica `--guasto`). Ne fa un oggetto `Impostazioni` e lo rende quello corrente con `imposta()`.
2. **`registrazioni.py`** decide la cartella della run (`cartella_della_run`): `registrazioni/strato-N` più il suffisso
   della correzione, della maschera o della produzione.
3. **`esecuzione.py`** (`esegui`) è la run: apre lo span radice `invoke_workflow`, chiede il client, fa partire
   l'agente `coordina` con la domanda di Giulia, misura il tempo e alla fine scrive la registrazione in JSON.
4. **`osservabilita/client.py`** (`cliente`) costruisce il client Anthropic per lo strato corrente: allo strato 0 senza
   OpenTelemetry, dall'1 con il `TracerProvider` di `osservabilita/tracce.py`, le metriche di
   `osservabilita/metriche.py` e i log di `osservabilita/log.py`.
5. **`agenti/ciclo.py`** è il ciclo di ogni agente (`agente` e `ciclo`): chiama il modello, scrive la riga di log della
   chiamata e le metriche dei token, e se il modello chiede strumenti li esegue (`esegui_chiamate`). Più strumenti
   chiesti nello stesso giro girano in parallelo, in thread che ricevono il contesto OpenTelemetry di chi li lancia.
   Un agente usato come strumento passa da `chiama_agente`, con la guardia contro i cicli (`controlla_catena`).
6. **`agenti/strumenti.py`** (`leggi_dato`) risponde agli strumenti dei dati (`leggi_programma`, `leggi_sale`,
   `leggi_avvisi`) leggendo il caso in **`evento/`**. Le istruzioni degli agenti e gli schemi degli strumenti stanno in
   **`agenti/prompt.py`**.
7. **`stampa.py`** (`mostra`) stampa la registrazione a terminale. È la stessa funzione del replay.

## Il replay e l'analisi lavorano sulle registrazioni

Tutto quello che viene dopo una run legge il file JSON, mai il sistema dal vivo:

- `strati replay F` è `stampa.mostra` sulla registrazione letta da `registrazioni.leggi`. Mostra solo quello che lo
  strato di quella run aveva catturato.
- `analisi/span.py` legge gli span di una registrazione (archi fra agenti, token, forma dell'albero). Sopra di lui
  `analisi/misure.py` (riepilogo, misure, esito di ogni risposta), `analisi/schema.py` (il grafo di chi chiama chi),
  `analisi/segnali.py` (i segnali da cruscotto) e `analisi/controllo.py` (il controllo della settimana del talk).
- `valutazione.py` dice se una risposta è giusta, avvisata o sbagliata.
- `cruscotto/invio.py` rimanda le registrazioni a Tempo, Loki e Prometheus, con gli orari spostati ad adesso;
  `cruscotto/verifica.py` confronta i numeri del cruscotto con quelli di `analisi/segnali.py`.

## Dove stanno le righe di ogni strato

Le righe che esistono solo per osservare finiscono con `# sN`. Sono in sette file; gli altri moduli non ne hanno.

| file | s0 | s1 | s2 | s3 | s4 | s5 |
|---|---|---|---|---|---|---|
| `agenti/ciclo.py` | 10 | 9 | 13 | 11 | | |
| `esecuzione.py` | 7 | 3 | 5 | | | |
| `osservabilita/tracce.py` | | 7 | | | | 22 |
| `osservabilita/metriche.py` | | 7 | | | | |
| `osservabilita/client.py` | | 3 | | | | 2 |
| `osservabilita/log.py` | | | | 7 | | |
| `agenti/strumenti.py` | | | | | 8 | |
| **totale** (`strati righe`) | **17** | **29** | **18** | **18** | **8** | **24** |

La strumentazione sta in linea, nel punto in cui il lavoro succede: lo span `execute_tool` si apre dentro
`esegui_strumento`, la riga di log della chiamata si scrive subito dopo `client.messages.create`. Non ci sono
decoratori né hook.

Il controllo dello strato si legge così: `if attuali().strato >= 4:  # s4`. Per gli span c'è `tracer(n)`, che dà il
tracer vero dallo strato `n` in su e uno muto sotto: è impalcatura della demo, e `strati codice N` la toglie quando
estrae il codice per le slide. `righe.py` legge i sette file in un ordine fisso (`ORDINE`) e fa sia il conteggio sia
l'estrazione.

## Lo stato condiviso

- Le scelte della run stanno in un solo oggetto, `Impostazioni` (`impostazioni.py`): strato, correzione, maschera,
  produzione, indirizzo OTLP. Si imposta una volta all'avvio con `imposta()` e si legge ovunque con `attuali()`. È
  immutabile: per cambiarlo se ne imposta uno nuovo (nei test, `with con(strato=5):`).
- I provider OpenTelemetry sono globali di processo per natura. Li crea ciascuno il suo modulo (`fai_provider`,
  `fai_metriche`, `fai_log`), e nessun modulo assegna attributi di un altro. Chi usa uno stato che cambia lo legge
  attraverso il modulo (`metriche.TOKEN_IN`, `tracce.memoria`), mai importandolo per valore.

## I test

`tests/` ha un file per argomento (strumenti, valutazione, misure, schema, segnali, cruscotto, esecuzione, controllo,
CLI, righe). Girano su `tests/server_finto.py`, un server finto che risponde come l'API Anthropic: non serve rete né
chiave. `tests/riferimento.py` è la rete di sicurezza del riordino: rigenera le uscite della demo (replay, misure,
schema, segnali, invio al cruscotto, righe, codice, hash dei prompt) per confrontarle con quelle di prima.
