# Il codice per le slide

Uscita di `.venv/bin/python strati.py --codice N`, per N da 0 a 5, e di `--righe`. Le righe `...` separano frammenti presi da punti diversi di `strati.py`.

## Strato 0: una riga di log per chiamata e la fattura, tutto quello che si ha oggi.

```python
u = r.usage
LOG.info("chiamata al modello", extra={"richiesta": stato["richiesta"], "agente": nome, "modello": r.model,
                                       "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                                       "cache_read_input_tokens": u.cache_read_input_tokens or 0,
                                       "cache_creation_input_tokens": u.cache_creation_input_tokens or 0})
...
stato["fattura"].append(r.usage)
...
stato["richiesta"] = uuid.uuid4().hex[:8]
...
inizio = time.monotonic()
...
secondi = time.monotonic() - inizio
...
"log": f"{ora:%H:%M:%S} INFO POST /chiedi 200 in {secondi:.1f} s",
"fattura": {"chiamate": len(u), "in": sum(x.input_tokens for x in u),
            "cache": sum(x.cache_read_input_tokens or 0 for x in u),
            "out": sum(x.output_tokens for x in u)},
```

La riga per chiamata è il primo frammento: dopo `r = client.messages.create(...)` (riga applicativa, non marcata) `u` è il conto della risposta, con i nomi dei campi del provider. `stato["richiesta"]` nasce in `esegui`. Le chiavi `"log"` e `"fattura"` stanno fuori dal dizionario che le contiene (restano la virgola finale e il `}` mancante del dizionario esterno): su una slide serve avvolgerle in un `return {...}`.

## Strato 1: le metriche dei token e l'SDK (gli span, con il contenuto spento: `metadata_only`).

```python
from opentelemetry.sdk.resources import Resource
...
VERSIONE = "2026-11-05"
RISORSA = Resource.create({"service.name": "osservare-a-strati", "service.version": VERSIONE})
...
provider = MeterProvider(resource=RISORSA, metric_readers=lettori)
misura = provider.get_meter("osservare-a-strati")
TOKEN_IN = misura.create_counter("gen_ai.client.inference.usage.input_tokens", unit="{token}")
TOKEN_OUT = misura.create_counter("gen_ai.client.inference.usage.output_tokens", unit="{token}")
TOKEN_AGENTE = misura.create_histogram("assistente.agente.token", unit="{token}",
                                       description="token di un agente in una richiesta",
                                       explicit_bucket_boundaries_advisory=CONFINI_TOKEN)
...
memoria = InMemorySpanExporter()
...
provider = TracerProvider(resource=RISORSA)
processore = SimpleSpanProcessor(memoria)
...
provider.add_span_processor(processore)
...
attributi = {"gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic",
             "gen_ai.token.modality": "text", "gen_ai.request.model": MODEL,
             "gen_ai.response.model": r.model, "gen_ai.agent.name": nome}
ingresso = u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
TOKEN_IN.add(ingresso, attributi)
TOKEN_OUT.add(u.output_tokens, attributi)
with stato["lock"]:
    stato["per_agente"][nome] = stato["per_agente"].get(nome, 0) + ingresso + u.output_tokens
...
modo = "metadata_only"
...
return anthropic.Anthropic(open_telemetry={"tracer_provider": provider,
                                           "traces": {"content_mode": modo}})
...
for nome, n in stato["per_agente"].items():
    TOKEN_AGENTE.record(n, {"gen_ai.agent.name": nome})
```

