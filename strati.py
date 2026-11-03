"""La stessa risposta sbagliata, osservata uno strato alla volta.

Tre agenti. `coordina` e' l'orchestratore: ha come strumenti gli agenti `cerca` e `valida` e decide
lui chi chiamare, in che ordine, cosa passare e quando rispondere. `cerca` legge il programma con lo
strumento `leggi_programma`, `valida` controlla una risposta prima che arrivi all'utente. Il servizio
del programma e' simulato e il difetto e' messo apposta: dopo un timeout lo strumento serve per 120 s
la copia di ieri (15:00 invece di 14:00).

Strati (ognuno contiene i precedenti):
  0  oggi: una riga di log e la fattura, niente OpenTelemetry
  1  l'SDK: la strumentazione nativa di anthropic, nient'altro
  2  gli agenti: span invoke_workflow, invoke_agent e gli archi fra agenti, scritti a mano
  3  lo strumento: span execute_tool con argomenti, risultato, timeout
  4  la provenienza: span cache.read con eta' e motivo della copia
  5  il contenuto: content_mode "content" (messaggi e ragionamento riassunto)

  python strati.py --strato 3 --guasto             una run
  python strati.py --strato 3 --guasto --banco 5   cinque run, una riga ciascuna
  python strati.py --replay registrazioni/strato-3/<file>.json
  python strati.py --riepilogo                     una riga per strato e modo
  python strati.py --misure 5                      grafo, riprove, verifiche e risposte dello strato 5
  python strati.py --righe                         righe di codice di ogni strato

Le righe che esistono solo per osservare finiscono con il marcatore dello strato (s0 ... s5 dopo il cancelletto).
La pipeline fissa, la variante A (agente come strumento) e il tool runner sono nel tag git spike-a-b.
"""

import argparse
import datetime as dt
import json
import re
import statistics
import textwrap
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

QUI = Path(__file__).parent
load_dotenv(QUI / ".env")

TITOLI = {0: "oggi: un log e una fattura", 1: "l'SDK", 2: "gli agenti", 3: "lo strumento",
          4: "la provenienza", 5: "il contenuto"}
STRATO = 0

EMAIL = re.compile(r"[\w.]+@[\w.]+\.\w+")
MASCHERA = False
PRODUZIONE = False  # il riassunto della richiesta sulla radice, per il cruscotto
OTLP = None  # dove esportare gli span, oltre alla memoria


class MascheraEmail(SpanProcessor):  # s5
    """Toglie l'email da ogni attributo prima che lo span esca dal processo, anche dentro i JSON."""  # s5

    def __init__(self, prossimo: SpanProcessor):  # s5
        self.prossimo = prossimo  # s5

    def on_start(self, span, parent_context=None):  # s5
        self.prossimo.on_start(span, parent_context)  # s5

    def on_end(self, span: ReadableSpan):  # s5
        pulito = {k: senza_email(v) for k, v in span.attributes.items()}  # s5
        self.prossimo.on_end(ReadableSpan(  # s5
            name=span.name, context=span.context, parent=span.parent, resource=span.resource,  # s5
            attributes=pulito, events=span.events, links=span.links, kind=span.kind, status=span.status,  # s5
            start_time=span.start_time, end_time=span.end_time, instrumentation_scope=span.instrumentation_scope))  # s5

    def shutdown(self):  # s5
        self.prossimo.shutdown()  # s5

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # s5
        return self.prossimo.force_flush(timeout_millis)  # s5


def senza_email(v):  # s5
    if isinstance(v, str):  # s5
        return EMAIL.sub("[email]", v)  # s5
    return tuple(senza_email(x) for x in v) if isinstance(v, (list, tuple)) else v  # s5


memoria = InMemorySpanExporter()  # s1  ponytail: in memoria; dal vivo un exporter OTLP verso un backend
_spento = trace.NoOpTracer()


def processore_otlp(url: str):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    return BatchSpanProcessor(OTLPSpanExporter(endpoint=url))


def fai_provider(maschera: bool) -> TracerProvider:
    """Un provider per client: con la maschera, gli span passano da MascheraEmail prima dell'exporter."""
    global _vero
    provider = TracerProvider()  # s1
    processore = SimpleSpanProcessor(memoria)  # s1
    if maschera:  # s5
        processore = MascheraEmail(processore)  # s5
    provider.add_span_processor(processore)  # s1
    if PRODUZIONE:
        from segnali import RiassuntoSullaRadice  # qui: segnali importa strati
        provider.add_span_processor(RiassuntoSullaRadice(STRATO))
    if OTLP:  # anche verso il backend l'email esce solo mascherata
        provider.add_span_processor(MascheraEmail(processore_otlp(OTLP)) if maschera else processore_otlp(OTLP))
    _vero = provider.get_tracer("osservare-a-strati")
    return provider


fai_provider(False)  # il tracer esiste anche prima del primo client


def tracer(n: int):
    """Il tracer dello strato n: vero da quello strato in su, muto sotto. Impalcatura della demo, non strumentazione."""
    return _vero if STRATO >= n else _spento


MODEL = "claude-haiku-5-5"
LISTINO = (0.10, 0.01, 0.50)  # USD per milione: ingresso, letto dalla cache, uscita (ragionamento compreso); letto il 23/10/2026
MAX_GIRI = 6

ETA_COPIA_ORE = 26
TIMEOUT_S = 2.0
FINESTRA_S = 120

