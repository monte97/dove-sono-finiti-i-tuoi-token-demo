# Orchestratore e misure entro il 2/11 — piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La demo del talk diventa l'orchestratore `coordina` (variante B). Su B si misurano la correzione e il dominio freeze. Per lo strato 5 si aggiungono la maschera dell'email e gli estratti di codice puliti per strato.

**Architecture:** Resta un file solo, `strati.py`, con lo stesso schema: globali `STRATO` e (nuovo) `DOMINIO` impostati dal `main`, ciclo dell'agente scritto a mano, righe di osservazione marcate `# sN`. Fissa, A e tool runner escono dal codice e restano nella storia git (tag `spike-a-b`). Il dominio diventa un dizionario in `DOMINI`, così l'orario e il freeze condividono il codice e il guasto.

**Tech Stack:** Python 3.14, `anthropic==1.15.0`, `opentelemetry-sdk==1.44.0`, test senza rete con `httpx2.MockTransport` (`python test_strati.py`).

**Spec:** `/Users/monte97/Documents/1_AETE/0_Content/_talks/devfest-alps-2026/observability-agenti-otel-storia.md` (D26, sezioni «La demo», «Lavoro, in ordine», «Rischi che restano»).

## Global Constraints

- Modello `claude-haiku-5-5`, `PENSIERO = {"type": "adaptive", "display": "summarized"}`, `MAX_GIRI = 6`: non cambiano.
- Guasto invariato: timeout di 2 s, poi per 120 s la copia di ieri; età 26 ore solo sullo span `cache.read` (salvo `--correzione`).
- Nessuna chiave nel repo: vive solo in `.env`, ignorato. Mai stamparla.
- `anthropic.organization.id`, `anthropic.workspace.id`, `anthropic.request.id` diventano `"oscurato"` prima di stampa e salvataggio (`in_dict`, già così).
- Email solo finte, `@example.com`. Le registrazioni normali tengono l'email in chiaro; solo `--maschera` la toglie.
- Ogni riga che esiste solo per osservare finisce con `# sN`; `--righe` deve continuare a contarle.
- Testi a schermo, commenti e commit in italiano, nello stile del file.
- Commit locali, nessun push.
- Ogni banco che chiama l'API spende denaro: si lancia solo nei passi che lo prevedono, con il numero di run scritto lì.

## Review Focus

1. **Freeze, argomento libero.** `coordina` può chiedere a `cerca` «deploy del servizio pagamenti» e `cerca` passare «servizio pagamenti» allo strumento. Lo strumento deve trovare `pagamenti` per sottostringa, come oggi trova il titolo. Test in Task 3.
2. **Email dentro JSON.** L'email sta anche dentro `gen_ai.input.messages`, che è JSON serializzato, e dentro gli argomenti degli archi fra agenti. La maschera deve coprire ogni attributo stringa, non solo quelli con l'email «nuda». Test in Task 5.
3. **Esito per dominio.** `misura` oggi conta `15:00`/`14:00` scritti nel codice. Sul freeze deve dire giusta o sbagliata con il predicato del dominio, senza contare per sbagliata una risposta che dice di non poter confermare. Test in Task 3.
4. **Correzione che si perde al confine.** Con `--correzione` l'età arriva a `cerca`. Va misurato se arriva anche a `valida`, cioè nel contesto o nella risposta che `coordina` le passa: è il numero che decide dove va la correzione. Test in Task 4.
5. **Replay di registrazioni vecchie.** Un file di `strato-N-A/` o `strato-1-runner/` ripreso dalla storia git deve ancora stampare con `--replay`, senza errore sul campo `variante`. Test in Task 1.

---

### Task 1: B è la demo; fissa, A e runner escono

**Files:**
- Modify: `strati.py` (docstring, `TITOLI`, costanti delle istruzioni, `esegui`, `mostra`, `misure`, `main`; via `ciclo_runner`, `CERCA_A`, `chiedi_verifica`)
- Modify: `test_strati.py`
- Modify: `README.md`
- Move: `registrazioni/strato-{2,4,5}-B/` → `registrazioni/strato-{2,4,5}/`; elimina dall'albero `strato-{0..5}/` della fissa, `strato-*-A/`, `strato-1-runner/`

