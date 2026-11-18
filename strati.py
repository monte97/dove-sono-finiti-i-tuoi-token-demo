"""La stessa risposta sbagliata, osservata uno strato alla volta.

Cinque agenti. `coordina` e' l'orchestratore: ha come strumenti gli agenti `programma`, `sale`, `avvisi` e
`valida` e decide lui chi chiamare, in che ordine, cosa passare e quando rispondere. `programma`, `sale` e
`avvisi` leggono ciascuno una fonte con uno strumento (`leggi_programma`, `leggi_sale`, `leggi_avvisi`),
`valida` controlla una risposta prima che arrivi all'utente. Nessun componente e' rotto: il programma di
ieri sera dice 15:00 sala B, e solo un avviso di stamattina sulla sala B dice che la sessione e' un'ora prima.

`--guasto` (modo "guasto" nelle registrazioni) e' la giornata piena: 40 pagine di avvisi, quello sulla sala B a
meta'. Senza `--guasto` (modo "sana") e' la giornata tranquilla: 3 pagine, niente sulla sala B.

Strati (ognuno contiene i precedenti):
  0  oggi: una riga di log per ogni chiamata al modello (agente e token) e la fattura, niente OpenTelemetry
  1  le metriche dei token e l'SDK: contatori per chiamata, un istogramma per agente in ogni richiesta, e la
     strumentazione nativa di anthropic
  2  gli agenti: span invoke_workflow, invoke_agent e gli archi fra agenti, scritti a mano
  3  lo strumento: span execute_tool con argomenti e risultato
  4  i dati letti: da dove viene il dato e quanto
  5  il contenuto: content_mode "content" (messaggi e ragionamento riassunto)

  python strati.py --strato 3 --guasto             una run
  python strati.py --strato 3 --guasto --banco 5   cinque run, una riga ciascuna
  python strati.py --strato 5 --correzione-dialogo avvisi puo' chiedere a programma (ricalcola la sala da solo)
  python strati.py --replay registrazioni/strato-3/<file>.json
  python strati.py --riepilogo                     una riga per strato e modo
  python strati.py --misure 5                      come ha deciso il grafo, cosa ha letto e riportato avvisi, token per agente
  python strati.py --righe                         righe di codice di ogni strato

Le righe che esistono solo per osservare finiscono con il marcatore dello strato (s0 ... s5 dopo il cancelletto).
La pipeline fissa, la variante A (agente come strumento) e il tool runner sono nel tag git spike-a-b.
"""

import argparse
import contextvars  # s2
import datetime as dt
import hashlib
import json
import logging
import re
import statistics
import sys
import textwrap
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.instrumentation.logging.handler import LoggingHandler  # s3
from opentelemetry.sdk._logs import LoggerProvider  # s3
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor  # s3
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader
from opentelemetry.sdk.resources import Resource  # s1
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from osservare_a_strati.evento.avvisi import (AVVISO_ALLARME, AVVISO_CHIAVE, AVVISI_PER_PAGINA, PAGINA_AVVISO,
                                              PAGINE_PIENA, PAGINE_TRANQUILLA, SEME_AVVISI, _MODELLI, _ORE, _voce, avvisi)
from osservare_a_strati.evento.dati import (AVVISI_AGGIORNATI, DOMANDA, PROGRAMMA, PUBBLICATO, SALE, SESSIONE_SALA,
                                            _trova, sala_normale)
from osservare_a_strati.modello import LISTINO, MAX_GIRI, MODEL, PENSIERO, costo
from osservare_a_strati.valutazione import (APPROVA, AVVISI_CAUSA, AVVISI_NEGA, AVVISI_SALA_B, CHIEDE_VARIAZIONI,
                                            CLASSI_DOMANDA, ESITI, _CONFINE_CLAUSOLA, _QUATTORDICI_POSSIBILE,
                                            _QUINDICI_SUPERATO, _avverte, _clausole, approva, classe_domanda,
                                            riporta_avviso, valuta)

QUI = Path(__file__).parent
load_dotenv(QUI / ".env")

TITOLI = {0: "oggi: un log e una fattura", 1: "le metriche e l'SDK", 2: "gli agenti", 3: "lo strumento",
          4: "i dati letti", 5: "il contenuto"}
STRATO = 0

EMAIL = re.compile(r"[\w.]+@[\w.]+\.\w+")
MASCHERA = False
PRODUZIONE = False  # il riassunto della richiesta sulla radice, per il cruscotto
OTLP = None  # dove esportare gli span, oltre alla memoria

# La versione del codice e del banco: il giorno del banco (tag banco-2026-11-05). Va nella Resource di span e log,
# cosi' una run dal vivo finisce in Tempo e in Loki sotto il servizio e la versione giusti. Si cambia solo se cambia
# qualcosa che il banco non ha misurato.
VERSIONE = "2026-11-05"  # s1
RISORSA = Resource.create({"service.name": "osservare-a-strati", "service.version": VERSIONE})  # s1


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


LOG = logging.getLogger("osservare-a-strati")  # i log come li scrive gia' un team: codice applicativo
LOG.setLevel(logging.INFO)
memoria_log = InMemoryLogRecordExporter()  # rifatto da fai_log a ogni run
_handler = None
_provider_log = None


def processore_otlp_log(url: str):
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    return BatchLogRecordProcessor(OTLPLogExporter(endpoint=url))


def url_log(url: str) -> str:
    """Dove vanno i log via OTLP: lo stesso host degli span, path /v1/logs."""
    return (url[:-len("/v1/traces")] if url.endswith("/v1/traces") else url.rstrip("/")) + "/v1/logs"


def fai_log():
    """Collega il logging di Python a OpenTelemetry: ogni riga esce col trace_id e lo span_id dello span corrente.
    Un solo handler alla volta: quello della run precedente viene tolto."""
    global _handler, _provider_log, memoria_log
    if _handler:
        LOG.removeHandler(_handler)
        _handler = None
    if _provider_log:  # chiude i processori della run precedente (con --otlp, il thread del batch)
        _provider_log.shutdown()
        _provider_log = None
    memoria_log = InMemoryLogRecordExporter()  # uno per run (e per provider: shutdown() chiude l'exporter)
    if STRATO < 3:
        return
    provider = LoggerProvider(resource=RISORSA)  # s3
    _provider_log = provider
    provider.add_log_record_processor(SimpleLogRecordProcessor(memoria_log))  # s3
    if OTLP:
        provider.add_log_record_processor(processore_otlp_log(url_log(OTLP)))
    _handler = LoggingHandler(logger_provider=provider)  # s3
    LOG.addHandler(_handler)  # s3


# Le righe di log per chiamata (strato 0) portano l'id della richiesta e il conto della risposta. Le prende anche
# l'impalcatura qui sotto, a ogni strato, per la stampa e per la registrazione: dallo strato 3 escono pure via OpenTelemetry.
# I nomi del conto sono quelli delle convenzioni GenAI di OpenTelemetry, gli stessi che l'SDK scrive sugli span:
# gen_ai.usage.input_tokens conta anche i token letti e scritti in cache. L'id della richiesta e' nostro.
CAMPI_RIGA = ("richiesta", "gen_ai.agent.name", "gen_ai.response.model", "gen_ai.usage.input_tokens",
              "gen_ai.usage.output_tokens", "gen_ai.usage.cache_read.input_tokens", "gen_ai.usage.cache_write.input_tokens")