# Freeze: la risposta giusta nomina un fatto che c'e' solo nel calendario di oggi; la sbagliata dice si'.
FATTI_DI_OGGI = re.compile(r"lunedì|black friday|09:12", re.I)
FERMO = re.compile(r"(?<!non )\bè in freeze|freeze in corso|non puoi|non è (possibile|consentit)", re.I)
VIA_LIBERA = re.compile(r"(?<!non )\bpuoi\b|(?<!non è )consentit|(?<!non )è possibile|via libera", re.I)
DUBBIO = re.compile(r"conferm|non (so|saprei)\b", re.I)  # «no, non posso confermare» non e' un no
SI = re.compile(r"(^|[,:.]\s*)sì\b", re.I)  # un sì che apre la risposta, non «sì o no»

# Il dominio: domanda, dati di oggi e di ieri, istruzioni degli agenti, strumento. Codice e guasto non cambiano.
# Istruzioni come le scriverebbe un team: consigliano la verifica, non dicono cosa passare ne' lo vietano.
DOMINI = {
    "orario": {
        "workflow": "assistente-evento", "cartella": "",
        "domanda": ("Ciao, sono Giulia Rossi (giulia.rossi@example.com). "
                    "A che ora è il workshop Kubernetes da zero?"),
        "oggi": {"Kubernetes da zero": {"giorno": "oggi", "ora": "14:00", "sala": "B"},  # spostato stamattina
                 "OpenTelemetry in un'ora": {"giorno": "oggi", "ora": "11:00", "sala": "A"},
                 "Rust per chi scrive Go": {"giorno": "domani", "ora": "16:30", "sala": "C"}},
        "ieri": {"Kubernetes da zero": {"giorno": "oggi", "ora": "15:00", "sala": "B"}},
        "servizio": "il servizio del programma",
        "correzione": " Se il dato del programma non è aggiornato, dillo nella risposta.",
        "strumento": "leggi_programma", "campo": "sessione", "descrizione_campo": "titolo della sessione",
        "descrizione": "Legge dal servizio del programma giorno, ora e sala di una sessione dell'evento.",
        "descrizione_cerca": ("Agente che trova informazioni sul programma dell'evento (sessioni, giorni, orari, "
                              "sale) leggendo il servizio del programma. Restituisce una risposta in una riga."),
        "cerca": ("Sei l'assistente di DevFest Immaginario 2026. Per gli orari usa sempre lo strumento "
                  "leggi_programma. Rispondi in una riga con giorno, ora e sala."),
        "coordina": ("Sei l'assistente di DevFest Immaginario 2026 e coordini due agenti: cerca trova le informazioni "
                     "sul programma dell'evento, valida controlla una risposta prima che arrivi all'utente. Prima di "
                     "rispondere all'utente, fai controllare la risposta da valida. Rispondi in una riga con giorno, "
                     "ora e sala."),
        "valida": ("Controlli le risposte dell'assistente di DevFest Immaginario 2026 prima che arrivino "
                   "all'utente. Ricevi la domanda, la risposta e, se c'è, il contesto su cui si basa. Verifica che "
                   "l'orario sia valido, che la sala esista (le sale sono A, B e C) e che la risposta sia pertinente "
                   "alla domanda e coerente con il contesto. Se va tutto bene, restituisci la risposta com'è "
                   "aggiungendo in fondo «Verificato.». Altrimenti spiega cosa non va."),
        "sbagliata": lambda r: "15:00" in r and "14:00" not in r,
        "giusta": lambda r: "14:00" in r and "15:00" not in r,
        "dato": re.compile(r"\d\d:\d\d"),  # il dato dello strumento, se arriva a valida
    },
    # dal pilota del 25/10 sulla pipeline fissa: stessa domanda, stessi dati, stesse istruzioni
    "freeze": {
        "workflow": "assistente-piattaforma", "cartella": "-freeze",
        "domanda": ("Ciao, sono Marco Bianchi (marco.bianchi@example.com). "
                    "Posso fare adesso il deploy del servizio pagamenti?"),
        "oggi": {"pagamenti": {"freeze": True, "dal": "oggi 09:12", "al": "lunedì 08:00", "motivo": "Black Friday"},
                 "catalogo": {"freeze": False}, "ricerca": {"freeze": False}},
        "ieri": {"pagamenti": {"freeze": False}},
        "servizio": "il servizio del calendario",
        "correzione": " Se il dato del calendario non è aggiornato, dillo nella risposta.",
        "strumento": "leggi_calendario", "campo": "servizio", "descrizione_campo": "nome del servizio",
        "descrizione": "Legge dal calendario dei freeze se un servizio si può rilasciare in questo momento.",
        "descrizione_cerca": ("Agente che trova informazioni sul calendario dei freeze dei servizi leggendo il "
                              "servizio del calendario. Restituisce una risposta in una riga."),
        "cerca": ("Sei l'assistente della piattaforma interna di Negozio Immaginario. Per sapere se si può fare il deploy "
                  "di un servizio usa sempre lo strumento leggi_calendario, che legge il calendario dei freeze. "
                  "Rispondi in una riga."),
        "coordina": ("Sei l'assistente della piattaforma interna di Negozio Immaginario e coordini due agenti: cerca "
                     "trova le informazioni sul calendario dei freeze, valida controlla una risposta prima che arrivi "
                     "allo sviluppatore. Prima di rispondere allo sviluppatore, fai controllare la risposta da valida. "
                     "Rispondi in una riga."),
        "valida": ("Controlli le risposte dell'assistente della piattaforma interna di Negozio Immaginario prima che "
                   "arrivino allo sviluppatore. Ricevi la domanda, la risposta e, se c'è, il contesto su cui si basa. "
                   "Verifica che il servizio esista (i servizi sono pagamenti, catalogo e ricerca), che la risposta dica "
                   "chiaramente sì o no e che sia pertinente alla domanda e coerente con il contesto. Se va tutto bene, "
                   "restituisci la risposta com'è aggiungendo in fondo «Verificato.». Altrimenti spiega cosa non va."),
        "sbagliata": lambda r: not DOMINI["freeze"]["giusta"](r) and bool(
            SI.search(r) or (VIA_LIBERA.search(r) and not NON_CONFERMA.search(r))),
        # un «sì» in apertura e' un via libera anche se poi nomina un «freeze in corso» negato (banco del 6/11)
        "giusta": lambda r: bool(FATTI_DI_OGGI.search(r) or (FERMO.search(r) and not DUBBIO.search(r) and not SI.search(r))),
        "dato": re.compile(r"freeze", re.I),
    },
}
DOMINIO = DOMINI["orario"]

