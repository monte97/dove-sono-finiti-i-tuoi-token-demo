# Rami paralleli: la giornata piena

Branch: `rami-paralleli`. Il sistema vecchio resta nel tag `tre-agenti-in-fila` (= `e6104c0`); il tag `banco-2026-11-06` non si tocca.

## Spec

La storia che la demo deve raccontare, e il criterio che il problema deve rispettare.

**Criterio.** Il problema si risolve facilmente solo osservando il sistema:
1. nessun componente sbaglia rispetto al proprio contratto: niente timeout, retry, fallback, eccezioni, `sleep` messi apposta;
2. nessun componente ha un indizio locale che qualcosa sia andato storto, quindi non c'è un flag da propagare;
3. la causa emerge solo dalla combinazione dei rami, visibile solo guardandoli insieme nella stessa trace;
4. una volta vista, la correzione è banale.

**Storia.** DevFest Immaginario 2026. Giulia Rossi (giulia.rossi@example.com) chiede: «A che ora è il workshop Kubernetes da zero?».
- Il programma pubblicato (ieri sera) dice: oggi, 15:00, sala B.
- Stamattina la sala B è stata chiusa dalle 15:00 per manutenzione e le sessioni pomeridiane in sala B iniziano un'ora prima. Lo sa **solo** un avviso, **indiretto**: parla della sala B, non nomina il workshop.
- Giornata **tranquilla** (modo `sana`): 3 pagine di avvisi, nessuno sulla sala B. Risposta giusta: 15:00.
- Giornata **piena** (modo `guasto`): 40 pagine di avvisi rumorosi ma plausibili; l'avviso sulla sala B sta a metà. Risposta giusta: 14:00. Il sistema risponde 15:00.

**Il sistema.** Cinque agenti: `coordina` (orchestratore) usa come strumenti gli agenti `programma`, `sale`, `avvisi` e `valida`.
- `programma` → `leggi_programma(sessione)`: giorno, ora, sala dal programma pubblicato.
- `sale` → `leggi_sale(sessione)`: sala, piano, capienza dal database delle sale. Niente orario.
- `avvisi` → `leggi_avvisi()`: tutte le comunicazioni di oggi, **tutte le pagine in una sola chiamata dello strumento** (il modello non sfoglia). Il suo contratto: riportare in al massimo tre righe gli avvisi più importanti per la richiesta ricevuta.
- `valida`: controlla la risposta contro il contesto che `coordina` le passa, come oggi; le sale sono A, B e C.
- `coordina` è istruito a consultare programma, sale e avvisi e poi far controllare la risposta da valida (consiglia, non impone). Quando il modello chiede più strumenti nello stesso giro, girano **in parallelo**.

Perché si sbaglia: in parallelo, `avvisi` riceve una richiesta sul workshop, non sa che è in sala B, e l'avviso sulla sala B per lui è uno fra tanti; non lo riporta. `coordina` compone «15:00, sala B», `valida` approva. I token in ingresso stanno quasi tutti in `avvisi`.

**Correzione.** `--correzione` (passo 1): solo istruzioni a `coordina`, che deve chiedere ad `avvisi` le comunicazioni sulla sala della sessione dopo averla saputa. `--correzione-completa` (passo 2): in più `leggi_avvisi` ha un parametro obbligatorio `sala` e restituisce solo gli avvisi di quella sala (una pagina). Si misurano correttezza e token.

**Il freeze** esce dal codice: niente `DOMINI`, niente `--dominio`.

**Fatto verificato il 5/11:** l'SDK `anthropic` 1.15.0 (`_tracing.py`) scrive il contenuto solo come attributi di span (`gen_ai.input.messages`, `gen_ai.output.messages`); nessun evento, nessun log, nessuna metrica.

## Global Constraints

