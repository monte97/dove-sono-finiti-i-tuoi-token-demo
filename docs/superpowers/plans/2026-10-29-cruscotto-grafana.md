# Cruscotto dei cinque segnali su Grafana e Tempo — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** I cinque segnali di «Lunedì, in produzione» (D29) su un cruscotto Grafana che legge Tempo con TraceQL, con numeri identici a `segnali.py`; le registrazioni esistenti si rimandano a Tempo per gli screenshot, le run del banco del 6/11 ci arrivano dal vivo.

**Architecture:** Un `SpanProcessor` (`RiassuntoSullaRadice`) scrive sullo span radice `invoke_workflow` i fatti che servono per richiesta (forma, costo, strumenti richiamati, copia vecchia), calcolati con le stesse funzioni di `segnali.py` sugli span già chiusi della trace. Il cruscotto conta span con `count_over_time` e prende il costo per richiesta dalla ricerca, con il calcolo `p95` di Grafana. `tempo.py` rimanda le registrazioni via OTLP con id nuovi e orari spostati ad adesso.

**Tech Stack:** Python 3.14, `opentelemetry-sdk==1.44.0`, `opentelemetry-exporter-otlp-proto-http==1.44.0`; `grafana/tempo:2.8.1`, `grafana/grafana:12.0.2` in Docker Compose.

**Spec:** `0_Content/_talks/devfest-alps-2026/observability-agenti-otel-storia.md` (D22, D25, D29, «Lunedì, in produzione»). Lo spike del 29/10 (scratchpad, non versionato) ha misurato quanto segue.

## Global Constraints

- Porte: Grafana `3377`, Tempo `3210`, OTLP HTTP `4418`. Le porte 3000 e 3200 sono di un altro progetto: non si usano e non si toccano i suoi container.
- Attributi del riassunto, solo sullo span radice: `richiesta.forma` (stringa, `" ".join(grafo)`), `richiesta.costo_microusd` (intero, `round(costo * 1e6)`), `richiesta.richiamati` (stringa: i nomi con almeno due chiamate, ordinati, separati da spazio; `""` se nessuno), `richiesta.copia_vecchia` (booleano). Un attributo il cui segnale è `None` sotto lo strato minimo non si scrive.
- Metadati del banco, solo nel replay e nelle run del banco: `banco.cartella`, `banco.modo`. Non sono segnali di produzione e il cruscotto li usa solo come filtro.
- Il costo è in microdollari interi: `quantile_over_time` di Tempo scarta i valori sotto 1 e approssima per fasce a potenze di due (spike: 3.566 invece di 2.159), quindi il cruscotto non lo usa.
- Il 95° percentile è quello di Grafana: `ordinati[round((n - 1) * 0.95)]`, senza interpolazione (`public/build/8882.*.js`, funzione del calcolo `p95`). `segnali.p95` si allinea, così slide e cruscotto dicono lo stesso numero.
- Le metriche TraceQL contano span, non trace: `{…} | count() > 1 | count_over_time()` dà 44 dove le richieste sono 22. Tutto ciò che è «per richiesta» si conta sulle radici.
- `count_over_time` con passo largo perde campioni (spike: 14 invece di 35 con passo 900 s): il cruscotto e la verifica usano passo 60 s e sommano i campioni.
- Il conteggio delle approvazioni segue `strati.approva`: regex TraceQL `(?s).*Verificato\.[ \n"'»*]*$` sul risultato degli archi verso `valida`.
- I test della suite restano senza rete; la verifica contro Tempo è uno script a parte, che si lancia con lo stack acceso.

## Review Focus

- Il processore deve scrivere sulla radice **prima** che si chiuda: se la radice si chiude prima di un figlio (non accade nel codice di oggi), il riassunto resta incompleto senza errore. Test: dopo una run finta, gli attributi della radice uguagliano `riassunto()` calcolato sulla registrazione.
- Più trace contemporanee nello stesso processo (non nel banco di oggi): lo stato per trace va indicizzato per `trace_id` e liberato alla chiusura della radice. Test nel Task 2.
- Una registrazione dello strato 0 o 1 nel replay: niente forma né richiamati, senza eccezioni. Test nel Task 3.
- La regex di approvazione in TraceQL deve dare lo stesso numero di `approva()` anche con il «Verificato.» seguito da `**` o da `»`: è la verifica del Task 4 sul freeze (22) e sullo strato 5 (29).
- Le run sane e guaste nella stessa finestra di tempo: il filtro `banco.modo` deve separarle. È la verifica del Task 4.

