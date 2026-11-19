"""Test di segnali. Nati da test_strati.py e test_segnali.py, divisi per argomento."""
import threading

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from server_finto import *

from osservare_a_strati import modello
from osservare_a_strati.agenti import prompt as prompt_mod
from osservare_a_strati.analisi import segnali as segnali_mod
from osservare_a_strati.analisi import span as span_mod
from osservare_a_strati.impostazioni import con
from osservare_a_strati.osservabilita import riassunto as riassunto_mod


def test_forma_non_dipende_dall_ordine_dei_rami_paralleli():
    a = run((("programma", 3.0), ("sale", 3.01), ("avvisi", 3.02)))
    b = run((("avvisi", 3.0), ("sale", 3.01), ("programma", 3.02)))  # stessi rami, partiti in un altro ordine
    assert span_mod.grafo(a["span"]) == span_mod.grafo(b["span"]) and " ".join(span_mod.grafo(a["span"])) == FORMA
    assert " ".join(span_mod.grafo([x for x in a["span"] if "leggi_" not in x["nome"]])) == SENZA_STRUMENTI
    assert segnali_mod.segnali(a)["forma"] == segnali_mod.segnali(b)["forma"] == FORMA


def test_forma_distingue_chi_va_dopo():
    # avvisi parte quando programma e sale hanno finito: sono due giri, e la forma lo dice
    dopo = run((("programma", 3.0), ("sale", 3.01), ("avvisi", 6.5)))
    assert " ".join(span_mod.grafo(dopo["span"])) == (
        "codice>coordina coordina>{programma(leggi_programma),sale(leggi_sale)} coordina>avvisi(leggi_avvisi) coordina>valida")
    tutti_in_fila = run((("programma", 3.0), ("sale", 6.5), ("avvisi", 10.0)))
    assert span_mod.grafo(tutti_in_fila["span"])[1].startswith("coordina>programma(")
    assert len(span_mod.grafo(tutti_in_fila["span"])) == 5


def test_errore_in_forma():
    r = run()
    next(x for x in r["span"] if x["nome"] == "execute_tool leggi_sale")["errore"] = True
    assert "sale(leggi_sale!)" in " ".join(span_mod.grafo(r["span"]))


def test_segnali_di_una_run():
    g = segnali_mod.segnali(run())
    assert g["forma"] == FORMA and g["verdetti"] == [True] and g["pagine"] == 40
    assert abs(g["costo"] - (modello.costo(1000, 0, 50) * 3 + modello.costo(8000, 0, 100) + modello.costo(2000, 1000, 100))) < 1e-12
    assert abs(g["quota_avvisi"] - 8100 / TOTALE) < 1e-12


def test_sotto_lo_strato_minimo_non_si_misura():
    g = segnali_mod.segnali({**run(), "strato": 3})
    assert g["pagine"] is None and g["verdetti"] == [True] and g["quota_avvisi"] is not None
    g = segnali_mod.segnali({**run(), "strato": 2})  # allo strato 2 gli strumenti non hanno span: niente verdetti
    assert g["verdetti"] is None and g["forma"] is not None and g["quota_avvisi"] is not None
    g = segnali_mod.segnali({**run(), "strato": 1})
    assert g["forma"] is None and g["quota_avvisi"] is None and g["pagine"] is None and g["costo"] is not None


def test_p95_e_valida_mai_chiamata():
    senza_valida = {**run(), "span": [x for x in run()["span"] if "valida" not in x["nome"]]}
    assert segnali_mod.cruscotto([senza_valida])["approva"] == (0, 0)  # misurabile, e zero: non None
    costi = [0.001 * i for i in range(1, 31)]
    assert segnali_mod.p95(costi) == sorted(costi)[round(29 * 0.95)]
    assert segnali_mod.p95([0.5]) == 0.5


def test_riassunto_della_run():
    assert segnali_mod.riassunto(run()) == {"richiesta.forma": FORMA, "richiesta.pagine_avvisi": 40,
                                   "richiesta.costo_microusd": round(segnali_mod.segnali(run())["costo"] * 1e6),
                                   "richiesta.quota_avvisi_pct": round(8100 / TOTALE * 100),
                                   "richiesta.valida_approva": 1, "richiesta.valida_verdetti": 1}
    assert set(segnali_mod.riassunto({**run(), "strato": 1})) == {"richiesta.costo_microusd"}
    assert "richiesta.pagine_avvisi" not in segnali_mod.riassunto({**run(), "strato": 3})


def test_riassunto_sulla_radice():
    with con(produzione=True):
        reg, _ = corri(5)
    radice = next(x for x in reg["span"] if x["padre"] is None)
    atteso = segnali_mod.riassunto({**reg, "span": [x for x in reg["span"] if x is not radice]})
    assert atteso["richiesta.forma"] and atteso["richiesta.costo_microusd"] > 0
    visti = {k: v for k, v in radice["attributi"].items() if k.startswith("richiesta.")}
    assert visti.pop("richiesta.correzione") == "nessuna" and visti.pop("richiesta.versione_prompt") == prompt_mod.versione_prompt(0)
    assert visti == atteso


def test_riassunto_due_trace_insieme():
    p = riassunto_mod.RiassuntoSullaRadice(5)
    tp = TracerProvider()
    tp.add_span_processor(p)
    t = tp.get_tracer("prova")
    a, b = t.start_span("invoke_workflow a"), t.start_span("invoke_workflow b")
    with trace.use_span(a):
        t.start_span("anthropic.messages.create", attributes={"gen_ai.usage.input_tokens": 1000,
                                                             "gen_ai.usage.output_tokens": 50}).end()
    assert a.attributes["richiesta.costo_microusd"] == round(modello.costo(1000, 0, 50) * 1e6)
    assert "richiesta.costo_microusd" not in b.attributes
    a.end()
    b.end()
    assert all(not v for v in vars(p).values() if isinstance(v, dict))  # nessuno stato resta dopo le radici


def test_riassunto_sulla_radice_con_rami_concorrenti():
    p = riassunto_mod.RiassuntoSullaRadice(5)
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
    assert radice.attributes["richiesta.costo_microusd"] == round(400 * modello.costo(1000, 0, 50) * 1e6)
    radice.end()
    assert p.radici == {} and p.chiusi == {}