class Righe(logging.Handler):
    """Impalcatura della demo, non strumentazione: tiene le righe di log della run che portano l'id della richiesta."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.righe = []

    def emit(self, record):
        if hasattr(record, "richiesta"):
            self.righe.append({"tempo": record.created, "livello": record.levelname, "testo": record.getMessage(),
                               "campi": {k: getattr(record, k) for k in CAMPI_RIGA if hasattr(record, k)}})


def logfmt(campi: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in campi.items())


# Le metriche (strato 1): un provider per processo. La memoria legge in delta, quindi a ogni run solo il nuovo.
memoria_metriche = InMemoryMetricReader(preferred_temporality={Counter: AggregationTemporality.DELTA,
                                                               Histogram: AggregationTemporality.DELTA})
_provider_metriche = None
TOKEN_IN = TOKEN_OUT = TOKEN_AGENTE = None
# I confini dell'istogramma: avvisi in una richiesta spende 17 mila token per volta che lavora (banco del 5/11),
# quindi una, due o tre volte cadono in tre secchi diversi.
CONFINI_TOKEN = [2_000, 5_000, 10_000, 20_000, 30_000, 40_000, 50_000, 60_000, 80_000, 100_000]


def url_metriche(url: str) -> str:
    """Dove vanno le metriche via OTLP: lo stesso host degli span, path /v1/metrics."""
    return (url[:-len("/v1/traces")] if url.endswith("/v1/traces") else url.rstrip("/")) + "/v1/metrics"


def fai_metriche():
    """Il provider delle metriche e i tre strumenti dei token: due contatori per chiamata con i nomi delle convenzioni
    GenAI, e un istogramma con un nome mio, un valore per agente a fine richiesta. Con --otlp escono ogni 5 secondi."""
    global _provider_metriche, TOKEN_IN, TOKEN_OUT, TOKEN_AGENTE
    if _provider_metriche:
        return
    lettori = [memoria_metriche]
    if OTLP:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        lettori.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=url_metriche(OTLP)),
                                                     export_interval_millis=5000))
    provider = MeterProvider(resource=RISORSA, metric_readers=lettori)  # s1
    misura = provider.get_meter("osservare-a-strati")  # s1
    TOKEN_IN = misura.create_counter("gen_ai.client.inference.usage.input_tokens", unit="{token}")  # s1
    TOKEN_OUT = misura.create_counter("gen_ai.client.inference.usage.output_tokens", unit="{token}")  # s1
    TOKEN_AGENTE = misura.create_histogram("assistente.agente.token", unit="{token}",  # s1
                                           description="token di un agente in una richiesta",  # s1
                                           explicit_bucket_boundaries_advisory=CONFINI_TOKEN)  # s1
    _provider_metriche = provider


def metriche_in_dict(dati) -> list[dict]:
    """Le misure lette dalla memoria: una voce per serie, con le trace degli exemplar (dallo strato 2, la richiesta)."""
    fuori = []
    for rm in (dati.resource_metrics if dati else []):
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                for p in m.data.data_points:
                    voce = {"nome": m.name, "attributi": dict(p.attributes or {})}
                    if hasattr(p, "bucket_counts"):  # istogramma
                        voce.update({"conteggio": p.count, "somma": p.sum})
                    else:
                        voce["valore"] = p.value
                    voce["exemplar"] = sorted({format(e.trace_id, "032x") for e in (p.exemplars or []) if e.trace_id})
                    fuori.append(voce)
    return fuori


def leggi_metriche() -> list[dict]:
    """Quello che le metriche hanno misurato dall'ultima lettura: vuoto finché nessuno strato 1 ha creato il provider."""
    return metriche_in_dict(memoria_metriche.get_metrics_data()) if _provider_metriche else []


memoria = InMemorySpanExporter()  # s1  ponytail: in memoria; dal vivo un exporter OTLP verso un backend
_spento = trace.NoOpTracer()


def processore_otlp(url: str):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    return BatchSpanProcessor(OTLPSpanExporter(endpoint=url))


def fai_provider(maschera: bool) -> TracerProvider:
    """Un provider per client: con la maschera, gli span passano da MascheraEmail prima dell'exporter."""
    global _vero
    provider = TracerProvider(resource=RISORSA)  # s1
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


# Istruzioni come le scriverebbe un team: dicono cosa fa ciascuno, non come evitare la trappola.
ISTRUZIONI = {
    "coordina": ("Sei l'assistente di DevFest Immaginario 2026 e coordini quattro agenti: programma legge il programma "
                 "pubblicato, sale le informazioni sulle sale (anche il piano), avvisi le comunicazioni di oggi, valida controlla una "
                 "risposta prima che arrivi all'utente. Per rispondere consulta programma, sale e avvisi; prima di "
                 "rispondere conviene far controllare la risposta da valida. Rispondi in una riga con giorno, ora, sala e piano."),
    "programma": ("Sei l'assistente del programma di DevFest Immaginario 2026. Per giorno, ora e sala di una sessione "
                  "usa sempre lo strumento leggi_programma; per il piano della sala chiedi all'agente sale. "
                  "Rispondi in una riga con giorno, ora, sala e piano."),
    "sale": ("Sei l'assistente delle sale di DevFest Immaginario 2026. Per sala, piano e capienza usa sempre lo strumento "
             "leggi_sale. Rispondi in una riga."),
    "avvisi": ("Sei l'assistente delle comunicazioni di DevFest Immaginario 2026. Gli avvisi di oggi li leggi con lo "
               "strumento leggi_avvisi. Riporta solo gli avvisi che riguardano ciò che ti è stato chiesto, al "
               "massimo tre righe, senza supposizioni; se non ce ne sono, rispondi «Nessun avviso.»."),
    "valida": ("Controlli le risposte dell'assistente di DevFest Immaginario 2026 prima che arrivino all'utente. "
               "Ricevi la domanda, la risposta e, se c'è, il contesto su cui si basa. Verifica che l'orario sia valido, "
               "che la sala esista (le sale sono A, B e C) e che la risposta sia pertinente alla domanda e coerente "
               "con il contesto. Se hai un dubbio sul contesto, puoi ricontrollarlo alla fonte prima di approvare: "
               "programma ti dice giorno, ora e sala di una sessione, avvisi le comunicazioni di oggi che la riguardano. "
               "Se va tutto bene, restituisci la risposta com'è aggiungendo in fondo «Verificato.». "
               "Altrimenti spiega cosa non va."),
}
DESCRIZIONI = {
    "programma": ("Agente che trova giorno, ora e sala di una sessione leggendo il programma pubblicato, e il piano "
                  "chiedendolo a sale. Risponde in una riga."),
    "sale": "Agente che trova sala, piano e capienza di una sessione leggendo il database delle sale. Risponde in una riga.",
    "avvisi": "Agente che riporta gli avvisi di oggi che riguardano la richiesta, al massimo tre righe.",
    "valida": ("Agente che controlla una risposta prima che arrivi all'utente. Restituisce la risposta verificata "
               "oppure cosa non va."),
}

# La correzione: 1 solo istruzioni a coordina (chiedi gli avvisi della sala dopo averla saputa);
# 2 in piu' leggi_avvisi vuole la sala e restituisce solo gli avvisi di quella sala (include la 1);
# 3 (dialogo) e' un'alternativa, non include la 1 ne' la 2: coordina e leggi_avvisi restano come nel guasto, ma
# avvisi puo' chiedere a programma giorno, ora e sala di una sessione.
CORREZIONE = 0
CORREZIONE_COORDINA = " Quando conosci la sala della sessione, chiedi ad avvisi le comunicazioni su quella sala."
CORREZIONE_AVVISI = " Lo strumento leggi_avvisi vuole la sala: usa quella indicata nella richiesta."
CORREZIONE_DIALOGO = (" Se per capire quali avvisi riguardano la richiesta ti servono giorno, ora e sala di una sessione, "
                      "puoi chiederli all'agente programma.")

_VERIFICA = {"type": "object", "required": ["domanda", "risposta"],
             "properties": {"domanda": {"type": "string", "description": "la domanda dell'utente"},
                            "risposta": {"type": "string", "description": "la risposta da controllare"},
                            "contesto": {"type": "string", "description": "informazioni utili alla verifica (facoltativo)"}}}


def _un_campo(campo: str, descrizione: str) -> dict:
    return {"type": "object", "required": [campo], "properties": {campo: {"type": "string", "description": descrizione}}}


def _sala_schema() -> dict:
    s = _un_campo("sala", "la sala: A, B o C")
    s["properties"]["sala"]["enum"] = ["A", "B", "C"]
    return s


def schemi(correzione: int | None = None) -> dict:
    sala = (CORREZIONE if correzione is None else correzione) == 2
    avvisi_tool = {"name": "leggi_avvisi", "input_schema": {"type": "object", "properties": {}},
                   "description": "Legge tutte le comunicazioni di oggi, tutte le pagine in una sola chiamata."}
    if sala:
        avvisi_tool = {"name": "leggi_avvisi", "input_schema": _sala_schema(),
                       "description": "Legge le comunicazioni di oggi che riguardano una sala."}
    return {
        "leggi_programma": {"name": "leggi_programma", "input_schema": _un_campo("sessione", "titolo della sessione"),
                            "description": "Legge dal programma pubblicato giorno, ora e sala di una sessione."},
        "leggi_sale": {"name": "leggi_sale", "input_schema": _un_campo("sessione", "titolo della sessione"),
                       "description": "Legge dal database delle sale sala, piano e capienza di una sessione."},
        "leggi_avvisi": avvisi_tool,
        **{n: {"name": n, "description": DESCRIZIONI[n], "input_schema": _un_campo("richiesta", "cosa cercare")}
           for n in ("programma", "sale", "avvisi")},
        "valida": {"name": "valida", "input_schema": _VERIFICA, "description": DESCRIZIONI["valida"]},
    }


