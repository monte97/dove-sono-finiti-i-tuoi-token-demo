"""Rimanda le registrazioni (span, log correlati e metriche) al collector, con id nuovi e orari spostati ad adesso, per il cruscotto.

Le registrazioni del banco del 5/11 sono di prima delle righe di log per chiamata e delle metriche: righe e misure si
rifanno dagli span della stessa run (strati.chiamate_dagli_span), con le cifre di quella run.

Uso: python tempo.py [--otlp URL] CARTELLA ...
"""
import argparse
import hashlib
import json
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path

from opentelemetry._logs import LogRecord, SeverityNumber
from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import NonRecordingSpan, SpanContext, Status, StatusCode, TraceFlags, set_span_in_context

import segnali as sg
import strati
from osservare_a_strati.impostazioni import Impostazioni, imposta
from osservare_a_strati.osservabilita import metriche, tracce

# La stessa Resource delle run dal vivo (servizio e versione): su span e su log.
RISORSA = tracce.RISORSA


def versione_della_registrazione(r: dict) -> dict:
    """La versione di una registrazione: quella scritta nel campo `versione` se c'e'; altrimenti, per le registrazioni
    vecchie (il banco del 5/11), derivata dalla modalita' di correzione e dalle istruzioni di adesso. Vale perche' le
    istruzioni non sono cambiate dopo il banco: test_strati.py fissa gli hash per modalita'."""
    return r.get("versione") or strati.versione(r.get("correzione", 0))


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
    versione = versione_della_registrazione(r)
    dati_versione = {"richiesta.correzione": versione["correzione"], "richiesta.versione_prompt": versione["prompt"]}
    fuori = []
    for x in span:
        attributi = dict(x["attributi"])
        padre = per_id.get(x["padre"])
        if x is radice:
            # una registrazione dal vivo ha gia' i suoi valori: non si toccano (setdefault)
            for k, v in {**sg.riassunto(r), **dati_versione}.items():
                attributi.setdefault(k, v)
            attributi.update(banco)
        elif radice is None and padre is None:  # sotto lo strato 2 niente radice: versione e banco su ogni trace
            attributi.update({**dati_versione, **banco})
        fuori.append(ReadableSpan(
            name=x["nome"], context=contesto(x), parent=contesto(padre) if padre else None, resource=RISORSA,
            attributes=attributi, status=Status(StatusCode.ERROR) if x["errore"] else Status(StatusCode.UNSET),
            start_time=round((x["inizio"] + sposta) * 1e9), end_time=round((x["fine"] + sposta) * 1e9)))
    return fuori


def righe_ricostruite(r: dict) -> list[dict]:
    """Le righe di log per chiamata, come log correlati. Se la registrazione le ha gia' (dallo strato 3, in log_otel con
    i loro campi) non serve niente; altrimenti si ricostruiscono dagli span, con lo stesso testo e gli stessi campi della
    riga dal vivo, dentro l'invoke_agent dell'agente che ha chiamato il modello."""
    if any("campi" in l for l in r.get("log_otel", [])):
        return []
    # l'id della richiesta: quello della run se c'e'; altrimenti stabile, dalla trace originale, cosi' a ogni rinvio e'
    # lo stesso e una slide o uno screenshot restano confrontabili
    richiesta = r.get("richiesta") or hashlib.sha1(r["span"][0]["trace"].encode()).hexdigest()[:8]
    return [{"trace": ch["trace"], "span": ch["span"], "livello": "INFO", "testo": "chiamata al modello",
             "tempo": ch["fine"], "campi": {"richiesta": richiesta, **ch["campi"]}}
            for ch in strati.chiamate_dagli_span(r["span"])]


def contesto_di(mappa: dict, traccia: str, span_id: str):
    """Il contesto di uno span rimappato, per gli exemplar: la misura porta la trace che il cruscotto apre."""
    return set_span_in_context(NonRecordingSpan(SpanContext(mappa["tracce"][traccia], mappa["ids"][span_id], False,
                                                            TraceFlags(TraceFlags.SAMPLED))))