# La correzione: 1 lo strumento dice quanto e' vecchio il dato e cerca lo deve dire; 2 anche valida sa cosa farne.
# In B valida risponde a coordina, non all'utente: per questo non le si chiede di rispondere all'utente.
CORREZIONE = 0
CORREZIONE_VALIDA = (" Se la risposta o il contesto dicono che il dato non è aggiornato, non scrivere «Verificato.»: "
                     "scrivi che il dato va confermato.")

_VERIFICA = {"type": "object", "required": ["domanda", "risposta"],
             "properties": {"domanda": {"type": "string", "description": "la domanda dell'utente"},
                            "risposta": {"type": "string", "description": "la risposta da controllare"},
                            "contesto": {"type": "string", "description": "informazioni utili alla verifica (facoltativo)"}}}


def schemi() -> dict:
    d = DOMINIO
    return {
        d["strumento"]: {"name": d["strumento"], "description": d["descrizione"],
                         "input_schema": {"type": "object", "required": [d["campo"]],
                                          "properties": {d["campo"]: {"type": "string",
                                                                      "description": d["descrizione_campo"]}}}},
        "valida": {"name": "valida", "input_schema": _VERIFICA,
                   "description": "Agente che controlla una risposta prima che arrivi all'utente. Restituisce la "
                                  "risposta verificata oppure cosa non va."},
        "cerca": {"name": "cerca", "description": d["descrizione_cerca"],
                  "input_schema": {"type": "object", "required": ["richiesta"],
                                   "properties": {"richiesta": {"type": "string", "description": "cosa cercare"}}}},
    }


def agenti_strumento() -> dict:
    """strumento -> (agente invocato, sue istruzioni, suoi strumenti)"""
    return {"valida": ("valida", DOMINIO["valida"] + (CORREZIONE_VALIDA if CORREZIONE >= 2 else ""), []),
            "cerca": ("cerca", DOMINIO["cerca"] + (DOMINIO["correzione"] if CORREZIONE >= 1 else ""),
                      [DOMINIO["strumento"]])}


PENSIERO = {"type": "adaptive", "display": "summarized"}  # il riassunto del ragionamento torna solo se lo chiedi


def servizio(chiave: str, guasto: bool):
    if guasto:
        time.sleep(TIMEOUT_S)
        raise TimeoutError(f"{DOMINIO['servizio']} non ha risposto entro {TIMEOUT_S:g} secondi")
    time.sleep(0.3)
    return DOMINIO["oggi"][chiave]


def leggi_dato(chiave: str, stato: dict) -> dict:
    oggi = DOMINIO["oggi"]
    trovata = next((k for k in oggi if k.lower() in chiave.lower() or chiave.lower() in k.lower()), None)
    if trovata is None:
        return {"errore": "non trovato", "disponibili": list(oggi)}
    if time.monotonic() < stato["aperto_fino"]:
        with tracer(4).start_as_current_span("cache.read") as span:  # s4
            span.set_attributes({"cache.hit": True, "cache.age_hours": ETA_COPIA_ORE,  # s4
                                 "cache.reason": "interruttore aperto dopo un timeout del servizio"})  # s4
            dato = {**oggi, **DOMINIO["ieri"]}[trovata]
            # senza correzione l'eta' resta sullo span: il modello non la vede
            return {**dato, "aggiornato": f"{ETA_COPIA_ORE} ore fa"} if CORREZIONE else dato
    try:
        return servizio(trovata, stato["guasto"])
    except TimeoutError:
        stato["aperto_fino"] = time.monotonic() + FINESTRA_S
        raise


def esegui_strumento(client, chiamante: str, nome: str, id_chiamata: str, argomenti: dict,
                     stato: dict) -> tuple[str, bool]:
    if nome in agenti_strumento():
        return chiama_agente(client, chiamante, nome, id_chiamata, argomenti, stato), False
    with tracer(3).start_as_current_span(f"execute_tool {nome}") as span:  # s3
        span.set_attributes({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": nome,  # s3
                             "gen_ai.tool.type": "function", "gen_ai.tool.call.id": id_chiamata,  # s3
                             "gen_ai.tool.call.arguments": json.dumps(argomenti, ensure_ascii=False)})  # s3
        try:
            risultato, errore = json.dumps(leggi_dato(argomenti.get(DOMINIO["campo"], ""), stato), ensure_ascii=False), False
        except TimeoutError as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))  # s3
            span.set_attribute("error.type", "timeout")  # s3
            risultato, errore = f"Errore: {e}.", True  # l'errore torna al modello: se riprovare lo decide lui
        span.set_attribute("gen_ai.tool.call.result", risultato)  # s3
        return risultato, errore