**Interfaces:**
- Produces: `esegui(guasto: bool, cartella: Path, client=None) -> dict` (senza `runner` e `variante`). La registrazione non ha più il campo `variante`. `misure(cartelle: list[Path])` resta. `--misure STRATO` legge `registrazioni/strato-STRATO*` (ogni cartella che inizia così). `TITOLI[2] == "gli agenti"`. `VALIDA` è il testo dell'attuale `VALIDA_AGENTI` (con il contesto); `AGENTI_STRUMENTO = {"valida": ("valida", VALIDA, []), "cerca": ("cerca", CERCA, ["leggi_programma"])}`.

- [ ] **Step 1: Tag e merge.** `git tag spike-a-b grafo-del-modello && git checkout main && git merge --ff-only grafo-del-modello`. Atteso: fast-forward a `4db7154`.
- [ ] **Step 2: Riscrivi i test per B.** Con il server finto attuale B fa 7 chiamate: `coordina`→`cerca`, timeout, ritenta, `cerca` risponde, `coordina`→`valida`, `valida` risponde, `coordina` risponde. Cambi:
  - `test_strato_0_…`: `reg["fattura"]["chiamate"] == 7`, e `VISTE[-7:]` senza `traceparent`.
  - `test_strato_1_…`: `nomi(reg) == ["anthropic.messages.create"] * 7`, `esito(reg)["tracce"] == 7`, `VISTE[-7:]` con `traceparent`.
  - `test_strato_2_una_trace_sola`: in più `"execute_tool valida" in nomi(reg)` e `"execute_tool cerca" in nomi(reg)`, senza `gen_ai.tool.call.arguments`. Assorbe `test_strato_2_le_varianti_…`, che si elimina.
  - `test_strato_3_…`: in più, sullo span `execute_tool valida`, `gen_ai.tool.call.arguments` presente.
  - `test_strato_5_…`: `"pensiero di coordina:" in fuori`.
  - `test_variante_b_orchestratore` diventa `test_orchestratore_grafo`, con le stesse asserzioni e `corri(5)`.
  - Eliminati: `test_strato_1_con_il_tool_runner`, `test_variante_a_…`, `test_strato_4_varianti_…`.
  - `corri(strato, guasto=True)` senza `runner` e `variante`.
- [ ] **Step 3: Test del replay vecchio** (Review Focus 5): `test_replay_registrazione_dello_spike` costruisce un `reg` da `corri(3)`, gli aggiunge `"variante": "A"` e controlla che `s.mostra(reg, registrata=True)` non sollevi eccezioni e stampi `variante A` nell'intestazione.
- [ ] **Step 4: Esegui i test.** Comando: `.venv/bin/python test_strati.py`. Atteso: falliscono, perché `esegui` ha ancora la vecchia firma.
- [ ] **Step 5: Togli dal codice fissa, A e runner.**
  - In `esegui` resta solo il ramo B: `agente(client, "coordina", COORDINA, DOMANDA, stato, ["cerca", "valida"])`.
  - `stato` perde `runner`, `agente` chiama sempre `ciclo`.
  - `mostra` legge `reg.get("variante")` come oggi, così il replay vecchio funziona.
  - `TITOLI[2] = "gli agenti"`.
  - Docstring e `--help` descrivono solo l'orchestratore.
  - Nel `main` niente `--variante`, niente `--runner`, cartella `registrazioni/strato-N`.
- [ ] **Step 6: Esegui i test.** Comando: `.venv/bin/python test_strati.py`. Atteso: `ok` per ogni test.
- [ ] **Step 7: Sposta le registrazioni.** Con `git mv`, `strato-N-B` diventa `strato-N`. Con `git rm -r`, via la fissa, A e il runner. Poi `--misure 5`: stampa una sezione `strato-5` con `guasto: n 30 … 3 grafi diversi`, uguale alla tabella B di oggi.
- [ ] **Step 8: Registra gli strati che mancano** (spesa: 21 run, circa $0.02).
  ```bash
  for n in 0 1 3; do .venv/bin/python strati.py --strato $n --guasto --banco 5; .venv/bin/python strati.py --strato $n --banco 2; done
  ```
  Dopo, `--riepilogo` ha una riga per ogni strato da 0 a 5, guasto e sana. Controllo: `grep -rc '"anthropic.workspace.id": "oscurato"' registrazioni | tail -3` ha conteggi > 0, e `grep -rL oscurato registrazioni/strato-1` non stampa niente.