def misura(r: dict, mappa: dict, cartella: str):
    """Le metriche della run come le misura lo strato 1: i contatori per chiamata dentro l'invoke_agent di chi chiama,
    l'istogramma per agente dentro la radice. Gli strumenti sono quelli di strati.fai_metriche."""
    banco, per_agente = {"banco.cartella": cartella, "banco.modo": r["modo"]}, {}
    for ch in strati.chiamate_dagli_span(r["span"]):
        k = ch["campi"]
        attributi = {"gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic", "gen_ai.token.modality": "text",
                     "gen_ai.request.model": strati.MODEL, "gen_ai.response.model": k["gen_ai.response.model"],
                     "gen_ai.agent.name": ch["agente"], **banco}
        ingresso = k["gen_ai.usage.input_tokens"]  # con la cache dentro, come nelle convenzioni
        contesto = contesto_di(mappa, ch["trace"], ch["span"])
        metriche.TOKEN_IN.add(ingresso, attributi, context=contesto)
        metriche.TOKEN_OUT.add(k["gen_ai.usage.output_tokens"], attributi, context=contesto)
        per_agente[ch["agente"]] = per_agente.get(ch["agente"], 0) + ingresso + k["gen_ai.usage.output_tokens"]
    radice = next((x for x in r["span"] if x["nome"].startswith("invoke_workflow")), None)
    contesto = contesto_di(mappa, radice["trace"], radice["id"]) if radice else None
    for agente, n in per_agente.items():
        metriche.TOKEN_AGENTE.record(n, {"gen_ai.agent.name": agente, **banco}, context=contesto)
    return len(per_agente)


def log_in_otlp(r: dict, mappa: dict, aggiunte: list[dict] = ()) -> list[ReadableLogRecord]:
    """I log correlati della registrazione, con gli id rimappati come quelli degli span. Ogni record porta il suo
    orario (`tempo`, spostato come quello degli span); se manca (registrazioni senza il campo) prende l'inizio
    spostato del suo span, piu' un millisecondo per posto, per tenere l'ordine. In ogni caso resta dentro lo span a
    cui appartiene. Un log il cui span non e' nella registrazione si salta: non avrebbe una trace a cui appartenere."""
    per_id = {x["id"]: x for x in r["span"]}
    posto, fuori = {}, []
    for l in list(r.get("log_otel", [])) + list(aggiunte):
        x = per_id.get(l["span"])
        if x is None:
            continue
        n = posto[l["span"]] = posto.get(l["span"], -1) + 1
        da, a = (x["inizio"] + mappa["sposta"]) * 1e9, (x["fine"] + mappa["sposta"]) * 1e9
        grezzo = (l["tempo"] + mappa["sposta"]) * 1e9 if "tempo" in l else da + n * 1_000_000
        ora = round(min(max(grezzo, da), a))
        numero = {"WARNING": SeverityNumber.WARN, "ERROR": SeverityNumber.ERROR, "DEBUG": SeverityNumber.DEBUG}.get(
            l["livello"], SeverityNumber.INFO)
        fuori.append(ReadableLogRecord(
            LogRecord(timestamp=ora, observed_timestamp=ora, trace_id=mappa["tracce"][x["trace"]],
                      span_id=mappa["ids"][x["id"]], trace_flags=TraceFlags(TraceFlags.SAMPLED),
                      severity_text=l["livello"], severity_number=numero, body=l["testo"],
                      attributes=l.get("campi") or None),
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

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--otlp", default="http://localhost:4418/v1/traces")
    p.add_argument("--tempo", default="http://localhost:3210", help="per controllare cosa c'e' gia'")
    p.add_argument("--ancora", action="store_true", help="rimanda anche se la cartella e' gia' in Tempo nell'ultima ora")
    p.add_argument("cartelle", nargs="+", type=Path)
    a = p.parse_args()
    esporta, esporta_log = OTLPSpanExporter(endpoint=a.otlp), OTLPLogExporter(endpoint=strati.url_log(a.otlp))
    imposta(Impostazioni(strato=5, otlp=a.otlp))  # gli strumenti delle metriche, con l'esportazione al collector
    metriche.fai_metriche()
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
            if logs := log_in_otlp(r, mappa, righe_ricostruite(r)):
                esito_log = esporta_log.export(logs)
                print(cartella.name, f.name, "log", len(logs), esito_log.name)
            agenti = misura(r, mappa, cartella.name)
            metriche.provider.force_flush()  # una richiesta per esportazione: gli exemplar sono suoi
            print(cartella.name, f.name, esito.name, "metriche", agenti, "agenti")
            time.sleep(0.1)
