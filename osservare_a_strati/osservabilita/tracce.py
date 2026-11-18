"""Le tracce: il provider, il tracer per strato, la maschera dell'email."""
import re

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource  # s1
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ..impostazioni import attuali

# La versione del codice e del banco: il giorno del banco (tag banco-2026-11-05). Va nella Resource di span e log,
# cosi' una run dal vivo finisce in Tempo e in Loki sotto il servizio e la versione giusti. Si cambia solo se cambia
# qualcosa che il banco non ha misurato.
VERSIONE = "2026-11-05"  # s1
RISORSA = Resource.create({"service.name": "osservare-a-strati", "service.version": VERSIONE})  # s1

EMAIL = re.compile(r"[\w.]+@[\w.]+\.\w+")


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


memoria = InMemorySpanExporter()  # s1  ponytail: in memoria; dal vivo un exporter verso un backend
_spento = trace.NoOpTracer()
_vero = None


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
    if attuali().produzione:
        from .riassunto import RiassuntoSullaRadice
        provider.add_span_processor(RiassuntoSullaRadice(attuali().strato))
    if attuali().otlp:  # anche verso il backend l'email esce solo mascherata
        provider.add_span_processor(MascheraEmail(processore_otlp(attuali().otlp)) if maschera else processore_otlp(attuali().otlp))
    _vero = provider.get_tracer("osservare-a-strati")
    return provider


fai_provider(False)  # il tracer esiste anche prima del primo client


def tracer(n: int):
    """Il tracer dello strato n: vero da quello strato in su, muto sotto. Impalcatura della demo, non strumentazione."""
    return _vero if attuali().strato >= n else _spento