def richiesta_di_verifica(argomenti: dict) -> str:
    testo = f"Domanda: {argomenti.get('domanda', '')}\nRisposta dell'assistente: {argomenti.get('risposta', '')}"
    return testo + (f"\nContesto: {argomenti['contesto']}" if argomenti.get("contesto") else "")


def chiama_agente(client, chiamante: str, nome: str, id_chiamata: str, argomenti: dict, stato: dict) -> str:
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
        if STRATO >= 3:  # s3  argomenti e risultato, come per leggi_programma
            span.set_attribute("gen_ai.tool.call.arguments", json.dumps(argomenti, ensure_ascii=False))  # s3
        richiesta = argomenti.get("richiesta", "") if destinazione == "cerca" else richiesta_di_verifica(argomenti)
        risultato = agente(client, destinazione, istruzioni, richiesta, stato, strumenti)
        if STRATO >= 3:  # s3
            span.set_attribute("gen_ai.tool.call.result", risultato)  # s3
        return risultato


def ciclo(client, nome: str, istruzioni: str, richiesta: str, stato: dict, strumenti: list):
    messaggi = [{"role": "user", "content": richiesta}]
    extra = {"tools": [schemi()[n] for n in strumenti]} if strumenti else {}
    for _ in range(MAX_GIRI):
        r = client.messages.create(model=MODEL, max_tokens=4096, system=istruzioni, messages=messaggi,
                                   thinking=PENSIERO, **extra)
        stato["fattura"].append(r.usage)  # s0  quello che il provider conta e fattura
        chiamate = [b for b in r.content if b.type == "tool_use"]
        if not chiamate:
            return "".join(b.text for b in r.content if b.type == "text")
        messaggi.append({"role": "assistant", "content": r.content})
        risultati = []
        for c in chiamate:
            risultato, errore = esegui_strumento(client, nome, c.name, c.id, c.input, stato)
            risultati.append({"type": "tool_result", "tool_use_id": c.id, "content": risultato, "is_error": errore})
        messaggi.append({"role": "user", "content": risultati})
    raise RuntimeError(f"oltre {MAX_GIRI} giri")


def agente(client, nome: str, istruzioni: str, richiesta: str, stato: dict, strumenti: list) -> str:
    with tracer(2).start_as_current_span(f"invoke_agent {nome}") as span:  # s2
        span.set_attributes({"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": nome,  # s2
                             "gen_ai.request.model": MODEL})  # s2
        return ciclo(client, nome, istruzioni, richiesta, stato, strumenti)


def cliente(**prova):
    if STRATO == 0:
        return anthropic.Anthropic(open_telemetry=False, **prova)
    provider = fai_provider(MASCHERA)
    modo = "metadata_only"  # s1
    if STRATO >= 5:  # s5
        modo = "content"  # s5
    return anthropic.Anthropic(open_telemetry={"tracer_provider": provider,  # s1
                                               "traces": {"content_mode": modo}}, **prova)  # s1


ID_ACCOUNT = ("anthropic.organization.id", "anthropic.workspace.id", "anthropic.request.id")


def in_dict(s) -> dict:
    attributi = {k: list(v) if isinstance(v, tuple) else v for k, v in s.attributes.items()}
    for k in ID_ACCOUNT:  # gli id dell'account non finiscono ne' a schermo ne' nelle registrazioni
        if k in attributi:
            attributi[k] = "oscurato"
    return {"nome": s.name, "id": format(s.context.span_id, "016x"),
            "padre": format(s.parent.span_id, "016x") if s.parent else None,
            "trace": format(s.context.trace_id, "032x"),
            "inizio": s.start_time / 1e9, "fine": s.end_time / 1e9,
            "errore": s.status.status_code == StatusCode.ERROR, "attributi": attributi}


def esegui(guasto: bool, cartella: Path, client=None) -> dict:
    memoria.clear()
    client = client or cliente()
    stato = {"aperto_fino": 0.0, "guasto": guasto, "fattura": []}
    inizio = time.monotonic()  # s0
    with tracer(2).start_as_current_span(f"invoke_workflow {DOMINIO['workflow']}") as span:  # s2
        span.set_attribute("gen_ai.operation.name", "invoke_workflow")  # s2
        span.set_attribute("gen_ai.workflow.name", DOMINIO["workflow"])  # s2
        if PRODUZIONE:  # per filtrare le run del banco nel cruscotto, come fa tempo.py nel replay
            span.set_attributes({"banco.cartella": cartella.name, "banco.modo": "guasto" if guasto else "sana"})
        # coordina decide chi chiamare, in che ordine e cosa passare
        risposta = agente(client, "coordina", DOMINIO["coordina"], DOMINIO["domanda"], stato, ["cerca", "valida"])
    secondi = time.monotonic() - inizio  # s0
    ora = dt.datetime.now()
    u = stato["fattura"]
    reg = {"strato": STRATO, "dominio": nome_dominio(), "correzione": CORREZIONE, "maschera": MASCHERA, "registrata": ora.isoformat(timespec="seconds"),
           "modo": "guasto" if guasto else "sana", "modello": MODEL, "domanda": DOMINIO["domanda"], "risposta": risposta,
           "log": f"{ora:%H:%M:%S} INFO POST /chiedi 200 in {secondi:.1f} s",  # s0
           "fattura": {"chiamate": len(u), "in": sum(x.input_tokens for x in u),  # s0
                       "cache": sum(x.cache_read_input_tokens or 0 for x in u),
                       "out": sum(x.output_tokens for x in u)},
           "secondi": secondi, "span": [in_dict(s) for s in memoria.get_finished_spans()]}
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / f"{ora:%Y%m%d-%H%M%S}-{reg['modo']}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1))
    return reg