- [ ] **Step 9: README.** Una sola sezione sull'orchestratore, al posto di «Varianti». La tabella degli strati con lo strato 2 «agenti e archi fra agenti». Una riga sul tag `spike-a-b`, dove stanno fissa, A e runner.
- [ ] **Step 10: Commit.** `git add -A && git commit -m "L'orchestratore è la demo: fissa, A e runner restano nel tag spike-a-b"`

### Task 2: Il dominio diventa un dizionario

**Files:**
- Modify: `strati.py` (costanti del dominio, `leggi_programma`, `esegui_strumento`, `misura`, `grafo`, `main`)
- Modify: `test_strati.py`

**Interfaces:**
- Consumes: Task 1 (`esegui` senza variante).
- Produces:
  - `DOMINI: dict[str, dict]` con le chiavi `domanda, oggi, ieri, cerca, coordina, valida, strumento, campo, descrizione, cartella, sbagliata, giusta`.
    - `strumento` è il nome dello strumento: `"leggi_programma"` per l'orario.
    - `campo` è il nome del parametro: `"sessione"`.
    - `sbagliata` e `giusta` sono predicati `Callable[[str], bool]` sulla risposta.
    - `cartella` è il suffisso: `""` per l'orario, `"-freeze"` per il freeze.
  - Globale `DOMINIO = DOMINI["orario"]`, opzione `--dominio {orario,freeze}`.
  - `leggi_dato(chiave: str, stato: dict) -> dict` sostituisce `leggi_programma`. Span `execute_tool {DOMINIO['strumento']}`, `gen_ai.tool.name` uguale.
  - `misura(r)["ora"]` diventa `misura(r)["esito"] in {"sbagliata", "giusta", "non conferma", "altro"}`.
  - Il blocco dei conteggi in `misure` stampa `sbagliata N · giusta N · non conferma N · altro N`.

- [ ] **Step 1: Scrivi il test.** `test_dominio_orario_invariato`: `corri(5)` dà lo stesso grafo del Task 1 (`… cerca>leggi_programma! cerca>leggi_programma coordina>valida`) e `s.misura(reg)["esito"] == "sbagliata"`. In più, `s.DOMINI["orario"]["sbagliata"]("Oggi alle 15:00, sala B.")` è vero, e `s.DOMINI["orario"]["giusta"]("Oggi alle 14:00, sala B.")` è vero.
- [ ] **Step 2: Esegui i test.** Atteso: FAIL, perché `DOMINI` non è definito.
- [ ] **Step 3: Sposta le costanti in `DOMINI["orario"]`.**
  - Tutto ciò che è scritto per l'orario finisce in `DOMINI["orario"]`: domanda, programma, copia di ieri, istruzioni, schema, descrizione dello strumento.
  - Predicati: `sbagliata = "15:00" in t and "14:00" not in t`, `giusta = "14:00" in t and "15:00" not in t`.
  - `esito`: «sbagliata» o «giusta» dai predicati; altrimenti «non conferma» se `NON_CONFERMA` trova qualcosa; altrimenti «altro».
  - `grafo` e il conteggio delle riprove usano `DOMINIO['strumento']` al posto di `"leggi_programma"`.
  - `SCHEMI` e `AGENTI_STRUMENTO` si costruiscono da `DOMINIO` con una funzione `schemi() -> dict`, chiamata in `ciclo`, così cambiano se cambia il dominio.
- [ ] **Step 4: Esegui i test.** Comando: `.venv/bin/python test_strati.py`. Atteso: tutti ok. Poi `--misure 5` dà gli stessi numeri del Task 1, con `sbagliata 30` al posto di `15:00 30`.
- [ ] **Step 5: Commit.** `git commit -am "Il dominio diventa un dizionario: stesso codice per orario e freeze"`

