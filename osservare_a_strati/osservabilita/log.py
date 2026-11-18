"""I log: la riga per chiamata e il collegamento a OpenTelemetry."""
import logging

from opentelemetry.instrumentation.logging.handler import LoggingHandler  # s3
from opentelemetry.sdk._logs import LoggerProvider  # s3
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor  # s3

from ..impostazioni import attuali
from . import tracce

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
    """Dove vanno i log via il collector: lo stesso host degli span, path /v1/logs."""
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
    if attuali().strato < 3:
        return
    provider = LoggerProvider(resource=tracce.RISORSA)  # s3
    _provider_log = provider
    provider.add_log_record_processor(SimpleLogRecordProcessor(memoria_log))  # s3
    if attuali().otlp:
        provider.add_log_record_processor(processore_otlp_log(url_log(attuali().otlp)))
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