def agenti_strumento(correzione: int | None = None) -> dict:
    """strumento -> (agente invocato, sue istruzioni, suoi strumenti)"""
    corr = CORREZIONE if correzione is None else correzione
    return {"programma": ("programma", ISTRUZIONI["programma"], ["leggi_programma", "sale"]),
            "sale": ("sale", ISTRUZIONI["sale"], ["leggi_sale"]),
            "avvisi": ("avvisi", ISTRUZIONI["avvisi"] + (CORREZIONE_AVVISI if corr == 2 else CORREZIONE_DIALOGO if corr == 3 else ""),
                       ["leggi_avvisi"] + (["programma"] if corr == 3 else [])),
            "valida": ("valida", ISTRUZIONI["valida"], ["programma", "avvisi"])}


def istruzioni_coordina(correzione: int | None = None) -> str:
    correzione = CORREZIONE if correzione is None else correzione
    return ISTRUZIONI["coordina"] + (CORREZIONE_COORDINA if correzione in (1, 2) else "")


# Che versione del comportamento sta girando: la modalita' di correzione e un hash corto del testo che il modello legge
# davvero (le istruzioni di ogni agente e le descrizioni e gli schemi degli strumenti, con la correzione applicata).
# Stesso testo, stesso hash: cambia solo se cambia una parola di un'istruzione o di una descrizione.
NOMI_CORREZIONE = ("nessuna", "istruzioni", "filtro", "dialogo")