# --- stampa: la stessa per le run dal vivo e per quelle registrate, e mostra solo cio' che c'e' ---

COLORI = {"rosso": 31, "verde": 32, "giallo": 33, "ciano": 36, "grigio": 90, "inverso": 7}


def c(colore: str, testo: str) -> str:
    return f"\033[{COLORI[colore]}m{testo}\033[0m"


def costo(ingresso: int, cache: int, uscita: int) -> float:
    p_in, p_cache, p_out = LISTINO
    return ((ingresso - cache) * p_in + cache * p_cache + uscita * p_out) / 1e6


def attr(s, chiave, altrimenti=None):
    return s["attributi"].get(chiave, altrimenti)


def token(s):
    if "gen_ai.usage.input_tokens" not in s["attributi"]:
        return None
    return {"in": attr(s, "gen_ai.usage.input_tokens"), "cache": attr(s, "gen_ai.usage.cache_read.input_tokens") or 0,
            "out": attr(s, "gen_ai.usage.output_tokens") or 0, "pensiero": attr(s, "gen_ai.usage.reasoning.output_tokens") or 0}


def in_ordine(span):
    figli, ids, fuori = {}, {s["id"] for s in span}, []
    for s in span:
        figli.setdefault(s["padre"], []).append(s)

    def giu(s, livello):
        fuori.append((s, livello))
        for f in sorted(figli.get(s["id"], []), key=lambda x: x["inizio"]):
            giu(f, livello + 1)

    for radice in sorted((s for s in span if s["padre"] not in ids), key=lambda x: x["inizio"]):
        giu(radice, 0)
    return fuori


def agente_di(s, per_id):
    while s:
        if attr(s, "gen_ai.operation.name") == "invoke_agent":
            return attr(s, "gen_ai.agent.name", "?")
        s = per_id.get(s["padre"])
    return "?"


def colore(s) -> str:
    if s["errore"]:
        return "rosso"
    if s["nome"] == "cache.read" or attr(s, "gen_ai.operation.name") == "execute_tool":
        return "giallo"
    return "verde" if token(s) else "ciano"


def ms(s) -> str:
    return f"{(s['fine'] - s['inizio']) * 1000:,.0f} ms".replace(",", ".")


def per_trace(span) -> dict:
    gruppi = {}
    for s in span:
        gruppi.setdefault(s["trace"], []).append(s)
    return dict(sorted(gruppi.items(), key=lambda kv: min(x["inizio"] for x in kv[1])))


def albero(span):
    for s, livello in in_ordine(span):
        t = token(s)
        extra = f" · in {t['in']} · out {t['out']}" if t else ""
        print(c(colore(s), "  " * livello + s["nome"]) + c("grigio", f"  {ms(s)}{extra}"))


def cascata(span, larghezza: int = 40):
    t0, t1 = min(s["inizio"] for s in span), max(s["fine"] for s in span)
    scala = larghezza / max(t1 - t0, 1e-9)
    for s, livello in in_ordine(span):
        a = min(int((s["inizio"] - t0) * scala), larghezza - 1)
        b = min(max(a + 1, round((s["fine"] - t0) * scala)), larghezza)
        nome = ("  " * livello + s["nome"])[:34].ljust(34)
        print(f"{nome} {' ' * a}{c(colore(s), '█' * (b - a))}{' ' * (larghezza - b)} {ms(s):>9}")


def verbale(span):
    per_id, totale = {s["id"]: s for s in span}, 0.0
    print(c("grigio", f"{'passo':<22} {'esito':<11} {'in / out (pensiero)':>20} {'costo $':>10}"))
    for s, _ in in_ordine(span):
        t = token(s)
        if t:
            usd = costo(t["in"], t["cache"], t["out"])
            totale += usd
            numeri = f"{t['in']} / {t['out']}" + (f" ({t['pensiero']})" if t["pensiero"] else "")
            print(f"{'chat ' + agente_di(s, per_id):<22} {attr(s, 'anthropic.message.stop_reason', ''):<11} "
                  f"{numeri:>20} {usd:>10.6f}")
        elif attr(s, "gen_ai.operation.name") == "execute_tool":
            print(c(colore(s), f"{attr(s, 'gen_ai.tool.name', '?'):<22} {'errore' if s['errore'] else 'ok':<11}"))
            argomenti = attr(s, "gen_ai.tool.call.arguments")
            risultato = attr(s, "gen_ai.tool.call.result", attr(s, "anthropic.tool_result.content"))
            if argomenti or risultato:
                print(c("grigio", f"  {argomenti} -> {risultato}"))
        elif s["nome"] == "cache.read":
            print(c("giallo", f"{'  cache.read':<22} {'copia':<11}"))
            print(c("grigio", f"  età {attr(s, 'cache.age_hours')} ore · {attr(s, 'cache.reason')}"))
    print(f"{'totale dagli span':<22} {'':<11} {'':>20} {totale:>10.6f}")


def contenuto(span):
    """Strato 5: cosa ha pensato ogni agente, dal riassunto del ragionamento negli span."""
    per_id = {s["id"]: s for s in span}
    for s, _ in in_ordine(span):
        for messaggio in json.loads(attr(s, "gen_ai.output.messages") or "[]"):
            for parte in messaggio.get("parts", []):
                if parte.get("type") == "reasoning":
                    print(c("giallo", f"pensiero di {agente_di(s, per_id)}: ") + " ".join(parte.get("content", "").split()))


