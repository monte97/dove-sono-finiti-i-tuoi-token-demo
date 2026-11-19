"""Una run: esegue, misura il tempo, scrive la registrazione."""
import datetime as dt
import json
import sys
import threading
import time
import uuid
from pathlib import Path

from .agenti.ciclo import agente
from .agenti.prompt import istruzioni_coordina, versione, versione_prompt
from .analisi.misure import banco
from .evento.dati import DOMANDA
from .impostazioni import NOMI_CORREZIONE, attuali
from .modello import MODEL
from .osservabilita import log as osservabilita_log
from .osservabilita import metriche, tracce
from .osservabilita.client import cliente
from .osservabilita.log import LOG, Righe
from .osservabilita.metriche import leggi_metriche
from .osservabilita.tracce import tracer
from .registrazioni import in_dict, log_in_dict


def esegui(guasto: bool, cartella: Path, client=None) -> dict:
    tracce.memoria.clear()
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
            span.set_attributes({"richiesta.correzione": NOMI_CORREZIONE[attuali().correzione],  # s2
                                 "richiesta.versione_prompt": versione_prompt()})  # s2
            if attuali().produzione:  # per filtrare le run del banco nel cruscotto, come fa strati cruscotto invia nel replay
                span.set_attributes({"banco.cartella": cartella.name, "banco.modo": "guasto" if guasto else "sana"})
            # coordina decide chi chiamare, in che ordine e cosa passare
            risposta = agente(client, "coordina", istruzioni_coordina(), DOMANDA, stato, ["programma", "sale", "avvisi", "valida"])
            if attuali().strato >= 1:  # s1  a fine richiesta, un valore per agente; dallo strato 2 porta la trace come exemplar
                for nome, n in stato["per_agente"].items():  # s1
                    metriche.TOKEN_AGENTE.record(n, {"gen_ai.agent.name": nome})  # s1
    finally:
        LOG.removeHandler(righe)
    secondi = time.monotonic() - inizio  # s0
    ora = dt.datetime.now()
    u = stato["fattura"]
    reg = {"strato": attuali().strato, "correzione": attuali().correzione, "maschera": attuali().maschera, "registrata": ora.isoformat(timespec="seconds"),
           "modo": "guasto" if guasto else "sana", "versione": versione(), "modello": MODEL, "domanda": DOMANDA, "risposta": risposta,
           "log": f"{ora:%H:%M:%S} INFO POST /chiedi 200 in {secondi:.1f} s",  # s0
           "fattura": {"chiamate": len(u), "in": sum(x.input_tokens for x in u),  # s0
                       "cache": sum(x.cache_read_input_tokens or 0 for x in u),  # s0
                       "out": sum(x.output_tokens for x in u)},  # s0
           "secondi": secondi, "span": [in_dict(s) for s in tracce.memoria.get_finished_spans()],
           "log_otel": [log_in_dict(r) for r in osservabilita_log.memoria_log.get_finished_logs()],
           "richiesta": stato["richiesta"], "righe": righe.righe, "metriche": leggi_metriche()}
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / f"{ora:%Y%m%d-%H%M%S}-{reg['modo']}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1))
    return reg


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