def versione_prompt(correzione: int | None = None) -> str:
    testo = json.dumps({"coordina": istruzioni_coordina(correzione), "agenti": agenti_strumento(correzione),
                        "strumenti": schemi(correzione)}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(testo.encode()).hexdigest()[:8]


def versione(correzione: int | None = None) -> dict:
    """Quello che la registrazione e lo span radice dicono sulla versione, per una modalita' di correzione."""
    correzione = CORREZIONE if correzione is None else correzione
    return {"codice": VERSIONE, "correzione": NOMI_CORREZIONE[correzione], "prompt": versione_prompt(correzione)}


# Attributi inventati, con prefisso proprio (le convenzioni semantiche non li coprono):
#   programma.pubblicato_il   quando e' stato pubblicato il programma letto
#   sale.fonte                da dove viene il dato sulle sale
#   avvisi.pagine             pagine di avvisi restituite al modello
#   avvisi.letti              avvisi restituiti al modello
#   avvisi.filtro             "nessuno" oppure la sala richiesta
#   avvisi.aggiornati_alle    ora dell'ultimo aggiornamento della bacheca
#   richiesta.correzione      sulla radice: nessuna | istruzioni | filtro | dialogo
#   richiesta.versione_prompt sulla radice: hash corto delle istruzioni e delle descrizioni degli strumenti in uso
# (gli altri richiesta.*, i riassunti per richiesta del cruscotto, sono dichiarati in segnali.py)
def leggi_dato(nome: str, argomenti: dict, stato: dict) -> str:
    """Lo strumento che legge un dato. Niente e' rotto: ognuno risponde correttamente a cio' che gli si chiede."""
    if nome == "leggi_programma":
        sessione = argomenti.get("sessione", "")
        LOG.info("leggi_programma: %s dal programma pubblicato il %s", sessione, PUBBLICATO)
        if STRATO >= 4:  # s4
            trace.get_current_span().set_attribute("programma.pubblicato_il", PUBBLICATO)  # s4
        return json.dumps(_trova(PROGRAMMA, sessione)[1], ensure_ascii=False)
    if nome == "leggi_sale":
        sessione = argomenti.get("sessione", "")
        LOG.info("leggi_sale: %s dal database delle sale", sessione)
        if STRATO >= 4:  # s4
            trace.get_current_span().set_attribute("sale.fonte", "database delle sale")  # s4
        k, dato = _trova(SESSIONE_SALA, sessione)
        return json.dumps(SALE[dato] if k else dato, ensure_ascii=False)
    if nome != "leggi_avvisi":  # un nome inventato dal modello e' un errore suo, non un caso dei dati
        return json.dumps({"errore": f"strumento sconosciuto: {nome}"}, ensure_ascii=False)
    voci = [v for pagina in avvisi(stato["piena"]) for v in pagina]  # tutte le pagine, in una sola chiamata
    filtro = "nessuno"
    if CORREZIONE == 2:
        sala = sala_normale(argomenti.get("sala", ""))
        voci = [v for v in voci if v.startswith(f"Sala {sala}:")]
        filtro = f"sala {sala}"
    pagine = -(-len(voci) // AVVISI_PER_PAGINA)
    LOG.info("leggi_avvisi: %d pagine, %d avvisi, filtro %s", pagine, len(voci), filtro)
    if STRATO >= 4:  # s4
        trace.get_current_span().set_attributes({"avvisi.pagine": pagine, "avvisi.letti": len(voci),  # s4
                                                 "avvisi.filtro": filtro,  # s4
                                                 "avvisi.aggiornati_alle": AVVISI_AGGIORNATI})  # s4
    return "\n".join(f"- {v}" for v in voci) or "Nessun avviso."


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
        if STRATO >= 3:  # s3  argomenti e risultato, come per gli strumenti dei dati
            span.set_attribute("gen_ai.tool.call.arguments", json.dumps(argomenti, ensure_ascii=False))  # s3
        rifiuto = controlla_catena(destinazione, CATENA.get())
        if rifiuto:  # un errore vero del modello, che il codice non nasconde: lo vede lui e lo vede lo span
            span.set_status(StatusCode.ERROR, rifiuto)  # s2
            span.set_attribute("error.type", "ciclo")  # s2
            if STRATO >= 3:  # s3
                span.set_attribute("gen_ai.tool.call.result", rifiuto)  # s3
            return rifiuto, True
        richiesta = richiesta_di_verifica(argomenti) if destinazione == "valida" else argomenti.get("richiesta", "")
        risultato = agente(client, destinazione, istruzioni, richiesta, stato, strumenti)
        if STRATO >= 3:  # s3
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
        if STRATO >= 1:  # s1  le stesse cifre, come metriche
            attributi = {"gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic",  # s1
                         "gen_ai.token.modality": "text", "gen_ai.request.model": MODEL,  # s1
                         "gen_ai.response.model": r.model, "gen_ai.agent.name": nome}  # s1
            ingresso = u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)  # s1
            TOKEN_IN.add(ingresso, attributi)  # s1
            TOKEN_OUT.add(u.output_tokens, attributi)  # s1
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


def cliente(**prova):
    if STRATO == 0:
        fai_log()
        return anthropic.Anthropic(open_telemetry=False, **prova)
    fai_metriche()
    provider = fai_provider(MASCHERA)
    fai_log()
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


def log_in_dict(r) -> dict:
    """Un record di log con il contesto che l'handler gli ha messo: trace e span dello span corrente, e i campi della
    riga per chiamata se ci sono."""
    lr = r.log_record
    campi = {k: v for k, v in (lr.attributes or {}).items() if k in CAMPI_RIGA}
    return {"trace": format(lr.trace_id, "032x"), "span": format(lr.span_id, "016x"),
            "livello": lr.severity_text, "testo": lr.body, "tempo": lr.timestamp / 1e9,  # epoch in secondi, come inizio e fine degli span
            **({"campi": campi} if campi else {})}


def esegui(guasto: bool, cartella: Path, client=None) -> dict:
    memoria.clear()
    client = client or cliente()
    stato = {"piena": guasto, "fattura": [], "per_agente": {}, "lock": threading.Lock()}
    stato["richiesta"] = uuid.uuid4().hex[:8]  # s0  lo stesso id su ogni riga di log della richiesta, per ritrovarle insieme
    righe = Righe()  # le righe di log di questa run, per la stampa e la registrazione
    LOG.addHandler(righe)
    leggi_metriche()  # la memoria delle metriche riparte da qui: conta solo questa run
    inizio = time.monotonic()  # s0
    try:
        with tracer(2).start_as_current_span("invoke_workflow assistente-evento") as span:  # s2
            span.set_attribute("gen_ai.operation.name", "invoke_workflow")  # s2
            span.set_attribute("gen_ai.workflow.name", "assistente-evento")  # s2
            span.set_attributes({"richiesta.correzione": NOMI_CORREZIONE[CORREZIONE],  # s2
                                 "richiesta.versione_prompt": versione_prompt()})  # s2
            if PRODUZIONE:  # per filtrare le run del banco nel cruscotto, come fa tempo.py nel replay
                span.set_attributes({"banco.cartella": cartella.name, "banco.modo": "guasto" if guasto else "sana"})
            # coordina decide chi chiamare, in che ordine e cosa passare
            risposta = agente(client, "coordina", istruzioni_coordina(), DOMANDA, stato, ["programma", "sale", "avvisi", "valida"])
            if STRATO >= 1:  # s1  a fine richiesta, un valore per agente; dallo strato 2 porta la trace come exemplar
                for nome, n in stato["per_agente"].items():  # s1
                    TOKEN_AGENTE.record(n, {"gen_ai.agent.name": nome})  # s1
    finally:
        LOG.removeHandler(righe)
    secondi = time.monotonic() - inizio  # s0
    ora = dt.datetime.now()
    u = stato["fattura"]
    reg = {"strato": STRATO, "correzione": CORREZIONE, "maschera": MASCHERA, "registrata": ora.isoformat(timespec="seconds"),
           "modo": "guasto" if guasto else "sana", "versione": versione(), "modello": MODEL, "domanda": DOMANDA, "risposta": risposta,
           "log": f"{ora:%H:%M:%S} INFO POST /chiedi 200 in {secondi:.1f} s",  # s0
           "fattura": {"chiamate": len(u), "in": sum(x.input_tokens for x in u),  # s0
                       "cache": sum(x.cache_read_input_tokens or 0 for x in u),  # s0
                       "out": sum(x.output_tokens for x in u)},  # s0
           "secondi": secondi, "span": [in_dict(s) for s in memoria.get_finished_spans()],
           "log_otel": [log_in_dict(r) for r in memoria_log.get_finished_logs()],
           "richiesta": stato["richiesta"], "righe": righe.righe, "metriche": leggi_metriche()}
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / f"{ora:%Y%m%d-%H%M%S}-{reg['modo']}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1))
    return reg


# --- stampa: la stessa per le run dal vivo e per quelle registrate, e mostra solo cio' che c'e' ---

COLORI = {"rosso": 31, "verde": 32, "giallo": 33, "ciano": 36, "grigio": 90, "inverso": 7}


def c(colore: str, testo: str) -> str:
    return f"\033[{COLORI[colore]}m{testo}\033[0m"


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
    if attr(s, "gen_ai.operation.name") == "execute_tool":
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


def breve(testo, massimo: int = 200) -> str:
    """Per la stampa: i risultati lunghi (le 400 righe di avvisi) si accorciano; lo span e la registrazione restano interi."""
    testo = str(testo)
    if len(testo) <= massimo:
        return testo
    return testo[:massimo].rstrip().replace("\n", " ") + f"… {testo.count(chr(10)) + 1} righe"


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
                print(c("grigio", f"  {argomenti} -> {breve(risultato)}"))
    print(f"{'totale dagli span':<22} {'':<11} {'':>20} {totale:>10.6f}")


def contenuto(span):
    """Strato 5: cosa ha pensato ogni agente, dal riassunto del ragionamento negli span."""
    per_id = {s["id"]: s for s in span}
    for s, _ in in_ordine(span):
        for messaggio in json.loads(attr(s, "gen_ai.output.messages") or "[]"):
            for parte in messaggio.get("parts", []):
                if parte.get("type") == "reasoning":
                    print(c("giallo", f"pensiero di {agente_di(s, per_id)}: ") + " ".join(parte.get("content", "").split()))


def mostra_metriche(metriche: list):
    """Dallo strato 1: cosa hanno misurato le metriche in questa richiesta."""
    per_agente = {m["attributi"].get("gen_ai.agent.name", "?"): m["somma"] for m in metriche
                  if m["nome"] == "assistente.agente.token"}
    somma = lambda nome: round(sum(m["valore"] for m in metriche if m["nome"] == nome))
    print(c("grigio", "metriche: ") + "assistente.agente.token · " + " · ".join(
        f"{a} {round(n)}" for a, n in sorted(per_agente.items(), key=lambda kv: -kv[1])))
    print(c("grigio", "          ") + f"gen_ai.client.inference.usage · input_tokens "
          f"{somma('gen_ai.client.inference.usage.input_tokens')} · output_tokens {somma('gen_ai.client.inference.usage.output_tokens')}")


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
    con_contesto = sum("campi" in r for r in reg.get("log_otel", []))
    if con_contesto:  # dallo strato 3 le stesse righe escono anche con il contesto: si stampano li', una volta sola
        print(c("grigio", "log:     ") + f"{con_contesto} righe «chiamata al modello» (sotto, con il contesto) · "
              + reg["log"])
    elif reg.get("righe"):  # una riga per ogni chiamata al modello, con l'id della richiesta e il conto della risposta
        print(c("grigio", "log:"))
        for riga in reg["righe"]:
            print(f"  {dt.datetime.fromtimestamp(riga['tempo']):%H:%M:%S} {riga['livello']} {riga['testo']} "
                  + c("grigio", logfmt(riga["campi"])))
        print("  " + reg["log"])
    else:  # le registrazioni di prima delle righe per chiamata
        print(c("grigio", "log:     ") + reg["log"])
    print(c("grigio", "fattura: ") + f"{f['chiamate']} chiamate · {f['in']} token in · {f['out']} out · "
          f"$ {costo(f['in'], f['cache'], f['out']):.6f}")
    if reg.get("metriche"):
        mostra_metriche(reg["metriche"])
    if not span:
        return
    if reg.get("log_otel"):
        print(c("grigio", "\nlog con contesto:"))
        nomi_span = {s["id"]: s["nome"] for s in span}
        for r in reg["log_otel"]:
            campi = {k: v for k, v in r.get("campi", {}).items() if k not in ("richiesta", "gen_ai.response.model")}
            print(f"  {r['livello']:<5} {r['testo']}" + (c("grigio", " " + logfmt(campi)) if campi else "")
                  + c("grigio", f"  [{nomi_span.get(r['span'], '?')}]"))
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

def esito(r: dict) -> dict:
    span, f = r["span"], r["fattura"]
    risposta = r["risposta"] or ""
    return {"tracce": len(per_trace(span)), "span": len(span), "chiamate": f["chiamate"],
            "strumento": sum(attr(s, "gen_ai.operation.name") == "execute_tool" for s in span),
            "esito": valuta(risposta, r["modo"]),
            "secondi": r["secondi"], "token": f["in"] + f["out"], "costo": costo(f["in"], f["cache"], f["out"]),
            "email": con_email(span), "attributi": sum(len(s["attributi"]) for s in span)}


def banco(regs: list):
    print(f"{'#':>2} {'trace':>5} {'span':>4} {'chiamate':>8} {'secondi':>7} {'token':>6} {'costo $':>9}  risposta")
    for i, r in enumerate(regs, 1):
        e = esito(r)
        print(f"{i:>2} {e['tracce']:>5} {e['span']:>4} {e['chiamate']:>8} {e['secondi']:>7.1f} {e['token']:>6} "
              f"{e['costo']:>9.6f}  {' '.join(r['risposta'].split())[:70]}")


def esegui_banco(n: int, guasto: bool, cartella: Path, client=None) -> tuple[list, int]:
    """n run di fila. Una run che fallisce (oltre MAX_GIRI, errore dell'API dopo i tentativi dell'SDK) non ferma il banco:
    la causa va su stderr, la run non e' registrata come riuscita, e si va avanti."""
    riuscite, fallite = [], 0
    for i in range(1, n + 1):
        try:
            riuscite.append(esegui(guasto, cartella, client))
        except Exception as e:
            fallite += 1
            print(f"run {i} fallita: {type(e).__name__}: {e}", file=sys.stderr)
    return riuscite, fallite


def concludi_banco(n: int, riuscite: list, fallite: int):
    """Stampa il banco; se una run e' fallita esce con stato 1 (uno script o una pipeline se ne accorge)."""
    banco(riuscite)
    if fallite:
        print(f"\nrun fallite: {fallite} su {n} (non registrate)")
        raise SystemExit(1)


def riepilogo(cartella: Path):
    gruppi, speso = {}, 0.0
    for f in sorted(cartella.rglob("*.json")):
        r = json.loads(f.read_text())
        e = esito(r)
        speso += e["costo"]
        gruppi.setdefault((f.parent.name, r["modo"]), []).append(e)
    print(f"{'cartella':<28} {'modo':6} {'n':>3} {'trace':>5} {'span':>4} {'attr':>4} {'chiam.':>6} "
          f"{'giuste':>6} {'avvis.':>6} {'sbagl.':>6} {'email':>5} {'sec med':>7} {'token med':>9} {'$ med':>9}")
    for (cartella_, modo), ee in sorted(gruppi.items()):
        conta = lambda k: sum(e["esito"] == k for e in ee) if k in ESITI else sum(e[k] for e in ee)
        med = lambda k: statistics.median(e[k] for e in ee)
        print(f"{cartella_:<28} {modo:6} {len(ee):>3} {med('tracce'):>5.0f} {med('span'):>4.0f} "
              f"{med('attributi'):>4.0f} {med('chiamate'):>6.0f} {conta('giusta'):>6} {conta('avvisata'):>6} {conta('sbagliata'):>6} "
              f"{med('email'):>5.0f} {med('secondi'):>7.1f} {med('token'):>9.0f} {med('costo'):>9.6f}")
    print(f"\nspeso in tutto, dalle registrazioni: $ {speso:.4f}")


# --- misure del grafo: cosa ha deciso il modello, run per run ---


# I thread di uno stesso giro partono a pochi millisecondi uno dall'altro: se uno strumento istantaneo (leggi_programma)
# finisce prima che parta il fratello (un agente), sono comunque dello stesso giro. Un giro dopo, invece, parte dopo una
# chiamata al modello (secondi).
SCARTO_GIRO_S = 0.02


def grafo(span) -> list[str]:
    """Chi ha chiamato che cosa, in una forma che non dipende da chi e' partito prima nei rami paralleli.

    Le chiamate figlie dello stesso invoke_agent che partono mentre una del giro e' ancora in corso sono dello
    stesso giro (il modello le ha chieste insieme): si scrivono come insieme ordinato, `{avvisi,programma,sale}`.
    Dentro un'agente-strumento, fra parentesi, cosa ha chiamato a sua volta; `!` se lo span e' in errore."""
    figli = {}
    for x in span:
        figli.setdefault(x["padre"], []).append(x)
    e = lambda x, operazione: attr(x, "gen_ai.operation.name") == operazione

    def giri(agente_span):
        chiamate = sorted((x for x in figli.get(agente_span["id"], []) if e(x, "execute_tool")), key=lambda x: x["inizio"])
        gruppi = []
        for x in chiamate:
            if gruppi and (x["inizio"] < max(y["fine"] for y in gruppi[-1])  # parte mentre una del giro e' ancora in corso
                           or x["inizio"] - gruppi[-1][0]["inizio"] < SCARTO_GIRO_S):  # o subito dopo: uno strumento istantaneo
                gruppi[-1].append(x)
            else:
                gruppi.append([x])
        return gruppi

    def voce(gruppo):
        nomi = []
        for x in gruppo:
            dentro = " ".join(voce(g) for a in sorted((a for a in figli.get(x["id"], []) if e(a, "invoke_agent")),
                                                     key=lambda a: a["inizio"]) for g in giri(a))
            nomi.append(attr(x, "gen_ai.tool.name") + ("!" if x["errore"] else "") + (f"({dentro})" if dentro else ""))
        return nomi[0] if len(nomi) == 1 else "{" + ",".join(sorted(nomi)) + "}"

    per_id, passi = {x["id"]: x for x in span}, []
    radici = sorted((x for x in span if e(x, "invoke_agent")
                     and not (per_id.get(x["padre"]) and e(per_id[x["padre"]], "execute_tool"))), key=lambda x: x["inizio"])
    for a in radici:
        nome = attr(a, "gen_ai.agent.name")
        passi.append(f"codice>{nome}")  # un agente chiamato dal codice, non da un modello
        passi += [f"{nome}>{voce(g)}" for g in giri(a)]
    return passi


# Le misure della giornata piena. Ognuna dice da quale strato in su gli span che servono esistono: sotto, None.
MINIMO_MISURE = {"stesso_giro": 2, "dopo_sala": 2, "token": 2, "letto": 3, "riporta": 3, "verdetti": 3, "email_valida": 3,
                 "pagine": 4, "sale_due": 2, "valida_rivede": 2, "valida_riporta": 3, "dialogo": 2, "dialogo_riporta": 3,
                 "cicli": 2, "profondita_agenti": 2, "domanda_avvisi": 3}


def domande_ad_avvisi(span) -> list[str]:
    """Gli argomenti `richiesta` degli archi coordina -> avvisi, nell'ordine in cui sono partiti."""
    fuori = []
    for x in archi(span, ("avvisi",), da="coordina"):
        try:
            fuori.append(str(json.loads(attr(x, "gen_ai.tool.call.arguments", "{}")).get("richiesta", "")))
        except (ValueError, AttributeError):
            fuori.append("")
    return fuori


def archi(span, verso=None, da=None) -> list:
    """Gli archi fra agenti (execute_tool con destinazione), in ordine di inizio, magari solo verso certi agenti
    e/o solo chiamati da un certo agente."""
    return sorted((x for x in span if attr(x, "gen_ai.operation.name") == "execute_tool"
                   and attr(x, "gen_ai.transfer.target.name") and (verso is None or attr(x, "gen_ai.transfer.target.name") in verso)
                   and (da is None or attr(x, "gen_ai.agent.name") == da)),
                  key=lambda x: x["inizio"])


def strumenti(span, nome: str) -> list:
    return [x for x in span if attr(x, "gen_ai.operation.name") == "execute_tool" and attr(x, "gen_ai.tool.name") == nome
            and not attr(x, "gen_ai.transfer.target.name")]


def stesso_giro(span) -> bool:
    """programma, sale e avvisi sono partiti insieme: gli archi hanno lo stesso padre e si sovrappongono nel tempo."""
    primi = {}
    for x in archi(span, ("programma", "sale", "avvisi"), da="coordina"):  # le chiamate annidate non contano
        primi.setdefault(attr(x, "gen_ai.transfer.target.name"), x)
    tre = list(primi.values())
    return len(tre) == 3 and len({x["padre"] for x in tre}) == 1 and max(x["inizio"] for x in tre) < min(x["fine"] for x in tre)


def avvisi_dopo_sala(span) -> bool:
    """avvisi e' stato chiamato quando programma o sale avevano gia' finito: coordina sapeva gia' la sala."""
    precedenti = archi(span, ("programma", "sale"), da="coordina")
    return any(p["fine"] <= a["inizio"] for a in archi(span, ("avvisi",), da="coordina") for p in precedenti)


def sale_da_due(span) -> bool:
    """sale e' stato chiamato da due agenti diversi (coordina e programma): lo stesso dato letto per due strade."""
    return len({attr(x, "gen_ai.agent.name") for x in archi(span, ("sale",))}) >= 2


def figli_arco(span, arco):
    """Gli archi che l'agente chiamato da `arco` ha chiamato a sua volta."""
    dentro = {x["id"] for x in span if x["padre"] == arco["id"] and attr(x, "gen_ai.operation.name") == "invoke_agent"}
    return [x for x in archi(span) if x["padre"] in dentro]


def dialogo(span) -> bool:
    """avvisi ha chiesto a programma (la correzione dialogo)."""
    return bool(archi(span, ("programma",), da="avvisi"))


def dialogo_riporta(span) -> bool:
    """...e poi la sua risposta riporta l'avviso sulla sala B."""
    return any(riporta_avviso(attr(a, "gen_ai.tool.call.result", "")) for a in archi(span, ("avvisi",))
               if any(attr(f, "gen_ai.transfer.target.name") == "programma" for f in figli_arco(span, a)))


def cicli(span) -> int:
    """Quante volte la guardia ha rifiutato una chiamata (archi in errore con error.type ciclo)."""
    return sum(attr(x, "error.type") == "ciclo" for x in archi(span))


def profondita_agenti(span) -> int:
    """Quanti agenti uno dentro l'altro, contando gli archi da coordina in giu': il ramo piu' lungo."""
    per_id, fondo = {x["id"]: x for x in span}, 0
    for a in archi(span):
        n, y = 0, a
        while y:
            n += attr(y, "gen_ai.transfer.target.name") is not None and attr(y, "gen_ai.operation.name") == "execute_tool"
            y = per_id.get(y["padre"])
        fondo = max(fondo, n)
    return fondo


def _letture_avvisi(span, di_coordina: bool) -> int:
    """Pagine lette da leggi_avvisi: quelle sotto l'arco di avvisi chiamato da coordina, oppure tutte le altre."""
    per_id, tot = {x["id"]: x for x in span}, 0
    for x in strumenti(span, "leggi_avvisi"):
        y = per_id.get(x["padre"])
        while y and not (attr(y, "gen_ai.operation.name") == "execute_tool" and attr(y, "gen_ai.transfer.target.name")):
            y = per_id.get(y["padre"])
        if (y is not None and attr(y, "gen_ai.agent.name") == "coordina") == di_coordina:
            tot += attr(x, "avvisi.pagine", 0)
    return tot


def pagine_avvisi(span) -> int:
    """Le pagine che legge l'avvisi chiamato da coordina: il numero della slide."""
    return _letture_avvisi(span, True)


def pagine_ricontrolli(span) -> int:
    """Le pagine lette da leggi_avvisi sotto qualunque altro chiamante (i ricontrolli di valida, il dialogo)."""
    return _letture_avvisi(span, False)


def verdetti(span) -> list[bool]:
    return [approva(attr(x, "gen_ai.tool.call.result")) for x in archi(span, ("valida",))
            if attr(x, "gen_ai.tool.call.result") is not None]


def token_per_agente(span) -> dict:
    """Token (ingresso e uscita) delle chiamate al modello, per agente che le ha fatte."""
    per_id, fuori = {x["id"]: x for x in span}, {}
    for x in span:
        if t := token(x):
            nome = agente_di(x, per_id)
            fuori[nome] = fuori.get(nome, 0) + t["in"] + t["out"]
    return fuori


def chiamate_dagli_span(span) -> list[dict]:
    """Le chiamate al modello ricostruite dagli span, dallo strato 2 in su, in ordine di fine: l'agente e il suo
    invoke_agent (lo span corrente quando la riga di log parte), la fine e il conto con i nomi del provider. Servono a
    tempo.py: le registrazioni del banco del 5/11 sono di prima delle righe per chiamata e delle metriche, e righe e
    misure si rifanno da qui, con le cifre di quella run. L'SDK scrive gen_ai.usage.input_tokens con la cache dentro."""
    per_id, fuori = {x["id"]: x for x in span}, []
    for x in sorted(span, key=lambda x: x["fine"]):
        if (t := token(x)) is None:
            continue
        y = x
        while y and attr(y, "gen_ai.operation.name") != "invoke_agent":
            y = per_id.get(y["padre"])
        if y is None:  # sotto lo strato 2 l'agente non si sa
            continue
        scritti = attr(x, "gen_ai.usage.cache_write.input_tokens") or 0
        fuori.append({"agente": attr(y, "gen_ai.agent.name"), "span": y["id"], "trace": x["trace"], "fine": x["fine"],
                      "campi": {"gen_ai.agent.name": attr(y, "gen_ai.agent.name"),
                                "gen_ai.response.model": attr(x, "gen_ai.response.model", MODEL),
                                "gen_ai.usage.input_tokens": t["in"], "gen_ai.usage.output_tokens": t["out"],
                                "gen_ai.usage.cache_read.input_tokens": t["cache"],
                                "gen_ai.usage.cache_write.input_tokens": scritti}})
    return fuori


def costo_per_agente(span) -> dict:
    """Costo in $ (a LISTINO) delle chiamate al modello, per agente che le ha fatte."""
    per_id, fuori = {x["id"]: x for x in span}, {}
    for x in span:
        if t := token(x):
            nome = agente_di(x, per_id)
            fuori[nome] = fuori.get(nome, 0) + costo(t["in"], t["cache"], t["out"])
    return fuori


def quota_riletture(span) -> float | None:
    """Quota dei token in ingresso che il modello rilegge. In ogni invoke_agent, ogni chiamata dopo la prima rilegge
    la conversazione fin li': conta i token in ingresso della chiamata precedente dello stesso invoke_agent. La quota
    e' la somma di questi sulla somma dei token in ingresso di tutte le chiamate (None se non ci sono token)."""
    per_id, per_invoke = {x["id"]: x for x in span}, {}
    for x in span:
        if token(x):
            y = x
            while y and attr(y, "gen_ai.operation.name") != "invoke_agent":
                y = per_id.get(y["padre"])
            per_invoke.setdefault(y["id"] if y else None, []).append(x)
    totale = sum(token(x)["in"] for xs in per_invoke.values() for x in xs)
    riletti = sum(token(a)["in"] for xs in per_invoke.values() for a, _ in zip(sorted(xs, key=lambda x: x["inizio"]), xs[1:]))
    return riletti / totale if totale else None


def quota_avvisi(span) -> float | None:
    """Che parte dei token della richiesta e' spesa dall'agente avvisi (None se non ci sono token)."""
    per_agente = token_per_agente(span)
    return per_agente.get("avvisi", 0) / sum(per_agente.values()) if per_agente else None


def misura(r: dict) -> dict:
    """Cosa e' successo in una run: il grafo, cosa ha letto e riportato avvisi, i verdetti di valida, i token per agente.
    None dove gli span che servono non esistono a quello strato."""
    span, risposta, strato = r["span"], r["risposta"] or "", r["strato"]
    se = lambda nome, valore: valore() if strato >= MINIMO_MISURE[nome] else None
    livelli = [lv for _, lv in in_ordine(span)]
    avvisi_tool, a_avvisi = strumenti(span, "leggi_avvisi"), archi(span, ("avvisi",), da="coordina")
    ricontrolli = archi(span, ("avvisi",), da="valida")
    verdetto = se("verdetti", lambda: verdetti(span))
    return {**esito(r), "grafo": " ".join(grafo(span)), "profondita": max(livelli) + 1 if livelli else 0,
            "stesso_giro": se("stesso_giro", lambda: stesso_giro(span)),
            "avvisi_dopo_sala": se("dopo_sala", lambda: avvisi_dopo_sala(span)),
            "pagine_avvisi": se("pagine", lambda: pagine_avvisi(span)),
            "pagine_ricontrolli": se("pagine", lambda: pagine_ricontrolli(span)),
            "tool_ha_avviso": se("letto", lambda: any(AVVISO_CHIAVE in attr(x, "gen_ai.tool.call.result", "") for x in avvisi_tool)),
            "avvisi_riporta": se("riporta", lambda: any(riporta_avviso(attr(x, "gen_ai.tool.call.result", "")) for x in a_avvisi)),
            "classe_domanda": se("domanda_avvisi", lambda: classe_domanda(domande_ad_avvisi(span)[0]) if a_avvisi else None),
            "avvisi_riporta_primo": se("domanda_avvisi", lambda: bool(a_avvisi) and riporta_avviso(attr(a_avvisi[0], "gen_ai.tool.call.result", ""))),
            "avvisi_con_sala": se("riporta", lambda: any(AVVISI_SALA_B.search(attr(x, "gen_ai.tool.call.arguments", "")) for x in a_avvisi)),
            "sale_da_due": se("sale_due", lambda: sale_da_due(span)),
            "valida_avvisi": se("valida_rivede", lambda: bool(ricontrolli)),
            "valida_avvisi_riporta": se("valida_riporta", lambda: any(riporta_avviso(attr(x, "gen_ai.tool.call.result", "")) for x in ricontrolli)),
            "valida_programma": se("valida_rivede", lambda: bool(archi(span, ("programma",), da="valida"))),
            "avvisi_chiede_programma": se("dialogo", lambda: dialogo(span)),
            "avvisi_poi_riporta": se("dialogo_riporta", lambda: dialogo_riporta(span)),
            "cicli": se("cicli", lambda: cicli(span)),
            "profondita_agenti": se("profondita_agenti", lambda: profondita_agenti(span)),
            "valida_chiamate": None if verdetto is None else len(verdetto),
            "valida_approva": None if verdetto is None else sum(verdetto),
            "email_a_valida": se("email_valida", lambda: any(EMAIL.search(attr(x, "gen_ai.tool.call.arguments", ""))
                                                             for x in archi(span, ("valida",)))),
            "token_agente": se("token", lambda: token_per_agente(span)),
            "quota_avvisi": se("token", lambda: quota_avvisi(span)),
            "costo_agente": se("token", lambda: costo_per_agente(span)),
            "riletture": se("token", lambda: quota_riletture(span))}


def tabella_domande(mm: list[dict]) -> list[str]:
    """La tabella incrociata «domanda di coordina ad avvisi × esito», sulla prima domanda di ogni run (quella dei rami
    paralleli, quando coordina non sa ancora la sala), e per ogni classe quante volte avvisi riporta l'avviso a coordina
    (nella prima risposta e in qualunque giro)."""
    righe = [f"  {'domanda di coordina ad avvisi × esito':<50} {'n':>3} {'giusta':>7} {'avvisata':>9} {'sbagliata':>10}"
             f" {'avvisi riporta (1° giro)':>25} {'(qualunque giro)':>17}"]
    for classe in CLASSI_DOMANDA + (None,):
        gruppo = [m for m in mm if m["classe_domanda"] == classe]
        if not gruppo:
            continue
        nome = {"variazioni": "nomina orario, sala, variazioni...", "sessione": "nomina solo la sessione",
                None: "avvisi non chiamato"}[classe]
        righe.append(f"    {nome:<48} {len(gruppo):>3} " + " ".join(
            f"{sum(m['esito'] == e for m in gruppo):>{w}}" for e, w in zip(ESITI, (7, 9, 10)))
            + f" {sum(m['avvisi_riporta_primo'] for m in gruppo):>25} {sum(bool(m['avvisi_riporta']) for m in gruppo):>17}")
    return righe


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
            n, strato = len(mm), regs[0]["strato"]
            med = lambda k: statistics.median(m[k] for m in mm)

            def conta(k, minimo, etichetta):  # quante run su n; se lo strato non basta lo dice
                if any(m[k] is None for m in mm):
                    return f"  {etichetta:<52} serve lo strato {minimo}"
                return f"  {etichetta:<52} {sum(bool(m[k]) for m in mm):>2} su {n}"
            print(f"{modo}: n {n} · " + " · ".join(
                f"{e} {sum(1 for m in mm if m['esito'] == e)}" for e in ESITI))
            print(conta("stesso_giro", 2, "programma, sale, avvisi nello stesso giro"))
            print(conta("avvisi_dopo_sala", 2, "avvisi chiamato dopo che si sapeva la sala"))
            print(conta("avvisi_con_sala", 3, "la richiesta ad avvisi nomina la sala B"))
            print(conta("tool_ha_avviso", 3, "leggi_avvisi ha restituito l'avviso sulla sala B"))
            print(conta("avvisi_riporta", 3, "avvisi lo riporta a coordina"))
            if strato >= MINIMO_MISURE["domanda_avvisi"] and modo == "guasto":
                print("\n".join(tabella_domande(mm)))
            print(conta("sale_da_due", 2, "sale chiamato da due chiamanti diversi"))
            print(conta("valida_avvisi", 2, "valida richiede ad avvisi"))
            print(conta("valida_avvisi_riporta", 3, "...e la risposta di avvisi riporta l'avviso"))
            print(conta("valida_programma", 2, "valida richiede a programma"))
            if regs[0].get("correzione") == 3:  # solo la correzione dialogo
                print(conta("avvisi_chiede_programma", 2, "avvisi chiede a programma"))
                print(conta("avvisi_poi_riporta", 3, "...e poi avvisi riporta l'avviso"))
            if strato < MINIMO_MISURE["pagine"]:
                print(f"  {'pagine di avvisi lette':<52} serve lo strato 4")
            else:
                print(f"  {'pagine di avvisi lette da coordina':<52} mediana {med('pagine_avvisi'):.0f} (da {min(m['pagine_avvisi'] for m in mm)} "
                      f"a {max(m['pagine_avvisi'] for m in mm)})")
                print(f"  {'pagine di avvisi nei ricontrolli':<52} mediana {med('pagine_ricontrolli'):.0f} (da {min(m['pagine_ricontrolli'] for m in mm)} "
                      f"a {max(m['pagine_ricontrolli'] for m in mm)})")
            if any(m["valida_approva"] is None for m in mm):
                print(f"  {'valida approva':<52} serve lo strato 3")
            else:
                print(f"  {'valida approva':<52} {sum(m['valida_approva'] > 0 for m in mm):>2} su {n} · "
                      f"mai chiamata in {sum(m['valida_chiamate'] == 0 for m in mm)}")
            print(conta("email_a_valida", 3, "l'email arriva a valida"))
            if strato < MINIMO_MISURE["token"]:
                print(f"  {'token per agente':<52} serve lo strato 2")
            else:
                agenti = sorted({a for m in mm for a in m["token_agente"]})
                print(f"  {'token per agente (mediana)':<52} " + " · ".join(
                    f"{a} {statistics.median(m['token_agente'].get(a, 0) for m in mm):.0f}" for a in agenti))
                print(f"  {'costo per agente, $ (mediana)':<52} " + " · ".join(
                    f"{a} {statistics.median(m['costo_agente'].get(a, 0) for m in mm):.6f}" for a in agenti))
                print(f"  {'quota di avvisi sui token della richiesta':<52} mediana {med('quota_avvisi'):.0%}")
                print(f"  {'quota delle riletture (token in ingresso)':<52} mediana {med('riletture'):.0%}")
            if strato < MINIMO_MISURE["cicli"]:
                print(f"  {'guardia dei cicli scattata':<52} serve lo strato 2")
            else:
                print(f"  {'guardia dei cicli scattata':<52} {sum(m['cicli'] > 0 for m in mm):>2} su {n} · {sum(m['cicli'] for m in mm)} volte"
                      + (" · guardia mai scattata" if not any(m['cicli'] for m in mm) else ""))
                print(f"  massimi: profondità {max(m['profondita'] for m in mm)} (agenti uno dentro l'altro "
                      f"{max(m['profondita_agenti'] for m in mm)}) · span {max(m['span'] for m in mm)}")
            print(f"  mediane: profondità {med('profondita'):.0f} · span {med('span'):.0f} · chiamate al modello "
                  f"{med('chiamate'):.0f} · token {med('token'):.0f} · secondi {med('secondi'):.1f} · $ {med('costo'):.6f}")
            grafi = {}
            for m in mm:
                grafi[m["grafo"]] = grafi.get(m["grafo"], 0) + 1
            if strato < 2:  # senza invoke_agent non c'e' un albero da confrontare
                print(f"  {"forme dell'albero":<52} serve lo strato 2")
            else:
                print(f"  {len(grafi)} forme dell'albero:")
                for g, k in sorted(grafi.items(), key=lambda kv: -kv[1]):
                    print(f"    {k:>2} × {g}")
        print()


# --- lo schema del sistema: il grafo delle chiamate fra agenti, aggregato sulle run ---

ORDINE_NODI = ("utente", "coordina", "programma", "sale", "avvisi", "valida")  # l'ordine in cui si disegnano


def _ordine(nome: str):
    return (ORDINE_NODI.index(nome), nome) if nome in ORDINE_NODI else (len(ORDINE_NODI), nome)


def archi_della_run(span) -> dict:
    """Per una run: {(chiamante, chiamato): quante volte}, con gli strumenti dei dati (leggi_*) come foglie.
    Il chiamante di uno strumento dei dati e' l'agente dell'invoke_agent che lo contiene."""
    per_id, fuori = {x["id"]: x for x in span}, {}
    for x in span:
        if attr(x, "gen_ai.operation.name") != "execute_tool":
            continue
        if attr(x, "gen_ai.transfer.target.name"):
            chiave = (attr(x, "gen_ai.agent.name"), attr(x, "gen_ai.transfer.target.name"))
        else:
            padre = per_id.get(x["padre"])
            chiave = (attr(padre, "gen_ai.agent.name") if padre else None, attr(x, "gen_ai.tool.name"))
        if chiave[0] and chiave[1]:
            fuori[chiave] = fuori.get(chiave, 0) + 1
    return fuori


def _agenti(span) -> set:
    return {attr(x, "gen_ai.agent.name") for x in span if attr(x, "gen_ai.operation.name") == "invoke_agent"}


def schema(regs: list[dict], senza_strumenti: bool = False) -> tuple[str, str]:
    """(testo, mermaid) dello schema delle chiamate, sulle registrazioni date (tutte dallo strato 2 in su)."""
    n = len(regs)
    strato = min(r["strato"] for r in regs)
    archi_run = [archi_della_run(r["span"]) for r in regs]
    agenti = set().union(*(_agenti(r["span"]) for r in regs)) | {"coordina"}
    arco = {}  # (da, a) -> [run in cui compare, volte in totale]
    for ar in archi_run:
        for k, v in ar.items():
            e = arco.setdefault(k, [0, 0])
            e[0] += 1
            e[1] += v
    # rimpalli: chi e' chiamato da due chiamanti diversi nella stessa run
    due_chiamanti, doppia_strada = {}, False
    for ar in archi_run:
        chiamanti = {}
        for (da, a) in ar:
            if a in agenti:
                chiamanti.setdefault(a, set()).add(da)
        for a, ds in chiamanti.items():
            if len(ds) >= 2:
                due_chiamanti.setdefault(a, [0, set()])
                due_chiamanti[a][0] += 1
                due_chiamanti[a][1] |= ds
        doppia_strada |= {"coordina", "programma"} <= chiamanti.get("sale", set())
    guardie = [(r, [x for x in archi(r["span"]) if attr(x, "error.type") == "ciclo"]) for r in regs]
    arco_guardia = {(attr(x, "gen_ai.agent.name"), attr(x, "gen_ai.transfer.target.name")) for _, g in guardie for x in g}
    # tratteggiati: chi controlla o chiede a una fonte fuori dal giro di coordina (valida che richiama, avvisi che chiede a
    # programma) e gli archi respinti dalla guardia. In rosso, pieno: la strada in piu' coordina → sale, quando sale e'
    # chiamato anche da programma nella stessa run (programma → sale e' la strada normale, resta piena).
    tratteggiati = {k for k in arco if k[0] == "valida" or k == ("avvisi", "programma")} | arco_guardia
    tratteggiati = {k for k in tratteggiati if k in arco}
    in_rosso = {("coordina", "sale")} if doppia_strada and ("coordina", "sale") in arco else set()
    rimpalli = tratteggiati | in_rosso

    # --- il testo ---
    righe = [f"schema del sistema: {n} run, strato {strato}", "", "chi chiama chi (in quante run · volte in totale)"]
    righe.append(f"   {'utente → coordina':<28} {n:>3} su {n} · {n:>3} volte")
    ordinati = sorted((k for k in arco if k[1] in agenti), key=lambda k: (_ordine(k[0]), _ordine(k[1])))
    for k in ordinati:
        segno = "  *" if k in rimpalli else "   "
        righe.append(f"{segno}{k[0] + ' → ' + k[1]:<28} {arco[k][0]:>3} su {n} · {arco[k][1]:>3} volte")
    foglie = sorted((k for k in arco if k[1] not in agenti), key=lambda k: (_ordine(k[0]), k[1]))
    if foglie and not senza_strumenti:
        righe.append("  strumenti dei dati")
        for k in foglie:
            righe.append(f"     {k[0] + ' → ' + k[1]:<28} {arco[k][0]:>3} su {n} · {arco[k][1]:>3} volte")
    righe += ["", "rimpalli (* nell'elenco sopra)"]
    for a in sorted(due_chiamanti, key=_ordine):
        righe.append(f"  {a} chiamato da {len(due_chiamanti[a][1])} chiamanti ({', '.join(sorted(due_chiamanti[a][1], key=_ordine))}): "
                     f"{due_chiamanti[a][0]} run su {n}")
    if not due_chiamanti:
        righe.append(f"  nessun agente chiamato da piu' chiamanti nella stessa run: 0 run su {n}")
    for fonte in ("avvisi", "programma"):
        k = ("valida", fonte)
        righe.append(f"  valida richiama {fonte}: {arco[k][0] if k in arco else 0} run su {n}")
        if fonte == "avvisi":
            if strato < MINIMO_MISURE["valida_riporta"]:
                righe.append("    ...e la risposta riporta l'avviso sulla sala B: serve lo strato 3")
            else:
                riportano = sum(any(riporta_avviso(attr(x, "gen_ai.tool.call.result", "")) for x in archi(r["span"], ("avvisi",), da="valida"))
                                for r in regs)
                righe.append(f"    ...e la risposta riporta l'avviso sulla sala B: {riportano} run su {n}")
    k = ("avvisi", "programma")
    righe.append(f"  avvisi chiede a programma (dialogo): {arco[k][0] if k in arco else 0} run su {n}")
    righe.append(f"  guardia dei cicli scattata: {sum(bool(g) for _, g in guardie)} run su {n} · {sum(len(g) for _, g in guardie)} volte")

    # --- Mermaid ---
    def etichetta(k):
        run, volte = arco[k]
        media = round(volte / run, 1)
        return f"{run}/{n}" + (f" ×{media:.1f}" if media > 1 else "")
    mm = ["flowchart LR", "  %% legenda: ogni arco e' «in quante run su quante» (×N = volte per run, in media);",
          "  %% tratteggiato = chi controlla o chiede a una fonte fuori dal giro di coordina (valida che richiama, avvisi che "
          "chiede a programma, arco respinto dalla guardia); rosso = coordina → sale quando sale e' chiamato anche da programma"]
    nodi = sorted(agenti, key=_ordine)
    mm.append("  utente([utente])")
    mm += [f"  {a}[{a}]" for a in nodi]
    mm.append(f"  utente -->|{n}/{n}| coordina")
    tratti, rossi = [], []
    for i, k in enumerate(ordinati, start=1):
        mm.append(f"  {k[0]} {'-.->' if k in tratteggiati else '-->'}|{etichetta(k)}| {k[1]}")
        if k in tratteggiati:
            tratti.append(i)
        if k in in_rosso:
            rossi.append(i)
    if tratti:
        mm.append(f"  linkStyle {','.join(map(str, tratti))} stroke:#7f8c8d,stroke-width:2px,color:#7f8c8d")
    if rossi:
        mm.append(f"  linkStyle {','.join(map(str, rossi))} stroke:#c0392b,stroke-width:3px,color:#c0392b")
    return "\n".join(righe), "\n".join(mm)


def mostra_schema(cartella: Path, modo: str | None = None, senza_strumenti: bool = False):
    if not cartella.is_dir():
        raise SystemExit(f"{cartella}: non e' una cartella di registrazioni")
    regs = [json.loads(f.read_text()) for f in sorted(cartella.glob("*.json"))]
    if not regs:
        raise SystemExit(f"{cartella}: nessuna registrazione")
    if min(r["strato"] for r in regs) < 2:
        print("lo schema delle chiamate serve lo strato 2: sotto non ci sono gli span degli agenti")
        return
    regs = [r for r in regs if modo is None or r["modo"] == modo]
    if not regs:
        print(f"nessuna registrazione in modo {modo}")
        return
    testo, mermaid = schema(regs, senza_strumenti)
    print(testo)
    print("\n```mermaid\n" + mermaid + "\n```")


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
            r = re.sub(rf"\s+#\s*s{n}\b.*$", "", testo[i]).replace(f"tracer({n}).", "tracer.").replace(", **prova)", ")")
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
    p.add_argument("--correzione", action="store_true", help="coordina chiede ad avvisi la sala della sessione")
    p.add_argument("--correzione-completa", action="store_true", help="...e leggi_avvisi restituisce solo gli avvisi di quella sala")
    p.add_argument("--correzione-dialogo", action="store_true", help="avvisi puo' chiedere a programma giorno, ora e sala (alternativa alle altre due)")
    p.add_argument("--maschera", action="store_true", help="solo con --strato 5: l'email non esce dagli span")
    p.add_argument("--produzione", action="store_true", help="dallo strato 2: il riassunto della richiesta sulla radice")
    p.add_argument("--otlp", metavar="URL", help="esporta gli span via OTLP HTTP (implica --produzione)")
    p.add_argument("--banco", type=int, default=0)
    p.add_argument("--replay")
    p.add_argument("--riepilogo", action="store_true")
    p.add_argument("--misure", type=int, metavar="STRATO", help="le misure della giornata piena e della tranquilla in uno strato")
    p.add_argument("--schema", metavar="CARTELLA", help="il grafo delle chiamate fra agenti sulle registrazioni (strato 2+), in testo e Mermaid")
    p.add_argument("--modo", choices=("guasto", "sana"), help="con --schema: solo le run di quel modo")
    p.add_argument("--senza-strumenti", action="store_true", help="con --schema: nascondi gli strumenti dei dati (leggi_*)")
    p.add_argument("--righe", action="store_true")
    p.add_argument("--codice", type=int, choices=range(6), metavar="STRATO", help="le righe di uno strato, pulite per le slide")
    a = p.parse_args()
    if a.schema:
        mostra_schema(Path(a.schema), a.modo, a.senza_strumenti)
    elif a.righe:
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
        STRATO, MASCHERA = a.strato, a.maschera
        CORREZIONE = 3 if a.correzione_dialogo else 2 if a.correzione_completa else 1 if a.correzione else 0
        a.guasto = a.guasto or CORREZIONE > 0  # la correzione ha senso solo nella giornata piena
        coda = ["", "-correzione", "-correzione-completa", "-correzione-dialogo"][CORREZIONE] + ("-maschera" if MASCHERA else "") + ("-produzione" if PRODUZIONE else "")
        cartella = QUI / "registrazioni" / f"strato-{a.strato}{coda}"
        if a.banco:
            concludi_banco(a.banco, *esegui_banco(a.banco, a.guasto, cartella))
        else:
            mostra(esegui(a.guasto, cartella))