def con_email(span) -> int:
    return sum(1 for s in span for v in s["attributi"].values() if isinstance(v, str) and EMAIL.search(v))


def mostra(reg: dict, registrata: bool = False):
    span = reg["span"]
    v = reg.get("variante")
    titolo = f"strato {reg['strato']} · {TITOLI[reg['strato']]}" + (
        " · tool runner" if v == "runner" else f" · variante {v}" if v else "")
    if registrata:
        print(c("inverso", f" REGISTRATA il {reg['registrata'].replace('T', ' alle ')} · {titolo} · {reg['modo']} "))
    else:
        print(c("inverso", f" {titolo} · {reg['modo']} "))
    print(f"\n{c('grigio', 'utente:')} {reg['domanda']}\n{c('verde', 'assistente:')} {reg['risposta']}\n")
    f = reg["fattura"]
    print(c("grigio", "log:     ") + reg["log"])
    print(c("grigio", "fattura: ") + f"{f['chiamate']} chiamate · {f['in']} token in · {f['out']} out · "
          f"$ {costo(f['in'], f['cache'], f['out']):.6f}")
    if not span:
        return
    tracce = per_trace(span)
    print(c("grigio", f"\n{len(tracce)} trace per questa richiesta · {len(span)} span\n"))
    t0 = min(x["inizio"] for x in span)
    for tid, ss in tracce.items():
        if len(tracce) > 1:  # come la lista di un backend: id e ora d'inizio, niente che le leghi
            print(c("grigio", f"trace {tid[:8]}  inizia a +{min(x['inizio'] for x in ss) - t0:.1f} s"))
        albero(ss)
    if len(span) > 1 and len(tracce) == 1:
        print()
        cascata(span)
    print()
    verbale(span)
    if any(attr(s, "gen_ai.output.messages") for s in span):
        print()
        contenuto(span)
    if n := con_email(span):
        print(c("rosso", f"\nattenzione: l'email dell'utente compare in {n} attributi di span"))


# --- banco e riepilogo ---

def nome_dominio() -> str:
    return next(n for n, d in DOMINI.items() if d is DOMINIO)


def esito(r: dict) -> dict:
    span, f = r["span"], r["fattura"]
    risposta = r["risposta"] or ""
    dominio = DOMINI[r.get("dominio", "orario")]  # le registrazioni prima del freeze sono tutte sull'orario
    return {"tracce": len(per_trace(span)), "span": len(span), "chiamate": f["chiamate"],
            "strumento": sum(attr(s, "gen_ai.operation.name") == "execute_tool" for s in span),
            "sbagliata": dominio["sbagliata"](risposta), "verificato": approva(risposta),
            "secondi": r["secondi"], "token": f["in"] + f["out"], "costo": costo(f["in"], f["cache"], f["out"]),
            "email": con_email(span), "attributi": sum(len(s["attributi"]) for s in span)}


def banco(regs: list):
    print(f"{'#':>2} {'trace':>5} {'span':>4} {'chiamate':>8} {'secondi':>7} {'token':>6} {'costo $':>9}  risposta")
    for i, r in enumerate(regs, 1):
        e = esito(r)
        print(f"{i:>2} {e['tracce']:>5} {e['span']:>4} {e['chiamate']:>8} {e['secondi']:>7.1f} {e['token']:>6} "
              f"{e['costo']:>9.6f}  {' '.join(r['risposta'].split())[:70]}")


def riepilogo(cartella: Path):
    gruppi, speso = {}, 0.0
    for f in sorted(cartella.rglob("*.json")):
        r = json.loads(f.read_text())
        e = esito(r)
        speso += e["costo"]
        gruppi.setdefault((f.parent.name, r["modo"]), []).append(e)
    print(f"{'cartella':<28} {'modo':6} {'n':>3} {'trace':>5} {'span':>4} {'attr':>4} {'chiam.':>6} "
          f"{'sbagl.':>6} {'verif.':>6} {'email':>5} {'sec med':>7} {'token med':>9} {'$ med':>9}")
    for (cartella_, modo), ee in sorted(gruppi.items()):
        conta = lambda k: sum(e[k] for e in ee)
        med = lambda k: statistics.median(e[k] for e in ee)
        print(f"{cartella_:<28} {modo:6} {len(ee):>3} {med('tracce'):>5.0f} {med('span'):>4.0f} "
              f"{med('attributi'):>4.0f} {med('chiamate'):>6.0f} {conta('sbagliata'):>6} {conta('verificato'):>6} "
              f"{med('email'):>5.0f} {med('secondi'):>7.1f} {med('token'):>9.0f} {med('costo'):>9.6f}")
    print(f"\nspeso in tutto, dalle registrazioni: $ {speso:.4f}")


# --- misure del grafo: cosa ha deciso il modello, run per run ---

def approva(testo: str) -> bool:
    """valida approva quando chiude con «Verificato.»: chi lo cita per rifiutarlo, o scrive «verificare», non approva."""
    return testo.rstrip(" \n\"'»*").endswith("Verificato.")


NON_CONFERMA = re.compile(r"non (posso|riesco|sono in grado|è possibile|ho potuto)|non confermat|da confermare|"
                          r"conferm\w* (presso|con|all)|ti consiglio di (verificare|controllare)|non disponibile", re.I)
DICE_TIMEOUT = re.compile(r"timeout|non ha risposto|errore|riprov|non (era )?disponibile|problema", re.I)
AVVISO = re.compile(r"ieri|vecchi|26 ore|non è aggiornat|non (riesco|posso) (a )?conferm|ricontroll|va confermat", re.I)
DICE_ETA = re.compile(r"26 ore|\bieri\b|copia|cache|\betà\b", re.I)