Frammenti non autonomi: `lettori` (la memoria e, con `--otlp`, l'esportazione periodica) è impalcatura e non compare; `r`, `u` e `nome` sono quelli di `ciclo`; il `for` finale sta dentro lo span `invoke_workflow`, per questo dallo strato 2 ogni misura porta la trace come exemplar. Il `return` sta fuori da una funzione, senza la funzione che lo contiene.

## Strato 2: gli agenti diventano archi dell'albero, con la guardia contro i cicli.

```python
import contextvars
...
with tracer.start_as_current_span(f"execute_tool {nome}") as span:
    span.set_attributes({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": nome,
                         "gen_ai.tool.type": "function", "gen_ai.tool.call.id": id_chiamata,
                         "gen_ai.agent.name": chiamante, "gen_ai.transfer.mode": "return_to_caller",
                         "gen_ai.transfer.target.name": destinazione})
...
span.set_status(StatusCode.ERROR, rifiuto)
span.set_attribute("error.type", "ciclo")
...
ctx = contextvars.copy_context()
lavori.append(pool.submit(ctx.run, esegui_strumento, client, nome, c.name, c.id, c.input, stato))
...
with tracer.start_as_current_span(f"invoke_agent {nome}") as span:
    span.set_attributes({"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": nome,
                         "gen_ai.request.model": MODEL})
...
with tracer.start_as_current_span("invoke_workflow assistente-evento") as span:
    span.set_attribute("gen_ai.operation.name", "invoke_workflow")
    span.set_attribute("gen_ai.workflow.name", "assistente-evento")
```

Frammenti non autonomi: `span.set_status(...)` e `span.set_attribute("error.type", ...)` sono righe orfane (appartengono al ramo di rifiuto della guardia, senza il `with` e l'`if`), e `lavori.append(...)` usa `pool` e `esegui_strumento` che qui non compaiono.

## Strato 3: lo strumento scrive argomenti, risultato e log correlati.

```python
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
...
provider = LoggerProvider()
...
provider.add_log_record_processor(SimpleLogRecordProcessor(memoria_log))
...
_handler = LoggingHandler(logger_provider=provider)
LOG.addHandler(_handler)
...
with tracer.start_as_current_span(f"execute_tool {nome}") as span:
    span.set_attributes({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": nome,
                         "gen_ai.tool.type": "function", "gen_ai.tool.call.id": id_chiamata,
                         "gen_ai.tool.call.arguments": json.dumps(argomenti, ensure_ascii=False)})
...
span.set_attribute("gen_ai.tool.call.result", risultato)
...
span.set_attribute("gen_ai.tool.call.arguments", json.dumps(argomenti, ensure_ascii=False))
...
span.set_attribute("gen_ai.tool.call.result", rifiuto)
...
span.set_attribute("gen_ai.tool.call.result", risultato)
```

Righe orfane: `span.set_attribute("gen_ai.tool.call.result", risultato)` compare due volte e `...call.arguments` è impostato una volta nel `with` e una volta più sotto, senza contesto. Il blocco `with` ripete quello dello strato 2 senza l'aggiunta dell'agente. Su una slide conviene mostrare un solo `with` completo.

## Strato 4: lo strumento dichiara i dati che ha letto (pubblicazione, fonte, pagine, filtro).

```python
trace.get_current_span().set_attribute("programma.pubblicato_il", PUBBLICATO)
...
trace.get_current_span().set_attribute("sale.fonte", "database delle sale")
...
trace.get_current_span().set_attributes({"avvisi.pagine": pagine, "avvisi.letti": len(voci),
                                         "avvisi.filtro": filtro,
                                         "avvisi.aggiornati_alle": AVVISI_AGGIORNATI})
```

Tre righe senza contesto: ogni `trace.get_current_span()...` sta dentro il ramo di una fonte diversa (programma, sale, avvisi) di `leggi_dato`, che qui non si vede. Leggibile come elenco, non come codice unico.

## Strato 5: il contenuto è acceso e un processore toglie l'email prima che lo span esca.

```python
class MascheraEmail(SpanProcessor):
    """Toglie l'email da ogni attributo prima che lo span esca dal processo, anche dentro i JSON."""

    def __init__(self, prossimo: SpanProcessor):
        self.prossimo = prossimo

    def on_start(self, span, parent_context=None):
        self.prossimo.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan):
        pulito = {k: senza_email(v) for k, v in span.attributes.items()}
        self.prossimo.on_end(ReadableSpan(
            name=span.name, context=span.context, parent=span.parent, resource=span.resource,
            attributes=pulito, events=span.events, links=span.links, kind=span.kind, status=span.status,
            start_time=span.start_time, end_time=span.end_time, instrumentation_scope=span.instrumentation_scope))

    def shutdown(self):
        self.prossimo.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.prossimo.force_flush(timeout_millis)


def senza_email(v):
    if isinstance(v, str):
        return EMAIL.sub("[email]", v)
    return tuple(senza_email(x) for x in v) if isinstance(v, (list, tuple)) else v
...
if maschera:
    processore = MascheraEmail(processore)
...
modo = "content"
```

Autonomo, salvo `EMAIL`, `ReadableSpan` e `SpanProcessor` non importati, e `modo = "content"` isolato in fondo (la riga appartiene a una funzione che qui non si vede). Lungo per una slide: 24 righe.

## Quante righe pesa ogni strato

```
strato 0 · oggi: un log e una fattura    13 righe
strato 1 · le metriche e l'SDK           29 righe
strato 2 · gli agenti                    18 righe
strato 3 · lo strumento                  18 righe
strato 4 · i dati letti                   8 righe
strato 5 · il contenuto                  24 righe
```
