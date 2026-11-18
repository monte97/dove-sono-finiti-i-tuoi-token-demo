"""Test di segnali. Nati da test_strati.py e test_segnali.py, divisi per argomento."""
import contextlib
import io
import json
import re
import tempfile
import threading
import time
from pathlib import Path

import httpx2 as httpx
import server_finto as sf
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from server_finto import *  # noqa: F401,F403

def test_forma_non_dipende_dall_ordine_dei_rami_paralleli():
    a = run((("programma", 3.0), ("sale", 3.01), ("avvisi", 3.02)))
    b = run((("avvisi", 3.0), ("sale", 3.01), ("programma", 3.02)))  # stessi rami, partiti in un altro ordine
    assert s.grafo(a["span"]) == s.grafo(b["span"]) and " ".join(s.grafo(a["span"])) == FORMA
    assert " ".join(s.grafo([x for x in a["span"] if "leggi_" not in x["nome"]])) == SENZA_STRUMENTI
    assert sg.segnali(a)["forma"] == sg.segnali(b)["forma"] == FORMA


def test_forma_distingue_chi_va_dopo():
    # avvisi parte quando programma e sale hanno finito: sono due giri, e la forma lo dice
    dopo = run((("programma", 3.0), ("sale", 3.01), ("avvisi", 6.5)))
    assert " ".join(s.grafo(dopo["span"])) == (
        "codice>coordina coordina>{programma(leggi_programma),sale(leggi_sale)} coordina>avvisi(leggi_avvisi) coordina>valida")
    tutti_in_fila = run((("programma", 3.0), ("sale", 6.5), ("avvisi", 10.0)))
    assert s.grafo(tutti_in_fila["span"])[1].startswith("coordina>programma(")
    assert len(s.grafo(tutti_in_fila["span"])) == 5


def test_errore_in_forma():
    r = run()
    next(x for x in r["span"] if x["nome"] == "execute_tool leggi_sale")["errore"] = True
    assert "sale(leggi_sale!)" in " ".join(s.grafo(r["span"]))


def test_segnali_di_una_run():
    g = sg.segnali(run())
    assert g["forma"] == FORMA and g["verdetti"] == [True] and g["pagine"] == 40
    assert abs(g["costo"] - (s.costo(1000, 0, 50) * 3 + s.costo(8000, 0, 100) + s.costo(2000, 1000, 100))) < 1e-12
    assert abs(g["quota_avvisi"] - 8100 / TOTALE) < 1e-12


def test_sotto_lo_strato_minimo_non_si_misura():
    g = sg.segnali({**run(), "strato": 3})
    assert g["pagine"] is None and g["verdetti"] == [True] and g["quota_avvisi"] is not None
    g = sg.segnali({**run(), "strato": 2})  # allo strato 2 gli strumenti non hanno span: niente verdetti
    assert g["verdetti"] is None and g["forma"] is not None and g["quota_avvisi"] is not None
    g = sg.segnali({**run(), "strato": 1})
    assert g["forma"] is None and g["quota_avvisi"] is None and g["pagine"] is None and g["costo"] is not None


def test_p95_e_valida_mai_chiamata():
    senza_valida = {**run(), "span": [x for x in run()["span"] if "valida" not in x["nome"]]}
    assert sg.cruscotto([senza_valida])["approva"] == (0, 0)  # misurabile, e zero: non None
    costi = [0.001 * i for i in range(1, 31)]
    assert sg.p95(costi) == sorted(costi)[round(29 * 0.95)]
    assert sg.p95([0.5]) == 0.5


def test_riassunto_della_run():
    assert sg.riassunto(run()) == {"richiesta.forma": FORMA, "richiesta.pagine_avvisi": 40,
                                   "richiesta.costo_microusd": round(sg.segnali(run())["costo"] * 1e6),
                                   "richiesta.quota_avvisi_pct": round(8100 / TOTALE * 100),
                                   "richiesta.valida_approva": 1, "richiesta.valida_verdetti": 1}
    assert set(sg.riassunto({**run(), "strato": 1})) == {"richiesta.costo_microusd"}
    assert "richiesta.pagine_avvisi" not in sg.riassunto({**run(), "strato": 3})


def test_riassunto_sulla_radice():
    s.PRODUZIONE = True
    try:
        reg, _ = corri(5)
    finally:
        s.PRODUZIONE = False
    radice = next(x for x in reg["span"] if x["padre"] is None)
    atteso = sg.riassunto({**reg, "span": [x for x in reg["span"] if x is not radice]})
    assert atteso["richiesta.forma"] and atteso["richiesta.costo_microusd"] > 0
    visti = {k: v for k, v in radice["attributi"].items() if k.startswith("richiesta.")}
    assert visti.pop("richiesta.correzione") == "nessuna" and visti.pop("richiesta.versione_prompt") == s.versione_prompt(0)
    assert visti == atteso


def test_riassunto_due_trace_insieme():
    p = sg.RiassuntoSullaRadice(5)
    tp = TracerProvider()
    tp.add_span_processor(p)
    t = tp.get_tracer("prova")
    a, b = t.start_span("invoke_workflow a"), t.start_span("invoke_workflow b")
    with trace.use_span(a):
        t.start_span("anthropic.messages.create", attributes={"gen_ai.usage.input_tokens": 1000,
                                                             "gen_ai.usage.output_tokens": 50}).end()
    assert a.attributes["richiesta.costo_microusd"] == round(s.costo(1000, 0, 50) * 1e6)
    assert "richiesta.costo_microusd" not in b.attributes
    a.end()
    b.end()
    assert all(not v for v in vars(p).values() if isinstance(v, dict))  # nessuno stato resta dopo le radici


def test_riassunto_sulla_radice_con_rami_concorrenti():
    p = sg.RiassuntoSullaRadice(5)
    tp = TracerProvider()
    tp.add_span_processor(p)
    t = tp.get_tracer("prova")
    radice = t.start_span("invoke_workflow x")
    from opentelemetry import trace
    contesto = trace.set_span_in_context(radice)
    barriera = threading.Barrier(8)

    def lavora():
        barriera.wait()
        for _ in range(50):
            t.start_span("anthropic.messages.create", context=contesto, attributes={
                "gen_ai.usage.input_tokens": 1000, "gen_ai.usage.output_tokens": 50}).end()
    fili = [threading.Thread(target=lavora) for _ in range(8)]
    [f.start() for f in fili]
    [f.join() for f in fili]
    assert radice.attributes["richiesta.costo_microusd"] == round(400 * s.costo(1000, 0, 50) * 1e6)
    radice.end()
    assert p.radici == {} and p.chiusi == {}