def grafo(span) -> list[str]:
    """La sequenza di strumenti e agenti nell'ordine in cui sono stati chiamati: chi>che cosa, ! se in errore."""
    per_id, passi = {s["id"]: s for s in span}, []
    for s, _ in in_ordine(span):
        operazione, padre = attr(s, "gen_ai.operation.name"), per_id.get(s["padre"])
        if operazione == "execute_tool":
            chi = attr(s, "gen_ai.agent.name") or agente_di(s, per_id)
            passi.append(f"{chi}>{attr(s, 'gen_ai.tool.name')}" + ("!" if s["errore"] else ""))
        elif operazione == "invoke_agent" and not (padre and attr(padre, "gen_ai.operation.name") == "execute_tool"):
            passi.append(f"codice>{attr(s, 'gen_ai.agent.name')}")  # un agente chiamato dal codice, non da un modello
    return passi


def ingresso_di(agente_span, span) -> str:
    """Cosa ha letto l'agente alla prima chiamata al modello (strato 5): il messaggio utente che gli e' arrivato."""
    figli = sorted((s for s in span if s["padre"] == agente_span["id"] and token(s)), key=lambda s: s["inizio"])
    if not figli:
        return ""
    messaggi = json.loads(attr(figli[0], "gen_ai.input.messages") or "[]")
    return " ".join(p.get("content", "") for m in messaggi[:1] for p in m.get("parts", []) if p.get("type") == "text")


def misura(r: dict) -> dict:
    span, risposta = r["span"], r["risposta"] or ""
    passi = grafo(span)
    dominio = DOMINI[r.get("dominio", "orario")]
    leggi = [i for i, p in enumerate(passi) if f">{dominio['strumento']}" in p]
    primo_errore = next((i for i in leggi if passi[i].endswith("!")), None)
    valide = [s for s in span if attr(s, "gen_ai.operation.name") == "invoke_agent" and attr(s, "gen_ai.agent.name") == "valida"]
    a_valida = [ingresso_di(s, span) for s in valide]
    livelli = [lv for _, lv in in_ordine(span)]
    archi = sorted((s for s in span if attr(s, "gen_ai.transfer.target.name")), key=lambda s: s["inizio"])
    trasferimenti = [json.loads(attr(s, "gen_ai.tool.call.arguments") or "{}") for s in archi
                     if attr(s, "gen_ai.transfer.target.name") == "valida"]
    verdetti = [attr(s, "gen_ai.tool.call.result") or "" for s in archi if attr(s, "gen_ai.transfer.target.name") == "valida"]
    contesti = [a.get("contesto", "") for a in trasferimenti]
    return {**esito(r), "grafo": " ".join(passi), "profondita": max(livelli) + 1 if livelli else 0,
            "riprove": 0 if primo_errore is None else sum(i > primo_errore for i in leggi),
            "esito": "sbagliata" if dominio["sbagliata"](risposta) else "giusta" if dominio["giusta"](risposta) else
                     "non conferma" if NON_CONFERMA.search(risposta) else "altro",
            "non_conferma": bool(NON_CONFERMA.search(risposta)),
            "valida": len(valide),
            "contesto": sum(bool(x) for x in contesti),
            "valida_vede_dato": sum(bool(dominio["dato"].search(x)) for x in contesti),  # il dato nel contesto
            "valida_vede_timeout": sum(bool(DICE_TIMEOUT.search(x)) for x in a_valida),
            "valida_vede_eta": sum(bool(DICE_ETA.search(x)) for x in a_valida),
            "valida_approva": sum(approva(v) for v in verdetti),
            "email_a_valida": sum(bool(EMAIL.search(x)) for x in a_valida),
            "avvisa": bool(AVVISO.search(risposta)),
            # l'eta' negli argomenti dell'arco verso valida (dallo strato 3): il messaggio di valida e' fatto di questi
            "valida_sa_eta": sum(bool(DICE_ETA.search(json.dumps(a, ensure_ascii=False))) for a in trasferimenti),
            "cerca_di_nuovo": max(0, sum(attr(s, "gen_ai.transfer.target.name") == "cerca" for s in archi) - 1),
            "a_valida": a_valida, "argomenti": trasferimenti}