### Task 3: Il freeze, misurato su B

**Files:**
- Modify: `strati.py` (`DOMINI["freeze"]`)
- Modify: `test_strati.py` (il server finto risponde anche per il freeze)

**Interfaces:**
- Consumes: Task 2 (`DOMINI`, `DOMINIO`, `--dominio`).
- Produces: `DOMINI["freeze"]` e le registrazioni in `registrazioni/strato-5-freeze/`.

Valori, dal pilota del 25/10 (`5_conferenze/…/pilota-domini-2026-10-25/pilota.py`, dominio `freeze`):
- `domanda`, `oggi`, `ieri`, `cerca`, `valida`: identici al pilota. A `valida` si aggiunge solo la frase sul contesto che ha già `VALIDA` dell'orario: «Ricevi la domanda, la risposta e, se c'è, il contesto su cui si basa» e «… pertinente alla domanda e coerente con il contesto».
- `coordina`: «Sei l'assistente della piattaforma interna di Negozio Immaginario e coordini due agenti: cerca trova le informazioni sul calendario dei freeze, valida controlla una risposta prima che arrivi allo sviluppatore. Prima di rispondere allo sviluppatore, fai controllare la risposta da valida. Rispondi in una riga.»
- `strumento = "leggi_calendario"`, `campo = "servizio"`. Descrizione: «Legge dal calendario dei freeze se un servizio si può rilasciare in questo momento.»
- La descrizione dell'agente `cerca` per `coordina`: «Agente che trova informazioni sul calendario dei freeze dei servizi leggendo il servizio del calendario. Restituisce una risposta in una riga.»
- Predicati:
  - `sbagliata(t)`: vero se la risposta dà il via libera e non nomina il freeze. Regex `\b(sì|puoi|via libera|nessun freeze|non è in freeze)\b`, e nessuna di `freeze in corso|in freeze|non puoi|bloccat|sospes`.
  - `giusta(t)`: vero se trova `in freeze|freeze in corso|non puoi|bloccat|sospes`.

- [ ] **Step 1: Scrivi i test.**
  - `test_freeze_argomento_libero` (Review Focus 1): con `s.DOMINIO = s.DOMINI["freeze"]` e lo stato sano, `s.leggi_dato("servizio pagamenti", stato)["freeze"] is True`.
  - `test_freeze_esito`:
    - `sbagliata("Sì, puoi fare il deploy di pagamenti adesso.")` è vero;
    - `giusta("No, pagamenti è in freeze fino a lunedì 08:00.")` è vero;
    - `misura` su una risposta «Non riesco a confermarlo, il calendario non ha risposto.» dà `esito == "non conferma"`.
  - `test_freeze_grafo`: `corri(5)` con il dominio freeze, e il server finto che chiama lo strumento con `{"servizio": "pagamenti"}` quando nei tool c'è `leggi_calendario`. Il grafo contiene `cerca>leggi_calendario!`, e lo span `cache.read` ha `cache.age_hours == 26`. Dopo il test, `s.DOMINIO` torna a `DOMINI["orario"]`.
- [ ] **Step 2: Esegui i test.** Atteso: FAIL, perché `KeyError: 'freeze'`.
- [ ] **Step 3: Aggiungi `DOMINI["freeze"]`** con i valori sopra. Nel server finto, il nome dello strumento e l'argomento si leggono da `corpo["tools"]`, non sono più scritti nel test.
- [ ] **Step 4: Esegui i test.** Comando: `.venv/bin/python test_strati.py`. Atteso: tutti ok.
- [ ] **Step 5: Il banco** (spesa: 35 run, circa $0.035).
  ```bash
  .venv/bin/python strati.py --dominio freeze --strato 5 --guasto --banco 30
  .venv/bin/python strati.py --dominio freeze --strato 5 --banco 5
  .venv/bin/python strati.py --misure 5
  ```
  Si annotano, per il report, i conteggi della sezione `strato-5-freeze`: riprova, sbagliata, giusta, non conferma, `valida` approva, grafi diversi. Il pilota sulla fissa dava riprova 2/30 e 0/30. Si legge a mano la registrazione con più span e una in cui riprova, se c'è.
