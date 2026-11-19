"""Il ciclo di un agente, l'agente come strumento e la guardia contro i cicli."""
import contextvars  # s2
import json
from concurrent.futures import ThreadPoolExecutor

from opentelemetry.trace import StatusCode

from ..impostazioni import attuali
from ..modello import MAX_GIRI, MODEL, PENSIERO
from ..osservabilita import metriche
from ..osservabilita.log import LOG
from ..osservabilita.tracce import tracer
from .prompt import agenti_strumento, schemi
from .strumenti import leggi_dato


def esegui_strumento(client, chiamante: str, nome: str, id_chiamata: str, argomenti: dict,
                     stato: dict) -> tuple[str, bool]:
    if nome in agenti_strumento():
        return chiama_agente(client, chiamante, nome, id_chiamata, argomenti, stato)
    with tracer(3).start_as_current_span(f"execute_tool {nome}") as span:  # s3
        span.set_attributes({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": nome,  # s3
                             "gen_ai.tool.type": "function", "gen_ai.tool.call.id": id_chiamata,  # s3
                             "gen_ai.tool.call.arguments": json.dumps(argomenti, ensure_ascii=False)})  # s3
        risultato = leggi_dato(nome, argomenti, stato)
        span.set_attribute("gen_ai.tool.call.result", risultato)  # s3
        return risultato, False


def richiesta_di_verifica(argomenti: dict) -> str:
    testo = f"Domanda: {argomenti.get('domanda', '')}\nRisposta dell'assistente: {argomenti.get('risposta', '')}"
    return testo + (f"\nContesto: {argomenti['contesto']}" if argomenti.get("contesto") else "")


# La catena di chiamata (chi ha chiamato chi, dalla radice) viaggia fuori dal prompt, in una variabile di contesto:
# ogni thread parte da una copia (esegui_chiamate), quindi i rami paralleli non si pestano.
CATENA = contextvars.ContextVar("catena", default=())
PROFONDITA_MAX = 4  # chiamate fra agenti una dentro l'altra, a partire da coordina (coordina>valida>avvisi>programma>sale)


def controlla_catena(nome: str, catena: tuple) -> str | None:
    """None se `nome` puo' essere chiamato da chi ha `catena` (l'ultimo e' il chiamante); altrimenti il motivo,
    che torna al modello come risultato dello strumento."""
    if nome in catena:
        return f"{nome} è già nella catena di chiamata ({' > '.join(catena)}): non puoi richiamarlo."
    if len(catena) > PROFONDITA_MAX:
        return f"catena di chiamata troppo profonda (massimo {PROFONDITA_MAX}): {' > '.join(catena)} > {nome}."
    return None


def chiama_agente(client, chiamante: str, nome: str, id_chiamata: str, argomenti: dict, stato: dict) -> tuple[str, bool]:
    """Un agente usato come strumento: execute_tool del chiamante con dentro invoke_agent del chiamato.

    Semconv GenAI, refinement "Agent as a tool" (gen_ai.execute_tool.transfer.internal). Lo span del
    passaggio e' dello strato 2 perche' e' l'arco fra due agenti: senza, il grafo non si vede.
    """
    destinazione, istruzioni, strumenti = agenti_strumento()[nome]
    with tracer(2).start_as_current_span(f"execute_tool {nome}") as span:  # s2
        span.set_attributes({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": nome,  # s2
                             "gen_ai.tool.type": "function", "gen_ai.tool.call.id": id_chiamata,  # s2
                             "gen_ai.agent.name": chiamante, "gen_ai.transfer.mode": "return_to_caller",  # s2
                             "gen_ai.transfer.target.name": destinazione})  # s2
        if attuali().strato >= 3:  # s3  argomenti e risultato, come per gli strumenti dei dati
            span.set_attribute("gen_ai.tool.call.arguments", json.dumps(argomenti, ensure_ascii=False))  # s3
        rifiuto = controlla_catena(destinazione, CATENA.get())
        if rifiuto:  # un errore vero del modello, che il codice non nasconde: lo vede lui e lo vede lo span
            span.set_status(StatusCode.ERROR, rifiuto)  # s2
            span.set_attribute("error.type", "ciclo")  # s2
            if attuali().strato >= 3:  # s3
                span.set_attribute("gen_ai.tool.call.result", rifiuto)  # s3
            return rifiuto, True
        richiesta = richiesta_di_verifica(argomenti) if destinazione == "valida" else argomenti.get("richiesta", "")
        risultato = agente(client, destinazione, istruzioni, richiesta, stato, strumenti)
        if attuali().strato >= 3:  # s3
            span.set_attribute("gen_ai.tool.call.result", risultato)  # s3
        return risultato, False


