"""Rimanda le registrazioni (span e log correlati) al collector via OTLP, con id nuovi e orari spostati ad adesso, per il cruscotto.

Uso: python tempo.py [--otlp URL] CARTELLA ...
"""
import argparse
import json
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path

from opentelemetry._logs import LogRecord, SeverityNumber
from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import SpanContext, Status, StatusCode, TraceFlags

import segnali as sg

RISORSA = Resource.create({"service.name": "osservare-a-strati"})


def rimappa(r: dict, adesso: float) -> dict:
    """Id nuovi per le trace e per gli span, e di quanto spostare gli orari perche' la richiesta finisca ad adesso.
    Gli span e i log della stessa registrazione usano la stessa mappa: cosi' il trace id dei log trova la trace."""
    span = r["span"]
    return {"sposta": adesso - max(x["fine"] for x in span),
            "tracce": {t: random.getrandbits(128) for t in {x["trace"] for x in span}},
            "ids": {x["id"]: random.getrandbits(64) for x in span}}


def in_otlp(r: dict, cartella: str, adesso: float, mappa: dict | None = None) -> list[ReadableSpan]:
    """Gli span di una registrazione come se fossero appena finiti. La radice della richiesta (invoke_workflow)
    prende il riassunto, se non lo ha gia', e i metadati del banco; sotto lo strato 2 una radice non c'e'
    e i metadati vanno su ogni trace (D22: allo strato 1 una domanda sono piu' trace scollegate)."""
    span = r["span"]
    if not span:  # strato 0: un log e una fattura, nessuno span
        return []
    mappa = mappa or rimappa(r, adesso)
    sposta, tracce, ids = mappa["sposta"], mappa["tracce"], mappa["ids"]
    contesto = lambda x: SpanContext(tracce[x["trace"]], ids[x["id"]], False, TraceFlags(TraceFlags.SAMPLED))
    per_id = {x["id"]: x for x in span}
    radice = next((x for x in span if x["nome"].startswith("invoke_workflow")), None)
    banco = {"banco.cartella": cartella, "banco.modo": r["modo"]}
    fuori = []
    for x in span:
        attributi = dict(x["attributi"])
        padre = per_id.get(x["padre"])
        if x is radice:
            if not any(k.startswith("richiesta.") for k in attributi):
                attributi.update(sg.riassunto(r))
            attributi.update(banco)
        elif radice is None and padre is None:
            attributi.update(banco)
        fuori.append(ReadableSpan(
            name=x["nome"], context=contesto(x), parent=contesto(padre) if padre else None, resource=RISORSA,
            attributes=attributi, status=Status(StatusCode.ERROR) if x["errore"] else Status(StatusCode.UNSET),
            start_time=round((x["inizio"] + sposta) * 1e9), end_time=round((x["fine"] + sposta) * 1e9)))
    return fuori


def log_in_otlp(r: dict, mappa: dict) -> list[ReadableLogRecord]:
    """I log correlati della registrazione, con gli id rimappati come quelli degli span. I record non hanno un orario
    proprio: ognuno prende l'inizio (spostato) del suo span, piu' un millisecondo per posto, per tenere l'ordine.
    Un log il cui span non e' nella registrazione si salta: non avrebbe una trace a cui appartenere."""
    per_id = {x["id"]: x for x in r["span"]}
    posto, fuori = {}, []
    for l in r.get("log_otel", []):
        x = per_id.get(l["span"])
        if x is None:
            continue
        n = posto[l["span"]] = posto.get(l["span"], -1) + 1
        ora = round((x["inizio"] + mappa["sposta"]) * 1e9) + n * 1_000_000
        numero = {"WARNING": SeverityNumber.WARN, "ERROR": SeverityNumber.ERROR, "DEBUG": SeverityNumber.DEBUG}.get(
            l["livello"], SeverityNumber.INFO)
        fuori.append(ReadableLogRecord(
            LogRecord(timestamp=ora, observed_timestamp=ora, trace_id=mappa["tracce"][x["trace"]],
                      span_id=mappa["ids"][x["id"]], trace_flags=TraceFlags(TraceFlags.SAMPLED),
                      severity_text=l["livello"], severity_number=numero, body=l["testo"]),
            resource=RISORSA, instrumentation_scope=InstrumentationScope("osservare-a-strati")))
    return fuori


def gia_in_tempo(cartella: str, cerca) -> bool:
    """Una cartella rimandata due volte nella stessa ora raddoppia ogni conteggio del cruscotto."""
    return cerca(f'{{ span.banco.cartella = "{cartella}" }}') > 0


def cerca_in_tempo(tempo: str):
    def cerca(q: str) -> int:
        fine = int(time.time())
        parametri = urllib.parse.urlencode({"q": q, "start": fine - 3600, "end": fine, "limit": 1})
        with urllib.request.urlopen(f"{tempo}/api/search?{parametri}", timeout=30) as r:
            return len(json.load(r).get("traces", []))
    return cerca


if __name__ == "__main__":
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    import strati

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--otlp", default="http://localhost:4418/v1/traces")
    p.add_argument("--tempo", default="http://localhost:3210", help="per controllare cosa c'e' gia'")
    p.add_argument("--ancora", action="store_true", help="rimanda anche se la cartella e' gia' in Tempo nell'ultima ora")
    p.add_argument("cartelle", nargs="+", type=Path)
    a = p.parse_args()
    esporta, esporta_log = OTLPSpanExporter(endpoint=a.otlp), OTLPLogExporter(endpoint=strati.url_log(a.otlp))
    cerca = cerca_in_tempo(a.tempo)
    for cartella in a.cartelle:
        if not a.ancora and gia_in_tempo(cartella.name, cerca):
            raise SystemExit(f"{cartella.name} e' gia' in Tempo nell'ultima ora: rimandarla raddoppia i conteggi "
                             "(--ancora per farlo comunque, oppure docker compose down -v e di nuovo up)")
        for f in sorted(cartella.glob("*.json")):
            r = json.loads(f.read_text())
            if not r["span"]:
                continue
            mappa = rimappa(r, time.time())
            esito = esporta.export(in_otlp(r, cartella.name, time.time(), mappa))
            if logs := log_in_otlp(r, mappa):
                esito_log = esporta_log.export(logs)
                print(cartella.name, f.name, "log", len(logs), esito_log.name)
            print(cartella.name, f.name, esito.name)
            time.sleep(0.1)