- [ ] **Step 6: Commit.** `git add -A && git commit -m "Freeze sull'orchestratore: 30 run guaste e 5 sane"`. Il messaggio contiene i conteggi letti al passo 5.

### Task 4: La correzione, misurata su B

**Files:**
- Modify: `strati.py` (`leggi_dato`, `esegui`, `misura`, `main`)
- Modify: `test_strati.py`

**Interfaces:**
- Consumes: Task 2 (`DOMINIO`, `leggi_dato`).
- Produces:
  - Opzioni `--correzione` e `--correzione-completa`. La seconda implica la prima, ed entrambe implicano `--guasto`.
  - Globale `CORREZIONE: int` (0, 1 o 2), impostato dal `main` come `STRATO`.
  - Cartelle `registrazioni/strato-N{dominio}-correzione/` e `…-correzione-completa/`.
  - In `misura` due campi nuovi: `avvisa: bool` (la risposta finale avvisa) e `valida_sa_eta: int` (`DICE_ETA` trova qualcosa nell'ingresso di `valida` o negli argomenti dell'arco verso `valida`).

Valori, dal repo vecchio `assistente-evento-otel/assistente.py`:
- Con `CORREZIONE >= 1` lo strumento restituisce `{**dato, "aggiornato": f"{ETA_COPIA_ORE} ore fa"}`. Le istruzioni di `cerca` ricevono in coda la stringa del dominio: per l'orario `" Se il dato del programma non è aggiornato, dillo nella risposta."`, per il freeze `" Se il dato del calendario non è aggiornato, dillo nella risposta."`
- Con `CORREZIONE == 2` le istruzioni di `valida` ricevono in coda: `" Se la risposta o il contesto dicono che il dato non è aggiornato, non scrivere «Verificato.»: scrivi che il dato va confermato."` Testo adattato da me: in B `valida` risponde a `coordina`, non all'utente.
- `AVVISO = re.compile(r"ieri|vecchi|26 ore|non è aggiornat|non (riesco|posso) (a )?conferm|ricontroll|va confermat", re.I)` decide `avvisa`.
- Nessuna regola a `coordina`. Dove va la correzione lo decide lo speaker sui numeri del passo 5 (storia, «Aperte»).

- [ ] **Step 1: Scrivi il test.** `test_correzione_l_eta_arriva_a_cerca` (Review Focus 4): con `s.CORREZIONE = 1`, `corri(5)`; il risultato del secondo `execute_tool leggi_programma` contiene `"aggiornato": "26 ore fa"`; `misura` ha le chiavi `avvisa` e `valida_sa_eta`. Con `s.CORREZIONE = 2`, le istruzioni di `valida` che arrivano al server finto (campo `system`, lette in `VISTE` o in una lista nuova di corpi) finiscono con «va confermato.». Dopo il test, `s.CORREZIONE = 0`.
- [ ] **Step 2: Esegui i test.** Atteso: FAIL, perché `CORREZIONE` non esiste.
- [ ] **Step 3: Implementa.** Le righe della correzione non sono osservazione: non portano il marcatore `# sN`.
- [ ] **Step 4: Esegui i test.** Comando: `.venv/bin/python test_strati.py`. Atteso: tutti ok.
- [ ] **Step 5: Il banco** (spesa: 60 run, circa $0.06).
  ```bash
  .venv/bin/python strati.py --strato 5 --correzione --banco 30
  .venv/bin/python strati.py --strato 5 --correzione-completa --banco 30
  .venv/bin/python strati.py --misure 5
  ```
  Si annotano, per ciascuna cartella: `avvisa`, `valida_sa_eta`, `valida approva`, sbagliata, grafi diversi. Il riferimento sulla fissa è «avvisa ma `valida` approva» al primo passo, e 0/30 approvazioni al secondo.
- [ ] **Step 6: Commit.** `git add -A && git commit -m "Correzione sull'orchestratore: …"`, con i conteggi.

### Task 5: La maschera dell'email

**Files:**
- Modify: `strati.py` (classe nuova vicino al provider, `main`)
- Modify: `test_strati.py`