def esegui_chiamate(client, nome: str, chiamate: list, stato: dict) -> list:
    """Gli strumenti chiesti nello stesso giro girano in parallelo; i risultati tornano nell'ordine dei tool_use."""
    if len(chiamate) == 1:  # una sola: nessun thread
        c = chiamate[0]
        return [esegui_strumento(client, nome, c.name, c.id, c.input, stato)]
    with ThreadPoolExecutor(max_workers=len(chiamate)) as pool:
        lavori = []
        for c in chiamate:
            ctx = contextvars.copy_context()  # s2  il thread parte dal contesto OpenTelemetry di chi lo lancia
            lavori.append(pool.submit(ctx.run, esegui_strumento, client, nome, c.name, c.id, c.input, stato))  # s2
        return [lavoro.result() for lavoro in lavori]  # un'eccezione risale come nel giro sequenziale


def ciclo(client, nome: str, istruzioni: str, richiesta: str, stato: dict, strumenti: list):
    messaggi = [{"role": "user", "content": richiesta}]
    extra = {"tools": [schemi()[n] for n in strumenti]} if strumenti else {}
    for _ in range(MAX_GIRI):
        r = client.messages.create(model=MODEL, max_tokens=4096, system=istruzioni, messages=messaggi,
                                   thinking=PENSIERO, **extra)
        u = r.usage  # s0  il conto di questa chiamata: arriva con la risposta
        letti, scritti = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0  # s0
        LOG.info("chiamata al modello", extra={"richiesta": stato["richiesta"],  # s0
                                               "gen_ai.agent.name": nome,  # s0
                                               "gen_ai.response.model": r.model,  # s0
                                               "gen_ai.usage.input_tokens": u.input_tokens + letti + scritti,  # s0
                                               "gen_ai.usage.output_tokens": u.output_tokens,  # s0
                                               "gen_ai.usage.cache_read.input_tokens": letti,  # s0
                                               "gen_ai.usage.cache_write.input_tokens": scritti})  # s0
        with stato["lock"]:  # i rami paralleli scrivono qui insieme
            stato["fattura"].append(r.usage)  # s0  quello che il provider conta e fattura
        if attuali().strato >= 1:  # s1  le stesse cifre, come metriche
            attributi = {"gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic",  # s1
                         "gen_ai.token.modality": "text", "gen_ai.request.model": MODEL,  # s1
                         "gen_ai.response.model": r.model, "gen_ai.agent.name": nome}  # s1
            ingresso = u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)  # s1
            metriche.TOKEN_IN.add(ingresso, attributi)  # s1
            metriche.TOKEN_OUT.add(u.output_tokens, attributi)  # s1
            with stato["lock"]:  # s1
                stato["per_agente"][nome] = stato["per_agente"].get(nome, 0) + ingresso + u.output_tokens  # s1
        chiamate = [b for b in r.content if b.type == "tool_use"]
        if not chiamate:
            return "".join(b.text for b in r.content if b.type == "text")
        messaggi.append({"role": "assistant", "content": r.content})
        risultati = [{"type": "tool_result", "tool_use_id": c.id, "content": r, "is_error": e}
                     for c, (r, e) in zip(chiamate, esegui_chiamate(client, nome, chiamate, stato))]
        messaggi.append({"role": "user", "content": risultati})
    raise RuntimeError(f"oltre {MAX_GIRI} giri")


def agente(client, nome: str, istruzioni: str, richiesta: str, stato: dict, strumenti: list) -> str:
    segno = CATENA.set(CATENA.get() + (nome,))  # chi e' in corso, per la guardia contro i cicli
    try:
        with tracer(2).start_as_current_span(f"invoke_agent {nome}") as span:  # s2
            span.set_attributes({"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": nome,  # s2
                                 "gen_ai.request.model": MODEL})  # s2
            return ciclo(client, nome, istruzioni, richiesta, stato, strumenti)
    finally:
        CATENA.reset(segno)
