"""Le metriche dei token: i due contatori per chiamata e l'istogramma per agente."""
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader

from ..impostazioni import attuali
from . import tracce

# Le metriche (strato 1): un provider per processo. La memoria legge in delta, quindi a ogni run solo il nuovo.
memoria_metriche = InMemoryMetricReader(preferred_temporality={Counter: AggregationTemporality.DELTA,
                                                               Histogram: AggregationTemporality.DELTA})
provider = None
TOKEN_IN = TOKEN_OUT = TOKEN_AGENTE = None
# I confini dell'istogramma: avvisi in una richiesta spende 17 mila token per volta che lavora (banco del 5/11),
# quindi una, due o tre volte cadono in tre secchi diversi.
CONFINI_TOKEN = [2_000, 5_000, 10_000, 20_000, 30_000, 40_000, 50_000, 60_000, 80_000, 100_000]


def url_metriche(url: str) -> str:
    """Dove vanno le metriche via il collector: lo stesso host degli span, path /v1/metrics."""
    return (url[:-len("/v1/traces")] if url.endswith("/v1/traces") else url.rstrip("/")) + "/v1/metrics"


def fai_metriche():
    """Il provider delle metriche e i tre strumenti dei token: due contatori per chiamata con i nomi delle convenzioni
    GenAI, e un istogramma con un nome mio, un valore per agente a fine richiesta. Con --otlp escono ogni 5 secondi."""
    global provider, TOKEN_IN, TOKEN_OUT, TOKEN_AGENTE
    if provider:
        return
    lettori = [memoria_metriche]
    if attuali().otlp:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        lettori.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=url_metriche(attuali().otlp)),
                                                     export_interval_millis=5000))
    provider = MeterProvider(resource=tracce.RISORSA, metric_readers=lettori)  # s1
    misura = provider.get_meter("osservare-a-strati")  # s1
    TOKEN_IN = misura.create_counter("gen_ai.client.inference.usage.input_tokens", unit="{token}")  # s1
    TOKEN_OUT = misura.create_counter("gen_ai.client.inference.usage.output_tokens", unit="{token}")  # s1
    TOKEN_AGENTE = misura.create_histogram("assistente.agente.token", unit="{token}",  # s1
                                           description="token di un agente in una richiesta",  # s1
                                           explicit_bucket_boundaries_advisory=CONFINI_TOKEN)  # s1


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
    return metriche_in_dict(memoria_metriche.get_metrics_data()) if provider else []