- Un solo file di demo, `strati.py`. Fissi: `MODEL = "claude-haiku-5-5"`, `anthropic==1.15.0`, `thinking=PENSIERO` a ogni chiamata, `LISTINO` invariato.
- Sei strati, `--strato 0..5`, ognuno contiene i precedenti. Ogni riga che esiste solo per osservare finisce con `# sN`; `--righe` e `--codice` devono restare corretti. Il parallelismo è codice applicativo: non si marca. La propagazione del contesto ai thread si marca `# s2`.
- Titoli degli strati: 0 «oggi: un log e una fattura», 1 «l'SDK», 2 «gli agenti», 3 «lo strumento», 4 «i dati letti», 5 «il contenuto».
- Strato 3: span `execute_tool <strumento>` con argomenti e risultato (come oggi), più i **log correlati**: lo strumento scrive righe con il `logging` di Python (logger `osservare-a-strati`), e dallo strato 3 un `LoggingHandler` OpenTelemetry le esporta con `trace_id` e `span_id`. Le righe che collegano il logging a OTel si marcano `# s3`.
- Strato 4: sugli span degli strumenti di dati, da dove viene il dato e quanto: per `leggi_programma` la data di pubblicazione del programma; per `leggi_avvisi` pagine lette, avvisi letti, filtro usato (nessuno o la sala), ora dell'ultimo aggiornamento. `cache.read`, interruttore, `TIMEOUT_S`, `FINESTRA_S`, `ETA_COPIA_ORE` spariscono.
- Strato 5: `content_mode="content"` e `MascheraEmail` come oggi (`--maschera`).
- Attributi: convenzioni semantiche OpenTelemetry dove esistono (`gen_ai.*`); quelli inventati con un prefisso proprio (es. `avvisi.pagine`, `programma.pubblicato_il`) e dichiarati in un commento.
- Le registrazioni nuove hanno la stessa forma JSON di oggi (`strato`, `correzione`, `maschera`, `registrata`, `modo` in `{"guasto","sana"}`, `modello`, `domanda`, `risposta`, `log`, `fattura`, `secondi`, `span`) più `log_otel` (lista dei record di log correlati: `trace`, `span`, `livello`, `testo`). Il campo `dominio` sparisce. Il codice nuovo non legge le registrazioni vecchie.
- Privacy: email solo `example.com`, `ID_ACCOUNT` oscurati come oggi, nessuna chiave nel repo.
- Leggibilità: una run guasta allo strato 5 non supera indicativamente 40 span.
- Test senza rete: `.venv/bin/python test_strati.py` e `.venv/bin/python test_segnali.py` passano. Lo stile dei test resta quello attuale (funzioni `test_*` eseguite dal `__main__` del file, server finto con `httpx.MockTransport`).
- Commenti e messaggi in italiano, come il resto del repo. Commit piccoli, messaggi in italiano.

## Task 1: la giornata, gli agenti e gli strumenti (ancora in sequenza)