---

### Task 1: il riassunto per richiesta e il percentile di Grafana

**Files:**
- Modify: `segnali.py`
- Modify: `test_segnali.py`

**Interfaces:**
- Consumes: `segnali(r)` e `p95` (esistenti).
- Produces: `p95(costi: list[float]) -> float` con il metodo di Grafana; `riassunto(r: dict) -> dict[str, str|int|bool]` con le chiavi `richiesta.*` dei Global Constraints, senza le chiavi il cui segnale è `None`.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
def test_p95_come_grafana():
    costi = [0.001 * i for i in range(1, 31)]
    assert sg.p95(costi) == sorted(costi)[round(29 * 0.95)]
    assert sg.p95([0.5]) == 0.5

def test_riassunto_della_run():
    assert sg.riassunto(RUN) == {"richiesta.forma": " ".join(s.grafo(RUN["span"])),
                                 "richiesta.costo_microusd": round((s.costo(1000, 0, 50) + s.costo(2000, 1000, 100)) * 1e6),
                                 "richiesta.richiamati": "cerca leggi_programma", "richiesta.copia_vecchia": True}
    assert set(sg.riassunto({**RUN, "strato": 1})) == {"richiesta.costo_microusd"}
```

e in `test_p95_e_valida_mai_chiamata` sostituisci l'assert su `statistics.quantiles` con quello sopra (stesso valore atteso del nuovo metodo).

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `.venv/bin/python test_segnali.py`
Expected: FAIL su `test_p95_come_grafana` (AssertionError) o su `riassunto` (AttributeError)

- [ ] **Step 3: Implementa `p95` e `riassunto` in `segnali.py`**

`riassunto` usa `segnali(r)`; `richiamati` = nomi con `chiamate[nome] >= 2`, `sorted`, uniti da spazio.

- [ ] **Step 4: Esegui e verifica che passi**

Run: `.venv/bin/python test_segnali.py && .venv/bin/python test_strati.py && .venv/bin/python segnali.py registrazioni/strato-5`
Expected: tutti `ok`; lo strato 5 guasto stampa ancora `95° percentile $ 0.002159`

- [ ] **Step 5: Commit** — `git commit -m "Segnali: il riassunto per richiesta e il 95° percentile come lo calcola Grafana"`

### Task 2: il riassunto sulla radice, dal vivo, e l'esportazione OTLP

**Files:**
- Modify: `segnali.py` (classe `RiassuntoSullaRadice`)
- Modify: `strati.py` (`fai_provider`, argomenti `--produzione` e `--otlp`)
- Modify: `requirements.txt` (`opentelemetry-exporter-otlp-proto-http==1.44.0` e le sue dipendenze, dal `pip freeze` del venv)
- Test: `test_strati.py`

**Interfaces:**
- Consumes: `riassunto(r)` (Task 1); `strati.in_dict(span) -> dict`, `strati.fai_provider(maschera)`, la run finta `corri(n)` di `test_strati.py`.
- Produces: `RiassuntoSullaRadice(strato: int)` in `segnali.py`; globali `strati.PRODUZIONE: bool` (default `False`) e `strati.OTLP: str | None` (default `None`); `fai_provider` aggiunge `RiassuntoSullaRadice(STRATO)` se `PRODUZIONE` e un `BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP))` se `OTLP`. Da riga di comando `--produzione` (strato 2 o più) e `--otlp URL`, che implica `--produzione`. La cartella delle registrazioni prende il suffisso `-produzione`.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
def test_riassunto_sulla_radice():
    s.PRODUZIONE = True
    try:
        reg, _ = corri(5)
    finally:
        s.PRODUZIONE = False
    radice = next(x for x in reg["span"] if x["padre"] is None)
    atteso = sg.riassunto({**reg, "span": [x for x in reg["span"] if x is not radice]})
    assert {k: v for k, v in radice["attributi"].items() if k.startswith("richiesta.")} == atteso

def test_riassunto_due_trace_insieme():
    from opentelemetry.sdk.trace import TracerProvider
    p = sg.RiassuntoSullaRadice(5)
    tp = TracerProvider(); tp.add_span_processor(p)
    t = tp.get_tracer("prova")
    a, b = t.start_span("invoke_workflow a"), t.start_span("invoke_workflow b")
    with trace.use_span(a):
        t.start_span("anthropic.messages.create", attributes={"gen_ai.usage.input_tokens": 1000,
                                                             "gen_ai.usage.output_tokens": 50}).end()
    assert a.attributes["richiesta.costo_microusd"] == round(s.costo(1000, 0, 50) * 1e6)
    assert "richiesta.costo_microusd" not in b.attributes or b.attributes["richiesta.costo_microusd"] == 0
    a.end(); b.end()
    assert all(not v for v in vars(p).values() if isinstance(v, dict))  # nessuno stato resta dopo le radici
```

