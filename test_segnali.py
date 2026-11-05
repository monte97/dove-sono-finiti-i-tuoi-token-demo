"""Controlli dei segnali per la produzione, su run finte (a mano e dal server finto di test_strati). Uso: python test_segnali.py"""
import contextlib
import io
import threading

import segnali as sg
import strati as s
import test_strati as ts
from opentelemetry.sdk.trace import TracerProvider


def sp(nome, id, padre=None, errore=False, inizio=0.0, durata=1.0, attributi=None):
    return {"nome": nome, "id": id, "padre": padre, "trace": "t", "inizio": inizio, "fine": inizio + durata,
            "errore": errore, "attributi": attributi or {}}


def arco(id, padre, chi, verso, inizio, durata=1.0, **altri):
    return sp(f"execute_tool {verso}", id, padre, inizio=inizio, durata=durata, attributi={
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": verso, "gen_ai.agent.name": chi,
        "gen_ai.transfer.target.name": verso, **altri})


def agente(id, padre, nome, inizio, durata=1.0):
    return sp(f"invoke_agent {nome}", id, padre, inizio=inizio, durata=durata,
              attributi={"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": nome})


def chat(id, padre, inizio, entrata, cache, uscita):
    return sp("anthropic.messages.create", id, padre, inizio=inizio, attributi={
        "gen_ai.usage.input_tokens": entrata, "gen_ai.usage.cache_read.input_tokens": cache,
        "gen_ai.usage.output_tokens": uscita})