Riscrivere il dominio in `strati.py` secondo la Spec, **senza ancora il parallelismo**:
- Dati: `PROGRAMMA` (Kubernetes da zero: oggi 15:00 sala B; OpenTelemetry in un'ora: oggi 11:00 sala A; Rust per chi scrive Go: domani 16:30 sala C; pubblicato «4/11 alle 18:00»), `SALE` (A, B, C con piano e capienza; mappa sessione → sala), `AVVISI` generati in modo deterministico (seed fisso): `avvisi(piena: bool) -> list[pagina]`, 10 avvisi per pagina, 3 pagine nella tranquilla e 40 nella piena. Rumore plausibile e vario (guardaroba, wifi, pranzo, sponsor, badge, parcheggio, una keynote spostata, una sessione di domani annullata, prova dell'allarme alle 11, ecc.); nessun avviso nomina il workshop né un orario del workshop. Nella piena l'avviso chiave sta a pagina 23: «Sala B: chiusa dalle 15:00 per manutenzione dell'impianto elettrico. Le sessioni del pomeriggio in sala B iniziano un'ora prima dell'orario in programma.» Costanti in testa al file così la taratura le cambia in un punto: `PAGINE_PIENA = 40`, `PAGINE_TRANQUILLA = 3`, `PAGINA_AVVISO = 23`, `AVVISI_PER_PAGINA = 10`.
- Strumenti `leggi_programma`, `leggi_sale`, `leggi_avvisi` con schemi; agenti `programma`, `sale`, `avvisi`, `valida` come strumenti di `coordina` (stesso meccanismo «agent as a tool» di oggi, con l'arco `execute_tool <agente>` dello strato 2 e `invoke_agent` dentro). Istruzioni nuove per i cinque agenti, scritte «come le scriverebbe un team».
- Esito per modo: nella piena `sbagliata = "15:00" in r and "14:00" not in r`, `giusta` il contrario; nella tranquilla `giusta = "15:00" in r and "14:00" not in r`, `sbagliata` il contrario.
- `--correzione` e `--correzione-completa` come nella Spec. Le cartelle delle registrazioni restano `strato-N[-correzione|-correzione-completa][-maschera][-produzione]`.
- Togliere: `DOMINI`, `--dominio`, `cerca`, `servizio()`, `leggi_dato()`, la copia, l'interruttore, le regex del freeze, `DICE_ETA`/`AVVISO`/`DICE_TIMEOUT` se non servono più.
- Aggiornare docstring del modulo, `TITOLI`, `mostra()`/`verbale()` per i nomi nuovi (`cache.read` sparisce dal verbale).
- `test_strati.py`: server finto nuovo che simula `coordina` (chiama programma, sale, avvisi, poi valida, poi risponde) e i tre agenti; i test per strato riscritti sulla nuova forma (strato 0 solo log e fattura; 1 una trace per chiamata, niente contenuto; 2 una trace sola con gli archi verso i quattro agenti; 3 gli span degli strumenti con argomenti e risultato; 5 contenuto ed email; maschera). I test del freeze e della copia si tolgono. Le funzioni di misura (`esito`, `misura`, `misure`, `riepilogo`) possono restare provvisoriamente rotte per i campi vecchi solo se non toccate dai test di questo task; il Task 4 le riscrive.

## Task 2: il parallelismo vero

In `ciclo()`: quando una risposta del modello contiene più `tool_use`, eseguirli in parallelo con `concurrent.futures.ThreadPoolExecutor`, propagando il contesto OpenTelemetry a ogni thread (`contextvars.copy_context().run`), con i risultati restituiti al modello nell'ordine dei `tool_use`. `stato["fattura"]` e ogni altra struttura condivisa protetti da un lock. Una sola chiamata: nessun thread.
Test: con il server finto che chiede programma, sale e avvisi nello stesso giro, i tre `execute_tool` degli archi hanno lo stesso padre (`invoke_agent coordina`), gli intervalli si sovrappongono (il server finto o gli strumenti finti devono durare abbastanza da renderlo deterministico, per esempio uno `sleep` breve **solo nel test**), e la trace è una sola.

## Task 3: strati 3 e 4, log correlati

- Strato 4 come nei Global Constraints, sugli span `execute_tool` degli strumenti di dati.
- Log correlati come nei Global Constraints: `LoggerProvider` con un exporter in memoria (come `memoria` per gli span) e, con `--otlp URL`, anche l'export OTLP dei log (stesso host, path `/v1/logs`). Il record entra in `log_otel` della registrazione. Righe di log: almeno `leggi_avvisi: N pagine, M avvisi, filtro …` e `leggi_programma: <sessione> dal programma pubblicato il …`. Sotto lo strato 3 i log non hanno contesto (`log_otel` vuoto).
- `mostra()`: dallo strato 3 una sezione «log con contesto» che stampa ogni record con il `span` a cui appartiene (nome dello span, non solo l'id).
- Test: allo strato 3 ogni record ha `trace` uguale a quello della run e `span` uguale all'id dello span `execute_tool leggi_avvisi`/`leggi_programma`; allo strato 2 `log_otel` è vuoto; allo strato 4 gli attributi del dato ci sono, allo strato 3 no. `--righe` conta le righe nuove negli strati giusti.

## Task 4: misure e segnali

- `strati.py`: `esito`, `misura`, `misure`, `riepilogo`, `grafo` riscritti per la storia nuova. `misura` deve dire, per run: grafo, se programma/sale/avvisi sono partiti nello stesso giro (archi sovrapposti nel tempo con lo stesso padre), quante pagine ha letto `avvisi`, se l'uscita di `leggi_avvisi` conteneva l'avviso sulla sala B, se l'uscita dell'agente `avvisi` verso `coordina` lo riporta (regex su «sala B» insieme a chiusura/manutenzione/un'ora prima), se `avvisi` è stato chiamato dopo che `coordina` sapeva la sala, verdetti di `valida`, esito, token per agente e quota di `avvisi`, email a `valida`. `misure` stampa i conteggi su 30 nello stile di oggi.
- `segnali.py`: i segnali nuovi, ciascuno con il suo strato minimo: `forma` (2), `costo` (1), `quota_avvisi` (quota dei token della richiesta spesa dall'agente `avvisi`, 2), `pagine` (pagine di avvisi lette, 4), `approva` (3). Spariscono `ritenta`/`richiamati` e `copia`. `riassunto()` scrive sulla radice `richiesta.forma`, `richiesta.costo_microusd`, `richiesta.quota_avvisi_pct`, `richiesta.pagine_avvisi`. `cruscotto()` e `stampa()` di conseguenza.
- `test_segnali.py`: i test che leggono `archivio/2026-10-28` si tolgono (sistema vecchio); restano e si adattano quelli su run finte, più un test di coerenza fra `segnali()` e `misura()` su una run finta generata dal server finto di `test_strati.py` o costruita a mano.
- `tempo.py` e `controllo.py` adattati (in `controllo.py` i casi: strato 5 guasta e sana, correzione, correzione completa; strato 1 per l'SDK). `verifica_cruscotto.py` adattato ai segnali nuovi.

## Task 5: il cruscotto con i log

- `cruscotto/compose.yaml`: aggiungere un OpenTelemetry Collector (riceve OTLP HTTP sulla porta esterna 4418, manda le trace a Tempo e i log a Loki) e Loki; Tempo non espone più OTLP all'esterno. Immagini con versione esatta.
- Grafana: datasource Loki; sul datasource Tempo la configurazione trace-to-logs (dallo span ai log con lo stesso trace id); il cruscotto `segnali.json` riscritto sui segnali nuovi (quota di `avvisi`, pagine lette, forme, approvazioni, costo mediana e p95) con query TraceQL sugli attributi `richiesta.*` della radice.
- `tempo.py` rimanda anche i `log_otel` delle registrazioni (con trace id coerenti con quelli rimappati degli span).
- Verifica: `docker compose up -d` nel cruscotto, una run `--strato 5 --guasto --otlp http://localhost:4418/v1/traces` (o `tempo.py` su una registrazione), e controllo via API che Tempo abbia la trace e Loki i log con quel trace id. Se una run vera non è possibile senza chiave, si usa `tempo.py` su una registrazione prodotta dai test.

## Task 6: README e documentazione

- `README.md` riscritto sulla giornata piena: la storia, i cinque agenti, i sei strati con il nuovo strato 4 e i log allo strato 3, i comandi, il cruscotto con Loki, come rifare il banco, il tag `tre-agenti-in-fila` per il sistema vecchio.
- `docs/banco-rami-paralleli.md`: lo scheletro della tabella dei numeri (righe da riempire dopo il banco, ciascuna con il comando che la riproduce): durata e costo guasta contro sana allo strato 0; token per richiesta e quota di `avvisi`; costo per agente; quota delle riletture; sbagliate su 30 guasta e sana; run in cui `avvisi` omette l'avviso; verdetti di `valida`; run con i tre rami nello stesso giro e forme dell'albero; effetto dei due passi della correzione su correttezza e costo. Più il fatto sull'SDK della Spec.