(`trace` è `opentelemetry.trace`). `corri` è l'helper esistente in `test_strati.py`; se ha un'altra firma, adatta la chiamata.

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `.venv/bin/python test_strati.py`
Expected: FAIL con `AttributeError` su `PRODUZIONE` o su `RiassuntoSullaRadice`

- [ ] **Step 3: Implementa**

`on_start`: se lo span non ha un genitore locale, ricordalo come radice della sua trace. `on_end` di un figlio: aggiungi `strati.in_dict(span)` al buffer della trace e scrivi sulla radice `riassunto({"strato": strato, "span": buffer})` con `set_attributes`. `on_end` della radice: libera radice e buffer. Import di `segnali` dentro `fai_provider` (evita l'import circolare).

- [ ] **Step 4: Esegui e verifica che passi**

Run: `.venv/bin/pip install -r requirements.txt && .venv/bin/python test_strati.py && .venv/bin/python test_segnali.py`
Expected: tutti `ok`

- [ ] **Step 5: Commit** — `git commit -m "In produzione: un SpanProcessor scrive il riassunto della richiesta sulla radice; esportazione OTLP"`

### Task 3: rimandare le registrazioni a Tempo

**Files:**
- Create: `tempo.py`
- Test: `test_segnali.py`

**Interfaces:**
- Consumes: `riassunto(r)` (Task 1).
- Produces: `in_otlp(r: dict, cartella: str, adesso: float) -> list[ReadableSpan]`; `python tempo.py [--otlp URL] CARTELLA ...` (default `http://localhost:4418/v1/traces`), una richiesta ogni 0,1 s, ognuna spostata così che la sua ultima chiusura cada ad `adesso`.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
def test_in_otlp():
    import tempo
    reg = leggi("strato-5-freeze")[0]
    spans = tempo.in_otlp(reg, "strato-5-freeze", adesso=2_000_000_000.0)
    assert len(spans) == len(reg["span"]) and len({x.context.trace_id for x in spans}) == 1
    radice = next(x for x in spans if x.parent is None)
    assert radice.attributes["banco.cartella"] == "strato-5-freeze" and radice.attributes["banco.modo"] == "guasto"
    assert radice.attributes["richiesta.forma"] == sg.riassunto(reg)["richiesta.forma"]
    assert max(x.end_time for x in spans) == 2_000_000_000 * 10**9
    ids = {x.context.span_id for x in spans}
    assert all(x.parent.span_id in ids for x in spans if x.parent)
    assert sum(x.status.status_code.name == "ERROR" for x in spans) == sum(x["errore"] for x in reg["span"])
    vecchia = tempo.in_otlp(leggi("strato-1")[0], "strato-1", adesso=2_000_000_000.0)
    assert "richiesta.forma" not in next(x for x in vecchia if x.parent is None).attributes
```

Nota: allo strato 1 le chiamate al modello sono trace separate senza radice comune (D22); «radice» è lo span senza genitore, e ce ne sono diverse. Il test prende la prima: è sufficiente per «niente forma».

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `.venv/bin/python test_segnali.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'tempo'`

- [ ] **Step 3: Implementa `tempo.py`**

Id nuovi con `random.getrandbits` (una mappa per registrazione; una trace nuova per ogni `trace` originale), stato `ERROR` dove `errore`, risorsa `service.name=osservare-a-strati`. Il riassunto si aggiunge solo se la radice non ha già attributi `richiesta.*` (le run del Task 2 li hanno).

- [ ] **Step 4: Esegui e verifica che passi**

Run: `.venv/bin/python test_segnali.py && .venv/bin/python test_strati.py`
Expected: tutti `ok`

- [ ] **Step 5: Commit** — `git commit -m "tempo.py: le registrazioni rimandate a Tempo, con il riassunto sulla radice"`

### Task 4: lo stack, il cruscotto e la verifica dei numeri

**Files:**
- Create: `cruscotto/compose.yaml`, `cruscotto/tempo.yaml`, `cruscotto/grafana/datasource.yaml`, `cruscotto/grafana/dashboards.yaml`, `cruscotto/grafana/segnali.json`
- Create: `verifica_cruscotto.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `cruscotto(regs)` (esistente), `tempo.py` (Task 3).
- Produces: un cruscotto Grafana «Lunedì, in produzione» (uid `segnali`) con le variabili `cartella` e `modo` (sui metadati `banco.*`) e sei pannelli: richieste; richiamati per strumento (una query per strumento: `{ span.richiesta.richiamati =~ ".*\\bNOME\\b.*" }`); forme dell'albero (`by (span.richiesta.forma)`, tabella col totale); `valida` approva (due query: verdetti e approvati, stat «22 su 30»); da copia vecchia (`{ span.richiesta.copia_vecchia = true }`); costo a richiesta (ricerca con `select(span.richiesta.costo_microusd)`, limite 500, calcoli `median` e `p95`, unità microdollari). `verifica_cruscotto.py CARTELLA` legge le query **dal JSON del cruscotto**, sostituisce le variabili, le esegue su Tempo (passo 60 s, ultima ora, somma dei campioni; il costo dalla ricerca) e confronta ogni numero con `cruscotto()` della stessa cartella, per modo.

- [ ] **Step 1: Configurazione dello stack**

`tempo.yaml` come nello spike: ricevitore OTLP HTTP su 4318, storage locale, `metrics_generator` con `local-blocks`, `filter_server_spans: false`, `flush_to_storage: true`, e override `processors: [local-blocks]`. Grafana anonimo con ruolo Admin, datasource Tempo uid `tempo`, cruscotto da file.

- [ ] **Step 2: Accendi lo stack e carica i dati**

Run: `docker compose -f cruscotto/compose.yaml up -d && sleep 20 && curl -s localhost:3210/ready && .venv/bin/python tempo.py registrazioni/strato-5 registrazioni/strato-5-freeze registrazioni/strato-5-correzione registrazioni/strato-5-correzione-completa`
Expected: `ready` e una riga `SUCCESS` per registrazione

- [ ] **Step 3: Scrivi `verifica_cruscotto.py` e lancialo prima del cruscotto**

Run: `.venv/bin/python verifica_cruscotto.py registrazioni/strato-5-freeze`
Expected: FAIL perché `cruscotto/grafana/segnali.json` non esiste o non ha i pannelli

- [ ] **Step 4: Scrivi il cruscotto e rilancia la verifica**

Run: `for c in strato-5 strato-5-freeze strato-5-correzione strato-5-correzione-completa; do .venv/bin/python verifica_cruscotto.py registrazioni/$c || break; done`
Expected: per ogni cartella e modo, ogni segnale `uguale`; sul freeze guasto: richiamati `leggi_calendario 22 · cerca 8`, approva `22 su 30`, copia `22`, p95 `1486` µ$. Un numero diverso si indaga (superpowers:systematic-debugging), non si aggiusta la query finché torna.

- [ ] **Step 5: Guardalo in Grafana**

Apri `http://localhost:3377/d/segnali?var-cartella=strato-5-freeze&var-modo=guasto`: i pannelli mostrano gli stessi numeri della verifica. (Lo screenshot per la slide si fa dopo, a parte.)

- [ ] **Step 6: README e commit**

Nel README una sezione «Cruscotto» con i tre comandi (compose, `tempo.py`, `verifica_cruscotto.py`), le porte e il motivo del costo in microdollari e del p95 di Grafana.

```bash
git add cruscotto verifica_cruscotto.py README.md
git commit -m "Cruscotto: i cinque segnali su Grafana e Tempo, verificati contro segnali.py"
```