def strumento(id, padre, nome, inizio, errore=False, **altri):
    return sp(f"execute_tool {nome}", id, padre, errore=errore, inizio=inizio, attributi={
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": nome, **altri})


TOKEN = {"programma": (1000, 50), "sale": (1000, 50), "avvisi": (8000, 100)}
STRUMENTO = {"programma": ("leggi_programma", {}), "sale": ("leggi_sale", {}),
             "avvisi": ("leggi_avvisi", {"avvisi.pagine": 40, "gen_ai.tool.call.result": "- " + s.AVVISO_CHIAVE})}
RISPOSTA = {"programma": "Oggi alle 15:00, sala B.", "sale": "Sala B, primo piano.", "avvisi": "Nessun avviso sul workshop."}


def ramo(verso, inizio, durata, **risultato):
    """Un arco di coordina verso un agente, con l'agente, la sua chiamata al modello e il suo strumento."""
    nome, attr_tool = STRUMENTO[verso]
    ing, usc = TOKEN[verso]
    return [arco(f"a-{verso}", "co", "coordina", verso, inizio, durata, **{"gen_ai.tool.call.result": RISPOSTA[verso], **risultato}),
            agente(f"g-{verso}", f"a-{verso}", verso, inizio, durata),
            chat(f"m-{verso}", f"g-{verso}", inizio, ing, 0, usc),
            strumento(f"l-{verso}", f"g-{verso}", nome, inizio, **attr_tool)]


def run(partenze=(("programma", 3.0), ("sale", 3.01), ("avvisi", 3.02)), strato=5, **risultato_avvisi):
    """coordina chiama i tre rami (insieme, se le partenze si sovrappongono), poi valida, che approva."""
    rami = [x for verso, inizio in partenze for x in ramo(verso, inizio, 3.0, **(risultato_avvisi if verso == "avvisi" else {}))]
    va = max(x["fine"] for x in rami if x["nome"].startswith("execute_tool ")) + 0.5  # valida dopo i rami
    return {"strato": strato, "modo": "guasto", "risposta": "Oggi alle 15:00, sala B.", "secondi": 12.0,
            "fattura": {"chiamate": 6, "in": TOTALE_IN, "cache": 1000, "out": TOTALE_OUT}, "span": [
        sp("invoke_workflow assistente", "w", durata=12, attributi={"gen_ai.operation.name": "invoke_workflow"}),
        agente("co", "w", "coordina", 1, 11),
        chat("m1", "co", 2, 1000, 0, 50),
        *rami,
        arco("a-valida", "co", "coordina", "valida", va, **{
            "gen_ai.tool.call.arguments": '{"domanda": "ciao giulia.rossi@example.com"}',
            "gen_ai.tool.call.result": "Il workshop è alle 15:00. Verificato."}),
        agente("g-valida", "a-valida", "valida", va),
        chat("m-valida", "g-valida", va + 1, 2000, 1000, 100),
    ]}


FORMA = "codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma),sale(leggi_sale)} coordina>valida"
SENZA_STRUMENTI = "codice>coordina coordina>{avvisi,programma,sale} coordina>valida"
TOTALE_IN, TOTALE_OUT = 1000 + 1000 + 1000 + 8000 + 2000, 50 + 50 + 50 + 100 + 100
TOTALE = 1000 + 50 + 1000 + 50 + 8000 + 100 + 1000 + 50 + 2000 + 100


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


def test_cruscotto():
    c = sg.cruscotto([run(), run(), run((("avvisi", 3.0), ("sale", 3.01), ("programma", 3.02)))])
    assert c["n"] == 3 and c["approva"] == (3, 3) and c["forme"] == {FORMA: 3}  # una forma sola, non due
    assert c["costo"]["mediana"] == c["costo"]["p95"]
    assert abs(c["quota_avvisi"]["mediana"] - 8100 / TOTALE) < 1e-12
    assert c["pagine"] == {"mediana": 40, "massimo": 40}
    assert sg.cruscotto([run(), {**run(), "strato": 3}])["pagine"] is None  # strato misto


def test_p95_e_valida_mai_chiamata():
    senza_valida = {**run(), "span": [x for x in run()["span"] if "valida" not in x["nome"]]}
    assert sg.cruscotto([senza_valida])["approva"] == (0, 0)  # misurabile, e zero: non None
    costi = [0.001 * i for i in range(1, 31)]
    assert sg.p95(costi) == sorted(costi)[round(29 * 0.95)]
    assert sg.p95([0.5]) == 0.5


def test_riassunto_della_run():
    assert sg.riassunto(run()) == {"richiesta.forma": FORMA, "richiesta.pagine_avvisi": 40,
                                   "richiesta.costo_microusd": round(sg.segnali(run())["costo"] * 1e6),
                                   "richiesta.quota_avvisi_pct": round(8100 / TOTALE * 100)}
    assert set(sg.riassunto({**run(), "strato": 1})) == {"richiesta.costo_microusd"}
    assert "richiesta.pagine_avvisi" not in sg.riassunto({**run(), "strato": 3})


def test_misure_di_una_run_finta():
    m = s.misura(run())
    assert m["grafo"] == FORMA and m["stesso_giro"] is True and m["avvisi_dopo_sala"] is False
    assert m["pagine_avvisi"] == 40 and m["tool_ha_avviso"] is True and m["avvisi_riporta"] is False
    assert m["valida_chiamate"] == 1 and m["valida_approva"] == 1 and m["email_a_valida"] is True
    assert m["token_agente"] == {"coordina": 1050, "programma": 1050, "sale": 1050, "avvisi": 8100, "valida": 2100}
    assert abs(m["quota_avvisi"] - 8100 / TOTALE) < 1e-12
    dopo = s.misura(run((("programma", 3.0), ("sale", 3.01), ("avvisi", 6.5))))
    assert dopo["stesso_giro"] is False and dopo["avvisi_dopo_sala"] is True
    assert s.misura(run(**{"gen_ai.tool.call.result": "Sala B chiusa dalle 15:00: le sessioni anticipano di un'ora."}))["avvisi_riporta"]
    assert s.misura({**run(), "strato": 2})["pagine_avvisi"] is None and s.misura({**run(), "strato": 2})["tool_ha_avviso"] is None
    assert s.misura({**run(), "strato": 2})["stesso_giro"] is True


def test_avvisi_riporta_solo_con_sala_b_e_causa():
    assert s.riporta_avviso("Sala B: chiusa dalle 15:00 per manutenzione. Le sessioni iniziano un'ora prima.")
    assert s.riporta_avviso("In sala B le sessioni del pomeriggio sono anticipate.")
    assert s.riporta_avviso("La sala b è chiusa.")
    assert not s.riporta_avviso("Sala B: il proiettore è stato sostituito.")  # la sala, ma niente chiusura
    assert not s.riporta_avviso("Manutenzione dell'ascensore, sala A chiusa.")  # la causa, ma non la sala B
    assert not s.riporta_avviso("Nessun avviso sul workshop.")


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


def test_stampa_dice_cosa_manca():
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        sg.stampa("prova · guasto", sg.cruscotto([run(), run()]))
    testo = fuori.getvalue()
    assert "95° percentile" in testo and "mediana 40 · massimo 40" in testo and "1 (la più frequente in 2 run)" in testo
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        sg.stampa("strato-1 · guasto", sg.cruscotto([{**run(), "strato": 1}]))
    assert fuori.getvalue().count("serve lo strato") == 4 and "serve lo strato 4" in fuori.getvalue()


def test_coerenza_fra_segnali_e_misura_sul_server_finto():
    for strato in (2, 3, 4, 5):
        reg, _ = ts.corri(strato)
        g, m = sg.segnali(reg), s.misura(reg)
        assert g["forma"] == m["grafo"] and g["pagine"] == m["pagine_avvisi"] and g["quota_avvisi"] == m["quota_avvisi"]
        assert (g["verdetti"] is None) == (m["valida_chiamate"] is None)
        if strato >= 3:
            assert sum(g["verdetti"]) == m["valida_approva"] and len(g["verdetti"]) == m["valida_chiamate"]
        assert abs(g["costo"] - s.costo(reg["fattura"]["in"], reg["fattura"]["cache"], reg["fattura"]["out"])) < 1e-9
    assert m["grafo"] == FORMA and m["pagine_avvisi"] == 40 and m["stesso_giro"] and not m["avvisi_dopo_sala"]
    assert m["tool_ha_avviso"] and not m["avvisi_riporta"]  # lo sbaglio che la demo osserva
    reg, _ = ts.corri(5, guasto=False)
    m = s.misura(reg)
    assert m["pagine_avvisi"] == 3 and not m["tool_ha_avviso"] and sg.segnali(reg)["pagine"] == 3


def test_in_otlp():
    import tempo
    reg = run()
    spans = tempo.in_otlp(reg, "strato-5", adesso=2_000_000_000.0)
    assert len(spans) == len(reg["span"]) and len({x.context.trace_id for x in spans}) == 1
    radice = next(x for x in spans if x.parent is None)
    assert radice.attributes["banco.cartella"] == "strato-5" and radice.attributes["banco.modo"] == "guasto"
    assert radice.attributes["richiesta.forma"] == FORMA and radice.attributes["richiesta.pagine_avvisi"] == 40
    assert max(x.end_time for x in spans) == 2_000_000_000 * 10**9
    ids = {x.context.span_id for x in spans}
    assert all(x.parent.span_id in ids for x in spans if x.parent)
    assert tempo.in_otlp({**reg, "span": [], "strato": 0}, "strato-0", adesso=2_000_000_000.0) == []
    assert tempo.gia_in_tempo("strato-5", cerca=lambda q: 30 if '"strato-5"' in q else 0)
    assert not tempo.gia_in_tempo("strato-5-correzione", cerca=lambda q: 0)


if __name__ == "__main__":
    for nome, prova in list(globals().items()):
        if nome.startswith("test_"):
            prova()
            print("ok", nome)