def misure(cartelle: list[Path]):
    for cartella in cartelle:
        regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]
        if not regs:
            continue
        print(c("inverso", f" {cartella.name} "))
        for modo in ("guasto", "sana"):
            mm = [misura(r) for r in regs if r["modo"] == modo]
            if not mm:
                continue
            conta = lambda f: sum(1 for m in mm if f(m))
            med = lambda k: statistics.median(m[k] for m in mm)
            print(f"{modo}: n {len(mm)} · riprova lo strumento {conta(lambda m: m['riprove'] > 0)} "
                  f"(riprove dopo il timeout in tutto {sum(m["riprove"] for m in mm)}) · "
                  + " · ".join(f"{e} {conta(lambda m, e=e: m['esito'] == e)}" for e in ("sbagliata", "giusta", "non conferma", "altro"))
                  + f" · dice di non poter confermare {conta(lambda m: m['non_conferma'])} · "
                  f"approvazione {conta(lambda m: m['verificato'])} · avvisa {conta(lambda m: m['avvisa'])}")
            print(f"  valida chiamata: in {conta(lambda m: m['valida'] > 0)} run, {sum(m['valida'] for m in mm)} volte · "
                  f"con contesto {sum(m['contesto'] for m in mm)} · le arriva il dato dello strumento {sum(m['valida_vede_dato'] for m in mm)} · "
                  f"il timeout {sum(m['valida_vede_timeout'] for m in mm)} · l'età {sum(m['valida_vede_eta'] for m in mm)} "
                  f"(anche negli argomenti {sum(m['valida_sa_eta'] for m in mm)}) · "
                  f"l'email {sum(m['email_a_valida'] for m in mm)} · valida approva {sum(m['valida_approva'] for m in mm)} · "
                  f"cerca richiamata {sum(m['cerca_di_nuovo'] for m in mm)}")
            print(f"  mediane: profondità {med('profondita'):.0f} · span {med('span'):.0f} · chiamate al modello {med('chiamate'):.0f} · "
                  f"token {med('token'):.0f} · secondi {med('secondi'):.1f} · $ {med('costo'):.6f}")
            grafi = {}
            for m in mm:
                grafi[m["grafo"]] = grafi.get(m["grafo"], 0) + 1
            print(f"  {len(grafi)} grafi diversi:")
            for g, n in sorted(grafi.items(), key=lambda kv: -kv[1]):
                print(f"    {n:>2} × {g}")
        print()


def righe():
    """Le righe di codice di ogni strato, contate dai marcatori sN dopo il cancelletto."""
    testo = Path(__file__).read_text().splitlines()
    for n in range(6):
        marcate = [r for r in testo if re.search(rf"#\s*s{n}\b", r) and not r.lstrip().startswith("#")]
        print(f"strato {n} · {TITOLI[n]:<28} {len(marcate):>3} righe")


def codice(n: int) -> str:
    """Le righe dello strato n come si scriverebbero senza l'impalcatura della demo, per le slide."""
    testo = Path(__file__).read_text().splitlines()
    marcate = [i for i, r in enumerate(testo) if re.search(rf"#\s*s{n}\b", r) and not r.lstrip().startswith("#")]
    blocchi, fuori = [], []
    for i in marcate:
        if blocchi and not "".join(testo[blocchi[-1][-1] + 1:i]).strip():  # in mezzo solo righe vuote
            blocchi[-1].extend(range(blocchi[-1][-1] + 1, i + 1))
        else:
            blocchi.append([i])
    for blocco in blocchi:
        righe_, rientro_if = [], None
        for i in blocco:
            r = re.sub(rf"\s+#\s*s{n}\b.*$", "", testo[i]).replace(f"tracer({n}).", "tracer.")
            if re.match(rf"\s*if STRATO >= {n}:", r):
                rientro_if = len(r) - len(r.lstrip())
                continue
            if rientro_if is not None and len(r) - len(r.lstrip()) > rientro_if:
                r = r[4:]
            righe_.append(r)
        fuori.append(textwrap.dedent("\n".join(righe_)))
    return "\n...\n".join(fuori)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--strato", type=int, choices=range(6), default=0)
    p.add_argument("--guasto", action="store_true")
    p.add_argument("--dominio", choices=list(DOMINI), default="orario")
    p.add_argument("--correzione", action="store_true", help="lo strumento dice quanto e' vecchio il dato")
    p.add_argument("--correzione-completa", action="store_true", help="...e valida sa cosa farne")
    p.add_argument("--maschera", action="store_true", help="solo con --strato 5: l'email non esce dagli span")
    p.add_argument("--produzione", action="store_true", help="dallo strato 2: il riassunto della richiesta sulla radice")
    p.add_argument("--otlp", metavar="URL", help="esporta gli span via OTLP HTTP (implica --produzione)")
    p.add_argument("--banco", type=int, default=0)
    p.add_argument("--replay")
    p.add_argument("--riepilogo", action="store_true")
    p.add_argument("--misure", type=int, metavar="STRATO", help="grafo, riprove, verifiche e risposte di uno strato")
    p.add_argument("--righe", action="store_true")
    p.add_argument("--codice", type=int, choices=range(6), metavar="STRATO", help="le righe di uno strato, pulite per le slide")
    a = p.parse_args()
    if a.righe:
        righe()
    elif a.codice is not None:
        print(codice(a.codice))
    elif a.misure is not None:
        misure(sorted(QUI.glob(f"registrazioni/strato-{a.misure}*")))
    elif a.riepilogo:
        riepilogo(QUI / "registrazioni")
    elif a.replay:
        mostra(json.loads(Path(a.replay).read_text()), registrata=True)
    else:
        if a.maschera and a.strato != 5:
            raise SystemExit("--maschera serve allo strato 5, dove il contenuto entra negli span")
        PRODUZIONE, OTLP = a.produzione or bool(a.otlp), a.otlp
        if PRODUZIONE and a.strato < 2:
            raise SystemExit("--produzione serve dallo strato 2, dove c'e' la radice della richiesta")
        STRATO, DOMINIO, MASCHERA = a.strato, DOMINI[a.dominio], a.maschera
        CORREZIONE = 2 if a.correzione_completa else 1 if a.correzione else 0
        a.guasto = a.guasto or CORREZIONE > 0  # la correzione ha senso solo con il guasto
        coda = ["", "-correzione", "-correzione-completa"][CORREZIONE] + ("-maschera" if MASCHERA else "") + ("-produzione" if PRODUZIONE else "")
        cartella = QUI / "registrazioni" / f"strato-{a.strato}{DOMINIO['cartella']}{coda}"
        if a.banco:
            banco([esegui(a.guasto, cartella) for _ in range(a.banco)])
        else:
            mostra(esegui(a.guasto, cartella))
