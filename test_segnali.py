"""Controlli dei segnali per la produzione, su run finte e sulle registrazioni. Uso: python test_segnali.py"""
import contextlib
import io
import json
import statistics
from pathlib import Path

import segnali as sg
import strati as s


def sp(nome, id, padre=None, errore=False, inizio=0.0, attributi=None):
    return {"nome": nome, "id": id, "padre": padre, "trace": "t", "inizio": inizio, "fine": inizio + 1,
            "errore": errore, "attributi": attributi or {}}


def arco(id, padre, chi, verso, inizio, **altri):
    return sp(f"execute_tool {verso}", id, padre, inizio=inizio, attributi={
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": verso, "gen_ai.agent.name": chi,
        "gen_ai.transfer.target.name": verso, **altri})


def agente(id, padre, nome, inizio):
    return sp(f"invoke_agent {nome}", id, padre, inizio=inizio,
              attributi={"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": nome})


def chat(id, padre, inizio, entrata, cache, uscita):
    return sp("anthropic.messages.create", id, padre, inizio=inizio, attributi={
        "gen_ai.usage.input_tokens": entrata, "gen_ai.usage.cache_read.input_tokens": cache,
        "gen_ai.usage.output_tokens": uscita})


def strumento(id, padre, inizio, errore=False):
    return sp("execute_tool leggi_programma", id, padre, errore=errore, inizio=inizio, attributi={
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "leggi_programma"})


RUN = {"strato": 5, "modo": "guasto", "span": [
    sp("invoke_workflow assistente", "w", attributi={"gen_ai.operation.name": "invoke_workflow"}),
    agente("co", "w", "coordina", 1),
    chat("m1", "co", 2, 1000, 0, 50),
    arco("a1", "co", "coordina", "cerca", 3),
    agente("ce", "a1", "cerca", 4),
    strumento("l1", "ce", 5, errore=True),
    strumento("l2", "ce", 6),
    sp("cache.read", "k", "l2", inizio=7, attributi={"cache.age_hours": 26}),
    arco("a2", "co", "coordina", "cerca", 8),
    agente("ce2", "a2", "cerca", 9),
    arco("a3", "co", "coordina", "valida", 10, **{"gen_ai.tool.call.result": "Il workshop è alle 15:00. Verificato."}),
    agente("va", "a3", "valida", 11),
    chat("m2", "va", 12, 2000, 1000, 100),
]}


def test_segnali_di_una_run():
    g = sg.segnali(RUN)
    assert g["chiamate"] == {"cerca": 2, "leggi_programma": 2, "valida": 1}
    assert g["forma"] == " ".join(s.grafo(RUN["span"]))
    assert g["verdetti"] == [True]
    assert g["copia"] is True
    assert abs(g["costo"] - (s.costo(1000, 0, 50) + s.costo(2000, 1000, 100))) < 1e-12


def test_sotto_lo_strato_minimo_non_si_misura():
    g = sg.segnali({**RUN, "strato": 3})
    assert g["copia"] is None and g["verdetti"] == [True]
    g = sg.segnali({**RUN, "strato": 1})
    assert g["chiamate"] is None and g["forma"] is None and g["verdetti"] is None and g["costo"] is not None


def test_cruscotto():
    sana = {**RUN, "span": [x for x in RUN["span"] if x["nome"] != "cache.read"]}  # stessa run, senza copia
    c = sg.cruscotto([RUN, sana, sana])
    assert c["n"] == 3
    assert c["ritenta"] == {"cerca": 3, "leggi_programma": 3}
    assert c["approva"] == (3, 3) and c["copia"] == 1
    assert sum(c["forme"].values()) == 3
    assert c["costo"]["mediana"] == c["costo"]["p95"]


def test_p95_e_valida_mai_chiamata():
    senza_valida = {**RUN, "span": [x for x in RUN["span"] if "valida" not in x["nome"]]}
    c = sg.cruscotto([senza_valida])
    assert c["approva"] == (0, 0)  # misurabile, e zero: non None
    costi = [0.001 * i for i in range(1, 21)]
    assert sg.p95(costi) == statistics.quantiles(costi, n=20, method="inclusive")[18]
    assert sg.p95([0.5]) == 0.5


def test_strato_misto_rende_none():
    assert sg.cruscotto([RUN, {**RUN, "strato": 3}])["copia"] is None


REG = Path(__file__).parent / "registrazioni"


def leggi(nome, modo="guasto"):
    return [r for f in sorted((REG / nome).glob("*.json")) if (r := json.loads(f.read_text()))["modo"] == modo]


def test_coerenti_con_misura_sul_freeze():
    regs = leggi("strato-5-freeze")
    c = sg.cruscotto(regs)
    assert c["approva"][0] == sum(s.misura(r)["valida_approva"] for r in regs)
    assert c["ritenta"].get("cerca", 0) == sum(s.misura(r)["cerca_di_nuovo"] > 0 for r in regs)


def test_costo_dagli_span_uguale_alla_fattura():
    for nome in ("strato-1", "strato-5", "strato-5-freeze"):
        for r in leggi(nome):
            f = r["fattura"]
            assert abs(sg.segnali(r)["costo"] - s.costo(f["in"], f["cache"], f["out"])) < 1e-9, nome


def test_stampa_dice_cosa_manca():
    with contextlib.redirect_stdout(io.StringIO()) as fuori:
        sg.stampa("strato-1 · guasto", sg.cruscotto(leggi("strato-1")))
    testo = fuori.getvalue()
    assert "95° percentile" in testo and "serve lo strato 4" in testo and "serve lo strato 3" in testo


if __name__ == "__main__":
    for nome, prova in list(globals().items()):
        if nome.startswith("test_"):
            prova()
            print("ok", nome)