**Interfaces:**
- Produces:
  - `class MascheraEmail(SpanProcessor)`: `__init__(self, prossimo: SpanProcessor)`. In `on_end(span)` passa a `prossimo.on_end` un `ReadableSpan` nuovo, con gli stessi campi e ogni attributo stringa (anche dentro le sequenze) passato per `EMAIL.sub("[email]", v)`. `on_start`, `shutdown` e `force_flush` delegano a `prossimo`.
  - Opzione `--maschera`, valida solo con `--strato 5`. Il provider usa `MascheraEmail(SimpleSpanProcessor(memoria))` al posto di `SimpleSpanProcessor(memoria)`. Il provider si costruisce in una funzione `fai_provider(maschera: bool) -> TracerProvider`, chiamata da `cliente()`. Cartella `registrazioni/strato-5-maschera/`.
  - Le righe della classe portano `# s5`.

- [ ] **Step 1: Scrivi il test.** `test_maschera_email` (Review Focus 2): con la maschera, `corri(5)` dà `s.con_email(reg["span"]) == 0` e `"[email]"` in almeno un `gen_ai.input.messages` e negli argomenti di `execute_tool cerca`. Senza maschera, lo stesso `corri(5)` dà `con_email > 0`. Gli id restano `"oscurato"`.
- [ ] **Step 2: Esegui i test.** Atteso: FAIL, perché `MascheraEmail` non è definita.
- [ ] **Step 3: Implementa.** `ReadableSpan(name=, context=, parent=, resource=, attributes=, events=, links=, kind=, status=, start_time=, end_time=, instrumentation_scope=)`: è la firma di `opentelemetry-sdk` 1.44.0, verificata il 28/10.
- [ ] **Step 4: Esegui i test.** Comando: `.venv/bin/python test_strati.py`. Atteso: tutti ok. Poi `--righe`: lo strato 5 ha più righe di prima.
- [ ] **Step 5: Una run registrata per la scena** (spesa: circa $0.001): `.venv/bin/python strati.py --strato 5 --guasto --maschera`. A schermo non compare l'avviso «attenzione: l'email…».
- [ ] **Step 6: Commit.** `git add -A && git commit -m "Maschera dell'email: uno SpanProcessor, ultimo gesto dello strato 5"`

### Task 6: Il codice pulito per strato, per le slide

**Files:**
- Modify: `strati.py` (funzione `codice(n)`, opzione `--codice N`)
- Modify: `test_strati.py`, `README.md`

**Interfaces:**
- Produces: `codice(n: int) -> str`. Contiene le righe marcate `# sN` e, per ogni blocco, la riga non marcata che lo precede, come contesto. Ogni blocco è separato da `...`. Pulizia, così il testo si incolla in slide:
  - via il marcatore e il commento che lo segue (`# s4  …`);
  - `tracer(N).` diventa `tracer.`;
  - le righe `if STRATO >= N:` spariscono, e il loro corpo perde un livello di rientro.

  `--codice N` stampa `codice(N)`.

- [ ] **Step 1: Scrivi il test.** `test_codice_pulito`: `t = s.codice(4)` contiene `start_as_current_span("cache.read")` e `cache.age_hours`, e non contiene `tracer(4)`, `# s4` né `STRATO`. `s.codice(1)` contiene `open_telemetry=`.
- [ ] **Step 2: Esegui i test.** Atteso: FAIL.
- [ ] **Step 3: Implementa** riusando la regex di `righe()`.
- [ ] **Step 4: Esegui i test, poi leggi `--codice 0` … `--codice 5` a schermo.** Ogni estratto si legge da solo, senza impalcatura della demo.
- [ ] **Step 5: README.** Una riga d'uso per `--codice`, `--dominio`, `--correzione`, `--correzione-completa`, `--maschera`.
- [ ] **Step 6: Commit.** `git commit -am "Codice pulito per strato, per le slide"`

### Chiusura

- [ ] Riporta allo speaker in una tabella i numeri dei Task 3 e 4, accanto a quelli della fissa. Poi una domanda sola: dove va la correzione. Il file della storia non si tocca prima della risposta.
