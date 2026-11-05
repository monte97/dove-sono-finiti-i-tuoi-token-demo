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


def test_avvisi_riporta_falsi_positivi():
    assert not s.riporta_avviso("Nessun avviso sulla sala B. Keynote di chiusura alle 17:30.")  # sala e causa in frasi diverse
    assert not s.riporta_avviso("Non risultano avvisi di chiusura o manutenzione per la sala B.")  # negazione
    assert not s.riporta_avviso("Sala B: la keynote di chiusura è spostata alle 17:30.")  # «chiusura» da sola e' rumore
    assert s.riporta_avviso("La sala B chiude alle 15, le sessioni del pomeriggio sono anticipate di un'ora.")  # parafrasi
    assert s.riporta_avviso("- Sala B: chiusa dalle 15:00 per manutenzione.\n- Prova dell'allarme alle 11:00.")
    assert s.riporta_avviso(s.AVVISO_CHIAVE)
    for v in (v for p in s.avvisi(True) for v in p if v != s.AVVISO_CHIAVE):  # nessun avviso di rumore scatta
        assert not s.riporta_avviso(v), v
    assert not s.riporta_avviso("Per il workshop controllare in sala.")  # limite noto: senza parole chiave la parafrasi sfugge
    assert not s.riporta_avviso("La B non si usa nel pomeriggio.")


def test_controllo_salta_il_formato_vecchio():
    import tempfile, json
    from pathlib import Path
    import controllo
    d = Path(tempfile.mkdtemp())
    (d / "vecchia.json").write_text(json.dumps({**run(), "dominio": "orario"}))
    (d / "senza-log.json").write_text(json.dumps(run()))
    (d / "nuova.json").write_text(json.dumps({**run(), "log_otel": []}))
    assert len(controllo.leggi(d, "guasto")) == 1
    (d / "nuova.json").unlink()
    assert controllo.leggi(d, "guasto") == []
    vero_banco, veri_casi = controllo.BANCO, list(controllo.CASI)
    nuovo = Path(tempfile.mkdtemp())
    (d / "k").mkdir()
    (d / "k" / "x.json").write_text(json.dumps({**run(), "dominio": "orario"}))  # il banco c'e', ma e' del sistema vecchio
    (nuovo / "k").mkdir()
    (nuovo / "k" / "x.json").write_text(json.dumps({**run(), "log_otel": []}))
    controllo.BANCO, controllo.CASI[:] = d, [("k", 0, True)]
    try:
        with contextlib.redirect_stdout(io.StringIO()) as fuori:
            controllo.confronta(nuovo)
        assert "banco da rigenerare" in fuori.getvalue()
    finally:
        controllo.BANCO, controllo.CASI[:] = vero_banco, veri_casi


if __name__ == "__main__":
    for nome, prova in list(globals().items()):
        if nome.startswith("test_"):
            prova()
            print("ok", nome)
