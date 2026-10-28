"""Rimanda le registrazioni a Tempo via OTLP, con id nuovi e orari spostati ad adesso, per il cruscotto.

Uso: python tempo.py [--otlp URL] CARTELLA ...
"""
import argparse
import json
import random
import time
from pathlib import Path

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanContext, Status, StatusCode, TraceFlags

import segnali as sg

RISORSA = Resource.create({"service.name": "osservare-a-strati"})


def in_otlp(r: dict, cartella: str, adesso: float) -> list[ReadableSpan]:
    """Gli span di una registrazione come se fossero appena finiti. La radice della richiesta (invoke_workflow)
    prende il riassunto, se non lo ha gia', e i metadati del banco; sotto lo strato 2 una radice non c'e'
    e i metadati vanno su ogni trace (D22: allo strato 1 una domanda sono piu' trace scollegate)."""
    span = r["span"]
    sposta = adesso - max(x["fine"] for x in span)
    tracce = {t: random.getrandbits(128) for t in {x["trace"] for x in span}}
    ids = {x["id"]: random.getrandbits(64) for x in span}
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


if __name__ == "__main__":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--otlp", default="http://localhost:4418/v1/traces")
    p.add_argument("cartelle", nargs="+", type=Path)
    a = p.parse_args()
    esporta = OTLPSpanExporter(endpoint=a.otlp)
    for cartella in a.cartelle:
        for f in sorted(cartella.glob("*.json")):
            esito = esporta.export(in_otlp(json.loads(f.read_text()), cartella.name, time.time()))
            print(cartella.name, f.name, esito.name)
            time.sleep(0.1)
